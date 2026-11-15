"""voiceforge (extras/voice): effects and config – no PipeWire needed, numpy only."""
import importlib.util
import os
import tempfile
import unittest

from helpers import ROOT

try:
    import numpy as np
except ImportError:
    np = None


def fresh():
    home = tempfile.mkdtemp()
    os.environ["HOME"] = home
    for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        os.environ.pop(k, None)
    os.environ["XDG_RUNTIME_DIR"] = home
    spec = importlib.util.spec_from_file_location("voiceforge", ROOT / "extras/voice/voiceforge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dominant(x, rate=48000):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(spec) * rate / len(x)


@unittest.skipUnless(np is not None, "numpy missing")
class Voice(unittest.TestCase):
    def setUp(self):
        self.vf = fresh()

    def run_fx(self, effect, freq=220.0, seconds=1.0, **extra):
        vf = self.vf
        fx = vf.Effects(np)
        cfg = dict(vf.DEFAULTS, effect=effect, gate=0.0, **extra)
        t = np.arange(int(seconds * vf.RATE)) / vf.RATE
        x = (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        out = [fx.process(x[i:i + vf.BLOCK], cfg) for i in range(0, len(x), vf.BLOCK)]
        for o in out:
            self.assertLessEqual(float(np.max(np.abs(o))), 1.0)
            self.assertTrue(np.all(np.isfinite(o)))
        return np.concatenate(out)

    def test_every_effect_runs_fast_enough(self):
        import time
        vf = self.vf
        for name in vf.EFFECTS:
            with self.subTest(effect=name):
                self.assertEqual(len(self.run_fx(name, seconds=0.5)), 24000)
                fx, cfg = vf.Effects(np), dict(vf.DEFAULTS, effect=name)
                x = (np.random.default_rng(0).standard_normal(vf.BLOCK) * 0.2).astype(np.float32)
                fx.process(x, cfg)
                t0 = time.perf_counter()
                for _ in range(20):
                    fx.process(x, cfg)
                self.assertLess((time.perf_counter() - t0) / 20, 0.012, "well under the 20 ms block")

    def test_pitch_moves_the_frequency(self):
        self.assertAlmostEqual(dominant(self.run_fx("deep", freq=440.0)[12000:]), 440 * 2 ** (-4 / 12), delta=25)
        self.assertAlmostEqual(dominant(self.run_fx("custom", freq=300.0, pitch=12)[12000:]), 600, delta=30)

    def test_gate_closes_on_hiss(self):
        vf = self.vf
        fx, cfg = vf.Effects(np), dict(vf.DEFAULTS, effect="clean", gate=0.05)
        hiss = (np.random.default_rng(0).standard_normal(vf.BLOCK) * 0.005).astype(np.float32)
        for _ in range(60):
            out = fx.process(hiss, cfg)
        self.assertLess(float(np.max(np.abs(out))), 1e-3)

    def test_config_sounds_keys(self):
        vf = self.vf
        vf.CONF_DIR.mkdir(parents=True)
        vf.CONF.write_text('{"effect": "laser", "pitch": 99, "gain": "x", "sound_volume": 5}')
        c = vf.load()
        self.assertEqual((c["effect"], c["pitch"], c["gain"], c["sound_volume"]), ("clean", 12, 1.0, 1.5))
        vf.set_effect("next")
        self.assertEqual(vf.load()["effect"], "deep")
        self.assertEqual(len(vf.sound_files()), 6)
        self.assertIn("bindsym Mod4+Mod1+1 exec", vf.sway_keys().read_text())

    def test_never_listens_to_itself(self):
        import json
        vf = self.vf
        vf._run = lambda cmd, timeout=10: vf.subprocess.CompletedProcess(cmd, 0, (
            json.dumps([{"name": "voiceforge_mic"}, {"name": "alsa_output.x.monitor"},
                        {"name": "alsa_input.usb", "description": "USB Mic"}])
            if "sources" in cmd else "voiceforge_mic\n"), "")
        self.assertEqual(vf.real_mic(vf.load()), "alsa_input.usb")


if __name__ == "__main__":
    unittest.main()
