#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Season play-by-play -> each team's serving rotation.

    python3 scripts/build_rotations.py            # writes data/rotations_2025.json

INPUT is the NCAA's own play-by-play, which names the server on EVERY rally --
not only on aces, which is all ncaa.com's feed carries. We do not fetch
stats.ncaa.org (it 403s non-browser clients and the no-scrape hook blocks it);
the identical data is published as MIT-licensed CSVs by the ncaavolleyballr
author. The CSV is ~739 MB and is NOT committed. This output is.

A ROTATION IS CYCLIC. Two lineups that differ only in where the listing starts
are the same rotation, so each is canonicalised by rotating the alphabetically
first name to the front before counting. Without that, one rotation shows up as
six different ones and the modal answer is noise.

WHAT IS DELIBERATELY NOT CLAIMED:
  * The SERVING six is not the six on the court. A libero replaces a middle the
    moment she rotates to the back row -- which is where the serve is -- so
    middles frequently never serve and never appear. Slots held by a libero or
    DS are flagged, not filled in.
  * A set that does not resolve is dropped, never trimmed to fit.

Python 3.9 target. Standard library only.
"""

import collections
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rotations import derive_rotation, setter_rows, opposite_of   # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
CSV_PATH = os.path.join(REPO, "data/raw/%d/pbp/wvb_pbp_div1_%d.csv" % (SEASON, SEASON))
OUT = os.path.join(REPO, "data/rotations_%d.json" % SEASON)

# A team must show a rotation this often before it is called that team's
# rotation. Not a tuning knob: one appearance is one set, and a single set is a
# lineup, not a pattern.
MIN_SETS_FOR_MODAL = 2


def canonical(rot):
    # type: (List[str]) -> Tuple[str, ...]
    """Rotate the alphabetically-first name to the front. Cyclic order kept."""
    if not rot or any(r is None for r in rot):
        return tuple()
    i = rot.index(min(rot))
    return tuple(rot[i:] + rot[:i])


def stream_sets(path):
    # type: (str) -> Any
    """Yield ((contest, set, team), [servers in order]) without holding the file.

    GROUPED BY (contest, set), NOT by team. The two teams' events interleave --
    that is what a rally is -- so keying the group on the serving team starts a
    new group at every side-out. The first version did exactly that and turned
    ~5,000 matches into 639,239 fragments, of which 8 resolved. Both teams'
    serve orders are collected within one set and emitted together.

    739 MB never lands in memory: one set at a time.
    """
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        key = None
        by_team = collections.OrderedDict()             # type: Any
        for row in reader:
            k = (row.get("contestid") or "", row.get("set") or "")
            if k != key:
                for team, names in (by_team or {}).items():
                    if names:
                        yield (key[0], key[1], team), names
                key, by_team = k, collections.OrderedDict()
            if row.get("event") != "Serve":
                continue
            player = (row.get("player") or "").strip()
            if player:
                by_team.setdefault(row.get("team") or "", []).append(player)
        for team, names in (by_team or {}).items():
            if names and key:
                yield (key[0], key[1], team), names


def main():
    if not os.path.exists(CSV_PATH):
        print("no play-by-play at %s" % CSV_PATH)
        print("download it first (MIT, ncaavolleyballr):")
        print("  curl -L -o %s \\\n    %s" % (CSV_PATH,
              "https://media.githubusercontent.com/media/JeffreyRStevens/"
              "ncaavolleyballr/refs/heads/main/data-csv/wvb_pbp_div1_%d.csv" % SEASON))
        return 1

    per_team = collections.defaultdict(collections.Counter)
    subs_seen = collections.defaultdict(collections.Counter)
    methods = collections.Counter()
    stats = collections.Counter()

    for (contest, st, team), names in stream_sets(CSV_PATH):
        turns = []                                      # type: List[str]
        for n in names:
            if not turns or turns[-1] != n:
                turns.append(n)
        stats["set_teams"] += 1
        res = derive_rotation(turns)
        if not res["consistent"] or not res["complete"]:
            stats["unresolved"] += 1
            continue
        stats["resolved"] += 1
        methods[res.get("method") or "?"] += 1
        per_team[team][canonical(res["rotation"])] += 1
        for starter, subs in (res.get("subs") or {}).items():
            for sub in subs:
                if starter != "(unplaced)":
                    subs_seen[team][(starter, sub)] += 1

    teams = {}                                          # type: Dict[str, Any]
    for team, counter in per_team.items():
        rot, n = counter.most_common(1)[0]
        if not rot or n < MIN_SETS_FOR_MODAL:
            continue
        total = sum(counter.values())
        pairs = [{"starter": a, "sub": b, "sets": c}
                 for (a, b), c in subs_seen[team].most_common(8)]
        teams[team] = {
            "rotation": list(rot),
            "sets_with_this_rotation": n,
            "sets_resolved": total,
            "agreement": round(float(n) / total, 3),
            "distinct_rotations": len(counter),
            "substitutions": pairs,
        }

    doc = {
        "meta": {
            "season": SEASON,
            "source": ("NCAA play-by-play as published by the ncaavolleyballr "
                       "package (MIT). stats.ncaa.org is never fetched."),
            "source_tier": "OFFICIAL (third-party mirror)",
            "derivation": ("A team serves in rotation order by rule, so the "
                           "order its players take the serve IS the rotation. "
                           "Nothing is inferred and no threshold is chosen."),
            "caveat": ("This is the SERVING six, not the six on court: a libero "
                       "replaces a middle when that middle rotates to the back "
                       "row, which is where the serve is, so middles often never "
                       "appear."),
            "set_teams_seen": stats["set_teams"],
            "resolved": stats["resolved"],
            "unresolved": stats["unresolved"],
            "resolved_pct": round(100.0 * stats["resolved"] /
                                  max(stats["set_teams"], 1), 1),
            "method_positional": methods.get("positional", 0),
            "method_successor_recovered": methods.get("successor", 0),
            "min_sets_for_modal": MIN_SETS_FOR_MODAL,
        },
        "teams": teams,
    }
    json.dump(doc, open(OUT, "w"), indent=1, sort_keys=True)
    m = doc["meta"]
    print("set-teams seen      : %d" % m["set_teams_seen"])
    print("  resolved          : %d  (%.1f%%)" % (m["resolved"], m["resolved_pct"]))
    print("    positional      : %d" % m["method_positional"])
    print("    successor-recov : %d" % m["method_successor_recovered"])
    print("  unresolved        : %d" % m["unresolved"])
    print("teams with a modal rotation: %d" % len(teams))
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
