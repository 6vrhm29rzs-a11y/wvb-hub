#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score crawl_aq.py's text matcher against conferences whose answer is KNOWN.

WHY. crawl_aq.py returns a mechanism for 22 conferences and labels every one
UNVERIFIED. "Unverified" is honest but it is not a measurement -- it does not
say whether the rows are 90% right or worthless, and the difference decides
whether they may touch the field projector.

Claude-app confirmed six conferences by research. crawl_aq.py deliberately does
not crawl those, so they are an untouched HELD-OUT SET: run the same matcher
against them and the accuracy is measurable rather than asserted.

RESULT WHEN FIRST RUN (2026-08-11): 0 of 6 correct. Five returned NOT FOUND,
and the one that produced a verdict was WRONG -- ACC called TOURNAMENT when the
confirmed answer is REGULAR_SEASON. So the 22 crawled rows carry no
demonstrated information and MUST NOT be wired into project_field.py.

HONEST CONFOUND, stated because it cuts against the conclusion: five of the six
failed at the URL level, not the matcher level -- these are big-conference sites
whose paths differ from the mid-major template in PATHS. So this measures the
whole pipeline, and only ACC directly tests the matcher. That is still 0 for 1
on the matcher, and 1 for 6 on finding the page at all. Neither number supports
using the output.

Python 3.9 target.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl_aq import fetch, TOURN, REGSEA, PATHS  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQ = os.path.join(REPO, "data", "raw", "2026", "aq_mechanism_2026.json")

# Answer confirmed by Claude-app research; site from the conference itself.
TRUTH = {
    "Big Ten": ("bigten.org", "TOURNAMENT"),
    "Pac-12": ("pac-12.com", "TOURNAMENT"),
    "SEC": ("secsports.com", "TOURNAMENT"),
    "ACC": ("theacc.com", "REGULAR_SEASON"),
    "Big 12": ("big12sports.com", "REGULAR_SEASON"),
    "Mountain West": ("themw.com", "TOURNAMENT"),
}


def classify(host):
    for path in PATHS:
        for scheme in ("https://www.", "https://"):
            html, _st = fetch(scheme + host + path)
            if not html:
                continue
            t, r = bool(TOURN.search(html)), bool(REGSEA.search(html))
            if t or r:
                return (("TOURNAMENT" if t and not r else
                         "REGULAR_SEASON" if r and not t else "AMBIGUOUS"),
                        scheme + host + path)
    return None, None


def main():
    print("=" * 78)
    print("AQ MATCHER VALIDATION — held-out set, six confirmed conferences")
    print("=" * 78)
    ok = wrong = notfound = 0
    detail = {}
    for conf, (host, truth) in TRUTH.items():
        got, src = classify(host)
        if got is None:
            notfound += 1
            verdict = "NOT FOUND"
        elif got == truth:
            ok += 1
            verdict = "match"
        else:
            wrong += 1
            verdict = "*** WRONG ***"
        detail[conf] = {"truth": truth, "matcher": got, "verdict": verdict,
                        "source": src}
        print("  %-14s truth=%-14s matcher=%-14s %s"
              % (conf, truth, got or "-", verdict))

    n = len(TRUTH)
    print()
    print("  correct %d of %d · wrong %d · page not found %d" % (ok, n, wrong, notfound))
    decided = ok + wrong
    if decided:
        print("  accuracy where the matcher produced a verdict: %d of %d"
              % (ok, decided))
    print()
    # Verdict built from the counts, never authored ahead of them (R1).
    usable = decided >= 3 and ok == decided
    print("  -> %s" % ("matcher reproduces known answers; rows may be used as "
                       "UNVERIFIED evidence"
                       if usable else
                       "matcher does NOT reproduce known answers. The crawled "
                       "rows carry no demonstrated information and must not be "
                       "wired into project_field.py."))

    # Stamp the result onto the crawl output so the file cannot be mistaken for
    # data later. This project has been bitten by neutral-looking artifacts that
    # nothing in them said were stale.
    if os.path.exists(AQ):
        doc = json.load(open(AQ))
        doc["meta"]["validation"] = {
            "held_out_set": sorted(TRUTH),
            "correct": ok, "wrong": wrong, "page_not_found": notfound,
            "of": n,
            "usable_for_projector": bool(usable),
            "note": ("Same matcher scored against six conferences whose answer "
                     "Claude-app confirmed independently. Rows below are "
                     "UNVERIFIED and, at this accuracy, are NOT evidence."),
        }
        json.dump(doc, open(AQ, "w"), indent=1)
        print("  stamped validation onto %s" % AQ)
    return 0


if __name__ == "__main__":
    sys.exit(main())
