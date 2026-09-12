#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The season's rating movement, reconstructed from committed snapshots.

Cody, 2026-09-11: a chart of the top teams' POWER through the season, a tick
per day, lines rising and falling.

⚠ WHY GIT HISTORY IS A LEGITIMATE SOURCE HERE, and the weekly archive is not
the only one. data/rankings_history_*.jsonl is declared un-rebuildable for a
real reason: re-deriving a past week's ranking from data that includes that
week's results would be a FIT, not a ranking. This does something different.
Every commit of digby_top25_2026.json holds the artifact AS IT WAS COMPUTED
THAT DAY, from the matches known at that moment. Reading it back is reading
what we actually published, not refitting it. The weekly archive stays the
record; this is a second, compatible view of the same history.

⚠ THE BASIS CHANGES AND THE CHART MUST SAY SO. The board ran on the preseason
projection, then the blend, and moves to the live fit once the rating
validates. A line drawn straight across that transition reports a team moving
when the RULER moved -- the same error the movement column refuses to make.
Each point therefore carries its own basis, and a consumer that ignores it is
doing arithmetic on two rulers.

⚠ GAPS ARE REAL AND ARE NOT INTERPOLATED. There is no snapshot for
2026-08-25..27 or 2026-09-09..10. A day we did not publish is a hole, not a
straight line between neighbours.

Python 3.9 target.
"""
import io
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
ART = "data/digby_top25_%d.json" % SEASON
OUT = os.path.join(REPO, "data", "rating_history_%d.json" % SEASON)


def _git(*a):
    return subprocess.check_output(["git"] + list(a), cwd=REPO,
                                   text=True, errors="replace")


def day_commits():
    """The LAST commit of each day that touched the artifact.

    Last rather than first: it is the day's settled state, after the evening's
    finals, which is what a reader means by "where they stood that day".
    """
    out = []
    for line in _git("log", "--format=%H %ad", "--date=short",
                     "--", ART).splitlines():
        sha, _, day = line.partition(" ")
        if sha and day:
            out.append((day.strip(), sha))
    best = {}
    for day, sha in out:                 # git log is newest-first
        best.setdefault(day, sha)        # so the first seen IS the last of day
    return sorted(best.items())


def series():
    pts = []
    for day, sha in day_commits():
        try:
            blob = _git("show", "%s:%s" % (sha, ART))
            d = json.loads(blob)
        except Exception:                                    # noqa: BLE001
            continue
        rows = d.get("all") or []
        if not rows:
            continue
        meta = d.get("meta") or {}
        pts.append({
            "day": day,
            "commit": sha[:9],
            "basis": meta.get("blend") and "blend" or meta.get("basis") or "blend",
            "generated_at_utc": meta.get("generated_at_utc"),
            "teams": {r["team"]: {"rank": r.get("rank"),
                                  "score": r.get("score"),
                                  "matches": r.get("matches")}
                      for r in rows if r.get("team")},
        })
    return pts


def main():
    pts = series()
    if not pts:
        print("no snapshots found for %s" % ART)
        return 1
    days = [p["day"] for p in pts]
    # state the holes rather than smoothing them away
    import datetime
    d0 = datetime.date(*map(int, days[0].split("-")))
    d1 = datetime.date(*map(int, days[-1].split("-")))
    have = set(days)
    gaps = []
    cur = d0
    while cur <= d1:
        s = cur.isoformat()
        if s not in have:
            gaps.append(s)
        cur += datetime.timedelta(days=1)
    doc = {
        "meta": {
            "source": "committed snapshots of %s, one per day (the day's "
                      "last commit)" % ART,
            "not_a_refit": "each point is the artifact as computed that day, "
                           "from the matches known then -- never re-derived "
                           "from later results",
            "days": len(pts), "first": days[0], "last": days[-1],
            "missing_days": gaps,
            "missing_days_note": "no snapshot was published on these days; a "
                                 "consumer must draw a gap, not a line",
            "basis_note": "each point carries its own basis; comparing across "
                          "a basis change measures the ruler, not the team",
        },
        "points": pts,
    }
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print("wrote %s" % os.path.relpath(OUT, REPO))
    print("  %d days, %s -> %s, %d team-rows per day"
          % (len(pts), days[0], days[-1], len(pts[-1]["teams"])))
    print("  gaps (no snapshot): %s" % (", ".join(gaps) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
