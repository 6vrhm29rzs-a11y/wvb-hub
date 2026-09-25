#!/usr/bin/env python3
"""Should the SEASON SIMULATOR start from the blend? Backtest on 2025.

Cody 2026-09-24: 2025 is the starting point only; lean on 2026. The match
forecasts moved to the blend on 2026-09-23 (measure_forecast_calibration).
simulate_season_2026 still starts every team from last season: mean =
0.860 x prior + 0.025, strength redrawn each iteration with SD 2.12.

Two candidates, played through the rest of 2025 from three checkpoints:
  PRIOR  -- what ships: last season shrunk, fixed SD 2.12, played results kept
  BLEND  -- the Rankings blend (k=10, 0.25 hit-eff) x the calibrated scale,
            and a per-team SD that NARROWS with matches played:
            1 / sd^2 = 1 / 2.12^2 + n / sigma^2   (sigma^2 = per-match margin
            variance, measured on the same season -- standard normal update,
            no constant chosen here)
Scored on each team's final D-I win total: 80% band coverage (the shipped
simulator's own test, 87.3% at season start) and absolute error of the
median, compared with a paired bootstrap. Ships only with the CI clear of
zero (R1).
"""
import json
import math
import os
import random
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rating_factors as RF          # noqa: E402
import measure_blend_k as MK         # noqa: E402
import measure_forecast_calibration as MFC  # noqa: E402
import simulate_2025 as SIM          # noqa: E402
import digby_top25 as D              # noqa: E402

KB = 10.0
CPS = (0.20, 0.35, 0.50)
ITERS = 2000
PRIOR_SLOPE, PRIOR_INTERCEPT, PRIOR_SD = 0.8597, 0.0246, 2.123
OUT = os.path.join(REPO, "data", "sim_blend_2025.json")


