#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE SEASON-COUNT CONTRACT — fixture corpus + cross-surface agreement.

One build showed three season totals at once (masthead 402, rankings 397,
Result Ledger 409) because every surface hand-rolled its own exclusions —
and two had silently diverged from the ledgers: digby's margins were
folding in the 21-point-set exhibitions, and the rating fit's loader
skipped nothing at all. season_counts.py is now the one classification;
this suite pins it with a five-game corpus and asserts every displayed
count agrees with the contract on the same snapshot.
"""

import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def _game(gid, state="F", winner="1", hs=3, as_=0, lines=True,
          div=(1, 1)):
    ls = ([{"period": "1", "home": "25", "visit": "20"},
           {"period": "2", "home": "25", "visit": "21"},
           {"period": "3", "home": "25", "visit": "22"}] if lines else [])
    return {
        "game_id": gid, "game_state": state,
        "winner_team_id": winner,
        "linescores": ls,
        "teams": [
            {"team_id": "1", "is_home": True, "division": div[0],
             "sets_won": hs, "is_winner": winner == "1"},
            {"team_id": "2", "is_home": False, "division": div[1],
             "sets_won": as_, "is_winner": winner == "2"},
        ],
    }


def main():
    import season_counts as SC

    print("1. THE FIVE-GAME FIXTURE CORPUS")
    # one of each class the season has actually produced
    normal = _game("100001")
    dup = _game("100002")
    exh = _game("100003")
    empty = _game("100004", winner=None, hs=None, as_=None, lines=False)
    corrected = _game("100005", winner=None, hs=None, as_=None, lines=False)
    corpus = [normal, dup, exh, empty, corrected,
              _game("100006", state="P")]        # a pre game: not a final

    # steer the ledger readers at the module seams -- the real files stay
    # untouched, and restoring them is the finally-block's job
    import dupes as D
    import exhibitions as E
    real_dg, real_rg = D.duplicate_gids, E.resolved_gids
    real_corr = SC.corrections
    try:
        D.duplicate_gids = lambda season: {"100002"}
        E.resolved_gids = lambda season, games_path=None: {"100003"}
        SC.corrections = lambda season: {"100005": {"correct": {
            "winner_team_id": "2", "home_sets": 0, "away_sets": 3,
            "linescores": [{"period": "1", "home": "20", "visit": "25"},
                           {"period": "2", "home": "21", "visit": "25"},
                           {"period": "3", "home": "22", "visit": "25"}],
        }}}

        cls = SC.classify(corpus, 2026)
        check("the normal final is ok", cls.get("100001") == "ok",
              str(cls.get("100001")))
        check("the duplicate listing is duplicate",
              cls.get("100002") == "duplicate")
        check("the exhibition is exhibition",
              cls.get("100003") == "exhibition")
        check("the empty final is empty", cls.get("100004") == "empty")
        check("the corrected empty final is ok (correction applied "
              "before classification)", cls.get("100005") == "ok",
              str(cls.get("100005")))
        check("a non-final is not classified at all",
              "100006" not in cls)

        t = SC.totals(corpus, 2026)
        check("feed_records counts every completed record",
              t["feed_records"] == 5, str(t))
        check("results_on_display = ok + exhibition (3 = 2 ok + 1 exh)",
              t["results_on_display"] == 3, str(t))
        check("rating_eligible = ok, D-I both, with a line (2)",
              t["rating_eligible"] == 2, str(t))

        elig = SC.countable(corpus, 2026, need_line=True, d1_only=True)
        check("countable() returns exactly the eligible games",
              sorted(g["game_id"] for g in elig) == ["100001", "100005"],
              str([g["game_id"] for g in elig]))
        c5 = [g for g in elig if g["game_id"] == "100005"][0]
        check("...with the corrected winner and filled line",
              c5["winner_team_id"] == "2" and len(c5["linescores"]) == 3)

        # a non-D-I final is displayable but not rating-eligible
        nd = corpus + [_game("100007", div=(1, 2))]
        t2 = SC.totals(nd, 2026)
        check("[NEG] a non-D-I final joins the display count but not the "
              "rating count",
              t2["results_on_display"] == 4 and t2["rating_eligible"] == 2,
              str(t2))
    finally:
        D.duplicate_gids, E.resolved_gids = real_dg, real_rg
        SC.corrections = real_corr

    print("\n2. EVERY DISPLAYED COUNT AGREES WITH THE CONTRACT "
          "(same snapshot)")
    ds = os.path.join(REPO, "data", "data_2026.json")
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    if not (os.path.exists(ds) and os.path.exists(page_p)):
        print("  -- dataset or page absent; corpus checks stand alone")
    else:
        doc = json.load(io.open(ds, encoding="utf-8"))
        t = SC.totals(doc.get("games") or [], 2026)
        page = io.open(page_p, encoding="utf-8").read()

        m = re.search(r"<b>(\d+)</b> <span[^>]*>results on the board", page)
        check("masthead states results_on_display",
              m and int(m.group(1)) == t["results_on_display"],
              "%s vs %s" % (m and m.group(1), t["results_on_display"]))

        dg = json.load(io.open(os.path.join(
            REPO, "data", "digby_top25_2026.json"), encoding="utf-8"))
        n_dg = (dg.get("meta") or {}).get("matches_counted")
        # digby is AS-OF THE PREVIOUS DAY (Cody, 2026-09-01): its count is
        # checked against the cutoff-filtered eligible total
        check("digby's matches_counted equals "
              "rating_eligible_through_yesterday (drift here means the "
              "artifacts are from different snapshots -- rebuild the chain)",
              n_dg == t["rating_eligible_through_yesterday"],
              "%s vs %s" % (n_dg, t["rating_eligible_through_yesterday"]))

        cf = json.load(io.open(os.path.join(
            REPO, "data", "result_confidence_2026.json"), encoding="utf-8"))
        n_cf = ((cf.get("meta") or {}).get("counts") or {}).get("finals")
        check("the Result Ledger's population equals feed_records",
              n_cf == t["feed_records"],
              "%s vs %s" % (n_cf, t["feed_records"]))
        check("...and the page names that population",
              "Completed feed records" in page)

        # the three numbers differ for stated reasons; assert the algebra
        check("results_on_display = feed - duplicates - empty",
              t["results_on_display"] == t["feed_records"]
              - t["duplicate"] - t["empty"], str(t))
        check("rating_eligible <= results_on_display - exhibitions",
              t["rating_eligible"] <= t["results_on_display"]
              - t["exhibition"], str(t))

    print("\n3. NEGATIVE CONTROL -- the corpus catches a de-wired exclusion")
    # re-loosen the exhibition skip in-process and the totals must move
    try:
        E.resolved_gids = lambda season, games_path=None: set()
        t3 = SC.totals(corpus, 2026)
        check("[NEG] removing the exhibitions ledger changes "
              "rating_eligible (guard would trip)",
              t3["rating_eligible"] == 3, str(t3))
    finally:
        E.resolved_gids = real_rg

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL SEASON-COUNT GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
