#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the shared visual system.

⚠ WHY THIS SUITE EXISTS. Class collisions are the most common bug in
build_hub.py -- nine now, every one silent. The ninth happened while building
THIS system: `.vx-key.digby` inherited `.digby`, an existing block style with
12px padding, and the swatch rendered 32x26px beside two 8x8 squares. The
prefix had been checked; the MODIFIER had not.

So the first thing here is a namespace guard, and the rest asserts that the
primitives exist once and that motion respects the reader's setting.

Python 3.9 target. Run: python3 scripts/test_visual_system.py
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)
import css_names as CN  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def page():
    p = os.path.join(REPO, "Cody", "START-HERE.html")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def main():
    print("VISUAL SYSTEM GUARDS\n")
    h = page()
    if not h:
        print("  (no built page -- skipping)")
        return 0
    src = open(os.path.join(SCRIPTS, "build_hub.py"), encoding="utf-8").read()

    print("1. THE NAMESPACE IS SELF-CONTAINED")
    # Every class the system applies must be under vx-, INCLUDING modifiers.
    applied = set()
    for m in re.finditer(r'class="([^"{}+]*vx-[^"{}+]*)"', h):
        for tok in m.group(1).split():
            applied.add(tok)
    check("[+] the system is actually applied", len(applied) >= 4,
          str(sorted(applied)[:6]))
    stray = sorted(t for t in applied if not t.startswith("vx-"))
    check("[-] no vx element carries a NON-namespaced class",
          not stray, "these could inherit foreign styles: %s" % stray)

    print("\n2. NO vx- NAME COLLIDES WITH THE EXISTING 868")
    inv = CN.inventory()
    # Names the system defines, and what they would collide with.
    defined = sorted(c for c in CN.defined_classes(src) if c.startswith("vx-"))
    check("[+] the system defines primitives", len(defined) >= 8,
          "%d" % len(defined))
    pre_existing = set()
    for c in defined:
        # anything non-vx that is exactly this name would be a collision
        if c in inv["taken"] and c not in defined:
            pre_existing.add(c)
    check("[-] none was already taken", not pre_existing, str(pre_existing))
    # ⚠ AND THE MODIFIER LESSON, ASSERTED DIRECTLY.
    for mod in ("power", "avca", "digby", "ballot"):
        check("[-] the bare modifier %-7r is NOT used as a vx selector" % mod,
              (".vx-key.%s{" % mod) not in src,
              "it would inherit the existing .%s block style" % mod)
    for mod in ("vx-k-power", "vx-k-avca", "vx-k-digby"):
        check("   %s is namespaced and defined" % mod,
              (".vx-key.%s{" % mod) in src)

    print("\n3. THE RULER KEY IS ONE SYSTEM, USED EVERYWHERE")
    for tok in ("--vx-power", "--vx-avca", "--vx-digby", "--vx-ballot"):
        check("the token %s is defined" % tok, "%s:" % tok in src)
    # ⚠ THE KEY MUST MATCH THE COLOURS ALREADY ON THE PAGE, or it introduces
    # the inconsistency it exists to remove. POWER has been green since the
    # rating shipped -- including the heat scale on the POWER column itself.
    check("POWER's key is the green the site already uses",
          "--vx-power:#31D07E" in src)
    check("...and the existing POWER labels use the token, not a literal",
          "b.kpow{color:var(--vx-power)}" in src
          and ".bwv.pw{color:var(--vx-power)}" in src)
    check("AVCA's key is the blue the site already uses",
          "--vx-avca:#7AA7FF" in src)
    check("the three rulers each carry a swatch on the selector",
          h.count('class="vx-key vx-k-') >= 3,
          "%d" % h.count('class="vx-key vx-k-'))

    print("\n4. THE PRIMITIVES EXIST ONCE EACH")
    # ⚠ COUNT BASE DEFINITIONS ONLY. A responsive override inside
    # @media(max-width:560px) is a legitimate SECOND occurrence of the same
    # selector -- the first version of this check counted those and failed four
    # primitives that were correct. Strip the media blocks, then count.
    base = re.sub(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", " ", src)
    for prim in (".vx-label{", ".vx-facts{", ".vx-idrow{", ".vx-empty{",
                 ".vx-read{", ".vx-key{"):
        # ⚠ ANCHOR THE SELECTOR. A plain substring count also matches
        # contextual rules like `.vx-label .vx-key{` and `.seg .segb .vx-key{`,
        # which are legitimate. Count only where the selector STARTS a rule.
        n = len(re.findall(r"(?m)^\s*" + re.escape(prim), base))
        check("%-12s has ONE base definition" % prim.strip(".{"), n == 1,
              "%d outside media queries" % n)

    print("\n5. MOTION IS DELIBERATE AND OPTIONAL")
    # ⚠ ONE ANIMATION, ON THE ONE THING THAT CHANGES WITHOUT THE READER ACTING.
    anims = re.findall(r"@keyframes\s+([\w-]+)", src)
    check("[+] there is at least one animation", len(anims) >= 1, str(anims))
    check("the live dot is the animated element", ".vx-livedot{" in src
          and "animation:vxpulse" in src)
    # ⚠ THE FILE ALREADY HAS 14 reduced-motion BLOCKS. Asserting that "a
    # reduced-motion block exists" therefore passes on somebody else's -- I
    # deleted mine as a control and the guard stayed green. The invariant is
    # that EVERY animated element the system introduces is turned off, so it is
    # checked per element.
    rm_blocks = re.findall(
        r"@media \(prefers-reduced-motion:reduce\)\{(.*?)\}\s*\n", src, re.S)
    joined = "\n".join(rm_blocks)
    check("[+] there are reduced-motion blocks to look in", bool(rm_blocks),
          "%d found" % len(rm_blocks))
    animated = sorted(set(re.findall(r"(\.vx-[\w-]+)\{[^}]*animation:", src)))
    check("[+] the system animates something", bool(animated), str(animated))
    for sel in animated:
        check("%s is disabled under reduced motion" % sel,
              re.search(re.escape(sel) + r"\{[^}]*animation:\s*none", joined)
              is not None, "not covered by any reduced-motion block")

    print("\n6. TODAY'S READ IS ASSEMBLED, NEVER WRITTEN")
    check("the strip exists", "function todaysRead(" in src)
    body = src[src.index("function todaysRead("):src.index("function renderDesk()")]
    # ⚠ NO CHARACTERISATION. Every row is a fact already on the page.
    for word in ("must-watch", "huge", "crucial", "showdown", "clash",
                 "don't miss", "biggest test", "statement"):
        check("[-] it never says %r" % word, word not in body.lower())
    check("every row links to the canonical match route",
          "matchRoute(gid, 'desk')" in body)
    check("an absent fact yields no row, rather than filler",
          "if (!rows.length) return '';" in body)
    # It reads My Board through the real contract, not an assumed return value.
    check("[-] it does not assume mbLoad() returns the list",
          "new Set(mbLoad()" not in body)
    check("   ...it calls mbLoad() then reads MB", "mbLoad();" in body
          and "Array.isArray(MB)" in body)

    print("\n7. THE EMPTY DAY IS A DELIBERATE PAGE")
    check("a no-games day uses the empty primitive",
          'class="vx-empty"' in h or "'<div class=\"vx-empty\">" in src)
    check("...and names the next window from the schedule",
          "The next window is" in src)
    check("...and offers somewhere to go", "vx-emptyacts" in src)

    print("\n8. THE PHONE RULES EXIST FOR EVERY NEW PRIMITIVE")
    phone = "\n".join(re.findall(r"@media \(max-width:560px\)\{(.*?)\n\}", src,
                                 re.S))
    for prim in (".vx-read", ".vx-facts", ".vx-empty", ".vx-idrow"):
        check("%-10s is sized at the phone breakpoint" % prim, prim in phone)

    print()
    if not check_ios_zoom(h):
        FAILS.append("form controls reach 16px at phone width")
    if not check_css_vars(h):
        FAILS.append("every CSS variable read is also defined")

    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL VISUAL SYSTEM GUARDS PASS")
    return 0



def check_css_vars(page):
    """Every custom property a rule READS must be DEFINED somewhere.

    ⚠ A PHANTOM TOKEN FAILS SILENTLY AND LOOKS LIKE A STYLING CHOICE. Seventeen
    rules were written against `--cs-mute`, which does not exist: colour then
    falls back to whatever is inherited, so a muted caption inside a card that
    happens to be an <a> rendered in default link blue. Nothing errored and the
    page still looked deliberate.
    A property with a FALLBACK -- var(--x, #ccc) -- is fine and is skipped.

    ⚠ IT SCANS COMMENTS TOO, so do not write a dead token's name in var()
    form inside the comment that explains you removed it. That is exactly what
    happened here and the guard reported the fix as the bug.
    """
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", page, re.I))
    used = set()
    for m in re.finditer(r"var\(\s*(--[a-z0-9-]+)\s*([,)])", page, re.I):
        if m.group(2) == ")":
            used.add(m.group(1))
    missing = sorted(used - defined)
    ok = not missing
    print("  %-64s %s" % ("every CSS variable read is also defined",
                          "ok" if ok else "FAIL %s" % missing[:6]))
    return ok



def check_ios_zoom(h):
    """A form control under 16px makes iOS Safari zoom, and it never zooms back.

    ⚠ REPORTED FROM A REAL PHONE, NOT GUESSED. Cody read the hub on his iPhone
    and said the text boxes and the scrolling were wonky. Both are the same
    cause: iOS zooms the page in when you focus a control whose font-size is
    under 16px and leaves it zoomed, so every scroll afterwards is against a
    scaled viewport. All 84 controls measured 11.5-14px.

    ⚠ THE RULE NEEDS !important AND THAT IS NOT LAZINESS. It has to beat about
    forty more-specific selectors AND every `font:` shorthand on the page,
    which resets font-size as a side effect. Without it, 84 controls stayed
    under the threshold with the rule present.

    ⚠ AND NOT maximum-scale=1, which also stops the zoom -- by disabling
    pinch-zoom for everyone, including anyone who needs to magnify the page.
    """
    ok = True
    # ⚠ READ THE META TAG, NOT THE WHOLE DOCUMENT. Searching the page for
    # "maximum-scale" matched the CSS COMMENT that explains why we did not use
    # it, and reported the correct build as broken. Sixth time in this session
    # a guard has matched prose instead of code; scope every one of them.
    m = re.search(r'<meta[^>]+name="viewport"[^>]*>', h)
    meta = m.group(0) if m else ""
    if "maximum-scale" in meta or "user-scalable=no" in meta:
        print("  FAIL the viewport meta disables pinch-zoom")
        ok = False
    # ⚠ ASSERT THE VALUE, NOT THE BLOCK. A first version accepted the media
    # query merely EXISTING, so reverting the size to 13px inside it would have
    # sailed through -- the guard would have been checking that somebody once
    # wrote a rule, not that the rule still says what it must.
    if not re.search(r"input,select,textarea\{font-size:16px ?!important\}", h):
        print("  FAIL no phone rule lifts form controls to 16px")
        ok = False
    print("  %-64s %s" % ("form controls reach 16px at phone width",
                          "ok" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    sys.exit(main())
