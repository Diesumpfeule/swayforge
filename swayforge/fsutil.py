"""Safe file writing: a crash, a full disk or a power cut never leaves a half-written config."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path | str, data: str | bytes, mode: int | None = None) -> None:
    """Write to a temporary file next to `path`, flush it to disk, then swap it in with one rename.
    Readers see either the old or the new file – never a mix. Keeps the old file's permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode() if isinstance(data, str) else data
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o7777
        except OSError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
