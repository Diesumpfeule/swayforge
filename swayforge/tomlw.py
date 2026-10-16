"""Minimal TOML writer (Python has tomllib for reading but nothing for writing)."""
from __future__ import annotations

import json
import re

_BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(k: str) -> str:
    return k if _BARE.match(k) else json.dumps(k)


def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_val(x) for x in v) + "]"
    if isinstance(v, dict):  # inline table
        return "{ " + ", ".join(f"{_key(k)} = {_val(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"TOML: type {type(v)} not supported")


def dumps(data: dict, _prefix: str = "") -> str:
    out: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    for k, v in scalars.items():
        out.append(f"{_key(k)} = {_val(v)}")
    for k, v in tables.items():
        name = f"{_prefix}.{_key(k)}" if _prefix else _key(k)
        out.append("")
        out.append(f"[{name}]")
        body = dumps(v, name)
        if body.strip():
            out.append(body.strip("\n"))
    return "\n".join(out).lstrip("\n") + "\n"
