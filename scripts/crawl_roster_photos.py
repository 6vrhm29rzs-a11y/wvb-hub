#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Photo URLs for rosters whose page renders in JavaScript.

`crawl_rosters.py` finds a headshot by looking for an <img> near the player's
own anchor. That works on templates that ship the roster as HTML and finds
nothing on the ones that build it client-side -- which left photo coverage at
38.4% of players (133 of 347 teams). Those same pages still emit the squad as
schema.org `Person` blocks, and each block carries an `image.url`.

URLS ONLY. The image is never downloaded and never committed: this repo is
PUBLIC and the photographs belong to the schools. Storing a reference is a
different act from republishing the file. A player without one renders her
initials, never a stand-in image.

Additive: writes its own file, merged at build time. It cannot alter or drop
anything the roster crawl already found.

Python 3.9 target.
"""

import json
import os
import re
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as CR  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
ROSTERS = os.path.join(RAW, "rosters_%d.json" % SEASON)
RECOVERED = os.path.join(RAW, "rosters_recovered_%d.json" % SEASON)
OUT = os.path.join(RAW, "roster_photos_%d.json" % SEASON)


def nkey(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def clean_url(url, base):
    """Two repairs, both measured on live templates:

    * WMT emits a DOUBLED prefix -- `site.com/https://site.com/imgproxy/...` --
      which 404s. Keep the absolute URL that starts inside it.
    * SIDEARM crop URLs carry `&amp;` query separators that 400 unless decoded.
    """
    if not url:
        return None
    url = url.strip().replace("&amp;", "&")
    m = re.search(r"https?://.*https?://", url)
    if m:
        url = url[url.index("http", url.index("http") + 1):]
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        url = base.rstrip("/") + "/" + url.lstrip("/")
    # a base64 placeholder is not a photograph
    if url.startswith("data:"):
        return None
    return url


def photos_from_jsonld(html, base):
    # type: (str, str) -> Dict[str, str]
    out = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("@type") == "Person" and node.get("name"):
                img = node.get("image")
                url = img.get("url") if isinstance(img, dict) else (
                    img if isinstance(img, str) else None)
                url = clean_url(url, base)
                if url:
                    out.setdefault(nkey(node["name"]), url)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for block in re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S | re.I):
        try:
            walk(json.loads(block.strip()))
        except ValueError:
            continue
    return out


def main():
    rosters = dict((json.load(open(ROSTERS)) or {}).get("teams", {}))
    if os.path.exists(RECOVERED):
        for team, rec in ((json.load(open(RECOVERED)) or {})
                          .get("teams", {}) or {}).items():
            if rec.get("players") and rec.get("url"):
                rosters.setdefault(team, {})
                rosters[team] = {"players": rec["players"], "url": rec["url"]}

    have = {}
    if os.path.exists(OUT):
        have = (json.load(open(OUT)) or {}).get("teams", {})

    todo = []
    for team, rec in rosters.items():
        players = rec.get("players") or []
        if not players or not rec.get("url") or team in have:
            continue
        if any(p.get("photo") for p in players):
            continue                      # the roster crawl already got these
        todo.append(team)

    print("teams needing photos: %d" % len(todo))
    matched_total = 0
    ok = 0
    for n, team in enumerate(sorted(todo), 1):
        base = rosters[team]["url"]
        html, status = CR.fetch(base)
        if not html or status != "ok":
            have[team] = {"status": status, "photos": {}}
            continue
        found = photos_from_jsonld(html, base)
        # only keep photos we can attach to a player ON THIS ROSTER
        names = dict((nkey(p.get("name_raw") or ""), p.get("name_raw"))
                     for p in rosters[team]["players"])
        matched = dict((names[k], v) for k, v in found.items() if k in names)
        have[team] = {"status": "ok", "photos": matched,
                      "of_players": len(names)}
        matched_total += len(matched)
        if matched:
            ok += 1
        if n % 25 == 0:
            print("  %d/%d teams=%d photos=%d" % (n, len(todo), ok, matched_total))
            json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                                "source": "school athletics sites, schema.org "
                                          "Person image URLs",
                                "note": "URLS ONLY -- images are never "
                                        "downloaded or committed."},
                       "teams": have}, open(OUT, "w"), indent=1)

    json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                        "source": "school athletics sites, schema.org Person "
                                  "image URLs",
                        "note": "URLS ONLY -- images are never downloaded or "
                                "committed. Additive; rosters_%d.json is never "
                                "rewritten." % SEASON},
               "teams": have}, open(OUT, "w"), indent=1)
    print("done: %d teams gained photos, %d player photos -> %s"
          % (ok, matched_total, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
