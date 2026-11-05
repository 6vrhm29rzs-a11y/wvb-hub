#!/usr/bin/env python3
"""Freshness repairs B1-B5 (work order 071, 2026-11-04) -- behaviour and guards.

  B1  one live fetch per 60-s cycle; Scores/ledger/team/match re-render from it;
      a failed fetch keeps the last good data
  B3  candidate weekly freeze decoupled from re-fits: idempotent per boundary,
      never labels later results as the week's snapshot; arrows name the freeze
  B4  verification/poll/correction/venue/date changes reach the right refresh
      path; per-match POWER status comes from the artifact's own input list
  B5  the quiet ticker capsule sheds rank chips/logos on a phone
  B2  versioned ranking sidecar; page and sidecar agree; public sidecar clean

Every behavioural check has a negative control that must trip.
Python 3.9. Run: python3 scripts/test_freshness_repairs.py
"""
import datetime
import importlib
import io
import json
import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-70s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:160]))
    if not ok:
        FAILS.append(label)


def src(name):
    return io.open(os.path.join(REPO, "scripts", name), encoding="utf-8").read()


def jsfn(text, name):
    from test_corrected_badge import jsfn as _j
    return _j(text, name) or ""


def main():
    B = src("build_hub.py")

    print("B1. ONE LIVE FETCH PER CYCLE")
    poll = jsfn(B, "pollLive")
    apply_ = jsfn(B, "deskApply")
    check("pollLive hands its response to deskApply", "deskApply(d)" in poll)
    check("deskApply does not fetch (one request per cycle)",
          "fetch(" not in apply_ and apply_)
    check("no second boot fetch through deskLive()",
          "if (typeof deskLive === 'function') deskLive();" not in B)
    G = "if (!j || !Array.isArray(j.games)) return;"

    def keeps_data(a):
        return 0 <= a.find(G) < a.find("LIVE_BY_ID = ") and "LIVE_BY_ID = {}" not in a
    check("a failed fetch returns before touching LIVE_BY_ID", keeps_data(apply_))
    check("deskApply refreshes the Scoreboard and the open match",
          "renderScoreboard()" in apply_ and "renderMatchDetail(" in apply_)
    check("scroll is kept across the re-render", "window.scrollTo(0, _y)" in apply_)
    bad = apply_.replace(G, "j = j || {games: []};")
    check("[NEG] a wipe-on-failure deskApply is caught",
          bad != apply_ and not keeps_data(bad))

    print("\nB3. WEEKLY FREEZE, DECOUPLED AND HONEST")
    SO = importlib.import_module("season_only_candidate")
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
    td = tempfile.mkdtemp()
    old_dir = SO.DIR
    SO.DIR = td
    try:
        mon = datetime.datetime(2026, 11, 9, 2, 0, tzinfo=PT)         # Monday 02:00 PT
        sun_night = datetime.datetime(2026, 11, 8, 21, 0, tzinfo=PT).timestamp()
        mon_noon = datetime.datetime(2026, 11, 9, 12, 0, tzinfo=PT).timestamp()
        cand = os.path.join(td, "cand.json")

        def write(ep):
            json.dump({"version": "v", "data_through_epoch": ep,
                       "teams": {"A": {"rank": 1}, "B": {"rank": 2}}}, open(cand, "w"))
        write(sun_night)
        r1 = SO.weekly_freeze(cand, now=mon)
        r2 = SO.weekly_freeze(cand, now=mon + datetime.timedelta(hours=1))
        rows = [json.loads(l) for l in open(os.path.join(td, "rankings_history_candidate.jsonl"))]
        check("a quiet Monday still freezes the completed week", r1 == "frozen", r1)
        check("idempotent: a second run the same week writes nothing",
              r2 == "already" and len(rows) == 1, (r2, len(rows)))
        check("the row is labelled by its Sunday and records both times",
              rows[0]["cutoff"] == "2026-11-08" and rows[0]["week"] == "2026-W45"
              and rows[0].get("captured_utc") and rows[0].get("results_through_pt"))
        os.remove(os.path.join(td, "rankings_history_candidate.jsonl"))
        write(mon_noon)
        r3 = SO.weekly_freeze(cand, now=mon + datetime.timedelta(days=2))
        check("[NEG] results after the Sunday -> MISSED, nothing written",
              r3 == "missed" and not os.path.exists(
                  os.path.join(td, "rankings_history_candidate.jsonl")), r3)
        write(sun_night)
        r4 = SO.weekly_freeze(cand, now=mon + datetime.timedelta(days=2))
        check("a late (Wednesday) run with Sunday-bounded data still freezes it",
              r4 == "frozen", r4)
    finally:
        SO.DIR = old_dir
    so = src("season_only_candidate.py")
    check("the freeze runs BEFORE any re-fit in main()",
          so.find("weekly_freeze(out)") < so.find('[sys.executable, WORK, "freeze"'))
    lr = src("local_refresh.py")
    check("local_refresh runs --weekly-only every cycle, before the gate",
          '"--weekly-only"' in lr and lr.find('"--weekly-only"') < lr.find("mode = decide("))
    check("arrows name WHICH freeze they compare with",
          't.get("move_vs")' in B and '"move_vs": prev_label' in src("build_rankings_board.py"))
    check("the disposition ledger is rebuilt locally too",
          '"scripts/fixture_disposition.py"' in lr)

    print("\nB4. THE RIGHT THINGS TRIGGER THE RIGHT REFRESH")
    LR = importlib.import_module("local_refresh")
    base = {"finals": "f", "rating": "r", "presentation": "p"}
    check("idle cycle -> none", LR.decide(base, dict(base)) == "none")
    check("poll/venue change -> page only",
          LR.decide(base, dict(base, presentation="p2")) == "present")
    check("verdict/correction/date change -> full rebuild",
          LR.decide(base, dict(base, rating="r2")) == "full")
    check("new final -> full rebuild", LR.decide(base, dict(base, finals="f2")) == "full")
    check("no saved state -> full rebuild (first run, or after a failure)",
          LR.decide({}, dict(base)) == "full")
    check("digests are stable across two computations",
          LR.digests("x") == LR.digests("x"))
    check("[NEG] the FETCH log is not a rating input (it grows every retry)",
          "result_verification_log.jsonl" not in LR.RATING_INPUTS)
    check("the Pacific date is part of the rating digest (midnight eligibility)",
          LR.pacific_date() in LR.digests("x")["rating"])
    check("verification runs before the gate",
          lr.find('"scripts/verify_results_daily.py", "--incremental"]') < lr.find("mode = decide("))
    check("digests are saved only after a successful rebuild",
          lr.count("save_digests(cur)") == 2
          and lr.find("save_digests(cur)") > lr.find('_record("rebuild_failed"'))
    vol = LR._stable({"a": 1, "retrieved_utc": "x", "n": {"generated": 2, "b": 3}})
    check("timestamp fields are dropped before hashing",
          vol == {"a": 1, "n": {"b": 3}}, vol)

    import build_hub as BH
    cand = json.load(open(os.path.join(REPO, "Cody", "data", "power_candidate",
                                       "v2so_preview.json"))) \
        if os.path.exists(os.path.join(REPO, "Cody", "data", "power_candidate",
                                       "v2so_preview.json")) else None
    if cand:
        inc = BH.power_inclusion(cand)
        used = set(str(r.get("gid")) for t in cand["teams"].values()
                   for r in (t.get("why") or {}).get("results") or [])
        check("'included' == exactly the artifact's own input list",
              set(k for k, v in inc.items() if v == "in") == used,
              (sum(1 for v in inc.values() if v == "in"), len(used)))
        check("no eligible-but-absent final is called included",
              not any(v == "in" for k, v in inc.items() if k not in used))
        fake = dict(cand, teams={})
        inc0 = BH.power_inclusion(fake)
        check("[NEG] with an empty artifact nothing is 'in'",
              not any(v == "in" for v in inc0.values()))
        check("every code has plain-English wording on the page",
              all(("'" + c + "'") in B for c in set(inc.values())), sorted(set(inc.values())))
    else:
        print("  no candidate file -- inclusion checks skipped (CI)")

    print("\nB5. QUIET TICKER FITS A PHONE")
    check("the quiet capsule drops rank chips and logos on a phone",
          "#livetick .tklab.tkquiet ~ .tkm .rks{display:none}" in B
          and "#livetick .tklab.tkquiet ~ .tkm img{display:none}" in B)

    print("\nB2. RANKINGS UPDATE WITHOUT A RELOAD")
    rl = jsfn(B, "rankLiveCheck")
    check("the poll asks for the sidecar", "rankLiveCheck()" in poll)
    check("a schema mismatch offers a notice and never reloads",
          "j.schema !== RANK_LIVE_SCHEMA" in rl and "location.reload" not in rl)
    check("a compatible version re-applies the reader's sort and Top-N",
          "rkApplySort();" in rl and "renderRank();" in rl)
    check("rank and POWER update together in TEAMS",
          "TEAMS[n].rank = j.teams[n].rank; TEAMS[n].power = j.teams[n].power;" in rl)
    check("the note dates the rest of the page", "PAGE_BUILT_EPOCH" in rl)
    for label, path in (("private", os.path.join(REPO, "Cody", "START-HERE.html")),
                        ("public", os.path.join(REPO, "output", "vb_dashboard.html"))):
        side = os.path.join(os.path.dirname(path), "rankings_live.json")
        if not (os.path.exists(path) and os.path.exists(side)):
            print("  %s: page or sidecar not built -- skipped" % label)
            continue
        page = io.open(path, encoding="utf-8").read()
        j = json.load(open(side))
        m = re.search(r"let RANK_LIVE_VERSION = \"([0-9a-f]+)\";", page)
        check("%s: page and sidecar carry the same version" % label,
              bool(m) and m.group(1) == j.get("version"), (m and m.group(1), j.get("version")))
        check("%s: sidecar rows and teams are consistent" % label,
              j.get("rows_html", "").count('class="row') >= len(j.get("teams") or {}) * 0.9)
        if label == "public":
            leaks = [mk for mk in BH.PRIVATE_MARKERS if mk in json.dumps(j)]
            check("public: the sidecar carries no private content", not leaks, leaks)

    if FAILS:
        print("\nFAILED: %d" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        sys.exit(1)
    print("\nALL FRESHNESS-REPAIR CHECKS PASSED")


if __name__ == "__main__":
    main()
