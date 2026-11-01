#!/bin/bash
# Removes voiceforge (your sounds and settings stay unless you add --all).
"$HOME/.local/bin/voiceforge" stop >/dev/null 2>&1 || true
rm -rf "$HOME/.local/share/voiceforge/app"
rm -f "$HOME/.local/bin/voiceforge" "$HOME/.local/share/applications/voiceforge.desktop"
if [ "$1" = "--all" ]; then
  rm -rf "$HOME/.local/share/voiceforge" "$HOME/.config/voiceforge"
fi
echo "voiceforge removed."
