"""Dev check (run INSIDE kitty): does the terminal accept what swayforge/kittyimg.py sends?

Renders one picture with kitten icat, sends the transmit command with answers switched on and reads
kitty's reply from the tty. Writes the verdict to the file given as argv[2].
    kitty python3 scripts/check_kitty_graphics.py PICTURE RESULT_FILE
"""
import os
import select
import sys
import termios
import tty

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from swayforge import kittyimg  # noqa: E402

pic, out = sys.argv[1], sys.argv[2]
res = []
try:
    pl = kittyimg.render(pic, 40, 12)
    res.append(f"render ok: id={pl.image_id} cells={pl.cols}x{pl.rows} lines={len(pl.lines)}")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    try:
        sys.stdout.write(pl.transmit.replace(",q=2", ",q=0").replace("q=2,", "q=0,"))
        sys.stdout.flush()
        buf = b""
        while b"\x1b\\" not in buf:
            r, _, _ = select.select([fd], [], [], 5)
            if not r:
                break
            buf += os.read(fd, 4096)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    res.append("terminal reply: " + repr(buf))
    res.append("ACCEPTED" if b";OK" in buf else "NOT ACCEPTED")
    sys.stdout.write(pl.free_command)
    sys.stdout.flush()
except Exception as e:  # noqa: BLE001
    res.append(f"FAILED: {e!r}")
open(out, "w").write("\n".join(res) + "\n")
