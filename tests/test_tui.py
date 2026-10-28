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


if __name__ == "__main__":
    unittest.main()
