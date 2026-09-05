#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Digby's Top 25 -- a ranking that moves with every result, from day one.

    python3 scripts/digby_top25.py        # -> data/digby_top25_2026.json

WHY THIS EXISTS. The Rankings tab is a preseason projection that CANNOT move: it
reads 2026 rosters against 2025 production and no result at all. It is honest
about what it is, but a page called "rankings" in a live season should respond
when somebody wins. `rating_2025.py` does respond -- and refuses to fit under 50
played matches, which in August means late September.

So this blends the two, and the blend weight is MEASURED rather than chosen.

    weight on this season = n / (n + k)

k is the number of matches at which results and preseason weigh equally, and it
falls out of two variances measured on the completed 2025 season:

    per-match noise   sigma^2 = 23.93   (sd 4.89 net pts/set)
    between-team      tau^2   =  5.94   (sd 2.44), de-noised
    k = sigma^2 / tau^2       =  4.03 matches

That is the standard shrinkage weight, not a knob. One match moves a team 20% of
the way off its preseason number; four matches gets it halfway; twenty gets it
83% of the way. Both variances are recomputed here from the data rather than
pasted in, so the number tracks reality if the sport changes.

⚠ THIS IS A STRENGTH RANKING, NOT A RESUME (R3). It answers "who would win a
match", which is what a poll is mostly read as. It is NOT what the selection
committee does -- that weighs won-lost results and is what `project_field.py`
predicts. Keeping them apart is the whole of R3.

⚠ EARLY ON, THE OPPONENT IS BARELY ADJUSTED FOR. With three matches played there
is no schedule graph worth speaking of, so a team that beat nobody looks the
same as a team that beat somebody. The page says so, and the adjustment arrives
on its own as the graph fills in.

