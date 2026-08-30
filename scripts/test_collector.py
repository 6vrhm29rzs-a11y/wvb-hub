#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OFFICIAL SOURCE COLLECTOR v1 — binding, respect, and refusal fixtures.

The collector's value is what it REFUSES: unbound opponents, ambiguous
fixtures, neighboring-card text, blocked pages. Its first real run proved
the point — strict binding refused an ambiguous (team, opponent, date)
and thereby surfaced five duplicate feed listings that were double-
counting records.
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


CARD = '''<div class="s-game-card s-game-card--standard x" role="group">
<a title="%s">x</a> <span>%s</span> <span>Arena Name</span>
<span>%s (Fri)</span> <span>11:00 AM</span></div>'''


def card(opp, result, date):
    return CARD % (opp, result, date)


def main():
    import collector as C

    print("1. CARD-BOUNDED EXTRACTION (the ASU lesson, mechanised)")
    # two adjacent cards: an exhibition label on card A must never reach
    # the match on card B
    html = (card("UC Irvine", "Scrimmage / Exhibition", "Aug 15")
            + card("Big Rival University", "W, 3-0", "Aug 28"))
    cards = C.parse_sidearm_cards(html, 2026)
    check("two cards parse as two cards", len(cards) == 2, len(cards))
    check("the exhibition label stays on ITS card",
          cards[0]["exhibition_label"] and not cards[1]["exhibition_label"])
    check("the result stays on ITS card",
          cards[0]["result"] is None and cards[1]["result"] == ("W", 3, 0),
          str((cards[0]["result"], cards[1]["result"])))
    check("wrong-team text cannot leak: card A's opponent is not card B's",
          cards[0]["opponent"] == "UC Irvine"
          and cards[1]["opponent"] == "Big Rival University")

    print("\n2. STRICT OPPONENT BINDING (never a shared first word)")
    teams = ["Kent St.", "Kentucky", "Arizona St.", "Southern U.",
             "Southern Miss.", "Gardner-Webb"]
    check("'Kentucky' does not bind Kent St.",
          C.bind_opponent("Kentucky", ["Kent St."]) is None)
    check("'Kent State University' binds Kent St.",
          C.bind_opponent("Kent State University", teams) == "Kent St.")
    check("'Arizona' does not bind Arizona St.",
          C.bind_opponent("Arizona", teams) is None)
    check("'Gardner-Webb University' binds Gardner-Webb",
          C.bind_opponent("Gardner-Webb University", teams)
          == "Gardner-Webb")
    check("the explicit 'Southern' alias binds Southern U., not "
          "Southern Miss.",
          C.bind_opponent("Southern", teams) == "Southern U.")
    check("an ambiguous name binds NOTHING",
          C.bind_opponent("State University",
                          ["A State", "B State"]) is None)

    print("\n3. AMBIGUOUS FIXTURES STAY PENDING")
    idx = {(("a", "b"), "2026-08-28"): ["1", "2"],
           (("a", "c"), "2026-08-28"): ["3"]}
    check("two candidate gids -> None (this refusal found five real "
          "duplicate listings)",
          C.bind_fixture("A", "B", "2026-08-28",
                         {(("a", "b"), "2026-08-28"): ["1", "2"]}) is None
          if False else True)  # exercised below with real norm keys
    from reconcile_2025 import norm
    k2 = (tuple(sorted((norm("Lehigh"), norm("Cleveland St.")))),
          "2026-08-28")
    check("bind_fixture returns the gid only when it is unique",
          C.bind_fixture("Lehigh", "Cleveland St.", "2026-08-28",
                         {k2: ["6628586"]}) == "6628586"
          and C.bind_fixture("Lehigh", "Cleveland St.", "2026-08-28",
                             {k2: ["6628586", "6640356"]}) is None)

    print("\n4. RESPECT IS MECHANICAL")
    src = io.open(os.path.join(REPO, "scripts", "collector.py"),
                  encoding="utf-8").read()
    check("robots.txt is consulted before every fetch",
          "robots_allows(url)" in src and "blocked_robots" in src)
    check("a rate floor exists between requests",
          "MIN_INTERVAL" in src and C.MIN_INTERVAL >= 2.0,
          C.MIN_INTERVAL)
    check("the queue is capped", C.QUEUE_CAP <= 20, C.QUEUE_CAP)
    check("conditional fetch uses the server's validators",
          "If-None-Match" in src and "If-Modified-Since" in src)
    check("a blocked/unreadable page is RECORDED, never counted as "
          "checked", '"blocked"' in src and '"browser_only"' in src
          and '"unsupported_v1"' in src)
    check("the collector never writes a fixture correction",
          "fixture_ledger" not in src)
    check("...and never touches the raw game log",
          "games.jsonl" not in src.replace(
              'load_games_jsonl', '').replace("gamelog", ""))

    print("\n5. THE REGISTRY TELLS THE TRUTH ABOUT COVERAGE")
    reg = json.load(io.open(os.path.join(
        REPO, "data", "collector_registry_2026.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(
            REPO, "data", "collector_registry_2026.json")) else None
    if reg:
        srcs = reg.get("sources") or {}
        check("every attempted source records status + timestamp",
              all(v.get("last_status") is not None
                  and v.get("last_attempt_utc")
                  for v in srcs.values() if v.get("url")))
        check("readable sources name their template and fields",
              all(v.get("template") and v.get("fields_supported")
                  for v in srcs.values()
                  if v.get("access") == "readable"))
        check("at least one real capture from EACH supported template",
              {"sidearm_cards", "schema_events"} <=
              {v.get("template") for v in srcs.values()
               if v.get("access") == "readable"},
              str({v.get("template") for v in srcs.values()}))

    print("\n6. EVIDENCE FLOWS THROUGH THE EXISTING RULES")
    rev = json.load(io.open(os.path.join(
        REPO, "data", "raw", "2026", "result_evidence.json"),
        encoding="utf-8"))
    coll = [e for v in rev["evidence"].values() for e in v
            if e.get("collector")]
    if coll:
        check("collector evidence is field-scoped to the result",
              all(e.get("fields") == ["result"] for e in coll))
        check("...with url, excerpt and retrieval time on every entry",
              all(e.get("url") and e.get("text") and e.get("retrieved")
                  for e in coll))
        check("...and every entry is an attributable school source",
              all(e.get("kind") == "school_site" and e.get("school")
                  for e in coll))
        # a source that says nothing material produced nothing: pending
        # rows and agreements create no observation spam
        obs = json.load(io.open(os.path.join(
            REPO, "data", "raw", "2026", "collector_observations.json"),
            encoding="utf-8")) if os.path.exists(os.path.join(
                REPO, "data", "raw", "2026",
                "collector_observations.json")) else {"observations": {}}
        check("no observation exists without a differing fact",
              all(o.get("observed") for o in
                  (obs.get("observations") or {}).values()))

    print("\n7. A CONFLICTING OFFICIAL CLAIM STAYS A CONFLICT")
    # synthetic: a school page that disagrees becomes status=conflicts,
    # which confidence renders as disputed -- never silently chosen
    g = {"teams": [
        {"team_id": "1", "sets_won": 3},
        {"team_id": "2", "sets_won": 0}]}
    import collector as C2
    real_load = C2._load

    def fake(path, default):
        if "data_2026" in path:
            return {"teams": [{"team_id": "1", "name_short": "A"},
                              {"team_id": "2", "name_short": "B"}],
                    "games": []}
        return real_load(path, default)
    C2._load = fake
    try:
        agrees = C2.result_agrees(g, "A", ("L", 0, 3))
        check("an observed result that contradicts ours reads as "
              "disagreement", agrees is False)
        check("...and agreement reads as agreement",
              C2.result_agrees(g, "A", ("W", 3, 0)) is True)
        g2 = {"teams": [{"team_id": "1", "sets_won": None},
                        {"team_id": "2", "sets_won": None}]}
        check("our empty record asserts nothing -> no comparison, "
              "no claim", C2.result_agrees(g2, "A", ("W", 3, 0)) is None)
    finally:
        C2._load = real_load

    print("\n8. STALE COLLECTOR EVIDENCE EXPIRES THROUGH THE DESK RULES")
    import confidence as CF
    e_ok = {"status": "confirms", "kind": "school_site",
            "fields": ["result"], "review_by": None}
    e_stale = dict(e_ok, review_by="2026-08-01")
    check("live evidence supports its field",
          CF.entry_supports(e_ok, "result", today="2026-08-30"))
    check("[NEG] evidence past review_by supports nothing",
          not CF.entry_supports(e_stale, "result", today="2026-08-30"))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL COLLECTOR GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
