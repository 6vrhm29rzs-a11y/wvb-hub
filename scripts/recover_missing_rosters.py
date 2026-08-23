#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover the rosters the main crawl could not find.

28 of 348 teams came back with no players -- LSU, Vanderbilt, Arkansas,
Syracuse, Wake Forest among them -- each with an honest status recorded
(`http404`, `not-found`, `no-players-parsed`). The cause is the roster PATH,
not the site: `crawl_rosters.py` guesses a small set of URL shapes, and these
schools use others (`/sports/wvolley/roster` at Vanderbilt,
`/sport/w-volley/roster/` at Arkansas).

So instead of guessing, ASK THE SITE: fetch the school's home page and read the
link it gives to its own women's volleyball roster.

Additive by construction -- writes its OWN file, merged at build time. It cannot
alter or drop anything the main crawl already found.

Python 3.9 target.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as CR  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
ROSTERS = os.path.join(RAW, "rosters_%d.json" % SEASON)
SITES = os.path.join(RAW, "athletics_sites.json")
OVERRIDES = os.path.join(RAW, "athletics_sites_overrides.json")
PLAYERBOX25 = os.path.join(REPO, "data", "raw", "2025", "playerbox.jsonl")
OUT = os.path.join(RAW, "rosters_recovered_%d.json" % SEASON)

# Tried only after the home page yields nothing.
FALLBACK_PATHS = (
    "/sports/womens-volleyball/roster",
    "/sports/wvolley/roster",
    "/sport/w-volley/roster/",
    "/sports/w-volley/roster",
    "/sports/wvball/roster",
    "/sports/volleyball/roster",
    # LAST RESORT: short sport codes. `vb` is women's volleyball at a school
    # with no men's programme (LSU), but it could be the men's roster
    # elsewhere -- which is why these come last and why the 2025-overlap
    # confirmation below is what actually accepts a roster.
    "/sports/vb/roster",
    "/sports/wvb/roster",
)

# A women's volleyball roster link, not the men's and not a schedule.
VB_ROSTER = re.compile(r'href="([^"]*(?:w-?volley|womens-volleyball|wvball)[^"]*roster[^"]*)"', re.I)
MIN_PLAYERS = 8


def absolutise(href, base):
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")


# Some templates wrap the jersey number INSIDE the player's own link:
#   <a href=".../player/hailee-mack"><span class="...__number">#1</span> Hailee Mack</a>
# Flattened that reads "#1 Hailee Mack", which fails the parser's name-shape
# test, so every player on the page is discarded and the roster looks empty.
# Strip the number span before parsing rather than loosening the name test --
# the name test is what keeps "Full Bio" and staff links out.
NUM_SPAN = re.compile(r"<span[^>]*>\s*#\s*\d{1,2}\s*</span>", re.I)


MAX_PLAYERS = 32


def players_from_jsonld(html):
    # type: (str) -> List[Dict]
    """Roster from schema.org JSON-LD, for pages that render in JavaScript.

    SIDEARM's newer template emits the roster table client-side -- the anchors
    in the served HTML are literal JS expressions
    (`'/sports/' + sport.global_sport_name_slug + '/roster/' + slugify(...)`),
    so the name-anchor parser finds nothing and the roster reads as empty.
    The same page carries the players as `Person` entries in ld+json.

    Names ONLY. No class year and no position come through this route, so those
    render as unlisted rather than being invented -- which is the honest result
    and the same ceiling the photo and position passes hit.

    Bounded to a plausible squad size: a page whose Person blocks include
    coaches or unrelated people would blow past it, and a wrong roster is worse
    than a missing one.
    """
    names = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("@type") == "Person" and node.get("name"):
                nm = re.sub(r"\s+", " ", node["name"]).strip()
                if nm and nm not in names:
                    names.append(nm)
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

    if not (MIN_PLAYERS <= len(names) <= MAX_PLAYERS):
        return []
    out = []
    for nm in names:
        parts = nm.split(" ")
        out.append({"first": parts[0], "last": " ".join(parts[1:]) or None,
                    "name_raw": nm, "class_raw": None, "pos_raw": None,
                    "num_raw": None, "how": "schema-person", "photo": None})
    return out


LAST_HTML = {"html": ""}


def try_url(url):
    # type: (str) -> Optional[List[Dict]]
    html, status = CR.fetch(url)
    if not html or status != "ok":
        return None
    LAST_HTML["html"] = html
    stripped = NUM_SPAN.sub(" ", html)
    try:
        players = CR.parse_roster(stripped)
    except Exception:                                  # noqa: BLE001
        players = []
    players = [p for p in players if p.get("_player_path")] or players
    if len(players) >= MIN_PLAYERS:
        return players
    # JS-rendered page: fall back to the structured data it still ships
    return players_from_jsonld(html) or None


