#!/usr/bin/env python3
"""When the daily reports go out (Cody/coordination to-builder 009).

  mail_scheduler.py morning         run at 06:00 PT: one Morning Brief per date
  mail_scheduler.py night-check     run every 15 min, 17:00-21:30 PT
  mail_scheduler.py status          print today's state

Night rules:
  * send EARLY only when today's slate is provably complete: at least one
    fixture today, every one of them FINAL in the logged dataset, none still
    listed as upcoming on the page, none live in the live feed. Feed silence
    or an empty fetch is NOT completion.
  * otherwise send at the 21:30 deadline, listing what is still live/pending.
    A day with no games gets a short digest at the deadline.
  * one Night Desk per date: an early delivery suppresses the deadline run.

Durable state lives in Cody/data/mail_state.json (private). A report is
marked "delivered" only after the mailer accepted it AND Mail's Outbox no
longer holds it -- never merely because a send was attempted. While the
mail transport is OFF, runs record "not sent (transport off)" and keep the
report in Cody/data/unsent/, and the slot stays open for a later run.

All calendar logic is America/Los_Angeles and DST-safe (zoneinfo).
Python 3.9 target.
"""
import datetime
import io
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
STATE = os.path.join(REPO, "Cody", "data", "mail_state.json")
UNSENT = os.path.join(REPO, "Cody", "data", "unsent")
LOG = os.path.expanduser("~/Library/Logs/wvb-mail.log")
DEADLINE = (21, 30)
VARIANT_FILE = os.path.join(REPO, "Cody", "data", "mail_variant.txt")

from zoneinfo import ZoneInfo  # noqa: E402
PT = ZoneInfo("America/Los_Angeles")


def now():
    return datetime.datetime.now(PT)


def log(msg):
    line = "%s  scheduler  %s" % (now().strftime("%Y-%m-%d %H:%M:%S %Z"), msg)
    print(line)
    try:
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except IOError:
        pass


def load_state():
    try:
        return json.load(io.open(STATE, encoding="utf-8"))
    except (IOError, ValueError):
        return {}


def save_state(s):
    tmp = STATE + ".tmp"
    json.dump(s, io.open(tmp, "w", encoding="utf-8"), indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def refresh():
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "local_refresh.py")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def slate_status(day):
    """(complete, n_fixtures, n_final, reason). Complete only on positive proof."""
    import season_counts as SC
    doc = json.load(io.open(os.path.join(REPO, "data", "data_%d.json" % SEASON),
                            encoding="utf-8"))
    todays = []
    for g in doc.get("games") or []:
        ep = g.get("start_time_epoch")
        if not ep:
            continue
        if datetime.datetime.fromtimestamp(ep, PT).strftime("%Y-%m-%d") == day:
            todays.append(g)
    # the dataset keeps withdrawn/duplicate listings; judge only what counts
    cls = SC.classify(todays, SEASON) if todays else {}
    real = [g for g in todays if cls.get(str(g.get("game_id"))) not in ("duplicate", "exhibition")]
    n = len(real)
    fin = [g for g in real if g.get("state") == "F"]
    if n == 0:
        return False, 0, 0, "no fixtures logged for today"
    live = []
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8799/api/live", timeout=5) as r:
            live = [x for x in (json.loads(r.read().decode("utf-8")).get("games") or [])
                    if x.get("state") == "live"]
    except Exception:
        return False, n, len(fin), "live feed unreachable -- cannot prove the slate is over"
    if live:
        return False, n, len(fin), "%d still live" % len(live)
    if len(fin) < n:
        return False, n, len(fin), "%d of %d final" % (len(fin), n)
    return True, n, len(fin), "all %d final and logged" % n


def variant():
    try:
        v = io.open(VARIANT_FILE, encoding="utf-8").read().strip().upper()
    except IOError:
        v = "A"
    # B (HTML) is a preview-only variant until an HTML send path is approved
    return "A" if v != "A" else v


def build(kind, day):
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "mail_report.py"),
                        kind, "--variant", variant(), "--day", day],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    body = r.stdout.decode("utf-8")
    if r.returncode != 0 or body.count("\n") < 12:
        raise RuntimeError("report build failed or looks empty: %s"
                           % r.stderr.decode("utf-8", "replace")[-300:])
    return body


def outbox_clear(subject, wait=150):
    script = ('tell application "Mail" to count (messages of outbox whose subject is "%s")'
              % subject.replace('"', ''))
    t0 = time.time()
    while time.time() - t0 < wait:
        r = subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode == 0 and r.stdout.decode().strip() == "0":
            return True
        time.sleep(10)
    return False


def deliver(kind, day, note):
    """Build, send, verify. Returns the state record."""
    import mailer
    title = "Night Desk" if kind == "night" else "Morning Brief"
    subject = "WVB Hub — %s — %s" % (title, day)
    rec = {"at": now().isoformat(timespec="seconds"), "subject": subject, "note": note}
    try:
        body = build(kind, day)
    except Exception as e:
        rec.update(status="build_failed", error=str(e)[:300])
        return rec
    if mailer.transport() == "off":
        os.makedirs(UNSENT, exist_ok=True)
        io.open(os.path.join(UNSENT, "%s-%s.txt" % (kind, day)), "w", encoding="utf-8").write(body)
        rec.update(status="not_sent_transport_off")
        return rec
    rc = mailer.send(subject, body)
    if rc != 0:
        rec.update(status="send_refused", rc=rc)
        return rec
    rec.update(status="delivered" if outbox_clear(subject) else "stuck_in_outbox")
    return rec


def run_morning():
    day = now().strftime("%Y-%m-%d")
    s = load_state()
    slot = s.setdefault(day, {})
    if (slot.get("morning") or {}).get("status") == "delivered":
        log("morning %s already delivered -- nothing to do" % day)
        return 0
    refresh()
    slot["morning"] = deliver("morning", day, "06:00 run")
    save_state(s)
    log("morning %s -> %s" % (day, slot["morning"]["status"]))
    return 0 if slot["morning"]["status"] in ("delivered", "not_sent_transport_off") else 1


def run_night_check():
    t = now()
    day = t.strftime("%Y-%m-%d")
    s = load_state()
    slot = s.setdefault(day, {})
    if (slot.get("night") or {}).get("status") == "delivered":
        log("night %s already delivered -- nothing to do" % day)
        return 0
    at_deadline = (t.hour, t.minute) >= DEADLINE
    refresh()
    complete, n, nf, why = slate_status(day)
    if not at_deadline and not complete:
        log("night %s waiting: %s" % (day, why))
        return 0
    if not at_deadline and (slot.get("night") or {}).get("status") == "not_sent_transport_off":
        return 0          # already built early today with sending off; wait for the deadline
    note = ("early: %s" % why) if complete and not at_deadline else ("deadline 21:30: %s" % why)
    slot["night"] = deliver("night", day, note)
    save_state(s)
    log("night %s -> %s (%s)" % (day, slot["night"]["status"], note))
    return 0 if slot["night"]["status"] in ("delivered", "not_sent_transport_off") else 1


if __name__ == "__main__":
    os.environ.setdefault("WVB_SEASON", str(SEASON))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "morning":
        sys.exit(run_morning())
    if cmd == "night-check":
        sys.exit(run_night_check())
    d = now().strftime("%Y-%m-%d")
    print(json.dumps({"today": d, "state": load_state().get(d),
                      "slate": slate_status(d)}, indent=1))
