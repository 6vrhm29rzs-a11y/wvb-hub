#!/usr/bin/env python3
"""When the daily reports go out (Cody/coordination to-builder 009, review 010).

  mail_scheduler.py morning         run at 06:00 PT: one Morning Brief per date
  mail_scheduler.py night-check     run every 15 min, 17:00-21:15 PT
  mail_scheduler.py status          print today's state

Night rules:
  * wrap EARLY only on positive proof: a fresh, well-formed live feed that
    lists today's slate with every game final, AND every counted fixture in
    the logged dataset final (feed_problem / slate_status). An empty,
    missing, stale or malformed feed is never completion.
  * otherwise the FINAL attempt starts at 21:15 -- refresh capped at 6 min,
    then build and submit -- so the report is submitted by the 21:30 cutoff,
    listing what is still live or not logged. A refresh that fails or times
    out falls back to the last built page and the report says so. A day with
    no games gets a short digest.
  * one Night Desk per date.

Delivery state (Cody/data/mail_state.json, private) is named for what is
known: 'claimed' is persisted BEFORE a send, 'queued_in_outbox' while Mail
holds it, 'submitted' once it left the Outbox -- hand-off to the mail
server, NOT proof of inbox delivery or receipt. A file lock serializes runs,
and an in-flight record is reconciled (Outbox + send log) before any retry,
so a queued message is never sent twice. With the transport OFF, runs record
'not_sent_transport_off' and keep the report in Cody/data/unsent/.

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
DEADLINE = (21, 30)          # the report is submitted by this time
FINAL_START = (21, 15)       # the final attempt starts here: refresh <= 6 min + build/submit
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


REFRESH_TIMEOUT_S = 360


def refresh():
    """Bounded refresh. (ok, note). ⚠ REVIEW 010 FINDING 2: an unbounded refresh
    started at the deadline could not finish in time; now it is capped and a
    failure or timeout falls back, SAID IN THE REPORT, to the last built page."""
    try:
        r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "local_refresh.py")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=REFRESH_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, "refresh exceeded %d s; report uses the last built page" % REFRESH_TIMEOUT_S
    if r.returncode != 0:
        return False, "refresh failed (exit %d); report uses the last built page" % r.returncode
    return True, "data refreshed"


FEED_MAX_AGE_MIN = 10


def fetch_feed():
    """(payload or None, error). The live feed from live_server, raw."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8799/api/live", timeout=8) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception as e:
        return None, "live feed unreachable (%s)" % type(e).__name__


def feed_problem(feed, day, t):
    """Why this feed is NOT evidence of anything, or None when it is.

    ⚠ REVIEW 010 FINDING 1: an HTTP 200 with an empty or absent games list
    used to read as "nothing live", and the early wrap then trusted the local
    finals alone. Silence is not completion: the feed must be well-formed,
    fresh (its own 'updated' stamp within FEED_MAX_AGE_MIN), and must list
    today's slate."""
    if not isinstance(feed, dict):
        return "live feed malformed"
    if feed.get("error"):
        return "live feed reported an error: %s" % str(feed.get("error"))[:80]
    games = feed.get("games")
    if not isinstance(games, list):
        return "live feed has no games list"
    upd = feed.get("updated")
    try:
        hh = datetime.datetime.strptime(str(upd).replace(" PT", ""), "%I:%M:%S %p")
        stamp = t.replace(hour=hh.hour, minute=hh.minute, second=hh.second, microsecond=0)
        if stamp > t + datetime.timedelta(minutes=1):
            stamp -= datetime.timedelta(days=1)
        if (t - stamp) > datetime.timedelta(minutes=FEED_MAX_AGE_MIN):
            return "live feed stale (updated %s)" % upd
    except (TypeError, ValueError):
        return "live feed freshness unknown (updated=%r)" % (upd,)
    if not [g for g in games if isinstance(g, dict) and g.get("date") == day]:
        return "live feed lists no games for %s" % day
    return None


