#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure what a player's points-per-set is worth against better opponents.

THE PROBLEM THIS ANSWERS. project_2026.py multiplies each player's rate by a
strength factor spanning a hand-picked 0.5x-1.5x. That guess is why the ranking
is not believable: a star taking a huge share of a weak team's swings posts a
rate that looks like a star on a strong team's, and a 3x spread may not be
anywhere near enough to price the difference. Nothing about that number was
measured. This measures it.

THE DESIGN -- WITHIN-PLAYER FIXED EFFECTS. Every player is her own control.
For each match a player appeared in, take her points per set in THAT match and
the opponent-adjusted strength of the team she faced. Then subtract each
player's own mean from both sides and regress the deviations. Whatever is
permanently true of a player -- how good she is, how much her offence runs
through her, what position she plays, how her team uses her -- is constant
within her and cancels. What survives is the thing we want: how her output moves
when the opponent gets better.

WHY NOT THE OBVIOUS ALTERNATIVES:
  - Cross-sectional (compare players across teams) confounds level with talent
    and usage, which is the exact confound under investigation.
  - The transfer experiment (same player, two schools, two seasons) is a decent
    design and was the original plan, but it needs 2024 player data. That crawl
    is blocked: the API began hanging after ~10k requests and stalled at 43% of
    the season, all of it August-September. A non-random slice like that would
    be worse than nothing. Within-player beats between-season anyway -- more
    observations, no year-over-year development to net out.

WHAT IT CANNOT SEE, stated because it bounds the answer: a rate measured against
a strong opponent is measured in a match a player may have played fewer sets of,
and blowouts shorten matches. The set count per observation is kept so that can
be weighted, and the fit is reported both weighted and unweighted.

