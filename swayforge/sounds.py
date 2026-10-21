"""System sounds: a freedesktop sound theme synthesised in pure Python (no samples, no deps).

One pack per look – classic bleeps, glass chimes, soft 11 pings, touch taps, wired blips and a
gothic pack (church bell, organ chord, funeral drone). The pack is written as a sound theme to
~/.local/share/sounds/swayforge/ and selected through GSettings; notifications (mako) and the
login chime play events by name via canberra, so every GTK/Qt app that asks for an event
sound picks the theme up too. Original sounds of swayforge.
"""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

from . import paths

RATE = 44100
THEME_DIR = paths.HOME / ".local/share/sounds/swayforge"
PACKS = {
    "classic": "Classic bleeps (Win98)", "glass": "Glass chimes (7)", "modern": "Soft pings (11)",
    "touch": "Touch taps", "wired": "Wired blips", "gothic": "Gothic bells & organ",
    "soft": "Soft default",
}
EVENTS = ["desktop-login", "desktop-logout", "message-new-instant", "message", "dialog-error",
          "dialog-warning", "dialog-information", "power-plug", "power-unplug", "device-added",
          "device-removed", "bell", "complete", "battery-low", "screen-capture",
          "audio-volume-change"]
LAYOUT_PACK = {"win98": "classic", "winxp": "glass", "win7": "glass", "win11": "modern", "touch": "touch",
               "wired": "wired", "cathedral": "gothic", "dread": "gothic", "glass": "modern"}


def pack_for(s: dict, theme_id: str, layout: str) -> str:
    choice = s.get("sound", {}).get("pack", "auto")
    if choice in PACKS:
        return choice
    if theme_id == "requiem":
        return "gothic"
    return LAYOUT_PACK.get(layout, "soft")


# ── synthesis ────────────────────────────────────────────────────────
def _env(n: int, a: float, r: float, curve: float = 3.0) -> list[float]:
    """Attack/exponential-release envelope over n samples."""
    na = max(1, int(a * RATE))
    out = []
    for i in range(n):
        out.append(i / na if i < na else math.exp(-curve * (i - na) / max(1, n - na)) * (1 - r * (i / n)))
    return out


def _wave(kind: str, ph: float) -> float:
    if kind == "square":
        return 1.0 if ph % 1 < 0.5 else -1.0
    if kind == "tri":
        return 4 * abs(ph % 1 - 0.5) - 1
    if kind == "saw":
        return 2 * (ph % 1) - 1
    return math.sin(math.tau * ph)


def tone(f: float, dur: float, kind: str = "sine", vol: float = 0.5, a: float = 0.005,
         curve: float = 3.0, slide: float = 0.0) -> list[float]:
    n = int(dur * RATE)
    env = _env(n, a, 0.0, curve)
    out, ph = [], 0.0
    for i in range(n):
        ph += (f + slide * i / n) / RATE
        out.append(_wave(kind, ph) * env[i] * vol)
    return out


def bell(f: float, dur: float = 2.5, vol: float = 0.5) -> list[float]:
    """Struck bell: inharmonic partials, each fading at its own speed."""
    n = int(dur * RATE)
    parts = [(0.5, 1.0, 1.0), (1.0, 0.9, 1.4), (1.19, 0.5, 2.0), (1.56, 0.4, 2.4),
             (2.0, 0.55, 2.8), (2.74, 0.3, 3.6), (3.0, 0.25, 4.2), (4.07, 0.15, 5.5)]
    out = [0.0] * n
    for ratio, amp, decay in parts:
        w = math.tau * f * ratio / RATE
        for i in range(n):
            t = i / RATE
            out[i] += math.sin(w * i) * amp * math.exp(-decay * t * 1.6)
    k = vol / max(abs(x) for x in out)
    return [x * k * min(1.0, i / 60) for i, x in enumerate(out)]


def organ(freqs: list[float], dur: float = 2.2, vol: float = 0.4) -> list[float]:
    n = int(dur * RATE)
    env = [min(1.0, i / (0.18 * RATE)) * min(1.0, (n - i) / (0.7 * RATE)) for i in range(n)]
    out = []
    for i in range(n):
        t = i / RATE
        v = 0.0
        for f in freqs:
            for h, a in ((1, 1.0), (2, 0.5), (3, 0.33), (4, 0.2), (6, 0.1)):
                v += math.sin(math.tau * f * h * t + 0.3 * math.sin(math.tau * 5.2 * t)) * a
        out.append(v / (len(freqs) * 2.2) * env[i] * vol)
    return out


