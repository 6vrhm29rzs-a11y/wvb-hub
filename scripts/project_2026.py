#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project 2026 team strength from who is actually on the 2026 roster.

Cody's spec, 2026-08-18: rank on points-per-set RETURNING weighted by the 2025
strength of the team that production came against, plus points-per-set
TRANSFERRED IN weighted by the source team's 2025 strength, plus incoming
freshmen weighted by class rank.

*** THE WEIGHTS BELOW ARE HAND-SET AND UNFITTED. ***
There is no 2026 result to fit them against, so nothing here is validated. They
are written as named constants at the top, printed on every run, and every
component is stored per team so a number can always be taken apart. Do not read
the ordering as measured. R1: this file computes values; it does not characterise
them, and no output string calls this projection good.

The way to replace the guesses with measurements is a 2024 -> 2025 backtest:
"returning production" is derivable from box scores alone (a player who appears
for the same team in both seasons returned), so 2024 player data plus 2025
outcomes is enough to FIT these weights rather than assert them. The 2024 crawl
needed for that is a separate job.

THE FRESHMAN TERM IS ZERO AND THAT IS A KNOWN BIAS, NOT AN OVERSIGHT.
We hold no recruiting-class data -- no rankings, no star ratings, no class ranks.
R5 forbids inventing a stand-in, so incoming players contribute nothing and the
count of them is reported per team instead. This systematically under-rates teams
with large or highly-rated freshman classes, and it under-rates them MORE the
better the class. Any team near a cutoff with a big incoming class is being
treated unfairly by this model, on purpose, because the alternative is a made-up
number. Supplying a published class-rank list is the sanctioned fix.

Python 3.9 target. Writes data/projection_2026.json.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm  # noqa: E402

OUT = os.path.join(REPO, "data", "projection_2026.json")

# ----------------------------------------------------------------- WEIGHTS
# All hand-set. Printed on every run so they cannot quietly become folklore.
W_RETURNING = 1.00     # weight on quality-adjusted returning points/set
W_TRANSFER = 1.00      # weight on quality-adjusted incoming-transfer points/set
W_FRESHMAN = 0.00      # no recruiting data exists; see module docstring

# THE STRENGTH CORRECTION IS NOW MEASURED, AND IT IS ADDITIVE, NOT A MULTIPLIER.
# Q_FLOOR/Q_CEIL used to scale each rate by a hand-picked 0.5x-1.5x. Two things
# were wrong with that and only measurement could show it:
#   1. The shape. A within-player fixed-effects fit over 20,997 player-matches
#      (scripts/measure_level_effect.py) says facing a team one SD stronger costs
#      a player -0.215 points/set, 95% CI [-0.231, -0.200]. That is a SHIFT, not
#      a scaling.
#   2. The size. 0.215/SD is far smaller than a 3x multiplier implies -- so
#      schedule strength was never going to explain the mid-major ordering on
#      its own, and turning the dial harder would only have hidden the problem.
# The real cause was that the projection ranked teams on RAW offence. Raw
# offence tracks a team's net strength at spearman 0.82; OPPONENT-ADJUSTED
# offence tracks it at 0.99. Normalising each player's rate to a neutral
# schedule lifts prediction of net strength from 0.749 to 0.891 across 349 teams.
# Read the adjusted rates from data/player_rates_2025.json; do not re-derive.
# THE PRIOR IS THE STRONGEST SINGLE PREDICTOR AND THE MODEL IS NOW ANCHORED ON IT.
# Measured 2024 -> 2025 across 346 teams: last season's opponent-adjusted NET
# rating predicts this season's at spearman +0.857, with offence and defence
# persisting about equally (+0.841 each). The first version of this file ignored
# that entirely and rebuilt each team from its roster alone, which is why it put
# Nebraska 41st -- it was discarding the best information available.
#
# The roster is the ADJUSTMENT, not the base. A team's schedule-adjusted top-6
# explains its own-season rating at spearman +0.887, so the change in that
# quantity between the 2025 roster and the 2026 roster is what should move a
# team off its prior:
#     projected = composite_2025 + COMPOSITE_PER_ADJ6 * (adj6_2026 - adj6_2025)
# COMPOSITE_PER_ADJ6 is the fitted slope of composite on adj6 (n=347, r=0.897).
COMPOSITE_PER_ADJ6 = 1.13122

