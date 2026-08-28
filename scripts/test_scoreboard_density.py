# -*- coding: utf-8 -*-
"""Guards for the scoreboard row -- the set-by-set line score and the context.

The Scores ledger row showed who played and how many sets each won, and left
roughly a thousand pixels of nothing between the names and the score. The
per-set points -- the detail a volleyball scoreboard exists for -- were
rendered only in a collapsed card grid further down the same page.

Two things were added to `matchRow()`, and both are ways to be wrong:

  setStrip()      the per-set line score, from two sources that do not overlap
  matchContext()  the event and venue, which must be REPORTED or absent

These guards assert the failure modes rather than the feature.

Python 3.9 target. Run: python3 scripts/test_scoreboard_density.py
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
    print("  %-64s %s" % (name, "ok" if cond else "FAIL %s" % detail))
    if not cond:
        FAIL.append(name)


def block(src, start):
    """Brace-match from `start` to the matching close.

    ⚠ A NON-GREEDY `.*?\n\}` EXTRACTOR TRUNCATES AT THE FIRST INNER FUNCTION.
    setStrip contains an arrow function, so the naive regex returned a fragment
    and eight guards reported the working code as broken. They were the guards
    being wrong, not the source -- exactly the trap this file exists to catch,
    so it is fixed here rather than worked around in build_hub.
    """
    i = src.find("{", start)
    if i < 0:
        return ""
    d, j, instr, esc = 0, i, None, False
    while j < len(src):
        c = src[j]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == instr:
                instr = None
            j += 1
            continue
        # ⚠ SKIP COMMENTS BEFORE ANYTHING ELSE. A quote inside a comment is not
        # a string. This file's comments quote rendered text -- "CLIFF KEEN
        # ARENA, ANN ARBOR" -- and an earlier version of this scanner treated
        # that opening quote as a string start, lost brace synchronisation, and
        # returned matchContext PLUS the two functions after it. The guard for
        # "never inferred from the home team" then found `mHome` in a function
        # it was never meant to be reading and failed correct code. Third time
        # a scanner in this file has been wrong about the source it scans.
        if c == "/" and j + 1 < len(src):
            if src[j + 1] == "*":
                k = src.find("*/", j + 2)
                j = (k + 2) if k >= 0 else len(src)
                continue
            if src[j + 1] == "/":
                k = src.find("\n", j + 2)
                j = (k + 1) if k >= 0 else len(src)
                continue
        if c in "'\"":
            instr = c
        elif c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d == 0:
                return src[start:j + 1]
        j += 1
    return ""


def fn(src, name):
    i = src.find("function %s(" % name)
    return block(src, i) if i >= 0 else ""


def main():
    print("SCOREBOARD DENSITY GUARDS\n")
    src = io.open(SRC, encoding="utf-8").read()

    print("1. The line score")
    strip = fn(src, "rowSetStrip")
    check("rowSetStrip exists", bool(strip))

    # ⚠ NO PLACEHOLDER, EVER. A match with no line scores on file must render
    # nothing -- not a zero, not a dash, not an empty set box. R5.
    check("no sets renders an empty strip, not a stand-in",
          "if (!raw) return '<span class=\"mline\"></span>';" in strip)
    for bad in ("'0'", '"0"', "|| 0", "'\\u2014'", "&mdash;"):
        check("[-] rowSetStrip substitutes no %s" % bad, bad not in strip)

    # ⚠ TWO SOURCES THAT DO NOT OVERLAP. The live feed carries `sets` while a
    # match is being played and EMPTIES the array the instant it goes final;
    # the crawled ledger carries them only once the crawl catches up. A match
    # that just ended therefore has line scores in neither, which is a real
    # state and must degrade to nothing rather than to a wrong number.
    check("live sets are preferred while a match is live",
          "(live && live.sets && live.sets.length) ? live.sets" in strip)
    check("...and the crawled ledger is the fallback",
          "m.sets && m.sets.length ? m.sets : null" in strip)

    # ⚠ DO NOT VALIDATE A SET AGAINST 25. Set one of SMU-Penn St. finished
    # 24-22 and that is a REAL completed set: the exhibition is played
    # first-two-to-21. A plausibility rule invented from the standard format
    # would suppress true scores -- inventing a threshold and calling the
    # result a verdict is exactly what R1 forbids.
    nums = re.findall(r"[<>=]=?\s*(?:25|21|15)\b", strip)
    check("[-] no set score is validated against an assumed target",
          not nums, str(nums))

    # a live set is provisional and is marked as such, never as a result
    check("the in-progress set is marked, and only while live",
          "const now = playing && i === raw.length - 1;" in strip)
    check("...and the in-progress set crowns no winner",
          "!now && +a > +h" in strip and "!now && +h > +a" in strip)
    check("...and 'playing' comes from the state, not the score",
          "const playing = st === 'live';" in strip)

    # ⚠ AND THE COLLISION THAT NEARLY SHIPPED. This function was first called
    # `setStrip` -- a name build_hub.py ALREADY used for the live band's own
    # strip. Two top-level declarations of one name do not warn; the later one
    # simply wins, so the live band would have called this signature with a
    # bare array and rendered nothing. Silent, and on the first card a reader
    # sees. The general invariant is cheap, so it is asserted for every
    # top-level function on the page, not just this one.
    names = re.findall(r"^function ([A-Za-z_$][\w$]*)\(", src, re.M)
    dupes = sorted(set(n for n in names if names.count(n) > 1))
    check("[-] no two top-level functions share a name", not dupes, str(dupes))
    check("[+] ...over a page that has plenty of them", len(names) > 80,
          "%d found" % len(names))

    # ⚠ NO CLOCK STRING MAY BE SORTED WITH localeCompare, ANYWHERE. This bug
    # has now been found in THREE separate places: the Scoreboard lanes, the
    # "tonight's slate" band, and the ledger day view -- plus the watch list's
    # date+time concatenation. "6:00 AM PT" sorts after "5:30 PM PT" because
    # '6' > '5'. It survived so long because every day the page had rendered
    # held two matches, and in the day view it was hidden behind a sort on
    # `a.ep`, an epoch field that exists on NO match in the payload (0 of
    # 1,594) -- so the subtraction was always 0 and it fell through to the
    # broken compare while a comment above claimed the problem was solved.
    # ISO dates are fine: they sort correctly as strings.
    bad_sorts = []
    for m in re.finditer(r"[^\n]*localeCompare[^\n]*", src):
        line = m.group(0)
        if "was visibly wrong" in line or "//" in line.split("localeCompare")[0]:
            continue
        # a time operand looks like `.t`, `.t ||`, `.time`, or `+ (x.t`
        if re.search(r"\.\s*t\s*(\|\||\)|,)|\.time\b|\.\s*t\s*\+", line):
            bad_sorts.append(line.strip()[:90])
    check("[-] no clock string is ordered with localeCompare",
          not bad_sorts, str(bad_sorts[:2]))
    check("[+] ...over a file that really does sort things",
          len(re.findall(r"localeCompare", src)) >= 3,
          "%d call sites" % len(re.findall(r"localeCompare", src)))
    # and the dead sort key must not come back
    check("[-] nothing sorts on the `ep` field, which no match carries",
          not re.search(r"\(\s*a\.ep\s*\|\|\s*0\s*\)", src),
          "a sort key that is always 0 reads as a fix and is not one")

    print("\n2. The context column")
    ctx = fn(src, "matchContext")
    check("matchContext exists", bool(ctx))
    # ⚠ THE VENUE IS THE ONE FIELD THIS PROJECT HAS ALREADY GOT WRONG BY
    # GUESSING: the dashboard once printed "at <home team>" and was wrong the
    # first weekend it mattered (two neutral-floor matches at Fiserv Forum).
    check("venue is printed only when the feed reported one",
          "if (m.venue) {" in ctx)
    check("[-] ...and is never inferred from the home team",
          "mHome" not in ctx and "m.h" not in ctx.replace("m.hr", ""))
    # ⚠ the event style and the venue style are keyed to the VALUE, not to a
    # position in the list -- keying on index gave a venue the event's gold
    # caps whenever there was no event, so a gymnasium read as a tournament
    check("[-] the style follows the value, not the array index",
          "(i ? 'mctxv' : 'mctxe')" not in ctx,
          "index-keyed styling reintroduced")
    check("the event carries the event class",
          "bits.push(['mctxe'" in ctx)
    check("the venue carries the venue class",
          "bits.push(['mctxv'" in ctx)
    check("no event and no venue renders nothing",
          "if (!bits.length) return '<span class=\"mctx\"></span>';" in ctx)

    print("\n3. The row still fits, and the phone drops the extras first")
    grid = re.search(r"\.mrow\{display:grid;grid-template-columns:([^;]+);", src)
    check("the row grid is declared", grid is not None)
    if grid:
        cols = grid.group(1)
        check("the team column is capped, not 1fr",
              "minmax(150px,270px)" in cols,
              "an uncapped team column pushes the line score to the far edge")
        check("the context column takes the slack", "minmax(0,1fr)" in cols)
    # ⚠ THERE ARE FORTY-ODD @media (max-width:560px) BLOCKS IN THIS FILE, not
    # one. A guard that read `src.find(...)` inspected the first of them and
    # reported working rules as missing -- the guard being wrong, again. Every
    # block has to be collected.
    ptxt, k = "", 0
    while True:
        k = src.find("@media (max-width:560px)", k)
        if k < 0:
            break
        ptxt += block(src, k)
        k += 1
    check("the phone rules were actually found", len(ptxt) > 2000,
          "%d chars" % len(ptxt))
    check("the line score is hidden at phone width",
          ".mrow .mline{display:none}" in ptxt)
    check("the context is hidden at phone width",
          ".mrow .mctx{display:none}" in ptxt)

    print("\n4. The built page")
    if not os.path.exists(PAGE):
        check("page exists", False, PAGE)
    else:
        # ⚠ Tests read the page Cody actually opens.
        page = io.open(PAGE, encoding="utf-8").read()
        check("the strip ships", "function rowSetStrip" in page)
        check("the context ships", "function matchContext" in page)
        # a set cell is two stacked numerals, so it lines up with the two team
        # rows above it -- one numeral per team, never a single "25-22" string
        check("a set cell carries two numerals",
              re.search(r"<b class=\"' \+ \(!now && \+a", page) is not None)

    print("\n5. The 60-second poller cannot be killed by a missing band")
    # ⚠ THE ONE THAT WAS GOING TO BREAK ON THE FIRST FULL MATCH DAY. The
    # Scoreboard rebuild removed the slate band's markup -- #todaymeta,
    # #todaycards and the `.soon` label -- leaving #today as an empty hidden
    # div. The live band below was guarded when that happened; the slate branch
    # was not, because REACHING it needs a fixture in state 'pre', and every
    # day this page had ever rendered held two finals and nothing scheduled.
    # With 196 scheduled the branch runs, `querySelector('#today .soon')`
    # returns null, and the throw happens INSIDE the poll callback -- so the
    # just-finished band and the live band stop running too, every 60 seconds,
    # all day. Nothing in the UI would say why.
    poll = fn(src, "pollLive")
    check("pollLive is found", bool(poll))
    if poll:
        # every element the poller touches must be checked before it is used
        # (a) nothing is written through an inline lookup
        raw = re.findall(
            r"(?:document\.getElementById\([^)]*\)|document\.querySelector"
            r"\([^)]*\)|\$\$\([^)]*\))\s*\.\s*(?:textContent|innerHTML|hidden)",
            poll)
        check("[-] no element is written to through an inline lookup",
              not raw, str(raw[:2]))
        # (b) ⚠ AND THE VARIABLE FORM, WHICH THE PATTERN ABOVE CANNOT SEE. A
        # negative control proved it: reverting `if (jbox && jmeta && jcards)`
        # to `if (jbox)` left `jmeta.textContent = ...` in place, which passes
        # a search for chained lookups and still throws on null. So every
        # variable that holds an element lookup and is later written through
        # must appear in a truthiness test somewhere in the function.
        # (findall with one group yields strings -- a set, not a dict; dict()
        #  would try to unpack 'tbox' into a key/value pair)
        held = set(re.findall(
            r"(?:const|let)\s+(\w+)\s*=\s*(?:\$\$\(|document\.getElementById\(|"
            r"document\.querySelector\()", poll))
        held |= set(re.findall(
            r",\s*(\w+)\s*=\s*(?:\$\$\(|document\.getElementById\(|"
            r"document\.querySelector\()", poll))
        unchecked = []
        for name in held:
            written = re.search(r"\b%s\s*\.\s*(?:textContent|innerHTML|hidden)\s*="
                                % re.escape(name), poll)
            if not written:
                continue
            # a name can be guarded as the FIRST, MIDDLE or LAST term of an
            # && chain, or negated, or tested alone -- the first version of
            # this pattern missed the last-term case and flagged correct code
            guarded = re.search(
                r"(?:!\s*%s\b|\b%s\s*&&|&&\s*%s\b|\bif\s*\(\s*%s\s*\))"
                % ((re.escape(name),) * 4), poll)
            if not guarded:
                unchecked.append(name)
        check("[-] ...nor through a variable that was never null-checked",
              not unchecked, str(unchecked))
        check("[+] ...over a poller that really does hold element refs",
              len(held) >= 4, "%d found" % len(held))
        # and the specific guard that replaced the crash
        check("the slate band no-ops when its markup is absent",
              "if (!tbox || !tmeta || !tcards || !tlabel)" in poll)
        check("the live band keeps its own guard", "if (!box) return;" in poll)
        check("...and its cards element too", "if (!lc) return;" in poll)
        # a cap must state what it is hiding
        check("the slate cap says how many are not shown",
              "showing the first" in poll and "more" in poll)
        check("the live cap says how many are not shown",
              "more live" in poll and "showing " in poll)

    print("\n6. The line scores reconcile with the result they sit beside")
    # ⚠ THE STRIP AND THE SCORE ARE TWO RENDERINGS OF ONE FACT, so they can
    # disagree -- and a row showing 3-0 above line scores that only add to 2-1
    # is worse than showing neither. Counting sets won from the per-set points
    # must reproduce the reported match score for every match on file. This is
    # the check that catches a feed change or a parsing slip, and it costs
    # nothing because the data is already in the page.
    import json
    page = io.open(PAGE, encoding="utf-8").read() if os.path.exists(PAGE) else ""
    k = page.find("const LEDGER = [")
    if k < 0:
        check("the ledger is in the page", False)
    else:
        i = page.find("[", k)
        d, j, instr, esc = 0, i, False, False
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
            elif c in "[{":
                d += 1
            elif c in "]}":
                d -= 1
                if d == 0:
                    break
            j += 1
        led = json.loads(page[i:j + 1])
        check("[+] there are finals to check at all", len(led) > 0,
              "%d" % len(led))
        withsets = [g for g in led if g.get("sets")]
        check("[+] ...and they carry line scores", len(withsets) > 0,
              "%d of %d" % (len(withsets), len(led)))
        wrong = []
        for g in withsets:
            aw = sum(1 for sv in g["sets"] if sv[0] > sv[1])
            hw = sum(1 for sv in g["sets"] if sv[1] > sv[0])
            if aw != g.get("as") or hw != g.get("hs"):
                wrong.append("%s-%s %s-%s vs line %d-%d"
                             % (g.get("a"), g.get("h"), g.get("as"),
                                g.get("hs"), aw, hw))
        check("[-] every match score is reproduced by its own line scores",
              not wrong, str(wrong[:2]))
        # a completed set cannot be tied -- one side has to have won it
        ties = ["%s-%s %s" % (g.get("a"), g.get("h"), sv)
                for g in withsets for sv in g["sets"] if sv[0] == sv[1]]
        check("[-] no completed set is tied", not ties, str(ties[:2]))

    print("")
    if FAIL:
        print("FAILED: %s" % "; ".join(FAIL))
        return 1
    print("SCOREBOARD DENSITY GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
