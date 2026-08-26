#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the Fixture Truth Ledger and the gate that consumes it.

⚠ THE RISK THIS CARRIES. Letting anything stop blocking a weekly freeze is the
one change that can quietly publish a poll with matches missing. So the tests
here are mostly about what must STILL block: an old match with no evidence, a
live match, a date we never observed, an observation taken too early, and an
observation showing the source had not finished with the date.

⚠ NOTHING HERE TOUCHES REAL DATA. Every fixture is synthetic and every
observation is written into a temp directory. The raw logs and the ranking
history are read-only to this suite, and that is asserted at the end.

Python 3.9 target. Run: python3 scripts/test_fixture_disposition.py
"""

import datetime
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)
import weekly as WK            # noqa: E402
import fixture_disposition as FD  # noqa: E402

FAILS = []
SUNDAY = datetime.date(2026, 9, 13)
MONDAY = datetime.date(2026, 9, 14)
TUESDAY = datetime.date(2026, 9, 15)


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def ep(d, hour=19):
    dt = datetime.datetime(d.year, d.month, d.day, hour, 0)
    if WK.ET:
        return int(dt.replace(tzinfo=WK.ET).timestamp())
    return int((dt - datetime.datetime(1970, 1, 1)).total_seconds())


def game(gid, d, state="P", hour=19, div=1):
    return {"game_id": gid, "game_state": state, "start_time_epoch": ep(d, hour),
            "teams": [{"name_short": "A", "division": div},
                      {"name_short": "B", "division": div}]}


def write_obs(root, season, date, listed, observed_utc):
    """A saved scoreboard observation, as the crawler stores one."""
    d = os.path.join(root, "data", "raw", str(season), "scoreboard")
    os.makedirs(d, exist_ok=True)
    json.dump({"updated_at": observed_utc,
               "games": [{"game": {"gameID": gid, "gameState": st}}
                         for gid, st in listed]},
              open(os.path.join(d, "%s.json" % date), "w"))


def main():
    print("FIXTURE TRUTH LEDGER GUARDS\n")
    root = tempfile.mkdtemp(prefix="wvb-fd-")
    # An observation taken well after the Sunday, showing the source finished.
    LATE = "2026-09-14 12:00:00"
    try:
        print("1. A FINAL IS A FINAL")
        r = FD.classify(game("f1", SUNDAY, "F"), MONDAY, 2026, root, {})
        check("a final needs no evidence and is never withdrawn",
              r["disposition"] == "final", str(r))

        print("\n2. WHAT MUST STILL BLOCK")
        # (a) live
        r = FD.classify(game("l1", SUNDAY, "I"), MONDAY, 2026, root, {})
        check("a live match is scheduled_or_live",
              r["disposition"] == "scheduled_or_live", str(r))
        # (b) date not yet passed
        r = FD.classify(game("t1", MONDAY, "P"), MONDAY, 2026, root, {})
        check("a match whose date has not passed is scheduled_or_live",
              r["disposition"] == "scheduled_or_live", str(r))
        # (c) ⚠ OLD, BUT NO OBSERVATION OF ITS DATE -- the whole point.
        r = FD.classify(game("o1", SUNDAY, "P"), TUESDAY, 2026, root, {})
        check("[-] an OLD match with no saved observation stays unknown",
              r["disposition"] == "unknown", str(r))
        check("   ...and says why", "no saved observation" in r["reason"])
        # (d) observation exists but predates the match
        write_obs(root, 2026, SUNDAY.isoformat(), [("zz", "final")],
                  "2026-09-13 10:00:00")
        r = FD.classify(game("o2", SUNDAY, "P", hour=19), TUESDAY, 2026, root, {})
        check("[-] an observation taken BEFORE the match proves nothing",
              r["disposition"] == "unknown", str(r))
        # (e) observation shows the source had not finished with the date
        write_obs(root, 2026, SUNDAY.isoformat(),
                  [("zz", "final"), ("yy", "live")], LATE)
        r = FD.classify(game("o3", SUNDAY, "P"), TUESDAY, 2026, root, {})
        check("[-] a date the source has not finished with proves nothing",
              r["disposition"] == "unknown", str(r))
        check("   ...and says why", "not every listed game was final"
              in r["reason"])
        # (f) still listed, still not final
        write_obs(root, 2026, SUNDAY.isoformat(),
                  [("o4", "final"), ("zz", "final")], LATE)
        r = FD.classify(game("o4", SUNDAY, "P"), TUESDAY, 2026, root, {})
        check("[-] a fixture the source STILL lists is not withdrawn",
              r["disposition"] == "unknown", str(r))

        print("\n3. WHAT MAY STOP BLOCKING")
        write_obs(root, 2026, SUNDAY.isoformat(),
                  [("kept", "final")], LATE)
        r = FD.classify(game("gone", SUNDAY, "P"), TUESDAY, 2026, root, {})
        check("a fixture absent from a finished date IS source_withdrawn",
              r["disposition"] == "source_withdrawn", str(r))
        check("   ...and carries its evidence",
              r.get("evidence", {}).get("all_listed_final") is True
              and r["evidence"].get("observed_utc") == LATE, str(r.get("evidence")))
        check("   ...and records teams, date, state and reason",
              r["teams"] and r["date"] and r["state"] and r["reason"])

        print("\n4. THE GATE USES IT, AND ONLY IT")
        games = [game("f1", SUNDAY, "F"), game("gone", SUNDAY, "P")]
        # Without a ledger, EVERYTHING non-final blocks -- the old behaviour.
        c = WK.completeness(games, SUNDAY, ep(TUESDAY), disposition=None)
        check("[-] with no ledger, a non-final match still blocks",
              c["state"] == "waiting" and not c["publishable"], str(c["state"]))
        c = WK.completeness(games, SUNDAY, ep(TUESDAY),
                            disposition={"gone": "source_withdrawn"})
        check("a withdrawn fixture no longer blocks",
              c["publishable"] is True, str(c))
        check("...and the week is NOT called plainly complete",
              c["state"] == "complete_with_withdrawals", c["state"])
        check("...and it stays visible in the metadata",
              len(c["withdrawn"]) == 1 and c["withdrawn"][0]["why"] == "withdrawn",
              str(c["withdrawn"]))
        check("...while the final is still counted", c["finals"] == 1)
        # An unknown must still block even alongside withdrawals.
        games2 = games + [game("huh", SUNDAY, "P")]
        c = WK.completeness(games2, SUNDAY, ep(TUESDAY),
                            disposition={"gone": "source_withdrawn",
                                         "huh": "unknown"})
        check("[-] one unknown still blocks the whole week",
              not c["publishable"] and c["state"] == "waiting", str(c["state"]))
        check("   ...and is reported as unknown, not stale",
              c["blocking"][0]["why"] == "unknown", str(c["blocking"][:1]))
        # A week with nothing missing is plainly complete.
        c = WK.completeness([game("f1", SUNDAY, "F")], SUNDAY, ep(TUESDAY),
                            disposition={})
        check("a week with no gaps is plainly complete",
              c["state"] == "complete", c["state"])

        print("\n5. MONDAY, EASTERN AND HAWAII ARE UNCHANGED")
        c = WK.completeness([game("s", SUNDAY, "F"), game("m", MONDAY, "F")],
                            SUNDAY, ep(TUESDAY), disposition={})
        check("a finished Monday match is still excluded", c["finals"] == 1)
        c = WK.completeness([game("s", SUNDAY, "F"),
                             game("hi", MONDAY, "F", hour=1)],
                            SUNDAY, ep(TUESDAY), disposition={})
        check("1am-Eastern Monday (7pm Sunday HST) is still next week's",
              c["finals"] == 1)
        check("the cutoff is still Eastern",
              c["cutoff_tz"] == "America/New_York")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n6. THE REAL 39 ARE CLASSIFIED FROM EVIDENCE, NOT ASSUMED")
    led = os.path.join(REPO, "data", "fixture_disposition_2026.json")
    check("the ledger exists", os.path.exists(led))
    if os.path.exists(led):
        doc = json.load(open(led))
        thru = [f for f in doc["fixtures"]
                if f.get("date") and f["date"] <= "2026-08-23"]
        check("[+] there are fixtures through the Aug 23 cutoff to check",
              len(thru) > 0, "%d" % len(thru))
        undecided = [f for f in thru if f["disposition"] == "unknown"]
        print("     (%d non-final through the cutoff; %d unknown)"
              % (len(thru), len(undecided)))
        # ⚠ THIS IS NOT "they must all be withdrawn". If the raw data cannot
        # prove one of them, it stays unknown and keeps blocking -- and this
        # test still passes. What it forbids is a verdict with no evidence.
        for f in thru:
            if f["disposition"] == "source_withdrawn":
                ok = (f.get("evidence", {}).get("all_listed_final") is True
                      and f["evidence"].get("observed_utc")
                      and "does not list this fixture" in f.get("reason", ""))
                if not ok:
                    check("every withdrawal carries its evidence", False,
                          "%s: %s" % (f["game_id"], f.get("evidence")))
                    break
        else:
            check("every withdrawal carries its evidence", True,
                  "%d checked" % len(thru))
        check("no fixture is withdrawn without an observation",
              all(f.get("evidence") for f in thru
                  if f["disposition"] == "source_withdrawn"))
        check("the policy is stamped on the ledger",
              doc.get("policy") == "scoreboard-absence-v1", doc.get("policy"))

    print("\n7. THE LEDGER IS DERIVED -- RAW LOGS ARE NEVER WRITTEN")
    src = open(os.path.join(SCRIPTS, "fixture_disposition.py"),
               encoding="utf-8").read()
    import ast
    tree = ast.parse(src)
    writes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
            if len(node.args) > 1:
                mode = getattr(node.args[1], "s", getattr(node.args[1], "value", ""))
                if isinstance(mode, str) and ("w" in mode or "a" in mode):
                    writes.append(ast.dump(node.args[0])[:60])
    check("[+] it writes exactly one file", len(writes) == 1, str(writes))
    for bad in ("games.jsonl", "playerbox.jsonl", "boxscores.jsonl",
                "rankings_history"):
        check("[-] it never writes %-18s" % bad,
              not any(bad in w for w in writes))
    check("[-] and never removes anything",
          "os.remove" not in src and "shutil.rmtree" not in src
          and "unlink" not in src)

    print("\n8. THE REAL ARCHIVE AND RAW LOGS ARE UNTOUCHED BY TESTS")
    for suite in ("test_weekly_calendar.py", "test_fixture_disposition.py"):
        body = open(os.path.join(SCRIPTS, suite), encoding="utf-8").read()
        check("%s redirects or never writes history" % suite,
              "WVB_HISTORY_OUT" in body or "rankings_history" not in body)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL FIXTURE TRUTH LEDGER GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
