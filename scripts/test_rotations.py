#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for rotation derivation from a per-rally serve sequence.

`docs/rotations_finding.md` closed this as impossible. It was right about
ncaa.com and wrong as a general claim: a feed that names the server on every
rally gives rotation order by rule, because a team serves in rotation order.

The load-bearing tests are the two controls. A method that "recovers" a rotation
from any sequence has recovered nothing, so a SHUFFLED sequence must be rejected
-- and a genuine rotation must survive, or the guard is just a refusal.

Python 3.9 target. Run: python3 scripts/test_rotations.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rotations import (parse_plays, serve_turns, derive_rotation,          # noqa: E402
                       positions_when_serving, front_row, setter_rows,
                       opposite_of, serving_six_caveats)

FAILED = []


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


SIX = ["Ann", "Bea", "Cal", "Dee", "Eve", "Fay"]


def _cycle(n, subs=None):
    """A genuine rotation: n turns of the six in order, with optional subs."""
    out = []
    for i in range(n):
        name = SIX[i % 6]
        if subs and (i % 6) in subs and i >= 6:
            name = subs[i % 6]
        out.append(name)
    return out


def test_positive_control_a_true_rotation_is_recovered():
    r = derive_rotation(_cycle(13))
    check(r["rotation"] == SIX, "POSITIVE CONTROL: a true rotation is recovered",
          str(r["rotation"]))
    check(r["complete"] and r["consistent"], "and is marked complete/consistent")


def test_negative_control_a_shuffled_sequence_is_rejected():
    """If this passed, the method would 'find' a rotation in anything."""
    shuffled = ["Ann", "Cal", "Fay", "Bea", "Eve", "Dee",
                "Fay", "Ann", "Dee", "Cal", "Bea", "Eve"]
    r = derive_rotation(shuffled)
    check(not r["consistent"],
          "NEGATIVE CONTROL: a shuffled serve order is rejected", str(r["problems"][:2]))


def test_a_substitute_is_paired_with_the_player_she_replaced():
    r = derive_rotation(_cycle(14, subs={4: "Gil"}))
    check(r["subs"].get("Eve") == ["Gil"],
          "a substitute is paired with the starter whose slot she serves from",
          str(r["subs"]))


def test_a_short_set_is_partial_not_a_rotation():
    r = derive_rotation(["Ann", "Bea", "Cal"])
    check(not r["complete"],
          "fewer than six turns is PARTIAL, never presented as a rotation")
    check(r["rotation"][3] is None, "the unserved slots stay empty, not filled")


def test_court_positions_follow_the_rotation_rule():
    """Position 1 serves; the next to serve stands at 2. Front row is 2, 3, 4."""
    pos = positions_when_serving(SIX, 0)
    check(pos[1] == "Ann" and pos[2] == "Bea" and pos[6] == "Fay",
          "the server is at position 1 and the next server at position 2", str(pos))
    check(front_row(SIX, 0) == ["Bea", "Cal", "Dee"],
          "front row is the three who serve next", str(front_row(SIX, 0)))


def test_setter_is_front_row_in_exactly_three_of_six():
    rows = setter_rows(SIX, "Fay")
    n = sum(1 for r in rows if r["setter_front_row"])
    check(len(rows) == 6, "every rotation is reported", str(len(rows)))
    check(n == 3, "the setter is front row in exactly three rotations", str(n))


def test_opposite_is_three_slots_away():
    check(opposite_of(SIX, "Ann") == "Dee", "the opposite is three slots away")
    check(opposite_of(SIX, "Zoe") is None, "an unknown player has no opposite")


def test_a_libero_slot_is_flagged_not_presented_as_the_starter():
    """The serve order gives the SERVING six. A middle replaced by the libero
    never serves, so her slot names the libero instead -- that must be flagged,
    not rendered as 'the player in rotation 1'."""
    positions = {"Ann": "L", "Bea": "RS", "Cal": "OH",
                 "Dee": "OH", "Eve": "S", "Fay": "S"}
    caveats = serving_six_caveats(SIX, positions)
    check([c["slot"] for c in caveats] == [1],
          "a libero-held slot is flagged", str(caveats))
    check(not serving_six_caveats(SIX, {n: "OH" for n in SIX}),
          "a six of front-row players raises no caveat")


def test_the_serving_team_code_is_read_from_the_line():
    lines = ["[Serve: Meester,Chloe] Kill by Chicoine,Chloe.\tLOU",
             "[Serve: Simon,Kristen] Attack error by Flanagan,Audrey.\tWIS",
             "a line with no serve marker at all\tWIS"]
    pairs = parse_plays(lines)
    check(len(pairs) == 2, "lines without a server are skipped", str(pairs))
    check(pairs[0] == ("Meester,Chloe", "LOU"), "server and team are parsed",
          str(pairs[0]))
    check(serve_turns(pairs, "LOU") == ["Meester,Chloe"],
          "turns are filtered to one team")


def test_consecutive_rallies_are_one_turn():
    pairs = [("Ann", "X"), ("Ann", "X"), ("Ann", "X"), ("Bea", "X")]
    check(serve_turns(pairs, "X") == ["Ann", "Bea"],
          "a server holding serve counts once, not once per point")


def main():
    for fn in (test_positive_control_a_true_rotation_is_recovered,
               test_negative_control_a_shuffled_sequence_is_rejected,
               test_a_substitute_is_paired_with_the_player_she_replaced,
               test_a_short_set_is_partial_not_a_rotation,
               test_court_positions_follow_the_rotation_rule,
               test_setter_is_front_row_in_exactly_three_of_six,
               test_opposite_is_three_slots_away,
               test_a_libero_slot_is_flagged_not_presented_as_the_starter,
               test_the_serving_team_code_is_read_from_the_line,
               test_consecutive_rallies_are_one_turn):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all rotation invariants pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
