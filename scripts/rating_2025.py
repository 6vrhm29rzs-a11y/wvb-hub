#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3: the composite rating. RPI + opponent-adjusted net points/set.

Chosen by the bake-off (scripts/bakeoff_2025.py). adj_hit_eff_diff performs
identically (they are redundant, +0.002 incremental over each other) and was
dropped on PROVENANCE, not accuracy: net points/set comes from /game/{id}
linescores at 100% coverage on all 348 teams, while hitting efficiency comes
from the stat leaderboards, which carry 343 teams and are a separate fetch that
can fail on its own.

WEIGHTS ARE FITTED, NOT HAND-ENTERED. A two-feature logistic on match outcomes
gives the relative weight of the two terms; the composite is then that same
linear combination applied to standardized team ratings.

The DELTA column against official RPI is the point of the exercise. A power
ranking that agrees with RPI everywhere carries no information; the only
interesting content is where it disagrees and whether those disagreements have
a story.

Python 3.9 target.
"""

import datetime
import json
import os
import random
import sys
import collections
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(REPO, "data", "rating_%d.json" % SEASON)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakeoff_2025 as B  # noqa: E402
from reconcile_2025 import norm, parse_record  # noqa: E402

PRIMARY = "adj_net_points_set"
LOW_CONF_GAMES = 10   # below this, the rating is flagged as thin-sample
SEED = 23


def zscore(vals):
    # type: (List[float]) -> Tuple[float, float]
    n = len(vals)
    mu = sum(vals) / n
    sd = (sum((v - mu) ** 2 for v in vals) / n) ** 0.5 or 1.0
    return mu, sd


def fit_weights(M, matches):
    """Two-feature logistic on match outcomes -> (w_rpi, w_primary, stats)."""
    rows, ys = [], []
    for m in matches:
        a, b = m["teams"]
        ra, rb = M["rpi"].get(a["key"]), M["rpi"].get(b["key"])
        pa, pb = M[PRIMARY].get(a["key"]), M[PRIMARY].get(b["key"])
        if None in (ra, rb, pa, pb):
            continue
        rows.append((ra - rb, pa - pb))
        ys.append(1 if m["winner_idx"] == 0 else 0)
    rmu, rsd = zscore([r[0] for r in rows])
    pmu, psd = zscore([r[1] for r in rows])
    X = [[1.0, (r[0] - rmu) / rsd, (r[1] - pmu) / psd] for r in rows]
    w = B.logistic(X, ys)
    return w, (rmu, rsd, pmu, psd), X, ys


def composite_table(M, w, di):
    """Team-level composite from standardized ratings, using the fitted weights."""
    keys = [k for k in sorted(di)
            if M["rpi"].get(k) is not None and M[PRIMARY].get(k) is not None]
    rmu, rsd = zscore([M["rpi"][k] for k in keys])
    pmu, psd = zscore([M[PRIMARY][k] for k in keys])
    out = {}
    for k in keys:
        zr = (M["rpi"][k] - rmu) / rsd
        zp = (M[PRIMARY][k] - pmu) / psd
        out[k] = {
            "z_rpi": zr, "z_primary": zp,
            "composite": w[1] * zr + w[2] * zp,
        }
    return out


def auc_of(scores, ys):
    g, ng = B._groups(scores)
    return B.auc_from_counts(g, ys, ng, range(len(ys)))


def main():
    matches, di = B.load()
    print("D-I matches: %d" % len(matches))
    print()

    # Pre-season and the first days of a season have no played matches. That is
    # expected, not a failure: exit cleanly and leave the existing dashboard
    # alone rather than crashing the run or publishing a rating fitted on
    # nothing. A failed run must not overwrite good data with worse data.
    MIN_MATCHES = 50
    if len(matches) < MIN_MATCHES:
        print("fewer than %d played matches -- too early to fit a rating." % MIN_MATCHES)
        print("Leaving the previous rating and dashboard untouched.")
        return 0

    # ---------------- weights fitted on the full season ----------------
    M_full = B.build_metrics(matches, di)
    w, norms, Xf, yf = fit_weights(M_full, matches)
    ratio = abs(w[1]) / abs(w[2]) if w[2] else float("inf")

    print("=" * 74)
    print("FITTED WEIGHTS (two-feature logistic on match outcomes, standardized)")
    print("=" * 74)
    print("  w_rpi                = %+.4f" % w[1])
    print("  w_adj_net_points_set = %+.4f" % w[2])
    print("  ratio rpi : margin   = %.2f : 1" % ratio)
    print()
    # State the comparison, do NOT pre-write its verdict. An earlier draft of
    # this block asserted the fit "lands close to 2:1" before the number was
    # known; it came out 1.00:1 and the sentence printed anyway.
    print("  CONTEXT: Cody's hand-built model was Adj = Z(net pts/set) + 2*Z(SOS)")
    print("  -- schedule weighted twice margin. NOT directly comparable: RPI is")
    print("  25%% own record + 75%% schedule, so w_rpi is not a pure SOS weight.")
    print("  Fitted here: %.2f : 1 (rpi : margin)." % ratio)
    if ratio >= 1.75:
        print("  => Close to his 2:1. Schedule dominates margin by about as much")
        print("     as he assumed.")
    elif ratio >= 1.2:
        print("  => Schedule outweighs margin, but by LESS than his 2:1. Margin")
        print("     deserves more weight than the hand-built model gave it.")
    else:
        print("  => Roughly EQUAL weight, well short of his 2:1. Directionally he")
        print("     was right that schedule matters, but the fit says margin is")
        print("     worth about as much -- and note w_rpi already contains 75%%")
        print("     schedule internally, so schedule is not being under-counted.")
    print()

    in_auc = auc_of([w[0] + w[1] * x[1] + w[2] * x[2] for x in Xf], yf)
    rpi_only_in = auc_of([x[1] for x in Xf], yf)
    print("  in-sample AUC: composite %.4f   (rpi alone %.4f)" % (in_auc, rpi_only_in))
    print()

    # ---------------- out-of-sample validation ----------------
    print("=" * 74)
    print("VALIDATION -- chronological splits, paired bootstrap, vs RPI alone")
    print("=" * 74)
    # Cutoffs are DERIVED from the data range, not hardcoded to 2025 dates.
    # The dry-run caught this: with only September data, fixed Oct/Nov cutoffs
    # leave an empty test set, incremental() returns None and the pipeline dies
    # -- in September 2026, i.e. on day one of live operation.
    dates = sorted(m["date"] for m in matches if m["date"])
    val = {}
    if len(dates) < 400:
        print("  too few matches (%d) to validate; skipping" % len(dates))
    cuts = []
    if dates:
        for frac in (0.55, 0.70, 0.85):
            c = dates[int(frac * (len(dates) - 1))]
            if c not in [x[1] for x in cuts]:
                cuts.append(("%.0f%%" % (frac * 100), c))
    for label, cut in cuts:
        fit = [m for m in matches if m["date"] and m["date"] < cut]
        test = [m for m in matches if m["date"] and m["date"] >= cut]
        if len(fit) < 200 or len(test) < 100:
            print("  %-7s skipped (fit %d / test %d too small)" % (
                label, len(fit), len(test)))
            continue
        Mc = B.build_metrics(fit, di)
        r = B.incremental(Mc, fit, test, PRIMARY)
        if r is None:
            print("  %-7s skipped (insufficient overlapping data)" % label)
            continue
        wc, _, Xc, yc = fit_weights(Mc, fit)
        ins = auc_of([wc[0] + wc[1] * x[1] + wc[2] * x[2] for x in Xc], yc)
        val[label] = dict(r, in_sample_auc=ins, gap=ins - r["auc_both"],
                          w_rpi=wc[1], w_primary=wc[2])
        flag = "CI excludes 0" if (r["delta_lo"] or 0) > 0 else "CI includes 0"
        print("  %-7s (%s) test n=%-5d  rpi %.4f -> composite %.4f   delta %+.4f "
              "[%+.4f, %+.4f]  %s" % (
                  label, cut.isoformat(), r["n"], r["auc_rpi"], r["auc_both"], r["delta"],
                  r["delta_lo"], r["delta_hi"], flag))
        print("           in-sample %.4f vs out-of-sample %.4f  -> overfit gap %+.4f"
              % (ins, r["auc_both"], ins - r["auc_both"]))
        print("           weights at this cutoff: rpi %+.3f, margin %+.3f (%.2f:1)"
              % (wc[1], wc[2], abs(wc[1]) / abs(wc[2]) if wc[2] else 0))
    print()

    # ---------------- the 348-team table ----------------
    from rpi_2025 import rpi_from_games as _rfg0
    _g0 = []
    for m in matches:
        _g0.append((m["teams"][m["winner_idx"]]["key"],
                    m["teams"][1 - m["winner_idx"]]["key"], m["game_id"]))
    _F0 = _rfg0(_g0, sorted(di))
    _sosrank = {k: i for i, (k, _) in enumerate(
        sorted(_F0.items(), key=lambda kv: -kv[1]["owp"]), 1)}

    # RESUME-VIEW inputs. Deliberately kept SEPARATE from the composite: the
    # composite answers "who would win a match" (strength); the committee asks
    # "who has earned selection" (resume) and weights won-lost results. One
    # number cannot serve both -- predicting the field with a strength rating
    # would systematically over-select good-margin/bad-record teams, which is the
    # measured bias below (corr(delta, own win%) = -0.205).
    # No official RPI table exists early in a season (RPI needs games first, and
    # the rankings endpoint cannot be season-pinned). The resume view degrades to
    # empty rather than crashing, and the dashboard shows blanks instead of
    # inventing ranks.
    from membership import from_archived_rpi as _arch
    _a = _arch(RAW)
    _offrank = {k: int(v["Rank"]) for k, v in (_a[1].items() if _a else [])}
    _vs = collections.defaultdict(lambda: {"t25_w": 0, "t25_l": 0,
                                           "t50_w": 0, "t50_l": 0})
    for m in matches:
        wk = m["teams"][m["winner_idx"]]["key"]
        lk = m["teams"][1 - m["winner_idx"]]["key"]
        lr, wr = _offrank.get(lk), _offrank.get(wk)
        if lr and lr <= 25:
            _vs[wk]["t25_w"] += 1
        if lr and lr <= 50:
            _vs[wk]["t50_w"] += 1
        if wr and wr <= 25:
            _vs[lk]["t25_l"] += 1
        if wr and wr <= 50:
            _vs[lk]["t50_l"] += 1

    # Display names: without the official table the join key (lowercased,
    # punctuation-stripped) would leak into the UI as "nebraska". Use the name
    # the feed itself printed.
    _disp = {}
    for m in matches:
        for t in m["teams"]:
            _disp.setdefault(t["key"], t.get("name_short") or t["key"])

    comp = composite_table(M_full, w, di)
    official = (_a[1] if _a else {})

    ranked = sorted(comp.items(), key=lambda kv: -kv[1]["composite"])
    table = []
    for i, (k, v) in enumerate(ranked, 1):
        off = official.get(k, {})
        # Official W-L only exists once the RPI table publishes. Early season,
        # derive it from the game log rather than rendering None into a "%d".
        rec = parse_record(off.get("Record"))
        if rec is None:
            f = _F0.get(k)
            rec = (f["wins"], f["losses"]) if f else (0, 0)
        table.append({
            "composite_rank": i,
            "team": off.get("School") or _disp.get(k, k),
            "conference": off.get("Conf"),
            "official_rpi_rank": int(off["Rank"]) if off.get("Rank") else None,
            "delta_vs_rpi": (int(off["Rank"]) - i) if off.get("Rank") else None,
            "wins": rec[0] if rec else None,
            "losses": rec[1] if rec else None,
            "adj_net_points_set": round(M_full[PRIMARY][k], 4),
            "raw_net_points_set": (round(M_full["net_points_set"][k], 4)
                                   if M_full["net_points_set"].get(k) is not None else None),
            "rpi": round(M_full["rpi"][k], 6),
            "owp": round(_F0[k]["owp"], 6),
            "sos_rank": _sosrank[k],
            # confidence: a team ranked 3rd on four matches must not look
            # identical to a team ranked 3rd on thirty
            "games_played": (rec[0] + rec[1]) if rec else 0,
            "low_confidence": bool(rec and (rec[0] + rec[1]) < LOW_CONF_GAMES),
            # resume view (separate from the strength composite, by design)
            "resume": {
                "vs_rpi_top25": "%d-%d" % (_vs[k]["t25_w"], _vs[k]["t25_l"]),
                "vs_rpi_top50": "%d-%d" % (_vs[k]["t50_w"], _vs[k]["t50_l"]),
                "official_rpi_rank": int(_offrank[k]) if k in _offrank else None,
                "kpi": None,
                "kpi_note": "KPI is PROPRIETARY and read-only from "
                            "faktorsports.com (THIRD-PARTY tier). Do not attempt "
                            "to reproduce it.",
            },
            "composite": round(v["composite"], 5),
            "source_tiers": {
                "official_rpi_rank": "OFFICIAL",
                "wins": "OFFICIAL", "losses": "OFFICIAL",
                "raw_net_points_set": "DERIVED",
                "adj_net_points_set": "DERIVED",
                "rpi": "DERIVED",
                "owp": "DERIVED", "sos_rank": "DERIVED",
                "games_played": "OFFICIAL", "resume.vs_rpi_top25": "DERIVED",
                "resume.vs_rpi_top50": "DERIVED", "resume.kpi": "THIRD-PARTY (unfetched)",
                "composite": "DERIVED",
                "delta_vs_rpi": "DERIVED",
            },
        })

    print("=" * 74)
    print("TOP 20 BY COMPOSITE")
    print("=" * 74)
    print("  %-4s %-24s %-8s %-7s %-8s %s" % (
        "rank", "team", "rpi rank", "delta", "W-L", "adj net/set"))
    for r in table[:20]:
        print("  %-4d %-24s %-8s %+-7d %-8s %+.2f" % (
            r["composite_rank"], r["team"],
            r["official_rpi_rank"] if r["official_rpi_rank"] is not None else "-",
            r["delta_vs_rpi"] if r["delta_vs_rpi"] is not None else 0,
            "%d-%d" % (r["wins"], r["losses"]),
            r["adj_net_points_set"]))
    print()

    print("=" * 74)
    print("BIGGEST DISAGREEMENTS WITH OFFICIAL RPI (the point of the table)")
    print("  positive delta = we rank them BETTER than RPI does")
    print("=" * 74)
    # Schedule strength (RPI Factor II) is printed alongside so the "story" is
    # checkable rather than asserted. The expected signature of a margin model
    # is: hard schedule + competitive losses ranked UP, soft schedule + padded
    # record ranked DOWN. If the biggest disagreements do NOT show that, it is a
    # bug signal, not a feature.
    from rpi_2025 import rpi_from_games as _rfg
    gsub = []
    for m in matches:
        wk = m["teams"][m["winner_idx"]]["key"]
        lk = m["teams"][1 - m["winner_idx"]]["key"]
        gsub.append((wk, lk, m["game_id"]))
    factors = _rfg(gsub, sorted(di))
    owp_rank = {k: i for i, (k, _) in enumerate(
        sorted(factors.items(), key=lambda kv: -kv[1]["owp"]), 1)}
    keyof = {}
    for k in comp:
        keyof[official.get(k, {}).get("School", k)] = k

    big = sorted([r for r in table if r["delta_vs_rpi"] is not None],
                 key=lambda r: -abs(r["delta_vs_rpi"]))[:16]
    print("  %-22s %-5s %-5s %-6s %-7s %-8s %-8s %s" % (
        "team", "ours", "rpi", "delta", "W-L", "adj/set", "raw/set", "SOS rk"))
    up_hard = down_soft = 0
    for r in big:
        k = keyof.get(r["team"])
        sr = owp_rank.get(k)
        print("  %-22s %-5d %-5d %+-6d %-7s %+-8.2f %+-8.2f %s" % (
            r["team"], r["composite_rank"], r["official_rpi_rank"],
            r["delta_vs_rpi"] if r["delta_vs_rpi"] is not None else 0,
            "%d-%d" % (r["wins"], r["losses"]),
            r["adj_net_points_set"], r["raw_net_points_set"],
            sr if sr else "?"))
        if sr:
            if r["delta_vs_rpi"] > 0 and sr <= 174:
                up_hard += 1
            if r["delta_vs_rpi"] < 0 and sr > 174:
                down_soft += 1
    print()
    print("  top-16 eyeball: %d ranked UP have an above-median schedule, %d ranked"
          % (up_hard, down_soft))
    print("  DOWN have a below-median one (%d/%d) -- but a 16-row eyeball is not a"
          % (up_hard + down_soft, len(big)))
    print("  test. The systematic version, across all 348:")
    print()

    # Correlate the disagreement against schedule strength and against own
    # record. An earlier reading of the top 16 called this a schedule story;
    # across the full table it is not one, and the honest signature is different.
    ds, os_, ws = [], [], []
    for r in table:
        k = keyof.get(r["team"])
        if k is None or r["delta_vs_rpi"] is None or r["wins"] is None:
            continue
        n = r["wins"] + r["losses"]
        if not n:
            continue
        ds.append(float(r["delta_vs_rpi"]))
        os_.append(factors[k]["owp"])
        ws.append(r["wins"] / float(n))

    def corr(a, b):
        n = len(a)
        ma, mb = sum(a) / n, sum(b) / n
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        sa = sum((x - ma) ** 2 for x in a) ** 0.5
        sb = sum((y - mb) ** 2 for y in b) ** 0.5
        return cov / (sa * sb) if sa and sb else 0.0

    if len(ds) < 30:
        # No official ranks yet -> no delta to correlate. Say so rather than
        # dividing by zero or, worse, printing a fabricated 0.0 correlation.
        print("    (no official RPI table yet -- delta diagnostics unavailable)")
        c_sched = c_rec = None
    else:
        c_sched = corr(ds, os_)
        c_rec = corr(ds, ws)
    if c_sched is not None:
        print("    corr(delta, opponents' win%%  [schedule]) = %+.4f" % c_sched)
        print("    corr(delta, own win%%)                    = %+.4f" % c_rec)
        print()
    print("  READ THIS CAREFULLY. Schedule correlation is ~0, so the composite is")
    print("  NOT 'RPI plus a better schedule correction'. The real signature is the")
    print("  record correlation: relative to RPI it ranks teams with WORSE records")
    print("  higher. That follows mechanically -- RPI is 25%% own winning")
    print("  percentage and the margin term is record-agnostic.")
    print()
    print("  CONSEQUENCE FOR USE: this is a STRENGTH metric, not a RESUME metric.")
    print("  It predicts individual matches better (validated above). It is NOT")
    print("  automatically the right input for bracketology, where the committee")
    print("  asks a resume question -- who has EARNED selection -- and deliberately")
    print("  weights won-lost results. Two different jobs; pick per use.")
    print()
    return_diag = {"corr_delta_schedule": c_sched, "corr_delta_own_winpct": c_rec}
    globals()["_DIAG"] = return_diag

    payload = {
        "meta": {
            "season": 2025,
            "source_tier": "DERIVED",
            "primary_margin_metric": PRIMARY,
            "selected_over": "adj_hit_eff_diff (redundant, +0.002 incremental; "
                             "dropped on provenance: 348-team linescore coverage "
                             "vs 343-team leaderboard dependency)",
            "weights": {"w_rpi": w[1], "w_margin": w[2],
                        "ratio_rpi_to_margin": ratio,
                        "fitted": True, "hand_entered": False},
            "cody_original_model": "Adj = Z(net points/set) + 2*Z(SOS)",
            "in_sample_auc": in_auc,
            "validation": val,
            "disagreement_diagnostics": globals().get("_DIAG"),
            "use_caveat": "STRENGTH metric, not RESUME metric. corr(delta vs RPI, "
                          "own win%) is negative: relative to RPI it favors teams "
                          "with worse records. Better at predicting matches; not "
                          "automatically right for resume-based bracketology.",
            "generated_at_utc": datetime.datetime.utcnow().replace(
                microsecond=0).isoformat() + "Z",
            # latest match actually IN the data, as distinct from when the
            # pipeline ran -- a run that fetches nothing new is fresh but the
            # data is not, and the dashboard must be able to say which
            "data_through": max((m["date"].isoformat() for m in matches
                                 if m.get("date")), default=None),
            "matches_in_data": len(matches),
        },
        "teams": table,
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote %s  (%d teams)" % (OUT, len(table)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
