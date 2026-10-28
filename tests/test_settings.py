"""Settings: old files, wrong types, broken files, atomic saving, the shared form list."""
import copy
import unittest

from helpers import fresh_home


class Settings(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        from swayforge import paths, settings
        self.paths, self.settings = paths, settings
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def test_old_names_are_migrated(self):
        self.paths.SETTINGS_FILE.write_text('[bar]\nstyle = "solid"\nnetwork = true\n[theme]\nname = "onyx"\n')
        s = self.settings.load()
        self.assertEqual(s["bar"]["layout"], "solid")
        self.assertEqual(s["bar"]["network"], "name")
        self.assertEqual(s["theme"]["name"], "noir")

    def test_wrong_types_fall_back(self):
        self.paths.SETTINGS_FILE.write_text('[look]\nradius = "round"\ngaps_inner = "6"\n[bar]\nlayout = 3\nlook = 1\n')
        s = self.settings.load()
        self.assertEqual(s["look"]["radius"], self.settings.DEFAULTS["look"]["radius"])
        self.assertEqual(s["look"]["gaps_inner"], 6)
        self.assertEqual(s["bar"]["layout"], self.settings.DEFAULTS["bar"]["layout"])

    def test_broken_file_does_not_lock_you_out(self):
        self.paths.SETTINGS_FILE.write_text("[look\nradius = 3")
        s1 = self.settings.load()
        s2 = self.settings.load()
        self.assertEqual(s1, s2)
        kept = list(self.paths.CONFIG_DIR.glob("settings.toml.broken-*"))
        self.assertEqual(len(kept), 1, "one copy of the broken file, not one per read")

    def test_save_is_atomic_and_round_trips(self):
        s = copy.deepcopy(self.settings.DEFAULTS)
        s["look"]["radius"] = 9
        self.settings.save(s)
        self.assertEqual(self.settings.load()["look"]["radius"], 9)
        leftovers = [p for p in self.paths.CONFIG_DIR.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_every_form_field_exists(self):
        from swayforge.fields import FIELDS
        for page, fs in FIELDS.items():
            for f in fs:
                if isinstance(f, str):
                    continue
                with self.subTest(field=f.path):
                    v = self.settings.get(self.settings.DEFAULTS, f.path, KeyError)
                    self.assertIsNot(v, KeyError, f"{page}: {f.path} missing in DEFAULTS")
                    if f.kind == "choice":
                        self.assertIn(v, [o for _, o in f.options], f"{f.path}: default not a choice")


if __name__ == "__main__":
    unittest.main()
