#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RESUME: what a team has EARNED, as distinct from how good it is.

    WVB_SEASON=2025 python3 scripts/resume_2025.py   -> data/resume_2025.json

WHY THIS EXISTS. R3 has said since Phase 3 that strength is not resume, and
measured it: relative to RPI our composite favours teams with WORSE records
(corr -0.205). The site shipped only the strength side, and that is the whole
of Cody's objection -- Texas sat near the top three days after losing at home,
because a strength rating correctly says "still a very good roster" while his
eye was asking "what have they actually done?" Both questions are legitimate.
Only one of them was on the page.

THE MEASURE: WINS ABOVE BUBBLE.

    WAB(team) = its actual wins
              - the wins a BUBBLE team would be expected to take
                against that exact schedule, at those exact venues

This is the concept the NCAA itself uses in other sports, and it has the
properties a resume needs and a power rating deliberately lacks:

  * MARGIN IS IGNORED. A win is a win. Beating a team 25-12 three times and
    surviving 27-25 in the fifth are the same line on a resume, which is
    exactly the distinction that makes this a different number from POWER --
    where the margin is the whole point and capping it was measured to HURT.
  * THE SCHEDULE PAYS FOR ITSELF. Beating a team the bubble would only beat 30%
    of the time earns 0.70 wins; beating one the bubble beats 97% of the time
    earns 0.03. Nobody gets rich on a soft schedule, and nobody is punished for
    a hard one.
  * A BAD LOSS COSTS REAL POINTS, with no special-case rule. Losing where the
    bubble team would have won 95% of the time is -0.95, automatically.
  * VENUE IS PRICED. The same opponent is worth more away than at home.

⚠ IT IS SCORED AGAINST THE COMMITTEE, NOT AGAINST AUC. A resume ranking that is
tuned to predict future matches has simply become a power rating with extra
steps. The right target is what the selection committee ACTUALLY DID, and we
hold it: `actual_field_2025.json` (the real 64) and their published seeds.

⚠ AND THE OPPONENT-STRENGTH INPUT IS A PREDICTIVE RATING, DELIBERATELY. Judging
who you played needs the best available estimate of how good they are; that is
not circular, it is the same thing the committee does when it looks at an
opponent's record and rating. What makes this a RESUME is that the team's OWN
contribution is its wins and losses -- nothing about how it played.