# *** THE ROSTER TERM IS NOW FITTED, AND IT IS SMALL. ***
# The 2024 player backfill finally completed (5,186 games, 0 failures), which
# made the only honest test possible: build the same prior-plus-roster-delta
# projection for 2024 -> 2025 and score it OUT OF SAMPLE against what actually
# happened, 5-fold over 323 teams.
#
#     prior alone                rho 0.8245
#     prior + roster delta       rho 0.8317      gain +0.0072
#     fitted weights             prior 2.13 | delta 0.20
#
# So the roster carries real, independent signal -- a partial correlation of
# +0.233 with the outcome once the prior is removed from both sides -- but it is
# worth about a TENTH of the prior, not the same as it.
#
# That is why every hand-set value failed. 0.15 through 1.00 were all far too
# aggressive and each made the ordering worse; 0.0 was too conservative and threw
# away a measured effect. Neither error was visible without two seasons of player
# data, which is why this sat switched off until the backfill landed.
#
# Related and worth keeping in view: the roster aggregation NEVER beats the prior
# on its own (best fitted variant rho 0.806 against the prior's 0.827). It is a
# correction, not a foundation.
# Weights fitted JOINTLY, out of sample, 2024 -> 2025, 5-fold, n=323. Jointly
# and not one at a time, because the roster delta and churn both partly measure
# production lost -- stacking separately-fitted weights would count it twice.
#
#     prior                    rho 0.8253
#     prior + delta            rho 0.8312
#     prior + churn            rho 0.8387
#     prior + delta + churn    rho 0.8405
#
#     z-weights: prior +2.178 | delta +0.123 | churn -0.284
#
# CHURN came from Cody's observation that pollsters mark down teams with heavy
# turnover. Testing it turned up something better than the hypothesis: churn does
# predict underperformance, but the effect GROWS through the season rather than
# fading (high-churn quartile residual win%: -0.019 early, -0.060 late). So it is
# not a temporary "haven't meshed yet" cost -- it is durable talent loss, and the
# pollsters' instinct is right for the wrong reason.
#
# The feature is PROSPECTIVE: share of last season's production that did not
# return, knowable the day rosters are published.
ROSTER_DELTA_WEIGHT = float(os.environ.get("WVB_ROSTER_WEIGHT", "0.0565"))
CHURN_WEIGHT = float(os.environ.get("WVB_CHURN_WEIGHT", "-0.1304"))

MIN_SETS = 20          # a rate below this many sets is noise, not a rate

# ROTATION SIZE -- MEASURED, not assumed. Summing the top-N players' own
# points-per-set and comparing to their team's ACTUAL points-per-set across all
# 343 teams with 2025 stats:
#     top-5  median error -2.12   top-6  -0.46   top-7  +1.00   top-8  +2.03
# Six is both the closest fit and the number of players on the court. This is
# what stops the model from crediting a team for production it cannot deploy:
# Florida returns 12 players and adds 7 transfers, and summing all 19 careers
# implied roughly double a team's worth of scoring. Reproduce with
# scripts/test_projection.py.
ROTATION = 6

# STACKING RETURNS LESS THAN IT COSTS -- also measured, on the same 343 teams.
# Regressing a team's ACTUAL points/set on the sum of its top six players' rates:
#     actual = 0.7965 * sum(top6) + 3.534      residual sd 0.68
# The slope is 0.80, not 1.0: every extra point of rate you stack onto a roster
# returns about four fifths of itself, because six players share a fixed number
# of swings and cannot all be on the court taking them. Summing raw rates
# therefore over-credits exactly the rosters that hoard talent, and the error
# grows with the sum (spearman(residual, sum) = +0.38).
#
# This is a MONOTONE transform, so it does not reorder anything -- it exists so
# the displayed points/set is a physical quantity rather than an index, and so a
# projection that lands outside anything 343 real teams achieved gets flagged
# instead of printed with a straight face.
CAL_SLOPE = 0.7965
CAL_INTERCEPT = 3.534
OBSERVED_MAX_PPS = 19.00   # highest team points/set in 2025
OBSERVED_MIN_PPS = 10.70


