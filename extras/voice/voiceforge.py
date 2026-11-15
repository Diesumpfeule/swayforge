#!/usr/bin/env python3
"""voiceforge – voice changer and soundboard for Linux (PipeWire).

Proof of concept, written by Claude (AI) – no warranty, use at your own risk.

How it works
------------
voiceforge adds a virtual microphone called "VoiceForge Microphone". Pick it as the input in
Discord, Vesktop, CS2, OBS … Behind it:

    your microphone ──► effects (pitch, robot, radio, echo, cave …) ──┐
                                                                      ├─► VoiceForge Microphone
    soundboard (any .wav/.ogg/.flac/.mp3 file) ───────────────────────┘

The effects are computed with numpy in small blocks (20 ms), the audio goes in and out through
PipeWire's own tools (pw-record / pw-play), the virtual devices are ordinary PipeWire/Pulse modules
that disappear again on `voiceforge stop`. Nothing is installed system-wide.

Commands
--------
    voiceforge                 terminal app (effects, soundboard, switches)
    voiceforge start | stop    virtual microphone on/off (runs in the background)
    voiceforge status
    voiceforge effect NAME     clean, deep, chipmunk, robot, radio, megaphone, echo, cave, alien,
                               demon, custom  ·  also: next, previous
    voiceforge play N|FILE     soundboard: sound number N (see `list`) or any file
    voiceforge hush            stop all sounds
    voiceforge list            your sounds
    voiceforge keys            write Sway hotkeys (Super+Alt+1…9 sounds, +0 hush, +V next effect)
"""
from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.0.0"
RATE = 48000
BLOCK = 960                          # 20 ms
HOME = Path.home()
CONF_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "voiceforge"
CONF = CONF_DIR / "config.json"
DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share") / "voiceforge"
SOUNDS = DATA / "sounds"
RUN = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/voiceforge-{os.getuid()}") / "voiceforge"
LOG = HOME / ".cache/voiceforge.log"
MIX = "voiceforge_mix"               # internal sink everything is played into
MIC = "voiceforge_mic"               # the virtual microphone apps pick
AUDIO_EXT = (".wav", ".ogg", ".oga", ".flac", ".mp3", ".opus")

EFFECTS: dict[str, str] = {
    "clean": "Your voice, only cleaned up (noise gate)",
    "deep": "Deep voice – four semitones down",
    "chipmunk": "Chipmunk – seven semitones up",
    "robot": "Robot – metallic ring modulation",
    "radio": "Radio / walkie-talkie – thin and a bit crunchy",
    "megaphone": "Megaphone – loud, narrow, distorted",
    "echo": "Echo – your words come back",
    "cave": "Cave – big reverb",
    "alien": "Alien – high and wobbly",
    "demon": "Demon – very deep, distorted, with reverb",
    "custom": "Custom pitch – choose the semitones",
}
DEFAULTS = {
    "effect": "clean", "pitch": 0, "gain": 1.0, "gate": 0.012, "mic": "",
    "hear_sounds": True, "hear_voice": False, "sound_volume": 0.8, "keys": True,
}


# ── config ───────────────────────────────────────────────────────────
def load() -> dict:
    try:
        data = json.loads(CONF.read_text())
    except (OSError, ValueError):
        data = {}
    out = dict(DEFAULTS)
    for k, v in (data.items() if isinstance(data, dict) else []):
        if k not in DEFAULTS:
            continue
        if isinstance(DEFAULTS[k], float) and isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = float(v)
        elif type(v) is type(DEFAULTS[k]):
            out[k] = v
    if out["effect"] not in EFFECTS:
        out["effect"] = "clean"
    out["pitch"] = max(-12, min(12, int(out["pitch"])))
    out["gain"] = max(0.1, min(4.0, float(out["gain"])))
    out["gate"] = max(0.0, min(0.2, float(out["gate"])))
    out["sound_volume"] = max(0.0, min(1.5, float(out["sound_volume"])))
    return out


def save(cfg: dict) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=1))
    tmp.replace(CONF)


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(time.strftime("%F %T ") + msg + "\n")
    except OSError:
        pass


