#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test for the two live-season crawl bugs. Run: python3 scripts/test_crawl_freshness.py

Both bugs are invisible on a finished season and destructive on a live one:

  BUG A  a date fetched mid-day was cached as complete and never refetched, so
         that evening's matches were lost permanently.
  BUG B  a game stored while in progress was never updated to final, and --
         worse -- the append-only log deduped FIRST-wins, so even a successful
         refetch would have been ignored by every reader.

Each test below is written so that it FAILS against the old behaviour. A fix
without a test that would have caught the bug is not finished.

No network. Pure functions and temp files only.
"""

import datetime
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl_2025 import date_is_authoritative, date_needs_refetch  # noqa: E402
from gamelog import load_games_jsonl, final_game_ids, is_final  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %-62s %s" % (name, "ok" if ok else "FAIL (got %r, want %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


def sb(games):
    return {"games": [{"game": g} for g in games]}


def game(gid, state, final_msg=""):
    return {"gameID": gid, "gameState": state, "finalMessage": final_msg}


def main():
    tmp = tempfile.mkdtemp(prefix="wvb-freshness-")
    try:
        today = datetime.date(2025, 9, 15)
        past = datetime.date(2025, 9, 14)

        # ---------------- BUG A: partial day must stay refetchable ----------
        print("BUG A -- a date fetched mid-day must not be cached as complete")

        partial = sb([game("1", "final", "FINAL"), game("2", "live")])
        complete = sb([game("1", "final", "FINAL"), game("2", "final", "FINAL")])

        p = os.path.join(tmp, "partial.json")
        with open(p, "w") as fh:
            json.dump(partial, fh)
        # THE BUG: old code was `if os.path.exists(out): skip`, which would have
        # returned False here and lost game 2 forever.
        check("past date with an unresolved game -> needs refetch",
              date_needs_refetch(p, past, today), True)

        c = os.path.join(tmp, "complete.json")
        with open(c, "w") as fh:
            json.dump(complete, fh)
        check("past date with all games final -> authoritative, no refetch",
              date_needs_refetch(c, past, today), False)

        check("TODAY is never authoritative even if all games read final",
              date_needs_refetch(c, today, today), True)
        check("a FUTURE date is never authoritative",
              date_needs_refetch(c, today + datetime.timedelta(days=1), today), True)

        check("missing file -> needs refetch",
              date_needs_refetch(os.path.join(tmp, "nope.json"), past, today), True)

        torn = os.path.join(tmp, "torn.json")
        with open(torn, "w") as fh:
            fh.write('{"games": [{"gam')
        check("truncated file -> needs refetch",
              date_needs_refetch(torn, past, today), True)

        check("empty past date (no games) -> authoritative",
              date_is_authoritative(sb([]), past, today), True)

        # ------------- CONVERGENCE: partial day then complete day -----------
        print()
        print("BUG A -- convergence: partial state then complete state")
        seq = os.path.join(tmp, "seq.json")
        with open(seq, "w") as fh:
            json.dump(partial, fh)
        before = date_needs_refetch(seq, past, today)
        with open(seq, "w") as fh:      # simulates the refetch landing
            json.dump(complete, fh)
        after = date_needs_refetch(seq, past, today)
        check("refetchable before, settled after -> converges", (before, after), (True, False))

        # ---------------- BUG B: in-progress game must be superseded --------
        print()
        print("BUG B -- an in-progress game must be superseded by its final record")
        jl = os.path.join(tmp, "games.jsonl")
        with open(jl, "w") as fh:
            fh.write(json.dumps({"game_id": "77", "game_state": "I",
                                 "teams": [], "note": "in progress"}) + "\n")
        check("in-progress game is NOT counted as already-have",
              "77" in final_game_ids(jl), False)
        check("in-progress game loads with its provisional state",
              load_games_jsonl(jl)[0]["game_state"], "I")

        # the refetch appends the final record AFTER the stale one
        with open(jl, "a") as fh:
            fh.write(json.dumps({"game_id": "77", "game_state": "F",
                                 "teams": [], "note": "final"}) + "\n")
        recs = load_games_jsonl(jl)
        # THE BUG: first-wins dedup returned the "in progress" record here, so
        # the refetch would have silently changed nothing.
        check("after refetch, exactly one record survives", len(recs), 1)
        check("the surviving record is the FINAL one", recs[0]["note"], "final")
        check("final game now counts as already-have", "77" in final_game_ids(jl), True)

        # order independence: final written BEFORE a later stale duplicate
        jl2 = os.path.join(tmp, "games2.jsonl")
        with open(jl2, "w") as fh:
            fh.write(json.dumps({"game_id": "9", "game_state": "F", "note": "final"}) + "\n")
            fh.write(json.dumps({"game_id": "9", "game_state": "I", "note": "stale"}) + "\n")
        check("a LATER in-progress duplicate cannot overwrite a final record",
              load_games_jsonl(jl2)[0]["note"], "final")

        # torn final line must not poison the log
        jl3 = os.path.join(tmp, "games3.jsonl")
        with open(jl3, "w") as fh:
            fh.write(json.dumps({"game_id": "5", "game_state": "F", "note": "good"}) + "\n")
            fh.write('{"game_id": "6", "game_st')
        recs3 = load_games_jsonl(jl3)
        check("torn trailing line is skipped, good records survive",
              (len(recs3), recs3[0]["note"]), (1, "good"))

        # ---------------- future fixtures must not be crawled ---------------
        print()
        print("FUTURE FIXTURES -- published-but-unplayed games must be skipped")
        import crawl_2025 as C
        sbdir = os.path.join(tmp, "sb")
        os.makedirs(sbdir)
        real_today = datetime.date.today()
        past_day = real_today - datetime.timedelta(days=2)
        future_day = real_today + datetime.timedelta(days=30)
        with open(os.path.join(sbdir, past_day.isoformat() + ".json"), "w") as fh:
            json.dump(sb([game("past1", "final", "FINAL")]), fh)
        with open(os.path.join(sbdir, future_day.isoformat() + ".json"), "w") as fh:
            json.dump(sb([game("fut1", "pre"), game("fut2", "pre")]), fh)
        orig = C.SCOREBOARD_DIR
        C.SCOREBOARD_DIR = sbdir
        try:
            got = C.game_ids_from_schedule()
            allids = C.game_ids_from_schedule(include_future=True)
        finally:
            C.SCOREBOARD_DIR = orig
        # THE BUG: without the date filter these unplayed fixtures are "not
        # final" forever, so they would be refetched on every single run.
        check("future fixtures excluded from the crawl list", got, ["past1"])
        check("include_future=True still sees them", sorted(allids),
              ["fut1", "fut2", "past1"])

        # ---------------------------------------------------------------
        print()
        print("VANISHED FIXTURES -- games ncaa.com removes from a past date")
        # MEASURED 2026-08-22. We crawled 12 games for 2026-08-21 on the 18th;
        # the live scoreboard for that date now returns 2. The other ten were
        # PULLED -- not postponed to a new date, not played, just gone. Their
        # non-final records are already in the append-only log and can never be
        # superseded by a final one, because the game will never be fetched
        # again: it is no longer enumerated.
        #
        # The log keeping them is correct and deliberate (append-only, and a
        # record we once saw is a record we once saw). What must hold is that
        # NOTHING DOWNSTREAM COUNTS THEM. A phantom fixture that leaks into a
        # team's record inflates games played and corrupts every rate derived
        # from it, and it would look entirely plausible while doing so.
        vpath = os.path.join(tmp, "vanished.jsonl")
        with open(vpath, "w") as fh:
            # one real final, and two that were pulled from the schedule
            fh.write(json.dumps({"game_id": "real", "game_state": "F",
                                 "teams": [], "linescores": []}) + "\n")
            fh.write(json.dumps({"game_id": "ghost1", "game_state": "P",
                                 "teams": [], "linescores": []}) + "\n")
            fh.write(json.dumps({"game_id": "ghost2", "game_state": "P",
                                 "teams": [], "linescores": []}) + "\n")
        recs = load_games_jsonl(vpath)
        check("all three survive dedup (the log does not delete them)",
              len(recs), 3)
        check("only the played one counts as final",
              sorted(final_game_ids(vpath)), ["real"])
        counted = [g for g in recs if g.get("game_state") == "F"]
        check("a consumer filtering on final sees exactly one game",
              len(counted), 1)

        # NEGATIVE CONTROL: drop the final-state filter and the phantoms walk in.
        unfiltered = list(recs)
        check("negative control -- without the filter, phantoms are counted",
              len(unfiltered) > len(counted), True)

        print()
        if FAILED:
            print("FAILED: %d" % len(FAILED))
            for f in FAILED:
                print("   - %s" % f)
            return 1
        print("ALL FRESHNESS TESTS PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