def main():
    matches = RF.load_matches()
    hit = MFC.load_hit()
    prior_raw = MK.load_prior()
    doc = json.load(open(os.path.join(REPO, "data", "data_2025.json")))
    id2name = dict((str(t.get("team_id")), t.get("name_short") or t.get("name_full"))
                   for t in doc.get("teams") or [])
    pv = list(prior_raw.values())
    pmu = sum(pv) / len(pv)
    psd = (sum((x - pmu) ** 2 for x in pv) / len(pv)) ** 0.5
    prior_pts, prior_z = {}, {}
    for tid, nm in id2name.items():
        if nm in prior_raw:
            prior_pts[tid] = prior_raw[nm]
            prior_z[tid] = (prior_raw[nm] - pmu) / psd
    for m in matches:
        per = hit.get(m["gid"]) or {}
        hd, ad = per.get(m["home"]), per.get(m["away"])
        m["hitdiff"] = (hd - ad) if (hd is not None and ad is not None) else None
    margins, hits = {}, {}
    for m in matches:
        margins.setdefault(m["home"], []).append(m["margin"])
        margins.setdefault(m["away"], []).append(-m["margin"])
        if m["hitdiff"] is not None:
            hits.setdefault(m["home"], []).append(m["hitdiff"])
            hits.setdefault(m["away"], []).append(-m["hitdiff"])
    sigma2, tau2 = D.variance_components(margins)
    tau = tau2 ** 0.5
    _, tau2h = D.variance_components(hits)
    tauh = tau2h ** 0.5
    home_adv = sum(m["margin"] for m in matches) / float(len(matches))
    hv = [m["hitdiff"] for m in matches if m["hitdiff"] is not None]
    home_adv_h = sum(hv) / float(len(hv))
    cal = json.load(open(os.path.join(REPO, "data", "forecast_calibration_2025.json")))
    scale, HA = cal["scale_pts_per_unit"], cal["home_adv_pts"]
    print("sigma^2 %.2f  tau %.2f  scale %.2f" % (sigma2, tau, scale))

    teams = sorted(set(prior_z))
    idx = {t: i for i, t in enumerate(teams)}
    final_w = np.zeros(len(teams))
    for m in matches:
        w = m["home"] if m["home_sets"] > m["away_sets"] else m["away"]
        if w in idx:
            final_w[idx[w]] += 1

    grid = np.linspace(0.10, 0.90, 1601)
    t25 = np.array([SIM.set_win_prob(x, 25) for x in grid])
    t15 = np.array([SIM.set_win_prob(x, 15) for x in grid])
    R = SIM.RALLIES_PER_SET if hasattr(SIM, "RALLIES_PER_SET") else None

    def sim_future(mean, sd, fut, past_w, seed):
        rng = np.random.default_rng(seed)
        hi = np.array([idx[m["home"]] for m in fut])
        ai = np.array([idx[m["away"]] for m in fut])
        out = np.zeros((ITERS, len(teams)))
        for it in range(ITERS):
            s = mean + rng.normal(0.0, 1.0, len(teams)) * sd
            margin = s[hi] + HA - s[ai]
            p = np.clip(np.array([SIM.rally_p(x) for x in margin]) if R is None
                        else 0.5 + margin / (2.0 * R), 0.10, 0.90)
            ps, p5 = np.interp(p, grid, t25), np.interp(p, grid, t15)
            # best of five: P(win) from set probability (sets 1-4) and set 5
            q = 1 - ps
            pw = ps ** 3 + 3 * ps ** 3 * q + 6 * ps ** 2 * q ** 2 * p5
            hw = rng.random(len(fut)) < pw
            wins = past_w.copy()
            np.add.at(wins, hi[hw], 1)
            np.add.at(wins, ai[~hw], 1)
            out[it] = wins
        return out

    per_team = {"PRIOR": [], "BLEND": []}
    for ci, frac in enumerate(CPS):
        cut = int(len(matches) * frac)
        past = [m for m in matches[:cut] if m["home"] in idx and m["away"] in idx]
        fut = [m for m in matches[cut:] if m["home"] in idx and m["away"] in idx]
        past_w = np.zeros(len(teams))
        n_played = np.zeros(len(teams))
        adj_m, adj_h = {}, {}
        for m in past:
            w = m["home"] if m["home_sets"] > m["away_sets"] else m["away"]
            past_w[idx[w]] += 1
            n_played[idx[m["home"]]] += 1
            n_played[idx[m["away"]]] += 1
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
        blend = np.zeros(len(teams))
        for t, i in idx.items():
            vm, vh = adj_m.get(t) or [], adj_h.get(t) or []
            zp = prior_z[t]
            if not vm:
                blend[i] = zp
                continue
            mm = sum(vm) / len(vm)
            val = (0.75 * mm + 0.25 * sum(vh) / len(vh)) if vh else mm
            w = len(vm) / (len(vm) + KB)
            blend[i] = (1 - w) * zp + w * val
        mean_p = np.array([PRIOR_SLOPE * prior_pts[t] + PRIOR_INTERCEPT for t in teams])
        sd_p = np.full(len(teams), PRIOR_SD)
        mean_b = blend * scale
        sd_b = 1.0 / np.sqrt(1.0 / PRIOR_SD ** 2 + n_played / sigma2)
        for name, mean, sd in (("PRIOR", mean_p, sd_p), ("BLEND", mean_b, sd_b)):
            sims = sim_future(mean, sd, fut, past_w, 1000 + ci)
            lo, med, hi_ = (np.percentile(sims, q, axis=0) for q in (10, 50, 90))
            for i in range(len(teams)):
                per_team[name].append((ci, abs(med[i] - final_w[i]),
                                       1.0 if lo[i] <= final_w[i] <= hi_[i] else 0.0))
            cov = np.mean([x[2] for x in per_team[name] if x[0] == ci])
            mae = np.mean([x[1] for x in per_team[name] if x[0] == ci])
            print("  %3.0f%%  %-5s  80%% band covers %.1f%%   median abs error %.2f wins"
                  % (frac * 100, name, 100 * cov, mae))

    a = np.array([x[1] for x in per_team["PRIOR"]])
    b = np.array([x[1] for x in per_team["BLEND"]])
    rng = random.Random(20260924)
    deltas = []
    for _ in range(2000):
        ix = [rng.randrange(len(a)) for _ in range(len(a))]
        deltas.append(float(np.mean(a[ix] - b[ix])))
    deltas.sort()
    lo, hi_ = deltas[50], deltas[1949]
    verdict = "SHIPS" if lo > 0 else ("HURTS" if hi_ < 0 else "inconclusive")
    res = {"checkpoints": CPS, "k": KB, "scale": scale, "sigma2": sigma2, "prior_sd": PRIOR_SD,
           "mae": {k: float(np.mean([x[1] for x in v])) for k, v in per_team.items()},
           "coverage80": {k: float(np.mean([x[2] for x in v])) for k, v in per_team.items()},
           "mae_improvement": {"delta": float(np.mean(a - b)), "ci": [lo, hi_], "verdict": verdict}}
    json.dump(res, open(OUT, "w"), indent=1)
    print("pooled: PRIOR mae %.3f cov %.1f%% | BLEND mae %.3f cov %.1f%%"
          % (res["mae"]["PRIOR"], 100 * res["coverage80"]["PRIOR"], res["mae"]["BLEND"],
             100 * res["coverage80"]["BLEND"]))
    print("median-error improvement %+.3f wins [%+.3f, %+.3f]  %s" % (np.mean(a - b), lo, hi_, verdict))
    print("wrote %s" % OUT)


if __name__ == "__main__":
    sys.exit(main())
