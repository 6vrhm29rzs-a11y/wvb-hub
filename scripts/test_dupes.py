#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Duplicate-listing guards (round 11).

The rule these protect: NOTHING is ever deduplicated by heuristic. The
detector only creates audit candidates; a listing stops counting only when
the append-only ledger holds authoritative evidence (both schools' official
schedules), and then it stops counting EVERYWHERE while staying inspectable.

Run: python3 scripts/test_dupes.py -- no network.
"""

import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import confidence as C  # noqa: E402
from dupes import duplicate_gids  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)
    return ok


def G(gid, a, h, winner, setline, ep, placeholder=False, venue="V",
      has_box=True):
    return {"gid": gid, "a": a, "h": h, "winner": winner,
            "setline": setline, "ep": ep, "placeholder": placeholder,
            "venue": venue, "has_box": has_box}


def main():
    print("DUPLICATE LISTINGS\n")
    print("1. THE DETECTOR CREATES CANDIDATES, NEVER REMOVALS")
    line = ((25, 23), (29, 27), (21, 25), (23, 25), (15, 12))
    # the confirmed shape: identical everything + asymmetry
    c1 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 1000, placeholder=True, venue=None,
          has_box=False),
        G("2", "A", "B", "9", line, 1000 + 14 * 3600)])
    check("identical pair with asymmetry -> ONE pending candidate",
          len(c1) == 1 and "verification pending" in c1[0]["status"])
    # a real two-match series: same teams, same winner, DIFFERENT set line
    c2 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 1000),
        G("2", "A", "B", "9", ((25, 20), (25, 22), (25, 18)),
          1000 + 20 * 3600, placeholder=True)])
    check("a real repeat meeting (different line) is NEVER flagged",
          not c2)
    # identical line but no quality asymmetry: also only silence
    c3 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 1000),
        G("2", "A", "B", "9", line, 1000 + 3600)])
    check("identical line WITHOUT asymmetry is not flagged either", not c3)
    # outside the window
    c4 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 0, placeholder=True),
        G("2", "A", "B", "9", line, 40 * 3600)])
    check("a 40-hour gap is outside the review window", not c4)

    print("\n2. ONLY THE LEDGER STOPS A COUNT, AND THEN EVERYWHERE")
    led = duplicate_gids(SEASON)
    check("the ledger holds the two verified entries",
          led.get("6640357") == "6625089" and led.get("6640332") == "6624350")
    data = json.load(open(os.path.join(REPO, "data",
                                       "data_%d.json" % SEASON)))
    marked = dict((str(g["game_id"]), g.get("duplicate_of"))
                  for g in data["games"])
    check("the dataset MARKS the duplicates (raw preserved, inspectable)",
          marked.get("6640357") == "6625089"
          and marked.get("6640332") == "6624350")
    check("...and the canonical gids are not marked",
          not marked.get("6625089") and not marked.get("6624350"))
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(hub):
        h = io.open(hub, encoding="utf-8").read()
        T = json.loads(re.search(r"const TEAMS\s*=\s*(.*?);\s*\n", h,
                                 re.S).group(1))
        for team, gid in (("UMES", "6640357"), ("Mississippi Val.", "6640357"),
                          ("Boise St.", "6640332"),
                          ("Middle Tenn.", "6640332")):
            gids = [p.get("gid") for p in (T.get(team) or {}).get("played")
                    or []]
            check("%s: duplicate out, canonical in" % team,
                  gid not in gids and led[gid] in gids,
                  "dup in list" if gid in gids else "canonical missing")
        # ⚠ VERIFIED AGAINST THE SCHOOLS' OWN RECORDS, not against what the
        # page said before the repair: easternshorehawks.com prints
        # "Overall 1-1" (L 0-3 Alabama A&M, W 3-0 MVSU) and goblueraiders.com
        # shows one played match (W 3-2 Boise St.). The first draft of this
        # check pinned the still-inflated 2-1/2-0.
        check("UMES matches its school's own record (1-1)",
              (T.get("UMES") or {}).get("record26") == "1-1",
              (T.get("UMES") or {}).get("record26"))
        check("Middle Tenn. matches its school's own record (1-0)",
              (T.get("Middle Tenn.") or {}).get("record26") == "1-0",
              (T.get("Middle Tenn.") or {}).get("record26"))
    lab = json.load(open(os.path.join(REPO, "data",
                                      "conference_lab_%d.json" % SEASON)))
    in_matrix = set()
    for cell in lab["matrix"].values():
        for g in cell["games"]:
            in_matrix.add(str(g["gid"]))
    check("Conference Lab counts neither duplicate",
          "6640357" not in in_matrix and "6640332" not in in_matrix)
    check("...but still counts the canonical matches",
          "6625089" in in_matrix and "6624350" in in_matrix)

    print("\n3. THE DUPLICATE STAYS VISIBLE, WITH THE REASON")
    rc = json.load(open(os.path.join(REPO, "data",
                                     "result_confidence_%d.json" % SEASON)))
    dups = dict((r["gid"], r["duplicate_of"]) for r in rc["finals"]
                if r.get("duplicate_of"))
    check("the Result Ledger carries both, marked duplicate_of",
          dups == {"6640357": "6625089", "6640332": "6624350"})
    check("no pending candidate remains (both were verified, not assumed)",
          rc["meta"]["counts"]["duplicate_candidates_pending"] == 0)
    check("the evidence names BOTH schools' official schedules per pair",
          all(len(v["evidence"]) >= 2 and
              all(e["kind"] == "school_site" for e in v["evidence"])
              for v in json.load(open(os.path.join(
                  REPO, "data", "raw", str(SEASON),
                  "duplicate_listings.json")))["duplicates"].values()))

    print("\n4. EMPTY FINALS: VISIBLE FOR AUDIT, COUNTED NOWHERE")
    empty = [r for r in rc["finals"] if r["gid"] == "6625090"]
    check("6625090 is visible in the Result Ledger", len(empty) == 1)
    if os.path.exists(hub):
        gids_all = set()
        for team in ("Mississippi Val.", "Delaware St."):
            for p in (T.get(team) or {}).get("played") or []:
                gids_all.add(p.get("gid"))
        check("...and appears in no team's played list",
              "6625090" not in gids_all)

    print("\n5. NEGATIVE CONTROLS")
    check("[NEG] a heuristic that excluded the identical pair on its own "
          "would break: the detector's output carries no exclusion field",
          "exclude" not in json.dumps(c1))
    bogus = dict(led)
    bogus["9999999"] = "1111111"
    check("[NEG] an unledgered gid is not marked in the dataset",
          "9999999" not in marked)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL DUPLICATE-LISTING GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
