#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the two roster-parser defects found 2026-08-18.

Both were SILENT. Neither raised, neither logged, neither failed a gate: a team
just came back with fewer players than it has, and every missing player's 2025
production was then attributed to "departed". Kassie O'Brien -- Kentucky's
returning sophomore and the 2025 National Freshman of the Year -- was reported
as having left. Cody caught it by reading the page, which is exactly the review
channel this project is trying not to depend on.

  1. HTML ENTITIES IN NAMES. Some templates emit the apostrophe in a surname as
     "&#039;". The name-shape pattern rejects "&", "#" and digits, so those
     players were dropped. Fix: unescape before the shape test.

  2. THE CLASS-TOKEN PROXY. The staff filter kept only candidates with a class
     year or jersey number nearby. That is a proxy for personhood, and SIDEARM
     moved the class token out of the anchor's neighbourhood -- so it started
     deleting real players. Measured: Virginia 17 -> 0, UCLA 18 -> 9.
     Fix: prefer the structural fact, /roster/player/<slug>, which staff do not
     get; keep the proxy only for templates without that path.

Each guard carries a NEGATIVE CONTROL that re-introduces the old behaviour in
process and asserts the check then fails. A test that cannot fail is not a test.

Python 3.9 target. Run: python3 scripts/test_roster_parser.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as cr  # noqa: E402

FAILURES = []


def check(label, got, want):
    ok = got == want
    print("  %-58s %s" % (label, "ok" if ok else "FAIL (got %r, want %r)" % (got, want)))
    if not ok:
        FAILURES.append(label)
    return ok


# --- fixtures --------------------------------------------------------------
# Shapes copied from the live pages that broke, reduced to the parts under test.

ENTITY_APOSTROPHE = """
<div class="roster__item">
  <a href="https://ukathletics.com/sports/wvball/roster/player/kassie-obrien/">Kassie O&#039;Brien</a>
  <span>Sophomore</span>
</div>
<div class="roster__item">
  <a href="https://ukathletics.com/sports/wvball/roster/player/trinity-ward/">Trinity Ward</a>
  <span>Sophomore</span>
</div>
"""

# Player anchors with NO class year or jersey number anywhere near them -- the
# shape that emptied Virginia's roster.
NO_CLASS_TOKEN = """
<a href="/sports/wvball/roster/player/becca-wight">Becca Wight</a>
<a href="/sports/wvball/roster/player/caroline-lang">Caroline Lang</a>
<a href="/sports/wvball/roster/player/ella-brodner">Ella Brodner</a>
"""

# Staff must still be excluded, or the fix trades one silent error for another.
STAFF_MIXED = """
<a href="/sports/wvball/roster/player/real-player">Reese Wuebker</a>
<a href="/sports/wvball/roster/season/2026/staff/nate-wilson">Nate Wilson</a>
<a href="/sports/wvball/roster/coaches/jane-doe">Jane Doe</a>
"""

# Templates without /roster/player/ still need the class/number proxy, or the
# structural rule would let every stray link through.
LOOSE_PATH = """
<a href="/sports/womens-volleyball/roster/nil-kayaalp/17216">Nil Kayaalp</a>
<span>Junior</span>
"""

# A loose-path link with no class token WITHIN REACH must be dropped.
LOOSE_PATH_UNCLASSED = """
<a href="/sports/womens-volleyball/roster/some-page/999">Ticket Office</a>
"""

# KNOWN HOLE, asserted so it cannot change unnoticed. On loose-path templates
# the class token is looked for in a window either side of the anchor, so a
# non-player link sitting next to a classed player BORROWS that player's token
# and survives. This is the Nebraska staff bug the parser comments describe, and
# it is unfixed: the note there records that tightening the window broke three
# other templates. It only affects templates WITHOUT /roster/player/, which is
# now the minority. Recorded as a limitation, not a passing grade.
LOOSE_PATH_BORROWED = """
<a href="/sports/womens-volleyball/roster/nil-kayaalp/17216">Nil Kayaalp</a>
<span>Junior</span>
<a href="/sports/womens-volleyball/roster/some-page/999">Ticket Office</a>
"""


def names(html):
    return sorted(p["name_raw"] for p in cr.parse_roster(html))


