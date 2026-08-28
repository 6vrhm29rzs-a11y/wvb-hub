# -*- coding: utf-8 -*-
"""Guards for the Team Dossier -- the reorganised team page.

The dossier is a POST-RENDER DOM reorganisation: `teamDossier()` takes the
sections the existing renderer already produced and files them into six tabbed
panels, then assembles an Overview that did not exist before. That design was
chosen so no rendering branch could be silently dropped -- but it means the
failure mode is a section landing in NO panel and vanishing from the page.
Nothing about that is visible: the page still renders, just without the part.

So the guards here assert the two things the reorganisation can break --
every group is reachable and nothing is orphaned -- plus the promises the
Overview makes about what it shows and how it shows it.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "scripts", "build_hub.py")
PAGE = os.path.join(ROOT, "Cody", "START-HERE.html")

FAIL = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAIL.append(name)


def main():
    src = io.open(SRC, encoding="utf-8").read()

    print("dossier structure")

    # --- 1. every group in TD_GROUPS has a mapping, and vice versa ---------
    m = re.search(r"const TD_GROUPS = (\[.*?\]);", src, re.S)
    check("TD_GROUPS is declared", m is not None)
    groups = re.findall(r"\['([a-z]+)'", m.group(1)) if m else []
    check("six groups", len(groups) == 6, groups)

    # TD_MAP is an ARRAY of [regex, group] pairs, not an object -- an earlier
    # version of this guard matched it as `{...}`, found no targets, and
    # therefore passed on an empty set. A test that cannot fail is not a test.
    m2 = re.search(r"const TD_MAP = \[(.*?)\n\];", src, re.S)
    check("TD_MAP is declared", m2 is not None)
    mapped = set(re.findall(r",\s*'([a-z]+)'\]", m2.group(1))) if m2 else set()
    check("TD_MAP targets were actually parsed", len(mapped) >= 4, sorted(mapped))
    unknown = mapped - set(groups)
    check("every TD_MAP target is a real group", not unknown, sorted(unknown))
    # every group except the assembled Overview must be reachable by some rule
    # or by the fallback, or its tab can never appear
    unreachable = set(groups) - mapped - {"overview", "numbers"}
    check("every group is reachable from a rule", not unreachable,
          sorted(unreachable))

    # --- 2. the fallback group must exist ---------------------------------
    # tdGroupOf() falls through to a default; a default naming a group that is
    # not in TD_GROUPS means panels[...] is undefined and .appendChild throws,
    # which blanks the whole team view.
    for fb in re.findall(r"\?\s*tdGroupOf\(el\)\s*:\s*'([a-z]+)'", src):
        check("fallback group '%s' exists" % fb, fb in groups)

    # --- 3. TD_GROUPS/TD_MAP must be declared BEFORE first use ------------
    # ⚠ THIS PROJECT HAS HIT THE TEMPORAL DEAD ZONE SEVEN TIMES. A top-level
    # `const` read before its declaration does not read as undefined -- it
    # THROWS, and a throw inside boot renders a blank view with no error the
    # reader can see. A `typeof` guard does not help either.
    for const in ("TD_GROUPS", "TD_MAP", "POSFULL"):
        decl = src.find("const %s" % const)
        if decl < 0:
            check("%s declared" % const, False)
            continue
        # first use inside a function body that boot can reach
        uses = [x.start() for x in re.finditer(r"\b%s\b" % const, src)]
        first = min(uses)
        check("%s declared at or before first mention" % const, first >= decl,
              "first use %d, decl %d" % (first, decl))

    # --- 3b. the idempotence check must test the WORK, not just a stamp ----
    # ⚠ `box.dataset.dossier` lives on the #teamcard element, which survives a
    # re-render; the panels and nav live in its innerHTML, which does not. A
    # guard that trusted the stamp alone returned early on team -> player ->
    # Back and handed the reader the flat pre-dossier page with no tabs. It
    # errored nowhere. The condition must also confirm the nav is still there.
    guard = re.search(r"function teamDossier\([^)]*\)\s*\{(.*?)\n\s*/\* every section",
                      src, re.S)
    check("teamDossier has an entry guard", guard is not None)
    if guard:
        g = guard.group(1)
        check("idempotence checks for the nav, not only the stamp",
              "querySelector('.tdnav')" in g,
              "a dataset stamp alone survives a re-render that wipes the work")

    # --- 3c. the open team page is told when live data lands ---------------
    # ⚠ THIRD MEMBER OF THE POLL-STALENESS FAMILY (scoreboard, ledger, now
    # this). The Next-match card reads matchState(m, LIVE_BY_ID[...]) and
    # renders on route entry -- on a fresh load that is BEFORE the first poll
    # returns, so Michigan's page said "Next match - 3:00 PM PT - 99% to win"
    # while Michigan was mid-2nd-set, and nothing re-rendered it. deskLive()
    # must re-render the OPEN team route (and only that one), and the entry
    # is safe because teamDossier checks for its own nav, not just its stamp.
    live_fn = src[src.find("async function deskLive"):]
    live_fn = live_fn[:live_fn.find("\nasync function ", 10)
                      if live_fn.find("\nasync function ", 10) > 0 else 6000]
    check("the poll re-renders the open team page",
          "#\\/teams\\/" in live_fn and "showTeam(" in live_fn,
          "a live team's own page must not show the pre-match card")
    check("...and only the one actually open",
          "location.hash" in live_fn)
    # --- 3d. a live or finished match shows no pre-match pick --------------
    # ⚠ "99% TO WIN" SAT BESIDE A LIVE MATCH. The simulator's number is a
    # statement about a match that has not started; on a live card it reads as
    # a live win probability, which this site never shows.
    # (this module has no fn() helper -- that lives in a sibling suite; the
    #  bounded-body regex is the same technique inline)
    _nmm = re.search(r"function tdNextMatch\(.*?\n\}", src, re.S)
    nm = _nmm.group(0) if _nmm else ""
    check("the pick renders only on an upcoming match",
          "st === 'upcoming' && f.pick" in nm,
          "a pre-match pick on a live card reads as a live probability")
    check("...and a live card carries the tally, not the start time",
          "st === 'live'" in nm and "matchScore(" in nm)

    print("overview promises")

    # --- 4. Overview carries the three things the brief asked for ---------
    ov = re.search(r"ov\.insertAdjacentHTML\('beforeend',(.*?)\);", src, re.S)
    check("Overview assembled from next-match + players", ov is not None and
          "tdNextMatch" in ov.group(1) and "tdPlayers" in ov.group(1))
    check("Scout's Read appended to Overview",
          re.search(r"if \(scout\) ov\.appendChild\(scout\)", src) is not None)

    # --- 5. faces are a real photo or initials -- never a drawn likeness ---
    # The brief was explicit: official headshots only where verified, never AI
    # portraits and never an empty visual placeholder. `avatar()` draws a
    # figure from a name; it must not be reachable from the dossier face.
    face = re.search(r"function tdFace\(([^)]*)\)\s*\{(.*?)\n\}", src, re.S)
    check("tdFace exists", face is not None)
    if face:
        body = face.group(2)
        check("tdFace never draws an avatar", "avatar(" not in body)
        check("tdFace falls back to initials", "tdInitials" in body)
        check("tdFace renders an img when a photo is given",
              "<img class=\"tdface\"" in body)
        check("a broken photo degrades to initials, not an empty frame",
              "onerror" in body and "tdinit" in body)

    # --- 6. a headline rate is position-appropriate and never a -0.0 ------
    # A libero rendered "-0.0 kills/set" on Bryant: schedule adjustment can
    # push a non-attacker's kill rate a hair below zero and rounding prints
    # the sign. 120 star rows sat below that threshold.
    # ⚠ ONE DEFINITION, EVERY CALLER. The rule below was first fixed inside
    # the dossier's own renderer -- and hours later Cody's phone showed
    # "-0.0 kills/set" on a LIVE MATCH PREVIEW, because starLine() was a
    # second copy of the same line with the old behaviour. posHeadline() is
    # now the single definition; both renderers must call it and neither may
    # keep a private kps fallback.
    check("posHeadline is the one definition",
          src.count("function posHeadline(") == 1)
    # (body extracted to the closing brace at column 0 -- `[^}]*` stopped at
    #  the FIRST inner brace and failed the correct code, the same extractor
    #  mistake this session has already made twice)
    _sl = re.search(r"function starLine\(.*?\n\}", src, re.S)
    check("...the match preview's starLine calls it",
          _sl is not None and "posHeadline(" in _sl.group(0),
          "a second copy of the rule is how the bug outlived its fix")
    check("...and starLine keeps no kps line of its own",
          re.search(r"function starLine\(.*?\n\}", src, re.S) and
          "kills/set" not in re.search(r"function starLine\(.*?\n\}", src,
                                       re.S).group(0))
    check("headline rate is floored above zero",
          re.search(r"v != null && v >= 0\.05", src) is not None)
    for pos, unit in (("LDS", "digs/set"), ("S", "assists/set"),
                      ("MB", "blocks/set")):
        check("%s leads with %s" % (pos, unit),
              re.search(r"x\.pos === '%s' \? \(?rate\(x\.\w+, '%s'\)"
                        % (pos, unit), src) is not None)

    # --- 3c. the glance strip must not hard-code its column count ---------
    # The dossier removes the "Next" tile (its Overview card is a superset),
    # so the strip is three tiles on most teams and four on a team with no
    # fixture. repeat(4,1fr) left a dead quarter-width column on every page
    # that had one removed.
    check("glance strip does not hard-code a column count",
          re.search(r"\.glance\{display:grid;grid-template-columns:"
                    r"repeat\(auto-fit", src) is not None)

    print("built page")
    if not os.path.exists(PAGE):
        check("page exists", False, PAGE)
    else:
        page = io.open(PAGE, encoding="utf-8").read()
        # ⚠ Tests must read the page Cody actually opens -- a guard that read
        # output/vb_dashboard.html once passed against a frozen artefact.
        check("dossier ships in the page", "teamDossier" in page)
        check("nav is a tablist", 'class="tdnav"' in page or
              "'tdnav'" in page)
        # mobile: the player grid must collapse to one column
        check("player grid collapses on a phone",
              re.search(r"@media \(max-width:\s*560px\)[^@]*?"
                        r"\.tdpgrid\{grid-template-columns:1fr\}", page,
                        re.S) is not None)

    # --- 7. negative-zero control on the real payload ---------------------
    # Positive control: the values that WOULD have printed a negative zero are
    # still in the data, so the guard above is doing work rather than passing
    # because the case disappeared.
    import json
    mm = re.search(r"const TEAMS = (\{)", page) if os.path.exists(PAGE) else None
    if mm:
        i = mm.start(1)
        d = 0
        j = i
        instr = False
        esc = False
        while j < len(page):
            c = page[j]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            elif c == '"':
                instr = True
            elif c == "{":
                d += 1
            elif c == "}":
                d -= 1
                if d == 0:
                    break
            j += 1
        teams = json.loads(page[i:j + 1])
        near = 0
        for v in teams.values():
            for st in (v.get("stars") or []):
                for f in ("kps", "dps", "bps", "asps"):
                    x = st.get(f)
                    if x is not None and -0.05 < x < 0.05:
                        near += 1
        check("rates that would round to zero still exist in the payload",
              near > 0, "%d found" % near)
        # ⚠ THE FACE RULE IS ENFORCED ON THE DATA, NOT THE FUNCTION. tdFace
        # renders whatever url it is handed; what makes the rule true is that
        # no placeholder ever reaches it. A `data:` URI is the 1x1 transparent
        # pixel some roster templates ship in place of a headshot -- an empty
        # visual placeholder is exactly what the brief forbade.
        # the face is looked up on the ROSTER row (`r.ph`), not on the star
        bad = []
        withph = 0
        for tn, v in teams.items():
            for r in (v.get("roster") or []):
                ph = r.get("ph")
                if not ph:
                    continue
                withph += 1
                # A face is legitimately one of two things: a remote headshot
                # URL from the school's own site, or a file Cody dropped in
                # Cody/players/ himself (private build only, gitignored). What
                # it may never be is a `data:` URI -- the 1x1 transparent pixel
                # some roster templates ship where a headshot should be, which
                # renders as an empty frame.
                if not (str(ph).startswith("http")
                        or str(ph).startswith("players/")):
                    bad.append((tn, r.get("n"), str(ph)[:32]))
        check("no face is a data: URI or other placeholder", not bad, bad[:3])
        check("real headshots are actually present", withph > 200,
              "%d roster rows carry a photo" % withph)
        # and the stars a dossier shows must be findable on that roster, or
        # every face silently falls back to initials
        # ⚠ A RATIO, NOT A COUNT. This was `len(miss) < 20`, and the first
        # evening of the season broke it at 21: more teams playing means more
        # stars, means more of the known feed-vs-roster spelling gaps
        # ("Una Vajagic", "Nina Jioshvili-ravva"). A fixed count fails on data
        # GROWTH, not on regression -- the same calendar-shaped mistake as the
        # exhibition-badge guard. The invariant is join HEALTH: an unresolved
        # star renders initials (honest), but if a large share stop resolving
        # the join itself has broken. A real break is ~100%; five percent is
        # the sanity bound, stated as one.
        miss, tot = [], 0
        for tn, v in teams.items():
            names = set(r.get("n") for r in (v.get("roster") or []))
            for st in (v.get("stars") or [])[:3]:
                if not st.get("n"):
                    continue
                tot += 1
                if st["n"] not in names:
                    miss.append((tn, st["n"]))
        _ratio = (len(miss) / float(tot)) if tot else 0.0
        check("dossier stars resolve against their own roster",
              _ratio <= 0.05,
              "%d of %d unresolved (%.1f%%), e.g. %s"
              % (len(miss), tot, 100 * _ratio, miss[:3]))

    # --- 8. the private art must never reach the published page -----------
    # Cody/players/ holds drawn likenesses of named athletes that he placed
    # there himself. They are fine on his own machine and are not ours to
    # republish; Cody/ is gitignored, but the guard that matters is that the
    # PUBLIC build cannot emit the path at all.
    art = re.search(r"_artdir[^\n]*\n(?:[^\n]*\n){0,3}?[^\n]*os\.path\.isdir"
                    r"\(_artdir\)([^\n]*)", src)
    check("private player art is excluded from the public build",
          art is not None and "not PUBLIC" in art.group(1),
          art.group(1) if art else "guard not found")

    pub = os.path.join(ROOT, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        p_ = io.open(pub, encoding="utf-8").read()
        check("no private art path in the published page",
              '"players/' not in p_ and "'players/" not in p_)

    print("")
    if FAIL:
        print("FAILED: %s" % ", ".join(FAIL))
        return 1
    print("dossier guards pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
