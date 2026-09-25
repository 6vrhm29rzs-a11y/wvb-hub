#!/usr/bin/env python3
"""Can MATCH FORECASTS run on the blend, and are the percentages honest? 2025.

Cody 2026-09-23: 2025 should be the starting point only; lean on 2026.
predict_2026 rated teams on last season alone. The blend (k=10, 0.25 hit-eff)
orders the rest of a season better (measure_blend_k_hiteff.py); this asks the
second question a PERCENTAGE needs: converted to points/set for the rally
model, are the resulting probabilities calibrated? One scale (pts/set per
blend unit) is fitted by log-likelihood on the even checkpoints and SCORED on
the odd ones, so the reported calibration is out of sample.


The 2026-08-27 k test (measure_blend_k.py) ran before the hit channel
shipped and found k=10 vs 13.5 not clear of zero. Re-run on the shipped
evidence (margin + 0.25 hit-eff): k=10 beats 13.5 with the CI clear of zero,
so digby_top25 adopts it via this receipt (Cody 2026-09-23: 2025 is a
starting point, lean on 2026).


Asked 2026-09-23 (Texas at Kentucky): predictions_2026.json rates every team
on the PRIOR season only, while the ranking blends in this season. Same
harness as measure_blend_hiteff: the prior-only variant (what the forecast
does today) against the shipped blend (margin + 0.25 hit-eff, k=13.5).
Verdict from a paired bootstrap on AUC, not a threshold of ours (R1).

(Original harness docstring follows.)
Does a hitting-efficiency evidence channel improve the blend? OOS on 2025.

The bake-off found adjusted hitting-efficiency differential the strongest
single factor on full seasons. This asks the EARLY-SEASON question: blending
the prior with margin-implied strengths (shipped), does mixing in
hit-eff-implied strengths at a pre-registered weight (0.25 / 0.50) predict
the rest of the season better? Same harness as measure_blend_upgrades:
checkpoint walk, paired bootstrap, ships only with the CI clear of zero.
"""
import json
import os
import random
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rating_factors as RF  # noqa: E402
import measure_blend_k as MK  # noqa: E402
KS = (2.0, 4.0, 7.0, 10.0, 13.5, 20.0)

K = 13.5
CHECKPOINTS = (0.03, 0.06, 0.12, 0.20, 0.35, 0.50, 0.65)
OUT = os.path.join(REPO, "data", "forecast_calibration_2025.json")


def load_hit():
    """gid -> team_id -> (K-E)/TA from the 2025 box scores, summed counts."""
    p = os.path.join(REPO, "data", "raw", "2025", "boxscores.jsonl")
    out = {}
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        gid = str(rec.get("game_id"))
        per = {}
        for t in rec.get("teams") or []:
            s = t.get("team_stats") or {}
            try:
                k = float(s.get("kills") or 0)
                e = float(s.get("attackErrors") or 0)
                ta = float(s.get("attackAttempts") or 0)
            except (TypeError, ValueError):
                continue
            if ta > 0:
                per[str(t.get("team_id"))] = (k - e) / ta
        if len(per) == 2:
            out[gid] = per
    return out


