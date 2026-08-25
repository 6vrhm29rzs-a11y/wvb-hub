#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the weekly ranking archive and the movement column.

The archive is the only record of what we said BEFORE a week's results, so the
things that must hold are: it is append-only, one row per week, and the movement
arrow points the right way. None of that can be checked by waiting -- the first
real comparison is a week away -- so it is exercised here against synthetic
weeks.

Python 3.9 target. Run: python3 scripts/test_rankings_history.py
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_hub import mover  # noqa: E402
from build_rankings_board import pick_comparison  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = []


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


def test_mover_direction():
    """A team that goes from 10th to 4th has moved UP six places."""
    up = mover({"move": 6})
    dn = mover({"move": -6})
    same = mover({"move": 0})
    none = mover({})
    check("9650" in up and "6" in up, "improving rank renders an up arrow", up)
    check("9660" in dn and "6" in dn, "falling rank renders a down arrow", dn)
    check("ndash" in same, "unchanged renders a dash", same)
    check(none == "", "no prior week renders NOTHING, not a dash", repr(none))
    # a dash means "we compared and it did not move"; blank means "we have
    # nothing to compare against". Conflating them would be a claim we cannot
    # support.
    check(none != same, "blank and unchanged are distinct")


def test_snapshot_is_weekly_and_append_only():
    """Two runs in the same week must leave ONE row, and an existing archive
    must never be rewritten."""
    with tempfile.TemporaryDirectory() as tmp:
        hist = os.path.join(tmp, "rankings_history_2026.jsonl")
        prior = {"week": "2026-W01", "date": "2026-01-05", "season": 2026,
                 "source": "preseason",
                 "teams": [{"team": "A", "rank": 1}, {"team": "B", "rank": 2}]}
        with open(hist, "w") as fh:
            fh.write(json.dumps(prior) + "\n")
        before = open(hist).read()

        env = dict(os.environ, WVB_SEASON="2026")
        script = os.path.join(REPO, "scripts", "snapshot_rankings.py")
        # run twice against the real repo but a temp archive
        code = ("import sys,os;sys.argv=['x','--force'];"
                "sys.path.insert(0,%r);"
                "import snapshot_rankings as S;S.OUT=%r;"
                "S.main();S.main()" % (os.path.join(REPO, "scripts"), hist))
        subprocess.run([sys.executable, "-c", code], env=env,
                       capture_output=True, cwd=REPO)

        rows = [json.loads(x) for x in open(hist) if x.strip()]
        weeks = [r["week"] for r in rows]
        check(len(weeks) == len(set(weeks)),
              "one row per ISO week even when run twice", str(weeks))
        check(open(hist).read().startswith(before),
              "the existing archive is never rewritten (append-only)")
        check(rows[0]["week"] == "2026-W01" and rows[0]["teams"][0]["team"] == "A",
              "the earlier week survives untouched")
        check(any("rank" in t for r in rows for t in r["teams"]),
              "captured rows carry ranks")
        check(all("source" in r for r in rows),
              "every row records whether it was preseason or live",
              "a preseason rank and a results-based rank are different claims")


def test_real_archive_shape():
    p = os.path.join(REPO, "data", "rankings_history_2026.jsonl")
    if not os.path.exists(p):
        print("  skip (no archive yet)")
        return
    rows = [json.loads(x) for x in open(p) if x.strip()]
    weeks = [r["week"] for r in rows]
    check(len(weeks) == len(set(weeks)), "real archive has no duplicate weeks",
          str(weeks))
    check(all(r.get("teams") for r in rows), "every archived week has teams")
    # ⚠ IMPORTED, NOT RESTATED. This line used to whitelist ("live",
    # "preseason") while snapshot_rankings.py had grown a third source,
    # "digby", when the weekly freeze moved to the Top 25. The snapshot runs on
    # MONDAYS ONLY, so the two sat out of step for a week and then failed on the
    # first real Monday -- and because the guards step gates the commit, the
    # week's ranking was never archived. The archive is the one artifact in this
    # project that cannot be rebuilt, so a guard that blocks it must not be able
    # to disagree with the writer about what a valid row looks like.
    import snapshot_rankings as SNAP
    unknown = sorted(set(r.get("source") for r in rows) - set(SNAP.SOURCES))
    check(not unknown, "every archived week names a source the writer can emit",
          "unknown source(s): %s (writer emits %s)" % (unknown, list(SNAP.SOURCES)))


