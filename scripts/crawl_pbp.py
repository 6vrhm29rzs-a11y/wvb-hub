#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crawl /game/{id}/play-by-play into an append-only jsonl.

Why this endpoint: it is the ONLY place the feed states who was on the court.
Box scores give season/match totals, never a six-player group, and inferring a
lineup from totals would be an R5 violation (a synthesised displayed value).

Two things about this feed that the parser downstream MUST know, both measured:

  1. EVERY event is emitted TWICE -- once under each team's teamId -- and the
     team NAME inside playText is rewritten to match whichever stream it sits
     in. So a Nebraska lineup appears verbatim under Pittsburgh's teamId with
     the text "Pittsburgh starters: ...". The feed's own team label is wrong on
     half of all lines. Attribute by matching NAMES to that game's box score,
     never by teamId or by the name in the text. (Same shape as R8: an
     authoritative-looking key that is not one.)

  2. 2025 archives are populated; 2026 matches return the `starters:` scaffold
     with zero names filled in. Re-check before assuming otherwise.

Resumable: ids already present in the output are skipped. Safe on a finished
season only -- these are archived, final games (R2's "skip what's on disk" is
correct here precisely because the season is over and every game is final).

Python 3.9 target.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lineups import box_index, lineups_for_game, parse_starters  # noqa: E402

API = "https://ncaa-api.henrygd.me"
UA = ("wvb-hub/0.1 (personal research project; "
      "contact via github.com/6vrhm29rzs-a11y/wvb-hub)")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(RAW, "pbp.jsonl")          # raw, only with --keep-raw
LINEUPS = os.path.join(RAW, "lineups.jsonl")  # the committed artifact
PLAYERBOX = os.path.join(RAW, "playerbox.jsonl")
GAMES = os.path.join(RAW, "games.jsonl")

SLEEP = 0.7


def done_ids(path):
    # type: (str) -> Set[str]
    have = set()
    if not os.path.exists(path):
        return have
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                have.add(json.loads(line)["game_id"])
            except (ValueError, KeyError):
                continue
    return have


def final_ids(path):
    # type: (str) -> List[str]
    """Final games only. A non-final record can never be trusted as complete,
    and on a past date ncaa.com may have deleted the game outright."""
    seen = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            gid = rec.get("game_id")
            if not gid:
                continue
            st = ((rec.get("payload") or {}).get("gameState")
                  or rec.get("game_state") or "")
            # append-only: final beats non-final, then last-wins
            if gid in seen and seen[gid] == "F" and st != "F":
                continue
            seen[gid] = st
    return sorted(g for g, s in seen.items() if s == "F")


def fetch(gid):
    # type: (str) -> Dict
    url = "%s/game/%s/play-by-play" % (API, gid)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract(gid, payload, boxidx):
    """Compact record. The raw payload is ~58 KB/game -- 296 MB for a season --
    so it is NOT retained by default: this repo is public and that is a lot of
    third-party JSON to carry for six names a game. Pass --keep-raw to keep it.
    Re-fetch is one command, documented in docs/rotations_finding.md."""
    teams_box = boxidx.get(gid) or {}
    rows = lineups_for_game(gid, payload, teams_box) if teams_box else []
    filled = 0
    for line in parse_starters(payload, period=None):
        if line["names"]:
            filled += 1
    return {
        "game_id": gid,
        "lineups": rows,
        # Coverage telemetry, so a season that quietly stops populating the
        # feed shows up as a number rather than as silence. 2026 currently
        # returns the starters scaffold with zero names filled.
        "starters_lines_with_names": filled,
    }


def main():
    argv = sys.argv[1:]
    limit = None
    stride = 1
    keep_raw = "--keep-raw" in argv
    for i, a in enumerate(argv):
        if a == "--limit":
            limit = int(argv[i + 1])
        elif a == "--stride":
            stride = int(argv[i + 1])

    boxidx = box_index(PLAYERBOX) if os.path.exists(PLAYERBOX) else {}

    ids = final_ids(GAMES)
    have = done_ids(LINEUPS)
    todo = [g for g in ids[::stride] if g not in have]
    if limit:
        todo = todo[:limit]

    print("season %d: %d final games, %d already extracted, %d to fetch"
          % (SEASON, len(ids), len(have), len(todo)))

    ok = failed = 0
    raw = open(OUT, "a") if keep_raw else None
    with open(LINEUPS, "a") as out:
        for n, gid in enumerate(todo, 1):
            try:
                payload = fetch(gid)
            except (urllib.error.URLError, urllib.error.HTTPError,
                    ValueError, OSError) as exc:
                failed += 1
                print("  FAIL %s %s" % (gid, exc))
                time.sleep(SLEEP)
                continue
            if raw is not None:
                raw.write(json.dumps({"game_id": gid, "payload": payload}) + "\n")
                raw.flush()
            out.write(json.dumps(extract(gid, payload, boxidx)) + "\n")
            out.flush()
            ok += 1
            if n % 250 == 0:
                print("  %d/%d ok=%d fail=%d" % (n, len(todo), ok, failed))
            time.sleep(SLEEP)
    if raw is not None:
        raw.close()

    print("done: ok=%d failed=%d -> %s" % (ok, failed, LINEUPS))


def seed_from_raw():
    """Backfill lineups.jsonl from an already-downloaded raw pbp.jsonl so the
    sample crawl is not repeated."""
    boxidx = box_index(PLAYERBOX)
    have = done_ids(LINEUPS)
    n = 0
    with open(LINEUPS, "a") as out:
        for line in open(OUT):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["game_id"] in have:
                continue
            out.write(json.dumps(extract(rec["game_id"], rec["payload"], boxidx)) + "\n")
            n += 1
    print("seeded %d games from %s" % (n, OUT))


if __name__ == "__main__":
    if "--seed-from-raw" in sys.argv:
        seed_from_raw()
    else:
        main()
