#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Freeze the Conference Lab payload on the ballot cutoff, append-only.

Same cadence contract as snapshot_rankings.py: the job runs daily but a row
is written only on MONDAY (Pacific) -- results through Sunday night, the
same cutoff the AVCA/VolleyTalk ballot work uses -- and only once per ISO
week. A past week is never rewritten: re-deriving it later from data that
includes newer results would be a different claim wearing the same date.

Each row records the POWER basis its ranks were computed on, because the
movement view may only compare rows on ONE basis (the same-basis rule the
rankings archive already enforces). Until two comparable rows exist the
page says so instead of faking movement.

Run: python3 scripts/snapshot_conferences.py [--force]
"""

import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
SRC = os.path.join(REPO, "data", "conference_lab_%d.json" % SEASON)
OUT = os.path.join(REPO, "data", "conference_snapshots_%d.jsonl" % SEASON)

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:                                      # noqa: BLE001
    PT = None


def main():
    force = "--force" in sys.argv
    now = datetime.datetime.now(PT) if PT else datetime.datetime.utcnow()
    if now.weekday() != 0 and not force:
        print("not Monday PT -- the conference snapshot freezes on the "
              "ballot cutoff only (results through Sunday). Nothing written.")
        return 0
    if not os.path.exists(SRC):
        print("no %s -- run build_hub.py first" % SRC)
        return 1
    doc = json.load(open(SRC, encoding="utf-8"))
    week = "%d-W%02d" % now.isocalendar()[:2]
    if os.path.exists(OUT):
        for ln in open(OUT, encoding="utf-8"):
            try:
                if json.loads(ln).get("week") == week:
                    print("week %s already frozen -- append-only, refusing "
                          "to rewrite" % week)
                    return 0
            except ValueError:
                continue
    # the POWER basis travels with the row, same rule as the rankings archive
    from snapshot_rankings import current_ranking, basis
    try:
        _, src_name = current_ranking()
        pbasis = basis(src_name)
    except Exception:                                  # noqa: BLE001
        pbasis = "unknown"
    row = {
        "week": week,
        "frozen_utc": datetime.datetime.utcnow().replace(
            microsecond=0).isoformat() + "Z",
        "power_basis": pbasis,
        "meta": doc.get("meta"),
        "confs": doc.get("confs"),
        # the matrix is rebuilt from raw data at any time; the per-week
        # claim worth freezing is the summary table, not 200 game rows
    }
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    print("froze %s (basis %s, %d conferences)"
          % (week, pbasis, len(row["confs"] or [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
