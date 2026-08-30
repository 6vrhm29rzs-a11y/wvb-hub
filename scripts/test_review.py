#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FINAL VERIFICATION QUEUE — the under-review wall, pinned.

Born from SMU-UC Davis (2026-08-30): the NCAA feed carried the TRUE set
sequence with the TEAMS SWAPPED -- internally coherent, and wrong. Only
an independent official source (SMU's own live-stat result data) exposed
it. The rules pinned here: a feed final is never more than 'official
scoreboard, confirmation pending' on its own; INDEPENDENTLY CONFIRMED
needs a host box/live-stat AND a separately attributable school source;
a conflict is UNDER REVIEW, retained, and counted NOWHERE; NCAA copies
can never be the second source.
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
    import confidence as CF
    import season_counts as SC

    print("1. THE REAL FIXTURE: SMU-UC DAVIS (6626259)")
    ev = json.load(io.open(os.path.join(
        REPO, "data", "raw", "2026", "result_evidence.json"),
        encoding="utf-8"))["evidence"].get("6626259") or []
    conf = [e for e in ev if e.get("status") == "conflicts"]
    check("the SMU live-stat conflict is ledgered with an exact excerpt",
          any(e.get("kind") == "host_livestat"
              and "period_home_score" in (e.get("text") or "")
              and e.get("url", "").startswith("https://smumustangs.com")
              for e in conf))
    check("no correction was written from a single source",
          "6626259" not in SC.corrections(2026))
    check("the gid is under review in the contract",
          "6626259" in SC.review_gids(2026))
    d = json.load(io.open(os.path.join(REPO, "data", "data_2026.json"),
                          encoding="utf-8"))
    cls = SC.classify(d["games"], 2026)
    check("classify() says under_review", cls.get("6626259") == "under_review")

    print("\n2. THE STATE MODEL")
    E = lambda **kw: dict({"status": "confirms", "kind": "school_site",
                           "fields": ["result"], "url": "https://x.edu/a",
                           "review_by": None}, **kw)
    # internally coherent feed final, no independent confirmation
    check("no evidence -> stays at its base (never confirmed)",
          CF.field_state([], "result", "reconciled") == "reconciled")
    # one school schedule row alone: corroborates, does NOT confirm
    check("one school source alone does NOT independently confirm",
          CF.field_state([E()], "result", "reconciled") == "reconciled")
    # host box + separately attributable school source -> confirmed
    check("host box + separate school source -> Independently confirmed",
          CF.field_state([E(kind="host_livestat"),
                          E(url="https://y.edu/b")],
                         "result", "reconciled") == "confirmed")
    # feed-vs-host conflict -> disputed, never silently chosen
    check("a conflict -> disputed, both claims retained upstream",
          CF.field_state([E(status="conflicts", kind="host_livestat")],
                         "result", "reconciled") == "disputed")
    # NCAA copies can never satisfy the two-source requirement
    check("[NEG] NCAA/feed copies never count as sources",
          CF.field_state([E(kind="ncaa_official"),
                          E(kind="ncaa_official", url="https://z.gov/c")],
                         "result", "reconciled") == "reconciled")
    check("[NEG] two school schedules without a box still do not confirm",
          CF.field_state([E(), E(url="https://y.edu/b")],
                         "result", "reconciled") == "reconciled")
    # a stale 'scheduled' page supports nothing: represented by absence --
    # entry_supports refuses attempted_unverifiable
    check("an attempted/unreadable source establishes nothing",
          not CF.entry_supports({"status": "attempted_unverifiable",
                                 "fields": ["result"]}, "result"))

    print("\n3. A DISPUTED RESULT ENTERS NO COUNTED CONSUMER")
    page = io.open(os.path.join(REPO, "Cody", "START-HERE.html"),
                   encoding="utf-8").read()
    T = json.loads(re.search(r"const TEAMS\s*=\s*(.*?);\n", page,
                             re.S).group(1))
    check("SMU's record excludes the disputed match",
          not any(p.get("gid") == "6626259"
                  for p in T["SMU"].get("played") or []))
    check("UC Davis's record excludes it too",
          not any(p.get("gid") == "6626259"
                  for p in T["UC Davis"].get("played") or []))
    CL = re.search(r"const CONFLAB\s*=\s*(.*?);\n", page, re.S).group(1)
    check("Conference Lab excludes it", "6626259" not in CL)
    # the ratings path: countable() refuses it
    elig = SC.countable(d["games"], 2026, need_line=True, d1_only=True)
    check("the rating-eligible set refuses it",
          not any(str(g.get("game_id")) == "6626259" for g in elig))
    # player aggregate
    agg = json.load(io.open(os.path.join(
        REPO, "data", "raw", "2026", "players_2026.json"),
        encoding="utf-8"))
    check("the player aggregate's skip set includes review gids "
          "(mechanism)", "review_gids" in io.open(os.path.join(
              REPO, "scripts", "crawl_2025.py"), encoding="utf-8").read())

    print("\n4. ...WHILE STAYING INSPECTABLE")
    L = json.loads(re.search(r"const LEDGER\s*=\s*(.*?);\n", page,
                             re.S).group(1))
    row = [m for m in L if m.get("gid") == "6626259"]
    check("the Scores ledger still lists it", bool(row))
    check("...in the review state, feed numbers unlabelled as fact",
          row and row[0].get("state") == "review"
          and row[0].get("under_review") is True)
    check("matchRow refuses winner emphasis under review",
          "const urv = !!m.under_review;" in page
          and "aw = !urv && done" in page)
    C = json.load(io.open(os.path.join(
        REPO, "data", "result_confidence_2026.json"), encoding="utf-8"))
    r = [x for x in C["finals"] if x["gid"] == "6626259"][0]
    check("the Result Ledger shows RESULT UNDER REVIEW",
          r["overall"] == "disputed"
          and "RESULT UNDER REVIEW" in page)
    check("field-level evidence stays separate (venue/box unaffected)",
          r["states"]["venue"] != "disputed"
          and r["states"]["box"] != "disputed")

    print("\n5. LABELS")
    check("a raw feed final reads 'Official scoreboard -- independent "
          "confirmation pending'",
          "Official scoreboard \\u00b7 independent confirmation pending"
          in page)
    check("'Independently confirmed' replaced the old confirmed label",
          "Independently confirmed" in page
          and "Cross-source confirmed'" not in page)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL REVIEW GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
