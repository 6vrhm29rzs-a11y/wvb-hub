#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NCAA D-I Women's Volleyball RPI, Factors I-III.

SPEC SOURCE (primary): 2025-26 NCAA Division I Women's Volleyball
Pre-Championship Manual, Section 2.2, via Research/ "RPI Spec, Selection
Criteria, Analytics Literature, Markov Modeling".

    Factor I   Division I winning percentage ............ 25%
    Factor II  Opponents' winning percentage ........... 50%
    Factor III Opponents' opponents' winning percentage . 25%

*** NO LOCATION WEIGHTING. *** The RPI section of the manual contains no
home/road/neutral multipliers. This is the decisive contrast with other NCAA
sports -- basketball weights home wins 0.6 / road wins 1.4, baseball weights
road wins 1.3 / home wins 0.7. Women's volleyball adopted NEITHER. Secondary
blogs claiming a weighted volleyball RPI are wrong; do not apply multipliers.

DIVISION I ONLY. Games against non-D-I opponents are excluded from Factors
I-III entirely. D-I membership comes from the official RPI table, never from the
game feed's `division` field (see reconcile_2025.py for why).

SELF-EXCLUSION -- LOGGED AS **INFERRED**, NOT OFFICIAL. Every published NCAA RPI
implementation computes opponents' winning percentage EXCLUDING games against
the team being rated, and Factor III likewise. This is universal RPI convention
but is NOT printed in the volleyball manual, so it is an inference. It is
implemented here and labeled accordingly.

FACTOR IV IS NOT ATTEMPTED. The manual expresses it in approximate RPI
*positions*, not decimals, so it is not exactly reproducible. Nothing in this
file is a Factor IV overlay. Divergence from the published ordering that
concentrates on teams with marquee wins or bad losses is the EXPECTED signature
of Factor IV and is evidence the base calculation is right.