def drone(f: float, dur: float = 1.8, vol: float = 0.45) -> list[float]:
    n = int(dur * RATE)
    return [(math.sin(math.tau * f * i / RATE) + 0.6 * math.sin(math.tau * f * 1.5 * i / RATE + 1)
             + 0.4 * math.sin(math.tau * f * 2.01 * i / RATE)) / 2.0
            * math.sin(math.pi * i / n) ** 1.5 * vol for i in range(n)]


def noise(dur: float, vol: float = 0.3, curve: float = 6.0, seed: int = 1) -> list[float]:
    rnd = random.Random(seed)
    n = int(dur * RATE)
    env = _env(n, 0.002, 0.0, curve)
    return [(rnd.random() * 2 - 1) * env[i] * vol for i in range(n)]


def seq(*parts: tuple[float, list[float]]) -> list[float]:
    """Mix parts, each starting `offset` seconds in."""
    end = max(int(o * RATE) + len(p) for o, p in parts)
    out = [0.0] * end
    for o, p in parts:
        s = int(o * RATE)
        for i, x in enumerate(p):
            out[s + i] += x
    return out


def _echo(x: list[float], delay: float = 0.23, fb: float = 0.35, taps: int = 3) -> list[float]:
    d = int(delay * RATE)
    out = x + [0.0] * (d * taps)
    for t in range(1, taps + 1):
        g = fb ** t
        for i, v in enumerate(x):
            out[i + d * t] += v * g
    return out


# ── the packs: pack -> event -> samples ──────────────────────────────
N = {"C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.0, "A4": 440.0, "B4": 493.88,
     "C5": 523.25, "D5": 587.33, "E5": 659.25, "G5": 783.99, "A5": 880.0, "C6": 1046.5, "E6": 1318.5,
     "A3": 220.0, "E3": 164.81, "D3": 146.83, "C3": 130.81, "G3": 196.0, "B3": 246.94}


def _arp(notes: list[str], gap: float, mk) -> list[float]:
    return seq(*[(i * gap, mk(N[n])) for i, n in enumerate(notes)])


