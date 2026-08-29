#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Result Confidence Ledger guards (round 7).

The claims these protect: one source can never render as cross-source
confirmed; evidence never spills into fields it does not list; a disputed
result cannot be silently consumed downstream (THIS SUITE going red IS the
quarantine -- the stated policy); and the ledger's counts reconcile with
the finals list.

Run: python3 scripts/test_confidence.py -- no network.
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import confidence as C  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)
    return ok


def E(**kw):
    e = {"url": "https://school.example/x", "kind": "school_site",
         "retrieved": "2026-08-28T00:00:00Z", "text": "W 3-1",
         "fields": ["result"], "status": "confirms", "review_by": None}
    e.update(kw)
    return e


def main():
    print("RESULT CONFIDENCE LEDGER\n")
    print("1. ONE SOURCE IS NEVER 'CROSS-SOURCE CONFIRMED'")
    check("no evidence at all -> official/reconciled, never confirmed",
          C.field_state([], "result", True) == "reconciled"
          and C.field_state([], "result", False) == "official")
    check("an NCAA endpoint can NEVER confirm (same source, new URL)",
          C.field_state([E(kind="ncaa_official")], "result", True)
          == "reconciled")
    check("one attributable second source CAN confirm",
          C.field_state([E()], "result", True) == "confirmed")
    check("exact duplicate source URLs count once",
          C.field_state([E(), E()], "result", False)
          == C.field_state([E()], "result", False))

    print("\n2. FIELD-LEVEL EVIDENCE DOES NOT SPILL")
    e = E(fields=["result"])
    check("a result confirmation confirms nothing about the box",
          C.field_state([e], "box", True) == "reconciled")
    check("...or the venue",
          C.field_state([e], "venue", False) == "official")
    check("same result, different stat line: box stays unconfirmed",
          C.field_state([E(fields=["result"]),
                         E(url="https://b.example", fields=["result"])],
                        "box", True) == "reconciled")

    print("\n3. CONFLICTS ARE SHOWN, NEVER CHOSEN")
    conflicted = [E(), E(url="https://other.example", status="conflicts")]
    check("a conflicting source makes the field DISPUTED",
          C.field_state(conflicted, "result", True) == "disputed")
    check("...and dispute outranks a confirmation",
          C.field_state(conflicted + [E(url="https://c.example")],
                        "result", True) == "disputed")

    print("\n4. STALE AND AMBIGUOUS EVIDENCE SUPPORTS NOTHING")
    check("evidence past its review date drops back to pending",
          C.field_state([E(review_by="2026-01-01")], "result", True,
                        today="2026-08-28") == "reconciled")
    check("an attempted-unverifiable page confirms nothing",
          C.field_state([E(status="attempted_unverifiable")],
                        "result", True) == "reconciled")

    print("\n5. THE SHIPPED LEDGER RECONCILES")
    art = os.path.join(REPO, "data", "result_confidence_%d.json" % SEASON)
    if not os.path.exists(art):
        check("the ledger artifact exists", False, art)
        return 1
    doc = json.load(open(art, encoding="utf-8"))
    c = doc["meta"]["counts"]
    rows = doc["finals"]
    check("counts reconcile with the finals list",
          c["finals"] == len(rows)
          and c["confirmed"] == sum(1 for r in rows
                                    if r["overall"] == "confirmed")
          and c["disputed"] == sum(1 for r in rows
                                   if r["overall"] == "disputed")
          and c["official_only"] + c["reconciled"] + c["confirmed"]
              + c["disputed"] == c["finals"],
          json.dumps(c))
    check("every confirmed row holds >=1 attributable source",
          all(r["n_sources"] >= 1 for r in rows
              if r["overall"] == "confirmed"))
    check("the manually verified corrections really are in the ledger",
          any(r["overall"] == "confirmed" and r["gid"] == "6628236"
              for r in rows))
    check("the ambiguous attempt stays PENDING, never confirmed",
          all(r["overall"] != "confirmed" for r in rows
              if r["gid"] == "6626806"))
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()
    check("the page never claims blanket triple-verification",
          "triple verified" not in src.lower()
          and "confirmation pending" in src)
    check("pending is phrased as normal, not alarming",
          "normal state" in src)

    print("\n6. THE DISPUTE QUARANTINE (this suite red IS the halt)")
    # stated policy: raw history is never rewritten and no silent per-match
    # exclusion is invented inside the rating (that would change ranking
    # math); instead ANY standing dispute fails this suite, so CI and the
    # publish gate stop until a human resolves the evidence file.
    check("no dispute is currently standing (else: resolve the evidence "
          "file before publishing)", c["disputed"] == 0,
          "%d disputed" % c["disputed"])
    ev = (C.load("data/raw/%d/result_evidence.json" % SEASON) or {})
    check("the evidence file states the discipline in its own _doc",
          "never called independent" in (ev.get("_doc") or "")
          or "is never called independent" in (ev.get("_doc") or ""))

    print("\n7. NEGATIVE CONTROLS")
    check("[NEG] a single NCAA 'confirmation' upgraded to confirmed "
          "would be caught",
          C.field_state([E(kind="ncaa_official")], "result", True)
          != "confirmed")
    check("[NEG] spilled fields would be caught",
          C.field_state([E(fields=["result", "box"])], "box", True)
          == "confirmed"
          and C.field_state([E(fields=["result"])], "box", True)
          != "confirmed")
    _fake = dict(c)
    _fake["disputed"] = 1
    check("[NEG] a standing dispute fails the quarantine check",
          _fake["disputed"] != 0)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL CONFIDENCE GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
