#!/usr/bin/env python3
"""Guards for the attribution-suspicion detector (2026-09-01)."""
import copy
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import attribution_suspicion as A  # noqa: E402

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def main():
    print("1. COMPONENT BEHAVIOUR, SYNTHETIC")
    # feed_record_fit: comparative error, missing -> UNAVAILABLE never PASS
    results = {"1": [(10, "gA", True), (20, "gB", True)],
               "2": [(10, "gA", False), (20, "gC", False)]}
    g = {"start_time_epoch": 30,
         "teams": [{"team_id": "1", "record_at_time": "(0-2)"},
                   {"team_id": "2", "record_at_time": "(2-0)"}]}
    r = A.feed_record_fit(g, results, "gX")
    check("a swapped feed record votes SUPPORTS_H1 with the delta logged",
          r["vote"] == "SUPPORTS_H1" and r["delta_h1_better"] == 8, r)
    g2 = {"start_time_epoch": 30,
          "teams": [{"team_id": "1", "record_at_time": "(2-0)"},
                    {"team_id": "2", "record_at_time": "(0-2)"}]}
    check("a correct feed record votes SUPPORTS_H0",
          A.feed_record_fit(g2, results, "gX")["vote"] == "SUPPORTS_H0")
    g3 = {"start_time_epoch": 30,
          "teams": [{"team_id": "1"}, {"team_id": "2",
                                       "record_at_time": "(2-0)"}]}
    r3 = A.feed_record_fit(g3, results, "gX")
    check("[NEG] a missing feed record is UNAVAILABLE, never a pass",
          r3["vote"] == "UNAVAILABLE" and not r3["available"])

    print("\n2. LEAVE-ONE-OUT -- a corrected game cannot prove its own H1")
    w, l = A.pre_record(results, "1", 25, "gB")
    check("pre_record EXCLUDES the candidate gid",
          (w, l) == (1, 0), (w, l))
    w2, l2 = A.pre_record(results, "1", 25, "none")
    check("...and includes it for any other candidate", (w2, l2) == (2, 0))

    print("\n3. BOX RELIABILITY GATE (stated as a gate, not a truth "
          "threshold)")
    boxes = {"gY": {"rows": [
        {"team_id": "1", "first": "A", "last": "One"},
        {"team_id": "1", "first": "B", "last": "Two"},
        {"team_id": "2", "first": "C", "last": "Three"},
    ]}}
    gY = {"teams": [{"team_id": "1"}, {"team_id": "2"}]}
    rk = {"T1": {"aone", "btwo"}, "T2": {"cthree"}}
    r = A.box_roster_fit("gY", gY, boxes, rk, {"1": "T1", "2": "T2"})
    check("below the reliability floor -> UNAVAILABLE",
          r["vote"] == "UNAVAILABLE" and "reliability" in r.get("why", ""))

    print("\n4. THE KNOWN POSITIVE, PROVED IN PROCESS (SMU-UC Davis)")
    raw, corrected = A.load_corpora()
    results_real = A.team_results(corrected)
    # ⚠ THIS FIXTURE HAS NOW ROTTED TWICE, AND THE SECOND TIME SETTLES THE
    # SHAPE. (1) The feed went back and fixed its own team attribution on
    # SMU-UC Davis (2026-09-11), so the box it serves TODAY is correct and a
    # last-wins read had no inversion left to find. Reading FIRST-wins kept
    # the capability provable -- until (2) the per-gid last-wins MERGE rule
    # for playerbox.jsonl collapsed the game to a single record, which is
    # exactly what that rule is for. The inverted copy is gone and is not
    # coming back.
    # So the detector's capability is no longer proved from a stored artifact
    # at all: the CURRENT box is read, the attribution is swapped IN PROCESS,
    # and the detector must see it. That control cannot rot, because it builds
    # the condition it tests instead of hoping the world still holds one.
    boxes_latest = {}
    with open(os.path.join(A.RAW, "playerbox.jsonl")) as f:
        for line in f:
            try:
                rr = json.loads(line)
            except ValueError:
                continue
            boxes_latest[str(rr.get("game_id"))] = rr        # last wins
    d = json.load(open(os.path.join(REPO, "data", "data_2026.json")))
    id2n = {str(t["team_id"]): t["name_short"] for t in d["teams"]}
    R = json.load(open(os.path.join(A.RAW, "rosters_2026.json")))
    rkeys = {}
    for team, v in (R.get("teams") or {}).items():
        ks = set(A._namekey(p.get("name_raw"))
                 for p in (v.get("players") or []))
        ks.discard("")
        if ks:
            rkeys[team] = ks
    GID = "6626259"
    have = GID in boxes_latest and GID in raw
    if not have:
        check("the SMU-UC Davis box is still held to test against", False,
              "gid %s absent from the raw corpus" % GID)
    else:
        clean = A.box_roster_fit(GID, raw[GID], boxes_latest, rkeys, id2n)
        check("as served TODAY the box matches the filed attribution "
              "(the feed corrected itself)",
              clean["vote"] == "SUPPORTS_H0", clean)
        # POSITIVE CONTROL: swap the two teams' rows and the detector must
        # call it -- this is the inversion the source once served.
        tids = [str(t.get("team_id")) for t in (raw[GID].get("teams") or [])]
        flip = {tids[0]: tids[1], tids[1]: tids[0]} if len(tids) == 2 else {}
        swapped = copy.deepcopy(boxes_latest[GID])
        for row in (swapped.get("rows") or []):
            row["team_id"] = flip.get(str(row.get("team_id")),
                                      row.get("team_id"))
        inverted = A.box_roster_fit(GID, raw[GID], dict(boxes_latest,
                                                        **{GID: swapped}),
                                    rkeys, id2n)
        check("[+] ...and an inverted attribution votes SUPPORTS_H1",
              inverted["vote"] == "SUPPORTS_H1"
              and inverted["fit_gain"] > 0.5, inverted)
        check("[+] ...on the same rows, so the detector is what changed "
              "the verdict",
              clean.get("eligible_rows") == inverted.get("eligible_rows")
              and clean.get("eligible_rows", 0) > 0,
              "%s vs %s" % (clean.get("eligible_rows"),
                            inverted.get("eligible_rows")))

    print("\n5. THE DETECTOR MUTATES NOTHING")
    src = open(os.path.join(REPO, "scripts",
                            "attribution_suspicion.py")).read()
    check("result_corrections.json is never opened by the detector",
          "result_corrections" not in src)
    check("queue entries never overwrite (setdefault-style guard)",
          "if key in q:" in src and '"attribution_suspicion"' in src)
    check("the queue rule states it is a heuristic, not a truth claim",
          "not a truth" in src)
    check("adjudications live in a separate hand file the detector only "
          "READS", "attribution_adjudications" in src and
          "ADJUDICATIONS, {})" in src.replace("_load_json(", "", 0)
          and "open(ADJUDICATIONS, \"w\")" not in src)

    print("\n6. THE ARTIFACT IS A TRAINING TABLE")
    art = json.load(open(A.OUT))
    check("model_version + queue_rule recorded",
          art.get("model_version") and
          "heuristic" in json.dumps(art.get("queue_rule")))
    m0 = art["matches"][0]
    check("per-match components carry votes and measured values",
          "components" in m0 and "n_h1_votes" in m0)
    check("the three hand labels are joined, features not absorbed",
          any(m.get("adjudication") for m in art["matches"]))
    # ⚠ IU-Georgia is labelled live_window_inversion_final_correct: the
    # feed self-corrected at final, so the FINAL-record detector rightly
    # scores it 0 -- only confirmed FINAL-record inversions must vote H1.
    check("confirmed FINAL-record inversions score H1 votes on raw "
          "attribution",
          all(m["n_h1_votes"] >= 1 for m in art["matches"]
              if (m.get("adjudication") or {}).get("label")
              == "confirmed_inversion"))
    check("...and the live-window-only case rightly scores clean",
          all(m["n_h1_votes"] == 0 for m in art["matches"]
              if (m.get("adjudication") or {}).get("label")
              == "live_window_inversion_final_correct"))

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL ATTRIBUTION-SUSPICION GUARDS PASS")


if __name__ == "__main__":
    main()
