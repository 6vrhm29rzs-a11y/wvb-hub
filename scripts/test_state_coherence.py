#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One match, one answer, on every surface.

⚠ THE FAILURE THIS EXISTS FOR, FOUND ON THE LIVE SITE. Florida-Nebraska
finished 0-2. The masthead rail said FINAL, the Scoreboard said FINAL, the
match detail said FINAL -- and "Your next watches" still offered the same
fixture as "TODAY 5:00 PM PT". A finished match cannot be a NEXT watch, and a
reader who sees one view contradict another stops trusting all of them.

Two independent causes, both of the same shape:

  * `if (liveOf(m)) w += 100` -- the truthiness mistake. A feed row exists for
    every match on today's card, finished ones included, so a completed match
    collected the live bonus and floated to the TOP of the watch list.
  * `done` filtered on `m.d < today`, so a match that finished a few hours ago
    belonged to no section at all. Nothing removed it from the watch list
    because nothing claimed it.

The rule this file enforces: every surface resolves state through
matchState()/matchState6(), and nothing selects a match for a
forward-looking list without asking.

Python 3.9 target. Run: python3 scripts/test_state_coherence.py
"""

import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-68s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def page():
    for c in ("Cody/START-HERE.html", "output/vb_dashboard.html"):
        f = os.path.join(REPO, c)
        if os.path.exists(f):
            return io.open(f, encoding="utf-8").read()
    return ""


def main():
    h = page()
    if not h:
        print("no built page")
        return 1

    print("1. NOTHING DECIDES 'LIVE' BY ASKING WHETHER A FEED ROW EXISTS")
    # ⚠ A feed row exists for EVERY match on today's scoreboard, whatever its
    # state. Testing it for truthiness is how an upcoming match rendered LIVE
    # before first serve, and how a finished one stayed a next-watch.
    bad = []
    for pat, why in (
            (r"if \(liveOf\(m\)\) w \+= ", "the watch list weights by mere presence"),
            (r"live \? ' islive'", "a card styles itself live by presence"),
            (r"live \? '<i class=\"cs-dot\"></i>LIVE", "a card labels itself live by presence"),
            (r"if \(live\) out\.unshift", "a reason chip fires on presence")):
        if re.search(pat, h):
            bad.append(why)
    check("no surface treats a feed row as proof of being live", not bad,
          "; ".join(bad))

    print("\n2. A FINISHED MATCH CANNOT BE A FORWARD-LOOKING WATCH")
    check("the watch list drops a final outright",
          "if (st === 'final') return null;" in h,
          "a completed match can still be offered as something to watch")
    check("...and the live bonus is applied only to a live match",
          "if (st === 'live') w += 100;" in h)
    check("today's finals are claimed by the results section",
          "m.d <= today && matchState(m, liveOf(m)) === 'final'" in h,
          "with `m.d < today` a match finishing today belongs to no section, "
          "so nothing takes it out of the watch list")

    print("\n3. EVERY SURFACE RESOLVES THROUGH THE SHARED MODEL")
    for fn, label in (("function matchState6", "the resolver exists"),
                      ("MSTATE.caps[live.state6]",
                       "it honours any state the server names")):
        check(label, fn in h)
    check("the Scoreboard is refreshed when live data lands",
          "if (typeof renderScoreboard === 'function') renderScoreboard();" in h,
          "it was the one view the poll never told, so a match could finish "
          "and sit there labelled Scheduled")

    print("\n4. NEGATIVE CONTROLS -- each reintroduced fault must be caught")
    cases = [
        ("watch list weights by presence again",
         h.replace("if (st === 'live') w += 100;", "if (liveOf(m)) w += 100;"),
         lambda d: not re.search(r"if \(liveOf\(m\)\) w \+= ", d)),
        ("a final is allowed back into the watch list",
         h.replace("if (st === 'final') return null;", ""),
         lambda d: "if (st === 'final') return null;" in d),
        ("today's finals excluded from results again",
         h.replace("m.d <= today && matchState", "m.d < today && matchState"),
         lambda d: "m.d <= today && matchState(m, liveOf(m)) === 'final'" in d),
        ("the poll stops refreshing the Scoreboard",
         h.replace("if (typeof renderScoreboard === 'function') renderScoreboard();", ""),
         lambda d: "if (typeof renderScoreboard === 'function') renderScoreboard();" in d),
    ]
    for label, doc, still_ok in cases:
        check("[NEG] %s is caught" % label, not still_ok(doc),
              "the guard above would pass against the broken version")

    print("\n%s" % ("ALL STATE COHERENCE GUARDS PASS" if not FAILS
                    else "FAILED: %s" % FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
