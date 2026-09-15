#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One row a day: what the board said, so "movers" has a yesterday.

Cody, 2026-09-13: "maybe in the rankings or somewhere for biggest movers up
or down that week or that day or after a win or loss."

⚠ THIS IS NOT THE ARCHIVE. data/rankings_history_*.jsonl is the append-only
WEEKLY freeze: one row per ISO week, written Mondays before play, never
rewritten, and it is the only record of what we said at the time. This file
is a convenience -- a daily carbon copy so the page can say "up six since
yesterday" -- and it may be deleted and rebuilt from nothing without losing
anything the archive holds. The two must never be confused, so they are
separate files with separate names and this docstring.

⚠ ONE ROW PER DAY, FIRST WRITE WINS. The board recomputes every refresh
cycle; if each cycle appended, "yesterday" would mean "twenty minutes ago"
by evening. The day's first write is the day's record.

Run: python3 scripts/snapshot_daily_ranks.py
"""

import datetime
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "rank_daily_%d.jsonl" % SEASON)


def today_pt():
    try:
        import zoneinfo
        return datetime.datetime.now(
            zoneinfo.ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:                                       # noqa: BLE001
        return (datetime.datetime.utcnow()
                - datetime.timedelta(hours=7)).date().isoformat()


def main():
    import build_rankings_board as BOARD

    day = today_pt()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                if json.loads(line).get("date") == day:
                    print("daily ranks: %s already recorded -- not rewritten"
                          % day)
                    return 0
            except ValueError:
                continue

    teams, _field, _un, _naq, meta = BOARD.build()
    ranks = {}
    for t in teams:
        if t.get("team") and t.get("rank26"):
            ranks[t["team"]] = t["rank26"]
    if len(ranks) < 300:
        raise SystemExit("only %d ranked teams -- refusing to record a "
                         "partial day" % len(ranks))
    row = {
        "date": day,
        "season": SEASON,
        "basis": (meta or {}).get("rank_source"),
        "stamp": (meta or {}).get("rank_stamp"),
        "recorded_utc": datetime.datetime.utcnow()
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "daily convenience copy; the weekly freeze in "
                "rankings_history is the archive",
        "n": len(ranks),
        "ranks": ranks,
    }
    with io.open(OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print("daily ranks: recorded %s on basis %s (%d teams)"
          % (day, row["basis"], len(ranks)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
