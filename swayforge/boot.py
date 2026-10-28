"""Boot screen (Plymouth) and login screen (greetd + tuigreet).

`render_all` calls `prepare()`, which only writes files into
~/.local/share/swayforge/generated/boot/. Applying them needs root and (for the boot
screen) rebuilds the initramfs, so that happens explicitly:

    bash ~/.local/share/swayforge/generated/boot/apply-boot.sh
    bash ~/.local/share/swayforge/generated/boot/apply-login.sh

(the settings app has buttons for both).
"""
from __future__ import annotations

import re
import socket
from html import escape
from typing import TYPE_CHECKING

from . import ascii as asc
from . import paths

if TYPE_CHECKING:
    from .render import Ctx, Writer

BOOT_DIR = paths.GEN_DIR / "boot"

STYLES: dict[str, tuple[str, str]] = {
    "bios": ("BIOS / POST", "Black screen, hardware check lines appear one by one, blinking cursor"),
    "ascii": ("ASCII art", "The theme's ASCII motif + banner, block progress bar"),
    "wired": ("Wired", "Flickering 'connecting' banner, static noise, thin progress line"),
    "classic": ("Classic PC", "Gradient background, banner, sliding loading strip"),
    "minimal": ("Minimal", "Small banner and three pulsing dots"),
}

PREVIEWS = {
    "bios": "SWAYFORGE BIOS v2.0\nCPU .................... OK\nMemory test ............ OK\nDetecting drives ....... OK\nLoading Fedora ......... _",
    "ascii": "      ( theme ASCII motif )\n\n   █▀▀ █ █ █ ▄▀█ █▄█ ...\n\n   [██████████░░░░░░░░░░]",
    "wired": "   ▓▒░ C O N N E C T I N G ░▒▓\n   . :  ..  .   :. . ..  :\n   ───────────────────────",
    "classic": "\n        ███ SWAYFORGE ███\n\n      ┌──────────────────┐\n      │      ▮▮▮         │\n      └──────────────────┘",
    "minimal": "\n            swayforge\n\n              • • •",
}

ANSI_NAMES = {
    "black": (0, 0, 0), "red": (205, 0, 0), "green": (0, 205, 0), "yellow": (205, 205, 0),
    "blue": (0, 0, 238), "magenta": (205, 0, 205), "cyan": (0, 205, 205), "gray": (229, 229, 229),
    "darkgray": (127, 127, 127), "lightred": (255, 0, 0), "lightgreen": (0, 255, 0),
    "lightyellow": (255, 255, 0), "lightblue": (92, 92, 255), "lightmagenta": (255, 0, 255),
    "lightcyan": (0, 255, 255), "white": (255, 255, 255),
}


def ansi_name(color: str) -> str:
    """Nearest named terminal colour (the Linux console only knows these 16)."""
    from .render import rgb
    r, g, b = rgb(color)
    return min(ANSI_NAMES, key=lambda n: (ANSI_NAMES[n][0] - r) ** 2 + (ANSI_NAMES[n][1] - g) ** 2
               + (ANSI_NAMES[n][2] - b) ** 2)


def style_for(ctx: "Ctx") -> str:
    st = ctx.s["boot"]["style"]
    if st in STYLES:
        return st
    return ctx.theme.style.get("boot", "minimal") if ctx.theme.style.get("boot") in STYLES else "minimal"


def banner_text(ctx: "Ctx") -> str:
    t = ctx.s["boot"]["text"].strip() or socket.gethostname().split(".")[0]
    t = re.sub(r"[^A-Za-z0-9 .:_!?/-]", "", t)[:14] or "swayforge"
    return t


# ── SVG helpers ──────────────────────────────────────────────────────
def text_svg(lines: list[str], color: str, size: int, font: str, bg: str | None = None,
             pad: int = 0, opacity: float = 1.0) -> str:
    cw = size * 0.6
    w = int(max((len(l) for l in lines), default=1) * cw + 2 * pad + 2)
    lh = int(size * 1.25)
    h = int(len(lines) * lh + 2 * pad + 2)
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    body = "".join(
        f'<text x="{pad}" y="{pad + (i + 1) * lh - int(size * 0.3)}" xml:space="preserve">{escape(l)}</text>'
        for i, l in enumerate(lines))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">{rect}'
            f'<g font-family="{escape(font)}, monospace" font-size="{size}" fill="{color}" '
            f'fill-opacity="{opacity}">{body}</g></svg>')


