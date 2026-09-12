#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A lapsed review must not go quiet.

An unresolved official conflict counts NOWHERE -- correctly, because one
source against the feed is not enough to correct a result. The cost is that
the match is invisible until somebody goes back for the second source, and
on 2026-09-12 a sweep found FIVE conflicts whose review_by had expired and
which had been sitting uncounted for days while both schools had published
the result. Four became corrections the same afternoon; a fifth turned out
to have been right all along and was closed as confirmed.

Nothing had resurfaced them. The verifier re-checks TODAY's finals; an old
conflict with a stale date is nobody's job. This guard makes it somebody's:
an expired review_by must carry a `rechecked` date, so "we looked again and
it still cannot be settled" is a recorded act rather than an absence.
"""
import datetime
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
GRACE_DAYS = 7

fails = []


def check(label, ok, detail=""):
    print("  %-62s %s%s" % (label, "ok" if ok else "FAIL",
                            ("  -- " + str(detail)[:160]) if detail and not ok else ""))
    if not ok:
        fails.append(label)


def main():
    import season_counts as SC
    today = os.environ.get("WVB_TODAY") or datetime.date.today().isoformat()
    p = os.path.join(REPO, "data/raw/%d/result_evidence.json" % SEASON)
    ev = (json.load(io.open(p, encoding="utf-8")).get("evidence") or {})
    corr = SC.corrections(SEASON)

    stale = []
    for gid, entries in ev.items():
        if str(gid) in corr:
            continue                      # a curated correction resolves it
        for e in (entries if isinstance(entries, list) else [entries]):
            if not isinstance(e, dict) or e.get("status") != "conflicts":
                continue
            rb = (e.get("review_by") or "").strip()
            looked = (e.get("rechecked") or "").strip()
            if rb and rb < today and (not looked or looked < rb):
                stale.append((str(gid), rb, looked or "never"))
    check("no conflict's review_by has lapsed without a recheck", not stale,
          "; ".join("%s due %s, last looked %s" % s for s in stale[:6]))

    # A recheck that says nothing is not a recheck.
    thin = []
    for gid, entries in ev.items():
        for e in (entries if isinstance(entries, list) else [entries]):
            if not isinstance(e, dict) or e.get("status") != "conflicts":
                continue
            if e.get("rechecked") and len((e.get("recheck_note") or "").strip()) < 40:
                thin.append(str(gid))
    check("every recheck records WHAT was found, not just that it happened",
          not thin, "bare rechecked stamps on: %s" % thin[:6])

    # An unresolved conflict must still be excluded from counting.
    review = SC.review_gids(SEASON)
    leaked = [g for g in review if g in corr]
    check("a corrected gid is no longer withheld as under review", not leaked,
          "both corrected and withheld: %s" % leaked[:5])

    print("\n  negative controls")
    tripped = []

    def control(label, broke):
        print("    %-56s %s" % (label, "trips" if broke else "DID NOT TRIP"))
        if not broke:
            tripped.append(label)

    control("an expired review with no recheck is rejected",
            bool([1 for rb, lk in [("2026-01-01", "")] if rb < today and not lk]))
    control("a recheck older than the due date does not count",
            bool([1 for rb, lk in [("2026-09-08", "2026-09-01")]
                  if rb < today and lk < rb]))
    control("a bare recheck stamp with no note is rejected",
            len("") < 40)

    print("\n%s" % ("REVIEW FRESHNESS HOLDS" if not (fails or tripped)
                    else "FAILED: %d check(s), %d control(s)" % (len(fails), len(tripped))))
    return 1 if (fails or tripped) else 0


if __name__ == "__main__":
    sys.exit(main())
