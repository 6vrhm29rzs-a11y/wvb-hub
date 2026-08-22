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
from html import unescape as _unescape
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



# ---------------------------------------------------------------- headshots
# URLS ONLY. The photo itself is never downloaded and never committed: this repo
# is PUBLIC, the images belong to the schools, and storing a reference is a
# different act from republishing the file. The page loads them from the
# school's own server and shows initials when one is missing.
_IMG_NEAR = re.compile(r'<img\b[^>]*?(?:data-src|src)="([^"]+)"', re.I)
_NOT_A_HEADSHOT = re.compile(
    r"(logo|icon|sprite|placeholder|default|blank|spacer|social|sponsor|"
    r"facebook|twitter|instagram|tiktok|\.svg(?:\?|$))", re.I)


def _absolutise(url, base):
    """Repair and absolutise a photo URL.

    WMT emits a doubled prefix -- "https://site.com/https://site.com/imgproxy/..."
    -- which is not a URL and 404s if used as one. Measured on Kentucky, where
    all 17 headshots came out that way.
    """
    if not url:
        return None
    # HTML-decode first. A SIDEARM crop URL carries its parameters as
    # "&amp;width=100&amp;height=100", and handing that to a server verbatim
    # gets a 400 -- measured on Tennessee, whose photos all failed until this.
    url = _unescape(url).strip()
    m = re.search(r"https?://.*?(https?://.*)$", url)
    if m:                      # doubled prefix: keep the inner, real one
        url = m.group(1)
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    if url.startswith("/") and base:
        return base.rstrip("/") + url
    return None


def _schema_photos(html, base):
    """name -> photo, from schema.org microdata.

    WMT wraps each player in an itemscope Person and states the name and image
    as sibling <span itemprop> tags with no <img> anywhere near the player's
    link -- so the neighbourhood search below finds nothing. Pairing the two
    itemprops recovers all of them.
    """
    out = {}
    for m in re.finditer(
            r'itemprop="name"[^>]*content="([^"]+)"(.{0,400}?)itemprop="image"'
            r'[^>]*content="([^"]+)"', html, re.S):
        nm = _unescape(m.group(1)).strip()
        url = _absolutise(_unescape(m.group(3)), base)
        if nm and url:
            out.setdefault(re.sub(r"[^a-z]", "", nm.lower()), url)
    return out


def _photo_for(html, anchor_start, anchor_end, base):
    """The first plausible headshot in the neighbourhood of a player's link."""
    window = html[max(0, anchor_start - 1200):anchor_end + 1200]
    for m in _IMG_NEAR.finditer(window):
        u = m.group(1)
        # A base64 data: URI is a lazy-loading placeholder -- a 1x1 transparent
        # gif -- not a headshot. UCLA's template ships only that, with the real
        # URL fetched by JavaScript, so its photos are genuinely absent from the
        # HTML and are reported missing rather than guessed at.
        if u.startswith("data:") or _NOT_A_HEADSHOT.search(u):
            continue
        got = _absolutise(u, base)
        if got:
            return got
    return None

def _slug_matches(href, name):
    """True when ANY path segment of href spells the anchor's own text.

    Not just the last segment: SIDEARM appends a numeric id, so the player link
    is /roster/victoria-harris/15501 and the name sits second from the end.
    Checking only the tail matched nothing and left SMU's roster empty.
    """
    flat = re.sub(r"[^a-z]", "", (name or "").lower())
    if not flat:
        return False
    for seg in (href or "").split("/"):
        if seg and re.sub(r"[^a-z]", "", seg.lower()) == flat:
            return True
    return False


def parse_roster(html, base=None):
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
        # HTML-ENTITY DECODE BEFORE THE SHAPE TEST. Roster templates emit the
        # apostrophe in a surname as a numeric entity -- "Kassie O&#039;Brien"
        # -- and the NAME pattern below rejects "&", "#" and digits, so every
        # such player was dropped from every roster ON EVERY PLATFORM, then
        # classified DEPARTED because she was absent from her own 2026 roster.
        # Kassie O'Brien (Kentucky, 2025 National Freshman of the Year, 114
        # sets) was reported as departed while listed on the live page.
        # Silent, name-shaped, and it never looked like a parse failure --
        # the roster just came back one player short.
        name = _unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner))).strip()
        name = re.sub(r"\s+", " ", name)
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
            # STRUCTURAL proof of personhood: /roster/player/<slug> is the path
            # players get and staff never do (staff are filtered by path above).
            # Used by the staff filter below instead of requiring a class token.
            # Two structural signals, either one sufficient:
            #   (a) /roster/player/<slug> -- the explicit player path.
            #   (b) the final URL slug de-hyphenates to the anchor's own text,
            #       e.g. /roster/victoria-harris/ linked as "Victoria Harris".
            # (b) covers templates with no /player/ segment (SMU, Utah St.),
            # where the class-token proxy was failing and the whole roster came
            # back empty. A link whose slug spells the displayed name is a
            # person's page; "Full Bio" and "Ticket Office" do not match theirs.
            "_player_path": bool(re.search(r"/roster/player/", href, re.I))
                            or _slug_matches(href, name),
            "first": name.split(" ")[0],
            "last": " ".join(name.split(" ")[1:]) or None,
            "name_raw": name,
            "class_raw": cm.group(1) if cm else None,
            "pos_raw": pos.group(1) if pos else None,
            "num_raw": num.group(1) if num else None,
            "how": "roster-anchor",
            "photo": _photo_for(html, m.start(), m.end(), base),
        })
    # Anchors under /roster/ also cover coaches and support staff, which is why
    # raw counts came out above a real roster size.
    #
    # The old rule was "a player has a class year or a jersey number; staff have
    # neither". That is a PROXY, and templates broke it: SIDEARM moved the class
    # token out of the anchor's neighbourhood, so the proxy started deleting real
    # players -- silently, because a short roster looks like a small roster.
    # Measured 2026-08-18: Virginia 17 players -> 0 (every one lacked a nearby
    # class token, so the team read as "no roster found"), UCLA 18 -> 9. Their
    # production then counts as DEPARTED, which is the same failure Kassie
    # O'Brien surfaced, from a different direction.
    #
    # Prefer the STRUCTURAL fact over the proxy: /roster/player/<slug> is a path
    # staff do not get. Keep the class/number requirement only for templates
    # that do not use it (e.g. /roster/nil-kayaalp/17216), where the proxy is
    # still the only discriminator available.
    players = [p for p in players
               if p.get("_player_path") or p.get("class_raw") or p.get("num_raw")]
    for p in players:
        p.pop("_player_path", None)
    # photos: neighbourhood <img> first, schema.org microdata as the fallback
    schema = _schema_photos(html, base)
    for p in players:
        key = re.sub(r"[^a-z]", "", (p["name_raw"] or "").lower())
        p["photo"] = p.get("photo") or schema.get(key)

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
        # STRIP THE URL. One cached entry was "https://utsports.com " with a
        # trailing space; every path built from it 404'd, so Tennessee -- a
        # top-20 team -- carried no roster at all and its whole 2025 production
        # read as departed. A single invisible character, and nothing in the
        # pipeline could see it. Cheap to defend against permanently.
        base = (meta.get("url") or "").strip() or None
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
                pl = parse_roster(html, base)
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
