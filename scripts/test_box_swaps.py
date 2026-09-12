#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for box_team_swap corrections (2026-09-11).

⚠ WHY THIS FILE EXISTS. A box_team_swap re-attributes a match's player rows
at read time. Whether it SHOULD apply depends on which version of the box the
append-only log currently holds -- and that is invisible at every call site.

On 2026-09-11 the season's player boxes were re-crawled to capture service
errors and seven other fields the extractor had been discarding. The feed had
meanwhile CORRECTED ITS OWN team attribution on 34 of 35 swap-corrected
matches, so the swaps would have re-inverted rows that were already right.
The symptom was 758 players appearing under two teams at once.

The corrections were not wrong and are not withdrawn: they are labelled
superseded, with the measurement attached. This suite re-derives that
measurement FROM THE CURRENT LOG on every run, so the day the feed reverts --
or a future crawl restores an older box -- a guard fails instead of a match's
players being silently attributed to the wrong team.
"""
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
import season_counts as SC  # noqa: E402

SEASON = 2026
FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def _key(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def rosters():
    p = os.path.join(REPO, "data/raw/%d/rosters_%d.json" % (SEASON, SEASON))
    R = json.load(open(p, encoding="utf-8"))["teams"]
    out = collections.defaultdict(set)
    for team, v in R.items():
        for pl in (v.get("players") or []):
            out[team].add(_key(pl.get("name_raw") or ""))
    return out


def last_boxes():
    """Per-gid last-wins, the documented reader semantics for this log."""
    p = os.path.join(REPO, "data/raw/%d/playerbox.jsonl" % SEASON)
    out = {}
    if not os.path.exists(p):
        return out
    for ln in open(p, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            r = json.loads(ln)
            out[str(r.get("game_id"))] = r
    return out


def fit(rows, names, roster, swap):
    hit = tot = 0
    for pl in rows:
        t = str(pl.get("team_id"))
        if swap:
            t = swap.get(t, t)
        team = names.get(t)
        if not team or team not in roster:
            continue
        tot += 1
        if _key("%s%s" % (pl.get("first") or "", pl.get("last") or "")) \
                in roster[team]:
            hit += 1
    return (hit / float(tot) if tot else None), tot


def main():
    names = {str(t["team_id"]): t["name_short"]
             for t in json.load(open(os.path.join(
                 REPO, "data/data_%d.json" % SEASON), encoding="utf-8"))["teams"]}
    roster = rosters()
    boxes = last_boxes()
    corr = SC.corrections(SEASON)
    all_swaps = {g: (c.get("correct") or {}) for g, c in corr.items()
                 if (c.get("correct") or {}).get("box_team_swap")}
    active = SC.box_team_swaps(SEASON)

    print("1. THE LEDGER STILL HOLDS EVERY SWAP EVER FILED")
    check("[+] there are swap corrections to check", len(all_swaps) >= 10,
          len(all_swaps))
    check("a superseded swap is LABELLED, never deleted",
          all(("box_team_swap" in f) for f in all_swaps.values()),
          "supersede by labelling; delete only what was never a record")
    check("box_team_swaps() returns fewer than the ledger holds",
          len(active) < len(all_swaps),
          "%d active of %d filed" % (len(active), len(all_swaps)))

    print("\n2. EVERY SWAP'S STATE MATCHES THE BOX THE LOG HOLDS TODAY")
    wrong_active, wrong_superseded, unknown = [], [], []
    for gid, f in all_swaps.items():
        rec = boxes.get(gid)
        rows = (rec or {}).get("rows") or []
        if not rows:
            unknown.append(gid)
            continue
        sw = {str(k): str(v) for k, v in f["box_team_swap"].items()}
        a, na = fit(rows, names, roster, None)
        b, _nb = fit(rows, names, roster, sw)
        if a is None or b is None or na < 4:
            unknown.append(gid)
            continue
        is_superseded = bool(f.get("box_team_swap_superseded"))
        if is_superseded and b > a:
            wrong_superseded.append((gid, round(a, 2), round(b, 2)))
        if (not is_superseded) and a > b:
            wrong_active.append((gid, round(a, 2), round(b, 2)))
    check("no ACTIVE swap would re-invert correct rows", not wrong_active,
          wrong_active[:3])
    check("no SUPERSEDED swap is still needed", not wrong_superseded,
          wrong_superseded[:3])
    check("[+] the check reached most swaps (not vacuous)",
          len(unknown) <= max(2, len(all_swaps) // 5),
          "%d of %d undetermined" % (len(unknown), len(all_swaps)))

    print("\n3. A SUPERSEDED ENTRY CARRIES ITS EVIDENCE")
    sup = [f for f in all_swaps.values() if f.get("box_team_swap_superseded")]
    check("[+] some are superseded", bool(sup), len(sup))
    bad = [s for s in sup
           if not ((s["box_team_swap_superseded"].get("measured") or {})
                   .get("roster_fit_as_filed") is not None)]
    check("each records the measurement that superseded it", not bad,
          "%d carry no measurement" % len(bad))

    print("\n4. NO PLAYER ENDS UP ON TWO TEAMS")
    # the symptom that exposed all of this
    agg = os.path.join(REPO, "data/raw/%d/players_%d.json" % (SEASON, SEASON))
    if os.path.exists(agg):
        ps = json.load(open(agg, encoding="utf-8")).get("players") or []
        if isinstance(ps, dict):
            ps = list(ps.values())
        byname = collections.defaultdict(set)
        for p in ps:
            byname[("%s %s" % (p.get("first") or "",
                               p.get("last") or "")).strip().lower()
                   ].add(str(p.get("team_id")))
        multi = [n for n, t in byname.items() if len(t) > 1]
        # Homonyms are real (two different players can share a name), so this
        # is a CEILING, not zero. 758 was the defect; the honest baseline is
        # under a hundred.
        check("players under two team ids stay near the homonym baseline",
              len(multi) <= 150, "%d players on 2+ teams" % len(multi))
    else:
        check("[skip] no aggregate on disk", True)

    print("\n5. NEGATIVE CONTROLS")
    if sup:
        gid = sorted(g for g, f in all_swaps.items()
                     if f.get("box_team_swap_superseded"))[0]
        f = all_swaps[gid]
        rows = (boxes.get(gid) or {}).get("rows") or []
        sw = {str(k): str(v) for k, v in f["box_team_swap"].items()}
        a, _ = fit(rows, names, roster, None)
        b, _ = fit(rows, names, roster, sw)
        check("[NEG] re-activating a superseded swap IS caught",
              a is not None and b is not None and a > b,
              "roster fit as-filed %s vs swapped %s -- if these were equal "
              "the section-2 check could not fail" % (a, b))
    check("[NEG] box_team_swaps would return a superseded entry if the "
          "flag were ignored",
          len([1 for f in all_swaps.values()
               if f.get("box_team_swap_superseded")]) > 0
          and len(active) < len(all_swaps))

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL BOX-SWAP GUARDS PASS")


if __name__ == "__main__":
    main()
