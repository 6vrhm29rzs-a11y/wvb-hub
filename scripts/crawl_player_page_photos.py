#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Third photo path: each player's OWN page, read for og:image.

WHY A THIRD PATH. Two already exist and both read the ROSTER page: an <img> near
the player's anchor (SIDEARM), and schema.org Person blocks carrying image.url
(WMT). 48 teams have neither -- Nebraska, LSU, Arkansas, Clemson, Iowa and the
rest -- because their roster renders as a TABLE with no photographs in it at all.
Measured on huskers.com: 886 KB of HTML, one <img> on the whole page (a banner),
no data-src, no srcset, no JSON-LD image.

But that table links to each player, and HER page carries og:image. Measured:
bergen-reilly, harper-murray and andi-jackson return three DISTINCT imgproxy
URLs. So the photo is published; it is just one hop further in.

⚠ ATTRIBUTION IS BY CONSTRUCTION, WHICH IS THE POINT. We arrive at the photo by
following that player's own link from her own roster, so there is no name match
to get wrong -- this path cannot produce the R8 failure where a correct number is
attached to the wrong person.

⚠ THE FAILURE MODE THIS GUARDS. A site with no per-player photo often serves a
generic og:image -- the team banner, a stadium, a logo -- on every player page.
That would hand every player on the roster the same picture and present it as
her headshot, which is R5 with a photograph instead of a number. So a team is
kept ONLY if its URLs are mostly distinct; if they collapse, the whole team is
rejected and its players keep rendering initials.

URLS ONLY. Nothing is downloaded and nothing is committed but the URL -- the
photographs belong to the schools and this repo is public.

Python 3.9 target. Run: python3 scripts/crawl_player_page_photos.py
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
PHOTOS = os.path.join(RAW, "roster_photos_%d.json" % SEASON)
OUT = os.path.join(RAW, "player_page_photos_%d.json" % SEASON)

# Below this share of distinct URLs the team is serving one generic image to
# everybody, not headshots. 0.6 is deliberately loose: a squad legitimately
# sharing one or two placeholder shots should not sink the whole roster.
MIN_DISTINCT = 0.6
PLAYER_HREF = re.compile(r'href="([^"]*?/roster/player/[^"?#]+)"')
OG = (re.compile(r'property="og:image"\s+content="([^"]+)"'),
      re.compile(r'content="([^"]+)"\s+property="og:image"'))


def nkey(s):
    # type: (str) -> str
    return re.sub(r"[^a-z]", "", (s or "").lower())


def og_image(html):
    # type: (str) -> Optional[str]
    for pat in OG:
        m = pat.search(html or "")
        if m:
            u = m.group(1).strip()
            if u and not u.startswith("data:"):
                # Reuse the existing repairs rather than writing a second copy:
                # WMT emits a doubled scheme prefix that 404s, and SIDEARM crop
                # URLs carry &amp; separators that 400 until decoded.
                return CR._absolutise(u, "")
    return None


def teams_without_photos():
    # type: () -> Dict[str, Dict]
    rosters = (json.load(open(ROSTERS)) or {}).get("teams", {})
    have = {}
    if os.path.exists(PHOTOS):
        have = (json.load(open(PHOTOS)) or {}).get("teams", {})
    out = {}
    for team, rec in rosters.items():
        players = rec.get("players") or []
        if not players or not rec.get("url"):
            continue
        if any(p.get("photo") for p in players):
            continue
        if (have.get(team) or {}).get("photos"):
            continue
        out[team] = rec
    return out


def main():
    todo = teams_without_photos()
    done = {}
    if os.path.exists(OUT):
        done = (json.load(open(OUT)) or {}).get("teams", {})
    todo = dict((k, v) for k, v in todo.items() if k not in done)
    print("teams still without a photo: %d" % len(todo))

    kept = rejected = 0
    for i, team in enumerate(sorted(todo), 1):
        rec = todo[team]
        html, status = CR.fetch(rec["url"])
        if not html or status != "ok":
            done[team] = {"status": status, "photos": {}, "why": "roster fetch failed"}
            continue
        links = []
        for m in PLAYER_HREF.finditer(html):
            href = m.group(1)
            if href not in links:
                links.append(href)
        if not links:
            done[team] = {"status": "ok", "photos": {},
                          "why": "no per-player links on the roster page"}
            continue
        names = dict((nkey(p.get("name_raw") or ""), p.get("name_raw"))
                     for p in rec["players"])
        found = {}
        for href in links:
            url = href if href.startswith("http") else (
                rec["url"].split("/sports/")[0] + href)
            slug = href.rstrip("/").rsplit("/", 1)[-1]
            key = nkey(slug.replace("-", ""))
            who = names.get(key)
            if not who:
                continue                     # a link we cannot tie to this roster
            page, st = CR.fetch(url)
            if not page or st != "ok":
                continue
            u = og_image(page)
            if u:
                found[who] = u
            time.sleep(0.15)
        if not found:
            done[team] = {"status": "ok", "photos": {}, "why": "no og:image"}
            rejected += 1
        else:
            distinct = len(set(found.values())) / float(len(found))
            if distinct < MIN_DISTINCT:
                done[team] = {"status": "ok", "photos": {},
                              "why": "one generic image served to %d players "
                                     "(distinct %.2f) -- not headshots"
                                     % (len(found), distinct)}
                rejected += 1
            else:
                done[team] = {"status": "ok", "photos": found,
                              "distinct": round(distinct, 3)}
                kept += 1
        print("  %-22s %d/%d  %s" % (team, i, len(todo),
              ("%d photos" % len(done[team]["photos"])) if done[team]["photos"]
              else ("rejected: " + done[team].get("why", ""))))
        json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                            "rule": "og:image on the player's own page; a team "
                                    "whose URLs are not mostly distinct is "
                                    "rejected as a generic banner",
                            "min_distinct": MIN_DISTINCT},
                   "teams": done}, open(OUT, "w"), indent=1, sort_keys=True)
    print("\nkept %d teams, rejected %d -> %s" % (kept, rejected, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
