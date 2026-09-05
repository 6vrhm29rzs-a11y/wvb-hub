#!/usr/bin/env python3
"""Does a hitting-efficiency evidence channel improve the blend? OOS on 2025.

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

K = 13.5
CHECKPOINTS = (0.03, 0.06, 0.12, 0.20, 0.35, 0.50, 0.65)
OUT = os.path.join(REPO, "data", "blend_hiteff_2025.json")


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

    variants = ["V0_margin", "V4_mix25", "V4_mix50", "V4_hitonly"]
    pooled = dict((v, []) for v in variants)
    paired_all = dict((v, []) for v in variants)

    for frac in CHECKPOINTS:
        cut = int(len(matches) * frac)
        past, future = matches[:cut], matches[cut:]
        if len(future) < 300:
            continue
        seen, adj_m, adj_h = {}, {}, {}
        for m in past:
            for side, sign in (("home", 1.0), ("away", -1.0)):
                t = m[side]
                opp = m["away"] if side == "home" else m["home"]
                seen[t] = seen.get(t, 0) + 1
                zo = prior_z.get(opp)
                if zo is None:
                    continue
                adj_m.setdefault(t, []).append(
                    zo + (sign * m["margin"]
                          - home_adv * (1.0 if side == "home" else -1.0)) / tau)
                if m["hitdiff"] is not None:
                    adj_h.setdefault(t, []).append(
                        zo + (sign * m["hitdiff"]
                              - home_adv_h * (1.0 if side == "home" else -1.0)
                              ) / tauh)

        def blend_mix(wh):
            out = {}
            for t in set(list(prior_z) + list(adj_m)):
                vm = adj_m.get(t) or []
                vh = adj_h.get(t) or []
                vals = None
                if vm and vh and wh > 0:
                    mm = sum(vm) / len(vm)
                    hh = sum(vh) / len(vh)
                    vals = (1 - wh) * mm + wh * hh
                    n = len(vm)
                elif vm:
                    vals = sum(vm) / len(vm)
                    n = len(vm)
                else:
                    zp = prior_z.get(t)
                    if zp is not None:
                        out[t] = zp
                    continue
                zp = prior_z.get(t)
                if zp is None:
                    zp = 0.0
                w = n / float(n + K)
                out[t] = (1 - w) * zp + w * vals
            return out

        for v, wh in (("V0_margin", 0.0), ("V4_mix25", 0.25),
                      ("V4_mix50", 0.50), ("V4_hitonly", 1.0)):
            sc = blend_mix(wh)
            scored = []
            for m in future:
                zh, za = sc.get(m["home"]), sc.get(m["away"])
                if zh is None or za is None:
                    continue
                scored.append((zh - za, m["home_win"]))
            a = RF.auc(scored)
            pooled[v].append(a)
            paired_all[v].append(scored)
        print("  %4.0f%%: " % (frac * 100) + "  ".join(
            "%s %.4f" % (v, pooled[v][-1]) for v in variants))

    print("\npooled mean AUC:")
    for v in variants:
        print("  %-12s %.5f" % (v, st.mean(pooled[v])))
    rng = random.Random(20260904)
    print("\npaired bootstrap (2000x), delta vs margin-only, pooled:")
    verdicts = {}
    for v in variants[1:]:
        deltas = []
        for _ in range(2000):
            tot0 = tot1 = 0.0
            for ci in range(len(paired_all["V0_margin"])):
                base = paired_all["V0_margin"][ci]
                cand = paired_all[v][ci]
                n = min(len(base), len(cand))
                idx = [rng.randrange(n) for _ in range(n)]
                tot0 += RF.auc([base[i] for i in idx])
                tot1 += RF.auc([cand[i] for i in idx])
            deltas.append((tot1 - tot0) / len(paired_all["V0_margin"]))
        deltas.sort()
        lo, hi, mid = deltas[50], deltas[1949], deltas[1000]
        verdict = "SHIPS" if lo > 0 else ("HURTS" if hi < 0 else "inconclusive")
        verdicts[v] = {"delta": mid, "ci": [lo, hi], "verdict": verdict}
        print("  %-12s %+0.5f  [%+0.5f, %+0.5f]  %s" % (v, mid, lo, hi, verdict))
    json.dump({"k": K, "pooled": dict((v, st.mean(pooled[v])) for v in variants),
               "verdicts": verdicts}, open(OUT, "w"), indent=1)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    sys.exit(main())
