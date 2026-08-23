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


def per_match_margins(doc):
    # type: (Dict) -> Dict[str, List[float]]
    """team_id -> [net points per set, one per completed D-I match]."""
    out = collections.defaultdict(list)
    for g in (doc or {}).get("games") or []:
        if g.get("state") != "F":
            continue
        ts = g.get("teams") or []
        ls = [l for l in (g.get("linescores") or []) if l.get("home") is not None]
        if len(ts) != 2 or not ls:
            continue
        home = [t for t in ts if t.get("is_home")]
        away = [t for t in ts if not t.get("is_home")]
        if not home or not away:
            continue
        home, away = home[0], away[0]
        if home.get("division") != 1 or away.get("division") != 1:
            continue
        hp = sum(l["home"] for l in ls)
        ap = sum(l["visit"] for l in ls)
        n = float(len(ls))
        out[str(home["team_id"])].append((hp - ap) / n)
        out[str(away["team_id"])].append((ap - hp) / n)
    return out


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
    zobs = dict((nm, v / tau) for nm, v in obs.items())

    # W-L from the live dataset, so the poll can show a record beside the rank.
    wl = collections.defaultdict(lambda: [0, 0])
    for g in (live.get("games") or []):
        if g.get("state") != "F":
            continue
        for t in (g.get("teams") or []):
            nm = id2name.get(str(t.get("team_id")))
            if not nm:
                continue
            wl[nm][0 if t.get("is_winner") else 1] += 1

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
            "k_note": ("matches at which this season and the preseason weigh "
                       "equally; k = per-match variance / the PROJECTION'S OWN "
                       "error variance, not the between-team variance -- the "
                       "projection is far better than an average team and is "
                       "weighted accordingly"),
            "prior_rho_out_of_sample": round(rho, 4),
            "prior_error_variance": round(prior_err, 3),
            "per_match_variance": round(sigma2, 3),
            "between_team_variance": round(tau2, 3),
            "caveat_schedule": ("early in the season the opponent is barely "
                                "adjusted for -- there is no schedule graph yet, "
                                "so beating nobody looks like beating somebody"),
            "teams_with_a_result": len(nmatch),
            "matches_counted": sum(nmatch.values()) // 2,
            "shown": SHOWN,
            "also_receiving": ALSO,
        },
        "top": rows[:SHOWN],
        "also_receiving": rows[SHOWN:SHOWN + ALSO],
    }
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
