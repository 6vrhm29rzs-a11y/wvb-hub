#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE ADVERSARIAL FIXTURE CORPUS -- Reliability Architecture Audit §4.

Ten match shapes, every one taken from something the feed actually did
this season, run through the REAL canonical code (season_counts,
confidence) with injected ledgers. Asserts class membership, resolved
result, box ownership and provenance state for each.

The corpus tests the CONTRACT; consumer conformance to the contract is
the reader map + the manifest invariant (test_audit_manifest checks).
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def team(tid, div=1, home=False, sets=None, winner=False):
    return {"team_id": str(tid), "division": div, "is_home": home,
            "sets_won": sets, "is_winner": winner}


def lines(pairs):
    return [{"period": i + 1, "visit": a, "home": b}
            for i, (a, b) in enumerate(pairs)]


def main():
    import season_counts as SC
    import dupes
    import exhibitions as EXH
    import confidence as CF

    SEASON = 2026

    # ── the corpus ─────────────────────────────────────────────────────
    G = {}
    # 1. ordinary final: A (away) beats B (home) 3-0
    G["F_ORD"] = {"game_id": "900001", "game_state": "F",
                  "winner_team_id": "1",
                  "teams": [team(1, sets=3, winner=True),
                            team(2, home=True, sets=0)],
                  "linescores": lines([(25, 20), (25, 18), (25, 22)]),
                  "location": {"venue": "Test Arena"}}
    # 2. the SMU shape: feed says HOME won 3-2, correction flips winner,
    #    replaces the (team-swapped) lines and swaps the box attribution
    G["F_SWAP"] = {"game_id": "900002", "game_state": "F",
                   "winner_team_id": "20",
                   "teams": [team(10, sets=2), team(20, home=True, sets=3,
                                                    winner=True)],
                   "linescores": lines([(25, 27), (20, 25), (25, 20),
                                        (25, 23), (12, 15)])}
    # 3. a ledgered duplicate listing of F_ORD
    G["F_DUP"] = {"game_id": "900003", "game_state": "F",
                  "winner_team_id": "1",
                  "teams": [team(1, sets=3, winner=True),
                            team(2, home=True, sets=0)],
                  "linescores": []}
    # 4. a ledgered nonstandard-format exhibition (sets to 21)
    G["F_EXH"] = {"game_id": "900004", "game_state": "F",
                  "winner_team_id": "3",
                  "teams": [team(3, sets=2, winner=True),
                            team(4, home=True, sets=0)],
                  "linescores": lines([(21, 18), (24, 22)])}
    # 5. a final asserting no result at all
    G["F_EMPTY"] = {"game_id": "900005", "game_state": "F",
                    "winner_team_id": None,
                    "teams": [team(5), team(6, home=True)],
                    "linescores": [{"period": 1, "visit": None,
                                    "home": None}]}
    # 6. an under-review conflict (official source disputes, no
    #    correction resolves it yet)
    G["F_REVIEW"] = {"game_id": "900006", "game_state": "F",
                     "winner_team_id": "7",
                     "teams": [team(7, sets=3, winner=True),
                               team(8, home=True, sets=1)],
                     "linescores": lines([(25, 20), (25, 22), (20, 25),
                                          (25, 23)])}
    # 7. a final with NO venue -- venue truth is unavailable; counting
    #    must be untouched
    G["F_NOVENUE"] = {"game_id": "900007", "game_state": "F",
                      "winner_team_id": "9",
                      "teams": [team(9, sets=3, winner=True),
                                team(11, home=True, sets=2)],
                      "linescores": lines([(25, 20), (23, 25), (25, 27),
                                           (25, 18), (15, 10)])}
    # 8. a live record then its final -- the log's append-only shape
    G["LIVE"] = {"game_id": "900008", "game_state": "I",
                 "winner_team_id": None,
                 "teams": [team(12), team(13, home=True)],
                 "linescores": lines([(18, 24)])}
    G["LIVE_F"] = {"game_id": "900008", "game_state": "F",
                   "winner_team_id": "13",
                   "teams": [team(12, sets=1), team(13, home=True, sets=3,
                                                    winner=True)],
                   "linescores": lines([(24, 26), (25, 20), (18, 25),
                                        (19, 25)])}
    # 9. two legitimate rematches: same teams, different dates, distinct
    #    gids -- BOTH count (the Boise-Middle Tennessee case)
    G["RE_A"] = {"game_id": "900009", "game_state": "F",
                 "winner_team_id": "14",
                 "teams": [team(14, sets=3, winner=True),
                           team(15, home=True, sets=1)],
                 "linescores": lines([(25, 20), (25, 22), (20, 25),
                                      (25, 23)]),
                 "start_time_epoch": 1000}
    G["RE_B"] = {"game_id": "900010", "game_state": "F",
                 "winner_team_id": "15",
                 "teams": [team(14, sets=1), team(15, home=True, sets=3,
                                                  winner=True)],
                 "linescores": lines([(20, 25), (25, 22), (20, 25),
                                      (23, 25)]),
                 "start_time_epoch": 90000}
    # 11. the FLAGLESS FINAL (2026-09-03, game 6628428): state F, a real
    #     set line 3-0, and is_winner FALSE ON BOTH SIDES. Counters that
    #     trusted the raw flag scored BOTH teams a loss. Class stays ok
    #     (sets assert the result) and winner_index derives it.
    G["F_NOFLAG"] = {"game_id": "900011", "game_state": "F",
                     "teams": [team(16, sets=3), team(17, home=True, sets=0)],
                     "linescores": lines([(25, 18), (25, 21), (25, 15)]),
                     "start_time_epoch": 2000}

    # 12. the SELF-CONTRADICTORY final (2026-09-05, Providence-Bryant /
    #     UIC-Montana St. / Central Ark.-Southern Miss., three in two
    #     hours): complete lines name one winner, derived fields name the
    #     other. Machine-nominated hold: counts NOWHERE, stays on display.
    G["F_SELFCON"] = {"game_id": "900012", "game_state": "F",
                      "winner_team_id": "19",
                      "teams": [team(18, sets=1), team(19, home=True,
                                                       sets=3, winner=True)],
                      "linescores": lines([(25, 19), (23, 25), (25, 12),
                                           (25, 16)]),
                      "start_time_epoch": 3000}

    games = list(G.values())

    # ── injected ledgers, at the module seams the real code uses ──────
    corr = {"900002": {"correct": {
        "winner_team_id": "10", "away_sets": 3, "home_sets": 2,
        "linescores": [{"period": 1, "visit": 27, "home": 25},
                       {"period": 2, "visit": 25, "home": 20},
                       {"period": 3, "visit": 20, "home": 25},
                       {"period": 4, "visit": 23, "home": 25},
                       {"period": 5, "visit": 15, "home": 12}],
        "linescores_replace": True,
        "box_team_swap": {"10": "20", "20": "10"}}}}
    real = (dupes.duplicate_gids, EXH.resolved_gids, SC.corrections,
            SC.review_gids)
    try:
        dupes.duplicate_gids = lambda season=None: {"900003": "900001"}
        EXH.resolved_gids = lambda season, games_path=None: {"900004"}
        SC.corrections = lambda season: corr
        SC.review_gids = lambda season: {"900006"}

        print("1. ONE CLASS EACH, THE RIGHT ONE")
        cls = SC.classify(games, SEASON)
        want = {"900001": "ok", "900002": "ok", "900003": "duplicate",
                "900004": "exhibition", "900005": "empty", "900011": "ok",
                "900012": "self_contradictory",
                "900006": "under_review", "900007": "ok",
                "900008": "ok", "900009": "ok", "900010": "ok"}
        for gid, w in sorted(want.items()):
            check("%s -> %s" % (gid, w), cls.get(gid) == w, cls.get(gid))
        check("the live (non-final) record classifies nothing extra",
              set(cls) == set(want))

        print("\n2. THE NAMED TOTALS ADD UP")
        t = SC.totals(games, SEASON)
        check("feed_records counts every completed record",
              t["feed_records"] == 12, t)  # +F_NOFLAG +F_SELFCON
        check("results_on_display = ok + exhibition + under_review",
              t["results_on_display"] == t["ok"] + t["exhibition"]
              + t["under_review"] + t["self_contradictory"]
              == 7 + 1 + 1 + 1)  # +F_NOFLAG; +F_SELFCON displays, held
        check("rating_eligible: ok, both D-I, with a line",
              t["rating_eligible"] == 7, t)  # +F_NOFLAG

        print("\n3. THE RESOLVED MATCH (corrections applied once)")
        cg = [g for g in SC.countable(games, SEASON)
              if g["game_id"] == "900002"][0]
        check("corrected winner is the away side",
              cg["winner_team_id"] == "10")
        aw = [x for x in cg["teams"] if not x.get("is_home")][0]
        hm = [x for x in cg["teams"] if x.get("is_home")][0]
        check("corrected sets 3-2, mirrored on both team rows",
              aw["sets_won"] == 3 and hm["sets_won"] == 2)
        check("linescores REPLACED (flagged), ints, set one 27-25 away",
              cg["linescores"][0]["visit"] == 27
              and isinstance(cg["linescores"][0]["visit"], int))
        check("the raw record is untouched (corrections copy)",
              G["F_SWAP"]["winner_team_id"] == "20")
        check("box ownership swaps via the SAME correction",
              SC.box_team_swaps(SEASON).get("900002")
              == {"10": "20", "20": "10"})

        print("\n4. MEMBERSHIP: WHO COUNTS, WHO ONLY AUDITS")
        counted = {g["game_id"] for g in SC.countable(games, SEASON)}
        check("duplicate, exhibition, empty and under-review count "
              "NOWHERE",
              not ({"900003", "900004", "900005", "900006"} & counted))
        check("both rematches count -- no heuristic dedup",
              {"900009", "900010"} <= counted)
        check("the no-venue final counts (venue truth is separate)",
              "900007" in counted)
        check("live->final: the gid counts exactly once",
              sum(1 for g in SC.countable(games, SEASON)
                  if g["game_id"] == "900008") == 1)
        check("...and resolves to the FINAL record's result",
              [g for g in SC.countable(games, SEASON)
               if g["game_id"] == "900008"][0]["winner_team_id"] == "13")

        print("\n5. A REVISED FINAL MUST NOT DOUBLE-COUNT")
        # the append-only log can hold TWO final records for one gid (a
        # scorer revision refetched). The contract: last-wins, once.
        rev = dict(G["F_ORD"])
        rev["winner_team_id"] = "2"
        rev["teams"] = [team(1, sets=2), team(2, home=True, sets=3,
                                              winner=True)]
        # a real scorer revision revises the TAPE too -- keeping the old
        # sweep lines beside a flipped 3-2 made this fixture
        # self-contradictory the day that class was born (2026-09-05),
        # and a held record is not a counted one
        rev["linescores"] = lines([(25, 20), (18, 25), (25, 27),
                                   (23, 25), (12, 15)])
        games2 = games + [rev]
        n = sum(1 for g in SC.countable(games2, SEASON)
                if g["game_id"] == "900001")
        check("two final records, one gid -> countable yields ONE",
              n == 1, "%d records for 900001" % n)
        if n == 1:
            check("...and it is the LAST (the revision)",
                  [g for g in SC.countable(games2, SEASON)
                   if g["game_id"] == "900001"][0]["winner_team_id"]
                  == "2")

        print("\n6. PROVENANCE STATES (confidence.field_state)")
        SUP = {"status": "confirms", "fields": ["result"],
               "url": "https://a.example.edu", "kind": "host_livestat"}
        SCH = {"status": "confirms", "fields": ["result"],
               "url": "https://b.example.edu", "kind": "school_site"}
        NCAA = {"status": "confirms", "fields": ["result"],
                "url": "https://ncaa.example", "kind": "ncaa_official"}
        CONF = {"status": "conflicts", "fields": ["result"],
                "url": "https://c.example.edu", "kind": "school_site"}
        check("one school source alone corroborates, never confirms",
              CF.field_state([SCH], "result", "official") == "official")
        check("box + school kinds -> independently confirmed",
              CF.field_state([SUP, SCH], "result", "official")
              == "confirmed")
        check("the NCAA feed can never corroborate itself",
              CF.field_state([NCAA, NCAA], "result", "official")
              == "official")
        check("a conflict outranks everything -> disputed",
              CF.field_state([SUP, SCH, CONF], "result", "official")
              == "disputed")
        check("two entries from ONE url count once",
              CF.field_state([SUP, dict(SUP)], "result", "official")
              == "official")

        print("\n7. [NEG] NEGATIVE CONTROLS")
        # un-ledger the duplicate: it must fall back to counting (the
        # ledger is the only thing excluding it -- no hidden heuristic)
        dupes.duplicate_gids = lambda season=None: {}
        check("[NEG] without its ledger entry the duplicate counts "
              "again (no hidden heuristic)",
              "900003" in {g["game_id"]
                           for g in SC.countable(games, SEASON)})
        dupes.duplicate_gids = lambda season=None: {"900003": "900001"}
        # strip the correction: the swap match still counts, at the
        # FEED's (wrong) values -- a correction is data, not code
        SC.corrections = lambda season: {}
        raw = [g for g in SC.countable(games, SEASON)
               if g["game_id"] == "900002"][0]
        check("[NEG] without the correction the feed's record stands "
              "(and the box swap map is empty)",
              raw["winner_team_id"] == "20"
              and SC.box_team_swaps(SEASON) == {})
        SC.corrections = lambda season: corr
    finally:
        (dupes.duplicate_gids, EXH.resolved_gids, SC.corrections,
         SC.review_gids) = real

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL FIXTURE-CORPUS CONTRACTS HOLD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
