#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the clean, metric-agnostic 2025 dataset from the raw crawl.

Design constraints (Cody's settled decisions):
  * RAW COUNTS ONLY -- never derived rates. Per-set rates published by ncaa.com
    are dropped; the raw numerator and the set count are kept so any rate can be
    recomputed later at whatever denominator a future metric wants.
  * Every record carries a SOURCE TIER: OFFICIAL / DERIVED / THIRD-PARTY /
    UNVERIFIED.
  * Metric-agnostic. This file computes NO rating. It is the substrate the
    bake-off (net points/set vs TCV vs original Adj) will run against.
  * Dated. But this file is a BUILD ARTIFACT, not history -- it is gitignored
    and rebuilt on read. History lives in data/raw/, which is what gets committed
    per run, because raw is the part that cannot be regenerated.

Join key is team_id from the game log. Team NAMES are not a safe join key:
ncaa.com renders the same school differently across endpoints (New Orleans vs
LSU New Orleans), so names are used only to bridge the stat leaderboards, which
carry no ids, and every failure to bridge is reported rather than dropped.

Python 3.9 target.
"""

import datetime
import exhibitions as _EXH
import json
import os
import sys
import collections
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT_DIR = os.path.join(REPO, "data")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm, parse_record  # noqa: E402

# Raw count columns to keep per category. Per-set rate columns are deliberately
# dropped -- they are derived, and we store only what they are derived from.
CAT_FIELDS = {
    45: {"S": "sets", "Kills": "kills", "Errors": "attack_errors",
         "Total Attacks": "total_attacks"},
    46: {"S": "sets", "Kills": "kills"},
    47: {"S": "sets", "Assists": "assists"},
    48: {"S": "sets", "Aces": "aces"},
    49: {"S": "sets", "Block Solos": "block_solos",
         "Block Assists": "block_assists"},
    50: {"S": "sets", "Digs": "digs"},
    51: {"W": "wins", "L": "losses"},
}


def to_int(v):
    # type: (Any) -> Optional[int]
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return None


def load_games():
    # type: () -> List[Dict]
    from gamelog import load_games_jsonl
    games = load_games_jsonl(os.path.join(RAW, "games.jsonl"))
    games.sort(key=lambda g: (g.get("start_time_epoch") or 0, g["game_id"]))
    return games


def load_stats():
    # type: () -> Dict[str, Dict[str, Any]]
    """Stat leaderboards keyed by normalized team name."""
    out = collections.defaultdict(dict)  # type: Dict[str, Dict[str, Any]]
    sdir = os.path.join(RAW, "stats")
    if not os.path.isdir(sdir):
        return out
    for name in sorted(os.listdir(sdir)):
        if not name.endswith(".json"):
            continue
        payload = json.load(open(os.path.join(sdir, name)))
        cat = payload.get("_wvb_category_id")
        fields = CAT_FIELDS.get(cat, {})
        for row in payload.get("data", []):
            key = norm(row.get("Team"))
            if not key:
                continue
            bucket = out[key]
            bucket["_name"] = row.get("Team")
            for src, dst in fields.items():
                val = to_int(row.get(src))
                if val is None:
                    continue
                # 'sets' and 'kills' appear in multiple categories; they must
                # agree. Disagreement is a real data problem, not a merge
                # detail, so surface it instead of silently taking the last.
                if dst in bucket and bucket[dst] != val:
                    bucket.setdefault("_conflicts", []).append(
                        {"field": dst, "have": bucket[dst], "saw": val, "cat": cat})
                bucket[dst] = val
    return out


def _local_date(g):
    """The Pacific date of a match, for the venue+date exhibition rule.

    ⚠ PACIFIC, because that is what the ledger is written in and what the hub
    displays. Using UTC here would put a 5pm Pacific match on the next day and
    the rule would silently never fire.
    """
    ep = g.get("start_time_epoch")
    if not ep:
        return None
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")
        return datetime.datetime.fromtimestamp(int(ep), tz).strftime("%Y-%m-%d")
    except Exception:
        return datetime.datetime.utcfromtimestamp(int(ep)).strftime("%Y-%m-%d")


def main():
    games = load_games()
    stats = load_stats()
    from membership import resolve as resolve_membership
    di_names, official_rows, di_source = resolve_membership(RAW, games)
    rpi_rows = list(official_rows.values())
    print("D-I membership: %s" % di_source)

    # Division-I membership comes from the official RPI table, NOT from the
    # per-team `division` field on /game/{id}. That field reports the team's
    # CURRENT division rather than its 2025 division: Saint Francis (PA) played
    # 2025 in D-I (official record 20-9) but is now served as `div3`, while
    # West Florida is served as `div1` on an all-D-II schedule. See
    # scripts/reconcile_2025.py -- using the raw field leaves 18 teams short.


    # ---- per-team aggregation from the game log (DERIVED) ----
    agg = collections.defaultdict(lambda: {
        "games": 0, "di_w": 0, "di_l": 0, "nondi_w": 0, "nondi_l": 0,
        "sets_won": 0, "sets_lost": 0, "points_for": 0, "points_against": 0,
        "sets_with_points": 0, "name_short": None, "seoname": None,
        "name_full": None, "division": None,
    })

    _skipped_exhibitions = set()
    try:
        from dupes import duplicate_gids
        _dup_of = duplicate_gids(SEASON)
    except Exception:                                  # noqa: BLE001
        _dup_of = {}
    for g in games:
        if g.get("game_state") != "F":
            continue
        # ⚠ A LEDGERED DUPLICATE COUNTS NOWHERE (round 11). Entered only on
        # authoritative evidence (both schools' official schedules establish
        # ONE meeting) -- never by heuristic, so real doubleheaders are safe.
        # The game itself is still persisted below, marked duplicate_of, so
        # the Result Ledger can show it with the reason; these tallies are
        # what the ratings, RPI, records and every counting surface read.
        if str(g.get("game_id")) in _dup_of:
            continue
        # ⚠ AN EXHIBITION IS FINAL TOO, AND FILTERING ON 'F' ALONE LET IT IN.
        # This function builds the dataset the RATING, the RPI, the simulator
        # and the field projector all read. Until this line existed, the hub's
        # display layer excluded Spikes Under the Lights correctly while every
        # rating in the project would have counted it -- which is the exact
        # opposite of the priority Cody set ("keep the stats out of the ratings
        # and rankings"). Its first two sets go to 21 rather than 25, so it
        # would also have deflated every per-set rate it touched.
        if _EXH.is_exhibition(g, SEASON, _local_date(g)):
            _skipped_exhibitions.add(str(g.get("game_id")))
            continue
        teams = g.get("teams") or []
        if len(teams) != 2:
            continue
        home_pts = away_pts = 0
        n_periods = 0
        for ls in g.get("linescores") or []:
            h, v = to_int(ls.get("home")), to_int(ls.get("visit"))
            if h is None or v is None:
                continue
            home_pts += h
            away_pts += v
            n_periods += 1
        for t in teams:
            tid = t.get("team_id")
            if not tid:
                continue
            other = [x for x in teams if x is not t][0]
            e = agg[tid]
            e["name_short"] = e["name_short"] or t.get("name_short")
            e["name_full"] = e["name_full"] or t.get("name_full")
            e["seoname"] = e["seoname"] or t.get("seoname")
            if e["division"] is None:
                e["division"] = t.get("division")
            e["games"] += 1
            won = bool(t.get("is_winner"))
            if norm(other.get("name_short")) in di_names:
                e["di_w" if won else "di_l"] += 1
            else:
                e["nondi_w" if won else "nondi_l"] += 1
            e["sets_won"] += to_int(t.get("sets_won")) or 0
            e["sets_lost"] += to_int(other.get("sets_won")) or 0
            e["sets_with_points"] += n_periods
            if t.get("is_home"):
                e["points_for"] += home_pts
                e["points_against"] += away_pts
            else:
                e["points_for"] += away_pts
                e["points_against"] += home_pts

    # ---- official RPI table, joined by normalized name ----
    rpi_by_norm = official_rows
    agg_by_norm = {}
    for tid, e in agg.items():
        agg_by_norm.setdefault(norm(e["name_short"]), tid)

    teams_out = []
    stat_unjoined = set(stats)
    rpi_unjoined = set(rpi_by_norm)

    for tid, e in sorted(agg.items(), key=lambda kv: kv[1]["name_short"] or ""):
        key = norm(e["name_short"])
        official = rpi_by_norm.get(key)
        st = stats.get(key)
        stat_unjoined.discard(key)
        rpi_unjoined.discard(key)
        off_rec = parse_record(official.get("Record")) if official else None

        rec = {
            "team_id": tid,
            "name_short": e["name_short"],
            "name_full": e["name_full"],
            "seoname": e["seoname"],
            "division": e["division"],
            "conference": official.get("Conf") if official else None,
            "is_division_i": official is not None,
            # championship-ineligible reclassifiers appear in the official RPI
            # table but are absent from the stat leaderboards
            "in_official_rpi": official is not None,
            "in_stat_leaderboards": st is not None,

            "official": {
                "source_tier": "OFFICIAL",
                "rpi_rank": to_int(official.get("Rank")) if official else None,
                "record_di": {"w": off_rec[0], "l": off_rec[1]} if off_rec else None,
                "record_non_di": (lambda p: {"w": p[0], "l": p[1]} if p else None)(
                    parse_record(official.get("Non-Div I")) if official else None),
                "road": official.get("Road") if official else None,
                "home": official.get("Home") if official else None,
                "neutral": official.get("Neutral") if official else None,
                "prev_rank": to_int(official.get("Prev")) if official else None,
            },

            # RAW COUNTS from the stat leaderboards. No rates.
            "season_totals": ({
                "source_tier": "OFFICIAL",
                "sets": st.get("sets"),
                "kills": st.get("kills"),
                "attack_errors": st.get("attack_errors"),
                "total_attacks": st.get("total_attacks"),
                "assists": st.get("assists"),
                "aces": st.get("aces"),
                "block_solos": st.get("block_solos"),
                "block_assists": st.get("block_assists"),
                "digs": st.get("digs"),
                "wins": st.get("wins"),
                "losses": st.get("losses"),
                "_conflicts": st.get("_conflicts"),
            } if st else None),

            "derived_from_game_log": {
                "source_tier": "DERIVED",
                "games": e["games"],
                "record_di": {"w": e["di_w"], "l": e["di_l"]},
                "record_non_di": {"w": e["nondi_w"], "l": e["nondi_l"]},
                "sets_won": e["sets_won"],
                "sets_lost": e["sets_lost"],
                "points_for": e["points_for"],
                "points_against": e["points_against"],
                "sets_with_linescores": e["sets_with_points"],
            },
        }
        teams_out.append(rec)

    # ---- games, trimmed to the raw fields worth persisting ----
    games_out = []
    for g in games:
        teams = g.get("teams") or []
        games_out.append({
            "duplicate_of": _dup_of.get(str(g.get("game_id"))) or None,
            "game_id": g["game_id"],
            "season": g.get("season_year"),
            "start_time_epoch": g.get("start_time_epoch"),
            "state": g.get("game_state"),
            "winner_team_id": str(g["winner_team_id"]) if g.get("winner_team_id") else None,
            "championship": g.get("championship"),
            "teams": [{
                "team_id": t.get("team_id"),
                "name_short": t.get("name_short"),
                "is_home": t.get("is_home"),
                "division": t.get("division"),
                "sets_won": to_int(t.get("sets_won")),
                "is_winner": t.get("is_winner"),
            } for t in teams],
            "linescores": [{
                "period": to_int(ls.get("period")),
                "home": to_int(ls.get("home")),
                "visit": to_int(ls.get("visit")),
            } for ls in (g.get("linescores") or [])],
            "source_tier": "OFFICIAL",
        })

    now = datetime.datetime.utcnow().replace(microsecond=0)
    payload = {
        "meta": {
            "season": SEASON,
            "generated_at_utc": now.isoformat() + "Z",
            "generator": "scripts/build_dataset.py",
            "source": "ncaa.com via ncaa-api.henrygd.me",
            "official_through": "games of 2025-12-21",
            "counts": {
                "games": len(games_out),
                "teams": len(teams_out),
                "teams_in_official_rpi": sum(1 for t in teams_out if t["in_official_rpi"]),
                "teams_in_stat_leaderboards": sum(
                    1 for t in teams_out if t["in_stat_leaderboards"]),
            },
            "source_tiers": {
                "OFFICIAL": "raw values as published by ncaa.com",
                "DERIVED": "computed here from OFFICIAL raw values",
                "THIRD-PARTY": "not present in this file",
                "UNVERIFIED": "not present in this file",
            },
            "notes": [
                "Raw counts only; per-set rates published by ncaa.com are dropped "
                "deliberately. Recompute any rate from the raw count and 'sets'.",
                "No rating metric is computed here by design -- the metric is "
                "deferred until the bake-off runs against 2025 outcomes.",
                "The official RPI 'record_di' column counts Division I opponents "
                "only; non-D-I games are broken out into 'record_non_di'.",
                "Stat leaderboards cover 343 teams and exclude championship-"
                "ineligible reclassifying programs; the RPI table covers 348.",
            ],
            "unjoined_stat_leaderboard_teams": sorted(stat_unjoined),
            "unjoined_official_rpi_teams": sorted(rpi_unjoined),
        },
        "teams": teams_out,
        "games": games_out,
    }

    # data_2025.json is a BUILD ARTIFACT, not history. It is a pure function of
    # data/raw/ plus this script, and git already versions the script -- so it is
    # gitignored and rebuilt on read. What gets committed per run is data/raw/,
    # because raw is the part that CANNOT be regenerated: the rankings endpoint
    # has no season pin, so once the season rolls over the official RPI table for
    # a past season is gone permanently. Store raw, derive everything else --
    # the same principle already governing raw counts vs derived rates.
    out_path = os.path.join(OUT_DIR, "data_%d.json" % SEASON)
    with open(out_path, "w") as fh:
        json.dump(payload, fh, indent=1)

    print("teams: %d  (official RPI %d / stat leaderboards %d)" % (
        len(teams_out),
        payload["meta"]["counts"]["teams_in_official_rpi"],
        payload["meta"]["counts"]["teams_in_stat_leaderboards"]))
    print("games: %d" % len(games_out))
    # ⚠ SAY WHAT WAS LEFT OUT. A filter that removes matches silently is
    # indistinguishable from a crawl that missed them, and the daily log is
    # the first place anyone would look.
    if _skipped_exhibitions:
        print("excluded %d exhibition match(es) that do not count: %s"
              % (len(_skipped_exhibitions),
                 ", ".join(sorted(_skipped_exhibitions))))
    # NAME THE PROBLEM, DO NOT WALLPAPER THE LOG WITH IT.
    # Early in a season the stat leaderboards are empty, so EVERY team is
    # unjoined -- 338 of them, dumped in full into the daily log every morning.
    # A wall that size is not a warning, it is camouflage: the day one genuinely
    # odd name appears, nobody will see it. Print the count, a sample, and let
    # the ratio say whether this is "nothing has been published yet" or "the
    # join is broken".
    def _unjoined(label, names, total):
        if not names:
            return
        n = len(names)
        sample = ", ".join(sorted(names)[:8])
        if total and n >= total:
            print("UNJOINED %s: all %d -- the source has published nothing yet "
                  "for this season, which is normal in August" % (label, n))
        else:
            print("UNJOINED %s: %d of %d -- %s%s"
                  % (label, n, total, sample, ", ..." if n > 8 else ""))

    _unjoined("stat-leaderboard teams", stat_unjoined,
              payload["meta"]["counts"]["teams_in_stat_leaderboards"] or len(stat_unjoined))
    _unjoined("official-RPI teams", rpi_unjoined,
              payload["meta"]["counts"]["teams_in_official_rpi"] or len(rpi_unjoined))
    print("wrote %s  (build artifact, gitignored -- rebuilt on read)" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
