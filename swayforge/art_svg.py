"""Procedural shapes for wallpapers and boot screens (deterministic, no image files needed)."""
from __future__ import annotations

import functools
import math
import random


def branches(seed: int, x: float, y: float, angle: float, length: float, depth: int,
             width: float = 18.0) -> list[tuple[str, float]]:
    """Recursive tree branch silhouette → list of (svg path, stroke width)."""
    rnd = random.Random(seed)
    out: list[tuple[str, float]] = []

    def grow(x0, y0, ang, ln, d, w):
        if d == 0 or ln < 6:
            return
        bend = rnd.uniform(-0.35, 0.35)
        x1 = x0 + math.cos(ang) * ln
        y1 = y0 + math.sin(ang) * ln
        cx = x0 + math.cos(ang + bend) * ln * 0.55
        cy = y0 + math.sin(ang + bend) * ln * 0.55
        out.append((f"M{x0:.0f} {y0:.0f} Q{cx:.0f} {cy:.0f} {x1:.0f} {y1:.0f}", max(w, 1.2)))
        for _ in range(rnd.choice((2, 2, 3))):
            grow(x1, y1, ang + rnd.uniform(-0.75, 0.75), ln * rnd.uniform(0.62, 0.8), d - 1, w * 0.68)

    grow(x, y, angle, length, depth, width)
    return out


def stars(seed: int, n: int, w: int = 3840, h: int = 2160) -> list[tuple[int, int, float, float]]:
    rnd = random.Random(seed)
    return [(rnd.randrange(w), rnd.randrange(int(h * 0.8)), rnd.choice((1.2, 1.6, 2.2, 3.0)),
             rnd.uniform(0.3, 1.0)) for _ in range(n)]


def leaves(seed: int, n: int, w: int = 3840, h: int = 2160) -> list[tuple[int, int, int, float, float]]:
    """(x, y, rotation, scale, opacity) for falling leaves."""
    rnd = random.Random(seed)
    return [(rnd.randrange(w), rnd.randrange(h), rnd.randrange(360), rnd.uniform(0.6, 2.4),
             rnd.uniform(0.15, 0.6)) for _ in range(n)]


LEAF = ("M0 -40 C 18 -30 30 -10 26 10 C 22 28 8 38 0 46 C -8 38 -22 28 -26 10 "
        "C -30 -10 -18 -30 0 -40 Z M0 -40 L0 52")


def network(seed: int, n: int, w: int = 3840, h: int = 2160):
    """Nodes and edges for the wired wallpaper."""
    rnd = random.Random(seed)
    nodes = [(rnd.randrange(80, w - 80), rnd.randrange(80, h - 80)) for _ in range(n)]
    edges = []
    for i, (x, y) in enumerate(nodes):
        near = sorted(range(n), key=lambda j: (nodes[j][0] - x) ** 2 + (nodes[j][1] - y) ** 2)[1:3]
        edges += [(i, j) for j in near if (j, i) not in edges]
    return nodes, edges


def noise(seed: int, n: int, w: int = 3840, h: int = 2160) -> list[tuple[int, int, int, float]]:
    rnd = random.Random(seed)
    return [(rnd.randrange(w), rnd.randrange(h), rnd.choice((2, 3, 4)), rnd.uniform(0.04, 0.18))
            for _ in range(n)]


@functools.cache
def extras() -> dict:
    """Everything the wallpaper templates may use."""
    trees = (branches(7, -40, 220, 0.25, 420, 7, 26) + branches(11, 3880, 160, math.pi - 0.3, 440, 7, 26)
             + branches(23, 3600, 2200, -math.pi / 2 - 0.35, 380, 6, 22)
             + branches(31, 260, 2200, -math.pi / 2 + 0.25, 360, 6, 20))
    nodes, edges = network(5, 46)
    return {"trees": trees, "stars": stars(3, 420), "leaves": leaves(9, 70), "leaf": LEAF,
            "nodes": nodes, "edges": edges, "noise": noise(13, 1400)}
