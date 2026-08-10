#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STAGE B: play the bracket out. Rally-level match model, Ferrante-Fonseca.

Stage A predicts COMMITTEE BEHAVIOUR (who is selected and seeded) and must not
use the strength composite. Stage B predicts MATCHES, which is exactly what the
composite is for and what it beat RPI at out-of-sample.

THE MODEL. One per-rally win probability p per matchup, from which set-win and
match-win probabilities are derived ANALYTICALLY (Ferrante & Fonseca, JQAS 2014)
rather than by coin-flipping the match. That yields the 3-0/3-1/3-2 distribution
instead of a binary, and it handles 25-point sets, win-by-2, and the 15-point
fifth set correctly.

*** ONE POOLED RALLY PARAMETER. NO SET-INDEXED STRENGTHS. ***
Sets 4 and 5 exist only in matches that were already close, so estimating
per-set team strength would be fitting a biased sample by construction -- a
strong team's fourth sets are drawn from its hardest matches. A single pooled p
sidesteps that: set-4 and set-5 behaviour is DERIVED from p, never estimated.

CALIBRATION IS THE HEADLINE, not accuracy. On 63 tournament matches accuracy is
noise; calibration answers whether the probabilities mean anything.

Everything feeding this is measured on this population, not borrowed:
  rallies/set      43.44  (2025, 18,981 sets)
  home advantage   from our own ridge fit, NOT the literature's ~58-60%
  team strength    opponent-adjusted net points/set

