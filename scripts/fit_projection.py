#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fit the projection's weights against what actually happened, using 2024 -> 2025.

WHY THIS EXISTS. project_2026.py carries hand-set weights, and the ordering they
produce is not believable: mid-majors in the top ten, and teams the whole sport
rates highly buried. The suspect is the strength multiplier -- a per-set rate
rewards a player who takes a big share of her own team's swings, and a 0.5x-1.5x
spread may not be enough to price in who she was swinging against. This file
stops guessing and measures it.

*** WE FIT TO OUTCOMES, NOT TO POLLS. ***
The target is the 2025 season as it actually played out. AVCA / VolleyTalk /
Massey are never inputs here -- they are the smell test afterwards. Fitting a
model to reproduce a poll would fit it to opinion, and would quietly break the
project's own rule that other rankings stay reference-only. If the fitted model
lands near the polls that is corroboration; if it does not, there is a measured
reason to look at.

EVERYTHING HERE COMES OUT OF BOX SCORES, no rosters and no transfer-portal feed:
  - a player appearing for the same team in 2024 and 2025  -> RETURNED
  - appearing for a different team                          -> TRANSFERRED
  - appearing in 2025 with no 2024 D-I record               -> NEW
That last one is how the freshman term stops being zero: we can measure what
share of a team's production actually comes from players who had no D-I record
the year before.

TWO EXPERIMENTS, and they differ in how much you should trust them:

  1. THE TRANSFER EXPERIMENT -- leakage-free. A player who moved between two
     programmes of known strength is a natural experiment in what a points-per-set
     rate is worth at a different level. Nothing about 2025 outcomes enters the
     feature side. This is the number that fixes the multiplier.

  2. THE AGGREGATE BACKTEST -- honest but slightly optimistic, and the reason is
     stated rather than buried. Projecting 2025 needs to know who was ON the 2025
     roster; we hold published rosters for 2026 but not for 2025, so participation
     in 2025 stands in for the roster. That means the backtest knows exactly who
     played, where a real projection knows only who was listed. Injuries and
     redshirts leak in. Treat its accuracy as an upper bound.

