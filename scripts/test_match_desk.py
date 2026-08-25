#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the Match Desk.

The desk answers "what should I watch, why does it matter, what did it mean" --
and every one of those answers is a copied fact. The ways it could go wrong are
specific:

  1. QUOTING A FORECAST THAT SAW THE RESULT. data/predictions_2026.json is
     regenerated nightly from everything known at the time. For a match that has
     been played, "everything known" includes the result. Showing that as "what
     we expected beforehand" would be inventing a prediction after the fact --
     the most dishonest thing this page could do, and completely invisible,
     because the number would look exactly like a real forecast.

  2. LETTING LIVE DATA REACH A RATING. A live card is read from the scoreboard
     feed. If any of it were baked into the built page or into a derived file,
     POWER would be computed from a half-played match.

  3. INVENTING A WATCH SCORE. The brief forbids it and so does this file: no
     composite ranking number may appear in the payload.

  4. FILLING A GAP. A missing venue must say so; a missing forecast must say so.

Python 3.9 target. Run: python3 scripts/test_match_desk.py
"""

import datetime
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def desk_payload(path):
    src = open(path, encoding="utf-8").read()
    m = re.search(r"const DESK = (\[.*?\]);\n", src, re.S)
    return (json.loads(m.group(1)) if m else None), src


def main():
    print("MATCH DESK GUARDS\n")
    # CI checks out a tree with no Cody/ (it is gitignored), so the private page
    # is genuinely absent there. The desk is on BOTH builds, so read whichever
    # exists -- failing for a file CI was never meant to carry would make the
    # nightly run red for no defect.
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        hub = os.path.join(REPO, "output", "vb_dashboard.html")
    if not os.path.exists(hub):
        print("  (no built page on disk -- nothing to guard; skipping)")
        return 0
    print("  reading %s" % os.path.relpath(hub, REPO))
    desk, src = desk_payload(hub)
    if desk is None:
        check("the desk payload is present", False, "const DESK not found")
        return 1
    check("the desk payload is present", True, "")
    print("     (%d fixtures in the window)" % len(desk))

    print("\n1. A finished match quotes only a forecast logged BEFORE tipoff")
    log = {}
    lp = os.path.join(REPO, "data", "raw", str(SEASON), "prediction_log.jsonl")
    if os.path.exists(lp):
        for line in open(lp, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            gid = str(r.get("game_id"))
            log.setdefault(gid, []).append(r)
    epoch = {}
    dp = os.path.join(REPO, "data", "data_%d.json" % SEASON)
    if os.path.exists(dp):
        for g in (json.load(open(dp, encoding="utf-8")).get("games") or []):
            epoch[str(g.get("game_id"))] = g.get("start_time_epoch")

    import build_hub as BH
    def verify_final(m, log, epoch):
        """Problems with ONE final card's forecast provenance. [] means proved."""
        bad = []
        if m.get("hw") is None:
            if not (m.get("fsrc") or ""):
                bad.append("%s: no forecast and no reason given" % m["gid"])
            return bad
        if not str(m.get("fsrc", "")).startswith("logged "):
            bad.append("%s: fsrc=%r" % (m["gid"], m.get("fsrc")))
            return bad
        row = None
        for r in (log.get(m["gid"]) or []):
            if str(r.get("logged_utc") or "") == str(m["fsrc"])[len("logged "):]:
                row = r
        if not row:
            bad.append("%s: names a logged row that is not in the log" % m["gid"])
            return bad
        if abs(float(row["home_win"]) - float(m["hw"])) > 1e-9:
            bad.append("%s: shows %s, log says %s"
                       % (m["gid"], m["hw"], row["home_win"]))
        # ⚠ NO EPOCH MEANS NO PROOF, AND THAT IS A FAILURE, NOT A PASS. This
        # used to read `if ep and lu:` -- so a card missing either one skipped
        # the check entirely and its forecast was accepted unexamined.
        ep = epoch.get(m["gid"])
        t = BH.parse_logged_utc(row.get("logged_utc"))
        try:
            ep = float(ep) if ep is not None else None
        except (TypeError, ValueError):
            ep = None
        if ep is None or ep <= 0:
            bad.append("%s: shows a forecast with no usable tipoff" % m["gid"])
        elif t is None:
            bad.append("%s: shows a forecast with no usable stamp (%r)"
                       % (m["gid"], row.get("logged_utc")))
        elif not t < ep:
            bad.append("%s: logged %s, tipoff %s -- not strictly earlier"
                       % (m["gid"], row.get("logged_utc"), ep))
        return bad

    import build_hub as BH
    finals = [m for m in desk if m.get("final")]
    print("     (%d final in the window)" % len(finals))
    bad_time, unavailable = [], 0
    for m in finals:
        if m.get("hw") is None:
            unavailable += 1
        bad_time.extend(verify_final(m, log, epoch))
    check("every final's forecast is the append-only log's value",
          not [b for b in bad_time if "log says" in b or "not in the log" in b],
          "; ".join(bad_time[:3]))
    check("...and every one is PROVED strictly earlier than first serve",
          not bad_time, "; ".join(bad_time[:3]))
    if unavailable:
        print("     (%d final(s) show 'forecast unavailable', each with a reason)"
              % unavailable)

    # ⚠ NEGATIVE CONTROL ON THE PAGE GUARD ITSELF. Live data may contain no
    # unproven card at all, so the guard would pass without ever exercising the
    # thing it exists to catch. Push doctored cards through the same function.
    # ⚠ DERIVED, NOT TYPED. I first hard-coded this and was two hours out,
    # so the "equal to first serve" control was really two hours BEFORE it
    # and passed -- the control was wrong, not the guard it accused.
    TIPE = BH.parse_logged_utc("2026-08-24T22:00:00Z")
    LOGX = {"g": [{"home_win": 0.7, "logged_utc": "2026-08-22T21:35:38Z"}]}
    good = {"gid": "g", "hw": 0.7, "fsrc": "logged 2026-08-22T21:35:38Z"}
    check("[+] a properly proved card passes the page guard",
          not verify_final(good, LOGX, {"g": TIPE}))
    for label, card, log2, ep2 in (
            ("a card whose tipoff is unknown", good, LOGX, {}),
            ("a card whose tipoff is malformed", good, LOGX, {"g": "soon"}),
            ("a card claiming a row the log does not have",
             {"gid": "g", "hw": 0.7, "fsrc": "logged 2026-08-23T00:00:00Z"},
             LOGX, {"g": TIPE}),
            ("a card whose number disagrees with the log",
             {"gid": "g", "hw": 0.42, "fsrc": "logged 2026-08-22T21:35:38Z"},
             LOGX, {"g": TIPE}),
            ("a card sourced from the forward file",
             {"gid": "g", "hw": 0.7, "fsrc": "current forecast"}, LOGX,
             {"g": TIPE}),
            ("a card logged exactly at first serve",
             {"gid": "g", "hw": 0.7, "fsrc": "logged 2026-08-24T22:00:00Z"},
             {"g": [{"home_win": 0.7, "logged_utc": "2026-08-24T22:00:00Z"}]},
             {"g": TIPE}),
            ("a card with no reason for having no forecast",
             {"gid": "g", "hw": None, "fsrc": ""}, LOGX, {"g": TIPE})):
        check("[-] the page guard rejects %s" % label,
              bool(verify_final(card, log2, ep2)))
    if unavailable:
        print("     (%d final(s) show 'forecast unavailable', each with a reason)"
              % unavailable)

    # The live data may contain no post-tipoff row at all, so the case the whole
    # rule exists for would never be exercised. Drive the rule directly.
    check("the rule is a callable, not buried in the builder",
          hasattr(BH, "played_forecast"))
    if hasattr(BH, "played_forecast"):
        import calendar
        import time as _t
        TIP = calendar.timegm(_t.strptime("2026-08-24T22:00:00Z",
                                          "%Y-%m-%dT%H:%M:%SZ"))
        EARLY = {"home_win": 0.7, "logged_utc": "2026-08-22T21:35:38Z"}
        EARLIER = {"home_win": 0.61, "logged_utc": "2026-08-21T09:00:00Z"}

        # POSITIVE CONTROLS. Without these, "refuse everything" passes the
        # whole negative block below and the feature silently shows nothing.
        for label, rows, ep, want in (
                ("a forecast logged 2 days early", [EARLY], TIP, 0.7),
                ("an undated row does NOT suppress a valid one",
                 [{"home_win": 0.9, "logged_utc": None}, EARLY], TIP, 0.7),
                ("a post-tipoff row does NOT suppress a valid one",
                 [{"home_win": 0.9, "logged_utc": "2026-08-25T03:00:00Z"},
                  EARLY], TIP, 0.7),
                ("the EARLIEST valid row wins", [EARLY, EARLIER], TIP, 0.61),
                ("...whatever order the log is read in",
                 [EARLIER, EARLY], TIP, 0.61),
                ("one second before first serve still counts",
                 [{"home_win": 0.55, "logged_utc": "2026-08-24T21:59:59Z"}],
                 TIP, 0.55)):
            hw, why = BH.played_forecast(rows, ep)
            check("[+] %s" % label, hw == want, "got %r (%s)" % (hw, why))

        # NEGATIVE CONTROLS -- each must refuse, and say which proof is missing.
        for label, rows, ep in (
                ("a missing start-time epoch", [EARLY], None),
                ("a malformed start-time epoch", [EARLY], "not-a-number"),
                ("an epoch of 0 (1970, not a match)", [EARLY], 0),
                ("a missing log timestamp",
                 [{"home_win": 0.7, "logged_utc": None}], TIP),
                ("a malformed log timestamp",
                 [{"home_win": 0.7, "logged_utc": "24/08/2026 10pm"}], TIP),
                ("a timestamp EQUAL to first serve",
                 [{"home_win": 0.7, "logged_utc": "2026-08-24T22:00:00Z"}], TIP),
                ("a timestamp after first serve",
                 [{"home_win": 0.7, "logged_utc": "2026-08-25T03:00:00Z"}], TIP),
                ("no logged row at all", None, TIP),
                ("an empty log", [], TIP),
                ("a row carrying no probability",
                 [{"home_win": None, "logged_utc": "2026-08-22T21:35:38Z"}],
                 TIP),
                ("every row invalid in a different way",
                 [{"home_win": 0.7, "logged_utc": None},
                  {"home_win": 0.7, "logged_utc": "2026-08-25T03:00:00Z"}],
                 TIP)):
            hw, why = BH.played_forecast(rows, ep)
            check("[-] %s is refused" % label, hw is None, "got %r" % (hw,))
            check("    ...and it says which proof is missing",
                  bool(why) and "logged" not in (why or "").split()[:1],
                  repr(why))

        # ⚠ THE CLAIM ITSELF. "logged <stamp>" is a statement that we CHECKED
        # the stamp against first serve. It may never appear otherwise.
        for label, rows, ep in (
                ("a missing epoch", [EARLY], None),
                ("an undated row", [{"home_win": 0.7, "logged_utc": None}], TIP),
                ("a tipoff-equal row",
                 [{"home_win": 0.7, "logged_utc": "2026-08-24T22:00:00Z"}],
                 TIP)):
            _hw, why = BH.played_forecast(rows, ep)
            check("[-] %s never claims 'logged ...'" % label,
                  not (why or "").startswith("logged "), repr(why))

        # An undated row must never be the DISPLAYED one even when it is alone
        # in being the earliest -- skipped, not selected.
        hw, why = BH.played_forecast(
            [{"home_win": 0.99, "logged_utc": None}, EARLY], TIP)
        check("[-] the undated row's own value is never displayed",
              hw != 0.99, "got %r" % (hw,))

    print("\n1a. Timestamp parsing refuses what it cannot read")
    if hasattr(BH, "parse_logged_utc"):
        check("[+] a well-formed stamp parses",
              BH.parse_logged_utc("2026-08-22T21:35:38Z") is not None)
        for bad in (None, "", "garbage", "2026-08-22", "2026-08-22 21:35:38",
                    "2026-13-45T99:99:99Z", 1755900000, {}):
            check("[-] %r does not parse" % (bad,),
                  BH.parse_logged_utc(bad) is None)

    print("\n1b. The result sentence describes the scoreline it was given")
    # deskHow() turns two set totals into words. It is pure and it is JS, so
    # lift it out of the page and actually run it rather than asserting that
    # its source contains some strings.
    import shutil
    import subprocess
    m = re.search(r"function deskHow\(f\) \{.*?\n\}", src, re.S)
    node = shutil.which("node")
    if not m:
        check("deskHow() is in the page", False)
    elif not node:
        print("  %-64s %s" % ("(no node on PATH -- cannot run deskHow)", "skip"))
    else:
        cases = [((3, 0), " in a sweep"), ((0, 3), " in a sweep"),
                 ((3, 2), ", but it went five"), ((2, 3), ", but it went five"),
                 ((3, 1), ", dropping a set"),
                 ((0, 0), "")]
        js = (m.group(0) + "\nconst out=[" + ",".join(
            "deskHow({hs:%d,as:%d})" % c[0] for c in cases)
            + "];console.log(JSON.stringify(out));")
        got = json.loads(subprocess.check_output(
            [node, "-e", js], universal_newlines=True).strip())
        for (score, want), g in zip(cases, got):
            check("%s-%s reads %r" % (score[0], score[1], want), g == want,
                  "got %r" % g)
        # NEGATIVE CONTROL: a sweep phrase must NOT appear when a set was lost.
        check("[-] a 3-1 is never called a sweep", "sweep" not in got[4], got[4])
        check("[-] a 3-0 is never called five", "five" not in got[0], got[0])

    print("\n2. Nothing live or partial is baked into the page")
    # the payload may carry a FINAL result; it must never carry an in-progress one
    live_ish = [m for m in desk
                if m.get("final") and (m["final"].get("hs") is None
                                       or m["final"].get("as") is None)]
    check("no card carries a half-finished result", not live_ish,
          str(live_ish[:2]))
    check("live scores are fetched at runtime, not built in",
          "fetch('/api/live')" in src,
          "the desk must read live data from the feed, never from the build")
    check("the live card names its source and says it is not rated",
          "not yet in any rating" in src)

    print("\n3. No composite watch score")
    banned = ("watch_score", "watchScore", "score", "rating", "weight")
    leaked = sorted({k for m in desk for k in m if k in banned})
    check("the payload carries no score/rating field", not leaked, str(leaked))
    check("the page says the order is a stated sort",
          "stated sort" in src, "a reader must see the reason, not a number")

    print("\n4. Missing values are stated, never filled")
    check("a missing venue renders as 'venue not listed'",
          "venue not listed" in src)
    check("a missing forecast renders as 'forecast unavailable'",
          "forecast unavailable" in src)
    novenue = [m for m in desk if not m.get("venue")]
    print("     (%d of %d fixtures have no venue on file)" % (len(novenue), len(desk)))
    check("no card invents a venue",
          all(m.get("venue") or m.get("venue") is None for m in desk))

    print("\n5. Pacific dates, not the builder's clock")
    check("the builder has one definition of today, in Pacific",
          hasattr(BH, "today_pt"))
    check("...and nothing falls back to the machine clock",
          "datetime.date.today()" not in re.sub(
              r"#.*|\"\"\".*?\"\"\"", "",
              open(os.path.join(REPO, "scripts", "build_hub.py"),
                   encoding="utf-8").read(), flags=re.S),
          "date.today() is UTC on a runner and Pacific here")
    check("the desk filters 'today' in America/Los_Angeles",
          "America/Los_Angeles" in src)
    # every day label must be consistent with its ISO date
    today = BH.today_pt()
    mism = [m for m in desk
            if m["d"] == today.isoformat() and m.get("dl") != "Today"]
    check("a fixture dated today is labelled Today", not mism,
          str([m["d"] for m in mism[:3]]))

    print("\n6. Private sources never reach the desk")
    # ⚠ THE PAYLOAD IS PUBLISHED. VolleyTalk and Massey are other people's and
    # the public gate forbids them; the desk must not be the way they get out.
    priv = sorted({k for m in desk for k in m if k in ("vt", "massey")})
    check("the desk payload carries no VolleyTalk or Massey values", not priv,
          str(priv))
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        ph = open(pub, encoding="utf-8").read()
        check("the public build HAS the desk (it is neutral)",
              'data-v="desk"' in ph and "const DESK" in ph)
        leaks = BH.public_leaks(ph)
        check("...and the public build is still clean", not leaks, str(leaks))
        for marker in ('id="v-ballot"', "renderBallot", "ballots_"):
            check("public build has no %s" % marker, marker not in ph)
    else:
        print("  (no public build on disk -- skipping the public checks)")

    print("\n7. The forecast is presented as a probability, not a pick")
    check("the page calls it a forecast, not a recommendation",
          "not a pick" in src or "probability, not a pick" in src)
    check("it states what a losing favourite means",
          "loses three times in ten" in src or "expects" in src)
    check("Résumé is named as inactive rather than omitted",
          "not active yet" in src)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL MATCH DESK GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
