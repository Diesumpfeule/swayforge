"""WallGrid: wallpaper thumbnails in a grid, one PAGE at a time (kitty graphics, see ../kittyimg.py).

Only the pictures of the current page are ever loaded (one kitten icat run at a time); turning the page
frees them and drops anything still waiting. So 5000 pictures cost the same as 10.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.events import Click
from textual.message import Message
from textual.widget import Widget
from textual.strip import Strip

from .. import kittyimg

TILE_W = 26                     # cells per tile
IMG_H = 7                       # picture rows per tile (+1 row for the file name)
TILE_H = IMG_H + 1
GAP = 1


class WallGrid(Widget, can_focus=True):
    DEFAULT_CSS = """
    WallGrid { height: 26; border: round $panel; }
    WallGrid:focus { border: round $accent; }
    """
    BINDINGS = [
        Binding("left", "move(-1, 0)", "Left", show=False),
        Binding("right", "move(1, 0)", "Right", show=False),
        Binding("up", "move(0, -1)", "Up", show=False),
        Binding("down", "move(0, 1)", "Down", show=False),
        Binding("pageup", "page(-1)", "Previous page", show=False),
        Binding("pagedown", "page(1)", "Next page", show=False),
        Binding("home", "jump(0)", "First", show=False),
        Binding("end", "jump(-1)", "Last", show=False),
        Binding("enter", "choose", "Set", show=False),
        Binding("space", "choose", "Set", show=False),
    ]

    class Highlighted(Message):
        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    class Chosen(Message):
        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    class PageChanged(Message):
        def __init__(self, page: int, pages: int, total: int) -> None:
            super().__init__()
            self.page, self.pages, self.total = page, pages, total

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.files: list[Path] = []
        self.sel = 0
        self.cache: dict[int, kittyimg.Placement] = {}
        self.queue: list[int] = []
        self.busy = False
        self.failed: dict[int, str] = {}
        self._gen = 0
        self._shape = (0, 0)
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._status = kittyimg.status()

    # ---- geometry ----
    @property
    def cols(self) -> int:
        return max(1, (self.size.width + GAP) // (TILE_W + GAP))

    @property
    def rows(self) -> int:
        return max(1, self.size.height // TILE_H)

    @property
    def per_page(self) -> int:
        return self.cols * self.rows

    @property
    def page(self) -> int:
        return self.sel // self.per_page

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.files) // self.per_page))

    # ---- data ----
    def set_files(self, files: list[Path], root: Path | None = None) -> None:
        self._free_all()
        self.files, self.sel = list(files), 0
        self._status = kittyimg.status()
        self._shape = (self.cols, self.rows)
        self._changed(True)

    def release(self) -> None:
        """Take every thumbnail out of the terminal (view hidden / page left)."""
        self._free_all()
        self.refresh()

    def on_resize(self) -> None:
        if (self.cols, self.rows) != self._shape and self.files:
            self._shape = (self.cols, self.rows)
            self._free_all()
            self._changed(True)
        self.refresh()

    def _changed(self, new_page: bool) -> None:
        if new_page:
            self._free_all()
            self.post_message(self.PageChanged(self.page + 1, self.pages, len(self.files)))
        if self.files:
            self.post_message(self.Highlighted(self.files[self.sel]))
        self.refresh()

    # ---- loading (current page only) ----
    def _request(self, i: int) -> None:
        if i in self.cache or i in self.queue or i in self.failed:
            return
        self.queue.append(i)
        self._next()

    def _next(self) -> None:
        if self.busy or not self.queue:
            return
        i = self.queue.pop(0)
        if not 0 <= i < len(self.files):
            return self._next()
        self.busy = True
        self._pool.submit(self._work, i, str(self.files[i]), self._gen)

    def _work(self, i: int, path: str, gen: int) -> None:
        if gen != self._gen:
            result: kittyimg.Placement | str = "skipped"
        else:
            try:
                result = kittyimg.render(path, TILE_W, IMG_H)
            except RuntimeError as e:
                result = str(e)
        try:
            self.app.call_from_thread(self._done, i, result, gen)
        except RuntimeError:
            pass                                       # app already closed

    def _done(self, i: int, result, gen: int) -> None:
        self.busy = False
        if gen == self._gen:
            if isinstance(result, str):
                self.failed[i] = result
            else:
                self._write(result.transmit)
                self.cache[i] = result
            self.refresh()
        elif not isinstance(result, str):
            self._write(result.free_command)           # arrived after the page was turned
        self._next()

    def _free_all(self) -> None:
        self._gen += 1
        for pl in self.cache.values():
            self._write(pl.free_command)
        self.cache.clear()
        self.queue.clear()
        self.failed.clear()

    def _write(self, data: str) -> None:
        drv = getattr(self.app, "_driver", None)
        if drv is not None:
            drv.write(data)

    def on_unmount(self) -> None:
        self._free_all()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- drawing ----
    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if not self._status.ok:
            text = f"No preview here: {self._status.reason}" if y == 0 else ""
            return Strip([Segment(text[:width].ljust(width), Style(dim=True))], width)
        if not self.files:
            return Strip([Segment(("No pictures." if y == 0 else "").ljust(width), Style(dim=True))], width)
        row, ty = divmod(y, TILE_H)
        if row >= self.rows:
            return Strip.blank(width)
        segs: list[Segment] = []
        used_w = 0
        base = self.page * self.per_page
        for c in range(self.cols):
            i = base + row * self.cols + c
            if i >= len(self.files):
                break
            segs += self._tile_segments(i, ty)
            used_w += TILE_W
            if c < self.cols - 1:
                segs.append(Segment(" " * GAP))
                used_w += GAP
        if used_w < width:
            segs.append(Segment(" " * (width - used_w)))
        return Strip(segs, max(used_w, width))

    def _tile_segments(self, i: int, ty: int) -> list[Segment]:
        if ty == IMG_H:                                # file name under the picture
            name = self.files[i].name
            if len(name) > TILE_W:
                name = name[:TILE_W - 1] + "…"
            style = Style(bold=True, reverse=True) if i == self.sel else Style(dim=True)
            return [Segment(name.ljust(TILE_W), style)]
        pl = self.cache.get(i)
        if pl is not None and ty < len(pl.lines):
            r, g, b = kittyimg.placeholder_color(pl.image_id)
            line = pl.lines[ty].replace("\x1b", "")
            n = line.count(kittyimg.PLACEHOLDER)
            segs = [Segment(line, Style(color=f"rgb({r},{g},{b})"))]
            if n < TILE_W:
                segs.append(Segment(" " * (TILE_W - n)))
            return segs
        if ty == 0:
            self._request(i)
        msg = ""
        if ty == IMG_H // 2:
            msg = "no preview" if i in self.failed else "…"
        return [Segment(msg.center(TILE_W)[:TILE_W].ljust(TILE_W), Style(dim=True))]

    # ---- selection / paging ----
    def _select(self, i: int) -> None:
        if not self.files:
            return
        i = max(0, min(len(self.files) - 1, i))
        turned = i // self.per_page != self.page
        self.sel = i
        self._changed(turned)

    def action_move(self, dx: int, dy: int) -> None:
        self._select(self.sel + dx + dy * self.cols)

    def action_page(self, d: int) -> None:
        self.go_page(self.page + d)

    def go_page(self, p: int) -> None:
        p = max(0, min(self.pages - 1, p))
        if p != self.page:
            self._select(p * self.per_page)

    def action_jump(self, i: int) -> None:
        self._select(i if i >= 0 else len(self.files) - 1)

    def action_choose(self) -> None:
        if self.files:
            self.post_message(self.Chosen(self.files[self.sel]))

    def on_click(self, ev: Click) -> None:
        self.focus()
        col, row = ev.x // (TILE_W + GAP), ev.y // TILE_H
        if col >= self.cols or row >= self.rows:
            return
        i = self.page * self.per_page + row * self.cols + col
        if 0 <= i < len(self.files):
            self._select(i)
            if getattr(ev, "chain", 1) >= 2:
                self.post_message(self.Chosen(self.files[i]))
