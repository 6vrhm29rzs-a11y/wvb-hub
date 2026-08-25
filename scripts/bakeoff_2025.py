#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The metric bake-off: does anything add signal on top of RPI?

PRE-REGISTERED EXPECTATION (Claude-app, recorded before any of this ran):
hitting-efficiency differential and net points/set lead among box-score
computable metrics. Recorded here so the outcome is falsifiable either way.

DESIGN, v2. The first version had three flaws, all found in review, all fixed:

  1. OPPONENT ADJUSTMENT. v1 tested BARE net points/set against RPI, which is
     ~75% strength-of-schedule by construction. A team running up margins on a
     soft schedule looks elite, so "the schedule-adjusted metric beat the
     unadjusted one" was close to circular. Every box-score candidate is now
     ALSO reported opponent-adjusted, via a ridge least-squares model over the
     complete game graph. Raw and adjusted are both reported; the gap between
     them is itself informative.

  2. THE QUESTION. "Which single metric wins" is less decision-relevant than
     "does anything add signal ON TOP OF RPI", since RPI is free, official and
     already computed. The headline is now INCREMENTAL AUC over RPI alone, from
     a two-variable model. A candidate worth +0.02 AUC on top of RPI beats one
     that merely loses to RPI by 0.05 standalone.

  3. LEAKAGE ASYMMETRY. v1's high-power test predicted regular-season matches
     from full-season metrics, putting the predicted outcome inside the
     predictor -- which hits RPI hardest, because Factor I is literally winning
     percentage. So RPI's v1 lead was partly artifact. Replaced with
     CHRONOLOGICAL splits: fit only on matches through a cutoff, test on
     everything after. Multiple cutoffs, so ranking stability is visible; if the
     order flips between cutoffs, the metrics are not separable and that is the
     honest finding.

  4. Every AUC carries a bootstrap confidence interval. Overlapping intervals
     are reported as indistinguishable rather than ranked.

*** SIDEOUT IS A PROXY, NOT SIDEOUT%. *** True sideout% = points won while
receiving / opponent serve attempts, and is NOT recoverable from box scores.
Checked rather than assumed: the rally identities P_us = S_us - Y + X and
P_opp = S_opp - X + Y give contradictory X on a real match (X-Y=1 vs Y-X=6),
because serveAttempts and receptionAttempts treat aces and service errors
differently. Implemented here is the SERVE-RECEIVE component only. The
attack-after-reception half -- Palao (2018)'s single most discriminating action
-- needs play-by-play we do not have. Tier: UNVERIFIED.

