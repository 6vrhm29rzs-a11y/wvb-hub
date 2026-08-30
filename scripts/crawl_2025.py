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

import collections
import json
import os
import re
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

# Seconds between requests. Overridable because the public API's tolerance is not
# a constant: a 2024 backfill ran ~1.4 req/s for 10k requests and then began
# hanging every second request -- one would return 200 in under a second and the
# next would stall past a 30s timeout. That is throttling, not an outage, and the
# only fix from our side is to ask for less. WVB_REQ_INTERVAL lets a bulk
# backfill crawl politely without slowing the daily run.
MIN_INTERVAL = float(os.environ.get("WVB_REQ_INTERVAL", "0.7"))
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

def eastern_today():
    # type: () -> datetime.date
    """Today's date on the NCAA's calendar, which is EASTERN.

    ⚠ NOT the local date. The scoreboard is keyed by the Eastern calendar day,
    and this machine is Pacific: between 9pm and midnight PT it is already
    tomorrow in New York, so a Pacific "today" would look at the wrong date
    exactly while the late West-coast matches are finishing -- the window this
    whole feature exists to cover.
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:                                     # noqa: BLE001
        # UTC is within an hour of Eastern's date boundary either way; a
        # neighbouring date is covered by the window below regardless.
        return datetime.datetime.utcnow().date()


def crawl_recent(back_days=2):
    # type: (int) -> None
    """Refetch only the dates that could contain a NEW final.

    ⚠ THIS IS NARROWER THAN crawl_schedule(), NEVER WEAKER, AND THE DISTINCTION
    IS THE WHOLE SAFETY ARGUMENT. R2 says a date stays refetchable until it is
    strictly in the past AND all its games are final; that rule is UNCHANGED and
    the daily run still applies it across the entire season. This phase exists
    for a poll that runs every half hour, whose only question is "did something
    finish just now" -- and a match can only finish on today's or a recent
    Eastern date.
    
    Measured, which is why the narrowing matters: a full schedule pass is 132
    requests (~1.6 min) and 130 of them are FUTURE dates that cannot contain a
    final. This pass is a handful of requests and a few seconds.
    
    Nothing is skipped permanently: the crawl is append-only, the daily full
    pass re-checks every date under the original rule, and this phase still
    honours date_needs_refetch -- it only narrows WHICH dates it offers.
    """
    ensure_dirs()
    today = datetime.date.today()
    east = eastern_today()
    # Eastern today, the days behind it, and tomorrow -- tomorrow because a
    # match late on the Eastern evening can already belong to the next date in
    # UTC terms, and one extra request is cheaper than a missed final.
    days = [east + datetime.timedelta(days=1)]
    days += [east - datetime.timedelta(days=i) for i in range(0, back_days + 1)]
    days = [d for d in sorted(set(days)) if SEASON_START <= d <= SEASON_END]
    fetched = skipped = 0
    for day in days:
        out = os.path.join(SCOREBOARD_DIR, day.isoformat() + ".json")
        if not date_needs_refetch(out, day, today):
            skipped += 1
            continue
        path = "/scoreboard/volleyball-women/d1/%04d/%02d/%02d/all-conf" % (
            day.year, day.month, day.day)
        data = fetch(path)
        if data is None:
            data = {"games": [], "_wvb_fetch": "no-data"}
        tmp = out + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, out)
        fetched += 1
        # no sleep here: fetch() already enforces MIN_INTERVAL between requests,
        # and a second delay would be a rate limit nobody declared.
    print("recent: %d date(s) considered, %d fetched, %d already authoritative"
          % (len(days), fetched, skipped))


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


def game_ids_from_schedule(include_future=False):
    # type: (bool) -> List[str]
    """Unique gameIDs across every scoreboard file, in date order.

    *** FUTURE FIXTURES ARE EXCLUDED BY DEFAULT, and that is load-bearing. ***
    ncaa.com publishes the whole season's schedule in advance -- the 2026 slate
    is already listed today with gameState 'pre'. A scheduled game is by
    definition not final, so the "refetch anything non-final" rule would refetch
    every unplayed fixture in the season on every run: ~10,000 requests and
    ~2 hours nightly, achieving nothing, until those matches are actually
    played. A game cannot have a result before it is played, so anything dated
    after today is skipped.
    """
    today = datetime.date.today()
    seen = set()  # type: Set[str]
    ids = []  # type: List[str]
    for name in sorted(os.listdir(SCOREBOARD_DIR)):
        if not name.endswith(".json"):
            continue
        try:
            day = datetime.date(*[int(x) for x in name[:-5].split("-")])
        except Exception:
            continue
        if not include_future and day > today:
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


def crawl_fixtures(refresh_days=14):
    # type: (int) -> None
    """Fetch /game/{id} for UNPLAYED fixtures, to learn WHERE they are played.

    WHY THIS IS NOT crawl_games(). That one deliberately skips the future,
    because a scheduled match has no result and the "refetch anything non-final"
    rule would re-request the whole season every night for nothing. That
    reasoning is about RESULTS -- and it is still right. But a fixture's VENUE is
    published well in advance: /game/{id} on an unplayed match returns
    gameState "P" and a full location block (measured: Michigan St. at Morehead
    St., 2026-09-12, "Johnson Arena, Morehead, KY"). The scoreboard feed that
    enumerates fixtures carries NO location at all, so this is the only route to
    "where is this match" for a schedule that is mostly unplayed.

    Bounded two ways so it cannot become the nightly 10,000-request crawl the
    comment above warns about:
      * a fixture we have NO record for is fetched once;
      * a fixture inside the next `refresh_days` is re-fetched, because that is
        exactly when a placeholder start time is replaced by a real one and a
        tournament's site firms up.
    Everything further out is left alone until it comes into that window.
    """
    ids = game_ids_from_schedule(include_future=True)
    past = set(game_ids_from_schedule(include_future=False))
    have = set()
    dates = {}                                          # type: Dict[str, str]
    if os.path.exists(GAMES_JSONL):
        # every id PRESENT, final or not -- unlike already_have(), because a
        # fixture we have merely recorded already told us its venue.
        have = set(str(k) for k in load_records_jsonl(GAMES_JSONL))
    # date per fixture, from the scoreboard filenames we already hold
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=refresh_days)
    soon = set()
    for name in sorted(os.listdir(SCOREBOARD_DIR)):
        if not name.endswith(".json"):
            continue
        try:
            day = datetime.date(*[int(x) for x in name[:-5].split("-")])
        except Exception:
            continue
        if not (today <= day <= horizon):
            continue
        with open(os.path.join(SCOREBOARD_DIR, name)) as fh:
            data = json.load(fh)
        for wrapper in data.get("games", []):
            game = wrapper.get("game", wrapper)
            gid = game.get("gameID") or game.get("id")
            if gid:
                soon.add(str(gid))

    todo = [g for g in ids if g not in past and (g not in have or g in soon)]
    print("fixtures: %d scheduled, %d already recorded, %d within %d days, "
          "%d to fetch" % (len(ids), len(have), len(soon), refresh_days, len(todo)))
    if not todo:
        return

    failures = []                                       # type: List[str]
    start = time.time()
    with open(GAMES_JSONL, "a") as out:
        for i, gid in enumerate(todo, 1):
            try:
                payload = fetch("/game/%s" % gid)
                rec = normalize_game(gid, payload)
                if rec:
                    out.write(json.dumps(rec) + "\n")
                    out.flush()
            except Exception as exc:                    # noqa: BLE001
                failures.append("%s: %s" % (gid, exc))
            if i % 25 == 0 or i == len(todo):
                rate = i / max(time.time() - start, 1e-6)
                print("  %d/%d  %.1f req/s  ~%d min left  (%d failed)"
                      % (i, len(todo), rate,
                         int((len(todo) - i) / max(rate, 1e-6) / 60), len(failures)))
    if failures:
        print("  %d failures; first: %s" % (len(failures), failures[0]))


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
            # brand colour, straight from the feed. Free, and the only source
            # we have for it -- the scoreboard endpoint does not carry it.
            "color": t.get("color"),
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
        # WHERE THE MATCH WAS ACTUALLY PLAYED. /game/{id} carries this and we
        # were throwing it away, so the dashboard inferred the venue from who
        # was listed at home -- and got it wrong the first time it mattered.
        # Kentucky-Wisconsin and Louisville-Texas A&M were both AVCA First Serve
        # matches at Fiserv Forum in Milwaukee: NEUTRAL SITE, no home team on
        # the floor. Rendering "at Wisconsin" was an inference presented as a
        # fact. It also matters to the rating, which fits a home-advantage term
        # and would credit a home edge nobody had.
        "location": {
            "venue": (c.get("location") or {}).get("venue"),
            "city": (c.get("location") or {}).get("city"),
            "state": (c.get("location") or {}).get("stateUsps"),
        } if c.get("location") else None,
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
    # ONLY FINAL GAMES. The line above already computed `finals` and the
    # docstring already says a boxscore is untrustworthy until the game is --
    # but the todo list ignored both and asked for every enumerated game,
    # including ones that had not been played. Measured on 2026-08-22:
    # "34 enumerated, 34 to fetch, 31 FAILED", where the 31 were simply
    # tomorrow's fixtures. Harmless to the data (they retry once final) and
    # corrosive to the signal: a real boxscore failure was indistinguishable
    # from a game that had not happened yet, in a list of 31.
    todo = [g for g in ids if g in finals and g not in have]
    print("boxscores: %d enumerated, %d on disk, %d to fetch" % (
        len(ids), len(have), len(todo)))
    failed_path = os.path.join(RAW, "boxscores_failed.json")
    if not todo:
        # Rewrite the failure list even when there is nothing to do, or it keeps
        # asserting yesterday's failures forever. It was still claiming 31 after
        # every one of them had been fetched or turned out to be an unplayed
        # fixture -- a stale alarm is worse than no alarm, because it is the file
        # you would look at to decide whether the crawl is healthy.
        with open(failed_path, "w") as fh:
            json.dump([], fh)
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
        with open(failed_path, "w") as fh:
            json.dump(failures, fh, indent=1)
        print("boxscores: %d FAILED" % len(failures))


PLAYERBOX_JSONL = os.path.join(RAW, "playerbox.jsonl")
PLAYERS_JSON = os.path.join(RAW, "players_%d.json" % SEASON)


def crawl_players():
    # type: () -> None
    """Per-player season production, aggregated from /game/{id}/boxscore.

    WHY RE-CRAWL. Phase 1 fetched these boxscores and deliberately DROPPED
    playerStats (~82 MB, a different grain), recording at the time that
    /boxscore is ID-addressed and therefore re-crawlable. That note is why this
    is a one-hour job instead of a blocked one.

    VERIFIED, not assumed: a 2024 game's boxscore still resolves today with full
    playerStats, two seasons on. ID-addressed endpoints survive a season
    rollover -- unlike the rankings table, which is current-only and whose 2025
    snapshot is irreplaceable.

    STORAGE. The per-game player rows go to a gitignored working file so the
    crawl is resumable; only the AGGREGATE is committed. Raw-only means commit
    what cannot be regenerated, and this raw demonstrably can be.

    Names are stored EXACTLY as served. No normalisation at ingest -- the join
    downstream needs to see what each source actually said.
    """
    ids = game_ids_from_schedule()
    # FINAL GAMES ONLY, same rule the boxscore phase needed: a match that has
    # not been played has no player lines, and asking for them every morning
    # buys a pile of failures that hide a real one.
    finals = final_game_ids(GAMES_JSONL)
    have = set(load_records_jsonl(PLAYERBOX_JSONL, key="game_id"))
    todo = [g for g in ids if g in finals and g not in have]
    print("players: %d games enumerated, %d final, %d on disk, %d to fetch"
          % (len(ids), len(finals), len(have), len(todo)))

    if todo:
        failures = []
        start = time.time()
        with open(PLAYERBOX_JSONL, "a") as out:
            for i, gid in enumerate(todo, 1):
                payload = fetch("/game/%s/boxscore" % gid)
                if not payload:
                    failures.append(gid)
                else:
                    rows = []
                    for tb in payload.get("teamBoxscore") or []:
                        tid = str(tb.get("teamId"))
                        for ps in tb.get("playerStats") or []:
                            if not ps.get("participated"):
                                continue
                            rows.append({
                                "team_id": tid,
                                "first": ps.get("firstName"), "last": ps.get("lastName"),
                                "num": ps.get("number"), "pos": ps.get("position"),
                                "gp": ps.get("gamesPlayed"),
                                "kills": ps.get("kills"),
                                "errors": ps.get("attackErrors"),
                                "atts": ps.get("attackAttempts"),
                                "aces": ps.get("serviceAces"),
                                "digs": ps.get("digs"),
                                "bs": ps.get("blockSolos"), "ba": ps.get("blockAssists"),
                                "assists": ps.get("assists"), "points": ps.get("points"),
                            })
                    out.write(json.dumps({"game_id": gid, "rows": rows}) + "\n")
                    out.flush()
                    os.fsync(out.fileno())
                if i % 250 == 0 or i == len(todo):
                    rate = i / max(time.time() - start, 1e-6)
                    print("  %d/%d  %.1f req/s  ~%.0f min left  (%d failed)"
                          % (i, len(todo), rate,
                             (len(todo) - i) / max(rate, 1e-6) / 60.0, len(failures)))
        if failures:
            print("players: %d FAILED" % len(failures))

    # ---- aggregate to per-player season totals ----
    # AGGREGATE ON A CASE- AND PUNCTUATION-INSENSITIVE WHOLE NAME.
    # The feed spells the same player differently between games -- "LeeAnne
    # Lowery" vs "Leeanne Lowery", "Peyton DeJardin" vs "Peyton Dejardin". A
    # case-sensitive key split 360 players (6%) into two rows each and stranded
    # 11,568 kills in orphaned partials, understating those players' seasons.
    # Found because the roster join reported an "ambiguous" match on a player
    # who appeared twice under one team.
    _COUNTS = ("kills", "errors", "atts", "aces", "digs",
               "bs", "ba", "assists", "points")

    def _has_production(row):
        """Did this line record anything at all? Not 'did she play well'."""
        for k in _COUNTS:
            try:
                if int(str(row.get(k) or 0).strip() or 0):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    import unicodedata as _ud

    def _canon(first, last):
        # ⚠ FEED-CORRUPTION REPAIR FIRST (Taryn Gilreath, 2026-08-30): the
        # feed served one player as '\u200bTaryn' and as the same zero-width
        # space mojibake'd + case-mangled -- NFKD alone turned the mojibake
        # into a stray letter 'a' and split her season across two rows.
        # nameclean.repair is the ONE definition, shared with both nkey()s.
        import nameclean as _nc
        w = "%s %s" % (_nc.repair(first or ""), _nc.repair(last or ""))
        w = "".join(c for c in _ud.normalize("NFKD", w.lower())
                    if not _ud.combining(c))
        return re.sub(r"[^a-z]", "", w)

    # ---- PHANTOM SET LINES ------------------------------------------------
    # `gamesPlayed` is normally the PLAYER's sets and varies correctly between
    # starters and substitutes. In a minority of box scores it does not: every
    # listed player reports the same value -- the match's set count -- including
    # players whose line is entirely empty. Measured on the completed 2025
    # season: 173 of 5,131 games (3.4%), 444 such lines, 331 of those players
    # producing in other matches. Because `sets` is the denominator of every
    # per-set rate, those phantom sets understated their rates by a MEDIAN
    # 16.7% (p90 66.7%; 120 players by more than 25%).
    #
    # THE RULE, and it is narrower than "drop the game". We do not decide that a
    # player did not play because her line is empty -- that is an inference
    # about a person. We decline to CREDIT sets where there is no evidence of
    # participation: in a game whose gp is demonstrably not per-player, an empty
    # line is not evidence. A player with production in the same game keeps her
    # sets, because her line IS evidence she was on court.
    #
    # ⚠ Deliberately NOT applied to games where gp varies. There an empty line
    # with gp=1 is an ordinary substitute who did nothing measurable, and that
    # set is real. This only touches records where the field itself is broken.
    def _uniform_gp_game(rows):
        if not rows:
            return False
        if len(set(str(x.get("gp")) for x in rows)) != 1:
            return False
        return any(not _has_production(x) for x in rows)

    agg = {}
    seen_names = {}
    ngames = 0
    dropped_lines = 0
    # ⚠ AN EXHIBITION'S PLAYER LINES MUST NOT REACH THE SEASON AGGREGATE. This
    # file is what player_rating.py turns into per-set rates, and Spikes Under
    # the Lights plays its first two sets to 21 rather than 25 -- so folding it
    # in would deflate the rates of four of the best teams in the country while
    # nothing looked wrong. The ids are resolved once, centrally, because a
    # playerbox record carries a game_id and rows and nothing else: it cannot
    # evaluate a venue rule on its own.
    try:
        import exhibitions as _EXH
        _skip_gids = _EXH.resolved_gids(SEASON)
    except Exception:
        _skip_gids = set()
    _skipped_exh = 0
    for gid_key, rec in load_records_jsonl(PLAYERBOX_JSONL, key="game_id").items():
        if str(gid_key) in _skip_gids:
            _skipped_exh += 1
            continue
        ngames += 1
        _rows = rec.get("rows") or []
        _broken = _uniform_gp_game(_rows)
        for r in _rows:
            if _broken and not _has_production(r):
                dropped_lines += 1
                continue
            key = (r["team_id"], _canon(r.get("first"), r.get("last")))
            # keep the most frequently served spelling as the display name
            import nameclean as _nc2
            nm = (_nc2.repair((r.get("first") or "").strip()),
                  _nc2.repair((r.get("last") or "").strip()))
            seen_names.setdefault(key, collections.Counter())[nm] += 1
            e = agg.setdefault(key, {
                "team_id": r["team_id"], "first": r.get("first"),
                "last": r.get("last"), "num": r.get("num"), "pos": r.get("pos"),
                "matches": 0, "sets": 0, "kills": 0, "errors": 0, "atts": 0,
                "aces": 0, "digs": 0, "block_solos": 0, "block_assists": 0,
                "assists": 0, "points": 0,
            })
            e["matches"] += 1
            for src, dst in (("gp", "sets"), ("kills", "kills"), ("errors", "errors"),
                             ("atts", "atts"), ("aces", "aces"), ("digs", "digs"),
                             ("bs", "block_solos"), ("ba", "block_assists"),
                             ("assists", "assists"), ("points", "points")):
                try:
                    e[dst] += int(str(r.get(src) or 0).strip() or 0)
                except (TypeError, ValueError):
                    pass

    if dropped_lines:
        print("  phantom set lines skipped: %d "
              "(empty lines in games whose gp is not per-player)" % dropped_lines)

    for key, e in agg.items():
        best = seen_names.get(key)
        if best:
            # most frequent spelling wins; a TIE prefers the properly
            # cased form -- the mojibake repair leaves 'taryn' lowercase
            # (the feed case-mangled it), and with one game each the
            # counter's tie-break is arbitrary
            _top = best.most_common()
            _n0 = _top[0][1]
            _tied = [nm for nm, n in _top if n == _n0]
            f, l = sorted(_tied, key=lambda nm: (
                not (nm[0][:1].isupper() and nm[1][:1].isupper()),))[0]
            e["first"], e["last"] = f, l

    out = {
        "meta": {
            "season": SEASON, "source_tier": "OFFICIAL",
            "source": "ncaa-api /game/{id}/boxscore playerStats, aggregated",
            "games_aggregated": ngames,
            "exhibitions_excluded": len(_skip_gids),
            "exhibitions_note": ("matches that do not count are excluded here, "
                                 "not just from the display: their per-set "
                                 "rates are on a different scale"),
            "players": len(agg),
            "name_merge": "aggregated on a case/punctuation-insensitive whole "
                          "name; the feed spells players inconsistently between "
                          "games. Display name is the most frequent spelling.",
            "note": "Names stored exactly as served; no normalisation at ingest. "
                    "Per-game rows are NOT committed -- /boxscore is ID-addressed "
                    "and re-crawlable (verified against a 2024 game).",
        },
        "players": sorted(agg.values(),
                          key=lambda p: (p["team_id"], p.get("last") or "")),
    }
    with open(PLAYERS_JSON, "w") as fh:
        json.dump(out, fh, indent=1)
    print("players: %d aggregated from %d games -> %s"
          % (len(agg), ngames, PLAYERS_JSON))
    if _skipped_exh:
        print("  %d exhibition game(s) left OUT of the season aggregate"
              % _skipped_exh)


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
        elif phase == "players":
            crawl_players()
        elif phase == "boxscores":
            crawl_boxscores()
        elif phase == "fixtures":
            crawl_fixtures()
        elif phase == "recent":
            crawl_recent()
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
