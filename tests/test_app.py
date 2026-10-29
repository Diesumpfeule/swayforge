"""swayforge app server, desktop widgets and the ASCII motion – no display needed."""
import json
import unittest
import urllib.error
import urllib.request

from helpers import fresh_home


class AppServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fresh_home()
        from swayforge.gui import server
        cls.srv, url, cls.state = server.serve()
        cls.base, cls.token = url.split("/#t=")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path, token=True):
        req = urllib.request.Request(self.base + path, headers={"X-Token": self.token} if token else {})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()

    def post_err(self, path, data):
        try:
            return self.post(path, data)
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, (400, 422))
            return {"error": e.code}

    def post(self, path, data, token=True):
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode(), method="POST",
                                     headers={"X-Token": self.token, "Content-Type": "application/json"} if token else
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def test_only_listens_locally(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_api_needs_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/api/state", token=False)
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("/api/set", {"path": "look.radius", "value": 1}, token=False)
        self.assertEqual(e.exception.code, 403)

    def test_static_cannot_escape(self):
        for p in ("/static/../server.py", "/static/..%2fserver.py", "/static/%2e%2e/%2e%2e/settings.py"):
            with self.subTest(path=p):
                try:
                    code, body = self.get(p, token=False)
                except urllib.error.HTTPError as e:
                    code, body = e.code, b""
                self.assertNotEqual(code, 200, p)
                self.assertNotIn(b"ThreadingHTTPServer", body)

    def test_state_and_validation(self):
        code, body = self.get("/api/state")
        self.assertEqual(code, 200)
        self.assertIn("settings", json.loads(body))
        r = self.post("/api/set", {"path": "look.radius", "value": 7})
        self.assertNotIn("error", r)
        self.assertEqual(self.state.s["look"]["radius"], 7)
        r = self.post_err("/api/set", {"path": "look.radius", "value": "drop table"})
        self.assertIn("error", r)
        r = self.post_err("/api/set", {"path": "nope.nothing", "value": 1})
        self.assertIn("error", r)
        self.assertEqual(self.state.s["look"]["radius"], 7)

    def test_maker_round_trip(self):
        r = self.post("/api/do", {"action": "theme_export", "id": "catppuccin-mocha"})
        self.assertIn("[colors]", r["text"])
        r = self.post("/api/do", {"action": "theme_import", "text": r["text"].replace("Catppuccin", "Imported")})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.state.s["theme"]["name"], r["id"])
        bad = self.post("/api/do", {"action": "theme_import", "text": "[colors]\nbase = 'red'"})
        self.assertFalse(bad["ok"])
        r = self.post("/api/do", {"action": "layout_save", "id": "",
                                  "layout": {"label": "Dock", "base": "win11", "position": "left", "left": ["workspaces"]}})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.state.s["bar"]["layout"], "my-dock")
        self.assertTrue(any(l["id"] == "my-dock" for l in r["layouts"]))
        r = self.post("/api/do", {"action": "layout_delete", "id": "my-dock"})
        self.assertEqual(self.state.s["bar"]["layout"], "modern")
        self.assertFalse(self.post("/api/do", {"action": "theme_delete", "id": "nord"})["ok"])

    def test_every_page_answers(self):
        from swayforge.gui import actions
        for name in [n[5:] for n in dir(actions) if n.startswith("page_")]:
            with self.subTest(page=name):
                code, body = self.get(f"/api/page?id={name}")
                self.assertEqual(code, 200)
                json.loads(body)


class Widgets(unittest.TestCase):
    def test_player_line(self):
        from swayforge.widgets import parse_player
        p = parse_player("Playing\tDaft Punk\tOne More Time\t1500000\t320000000\tspotify\n")
        self.assertEqual((p["artist"], p["pos"], p["length"]), ("Daft Punk", 1.5, 320.0))
        self.assertIsNone(parse_player("No players found"))
        self.assertEqual(parse_player("Paused\t\t\tx\t\tmpv")["title"], "(no title)")

    def test_layout_and_size(self):
        from swayforge import settings, widgets
        cfg = dict(settings.DEFAULTS["widgets"], clock="off", player=True, clippy=True, scale=1.5)
        self.assertEqual([k for k, _ in widgets.layout_widgets(cfg)], ["player", "clippy"])
        for clock in widgets.CLOCKS:
            w, h = widgets.size_of("clock", dict(cfg, clock=clock))
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)