# ── effects (numpy, block by block, with state) ──────────────────────
class Effects:
    """Turns blocks of float32 samples (-1…1, mono, 48 kHz) into processed blocks of the same size."""

    def __init__(self, np) -> None:
        self.np = np
        self.n = 0                                     # samples processed (for oscillators)
        self.env = 0.0                                 # noise-gate envelope
        self.hist = np.zeros(RATE * 2, dtype=np.float32)      # input history (pitch shifter, comb)
        self.out_hist = np.zeros(RATE, dtype=np.float32)      # output history (echo feedback)
        self.phase = 0.0                               # pitch-shifter delay phase
        self.tail = np.zeros(0, dtype=np.float32)      # reverb overlap
        self.ir: dict = {}
        self.fir: dict = {}
        self.rng = np.random.default_rng(7)

    # helpers ----------------------------------------------------------
    def _push(self, buf, x):
        np = self.np
        buf[:-len(x)] = buf[len(x):]
        buf[-len(x):] = x
        return buf

    def gate(self, x, threshold: float):
        np = self.np
        if threshold <= 0:
            return x
        rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
        target = 1.0 if rms > threshold else 0.0
        # open fast (5 ms), close slowly (150 ms) – no choppy word endings
        k = 1 - math.exp(-len(x) / (RATE * (0.005 if target > self.env else 0.15)))
        start = self.env
        self.env += (target - self.env) * k
        return x * np.linspace(start, self.env, len(x), dtype=np.float32)

    def pitch(self, x, semitones: float, window: int = 2048):
        """Real-time pitch shift: two delay-line taps sweeping at the pitch ratio, cross-faded."""
        np = self.np
        if abs(semitones) < 0.01:
            return x
        ratio = 2 ** (semitones / 12)
        n = len(x)
        h = self.hist                                     # already contains x at the end
        rate = 1.0 - ratio                                # how fast the delay changes per sample
        ph = (self.phase + rate * np.arange(1, n + 1)) % window
        self.phase = float(ph[-1])
        out = np.zeros(n, dtype=np.float32)
        end = len(h) - n                                  # index of x[0] in the history
        for off in (0.0, window / 2):
            d = (ph + off) % window + 1.0                 # delay in samples (≥ 1)
            pos = end + np.arange(n) - d
            i = np.floor(pos).astype(np.int64)
            frac = (pos - i).astype(np.float32)
            s = h[i] * (1 - frac) + h[i + 1] * frac
            g = np.sin(np.pi * ((ph + off) % window) / window) ** 2
            out += (s * g).astype(np.float32)
        return out

    def ring(self, x, freq: float):
        np = self.np
        t = (self.n + np.arange(len(x))) / RATE
        return x * np.sin(2 * np.pi * freq * t).astype(np.float32)

    def comb(self, x, delay_s: float, amount: float):
        np = self.np
        d = int(delay_s * RATE)
        end = len(self.hist) - len(x)
        return x + amount * self.hist[end - d:end - d + len(x)]

    def bandpass(self, x, lo: float, hi: float, taps: int = 255):
        """FIR band-pass (windowed sinc), overlap kept in the history buffer."""
        np = self.np
        key = (lo, hi, taps)
        if key not in self.fir:
            t = np.arange(taps) - (taps - 1) / 2
            sinc = lambda f: 2 * f / RATE * np.sinc(2 * f / RATE * t)  # noqa: E731
            k = (sinc(hi) - sinc(lo)) * np.hamming(taps)
            self.fir[key] = k.astype(np.float32)
        k = self.fir[key]
        end = len(self.hist)
        seg = self.hist[end - len(x) - len(k) + 1:end]
        return np.convolve(seg, k, mode="valid").astype(np.float32)

    def echo(self, x, delay_s: float = 0.32, feedback: float = 0.45):
        np = self.np
        d = int(delay_s * RATE)                           # ≥ one block → no feedback inside a block
        oh = self.out_hist
        y = x + feedback * oh[len(oh) - d:len(oh) - d + len(x)]
        self._push(oh, y)
        return y

    def reverb(self, x, seconds: float = 1.6, wet: float = 0.45):
        np = self.np
        if seconds not in self.ir:
            n = int(seconds * RATE)
            decay = np.exp(-6.9 * np.arange(n) / n)       # −60 dB at the end
            ir = self.rng.standard_normal(n) * decay
            ir[:int(0.012 * RATE)] = 0                     # small pre-delay
            ir /= np.sqrt(np.sum(ir ** 2)) * 1.6
            size = 1 << int(math.ceil(math.log2(n + BLOCK)))
            self.ir[seconds] = (np.fft.rfft(ir, size).astype(np.complex64), size, n)
        spec, size, n = self.ir[seconds]
        full = np.fft.irfft(np.fft.rfft(x, size) * spec, size)[:len(x) + n - 1].astype(np.float32)
        if len(self.tail) < len(full):
            self.tail = np.concatenate([self.tail, np.zeros(len(full) - len(self.tail), dtype=np.float32)])
        self.tail[:len(full)] += full
        y = self.tail[:len(x)].copy()
        self.tail = self.tail[len(x):]
        return x * (1 - wet * 0.5) + wet * y

    def drive(self, x, amount: float):
        np = self.np
        return (np.tanh(x * amount) / math.tanh(amount)).astype(np.float32)

    # the chain --------------------------------------------------------
    def process(self, x, cfg: dict):
        np = self.np
        x = (x * float(cfg["gain"])).astype(np.float32)
        x = self.gate(x, float(cfg["gate"]))
        self._push(self.hist, x)
        fx = cfg["effect"]
        if fx == "deep":
            y = self.pitch(x, -4)
        elif fx == "chipmunk":
            y = self.pitch(x, 7)
        elif fx == "custom":
            y = self.pitch(x, float(cfg["pitch"]))
        elif fx == "robot":
            y = self.comb(self.ring(x, 55.0), 0.006, 0.6) * 0.8
        elif fx == "radio":
            y = self.drive(self.bandpass(x, 400, 3000), 3.0) * 0.8
            y += self.rng.standard_normal(len(x)).astype(np.float32) * 0.004
        elif fx == "megaphone":
            y = self.drive(self.bandpass(x, 600, 2500) * 2.5, 6.0) * 0.7
        elif fx == "echo":
            y = self.echo(x)
        elif fx == "cave":
            y = self.reverb(x, 2.4, 0.6)
        elif fx == "alien":
            p = self.pitch(x, 5)
            y = p * 0.6 + self.ring(p, 420.0 + 60 * math.sin(self.n / RATE * 6)) * 0.5
        elif fx == "demon":
            y = self.reverb(self.drive(self.pitch(x, -7) * 1.6, 2.5), 1.4, 0.35)
        else:
            y = x
        if fx != "echo":
            self._push(self.out_hist, y)
        self.n += len(x)
        return np.clip(y, -1.0, 1.0).astype(np.float32)


