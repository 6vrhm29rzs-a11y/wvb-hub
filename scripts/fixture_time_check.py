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
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "fixture_time_check_%d.json" % SEASON)
IDS = os.path.join(REPO, "data", "raw", str(SEASON), "wmt_sport_ids.json")

# A disagreement under this is scheduling noise (a school rounding a 7:00 to
# 7:05, a feed storing the doors time). Stated, not fitted, and it feeds
# nothing but the display.
TOLERANCE_MIN = 15


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
        if not (now.timestamp() <= ep <= until.timestamp()):
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
        fixtures.append({"gid": gid, "epoch": ep, "home": home, "away": away})
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
    asked = 0
    for s in schools:
        base = sites.get(s)
        log = []
        sid = ids.get(s)
        if sid is None:
            sid = V.wmt_sport_id(base, log)
            ids[s] = sid if sid is not None else 0
        if not sid:
            continue
        url = (base + "/website-api/schedule-events?filter%5Bschedule.sport_id"
               "%5D=" + str(sid) + "&per_page=60&sort=-datetime"
               "&include=opponent")
        with V._host_lock(base):
            st, body, _fu = V._fetch(url)
        asked += 1
        if st != 200 or not body:
            continue
        try:
            doc = json.loads(body)
        except ValueError:
            continue
        rows = []
        for r in (doc.get("data") or []):
            dt = r.get("datetime")
            opp = (r.get("opponent_name")
                   or (r.get("opponent") or {}).get("name") or "").strip()
            if not dt or not opp:
                continue
            try:
                when = datetime.datetime.strptime(dt[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
            rows.append({"epoch": when.replace(
                tzinfo=datetime.timezone.utc).timestamp(),
                "opp": opp, "url": base + "/schedule"})
        events[s] = rows
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
    for f in fixtures:
        for side, other in (("home", "away"), ("away", "home")):
            school = f[side]
            rows = events.get(school)
            if not rows:
                continue
            m = match(rows, f[other], f["epoch"])
            if not m:
                continue
            diff = (m["epoch"] - f["epoch"]) / 60.0
            if abs(diff) < TOLERANCE_MIN:
                break
            out.append({
                "gid": f["gid"], "home": f["home"], "away": f["away"],
                "school_asked": school,
                "feed_epoch": f["epoch"], "school_epoch": m["epoch"],
                "minutes_apart": round(diff),
                "school_url": m["url"],
                "claim": "the NCAA feed and this school's own schedule "
                         "disagree about when this match starts; neither is "
                         "corrected here",
            })
            break
    out.sort(key=lambda r: -abs(r["minutes_apart"]))
    doc = {
        "season": SEASON,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "fixtures_checked": len(fixtures),
        "schools_answered": len(events),
        "tolerance_minutes": TOLERANCE_MIN,
        "what_this_is": "Fixtures where the feed's start time and the "
                        "school's own published start time differ by more "
                        "than the tolerance.",
        "what_this_is_not": "Not a correction. The hand-curated fixture "
                            "ledger is the only thing that overrides a "
                            "displayed time, and it needs a citation.",
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