def slate_status(day, feed=None, t=None, games=None):
    """(complete, n_known, n_final, reason). Complete only on positive proof:
    a fresh, well-formed feed listing today's slate with every game final,
    AND every counted fixture in the logged dataset final. The two sources
    are unioned, so a game known to either one must be finished."""
    import season_counts as SC
    t = t or now()
    if games is None:
        doc = json.load(io.open(os.path.join(REPO, "data", "data_%d.json" % SEASON),
                                encoding="utf-8"))
        games = doc.get("games") or []
    todays = [g for g in games if g.get("start_time_epoch") and
              datetime.datetime.fromtimestamp(g["start_time_epoch"], PT).strftime("%Y-%m-%d") == day]
    cls = SC.classify(todays, SEASON) if todays else {}
    real = [g for g in todays if cls.get(str(g.get("game_id"))) not in ("duplicate", "exhibition")]
    logged_final = set(str(g["game_id"]) for g in real if g.get("state") == "F")
    logged_all = set(str(g["game_id"]) for g in real)
    if feed is None:
        feed, err = fetch_feed()
        if err:
            return False, len(logged_all), len(logged_final), err
    bad = feed_problem(feed, day, t)
    if bad:
        return False, len(logged_all), len(logged_final), bad
    fg = [g for g in feed["games"] if isinstance(g, dict) and g.get("date") == day]
    feed_ids = set(str(g.get("id")) for g in fg)
    not_final_feed = [g for g in fg if g.get("state") != "final"]
    known = logged_all | feed_ids
    if not_final_feed:
        return False, len(known), len(logged_final), "%d of today's games not final in the feed" % len(not_final_feed)
    missing = feed_ids - logged_final
    if missing:
        return False, len(known), len(logged_final), "%d final in the feed but not logged yet" % len(missing)
    if logged_all - logged_final:
        return False, len(known), len(logged_final), "%d logged fixtures not final" % len(logged_all - logged_final)
    return True, len(known), len(logged_final), "all %d final in the feed and logged" % len(known)


def variant():
    try:
        v = io.open(VARIANT_FILE, encoding="utf-8").read().strip().upper()
    except IOError:
        v = "A"
    # B (HTML) is a preview-only variant until an HTML send path is approved
    return "A" if v != "A" else v


def build(kind, day, note=""):
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "mail_report.py"),
                        kind, "--variant", variant(), "--day", day, "--status", note],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    body = r.stdout.decode("utf-8")
    if r.returncode != 0 or body.count("\n") < 12:
        raise RuntimeError("report build failed or looks empty: %s"
                           % r.stderr.decode("utf-8", "replace")[-300:])
    return body


def outbox_count(subject):
    script = ('tell application "Mail" to count (messages of outbox whose subject is "%s")'
              % subject.replace('"', ''))
    r = subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        return int(r.stdout.decode().strip()) if r.returncode == 0 else None
    except ValueError:
        return None


def wait_outbox(subject, wait=150):
    t0 = time.time()
    while time.time() - t0 < wait:
        if outbox_count(subject) == 0:
            return True
        time.sleep(10)
    return False


class Lock(object):
    """One scheduler run at a time (REVIEW 010 FINDING 3): the whole
    load -> check -> claim -> send -> save sequence is serialized."""
    def __enter__(self):
        import fcntl
        self.fh = open(STATE + ".lock", "w")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise SystemExit("another scheduler run holds the lock -- exiting")
        return self

    def __exit__(self, *a):
        import fcntl
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


# States, named for what is actually known (REVIEW 010 FINDING 3):
#   claimed               a send was about to be attempted; never resend blindly
#   queued_in_outbox      Mail accepted it and still holds it
#   submitted             Mail accepted it and it left the Outbox (handed to the
#                         server). NOT proof of inbox delivery or of receipt.
#   not_sent_transport_off / build_failed / send_refused   nothing left the Mac
DONE = ("submitted",)
IN_FLIGHT = ("claimed", "queued_in_outbox")


