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
        # digby counts through-yesterday PLUS today's school-verified
        # finals (the TRUST CUTOFF, 2026-09-04). Eligible-now MOVES
        # intraday as finals verify, so equality is only meaningful
        # within one corpus generation: same fingerprint -> must match;
        # different -> the artifact is from an older corpus, which the
        # build gate and fingerprint guards already refuse to PUBLISH.
        _elig_now = t.get("rating_eligible_now",
                          t["rating_eligible_through_yesterday"])
        _fp_now = SC.corpus_fingerprint(2026)
        _fp_dg = (dg.get("meta") or {}).get("corpus_fingerprint")
        if _fp_dg and _fp_dg != _fp_now:
            print("    (digby artifact is from corpus %s, current is %s "
                  "-- intraday drift; equality is enforced at build time "
                  "by the manifest gate)" % (_fp_dg[:8], _fp_now[:8]))
        else:
            # Within one corpus generation the VERIFICATION state still
            # moves (the incremental verifier runs between rebuilds), so
            # eligible_now can grow past an artifact that was correct
            # when built. The stable invariants: digby's count is its
            # through-yesterday base plus its OWN verified-intraday
            # tally, and never exceeds the current eligible_now.
            _nv_dg = (dg.get("meta") or {}).get(
                "verified_intraday_counted") or 0
            check("digby's matches_counted = through_yesterday + its own "
                  "verified-intraday tally",
                  n_dg == t["rating_eligible_through_yesterday"] + _nv_dg,
                  "%s vs %s+%s" % (
                      n_dg, t["rating_eligible_through_yesterday"], _nv_dg))
            check("digby's matches_counted never exceeds eligible_now",
                  n_dg <= _elig_now, "%s vs %s" % (n_dg, _elig_now))

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

    # -- winner_index: the ONE winner derivation (2026-09-03, game 6628428
    # went final with sets 3-0 and is_winner False on BOTH sides; every
    # counter trusting the raw flag scored both teams a loss) --
    def _g(fa, fb, sa=None, sb=None):
        return {"teams": [{"is_winner": fa, "sets_won": sa},
                          {"is_winner": fb, "sets_won": sb}]}
    check("winner_index: exactly one flag decides",
          SC.winner_index(_g(True, False)) == 0
          and SC.winner_index(_g(False, True)) == 1)
    check("winner_index: flag absent on both -> sets decide (6628428)",
          SC.winner_index(_g(False, False, 3, 0)) == 0
          and SC.winner_index(_g(None, None, 1, 3)) == 1)
    check("winner_index: both flags true (incoherent) -> sets decide",
          SC.winner_index(_g(True, True, 0, 3)) == 1)
    check("winner_index: string sets still compare",
          SC.winner_index(_g(False, False, "3", "1")) == 0)
    check("winner_index: no flag, no sets -> None (counts NOWHERE)",
          SC.winner_index(_g(False, False)) is None)
    check("winner_index: level sets, no flag -> None, never a guess",
          SC.winner_index(_g(False, False, 2, 2)) is None)
    check("winner_index: not two teams -> None",
          SC.winner_index({"teams": [{"is_winner": True}]}) is None)
    # NEGATIVE CONTROL: the raw-flag reading really does differ on the
    # 6628428 shape -- if it ever stops differing, this guard guards nothing.
    _raw = [bool(t.get("is_winner")) for t in _g(False, False, 3, 0)["teams"]]
    check("[NEG] the raw flag scores the 6628428 shape as two losses "
          "(what winner_index exists to prevent)",
          _raw == [False, False]
          and SC.winner_index(_g(False, False, 3, 0)) == 0)

    # -- an explicit empty linescores_replace clears a truncated tape
    # (2026-09-04, 6626507: feed went final mid-third-set; corrected 3-2
    # has no per-set points in any source, so the correction withholds
    # the line rather than showing three real rows beside a 3-2) --
    _tg = {"game_id": "990001", "game_state": "F",
           "teams": [{"team_id": "1", "is_home": False, "sets_won": 2,
                      "is_winner": False},
                     {"team_id": "2", "is_home": True, "sets_won": 0,
                      "is_winner": False}],
           "linescores": [{"period": 1, "visit": 25, "home": 22},
                          {"period": 2, "visit": 25, "home": 21},
                          {"period": 3, "visit": 22, "home": 21}]}
    _tc = {"990001": {"correct": {"winner_team_id": "1", "away_sets": 3,
                                  "home_sets": 2, "linescores": [],
                                  "linescores_replace": True}}}
    _tr = SC.apply_correction(_tg, _tc)
    check("empty linescores_replace clears the truncated tape",
          _tr["linescores"] == [] and
          [t["sets_won"] for t in _tr["teams"]] == [3, 2] and
          SC.winner_index(_tr) == 0)
    # NEGATIVE CONTROL: without the replace flag the lines must be KEPT
    _tc2 = {"990001": {"correct": {"winner_team_id": "1", "away_sets": 3,
                                   "home_sets": 2}}}
    check("[NEG] without the flag the feed's lines are kept",
          len(SC.apply_correction(_tg, _tc2)["linescores"]) == 3)

    # -- the trust cutoff (2026-09-04): a school-verified final enters
    # the rating intraday; an unverified same-day feed claim never does --
    _cut = 1000
    _pre  = {"game_id": "800001", "start_time_epoch": 500}
    _todv = {"game_id": "800002", "start_time_epoch": 2000}
    _todu = {"game_id": "800003", "start_time_epoch": 2000}
    _ver = {"800002"}
    check("trust cutoff: before the boundary always counts",
          SC.rating_input_ok(_pre, _cut, _ver))
    check("trust cutoff: today + school-verified counts",
          SC.rating_input_ok(_todv, _cut, _ver))
    check("[NEG] trust cutoff: today + UNVERIFIED does not count",
          not SC.rating_input_ok(_todu, _cut, _ver))
    check("verified_result_gids returns a set and never raises",
          isinstance(SC.verified_result_gids(), set))

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