def build(pack: str) -> dict[str, list[float]]:
    if pack == "gothic":
        return {
            "desktop-login": _echo(seq((0, organ([N["A3"], N["E4"], N["A4"]], 3.2)), (0.1, bell(N["A3"] * 2, 4))), 0.4, 0.3, 2),
            "desktop-logout": seq((0, drone(N["A3"] / 2, 2.2)), (0.2, bell(N["E3"] * 2, 3))),
            "message-new-instant": bell(N["E5"], 1.8, 0.45),
            "message": bell(N["A4"], 1.4, 0.4),
            "dialog-error": seq((0, bell(N["D3"], 2.6, 0.6)), (0.0, drone(N["D3"] / 2, 1.2, 0.4))),
            "dialog-warning": seq((0, bell(N["G3"] * 2, 1.6)), (0.35, bell(N["G3"] * 2 * 0.94, 1.8))),
            "dialog-information": bell(N["C5"], 1.2, 0.35),
            "power-plug": organ([N["A3"], N["E4"]], 0.9, 0.35),
            "power-unplug": organ([N["E3"], N["A3"]], 0.9, 0.35),
            "device-added": bell(N["G4"], 1.0, 0.35),
            "device-removed": bell(N["D4"], 1.0, 0.35),
            "bell": bell(N["A3"], 2.8, 0.55),
            "complete": _arp(["A3", "C4", "E4", "A4"], 0.18, lambda f: bell(f, 1.5, 0.3)),
            "battery-low": seq((0, bell(N["D3"], 2.2, 0.5)), (0.9, bell(N["D3"], 2.2, 0.5))),
            "screen-capture": seq((0, noise(0.08, 0.35)), (0.05, bell(N["E5"], 0.6, 0.2))),
            "audio-volume-change": bell(N["A4"], 0.35, 0.3),
        }
    if pack == "classic":
        sq = lambda f, d=0.12: tone(f, d, "square", 0.22, 0.002, 2.0)
        return {
            "desktop-login": seq(*[(i * 0.16, sq(f, 0.5)) for i, f in enumerate([N["C4"], N["E4"], N["G4"], N["C5"], N["E5"]])]),
            "desktop-logout": seq(*[(i * 0.16, sq(f, 0.45)) for i, f in enumerate([N["E5"], N["C5"], N["G4"], N["C4"]])]),
            "message-new-instant": seq((0, sq(N["E5"])), (0.13, sq(N["A5"], 0.25))),
            "message": sq(N["C5"], 0.2),
            "dialog-error": seq((0, sq(N["C4"], 0.18)), (0.2, sq(N["A3"], 0.45))),
            "dialog-warning": seq((0, sq(N["G4"], 0.15)), (0.18, sq(N["G4"], 0.25))),
            "dialog-information": sq(N["E5"], 0.2),
            "power-plug": seq((0, sq(N["G4"], 0.1)), (0.1, sq(N["C5"], 0.2))),
            "power-unplug": seq((0, sq(N["C5"], 0.1)), (0.1, sq(N["G4"], 0.2))),
            "device-added": seq((0, sq(N["C5"], 0.1)), (0.11, sq(N["G5"], 0.2))),
            "device-removed": seq((0, sq(N["G5"], 0.1)), (0.11, sq(N["C5"], 0.2))),
            "bell": sq(N["A4"], 0.25),
            "complete": _arp(["C5", "E5", "G5", "C6"], 0.09, sq),
            "battery-low": seq(*[(i * 0.25, sq(N["A4"], 0.15)) for i in range(3)]),
            "screen-capture": noise(0.12, 0.3, 8),
            "audio-volume-change": sq(N["A4"], 0.06),
        }
    if pack == "glass":
        gl = lambda f, d=1.0: tone(f, d, "sine", 0.32, 0.01, 4.0)
        return {
            "desktop-login": _echo(seq(*[(i * 0.14, gl(f, 1.6)) for i, f in enumerate([N["C5"], N["E5"], N["G5"], N["C6"]])]), 0.3, 0.3, 2),
            "desktop-logout": seq(*[(i * 0.14, gl(f, 1.2)) for i, f in enumerate([N["C6"], N["G5"], N["E5"], N["C5"]])]),
            "message-new-instant": seq((0, gl(N["E5"], 0.8)), (0.12, gl(N["C6"], 1.0))),
            "message": gl(N["G5"], 0.8),
            "dialog-error": seq((0, gl(N["A4"], 0.5)), (0.15, gl(N["E4"], 0.9))),
            "dialog-warning": seq((0, gl(N["E5"], 0.4)), (0.2, gl(N["E5"], 0.6))),
            "dialog-information": gl(N["C6"], 0.7),
            "power-plug": seq((0, gl(N["E5"], 0.4)), (0.1, gl(N["A5"], 0.7))),
            "power-unplug": seq((0, gl(N["A5"], 0.4)), (0.1, gl(N["E5"], 0.7))),
            "device-added": seq((0, gl(N["G5"], 0.4)), (0.1, gl(N["C6"], 0.7))),
            "device-removed": seq((0, gl(N["C6"], 0.4)), (0.1, gl(N["G5"], 0.7))),
            "bell": gl(N["A5"], 0.9),
            "complete": _arp(["C5", "E5", "G5", "C6"], 0.08, lambda f: gl(f, 0.8)),
            "battery-low": seq((0, gl(N["E4"], 0.6)), (0.4, gl(N["E4"], 0.6))),
            "screen-capture": seq((0, noise(0.06, 0.25)), (0.03, gl(N["C6"], 0.4))),
            "audio-volume-change": gl(N["C6"], 0.12),
        }
    if pack == "modern":
        pg = lambda f, d=0.9: tone(f, d, "tri", 0.3, 0.004, 5.0)
        return {
            "desktop-login": _echo(seq((0, pg(N["G4"], 1.2)), (0.18, pg(N["D5"], 1.2)), (0.36, pg(N["G5"], 1.6))), 0.35, 0.3, 2),
            "desktop-logout": seq((0, pg(N["G5"], 0.8)), (0.18, pg(N["D5"], 1.0))),
            "message-new-instant": seq((0, pg(N["D5"], 0.5)), (0.1, pg(N["A5"], 0.8))),
            "message": pg(N["A5"], 0.6),
            "dialog-error": seq((0, pg(N["E4"], 0.4)), (0.12, pg(N["B3"], 0.7))),
            "dialog-warning": pg(N["D5"], 0.6),
            "dialog-information": pg(N["G5"], 0.5),
            "power-plug": seq((0, pg(N["D5"], 0.3)), (0.08, pg(N["A5"], 0.5))),
            "power-unplug": seq((0, pg(N["A5"], 0.3)), (0.08, pg(N["D5"], 0.5))),
            "device-added": seq((0, pg(N["E5"], 0.3)), (0.08, pg(N["B4"] * 2, 0.5))),
            "device-removed": seq((0, pg(N["B4"] * 2, 0.3)), (0.08, pg(N["E5"], 0.5))),
            "bell": pg(N["E6"], 0.5),
            "complete": _arp(["D5", "G5", "B4"], 0.1, pg),
            "battery-low": seq((0, pg(N["A4"], 0.5)), (0.3, pg(N["A4"], 0.5))),
            "screen-capture": seq((0, noise(0.05, 0.2)), (0.02, pg(N["E6"], 0.25))),
            "audio-volume-change": pg(N["E6"], 0.1),
        }
    if pack == "touch":
        tp = lambda f, d=0.25: tone(f, d, "sine", 0.45, 0.002, 7.0, slide=-f * 0.15)
        return {
            "desktop-login": seq((0, tp(N["C5"], 0.5)), (0.12, tp(N["G5"], 0.5)), (0.24, tp(N["C6"], 0.8))),
            "desktop-logout": seq((0, tp(N["C6"], 0.4)), (0.12, tp(N["G5"], 0.4)), (0.24, tp(N["C5"], 0.6))),
            "message-new-instant": seq((0, tp(N["G5"])), (0.12, tp(N["E6"], 0.4))),
            "message": tp(N["E5"], 0.3),
            "dialog-error": seq((0, tp(N["A4"], 0.2)), (0.12, tp(N["A4"] * 0.75, 0.4))),
            "dialog-warning": seq((0, tp(N["E5"], 0.2)), (0.14, tp(N["E5"], 0.3))),
            "dialog-information": tp(N["A5"]),
            "power-plug": seq((0, tp(N["E5"], 0.15)), (0.08, tp(N["A5"], 0.3))),
            "power-unplug": seq((0, tp(N["A5"], 0.15)), (0.08, tp(N["E5"], 0.3))),
            "device-added": seq((0, tp(N["G5"], 0.15)), (0.08, tp(N["C6"], 0.3))),
            "device-removed": seq((0, tp(N["C6"], 0.15)), (0.08, tp(N["G5"], 0.3))),
            "bell": tp(N["C6"], 0.35),
            "complete": _arp(["C5", "E5", "G5"], 0.08, tp),
            "battery-low": seq((0, tp(N["E5"], 0.3)), (0.3, tp(N["E5"], 0.3))),
            "screen-capture": noise(0.06, 0.3, 9),
            "audio-volume-change": tp(N["E5"], 0.08),
        }
    if pack == "wired":
        bl = lambda f, d=0.06: tone(f, d, "saw", 0.2, 0.001, 2.5)
        glitch = lambda s: seq(*[(i * 0.045, bl(f)) for i, f in enumerate([N["C6"], N["G4"], N["E6"], N["A4"]][: 2 + s % 3])])
        return {
            "desktop-login": seq(*[(i * 0.07, bl(f, 0.09)) for i, f in enumerate([N["A3"], N["E4"], N["A4"], N["C5"], N["E5"], N["A5"], N["E6"]])]),
            "desktop-logout": seq(*[(i * 0.07, bl(f, 0.09)) for i, f in enumerate([N["E6"], N["A5"], N["E5"], N["A4"], N["A3"]])]),
            "message-new-instant": glitch(1), "message": glitch(0),
            "dialog-error": seq((0, tone(N["A3"], 0.3, "square", 0.25, 0.001, 3.0, slide=-60))),
            "dialog-warning": seq((0, bl(N["E5"], 0.08)), (0.12, bl(N["E5"], 0.08))),
            "dialog-information": bl(N["A5"], 0.07),
            "power-plug": bl(N["E5"], 0.1), "power-unplug": bl(N["A4"], 0.1),
            "device-added": seq((0, bl(N["A4"])), (0.07, bl(N["E5"]))),
            "device-removed": seq((0, bl(N["E5"])), (0.07, bl(N["A4"]))),
            "bell": bl(N["C6"], 0.1), "complete": glitch(2),
            "battery-low": seq(*[(i * 0.2, bl(N["A3"], 0.12)) for i in range(3)]),
            "screen-capture": noise(0.1, 0.25, 10), "audio-volume-change": bl(N["E6"], 0.03),
        }
    # soft default
    sf = lambda f, d=0.5: tone(f, d, "sine", 0.3, 0.006, 4.5)
    return {
        "desktop-login": seq((0, sf(N["C5"], 0.9)), (0.15, sf(N["G5"], 1.0))),
        "desktop-logout": seq((0, sf(N["G5"], 0.7)), (0.15, sf(N["C5"], 0.9))),
        "message-new-instant": seq((0, sf(N["E5"])), (0.1, sf(N["A5"], 0.6))),
        "message": sf(N["E5"]), "dialog-error": seq((0, sf(N["A4"], 0.3)), (0.12, sf(N["E4"], 0.6))),
        "dialog-warning": seq((0, sf(N["D5"], 0.25)), (0.15, sf(N["D5"], 0.4))),
        "dialog-information": sf(N["G5"], 0.4),
        "power-plug": seq((0, sf(N["E5"], 0.2)), (0.08, sf(N["A5"], 0.4))),
        "power-unplug": seq((0, sf(N["A5"], 0.2)), (0.08, sf(N["E5"], 0.4))),
        "device-added": seq((0, sf(N["G5"], 0.2)), (0.08, sf(N["C6"], 0.4))),
        "device-removed": seq((0, sf(N["C6"], 0.2)), (0.08, sf(N["G5"], 0.4))),
        "bell": sf(N["A5"], 0.4), "complete": _arp(["C5", "E5", "G5"], 0.09, sf),
        "battery-low": seq((0, sf(N["E5"], 0.4)), (0.3, sf(N["E5"], 0.4))),
        "screen-capture": noise(0.07, 0.25, 8), "audio-volume-change": sf(N["C6"], 0.08),
    }


