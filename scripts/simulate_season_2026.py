#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Play the rest of the 2026 season, many times, and see how it lands.

Every match still to come has a win probability (scripts/predict_2026.py, rally
model, calibrated Brier 0.1289). This runs the whole remaining schedule
repeatedly to turn those into the things actually worth knowing: a team's likely
final record, its chance of winning its conference, its chance of finishing top
of the country.

TWO CORRECTIONS THAT MOST SEASON SIMULATIONS SKIP, both measured here rather
than assumed:

1. SHRINK THE PRIOR. Regressing 2025 net points/set on 2024 across 346 teams
   gives slope 0.860, not 1.0 -- last season's rating overstates how extreme a
   team will be this season. Using it raw makes the strong too strong and the
   weak too weak, all season.

2. CARRY THE UNCERTAINTY. That same fit leaves a residual SD of 2.12 points per
   set, against a between-team SD of 4.48. So a team's true 2026 strength is
   genuinely uncertain, and a simulation that fixes strength and only flips
   match coins produces win totals far too narrow -- it would tell you Nebraska
   wins 24-26 matches when the honest answer is a much wider band. Each
   iteration therefore redraws every team's strength before playing any match.

   This matters more than it sounds: fixing strength makes the model
   overconfident in exactly the direction that looks impressive and is wrong.

WHAT IT DOES NOT MODEL, said plainly: injuries and absences (nothing in the feed
predicts them), in-season improvement, and the correlation between a team's
matches beyond shared strength. Conference titles are decided here on conference
win totals, which is the regular-season race -- not the tournaments most leagues
actually use to award their bid.

