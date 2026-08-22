#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Win probability for every scheduled 2026 match.

Reuses the rally model from scripts/simulate_2025.py rather than inventing a
second one: an expected per-set point margin becomes a per-rally probability,
and the best-of-5 outcome distribution follows analytically (Ferrante & Fonseca)
instead of by coin-flipping. That model is CALIBRATED -- Brier 0.1289 across
5,014 matches, every probability bucket within 3.4 points -- which is the claim
that matters for a number presented as a percentage.

WHERE STRENGTH COMES FROM, and this is the honest limit early in a season:
2026 has a handful of matches, so nearly all of the signal is last season's
opponent-adjusted net points/set. That prior predicts the following season at
spearman 0.857, which is strong but is emphatically NOT the same thing as
knowing how this year's team plays. Every row carries how many 2026 matches its
teams have actually played, so a 71% built on nothing can be told from one built
on something.

HOME ADVANTAGE IS APPLIED ONLY WHERE THERE IS A HOME TEAM. The fitted advantage
comes from our own ridge solve, not the literature, and scripts/venues.py says
which floors are neutral. All eight Jeep AVCA First Serve matches are neutral,
so none of them gets one.

Python 3.9 target. Writes data/predictions_2026.json.
"""

import json
import os
import sys
import glob
import datetime
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulate_2025 as S  # noqa: E402

SEASON = 2026
OUT = os.path.join(REPO, "data", "predictions_%d.json" % SEASON)
# A PERMANENT RECORD OF WHAT WE SAID BEFORE THE MATCH.
# predictions_2026.json only ever holds FUTURE fixtures -- a game drops out of it
# the moment it is played. Scoring the model against results afterwards would
# then mean re-deriving a "prediction" from data that now includes the outcome,
# which is not a forecast, it is a fit. So each fixture's first prediction is
# appended here and NEVER revised: first write wins, permanently.
LOG = os.path.join(REPO, "data", "raw", str(SEASON), "prediction_log.jsonl")

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                       # pragma: no cover
    ET = None


def load(p, default=None):
    path = os.path.join(REPO, p)
    return json.load(open(path)) if os.path.exists(path) else default


def et_date(epoch):
    if not epoch:
        return None
    if ET:
        return datetime.datetime.fromtimestamp(int(epoch), ET).strftime("%Y-%m-%d")
    return (datetime.datetime.utcfromtimestamp(int(epoch))
            - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")


def build():
    rating = load("data/rating_2025.json") or {}
    strength = {}
    for t in rating.get("teams", []):
        v = t.get("adj_net_points_set")
        if v is not None:
            strength[t["team"]] = v
    if not strength:
        print("no 2025 rating to stand on")
        return None

    venues = load("data/venues_%d.json" % SEASON) or {}
    site_of = {r["game_id"]: r["site"] for r in venues.get("games", [])}
    event_of = {}
    for e in venues.get("events", []):
        for gid in e.get("game_ids", []):
            event_of[gid] = e.get("name")

    # how many 2026 matches has each team actually played? -- the honesty column
    played = {}
    gpath = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if os.path.exists(gpath):
        seen = set()
        for line in open(gpath):
            try:
                g = json.loads(line)
            except ValueError:
                continue
            if not isinstance(g, dict) or g.get("game_state") != "F":
                continue
            if g.get("game_id") in seen:
                continue
            seen.add(g.get("game_id"))
            for t in g.get("teams") or []:
                nm = t.get("name_short")
                if nm:
                    played[nm] = played.get(nm, 0) + 1

    # the fitted home advantage, in points per set, from our own ridge solve
    home_adv = 0.0
    try:
        import bakeoff_2025 as B
        matches, di = B.load()
        M = B.build_metrics(matches, di)
        home_adv = M.get("_home_adv_points_per_set", 0.0) or 0.0
    except Exception:
        home_adv = 0.0

    today = datetime.date.today().isoformat()
    rows, skipped = [], 0
    for path in sorted(glob.glob(os.path.join(
            REPO, "data/raw/%d/scoreboard/*.json" % SEASON))):
        try:
            payload = json.load(open(path))
        except ValueError:
            continue
        for entry in payload.get("games") or []:
            g = entry.get("game", entry)
            gid = str(g.get("gameID") or "")
            a = (g.get("away") or {}).get("names", {}).get("short")
            h = (g.get("home") or {}).get("names", {}).get("short")
            if not a or not h:
                continue
            date = et_date(g.get("startTimeEpoch")) or os.path.basename(path)[:-5]
            if date < today:
                continue
            if a not in strength or h not in strength:
                # A team we have no 2025 rating for -- usually a non-D-I
                # opponent. Skipped rather than given a made-up strength.
                skipped += 1
                continue

            site = site_of.get(gid)
            adv = 0.0 if site == "neutral" else home_adv
            margin = (strength[h] + adv) - strength[a]      # home team's margin
            p = S.rally_p(margin)
            dist = S.match_dist(p)
            rows.append({
                "game_id": gid, "date": date,
                "time": (g.get("startTime") or "").strip(),
                "away": a, "home": h,
                "home_win": round(dist["win"], 4),
                "away_win": round(1.0 - dist["win"], 4),
                "home_margin_per_set": round(margin, 3),
                "neutral": site == "neutral",
                "event": event_of.get(gid),
                "played_2026": {"away": played.get(a, 0), "home": played.get(h, 0)},
                # NAME WHOSE DISTRIBUTION THIS IS. match_dist() returns w/l
                # from the perspective of the team whose rally probability was
                # passed in -- the HOME team here. Printed as bare w30/w31/w32
                # it read as the favourite's distribution and showed
                # "Pittsburgh 98%  (3-0 0% / 3-1 1%)", which is Xavier's.
                "home_dist": {"3-0": round(dist["w30"], 4),
                              "3-1": round(dist["w31"], 4),
                              "3-2": round(dist["w32"], 4)},
                "away_dist": {"3-0": round(dist["l30"], 4),
                              "3-1": round(dist["l31"], 4),
                              "3-2": round(dist["l32"], 4)},
            })
    rows.sort(key=lambda r: (r["date"], r["time"]))
    return {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "model": ("rally model from simulate_2025.py -- one pooled per-rally "
                      "probability, best-of-5 distribution derived analytically"),
            "calibration": ("Brier 0.1289 over 5,014 matches, every bucket within "
                            "3.4 points (measured on 2025)"),
            "strength_source": ("2025 opponent-adjusted net points/set. 2026 has "
                                "barely been played, so this is a prior, not a "
                                "read on this year's teams"),
            "home_advantage_points_per_set": round(home_adv, 4),
            "home_advantage_applied": "except on floors venues.py calls neutral",
            "fixtures": len(rows),
            "skipped_no_rating": skipped,
        },
        "games": rows,
    }


def append_log(rows):
    """Record the first prediction made for each fixture, once, forever."""
    seen = set()
    if os.path.exists(LOG):
        for line in open(LOG):
            try:
                seen.add(json.loads(line)["game_id"])
            except (ValueError, KeyError):
                continue
    added = 0
    if not os.path.isdir(os.path.dirname(LOG)):
        os.makedirs(os.path.dirname(LOG))
    with open(LOG, "a") as fh:
        for r in rows:
            if r["game_id"] in seen:
                continue
            fh.write(json.dumps({
                "game_id": r["game_id"], "date": r["date"],
                "away": r["away"], "home": r["home"],
                "home_win": r["home_win"], "neutral": r["neutral"],
                "played_2026": r["played_2026"],
                "logged_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }) + "\n")
            added += 1
    return added, len(seen) + added


if __name__ == "__main__":
    out = build()
    if not out:
        sys.exit(1)
    json.dump(out, open(OUT, "w"), indent=1)
    added, total = append_log(out["games"])
    print("prediction log: +%d new, %d fixtures on record" % (added, total))
    m = out["meta"]
    print("wrote %s" % OUT)
    print("  fixtures predicted : %d" % m["fixtures"])
    print("  skipped (no rating): %d" % m["skipped_no_rating"])
    print("  home advantage     : %+.3f points/set (fitted)"
          % m["home_advantage_points_per_set"])
    print("\n  next up:")
    for r in out["games"][:10]:
        fav = r["home"] if r["home_win"] >= 0.5 else r["away"]
        pct = max(r["home_win"], r["away_win"])
        tag = "  [%s]" % r["event"] if r["event"] else ("  [neutral]" if r["neutral"] else "")
        d = r["home_dist"] if r["home_win"] >= 0.5 else r["away_dist"]
        print("     %s  %-20s at %-20s  %-14s %.0f%%  (3-0 %.0f / 3-1 %.0f / 3-2 %.0f)%s"
              % (r["date"], r["away"][:20], r["home"][:20], fav[:14], 100 * pct,
                 100 * d["3-0"], 100 * d["3-1"], 100 * d["3-2"], tag))
