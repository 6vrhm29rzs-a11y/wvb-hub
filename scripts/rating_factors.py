#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does weighting matches differently predict the future better? Measured, not chosen.

    python3 scripts/rating_factors.py        -> data/rating_factors_2025.json

WHAT THIS IS FOR. Cody's question: how should a ranking weight early matches
against late ones, strong opponents against weak, a 3-0 against a 3-2, a
25-12 sweep against a 25-23 sweep, a match a team was outscored in but won,
home against road against neutral, a team's own earned points against points
its opponent simply gave away?

Every one of those is a real question and NONE of them can be settled by
picking a number. This project has been burned by hand-set weights before --
the roster term was tried at 0.15, 0.30, 0.50 and 1.00, all of which made the
ordering WORSE, and the fitted value turned out to be 0.09. So the honest
form of Cody's question is:

    if we weight matches this way instead of that way, does the resulting
    rating predict matches it has never seen more accurately?

That is what this measures. A factor that improves out-of-sample prediction
earns its weight. A factor that does not gets ZERO and the page says so --
which is a real answer, not a failure.

--- THE DESIGN ---

Split the season by DATE, never at random. A ranking exists to predict what
happens next, so the test has to be the future: fit on everything up to a
cutoff, score on everything after it. Random k-fold would let a team's November
result inform its own September rating, which flatters every scheme equally and
tells us nothing about the thing we care about. Three cutoffs, because one split
is one sample.

The rating itself is the existing ridge (bakeoff_2025.fit_off_def), which
already solves y(i vs j) ~ mu + off_i - def_j + h*home_sign. So OPPONENT
STRENGTH and HOME ADVANTAGE are not candidate factors -- they are already in
every scheme below, including the baseline, and the interesting question is
what to add on top of them.

Scored three ways, because they answer different questions:
  * AUC  -- can it pick the winner? (threshold-free, R1)
  * RMSE -- can it predict the margin?
  * a bootstrap CI on the AUC difference from baseline, so "better" means
    better than sampling noise rather than better in the third decimal.

--- WHAT IS NOT HERE, AND WHY ---

⚠ TRAVEL, TIME ZONES AND EARLY STARTS CANNOT BE MEASURED ON 2025 DATA. Cody
asked specifically about a Pacific team playing 8am Eastern and turning around
that afternoon. The turnaround IS measurable -- two matches on one date, and
days of rest, both come straight from the epochs. The rest of it does not:
`crawl_2025.py` discarded `location` from /game/{id}, so 2025 carries no venue,
no city and no state, and re-crawling a past season is banned. We started
storing venue in 2026 (`data/venues_2026.json`), so time zone and local start
time become measurable as this season accumulates -- not now. Saying that is
better than proxying it with something we can compute and calling it travel.

