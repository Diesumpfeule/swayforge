#!/usr/bin/env bash
# swayforge-cs2-watcher: runs the chat translator while CS2 is running.
# Started by Sway (exec_always) – a running older watcher is replaced.
PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/swayforge-cs2-watcher.pid"
LOG="$HOME/.cache/cs2_chat_uebersetzer.log"
SCRIPT="$HOME/.local/share/cs2-chat-uebersetzer/cs2_chat_uebersetzer.py"
ARGS_FILE="$HOME/.config/swayforge/cs2.args"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill "$(cat "$PIDFILE")" 2>/dev/null
fi
echo $$ > "$PIDFILE"
mkdir -p "$(dirname "$LOG")"

child=""
trap '[ -n "$child" ] && kill "$child" 2>/dev/null; rm -f "$PIDFILE"; exit 0' TERM INT

running() { pgrep -x cs2 >/dev/null 2>&1; }

while true; do
  until running; do sleep 5; done
  sleep 6                                         # let CS2 open its window first
  echo "$(date '+%F %T') CS2 erkannt, starte Übersetzer" >>"$LOG"
  # --verlauf 0 first, so options in cs2.args can still override it
  extra=$(grep -v '^[[:space:]]*#' "$ARGS_FILE" 2>/dev/null | tr '\n' ' ')
  eval "set -- --verlauf 0 $extra"
  python3 "$SCRIPT" "$@" >>"$LOG" 2>&1 &
  child=$!
  while running && kill -0 "$child" 2>/dev/null; do sleep 3; done
  kill "$child" 2>/dev/null
  wait "$child" 2>/dev/null
  child=""
  echo "$(date '+%F %T') Übersetzer beendet" >>"$LOG"
  # if the translator crashed: don't restart it in a loop, wait until CS2 is closed
  while running; do sleep 5; done
done
