#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for head-coach extraction. No network -- fixtures only.

WHY THIS FILE EXISTS. Getting a coach wrong is the quiet kind of wrong: a name
renders perfectly, sits under the right crest, and is a different human being.
Nothing downstream can detect it. Three things produce it, and all three
happened while building the roster-page recoverer:

  1. THE DEPUTY. "Head Coach" is a substring of "Associate Head Coach" and
     "Assistant Head Coach", and several schools list the associate FIRST.
  2. THE FURNITURE. A loose "capitalised phrase near the title" scan published
     "Volleyball Coaching Staff", then "Alma Mater", then "Printer Friendly
     Version" -- three rounds, three templates, each fix blind to the next.
  3. THE ENDOWMENT, which cuts the other way: Purdue's head coach is the "Art
     and Connie Euler Women's Volleyball Head Coach", so an EXACT match on the
     words "Head Coach" rejects the real one. Meanwhile Stanford's page carries
     "The Kimberly and Beverly Oden Associate Head Coach" -- which also ends in
     those two words and is not the head coach. Any ends-with rule gets this
     pair exactly backwards.

Every fixture below is a reduction of a real page's markup.

Python 3.9 target. Run: python3 scripts/test_coaches.py
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recover_coaches_from_roster as RC   # noqa: E402
import reconcile_2025 as R                 # noqa: E402

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


# --- fixtures: the real template shapes, reduced -------------------------
NESTED_ANCHOR = (             # Nebraska / WMT: name nested in a span in a link
    '<th class="roster-table-cell roster-table-cell--full-name"><div>'
    '<a href="/sports/volleyball/roster/season/2026/staff/dani-busboom-kelly" '
    'class="table__roster-name"><span>Dani Busboom Kelly</span></a></div></th>'
    '<td class="roster-table-cell roster-table-cell--position">'
    '<span>Head Coach</span></td>')

DEPUTY_FIRST = (              # the associate listed ABOVE the head coach
    '<a href="/sports/womens-volleyball/roster/season/2026/staff/jane-deputy" '
    'class="roster-card-item__title-link">Jane Deputy</a>'
    '<div class="roster-card-item__position">Associate Head Coach</div>'
    '<a href="/sports/womens-volleyball/roster/season/2026/staff/real-boss" '
    'class="roster-card-item__title-link">Real Boss</a>'
    '<div class="roster-card-item__position">Head Coach</div>')

ENDOWED = (                   # Purdue: an endowed HEAD coach title
    '<a href="/sports/womens-volleyball/roster/season/2026/staff/dave-shondell" '
    'class="roster-card-item__title-link">Dave Shondell</a>'
    '<div class="roster-card-item__position">'
    "Art and Connie Euler Women&#39;s Volleyball Head Coach</div>")

ENDOWED_DEPUTY = (            # Stanford: an endowed ASSOCIATE, no head coach
    '<strong class="roster-card-item__position">'
    'The Kimberly and Beverly Oden Associate Head Coach</strong>'
    '<a href="/sports/womens-volleyball/roster/season/2026/staff/rachel-corbelli" '
    'class="roster-card-item__title-link">Rachel Corbelli</a>')

FURNITURE = (                 # the three phrases that actually got published
    '<div class="section-heading">Volleyball Coaching Staff</div>'
    '<th class="col">Alma Mater</th><a href="/print">Printer Friendly Version</a>'
    '<div class="roster-card-item__position">Head Coach</div>')

TITLE_CARRIES_NAME = (        # Maryland: name and title are one string
    '<div class="roster-item__info">Head Coach Adam Hughes</div>')

PAYLOAD = '"Dani","Busboom Kelly","Head Coach","x@y.edu"'
PAYLOAD_DEPUTY = '"Jane","Deputy","Associate Head Coach","x@y.edu"'


