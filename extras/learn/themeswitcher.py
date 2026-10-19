"""Theme switcher – a learning project.

Run it from the swayforge folder:   python3 extras/learn/themeswitcher.py

What works already: a list of all themes, q quits, the preview box reacts when you move
through the list. Everything else is YOUR job – see the numbered steps in README.md.
"""
import sys
from pathlib import Path

# lets us `import swayforge` when running this file straight from the repo
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from swayforge import themes

THEMES = themes.all_themes()          # dict: theme id -> Theme (has .label, .colors, .dark …)


class ThemeSwitcher(App):
    CSS = """
    ListView { width: 32; }
    #preview { width: 1fr; padding: 1 2; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(*[ListItem(Label(t.label), id=f"t-{t.id}") for t in THEMES.values()])
            yield Static("move through the list", id="preview")
        yield Footer()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        theme_id = event.item.id.removeprefix("t-")
        theme = THEMES[theme_id]
        # STEP 1: show real colours here instead of just the name
        self.query_one("#preview", Static).update(f"{theme.label}\n\n({theme_id})")


if __name__ == "__main__":
    ThemeSwitcher().run()