# ── PipeWire plumbing ────────────────────────────────────────────────
def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def sources() -> list[tuple[str, str]]:
    """Real microphones: [(node name, description)] – no monitors, not our own."""
    r = _run(["pactl", "-f", "json", "list", "sources"])
    try:
        data = json.loads(r.stdout) if r.returncode == 0 else []
    except ValueError:
        data = []
    out = []
    for s in data:
        name = s.get("name", "")
        if name.endswith(".monitor") or name.startswith("voiceforge"):
            continue
        out.append((name, s.get("description") or name))
    return out


def real_mic(cfg: dict) -> str:
    """The microphone to listen to – never our own virtual one (that would feed back)."""
    names = [n for n, _ in sources()]
    if cfg.get("mic") in names:
        return cfg["mic"]
    default = _run(["pactl", "get-default-source"]).stdout.strip()
    if default in names:
        return default
    return names[0] if names else ""


def modules() -> dict:
    try:
        return json.loads((RUN / "modules.json").read_text())
    except (OSError, ValueError):
        return {}


def devices_up() -> bool:
    return MIC in _run(["pactl", "list", "short", "sources"]).stdout


def create_devices() -> None:
    """The internal mix sink and the virtual microphone on top of it."""
    RUN.mkdir(parents=True, exist_ok=True)
    mods = modules()
    if not devices_up():
        a = _run(["pactl", "load-module", "module-null-sink", f"sink_name={MIX}", "rate=48000",
                  'sink_properties=device.description="VoiceForge-Mix (internal)"'])
        b = _run(["pactl", "load-module", "module-remap-source", f"master={MIX}.monitor", f"source_name={MIC}",
                  'source_properties=device.description="VoiceForge Microphone"'])
        mods = {"sink": a.stdout.strip(), "source": b.stdout.strip()}
        (RUN / "modules.json").write_text(json.dumps(mods))
        if a.returncode or b.returncode:
            raise RuntimeError(f"could not create the virtual microphone: {a.stderr.strip()} {b.stderr.strip()}")


