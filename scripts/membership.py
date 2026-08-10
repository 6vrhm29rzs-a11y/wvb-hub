#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Who is Division I? Resolved differently for a finished season vs a live one.

*** THIS REFINES THE EARLIER RULE, WHICH WAS TOO BROAD. ***

CLAUDE.md previously said "never trust /game/{id}'s `division` field, always use
the RPI table." That is right for a FINISHED season and wrong for a LIVE one.
The field reports the team's CURRENT division. Read retroactively it is wrong --
Saint Francis (PA) played 2025 in D-I but is served as div3 today, which cost us
18 teams. Read DURING the season it describes, it is correct and current.

Measured 2026-08-10 on a real 2026 fixture (game 6625058, seasonYear 2026,
gameState P): Norfolk St. division=1, Bowie St. division=2. Correctly flagged,
before a single point has been played.

That matters because in August 2026 there IS NO 2026 RPI TABLE -- RPI needs
games first, and the rankings endpoint cannot be season-pinned, so it will keep
serving the 2025 final table until the NCAA publishes a 2026 one. Using that as
2026 membership would be stale in known ways (Saint Francis has left D-I;
reclassifiers become eligible on their own timetables).

PRECEDENCE, in order:
  1. ARCHIVED  an rpi_official.json captured during the season in question.
               Authoritative; this is what 2025 uses.
  2. LIVE      division == 1 observed in that season's own game log. Correct for
               the season being played, needs no external table, and degrades
               gracefully on day one.
Both are reported with a source label so the dashboard and logs can say which
one is in force rather than pretending they are the same thing.

Python 3.9 target.
"""

import json
import os
import sys
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm  # noqa: E402


def from_archived_rpi(raw_dir):
    # type: (str) -> Optional[Tuple[Set[str], Dict[str, dict]]]
    path = os.path.join(raw_dir, "rpi_official.json")
    if not os.path.exists(path):
        return None
    try:
        rows = json.load(open(path))["data"]
    except Exception:
        return None
    if not rows:
        return None
    return (set(norm(r["School"]) for r in rows),
            {norm(r["School"]): r for r in rows})


def from_game_log(games):
    # type: (List[dict]) -> Set[str]
    """Teams observed at division == 1 in this season's own games."""
    out = set()
    for g in games:
        for t in (g.get("teams") or []):
            if t.get("division") == 1 and t.get("name_short"):
                out.add(norm(t["name_short"]))
    return out


def resolve(raw_dir, games):
    # type: (str, List[dict]) -> Tuple[Set[str], Dict[str, dict], str]
    """Returns (di_keys, official_rows_by_key, source_label)."""
    arch = from_archived_rpi(raw_dir)
    if arch:
        keys, rows = arch
        return keys, rows, "OFFICIAL archived RPI table (%d teams)" % len(keys)
    keys = from_game_log(games)
    return keys, {}, ("DERIVED from live division flags (%d teams) -- no RPI "
                      "table for this season yet" % len(keys))