Python 3.9 target. Writes data/fit_2024_2025.json.
"""

import json
import os
import sys
import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = os.path.join(REPO, "data", "fit_2024_2025.json")
MIN_SETS = 20          # a rate below this many sets is noise
SEED = 20260818        # fixed so a rerun reproduces; never time-based


def load(p):
    path = os.path.join(REPO, p)
    return json.load(open(path)) if os.path.exists(path) else None


def player_points(p) -> float:
    return ((p.get("kills") or 0) + (p.get("aces") or 0)
            + (p.get("block_solos") or 0) + 0.5 * (p.get("block_assists") or 0))


def pkey(p) -> str:
    import re
    return re.sub(r"[^a-z]", "",
                  ("%s %s" % (p.get("first") or "", p.get("last") or "")).lower())


# ------------------------------------------------------------------ strength
def team_strength_from_games(path: str, di_ids: set) -> Dict[str, float]:
    """OPPONENT-ADJUSTED net points per set for each team, from the linescores.

    Deliberately NOT raw margin. Raw net points/set carries exactly the bias this
    whole exercise is trying to remove: it put American and Hofstra among the top
    five in 2025, because beating weak schedules badly looks the same as beating
    strong ones. Feeding that into the strength multiplier would bake the
    mid-major inflation into the correction meant to fix it.

    So this reuses the SAME ridge off/def solve the validated composite uses
    (bakeoff_2025.fit_off_def): points/set in each match regressed on who
    produced it and who allowed it, with ridge shrinkage in pseudo-games so a
    thin sample cannot swing the field.

    Deliberately NOT RPI either: the official RPI table cannot be season-pinned,
    so no 2024 table exists or can ever be fetched.
    """
    from bakeoff_2025 import fit_off_def  # noqa: E402
    obs = []
    keys = set()
    if not os.path.exists(path):
        return {}
    for line in open(path):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if g.get("game_state") != "F":
            continue
        ls = g.get("linescores") or []
        teams = g.get("teams") or []
        if len(teams) != 2 or not ls:
            continue
        home = next((t for t in teams if t.get("is_home")), None)
        away = next((t for t in teams if not t.get("is_home")), None)
        if not home or not away:
            continue
        hid, aid = str(home.get("team_id")), str(away.get("team_id"))
        if hid not in di_ids or aid not in di_ids:
            continue
        hp = ap = 0
        n = 0
        for st in ls:
            try:
                h, a = int(st.get("home")), int(st.get("visit"))
            except (TypeError, ValueError):
                continue
            hp += h
            ap += a
            n += 1
        if not n:
            continue
        keys.add(hid)
        keys.add(aid)
        obs.append((hid, aid, hp / float(n), 1))
        obs.append((aid, hid, ap / float(n), -1))
    if not obs:
        return {}
    ks = sorted(keys)
    fit = fit_off_def(obs, ks)
    # off + def is the net: what a team produces plus what it suppresses.
    return {k: fit[k]["off"] + fit[k]["def"] for k in ks}


def zmap(d: Dict[str, float]) -> Dict[str, float]:
    if not d:
        return {}
    vals = list(d.values())
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
    return {k: (v - mu) / sd for k, v in d.items()}


# ------------------------------------------------------- experiment 1: moves
def transfer_experiment(p24, p25, s24z, s25z) -> Dict:
    """How much does a player's points/set change when the level changes?

    For everyone with a usable line in both seasons, regress the change in rate
    on the change in team strength. STAYERS are the control: their strength gap
    is ~0, so whatever drift shows up in them is development and noise, not
    level. The slope on the movers, net of that, is the translation factor the
    projection's multiplier is trying to express.
    """
    movers, stayers = [], []
    for k, a in p24.items():
        b = p25.get(k)
        if not b:
            continue
        if a["sets"] < MIN_SETS or b["sets"] < MIN_SETS:
            continue
        za, zb = s24z.get(a["team"]), s25z.get(b["team"])
        if za is None or zb is None:
            continue
        row = {"d_rate": b["rate"] - a["rate"], "d_str": zb - za,
               "rate24": a["rate"], "from": a["team"], "to": b["team"]}
        (movers if a["team"] != b["team"] else stayers).append(row)

    def fit(rows):
        if len(rows) < 30:
            return None
        x = np.array([r["d_str"] for r in rows])
        y = np.array([r["d_rate"] for r in rows])
        A = np.vstack([x, np.ones(len(x))]).T
        slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
        # bootstrap CI -- seeded, so this is reproducible
        rnd = random.Random(SEED)
        slopes = []
        for _ in range(2000):
            idx = [rnd.randrange(len(rows)) for _ in range(len(rows))]
            xb, yb = x[idx], y[idx]
            Ab = np.vstack([xb, np.ones(len(xb))]).T
            slopes.append(np.linalg.lstsq(Ab, yb, rcond=None)[0][0])
        slopes.sort()
        return {"n": len(rows), "slope": float(slope), "intercept": float(intercept),
                "ci95": [float(slopes[int(.025 * len(slopes))]),
                         float(slopes[int(.975 * len(slopes))])],
                "mean_d_rate": float(y.mean())}

    return {"movers": fit(movers), "stayers": fit(stayers),
            "n_movers": len(movers), "n_stayers": len(stayers)}


# --------------------------------------------------- experiment 2: aggregate
def build_features(p_prev, p_next, s_prev_z, teams_next):
    """For each team, the pool of players it carried into the next season.

    Membership comes from who actually appeared for the team in the NEXT season
    (see the module docstring -- this is the optimistic part). Each carried
    player brings the rate they posted in the PREVIOUS season and the strength of
    the team they posted it at.
    """
    pool = {}
    newshare = {}
    for k, b in p_next.items():
        t = b["team"]
        if t not in teams_next:
            continue
        a = p_prev.get(k)
        rec = pool.setdefault(t, [])
        tot = newshare.setdefault(t, [0.0, 0.0])
        tot[1] += b["pts"]
        if a and a["sets"] >= MIN_SETS and s_prev_z.get(a["team"]) is not None:
            rec.append({"rate": a["rate"], "z": s_prev_z[a["team"]],
                        "moved": a["team"] != t})
        else:
            tot[0] += b["pts"]          # production from a player with no prior line
    return pool, {t: (v[0] / v[1] if v[1] else None) for t, v in newshare.items()}


def score_team(cands, rotation, alpha, new_term):
    """alpha prices the level: a rate is multiplied by exp(alpha * z_strength)."""
    if not cands:
        return None
    adj = sorted((c["rate"] * math.exp(alpha * c["z"]) for c in cands), reverse=True)
    return sum(adj[:rotation]) + new_term


def evaluate(pool, target, rotation, alpha, new_term, folds=5):
    """Out-of-sample Spearman between the projection and the actual outcome."""
    from scipy.stats import spearmanr
    teams = sorted(set(pool) & set(target))
    if len(teams) < 40:
        return None
    rnd = random.Random(SEED)
    order = teams[:]
    rnd.shuffle(order)
    rhos = []
    for f in range(folds):
        test = [t for i, t in enumerate(order) if i % folds == f]
        xs, ys = [], []
        for t in test:
            s = score_team(pool[t], rotation, alpha, new_term)
            if s is None:
                continue
            xs.append(s)
            ys.append(target[t])
        if len(xs) >= 15:
            rhos.append(spearmanr(xs, ys).correlation)
    return float(np.mean(rhos)) if rhos else None


def main():
    p24raw = load("data/raw/2024/players_2024.json")
    p25raw = load("data/raw/2025/players_2025.json")
    rating25 = load("data/rating_2025.json")
    ds25 = load("data/data_2025.json")
    if not p24raw:
        print("data/raw/2024/players_2024.json not present yet -- the 2024 crawl "
              "is still running. Re-run when it finishes.")
        return 1
    if not (p25raw and rating25 and ds25):
        print("missing 2025 inputs")
        return 1

    # D-I membership: the official 2025 RPI table is the only self-consistent
    # flag we hold, and it is used for BOTH seasons. For 2024 that is an
    # approximation -- a handful of programmes changed division -- and it is
    # recorded as one rather than presented as membership.
    di_ids = set()
    id2name = {}
    for t in ds25["teams"]:
        if t.get("is_division_i") and t.get("team_id"):
            di_ids.add(str(t["team_id"]))
            id2name[str(t["team_id"])] = t["name_short"]

    s24 = team_strength_from_games(os.path.join(REPO, "data/raw/2024/games.jsonl"), di_ids)
    s25 = team_strength_from_games(os.path.join(REPO, "data/raw/2025/games.jsonl"), di_ids)
    s24z, s25z = zmap(s24), zmap(s25)
    print("team strength derived: 2024 %d teams | 2025 %d teams" % (len(s24), len(s25)))

    def index(raw):
        out = {}
        for p in raw["players"]:
            tid = str(p.get("team_id") or "")
            k = pkey(p)
            if not tid or not k or not (p.get("sets") or 0):
                continue
            out[(tid, k)] = None  # placeholder to detect dupes
        res = {}
        for p in raw["players"]:
            tid = str(p.get("team_id") or "")
            k = pkey(p)
            if not tid or not k or not (p.get("sets") or 0):
                continue
            pts = player_points(p)
            res[k + "@" + tid] = {"team": tid, "sets": p["sets"], "pts": pts,
                                  "rate": pts / float(p["sets"])}
        return res

    # Key players by NAME ONLY across seasons so a move is detectable, but keep
    # the team on the record. A name colliding across two programmes is the R8
    # hazard; require the surname to be non-trivial and drop ambiguous keys.
    def by_name(raw):
        seen = {}
        for p in raw["players"]:
            tid = str(p.get("team_id") or "")
            k = pkey(p)
            if not tid or len(k) < 6 or not (p.get("sets") or 0):
                continue
            pts = player_points(p)
            rec = {"team": tid, "sets": p["sets"], "pts": pts,
                   "rate": pts / float(p["sets"])}
            if k in seen:
                seen[k] = "AMBIG"
            else:
                seen[k] = rec
        return {k: v for k, v in seen.items() if v != "AMBIG"}

    p24, p25 = by_name(p24raw), by_name(p25raw)
    print("players keyed uniquely by name: 2024 %d | 2025 %d" % (len(p24), len(p25)))

    # ---- experiment 1 ----------------------------------------------------
    tx = transfer_experiment(p24, p25, s24z, s25z)
    print("\nTRANSFER EXPERIMENT (leakage-free)")
    for lab in ("movers", "stayers"):
        f = tx[lab]
        if f:
            print("  %-8s n=%4d  slope %+.4f pts/set per SD of team strength  "
                  "95%% CI [%+.4f, %+.4f]  mean drate %+.3f"
                  % (lab, f["n"], f["slope"], f["ci95"][0], f["ci95"][1], f["mean_d_rate"]))
        else:
            print("  %-8s too few to fit (n=%d)" % (lab, tx["n_%s" % lab]))

    # ---- experiment 2 ----------------------------------------------------
    target = {}
    name2id = {v: k for k, v in id2name.items()}
    for t in rating25["teams"]:
        tid = name2id.get(t["team"])
        if tid and t.get("composite") is not None:
            target[tid] = t["composite"]

    pool, newshare = build_features(p24, p25, s24z, set(target))
    ns = [v for v in newshare.values() if v is not None]
    ns_med = float(np.median(ns)) if ns else None
    print("\nNEW-PLAYER SHARE (players with no prior D-I line)")
    print("  measured on %d teams: median %.1f%% of a team's production" %
          (len(ns), 100 * ns_med if ns_med is not None else float("nan")))

    print("\nGRID SEARCH -- out-of-sample Spearman vs the actual 2025 composite")
    best = None
    results = []
    for rotation in (5, 6, 7, 8):
        # THE FIRST GRID STOPPED AT 1.0 AND 1.0 WON AT EVERY ROTATION -- which
        # means the optimum was at or past the edge and the search was simply
        # too narrow. Extended until the curve turns over.
        for alpha in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
                      2.0, 2.5, 3.0, 4.0):
            rho = evaluate(pool, target, rotation, alpha, 0.0)
            if rho is None:
                continue
            results.append({"rotation": rotation, "alpha": round(alpha, 2),
                            "rho": round(rho, 4)})
            if best is None or rho > best["rho"]:
                best = {"rotation": rotation, "alpha": alpha, "rho": rho}
    for r in sorted(results, key=lambda x: -x["rho"])[:12]:
        mark = "  <-- best" if best and r["rotation"] == best["rotation"] and \
            abs(r["alpha"] - best["alpha"]) < 1e-9 else ""
        print("  rotation=%d alpha=%.2f  rho=%.4f%s" % (r["rotation"], r["alpha"], r["rho"], mark))

    out = {
        "meta": {
            "source_tier": "DERIVED",
            "target": "2025 fitted composite (outcome), NOT any poll",
            "min_sets": MIN_SETS,
            "seed": SEED,
            "caveat_aggregate": ("roster membership for 2025 is stood in for by who "
                                 "actually played in 2025, because no 2025 published "
                                 "roster is held; the aggregate accuracy is therefore "
                                 "an upper bound"),
            "caveat_membership": ("D-I membership uses the official 2025 RPI table for "
                                  "both seasons; for 2024 that is an approximation"),
        },
        "transfer_experiment": tx,
        "new_player_share_median": ns_med,
        "grid": results,
        "best": best,
    }
    json.dump(out, open(OUT, "w"), indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
