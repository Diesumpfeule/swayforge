# CS2 chat translator

Your live translator for the Counter-Strike 2 chat (`cs2_chat_uebersetzer.py`) is bundled here.
It only reads `console.log`, which CS2 writes itself with the launch option `-condebug`, and
shows the translation as a click-through overlay over the game chat. The original German
manual is in [README.original.de.md](README.original.de.md).

## What swayforge does with it

The installer item **Own tools → CS2 chat translator** (on by default):

- installs `python3-tkinter` (for the overlay window)
- copies the program to `~/.local/share/cs2-chat-uebersetzer/`
- puts a watcher in place that **Sway** starts on login: it waits for `cs2`, starts the
  translator (`--verlauf 0`), stops it when the game closes, and doesn't restart it in a loop
  if it crashes
- removes the old GNOME-style autostart from `installieren.sh` (Sway doesn't run those)
- colours the overlay in your **theme** (CT = theme blue, T = theme yellow, all chat = theme
  green, background, text and logo colour) using your Nerd Font – re-done on every theme change

Settings app → **Apps & shortcuts → CS2 chat translator** has buttons for positioning,
a test run, the options file and the log.

## Once per reset

1. Steam → CS2 → *Properties → Launch options*: `-condebug`
   (together with the gaming tip: `gamemoderun mangohud %command% -condebug`)
2. CS2 → *Video*: display mode **Fullscreen windowed**
3. While CS2 runs: `cs2-uebersetzer --verschieben` – drag the overlay over the chat, `Esc`

The overlay position is saved in `~/.config/cs2_chat_uebersetzer.json` and goes into the
swayforge export, so after `./install.sh --restore` you only need step 1.

## Files

| File | What |
|---|---|
| `cs2_chat_uebersetzer.py` | the program (edit it here, then run the installer item again) |
| `install.sh` | used by the swayforge installer |
| `watcher.sh` | becomes `~/.local/bin/swayforge-cs2-watcher` |
| `uninstall.sh` | removes everything again (also copied next to the installed program) |

| Path on the system | What |
|---|---|
| `~/.config/swayforge/cs2.args` | options for auto-start and `cs2-uebersetzer`, e.g. `--schrift 14 --ohne-original` |
| `~/.config/cs2_chat_uebersetzer.json` | overlay position + theme colours (the `"theme"` key is rewritten by swayforge) |
| `~/.cache/cs2_chat_uebersetzer.log` | log – first place to look if nothing shows up |

To keep your own overlay colours, put `"theme_locked": true` into
`~/.config/cs2_chat_uebersetzer.json` – swayforge then leaves the `"theme"` key alone.

## Sway notes

- CS2 runs through XWayland. The overlay is an X11 override-redirect window, which Sway draws
  above fullscreen XWayland games, and clicks pass through to the game.
- `--fenster` (normal window mode) opens floating and sticky.
- Gaming mode doesn't touch the translator.