def main():
    matches = RF.load_matches()
    hit = load_hit()
    prior_by_name = MK.load_prior()
    doc = json.load(open(os.path.join(REPO, "data", "data_2025.json"),
                         encoding="utf-8"))
    id2name = dict((str(t.get("team_id")),
                    t.get("name_short") or t.get("name_full"))
                   for t in (doc.get("teams") or []))
    pv = [prior_by_name[n] for n in prior_by_name]
    pmu, psd = st.mean(pv), (st.pstdev(pv) or 1.0)
    prior_z = {}
    for tid, nm in id2name.items():
        if nm in prior_by_name:
            prior_z[tid] = (prior_by_name[nm] - pmu) / psd

    # attach the hit-eff DIFF (own - opp) to each match, home side's view
    n_hit = 0
    for m in matches:
        per = hit.get(m["gid"]) or {}
        hd = per.get(m["home"])
        ad = per.get(m["away"])
        m["hitdiff"] = (hd - ad) if (hd is not None and ad is not None) else None
        if m["hitdiff"] is not None:
            n_hit += 1
    print("matches %d, with hit-eff %d (%.1f%%)"
          % (len(matches), n_hit, 100.0 * n_hit / len(matches)))

    margins, hits = {}, {}
    for m in matches:
        margins.setdefault(m["home"], []).append(m["margin"])
        margins.setdefault(m["away"], []).append(-m["margin"])
        if m["hitdiff"] is not None:
            hits.setdefault(m["home"], []).append(m["hitdiff"])
            hits.setdefault(m["away"], []).append(-m["hitdiff"])
    import digby_top25 as D
    _, tau2 = D.variance_components(margins)
    tau = tau2 ** 0.5
    _, tau2h = D.variance_components(hits)
    tauh = tau2h ** 0.5
    home_adv = sum(m["margin"] for m in matches) / float(len(matches))
    hvals = [m["hitdiff"] for m in matches if m["hitdiff"] is not None]
    home_adv_h = sum(hvals) / float(len(hvals))
    print("tau margin %.2f  tau hitdiff %.4f  home %+.3f / %+.4f\n"
          % (tau, tauh, home_adv, home_adv_h))

    import simulate_2025 as SIM
    import math
    KB = 10.0
    CPS = (0.03, 0.06, 0.12, 0.20, 0.35, 0.50, 0.65)
    per_cp = []
    for frac in CPS:
        cut = int(len(matches) * frac)
        past, future = matches[:cut], matches[cut:]
        adj_m, adj_h = {}, {}
        for m in past:
            for side, sign in (("home", 1.0), ("away", -1.0)):
                t = m[side]
                opp = m["away"] if side == "home" else m["home"]
                zo = prior_z.get(opp)
                if zo is None:
                    continue
                hs = 1.0 if side == "home" else -1.0
                adj_m.setdefault(t, []).append(zo + (sign * m["margin"] - home_adv * hs) / tau)
                if m["hitdiff"] is not None:
                    adj_h.setdefault(t, []).append(zo + (sign * m["hitdiff"] - home_adv_h * hs) / tauh)
        sc = {}
        for t in set(list(prior_z) + list(adj_m)):
            vm, vh = adj_m.get(t) or [], adj_h.get(t) or []
            zp = prior_z.get(t)
            if not vm:
                if zp is not None:
                    sc[t] = zp
                continue
            mm = sum(vm) / len(vm)
            val = (0.75 * mm + 0.25 * sum(vh) / len(vh)) if vh else mm
            w = len(vm) / float(len(vm) + KB)
            sc[t] = (1 - w) * (zp or 0.0) + w * val
        rows = [(sc[m["home"]] - sc[m["away"]], m["home_win"]) for m in future
                if m["home"] in sc and m["away"] in sc]
        per_cp.append((frac, rows))

    # the rally model's own home edge, as predict_2026 uses it
    HA = 0.2675

    def probs(rows, s):
        return [(SIM.match_dist(SIM.rally_p(s * d + HA))["win"], y) for d, y in rows]

    def ll(rows, s):
        return sum(math.log(max(1e-9, p if y else 1 - p)) for p, y in probs(rows, s))

    fit = [r for i, (_, r) in enumerate(per_cp) if i % 2 == 0]
    held = [r for i, (_, r) in enumerate(per_cp) if i % 2 == 1]
    fit_rows = [x for r in fit for x in r]
    grid = [x / 20.0 for x in range(20, 121)]
    s_best = max(grid, key=lambda s: ll(fit_rows, s))
    print("fitted scale: %.2f pts/set per blend unit (tau %.2f)" % (s_best, tau))

    held_rows = [x for r in held for x in r]
    P = probs(held_rows, s_best)
    brier = sum((p - y) ** 2 for p, y in P) / len(P)
    print("HELD-OUT (%d matches) Brier %.4f" % (len(P), brier))
    buckets = []
    for lo in range(0, 100, 10):
        b = [(p, y) for p, y in P if lo / 100.0 <= max(p, 1 - p) < (lo + 10) / 100.0 or (lo == 90 and max(p, 1 - p) >= 1.0)]
        if not b:
            continue
        # fold to the favourite so buckets read 50-100
        fav = [(max(p, 1 - p), (y if p >= 0.5 else 1 - y)) for p, y in b]
        mp = sum(p for p, _ in fav) / len(fav)
        hit = sum(y for _, y in fav) / float(len(fav))
        buckets.append({"bucket": "%d-%d%%" % (lo, lo + 10), "n": len(fav),
                        "predicted": round(mp, 4), "actual": round(hit, 4),
                        "gap_pts": round(100 * (hit - mp), 1)})
        print("  fav %3d-%3d%%  n=%4d  said %.1f%%  won %.1f%%  gap %+.1f"
              % (lo, lo + 10, len(fav), 100 * mp, 100 * hit, 100 * (hit - mp)))
    # baseline: prior-only percentages on the same held-out matches
    # SAME held-out matches, prior-only (what predict_2026 did before), with
    # its OWN best scale -- so the comparison is not rigged by a bad scale.
    prow = []
    for i, (frac, r) in enumerate(per_cp):
        cut = int(len(matches) * frac)
        rr = [(prior_z[m["home"]] - prior_z[m["away"]], m["home_win"])
              for m in matches[cut:] if m["home"] in prior_z and m["away"] in prior_z]
        prow.append(rr)
    pfit = [x for i, r in enumerate(prow) if i % 2 == 0 for x in r]
    pheld = [x for i, r in enumerate(prow) if i % 2 == 1 for x in r]
    ps = max(grid, key=lambda s: ll(pfit, s))
    PP = probs(pheld, ps)
    pbrier = sum((p - y) ** 2 for p, y in PP) / len(PP)
    print("PRIOR-ONLY on the same held-out: scale %.2f, Brier %.4f (n=%d)"
          % (ps, pbrier, len(PP)))
    json.dump({"k": KB, "hit_mix": 0.25, "scale_pts_per_unit": s_best,
               "home_adv_pts": HA, "fit_on": "even checkpoints", "scored_on": "odd checkpoints",
               "heldout_n": len(P), "heldout_brier": round(brier, 5),
               "reliability": buckets, "prior_only_heldout_brier": round(pbrier, 5)}, open(OUT, "w"), indent=1)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    sys.exit(main())
