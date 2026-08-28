#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which matches do not count — one definition, for every consumer.

⚠ THIS EXISTS BECAUSE THE FIRST VERSION LIVED IN build_hub.py ALONE. The hub's
records, standings and per-set rates excluded tonight's exhibition correctly,
and `build_dataset.py` -- which produces the dataset the RATING, the RPI, the
simulator and the field projector all read -- had never heard of it. It filters
on `game_state == "F"` and nothing else, so the moment the match went final it
would have flowed into every rating in the project. Cody's instruction was
explicitly "keep the stats out of the ratings and rankings"; the display layer
was the half that did not matter most.

⚠ THE FEED CANNOT TELL US THIS. Checked game 6640217 during play: no `type`,
no `gameType` (that field exists on the boxscore endpoint and is None), no
exhibition flag, `division: 1`, both teams `(0-0)`. An exhibition is
indistinguishable from a counting match, so this is a hand-maintained ledger
with a source on every entry.

⚠ AND THE STATS ARE NOT MERELY UNOFFICIAL, THEY ARE ON A DIFFERENT SCALE.
Spikes Under the Lights plays its first two sets to 21 rather than 25
(huskers.com match notes, 2026-08-26). Every rate this project computes is per
SET, so a 21-point set deflates points/set, swings/set, the opponent adjustment
and the rally model. The format is also the proof it cannot be an NCAA result:
the playing rules put a set at 25.

Two ways to match, because ids alone have a deadline:
  * by game id, for matches already on the scoreboard
  * by venue + date, for one that is not -- the championship match had no id
    while the semi-finals were being played, and an id-only ledger would have
    missed it entirely.

Python 3.9 target.
"""

import io
import json
import os
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(season):
    # type: (int) -> Dict[str, Any]
    p = os.path.join(REPO, "data/raw/%d/exhibitions.json" % season)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except ValueError:
        return {}


def ledger(season):
    # type: (int) -> Dict[str, Dict]
    """game id -> entry."""
    doc = _load(season)
    return dict((str(k), v) for k, v in (doc.get("exhibitions") or {}).items())


def rules(season):
    # type: (int) -> List[Dict]
    """venue+date rules, for matches whose id does not exist yet."""
    return _load(season).get("rules") or []


def match_of(game, season, date=None):
    # type: (Dict, int, Optional[str]) -> Optional[Dict]
    """Return the ledger entry or rule this game matches, else None.

    `game` is a raw record from games.jsonl. `date` is the LOCAL date string if
    the caller has already computed one; otherwise only the id is checked,
    because deriving a date here would give two callers two answers to the same
    question (R4).
    """
    gid = str(game.get("game_id") or game.get("gid") or "")
    hit = ledger(season).get(gid)
    if hit:
        return hit
    if not date:
        return None
    loc = game.get("location") or {}
    venue = (loc.get("venue") or "").strip()
    if not venue:
        return None
    for r in rules(season):
        m = r.get("match_on") or {}
        if m.get("venue") == venue and m.get("date") == date:
            return r
    return None


def is_exhibition(game, season, date=None):
    # type: (Dict, int, Optional[str]) -> bool
    return match_of(game, season, date) is not None


def resolved_gids(season, games_path=None):
    # type: (int, Optional[str]) -> set
    """Every exhibition game id for a season: ledger entries AND rule matches.

    ⚠ A CONSUMER THAT ONLY HAS A GAME ID CANNOT APPLY A VENUE RULE. The player
    aggregate walks playerbox.jsonl, whose records carry a game_id and rows and
    nothing else -- no venue, no date -- so it cannot evaluate "every match at
    AT&T Stadium on this date". Resolving the rule ONCE here, against the game
    log, hands every such consumer a plain set of ids and keeps one definition
    of the question (R4).
    """
    out = set(ledger(season).keys())
    rs = rules(season)
    if not rs:
        return out
    path = games_path or os.path.join(
        REPO, "data/raw/%d/games.jsonl" % season)
    if not os.path.exists(path):
        return out
    import datetime
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")
    except Exception:
        tz = None
    for line in io.open(path, encoding="utf-8"):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if not isinstance(g, dict) or not g.get("game_id"):
            continue
        gid = str(g["game_id"])
        if gid in out:
            continue
        ep = g.get("start_time_epoch")
        if not ep:
            continue
        # ⚠ PACIFIC. The ledger is written in the timezone the hub displays; a
        # UTC date would push a 5pm Pacific match to the next day and the rule
        # would silently never fire.
        try:
            d = (datetime.datetime.fromtimestamp(int(ep), tz) if tz
                 else datetime.datetime.utcfromtimestamp(int(ep))
                 ).strftime("%Y-%m-%d")
        except Exception:
            continue
        if match_of(g, season, d):
            out.add(gid)
    return out
