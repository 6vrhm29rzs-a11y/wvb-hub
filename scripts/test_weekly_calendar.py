#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the weekly ranking calendar.

The cutoff policy is stated in scripts/weekly.py and implemented once. These
tests hold it to that statement using SYNTHETIC games, so they do not drift
with the live season and cannot touch the real archive.

⚠ EVERY WRITE PATH HERE IS REDIRECTED. `rankings_history_*.jsonl` is the one
artifact in this repo that cannot be rebuilt and is append-only; a test that
writes into it has damaged the record. I did that once by running --force while
developing and had to restore from git. WVB_HISTORY_OUT points at a temp file.

Python 3.9 target. Run: python3 scripts/test_weekly_calendar.py
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)
import weekly as WK  # noqa: E402

FAILS = []
# A Sunday, and the Monday after it. Fixed, so the tests never depend on today.
SUNDAY = datetime.date(2026, 9, 13)
MONDAY = datetime.date(2026, 9, 14)


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def ep(d, hour=19):
    """Epoch for a match at `hour` EASTERN on date `d`."""
    dt = datetime.datetime(d.year, d.month, d.day, hour, 0)
    if WK.ET:
        dt = dt.replace(tzinfo=WK.ET)
        return int(dt.timestamp())
    return int((dt - datetime.datetime(1970, 1, 1)).total_seconds())


def game(gid, d, state, hour=19, div=1):
    return {"game_id": gid, "game_state": state,
            "start_time_epoch": ep(d, hour),
            "teams": [{"name_short": "A", "division": div},
                      {"name_short": "B", "division": div}]}


