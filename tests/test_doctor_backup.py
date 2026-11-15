"""Doctor, automatic backups, notification history parsing."""
import copy
import os
import time
import unittest

from helpers import fresh_home, sysinfo


class Doctor(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        from swayforge import doctor, render, settings, system
        system.detect = lambda: sysinfo()
        render.detect = system.detect
        self.doctor, self.render, self.settings = doctor, render, settings

    def test_reports_stale_configs_and_apply_fixes_it(self):
        d = self.doctor
        before = d.check_configs()
        self.assertTrue(any(c.auto == "apply" and c.state == d.WARN for c in before), "nothing applied yet")
        self.settings.save(self.settings.load())
        self.render.apply(live=False)
        after = d.check_configs()
        self.assertTrue(any("match your settings" in c.what for c in after), [c.what for c in after])

    def test_every_check_survives_an_empty_system(self):
        d = self.doctor
        checks = d.run_all()
        self.assertGreater(len(checks), 5)
        self.assertFalse([c for c in checks if c.group == "Doctor"], "a check crashed")
        self.assertEqual(checks, sorted(checks, key=lambda c: {"bad": 0, "warn": 1, "ok": 2}[c.state]))
        self.assertTrue(d.summary(checks))

    def test_broken_settings_are_reported(self):
        from swayforge import paths
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        paths.SETTINGS_FILE.write_text("[look\n")
        self.settings.LOAD_ERRORS.clear()
        self.assertTrue(any(c.state == "bad" for c in self.doctor.check_settings()))
        self.settings.LOAD_ERRORS.clear()


class Backup(unittest.TestCase):
    def test_due_make_and_thinning(self):
        home = fresh_home()
        from swayforge import backup, paths, settings
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        s = copy.deepcopy(settings.DEFAULTS)
        settings.save(s)
        self.assertFalse(backup.due(s), "off by default")
        self.assertIsNone(backup.auto_run(s))
        s["backup"].update(auto=True, keep=3, every_days=7, dir=str(home / "bk"))
        self.assertTrue(backup.due(s))
        first = backup.auto_run(s)
        self.assertTrue(first.is_file())
        self.assertFalse(backup.due(s), "just made one")
        self.assertTrue(backup.due(s, now=time.time() + 8 * 86400))
        for i in range(5):                                  # older ones are thinned out
            f = home / "bk" / f"swayforge-backup-2020010{i}-0000.tar.gz"
            f.write_bytes(b"x")
            os.utime(f, (1000 + i, 1000 + i))
        backup.make(s)
        self.assertEqual(len(list((home / "bk").glob("*.tar.gz"))), 3)
        self.assertEqual(backup.last(s).parent, home / "bk")
        self.assertFalse(list((home / "bk").glob("*.part")))


class Notifications(unittest.TestCase):
    def test_all_mako_formats(self):
        fresh_home()
        from swayforge import tools
        old = '{"type":"aa{sv}","data":[[{"app-name":{"type":"s","data":"Vesktop"},"summary":{"type":"s","data":"Hi"},"body":{"type":"s","data":"there"}}]]}'
        new = '[{"app_name":"Steam","summary":"Download done","body":""}]'
        text = "Notification 3: Battery low\n  App name: upower\n  Body: 10% left\n"
        self.assertEqual(tools.parse_mako_history(old), [{"app": "Vesktop", "summary": "Hi", "body": "there"}])
        self.assertEqual(tools.parse_mako_history(new)[0]["app"], "Steam")
        self.assertEqual(tools.parse_mako_history(text), [{"app": "upower", "summary": "Battery low", "body": "10% left"}])
        self.assertEqual(tools.parse_mako_history(""), [])


if __name__ == "__main__":
    unittest.main()
