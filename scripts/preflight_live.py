#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Game-day preflight: which upcoming match is worth probing, and when.

⚠ READ-ONLY, AND THAT IS THE POINT. This opens the committed game log and
prints. It writes nothing -- not raw data, not rankings, not snapshots, not
notes, not git. Asserted by scripts/test_gameday.py over this file's AST.

WHY IT EXISTS. `probe_live_boxscore.py` has to be pointed at a match that is
actually in progress, and picking one in the moment -- from 195 fixtures, in
Eastern, while the slate is running -- is exactly when a mistake is easy. This
picks in advance, in Pacific, with reasons.

    python3 scripts/preflight_live.py              # next slate
    python3 scripts/preflight_live.py --date 2026-08-28
    python3 scripts/preflight_live.py --top 5

Python 3.9 target.
"""

import argparse
import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weekly as WK  # noqa: E402

SEASON = int(os.environ.get("WVB_SEASON", "2026"))

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:                                          # pragma: no cover
    PT = None


def pt_str(epoch):
    if not epoch:
        return "time not set"
    dt = (datetime.datetime.fromtimestamp(int(epoch), PT) if PT
          else datetime.datetime.utcfromtimestamp(int(epoch)))
    return dt.strftime("%a %b %d, %-I:%M %p PT")


def load(path):
    p = os.path.join(REPO, path)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except ValueError:
        return None


def candidates(season=SEASON, on_date=None, now_epoch=None):
    """Upcoming Division-I fixtures, best probe candidates first.

    ⚠ RANKED BY WHAT MAKES A PROBE USEFUL, NOT BY WHAT IS INTERESTING. A probe
    needs a match that will definitely be played, that we hold context for, and
    that starts at a civilised hour so all four checkpoints can actually be
    observed. A ranked-versus-ranked thriller at 4am is a worse candidate than
    a dull one at 4pm.
    """
    now_epoch = now_epoch or int(datetime.datetime.now().timestamp())
    games = WK._load_games(os.path.join(REPO, "data", "raw", str(season),
                                        "games.jsonl"))
    di = WK.disposition(season)
    ranks = {}
    board = load("data/digby_top25_%d.json" % season) or {}
    for r in (board.get("all") or []):
        if r.get("team") and r.get("rank"):
            ranks[r["team"]] = r["rank"]

    rows = []
    for g in games:
        ep = g.get("start_time_epoch")
        if not ep or int(ep) < now_epoch:
            continue                                   # already started/past
        if g.get("game_state") == WK.FINAL:
            continue
        if di.get(str(g.get("game_id"))) == "source_withdrawn":
            continue                                   # the source pulled it
        teams = g.get("teams") or []
        if len(teams) != 2:
            continue
        # Division-I on BOTH sides: a probe should exercise the ordinary path.
        if not all(t.get("division") == 1 for t in teams):
            continue
        d = WK.et_date(ep)
        if on_date and d != on_date:
            continue
        away = next((t for t in teams if not t.get("is_home")), teams[0])
        home = next((t for t in teams if t.get("is_home")), teams[-1])
        an, hn = away.get("name_short"), home.get("name_short")
        pt_hour = (datetime.datetime.fromtimestamp(int(ep), PT).hour if PT
                   else datetime.datetime.utcfromtimestamp(int(ep)).hour)
        # ⚠ CONTEXT KNOWN means the hub already holds these teams, so a probe
        # can be checked against something. An unknown team is not a failure,
        # it just makes the observation harder to interpret.
        known = bool(an in ranks or hn in ranks)
        score = 0
        if 12 <= pt_hour <= 19:
            score += 40                                # watchable window
        elif 9 <= pt_hour <= 21:
            score += 20
        if known:
            score += 20
        if an in ranks and hn in ranks:
            score += 15                                # both rated
        best = min([ranks.get(an, 999), ranks.get(hn, 999)])
        score += max(0, 25 - best // 4)                # a rated side helps
        rows.append({
            "game_id": str(g.get("game_id")),
            "away": an, "home": hn,
            "away_rank": ranks.get(an), "home_rank": ranks.get(hn),
            "epoch": int(ep), "date_et": d,
            "when_pt": pt_str(ep), "pt_hour": pt_hour,
            "context_known": known,
            "link": "https://www.ncaa.com/game/%s" % g.get("game_id"),
            "score": score,
        })
    rows.sort(key=lambda r: (-r["score"], r["epoch"]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Eastern date, YYYY-MM-DD")
    ap.add_argument("--top", type=int, default=3)
    a = ap.parse_args()

    rows = candidates(on_date=a.date)
    if not rows:
        print("No upcoming Division-I fixture found%s."
              % (" on %s" % a.date if a.date else ""))
        print("Nothing to probe. This is a statement about the schedule, "
              "not a failure.")
        return 0

    first_date = rows[0]["date_et"]
    same_day = [r for r in rows if r["date_et"] == first_date]
    print("NEXT LIVE VALIDATION OPPORTUNITY")
    print("  %s Eastern -- %d Division-I fixtures on the slate\n"
          % (first_date, len(same_day)))
    print("Best probe candidates:\n")
    for i, r in enumerate(rows[:a.top], 1):
        rk = lambda v: ("#%d " % v) if v else ""       # noqa: E731
        print("  %d. %s%s at %s%s" % (i, rk(r["away_rank"]), r["away"],
                                      rk(r["home_rank"]), r["home"]))
        print("     %s" % r["when_pt"])
        print("     game id %s" % r["game_id"])
        print("     %s" % r["link"])
        print("     context already known: %s"
              % ("yes" % () if r["context_known"] else "no"))
        print()
    print("Then, with that game id:")
    print("  python3 scripts/probe_live_boxscore.py --id %s --checkpoint pre"
          % rows[0]["game_id"])
    print()
    print("⚠ Nothing about live team or player statistics is established yet.")
    print("  These four checkpoints are how that question gets answered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
