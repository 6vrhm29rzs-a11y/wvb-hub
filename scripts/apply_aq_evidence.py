#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Set each conference's AQ mechanism from NCAA.com's own 2025 AQ tracker.

WHY THIS SOURCE. The mechanism cannot be derived from our game log -- a
conference final and a regular-season finale are indistinguishable in a feed
that carries no bracket structure (see crawl_aq.py, and the failed attempt
recorded in CLAUDE.md). ncaa.com published the answer directly:

  "Tracking all 31 automatic qualifiers for the 2025 NCAA women's volleyball
   tournament", 2025-11-27

It lists, per conference, the team that took the bid and the tournament rounds.
A conference with no tournament shows **N/A** where the others list rounds.
That is an explicit statement, not an inference.

CORROBORATION. All six rows previously CONFIRMED by Claude-app agree with it
independently (ACC and Big 12 regular-season; SEC and Mountain West tournament;
Big Ten N/A in 2025, consistent with its tournament being new for 2026; Pac-12
did not field a league in 2025). Two sources, same answers.

⚠ THIS IS 2025 EVIDENCE. Conferences change format -- the Big Ten and Pac-12
both added tournaments for 2026, which is exactly why the 2026 overrides below
are applied on top and why every row records the season its evidence came from.
A conference that changes format for 2026 without announcing it will be wrong
here, and the tier says so.

Python 3.9 target.
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
AQ = os.path.join(REPO, "data", "raw", str(SEASON), "aq_mechanism_%d.json" % SEASON)

SRC = ("https://www.ncaa.com/news/volleyball-women/article/2025-11-27/"
       "tracking-all-31-automatic-qualifiers-2025-ncaa-womens-volleyball-tournament")

# Conferences that showed N/A -- no tournament, the regular-season champion
# took the automatic bid. Everything else in the tracker listed rounds.
NO_TOURNAMENT_2025 = {"Atlantic Coast", "Big 12", "Big Ten", "WCC"}

# ncaa.com's names -> ours.
ALIAS = {
    "Atlantic Coast": "ACC", "Atlantic Sun": "ASUN", "Conference USA": "CUSA",
    "Horizon League": "Horizon", "Missouri Valley": "MVC",
    "Ohio Valley": "OVC", "Patriot League": "Patriot",
    "Southern": "SoCon", "American": "American",
}

# KNOWN 2026 CHANGES, applied ON TOP of the 2025 evidence. Both were already
# CONFIRMED independently and both are new-for-2026, so 2025 cannot show them.
OVERRIDES_2026 = {
    "Big Ten": ("TOURNAMENT", "first ever for 2026; 2025 had none"),
    "Pac-12": ("TOURNAMENT", "rebuilt league, new for 2026; fielded none in 2025"),
}


def main():
    doc = json.load(open(AQ))
    confs = doc["conferences"]

    tracker = json.load(open("/tmp/aq_2025.json")) if os.path.exists("/tmp/aq_2025.json") else {}
    if not tracker:
        print("no parsed tracker at /tmp/aq_2025.json -- nothing to apply")
        return 1

    changed = agreed = conflict = 0
    for raw, row in tracker.items():
        name = ALIAS.get(raw, raw)
        if name not in confs:
            continue
        mech = "REGULAR_SEASON" if raw in NO_TOURNAMENT_2025 else "TOURNAMENT"
        prev = confs[name].get("mechanism")
        was_confirmed = "CONFIRMED" in (confs[name].get("tier") or "")

        if was_confirmed and prev and prev != mech and name not in OVERRIDES_2026:
            # Do not silently overwrite a confirmed row with a different answer.
            confs[name]["conflict_2025_tracker"] = mech
            conflict += 1
            continue
        if prev == mech:
            agreed += 1

        confs[name]["mechanism"] = mech
        confs[name]["tier"] = "CONFIRMED (ncaa.com 2025 AQ tracker)"
        confs[name]["source"] = SRC
        confs[name]["evidence_season"] = 2025
        confs[name]["bid_2025"] = row.get("team")
        confs[name]["detail"] = (
            "no conference tournament in 2025; the regular-season champion took "
            "the bid" if mech == "REGULAR_SEASON"
            else "conference tournament in 2025 (%s)" % row.get("first_round"))
        changed += 1

    for name, (mech, why) in OVERRIDES_2026.items():
        if name in confs:
            confs[name]["mechanism"] = mech
            confs[name]["tier"] = "CONFIRMED (2026 change, corroborated)"
            confs[name]["detail"] = why
            confs[name]["evidence_season"] = 2026

    doc["meta"]["mechanism_source"] = SRC
    doc["meta"]["mechanism_note"] = (
        "Mechanism set from ncaa.com's 2025 automatic-qualifier tracker, which "
        "states each conference's tournament rounds or N/A. 2025 EVIDENCE: a "
        "league that changes format for 2026 without announcing it will be "
        "wrong here. Big Ten and Pac-12 overrides applied for known 2026 "
        "changes. Cannot be derived from our game log -- the feed carries no "
        "bracket structure.")
    counts = {}
    for v in confs.values():
        counts[v.get("mechanism") or "UNKNOWN"] = counts.get(v.get("mechanism") or "UNKNOWN", 0) + 1
    doc["meta"]["counts"] = counts

    json.dump(doc, open(AQ, "w"), indent=1)
    print("rows set from the tracker : %d" % changed)
    print("  of which already agreed : %d" % agreed)
    print("  conflicts (NOT overwritten): %d" % conflict)
    print("mechanism counts          : %s" % counts)
    unconf = [k for k, v in confs.items() if "CONFIRMED" not in (v.get("tier") or "")]
    print("still unconfirmed         : %d %s" % (len(unconf), sorted(unconf)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
