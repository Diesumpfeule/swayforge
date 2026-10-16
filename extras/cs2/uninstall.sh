#!/usr/bin/env bash
# Removes the CS2 chat translator (installed copy, watcher, launcher, log).
# Your overlay position (~/.config/cs2_chat_uebersetzer.json) and options
# (~/.config/swayforge/cs2.args) are kept – delete them by hand if you want.
BIN="$HOME/.local/bin"
pkill -f "$BIN/swayforge-cs2-watcher" 2>/dev/null
pkill -f "$BIN/cs2-uebersetzer-waechter" 2>/dev/null
pkill -f "cs2-chat-uebersetzer/cs2_chat_uebersetzer.py" 2>/dev/null
rm -f "$BIN/swayforge-cs2-watcher" "$BIN/cs2-uebersetzer" "$BIN/cs2-uebersetzer-waechter" \
      "$BIN/cs2-uebersetzer-start" "$HOME/.config/autostart/cs2-chat-uebersetzer.desktop" \
      "$HOME/.cache/cs2_chat_uebersetzer.log"
rm -rf "$HOME/.local/share/cs2-chat-uebersetzer"
echo "CS2 chat translator removed. Run 'swayforge apply' so Sway stops starting the watcher."
echo "Remove -condebug from the CS2 launch options in Steam if you don't need it anymore."
