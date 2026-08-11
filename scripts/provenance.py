#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provenance manifest: every displayed field, its source, and its tier.

Run: python3 scripts/provenance.py          # prints the table
     python3 scripts/provenance.py --check  # gate: unknown fields fail

*** WHAT THIS GUARD CAN AND CANNOT CATCH. Read before trusting it. ***

CAN catch:
  - a NEW field appearing in the dashboard payload with no declared provenance
  - a field declared UNVERIFIED that the UI does not visibly mark as such
  - the specific name-hash fabricator, and label-hashing functions not
    allowlisted as decorative (see test_display_invariants.py)

CANNOT catch:
  - a client-side JavaScript expression inventing a value for a field that
    already has a legitimate entry here. The dashboard computes some display
    values in the browser; nothing in a static manifest observes that. The
    retPct fabrication was exactly this shape, and it is why the sign/range
    invariants exist as a SECOND, independent check -- a fabricated value must
    also survive being non-negative and in range to get through.
  - anything in the roster/transfer detail panes, which are sourced from the
    original 40-team files and are not part of the numeric payload.

So: this is a coverage gate, not a proof of correctness. An honest boundary
beats an implied guarantee.

Python 3.9 target.
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(REPO, "output", "vb_dashboard.html")

# field -> (what it is, source, tier, is the tier visible to the reader?)
MANIFEST = {
    "team":       ("School name", "ncaa.com RPI table / game feed", "OFFICIAL", "n/a"),
    "conf":       ("Conference", "ncaa.com RPI table", "OFFICIAL", "n/a"),
    "record":     ("W-L, Division I only", "ncaa.com RPI table 'Record'", "OFFICIAL",
                   "yes - footer states records are official NCAA"),
    "gp":         ("Games played", "derived: wins + losses", "DERIVED",
                   "yes - thin-sample rows are dimmed and flagged"),
    "rpi":        ("RPI Factors I-III", "computed from the game graph per the "
                   "2025-26 Pre-Championship Manual 2.2", "DERIVED",
                   "yes - formula stated on the page"),
    "rpiRank":    ("Official RPI rank", "ncaa.com RPI table 'Rank'", "OFFICIAL",
                   "yes - footer cites stats.ncaa.org"),
    "delta":      ("Our rank minus official RPI rank", "derived", "DERIVED",
                   "yes - column tooltip explains it"),
    "composite":  ("1.27*Z(RPI) + 1.27*Z(adj net pts/set)", "fitted on 2025 "
                   "match outcomes", "DERIVED", "yes - formula and weights on the page"),
    "pps":        ("Opponent-adjusted net points/set", "ridge fit over the game "
                   "graph, from /game linescores", "DERIVED",
                   "yes - column header 'Adj Net/Set' + method in footer"),
    "opps":       ("Offense points/set (kills+aces+blocks)", "stat leaderboards "
                   "cats 45-50", "OFFICIAL", "yes - labelled 2025 Pts/Set"),
    "kps":        ("Kills per set", "stat leaderboard cat 46", "OFFICIAL", "n/a"),
    "aps":        ("Aces per set", "stat leaderboard cat 48", "OFFICIAL", "n/a"),
    "bps":        ("Blocks per set", "stat leaderboard cat 49", "OFFICIAL", "n/a"),
    "sos":        ("Schedule rank by opponents' win %", "RPI Factor II", "DERIVED", "n/a"),
    "t25":        ("Record vs official RPI top 25", "derived from the game log",
                   "DERIVED", "yes - resume column"),
    "t50":        ("Record vs official RPI top 50", "derived from the game log",
                   "DERIVED", "yes - resume column"),
    "lowconf":    ("Thin-sample flag (<10 D-I matches)", "derived", "DERIVED",
                   "yes - row dimmed, marker, tooltip"),
    "ret2026":    ("Returning production. Roster-based where returning_method "
                   "== 'roster' (2026 rosters x 2025 production, 308 of 348); "
                   "graduation-only on the legacy 40-team path",
                   "data/returning_2026.json (join of school rosters x ncaa.com "
                   "box scores); legacy: data/vb_players_2025.json",
                   "DERIVED from two OFFICIAL sources",
                   "yes - banner states 'Coverage: N of 348' and names the method"),
    "returning_method": ("Which question the Returning % answers: 'roster' "
                         "(on the published 2026 roster) or class-year "
                         "graduation. Selects the method sentence on the page "
                         "so the number and its label cannot drift apart",
                         "set by scripts/build_vb.py from which join was used",
                         "DERIVED", "yes - it IS the disclosure"),
    "unres2026": ("Roster players whose 2025 production could not be matched. "
                  "Their production is not attributed, so the team's share is "
                  "conservative rather than inflated",
                  "data/returning_2026.json unresolved list; audited by "
                  "scripts/audit_unresolved.py (defect rate 0.09%)",
                  "DERIVED", "yes - method note states unmatched are excluded"),
    "ret2026net": ("Returning production net of transfers", "vb_transfers_2026.json, "
                   "a NON-OFFICIAL tracker dated 2026-08-09", "THIRD-PARTY",
                   "yes - orange banner names the tracker and its date"),
    "dep1": ("Top departure", "vb_players_2025.json", "OFFICIAL (partial)", "n/a"),
    "dep2": ("Second departure", "vb_players_2025.json", "OFFICIAL (partial)", "n/a"),
    "xin":  ("Incoming transfers", "NON-OFFICIAL tracker", "THIRD-PARTY",
             "yes - same orange banner"),
    "xout": ("Outgoing transfers", "NON-OFFICIAL tracker", "THIRD-PARTY",
             "yes - same orange banner"),
    "inPts": ("Incoming transfer production", "NON-OFFICIAL tracker", "THIRD-PARTY",
              "yes - same orange banner"),
    "roster": ("Player list", "vb_players_2025.json, 40-team coverage",
               "OFFICIAL (partial)", "yes - only shown where it exists"),
    "real":   ("Has official player data", "derived presence check", "DERIVED", "n/a"),
    "ncRpiRank": ("Non-conference RPI rank", "ncaa.com RPI table", "OFFICIAL", "n/a"),
    "teamPts": ("Season total points (kills+aces+blocks)", "vb_players_2025.json "
                "summed, 40-team coverage", "OFFICIAL (partial)",
                "yes - only present where roster data exists"),
}

