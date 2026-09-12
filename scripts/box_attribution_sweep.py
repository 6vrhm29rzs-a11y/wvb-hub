#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Are the PLAYER rows filed under the right team?

⚠ WHY. Twenty result corrections were filed on 2026-09-12, most of them the
same defect: the feed's per-set values right and its TEAM LABELS inverted. A
correction fixes the RESULT. It says nothing about the box score, and the box
feeds player stats, team stats and the ratings. If the feed swapped the teams
on the scoreline it may have swapped them on the player rows too, and every
note on those corrections says the box was not checked.

THE TEST IS THE ONE THAT SETTLED HAMPTON-FIU: reconcile each box row against
the two schools' OWN published rosters. Rows filed under Hampton were 11 of
12 on Hampton's roster and 0 on FIU's -- correctly attributed, so no swap was
applied, and applying one would have re-inverted good data (which is exactly
what happened on 6626259 when the feed silently fixed itself under a standing
swap).

⚠ ABSENCE OF A MATCH IS NOT EVIDENCE OF A SWAP. Roster coverage is
incomplete, players transfer, and the feed's spellings drift, so a row that
matches NEITHER roster is unresolved, never a vote. A swap is claimed only
when rows cross-match the OPPOSITE roster in numbers -- and even then it is
reported, not applied.
"""
import io
import json
import os
import sys
import collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))


def norm_name(first, last):
    import nameclean
    raw = ("%s %s" % (first or "", last or "")).strip()
    try:
        raw = nameclean.clean(raw)
    except Exception:
        pass
    return " ".join(raw.lower().replace(".", "").replace("'", "").split())


def main():
    import season_counts as SC
    rosters = json.load(io.open(os.path.join(
        REPO, "data/raw/%d/rosters_%d.json" % (SEASON, SEASON)), encoding="utf-8"))["teams"]
    by_team = {}
    for tm, v in rosters.items():
        by_team[tm] = {norm_name(p.get("first"), p.get("last"))
                       for p in (v.get("players") or [])}
    teams_doc = json.load(io.open(os.path.join(REPO, "data/data_%d.json" % SEASON),
                                  encoding="utf-8"))["teams"]
    name = {t["team_id"]: t.get("name_short") for t in teams_doc}

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

    boxes = {}
    for l in io.open(os.path.join(REPO, "data/raw/%d/playerbox.jsonl" % SEASON),
                     encoding="utf-8"):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        boxes[str(r.get("game_id"))] = r          # last wins, per the crawl contract

    only = set(sys.argv[1:]) or None
    corr_map = SC.corrections(SEASON)
    corr = set(corr_map)
    swapped = {g for g, e in corr_map.items()
               if (e.get("correct") or {}).get("box_team_swap")
               and not (e.get("correct") or {}).get("box_team_swap_superseded")}
    rows = []
    for gid, box in boxes.items():
        if only and gid not in only:
            continue
        g = best.get(gid)
        if not g:
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        nm = [name.get(t.get("team_id")) for t in ts]
        if not all(nm) or not all(n in by_team for n in nm):
            continue
        tally = collections.defaultdict(lambda: [0, 0, 0])   # filed_id -> [own, other, unresolved]
        for p in (box.get("rows") or []):
            n = norm_name(p.get("first"), p.get("last"))
            fid = p.get("team_id")
            side = 0 if fid == ts[0].get("team_id") else (1 if fid == ts[1].get("team_id") else None)
            if side is None or not n:
                continue
            own, other = by_team[nm[side]], by_team[nm[1 - side]]
            t = tally[side]
            if n in own and n not in other: t[0] += 1
            elif n in other and n not in own: t[1] += 1
            else: t[2] += 1
        own = sum(v[0] for v in tally.values())
        oth = sum(v[1] for v in tally.values())
        unr = sum(v[2] for v in tally.values())
        if own + oth == 0:
            continue                                  # no resolvable rows: no evidence
        rows.append((gid, nm, own, oth, unr, gid in corr))

    suspect = [r for r in rows if r[3] > r[2] and r[0] not in swapped]
    already = [r for r in rows if r[3] > r[2] and r[0] in swapped]
    print("games with a box and both rosters: %d" % len(rows))
    print("  rows matching the team they are FILED under : %d" % sum(r[2] for r in rows))
    print("  rows matching the OPPOSITE team             : %d" % sum(r[3] for r in rows))
    print("  unresolved (neither roster, or on both)     : %d" % sum(r[4] for r in rows))
    if already:
        print("\nalready carrying a box_team_swap -- raw rows inverted BY DESIGN,")
        print("and these confirm the standing swap is still needed:")
        for gid, nm, own, oth, unr, _ in already:
            print("   %-10s %-22s vs %-22s  opposite=%d" % (gid, nm[0], nm[1], oth))
    print("\nBOXES WHERE MORE ROWS FIT THE OPPOSITE ROSTER -- candidate swaps: %d" % len(suspect))
    for gid, nm, own, oth, unr, was_corr in sorted(suspect, key=lambda r: -(r[3] - r[2])):
        print("   %-10s %-22s vs %-22s  own=%-3d opposite=%-3d unresolved=%-3d %s"
              % (gid, nm[0], nm[1], own, oth, unr,
                 "[result corrected]" if was_corr else ""))
    if corr:
        cr = [r for r in rows if r[5]]
        print("\nOF THE %d CORRECTED RESULTS, %d have a checkable box:" % (len(corr), len(cr)))
        for gid, nm, own, oth, unr, _ in sorted(cr):
            verdict = "SWAPPED" if oth > own else "correctly attributed"
            print("   %-10s %-20s vs %-20s own=%-3d opp=%-3d  %s"
                  % (gid, nm[0][:20], nm[1][:20], own, oth, verdict))
    if suspect:
        print("\nFAILED: %d box(es) attributed to the wrong team and not yet "
              "handled. Verify the RESULT against both schools, then file a "
              "correction carrying box_team_swap." % len(suspect))
    return 1 if suspect else 0


if __name__ == "__main__":
    sys.exit(main())
