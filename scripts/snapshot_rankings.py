#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weekly ranking snapshot -- a poll-style archive with movement.

Cody's ask (2026-08-23): a running ranking that updates constantly, PLUS a
saved history taken Monday mornings before each week's games, the way the AVCA
and VolleyTalk polls publish.

The running ranking is the page itself: it rebuilds nightly and, once 50 matches
have been played, comes from the in-season composite rather than the preseason
projection. This script is the OTHER half -- it freezes that ranking once a week
so movement can be shown and so there is a record of what we said BEFORE the
week's results, which is the only version of a ranking that can be scored later.

Rules, deliberate:
  * MONDAY ONLY by default. The daily job runs 09:15 UTC = 05:15 ET, before any
    match starts, so a Monday snapshot is genuinely pre-week. `--force` overrides
    for a manual capture.
  * ONE SNAPSHOT PER ISO WEEK. Re-running is a no-op, so the daily job can call
    it unconditionally without the archive growing a row a day.
  * APPEND-ONLY. A past week is never rewritten -- that is the whole point of an
    archive. If the model changes, the old rows stay as what we actually said.
  * It records `rank_source`, because a preseason rank and a results-based rank
    are different claims and the archive must not blur them.

Python 3.9 target.
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weekly  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
# ⚠ REDIRECTABLE FOR TESTS, AND THAT IS NOT A CONVENIENCE. This archive is the
# one artifact in the repo that cannot be rebuilt, and it is append-only -- so a
# test (or a careless --force while developing) that writes a row into the real
# file has damaged the record. I did exactly that once and had to restore it
# from git. Tests point WVB_HISTORY_OUT at a temp file.
OUT = os.environ.get(
    "WVB_HISTORY_OUT",
    os.path.join(REPO, "data", "rankings_history_%d.jsonl" % SEASON))


# ⚠ ONE NAME PER RULER. This archive already contains a week written as
# "digby" and the rankings board now calls the same ordering "blend" -- the
# blended projection-plus-results from digby_top25.py, one ruler, two words.
# The movement rule compares only within a basis, so two names for one thing
# silently blanks the movement column instead of erroring. The archive is
# APPEND-ONLY and the "digby" week stays exactly as written; it is normalised
# on READ.
BASIS_ALIASES = {"digby": "blend"}


def basis(name):
    # type: (str) -> str
    """Canonical name for a ranking basis. Never rewrites the archive."""
    return BASIS_ALIASES.get(name or "", name or "")


def load(path):
    p = os.path.join(REPO, path)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p))
    except ValueError:
        return None


def existing_weeks():
    weeks = set()
    if not os.path.exists(OUT):
        return weeks
    with open(OUT) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                weeks.add(json.loads(line)["week"])
            except (ValueError, KeyError):
                continue
    return weeks


# THE SOURCES THIS ARCHIVE CAN CARRY, declared once so the guard can import
# them instead of restating them. They drifted apart exactly once: "digby" was
# added here when the weekly freeze moved to the Top 25, the test kept
# whitelisting ("live", "preseason"), and because the snapshot only runs on
# MONDAYS the mismatch lay dormant for a week and then failed the first real
# Monday of the season -- taking the commit step with it, so the one artifact
# that cannot be rebuilt was never archived.
# ⚠ "blend" WAS MISSING AND THE WRITER COULD ALREADY EMIT IT. current_ranking()
# returns "blend" for the Top-25 blend; this tuple still listed only the older
# "digby" spelling, so the first row actually written with the new name failed
# the archive-shape guard -- the SECOND time this exact drift has happened.
SOURCES = ("blend", "digby", "live", "preseason")


