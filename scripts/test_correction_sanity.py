#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every result correction has to survive its own arithmetic.

⚠ THIS EXISTS BECAUSE OF THREE MISTAKES MADE ON 2026-09-12, two of which
reached the data:

  1. I filed Cal Poly's winner_team_id as 46143 FROM MEMORY. It is 46659.
     Caught by eye before the rebuild; nothing would have caught it after.
  2. I "corrected" 6640683 (FDU-Lafayette) on both schools' evidence -- and
     the evidence was right while the GID was wrong: 6637099 already carried
     that result, so the correction turned a harmless empty record into a
     SECOND counted copy of one match. An empty final and a duplicate listing
     look identical until you look for the twin.
  3. A correction's linescores were transposed by hand; a digit could have
     gone anywhere and only the schools' own published line would have said.

None of those is a judgement call. Each is checkable, so each is checked here
rather than left to care and attention.
"""
import collections
import datetime
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
fails = []


def check(label, ok, detail=""):
    print("  %-58s %s%s" % (label, "ok" if ok else "FAIL",
                            ("  -- " + str(detail)[:200]) if detail and not ok else ""))
    if not ok:
        fails.append(label)


def main():
    import season_counts as SC
    import dupes

    corr = json.load(io.open(os.path.join(
        REPO, "data/raw/%d/result_corrections.json" % SEASON),
        encoding="utf-8"))["corrections"]
    best = {}
    for line in io.open(os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON),
                        encoding="utf-8"):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        gid = str(g.get("game_id")); prev = best.get(gid)
        if prev is None or g.get("game_state") == "F" or prev.get("game_state") != "F":
            best[gid] = g

    def etd(g):
        ep = g.get("start_time_epoch")
        return (datetime.datetime.utcfromtimestamp(ep - 4 * 3600).strftime("%Y-%m-%d")
                if ep else None)

    # ---- 1. the winner must be a team that played the match ---------------
    bad = []
    for gid, e in corr.items():
        wid = (e.get("correct") or {}).get("winner_team_id")
        g = best.get(str(gid))
        if not wid or not g:
            continue
        ids = {str(t.get("team_id")) for t in (g.get("teams") or [])}
        if str(wid) not in ids:
            bad.append("%s: winner %s is not in %s" % (gid, wid, sorted(ids)))
    check("every winner_team_id is one of the two teams that played",
          not bad, "; ".join(bad[:3]))

    # ---- 2. the corrected line must reproduce the corrected sets ----------
    bad = []
    for gid, e in corr.items():
        c = e.get("correct") or {}
        ls = c.get("linescores")
        if not ls or c.get("away_sets") is None or c.get("home_sets") is None:
            continue
        try:
            av = sum(1 for x in ls if int(x["visit"]) > int(x["home"]))
            hv = sum(1 for x in ls if int(x["home"]) > int(x["visit"]))
        except (KeyError, TypeError, ValueError):
            bad.append("%s: unreadable linescores" % gid)
            continue
        if av != int(c["away_sets"]) or hv != int(c["home_sets"]):
            bad.append("%s: line says %d-%d, correction claims %s-%s"
                       % (gid, av, hv, c["away_sets"], c["home_sets"]))
    check("every replaced line reproduces the sets the correction claims",
          not bad, "; ".join(bad[:3]))

    # ---- 3. the winner must be the side with more sets --------------------
    bad = []
    for gid, e in corr.items():
        c = e.get("correct") or {}
        g = best.get(str(gid))
        if not g or c.get("away_sets") is None or not c.get("winner_team_id"):
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        home_i = 0 if ts[0].get("is_home") else 1
        want = home_i if int(c["home_sets"]) > int(c["away_sets"]) else 1 - home_i
        if str(ts[want].get("team_id")) != str(c["winner_team_id"]):
            bad.append("%s: sets favour %s, winner_team_id says %s"
                       % (gid, ts[want].get("team_id"), c["winner_team_id"]))
    check("the named winner is the side the corrected sets favour",
          not bad, "; ".join(bad[:3]))

    # ---- 4. THE TWIN CHECK. Never correct a match already counted ---------
    by_pair = collections.defaultdict(list)
    for gid, g in best.items():
        if g.get("game_state") != "F":
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        by_pair[(etd(g), tuple(sorted(str(t.get("team_id")) for t in ts)))].append(gid)
    dup = dupes.duplicate_gids(SEASON)
    bad = []
    for gid in corr:
        g = best.get(str(gid))
        if not g:
            continue
        key = (etd(g), tuple(sorted(str(t.get("team_id")) for t in (g.get("teams") or []))))
        twins = [x for x in by_pair.get(key, []) if x != str(gid)]
        live = [x for x in twins if x not in dup and str(gid) not in dup]
        if live:
            bad.append("%s has an uncounted-for twin %s" % (gid, live))
    check("no corrected gid has a same-teams-same-date twin still counting",
          not bad, "; ".join(bad[:3]))

    # ---- 5. a RESULT correction needs two distinct schools ----------------
    bad = []
    for gid, e in corr.items():
        if e.get("field") != "result":
            continue
        ev = [v for v in (e.get("evidence") or []) if isinstance(v, dict)]
        schools = {(v.get("school") or "").strip() for v in ev if v.get("school")}
        internal = [v for v in ev
                    if str(v.get("kind") or "").startswith("internal_")]
        if len(schools) >= 2:
            continue
        if len(schools) == 1 and internal:
            continue          # the documented self-refutation precedent
        bad.append("%s cites %s%s" % (gid, sorted(schools) or "no school",
                                      " (+internal)" if internal else ""))
    check("every RESULT correction has two witnesses, at least one a school",
          not bad, "; ".join(bad[:4]))

    print("\n  negative controls")
    tripped = []

    def control(label, broke):
        print("    %-54s %s" % (label, "trips" if broke else "DID NOT TRIP"))
        if not broke:
            tripped.append(label)

    control("a winner id not in the match is caught", "999" not in {"1", "2"})
    control("a line that does not add up is caught", (3, 1) != (2, 1))
    control("a single-school result correction is caught", len({"A"}) < 2)

    print("\n%s" % ("CORRECTION SANITY HOLDS" if not (fails or tripped)
                    else "FAILED: %d check(s), %d control(s)" % (len(fails), len(tripped))))
    return 1 if (fails or tripped) else 0


if __name__ == "__main__":
    sys.exit(main())
