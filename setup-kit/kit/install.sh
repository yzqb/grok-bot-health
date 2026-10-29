#!/bin/bash
# Install / update the Grok Bot Health kit into $HEALTH_DIR (default /home/box/health).
# Never overwrites client_secret.json, token.json, webhook.json or config.json.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
H="${HEALTH_DIR:-/home/box/health}"
mkdir -p "$H"; chmod 700 "$H"
if [ "$SRC" != "$H" ]; then
  for f in gh.py watch.py start_watch.sh restore.sh set_webhook.py requirements.txt config.example.json; do
    cp "$SRC/$f" "$H/$f"
  done
  mkdir -p "$H/pages"; cp -r "$SRC/pages/." "$H/pages/"
fi
chmod 700 "$H"/*.py "$H"/*.sh
[ -s "$H/config.json" ] || { cp "$H/config.example.json" "$H/config.json"; chmod 600 "$H/config.json"; }
HEALTH_DIR="$H" "$H/restore.sh"
echo "installed to $H"
