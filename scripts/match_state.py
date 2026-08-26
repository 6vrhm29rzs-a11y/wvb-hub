#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ONE state model for a match, and one place that decides it.

⚠ WHY THIS EXISTS. Three renderers were each deciding for themselves whether a
match was live, over, or had usable statistics -- the Match Desk band, the
Scores ledger, and the match detail. They agreed by luck. This project has
already been bitten twice by that shape: a finished match sat in "Coming up"
because one renderer only trusted the archive, and a 0-0 match showed the home
team winning because another tested `away > home` with two states in mind
instead of three.

THE SIX STATES, and nothing displays above its own state:

    upcoming              no score yet
    live_score_only       score and sets, no usable statistics
    live_with_team_stats  score, sets, AND team totals from the feed
    final_box_pending     the match is over; the official box score is not
                          served yet
    final_with_box        over, with official team totals (and player lines
                          when the feed carries them)
    unavailable           the source will not tell us (fetch failed / error)

⚠ THE EMPTY-STRING SCORE TRAP, measured 2026-08-25 and documented in
docs/live_endpoint_audit.md. The scoreboard serves `score: ''` before first
serve -- an EMPTY STRING, not null and not 0. `Number('')` is 0, so a careless
read renders an unplayed match as 0-0 and cannot tell it from a real 0-0 at
first serve. `_score()` below returns None for the empty string, and that is
the difference between `upcoming` and `live_score_only`.

⚠ AND A FINAL IS NEVER DOWNGRADED. A stale live payload arriving after a match
has gone final must not turn it back into a live match; `resolve()` takes the
strongest evidence, never the most recent.

Python 3.9 target. Import-only, no side effects.
"""

from typing import Any, Dict, Optional

UPCOMING = "upcoming"
LIVE_SCORE = "live_score_only"
LIVE_STATS = "live_with_team_stats"
FINAL_PENDING = "final_box_pending"
FINAL_BOX = "final_with_box"
UNAVAILABLE = "unavailable"

# What each state is allowed to put on screen. A renderer asks this rather than
# deciding for itself, so "may I draw a player table" has one answer.
CAPABILITIES = {
    UPCOMING:      {"score": False, "sets": False, "team_stats": False,
                    "player_lines": False},
    LIVE_SCORE:    {"score": True,  "sets": True,  "team_stats": False,
                    "player_lines": False},
    LIVE_STATS:    {"score": True,  "sets": True,  "team_stats": True,
                    "player_lines": False},
    FINAL_PENDING: {"score": True,  "sets": True,  "team_stats": False,
                    "player_lines": False},
    FINAL_BOX:     {"score": True,  "sets": True,  "team_stats": True,
                    "player_lines": True},
    UNAVAILABLE:   {"score": False, "sets": False, "team_stats": False,
                    "player_lines": False},
}

LABEL = {
    UPCOMING: "Upcoming",
    LIVE_SCORE: "Live",
    LIVE_STATS: "Live",
    FINAL_PENDING: "Final",
    FINAL_BOX: "Final",
    UNAVAILABLE: "Unavailable",
}

# What to say about the DATA at this state, in the reader's terms.
DETAIL_NOTE = {
    UPCOMING: "Not started.",
    LIVE_SCORE: "Live score only — the source is not serving statistics "
                "for this match yet.",
    LIVE_STATS: "Live score and team totals from the official feed.",
    FINAL_PENDING: "Final. The official box score has not been published yet.",
    FINAL_BOX: "Final, with the official box score.",
    UNAVAILABLE: "The source did not return this match.",
}


def _score(v):
    # type: (Any) -> Optional[int]
    """A set count, or None when the feed has not got one.

    ⚠ '' IS NOT ZERO. See the module docstring: the scoreboard uses an empty
    string before first serve, and int('' or 0) would quietly make it 0.
    """
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def is_over(feed):
    # type: (Optional[Dict]) -> bool
    """Over according to EITHER signal the feed uses.

    The scoreboard flips `currentPeriod` to FINAL before `gameState` leaves
    the live value, so for several minutes a match reports both. Trusting one
    field put a card headed LIVE above a line reading FINAL.
    """
    if not feed:
        return False
    for k in ("state", "gameState", "period", "currentPeriod"):
        v = str(feed.get(k) or "").lower()
        if "final" in v or "complete" in v:
            return True
    return False


def is_live(feed):
    # type: (Optional[Dict]) -> bool
    if not feed or is_over(feed):
        return False
    st = str(feed.get("state") or feed.get("gameState") or "").lower()
    return st in ("i", "live", "in progress", "inprogress")


def resolve(feed=None, stored=None, box=None, fetch_failed=False):
    # type: (Optional[Dict], Optional[Dict], Optional[Dict], bool) -> Dict[str, Any]
    """The single decision. Returns state, capabilities and a reason.

    `feed`   -- a scoreboard row, if we have one
    `stored` -- what the crawled archive holds for this match
    `box`    -- a validated box score, or None. None is the ORDINARY case.
    """
    has_box_team = bool(box and box.get("teams"))
    has_box_players = bool(box and box.get("players"))

    over = is_over(feed) or bool(stored and stored.get("final"))
    live = is_live(feed)

    if over:
        state = FINAL_BOX if has_box_team else FINAL_PENDING
        reason = ("official box score present" if has_box_team
                  else "over; no box score served yet")
    elif live:
        state = LIVE_STATS if has_box_team else LIVE_SCORE
        reason = ("feed is serving team totals mid-match" if has_box_team
                  else "in progress; no usable statistics served")
    else:
        a = _score((feed or {}).get("away_sets"))
        h = _score((feed or {}).get("home_sets"))
        if a is None and h is None and fetch_failed:
            state, reason = UNAVAILABLE, "the source did not return this match"
        elif a is None and h is None:
            state, reason = UPCOMING, "no score yet"
        else:
            # A score with no live/final flag: treat it as live score only.
            state, reason = LIVE_SCORE, "a score exists but no state was given"

    caps = dict(CAPABILITIES[state])
    # ⚠ CAPABILITY IS THE FLOOR, NOT A PROMISE. `final_with_box` allows player
    # lines, but if this particular box score carries none, the renderer must
    # still not draw a table. The state says what is PERMITTED; the payload
    # says what actually exists, and both must agree before anything renders.
    caps["player_lines"] = caps["player_lines"] and has_box_players
    caps["team_stats"] = caps["team_stats"] and has_box_team
    return {"state": state, "label": LABEL[state], "note": DETAIL_NOTE[state],
            "caps": caps, "reason": reason}


def js_table():
    """The same table, emitted for the page, so the two cannot drift.

    ⚠ THE RULES LIVE HERE, IN PYTHON, AND THE PAGE IS GIVEN THEM. Writing the
    state machine twice is how the three renderers disagreed in the first
    place. The page reads capabilities out of this object; it never decides
    what a state may show.
    """
    import json
    return json.dumps({"caps": CAPABILITIES, "label": LABEL,
                       "note": DETAIL_NOTE}, separators=(",", ":"))
