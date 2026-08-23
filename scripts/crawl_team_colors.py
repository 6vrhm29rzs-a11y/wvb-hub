#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Team colours, read out of each school's own logo.

    python3 scripts/crawl_team_colors.py        # -> data/team_colors_2026.json

WHY THIS IS MEASURED RATHER THAN PICKED. Hand-typing 348 pairs of school
colours is 348 chances to be wrong about somebody's shade of red, and nobody
would ever check. The logos ncaa.com already serves are SVG, so the colours are
literally in the file -- this reads them instead of asserting them.

WHAT COUNTS AS A COLOUR. Near-black and near-white are thrown out: they are
outlines and paper, present in almost every logo, and taking the most frequent
fill without filtering hands you "black" for Wisconsin (#231f20 appears six
times) instead of its cardinal (#92191e, once). Greys go too. What survives is
ranked by saturation x frequency, so a large flat field of the school's colour
beats a single accent stroke.

A team whose logo yields nothing usable gets **no colour**, and the page falls
back to its own neutral -- never a guessed hue standing in for a real one.

Python 3.9 target. Standard library only.
"""

import collections
import colorsys
import json
import os
import re
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "team_colors_%d.json" % SEASON)
UA = "wvb-hub/0.1 (personal research project; one request per school logo)"
PAUSE = 0.25                                            # ~4 req/s, one pass only
TIMEOUT = 20

COLOR_RE = re.compile(
    r'(?:fill|stop-color)\s*[:=]\s*["\']?\s*(#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3}'
    r'|rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\))', re.I)


def _rgb(token):
    # type: (str) -> Optional[Tuple[int, int, int]]
    t = token.strip().lower()
    if t.startswith("#"):
        h = t[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return None
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return None
    m = re.findall(r"\d+", t)
    if len(m) >= 3:
        return tuple(min(255, int(x)) for x in m[:3])       # type: ignore
    return None


def _usable(rgb):
    # type: (Tuple[int, int, int]) -> bool
    """Drop paper, ink and grey -- outlines, not identity."""
    r, g, b = [c / 255.0 for c in rgb]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l > 0.93 or l < 0.10:                 # white-ish / black-ish
        return False
    if s < 0.18:                             # grey
        return False
    return True


def _rank(rgb, count):
    # type: (Tuple[int, int, int], int) -> float
    r, g, b = [c / 255.0 for c in rgb]
    _h, _l, s = colorsys.rgb_to_hls(r, g, b)
    return s * (count ** 0.5)


def _hex(rgb):
    # type: (Tuple[int, int, int]) -> str
    return "#%02x%02x%02x" % rgb


def readable_on(rgb):
    # type: (Tuple[int, int, int]) -> str
    """Black or white text on this colour, by relative luminance."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])
    return "#141210" if lum > 0.45 else "#FFFFFF"


def colors_from_svg(svg):
    # type: (str) -> Dict[str, Any]
    counts = collections.Counter()
    for tok in COLOR_RE.findall(svg or ""):
        rgb = _rgb(tok)
        if rgb and _usable(rgb):
            counts[rgb] += 1
    if not counts:
        return {}
    ranked = sorted(counts.items(), key=lambda kv: -_rank(kv[0], kv[1]))
    primary = ranked[0][0]
    accent = None
    for rgb, _n in ranked[1:]:
        # A second colour only if it is genuinely different, or it is just a
        # shade of the first and adds nothing.
        if sum(abs(a - b) for a, b in zip(rgb, primary)) > 90:
            accent = rgb
            break
    out = {"primary": _hex(primary), "on_primary": readable_on(primary),
           "n_colors": len(counts)}
    if accent:
        out["accent"] = _hex(accent)
        out["on_accent"] = readable_on(accent)
    return out


def fetch(url):
    # type: (str) -> Optional[str]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:                                    # noqa: BLE001
        return None


def logos_from_page():
    # type: () -> Dict[str, str]
    page = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(page):
        return {}
    html = open(page, encoding="utf-8").read()
    m = re.search(r"const LOGOS = (\{.*?\});\n", html, re.S)
    return json.loads(m.group(1)) if m else {}


def main():
    logos = logos_from_page()
    if not logos:
        print("no built page -- run scripts/build_hub.py first")
        return 1

    prev = {}
    if os.path.exists(OUT):
        try:
            prev = (json.load(open(OUT, encoding="utf-8")) or {}).get("teams") or {}
        except ValueError:
            prev = {}

    teams = dict(prev)
    got = skipped = failed = novector = 0
    for i, (name, url) in enumerate(sorted(logos.items())):
        if name in teams and teams[name].get("primary"):
            skipped += 1
            continue
        if not url or not url.lower().endswith(".svg"):
            novector += 1                                # raster: colours not readable
            continue
        svg = fetch(url)
        time.sleep(PAUSE)
        if not svg:
            failed += 1
            continue
        c = colors_from_svg(svg)
        if not c:
            failed += 1
            continue
        c["source"] = url
        teams[name] = c
        got += 1
        if got % 40 == 0:
            print("  %d fetched..." % got)

    doc = {"meta": {"season": SEASON, "source_tier": "DERIVED",
                    "source": "school logo SVGs served by ncaa.com",
                    "method": ("most saturated frequent fill, after dropping "
                               "near-black, near-white and grey -- those are "
                               "outlines, not identity"),
                    "no_colour_means": ("logo unreadable or raster; the page "
                                        "falls back to its own neutral rather "
                                        "than inventing a hue"),
                    "teams_with_colour": len(teams),
                    "raster_logos_skipped": novector,
                    "fetch_failures": failed},
           "teams": teams}
    json.dump(doc, open(OUT, "w"), indent=1, sort_keys=True)
    print("fetched %d, already had %d, failed %d, non-vector %d"
          % (got, skipped, failed, novector))
    print("teams with a colour: %d of %d" % (len(teams), len(logos)))
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