def reconcile(rec):
    """Resolve an in-flight record before any retry, so a message that later
    left the Outbox is never sent a second time."""
    if not rec or rec.get("status") not in IN_FLIGHT:
        return rec
    n = outbox_count(rec["subject"])
    if n and n > 0:
        rec["status"] = "queued_in_outbox"
    else:
        logged = False
        try:
            for line in io.open(os.path.join(REPO, "Cody", "data", "mail_log.jsonl"), encoding="utf-8"):
                if rec["subject"] in line:
                    logged = True
        except IOError:
            pass
        # accepted by the mailer and gone from the Outbox -> submitted;
        # never accepted -> the claim was abandoned before sending
        rec["status"] = "submitted" if logged else "claim_abandoned"
    rec["reconciled_at"] = now().isoformat(timespec="seconds")
    return rec


def deliver(kind, day, note, s, slot):
    import mailer
    title = "Night Desk" if kind == "night" else "Morning Brief"
    subject = "WVB Hub — %s — %s" % (title, day)
    rec = {"at": now().isoformat(timespec="seconds"), "subject": subject, "note": note}
    try:
        body = build(kind, day, note)
    except Exception as e:
        rec.update(status="build_failed", error=str(e)[:300])
        return rec
    if mailer.transport() == "off":
        os.makedirs(UNSENT, exist_ok=True)
        io.open(os.path.join(UNSENT, "%s-%s.txt" % (kind, day)), "w", encoding="utf-8").write(body)
        rec.update(status="not_sent_transport_off")
        return rec
    rec["status"] = "claimed"                     # persisted BEFORE the send
    slot[kind] = rec
    save_state(s)
    rc = mailer.send(subject, body)
    if rc != 0:
        rec.update(status="send_refused", rc=rc)
        return rec
    rec.update(status="submitted" if wait_outbox(subject) else "queued_in_outbox")
    return rec


def run_morning():
    with Lock():
        day = now().strftime("%Y-%m-%d")
        s = load_state()
        slot = s.setdefault(day, {})
        slot["morning"] = reconcile(slot.get("morning"))
        if (slot.get("morning") or {}).get("status") in DONE + IN_FLIGHT:
            save_state(s)
            log("morning %s already %s -- not sending again" % (day, slot["morning"]["status"]))
            return 0
        ok, rnote = refresh()
        slot["morning"] = deliver("morning", day, "06:00 run; " + rnote, s, slot)
        save_state(s)
        log("morning %s -> %s" % (day, slot["morning"]["status"]))
        return 0 if slot["morning"]["status"] in DONE + ("not_sent_transport_off",) else 1


def run_night_check():
    with Lock():
        t = now()
        day = t.strftime("%Y-%m-%d")
        s = load_state()
        slot = s.setdefault(day, {})
        slot["night"] = reconcile(slot.get("night"))
        if (slot.get("night") or {}).get("status") in DONE + IN_FLIGHT:
            save_state(s)
            log("night %s already %s -- not sending again" % (day, slot["night"]["status"]))
            return 0
        final = (t.hour, t.minute) >= FINAL_START
        ok, rnote = refresh()
        complete, n, nf, why = slate_status(day)
        if not final and not complete:
            save_state(s)
            log("night %s waiting: %s" % (day, why))
            return 0
        if not final and (slot.get("night") or {}).get("status") == "not_sent_transport_off":
            return 0
        note = (("early wrap: %s" % why) if (complete and not final)
                else ("deadline wrap (cutoff 21:30): %s" % why)) + "; " + rnote
        slot["night"] = deliver("night", day, note, s, slot)
        save_state(s)
        log("night %s -> %s (%s)" % (day, slot["night"]["status"], note))
        return 0 if slot["night"]["status"] in DONE + ("not_sent_transport_off",) else 1


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
