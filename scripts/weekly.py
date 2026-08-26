#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The weekly ranking calendar: cutoffs, completeness, and what may be frozen.

⚠ THE CUTOFF POLICY, STATED ONCE AND IMPLEMENTED ONCE.

A **Digby Weekly** covers every completed match dated **on or before the prior
Sunday, in EASTERN time**, and nothing after it.

  * EASTERN, not Pacific, and not UTC. The sport schedules in Eastern and the
    AVCA's own "Through Games" stamp is an Eastern date, so a weekly freeze
    that means to line up with the poll has to use the same ruler. The hub
    DISPLAYS Pacific for Cody, which is a separate decision about presentation
    and does not move the cutoff.
  * MONDAY IS EXCLUDED even when it has already finished. A Monday match
    belongs to the next week's freeze. This is what makes the archive
    comparable to a poll: both sides drew the line in the same place.
  * ⚠ A HAWAII MATCH THAT STARTS 7pm HST ON SUNDAY IS 1:00am EASTERN ON
    MONDAY, and is therefore excluded from that week. That is a real
    consequence of using one zone rather than a per-venue local date, and it
    is stated rather than papered over: we do not have venue-local zones, and
    inventing one per match would be a guess. The same is true of a 9pm PT
    Sunday match on the mainland.

**COMPLETENESS.** The freeze happens only when every match dated on or before
the cutoff is FINAL. If any is live, unresolved, or stale, nothing is written
and the calendar shows an honest waiting state naming what it is waiting for.
A partial weekly snapshot would be a poll published while games were still
being played.

⚠ **STALE IS ITS OWN STATE AND IT CAN BLOCK FOREVER.** ncaa.com deletes games
from a past date (measured 2026-08-22: twelve fixtures crawled for 2026-08-21,
two remain). Those records sit in the append-only log and can never resolve,
because the game is no longer enumerated and will never be refetched. Such a
match is reported as `stale`, it blocks the freeze, and clearing it is a
deliberate human act (`snapshot_rankings.py --force`), never an automatic
decision to ignore missing results.

Python 3.9 target. Import-only; no side effects.
"""

import datetime
import json
import os
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                        # pragma: no cover
    ET = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FINAL = "F"
LIVE_STATES = ("I",)
# How long after a match's scheduled start we stop calling it "not played yet"
# and start calling it stale. Generous: a five-set match plus delays.
STALE_AFTER_HOURS = 12


def et_date(epoch):
    # type: (Optional[int]) -> Optional[str]
    """The match's EASTERN calendar date -- the ruler the cutoff uses."""
    if not epoch:
        return None
    dt = datetime.datetime.fromtimestamp(int(epoch), ET) if ET else \
        datetime.datetime.utcfromtimestamp(int(epoch))
    return dt.strftime("%Y-%m-%d")


def prior_sunday(today):
    # type: (datetime.date) -> datetime.date
    """The most recent Sunday STRICTLY BEFORE `today`.

    On a Monday this is yesterday. On a Sunday it is eight days back, NOT
    today: a freeze taken on Sunday cannot claim to cover Sunday's own matches,
    most of which have not been played.
    """
    # weekday(): Mon=0 .. Sun=6
    back = today.weekday() + 1               # Mon -> 1, Tue -> 2, ... Sun -> 7
    return today - datetime.timedelta(days=back)


def week_label(cutoff):
    # type: (datetime.date) -> str
    """`Digby Weekly · Through Sunday, August 23` -- the visible promise."""
    return "Digby Weekly · Through Sunday, %s %d" % (
        cutoff.strftime("%B"), cutoff.day)


def iso_week(d):
    # type: (datetime.date) -> str
    iso = d.isocalendar()
    return "%d-W%02d" % (iso[0], iso[1])


def _load_games(path):
    # type: (str) -> List[Dict[str, Any]]
    """Deduped game log: final beats non-final, then last write wins."""
    best = {}                                            # type: Dict[str, Dict]
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                g = json.loads(line)
            except ValueError:
                continue
            gid = g.get("game_id")
            if not gid:
                continue
            prev = best.get(gid)
            is_f = g.get("game_state") == FINAL
            was_f = bool(prev) and prev.get("game_state") == FINAL
            if prev is None or is_f or not was_f:
                best[gid] = g
    return list(best.values())