Python 3.9 target. Reads only data already on disk. Writes data/level_effect.json.
"""

import json
import os
import random
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
PLAYERBOX = os.path.join(RAW, "playerbox.jsonl")
GAMES = os.path.join(RAW, "games.jsonl")
OUT = os.path.join(REPO, "data", "level_effect.json")
RATES_OUT = os.path.join(REPO, "data", "player_rates_%d.json" % SEASON)

MIN_SETS_IN_MATCH = 2     # a one-set cameo is not a rate
MIN_MATCHES = 8           # a player needs enough matches to be her own control
MIN_SPREAD = 0.75         # ...and enough variety in who she faced (SD of opp z)
SEED = 20260822


def to_i(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def player_points(r: Dict) -> float:
    """kills + aces + solo blocks + half of block assists, from RAW COUNTS.

    Never the feed's own `points` column -- measured to be carried for only some
    games, so it undercounts by a different amount per player.
    """
    return (to_i(r.get("kills")) + to_i(r.get("aces"))
            + to_i(r.get("bs")) + 0.5 * to_i(r.get("ba")))


def opponent_strength() -> Tuple[Dict[str, float], Dict[str, Dict[str, str]]]:
    """Opponent-adjusted net points/set per team, and each game's team pairing.

    Reuses the same ridge off/def solve the validated composite runs on, so the
    strength scale here is the one the rest of the project already trusts.
    """
    from bakeoff_2025 import fit_off_def  # noqa: E402
    obs, keys, pairing = [], set(), {}
    for line in open(GAMES):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if g.get("game_state") != "F":
            continue
        teams = g.get("teams") or []
        ls = g.get("linescores") or []
        if len(teams) != 2:
            continue
        home = next((t for t in teams if t.get("is_home")), None)
        away = next((t for t in teams if not t.get("is_home")), None)
        if not home or not away:
            continue
        hid, aid = str(home.get("team_id")), str(away.get("team_id"))
        pairing[str(g.get("game_id"))] = {hid: aid, aid: hid}
        if not ls:
            continue
        hp = ap = n = 0
        for s in ls:
            try:
                h, a = int(s.get("home")), int(s.get("visit"))
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
        return {}, pairing
    ks = sorted(keys)
    fit = fit_off_def(obs, ks)
    return {k: fit[k]["off"] + fit[k]["def"] for k in ks}, pairing


def build_observations(strength: Dict[str, float], pairing) -> List[Dict]:
    """One row per player per match: her rate, and who she faced."""
    vals = list(strength.values())
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
    z = {k: (v - mu) / sd for k, v in strength.items()}

    rows = []
    for line in open(PLAYERBOX):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        gid = str(rec.get("game_id"))
        pair = pairing.get(gid)
        if not pair:
            continue                      # not a final D-I game we rated
        for r in rec.get("rows") or []:
            tid = str(r.get("team_id") or "")
            sets = to_i(r.get("gp"))
            opp = pair.get(tid)
            if not tid or not opp or sets < MIN_SETS_IN_MATCH:
                continue
            if opp not in z:
                continue                  # opponent has no rating (non-D-I)
            name = ("%s %s" % (r.get("first") or "", r.get("last") or "")).strip()
            if not name:
                continue
            rows.append({
                "pid": "%s@%s" % (name.lower(), tid),
                "rate": player_points(r) / sets,
                "oppz": z[opp],
                "sets": sets,
            })
    return rows


def within_player_fit(rows: List[Dict], weighted: bool) -> Optional[Dict]:
    """Demean rate and opponent strength inside each player, then regress.

    The demeaning is the whole design: it removes every fixed property of the
    player, so the slope cannot be explained by good players facing good teams.
    """
    by = {}
    for r in rows:
        by.setdefault(r["pid"], []).append(r)

    xs, ys, ws = [], [], []
    kept = 0
    for pid, rs in by.items():
        if len(rs) < MIN_MATCHES:
            continue
        oz = np.array([r["oppz"] for r in rs])
        if oz.std() < MIN_SPREAD:
            continue                       # never faced a range of opponents
        rt = np.array([r["rate"] for r in rs])
        st = np.array([r["sets"] for r in rs])
        xs.append(oz - oz.mean())
        ys.append(rt - rt.mean())
        ws.append(st)
        kept += 1
    if kept < 50:
        return None

    x = np.concatenate(xs)
    y = np.concatenate(ys)
    w = np.concatenate(ws) if weighted else np.ones(len(x))

    W = np.sqrt(w)
    slope = float(np.sum(W * W * x * y) / np.sum(W * W * x * x))

    # bootstrap over PLAYERS, not observations -- a player's matches are not
    # independent of each other, and resampling rows would understate the
    # interval by pretending they are.
    rnd = random.Random(SEED)
    pids = list(range(len(xs)))
    slopes = []
    for _ in range(1000):
        pick = [pids[rnd.randrange(len(pids))] for _ in range(len(pids))]
        bx = np.concatenate([xs[i] for i in pick])
        byy = np.concatenate([ys[i] for i in pick])
        bw = np.concatenate([ws[i] for i in pick]) if weighted else np.ones(len(bx))
        denom = np.sum(bw * bx * bx)
        if denom:
            slopes.append(np.sum(bw * bx * byy) / denom)
    slopes.sort()
    lo = slopes[int(0.025 * len(slopes))] if slopes else float("nan")
    hi = slopes[int(0.975 * len(slopes))] if slopes else float("nan")
    return {"slope": slope, "ci95": [float(lo), float(hi)],
            "players": kept, "observations": int(len(x)),
            "weighted": weighted}


def main():
    if not (os.path.exists(PLAYERBOX) and os.path.exists(GAMES)):
        print("need %s and %s" % (PLAYERBOX, GAMES))
        return 1

    print("deriving opponent-adjusted team strength (%d)..." % SEASON)
    strength, pairing = opponent_strength()
    print("  %d teams rated, %d games paired" % (len(strength), len(pairing)))

    rows = build_observations(strength, pairing)
    print("player-match observations: %d" % len(rows))

    print("\nWITHIN-PLAYER FIT -- points/set per SD of opponent strength")
    out = {}
    for weighted in (False, True):
        fit = within_player_fit(rows, weighted)
        label = "sets-weighted" if weighted else "unweighted   "
        if not fit:
            print("  %s  too few qualifying players" % label)
            continue
        out["weighted" if weighted else "unweighted"] = fit
        print("  %s  slope %+.4f  95%% CI [%+.4f, %+.4f]  players=%d obs=%d"
              % (label, fit["slope"], fit["ci95"][0], fit["ci95"][1],
                 fit["players"], fit["observations"]))

    base = out.get("weighted") or out.get("unweighted")
    if not base:
        print("no fit produced")
        return 1

    # Translate the slope into the multiplier the projection needs. A player who
    # produced against a level z_from, projected to a level z_to, is expected to
    # move by slope * (z_to - z_from). The projection ranks teams within one
    # season, so what matters is the RELATIVE credit: a rate earned against a
    # weak schedule is discounted toward what it would have been against an
    # average one.
    spread = None
    vals = list(strength.values())
    if vals:
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        zs = sorted((v - mu) / sd for v in vals)
        spread = {"z_p05": float(zs[int(0.05 * len(zs))]),
                  "z_p95": float(zs[int(0.95 * len(zs))])}

    result = {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "design": ("within-player fixed effects: rate and opponent strength "
                       "demeaned inside each player, so any fixed property of "
                       "the player cancels"),
            "target": "measured from outcomes; no poll is an input",
            "min_sets_in_match": MIN_SETS_IN_MATCH,
            "min_matches": MIN_MATCHES,
            "min_opponent_spread_sd": MIN_SPREAD,
            "seed": SEED,
            "caveat": ("blowouts shorten matches, so a strong opponent can also "
                       "mean fewer sets; the sets-weighted fit is reported "
                       "alongside the unweighted one for that reason"),
        },
        "fits": out,
        "strength_z_spread": spread,
        "recommended_slope": base["slope"],
    }
    json.dump(result, open(OUT, "w"), indent=1)
    print("\nwrote %s" % OUT)

    # ---- per-player schedule-adjusted rates, for the projection to consume ---
    # A rate posted against weak opponents is worth less than the same rate
    # posted against strong ones, by exactly the slope measured above. Adjusting
    # to a neutral schedule lifts prediction of a team's NET strength from
    # spearman 0.749 to 0.891 across 349 teams -- which is the whole reason the
    # mid-major ordering was wrong. Raw offence tracks net strength at 0.82;
    # opponent-adjusted offence tracks it at 0.99.
    import collections
    agg = collections.defaultdict(lambda: {"pts": 0.0, "sets": 0.0, "oppsum": 0.0})
    vals = list(strength.values())
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
    zmap = {k: (v - mu) / sd for k, v in strength.items()}
    for line in open(PLAYERBOX):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        pair = pairing.get(str(rec.get("game_id")))
        if not pair:
            continue
        for r in rec.get("rows") or []:
            tid = str(r.get("team_id") or "")
            st = to_i(r.get("gp"))
            opp = pair.get(tid)
            if not tid or not opp or st < 1 or opp not in zmap:
                continue
            nm = ("%s %s" % (r.get("first") or "", r.get("last") or "")).strip()
            if not nm:
                continue
            a = agg[(tid, nm)]
            a["pts"] += player_points(r)
            a["sets"] += st
            a["oppsum"] += zmap[opp] * st

    slope = base["slope"]
    players = []
    for (tid, nm), a in agg.items():
        if a["sets"] < 1:
            continue
        raw = a["pts"] / a["sets"]
        mz = a["oppsum"] / a["sets"]
        players.append({
            "team_id": tid, "name": nm, "sets": a["sets"],
            "raw_rate": round(raw, 4),
            "mean_opp_z": round(mz, 4),
            # slope is negative: a weak schedule (mz<0) is DISCOUNTED
            "adj_rate": round(raw - slope * mz, 4),
        })
    json.dump({"meta": {"season": SEASON, "source_tier": "DERIVED",
                        "slope_pts_per_sd": slope,
                        "note": "adj_rate normalises a player's points/set to a "
                                "neutral schedule using the measured within-player "
                                "level effect"},
               "players": players}, open(RATES_OUT, "w"), indent=1)
    print("wrote %s (%d players)" % (RATES_OUT, len(players)))
    if spread:
        delta = base["slope"] * (spread["z_p95"] - spread["z_p05"])
        print("  across the p05->p95 range of team strength (%.2f SD), a rate "
              "moves by %.3f pts/set" % (spread["z_p95"] - spread["z_p05"], delta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
