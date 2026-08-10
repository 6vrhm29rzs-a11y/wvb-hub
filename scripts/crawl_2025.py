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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamelog import final_game_ids, load_records_jsonl  # noqa: E402

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
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
UA = "wvb-hub/0.1 (personal research project; contact via github.com/6vrhm29rzs-a11y/wvb-hub)"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
SCOREBOARD_DIR = os.path.join(RAW, "scoreboard")
STATS_DIR = os.path.join(RAW, "stats")
GAMES_JSONL = os.path.join(RAW, "games.jsonl")

# Season window. Deliberately wider than the real season on both ends so we
# cannot clip opening weekend or the championship; empty days cost one request.
SEASON_START = datetime.date(SEASON, 8, 15)
SEASON_END = datetime.date(SEASON, 12, 31)

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


# ---------------------------------------------------------- freshness rules
#
# *** COMPLETENESS RULE. Do not "optimise" this away. ***
# A DATE is authoritative only when BOTH hold:
#     (1) the date is strictly in the past (not today), AND
#     (2) every game listed on it is final.
# A GAME is authoritative only when game_state == 'F'.
# Anything else stays refetchable.
#
# The bug this prevents: on a finished season, "skip any date already on disk"
# is correct and fast. On a LIVE season it silently destroys data -- a date
# fetched at 3pm caches that afternoon's partial slate as complete, and the
# evening matches are never fetched again. Silent, unrecoverable, and it
# corrupts the game graph that every reconciliation depends on.

def date_is_authoritative(payload, day, today):
    # type: (Optional[Dict[str, Any]], datetime.date, datetime.date) -> bool
    """True only if this stored date can never change again."""
    if payload is None:
        return False
    if day >= today:
        return False                      # today is still in progress
    games = payload.get("games") or []
    for wrapper in games:
        g = wrapper.get("game", wrapper)
        state = (g.get("gameState") or "").lower()
        final = g.get("finalMessage") or ""
        if state != "final" and "final" not in str(final).lower():
            return False                  # a game on this date is unresolved
    return True


def date_needs_refetch(path, day, today):
    # type: (str, datetime.date, datetime.date) -> bool
    if not os.path.exists(path):
        return True
    try:
        with open(path) as fh:
            payload = json.load(fh)
    except Exception:
        return True                       # truncated write
    return not date_is_authoritative(payload, day, today)


def ensure_dirs():
    for d in (SCOREBOARD_DIR, STATS_DIR):
        if not os.path.isdir(d):
            os.makedirs(d)


# ---------------------------------------------------------------- phase: schedule

def crawl_schedule():
    # type: () -> None
    """One scoreboard request per date. Skips dates already on disk."""
    ensure_dirs()
    today = datetime.date.today()
    day = SEASON_START
    fetched = skipped = 0
    while day <= SEASON_END:
        out = os.path.join(SCOREBOARD_DIR, day.isoformat() + ".json")
        if not date_needs_refetch(out, day, today):
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
    """gameIDs whose stored record is FINAL.

    Deliberately NOT "every id present". A game stored while in progress must be
    refetched until it finishes; treating it as done freezes a live match at
    whatever score it had when we first looked.
    """
    return final_game_ids(GAMES_JSONL)


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


BOX_JSONL = os.path.join(RAW, "boxscores.jsonl")


def crawl_boxscores():
    # type: () -> None
    """Per-match team attack lines from /game/{id}/boxscore.

    This is what makes OPPONENT hitting efficiency computable: both teams'
    attack lines arrive in one payload, so what a team allowed is directly
    observed rather than inferred from its opponents' season averages. Being
    per-match, it also permits a regular-season-only fit tested on the
    tournament, which the season-total leaderboards cannot support.

    SCOPE: `teamStats` is stored in full (raw counts, including the per-set
    attack breakdown). `playerStats` is DROPPED -- it is a different grain
    (~16 KB/game, ~82 MB across the season) that no team metric needs. Unlike
    the rankings table, /boxscore is ID-addressed rather than season-addressed,
    so it carries no season-rollover risk and can be re-crawled in full at any
    time if player-level data is ever wanted.
    """
    ids = game_ids_from_schedule()
    # A boxscore is only trustworthy once its game is final -- an in-progress
    # boxscore holds partial attack lines.
    finals = final_game_ids(GAMES_JSONL)
    have = set(k for k in load_records_jsonl(BOX_JSONL) if k in finals)
    todo = [g for g in ids if g not in have]
    print("boxscores: %d enumerated, %d on disk, %d to fetch" % (
        len(ids), len(have), len(todo)))
    if not todo:
        return

    failures = []
    start = time.time()
    with open(BOX_JSONL, "a") as out:
        for i, gid in enumerate(todo, 1):
            payload = fetch("/game/%s/boxscore" % gid)
            if not payload:
                failures.append(gid)
            else:
                teams = []
                for tb in payload.get("teamBoxscore") or []:
                    ts = tb.get("teamStats") or {}
                    ts.pop("__typename", None)
                    teams.append({"team_id": str(tb.get("teamId")), "team_stats": ts})
                meta = {}
                for t in payload.get("teams") or []:
                    meta[str(t.get("teamId"))] = {
                        "name_short": t.get("nameShort"),
                        "is_home": t.get("isHome"),
                    }
                for t in teams:
                    t.update(meta.get(t["team_id"], {}))
                out.write(json.dumps({
                    "game_id": gid,
                    "teams": teams,
                    "source_tier": "OFFICIAL",
                    "source": "ncaa-api /game/%s/boxscore" % gid,
                }) + "\n")
                out.flush()
                os.fsync(out.fileno())
            if i % 250 == 0 or i == len(todo):
                rate = i / max(time.time() - start, 1e-6)
                print("  %d/%d  %.1f req/s  ~%.0f min left  (%d failed)" % (
                    i, len(todo), rate, (len(todo) - i) / max(rate, 1e-6) / 60.0,
                    len(failures)))
    if failures:
        with open(os.path.join(RAW, "boxscores_failed.json"), "w") as fh:
            json.dump(failures, fh, indent=1)
        print("boxscores: %d FAILED" % len(failures))


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
        elif phase == "boxscores":
            crawl_boxscores()
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
