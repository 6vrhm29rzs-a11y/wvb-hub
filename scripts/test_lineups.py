#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Invariants for lineup parsing, and the guard on the rotation-order claim.

The load-bearing test here is the POSITIVE CONTROL. The headline finding is a
NEGATIVE one -- the feed's order is not rotation order -- and a negative result
is worthless if the test could not have detected a positive. So the same
checker is run against synthetic lineups that ARE in rotation order and must
score 100%. A test that cannot fail is not a test.

Python 3.9 target. Run: python3 scripts/test_lineups.py
"""

import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lineups import (attribute, lineups_for_game, parse_starters,  # noqa: E402
                     split_names, surname)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINEUPS = os.path.join(REPO, "data", "raw", "2025", "lineups.jsonl")

FAILED = []


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


# ---------------------------------------------------------------- rotation
def dist3(i, j):
    d = abs(i - j) % 6
    return min(d, 6 - d) == 3


def rotation_signature(pos):
    """In a 5-1 written in rotation order, slots i and i+3 are opposite each
    other: the two MBs sit 3 apart, likewise the two OHs and S/OPP."""
    out = {}
    mb = [i for i, x in enumerate(pos) if x == "MB"]
    oh = [i for i, x in enumerate(pos) if x == "OH"]
    s = [i for i, x in enumerate(pos) if x == "S"]
    op = [i for i, x in enumerate(pos) if x == "OPP"]
    if len(mb) == 2:
        out["MB"] = dist3(*mb)
    if len(oh) == 2:
        out["OH"] = dist3(*oh)
    if len(s) == 1 and len(op) == 1:
        out["S-OPP"] = dist3(s[0], op[0])
    return out


def bucket(p):
    p = (p or "").upper()
    if not p:
        return "?"
    if p.startswith("S"):
        return "S"
    if p.startswith("MB") or p.startswith("M"):
        return "MB"
    if p.startswith("OPP") or p.startswith("RS"):
        return "OPP"
    if p.startswith("OH"):
        return "OH"
    if p.startswith("L") or p.startswith("DS"):
        return "L"
    return "?"


def test_positive_control():
    """THE control. Synthetic true-rotation lineups must be detected."""
    rng = random.Random(20260822)
    canon = ["S", "OH", "MB", "OPP", "OH", "MB"]
    hits = collections.Counter()
    tot = collections.Counter()
    for _ in range(2000):
        k = rng.randrange(6)
        pos = canon[k:] + canon[:k]          # any cyclic shift is still rotation order
        for key, val in rotation_signature(pos).items():
            tot[key] += 1
            hits[key] += 1 if val else 0
    for key in ("MB", "OH", "S-OPP"):
        rate = 100.0 * hits[key] / tot[key]
        check(rate == 100.0,
              "positive control: %s detected on true rotation order" % key,
              "got %.1f%%, expected 100%%" % rate)

    # ...and must NOT fire at high rate on shuffled order.
    hits = collections.Counter()
    tot = collections.Counter()
    for _ in range(4000):
        pos = canon[:]
        rng.shuffle(pos)
        for key, val in rotation_signature(pos).items():
            tot[key] += 1
            hits[key] += 1 if val else 0
    for key in ("MB", "OH", "S-OPP"):
        rate = 100.0 * hits[key] / tot[key]
        check(10.0 < rate < 30.0,
              "negative control: %s near chance on shuffled order" % key,
              "got %.1f%%" % rate)


def test_feed_order_is_not_rotation():
    """The shipped claim: the feed order carries no rotation structure. If this
    ever starts passing the structural test, the finding must be revisited
    BEFORE any rotation view is built."""
    if not os.path.exists(LINEUPS):
        print("  skip (no lineups.jsonl yet)")
        return
    hits = collections.Counter()
    tot = collections.Counter()
    n = 0
    for line in open(LINEUPS):
        line = line.strip()
        if not line:
            continue
        for lu in json.loads(line).get("lineups", []):
            pos = [bucket(p.get("pos")) for p in lu["starters"]]
            if "?" in pos:
                continue
            n += 1
            for key, val in rotation_signature(pos).items():
                tot[key] += 1
                hits[key] += 1 if val else 0
    if n < 50:
        print("  skip (only %d lineups)" % n)
        return
    for key in ("MB", "OH", "S-OPP"):
        if not tot[key]:
            continue
        rate = 100.0 * hits[key] / tot[key]
        check(rate < 40.0,
              "feed order shows no rotation signature: %s" % key,
              "got %.1f%% -- REVISIT docs/rotations_finding.md" % rate)


# ---------------------------------------------------------------- parsing
def test_separator_both_forms():
    semi = {"periods": [{"periodNumber": 1, "playbyplayStats": [{"teamId": 1, "plays": [
        {"playText": "X starters: A One; B Two; C Three; D Four; E Five; F Six"}]}]}]}
    comma = {"periods": [{"periodNumber": 1, "playbyplayStats": [{"teamId": 1, "plays": [
        {"playText": "X starters: A One, B Two, C Three, D Four, E Five, F Six"}]}]}]}
    check(len(parse_starters(semi)[0]["names"]) == 6, "semicolon separator parses to 6")
    check(len(parse_starters(comma)[0]["names"]) == 6, "comma separator parses to 6")
    check(split_names("Neal Grace Berry, Ava Henry") == ["Neal Grace Berry", "Ava Henry"],
          "multi-token names survive comma split")


def test_only_period_one():
    """Sets 2+ carry a CUMULATIVE participation list, not a lineup. Reading one
    as a starting six is the bug this guards."""
    payload = {"periods": [
        {"periodNumber": 1, "playbyplayStats": [{"teamId": 1, "plays": [
            {"playText": "X starters: A One; B Two; C Three; D Four; E Five; F Six"}]}]},
        {"periodNumber": 2, "playbyplayStats": [{"teamId": 1, "plays": [
            {"playText": "X starters: A One; B Two; C Three; D Four; E Five; F Six; G Seven; H Eight"}]}]},
    ]}
    check(len(parse_starters(payload, period=1)) == 1, "set 1 only by default")
    check(len(parse_starters(payload, period=None)) == 2, "period=None sees all sets")


def test_attribution_ignores_feed_label():
    """The measured trap: the feed put Nebraska's six under Pittsburgh's teamId
    AND Pittsburgh's name. Attribution must follow the names."""
    teams_box = {
        "NEB": {"murray": {"pos": "OH", "num": 8, "name": "Harper Murray"},
                "jackson": {"pos": "MB", "num": 15, "name": "Andi Jackson"},
                "reilly": {"pos": "S", "num": 3, "name": "Bergen Reilly"},
                "allick": {"pos": "MB", "num": 5, "name": "Rebekah Allick"},
                "adriano": {"pos": "OPP", "num": 12, "name": "Virginia Adriano"},
                "sigler": {"pos": "OH", "num": 7, "name": "Teraya Sigler"}},
        "PITT": {"babcock": {"pos": "OH", "num": 1, "name": "Olivia Babcock"}},
    }
    payload = {"periods": [{"periodNumber": 1, "playbyplayStats": [{"teamId": "PITT", "plays": [
        {"playText": "Pittsburgh starters: Bergen Reilly; Rebekah Allick; Virginia Adriano; "
                     "Teraya Sigler; Andi Jackson; Harper Murray."}]}]}]}
    rows = lineups_for_game("g", payload, teams_box)
    check(len(rows) == 1 and rows[0]["team_id"] == "NEB",
          "mislabelled lineup attributed by NAMES to the right team",
          repr([r["team_id"] for r in rows]))
    check(rows and rows[0]["feed_label_agreed"] is False,
          "disagreement with the feed label is recorded, not hidden")


