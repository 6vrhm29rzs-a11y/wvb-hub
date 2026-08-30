#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Today and the Scoreboard.

⚠ WHAT THIS PHASE FIXED, MEASURED BEFORE THE CHANGE. Every one of six
destinations carried 335px of chrome before its first content -- 41% of an
825px viewport -- because the full match band rendered identically on all of
them, five days out, carrying five empty dashed set cells that read as a score
that failed to load. And the scoreboard opened with a season recap, a podium
and a results ribbon before its first date control.

Python 3.9 target. Run: python3 scripts/test_today_scoreboard.py
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


def main():
    print("TODAY AND THE SCOREBOARD\n")
    h, which = page()
    if not h:
        print("  (no built page -- skipping)")
        return 0
    src = open(os.path.join(REPO, "scripts", "build_hub.py"),
               encoding="utf-8").read()
    private = "START-HERE" in (which or "")
    print("  reading %s\n" % which)

    # ── 1. TODAY ────────────────────────────────────────────────────────
    print("1. TODAY IS THE PRIMARY DESTINATION")
    tabs = re.findall(r'<button role="tab"[^>]*data-v="([a-z0-9]+)"[^>]*>([^<]*)<', h)
    first = tabs[0] if tabs else ("", "")
    check("the first primary tab is Today", first == ("desk", "Today"),
          str(first))
    # ⚠ SCAN THE MARKUP, NOT THE SCRIPT. The first version searched the whole
    # document for text between angle brackets, which on a page carrying a
    # 400KB inline <script> matches the script's own comments -- several of
    # which discuss the old name for good reason. Strip script and style, then
    # look at what a reader can actually see.
    visible = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    shown = re.findall(r">([^<>]{0,80}Match Desk[^<>]{0,80})<", visible)
    check("[-] 'Match Desk' is never a user-facing label",
          not shown, str(shown[:2]))
    check("[+] ...over markup that does carry visible tab labels",
          ">Today<" in visible and ">Rankings<" in visible)
    check("the primary route is /today", "desk:'today'" in src)
    # ⚠ OLD LINKS MUST STILL RESOLVE.
    check("[-] ...and match-desk survives as an alias",
          "ROUTE_ALIASES = { 'match-desk': 'desk' }" in src and
          "VIEW_OF_ROUTE[k] = ROUTE_ALIASES[k]" in src,
          "every bookmark and saved note points at the old path")

    print("\n1b. A TOP GAME EXPLAINS ITSELF")
    check("named reasons exist", "function todayReasons(" in src)
    for tag in ("ranked v ranked", "national TV", "conference test",
                "ranking disagreement"):
        check("  reason: %s" % tag, "'%s'" % tag in src)
    if private:
        check("  reason: my board", "'my board'" in src)
    # ⚠ NO OPAQUE SCORE.
    check("[-] top games are chosen by REASON COUNT, not a blended score",
          "filter(x => x[1].length)" in src and
          "b[1].length - a[1].length" in src)
    check("[-] ...and a match with no reason is not a top game",
          ".filter(x => x[1].length)" in src)

    print("\n1c. THE LANDING PAGE IS WATCH-FIRST AND BOUNDED")
    # ⚠ THE QUIET-DAY BLOCKS WERE REPLACED WHOLESALE. Cody's own words:
    # "I don't care about all that info. I just want to know when the top teams
    # are playing" and "you don't need to say no games today -- I want to know
    # when the next game that I need to watch is." So the page no longer
    # announces absence, no longer counts mid-major fixtures, and leads with
    # matches he might actually watch.
    # ⚠ THE HEADING IS LIVE-AWARE NOW (round 5): "Watch now" while cards
    # are in progress, "Your next watches" otherwise -- pinning the literal
    # would fail the better behavior.
    check("the first block is the watch list (live-aware title)",
          "? 'Watch now' : 'Your next watches'" in src)
    check("[-] at most five watches", "ranked.slice(0, 5)" in src)
    check("then the rest of the ranked slate", "Big weekend ahead" in src)
    check("then results that moved the picture",
          "Results that changed the picture" in src)
    check("[-] ...on a stated test, not an editorial feel",
          "const five = (+sc[0] + +sc[1]) === 5" in src and
          "rankedLost" in src)
    # ⚠ SCOPE THIS TO THE LANDING PAGE. A DATE view -- the Scoreboard, the day
    # lanes -- SHOULD say when a chosen date is empty; that is an answer to the
    # question it was asked. The rule is that the landing page never leads with
    # absence, because nobody opens it to be told nothing is on.
    # bounded by the end of renderDesk's landing branch, whose last statement
    # is the stated-rule paragraph
    landing = src[src.index("THE LANDING PAGE"):]
    _end = landing.find("ONE FEATURED MATCH AT MOST")
    landing = landing[:_end] if _end > 0 else landing[:9000]
    check("[-] the LANDING page never announces absence",
          "No Division-I matches" not in landing,
          "it tells him what to watch, not what is missing")
    check("[+] ...while a chosen empty DATE still says so",
          "No Division-I matches on " in src,
          "a date view owes that answer")
    check("[-] ...and no mid-major fixture count",
          "' matches.'" not in src.split("THE LANDING PAGE")[1][:5200],
          "195 matches is not information he asked for")
    check("[-] no explanatory sentence about the model on the first screen",
          "a forecast is a " not in src.split("desklead")[1][:900])
    check("the selection rule is printed for the reader", "tdrule" in src)

    print("\n1d. WHERE TO WATCH")
    # ⚠ THE FEED CARRIES NO BROADCAST AT ALL -- measured, empty on all 1,971
    # scoreboard entries. This is Cody's own transcribed listing, joined
    # strictly, and it is the first thing he asked for.
    check("fixtures carry a network", "\"tv\": (tvx.get(gid) or {}).get(\"net\")" in src)
    check("[-] joined only when exactly one fixture matches",
          "if len(cand) != 1:" in src)
    check("[-] ...through the existing normaliser, not a new one",
          "from reconcile_2025 import norm as _norm" in src)
    check("a watch card shows the channel", "class=\"wnet\"" in src)
    # ⚠ ASSERT THE MEANING, NOT THE WORDING. This pinned the literal string
    # "TV not listed", which was rendered as a dashed BADGE in the very slot
    # where FOX and BTN appear -- so an unknown broadcast looked like a
    # featured fact in the one place Cody scans for a channel. The badge is now
    # plain muted type reading "no listing", with the distinction spelled out
    # on hover. What must not change is that the card still SAYS SOMETHING:
    # silence would imply "not televised" when we mean "we do not know".
    check("[-] ...and says so when there is none, rather than implying not-on-TV",
          'class="wnet none"' in src
          and "TV/stream listing not held" in src
          and "never untelevised" in src)
    check("[-] ...without dressing an unknown up as a badge",
          ".wnet.none{" in src and "border:0" in src,
          "a dashed border in the channel slot reads as a data point")
    # ⚠ THE NETWORK IS RENDERED BY JS, so it is not in the static markup --
    # the first version of this check scanned the HTML and found only the
    # literal fallback string. Assert the DATA instead: the payload the page
    # renders from is static and carries the joined networks.
    # ⚠ GATE ON THE DATA, NOT ON WHICH PAGE. `private` here meant "the private
    # page exists" -- and CI BUILDS the private page, just without
    # Cody/data/tv_listings_2026.txt, which is gitignored and can never be in
    # a checkout. So this check demanded four joined networks from a build
    # that legitimately has zero, and blocked the publish pipeline on the
    # first real match day. The join can only be judged where its source is.
    _tv_src = os.path.join(REPO, "Cody", "data", "tv_listings_2026.txt")
    if private and not os.path.exists(_tv_src):
        print("  --   no TV listings on this machine (private file absent); "
              "join not judgeable here")
    if private and os.path.exists(_tv_src):
        mfx = re.search(r"const FIXTURES = (\{.*?\});\n", h, re.S)
        FIXP = json.loads(mfx.group(1)) if mfx else {}
        nets = sorted({v["tv"] for v in FIXP.values() if v.get("tv")})
        check("[+] real networks are joined onto real fixtures",
              len(nets) >= 4, str(nets[:8]))
        check("[+] ...on a meaningful number of them",
              sum(1 for v in FIXP.values() if v.get("tv")) >= 20,
              str(sum(1 for v in FIXP.values() if v.get("tv"))))

    # ── 2. THE HEADER ───────────────────────────────────────────────────
    print("\n2. THE HEADER DOES NOT DOMINATE EVERY SCREEN")
    # ⚠ THE RAIL SHAPE IS RETIRED (review round 4): the ticker is the one
    # global strip, and the tape renders the marquee on the Today landing or
    # nothing at all. Asserting the old rail's existence would pin the shape
    # of a deleted feature.
    check("the band has one shape: the marquee, or nothing",
          "data-cs-shape=\"marquee\"" in src and
          "data-cs-shape=\"rail\"" not in src)
    check("...and the non-marquee branch renders empty",
          "mount.innerHTML = '';" in src)
    check("the marquee is Today-only", "csIsTodayRoute()" in src and
          "marquee = csIsTodayRoute()" in src)
    check("[-] ...and only when the match is genuinely near",
          "function csNearness(" in src and
          "near === 'today'" in src and "near === 'tomorrow'" in src)
    check("the header repaints when the route changes",
          "csTape(); } catch (e) { }" in src)
    # ⚠ THE ARTEFACT THAT READ AS A BROKEN SCORE
    # ⚠ ASSERT THE RULE, NOT THE EXPRESSION. This checked for the literal
    # string "(quiet ? '' : csCells(sets, st === 'live'))" -- the fourth guard
    # in this repo to pin the SHAPE of a fix rather than what it does. Adding a
    # second, correct suppression (a final whose line score is not in yet)
    # changed that expression and failed a build that satisfies the rule more
    # completely than before.
    # ⚠ ...and anchor on the CALL, not the first textual match. The first
    # version split the file at "csCells(sets" and inspected what came before
    # it -- which is the FUNCTION DEFINITION, several hundred lines above the
    # call, and of course mentions no `quiet`. It failed correct code.
    _call = re.search(r"\(quiet[^;]{0,120}?csCells\(sets,\s*st === 'live'\)",
                      src, re.S)
    check("[-] an upcoming match renders NO set cells",
          "const quiet = st === 'upcoming';" in src and _call is not None,
          "empty dashed boxes read as a score that failed to load")
    check("[-] ...and neither does a final whose line score is not in yet",
          "st === 'final' && !sets.length" in src,
          "five empty boxes beside a FINAL read as a failed load")

    # ── 3. THE SCOREBOARD ───────────────────────────────────────────────
    print("\n3. THE SCOREBOARD ANSWERS ONE QUESTION")
    check("it is called Scoreboard", '<h2 class="vh">Scoreboard</h2>' in h)
    check("the date is the page state", "let SB_DATE = null;" in src)
    for ctl in ("sbPrev", "sbNext", "sbToday", "sbDate"):
        check("  control present: %s" % ctl, 'id="%s"' % ctl in h)
    fl = re.findall(r'data-sbf="([a-z]+)"', h)
    want = ["all", "board", "ranked", "live", "final", "upcoming"] if private \
        else ["all", "ranked", "live", "final", "upcoming"]
    check("the filters are exactly the six (five in public)", fl == want, str(fl))
    # ⚠ TOP GAMES LEFT THE SCOREBOARD ENTIRELY (design review via Cody,
    # 2026-08-28): highlights belong on Today; Scores opens straight into
    # Live now. The guard flips from "scoped to the date" to "absent".
    check("the Scoreboard mounts no Top Games band",
          'id="sbTop"' not in h,
          "highlights on the working board duplicate the live lane below")
    # ⚠ THE THREE THINGS THAT USED TO OPEN THIS PAGE
    scores = h[h.index('<section id="v-scores"'):]
    scores = scores[:scores.index("</section>")]
    check("[-] no season-recap hero on the scoreboard",
          "herotitle" not in scores, "the season summary is a different job")
    check("[-] no What Changed ribbon on the scoreboard",
          'id="chgmeta"' not in scores)
    check("[+] ...and What Changed still exists, on Today",
          "CHANGED_ROWS_HTML" in src and "What changed" in src)
    check("the full season ledger is kept and named",
          'class="sbfull"' in h and "Full season ledger" in h)

    # ── 4. NO ORPHANED NODES ────────────────────────────────────────────
    print("\n4. NOTHING ADDRESSES A NODE THAT NO LONGER EXISTS")
    # ⚠ THIS PHASE REMOVED A STACK OF NODES AND LEFT POLLERS ADDRESSING THEM.
    # `getElementById(x).textContent = ...` on a null threw inside the boot
    # sequence and took the whole page with it -- Today rendered empty with no
    # header. $$ returns a harmless stand-in, but an orphan is still a bug.
    present = set(re.findall(r'id="([A-Za-z0-9_-]+)"', h))
    js = max(re.findall(r"<script>(.*?)</script>", h, re.S), key=len)
    refs = set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", js))
    orphans = sorted(refs - present)
    check("no getElementById target is missing from the page",
          not orphans, str(orphans[:4]))
    check("[+] ...over a page that really does address nodes",
          len(refs) > 30, str(len(refs)))
    check("a safe accessor exists for the ones that survive a removal",
          "function $$(id)" in src)

    # ── THE LIVE TICKER (Cody, 2026-08-28: "every sports site has an upper
    # banner of live games"). Invariants: every chip routes through the ONE
    # open-a-match handler (data-match); the strip hides when nothing is
    # live rather than rendering an empty frame; a rebuild preserves the
    # reader's scroll position and skips when content is unchanged -- a strip
    # that snaps back to the left every 60 seconds is unusable; and the live
    # band's cards route too (a match-shaped box that does nothing when
    # tapped reads as broken -- the just-finished and live cards were the
    # only match surfaces with no data-match).
    print("\n8. THE LIVE TICKER")
    check("the ticker mount exists", 'id="livetick"' in h)
    _tk = src[src.find("let TK_LAST"):]
    _tk = _tk[:_tk.find("async function pollLive")]
    check("chips route through data-match", "data-match=" in _tk
          and 'class="tkm"' in _tk)
    check("hidden when nothing is live",
          "el.hidden = true" in _tk and "TK_LAST = ''" in _tk)
    check("scroll position survives a rebuild",
          "el.scrollLeft" in _tk and "keep" in _tk)
    check("unchanged content skips the rebuild",
          "html === TK_LAST" in _tk)
    check("current-set points come from the feed, never invented",
          "cur[0] !== null" in _tk)
    check("the live band cards carry data-match",
          "class=\"card islive\" data-match=" in src.replace("' +\n      '", ""))
    check("the just-finished cards carry data-match",
          "class=\"card done\" data-match=" in src)
    _b = _tk.replace("data-match=", "data-nothing=")
    check("[NEG] chips without routing are caught", "data-match=" not in _b)

    print()
    # ⚠ page() returns (html, filename), not a string. Passing the tuple
    #   made every `in` check test tuple MEMBERSHIP, which is always
    #   false for a substring -- so the guard failed against a correct
    #   build and would have 'passed' nothing.
    if not check_scoreboard_follows_the_feed(page()[0] or ''):
        FAILS.append("the Scoreboard follows the feed and does not repeat itself")

    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL TODAY / SCOREBOARD GUARDS PASS")
    return 0