def main():
    print("ROSTER PARSER GUARDS\n")

    print("1. HTML-entity names survive the shape test")
    got = names(ENTITY_APOSTROPHE)
    check("Kassie O'Brien is parsed, apostrophe intact", "Kassie O'Brien" in got, True)
    check("the entity is decoded, not left literal",
          any("&#039;" in n for n in got), False)
    check("her teammate is unaffected", "Trinity Ward" in got, True)

    print("\n2. A player with no nearby class token is still a player")
    got = names(NO_CLASS_TOKEN)
    check("all three /roster/player/ anchors survive", len(got), 3)
    check("Becca Wight kept despite class_raw being None", "Becca Wight" in got, True)

    print("\n3. Staff are still excluded (the filter's original job)")
    got = names(STAFF_MIXED)
    check("the player is kept", "Reese Wuebker" in got, True)
    check("/staff/ is dropped", "Nate Wilson" in got, False)
    check("/coaches/ is dropped", "Jane Doe" in got, False)

    print("\n4. Templates without /roster/player/ still use the class proxy")
    got = names(LOOSE_PATH)
    check("classed player on a loose path is kept", "Nil Kayaalp" in got, True)
    got = names(LOOSE_PATH_UNCLASSED)
    check("loose-path link with no class token in reach is dropped", got, [])
    got = names(LOOSE_PATH_BORROWED)
    check("KNOWN HOLE: adjacent non-player borrows the class token",
          "Ticket Office" in got, True)

    print("\n5. Headshot URLs are repaired, and absent ones stay absent")
    # WMT doubles the host prefix; the result is not a URL and 404s
    doubled = ('<a href="/roster/player/x">Ann Lee</a>'
               '<span itemprop="name" content="Ann Lee"></span>'
               '<span itemprop="image" content="https://s.com/https://s.com/img/a.png">'
               '</span><span>Senior</span>')
    got = cr.parse_roster(doubled, "https://s.com")
    photo = got[0]["photo"] if got else None
    check("the doubled host prefix is stripped",
          photo, "https://s.com/img/a.png")

    # SIDEARM crop URLs carry &amp; separators that 400 unless decoded
    amp = ('<a href="/roster/player/y">Bea Ray</a><span>Junior</span>'
           '<img src="https://i.dev/crop?url=x&amp;width=100&amp;height=100">')
    got = cr.parse_roster(amp, "https://s.com")
    photo = got[0]["photo"] if got else None
    check("&amp; in a photo URL is decoded",
          photo, "https://i.dev/crop?url=x&width=100&height=100")

    # a lazy-loading placeholder is not a headshot
    placeholder = ('<a href="/roster/player/z">Cal Poe</a><span>Freshman</span>'
                   '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5">')
    got = cr.parse_roster(placeholder, "https://s.com")
    check("a base64 placeholder is not taken as a photo",
          got[0]["photo"] if got else "MISSING", None)

    # neither is a logo
    logo = ('<a href="/roster/player/w">Dee Fox</a><span>Senior</span>'
            '<img src="https://s.com/images/site-logo.png">')
    got = cr.parse_roster(logo, "https://s.com")
    check("a logo is not taken as a photo",
          got[0]["photo"] if got else "MISSING", None)

    # --- negative controls -------------------------------------------------
    # Re-introduce each old behaviour in process and assert the guard trips.
    print("\nNEGATIVE CONTROLS -- re-introduce each bug and confirm the guard fails")

    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "crawl_rosters.py"), encoding="utf-8").read()

    # (a) remove the unescape
    no_unescape = src.replace(
        'name = _unescape(re.sub(r"\\s+", " ", re.sub(r"<[^>]+>", " ", inner))).strip()',
        'name = re.sub(r"\\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()')
    # (b) restore the class/number-only filter
    no_structural = src.replace(
        'if p.get("_player_path") or p.get("class_raw") or p.get("num_raw")]',
        'if p.get("class_raw") or p.get("num_raw")]')

    def parse_with(modified_src, html):
        ns = {"__name__": "old_crawl", "__file__": os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "crawl_rosters.py")}
        exec(compile(modified_src, "old_crawl", "exec"), ns)
        return sorted(p["name_raw"] for p in ns["parse_roster"](html))

    if no_unescape == src:
        print("  %-58s %s" % ("could not synthesise the pre-unescape parser", "FAIL"))
        FAILURES.append("negative control (a) not applied")
    else:
        got = parse_with(no_unescape, ENTITY_APOSTROPHE)
        check("(a) without unescape, O'Brien disappears", "Kassie O'Brien" in got, False)

    if no_structural == src:
        print("  %-58s %s" % ("could not synthesise the class-only filter", "FAIL"))
        FAILURES.append("negative control (b) not applied")
    else:
        got = parse_with(no_structural, NO_CLASS_TOKEN)
        check("(b) with the class-only filter, the roster empties", len(got), 0)

    print()
    if FAILURES:
        print("FAILED: %d check(s)" % len(FAILURES))
        for f in FAILURES:
            print("   - %s" % f)
        return 1
    print("ALL ROSTER PARSER GUARDS PASS, both negative controls tripped as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
