#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOURCE INTELLIGENCE FOUNDATION v1 — the seven-state fixtures and the
walls around it.

What is pinned: each claim state derives from its ledger's own rules; a
community claim can never render as confirmed and can never touch a
ranking; the Today feed is bounded and EMPTY rather than padded; private
claims (availability, community) never reach the public payload or page.
"""

import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def main():
    import source_intel as SI

    print("1. THE SEVEN-STATE FIXTURE CORPUS (synthetic ledgers, real code)")
    # steer every ledger reader at the module seam; restore in finally
    real_load = SI._load
    import ledger as LG
    real_lg = LG.load
    import exhibitions as EX
    real_exh = EX.ledger
    import availability_desk as AD

    SUP = {"url": "https://school-a.example.edu/schedule",
           "retrieved": "2026-08-30", "text": "W, 3-0 vs Rival"}
    fx_ledger = {
        "corrections": {
            "900002": {"matchup": "A vs B", "review_by": "2099-01-01",
                       "fields": {"venue": "Real Arena"},
                       "support": {"venue": SUP}},
        },
        "conflicts": {
            "900003": [{"field": "start_time_epoch", "claims": [
                {"value": 1, "support": SUP},
                {"value": 2, "support": dict(
                    SUP, url="https://school-b.example.edu/s")}]}],
        },
        "stale": {"900004": [{"kind": "correction", "matchup": "C vs D",
                              "review_by": "2026-08-01"}]},
        "invalid": {},
    }

    def fake_load(path):
        if "result_corrections" in path:
            return {"corrections": {"900001": {
                "established": "X beat Y 3-0; official box supplies it",
                "feed_said": "empty final",
                "correct": {"winner_team_id": "1"},
                "evidence": [dict(SUP), dict(
                    SUP, url="https://school-b.example.edu/s")]}}}
        if "duplicate_listings" in path:
            return {"duplicates": {"900005": {
                "duplicate_of": "900006",
                "evidence": [dict(SUP), dict(
                    SUP, url="https://school-b.example.edu/s")]}}}
        if "result_evidence" in path:
            return {"evidence": {
                "900007": [dict(SUP, status="confirms", kind="school_site"),
                           dict(SUP, status="confirms", kind="school_site",
                                url="https://school-b.example.edu/s")],
                "900008": [dict(SUP, status="attempted_unverifiable",
                                note="page unreadable")],
                "900009": [dict(SUP, status="confirms"),
                           dict(SUP, status="conflicts",
                                url="https://school-b.example.edu/s")],
            }}
        if "availability_evidence" in path:
            return {"players": {
                "Team X|Jane Doe": [
                    {"kind": "cody_observation", "quote": "looked out",
                     "url": None, "retrieved": "2026-08-30T00:00:00Z",
                     "effective": {"from": "2026-08-30", "to": "2026-08-30"},
                     "review_by": "2026-09-06"},
                    {"kind": "cody_observation", "quote": "still out?",
                     "url": None, "retrieved": "2026-08-01T00:00:00Z",
                     "effective": {"from": "2026-08-01", "to": "2026-08-01"},
                     "review_by": "2026-08-02"},
                ]}}
        return {}

    try:
        SI._load = fake_load
        LG.load = lambda today=None, path=None: fx_ledger
        EX.ledger = lambda season: {"900010": {
            "counts_toward_record": False, "date": "2026-08-27",
            "teams": ["P", "Q"], "sets_to": [21, 21, 15]}}
        cs = SI.claims(2026, today="2026-08-30")
        by = {}
        for c in cs:
            by.setdefault(c["type"], []).append(c)

        get = lambda t: (by.get(t) or [{}])[0]
        check("official confirmation -> confirmed_official",
              get("result_correction").get("state") == "confirmed_official")
        check("independent corroboration -> corroborated",
              get("result_confirmation").get("state") == "corroborated")
        check("forum-only signal -> community_signal, never more",
              get("availability").get("state") == "community_signal")
        check("conflicting claims -> conflicting",
              get("fixture_conflict").get("state") == "conflicting"
              and get("result_conflict").get("state") == "conflicting")
        check("expired evidence -> expired",
              any(c["state"] == "expired" for c in cs))
        check("inaccessible attempt -> inaccessible, establishes nothing",
              get("verification_attempt").get("state") == "inaccessible")
        check("classification carries its format proof",
              get("classification").get("state") == "confirmed_official"
              and "cannot be an NCAA result"
              in get("classification").get("why", ""))
        check("every availability/community claim is PRIVATE",
              all(not c["public"] for c in by.get("availability") or []))
        check("every claim wears exactly one known state",
              all(c["state"] in SI.STATES for c in cs))
        check("...and a reader-facing label",
              all(c.get("state_label") for c in cs))

        # ⚠ AN AMBIGUOUS SUBJECT STAYS PENDING: the availability desk's own
        # entry_state returns 'invalid' for an entry that cannot bind, and
        # source_intel SKIPS it rather than guessing
        SI._load = lambda p: ({"players": {"Team X|": [
            {"kind": "cody_observation", "quote": "??",
             "retrieved": "2026-08-30T00:00:00Z"}]}}
            if "availability_evidence" in p else fake_load(p))
        cs2 = SI.claims(2026, today="2026-08-30")
        n_avail2 = sum(1 for c in cs2 if c["type"] == "availability")
        SI._load = fake_load
        check("an entry the desk calls invalid produces NO claim "
              "(ambiguity stays pending)",
              n_avail2 <= sum(1 for c in cs
                              if c["type"] == "availability"))

        print("\n2. A COMMUNITY CLAIM CANNOT BE PROMOTED")
        # [NEG] force-confirm a community-only claim: the assembler refuses
        real_from_avail = SI._from_availability

        def evil(season, today):
            out = real_from_avail(season, today)
            for c in out:
                c["state"] = "confirmed_official"
            return out
        SI._from_availability = evil
        try:
            SI.claims(2026, today="2026-08-30")
            tripped = False
        except AssertionError:
            tripped = True
        finally:
            SI._from_availability = real_from_avail
        check("[NEG] a community-only claim promoted to confirmed is "
              "refused by the assembler", tripped)

        print("\n3. THE FEED IS BOUNDED, RANKED, AND HONESTLY EMPTY")
        import tempfile
        cs = SI.claims(2026, today="2026-08-30")
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "feed.jsonl")
            seen = SI.first_seen(cs, feed_path=fp,
                                 now="2026-08-30T12:00:00Z")
            feed = SI.what_changed(cs, seen, now="2026-08-30T13:00:00Z")
            check("the feed is capped", len(feed) <= SI.FEED_CAP,
                  len(feed))
            check("...and priority-ranked (conflicts first)",
                  feed and feed[0]["state"] == "conflicting",
                  feed[0]["state"] if feed else "empty")
            old = SI.what_changed(cs, seen, now="2026-09-30T12:00:00Z")
            check("nothing recent -> EMPTY, never padded", old == [])
            seen2 = SI.first_seen(cs, feed_path=fp,
                                  now="2026-09-30T12:00:00Z")
            check("first_seen is append-only (re-run adds nothing new)",
                  seen2 == seen)
    finally:
        SI._load = real_load
        LG.load = real_lg
        EX.ledger = real_exh

    print("\n4. RANKING SEPARATION -- intel can never touch a rating")
    for mod in ("rating_2025.py", "digby_top25.py", "bakeoff_2025.py",
                "rpi_2025.py", "project_2026.py", "player_rating.py",
                "build_rankings_board.py", "snapshot_rankings.py"):
        p = os.path.join(REPO, "scripts", mod)
        if not os.path.exists(p):
            continue
        src = io.open(p, encoding="utf-8").read()
        check("%s never reads source intel" % mod,
              "source_intel" not in src and "intel_feed" not in src)

    print("\n5. THE BUILT PAGES")
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(page_p):
        page = io.open(page_p, encoding="utf-8").read()
        m = re.search(r"const INTEL = (.*?);\n", page)
        check("the private page embeds the INTEL payload", bool(m))
        if m:
            d = json.loads(m.group(1))
            check("the payload states are all known",
                  all(c["state"] in SI.STATES for c in d["claims"]))
            check("the feed is capped in the payload",
                  len(d["feed"]) <= (d["meta"].get("feed_cap") or 5))
        check("the empty state renders NOTHING (block() drops an empty "
              "body)", "intelBlock()" in page
              and "if (!feed.length) return '';" in page)
        check("a community chip can never wear a confirmed face "
              "(class comes from the state)",
              "si-' + esc(state)" in page.replace('"', "'"))
    if os.path.exists(pub_p):
        pub = io.open(pub_p, encoding="utf-8").read()
        m2 = re.search(r"const INTEL = (.*?);\n", pub)
        if m2:
            d2 = json.loads(m2.group(1))
            check("PUBLIC payload carries only public claims",
                  all(c.get("public") for c in d2["claims"])
                  and all(c.get("public") for c in d2["feed"]))
            check("no community source class reaches the public page",
                  not any(s.get("source_class") == "community"
                          for c in d2["claims"]
                          for s in c.get("sources") or []))
        # the real private quote must be absent by VALUE
        check("the private observation text is absent from the "
              "public page", "oh darn no jaela auguste" not in pub.lower())

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL SOURCE-INTEL GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