def current_ranking():
    """Whatever the page is showing right now.

    PRECEDENCE -- live, then blend, then preseason -- and it MUST match
    build_rankings_board.py's, because this archive is meant to record the
    ruler the page was showing.

    ⚠ THIS DOCSTRING USED TO SAY "Digby's Top 25 comes first" and the code did
    exactly that. The reasoning was sound against the only alternative it knew:
    the board's order was a preseason projection until 50 matches, so archiving
    it weekly in August stored the same numbers over and over -- a history of
    nothing -- while the Top 25 blends the projection with results from the
    first match onward. What it did not anticipate is the board gaining a THIRD
    source and reordering to live-first. Blend still beats preseason for that
    original reason; it does NOT beat a fitted rating.

    The `source` field keeps the three apart, and the movement rule already
    refuses to compare across bases -- subtracting a rank on one ruler from a
    rank on another is arithmetic on two different things, which is the bug
    `test_rankings_history.py` exists to prevent.
    """
    # ⚠ LIVE FIRST, AND THIS WAS INVERTED. The note below is the reasoning for
    # putting the blend AHEAD OF THE PRESEASON PROJECTION, and it still holds.
    # What it did not anticipate is that build_rankings_board.py later gained a
    # THIRD source and its precedence became live -> blend -> preseason. This
    # function kept blend first, so with a fitted rating on disk the BOARD said
    # "rank source: live" while the snapshot recorded the week as "blend" --
    # and stored the blend's ranks, not the ones on the page.
    # That matters on a date: the season is at 9 matches, 2026-08-28 schedules
    # 196 and the 29th another 179, so rating_2026.json appears this weekend
    # and Monday is the first live freeze. The archive is APPEND-ONLY; a week
    # written under the wrong ruler, with the wrong numbers, cannot be
    # corrected later. Measured with a synthetic rating file before it could
    # happen: board said `live`, snapshot said `blend`.
    rows = []
    live = load("data/rating_%d.json" % SEASON) or {}
    for r in (live.get("teams") or []):
        if r.get("composite_rank"):
            rows.append({"team": r["team"], "rank": r["composite_rank"],
                         "source": "live", "gp": r.get("games_played"),
                         "record": ("%s-%s" % (r.get("wins"), r.get("losses"))
                                    if r.get("wins") is not None else None)})
    if rows:
        rows.sort(key=lambda x: x["rank"])
        return rows, "live"

    t25 = load("data/digby_top25_%d.json" % SEASON) or {}
    # ALL 348, not the 35 that are displayed. The first blended week archived
    # only the Top 25 plus also-receiving, so movement could never be computed
    # for team 36 onward -- a ranking board of 348 rows with 313 permanently
    # blank movement cells. digby_top25.py now emits the full ordering.
    _rec = dict((r["team"], r.get("record"))
                for r in ((t25.get("top") or []) + (t25.get("also_receiving") or []))
                if r.get("team"))
    for r in (t25.get("all") or []):
        if r.get("rank"):
            rows.append({"team": r["team"], "rank": r["rank"], "source": "blend",
                         "gp": r.get("matches") or 0,
                         "record": _rec.get(r["team"])})
    if rows:
        rows.sort(key=lambda x: x["rank"])
        return rows, "blend"

    # (the live branch is at the TOP of this function now -- a second copy
    #  here would be unreachable, and dead code that looks live is exactly the
    #  liability the `a.ep` sort key turned out to be)
    proj = load("data/projection_%d.json" % SEASON) or {}
    for r in (proj.get("teams") or []):
        if r.get("talent_rank"):
            rows.append({"team": r["team"], "rank": r["talent_rank"],
                         "source": "preseason", "gp": 0, "record": None})
    rows.sort(key=lambda x: x["rank"])
    return rows, "preseason"


def existing_cutoffs():
    """Cutoffs already frozen on the digby_weekly track.

    ⚠ KEYED BY CUTOFF, NOT BY THE DAY WE RAN. The legacy rows key on the ISO
    week of their CAPTURE date; a weekly freeze keys on the Sunday it covers,
    which is the thing that is actually unique. Those two can collide -- the
    preseason row sits at 2026-W34 and the first real cutoff (Aug 23) is also
    W34 -- so a week-only check would refuse to ever write the first Digby
    Weekly. Legacy rows carry no `track` and are never touched.
    """
    seen = set()
    if not os.path.exists(OUT):
        return seen
    with open(OUT) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("track") == "digby_weekly" and r.get("cutoff"):
                seen.add(r["cutoff"])
    return seen