Python 3.9 target.
"""

import collections
import datetime
import json
import os
import statistics as st
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "digby_top25_%d.json" % SEASON)

SHOWN = 25          # the poll itself
ALSO = 10           # "also receiving votes" -- the next ten, as the AVCA does
MIN_MATCHES = 8     # for measuring the variances, not for ranking anyone


def load(rel):
    p = os.path.join(REPO, rel)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except ValueError:
        return None


def _eligible(doc):
    """The finals a rating may see -- season_counts.countable, exactly.

    ⚠ ADDED 2026-08-30: both loops below skipped duplicates and hand-rolled
    the D-I/line checks -- and never learned about the EXHIBITIONS ledger,
    so the two 21-point-set Spikes matches were feeding margins into the
    live blend: the exact per-set deflation the ledger exists to prevent,
    invisible because the count merely read two high. One counting set,
    from the contract, for every consumer."""
    import season_counts as _SC
    # ⚠ THE TRUST CUTOFF (2026-09-04, superseding the pure as-of-previous-
    # day rule of 2026-09-01 -- Cody: "I like looking at it through the
    # day and see why teams move"): a final enters the blend when it is
    # school-VERIFIED, or once it predates the midnight-PT boundary. The
    # delay was standing in for trust; verification carries the trust
    # directly, so verified results move the ranking intraday and an
    # unverified feed claim never does.
    _cutoff = _SC.rating_cutoff_epoch()
    _verified = _SC.verified_result_gids()
    for g in _SC.countable((doc or {}).get("games") or [], SEASON,
                           need_line=True, d1_only=True):
        if not _SC.rating_input_ok(g, _cutoff, _verified):
            continue
        ts = g.get("teams") or []
        ls = [l for l in (g.get("linescores") or [])
              if l.get("home") is not None]
        home = [t for t in ts if t.get("is_home")]
        away = [t for t in ts if not t.get("is_home")]
        if not home or not away:
            continue
        yield g, home[0], away[0], ls


def per_match_margins(doc):
    # type: (Dict) -> Dict[str, List[float]]
    """team_id -> [net points per set, one per completed D-I match]."""
    out = collections.defaultdict(list)
    for g, home, away, ls in _eligible(doc):
        hp = sum(l["home"] for l in ls)
        ap = sum(l["visit"] for l in ls)
        n = float(len(ls))
        out[str(home["team_id"])].append((hp - ap) / n)
        out[str(away["team_id"])].append((ap - hp) / n)
    return out


def per_match_detail(doc):
    # type: (Dict) -> Dict[str, List[Dict]]
    """team_id -> one record per completed D-I match, with WHO it was against.

    per_match_margins() throws the opponent away, which is what forced the
    season term to be scored as if every match were against an average team.
    """
    out = collections.defaultdict(list)
    for g, home, away, ls in _eligible(doc):
        hp = sum(l["home"] for l in ls)
        ap = sum(l["visit"] for l in ls)
        n = float(len(ls))
        out[str(home["team_id"])].append(
            {"margin": (hp - ap) / n, "opp": str(away["team_id"]), "is_home": True})
        out[str(away["team_id"])].append(
            {"margin": (ap - hp) / n, "opp": str(home["team_id"]), "is_home": False})
    return out


def home_advantage(doc):
    # type: (Dict) -> float
    """Mean per-set margin from the home side, measured on a full season.

    Measured on 2025 rather than on the handful of 2026 matches played so far:
    with seven results the estimate would be noise, and a home-court term that
    swings week to week would move teams for reasons that are not about them.
    """
    vals = []
    for tid, recs in per_match_detail(doc).items():
        for r in recs:
            if r["is_home"]:
                vals.append(r["margin"])
    return st.mean(vals) if vals else 0.0


def variance_components(margins):
    # type: (Dict[str, List[float]]) -> Tuple[float, float]
    """(sigma^2 per match, tau^2 between teams). Measured, not chosen.

    tau^2 is DE-NOISED: the spread of season means already contains sampling
    noise, so subtracting sigma^2/n_avg is what separates "teams really differ"
    from "short seasons wobble". Skipping it inflates tau^2 and would let one
    match count for far more than it earns.
    """
    usable = dict((t, v) for t, v in margins.items() if len(v) >= MIN_MATCHES)
    if len(usable) < 30:
        return 23.93, 5.94                             # 2025's measured values
    means = [st.mean(v) for v in usable.values()]
    sigma2 = st.mean([st.pvariance(v) for v in usable.values() if len(v) > 1])
    n_avg = st.mean([len(v) for v in usable.values()])
    tau2 = max(st.pvariance(means) - sigma2 / n_avg, 0.01)
    return sigma2, tau2


def shrinkage_k(sigma2, tau2, rho):
    # type: (float, float, float) -> Tuple[float, float]
    """(k, prior error variance).

    ⚠ THE SUBTLE ONE, AND THE FIRST VERSION GOT IT WRONG. Shrinkage weights a
    prior by ITS OWN error variance, not by the spread of the population. Using
    tau^2 -- the between-team variance -- treats the preseason projection as if
    it carried no information beyond "an average D-I team", which is exactly
    what it is not. That handed one match 20% of a team's rating.

    The projection correlates with the following season at rho = %.2f out of
    sample (measured, `churn_fit.json`), so the variance it leaves unexplained
    is tau^2 * (1 - rho^2). That is what a match has to compete with:

        k = sigma^2 / (tau^2 * (1 - rho^2))

    The effect is large and in the direction of humility: k goes from ~4 matches
    to ~14, so one result moves a team a few per cent rather than a fifth of the
    way. Which is right -- a projection that predicts next season at 0.84 is not
    overturned by one Friday night.
    """
    prior_err = max(tau2 * (1.0 - rho * rho), 1e-6)
    return sigma2 / prior_err, prior_err


def zscores(values):
    # type: (Dict[str, float]) -> Dict[str, float]
    if not values:
        return {}
    vals = list(values.values())
    mu = st.mean(vals)
    sd = st.pstdev(vals) or 1.0
    return dict((k, (v - mu) / sd) for k, v in values.items())


def main():
    prior_doc = load("data/projection_2026.json") or {}
    prior_rows = prior_doc.get("teams") or []
    if not prior_rows:
        print("no preseason projection -- run scripts/project_2026.py first")
        return 1

    # k from the completed 2025 season: a full season is the only place the two
    # variances can both be seen.
    hist = load("data/data_2025.json") or {}
    sigma2, tau2 = variance_components(per_match_margins(hist))
    # How good the preseason projection actually is, measured out of sample on
    # 2024 -> 2025 rather than assumed. If that file is missing we fall back to
    # the value recorded in CLAUDE.md rather than to an optimistic guess.
    rho = ((load("data/churn_fit.json") or {}).get("meta") or {}).get("with_churn_rho")
    rho = float(rho) if rho else 0.8379
    k, prior_err = shrinkage_k(sigma2, tau2, rho)

    live = load("data/data_%d.json" % SEASON) or {}
    id2name = dict((str(t.get("team_id")), t.get("name_short") or t.get("name_full"))
                   for t in (live.get("teams") or []))
    played = per_match_margins(live)
    detail = per_match_detail(live)
    home_adv = home_advantage(hist)

    prior = {}
    record = {}
    conf = {}
    for r in prior_rows:
        name = r.get("team")
        # `blend` is the projector's own final preseason number -- the one
        # `blend_rank` is built from, so the Top 25 starts from exactly the
        # order the Rankings tab already shows rather than a second opinion.
        val = r.get("blend")
        if val is None:
            val = r.get("talent")
        if name is not None and val is not None:
            prior[name] = float(val)
        conf[name] = r.get("conference") or r.get("conf")
    zprior = zscores(prior)

    # This season's margin, per team, in the same z units as the prior.
    obs = {}
    nmatch = {}
    for tid, vals in played.items():
        nm = id2name.get(tid)
        if not nm:
            continue
        obs[nm] = st.mean(vals)
        nmatch[nm] = len(vals)
    # STANDARDISE AGAINST THE LEAGUE, NOT AGAINST WHOEVER HAS PLAYED.
    # z-scoring the handful of teams with a result is wrong in a way that is
    # invisible once the season fills in: in week one only six teams have
    # played, so the best of those six scores +1.5 SD purely for being the best
    # of six, and lands next to a preseason z computed across all 348. The
    # league mean net margin is 0 by construction (every point is somebody's
    # loss), and tau is the between-team SD measured above -- so margin/tau is
    # already "how many team-strength SDs above average", on exactly the scale
    # the prior uses, whether two teams have played or three hundred.
    tau = tau2 ** 0.5

    # ⚠ OPPONENT-ADJUSTED. The raw margin over tau scores a result as if it had
    # come against an average Division-I team, and it is the single largest
    # error the early-season ranking was making: Texas losing 4.25 points a set
    # to the SEVENTH-BEST TEAM IN THE COUNTRY was recorded as -1.74 z, the same
    # as losing it to anybody. The page used to admit this ("the schedule is
    # barely adjusted for early") rather than fix it.
    #
    # What a result actually implies about a team is:
    #
    #     implied strength = opponent's strength + how far you beat them
    #                        (in the same units, home advantage removed)
    #
    # which is precisely what the ridge computes once a schedule graph exists.
    # Before then the preseason projection stands in for the opponent. That is
    # a real assumption and it is the best available one -- the projection
    # predicts the following season at rho 0.84 out of sample.
    #
    # MEASURED, not argued: scripts/measure_blend_k.py walks 2025, blends prior
    # with results at a checkpoint and scores every match AFTER it. The
    # adjustment helps at EVERY reaction speed tested, with the CI clear of zero
    # at all of them -- +0.021 AUC at the shipped k (0.7998 -> 0.8205), and
    # +0.086 at k=0.5 where results dominate. It is four times larger than any
    # other change measured this session.
    zobs = {}
    for tid, recs in detail.items():
        nm = id2name.get(tid)
        if not nm:
            continue
        vals = []
        for r in recs:
            opp_nm = id2name.get(r["opp"])
            zopp = zprior.get(opp_nm) if opp_nm else None
            if zopp is None:
                continue
            vals.append(zopp + (r["margin"] - home_adv * (1.0 if r["is_home"] else -1.0)) / tau)
        if vals:
            zobs[nm] = st.mean(vals)
    # A team whose opponents we cannot place falls back to the raw margin --
    # worse, but better than dropping the result entirely.
    for nm, v in obs.items():
        if nm not in zobs:
            zobs[nm] = v / tau

    # W-L from the live dataset, so the poll can show a record beside the
    # rank. ⚠ THIS LOOP DIVERGED FROM ITS OWN _eligible() (reliability
    # audit, 2026-08-31): finals+duplicate only, so the two exhibitions
    # inflated records (Nebraska 3-0, SMU 4-0 measured) and an empty
    # final -- is_winner None on both sides -- scored BOTH teams a loss.
    # One counting classification (season_counts), same as everything
    # that counts.
    import season_counts as _SCW
    _wl_cls = _SCW.classify(live.get("games") or [], SEASON)
    wl = collections.defaultdict(lambda: [0, 0])
    for g in (live.get("games") or []):
        if _wl_cls.get(str(g.get("game_id"))) != "ok":
            continue
        _wi = _SCW.winner_index(g)   # never the raw flag: a final can
        if _wi is None:              # carry is_winner False on BOTH sides
            continue                 # (6628428) -- sets decide, or nothing
        for _ti, t in enumerate(g.get("teams") or []):
            nm = id2name.get(str(t.get("team_id")))
            if not nm:
                continue
            wl[nm][0 if _ti == _wi else 1] += 1

    rows = []
    for name, zp in zprior.items():
        n = nmatch.get(name, 0)
        w = (n / float(n + k)) if n else 0.0
        zo = zobs.get(name)
        if zo is None:
            w, zo = 0.0, 0.0                            # nothing played: prior alone
        score = (1.0 - w) * zp + w * zo
        won, lost = wl.get(name, [0, 0])
        rows.append({
            "team": name,
            "score": round(score, 4),
            "preseason_z": round(zp, 3),
            "season_z": (round(zo, 3) if n else None),
            "matches": n,
            "weight_on_season": round(w, 3),
            "record": "%d-%d" % (won, lost),
            "net_pts_per_set": (round(obs[name], 2) if name in obs else None),
            "conf": conf.get(name),
        })
    # The spread of the blended score across ALL 348 teams, so a consumer can
    # put it on a stated scale. Only the top 35 rows are stored, so the mean and
    # SD have to be recorded here or they are gone -- and a power score computed
    # from the 25 rows that survive would be measuring "spread among the best",
    # which is the same error as z-scoring season margin against whoever had
    # played (fixed in this file's own history).
    _sv = [r["score"] for r in rows]
    _smu = st.mean(_sv) if _sv else 0.0
    _ssd = (st.pstdev(_sv) or 1.0) if _sv else 1.0

    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    doc = {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "what_it_is": ("A STRENGTH ranking -- who would win a match -- that "
                           "moves with every result. Not a resume ranking and "
                           "not what the committee does (R3)."),
            "blend": "score = (1-w)*preseason_z + w*season_z,  w = n/(n+k)",
            "season_z_scale": ("observed net pts/set divided by the between-team "
                               "SD (%.2f), NOT z-scored against whoever happens "
                               "to have played -- that would score the best of "
                               "six teams as if it were the best of 348"
                               % (tau2 ** 0.5)),
            "k_matches": round(k, 2),
            "opponent_adjusted": True,
            "home_advantage_pts_per_set": None,   # filled below
            # ⚠ STEP 3 OF THE AUDIT: RE-FIT k, OR STATE WHY NOT. Stating why
            # not. With the opponent adjustment in place the measured optimum
            # moves from 25 to 10 (measure_blend_k.py, 2025, seven checkpoints)
            # -- but k=10 against the derived 13.52 is +0.00071 AUC with a CI of
            # [-0.00064, +0.00206], which includes zero. Seven of seven
            # checkpoints prefer something below 13.5, which is suggestive, and
            # the checkpoints share data so that is not seven independent votes.
            #
            # A derived constant that updates itself from the season's own
            # variances is worth more than a hand-pasted 10 that happened to win
            # a comparison it could not win significantly. This project has been
            # explicit about that since the roster term (0.15/0.30/0.50/1.00 all
            # hand-set, all worse; fitted value 0.09). So k stays derived, and
            # the measurement is recorded here so the decision is re-checkable
            # rather than remembered.
            "k_measured_optimum_2025": 10,
            "k_measured_vs_derived": {
                "auc_delta": 0.00071,
                "ci95": [-0.00064, 0.00206],
                "clear_of_zero": False,
                "checkpoints_preferring_faster": [7, 7],
                "decision": ("keep the derived value -- the difference is not "
                             "distinguishable from zero, and the derivation "
                             "tracks the data while a pasted constant does not"),
            },
            "k_note": ("matches at which this season and the preseason weigh "
                       "equally; k = per-match variance / the PROJECTION'S OWN "
                       "error variance, not the between-team variance -- the "
                       "projection is far better than an average team and is "
                       "weighted accordingly"),
            "prior_rho_out_of_sample": round(rho, 4),
            "prior_error_variance": round(prior_err, 3),
            "per_match_variance": round(sigma2, 3),
            "between_team_variance": round(tau2, 3),
            "caveat_schedule": ("the opponent IS adjusted for from match one: "
                                "a result is scored as the strength it implies "
                                "(opponent's rating + margin, home court "
                                "removed). What is still thin early is the "
                                "opponent's own rating, which is the preseason "
                                "projection until a schedule graph exists"),
            "teams_with_a_result": len(nmatch),
            "matches_counted": sum(nmatch.values()) // 2,
            "corpus_fingerprint": __import__("season_counts")
            .corpus_fingerprint(SEASON),
            "certifies": {
                "blend_weight_derived_not_chosen": {
                    "value": True,
                    "policy": __import__("properties")
                    .POLICY["BLEND_WEIGHT"],
                    "measurement": {"k_matches": round(k, 2),
                                    "per_match_variance": round(sigma2, 3),
                                    "prior_error_variance":
                                        round(prior_err, 3)}},
            },
            "score_mean": round(_smu, 5),
            "score_sd": round(_ssd, 5),
            "score_scale_note": ("mean and SD across ALL %d teams, not just the "
                                 "ones shown -- a scale computed from the top 25 "
                                 "would measure the spread among the best"
                                 % len(rows)),
            "shown": SHOWN,
            "also_receiving": ALSO,
        },
        "top": rows[:SHOWN],
        "also_receiving": rows[SHOWN:SHOWN + ALSO],
        # ⚠ ALL 348, NOT JUST THE 25 SHOWN. The Rankings tab needs the same
        # blend for every team, and the alternative -- recomputing it there --
        # would be a second definition of the ranking that could drift from
        # this one (R4). Kept compact: the Top 25 rows above carry the detail.
        "all": [{"team": r["team"], "rank": r["rank"], "score": r["score"],
                 "matches": r["matches"],
                 "weight_on_season": r["weight_on_season"]} for r in rows],
    }
    doc["meta"]["home_advantage_pts_per_set"] = round(home_adv, 4)
    # When was this ranking computed, and through what? Two different facts:
    # the run stamp moves every time the script runs, while data_through moves
    # only when a new final is actually in the dataset. Cody asked for exactly
    # this pair -- "when was it last updated?" is unanswerable from a page
    # build time, because a page rebuild without a recompute keeps old ranks.
    # Same field names as rating_2025.py meta, so consumers read one shape.
    doc["meta"]["generated_at_utc"] = datetime.datetime.utcnow().replace(
        microsecond=0).isoformat() + "Z"
    # ⚠ THROUGH WHAT THE RATING COUNTS, not through what the dataset holds
    # (Cody, 2026-09-04: "recomputed 5:38 PM today" beside the as-of-
    # yesterday cutoff read as if today's finals were in). The max epoch
    # over ALL finals stamped data-through at 4 PM while _eligible() cut
    # at midnight -- two rulers in one stamp. data_through is the latest
    # COUNTED final; the cutoff rides beside it so the page can say both.
    import season_counts as _SCm
    _cut = _SCm.rating_cutoff_epoch()
    _ver = _SCm.verified_result_gids()
    _fin, _n_intraday = [], 0
    for g in (live.get("games") or []):
        if g.get("state") != "F" or not g.get("start_time_epoch"):
            continue
        if g.get("start_time_epoch") < _cut:
            _fin.append(g.get("start_time_epoch"))
        elif str(g.get("game_id")) in _ver:
            _fin.append(g.get("start_time_epoch"))
            _n_intraday += 1
    doc["meta"]["data_through_epoch"] = max(_fin) if _fin else None
    doc["meta"]["rating_cutoff_epoch"] = _cut
    # today's school-verified finals already counted (the trust cutoff)
    doc["meta"]["verified_intraday_counted"] = _n_intraday
    json.dump(doc, open(OUT, "w"), indent=1, sort_keys=False)
    m = doc["meta"]
    print("k = %.2f matches  (sigma^2 %.2f / tau^2 %.2f)"
          % (m["k_matches"], m["per_match_variance"], m["between_team_variance"]))
    print("%d teams have played; %d D-I matches counted"
          % (m["teams_with_a_result"], m["matches_counted"]))
    print()
    for r in doc["top"][:10]:
        moved = ("%+d%% season" % round(100 * r["weight_on_season"])) if r["matches"] else "preseason only"
        print("  %2d  %-22s %-6s  %s" % (r["rank"], r["team"], r["record"], moved))
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
