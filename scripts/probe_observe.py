#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Classify one live-probe response, and record it immutably.

⚠ THIS IS THE MEASUREMENT THAT SETTLES A STANDING QUESTION. Nothing in this
project may claim live team or player statistics are available until a real
match has been observed. These six outcomes are the vocabulary that answer is
written in, and they are deliberately NOT collapsed:

    network_failure   we could not reach the source at all
    source_502        the source answered with an error page, not JSON
    no_data           valid JSON, but no usable box score yet
    live_score_only   in progress, score present, no usable statistics
    final_pending     over, box score not served yet
    final_with_box    over, official team totals present

⚠ TWO COLLAPSES THAT WOULD RUIN THE MEASUREMENT, BOTH FORBIDDEN HERE:
  * a BLANK SCORE IS NOT ZERO. The scoreboard serves '' before first serve and
    `Number('')` is 0, so a careless read records an unplayed match as 0-0.
  * FAILED JSON IS NOT AN EMPTY BOX SCORE. A 502 HTML page is the source
    refusing, which is a different fact from a match having no stats yet.

Python 3.9 target. Import-only; the runner is probe_live_boxscore.py.
"""

import datetime
import json
import os
from typing import Any, Dict, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS_PATH = os.path.join(REPO, "docs", "live_probe_observations.jsonl")

NETWORK_FAILURE = "network_failure"
SOURCE_502 = "source_502"
NO_DATA = "no_data"
LIVE_SCORE_ONLY = "live_score_only"
FINAL_PENDING = "final_pending"
FINAL_WITH_BOX = "final_with_box"

# Ranked by how much they SETTLE. A later observation may never claim less than
# an earlier one for the same match (see append_observation).
STRENGTH = {
    NETWORK_FAILURE: 0, SOURCE_502: 1, NO_DATA: 2,
    LIVE_SCORE_ONLY: 3, FINAL_PENDING: 4, FINAL_WITH_BOX: 5,
}

CHECKPOINTS = ("pre", "live", "final", "box")


def _num(v):
    """A set count, or None. ⚠ '' IS NOT 0 -- see the module docstring."""
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


def classify(http_status=None, body=None, transport_error=None,
             scoreboard=None):
    # type: (Optional[int], Optional[str], Optional[str], Optional[Dict]) -> Dict[str, Any]
    """One response -> one outcome, plus the shape facts worth keeping.

    `body` is the raw text of /game/{id}/boxscore. `scoreboard` is that match's
    row from the slate, if we have one.
    """
    out = {"outcome": None, "http": http_status, "why": "",
           "shape": {"json": False, "team_entries": 0, "player_rows": 0,
                     "status": None, "period": None},
           "score": {"away": None, "home": None, "state": None}}

    if scoreboard:
        out["score"]["away"] = _num(scoreboard.get("away_sets"))
        out["score"]["home"] = _num(scoreboard.get("home_sets"))
        out["score"]["state"] = (scoreboard.get("state")
                                 or scoreboard.get("gameState"))

    if transport_error:
        out["outcome"] = NETWORK_FAILURE
        out["why"] = "the source could not be reached: %s" % transport_error
        return out

    # ⚠ A 502 (OR ANY NON-JSON BODY) IS THE SOURCE REFUSING, not an empty box.
    # Measured 2026-08-25: before first serve this endpoint returns HTTP 502
    # with an HTML error page on every id tried.
    if http_status is not None and http_status >= 400:
        out["outcome"] = SOURCE_502
        out["why"] = "the source answered %s, not a box score" % http_status
        return out

    doc = None
    if body is not None:
        try:
            doc = json.loads(body)
        except ValueError:
            out["outcome"] = SOURCE_502
            out["why"] = "the source returned something that is not JSON"
            return out

    if not isinstance(doc, dict):
        out["outcome"] = NO_DATA
        out["why"] = "no box score document was returned"
        return out

    out["shape"]["json"] = True
    out["shape"]["status"] = doc.get("status")
    out["shape"]["period"] = doc.get("period")
    tb = doc.get("teamBoxscore")
    entries = len(tb) if isinstance(tb, list) else 0
    out["shape"]["team_entries"] = entries
    rows = 0
    if isinstance(tb, list):
        for t in tb:
            if isinstance(t, dict) and isinstance(t.get("playerStats"), list):
                rows += len(t["playerStats"])
    out["shape"]["player_rows"] = rows

    over = str(doc.get("status") or "").upper() in ("F", "FINAL") or \
        "final" in str(doc.get("period") or "").lower()
    live = str(out["score"]["state"] or "").lower() in ("i", "live",
                                                        "in progress")
    has_box = entries >= 2

    if over:
        out["outcome"] = FINAL_WITH_BOX if has_box else FINAL_PENDING
        out["why"] = ("official team totals present" if has_box
                      else "over; the box score is not served yet")
    elif live:
        out["outcome"] = LIVE_SCORE_ONLY if not has_box else FINAL_WITH_BOX
        if has_box:
            # A live match serving team totals is the finding this whole
            # exercise exists to test for. It is recorded as its own fact.
            out["outcome"] = "live_with_team_stats"
            out["why"] = "IN PROGRESS AND SERVING TEAM TOTALS -- notable"
        else:
            out["why"] = "in progress; no usable statistics served"
    else:
        out["outcome"] = NO_DATA
        out["why"] = "valid response, nothing usable in it yet"
    return out


def read_observations(path=None):
    p = path or OBS_PATH
    rows = []
    if not os.path.exists(p):
        return rows
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def append_observation(rec, path=None):
    """Append one observation. Never rewrites, never weakens.

    ⚠ A LATER RUN MAY NOT UNDO AN EARLIER FINDING. Once a match has been
    observed at `final_with_box`, a later probe of the same match cannot record
    a weaker outcome for the same checkpoint -- a flaky re-run at midnight must
    not erase the evidence collected at 4pm. The append is refused and says so.
    The file is append-only, so nothing is ever edited in place.
    """
    p = path or OBS_PATH
    rows = read_observations(p)
    gid, cp = str(rec.get("game_id")), rec.get("checkpoint")
    prior = [r for r in rows
             if str(r.get("game_id")) == gid and r.get("checkpoint") == cp]
    if prior:
        best = max(STRENGTH.get(r.get("outcome"), 0) for r in prior)
        if STRENGTH.get(rec.get("outcome"), 0) < best:
            return {"written": False,
                    "reason": ("a stronger observation already exists for this "
                               "match at this checkpoint; not overwritten")}
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return {"written": True, "reason": ""}


def observation(game_id, checkpoint, cls, note=""):
    """The minimal durable record. ⚠ NO RAW BODIES, NO CREDENTIALS."""
    return {
        "observed_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "game_id": str(game_id),
        "checkpoint": checkpoint,
        "outcome": cls.get("outcome"),
        "http": cls.get("http"),
        "shape": cls.get("shape"),
        "score": cls.get("score"),
        "why": cls.get("why"),
        "note": str(note or "")[:200],
    }
