"""Privacy guard parsing and the clipboard history (no Flatpak, no Wayland needed)."""
import os
import unittest

from helpers import fresh_home

VESKTOP = """[Application]
name=dev.vencord.Vesktop
runtime=org.freedesktop.Platform/x86_64/24.08

[Context]
shared=network;ipc;
sockets=x11;wayland;pulseaudio;
devices=all;
filesystems=xdg-download;xdg-pictures:ro;xdg-run/pipewire-0;

[Session Bus Policy]
org.kde.StatusNotifierWatcher=talk
"""

ESCAPER = """[Context]
shared=network;
sockets=wayland;
filesystems=host;
[Session Bus Policy]
org.freedesktop.Flatpak=talk
"""

CALC = """[Context]
sockets=wayland;fallback-x11;
"""


class Privacy(unittest.TestCase):
    def test_vesktop(self):
        from swayforge import privacy
        j = privacy.judge_flatpak(privacy.parse_flatpak_permissions(VESKTOP))
        for k in ("network", "camera", "microphone", "devices", "screen", "files"):
            self.assertIn(k, j["perms"], k)
        self.assertNotIn("home", j["perms"])
        self.assertEqual(j["risk"], "high")         # devices=all

    def test_escape_and_low(self):
        from swayforge import privacy
        j = privacy.judge_flatpak(privacy.parse_flatpak_permissions(ESCAPER))
        self.assertIn("escape", j["perms"])
        self.assertIn("system_files", j["perms"])
        self.assertIn("home", j["perms"])
        low = privacy.judge_flatpak(privacy.parse_flatpak_permissions(CALC))
        self.assertEqual(low, {"perms": {}, "risk": "low"})

    def test_portal_answers(self):
        from swayforge import privacy
        txt = "devices\tcamera\tcom.obsproject.Studio\tyes\t0x00\nlocation\tlocation\torg.gnome.Maps\tEXACT\t\n"
        p = privacy.portal_permissions(txt)
        self.assertEqual(p["com.obsproject.Studio"]["camera"], "yes")
        j = privacy.judge_flatpak({}, p["com.obsproject.Studio"])
        self.assertIn("camera", j["perms"])

    def test_ss(self):
        from swayforge import privacy
        out = privacy.parse_ss(
            'tcp ESTAB 0 0 192.168.1.5:50000 140.82.112.4:443 users:(("librewolf",pid=1,fd=3))\n'
            'tcp ESTAB 0 0 192.168.1.5:50001 1.1.1.1:443 users:(("librewolf",pid=1,fd=4))\n'
            'tcp ESTAB 0 0 127.0.0.1:1 127.0.0.1:2 users:(("x",pid=2,fd=4))\n')
        self.assertEqual(out["librewolf"]["connections"], 2)
        self.assertNotIn("x", out)

    def test_revoke_is_argument_safe(self):
        from swayforge import privacy
        self.assertEqual(privacy.revoke_cmd("dev.vencord.Vesktop", "network"),
                         ["flatpak", "override", "--user", "--unshare=network", "dev.vencord.Vesktop"])
        with self.assertRaises(ValueError):
            privacy.revoke_cmd("x; rm -rf ~", "network")
        with self.assertRaises(ValueError):
            privacy.revoke_cmd("dev.x", "everything")

    def test_camera_scan_on_fake_proc(self):
        import tempfile
        from pathlib import Path
        from swayforge import privacy
        r = Path(tempfile.mkdtemp())
        (r / "42/fd").mkdir(parents=True)
        (r / "42/comm").write_text("obs\n")
        os.symlink("/dev/video0", r / "42/fd/7")
        (r / "43/fd").mkdir(parents=True)
        os.symlink("/dev/null", r / "43/fd/1")
        self.assertEqual(privacy.camera_users(str(r)), ["obs"])


class Clipboard(unittest.TestCase):
    def setUp(self):
        fresh_home()
        from swayforge import clipboard
        self.c = clipboard
        self.conf = {"enabled": True, "max_items": 3, "max_age": 60, "images": True, "skip_sensitive": True}

    def test_dedupe_limit_and_pins(self):
        c = self.c
        a = c.store(b"alpha", conf=self.conf, now=1000)
        c.store(b"beta", conf=self.conf, now=1001)
        self.assertEqual(c.store(b"alpha", conf=self.conf, now=1002), a)       # copied again → same entry
        c.pin(c.store(b"pinned", conf=self.conf, now=1003))
        for i, w in enumerate((b"c", b"d", b"e")):
            c.store(w, conf=self.conf, now=1004 + i)
        texts = [i["preview"] for i in c.items()]
        self.assertEqual(texts[0], "pinned")
        self.assertEqual(len(texts), 4)                                          # 3 + the pinned one
        self.assertNotIn("alpha", texts)

    def test_age_and_search(self):
        c = self.c
        c.store(b"old secret", conf=self.conf, now=1000)
        c.store(b"fresh text", conf=self.conf, now=1000 + 59 * 60)
        c.trim(conf=self.conf, now=1000 + 61 * 60)
        self.assertEqual([i["preview"] for i in c.items()], ["fresh text"])
        self.assertEqual(len(c.items("fresh")), 1)
        self.assertEqual(c.items("nothing"), [])

    def test_passwords_and_pause(self):
        c = self.c
        os.environ["CLIPBOARD_STATE"] = "sensitive"
        try:
            self.assertIsNone(c.store(b"hunter2", conf=self.conf))
        finally:
            del os.environ["CLIPBOARD_STATE"]
        c.set_paused(True)
        self.assertIsNone(c.store(b"while paused", conf=self.conf))
        c.set_paused(False)
        self.assertIsNotNone(c.store(b"after", conf=self.conf))

    def test_private_file_and_images(self):
        c = self.c
        png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (640).to_bytes(4, "big") + (480).to_bytes(4, "big") + b"xx"
        c.store(png, "image/png", conf=self.conf)
        self.assertEqual(c.items()[0]["preview"], "[picture 640×480]")
        self.assertEqual(os.stat(c.db_path()).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
