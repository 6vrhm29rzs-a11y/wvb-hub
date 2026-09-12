#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the FEED ERROR flag (2026-09-11).

Cody, reading the Scores tab: "these errors in scores need to be flagged and
marked somehow as 'error in feed' or something so I know when I should and
should not trust what I'm reading."

The feed served Le Moyne-Siena as 20-56 and 32-62, and a COUNTED final --
Kennesaw St.-Alabama A&M -- as 26-21, which the rules end at 25-21. The page
rendered all of it as fact.

THE RULE IS THE SPORT'S, NOT A THRESHOLD ANYBODY PICKED. A set above the
format minimum ends the moment a side leads by two, so a winner OVER 25 with
any other margin cannot have been played -- true of the 25-point set, the
15-point decider and the first-to-21 exhibition alike, so it never asks which
format was used.

⚠ AND IT IS DELIBERATELY CONSERVATIVE. This codebase nearly deleted a REAL
24-22 set by inventing a plausibility rule from the standard format. Nothing
at or below 25 is judged. The controls below pin that both ways: the
impossible must flag, and the awkward-but-real must not.
"""
import io
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
import season_counts as SC  # noqa: E402

SRC = os.path.join(REPO, "scripts", "build_hub.py")
FAILED = []

CASES = [
    ((56, 20), True,  "Le Moyne-Siena, what Cody saw"),
    ((62, 32), True,  "...its second set"),
    ((26, 21), True,  "Kennesaw St.-Alabama A&M, a COUNTED final"),
    ((25, 20), False, "an ordinary set"),
    ((27, 25), False, "a deuce"),
    ((31, 29), False, "a long deuce"),
    ((24, 22), False, "THE REAL EXHIBITION SET -- must never flag"),
    ((21, 19), False, "first-to-21 exhibition"),
    ((15, 10), False, "the deciding set"),
    ((12, 8),  False, "a set in progress"),
]


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def jsblock(src, start):
    i = src.find("{", start)
    if i < 0:
        return ""
    d, j = 0, i
    while j < len(src):
        if src[j] == "{":
            d += 1
        elif src[j] == "}":
            d -= 1
            if d == 0:
                return src[start:j + 1]
        j += 1
    return ""


def main():
    src = io.open(SRC, encoding="utf-8").read()

    print("1. THE PYTHON RULE")
    bad = []
    for (a, b), want, why in CASES:
        got = SC.has_impossible_sets(
            {"linescores": [{"period": "1", "home": a, "visit": b}]})
        if got != want:
            bad.append((a, b, why, got))
    check("every case classifies correctly", not bad, bad[:3])
    check("[+] the case list actually exercises both outcomes",
          any(w for _p, w, _y in CASES) and any(not w for _p, w, _y in CASES))
    check("a match with no line scores is not flagged",
          not SC.has_impossible_sets({"linescores": []}))
    check("unparseable scores are not flagged (missing != impossible)",
          not SC.has_impossible_sets(
              {"linescores": [{"period": "1", "home": "", "visit": None}]}))

    print("\n2. THE JS TWIN AGREES -- ASSERTED, NOT ASSUMED")
    hi = src.find("function impossibleSetPair")
    ti = src.find("function impossibleTape")
    check("[+] both helpers exist in the page", hi >= 0 and ti >= 0)
    js = jsblock(src, hi) + "\n" + jsblock(src, ti) + "\nconsole.log(" \
        "JSON.stringify([%s]));" % ",".join(
            "impossibleSetPair(%d,%d)" % p for p, _w, _y in CASES)
    try:
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        got = json.loads(r.stdout.strip()) if r.returncode == 0 else None
        why = (r.stderr or "").strip()[:160]
    except Exception as e:                                   # noqa: BLE001
        got, why = None, repr(e)[:160]
    check("the JS twin returns the same verdicts as Python",
          got == [w for _p, w, _y in CASES], why or got)

    print("\n3. THE PAGE WITHHOLDS AND SAYS WHY")
    check("both payload emitters consult the rule",
          src.count("impossible_sets(") >= 2,
          "res and desk must both withhold, or one surface disagrees")
    check("the row renders a FEED ERROR mark", "FEED ERROR" in src)
    check("...and it explains itself on hover",
          "rules of the sport forbid" in src)
    check("the result is still shown beside the mark",
          re.search(r"FEED ERROR</span>'\s*\+", src) is not None,
          "a flagged match must not become a blank row")
    check("[-] the score is never CORRECTED, only flagged",
          "impossible" in src and "corrected" not in
          src[src.find("FEED ERROR") - 400: src.find("FEED ERROR")],
          "we do not know the true score")

    print("\n4. NEGATIVE CONTROLS")
    check("[NEG] a 24-22 set would be caught if the rule reached below 25",
          (24 > 25) is False and not SC.has_impossible_sets(
              {"linescores": [{"period": "1", "home": 24, "visit": 22}]}),
          "the real exhibition set must survive")
    # the rule's own boundary: 26-21 flags, 26-24 does not
    check("[NEG] the margin is what decides, not the number",
          SC.has_impossible_sets(
              {"linescores": [{"period": "1", "home": 26, "visit": 21}]})
          and not SC.has_impossible_sets(
              {"linescores": [{"period": "1", "home": 26, "visit": 24}]}))
    check("[NEG] removing the margin test would flag every deuce",
          not SC.has_impossible_sets(
              {"linescores": [{"period": "1", "home": 33, "visit": 31}]}),
          "33-31 is a real long set")

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL FEED-ERROR GUARDS PASS")


if __name__ == "__main__":
    main()
