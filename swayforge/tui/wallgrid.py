"""WallGrid: many wallpaper thumbnails at once, in a scrollable grid (kitty graphics, see ../kittyimg.py).

Each tile is one picture drawn with Unicode placeholders – ordinary text, so it scrolls with the widget.
Only tiles that are actually on screen get loaded (kitten icat, 3 at a time); tiles far away are freed again.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.events import Click
from textual.geometry import Region, Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip

from .. import kittyimg

TILE_W = 26                     # cells per tile
IMG_H = 7                       # picture rows per tile (+1 row for the file name)
TILE_H = IMG_H + 1
GAP = 1
MAX_LOADED = 90                 # thumbnails kept in the terminal at once


class WallGrid(ScrollView, can_focus=True):
    DEFAULT_CSS = """
    WallGrid { height: 24; border: round $panel; }
    WallGrid:focus { border: round $accent; }
    """
    BINDINGS = [
        Binding("left", "move(-1, 0)", "Left", show=False),
        Binding("right", "move(1, 0)", "Right", show=False),
        Binding("up", "move(0, -1)", "Up", show=False),
        Binding("down", "move(0, 1)", "Down", show=False),
        Binding("pageup", "page(-1)", "Page up", show=False),
        Binding("pagedown", "page(1)", "Page down", show=False),
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

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.files: list[Path] = []
        self.root: Path | None = None
        self.sel = 0
        self.cache: dict[int, kittyimg.Placement] = {}
        self.pending: set[int] = set()
        self.failed: dict[int, str] = {}
        self._gen = 0
        self._pool = ThreadPoolExecutor(max_workers=3)
        self._status = kittyimg.status()

    # ---- data ----
    def set_files(self, files: list[Path], root: Path | None) -> None:
        self._free_all()
        self.files, self.root, self.sel = list(files), root, 0
        self._status = kittyimg.status()
        self._relayout()
        self.scroll_to(0, 0, animate=False)
        self.refresh()
        if self.files:
            self.post_message(self.Highlighted(self.files[0]))

    def release(self) -> None:
        """Take every thumbnail out of the terminal (view hidden / page left)."""
        self._free_all()
        self.refresh()

    # ---- geometry ----
    @property
    def cols(self) -> int:
        return max(1, (self.size.width + GAP) // (TILE_W + GAP))

    @property
    def nrows(self) -> int:
        return (len(self.files) + self.cols - 1) // self.cols

    def _relayout(self) -> None:
        self.virtual_size = Size(self.size.width, max(self.nrows * TILE_H, 1))

    def on_resize(self) -> None:
        self._relayout()
        self.refresh()

    # ---- loading ----
    def _request(self, i: int) -> None:
        if i in self.cache or i in self.pending or i in self.failed or not (0 <= i < len(self.files)):
            return
        self.pending.add(i)
        gen, path = self._gen, str(self.files[i])
        self._pool.submit(self._work, i, path, gen)

    def _work(self, i: int, path: str, gen: int) -> None:
        try:
            pl = kittyimg.render(path, TILE_W, IMG_H)
            result: kittyimg.Placement | str = pl
        except RuntimeError as e:
            result = str(e)
        if gen == self._gen:
            try:
                self.app.call_from_thread(self._done, i, result, gen)
            except RuntimeError:
                pass                                   # app already closed

    def _done(self, i: int, result, gen: int) -> None:
        if gen != self._gen:
            return
        self.pending.discard(i)
        if isinstance(result, str):
            self.failed[i] = result
        else:
            self._write(result.transmit)
            self.cache[i] = result
            self._evict()
        self.refresh()

    def _evict(self) -> None:
        if len(self.cache) <= MAX_LOADED:
            return
        here = self.sel
        for i in sorted(self.cache, key=lambda k: -abs(k - here))[:len(self.cache) - MAX_LOADED]:
            self._write(self.cache.pop(i).free_command)

    def _free_all(self) -> None:
        self._gen += 1
        for pl in self.cache.values():
            self._write(pl.free_command)
        self.cache.clear()
        self.pending.clear()
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
        ay = y + self.scroll_offset.y
        if not self._status.ok:
            text = f"No preview here: {self._status.reason}" if y == 0 else ""
            return Strip([Segment(text[:width].ljust(width), Style(dim=True))], width)
        if not self.files:
            return Strip([Segment(("No pictures." if y == 0 else "").ljust(width), Style(dim=True))], width)
        row, ty = divmod(ay, TILE_H)
        if row >= self.nrows:
            return Strip.blank(width)
        segs: list[Segment] = []
        used_w = 0
        for c in range(self.cols):
            i = row * self.cols + c
            if i >= len(self.files):
                break
            tile = self._tile_segments(i, ty)
            segs += tile
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
        self._request(i)
        msg = ""
        if ty == IMG_H // 2:
            msg = "no preview" if i in self.failed else "…"
        return [Segment(msg.center(TILE_W)[:TILE_W].ljust(TILE_W), Style(dim=True))]

    # ---- selection ----
    def _select(self, i: int, notify: bool = True) -> None:
        if not self.files:
            return
        i = max(0, min(len(self.files) - 1, i))
        if i == self.sel and not notify:
            return
        self.sel = i
        row = i // self.cols
        self.scroll_to_region(Region(0, row * TILE_H, 1, TILE_H), animate=False, spacing=None)
        self.refresh()
        if notify:
            self.post_message(self.Highlighted(self.files[i]))

    def action_move(self, dx: int, dy: int) -> None:
        self._select(self.sel + dx + dy * self.cols)

    def action_page(self, d: int) -> None:
        rows = max(1, self.size.height // TILE_H)
        self._select(self.sel + d * rows * self.cols)

    def action_jump(self, i: int) -> None:
        self._select(i if i >= 0 else len(self.files) - 1)

    def action_choose(self) -> None:
        if self.files:
            self.post_message(self.Chosen(self.files[self.sel]))

    def on_click(self, ev: Click) -> None:
        self.focus()
        col = ev.x // (TILE_W + GAP)
        row = (ev.y + self.scroll_offset.y) // TILE_H
        if col >= self.cols:
            return
        i = row * self.cols + col
        if 0 <= i < len(self.files):
            self._select(i)
            if ev.chain >= 2:
                self.post_message(self.Chosen(self.files[i]))