class Motion(unittest.TestCase):
    def test_moving_art_keeps_its_size(self):
        from swayforge import anim
        art = ["  /\\  ", " /  \\ ", "/____\\"]
        for motion in anim.MOTIONS:
            sizes = {(len(f), tuple(len(l) for l in f)) for f in (anim.move(art, t / 10, motion) for t in range(200))}
            self.assertEqual(len(sizes), 1, motion)
            if motion != "glint":
                self.assertGreater(len({tuple(anim.move(art, t / 10, motion)) for t in range(200)}), 1, motion)


class Screensaver(unittest.TestCase):
    def test_matrix_speed_is_monotonic(self):
        fresh_home()
        from swayforge import screensaver, settings
        import copy
        delays = []
        for sp in range(1, 11):
            s = copy.deepcopy(settings.DEFAULTS)
            s["power"]["saver_speed"] = sp
            settings.save(s)
            delays.append(screensaver.matrix_speed())
        self.assertEqual(delays, sorted(delays))


if __name__ == "__main__":
    unittest.main()


class FakeCairo:
    """Records nothing, answers everything – enough to run every widget painter without a display."""
    FONT_SLANT_NORMAL = FONT_WEIGHT_NORMAL = FONT_WEIGHT_BOLD = 0

    class ImageSurface:
        @staticmethod
        def create_from_png(path):
            raise OSError("no png in tests")

    class Ctx:
        def text_extents(self, s):
            import types
            return types.SimpleNamespace(x_advance=len(s) * 7.0)

        def __getattr__(self, name):
            return lambda *a, **k: None


class WidgetPainters(unittest.TestCase):
    def test_every_widget_draws(self):
        import sys
        import time
        sys.modules.setdefault("cairo", FakeCairo)
        fresh_home()
        from swayforge import settings, themes, widgets
        t = themes.get("catppuccin-mocha")
        cfg = dict(settings.DEFAULTS["widgets"])
        p = widgets.Painter({"colors": t.colors, "font": "monospace", "radius": 8}, cfg)
        cr, now = FakeCairo.Ctx(), time.localtime()
        for style in widgets.CLOCKS:
            p.cfg = dict(cfg, clock=style)
            p.clock(cr, 300, 150, now, 0.5)
        p.player(cr, 340, 118, {"status": "Playing", "artist": "a", "title": "t", "pos": 1, "length": 3, "player": "x"})
        p.player(cr, 340, 118, None)
        p.sysmon(cr, 280, 120, 0.5, 0.9, None)
        p.clippy(cr, 330, 190, widgets.TIPS[0], 1.0)
        ws = widgets.parse_tree(TREE, "2")
        self.assertEqual(p.workspaces(cr, 560, 128, ws, True).keys(), {"1", "2"})
        p.workspaces(cr, 560, 128, [], False)
        p.calendar(cr, 260, 236, now)
        wx = widgets.parse_weather(WEATHER)
        p.weather(cr, 300, 150, wx)
        p.weather(cr, 300, 150, None)
        for kind in ("sun", "partly", "cloud", "rain", "snow", "storm", "fog"):
            p.wicon(cr, 0, 0, 40, kind)
        net = widgets.NetMeter("/nonexistent")
        net.sample()
        p.network(cr, 300, 120, net.hist)
        p.disks(cr, 300, 132, widgets.disks())
        p.battery(cr, 220, 84, {"percent": 42, "status": "Discharging"})
        p.battery(cr, 220, 84, None)
        p.notes(cr, 260, 190, "line one\nand a much longer second line that has to wrap somewhere")
        p.timer(cr, 220, 120, widgets.Timer())
        for kind in widgets.KINDS:
            self.assertGreater(widgets.size_of(kind, cfg)[0], 0)

    def test_tree_and_weather_parsing(self):
        from swayforge import widgets
        ws = widgets.parse_tree(TREE, "2")
        self.assertEqual([w["name"] for w in ws], ["1", "2"])
        self.assertTrue(ws[1]["focused"])
        self.assertEqual([x["app"] for x in ws[0]["windows"]], ["kitty", "librewolf"])
        self.assertTrue(ws[0]["windows"][1]["floating"])
        wx = widgets.parse_weather(WEATHER)
        self.assertEqual((wx["temp"], wx["place"], len(wx["days"])), (7, "Bern", 1))
        self.assertEqual(widgets.weather_kind(wx["code"]), "partly")
        self.assertIsNone(widgets.parse_weather({}))
        self.assertIn("Z%C3%BCrich", widgets.weather_url("Zürich"))

    def test_timer_phases(self):
        from swayforge import widgets
        t = widgets.Timer()
        t.toggle()
        t.left = 0.01
        import time
        time.sleep(0.02)
        self.assertEqual(t.tick(), "work")
        self.assertEqual(t.phase, "break")


