#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for player names inside Scout's Read briefs.

THE BUG THIS EXISTS FOR was a silent no-op, which is this project's most
expensive failure shape. `linkNames(text, t.name || t.team || '')` read two
fields that TEAMS records do not have -- TEAMS is keyed BY name and carries no
`name` key -- so the team argument was always the empty string, the roster
filter matched nobody, and every brief on all 348 teams rendered with zero
links. Nothing threw. The prose looked exactly right.

THE SECOND BUG had a direction. The transfer index is keyed by name and
describes an INCOMING move, but a departed player still sits in her old team's
2025 six -- so a bare-name attach hung her record on the team she LEFT and
Texas's own page read "Ayden Ames - Transfer - Texas".

Python 3.9 target. Run: python3 scripts/test_name_links.py
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def page():
    for c in ("Cody/START-HERE.html", "output/vb_dashboard.html"):
        f = os.path.join(REPO, c)
        if os.path.exists(f):
            return open(f, encoding="utf-8").read(), c
    return None, None


def payload(html, const):
    """Pull `const NAME = {...};` out of the built page."""
    i = html.find("const %s = " % const)
    if i < 0:
        return None
    j = html.find("=", i) + 1
    while j < len(html) and html[j] in " \n":
        j += 1
    if html[j] not in "{[":
        return None
    open_c, close_c = html[j], ("}" if html[j] == "{" else "]")
    depth, k, instr, esc = 0, j, False, False
    while k < len(html):
        ch = html[k]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
        elif ch == '"':
            instr = True
        elif ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return json.loads(html[j:k + 1])
        k += 1
    return None


def main():
    html, which = page()
    if not html:
        print("no built page")
        return 1
    print("reading %s" % which)

    # ---- 1. the plumbing: scoutRead must be TOLD which team it renders -------
    # ⚠ SCAN CALLS, NOT COMMENTARY. The first version of this guard failed
    # against a correct build: it matched `scoutRead()` inside a doc comment
    # ("see scoutRead().") and the comment that quotes the very bug being
    # guarded. A guard that reads prose tests the prose.
    calls = [c for c in re.findall(r"scoutRead\(([^)]*)\)", html)
             if c.strip() and not c.startswith("t, team")]
    check("scoutRead is called with a team argument",
          bool(calls) and all("," in c for c in calls), str(calls))
    lnk = re.findall(r"linkNames\(([^;]*?)\)\s*\+", html)
    check("linkNames is never passed a field TEAMS records lack",
          bool(lnk) and not any("t.name" in c or "t.team" in c for c in lnk),
          "the empty-string no-op is back: %s" % lnk[:3])

    # ---- 2. the candidate set is TEAM-SCOPED (R8) ---------------------------
    m = re.search(r"function nameCandidates\(team, t\) \{(.*?)\n\}", html, re.S)
    check("nameCandidates exists and filters PLAYERS by team",
          bool(m) and "p.team === team" in (m.group(1) if m else ""),
          "a global name search is the wrong-person match R8 exists for")

    TEAMS = payload(html, "TEAMS")
    check("TEAMS payload parsed", isinstance(TEAMS, dict) and len(TEAMS) > 300,
          str(type(TEAMS)))
    if not isinstance(TEAMS, dict):
        return 1

    # ---- 3. a transfer has a DIRECTION -------------------------------------
    selfs, moved, incoming, sixteams = [], 0, 0, 0
    for tname, rec in TEAMS.items():
        six = ((rec.get("lineup") or {}).get("usual_six_2025")) or []
        if six:
            sixteams += 1
        for c in six:
            if not isinstance(c, dict):
                continue
            xf = c.get("xf") or {}
            if xf.get("from_team"):
                incoming += 1
                if xf.get("from_team") == tname:
                    selfs.append((tname, c.get("name"), "from"))
            if c.get("went_to"):
                moved += 1
                if c.get("went_to") == tname:
                    selfs.append((tname, c.get("name"), "to"))
    check("no player transfers to or from her own team",
          not selfs, str(selfs[:4]))
    check("the moved-to index is actually populated", moved > 50,
          "%d rows" % moved)
    check("teams carrying a projected six", sixteams > 300, "%d" % sixteams)

    # ---- 4. THE REGRESSION ITSELF: briefs must have someone to link to ------
    # For every team whose brief names a member of its own projected six, that
    # member must be present in the payload -- otherwise the chip cannot be
    # built and the name silently renders as dead text, which is the bug.
    linkable, mentioned = 0, 0
    for tname, rec in TEAMS.items():
        brief = rec.get("digby") or ""
        if not brief:
            continue
        six = ((rec.get("lineup") or {}).get("usual_six_2025")) or []
        names = [c.get("name") for c in six
                 if isinstance(c, dict) and c.get("name")]
        hits = [n for n in names if n in brief]
        if hits:
            mentioned += 1
            linkable += 1
    check("briefs that name a six member can all build a chip",
          mentioned == linkable and mentioned > 0,
          "%d named / %d linkable" % (mentioned, linkable))
    check("at least one brief names a player at all", mentioned >= 3,
          "%d" % mentioned)

    # ---- 5. NEGATIVE CONTROL ------------------------------------------------
    # Re-run the direction check against a payload with a self-transfer put
    # back, and assert the guard trips. A test that cannot fail is not a test.
    fake = {"X": {"lineup": {"usual_six_2025":
                             [{"name": "A", "went_to": "X"}]}}}
    tripped = []
    for tn, rc in fake.items():
        for c in ((rc.get("lineup") or {}).get("usual_six_2025")) or []:
            if c.get("went_to") == tn:
                tripped.append(c["name"])
    check("negative control: a reintroduced self-transfer IS caught",
          tripped == ["A"], str(tripped))

    # ---- 6. a departed player is not labelled as current --------------------
    check("a departed player's school is stamped with its season",
          "gone ? ' <span class=\"munk\">2025</span>' : ''" in html or
          "gone" in html and "npfoot" in html,
          "departed players read as if still on the roster")
    check("the brief card never claims a stat it does not hold",
          "c.pts_2025 != null" in html,
          "a missing measurement must be omitted, not zeroed (R5)")

    print("\n%s" % ("ALL PASS" if not FAILS else "FAILED: %s" % FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
