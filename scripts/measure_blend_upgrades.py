#!/usr/bin/env python3
"""Do two candidate blend upgrades actually predict better? Measured on 2025.

Cody, 2026-09-04: make the rankings the best version of anything out there.
The way there is R1's: candidate improvements are SCORED out of sample, and
only a winner with its bootstrap CI clear of zero ships.

Candidates, against the shipped method (prior + opponent-adjusted margins,
opponent = preseason prior, k = 13.5):

  V1  ITERATED opponent adjustment -- score each opponent by their BLENDED
      rating at the checkpoint instead of their preseason prior, then
      re-blend. Mid-season, an opponent's blend knows more than their prior;
      the question is whether that helps before the ridge takes over.
  V2  MARGIN CAP -- clip each match margin to +/-8 (and +/-10) points/set
      before adjusting. A 15-point blowout says little more than an
      8-point one; a linear margin term disagrees. Massey caps for the
      same reason.

Method identical to measure_blend_k.py: walk 2025 in date order, blend at a
checkpoint, score every match after it (AUC on home-win), pool checkpoints.
Deltas are computed PAIRED on the same future matches, bootstrap 2000x.
"""
import json
import os
import random
import statistics as st
import sys
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rating_factors as RF  # noqa: E402
import measure_blend_k as MK  # noqa: E402

K = 13.5
CHECKPOINTS = (0.03, 0.06, 0.12, 0.20, 0.35, 0.50, 0.65)
OUT = os.path.join(REPO, "data", "blend_upgrades_2025.json")


def adj_obs(matches_seen, prior_z, opp_score, tau, home_adv, cap=None):
    """implied strengths per team, opponent scored by `opp_score`."""
    adj = {}
    for m in matches_seen:
        for side, sign in (("home", 1.0), ("away", -1.0)):
            t = m[side]
            opp = m["away"] if side == "home" else m["home"]
            zo = opp_score.get(opp)
            if zo is None:
                continue
            mg = sign * m["margin"]
            if cap is not None:
                mg = max(-cap, min(cap, mg))
            adj.setdefault(t, []).append(
                zo + (mg - home_adv * (1.0 if side == "home" else -1.0)) / tau)
    return adj


def blend_all(prior_z, seen, adj, tau):
    out = {}
    for t in set(list(prior_z.keys()) + list(adj.keys())):
        z = MK.blended(t, K, prior_z, seen, adj, tau, raw=False)
        if z is not None:
            out[t] = z
    return out


def auc_scored(future, scores):
    sc = []
    for m in future:
        zh, za = scores.get(m["home"]), scores.get(m["away"])
        if zh is None or za is None:
            continue
        sc.append((zh - za, m["home_win"]))
    return sc


def main():
    matches = RF.load_matches()
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
    margins = {}
    for m in matches:
        margins.setdefault(m["home"], []).append(m["margin"])
        margins.setdefault(m["away"], []).append(-m["margin"])
    import digby_top25 as D
    sigma2, tau2 = D.variance_components(margins)
    tau = tau2 ** 0.5
    home_adv = sum(m["margin"] for m in matches) / float(len(matches))
    print("teams with prior %d  tau %.2f  home %+.3f  k=%.1f\n"
          % (len(prior_z), tau, home_adv, K))

    variants = ["V0_shipped", "V1_iter1", "V1_iter2",
                "V2_cap8", "V2_cap10", "V3_iter1_cap8"]
    pooled = dict((v, []) for v in variants)
    paired_all = dict((v, []) for v in variants)

    for frac in CHECKPOINTS:
        cut = int(len(matches) * frac)
        past, future = matches[:cut], matches[cut:]
        if len(future) < 300:
            continue
        seen = {}
        for m in past:
            seen[m["home"]] = seen.get(m["home"], 0) + 1
            seen[m["away"]] = seen.get(m["away"], 0) + 1

        def run(opp_score, cap):
            adj = adj_obs(past, prior_z, opp_score, tau, home_adv, cap)
            return blend_all(prior_z, seen, adj, tau)

        s0 = run(prior_z, None)                    # shipped
        s_i1 = run(s0, None)                       # iterate once
        s_i2 = run(s_i1, None)                     # twice
        s_c8 = run(prior_z, 8.0)
        s_c10 = run(prior_z, 10.0)
        s_i1c8 = run(run(prior_z, 8.0), 8.0)
        row = {}
        for v, sc in (("V0_shipped", s0), ("V1_iter1", s_i1),
                      ("V1_iter2", s_i2), ("V2_cap8", s_c8),
                      ("V2_cap10", s_c10), ("V3_iter1_cap8", s_i1c8)):
            scored = auc_scored(future, sc)
            a = RF.auc(scored)
            pooled[v].append(a)
            paired_all[v].append(scored)
            row[v] = a
        print("  %4.0f%%: " % (frac * 100) +
              "  ".join("%s %.4f" % (v.split("_")[0] + v.split("_")[-1][:5],
                                     row[v]) for v in variants))

    print("\npooled mean AUC:")
    for v in variants:
        print("  %-14s %.5f" % (v, st.mean(pooled[v])))

    # paired bootstrap on the DELTA vs shipped, pooled over checkpoints
    rng = random.Random(20260904)
    print("\npaired bootstrap (2000x), delta vs shipped, pooled:")
    verdicts = {}
    for v in variants[1:]:
        deltas = []
        for _ in range(2000):
            tot0 = tot1 = 0.0
            npts = 0
            for ci in range(len(paired_all["V0_shipped"])):
                base = paired_all["V0_shipped"][ci]
                cand = paired_all[v][ci]
                n = min(len(base), len(cand))
                idx = [rng.randrange(n) for _ in range(n)]
                tot0 += RF.auc([base[i] for i in idx])
                tot1 += RF.auc([cand[i] for i in idx])
                npts += 1
            deltas.append((tot1 - tot0) / npts)
        deltas.sort()
        lo, hi = deltas[50], deltas[1949]
        mid = deltas[1000]
        verdict = "SHIPS" if lo > 0 else ("HURTS" if hi < 0 else "inconclusive")
        verdicts[v] = {"delta": mid, "ci": [lo, hi], "verdict": verdict}
        print("  %-14s %+0.5f  [%+0.5f, %+0.5f]  %s" % (v, mid, lo, hi, verdict))

    json.dump({"_doc": __doc__.strip().split("\n")[0],
               "k": K, "pooled": dict((v, st.mean(pooled[v])) for v in variants),
               "verdicts": verdicts}, open(OUT, "w"), indent=1)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    sys.exit(main())
