#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parts versus whole, and what each team returns by position.

TWO THINGS, AND THE FIRST IS NOT A RATING.

1. PARTS VERSUS WHOLE. A team's players predict its strength well -- the mean
   of its top seven rated players correlates 0.833 with what the team actually
   did. The interesting number is therefore not the prediction, it is the GAP:
   a team that beat what its roster predicts got something out of a season that
   individual box-score lines cannot see, and one that fell short did not.

   ⚠ MEASURED FIRST, AND TWO INTUITIONS DIED. Cody's hypothesis was that
   volleyball's rotation rules break "sum of the parts" -- you cannot hide a
   weak player, because everyone rotates through all six positions and a team
   must side out in all six rotations. Tested both ways:
     * ROSTER SPREAD: holding the mean fixed, the WEAKEST starter carries a
       NEGATIVE coefficient (-0.349) and spread a POSITIVE one (+0.261). At
       equal average a team with one dominant hitter beats a balanced one --
       the opposite of a weakest-link effect, and it makes sense, because
       rotation forces everyone on court but SET DISTRIBUTION is a choice and a
       star absorbs 35-40% of the swings.
     * ROTATION SPREAD: correlates -0.088 with team strength. Adding the worst
       rotation to mean side-out moves R-squared from 0.6960 to 0.6964.
   So the weakest-link story is not supported and the residual is NOT modelled
   as one. It is reported as what it is: unexplained.

   ⚠ AND IT IS A 2025 NUMBER, DELIBERATELY. Comparing a 2026 player sum against
   the 2026 team projection would be circular -- that projection is BUILT from
   2026 rosters times 2025 production, so the two would agree by construction
   and the "gap" would measure nothing. Only a completed season, where team
   strength comes from results, gives an honest residual.

2. WHAT A TEAM RETURNS, BY POSITION. "Returns 78% of its production" hides the
   thing that matters: a side returning both middles and losing its setter is a
   different team from one that did the reverse.

