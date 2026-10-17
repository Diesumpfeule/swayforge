#!/usr/bin/env bash
# Installs opencode (AI coding agent for the terminal) for the current user.
# Connecting it to a home server (Ollama over Tailscale) is a separate, interactive step:
#   opencode-setup server.your-tailnet.ts.net
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
export PATH="$HOME/.opencode/bin:$BIN:$PATH"

mkdir -p "$BIN"
install -m 755 "$HERE/opencode-setup.sh" "$BIN/opencode-setup"

if command -v opencode >/dev/null; then
  echo "opencode already installed ($(opencode --version 2>/dev/null || echo '?'))."
else
  curl -fsSL https://opencode.ai/install | bash || { echo "opencode: install failed."; exit 1; }
fi

cat <<EOT
opencode installed.
  opencode                              start it in a project folder
  opencode-setup server.xyz.ts.net      connect it to your home server's Ollama (needs Tailscale)
EOT
