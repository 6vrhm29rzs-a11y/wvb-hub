#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for wayfinding and daily-use truth.

Four things this phase fixed, each of which was WRONG WHILE THE UNDERLYING DATA
WAS RIGHT -- which is why none of them was caught by an existing suite:

  1. A direct route painted the correct tab as selected AND left a gold ring on
     the previously-clicked one. aria-selected was right the whole time.
  2. A rank rendered as a bare "#21" whose ruler the reader had to infer. Every
     number correct; the screen ambiguous.
  3. Scores opened on 472 matches sorted newest-first, which on an August
     evening means December fixtures first.
  4. The team page opened with a paragraph above the crest, and the first
     attempt to compress it split "3.472" into a sentence boundary and printed
     "472" as though it were a figure.

Python 3.9 target. Run: python3 scripts/test_wayfinding.py
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


def code_only(s):
    """Comments removed -- a guard must not find its own explanation."""
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"(?m)^\s*#(?!\w).*$", " ", s)
    return s


def main():
    print("WAYFINDING AND DAILY-USE GUARDS\n")
    h, which = page()
    if not h:
        print("  (no built page -- skipping)")
        return 0
    print("  reading %s\n" % which)
    import build_hub as BH
    S = open(os.path.join(REPO, "scripts", "build_hub.py"),
             encoding="utf-8").read()
    C = code_only(S)

    # ── 1. ONE LOCATION, ONE ACTIVE STATE ───────────────────────────────
    print("1. ONE LOCATION, ONE ACTIVE STATE")
    # ⚠ THE COLOURS MUST DIFFER. This is the actual defect: the focus ring and
    # the selected underline were both var(--amber), so a focused-but-not-
    # selected tab was indistinguishable from the selected one.
    m = re.search(r"nav button:focus-visible\{([^}]*)\}", h)
    focus = m.group(1) if m else ""
    check("the nav focus ring exists", bool(focus))
    check("[-] ...and is NOT the selection colour",
          "var(--amber)" not in focus and "var(--cs-cyan)" in focus,
          "focus and selection in one colour is the double-active state")
    check("selection is still marked by the gold rule",
          "background:var(--amber)" in h)
    check("focus moves to the routed region, it is not merely blurred",
          "el.focus({ preventScroll: true })" in C,
          "blurring drops a keyboard reader to nowhere")
    check("[-] ...and only when focus was on a nav control",
          "a.closest('nav')" in C,
          "otherwise it steals focus out of a filter box mid-typing")
    check("a programmatic focus shows no ring to a mouse user",
          "main section:focus{outline:none}" in h)
    check("[+] ...but a keyboard user still gets one",
          "main section:focus-visible{outline:2px solid var(--cs-cyan)" in h)

    # ── 2. NEVER A RANK WITHOUT ITS RULER ───────────────────────────────
    print("\n2. NEVER A RANK WITHOUT ITS RULER")
    check("the ruler table exists in Python", bool(getattr(BH, "RULERS", None)))
    check("[-] ...and the JS table is EMITTED from it, not written twice",
          '.replace("{{RULERS_JSON}}"' in S,
          "two tables is how the same ranking gets two names")
    payload = re.search(r"const RULERS = (\{.*?\});", h)
    js_rulers = json.loads(payload.group(1)) if payload else {}
    check("the page carries the table", bool(js_rulers))
    check("[-] ...and it matches the Python one exactly",
          {k: list(v) for k, v in BH.RULERS.items()} == js_rulers,
          "python=%d js=%d" % (len(BH.RULERS), len(js_rulers)))
    # basis is required -- there is no one-argument form left
    check("rank_badge() requires a basis",
          "def rank_badge(basis, v" in S)
    try:
        BH.rank_badge("no-such-ruler", 4)
        loud = "rank basis?" in BH.rank_badge("no-such-ruler", 4)
    except Exception:
        loud = True
    check("[-] an unknown basis is LOUD, never a bare number", loud)
    check("[+] ...and a known basis renders the label visibly",
          "AVCA" in BH.rank_badge("avca", 15) and "#15" in BH.rank_badge("avca", 15))
    check("the loud marker never reaches the built page",
          '<i class="rnk rnkbad"' not in re.sub(
              r"function rankHTML.*?\n\}", "", h, flags=re.S).replace(
              "'<i class=\"rnk rnkbad\" title=\"no ruler named\">rank basis?</i> '", ""),
          "a rank rendered with no ruler named is on the page")
    # THE KANSAS / PITTSBURGH CASE, BOTH SIDES
    print("\n2b. THE KANSAS / PITTSBURGH CASE")
    check("the Rally Tape names its ruler at the number",
          "rankHTML('avca', rk, true)" in C)
    check("today's read names its ruler at the number",
          "rankHTML('avca', m.ar, true)" in C)
    check("the readiness panel names ITS ruler -- and it is a different one",
          'rank_badge("digby", c["away_rank"]' in S,
          "preflight_live ranks by Digby's Top 25, not the AVCA poll")
    check("[-] ...and it asks for TEXT, because that field is not HTML",
          "text=True" in S,
          "markup in a text field prints the tag on screen")
    # no bare rank concatenations left on a rank-bearing field
    RANKY = (r"(?:\bar\b|\bhr\b|away_rank|home_rank|\.rank\b|\.avca\b|"
             r"\.vt\b|\.rpi\b|\.massey\b|rank25|resume_rank|\brk\b)")
    LABELS = [v[0] for v in BH.RULERS.values()] + \
             [v[1] for v in BH.RULERS.values()] + ["rankHTML", "rank_badge",
                                                   "rankText", "rank("]
    # ⚠ TWO FALSE POSITIVES TAUGHT ME TO SCAN A WINDOW, NOT A LINE. These are
    # multi-line expressions: `bits.push('<span class="bwe ref"><i>AVCA</i> ' +`
    # puts the ruler on the line ABOVE the number, and `chip('R\u00c9SUM\u00c9',
    # ...)` writes its label as a unicode escape that no literal comparison
    # matches. Both were correctly labelled on screen. A guard that fires on
    # correct code is how a suite stops being believed.
    lines = C.split("\n")
    def unesc(x):
        return re.sub(r"\\u([0-9a-fA-F]{4})",
                      lambda m: chr(int(m.group(1), 16)), x)
    bare = []
    for i, line in enumerate(lines, 1):
        if not re.search(r"""['"]#['"]\s*\+""", line):
            continue
        if not re.search(RANKY, line):
            continue
        window = unesc(" ".join(lines[max(0, i - 2):i + 1]))
        if any(lb in window for lb in LABELS):
            continue
        bare.append("%d: %s" % (i, line.strip()[:70]))
    check("no rank is concatenated to a '#' without a ruler beside it",
          not bare, "; ".join(bare[:2]))
    check("[+] ...over a file that really does render ranks",
          C.count("rankHTML(") >= 8, "%d uses" % C.count("rankHTML("))

    # ── 3. SCORES OPENS ON THE DAY ──────────────────────────────────────
    print("\n3. SCORES OPENS ON THE DAY")
    check("the default ledger state is today", "let LEDGER_STATE = 'today';" in h)
    check("[-] ...not the full ledger",
          "let LEDGER_STATE = 'all';" not in h)
    check("the full ledger is still reachable, and named",
          'data-ls2="all">Full ledger<' in h)
    check("every prior state filter survives",
          all('data-ls2="%s"' % k in h
              for k in ("today", "live", "final", "upcoming", "all")))
    check("the date jump survives", 'id="ldate"' in h and 'id="lclear"' in h)
    for lane in ("Live now", "Final today", "Still to come",
                 "Next match window", "Most recent finals"):
        check("the day view has a '%s' lane" % lane, "'" + lane + "'" in C)
    check("a lane is capped and NAMES the remainder",
          "LANE_CAP" in C and "Show ' + rest + ' more" in C,
          "195 rows under a nicer heading is the same wall")
    check("[-] ...and the remainder is one click from being shown",
          "LEDGER_OPEN[k] = !LEDGER_OPEN[k]" in C)
    check("lanes sort by time, with ranked pairings lifted",
          "(a.ep || 0) - (b.ep || 0)" in C)
    # ⚠ dayLabel() returns the WORD "Today"
    check("[-] an empty today does not say 'matches on Today'",
          "'No Division-I matches today.'" in C,
          "dayLabel() returns a relative word; it needs its own sentence")
    check("the count describes the day it names, not the fallback",
          "' \\u00b7 none'" in C or "\\u00b7 none" in C)

    # ── 4. THE TEAM PAGE ────────────────────────────────────────────────
    print("\n4. THE TEAM PAGE LEADS WITH THE TEAM")
    # ⚠ NOT THE SENTINEL COMMENT -- code_only() strips comments, which is the
    # point of it, so anchoring on COURTSIGNAL-THEAD-BEGIN resolved to -1 and
    # the ordering check compared against a position that did not exist.
    # Anchor on the markup itself.
    # ⚠ AND THE CALL SITE, NOT THE DEFINITION. `C.index("scoutRead(t)")`
    # found `function scoutRead(t) {` -- which sits far ABOVE the assembly --
    # so the ordering check compared the wrong two positions and reported the
    # note as rendering before the crest when it does not.
    # ⚠ AND MATCH THE CALL SHAPE, NOT ITS EXACT ARGUMENTS. This was pinned to
    # the literal "scoutRead(t) +", so adding the team argument the function
    # needs -- scoutRead(t, name) -- failed a guard about ORDERING, which the
    # rename does not touch. Anchor on what the check is actually about.
    _m = re.search(r"scoutRead\([^)]*\)\s*\+", C)
    order = _m.start() if _m else -1
    TH = '\'<div class="thead cs-court cs-prog"\''
    thead = C.index(TH) if TH in C else -1
    glance = C.index("glanceHtml +") if "glanceHtml +" in C else -1
    check("identity, then the glance, then the scouting note",
          0 < thead < glance < order,
          "thead=%d glance=%d scout=%d" % (thead, glance, order))
    check("[-] the long prose no longer renders above the crest",
          "'<div class=\"digby\"><div class=\"digby-tag\">' + DIGBY_FACE" not in C)
    check("the full note is kept behind a disclosure",
          "Full scouting note" in h and "<details" in h)
    check("the provenance line stays OUT of the disclosure",
          C.index("digby-note") > C.index("scoutmore"),
          "a reader who never opens the note still needs to know its basis")
    check("[-] no new prose is generated -- it is a split",
          "csSentences(String(t.digby))" in C)

    print("\n4b. THE SPLITTER CANNOT INVENT A NUMBER")
    m2 = re.search(r"function csSentences\(text\) \{(.*?)\n\}", h, re.S)
    body = m2.group(1) if m2 else ""
    check("csSentences exists", bool(body))
    check("[-] a period between digits is a decimal point",
          "isD(text[i - 1]" in body and "isD(text[i + 1]" in body,
          "'3.472' split naively prints '472' as though it were a figure")
    check("sentences are rejoined with a separator",
          "(lead ? ' ' : '') + parts[i]" in C,
          "the scanner skips the whitespace between them")
    # a real reproduction, run against the shipped scanner via a JS-free port
    def sentences(text):
        out, start, i = [], 0, 0
        isD = lambda c: c.isdigit()
        CLOSERS = '.!?")]”’'
        while i < len(text):
            c = text[i]
            if c not in ".!?":
                i += 1
                continue
            if c == "." and i and isD(text[i - 1]) and i + 1 < len(text) \
                    and isD(text[i + 1]):
                i += 1
                continue
            j = i + 1
            while j < len(text) and text[j] in CLOSERS:
                j += 1
            if j >= len(text):
                out.append(text[start:])
                start = len(text)
                break
            if not text[j].isspace():
                i += 1
                continue
            out.append(text[start:j])
            start = j
            while start < len(text) and text[start].isspace():
                start += 1
            i = start
        if start < len(text):
            out.append(text[start:])
        return [x for x in out if x.strip()]

    NEB = ("Nebraska went 33-1. Murray led the team at 4.215 points per set "
           "and Jackson added 3.472, and both are returning. Allick scored "
           "333.5 points before departing.")
    got = sentences(NEB)
    check("the measured case splits into 3 sentences, not 5",
          len(got) == 3, str(len(got)))
    check("[-] ...and no fragment begins with a decimal's tail",
          not any(re.match(r"^\d", x.strip()) for x in got),
          str([x[:14] for x in got]))
    check("[+] ...while real sentence ends still split",
          got[0].strip() == "Nebraska went 33-1.", repr(got[0]))
    # NEGATIVE CONTROL: the naive regex must fail this same case
    naive = re.findall(r"[^.!?]+[.!?]+(?:\s|$)", NEB)
    check("[NEG] the regex this replaced DOES produce the bad fragment",
          any(re.match(r"^\d", x.strip()) for x in naive),
          "if this passes, the test above is not testing anything")
    check("nothing is lost in the split",
          "".join(x.strip() for x in got).replace(" ", "")
          == NEB.replace(" ", ""))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL WAYFINDING GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
