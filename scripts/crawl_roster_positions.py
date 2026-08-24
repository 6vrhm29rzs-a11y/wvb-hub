#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill in the roster positions the main roster crawl misses.

WHY THIS IS A SEPARATE FILE AND A SEPARATE PASS
-----------------------------------------------
`crawl_rosters.py` looks for a position with `\\b(OH|MB|OPP|RS|DS|L|S)\\b` in the
300 characters after a player's name anchor. That finds the short codes and
nothing else, so a site that writes "Outside Hitter" in words yields nothing:
measured, only 39.5% of roster players had a position, and 199 of 347 teams had
none at all. Positions matter for reading a roster the way a volleyball person
does, and a true freshman has no box score to fall back on.

The output is written to its OWN file and merged at build time. It never
rewrites `rosters_2026.json`, so this pass cannot drop a player, cannot change a
class year, and cannot regress the R8 name join -- the worst case is that it
learns nothing.

WHAT IT WILL NOT DO
-------------------
Guess. Spelled-out titles are matched first because they are unambiguous; the
short codes are a fallback in a tight window. `O` on its own is NEVER mapped:
of the 41 box-score `O` players who also carry a school-site position, 27 are
OPP but 8 are OH and 5 are S, so reading it as "opposite" would be wrong about
a third of the time. Unmatched stays unmatched and renders as "not listed".

Python 3.9 target.
"""

import json
import os
import re
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as CR  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
ROSTERS = os.path.join(RAW, "rosters_%d.json" % SEASON)
OUT = os.path.join(RAW, "roster_positions_%d.json" % SEASON)

# Spelled-out titles first: they are unambiguous. Order matters -- "opposite
# hitter" must beat "opposite", and "outside hitter" must beat "outside".
POS_WORDS = (
    (r"outside\s*/?\s*hitter", "OH"),
    (r"opposite\s*/?\s*hitter", "OPP"),
    (r"middle\s*/?\s*blocker", "MB"),
    (r"middle\s*/?\s*hitter", "MB"),
    (r"defensive\s+specialist", "DS"),
    (r"right\s*[-\s]?side\s*hitter", "OPP"),
    (r"right\s*[-\s]?side", "OPP"),
    (r"\blibero\b", "L"),
    (r"\bsetter\b", "S"),
    (r"\bopposite\b", "OPP"),
    (r"\boutside\b", "OH"),
    (r"\bmiddle\b", "MB"),
)
POS_WORDS_RE = tuple((re.compile(p, re.I), v) for p, v in POS_WORDS)

# Fallback: the short codes, in a TIGHT window so a stray capital does not
# become a position. Deliberately excludes a bare "O".
POS_CODE_RE = re.compile(r"\b(OH/DS|DS/L|L/DS|S/RS|OH|MB|OPP|RS|DS|L|S)\b")


def position_from(text):
    # type: (str) -> Optional[str]
    """A position, or None. Words win; codes are the fallback."""
    if not text:
        return None
    for rx, val in POS_WORDS_RE:
        if rx.search(text):
            return val
    m = POS_CODE_RE.search(text[:160])
    return m.group(1) if m else None


def positions_in(html):
    # type: (str) -> Dict[str, str]
    """name -> position, using the same name anchors the roster parser uses.

    Reuses crawl_rosters.parse_roster so this pass can never disagree with it
    about WHO is on the roster -- it only adds a field.
    """
    out = {}
    for pl in CR.parse_roster(html):
        name = pl.get("name_raw")
        if not name:
            continue
        if pl.get("pos_raw"):
            out[name] = pl["pos_raw"]
    # Second sweep: for anchors the main parser found but could not type, look
    # at a wider window on BOTH sides of the name (some templates put the
    # position in a table cell before the name).
    for m in re.finditer(r'<a\b[^>]*href="([^"]*/roster/[^"]*)"[^>]*>(.*?)</a>',
                         html, re.S | re.I):
        inner = re.sub(r"<[^>]+>", " ", m.group(2))
        name = re.sub(r"\s+", " ", CR.html_unescape(inner) if hasattr(CR, "html_unescape")
                      else inner).strip()
        name = re.sub(r"\s+(photo|headshot|image|picture)$", "", name, flags=re.I)
        if not name or name in out:
            continue
        after = re.sub(r"<[^>]+>", " ", html[m.end():m.end() + 700])
        before = re.sub(r"<[^>]+>", " ", html[max(0, m.start() - 500):m.start()])
        pos = position_from(after) or position_from(before)
        if pos:
            out[name] = pos
    return out


def main():
    rosters = dict((json.load(open(ROSTERS)) or {}).get("teams", {}))
    # Teams whose roster came from the recovery pass carry their own (corrected)
    # URL. They arrive with no positions at all -- the JSON-LD route yields
    # names only -- so they are exactly the teams this pass exists for.
    recovered_path = os.path.join(RAW, "rosters_recovered_%d.json" % SEASON)
    if os.path.exists(recovered_path):
        for team, rec in ((json.load(open(recovered_path)) or {})
                          .get("teams", {}) or {}).items():
            if rec.get("players") and rec.get("url"):
                rosters[team] = {"players": rec["players"], "url": rec["url"]}
    have = {}
    if os.path.exists(OUT):
        have = (json.load(open(OUT)) or {}).get("teams", {})

    todo = []
    for team, rec in rosters.items():
        players = rec.get("players") or []
        if not players or not rec.get("url"):
            continue
        missing = [p for p in players if not p.get("pos_raw")]
        if not missing:
            continue
        # ⚠ A ZERO-POSITION RECORD IS ONLY AS GOOD AS THE FETCH THAT WROTE IT.
        # 150 of 254 teams here were stored with an empty positions map and no
        # status at all, under a fetch() that reported an empty HTTP 200 as
        # "ok" -- so a page nobody ever saw is indistinguishable from a page
        # that lists no positions. Records WITH positions are trusted and
        # skipped; empty ones are retried once now that an empty body is
        # reported as a failure.
        if team in have and (have[team] or {}).get("positions"):
            continue
        todo.append(team)

    print("teams needing positions: %d" % len(todo))
    found_total = 0
    ok = fail = 0
    for n, team in enumerate(sorted(todo), 1):
        url = rosters[team].get("url")
        html, status = CR.fetch(url)
        if not html or status != "ok":
            fail += 1
            have[team] = {"error": status, "positions": {}}
            continue
        try:
            pos = positions_in(html)
        except Exception as exc:                      # noqa: BLE001
            fail += 1
            have[team] = {"error": "parse: %s" % str(exc)[:100], "positions": {}}
            continue
        have[team] = {"positions": pos, "url": url,
                      # say WHY an empty result is empty, so the next run does
                      # not have to guess whether the page was ever seen
                      "why": None if pos else "page fetched, no position field"}
        found_total += len(pos)
        ok += 1
        if n % 25 == 0:
            print("  %d/%d  ok=%d fail=%d  positions so far=%d"
                  % (n, len(todo), ok, fail, found_total))
            json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                                "source": "school athletics sites, position field only"},
                       "teams": have}, open(OUT, "w"), indent=1)

    json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                        "source": "school athletics sites, position field only",
                        "note": ("Additive. Merged at build time; rosters_%d.json is "
                                 "never rewritten by this pass." % SEASON)},
               "teams": have}, open(OUT, "w"), indent=1)
    print("done: ok=%d fail=%d, %d positions -> %s" % (ok, fail, found_total, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
