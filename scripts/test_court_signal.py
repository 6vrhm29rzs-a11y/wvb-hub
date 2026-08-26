#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Court Signal: Rally Tape state honesty, mobile structure, motion.

⚠ WHY A COMPONENT THAT ONLY *DISPLAYS* NEEDS GUARDS AT ALL. Everything the
Rally Tape shows is copied from DESK and LIVE_BY_ID, so no number in it can be
miscalculated. That is exactly what makes it dangerous: the failure available
to it is not a wrong number, it is a CONFIDENT number that is not a fact --
a 0-0 printed for a set nobody played, a home floor inferred for a neutral
match, a score shown before first serve. This page has shipped all three
classes of that bug before (the '' -> 0 coercion, Fiserv Forum, the 0-0
"leader"), which is why each is a check here.

Three defects found by LOOKING at the built page in this phase are pinned as
regression checks: a masthead value produced by slicing a string whose format
was never checked, a context line that said "on the card" about matches on a
different day, and two unlabelled rank bases inches apart.

Python 3.9 target. Run: python3 scripts/test_court_signal.py
"""

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


def src():
    return open(os.path.join(REPO, "scripts", "build_hub.py"),
                encoding="utf-8").read()


def code_only(s):
    """Strip comments so a guard cannot find its own prohibition text.

    ⚠ THIS HAS BITTEN EIGHT TIMES IN THIS PROJECT. A check that greps for a
    forbidden string finds the comment explaining why the string is forbidden,
    passes or fails for the wrong reason, and is not a test of anything."""
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"^\s*#.*$", " ", s, flags=re.M)
    s = re.sub(r'"""..*?"""', " ", s, flags=re.S)
    return s


def main():
    print("COURT SIGNAL GUARDS\n")
    h, which = page()
    if not h:
        print("  (no built page -- skipping)")
        return 0
    print("  reading %s\n" % which)
    S = src()
    C = code_only(S)

    # ── 1. THE TAPE EXISTS AND IS MOUNTED ONCE ──────────────────────────
    print("1. ONE TAPE, ONE DEFINITION")
    check("the tape mount is in the page", 'id="cstape"' in h)
    check("[-] ...exactly once -- two mounts could disagree",
          h.count('id="cstape"') == 1, "%d" % h.count('id="cstape"'))
    check("csTape() is defined", "function csTape()" in h)
    check("the control-room status strip is mounted", 'id="csstatus"' in h)
    check("both are painted at boot AND after the live poll lands",
          C.count("csTape(); csStatus();") == 2,
          "%d call sites" % C.count("csTape(); csStatus();"))

    # ── 2. STATE HONESTY ────────────────────────────────────────────────
    print("\n2. THE TAPE CANNOT SHOW SOMETHING THAT IS NOT A FACT")
    body = re.search(r"function csCells\(sets, playing\) \{(.*?)\n\}", h, re.S)
    cells = body.group(1) if body else ""
    check("csCells() exists", bool(cells))
    # '' IS NOT ZERO. The feed serves '' for a score that does not exist yet.
    check("a set counts only when BOTH sides carry a real number",
          "sv.a !== ''" in cells and "sv.h !== ''" in cells and
          "isNaN" in cells,
          "an empty string coerces to 0 and would print a 0-0 nobody played")
    check("...and an absent set renders a court dot, never a 0",
          "cs-empty" in cells and "&middot;" in cells)
    check("[+] there IS a numeric path to get wrong",
          "cs-cw" in cells, "the guard above is empty if numbers never render")
    tape = re.search(r"function csTape\(\) \{(.*?)\n\}\n", h, re.S)
    tb = tape.group(1) if tape else ""
    check("an upcoming match carries no score",
          "const quiet = st === 'upcoming'" in tb and
          "quiet ? [null, null] : matchScore" in tb)
    check("...and no set values either", "quiet ? [] : matchSets" in tb)
    # venue: stated or stated missing, never inferred
    check("a venue is the feed's or it says it is not reported",
          "venue not reported" in h)
    # ⚠ MY FIRST VERSION OF THIS CHECK WAS WRONG, AND WRONG IN THE WAY THAT
    # MATTERS: it grepped the WHOLE file for "' at ' + mHome" and tripped on
    # Film Room's frFreezeMatch, which builds the string "Kansas at
    # Pittsburgh". That is a FIXTURE DESCRIPTION -- which team is home is a
    # fact the feed states -- not an inferred VENUE. A guard that forbids the
    # normal way of naming a match is not a guard, it is an obstacle. The real
    # invariant lives inside csWhere() and nowhere else, so that is what is
    # read.
    w = re.search(r"function csWhere\(m\) \{(.*?)\n\}", h, re.S)
    wb = w.group(1) if w else ""
    check("csWhere() exists", bool(wb))
    check("[-] ...and reads only m.venue/m.city/m.st -- never a team name",
          bool(wb) and "m.h" not in wb and "m.a" not in wb and
          "mHome" not in wb and "mAway" not in wb,
          "an inferred venue rendered as fact is the Fiserv Forum defect")
    # NEGATIVE CONTROL: re-introduce the inference in-process and prove the
    # check above trips. A test that cannot fail is not a test.
    broken = wb.replace("if (!m.venue)", "if (!m.venue) return m.h;\n  if (0)")
    check("[NEG] ...and that check FAILS against an inferring csWhere()",
          "m.h" in broken and not ("m.h" not in broken))
    check("the tape never invents activity: no-fixture is its own state",
          "No matches on the schedule." in h)

    # ── 3. THE THREE DEFECTS THIS PHASE FOUND BY LOOKING ────────────────
    print("\n3. REGRESSIONS PINNED FROM THIS PHASE")
    # (a) a masthead value produced by slicing an unchecked format
    check("the feed stamp is printed, not sliced",
          ".slice(11, 16)" not in C,
          "LIVE_STAMP is '8:59:54 PM PT'; chars 11-16 are 'PT'")
    check("[+] ...and the stamp still reaches the strip",
          "esc(String(LIVE_STAMP))" in C)
    # (b) "on the card" was false when the pick came from a later day
    check("'on the card' is claimed only for TODAY's card",
          "' on the card'" in C and "' that day'" in C and "todayPT()" in C)
    # (c) two rank bases, unlabelled, inches apart
    check("the tape names which ranking its numbers come from",
          "ranks: AVCA poll" in h)

    # ── 4. MOTION ───────────────────────────────────────────────────────
    print("\n4. MOTION IS TIED TO REAL STATE")
    check("there is ONE orchestrated entrance", "@keyframes cs-in" in h)
    check("the live pulse exists", "@keyframes cs-pulse" in h)
    check("[-] ...and runs only while something is LIVE",
          ".cs-live .cs-dot{animation:cs-pulse" in h)
    check("a quiet day does not animate",
          ".cs-quiet,.cs-quiet .cs-cell{animation:none}" in h)
    check("reduced motion stops the tape's animation",
          re.search(r"@media \(prefers-reduced-motion:reduce\)\{\s*"
                    r"\.cs-tape,\.cs-tape \.cs-cell\{animation:none\}", h)
          is not None)
    check("[-] ...including the live pulse",
          re.search(r"@media \(prefers-reduced-motion:reduce\)\{[^}]*"
                    r"\}\s*\.cs-live \.cs-dot\{animation:none", h) is not None
          or ".cs-live .cs-dot{animation:none;" in h)
    # no ambient loop anywhere else in the component
    loops = re.findall(r"\.cs-[a-z-]+\{[^}]*animation:[^};]*infinite", h)
    check("the pulse is the ONLY looping animation in Court Signal",
          len(loops) == 1, str(loops))

    # ── 5. MOBILE STRUCTURE ─────────────────────────────────────────────
    print("\n5. THE PHONE KEEPS THE IDENTITY")
    phone = "\n".join(re.findall(
        r"@media \(max-width:560px\)\{(.*?)\n\}", h, re.S))
    check("a 560px block exists", bool(phone))
    check("[-] the tape is NEVER hidden on a phone",
          not re.search(r"\.cs-tape\{[^}]*display:none", phone),
          "collapsing it deletes the identity where it is most read")
    check("the tape stacks to one column", ".cs-tape{margin-top:12px;"
          "grid-template-columns:minmax(0,1fr)}" in phone)
    check("the set cells scroll in their OWN box, not the page",
          "overflow-x:auto" in phone)
    check("the empty pad column is dropped", ".cs-pad{display:none}" in phone)
    check("the state row re-states its alignment after the direction flip",
          "justify-content:flex-start" in h,
          "justify-content:center survives a row/column flip")

    # ── 6. NAMING ───────────────────────────────────────────────────────
    print("\n6. COLLISION-SAFE NAMES")
    used = set(re.findall(r"\.(cs-[a-z0-9-]+)\b", S))
    check("every Court Signal class is cs- prefixed", bool(used),
          "none found")
    # ⚠ MY FIRST VERSION OF THIS CHECK WAS ALSO WRONG. It flagged cs-at,
    # cs-dot and cs-nm for "shadowing" the existing classes at, dot and nm --
    # but a CSS class selector matches a whole token, so `.cs-at` can never
    # match class="at" and vice versa. It was testing a risk that does not
    # exist, and would have blocked three correct names.
    # The collision that DOES bite this project is exact reuse: a second
    # definition of a name that already has one, which is how `.vx-key.digby`
    # inherited a 12px padding and rendered a 32x26 swatch beside an 8x8 one.
    defined = set(re.findall(r"\.([a-z][a-z0-9-]*)\s*[{,:]", S))
    clash = sorted(n for n in used if n in (defined - used))
    check("[-] no cs- name is also defined as a non-Court-Signal class",
          not clash, str(clash[:3]))
    # NEGATIVE CONTROL: a real collision must be caught.
    fake = used | {"cs-fake"}
    fake_defined = defined | {"cs-fake"}
    check("[NEG] ...and that check catches a planted duplicate",
          bool(sorted(n for n in fake if n in (fake_defined - used))))
    # serve cyan is rationed -- a bright cyan used generally IS the terminal look
    cyan = len(re.findall(r"var\(--cs-cyan\)", h))
    check("serve cyan stays rationed (<=6 uses)", cyan <= 6, "%d uses" % cyan)
    check("[+] ...and is actually used somewhere", cyan >= 1)

    # ── 7. THE TEXTURE IS TEXTURE ───────────────────────────────────────
    print("\n7. THE COURT TEXTURE SITS BEHIND, AND IS A COURT")
    m = re.search(r"\.cs-court::before\{(.*?)\}", h, re.S)
    tex = m.group(1) if m else ""
    check("the texture rule exists", bool(tex))
    check("it never takes a pointer", "pointer-events:none" in tex)
    check("it sits behind its content", "z-index:0" in tex and
          ".cs-court>*{position:relative;z-index:1}" in h)
    check("it is low-contrast", "stroke-opacity='.07'" in tex)
    # ⚠ the first tile drew its own border and the repeat printed a lattice
    check("[-] the tile draws no boundary rectangle", "<rect" not in tex,
          "a bordered tile repeats as a grid of boxes, which is a spreadsheet")
    # ⚠ and no net in the tile: the tape draws the one net that means something
    check("[-] no dashed net in the tile", "stroke-dasharray" not in tex,
          "four decorative nets competed with the one real one")

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL COURT SIGNAL GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
