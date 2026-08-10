#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 crawler: 2025 D-I women's volleyball game log + team season stats.

Resumable by design. Every phase checkpoints to disk as it goes, so an
interruption leaves a partial that is *known* to be partial (progress files
record exactly what was fetched) rather than one that looks complete.

Phases:
  schedule  scoreboard by date -> data/raw/2025/scoreboard/{YYYY-MM-DD}.json
  games     /game/{id}         -> data/raw/2025/games.jsonl  (append-only)
  stats     team stat cats     -> data/raw/2025/stats/cat{ID}_p{N}.json

Python 3.9 target: no PEP 604 unions, no builtin generics in annotations.
"""

import json
import os
import sys
import time
import datetime
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Set

API = "https://ncaa-api.henrygd.me"

# *** `/current/` IS BANNED IN THIS CODEBASE. Always pin the season. ***
#
# `/current/` resolves to whatever season ncaa.com considers active, so the same
# URL silently returns different data after a season rolls over -- no error, no
# warning, just 2026 rows arriving where 2025 was expected. Verified 2026-08-10:
# the year segment IS honored (2023 -> Nebraska 33-2, 2024 -> Penn St. 35-2,
# 2025 -> Nebraska 33-1) and `/2025/` is byte-identical to what `/current/`
# returned that day.
#
# EXCEPTION, and it is a real gap: the RANKINGS endpoint accepts no season
# segment at all (every pinned variant 404s). The official RPI table is
# therefore CURRENT-ONLY and cannot be re-fetched for a past season. The 2025
# table captured in data/raw/2025/rpi_official.json is IRREPLACEABLE -- it is
# also the authority for Division-I membership. Do not delete it.
SEASON = 2025
UA = "wvb-hub/0.1 (personal research project; contact via github.com/6vrhm29rzs-a11y/wvb-hub)"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "data", "raw", "2025")
SCOREBOARD_DIR = os.path.join(RAW, "scoreboard")
STATS_DIR = os.path.join(RAW, "stats")
GAMES_JSONL = os.path.join(RAW, "games.jsonl")

# Season window. Deliberately wider than the real season on both ends so we
# cannot clip opening weekend or the championship; empty days cost one request.
SEASON_START = datetime.date(2025, 8, 15)
SEASON_END = datetime.date(2025, 12, 31)

# Team stat categories (measured, see CLAUDE.md). Raw counts only.
STAT_CATS = {
    45: "hitting_pct",       # Kills, Errors, Total Attacks, Pct
    46: "kills_per_set",
    47: "assists_per_set",
    48: "aces_per_set",
    49: "blocks_per_set",    # Block Solos + Block Assists SEPARATE
    50: "digs_per_set",
    51: "win_loss_pct",      # W, L, Pct
}
STAT_PAGES = 7  # 7 x 50 = 350 slots for 348 teams

MIN_INTERVAL = 0.7   # seconds between requests (~1.4 req/s; public demo caps at 5)
MAX_RETRIES = 4

_last_request = [0.0]


def _throttle():
    delta = time.time() - _last_request[0]
    if delta < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - delta)
    _last_request[0] = time.time()


def fetch(path):
    # type: (str) -> Optional[Any]
    """GET an API path. Returns parsed JSON, or None for a hard 404/422."""
    url = API + path
    for attempt in range(MAX_RETRIES):
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 422):
                return None
            wait = 2 ** attempt
            sys.stderr.write("  HTTP %d on %s, retry in %ds\n" % (exc.code, path, wait))
            time.sleep(wait)
        except Exception as exc:  # network flake, timeout, bad JSON
            wait = 2 ** attempt
            sys.stderr.write("  %s on %s, retry in %ds\n" % (type(exc).__name__, path, wait))
            time.sleep(wait)
    sys.stderr.write("  GIVING UP on %s after %d attempts\n" % (path, MAX_RETRIES))
    return None


def ensure_dirs():
    for d in (SCOREBOARD_DIR, STATS_DIR):
        if not os.path.isdir(d):
            os.makedirs(d)


# ---------------------------------------------------------------- phase: schedule

def crawl_schedule():
    # type: () -> None
    """One scoreboard request per date. Skips dates already on disk."""
    ensure_dirs()
    day = SEASON_START
    fetched = skipped = 0
    while day <= SEASON_END:
        out = os.path.join(SCOREBOARD_DIR, day.isoformat() + ".json")
        if os.path.exists(out):
            skipped += 1
            day += datetime.timedelta(days=1)
            continue
        path = "/scoreboard/volleyball-women/d1/%04d/%02d/%02d/all-conf" % (
            day.year, day.month, day.day)
        data = fetch(path)
        if data is None:
            data = {"games": [], "_wvb_fetch": "no-data"}
        # Write atomically so an interrupt cannot leave a half-written file that
        # a later resume would mistake for a completed date.
        tmp = out + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.rename(tmp, out)
        fetched += 1
        n = len(data.get("games", []))
        if n:
            print("  %s  %3d games" % (day.isoformat(), n))
        day += datetime.timedelta(days=1)
    print("schedule: %d dates fetched, %d already on disk" % (fetched, skipped))


def game_ids_from_schedule():
    # type: () -> List[str]
    """Unique gameIDs across every scoreboard file, in date order."""
    seen = set()  # type: Set[str]
    ids = []  # type: List[str]
    for name in sorted(os.listdir(SCOREBOARD_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(SCOREBOARD_DIR, name)) as fh:
            data = json.load(fh)
        for wrapper in data.get("games", []):
            game = wrapper.get("game", wrapper)
            gid = game.get("gameID") or game.get("id")
            if gid and gid not in seen:
                seen.add(gid)
                ids.append(gid)
    return ids


# ------------------------------------------------------------------- phase: games

def already_have():
    # type: () -> Set[str]
    """gameIDs already written to the JSONL. Tolerates a truncated last line."""
    have = set()  # type: Set[str]
    if not os.path.exists(GAMES_JSONL):
        return have
    with open(GAMES_JSONL) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                have.add(json.loads(line)["game_id"])
            except Exception:
                continue  # partial write from an interrupt; will be refetched
    return have


def normalize_game(gid, payload):
    # type: (str, Dict[str, Any]) -> Optional[Dict[str, Any]]
    """Flatten /game/{id} into one raw, source-tiered record. Raw values only."""
    contests = payload.get("contests") or []
    if not contests:
        return None
    c = contests[0]

    teams = []
    for t in c.get("teams", []):
        teams.append({
            "team_id": t.get("teamId"),
            "seoname": t.get("seoname"),
            "name_short": t.get("nameShort"),
            "name_full": t.get("nameFull"),
            "is_home": t.get("isHome"),
            "division": t.get("division"),          # RPI: D-I-only records
            "division_name": t.get("divisionName"),
            "sets_won": t.get("score"),             # match score in SETS
            "is_winner": t.get("isWinner"),
            "record_at_time": t.get("record"),
            "team_rank": t.get("teamRank"),
            "seed": t.get("seed"),
        })

    linescores = []
    for ls in c.get("linescores", []):
        linescores.append({
            "period": ls.get("period"),
            "home": ls.get("home"),
            "visit": ls.get("visit"),
        })

    return {
        "game_id": gid,
        "season_year": c.get("seasonYear"),
        "sport_code": c.get("sportCode"),
        "division": c.get("division"),
        "game_state": c.get("gameState"),
        "final_message": c.get("finalMessage"),
        "start_time_epoch": c.get("startTimeEpoch"),
        "winner_team_id": c.get("winner"),
        "championship": c.get("championship"),
        "teams": teams,
        "linescores": linescores,
        "has_boxscore": c.get("hasBoxscore"),
        "has_pbp": c.get("hasPbp"),
        "source_tier": "OFFICIAL",
        "source": "ncaa-api /game/%s" % gid,
    }


def crawl_games():
    # type: () -> None
    """Fetch /game/{id} for every enumerated id. Appends + flushes per record."""
    ids = game_ids_from_schedule()
    have = already_have()
    todo = [g for g in ids if g not in have]
    print("games: %d enumerated, %d already on disk, %d to fetch" % (
        len(ids), len(have), len(todo)))
    if not todo:
        return

    failures = []  # type: List[str]
    start = time.time()
    with open(GAMES_JSONL, "a") as out:
        for i, gid in enumerate(todo, 1):
            payload = fetch("/game/%s" % gid)
            rec = normalize_game(gid, payload) if payload else None
            if rec is None:
                failures.append(gid)
            else:
                out.write(json.dumps(rec) + "\n")
                out.flush()
                os.fsync(out.fileno())  # survive an interrupt, not just a crash
            if i % 100 == 0 or i == len(todo):
                rate = i / max(time.time() - start, 1e-6)
                left = (len(todo) - i) / max(rate, 1e-6)
                print("  %d/%d  %.1f req/s  ~%.0f min left  (%d failed)" % (
                    i, len(todo), rate, left / 60.0, len(failures)))

    if failures:
        fpath = os.path.join(RAW, "games_failed.json")
        with open(fpath, "w") as fh:
            json.dump(failures, fh, indent=1)
        print("games: %d FAILED, ids written to %s" % (len(failures), fpath))


# ------------------------------------------------------------------- phase: stats

def crawl_stats():
    # type: () -> None
    """7 categories x 7 pages of team season stats. Raw counts preserved."""
    ensure_dirs()
    for cat_id in sorted(STAT_CATS):
        for page in range(1, STAT_PAGES + 1):
            out = os.path.join(STATS_DIR, "cat%d_p%d.json" % (cat_id, page))
            if os.path.exists(out):
                continue
            suffix = "" if page == 1 else "/p%d" % page
            path = "/stats/volleyball-women/d1/%d/team/%d%s" % (SEASON, cat_id, suffix)
            data = fetch(path)
            if data is None:
                print("  cat %d p%d: no data" % (cat_id, page))
                continue
            rows = data.get("data", [])
            data["_wvb_category"] = STAT_CATS[cat_id]
            data["_wvb_category_id"] = cat_id
            data["_wvb_page"] = page
            data["_wvb_source_tier"] = "OFFICIAL"
            tmp = out + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(data, fh)
            os.rename(tmp, out)
            print("  cat %d (%s) p%d: %d rows" % (
                cat_id, STAT_CATS[cat_id], page, len(rows)))


def verify_season_pin():
    # type: () -> int
    """Regression test: refetch every stat page PINNED to SEASON and diff the
    rows against what is already on disk (originally pulled via `/current/`).

    This is free and it is the check that proves the pin is equivalent rather
    than merely syntactically valid -- the failure mode being guarded against is
    silent, so an assertion that never fires is worth having.
    """
    import hashlib

    def digest(rows):
        return hashlib.md5(json.dumps(rows, sort_keys=True).encode()).hexdigest()

    checked = same = diff = missing = 0
    for cat_id in sorted(STAT_CATS):
        for page in range(1, STAT_PAGES + 1):
            on_disk = os.path.join(STATS_DIR, "cat%d_p%d.json" % (cat_id, page))
            if not os.path.exists(on_disk):
                missing += 1
                continue
            suffix = "" if page == 1 else "/p%d" % page
            path = "/stats/volleyball-women/d1/%d/team/%d%s" % (SEASON, cat_id, suffix)
            fresh = fetch(path)
            checked += 1
            if fresh is None:
                diff += 1
                print("  cat %d p%d: PINNED FETCH FAILED" % (cat_id, page))
                continue
            want = json.load(open(on_disk)).get("data", [])
            got = fresh.get("data", [])
            if digest(want) == digest(got):
                same += 1
            else:
                diff += 1
                print("  cat %d p%d: DIFFERS  disk=%d rows  pinned=%d rows" % (
                    cat_id, page, len(want), len(got)))
    print("season pin regression: %d checked, %d identical, %d differing, %d missing"
          % (checked, same, diff, missing))
    if diff == 0 and checked:
        print("PASS -- /%d/ reproduces exactly what /current/ returned." % SEASON)
    return 1 if diff else 0


def main():
    phases = sys.argv[1:] or ["schedule", "games", "stats"]
    for phase in phases:
        print("=== %s ===" % phase)
        if phase == "schedule":
            crawl_schedule()
        elif phase == "games":
            crawl_games()
        elif phase == "stats":
            crawl_stats()
        elif phase == "verify-pin":
            rc = verify_season_pin()
            if rc:
                return rc
        else:
            sys.stderr.write("unknown phase: %s\n" % phase)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