Python 3.9 target.
"""

import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEASON = int(os.environ.get("WVB_SEASON", "2025"))
OUT = os.path.join(REPO, "data", "resume_%d.json" % SEASON)

# ⚠ A RESUME OFF ONE MATCH IS NOT A RESUME. The whole measure is "what have
# you earned against the schedule you played", and with a handful of results
# league-wide the answer is "nothing yet, and neither has anyone else". Rather
# than print a precise-looking number nobody should read, the script refuses and
# the page says when it will exist. 200 D-I matches is roughly the point at
# which most teams have played more than once.
MIN_MATCHES = 200

FIELD_SIZE = 64          # the cut line: the last team in the bracket
BUBBLE_BAND = 5          # average a few ranks around it, so one team's rating
                         # does not set the entire league's yardstick


def load(rel):
    p = os.path.join(REPO, rel)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except ValueError:
        return None


def team_strength():
    # type: () -> Tuple[Dict[str, float], str]
    """name -> strength in z units, and where it came from.

    Same precedence as the rankings board: the fitted composite when the season
    can support it, the blended projection-plus-results before that.
    """
    live = load("data/rating_%d.json" % SEASON) or {}
    rows = [r for r in (live.get("teams") or []) if r.get("composite") is not None]
    if rows:
        vals = [r["composite"] for r in rows]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        return dict((r["team"], (r["composite"] - mu) / sd) for r in rows), "live"

    blend = load("data/digby_top25_%d.json" % SEASON) or {}
    rows = [r for r in (blend.get("all") or []) if r.get("score") is not None]
    if rows:
        vals = [r["score"] for r in rows]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        return dict((r["team"], (r["score"] - mu) / sd) for r in rows), "blend"
    return {}, "none"


def matches():
    # type: () -> List[Dict]
    doc = load("data/data_%d.json" % SEASON) or {}
    id2 = dict((str(t.get("team_id")), t.get("name_short") or t.get("name_full"))
               for t in (doc.get("teams") or []))
    # ⚠ THE RESUME COUNTED 14 NON-OK MATCHES (reliability audit,
    # 2026-08-31): 2 exhibitions, 6 duplicate listings and 5 empty
    # finals -- and the empty finals, having no sets, scored as AWAY
    # wins through the sets comparison below. season_counts.classify is
    # the one counting classification; only 'ok' matches are results.
    import season_counts as _SC
    _cls = _SC.classify(doc.get("games") or [], SEASON)
    out = []
    for g in (doc.get("games") or []):
        if g.get("state") != "F":
            continue
        if _cls.get(str(g.get("game_id"))) != "ok":
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        home = next((t for t in ts if t.get("is_home")), None)
        away = next((t for t in ts if not t.get("is_home")), None)
        if not home or not away:
            continue
        if home.get("division") != 1 or away.get("division") != 1:
            continue
        hn, an = id2.get(str(home["team_id"])), id2.get(str(away["team_id"]))
        if not hn or not an:
            continue
        out.append({"home": hn, "away": an,
                    "home_win": 1 if (home.get("sets_won") or 0) >
                                     (away.get("sets_won") or 0) else 0})
    return out


def fit_prob(ms, z):
    # type: (List[Dict], Dict[str, float]) -> Tuple[float, float]
    """(beta, home) for P(home wins) = sigmoid(beta*(z_h - z_a) + home).

    Fitted on the season's own results rather than assumed, so the curve that
    prices a schedule is the curve this league actually produced.
    """
    rows = [(z[m["home"]] - z[m["away"]], m["home_win"])
            for m in ms if m["home"] in z and m["away"] in z]
    if len(rows) < 100:
        return 1.0, 0.0
    b, h = 1.0, 0.0
    for _ in range(300):
        gb = gh = 0.0
        for d, y in rows:
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, b * d + h))))
            gb += (p - y) * d
            gh += (p - y)
        b -= 0.5 * gb / len(rows)
        h -= 0.5 * gh / len(rows)
    return b, h


def main():
    z, basis = team_strength()
    if not z:
        print("no team strength available -- run rating or digby_top25 first")
        return 1
    ms = matches()
    if len(ms) < MIN_MATCHES:
        # Write the refusal down, so the page can state it rather than guess.
        json.dump({"meta": {"season": SEASON, "active": False,
                            "matches": len(ms), "min_matches": MIN_MATCHES,
                            "why": ("a resume measures what a team has earned "
                                    "against the schedule it has played; with "
                                    "%d D-I matches league-wide there is not "
                                    "enough of a season for anyone to have "
                                    "earned anything" % len(ms))},
                   "teams": []}, open(OUT, "w"), indent=1)
        print("only %d completed D-I matches (need %d) -- resume not active; "
              "wrote the refusal to %s" % (len(ms), MIN_MATCHES, OUT))
        return 0
    beta, home = fit_prob(ms, z)

    order = sorted(z.items(), key=lambda kv: -kv[1])
    lo = max(0, FIELD_SIZE - 1 - BUBBLE_BAND // 2)
    band = [v for _, v in order[lo:lo + BUBBLE_BAND]]
    bubble = sum(band) / len(band) if band else 0.0

    wins = {}
    exp = {}
    played = {}
    for m in ms:
        h, a = m["home"], m["away"]
        if h not in z or a not in z:
            continue
        for me, opp, is_home, won in ((h, a, True, m["home_win"]),
                                      (a, h, False, 1 - m["home_win"])):
            wins[me] = wins.get(me, 0) + won
            played[me] = played.get(me, 0) + 1
            # what would a BUBBLE team have done here? Same opponent, same
            # venue -- the only thing swapped out is the team itself.
            d = bubble - z[opp]
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0,
                       beta * d + (home if is_home else -home)))))
            exp[me] = exp.get(me, 0.0) + p

    # ⚠ THE RANK COMES FROM RPI, NOT FROM WAB, AND THAT IS A MEASURED RESULT
    # RATHER THAN A PREFERENCE. Scored against the only ground truth that
    # exists -- the 64 teams the committee ACTUALLY selected in 2025 -- with
    # 5-fold cross-validation so nothing is fitted and graded on the same data:
    #
    #     RPI alone          0.9215      <- best
    #     WAB alone          0.9107
    #     POWER alone        0.9071
    #     RPI + WAB          0.9152
    #     RPI + POWER        0.9156
    #     RPI + WAB + POWER  0.9136
    #
    # Every combination is WORSE than RPI by itself, and on the raw selection
    # count RPI puts 47 of the real 64 in its top 64 against WAB's 45. Building
    # a new resume metric that loses to the one already in the repository would
    # be invention for its own sake.
    #
    # ⚠ And note the honest caveat: the committee LOOKS at RPI, so predicting
    # the committee with RPI is partly circular. It is still the best answer we
    # can defend, because the committee's own choices are the only ground truth
    # for "who had earned it".
    #
    # WAB is kept and shipped because it is the READABLE form of the same
    # question -- "+19.2 wins more than a bubble team would have taken from
    # this schedule" explains a resume in a way an RPI decimal never will. It is
    # labelled as its own measure on the page, never as the ranking basis.
    rpi_doc = load("data/rpi_%d.json" % SEASON) or {}
    rpi_val = dict((r["team"], r.get("rpi")) for r in (rpi_doc.get("teams") or [])
                   if r.get("rpi") is not None)

    rows = []
    for t in sorted(z):
        if not played.get(t):
            continue
        rows.append({"team": t, "wins": wins.get(t, 0),
                     "losses": played[t] - wins.get(t, 0),
                     "matches": played[t],
                     "bubble_expected_wins": round(exp.get(t, 0.0), 3),
                     "wab": round(wins.get(t, 0) - exp.get(t, 0.0), 3),
                     "rpi": rpi_val.get(t)})
    rows.sort(key=lambda r: -r["wab"])
    for i, r in enumerate(rows, 1):
        r["wab_rank"] = i

    ranked = [r for r in rows if r.get("rpi") is not None]
    ranked.sort(key=lambda r: -r["rpi"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    # A team with no RPI keeps its WAB but gets no resume rank -- never a
    # fabricated position (R5).
    for r in rows:
        r.setdefault("rank", None)
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0))

    doc = {
        "meta": {
            "season": SEASON,
            "active": True,
            "min_matches": MIN_MATCHES,
            "source_tier": "DERIVED",
            "what_it_is": ("RESUME -- who has EARNED a bid. Ranked by RPI, "
                           "which beat every alternative against the committee's "
                           "actual 2025 selections. `wab` is the readable form: "
                           "wins above what a bubble team would take from the "
                           "same schedule at the same venues."),
            "rank_basis": "rpi",
            "validated_against": ("data/actual_field_2025.json -- the 64 teams "
                                  "the committee really selected"),
            "cv_auc_made_the_field": {"rpi": 0.9215, "wab": 0.9107,
                                      "power": 0.9071, "rpi+wab": 0.9152,
                                      "rpi+power": 0.9156,
                                      "note": ("5-fold cross-validated; every "
                                               "combination is worse than RPI "
                                               "alone, so nothing is blended")},
            "circularity_caveat": ("the committee looks at RPI, so predicting "
                                   "the committee with RPI is partly circular. "
                                   "It is still the best defensible answer: the "
                                   "committee's choices are the only ground "
                                   "truth for who had earned it."),
            "not_a_power_rating": ("POWER answers who would win tomorrow and is "
                                   "driven by margin. This answers who has "
                                   "earned a bid. R3 keeps them apart."),
            "strength_basis": basis,
            "fitted_beta": round(beta, 4),
            "fitted_home_logit": round(home, 4),
            "bubble_rank_band": [lo + 1, lo + BUBBLE_BAND],
            "bubble_strength_z": round(bubble, 4),
            "teams": len(rows),
            "matches": len(ms),
        },
        "teams": rows,
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    print("basis %s   beta %.3f   home %+.3f   bubble z %+.3f (ranks %d-%d)"
          % (basis, beta, home, bubble, lo + 1, lo + BUBBLE_BAND))
    print("\n  %-4s %-22s %-7s %8s %8s %6s"
          % ("#", "team", "record", "bubbleW", "WAB", "wabRk"))
    for r in rows[:15]:
        print("  %-4s %-22s %-7s %8.2f %+8.2f %6s"
              % (r["rank"] if r["rank"] else "-", r["team"],
                 "%d-%d" % (r["wins"], r["losses"]),
                 r["bubble_expected_wins"], r["wab"], r.get("wab_rank")))
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
