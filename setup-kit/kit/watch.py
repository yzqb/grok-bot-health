#!/usr/bin/env python3
"""Local sedentary watcher (Grok Bot Health kit).

Runs `gh.py sedentary` every `interval_minutes` during active hours (config.json),
and POSTs to the bot's webhook routine ONLY when the person has been sitting and the
data is fresh (at most once per `remind_gap_minutes`). Quiet checks cost no Grok Bot usage.

  watch.py          -> run forever (started by start_watch.sh with setsid nohup)
  watch.py once     -> one check now (ignores active hours), then exit
  watch.py test     -> POST {"event":"test"} to the webhook and print the HTTP status
"""
import json, subprocess, time, datetime, urllib.request, urllib.error, os, sys
from zoneinfo import ZoneInfo

H = os.environ.get("HEALTH_DIR") or os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(H, ".venv", "bin", "python")
CFG_WEBHOOK = os.path.join(H, "webhook.json")
STATE = os.path.join(H, "watch_state.json")
LOG = os.path.join(H, "watch.log")


def load(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d


CFG = load(os.path.join(H, "config.json"), {})
TZ = ZoneInfo(CFG.get("timezone", "Asia/Singapore"))
START_H = int(CFG.get("active_start_hour", 9))     # first check at START_H:00
END_H = int(CFG.get("active_end_hour", 22))        # last check at END_H:00
STEP = int(CFG.get("interval_minutes", 30))
GAP = int(CFG.get("remind_gap_minutes", 55)) * 60


def log(m):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 1_000_000:
            os.replace(LOG, LOG + ".1")
    except OSError: pass
    with open(LOG, "a") as f: f.write(f"{datetime.datetime.now(TZ):%F %T} {m}\n")
    os.chmod(LOG, 0o600)


def save_state(st):
    with open(STATE, "w") as f: json.dump(st, f)


def post(cfg, body):
    req = urllib.request.Request(cfg["url"], data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg['key']}", "X-Automation-Key": cfg["key"]})
    try:
        return urllib.request.urlopen(req, timeout=8).status
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            log(f"webhook {e.code}: sender key wrong or routine deleted/re-created -> redo set_webhook.py")
        return e.code


def check():
    cfg = load(CFG_WEBHOOK, None)
    if not cfg or not cfg.get("url") or not cfg.get("key"):
        log("no webhook config (webhook.json); skip"); return
    r = subprocess.run([PY, os.path.join(H, "gh.py"), "sedentary"], capture_output=True, text=True, timeout=120)
    st = load(STATE, {})
    if r.returncode != 0:
        if not st.get("error_sent"):
            detail = "authorization expired or revoked; run gh.py auth" if r.returncode == 3 else "gh.py sedentary failed"
            try:
                s = post(cfg, {"event": "error", "detail": detail})
                if s == 200: st["error_sent"] = True; save_state(st)
            except Exception as e: log(f"post fail {e}")
        log(f"gh.py failed rc={r.returncode} {(r.stdout or r.stderr)[-300:]!r}"); return
    d = json.loads(r.stdout); st.pop("error_sent", None)
    now = time.time()
    if d.get("sedentary") and not d.get("data_stale"):
        if now - st.get("last_reminded", 0) >= GAP:
            try:
                s = post(cfg, {"event": "sedentary", "steps_last_window": d.get("steps_last_window"),
                               "window_minutes": d.get("window_minutes"), "last_sync_time": d.get("last_sync_time")})
                if s == 200: st["last_reminded"] = now
                log(f"sedentary -> webhook {s} steps={d.get('steps_last_window')}")
            except Exception as e: log(f"post fail {e}")
        else: log("sedentary, already reminded recently")
    else:
        log(f"ok sedentary={d.get('sedentary')} stale={d.get('data_stale')} steps={d.get('steps_last_window')}")
    save_state(st)


def in_hours(n):
    return START_H <= n.hour < END_H or (n.hour == END_H and n.minute < STEP)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "once": check(); return
    if arg == "test":
        cfg = load(CFG_WEBHOOK, None)
        if not cfg: sys.exit("no webhook.json")
        print("webhook status:", post(cfg, {"event": "test"})); return
    if arg in ("-h", "--help"): print(__doc__); return
    log(f"watcher started (pid {os.getpid()}); catch-up check now if inside active hours")
    while True:
        n = datetime.datetime.now(TZ)
        if in_hours(n):
            try: check()
            except Exception as e: log(f"error {e}")
        n = datetime.datetime.now(TZ)
        nxt = n.replace(second=0, microsecond=0) + datetime.timedelta(minutes=STEP - n.minute % STEP)
        time.sleep(max(30, (nxt - n).total_seconds()))


if __name__ == "__main__": main()