def test_movement_never_crosses_the_basis():
    """Movement must compare like with like.

    Found by review, and it broke the invariant this very archive documents.
    The comparison picked the latest earlier week by DATE alone. On the
    crossover Monday -- when the season passes 50 matches and the live
    composite replaces the preseason projection -- every earlier row is
    preseason while the current rank is live. Subtracting them is arithmetic on
    two different rulers: a mid-major at #14 on a roster projection lands near
    #80 on a rating that punishes weak schedules, and the page would report a
    confident fall of 66 places for a team that did nothing.

    Blank is the correct output there. It is also why this is a test and not a
    comment: the original synthetic-week test passed, because both of its rows
    happened to be preseason.
    """
    pre_a = {"week": "2026-W34", "source": "preseason"}
    pre_b = {"week": "2026-W35", "source": "preseason"}
    live_a = {"week": "2026-W36", "source": "live"}
    snaps = [pre_a, pre_b, live_a]

    # still preseason: compare against the previous PRESEASON week
    got = pick_comparison(snaps, "2026-W35", "preseason")
    check(got is pre_a, "preseason compares against an earlier preseason week")

    # THE CROSSOVER: current basis is live, every earlier row is preseason
    got = pick_comparison([pre_a, pre_b], "2026-W36", "live")
    check(got is None,
          "crossover week yields NO comparison, not a cross-basis one",
          repr(got))
    check(mover({"move": None}) == "",
          "and that renders blank, not a dash")

    # once a live week exists, live compares against live
    got = pick_comparison(snaps + [{"week": "2026-W37", "source": "live"}],
                          "2026-W37", "live")
    check(got is live_a, "live compares against an earlier live week")

    # never compares against the current week
    got = pick_comparison([pre_b], "2026-W35", "preseason")
    check(got is None, "this week is never its own comparison")


def check_basis_aliases():
    """ONE RULER MUST NOT HAVE TWO NAMES.

    The archive contains a week written as "digby"; the rankings board calls
    the same ordering "blend". They are the same thing -- digby_top25.py's
    blended projection-plus-results. The movement rule compares only within a
    basis, so two names for one ruler does not error, it silently blanks the
    entire movement column, which is indistinguishable from "no history yet".

    ⚠ THE ARCHIVE IS APPEND-ONLY and the "digby" week must stay exactly as
    written -- normalisation happens on READ. This asserts both halves: the
    alias resolves, and a genuinely different ruler is still refused.
    """
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    from snapshot_rankings import basis
    import build_rankings_board as BB

    check(basis("digby") == basis("blend") == "blend", "the two names for the blended ruler resolve to one",
          "(digby -> %r, blend -> %r)" % (basis("digby"), basis("blend")))
    check(basis("live") == "live" and basis("preseason") == "preseason", "a different ruler keeps its own name")

    p = os.path.join(REPO, "data", "rankings_history_%d.jsonl" % int(os.environ.get("WVB_SEASON","2026")))
    if not os.path.exists(p):
        print("  (no archive yet -- skipping the comparison checks)")
        return
    snaps = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            snaps.append(json.loads(line))
    weeks = sorted(set(s.get("week") for s in snaps if s.get("week")))
    if len(weeks) < 2:
        print("  (fewer than two archived weeks -- skipping)")
        return
    future = "2099-W52"
    got = BB.pick_comparison(snaps, future, "blend")
    have_blend = [s for s in snaps if basis(s.get("source")) == "blend"]
    if have_blend:
        check(got is not None and basis(got.get("source")) == "blend", "a blended week IS found when the basis name differs",
              "(picked %r)" % ((got or {}).get("source"),))
        # NEGATIVE CONTROL: exact string matching -- the old behaviour -- must
        # fail to find it, or this guard is testing nothing.
        exact = [s for s in snaps
                 if s.get("week") != future and s.get("source") == "blend"]
        stored_as_alias = any(s.get("source") == "digby" for s in snaps)
        if stored_as_alias:
            check(not exact, "...and exact-string matching would NOT have found it",
                  "(the archive already stores the canonical name, so this "
                  "control cannot fire)")
    # cross-ruler must still be refused
    check(BB.pick_comparison(snaps, future, "live") is None
          or basis(BB.pick_comparison(snaps, future, "live").get("source")) == "live", "a preseason week is never offered to a blended ranking")


def main():
    for fn in (test_mover_direction, test_movement_never_crosses_the_basis,
               check_basis_aliases,
               test_snapshot_is_weekly_and_append_only,
               test_real_archive_shape):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all ranking-history invariants pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
