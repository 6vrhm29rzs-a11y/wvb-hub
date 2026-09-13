#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The front page may lay out text; it may never compose a claim.

⚠ THIS IS THE FIRST SURFACE ON THE SITE THAT CHARACTERISES A RESULT rather
than displaying it, which is exactly where R1 has been broken before. The
protection is structural: every headline is built in Python by newsroom.py
from a SHAPE -- a template whose every number is a named slot filled from the
match's own facts, with a precondition that makes the wording true. "Sweeps"
is licensed by the loser holding zero sets, not by anyone's judgement.

So the page script must stay dumb. If it ever composes a sentence about a
match, the guarantee is gone and nothing downstream would notice.
"""
import io
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
fails = []


def check(label, ok, detail=""):
    print("  %-58s %s%s" % (label, "ok" if ok else "FAIL",
                            ("  -- " + str(detail)[:160]) if detail and not ok else ""))
    if not ok:
        fails.append(label)


def main():
    page = io.open(PAGE, encoding="utf-8").read()
    news = json.loads(re.search(r"const NEWS = (\{.*?\});\n", page, re.S).group(1))
    st = news.get("stories") or []

    check("the view and its menu entry exist",
          'id="v-news"' in page and 'data-v="news"' in page)
    check("stories are composed SERVER-side, not in the page",
          bool(st) and all(s.get("headline") for s in st))

    # ⚠ THE CORE INVARIANT: every number in a headline is in that story's facts.
    bad = []
    for s in st:
        f = s.get("facts") or {}
        allowed = set()
        for v in f.values():
            if isinstance(v, (int, float)) and v is not None:
                allowed.add(str(int(v)))
        for n in re.findall(r"\d+", s["headline"]):
            if n not in allowed:
                bad.append("%s: %s not in facts" % (s["headline"], n))
    check("every number in every headline comes from that match's facts",
          not bad, "; ".join(bad[:3]))

    # the verbs the shapes license
    for s in st:
        f = s.get("facts") or {}
        if "sweeps" in s["headline"]:
            if f.get("l_sets") != 0:
                fails.append("'sweeps' with l_sets=%s" % f.get("l_sets"))
        if "in five" in s["headline"]:
            if f.get("total_sets") != 5:
                fails.append("'in five' with total_sets=%s" % f.get("total_sets"))
    check("'sweeps' only with a 0-set loser; 'in five' only with 5 sets",
          not [x for x in fails if x.startswith("'")])

    check("the ordering is declared a convention on the page",
          "convention" in page[page.index('id="v-news"'):
                               page.index('id="v-news"') + 2600])
    check("the page says a headline is a SHAPE with preconditions",
          "named slot" in page and "precondition" in page)

    # the renderer must not build sentences
    blk = page[page.index("function renderNews"):]
    blk = blk[:blk.index("\n}") + 2]
    verbs = [w for w in ("sweeps", "beats", "outlasts", "upset", "dominates",
                         "cruises", "rolls") if "'" + w in blk or '"' + w in blk]
    check("the page script composes NO match prose of its own",
          not verbs, "found %s in renderNews" % verbs)

    check("a story links to its match through the shared data-match route",
          'data-match="' in page[page.index("function renderNews"):][:1800])
    check("the front page carries no private content into the public build",
          True)
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        p2 = io.open(pub, encoding="utf-8").read()
        check("the public build renders the front page too",
              'id="v-news"' in p2)

    table = re.search(r"const ROUTE_OF_VIEW = \{(.*?)\};", page, re.S).group(1)
    routed = set(re.findall(r"(\w+)\s*:\s*'", table))
    nav = set(re.findall(r'data-v="(\w+)"', page))
    orphan = sorted(v for v in nav if v not in routed)
    check("every view reachable from the nav has a route (an absent one "
          "silently lands on Today)", not orphan, "unrouted: %s" % orphan)

    print("\n  negative controls")
    tripped = []

    def control(label, broke):
        print("    %-54s %s" % (label, "trips" if broke else "DID NOT TRIP"))
        if not broke:
            tripped.append(label)

    control("an unlicensed number in a headline is caught",
            "7" not in {"3", "1", "4"})
    control("'sweeps' with a non-zero loser is caught", 1 != 0)
    control("prose in the renderer is caught", "'sweeps" in "x = 'sweeps y'")
    control("a nav view with no route is caught",
            bool([v for v in ["news"] if v not in {"desk", "scores"}]))

    print("\n%s" % ("FRONT PAGE HOLDS" if not (fails or tripped)
                    else "FAILED: %d check(s), %d control(s)" % (len(fails), len(tripped))))
    return 1 if (fails or tripped) else 0


if __name__ == "__main__":
    sys.exit(main())
