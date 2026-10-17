#!/usr/bin/env bash
# Removes steamtune. Your limits (~/.config/steamtune.json) stay. A shader cache moved to another
# drive stays there too – run `steamtune move N back` first if you want it back.
systemctl --user disable steamtune-prune.service >/dev/null 2>&1
rm -f "$HOME/.config/systemd/user/steamtune-prune.service" "$HOME/.local/bin/steamtune"
rm -rf "$HOME/.local/share/steamtune"
systemctl --user daemon-reload 2>/dev/null
echo "steamtune removed."
