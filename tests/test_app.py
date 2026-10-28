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
