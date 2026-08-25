#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""How fast should a ranking react to a result? Measured on 2025.

    python3 scripts/measure_blend_k.py     -> data/blend_k_2025.json

WHY. Cody, looking at the live Top 25: "the rankings aren't true to what i feel
and who i see... texas looks a hot mess and is too high." Texas is 0-1, beaten
3-1 at home by Arizona St. and outscored by 4.25 points per set, and it sits
3rd. That is not a bug -- 93% of its rating is still the preseason projection,
because the blend weight is

    w = n / (n + k),   k = 13.5 matches

and one match therefore moves a team 7%. k was DERIVED (per-match variance over
the projection's own error variance), not chosen. But a derivation rests on its
assumptions, and the honest way to answer "is 7% too slow" is to check whether a
different k would have predicted 2025 better.

THE TEST. Walk the 2025 season in date order. At a checkpoint, every team has a
prior (its 2024 strength) and some number of played matches. Blend them at a
grid of k, then score the blended rating against every match that happens AFTER
the checkpoint. The k that predicts the rest of the season best is the right
answer, and it is an answer rather than an opinion.

⚠ THE PRIOR HAS TO BE FROM BEFORE THE SEASON. `strength_2024.json` is used
precisely because it cannot contain 2025 information. Using a 2025-derived
rating as the "prior" would leak the outcome into the thing being tested and
would make every k look good.

Python 3.9 target.
"""

import json
import os
import statistics as st
import sys
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rating_factors as RF  # noqa: E402

OUT = os.path.join(REPO, "data", "blend_k_2025.json")
K_GRID = [0.5, 1, 2, 3, 4, 6, 8, 10, 13.5, 18, 25, 35, 50, 1e9]
# ⚠ THE EARLY CHECKPOINTS ARE THE POINT. Cody's complaint is about a team that
# has played ONE match, so a grid that starts at 20% of the season (six matches
# each) never tests the regime he is looking at. 3% is roughly where the 2026
# season is as this is written.
CHECKPOINTS = (0.03, 0.06, 0.12, 0.20, 0.35, 0.50, 0.65)


def load_prior():
    # type: () -> Dict[str, float]
    p = os.path.join(REPO, "data", "strength_2024.json")
    if not os.path.exists(p):
        return {}
    return (json.load(open(p, encoding="utf-8")).get("teams") or {})


def main():
    matches = RF.load_matches()
    if not matches:
        print("no matches")
        return 1
    prior_by_name = load_prior()

    # team_id -> name, so the 2024 prior can be attached
    doc = json.load(open(os.path.join(REPO, "data", "data_2025.json"), encoding="utf-8"))
    id2name = dict((str(t.get("team_id")), t.get("name_short") or t.get("name_full"))
                   for t in (doc.get("teams") or []))

    pv = [prior_by_name[n] for n in prior_by_name]
    pmu, psd = st.mean(pv), (st.pstdev(pv) or 1.0)
    prior_z = {}
    for tid, nm in id2name.items():
        if nm in prior_by_name:
            prior_z[tid] = (prior_by_name[nm] - pmu) / psd

    # between-team SD of per-match margin, in points/set -- the scale that turns
    # an observed margin into the same z units the prior lives in.
    margins = {}
    for m in matches:
        margins.setdefault(m["home"], []).append(m["margin"])
        margins.setdefault(m["away"], []).append(-m["margin"])
    sigma2, tau2 = RF.variance_components(margins) if hasattr(RF, "variance_components") else (None, None)
    if sigma2 is None:
        import digby_top25 as D
        sigma2, tau2 = D.variance_components(dict((k, v) for k, v in margins.items()))
    tau = tau2 ** 0.5
    global HOME_ADV
    HOME_ADV = sum(m["margin"] for m in matches) / float(len(matches))
    print("prior teams matched: %d   tau (between-team SD) = %.2f pts/set   "
          "home advantage = %+.3f pts/set\n" % (len(prior_z), tau, HOME_ADV))

    results = {}
    early = {}
    paired = {}
    adj_results = {}
    adj_paired = {}
    adj_early = {}
    adj_meta = {}
    for frac in CHECKPOINTS:
        cut = int(len(matches) * frac)
        seen, obs, adj = {}, {}, {}
        for m in matches[:cut]:
            for side, sign in (("home", 1.0), ("away", -1.0)):
                t = m[side]
                opp = m["away"] if side == "home" else m["home"]
                seen[t] = seen.get(t, 0) + 1
                obs.setdefault(t, []).append(sign * m["margin"])
                # OPPONENT-ADJUSTED: what strength does this result IMPLY?
                # A team that loses by 4.25 a set to the 7th-best team in the
                # country is not a bad team; a team that loses by 4.25 to the
                # 200th is. The raw margin cannot tell those apart -- it scores
                # both as if the opponent were average, which is what the Top 25
                # currently does and what the page admits when it says the
                # schedule is barely adjusted for early.
                #
                #   implied strength = opponent's strength + how far you beat
                #                      them, in the same units
                #
                # This is exactly what the ridge computes once a schedule graph
                # exists; before then the prior stands in for the opponent.
                zo = prior_z.get(opp)
                if zo is not None:
                    hs = sign if side == "home" else -sign
                    adj.setdefault(t, []).append(
                        zo + (sign * m["margin"] - HOME_ADV * (1.0 if side == "home" else -1.0)) / tau)
        future = matches[cut:]
        if len(future) < 300:
            continue
        per_k = {}
        for k in K_GRID:
            scored = []
            for m in future:
                zh, za = blended(m["home"], k, prior_z, seen, obs, tau), \
                         blended(m["away"], k, prior_z, seen, obs, tau)
                if zh is None or za is None:
                    continue
                scored.append((zh - za, m["home_win"]))
            # the same k, but with the opponent-adjusted season term
            scored_adj = []
            for m in future:
                zh = blended(m["home"], k, prior_z, seen, adj, tau, raw=False)
                za = blended(m["away"], k, prior_z, seen, adj, tau, raw=False)
                if zh is None or za is None:
                    continue
                scored_adj.append((zh - za, m["home_win"]))
            if len(scored_adj) >= 200:
                adj_results.setdefault(k, []).append(RF.auc(scored_adj))
                adj_paired.setdefault(frac, {})[k] = scored_adj
                adj_early.setdefault(frac, {})[k] = RF.auc(scored_adj)
            if len(scored) < 200:
                continue
            a = RF.auc(scored)
            results.setdefault(k, []).append(a)
            per_k[k] = scored
            early.setdefault(frac, {})[k] = a
        paired[frac] = per_k
        played = [seen.get(t, 0) for t in seen]
        print("  checkpoint %4.0f%% -- %d matches played, median %d per team, "
              "%d to predict" % (100 * frac, cut,
                                 sorted(played)[len(played) // 2] if played else 0,
                                 len(future)))

    rows = []
    for k in K_GRID:
        if k not in results:
            continue
        rows.append((k, sum(results[k]) / len(results[k]), len(results[k])))
    rows.sort(key=lambda r: -r[1])
    print("\n  k       mean AUC over checkpoints")
    for k, a, n in sorted(rows, key=lambda r: r[0]):
        label = "%g" % k if k < 1e8 else "inf (prior only)"
        star = "   <-- best" if k == rows[0][0] else ""
        shipped = "   <-- SHIPPED" if abs(k - 13.5) < 1e-9 else ""
        print("  %-16s %.5f%s%s" % (label, a, star, shipped))

    # ⚠ A DIFFERENCE IN THE THIRD DECIMAL IS NOT A FINDING WITHOUT A CI.
    import random
    rng = random.Random(23)
    cis = {}
    for k in (13.5, rows[0][0]):
        if k == 13.5:
            continue
        los, his = [], []
        for frac, per_k in paired.items():
            if 13.5 in per_k and k in per_k:
                lo, hi = RF.boot_delta(per_k[13.5], per_k[k], rng)
                los.append(lo)
                his.append(hi)
        if los:
            cis[k] = (sum(los) / len(los), sum(his) / len(his))
            print("\n  best k=%g vs shipped k=13.5:  %+0.5f  CI [%+0.5f, %+0.5f]  %s"
                  % (k, rows[0][1] - dict((r[0], r[1]) for r in rows)[13.5],
                     cis[k][0], cis[k][1],
                     "CLEAR OF ZERO" if cis[k][0] > 0 else "not distinguishable"))

    print("\n  AUC by k, at the EARLIEST checkpoints (the regime we are in now):")
    for frac in sorted(early):
        if frac > 0.12:
            continue
        row = early[frac]
        bk = max(row, key=lambda x: row[x])
        print("    %4.0f%% of season: best k = %-6s (AUC %.4f)   k=13.5 -> %.4f"
              % (100 * frac, "%g" % bk if bk < 1e8 else "inf", row[bk],
                 row.get(13.5, float("nan"))))

    if adj_results:
        print("\n  OPPONENT-ADJUSTED SEASON TERM vs raw margin, same k:")
        import random as _r
        rng2 = _r.Random(99)
        for k in sorted(adj_results):
            if k not in results:
                continue
            a_raw = sum(results[k]) / len(results[k])
            a_adj = sum(adj_results[k]) / len(adj_results[k])
            los, his = [], []
            for frac in paired:
                if k in paired[frac] and k in adj_paired.get(frac, {}):
                    lo, hi = RF.boot_delta(paired[frac][k], adj_paired[frac][k], rng2)
                    los.append(lo)
                    his.append(hi)
            lo = sum(los) / len(los) if los else 0.0
            hi = sum(his) / len(his) if his else 0.0
            mark = "  <-- shipped k" if abs(k - 13.5) < 1e-9 else ""
            print("    k=%-6s raw %.5f  adj %.5f  %+0.5f  CI [%+0.5f, %+0.5f]  %s%s"
                  % ("%g" % k if k < 1e8 else "inf", a_raw, a_adj, a_adj - a_raw,
                     lo, hi, "HELPS" if lo > 0 else "not distinguishable", mark))

    if adj_early:
        print("\n  WITH the opponent adjustment, best k at each checkpoint:")
        for frac in sorted(adj_early):
            row = adj_early[frac]
            bk = max(row, key=lambda x: row[x])
            print("    %4.0f%% of season: best k = %-6s (AUC %.4f)   k=13.5 -> %.4f"
                  % (100 * frac, "%g" % bk if bk < 1e8 else "inf", row[bk],
                     row.get(13.5, float("nan"))))
        pooled = dict((k, sum(v) / len(v)) for k, v in adj_results.items())
        bk = max(pooled, key=lambda x: pooled[x])
        print("    pooled best k = %g (AUC %.5f)" % (bk, pooled[bk]))
        # ⚠ AND IS IT DISTINGUISHABLE FROM THE SHIPPED VALUE? The adjustment is
        # worth +0.021; moving k from 13.5 to 10 is worth a fraction of that,
        # and a point estimate is not a reason to change a constant.
        import random as _r3
        rng3 = _r3.Random(1234)
        los, his = [], []
        for frac in adj_paired:
            if bk in adj_paired[frac] and 13.5 in adj_paired[frac]:
                lo, hi = RF.boot_delta(adj_paired[frac][13.5], adj_paired[frac][bk], rng3)
                los.append(lo)
                his.append(hi)
        if los:
            lo, hi = sum(los) / len(los), sum(his) / len(his)
            print("    k=%g vs k=13.5 (both adjusted): %+0.5f  CI [%+0.5f, %+0.5f]  %s"
                  % (bk, pooled[bk] - pooled.get(13.5, 0.0), lo, hi,
                     "CLEAR OF ZERO" if lo > 0 else "not distinguishable"))
            _favour = sum(1 for f in adj_early
                          if max(adj_early[f], key=lambda x: adj_early[f][x]) < 13.5)
            print("    checkpoints whose best k is BELOW 13.5: %d of %d"
                  % (_favour, len(adj_early)))
            adj_meta["best_k"] = bk
            adj_meta["best_k_ci_vs_13_5"] = [round(lo, 5), round(hi, 5)]
            adj_meta["best_k_clear_of_zero"] = bool(lo > 0)
            adj_meta["checkpoints_favouring_faster"] = [_favour, len(adj_early)]
            adj_meta["auc_at_best_k"] = round(pooled[bk], 5)
            adj_meta["auc_at_13_5"] = round(pooled.get(13.5, 0.0), 5)

    best = rows[0]
    ship = [r for r in rows if abs(r[0] - 13.5) < 1e-9]
    doc_out = {
        "meta": {
            "season": 2025,
            "question": ("how fast should a ranking react to a result? "
                         "w = n/(n+k); smaller k reacts faster"),
            "prior": "data/strength_2024.json -- cannot contain 2025 information",
            "method": ("blend prior with observed margin at a checkpoint, score "
                       "every match AFTER it; the k that predicts the rest of the "
                       "season best wins"),
            "tau_between_team_sd": round(tau, 4),
            "checkpoints": list(CHECKPOINTS),
            "best_k": best[0] if best[0] < 1e8 else None,
            "best_auc": round(best[1], 5),
            "shipped_k": 13.5,
            "shipped_auc": round(ship[0][1], 5) if ship else None,
        },
        "opponent_adjusted": adj_meta,
        "grid": [{"k": (k if k < 1e8 else None), "auc": round(a, 5)} for k, a, _ in
                 sorted(rows, key=lambda r: r[0])],
    }
    json.dump(doc_out, open(OUT, "w"), indent=1)
    print("\nwrote %s" % OUT)
    return 0


HOME_ADV = 0.0          # measured in main() from the season itself


def blended(team, k, prior_z, seen, obs, tau, raw=True):
    # type: (str, float, Dict, Dict, Dict, float, bool) -> Optional[float]
    """Prior blended with what has been seen.

    `raw=True`  -- obs holds margins; divide by tau to reach z units.
    `raw=False` -- obs already holds implied strengths in z units, because the
                   opponent's own strength has been added in. Dividing again
                   would be a units error, and a silent one: the numbers would
                   still be plausible and every team would look average.
    """
    zp = prior_z.get(team)
    vals = obs.get(team) or []
    n = len(vals) if not raw else seen.get(team, 0)
    if zp is None and not n:
        return None
    if zp is None:
        zp = 0.0
    if not n or not vals:
        return zp
    zo = (sum(vals) / float(len(vals)))
    if raw:
        zo = zo / tau
    w = n / float(n + k) if k < 1e8 else 0.0
    return (1 - w) * zp + w * zo


if __name__ == "__main__":
    sys.exit(main())
