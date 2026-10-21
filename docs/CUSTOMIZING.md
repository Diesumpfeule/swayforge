# Customizing swayforge – "how do I change X again?"

## The one rule

swayforge **generates** config files from `~/.config/swayforge/settings.toml` + the theme +
the layout. Next to every generated file there is a file that **belongs to you** and is loaded
last – put your changes there and they always win.

| What | Your file | Generated file (don't edit) |
|---|---|---|
| Sway (keys, rules, gaps, input …) | `~/.config/sway/custom.conf` | `~/.config/sway/config` |
| Waybar modules / clicks | `~/.config/waybar/config.jsonc` | `~/.config/waybar/swayforge.jsonc` |
| Waybar look | `~/.config/waybar/style.css` | `~/.config/waybar/swayforge.css` |
| Rofi | `~/.config/rofi/config.rasi` | `~/.config/rofi/themes/swayforge.rasi` |
| kitty | `~/.config/kitty/kitty.conf` | `~/.config/kitty/swayforge.conf` |
| Alacritty | `~/.config/alacritty/alacritty.toml` | `~/.config/alacritty/swayforge.toml` |
| zsh | `~/.zshrc` | `~/.local/share/swayforge/generated/zshrc.zsh` |
| Spaceship prompt | `~/.spaceshiprc.zsh` | `~/.local/share/swayforge/generated/spaceship.zsh` |
| GTK apps | `~/.config/gtk-3.0/gtk.css`, `gtk-4.0/gtk.css` | `…/swayforge.css` next to them |

Every other generated file (fastfetch, mako, swaylock, fonts, btop, MangoHud, cava) contains the
line **`swayforge generated`**. Delete that line and the file is yours – swayforge never touches it
again. In the settings app, the **✎** button next to each option opens the right file, and
`System & files` lists all of them.

After editing: press `Ctrl+S` in the settings app or run `swayforge apply`.

## Recipes

**Add a shortcut** → `~/.config/sway/custom.conf`
```
bindsym $mod+p exec keepassxc
```

**Change an existing shortcut** → settings app → *Apps & shortcuts* (or `[keys]` in settings.toml).

**Always open an app on a workspace / floating** → `custom.conf`
```
assign [class="steam"] workspace number 9
for_window [app_id="mpv"] floating enable
```
Tiling only is the default (*Appearance → Tiling only*). Rules in `custom.conf` come later in the
config, so a single `floating enable` there still works for that one app.

**Autostart something** → settings app → *Apps & shortcuts → Autostart*, one command per line.

**Different clock in the bar** → `~/.config/waybar/config.jsonc`
```jsonc
{
  "include": ["~/.config/waybar/swayforge.jsonc"],
  "clock": { "format": "{:%H:%M:%S}", "interval": 1 }
}
```

**Change a bar colour** → `~/.config/waybar/style.css` (below the `@import` line)
```css
#clock { color: #ff8800; }
```

**Your own colour theme** → settings app → *Theme → Edit colours → Save as my theme*.
It's stored as `~/.config/swayforge/themes/<name>.toml`. You can also copy any file from
`swayforge/data/themes/` there and edit it. A theme can carry a style:
```toml
[style]
radius = 0             # square corners
layout = "win98"       # modern | glass | solid | win98 | winxp | dread | win7 | wired | minimal | sidebar
font = "Terminess Nerd Font"
font_size = 13
wallpaper = "crt"      # gradient | plain | crt | gothic | rust | night | wired
ascii = "skull"        # any ASCII art name
boot = "bios"          # bios | ascii | wired | classic | minimal
```

**Your own ASCII art** → put `name.txt` (max ~40 columns) into `~/.config/swayforge/ascii/`.
Pick it under *Theme → ASCII art*. It shows up in fastfetch, the login and the boot screen.

**A different font everywhere** → *Appearance → Font*. Use a Nerd Font so the bar icons work
(`JetBrainsMono Nerd Font`, `Terminess Nerd Font` are installed). More Nerd Fonts:
download from nerdfonts.com into `~/.local/share/fonts/` and run `fc-cache -f`.

**Window borders / title bars** → *Appearance*: border width (0 = none), title bars, close
buttons in GTK apps.

**Wallpaper** → *Theme → Wallpaper*: theme motif, solid colour or any image from
`~/Pictures/Wallpapers` (the drawn theme motifs end up there as `swayforge-<theme>.png`).

**Monitors** → *Displays* (inside Sway). Settings are stored per monitor model, so they survive
plugging into another port.

**Boot screen / login** → *Boot & login*. Boot screen changes need *Install boot screen* again
(rebuilds initramfs). Back to the graphical login: *Back to SDDM*.

**Add an app to the installer** → create `~/.config/swayforge/catalog.toml`:
```toml
[[group]]
id = "mine"
label = "My stuff"

  [[group.items]]
  id = "obs"
  label = "OBS"
  desc = "Streaming"
  default = true
  dnf = ["obs-studio"]
```

**CS2 chat translator** → options (font size, transparency, `--ohne-original` …) in
`~/.config/swayforge/cs2.args`; your own overlay colours: `"theme_locked": true` in
`~/.config/cs2translate.json`; the program itself: `extras/cs2/cs2translate.py`,
then run the installer item again. Settings → *Apps & shortcuts* has position/test/log buttons.

**Feed in an old Sway config** → `swayforge import-sway ~/old-config` – keys, rules and
autostarts land in `custom.conf`, look stays with the theme.

## Where things live

| Path | What |
|---|---|
| `~/.config/swayforge/settings.toml` | all settings (safe to edit by hand) |
| `~/.config/swayforge/profile.toml` | your app selection for `./install.sh --yes` |
| `~/.config/swayforge/themes/` | your themes |
| `~/.config/swayforge/ascii/` | your ASCII art |
| `~/.local/share/swayforge/app/` | the installed copy of swayforge |
| `~/.local/share/swayforge/generated/` | generated helper files, boot/login scripts |
| `~/.local/share/swayforge/backups/` | automatic backups of files swayforge replaced |
| `~/.local/share/swayforge/install.log` | install log |

## Updating swayforge itself

`git pull` in your clone, then `./install.sh` again (or just copy the `swayforge/` folder to
`~/.local/share/swayforge/app/` and run `swayforge apply`).

## Something broke?

- **Sway config invalid** → swayforge checks with `sway -C` before writing and refuses broken
  configs. Your own `custom.conf` can still break things: `sway -C` shows the line.
- **Restore an old file** → *System & files → Automatic backups → Restore selected*.
- **Login screen won't start** → `Ctrl+Alt+F3`, log in,
  `bash ~/.local/share/swayforge/generated/boot/restore-sddm.sh`, reboot.
- **Boot screen looks wrong** → `sudo plymouth-set-default-theme -R bgrt` restores Fedora's.
