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

    # CROSS-TEAM NAME INDEX -- used ONLY to CLASSIFY, never to attribute
    # production. Three cases look identical as "upperclassman with no
    # within-team 2025 production": a D-I transfer in (has production under a
    # different team_id), a D-II/JUCO/international arrival (no D-I production
    # exists), and a genuine name-match failure. Only the third is a defect.
    # Searching the other 347 teams separates the first from the other two.
    everywhere = {}
    for p in prod:
        everywhere.setdefault(nkey(p.get("first"), p.get("last")), []).append(p)

    print("=" * 78)
    print("JOIN — 2026 rosters x 2025 production")
    print("=" * 78)

    totals = {"returning": 0, "departed": 0, "new": 0, "unresolved": 0,
              "loose": 0, "transfer_in": 0}
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
        transfers = []
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
                    # upperclassman with no production HERE -- transfer or defect?
                    elsewhere = [q for q in everywhere.get(nkey(f, l), [])
                                 if str(q.get("team_id")) != str(tid)]
                    if len(elsewhere) == 1:
                        q = elsewhere[0]
                        transfers.append({"name": r.get("name_raw"),
                                          "class": r.get("class_raw"),
                                          "from_team_id": q.get("team_id"),
                                          "points_2025": q.get("points"),
                                          "kills_2025": q.get("kills")})
                    elif len(elsewhere) > 1:
                        unresolved.append((r.get("name_raw"),
                                           "ambiguous across %d teams" % len(elsewhere)))
                    else:
                        unresolved.append((r.get("name_raw"),
                                           "no D-I production anywhere, class=%s"
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
            "transfer_in_official": transfers,
            "resolved_by_normalisation": loose_hits,
        }
        totals["returning"] += len(returning)
        totals["departed"] += len(departed)
        totals["new"] += len(new)
        totals["unresolved"] += len(unresolved)
        totals["loose"] += len(loose_hits)
        totals["transfer_in"] += len(transfers)

        print("  %-11s returning=%-3d departed=%-3d new=%-3d xfer-in=%-3d "
              "UNRESOLVED=%-3d loose=%d"
              % (team, len(returning), len(departed), len(new), len(transfers),
                 len(unresolved), len(loose_hits)))

    print()
    print("  TOTALS  returning=%d departed=%d new/unplayed=%d transfer-in=%d "
          "UNRESOLVED=%d"
          % (totals["returning"], totals["departed"], totals["new"],
             totals["transfer_in"], totals["unresolved"]))
    roster_n = totals["returning"] + totals["new"] + totals["transfer_in"] + totals["unresolved"]
    if roster_n:
        print("  JOIN RATE (roster players classified without defect): %.1f%%  "
              "-- go/no-go bar is 90%%" % (100.0 * (roster_n - totals["unresolved"]) / roster_n))
    print("  resolved only by normalisation (eyeball these): %d" % totals["loose"])
    print()

    # CLUSTERED vs EVEN. If unresolved upperclassmen pile up at a few schools
    # the heuristic is catching transfer intake, not join failures; if they
    # spread evenly it is finding real name mismatches. Those call for
    # completely different responses, so the distinction is reported, not the
    # bare count.
    per = {t: len(r.get("unresolved") or []) for t, r in report.items()
           if isinstance(r.get("unresolved"), list)}
    if per:
        vals = sorted(per.values(), reverse=True)
        tot = sum(vals) or 1
        top2 = sum(vals[:2])
        nz = sum(1 for v in vals if v)
        print("  DISTRIBUTION of unresolved across %d schools: %s"
              % (len(vals), ", ".join("%s=%d" % (t, n)
                                      for t, n in sorted(per.items(),
                                                         key=lambda kv: -kv[1]) if n)
                 or "none"))
        if tot:
            print("    top-2 schools hold %d/%d (%.0f%%); %d of %d schools have any"
                  % (top2, tot, 100.0 * top2 / tot, nz, len(vals)))
            print("    -> %s" % ("CLUSTERED: likely transfer intake, not join failure"
                                 if (top2 / float(tot)) > 0.6 and nz <= max(2, len(vals) // 3)
                                 else "SPREAD: likely genuine name mismatches"))
        print()

    # NAME-SHAPE PATTERNS in the failures -- a fixable pattern vs random churn.
    shapes = {"hyphenated": 0, "suffix": 0, "diacritic": 0, "three_plus_parts": 0,
              "initial": 0, "apostrophe": 0}
    for r in report.values():
        for nm, _why in (r.get("unresolved") or []):
            n = nm or ""
            if "-" in n:
                shapes["hyphenated"] += 1
            if SUFFIX.search(n.split(" ")[-1] if " " in n else ""):
                shapes["suffix"] += 1
            if any(ord(c) > 127 for c in n):
                shapes["diacritic"] += 1
            if len(n.split()) >= 3:
                shapes["three_plus_parts"] += 1
            if re.search(r"\b[A-Z]\.", n):
                shapes["initial"] += 1
            if "'" in n or "\u2019" in n:
                shapes["apostrophe"] += 1
    if any(shapes.values()):
        print("  NAME-SHAPE PATTERNS among unresolved: %s"
              % ", ".join("%s=%d" % (k, v) for k, v in shapes.items() if v))
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
