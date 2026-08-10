#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Join 2026 rosters to 2025 per-player production. Reports FOUR categories.

THE JOIN IS THE RISK. Two institutions spell the same person differently:
production comes from ncaa.com boxscores, rosters from school athletics sites.
A wrong join silently attributes one player's production to another -- plausible
output, wrong answer, the failure pattern this project keeps hitting.

FOUR CATEGORIES, reported separately. Conflating any two of them turns a normal
situation into a fake problem or hides a real one:

  RETURNING      on the 2026 roster AND produced in 2025
  DEPARTED       produced in 2025, NOT on the 2026 roster        <- the signal
  NEW/UNPLAYED   on the 2026 roster, no 2025 production          <- NOT a failure
                 (true freshmen, redshirts, incoming transfers, injured)
  UNRESOLVED     a name that could not be resolved either way    <- the actual
                 join failure, and the only one that is a defect

WITHIN-TEAM ONLY, and conservative. The candidate pool per team is ~15-22
players, so: exact match first, then one narrow normalisation pass (case,
punctuation, diacritics, suffixes). Anything resolved by the looser pass is
reported SEPARATELY so it can be eyeballed. Never fuzzy-match across teams.

Python 3.9 target.
"""

import json
import os
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTERS = os.path.join(REPO, "data", "raw", "2026", "rosters_2026.json")
PLAYERS = os.path.join(REPO, "data", "raw", "2025", "players_2025.json")
OUT = os.path.join(REPO, "data", "returning_2026.json")

SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\.?$", re.I)


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def nkey(first, last):
    """Narrow normalisation: accents, case, punctuation, suffixes."""
    f = strip_accents((first or "").lower())
    l = strip_accents((last or "").lower())
    l = SUFFIX.sub("", l).strip()
    f = re.sub(r"[^a-z]", "", f)
    l = re.sub(r"[^a-z]", "", l)
    return f, l


def main():
    if not os.path.exists(PLAYERS):
        print("no %s yet -- run: python3 scripts/crawl_2025.py players" % PLAYERS)
        return 1
    rosters = json.load(open(ROSTERS))["teams"]
    prod = json.load(open(PLAYERS))["players"]

    by_team = {}
    for p in prod:
        by_team.setdefault(p["team_id"], []).append(p)

    print("=" * 78)
    print("JOIN — 2026 rosters x 2025 production")
    print("=" * 78)

    totals = {"returning": 0, "departed": 0, "new": 0, "unresolved": 0, "loose": 0}
    report = {}
    for team, meta in sorted(rosters.items()):
        roster = meta.get("players") or []
        tid = meta.get("team_id")
        if not roster or not tid:
            continue
        pool = by_team.get(str(tid), [])
        if not pool:
            report[team] = {"status": "no 2025 production data for this team_id"}
            continue

        # index production by exact and normalised keys
        exact, loose = {}, {}
        for p in pool:
            exact[((p.get("first") or "").strip(), (p.get("last") or "").strip())] = p
            loose.setdefault(nkey(p.get("first"), p.get("last")), []).append(p)

        matched_ids, returning, new, unresolved, loose_hits = set(), [], [], [], []
        for r in roster:
            f, l = (r.get("first") or "").strip(), (r.get("last") or "").strip()
            hit = exact.get((f, l))
            how = "exact"
            if hit is None:
                cands = loose.get(nkey(f, l), [])
                if len(cands) == 1:
                    hit, how = cands[0], "normalised"
                elif len(cands) > 1:
                    unresolved.append((r.get("name_raw"), "ambiguous: %d candidates"
                                       % len(cands)))
                    continue
            if hit is None:
                # genuinely absent from 2025 production: could be a true
                # freshman/transfer (expected) OR a name we failed to resolve.
                # Distinguishable only by class year: a returning player with
                # 2025 production should not be a first-year.
                cls = (r.get("class_raw") or "").lower()
                if cls.startswith(("fr", "freshman", "redshirt fr", "r-fr")):
                    new.append(r.get("name_raw"))
                else:
                    unresolved.append((r.get("name_raw"),
                                       "no 2025 production, class=%s"
                                       % (r.get("class_raw") or "?")))
                continue
            key = (hit.get("first"), hit.get("last"))
            matched_ids.add(key)
            returning.append({"name": r.get("name_raw"), "class": r.get("class_raw"),
                              "how": how,
                              "kills": hit.get("kills"), "points": hit.get("points"),
                              "sets": hit.get("sets")})
            if how == "normalised":
                loose_hits.append((r.get("name_raw"),
                                   "%s %s" % (hit.get("first"), hit.get("last"))))

        departed = [{"name": "%s %s" % (p.get("first"), p.get("last")),
                     "points": p.get("points"), "kills": p.get("kills")}
                    for p in pool
                    if (p.get("first"), p.get("last")) not in matched_ids
                    and (p.get("points") or 0) > 0]

        report[team] = {
            "returning": returning, "departed": departed,
            "new_or_unplayed": new, "unresolved": unresolved,
            "resolved_by_normalisation": loose_hits,
        }
        totals["returning"] += len(returning)
        totals["departed"] += len(departed)
        totals["new"] += len(new)
        totals["unresolved"] += len(unresolved)
        totals["loose"] += len(loose_hits)

        print("  %-11s returning=%-3d departed=%-3d new=%-3d UNRESOLVED=%-3d loose=%d"
              % (team, len(returning), len(departed), len(new), len(unresolved),
                 len(loose_hits)))

    print()
    print("  TOTALS  returning=%d departed=%d new/unplayed=%d UNRESOLVED=%d"
          % (totals["returning"], totals["departed"], totals["new"], totals["unresolved"]))
    print("  resolved only by normalisation (eyeball these): %d" % totals["loose"])
    print()

    print("  UNRESOLVED NAMES — the actual join failures, listed not counted:")
    any_un = False
    for team, r in sorted(report.items()):
        for nm, why in (r.get("unresolved") or []):
            print("    %-12s %-26s %s" % (team, nm, why))
            any_un = True
    if not any_un:
        print("    none")
    print()
    if totals["loose"]:
        print("  RESOLVED BY NORMALISATION — roster name -> production name:")
        for team, r in sorted(report.items()):
            for a, b in (r.get("resolved_by_normalisation") or []):
                print("    %-12s %-26s -> %s" % (team, a, b))
        print()

    json.dump({"meta": {"source_tier": "DERIVED",
                        "note": "roster (school sites, OFFICIAL) x production "
                                "(ncaa.com boxscores, OFFICIAL); join is DERIVED",
                        "totals": totals},
               "teams": report}, open(OUT, "w"), indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
