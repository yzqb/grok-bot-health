#!/bin/bash
# Start the sedentary watcher if it is not running. Idempotent. No cron on the box (PID 1 is tini),
# so the watcher is a setsid+nohup daemon; restore.sh calls this after every box reset/update.
H="${HEALTH_DIR:-$(cd "$(dirname "$0")" && pwd)}"
if pgrep -f "$H/watch.py" >/dev/null; then
  echo "watcher already running (pid $(pgrep -f "$H/watch.py" | head -1))"
else
  HEALTH_DIR="$H" setsid nohup "$H/.venv/bin/python" "$H/watch.py" >/dev/null 2>&1 < /dev/null &
  sleep 1
  pgrep -f "$H/watch.py" >/dev/null && echo "watcher started" || { echo "watcher FAILED to start; see $H/watch.log" >&2; exit 1; }
fi
