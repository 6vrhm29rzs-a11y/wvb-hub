#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Head coaches, from each school's own coaches page.

WHY THIS EXISTS NOW AND NOT BEFORE. coaches_2026.json records that this is "NOT
derivable from any feed we can reach... school coaches pages are
JavaScript-rendered with no JSON-LD fallback (probed Texas, Kentucky, Nebraska)".
That note was written while crawl_rosters.fetch() returned ("", "ok") for an
empty HTTP 200 -- so a fetch that came back with nothing was indistinguishable
from a page that contained nothing. Re-probed after that was fixed, all three
schools serve their coaching staff in plain HTML: "Head Coach" appears 31-73
times per page.

⚠ THE TRAP THIS IS BUILT AROUND. "Head Coach" is a SUBSTRING of "Associate Head
Coach" and "Assistant Head Coach", and on the Texas page the associate is listed
FIRST. A substring match hands you the wrong person with total confidence. The
title is compared exactly, after normalising whitespace and case, and anything
that is not precisely "head coach" is ignored.

⚠ AND A NAME IS ONLY ACCEPTED FROM THE SPORT'S OWN PAGE. A school's
/staff-directory lists the head coach of every sport in the building; taking
"the first head coach on the page" from there would give volleyball the football
coach. Only /sports/<volleyball>/coaches is read.

URLS ONLY for any photo, as everywhere else in this project: the images belong
to the schools and this repo is public.

Python 3.9 target. Run: python3 scripts/crawl_coaches.py [Team ...]
"""

import json
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as CR  # noqa: E402

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
ROSTERS = os.path.join(RAW, "rosters_%d.json" % SEASON)
RECOVERED = os.path.join(RAW, "rosters_recovered_%d.json" % SEASON)
OUT = os.path.join(RAW, "coaches_found_%d.json" % SEASON)

# Only the volleyball section -- never a building-wide staff directory.
PATHS = ["/sports/womens-volleyball/coaches",
         "/sports/wvball/coaches",
         "/sports/womens-volleyball/roster/coaches",
         "/sports/wvball/%d-%d/coaches" % (SEASON, SEASON + 1),
         "/sports/womens-volleyball/coaches/roster",
         "/sports/wvball/coaches/roster",
         "/sports/womens-volleyball/staff",
         "/sports/wvball/staff"]

_ROW = re.compile(r"<tr\b.*?</tr>", re.S)
_CELL = re.compile(r"<t[dh]\b.*?</t[dh]>", re.S)
_TAG = re.compile(r"<[^>]+>")

# ⚠ THE TITLE IS NOT ALWAYS "HEAD COACH", AND SUBSTRINGS BITE BOTH WAYS.
# Texas lists "Director of Volleyball & Head Volleyball Coach"; an exact match
# on "head coach" rejects the actual head coach. But a plain substring match
# accepts "Associate Head Coach" -- who is listed FIRST on some pages, so the
# wrong person is returned with complete confidence.
# The rule that separates them: the title must name a HEAD COACH and must not be
# a deputy. An interim head coach IS the head coach and is deliberately kept.
_IS_HEAD = re.compile(r"\bhead\b.*\bcoach\b|\bcoach\b.*\bhead\b", re.I)
_NOT_HEAD = re.compile(r"\bassociate\b|\bassistant\b|\basst\b|\bemerit", re.I)


def _clean(t):
    # type: (str) -> str
    from html import unescape
    return re.sub(r"\s+", " ", unescape(_TAG.sub(" ", t or ""))).strip()


# A staff table prints the person as the school writes her, which sometimes
# includes an honorific or a string of credentials: "Dr. Brandon Reeves",
# "Brandon Nakrin, MS, CSCS". Those are decorations on a name, not part of it,
# and they would sit oddly next to 320 plain ones. Only these two shapes are
# touched -- a leading title, and a trailing comma-separated credential list of
# short all-caps or dotted tokens. A genuine name is never comma-separated, and
# anything unrecognised is left exactly as the school wrote it.
_HONORIFIC = re.compile(r"^(?:Dr|Mr|Mrs|Ms|Coach)\.?\s+", re.I)
_CREDENTIAL = re.compile(r"^(?:[A-Z]{2,5}|[A-Z]\.[A-Z]\.?[A-Z]?\.?|Ph\.?D|Ed\.?D|M\.?S|M\.?A|MBA)$")


def tidy_name(name):
    # type: (str) -> str
    name = _HONORIFIC.sub("", name or "").strip()
    if "," in name:
        head, rest = name.split(",", 1)
        tail = [x.strip().rstrip(".") for x in rest.split(",") if x.strip()]
        if tail and all(_CREDENTIAL.match(x) for x in tail):
            name = head.strip()
    return name


def head_coach(html):
    # type: (str) -> Optional[Tuple[str, str]]
    """(name, title) from the staff table, or None.

    Row-based rather than regex-across-tags: the cells carry a paragraph of
    class names each, so any pattern that has to span them is brittle. A row is
    a row.
    """
    for row in _ROW.findall(html or ""):
        cells = [_clean(c) for c in _CELL.findall(row)]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        name, title = cells[0], cells[1]
        if not _IS_HEAD.search(title) or _NOT_HEAD.search(title):
            continue
        # a name, not a heading: two words, no digits
        if " " in name and 3 <= len(name) <= 48 and not re.search(r"\d", name) \
                and name.lower() not in ("name", "title"):
            return tidy_name(name), title
    return None


def bases():
    # type: () -> Dict[str, str]
    out = {}
    for path in (ROSTERS, RECOVERED):
        if not os.path.exists(path):
            continue
        for team, rec in ((json.load(open(path)) or {}).get("teams", {}) or {}).items():
            url = (rec or {}).get("url") or ""
            if "/sports/" in url:
                out.setdefault(team, url.split("/sports/")[0])
    return out


def main():
    only = sys.argv[1:]
    site = bases()
    teams = sorted(only or site)
    have = {}
    if os.path.exists(OUT):
        have = (json.load(open(OUT)) or {}).get("teams", {})
    todo = [t for t in teams if t in site and not (have.get(t) or {}).get("name")]
    print("teams to try: %d" % len(todo))
    found = 0
    for i, team in enumerate(sorted(todo), 1):
        rec = None
        for p in PATHS:
            time.sleep(0.4)
            html, st = CR.fetch(site[team] + p)
            if not html:
                continue
            hit = head_coach(html)
            if hit:
                rec = {"name": hit[0], "title": hit[1],
                       "source": site[team] + p, "how": "school coaches page"}
                break
        have[team] = rec or {"name": None, "source": None,
                             "why": "no staff table naming a head coach on any known path"}
        if rec:
            found += 1
        if i % 20 == 0 or i == len(todo):
            print("  %d/%d  found=%d" % (i, len(todo), found))
            json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                                "rule": ("exact title match on 'head coach'; "
                                         "sport page only, never a staff "
                                         "directory")},
                       "teams": have}, open(OUT, "w"), indent=1, sort_keys=True)
    json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                        "rule": ("exact title match on 'head coach'; sport page "
                                 "only, never a staff directory")},
               "teams": have}, open(OUT, "w"), indent=1, sort_keys=True)
    print("done: %d coaches -> %s" % (found, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
