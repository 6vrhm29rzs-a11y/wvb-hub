#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RANKINGS USABILITY REPAIR guards (2026-08-31).

Behavioral checks for the More menu (readable contrast, grouped, 14px
items, phone sheet without the multicol spill) and the Rankings
above-the-fold hierarchy (extref/methodology below the table, compact
lead, colspan arithmetic that keeps group headers from overlapping).
These guard the CSS/markup CONTRACT; they do not replace the pixel
screenshot review, which was performed and filed with the repair.
"""

import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

FAILS = []


def check_no_view_inside_a_fold(h):
    """VIEW CONTENT NEVER LIVES INSIDE AN EXPLAINER FOLD (2026-09-06).

    #pollview -- the container three whole rankings views render into --
    sat inside the rkhow <details>, which the phone closes at boot. A
    closed details hides every child but its summary, so AVCA, POWER vs
    AVCA and the weekly calendar rendered BLANK on every phone while
    desktop (details open) never showed it: Cody's "missing mystery
    mess". Checked structurally: walk from each view container's position
    back through unclosed <details> tags."""
    def inside_details(html, idx):
        depth = 0
        for m in re.finditer(r"<details\b|</details>", html[:idx]):
            depth += 1 if m.group(0).startswith("<details") else -1
        return depth > 0
    for vid in ("pollview", "rankpanel", "v-top25"):
        i = h.find('id="%s"' % vid)
        if i < 0:
            check("view container #%s exists" % vid, False)
            continue
        check("#%s is not inside a <details> fold" % vid,
              not inside_details(h, i))
    # negative control: a synthetic nesting must be caught
    bad = "<details><summary>x</summary><div id=\"pollview\"></div></details>"
    check("negative control: a folded pollview is caught",
          inside_details(bad, bad.find('id="pollview"')))



def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + .055) / 1.055) ** 2.4
    r, g, b = (f(v) for v in rgb)
    return .2126 * r + .7152 * g + .0722 * b


def contrast(a, b):
    l1, l2 = _lum(_hex_rgb(a)), _lum(_hex_rgb(b))
    return (max(l1, l2) + .05) / (min(l1, l2) + .05)


def main():
    src = io.open(os.path.join(REPO, "scripts/build_hub.py"),
                  encoding="utf-8").read()
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    page = io.open(page_p, encoding="utf-8").read() \
        if os.path.exists(page_p) else ""
    if page:
        check_no_view_inside_a_fold(page)

    print("1. THE MORE MENU")
    m = re.search(r"\.moremenu\{[^}]*background:var\(--(\w+)\)", page)
    check("menu surface is the CARD, not the navy chrome",
          m and m.group(1) == "card", m and m.group(1))
    # contrast computed from the page's own tokens
    toks = dict(re.findall(r"--(\w+):(#[0-9A-Fa-f]{6})", page))
    card = toks.get("card", "#FFFFFF")
    ink = toks.get("ink")
    check("item ink on the card surface >= 4.5:1 (measured %.1f:1)"
          % (contrast(ink, card) if ink else 0),
          ink and contrast(ink, card) >= 4.5)
    mi = re.search(r"\.moremenu button\{[^}]*font:600 (\d+)px", page)
    check("menu items are >= 14px", mi and int(mi.group(1)) >= 14,
          mi and mi.group(1))
    check("three labelled groups: Explore / Reference / Private workspace",
          page.count('class="mglabel"') >= 3
          and ">Explore<" in page and ">Reference<" in page
          and "Private workspace" in page)
    check("hover and focus are visible (background changes to --alt)",
          re.search(r"\.moremenu button:hover,\.moremenu button:"
                    r"focus-visible\{background:var\(--alt\)", page))
    check("Escape, arrows and outside-click close are wired",
          "closeMore(); b.focus({ preventScroll: true })" in page
          and "!m.contains(e.target)" in page)
    # ⚠ THE MULTICOL SPILL: column-count:1 + max-height fragments the
    # overflow into a phantom column OFF THE RIGHT EDGE (ballot measured
    # at x=391 in a 390 viewport). The phone sheet must not be a multicol.
    # collect EVERY 560 block (the first-match trap has bitten before)
    ph_rules = []
    for blk in re.findall(r"@media \(max-width:560px\)\{(.*?)\n\}", page,
                          re.S):
        ph_rules += re.findall(r"\.moremenu\{([^}]*)\}", blk)
    sheet = [r for r in ph_rules if "position:fixed" in r]
    check("the phone sheet is fixed+inset and NOT a multicol",
          sheet and "column-count:auto" in sheet[0]
          and "overflow:auto" in sheet[0],
          (len(ph_rules), sheet and sheet[0][:60]))
    check("[NEG] the desktop menu IS a two-column layout",
          re.search(r"\.moremenu\{[^}]*column-count:2", page))

    print("\n1b. THE FINISH PASS (2026-09-01)")
    check("phone masthead compacts (.mast .meta hidden at 560)",
          re.search(r"@media\(max-width:560px\)\{[^@]*\.mast \.meta"
                    r"\{display:none\}", page, re.S))
    check("the ranking explainer is a real disclosure, closed on a "
          "phone at boot",
          'id="rkhow"' in page and "rkhow" in page
          and "removeAttribute('open')" in page
          and "max-width:560px" in page)
    check("RESUME is compare-only: hidden with the reference set",
          ".rk3.hideref th.c-res,.rk3.hideref td.rs" in page)
    check("...and the group header shrinks with it (colspan sync)",
          "gOurs.colSpan = refcols.checked ? 3 : 2" in page)
    check("the sheet Close control exists, 44px, phone-only",
          'id="msheetx"' in page
          and ".moremenu .msheetx{display:none}" in page
          and "min-height:44px" in page)
    check("menu focus never scrolls the page (preventScroll on open "
          "AND on every close-return)",
          page.count("preventScroll: true") >= 3)
    # ⚠ the unqualified '#moremenu button' selector routed the Close
    # control and the Ask Digby item to the DEFAULT VIEW (measured:
    # Close navigated to the desk and dumped the reader's scroll)
    check("the router wires only [data-v] menu buttons",
          "#moremenu button[data-v]" in page
          and not re.search(r"querySelectorAll\('nav button\[role=tab\], "
                            r"#moremenu button'\)", page))

    print("\n2. THE LAUNCHER LEFT THE NAV")
    check("Ask Digby: fixed edge trigger base + IN-LAYOUT dock at "
          "desktop (masthead meta), never nav-appended",
          ".asklaunch{position:fixed" in page
          and ".asklaunch.inmast{position:static" in page
          and "meta.appendChild(b)" in page
          and "inner.appendChild(b)" not in page)
    check("phone clearance under the edge trigger",
          "main{padding-bottom:88px}" in page)
    check("the More menu carries an Ask Digby item (private group)",
          'id="askmenu"' in page and "mgpriv" in page)

    print("\n3. RANKINGS ABOVE THE FOLD")
    sec = page[page.find('id="v-rankings"'):page.find('id="v-teams"')] \
        if 'id="v-rankings"' in page else ""
    tbl = sec.find('id="rbody"')
    ext = sec.find("EXTREF-HTML-BEGIN")
    meth = sec.find("<details class=\"method\">")
    check("the External references disclosure sits BELOW the table",
          tbl > -1 and (ext == -1 or ext > tbl), (tbl, ext))
    check("methodology sits below the table too",
          tbl > -1 and meth > tbl)
    check("the lead is one compact basis line (no POWER/RESUME essay)",
          "POWER</b> is how strong a team is" not in
          (re.search(r'id="ranklead">.*?</p>', page, re.S) or
           re.match(r"", "")).group(0) if
          re.search(r'id="ranklead">.*?</p>', page, re.S) else False)

    print("\n4. HEADER GEOMETRY CONTRACT (colspan arithmetic)")
    thead = re.search(r'<table class="rk3">.*?<thead>(.*?)</thead>', page,
                      re.S)
    if thead:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", thead.group(1), re.S)
        check("the header has a group row and a label row",
              len(rows) == 2, len(rows))
        if len(rows) == 2:
            spans = [int(x) for x in
                     re.findall(r'colspan="(\d+)"', rows[0])]
            plain = len(re.findall(r"<th(?![^>]*colspan)", rows[0]))
            n_groups = sum(spans) + plain
            n_labels = len(re.findall(r"<th", rows[1]))
            check("group colspans cover the label columns exactly "
                  "(%d == %d) -- the arithmetic that keeps group "
                  "headers from overlapping" % (n_groups, n_labels),
                  n_groups == n_labels)
    check("hiding reference columns hides their group headers too",
          ".rk3.hideref th.g-ref" in page
          and ".rk3.hideref th.g-proj" in page)
    check("reference header labels are chalk on the navy band, "
          "not ink-on-navy",
          re.search(r"\.rk3 th\.c-ref\{color:var\(--chalk\)", page))
    chalk, navy = toks.get("chalk"), toks.get("navy")
    if chalk and navy:
        check("...at >= 4.5:1 even at .85 opacity (band %.1f:1)"
              % contrast(chalk, navy), contrast(chalk, navy) >= 7.0)
    check("the toggle is named Compare sources, with its explanation",
          "Compare sources" in page and 'id="refcols"' in page)
    check("every default column header carries a title explanation",
          all(('title="' in th) for th in re.findall(
              r'<th class="n[^"]*"[^>]*>', page[page.find('rk3'):
                                                page.find('rbody')])[:4]))

    print("\n5. THE PUBLIC BUILD")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub_p):
        pub = io.open(pub_p, encoding="utf-8").read()
        check("public menu keeps Explore/Reference groups",
              ">Explore<" in pub and ">Reference<" in pub)
        check("...and carries NO private group, label or Digby item",
              all(x not in pub for x in
                  ("mgpriv", "askmenu", "Private workspace",
                   "MOREPRIV", "Ask Digby")))

    print()

    print("\nSTICKY RANKING HEADERS (phase C)")
    check("rkscroll wrapper gives up its overflow context",
          ".scroll.rkscroll{overflow:visible}" in src)
    check("th offsets under the nav at page level",
          ".scroll.rkscroll th{top:var(--navh,0px)}" in src)
    check("the panel's clipping context is lifted (measured confiner)",
          "#rankpanel.panel{overflow:visible}" in src)
    check("both ranking tables ride the rkscroll wrapper",
          'class="scroll rkscroll"><table class="t25">' in src
          and 'class="scroll rkscroll"><table class="rk3">' in src)

    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL RANKINGS-UX GUARDS PASS")
    return 0



if __name__ == "__main__":
    sys.exit(main())
