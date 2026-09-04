#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the prediction scorer.

This file exists because the scorer is the component that judges everything
else. A rating that is wrong shows up as a bad Brier score; a SCORER that is
wrong shows up as nothing at all, and quietly certifies whatever it is fed.

Three failures it is built to prevent:

  1. SCORING A PREDICTION MADE AFTER THE MATCH. Trivially produces a brilliant
     Brier score and means nothing. The log records when each prediction was
     written and the scorer refuses anything stamped after tip-off.

  2. SCORING THE WRONG MATCH. Game ids are reused across seasons and feeds; a
     prediction and a result sharing an id but not the same two teams is a
     collision, not a forecast.

  3. SILENTLY REWRITING HISTORY. The log is first-write-wins. If a later run
     could overwrite an earlier prediction, every score becomes a fit.

Python 3.9 target. Run: python3 scripts/test_score_predictions.py
"""

import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %-58s %s" % (name, "ok" if ok else "FAIL (got %r, want %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


def approx(name, got, want, tol=1e-6):
    ok = got is not None and abs(got - want) < tol
    print("  %-58s %s" % (name, "ok" if ok else "FAIL (got %r, want %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


def run(preds, games):
    """Score a synthetic log against synthetic results."""
    tmp = tempfile.mkdtemp(prefix="wvb-score-")
    try:
        raw = os.path.join(tmp, "data", "raw", "2026")
        os.makedirs(raw)
        with open(os.path.join(raw, "prediction_log.jsonl"), "w") as fh:
            for p in preds:
                fh.write(json.dumps(p) + "\n")
        with open(os.path.join(raw, "games.jsonl"), "w") as fh:
            for g in games:
                fh.write(json.dumps(g) + "\n")
        import score_predictions as SP
        prev = (SP.LOG, SP.GAMES, SP.OUT)
        SP.LOG = os.path.join(raw, "prediction_log.jsonl")
        SP.GAMES = os.path.join(raw, "games.jsonl")
        SP.OUT = os.path.join(tmp, "out.json")
        try:
            return SP.build()
        finally:
            SP.LOG, SP.GAMES, SP.OUT = prev
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pred(gid, home, away, p, logged="2026-08-20T00:00:00Z"):
    return {"game_id": gid, "date": "2026-08-21", "home": home, "away": away,
            "home_win": p, "neutral": False, "played_2026": {"home": 0, "away": 0},
            "logged_utc": logged}


def game(gid, home, away, home_won, epoch=1787335200):   # 2026-08-21 18:00Z
    # A fixture must look like a REAL final: the loader now runs the one
    # counting classification (season_counts), and a final with no sets and
    # no lines is the EMPTY class -- it counts nowhere, fixtures included.
    return {"game_id": gid, "game_state": "F", "start_time_epoch": epoch,
            "teams": [{"team_id": "1", "name_short": home, "is_home": True,
                       "is_winner": home_won,
                       "sets_won": 3 if home_won else 1},
                      {"team_id": "2", "name_short": away, "is_home": False,
                       "is_winner": not home_won,
                       "sets_won": 1 if home_won else 3}]}


def main():
    print("PREDICTION SCORER GUARDS\n")

    print("1. Brier score is computed correctly")
    out = run([pred("g1", "A", "B", 0.8), pred("g2", "C", "D", 0.5)],
              [game("g1", "A", "B", True), game("g2", "C", "D", False)])
    # (0.8-1)^2 = 0.04 ; (0.5-0)^2 = 0.25 ; mean = 0.145
    check("both matches scored", out["meta"]["scored"], 2)
    approx("Brier is the mean squared error", out["meta"]["brier"], 0.145, 1e-4)

    print("\n2. A prediction logged AFTER tip-off is refused")
    out = run([pred("g1", "A", "B", 0.99, logged="2026-12-31T00:00:00Z")],
              [game("g1", "A", "B", True, epoch=1787335200)])
    check("not scored", out["meta"]["scored"], 0)
    check("counted as excluded", out["meta"]["logged_after_tipoff_excluded"], 1)

    print("\n3. A prediction about different teams is refused")
    out = run([pred("g1", "A", "B", 0.9)], [game("g1", "X", "Y", True)])
    check("not scored", out["meta"]["scored"], 0)
    check("counted as a mismatch", out["meta"]["team_mismatch_excluded"], 1)

    print("\n4. The log is first-write-wins")
    # the same fixture predicted twice; only the FIRST may count
    out = run([pred("g1", "A", "B", 0.60), pred("g1", "A", "B", 0.99)],
              [game("g1", "A", "B", True)])
    check("scored once, not twice", out["meta"]["scored"], 1)
    approx("the FIRST prediction is the one scored",
           out["meta"]["brier"], (0.60 - 1.0) ** 2, 1e-6)

    print("\n5. Calibration buckets read from the favourite's side")
    # four matches called 80%, three of which the favourite won
    preds, games = [], []
    for i, won in enumerate([True, True, True, False]):
        preds.append(pred("h%d" % i, "H%d" % i, "A%d" % i, 0.8))
        games.append(game("h%d" % i, "H%d" % i, "A%d" % i, won))
    # and one where the AWAY team is the favourite, and wins
    preds.append(pred("z", "HZ", "AZ", 0.2))
    games.append(game("z", "HZ", "AZ", False))
    out = run(preds, games)
    b = {x["range"]: x for x in out["calibration"]}
    check("the 80-90% band exists", "80-90%" in b, True)
    if "80-90%" in b:
        check("it holds all five (the away favourite counts too)", b["80-90%"]["n"], 5)
        check("we said 80%", b["80-90%"]["said"], 80.0)
        check("it happened 80% of the time", b["80-90%"]["happened"], 80.0)

    print("\n6. An unplayed fixture is simply not scored")
    out = run([pred("g1", "A", "B", 0.7)], [])
    check("nothing scored", out["meta"]["scored"], 0)
    check("but the prediction is still on record",
          out["meta"]["predictions_on_record"], 1)

    print()
    if FAILED:
        print("FAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - %s" % f)
        return 1
    print("ALL PREDICTION SCORER GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
