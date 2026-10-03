#!/usr/bin/env python3
"""Derived absence flags must not be made of spelling, DNP listings or
truncated boxes (mail 036). Synthetic team, real build()."""
import collections
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import availability as A  # noqa: E402

FAIL = []


def check(name, ok):
    print("  %-66s %s" % (name, "ok" if ok else "FAIL"))
    if not ok:
        FAIL.append(name)


def line(sets, k=5, acted=True):
    return {"sets": float(sets), "pts": float(k) if acted else 0.0, "pos": "OH",
            "acted": acted}


def run(case_merge=True, zero_unknown=True, trunc_skip=True):
    """Six regulars over 9 matches. Match 4: star listed zero-action.
    Match 6: star spelled in a different case. Match 8: truncated box
    (1 of 3 sets) missing the star."""
    A._spell.clear()
    regs = ["Ann Ace", "Bea Bee", "Cy Sea", "Di Dee", "Em Emm", "Flo Eff"]
    by = collections.defaultdict(dict)
    meta = {}
    for i in range(9):
        gid = "g%d" % i
        meta[gid] = {"teams": {"T": "Team"}, "epoch": i, "nsets": 3}
        for nm in regs:
            disp = nm
            if nm == "Ann Ace" and i == 6:
                disp = "ANN ACE"
            key = A._ident(disp) if case_merge else disp
            A._spell["T"][key][disp] += 1
            ln = line(3, k=15 if nm == "Ann Ace" else 5)
            if nm == "Ann Ace" and i == 4:
                ln = line(3, acted=False)
                if not zero_unknown:
                    continue            # control: treat DNP listing as missing row
            if nm == "Ann Ace" and i == 8:
                continue                # truncated box omits her
            if i == 8:
                ln = line(1)
            by[gid][key] = ln
        if i == 8 and not trunc_skip:
            meta[gid]["nsets"] = None
    orig = A.load
    A.load = lambda: ({"T": by}, meta)
    try:
        return A.build()
    finally:
        A.load = orig


out = run()
names = [(r["game_id"], a["name"]) for r in out["flagged"] for a in r["absent"]]
check("no flag from a case variant of the same player", not any(g == "g6" for g, _ in names))
check("a zero-action listing is not flagged absent", not any(g == "g4" for g, _ in names))
check("a truncated box is not judged", not any(g == "g8" for g, _ in names))
check("[NEG] un-merged spelling DOES flag (control)",
      any(g == "g6" for g, _ in [(r["game_id"], 0) for r in run(case_merge=False)["flagged"]]))
check("[NEG] a missing row where the DNP was DOES flag (control)",
      any(r["game_id"] == "g4" for r in run(zero_unknown=False)["flagged"]))
check("[NEG] judging the truncated box DOES flag (control)",
      any(r["game_id"] == "g8" for r in run(trunc_skip=False)["flagged"]))
print("FAILED: %s" % FAIL if FAIL else "ALL AVAILABILITY FLAG CHECKS HOLD")
sys.exit(1 if FAIL else 0)
