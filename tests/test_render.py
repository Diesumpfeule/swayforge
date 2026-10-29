"""Every theme × layout (× transparency) renders valid configs."""
import copy
import json
import re
import unittest

from helpers import fresh_home, sysinfo


def balanced(text: str) -> bool:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r'"[^"\n]*"', "", text)
    depth = 0
    for ch in text:
        depth += ch == "{"
        depth -= ch == "}"
        if depth < 0:
            return False
    return depth == 0


class RenderMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = fresh_home()
        from swayforge import layouts, render, settings, themes
        cls.render, cls.settings, cls.themes, cls.layouts = render, settings, themes, layouts

    def render_combo(self, theme: str, layout: str, ui: float = 1.0, **si):
        s = copy.deepcopy(self.settings.DEFAULTS)
        s["theme"]["name"], s["bar"]["layout"], s["look"]["ui_opacity"] = theme, layout, ui
        res = self.render.render_all(s, si=sysinfo(**si))
        self.assertEqual(res.errors, [], f"{theme}/{layout}")
        cfg = self.home / ".config"
        for f in ("waybar/swayforge.css", "rofi/themes/swayforge.rasi", "gtk-3.0/swayforge.css"):
            t = (cfg / f).read_text()
            self.assertTrue(balanced(t), f"unbalanced braces in {f} ({theme}/{layout}/{ui})")
            self.assertNotIn("{{", t)
            self.assertNotRegex(t, r"(?<![A-Za-z])None(?![A-Za-z])")
        body = "\n".join(l for l in (cfg / "waybar/swayforge.jsonc").read_text().splitlines() if not l.lstrip().startswith("//"))
        json.loads(body)
        sway = (cfg / "sway/config").read_text()
        self.assertIn("swayforge generated", sway)
        self.assertNotIn("None", sway)

    def test_all_themes_all_layouts(self):
        for tid in self.themes.all_themes():
            for lid in self.layouts.LAYOUTS:
                with self.subTest(theme=tid, layout=lid):
                    self.render_combo(tid, lid)

    def test_transparency(self):
        for lid in self.layouts.LAYOUTS:
            with self.subTest(layout=lid):
                self.render_combo("catppuccin-mocha", lid, ui=0.4)

    def test_without_swayfx_and_desktop_pc(self):
        self.render_combo("rust", "win98", swayfx=False, laptop=False, bluetooth=False)

    def test_readable_text_on_accent(self):
        # every theme: text placed on the accent colour must be readable (contrast ≥ 3)
        for tid, t in self.themes.all_themes().items():
            c = dict(t.colors)
            for bg in ("accent", "accent2", "red", "green"):
                fg = self.render.readable(c[bg], "#ffffff", c)
                self.assertGreaterEqual(self.render.contrast(fg, c[bg]), 3.0, f"{tid}: text on {bg}")


class Portal(unittest.TestCase):
    def test_screen_picker_config(self):
        fresh_home()
        from swayforge import render, settings
        render.render_all(copy.deepcopy(settings.DEFAULTS), si=sysinfo())
        from swayforge import paths
        cfg = (paths.XDG_CONFIG / "xdg-desktop-portal-wlr/config").read_text()
        self.assertIn("[screencast]", cfg)
        self.assertIn("chooser_type=", cfg)
        self.assertIn("ScreenCast=wlr", (paths.XDG_CONFIG / "xdg-desktop-portal/sway-portals.conf").read_text())


if __name__ == "__main__":
    unittest.main()


class CustomLayouts(unittest.TestCase):
    def test_sanitize_rejects_junk(self):
        fresh_home()
        from swayforge import layouts
        c = layouts.sanitize({"label": "x\nevil", "base": "nope", "position": "middle", "left": ["cpu", "cpu", "rm -rf"],
                              "right": "cpu", "height": 999, "opacity": "a", "ws_style": "emoji"})
        self.assertEqual((c["base"], c["position"], c["left"], c["right"], c["height"], c["ws_style"]),
                         ("modern", "top", ["cpu"], [], 72, "numbers"))
        self.assertNotIn("\n", c["label"])
        self.assertFalse(layouts.delete_user("../settings"))

    def test_every_base_and_position_renders(self):
        home = fresh_home()
        from swayforge import layouts, render, settings
        for base in layouts.LAYOUTS:
            for pos in layouts.POSITIONS:
                with self.subTest(base=base, pos=pos):
                    lid = layouts.save_user({"label": f"T {base} {pos}", "base": base, "position": pos, "margin": 6,
                                             "left": ["start", "workspaces", "taskbar"], "center": ["clock"],
                                             "right": ["gpu", "battery", "keyboard", "tray", "power"],
                                             "ws_style": "roman", "text_mode": "text", "radius": 8})
                    s = copy.deepcopy(settings.DEFAULTS)
                    s["bar"]["layout"] = lid
                    res = render.render_all(s, si=sysinfo())
                    self.assertEqual(res.errors, [])
                    body = "\n".join(l for l in (home / ".config/waybar/swayforge.jsonc").read_text().splitlines()
                                     if not l.lstrip().startswith("//"))
                    cfg = json.loads(body)
                    self.assertEqual(cfg["position"], pos)
                    self.assertIn("wlr/taskbar", cfg)
                    self.assertIn("custom/start", cfg)
                    css = (home / ".config/waybar/swayforge.css").read_text()
                    self.assertTrue(balanced(css))
                    self.assertIn("your layout", css)
                    layouts.delete_user(lid)

    def test_deleted_layout_falls_back(self):
        fresh_home()
        from swayforge import layouts
        self.assertEqual(layouts.get("my-gone").id, "modern")
        self.assertFalse(layouts.exists("my-gone"))