def prior_names_by_team():
    """team_id -> set of surnames that played for it in 2025.

    This is how a corrected domain is CONFIRMED. That a domain resolves proves
    nothing -- it could be any school, or a parked page. A real roster for the
    right team shares returning players with that team's own 2025 box scores.
    Evidence from outside the thing being adjudicated (R8).
    """
    import collections
    idx = collections.defaultdict(set)
    if not os.path.exists(PLAYERBOX25):
        return idx
    for line in open(PLAYERBOX25):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        for r in rec.get("rows", []):
            last = re.sub(r"[^a-z]", "", (r.get("last") or "").lower())
            if last:
                idx[str(r.get("team_id"))].add(last)
    return idx


def main():
    doc = json.load(open(ROSTERS))
    rosters = doc.get("teams", {})
    sites = json.load(open(SITES))
    overrides = {}
    if os.path.exists(OVERRIDES):
        overrides = (json.load(open(OVERRIDES)) or {}).get("teams", {})
    prior = prior_names_by_team()
    have = {}
    if os.path.exists(OUT):
        have = (json.load(open(OUT)) or {}).get("teams", {})

    todo = [t for t, v in rosters.items()
            if not (v.get("players") or []) and t not in have]
    print("teams with no roster: %d" % len(todo))

    ok = 0
    for team in sorted(todo):
        base = overrides.get(team) or (sites.get(team) or {}).get("url")
        if not base:
            have[team] = {"status": "no-athletics-site", "players": []}
            print("  %-20s no athletics site" % team)
            continue

        found = None
        # 1) ask the home page which URL it uses
        html, status = CR.fetch(base)
        if html and status == "ok":
            for href in dict.fromkeys(VB_ROSTER.findall(html)):
                url = absolutise(href.split("#")[0], base)
                players = try_url(url)
                if players:
                    found = (url, players)
                    break
        # 2) only then fall back to guessing
        if not found:
            for path in FALLBACK_PATHS:
                url = base.rstrip("/") + path
                players = try_url(url)
                if players:
                    found = (url, players)
                    break

        if found:
            # CONFIRM it is really this team, not merely a site that parsed.
            last_html = LAST_HTML.get("html", "")
            tid = str((sites.get(team) or {}).get("team_id"))
            known = prior.get(tid) or set()
            got = set(re.sub(r"[^a-z]", "", (p.get("last") or "").lower())
                      for p in found[1] if p.get("last"))
            overlap = len(known & got)
            # TWO INDEPENDENT CONFIRMATIONS, because either alone can be wrong:
            #  (a) shared 2025 players -- strong, but fails on a team that
            #      genuinely turned its roster over. Syracuse was rejected at a
            #      self-chosen ">=2" cutoff despite cuse.com really being theirs;
            #      they returned 1 of 16. A verdict that hinges on a threshold I
            #      picked has tested nothing (R1).
            #  (b) the site identifies the school -- independent of the roster.
            # Accept on either; record which fired so a weak case stays visible.
            seo = (sites.get(team) or {}).get("seoname") or ""
            seo_tok = re.sub(r"[^a-z]", "", seo.lower())
            page = (last_html or "").lower()
            names_school = bool(seo_tok) and seo_tok in re.sub(r"[^a-z]", "", page)
            if known and overlap < 2 and not names_school:
                have[team] = {"status": "unconfirmed", "url": found[0],
                              "players": [], "overlap": overlap}
                print("  %-20s UNCONFIRMED %s (%d shared 2025 names, site does "
                      "not name the school)" % (team, found[0], overlap))
                json.dump({"meta": {"season": SEASON}, "teams": have},
                          open(OUT, "w"), indent=1)
                continue
            have[team] = {"status": "ok", "url": found[0], "players": found[1],
                          "confirmed_by_2025_overlap": overlap,
                          "confirmed_by_site_naming_school": names_school,
                          "overridden_domain": team in overrides}
            ok += 1
            print("  %-20s %d players  overlap=%d  %s"
                  % (team, len(found[1]), overlap, found[0]))
        else:
            have[team] = {"status": "still-not-found", "players": []}
            print("  %-20s still not found" % team)
        json.dump({"meta": {"season": SEASON, "source_tier": "OFFICIAL",
                            "source": "school athletics sites; roster URL read "
                                      "from the school's own home page",
                            "note": "Additive. Merged at build time; "
                                    "rosters_%d.json is never rewritten." % SEASON},
                   "teams": have}, open(OUT, "w"), indent=1)

    print("recovered %d of %d -> %s" % (ok, len(todo), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
