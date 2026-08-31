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

    print("1. THE REAL FIXTURE: SMU-UC DAVIS (6626259) -- PROMOTED")
    # the full lifecycle happened on the real match: one official source
    # (SMU live-stat) -> UNDER REVIEW, counted nowhere; then UC Davis's
    # own schedule posted the same set line -> a two-source correction
    # promoted it, and it re-entered every counted surface exactly once.
    ev = json.load(io.open(os.path.join(
        REPO, "data", "raw", "2026", "result_evidence.json"),
        encoding="utf-8"))["evidence"].get("6626259") or []
    conf = [e for e in ev if e.get("status") == "conflicts"]
    check("the SMU live-stat conflict stays ledgered as history",
          any(e.get("kind") == "host_livestat"
              and "period_home_score" in (e.get("text") or "")
              for e in conf))
    corr = SC.corrections(2026).get("6626259") or {}
    check("the correction carries BOTH independent sources",
          len({e.get("url") for e in corr.get("evidence") or []}) >= 2
          and any(e.get("kind") == "host_livestat"
                  for e in corr.get("evidence") or [])
          and any(e.get("school") == "UC Davis"
                  for e in corr.get("evidence") or []))
    check("...and the linescore REPLACEMENT is explicitly flagged",
          (corr.get("correct") or {}).get("linescores_replace") is True)
    check("...and the box-attribution swap is evidenced",
          (corr.get("correct") or {}).get("box_team_swap")
          == {"46036": "46250", "46250": "46036"})
    check("a correction RESOLVES the review (no longer under review)",
          "6626259" not in SC.review_gids(2026))
    d = json.load(io.open(os.path.join(REPO, "data", "data_2026.json"),
                          encoding="utf-8"))
    cls = SC.classify(d["games"], 2026)
    check("classify() says ok -- re-entered the counted universe",
          cls.get("6626259") == "ok")
    g = [x for x in d["games"] if str(x["game_id"]) == "6626259"][0]
    check("the dataset carries SMU 3-2 with the re-attributed line",
          str(g.get("winner_team_id")) == "46250"
          and [(l["visit"], l["home"]) for l in g["linescores"]]
          == [(27, 25), (25, 20), (20, 25), (23, 25), (15, 12)])
    # the promotion path, synthetically: conflict alone -> review; adding
    # a correction -> resolved. Same mechanism the real fixture used.
    real_load = SC._load
    try:
        SC._load = lambda p2: (
            {"evidence": {"888888": [{"status": "conflicts"}]}}
            if "result_evidence" in p2 else
            ({"corrections": {}} if "result_corrections" in p2
             else real_load(p2)))
        check("[SYN] one conflicting source -> under review",
              "888888" in SC.review_gids(2026))
        SC._load = lambda p2: (
            {"evidence": {"888888": [{"status": "conflicts"}]}}
            if "result_evidence" in p2 else
            ({"corrections": {"888888": {"correct": {}}}}
             if "result_corrections" in p2 else real_load(p2)))
        check("[SYN] a later two-source correction promotes it out of "
              "review", "888888" not in SC.review_gids(2026))
    finally:
        SC._load = real_load

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
    smu_e = [p for p in T["SMU"].get("played") or []
             if p.get("gid") == "6626259"]
    check("SMU's record counts it exactly once, as the 3-2 WIN",
          len(smu_e) == 1 and smu_e[0].get("mine") == 3
          and smu_e[0].get("theirs") == 2)
    ucd_e = [p for p in T["UC Davis"].get("played") or []
             if p.get("gid") == "6626259"]
    check("UC Davis counts the mirror loss exactly once",
          len(ucd_e) == 1 and ucd_e[0].get("mine") == 2)
    CL = re.search(r"const CONFLAB\s*=\s*(.*?);\n", page, re.S).group(1)
    check("Conference Lab counts it exactly once",
          CL.count('"6626259"') == 1)
    elig = SC.countable(d["games"], 2026, need_line=True, d1_only=True)
    check("the rating-eligible set includes it exactly once",
          sum(1 for g2 in elig
              if str(g2.get("game_id")) == "6626259") == 1)
    # player aggregate: the swap healed the split rows -- SMU's Beauford
    # sits on ONE team, and no SMU-roster player carries a UC Davis row
    agg = json.load(io.open(os.path.join(
        REPO, "data", "raw", "2026", "players_2026.json"),
        encoding="utf-8"))
    bo = [r2 for r2 in agg["players"]
          if (r2.get("last") or "").lower() == "beauford"]
    check("the box-attribution swap healed the player aggregate "
          "(Beauford on one team, SMU's id)",
          len(bo) == 1 and str(bo[0]["team_id"]) == "46250")
    check("the aggregate's review/swap mechanisms exist (crawl_2025)",
          "box_team_swaps" in io.open(os.path.join(
              REPO, "scripts", "crawl_2025.py"), encoding="utf-8").read())

    print("\n4. ...WHILE STAYING INSPECTABLE")
    L = json.loads(re.search(r"const LEDGER\s*=\s*(.*?);\n", page,
                             re.S).group(1))
    row = [m for m in L if m.get("gid") == "6626259"]
    check("the Scores ledger lists the corrected final",
          bool(row) and row[0].get("state") == "final"
          and row[0].get("as") == 3 and row[0].get("hs") == 2)
    check("matchRow refuses winner emphasis under review",
          "const urv = !!m.under_review;" in page
          and "aw = !urv && done" in page)
    C = json.load(io.open(os.path.join(
        REPO, "data", "result_confidence_2026.json"), encoding="utf-8"))
    r = [x for x in C["finals"] if x["gid"] == "6626259"][0]
    check("the Result Ledger shows Corrected, never merely reconciled",
          r["overall"] == "corrected"
          and r["states"]["result"] == "corrected")
    check("the review mechanics remain on the page for the next dispute",
          "RESULT UNDER REVIEW" in page)
    check("field-level evidence stays separate (venue/box unaffected)",
          r["states"]["venue"] != "corrected"
          or r["states"]["box"] != "corrected")

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