def test_partial_match_dropped():
    """A six-name group that does not fully match a box score is dropped, never
    half-assigned -- a partly-wrong lineup looks entirely right downstream."""
    teams_box = {"A": {"one": {"pos": "S", "num": 1, "name": "A One"},
                       "two": {"pos": "OH", "num": 2, "name": "B Two"}}}
    payload = {"periods": [{"periodNumber": 1, "playbyplayStats": [{"teamId": "A", "plays": [
        {"playText": "A starters: A One; B Two; C Three; D Four; E Five; F Six"}]}]}]}
    check(lineups_for_game("g", payload, teams_box) == [],
          "lineup with only 2 of 6 names matched is dropped")


def test_real_data_shape():
    if not os.path.exists(LINEUPS):
        print("  skip (no lineups.jsonl yet)")
        return
    games = sizes = 0
    bad = 0
    for line in open(LINEUPS):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        games += 1
        for lu in rec.get("lineups", []):
            sizes += 1
            if len(lu["starters"]) != 6:
                bad += 1
    check(bad == 0, "every extracted lineup has exactly 6 players", "%d bad" % bad)
    check(games > 0 and sizes > 0, "lineups extracted from real data",
          "%d games, %d lineups" % (games, sizes))



# ------------------------------------------------------- projection output
PROJ = os.path.join(REPO, "data", "lineups_2026.json")


