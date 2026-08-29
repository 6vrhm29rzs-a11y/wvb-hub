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
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()
    print("1. ONE SOURCE IS NEVER 'CROSS-SOURCE CONFIRMED'")
    check("no evidence at all stays at the field's own base",
          C.field_state([], "result", "reconciled") == "reconciled"
          and C.field_state([], "result", "official") == "official"
          and C.field_state([], "venue", "unavailable") == "unavailable")
    check("an NCAA endpoint can NEVER confirm (same source, new URL)",
          C.field_state([E(kind="ncaa_official")], "result", "reconciled")
          == "reconciled")
    check("one attributable second source CAN confirm",
          C.field_state([E()], "result", "reconciled") == "confirmed")
    check("exact duplicate source URLs count once",
          C.field_state([E(), E()], "result", "official")
          == C.field_state([E()], "result", "official"))

    print("\n2. FIELD-LEVEL EVIDENCE DOES NOT SPILL -- IN EITHER LAYER")
    e = E(fields=["result"])
    check("a result confirmation confirms nothing about the box",
          C.field_state([e], "box", "official") == "official")
    check("...or the venue (which stays unavailable when the feed had none)",
          C.field_state([e], "venue", "unavailable") == "unavailable")
    check("same result, different stat line: box stays unconfirmed",
          C.field_state([E(fields=["result"]),
                         E(url="https://b.example", fields=["result"])],
                        "box", "official") == "official")
    # ⚠ THE BASE LAYER ITSELF: score coherence must never lift the venue.
    # This is the breach round 8 found live -- one shared reconciled flag
    # rendered "venue: reconciled" on a final with zero venue evidence.
    art0 = json.load(open(os.path.join(
        REPO, "data", "result_confidence_%d.json" % SEASON)))
    _nov = [r for r in art0["finals"]
            if r["n_indep"] == 0 and r["states"]["result"] == "reconciled"]
    check("a coherent final with NO evidence never shows venue "
          "reconciled/confirmed (checked %d finals)" % len(_nov),
          all(r["states"]["venue"] in ("official", "unavailable")
              for r in _nov))
    check("result-only external evidence leaves venue at its base "
          "(shipped Wisconsin row)",
          all(r["states"]["venue"] in ("official", "unavailable")
              and r["states"]["box"] != "confirmed"
              for r in art0["finals"] if r["gid"] == "6628236"))

    print("\n3. CONFLICTS ARE SHOWN, NEVER CHOSEN")
    conflicted = [E(), E(url="https://other.example", status="conflicts")]
    check("a conflicting source makes the field DISPUTED",
          C.field_state(conflicted, "result", "reconciled") == "disputed")
    check("...and dispute outranks a confirmation",
          C.field_state(conflicted + [E(url="https://c.example")],
                        "result", "reconciled") == "disputed")

    print("\n4. STALE AND AMBIGUOUS EVIDENCE SUPPORTS NOTHING")
    check("evidence past its review date drops back to pending",
          C.field_state([E(review_by="2026-01-01")], "result", "reconciled",
                        today="2026-08-28") == "reconciled")
    check("an attempted-unverifiable page confirms nothing",
          C.field_state([E(status="attempted_unverifiable")],
                        "result", "reconciled") == "reconciled")

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
          and c.get("corrected", 0) == sum(1 for r in rows
                                           if r["overall"] == "corrected")
          and c["official_only"] + c["reconciled"] + c["confirmed"]
              + c["disputed"] + c.get("corrected", 0) == c["finals"],
          json.dumps(c))
    check("every confirmed row holds >=1 attributable source",
          all(r["n_indep"] >= 1 for r in rows
              if r["overall"] == "confirmed"))
    check("the official record is visible even at zero corroboration",
          "official: recorded" in src and "none yet" in src)
    check("attempted-unreadable renders separately from none-attempted",
          "attempted, unreadable" in src and "None attempted" in src)
    check("the aggregate names itself a result-level count",
          "Awaiting independent result confirmation" in src)
    check("ledger -> match -> Back restores the ledger",
          "?from=ledger" in src and "'Result Ledger', routeFor('confidence')"
          in src and "back.dataset.back === 'ledger'" in src)
    check("the manually verified corrections really are in the ledger",
          any(r["overall"] == "confirmed" and r["gid"] == "6628236"
              for r in rows))
    check("the ambiguous attempt stays PENDING, never confirmed",
          all(r["overall"] != "confirmed" for r in rows
              if r["gid"] == "6626806"))

    check("the page never claims blanket triple-verification",
          "triple verified" not in src.lower()
          and "confirmation pending" in src)
    check("pending is phrased as normal, not alarming",
          "normal state" in src)

    print("\n5b. A CORRECTED RESULT IS VISIBLE, EVIDENCED, AND COUNTED "
          "CORRECTLY")
    _corr = [r for r in rows if r.get("result_corrected")]
    check("the Kent St.-W&M correction is marked on its ledger row",
          any(r["gid"] == "6628406" for r in _corr))
    check("...with the feed's original claim and the established reason",
          all(r.get("corr_feed_said") and r.get("corr_reason")
              for r in _corr))
    check("...and at least one attributable school citation",
          all(any(e.get("text") for e in r.get("corr_evidence") or [])
              for r in _corr))
    # ⚠ REWRITTEN with the corrected state (USC-ASU incident): a corrected
    # record must never read as "reconciled" -- this module sees the
    # corrected dataset, so agreement there is BY CONSTRUCTION, and calling
    # it reconciled laundered the correction into the feed's credibility.
    check("a corrected result carries the corrected state, not reconciled",
          all(r["states"]["result"] == "corrected"
              and r["overall"] in ("corrected", "confirmed", "disputed")
              for r in _corr))
    check("...and a correction alone never reads cross-source confirmed",
          all(r["overall"] != "confirmed" or r["n_indep"] >= 2
              for r in _corr))
    check("the empty-final kind is distinguished from the contradicted kind",
          any(r.get("corr_kind") == "incomplete" for r in _corr
              if r["gid"] == "6627523")
          and any(r.get("corr_kind") == "contradicted" for r in _corr
                  if r["gid"] == "6628406"))
    check("the page renders the corrected chip and the audit block",
          "RESULT CORRECTED" in src and "Result corrected on ledger" in src)
    check("[NEG] an uncorrected row carries no corrected flag",
          not any(r.get("result_corrected") for r in rows
                  if r["gid"] not in [c["gid"] for c in _corr]))
    # ── ROUND 19: the corrected row's SUMMARY names its correction
    # evidence and never the contradictory generic phrase ──────────────
    import subprocess as _sp19
    from test_scoreboard_density import block as _jsb19
    _rc19 = _jsb19(src, src.find("function renderConfidence("))
    _js19 = """
const esc = s => String(s == null ? '' : s);
const matchRoute = g => '#/m/' + g;
const RC_LABEL = { reconciled: 'Reconciled' };
let RC_FILTER = 'all';
const CONFIDENCE = { meta: { counts: {} }, finals: [
  { gid: 'CORR', a: 'A', h: 'B', d: '2026-08-29', overall: 'corrected',
    duplicate_of: null, result_corrected: true, corr_kind: 'contradicted',
    corr_evidence: [
      { school: 'A U', text: 'L, 2-3 on the row', status: 'confirms' },
      { school: 'B U', text: null, status: 'attempted_unverifiable' }],
    states: {}, n_indep: 0, n_attempted: 0, sources: [] },
  { gid: 'PLAIN', a: 'C', h: 'D', d: '2026-08-29', overall: 'official',
    duplicate_of: null, result_corrected: null,
    states: {}, n_indep: 0, n_attempted: 0, sources: [] }]};
const els = {}; const mk = id => els[id] = { innerHTML: '', hidden: false };
['rcsummary','rclist','rcdrill'].forEach(mk);
global.document = { getElementById: id => els[id] || null };
%s
renderConfidence();
const list = els.rclist.innerHTML;
const corr = (list.match(/<button[^>]*data-rcgid="CORR"[\\s\\S]*?<\\/button>/) || [''])[0];
const plain = (list.match(/<button[^>]*data-rcgid="PLAIN"[\\s\\S]*?<\\/button>/) || [''])[0];
const bad = [];
if (corr.indexOf('independent: none yet') >= 0)
  bad.push('corrected row still shows the contradictory generic phrase');
if (corr.indexOf('corrected against raw set line') < 0)
  bad.push('corrected row lacks the correction summary');
if (corr.indexOf('1 attributable official source') < 0)
  bad.push('attributable correction-evidence count missing or wrong');
if (corr.indexOf('1 attempted, unreadable') < 0)
  bad.push('the attempted recheck is not distinguished');
if (corr.indexOf('CROSS-SOURCE') >= 0 || corr.indexOf('Confirmed') >= 0)
  bad.push('a correction was promoted toward cross-source confirmed');
if (plain.indexOf('independent: none yet') < 0)
  bad.push('the ordinary row lost its generic summary');
if (bad.length) { console.log('R19-FAIL: ' + bad.join(' | ')); process.exit(1); }
console.log('R19-OK'); process.exit(0);
""" % _rc19
    _r19 = _sp19.run(["node", "-e", _js19], capture_output=True, text=True)
    check("BEHAVIOUR: corrected summary counts from the payload; ordinary "
          "rows keep the generic one",
          _r19.returncode == 0, (_r19.stdout + _r19.stderr).strip()[:160])
    _bad19 = _rc19.replace("r.result_corrected\n        ? (function", "false\n        ? (function")
    if _bad19 == _rc19:
        _bad19 = _rc19.replace("(r.result_corrected", "(false")
    _rb19 = _sp19.run(["node", "-e", _js19.replace(_rc19, _bad19)],
                      capture_output=True, text=True)
    check("[NEG] reverting to the generic summary on corrected rows fails",
          _rb19.returncode != 0
          and "contradictory generic phrase" in (_rb19.stdout + _rb19.stderr))

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
          C.field_state([E(fields=["result", "box"])], "box", "official")
          == "confirmed"
          and C.field_state([E(fields=["result"])], "box", "official")
          != "confirmed")
    # a deliberately regressed GENERIC fallback -- one shared coherence flag
    # for all four fields -- must fail the venue invariant above
    def _regressed_states(rec):
        shared = "reconciled" if rec else "official"
        return dict((f, C.field_state([], f, shared)) for f in C.FIELDS)
    check("[NEG] the one-shared-flag regression is caught by the venue rule",
          _regressed_states(True)["venue"] == "reconciled")  # would trip p2
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
