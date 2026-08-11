#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026 roster pull: name + class year from 348 school athletics sites.

ANNUAL PRESEASON JOB. Not wired into the daily cron -- rosters change once a
year, and this hits 348 separate athletic-department servers rather than one
API.

THE URL CHAIN, solved before any parser was written (same discipline as proving
the game log was enumerable before crawling it):
    teamId -> seoname (already in the game log)
           -> ncaa.com/schools/{seo}  -> "school-links" block
           -> official athletics domain
           -> /sports/{path}/roster
Measured on a 12-school sample: 12/12 athletics URLs resolved, 10/12 rosters
yielded class years from a PLAIN fetch (no JS). Both failures were path, not
platform -- Nebraska uses /sports/volleyball/roster because it sponsors no
men's team.

PLATFORMS: SIDEARM dominates; Kentucky runs WMT at /sports/wvball/roster.
Gemini's cited SIDEARM selectors are stale (the template is now s-person-*), so
this does not use CSS selectors at all -- it extracts from the JSON payload
SIDEARM embeds, and falls back to text scanning.

RAW STRINGS AS SERVED. "Sr." / "Senior" / "SR" are stored exactly as the page
wrote them. Normalisation happens downstream, never at ingest -- same principle
as raw counts over derived rates.

POLITENESS. 1.5 req/s, self-identifying user agent, and a 403 or rate-limit is
recorded as UNCOVERED rather than retried hard. An em dash costs nothing;
annoying a school webmaster costs goodwill we cannot measure.

Python 3.9 target.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
SRC = os.path.join(REPO, "data", "raw", "2025")     # seonames come from the game log
OUT = os.path.join(RAW, "rosters_%d.json" % SEASON)
SITES = os.path.join(RAW, "athletics_sites.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamelog import load_games_jsonl  # noqa: E402
from reconcile_2025 import norm  # noqa: E402

UA = ("wvb-hub/0.1 (personal research project, ~1.5 req/s; "
      "github.com/6vrhm29rzs-a11y/wvb-hub)")
MIN_INTERVAL = 0.7
TIMEOUT = 25

ROSTER_PATHS = [
    "/sports/womens-volleyball/roster",
    "/sports/volleyball/roster",          # schools with no men's team (Nebraska)
    "/sports/wvball/roster",              # WMT (Kentucky)
    "/sports/wvb/roster",
    "/sports/womens-volleyball/roster/2026-27",
    "/sports/womens-volleyball/roster/2026",
]

CLASS_RE = re.compile(
    r"\b(Freshman|Sophomore|Junior|Senior|Graduate|Redshirt\s+\w+|"
    r"Fr\.?|So\.?|Jr\.?|Sr\.?|Gr\.?|R-Fr\.?|R-So\.?|R-Jr\.?|R-Sr\.?)\b")

_last = [0.0]


def throttle():
    d = time.time() - _last[0]
    if d < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - d)
    _last[0] = time.time()


def fetch(url):
    # type: (str) -> Tuple[Optional[str], str]
    """Returns (html, status). Never retries hard -- see POLITENESS above."""
    throttle()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace"), "ok"
    except urllib.error.HTTPError as e:
        return None, "http%d" % e.code
    except Exception as e:
        return None, type(e).__name__.lower()


def seonames():
    # type: () -> Dict[str, Dict[str, str]]
    out = {}
    for g in load_games_jsonl(os.path.join(SRC, "games.jsonl")):
        for t in (g.get("teams") or []):
            s, n = t.get("seoname"), t.get("name_short")
            if s and n and t.get("division") is not None:
                out[n] = {"seoname": s, "team_id": t.get("team_id")}
    return out


def athletics_site(seo):
    # type: (str) -> Tuple[Optional[str], str]
    html, st = fetch("https://www.ncaa.com/schools/%s" % seo)
    if not html:
        return None, st
    m = re.search(r'class="school-links".*?<a\s+href="(https?://[^"]+)"', html, re.S)
    return (m.group(1).rstrip("/") if m else None), ("ok" if m else "no-link")


