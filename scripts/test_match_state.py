#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the six-state match model and what each state may display.

⚠ WHAT THIS PROTECTS. A match page is read while something is happening, and
the failure mode is not a crash -- it is a table of zeroes that looks like a
result, or a "leader" derived from a payload that carries no players. Every
check here is about not displaying above the state the source supports.

The endpoint behaviour these rules are built on is MEASURED and written down in
docs/live_endpoint_audit.md. Two states are covered by real data (upcoming,
final_with_box); the rest are covered by fixtures, and that limit is asserted
here rather than glossed.

Python 3.9 target. Run: python3 scripts/test_match_state.py
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)
import match_state as MS  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def page():
    p = os.path.join(REPO, "Cody", "START-HERE.html")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def main():
    print("MATCH STATE GUARDS\n")

    print("1. ALL SIX STATES RESOLVE, AND ONLY FROM EVIDENCE")
    cases = [
        ("upcoming", MS.resolve(feed={"gameState": "pre", "away_sets": "",
                                      "home_sets": ""})),
        ("live_score_only", MS.resolve(feed={"gameState": "I", "away_sets": 1,
                                             "home_sets": 0})),
        ("live_with_team_stats",
         MS.resolve(feed={"gameState": "I", "away_sets": 1, "home_sets": 0},
                    box={"teams": [1, 2]})),
        ("final_box_pending", MS.resolve(feed={"gameState": "final",
                                               "away_sets": 3, "home_sets": 1})),
        ("final_with_box", MS.resolve(feed={"gameState": "final"},
                                      box={"teams": [1, 2], "players": [1]})),
        ("unavailable", MS.resolve(feed={}, fetch_failed=True)),
    ]
    for want, got in cases:
        check("%-22s resolves" % want, got["state"] == want, got["state"])
    check("[+] all six are distinct", len(set(c[1]["state"] for c in cases)) == 6)

    print("\n2. A FINAL IS NEVER UPCOMING")
    # ⚠ THE SEAM THIS PROJECT HAS ALREADY BEEN BITTEN BY. A match that ended on
    # the scoreboard but is not yet in the archive must not fall through to
    # "Coming up" with its score showing.
    for feed in ({"gameState": "final"}, {"currentPeriod": "FINAL"},
                 {"period": "Final"}, {"state": "final"},
                 {"gameState": "I", "currentPeriod": "FINAL"}):
        st = MS.resolve(feed=feed)["state"]
        check("%-38s is not upcoming" % json.dumps(feed)[:38],
              st != MS.UPCOMING and st.startswith("final"), st)
    check("a stored final with no feed is still final",
          MS.resolve(feed=None, stored={"final": True})["state"]
          .startswith("final"))

    print("\n3. AN EMPTY SCORE IS NOT ZERO")
    # Measured: the scoreboard serves score:'' before first serve.
    check("'' is absent, not 0", MS._score("") is None)
    check("' ' is absent too", MS._score("  ") is None)
    check("'0' really is zero", MS._score("0") == 0)
    check("a pre match with empty scores is upcoming",
          MS.resolve(feed={"gameState": "pre", "away_sets": "",
                           "home_sets": ""})["state"] == MS.UPCOMING)

    print("\n4. NOTHING DISPLAYS ABOVE ITS STATE")
    for st in (MS.UPCOMING, MS.UNAVAILABLE):
        c = MS.CAPABILITIES[st]
        check("%-12s shows no score, stats or players" % st,
              not any(c.values()), str(c))
    c = MS.CAPABILITIES[MS.LIVE_SCORE]
    check("live_score_only may show a score but NOT stats",
          c["score"] and c["sets"] and not c["team_stats"]
          and not c["player_lines"], str(c))
    c = MS.CAPABILITIES[MS.FINAL_PENDING]
    check("final_box_pending may show the score but NOT a player table",
          c["score"] and not c["team_stats"] and not c["player_lines"], str(c))
    # ⚠ CAPABILITY IS A CEILING, NOT A PROMISE.
    r = MS.resolve(feed={"gameState": "final"}, box={"teams": [1, 2],
                                                     "players": []})
    check("[-] a box score with no player rows still forbids a player table",
          r["state"] == MS.FINAL_BOX and not r["caps"]["player_lines"], str(r))
    r = MS.resolve(feed={"gameState": "I", "away_sets": 1, "home_sets": 0},
                   box={"teams": [1, 2], "players": [1, 2]})
    check("[-] a LIVE match never unlocks player lines",
          r["state"] == MS.LIVE_STATS and not r["caps"]["player_lines"], str(r))

    print("\n5. A STALE LIVE PAYLOAD NEVER OVERWRITES A FINAL")
    # A poller that lags can hand back an in-progress row for a match that has
    # since ended. The strongest evidence wins, never the most recent.
    r = MS.resolve(feed={"gameState": "I"}, stored={"final": True})
    check("stored-final beats a live feed row", r["state"].startswith("final"),
          r["state"])
    r = MS.resolve(feed={"gameState": "I", "currentPeriod": "FINAL"})
    check("a feed reporting both live and FINAL is final",
          r["state"].startswith("final"), r["state"])

    print("\n6. THE PAGE USES THE SHARED TABLE, NOT ITS OWN RULES")
    h = page()
    if not h:
        print("  (no built page -- skipping)")
    else:
        check("the state table is injected from Python",
              "const MSTATE = {" in h and '"caps"' in h)
        m = re.search(r"const MSTATE = (\{.*?\});\n", h, re.S)
        tbl = json.loads(m.group(1)) if m else {}
        check("[+] it carries every state", set(tbl.get("caps", {})) ==
              set(MS.CAPABILITIES), str(sorted(tbl.get("caps", {}))))
        for st, caps in MS.CAPABILITIES.items():
            check("   %-22s matches Python exactly" % st,
                  tbl.get("caps", {}).get(st) == caps,
                  str(tbl.get("caps", {}).get(st)))
        check("the page asks the table what it may draw", "function mCaps(" in h)
        check("...and the box section is gated on BOTH state and data",
              "caps.player_lines && typeof boxHTML" in h)
        check("the empty-score trap is handled in the page too",
              "function mNum(" in h and "!v.trim()" in h)

        print("\n7. A FINAL WITHOUT A BOX SCORE SHOWS NO TABLE")
        check("there is an explicit pending block",
              'class="mpend"' in h)
        check("...that says the box score is not published yet",
              "has not been published yet" in h)
        check("[-] and no zero-filled fallback exists",
              "0</td><td>0</td><td>0" not in h)

        print("\n8. EVERY ENTRY POINT USES ONE CANONICAL ROUTE")
        check("there is a single route helper", "function matchRoute(" in h)
        check("...and the click handler matches ANY data-match element",
              "closest('[data-match]')" in h)
        check("...with keyboard parity",
              "e.key !== 'Enter' && e.key !== ' '" in h)
        # every surface that renders a match must carry data-match
        check("the shared row carries it", 'data-match="' in h)
        check("a team's own result carries it",
              "g.gid ? ' data-match=\"'" in h)
        # ⚠ NO SECOND ADDRESS FOR A MATCH.
        alt = re.findall(r"'#/(?:scores|match-desk)/'\s*\+", h)
        check("[-] no caller builds a match URL by hand",
              len(alt) <= 1, "%d hand-built match URLs" % len(alt))

    print("\n8b. THE SCORE RIBBON KEEPS ITS COLUMN COUNT")
    # ⚠ A MEASURED LAYOUT BUG, AND IT HIT EXACTLY THE TEAMS WE JUST SURFACED.
    # `.rbside` is a four-column grid; logo() returns '' for a team we hold no
    # crest for, so the row had three children, every cell shifted one column
    # left, and the name rendered inside the 34px crest track -- three lines
    # tall, with the score stranded beside it instead of at the right edge.
    # Every non-Division-I opponent was affected.
    if h:
        check("the crest slot is emitted even with no crest",
              "logo(name) || '<span class=\"rbnologo\"></span>'" in h)
        check("...and that placeholder holds the column open",
              ".rbside .rbnologo{" in h and "width:34px" in h)
        m4 = re.search(r"\.rbside\{[^}]*grid-template-columns:([^;]+);", h)
        cols = (m4.group(1).strip() if m4 else "")
        check("[+] the grid really does declare four columns",
              len(cols.split()) == 4, cols)
        check("the name cell can shrink and wrap",
              ".rbside .rbnm{min-width:0" in h)

    print("\n9. OFFICIAL BOX-SCORE TOTALS RECONCILE")
    # The archive's per-player rows must sum to the team totals the page shows.
    hub = page()
    if hub:
        mb = re.search(r"const BOXES = (\{.*?\});\n", hub, re.S)
        B = json.loads(mb.group(1)) if mb else {}
        checked = 0
        bad = []
        for gid, rows in B.items():
            by = {}
            for r in rows:
                t = by.setdefault(r["team"], {"k": 0, "e": 0, "ta": 0})
                t["k"] += r.get("k") or 0
                t["e"] += r.get("e") or 0
                t["ta"] += r.get("ta") or 0
            for t, v in by.items():
                checked += 1
                # ⚠ HITTING PERCENTAGE IS NEGATIVE WHEN ERRORS EXCEED KILLS,
                # and that is real volleyball, not corruption. The first real
                # match day produced three: Montreat 10K-14E (-.063),
                # Southern U. 23-24, NJIT 22-27 -- overmatched teams erring
                # more than they kill. The old lower bound of 0 was a
                # plausibility rule invented from the typical case, the same
                # mistake as validating a set score against 25: it failed
                # correct data the first time the sport produced the tail.
                # The true range of (K-E)/TA is -1..1.
                if v["ta"] and not (-1 <= (v["k"] - v["e"]) / v["ta"] <= 1):
                    bad.append("%s %s" % (gid, t))
                if v["k"] > v["ta"]:
                    bad.append("%s %s kills>attempts" % (gid, t))
        check("[+] there are box scores to reconcile", checked > 0,
              "%d team-boxes" % checked)
        check("kills never exceed attempts; hit%% stays in range", not bad,
              str(bad[:3]))
        print("     (%d team box scores checked)" % checked)

    print("\n10. THE AUDIT IS WRITTEN DOWN AND ITS LIMITS ARE STATED")
    ad = os.path.join(REPO, "docs", "live_endpoint_audit.md")
    check("the endpoint audit exists", os.path.exists(ad))
    if os.path.exists(ad):
        t = open(ad, encoding="utf-8").read()
        check("it records the 502 before first serve", "502" in t)
        check("it records the empty-string score", "score: ''" in t
              or "score:''" in t or "`''`" in t)
        # ⚠ THE LIMIT MUST BE STATED, NOT IMPLIED.
        check("it says the live states are not yet measured",
              "not yet measured" in t.lower() or "NOT yet measured" in t)
        check("...and repeats the standing rule about claiming live stats",
              "may claim live team or player statistics" in t)

    # ── THE PAGE MUST NOT OVERRULE THE SERVER'S STATE ──────────────────
    print("\nTHE CLIENT HONOURS EVERY STATE THE SERVER NAMES")
    # ⚠ THIS SHIPPED WRONG AND CODY CAUGHT IT ON THE SEASON'S FIRST NIGHT.
    # matchState6() said it trusted the server's state6 and then honoured
    # exactly TWO of its five values; anything else fell through to
    # `if (live) return 'live_score_only'`, so merely APPEARING on today's
    # scoreboard made a match live. At 4:45pm Pacific, with first serve at 5:00
    # and 6:00, Florida at Nebraska and SMU at Penn St. both rendered LIVE while
    # the feed said state:"pre", state6:"upcoming", "Not started." for both.
    hub = page()
    if hub:
        i = hub.find("function matchState6(")
        j = hub.find("\nfunction ", i + 1)
        body = hub[i:j] if i >= 0 else ""
        check("matchState6 exists", bool(body))
        check("it honours any state the server names, not a hand-picked pair",
              "MSTATE.caps[live.state6]" in body,
              "an allow-list of two values is how 'upcoming' became 'live'")
        # ⚠ NEGATIVE CONTROL: the old shape must be gone, not merely joined by
        # the new one. Leaving it in place would let the fall-through win again.
        check("[NEG] the two-value allow-list is gone",
              "live.state6 === 'live_with_team_stats' ||" not in body,
              "the old branch still decides before the new one")
        # and the renderers that consume it must ask, not test truthiness
        wc = hub.find("const watchCard = x =>")
        wbody = hub[wc:wc + 1400] if wc >= 0 else ""
        check("a watch card asks the state model, not whether a feed row exists",
              "matchState(m, live) === 'live'" in wbody,
              "being on today's scoreboard is not being in progress")
        check("...and the 'live now' reason chip does the same",
              "if (matchState(m, live) === 'live') {" in hub)

    print("\n11. THREE SETS IS A WIN BY RULE, WHATEVER THE STATE FIELDS SAY")
    # ⚠ SEEN LIVE, 2026-08-28, FIU-Merrimack: the feed carried away_sets "3"
    # while state was still "live" and period still "3RD SET" -- the inverse
    # of the documented period-flips-first lag. The tape showed the impossible
    # "LIVE - 3RD SET" beside a 3-0 tally. A side with three sets has won by
    # rule; the match is over the moment either tally reaches three. Asserted
    # on the shared mOver() and on the poller's isOver, the two over-tests the
    # R4 audit found.
    src = open(os.path.join(REPO, "scripts", "build_hub.py"),
               encoding="utf-8").read()
    mo = src[src.find("function mOver"):]
    mo = mo[:mo.find("\n}") + 2]
    check("mOver treats a tally of three as over",
          "away_sets) >= 3" in mo and "home_sets) >= 3" in mo,
          "the feed can lag state AND period past the final rally")
    check("...through the null-safe reader",
          "mNum(live.away_sets)" in mo,
          "an empty-string tally must not be coerced to a number")
    check("the poller's isOver carries the same rule",
          "+g.away_sets >= 3" in src and "+g.home_sets >= 3" in src)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL MATCH STATE GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
