#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Is the 88.0% join rate a DEFECT rate, or a floor?

The join reports UNRESOLVED for any roster player it cannot tie to 2025
production. That count conflates two populations that call for opposite
responses:

  REAL JOIN DEFECT   the player DID produce for this team in 2025, under a
                     spelling the key missed. Production exists and is being
                     dropped on the floor.
  NOT A DEFECT       the player has no D-I production because there is none to
                     have -- a walk-on, a D-II/JUCO/international arrival, or a
                     squad member who never saw the court.

Only the first is a defect, and only the first should count against the 90%
go/no-go bar. The distinguishing test: does a NEAR name exist in that team's
OWN 2025 production pool? Pools are ~15-22 players, so a near-miss inside one
is strong evidence of a spelling mismatch rather than coincidence.

  difflib.get_close_matches(roster_name, pool_names, n=1, cutoff=0.72)

Same check, same cutoff, that found ZERO real defects among the 11 unresolved
on the 10-school hand-verified test. This runs it on all 673.

TWO REFINEMENTS the 10-school run did not need, both of which cut the other way
(they REDUCE the defect count, so they are stated rather than buried):

  1. CLAIMED POOL PLAYERS ARE EXCLUDED. If roster "Jane Smith" nearly matches
     pool "Jane Smyth" but Smyth was already matched exactly to a DIFFERENT
     roster player, nothing is being dropped -- one real person cannot be two
     roster entries. Counting it would inflate the defect rate. Reported both
     ways so the exclusion is auditable.
  2. ZERO-PRODUCTION NEAR MATCHES ARE SPLIT OUT. A missed join to a pool row
     with 0 points and 0 sets is still a join miss, but it strands nothing and
     cannot move a returning-production number.

Verdict is threshold-free in the sense R1 requires: the script reports the
measured defect rate and the recomputed join rate. It does not print a
characterisation that was written before the number existed.