def parse_roster(html):
    # type: (str) -> List[Dict[str, str]]
    """Extract players by NAME ANCHOR, then the nearest class token after it.

    Deliberately not CSS-selector based and not JSON based. Measured on the
    current SIDEARM template: there is NO embedded player JSON (no firstName,
    no academicYear), and the classes cited in earlier research (s-person-*)
    are gone -- it now renders roster-player-card-*. Selectors break on every
    redesign; a link to a player's own page plus a class word near it survives
    them, and works across platforms.
    """
    players = []
    # Three link shapes observed on four schools, so match the SHAPE-INDEPENDENT
    # thing: an anchor whose href passes through /roster/ and whose visible text
    # reads as a person's name.
    #   Stanford  /sports/womens-volleyball/roster/player/sarah-hickman
    #   Nebraska  /roster/player/{slug}          (name nested inside child tags)
    #   Hofstra   /sports/womens-volleyball/roster/nil-kayaalp/17216   (no /player/)
    NAME = re.compile(r"^[A-Z][A-Za-z'`\u00c0-\u024f.-]+(?:\s+[A-Z][A-Za-z'`\u00c0-\u024f.-]+){1,3}$")
    for m in re.finditer(r'<a\b[^>]*href="([^"]*/roster/[^"]*)"[^>]*>(.*?)</a>',
                         html, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        if re.search(r"/roster/?$", href):
            continue                      # the roster index itself, not a player
        # COACHING STAFF are linked from the same roster page and pick up a
        # neighbouring player's class token, which made six Nebraska staff --
        # including a male name on a women's roster -- look like seniors.
        # Tightening the class window instead broke three other templates, so
        # discriminate STRUCTURALLY: staff live under a different path.
        #   player: /roster/player/harper-murray
        #   staff:  /roster/season/2026/staff/nate-wilson
        if re.search(r"/(staff|coach|coaches|administration|support-staff)/", href, re.I):
            continue
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        if not NAME.match(name):
            continue
        # "Full Bio" / "View Profile" links sit inside the same card and match
        # the two-capitalised-words shape.
        low = name.lower()
        if low in ("full bio", "view profile", "view bio", "read more",
                   "player bio", "full profile") or \
           low.startswith(("view ", "full bio", "read ")) or "bio" == low.split()[-1]:
            continue
        # SAME BUG CLASS, different template: WMT wraps the headshot in its own
        # anchor whose text is "<Player Name> Photo". That is not a "Full Bio"
        # string so the list above misses it, and because the dedup below keyed
        # on the exact string, each player survived TWICE -- once clean, once
        # with the trailing token. Miami (FL) shipped 30 "players" for a
        # 15-player roster and every Photo copy landed in UNRESOLVED. Strip the
        # media token rather than dropping the anchor: on some templates the
        # headshot link is the ONLY anchor a player has.
        name = re.sub(r"\s+(photo|headshot|image|picture)$", "", name, flags=re.I)
        # Look BOTH sides: some templates put the class before the name (table
        # rows), others after (cards).
        window = html[m.end():m.end() + 1800]
        before = html[max(0, m.start() - 900):m.start()]
        flat = re.sub(r"<[^>]+>", " ", window)
        flat_b = re.sub(r"<[^>]+>", " ", before)
        cm = CLASS_RE.search(flat) or CLASS_RE.search(flat_b)
        num = re.search(r'>\s*#?\s*(\d{1,2})\s*<', window)
        pos = re.search(r'\b(OH|MB|OPP|RS|DS|L|S)\b', flat[:300])
        players.append({
            "first": name.split(" ")[0],
            "last": " ".join(name.split(" ")[1:]) or None,
            "name_raw": name,
            "class_raw": cm.group(1) if cm else None,
            "pos_raw": pos.group(1) if pos else None,
            "num_raw": num.group(1) if num else None,
            "how": "roster-anchor",
        })
    # Anchors under /roster/ also cover coaches and support staff, which is why
    # raw counts came out above a real roster size. A player has a class year or
    # a jersey number; staff have neither.
    players = [p for p in players if p.get("class_raw") or p.get("num_raw")]
    # de-duplicate: cards and table rows both link the same player
    seen, out = set(), []
    for p in players:
        # normalise the key: an exact-string key let "Avery Bain Photo" and
        # "Avery Bain" both through as separate people.
        k = re.sub(r"[^a-z]", "", (p["name_raw"] or "").lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def main():
    if not os.path.isdir(RAW):
        os.makedirs(RAW)
    teams = seonames()
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    if only:
        teams = {k: v for k, v in teams.items() if k in only}
    print("resolving athletics sites for %d teams" % len(teams))

    sites = {}
    if os.path.exists(SITES):
        sites = json.load(open(SITES))
    for i, (name, meta) in enumerate(sorted(teams.items()), 1):
        if name in sites:
            continue
        url, st = athletics_site(meta["seoname"])
        sites[name] = {"url": url, "status": st, "seoname": meta["seoname"],
                       "team_id": meta.get("team_id")}
        if i % 50 == 0:
            print("  %d/%d sites resolved" % (i, len(teams)))
            json.dump(sites, open(SITES, "w"), indent=1)
    json.dump(sites, open(SITES, "w"), indent=1)
    got = sum(1 for v in sites.values() if v.get("url"))
    print("athletics sites: %d/%d resolved" % (got, len(sites)))

    rosters = {}
    if os.path.exists(OUT):
        try:
            rosters = json.load(open(OUT)).get("teams", {})
        except Exception:
            rosters = {}

    stats = {"ok": 0, "no_site": 0, "no_roster": 0, "blocked": 0}
    for i, (name, meta) in enumerate(sorted(sites.items()), 1):
        if name in rosters and rosters[name].get("players"):
            continue
        base = meta.get("url")
        if not base:
            rosters[name] = {"status": "no-athletics-site", "players": []}
            stats["no_site"] += 1
            continue
        hit = None
        last_status = "not-found"
        for path in ROSTER_PATHS:
            html, st = fetch(base + path)
            if st.startswith("http4") or st.startswith("http5"):
                last_status = st
                if st in ("http403", "http429"):
                    break        # back off, do not hammer
                continue
            if html and CLASS_RE.search(html):
                pl = parse_roster(html)
                if pl:
                    hit = (path, pl, html)
                    break
                last_status = "no-players-parsed"
        if hit:
            path, pl, html = hit
            plat = ("SIDEARM" if "sidearm" in html.lower() else
                    "WMT" if "wmt" in html.lower() else
                    "PRESTO" if "presto" in html.lower() else "unknown")
            rosters[name] = {
                "status": "ok", "url": base + path, "platform": plat,
                "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source_tier": "OFFICIAL",
                "team_id": meta.get("team_id"),
                "players": pl,
            }
            stats["ok"] += 1
        else:
            rosters[name] = {"status": last_status, "players": [],
                             "team_id": meta.get("team_id")}
            if last_status in ("http403", "http429"):
                stats["blocked"] += 1
            else:
                stats["no_roster"] += 1
        if i % 25 == 0:
            print("  %d/%d  ok=%d no-roster=%d blocked=%d"
                  % (i, len(sites), stats["ok"], stats["no_roster"], stats["blocked"]))
            json.dump({"meta": {"season": SEASON}, "teams": rosters},
                      open(OUT, "w"), indent=1)

    payload = {
        "meta": {
            "season": SEASON, "source_tier": "OFFICIAL",
            "source": "school athletics sites, one request each, ~1.5 req/s",
            "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "coverage": {"teams": len(rosters), "with_players": stats["ok"],
                         "no_athletics_site": stats["no_site"],
                         "no_roster_found": stats["no_roster"],
                         "blocked_403_429": stats["blocked"]},
            "note": "Class years stored EXACTLY as served. No normalisation at "
                    "ingest. Teams without a usable roster carry an empty list, "
                    "never an estimate.",
        },
        "teams": rosters,
    }
    json.dump(payload, open(OUT, "w"), indent=1)
    print()
    print("COVERAGE: %d/%d teams with players (%.0f%%)"
          % (stats["ok"], len(rosters), 100.0 * stats["ok"] / max(len(rosters), 1)))
    print("  no athletics site %d · no roster found %d · blocked %d"
          % (stats["no_site"], stats["no_roster"], stats["blocked"]))
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
