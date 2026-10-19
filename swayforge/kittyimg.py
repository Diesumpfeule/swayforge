"""Image previews inside the terminal UI through kitty's graphics protocol.

No image library of our own: `kitten icat` (shipped with kitty) decodes and scales the picture and
hands it to the terminal. We ask it for *Unicode placeholders* (--unicode-placeholder): the picture
then lives in the terminal and what the UI has to draw is ordinary text (U+10EEEE + diacritics,
coloured with the image id). Because that is just text, the picture moves, scrolls and is
redrawn together with the rest of the interface – no overlay positioning, no flicker.

    1. run  kitten icat --unicode-placeholder …   (its stdout = transmit commands + placeholder text)
    2. send the transmit commands (ESC _ G … ESC \\) to the terminal once
    3. draw the placeholder lines as text
    4. when the picture goes away: delete the image in the terminal (free_command)

Only works in kitty itself (not over SSH, tmux or other terminals) – `available()` says so and the
callers show a plain text hint instead.
"""
from __future__ import annotations

import fcntl
import itertools
import os
import re
import shutil
import struct
import subprocess
import sys
import termios
import threading
from dataclasses import dataclass, field

PLACEHOLDER = "\U0010EEEE"
APC_RE = re.compile(r"\x1b_G.*?\x1b\\", re.S)
SGR_ID_RE = re.compile(r"\x1b\[38:2:(\d+):(\d+):(\d+)m")
ANY_ESC_RE = re.compile(r"\x1b\[[0-9;:]*[A-Za-z]")
FIRST_ID = 1000                       # our image ids: 1000, 1001, … (unique inside this process)
_ids = itertools.count(FIRST_ID)
_lock = threading.Lock()


@dataclass
class Placement:
    image_id: int
    lines: list[str]                  # placeholder text, one string per row
    transmit: str                     # escape commands that put the picture into the terminal
    cols: int = 0
    rows: int = 0
    path: str = ""

    @property
    def free_command(self) -> str:
        return free_command(self.image_id)


@dataclass
class Status:
    ok: bool
    reason: str = ""                  # shown to the user when not ok


def free_command(image_id: int) -> str:
    """Delete the image (and its data) from the terminal."""
    return f"\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\"


def status() -> Status:
    """Can we show pictures here? Needs kitty itself and its `kitten` helper."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return Status(False, "no preview over SSH (kitty reads the image file from this computer)")
    if os.environ.get("TMUX") or os.environ.get("STY"):
        return Status(False, "no preview inside tmux/screen")
    if not (os.environ.get("KITTY_WINDOW_ID") or os.environ.get("TERM") == "xterm-kitty"):
        term = os.environ.get("TERM_PROGRAM") or os.environ.get("TERM") or "this terminal"
        return Status(False, f"preview needs the kitty terminal ({term} can't show images here)")
    if not shutil.which("kitten"):
        return Status(False, "preview needs kitty's `kitten` tool (installed with kitty)")
    return Status(True)


def available() -> bool:
    return status().ok


def window_size(fd: int | None = None) -> tuple[int, int, int, int]:
    """(columns, rows, width px, height px) of the terminal; pixel size guessed if the terminal hides it."""
    cols, rows, xpx, ypx = 80, 24, 0, 0
    for f in ([fd] if fd is not None else []) + [1, 0, 2]:
        try:
            rows, cols, xpx, ypx = struct.unpack("HHHH", fcntl.ioctl(f, termios.TIOCGWINSZ, b"\0" * 8))
            break
        except (OSError, ValueError):
            continue
    cols, rows = max(cols, 20), max(rows, 10)
    if not xpx or not ypx:
        xpx, ypx = cols * 10, rows * 20
    return cols, rows, xpx, ypx


def parse(output: str) -> tuple[str, list[str], int]:
    """Split icat's output into (transmit commands, placeholder lines, image id)."""
    transmit = "".join(APC_RE.findall(output))
    body = APC_RE.sub("", output)
    m = SGR_ID_RE.search(body)
    image_id = (int(m.group(1)) << 16 | int(m.group(2)) << 8 | int(m.group(3))) if m else 0
    body = ANY_ESC_RE.sub("", body)
    lines = [ln for ln in body.replace("\r", "").split("\n") if PLACEHOLDER in ln]
    return transmit, lines, image_id


def render(path: str, cols: int, rows: int, timeout: float = 20,
           proc_holder: list | None = None) -> Placement:
    """Let kitten icat prepare <path> to fit into cols×rows cells. Raises RuntimeError on failure.
    proc_holder: a list that receives the running process (so a newer request can kill this one)."""
    if cols < 2 or rows < 1:
        raise RuntimeError("no room for a picture")
    wc, wr, wx, wy = window_size()
    with _lock:
        image_id = next(_ids)
    mode = "file"
    cmd = ["kitten", "icat", "--unicode-placeholder", "--transfer-mode", mode, "--stdin", "no",
           "--align", "left", "--passthrough", "none", "--scale-up", "--image-id", str(image_id),
           "--use-window-size", f"{wc},{wr},{wx},{wy}",
           "--place", f"{cols}x{rows}@0x0", "--", path]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    except OSError as e:
        raise RuntimeError(f"can't run kitten: {e}") from e
    if proc_holder is not None:
        proc_holder.append(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise RuntimeError("kitten icat took too long") from None
    if p.returncode != 0:
        msg = err.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(msg[-1] if msg else f"kitten icat failed ({p.returncode})")
    transmit, lines, got_id = parse(out.decode("utf-8", "replace"))
    if not lines or not transmit:
        raise RuntimeError("kitten icat gave no picture")
    cells = max(ln.count(PLACEHOLDER) for ln in lines)
    return Placement(got_id or image_id, lines, transmit, cells, len(lines), path)


def placeholder_color(image_id: int) -> tuple[int, int, int]:
    """Foreground colour that encodes the image id (24-bit)."""
    return (image_id >> 16) & 255, (image_id >> 8) & 255, image_id & 255
