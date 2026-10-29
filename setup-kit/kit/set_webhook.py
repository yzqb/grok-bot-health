#!/usr/bin/env python3
"""Write webhook.json (mode 600) without ever printing the sender key.

  set_webhook.py --url https://api2.cursor.sh/automations/webhook/<id> --key-env NAME_OF_ENV_VAR
  set_webhook.py --url ... --key-file /path/to/file/containing/key
  set_webhook.py --url ... --key-stdin          (key piped on stdin)
"""
import argparse, json, os, re, sys
H = os.environ.get("HEALTH_DIR") or os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--url", required=True)
g = ap.add_mutually_exclusive_group(required=True)
g.add_argument("--key-env"); g.add_argument("--key-file"); g.add_argument("--key-stdin", action="store_true")
a = ap.parse_args()
if not re.fullmatch(r"https://api2\.cursor\.sh/automations/webhook/[0-9a-fA-F-]{36}", a.url.strip()):
    sys.exit("URL does not look like https://api2.cursor.sh/automations/webhook/<uuid> (copy it from the routine panel)")
if a.key_env: key = os.environ.get(a.key_env, "")
elif a.key_file: key = open(a.key_file).read()
else: key = sys.stdin.read()
key = key.strip()
if len(key) < 8: sys.exit("sender key missing/too short (value not printed)")
p = os.path.join(H, "webhook.json")
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f: json.dump({"url": a.url.strip(), "key": key}, f)
os.chmod(p, 0o600)
b = os.environ.get("HEALTH_BACKUP_DIR", "/home/box/.health-backup")
os.makedirs(b, mode=0o700, exist_ok=True)
fd = os.open(os.path.join(b, "webhook.json"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f: json.dump({"url": a.url.strip(), "key": key}, f)
print(f"saved {p} (key length {len(key)}, not shown). Next: watch.py test  -> expect 200")
