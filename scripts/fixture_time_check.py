#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does the NCAA feed agree with the SCHOOLS about when a match starts?

Cody, 2026-09-13, watching Purdue-SMU: "NCAA site shows Purdue/SMU starting
at 3pm pacific, but it's already going." Checked at that moment, the feed
said the match had not started and listed 18:00 ET. Purdue's own site listed
21:00Z -- 2:00 PM PT -- which is when it actually began. The feed was an hour
wrong, and every live surface here reads the feed, so nothing of ours could
show the match he was watching.

This is the check that catches that class BEFORE he notices: for every
upcoming fixture, ask the school's own platform when IT thinks the match
starts, and report the disagreements.

⚠ IT FLAGS, IT NEVER CORRECTS. data/raw/2026/fixture_corrections.json is
hand-curated and evidence-bearing, and this file writes CANDIDATES only --
the same discipline the duplicate-listing detector follows, for the same
reason: a machine that both nominates and decides has no second witness.

⚠ ONE REQUEST PER SCHOOL PER RUN. Sport ids are cached to disk, so a school
whose id is known costs a single events fetch. Per-host serialisation is the
verifier's own _host_lock.

Run: python3 scripts/fixture_time_check.py [--days 3] [--limit N]
"""

import datetime
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "fixture_time_check_%d.json" % SEASON)
IDS = os.path.join(REPO, "data", "raw", str(SEASON), "wmt_sport_ids.json")

# A disagreement under this is scheduling noise (a school rounding a 7:00 to
# 7:05, a feed storing the doors time). Stated, not fitted, and it feeds
# nothing but the display.
# ---- TIMESTAMP PARSING -------------------------------------------------
# WARN: `dt[:19]` + `replace(tzinfo=utc)` DISCARDED THE OFFSET AND THEN
# ASSUMED UTC (found by Codex review, 2026-09-13). It happens to be right for
# every host measured -- 36 of 36 samples across 18 schools return
# `2026-11-21T01:00:00.000000Z` -- but a host emitting `...T20:00:00-05:00`
# would have been read as 20:00 UTC and produced a FIVE-HOUR false
# disagreement. This module's whole job is to flag disagreements; one it
# manufactures itself is the worst output it can produce.
#
# THE SOURCE CONTRACT, measured rather than assumed: this platform emits an
# explicit zone, and every observed value is `Z`. So:
#   * `Z` and any explicit `+HH:MM` / `+HHMM` offset are honoured exactly;
#   * a TIMEZONE-NAIVE value is OFF-CONTRACT and returns None -- it is
#     counted as unresolved and the fixture is skipped, never guessed into a
#     zone. Guessing is how a false flag gets made.
_TZ_TAIL = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


def parse_dt(text):
    """An ISO-8601 instant -> aware datetime, or None if it carries no zone.

    Handles `Z`, `+HH:MM`, `+HHMM` and fractional seconds. Returns None for a
    naive value rather than assuming one, and None for anything unparseable.
    """
    t = (text or "").strip()
    if not t:
        return None
    m = _TZ_TAIL.search(t)
    if not m:
        return None                      # naive: off-contract, unresolved
    tail = m.group(0)
    body = t[:m.start()]
    if tail == "Z":
        tail = "+00:00"
    elif ":" not in tail:
        tail = tail[:3] + ":" + tail[3:]
    # 3.9's fromisoformat takes 3- or 6-digit fractions only
    if "." in body:
        head, frac = body.split(".", 1)
        frac = (frac + "000000")[:6]
        body = head + "." + frac
    try:
        return datetime.datetime.fromisoformat(body + tail)
    except ValueError:
        return None


# ---- SCHOOL SCHEDULE TEXT PAGES (B020, approved by Cody 2026-09-26) ------
# ⚠ THE CHECK ASKED ONLY ~30 OF 350 SCHOOLS. It read nothing but the WMT
# JSON API, and 320 schools are negative-cached as having none -- so a
# Creighton-at-St.-John's fixture listed two hours early (feed 2 PM PT;
# Creighton "6:00 PM CT", St. John's "7 p.m.", actual first serve 7:03 PM ET)
# was never asked about, and "0 disagreements" read as agreement. The
# SIDEARM /schedule/text page the result verifier already parses carries a
# Time column; this reads it.
#
# A clock with an explicit zone ("6:00 PM CT") is honoured exactly. A naive
# clock ("7 p.m.") is read in the school's HOME zone only when its home
# state lies in exactly one zone; anything else is counted unresolved,
# never guessed -- a false flag is the worst thing this file can emit.
_ZONE_NAMES = {"ET": "America/New_York", "CT": "America/Chicago",
               "MT": "America/Denver", "PT": "America/Los_Angeles",
               "HT": "Pacific/Honolulu", "AKT": "America/Anchorage"}
_ZONE_FIXED = {"EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6,
               "MST": -7, "PDT": -7, "PST": -8, "HST": -10}
# states wholly inside one zone (split states -- FL, IN, KY, TN, TX, KS, NE,
# ND, SD, ID, OR, MI -- are deliberately absent)
_STATE_ZONE = {}
for _z, _sts in (
        ("America/New_York", "CT DE DC GA ME MD MA NH NJ NY NC OH PA RI SC VT "
                             "VA WV"),
        ("America/Chicago", "AL AR IL IA LA MN MS MO OK WI"),
        ("America/Denver", "CO MT NM UT WY"),
        ("America/Phoenix", "AZ"),
        ("America/Los_Angeles", "CA NV WA"),
        ("Pacific/Honolulu", "HI")):
    for _st in _sts.split():
        _STATE_ZONE[_st] = _z

_CLOCK = re.compile(
    r"^\s*(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>a\.?\s*m\.?|p\.?\s*m\.?)"
    r"\s*(?P<z>[A-Z]{2,4})?\b", re.I)


def parse_clock(text):
    """'6:00 PM CT' -> (18, 0, 'CT'); '7 p.m.' -> (19, 0, None); 'Noon' ->
    (12, 0, None); TBA/TBD/blank/anything else -> None."""
    t = (text or "").strip()
    if re.match(r"^noon\b", t, re.I):
        z = re.search(r"\b([A-Z]{2,4})\b", t[4:])
        return (12, 0, z.group(1).upper() if z else None)
    m = _CLOCK.match(t)
    if not m:
        return None
    h = int(m.group("h")) % 12
    if m.group("ap").lower().startswith("p"):
        h += 12
    z = (m.group("z") or "").upper() or None
    if z and z not in _ZONE_NAMES and z not in _ZONE_FIXED:
        z = None
    return (h, int(m.group("m") or 0), z)


def local_instant(date, clock, home_state):
    """(ISO date, parse_clock tuple, state) -> aware UTC datetime, or
    (None, reason)."""
    import zoneinfo
    h, mi, z = clock
    y, mo, d = (int(x) for x in date.split("-"))
    if z in _ZONE_FIXED:
        tz = datetime.timezone(datetime.timedelta(hours=_ZONE_FIXED[z]))
    elif z in _ZONE_NAMES:
        tz = zoneinfo.ZoneInfo(_ZONE_NAMES[z])
    elif home_state in _STATE_ZONE:
        tz = zoneinfo.ZoneInfo(_STATE_ZONE[home_state])
    else:
        return None, "naive_time_zone_unknown"
    return (datetime.datetime(y, mo, d, h, mi, tzinfo=tz)
            .astimezone(datetime.timezone.utc), None)


def home_states():
    """team_id -> USPS state of its derived home venue (venues_2026.json)."""
    try:
        v = json.load(io.open(os.path.join(REPO, "data", "venues_%d.json"
                                           % SEASON), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for tid, venue in (v.get("home_venues") or {}).items():
        m = re.search(r",\s*([A-Z]{2})\s*$", venue or "")
        if m:
            out[str(tid)] = m.group(1)
    return out


def text_rows(V, base, school, state, unresolved):
    """A school's SIDEARM /schedule/text rows as {epoch, opp, url}, or None
    if no text surface parsed."""
    for path in V.SPORT_PATHS:
        url = base + path
        with V._host_lock(base):
            st, body, fu = V._fetch(url)
        if st != 200 or not body:
            continue
        rows = V.parse_schedule_text(body)
        if not rows:
            continue
        out = []
        for r in rows:
            raw = r.get("raw") or []
            clock = parse_clock(raw[1]) if len(raw) > 1 else None
            if clock is None:
                continue                 # TBA / no time: nothing to compare
            when, why = local_instant(r["date"], clock, state)
            if when is None:
                unresolved.append({"school": school, "datetime":
                                   "%s %s" % (r["date"], raw[1]),
                                   "opp": r["opponent"], "why": why})
                continue
            out.append({"epoch": when.timestamp(), "opp": r["opponent"],
                        "url": fu or url, "published": raw[1]})
        return out
    return None


TOLERANCE_MIN = 15
LOOKBACK_S = 12 * 3600


def load_ids():
    try:
        return json.load(io.open(IDS, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_ids(d):
    try:
        os.makedirs(os.path.dirname(IDS), exist_ok=True)
        json.dump(d, io.open(IDS, "w", encoding="utf-8"), indent=1,
                  sort_keys=True)
    except OSError:
        pass


def main():
    import verify_results_daily as V
    import gamelog
    import season_counts as SC

    days = 3
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    now = datetime.datetime.now(datetime.timezone.utc)
    until = now + datetime.timedelta(days=days)
    games = gamelog.load_games_jsonl(
        os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON))
    dup = __import__("dupes").duplicate_gids(SEASON)

    fixtures = []
    for g in SC.resolve(games):
        if (g.get("game_state") or "") == "F":
            continue
        gid = str(g.get("game_id"))
        if gid in dup:
            continue
        ep = g.get("start_time_epoch") or 0
        # ⚠ A FIXTURE WHOSE (POSSIBLY WRONG) FEED TIME HAS PASSED IS STILL
        # CHECKED while it is not final: an early feed time is exactly the
        # error this looks for, and dropping the match the moment that wrong
        # time went by hid it (Creighton at St. John's, 2026-09-26).
        if not (now.timestamp() - LOOKBACK_S <= ep <= until.timestamp()):
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        names = [t.get("name_short") for t in ts]
        if not all(names):
            continue
        home = next((t.get("name_short") for t in ts if t.get("is_home")),
                    names[1])
        away = next((n for n in names if n != home), names[0])
        tids = {t.get("name_short"): str(t.get("team_id")) for t in ts}
        fixtures.append({"gid": gid, "epoch": ep, "home": home, "away": away,
                         "tid": tids})
    fixtures.sort(key=lambda f: f["epoch"])
    print("upcoming fixtures in the next %d days: %d" % (days, len(fixtures)))

    sites = V._sites()
    ids = load_ids()
    # ⚠ ASK THE HOME SCHOOL FIRST: it owns the start time. Only if its site
    # cannot be read is the visitor asked, and the row records WHICH school
    # answered, because "the school says" means nothing without naming it.
    by_school = {}
    for f in fixtures:
        for side in ("home", "away"):
            by_school.setdefault(f[side], []).append((f, side))
    schools = [s for s in by_school if sites.get(s)]
    if limit:
        schools = schools[:limit]
    print("schools to ask: %d" % len(schools))

    events = {}
    sources = {}
    states = home_states()
    tid_of = {}
    for f in fixtures:
        tid_of.update(f["tid"])
    # rows whose timestamp carried no zone, or would not parse.
    # Counted and reported so coverage is stated rather than
    # silently reduced -- a run that read nothing must not look
    # like a run that found nothing.
    unresolved = []
    import threading
    asked = []
    def one(s):
            base = sites.get(s)
            log = []
            sid = ids.get(s)
            if sid is None:
                sid = V.wmt_sport_id(base, log)
                ids[s] = sid if sid is not None else 0
            if not sid:
                # no WMT API: the SIDEARM text schedule, which carries a clock
                asked.append(s)
                rows = text_rows(V, base, s, states.get(tid_of.get(s)),
                                 unresolved)
                if rows is not None:
                    events[s] = rows
                    sources[s] = "schedule_text"
                return
            url = (base + "/website-api/schedule-events?filter%5Bschedule.sport_id"
                   "%5D=" + str(sid) + "&per_page=60&sort=-datetime"
                   "&include=opponent")
            with V._host_lock(base):
                st, body, _fu = V._fetch(url)
            asked.append(s)
            if st != 200 or not body:
                return
            try:
                doc = json.loads(body)
            except ValueError:
                return
            rows = []
            for r in (doc.get("data") or []):
                dt = r.get("datetime")
                opp = (r.get("opponent_name")
                       or (r.get("opponent") or {}).get("name") or "").strip()
                if not dt or not opp:
                    return
                when = parse_dt(dt)
                if when is None:
                    # off-contract or unparseable: counted, never guessed
                    unresolved.append({"school": s, "datetime": dt, "opp": opp})
                    return
                rows.append({"epoch": when.timestamp(),
                             "opp": opp, "url": base + "/schedule"})
            events[s] = rows
            sources[s] = "wmt_api"
    # ⚠ PARALLEL ACROSS SCHOOLS, SERIAL PER HOST (the verifier's _host_lock):
    # asking ~200 schools one at a time took minutes, and this runs in the
    # 20-minute local refresh and the half-hourly CI job.
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(one, schools))
    asked = len(asked)
    save_ids(ids)
    print("asked %d schools, %d answered with events" % (asked, len(events)))

    def match(rows, opp, ep):
        """The school's row for this fixture: same opponent, same day."""
        want = V.team_norm(opp)
        wantl = V.loose_key(opp)
        day = datetime.datetime.fromtimestamp(
            ep, datetime.timezone.utc).date()
        best = None
        for r in rows:
            rday = datetime.datetime.fromtimestamp(
                r["epoch"], datetime.timezone.utc).date()
            if abs((rday - day).days) > 1:
                continue
            if V.team_norm(r["opp"]) == want or (
                    wantl and V._loose_hub_count(wantl) == 1
                    and V.loose_key(r["opp"]) == wantl):
                if best is None or abs(r["epoch"] - ep) < abs(best["epoch"] - ep):
                    best = r
        return best

    out = []
    # ⚠ A FIXTURE NO SCHOOL ANSWERED FOR IS UNKNOWN, NEVER AGREEMENT. Every
    # fixture ends in exactly one status, and the counts are published so
    # "0 disagreements" can be read against how much was actually checked.
    status = {}
    for f in fixtures:
        st = "no_reader"
        for side, other in (("home", "away"), ("away", "home")):
            school = f[side]
            rows = events.get(school)
            if rows is None:
                if sites.get(school) and school in schools:
                    st = st if st != "no_reader" else "fetch_failed"
                continue
            if not rows:
                st = "no_match" if st in ("no_reader", "fetch_failed") else st
                continue
            m = match(rows, f[other], f["epoch"])
            if not m:
                st = "no_match" if st in ("no_reader", "fetch_failed") else st
                continue
            diff = (m["epoch"] - f["epoch"]) / 60.0
            if abs(diff) < TOLERANCE_MIN:
                st = "agree"
                break
            st = "disagree"
            out.append({
                "gid": f["gid"], "home": f["home"], "away": f["away"],
                "school_asked": school,
                "feed_epoch": f["epoch"], "school_epoch": m["epoch"],
                "minutes_apart": round(diff),
                "school_url": m["url"],
                "school_source": sources.get(school),
                "school_published": m.get("published"),
                "claim": "the NCAA feed and this school's own schedule "
                         "disagree about when this match starts; neither is "
                         "corrected here",
            })
            break
        status[f["gid"]] = st
    out.sort(key=lambda r: -abs(r["minutes_apart"]))
    doc = {
        "season": SEASON,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "fixtures_checked": len(fixtures),
        "schools_answered": len(events),
        "timestamps_unresolved": len(unresolved),
        "timestamps_unresolved_sample": unresolved[:5],
        "tolerance_minutes": TOLERANCE_MIN,
        "what_this_is": "Fixtures where the feed's start time and the "
                        "school's own published start time differ by more "
                        "than the tolerance.",
        "what_this_is_not": "Not a correction. The hand-curated fixture "
                            "ledger is the only thing that overrides a "
                            "displayed time, and it needs a citation.",
        "lookback_hours": LOOKBACK_S // 3600,
        "sources": {k: sum(1 for v in sources.values() if v == k)
                    for k in ("wmt_api", "schedule_text")},
        "status_counts": {k: sum(1 for v in status.values() if v == k)
                          for k in ("agree", "disagree", "no_match",
                                    "fetch_failed", "no_reader")},
        "unknown_is_not_agreement": "no_match / fetch_failed / no_reader "
                                    "fixtures were NOT checked.",
        "n": len(out),
        "disagreements": out,
    }
    json.dump(doc, io.open(OUT, "w", encoding="utf-8"), indent=1)
    print("wrote %s" % OUT)
    import zoneinfo
    pt = zoneinfo.ZoneInfo("America/Los_Angeles")
    print("\n%d disagreement(s) over %d minutes:" % (len(out), TOLERANCE_MIN))
    for r in out[:20]:
        fe = datetime.datetime.fromtimestamp(r["feed_epoch"], pt)
        se = datetime.datetime.fromtimestamp(r["school_epoch"], pt)
        print("  %-18s v %-18s feed %s | %s says %s  (%+d min)"
              % (r["away"][:18], r["home"][:18],
                 fe.strftime("%a %I:%M %p"), r["school_asked"][:12],
                 se.strftime("%a %I:%M %p"), r["minutes_apart"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
