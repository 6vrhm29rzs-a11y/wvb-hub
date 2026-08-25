#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Player aggregation: unique games first, totals derived from them.

⚠ THE ORDERING DEFECT THIS EXISTS FOR. Season totals used to be accumulated as
box-score rows arrived, and the match log was deduplicated by game id
afterwards. So a second row for the SAME canonical player in the SAME match
produced a page where the log said one match and the season totals counted two
-- two numbers on one card disagreeing, with nothing to say which was wrong.
It was reachable: the duplicate-identity bug fixed alongside it came from the
feed spelling one player two ways, and two spellings in a single match is the
same input arriving twice.

The fix is an ordering one: choose the unique game record first, then derive
every total and rate FROM those records, so "the season is the sum of the
games" is a property of the construction rather than of two code paths
agreeing.

This test feeds box_and_players() a synthetic season containing a deliberate
duplicate and asserts nothing doubles. It runs against a THROWAWAY season so it
can never touch real data.

Python 3.9 target. Run: python3 scripts/test_player_aggregation.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
FAILS = []

TEST_SEASON = 2099          # never a real season; the fixture is deleted after


def check(label, ok, detail=""):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def row(first, last, gp, k, e, ta, digs, aces, ast=0, bs=0, ba=0):
    return {"team_id": "9001", "first": first, "last": last, "pos": "OH",
            "num": 7, "gp": gp, "kills": k, "errors": e, "atts": ta,
            "digs": digs, "aces": aces, "assists": ast, "bs": bs, "ba": ba}


# THE FIXTURE. Game A carries the same player TWICE, spelled two ways -- the
# exact shape the live feed produced for DeLeye/Deleye. The second copy is the
# THINNER line, so a correct implementation must keep the richer one and count
# it once.
FIXTURE = [
    {"game_id": "A", "rows": [
        row("Brooklyn", "DeLeye", gp=4, k=10, e=3, ta=30, digs=6, aces=1),
        row("Brooklyn", "Deleye", gp=2, k=4, e=1, ta=12, digs=2, aces=0),
    ]},
    {"game_id": "B", "rows": [
        row("Brooklyn", "DeLeye", gp=3, k=6, e=2, ta=20, digs=4, aces=2),
    ]},
]

# Derived by hand from the fixture, so the expectation is independent of the
# code under test: game A's RICHER row plus game B.
EXPECT = {"games": 2, "sets": 7.0, "k": 16.0, "e": 5.0, "ta": 50.0,
          "digs": 10.0, "aces": 3.0}
EXPECT["pts"] = 16.0 + 3.0            # kills + aces (no blocks in the fixture)
EXPECT["hit"] = round((16.0 - 5.0) / 50.0, 3)
EXPECT["kps"] = round(16.0 / 7.0, 2)
EXPECT["pps"] = round(19.0 / 7.0, 2)

# What the OLD code produced: the richer row won the log, but both rows had
# already been added to the totals.
# Confirmed by a negative control that restores the old ordering: every one of
# these is what the page would have shown, against a match log showing two.
WOULD_HAVE_BEEN = {"sets": 9.0, "k": 20.0, "e": 6.0, "ta": 62.0,
                   "digs": 12.0, "aces": 3.0, "pts": 23.0}

# ⚠ build_hub SETS SEASON = 2026 AS A CONSTANT, not from the environment. The
# first version of this harness exported WVB_SEASON and assumed that was
# enough -- so it silently read the REAL 2026 playerbox and reported Brooklyn's
# actual season as a failure. It only failed instead of passing vacuously
# because the expectations above are derived by hand from the fixture. The
# season is repointed on the imported module, which box_and_players() reads at
# call time.
RUNNER = r"""
import json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import build_hub as BH
BH.SEASON = int(os.environ["WVB_SEASON"])
# The Players list is a DIVISION-I directory, so box_and_players() drops any
# team not in the official membership -- which a synthetic team never is. That
# filter is real and is covered elsewhere; it is not what this test is about,
# so it is stood down for the fixture rather than worked around by borrowing a
# real school's id (which would make the fixture look like real data).
BH.di_teams = lambda: set()
res = [{"gid": "A", "date": "2099-09-01", "home": "9001", "away": "9002"},
       {"gid": "B", "date": "2099-09-08", "home": "9002", "away": "9001"}]
boxes, players = BH.box_and_players(res)
mine = [p for p in players if "Brooklyn" in p["name"]]
print(json.dumps({"n": len(mine), "p": mine[0] if mine else None}))
"""


