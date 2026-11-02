#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read a top-level `const NAME = ...;` payload back out of a built page.

⚠ WHY THIS EXISTS AS ONE DEFINITION. The big payloads used to be emitted as
JavaScript object literals, and six places -- the public-build privacy gate,
digby, and four guards -- each carried their own
`re.search(r"const TEAMS = (\\{.*?\\});\\n", ...)`. Emitting them through
JSON.parse instead (measured 5-6x faster to parse: TEAMS 123ms -> 21ms,
PLAYERS 196ms -> 39ms, BOXES 165ms -> 30ms) would have broken all six at
once, and the privacy gate's failure mode was the dangerous one: it guards
`if m:`, so a regex that stops matching checks NOTHING and passes.

So both shapes are read here, by one function, and a caller that needs the
payload asks for it rather than writing the pattern again.

Python 3.9 target.
"""

import json
import re
from typing import Any, Dict, Optional


def _find_raw(html, name):
    # type: (str, str) -> Optional[Any]
    """The decoded value of `const NAME = ...;`, or None if it is not there.

    Handles both shapes:
        const NAME = {...};                  (object/array literal)
        const NAME = JSON.parse('...');      (JSON in a JS string)
    """
    if not html:
        return None
    m = re.search(r"const %s\s*=\s*JSON\.parse\('" % re.escape(name), html)
    if m:
        i = m.end()
        out = []
        while i < len(html):
            ch = html[i]
            if ch == "\\":
                nxt = html[i + 1]
                # `\'` and `\\` are JS-string escapes we added; every other
                # backslash escape belongs to the JSON underneath and must
                # survive verbatim (\n, \uXXXX, \" ...).
                if nxt in ("'", "\\"):
                    out.append(nxt)
                else:
                    out.append(ch)
                    out.append(nxt)
                i += 2
                continue
            if ch == "'":
                break
            out.append(ch)
            i += 1
        try:
            return json.loads("".join(out))
        except ValueError:
            return None
    m = re.search(r"const %s\s*=\s*([\{\[].*?)\;\n" % re.escape(name),
                  html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None


def find(html, name):
    # type: (str, str) -> Optional[Any]
    """The decoded value of `const NAME = ...;`, or None if it is not there.

    PLAYERS is returned EXPANDED: the page ships each game row that exactly
    copies a BOXES line as a pointer (build_hub.compact_player_games), and
    readers here must see the same full rows the page's hydratePlayers()
    produces.
    """
    v = _find_raw(html, name)
    if name == "PLAYERS" and isinstance(v, list):
        boxes = _find_raw(html, "BOXES") or {}
        hydrate_players(v, boxes)
    return v


def hydrate_players(players, boxes):
    """In place: pointer game rows -> full rows. Mirrors hydratePlayers()."""
    for p in players:
        gs = p.get("games")
        if not gs:
            continue
        out = []
        for g in gs:
            if not isinstance(g, list):
                out.append(g)
                continue
            lines = boxes.get(g[0]) or []
            ln = lines[g[1]] if g[1] < len(lines) else {}
            x = g[4] if len(g) > 4 else {}
            o = {"d": g[2], "gid": g[0], "opp": g[3], "nondi": bool(x.get("nondi"))}
            for k, val in ln.items():
                if k not in ("team", "name", "pos", "num"):
                    o[k] = val
            o["src_corrected"] = x.get("src_corrected")
            if "partial_box" in x:
                o["partial_box"] = x["partial_box"]
            out.append(o)
        p["games"] = out
    return players


def teams(html):
    # type: (str) -> Dict[str, Any]
    """TEAMS as a dict, or {} -- the shape every caller of it expects."""
    v = find(html, "TEAMS")
    return v if isinstance(v, dict) else {}
