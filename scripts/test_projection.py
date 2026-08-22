#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the 2026 projection, and the measurement its rotation size rests on.

THE ONE THING IN THE PROJECTION THAT IS MEASURED is ROTATION = 6. Everything
else in project_2026.py is a hand-set weight. This file re-derives the rotation
number from 2025 data on every run, so the constant cannot drift away from the
evidence for it, and asserts the failure that made it necessary.

WHAT WENT WRONG WITHOUT IT. The first version summed every roster player's prior
production. Florida returns 12 and adds 7 transfers; counting all 19 credited it
with roughly two teams' worth of scoring and put it top of the table. Six players
are on the court, and summing the top six players' own points-per-set reproduces
their team's ACTUAL points-per-set more closely than any other cut.

Python 3.9 target. Run: python3 scripts/test_projection.py
"""

import json
import os
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project_2026 as P  # noqa: E402

FAILURES = []
MIN_SETS = 20


def check(label, ok, detail=""):
    print("  %-58s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILURES.append(label)


def load(p):
    path = os.path.join(REPO, p)
    return json.load(open(path)) if os.path.exists(path) else None


def rotation_fit():
    """median(sum of top-N player rates - team's real rate), by N, over 2025."""
    ds = load("data/data_2025.json")
    pjson = load("data/raw/2025/players_2025.json")
    if not ds or not pjson:
        return None
    by_team = {}
    for p in pjson["players"]:
        if (p.get("sets") or 0) >= MIN_SETS and p.get("team_id"):
            by_team.setdefault(str(p["team_id"]), []).append(p)
    out = {}
    for n in range(4, 10):
        errs = []
        for t in ds["teams"]:
            tid = str(t.get("team_id") or "")
            st = t.get("season_totals") or {}
            if not st.get("sets") or tid not in by_team:
                continue
            team_rate = ((st.get("kills", 0) + st.get("aces", 0)
                          + st.get("block_solos", 0)
                          + 0.5 * st.get("block_assists", 0)) / float(st["sets"]))
            rates = sorted((P.player_points(p) / float(p["sets"])
                            for p in by_team[tid]), reverse=True)
            if len(rates) < n:
                continue
            errs.append(sum(rates[:n]) - team_rate)
        if errs:
            out[n] = (statistics.median(errs), len(errs))
    return out


def main():
    print("PROJECTION GUARDS\n")

    print("1. ROTATION size is the best-fitting cut, re-derived from 2025")
    fit = rotation_fit()
    if not fit:
        check("2025 data present to re-derive rotation size", False, "(missing inputs)")
    else:
        for n in sorted(fit):
            med, cnt = fit[n]
            mark = "  <-- ROTATION" if n == P.ROTATION else ""
            print("     top-%d  median error %+6.3f pts/set  (n=%d)%s" % (n, med, cnt, mark))
        best = min(fit, key=lambda n: abs(fit[n][0]))
        check("the constant equals the best-fitting cut", best == P.ROTATION,
              "(best is top-%d, code says %d)" % (best, P.ROTATION))
        check("its median error is under 1 point/set", abs(fit[P.ROTATION][0]) < 1.0,
              "(%.3f)" % fit[P.ROTATION][0])

    print("\n2. The projection is capped by the rotation, not by roster size")
    proj = load("data/projection_2026.json")
    if not proj:
        # The projection is a DERIVED artifact and deliberately not committed,
        # so a fresh CI checkout will not have one. Skipping is correct there;
        # failing would make the daily run red for a file it was never meant to
        # carry. Locally, where it exists, every check below still runs.
        print("  %-58s %s" % ("(no data/projection_2026.json -- derived, skipping)",
                              "skip"))
        print()
        print("ROTATION guard ran; projection-payload guards skipped")
        return 1 if FAILURES else 0
    else:
        rows = proj["teams"]
        over = [r for r in rows if (r.get("rotation_known") or 0) > P.ROTATION]
        check("no team counts more than ROTATION players", not over,
              "(%d teams do)" % len(over))
        # Florida is the case that exposed the bug: deep roster, many transfers.
        fl = next((r for r in rows if r["team"] == "Florida"), None)
        if fl:
            check("Florida's pool is deeper than its counted rotation",
                  (fl.get("pool_size") or 0) > (fl.get("rotation_known") or 0),
                  "(pool %s, counted %s)" % (fl.get("pool_size"), fl.get("rotation_known")))
        # A projected team rate must land in the range real teams occupy.
        vals = [r["proj_points_per_set"] for r in rows
                if r.get("proj_points_per_set") is not None]
        if vals:
            check("projected points/set stay in a physical range",
                  min(vals) > 2.0 and max(vals) < 30.0,
                  "(min %.2f, max %.2f)" % (min(vals), max(vals)))

    print("\n3. Nothing is invented for teams we cannot see")
    if proj:
        rows = proj["teams"]
        # A team with no roster is still RANKED -- on last season's rating alone,
        # which predicts the next season at spearman 0.857 and is the best
        # estimate available for anyone. What must never happen is roster
        # information being INVENTED to fill the gap. So the check is not "no
        # score" but "the score is exactly the prior, with nothing added".
        noroster = [r for r in rows if not r.get("has_roster")]
        bad = [r for r in noroster
               if r.get("talent") is not None and r.get("composite_2025") is not None
               # talent is stored rounded to 4dp; compare at that precision
               and abs(r["talent"] - r["composite_2025"]) > 5e-5]
        check("teams with no roster score exactly their prior, nothing invented",
              not bad, "(%d differ from their 2025 composite)" % len(bad))
        check("no team with no roster gets a roster delta",
              all(r.get("roster_delta") is None for r in noroster),
              "(%d have one)" % sum(1 for r in noroster if r.get("roster_delta") is not None))
        check("the freshman weight is zero while we hold no recruiting data",
              P.W_FRESHMAN == 0.0, "(W_FRESHMAN=%s)" % P.W_FRESHMAN)
        check("weights are declared in the output, not just in code",
              bool((proj.get("meta") or {}).get("weights")))
        check("the output states it is unvalidated",
              (proj.get("meta") or {}).get("validated") is False)

    print()
    if FAILURES:
        print("FAILED: %d check(s)" % len(FAILURES))
        for f in FAILURES:
            print("   - %s" % f)
        return 1
    print("ALL PROJECTION GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
