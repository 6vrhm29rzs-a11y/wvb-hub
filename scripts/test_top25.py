#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Digby's Top 25.

The load-bearing property is that the blend weight is DERIVED. If k ever becomes
a number somebody typed, this ranking stops being defensible and becomes a
preference -- so the tests check the arithmetic that produces it, and check the
two ways it has already been got wrong:

  * shrinking toward the population instead of toward the projection's own
    error (that handed one match 20% of a team's rating instead of 7%);
  * z-scoring this season against whoever happens to have played, which in
    week one scores the best of six teams as if it were the best of 348.

Python 3.9 target. Run: python3 scripts/test_top25.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from digby_top25 import (shrinkage_k, variance_components,          # noqa: E402
                         per_match_margins, zscores)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = []


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


def test_k_uses_the_priors_error_not_the_population_spread():
    """THE REGRESSION. A useful prior must be shrunk toward less."""
    sigma2, tau2 = 23.93, 5.94
    k_naive = sigma2 / tau2                       # what the first version did
    k_good, err = shrinkage_k(sigma2, tau2, 0.8379)
    check(k_good > k_naive * 2,
          "a prior that predicts at rho=.84 earns far more weight than the "
          "population mean would", "naive %.1f vs %.1f" % (k_naive, k_good))
    check(abs(err - tau2 * (1 - 0.8379 ** 2)) < 1e-9,
          "prior error variance is tau^2(1-rho^2)")


def test_a_useless_prior_collapses_to_the_population():
    """POSITIVE CONTROL on the same formula: at rho=0 the projection carries no
    information and k must fall back to sigma^2/tau^2."""
    k, _ = shrinkage_k(23.93, 5.94, 0.0)
    check(abs(k - 23.93 / 5.94) < 1e-9,
          "POSITIVE CONTROL: rho=0 gives back the naive weight", "%.3f" % k)


def test_a_perfect_prior_is_never_overturned():
    k, _ = shrinkage_k(23.93, 5.94, 0.999999)
    check(k > 1e5, "a near-perfect prior takes essentially infinite evidence",
          "%.0f" % k)


def test_weight_grows_with_matches_and_never_exceeds_one():
    k = 13.52
    ws = [n / float(n + k) for n in (0, 1, 4, 14, 30, 200)]
    check(ws == sorted(ws), "weight on this season rises with matches played")
    check(ws[0] == 0.0, "no matches means the projection alone")
    check(max(ws) < 1.0, "it never reaches 1 -- the projection always counts")
    check(abs(ws[3] - 0.5) < 0.03, "at n=k the two weigh about equally",
          "%.3f" % ws[3])


def test_variance_components_denoise_tau():
    """Short seasons wobble; that wobble is not teams differing."""
    import random
    random.seed(11)
    true = [random.gauss(0, 2.0) for _ in range(200)]
    margins = dict((str(i), [random.gauss(t, 5.0) for _ in range(10)])
                   for i, t in enumerate(true))
    sigma2, tau2 = variance_components(margins)
    check(abs(sigma2 ** 0.5 - 5.0) < 0.6,
          "per-match sd recovered", "%.2f" % sigma2 ** 0.5)
    check(abs(tau2 ** 0.5 - 2.0) < 0.7,
          "between-team sd recovered after de-noising", "%.2f" % tau2 ** 0.5)
    raw = tau2 + sigma2 / 10.0
    check(raw ** 0.5 > tau2 ** 0.5,
          "NEGATIVE CONTROL: the un-de-noised spread is inflated",
          "%.2f vs %.2f" % (raw ** 0.5, tau2 ** 0.5))


def test_season_z_is_not_scaled_by_who_has_played():
    """Dividing by a measured tau is stable; z-scoring the played sample is not."""
    tau = 5.94 ** 0.5
    early = {"A": 4.0, "B": 1.0, "C": -2.0}
    late = dict(early)
    late.update(dict((str(i), 0.0) for i in range(300)))
    stable_early = early["A"] / tau
    stable_late = late["A"] / tau
    check(abs(stable_early - stable_late) < 1e-9,
          "dividing by tau gives the same answer in week 1 and week 12")
    z_early = zscores(early)["A"]
    z_late = zscores(late)["A"]
    check(abs(z_early - z_late) > 0.5,
          "NEGATIVE CONTROL: sample z-scoring would have swung with the field",
          "%.2f vs %.2f" % (z_early, z_late))


def test_the_built_file_is_coherent():
    p = os.path.join(REPO, "data", "digby_top25_2026.json")
    if not os.path.exists(p):
        print("  --   no built Top 25 yet; skipping")
        return
    doc = json.load(open(p, encoding="utf-8"))
    top = doc.get("top") or []
    check(len(top) == 25, "exactly 25 in the poll", str(len(top)))
    check([r["rank"] for r in top] == list(range(1, len(top) + 1)),
          "ranks are 1..25 with no gaps")
    scores = [r["score"] for r in top]
    check(scores == sorted(scores, reverse=True), "sorted by score, descending")
    also = doc.get("also_receiving") or []
    check(all(a["rank"] > 25 for a in also),
          "everyone receiving votes ranks below the poll")
    if top and also:
        check(top[-1]["score"] >= also[0]["score"],
              "and scores below the last ranked team")
    for r in top:
        w = r.get("weight_on_season")
        check_ok = (0.0 <= w < 1.0) and (w == 0.0 or r["matches"] > 0)
        if not check_ok:
            check(False, "weight out of range for %s" % r["team"], str(w))
            return
    check(True, "every weight is in [0,1) and zero only without matches")


def test_the_weekly_archive_captures_the_top_25():
    """The archive used to freeze the BOARD's order, which is a preseason
    projection until 50 matches -- storing the same numbers every week is a
    history of nothing. It captures the ranking that actually moves."""
    import snapshot_rankings as SNAP
    rows, source = SNAP.current_ranking()
    p = os.path.join(REPO, "data", "digby_top25_2026.json")
    if not os.path.exists(p):
        print("  --   no Top 25 built; skipping")
        return
    check(source == "digby",
          "the weekly snapshot archives Digby's Top 25", source)
    check(rows and all(r.get("source") == "digby" for r in rows),
          "every archived row carries its basis, so movement cannot mix rulers")
    check(len(rows) >= 25, "the poll and the receiving-votes teams are both kept",
          str(len(rows)))


def test_the_move_column_states_which_comparison_it_makes():
    """R4 in miniature: 'Move' means two different things depending on whether a
    same-basis week exists, so the header has to say which."""
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  --   no built page; skipping")
        return
    h = open(hub, encoding="utf-8").read()
    m = re.search(r'<th title="how the rank changed">([^<]+)</th>', h)
    check(m is not None, "the Move column has a header")
    if m:
        check(m.group(1).strip() in ("vs last week", "vs preseason"),
              "and it names the comparison", m.group(1))


def main():
    for fn in (test_k_uses_the_priors_error_not_the_population_spread,
               test_a_useless_prior_collapses_to_the_population,
               test_a_perfect_prior_is_never_overturned,
               test_weight_grows_with_matches_and_never_exceeds_one,
               test_variance_components_denoise_tau,
               test_season_z_is_not_scaled_by_who_has_played,
               test_the_built_file_is_coherent,
               test_the_weekly_archive_captures_the_top_25,
               test_the_move_column_states_which_comparison_it_makes):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all Top 25 invariants pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
