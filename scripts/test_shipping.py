#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards on the two shipping gates, and on records drifting from code.

⚠ WHY THIS FILE EXISTS. Two things went wrong this session that no suite could
have caught, because neither was a wrong value:

  1. A comment in daily.yml said the public build was off, sitting directly
     above the line that stages the public build's output -- ninety lines below
     another comment saying it had been re-enabled. CLAUDE.md said the same.
     Both had been false since 2026-08-24. Nothing compares prose to code, so
     nothing noticed.
  2. Verification lived in a sequence typed by hand at the end of each phase.
     "Green" was therefore a claim, not an artefact, and nothing checked what
     was actually SERVED once a push landed.

So: a gate before (preflight.py), a gate after (verify_shipped.py), and the
checks below on both -- plus the contradiction check that would have caught (1).

Python 3.9 target. Run: python3 scripts/test_shipping.py
"""

import glob
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMENT_RE = "/\\*.*?\\*/"
COMMENT_SRC = 'r"/' + chr(92) + '*.*?' + chr(92) + '*/"'   # the literal r"/\*.*?\*/" as it appears in a suite
LIT_RE = re.compile(r'''["\']([^"\'\n]{6,80})["\']\s*(?:not\s+)?in\s+(?:C|code|hc)\b''')

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def read(rel):
    p = os.path.join(REPO, rel)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


# ── the contradiction rule, as a function so a control can exercise it ──
OFF_CLAIMS = (
    "the public build is off",
    "no longer runs `--public`",
    "no longer runs --public",
    "are no longer regenerated",
)


def claims_public_is_off(text):
    """Does this text assert, unqualified, that the public build is off?

    ⚠ A SUPERSEDED RECORD IS NOT A CONTRADICTION. This project's amendment
    protocol keeps old entries and labels them, because the reasoning usually
    outlives the conclusion. A line that carries SUPERSEDED, or strikes itself
    through, is history and is allowed to say what it said.

    ⚠ AND IT READS A WINDOW, NOT A LINE. The first version scanned line by
    line and immediately flagged the very corrections that fixed the drift --
    because a correction QUOTES the wording it is replacing, and the quoted
    phrase lands on its own line while the word "superseded" sits three lines
    above it. That is this project's oldest trap (a guard finding its own
    explanation) wearing a new hat, and it would have made the honest fix
    impossible to commit. Exemption is judged over the surrounding lines.
    """
    lines = text.splitlines()
    hits = []
    for i, line in enumerate(lines):
        low = line.lower()
        if not any(c in low for c in OFF_CLAIMS):
            continue
        window = " ".join(lines[max(0, i - 6):i + 3]).lower()
        if any(w in window for w in
               ("superseded", "~~", "used to say", "re-enabled",
                "reversed", "this comment used to")):
            continue
        hits.append(line.strip()[:90])
    return hits


def main():
    print("SHIPPING GATES AND RECORD DRIFT\n")

    # ── 1. RECORDS MUST NOT CONTRADICT THE CODE ─────────────────────────
    print("1. NO RECORD MAY CONTRADICT THE CODE IT DESCRIBES")
    wf = read(".github/workflows/daily.yml")
    check("the daily workflow exists", bool(wf))
    stages_public = "git add output/vb_dashboard.html index.html" in wf
    builds_public = "build_hub.py --public" in wf
    print("     daily.yml: builds public = %s, stages it = %s"
          % (builds_public, stages_public))
    if stages_public or builds_public:
        hits = claims_public_is_off(wf)
        check("[-] ...so nothing in it may claim the public build is off",
              not hits, str(hits[:2]))
    cm = read("CLAUDE.md")
    check("CLAUDE.md exists", bool(cm))
    if stages_public or builds_public:
        hits = claims_public_is_off(cm)
        check("[-] ...and neither may CLAUDE.md, unless labelled superseded",
              not hits, str(hits[:2]))
    # ⚠ NEGATIVE CONTROL: replant the exact comment that was there, and require
    # the rule to trip. Without this the check above passes on any wording.
    planted = ("          # output/vb_dashboard.html and index.html are no "
               "longer regenerated\n          # (the public build is off), so "
               "they are not staged either.\n")
    check("[NEG] the real stale comment WOULD be caught",
          bool(claims_public_is_off(planted)),
          "the rule does not recognise the wording it was written for")
    # ⚠ POSITIVE CONTROL: a properly superseded record must NOT trip it, or the
    # rule would forbid this project's own amendment protocol.
    ok_form = ("- **⚠ SUPERSEDED 2026-08-24 -- the public build is off was "
               "reversed.**\n- **~~THE PUBLIC BUILD IS OFF~~ (2026-08-23).**\n")
    check("[+] ...while a SUPERSEDED entry is left alone",
          not claims_public_is_off(ok_form),
          "labelling history must stay legal")

    # ── 2. THE BEFORE GATE ──────────────────────────────────────────────
    print("\n2. THE GATE BEFORE SHIPPING")
    pf = read("scripts/preflight.py")
    check("preflight.py exists", bool(pf))
    # ⚠ IT MUST DISCOVER SUITES, NOT LIST THEM.
    check("[-] it DISCOVERS the suites rather than hard-coding a list",
          'glob.glob(os.path.join(REPO, "scripts", "test_*.py"))' in pf,
          "a hard-coded list silently omits the next suite added")
    on_disk = {os.path.basename(p) for p in
               glob.glob(os.path.join(REPO, "scripts", "test_*.py"))}
    check("[+] ...over a real set of suites (%d found)" % len(on_disk),
          len(on_disk) >= 30)
    for frag, why in (("build_hub.py --public", "the public build"),
                      ("VolleyTalk", "third-party residue"),
                      ("_flysystem", "feed media URLs"),
                      ("len(h) > 500000", "a positive control on page size")):
        check("  preflight checks %s" % why, frag in pf)
    check("[-] preflight fails loudly rather than warning",
          "DO NOT SHIP" in pf and "return 1" in pf)

    # ── 3. THE AFTER GATE ───────────────────────────────────────────────
    print("\n3. THE GATE AFTER SHIPPING")
    vs = read("scripts/verify_shipped.py")
    check("verify_shipped.py exists", bool(vs))
    # ⚠ THE WHOLE POINT: it must read the SERVED bytes.
    check("[-] it fetches the published page rather than reading a local file",
          "urlopen" in vs and "github.io" in vs,
          "a local read cannot answer what is public")
    check("it checks the served pair agrees with itself",
          "hashlib.sha1(dash" in vs)
    check("it checks nothing private is public", "PRIVATE = [" in vs)
    check("[+] ...with a positive control against an error page",
          "len(imgs) > 100" in vs,
          "every absence check passes on a 404 body")
    # ⚠ AND IT MUST NOT FAIL ON NORMAL DEPLOY LAG.
    check("[-] deploy lag is reported, not failed",
          "reported, not failed" in vs and "Fastly" in vs,
          "a verifier that cries wolf during a normal deploy gets ignored")

    # 3b. A GUARD MUST NOT BE MADE VACUOUS BY ITS OWN PREPROCESSING
    print("\n3b. NO SUITE'S CHECKS ARE EATEN BY ITS OWN COMMENT STRIP")
    # ⚠ THE HAZARD, MEASURED. Several suites strip C-style comments from
    # build_hub.py before searching it, to stop a guard matching the comment
    # that explains the thing it forbids. But build_hub.py is PYTHON that
    # embeds JS and CSS, so those pairs span unrelated blocks and swallow the
    # Python between them: 325,263 of 789,437 characters, 41% of the file. A
    # literal that lands in a swallowed region makes an "X not in code" check
    # pass for free -- a guard that cannot fail, which is this project's oldest
    # failure mode. Nothing is lying today (0 of 40 literals eaten). This is
    # what notices when that changes.
    import glob as _glob
    bh = read("scripts/build_hub.py")
    stripped = re.sub(COMMENT_RE, " ", bh, flags=re.S)
    removed = len(bh) - len(stripped)
    print("     the strip removes %d of %d chars (%.1f%%) from build_hub.py"
          % (removed, len(bh), 100.0 * removed / max(1, len(bh))))
    eaten, checked = [], 0
    for path in sorted(_glob.glob(os.path.join(REPO, "scripts", "test_*.py"))):
        t = open(path, encoding="utf-8").read()
        if COMMENT_SRC not in t or "build_hub.py" not in t:
            continue
        for m in LIT_RE.finditer(t):
            lit = m.group(1)
            checked += 1
            if lit in bh and lit not in stripped:
                eaten.append("%s: %r" % (os.path.basename(path), lit))
    check("no suite tests a literal its own strip has swallowed",
          not eaten, "; ".join(eaten[:3]))
    check("[+] ...over a real set of literals (%d checked)" % checked,
          checked >= 20, str(checked))
    # ⚠ NEGATIVE CONTROL: a literal that exists ONLY inside a comment
    # region must be detected as eaten, or the check above proves nothing.
    m_c = re.search(r"/\*([^*]{40,}?)\*/", bh, re.S)
    inside = " ".join(m_c.group(1).split())[:40] if m_c else ""
    check("[NEG] a literal living only inside a comment IS detected",
          bool(inside) and inside in bh and inside not in stripped,
          "picked %r" % inside)

    # ── 4. THEY ARE REACHABLE FROM THE RECORD ───────────────────────────
    print("\n4. SOMEONE WILL ACTUALLY FIND THEM")
    close = read("docs/session_close_2026-08-25.md")
    check("the session close names both gates",
          "preflight.py" in close and "verify_shipped.py" in close,
          "a safeguard nobody knows about is not a safeguard")

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL SHIPPING GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
