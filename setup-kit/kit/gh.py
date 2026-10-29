#!/usr/bin/env python3
"""Minimal Google Health API (v4) client for one personal account (Grok Bot Health kit).

  gh.py auth                 -> one-time OAuth (loopback on localhost:PORT, prints URL, no browser)
  gh.py auth --manual        -> fallback: print URL, then paste the full http://localhost:PORT/?code=... URL
  gh.py identity             -> check the Google account is linked to Google Health
  gh.py daily --days N       -> JSON daily summary for the last N days
  gh.py sedentary [--minutes 60] [--threshold 250] -> JSON sit-still check
  gh.py hourly [--date YYYY-MM-DD] -> JSON steps per hour (local timezone from config.json)

Files live next to this script (or in $HEALTH_DIR): client_secret.json, token.json, config.json.
Exit code 3 = authorization missing/expired/revoked -> run `gh.py auth` again.
"""
import argparse, datetime as dt, json, os, sys
import requests
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

H = os.environ.get("HEALTH_DIR") or os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(H, "client_secret.json")
TOKEN = os.path.join(H, "token.json")
BACKUP = os.environ.get("HEALTH_BACKUP_DIR", "/home/box/.health-backup")  # second copy, survives box resets


def _cfg():
    try:
        with open(os.path.join(H, "config.json")) as f: return json.load(f)
    except Exception: return {}


CFG = _cfg()
PORT = int(CFG.get("oauth_port", 8765))
BASE = "https://health.googleapis.com/v4/users/me"
P = "https://www.googleapis.com/auth/googlehealth."
SCOPES = [P + s + ".readonly" for s in
          ("activity_and_fitness", "health_metrics_and_measurements", "sleep", "profile")]
# settings.readonly is needed only for /pairedDevices (lastSyncTime). Requested on the
# next `auth`; refresh keeps whatever scopes the saved token already has.
AUTH_SCOPES = SCOPES + [P + "settings.readonly"]
TZ = ZoneInfo(CFG.get("timezone", "Asia/Singapore"))
TZ_LABEL = f"{CFG.get('timezone', 'Asia/Singapore')}"


def save(creds):
    os.makedirs(os.path.dirname(TOKEN), mode=0o700, exist_ok=True)
    fd = os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())
    os.chmod(TOKEN, 0o600)
    try:  # keep a backup copy for restore.sh
        os.makedirs(BACKUP, mode=0o700, exist_ok=True)
        bp = os.path.join(BACKUP, "token.json")
        fd = os.open(bp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f: f.write(creds.to_json())
    except OSError:
        pass


def cmd_auth(a):
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not os.path.exists(CLIENT_SECRET):
        sys.exit(f"missing {CLIENT_SECRET} (download the Desktop-app OAuth client JSON and save it there)")
    j = json.load(open(CLIENT_SECRET))
    if "installed" not in j:
        sys.exit("client_secret.json is not a *Desktop app* OAuth client (top-level key must be 'installed'). "
                 "Create a new OAuth client of type 'Desktop app' and download its JSON.")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, AUTH_SCOPES)
    if a.manual:
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # loopback http redirect, never leaves the machine
        flow.redirect_uri = f"http://localhost:{PORT}/"
        url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        print("Open this URL to authorize:\n" + url + "\n", flush=True)
        resp = input("After 'Continue', the browser lands on a page that fails to load.\n"
                     "Paste that page's FULL address (starts with http://localhost): ").strip()
        flow.fetch_token(authorization_response=resp)
        creds = flow.credentials
        if not creds.refresh_token: sys.exit("no refresh_token returned")
        save(creds); print("token saved to", TOKEN); return
    creds = flow.run_local_server(
        host="localhost", port=PORT, open_browser=False,
        authorization_prompt_message="Open this URL to authorize:\n{url}\n",
        success_message="Authorized. You can close this tab.",
        access_type="offline", prompt="consent")
    if not creds.refresh_token:
        sys.exit("no refresh_token returned")
    save(creds)
    print("token saved to", TOKEN)


