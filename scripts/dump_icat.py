"""Dev check (run INSIDE kitty): what exactly does kitten icat print for our command line?
    kitty python3 scripts/dump_icat.py PICTURE RESULT_FILE"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from swayforge import kittyimg  # noqa: E402

pic, out = sys.argv[1], sys.argv[2]
res = []
for cols, rows in ((40, 12), (60, 16)):
    cmd = kittyimg.build_cmd(pic, cols, rows, 4242)
    p = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)
    res.append("cmd: " + " ".join(cmd))
    raw = p.stdout.decode("utf-8", "replace")
    res.append(f"returncode {p.returncode}, stdout {len(raw)} chars, stderr {p.stderr[:200]!r}")
    body = kittyimg.APC_RE.sub("<APC>", raw)
    res.append("body head: " + repr(body[:300]))
    res.append("body tail: " + repr(body[-200:]))
    tr, lines, iid = kittyimg.parse(raw)
    res.append(f"parsed: {len(lines)} lines, id {iid}, widths {[ln.count(kittyimg.PLACEHOLDER) for ln in lines]}")
    res.append("line0: " + repr(lines[0][:60]) if lines else "no lines")
    res.append("line1: " + repr(lines[1][:60]) if len(lines) > 1 else "")
    res.append("apc: " + repr(tr[:300]))
    res.append("")
open(out, "w").write("\n".join(res) + "\n")