def blocks_svg(lines: list[str], face: str, shade: str, size: int) -> str:
    """Block lettering (█ ▀ ▄ ░) drawn as rectangles – no font, no gaps between rows."""
    cw, ch = size * 0.6, size * 1.2
    w = int(max((len(l) for l in lines), default=1) * cw + 2)
    h = int(len(lines) * ch + 2)
    rects = []
    for y, line in enumerate(lines):
        for x, c in enumerate(line):
            part = {"█": (0, 1, face), "▀": (0, 0.5, face), "▄": (0.5, 1, face), "░": (0, 1, shade)}.get(c)
            if part:
                y0, y1, col = part
                rects.append(f'<rect x="{x * cw:.1f}" y="{(y + y0) * ch:.1f}" width="{cw + 0.4:.1f}" '
                             f'height="{(y1 - y0) * ch + 0.4:.1f}" fill="{col}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">{"".join(rects)}</svg>'


def rect_svg(w: int, h: int, fill: str, stroke: str | None = None, sw: int = 0, rx: int = 0,
             opacity: float = 1.0) -> str:
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    o = sw // 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
            f'<rect x="{o}" y="{o}" width="{w - sw}" height="{h - sw}" rx="{rx}" fill="{fill}" '
            f'fill-opacity="{opacity}"{s}/></svg>')


def noise_svg(seed: int, w: int, h: int, color: str) -> str:
    import random
    rnd = random.Random(seed)
    dots = "".join(f'<rect x="{rnd.randrange(w)}" y="{rnd.randrange(h)}" width="{rnd.choice((2, 3, 5))}" '
                   f'height="1" fill-opacity="{rnd.uniform(0.05, 0.4):.2f}"/>' for _ in range(900))
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><g fill="{color}">{dots}</g></svg>'


def rgbf(color: str) -> str:
    from .render import rgb
    return ", ".join(f"{v / 255:.3f}" for v in rgb(color))


# ── Plymouth script ──────────────────────────────────────────────────
SCRIPT_COMMON = r"""
// swayforge boot screen – style: @STYLE@
W = Window.GetWidth(0); H = Window.GetHeight(0);
X = Window.GetX(); Y = Window.GetY();
Window.SetBackgroundTopColor(@TOP@);
Window.SetBackgroundBottomColor(@BOTTOM@);
tick = 0;
prog = 0;
pw_mode = 0;

fun progress_cb(duration, progress) { global.prog = progress; }
Plymouth.SetBootProgressFunction(progress_cb);

// ── password prompt (encrypted disks) ──
pw_image = Image("prompt.png");
bullet_image = Image("bullet.png");
pw_sprite = null;
bullet_sprites = null;
fun password_cb(prompt, bullets) {
    global.pw_mode = 1;
    global.pw_sprite = Sprite(pw_image);
    global.pw_sprite.SetPosition(X + W / 2 - pw_image.GetWidth() / 2, Y + H * 0.66, 100);
    global.bullet_sprites = null;
    bx = X + W / 2 - (bullets * bullet_image.GetWidth() * 1.5) / 2;
    for (i = 0; i < bullets; i++) {
        global.bullet_sprites[i] = Sprite(bullet_image);
        global.bullet_sprites[i].SetPosition(bx + i * bullet_image.GetWidth() * 1.5,
                                             Y + H * 0.66 + pw_image.GetHeight() + 16, 101);
    }
}
Plymouth.SetDisplayPasswordFunction(password_cb);

fun normal_cb() {
    global.pw_mode = 0;
    global.pw_sprite = null;
    global.bullet_sprites = null;
}
Plymouth.SetDisplayNormalFunction(normal_cb);

fun center(img, ypos) {
    spr = Sprite(img);
    spr.SetPosition(X + W / 2 - img.GetWidth() / 2, ypos, 10);
    return spr;
}
"""

