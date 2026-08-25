#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the in-season refresh: what may publish, and what must not.

The refresh runs every half hour during the season. Two things have to be true
or it is worse than the once-a-night job it speeds up:

  1. ONLY A FINAL MAY REACH A DERIVED PAGE. A match in progress is refetched on
     every poll and its score changes each time. If that could trigger a
     publish, the site would show a rating computed from a half-played match --
     and would do it repeatedly, all evening.

  2. NOTHING NEW MUST MEAN NOTHING PUBLISHED. The page embeds a build
     timestamp, so a rebuild produces different bytes on EVERY run whether or
     not a match finished. Without a data-level gate the job would commit ~48
     times a day and fire a Pages deploy for each.

Both reduce to the same rule -- the fingerprint counts finals only -- which is
what these tests pin.

Python 3.9 target. Run: python3 scripts/test_freshness_refresh.py
"""

import datetime
import json
import os
import re
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, ok, detail=""):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def write_games(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def game(gid, state, sets=((25, 20), (25, 18), (25, 22))):
    return {"game_id": gid, "game_state": state,
            "linescores": [{"visit": a, "home": b} for a, b in sets]}


def main():
    print("IN-SEASON REFRESH GUARDS\n")
    import freshness as F
    import crawl_2025 as C

    tmp = tempfile.mkdtemp(prefix="wvb-fresh-")
    real_raw = F.RAW
    F.RAW = tmp
    try:
        gp = os.path.join(tmp, "games.jsonl")

        print("1. Only a FINAL counts -- an in-progress match is invisible")
        write_games(gp, [game("1", "F")])
        base = F.fingerprint()
        write_games(gp, [game("1", "F"), game("2", "I", ((15, 12),))])
        check("adding an IN-PROGRESS match does not move the fingerprint",
              F.fingerprint() == base,
              "a live match would publish a rating built from a half-played game")

        # ...and its score changing on every poll must not either
        write_games(gp, [game("1", "F"), game("2", "I", ((22, 19),))])
        check("...nor does that match's score changing on the next poll",
              F.fingerprint() == base)

        print("\n2. A final DOES move it")
        write_games(gp, [game("1", "F"), game("2", "F", ((25, 21), (25, 19), (25, 17)))])
        after = F.fingerprint()
        check("a newly final match moves the fingerprint", after != base)

        print("\n3. No-op: an unchanged log republishes nothing")
        check("the same data twice gives the same fingerprint",
              F.fingerprint() == after)
        # a rebuilt page differs every minute; the DATA is what is asked
        check("...so the gate is on data, not on the built bytes",
              F.fingerprint() == after)

        print("\n4. A CORRECTION to an already-final match still publishes")
        # ⚠ the count of finals does not move here -- only the score does. A
        # scoring error fixed the next morning must still reach the page.
        write_games(gp, [game("1", "F"), game("2", "F", ((25, 21), (25, 19), (25, 23)))])
        check("a corrected set score republishes", F.fingerprint() != after)

        print("\n5. Append-only: the LAST final record for an id wins")
        write_games(gp, [game("3", "I", ((10, 8),)), game("3", "F", ((25, 10),))])
        one = F.fingerprint()
        write_games(gp, [game("3", "F", ((25, 10),))])
        check("an earlier in-progress line for the same id is ignored",
              F.fingerprint() == one,
              "the append-only log keeps both; only the final may count")
    finally:
        F.RAW = real_raw
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n6. A late-night final is eligible on the following run")
    # ⚠ THE NCAA CALENDAR IS EASTERN AND THIS MACHINE IS PACIFIC. At 10pm PT it
    # is already tomorrow in New York, which is exactly when the late West-coast
    # matches finish. A Pacific "today" would poll the wrong date.
    east = C.eastern_today()
    days = [east + datetime.timedelta(days=1)]
    days += [east - datetime.timedelta(days=i) for i in range(0, 3)]
    days = sorted(set(days))
    check("the poll window includes Eastern today", east in days)
    check("...and yesterday, for a match that finished after midnight ET",
          east - datetime.timedelta(days=1) in days)
    check("...and tomorrow, for a late match already on the next Eastern date",
          east + datetime.timedelta(days=1) in days)
    check("crawl_recent exists and is reachable as a phase",
          hasattr(C, "crawl_recent"))
    src = open(os.path.join(REPO, "scripts", "crawl_2025.py"), encoding="utf-8").read()
    check("the 'recent' phase is wired into the CLI",
          re.search(r'phase == "recent"', src) is not None)
    # NARROWER, NOT WEAKER: it must still consult the same authority rule
    body = src[src.index("def crawl_recent("):src.index("def crawl_schedule(")]
    check("crawl_recent still honours date_needs_refetch",
          "date_needs_refetch" in body,
          "narrowing which dates are offered is fine; skipping the rule is not")

    print("\n7. The refresh workflow publishes only on new data")
    wf = os.path.join(REPO, ".github", "workflows", "refresh.yml")
    if not os.path.exists(wf):
        check("refresh.yml exists", False)
    else:
        y = open(wf, encoding="utf-8").read()
        gated = re.findall(r"if: steps\.after\.outputs\.changed == 'yes'", y)
        check("the publishing steps are gated on a change", len(gated) >= 4,
              "%d gated steps" % len(gated))
        for step in ("Rebuild derived outputs", "Invariant guards",
                     "Commit and publish", "Sanity gate"):
            i = y.find("- name: %s" % step)
            nxt = y.find("- name:", i + 10)
            block = y[i:nxt if nxt > 0 else len(y)]
            check("'%s' cannot run without a change" % step,
                  "steps.after.outputs.changed == 'yes'" in block)
        # ⚠ CHECK THE INVOCATION, NOT THE WORD. The first version searched the
        # whole file for "snapshot_rankings" and failed on the COMMENT that
        # explains snapshot is deliberately excluded. That is the fifth guard in
        # this repository to match its own prose; strip the comments first.
        code = "\n".join(l for l in y.split("\n")
                         if not l.lstrip().startswith("#"))
        check("it never runs snapshot_rankings",
              "snapshot_rankings.py" not in code,
              "the weekly freeze belongs to the daily run")
        check("it never stages a ranking-history row",
              "git add data/rankings_history" not in code)
        # POSITIVE CONTROL: the comment stripper must not eat the real commands
        check("...and the stripper leaves the real commands visible",
              "build_hub.py --public" in code and "crawl_2025.py recent" in code)
        check("it runs the freshness regression test before any network call",
              y.index("test_crawl_freshness") < y.index("crawl_2025.py recent"))
        check("it shares the daily job's concurrency group",
              "group: daily-pipeline" in y,
              "two jobs appending to one game log is how a race corrupts it")
        check("it runs the publishing gate's own guard",
              "test_display_invariants" in y)
        # the private ballot backup must never run in CI
        check("it never touches the private ballot backup",
              "ballot_backup" not in y)

    print("\n8. The daily run keeps the parts the refresh skips")
    d = open(os.path.join(REPO, ".github", "workflows", "daily.yml"),
             encoding="utf-8").read()
    check("the daily job still does the whole-season schedule pass",
          "crawl_2025.py schedule" in d)
    check("the daily job still writes the weekly ranking freeze",
          "snapshot_rankings" in d)
    check("the daily job still runs the fresh-checkout guard",
          "test_pipeline_fresh_checkout" in d)
    check("the daily cron is unchanged (09:15 UTC)", 'cron: "15 9 * * *"' in d)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL REFRESH GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