def main():
    print("WEEKLY CALENDAR GUARDS\n")
    now = ep(MONDAY, 23)                       # "now" = late Monday night

    print("1. THE CUTOFF IS THE PRIOR SUNDAY, IN EASTERN")
    check("Monday looks back to yesterday",
          WK.prior_sunday(MONDAY) == SUNDAY, str(WK.prior_sunday(MONDAY)))
    check("Tuesday still looks back to that Sunday",
          WK.prior_sunday(MONDAY + datetime.timedelta(days=1)) == SUNDAY)
    # ⚠ A SUNDAY FREEZE CANNOT COVER ITS OWN SUNDAY: most of it is unplayed.
    check("[-] Sunday does NOT cut off on itself",
          WK.prior_sunday(SUNDAY) == SUNDAY - datetime.timedelta(days=7),
          str(WK.prior_sunday(SUNDAY)))
    check("the cutoff is stated in Eastern",
          WK.completeness([], SUNDAY, now)["cutoff_tz"] == "America/New_York")

    print("\n2. A SUNDAY FINAL IS INCLUDED")
    c = WK.completeness([game("s1", SUNDAY, "F")], SUNDAY, now)
    check("a Sunday final counts toward the freeze", c["finals"] == 1,
          str(c["finals"]))
    check("...and nothing blocks", c["state"] == "complete", str(c["blocking"]))
    # A Saturday final counts too -- the window is "on or before".
    c2 = WK.completeness([game("s0", SUNDAY - datetime.timedelta(days=1), "F"),
                          game("s1", SUNDAY, "F")], SUNDAY, now)
    check("an earlier final in the same week also counts", c2["finals"] == 2)

    print("\n3. AN UNRESOLVED SUNDAY MATCH BLOCKS THE FREEZE")
    for state, hours_ago, why in (("I", 1, "live"),
                                  ("P", 1, "unresolved"),
                                  ("P", 48, "stale")):
        g = game("x", SUNDAY, state, hour=19)
        n = ep(SUNDAY, 19) + int(hours_ago * 3600)
        c3 = WK.completeness([game("s1", SUNDAY, "F"), g], SUNDAY, n)
        check("a %-10s Sunday match blocks" % why, c3["state"] == "waiting",
              str(c3))
        check("   ...and is reported as %r" % why,
              bool(c3["blocking"]) and c3["blocking"][0]["why"] == why,
              str(c3["blocking"][:1]))
    # ⚠ AND THE FINAL BESIDE IT IS STILL COUNTED, so the waiting state can say
    # how much of the week IS in -- "7 final, 39 not" rather than a bare stop.
    c4 = WK.completeness([game("s1", SUNDAY, "F"), game("x", SUNDAY, "P")],
                         SUNDAY, ep(SUNDAY, 19) + 3600)
    check("the waiting state still reports the finals it has",
          c4["finals"] == 1 and len(c4["blocking"]) == 1)

    print("\n4. MONDAY IS EXCLUDED EVEN WHEN FINISHED")
    c5 = WK.completeness([game("s1", SUNDAY, "F"), game("m1", MONDAY, "F")],
                         SUNDAY, now)
    check("a finished MONDAY match is not counted", c5["finals"] == 1,
          "%d finals" % c5["finals"])
    check("[-] ...and an unfinished Monday match does NOT block",
          WK.completeness([game("s1", SUNDAY, "F"), game("m2", MONDAY, "P")],
                          SUNDAY, now)["state"] == "complete")
    # ⚠ THE HAWAII CASE, MADE EXPLICIT. 7pm Sunday in Honolulu is 1am Monday
    # Eastern, so it falls in the NEXT week. That is a real consequence of
    # using one zone, and it is tested rather than discovered.
    haw = game("hi", MONDAY, "F", hour=1)
    c6 = WK.completeness([game("s1", SUNDAY, "F"), haw], SUNDAY, now)
    check("a 1am-Eastern Monday match (7pm Sunday HST) is next week's",
          c6["finals"] == 1, "%d finals" % c6["finals"])

    print("\n5. NON-DIVISION-I FIXTURES DO NOT HOLD A POLL OPEN")
    c7 = WK.completeness([game("s1", SUNDAY, "F"),
                          game("d2", SUNDAY, "P", div=2)], SUNDAY, now)
    check("a non-D-I fixture cannot block the freeze",
          c7["state"] == "complete", str(c7["blocking"]))

    print("\n6. THE CUTOFF IS VISIBLE, NOT IMPLIED")
    lab = WK.week_label(SUNDAY)
    check("the label names the ruler and the Sunday",
          lab == "Digby Weekly · Through Sunday, September 13", lab)
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(hub):
        h = open(hub, encoding="utf-8").read()
        check("the page carries a 'Through Sunday' label",
              "Through Sunday," in h)
        check("the calendar states the waiting rule",
              "Nothing partial is saved" in h)
        # ⚠ THIS COPY IS CONDITIONAL NOW. The withdrawal explanation renders
        # only while something is actually blocking; with a clean week it is
        # correctly absent from the DOM. Assert the page CAN say it.
        check("...and can explain why a withdrawn fixture stops blocking",
              "has <b>withdrawn</b> no longer blocks" in h)
        check("...and names the disposition policy on the active week",
              "Disposition policy" in h)
        # The tag class is applied at render time ('caltag ' + tagcls), so the
        # joined string is never a literal. Assert the pieces that are.
        check("the three track kinds are styled distinctly",
              ".caltag.derived{" in h and ".caltag.official{" in h
              and ".caltag.community{" in h)
        check("...and each track is labelled with its kind",
              "'Derived', 'derived'" in h and "'Official', 'official'" in h
              and "'community'" in h)

    print("\n7. A NEW WEEKLY SNAPSHOT CARRIES THE WHOLE FIELD")
    # Written to a TEMP file. The real archive is never touched by a test.
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    tmp.close()
    try:
        env = dict(os.environ, WVB_HISTORY_OUT=tmp.name)
        out = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "snapshot_rankings.py"),
             "--force"], env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, universal_newlines=True)
        rows = [json.loads(l) for l in open(tmp.name) if l.strip()]
        # ⚠ INTRADAY GENERATION RACE (2026-09-04): on a live match night
        # the corpus moves between certify and this test, and the archive
        # gate then fails closed with "right property, wrong generation"
        # -- which is the gate WORKING, not the snapshot code regressing.
        # The behavioural check runs whenever generations align (every CI
        # run; any quiet hour locally) and defers to the gate otherwise.
        if len(rows) != 1 and "wrong generation" in out.stdout:
            print("    (corpus moved since certify_rankings -- the "
                  "archive gate refused a cross-generation snapshot, "
                  "which is its job; behavioural check deferred)")
        else:
            check("a forced snapshot wrote exactly one row", len(rows) == 1,
                  out.stdout[-200:])
        if rows:
            r = rows[0]
            check("it carries all 348 teams", len(r.get("teams") or []) == 348,
                  "%d teams" % len(r.get("teams") or []))
            for f in ("cutoff", "cutoff_tz", "captured_utc", "finals_included",
                      "completeness", "label", "track"):
                check("   it records %-16s" % f, r.get(f) is not None,
                      "missing")
            check("   the label is the visible promise",
                  str(r.get("label", "")).startswith("Digby Weekly · Through Sunday,"),
                  r.get("label"))
            # ⚠ A FORCED SNAPSHOT IS NEVER LABELLED COMPLETE. It records what
            # it overrode, so the two can never be confused a month later.
            if r.get("completeness") == "forced":
                check("   a forced row keeps the count it overrode",
                      r.get("blocking_at_capture", 0) > 0,
                      str(r.get("blocking_at_capture")))
        # Re-running must not append a second row for the same cutoff.
        subprocess.run([sys.executable,
                        os.path.join(SCRIPTS, "snapshot_rankings.py"), "--force"],
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        rows2 = [json.loads(l) for l in open(tmp.name) if l.strip()]
        check("[-] re-running does not duplicate the cutoff",
              len(rows2) == len(rows), "%d rows" % len(rows2))
    finally:
        os.unlink(tmp.name)

    print("\n8. THE REAL ARCHIVE IS UNTOUCHED AND ITS HISTORY IS INTACT")
    real = os.path.join(REPO, "data", "rankings_history_2026.jsonl")
    if os.path.exists(real):
        rows = [json.loads(l) for l in open(real) if l.strip()]
        w35 = [r for r in rows if r.get("week") == "2026-W35"]
        # ⚠ THIS USED TO PIN len(w35) == 1 -- true only BEFORE the first
        # Monday freeze completed the week. On 2026-08-31 the CI freeze
        # legitimately wrote the completed W35 row (cutoff Sunday Aug 30),
        # this guard failed the build, the commit step never ran, AND THE
        # FROZEN ROW WAS THROWN AWAY -- a calendar-phase pin destroying
        # the freeze itself. The invariant is: the historical incomplete
        # row is still there, unrewritten; anything further for W35 must
        # be a completed cutoff freeze, appended, never a rewrite.
        legacy = [r for r in w35 if "cutoff" not in r]
        frozen = [r for r in w35 if "cutoff" in r]
        check("the incomplete W35 row is still present (unrewritten)",
              len(legacy) == 1, "%d legacy rows" % len(legacy))
        if legacy:
            check("   ...still exactly as archived (35 teams)",
                  len(legacy[0].get("teams") or []) == 35,
                  "%d teams" % len(legacy[0].get("teams") or []))
        check("   ...at most one completed W35 freeze beside it, on the "
              "Sunday cutoff with the full field",
              len(frozen) <= 1 and all(
                  r.get("cutoff") == "2026-08-30"
                  and len(r.get("teams") or []) >= 300 for r in frozen),
              frozen and (frozen[0].get("cutoff"),
                          len(frozen[0].get("teams") or [])))
        check("no row was rewritten to a new track",
              all(("track" not in r) or r.get("cutoff") for r in rows))

    print("\n9. THE AVCA POLL IS CAPTURED ONCE PER PUBLICATION")
    src = open(os.path.join(SCRIPTS, "crawl_polls.py"), encoding="utf-8").read()
    check("captures are keyed on the poll's own stamp",
          'seen.add(json.loads(line).get("stamp"))' in src)
    check("...and an unchanged stamp adds no row",
          "if stamp and stamp in seen:" in src and "continue" in src)
    check("both times are recorded: the stamp and our capture",
          '"captured_utc"' in src and '"stamp": stamp' in src)
    pol = os.path.join(REPO, "data", "raw", "2026", "polls_avca.jsonl")
    if os.path.exists(pol):
        stamps = [json.loads(l).get("stamp") for l in open(pol) if l.strip()]
        check("[+] there is at least one capture to check", bool(stamps))
        check("no stamp appears twice in the archive",
              len(stamps) == len(set(stamps)), str(stamps))
    wf = open(os.path.join(REPO, ".github", "workflows", "daily.yml"),
              encoding="utf-8").read()
    # ⚠ MONDAY AFTERNOON. The poll publishes Monday, usually after the 09:15
    # UTC run, and the endpoint is current-only -- a poll missed on its
    # publication day can be gone, not merely late.
    check("a Monday afternoon/evening run exists to catch a new poll",
          re.search(r'cron:\s*"\d+ (1[3-9]|2[0-3]) \* \* 1"', wf) is not None,
          "no Monday-only afternoon cron")

    print("\n10. THE COMMUNITY POLL REACHES NOTHING")
    # ⚠ THE POINT OF THIS SECTION. VolleyTalk is display-only. It must not be
    # crawled, and it must not feed any number this site computes.
    vt_file = "volleytalk_polls"
    readers = []
    for fn in sorted(os.listdir(SCRIPTS)):
        if not fn.endswith(".py") or fn.startswith("test_"):
            continue
        body = open(os.path.join(SCRIPTS, fn), encoding="utf-8").read()
        if vt_file in body:
            readers.append(fn)
    check("only the page builder reads the community poll at all",
          readers == ["build_hub.py"], str(readers))
    bh = open(os.path.join(SCRIPTS, "build_hub.py"), encoding="utf-8").read()
    # It may be read ONLY inside calendar_tracks(), the display function.
    fn_src = bh[bh.index("def calendar_tracks"):bh.index("def powercell")]
    check("...and only inside calendar_tracks(), which renders it",
          bh.count(vt_file) == 1 and vt_file in fn_src,
          "%d references" % bh.count(vt_file))
    # No rating/projection/ballot module may even mention it.
    for mod in ("rating_2025.py", "digby_top25.py", "project_2026.py",
                "project_field.py", "simulate_season_2026.py",
                "build_rankings_board.py"):
        p2 = os.path.join(SCRIPTS, mod)
        if os.path.exists(p2):
            body = open(p2, encoding="utf-8").read()
            check("[-] %-26s never reads the manual poll" % mod,
                  vt_file not in body)
    # ⚠ AND THE PRE-EXISTING REFERENCE COLUMN IS NOT INFLUENCE. The rankings
    # board has always CARRIED a VolleyTalk rank as one of its reference
    # columns (stripped from the public build). It is displayed beside our own
    # order and never read back into it. Assert that distinction rather than
    # pretending the word does not appear.
    brb = open(os.path.join(SCRIPTS, "build_rankings_board.py"),
               encoding="utf-8").read()
    for feeder in ("composite", "rating", "score =", "power"):
        near = re.findall(r"[^\n]*volleytalk[^\n]*", brb, re.I)
        bad = [ln for ln in near if feeder in ln.lower()]
        check("[-] its VT reference never feeds %-10s" % feeder, not bad,
              str(bad[:1]))
    # And no script fetches the domain.
    fetchers = []
    for fn in sorted(os.listdir(SCRIPTS)):
        # ⚠ SKIP TEST FILES, INCLUDING THIS ONE. The first version searched
        # every script for a fetch aimed at the domain and found ITSELF --
        # this file necessarily contains that pattern in order to look for it.
        # The claim being made is about the pipeline, not about the guard.
        if not fn.endswith(".py") or fn.startswith("test_"):
            continue
        body = open(os.path.join(SCRIPTS, fn), encoding="utf-8").read()
        if re.search(r"(urlopen|requests\.|curl)[^\n]{0,120}volleytalk", body, re.I):
            fetchers.append(fn)
    check("[-] nothing fetches the community site", not fetchers, str(fetchers))
    # The public build must not carry it at all.
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        ph = open(pub, encoding="utf-8").read()
        check("[-] the public build carries no community-poll payload",
              '"vt_name"' not in ph and "VolleyTalk" not in ph)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL WEEKLY CALENDAR GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
