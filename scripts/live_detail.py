#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live box-score detail for ONE open match. Local only, never persisted.

WHAT THIS IS FOR. The Match Desk shows a live score from the scoreboard poller.
This module answers the next question -- "what is actually happening in it" --
for the single match Cody has opened, and it is deliberately the most
distrustful code in the project.

⚠ THE CENTRAL UNKNOWN, STATED RATHER THAN ASSUMED. As of 2026-08-24 nobody has
observed what /game/{id}/boxscore returns DURING a live volleyball match. No
D-I match was in progress when this was written (next slate: 2026-08-28), and
men's and women's soccer on the same API were all final that night, so there
was nothing live anywhere to probe. Everything here is therefore written so
that "the feed gave us nothing usable" is the ORDINARY path and stats are the
conditional upgrade -- not the other way round. scripts/probe_live_boxscore.py
settles the question with evidence during the next active window.

THREE RULES THAT DO NOT BEND:
  1. Nothing here is ever written to data/raw, or read by any rating, resume,
     record, forecast or projection. It is display, in memory, for one screen.
  2. A number is rendered only if it survives validate(). A partial, all-zero
     or self-contradictory payload renders as an honest unavailable state --
     never a zero, never a placeholder, never an estimate (R5).
  3. Points per set come from RAW COUNTS (kills + aces + solo + half assist),
     never the feed's own `points` column, which is measured to be absent from
     some games and would undercount by a different amount per team.

Python 3.9 target.
"""

import threading
import time

# One team's worth of countable things. Everything displayed is derived from
# these; nothing is displayed that is not one of these or built from them.
COUNTS = ("kills", "attackErrors", "attackAttempts", "assists", "digs",
          "serviceAces", "serviceErrors", "blockSolos", "blockAssists")

CACHE_TTL = 20.0          # seconds a detail response stays fresh
CACHE_MAX = 4             # ⚠ a HARD CAP: a busy night must not become a crawl
STALE_MAX = 600.0         # after 10 min a last-good response is too old to show


def _int(v):
    """An int, or None. A blank, a dash or a stray string is NOT a zero."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if float(v).is_integer() else None
    if isinstance(v, str):
        t = v.strip()
        if not t or t in ("-", "--", "N/A", "NA"):
            return None
        try:
            return int(t)
        except ValueError:
            try:
                f = float(t)
            except ValueError:
                return None
            return int(f) if f.is_integer() else None
    return None


def team_line(stats):
    """Countable fields for one team, or (None, reason) if they do not parse."""
    if not isinstance(stats, dict):
        return None, "team statistics missing"
    out = {}
    for k in COUNTS:
        n = _int(stats.get(k))
        if n is None:
            return None, "%s did not parse" % k
        if n < 0:
            return None, "%s is negative" % k
        out[k] = n
    if out["kills"] > out["attackAttempts"]:
        return None, "more kills than attack attempts"
    if out["attackErrors"] > out["attackAttempts"]:
        return None, "more attack errors than attempts"
    if out["serviceAces"] > 400 or out["kills"] > 400:
        return None, "counts are implausibly large"
    ta = out["attackAttempts"]
    out["hitpct"] = round((out["kills"] - out["attackErrors"]) / float(ta), 3) \
        if ta else None
    # ⚠ RAW COUNTS, NEVER THE FEED'S `points` COLUMN. Blocks are solo + half
    # assist, the NCAA convention.
    out["points"] = (out["kills"] + out["serviceAces"] + out["blockSolos"]
                     + 0.5 * out["blockAssists"])
    out["blocks"] = out["blockSolos"] + 0.5 * out["blockAssists"]
    return out, ""


def sets_played(payload):
    """How many sets the box score claims, from the most reliable field there."""
    for t in (payload.get("teamBoxscore") or []):
        n = _int(((t.get("teamStats") or {}).get("sets")))
        if n:
            return n
        n = _int(((t.get("teamStats") or {}).get("gamesPlayed")))
        if n:
            return n
    return None