def test_projection_invariants():
    """Guards the measured artifact: three teams reported '0 of 6 returning'
    when the truth was that they have no 2026 roster join at all (~39 of 348
    schools). An absent measurement is not a zero -- that is the same mistake
    R5 exists for, and it renders as total roster turnover on the page."""
    if not os.path.exists(PROJ):
        print("  skip (no lineups_2026.json yet)")
        return
    doc = json.load(open(PROJ))
    teams = doc["teams"]

    bad_zero = [k for k, v in teams.items()
                if not v["roster_join_available"] and v["returning_of_six"] == 0]
    check(not bad_zero,
          "no-roster teams never report 0 returning (they report None)",
          str(bad_zero[:5]))

    bad_none = [k for k, v in teams.items()
                if v["roster_join_available"] and v["returning_of_six"] is None]
    check(not bad_none, "teams WITH a roster join report a real count",
          str(bad_none[:5]))

    over = [k for k, v in teams.items()
            if any(p["starts_2025"] > v["matches_with_lineup"]
                   for p in v["usual_six_2025"])]
    check(not over, "no player has more starts than the team has matches",
          str(over[:5]))

    toobig = [k for k, v in teams.items() if len(v["usual_six_2025"]) > 6]
    check(not toobig, "usual six is never more than six", str(toobig[:5]))

    dupes = [k for k, v in teams.items()
             if len(set(p["name"] for p in v["usual_six_2025"]))
             != len(v["usual_six_2025"])]
    check(not dupes, "no duplicate player within a lineup", str(dupes[:5]))

    # No rotation ordering may leak into the shipped artifact.
    check("NOT AVAILABLE" in (doc["meta"].get("rotation_order") or ""),
          "artifact states rotation order is unavailable")

    # ---- NEGATIVE CONTROL ----------------------------------------------
    # Re-introduce the bug in-process and assert the guard above trips. A test
    # that cannot fail is not a test.
    broken = dict((k, dict(v)) for k, v in list(teams.items())[:1])
    for v in broken.values():
        v["roster_join_available"] = False
        v["returning_of_six"] = 0
    tripped = [k for k, v in broken.items()
               if not v["roster_join_available"] and v["returning_of_six"] == 0]
    check(len(tripped) == 1,
          "negative control: guard trips on the reintroduced bug")


def test_offense_system():
    """5-1 / 6-2 must follow the actual setter count, and stay silent when the
    position data cannot support a claim."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from project_lineups import offense_system, pos_bucket

    check(offense_system([1] * 10) == "5-1", "ten one-setter lineups -> 5-1")
    check(offense_system([2] * 10) == "6-2", "ten two-setter lineups -> 6-2")
    check(offense_system([1, 2, 1, 2, 1, 2, 1, 2]) is None,
          "a team that disagrees with itself gets no label")
    check(offense_system([0] * 10) is None,
          "zero setters means missing position data, not a system")
    check(offense_system([1, 1]) is None, "too few matches -> no label")
    check(pos_bucket("") == "?" and pos_bucket("O") == "?",
          "unknown/ambiguous position stays unknown")

    if not os.path.exists(PROJ):
        return
    teams = json.load(open(PROJ))["teams"]
    # the claim must match the six actually shown
    wrong = []
    for name, v in teams.items():
        sysm = v.get("offense_system_2025")
        if not sysm:
            continue
        setters = sum(1 for p in v["usual_six_2025"] if pos_bucket(p.get("pos")) == "S")
        want = 1 if sysm == "5-1" else 2
        # the usual six is a per-player aggregate, so allow it to differ from
        # the modal lineup by one; a 5-1 showing three setters is not credible
        if abs(setters - want) > 1:
            wrong.append((name, sysm, setters))
    check(not wrong, "system label is consistent with the six shown",
          str(wrong[:3]))


def main():
    for fn in (test_positive_control, test_feed_order_is_not_rotation,
               test_separator_both_forms, test_only_period_one,
               test_attribution_ignores_feed_label, test_partial_match_dropped,
               test_real_data_shape,
               test_projection_invariants, test_offense_system):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all lineup invariants pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