def check_scoreboard_follows_the_feed(h):
    """The Scores list must be refreshed when live data lands.

    ⚠ IT WAS THE ONE VIEW THE POLL NEVER TOLD. renderDesk(), the rally tape,
    csStatus() and any open match detail were all re-rendered when a poll
    returned; the Scoreboard list was not. So Florida-Nebraska finished 2-0,
    the masthead rail said FINAL, and the lane beneath it still read SCHEDULED
    with no score -- and would have until the reader touched a filter. Cody
    called the page a mess and he was right.

    ⚠ AND "TOP GAMES" MUST BE A SELECTION. On a two-match evening every match
    was also a top game, so the band repeated the whole day directly above the
    list: the same two fixtures twice, which reads as a bug rather than as
    emphasis.
    """
    ok = True
    if "if (typeof renderScoreboard === 'function') renderScoreboard();" not in h:
        print("  FAIL the live poll does not refresh the Scoreboard")
        ok = False
    # (the day-repeat guard retired with the band itself; its renderer no
    #  longer mounts on this page)
    if 'id="sbTop"' in h:
        print("  FAIL the Top Games band came back to the Scoreboard")
        ok = False
    # the exhibition badge must not be a flex item in the team column
    if "exhTag(m) + '</span>'" in h and "'<span class=\"mteams\">'" in h:
        i = h.find("'<span class=\"mteams\">'")
        if "exhTag" in h[i:i + 200]:
            print("  FAIL the EXH badge is back inside the team column, where "
                  "a column flex stretches it to the full row width")
            ok = False
    print("  %-64s %s" % ("the Scoreboard follows the feed and does not repeat "
                          "itself", "ok" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.exit(main())
