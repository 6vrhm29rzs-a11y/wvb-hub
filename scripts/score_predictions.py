#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score the model against what actually happened.

If this project is going to put percentages on screen, something has to check
them. This compares each match's PRE-MATCH prediction -- the one recorded in
data/raw/2026/prediction_log.jsonl before it was played -- against the result,
and reports the two things that matter:

  BRIER SCORE. Mean squared error of the probability. 0.25 is what you get by
  saying 50% to everything, so anything at or above that is worthless. The 2025
  backtest of this same model scored 0.1289.

  CALIBRATION. Of the matches we called 70%, did about 70% happen? A model can
  have a good Brier score and still be systematically overconfident, and
  calibration is the part that tells you whether a number means what it says.

WHY THE LOG EXISTS AND WHY IT IS NEVER REWRITTEN. predictions_2026.json holds
only FUTURE fixtures -- a match drops out of it the moment it is played. Scoring
against that file would mean re-deriving a "prediction" from data that already
contains the outcome, which is a fit wearing a forecast's clothes. The log is
first-write-wins and permanent.

INTEGRITY CHECK. Each logged prediction carries the time it was written, and
this refuses to score any prediction recorded after its match started. That
cannot happen by design, and checking is cheap.

Python 3.9 target. Writes data/prediction_score_2026.json.
"""

import json
import os
import sys
import datetime
import collections
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_counts as _SC  # noqa: E402
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
LOG = os.path.join(REPO, "data", "raw", str(SEASON), "prediction_log.jsonl")
GAMES = os.path.join(REPO, "data", "raw", str(SEASON), "games.jsonl")
OUT = os.path.join(REPO, "data", "prediction_score_%d.json" % SEASON)

BUCKETS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


def load_predictions() -> Dict[str, Dict]:
    out = {}
    if not os.path.exists(LOG):
        return out
    for line in open(LOG):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not isinstance(r, dict) or "game_id" not in r:
            continue
        out.setdefault(str(r["game_id"]), r)     # first write wins
    return out


def load_results() -> Dict[str, Dict]:
    # ⚠ 2026-09-03: this loader read the RAW log -- no duplicate/exhibition/
    # review exclusion, no result corrections -- so the Brier was scored
    # against the feed's uncorrected winner for every ledgered inversion.
    # One counting classification (season_counts), same as everything counted.
    out = {}
    if not os.path.exists(GAMES):
        return out
    games = []
    for line in open(GAMES):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if isinstance(g, dict):
            games.append(g)
    cls = _SC.classify(games, SEASON)
    corr = _SC.corrections(SEASON)
    for g in _SC.resolve(games):
        if g.get("game_state") != "F":
            continue
        if cls.get(str(g.get("game_id"))) != "ok":
            continue
        g = _SC.apply_correction(g, corr)
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        home = next((t for t in ts if t.get("is_home")), None)
        away = next((t for t in ts if not t.get("is_home")), None)
        if not home or not away:
            continue
        wi = _SC.winner_index(g)   # sets decide when is_winner is
        if wi is None:             # absent/incoherent (6628428) -- and a
            continue               # final asserting no result scores nothing
        out[str(g.get("game_id"))] = {
            "home": home.get("name_short"), "away": away.get("name_short"),
            "home_won": ts[wi] is home,
            "epoch": g.get("start_time_epoch"),
        }
    return out


def build():
    preds = load_predictions()
    results = load_results()

    scored, late, mismatched = [], 0, 0
    for gid, p in preds.items():
        r = results.get(gid)
        if not r:
            continue
        # the prediction must predate the match
        if r.get("epoch") and p.get("logged_utc"):
            try:
                logged = datetime.datetime.strptime(
                    p["logged_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc).timestamp()
                if logged > float(r["epoch"]):
                    late += 1
                    continue
            except ValueError:
                pass
        # and it must be about the same match
        if p.get("home") != r.get("home") or p.get("away") != r.get("away"):
            mismatched += 1
            continue
        scored.append({
            "game_id": gid, "date": p.get("date"),
            "away": r["away"], "home": r["home"],
            "p_home": p["home_win"], "home_won": r["home_won"],
            "brier": (p["home_win"] - (1.0 if r["home_won"] else 0.0)) ** 2,
        })

    n = len(scored)
    brier = sum(s["brier"] for s in scored) / n if n else None
    hits = sum(1 for s in scored
               if (s["p_home"] >= 0.5) == s["home_won"]) if n else 0

    # calibration: bucket by the FAVOURITE's probability
    buckets = []
    for lo, hi in BUCKETS:
        rows = []
        for s in scored:
            fav_p = max(s["p_home"], 1.0 - s["p_home"])
            fav_won = s["home_won"] if s["p_home"] >= 0.5 else (not s["home_won"])
            if lo <= fav_p < hi:
                rows.append((fav_p, fav_won))
        if rows:
            buckets.append({
                "range": "%d-%d%%" % (100 * lo, 100 * hi),
                "n": len(rows),
                "said": round(100 * sum(x for x, _ in rows) / len(rows), 1),
                "happened": round(100 * sum(1 for _, w in rows if w) / len(rows), 1),
            })

    return {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "scored": n,
            "logged_after_tipoff_excluded": late,
            "team_mismatch_excluded": mismatched,
            "predictions_on_record": len(preds),
            "results_available": len(results),
            "brier": round(brier, 4) if brier is not None else None,
            "brier_reference": ("0.25 is what saying 50%% to everything scores; "
                                "this model backtested at 0.1289 on 2025"),
            "favourite_correct": hits,
            "favourite_correct_pct": round(100.0 * hits / n, 1) if n else None,
        },
        "calibration": buckets,
        "matches": sorted(scored, key=lambda s: -s["brier"])[:50],
    }


if __name__ == "__main__":
    out = build()
    json.dump(out, open(OUT, "w"), indent=1)
    m = out["meta"]
    print("wrote %s" % OUT)
    print("  predictions on record : %d" % m["predictions_on_record"])
    print("  results available     : %d" % m["results_available"])
    print("  scored                : %d" % m["scored"])
    if m["logged_after_tipoff_excluded"]:
        print("  EXCLUDED, logged after the match started: %d"
              % m["logged_after_tipoff_excluded"])
    if not m["scored"]:
        print("\n  Nothing to score yet. Every fixture on record is still to be "
              "played, which is exactly what you want at this point -- the log "
              "has to be written before the matches, not after.")
        sys.exit(0)
    print("\n  Brier score      : %.4f   (0.25 = coin flip, 0.1289 = 2025 backtest)"
          % m["brier"])
    print("  favourite won    : %d of %d (%.1f%%)"
          % (m["favourite_correct"], m["scored"], m["favourite_correct_pct"]))
    if out["calibration"]:
        print("\n  CALIBRATION -- what we said vs what happened")
        print("    %-9s %5s %8s %10s" % ("band", "n", "said", "happened"))
        for b in out["calibration"]:
            print("    %-9s %5d %7.1f%% %9.1f%%"
                  % (b["range"], b["n"], b["said"], b["happened"]))
