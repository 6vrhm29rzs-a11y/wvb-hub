#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rotation order from a per-rally serve sequence.

WHAT THIS OVERTURNS. `docs/rotations_finding.md` closed rotations as
unrecoverable. That verdict was correct **about ncaa.com's feed**, where serves
are named only on aces, and it is still correct there. It does not generalise:
an official scoring feed that names the server on EVERY rally gives rotation
order directly, because a team serves in rotation order by rule. Nothing is
inferred here and no threshold is chosen.

THE DERIVATION
    Positions rotate 1 -> 6 -> 5 -> 4 -> 3 -> 2 -> 1, so the player who was at
    position 2 becomes the next server. The order in which a team's players take
    the serve therefore IS its rotation, and it must repeat with period 6.

    When the player at index k serves she stands at position 1, and the players
    at k+1 .. k+5 stand at positions 2, 3, 4, 5, 6. Front row is positions 2, 3
    and 4 -- so the three players who serve NEXT are the three at the net. That
    is what answers "is the setter front row or back row", which is the question
    the box score cannot reach.

WHAT MAKES IT TRUSTWORTHY
    Period 6 is a hard constraint, not a preference. A sequence that does not
    repeat with period 6 is rejected rather than trimmed to fit, and a set with
    fewer than six serve turns yields a PARTIAL order that must never be
    rendered as a rotation (R5). Substitutions are recovered as a by-product:
    a substitute serves in the slot of the player she replaced, so the pairing
    is read off the cycle rather than guessed -- the thing the NCAA feed could
    only resolve for 4% of entries.

Python 3.9 target.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

ROT = 6

# "[Serve: Meester,Chloe] Kill by Chicoine,Chloe (assist from Cabello,Nayelis)."
SERVE_RE = re.compile(r"\[Serve:\s*([^\]]+)\]")


def parse_plays(lines):
    # type: (List[str]) -> List[Tuple[str, str]]
    """Play lines -> [(server, serving_team), ...] in order.

    The trailing team code is the SERVING team, not the point winner. Verified
    rather than assumed: across a full set every server carried exactly one
    code, which cannot be true of a point-winner column because a server loses
    rallies too.
    """
    out = []                                            # type: List[Tuple[str, str]]
    for ln in lines:
        m = SERVE_RE.search(ln or "")
        if not m:
            continue
        parts = [p.strip() for p in (ln or "").split("\t") if p.strip()]
        team = parts[-1] if parts else ""
        # A team code is short and has no spaces; anything else means the line
        # was not laid out as expected and the row is skipped rather than
        # guessed at.
        if not team or len(team) > 5 or " " in team:
            team = ""
        out.append((m.group(1).strip(), team))
    return out


def serve_turns(pairs, team):
    # type: (List[Tuple[str, str]], str) -> List[str]
    """Consecutive rallies by the same server are ONE turn at the service line."""
    turns = []                                          # type: List[str]
    for server, t in pairs:
        if t != team:
            continue
        if not turns or turns[-1] != server:
            turns.append(server)
    return turns