Python 3.9 target.
"""

import datetime
import json
import math
import os
import random
import sys
import collections
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(REPO, "data", "bakeoff_%d.json" % SEASON)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm  # noqa: E402
from rpi_2025 import rpi_from_games  # noqa: E402

RIDGE = 3.0        # shrinkage in "pseudo-games"; ~30-game teams barely move
CD_ITERS = 300     # coordinate-descent sweeps
BOOTSTRAP = 600
SEED = 11


def to_i(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------------ load

def load():
    from gamelog import load_games_jsonl as _lg
    from membership import resolve as _resolve
    di, _official, _src = _resolve(RAW, _lg(os.path.join(RAW, "games.jsonl")))

    box = {}
    bpath = os.path.join(RAW, "boxscores.jsonl")
    if os.path.exists(bpath):
        with open(bpath) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    b = json.loads(line)
                except Exception:
                    continue
                box[b["game_id"]] = b

    from gamelog import load_games_jsonl
    matches = []
    for g in load_games_jsonl(os.path.join(RAW, "games.jsonl")):
            if g.get("game_state") != "F":
                continue
            t = g.get("teams") or []
            if len(t) != 2:
                continue
            ka, kb = norm(t[0].get("name_short")), norm(t[1].get("name_short"))
            if ka not in di or kb not in di:
                continue
            if t[0].get("is_winner"):
                win = 0
            elif t[1].get("is_winner"):
                win = 1
            else:
                continue

            ep = g.get("start_time_epoch")
            date = datetime.datetime.utcfromtimestamp(int(ep)).date() if ep else None

            hp = ap = nsets = 0
            for ls in g.get("linescores") or []:
                hp += to_i(ls.get("home"))
                ap += to_i(ls.get("visit"))
                nsets += 1

            bx = box.get(g["game_id"])
            blines = {}
            if bx:
                for tb in bx.get("teams", []):
                    blines[str(tb.get("team_id"))] = tb.get("team_stats") or {}

            side = []
            for tt in t:
                pf, pa = (hp, ap) if tt.get("is_home") else (ap, hp)
                side.append({
                    "key": norm(tt.get("name_short")),
                    "name_short": tt.get("name_short"),
                    "points_for": pf, "points_against": pa, "sets": nsets,
                    "is_home": bool(tt.get("is_home")),
                    "box": blines.get(str(tt.get("team_id"))),
                })

            matches.append({
                "game_id": g["game_id"], "date": date,
                "is_championship": bool(g.get("championship")),
                "teams": side, "winner_idx": win,
            })
    return matches, di


# ------------------------------------------------------- opponent adjustment

_SITE_CACHE = {}


def _site_factor(game_id):
    """1 for a normal match, 0 when the floor was neutral."""
    if not _SITE_CACHE:
        path = os.path.join(REPO, "data", "venues_%d.json" % SEASON)
        _SITE_CACHE["_"] = {}
        if os.path.exists(path):
            try:
                v = json.load(open(path))
                _SITE_CACHE["_"] = {r["game_id"]: r["site"] for r in v.get("games", [])}
            except ValueError:
                pass
    return 0 if _SITE_CACHE["_"].get(str(game_id)) == "neutral" else 1


def fit_off_def(obs, keys, w=None):
    # type: (List[Tuple[str,str,float,int]], List[str], Optional[List[float]]) -> Dict[str, Dict[str,float]]
    """Ridge least squares  y(i vs j) ~ mu + off_i - def_j + h*home_sign.

    `off_i` is how much of the quantity team i produces after accounting for who
    it faced; `def_i` is how much it suppresses in opponents. Solved by
    coordinate descent with explicit residual maintenance -- 697 parameters, so
    a direct normal-equations solve would be needlessly cubic in pure Python.

    Ridge is expressed in pseudo-games (RIDGE), so a team with ~30 games barely
    shrinks while a team with 3 is pulled hard toward the mean. That matters:
    without it, a 2-game sample produces a wild rating that then contaminates
    every opponent's adjustment.

    `w` gives each observation a weight -- used by rating_factors.py to ask
    whether weighting matches differently (by recency, by margin shape, by
    anything) predicts future results better. It is OPTIONAL and defaults to
    equal weights, so every existing caller is untouched: with w=None the
    arithmetic below reduces to exactly what it was, which is asserted rather
    than assumed (test_rating_factors.py compares the two paths on real data
    and requires bit-identical output).

    In the weighted form the ridge denominator becomes the SUM OF WEIGHTS
    rather than the count, which is the point: a team whose matches are
    down-weighted for being old should shrink toward the mean like a team with
    fewer matches, because that is what it now has -- less evidence.
    """
    n = len(obs)
    if not n:
        return {k: {"off": 0.0, "def": 0.0} for k in keys}

    idx = {k: c for c, k in enumerate(keys)}
    T = len(keys)
    I = [idx[o[0]] for o in obs]
    J = [idx[o[1]] for o in obs]
    Y = [o[2] for o in obs]
    H = [o[3] for o in obs]
    W = [1.0] * n if w is None else [float(x) for x in w]
    if len(W) != n:
        raise ValueError("weights: %d for %d observations" % (len(W), n))
    WSUM = sum(W) or 1.0

    rows_i = collections.defaultdict(list)
    rows_j = collections.defaultdict(list)
    for r in range(n):
        rows_i[I[r]].append(r)
        rows_j[J[r]].append(r)

    mu = sum(W[r] * Y[r] for r in range(n)) / WSUM
    h = 0.0
    off = [0.0] * T
    dff = [0.0] * T
    resid = [Y[r] - mu for r in range(n)]

    for _ in range(CD_ITERS):
        d = sum(W[r] * resid[r] for r in range(n)) / WSUM
        mu += d
        for r in range(n):
            resid[r] -= d

        num = sum(W[r] * resid[r] * H[r] for r in range(n))
        den = sum(W[r] * H[r] * H[r] for r in range(n)) or 1.0
        d = num / den
        h += d
        for r in range(n):
            resid[r] -= d * H[r]

        for a in range(T):
            rr = rows_i[a]
            if not rr:
                continue
            d = (sum(W[r] * resid[r] for r in rr)
                 / (sum(W[r] for r in rr) + RIDGE))
            off[a] += d
            for r in rr:
                resid[r] -= d

        for b in range(T):
            rr = rows_j[b]
            if not rr:
                continue
            # pred contains -def_j, so d(resid)/d(def_j) = +1
            d = -(sum(W[r] * resid[r] for r in rr)
                  / (sum(W[r] for r in rr) + RIDGE))
            dff[b] += d
            for r in rr:
                resid[r] += d

    return {k: {"off": off[idx[k]], "def": dff[idx[k]], "_h": h, "_mu": mu}
            for k in keys}


# --------------------------------------------------------------- metric build

def build_metrics(fit_matches, di):
    """metric name -> team key -> value. Raw and opponent-adjusted."""
    keys = sorted(di)
    agg = collections.defaultdict(lambda: {
        "k": 0, "e": 0, "ta": 0, "ok": 0, "oe": 0, "ota": 0,
        "pf": 0, "pa": 0, "sets": 0, "rerr": 0, "ratt": 0, "w": 0, "l": 0})

    games_rpi = []
    obs_pts, obs_hit, obs_rec = [], [], []

    for m in fit_matches:
        a, b = m["teams"]
        wk = m["teams"][m["winner_idx"]]["key"]
        lk = m["teams"][1 - m["winner_idx"]]["key"]
        games_rpi.append((wk, lk, m["game_id"]))
        agg[wk]["w"] += 1
        agg[lk]["l"] += 1

        for me, opp in ((a, b), (b, a)):
            e = agg[me["key"]]
            e["pf"] += me["points_for"]
            e["pa"] += me["points_against"]
            e["sets"] += me["sets"]
            # NEUTRAL FLOORS GET NO HOME TERM. `sign` feeds the home-advantage
            # coefficient in fit_off_def; on a neutral court there is no home
            # advantage to attribute, and crediting one is a silent systematic
            # error. scripts/venues.py decides this from the venue itself and
            # abstains when it cannot tell -- an unclassified match keeps the
            # ordinary sign, which is right the overwhelming majority of the
            # time. The 2026 season opened on a neutral floor (both AVCA First
            # Serve matches at Fiserv Forum), so this is not a rare case.
            sign = (1 if me["is_home"] else -1) * _site_factor(m["game_id"])
            if me["sets"]:
                obs_pts.append((me["key"], opp["key"],
                                me["points_for"] / float(me["sets"]), sign))
            if me["box"] and opp["box"]:
                mk, mev = to_i(me["box"].get("kills")), to_i(me["box"].get("attackErrors"))
                mta = to_i(me["box"].get("attackAttempts"))
                e["k"] += mk
                e["e"] += mev
                e["ta"] += mta
                e["ok"] += to_i(opp["box"].get("kills"))
                e["oe"] += to_i(opp["box"].get("attackErrors"))
                e["ota"] += to_i(opp["box"].get("attackAttempts"))
                e["rerr"] += to_i(me["box"].get("receptionErrors"))
                e["ratt"] += to_i(me["box"].get("receptionAttempts"))
                if mta:
                    obs_hit.append((me["key"], opp["key"], (mk - mev) / float(mta), sign))
                ra = to_i(me["box"].get("receptionAttempts"))
                if ra:
                    obs_rec.append((me["key"], opp["key"],
                                    1.0 - to_i(me["box"].get("receptionErrors")) / float(ra),
                                    sign))

    rpi = rpi_from_games(games_rpi, keys)
    adj_pts = fit_off_def(obs_pts, keys)
    adj_hit = fit_off_def(obs_hit, keys)
    adj_rec = fit_off_def(obs_rec, keys)

    M = collections.defaultdict(dict)
    for k in keys:
        e = agg[k]
        own = ((e["k"] - e["e"]) / float(e["ta"])) if e["ta"] else None
        opp = ((e["ok"] - e["oe"]) / float(e["ota"])) if e["ota"] else None

        M["rpi"][k] = rpi[k]["rpi"]
        nw = e["w"] + e["l"]
        M["win_pct"][k] = (e["w"] / float(nw)) if nw else None

        M["own_hit_eff"][k] = own
        M["opp_hit_eff"][k] = (-opp) if opp is not None else None
        M["hit_eff_diff"][k] = (own - opp) if (own is not None and opp is not None) else None
        M["net_points_set"][k] = ((e["pf"] - e["pa"]) / float(e["sets"])) if e["sets"] else None
        M["sideout_proxy"][k] = (1.0 - e["rerr"] / float(e["ratt"])) if e["ratt"] else None

        # opponent-adjusted counterparts
        M["adj_net_points_set"][k] = adj_pts[k]["off"] + adj_pts[k]["def"]
        M["adj_hit_eff_diff"][k] = adj_hit[k]["off"] + adj_hit[k]["def"]
        M["adj_own_hit_eff"][k] = adj_hit[k]["off"]
        M["adj_opp_hit_eff"][k] = adj_hit[k]["def"]
        M["adj_sideout_proxy"][k] = adj_rec[k]["off"]

    M["_home_adv_points_per_set"] = adj_pts[keys[0]]["_h"] if keys else 0.0
    return M


# ------------------------------------------------------------------- scoring

def _groups(scores):
    uniq = sorted(set(scores))
    gi = {v: i for i, v in enumerate(uniq)}
    return [gi[s] for s in scores], len(uniq)


def auc_from_counts(g, y, ng, idxs):
    """Mann-Whitney AUC over a (possibly bootstrap-resampled) index list."""
    cp = [0] * ng
    cn = [0] * ng
    np_ = nn = 0
    for i in idxs:
        if y[i] == 1:
            cp[g[i]] += 1
            np_ += 1
        else:
            cn[g[i]] += 1
            nn += 1
    if not np_ or not nn:
        return None
    below = 0
    u = 0.0
    for k in range(ng):
        u += cp[k] * (below + cn[k] / 2.0)
        below += cn[k]
    return u / float(np_ * nn)


def score_metric(M, metric, test):
    """Returns (scores, labels) for one metric over the test matches."""
    tbl = M[metric]
    s, y = [], []
    for m in test:
        a, b = m["teams"]
        va, vb = tbl.get(a["key"]), tbl.get(b["key"])
        if va is None or vb is None:
            continue
        s.append(va - vb)
        y.append(1 if m["winner_idx"] == 0 else 0)
    return s, y


def boot_ci(s, y, rnd, b=BOOTSTRAP):
    if not s:
        return (None, None, None)
    g, ng = _groups(s)
    n = len(s)
    base = auc_from_counts(g, y, ng, range(n))
    vals = []
    for _ in range(b):
        idxs = [rnd.randrange(n) for _ in range(n)]
        v = auc_from_counts(g, y, ng, idxs)
        if v is not None:
            vals.append(v)
    vals.sort()
    if len(vals) < 20:
        return (base, None, None)
    return (base, vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1])


def logistic(X, y, iters=200, l2=1e-3):
    """Plain IRLS-free gradient fit; few features, so this is plenty."""
    p = len(X[0])
    w = [0.0] * p
    lr = 0.5
    for _ in range(iters):
        gr = [0.0] * p
        for xi, yi in zip(X, y):
            z = sum(w[k] * xi[k] for k in range(p))
            pr = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            d = pr - yi
            for k in range(p):
                gr[k] += d * xi[k]
        for k in range(p):
            gr[k] = gr[k] / len(X) + l2 * w[k]
            w[k] -= lr * gr[k]
    return w


def standardize(v):
    n = len(v)
    mu = sum(v) / n
    sd = (sum((x - mu) ** 2 for x in v) / n) ** 0.5 or 1.0
    return [(x - mu) / sd for x in v], mu, sd


def incremental(M, fit, test, cand):
    """Out-of-sample incremental AUC of (RPI + candidate) over RPI alone.

    Coefficients are trained on the FIT window and evaluated on TEST, so the
    reported gain is genuinely out of sample. Two features, so coefficient
    variance is negligible relative to the metric-estimation noise.
    """
    def feats(matches):
        rows, ys = [], []
        for m in matches:
            a, b = m["teams"]
            r = M["rpi"].get(a["key"]), M["rpi"].get(b["key"])
            c = M[cand].get(a["key"]), M[cand].get(b["key"])
            if None in r or None in c:
                continue
            rows.append((r[0] - r[1], c[0] - c[1]))
            ys.append(1 if m["winner_idx"] == 0 else 0)
        return rows, ys

    ftr, fy = feats(fit)
    ttr, ty = feats(test)
    if len(ftr) < 50 or len(ttr) < 20:
        return None

    r_f, c_f = [x[0] for x in ftr], [x[1] for x in ftr]
    r_s, rmu, rsd = standardize(r_f)
    c_s, cmu, csd = standardize(c_f)
    Xr = [[1.0, r_s[i]] for i in range(len(ftr))]
    Xb = [[1.0, r_s[i], c_s[i]] for i in range(len(ftr))]
    wr = logistic(Xr, fy)
    wb = logistic(Xb, fy)

    sr, sb, yy = [], [], []
    for (rv, cv), lab in zip(ttr, ty):
        rz = (rv - rmu) / rsd
        cz = (cv - cmu) / csd
        sr.append(wr[0] + wr[1] * rz)
        sb.append(wb[0] + wb[1] * rz + wb[2] * cz)
        yy.append(lab)

    gr, ngr = _groups(sr)
    gb, ngb = _groups(sb)
    n = len(yy)
    a_r = auc_from_counts(gr, yy, ngr, range(n))
    a_b = auc_from_counts(gb, yy, ngb, range(n))

    rnd = random.Random(SEED + 1)
    diffs = []
    for _ in range(BOOTSTRAP):
        idxs = [rnd.randrange(n) for _ in range(n)]
        x1 = auc_from_counts(gr, yy, ngr, idxs)
        x2 = auc_from_counts(gb, yy, ngb, idxs)
        if x1 is not None and x2 is not None:
            diffs.append(x2 - x1)
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))] if len(diffs) > 20 else None
    hi = diffs[int(0.975 * len(diffs)) - 1] if len(diffs) > 20 else None
    return {"n": n, "auc_rpi": a_r, "auc_both": a_b, "delta": a_b - a_r,
            "delta_lo": lo, "delta_hi": hi, "coef_candidate": wb[2]}


ORDER = ["rpi", "adj_net_points_set", "net_points_set", "adj_hit_eff_diff",
         "hit_eff_diff", "adj_own_hit_eff", "own_hit_eff", "adj_opp_hit_eff",
         "opp_hit_eff", "adj_sideout_proxy", "sideout_proxy", "win_pct"]
CANDIDATES = ["adj_net_points_set", "net_points_set", "adj_hit_eff_diff",
              "hit_eff_diff", "adj_opp_hit_eff", "adj_sideout_proxy"]


def run_split(name, fit, test, di):
    print("=" * 78)
    print(name)
    print("  fit n=%d   test n=%d" % (len(fit), len(test)))
    print("=" * 78)
    M = build_metrics(fit, di)
    rnd = random.Random(SEED)

    print("  STANDALONE (AUC with 95%% bootstrap CI)")
    rows = {}
    for metric in ORDER:
        s, y = score_metric(M, metric, test)
        if not s:
            print("    %-22s no data" % metric)
            continue
        base, lo, hi = boot_ci(s, y, rnd)
        acc = sum(1 for v, l in zip(s, y) if (v > 0) == (l == 1)) / float(len(s))
        rows[metric] = {"n": len(s), "acc": acc, "auc": base, "lo": lo, "hi": hi}
        print("    %-22s n=%-5d acc=%.4f  auc=%.4f  [%.4f, %.4f]" % (
            metric, len(s), acc, base,
            lo if lo is not None else float("nan"),
            hi if hi is not None else float("nan")))
    print()

    print("  INCREMENTAL over RPI (out-of-sample; positive delta = adds signal)")
    incs = {}
    for cand in CANDIDATES:
        r = incremental(M, fit, test, cand)
        if not r:
            print("    %-22s insufficient data" % cand)
            continue
        incs[cand] = r
        star = ""
        if r["delta_lo"] is not None and r["delta_lo"] > 0:
            star = "  *** CI excludes 0"
        print("    %-22s auc_rpi=%.4f -> %.4f   delta=%+.4f [%+.4f, %+.4f]%s" % (
            cand, r["auc_rpi"], r["auc_both"], r["delta"],
            r["delta_lo"] if r["delta_lo"] is not None else float("nan"),
            r["delta_hi"] if r["delta_hi"] is not None else float("nan"), star))
    print()
    hcs = M.get("_home_adv_points_per_set")
    if hcs:
        print("  (fitted home advantage: %+.3f points per set, half-effect)" % hcs)
        print()
    return {"standalone": rows, "incremental": incs,
            "n_fit": len(fit), "n_test": len(test),
            "home_adv_half_points_per_set": hcs}


def main():
    matches, di = load()
    with_box = sum(1 for m in matches if m["teams"][0]["box"] and m["teams"][1]["box"])
    print("D-I matches %d   with both box lines %d (%.1f%%)" % (
        len(matches), with_box, 100.0 * with_box / max(len(matches), 1)))
    print()

    champ = [m for m in matches if m["is_championship"]]
    reg = [m for m in matches if not m["is_championship"]]

    out = {}
    out["tournament"] = run_split(
        "TOURNAMENT  fit = regular season -> test = D-I championship matches",
        reg, champ, di)

    for label, cut in (("OCT 1", datetime.date(2025, 10, 1)),
                       ("OCT 15", datetime.date(2025, 10, 15)),
                       ("NOV 1", datetime.date(2025, 11, 1))):
        fit = [m for m in matches if m["date"] and m["date"] < cut]
        test = [m for m in matches if m["date"] and m["date"] >= cut]
        out["cutoff_%s" % label.replace(" ", "_").lower()] = run_split(
            "CHRONOLOGICAL  fit = before %s -> test = everything after" % label,
            fit, test, di)

    # ranking stability across cutoffs
    print("=" * 78)
    print("RANKING STABILITY ACROSS CUTOFFS (standalone AUC order)")
    print("=" * 78)
    for k in ("cutoff_oct_1", "cutoff_oct_15", "cutoff_nov_1"):
        st = out[k]["standalone"]
        rank = sorted(st.items(), key=lambda kv: -(kv[1]["auc"] or 0))
        print("  %-14s %s" % (k, " > ".join(m for m, _ in rank[:5])))
    print()

    payload = {
        "meta": {
            "season": 2025, "source_tier": "DERIVED",
            "pre_registered_expectation": "hitting-efficiency differential and "
                                          "net points/set lead among box-score "
                                          "computable metrics (Claude-app)",
            "design_notes": [
                "opponent adjustment via ridge least squares over the game graph",
                "headline is incremental AUC over RPI, not standalone ranking",
                "chronological splits only; no full-season metric predicts a "
                "match inside its own fit window",
                "all AUCs carry 95% bootstrap CIs; overlapping CIs mean "
                "indistinguishable, not ranked",
            ],
            "sideout_caveat": "serve-receive component only; true sideout% is "
                              "not recoverable from box scores",
            "ridge_pseudo_games": RIDGE, "bootstrap": BOOTSTRAP,
            "matches_di": len(matches), "matches_with_boxscores": with_box,
        },
        "splits": out,
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
