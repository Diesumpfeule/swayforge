# swayforge – audit report (2026-10-29)

Proof of concept, written by Claude, no warranty. This report covers what was checked, what was
fixed, what was **actually** tested and what could not be tested in the audit environment.

## 1. Executive summary

swayforge renders Sway/Waybar/Rofi/Mako/GTK/Vesktop configs from Jinja templates, plus three
front-ends (CLI, Textual TUI, local web-view "swayforge app") and a few system helpers (mounts,
updates, backups, screen saver, desktop widgets). The rendering core is solid: all 300+ theme ×
layout combinations render balanced CSS, valid JSON and a complete sway config.

The real risks were in the edges around your data: a typo in `settings.toml` locked every app out,
a wrongly typed hand-edited value crashed config generation, configs and settings were written
non-atomically, and the installer deleted the installed app before copying the new one. These are
fixed and covered by tests. A unit-test suite (25 tests) and a CI workflow were added.

## 2. Confirmed bugs fixed

| # | Severity | Where | Bug (reproduced before the fix) | Fix | Regression test |
|---|---|---|---|---|---|
| 1 | High | `settings.py` `load()` | A syntax error in `settings.toml` raised `SystemExit` – Settings, the app, `apply` and the bar scripts all refused to start, so you could not repair it from inside swayforge. | Broken file is copied once to `settings.toml.broken-DATE`, defaults are used, a message goes to stderr / `LOAD_ERRORS`. | `test_settings.test_broken_file_does_not_lock_you_out` |
| 2 | High | `settings.py` `_merge()` | A hand-edited value of the wrong type (`radius = "round"`) crashed `render_all` with `TypeError: unsupported operand type(s) for -: 'str' and 'int'`. A plain value replacing a whole section did the same. | `_fits()` coerces numbers given as strings and falls back to the default otherwise; sections can't be replaced by scalars. | `test_settings.test_wrong_types_fall_back` |
| 3 | Medium (data loss) | `settings.py` `save()`, `render.py` `Writer` | Settings and every generated config were written in place – a crash, power loss or full disk mid-write left a truncated file. | New `fsutil.atomic_write` (temp file in same dir, fsync, keep mode, `os.replace`). | `test_settings.test_save_is_atomic_and_round_trips`, `test_safety.Atomic` |
| 4 | Medium (broken install) | `install.sh` | `rm -rf $APP/swayforge` ran before the copy – an interrupted or failed copy left no working swayforge. | Copy to `swayforge.new`, `compileall` check, then swap. | `test_safety.Install` (syntax only, see §5) |

Fixed earlier in the same work session (already pushed, listed for completeness):
updater blocked by edited files → stash + backup branch (`ce96078`, covered by
`test_safety.Updater`); Thunar "Open terminal here" / "could not find fallback terminal emulator"
(exo helper with `X-XFCE-Binaries` + `xdg-terminal-exec` shim); Vesktop screen sharing portal config.

## 3. Checked and found OK

- **Backup import** (`tools.import_`): members are filtered (no absolute paths, no `..`, no links)
  and extracted with `filter="data"` – a hostile archive stays inside HOME (`test_hostile_archive_stays_inside_home`).
- **Shell use**: no `shell=True` with user input; the `mounts.py` f-string commands only contain
  `shlex.quote`d values.
- **App server**: listens on 127.0.0.1 only, random token per start, every `/api/` call needs it,
  `/static/` cannot escape its folder, values are validated against the field list (`test_app.AppServer`).

## 4. Remaining known issues / limits

- **Not testable here** (no display, no GTK, no Sway, no root): the GTK desktop widgets, the native
  app window (GTK4 + WebKit), Thunar integration, real screen sharing, mounts and wiping. They were
  only syntax- and import-checked.
- **Textual TUI**: the TUI smoke test (`tests/test_tui.py`) runs only where Textual is installed –
  in CI, not in the audit container (pip was blocked there).
- **HOME with spaces**: the sway config calls `~/.local/bin/swayforge` unquoted in `exec` lines.
  Fedora never creates such a HOME, so this is documented rather than changed.
- **Thumbnail cache** (`~/.cache/swayforge`) is never pruned; grows with the number of wallpapers.
- No dry-run flag for `apply`/`mount`; destructive actions (wipe, reset) do ask for confirmation.

## 5. Tests executed (actual results)

Run in the audit container (Python 3.13, no Textual, no GTK):

```
python3 -m unittest discover -s tests      → Ran 25 tests … OK (1 skipped: textual not installed)
python3 -m compileall -q swayforge tests   → OK
bash -n install.sh extras/*/*.sh           → OK (part of the suite)
```

Also run during the session, outside the suite: headless Chromium (Playwright) render of every app
page with fake `swaymsg/pactl/nmcli/bluetoothctl/ip` – no JavaScript errors; screenshots of all skins.

## 6. Security and data-loss assessment

- No remote surface: the app server is loopback + token.
- Writes to your files are atomic; your own settings are never dropped because of one bad value.
- The updater never discards local changes (stash + backup branch).
- Restore cannot write outside HOME.
- Remaining risk: tools that run `sudo` (packages, mounts, wipe) are only as safe as their confirm
  prompts – they are not covered by automated tests.

## 7. Ranked roadmap

1. **Config history & rollback** – keep the last N rendered config sets, "undo last apply". Small effort, high value.
2. **Health check page** (`swayforge doctor`): portals, pipewire, missing packages, broken settings file. Small–medium.
3. **Dry-run for apply** – show which files would change (diff) before writing. Small.
4. **Local assistant** (Ollama + small model, answers from README/CUSTOMIZING/your settings). Medium; optional package.
5. **Profiles** – export/import named look profiles (theme + layout + widgets). Small.
6. **Accessibility** – larger-text preset, high-contrast theme check in CI. Small.

## 8. Recommended next phase

Config history + `doctor`, then a GTK/Sway test run in a Fedora VM (nested Sway with
`WLR_BACKENDS=headless`) so the widgets and the native window get real automated coverage.