def creds():
    if not os.path.exists(TOKEN):
        print(json.dumps({"error": "not_authorized", "fix": "run gh.py auth"})); sys.exit(3)
    c = Credentials.from_authorized_user_file(TOKEN)  # use the scopes stored with the token
    if not c.valid:
        try:
            c.refresh(Request())
        except RefreshError as e:
            # invalid_grant: token expired (Testing mode = 7 days), revoked, or unused ~6 months
            print(json.dumps({"error": "auth_expired_or_revoked", "detail": str(e)[:300],
                              "fix": "check consent screen is 'In production', then run gh.py auth"}))
            sys.exit(3)
        save(c)
    return c


class API:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(Authorization="Bearer " + creds().token, Accept="application/json")

    def _ok(self, r):
        if r.status_code != 200:
            return {"_error": r.status_code, "_body": r.text[:500]}
        return r.json()

    def list(self, dtype, flt, page_size=None):
        out, tok = [], None
        while True:
            params = {"filter": flt}
            if page_size: params["pageSize"] = page_size
            if tok: params["pageToken"] = tok
            j = self._ok(self.s.get(f"{BASE}/dataTypes/{dtype}/dataPoints", params=params))
            if "_error" in j: return j
            out += j.get("dataPoints", [])
            tok = j.get("nextPageToken")
            if not tok: return out

    def daily_rollup(self, dtype, start, end, chunk=14):
        """start inclusive, end exclusive (dates). Chunked to respect 14-day limit."""
        out, cur = [], start
        civ = lambda d: {"date": {"year": d.year, "month": d.month, "day": d.day}, "time": {}}
        while cur < end:
            stop = min(cur + dt.timedelta(days=chunk), end)
            body = {"range": {"start": civ(cur), "end": civ(stop)}, "windowSizeDays": 1}
            j = self._ok(self.s.post(f"{BASE}/dataTypes/{dtype}/dataPoints:dailyRollUp", json=body))
            if "_error" in j: return j
            out += j.get("rollupDataPoints", [])
            cur = stop
        return out


def num(v):
    """API returns int64 as strings; convert recursively."""
    if isinstance(v, dict): return {k: num(x) for k, x in v.items()}
    if isinstance(v, list): return [num(x) for x in v]
    if isinstance(v, str):
        try: return int(v)
        except ValueError:
            try: return float(v)
            except ValueError: return v
    return v


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ)


def sgt(t, fmt="%Y-%m-%d %H:%M:%S"):
    return t.astimezone(TZ).strftime(fmt) if t else None


