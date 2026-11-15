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


class Tidy(unittest.TestCase):
    def test_numbers_are_clamped_and_bad_texts_fall_back(self):
        home = fresh_home()
        from swayforge import paths, settings
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        paths.SETTINGS_FILE.write_text(
            '[look]\ngaps_inner = 100000\nradius = -3\n[theme]\nfont = "Evil\\"; exec rm -rf ~ #"\n'
            '[power]\nlocation = "$(id)"\n[input]\nkb_layout = "de; exec x"\n[prompt]\nchar = "$(x)"\n')
        s = settings.load()
        d = settings.DEFAULTS
        self.assertEqual((s["look"]["gaps_inner"], s["look"]["radius"]), (40, 0))
        self.assertEqual(s["theme"]["font"], d["theme"]["font"])
        self.assertEqual(s["power"]["location"], d["power"]["location"])
        self.assertEqual(s["input"]["kb_layout"], d["input"]["kb_layout"])
        self.assertEqual(s["prompt"]["char"], d["prompt"]["char"])
        del home

    def test_normal_values_survive(self):
        fresh_home()
        from swayforge import settings
        s = copy.deepcopy(settings.DEFAULTS)
        s["theme"]["font"] = "Terminess Nerd Font"
        s["input"].update(kb_layout="ch,us", kb_variant="de_nodeadkeys", kb_options="grp:alt_shift_toggle,caps:escape")
        s["power"]["location"] = "47.37:8.54"
        s["bar"]["clock_format"] = "%H:%M:%S"
        s["widgets"]["weather_city"] = "Zürich"
        before = copy.deepcopy(s)
        self.assertEqual(settings.tidy(s), before)