Python 3.9 target.
"""

import collections
import json
import math
import os
import random
import sys
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakeoff_2025 as B  # noqa: E402

SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(REPO, "data", "rating_factors_%d.json" % SEASON)

SEED = 23
BOOT = 400
CUTOFFS = (0.45, 0.60, 0.75)      # fraction of the season used to fit
DAY = 86400.0


# ------------------------------------------------------------------ loading

def load_matches():
    # type: () -> List[Dict]
    """One record per completed D-I match, with everything the schemes need."""
    doc = json.load(open(os.path.join(REPO, "data", "data_%d.json" % SEASON),
                         encoding="utf-8"))
    earned = load_earned()
    out = []
    for g in doc.get("games") or []:
        if g.get("state") != "F":
            continue
        ts = g.get("teams") or []
        ls = [l for l in (g.get("linescores") or []) if l.get("home") is not None]
        if len(ts) != 2 or not ls:
            continue
        home = next((t for t in ts if t.get("is_home")), None)
        away = next((t for t in ts if not t.get("is_home")), None)
        if not home or not away:
            continue
        if home.get("division") != 1 or away.get("division") != 1:
            continue
        ep = g.get("start_time_epoch")
        if not ep:
            continue
        hp = sum(int(l["home"]) for l in ls)
        ap = sum(int(l["visit"]) for l in ls)
        nsets = len(ls)
        setscores = [(int(l["home"]), int(l["visit"])) for l in ls]
        gid = str(g.get("game_id"))
        e = earned.get(gid) or {}
        out.append({
            "gid": gid,
            "epoch": int(ep),
            "home": str(home["team_id"]),
            "away": str(away["team_id"]),
            "home_sets": int(home.get("sets_won") or 0),
            "away_sets": int(away.get("sets_won") or 0),
            "home_pts": hp,
            "away_pts": ap,
            "sets": nsets,
            "setscores": setscores,
            # per-set point margin from the HOME side -- the quantity the
            # rating already uses, and the one that answers 25-12 vs 25-23 and
            # "outscored but won" without being told about either.
            "margin": (hp - ap) / float(nsets),
            "home_earned": e.get(str(home["team_id"])),
            "away_earned": e.get(str(away["team_id"])),
            "home_win": 1 if int(home.get("sets_won") or 0) >
                             int(away.get("sets_won") or 0) else 0,
        })
    out.sort(key=lambda m: m["epoch"])
    return out


def load_earned():
    # type: () -> Dict[str, Dict[str, float]]
    """game_id -> team_id -> points the team EARNED (kills + aces + blocks).

    The other way to score is for the opponent to miss: a serve into the net, an
    attack out, a ball-handling error. Those points are real and they count, but
    they are the opponent's doing. Cody's question -- "winning by the opponent
    missing every serve vs scoring 19 points per set" -- is exactly the gap
    between this number and the team's rally points, and it is computable
    because the box score carries the raw counts and the linescores carry the
    rally points.

    ⚠ NEVER the box score's own `points` column: measured 2026-08-11, it is
    absent from some games and undercounts by a different amount per player.
    """
    p = os.path.join(RAW, "boxscores.jsonl")
    out = {}
    if not os.path.exists(p):
        return out
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        gid = str(rec.get("game_id"))
        for t in rec.get("teams") or []:
            st = t.get("team_stats") or {}
            try:
                k = float(st.get("kills") or 0)
                a = float(st.get("serviceAces") or 0)
                bs = float(st.get("blockSolos") or 0)
                ba = float(st.get("blockAssists") or 0)
            except (TypeError, ValueError):
                continue
            out.setdefault(gid, {})[str(t.get("team_id"))] = k + a + bs + 0.5 * ba
    return out


# ---------------------------------------------------------------- schemes

def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def scheme_obs(matches, cutoff_epoch, scheme):
    # type: (List[Dict], int, Dict) -> Tuple[List[Tuple], List[float]]
    """(observations, weights) for one weighting scheme, from training matches."""
    obs, wts = [], []
    half = scheme.get("half_life_days")
    cap = scheme.get("margin_cap")
    root = scheme.get("margin_root")
    use_earned = scheme.get("target") == "earned"
    use_sets = scheme.get("target") == "sets"
    blend = scheme.get("earned_blend")
    for m in matches:
        y = m["margin"]
        if use_sets:
            # 3-0 is +3, 3-2 is +1. Deliberately coarse: this scheme exists to
            # ask whether the set score carries anything the point margin does
            # not, and it throws away 25-12 vs 25-23 completely to find out.
            y = float(m["home_sets"] - m["away_sets"])
        if use_earned or blend:
            if m["home_earned"] is None or m["away_earned"] is None:
                continue
            ey = (m["home_earned"] - m["away_earned"]) / float(m["sets"])
            y = ey if use_earned else (1 - blend) * y + blend * ey
        if cap:
            y = clamp(y, -cap, cap)
        if root:
            y = math.copysign(abs(y) ** root, y)
        w = 1.0
        if half:
            age_days = (cutoff_epoch - m["epoch"]) / DAY
            w = 0.5 ** (max(age_days, 0.0) / half)
        obs.append((m["home"], m["away"], y, 1))
        wts.append(w)
    return obs, wts


SCHEMES = [
    {"name": "baseline",
     "what": "equal weight, rally point margin per set (what ships today)"},
    {"name": "recency-14", "half_life_days": 14,
     "what": "a match halves in weight every 14 days"},
    {"name": "recency-30", "half_life_days": 30, "what": "half-life 30 days"},
    {"name": "recency-45", "half_life_days": 45, "what": "half-life 45 days"},
    {"name": "recency-60", "half_life_days": 60, "what": "half-life 60 days"},
    {"name": "recency-90", "half_life_days": 90, "what": "half-life 90 days"},
    {"name": "cap-3", "margin_cap": 3.0,
     "what": "margin clipped at +/-3 pts/set -- does running up the score help?"},
    {"name": "cap-5", "margin_cap": 5.0, "what": "margin clipped at +/-5 pts/set"},
    {"name": "cap-8", "margin_cap": 8.0, "what": "margin clipped at +/-8 pts/set"},
    {"name": "root-0.5", "margin_root": 0.5,
     "what": "diminishing returns: sign(m)*sqrt(|m|)"},
    {"name": "root-0.75", "margin_root": 0.75, "what": "milder diminishing returns"},
    {"name": "earned-only", "target": "earned",
     "what": "margin of EARNED points (kills+blocks+aces), ignoring gifts"},
    {"name": "earned-blend-25", "earned_blend": 0.25,
     "what": "75% rally margin + 25% earned margin"},
    {"name": "earned-blend-50", "earned_blend": 0.50, "what": "half and half"},
    {"name": "recency-45+cap-5", "half_life_days": 45, "margin_cap": 5.0,
     "what": "the two best single ideas together, if they are"},
    {"name": "sets-target", "target": "sets",
     "what": "rank on SET margin (3-0 vs 3-2) instead of point margin"},
]


# ---------------------------------------------------------------- scoring

def auc(pairs):
    # type: (List[Tuple[float,int]]) -> float
    """Threshold-free (R1). Mann-Whitney U over (score, label), ties averaged.

    ⚠ THE FIRST VERSION KEYED ITS TIE RANKS ON id(), AND THE BOOTSTRAP BREAKS
    THAT. Resampling draws with replacement, so the SAME tuple object appears in
    the list several times -- one id, one rank, and every duplicate silently
    collapsed onto the first one's value. The plain path was fine and the
    confidence intervals, which are the entire reason the bootstrap exists,
    were computed on a quietly wrong statistic. Rank by POSITION, which cannot
    collide.
    """
    n1 = sum(1 for _, y in pairs if y == 1)
    n0 = len(pairs) - n1
    if not n1 or not n0:
        return float("nan")
    order = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and pairs[order[j + 1]][0] == pairs[order[i]][0]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rsum = sum(ranks[i] for i in range(len(pairs)) if pairs[i][1] == 1)
    return (rsum - n1 * (n1 + 1) / 2.0) / float(n1 * n0)


def evaluate(matches, frac, scheme):
    # type: (List[Dict], float, Dict) -> Optional[Dict]
    cut = int(len(matches) * frac)
    train, test = matches[:cut], matches[cut:]
    if not train or not test:
        return None
    cutoff_epoch = train[-1]["epoch"]
    keys = sorted(set([m["home"] for m in matches] + [m["away"] for m in matches]))
    obs, wts = scheme_obs(train, cutoff_epoch, scheme)
    if not obs:
        return None
    fit = B.fit_off_def(obs, keys, wts)
    mu = fit[keys[0]]["_mu"]
    h = fit[keys[0]]["_h"]

    scored, errs = [], []
    for m in test:
        fh, fa = fit.get(m["home"]), fit.get(m["away"])
        if not fh or not fa:
            continue
        pred = mu + fh["off"] - fa["def"] + h
        pred_a = mu + fa["off"] - fh["def"] - h
        edge = pred - pred_a
        scored.append((edge, m["home_win"]))
        errs.append((edge / 2.0 - m["margin"]) ** 2)
    if len(scored) < 100:
        return None
    return {"auc": auc(scored), "rmse": (sum(errs) / len(errs)) ** 0.5,
            "n_test": len(scored), "n_train": len(obs),
            "home_adv_pts_per_set": h, "scored": scored}


def boot_delta(a_scores, b_scores, rng):
    # type: (List, List, random.Random) -> Tuple[float,float]
    """95% CI on AUC(b) - AUC(a), paired by test match."""
    n = len(a_scores)
    ds = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        ds.append(auc([b_scores[i] for i in idx]) - auc([a_scores[i] for i in idx]))
    ds.sort()
    return ds[int(0.025 * BOOT)], ds[int(0.975 * BOOT)]


def team_profiles(matches, hit=None):
    # type: (List[Dict], Optional[Dict]) -> Dict[str, Dict[str, float]]
    """team -> the "profile" metrics both AI proposals lean on heavily.

    Clutch rating, grit index, red-zone efficiency, resilience, blowout
    avoidance, consistency, five-set record -- between them the two lists spend
    dozens of entries on this family. Almost all of it reduces to a handful of
    quantities that ARE computable from set scores, so they can be settled
    rather than argued about:

      deuce_win     sets that went past 25 (a 27-25 needs a two-point margin)
      close_win     sets decided by two points or fewer
      blowout_for   sets won holding the opponent under 15
      blowout_vs    sets lost scoring under 15
      five_set_win  matches that went the distance
      comeback      matches won after losing the first two sets
      collapse      matches lost after winning the first two
      consistency   1 / (1 + SD of per-match margin) -- steadier is higher
      earned_share  earned points as a fraction of rally points ("silent points")

    ⚠ WHAT IS NOT HERE AND CANNOT BE: "first to 20", performance at 22-22, and
    momentum after a timeout need point-by-point data. ncaa.com does not carry
    it, and the MIT play-by-play mirror covers 2025 but has no live 2026 feed --
    so a term built on it could be measured on history and never computed during
    a season. Left out rather than half-built.
    """
    agg = collections.defaultdict(lambda: {
        "deuce_w": 0, "deuce_n": 0, "close_w": 0, "close_n": 0,
        "bfor": 0, "bvs": 0, "sets": 0, "five_w": 0, "five_n": 0,
        "cb_w": 0, "cb_n": 0, "col_l": 0, "col_n": 0,
        "margins": [], "earned": 0.0, "rally": 0.0})
    for m in matches:
        for side, opp in (("home", "away"), ("away", "home")):
            t = m[side]
            e = agg[t]
            mine_i, opp_i = (0, 1) if side == "home" else (1, 0)
            won_sets = 0
            lost_sets = 0
            order = []
            for sc in m["setscores"]:
                a, b = sc[mine_i], sc[opp_i]
                e["sets"] += 1
                if max(a, b) > 25:
                    e["deuce_n"] += 1
                    e["deuce_w"] += 1 if a > b else 0
                if abs(a - b) <= 2:
                    e["close_n"] += 1
                    e["close_w"] += 1 if a > b else 0
                if a > b and b < 15:
                    e["bfor"] += 1
                if b > a and a < 15:
                    e["bvs"] += 1
                order.append(1 if a > b else 0)
                won_sets += 1 if a > b else 0
                lost_sets += 0 if a > b else 1
            won = won_sets > lost_sets
            if len(order) == 5:
                e["five_n"] += 1
                e["five_w"] += 1 if won else 0
            if len(order) >= 2 and order[0] == 0 and order[1] == 0:
                e["cb_n"] += 1
                e["cb_w"] += 1 if won else 0
            if len(order) >= 2 and order[0] == 1 and order[1] == 1:
                e["col_n"] += 1
                e["col_l"] += 0 if won else 1
            sign = 1.0 if side == "home" else -1.0
            e["margins"].append(sign * m["margin"])
            ea = m[side + "_earned"]
            if ea is not None:
                e["earned"] += ea
                e["rally"] += (m["home_pts"] if side == "home" else m["away_pts"])

    def frac(a, b, default=0.5):
        return (a / float(b)) if b else default

    out = {}
    for t, e in agg.items():
        mg = e["margins"]
        sd = 0.0
        if len(mg) > 1:
            mu = sum(mg) / len(mg)
            sd = (sum((x - mu) ** 2 for x in mg) / (len(mg) - 1)) ** 0.5
        out[t] = {
            "deuce_win": frac(e["deuce_w"], e["deuce_n"]),
            "close_win": frac(e["close_w"], e["close_n"]),
            "blowout_for": frac(e["bfor"], e["sets"], 0.0),
            "blowout_vs": frac(e["bvs"], e["sets"], 0.0),
            "five_set_win": frac(e["five_w"], e["five_n"]),
            "comeback": frac(e["cb_w"], e["cb_n"], 0.0),
            "collapse": frac(e["col_l"], e["col_n"], 0.0),
            "consistency": 1.0 / (1.0 + sd),
            "earned_share": frac(e["earned"], e["rally"], 0.0),
            "_n": len(mg),
        }
    return out


PROFILE_FEATURES = [
    ("deuce_win", "win rate in sets that went past 25 (composure)"),
    ("close_win", "win rate in sets decided by two points or fewer (clutch)"),
    ("blowout_for", "share of sets won holding the opponent under 15 (dominance)"),
    ("blowout_vs", "share of sets lost scoring under 15 (blowout avoidance)"),
    ("five_set_win", "five-set win rate"),
    ("comeback", "share of 0-2 holes climbed out of (grit / resilience)"),
    ("collapse", "share of 2-0 leads lost"),
    ("consistency", "steadiness of per-match margin (higher = steadier)"),
    ("earned_share", "earned points as a share of rally points (silent points)"),
]


def incremental_features(matches):
    # type: (List[Dict]) -> Dict
    """Does any profile metric add to what the rating already knows?

    THE ONLY VERSION OF THIS QUESTION THAT MEANS ANYTHING IS INCREMENTAL. A
    clutch rating correlates with winning because good teams win close sets
    too; the question is whether it says anything the opponent-adjusted margin
    has not already said. So each feature is given its own coefficient, FITTED
    ON THE TRAINING HALF, and then scored on matches from the future.
    """
    cut = int(len(matches) * 0.60)
    train, test = matches[:cut], matches[cut:]
    keys = sorted(set([m["home"] for m in matches] + [m["away"] for m in matches]))
    obs, wts = scheme_obs(train, train[-1]["epoch"], {"name": "baseline"})
    fit = B.fit_off_def(obs, keys, wts)
    mu, h = fit[keys[0]]["_mu"], fit[keys[0]]["_h"]
    # profiles from TRAINING matches only -- a feature built on the test half
    # would be scoring itself.
    prof = team_profiles(train)

    def edge_of(m):
        fh, fa = fit.get(m["home"]), fit.get(m["away"])
        if not fh or not fa:
            return None
        return ((mu + fh["off"] - fa["def"] + h)
                - (mu + fa["off"] - fh["def"] - h))

    MIN_N = 5
    out = {}
    rng = random.Random(SEED + 2)
    for feat, what in PROFILE_FEATURES:
        trows, erows = [], []
        for src, dst in ((train, trows), (test, erows)):
            for m in src:
                e = edge_of(m)
                ph, pa = prof.get(m["home"]), prof.get(m["away"])
                if e is None or not ph or not pa:
                    continue
                if ph["_n"] < MIN_N or pa["_n"] < MIN_N:
                    continue
                dst.append((e, ph[feat] - pa[feat], m["home_win"]))
        if len(erows) < 200 or len(trows) < 200:
            continue
        beta = fit_rest_beta(trows)
        plain = [(e, y) for e, d, y in erows]
        withf = [(e + beta * d, y) for e, d, y in erows]
        a0, a1 = auc(plain), auc(withf)
        lo, hi = boot_delta(plain, withf, rng)
        out[feat] = {
            "what": what, "auc_without": round(a0, 5), "auc_with": round(a1, 5),
            "delta": round(a1 - a0, 5), "ci95": [round(lo, 5), round(hi, 5)],
            "beta": round(beta, 4), "helps": bool(lo > 0),
            "n_test": len(erows),
        }
    return out


def rest_analysis(matches):
    # type: (List[Dict]) -> Dict
    """Does REST explain anything the rating does not already know?

    Cody asked about a team playing early and turning around to play again the
    same afternoon. Two parts of that are in the data and one is not: days since
    a team's previous match, and whether it already played that day, come
    straight from the epochs. The travel that goes with it -- time zone, an 8am
    Eastern start for a Pacific team -- does not: 2025 carries no venue.

    The test is INCREMENTAL, which is the only version that means anything. The
    rating already predicts each match; the question is whether knowing the two
    teams' rest improves that prediction. So we fit on the first 60% and ask
    whether a rest term lifts AUC on the last 40%, and separately report the
    raw win rate by rest state -- which is descriptive and NOT causal: a team
    playing its second match of the day is usually in a tournament, and its
    opponent usually is too.
    """
    prev = {}
    for m in matches:
        for side in ("home", "away"):
            t = m[side]
            p = prev.get(t)
            m[side + "_rest"] = None if p is None else (m["epoch"] - p) / DAY
            m[side + "_same_day"] = bool(p is not None and (m["epoch"] - p) < DAY)
        prev[m["home"]] = m["epoch"]
        prev[m["away"]] = m["epoch"]

    # descriptive: win rate when a team is on its second match of the day
    same, notsame = [0, 0], [0, 0]
    for m in matches:
        for side, win in (("home", m["home_win"]), ("away", 1 - m["home_win"])):
            (same if m[side + "_same_day"] else notsame)[win] += 1
    def rate(c):
        n = c[0] + c[1]
        return (c[1] / float(n), n) if n else (float("nan"), 0)
    sw, sn = rate(same)
    nw, nn = rate(notsame)

    # incremental: does rest difference add to the rating's own edge?
    cut = int(len(matches) * 0.60)
    train, test = matches[:cut], matches[cut:]
    keys = sorted(set([m["home"] for m in matches] + [m["away"] for m in matches]))
    obs, wts = scheme_obs(train, train[-1]["epoch"], {"name": "baseline"})
    fit = B.fit_off_def(obs, keys, wts)
    mu, h = fit[keys[0]]["_mu"], fit[keys[0]]["_h"]

    plain, withrest, rows = [], [], []
    for m in test:
        fh, fa = fit.get(m["home"]), fit.get(m["away"])
        if not fh or not fa or m["home_rest"] is None or m["away_rest"] is None:
            continue
        edge = ((mu + fh["off"] - fa["def"] + h)
                - (mu + fa["off"] - fh["def"] - h))
        # rest difference, capped -- past a week more rest is just the calendar
        rd = clamp(m["home_rest"], 0, 7) - clamp(m["away_rest"], 0, 7)
        rows.append((edge, rd, m["home_win"]))
    if len(rows) < 200:
        return {"note": "not enough test matches with a previous match on file"}

    # fit the rest coefficient on the TRAIN half, never on the half it is scored on
    trows = []
    for m in train:
        fh, fa = fit.get(m["home"]), fit.get(m["away"])
        if not fh or not fa or m["home_rest"] is None or m["away_rest"] is None:
            continue
        edge = ((mu + fh["off"] - fa["def"] + h)
                - (mu + fa["off"] - fh["def"] - h))
        rd = clamp(m["home_rest"], 0, 7) - clamp(m["away_rest"], 0, 7)
        trows.append((edge, rd, m["home_win"]))
    beta = fit_rest_beta(trows)

    plain = [(e, y) for e, rd, y in rows]
    withrest = [(e + beta * rd, y) for e, rd, y in rows]
    a0, a1 = auc(plain), auc(withrest)
    rng = random.Random(SEED + 1)
    lo, hi = boot_delta(plain, withrest, rng)
    return {
        "same_day_second_match": {
            "win_rate": round(sw, 4), "team_matches": sn,
            "win_rate_when_not": round(nw, 4), "team_matches_when_not": nn,
            "warning": ("DESCRIPTIVE, NOT CAUSAL -- a team playing twice in a "
                        "day is usually in a tournament, and so is its opponent"),
        },
        "rest_term": {
            "auc_without": round(a0, 5), "auc_with": round(a1, 5),
            "delta": round(a1 - a0, 5), "ci95": [round(lo, 5), round(hi, 5)],
            "beta_per_day": round(beta, 5),
            "helps": bool(lo > 0),
            "fitted_on": "the training half only, scored on the held-out half",
        },
    }


def fit_rest_beta(rows):
    # type: (List[Tuple[float,float,int]]) -> float
    """One-parameter logistic: how much is a day of extra rest worth, in edge?"""
    if not rows:
        return 0.0
    b = 0.0
    scale = 0.35                     # edge -> logit, roughly; only b is fitted
    for _ in range(60):
        g = hh = 0.0
        for e, rd, y in rows:
            z = scale * (e + b * rd)
            pz = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            g += (y - pz) * scale * rd
            hh += pz * (1 - pz) * (scale * rd) ** 2
        if hh <= 1e-9:
            break
        step = g / hh
        b += step
        if abs(step) < 1e-7:
            break
    return b


def main():
    matches = load_matches()
    if len(matches) < 500:
        print("not enough completed matches to measure anything (%d)" % len(matches))
        return 1
    with_earned = sum(1 for m in matches
                      if m["home_earned"] is not None and m["away_earned"] is not None)
    print("%d completed D-I matches; %d (%.1f%%) also carry box scores\n"
          % (len(matches), with_earned, 100.0 * with_earned / len(matches)))

    results = {}
    per_split = {}
    for sc in SCHEMES:
        runs = [evaluate(matches, f, sc) for f in CUTOFFS]
        runs = [r for r in runs if r]
        if not runs:
            continue
        per_split[sc["name"]] = [r["scored"] for r in runs]
        results[sc["name"]] = {
            "what": sc["what"],
            "auc": sum(r["auc"] for r in runs) / len(runs),
            "rmse": sum(r["rmse"] for r in runs) / len(runs),
            "splits": len(runs),
            "home_adv_pts_per_set": sum(r["home_adv_pts_per_set"]
                                        for r in runs) / len(runs),
        }
        print("  %-18s AUC %.4f   RMSE %.3f   (%d splits)"
              % (sc["name"], results[sc["name"]]["auc"],
                 results[sc["name"]]["rmse"], len(runs)))

    base = results.get("baseline")
    if base:
        for name, r in results.items():
            r["auc_delta_vs_baseline"] = round(r["auc"] - base["auc"], 5)

        # ⚠ AN AUC DIFFERENCE IN THE THIRD DECIMAL IS NOT A FINDING UNTIL IT HAS
        # A CONFIDENCE INTERVAL. earned-blend-25 beats the baseline by 0.0016;
        # that is either a real improvement or the shape of the noise, and
        # nothing about the number itself says which. Paired bootstrap over the
        # SAME test matches, so the comparison is like-for-like.
        rng = random.Random(SEED)
        print("\n  bootstrap, %d resamples, paired on the same test matches:" % BOOT)
        for name in sorted(results, key=lambda k: -results[k]["auc"]):
            if name == "baseline":
                continue
            los, his = [], []
            for a_s, b_s in zip(per_split["baseline"], per_split[name]):
                lo, hi = boot_delta(a_s, b_s, rng)
                los.append(lo)
                his.append(hi)
            lo, hi = sum(los) / len(los), sum(his) / len(his)
            results[name]["auc_delta_ci95"] = [round(lo, 5), round(hi, 5)]
            beats = lo > 0
            results[name]["beats_baseline"] = bool(beats)
            print("    %-18s %+0.4f  CI [%+0.4f, %+0.4f]  %s"
                  % (name, results[name]["auc_delta_vs_baseline"], lo, hi,
                     "CLEAR OF ZERO" if beats else ("worse" if hi < 0 else "not distinguishable")))
        results["baseline"]["beats_baseline"] = None

    feats = incremental_features(matches)
    if feats:
        print("\n  DOES A PROFILE METRIC ADD ANYTHING THE RATING DOES NOT KNOW?")
        for f in sorted(feats, key=lambda k: -feats[k]["delta"]):
            r = feats[f]
            print("    %-14s %+0.5f  CI [%+0.5f, %+0.5f]  %s"
                  % (f, r["delta"], r["ci95"][0], r["ci95"][1],
                     "HELPS" if r["helps"] else
                     ("hurts" if r["ci95"][1] < 0 else "no")))

    rest = rest_analysis(matches)
    if "rest_term" in rest:
        rt = rest["rest_term"]
        sd = rest["same_day_second_match"]
        print("\n  REST AND TURNAROUND")
        print("    second match of the same day: %.1f%% wins (n=%d) vs %.1f%% "
              "otherwise (n=%d)  -- descriptive only"
              % (100 * sd["win_rate"], sd["team_matches"],
                 100 * sd["win_rate_when_not"], sd["team_matches_when_not"]))
        print("    adding a rest term to the rating: AUC %.5f -> %.5f  "
              "(%+.5f, CI [%+.5f, %+.5f])  %s"
              % (rt["auc_without"], rt["auc_with"], rt["delta"],
                 rt["ci95"][0], rt["ci95"][1],
                 "HELPS" if rt["helps"] else "not distinguishable from zero"))

    doc = {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "question": ("does weighting matches differently predict UNSEEN "
                         "matches better? A factor that does not improve "
                         "out-of-sample prediction gets zero weight."),
            "design": ("split by DATE at %s of the season, fit on the past, "
                       "score on the future; a random split would let a "
                       "November result inform a September rating"
                       % (", ".join("%d%%" % (c * 100) for c in CUTOFFS))),
            "already_in_every_scheme": ("opponent strength and home advantage -- "
                                        "the ridge fits mu + off_i - def_j + "
                                        "h*home_sign, so these are the baseline, "
                                        "not candidates"),
            "not_measurable_here": ("travel, time zones and local start times: "
                                    "2025 carries no venue (crawl_2025.py "
                                    "discarded location) and re-crawling a past "
                                    "season is banned. Venue is stored from 2026, "
                                    "so this becomes measurable as the season "
                                    "accumulates."),
            "matches": len(matches),
            "matches_with_box_scores": with_earned,
        },
        "schemes": results,
        "rest_and_turnaround": rest,
        "profile_features": feats,
    }
    for r in results.values():
        r.pop("scored", None)
    json.dump(doc, open(OUT, "w"), indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
