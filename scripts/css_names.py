#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What class names are already taken, so a new one cannot collide.

⚠ WHY THIS EXISTS. Class and id collisions are the most common bug in
build_hub.py -- eight so far, each silent: `.lead`, `.why`, `.bwsub`, `.bwlink`,
`.mt`, `#bwcmpout`, `.warn` borrowed from a fenced ballot region, and `.ndi`
which would have matched 53 substrings (sta*ndi*ngs, I*ndi*ana). None threw an
error; each just quietly styled or selected the wrong thing.

Run it before naming anything:

    python3 scripts/css_names.py              # summary + risky names
    python3 scripts/css_names.py mycls other  # are these free?

Python 3.9 target.
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
SRC = os.path.join(REPO, "scripts", "build_hub.py")

# A CSS identifier. Anchored so JS fragments (`.replace`, `.push`) and
# numbers do not enter the inventory as if they were class names.
IDENT = r"[a-zA-Z_][a-zA-Z0-9_-]*"


def defined_classes(css):
    """Class names that a CSS rule actually defines."""
    out = set()
    # strip comments and anything that is plainly JS before scanning
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for m in re.finditer(r"\.(%s)(?=[\s,{:.\[>+~])" % IDENT, css):
        out.add(m.group(1))
    return out


def used_classes(html):
    """Class names that appear in a rendered class attribute."""
    out = set()
    for m in re.finditer(r'class="([^"{}+]*)"', html):
        for tok in m.group(1).split():
            if re.match(r"^%s$" % IDENT, tok):
                out.add(tok)
    return out


def element_ids(html):
    out = set()
    for m in re.finditer(r'id="([^"{}+]*)"', html):
        tok = m.group(1).strip()
        if re.match(r"^%s$" % IDENT, tok):
            out.add(tok)
    return out


def inventory():
    html = open(PAGE, encoding="utf-8").read() if os.path.exists(PAGE) else ""
    src = open(SRC, encoding="utf-8").read()
    # the page carries the built CSS; the source carries names not yet rendered
    d = defined_classes(html) | defined_classes(src)
    u = used_classes(html) | used_classes(src)
    return {"defined": d, "used": u, "taken": d | u, "ids": element_ids(html)}


def substring_risk(name, taken):
    """Names this one is a substring OF, or that are substrings of it.

    ⚠ THE `.ndi` LESSON. A guard or selector written around a short name can
    match inside a longer one. `bwr` lives inside `bwrap`; `mbrow` lives inside
    the surname Stambrowska. Anything under five characters is reported.
    """
    hits = []
    for t in taken:
        if t == name:
            continue
        if name in t or t in name:
            hits.append(t)
    return sorted(hits)


def main():
    inv = inventory()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        bad = 0
        for name in args:
            taken = name in inv["taken"]
            risk = substring_risk(name, inv["taken"]) if len(name) < 6 else []
            print("%-16s %-9s %s" % (
                name, "TAKEN" if taken else "free",
                ("substring risk: %s" % ", ".join(risk[:6])) if risk else ""))
            bad += 1 if taken else 0
        return 1 if bad else 0
    print("classes defined : %d" % len(inv["defined"]))
    print("classes used    : %d" % len(inv["used"]))
    print("total taken     : %d" % len(inv["taken"]))
    print("element ids     : %d" % len(inv["ids"]))
    short = sorted(c for c in inv["taken"] if len(c) <= 3)
    print("\nnames of 3 characters or fewer (%d) -- reuse with care:" % len(short))
    print("  " + " ".join(short))
    return 0


if __name__ == "__main__":
    sys.exit(main())
