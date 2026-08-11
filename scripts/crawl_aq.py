#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conference AQ-mechanism map: does each league award its bid by TOURNAMENT or
by REGULAR-SEASON CHAMPION?

WHY THIS MATTERS. The field projector backtested at 62/64. One of the two misses
was an AQ inference failure -- the game feed carries no bracket structure, so a
conference final, a consolation game and a regular-season finale are
indistinguishable. This replaces a heuristic with DATA, which was the diagnosis
when tuning stopped at 62/64. Three heuristic variants all scored 62/64 while
only shuffling WHICH conference broke; that is an information limit, not a
tuning problem.

Reassigned from the Architect seat, which was asked twice and produced zero rows.

SIX ROWS ARE ALREADY CONFIRMED by Claude-app's research and are used AS GIVEN.
This crawl does not re-derive them; if it finds something contradicting one, the
contradiction is FLAGGED rather than silently overriding either source.

EVERY ROW CARRIES ITS SOURCE URL and is marked CONFIRMED or UNVERIFIED.
"Couldn't find it" is a real result and is recorded as such, not left blank.

Politeness: ~1.5 req/s, self-identifying UA, no hard retries. Same rules as the
school-roster crawl.

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
OUT = os.path.join(REPO, "data", "raw", "2026", "aq_mechanism_2026.json")

UA = ("wvb-hub/0.1 (personal research project, ~1.5 req/s; "
      "github.com/6vrhm29rzs-a11y/wvb-hub)")
MIN_INTERVAL = 0.7

# CONFIRMED by Claude-app, 2026 season. Used as given, never re-derived.
CONFIRMED = {
    "Big Ten": {"mechanism": "TOURNAMENT", "detail": "first ever, 2026; top 15 of 18; "
                "Nov 20-25; Fishers IN", "tier": "CONFIRMED (Claude-app research)"},
    "Pac-12": {"mechanism": "TOURNAMENT", "detail": "new; top 4; week of Nov 23",
               "tier": "CONFIRMED (Claude-app research)"},
    "SEC": {"mechanism": "TOURNAMENT", "detail": "added 2025; Nov 20-24; Savannah GA",
            "tier": "CONFIRMED (Claude-app research)"},
    "ACC": {"mechanism": "REGULAR_SEASON", "detail": "regular-season champion takes the bid",
            "tier": "CONFIRMED (Claude-app research)"},
    "Big 12": {"mechanism": "REGULAR_SEASON", "detail": "highest conference win pct",
               "tier": "CONFIRMED (Claude-app research)"},
    "Mountain West": {"mechanism": "TOURNAMENT", "detail": "top 4",
                      "tier": "CONFIRMED (Claude-app research)"},
}

# Conference -> official site. Derived from the RPI table's Conf labels.
SITES = {
    "America East": "americaeast.com", "American": "theamerican.org",
    "ASUN": "asunsports.org", "Atlantic 10": "atlantic10.com",
    "Big East": "bigeast.com", "Big Sky": "bigskyconf.com",
    "Big South": "bigsouthsports.com", "Big West": "bigwest.org",
    "CAA": "caasports.com", "CUSA": "conferenceusa.com",
    "Horizon": "horizonleague.org", "Ivy League": "ivyleague.com",
    "MAAC": "maacsports.com", "MAC": "getsomemaction.com",
    "MEAC": "meacsports.com", "MVC": "mvc-sports.com",
    "NEC": "northeastconference.org", "OVC": "ovcsports.com",
    "Patriot": "patriotleague.org", "SoCon": "soconsports.com",
    "Southland": "southland.org", "SWAC": "swac.org",
    "Summit League": "thesummitleague.org", "Sun Belt": "sunbeltsports.org",
    "WAC": "wacsports.com", "WCC": "wccsports.org",
}

PATHS = ["/sports/wvball", "/sports/womens-volleyball",
         "/index.aspx?path=wvball", "/sports/wvball/championship",
         "/championships/wvball"]

TOURN = re.compile(r"\b(championship tournament|conference tournament|"
                   r"volleyball championship|tournament bracket|quarterfinal|semifinal)\b",
                   re.I)
REGSEA = re.compile(r"\b(regular[- ]season champion|regular season title|"
                    r"no (?:conference )?tournament)\b", re.I)

_last = [0.0]


def throttle():
    d = time.time() - _last[0]
    if d < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - d)
    _last[0] = time.time()


def fetch(url):
    throttle()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace"), "ok"
    except urllib.error.HTTPError as e:
        return None, "http%d" % e.code
    except Exception as e:
        return None, type(e).__name__.lower()


def main():
    rows = {}
    for conf, info in CONFIRMED.items():
        rows[conf] = dict(info, source="Claude-app research handoff", checked=False)

    todo = [c for c in sorted(SITES) if c not in rows]
    print("AQ MECHANISM MAP — %d confirmed, %d to investigate"
          % (len(rows), len(todo)))

    for conf in todo:
        host = SITES[conf]
        found = None
        last = "not-found"
        for path in PATHS:
            for scheme in ("https://www.", "https://"):
                html, st = fetch(scheme + host + path)
                if not html:
                    last = st
                    continue
                t, r = bool(TOURN.search(html)), bool(REGSEA.search(html))
                if t or r:
                    found = {
                        "mechanism": ("TOURNAMENT" if t and not r else
                                      "REGULAR_SEASON" if r and not t else "AMBIGUOUS"),
                        "detail": ("page mentions a championship tournament" if t and not r
                                   else "page states a regular-season champion" if r and not t
                                   else "page mentions BOTH -- needs a human read"),
                        "tier": "UNVERIFIED (page text match, not a rules citation)",
                        "source": scheme + host + path,
                        "checked": True,
                    }
                    break
            if found:
                break
        rows[conf] = found or {
            "mechanism": None, "detail": "could not locate a volleyball "
            "championship page", "tier": "UNVERIFIED — NOT FOUND",
            "source": "https://" + host, "checked": True,
            "last_status": last,
        }
        m = rows[conf].get("mechanism")
        print("  %-16s %-14s %s" % (conf, m or "NOT FOUND", rows[conf]["tier"][:34]))

    conf_n = sum(1 for v in rows.values() if v["tier"].startswith("CONFIRMED"))
    unv = sum(1 for v in rows.values() if v.get("mechanism") and
              v["tier"].startswith("UNVERIFIED"))
    miss = sum(1 for v in rows.values() if not v.get("mechanism"))
    print()
    print("  CONFIRMED %d · UNVERIFIED-with-answer %d · NOT FOUND %d · total %d"
          % (conf_n, unv, miss, len(rows)))
    print("  'NOT FOUND' is a result, not a failure -- those conferences keep the")
    print("  TOURNAMENT default in project_field.py and stay flagged unverified.")

    d = os.path.dirname(OUT)
    if not os.path.isdir(d):
        os.makedirs(d)
    json.dump({"meta": {
        "season": 2026,
        "note": "Six rows CONFIRMED by Claude-app are used as given and not "
                "re-derived. Text-matched rows are UNVERIFIED: matching page "
                "prose is weaker evidence than a rules citation.",
        "default_for_unknown": "TOURNAMENT (most mid-majors), flagged unverified",
        "counts": {"confirmed": conf_n, "unverified": unv, "not_found": miss},
    }, "conferences": rows}, open(OUT, "w"), indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
