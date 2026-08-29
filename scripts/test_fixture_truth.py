#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the canonical fixture record.

⚠ THE FIXTURES BELOW ARE WRITTEN IN THE RAW /game SHAPE, NOT IN THE SHAPE THE
CODE RETURNS. That distinction cost this project a live bug two phases ago: the
Rally Tape read sets as {a,h} objects for two commits because the only test
data was a fixture written to match the code. A fixture authored from the code
under test confirms exactly what it was built to confirm. These are shaped like
data/raw/2026/games.jsonl -- teams[] with is_home, a location block, game_state
-- because that is what the season actually produces.

Python 3.9 target. Run: python3 scripts/test_fixture_truth.py
"""

import copy
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as FX

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


# ── raw-shaped synthetic records ────────────────────────────────────────
def raw(gid, away, home, epoch, state="P", venue=None, city=None, st=None,
        away_home=False):
    r = {"game_id": gid, "game_state": state, "start_time_epoch": epoch,
         "teams": [{"team_id": "A1", "name_short": away, "is_home": away_home},
                   {"team_id": "H1", "name_short": home, "is_home": not away_home}]}
    if venue:
        r["location"] = {"venue": venue, "city": city, "state": st}
    return r


def resolve(records, corr=None):
    """Run the real resolver over synthetic records, without touching disk."""
    real_det = FX._detail_records
    real_ledger = FX.ledger
    real_load = FX._load
    try:
        FX._detail_records = lambda: {records[0]["game_id"]:
                                      [dict(r, _line=i) for i, r in enumerate(records)]}
        # ⚠ RUN SYNTHETIC ENTRIES THROUGH THE REAL VALIDATOR. Stubbing the
        # ledger wholesale meant the provenance rules were never exercised and
        # the negative controls passed for nothing.
        import ledger as LG
        ents = list((corr or {}).values())
        valid = [e for e in ents if not LG.validate_entry(e)]
        # ⚠ THE ENTRY'S OWN game_id IS THERE TO SATISFY THE SCHEMA (which
        # requires a real numeric id) -- the synthetic records under test are
        # keyed "g1".."g9". Map the validated entry onto the record being
        # resolved, so what is exercised is the RULE, not the id.
        gid_under_test = records[0]["game_id"]
        FX.ledger = lambda today=None: {
            "corrections": {gid_under_test: e for e in valid
                            if e.get("kind") == "correction"},
            "conflicts": {}, "stale": {}, "invalid": {}, "entries": valid}
        FX._load = lambda rel: ({"games": []} if "venues_" in rel else None)
        return FX.canonical_fixtures()[records[0]["game_id"]]
    finally:
        FX._detail_records = real_det
        FX.ledger = real_ledger
        FX._load = real_load


EVENING = 1788735600      # 2026-09-06 19:00 ET -- a real announced time
MIDNIGHT = 1788667200     # 2026-09-06 00:00 ET -- the unannounced sentinel
LATER = 1788742800        # 21:00 ET the same night -- a genuine disagreement


def main():
    print("FIXTURE TRUTH\n")

    # ── 1. THE SELECTION RULE ───────────────────────────────────────────
    print("1. THE CANONICAL SELECTION RULE")
    r = resolve([raw("g1", "A", "B", EVENING, venue="Hall", city="X", st="PA"),
                 raw("g1", "A", "B", EVENING, venue="Hall", city="X", st="PA")])
    check("records that agree produce one clean record",
          r["venue"] == "Hall" and not r["conflicts"])

    # ⚠ TWO DIFFERENT START TIMES, BOTH REAL -> a conflict, not a winner.
    r = resolve([raw("g2", "A", "B", EVENING), raw("g2", "A", "B", LATER)])
    check("two genuinely different start times are a CONFLICT",
          any(c["field"] == "start_time_epoch" for c in r["conflicts"]))
    check("[-] ...and the fixture is blocked from a confident render",
          not FX.renderable(r))
    # ⚠ NEGATIVE CONTROL: "last wins" would have silently chosen one.
    check("[NEG] last-wins would have picked one and said nothing",
          r["start_time_epoch"] != LATER,
          "the resolver picked the last record, which is the old behaviour")

    # ⚠ A PLACEHOLDER IS NOT A COMPETING OPINION.
    r = resolve([raw("g3", "A", "B", MIDNIGHT), raw("g3", "A", "B", MIDNIGHT),
                 raw("g3", "A", "B", EVENING)])
    check("an unannounced-time placeholder loses to a real time",
          r["start_time_epoch"] == EVENING and not r["conflicts"],
          str(r["start_time_epoch"]))
    check("[+] ...and the placeholder is still recognised as one",
          FX.is_placeholder_epoch(MIDNIGHT) and
          not FX.is_placeholder_epoch(EVENING))
    r = resolve([raw("g4", "A", "B", MIDNIGHT), raw("g4", "A", "B", MIDNIGHT)])
    check("[-] all-placeholder means the time is NOT announced",
          r["time_unannounced"] is True)

    # ⚠ STATUS CONFLICT, and a FINAL supersedes pregame.
    r = resolve([raw("g5", "A", "B", EVENING, state="P"),
                 raw("g5", "A", "B", EVENING, state="F", venue="Hall")])
    check("a FINAL record supersedes pregame ones", r["completed"] is True)
    check("[-] ...so a completed match is never blocked by pregame disagreement",
          FX.renderable(r))
    r = resolve([raw("g6", "A", "B", EVENING, state="P"),
                 raw("g6", "A", "B", EVENING, state="I")])
    check("two non-final states disagree -> recorded as a conflict",
          any(c["field"] == "game_state" for c in r["conflicts"]))

    # ── 2. THE NEUTRAL-SITE FLIP ────────────────────────────────────────
    print("\n2. THE HOME/AWAY FLIP AT A THIRD-PARTY VENUE")
    flip = [raw("g7", "Nebraska", "UNLV", EVENING, venue="T-Mobile Arena",
                city="Las Vegas", st="NV"),
            raw("g7", "Nebraska", "UNLV", EVENING, venue="T-Mobile Arena",
                city="Las Vegas", st="NV", away_home=True)]
    r = resolve(flip)
    check("a flip across snapshots is detected",
          any(c["field"] == "teams" for c in r["conflicts"]))
    check("[-] ...and the site is UNCONFIRMED, not guessed",
          r["site"] == FX.SITE_UNCONFIRMED, r["site"])
    check("[-] ...so the fixture will not claim a home floor",
          not FX.renderable(r))
    # with an official correction naming the site, the flip stops mattering
    SUP = {"url": "https://example.edu/schedule", "retrieved": "2026-08-26",
           "text": "Neutral Saturday Aug 29 vs. UNLV at T-Mobile Arena"}
    corr = {"g7": {"game_id": "6628315", "kind": "correction",
                   "review_by": "2026-12-01", "fields": {"site": "neutral"},
                   "support": {"site": SUP}}}
    r = resolve(flip, corr)
    check("a sourced neutral site settles it", r["site"] == "neutral")
    check("[-] ...the flip is still RECORDED", any(c["field"] == "teams"
                                                   for c in r["conflicts"]))
    check("[+] ...but no longer blocks, since nothing displayed depends on it",
          FX.renderable(r))

    # ── 3. CORRECTIONS ARE NARROW AND SOURCED ───────────────────────────
    print("\n3. CORRECTIONS WIN ONLY WHERE VERIFIED")
    base = [raw("g8", "Kentucky", "Penn St.", EVENING, venue="Rec Hall",
                city="State College", st="PA")]
    r = resolve(base)
    check("[+] uncorrected, the stale feed venue is what you get",
          r["venue"] == "Rec Hall")
    SUP8 = {"url": "https://gopsusports.com/sports/womens-volleyball/schedule",
            "retrieved": "2026-08-26",
            "text": "Big Ten/SEC Challenge neutral Sep 6 vs. Kentucky Wrigley Field"}
    corr = {"g8": {"game_id": "6626809", "kind": "correction",
                   "review_by": "2026-12-01",
                   "fields": {"site": "neutral", "venue": "Wrigley Field",
                              "city": "Chicago", "state_usps": "IL"},
                   "support": {k: SUP8 for k in
                               ("site", "venue", "city", "state_usps")}}}
    r = resolve(base, corr)
    check("a sourced correction replaces the stale venue",
          r["venue"] == "Wrigley Field" and r["city"] == "Chicago")
    check("[-] ...and only the listed fields are touched",
          r["start_time_epoch"] == EVENING and "start_time_epoch"
          not in r["corrected_fields"])
    # ⚠ PROVENANCE IS PER FIELD NOW, so this checks that each corrected fact
    # carries its OWN url and retrieval date -- the thing the old single-quote
    # entry could not do.
    supp = (r["correction"] or {}).get("support") or {}
    check("the correction's provenance travels PER FIELD",
          set(supp) == set(r["corrected_fields"]) and
          all(v["url"].startswith("https://") and v["retrieved"] == "2026-08-26"
              for v in supp.values()),
          "supported=%s corrected=%s" % (sorted(supp), sorted(r["corrected_fields"])))
    # ⚠ AN ENTRY WITHOUT PROVENANCE IS NOT A CORRECTION. Now expressed against
    # the per-field schema: drop a support key, or a required field on one, and
    # the whole entry must be refused rather than half-applied.
    for label, mangle in (
            ("no support for a corrected field",
             lambda e: e["support"].pop("venue")),
            ("a support entry with no url",
             lambda e: e["support"]["venue"].pop("url")),
            ("a support entry with no retrieval date",
             lambda e: e["support"]["venue"].pop("retrieved")),
            ("a support entry with no quoted text",
             lambda e: e["support"]["venue"].pop("text")),
            ("no review_by", lambda e: e.pop("review_by"))):
        bad = copy.deepcopy(corr)
        mangle(bad["g8"])
        r2 = resolve(base, bad)
        check("[NEG] %-38s -> entry IGNORED" % label,
              r2["venue"] == "Rec Hall", r2["venue"])

    # ── 4. UNKNOWN VENUE ────────────────────────────────────────────────
    print("\n4. AN UNKNOWN VENUE STAYS UNKNOWN")
    r = resolve([raw("g9", "A", "B", EVENING)])
    check("no location in the feed -> no venue asserted", r["venue"] is None)
    check("[-] ...and the site is unconfirmed, never inferred from ordering",
          r["site"] == FX.SITE_UNCONFIRMED)

    # ── 5. THE REAL SEASON ──────────────────────────────────────────────
    print("\n5. THE REAL 2026 RECORD")
    fx = FX.canonical_fixtures()
    check("[+] the audit compares a real corpus", len(fx) > 4000, str(len(fx)))
    multi = [r for r in fx.values() if r["record_count"] > 1]
    check("[+] ...in which duplicates genuinely exist", len(multi) > 500,
          "%d ids with >1 record" % len(multi))
    for gid, want in (("6626809", {"site": "neutral", "venue": "Wrigley Field",
                                   "city": "Chicago",
                                   "event": "Big Ten/SEC Challenge"}),
                      ("6628315", {"site": "neutral",
                                   "venue": "T-Mobile Arena",
                                   "event": "Players Era Showcase"}),
                      ):
        r = fx.get(gid) or {}
        for k, v in want.items():
            check("%s %-8s == %r" % (gid, k, v), r.get(k) == v, repr(r.get(k)))
        check("  %s renders confidently" % gid, FX.renderable(r))
    # ⚠ 6625717 CHANGED CLASS THE MOMENT IT WENT FINAL (2026-08-28). Its
    # venue was never in the feed -- "Petersen Events Center / Opening Spike
    # Classic" came from a cited PREGAME ledger correction, and fixtures.py
    # deliberately withholds pregame schedule corrections once a match is
    # final: where it was going to be played is settled by what happened,
    # and the feed reported nothing. So the pinned expectation above became
    # wrong BY POLICY, not by defect. What must now hold: no venue asserted,
    # and the withholding is stated on the record rather than silent.
    r = fx.get("6625717") or {}
    check("6625717 (final, feed silent): no venue asserted", r.get("venue") is None,
          repr(r.get("venue")))
    check("  ...and the withheld correction says so",
          bool(r.get("correction_withheld")), repr(r.get("correction_withheld")))
    # ⚠ THE LEDGER MOVED AND ITS SCHEMA TIGHTENED. Support is now per FIELD,
    # so this no longer checks "the entry has a url" -- it checks that every
    # single overridden fact carries its own citation. scripts/test_ledger.py
    # owns the schema; this checks the shipped file satisfies it.
    import ledger as LG
    L = LG.load(today="2026-08-27")
    check("the shipped ledger has no invalid entries", not L["invalid"],
          json.dumps(L["invalid"])[:140])
    for gid, c in sorted(L["corrections"].items()):
        fields = set(c.get("fields") or {})
        supported = set(c.get("support") or {})
        check("ledger %s: every corrected fact has its own citation" % gid,
              fields and fields == supported,
              "fields=%s supported=%s" % (sorted(fields), sorted(supported)))
        check("  %s carries a review date no later than first serve" % gid,
              bool(c.get("review_by")))

    # ── 6. THE PAGE AGREES WITH ITSELF ──────────────────────────────────
    print("\n6. NO VIEW DISAGREES WITH ANOTHER")
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  (no built page -- skipping)")
    else:
        h = open(hub, encoding="utf-8").read()
        m = re.search(r"const FIXTURES = (\{.*?\});\n", h, re.S)
        FIX = json.loads(m.group(1)) if m else {}
        check("the page carries the canonical fixture payload", len(FIX) > 1000,
              str(len(FIX)))
        # the match route can reach a fixture far beyond the desk window
        check("[-] a fixture 11 days out is routable", "6626809" in FIX,
              "the Schedule would list a match the match route denies")
        for gid in ("6626809", "6628315", "6625717"):
            a, b = FIX.get(gid) or {}, fx.get(gid) or {}
            same = all(a.get(k) == b.get(k)
                       for k in ("venue", "city", "site", "event"))
            check("%s: page payload == canonical record" % gid, same,
                  "%s vs %s" % (a.get("venue"), b.get("venue")))
        # the fail-closed connector exists on both sides
        # ⚠ DO NOT STRIP /* */ FROM A PYTHON FILE. build_hub.py embeds JS and
        # CSS, so those pairs span unrelated blocks and swallow the Python
        # between them: measured, the strip removed 325,263 of 789,437
        # characters -- 41% of the file -- and took SCHED_INITIAL with it,
        # failing a check about code that was present all along. Read the raw
        # source and choose patterns that cannot occur in prose.
        code = open(os.path.join(REPO, "scripts", "build_hub.py"),
                    encoding="utf-8").read()
        check("one JS connector decides at/vs/v", "function connector(m)" in code)
        check("[-] no view infers 'at' from nominal home ordering",
              "' at ' + mHome" not in code and
              "(m.site === 'neutral' ? 'vs' : 'at')" not in code)
        check("[NEG] the old inference WOULD be caught",
              "(m.site === 'neutral' ? 'vs' : 'at')" not in code,
              "pattern still present")
        check("the schedule says how many of how many it shows",
              "Showing <b>{{N_SHOWN}}</b> of" in code)
        check("[-] ...and no longer claims to be straight from ncaa.com alone",
              "straight from ncaa.com" not in code)
        check("every fixture is emitted, not just the window",
              "SCHED_INITIAL = 600" in code and 'data-beyond="1"' in code)
        check("[-] ...and the emit is no longer capped at 600",
              "for r in sched[:600]:" not in code,
              "the loop still slices the schedule")
        check("a conflicted fixture says so on the page",
              "schedule conflict" in h)

    # ── 7. A BLOCKED FIXTURE LEAKS NOTHING, ANYWHERE ────────────────────
    print("\n7. A BLOCKED FIXTURE NEVER LEAKS A CLAIM IT CANNOT SUPPORT")
    if os.path.exists(hub):
        blocked = {g: r for g, r in fx.items() if FX.blocking_conflicts(r)}
        check("[+] there ARE blocked fixtures to leak", len(blocked) > 5,
              str(len(blocked)))
        # the page payload for a blocked fixture must not carry a confident fact
        leaked = []
        for g, r in blocked.items():
            row = FIX.get(g)
            if not row:
                continue
            fields = {c["field"] for c in FX.blocking_conflicts(r)}
            # ⚠ THE CONNECTOR MUST NOT ASSERT A FLOOR.
            if row.get("site") in ("home", "away", "neutral") and "site" in fields:
                leaked.append("%s site=%s" % (g, row["site"]))
            # ⚠ AND A DISPUTED TIME MUST NOT RENDER AS A TIME.
            if "start_time_epoch" in fields and row.get("t") and \
                    row.get("t") not in ("TBA", "", None) and \
                    not row.get("conflict"):
                leaked.append("%s t=%s" % (g, row["t"]))
        check("no blocked fixture carries a confident site or time",
              not leaked, "; ".join(leaked[:3]))
        # every blocked fixture must actually carry its conflict to the page
        missing = [g for g in blocked if g in FIX and not FIX[g].get("conflict")]
        check("[-] every blocked fixture carries its conflict into the payload",
              not missing, "%d without: %s" % (len(missing), missing[:3]))
        # ⚠ AND THE CONNECTOR IS FAIL-CLOSED IN THE ONE HELPER.
        cjs = re.search(r"function connector\(m\) \{(.*?)\n\}", h, re.S)
        cbody = cjs.group(1) if cjs else ""
        check("connector refuses to assert on a conflict",
              "m.conflict && m.conflict.length" in cbody and
              cbody.index("conflict") < cbody.index("neutral"),
              "conflict must be checked BEFORE site")
        check("[-] ...and returns a non-committal connector",
              "return 'v'" in cbody)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL FIXTURE TRUTH GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