def validate(payload, expect_sets=None):
    """(teams, leaders, reason). teams is None whenever anything is off.

    Returning None is the SAFE and expected outcome. The caller renders the
    live score and says box-score detail is not available -- which is a true
    statement about the feed, not a failure of ours.
    """
    if not isinstance(payload, dict):
        return None, [], "no box score returned"
    tb = payload.get("teamBoxscore")
    if not isinstance(tb, list) or len(tb) != 2:
        return None, [], "the feed did not return both teams"

    names = {}
    for t in (payload.get("teams") or []):
        if isinstance(t, dict) and t.get("teamId") is not None:
            names[str(t["teamId"])] = (t.get("nameShort") or t.get("teamName")
                                       or t.get("nameFull") or "")

    teams = []
    for t in tb:
        if not isinstance(t, dict):
            return None, [], "a team entry was malformed"
        line, why = team_line(t.get("teamStats"))
        if line is None:
            return None, [], why
        line["team_id"] = str(t.get("teamId") or "")
        line["team"] = names.get(line["team_id"], "")
        teams.append(line)

    # ⚠ ALL-ZERO IS NOT A SCORELINE, IT IS AN EMPTY TEMPLATE. A match that is
    # genuinely live has had rallies; a box of zeros means the scorer has not
    # started filling it in, and showing it would be showing an invention.
    if sum(t["kills"] + t["attackAttempts"] + t["digs"] for t in teams) == 0:
        return None, [], "the official box score is still empty"

    n = sets_played(payload)
    if n is not None and not (1 <= n <= 5):
        return None, [], "the set count is not plausible (%s)" % n
    if expect_sets is not None and n is not None and n < expect_sets:
        # The scoreboard says more sets have been played than the box knows
        # about: the box is behind, so it describes a different match state.
        return None, [], "the box score is behind the scoreboard"

    leaders = player_leaders(tb, names)
    return teams, leaders, ""


def player_leaders(tb, names, top=3):
    """Top scorers by RAW production. [] if the rows are not usable."""
    out = []
    for t in tb or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("teamId") or "")
        for p in (t.get("playerStats") or []):
            if not isinstance(p, dict):
                continue
            k, a = _int(p.get("kills")), _int(p.get("serviceAces"))
            bs, ba = _int(p.get("blockSolos")), _int(p.get("blockAssists"))
            if None in (k, a, bs, ba):
                continue
            name = (" ".join(x for x in ((p.get("firstName") or "").strip(),
                                         (p.get("lastName") or "").strip()) if x)
                    ).strip()
            if not name:
                continue
            pts = k + a + bs + 0.5 * ba
            if pts <= 0:
                continue
            # sets/assists/blocks travel too (round 15: the Live Pulse
            # names each leader's metric AND current sets sample; a leader
            # whose sets the feed does not carry renders without one, never
            # with an invented zero -- None is preserved as None)
            out.append({"name": name, "team_id": tid,
                        "team": names.get(tid, ""), "kills": k,
                        "digs": _int(p.get("digs")) or 0,
                        "aces": a, "points": pts,
                        # ⚠ MEASURED FIELD NAME: this feed's per-player sets column is
                        # gamesPlayed (checked live on 6627234); setsPlayed
                        # exists in a different payload variant and reads None here
                        "sets": _int(p.get("gamesPlayed")),
                        "assists": _int(p.get("assists")),
                        "blocks": (bs + 0.5 * ba)})
    out.sort(key=lambda r: (-r["points"], r["name"]))
    return out[:top]


class DetailCache(object):
    """One-match-at-a-time detail, with a hard cap and a last-good memory.

    ⚠ SCOPE IS THE WHOLE POINT. This never iterates the night's slate. It holds
    at most CACHE_MAX entries and only ever fetches the id it is asked for, so
    opening one match costs one upstream request per CACHE_TTL and a busy
    Friday costs exactly the same as a quiet Monday.
    """

    def __init__(self, fetch, ttl=CACHE_TTL, cap=CACHE_MAX, clock=time.time):
        self._fetch = fetch
        self._ttl = ttl
        self._cap = cap
        self._clock = clock
        self._lock = threading.Lock()
        self._entries = {}                    # id -> {payload, at, error}
        self.fetches = 0                      # observable, for the tests

    def _evict(self):
        while len(self._entries) > self._cap:
            oldest = min(self._entries, key=lambda k: self._entries[k]["at"])
            del self._entries[oldest]

    def get(self, gid):
        """(payload, age_seconds, stale, error). Never raises."""
        gid = str(gid)
        now = self._clock()
        with self._lock:
            e = self._entries.get(gid)
            if e and (now - e["at"]) < self._ttl:
                return e["payload"], now - e["at"], False, e.get("error")
        try:
            self.fetches += 1
            fresh = self._fetch(gid)
        except Exception as exc:                          # noqa: BLE001
            fresh, err = None, "upstream error: %s" % str(exc)[:120]
        else:
            err = None if fresh is not None else "upstream returned nothing"
        with self._lock:
            if fresh is not None:
                self._entries[gid] = {"payload": fresh, "at": now, "error": None}
                self._evict()
                return fresh, 0.0, False, None
            # ⚠ FAIL SOFT: keep the last coherent response rather than blanking
            # the inset. A momentary upstream hiccup should not read as "the
            # match stopped existing" -- but it must SAY it is stale, and it
            # must give up entirely once it is too old to mean anything.
            e = self._entries.get(gid)
            if e:
                age = now - e["at"]
                if age <= STALE_MAX:
                    e["error"] = err
                    return e["payload"], age, True, err
                del self._entries[gid]
            return None, 0.0, False, err
