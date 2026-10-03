#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Player HEIGHTS from the school roster pages we already fetch (Cody,
2026-09-28, approved as a new pure data point for the POWER candidate).

Separate pass, separate file (data/raw/2026/roster_heights_2026.json), exactly
like crawl_roster_positions.py: rosters_2026.json is never rewritten, so this
pass cannot drop a player or change the R8 name join. Same fetch() (polite,
throttled, fetch_policy-gated). A height is read only in a tight window after
the player's own name anchor, or from schema.org Person "height" fields; it must
parse to 4'10"-6'8" (58-80 in). Anything else stays unknown -- never guessed.

Python 3.9 target.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as CR  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
ROSTERS = os.path.join(RAW, "rosters_%d.json" % SEASON)
OUT = os.path.join(RAW, "roster_heights_%d.json" % SEASON)
HT = re.compile(r"(?<![\d.])([4-6])\s*(?:-|'|’|′|ft\.?)\s*(\d{1,2})(?:\s*(?:\"|”|″|''|in\.?))?(?![\d])")


def inches(text):
    for m in HT.finditer(text or ""):
        f, i = int(m.group(1)), int(m.group(2))
        if i <= 11 and 58 <= 12 * f + i <= 80:
            return 12 * f + i
    return None


def heights_in(html):
    out = {}
    # schema.org Person blocks
    for m in re.finditer(r'"@type"\s*:\s*"Person".{0,800}?"name"\s*:\s*"([^"]+)".{0,400}?"height"\s*:\s*"([^"]+)"', html, re.S):
        h = inches(m.group(2).replace("\\", ""))
        if h:
            out[m.group(1).strip()] = h
    for m in re.finditer(r'<a\b[^>]*href="([^"]*/roster/[^"]*)"[^>]*>(.*?)</a>', html, re.S | re.I):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        name = re.sub(r"\s+(photo|headshot|image|picture)$", "", name, flags=re.I)
        name = __import__("html").unescape(name)
        name = re.sub(r"^(view\s+)?(full\s+)?bio\s*", "", name, flags=re.I)
        name = re.sub(r"^#?\d+\s+", "", name).strip()
        if not name or name in out or len(name.split()) < 2:
            continue
        after = re.sub(r"<[^>]+>", " ", html[m.end():m.end() + 600])
        h = inches(after)
        if h:
            out[name] = h
    return out


def main():
    rosters = dict((json.load(open(ROSTERS)) or {}).get("teams", {}))
    rp = os.path.join(RAW, "rosters_recovered_%d.json" % SEASON)
    if os.path.exists(rp):
        for team, rec in ((json.load(open(rp)) or {}).get("teams", {}) or {}).items():
            if rec.get("players") and rec.get("url"):
                rosters[team] = {"players": rec["players"], "url": rec["url"]}
    have = (json.load(open(OUT)) or {}).get("teams", {}) if os.path.exists(OUT) else {}
    todo = sorted(t for t, r in rosters.items() if r.get("url") and r.get("players") and not (have.get(t) or {}).get("heights"))
    print("teams to fetch: %d" % len(todo))
    ok = fail = n_h = 0
    for n, team in enumerate(todo, 1):
        html, status = CR.fetch(rosters[team]["url"])
        if not html or status != "ok":
            fail += 1; have[team] = {"error": status, "heights": {}}; continue
        h = heights_in(html)
        have[team] = {"heights": h, "url": rosters[team]["url"], "why": None if h else "page fetched, no height field found"}
        ok += 1; n_h += len(h)
        if n % 25 == 0:
            print("  %d/%d ok=%d fail=%d heights=%d" % (n, len(todo), ok, fail, n_h), flush=True)
            json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL", "source": "school athletics sites, height only"}, "teams": have}, open(OUT, "w"), indent=1)
    json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL", "source": "school athletics sites, height only",
                        "note": "Additive; rosters_%d.json is never rewritten. Inches." % SEASON}, "teams": have}, open(OUT, "w"), indent=1)
    print("done: ok=%d fail=%d heights=%d -> %s" % (ok, fail, n_h, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
