"""Discord screen sharing: launcher flags, portal routing, backups – all idempotent."""
import copy
import unittest
from unittest import mock

from helpers import fresh_home, sysinfo

FLATPAK_EXEC = ("/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=discord --file-forwarding "
                "com.discordapp.Discord @@u %U @@")


class Flags(unittest.TestCase):
    def setUp(self):
        fresh_home()
        from swayforge import discordshare
        self.d = discordshare

    def test_rpm_exec(self):
        out = self.d.with_flags("/usr/bin/discord %U")
        self.assertEqual(out, "/usr/bin/discord --enable-features=UseOzonePlatform,WebRTCPipeWireCapturer "
                              "--ozone-platform=wayland %U")

    def test_flatpak_flags_go_after_the_app_id(self):
        out = self.d.with_flags(FLATPAK_EXEC, "com.discordapp.Discord")
        self.assertIn("com.discordapp.Discord --enable-features=UseOzonePlatform,WebRTCPipeWireCapturer "
                      "--ozone-platform=wayland @@u %U @@", out)
        self.assertTrue(out.startswith("/usr/bin/flatpak run --branch=stable"))

    def test_env_prefix_and_existing_features(self):
        out = self.d.with_flags("env FOO=1 BAR=2 /opt/discord/Discord --enable-features=VaapiVideoDecoder --ozone-platform=x11")
        self.assertEqual(out, "env FOO=1 BAR=2 /opt/discord/Discord "
                              "--enable-features=VaapiVideoDecoder,UseOzonePlatform,WebRTCPipeWireCapturer "
                              "--ozone-platform=wayland")

    def test_idempotent_and_quoting(self):
        once = self.d.with_flags('"/home/me/My Apps/Discord" %U')
        self.assertEqual(self.d.with_flags(once), once)
        self.assertTrue(once.startswith('"/home/me/My Apps/Discord" --enable-features='))

    def test_desktop_text_every_exec_line(self):
        src = ("[Desktop Entry]\nName=Discord\nExec=/usr/bin/discord %U\nActions=new;\n\n"
               "[Desktop Action new]\nName=New window\nExec=/usr/bin/discord --new-window\n")
        c = self.d.Client("Discord", "RPM", "discord.desktop", "/usr/bin/discord")
        text = self.d.desktop_text(c, src)
        execs = [l for l in text.splitlines() if l.startswith("Exec=")]
        self.assertEqual(len(execs), 2)
        self.assertTrue(all("--ozone-platform=wayland" in l for l in execs))
        self.assertIn(self.d.MARK, text.splitlines()[0])
        self.assertEqual(self.d.desktop_text(c, text), text)          # running it again changes nothing

    def test_minimal_entry_for_binary_installs(self):
        c = self.d.Client("Discord", "binary", "discord.desktop", "/opt/discord/Discord")
        text = self.d.desktop_text(c, None)
        self.assertIn("Exec=/opt/discord/Discord --enable-features=", text)
        self.assertIn("[Desktop Entry]", text)


class Files(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        from swayforge import discordshare, paths
        self.d, self.paths = discordshare, paths

    def test_portals_conf_create_and_rerun(self):
        f = self.d.portals_conf()
        self.d.write_portals_conf()
        self.assertEqual(f.read_text(), self.d.PORTALS_CONF)
        self.assertIn("already", self.d.write_portals_conf()[0])
        self.assertFalse(self.paths.BACKUP_DIR.exists())

    def test_portals_conf_foreign_file(self):
        f = self.d.portals_conf()
        f.parent.mkdir(parents=True)
        mine = "[preferred]\ndefault=gtk;wlr\norg.freedesktop.impl.portal.ScreenCast=wlr\norg.freedesktop.impl.portal.Screenshot=wlr\n"
        f.write_text(mine)
        self.assertIn("left as it is", self.d.write_portals_conf()[0])
        self.assertEqual(f.read_text(), mine)
        f.write_text("[preferred]\ndefault=gnome\n")
        msg = self.d.write_portals_conf()[0]
        self.assertIn("old version", msg)
        self.assertEqual(f.read_text(), self.d.PORTALS_CONF)
        saved = list(self.paths.BACKUP_DIR.rglob("sway-portals.conf"))
        self.assertEqual([p.read_text() for p in saved], ["[preferred]\ndefault=gnome\n"])

    def test_routes_to_wlr(self):
        self.assertTrue(self.d.routes_to_wlr(self.d.PORTALS_CONF))
        self.assertFalse(self.d.routes_to_wlr("[preferred]\ndefault=wlr\n"))
        self.assertFalse(self.d.routes_to_wlr("[other]\norg.freedesktop.impl.portal.ScreenCast=wlr\n"
                                              "org.freedesktop.impl.portal.Screenshot=wlr\n"))

    def test_rendered_config_exports_session(self):
        from swayforge import render, settings
        res = render.render_all(copy.deepcopy(settings.DEFAULTS), si=sysinfo())
        self.assertEqual(res.errors, [])
        cfg = (self.home / ".config/sway/config").read_text()
        self.assertTrue(self.d.sway_config_ok(cfg))
        self.assertEqual(cfg.count("dbus-update-activation-environment"), 1)
        env = (self.home / ".config/sway/environment").read_text()
        self.assertIn('XDG_SESSION_TYPE="wayland"', env)
        self.assertNotIn("XDG_CURRENT_DESKTOP", (self.home / ".config/environment.d/90-swayforge.conf").read_text())
        self.assertEqual((self.home / ".config/xdg-desktop-portal/sway-portals.conf").read_text(), self.d.PORTALS_CONF)

    def test_launchers_backup_and_rerun(self):
        c = self.d.Client("Discord", "RPM", "discord.desktop", "/usr/bin/discord")
        target = self.d.apps_dir() / "discord.desktop"
        target.parent.mkdir(parents=True)
        target.write_text("[Desktop Entry]\nName=My Discord\nExec=/usr/bin/discord %U\n")
        with mock.patch.object(self.d, "find_clients", return_value=[c]):
            first = self.d.write_launchers()
            again = self.d.write_launchers()
        self.assertIn("old version", first[0])
        self.assertIn("already has the flags", again[0])
        text = target.read_text()
        self.assertIn("Name=My Discord", text)                        # your own entry kept, flags added
        self.assertIn("--ozone-platform=wayland", text)
        self.assertEqual(len(list(self.paths.BACKUP_DIR.rglob("discord.desktop"))), 1)

    def test_flatpak_uses_override(self):
        c = self.d.Client("Vesktop", "Flatpak", "dev.vencord.Vesktop.desktop", "flatpak", "dev.vencord.Vesktop")
        with mock.patch.object(self.d, "find_clients", return_value=[c]), \
                mock.patch.object(self.d, "system_desktop", return_value=None), \
                mock.patch.object(self.d, "flatpak_override", return_value=True) as fo:
            out = self.d.write_launchers()
        fo.assert_called_once_with("dev.vencord.Vesktop")
        self.assertTrue(any("flatpak override set" in l for l in out))

    def test_check_runs_anywhere(self):
        items = self.d.check()
        self.assertTrue(items)
        self.assertTrue(all(isinstance(i.ok, bool) and i.what for i in items))


if __name__ == "__main__":
    unittest.main()
