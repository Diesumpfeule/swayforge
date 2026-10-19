"""Widget board – a learning project. One small widget at a time.

Run it:   python3 extras/learn/widgets.py

Look at Clock: it is the pattern for every widget you add (see README.md for ideas).
"""
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.widgets import Footer, Header, Static


class Clock(Static):
    """A widget is a class. on_mount runs once; set_interval repeats a function."""

    def on_mount(self) -> None:
        self.border_title = "Clock"
        self.set_interval(1, self.tick)
        self.tick()

    def tick(self) -> None:
        self.update(datetime.now().strftime("%H:%M:%S\n%A %d.%m."))


class Board(App):
    CSS = """
    Grid { grid-size: 3; grid-gutter: 1 2; padding: 1 2; }
    Static { border: round $primary; height: 7; content-align: center middle; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid():
            yield Clock()
            # NEXT: add your widgets here (one line each)
        yield Footer()


if __name__ == "__main__":
    Board().run()
