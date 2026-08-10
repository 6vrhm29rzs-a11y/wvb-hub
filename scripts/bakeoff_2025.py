#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The metric bake-off: which team rating actually predicts 2025 outcomes?

PRE-REGISTERED CANDIDATES (Research/ "RPI Spec ...", section 5.4). Claude-app's
written expectation, recorded BEFORE this ran, is that hitting-efficiency
differential and net points/set lead among box-score-computable metrics. That
expectation is what makes this a test rather than a rationalization.

    hit_eff_diff     own hitting efficiency - opponent hitting efficiency allowed
    opp_hit_eff      opponent hitting efficiency allowed (negated: higher better)
    net_points_set   (points for - points against) / sets
    sideout_proxy    serve-receive success, 1 - receptionErrors/receptionAttempts

Plus the incumbent and a floor, without which "good" has no scale:

    rpi              Factors I-III, recomputed on the fit window
    own_hit_eff      own hitting efficiency alone
    win_pct          Division-I winning percentage

*** SIDEOUT IS A PROXY, NOT SIDEOUT%. *** True sideout% = points won while
receiving / opponent serve attempts, and it is NOT recoverable from box scores.
Verified directly rather than assumed: the rally identities P_us = S_us - Y + X
and P_opp = S_opp - X + Y give contradictory values for X on a real match
(X - Y = 1 from one, Y - X = 6 from the other), because serveAttempts and
receptionAttempts do not count aces and service errors alike. What is
implemented here is the SERVE-RECEIVE component only; the attack-after-reception
half -- which Palao (2018) identifies as the single most discriminating action
-- is unobservable without play-by-play. Tier: UNVERIFIED.

*** LEAKAGE CONTROL. *** Every metric is computed ONLY from games in the fit
window and tested on games outside it. Season-total leaderboards cannot support
this (they are cumulative through Dec 21, tournament included), which is why the
per-match boxscore crawl was necessary. Two independent tests:

  TEST A  fit = regular season (non-championship), test = the 65 championship
          games. This is the question actually asked -- does the metric predict
          TOURNAMENT outcomes -- but n is small.
  TEST B  fit = games before Nov 1, test = regular-season games from Nov 1 on.
          Same leakage discipline, ~20x the sample, so it is the one with power.

Scored by accuracy (sign of the metric difference) and AUC (threshold-free, so
no cutoff is hand-picked -- a lesson from the Factor IV diagnostic).

Python 3.9 target.
"""

import datetime
import json
import os
import sys
import collections
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "data", "raw", "2025")
OUT = os.path.join(REPO, "data", "bakeoff_2025.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm  # noqa: E402
from rpi_2025 import rpi_from_games  # noqa: E402


def to_i(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def load():
    """Returns (matches, di_keys). Each match carries both teams' box lines."""
    rpi_rows = json.load(open(os.path.join(RAW, "rpi_official.json")))["data"]
    di = {norm(r["School"]) for r in rpi_rows}

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

    matches = []
    seen = set()
    with open(os.path.join(RAW, "games.jsonl")) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                g = json.loads(line)
            except Exception:
                continue
            if g["game_id"] in seen or g.get("game_state") != "F":
                continue
            seen.add(g["game_id"])
            t = g.get("teams") or []
            if len(t) != 2:
                continue
            ka, kb = norm(t[0].get("name_short")), norm(t[1].get("name_short"))
            if ka not in di or kb not in di:
                continue
            if t[0].get("is_winner"):
                win, lose = 0, 1
            elif t[1].get("is_winner"):
                win, lose = 1, 0
            else:
                continue

            ep = g.get("start_time_epoch")
            date = (datetime.datetime.utcfromtimestamp(int(ep)).date()
                    if ep else None)

            # points for/against per team from linescores
            hp = ap = 0
            nsets = 0
            for ls in g.get("linescores") or []:
                h, v = to_i(ls.get("home")), to_i(ls.get("visit"))
                hp += h
                ap += v
                nsets += 1

            bx = box.get(g["game_id"])
            blines = {}
            if bx:
                for tb in bx.get("teams", []):
                    blines[str(tb.get("team_id"))] = tb.get("team_stats") or {}

            side = []
            for i, tt in enumerate(t):
                pf, pa = (hp, ap) if tt.get("is_home") else (ap, hp)
                side.append({
                    "key": norm(tt.get("name_short")),
                    "team_id": str(tt.get("team_id")),
                    "points_for": pf, "points_against": pa,
                    "sets": nsets,
                    "box": blines.get(str(tt.get("team_id"))),
                })

            matches.append({
                "game_id": g["game_id"],
                "date": date,
                "is_championship": bool(g.get("championship")),
                "teams": side,
                "winner_idx": win,
            })
    return matches, di