def load(p, default=None):
    path = os.path.join(REPO, p)
    if not os.path.exists(path):
        return default
    return json.load(open(path))


def player_points(p: Dict) -> float:
    """kills + aces + solo blocks + half of block assists, from RAW COUNTS.

    The same formula join_players.production() uses. NEVER the feed's own
    `points` column, which is measured to be missing for some games and
    undercounts by a different amount per player.
    """
    return ((p.get("kills") or 0) + (p.get("aces") or 0)
            + (p.get("block_solos") or 0) + 0.5 * (p.get("block_assists") or 0))


def build():
    rating = load("data/rating_2025.json")
    returning = (load("data/returning_2026.json") or {}).get("teams", {})
    players25 = (load("data/raw/2025/players_2025.json") or {}).get("players", [])
    if not rating or not returning:
        print("need data/rating_2025.json and data/returning_2026.json")
        raise SystemExit(1)

    # A team's 2025 percentile, kept only as a REPORTED column so a row can be
    # read in context. It no longer scales anything -- the schedule correction
    # now lives inside each player's adjusted rate, where it was measured.
    ranked = [t for t in rating["teams"] if t.get("composite") is not None]
    ranked.sort(key=lambda t: -t["composite"])
    n = float(len(ranked))
    q_by_name, comp_by_name = {}, {}
    for i, t in enumerate(ranked):
        q_by_name[t["team"]] = round(1.0 - (i / max(n - 1.0, 1.0)), 4)
        comp_by_name[t["team"]] = t["composite"]

    # team_id -> team name, so a transfer's SOURCE team can be scored
    id_to_name, team_sets = {}, {}
    ds = load("data/data_2025.json") or {}
    for t in ds.get("teams", []):
        if t.get("team_id"):
            id_to_name[str(t["team_id"])] = t["name_short"]
        st = t.get("season_totals") or {}
        if st.get("sets"):
            team_sets[t["name_short"]] = st["sets"]

    # --- 2025 per-player lines by team_id, for transfer rate lookup ---------
    by_team_player = {}
    for p in players25:
        tid = str(p.get("team_id") or "")
        nm = re.sub(r"[^a-z]", "", ("%s %s" % (p.get("first") or "",
                                               p.get("last") or "")).lower())
        if tid and nm:
            by_team_player[(tid, nm)] = p

    # ---- schedule-adjusted rates, keyed by (team_id, squashed name) --------
    rates_raw = load("data/player_rates_2025.json") or {"players": []}
    _adj = {}
    for pr in rates_raw["players"]:
        _adj[(str(pr["team_id"]), re.sub(r"[^a-z]", "", pr["name"].lower()))] = pr["adj_rate"]
    name_to_id = {v: k for k, v in id_to_name.items()}

    def adj_rate(team_id, player_name, raw):
        """The player's rate normalised to a neutral schedule.

        Falls back to the RAW rate when we cannot find her -- an unadjusted rate
        is a worse estimate but an honest one, and it is the same quantity in
        the same units. Silently substituting a league average here would be
        inventing a measurement.
        """
        if not team_id or not player_name:
            return raw
        k = (str(team_id), re.sub(r"[^a-z]", "", player_name.lower()))
        v = _adj.get(k)
        return v if v is not None else raw

    baseline = (load("data/adj6_baseline_2025.json") or {}).get("teams", {})
    # every 2025 player rate per team, so the baseline can be taken at the same
    # depth as the 2026 roster we actually know
    baseline_pool = {}
    for pr in rates_raw["players"]:
        if (pr.get("sets") or 0) >= MIN_SETS:
            nm = id_to_name.get(str(pr["team_id"]))
            if nm:
                baseline_pool.setdefault(nm, []).append(pr["adj_rate"])

    rows = []
    tin_unresolved = 0
    for t in rating["teams"]:
        name = t["team"]
        rec = returning.get(name) or {}
        has_roster = bool(rec.get("returning") is not None)

        # ---- returning points per set -------------------------------------
        ret_pts = sum((p.get("pts") or 0) for p in rec.get("returning") or [])
        ret_sets = sum((p.get("sets") or 0) for p in rec.get("returning") or [])
        ret_pps = (ret_pts / float(ret_sets)) if ret_sets >= MIN_SETS else None

        dep_pts = sum((p.get("pts") or 0) for p in rec.get("departed") or [])
        dep_sets = sum((p.get("sets") or 0) for p in rec.get("departed") or [])

        qT = q_by_name.get(name, 1.0)
        tsets = team_sets.get(name)

        # ---- build the candidate pool: who can actually score in 2026 ------
        # Each candidate carries the RATE they produced at and the QUALITY of
        # the level they produced it against. Returning players earned theirs
        # here; transfers earned theirs at their old school.
        pool = []
        for pl in rec.get("returning") or []:
            if (pl.get("sets") or 0) >= MIN_SETS and pl.get("pts") is not None:
                raw = pl["pts"] / float(pl["sets"])
                pool.append({"name": pl.get("name"), "src": name, "q": qT,
                             "rate": adj_rate(name_to_id.get(name), pl.get("name"), raw),
                             "raw_rate": raw, "kind": "returning"})

        tin_detail = []
        for x in rec.get("transfer_in_official") or []:
            src_name = id_to_name.get(str(x.get("from_team_id") or ""))
            qS = q_by_name.get(src_name, 1.0) if src_name else 1.0
            nm = re.sub(r"[^a-z]", "", (x.get("name") or "").lower())
            row = by_team_player.get((str(x.get("from_team_id") or ""), nm))
            if not (row and (row.get("sets") or 0) >= MIN_SETS):
                # No 2025 line we can stand behind -- counted and reported,
                # never approximated from a season total, because sets played
                # is exactly what a total cannot tell you.
                tin_unresolved += 1
                continue
            raw = player_points(row) / float(row["sets"])
            rate = adj_rate(str(x.get("from_team_id") or ""), x.get("name"), raw)
            pool.append({"name": x.get("name"), "src": src_name, "q": qS,
                         "rate": rate, "raw_rate": raw, "kind": "transfer"})
            tin_detail.append({"name": x.get("name"), "from": src_name,
                               "rate": round(rate, 3), "q_src": round(qS, 3)})

        # ---- top ROTATION, on schedule-adjusted rates ---------------------
        # No multiplier: the rate is ALREADY schedule-adjusted.
        pool.sort(key=lambda c: -c["rate"])
        six = pool[:ROTATION]
        adj6_2026 = round(sum(c["rate"] for c in six), 4) if six else None
        raw_pps = sum(c.get("raw_rate", c["rate"]) for c in six) if six else None
        proj_pps = (round(CAL_SLOPE * raw_pps + CAL_INTERCEPT, 3)
                    if raw_pps is not None else None)

        # ANCHOR ON THE PRIOR, MOVE BY THE ROSTER CHANGE.
        # COMPARE LIKE WITH LIKE. adj6_2026 can only count players who have a
        # 2025 D-I record; a true freshman contributes nothing, so a team with
        # two unknown starters has its top-6 built from four real players and
        # two weak ones. Differencing that against a 2025 top-6 drawn from a
        # FULL roster charges the team for our ignorance.
        #
        # Measured: median projected adj6 is 12.54 against 15.90 across real
        # 2025 rosters -- a 3.4 point systematic gap that has nothing to do with
        # how good anyone is. So difference the top-K where K is how many
        # players we actually know, on both sides.
        base_pool = baseline_pool.get(name) or []
        k = len(six)
        base_k = (round(sum(sorted(base_pool, reverse=True)[:k]), 4)
                  if len(base_pool) >= k and k else None)
        comp25 = comp_by_name.get(name)
        base26 = baseline.get(name)
        talent = None
        roster_delta = None
        if adj6_2026 is not None and base_k is not None and comp25 is not None:
            # in compressed units: stacking returns ~80% of itself (CAL_SLOPE)
            roster_delta = round(CAL_SLOPE * (adj6_2026 - base_k), 4)
            talent = round(comp25 + ROSTER_DELTA_WEIGHT
                           * COMPOSITE_PER_ADJ6 * roster_delta, 4)
        elif comp25 is not None:
            # No usable roster read. The prior alone is still the best estimate
            # we have, so the team is ranked on it rather than dropped.
            talent = round(comp25, 4)

        over = (proj_pps is not None and proj_pps > OBSERVED_MAX_PPS)
        thin = len(six) < ROTATION
        under = (proj_pps is not None and proj_pps < OBSERVED_MIN_PPS and not thin)
        ret_term = round(sum(c["rate"] for c in six if c["kind"] == "returning"), 3)
        tin_term_pps = round(sum(c["rate"] for c in six if c["kind"] == "transfer"), 3)
        n_tin_in_six = sum(1 for c in six if c["kind"] == "transfer")

        # ---- freshmen: structurally zero ----------------------------------
        n_incoming = len(rec.get("new_or_unplayed") or [])
        fr_term = 0.0

        rows.append({
            "team": name,
            "conference": t.get("conference"),
            "composite_2025": t.get("composite"),
            "rank_2025": t.get("composite_rank"),
            "rpi_2025": t.get("official_rpi_rank"),
            "has_roster": has_roster,
            "q_2025": round(qT, 3),
            "returning_pps": round(ret_pps, 3) if ret_pps is not None else None,
            "returning_pts": round(ret_pts, 1),
            "returning_sets": ret_sets,
            "departed_pts": round(dep_pts, 1),
            "departed_sets": dep_sets,
            "returning_share": (round(ret_pts / (ret_pts + dep_pts), 3)
                                if (ret_pts + dep_pts) else None),
            "transfer_in_pps_weighted": tin_term_pps,
            "team_sets_2025": tsets,
            "proj_points_per_set": proj_pps,
            "adj6_2026": adj6_2026,
            "adj6_2025_baseline": base26,
            "baseline_at_same_depth": base_k,
            "roster_delta": roster_delta,
            "raw_top6_sum": round(raw_pps, 3) if raw_pps is not None else None,
            "over_observed_max": over,
            "under_observed_min": under,
            "thin_roster": thin,
            "rotation_known": len(six),
            "pool_size": len(pool),
            "transfers_in_rotation": n_tin_in_six,
            "transfers_counted": len(tin_detail),
            "transfers_in": tin_detail,
            # The six the score is actually made of, so any ranking can be
            # taken apart without re-running anything.
            "rotation": [{"name": c["name"], "kind": c["kind"], "from": c["src"],
                          "rate": round(c.get("raw_rate", c["rate"]), 3),
                          "adj": round(c["rate"], 3)} for c in six],
            "incoming_unplayed": n_incoming,
            "talent": talent,
        })

    # ---- churn: production that did not come back ------------------------
    # Applied here rather than in the loop because it is z-scored across the
    # field, which needs every team's share first. A team we cannot compute a
    # returning share for gets NO churn adjustment rather than the mean -- an
    # absent measurement is not a zero.
    shares = [r["returning_share"] for r in rows if r["returning_share"] is not None]
    if shares and CHURN_WEIGHT:
        mu_s = sum(shares) / len(shares)
        sd_s = (sum((v - mu_s) ** 2 for v in shares) / len(shares)) ** 0.5 or 1.0
        comps = [r["composite_2025"] for r in rows if r["composite_2025"] is not None]
        sd_c = ((sum((v - sum(comps) / len(comps)) ** 2 for v in comps)
                 / len(comps)) ** 0.5) or 1.0
        for r in rows:
            if r["talent"] is None or r["returning_share"] is None:
                r["churn"] = None
                continue
            lost = 1.0 - r["returning_share"]
            z_lost = ((lost - (1.0 - mu_s)) / sd_s)
            adj = CHURN_WEIGHT * z_lost * sd_c
            r["churn"] = round(lost, 4)
            r["churn_adj"] = round(adj, 4)
            r["talent"] = round(r["talent"] + adj, 4)

    # `talent` is already anchored on last season's composite, so a separate
    # "blend with the prior" view would be blending the prior with itself. The
    # z-score is kept only so the spread is readable.
    vals = [r["talent"] for r in rows if r["talent"] is not None]
    if vals:
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        for r in rows:
            r["z_talent"] = (round((r["talent"] - mu) / sd, 4)
                             if r["talent"] is not None else None)
            r["blend"] = r["talent"]

    # ranks: teams without a roster are NOT ranked, they are listed as unranked
    for field, key in (("talent_rank", "talent"), ("blend_rank", "blend")):
        ok = [r for r in rows if r.get(key) is not None]
        ok.sort(key=lambda r: -r[key])
        for i, r in enumerate(ok, 1):
            r[field] = i
        for r in rows:
            r.setdefault(field, None)

    meta = {
        "source_tier": "DERIVED",
        "validated": False,
        "note": ("2026 projection from 2026 rosters x 2025 per-player production, "
                 "each rate normalised to a neutral schedule using a MEASURED "
                 "within-player level effect (-0.215 pts/set per SD, 95% CI "
                 "[-0.231,-0.200], 20,997 player-matches), summed over a MEASURED "
                 "6-player rotation and compressed by a MEASURED stacking slope "
                 "(0.796). No 2026 result exists to validate the whole against, "
                 "but each component is fitted to 2025 outcomes rather than "
                 "guessed. The freshman term remains structurally zero because no "
                 "recruiting data is held; teams with large incoming classes are "
                 "under-rated as a result."),
        "weights": {
            "W_RETURNING": W_RETURNING, "W_TRANSFER": W_TRANSFER,
            "W_FRESHMAN": W_FRESHMAN, "COMPOSITE_PER_ADJ6": COMPOSITE_PER_ADJ6,
            "ROSTER_DELTA_WEIGHT": ROSTER_DELTA_WEIGHT,
            "CHURN_WEIGHT": CHURN_WEIGHT,
            "MIN_SETS": MIN_SETS,
            "ROTATION": ROTATION,
            "level_slope_pts_per_sd": (load("data/level_effect.json") or {})
                .get("recommended_slope"),
            "stacking_slope": CAL_SLOPE,
        },
        "coverage": {
            "teams": len(rows),
            "ranked": sum(1 for r in rows if r["talent"] is not None),
            "no_roster": sum(1 for r in rows if not r["has_roster"]),
            "transfers_counted": sum(r["transfers_counted"] for r in rows),
            "transfers_without_a_usable_2025_rate": tin_unresolved,
        },
    }
    return {"meta": meta, "teams": rows}