def _write(path: Path, samples: list[float], gain: float) -> None:
    peak = max((abs(x) for x in samples), default=1.0) or 1.0
    k = min(1.0, 0.9 / peak) * gain
    fade = int(0.01 * RATE)
    n = len(samples)
    frames = bytearray()
    for i, x in enumerate(samples):
        x *= k * min(1.0, i / fade, (n - i) / fade)
        frames += struct.pack("<hh", *(2 * [int(max(-1.0, min(1.0, x)) * 32000)]))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


def install(pack: str, volume: float = 0.7, force: bool = False) -> Path:
    """Writes the sound theme for `pack`; skipped when it is already there."""
    stereo = THEME_DIR / "stereo"
    stamp = THEME_DIR / ".pack"
    want = f"{pack}:{volume:.2f}"
    if not force and stamp.exists() and stamp.read_text() == want and (stereo / "bell.wav").exists():
        return THEME_DIR
    stereo.mkdir(parents=True, exist_ok=True)
    (THEME_DIR / "index.theme").write_text(
        "[Sound Theme]\nName=swayforge\nComment=Generated by swayforge – pack: "
        f"{PACKS[pack]}\nDirectories=stereo\n\n[stereo]\nOutputProfile=stereo\n")
    for ev, samples in build(pack).items():
        _write(stereo / f"{ev}.wav", samples, volume)
    stamp.write_text(want)
    return THEME_DIR


def play(event: str) -> None:
    import shutil
    import subprocess
    f = THEME_DIR / "stereo" / f"{event}.wav"
    if f.exists() and (p := shutil.which("pw-play") or shutil.which("paplay")):
        subprocess.Popen([p, str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
