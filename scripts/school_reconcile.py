#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diff our counted matches against the schools' own schedules, BY DATE.

⚠ COUNT PER DATE; DO NOT MATCH OPPONENT NAMES. Schools write "Binghamton
University", "College of Charleston", "University of the Pacific" where the
hub writes "Binghamton", "Col. of Charleston", "Pacific". A name-matching
diff reported eight false gaps for Bradley alone. The DATE is unambiguous on
both sides, so a date whose counts agree needs no names at all, and only the
dates that differ are worth resolving -- a handful rather than thousands.

This is the tool that found sixteen matches sitting uncounted on 2026-09-12.
It reports; it never writes a correction. A difference is a place to LOOK.

  python3 scripts/school_reconcile.py                 # every D-I team
  python3 scripts/school_reconcile.py "Air Force" ...  # named teams
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
CUT = os.environ.get("WVB_RECONCILE_CUT", "")


def _s(x):
    if isinstance(x, (tuple, list)):
        return " ".join(str(i) for i in x if i is not None)
    return str(x or "")


def main():
    import verify_results_daily as V
    import season_counts as SC
    from concurrent.futures import ThreadPoolExecutor

    cut = CUT or (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    doc = json.load(io.open(os.path.join(REPO, "data/data_%d.json" % SEASON),
                            encoding="utf-8"))
    name = {t["team_id"]: t.get("name_short") for t in doc["teams"]}
    best = {}
    for l in io.open(os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON),
                     encoding="utf-8"):
        try:
            g = json.loads(l)
        except ValueError:
            continue
        gid = str(g.get("game_id")); prev = best.get(gid)
        if prev is None or g.get("game_state") == "F" or prev.get("game_state") != "F":
            best[gid] = g
    cls = SC.classify(list(best.values()), SEASON)

    def etd(g):
        ep = g.get("start_time_epoch")
        return (datetime.datetime.utcfromtimestamp(ep - 4 * 3600).strftime("%Y-%m-%d")
                if ep else None)

    ours = collections.defaultdict(lambda: collections.defaultdict(list))
    held = collections.defaultdict(lambda: collections.defaultdict(list))
    for gid, g in best.items():
        d = etd(g)
        if not d or d > cut:
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        for i in (0, 1):
            me = name.get(ts[i].get("team_id"))
            opp = name.get(ts[1 - i].get("team_id"))
            if not me:
                continue
            held[me][d].append((gid, opp, cls.get(gid), g.get("game_state")))
            if cls.get(gid) == "ok":
                ours[me][d].append(gid)

    sites = V._sites()
    teams = sys.argv[1:] or sorted(t for t in sites if t in
                                   {x.get("name_short") for x in doc["teams"]})

    def fetch(team):
        base = sites.get(team)
        if not base:
            return team, None
        try:
            rows, _ = V.legacy_txt_rows(base, [], team)
            if rows:
                return team, rows
            for p in V.SPORT_PATHS:
                st, body, _ = V._fetch(base + p)
                if st == 200 and body:
                    r = V.parse_schedule_text(body)
                    if r:
                        return team, r
            # modern templates that render results statically (a label or a
            # visible score row) -- the legacy text export does not exist
            for sport in ("womens-volleyball", "volleyball", "wvball", "wvb"):
                st, body, _ = V._fetch(base + "/sports/%s/schedule" % sport)
                if st == 200 and body:
                    r = V.parse_completed_events(body)
                    if r:
                        return team, r
        except Exception:                                  # noqa: BLE001
            return team, None
        return team, None

    unread, clean, diffs = [], [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for team, rows in ex.map(fetch, teams):
            if not rows:
                unread.append(team); continue
            byd = collections.Counter()
            for r in rows:
                d = _s(r.get("date"))
                if d and d <= cut and _s(r.get("result")).strip():
                    byd[d] += 1
            bad = []
            for d in sorted(set(byd) | set(ours[team])):
                ns, no = byd.get(d, 0), len(ours[team].get(d, []))
                if ns != no:
                    bad.append((d, ns, no, held[team].get(d, [])))
            (diffs if bad else clean).append((team, bad))

    print("reconciled %d teams through %s" % (len(teams), cut))
    print("  agree on every date : %d" % len(clean))
    print("  differ somewhere    : %d" % len(diffs))
    print("  site unreadable     : %d" % len(unread))
    if unread:
        print("    %s" % ", ".join(sorted(unread)[:14]))
    print()
    for team, bad in sorted(diffs):
        print("%s" % team)
        for d, ns, no, rec in bad:
            what = ", ".join("%s(%s/%s)" % (g, c, st) for g, _o, c, st in rec) or "nothing in our log"
            print("   %s  school=%d ours=%d   %s" % (d, ns, no, what))
    return 0


if __name__ == "__main__":
    sys.exit(main())
