#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for RESUME -- the ranking that answers "what have you earned".

WHY IT NEEDS ITS OWN GUARDS. Resume and Power are two numbers that look alike,
sit next to each other, and must never quietly become the same thing. If they
converge, the page shows one opinion twice while claiming to show two -- and
nothing about the display would reveal it. R3 has kept them apart since Phase 3
precisely because merging them is the easy mistake.

Python 3.9 target. Run: python3 scripts/test_resume.py
"""

import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def load(rel):
    p = os.path.join(REPO, rel)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def main():
    print("RESUME GUARDS\n")

    print("1. Wins Above Bubble behaves like a resume, not like a rating")
    import resume_2025 as R

    # A win over a strong opponent must be worth more than over a weak one, and
    # a loss to a weak one must cost more than a loss to a strong one.
    beta, home = 2.5, 0.38
    def bubble_p(z_bubble, z_opp, is_home):
        d = z_bubble - z_opp
        return 1.0 / (1.0 + math.exp(-(beta * d + (home if is_home else -home))))
    zb = 0.9
    p_vs_strong = bubble_p(zb, 2.5, True)
    p_vs_weak = bubble_p(zb, -1.5, True)
    check("beating a strong team is worth more than beating a weak one",
          (1 - p_vs_strong) > (1 - p_vs_weak),
          "(%.3f vs %.3f)" % (1 - p_vs_strong, 1 - p_vs_weak))
    check("losing to a weak team costs more than losing to a strong one",
          p_vs_weak > p_vs_strong, "(%.3f vs %.3f)" % (p_vs_weak, p_vs_strong))
    check("the same opponent is worth more away than at home",
          bubble_p(zb, 0.5, False) < bubble_p(zb, 0.5, True),
          "a bubble team wins less on the road, so beating them there earns more")

    # ⚠ MARGIN MUST NOT ENTER. This is what makes it a different number from
    # POWER, where margin is the whole point and capping it was measured to HURT.
    #
    # ⚠ AND THE FIRST VERSION OF THIS CHECK FAILED ON ITS OWN EXPLANATION. It
    # grepped the source for "margin", which appears three times in the module
    # docstring saying that margin is deliberately ignored. That is the fourth
    # guard in this repository to match its own prose. Strip comments AND string
    # literals with tokenize -- a regex cannot do it, because a docstring is a
    # multi-line string and "#" inside one is not a comment.
    # ⚠ TWO WRONG VERSIONS BEFORE THIS ONE, AND THE POSITIVE CONTROL CAUGHT
    # BOTH.
    #   (a) A regex grep for "margin" failed on the module's own docstring,
    #       which says three times that margin is deliberately ignored. That is
    #       the fourth guard here to match its own prose.
    #   (b) Stripping every STRING token with tokenize removed the docstrings --
    #       and also every dict key, because `g.get("linescores")` is a string
    #       literal too. The check would then have passed no matter what the
    #       code did. The positive control is the only reason that was noticed.
    #
    # What is actually wanted is: remove PROSE, keep DATA ACCESS. ast does
    # exactly that -- it drops comments for free and lets docstring nodes be
    # deleted while every other literal survives.
    import ast as _ast
    src_path = os.path.join(REPO, "scripts", "resume_2025.py")
    tree = _ast.parse(open(src_path, encoding="utf-8").read())
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                             _ast.ClassDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, _ast.Expr)
                    and isinstance(first.value, _ast.Constant)
                    and isinstance(first.value.value, str)):
                node.body = node.body[1:] or [_ast.Pass()]
    code_only = _ast.unparse(_ast.fix_missing_locations(tree))

    check("the resume never reads point-level data",
          "linescores" not in code_only,
          "linescores is the only source of point margins; reading it here "
          "would turn the resume into a power rating")
    # POSITIVE CONTROL: the scan must still be able to SEE the data access it
    # is meant to police. Without this, an over-eager stripper makes the check
    # above pass vacuously -- which is what happened.
    check("...and the scan can still see real data access (positive control)",
          "sets_won" in code_only and "wab" in code_only,
          "the stripper removed too much, so the check above proves nothing")
    # NEGATIVE CONTROL: inject the forbidden access and confirm it is seen.
    check("...and it would catch a real leak (negative control)",
          "linescores" in (code_only + '\ng.get("linescores")'))

    print("\n2. The shipped payload")
    doc = load("data/resume_%d.json" % SEASON)
    if doc is None:
        check("a resume file exists for the season", False, "(missing)")
        return 1
    meta = doc.get("meta") or {}
    if not meta.get("active"):
        check("an inactive resume says WHY, and names the threshold",
              bool(meta.get("why")) and bool(meta.get("min_matches")),
              str(meta)[:120])
        check("...and ships no teams rather than a thin ranking",
              not doc.get("teams"),
              "a resume off a handful of matches is not a thin resume, it is "
              "not a resume (R5)")
        print("\n  (resume not active this season yet -- %d of %d matches)"
              % (meta.get("matches") or 0, meta.get("min_matches") or 0))
    else:
        rows = doc["teams"]
        ranked = [r for r in rows if r.get("rank")]
        check("ranks are 1..N with no gaps or duplicates",
              sorted(r["rank"] for r in ranked) == list(range(1, len(ranked) + 1)))
        check("the rank basis is recorded", meta.get("rank_basis") == "rpi",
              str(meta.get("rank_basis")))
        check("the validation target is recorded",
              "actual_field" in (meta.get("validated_against") or ""))
        check("the circularity caveat is stated, not buried",
              "circular" in (meta.get("circularity_caveat") or ""))
        # WAB must actually vary -- a constant would mean the bubble model
        # collapsed and every schedule looked identical.
        wabs = [r["wab"] for r in rows if r.get("wab") is not None]
        check("wins-above-bubble varies across teams",
              len(set(round(w, 2) for w in wabs)) > 50, "(%d distinct)" %
              len(set(round(w, 2) for w in wabs)))

        print("\n3. RESUME and POWER must not be the same ranking")
        rat = load("data/rating_%d.json" % SEASON) or {}
        pw = dict((r["team"], r.get("composite_rank")) for r in (rat.get("teams") or []))
        pairs = [(r["rank"], pw[r["team"]]) for r in ranked
                 if pw.get(r["team"])]
        if len(pairs) > 50:
            n = len(pairs)
            d2 = sum((a - b) ** 2 for a, b in pairs)
            rho = 1 - 6.0 * d2 / (n * (n * n - 1))
            check("they correlate (both are about being good)", rho > 0.5,
                  "(rho %.3f)" % rho)
            # ⚠ NO INVENTED CEILING ON rho. The first version asserted
            # rho < 0.98 and failed at 0.989 -- but a Spearman over 346 teams is
            # dominated by the broad ordering (both rankings agree that Nebraska
            # is better than Alcorn), so it is nearly 1 even when the two
            # disagree constantly where it matters. A verdict resting on a
            # cutoff I chose has tested nothing (R1).
            #
            # The threshold-free question is whether they would SELECT
            # DIFFERENTLY: do the two top-64s contain the same teams? That is
            # the decision a resume ranking exists to inform.
            top_r = set(r["team"] for r in ranked[:64])
            top_p = set(t for t, k in pw.items() if k and k <= 64)
            diff = len(top_r ^ top_p) // 2
            moved = sum(1 for a, b in pairs if abs(a - b) >= 10)
            check("the two rankings would select a different field",
                  diff > 0,
                  "(identical top-64 -- the page is showing one opinion twice "
                  "while claiming to show two)")
            check("a real number of teams sit in different places", moved >= 10,
                  "(%d teams differ by 10+ places)" % moved)
            print("     (spearman %.3f, %d teams differ by 10+ places, "
                  "%d teams differ between the two top-64s)" % (rho, moved, diff))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL RESUME GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
