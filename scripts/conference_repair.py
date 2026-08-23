#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repair a stale conference label from the team's own schedule.

WHY THIS EXISTS. ncaa.com still serves UT Arlington under `wac`. The WAC no
longer fields a D-I volleyball league -- it became the UAC -- so the label
leaves a one-team "conference" that would collect an automatic bid on its own.
The existing guard handled that by refusing a bid to any league under six
members, which is correct but is a *defence*, not an answer: the team ends up in
no real league at all.

THE ANSWER IS ALREADY IN THE FEED. A team's conference schedule is a round-robin
against its own league. UT Arlington plays 16 fixtures from Sept 20 onward and
**all sixteen** are against UAC teams, opening Sept 22 at Tarleton St. That is a
measurement, not an inference, and it self-populates for any future realignment
the label lags behind.

TWO CONDITIONS, NEITHER OF THEM A NUMBER I CHOSE:
  * **Unanimity.** Every late-season opponent is in the same conference. This is
    the absence of contrary evidence rather than a cutoff -- one opponent from
    another league and the repair does not fire.
  * **At least MIN_CONF fixtures**, reusing the constant the bid rule already
    uses for "enough D-I members to be a league". No new threshold is invented.

The mirrored `conferences_2026.json` is never rewritten -- it stays a faithful
record of what ncaa.com says. Corrections live in their own file, the same
separation `athletics_sites_overrides.json` already uses.

Python 3.9 target. Run: python3 scripts/conference_repair.py
"""

import collections
import glob
import json
import os
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data/raw/%d/conference_overrides.json" % SEASON)

# Conference play. Non-conference is front-loaded in August and early September;
# from here on a team plays its own league.
CONF_PLAY_FROM = "%d-09-20" % SEASON

# The same "enough D-I members to be a league" constant the bid rule uses.
MIN_CONF = 6


def opponents():
    # type: () -> Dict[str, List[Tuple[str, str]]]
    """team -> [(date, opponent), ...] from the cached scoreboard."""
    out = collections.defaultdict(list)
    pat = os.path.join(REPO, "data/raw/%d/scoreboard/*.json" % SEASON)
    for path in sorted(glob.glob(pat)):
        try:
            payload = json.load(open(path))
        except ValueError:
            continue
        date = os.path.basename(path)[:-5]
        for entry in payload.get("games") or []:
            g = entry.get("game", entry)
            a = (g.get("away") or {}).get("names", {}).get("short")
            h = (g.get("home") or {}).get("names", {}).get("short")
            if a and h:
                out[a].append((date, h))
                out[h].append((date, a))
    return out


def resolve(team, conf_of, opps):
    # type: (str, Dict[str, str], Dict[str, List[Tuple[str, str]]]) -> Optional[Dict]
    """The conference a team's own schedule says it is in, or None."""
    late = [o for d, o in opps.get(team, []) if d >= CONF_PLAY_FROM]
    seen = [conf_of.get(o) for o in late if conf_of.get(o)]
    if len(seen) < MIN_CONF:
        return None
    counts = collections.Counter(seen)
    if len(counts) != 1:                    # not unanimous -> no repair
        return None
    conference = list(counts)[0]
    if conference == conf_of.get(team):     # label already agrees
        return None
    return {"team": team, "from_label": conf_of.get(team), "conference": conference,
            "evidence": "%d of %d conference-play fixtures, all vs %s"
                        % (len(seen), len(late), conference),
            "first_fixture": sorted((d, o) for d, o in opps.get(team, [])
                                    if d >= CONF_PLAY_FROM)[:1],
            "source_tier": "DERIVED"}


def build():
    # type: () -> Dict
    conf26 = (json.load(open(os.path.join(
        REPO, "data/raw/%d/conferences_%d.json" % (SEASON, SEASON)),
        encoding="utf-8")) or {})
    conf_of = conf26.get("teams", {})
    opps = opponents()

    sizes = collections.Counter(v for v in conf_of.values() if v)
    # Only leagues too small to be leagues are candidates. A team in a healthy
    # conference is not re-adjudicated on the strength of its schedule.
    suspect = sorted(t for t, c in conf_of.items() if c and sizes[c] < MIN_CONF)

    fixed = []
    for team in suspect:
        r = resolve(team, conf_of, opps)
        if r:
            fixed.append(r)
    return {"meta": {"season": SEASON, "source_tier": "DERIVED",
                     "rule": ("a team in a league below %d members takes the "
                              "conference of its own schedule, but only when "
                              "every conference-play opponent agrees and there "
                              "are at least %d of them" % (MIN_CONF, MIN_CONF)),
                     "note": ("conferences_%d.json is NOT rewritten -- it stays "
                              "a faithful record of what ncaa.com serves"
                              % SEASON),
                     "candidates_examined": suspect},
            "overrides": dict((r["team"], r["conference"]) for r in fixed),
            "evidence": fixed}


def load_overrides():
    # type: () -> Dict[str, str]
    try:
        return (json.load(open(OUT, encoding="utf-8")) or {}).get("overrides") or {}
    except Exception:                                   # noqa: BLE001
        return {}


if __name__ == "__main__":
    doc = build()
    json.dump(doc, open(OUT, "w"), indent=1, sort_keys=True)
    print("examined %d team(s) in undersized leagues"
          % len(doc["meta"]["candidates_examined"]))
    for r in doc["evidence"]:
        print("  %-16s %s -> %s   (%s)"
              % (r["team"], r["from_label"], r["conference"], r["evidence"]))
    if not doc["evidence"]:
        print("  no repair fired")
    print("wrote %s" % OUT)