Python 3.9 target. Writes data/season_sim_2026.json.
"""

import json
import os
import sys
import collections
from typing import Dict, List, Optional

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulate_2025 as S  # noqa: E402

SEASON = 2026
OUT = os.path.join(REPO, "data", "season_sim_%d.json" % SEASON)

# both measured, 2024 -> 2025, n=346
PRIOR_SLOPE = 0.8597
PRIOR_INTERCEPT = 0.0246
PRIOR_RESIDUAL_SD = 2.123
HOME_ADV = 0.333          # points/set, from our own ridge fit

ITERATIONS = int(os.environ.get("WVB_SIM_ITERS", "4000"))
SEED = 20260822


def load(p, default=None):
    path = os.path.join(REPO, p)
    return json.load(open(path)) if os.path.exists(path) else default


def build():
    rating = load("data/rating_2025.json") or {}
    strength = {}
    conf = {}
    for t in rating.get("teams", []):
        if t.get("adj_net_points_set") is not None:
            strength[t["team"]] = t["adj_net_points_set"]
            conf[t["team"]] = t.get("conference")
    conf26 = (load("data/raw/%d/conferences_%d.json" % (SEASON, SEASON)) or {}).get("teams", {})
    for k, v in conf26.items():
        conf[k] = v
    if not strength:
        print("no 2025 rating to stand on")
        return None

    preds = load("data/predictions_%d.json" % SEASON) or {}
    fixtures = [r for r in preds.get("games", [])
                if r["home"] in strength and r["away"] in strength]
    if not fixtures:
        print("no fixtures to simulate")
        return None

    # results already in the book
    played = collections.defaultdict(lambda: [0, 0])
    # ⚠ AUDIT D5 (2026-08-31): this loop had its own FIRST-seen-wins
    # dedup -- a stale record beating its own revision, the exact
    # anti-pattern the append-only log exists to prevent -- plus no
    # duplicate/exhibition/review exclusion, no result corrections, and
    # a winnerless final scored the non-winner as a LOSS. One chain:
    # gamelog's dedup + season_counts' classification + corrections.
    gpath = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if os.path.exists(gpath):
        import gamelog
        import season_counts as _SC
        for g in _SC.countable(gamelog.load_games_jsonl(gpath), SEASON):
            ts = g.get("teams") or []
            if len(ts) != 2:
                continue
            win = str(g.get("winner_team_id") or "")
            if not win:
                continue               # no asserted winner, no tally
            for t in ts:
                nm = t.get("name_short")
                if nm not in strength:
                    continue
                if str(t.get("team_id")) == win:
                    played[nm][0] += 1
                else:
                    played[nm][1] += 1

    teams = sorted(strength)
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    base = np.array([PRIOR_SLOPE * strength[t] + PRIOR_INTERCEPT for t in teams])
    hi = np.array([idx[f["home"]] for f in fixtures])
    ai = np.array([idx[f["away"]] for f in fixtures])
    # The fitted home edge, zero on a neutral floor. Taken as a constant rather
    # than re-derived from each fixture's stored margin, because that margin was
    # computed from the UNSHRUNK prior and this simulation uses the shrunk one.
    adv = np.array([0.0 if f["neutral"] else HOME_ADV for f in fixtures])

    # ---- tournament bids -------------------------------------------------
    # 32 automatic bids go to conference winners; the rest of the field is the
    # best remaining resume. RESUME, not strength: the committee weights
    # won-lost results, which is why project_field.py refuses the composite.
    # The proxy here is RPI's own shape -- 25% own win pct, 50% opponents',
    # 25% opponents' opponents' -- computed from each simulated season's win
    # graph rather than from team ratings.
    FIELD_SIZE = 64
    adjacency = np.zeros((n, n))
    for f in fixtures:
        adjacency[idx[f["home"]], idx[f["away"]]] += 1
        adjacency[idx[f["away"]], idx[f["home"]]] += 1
    opp_counts = adjacency.sum(axis=1)
    opp_counts[opp_counts == 0] = 1.0

    bids = np.zeros(n)
    wins = np.zeros(n)
    conf_wins = np.zeros(n)
    win_counts = np.zeros((n, 40))          # histogram of final win totals
    conf_titles = np.zeros(n)

    # conference membership as index lists
    by_conf = collections.defaultdict(list)
    for t in teams:
        c = conf.get(t)
        if c:
            by_conf[c].append(idx[t])
    is_conf_game = np.array([1 if (conf.get(f["home"]) and
                                   conf.get(f["home"]) == conf.get(f["away"])) else 0
                             for f in fixtures], dtype=bool)

    fixture_count = collections.Counter()
    for f in fixtures:
        fixture_count[f["home"]] += 1
        fixture_count[f["away"]] += 1

    # matches each team will have played by season's end
    games_played = np.array(
        [fixture_count.get(t, 0) + played[t][0] + played[t][1] for t in teams],
        dtype=float)

    start_w = np.array([played[t][0] for t in teams], dtype=float)
    rng = np.random.default_rng(SEED)
    R = S.RALLIES_PER_SET

    # SET-WIN PROBABILITY AS A LOOKUP, not 14 million Python calls.
    # set_win_prob() is a tidy scalar function and calling it per fixture per
    # iteration made a 1,500-iteration run take longer than ten minutes. It is
    # smooth and monotone in p over a narrow clipped range, so sampling it on a
    # fine grid once and interpolating is exact to well past the precision any
    # of this deserves -- and turns the run into seconds.
    grid = np.linspace(0.10, 0.90, 1601)
    tbl25 = np.array([S.set_win_prob(x, 25) for x in grid])
    tbl15 = np.array([S.set_win_prob(x, 15) for x in grid])

    for _ in range(ITERATIONS):
        # redraw every team's true strength -- the correction that keeps the
        # win-total bands honest
        s = base + rng.normal(0.0, PRIOR_RESIDUAL_SD, n)
        margin = (s[hi] + adv) - s[ai]
        p = np.clip(0.5 + margin / (2.0 * R), 0.10, 0.90)

        # set win probability, then match win probability, vectorised
        pw = np.interp(p, grid, tbl25)
        pw5 = np.interp(p, grid, tbl15)
        q = 1.0 - pw
        home_win = pw ** 3 + 3 * (pw ** 3) * q + 6 * (pw ** 2) * (q ** 2) * pw5

        draw = rng.random(len(fixtures)) < home_win
        w = start_w.copy()
        np.add.at(w, hi[draw], 1.0)
        np.add.at(w, ai[~draw], 1.0)
        wins += w

        cw = np.zeros(n)
        cd = draw & is_conf_game
        cnd = (~draw) & is_conf_game
        np.add.at(cw, hi[cd], 1.0)
        np.add.at(cw, ai[cnd], 1.0)
        conf_wins += cw

        b = np.clip(np.rint(w).astype(int), 0, 39)
        np.add.at(win_counts, (np.arange(n), b), 1.0)

        champions = []
        for c, members in by_conf.items():
            if len(members) < 2:
                continue
            m = np.array(members)
            best = cw[m].max()
            leaders = m[cw[m] >= best]
            # a shared lead splits the credit rather than picking one at random
            conf_titles[leaders] += 1.0 / len(leaders)
            # one bid per conference, so a tie is broken by overall wins
            champions.append(int(leaders[np.argmax(w[leaders])]))

        # RPI-shaped resume from this simulated season
        total = w + (games_played - w)
        total[total == 0] = 1.0
        wp = w / total
        owp = adjacency.dot(wp) / opp_counts
        oowp = adjacency.dot(owp) / opp_counts
        rpi = 0.25 * wp + 0.50 * owp + 0.25 * oowp

        field = set(champions)
        order = np.argsort(-rpi)
        for i in order:
            if len(field) >= FIELD_SIZE:
                break
            field.add(int(i))
        for i in field:
            bids[i] += 1

    rows = []
    for t in teams:
        i = idx[t]
        hist = win_counts[i]
        tot = hist.sum() or 1
        cum = np.cumsum(hist) / tot
        p10 = int(np.searchsorted(cum, 0.10))
        p50 = int(np.searchsorted(cum, 0.50))
        p90 = int(np.searchsorted(cum, 0.90))
        # NO FIXTURES IS NOT A PROJECTION OF ZERO. Two teams have no scheduled
        # matches we can rate (their 2026 conference never resolved), and
        # reporting "0.0 projected wins" for them reads as a forecast of a
        # winless season rather than an absence of data.
        n_fix = fixture_count.get(t, 0)
        if n_fix == 0 and played[t][0] + played[t][1] == 0:
            rows.append({"team": t, "conference": conf.get(t), "played": 0,
                         "record_so_far": "0-0", "proj_wins_mean": None,
                         "proj_wins_p10": None, "proj_wins_p50": None,
                         "proj_wins_p90": None, "conf_wins_mean": None,
                         "conf_title_pct": None, "tournament_pct": None,
                         "fixtures": 0,
                         "note": "no rateable fixtures on file"})
            continue
        rows.append({
            "team": t,
            "fixtures": n_fix,
            "conference": conf.get(t),
            "played": played[t][0] + played[t][1],
            "record_so_far": "%d-%d" % (played[t][0], played[t][1]),
            "proj_wins_mean": round(wins[i] / ITERATIONS, 2),
            "proj_wins_p10": p10,
            "proj_wins_p50": p50,
            "proj_wins_p90": p90,
            "conf_wins_mean": round(conf_wins[i] / ITERATIONS, 2),
            "conf_title_pct": round(100.0 * conf_titles[i] / ITERATIONS, 1),
            "tournament_pct": round(100.0 * bids[i] / ITERATIONS, 1),
        })
    rows.sort(key=lambda r: (r["proj_wins_mean"] is None,
                             -(r["proj_wins_mean"] or 0)))

    return {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "iterations": ITERATIONS,
            "seed": SEED,
            "prior_slope": PRIOR_SLOPE,
            "prior_residual_sd": PRIOR_RESIDUAL_SD,
            "match_model": "rally model, calibrated Brier 0.1289 on 2025",
            "strength_uncertainty": ("each iteration redraws every team's strength "
                                     "from the prior plus its measured residual; "
                                     "fixing strength would make the win bands far "
                                     "too narrow"),
            "tournament_backtest": (
                "2024 prior -> simulated 2025 -> compared to the field that "
                "actually happened (recovered from championship-flagged games): "
                "the simulated top 64 contained 42 of the real 64, and the odds "
                "are calibrated across the range -- 95% band went 100%, 60% band "
                "went 71%, 19% band went 15%, 2% band went 2%. For contrast "
                "project_field.py gets 62/64, but from a COMPLETED season's "
                "results; this is preseason, from last year alone"),
            "backtest": ("2024 prior -> simulated 2025 -> compared to actual: the "
                         "80% win-total band contained the true result for 87.3% of "
                         "346 teams, and the median projection missed by 3.74 wins. "
                         "The band is slightly WIDE rather than narrow, which is the "
                         "safe direction; it was left alone rather than tuned to hit "
                         "80% exactly on a single season"),
            "not_modelled": ("injuries and absences, in-season improvement, and "
                             "conference tournaments -- titles here are the "
                             "regular-season race"),
            "fixtures_simulated": len(fixtures),
            "teams": len(teams),
        },
        "teams": rows,
    }


if __name__ == "__main__":
    out = build()
    if not out:
        sys.exit(1)
    json.dump(out, open(OUT, "w"), indent=1)
    m = out["meta"]
    print("wrote %s" % OUT)
    print("  %d iterations over %d fixtures, %d teams"
          % (m["iterations"], m["fixtures_simulated"], m["teams"]))
    print("\n  %-22s %-13s %8s  %-12s %s" %
          ("team", "conf", "proj W", "80% range", "conf title"))
    for r in out["teams"][:20]:
        if r["proj_wins_mean"] is None:
            continue
        print("  %-22s %-13s %8.1f  %2d-%-2d        %5.1f%%"
              % (r["team"][:22], (r["conference"] or "")[:13], r["proj_wins_mean"],
                 r["proj_wins_p10"], r["proj_wins_p90"], r["conf_title_pct"]))
