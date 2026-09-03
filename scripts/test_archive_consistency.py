#!/usr/bin/env python3
"""Weekly-archive internal consistency (architect plan #6, 2026-09-03).

The archive is append-only and each frozen row must be coherent WITH
ITSELF -- its own captured ruler, cutoff and board -- never judged against
current artifacts (it should NOT match today; that is the point of a
freeze). Checks: every row names a known basis; each row's board is a
complete permutation with one source throughout; weeks never repeat within
a track; capture dates are Mondays where the freeze rule says Mondays; and
each team's gp is consistent with the row's own cutoff ordering
(a later week's gp never DECREASES for a team on the same basis)."""
import json
import os
import sys
import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


KNOWN_BASES = {"preseason", "digby", "blend", "live"}


def main():
    p = os.path.join(REPO, "data", "rankings_history_2026.jsonl")
    rows = [json.loads(l) for l in open(p) if l.strip()]
    board_rows = [r for r in rows if r.get("teams")]
    print("1. EVERY FROZEN ROW IS COHERENT WITH ITSELF (%d rows, %d with "
          "boards)" % (len(rows), len(board_rows)))
    import snapshot_rankings as SR
    for r in board_rows:
        wk = r.get("week")
        basis = SR.basis(r.get("source") or "")
        check("%s: basis %r is a known ruler" % (wk, r.get("source")),
              basis in KNOWN_BASES)
        teams = r["teams"]
        ranks = [t.get("rank") for t in teams]
        check("%s: the board is a complete permutation (no dup, no gap)"
              % wk, sorted(ranks) == list(range(1, len(ranks) + 1)),
              "n=%d dups=%d" % (len(ranks),
                                len(ranks) - len(set(ranks))))
        srcs = {SR.basis(t.get("source") or "") for t in teams}
        check("%s: ONE ruler throughout the frozen board" % wk,
              srcs == {basis}, srcs)
        names = [t.get("team") for t in teams]
        check("%s: no team appears twice" % wk,
              len(names) == len(set(names)))
    # weekly freezes land on Mondays (the rule snapshot_rankings states)
    for r in board_rows:
        d = r.get("date")
        if d:
            wd = datetime.date(*map(int, d.split("-"))).weekday()
            if r.get("source") == "preseason":
                # the 2026-08-22 bootstrap row predates the Monday-freeze
                # rule; append-only means it stays exactly as written
                print("  --   %s: preseason bootstrap row (captured %s), "
                      "exempt from the Monday rule" % (r.get("week"), d))
                continue
            check("%s: captured on a Monday (weekday %d)"
                  % (r.get("week"), wd), wd == 0, d)

    print("\n2. APPEND-ONLY DISCIPLINE")
    tracks = {}
    for r in rows:
        key = (r.get("track") or "board", r.get("week"))
        tracks.setdefault(key, 0)
        tracks[key] += 1
    dups = [k for k, v in tracks.items() if v > 1]
    check("one row per (track, week) -- a past week is never rewritten",
          not dups, dups)

    print("\n3. GP NEVER DECREASES ACROSS WEEKS ON ONE BASIS")
    seq = {}
    bad = []
    for r in sorted(board_rows, key=lambda x: x.get("week") or ""):
        basis = SR.basis(r.get("source") or "")
        for t in r["teams"]:
            k = (basis, t.get("team"))
            prev = seq.get(k)
            gp = t.get("gp") or 0
            if prev is not None and gp < prev:
                bad.append((r.get("week"), t.get("team"), prev, gp))
            seq[k] = gp
    # ⚠ DOCUMENTED BREAKPOINT: between the W34 and W35 freezes the
    # counting contract was adopted (2026-08-31 reliability audit) and the
    # blend's per-team matches tightened to rating-eligible-with-line --
    # so two W35 cells (Pittsburgh, Texas) read LOWER than W34's looser
    # count. The archive is append-only; those cells stay as frozen, the
    # exception is named here, and any decrease OUTSIDE it still fails.
    _known = {("2026-W35", "Pittsburgh"), ("2026-W35", "Texas")}
    new_bad = [b for b in bad if (b[0], b[1]) not in _known]
    if bad and not new_bad:
        print("  --   %d known decrease(s) from the W34->W35 counting-"
              "contract change, documented above" % len(bad))
    check("a team's frozen gp never decreases week over week (same basis, "
          "outside the documented W35 contract change)",
          not new_bad, new_bad[:4])

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL ARCHIVE-CONSISTENCY CHECKS HOLD")


if __name__ == "__main__":
    main()
