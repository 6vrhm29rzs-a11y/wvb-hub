#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WHO IS MISSING -- ranked, from the box scores, without being told.

Cody, 2026-09-13: "the site should flag players playing vs players not
playing based on box scores and stats... i can't be the catch for
everything. this build and this system needs to scour all available info to
inform ME."

⚠ THE DETECTION ALREADY EXISTED AND WAS USELESS AS DELIVERED. availability.py
flags a team-match where a top-6 player has no box line, and it has flagged
**750** of them this season. Seven hundred and fifty undifferentiated flags
do not tell anybody anything; a reader needs the handful that matter, which
is a RANKING problem, not a detection one. This is the ranking.

WHAT IT CLAIMS, AND WHAT IT REFUSES TO CLAIM. This is PARTICIPATION -- an
observed fact about a box score -- and never availability, which in this
codebase may only be set by an attributable public source with its exact
wording. A player absent from a box may be injured, rested, suspended,
academically ineligible, or the scorer may have omitted her. This file says
"has not appeared since <date>" and nothing else, and no row it produces can
become a status.

THREE PARTICIPATION STATES, measured not inferred (2026-08-28): appeared
(recorded actions), zero-action listing (the feed's DNP convention: gp is
non-zero and every stat is 0 -- NOT an absence claim, four of Wisconsin's
five such listings were routine reserves), and not in the box at all.

Writes data/participation_radar_2026.json.
Run: python3 scripts/participation_radar.py
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "participation_radar_%d.json" % SEASON)