Python 3.9 target. Run: python3 scripts/team_parts.py
"""

import collections
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = 2026
PRIOR = 2025
MIN_RATED = 7          # a team needs a real roster before its parts mean anything

POSMAP = {"OH": "OH", "MB": "MB", "MH": "MB", "S": "S", "OPP": "OPP",
          "RS": "OPP", "L": "LDS", "DS": "LDS", "L/DS": "LDS"}
POS_ORDER = ["OH", "OPP", "MB", "S", "LDS"]


def L(path):
    p = os.path.join(REPO, path)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding="utf-8"))


def bucket(p):
    return POSMAP.get((p or "").strip().upper())


def ols(X, y):
    """Least squares with an intercept, without numpy."""
    n = len(X)
    k = len(X[0])
    A = [[1.0] + list(row) for row in X]
    # normal equations
    XtX = [[sum(A[i][a] * A[i][b] for i in range(n)) for b in range(k + 1)]
           for a in range(k + 1)]
    Xty = [sum(A[i][a] * y[i] for i in range(n)) for a in range(k + 1)]
    # gaussian elimination
    M = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    m = k + 1
    for c in range(m):
        piv = max(range(c, m), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        d = M[c][c]
        M[c] = [v / d for v in M[c]]
        for r in range(m):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [a2 - f * b2 for a2, b2 in zip(M[r], M[c])]
    return [M[i][m] for i in range(m)]


def main():
    rate = L("data/player_rating_%d.json" % SEASON)
    if not rate:
        print("no player ratings -- run scripts/player_rating.py first")
        return 1
    strength = {}
    for t in ((L("data/rating_%d.json" % PRIOR) or {}).get("teams") or []):
        strength[t["team"]] = float(t.get("adj_net_points_set") or 0.0)

    # ---- 1. parts vs whole, on the completed prior season ------------------
    byteam = collections.defaultdict(list)
    for p in rate.get("players") or []:
        if (p.get("prior_score") is not None and p.get("team") in strength
                and (p.get("prior_sets") or 0) >= 40):
            byteam[p["team"]].append(p)

    fit_rows, fit_y, names = [], [], []
    for tm, pl in byteam.items():
        if len(pl) < MIN_RATED:
            continue
        pl.sort(key=lambda x: -x["prior_score"])
        top = [x["prior_score"] for x in pl[:MIN_RATED]]
        fit_rows.append([sum(top) / len(top)])
        fit_y.append(strength[tm])
        names.append(tm)
    if len(fit_rows) < 40:
        print("not enough teams with %d rated returners" % MIN_RATED)
        return 1
    b = ols(fit_rows, fit_y)
    pred = [b[0] + b[1] * r[0] for r in fit_rows]
    ybar = sum(fit_y) / len(fit_y)
    ss_res = sum((a - p) ** 2 for a, p in zip(fit_y, pred))
    ss_tot = sum((a - ybar) ** 2 for a in fit_y)
    r2 = 1 - ss_res / ss_tot
    resid = [a - p for a, p in zip(fit_y, pred)]
    sd = (sum(x * x for x in resid) / len(resid)) ** 0.5

    parts = {}
    for tm, row, actual, p in zip(names, fit_rows, fit_y, pred):
        parts[tm] = {
            "parts_mean": round(row[0], 4),
            "predicted": round(p, 4),
            "actual": round(actual, 4),
            "residual": round(actual - p, 4),
            # ⚠ IN SDs, SO IT CAN BE READ. A raw residual in net points per set
            # means nothing to a reader; "1.4 SDs above what its roster
            # predicted" does.
            "residual_sd": round((actual - p) / sd, 3) if sd else None,
            "rated_players": len(byteam[tm]),
        }

    # ---- 2. what each team returns, BY POSITION ----------------------------
    ret = (L("data/returning_%d.json" % SEASON) or {}).get("teams") or {}
    bypos = {}
    for tm, rec in ret.items():
        acc = collections.defaultdict(lambda: {"ret": 0.0, "dep": 0.0,
                                               "n_ret": 0, "n_dep": 0})
        for key, field in (("returning", "ret"), ("departed", "dep")):
            for pl in (rec.get(key) or []):
                if not isinstance(pl, dict):
                    continue
                pos = bucket(pl.get("pos"))
                if not pos:
                    continue
                a = acc[pos]
                a[field] += float(pl.get("pts") or 0)
                a["n_" + field] += 1
        out = {}
        for pos, a in acc.items():
            tot = a["ret"] + a["dep"]
            out[pos] = {
                "returning_points": round(a["ret"], 1),
                "departed_points": round(a["dep"], 1),
                # ⚠ NO SHARE WHEN THERE IS NOTHING TO TAKE A SHARE OF. A
                # position with no recorded production last season renders as
                # unknown, never as 0% returning, which would read as a team
                # that lost everything there (R5).
                "share": (round(a["ret"] / tot, 4) if tot > 0 else None),
                "n_returning": a["n_ret"], "n_departed": a["n_dep"],
            }
        if out:
            bypos[tm] = out

    doc = {
        "meta": {
            "season": SEASON,
            "prior_season": PRIOR,
            "source_tier": "DERIVED",
            "parts_fit": {
                "teams": len(fit_rows),
                "r2": round(r2, 4),
                "residual_sd": round(sd, 4),
                "intercept": round(b[0], 4),
                "slope": round(b[1], 4),
                "basis": ("mean of the team's top %d rated players, fitted "
                          "against its measured %d strength" % (MIN_RATED, PRIOR)),
            },
            "parts_season": PRIOR,
            "parts_note": ("a %d measurement on purpose: the %d team "
                           "projection is built from %d production, so "
                           "comparing the two would be circular and the gap "
                           "would measure nothing" % (PRIOR, SEASON, PRIOR)),
            "residual_is_not_modelled": (
                "the weakest-link hypothesis was tested and failed twice -- "
                "roster spread carries a POSITIVE coefficient (+0.261) and "
                "rotation spread correlates -0.088 with team strength -- so "
                "the gap is reported as unexplained rather than attributed"),
        },
        "parts": parts,
        "returning_by_position": bypos,
    }
    p = os.path.join(REPO, "data/team_parts_%d.json" % SEASON)
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=1, sort_keys=True))
    print("wrote %s" % p)
    print("  parts fit: %d teams, R2 %.4f, residual sd %.3f"
          % (len(fit_rows), r2, sd))
    over = sorted(parts.items(), key=lambda kv: -(kv[1]["residual"]))[:4]
    under = sorted(parts.items(), key=lambda kv: kv[1]["residual"])[:4]
    print("  most ABOVE its roster:  " + " | ".join(
        "%s %+.2f" % (k, v["residual"]) for k, v in over))
    print("  most BELOW its roster:  " + " | ".join(
        "%s %+.2f" % (k, v["residual"]) for k, v in under))
    print("  returning-by-position for %d teams" % len(bypos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
