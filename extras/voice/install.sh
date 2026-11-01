#!/bin/bash
# Installs voiceforge for your user: ~/.local/share/voiceforge/app + the `voiceforge` command.
# Needs: PipeWire (Fedora's default), numpy, Textual for the terminal app.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/voiceforge/app"
BIN="$HOME/.local/bin/voiceforge"

[ -f "$HERE/voiceforge.py" ] || { echo "voiceforge.py not found – run install.sh from its folder."; exit 1; }

missing=()
python3 -c "import numpy" 2>/dev/null || missing+=(python3-numpy)
python3 -c "import textual" 2>/dev/null || missing+=(python3-textual)
command -v pw-record >/dev/null || missing+=(pipewire-utils)
command -v pactl >/dev/null || missing+=(pulseaudio-utils)
if [ ${#missing[@]} -gt 0 ]; then
  if command -v dnf >/dev/null; then
    echo "Installing: ${missing[*]}"
    sudo dnf install -y --skip-unavailable "${missing[@]}"
  else
    echo "Please install: ${missing[*]} (numpy, Textual, pw-record/pw-play, pactl)"
  fi
fi

mkdir -p "$DEST" "$(dirname "$BIN")" "$HOME/.local/share/applications"
cp "$HERE/voiceforge.py" "$DEST/"
cat > "$BIN" <<EOB
#!/bin/sh
exec python3 "$DEST/voiceforge.py" "\$@"
EOB
chmod +x "$BIN"

cat > "$HOME/.local/share/applications/voiceforge.desktop" <<EOD
[Desktop Entry]
Type=Application
Name=voiceforge
Comment=Voice changer and soundboard (virtual microphone)
Exec=$BIN
Terminal=true
Icon=audio-input-microphone
Categories=AudioVideo;Audio;
EOD

# a running engine picks up the new version on its next start
if "$BIN" status 2>/dev/null | grep -q "running        : yes"; then
  "$BIN" stop >/dev/null && "$BIN" start >/dev/null || true
fi
# Sway hotkeys file (swayforge includes it; plain Sway: add  include ~/.config/voiceforge/sway.conf)
[ -f "$HOME/.config/voiceforge/sway.conf" ] || "$BIN" keys >/dev/null || true

echo "Done.  voiceforge          the app (effects, soundboard)"
echo "       voiceforge start    virtual microphone on – pick “VoiceForge Microphone” in Discord, CS2, OBS"
echo "       voiceforge --help   everything else"
