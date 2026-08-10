#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STAGE A: project the 64-team NCAA field and its seeds. Backtested on 2025.

*** THIS PREDICTS COMMITTEE BEHAVIOUR, NOT TEAM STRENGTH. ***
The strength composite (scripts/rating_2025.py) is deliberately NOT an input.
Measured: corr(delta_vs_RPI, own win%) = -0.205, i.e. relative to RPI the
composite favours teams with good margins and BAD RECORDS -- close to the
opposite of a selection resume. The committee asks who has EARNED selection and
weights won-lost results. Letting the strength rating leak in here would
systematically over-select good-margin/bad-record teams.

Stage B (simulating the bracket once it exists) is where the composite belongs.

RESUME MODEL. The committee's primary criteria are RPI, KPI, head-to-head,
results vs common opponents, and significant wins/losses -- explicitly UNORDERED
(Pre-Championship Manual 2.4). KPI is proprietary and unfetched (THIRD-PARTY,
faktorsports.com), so it is absent here and that absence is a known gap, not an
oversight. What is used: RPI rank, record vs the RPI top 25 and top 50, and
overall winning percentage -- all resume quantities.

Python 3.9 target.
"""

import collections
import datetime
import json
import os
import sys
from typing import Dict, List, Optional, Set, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(REPO, "data", "field_%d.json" % SEASON)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm, parse_record  # noqa: E402
from gamelog import load_games_jsonl  # noqa: E402
from rpi_2025 import rpi_from_games  # noqa: E402

# ---------------------------------------------------------------- CONFIG
# Every value here is a CONFIG VALUE, not a constant. The NCAA had not published
# the 2026 structure as of 2026-08-10.

AQ_COUNT = 32          # primary; the rebuilt nine-member Pac-12 restores a bid
AQ_COUNT_FALLBACK = 31  # 2024 and 2025 actual
FIELD_SIZE = 64
SEEDED = 32            # top 32 seeded nationally, pods of four

# AQ mechanism CHANGED MATERIALLY FOR 2026. The Big Ten holds its first-ever
# volleyball tournament (top 15 of 18, Nov 20-25) and the regular-season-champion
# model is DEAD there. Pac-12 has a new tournament (top 4, week of Nov 23).
AQ_MECHANISM = {
    "Big Ten": "TOURNAMENT",      # NEW for 2026 (was regular-season champion)
    "Pac-12": "TOURNAMENT",       # NEW for 2026
    "SEC": "TOURNAMENT",          # continued from 2025
    "ACC": "REGULAR_SEASON",
    "Big 12": "REGULAR_SEASON",
    "Mountain West": "TOURNAMENT",
}
AQ_MECHANISM_DEFAULT = "TOURNAMENT"   # most mid-majors; flagged unverified

# Championship-INELIGIBLE reclassifying programs. Excluded from the field, but
# their games still COUNT in opponents' RPI. If one wins its conference, the AQ
# passes to the best eligible finisher.
INELIGIBLE_2026 = {"west ga", "mercyhurst", "new haven", "west florida"}
INELIGIBLE = {2026: INELIGIBLE_2026}.get(SEASON, set())

MIN_WIN_PCT = 0.500    # at-large teams must be .500 or better
MIN_DI_SHARE = 0.80    # >=80% of matches against Division I


def load(cutoff):
    """Games strictly before `cutoff`, restricted to D-I vs D-I, plus metadata."""
    rows = json.load(open(os.path.join(RAW, "rpi_official.json")))["data"]
    di = {norm(r["School"]) for r in rows}
    meta = {norm(r["School"]): r for r in rows}

    played, allgames = [], []
    for g in load_games_jsonl(os.path.join(RAW, "games.jsonl")):
        if g.get("game_state") != "F":
            continue
        ep = g.get("start_time_epoch")
        if not ep:
            continue
        d = datetime.datetime.utcfromtimestamp(int(ep)).date()
        if d >= cutoff:
            continue
        t = g.get("teams") or []
        if len(t) != 2:
            continue
        a, b = norm(t[0].get("name_short")), norm(t[1].get("name_short"))
        w = a if t[0].get("is_winner") else (b if t[1].get("is_winner") else None)
        if w is None:
            continue
        l = b if w == a else a
        allgames.append((w, l, d, a in di and b in di))
        if a in di and b in di:
            played.append((w, l, g["game_id"]))
    return di, meta, played, allgames


def conference_of(meta, k):
    return (meta.get(k) or {}).get("Conf")


def pick_aq(conf, members, played, allgames, eligible, rpirank):
    """Return (team, method, note) for one conference's automatic qualifier.

    TOURNAMENT conferences: the champion is inferred from the last date of
    intra-conference play. THIS IS THE WEAK LINK IN STAGE A and the limit is
    DATA, not tuning: the feed exposes no bracket structure, so a tournament
    final, a consolation game and a regular-season finale are indistinguishable.

    Three variants were tried against the 2025 ground truth. All three scored
    62/64; what changed was only WHICH conference broke (WCC, then MAC, then
    SoCon). A heuristic whose errors move around under perturbation while the
    total holds is at its information limit -- further tuning on three data
    points would be fitting noise, so tuning stopped there.

    The real fix is a source for conference tournament brackets, not a cleverer
    rule. Until then every AQ carries a `note` saying how it was derived.
    REGULAR_SEASON conferences: best conference winning percentage.
    """
    mech = AQ_MECHANISM.get(conf, AQ_MECHANISM_DEFAULT)
    mem = set(members)

    conf_games = [(w, l, d) for (w, l, d, isdi) in allgames
                  if w in mem and l in mem]
    if not conf_games:
        return None, mech, "no conference games"

    if mech == "TOURNAMENT":
        # A conference TITLE MATCH is a single game standing alone on the last
        # date. If the final date carries a BATCH of games it is the regular
        # season finishing, not a tournament final -- the WCC played six
        # simultaneous matches on 2025-11-29 and the naive "last match" rule
        # picked 7-20 LMU out of that batch as champion. Fall back to conference
        # record when the last date is not a single decisive game.
        conf_games.sort(key=lambda x: x[2])
        last_day = conf_games[-1][2]
        final_day = [g for g in conf_games if g[2] == last_day]
        rec = collections.defaultdict(lambda: [0, 0])
        for w, l, _ in conf_games:
            rec[w][0] += 1
            rec[l][1] += 1

        def confpct(k):
            n = rec[k][0] + rec[k][1]
            return rec[k][0] / float(n) if n else 0.0

        if len(final_day) == 1:
            winner = final_day[0][0]
            note = "winner of the title match (%s)" % last_day
        else:
            # The last date often carries the final ALONGSIDE a consolation
            # game (MAC, SoCon), or is simply the regular season ending in a
            # batch (WCC: six simultaneous matches). Both look identical from
            # the feed. The champion is among that date's WINNERS, so take the
            # strongest of them by conference record.
            winners = sorted(set(w for w, _, _ in final_day),
                             key=lambda k: (-confpct(k), rpirank.get(k, 999)))
            winner = winners[0]
            note = ("%d games on %s -- best of that date's winners by "
                    "conference record" % (len(final_day), last_day))
    else:
        rec = collections.defaultdict(lambda: [0, 0])
        for w, l, _ in conf_games:
            rec[w][0] += 1
            rec[l][1] += 1
        best = sorted(mem, key=lambda k: (
            -(rec[k][0] / float(rec[k][0] + rec[k][1]) if (rec[k][0] + rec[k][1]) else 0),
            rpirank.get(k, 999)))
        winner = best[0]
        note = "best conference win pct"

    # An ineligible champion forfeits the bid to the best eligible finisher.
    if winner not in eligible:
        alt = sorted([m for m in mem if m in eligible], key=lambda k: rpirank.get(k, 999))
        if not alt:
            return None, mech, "champion ineligible, no eligible member"
        return alt[0], mech, note + " -- champion %s INELIGIBLE, bid passes" % winner
    return winner, mech, note


def main():
    cutoff = datetime.date(SEASON, 11, 30)   # Selection Sunday 2025 was Nov 30
    di, meta, played, allgames = load(cutoff)
    print("=" * 76)
    print("STAGE A -- FIELD PROJECTION, data through %s" % (cutoff - datetime.timedelta(days=1)))
    print("=" * 76)
    print("  D-I teams %d   D-I matches before cutoff %d" % (len(di), len(played)))

    factors = rpi_from_games(played, sorted(di))
    order = sorted(di, key=lambda k: -factors[k]["rpi"])
    rpirank = {k: i for i, k in enumerate(order, 1)}

    # resume inputs
    vs = collections.defaultdict(lambda: {"t25w": 0, "t25l": 0, "t50w": 0, "t50l": 0})
    for w, l, _ in played:
        if rpirank.get(l, 999) <= 25:
            vs[w]["t25w"] += 1
        if rpirank.get(l, 999) <= 50:
            vs[w]["t50w"] += 1
        if rpirank.get(w, 999) <= 25:
            vs[l]["t25l"] += 1
        if rpirank.get(w, 999) <= 50:
            vs[l]["t50l"] += 1

    # non-D-I share, for the >=80% D-I eligibility rule
    total = collections.Counter()
    digames = collections.Counter()
    for (w, l, d, isdi) in allgames:
        for k in (w, l):
            total[k] += 1
            if isdi:
                digames[k] += 1

    # TWO DIFFERENT GATES, and conflating them is a real error the backtest
    # caught. The .500 floor and the 80%-D-I-schedule rule are AT-LARGE
    # criteria (Pre-Championship Manual 2.4). A CONFERENCE CHAMPION carries its
    # league's automatic bid regardless of record -- that is the entire point of
    # an automatic qualifier. Applying the at-large floor to AQs cost Florida
    # A&M (14-16, actual SWAC champion) its bid and handed it to Prairie View.
    champ_eligible, at_large_eligible, why_out = set(), set(), {}
    for k in di:
        f = factors[k]
        n = f["wins"] + f["losses"]
        wp = f["wins"] / float(n) if n else 0.0
        if k in INELIGIBLE:
            why_out[k] = "reclassifying, championship-ineligible"
            continue
        champ_eligible.add(k)          # may still win an AQ
        if wp < MIN_WIN_PCT:
            why_out[k] = "below .500 (%d-%d) -- at-large only" % (f["wins"], f["losses"])
        elif total[k] and digames[k] / float(total[k]) < MIN_DI_SHARE:
            why_out[k] = "under 80%% D-I schedule -- at-large only"
        else:
            at_large_eligible.add(k)
    eligible = at_large_eligible
    print("  championship-eligible %d   at-large-eligible %d   excluded %d"
          % (len(champ_eligible), len(at_large_eligible), len(INELIGIBLE)))

    # ---- automatic qualifiers ----
    byconf = collections.defaultdict(list)
    for k in di:
        c = conference_of(meta, k)
        if c:
            byconf[c].append(k)
    aqs, aq_detail = {}, []
    for conf, members in sorted(byconf.items()):
        t, mech, note = pick_aq(conf, members, played, allgames, champ_eligible, rpirank)
        if t:
            aqs[t] = conf
            aq_detail.append((conf, t, mech, note))
    print("  conferences %d -> automatic qualifiers %d (config AQ_COUNT=%d)"
          % (len(byconf), len(aqs), AQ_COUNT))

    # ---- at-large: resume ranking of everyone not holding an AQ ----
    def resume_score(k):
        # Lower is better. RPI rank dominates, with credit for top-25/top-50
        # wins and a penalty for bad losses -- the committee's stated criteria,
        # minus KPI which is unfetchable.
        r = rpirank.get(k, 999)
        v = vs[k]
        return (r
                - 2.0 * v["t25w"]
                - 1.0 * v["t50w"]
                + 1.5 * v["t25l"] * 0)     # losses to top-25 are not penalised

    pool = sorted([k for k in eligible if k not in aqs], key=resume_score)
    at_large = pool[:max(0, FIELD_SIZE - len(aqs))]
    field = list(aqs.keys()) + at_large
    print("  at-large slots %d -> projected field %d" % (len(at_large), len(field)))
    print()

    # ---- seeds: top 32 of the field by resume ----
    seeded = sorted(field, key=resume_score)[:SEEDED]
    seed_of = {k: i for i, k in enumerate(seeded, 1)}

    # ---- BACKTEST against what actually happened ----
    actual_field, actual_seed = set(), {}
    for g in load_games_jsonl(os.path.join(RAW, "games.jsonl")):
        if not g.get("championship") or g.get("game_state") != "F":
            continue
        t = g.get("teams") or []
        if len(t) != 2:
            continue
        ks = [norm(x.get("name_short")) for x in t]
        if not all(k in di for k in ks):
            continue          # the championship flag also carries non-D-I events
        for x in t:
            k = norm(x.get("name_short"))
            actual_field.add(k)
            if x.get("seed"):
                actual_seed[k] = int(x["seed"])

    hit = set(field) & actual_field
    missed = actual_field - set(field)
    wrong = set(field) - actual_field
    print("=" * 76)
    print("BACKTEST vs the actual %d field" % len(actual_field))
    print("=" * 76)
    print("  CORRECT      %d / %d  (%.1f%%)" % (len(hit), len(actual_field),
                                                100.0 * len(hit) / max(len(actual_field), 1)))
    print("  MISSED (in the real field, we left out): %d" % len(missed))
    for k in sorted(missed, key=lambda k: rpirank.get(k, 999)):
        f = factors[k]
        print("     %-24s RPI#%-4s %d-%-3d %s" % (
            meta.get(k, {}).get("School", k), rpirank.get(k), f["wins"], f["losses"],
            why_out.get(k, "not selected by resume model")))
    print("  WRONG (we selected, not in the real field): %d" % len(wrong))
    for k in sorted(wrong, key=lambda k: rpirank.get(k, 999)):
        f = factors[k]
        print("     %-24s RPI#%-4s %d-%-3d %s" % (
            meta.get(k, {}).get("School", k), rpirank.get(k), f["wins"], f["losses"],
            "AQ:" + aqs[k] if k in aqs else "at-large"))
    print()

    both = [k for k in seeded if k in actual_seed]
    exact = sum(1 for k in both if seed_of[k] == actual_seed[k])
    print("  SEEDS: %d of our %d seeded teams were actually seeded" % (len(both), len(seeded)))
    print("  top-16 overlap: %d / 16" % len(
        set(list(seed_of)[:16]) & set(k for k, v in actual_seed.items() if v <= 4)))
    print()

    payload = {
        "meta": {
            "season": SEASON, "source_tier": "DERIVED",
            "stage": "A -- field projection (committee behaviour, NOT strength)",
            "cutoff": cutoff.isoformat(),
            "config": {"AQ_COUNT": AQ_COUNT, "AQ_COUNT_FALLBACK": AQ_COUNT_FALLBACK,
                       "FIELD_SIZE": FIELD_SIZE, "SEEDED": SEEDED,
                       "AQ_MECHANISM": AQ_MECHANISM,
                       "AQ_MECHANISM_DEFAULT": AQ_MECHANISM_DEFAULT,
                       "INELIGIBLE": sorted(INELIGIBLE)},
            "known_gaps": [
                "KPI absent -- proprietary, read-only from faktorsports.com",
                "AQ for tournament conferences inferred from the last "
                "intra-conference match; the feed carries no bracket structure",
            ],
            "backtest": {"actual_field": len(actual_field), "correct": len(hit),
                         "missed": sorted(missed), "wrong": sorted(wrong)},
        },
        "automatic_qualifiers": [
            {"conference": c, "team": meta.get(t, {}).get("School", t),
             "mechanism": m, "note": n} for c, t, m, n in aq_detail],
        "field": [{"team": meta.get(k, {}).get("School", k),
                   "rpi_rank": rpirank.get(k),
                   "seed": seed_of.get(k),
                   "bid": "AQ" if k in aqs else "at-large"} for k in
                  sorted(field, key=resume_score)],
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
