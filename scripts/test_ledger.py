#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the official-source ledger and the time-sentinel rule.

⚠ WHAT WENT WRONG THAT THIS PREVENTS. The first ledger accepted an entry with
ONE quote standing behind FIVE independent facts, had no expiry, no schema, and
no way to say "two official sources disagree" -- only "one of them is right".
And the placeholder-time rule was an hour-of-day threshold that classified
Hawaii's genuine 1:00 AM ET starts as unannounced.

Python 3.9 target. Run: python3 scripts/test_ledger.py
"""

import datetime
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger as LG
import fixtures as FX

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def sup(url="https://example.edu/schedule", when="2026-08-26",
        text="Neutral Saturday Aug 29 vs. UNLV T-Mobile Arena"):
    return {"url": url, "retrieved": when, "text": text}


def entry(**kw):
    e = {"game_id": "6628315", "kind": "correction", "review_by": "2026-12-01",
         "fields": {"venue": "T-Mobile Arena"},
         "support": {"venue": sup()}}
    e.update(kw)
    return e


def main():
    print("LEDGER SCHEMA, CONFLICTS, AND THE TIME SENTINEL\n")

    # ── 1. SCHEMA ───────────────────────────────────────────────────────
    print("1. A MALFORMED ENTRY IS REJECTED, NOT SILENTLY ACCEPTED")
    check("[+] a well-formed correction validates", not LG.validate_entry(entry()))
    bad = [
        ("a malformed game id", entry(game_id="abc")),
        ("an unknown kind", entry(kind="hunch")),
        ("a missing review_by", entry(review_by=None)),
        ("a malformed review_by", entry(review_by="26-08-29")),
        ("an unknown overridable field",
         entry(fields={"attendance": 5000}, support={"attendance": sup()})),
        ("a bad site value",
         entry(fields={"site": "roadish"}, support={"site": sup()})),
        ("a malformed state code",
         entry(fields={"state_usps": "Nevada"}, support={"state_usps": sup()})),
        ("a non-https source", entry(support={"venue": sup(url="http://x.edu/s")})),
        ("a relative source url", entry(support={"venue": sup(url="/schedule")})),
        ("a malformed retrieved date", entry(support={"venue": sup(when="2026-8-1")})),
        ("an impossible retrieved date", entry(support={"venue": sup(when="2026-02-30")})),
        ("a too-short quote", entry(support={"venue": sup(text="see site")})),
        # ⚠ THE ONE THIS LEDGER ACTUALLY SHIPPED WITH.
        ("a field with NO support at all",
         entry(fields={"venue": "X", "event": "Y"}, support={"venue": sup()})),
        ("support for a field it does not override",
         entry(support={"venue": sup(), "city": sup()})),
        ("a conflict with only one claim",
         entry(kind="conflict", field="start_time_epoch",
               claims=[{"value": 1, "support": sup()}], fields=None, support=None)),
    ]
    for label, e in bad:
        check("[NEG] %-42s is rejected" % label, bool(LG.validate_entry(e)))

    print("\n1b. THE SHIPPED LEDGER ITSELF IS VALID")
    L = LG.load(today="2026-08-27")
    check("no invalid entries in the real ledger", not L["invalid"],
          json.dumps(L["invalid"])[:160])
    check("[+] ...over a ledger that actually has entries",
          len(L["entries"]) >= 3, str(len(L["entries"])))
    # duplicate detection
    p = os.path.join(REPO, "data/raw/2026/fixture_ledger.json")
    doc = json.load(open(p, encoding="utf-8"))
    dup = {"season": 2026, "entries": doc["entries"] + [doc["entries"][0]]}
    tmp = os.path.join(REPO, ".dup_ledger.json")
    json.dump(dup, open(tmp, "w", encoding="utf-8"))
    try:
        L2 = LG.load(path=tmp, today="2026-08-27")
        check("[NEG] a duplicate (game, kind, field) is rejected",
              any("duplicate" in m for ms in L2["invalid"].values() for m in ms))
    finally:
        os.remove(tmp)

    # ── 2. STALENESS ────────────────────────────────────────────────────
    print("\n2. A SCHEDULE CLAIM IS PERISHABLE")
    fresh = LG.load(today="2026-08-27")
    check("[+] entries apply before their review date",
          "6628315" in fresh["corrections"])
    # ⚠ NEGATIVE CONTROL: THE SAME LEDGER, READ LATER.
    old = LG.load(today="2026-12-31")
    check("[NEG] a stale correction is NOT applied as truth",
          "6628315" not in old["corrections"])
    check("[-] ...and is surfaced as needing review, not dropped",
          "6628315" in old["stale"])

    # ── 3. THE TIME SENTINEL ────────────────────────────────────────────
    print("\n3. THE SENTINEL IS A SENTINEL, NOT AN HOUR RANGE")
    try:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
    except Exception:                                      # noqa: BLE001
        print("  (no zoneinfo -- skipping)")
        ET = None
    if ET:
        def ep(y, m, d, h, mi=0):
            return int(datetime.datetime(y, m, d, h, mi, tzinfo=ET).timestamp())
        cases = [
            ("midnight ET in EDT is the sentinel", ep(2026, 9, 6, 0), True),
            ("midnight ET in EST is the sentinel", ep(2026, 11, 8, 0), True),
            ("DST fall-back day, midnight ET", ep(2026, 11, 1, 0), True),
            ("DST spring-forward day, midnight ET", ep(2026, 3, 8, 0), True),
            # ⚠ THE REAL-EARLY-TIME NEGATIVE CONTROL. 1:00 AM ET is 7:00 PM in
            # Honolulu; 13 such fixtures existed in the completed 2025 season
            # and ALL were at Hawaii. The old hour-threshold called them
            # unannounced.
            ("[NEG] Hawaii's real 1:00 AM ET start is NOT a placeholder",
             ep(2026, 9, 6, 1), False),
            ("[NEG] a real 10:00 AM ET morning start is not either",
             ep(2026, 9, 6, 10), False),
            ("an ordinary 7:00 PM ET evening is not", ep(2026, 9, 6, 19), False),
        ]
        for label, e, want in cases:
            check(label, FX.is_placeholder_epoch(e) == want)
        check("[-] no fixed UTC offset is used for Eastern",
              "timedelta(hours=4)" not in open(
                  os.path.join(REPO, "scripts", "fixtures.py"),
                  encoding="utf-8").read(),
              "EDT-only arithmetic is wrong for half the season")
        check("[+] zoneinfo is what does the conversion",
              'ZoneInfo("America/New_York")' in open(
                  os.path.join(REPO, "scripts", "fixtures.py"),
                  encoding="utf-8").read())

    # ── 4. THE CONFLICT MECHANISM ───────────────────────────────────────
    print("\n4. TWO OFFICIAL SOURCES THAT DISAGREE")
    # a synthetic conflict on the real corpus, applied through the real path
    # ⚠ THE TARGET GID IS CHOSEN AT TEST TIME, NOT PINNED. The first version
    # pinned 6628315 (Nebraska-UNLV) -- and the night that match went FINAL,
    # all five conflict checks failed at once, because conflicts stop
    # applying to a completed match BY DESIGN (a result settles what a
    # schedule page could only claim). A guard pinned to a real fixture
    # inherits that fixture's calendar. Any still-upcoming fixture
    # exercises the identical path.
    _upc = sorted(g for g, r in FX.canonical_fixtures().items()
                  if not r.get("completed") and r.get("start_time_epoch")
                  and not r.get("correction"))
    check("[+] an upcoming fixture exists to host the synthetic conflict",
          bool(_upc), "no upcoming fixtures at all?")
    _cgid = _upc[0] if _upc else "0"
    _cep = FX.canonical_fixtures()[_cgid]["start_time_epoch"] if _upc else 0
    FX_real_venue = (FX.canonical_fixtures()[_cgid].get("venue")
                     if _upc else None)
    conflict = {
        "game_id": _cgid, "kind": "conflict", "field": "start_time_epoch",
        "review_by": "2099-01-01",
        "claims": [
            {"value": int(_cep) + 3600, "support": sup(
                url="https://school-a.example.edu/schedule",
                text="synthetic claim A, one hour later")},
            {"value": int(_cep) + 7200, "support": sup(
                url="https://school-b.example.edu/schedule",
                text="synthetic claim B, two hours later")},
        ],
    }
    check("[+] a well-formed conflict validates",
          not LG.validate_entry(conflict), str(LG.validate_entry(conflict)[:2]))
    tmp = os.path.join(REPO, ".conf_ledger.json")
    json.dump({"season": 2026, "entries": doc["entries"] + [conflict]},
              open(tmp, "w", encoding="utf-8"))
    real_ledger = FX.ledger
    try:
        FX.ledger = lambda today=None: LG.load(path=tmp)
        r = FX.canonical_fixtures()[_cgid]
        check("the conflicted fact is rendered UNAVAILABLE",
              r["start_time_epoch"] is None, str(r["start_time_epoch"]))
        # ⚠ NEGATIVE CONTROL: the NCAA value must NOT quietly win.
        check("[NEG] the NCAA value is not silently preferred",
              r["start_time_epoch"] != 1788048000)
        oc = [c for c in r["conflicts"] if c.get("official_conflict")]
        check("both cited claims are preserved",
              oc and len(oc[0]["claims"]) == 2)
        check("[-] ...each with its own url and retrieval date",
              oc and all(c.get("url", "").startswith("https://")
                         and c.get("retrieved") for c in oc[0]["claims"]))
        check("[-] the fixture is blocked from a confident render",
              not FX.renderable(r))
        # other facts survive -- a conflict is field-scoped. Compared
        # against the fixture's own undisputed venue, not a pinned arena
        # (the pinned "T-Mobile Arena" broke when the host gid went dynamic).
        _venue_before = FX_real_venue
        check("[+] ...while the venue it does NOT dispute survives",
              r["venue"] == _venue_before, "%r vs %r" % (r["venue"],
                                                         _venue_before))
    finally:
        FX.ledger = real_ledger
        os.remove(tmp)

    # ── 5. A FINAL MATCH DOES NOT WEAR A PREGAME CORRECTION ─────────────
    print("\n5. ONCE A MATCH IS FINAL, A SCHEDULE CORRECTION STOPS APPLYING")
    src = open(os.path.join(REPO, "scripts", "fixtures.py"), encoding="utf-8").read()
    check("the resolver withholds pregame corrections on a final",
          'rec["correction_withheld"]' in src)

    # ── 6. THE AUDIT IS READ-ONLY BY DEFAULT ────────────────────────────
    print("\n6. THE AUDIT DOES NOT WRITE UNLESS ASKED")
    art = os.path.join(REPO, "docs", "fixture_conflicts.json")
    before = os.path.getmtime(art) if os.path.exists(art) else 0
    subprocess.call([sys.executable, "scripts/audit_fixtures.py"], cwd=REPO,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    check("[NEG] a default run leaves the tracked artefact untouched",
          os.path.getmtime(art) == before if os.path.exists(art) else True)
    subprocess.call([sys.executable, "scripts/audit_fixtures.py", "--write"],
                    cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    check("[+] ...and --write does refresh it",
          os.path.getmtime(art) > before if os.path.exists(art) else False)

    # ── 7. THE LEDGER LEARNS WHAT THE POLL LEARNS ───────────────────────
    print("\n7. THE LEDGER IS TOLD WHEN LIVE DATA LANDS")
    # ⚠ IT WAS NOT, AND THE SYMPTOM WAS ON SCREEN FOR HOURS. The ledger reads
    # matchState(m, LIVE_BY_ID[m.gid]) and renders ONCE at load -- before the
    # first poll returns -- so with an empty LIVE_BY_ID every match that had
    # finished but not yet been crawled fell into the `upcoming` lane. Two
    # matches that ended hours earlier sat under "STILL TO COME"; a forced
    # re-render changed the heading to "FINAL TODAY 2" immediately.
    # deskLive() already re-rendered the SCOREBOARD for exactly this reason and
    # carried a comment calling it "the one view the poll never told" -- it was
    # not the only one. Same bug, one view across.
    src = open(os.path.join(REPO, "scripts", "build_hub.py"),
               encoding="utf-8").read()
    live_fn = src[src.find("async function deskLive"):]
    live_fn = live_fn[:live_fn.find("\nasync function ", 10)
                      if live_fn.find("\nasync function ", 10) > 0 else 4000]
    check("the poll re-renders the scoreboard",
          "renderScoreboard()" in live_fn)
    check("[+] ...and the ledger too", "renderLedger()" in live_fn,
          "the ledger reads the same live state and must learn with it")
    # only while it is open -- 1,594 rows rebuilt into a collapsed <details>
    # every 60 seconds is work nobody can see
    check("...but only while the ledger is open",
          "_lg.open" in live_fn or ".open &&" in live_fn)
    # and opening it renders, so a ledger opened later is never stale either
    check("opening the ledger renders it",
          "addEventListener('toggle'" in src and "sbfull" in src)

    # --- classification can never ride a fixture correction (USC-ASU) ----
    # The fixture ledger corrects WHERE and WHEN a match happens. Whether it
    # COUNTS is a different fact with its own ledger and its own evidence
    # bar (exhibitions.json + exhibitions.entry_problems). If a field like
    # "exhibition", "counts" or "classification" ever became overridable
    # here, a venue repair could quietly flip a match's competition status,
    # which is the incident of 2026-08-29 rebuilt as a code path.
    import ledger as _ledger_mod
    _banned = ("exhibition", "scrimmage", "counts", "classif", "kind",
               "type", "status")
    _leak = [f for f in _ledger_mod.OVERRIDABLE
             if any(b in f.lower() for b in _banned)]
    check("no classification-like field is overridable in the fixture ledger",
          not _leak, str(_leak))
    check("the overridable set is exactly the where-and-when fields",
          set(_ledger_mod.OVERRIDABLE) == {
              "site", "venue", "city", "state_usps", "event",
              "start_time_epoch"},
          str(sorted(_ledger_mod.OVERRIDABLE)))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL LEDGER GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