def main():
    print("HEAD-COACH GUARDS\n")

    print("1. POSITIVE CONTROLS -- the real template shapes must resolve")
    got = RC.from_html(NESTED_ANCHOR)
    check("a name nested inside a link is found", got and got[0] == "Dani Busboom Kelly",
          "(got %r)" % (got,))
    got = RC.from_html(ENDOWED)
    check("an ENDOWED head-coach title is accepted",
          got and got[0] == "Dave Shondell", "(got %r)" % (got,))
    got = RC.from_html(TITLE_CARRIES_NAME)
    check("a name carried inside the title is read out of it",
          got and got[0] == "Adam Hughes", "(got %r)" % (got,))
    got = RC.from_payload(PAYLOAD)
    check("the embedded data payload resolves too",
          got and got[0] == "Dani Busboom Kelly", "(got %r)" % (got,))

    print("\n2. NEGATIVE CONTROLS -- the ways to get the wrong person")
    got = RC.from_html(DEPUTY_FIRST)
    check("the associate listed FIRST is not returned as head coach",
          got and got[0] == "Real Boss",
          "(got %r -- a substring match returns the deputy)" % (got,))
    got = RC.from_html(ENDOWED_DEPUTY)
    check("an endowed ASSOCIATE title is refused", got is None,
          "(got %r -- ends in 'Head Coach' and is not one)" % (got,))
    got = RC.from_payload(PAYLOAD_DEPUTY)
    check("the payload path refuses a deputy too", got is None, "(got %r)" % (got,))
    got = RC.from_html(FURNITURE)
    check("page furniture is never published as a person", got is None,
          "(got %r)" % (got,))
    for junk in ("Volleyball Coaching Staff", "Alma Mater",
                 "Printer Friendly Version", "Coaching Staff", "Additional Links"):
        if RC.looks_like_a_person(junk):
            check("the person test rejects %r" % junk, False)
            break
    else:
        check("the person test rejects all five published-junk phrases", True)
    check("...and still accepts real names",
          all(RC.looks_like_a_person(n) for n in
              ("Dani Busboom Kelly", "Craig Skinner", "Sondra D'Amore",
               "Katie Schumacher-Cawley", "Paco Labrador")))

    print("\n3. THE SHIPPED DATA")
    out = {}
    for rel, key in (("data/raw/%d/coaches_found_%d.json" % (SEASON, SEASON), "teams"),
                     ("data/raw/%d/coaches_from_roster_%d.json" % (SEASON, SEASON), "teams"),
                     ("data/raw/%d/coaches_%d.json" % (SEASON, SEASON), "coaches")):
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            continue
        for t, v in (json.load(open(p, encoding="utf-8")).get(key) or {}).items():
            if (v or {}).get("name"):
                out.setdefault(rel, {})[t] = v["name"]

    published = {}
    for rel in out:
        published.update(out[rel])
    # ⚠ THE FURNITURE TEST, NOT THE SHAPE TEST. This crawler's NAME shape is
    # strict because it reads a page loosely; crawl_coaches reads a staff TABLE
    # row, where the school has already said the cell is a person, so it keeps
    # names as written -- 'Ma-Kayla "MJayee" Johnson', "Alicia Manguiat (Roth)".
    # Judging those by this crawler's rule would delete two real coaches, which
    # is exactly what the first version of this check did.
    bad = [(t, n) for t, n in published.items() if RC.is_furniture(n)]
    check("no published coach name is page furniture", not bad,
          "(%s)" % (bad[:3],))

    # A name shared by two schools is furniture, not a coach with two jobs.
    byname = {}
    for t, n in published.items():
        byname.setdefault(n, []).append(t)
    shared = dict((n, ts) for n, ts in byname.items() if len(ts) > 1)
    check("no coach name is claimed by more than one school", not shared,
          "(%s)" % (list(shared.items())[:2],))

    # The hand-entered rows are individually sourced; a crawl that disagrees
    # with one is a signal, not a tie to break silently.
    hand = out.get("data/raw/%d/coaches_%d.json" % (SEASON, SEASON), {})
    crawl = {}
    crawl.update(out.get("data/raw/%d/coaches_found_%d.json" % (SEASON, SEASON), {}))
    crawl.update(out.get("data/raw/%d/coaches_from_roster_%d.json" % (SEASON, SEASON), {}))
    clash = [(t, hand[t], crawl[t]) for t in hand if t in crawl and hand[t] != crawl[t]]
    agree = [t for t in hand if t in crawl and hand[t] == crawl[t]]
    check("hand-entered names and crawled names never disagree", not clash,
          "(%s)" % (clash[:2],))
    if agree:
        print("     (%d hand-entered row(s) independently confirmed by a crawl: %s)"
              % (len(agree), ", ".join(sorted(agree))))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL HEAD-COACH GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
