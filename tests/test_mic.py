"""The microphone level you set is remembered per microphone and put back."""
import unittest
from unittest import mock

from helpers import fresh_home


class Mic(unittest.TestCase):
    def setUp(self):
        fresh_home()
        from swayforge import mic
        self.mic = mic
        self.vol = {"src": 40}

        def pactl(*a, timeout=5):
            if a[0] == "get-default-source":
                return "alsa_input.usb-mic\n"
            if a[0] == "get-source-volume":
                return f"Volume: front-left: 1 /  {self.vol['src']}% / -3 dB\n"
            if a[0] == "set-source-volume":
                self.vol["src"] = int(a[2].rstrip("%"))
            return ""
        self.p = mock.patch.object(mic, "_pactl", pactl)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_remember_and_restore(self):
        m = self.mic
        self.assertFalse(m.restore())                  # nothing remembered yet → leave it alone
        m.set_volume(85)
        self.assertEqual(m.wanted(), 85)
        self.vol["src"] = 30                           # Discord's auto gain / a reboot turned it down
        self.assertTrue(m.restore())
        self.assertEqual(self.vol["src"], 85)
        self.assertFalse(m.restore())                  # already right → nothing to do

    def test_steps_are_clamped_and_remembered(self):
        m = self.mic
        m.set_volume(148)
        m.step(5)
        self.assertEqual((self.vol["src"], m.wanted()), (150, 150))
        m.set_volume(-3)
        self.assertEqual(m.wanted(), 0)

    def test_monitor_sources_are_ignored(self):
        m = self.mic
        m.remember(70, "alsa_output.speakers.monitor")
        self.assertEqual(m.store(), {})


if __name__ == "__main__":
    unittest.main()