Python 3.9 target.
"""

import collections
import datetime
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(REPO, "data", "simulation_%d.json" % SEASON)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm  # noqa: E402
from gamelog import load_games_jsonl  # noqa: E402
import bakeoff_2025 as B  # noqa: E402

RALLIES_PER_SET = 43.44     # measured, 2025
PRIMARY = "adj_net_points_set"


# ----------------------------------------------------- rally -> set -> match

def set_win_prob(p, target):
    # type: (float, int) -> float
    """P(win a race to `target`, win by 2) given per-rally probability p.

    Exact, not simulated. At (target-1, target-1) the deuce continuation has
    closed form W = p^2 / (1 - 2pq): win two straight, or split and repeat.
    """
    q = 1.0 - p
    deuce = (p * p) / (1.0 - 2.0 * p * q) if (1.0 - 2.0 * p * q) > 0 else 0.5
    memo = {}

    def f(a, b):
        if a == target - 1 and b == target - 1:
            return deuce
        if a >= target and b <= target - 2:
            return 1.0
        if b >= target and a <= target - 2:
            return 0.0
        key = (a, b)
        if key in memo:
            return memo[key]
        v = p * f(a + 1, b) + q * f(a, b + 1)
        memo[key] = v
        return v

    return f(0, 0)


def match_dist(p):
    # type: (float) -> Dict[str, float]
    """Best-of-5 outcome distribution from ONE pooled per-rally probability.

    Sets 1-4 race to 25, set 5 to 15. Set-4 and set-5 behaviour is derived
    here, never estimated from set-indexed data.
    """
    s = set_win_prob(p, 25)
    s5 = set_win_prob(p, 15)
    t = 1.0 - s
    w30 = s ** 3
    w31 = 3 * (s ** 3) * t
    w32 = 6 * (s ** 2) * (t ** 2) * s5
    l30 = t ** 3
    l31 = 3 * (t ** 3) * s
    l32 = 6 * (t ** 2) * (s ** 2) * (1.0 - s5)
    return {"w30": w30, "w31": w31, "w32": w32,
            "l30": l30, "l31": l31, "l32": l32,
            "win": w30 + w31 + w32}


def rally_p(margin_per_set):
    # type: (float) -> float
    """Map an expected per-set point margin to a per-rally win probability.

    If a team wins fraction p of rallies, its expected margin over a set of R
    rallies is (2p-1)*R, so p = 0.5 + margin/(2R). R is measured, not assumed.
    """
    p = 0.5 + margin_per_set / (2.0 * RALLIES_PER_SET)
    return min(0.90, max(0.10, p))


# ------------------------------------------------------------------- loading

def load_strength(cutoff=None):
    """Opponent-adjusted net points/set, plus the fitted home advantage."""
    matches, di = B.load()
    fit = [m for m in matches
           if cutoff is None or (m["date"] and m["date"] < cutoff)]
    M = B.build_metrics(fit, di)
    return M[PRIMARY], M.get("_home_adv_points_per_set", 0.0), matches, di


def reconstruct_bracket(di):
    """Rebuild the real 2025 tournament tree from the championship games."""
    games = []
    for g in load_games_jsonl(os.path.join(RAW, "games.jsonl")):
        if not g.get("championship") or g.get("game_state") != "F":
            continue
        t = g.get("teams") or []
        if len(t) != 2:
            continue
        ks = [norm(x.get("name_short")) for x in t]
        if not all(k in di for k in ks):
            continue          # the championship flag also carries non-D-I events
        ep = g.get("start_time_epoch")
        d = datetime.datetime.utcfromtimestamp(int(ep)).date() if ep else None
        w = ks[0] if t[0].get("is_winner") else ks[1]
        games.append({"date": d, "teams": ks, "winner": w,
                      "home": ks[0] if t[0].get("is_home") else ks[1]})
    # ROUND ASSIGNMENT BY TEAM APPEARANCE, not by date-slicing.
    # Rounds 1 and 2 are played on the SAME weekend, so "the first 32 games by
    # date" interleaves them -- Nebraska vs LIU, a first-round match, landed in
    # round 2 and eight nodes then failed to resolve their feeders. Each team
    # plays exactly one game per round, so a team's k-th championship game IS
    # round k. That is structural and cannot be confused by scheduling.
    games.sort(key=lambda x: (x["date"] or datetime.date(1900, 1, 1)))
    played = collections.Counter()
    by_round = collections.defaultdict(list)
    for g in games:
        r = max(played[k] for k in g["teams"])
        by_round[r].append(g)
        for k in g["teams"]:
            played[k] += 1
    return [by_round[i] for i in sorted(by_round)]


# ---------------------------------------------------------------- evaluation

def main():
    strength, home_half, matches, di = load_strength()
    print("=" * 76)
    print("STAGE B -- RALLY-LEVEL MATCH MODEL (Ferrante-Fonseca)")
    print("=" * 76)
    print("  rallies/set (measured)  : %.2f" % RALLIES_PER_SET)
    print("  home advantage (fitted) : %+.3f pts/set half-effect "
          "(%.2f full gap) -- our own data, not the literature"
          % (home_half, 2 * home_half))
    print()

    def predict(a, b, home=None):
        """Outcome distribution for team a vs team b."""
        sa, sb = strength.get(a), strength.get(b)
        if sa is None or sb is None:
            return None
        m = sa - sb
        if home == a:
            m += 2 * home_half
        elif home == b:
            m -= 2 * home_half
        return match_dist(rally_p(m))

    # ---- 1. SERIES LENGTH: the free reconciliation target ----
    obs = collections.Counter()
    exp = collections.Counter()
    n = 0
    for mt in matches:
        a, b = mt["teams"]
        d = predict(a["key"], b["key"], home=a["key"] if a["is_home"] else b["key"])
        if d is None:
            continue
        wa, la = a["sets_won"] if "sets_won" in a else None, None
        n += 1
        exp["3-0"] += d["w30"] + d["l30"]
        exp["3-1"] += d["w31"] + d["l31"]
        exp["3-2"] += d["w32"] + d["l32"]
    for g in load_games_jsonl(os.path.join(RAW, "games.jsonl")):
        if g.get("game_state") != "F":
            continue
        t = g.get("teams") or []
        if len(t) != 2 or not all(norm(x.get("name_short")) in di for x in t):
            continue
        try:
            s = sorted(int(x.get("sets_won")) for x in t)
        except (TypeError, ValueError):
            continue
        if s[1] == 3:
            obs["3-%d" % s[0]] += 1
    tot_o = sum(obs.values()) or 1
    print("  SERIES LENGTH -- predicted vs observed (%d matches)" % n)
    print("    %-6s %-12s %-12s %s" % ("", "predicted", "observed", "diff"))
    for k in ("3-0", "3-1", "3-2"):
        pe, po = exp[k] / max(n, 1), obs[k] / float(tot_o)
        print("    %-6s %-12.4f %-12.4f %+.4f" % (k, pe, po, pe - po))
    print()

    # ---- 2. CALIBRATION: the headline ----
    def calib(subset, label):
        buckets = collections.defaultdict(lambda: [0, 0])   # [n, wins]
        preds = []
        for mt in subset:
            a, b = mt["teams"]
            d = predict(a["key"], b["key"],
                        home=a["key"] if a["is_home"] else b["key"])
            if d is None:
                continue
            pw = d["win"]
            won = 1 if mt["winner_idx"] == 0 else 0
            # orient to the FAVOURITE so buckets are >= 0.5
            if pw < 0.5:
                pw, won = 1.0 - pw, 1 - won
            preds.append((pw, won))
            lo = min(int(pw * 10) * 10, 90)
            buckets[lo][0] += 1
            buckets[lo][1] += won
        if not preds:
            return None
        brier = sum((p - w) ** 2 for p, w in preds) / len(preds)
        acc = sum(1 for p, w in preds if w == 1) / float(len(preds))
        print("  CALIBRATION -- %s (n=%d)" % (label, len(preds)))
        print("    %-14s %-7s %-11s %-11s %s" % (
            "predicted", "n", "predicted", "actual", "gap"))
        for lo in sorted(buckets):
            cnt, wins = buckets[lo]
            mean_p = sum(p for p, _ in preds if min(int(p * 10) * 10, 90) == lo) / cnt
            actual = wins / float(cnt)
            print("    %-14s %-7d %-11.3f %-11.3f %+.3f" % (
                "%d-%d%%" % (lo, lo + 10), cnt, mean_p, actual, mean_p - actual))
        print("    favourite win rate %.4f   Brier %.4f "
              "(0.25 = coin flip, lower is better)" % (acc, brier))
        print()
        return {"n": len(preds), "brier": brier, "favourite_accuracy": acc,
                "buckets": {str(k): {"n": v[0], "wins": v[1]}
                            for k, v in buckets.items()}}

    champ_matches = [m for m in matches if m["is_championship"]]
    reg = [m for m in matches if not m["is_championship"]]
    cal_all = calib(reg, "all regular-season D-I matches")
    cal_t = calib(champ_matches, "the 2025 tournament")

    # ---- 3. RUN THE REAL BRACKET ----
    rounds = reconstruct_bracket(di)
    print("  BRACKET reconstructed from actual games: %s"
          % " -> ".join(str(len(r)) for r in rounds))
    # Build the actual bracket TREE. A realized game list is only the path that
    # happened; to ask "how likely was each team to win the title" the model has
    # to know who WOULD have met whom. Each round-N game is fed by the two
    # round-(N-1) games its participants won, which reconstructs the tree
    # exactly. (An earlier version propagated along the realized path instead,
    # which left eliminated teams holding their first-round win probability --
    # Tennessee "0.84 to win the title" was really P(win its opener), and the
    # numbers did not sum to 1.)
    winner_of = {}
    for ri, rnd in enumerate(rounds):
        for gi, g in enumerate(rnd):
            winner_of[g["winner"]] = (ri, gi)

    feeders = {}
    for ri in range(1, len(rounds)):
        for gi, g in enumerate(rounds[ri]):
            f = []
            for k in g["teams"]:
                src = winner_of.get(k)
                # the feeder is the game this team won in the PREVIOUS round
                for pri in range(ri - 1, -1, -1):
                    hit = [j for j, pg in enumerate(rounds[pri])
                           if pg["winner"] == k]
                    if hit:
                        f.append((pri, hit[0]))
                        break
            feeders[(ri, gi)] = f

    def occupants(node):
        """team -> probability that team occupies this game slot."""
        ri, gi = node
        g = rounds[ri][gi]
        if ri == 0:
            return {g["teams"][0]: 1.0, g["teams"][1]: 1.0}, g
        f = feeders.get(node, [])
        if len(f) != 2:
            return {k: 1.0 for k in g["teams"]}, g
        dists = []
        for fn in f:
            sub, subg = occupants(fn)
            dists.append(winners_of_node(fn, sub, subg))
        return dists, g

    memo = {}

    def node_winner_dist(node):
        """team -> probability that team WINS this game."""
        if node in memo:
            return memo[node]
        ri, gi = node
        g = rounds[ri][gi]
        if ri == 0:
            a, b = g["teams"]
            d = predict(a, b, home=g.get("home"))
            pa = 0.5 if d is None else d["win"]
            out = {a: pa, b: 1.0 - pa}
        else:
            f = feeders.get(node, [])
            if len(f) != 2:
                a, b = g["teams"]
                d = predict(a, b, home=g.get("home"))
                pa = 0.5 if d is None else d["win"]
                out = {a: pa, b: 1.0 - pa}
            else:
                left = node_winner_dist(f[0])
                right = node_winner_dist(f[1])
                out = collections.defaultdict(float)
                for a, pa in left.items():
                    for b, pb in right.items():
                        d = predict(a, b)
                        pw = 0.5 if d is None else d["win"]
                        out[a] += pa * pb * pw
                        out[b] += pa * pb * (1.0 - pw)
                out = dict(out)
        memo[node] = out
        return out

    final_node = (len(rounds) - 1, 0)
    alive = node_winner_dist(final_node)
    title = sorted(alive.items(), key=lambda kv: -kv[1])
    print("  (title probabilities sum to %.4f -- must be 1.0)"
          % sum(v for _, v in title))
    print()
    print("  TITLE PROBABILITY through the ACTUAL bracket (top 10)")
    for k, v in title[:10]:
        print("    %-26s %.4f" % (k, v))
    champ = rounds[-1][0]["winner"] if rounds else None
    p_champ = dict(title).get(champ)
    print()
    print("  *** ACTUAL 2025 CHAMPION: %s -- model gave it %.4f (%.1f%%) ***"
          % (champ, p_champ or 0.0, 100.0 * (p_champ or 0.0)))
    rank = [k for k, _ in title].index(champ) + 1 if champ in dict(title) else None
    print("      that was the %s-most likely champion of %d" % (rank, len(title)))
    print()

    payload = {
        "meta": {
            "season": SEASON, "source_tier": "DERIVED",
            "stage": "B -- match simulation (strength, not resume)",
            "model": "Ferrante-Fonseca; one pooled per-rally probability, "
                     "set-4/5 behaviour derived not estimated",
            "rallies_per_set": RALLIES_PER_SET,
            "home_advantage_half_points_per_set": home_half,
            "series_length": {k: {"predicted": exp[k] / max(n, 1),
                                  "observed": obs[k] / float(tot_o)}
                              for k in ("3-0", "3-1", "3-2")},
            "calibration_regular_season": cal_all,
            "calibration_tournament": cal_t,
            "actual_champion": champ,
            "model_probability_for_actual_champion": p_champ,
        },
        "title_probabilities": [{"team": k, "p": v} for k, v in title],
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