SCRIPTS = {
    "bios": r"""
lines = null;
for (i = 0; i < @NLINES@; i++) {
    lines[i].image = Image("line" + i + ".png");
    lines[i].sprite = Sprite(lines[i].image);
    lines[i].sprite.SetPosition(X + W * 0.06, Y + H * 0.08 + i * lines[i].image.GetHeight() * 1.6, 10);
    lines[i].sprite.SetOpacity(0);
}
cursor_image = Image("cursor.png");
cursor = Sprite(cursor_image);
logo_image = Image("banner.png");
logo = Sprite(logo_image);
logo.SetPosition(X + W * 0.94 - logo_image.GetWidth(), Y + H * 0.08, 5);
logo.SetOpacity(0.85);

fun refresh_cb() {
    global.tick++;
    shown = Math.Int(global.tick / 22);
    if (shown > @NLINES@) { shown = @NLINES@; }
    for (i = 0; i < shown; i++) { lines[i].sprite.SetOpacity(1); }
    last = shown - 1;
    if (last < 0) { last = 0; }
    cursor.SetPosition(X + W * 0.06 + lines[last].image.GetWidth() + 8,
                       Y + H * 0.08 + last * lines[0].image.GetHeight() * 1.6, 11);
    if (Math.Int(global.tick / 15) % 2 == 0) { cursor.SetOpacity(1); } else { cursor.SetOpacity(0); }
}
Plymouth.SetRefreshFunction(refresh_cb);
""",
    "ascii": r"""
art_image = Image("art.png");
banner_image = Image("banner.png");
frame_image = Image("barframe.png");
fill_image = Image("barfill.png");
art = center(art_image, Y + H * 0.42 - art_image.GetHeight() - 30);
banner = center(banner_image, Y + H * 0.46);
frame = center(frame_image, Y + H * 0.46 + banner_image.GetHeight() + 50);
fill = Sprite();
fill_x = X + W / 2 - frame_image.GetWidth() / 2 + 6;
fill_y = Y + H * 0.46 + banner_image.GetHeight() + 56;

fun refresh_cb() {
    global.tick++;
    p = global.prog;
    if (p < 0.02) { p = 0.02; }
    fw = Math.Int((frame_image.GetWidth() - 12) * p);
    if (fw < 1) { fw = 1; }
    fill.SetImage(fill_image.Scale(fw, fill_image.GetHeight()));
    fill.SetPosition(fill_x, fill_y, 11);
    art.SetOpacity(0.75 + 0.25 * Math.Sin(global.tick / 20));
}
Plymouth.SetRefreshFunction(refresh_cb);
""",
    "wired": r"""
banner_image = Image("banner.png");
sub_image = Image("sub.png");
noise_images[0] = Image("noise0.png");
noise_images[1] = Image("noise1.png");
noise_images[2] = Image("noise2.png");
for (i = 0; i < 3; i++) { noise_scaled[i] = noise_images[i].Scale(W, H); }
noise = Sprite(noise_scaled[0]);
noise.SetPosition(X, Y, 1);
banner = center(banner_image, Y + H * 0.40);
sub = center(sub_image, Y + H * 0.40 + banner_image.GetHeight() + 30);
line_image = Image("barfill.png");
line = Sprite();

fun refresh_cb() {
    global.tick++;
    noise.SetImage(noise_scaled[Math.Int(global.tick / 3) % 3]);
    if (Math.Int(global.tick / 7) % 9 == 0) { banner.SetOpacity(0.35); } else { banner.SetOpacity(1); }
    lw = Math.Int(W * 0.5 * global.prog);
    if (lw < 2) { lw = 2; }
    line.SetImage(line_image.Scale(lw, 2));
    line.SetPosition(X + W / 4, Y + H * 0.40 + banner_image.GetHeight() + 90, 12);
}
Plymouth.SetRefreshFunction(refresh_cb);
""",
    "classic": r"""
banner_image = Image("banner.png");
track_image = Image("track.png");
chaser_image = Image("chaser.png");
banner = center(banner_image, Y + H * 0.38);
track = center(track_image, Y + H * 0.62);
chaser = Sprite(chaser_image);
track_x = X + W / 2 - track_image.GetWidth() / 2;

fun refresh_cb() {
    global.tick++;
    span = track_image.GetWidth() + chaser_image.GetWidth();
    off = (global.tick * 4) % span;
    cx = track_x - chaser_image.GetWidth() + off;
    chaser.SetPosition(cx, Y + H * 0.62 + (track_image.GetHeight() - chaser_image.GetHeight()) / 2, 11);
    if (cx < track_x || cx + chaser_image.GetWidth() > track_x + track_image.GetWidth()) {
        chaser.SetOpacity(0);
    } else {
        chaser.SetOpacity(1);
    }
}
Plymouth.SetRefreshFunction(refresh_cb);
""",
    "minimal": r"""
banner_image = Image("banner.png");
dot_image = Image("dot.png");
banner = center(banner_image, Y + H * 0.45);
dots = null;
for (i = 0; i < 3; i++) {
    dots[i] = Sprite(dot_image);
    dots[i].SetPosition(X + W / 2 + (i - 1) * dot_image.GetWidth() * 2.5 - dot_image.GetWidth() / 2,
                        Y + H * 0.45 + banner_image.GetHeight() + 40, 10);
}

fun refresh_cb() {
    global.tick++;
    for (i = 0; i < 3; i++) {
        dots[i].SetOpacity(0.25 + 0.75 * (Math.Sin(global.tick / 9 - i * 0.9) + 1) / 2);
    }
}
Plymouth.SetRefreshFunction(refresh_cb);
""",
}


