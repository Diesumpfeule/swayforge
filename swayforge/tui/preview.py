"""KittyPreview: a widget that shows a picture through kitty's graphics protocol (see ../kittyimg.py).

Outside kitty it shows a one-line hint instead, so callers never have to special-case it."""
from __future__ import annotations

import threading

from rich.segment import Segment
from rich.style import Style
from textual.color import Color
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from .. import kittyimg


class KittyPreview(Widget):
    DEFAULT_CSS = """
    KittyPreview { height: 14; min-height: 6; width: 1fr; }
    """
    message = reactive("Select a picture to preview it.")

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.placement: kittyimg.Placement | None = None
        self._path = ""
        self._gen = 0
        self._procs: list = []

    # ---- public ----
    def show(self, path: str) -> None:
        """Preview <path> (non-blocking; a newer call cancels an older one)."""
        st = kittyimg.status()
        if not st.ok:
            self._drop()
            self.message = st.reason
            return
        self._path = path
        self._gen += 1
        gen = self._gen
        for p in self._procs:
            try:
                p.kill()
            except OSError:
                pass
        self._procs = procs = []
        w, h = self.size.width, self.size.height
        if w < 2 or h < 1:
            return
        self.message = "Loading preview …"
        self.refresh()
        threading.Thread(target=self._work, args=(path, w, h, gen, procs), daemon=True).start()

    def clear(self, message: str = "") -> None:
        self._gen += 1
        self._path = ""
        self._drop()
        if message:
            self.message = message

    # ---- internals ----
    def _work(self, path: str, w: int, h: int, gen: int, procs: list) -> None:
        try:
            pl = kittyimg.render(path, w, h, proc_holder=procs)
        except RuntimeError as e:
            if gen == self._gen:
                self.app.call_from_thread(self._failed, str(e), gen)
            return
        if gen == self._gen:
            self.app.call_from_thread(self._ready, pl, gen)

    def _failed(self, msg: str, gen: int) -> None:
        if gen == self._gen:
            self._drop()
            self.message = f"No preview: {msg}"

    def _ready(self, pl: kittyimg.Placement, gen: int) -> None:
        if gen != self._gen:
            return
        self._drop()
        self._write(pl.transmit)
        self.placement = pl
        self.refresh()

    def _write(self, data: str) -> None:
        drv = getattr(self.app, "_driver", None)
        if drv is not None:
            drv.write(data)

    def _drop(self) -> None:
        if self.placement is not None:
            self._write(self.placement.free_command)
            self.placement = None
            self.refresh()

    def on_unmount(self) -> None:
        self._gen += 1
        self._drop()

    def on_resize(self) -> None:
        if self._path and self.placement is not None:
            self.show(self._path)

    def render_line(self, y: int) -> Strip:
        w = self.size.width
        pl = self.placement
        if pl is None:
            if y == 0:
                return Strip([Segment(str(self.message)[:w].ljust(w), Style(dim=True))])
            return Strip.blank(w)
        if y >= len(pl.lines):
            return Strip.blank(w)
        r, g, b = kittyimg.placeholder_color(pl.image_id)
        line = pl.lines[y]
        style = Style(color=f"rgb({r},{g},{b})")
        used = line.count(kittyimg.PLACEHOLDER)
        segs = [Segment(line, style)]
        if used < w:
            segs.append(Segment(" " * (w - used)))
        return Strip(segs, w)
