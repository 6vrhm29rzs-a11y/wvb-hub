#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for player identity and the app shell's routing.

⚠ THE DEFECT THIS EXISTS FOR WAS LIVE AND MEASURED. box_and_players() keyed a
player by team plus the name AS THE FEED SPELLED IT, so one player became two
whenever a scorer's capitalisation moved between matches:

    Kentucky  Brooklyn DeLeye / Brooklyn Deleye     1 match each
    Kentucky  Kassie O'Brien  / Kassie O'brien      1 match each
    Texas     Abby Vander Wal / Abby Vander wal     1 match each

Three duplicate identities across 152 rows. Every number was computed correctly
and attributed to half a person -- the failure mode R8 exists for, arriving
from the opposite direction: not a wrong merge, a missing one.

Python 3.9 target. Run: python3 scripts/test_player_identity.py
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def nk(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def page():
    for c in ("Cody/START-HERE.html", "output/vb_dashboard.html"):
        p = os.path.join(REPO, c)
        if os.path.exists(p):
            return open(p, encoding="utf-8").read(), c
    return None, None


def main():
    print("PLAYER IDENTITY AND APP SHELL GUARDS\n")
    h, which = page()
    if not h:
        print("  (no built page -- skipping)")
        return 0
    print("  reading %s\n" % which)

    m = re.search(r"const PLAYERS = (\[.*?\]);\n", h, re.S)
    P = json.loads(m.group(1)) if m else []
    check("the player payload is present", bool(P), "0 rows")

    print("\n1. ONE AGGREGATE PER CANONICAL (team, name)")
    seen = {}
    dupes = []
    for p in P:
        k = (p.get("team"), nk(p.get("name")))
        if k in seen:
            dupes.append("%s / %s vs %s" % (k[0], seen[k], p.get("name")))
        seen[k] = p.get("name")
    check("no duplicate canonical player identities", not dupes,
          "; ".join(dupes[:3]))
    check("[+] ...and there are players to be wrong about", len(P) > 50,
          "%d rows" % len(P))

    print("\n2. ONE ROW PER GAME ID IN A MATCH LOG")
    bad = []
    for p in P:
        gids = [g.get("gid") for g in (p.get("games") or [])]
        if len(gids) != len(set(gids)):
            bad.append("%s %s" % (p.get("team"), p.get("name")))
    check("no player's log repeats a game id", not bad, "; ".join(bad[:3]))

    print("\n3. THE THREE MEASURED REGRESSIONS")
    for team, name, want_spelling in (
            ("Kentucky", "brooklyndeleye", "Brooklyn DeLeye"),
            ("Kentucky", "kassieobrien", "Kassie O'Brien"),
            ("Texas", "abbyvanderwal", "Abby Vander Wal")):
        rows = [p for p in P if p.get("team") == team and nk(p.get("name")) == name]
        check("%s / %s is ONE player" % (team, want_spelling),
              len(rows) == 1, "%d rows" % len(rows))
        if len(rows) == 1:
            r = rows[0]
            check("   ...spelled as the official roster spells it",
                  r.get("name") == want_spelling, repr(r.get("name")))
            check("   ...and keeps BOTH matches",
                  len(r.get("games") or []) >= 2,
                  "%d games" % len(r.get("games") or []))

    print("\n4. OFFICIAL CLASS YEAR REACHES THE PROFILE")
    import build_hub as BH
    idx, ambiguous = BH.roster_identity_index()
    check("the roster identity index is populated", len(idx) > 3000,
          "%d entries" % len(idx))
    # ⚠ AMBIGUITY IS NOT MERGED SILENTLY. If two different roster players in one
    # team normalise to the same key they are two people the canonical key
    # cannot separate -- they are recorded, not joined.
    check("no team has two roster players sharing one canonical key",
          not ambiguous, str(ambiguous[:2]))
    gw = [p for p in P if p.get("team") == "Kentucky"
          and nk(p.get("name")) == "georgiawatson"]
    check("Georgia Watson is on the page", len(gw) == 1, "%d rows" % len(gw))
    if gw:
        check("...and shows Sophomore", gw[0].get("class") == "Sophomore",
              repr(gw[0].get("class")))
    bd = [p for p in P if p.get("team") == "Kentucky"
          and nk(p.get("name")) == "brooklyndeleye"]
    if bd:
        check("Brooklyn DeLeye carries an official class",
              bool(bd[0].get("class")), repr(bd[0].get("class")))
    withclass = [p for p in P if p.get("class")]
    print("     (%d of %d players carry an official class year)"
          % (len(withclass), len(P)))
    check("most players joined to the roster", len(withclass) > len(P) * 0.5,
          "%d of %d" % (len(withclass), len(P)))

    print("\n5. THE APP SHELL")
    prim = re.findall(r'<button role="tab"[^>]*data-v="([a-z0-9]+)"', h)
    check("exactly five primary destinations", len(prim) == 5, str(prim))
    check("...and they are the daily five",
          prim == ["desk", "scores", "rankings", "teams", "ballot"], str(prim))
    more = re.findall(r'<button role="menuitem"[^>]*data-v="([a-z0-9]+)"', h)
    check("the reference tools moved to More, none lost",
          set(more) >= {"leaders", "players", "standings", "bracket", "schedule"},
          str(more))
    check("Digby's Top 25 is a RANKINGS view, not a top-level tab",
          "top25" not in prim and 'data-r="digby"' in h)
    check("the More menu is a real menu (aria)",
          'aria-haspopup="true"' in h and 'role="menu"' in h)

    print("\n6. ROUTING")
    for frag in ("function route()", "addEventListener('hashchange'",
                 "function go(", "ROUTE_OF_VIEW", "renderCrumbs"):
        check("the router defines %s" % frag, frag in h)
    check("every nav control routes through go()",
          "go(routeFor(b.dataset.v))" in h)
    check("a player route carries where it came from", "?from=" in h)
    check("...and a team page offers the way back",
          "Back to " in h and "backlink" in h)
    check("scroll is reset on a NEW destination only",
          "ROUTE_POP" in h and "scrollTo({ top: 0 })" in h)

    print("\n6b. THE ROUTE WINS OVER THE SEARCH BOX")
    # ⚠ A LIVE DEFECT, FOUND BY LOOKING RATHER THAN BY A FAILING TEST.
    # renderPlayers() ends with `if (rows.length === 1) showPlayer(rows[0])`.
    # renderPlayerDetail() called it AFTER painting the routed player, so
    # arriving at #/players/kentucky/kassie-o-brien while the search box still
    # held "Brooklyn DeLeye" showed Kassie's URL and breadcrumb above
    # Brooklyn's card. Nothing threw; each half looked right on its own.
    m2 = re.search(r"function renderPlayerDetail\(p\) \{(.*?)\n\}", h, re.S)
    body = m2.group(1) if m2 else ""
    check("renderPlayerDetail exists", bool(body))
    if body:
        i_render = body.find("renderPlayers")
        i_show = body.rfind("showPlayer(p)")
        check("the routed player is painted AFTER the directory re-renders",
              i_show > i_render >= 0,
              "showPlayer at %d, renderPlayers at %d" % (i_show, i_render))
        check("...and the search box is made to agree with the route",
              "q.value = p.name" in body)
    check("[+] the auto-open convenience still exists to be raced",
          "if (rows.length === 1) showPlayer(rows[0]);" in h,
          "the guard above is pointless if this was simply deleted")

    print("\n7. NO SHELL RECIPE RENDERS IN THE PAGE")
    for bad_s in ("export ANTHROPIC", "sk-ant-", "ANTHROPIC_API_KEY"):
        check("the page never prints %r" % bad_s, bad_s not in h)
    check("an unavailable chat states it plainly",
          "not connected on this local build" in h)
    check("...and disables its composer", "q.disabled = true" in h)

    print("\n8. DEAD UI REMOVED")
    check("no per-team 'trend unavailable' block renders",
          h.count('class="trend') == 0, "%d found" % h.count('class="trend'))
    check("the archive states its limit ONCE instead",
          h.count('class="histnote"') == 1)
    check("search counts use singular/plural language",
          "' matching player'" in h and "' matching players'" in h)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL PLAYER IDENTITY AND SHELL GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