# A player has to have been ESTABLISHED before her absence means anything.
# Both numbers are stated conventions for display, not fitted to anything,
# and neither feeds a rating (R1).
MIN_MATCHES_BEFORE = 3      # appeared in at least this many earlier matches
MIN_SHARE = 0.04            # and carried at least 4% of the team's points


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    import player_rating as PR
    import gamelog
    import season_counts as SC
    import nameclean

    games = gamelog.load_games_jsonl(
        os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON))
    corr = SC.corrections(SEASON)
    when, opp_of, nm_of = {}, {}, {}
    for g in SC.countable(games, SEASON):
        g = SC.apply_correction(g, corr)
        gid = str(g.get("game_id"))
        ep = g.get("start_time_epoch")
        if ep:
            when[gid] = ep
        ts = g.get("teams") or []
        for t in ts:
            nm_of[str(t.get("team_id"))] = t.get("name_short")
        if len(ts) == 2:
            opp_of[(gid, str(ts[0].get("team_id")))] = ts[1].get("name_short")
            opp_of[(gid, str(ts[1].get("team_id")))] = ts[0].get("name_short")

    # team -> ordered match list; (team, player) -> appearances
    per_team = {}
    appear = {}
    points = {}
    display = {}
    for gid, rows in PR._counted_playerbox(SEASON):
        if gid not in when:
            continue
        for r in rows:
            tid = str(r.get("team_id"))
            per_team.setdefault(tid, set()).add(gid)
            raw = ("%s %s" % (r.get("first") or "",
                              r.get("last") or "")).strip()
            # ⚠⚠ KEY ON THE IDENTITY, NEVER ON THE DISPLAY STRING. The first
            # run of this file reported Brooklyn DeLeye -- 22% of Kentucky's
            # points -- as not having appeared since Sep 9. She played on the
            # 12th (14 kills) and the 13th. The feed simply changed her
            # spelling mid-season, "DeLeye" to "Deleye", so keying on the
            # printed name split one player into two: one who vanished and one
            # who arrived. Every re-spelled player would have raised a false
            # absence, which is the worst thing this feature could possibly
            # emit about a real person. PR.nkey is the chain's own canonical
            # key (repair + accent fold + letters only); the display name is
            # kept from her FIRST appearance, which is the school's spelling
            # before the feed drifted.
            key_nm = PR.nkey(raw)
            if not key_nm:
                continue
            nm = raw
            k, bs, ba = _f(r.get("kills")), _f(r.get("bs")), _f(r.get("ba"))
            pts = k + bs + ba / 2.0 + _f(r.get("aces"))
            acts = pts + _f(r.get("digs")) + _f(r.get("assists")) + \
                _f(r.get("errors")) + _f(r.get("atts"))
            key = (tid, key_nm)
            display.setdefault(key, nm)
            points[key] = points.get(key, 0.0) + pts
            # ⚠ A ZERO-ACTION LISTING IS NOT AN APPEARANCE. The crawled box
            # marks a DNP as gp=N with every stat zero (measured on Auguste,
            # whose live box carried setsPlayed:null), so "appeared" may
            # never be inferred from gp alone.
            if acts > 0:
                appear.setdefault(key, set()).add(gid)

    team_points = {}
    for (tid, _nm), p in points.items():
        team_points[tid] = team_points.get(tid, 0.0) + p

    out = []
    for tid, gids in per_team.items():
        order = sorted(gids, key=lambda g: when.get(g, 0))
        if len(order) < MIN_MATCHES_BEFORE + 1:
            continue
        tpts = team_points.get(tid) or 0.0
        for (t2, key_nm), seen in appear.items():
            if t2 != tid or not seen:
                continue
            nm = display.get((tid, key_nm), key_nm)
            share = (points.get((tid, key_nm), 0.0) / tpts) if tpts else 0.0
            last = max(seen, key=lambda g: when.get(g, 0))
            since = [g for g in order if when.get(g, 0) > when.get(last, 0)]
            if not since:
                continue                      # played in the latest match
            before = [g for g in order if when.get(g, 0) <= when.get(last, 0)]
            played_before = len([g for g in before if g in seen])
            if played_before < MIN_MATCHES_BEFORE or share < MIN_SHARE:
                continue
            out.append({
                "team": nm_of.get(tid), "team_id": tid, "player": nm,
                "missed": len(since),
                "missed_gids": since,
                "last_seen_gid": last,
                "last_seen_epoch": when.get(last),
                "last_opponent": opp_of.get((last, tid)),
                "played_before": played_before,
                "points": round(points.get((tid, key_nm), 0.0), 1),
                "share_of_team_points": round(share, 4),
                # what the team has had to replace, in its own points
                "weight": round(share * 100 * min(len(since), 5), 2),
                "claim": "has not appeared in a counted box score since this "
                         "date -- a participation fact, not an availability "
                         "status, and the reason is not in the data",
            })
    out.sort(key=lambda r: -r["weight"])
    doc = {
        "season": SEASON,
        "generated_utc": __import__("datetime").datetime.utcnow()
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "what_this_is": "Players established in a team's box scores who have "
                        "not appeared since a given date. Observed "
                        "participation only.",
        "what_this_is_not": "Not an availability status, not an injury, not a "
                            "diagnosis. A player may be rested, suspended, "
                            "ineligible, or simply omitted by a scorer.",
        "rules": {"min_matches_before": MIN_MATCHES_BEFORE,
                  "min_share_of_team_points": MIN_SHARE,
                  "zero_action_listing": "counted as NOT appearing -- the "
                                         "feed's DNP convention",
                  "ranking": "share of the team's points x matches missed "
                             "(capped at 5), a display ordering that feeds "
                             "nothing"},
        "n": len(out),
        "players": out,
    }
    json.dump(doc, io.open(OUT, "w", encoding="utf-8"), indent=1)
    print("participation radar: %d established players have not appeared "
          "in their team's most recent counted match(es)" % len(out))
    print("wrote %s\n" % OUT)
    print("%-22s %-18s %5s %6s  %s" % ("player", "team", "miss", "share",
                                       "last seen"))
    # ⚠ PACIFIC, like every other displayed date here. The first version
    # printed UTC and disagreed with the page about which day a match was
    # on (Sep 4 in the console, Sep 3 on the site) -- two answers to one
    # question is how this project's date bugs start.
    import datetime as _dt
    try:
        import zoneinfo
        _PT = zoneinfo.ZoneInfo("America/Los_Angeles")
    except Exception:                                       # noqa: BLE001
        _PT = None
    for r in out[:20]:
        _e = r["last_seen_epoch"] or 0
        ls = (_dt.datetime.fromtimestamp(_e, _dt.timezone.utc).astimezone(_PT)
              if _PT else _dt.datetime.utcfromtimestamp(_e))
        print("%-22s %-18s %5d %5.1f%%  %s vs %s"
              % (r["player"][:22], (r["team"] or "")[:18], r["missed"],
                 r["share_of_team_points"] * 100, ls.strftime("%b %d"),
                 r["last_opponent"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