def remove_devices() -> None:
    mods = modules()
    for key in ("monitor", "source", "sink"):
        if str(mods.get(key, "")).isdigit():
            _run(["pactl", "unload-module", mods[key]])
    (RUN / "modules.json").unlink(missing_ok=True)


def hear_voice(on: bool) -> None:
    """Listen to your changed voice on your own speakers/headphones (a loopback, ~40 ms)."""
    mods = modules()
    if on and not str(mods.get("monitor", "")).isdigit():
        r = _run(["pactl", "load-module", "module-loopback", f"source={MIC}", "latency_msec=40"])
        if r.returncode == 0:
            mods["monitor"] = r.stdout.strip()
    elif not on and str(mods.get("monitor", "")).isdigit():
        _run(["pactl", "unload-module", mods.pop("monitor")])
    if RUN.is_dir():
        (RUN / "modules.json").write_text(json.dumps(mods))


# ── the engine (background process) ──────────────────────────────────
def engine() -> int:
    """mic → effects → mix sink, until SIGTERM. Follows config changes live."""
    try:
        import numpy as np
    except ImportError:
        print("voiceforge needs numpy:  sudo dnf install python3-numpy")
        return 1
    for tool in ("pw-record", "pw-play", "pactl"):
        if not shutil.which(tool):
            print(f"{tool} is missing:  sudo dnf install pipewire-utils pulseaudio-utils")
            return 1
    stop = {"now": False}

    def bye(*_):
        stop["now"] = True
    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "engine.pid").write_text(str(os.getpid()))
    cfg = load()
    create_devices()
    hear_voice(cfg["hear_voice"])
    fx = Effects(np)
    stamp = CONF.stat().st_mtime if CONF.exists() else 0.0
    log(f"engine started, effect {cfg['effect']}")
    fmt = ["--rate", str(RATE), "--channels", "1", "--format", "s16", "--latency", "20ms"]
    while not stop["now"]:
        mic = real_mic(cfg)
        if not mic:
            log("no microphone found – waiting")
            time.sleep(3)
            continue
        rec = subprocess.Popen(["pw-record", "--target", mic, *fmt, "-"], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
        play = subprocess.Popen(["pw-play", "--target", MIX, *fmt, "-"], stdin=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        log(f"listening to {mic}")
        n = 0
        try:
            while not stop["now"]:
                raw = rec.stdout.read(BLOCK * 2)
                if not raw or len(raw) < 2:
                    break
                x = np.frombuffer(raw[:len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
                y = fx.process(x, cfg)
                play.stdin.write((y * 32767).astype("<i2").tobytes())
                n += 1
                if n % 10 == 0:                                   # 5× a second: new settings?
                    try:
                        m = CONF.stat().st_mtime
                    except OSError:
                        m = stamp
                    if m != stamp:
                        stamp, old = m, cfg
                        cfg = load()
                        if cfg["hear_voice"] != old["hear_voice"]:
                            hear_voice(cfg["hear_voice"])
                        if real_mic(cfg) != mic:
                            break                                 # other microphone → reconnect
        except (BrokenPipeError, OSError) as e:
            log(f"audio pipe: {e}")
        finally:
            for p in (rec, play):
                try:
                    p.kill()
                except OSError:
                    pass
        if not stop["now"]:
            time.sleep(0.5)
    hear_voice(False)
    remove_devices()
    (RUN / "engine.pid").unlink(missing_ok=True)
    log("engine stopped")
    return 0


def engine_pid() -> int | None:
    try:
        pid = int((RUN / "engine.pid").read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def start() -> int:
    if engine_pid():
        print("voiceforge is already running.")
        return 0
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "engine"], stdout=f, stderr=f,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(30):
        if devices_up():
            print("✓ voiceforge runs – choose “VoiceForge Microphone” as input in Discord, CS2, OBS …")
            return 0
        time.sleep(0.2)
    print(f"✗ the virtual microphone didn't appear – see {LOG}")
    return 1


def stop() -> int:
    pid = engine_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not engine_pid():
                break
            time.sleep(0.1)
    hush()
    remove_devices()                       # also cleans up after a crash
    print("voiceforge stopped – the virtual microphone is gone.")
    return 0


# ── soundboard ───────────────────────────────────────────────────────
def sound_files() -> list[Path]:
    ensure_sounds()
    return sorted((p for p in SOUNDS.iterdir() if p.suffix.lower() in AUDIO_EXT), key=lambda p: p.name.lower())


def play(target: str) -> int:
    files = sound_files()
    if target.isdigit():
        i = int(target) - 1
        if not 0 <= i < len(files):
            print(f"no sound number {target} – `voiceforge list` shows them")
            return 1
        f = files[i]
    else:
        f = Path(os.path.expanduser(target))
        if not f.is_file():
            print(f"{f} not found")
            return 1
    cfg = load()
    base = ["pw-play", "--volume", str(cfg["sound_volume"])]
    pids = []
    if engine_pid():                                       # into the virtual microphone
        pids.append(subprocess.Popen([*base, "--target", MIX, str(f)], start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).pid)
    if cfg["hear_sounds"] or not engine_pid():             # and/or to your own speakers
        pids.append(subprocess.Popen([*base, str(f)], start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).pid)
    RUN.mkdir(parents=True, exist_ok=True)
    with open(RUN / "sounds.pids", "a") as fh:
        fh.write("".join(f"{p}\n" for p in pids))
    return 0


def hush() -> int:
    """Stop every sound the soundboard started."""
    try:
        pids = [int(x) for x in (RUN / "sounds.pids").read_text().split()]
    except (OSError, ValueError):
        pids = []
    for pid in pids:
        try:
            if "pw-play" in Path(f"/proc/{pid}/cmdline").read_text(errors="replace"):
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    (RUN / "sounds.pids").unlink(missing_ok=True)
    return 0


def _wav(path: Path, samples) -> None:
    import wave
    import numpy as np
    data = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)


def ensure_sounds() -> None:
    """A few sounds made from scratch on first start – so the soundboard isn't empty."""
    SOUNDS.mkdir(parents=True, exist_ok=True)
    if any(SOUNDS.iterdir()) or (DATA / ".made").exists():
        return
    try:
        import numpy as np
    except ImportError:
        return
    t = lambda s: np.arange(int(s * RATE)) / RATE  # noqa: E731

    def tone(f, s, shape=np.sin):
        x = t(s)
        return shape(2 * np.pi * f * x)
    env = lambda x, a=0.01, r=0.2: x * np.minimum(1, np.arange(len(x)) / (a * RATE)) * np.minimum(1, (len(x) - np.arange(len(x))) / (r * RATE))  # noqa: E731
    horn = sum(np.sign(tone(f, 1.4)) * 0.18 for f in (233, 294, 349))
    _wav(SOUNDS / "01 Air horn.wav", env(horn, 0.02, 0.15))
    notes = [(392, .18), (370, .18), (349, .18), (330, .9)]
    tromb = np.concatenate([env(tone(f, d) * 0.5 + tone(f * 2, d) * 0.2, 0.02, 0.06) for f, d in notes])
    _wav(SOUNDS / "02 Sad trombone.wav", tromb)
    rng = np.random.default_rng(1)
    snare = lambda d: env(rng.standard_normal(int(d * RATE)) * 0.4 * np.exp(-np.arange(int(d * RATE)) / (0.06 * RATE)), 0.001, 0.02)  # noqa: E731
    kick = lambda d: env(np.sin(2 * np.pi * 60 * t(d) * np.exp(-t(d) * 8)) * 0.8, 0.001, 0.05)  # noqa: E731
    gap = lambda d: np.zeros(int(d * RATE))  # noqa: E731
    cymbal = env(rng.standard_normal(int(1.2 * RATE)) * 0.25 * np.exp(-t(1.2) * 3), 0.001, 0.3)
    _wav(SOUNDS / "03 Ba dum tss.wav", np.concatenate([snare(.15), gap(.08), kick(.2), cymbal]))
    _wav(SOUNDS / "04 Beep.wav", env(tone(1000, .35) * 0.4, 0.005, 0.02))
    _wav(SOUNDS / "05 Level up.wav", np.concatenate([env(tone(f, .09) * 0.4, .005, .02) for f in (523, 659, 784)]
                                                    + [env(tone(1046, .4) * 0.4, .005, .25)]))
    _wav(SOUNDS / "06 Wrong.wav", env(np.sign(tone(110, .6)) * 0.25, 0.01, 0.1))
    (DATA / ".made").write_text("")


# ── hotkeys for Sway ─────────────────────────────────────────────────
def sway_keys() -> Path:
    """~/.config/voiceforge/sway.conf – swayforge includes it; others: add `include` to your config."""
    me = shutil.which("voiceforge") or f"{sys.executable} {os.path.abspath(__file__)}"
    lines = ["# voiceforge hotkeys – written by `voiceforge keys`, change them here",
             f"bindsym Mod4+Mod1+0 exec {me} hush",
             f"bindsym Mod4+Mod1+v exec {me} effect next",
             f"bindsym Mod4+Mod1+Shift+v exec {me} effect clean"]
    lines += [f"bindsym Mod4+Mod1+{i} exec {me} play {i}" for i in range(1, 10)]
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    f = CONF_DIR / "sway.conf"
    f.write_text("\n".join(lines) + "\n")
    return f


def set_effect(name: str) -> int:
    cfg = load()
    names = list(EFFECTS)
    if name in ("next", "previous"):
        i = names.index(cfg["effect"]) + (1 if name == "next" else -1)
        name = names[i % len(names)]
    if name in ("off", "none"):
        name = "clean"
    if name not in EFFECTS:
        print("effects: " + ", ".join(EFFECTS))
        return 1
    cfg["effect"] = name
    save(cfg)
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "voiceforge", "-t", "1500", "Voice: " + name, EFFECTS[name]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"effect: {name}")
    return 0


def status() -> int:
    cfg = load()
    pid = engine_pid()
    print(f"voiceforge {VERSION}")
    print(f"  running        : {'yes (pid %d)' % pid if pid else 'no – voiceforge start'}")
    print(f"  virtual mic    : {'VoiceForge Microphone' if devices_up() else '–'}")
    print(f"  listening to   : {real_mic(cfg) or 'no microphone found'}")
    print(f"  effect         : {cfg['effect']}" + (f" ({cfg['pitch']:+d} semitones)" if cfg['effect'] == 'custom' else ""))
    print(f"  sounds         : {len(sound_files())} in {SOUNDS}")
    return 0


# ── terminal app ─────────────────────────────────────────────────────
def tui() -> int:
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static, Switch
    except ImportError:
        print("The terminal app needs Textual:  sudo dnf install python3-textual\n")
        return status()

    def palette() -> dict:
        """swayforge's colours, if it's installed."""
        try:
            p = json.loads((DATA.parent / "swayforge/generated/palette.json").read_text())
            return dict(p.get("colors", {}), dark=p.get("dark", True))
        except (OSError, ValueError):
            return {}

    class VoiceForge(App):
        TITLE = "voiceforge"
        SUB_TITLE = "voice changer & soundboard"
        CSS = """
        Screen { layout: vertical; }
        #cols { height: 1fr; }
        .col { width: 1fr; padding: 0 1; }
        .h { text-style: bold; color: $accent; margin: 1 0 0 0; }
        ListView { height: 1fr; border: round $primary 40%; }
        ListView:focus { border: round $accent; }
        #state { padding: 0 1; height: 3; }
        .row { height: 3; }
        .row Label { width: 22; padding: 1 1 0 0; }
        Button { margin: 0 1 0 0; }
        #btns { height: 3; padding: 0 1; }
        """
        BINDINGS = [Binding("space", "toggle", "start/stop"), Binding("e", "next_fx", "next effect"),
                    Binding("0", "hush", "stop sounds"), Binding("plus", "pitch(1)", "pitch +"),
                    Binding("minus", "pitch(-1)", "pitch −"), Binding("q", "quit", "quit")] + \
                   [Binding(str(i), f"play({i})", show=False) for i in range(1, 10)]

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static("", id="state")
            with Horizontal(id="cols"):
                with Vertical(classes="col"):
                    yield Label("Voice effect  (Enter = use · e = next · +/− pitch for Custom)", classes="h")
                    yield ListView(*[ListItem(Label(f"{k:<10} {v}"), name=k) for k, v in EFFECTS.items()], id="fx")
                with Vertical(classes="col"):
                    yield Label("Soundboard  (1–9 or Enter = play · 0 = stop)", classes="h")
                    yield ListView(id="sb")
            cfg = load()
            with Horizontal(classes="row"):
                yield Label("Hear sounds myself")
                yield Switch(cfg["hear_sounds"], id="hear_sounds")
                yield Label("Hear my changed voice")
                yield Switch(cfg["hear_voice"], id="hear_voice")
            with Horizontal(id="btns"):
                yield Button("Start", id="toggle", variant="primary")
                yield Button("Microphone …", id="mic")
                yield Button("Sounds folder", id="folder")
                yield Button("Sway hotkeys", id="keys")
            yield Footer()

        def on_mount(self) -> None:
            c = palette()
            if c.get("accent"):
                from textual.theme import Theme
                self.register_theme(Theme(name="swayforge", primary=c.get("accent2", c["accent"]), accent=c["accent"],
                                          background=c.get("base"), surface=c.get("mantle"), panel=c.get("surface"),
                                          foreground=c.get("text"), dark=bool(palette().get("dark", True))))
                self.theme = "swayforge"
            self.fill_sounds()
            self.refresh_state()
            self.set_interval(2, self.refresh_state)

        def fill_sounds(self) -> None:
            lv = self.query_one("#sb", ListView)
            lv.clear()
            for i, f in enumerate(sound_files(), 1):
                lv.append(ListItem(Label(f"{i if i < 10 else ' '}  {f.stem}"), name=str(i)))

        def refresh_state(self) -> None:
            cfg = load()
            on = engine_pid() is not None
            fx = cfg["effect"] + (f" {cfg['pitch']:+d}" if cfg["effect"] == "custom" else "")
            self.query_one("#state", Static).update(
                (f"[b green]● ON[/] – pick [b]VoiceForge Microphone[/] as input in Discord/CS2/OBS · effect [b]{fx}[/]"
                 if on else "[b red]● OFF[/] – space or Start creates the virtual microphone")
                + f"\nmicrophone: {real_mic(cfg) or 'none found'}")
            self.query_one("#toggle", Button).label = "Stop" if on else "Start"
            idx = list(EFFECTS).index(cfg["effect"])
            lv = self.query_one("#fx", ListView)
            if lv.index != idx and not lv.has_focus:
                lv.index = idx

        def action_toggle(self) -> None:
            (stop if engine_pid() else start)()
            self.refresh_state()

        def action_next_fx(self) -> None:
            set_effect("next")
            self.refresh_state()

        def action_hush(self) -> None:
            hush()

        def action_play(self, n: int) -> None:
            play(str(n))

        def action_pitch(self, d: int) -> None:
            cfg = load()
            cfg["effect"], cfg["pitch"] = "custom", max(-12, min(12, cfg["pitch"] + d))
            save(cfg)
            self.refresh_state()

        def on_list_view_selected(self, ev: ListView.Selected) -> None:
            if ev.list_view.id == "fx" and ev.item.name:
                set_effect(ev.item.name)
            elif ev.list_view.id == "sb" and ev.item.name:
                play(ev.item.name)
            self.refresh_state()

        def on_switch_changed(self, ev: Switch.Changed) -> None:
            cfg = load()
            cfg[ev.switch.id] = ev.value
            save(cfg)
            if ev.switch.id == "hear_voice" and engine_pid():
                pass                                   # the engine follows the config file

        def on_button_pressed(self, ev: Button.Pressed) -> None:
            bid = ev.button.id
            if bid == "toggle":
                self.action_toggle()
            elif bid == "folder":
                subprocess.Popen(["xdg-open", str(SOUNDS)], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.notify("Put .wav/.ogg/.flac/.mp3 files there – they show up here")
                self.set_timer(3, self.fill_sounds)
            elif bid == "keys":
                f = sway_keys()
                self.notify(f"Written: {f} – Super+Alt+1…9 play, +0 stop, +V next effect. "
                            "swayforge picks it up on the next apply.", timeout=10)
            elif bid == "mic":
                cfg = load()
                names = [n for n, _ in sources()]
                if names:
                    i = (names.index(cfg["mic"]) + 1) % len(names) if cfg["mic"] in names else 0
                    cfg["mic"] = names[i]
                    save(cfg)
                    self.notify("Microphone: " + dict(sources()).get(cfg["mic"], cfg["mic"]))
                self.refresh_state()

    VoiceForge().run()
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        return tui()
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if cmd == "--version":
        print(VERSION)
        return 0
    if cmd == "engine":
        return engine()
    if cmd == "start":
        return start()
    if cmd == "stop":
        return stop()
    if cmd == "status":
        return status()
    if cmd == "effect" and rest:
        return set_effect(rest[0])
    if cmd == "play" and rest:
        return play(rest[0])
    if cmd in ("hush", "stopsounds"):
        return hush()
    if cmd == "list":
        for i, f in enumerate(sound_files(), 1):
            print(f"{i:>3}  {f.stem}")
        print(f"\nAdd your own: {SOUNDS}")
        return 0
    if cmd == "keys":
        print(f"written: {sway_keys()}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
