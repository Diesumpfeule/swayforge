<p align="center">
  <img src="docs/img/banner.svg" alt="swayforge" width="100%">
</p>

<p align="center">
  <b>Fedora Sway</b> · AMD · keyboard-first · 15 themes × 7 layouts · 88 apps · reset-friendly
</p>

Set up Fedora Sway in one go – then tweak everything from a terminal app, like KDE's
System Settings but for Sway. Built for the Fedora Sway Spin on AMD graphics, with a focus on
gaming, IT tools, keyboard-driven use and **frequent resets**.

- **Installer** – pick apps, clean-up, theme and layout, run once, reboot.
- **Settings** (`Super+I`) – theme, layout, appearance, bar, displays, audio, Bluetooth,
  network, keyboard/mouse, terminal & prompt, shortcuts, power, boot & login, files.
- **15 colour themes × 7 layouts** – every theme recolours Sway, Waybar, Rofi, kitty/Alacritty,
  Spaceship, fastfetch, GTK apps, mako, swaylock, btop, cava, MangoHud, the boot screen and the
  login screen. One Nerd Font everywhere.
- **Your tweaks always win** – every generated file has a companion file that belongs to you.

> New here after a while? Read **[docs/CUSTOMIZING.md](docs/CUSTOMIZING.md)** – it's the
> "how do I change X again?" cheat sheet.

## Screenshots

<table>
  <tr>
    <td><img src="docs/img/type-o_modern.png" alt="Type O"><br><sub><b>Type O</b> · Modern islands · bat motif</sub></td>
    <td><img src="docs/img/rust_win98.png" alt="Rust"><br><sub><b>Rust</b> · Classic 98 · rose motif</sub></td>
  </tr>
  <tr>
    <td><img src="docs/img/green-night_win98.png" alt="Green Night"><br><sub><b>Green Night</b> · Classic 98 · moon motif</sub></td>
    <td><img src="docs/img/wired_wired.png" alt="Wired"><br><sub><b>Wired</b> · Wired layout · network motif</sub></td>
  </tr>
  <tr>
    <td><img src="docs/img/phosphor_solid.png" alt="Phosphor"><br><sub><b>Phosphor</b> · Solid bar · CRT motif</sub></td>
    <td><img src="docs/img/catppuccin-mocha_modern.png" alt="Catppuccin Mocha"><br><sub><b>Catppuccin Mocha</b> · Modern islands · forge motif</sub></td>
  </tr>
</table>

<sub>Rendered from the real generated configs (bar, colours, fastfetch art, fonts).</sub>

---

## Install (after every reset)

1. Install the **Fedora Sway Spin**, log in, open a terminal (`Super+Enter`).
2. Get this repo onto the machine:
   ```sh
   git clone https://github.com/Diesumpfeule/swayforge.git && cd swayforge
   ```
3. Run it:
   ```sh
   ./install.sh
   ```

The installer asks for your sudo password once and walks you through
**Apps → Clean-up → Look → Summary → Install**. Reboot when it's done.

### The fast way from the second time on

`Super+I → System & files → Export` saves settings, app selection, your themes, ASCII art,
tweaks and the CS2 translator into one file. After the next reset:

```sh
./install.sh --restore ~/swayforge-backup.tar.gz   # everything back, no questions
./install.sh --yes                                 # just the saved profile, no questions
./install.sh --dry-run                             # only show what would happen
```

Tip: commit your exported backup (or `~/.config/swayforge/`) to a private repo too.

## What you can install

