#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fit the Pythagorean exponent for volleyball on a COMPLETE season.

Pythagorean win expectation is pts_for^x / (pts_for^x + pts_against^x). The
exponent x is sport-specific and is not ours to guess -- baseball's 1.83 and
basketball's ~14 are both fitted numbers, and volleyball's rally scoring sits
nowhere near either. So it is fitted here on 2025, a season that is over, and
the fit is reported with its error so the number on the page can say how well
it actually predicts (R1: no interpretation before the number exists).

Writes data/pythagorean_fit.json. The 2026 page reads the exponent from that
receipt rather than carrying a literal.
"""
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FIT_SEASON = int(os.environ.get("WVB_FIT_SEASON", "2025"))
OUT = os.path.join(REPO, "data", "pythagorean_fit.json")


def main():
    import season_counts as SC
    doc = json.load(io.open(os.path.join(REPO, "data/data_%d.json" % FIT_SEASON),
                            encoding="utf-8"))
    name = {t["team_id"]: t.get("name_short") for t in doc["teams"]}
    corr = SC.corrections(FIT_SEASON)

    pf, pa, w, l = {}, {}, {}, {}
    for g in doc["games"]:
        if (g.get("game_state") or g.get("state")) != "F":
            continue
        g = SC.apply_correction(g, corr)
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        wi = SC.winner_index(g)
        if wi is None:
            continue
        ls = g.get("linescores") or []
        # ⚠ SCOREBOARD POINTS, from the set scores -- not kills+aces+blocks.
        # Pythagorean is about every point the scoreboard moved, including the
        # ones the opponent handed over; the earned-points formula is a
        # different quantity and must not be substituted here (R4).
        a = sum(int(x.get("visit") or 0) for x in ls)
        h = sum(int(x.get("home") or 0) for x in ls)
        if a + h < 30:
            continue
        ids = [str(t.get("team_id")) for t in ts]
        # the built dataset carries the display name on the team itself
        for _i, _t in enumerate(ts):
            if _t.get("name_short"):
                name[str(_t.get("team_id"))] = _t["name_short"]
        home_i = 0 if ts[0].get("is_home") else 1
        for i, tid in enumerate(ids):
            nm = name.get(tid)
            if not nm:
                continue
            mine = h if i == home_i else a
            theirs = a if i == home_i else h
            pf[nm] = pf.get(nm, 0) + mine
            pa[nm] = pa.get(nm, 0) + theirs
            if i == wi:
                w[nm] = w.get(nm, 0) + 1
            else:
                l[nm] = l.get(nm, 0) + 1

    teams = [t for t in pf if (w.get(t, 0) + l.get(t, 0)) >= 15]
    print("fitting on %d teams with 15+ counted matches in %d" % (len(teams), FIT_SEASON))

    def rmse(x):
        tot = 0.0
        for t in teams:
            f, a = float(pf[t]), float(pa[t])
            pred = f ** x / (f ** x + a ** x)
            act = w.get(t, 0) / float(w.get(t, 0) + l.get(t, 0))
            tot += (pred - act) ** 2
        return (tot / len(teams)) ** 0.5

    best, bx = None, None
    x = 3.0
    while x <= 20.0:
        e = rmse(x)
        if best is None or e < best:
            best, bx = e, x
        x += 0.05
    # refine
    lo, hi = bx - 0.05, bx + 0.05
    for _ in range(40):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if rmse(m1) < rmse(m2):
            hi = m2
        else:
            lo = m1
    bx = round((lo + hi) / 2, 3)
    best = rmse(bx)

    # how much better than the naive "everyone is .500"?
    import statistics
    acts = [w.get(t, 0) / float(w.get(t, 0) + l.get(t, 0)) for t in teams]
    base = (sum((0.5 - a) ** 2 for a in acts) / len(acts)) ** 0.5
    mean_base = statistics.mean(acts)
    base_mean = (sum((mean_base - a) ** 2 for a in acts) / len(acts)) ** 0.5

    rec = {"season_fitted_on": FIT_SEASON, "exponent": bx,
           "rmse_win_pct": round(best, 4),
           "rmse_if_everyone_500": round(base, 4),
           "rmse_if_everyone_league_mean": round(base_mean, 4),
           "n_teams": len(teams),
           "what_it_is": ("pts_for^x / (pts_for^x + pts_against^x), on SCOREBOARD "
                          "points from the set scores -- not the kills+aces+blocks "
                          "earned-points formula, which is a different quantity"),
           "how_to_read": ("RMSE is in win-percentage points. Compare it to the "
                           "two baselines: a model that says every team is .500, "
                           "and one that says every team is the league mean. A "
                           "Pythagorean worth showing beats both clearly."),
           "caveat": ("Fitted on a COMPLETE season and applied to a partial one. "
                      "Early-season teams have small point totals, so their "
                      "expectation is noisier than this RMSE suggests.")}
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(rec, indent=1))
    print("  exponent  %.3f" % bx)
    print("  RMSE      %.4f win%%  (everyone .500: %.4f · league mean: %.4f)"
          % (best, base, base_mean))
    print("  -> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