def zulu(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def step_buckets(api, start, end, window_min):
    """{bucket_start_utc: steps} for [start,end) aligned buckets. rollUp, else raw list."""
    buckets, t = {}, start
    while t < end:
        buckets[t] = 0; t += dt.timedelta(minutes=window_min)
    j = api._ok(api.s.post(f"{BASE}/dataTypes/steps/dataPoints:rollUp", json={
        "range": {"startTime": zulu(start), "endTime": zulu(end)}, "windowSize": f"{window_min*60}s"}))
    if "_error" not in j:
        for p in j.get("rollupDataPoints", []):
            b = parse(p["startTime"]).astimezone(dt.timezone.utc)
            if b in buckets: buckets[b] = num(p.get("steps", {}).get("countSum", 0))
        return buckets, "rollUp"
    r = api.list("steps", f'steps.interval.start_time >= "{zulu(start)}"', page_size=1000)
    if isinstance(r, dict): return {"rollUp": j, "list": r}, None
    for p in r:
        iv = p["steps"]["interval"]; st = parse(iv["startTime"]).astimezone(dt.timezone.utc)
        if not (start <= st < end): continue
        b = start + dt.timedelta(minutes=window_min) * ((st - start) // dt.timedelta(minutes=window_min))
        buckets[b] += num(p["steps"].get("count", 0))
    return buckets, "list"


def last_sync(api):
    """(datetime, source). pairedDevices.lastSyncTime if the token has settings scope;
    otherwise newest heart-rate sample / step interval (both come from the band's sync)."""
    j = api._ok(api.s.get(f"{BASE}/pairedDevices", params={"pageSize": 100}))
    if "_error" not in j:
        ts = [parse(d["lastSyncTime"]) for d in j.get("pairedDevices", []) if d.get("lastSyncTime")]
        if ts: return max(ts), "pairedDevices"
    since = zulu(dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12))
    cands = []
    for dtype, flt, get in (
            ("heart-rate", f'heart_rate.sample_time.physical_time >= "{since}"',
             lambda p: p["heartRate"]["sampleTime"]["physicalTime"]),
            ("steps", f'steps.interval.start_time >= "{since}"',
             lambda p: p["steps"]["interval"]["endTime"])):
        r = api._ok(api.s.get(f"{BASE}/dataTypes/{dtype}/dataPoints", params={"filter": flt, "pageSize": 5}))
        if "_error" not in r:
            cands += [parse(get(p)) for p in r.get("dataPoints", [])]
    return (max(cands), "latest_data_point") if cands else (None, None)


def cmd_sedentary(a):
    api = API()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    q = 15
    end = now.replace(second=0) + dt.timedelta(minutes=(q - now.minute % q) % q)
    if end == now.replace(second=0) and now.second: end += dt.timedelta(minutes=q)
    start = end - dt.timedelta(hours=3)
    buckets, method = step_buckets(api, start, end, q)
    if method is None:
        print(json.dumps({"error": buckets}, indent=2)); sys.exit(1)
    sync, sync_src = last_sync(api)
    mins_since = round((now - sync).total_seconds() / 60, 1) if sync else None
    stale = mins_since is None or mins_since > int(CFG.get("stale_minutes", 30))
    # window ends at the last synced data (not "now"), so an un-synced gap isn't counted as sitting
    w_end = min(sync, now) if sync else now
    w_start = w_end - dt.timedelta(minutes=a.minutes)
    # per-minute precision for the window from the raw list (rollUp buckets are 15-min)
    r = api.list("steps", f'steps.interval.start_time >= "{zulu(w_start - dt.timedelta(minutes=1))}"', page_size=1000)
    if isinstance(r, dict):  # fall back to buckets fully inside window
        win = sum(v for b, v in buckets.items() if b >= w_start and b + dt.timedelta(minutes=q) <= w_end + dt.timedelta(minutes=q))
    else:
        win = 0
        for p in r:
            iv = p["steps"]["interval"]; s0, s1 = parse(iv["startTime"]), parse(iv["endTime"])
            ov = (min(s1, w_end) - max(s0, w_start)).total_seconds()
            if ov > 0: win += num(p["steps"].get("count", 0)) * ov / max((s1 - s0).total_seconds(), 1)
        win = round(win)
    out = {
        "now": sgt(now), "timezone": TZ_LABEL,
        "last_sync_time": sgt(sync), "last_sync_source": sync_src,
        "minutes_since_sync": mins_since,
        "buckets_15min": [{"start": sgt(b, "%H:%M"), "end": sgt(b + dt.timedelta(minutes=q), "%H:%M"), "steps": v}
                          for b, v in sorted(buckets.items())],
        "bucket_method": method,
        "window_minutes": a.minutes, "window": [sgt(w_start), sgt(w_end)],
        "threshold": a.threshold, "steps_last_window": win,
        "data_stale": stale,
        "sedentary": (win < a.threshold) and not stale,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_identity(_):
    api = API()
    r = api.s.get(f"{BASE}/identity")
    if r.status_code == 200:
        print(json.dumps({"linked": True}, indent=2)); return
    body = r.text[:500]
    hint = ("Google account is not linked to Google Health: install the Google Health app on the phone, "
            "sign in with THIS Google account, finish setup / Fitbit migration, then retry"
            if "ACCOUNT_NOT_LINKED" in body else "see body")
    print(json.dumps({"linked": False, "status": r.status_code, "body": body, "hint": hint}, indent=2))
    sys.exit(1)


def cmd_hourly(a):
    api = API()
    day = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(TZ).date()
    start = dt.datetime.combine(day, dt.time(), TZ).astimezone(dt.timezone.utc)
    end = start + dt.timedelta(days=1)
    buckets, method = step_buckets(api, start, end, 60)
    if method is None:
        print(json.dumps({"error": buckets}, indent=2)); sys.exit(1)
    hours = {sgt(b, "%H:00"): v for b, v in sorted(buckets.items())}
    print(json.dumps({"date": day.isoformat(), "timezone": TZ_LABEL,
                      "method": method, "total": sum(hours.values()), "hours": hours},
                     indent=2, ensure_ascii=False))


def dkey(civil):
    d = civil["date"]; return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}"


def cmd_daily(a):
    api = API()
    today = dt.datetime.now(TZ).date()
    start = today - dt.timedelta(days=a.days - 1)
    end = today + dt.timedelta(days=1)
    days = {(start + dt.timedelta(days=i)).isoformat(): {} for i in range(a.days)}
    errors = {}

    # Interval types: daily rollups
    for dtype, field in (("steps", "steps"), ("total-calories", "totalCalories"),
                         ("active-zone-minutes", "activeZoneMinutes")):
        r = api.daily_rollup(dtype, start, end)
        if isinstance(r, dict): errors[dtype] = r; continue
        for p in r:
            k = dkey(p["civilStartTime"])
            if k not in days: continue
            v = p.get(field) or {}
            if dtype == "steps":
                days[k]["steps"] = num(v.get("countSum"))
            elif dtype == "total-calories":
                days[k]["total_calories_kcal"] = round(num(v.get("kcalSum")), 1)
            else:
                azm = {"fat_burn": num(v.get("sumInFatBurnHeartZone")),
                       "cardio": num(v.get("sumInCardioHeartZone")),
                       "peak": num(v.get("sumInPeakHeartZone"))}
                azm["total"] = sum(azm.values())
                days[k]["active_zone_minutes"] = azm

    # Daily summary types: list filtered on <type>.date
    for dtype in ("daily-resting-heart-rate", "daily-heart-rate-variability", "daily-oxygen-saturation"):
        snake = dtype.replace("-", "_")
        camel = "".join(w if i == 0 else w.title() for i, w in enumerate(dtype.split("-")))
        r = api.list(dtype, f'{snake}.date >= "{start.isoformat()}"')
        if isinstance(r, dict): errors[dtype] = r; continue
        for p in r:
            v = p.get(camel, {}); d = v.get("date")
            k = f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}" if isinstance(d, dict) else d
            if k in days:
                days[k][dtype] = {x: num(y) for x, y in v.items() if x != "date"}

    # Sleep: list filtered on end time, keep summary only, bucket by wake date
    since = dt.datetime.combine(start, dt.time(), TZ).astimezone(dt.timezone.utc)
    r = api.list("sleep", f'sleep.interval.end_time >= "{since.strftime("%Y-%m-%dT%H:%M:%SZ")}"', page_size=25)
    if isinstance(r, dict): errors["sleep"] = r
    else:
        for p in r:
            s = p.get("sleep", {}); iv = s.get("interval", {})
            endt = parse(iv["endTime"])
            k = endt.date().isoformat()
            if k in days:
                md = s.get("metadata", {})
                days[k].setdefault("sleep", []).append({
                    "start": sgt(parse(iv["startTime"])), "end": sgt(endt),
                    "main": bool(md.get("mainSleep")), "nap": bool(md.get("nap")),
                    "summary": num(s.get("summary"))})

    out = {"days": days}
    if errors: out["errors"] = errors
    print(json.dumps(out, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("auth"); d.add_argument("--manual", action="store_true"); d.set_defaults(f=cmd_auth)
    sub.add_parser("identity").set_defaults(f=cmd_identity)
    d = sub.add_parser("daily"); d.add_argument("--days", type=int, default=7); d.set_defaults(f=cmd_daily)
    d = sub.add_parser("sedentary"); d.add_argument("--minutes", type=int, default=int(CFG.get("window_minutes", 60)))
    d.add_argument("--threshold", type=int, default=int(CFG.get("threshold_steps", 250))); d.set_defaults(f=cmd_sedentary)
    d = sub.add_parser("hourly"); d.add_argument("--date"); d.set_defaults(f=cmd_hourly)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