def build_metrics(fit_matches, di):
    # type: (List[dict], set) -> Dict[str, Dict[str, float]]
    """Aggregate every candidate over the fit window. Returns metric -> key -> value."""
    agg = collections.defaultdict(lambda: {
        "k": 0, "e": 0, "ta": 0, "ok": 0, "oe": 0, "ota": 0,
        "pf": 0, "pa": 0, "sets": 0, "rec_err": 0, "rec_att": 0,
        "w": 0, "l": 0, "box_games": 0,
    })
    games_for_rpi = []
    for m in fit_matches:
        a, b = m["teams"]
        wk = m["teams"][m["winner_idx"]]["key"]
        lk = m["teams"][1 - m["winner_idx"]]["key"]
        games_for_rpi.append((wk, lk, m["game_id"]))
        agg[wk]["w"] += 1
        agg[lk]["l"] += 1
        for me, opp in ((a, b), (b, a)):
            e = agg[me["key"]]
            e["pf"] += me["points_for"]
            e["pa"] += me["points_against"]
            e["sets"] += me["sets"]
            if me["box"] and opp["box"]:
                e["box_games"] += 1
                e["k"] += to_i(me["box"].get("kills"))
                e["e"] += to_i(me["box"].get("attackErrors"))
                e["ta"] += to_i(me["box"].get("attackAttempts"))
                e["ok"] += to_i(opp["box"].get("kills"))
                e["oe"] += to_i(opp["box"].get("attackErrors"))
                e["ota"] += to_i(opp["box"].get("attackAttempts"))
                e["rec_err"] += to_i(me["box"].get("receptionErrors"))
                e["rec_att"] += to_i(me["box"].get("receptionAttempts"))

    keys = sorted(di)
    rpi = rpi_from_games(games_for_rpi, keys)

    M = collections.defaultdict(dict)
    for k in keys:
        e = agg[k]
        own = ((e["k"] - e["e"]) / float(e["ta"])) if e["ta"] else None
        opp = ((e["ok"] - e["oe"]) / float(e["ota"])) if e["ota"] else None
        M["own_hit_eff"][k] = own
        M["opp_hit_eff"][k] = (-opp) if opp is not None else None
        M["hit_eff_diff"][k] = (own - opp) if (own is not None and opp is not None) else None
        M["net_points_set"][k] = ((e["pf"] - e["pa"]) / float(e["sets"])) if e["sets"] else None
        M["sideout_proxy"][k] = (1.0 - e["rec_err"] / float(e["rec_att"])) if e["rec_att"] else None
        n = e["w"] + e["l"]
        M["win_pct"][k] = (e["w"] / float(n)) if n else None
        M["rpi"][k] = rpi[k]["rpi"]
    return M


def auc(pairs):
    # type: (List[Tuple[float, int]]) -> Optional[float]
    """Rank-based AUC. pairs = (score, label). Threshold-free by construction."""
    pos = [s for s, y in pairs if y == 1]
    neg = [s for s, y in pairs if y == 0]
    if not pos or not neg:
        return None
    allv = sorted(s for s, _ in pairs)
    ranks = {}
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1] == allv[i]:
            j += 1
        r = (i + j) / 2.0 + 1
        ranks[allv[i]] = r
        i = j + 1
    rsum = sum(ranks[s] for s in pos)
    n1, n0 = len(pos), len(neg)
    return (rsum - n1 * (n1 + 1) / 2.0) / float(n1 * n0)


