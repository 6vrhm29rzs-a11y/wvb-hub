#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the factor bake-off. The measurement has to be trustworthy first.

This file exists because rating_factors.py is used to SETTLE ARGUMENTS -- it is
the thing that says "no, weighting recent matches more does not help". A
measurement used that way has to be checked harder than the thing it measures,
and two of its pieces were wrong before these guards were written:

  1. The AUC keyed its tie-ranks on id(). The bootstrap resamples WITH
     REPLACEMENT, so the same tuple object appears many times -- one id, one
     rank, every duplicate silently collapsed onto the first. The plain numbers
     were fine and the confidence intervals, the entire reason the bootstrap
     exists, were computed on a quietly wrong statistic.

  2. fit_off_def() gained a weights argument. If w=None ever stopped being
     exactly the old arithmetic, every rating this project has ever published
     would move and nothing would say so.

Python 3.9 target. Run: python3 scripts/test_rating_factors.py
"""

import json
import math
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakeoff_2025 as B        # noqa: E402
import rating_factors as RF     # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    print("RATING-FACTOR GUARDS\n")

    print("1. AUC -- positive and negative controls")
    perfect = [(i, 1 if i >= 50 else 0) for i in range(100)]
    check("a perfect separator scores 1.0", abs(RF.auc(perfect) - 1.0) < 1e-9,
          "(%.4f)" % RF.auc(perfect))
    check("its reverse scores 0.0",
          abs(RF.auc([(-s, y) for s, y in perfect])) < 1e-9)
    check("all-tied scores exactly 0.5",
          abs(RF.auc([(1.0, i % 2) for i in range(100)]) - 0.5) < 1e-9)
    rng = random.Random(1)
    r = RF.auc([(rng.random(), rng.randint(0, 1)) for _ in range(8000)])
    check("random scores about 0.5", abs(r - 0.5) < 0.03, "(%.4f)" % r)

    # ⚠ THE BUG THAT WAS ACTUALLY THERE. Duplicated rows are what a bootstrap
    # resample looks like; an id()-keyed rank table gets them wrong.
    check("duplicated rows do not change the AUC (the bootstrap case)",
          abs(RF.auc(perfect * 3) - 1.0) < 1e-9, "(%.4f)" % RF.auc(perfect * 3))
    check("an empty class returns nan rather than a number",
          math.isnan(RF.auc([(1.0, 1), (2.0, 1)])))

    print("\n2. The weighted ridge reduces EXACTLY to the unweighted one")
    rng = random.Random(7)
    keys = ["t%02d" % i for i in range(40)]
    obs = []
    for _ in range(600):
        a, b = rng.sample(keys, 2)
        obs.append((a, b, rng.gauss(0, 4), rng.choice([-1, 0, 1])))
    r0 = B.fit_off_def(obs, keys)
    r1 = B.fit_off_def(obs, keys, [1.0] * len(obs))
    dmax = max(max(abs(r0[k]["off"] - r1[k]["off"]),
                   abs(r0[k]["def"] - r1[k]["def"])) for k in keys)
    check("w=None and w=all-ones are bit-identical", dmax == 0.0, "(%.3e)" % dmax)
    check("mu and the home term are identical too",
          r0[keys[0]]["_mu"] == r1[keys[0]]["_mu"]
          and r0[keys[0]]["_h"] == r1[keys[0]]["_h"])

    # NEGATIVE CONTROL: weights that are not all equal MUST change the answer,
    # or the argument is being ignored and every scheme below is measuring the
    # same thing under different names.
    w = [1.0 if i % 2 else 0.1 for i in range(len(obs))]
    r2 = B.fit_off_def(obs, keys, w)
    moved = max(abs(r0[k]["off"] - r2[k]["off"]) for k in keys)
    check("unequal weights actually change the fit", moved > 1e-6, "(%.4f)" % moved)

    check("a wrong-length weight vector is refused, not silently padded",
          _raises(lambda: B.fit_off_def(obs, keys, [1.0] * (len(obs) - 1))))

    print("\n3. The schemes are distinct, and do what their names say")
    m = {"gid": "1", "epoch": 1000000, "home": "A", "away": "B",
         "home_sets": 3, "away_sets": 0, "home_pts": 75, "away_pts": 45,
         "sets": 3, "margin": 10.0, "home_earned": 60.0, "away_earned": 30.0,
         "home_win": 1}
    _, w_flat = RF.scheme_obs([m], m["epoch"], {"name": "baseline"})
    check("baseline weights every match at 1.0", w_flat == [1.0])
    old = dict(m)
    old["epoch"] = m["epoch"] - int(30 * 86400)
    _, w_old = RF.scheme_obs([old], m["epoch"], {"half_life_days": 30})
    check("a match one half-life old weighs 0.5", abs(w_old[0] - 0.5) < 1e-9,
          "(%.4f)" % w_old[0])
    o_cap, _ = RF.scheme_obs([m], m["epoch"], {"margin_cap": 3.0})
    check("a cap actually clips the margin", o_cap[0][2] == 3.0, "(%s)" % o_cap[0][2])
    o_set, _ = RF.scheme_obs([m], m["epoch"], {"target": "sets"})
    check("the sets target uses set margin, not points", o_set[0][2] == 3.0,
          "(%s)" % o_set[0][2])
    o_e, _ = RF.scheme_obs([m], m["epoch"], {"target": "earned"})
    check("the earned target uses earned points only", o_e[0][2] == 10.0,
          "(%s)" % o_e[0][2])

    print("\n4. The shipped measurement")
    p = os.path.join(REPO, "data", "rating_factors_%d.json" % RF.SEASON)
    if not os.path.exists(p):
        print("  (no measurement on disk -- run scripts/rating_factors.py)")
    else:
        doc = json.load(open(p, encoding="utf-8"))
        sc = doc.get("schemes") or {}
        check("the baseline is present to compare against", "baseline" in sc)
        # Every scheme that claims to beat the baseline must have a CI clear of
        # zero. This is R1 in one line: a verdict may not rest on the point
        # estimate alone.
        wrong = [n for n, r in sc.items()
                 if r.get("beats_baseline") and (r.get("auc_delta_ci95") or [0])[0] <= 0]
        check("nothing is marked as beating the baseline on a point estimate",
              not wrong, "(%s)" % wrong)
        check("the write-up records what could NOT be measured",
              "not_measurable_here" in (doc.get("meta") or {}))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL RATING-FACTOR GUARDS PASS")
    return 0


def _raises(fn):
    try:
        fn()
    except Exception:
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
