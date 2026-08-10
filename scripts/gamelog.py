#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared game-log reader with correct freshness semantics.

WHY THIS EXISTS. games.jsonl is append-only, so a game refetched after it
finished appears TWICE: once as it was mid-match, once final. Every reader in
this repo used to dedupe first-wins, which would have made the stale in-progress
record permanently win over the correction. Refetching would have looked like it
worked and changed nothing.

THE RULE: a FINAL record always beats a non-final one; among equals, the LAST
written wins. Centralised here so the four readers cannot drift apart again.

COMPLETENESS RULE (see also CLAUDE.md): a stored record is authoritative only
when game_state == 'F'. Anything else is provisional and must be refetched.

Python 3.9 target.
"""

import json
import os
from typing import Any, Dict, List, Optional

FINAL = "F"


def is_final(rec):
    # type: (Optional[Dict[str, Any]]) -> bool
    return bool(rec) and rec.get("game_state") == FINAL


def load_games_jsonl(path):
    # type: (str) -> List[Dict[str, Any]]
    """All games, deduped: final beats non-final, then last-written wins."""
    best = {}  # type: Dict[str, Dict[str, Any]]
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                g = json.loads(line)
            except Exception:
                continue  # torn last line from an interrupt; refetched next run
            gid = g.get("game_id")
            if not gid:
                continue
            prev = best.get(gid)
            if prev is None:
                best[gid] = g
            elif is_final(g) or not is_final(prev):
                # g wins if it is final, or if neither is (later write)
                best[gid] = g
    return list(best.values())


def final_game_ids(path):
    # type: (str) -> set
    """Ids whose stored record is FINAL -- i.e. genuinely done, skip on resume."""
    return set(g["game_id"] for g in load_games_jsonl(path) if is_final(g))


def load_records_jsonl(path, key="game_id"):
    # type: (str, str) -> Dict[str, Dict[str, Any]]
    """Generic last-wins loader for the boxscore log (no finality concept)."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get(key):
                out[r[key]] = r
    return out
