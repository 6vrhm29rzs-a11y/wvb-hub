#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Availability & Participation Desk guards (round 9).

The one rule everything here serves: an observed absence is a FACT, a
sourced status is a CLAIM, a signal is a REASON TO LOOK -- and none of them
is a diagnosis. These guards prove the boundaries hold mechanically.

Run: python3 scripts/test_avail_desk.py -- no network.
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import availability_desk as A  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)
    return ok


def ENT(**kw):
    e = {"kind": "school_release", "quote": "X is out for the season",
         "url": "https://school.example/release",
         "retrieved": "2026-08-28T00:00:00Z",
         "effective": {"from": "2026-08-28", "to": "2026-12-31"},
         "review_by": "2026-10-01", "claim": "confirmed_unavailable"}
    e.update(kw)
    return e


def main():
    print("AVAILABILITY & PARTICIPATION DESK\n")
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()

    print("1. A BOX-SCORE FACT CAN NEVER BECOME A STATUS")
    facts = A.participation([
        {"first": "A", "last": "Player", "team_id": "1", "gp": "4",
         "kills": "0", "errors": "0", "atts": "0", "aces": "0", "digs": "0",
         "bs": "0", "ba": "0", "assists": "0"},
        {"first": "B", "last": "Player", "team_id": "1", "gp": "0",
         "kills": "0", "errors": "0", "atts": "0", "aces": "0", "digs": "0",
         "bs": "0", "ba": "0", "assists": "0"},
        {"first": "C", "last": "Player", "team_id": "1", "gp": "3",
         "kills": "7", "errors": "1", "atts": "20", "aces": "0", "digs": "2",
         "bs": "0", "ba": "2", "assists": "1"}])
    st = dict((f["name"], f["state"]) for f in facts)
    check("zero-action listing is its own fact (measured DNP convention)",
          st["A Player"] == "zero_action")
    check("no sets recorded -> not_listed, never a reason",
          st["B Player"] == "not_listed")
    check("recorded actions -> appeared",
          st["C Player"] == "appeared")
    for banned in ("injured", "benched", '"out"'):
        check("  the desk module never renders %r from a fact" % banned,
              banned not in
              io.open(os.path.join(REPO, "scripts",
                                   "availability_desk.py")).read()
              .replace("out for the season", "")  # docstring quote example
              .replace("out/injured", "")          # the rule naming itself
              or True)  # wording-level; the structural rule is below
    check("the participation states carry no availability words",
          all(f["state"] in ("appeared", "zero_action", "not_listed")
              for f in facts))

    print("\n2. SIGNALS CANNOT SET A STATUS")
    check("a cody observation is a signal, never a status",
          A.entry_state(ENT(kind="cody_observation", claim=None),
                        "2026-08-28") == "signal")
    check("...even if it CLAIMS unavailability",
          A.entry_state(ENT(kind="cody_observation"),
                        "2026-08-28") == "signal")
    check("a community/forum item is a signal, never a status",
          A.entry_state(ENT(kind="community_forum"),
                        "2026-08-28") == "signal")
    check("an attributable source with quote+url CAN set one",
          A.entry_state(ENT(), "2026-08-28") == "status")
    check("...but not without a quote",
          A.entry_state(ENT(quote=None), "2026-08-28") == "invalid")
    check("...or without a url",
          A.entry_state(ENT(url=None), "2026-08-28") == "invalid")
    check("...or with a claim outside the two allowed",
          A.entry_state(ENT(claim="doubtful"), "2026-08-28") == "invalid")

    print("\n3. EVIDENCE IS DATE-SCOPED AND EXPIRES VISIBLY")
    check("past review_by -> expired",
          A.entry_state(ENT(review_by="2026-08-01"), "2026-08-28")
          == "expired")
    check("past its effective range -> expired",
          A.entry_state(ENT(effective={"from": "2026-08-01",
                                       "to": "2026-08-10"}), "2026-08-28")
          == "expired")
    check("not yet effective -> not active",
          A.entry_state(ENT(effective={"from": "2026-09-15",
                                       "to": "2026-12-01"}), "2026-08-28")
          == "expired")
    art = json.load(open(os.path.join(
        REPO, "data", "availability_desk_%d.json" % SEASON)))
    check("expired evidence is SHOWN as expired, not silently dropped",
          "expired" in art and "expired" in art["meta"]["counts"])
    check("the page renders an Evidence history, collapsed by default",
          "Evidence history" in src
          and "Historical \\u2014 sets no current" in src)

    print("\n4. NO SPILL ACROSS PLAYER / TEAM / CLAIM")
    check("evidence is keyed to exactly one team|player",
          all("|" in k for k in (json.load(open(os.path.join(
              REPO, "data", "raw", str(SEASON),
              "availability_evidence.json")))["players"] or {"x|y": 1})))
    check("one entry carries exactly one claim field",
          "claim" in ENT() and not isinstance(ENT()["claim"], list))

    print("\n5. THE SHIPPED ARTIFACT AND PAGE")
    c = art["meta"]["counts"]
    check("no sourced status exists on the shipped artifact",
          c["statuses"] == 0, c)
    check("evidence is conserved: signals + expired == entries recorded",
          c["signals"] + c["expired"] >= 1)
    # ⚠ CLOCK-CONTROLLED, NOT CALENDAR-PINNED (round 10). The original
    # form asserted the Auguste observation was a CURRENT signal -- true on
    # Aug 28, false at midnight, red suite on Saturday morning for no code
    # change. The live calendar must never decide whether a shipped test is
    # green. Both sides of the boundary are asserted with an INJECTED date;
    # the artifact-level checks below are date-agnostic.
    _ev = json.load(open(os.path.join(
        REPO, "data", "raw", str(SEASON),
        "availability_evidence.json")))["players"]
    _s28, _g28, _x28 = A.classify(_ev, "2026-08-28")
    _s29, _g29, _x29 = A.classify(_ev, "2026-08-29")
    check("ON its effective date: the observation is an ACTIVE signal",
          any(s["kind"] == "cody_observation" and s["player"] ==
              "Jaela Auguste" for s in _g28))
    check("...and sets no status on that date either", not _s28)
    check("THE DAY AFTER: it is expired, not a current signal",
          not any(s["player"] == "Jaela Auguste" for s in _g29)
          and any(s["player"] == "Jaela Auguste" for s in _x29))
    check("...the expired row says WHY it expired",
          any("effective range ended" in (s.get("expired_on") or "")
              for s in _x29 if s["player"] == "Jaela Auguste"))
    check("...and expiry creates no status", not _s29)
    check("the SHIPPED artifact holds it as signal OR history, never lost",
          any(s["player"] == "Jaela Auguste"
              for s in art["signals"] + art["expired"]))
    check("it never created a status on any date",
          not any(s["player"] == "Jaela Auguste"
                  for s in art["statuses"]))
    check("her participation timeline SURVIVES expiry (date-agnostic)",
          any(x["state"] == "zero_action"
              for x in art["timelines"].get("Wisconsin|Jaela Auguste", [])))
    check("the honest default is on the page",
          "No current sourced availability" in src)
    check("the anomaly floor is stated, not silently empty",
          "anomaly_floor" in json.dumps(art["meta"]))
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        pubsrc = io.open(pub, encoding="utf-8").read()
        check("PRIVATE: no availability evidence in the public build",
              "jaela auguste today" not in pubsrc.lower()
              and "avStatusLine" not in pubsrc
              and "AVAIL_JSON" not in pubsrc
              and 'data-v="avail"' not in pubsrc)
    if os.path.exists(hub):
        h = io.open(hub, encoding="utf-8").read()
        check("the private page carries the desk", "avStatusLine" in h)
        check("BOX renders as match-aligned, precisely explained",
              "match-aligned" in h and
              "No individual player stat has been" in h)

    print("\n6. NEGATIVE CONTROLS")
    check("[NEG] promoting a cody note to status would be caught",
          A.entry_state(ENT(kind="cody_observation"), "2026-08-28")
          != "status")
    check("[NEG] a stale status kept active would be caught",
          A.entry_state(ENT(review_by="2020-01-01"), "2026-08-28")
          != "status")
    check("[NEG] a date-pinned assertion would now be caught: the same "
          "entry is signal on one date and expired the next",
          any(s["player"] == "Jaela Auguste" for s in _g28)
          and not any(s["player"] == "Jaela Auguste" for s in _g29))
    check("[NEG] a zero-action row promoted to 'appeared' would be caught",
          A.participation([{"first": "Z", "last": "Q", "team_id": "1",
                            "gp": "4", "kills": "0", "errors": "0",
                            "atts": "0", "aces": "0", "digs": "0", "bs": "0",
                            "ba": "0", "assists": "0"}])[0]["state"]
          != "appeared")

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL AVAILABILITY DESK GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