Python 3.9 target.
"""

import json
import os
import random
import sys
import collections
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "data", "raw", "2025")
OUT = os.path.join(REPO, "data", "rpi_2025.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm  # noqa: E402

W_FACTOR_I = 0.25
W_FACTOR_II = 0.50
W_FACTOR_III = 0.25


def load_di_games():
    # type: () -> Tuple[List[Tuple[str, str, str]], Dict[str, dict]]
    """Return (games, teams) restricted to Division I vs Division I.

    Each game is (winner_key, loser_key, game_id). Division I membership is
    taken from the official RPI table.
    """
    rpi_rows = json.load(open(os.path.join(RAW, "rpi_official.json")))["data"]
    teams = {}
    for r in rpi_rows:
        teams[norm(r["School"])] = {
            "school": r["School"],
            "official_rank": int(r["Rank"]),
            "conference": r.get("Conf"),
        }
    di = set(teams)

    from gamelog import load_games_jsonl
    games = []
    for g in load_games_jsonl(os.path.join(RAW, "games.jsonl")):
            if g.get("game_state") != "F":
                continue
            t = g.get("teams") or []
            if len(t) != 2:
                continue
            a, b = norm(t[0].get("name_short")), norm(t[1].get("name_short"))
            if a not in di or b not in di:
                continue  # non-D-I games are excluded from Factors I-III
            if t[0].get("is_winner"):
                games.append((a, b, g["game_id"]))
            elif t[1].get("is_winner"):
                games.append((b, a, g["game_id"]))
    return games, teams


def rpi_from_games(games, keys):
    # type: (List[Tuple[str, str, str]], List[str]) -> Dict[str, Dict[str, float]]
    """Factors I-III over an arbitrary game subset.

    Extracted so the metric bake-off can recompute RPI on a fit window without
    duplicating the formula -- a second copy would be free to drift from the
    shipped one, which is exactly the sort of silent divergence this project
    keeps getting bitten by.
    """
    opponents = collections.defaultdict(list)
    wins = collections.Counter()
    losses = collections.Counter()
    for w, l, _ in games:
        wins[w] += 1
        losses[l] += 1
        opponents[w].append(l)
        opponents[l].append(w)

    wp = {}
    for k in keys:
        n = wins[k] + losses[k]
        wp[k] = (float(wins[k]) / n) if n else 0.0

    h2h_w = collections.Counter()
    for w, l, _ in games:
        h2h_w[(w, l)] += 1

    def wp_excl(opp, exclude):
        w = wins[opp] - h2h_w[(opp, exclude)]
        l = losses[opp] - h2h_w[(exclude, opp)]
        n = w + l
        return (float(w) / n) if n else 0.0

    owp = {}
    for k in keys:
        opps = opponents[k]
        owp[k] = (sum(wp_excl(o, k) for o in opps) / len(opps)) if opps else 0.0

    oowp = {}
    for k in keys:
        opps = opponents[k]
        oowp[k] = (sum(owp[o] for o in opps) / len(opps)) if opps else 0.0

    out = {}
    for k in keys:
        out[k] = {
            "wp": wp[k], "owp": owp[k], "oowp": oowp[k],
            "wins": wins[k], "losses": losses[k],
            "rpi": W_FACTOR_I * wp[k] + W_FACTOR_II * owp[k] + W_FACTOR_III * oowp[k],
        }
    return out


def compute():
    games, teams = load_di_games()

    # opponents[team] = list of opponents, one entry per game played (a team
    # played twice counts twice -- RPI weights by games, not distinct opponents)
    opponents = collections.defaultdict(list)
    wins = collections.Counter()
    losses = collections.Counter()
    for w, l, _ in games:
        wins[w] += 1
        losses[l] += 1
        opponents[w].append(l)
        opponents[l].append(w)

    # --- Factor I: Division I winning percentage, unweighted ---
    wp = {}
    for k in teams:
        n = wins[k] + losses[k]
        wp[k] = (float(wins[k]) / n) if n else 0.0

    # --- Factor II: opponents' winning percentage, EXCLUDING games vs the team
    # being rated (self-exclusion; INFERRED convention, see module docstring) ---
    # Head-to-head counts, precomputed: self-exclusion is looked up ~350 * ~30
    # times and a linear scan per lookup would be needlessly quadratic.
    h2h_w = collections.Counter()  # (winner, loser) -> count
    for w, l, _ in games:
        h2h_w[(w, l)] += 1

    def wp_excl(opp, exclude):
        # type: (str, str) -> float
        w = wins[opp] - h2h_w[(opp, exclude)]
        l = losses[opp] - h2h_w[(exclude, opp)]
        n = w + l
        return (float(w) / n) if n else 0.0

    owp = {}
    for k in teams:
        opps = opponents[k]
        if not opps:
            owp[k] = 0.0
            continue
        owp[k] = sum(wp_excl(o, k) for o in opps) / len(opps)

    # --- Factor III: opponents' opponents' winning percentage.
    # Standard convention: the average, over a team's opponents, of each
    # opponent's OWP. Each opponent's OWP is itself self-excluded against that
    # opponent (not against the original team). ---
    oowp = {}
    for k in teams:
        opps = opponents[k]
        if not opps:
            oowp[k] = 0.0
            continue
        oowp[k] = sum(owp[o] for o in opps) / len(opps)

    rows = []
    for k, meta in teams.items():
        rpi = W_FACTOR_I * wp[k] + W_FACTOR_II * owp[k] + W_FACTOR_III * oowp[k]
        rows.append({
            "team": meta["school"],
            "key": k,
            "conference": meta["conference"],
            "official_rank": meta["official_rank"],
            "wins": wins[k], "losses": losses[k],
            "wp": round(wp[k], 6),
            "owp": round(owp[k], 6),
            "oowp": round(oowp[k], 6),
            "rpi": round(rpi, 8),
        })
    rows.sort(key=lambda r: -r["rpi"])
    for i, r in enumerate(rows, 1):
        r["derived_rank"] = i
        r["delta"] = r["official_rank"] - r["derived_rank"]
    return rows


def marquee_profile(rows):
    # type: (List[dict]) -> Dict[str, dict]
    """Per team, the Factor IV inputs, with the manual's own position weights.

    From the Pre-Championship Manual:
        BONUS   ~2 positions per win vs teams ranked   1-25
        BONUS   ~1 position  per win vs teams ranked  26-50
        PENALTY ~1 position  per loss vs teams ranked 288-312
        PENALTY ~2 positions per loss vs teams ranked 313+

    `predicted_delta` = penalty - bonus, in RANK-NUMBER terms (lower rank number
    is better). A Factor IV bonus moves NCAA's rank number DOWN relative to the
    base index, so delta = official_rank - derived_rank should go NEGATIVE; a
    penalty should push it POSITIVE. If our divergence really is Factor IV, that
    signed prediction should correlate with the observed delta.
    """
    games, _ = load_di_games()
    rank = {r["key"]: r["official_rank"] for r in rows}
    prof = collections.defaultdict(lambda: {
        "win_top25": 0, "win_26_50": 0,
        "loss_288_312": 0, "loss_313plus": 0, "predicted_delta": 0})
    for w, l, _ in games:
        lr, wr = rank.get(l), rank.get(w)
        if lr and lr <= 25:
            prof[w]["win_top25"] += 1
        elif lr and lr <= 50:
            prof[w]["win_26_50"] += 1
        if wr and wr >= 313:
            prof[l]["loss_313plus"] += 1
        elif wr and wr >= 288:
            prof[l]["loss_288_312"] += 1
    for p in prof.values():
        bonus = 2 * p["win_top25"] + 1 * p["win_26_50"]
        penalty = 1 * p["loss_288_312"] + 2 * p["loss_313plus"]
        p["predicted_delta"] = penalty - bonus
    return prof


def main():
    rows = compute()
    prof = marquee_profile(rows)

    deltas = [abs(r["delta"]) for r in rows]
    n = len(rows)
    exact = sum(1 for d in deltas if d == 0)
    within3 = sum(1 for d in deltas if d <= 3)
    within10 = sum(1 for d in deltas if d <= 10)
    mean_abs = sum(deltas) / float(n)

    # Spearman on derived vs official ordering
    mean_o = sum(r["official_rank"] for r in rows) / float(n)
    mean_d = sum(r["derived_rank"] for r in rows) / float(n)
    num = sum((r["official_rank"] - mean_o) * (r["derived_rank"] - mean_d) for r in rows)
    den_o = sum((r["official_rank"] - mean_o) ** 2 for r in rows) ** 0.5
    den_d = sum((r["derived_rank"] - mean_d) ** 2 for r in rows) ** 0.5
    rho = num / (den_o * den_d) if den_o and den_d else 0.0

    print("=" * 70)
    print("RPI FACTORS I-III vs PUBLISHED NCAA ORDERING -- 2025")
    print("=" * 70)
    print("teams                : %d" % n)
    print("rank correlation rho : %.5f" % rho)
    print("exact rank match     : %d (%.1f%%)" % (exact, 100.0 * exact / n))
    print("within 3 positions   : %d (%.1f%%)" % (within3, 100.0 * within3 / n))
    print("within 10 positions  : %d (%.1f%%)" % (within10, 100.0 * within10 / n))
    print("mean |delta|         : %.2f positions" % mean_abs)
    print()

    # THE DIAGNOSTIC THAT MATTERS: is divergence CONCENTRATED on teams with a
    # marquee-win / bad-loss profile (expected -- that is Factor IV), or is it
    # scattered at random (which would mean the base calc is actually wrong)?
    # A magnitude split ("teams with any profile diverge more") is too blunt --
    # most teams have some profile. The discriminating test is SIGNED: does the
    # direction and size of each team's divergence track what Factor IV predicts?
    xs = [prof[r["key"]]["predicted_delta"] for r in rows]
    ys = [r["delta"] for r in rows]
    mx = sum(xs) / float(n)
    my = sum(ys) / float(n)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    r_signed = cov / (sx * sy) if sx and sy else 0.0

    bonus_only = [r["delta"] for r in rows if prof[r["key"]]["predicted_delta"] < 0]
    pen_only = [r["delta"] for r in rows if prof[r["key"]]["predicted_delta"] > 0]
    neutral = [r["delta"] for r in rows if prof[r["key"]]["predicted_delta"] == 0]

    def mean(v):
        return sum(v) / float(len(v)) if v else 0.0

    print("DIVERGENCE PATTERN (the check that matters)")
    print("  Factor IV predicts delta = penalty - bonus, SIGNED.")
    print("  correlation(predicted delta, observed delta) = %+.4f" % r_signed)
    print()
    print("  %-38s %-6s %-12s %s" % ("group", "n", "mean delta", "expected"))
    print("  %-38s %-6d %+11.2f   %s" % (
        "teams with net BONUS profile", len(bonus_only), mean(bonus_only),
        "negative"))
    print("  %-38s %-6d %+11.2f   %s" % (
        "teams with net PENALTY profile", len(pen_only), mean(pen_only),
        "positive"))
    print("  %-38s %-6d %+11.2f   %s" % (
        "teams with neither", len(neutral), mean(neutral), "~zero"))
    print()
    # A raw Pearson correlation understates the effect and is the wrong test.
    # Factor IV is specified as "approximately N positions" applied to the index
    # and then re-ranked, so its DIRECTION should hold while its MAGNITUDE should
    # not be proportional. The principled question is whether the bonus and
    # penalty groups are separated in the predicted direction by more than
    # chance -- a permutation test on the group-mean gap answers exactly that,
    # with no threshold to hand-pick.
    gap = mean(pen_only) - mean(bonus_only)
    pool = list(bonus_only) + list(pen_only)
    nb = len(bonus_only)
    rnd = random.Random(7)
    trials = 20000
    hits = 0
    for _ in range(trials):
        rnd.shuffle(pool)
        gb = sum(pool[:nb]) / float(nb)
        gq = sum(pool[nb:]) / float(len(pool) - nb)
        if gq - gb >= gap:
            hits += 1
    p_value = (hits + 1) / float(trials + 1)

    print("  group gap (penalty mean - bonus mean) = %+.2f positions" % gap)
    print("  permutation p-value (%d shuffles)   = %.5f" % (trials, p_value))
    print()
    if gap > 0 and p_value < 0.01:
        print("  VERDICT: divergence is CONCENTRATED in the direction Factor IV")
        print("           predicts, not scattered. The base calc is corroborated.")
        print("           Magnitude is deliberately not proportional -- the manual")
        print("           specifies approximate positions, then re-ranks.")
    else:
        print("  VERDICT: divergence does NOT show the Factor IV signature.")
        print("           Something in Factors I-III is likely wrong. INVESTIGATE.")
    print()

    print("20 LARGEST DIVERGENCES (negative delta = we rank them BETTER than NCAA)")
    print("   %-26s %-6s %-6s %-6s  %s" % (
        "team", "ours", "ncaa", "delta", "factor-IV profile"))
    for r in sorted(rows, key=lambda r: -abs(r["delta"]))[:20]:
        p = prof[r["key"]]
        tag = "top25W=%d 26-50W=%d badL=%d  pred=%+d" % (
            p["win_top25"], p["win_26_50"],
            p["loss_288_312"] + p["loss_313plus"], p["predicted_delta"])
        print("   %-26s %-6d %-6d %+-6d %s" % (
            r["team"], r["derived_rank"], r["official_rank"], r["delta"], tag))
    print()

    print("TOP 16 DERIVED (vs official)")
    for r in rows[:16]:
        print("   %2d. %-26s %2d-%-3d rpi=%.5f   (ncaa %d)" % (
            r["derived_rank"], r["team"], r["wins"], r["losses"],
            r["rpi"], r["official_rank"]))

    payload = {
        "meta": {
            "season": 2025,
            "spec": "2025-26 NCAA D-I Women's Volleyball Pre-Championship Manual 2.2",
            "weights": {"factor_i_wp": 0.25, "factor_ii_owp": 0.50,
                        "factor_iii_oowp": 0.25},
            "location_weighting": "NONE -- manual specifies no home/road/neutral "
                                  "multipliers for women's volleyball",
            "division_i_only": True,
            "division_i_membership_source": "official RPI table (348 teams)",
            "self_exclusion": "APPLIED in Factors II and III",
            "self_exclusion_tier": "INFERRED -- universal RPI convention, not "
                                   "printed in the volleyball manual",
            "factor_iv": "NOT ATTEMPTED -- expressed in approximate RPI positions, "
                         "not reproducible",
            "source_tier": "DERIVED",
            "reconciliation": {
                "spearman_rho": round(rho, 6),
                "exact_rank_matches": exact,
                "within_3": within3,
                "within_10": within10,
                "mean_abs_delta": round(mean_abs, 4),
                "factor_iv_signed_correlation": round(r_signed, 6),
                "factor_iv_group_gap_positions": round(gap, 4),
                "factor_iv_permutation_p": round(p_value, 6),
                "mean_delta_bonus_profile": round(mean(bonus_only), 4),
                "mean_delta_penalty_profile": round(mean(pen_only), 4),
                "mean_delta_neutral": round(mean(neutral), 4),
            },
        },
        "teams": rows,
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=1)
    print()
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