def main():
    argv = sys.argv[1:]
    force = "--force" in argv

    today = datetime.date.today()
    cutoff = weekly.prior_sunday(today)
    label = weekly.week_label(cutoff)

    if today.weekday() != 0 and not force:
        print("not Monday (%s) -- no snapshot. Use --force to capture anyway."
              % today.isoformat())
        return 0
    if cutoff.isoformat() in existing_cutoffs():
        print("%s already frozen -- nothing to do." % label)
        return 0

    # ⚠ THE GATE. A weekly freeze may only be written once every match dated on
    # or before the cutoff is FINAL. A poll published while games are still
    # being played is not a poll, and a partial one would be indistinguishable
    # from a complete one a week later.
    st = weekly.status(SEASON, today=today)
    if not st["publishable"] and not force:
        blocking = st["blocking"]
        why = {}
        for b in blocking:
            why[b["why"]] = why.get(b["why"], 0) + 1
        print("%s NOT frozen -- %d match(es) through the cutoff are not final: %s"
              % (label, len(blocking),
                 ", ".join("%d %s" % (v, k) for k, v in sorted(why.items()))))
        for b in blocking[:5]:
            print("    %s  %s  %s" % (b["date"], b["why"],
                                      " vs ".join(x or "?" for x in b["teams"])))
        if len(blocking) > 5:
            print("    ... and %d more" % (len(blocking) - 5))
        print("  The calendar shows this as WAITING. Nothing partial is saved.")
        print("  A fixture the SOURCE has withdrawn no longer blocks -- see "
              "scripts/fixture_disposition.py, which evidences that from the "
              "saved scoreboard for the date. Anything still listed here is "
              "genuinely unresolved, not merely old.")
        return 0

    rows, source = current_ranking()
    if not rows:
        print("no ranking available to snapshot")
        return 0

    rec = {
        # the ISO week OF THE CUTOFF, so a week means the games it covers
        "week": weekly.iso_week(cutoff),
        "track": "digby_weekly",
        "label": label,
        "cutoff": cutoff.isoformat(),
        "cutoff_tz": st["cutoff_tz"],
        "captured_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": today.isoformat(),
        "season": SEASON,
        "source": source,
        "source_tier": "DERIVED",
        "finals_included": st["finals"],
        # ⚠ THREE STATES, AND A FORCED ROW IS MARKED FOREVER.
        #   complete                  -- every match through the cutoff played
        #   complete_with_withdrawals -- the rest were withdrawn BY THE SOURCE,
        #                                with evidence, and are listed below
        #   forced                    -- a human overrode a real blocker
        # A forced row can never later be read as either of the other two, and
        # it keeps the count and the reasons it overrode.
        "completeness": (st["state"] if st["publishable"] else "forced"),
        "blocking_at_capture": len(st["blocking"]),
        "blocking_reasons": sorted(set(b["why"] for b in st["blocking"])),
        "withdrawn_excluded": len(st["withdrawn"]),
        # The policy that produced those verdicts, stamped at capture: a later
        # change to the evidence rule must not silently reinterpret this row.
        "disposition_policy": st.get("policy"),
        # ⚠ THE NOTE MUST DESCRIBE THIS ROW, NOT THE HAPPY CASE. It said
        # "after every match through the cutoff went final", which is false of
        # a row that excluded withdrawn fixtures -- a sentence that would have
        # quietly overstated the archive every week from here on.
        "note": (("Frozen after every match through the cutoff went final."
                  if st["state"] == "complete" else
                  ("Frozen after every match through the cutoff was either "
                   "final or withdrawn by the source. %d withdrawal(s) were "
                   "excluded, each evidenced by the saved scoreboard for its "
                   "date." % len(st["withdrawn"]))
                  if st["publishable"] else
                  ("FORCED. %d match(es) through the cutoff were still "
                   "unresolved when this was written; a human overrode the "
                   "gate. This row is not a complete week."
                   % len(st["blocking"])))
                 + " Append-only: a past week is never rewritten, so this "
                   "records what we actually said at the time, not what the "
                   "current model would say about the past."),
        "teams": rows,
    }
    with open(OUT, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print("captured %s (%s): %d teams, %d finals, %d source-withdrawn "
          "excluded, state=%s -> %s"
          % (label, source, len(rows), st["finals"], len(st["withdrawn"]),
             rec["completeness"], OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
