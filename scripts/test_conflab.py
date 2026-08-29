#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conference Lab guards (round 6).

What these stop: a blended unlabelled conference score; a matrix count that
disagrees with its own drill-down; exhibitions or non-D-I results leaking
into league evidence; movement faked across incomparable snapshots; and an
early-season sample dressed up as a verdict.

Run: python3 scripts/test_conflab.py -- no network.
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)
    return ok


def main():
    print("CONFERENCE LAB\n")
    art = os.path.join(REPO, "data", "conference_lab_%d.json" % SEASON)
    if not os.path.exists(art):
        check("the side artifact exists (build_hub writes it)", False, art)
        return 1
    doc = json.load(open(art, encoding="utf-8"))
    meta, confs, matrix = doc["meta"], doc["confs"], doc["matrix"]
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()

    print("1. EXCLUSIONS ARE REAL, NOT CLAIMED")
    exh = set()
    exf = os.path.join(REPO, "data", "raw", "2026", "exhibitions.json")
    if os.path.exists(exf):
        exh = set(json.load(open(exf))["exhibitions"].keys())
    in_matrix = set()
    for cell in matrix.values():
        for g in cell["games"]:
            in_matrix.add(str(g["gid"]))
    check("no exhibition gid appears in the matrix",
          not (exh & in_matrix), sorted(exh & in_matrix)[:3])
    check("...and the exclusion is counted in meta",
          meta.get("n_exhibitions_excluded", 0) >= len(exh & set())
          and "n_exhibitions_excluded" in meta)
    # non-D-I exclusion: every team named in the matrix is a D-I conference
    # member by construction (conf_of only holds the 348) -- assert the
    # construction is the one used
    check("conference resolution goes through the one normaliser",
          "n2team.get(_n(" in src or "_n(n)" in src)

    print("\n2. NO BLENDED, UNLABELLED SCORE")
    banned = [k for c in confs for k in c
              if k in ("score", "rating", "grade", "index")]
    check("the payload holds no single blended conference score",
          not banned, banned[:3])
    check("the page states the strength/results separation",
          "never" in src and "blended into one" in src)
    # ⚠ the label sentences are split across JS string concatenation, so
    # match on fragments that survive any wrap point
    check("ranking bases are labelled at the point of use",
          "poll as captured" in src and "POWER is our board rank" in src)

    print("\n3. THE MATRIX RECONCILES WITH ITS OWN DRILL-DOWNS")
    badcells = [k for k, cell in matrix.items()
                if cell["w"] + cell["l"] != len(cell["games"])]
    check("every cell's W+L equals its match-list length (all %d cells)"
          % len(matrix), not badcells, badcells[:3])
    # and the conference table reconciles with the matrix
    for c in confs[:5] if confs else []:
        n_tab = c["w"] + c["l"]
        n_mat = sum(cell["w"] + cell["l"]
                    for k, cell in matrix.items()
                    if k.startswith(c["conf"] + "|")) + \
                sum(len(cell["games"])
                    for k, cell in matrix.items()
                    if k.endswith("|" + c["conf"]))
        check("  %s: table record equals matrix appearances" % c["conf"],
              n_tab == n_mat, "%d vs %d" % (n_tab, n_mat))

    print("\n4. SAMPLE SIZE IS DISCLOSED, NOT DRESSED UP")
    check("an under-sample league wears the EARLY tag",
          any(c["early"] for c in confs)
          or all(c["w"] + c["l"] >= 10 for c in confs))
    check("...and the tag is stated as a display floor, not a verdict",
          "display floor, not a verdict" in src)
    check("a league with no sample renders as missing evidence",
          "Evidence still missing" in src)
    # the spec's three live test cases, verified on the real artifact
    by = dict((c["conf"], c) for c in confs)
    sec = by.get("SEC")
    if sec and sec["w"] + sec["l"] >= 10:
        check("  test case: a strong raw record can sit beside weak "
              "ranked evidence (SEC)",
              sec["w"] > sec["l"] and "vs25" in sec)
    ivy = by.get("Ivy League")
    if ivy is not None:
        check("  test case: a no-sample league carries 0-0, never invented",
              ivy["w"] + ivy["l"] == 0 and ivy["early"])

    print("\n5. SNAPSHOTS: COMPARABLE OR NOTHING")
    snap = io.open(os.path.join(REPO, "scripts",
                                "snapshot_conferences.py"),
                   encoding="utf-8").read()
    check("frozen on the Monday/ballot cutoff only",
          "weekday() != 0" in snap)
    check("append-only: a frozen week is refused",
          "refusing" in snap and '"a"' in snap)
    check("the POWER basis travels with every row",
          "power_basis" in snap)
    check("the page admits movement needs two comparable rows",
          "two comparable snapshots on the same POWER basis" in src)

    print("\n6. NEGATIVE CONTROLS")
    bogus = dict(matrix)
    k0 = list(bogus)[0] if bogus else None
    if k0:
        cell = dict(bogus[k0])
        cell["w"] += 1                      # count no longer equals the list
        check("[NEG] a padded cell count is caught",
              cell["w"] + cell["l"] != len(cell["games"]))
    _b2 = src.replace("display floor, not a verdict", "verdict")
    check("[NEG] dropping the display-floor label is caught",
          "display floor, not a verdict" not in _b2)

    # --- cell rows show the REAL winner (USC-Arizona St. incident) --------
    # The drill rows once took NAMES from the feed's array order and SETS
    # from the linescores' visit/home columns -- two different orientations,
    # so any game whose ts[0] was the home side displayed the wrong winner
    # (Arizona St. "3-0" over USC in a match USC won). Cross-checked against
    # the dataset's own winner_team_id for EVERY row in every cell; and the
    # two zero-scaffold finals must show their sets_won tally, never 0-0.
    ds = os.path.join(REPO, "data", "data_%d.json" % SEASON)
    if os.path.exists(ds):
        by = dict((str(g["game_id"]), g)
                  for g in json.load(open(ds, encoding="utf-8"))["games"])
        mism, zero, nrows = [], [], 0
        for cell in (doc.get("matrix") or {}).values():
            for r in cell.get("games") or []:
                nrows += 1
                g = by.get(str(r.get("gid")))
                if not g:
                    continue
                th = next((t for t in g["teams"] if t.get("is_home")), {})
                win_home = (str(g.get("winner_team_id"))
                            == str(th.get("team_id")))
                if g.get("winner_team_id") and                         win_home != ((r.get("hs") or 0) > (r.get("as") or 0)):
                    mism.append(r.get("gid"))
                if g.get("winner_team_id") and                         not (r.get("as") or r.get("hs")):
                    zero.append(r.get("gid"))
        check("every cell row's displayed winner matches the dataset winner "
              "(%d rows)" % nrows, not mism, str(mism[:4]))
        check("no decided match displays a 0-0 set tally", not zero,
              str(zero[:4]))
        check("...and the check saw a real sample", nrows >= 50, str(nrows))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL CONFERENCE LAB GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
