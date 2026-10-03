#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find the matches a team played without someone it normally plays.

WHY. Cody, 2026-08-22: Louisville beat Texas A&M, but Kyndal Stowers tore up her
warmup with a back problem and did not play; A&M moved Fitch outside and tinkered
with lineups all night. The scoreline records none of that, and a rating that
treats the result as a clean read on A&M is wrong in a way nothing in the data
announces.

WHAT IS ACTUALLY MEASURABLE. Not injuries -- the feed says nothing about health.
What it does say is who was on the floor: a player with a line in nine straight
matches and no line in the tenth was absent, whatever the reason. That is the
signal, and it is honest to call it "absent", not "injured".

THE METHOD, and its one real trap. A player's expected availability has to be
judged from her OTHER matches, not from the season as a whole -- a player who
misses the second half of a season has a low season-wide rate, so a season-wide
threshold would quietly stop flagging her exactly when she starts missing time.
So: for each match, a player is EXPECTED if she appeared in enough of the team's
OTHER matches, and ABSENT if she then has no line in this one.

WEIGHT BY WHAT IS MISSING. Six players out of fifteen is not six equal losses.
Each absence carries the player's own points per set, so a team missing its best
attacker reads differently from one resting a reserve.

Python 3.9 target. Reads playerbox.jsonl. Writes data/availability_{SEASON}.json.
"""

import json
import os
import sys
import collections
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
PLAYERBOX = os.path.join(RAW, "playerbox.jsonl")
GAMES = os.path.join(RAW, "games.jsonl")
OUT = os.path.join(REPO, "data", "availability_%d.json" % SEASON)

MIN_TEAM_MATCHES = 4     # below this there is no "normally" to depart from
EXPECTED_SHARE = 0.60    # appeared in this share of the team's NEARBY matches
WINDOW = 4               # matches either side that define "normally"
# ONLY THE ROTATION COUNTS. A squad carries 14 players and a coach rests people;
# a reserve sitting out is not news, and flagging it buried the signal -- 43% of
# all team-matches came back flagged even after the window fix. What matters is
# the six who actually decide a team's strength, which is the same six the
# projection is built on and the same six measured to reproduce a team's real
# points per set. So an absence is reported only for a player in her team's top
# ROTATION by scoring rate.
ROTATION = 6
MIN_RATE_TO_REPORT = 0.5  # and she must actually score


def to_f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def points(r: Dict) -> float:
    return (to_f(r.get("kills")) + to_f(r.get("aces"))
            + to_f(r.get("bs")) + 0.5 * to_f(r.get("ba")))


_ACTION_FIELDS = ("kills", "errors", "atts", "aces", "digs", "bs", "ba",
                  "assists", "serve_atts", "serve_errors", "recv_atts",
                  "recv_errors", "bh_errors", "set_errors", "block_errors")


def _acted(r: Dict) -> bool:
    """Did the line record ANY action? Not 'did she play well'."""
    return any(to_f(r.get(k)) for k in _ACTION_FIELDS)


def _ident(nm: str) -> str:
    return "".join(ch for ch in nm.lower() if ch.isalnum())


_spell = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))


def _display(tid: str, key: str) -> str:
    c = _spell.get(tid, {}).get(key)
    return c.most_common(1)[0][0] if c else key


def load():
    """team -> {match_id -> {player_key -> line}}, and match metadata."""
    by_team = collections.defaultdict(lambda: collections.defaultdict(dict))
    if not os.path.exists(PLAYERBOX):
        return by_team, {}
    # ⚠ AUDIT D8: evidenced box-team swaps apply here too, or a swapped
    # match attributes every appearance to the wrong roster.
    import season_counts as _SC
    _swaps = _SC.box_team_swaps(SEASON)
    # held results are not accepted statistical evidence for "who normally
    # plays" (mail 055) -- the same shared eligibility as player ratings
    try:
        _held = set(str(x) for x in _SC.held_gids(SEASON))
    except Exception:
        _held = set()
    for line in open(PLAYERBOX):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        gid = str(rec.get("game_id"))
        if gid in _held:
            continue
        _sw = _swaps.get(gid) or {}
        for r in rec.get("rows") or []:
            tid = str(r.get("team_id") or "")
            tid = _sw.get(tid, tid)
            import nameclean as _nci
            r = _nci.apply_identity_override(dict(r, team_id=tid), gid)   # mail 052
            import nameclean as _nc
            nm = ("%s %s" % (_nc.repair(r.get("first") or ""),
                             _nc.repair(r.get("last") or ""))).strip()
            if not tid or not nm:
                continue
            # ⚠ ONE IDENTITY PER PLAYER, CASE- AND PUNCTUATION-INSENSITIVE
            # (mail 036). Keyed on the display string, "Claire Little
            # Chambers" and a case variant of it were two players, so each
            # read as ABSENT in the other's matches -- a false flag made of
            # spelling. The key folds case/punctuation; the display keeps the
            # most common spelling (see _display).
            key = _ident(nm)
            _spell[tid][key][nm] += 1
            by_team[tid][gid][key] = {
                "sets": to_f(r.get("gp")), "pts": points(r),
                "pos": r.get("pos") or "",
                # A ZERO-ACTION LISTING IS NEITHER AN APPEARANCE NOR AN
                # ABSENCE. The feed lists a DNP as gp=N with every count zero
                # (the Auguste finding), and gp itself can be copied/inflated.
                "acted": _acted(r),
            }

    meta = {}
    if os.path.exists(GAMES):
        for line in open(GAMES):
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if not isinstance(g, dict) or g.get("game_state") != "F":
                continue
            names = {str(t.get("team_id")): t.get("name_short")
                     for t in g.get("teams") or []}
            nsets = sum(1 for ls in g.get("linescores") or []
                        if to_f(ls.get("home")) or to_f(ls.get("visit")))
            meta[str(g.get("game_id"))] = {
                "teams": names,
                "epoch": g.get("start_time_epoch"),
                "nsets": nsets or None,
            }
    return by_team, meta


def build():
    by_team, meta = load()
    teams_out = {}
    flagged = []

    for tid, matches in by_team.items():
        # ⚠ A TRUNCATED BOX PROVES NOTHING ABOUT WHO PLAYED (mail 036). A
        # box whose deepest player line stops short of the match's sets is a
        # partial capture; a player missing from it is UNKNOWN, not absent.
        # Such matches are not judged and do not count toward expectation.
        def _complete(m):
            ns = meta.get(m, {}).get("nsets")
            if not ns:
                return True
            mx = max([ln["sets"] for ln in matches[m].values()] or [0])
            return mx >= ns
        skipped = [m for m in matches if not _complete(m)]
        mids = sorted((m for m in matches if m not in skipped),
                      key=lambda m: (meta.get(m, {}).get("epoch") or 0, m))
        if len(mids) < MIN_TEAM_MATCHES:
            continue

        # a player's season rate, used only to weight what an absence costs
        totals = collections.defaultdict(lambda: {"sets": 0.0, "pts": 0.0})
        for m in mids:
            for nm, line in matches[m].items():
                totals[nm]["sets"] += line["sets"]
                totals[nm]["pts"] += line["pts"]
        rate = {nm: (v["pts"] / v["sets"]) if v["sets"] else 0.0
                for nm, v in totals.items()}

        # APPEARED = a line with a recorded action. A zero-action listing is
        # held apart: it neither counts as playing nor as missing.
        appear = {nm: set(m for m in mids if nm in matches[m] and matches[m][nm]["acted"])
                  for nm in totals}
        core = set(sorted(rate, key=lambda n: -rate[n])[:ROTATION])

        for m in mids:
            others = [x for x in mids if x != m]
            if not others:
                continue
            # A LOCAL WINDOW, NOT THE WHOLE SEASON. Judging "normally plays"
            # across every other match flags the wrong thing: a player who
            # joins the lineup in October appears in ~two thirds of the season,
            # so she is scored as expected in September and flagged absent for
            # every match she had not yet arrived for. Measured with a
            # season-wide rule, 52% of all team-matches came back flagged, and
            # Saint Peter's produced the same three names over and over -- that
            # is a roster change being reported as an absence.
            #
            # So expectation is judged against the WINDOW matches either side of
            # this one. A player who was playing right before and right after
            # but not in between is genuinely missing; one who had not debuted
            # yet simply is not expected.
            i = mids.index(m)
            near = mids[max(0, i - WINDOW):i] + mids[i + 1:i + 1 + WINDOW]
            if len(near) < 2:
                continue
            absent = []
            for nm, seen in appear.items():
                if nm in matches[m]:   # acted, or zero-action (unknown)
                    continue
                share = len(seen & set(near)) / float(len(near))
                if share < EXPECTED_SHARE:
                    continue
                if nm not in core or rate.get(nm, 0.0) < MIN_RATE_TO_REPORT:
                    continue
                absent.append({"name": _display(tid, nm), "rate": round(rate[nm], 3),
                               "played_share": round(share, 3)})
            if absent:
                absent.sort(key=lambda a: -a["rate"])
                lost = round(sum(a["rate"] for a in absent), 3)
                row = {
                    "game_id": m,
                    "team_id": tid,
                    "team": (meta.get(m, {}).get("teams") or {}).get(tid),
                    "absent": absent,
                    "points_per_set_missing": lost,
                }
                flagged.append(row)
                teams_out.setdefault(tid, []).append(row)

    flagged.sort(key=lambda r: -r["points_per_set_missing"])
    return {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "measures": ("who did NOT take the floor, from the box score. NOT an "
                         "injury feed -- the reason for an absence is never in "
                         "the data and is not inferred here"),
            "expected_share": EXPECTED_SHARE,
            "window_matches_either_side": WINDOW,
            "min_team_matches": MIN_TEAM_MATCHES,
            "min_rate_to_report": MIN_RATE_TO_REPORT,
            "rotation": ROTATION,
            "teams_examined": len(by_team),
            "matches_flagged": len(flagged),
            "not_judged": ("matches whose box is truncated (deepest line short of "
                           "the match's sets) and zero-action listings are "
                           "UNKNOWN -- never counted as present or absent"),
        },
        "flagged": flagged,
    }


if __name__ == "__main__":
    out = build()
    json.dump(out, open(OUT, "w"), indent=1)
    m = out["meta"]
    print("wrote %s" % OUT)
    print("  teams examined : %d" % m["teams_examined"])
    print("  matches where a regular did not play: %d" % m["matches_flagged"])
    if out["flagged"]:
        print("\n  biggest absences (points/set not on the floor):")
        for r in out["flagged"][:12]:
            who = ", ".join("%s (%.2f)" % (a["name"], a["rate"]) for a in r["absent"][:3])
            print("     %-22s -%.2f/set   %s" % (r["team"] or r["team_id"],
                                                 r["points_per_set_missing"], who))
    else:
        print("  nothing flagged yet -- a team needs %d matches before there is a "
              "'normally' to depart from" % m["min_team_matches"])
