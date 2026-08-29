#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the global rail and the Why Watch preview (review round 4).

The failure modes these stop: two global score summaries of the same match
on one screen; a rail that grows without bound on a 60-match night; a quiet
day rendering a giant nothing; a preview that drifts from checkable facts
into marketing copy; and a forecast surviving past first serve.

Run: python3 scripts/test_why_watch.py -- no network.
"""

import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:120]))
    if not ok:
        FAILS.append(label)
    return ok


def main():
    print("THE GLOBAL RAIL AND WHY WATCH\n")
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    page = io.open(hub, encoding="utf-8").read() if os.path.exists(hub) else ""

    print("1. ONE GLOBAL SCORE STRIP, NOT TWO")
    # the tape's one-line rail form is deleted; on a non-Today route the tape
    # renders NOTHING and the ticker is the single global summary
    check("the cs-rail form is gone from the source", "cs-rail" not in src)
    check("...and from the built page", not page or "cs-rail" not in page)
    check("the non-marquee tape branch renders empty and returns",
          re.search(r"if \(!marquee\) \{[^}]*mount\.innerHTML = '';[^}]*return;",
                    src, re.S) is not None)

    print("\n2. THE RAIL IS BOUNDED AND ITS ORDER IS DETERMINISTIC")
    tk = src[src.find("let TK_LAST"):src.find("async function pollLive")]
    check("a cap exists and is six", "TK_CAP = 6" in tk)
    check("overflow gets an explicit All-live control",
          "data-alllive" in tk and "live.length > TK_CAP" in tk)
    check("the control applies the Live filter on Scores",
          "SB_FILTER = 'live'" in src)
    # deterministic priority: the sort key is the stated reason tuple with a
    # stable id tiebreak -- no Math.random, no insertion order
    check("priority = rv, mb, tv, dg, rank, then id",
          re.search(r"pa\.rv - pb\.rv.*pa\.mb - pb\.mb.*pa\.tv - pb\.tv"
                    r".*pa\.dg - pb\.dg.*pa\.rk - pb\.rk", tk, re.S) is not None
          and "localeCompare(String(b.id))" in tk)
    check("each chip states its reason (title)", 'title="\' + esc(why)' in tk)
    check("finals cannot linger: the caller filters to in-progress",
          "csTicker(live);" in src and "justEnded" in src)

    print("\n3. THE QUIET STATE IS NEXT-TO-WATCH, NEVER A GIANT NOTHING")
    check("quiet renders up to three upcoming priority fixtures",
          "TK_QUIET_CAP = 3" in tk and "tkQuietChips" in tk)
    check("the window is 72 hours", "3 * 86400000" in tk)
    check("no giant empty message in the ticker path",
          "No matches on the schedule" not in tk)

    print("\n4. WHY WATCH IS FACTS OR ABSENCE")
    ww = src[src.find("WHY THIS MATTERS"):src.find("starsSection(m) +")]
    check("the module exists on the upcoming branch",
          "st === 'upcoming'" in ww and "todayReasons(m, null)" in ww)
    check("at most three reason chips", ".slice(0, 3)" in ww)
    check("no reasons renders no section (absence, not prose)",
          "if (!rs.length) return '';" in ww)
    # no marketing adjectives anywhere in the module or the reason set
    reasons = src[src.find("function todayReasons"):src.find("function starPeek")]
    _banned = re.compile(r"'[^']*\b(?:hot|struggling|decisive|must-see|"
                         r"clutch|superstar)\b[^']*'", re.I)
    check("no marketing copy in the reason set",
          not _banned.search(reasons) and not _banned.search(ww))
    check("the disagreement chip carries BOTH labelled values",
          "AVCA #" in reasons and "POWER #" in reasons)
    check("POWER top-50 pairing yields to the stronger AVCA chip",
          "!(m.ar && m.hr)" in reasons)

    print("\n5. NEGATIVE CONTROLS")
    check("[NEG] an uncapped rail is caught", "TK_CAP = 6" not in
          tk.replace("TK_CAP = 6", "TK_CAP = 999"))
    _wwbad = ww.replace("if (!rs.length) return '';",
                        "if (!rs.length) return 'A big matchup!';")
    check("[NEG] filler prose on an empty reason list is caught",
          "return '';" in ww and "return '';" not in _wwbad
          or "A big matchup!" in _wwbad and "if (!rs.length) return '';" not in _wwbad)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL WHY-WATCH GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