def plymouth_files(ctx: "Ctx") -> dict[str, str]:
    c, font = ctx.c, ctx.s["theme"]["font"]
    style = style_for(ctx)
    text = banner_text(ctx)
    files: dict[str, str] = {}
    size = 30 if style != "bios" else 18
    big = asc.best_banner(text, 70 if style != "bios" else 100)
    from .render import mix
    files["banner.svg"] = blocks_svg(big, c["accent"], mix(c["accent"], c["base"], 0.5), size)
    files["prompt.svg"] = text_svg(["  Disk passphrase  "], c["text"], 26, font, bg=c["surface"], pad=14)
    files["bullet.svg"] = rect_svg(14, 14, c["accent"])
    top, bottom = c["base"], c["mantle"]
    n = 0
    if style == "bios":
        top = bottom = c["crust"]
        import platform
        lines = [f"{text.upper()} BIOS v2.0   (c) swayforge", "",
                 f"CPU ......................... {platform.machine() or 'x86_64'}  OK",
                 "Memory test ................. OK",
                 "Detecting drives ............ OK",
                 "Video adapter ............... OK",
                 "Loading Fedora .............. OK",
                 "Starting display server ....."]
        n = len(lines)
        for i, l in enumerate(lines):
            files[f"line{i}.svg"] = text_svg([l or " "], c["text"] if i else c["accent"], 26, font)
        files["cursor.svg"] = rect_svg(16, 28, c["accent"])
    elif style == "ascii":
        files["art.svg"] = text_svg(ctx.as_dict()["art"], c["accent2"], 24, font)
        files["barframe.svg"] = rect_svg(560, 34, c["mantle"], c["accent"], 3)
        files["barfill.svg"] = rect_svg(16, 22, c["accent"])
    elif style == "wired":
        top = bottom = c["crust"]
        files["banner.svg"] = text_svg(asc.banner("connecting"), c["accent"], 26, font)
        files["sub.svg"] = text_svg([f"node {text.lower()} :: link up :: handshake"], c["subtext"], 24, font)
        for i in range(3):
            files[f"noise{i}.svg"] = noise_svg(i + 1, 960, 540, c["text"])
        files["barfill.svg"] = rect_svg(16, 2, c["accent"])
    elif style == "classic":
        top, bottom = c["surface"], c["crust"]
        files["track.svg"] = rect_svg(420, 30, c["crust"], c["surface2"], 2)
        files["chaser.svg"] = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="18">'
            + "".join(f'<rect x="{i * 34}" y="0" width="28" height="18" fill="{c["accent"]}"/>' for i in range(3))
            + "</svg>")
    else:
        files["dot.svg"] = rect_svg(16, 16, c["accent"], rx=8)
    script = SCRIPT_COMMON + SCRIPTS[style]
    script = (script.replace("@STYLE@", style).replace("@TOP@", rgbf(top))
              .replace("@BOTTOM@", rgbf(bottom)).replace("@NLINES@", str(n)))
    files["swayforge.script"] = script
    files["swayforge.plymouth"] = (
        "[Plymouth Theme]\nName=swayforge\nDescription=swayforge boot screen\nModuleName=script\n\n"
        "[script]\nImageDir=/usr/share/plymouth/themes/swayforge\n"
        "ScriptFile=/usr/share/plymouth/themes/swayforge/swayforge.script\n")
    return files


APPLY_BOOT = r"""#!/usr/bin/env bash
# swayforge: install the boot screen. Run as your normal user – asks for sudo itself.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/plymouth"
DEST=/usr/share/plymouth/themes/swayforge
command -v rsvg-convert >/dev/null || { echo "rsvg-convert missing: sudo dnf install librsvg2-tools"; exit 1; }
echo ":: rendering images (with your fonts) …"
tmp="$(mktemp -d)"
for f in "$SRC"/*.svg; do rsvg-convert -o "$tmp/$(basename "${f%.svg}").png" "$f"; done
cp "$SRC"/swayforge.plymouth "$SRC"/swayforge.script "$tmp"/
echo ":: installing (sudo) …"
rpm -q plymouth-plugin-script >/dev/null 2>&1 || sudo dnf install -y plymouth-plugin-script
sudo rm -rf "$DEST"
sudo mkdir -p "$DEST"
sudo cp "$tmp"/* "$DEST"/
rm -rf "$tmp"
echo ":: rebuilding initramfs – this takes a minute …"
sudo plymouth-set-default-theme -R swayforge
echo ":: done – the new boot screen shows on next boot."
"""

