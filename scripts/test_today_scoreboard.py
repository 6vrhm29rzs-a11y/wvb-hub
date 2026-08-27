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
    check("the first block is Your next watches",
          "block('Your next watches'" in src)
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
    check("[-] ...and says so when there is none, rather than implying not-on-TV",
          "TV not listed" in src)
    # ⚠ THE NETWORK IS RENDERED BY JS, so it is not in the static markup --
    # the first version of this check scanned the HTML and found only the
    # literal fallback string. Assert the DATA instead: the payload the page
    # renders from is static and carries the joined networks.
    if private:
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
    check("the band has two shapes", "data-cs-shape=\"rail\"" in src and
          "data-cs-shape=\"marquee\"" in src)
    check("the marquee is Today-only", "csIsTodayRoute()" in src and
          "marquee = csIsTodayRoute()" in src)
    check("[-] ...and only when the match is genuinely near",
          "function csNearness(" in src and
          "near === 'today'" in src and "near === 'tomorrow'" in src)
    check("the header repaints when the route changes",
          "csTape(); } catch (e) { }" in src)
    # ⚠ THE ARTEFACT THAT READ AS A BROKEN SCORE
    check("[-] an upcoming match renders NO set cells",
          "(quiet ? '' : csCells(sets, st === 'live'))" in src,
          "empty dashed boxes read as a score that failed to load")

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
    check("top games are for the selected date only",
          "topGames(rows, liveOf, 4)" in src)
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

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL TODAY / SCOREBOARD GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