if __name__ == "__main__":
    out = build()
    json.dump(out, open(OUT, "w"), indent=1)
    m = out["meta"]
    print("wrote %s" % OUT)
    # The label has to keep up with the constants. Most of these are now
    # measured, and calling them "hand-set, unfitted" is the R4 failure in
    # miniature: right numbers, wrong heading.
    print("WEIGHTS -- fitted: ROTATION (best of 5-9 on 2025), "
          "level_slope (within-player, 20,997 obs), stacking_slope (n=343), "
          "COMPOSITE_PER_ADJ6 (n=347), ROSTER_DELTA_WEIGHT (out-of-sample "
          "2024->2025, n=323)")
    print("        -- still hand-set: W_RETURNING, W_TRANSFER, and W_FRESHMAN "
          "(zero, because no recruiting data is held)")
    print("  %s" % json.dumps(m["weights"]))
    print("coverage: %s" % json.dumps(m["coverage"]))
    print()
    print("TOP 25 by talent (quality-weighted returning + transfer points/set)")
    print("%-4s %-22s %-12s %7s %7s %7s %6s %4s" %
          ("#", "team", "conf", "ret/set", "q", "tin", "ret%", "in"))
    for r in sorted([x for x in out["teams"] if x["talent"] is not None],
                    key=lambda x: x["talent_rank"])[:25]:
        print("%-4d %-22s %-12s %7s %7s %7s %6s %4d" % (
            r["talent_rank"], r["team"][:22], (r["conference"] or "")[:12],
            r["returning_pps"], r["q_2025"], r["transfer_in_pps_weighted"],
            ("%.0f%%" % (100 * r["returning_share"])) if r["returning_share"] is not None else "-",
            r["incoming_unplayed"]))
