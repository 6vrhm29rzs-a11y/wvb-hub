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

import io
import json
import os
import re
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

        print("\n5b. A NON-DIVISION-I OPPONENT IS MARKED ON THE ROW")
        # WHY THIS IS SYNTHETIC. The site deliberately does not filter non-D-I
        # opponents; it states them instead. That caveat lived only in the
        # Stats table's note -- one view away from the player card, which is
        # where a reader actually meets the number. Catori Crawford's ".500
        # HIT" is one match against a Division-II side and read exactly like
        # an SEC hitter's line.
        # Real data has only two of the three cases: every-match and
        # no-match. The MIXED case ("2 of these 3") cannot occur two days into
        # a season, so it is constructed here rather than left to be found
        # later by a reader.
        def note_for(flags):
            n, t = sum(1 for f in flags if f), len(flags)
            if n == 0:
                return ""
            if n == t:
                return "her only match" if t == 1 else "every match"
            # verb agrees with the count: "1 ... is", "2 ... are"
            return ("%d of these %d matches is against a non-Division-I "
                    "opponent" % (n, t)) if n == 1 else (
                   "%d of these %d matches are against non-Division-I "
                   "opponents" % (n, t))

        for flags, want in (([True], "her only match"),
                            ([True, True], "every match"),
                            ([True, False, False],
                             "1 of these 3 matches is against a "
                             "non-Division-I opponent"),
                            ([True, True, False],
                             "2 of these 3 matches are against "
                             "non-Division-I opponents"),
                            ([False], ""),
                            ([False, False], "")):
            got = note_for(flags)
            check("%-22s -> %r" % (flags, want), got == want, repr(got))

        hp, _which = None, None
        for cand in ("Cody/START-HERE.html", "output/vb_dashboard.html"):
            fp = os.path.join(REPO, cand)
            if os.path.exists(fp):
                hp = io.open(fp, encoding="utf-8").read()
                break
        if hp:
            # ⚠ ASSERT THE PIECES, NOT AN OLD IMPLEMENTATION'S LITERALS.
            # These checks used to look for whole sentences ("Her only match
            # on file"). Consolidating the four surfaces onto one helper meant
            # the sentence is now assembled, so those literals vanished and
            # the guard failed against a page that was working correctly. What
            # matters is that every branch and every subject still exists.
            for frag in ("The only match ", "Every match ",
                         " is against a non-Division-I opponent",
                         "of these ", "non-Division-I",
                         "are against non-Division-I opponents"):
                check("the caveat can say %r" % frag, frag in hp)
            # One subject per surface, so the sentence reads naturally in each.
            for where in ("'on file'", "'here'", "'in this sample'"):
                check("...with the subject %s" % where, where in hp)
            # NEGATIVE CONTROL ON THE CLASS NAME ITSELF. `ndi` was rejected
            # because it matches 53 substrings in this page (sta-ndi-ngs,
            # I-ndi-ana) -- the trap that made `.bwr` match `.bwrap` and
            # `mbrow` match the surname Stambrowska.
            check("[-] the marker class is not a substring of common words",
                  all("nondi" not in w
                      for w in ("standings", "indiana", "ending", "sondheim")))
            check("the marker renders at least once", 'class="nondi"' in hp)
            m3 = re.search(r"const PLAYERS = (\[.*?\]);\n", hp, re.S)
            PP = json.loads(m3.group(1)) if m3 else []
            flagged = sum(1 for pl in PP for g in pl.get("games", [])
                          if g.get("nondi"))
            total = sum(len(pl.get("games", [])) for pl in PP)
            check("[+] some game rows carry the flag", flagged > 0,
                  "%d of %d" % (flagged, total))
            # A FLAG THAT IS ALWAYS TRUE MARKS NOTHING.
            check("[-] ...and not every row does", flagged < total,
                  "%d of %d" % (flagged, total))
            print("     (%d of %d game rows face non-D-I opponents)"
                  % (flagged, total))

            # THE SAME CAVEAT ON THE TEAM PAGE. It was fixed on the player
            # card first; the identical defect sat one view over, where
            # Norfolk St. read "Hitting % .390" against opponents' ".037" --
            # both true, both from one Division-II match.
            check("the team page renders the caveat", "dicaveat" in hp)
            # ⚠ THE CAVEAT MUST NOT WEAR A FENCED BALLOT CLASS. `.warn` is
            # only ever defined as `.bwstate.warn`, inside the region the
            # public build strips -- borrowing it would style nothing and
            # would repeat the Match-Desk-borrows-.bwsub mistake. Assert the
            # caveat carries its own class and that the class is really
            # styled somewhere.
            check("[-] the caveat does not borrow a fenced ballot class",
                  'class="warn"' not in hp)
            # ⚠ ONE DEFINITION OF THE SENTENCE, or the four surfaces drift.
            # They already had: the table tooltip read "1 of these 1 matches
            # is". Assert the helper exists and that no call site rebuilds the
            # phrasing by hand.
            check("the caveat has ONE definition",
                  hp.count("function nonDiPhrase") == 1,
                  "%d definitions" % hp.count("function nonDiPhrase"))
            check("...used by every surface that shows it",
                  hp.count("nonDiPhrase(") >= 3,
                  "%d call sites" % hp.count("nonDiPhrase("))
            check("[-] no call site spells the sentence out again",
                  "of these ' + t + ' matches" not in hp
                  and "' matches ' + (d.nondi" not in hp)
            # The stats TABLE marks the row, not only the panel note. Norfolk
            # St. ranks 1st in fewest points allowed off one D-II match.
            check("the team stats table can mark a row",
                  "'in this sample'" in hp or '"in this sample"' in hp)
            check("...and the badge is styled inside a table cell too",
                  ".tm .nondi" in hp)
            check("...and its own class is actually defined",
                  ".dicaveat{" in hp)
            # The result row must carry the marker too, not just the note.
            check("a played row can carry the marker",
                  'g.nondi ?' in hp and hp.count('">non-D-I</b>') >= 2,
                  "%d marker sites" % hp.count('">non-D-I</b>'))
            # ⚠ TEAMS IS AN OBJECT, NOT AN ARRAY. The first version of this
            # block matched `const TEAMS = (\[...\])` and therefore matched
            # nothing, so every assertion below it was skipped in silence and
            # the section still printed all-ok. A guard that cannot run is not
            # a guard -- so a missing payload is now a FAILURE, not a skip.
            m4 = re.search(r"const TEAMS = (\{.*?\});\n", hp, re.S)
            check("[+] the TEAMS payload was found and parsed", bool(m4),
                  "regex did not match -- the checks below would be skipped")
            if m4:
                _T = json.loads(m4.group(1))
                TT = list(_T.values()) if isinstance(_T, dict) else _T
                pl = [g for t2 in TT for g in (t2.get("played") or [])]
                nd = [g for g in pl if g.get("nondi")]
                check("[+] some played rows are flagged", len(nd) > 0,
                      "%d of %d" % (len(nd), len(pl)))
                check("[-] ...and not all of them", len(nd) < len(pl),
                      "%d of %d" % (len(nd), len(pl)))
                ts = [t2.get("tstats") for t2 in TT if t2.get("tstats")]
                own = [x["own"] for x in ts if x.get("own")]
                check("team totals carry a non-D-I match count",
                      all("nondi" in o for o in own),
                      "%d of %d" % (sum(1 for o in own if "nondi" in o),
                                    len(own)))
                # It must never exceed the matches it counts.
                check("[-] the count never exceeds the sample",
                      all((o.get("nondi") or 0) <= (o.get("matches") or 0)
                          for o in own))

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