def evaluate(M, test_matches, name):
    print("=" * 72)
    print(name)
    print("=" * 72)
    order = ["hit_eff_diff", "net_points_set", "opp_hit_eff", "own_hit_eff",
             "sideout_proxy", "rpi", "win_pct"]
    results = {}
    for metric in order:
        table = M[metric]
        pairs = []
        correct = ties = skipped = 0
        for m in test_matches:
            a, b = m["teams"]
            va, vb = table.get(a["key"]), table.get(b["key"])
            if va is None or vb is None:
                skipped += 1
                continue
            # orient so the FIRST listed team is the label subject
            label = 1 if m["winner_idx"] == 0 else 0
            pairs.append((va - vb, label))
            if va == vb:
                ties += 1
            elif (va > vb) == (label == 1):
                correct += 1
        n = len(pairs)
        acc = (correct / float(n)) if n else 0.0
        a_ = auc(pairs)
        results[metric] = {"n": n, "accuracy": acc, "auc": a_, "skipped": skipped}
        print("  %-16s n=%-5d acc=%.4f  auc=%s%s" % (
            metric, n, acc,
            ("%.4f" % a_) if a_ is not None else " n/a ",
            ("   (%d skipped, no data)" % skipped) if skipped else ""))
    print()
    ranked = sorted([r for r in results.items() if r[1]["auc"] is not None],
                    key=lambda kv: -kv[1]["auc"])
    print("  RANKED BY AUC: %s" % ", ".join(
        "%s %.4f" % (k, v["auc"]) for k, v in ranked))
    print()
    return results


def main():
    matches, di = load()
    with_box = sum(1 for m in matches
                   if m["teams"][0]["box"] and m["teams"][1]["box"])
    champ = [m for m in matches if m["is_championship"]]
    reg = [m for m in matches if not m["is_championship"]]
    print("D-I matches: %d  (championship %d, regular %d)" % (
        len(matches), len(champ), len(reg)))
    print("matches with both box lines: %d (%.1f%%)" % (
        with_box, 100.0 * with_box / max(len(matches), 1)))
    print()

    # TEST A -- fit on regular season, predict the tournament
    Ma = build_metrics(reg, di)
    res_a = evaluate(Ma, champ,
                     "TEST A  fit = regular season -> test = 65 championship games")

    # TEST B -- temporal holdout inside the regular season (higher power)
    cut = datetime.date(2025, 11, 1)
    fit_b = [m for m in reg if m["date"] and m["date"] < cut]
    test_b = [m for m in reg if m["date"] and m["date"] >= cut]
    Mb = build_metrics(fit_b, di)
    res_b = evaluate(Mb, test_b,
                     "TEST B  fit = before Nov 1 (%d) -> test = Nov 1 onward (%d)"
                     % (len(fit_b), len(test_b)))

    payload = {
        "meta": {
            "season": 2025,
            "source_tier": "DERIVED",
            "pre_registered_expectation": "hitting-efficiency differential and "
                                          "net points/set lead among box-score "
                                          "computable metrics (Claude-app)",
            "leakage_control": "metrics fit only on the fit window; test games "
                               "excluded from every aggregate",
            "sideout_caveat": "sideout_proxy is the SERVE-RECEIVE component only "
                              "(1 - receptionErrors/receptionAttempts). True "
                              "sideout%% is not recoverable from box scores.",
            "scoring": "accuracy (sign) and AUC (rank-based, threshold-free)",
            "matches_di": len(matches),
            "matches_with_boxscores": with_box,
        },
        "test_a_tournament": res_a,
        "test_b_temporal_holdout": res_b,
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