APPLY_LOGIN = r"""#!/usr/bin/env bash
# swayforge: tuigreet login screen. Run as your normal user – asks for sudo itself.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
pkgs=""
for p in greetd greetd-selinux tuigreet; do rpm -q "$p" >/dev/null 2>&1 || pkgs="$pkgs $p"; done
[ -z "$pkgs" ] || sudo dnf install -y $pkgs
GUSER="$(grep -oP '^\s*user\s*=\s*"\K[^"]+' /etc/greetd/config.toml 2>/dev/null | head -1 || true)"
if [ -z "$GUSER" ]; then
  for u in greetd greeter; do getent passwd "$u" >/dev/null && { GUSER="$u"; break; }; done
fi
[ -n "$GUSER" ] || { echo "No greeter user found (greetd package broken?) – aborting, nothing changed."; exit 1; }
CMD="$(command -v start-sway || command -v sway)"
[ -f /etc/greetd/config.toml.swayforge-orig ] || sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.swayforge-orig 2>/dev/null || true
sed -e "s|@GUSER@|$GUSER|" -e "s|@CMD@|$CMD|" "$HERE/greetd.toml" | sudo tee /etc/greetd/config.toml >/dev/null
[ -f /etc/issue.swayforge-orig ] || sudo cp /etc/issue /etc/issue.swayforge-orig 2>/dev/null || true
sudo cp "$HERE/issue" /etc/issue
sudo mkdir -p /var/cache/tuigreet
sudo chown "$GUSER" /var/cache/tuigreet
for dm in sddm gdm lightdm lxdm; do
  if systemctl is-enabled "$dm" >/dev/null 2>&1; then sudo systemctl disable "$dm"; fi
done
sudo systemctl enable greetd
sudo systemctl set-default graphical.target >/dev/null
echo ":: login screen ready – active after the next reboot."
echo ":: emergency: Ctrl+Alt+F3, log in, then run:  bash $HERE/restore-sddm.sh"
"""

RESTORE_SDDM = r"""#!/usr/bin/env bash
# swayforge: go back to the SDDM login screen.
set -euo pipefail
sudo systemctl disable greetd || true
rpm -q sddm >/dev/null 2>&1 || sudo dnf install -y sddm
sudo systemctl enable sddm
[ -f /etc/issue.swayforge-orig ] && sudo cp /etc/issue.swayforge-orig /etc/issue
echo ":: SDDM is back after the next reboot."
"""


def login_files(ctx: "Ctx") -> dict[str, str]:
    c, lg = ctx.c, ctx.s["login"]
    theme = ";".join(f"{k}={ansi_name(v)}" for k, v in {
        "text": c["text"], "time": c["accent2"], "container": c["crust"], "border": c["accent"],
        "title": c["accent"], "greet": c["accent"], "prompt": c["accent2"], "input": c["text"],
        "action": c["subtext"], "button": c["accent"]}.items())
    flags = ["--issue", "--asterisks", "--width 90", "--container-padding 2", "--window-padding 1"]
    if lg["show_time"]:
        flags.append("--time")
    if lg["remember"]:
        flags.append("--remember")
    cmd = f"tuigreet {' '.join(flags)} --cmd @CMD@ --theme '{theme}'"
    greetd = (f"# {MARK_LINE}\n[terminal]\nvt = 1\n\n[default_session]\n"
              f'command = "{cmd}"\nuser = "@GUSER@"\n')
    art = ctx.as_dict()["art"]
    lines = art + [""] + asc.banner(banner_text(ctx), 5) + [""]
    if lg["greeting"].strip():
        lines.append(lg["greeting"].strip())
    # tuigreet replaces \n, \s, \l … – keep backslashes in the art from turning into escapes
    issue = "\n".join(re.sub(r"\\(?=[A-Za-z0-9\\])", "/", l) for l in lines) + "\n\n"
    return {"greetd.toml": greetd, "issue": issue}


MARK_LINE = "swayforge generated"


def prepare(ctx: "Ctx", w: "Writer") -> None:
    if w.dry:
        return
    pdir = BOOT_DIR / "plymouth"
    pdir.mkdir(parents=True, exist_ok=True)
    for old in pdir.iterdir():
        old.unlink()
    for name, content in plymouth_files(ctx).items():
        (pdir / name).write_text(content)
    for name, content in login_files(ctx).items():
        (BOOT_DIR / name).write_text(content)
    for name, content in (("apply-boot.sh", APPLY_BOOT), ("apply-login.sh", APPLY_LOGIN),
                          ("restore-sddm.sh", RESTORE_SDDM)):
        p = BOOT_DIR / name
        p.write_text(content)
        p.chmod(0o755)
