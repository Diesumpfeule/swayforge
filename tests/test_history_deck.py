"""Undo for Apply, and cyberdeck mode (never touches your own settings)."""
import copy
import unittest

from helpers import fresh_home, sysinfo


class History(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        from swayforge import history, render, settings, system
        self.h, self.render, self.settings = history, render, settings
        system.detect = lambda: sysinfo()              # no real hardware probing in tests
        render.detect = system.detect

    def apply(self, **change):
        s = self.settings.load()
        for path, v in change.items():
            sec, key = path.split("__")
            s[sec][key] = v
        self.settings.save(s)
        res = self.render.apply(s, live=False)
        self.assertEqual(res.errors, [])
        return s

    def test_undo_goes_back_and_rewrites_configs(self):
        self.apply(theme__name="nord")
        self.apply(theme__name="rust", look__radius=0)
        self.apply(theme__name="rust", look__radius=0)          # same again → no new entry
        es = self.h.entries()
        self.assertEqual(len(es), 2)
        self.assertIn("theme.name: nord → rust", es[0]["summary"])
        res = self.h.undo(live=False)
        self.assertEqual(res.errors, [])
        s = self.settings.load()
        self.assertEqual((s["theme"]["name"], s["look"]["radius"]), ("nord", 4))
        self.assertIn("back to", self.h.entries()[0]["summary"])
        sway = (self.home / ".config/sway/config").read_text()
        from swayforge import themes
        self.assertIn(themes.get("nord").colors["accent"].lower(), sway.lower())

    def test_own_theme_comes_back_as_it_was(self):
        from swayforge import themes
        base = themes.get("nord")
        t = themes.save_custom("Mine", base, dict(base.colors, accent="#123456"))
        self.apply(theme__name=t.id)
        themes.save_custom("Mine", base, dict(base.colors, accent="#abcdef"))
        self.apply(theme__name=t.id, look__radius=9)
        self.h.restore(self.h.entries()[1]["id"], live=False)
        self.assertEqual(themes.get(t.id).colors["accent"], "#123456")

    def test_keeps_only_the_last_versions_and_rejects_bad_ids(self):
        for i in range(self.h.KEEP + 3):
            self.apply(look__gaps_inner=i)
        self.assertEqual(len(self.h.entries()), self.h.KEEP)
        with self.assertRaises(ValueError):
            self.h.restore("../../etc", live=False)


class Cyberdeck(unittest.TestCase):
    def test_off_by_default_and_never_changes_your_settings(self):
        fresh_home()
        from swayforge import cyberdeck, settings
        s = copy.deepcopy(settings.DEFAULTS)
        self.assertFalse(s["cyberdeck"]["enabled"])
        self.assertIs(cyberdeck.effective(s), s)
        s["cyberdeck"].update(enabled=True, touch=True, scale=1.5)
        before = copy.deepcopy(s)
        e = cyberdeck.effective(s)
        self.assertEqual(s, before)
        self.assertEqual((e["bar"]["height"], e["look"]["gaps_outer"], e["bar"]["layout"]), (24, 0, "touch"))
        self.assertFalse(e["look"]["fx_blur"])
        self.assertFalse(e["widgets"]["enabled"])

    def test_renders_with_scale(self):
        home = fresh_home()
        from swayforge import render, settings
        s = copy.deepcopy(settings.DEFAULTS)
        s["cyberdeck"].update(enabled=True, scale=1.5)
        s["display"]["outputs"] = {"Some Panel X": {"scale": 2.0}}
        self.assertEqual(render.render_all(s, si=sysinfo()).errors, [])
        sway = (home / ".config/sway/config").read_text()
        self.assertIn("output * scale 1.5", sway)
        self.assertNotIn("scale 2.0", sway)
        self.assertEqual(s["bar"]["height"], settings.DEFAULTS["bar"]["height"])


if __name__ == "__main__":
    unittest.main()
