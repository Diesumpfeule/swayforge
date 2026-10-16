"""swayforge installer – pick what you want, run it once, done."""
from __future__ import annotations

import subprocess

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (Button, Checkbox, Header, Input, Label, ListItem, ListView, ProgressBar,
                             RichLog, Select, SelectionList, Static, Switch, TabbedContent, TabPane)
from textual.widgets.selection_list import Selection

from .. import ascii as asc
from .. import catalog as cat
from .. import layouts, paths, plan, settings, themes
from ..system import detect, installed_rpms
from ..render import mix
from .common import BASE_CSS, hero_text, swatch, two_tone, use_layout, use_theme


class Nav(Horizontal):
    def __init__(self, back: bool = True, next_label: str = "Next →", next_variant: str = "primary") -> None:
        super().__init__(classes="nav")
        self._back, self._label, self._variant = back, next_label, next_variant

    def compose(self) -> ComposeResult:
        if self._back:
            yield Button("← Back", id="back")
        yield Static(classes="spacer")
        yield Button(self._label, id="next", variant=self._variant)


class Step(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def action_back(self) -> None:
        if len(self.app.screen_stack) > 2:
            self.app.pop_screen()

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self.action_back()

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        self.next()

    def next(self) -> None:  # pragma: no cover
        raise NotImplementedError


# ── 0. Intro animation ───────────────────────────────────────────────
class Splash(Screen):
    """~1.7 s: the forge heats up out of sparks, then the name is forged left to right.
    Any key or click skips it; SWAYFORGE_NO_INTRO=1 turns it off."""
    DURATION = 1.7
    FPS = 30
    CSS = """
    Splash { align: center middle; background: $background; }
    #splash { width: auto; height: auto; }
    #skip { dock: bottom; width: 100%; text-align: center; color: $text-muted; height: 1; margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="splash")
        yield Static("press any key to skip", id="skip")

    def on_mount(self) -> None:
        import random
        app = self.app
        c = themes.get(app.s["theme"]["name"]).with_accent(app.s["theme"]["accent"])
        self.col = {"face": f"bold {c['accent']}", "shade": mix(c["accent"], c["base"], 0.5),
                    "art": c["accent2"], "artshade": mix(c["accent2"], c["base"], 0.55),
                    "hot": f"bold {c['yellow']}", "spark": c["orange"]}
        width = max(40, min(self.app.size.width - 4, 120))
        self.art = asc.art("forge")
        self.word = asc.best_banner("swayforge", width)
        rnd = random.Random(7)
        self.seed = {(r, x): rnd.random() for r, l in enumerate(self.art) for x in range(len(l))}
        self.rnd = rnd
        self.t = 0.0
        self.done = False
        self.timer = self.set_interval(1 / self.FPS, self.tick)
        self.tick()

    def frame(self, t: float):
        from rich.text import Text
        sh = asc.SHADE
        out = Text(no_wrap=True)
        aw = max(map(len, self.art), default=0)
        ww = max(map(len, self.word), default=0)
        width = max(aw, ww)
        # forge motif: each character ignites at its own moment, glowing hot first
        heat = min(t / 0.75, 1.0) * 1.2
        for r, line in enumerate(self.art):
            out.append(" " * ((width - aw) // 2))
            for x, ch in enumerate(line):
                if ch == " ":
                    out.append(" ")
                    continue
                k = self.seed[(r, x)]
                if heat >= k + 0.18:
                    out.append(ch, style=self.col["artshade"] if ch in sh else self.col["art"])
                elif heat >= k:
                    out.append(self.rnd.choice("*+'.`"), style=self.col["hot"])
                else:
                    out.append(" ")
            out.append("\n")
        out.append("\n")
        # the name: revealed left to right with a white-hot edge and sparks behind it
        edge = (t - 0.45) / 0.9 * (ww + 6)
        for line in self.word:
            out.append(" " * ((width - ww) // 2))
            for x, ch in enumerate(line):
                if x < edge - 2:
                    out.append(ch, style=self.col["shade"] if ch in sh else self.col["face"])
                elif x < edge:
                    out.append(ch if ch != " " else " ", style=self.col["hot"])
                elif x < edge + 2 and self.rnd.random() < 0.25:
                    out.append(self.rnd.choice("*'.`"), style=self.col["spark"])
                else:
                    out.append(" ")
            out.append("\n")
        return out

    def tick(self) -> None:
        if self.done:
            return
        self.t += 1 / self.FPS
        self.query_one("#splash", Static).update(self.frame(self.t))
        if self.t >= self.DURATION:
            self.finish()

    def finish(self) -> None:
        if self.done:
            return
        self.done = True
        self.timer.stop()
        self.app.switch_screen(Welcome())

    def on_key(self, event) -> None:
        event.stop()
        self.finish()

    def on_click(self) -> None:
        self.finish()


# ── 1. Welcome ───────────────────────────────────────────────────────
class Welcome(Step):
    def compose(self) -> ComposeResult:
        yield Header()
        si = self.app.si
        ok = "[green]✓[/]"
        warn = "[yellow]![/]"
        lines = [
            f"{ok if si.is_fedora else warn} System: {si.distro}",
            f"{ok if si.amd_gpu else '·'} Graphics: {'AMD' if si.amd_gpu else 'NVIDIA' if si.nvidia_gpu else 'Intel/other'}",
            f"{ok} Device: {'laptop' if si.laptop else 'desktop'}",
            f"{ok if si.bluetooth else '·'} Bluetooth: {'found' if si.bluetooth else 'none'}",
        ]
        if si.nvidia_gpu:
            lines.append(f"{warn} NVIDIA detected: Sway then needs the proprietary driver "
                         "+ --unsupported-gpu. swayforge is tuned for AMD/Intel.")
        if si.is_fedora and si.fedora < 41:
            lines.append(f"{warn} Fedora {si.fedora} is too old – 41 or newer is expected.")
        prof = plan.Profile.load()
        with VerticalScroll(classes="page"):
            yield Static(hero_text(self.app.s["theme"]["name"], self.app.s["theme"]["accent"],
                                   width=max(40, self.app.size.width - 8)), id="w_banner")
            c = themes.get(self.app.s["theme"]["name"]).with_accent(self.app.s["theme"]["accent"])
            yield Static(two_tone(asc.art("forge"), c["accent2"], mix(c["accent2"], c["base"], 0.55)), id="w_art")
            yield Static("Sets up Fedora Sway in one go: apps, drivers, theme, layout, bar, launcher, "
                         "terminal, prompt, boot and login screen. You choose, swayforge does the rest – "
                         "afterwards Super+I lets you change everything.", classes="hint")
            yield Static("\n".join(lines))
            yield Static("[dim]Proof of concept, written by Claude (Anthropic) – no warranty. "
                         "Read the summary before you install.[/]")
            if prof:
                yield Static("")
                yield Static(f"[b]Saved profile found[/b] ({len(prof.selected)} items). "
                             "Use it as is or adjust it on the next pages.", classes="hint")
                yield Button("Load profile", id="use_profile", variant="success")
        yield Nav(back=False, next_label="Let's go →")

    @on(Button.Pressed, "#use_profile")
    def use_profile(self) -> None:
        prof = plan.Profile.load()
        if prof:
            self.app.selected = set(prof.selected)
            self.app.remove = set(prof.remove)
            self.app.update_first = prof.update_first
            self.notify("Profile loaded")
        self.next()

    def next(self) -> None:
        self.app.push_screen(Apps())


# ── 2. Apps ──────────────────────────────────────────────────────────
class AppCheck(Checkbox):
    BUTTON_INNER = "✓"


class Apps(Step):
    BINDINGS = [Binding("pagedown", "group(1)", "Next group"), Binding("pageup", "group(-1)", "Prev group")]

    def compose(self) -> ComposeResult:
        yield Header()
        c, si = self.app.catalog, self.app.si
        yield Static("Choose apps   [dim]Space/click = on/off · ↑↓ or Tab = move · PgUp/PgDn = group · "
                     "RPM first, Flatpak only when there is no RPM[/]", classes="steptitle")
        yield Static("", id="appcount", classes="hint")
        with TabbedContent(id="appgroups"):
            for g in c.groups:
                with TabPane(g.label, id=f"tab-{g.id}"):
                    with VerticalScroll(classes="applist"):
                        for i in g.items:
                            yield self.row(i, si)
        yield Nav()

    def row(self, i, si) -> Horizontal:
        badges = []
        if i.locked:
            badges.append("[b $accent]always[/]")
        if i.flatpak:
            badges.append("[b $warning]Flatpak[/]")
        if not i.applicable(si):
            badges.append("[dim]not detected[/]")
        title = f"[b]{i.label}[/b]" + ("   " + "  ".join(badges) if badges else "")
        box = AppCheck(title, value=i.id in self.app.selected or i.locked, id=f"app__{i.id}",
                       disabled=i.locked, classes="appcheck")
        return Horizontal(box, Static(f"[dim]{i.desc}[/]", classes="appdesc"), classes="approw")

    def on_mount(self) -> None:
        self.count()

    @on(Checkbox.Changed, ".appcheck")
    def count(self, _ev=None) -> None:
        n = sum(1 for cb in self.query(".appcheck").results(Checkbox) if cb.value)
        self.query_one("#appcount", Static).update(f"{n} selected")

    def action_group(self, step: int) -> None:
        tc = self.query_one("#appgroups", TabbedContent)
        ids = [f"tab-{g.id}" for g in self.app.catalog.groups]
        if tc.active in ids:
            tc.active = ids[(ids.index(tc.active) + step) % len(ids)]

    def next(self) -> None:
        self.app.selected = {cb.id[5:] for cb in self.query(".appcheck").results(Checkbox) if cb.value}
        self.app.push_screen(Cleanup())


# ── 3. Clean-up ──────────────────────────────────────────────────────
class Cleanup(Step):
    def compose(self) -> ComposeResult:
        yield Header()
        rem = self.app.catalog.removable
        installed = installed_rpms([r.pkg for r in rem])
        yield Static("Clean-up", classes="steptitle")
        with VerticalScroll(classes="page"):
            yield Horizontal(Vertical(Label("Update the system first", classes="flabel"),
                                      Label("recommended after a fresh install", classes="fhelp"),
                                      classes="flabelbox"),
                             Switch(value=self.app.update_first, id="update_first"), classes="frow")
            present = [r for r in rem if r.pkg in installed]
            if present:
                yield Static("These pre-installed packages aren't needed by your setup "
                             "(sensible ones are pre-selected):", classes="hint")
                yield SelectionList[str](
                    *[Selection(f"[b]{r.pkg}[/b]  [dim]{r.desc}[/]", r.pkg,
                                (r.pkg in self.app.remove) if self.app.remove else r.default)
                      for r in present], id="removelist")
            else:
                yield Static("Nothing unnecessary found – clean!", classes="hint")
        yield Nav()

    def next(self) -> None:
        self.app.update_first = self.query_one("#update_first", Switch).value
        rl = self.query("#removelist")
        self.app.remove = set(rl.first(SelectionList).selected) if rl else set()
        self.app.push_screen(Look())


# ── 4. Look ──────────────────────────────────────────────────────────
class Look(Step):
    def compose(self) -> ComposeResult:
        yield Header()
        s = self.app.s
        all_t = themes.all_themes()
        ids = list(all_t)
        lay_ids = list(layouts.LAYOUTS)
        yield Static("Look & terminal", classes="steptitle")
        with VerticalScroll(classes="page"):
            yield Static("Theme – arrow keys preview it, the installer recolours itself:", classes="hint")
            yield ListView(*[ListItem(Horizontal(Label(f"{t.label:<34}"), Label(swatch(t))), name=tid)
                             for tid, t in all_t.items()],
                           id="themes", initial_index=ids.index(s["theme"]["name"]) if s["theme"]["name"] in ids else 0)
            yield Horizontal(Label("Layout (bar & launcher)", classes="flabel flabelbox"),
                             Select(layouts.choices(), value=layouts.get(s["bar"]["layout"]).id,
                                    allow_blank=False, id="layout"), classes="frow")
            yield Static(layouts.get(s["bar"]["layout"]).preview, id="layout_preview", classes="preview", markup=False)
            yield Horizontal(Label("Terminal", classes="flabel flabelbox"),
                             Select([("kitty", "kitty"), ("Alacritty", "alacritty")],
                                    value=s["general"]["terminal"], allow_blank=False, id="terminal"),
                             classes="frow")
            yield Horizontal(Vertical(Label("Spaceship prompt (zsh)", classes="flabel"),
                                      Label("pretty prompt with Git status, Python venv etc.", classes="fhelp"),
                                      classes="flabelbox"),
                             Switch(value=s["shell"]["spaceship"], id="spaceship"), classes="frow")
            yield Horizontal(Vertical(Label("Keyboard layout", classes="flabel"),
                                      Label("ch = Swiss German, de, us …", classes="fhelp"),
                                      classes="flabelbox"),
                             Input(s["input"]["kb_layout"], id="kb"), classes="frow")
            yield Horizontal(Label("Main modifier", classes="flabel flabelbox"),
                             Select([("Super / Windows", "Mod4"), ("Alt", "Mod1")], value=s["general"]["mod"],
                                    allow_blank=False, id="mod"), classes="frow")
        yield Nav()

    @on(ListView.Highlighted, "#themes")
    def preview(self, ev: ListView.Highlighted) -> None:
        if ev.item and ev.item.name and ev.item.name != self.app.s["theme"]["name"]:
            all_t = themes.all_themes()
            themes.apply_style(self.app.s, all_t[ev.item.name], all_t.get(self.app.s["theme"]["name"]))
            self.app.s["theme"]["name"] = ev.item.name
            use_theme(self.app, ev.item.name, "", self.app.s["bar"]["layout"])
            lay = layouts.get(self.app.s["bar"]["layout"])
            with self.prevent(Select.Changed):
                self.query_one("#layout", Select).value = lay.id
            self.query_one("#layout_preview", Static).update(lay.preview)

    @on(Select.Changed, "#layout")
    def layout_changed(self, ev: Select.Changed) -> None:
        if isinstance(ev.value, str):
            self.app.s["bar"]["layout"] = ev.value
            use_layout(self.app, ev.value)
            self.query_one("#layout_preview", Static).update(layouts.get(ev.value).preview)

    def next(self) -> None:
        s = self.app.s
        s["general"]["terminal"] = self.query_one("#terminal", Select).value
        s["general"]["mod"] = self.query_one("#mod", Select).value
        s["bar"]["layout"] = self.query_one("#layout", Select).value
        s["shell"]["spaceship"] = self.query_one("#spaceship", Switch).value
        s["input"]["kb_layout"] = self.query_one("#kb", Input).value.strip() or "us"
        self.app.push_screen(Summary())


# ── 5. Summary ───────────────────────────────────────────────────────
class Summary(Step):
    def compose(self) -> ComposeResult:
        yield Header()
        app = self.app
        steps = app.build_steps()
        items = app.catalog.resolve(app.selected)
        n_dnf = len({p for i in items for p in i.dnf})
        n_flat = sum(len(i.flatpak) for i in items)
        t = themes.get(app.s["theme"]["name"])
        lay = layouts.get(app.s["bar"]["layout"])
        yield Static("Summary", classes="steptitle")
        with VerticalScroll(classes="page"):
            yield Static(
                f"[b]{len(items)}[/b] items  ·  [b]{n_dnf}[/b] packages  ·  [b]{n_flat}[/b] Flatpaks  ·  "
                f"[b]{len(app.remove)}[/b] to remove\n"
                f"Theme [b]{t.label}[/b]  ·  layout [b]{lay.label}[/b]  ·  terminal "
                f"[b]{app.s['general']['terminal']}[/b]  ·  keyboard [b]{app.s['input']['kb_layout']}[/b]\n")
            yield Static("[b]Steps[/b]\n" + "\n".join(f"  {n + 1:>2}. {st.title}" for n, st in enumerate(steps)))
            yield Static("\nTakes 10–30 minutes depending on your connection. Existing configs are backed up "
                         "automatically. Your selection is saved as a profile, so the next reset runs "
                         "without questions via [b]./install.sh --yes[/b].", classes="hint")
            yield Horizontal(Button("Dry run (only show)", id="dry"), classes="btnrow")
        yield Nav(next_label="Install", next_variant="success")

    @on(Button.Pressed, "#dry")
    def dry(self) -> None:
        self.app.push_screen(Run(dry=True))

    def next(self) -> None:
        self.app.push_screen(Run(dry=False))


# ── 6. Run ───────────────────────────────────────────────────────────
class Run(Screen):
    BINDINGS = [Binding("escape", "maybe_back", "Back", show=False)]

    def __init__(self, dry: bool) -> None:
        super().__init__()
        self.dry = dry
        self.steps = self.app.build_steps()
        self.finished = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(("Dry run – nothing is changed" if self.dry else "Installing …"),
                     id="runtitle", classes="steptitle")
        yield ProgressBar(total=len(self.steps), show_eta=False, id="prog")
        yield Static("", id="current")
        yield RichLog(id="log", wrap=True, markup=True, highlight=False, max_lines=5000)
        with Horizontal(classes="nav", id="donebar"):
            yield Button("← Back", id="back", disabled=not self.dry)
            yield Static(classes="spacer")
            yield Button("Reboot", id="reboot", variant="success", disabled=True)
            yield Button("Quit", id="quit", disabled=True)

    def on_mount(self) -> None:
        self.run_steps()

    @work(exclusive=True)
    async def run_steps(self) -> None:
        log = self.query_one("#log", RichLog)
        prog = self.query_one("#prog", ProgressBar)
        cur = self.query_one("#current", Static)
        failed = 0
        async for ev in plan.execute(self.steps, dry=self.dry):
            if ev.kind == "step":
                cur.update(f"[b]{ev.index + 1}/{len(self.steps)}[/b]  {ev.text}")
                acc = self.app.current_theme.primary
                log.write(f"\n[b {acc}]━━ {ev.text}[/]")
            elif ev.kind == "line":
                txt = ev.text.replace("[", "\\[")
                log.write(f"[dim]{txt}[/]" if ev.text.startswith("$ ") else txt)
            elif ev.kind == "ok":
                prog.advance(1)
                log.write("[green]✓ done[/]")
            elif ev.kind == "fail":
                prog.advance(1)
                failed += 1
                log.write("[red]✗ failed – see above (continuing)[/]")
            elif ev.kind == "done":
                self.finished = True
                if ev.text == "aborted":
                    cur.update("[red b]Aborted.[/] Details in the log: ~/.local/share/swayforge/install.log")
                elif self.dry:
                    cur.update("[b]Dry run finished.[/] This is what the installation would do.")
                else:
                    msg = "[green b]Done![/] " if not failed else f"[yellow b]Done with {failed} warning(s).[/] "
                    cur.update(msg + "Please reboot. Super+I opens the settings, Super+F1 shows all shortcuts.")
        self.query_one("#back", Button).disabled = False
        self.query_one("#quit", Button).disabled = False
        self.query_one("#reboot", Button).disabled = self.dry

    def action_maybe_back(self) -> None:
        if self.finished or self.dry:
            self.app.pop_screen()

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#quit")
    def quit(self) -> None:
        self.app.exit()

    @on(Button.Pressed, "#reboot")
    def reboot(self) -> None:
        self.app.exit()
        subprocess.Popen(["systemctl", "reboot"])


class InstallerApp(App):
    TITLE = "swayforge"
    SUB_TITLE = "Installer"
    CSS = BASE_CSS + """
    .steptitle { text-style: bold; color: $accent; padding: 1 3 0 3; height: auto; }
    #w_hero { height: auto; margin-bottom: 1; }
    #w_banner { width: auto; height: auto; margin: 1 0; }
    #w_art { color: $secondary; width: auto; margin-bottom: 1; }
    TabbedContent { height: 1fr; margin: 0 2; }
    .applist { height: 1fr; border: none; padding: 0 1; }
    .approw { height: auto; padding: 1 1 1 1; margin-bottom: 1; background: $surface;
              border-left: thick $panel; }
    .approw:focus-within { border-left: thick $accent; background: $boost; }
    .appcheck { width: 46; height: auto; border: none; background: transparent; padding: 0; }
    .appcheck:focus { background: transparent; }
    .appcheck > .toggle--button { color: $panel; background: $panel; }
    .appcheck.-on > .toggle--button { color: $background; background: $accent; text-style: bold; }
    .appdesc { width: 1fr; padding: 0 1; }
    #appcount { padding: 0 3; height: 1; }
    #removelist { height: auto; max-height: 20; }
    #themes { height: auto; max-height: 14; border: round $panel; margin-bottom: 1; }
    #themes ListItem { height: 1; padding: 0 1; }
    #themes Horizontal { height: 1; }
    #themes Label { width: auto; }
    .preview { border: round $accent; padding: 1 2; margin-bottom: 1; height: auto; }
    .nav { height: 3; dock: bottom; padding: 0 2; margin-bottom: 1; }
    .nav .spacer { width: 1fr; }
    .nav Button { margin-left: 1; }
    #prog { margin: 1 3 0 3; }
    #current { padding: 1 3; height: auto; }
    #log { height: 1fr; margin: 0 2; border: round $panel; }
    """
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True),
                Binding("ctrl+l", "redraw", "Redraw", priority=True)]

    def action_redraw(self) -> None:
        self.refresh(repaint=True, layout=True)
        self.screen.refresh(repaint=True, layout=True)

    def __init__(self) -> None:
        super().__init__()
        self.si = detect()
        self.catalog = cat.load()
        self.s = settings.load()
        if self.si.laptop and not paths.SETTINGS_FILE.exists():
            self.s["power"]["suspend_after"] = 30
        self.selected = self.catalog.defaults(self.si)
        self.remove: set[str] = set()
        self.update_first = True

    def build_steps(self) -> list[plan.Step]:
        prof = plan.Profile(set(self.selected), set(self.remove), self.update_first)
        return plan.build(prof, self.s, self.si, self.catalog)

    def on_mount(self) -> None:
        use_theme(self, self.s["theme"]["name"], self.s["theme"]["accent"], self.s["bar"]["layout"])
        import os
        self.push_screen(Welcome() if os.environ.get("SWAYFORGE_NO_INTRO") else Splash())


def main() -> None:
    InstallerApp().run()
