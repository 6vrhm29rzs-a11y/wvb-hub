#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse starting lineups out of the play-by-play feed.

WHAT THIS FEED DOES AND DOES NOT CONTAIN -- all measured 2026-08-22 on a
206-game spread sample of 2025 (see docs/rotations_finding.md):

  * SET 1 carries a real starting six. 414 of 416 set-1 lines held exactly six
    names; 403 of 410 matched a box score on all six.
  * SETS 2+ DO NOT. Their `starters:` line is CUMULATIVE -- everyone who has
    appeared so far, 6 to 14 names. Reading it as a lineup is simply wrong.
    Only period 1 is used here.
  * THE ORDER IS JERSEY NUMBER, NOT ROTATION ORDER. Ascending jersey number
    explains 91.7% of orderings; the rotation-order signature (in a 5-1 the
    two MBs sit 3 apart, likewise the two OHs and S/OPP) is absent -- 16.7%
    observed against a 20% shuffled-chance baseline, while the same test scores
    100% on synthetic true-rotation lineups. So NO rotation 1-6 view can be
    built from this feed. Do not infer one from box-score totals (that is R5).
  * The separator is `;` in some games and `,` in others.
  * The feed's own teamId/label is USUALLY right (407 of 409) but not always,
    so attribution is by matching names to that game's box score. Same shape of
    trap as R8: an authoritative-looking key that is not one.
  * 2026 matches return the `starters:` scaffold with ZERO names filled.

Python 3.9 target.
"""

import collections
import json
import os
import re
import unicodedata
from typing import Dict, List, Optional

STARTERS_RE = re.compile(r"^(.*?)\s+starters:\s*(.+?)\.?\s*$", re.S)


def norm(s):
    # type: (str) -> str
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace(u"­", "")          # soft hyphen, seen in WMT-sourced text
    return re.sub(r"[^A-Za-z]", "", s).lower()


def surname(full):
    # type: (str) -> str
    toks = [t for t in re.split(r"\s+", (full or "").strip()) if t]
    return norm(toks[-1]) if toks else ""


def split_names(blob):
    # type: (str) -> List[str]
    """Separator varies by game: `;` in some feeds, `,` in others. Prefer `;`
    when present -- a comma split would shred three-token names like
    'Neal Grace Berry' only if it were the wrong separator, and `;` never is."""
    parts = blob.split(";") if ";" in blob else blob.split(",")
    return [p.strip() for p in parts if p.strip()]


def parse_starters(payload, period=1):
    # type: (Dict, Optional[int]) -> List[Dict]
    """Every `starters:` line in the given period (default: set 1 only)."""
    out = []
    for per in (payload or {}).get("periods", []) or []:
        pn = per.get("periodNumber")
        if period is not None and pn != period:
            continue
        for ev in per.get("playbyplayStats", []) or []:
            for pl in ev.get("plays", []) or []:
                text = (pl.get("playText") or "").strip()
                m = STARTERS_RE.match(text)
                if not m:
                    continue
                names = split_names(m.group(2))
                out.append({
                    "period": pn,
                    "label": m.group(1).strip(),
                    "feed_team_id": str(ev.get("teamId")),
                    "names": names,
                })
    return out


def box_index(playerbox_path):
    # type: (str) -> Dict
    """game_id -> team_id -> surname -> {'pos','num','name'} from the box score.
    This is the attribution authority: it is the only per-game record of which
    players belong to which team."""
    idx = collections.defaultdict(lambda: collections.defaultdict(dict))
    with open(playerbox_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            for r in rec.get("rows", []):
                full = ((r.get("first") or "") + " " + (r.get("last") or "")).strip()
                sn = norm((r.get("last") or "").strip())
                if not sn:
                    continue
                idx[rec["game_id"]][r["team_id"]][sn] = {
                    "pos": (r.get("pos") or "").upper(),
                    "num": r.get("num"),
                    "name": full,
                }
    return idx


def attribute(names, teams_box):
    # type: (List[str], Dict) -> Dict
    """Assign a six-name group to a team by NAME OVERLAP with the box score.

    Never by the feed's teamId or the team name in the play text -- both are
    wrong on a minority of lines, and a wrong attribution is the failure mode
    that looks completely correct downstream (R8)."""
    sns = set(surname(n) for n in names)
    best, best_n = None, -1
    for tid, players in teams_box.items():
        ov = len(sns & set(players.keys()))
        if ov > best_n:
            best, best_n = tid, ov
    return {"team_id": best, "matched": best_n, "of": len(sns)}


def lineups_for_game(game_id, payload, teams_box):
    # type: (str, Dict, Dict) -> List[Dict]
    """Distinct set-1 starting sixes for a game, attributed to real teams.

    Requires all six names to match the box score. A group that does not fully
    match is DROPPED, not guessed at -- a partially-matched lineup is exactly
    the kind of plausible-looking wrong answer this project keeps paying for."""
    groups = collections.OrderedDict()
    for line in parse_starters(payload, period=1):
        if len(line["names"]) != 6:
            continue
        key = frozenset(surname(n) for n in line["names"])
        groups.setdefault(key, []).append(line)

    out = []
    for key, lines in groups.items():
        att = attribute(lines[0]["names"], teams_box)
        if att["matched"] != 6:
            continue
        players = teams_box[att["team_id"]]
        six = []
        for n in lines[0]["names"]:
            sn = surname(n)
            info = players.get(sn, {})
            six.append({
                "name": info.get("name") or n,
                "surname": sn,
                "pos": info.get("pos") or "",
                "num": info.get("num"),
            })
        out.append({
            "game_id": game_id,
            "team_id": att["team_id"],
            "starters": six,
            # The feed's label was wrong on 2 of 409 sampled lines. Recording
            # the disagreement makes that rate measurable rather than assumed.
            "feed_label_agreed": lines[0]["feed_team_id"] == att["team_id"],
        })
    return out