**Bold** = ticked by default · \* = Flatpak (only when there's no maintained RPM).
Everything is optional except the Sway base.

| Group | Apps |
|---|---|
| Desktop | **Sway base**, **Thunar file manager**, **Image & video viewers**, **Terminal tools**, **cava**, SwayFX (effects) |
| Gaming | **Steam**, **GameMode + MangoHud**, **Protontricks**, **ProtonPlus**, **Prism Launcher**, **Heroic Games Launcher**, **Discord**, Vesktop*, Lutris, Bottles, Gamescope, CoreCtrl, RetroArch, ProtonUp-Qt*, Dolphin, PCSX2*, Ruffle*, OpenRGB |
| Browser | **Firefox**, Brave, **LibreWolf**, Chromium, Zen Browser* |
| Dev | **Visual Studio Code**, VSCodium, **Python**, **uv**, Thonny, **Compilers & build tools**, **Podman**, **GitHub CLI + tig**, Node.js, Rust, **tmux**, **Distrobox** |
| IT & Security | **Network tools**, **Wireshark**, **Virtual machines (KVM)**, Tailscale, Remmina, Password audit tools, **KeePassXC**, Pentest basics, Kali container, Ghidra*, WireGuard tools |
| Media | OBS Studio, **VLC**, Kdenlive, Audacity, EasyEffects, LibreOffice, GIMP, Inkscape, Krita, Blender, Spotify*, Obsidian*, Thunderbird, qBittorrent, **yt-dlp**, Syncthing, **7-Zip + unrar** |
| USB & SD | **balenaEtcher**, **Raspberry Pi Imager**, Fedora Media Writer, **GParted** |
| Maker | FreeCAD, KiCad, PrusaSlicer |
| System | RPM Fusion, codecs, AMD video acceleration, firmware updates, Timeshift, Bluetooth, Flathub |
| Boot & login | themed Plymouth boot screen, tuigreet login |
| Own tools | [CS2 chat translator](https://github.com/Diesumpfeule/cs2translate) |

Missing something? Add it to `~/.config/swayforge/catalog.toml` – see
[docs/CUSTOMIZING.md](docs/CUSTOMIZING.md#recipes).

## Packages: Fedora first

1. **Fedora repos** whenever possible
2. **RPM Fusion / COPR / vendor RPM repos** – Steam & Discord (RPM Fusion), Prism Launcher &
   ProtonPlus (COPR), Heroic & balenaEtcher (official RPMs from GitHub), Brave / LibreWolf / VS Code / VSCodium (vendor repos)
3. **Flatpak** only when there's no maintained RPM (Spotify, Obsidian, Zen, Vesktop, PCSX2, Ruffle, Ghidra …) – marked **[Flatpak]**

swayforge also switches dnf to **Enter = yes** (`[Y/n]` instead of `[y/N]`). That applies to
`dnf remove` too – read before pressing Enter.

## Themes

| Theme | Style |
|---|---|
| Catppuccin Mocha / Latte, Dracula, Everforest, Gruvbox, Nord, Rosé Pine, Tokyo Night | classics |
| **Clean** | neutral base for building your own |
| **Rust** | black, sage green, rust orange · Classic 98 layout · autumn-leaves wallpaper |
| **Green Night** | deep green, blue, moon-white · Classic 98 layout · moonlit night wallpaper |
| **Type O** | gothic black & deep green · pointed-arch wallpaper |
| **Phosphor** / **Amber** | green / amber CRT · Terminus font · BIOS wallpaper |
| **Wired** | full-on hacker: black, red, static, network nodes · Wired layout |

Retro themes bring their own style (square corners, retro font, layout). Switch to another theme
and your own values come back. **Make your own:** `Theme → Edit colours → Save as my theme`.

## Layouts

| Layout | Look |
|---|---|
| Modern islands | floating rounded islands at the top |
| Solid bar | one continuous bar at the top |
| **Classic 98** | bottom taskbar, Start button, 3D bevelled buttons, sunken tray (GTK apps too) |
| **Glass 7** | bottom glass taskbar, round start orb, icon-only task buttons |
| **Wired** | text only, `[brackets]`, no icons, seconds ticking, terminal-style launcher |
| Minimal | only workspaces, clock, tray, power |
| Sidebar | vertical icon bar on the left |

Any layout works with any theme. `Super+Shift+L` cycles layouts, `Super+Shift+T` cycles themes.

## ASCII art

A 3D shadow font for banners (settings, installer, boot screen, power menu) and shaded motifs
for fastfetch, the login and the boot screen – faces in the accent colour, shading darker:

```
██████╗   ██╗   ██╗   ██████╗ ██████╗
██╔═══██╗ ██║   ██║ ██╔═════╝ ╚═██╔═╝
██████╔═╝ ██║   ██║ ╚═████╗     ██║
██╔═██║   ██║   ██║   ╚═══██╗   ██║
██║ ╚═██╗ ╚═████╔═╝ ██████╔═╝   ██║
╚═╝   ╚═╝   ╚═══╝   ╚═════╝     ╚═╝
```

Motifs: `forge` · `crt` · `cyberdeck` · `gamepad` · `bat` · `lantern` · `rose` · `moon` ·
`wired` · `skull` · `terminal` · `anvil` – or your own `~/.config/swayforge/ascii/NAME.txt`.

## Keys

| Key | Action |
|---|---|
| `Super+I` | swayforge settings |
| `Super+F1` | show all shortcuts |
| `Super+D` | app launcher (Rofi) |
| `Super+Enter` | terminal |
| `Ctrl+Shift+Esc` | task manager (btop) – also a bar button |
| `Super+Shift+G` | gaming mode on/off – also a bar button |
| `Super+Shift+A` / `Super+Shift+I` | audio / network settings |
| `Super+Escape` | power menu (also the bar's ⏻ button) |
| `Super+V` | clipboard history |
| `Super+Shift+S` | screenshot area and edit · `Print` = area to clipboard |
| `Super+Shift+T` / `Super+Shift+L` | next theme / next layout |
| `Super+Arrows` / `+Shift` | move focus / move window |

**Bar:** click speaker/Bluetooth/network → matching settings page; right-click = mute/advanced;
scroll = volume. Volume and brightness keys show a themed on-screen display.

**Gaming mode:** no gaps or borders, notifications muted, no auto-lock, power profile
"performance". Toggle again to restore everything.

## Boot & login screens

- **Boot screen (Plymouth):** BIOS/POST, ASCII art, Wired, Classic PC or Minimal – in your theme
  colours, font and ASCII art. `Settings → Boot & login → Install boot screen` (rebuilds the
  initramfs, about a minute). Re-run after changing the theme if you want them to match.
- **Login (tuigreet):** keyboard-only text login with your ASCII art, replaces SDDM.
  Emergency: `Ctrl+Alt+F3`, log in, run `bash ~/.local/share/swayforge/generated/boot/restore-sddm.sh`.

## Command line

```
swayforge                     settings app   (--page audio|network|layout|boot|…)
swayforge install             installer      (--yes, --dry-run, --profile FILE)
swayforge apply               regenerate configs + reload
swayforge theme NAME          switch theme   (--list, --next)
swayforge layout NAME         switch layout  (--list, --next)
swayforge boot / login        install boot screen / login screen
swayforge gamemode            toggle gaming mode
swayforge import-sway FILE    take over an existing Sway config
swayforge export [FILE]       back up;  swayforge restore FILE
```

Install log: `~/.local/share/swayforge/install.log`

## Repository layout

```
install.sh                 entry point after a reset
docs/CUSTOMIZING.md        how to change things (start here)
extras/cs2/                CS2 chat translator + watcher (auto-starts with CS2)
swayforge/
  data/catalog.toml        everything the installer can install
  data/themes/*.toml       colour themes
  templates/*.j2           config templates (sway, waybar, rofi, kitty, …)
  render.py                turns settings + theme + layout into config files
  layouts.py               bar/UI layouts
  ascii.py                 block + 3D shadow font, ASCII motifs
scripts/make_banner.py     regenerates docs/img/banner.svg
  boot.py                  Plymouth boot screens + tuigreet login
  tui/                     the installer and settings apps (Textual)
```

## CS2 chat translator

Bundled in `extras/cs2/`. The installer item *Own tools → CS2 chat translator* sets it up: a
watcher started by Sway runs the overlay while CS2 runs, coloured in your theme. Once per reset:
Steam launch option `-condebug`, CS2 display mode *Fullscreen windowed*. Positioning, test run,
options and log: *Settings → Apps & shortcuts*. Details: [extras/cs2/README.md](extras/cs2/README.md).

## Gaming tips

- Steam launch option for performance + FPS overlay: `gamemoderun mangohud %command%`
  (for CS2 add `-condebug` for the chat translator)
  (MangoHud on/off: right Shift+F12).
- Install Proton-GE via **ProtonPlus**, then pick it per game in Steam.
- Turn on FreeSync under Displays; "Allow tearing in games" lowers input lag.

## License

MIT – see [LICENSE](LICENSE).
