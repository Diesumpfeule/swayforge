# Learning projects

Two small Textual apps with only the skeleton written. You do the rest, one tiny step at a time.
Run them from the swayforge folder. Stuck? Read the error message first, then ask.

## themeswitcher.py – pick a theme with a preview

1. **Preview colours.** Theme has `.colors` (a dict like `{"base": "#1e1e2e", "accent": "#89b4fa", …}`). Show a few
   as coloured blocks in the preview. Hint: Textual text accepts `[on #1e1e2e]   [/]`.
2. **Apply on Enter.** Add a handler `on_list_view_selected`. Run `swayforge theme <id>` with
   `subprocess.run([...])`. Show a message with `self.notify("…")`.
3. **Keys.** Add `j`/`k` for down/up (look up `BINDINGS` and `action_…` methods).
4. **Mark the current theme.** Where does swayforge store the active theme? (look in `settings.py`, key `theme.name` or similar)
5. **Shortcut.** Add a sway binding that opens it in a floating terminal.
6. **Bonus:** theme preview for the whole bar (reuse the CI screenshots?), filter box, favourites.

## widgets.py – a board of small widgets

Copy `Clock`, rename it, change what `tick` shows. Ideas, easy to hard:
battery % · uptime · RAM usage · weather text · "next calendar event" · disk space ·
a counter you click · a todo list saved to a file · now playing (playerctl) · network speed.
Each one is a new class plus one `yield` line in `Board.compose`.
