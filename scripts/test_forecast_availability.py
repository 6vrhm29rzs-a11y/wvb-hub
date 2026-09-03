#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE AVAILABILITY-FORECAST CONTRACT (audit, 2026-09-01).

Availability is NOT an input to any forecast, probability, power
rating or projection -- so every surface rendering one carries the
disclosure, discoverable from the number itself, and no producer can
quietly grow an availability read. docs/forecast_availability_audit_
2026-09-01.md is the map this enforces.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

FAILS = []
NOTE = "Forecast does not incorporate availability."


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


PRODUCERS = ("predict_2026.py", "simulate_season_2026.py",
             "simulate_2025.py", "rating_2025.py", "bakeoff_2025.py",
             "digby_top25.py", "project_2026.py", "project_field.py",
             "build_rankings_board.py", "resume_2025.py", "rpi_2025.py",
             "score_predictions.py")
BANNED = ("availability", "participation", "AVAIL")


def main():
    print("1. NO PRODUCER READS AVAILABILITY (structural)")
    for mod in PRODUCERS:
        p = os.path.join(REPO, "scripts", mod)
        if not os.path.exists(p):
            continue
        src = io.open(p, encoding="utf-8").read()
        hits = [b for b in BANNED if b in src]
        check("%s is availability-free" % mod, not hits, hits)
    # [NEG] the scan itself can fail
    check("[NEG] an injected availability read would be caught",
          any(b in "import availability_desk" for b in BANNED))

    print("\n2. BEHAVIORAL: predictions are IDENTICAL without the "
          "evidence file")
    ev = os.path.join(REPO, "data/raw/2026/availability_evidence.json")
    pred = os.path.join(REPO, "data/predictions_2026.json")
    env = dict(os.environ, WVB_SEASON="2026")

    def run_predict():
        subprocess.run([sys.executable,
                        os.path.join(REPO, "scripts/predict_2026.py")],
                       env=env, capture_output=True, timeout=300)
        d = json.load(io.open(pred, encoding="utf-8"))
        # compare the probabilities only -- a generated_at stamp may move
        return {str(g.get("game_id")): g.get("home_win")
                for g in d.get("games") or []}

    base = run_predict()
    moved = ev + ".audit_bak"
    try:
        shutil.move(ev, moved)
        without = run_predict()
    finally:
        shutil.move(moved, ev)
        run_predict()                       # restore the real artifact
    check("every fixture probability is byte-equal with the evidence "
          "file ABSENT (%d fixtures)" % len(base),
          base == without and len(base) > 100)

    print("\n3. THE DISCLOSURE, ON EVERY SURFACE")
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    page = io.open(page_p, encoding="utf-8").read()
    check("one definition: the JS const is substituted from python",
          "const FORECAST_NOTE = \"%s\"" % NOTE in page
          or "const FORECAST_NOTE = %s" % json.dumps(NOTE) in page)
    # literal text sites + JS sites that render through the const
    n = page.count(NOTE) + page.count("FORECAST_NOTE")
    check("the sentence reaches the surfaces (%d literal+const sites "
          ">= 8)" % n, n >= 8, n)
    for frag, label in (
            ("pre-match pick for this fixture. ' + FORECAST_NOTE",
             "dossier next-match pick title"),
            ("pre-match pick. ' + FORECAST_NOTE", "fixtures-list pick"),
            ("class=\"dfc\" title=\"' + FORECAST_NOTE",
             "Today forecast card"),
            ("munk fcavail", "match-detail forecast section"),
            ("backtested at 42 of the real 64 from a preseason prior. "
             "Forecast does not incorporate availability.",
             "Tourn column header"),
            ("Sourced availability is not an input.",
             "POWER ruler tooltip"),
            ("changes\n  nothing in this projection", "bracket lead"),
            ("Availability is not an input.</b> Neither POWER",
             "rankings methodology")):
        check("disclosure: %s" % label, frag in page, frag[:40])
    check("the dossier Outlook states no number changes",
          "changes no Power number" in page.replace("\n", " ")
          or "changes no Power" in page)

    print("\n4. THE TEXAS TRACE + CONTROLS (numeric agreement)")
    m = re.search(r"const TEAMS = (\{.*?\});\n", page, re.S)
    teams = json.loads(m.group(1).replace("<\\/", "</")) if m else {}
    tx = teams.get("Texas") or {}
    fx = [f for f in (tx.get("fixtures") or [])
          if f.get("pick") is not None]
    check("Texas renders a pick beside a current sourced status",
          bool(fx) and bool(tx.get("digby_avail_withheld")))
    if fx:
        gid = str(fx[0].get("gid"))
        check("...and the rendered pick equals the predictions file "
              "(payload rounds to 3dp) for gid %s" % gid,
              gid in base and any(abs(fx[0]["pick"] - round(v, 3)) < 1e-9
                                  for v in (base[gid], 1 - base[gid])),
              (fx[0]["pick"], base.get(gid)))
    pu = teams.get("Purdue") or {}
    pfx = [f for f in (pu.get("fixtures") or [])
           if f.get("pick") is not None]
    if pfx:
        pgid = str(pfx[0].get("gid"))
        check("Purdue control: the pick beside an unavailable status is "
              "the predictions value, untouched",
              pgid in base and any(
                  abs(pfx[0]["pick"] - round(v, 3)) < 1e-9
                  for v in (base[pgid], 1 - base[pgid])),
              (pfx[0].get("pick"), base.get(pgid)))
    # status vs incident never conflated on the forecast side either:
    # the projection is the ONLY availability surface, and neither state
    # reaches base (proven in section 2); assert the two states remain
    # distinct in the canonical projection
    import availability_desk as AD
    proj = {(c["team"], c["player"]): c["state"] for c in AD.projection()}
    # ⚠ STATE-CONDITIONAL (2026-09-02): Heaney's incident RESOLVED at her
    # box-verified return, so she has no current card -- pinning her as a
    # live incident is the calendar-pin class. Wollard's status is the
    # standing control; Heaney's expectation follows the evidence file.
    _hev = json.load(open(os.path.join(
        REPO, "data", "raw", "2026",
        "availability_evidence.json")))["players"]["Purdue|Grace Heaney"]
    _hopen = not any((e.get("effective") or {}).get("to")
                     for e in _hev if e.get("claim") == "match_incident")
    check("controls stay distinct: Wollard status%s" %
          (", Heaney incident" if _hopen else "; Heaney resolved, no card"),
          proj.get(("Purdue", "Kenna Wollard")) == "status"
          and (proj.get(("Purdue", "Grace Heaney")) == "incident"
               if _hopen else
               ("Purdue", "Grace Heaney") not in proj))

    print("\n5. PUBLIC FENCES")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub_p):
        pub = io.open(pub_p, encoding="utf-8").read()
        check("the disclosure ships publicly too (it is about the "
              "model, not the private desk)", NOTE in pub)
        check("...without naming the private desk beside it",
              "Availability Desk" not in pub)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("THE AVAILABILITY-FORECAST CONTRACT HOLDS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