def main():
    print("PLAYER AGGREGATION GUARDS\n")
    raw = os.path.join(REPO, "data", "raw", str(TEST_SEASON))
    if os.path.exists(raw):
        print("  refusing to run: %s already exists" % raw)
        return 1
    os.makedirs(raw)
    try:
        with open(os.path.join(raw, "playerbox.jsonl"), "w",
                  encoding="utf-8") as fh:
            for rec in FIXTURE:
                fh.write(json.dumps(rec) + "\n")

        env = dict(os.environ, WVB_SEASON=str(TEST_SEASON), SCRIPTS=SCRIPTS)
        out = subprocess.check_output([sys.executable, "-c", RUNNER], env=env,
                                      universal_newlines=True)
        got = json.loads(out.strip().splitlines()[-1])

        print("1. THE DUPLICATE COLLAPSES TO ONE PLAYER")
        check("one canonical player, not two", got["n"] == 1,
              "%d players" % got["n"])
        p = got["p"]
        if not p:
            print("\n  no player came back; cannot continue")
            return 1
        # No roster exists for a throwaway season, so the display name is the
        # first-seen feed spelling -- the roster override is covered by
        # test_player_identity against the real build.
        check("...carrying one spelling, not two",
              p["name"] == "Brooklyn DeLeye", repr(p["name"]))

        print("\n2. THE LOG HOLDS ONE ROW PER GAME")
        gids = [g["gid"] for g in p["games"]]
        check("two games, not three", len(gids) == EXPECT["games"], str(gids))
        check("...and no game id repeats", len(gids) == len(set(gids)),
              str(gids))
        ga = [g for g in p["games"] if g["gid"] == "A"]
        check("the RICHER row survived game A",
              bool(ga) and ga[0]["sets"] == 4 and ga[0]["k"] == 10,
              str(ga[:1]))

        print("\n3. NOTHING IS DOUBLE-COUNTED")
        for f in ("sets", "k", "e", "ta", "digs", "aces", "pts"):
            check("%-5s is %s, not %s" % (
                      f, EXPECT[f],
                      WOULD_HAVE_BEEN.get(f, "the sum of both rows")),
                  abs((p.get(f) or 0) - EXPECT[f]) < 1e-9,
                  "got %s" % p.get(f))

        print("\n4. RATES ARE DERIVED FROM THE UNIQUE GAMES TOO")
        # ⚠ A RATE CAN BE WRONG IN BOTH DIRECTIONS AT ONCE. With the old code
        # both numerator and denominator were inflated, so kills/set stayed
        # plausible while the totals under it were not.
        check("hit%% is (K-E)/TA on deduped counts",
              abs((p.get("hit") or 0) - EXPECT["hit"]) < 1e-9,
              "got %s want %s" % (p.get("hit"), EXPECT["hit"]))
        check("kills/set uses the deduped set count",
              abs((p.get("kps") or 0) - EXPECT["kps"]) < 1e-9,
              "got %s want %s" % (p.get("kps"), EXPECT["kps"]))
        check("points/set uses the deduped set count",
              abs((p.get("pps") or 0) - EXPECT["pps"]) < 1e-9,
              "got %s want %s" % (p.get("pps"), EXPECT["pps"]))

        print("\n5. THE SEASON IS THE SUM OF THE LOG, BY CONSTRUCTION")
        for f in ("sets", "k", "e", "ta", "digs", "aces", "pts"):
            s = sum(g.get(f) or 0 for g in p["games"])
            check("total %-5s equals the log" % f,
                  abs(s - (p.get(f) or 0)) < 1e-9,
                  "total %s, log %s" % (p.get(f), s))

        print("\n6. CLASS YEARS ARE SPELLED OUT, UNKNOWNS PRESERVED")
        sys.path.insert(0, SCRIPTS)
        import build_hub as BH
        for raw_v, want in (("So", "Sophomore"), ("so", "Sophomore"),
                            ("So.", "Sophomore"), ("Fr", "Freshman"),
                            ("R-Fr", "Redshirt Freshman"),
                            ("R-So", "Redshirt Sophomore"), ("Jr", "Junior"),
                            ("R-Jr", "Redshirt Junior"), ("Sr", "Senior"),
                            ("R-Sr", "Redshirt Senior"), ("Gr", "Graduate")):
            check("%-6r -> %s" % (raw_v, want), BH.class_full(raw_v) == want,
                  repr(BH.class_full(raw_v)))
        # ⚠ AN UNKNOWN VALUE IS NOT GUESSED AT. Anything the schools publish
        # that is not one of the nine standard abbreviations is shown exactly
        # as published -- including a value already spelled out.
        for keep in ("Sophomore", "Redshirt Freshman", "5th Year", "RS-Fr",
                     "Grad Transfer", "", None):
            check("[-] %r is preserved exactly" % (keep,),
                  BH.class_full(keep) == keep, repr(BH.class_full(keep)))
    finally:
        shutil.rmtree(raw, ignore_errors=True)
        check("[+] the throwaway season fixture was removed",
              not os.path.exists(raw))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL PLAYER AGGREGATION GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
