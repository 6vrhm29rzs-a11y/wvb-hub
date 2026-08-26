#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture Truth Ledger -- what actually happened to every non-final fixture.

⚠ THE PROBLEM. The weekly freeze refuses to publish while any match through the
cutoff is unresolved, which is right. But ncaa.com REMOVES fixtures from a past
date: twelve were crawled for 2026-08-21 and the source now lists two. Those
ten sit in the append-only log forever, non-final, and can never resolve --
so every week would need `--force`, and a gate that always needs overriding is
not a gate.

⚠ WHAT THIS IS NOT. It does not delete, rewrite, or ignore anything. The raw
logs are untouched and remain the record of what was fetched. This is a
DERIVED, AUDITABLE layer that says, with evidence, which of those records the
SOURCE ITSELF has withdrawn.

────────────────────────────────────────────────────────────────────────────
THE EVIDENCE RULE, and it deliberately contains no invented time threshold.

A non-final fixture is `source_withdrawn` only when ALL FIVE hold:

  1. Its Eastern date is strictly in the PAST.
  2. We hold a saved scoreboard observation of that exact date
     (`data/raw/{season}/scoreboard/{date}.json`, committed, so any of this is
     reproducible by anyone with the repo).
  3. That observation was taken at or after the fixture's own scheduled start,
     so the source had the opportunity to list it.
  4. ⚠ THE OBSERVATION SHOWS THE SOURCE HAD FINISHED WITH THAT DATE: every
     game it lists is FINAL. If anything there is still live or pending, the
     source is not done and an absence proves nothing.
  5. The fixture's game id is absent from that observation.

Point 4 is what replaces "it is old enough" with something checkable. A
cutoff in hours would have been a number I chose -- exactly the kind of
threshold that makes a verdict meaningless (R1). "The source has published
finals for this date and does not list this game" is an observation.

Anything that fails 2, 3 or 4 stays `unknown` and KEEPS BLOCKING. A fixture
that is live, or whose date has not passed, is `scheduled_or_live` and blocks.
We would rather wait than publish a poll that skipped a match.
────────────────────────────────────────────────────────────────────────────

Writes `data/fixture_disposition_{season}.json`. Python 3.9 target.
"""

import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weekly as WK  # noqa: E402

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
POLICY = "scoreboard-absence-v1"


def _obs_path(season, date, root=None):
    return os.path.join(root or REPO, "data", "raw", str(season), "scoreboard",
                        "%s.json" % date)


def observation(season, date, root=None):
    """What the source listed for `date`, the last time we looked."""
    p = _obs_path(season, date, root)
    if not os.path.exists(p):
        return None
    try:
        j = json.load(open(p))
    except ValueError:
        return None
    games = []
    for row in (j.get("games") or []):
        g = row.get("game") or {}
        games.append({"id": str(g.get("gameID") or ""),
                      "state": str(g.get("gameState") or "").lower()})
    stamp = j.get("updated_at")
    epoch = None
    if stamp:
        try:
            dt = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
            # ⚠ READ THE STAMP IN UTC, THE CONSERVATIVE CHOICE. The feed does
            # not label the zone. Reading it as UTC places the observation
            # EARLIER in Eastern terms, which can only make rule 3 harder to
            # satisfy -- so an ambiguity in the source cannot manufacture
            # evidence, it can only withhold it.
            epoch = int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())
        except ValueError:
            epoch = None
    if epoch is None:
        try:
            epoch = int(os.path.getmtime(p))
        except OSError:
            epoch = None
    return {"date": date, "observed_utc": stamp, "observed_epoch": epoch,
            "listed": games,
            "ids": set(g["id"] for g in games if g["id"]),
            "all_final": bool(games) and all(g["state"] == "final"
                                             for g in games),
            "n_listed": len(games)}


def classify(game, today, season, root=None, obs_cache=None):
    """One fixture's disposition, with the evidence that produced it."""
    gid = str(game.get("game_id"))
    date = WK.et_date(game.get("start_time_epoch"))
    teams = [t.get("name_short") for t in (game.get("teams") or [])][:2]
    base = {"game_id": gid, "date": date, "teams": teams,
            "state": game.get("game_state"),
            "start_epoch": game.get("start_time_epoch")}

    if game.get("game_state") == WK.FINAL:
        base.update({"disposition": "final", "reason": "the log records a final"})
        return base

    if game.get("game_state") in WK.LIVE_STATES:
        base.update({"disposition": "scheduled_or_live",
                     "reason": "the source reports this match in progress"})
        return base

    if not date or date >= today.isoformat():
        base.update({"disposition": "scheduled_or_live",
                     "reason": "its date has not passed"})
        return base

    cache = obs_cache if obs_cache is not None else {}
    if date not in cache:
        cache[date] = observation(season, date, root)
    obs = cache[date]

    if obs is None:
        base.update({"disposition": "unknown",
                     "reason": "no saved observation of this date to check"})
        return base
    ev = {"observed_utc": obs["observed_utc"], "listed": obs["n_listed"],
          "all_listed_final": obs["all_final"]}
    if obs["observed_epoch"] and game.get("start_time_epoch") and \
            obs["observed_epoch"] < int(game["start_time_epoch"]):
        base.update({"disposition": "unknown", "evidence": ev,
                     "reason": "the observation predates this fixture's start"})
        return base
    if not obs["all_final"]:
        base.update({"disposition": "unknown", "evidence": ev,
                     "reason": ("the source had not finished with this date: "
                                "not every listed game was final")})
        return base
    if gid in obs["ids"]:
        base.update({"disposition": "unknown", "evidence": ev,
                     "reason": ("the source still lists this fixture but it "
                                "is not final")})
        return base
    base.update({"disposition": "source_withdrawn", "evidence": ev,
                 "reason": ("the source published finals for this date and "
                            "does not list this fixture")})
    return base


def build(season=SEASON, today=None, root=None):
    today = today or datetime.date.today()
    root = root or REPO
    games = WK._load_games(os.path.join(root, "data", "raw", str(season),
                                        "games.jsonl"))
    cache = {}
    rows = [classify(g, today, season, root, cache) for g in games]
    rows.sort(key=lambda r: (r["date"] or "", r["game_id"]))
    counts = {}
    for r in rows:
        counts[r["disposition"]] = counts.get(r["disposition"], 0) + 1
    return {
        "season": season, "policy": POLICY,
        "built_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": today.isoformat(),
        "counts": counts,
        "note": ("Derived and auditable. The raw logs are never modified: this "
                 "records which fixtures the SOURCE itself no longer lists, "
                 "with the observation that shows it."),
        # Only the non-final rows are worth storing: a final needs no defence.
        "fixtures": [r for r in rows if r["disposition"] != "final"],
    }


def main():
    doc = build()
    out = os.path.join(REPO, "data", "fixture_disposition_%d.json" % SEASON)
    with open(out, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("fixture disposition (%s): %s" % (doc["policy"], doc["counts"]))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