TREE = {"nodes": [
    {"name": "__i3", "nodes": [{"type": "workspace", "name": "__i3_scratch", "nodes": []}]},
    {"name": "DP-1", "nodes": [
        {"type": "workspace", "name": "1", "num": 1, "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
         "nodes": [{"type": "con", "app_id": "kitty", "pid": 5, "rect": {"x": 0, "y": 0, "width": 960, "height": 1080}, "nodes": []}],
         "floating_nodes": [{"type": "floating_con", "app_id": None, "window_properties": {"class": "librewolf"},
                             "pid": 6, "rect": {"x": 100, "y": 100, "width": 800, "height": 600}, "nodes": []}]},
        {"type": "workspace", "name": "2", "num": 2, "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080}, "nodes": []},
    ]}]}

WEATHER = {"current_condition": [{"temp_C": "7", "FeelsLikeC": "4", "weatherDesc": [{"value": "Partly cloudy"}],
                                  "weatherCode": "116"}],
           "nearest_area": [{"areaName": [{"value": "Bern"}]}],
           "weather": [{"date": "2026-10-29", "mintempC": "3", "maxtempC": "11",
                        "hourly": [{"weatherCode": "113"}] * 8}]}


class FetchAnimation(unittest.TestCase):
    def test_generators_fill_the_box(self):
        from swayforge import fetchanim as f
        art = ["  /\\  ", " /  \\ ", "/____\\"]
        for t in (0.0, 0.8, 2.0):
            for rows in (f.donut(t, 40, 18), f.cube(t, 40, 18), f.spin(art, t, 40, 18), f.Fire(40, 18).step()):
                self.assertEqual(len(rows), 18)
                self.assertTrue(all(len(r) == 40 for r in rows))
        front = ["".join(c for c, _ in r).strip() for r in f.spin(art, 0.0, 40, 5)]
        self.assertEqual([x for x in front if x], [a.strip() for a in art])     # t=0: the motif, as is
        self.assertTrue(any(ch != " " for r in f.donut(1.0, 40, 18) for ch, _ in r))

    def test_colours_and_widths(self):
        from swayforge import fetchanim as f
        g = f.ramp("#000000", "#ffffff", 3)
        self.assertEqual(g[0], "\033[38;2;0;0;0m")
        self.assertEqual(f.visible_len(f.render_cells([[("#", 1.0), (" ", 0)]], g)[0]), 2)

    def test_gif_becomes_blocks(self):
        home = fresh_home()
        from swayforge import fetchanim as f
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow missing")
        frames = [Image.new("RGB", (60, 40), (i * 30, 0, 0)) for i in range(3)]
        p = home / "a.gif"
        frames[0].save(p, save_all=True, append_images=frames[1:], duration=100, loop=0)
        out = f.video_frames(str(p), 30, 20)
        self.assertEqual(len(out), 3)
        self.assertEqual(f.visible_len(out[0][0]), 30)
        self.assertEqual(f.video_frames(str(home / "missing.mp4"), 30, 20), [])


class ThemeWallpaperPicture(unittest.TestCase):
    def test_png_in_the_size_shown_and_svg_fallback(self):
        import os
        import stat
        import tempfile
        from pathlib import Path
        fresh_home()
        from swayforge.gui import server
        self.assertIsNone(server.theme_wallpaper_png("<svg/>", 0))
        bindir = Path(tempfile.mkdtemp())
        fake = bindir / "rsvg-convert"                    # stands in for librsvg: writes its arguments
        fake.write_text("#!/bin/sh\nprintf 'PNG %s %s' \"$2\" \"$4\"\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{bindir}:{old}"
        try:
            self.assertEqual(server.theme_wallpaper_png("<svg/>", 1920), b"PNG 1920 1080")
            fake.write_text("#!/bin/sh\nexit 1\n")
            self.assertEqual(server.theme_wallpaper_png("<svg/>", 1920), b"PNG 1920 1080")   # cached
        finally:
            os.environ["PATH"] = old
