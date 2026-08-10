#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 4: reconcile the derived 2025 game graph against official ncaa.com records.

The question this answers is NOT "did the crawler run" but "is the game graph
COMPLETE". RPI Factor II needs every opponent's full record and Factor III needs
every opponent's opponents' records, so a hole anywhere in the graph produces a
silently wrong SOS with no natural reconciliation target. Deriving each team's
W-L from the game log and diffing it against the official record is the check
that catches those holes.

Reconciliation target: the official RPI table (348 teams, includes reclassifying
programs). The stat leaderboards are NOT usable here -- they carry only 343
teams, excluding reclassifiers.

Python 3.9 target.
"""

import json
import os
import re
import sys
import collections
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "data", "raw", "2025")
GAMES_JSONL = os.path.join(RAW, "games.jsonl")
RPI_JSON = os.path.join(RAW, "rpi_official.json")
OUT = os.path.join(RAW, "reconcile_report.json")

# ncaa.com abbreviates school names inconsistently across endpoints, and at
# least one 2025 rebrand (New Orleans -> LSU New Orleans) means names are not a
# safe join key. Normalization gets most of the way; this map covers the rest.
ALIASES = {
    "new orleans": "lsu new orleans",
}

ABBREV = [
    (r"\bst\.\b", "state"), (r"\bga\.\b", "georgia"), (r"\bfla\.\b", "florida"),
    (r"\bcalif\.\b", "california"), (r"\bcaro\.\b", "carolina"),
    (r"\bmich\.\b", "michigan"), (r"\bminn\.\b", "minnesota"),
    (r"\bmiss\.\b", "mississippi"), (r"\btenn\.\b", "tennessee"),
    (r"\bky\.\b", "kentucky"), (r"\bla\.\b", "louisiana"),
    (r"\bcolo\.\b", "colorado"), (r"\bwash\.\b", "washington"),
    (r"\bore\.\b", "oregon"), (r"\bariz\.\b", "arizona"),
    (r"\btex\.\b", "texas"), (r"\bokla\.\b", "oklahoma"),
    (r"\bill\.\b", "illinois"), (r"\bind\.\b", "indiana"),
    (r"\bconn\.\b", "connecticut"), (r"\bmass\.\b", "massachusetts"),
    (r"\bpa\.\b", "pennsylvania"), (r"\bva\.\b", "virginia"),
    (r"\bwis\.\b", "wisconsin"), (r"\bneb\.\b", "nebraska"),
    (r"\bark\.\b", "arkansas"), (r"\bala\.\b", "alabama"),
    (r"\bmd\.\b", "maryland"), (r"\bmo\.\b", "missouri"),
    (r"\bn\.c\.\b", "north carolina"), (r"\bs\.c\.\b", "south carolina"),
    (r"\bn\.m\.\b", "new mexico"), (r"\bn\.y\.\b", "new york"),
    (r"\bnorthern colo\.\b", "northern colorado"),
]


def norm(name):
    # type: (Optional[str]) -> str
    if not name:
        return ""
    s = name.lower().strip()
    s = s.replace("&", " and ").replace("'", "")
    for pat, rep in ABBREV:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return ALIASES.get(s, s)


def parse_record(rec):
    # type: (Optional[str]) -> Optional[Tuple[int, int]]
    """'33-1' or '(33-1)' -> (33, 1)."""
    if not rec:
        return None
    m = re.search(r"(\d+)\s*-\s*(\d+)", rec)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def load_games():
    # type: () -> List[Dict]
    games = []
    with open(GAMES_JSONL) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                games.append(json.loads(line))
            except Exception:
                continue
    return games


def main():
    if not os.path.exists(GAMES_JSONL):
        sys.stderr.write("no games.jsonl yet -- run the crawl first\n")
        return 1

    games = load_games()
    seen_ids = set()
    unique = []
    for g in games:
        if g["game_id"] in seen_ids:
            continue
        seen_ids.add(g["game_id"])
        unique.append(g)

    # Tally per team_id. Track D-I-only and non-D-I splits separately, because
    # RPI Factors I-III count only Division I opponents while the official table
    # breaks non-D-I out into its own column.
    tally = collections.defaultdict(lambda: {
        "w": 0, "l": 0, "di_w": 0, "di_l": 0, "nondi_w": 0, "nondi_l": 0,
        "name": None, "seoname": None, "sets_for": 0, "sets_against": 0,
        "pts_for": 0, "pts_against": 0, "games": 0,
    })

    non_final = 0
    bad_shape = 0
    for g in unique:
        if g.get("game_state") != "F":
            non_final += 1
            continue
        teams = g.get("teams") or []
        if len(teams) != 2:
            bad_shape += 1
            continue

        # points for/against from linescores (home/visit keyed)
        home_pts = away_pts = 0
        for ls in g.get("linescores") or []:
            try:
                home_pts += int(ls.get("home") or 0)
                away_pts += int(ls.get("visit") or 0)
            except (TypeError, ValueError):
                pass

        for t in teams:
            tid = t.get("team_id")
            if not tid:
                bad_shape += 1
                continue
            other = [x for x in teams if x is not t][0]
            e = tally[tid]
            e["name"] = e["name"] or t.get("name_short")
            e["seoname"] = e["seoname"] or t.get("seoname")
            e["games"] += 1
            won = bool(t.get("is_winner"))
            if won:
                e["w"] += 1
            else:
                e["l"] += 1
            opp_di = (other.get("division") == 1)
            if opp_di:
                e["di_w" if won else "di_l"] += 1
            else:
                e["nondi_w" if won else "nondi_l"] += 1
            try:
                e["sets_for"] += int(t.get("sets_won") or 0)
                e["sets_against"] += int(other.get("sets_won") or 0)
            except (TypeError, ValueError):
                pass
            if t.get("is_home"):
                e["pts_for"] += home_pts
                e["pts_against"] += away_pts
            else:
                e["pts_for"] += away_pts
                e["pts_against"] += home_pts

    # Official side
    rpi = json.load(open(RPI_JSON))["data"]
    by_norm = {}
    for r in rpi:
        by_norm[norm(r["School"])] = r

    derived_by_norm = {}
    for tid, e in tally.items():
        key = norm(e["name"])
        # Two team_ids should never collapse to one normalized name; if they do,
        # report it rather than silently overwriting.
        if key in derived_by_norm:
            derived_by_norm[key]["_collision"] = True
        else:
            derived_by_norm[key] = dict(e, team_id=tid, _collision=False)

    matched, mismatches, unmatched_official, unmatched_derived = [], [], [], []

    for key, off in by_norm.items():
        der = derived_by_norm.get(key)
        if der is None:
            unmatched_official.append(off["School"])
            continue
        off_rec = parse_record(off.get("Record"))
        off_nondi = parse_record(off.get("Non-Div I")) or (0, 0)
        row = {
            "school": off["School"],
            "team_id": der["team_id"],
            "official_rank": int(off.get("Rank") or 0),
            "official_w": off_rec[0] if off_rec else None,
            "official_l": off_rec[1] if off_rec else None,
            # Compare D-I-ONLY against the official Record column. Verified from
            # the official table itself: Mississippi Val. shows Record 1-17 with
            # Non-Div I 3-3, which is only coherent if Record excludes non-D-I
            # games. Matches the Pre-Championship Manual (Factors I-III count
            # Division I opponents only).
            "derived_w": der["di_w"], "derived_l": der["di_l"],
            "derived_total_w": der["w"], "derived_total_l": der["l"],
            "official_nondi_w": off_nondi[0], "official_nondi_l": off_nondi[1],
            "derived_nondi_w": der["nondi_w"], "derived_nondi_l": der["nondi_l"],
            "derived_games": der["games"],
            "sets_for": der["sets_for"], "sets_against": der["sets_against"],
            "pts_for": der["pts_for"], "pts_against": der["pts_against"],
        }
        if off_rec and (der["di_w"], der["di_l"]) == off_rec:
            matched.append(row)
        else:
            row["delta_w"] = (der["di_w"] - off_rec[0]) if off_rec else None
            row["delta_l"] = (der["di_l"] - off_rec[1]) if off_rec else None
            mismatches.append(row)

    derived_keys = set(derived_by_norm)
    for key in derived_keys - set(by_norm):
        d = derived_by_norm[key]
        unmatched_derived.append({
            "name": d["name"], "team_id": d["team_id"],
            "w": d["w"], "l": d["l"], "games": d["games"],
        })

    mismatches.sort(key=lambda r: -abs((r.get("delta_w") or 0) + (r.get("delta_l") or 0)))
    unmatched_derived.sort(key=lambda r: -r["games"])

    report = {
        "season": 2025,
        "games_in_log": len(unique),
        "games_non_final_skipped": non_final,
        "games_bad_shape": bad_shape,
        "official_teams": len(by_norm),
        "derived_teams": len(derived_by_norm),
        "records_matched": len(matched),
        "records_mismatched": len(mismatches),
        "unmatched_official_names": sorted(unmatched_official),
        "unmatched_derived_teams": unmatched_derived[:60],
        "mismatches": mismatches,
    }
    with open(OUT, "w") as fh:
        json.dump(report, fh, indent=1)

    print("=" * 66)
    print("GAME GRAPH RECONCILIATION -- 2025")
    print("=" * 66)
    print("games in log            : %d" % len(unique))
    print("  non-final skipped     : %d" % non_final)
    print("  malformed             : %d" % bad_shape)
    print("official teams (RPI)    : %d" % len(by_norm))
    print("derived teams (game log): %d" % len(derived_by_norm))
    print()
    print("RECORDS MATCHED         : %d / %d" % (len(matched), len(by_norm)))
    print("RECORDS MISMATCHED      : %d" % len(mismatches))
    print()
    if unmatched_official:
        print("OFFICIAL TEAMS WITH NO DERIVED GAMES (%d):" % len(unmatched_official))
        for n in sorted(unmatched_official):
            print("   %s" % n)
        print()
    if unmatched_derived:
        print("DERIVED TEAMS NOT IN OFFICIAL RPI (top %d by games) -- expected: "
              "non-D-I opponents" % min(len(unmatched_derived), 15))
        for d in unmatched_derived[:15]:
            print("   %-34s %2d-%-2d  (%d games)" % (d["name"], d["w"], d["l"], d["games"]))
        print("   ... %d total" % len(unmatched_derived))
        print()
    if mismatches:
        print("MISMATCHES BY TEAM (derived vs official):")
        print("   %-30s %-9s %-9s %s" % ("school", "derived", "official", "delta"))
        for r in mismatches:
            print("   %-30s %2d-%-6d %2d-%-6d W%+d L%+d" % (
                r["school"], r["derived_w"], r["derived_l"],
                r["official_w"] or -1, r["official_l"] or -1,
                r.get("delta_w") or 0, r.get("delta_l") or 0))
    else:
        print("NO MISMATCHES. Every official record reproduces from the game log.")
    print()
    print("report -> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
