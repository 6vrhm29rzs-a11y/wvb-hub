#!/usr/bin/env python3
"""Guards for the attribution-suspicion detector (2026-09-01)."""
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

    print("\n4. THE REAL KNOWN POSITIVE (SMU-UC Davis, from committed raw)")
    raw, corrected = A.load_corpora()
    results_real = A.team_results(corrected)
    boxes_real = {}
    with open(os.path.join(A.RAW, "playerbox.jsonl")) as f:
        for line in f:
            try:
                rr = json.loads(line)
                boxes_real[str(rr.get("game_id"))] = rr
            except ValueError:
                continue
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
    smu = A.box_roster_fit("6626259", raw["6626259"], boxes_real, rkeys,
                           id2n)
    check("SMU-UC Davis box rows vote SUPPORTS_H1 on the RAW attribution",
          smu["vote"] == "SUPPORTS_H1" and smu["fit_gain"] > 0.5, smu)

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
