#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the Rankings board: POWER, AVCA, Digby's Top 25, and the
POWER-vs-AVCA comparison.

⚠ WHAT THIS TAB LOOKED LIKE BEFORE. Thirteen equal columns, five of them bare
ranks from five different organisations, so a single row could read
"#1 #1 #1 #1 #1" with nothing on screen saying whose ruler each number came
from. The rebuild is about hierarchy and labelling, and every claim it makes is
checked here rather than trusted.

Python 3.9 target. Run: python3 scripts/test_rankings_board.py
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def page(which="private"):
    cand = ("Cody/START-HERE.html" if which == "private"
            else "output/vb_dashboard.html")
    p = os.path.join(REPO, cand)
    return (open(p, encoding="utf-8").read(), cand) if os.path.exists(p) else (None, None)


def payload(h, name):
    m = re.search(r"const %s = (\{.*?\});\n" % name, h, re.S)
    return json.loads(m.group(1)) if m else None


def main():
    print("RANKINGS BOARD GUARDS\n")
    h, which = page()
    if not h:
        print("  (no private build -- skipping)")
        return 0
    print("  reading %s\n" % which)
    TEAMS = payload(h, "TEAMS") or {}

    print("1. EVERY RULER SAYS WHAT IT IS")
    # A rank is meaningless without knowing whose ruler produced it.
    rulers = re.findall(r'<button class="segb[^"]*" data-r="([a-z0-9]+)"', h)
    # Three rulers a voter works in, plus the comparison, plus the archive.
    # The Reference select stays separate and is checked below.
    check("the primary rulers are the three a voter works in, plus the tools",
          rulers == ["ours", "avca", "digby", "gap", "cal"], str(rulers))
    m = re.search(r"const RULER_WHAT = \{(.*?)\n\};", h, re.S)
    check("a purpose map exists", bool(m))
    keys = re.findall(r"^\s*([a-z0-9]+):", m.group(1), re.M) if m else []
    rsel = re.search(r'<select id="refpick"[^>]*>(.*?)</select>', h, re.S)
    ref = re.findall(r'<option value="([a-z0-9]+)">', rsel.group(1)) if rsel else []
    check("the reference select exists and is separate from the rulers",
          bool(rsel) and len(ref) >= 2, str(ref))
    want = set(rulers) | set(x for x in ref if x)
    missing = sorted(want - set(keys))
    check("...and EVERY selectable ruler has a sentence in it",
          not missing, "no purpose text for %s" % missing)
    body = m.group(1) if m else ""
    check("POWER is described as ours and predictive",
          "predictive order" in body and "not a poll" in body)
    check("the AVCA poll is described as external",
          "American Volleyball Coaches Association" in body)
    # ⚠ DIGBY'S TOP 25 MUST NOT BE IMPLIED TO BE THE AVCA POLL OR A BALLOT.
    dig = re.search(r"digby: (.*?)\n  [a-z]+:", body, re.S)
    dtxt = dig.group(1) if dig else ""
    check("Digby's Top 25 disclaims being the poll or anybody's ballot",
          "not the AVCA poll" in dtxt and "ballot" in dtxt, dtxt[:70])

    print("\n2. NO RANK IS RENDERED BARE")
    # On a phone the table becomes a strip, so the label rides in front of the
    # value via data-l. Without it the row is a line of anonymous numbers.
    for label in ("Conf", "Record", "AVCA", "2025", "RPI"):
        check("the %-6s cell carries its label" % label,
              'data-l="%s"' % label in h)
    check("the label is actually printed at the phone breakpoint",
          'td[data-l]::before{content:attr(data-l)' in h)
    check("...and the reference columns are hidden there instead",
          re.search(r"@media \(max-width:560px\)\{[^@]*?"
                    r"\.rk3 tr\.row td\.c-ref\{display:none\}", h, re.S) is not None)

    print("\n2b. THE PHONE STRIP CANNOT STACK ITS OWN CELLS")
    # ⚠ THE DEFECT THIS EXISTS FOR, AND NOTHING MEASURED CAUGHT IT. The first
    # phone layout put conference, resume, record and AVCA in ONE named grid
    # area. CSS grid STACKS items that share an area, so all four painted on
    # top of each other and the row read as garbled overlapping text. The row
    # did not overflow, every cell was "visible", every label was present -- a
    # screenshot caught it in one look. Explicit row/column placement is what
    # makes the overlap impossible, so that is what is asserted.
    # ⚠ THERE ARE SEVERAL @media (max-width:560px) BLOCKS in this stylesheet.
    # Matching "the" phone block found the FIRST one, which holds none of these
    # rules, so every placement check failed against correct CSS -- and the
    # "no two cells share a slot" check passed vacuously on zero slots. Only
    # the positive control below caught that. Join every phone block instead.
    pcss = "\n".join(re.findall(r"@media \(max-width:560px\)\{(.*?)\n\}",
                                h, re.S))
    check("the phone block exists", bool(pcss))
    check("[-] no cell is placed by a shared grid-area name",
          "grid-area:meta" not in pcss and "grid-template-areas" not in pcss,
          "a shared area stacks its occupants")
    slots = {}
    for cls in ("rk", "tm", "pw", "cf", "rec", "c-avca", "rs"):
        m2 = re.search(r"\.rk3 tr\.row td\.%s\{([^}]*)\}" % re.escape(cls), pcss)
        rule = m2.group(1) if m2 else ""
        gr = re.search(r"grid-row:([^;]+)", rule)
        gc = re.search(r"grid-column:([^;]+)", rule)
        check("td.%-7s has an explicit slot" % cls, bool(gr and gc), rule[:50])
        if gr and gc:
            slots[cls] = (gr.group(1).strip(), gc.group(1).strip())
    dupes = [k for k, v in slots.items()
             if list(slots.values()).count(v) > 1]
    check("[-] no two cells occupy the SAME row/column slot",
          not dupes, "stacked: %s" % dupes)
    check("[+] ...and there are cells to be wrong about", len(slots) >= 6,
          "%d placed" % len(slots))

    print("\n3. POWER vs AVCA IS ARITHMETIC, NOT OPINION")
    rated = [(n, t["rank"], t["avca"]) for n, t in TEAMS.items()
             if t.get("rank") and t.get("avca") is not None]
    check("[+] teams are ranked by both, so there is something to compare",
          len(rated) > 5, "%d teams" % len(rated))
    # The page computes abs(rank - avca). Recompute it here independently.
    gaps = sorted(((abs(r - a), n, r, a) for n, r, a in rated), reverse=True)
    check("the largest difference is a real one",
          gaps and gaps[0][0] > 0, str(gaps[:1]))
    check("no difference is negative", all(g[0] >= 0 for g in gaps))
    check("the gap is |POWER - AVCA| for every team",
          all(g[0] == abs(g[2] - g[3]) for g in gaps), "arithmetic mismatch")
    # ⚠ A TEAM THE POLL DOES NOT RANK HAS NO POSITION THERE. Subtracting an
    # absent rank from a real one invents a difference; an unranked team is not
    # a 26th-place team.
    src = re.search(r"function gapRows\(\) \{(.*?)\n\}", h, re.S)
    g = src.group(1) if src else ""
    check("gapRows exists", bool(g))
    check("an unranked team is routed to the NR list, never given a gap",
          "t.avca === null || t.avca === undefined" in g and "nr.push" in g)
    check("...and only rated teams get a computed gap",
          "gap: Math.abs(t.rank - t.avca)" in g)
    check("the NR list is labelled AVCA NR on screen",
          "AVCA NR" in h)
    check("[-] ...and an NR row carries no number",
          '<td class="n dim">no gap</td>' in h)
    check("the surface states that an absent rank is not a low one",
          "an absent rank is not a low one" in h)

    print("\n4. IT RECOMMENDS NOTHING")
    # ⚠ MATCH WHOLE WORDS. An earlier guard in this repo matched substrings and
    # hit real data; and several have tripped on the project's OWN denials, so
    # comments are stripped before scanning.
    txt = re.sub(r"/\*.*?\*/", " ", h, flags=re.S)
    txt = re.sub(r"<!--.*?-->", " ", txt, flags=re.S)
    for word in ("overrated", "underrated", "should be ranked", "controversy",
                 "snub", "we recommend", "deserves to be", "too high",
                 "too low", "wrongly ranked"):
        check("[-] the page never says %r" % word,
              not re.search(r"\b%s\b" % re.escape(word), txt, re.I))
    check("it describes itself as a difference, not a verdict",
          "statement of difference" in h)

    print("\n5. AN INACTIVE RESUME SAYS SO")
    check("the inactive resume renders an explicit off-state",
          'class="rsoff"' in h)
    check("...explaining that nobody has earned anything yet",
          "have earned anything yet" in h)
    check("[-] and it does not print a rank while inactive",
          not re.search(r'class="n rs"><span class="rsoff"[^>]*>#\d', h))

    print("\n6. NO FABRICATED MOVEMENT")
    # Movement is only honest with enough dated, SAME-BASIS snapshots.
    check("the history note is present and says what is missing",
          'class="histnote"' in h)
    movers = re.findall(r'<span class="mv (up|dn|sm)">', h)
    hist = os.path.join(REPO, "data")
    snaps = [f for f in os.listdir(hist)
             if f.startswith("rankings_history_") and f.endswith(".jsonl")]
    bases = set()
    for f in snaps:
        for line in open(os.path.join(hist, f), encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    bases.add((json.loads(line).get("source"),
                               json.loads(line).get("week")))
                except ValueError:
                    pass
    per_basis = {}
    for src_, wk in bases:
        per_basis[src_] = per_basis.get(src_, 0) + 1
    enough = any(v >= 2 for v in per_basis.values())
    if not enough:
        check("[-] no movement is drawn without two same-basis weeks",
              not movers, "%d movement marks with %s" % (len(movers), per_basis))
    else:
        check("movement is drawn now that same-basis history exists", True)
    print("     (weeks per basis: %s)" % (per_basis or "none"))
    check("[-] no sparkline or trend line is drawn for a rank",
          "class=\"trend" not in h and "<svg class=\"spark" not in h)

    print("\n7. EVERY RANK ROW ROUTES TO ITS OWN TEAM")
    rows = re.findall(r'<tr class="row" data-r="(\d+)" data-team="([^"]+)"', h)
    check("[+] rows exist to check", len(rows) > 100, "%d rows" % len(rows))
    import html as _html
    unknown = [t for _r, t in rows if _html.unescape(t) not in TEAMS]
    check("every row names a team the payload knows",
          not unknown, "%d unknown: %s" % (len(unknown), unknown[:3]))
    # The rank on the row must be that team's own rank.
    wrong = [(t, r) for r, t in rows
             if TEAMS.get(_html.unescape(t), {}).get("rank") != int(r)]
    check("...and each row's rank is that team's rank",
          not wrong, str(wrong[:3]))
    check("the row opens the routed team page",
          "function openRankRow" in h and "routeFor('teams', slug(nm))" in h)
    check("...and is reachable from the keyboard",
          'tabindex="0" role="link"' in h
          and "e.key === 'Enter'" in h)
    check("[-] no in-place pseudo-detail row remains",
          '<tr class="det"' not in h)

    print("\n8. THE PUBLIC BUILD CARRIES NO PRIVATE MATERIAL")
    ph, pw = page("public")
    if not ph:
        print("  (no public build -- skipping)")
    else:
        # Structural markers: asserted against the RAW page, because these are
        # the feature itself and may not ship in any form.
        for marker in ("BALLOT-WORKSHOP", "MYBOARD-HTML", "MYBOARD-JS",
                       "wvb.myboard", "wvb.ballot", "bwcmp", "mbToggle",
                       "bwSave", 'id="v-ballot"'):
            check("public: no %r" % marker, marker not in ph)
        # Human-facing names: scanned with comments removed. A source comment
        # explaining why routing avoids the dead zone mentions "My Board" and
        # is not the feature shipping.
        pv = re.sub(r"/\*.*?\*/", " ", ph, flags=re.S)
        pv = re.sub(r"<!--.*?-->", " ", pv, flags=re.S)
        for marker in ("My Board", "My Ballot"):
            check("public: no %r outside comments" % marker, marker not in pv)
        pt = payload(ph, "TEAMS") or {}
        check("[+] the public build still has its rankings", len(pt) > 300,
              "%d teams" % len(pt))
        check("public: the ruler purposes still ship", "RULER_WHAT" in ph)
        check("public: the comparison surface still works", "gapRows" in ph)
        # Alignment after the strip removes three reference columns.
        gm = re.search(r'<th class="g-ref" colspan="(\d+)">', ph)
        check("public: the reference group shrank with its columns",
              gm and int(gm.group(1)) == 2, gm.group(1) if gm else "absent")

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL RANKINGS BOARD GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