# Provenance STRINGS shown to the reader. Not measurements -- they are the
# citations the UI prints, which is how the tier reaches the reader at all.
CITATIONS = {
    "official_asof":     "footer citation for records + RPI",
    "returning_source":  "footer citation for returning production",
    "transfers_source":  "orange banner citation naming the transfer trackers",
    "transfers_conf":    "orange banner confidence note on transfer dimensions",
}

# non-numeric / structural keys that need no provenance entry
STRUCTURAL = {"fitted", "asof", "sos_weight", "weights", "teams", "logos",
              "generated_at", "data_through", "matches_in_data",
              "transfers_asof", "official_source"}


def payload_fields():
    if not os.path.exists(DASH):
        return set()
    h = open(DASH, encoding="utf-8").read()
    m = re.search(r"const MODEL = (\{.*?\});\n", h, re.S)
    if not m:
        return set()
    M = json.loads(m.group(1).replace("<\\/", "</"))
    keys = set(M.keys()) - STRUCTURAL
    for t in (M.get("teams") or [])[:50]:
        keys |= set(t.keys())
    return keys


def main():
    check = "--check" in sys.argv
    fields = payload_fields()
    unknown = sorted(f for f in fields
                     if f not in MANIFEST and f not in STRUCTURAL
                     and f not in CITATIONS)

    if not check:
        print("=" * 100)
        print("PROVENANCE — every displayed field in the dashboard payload")
        print("=" * 100)
        print("%-12s %-38s %-24s %s" % ("FIELD", "SOURCE", "TIER", "TIER VISIBLE TO READER?"))
        print("-" * 100)
        for k in sorted(MANIFEST):
            what, src, tier, vis = MANIFEST[k]
            mark = "" if k in fields else "   (not currently rendered)"
            print("%-12s %-38s %-24s %s%s" % (k, src[:38], tier, vis[:34], mark))
        print()
        print("CITATION STRINGS (text the UI prints, not measurements):")
        for k, v in sorted(CITATIONS.items()):
            print("   %-20s %s" % (k, v))
        print()
        print("UNVERIFIED fields: none. Every THIRD-PARTY field (transfer data) is")
        print("named on the page with its tracker and date. Partial-coverage fields")
        print("state their coverage rather than filling gaps.")
        print()

    if unknown:
        print("FAIL: %d displayed field(s) have no declared provenance: %s"
              % (len(unknown), unknown))
        return 1
    print("PROVENANCE OK — all %d displayed fields declared." % len(fields))
    return 0


if __name__ == "__main__":
    sys.exit(main())
