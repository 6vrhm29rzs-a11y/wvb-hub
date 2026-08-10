#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Semantic invariants on what the dashboard actually SHOWS.

WHY THIS EXISTS. The bug that motivated it passed every existing check: the
crawl was correct, the reconcile was 348/348, the freshness tests passed, and CI
was green. The 2026 view rendered "Ark.-Pine Bluff 2025 Pts/Set -14.31" because
`pps` had been repointed from offense-only points/set to opponent-adjusted NET
points/set, and only one of its four call sites was renamed. Every number was
computed correctly and displayed under a heading that made it wrong.

Nothing in the suite guarded "is this number under the right heading". That is
what this file is for. The generic form of the failure is a quantity appearing
where its SIGN, RANGE or UNITS are impossible, so that is what gets asserted --
cheap, and it catches an entire class of mislabelling rather than one instance.

Checks the BUILT artifact (output/vb_dashboard.html) plus data/rating_*.json,
because what matters is what is served, not what an intermediate script thought.

Run: python3 scripts/test_display_invariants.py
No network. Exits non-zero on violation.
"""

import datetime
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
DASH = os.path.join(REPO, "output", "vb_dashboard.html")
RATING = os.path.join(REPO, "data", "rating_%d.json" % SEASON)

FAILS = []


def bad(what, detail):
    FAILS.append("%s: %s" % (what, detail))


def ok(name, n=None):
    print("  %-58s ok%s" % (name, "" if n is None else "  (%d checked)" % n))


def load_model():
    if not os.path.exists(DASH):
        return None
    h = open(DASH, encoding="utf-8").read()
    m = re.search(r"const MODEL = (\{.*?\});\n", h, re.S)
    if not m:
        return None
    return json.loads(m.group(1).replace("<\\/", "</"))


# Fields that are semantically NON-NEGATIVE. A negative here means a
# differential (or some other signed quantity) has been plumbed into a slot that
# means a count or a rate. That is exactly the bug this file was written for.
NON_NEGATIVE = {
    "opps": "offense points/set (kills+aces+blocks)",
    "kps": "kills per set",
    "aps": "aces per set",
    "bps": "blocks per set",
    "gp": "games played",
}

# Plausible ranges, to catch unit errors and per-set/per-match confusion.
RANGES = {
    "kps": (3.0, 25.0),
    "aps": (0.0, 5.0),
    "bps": (0.0, 5.0),
    "opps": (4.0, 30.0),
    "pps": (-30.0, 30.0),      # adjusted margin: signed, but bounded
}


def check_model(M):
    teams = M.get("teams") or []
    if not teams:
        bad("model", "no teams in the built dashboard")
        return
    print("dashboard payload (%d teams)" % len(teams))

    # --- sign invariants ---
    for field, label in sorted(NON_NEGATIVE.items()):
        offenders = [(t.get("team"), t.get(field)) for t in teams
                     if t.get(field) is not None and t.get(field) < 0]
        if offenders:
            bad("negative %s" % field,
                "%s must be >= 0; %d violations e.g. %s" % (
                    label, len(offenders), offenders[:3]))
        else:
            ok("%s (%s) is never negative" % (field, label), len(teams))

    # --- range invariants ---
    for field, (lo, hi) in sorted(RANGES.items()):
        vals = [(t.get("team"), t.get(field)) for t in teams
                if t.get(field) is not None]
        out = [(n, v) for n, v in vals if not (lo <= v <= hi)]
        if out:
            bad("%s out of range" % field,
                "expected [%s, %s]; %d violations e.g. %s" % (lo, hi, len(out), out[:3]))
        else:
            ok("%s within [%s, %s]" % (field, lo, hi), len(vals))

    # --- ordering invariant ---
    # NOTE: the payload carries no `rank` field -- the page computes ranks
    # client-side from `composite`. So the invariant that actually holds here is
    # that the payload is pre-sorted by composite descending; the row number the
    # user sees is derived from that order. (An earlier version of this test
    # asserted on a `rank` field that does not exist and failed for that reason
    # -- a broken check, not a finding.)
    comps = [t.get("composite") for t in teams]
    if any(c is None for c in comps):
        bad("composite", "%d teams have no composite score"
            % sum(1 for c in comps if c is None))
    elif any(comps[i] < comps[i + 1] for i in range(len(comps) - 1)):
        drops = [(teams[i].get("team"), comps[i], teams[i + 1].get("team"), comps[i + 1])
                 for i in range(len(comps) - 1) if comps[i] < comps[i + 1]]
        bad("ordering", "payload not sorted by composite desc; %d inversions e.g. %s"
            % (len(drops), drops[:2]))
    else:
        ok("payload sorted by composite descending (drives displayed rank)", len(comps))

    # --- delta consistency against the payload's own ordering ---
    mism = []
    for i, t in enumerate(teams, 1):
        d, rr = t.get("delta"), t.get("rpiRank")
        if d is None or rr is None:
            continue
        if d != rr - i:
            mism.append((t.get("team"), d, rr - i))
    if mism:
        bad("delta", "delta != rpiRank - position for %d teams e.g. %s"
            % (len(mism), mism[:3]))
    else:
        ok("delta == official RPI rank minus displayed position")

    # --- record parses and is non-negative ---
    badrec = []
    for t in teams:
        rec = t.get("record")
        if not rec:
            continue
        m = re.match(r"^(\d+)-(\d+)$", str(rec))
        if not m:
            badrec.append((t.get("team"), rec))
        elif t.get("gp") is not None and int(m.group(1)) + int(m.group(2)) != t["gp"]:
            badrec.append((t.get("team"), "%s vs gp=%s" % (rec, t["gp"])))
    if badrec:
        bad("record", "malformed or inconsistent with games played: %s" % badrec[:3])
    else:
        ok("record parses as W-L and matches games played")

    # --- display names must not be raw join keys ---
    keyish = [t.get("team") for t in teams
              if t.get("team") and t["team"] == t["team"].lower()
              and re.match(r"^[a-z0-9 ]+$", t["team"])]
    if keyish:
        bad("team names", "look like normalized join keys, not display names: %s"
            % keyish[:5])
    else:
        ok("team names are display names, not join keys", len(teams))

    # --- low-confidence flag agrees with games played ---
    LOW = 10
    wrong = [t.get("team") for t in teams
             if t.get("gp") is not None
             and bool(t.get("lowconf")) != (t["gp"] < LOW)]
    if wrong:
        bad("lowconf", "flag disagrees with games played for %d teams e.g. %s"
            % (len(wrong), wrong[:3]))
    else:
        ok("low-confidence flag agrees with games played (<%d)" % LOW)

    # --- freshness metadata must exist and be sane ---
    gen = M.get("generated_at")
    if not gen:
        bad("freshness", "no generated_at in the payload; the staleness banner "
                         "cannot work without it")
    else:
        try:
            t = datetime.datetime.strptime(gen.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
            if t > datetime.datetime.utcnow() + datetime.timedelta(hours=1):
                bad("freshness", "generated_at is in the future: %s" % gen)
            else:
                ok("generated_at present and not in the future")
        except Exception:
            bad("freshness", "generated_at unparseable: %r" % gen)

    dt = M.get("data_through")
    if dt:
        try:
            d = datetime.datetime.strptime(dt, "%Y-%m-%d").date()
            if d > datetime.date.today():
                bad("freshness", "data_through is in the future: %s" % dt)
            else:
                ok("data_through present and not in the future")
        except Exception:
            bad("freshness", "data_through unparseable: %r" % dt)


def check_rating():
    if not os.path.exists(RATING):
        print("rating file (season %d): absent -- skipping (normal pre-season)" % SEASON)
        return
    R = json.load(open(RATING))
    teams = R.get("teams") or []
    print("rating payload (%d teams)" % len(teams))

    cr = [t.get("composite_rank") for t in teams]
    if sorted(x for x in cr if x is not None) != list(range(1, len(teams) + 1)):
        bad("composite_rank", "must be exactly 1..%d, unique" % len(teams))
    else:
        ok("composite_rank is exactly 1..N, unique", len(teams))

    neg = [t["team"] for t in teams
           if t.get("games_played") is not None and t["games_played"] < 0]
    if neg:
        bad("games_played", "negative for %s" % neg[:3])
    else:
        ok("games_played non-negative", len(teams))

    badres = []
    for t in teams:
        for k in ("vs_rpi_top25", "vs_rpi_top50"):
            v = (t.get("resume") or {}).get(k)
            if v is None:
                continue
            if not re.match(r"^\d+-\d+$", str(v)):
                badres.append((t.get("team"), k, v))
    if badres:
        bad("resume", "malformed W-L strings: %s" % badres[:3])
    else:
        ok("resume records parse as W-L")

    w = (R.get("meta") or {}).get("weights") or {}
    if w.get("hand_entered") is True:
        bad("weights", "marked hand_entered; they are supposed to be fitted")
    elif not w.get("fitted"):
        bad("weights", "not marked as fitted")
    else:
        ok("rating weights are fitted, not hand-entered")


def main():
    print("=" * 68)
    print("DISPLAY INVARIANTS -- is each number under the right heading?")
    print("=" * 68)
    M = load_model()
    if M is None:
        print("no built dashboard payload found -- skipping (pre-season is fine)")
    else:
        check_model(M)
    print()
    check_rating()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL DISPLAY INVARIANTS HOLD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
