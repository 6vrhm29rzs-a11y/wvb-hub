#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the participation radar (2026-09-13).

Cody: "the site should flag players playing vs players not playing... i
can't be the catch for everything."

⚠⚠ THE REGRESSION THAT MATTERS IS THE FIRST RUN OF THIS FEATURE. It reported
Brooklyn DeLeye -- 22% of Kentucky's points -- as not having appeared since
Sep 9. She played on the 12th (14 kills) and the 13th. The feed had simply
changed her spelling mid-season, "DeLeye" to "Deleye", and the radar keyed on
the printed name, so one player became two: one who vanished and one who
arrived. 114 of the first 349 rows were that artifact. A false absence claim
about a named athlete is the worst thing this feature can emit, so the
identity fold is fixtured here in both directions.

The other rule these guards hold: what this produces is PARTICIPATION, never
availability. A player missing from a box may be rested, suspended,
ineligible or omitted by a scorer, and no row here may become a status or
carry a diagnosis.

Run: python3 scripts/test_radar.py
"""

import io
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from test_scoreboard_density import fn as js_block  # noqa: E402

PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
FAILS = []


def check(label, ok, detail=""):
    print("  %-68s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)


def main():
    season = int(os.environ.get("WVB_SEASON", "2026"))
    import build_hub as B
    import player_rating as PR

    print("1. THE IDENTITY FOLD -- A RE-SPELLING IS NOT A DISAPPEARANCE")
    pairs = [("Brooklyn DeLeye", "Brooklyn Deleye"),
             ("Ana Burilović", "Ana Burilovic"),
             ("O'Hara Smith", "OHara Smith")]
    for a, b in pairs:
        check("%r and %r are one identity" % (a, b),
              PR.nkey(a) == PR.nkey(b), (PR.nkey(a), PR.nkey(b)))
    check("[NEG] two genuinely different players stay separate",
          PR.nkey("Taylor Williams") != PR.nkey("Taylor Stanley"))
    check("the page's fold agrees with the chain's",
          B._nkey_letters("Brooklyn DeLeye") == PR.nkey("Brooklyn DeLeye"))

    print("\n2. THE ARTIFACT, AND WHAT IT REFUSES TO SAY")
    p = os.path.join(REPO, "data", "participation_radar_%d.json" % season)
    if not os.path.exists(p):
        check("the radar artifact exists", False, p)
        return 1
    doc = json.load(io.open(p, encoding="utf-8"))
    rows = doc.get("players") or []
    check("it carries players", len(rows) > 0, len(rows))
    check("it states what it is NOT, in the artifact itself",
          "not an availability status" in
          (doc.get("what_this_is_not") or "").lower(),
          doc.get("what_this_is_not"))
    banned = ("injur", "out for", "hurt", "surgery", "illness", "concussion",
              "suspended for", "ill ")
    # ⚠ SCAN THE CLAIMS, NOT THE DENIAL. The first version scanned the
    # whole document and matched "not an injury report" -- the sentence that
    # exists precisely to forbid the thing being searched for. Eleventh time
    # a check here has matched the prose describing it. A diagnosis in a
    # player ROW would be a lie about a person; in the meta it is required.
    blob = json.dumps(rows).lower()
    hits = [w for w in banned if w in blob]
    check("[NEG] no diagnosis or injury word in any player ROW", not hits,
          hits)
    check("...and the document denies being an injury report in its own "
          "words", "injury" in (doc.get("what_this_is_not") or "").lower())
    check("every row names its evidence", all(
        r.get("last_seen_gid") and r.get("missed_gids") for r in rows))
    check("every row carries the share it represents", all(
        isinstance(r.get("share_of_team_points"), float) for r in rows))
    check("the ranking rule is stated as a display ordering",
          "feeds nothing" in json.dumps(doc.get("rules") or {}))

    print("\n3. THE REAL REGRESSION: DeLEYE MUST NOT BE ON THE LIST")
    # she has played in Kentucky's most recent counted matches
    ky = [r for r in rows if r.get("team") == "Kentucky"]
    bad = [r for r in ky if PR.nkey(r.get("player") or "")
           == PR.nkey("Brooklyn DeLeye")]
    check("[NEG] Kentucky's leading scorer is not reported as missing",
          not bad, bad[:1])

    print("\n4. A ZERO-ACTION LISTING IS NOT AN APPEARANCE")
    src = io.open(os.path.join(REPO, "scripts",
                               "participation_radar.py"), encoding="utf-8").read()
    check("the DNP convention is handled explicitly",
          "acts > 0" in src and "zero-action" in src.lower())
    check("the sample floor is stated, not fitted",
          "MIN_MATCHES_BEFORE" in src and "feeds a rating" in src)

    print("\n5. THE PAGE SAYS PARTICIPATION, NEVER AVAILABILITY")
    page = io.open(PAGE, encoding="utf-8").read()
    out = js_block(page, "tdOutbox")
    check("the team block exists", bool(out))
    check("it says the reason is not in the data",
          "reason is not in the data" in out)
    check("it denies being an injury report in so many words",
          "never an injury report" in out)
    for w in ("<b>OUT</b>", "'OUT'", "injured", "sidelined"):
        check("[NEG] it never renders %r" % w, w not in out)
    check("the squad wall marks a face rather than labelling a person",
          "sqout" in page and "NOT IN A BOX" in page)

    print("\n6. IT RUNS WITHOUT BEING ASKED")
    lr = io.open(os.path.join(REPO, "scripts", "local_refresh.py"),
                 encoding="utf-8").read()
    check("the local refresh runs it", "participation_radar.py" in lr)
    for wf in ("refresh.yml", "daily.yml"):
        t = io.open(os.path.join(REPO, ".github", "workflows", wf),
                    encoding="utf-8").read()
        check("%s runs it too" % wf, "participation_radar.py" in t)

    print("\n%s" % ("ALL RADAR GUARDS PASS" if not FAILS else
                    "FAILED: %d\n   - %s" % (len(FAILS), "\n   - ".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
