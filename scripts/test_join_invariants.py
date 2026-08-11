#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard the surname-anchored join against attributing one player's season to another.

THE RISK THIS GUARDS. The join's surname-anchored pass exists to recover real
misses -- "Madi Cowan" on a 2026 roster is "Madison Cowan" in the 2025 feed,
and without it 147 points go missing from a returning-production number. But
the same loosening, applied to the surname instead of the given name, joins
"Lauren Pyle" to "Lauren Malone": two different people, 316 kills, and a
plausible-looking wrong number on the page. That is the R4/R5 failure mode --
every value computed correctly, displayed against the wrong person.

Data-correctness tests cannot catch that (see the note under R4: the crawl was
correct, reconcile was 348/348, CI was green, and a human found the bug). So
this tests the JOIN DECISION itself, on fixtures where the right answer is
known by construction.

NEGATIVE CONTROL IS PART OF THE TEST. A test that only passes against the fix
proves nothing about whether it would catch the bug. The last section
deliberately re-loosens the rule in-process and asserts that the guard tests
then FAIL. If the negative control does not trip, this file is not guarding
anything and says so.

Python 3.9 target.
"""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import join_players as J  # noqa: E402


def _player(team_id, first, last, points=100, kills=100, sets=90):
    return {"team_id": team_id, "first": first, "last": last, "points": points,
            "kills": kills, "sets": sets, "num": 1, "pos": "OH", "matches": 30,
            "errors": 0, "atts": 0, "aces": 0, "digs": 0, "block_solos": 0,
            "block_assists": 0, "assists": 0}


def _roster(name, cls="Jr"):
    p = name.split(" ")
    return {"first": p[0], "last": " ".join(p[1:]) or None, "name_raw": name,
            "class_raw": cls, "pos_raw": None, "num_raw": "1",
            "how": "roster-anchor"}


def run_join(roster_names, pool_names, tid="9001"):
    """Drive the REAL join over fixtures and return that team's result."""
    d = tempfile.mkdtemp()
    rp = os.path.join(d, "r.json")
    pp = os.path.join(d, "p.json")
    op = os.path.join(d, "o.json")
    json.dump({"teams": {"Fixture": {"team_id": tid, "status": "ok",
                                     "players": [_roster(*n) if isinstance(n, tuple)
                                                 else _roster(n)
                                                 for n in roster_names]}}},
              open(rp, "w"))
    json.dump({"meta": {}, "players": [_player(tid, *n.split(" ", 1))
                                       for n in pool_names]}, open(pp, "w"))
    old = (J.ROSTERS, J.PLAYERS, J.OUT)
    J.ROSTERS, J.PLAYERS, J.OUT = rp, pp, op
    try:
        with redirect_stdout(io.StringIO()):
            J.main()
        return json.load(open(op))["teams"]["Fixture"]
    finally:
        J.ROSTERS, J.PLAYERS, J.OUT = old


def joined_names(res):
    return set(r["name"] for r in res.get("returning") or [])


def unresolved_names(res):
    return set(n for n, _why in res.get("unresolved") or [])


CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("nickname joins (the case the pass exists for)")
def t_nickname():
    r = run_join(["Madi Cowan"], ["Madison Cowan"])
    assert joined_names(r) == {"Madi Cowan"}, r
    assert not unresolved_names(r), r


@check("compound surname joins")
def t_compound():
    r = run_join(["Ava Hewitt-Smith"], ["Ava Hewitt"])
    assert joined_names(r) == {"Ava Hewitt-Smith"}, r


@check("compound GIVEN name joins (Bernardita/Maria Bernardita)")
def t_compound_given():
    r = run_join(["Bernardita Aguilar"], ["Maria Bernardita Aguilar Toranza"])
    assert joined_names(r) == {"Bernardita Aguilar"}, r


@check("DIFFERENT SURNAME never joins (Pyle/Malone)")
def t_different_surname():
    r = run_join(["Lauren Pyle"], ["Lauren Malone"])
    assert not joined_names(r), r
    assert unresolved_names(r) == {"Lauren Pyle"}, r


@check("near-miss surname never joins (Greek/Kreck)")
def t_near_surname():
    r = run_join(["Harley Greek"], ["Harley Kreck"])
    assert not joined_names(r), r


@check("two same-surname candidates stay unresolved (the sister case)")
def t_ambiguous():
    r = run_join(["Katie Smith"], ["Kathryn Smith", "Kate Smith"])
    assert not joined_names(r), r
    assert unresolved_names(r) == {"Katie Smith"}, r


@check("a claimed production row is never joined twice")
def t_no_double_claim():
    r = run_join(["Madison Cowan", "Madi Cowan"], ["Madison Cowan"])
    assert joined_names(r) == {"Madison Cowan"}, r
    assert unresolved_names(r) == {"Madi Cowan"}, r


@check("true freshmen are never surname-anchored")
def t_freshman():
    r = run_join([("Abby Kaminski", "Fr")], ["Abigail Kaminski"])
    assert not joined_names(r), r
    assert r.get("new_or_unplayed") == ["Abby Kaminski"], r


@check("roster order does not change the outcome")
def t_order_independent():
    a = run_join(["Madi Cowan", "Sam Pope"], ["Madison Cowan", "Samantha Pope"])
    b = run_join(["Sam Pope", "Madi Cowan"], ["Samantha Pope", "Madison Cowan"])
    assert joined_names(a) == joined_names(b) == {"Madi Cowan", "Sam Pope"}, (a, b)


def main():
    print("=" * 78)
    print("JOIN INVARIANTS — the surname-anchored pass must not cross two people")
    print("=" * 78)
    failed = []
    for name, fn in CHECKS:
        try:
            fn()
            print("  PASS  %s" % name)
        except AssertionError as e:
            failed.append(name)
            print("  FAIL  %s\n        %s" % (name, str(e)[:300]))

    # ---- NEGATIVE CONTROL ----
    # Reintroduce the bug and assert the guards trip. The bug is NOT a loose
    # given-name test -- loosening that changes nothing here, because the
    # candidate set is anchored on the surname and the mutual-uniqueness guard
    # is structural. The bug is a surname anchor that stops being exact, which
    # is what a plain difflib match over the whole name amounts to. Simulated
    # by collapsing every surname to one token, so surnames match everything
    # and only the given name is left to discriminate.
    print()
    print("  negative control: collapsing the surname anchor in-process...")
    orig = J.parts
    J.parts = lambda f, l: [orig(f, l)[0] if orig(f, l) else "", "SURNAME"]
    try:
        tripped = []
        for name, fn in (("Pyle/Malone", t_different_surname),
                         ("Greek/Kreck", t_near_surname)):
            try:
                fn()
            except AssertionError:
                tripped.append(name)
    finally:
        J.parts = orig

    print("  guards that tripped without an exact surname: %s"
          % (", ".join(tripped) if tripped else "NONE"))
    if len(tripped) < 2:
        print("  -> NEGATIVE CONTROL DID NOT FULLY TRIP. These tests are not proven")
        print("     to catch a loosened surname anchor. Treat the suite as unverified.")
        failed.append("negative control")

    print()
    if failed:
        print("FAILED: %d" % len(failed))
        return 1
    print("ALL %d CHECKS PASS, negative control tripped as expected" % len(CHECKS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