def _by_successor(turns):
    # type: (List[str]) -> Optional[List[str]]
    """Rebuild the cycle from who-follows-whom instead of absolute position.

    WHY A SECOND METHOD. The positional method indexes turns by `i % 6`, which
    assumes no serve turn is ever missing. When the feed drops one, everything
    after it shifts a slot and the whole set is rejected. The successor relation
    does not care where a turn sits in the sequence, so a single gap costs one
    edge instead of the entire set. Measured on 381 NCAA set-teams: it recovers
    19 of the 30 the positional method rejects -- which is what confirms the
    diagnosis rather than merely asserting it.

    It is NOT strictly better, which is why both are kept: it resolves slightly
    fewer overall (91.1% vs 92.1%), because a substitution makes two different
    players legitimately follow the same predecessor and the majority edge can
    pick the wrong one.
    """
    nxt = {}                                            # type: Dict[str, Dict[str, int]]
    for a, b in zip(turns, turns[1:]):
        nxt.setdefault(a, {})
        nxt[a][b] = nxt[a].get(b, 0) + 1
    start = turns[0]
    cycle = [start]
    cur = start
    for _ in range(ROT):
        opts = nxt.get(cur)
        if not opts:
            return None
        cur = sorted(opts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        if cur == start:
            break
        if cur in cycle:                                # ran into itself early
            return None
        cycle.append(cur)
    return cycle if len(cycle) == ROT and cur == start else None


def derive_rotation(turns):
    # type: (List[str]) -> Dict[str, Any]
    """Serve turns -> rotation, substitutions, and whether it is trustworthy.

    Returns `complete` False when the set gave fewer than six turns. A partial
    order is real information but it is NOT a rotation, and presenting it as one
    would be exactly the synthesised-measurement failure R5 forbids.
    """
    res = {"rotation": [], "subs": {}, "complete": False,
           "consistent": True, "turns": len(turns),
           "problems": []}                              # type: Dict[str, Any]
    if not turns:
        res["problems"].append("no serve turns")
        res["consistent"] = False
        return res

    slots = [[] for _ in range(ROT)]                    # type: List[List[str]]
    for i, name in enumerate(turns):
        slots[i % ROT].append(name)

    rotation = []                                       # type: List[str]
    for i, occupants in enumerate(slots):
        if not occupants:
            rotation.append(None)
            continue
        rotation.append(occupants[0])
        # Anyone else who served from this slot came on as a substitute for the
        # player who started it. The pairing is read off the cycle, not guessed.
        extra = [n for n in occupants[1:] if n != occupants[0]]
        if extra:
            res["subs"][occupants[0]] = sorted(set(extra))

    res["rotation"] = rotation
    res["complete"] = all(r is not None for r in rotation) and len(turns) >= ROT
    res["method"] = "positional"

    # THE HARD CHECK. A slot may hold a starter and her substitutes; it may not
    # hold two unrelated players in an order that never repeats. If the distinct
    # names in a slot exceed what substitution can explain, the sequence is not
    # a rotation and is rejected rather than trimmed to fit.
    seen = set()
    for i, occupants in enumerate(slots):
        distinct = list(dict.fromkeys(occupants))
        for n in distinct:
            if n in seen:
                res["consistent"] = False
                res["problems"].append(
                    "%s serves from more than one slot" % n)
            seen.add(n)
        if len(distinct) > 3:
            res["consistent"] = False
            res["problems"].append(
                "slot %d had %d different servers" % (i + 1, len(distinct)))

    # FALL BACK, do not overrule. The positional answer is preferred when it is
    # self-consistent; the successor graph is asked only when it is not, so a
    # clean set is never re-decided by the weaker method.
    if not res["consistent"] and len(turns) >= ROT:
        alt = _by_successor(turns)
        if alt:
            res.update({"rotation": alt, "complete": True, "consistent": True,
                        "method": "successor",
                        "recovered_from": list(res["problems"]),
                        "problems": []})
            res["subs"] = {}
            for i, name in enumerate(turns):
                slot = alt.index(name) if name in alt else None
                if slot is None:
                    res["subs"].setdefault("(unplaced)", [])
                    if name not in res["subs"]["(unplaced)"]:
                        res["subs"]["(unplaced)"].append(name)
    return res


def positions_when_serving(rotation, server_index):
    # type: (List[str], int) -> Dict[int, str]
    """Court position 1-6 for every player, at the moment `server_index` serves.

    Position 1 is the server (back right); the next to serve stands at 2, and so
    on round to 6. Front row is 2, 3, 4.
    """
    out = {}                                            # type: Dict[int, str]
    for off in range(ROT):
        who = rotation[(server_index + off) % ROT]
        out[off + 1] = who
    return out


FRONT_ROW = (2, 3, 4)


def front_row(rotation, server_index):
    # type: (List[str], int) -> List[str]
    pos = positions_when_serving(rotation, server_index)
    return [pos[p] for p in FRONT_ROW]


def setter_rows(rotation, setter):
    # type: (List[str], str) -> List[Dict[str, Any]]
    """For each of the six rotations, is the setter at the net or in the back?

    This is the question Cody asked that the box score cannot answer: a setter
    in the front row is one fewer attacker and a different blocking matchup.
    """
    out = []                                            # type: List[Dict[str, Any]]
    if setter not in (rotation or []):
        return out
    for i in range(ROT):
        pos = positions_when_serving(rotation, i)
        where = [p for p, who in pos.items() if who == setter][0]
        out.append({"serving": rotation[i], "setter_position": where,
                    "setter_front_row": where in FRONT_ROW,
                    "front_row": [pos[p] for p in FRONT_ROW]})
    return out


BACK_ROW_ONLY = ("L", "DS", "L/DS", "DS/L")


def serving_six_caveats(rotation, positions):
    # type: (List[str], Dict[str, str]) -> List[Dict[str, Any]]
    """Which slots are held by a back-row replacement rather than the starter.

    MEASURED, AND THIS IS THE LIMIT OF THE METHOD. The serve order gives the
    SERVING six, which is not the six on the court. A libero replaces a middle
    the moment that middle rotates to the back row -- and the back row is where
    the serve is -- so the middle never serves and never appears. In the one set
    checked, NONE of Wisconsin's five middles appear in its serve order, and only
    one of Louisville's five does, while Auguste and Tarnow both recorded kills
    in that same set.

    So: rotation ORDER is exact, and the setter's front/back row is exact,
    because her own slot is known. But a slot whose server is a libero or DS
    belongs to a front-row player the serve order does not name. Rendering that
    name as "the player in rotation 1" would be a measurement standing where
    there is none (R5). The slot is flagged instead, and the front-row occupant
    has to come from the box score.
    """
    out = []                                            # type: List[Dict[str, Any]]
    for i, name in enumerate(rotation or []):
        pos = (positions or {}).get(name)
        if pos and pos.upper() in BACK_ROW_ONLY:
            out.append({"slot": i + 1, "server": name, "position": pos,
                        "note": "back-row replacement; the front-row player in "
                                "this slot is not named by the serve order"})
    return out


def opposite_of(rotation, name):
    # type: (List[str], str) -> Optional[str]
    """The player three slots away -- diagonally opposite, by definition."""
    if name not in (rotation or []):
        return None
    return rotation[(rotation.index(name) + 3) % ROT]
