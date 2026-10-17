#!/usr/bin/env bash
# =============================================================================
#  opencode auf deinem Linux-PC mit der KI vom Homeserver verbinden
#
#  - installiert opencode (falls noch nicht da)
#  - trägt den Server (Ollama über Tailscale) als KI-Anbieter ein
#  - legt den Befehl 'oc' an: weckt den Server bei Bedarf und startet opencode
#
#  Start (als normaler Benutzer, OHNE sudo):
#     ./opencode-setup.sh server.dein-tailnet.ts.net
#  Modell-Liste später aktualisieren:
#     ./opencode-setup.sh --refresh
# =============================================================================
set -Eeuo pipefail

if [[ -t 1 ]]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'
else B=""; G=""; Y=""; R=""; C=""; N=""; fi
info() { echo; echo "${C}==>${N} ${B}$*${N}"; }
ok()   { echo "${G}  ✓${N} $*"; }
warn() { echo "${Y}  !${N} $*"; }
die()  { echo "${R}  ✗ $*${N}" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "Bitte OHNE sudo starten - opencode gehört in deinen Benutzer."

SETTINGS="$HOME/.config/homeserver-opencode.conf"
CFG_DIR="$HOME/.config/opencode"
CFG="$CFG_DIR/opencode.json"
BIN="$HOME/.local/bin"

# ---------- Einstellungen ---------------------------------------------------
SERVER=""; PI_HOST="pi"
# shellcheck disable=SC1090
[[ -f "$SETTINGS" ]] && source "$SETTINGS"
if [[ "${1:-}" != "--refresh" && -n "${1:-}" ]]; then SERVER="$1"; fi
if [[ -z "$SERVER" ]]; then
  read -rp "Tailscale-Name des Servers (steht in 'homeserver info', z.B. server.xyz.ts.net): " SERVER
fi
[[ -n "$SERVER" ]] || die "Kein Servername angegeben."
read -rp "SSH-Name des Raspberry Pi zum Aufwecken [$PI_HOST]: " ans || true
PI_HOST="${ans:-$PI_HOST}"
mkdir -p "$(dirname "$SETTINGS")"
printf 'SERVER="%s"\nPI_HOST="%s"\n' "$SERVER" "$PI_HOST" > "$SETTINGS"
URL="http://$SERVER:11434"

# ---------- Werkzeuge -------------------------------------------------------
info "Werkzeuge prüfen"
need=()
command -v curl >/dev/null || need+=(curl)
command -v jq   >/dev/null || need+=(jq)
if ((${#need[@]})); then
  warn "Installiere ${need[*]} (braucht dein sudo-Passwort)"
  if command -v dnf >/dev/null; then sudo dnf install -y "${need[@]}"
  elif command -v apt-get >/dev/null; then sudo apt-get install -y "${need[@]}"
  else die "Bitte ${need[*]} selbst installieren."; fi
fi
command -v tailscale >/dev/null || warn "Tailscale ist hier nicht installiert. Ohne Tailscale erreichst du den Server nur, wenn der Name im Heimnetz auflösbar ist."
ok "Bereit."

# ---------- Server erreichen (und notfalls wecken) -------------------------
info "Server $SERVER erreichen"
if ! curl -fs --max-time 4 "$URL/api/tags" >/dev/null; then
  warn "Server antwortet nicht. Ich versuche, ihn über den Pi zu wecken ..."
  ssh -o ConnectTimeout=8 "$PI_HOST" wake-server || warn "Wecken über '$PI_HOST' ging nicht."
  for i in {1..40}; do
    curl -fs --max-time 3 "$URL/api/tags" >/dev/null && break
    printf "\r  warte auf den Server ... %ss " $((i * 3)); sleep 3
  done; echo
fi
TAGS=$(curl -fs --max-time 10 "$URL/api/tags") || die "Ollama auf $URL ist nicht erreichbar. Läuft Tailscale hier und auf dem Server?"
MODELS=$(jq -c '[.models[].name] | map({(.): {name: .}}) | add // {}' <<<"$TAGS")
[[ "$MODELS" != "{}" ]] || die "Auf dem Server ist noch kein Modell. Dort ausführen:  homeserver pull qwen3:14b"
ok "Gefundene Modelle: $(jq -r 'keys | join(", ")' <<<"$MODELS")"

# ---------- opencode installieren -------------------------------------------
info "opencode installieren"
export PATH="$HOME/.opencode/bin:$BIN:$PATH"
if command -v opencode >/dev/null; then
  ok "opencode ist schon da ($(opencode --version 2>/dev/null || echo '?'))."
else
  curl -fsSL https://opencode.ai/install | bash
  export PATH="$HOME/.opencode/bin:$PATH"
  command -v opencode >/dev/null || die "opencode wurde nicht gefunden. Terminal neu öffnen und Skript nochmal starten."
  ok "opencode installiert."
fi
OPENCODE_BIN=$(command -v opencode)

# ---------- Konfiguration ---------------------------------------------------
info "opencode mit dem Server verbinden"
mkdir -p "$CFG_DIR"
DEFAULT=$(jq -r 'keys | map(select(test("coder"))) + keys | .[0]' <<<"$MODELS")
NEW=$(jq -n --arg url "$URL/v1" --argjson models "$MODELS" --arg def "homeserver/$DEFAULT" '{
  "$schema": "https://opencode.ai/config.json",
  model: $def,
  provider: { homeserver: {
    npm: "@ai-sdk/openai-compatible",
    name: "Homeserver (Ollama)",
    options: { baseURL: $url },
    models: $models
  } }
}')
if [[ -f "$CFG" ]]; then
  cp "$CFG" "$CFG.bak.$(date +%Y%m%d-%H%M%S)"
  # Bestehende Einstellungen behalten, nur Anbieter + Modell-Liste ersetzen
  jq --argjson new "$NEW" '. * {"$schema": $new["$schema"], provider: {homeserver: $new.provider.homeserver}}
      | .model = (if (.model // "" | startswith("homeserver/")) or (.model == null) then $new.model else .model end)
      | .provider.homeserver.models = $new.provider.homeserver.models' "$CFG" > "$CFG.tmp"
  mv "$CFG.tmp" "$CFG"
  ok "Bestehende Konfiguration ergänzt (Sicherung: $CFG.bak.*)"
else
  echo "$NEW" > "$CFG"
  ok "Konfiguration angelegt: $CFG"
fi

# ---------- Befehl 'oc' -----------------------------------------------------
info "Befehl 'oc' anlegen"
mkdir -p "$BIN"
cat > "$BIN/oc" <<EOF
#!/usr/bin/env bash
# Startet opencode mit der KI vom Homeserver - weckt den Server, falls er schläft.
URL="$URL"
if ! curl -fs --max-time 3 "\$URL/api/tags" >/dev/null; then
  echo "Server schläft - wecke ihn über $PI_HOST ..."
  ssh -o ConnectTimeout=8 "$PI_HOST" wake-server >/dev/null || echo "Wecken fehlgeschlagen."
  for i in {1..40}; do
    curl -fs --max-time 3 "\$URL/api/tags" >/dev/null && break
    printf "\\r  warte auf den Server ... %ss " \$((i * 3)); sleep 3
  done; echo
fi
exec "$OPENCODE_BIN" "\$@"
EOF
chmod +x "$BIN/oc"
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN ist nicht im PATH. Füge in ~/.bashrc hinzu:  export PATH=\"\$HOME/.local/bin:\$PATH\"";; esac
ok "Fertig."

echo
echo "${G}${B}=====================  FERTIG  =====================${N}"
echo "Starten:     ${B}cd dein-projekt && oc${N}"
echo "Standard-Modell: $DEFAULT   (in opencode wechseln mit  /models)"
echo
echo "Tipps:"
echo " - Im Projekt einmal  /init  ausführen: opencode legt AGENTS.md mit Projektinfos an."
echo " - Tab wechselt zwischen 'plan' (nur lesen) und 'build' (darf ändern)."
echo " - Neues Modell: auf dem Server  homeserver pull <name>, hier  ./opencode-setup.sh --refresh"
echo " - Arbeite in Git-Projekten, dann kannst du jede Änderung der KI rückgängig machen."
