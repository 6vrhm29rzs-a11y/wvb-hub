#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the newsroom's headline system (2026-09-11).

This is the first feature that CHARACTERISES results rather than displaying
them, which is where R1 has been broken twice. The controls below assert the
two independent mechanisms and, critically, assert WHY the first one exists:
the gate alone demonstrably passes a wrong scoreline.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import newsroom as N  # noqa: E402

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


FIN = {"winner": "Nebraska", "loser": "Baylor", "w_sets": 3, "l_sets": 0,
       "total_sets": 3}


def main():
    print("1. EVERY SHIPPED SHAPE IS STRUCTURALLY SOUND")
    probs = [p for sh in N.ALL_SHAPES for p in N.shape_problems(sh)]
    check("no shape has a structural problem", not probs, probs[:2])
    check("[+] there are shapes to check (not vacuous)",
          len(N.ALL_SHAPES) >= 4, len(N.ALL_SHAPES))
    check("no template carries a literal digit",
          not any(re.search(r"\d", re.sub(r"\{[a-z0-9_]+\}", "", sh.text))
                  for sh in N.ALL_SHAPES))

    print("\n2. A HEADLINE NEVER RENDERS ON MISSING OR FALSE GROUND")
    for miss in ("winner", "w_sets", "l_sets"):
        f = dict(FIN)
        f[miss] = None
        t, _ = N.headline(N.ALL_SHAPES, f)
        check("a missing %-9s produces NO headline, not a partial one"
              % miss, t == "", t)
    sweep = [sh for sh in N.ALL_SHAPES if sh.name == "sweep"][0]
    check("[-] 'sweeps' refuses a match that was not a sweep",
          N.render(sweep, {"winner": "A", "loser": "B", "w_sets": 3,
                           "l_sets": 1, "total_sets": 4}) == "",
          "the verb is licensed by l_sets == 0, not by the author")
    check("[+] ...and does render a real sweep",
          N.render(sweep, FIN) != "")

    print("\n3. EVERY RENDERED HEADLINE PASSES THE INDEPENDENT GATE")
    import digby
    cases = [FIN,
             {"winner": "Texas", "loser": "Stanford", "w_sets": 3,
              "l_sets": 2, "total_sets": 5, "loser_rank": 4},
             {"winner": "Pitt", "loser": "SMU", "w_sets": 3, "l_sets": 1,
              "total_sets": 4}]
    bad = []
    for f in cases:
        t, nm = N.headline(N.ALL_SHAPES, f)
        if not t:
            bad.append(("no headline", f))
            continue
        ok, why = digby.verify(t, [], f)
        if not ok:
            bad.append((t, why))
    check("every case yields a headline that clears the gate", not bad,
          bad[:2])

    print("\n4. WHY THE TEMPLATE SYSTEM EXISTS -- THE GATE ALONE IS NOT ENOUGH")
    # ⚠ MEASURED, and the reason headlines are not free text. The gate asks
    # whether a number is IN THE DATA, not whether it is in the right place.
    licensed = dict(FIN)
    licensed["our_power_rank"] = 1
    ok_bad, _ = digby.verify("Nebraska sweeps Baylor, 3-1", [], licensed)
    check("[+] the gate PASSES a wrong scoreline when the digit is "
          "licensed elsewhere", ok_bad,
          "if this ever fails, the gate got stricter and this rationale "
          "should be re-read -- not deleted")
    ok_ord, _ = digby.verify("wins its seventh straight", [], FIN)
    check("[+] ...and PASSES an ordinal with no such number in the facts",
          ok_ord)
    # the shape system is what stops both: neither string can be produced
    t, _ = N.headline(N.ALL_SHAPES, licensed)
    check("[-] ...while the shapes cannot produce that scoreline",
          t == "Nebraska sweeps Baylor, 3-0", t)

    print("\n5. NEGATIVE CONTROLS ON THE STRUCTURAL CHECK")
    lit = N.Shape("lit", "result", ("winner",), lambda f: True,
                  "{winner} wins 3 straight")
    check("[NEG] a literal digit in a template IS caught",
          any("literal digit" in p for p in N.shape_problems(lit)))
    unk = N.Shape("unk", "result", ("winner",), lambda f: True,
                  "{winner} beats {loser}")
    check("[NEG] a slot with no matching fact IS caught",
          any("not in `needs`" in p for p in N.shape_problems(unk)))
    ordl = N.Shape("ord", "result", ("winner",), lambda f: True,
                   "{winner} takes its seventh")
    check("[NEG] an ordinal in a template IS caught",
          any("ordinal" in p for p in N.shape_problems(ordl)))
    empty = N.Shape("mt", "result", (), lambda f: True, "something happened")
    check("[NEG] a shape declaring no facts IS caught",
          any("declares no facts" in p for p in N.shape_problems(empty)))
    liar = N.Shape("liar", "result",
                   ("winner", "loser", "w_sets", "l_sets"),
                   lambda f: True, "{winner} sweeps {loser}, {w_sets}-{l_sets}")
    check("[NEG] a 'sweeps' shape with no precondition WOULD lie",
          N.render(liar, {"winner": "A", "loser": "B", "w_sets": 3,
                          "l_sets": 2}) == "A sweeps B, 3-2",
          "this is the string the precondition exists to prevent")

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL NEWSROOM GUARDS PASS")


if __name__ == "__main__":
    main()
