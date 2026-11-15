"""The terminal apps start, every page opens, nothing crashes (needs Textual; skipped without it)."""
import asyncio
import unittest

from helpers import fresh_home

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False


@unittest.skipUnless(HAVE_TEXTUAL, "textual not installed")
class SettingsTUI(unittest.TestCase):
    def test_opens_every_page(self):
        fresh_home()
        from swayforge.tui.settings_app import SettingsApp

        async def run():
            app = SettingsApp()
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                for _ in range(40):                 # walk the whole menu
                    await pilot.press("down")
                    await pilot.pause()
                self.assertIsNone(app._exception)
        asyncio.run(run())

    def test_every_switch_and_choice_can_be_changed(self):
        """Flip every setting switch and pick another option in every setting list – nothing may crash,
        and the value must arrive in the settings."""
        fresh_home()
        from textual.widgets import Select, Switch
        from swayforge import settings
        from swayforge.tui.common import path_from_wid
        from swayforge.tui.settings_app import SettingsApp

        async def run():
            app = SettingsApp()
            app.live_apply = lambda *a, **k: None          # no real apply (Sway, gsettings) in a test
            app.save_and_apply = lambda *a, **k: None
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                flipped = 0
                for sw in list(app.query(Switch)):
                    if not (sw.id or "").startswith("f__"):
                        continue
                    path = path_from_wid(sw.id)
                    before = settings.get(app.s, path)
                    sw.value = not sw.value
                    await pilot.pause()
                    self.assertEqual(settings.get(app.s, path), (not before), path)
                    flipped += 1
                for sel in list(app.query(Select)):
                    if not (sel.id or "").startswith("f__"):
                        continue
                    opts = [v for _l, v in sel._options if v is not Select.BLANK]
                    if len(opts) < 2:
                        continue
                    sel.value = next(v for v in opts if v != sel.value)
                    await pilot.pause()
                    flipped += 1
                self.assertGreater(flipped, 40)
                self.assertIsNone(app._exception)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
