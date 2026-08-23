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
    check(all(r.get("source") in ("live", "preseason") for r in rows),
          "every archived week names its source")


def main():
    for fn in (test_mover_direction, test_snapshot_is_weekly_and_append_only,
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
