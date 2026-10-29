#!/bin/bash
# Grok Bot Health kit: restore everything after a box reset / automatic update. Idempotent, safe to run any time.
#   restore.sh           -> fix what is missing, start the watcher, print a short status
#   restore.sh --quiet   -> same, prints only problems (use this on every wake-up)
# What a box reset does: running processes and system installs (/usr, apt packages, /tmp) are gone;
# files under /home/box stay. So: code + venv + secrets live in $H, a second copy of the secrets lives in $B,
# and this script rebuilds the venv if the system Python changed, then restarts the watcher daemon.
H="${HEALTH_DIR:-/home/box/health}"
B="${HEALTH_BACKUP_DIR:-/home/box/.health-backup}"
Q=0; [ "$1" = "--quiet" ] && Q=1
say() { [ $Q = 1 ] || echo "$@"; }
warn() { echo "[health restore] $*" >&2; }
cd "$H" 2>/dev/null || { warn "missing $H (kit not installed)"; exit 1; }
umask 077; mkdir -p "$B"; chmod 700 "$B" "$H"

# 1) reset detection (boot id changes on every reset/reboot)
BOOT=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
if [ -n "$BOOT" ] && [ "$(cat "$H/.last_boot_id" 2>/dev/null)" != "$BOOT" ]; then
  [ -f "$H/.last_boot_id" ] && say "box reset/restart detected -> restoring"
  echo "$BOOT" > "$H/.last_boot_id"
fi

# 2) Python + venv (rebuild if the system python was replaced and the venv broke)
if ! command -v python3 >/dev/null; then
  sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv >/dev/null || warn "python3 install failed"
fi
if ! "$H/.venv/bin/python" -c "import requests, google.oauth2.credentials, google_auth_oauthlib" 2>/dev/null; then
  say "rebuilding venv"
  rm -rf "$H/.venv"
  python3 -m venv "$H/.venv" 2>/dev/null || { sudo apt-get update -qq; sudo apt-get install -y -qq python3-venv >/dev/null; python3 -m venv "$H/.venv"; }
  "$H/.venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1
  "$H/.venv/bin/pip" install -q -r "$H/requirements.txt" || warn "pip install failed (network?) - rerun restore.sh"
fi

# 3) secrets/config: live copy <-> backup copy (only valid, non-empty JSON is ever copied)
valid() { [ -s "$1" ] && python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$1" 2>/dev/null; }
for f in client_secret.json token.json webhook.json config.json; do
  if valid "$H/$f"; then cp -p "$H/$f" "$B/$f"
  elif valid "$B/$f"; then cp -p "$B/$f" "$H/$f"; say "restored $f from backup"
  fi
  chmod 600 "$H/$f" "$B/$f" 2>/dev/null
done
[ -s "$H/config.json" ] || cp "$H/config.example.json" "$H/config.json"
for f in client_secret.json token.json webhook.json; do [ -s "$H/$f" ] || warn "missing $f (setup step not done yet)"; done

# 4) start the watcher daemon (it does a catch-up check immediately if inside active hours)
if [ -s "$H/token.json" ] && [ -s "$H/webhook.json" ]; then
  out=$(HEALTH_DIR="$H" "$H/start_watch.sh" 2>&1) || warn "$out"
  say "$out"
fi
say "health kit ok: venv $("$H/.venv/bin/python" -V 2>&1), watcher pid $(pgrep -f "$H/watch.py" | head -1)"
exit 0
