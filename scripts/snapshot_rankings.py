#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weekly ranking snapshot -- a poll-style archive with movement.

Cody's ask (2026-08-23): a running ranking that updates constantly, PLUS a
saved history taken Monday mornings before each week's games, the way the AVCA
and VolleyTalk polls publish.

The running ranking is the page itself: it rebuilds nightly and, once 50 matches
have been played, comes from the in-season composite rather than the preseason
projection. This script is the OTHER half -- it freezes that ranking once a week
so movement can be shown and so there is a record of what we said BEFORE the
week's results, which is the only version of a ranking that can be scored later.

Rules, deliberate:
  * MONDAY ONLY by default. The daily job runs 09:15 UTC = 05:15 ET, before any
    match starts, so a Monday snapshot is genuinely pre-week. `--force` overrides
    for a manual capture.
  * ONE SNAPSHOT PER ISO WEEK. Re-running is a no-op, so the daily job can call
    it unconditionally without the archive growing a row a day.
  * APPEND-ONLY. A past week is never rewritten -- that is the whole point of an
    archive. If the model changes, the old rows stay as what we actually said.
  * It records `rank_source`, because a preseason rank and a results-based rank
    are different claims and the archive must not blur them.

Python 3.9 target.
"""

import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "rankings_history_%d.jsonl" % SEASON)


def load(path):
    p = os.path.join(REPO, path)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p))
    except ValueError:
        return None


def existing_weeks():
    weeks = set()
    if not os.path.exists(OUT):
        return weeks
    with open(OUT) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                weeks.add(json.loads(line)["week"])
            except (ValueError, KeyError):
                continue
    return weeks


def current_ranking():
    """Whatever the page is showing right now: live rating if one exists,
    otherwise the preseason projection. Same precedence as the board."""
    live = load("data/rating_%d.json" % SEASON) or {}
    rows = []
    for r in (live.get("teams") or []):
        if r.get("composite_rank"):
            rows.append({"team": r["team"], "rank": r["composite_rank"],
                         "source": "live", "gp": r.get("games_played"),
                         "record": ("%s-%s" % (r.get("wins"), r.get("losses"))
                                    if r.get("wins") is not None else None)})
    if rows:
        rows.sort(key=lambda x: x["rank"])
        return rows, "live"

    proj = load("data/projection_%d.json" % SEASON) or {}
    for r in (proj.get("teams") or []):
        if r.get("talent_rank"):
            rows.append({"team": r["team"], "rank": r["talent_rank"],
                         "source": "preseason", "gp": 0, "record": None})
    rows.sort(key=lambda x: x["rank"])
    return rows, "preseason"


def main():
    argv = sys.argv[1:]
    force = "--force" in argv

    today = datetime.date.today()
    iso = today.isocalendar()
    week = "%d-W%02d" % (iso[0], iso[1])

    if today.weekday() != 0 and not force:
        print("not Monday (%s) -- no snapshot. Use --force to capture anyway."
              % today.isoformat())
        return 0
    if week in existing_weeks():
        print("%s already captured -- nothing to do." % week)
        return 0

    rows, source = current_ranking()
    if not rows:
        print("no ranking available to snapshot")
        return 0

    rec = {
        "week": week,
        "date": today.isoformat(),
        "season": SEASON,
        "source": source,
        "source_tier": "DERIVED",
        "note": ("Frozen before the week's matches. Append-only: a past week is "
                 "never rewritten, so this records what we actually said at the "
                 "time, not what the current model would say about the past."),
        "teams": rows,
    }
    with open(OUT, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print("captured %s (%s): %d teams -> %s" % (week, source, len(rows), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