Python 3.9 target.
"""

import difflib
import json
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from join_players import fullkey, nkey  # noqa: E402  same keys the join used

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTERS = os.path.join(REPO, "data", "raw", "2026", "rosters_2026.json")
PLAYERS = os.path.join(REPO, "data", "raw", "2025", "players_2025.json")
REPORT = os.path.join(REPO, "data", "returning_2026.json")
OUT = os.path.join(REPO, "data", "unresolved_audit.json")

CUTOFF = 0.72


def disp(p):
    return ("%s %s" % (p.get("first") or "", p.get("last") or "")).strip()


def main():
    for path in (ROSTERS, PLAYERS, REPORT):
        if not os.path.exists(path):
            print("missing %s -- run scripts/join_players.py first" % path)
            return 1

    rosters = json.load(open(ROSTERS))["teams"]
    prod = json.load(open(PLAYERS))["players"]
    report = json.load(open(REPORT))["teams"]

    by_team = {}
    for p in prod:
        by_team.setdefault(str(p["team_id"]), []).append(p)

    print("=" * 78)
    print("UNRESOLVED AUDIT — near-name search inside each team's own 2025 pool")
    print("  cutoff=%.2f  (same check that cleared all 11 on the 10-school test)" % CUTOFF)
    print("=" * 78)
    print()

    rows = []
    n_unresolved = 0
    for team, meta in sorted(rosters.items()):
        r = report.get(team) or {}
        unres = r.get("unresolved") or []
        if not unres:
            continue
        tid = str(meta.get("team_id") or "")
        pool = by_team.get(tid, [])

        # Which pool players are already spoken for by ANOTHER roster entry?
        # Rebuilt with the join's own keys so the two passes agree by
        # construction rather than by hope.
        roster = meta.get("players") or []
        exact, loose, whole = {}, {}, {}
        for p in pool:
            exact[((p.get("first") or "").strip(), (p.get("last") or "").strip())] = p
            loose.setdefault(nkey(p.get("first"), p.get("last")), []).append(p)
            whole.setdefault(fullkey(p.get("first"), p.get("last")), []).append(p)
        claimed = set()
        for rp in roster:
            f = (rp.get("first") or "").strip()
            l = (rp.get("last") or "").strip()
            hit = exact.get((f, l))
            if hit is None:
                c = loose.get(nkey(f, l), [])
                hit = c[0] if len(c) == 1 else None
            if hit is None:
                c = whole.get(fullkey(f, l), [])
                hit = c[0] if len(c) == 1 else None
            if hit is not None:
                claimed.add(id(hit))

        named = [p for p in pool if disp(p)]
        free = [p for p in named if id(p) not in claimed]
        free_names = [disp(p) for p in free]
        all_names = [disp(p) for p in named]

        for nm, why in unres:
            n_unresolved += 1
            name = nm or ""
            hit_any = difflib.get_close_matches(name, all_names, n=1, cutoff=CUTOFF)
            hit_free = difflib.get_close_matches(name, free_names, n=1, cutoff=CUTOFF)
            row = {"team": team, "name": name, "why": why,
                   "pool_size": len(named), "unclaimed_pool": len(free),
                   "near_any": hit_any[0] if hit_any else None,
                   "near_free": hit_free[0] if hit_free else None}
            if hit_free:
                q = free[free_names.index(hit_free[0])]
                row["ratio"] = round(difflib.SequenceMatcher(
                    None, name, hit_free[0]).ratio(), 3)
                row["points_2025"] = q.get("points")
                row["kills_2025"] = q.get("kills")
                row["sets_2025"] = q.get("sets")
            rows.append(row)

    # ---- counts first, wording afterwards (R1) ----
    defects = [r for r in rows if r["near_free"]]
    defects_live = [r for r in defects
                    if (r.get("points_2025") or 0) > 0 or (r.get("sets_2025") or 0) > 0]
    defects_zero = [r for r in defects if r not in defects_live]
    clean = [r for r in rows if not r["near_free"]]
    coincident = [r for r in rows if r["near_any"] and not r["near_free"]]
    empty_pool = [r for r in rows if r["pool_size"] == 0]

    stranded_pts = sum((r.get("points_2025") or 0) for r in defects_live)
    stranded_kills = sum((r.get("kills_2025") or 0) for r in defects_live)

    tot = json.load(open(REPORT))["meta"]["totals"]
    roster_n = tot["returning"] + tot["new"] + tot["transfer_in"] + tot["unresolved"]
    reported_rate = 100.0 * (roster_n - tot["unresolved"]) / roster_n
    true_rate = 100.0 * (roster_n - len(defects)) / roster_n
    live_rate = 100.0 * (roster_n - len(defects_live)) / roster_n

    print("  audited                       %d unresolved names" % n_unresolved)
    print("  NEAR MATCH in own pool        %d   <- candidate real join defects"
          % len(defects))
    print("    ...with 2025 production     %d   (points>0 or sets>0)" % len(defects_live))
    print("    ...zero-production rows     %d   (a miss, but strands nothing)"
          % len(defects_zero))
    print("  no near match                 %d   <- no D-I production to attribute"
          % len(clean))
    print("    of which the near name was already claimed by another roster entry: %d"
          % len(coincident))
    print("  unresolved at teams with an empty 2025 pool: %d" % len(empty_pool))
    print()
    print("  production stranded by the candidate defects: %d points, %d kills"
          % (stranded_pts, stranded_kills))
    print()
    print("  JOIN RATE, reported (every unresolved counted as a defect)  %.1f%%"
          % reported_rate)
    print("  JOIN RATE, defects only (near match in own pool)            %.1f%%"
          % true_rate)
    print("  JOIN RATE, defects that strand production                   %.1f%%"
          % live_rate)
    print("  go/no-go bar                                                90.0%%")
    print("  measured defect rate among roster players: %.2f%% (%d of %d)"
          % (100.0 * len(defects) / roster_n, len(defects), roster_n))
    print()

    if defects:
        print("  CANDIDATE DEFECTS — roster name -> unclaimed pool name (ratio, 2025 prod):")
        for r in sorted(defects, key=lambda x: -(x.get("points_2025") or 0)):
            print("    %-13s %-24s -> %-24s %.2f  pts=%s kills=%s sets=%s"
                  % (r["team"], r["name"], r["near_free"], r["ratio"],
                     r.get("points_2025"), r.get("kills_2025"), r.get("sets_2025")))
        print()

    json.dump({"meta": {"source_tier": "DERIVED",
                        "note": "difflib near-name audit of join_players.py "
                                "UNRESOLVED; cutoff=%.2f" % CUTOFF,
                        "audited": n_unresolved,
                        "candidate_defects": len(defects),
                        "defects_with_production": len(defects_live),
                        "join_rate_reported": round(reported_rate, 2),
                        "join_rate_defects_only": round(true_rate, 2),
                        "join_rate_production_defects": round(live_rate, 2),
                        "stranded_points": stranded_pts,
                        "stranded_kills": stranded_kills},
               "rows": rows}, open(OUT, "w"), indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
