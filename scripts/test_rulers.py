#!/usr/bin/env python3
"""Guards for THE RULERS -- name, colour, and the badge that renders them.

⚠ THIS FILE IS CITED TWICE IN build_hub.py AND DID NOT EXIST. Both comments
on rank_badge say "test_rulers.py asserts that marker never reaches a built
page"; the assertion was real but lived in test_wayfinding. A guard named in
a comment that nobody can open is worse than no comment, so the file now
exists and the marker check is re-derived here too.

WHAT THIS PROTECTS (Cody, 2026-09-11: "ranks ... are all the same color
across all pages"). Colour is a property of the RULER, stored beside its
label in build_hub.RULERS and generated into CSS by ruler_color_css(). These
checks re-derive the contrast and the hue separation from the table rather
than pinning hex strings, so improving a colour does not fail the suite --
only an illegible or indistinguishable one does.
"""
import colorsys
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import build_hub as B  # noqa: E402

FAILED = []
PAGE_BG, CARD_BG, NAVY = "#EFECF7", "#FFFFFF", "#12294B"
FLOOR = 4.5
HUE_MIN = 25.0


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def _lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    f = lambda x: x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hue(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return colorsys.rgb_to_hsv(*c)[0] * 360


def page():
    p = os.path.join(REPO, "Cody", "START-HERE.html")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def main():
    print("1. EVERY RULER CARRIES A NAME AND A COLOUR")
    check("the table is non-trivial", len(B.RULERS) >= 8, len(B.RULERS))
    shapes = {k: len(v) for k, v in B.RULERS.items()}
    check("every ruler has 4 fields (full, compact, description, colour)",
          all(n == 4 for n in shapes.values()),
          {k: n for k, n in shapes.items() if n != 4})
    check("every colour is a 6-digit hex",
          all(re.match(r"^#[0-9A-Fa-f]{6}$", v[3]) for v in B.RULERS.values()),
          [k for k, v in B.RULERS.items()
           if not re.match(r"^#[0-9A-Fa-f]{6}$", v[3])])
    check("every ruler names itself in words (full and compact labels)",
          all(v[0].strip() and v[1].strip() for v in B.RULERS.values()))

    print("\n2. THE COLOURS ARE LEGIBLE -- RE-DERIVED, NOT PINNED")
    bad = [(k, round(min(contrast(v[3], PAGE_BG),
                         contrast(v[3], CARD_BG)), 2))
           for k, v in B.RULERS.items()
           if min(contrast(v[3], PAGE_BG), contrast(v[3], CARD_BG)) < FLOOR]
    check("every ruler colour clears %.1f:1 on page and card" % FLOOR,
          not bad, bad)
    badl = [(k, round(contrast(B.ruler_lift(v[3]), NAVY), 2))
            for k, v in B.RULERS.items()
            if contrast(B.ruler_lift(v[3]), NAVY) < FLOOR]
    check("every LIFTED colour clears %.1f:1 on the navy header band" % FLOOR,
          not badl, badl)

    print("\n3. THE CHROMATIC RULERS ARE TELLABLE APART")
    chrom = sorted(((k, hue(v[3])) for k, v in B.RULERS.items()
                    if k not in B.RULER_NEUTRAL), key=lambda x: x[1])
    close = []
    for i in range(len(chrom)):
        a, b = chrom[i], chrom[(i + 1) % len(chrom)]
        d = (b[1] - a[1]) % 360
        if d < HUE_MIN:
            close.append((a[0], b[0], round(d)))
    check("no two chromatic rulers sit within %d degrees" % HUE_MIN,
          not close, close)
    check("the neutral rulers are the ones we do not compute",
          set(B.RULER_NEUTRAL) <= set(B.RULERS))

    print("\n4. THE BADGE NAMES ITS RULER AND CARRIES ITS COLOUR")
    for basis in B.RULERS:
        h = B.rank_badge(basis, 5)
        if "rnk-" + basis not in h:
            check("%s badge carries its basis class" % basis, False, h[:70])
            break
    else:
        check("every ruler's badge carries rnk-<basis>", True)
    check("an unknown basis is still LOUD, never a bare numeral",
          "rank basis?" in B.rank_badge("no-such-ruler", 4))
    check("the JS twin emits the same basis class",
          "'<i class=\"rnk rnk-' + esc(basis)" in
          open(os.path.join(REPO, "scripts", "build_hub.py"),
               encoding="utf-8").read())

    print("\n5. THE GENERATED CSS COVERS THE TABLE")
    css = B.ruler_color_css()
    miss = [k for k in B.public_rulers()
            if "--vx-%s:" % k not in css or "i.rnk.rnk-%s{" % k not in css]
    check("a token and a badge rule for every public ruler", not miss, miss)
    check("the badge rule outranks the blanket `i.rnk` colour",
          all(("i.rnk.rnk-%s{" % k) in css for k in B.public_rulers()),
          "a bare .rnk-x selector loses the specificity tie and renders "
          "nothing -- this codebase has shipped that bug twice")

    print("\n6. NO RULER COLOUR IS HAND-WRITTEN IN THE SOURCE")
    src = open(os.path.join(REPO, "scripts", "build_hub.py"),
               encoding="utf-8").read()
    stray = re.findall(
        r"\.(?:rnk|mrk|rbrk|pwr|kpow)[^{\n]*\{[^}\n]*#[0-9A-Fa-f]{6}", src)
    check("no rank class carries a literal hex", not stray, stray[:3])

    print("\n7. THE BUILT PAGE AGREES WITH THE TABLE")
    p = page()
    if p is None:
        check("[skip] Cody/START-HERE.html absent -- nothing to check here",
              True)
    else:
        toks = dict(re.findall(r"--vx-([a-z0-9]+):(#[0-9A-F]{6})", p))
        missing = [k for k in B.public_rulers() if k not in toks]
        check("the page defines a token for every public ruler",
              not missing, missing)
        wrong = [(k, toks.get(k), B.RULERS[k][3]) for k in B.public_rulers()
                 if toks.get(k, "").upper() != B.RULERS[k][3].upper()]
        check("each token equals the table's colour", not wrong, wrong[:3])
        bare = re.findall(r'class="rnk"(?! rnk-)', p)
        check("no rendered badge is left without a basis class",
              not bare, "%d bare badges" % len(bare))
        # ⚠ THE MARKER APPEARS IN THE PAGE AS JS *SOURCE* -- rankHTML's own
        # fallback literal -- which is not a rendered badge. Strip the
        # function body first, exactly as test_wayfinding does, or this
        # check fails on a correct page.
        rendered = re.sub(r"function rankHTML.*?\n\}", "", p, flags=re.S)
        check("the loud unknown-basis marker never shipped as a BADGE",
              '<i class="rnk rnkbad"' not in rendered)
        check("[+] ...and the stripper did not eat the whole page",
              len(rendered) > len(p) * 0.9,
              "stripped %d of %d chars" % (len(p) - len(rendered), len(p)))
        n = len(re.findall(r'class="rnk rnk-[a-z]', p))
        check("[+] the page really does render badges (not vacuous)",
              n > 50, n)

    print("\n8. NEGATIVE CONTROLS")
    real = B.RULERS["power"]
    B.RULERS["power"] = (real[0], real[1], real[2], "#9BE8C0")  # too pale
    trip = min(contrast(B.RULERS["power"][3], PAGE_BG),
               contrast(B.RULERS["power"][3], CARD_BG)) < FLOOR
    B.RULERS["power"] = real
    check("[NEG] an illegible ruler colour IS caught", trip)

    B.RULERS["power"] = (real[0], real[1], real[2], B.RULERS["resume"][3])
    ch = sorted(((k, hue(v[3])) for k, v in B.RULERS.items()
                 if k not in B.RULER_NEUTRAL), key=lambda x: x[1])
    dup = any((ch[(i + 1) % len(ch)][1] - ch[i][1]) % 360 < HUE_MIN
              for i in range(len(ch)))
    B.RULERS["power"] = real
    check("[NEG] two rulers sharing a hue IS caught", dup)

    check("[NEG] a badge without its basis class IS caught",
          bool(re.findall(r'class="rnk"(?! rnk-)', '<i class="rnk" title="x">')))

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL RULER GUARDS PASS")


if __name__ == "__main__":
    main()