def completeness(games, cutoff, now_epoch, season_start=None,
                 disposition=None):
    # type: (List[Dict], datetime.date, int, Optional[str], Optional[Dict]) -> Dict[str, Any]
    """Can a weekly freeze be written for this cutoff, and if not, why not?

    Only DIVISION-I matches count. A non-D-I fixture on the scoreboard is not
    part of the ranking and must not hold a poll open.

    ⚠ A WITHDRAWN FIXTURE STOPS BLOCKING; NOTHING ELSE DOES. `disposition` maps
    game_id -> the Fixture Truth Ledger's verdict. A fixture the SOURCE ITSELF
    no longer lists, evidenced by a saved observation of a date it has already
    published finals for, is counted as withdrawn rather than pending -- it is
    not going to resolve, because there is nothing left to resolve. Everything
    else (live, pending, unknown, no evidence) still blocks, because "we cannot
    prove what happened" is not the same as "nothing happened".

    Pass `disposition=None` and this behaves exactly as it did before: every
    non-final match blocks. The ledger can only ever REMOVE a blocker it has
    evidence for.
    """
    cut = cutoff.isoformat()
    disp = disposition or {}
    finals, blocking, withdrawn = [], [], []
    for g in games:
        d = et_date(g.get("start_time_epoch"))
        if not d or d > cut:
            continue                                     # after the cutoff
        if season_start and d < season_start:
            continue
        teams = g.get("teams") or []
        if not any((t.get("division") == 1) for t in teams):
            continue                                     # no D-I side involved
        state = g.get("game_state")
        if state == FINAL:
            finals.append(g.get("game_id"))
            continue
        gid = str(g.get("game_id"))
        row = {
            "game_id": g.get("game_id"), "date": d, "state": state,
            "teams": [t.get("name_short") for t in teams][:2],
        }
        if disp.get(gid) == "source_withdrawn":
            row["why"] = "withdrawn"
            withdrawn.append(row)
            continue
        ep = g.get("start_time_epoch") or 0
        age_h = (now_epoch - int(ep)) / 3600.0 if ep else 0.0
        if state in LIVE_STATES:
            row["why"] = "live"
        elif disp.get(gid) == "unknown":
            row["why"] = "unknown"
        elif age_h > STALE_AFTER_HOURS:
            row["why"] = "stale"
        else:
            row["why"] = "unresolved"
        blocking.append(row)
    blocking.sort(key=lambda b: (b["date"], str(b["game_id"])))
    withdrawn.sort(key=lambda b: (b["date"], str(b["game_id"])))
    # ⚠ THREE STATES, NOT TWO. A week whose only gap is documented withdrawals
    # is publishable, but it is NOT the same thing as a week where every
    # scheduled match was played -- so it does not get to say "complete" on
    # its own. The distinction is carried into the archive row.
    if blocking:
        state_ = "waiting"
    elif withdrawn:
        state_ = "complete_with_withdrawals"
    else:
        state_ = "complete"
    return {
        "cutoff": cut,
        "cutoff_tz": "America/New_York",
        "finals": len(finals),
        "blocking": blocking,
        "withdrawn": withdrawn,
        "state": state_,
        "publishable": not blocking,
    }


def disposition(season, root=None):
    # type: (int, Optional[str]) -> Dict[str, str]
    """game_id -> disposition, from the Fixture Truth Ledger if it exists.

    Missing ledger means an EMPTY map, which means every non-final match
    blocks. The gate is never loosened by the absence of evidence.
    """
    p = os.path.join(root or REPO, "data",
                     "fixture_disposition_%d.json" % season)
    if not os.path.exists(p):
        return {}
    try:
        doc = json.load(open(p))
    except ValueError:
        return {}
    return dict((str(f.get("game_id")), f.get("disposition"))
                for f in (doc.get("fixtures") or []))


def status(season, today=None, now_epoch=None):
    # type: (int, Optional[datetime.date], Optional[int]) -> Dict[str, Any]
    """The whole picture the calendar view renders."""
    today = today or datetime.date.today()
    now_epoch = now_epoch or int(datetime.datetime.now().timestamp())
    cutoff = prior_sunday(today)
    games = _load_games(os.path.join(REPO, "data", "raw", str(season),
                                     "games.jsonl"))
    c = completeness(games, cutoff, now_epoch, disposition=disposition(season))
    c["week"] = iso_week(cutoff)
    c["label"] = week_label(cutoff)
    c["captured_utc"] = None
    c["policy"] = _policy(season)
    return c


def _policy(season, root=None):
    """The disposition policy in force, stamped into each archive row."""
    p = os.path.join(root or REPO, "data",
                     "fixture_disposition_%d.json" % season)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p)).get("policy")
    except ValueError:
        return None
