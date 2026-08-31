#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Position-relative player ratings: POWER and RESUME.

TWO RATINGS, TWO JOBS, NEVER MERGED -- R3 applied to players.
  POWER  = how good is she right now. Prior season blended with season-to-date.
  RESUME = what has she produced THIS season. Current results only.

WITHIN POSITION ONLY. Nothing in a box score licenses "this libero is better
than that middle": the positions do not share a job and do not share a stat
line. There is deliberately no cross-position board.

--------------------------------------------------------------------------
THE WEIGHTS ARE FITTED, NOT CHOSEN, AND THE CRITERION IS EXTERNAL.
Fitted to predict AVCA All-America selection -- a published judgement made by
people who watched the season, which is evidence from OUTSIDE the box scores it
adjudicates. Logistic, 2024 and 2025 pooled, surname-anchored join (R8) that
recovered 92 and 94 of 99 selections.

⚠ AND THE FIRST HONEST FIT WAS THE WRONG ONE. Fitted naively, the model scored
0.98 AUC and looked superb -- but TEAM STRENGTH ALONE already scores 0.976 for
middles and 0.956 for liberos. At those positions All-America is substantially
a team-quality award, so a rating fitted to it would encode "plays for a good
team" while appearing to measure the player. The shipped weights are therefore
fitted with team strength IN the model and scored with that term REMOVED, and
validated among players on comparable teams (top third by strength), which
takes the team edge out of the test as well as the fit:

    OH  0.972 / 0.985    MB  0.933 / 0.984    S  0.919 / 0.961
    OPP 0.969 / 0.956    LDS 0.954 / 0.936      (both directions, p=0.0005)

The fitted vectors independently reproduce the sport: middles are rewarded for
blocks and PENALISED for digs, setters load on assists, liberos load on digs
with attacking negative. Nobody told the model what a position does.

⚠ ATTACK ERRORS/SET WAS DROPPED, AND MEASURED BEFORE DROPPING. It carried a
POSITIVE weight -- collinear with attempts, since hitting % already contains
errors -- which would have shipped a rating that visibly rewards errors.
Removing it cost at most 0.007 AUC and averaged zero across ten fits.

--------------------------------------------------------------------------
WHAT THIS CANNOT SEE, STATED BECAUSE IT IS LOAD-BEARING.
Serve-receive is not in the box score at all. Passing is a libero's and an
outside's primary job, so their ratings rest on digs and serving alone. That is
why L/DS is the weakest-supported board and it says so on the page. A middle's
efficiency inflates on low volume. A setter's assists depend on the offence her
team runs, not on how well she sets.

Python 3.9 target. Run: python3 scripts/player_rating.py
"""

import collections
import io
import json
import os
import re
import unicodedata
import sys
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = 2026
PRIOR = 2025

# ---- fitted on 2024+2025 pooled, team strength held constant ---------------
WEIGHTS = {
    "OH":  {"kps": 2.5006, "hit": 1.6390, "dps": 0.8203, "bps": -0.1844,
            "sps": 0.2820, "asps": -0.5405, "aps": 0.3504},
    "MB":  {"kps": 2.0546, "hit": 0.9342, "dps": -0.5867, "bps": 1.0929,
            "sps": 0.2723, "asps": 0.2140, "aps": 0.0149},
    "S":   {"kps": 0.5291, "hit": 1.2778, "dps": -0.0158, "bps": 0.3356,
            "sps": 0.0987, "asps": 1.3849, "aps": 0.1646},
    "OPP": {"kps": 1.5362, "hit": 1.4177, "dps": 0.5799, "bps": 0.0708,
            "sps": 0.0624, "asps": -0.0636, "aps": 0.1555},
    "LDS": {"kps": -0.3353, "hit": -0.0419, "dps": 1.9572, "bps": -0.1190,
            "sps": 0.4644, "asps": 0.1168, "aps": -0.2772},
}
FEATS = ["kps", "hit", "dps", "bps", "sps", "asps", "aps"]

# How much of the rating this season's matches carry, by matches played.
# ⚠ MEASURED, AND THE OBVIOUS FUNCTIONAL FORM WAS REJECTED BY THE MEASUREMENT.
# For each n, a rating built from a player's first n matches of 2025 was blended
# with her 2024 rating and scored against the rating from her REMAINING matches;
# the weight below is the one that minimised error, over 2,509-3,096 player
# pairs per point. Fitting w = n/(n+k) to these gives k = 1.25, but that curve
# under-weights at n=1 (0.444 vs 0.536) and over-weights at n=12 (0.906 vs
# 0.870), so the measured points are used directly rather than a form the data
# rejects.
# ⚠ It is FAST -- one match is already 54%, against 7% for a team ranking. That
# is not an error: a player's prior year carries a different role and sometimes
# a different school, while her current matches share this season's role.
# ⚠ CAVEAT, because it inflates the weight: the first n matches and the rest of
# the season share team, role and schedule, which the prior does not.
BLEND = [(1, 0.536), (2, 0.626), (3, 0.690), (4, 0.742), (6, 0.786),
         (8, 0.820), (10, 0.854), (12, 0.870)]
BLEND_CEIL = 0.92          # never let one season fully erase the prior
MIN_ATTS_HIT = 20          # hitting % below this is missing, never a guess

# Positions. ⚠ `O` IS NEVER MAPPED: of 41 box-score `O` players who also carry a
# school-site position, 27 are OPP, 8 OH, 5 S, 1 RS. A third wrong is not a
# position. `N` and blank are likewise unresolved.
POSMAP = {"OH": "OH", "MB": "MB", "MH": "MB", "S": "S", "OPP": "OPP",
          "RS": "OPP", "L": "LDS", "DS": "LDS", "L/DS": "LDS"}
POS_ORDER = ["OH", "OPP", "MB", "S", "LDS"]
POS_LABEL = {"OH": "Outside hitter", "OPP": "Opposite", "MB": "Middle blocker",
             "S": "Setter", "LDS": "Libero / DS"}

# What the box score actually supports, per position. These are not vibes: the
# support level is the measured out-of-sample AUC among comparable teams, and
# the caveat names the specific thing the data cannot see.
SUPPORT = {
    "OH":  ("good", 0.972, "Scoring and efficiency are measured directly. "
                           "Serve-receive is not in the box score, and passing "
                           "is half an outside's job."),
    "OPP": ("good", 0.956, "The opposite's job is scoring, which the box score "
                           "sees well. Smallest sample of the five positions."),
    "MB":  ("fair", 0.933, "Blocks and efficiency are measured, but a middle "
                           "swings less often, so efficiency moves on low "
                           "volume. Block assists are shared credit."),
    "S":   ("fair", 0.919, "Assists count the offence her team runs, not how "
                           "well she sets. A 6-2 splits them between two "
                           "setters, which understates both."),
    "LDS": ("weak", 0.936, "Digs and serving only. Serve-receive -- the "
                           "libero's primary job -- is absent from the feed "
                           "entirely, so this board is the least supported."),
}


# Per-component effect of opponent strength, MEASURED WITHIN PLAYER: each
# player's match compared only against her own other matches, so the slope
# cannot be contaminated by "good players face good teams", which is what a
# between-player regression would actually measure. Pooled over players with at
# least 8 matches, 5,543 player-seasons, non-D-I opponents excluded.
#
# ⚠ WITHOUT THIS THE BOARDS RANKED THE WRONG PEOPLE AND LOOKED FINE DOING IT.
# Un-adjusted, the top middle in the country came out of the Ivy League and the
# top libero out of the CAA -- rates built against weaker schedules, presented
# as national leaders.
#
# Every slope is negative for production (a harder opponent suppresses it) and
# they reproduce the sport unprompted: a setter's assists fall hardest of all
# (-0.50), because assists depend on her hitters converting; and ATTEMPTS RISE
# for outsides and opposites against better teams (+0.07, +0.05), which is what
# "give it to your best hitter when it is tight" looks like in a box score.
OPP_SLOPE = {
    "OH":  {"kps": -0.1849, "hit": -0.0522, "dps": -0.0905, "bps": -0.0227,
            "sps": -0.0435, "asps": -0.0144, "aps": 0.0686},
    "OPP": {"kps": -0.1585, "hit": -0.0518, "dps": -0.0592, "bps": -0.0308,
            "sps": -0.0103, "asps": -0.0219, "aps": 0.0522},
    "MB":  {"kps": -0.1934, "hit": -0.0591, "dps": -0.0381, "bps": -0.0489,
            "sps": -0.0234, "asps": -0.0109, "aps": -0.0988},
    "S":   {"kps": -0.0415, "hit": -0.0418, "dps": -0.0668, "bps": -0.0086,
            "sps": -0.0604, "asps": -0.5023, "aps": -0.0521},
    "LDS": {"kps": -0.0020, "hit": -0.0752, "dps": -0.1508, "bps": -0.0002,
            "sps": -0.0517, "asps": -0.0536, "aps": -0.0031},
}


def L(path):
    p = os.path.join(REPO, path)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding="utf-8"))


def nkey(s):
    """Join key: lowercase letters only, after nameclean.repair -- the ONE
    shared repair for feed-corrupted names (mojibake round-trip, C1-debris
    pairs, zero-width characters) -- then an NFKD accent fold. Pure-ASCII
    keys are byte-for-byte unchanged, so no existing join moves; only
    joins that previously FAILED can now succeed."""
    import nameclean as _nc
    s = _nc.repair(s or "")
    if any(ord(c) > 0x7F for c in s):
        s = unicodedata.normalize("NFKD", s)
        s = s.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", s.lower())


def bucket(p):
    return POSMAP.get((p or "").strip().upper())


def blend_w(n):
    # type: (int) -> float
    """Share of the rating carried by this season, at n matches played."""
    if n <= 0:
        return 0.0
    if n <= BLEND[0][0]:
        return BLEND[0][1]
    for i in range(1, len(BLEND)):
        a, wa = BLEND[i - 1]
        b, wb = BLEND[i]
        if n <= b:
            return wa + (wb - wa) * (float(n - a) / (b - a))
    last_n, last_w = BLEND[-1]
    # beyond the measured range, approach the ceiling slowly rather than
    # extrapolating a straight line off the end of the evidence
    return min(BLEND_CEIL, last_w + (BLEND_CEIL - last_w) *
               (1.0 - 1.0 / (1.0 + (n - last_n) / 12.0)))


def rates(agg):
    # type: (Dict) -> Optional[Dict]
    """Per-set rates from RAW COUNTS.

    ⚠ NEVER the box score's own `points` column -- measured unusable as a
    season total (below kills+aces+blocks for 3,270 of 4,601 players, median
    ratio 0.61), because the feed carries it for only some games.
    """
    s = float(agg.get("sets") or 0)
    if s <= 0:
        return None
    k = float(agg.get("kills") or 0)
    e = float(agg.get("errors") or 0)
    at = float(agg.get("atts") or 0)
    return {
        "sets": s,
        "kps": k / s,
        "hit": ((k - e) / at) if at >= MIN_ATTS_HIT else None,
        "dps": float(agg.get("digs") or 0) / s,
        "bps": (float(agg.get("block_solos") or 0)
                + 0.5 * float(agg.get("block_assists") or 0)) / s,
        "sps": float(agg.get("aces") or 0) / s,
        "asps": float(agg.get("assists") or 0) / s,
        "aps": at / s,
        "kills": k, "errors": e, "atts": at,
        "digs": float(agg.get("digs") or 0),
        "aces": float(agg.get("aces") or 0),
        "assists": float(agg.get("assists") or 0),
        "blocks": (float(agg.get("block_solos") or 0)
                   + 0.5 * float(agg.get("block_assists") or 0)),
        "matches": int(agg.get("matches") or 0),
    }


def scale_from(rows_by_pos):
    # type: (Dict[str, List[Dict]]) -> Dict
    """Mean and SD per position, from the COMPLETED prior season.

    ⚠ THIS IS THE FIX THE TOP 25 ALREADY PAID FOR, APPLIED TO PLAYERS. Scoring
    this season's rates against whoever happens to have played scores the best
    of a few dozen as though it were the best of six thousand. The reference
    distribution is a finished season and does not move as August fills in.
    """
    out = {}
    for pos, rows in rows_by_pos.items():
        out[pos] = {}
        for f in FEATS:
            v = [r[f] for r in rows if r.get(f) is not None]
            if len(v) < 20:
                out[pos][f] = [0.0, 1.0]
                continue
            mu = sum(v) / len(v)
            var = sum((x - mu) ** 2 for x in v) / len(v)
            out[pos][f] = [mu, (var ** 0.5) or 1.0]
    return out


def composite(r, pos, scale):
    # type: (Dict, str, Dict) -> Dict
    """Weighted sum of z-scored components, plus the components themselves.

    A missing component contributes ZERO -- the position's own mean -- and is
    reported as missing so it never silently reads as average ability (R5).
    """
    total = 0.0
    comp = {}
    missing = []
    for f in FEATS:
        mu, sd = scale[pos][f]
        if r.get(f) is None:
            missing.append(f)
            z = 0.0
        else:
            z = (r[f] - mu) / sd
        w = WEIGHTS[pos][f]
        comp[f] = {"z": round(z, 4), "w": w, "contrib": round(z * w, 4),
                   "value": (None if r.get(f) is None else round(r[f], 4))}
        total += z * w
    return {"score": total, "components": comp, "missing": missing}


_COUNTED_PB_CACHE = {}


def _counted_playerbox(year):
    # type: (int) -> list
    """(gid, rows) for COUNTED matches only, box-team swaps applied.

    ⚠ AUDIT D7 (2026-08-31): the three playerbox loops below each read
    the raw file with no duplicate/exhibition/review eligibility and no
    box_team_swap -- so the SMU-UC Davis swap entered opponent-defence,
    faced-defence and schedule strength attributed to the wrong team,
    and the two exhibitions' 21-point sets deflated defence rates. One
    reader, the same chain as every counting consumer. Cached per year:
    three loops, one classification."""
    if year in _COUNTED_PB_CACHE:
        return _COUNTED_PB_CACHE[year]
    import gamelog
    import season_counts as _SC
    gpath = os.path.join(REPO, "data/raw/%d/games.jsonl" % year)
    ok = set(str(g.get("game_id")) for g in _SC.countable(
        gamelog.load_games_jsonl(gpath), year))
    swaps = _SC.box_team_swaps(year)
    out = []
    pb = os.path.join(REPO, "data/raw/%d/playerbox.jsonl" % year)
    if os.path.exists(pb):
        for ln in io.open(pb, encoding="utf-8"):
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            gid = str(rec.get("game_id"))
            if gid not in ok:
                continue
            sw = swaps.get(gid) or {}
            rows = rec.get("rows") or []
            if sw:
                rows = [dict(r, team_id=sw.get(str(r.get("team_id")),
                                               r.get("team_id")))
                        for r in rows]
            out.append((gid, rows))
    _COUNTED_PB_CACHE[year] = out
    return out


def team_def_profile(year):
    # type: (int) -> Dict
    """team_id -> what this defence ALLOWS, from per-match box lines.

    ⚠ TEAM STRENGTH IS NOT THE SAME AS THE DEFENCE A HITTER FACED. A team can be
    strong overall and a poor blocking side, and a hitter deserves no credit for
    that. Defences vary far more than the single strength number suggests:
    hitting % allowed runs .179 to .248 across D-I (p10-p90, a 33% spread) and
    block rate varies by 46%.
    """
    agg = collections.defaultdict(lambda: collections.Counter())
    for gid, rows in _counted_playerbox(year):
        by = collections.defaultdict(list)
        for r in rows:
            by[str(r.get("team_id"))].append(r)
        if len(by) != 2:
            continue
        ids = list(by)
        for tid in ids:
            o = [x for x in ids if x != tid][0]
            a = agg[tid]
            for k, col in (("oa", "atts"), ("ok", "kills"), ("oe", "errors")):
                a[k] += sum(float(r.get(col) or 0) for r in by[o])
    out = {}
    for tid, a in agg.items():
        if a["oa"] >= 200:
            out[tid] = (a["ok"] - a["oe"]) / a["oa"]
    lg = (sum(out.values()) / len(out)) if out else 0.0
    return out, lg


def faced_defence(year, defmap):
    # type: (int, Dict) -> Dict
    """(team_id, nkey) -> mean hitting % those defences allow, weighted by the
    sets she was actually on court for."""
    acc = collections.defaultdict(lambda: [0.0, 0.0])
    for gid, rows in _counted_playerbox(year):
        by = collections.defaultdict(list)
        for r in rows:
            by[str(r.get("team_id"))].append(r)
        if len(by) != 2:
            continue
        ids = list(by)
        for tid in ids:
            o = [x for x in ids if x != tid][0]
            if o not in defmap:
                continue          # unrated defence contributes nothing
            for r in by[tid]:
                try:
                    gp = float(r.get("gp") or 0)
                except Exception:
                    gp = 0.0
                if gp <= 0:
                    continue
                k = (tid, nkey((r.get("first") or "") + (r.get("last") or "")))
                acc[k][0] += defmap[o] * gp
                acc[k][1] += gp
    return dict((k, v[0] / v[1]) for k, v in acc.items() if v[1] > 0)


def load_pbp(year):
    # type: (int) -> Dict
    """(normalised team, nkey) -> passing, role and touch metrics.

    ⚠ THIS IS THE FIX FOR A CLAIM THIS PROJECT HAD WRITTEN DOWN AS SETTLED.
    "Serve-receive is absent from the feed" is true of the ncaa.com box score
    and false of the play-by-play mirror, where Reception is a named event. A
    libero's main job is measurable.
    There is no 0-3 pass grade in this data, so passing is measured by OUTCOME:
    when she passed, did her team side out, and did it kill the first ball --
    both expressed RELATIVE TO HER OWN TEAM, which controls for how good her
    hitters are. A great passer on a poor attacking team would otherwise grade
    out badly for someone else's failing.
    """
    doc = L("data/pbp_player_%d.json" % year)
    if not doc:
        return {}
    try:
        from reconcile_2025 import norm as _tn
    except Exception:
        _tn = lambda x: (x or "").lower()
    out = {}
    for r in (doc.get("players") or []):
        out[(_tn(r.get("team")), r.get("nkey"))] = r
    return out


def strength_z(year, i2n):
    # type: (int, Dict) -> Dict[str, float]
    """team_id -> strength in SDs, using that season's own best estimate.

    A completed season has a measured rating; a live one has only a projection.
    Using each season's best available estimate is correct, not inconsistent --
    and which one was used is recorded in the output rather than left implicit.
    """
    vals = {}
    if year == PRIOR:
        for t in ((L("data/rating_%d.json" % PRIOR) or {}).get("teams") or []):
            vals[t["team"]] = float(t.get("adj_net_points_set") or 0.0)
        src = "rating_%d adj_net_points_set" % PRIOR
    else:
        for t in ((L("data/projection_%d.json" % SEASON) or {}).get("teams") or []):
            v = t.get("blend")
            if v is None:
                v = t.get("adj6_2026")
            if v is not None:
                vals[t["team"]] = float(v)
        src = "projection_%d blend" % SEASON
    if not vals:
        return {}, src
    mu = sum(vals.values()) / len(vals)
    var = sum((v - mu) ** 2 for v in vals.values()) / len(vals)
    sd = (var ** 0.5) or 1.0
    n2i = {}
    for tid, nm in i2n.items():
        n2i[nm] = tid
    out = {}
    for nm, v in vals.items():
        if nm in n2i:
            out[n2i[nm]] = (v - mu) / sd
    return out, src


def mean_opp_z(year, i2n, zmap):
    # type: (int, Dict, Dict) -> Dict
    """(team_id, first, last, pos) -> set-weighted mean opponent strength.

    Built from the per-match box scores, so it is the schedule she ACTUALLY
    played, not her team's overall schedule -- a player who missed the three
    hardest matches did not face them.
    ⚠ A non-D-I opponent contributes nothing rather than a zero: it is not an
    average opponent, it is an unrated one.
    """
    gp_of = {}
    f = os.path.join(REPO, "data/raw/%d/games.jsonl" % year)
    if os.path.exists(f):
        for ln in io.open(f, encoding="utf-8"):
            try:
                g = json.loads(ln)
            except Exception:
                continue
            ids = [str(t.get("team_id")) for t in (g.get("teams") or [])
                   if t.get("team_id")]
            if len(ids) == 2:
                gp_of[str(g.get("game_id"))] = ids
    acc = collections.defaultdict(lambda: [0.0, 0.0])
    for _gid, _rows in _counted_playerbox(year):
        rec = {"game_id": _gid, "rows": _rows}
        ids = gp_of.get(str(rec.get("game_id")))
        if not ids:
            continue
        for r in (rec.get("rows") or []):
            tid = str(r.get("team_id"))
            if tid not in i2n:
                continue
            other = [x for x in ids if x != tid]
            if not other or other[0] not in zmap:
                continue
            # ⚠ DO NOT KEY THIS ON POSITION. The position printed on a box
            # line varies match to match for the same player, so keying on it
            # silently failed to match most players and the schedule adjustment
            # reached only a minority -- Andi Jackson among the misses. A name
            # within a team identifies her; the position does not.
            try:
                gp = float(r.get("gp") or 0)
            except Exception:
                gp = 0.0
            if gp <= 0:
                continue
            k = (tid, nkey(r.get("first")), nkey(r.get("last")))
            a = acc[k]
            a[0] += gp * zmap[other[0]]
            a[1] += gp
    return dict((k, v[0] / v[1]) for k, v in acc.items() if v[1] > 0)


def adjust(r, pos, oz, faced_hit=None, league_hit=None):
    # type: (Dict, str, Optional[float], Optional[float], Optional[float]) -> Dict
    """Normalise every component to a neutral schedule.

    rate_neutral = rate_observed - slope * mean_opponent_z. A player whose
    opponents are unknown is returned UNCHANGED and flagged, never adjusted
    toward an assumed average.
    """
    if oz is None:
        return dict(r, opp_z=None, opp_adjusted=False)
    out = dict(r, opp_z=round(oz, 4), opp_adjusted=True)
    for f in FEATS:
        if out.get(f) is not None:
            out[f] = out[f] - OPP_SLOPE[pos][f] * oz
    # ⚠ AND THEN THE MATCHUP, WHICH IS A DIFFERENT QUESTION FROM TEAM STRENGTH.
    # Hitting efficiency is normalised to a league-average defence by the exact
    # transform that was validated: hit_neutral = hit - (what the defences she
    # faced allow - the league mean). Validated on PREDICTION, not on
    # All-America -- it improves how well her first half predicts her second at
    # every position (OH +.0109 n=1416, OPP +.0206 n=158, MB +.0091 n=911,
    # S +.0063 n=347). Consistent in sign across all four is the signature of a
    # real correction; a spurious one helps some and hurts others.
    if (faced_hit is not None and league_hit is not None
            and out.get("hit") is not None):
        out["hit"] = out["hit"] - (faced_hit - league_hit)
        out["faced_hit_allowed"] = round(faced_hit, 5)
    return out


def id2name():
    """team_id -> name, DIVISION I ONLY.

    ⚠ THE UNFILTERED MAP SHIPPED NONSENSE AND IT LOOKED LIKE A RATING BUG.
    data_2025.json carries 384 teams: the 348 D-I sides plus 36 non-D-I
    opponents they happened to play. Left in, the top middle in the country came
    out as a Palm Beach Atlantic player and the top libero as one from Christian
    Brothers -- both Division II, both with rates built against weaker
    opposition, and both contaminating the per-position reference distribution
    everyone else is scored against.
    D-I membership comes from the 2025 official RPI table, which is the only
    self-consistent flag this project has (the feed's own `division` field is
    unreliable retroactively).
    """
    di = set()
    for t in ((L("data/rating_%d.json" % PRIOR) or {}).get("teams") or []):
        if t.get("team"):
            di.add(t["team"])
    m = {}
    for t in ((L("data/data_%d.json" % PRIOR) or {}).get("teams") or []):
        nm = t.get("name_short") or t.get("name_full")
        if nm in di:
            m[str(t.get("team_id"))] = nm
    return m


def load_season(year):
    # type: (int) -> List[Dict]
    d = L("data/raw/%d/players_%d.json" % (year, year)) or {}
    return d.get("players") or []


def _roster_field(field):
    # type: (str) -> Dict
    """(team_id, normalised name) -> one raw roster field.

    ⚠ ONE READER FOR THE ROSTER FILE, BECAUSE TWO GUESSED WRONG IN THE SAME
    WAY. Both callers reached for `name`/`class`/`pos`; the file actually
    carries `name_raw`, `class_raw` and `pos_raw`, keyed by team NAME with the
    id inside the record. Both silently returned an EMPTY dict -- so positions
    quietly fell back to the box score and every played player's class year
    rendered as a dash, with nothing anywhere saying a lookup had failed.
    A dict that comes back empty is indistinguishable from a player who has no
    class listed, which is why this is one function with one shape now.
    """
    out = {}
    doc = L("data/raw/%d/rosters_%d.json" % (SEASON, SEASON)) or {}
    for _team, rec in (doc.get("teams") or {}).items():
        if not isinstance(rec, dict):
            continue
        tid = str(rec.get("team_id") or "")
        if not tid:
            continue
        for pl in (rec.get("players") or []):
            v = pl.get(field)
            if not v:
                continue
            nm = pl.get("name_raw") or (
                (pl.get("first") or "") + " " + (pl.get("last") or ""))
            k = nkey(nm)
            if k:
                out[(tid, k)] = v
    return out


def roster_class():
    # type: () -> Dict
    """(team_id, name) -> class year, from the school's own roster.

    ⚠ THE CLASS COLUMN READ "-" FOR EVERY PLAYER WHO HAD ACTUALLY PLAYED. It
    was attached only on the prior-season seeding path, so appearing in a 2026
    box score -- the thing that makes a player CURRENT -- was what removed her
    class year. Exactly backwards.
    """
    return _roster_field("class_raw")


def roster_positions():
    # type: () -> Dict
    """Position from the school's own roster, keyed (team_id, name).

    Used only to RESOLVE a player the box score left blank -- never to override
    a stated one, and never to turn an `O` into a guess.
    """
    out = {}
    for k, v in _roster_field("pos_raw").items():
        b = bucket(v)
        if b:
            out[k] = b
    return out


def percentile(sorted_scores, v):
    lo, hi = 0, len(sorted_scores)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_scores[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return 100.0 * lo / max(1, len(sorted_scores))


def antimode(values, bins=40, hi=0.5):
    # type: (List[float], int, float) -> float
    """The valley between "never passes" and "passes", found in the histogram.

    ⚠ OTSU WAS THE WRONG TOOL AND THE NUMBER SHOWED IT. Reception share is not
    two comparable humps: it is a hard spike at zero (outsides who are replaced
    in the back row and never pass) plus a broad plateau of everyone who does.
    Otsu maximises between-group variance, which on that shape lands near the
    middle of the RANGE -- it put the outside boundary at 0.140, which files a
    player taking a tenth of her team's serve-receive as a non-passer.
    The valley is what the split actually is, so find the valley: smooth the
    histogram and take the first local minimum after the opening peak.
    """
    v = [x for x in values if x is not None]
    if len(v) < 60:
        return 0.0
    h = [0] * bins
    for x in v:
        i = int(min(bins - 1, max(0, x / hi * bins)))
        h[i] += 1
    sm = []
    for i in range(bins):
        w = h[max(0, i - 1):i + 2]
        sm.append(float(sum(w)) / len(w))
    # walk out of the opening peak, then stop at the first upturn
    i = 0
    while i + 1 < bins and sm[i + 1] <= sm[i]:
        i += 1
    if i == 0 or i >= bins - 1:
        return 0.0
    return (i + 0.5) * hi / bins


def attach_pbp(rec, pbp, team, sets):
    # type: (Dict, Dict, str, float) -> None
    """Passing, role and involvement, from the play-by-play. Prior season only.

    ⚠ EVERY FIGURE HERE IS 2025 AND THERE IS NO 2026 EQUIVALENT. The
    play-by-play mirror runs to 2025 and there is no live route for this
    season, so these describe last season and the page must say so rather than
    let them read as current form.
    ⚠ SIDE-OUT AND FIRST-BALL KILL ARE EXPRESSED AGAINST HER OWN TEAM'S
    AVERAGE. Absolute side-out rate mostly measures how well her hitters
    convert, which is not her doing. The within-team difference is hers.
    """
    try:
        from reconcile_2025 import norm as _tn
    except Exception:
        _tn = lambda x: (x or "").lower()
    m = pbp.get((_tn(team), nkey(rec.get("name"))))
    if not m or sets <= 0:
        return
    tr = m.get("team_recv") or 0
    rc = m.get("recv") or 0
    out = {"receptions": rc, "touches": m.get("touch") or 0,
           "touch_per_set": round((m.get("touch") or 0) / sets, 2)}
    rec["pbp"] = {"serves": m.get("ev_Serve") or 0,
                  "att_front": m.get("att_front") or 0,
                  "att_back": m.get("att_back") or 0,
                  "att_front_by_rule": m.get("att_front_inferred") or 0}
    if tr >= 200:
        out["recv_share"] = round(float(rc) / tr, 4)
        out["recv_per_set"] = round(float(rc) / sets, 3)
    # ⚠ A RATE ON 12 PASSES IS NOISE. Below this the outcome rates are omitted
    # rather than shown with a caveat nobody reads.
    if rc >= 40:
        out["sideout"] = round((m.get("recv_sideout") or 0) / float(rc), 4)
        out["first_ball_kill"] = round((m.get("recv_fbk") or 0) / float(rc), 4)
    # ---- setting and serving, the two skills the box score cannot see ------
    sa = m.get("set_att") or 0
    if sa >= 200:
        out["set_att"] = sa
        out["set_kill_rate"] = round((m.get("set_kill") or 0) / float(sa), 4)
    sr = m.get("srv_rally") or 0
    if sr >= 120:
        out["srv_rally"] = sr
        out["srv_win"] = round((m.get("srv_won") or 0) / float(sr), 4)
    rec["pass"] = out


def prior_universe(prior_by_key, prior_rows_by_team, i2n, ozp,
                   ozfaced, ozlg, rposg):
    # type: (Dict, Dict, Dict) -> List[Dict]
    """Every player on a 2026 roster who has a 2025 D-I line.

    ⚠ WITHOUT THIS THE BOARDS ARE EMPTY UNTIL OCTOBER. Rating only players who
    appear in a 2026 box score means 140 players in August out of ~6,000 -- and
    "how did she do last year" is most of what there is to know right now.

    The join is NOT re-derived: returning_2026.json is the existing
    surname-anchored join (R8), already guarded. This walks it and pulls each
    player's FULL 2025 counts, which that file does not carry (it holds points
    and sets, not digs, assists or attempts).

    ⚠ AND THE JOIN IS VERIFIED RATHER THAN TRUSTED: the sets and points the
    roster file records must reconcile with the raw 2025 row we matched. A
    disagreement means we matched a different player, and it is dropped and
    counted, never rendered.
    """
    ret = (L("data/returning_%d.json" % SEASON) or {}).get("teams") or {}
    n2i = {}
    for tid, nm in i2n.items():
        n2i[nm] = tid
    out, checked, mismatch = [], 0, 0
    for team, rec in ret.items():
        tid = n2i.get(team)
        if not tid:
            continue
        pool = prior_rows_by_team.get(tid) or []
        for pl in (rec.get("returning") or []):
            if not isinstance(pl, dict):
                continue
            want = nkey(pl.get("name"))
            hit = None
            for r in pool:
                if nkey((r.get("first") or "") + (r.get("last") or "")) == want:
                    hit = r
                    break
            if not hit:
                continue
            rr = rates(hit)
            if not rr:
                continue
            checked += 1
            # ⚠ THE RECONCILE USES RAW COUNTS, THE RATING USES ADJUSTED ONES.
            # Check first, then adjust: comparing a schedule-normalised points
            # total against the roster file's raw one would fail every time.
            _pos_adj = bucket(hit.get("pos")) or bucket(pl.get("pos"))
            # the free correctness check -- two independent records of the
            # same season must agree
            pts = rr["kills"] + rr["aces"] + rr["blocks"]
            if (abs(rr["sets"] - float(pl.get("sets") or 0)) > 0.5 or
                    abs(pts - float(pl.get("pts") or 0)) > 0.6):
                mismatch += 1
                continue
            pos = _pos_adj
            if not pos:
                continue
            _rp = rposg.get((tid, nkey(pl.get("name"))))
            if _rp:
                pos = _rp
            # ⚠ AND IT MUST BE ADJUSTED, OR IT IS SCORED ON A DIFFERENT
            # FOOTING FROM THE SCALE. This path was left raw while the
            # reference distribution was schedule-normalised, which inflated
            # every player on a soft schedule and put them top of the boards.
            rr = adjust(rr, pos, ozp.get(
                (tid, nkey(hit.get("first")), nkey(hit.get("last")))),
                ozfaced.get((tid, nkey((hit.get("first") or "") +
                                       (hit.get("last") or "")))), ozlg)
            out.append({"team": team, "team_id": tid,
                        "name": pl.get("name"), "cls": pl.get("class"),
                        "pos": pos, "num": hit.get("num"), "row": rr})
    return out, checked, mismatch


# A starting six plus the libero, built as a 5-1 -- the offence 253 of 348
# teams actually start. The 6-2 variant is offered beside it because it is a
# genuinely different team, not a re-sort: it fields two setters and no
# opposite, so it asks the boards a different question.
LINEUP_51 = [("S", 1), ("OH", 2), ("OPP", 1), ("MB", 2), ("LDS", 1)]
LINEUP_62 = [("S", 2), ("OH", 2), ("MB", 2), ("LDS", 1)]


def all_star_teams(players, n_teams=3, hm=5):
    # type: (List[Dict], int, int) -> Dict
    """First, second and third teams by POWER, filled position by position.

    ⚠ THIS IS A CONSTRUCTION, NOT AN AWARD, and the page says so. It reads the
    position boards in order and fills a lineup; it is not a claim that anyone
    voted for these players. It is also NOT a cross-position ranking -- each
    slot is filled from its own board, and no comparison is ever made between a
    libero and a middle.

    A slot with nobody left to fill it renders as vacant rather than reaching
    into another position for a body (R5).
    """
    pool = {}
    for pos in POS_ORDER:
        pool[pos] = sorted([p for p in players if p["pos"] == pos],
                           key=lambda x: x["power_rank"])
    used = set()

    def take(pos, k):
        got = []
        for p in pool.get(pos, []):
            if len(got) >= k:
                break
            key = (p["team_id"], p["name"])
            if key in used:
                continue
            used.add(key)
            got.append(p)
        while len(got) < k:
            got.append(None)          # vacant, never substituted
        return got

    teams = []
    for i in range(n_teams):
        slots = []
        for pos, k in LINEUP_51:
            for p in take(pos, k):
                slots.append({"pos": pos, "player": p})
        teams.append({"tier": i + 1, "system": "5-1", "slots": slots,
                      "profile": lineup_profile(slots)})

    # the 6-2 alternative, built fresh from the top of each board
    used = set()
    alt_slots = []
    for pos, k in LINEUP_62:
        for p in take(pos, k):
            alt_slots.append({"pos": pos, "player": p})
    alt = {"tier": 1, "system": "6-2", "slots": alt_slots,
           "profile": lineup_profile(alt_slots)}

    honourable = {}
    for pos in POS_ORDER:
        rest = [p for p in pool.get(pos, [])
                if (p["team_id"], p["name"]) not in
                set((x["player"]["team_id"], x["player"]["name"])
                    for t in teams for x in t["slots"] if x["player"])]
        honourable[pos] = rest[:hm]
    return {"teams": teams, "alt_62": alt, "honourable": honourable}


def lineup_profile(slots):
    # type: (List[Dict]) -> Dict
    """What this lineup measurably does. No system is asserted.

    ⚠ IT REPORTS RATES, NOT A STYLE. Whether a team plays perimeter or
    rotational defence is not in a box score, and naming one would be inventing
    a fact about people who never played together. What IS measurable: how this
    six blocks, digs, serves and hits. The front-row block rate counts only the
    three positions that block.
    """
    def vals(field, positions=None):
        out = []
        for s in slots:
            p = s["player"]
            if not p:
                continue
            if positions and s["pos"] not in positions:
                continue
            src = p.get("prior") or (p.get("season") or {}).get("components")
            if not src or not src.get(field):
                continue
            v = src[field].get("value")
            if v is not None:
                out.append(v)
        return out

    def mean(v):
        return round(sum(v) / len(v), 3) if v else None
    return {
        "block_front": mean(vals("bps", ("MB", "OPP", "OH"))),
        "dig": mean(vals("dps")),
        "serve": mean(vals("sps")),
        "kill": mean(vals("kps", ("OH", "OPP", "MB"))),
        "hit": mean(vals("hit", ("OH", "OPP", "MB"))),
        "filled": sum(1 for s in slots if s["player"]),
        "vacant": sum(1 for s in slots if not s["player"]),
    }


def main():
    i2n = id2name()
    rpos = roster_positions()
    rcls = roster_class()
    # ⚠ THE ROSTER OUTRANKS THE BOX SCORE FOR THE NAME TOO, same rule as the
    # position above it. The feed spells Kentucky's outside "Brooklyn Deleye";
    # her school spells her DeLeye. Every consumer that joins stars back to a
    # roster -- the dossier's faces, the photo lookup -- compares STRINGS, so
    # a feed-cased name silently falls back to initials. Measured the night
    # this was fixed: 68 of 1,013 dossier stars (6.7%) failed to resolve, and
    # every example was a feed-vs-roster spelling gap. nkey() is unchanged by
    # the swap (it is how the lookup hits), so no key or join moves.
    rname = _roster_field("name_raw")
    zp, zp_src = strength_z(PRIOR, i2n)
    zc, zc_src = strength_z(SEASON, i2n)
    ozp = mean_opp_z(PRIOR, i2n, zp)
    ozc = mean_opp_z(SEASON, i2n, zc)
    defp, lgp = team_def_profile(PRIOR)
    defc, lgc = team_def_profile(SEASON)
    fdp = faced_defence(PRIOR, defp)
    fdc = faced_defence(SEASON, defc)
    pbp = load_pbp(PRIOR)
    pbp_raw = {}
    # pbp keys are (normalised team, nkey); recover the display name so team
    # baselines can be attributed
    try:
        from reconcile_2025 import norm as _tn
    except Exception:
        _tn = lambda x: (x or "").lower()
    pbp_team_name = {}
    for _nm in i2n.values():
        pbp_team_name[_tn(_nm)] = _nm

    # ---- prior season: the reference distribution and every player's prior --
    prior_rows = load_season(PRIOR)
    by_pos = collections.defaultdict(list)
    prior_by_key = {}
    prior_ambiguous = set()
    prior_rows_by_team = collections.defaultdict(list)
    for r in prior_rows:
        prior_rows_by_team[str(r.get("team_id"))].append(r)
    for r in prior_rows:
        pos = bucket(r.get("pos"))
        if not pos:
            continue
        tid0 = str(r.get("team_id"))
        if tid0 not in i2n:
            continue          # non-D-I: out of the scale AND out of the boards
        rr = rates(r)
        if not rr or rr["sets"] < 20:
            continue
        # ⚠ ADJUST BEFORE SCALING. The reference distribution must be built from
        # neutral-schedule rates too, or a player is z-scored against a
        # population measured on a different footing.
        _k0 = (tid0, nkey((r.get("first") or "") + (r.get("last") or "")))
        rr = adjust(rr, pos, ozp.get(
            (tid0, nkey(r.get("first")), nkey(r.get("last")))),
            fdp.get(_k0), lgp)
        by_pos[pos].append(rr)
        # ⚠ THE PRIOR IS KEYED WITHOUT POSITION, AND KEYING IT WITH ONE WAS A
        # BUG THE POSITION FIX EXPOSED. Resolving Olivia Babcock to OPP from her
        # school's roster orphaned her own 2025 season, which was filed under
        # OH by the box score -- so the two-time national player of the year was
        # rated on two matches with no prior at all, and nothing said so.
        # Her production is her production; it is scored against whatever
        # position we have resolved her to.
        # ⚠ AND AMBIGUOUS NAMES GET NO PRIOR RATHER THAN A GUESS (R8). 14 full
        # names are shared by 2+ players among the 4,563 with 20+ sets; those 36
        # are recorded as ambiguous and left without a prior, never merged.
        _nkp = (nkey(r.get("first")), nkey(r.get("last")))
        if _nkp in prior_by_key:
            prior_ambiguous.add(_nkp)
        prior_by_key[_nkp] = rr
    scale = scale_from(by_pos)

    for _k in prior_ambiguous:
        prior_by_key.pop(_k, None)

    # ---- this season to date ----------------------------------------------
    universe, ujoined, umismatch = prior_universe(
        prior_by_key, prior_rows_by_team, i2n, ozp, fdp, lgp, rpos)
    seeded = {}
    for u in universe:
        pos = u["pos"]
        pr = composite(u["row"], pos, scale)
        seeded[(u["team_id"], nkey(u["name"]), pos)] = {
            "team_id": u["team_id"], "team": u["team"], "name": u["name"],
            "pos": pos, "num": u["num"], "cls": u["cls"],
            "matches": 0, "sets": 0.0,
            "power": round(pr["score"], 4),
            "resume_score": None, "season_weight": 0.0,
            "has_prior": True, "prior_score": round(pr["score"], 4),
            "prior_sets": u["row"]["sets"],
            "opp_z": None, "opp_adjusted": False,
            "prior_opp_z": u["row"].get("opp_z"),
            "season": None, "prior": pr["components"],
            "totals": None,
        }

    cur_rows = load_season(SEASON)
    out = []
    unresolved = 0
    for r in cur_rows:
        tid = str(r.get("team_id"))
        if tid not in i2n:
            continue
        name = ((r.get("first") or "") + " " + (r.get("last") or "")).strip()
        name = rname.get((tid, nkey(name))) or name
        # ⚠ THE SCHOOL'S OWN ROSTER OUTRANKS THE BOX SCORE, AND THIS WAS THE
        # WRONG WAY ROUND. The feed's per-match position field calls 43 players
        # OH whom their own school lists as RS -- Olivia Babcock and Kennedy
        # Martin among them, both right-side hitters filed as outsides. AVCA
        # independently lists Babcock as RS, so two authorities agree against
        # the box score. Overall the two sources agree on only 77.1%.
        # Priority: the school, then the feed. Which one answered is recorded,
        # because a position that came from the weaker source should be
        # inspectable rather than indistinguishable.
        rp = rpos.get((tid, nkey(name)))
        pos, pos_src = (rp, "roster") if rp else (bucket(r.get("pos")), "box")
        if not pos:
            unresolved += 1
            continue
        cur = rates(r)
        if not cur:
            continue
        _kc = (tid, nkey((r.get("first") or "") + (r.get("last") or "")))
        cur = adjust(cur, pos, ozc.get(
            (tid, nkey(r.get("first")), nkey(r.get("last")))),
            fdc.get(_kc), lgc)
        key = (nkey(r.get("first")), nkey(r.get("last")))
        prr = prior_by_key.get(key)
        # scored against the position we resolved her to, not the one the box
        # score happened to print last season
        pr = composite(prr, pos, scale) if prr else None
        cs = composite(cur, pos, scale)
        n = int(cur["matches"] or 0)
        w = blend_w(n)
        # ⚠ NO PRIOR IS NOT A LICENCE TO TRUST A TWO-MATCH SAMPLE. Giving a
        # player with no prior season 100% weight on her own handful of matches
        # put a Wisconsin middle 7th in the country on two matches. A player we
        # know nothing about starts at the position AVERAGE and earns her way
        # off it at exactly the measured rate everyone else does.
        base = pr["score"] if pr else 0.0
        power = (1.0 - w) * base + w * cs["score"]
        seeded.pop((tid, nkey(name), pos), None)
        out.append({
            "team_id": tid,
            "team": i2n.get(tid),
            "name": name,
            "pos": pos,
            "num": r.get("num"),
            "cls": rcls.get((tid, nkey(name))),
            "pos_source": pos_src,
            "matches": n,
            "sets": cur["sets"],
            "power": round(power, 4),
            "resume_score": round(cs["score"], 4),
            "season_weight": round(w, 4),
            "has_prior": bool(pr),
            "prior_score": (round(pr["score"], 4) if pr else None),
            "prior_sets": (prr["sets"] if prr else None),
            "opp_z": cur.get("opp_z"),
            "opp_adjusted": bool(cur.get("opp_adjusted")),
            "prior_opp_z": (prr.get("opp_z") if prr else None),
            "season": cs,
            "prior": (pr["components"] if pr else None),
            "totals": {
                "kills": cur["kills"], "errors": cur["errors"],
                "atts": cur["atts"], "digs": cur["digs"], "aces": cur["aces"],
                "assists": cur["assists"], "blocks": cur["blocks"],
                "points": round(cur["kills"] + cur["aces"] + cur["blocks"], 1),
            },
        })

    # whoever has not played yet keeps her prior-only rating
    out.extend(seeded.values())

    # passing, involvement and rotation role, from last season's play-by-play
    for pl in out:
        attach_pbp(pl, pbp, pl.get("team") or "",
                   float(pl.get("prior_sets") or pl.get("sets") or 0))

    # ⚠ EVERY OUTCOME METRIC IS EXPRESSED AGAINST HER OWN TEAM. Absolute kill
    # rate off her sets mostly measures her HITTERS, and absolute serve-win
    # rate mostly measures her team's defence and its schedule -- which is why
    # the raw serving leaderboard came out entirely mid-major. The within-team
    # difference is the part that is hers.
    #
    # ⚠ THE BASELINE IS THE WHOLE TEAM, NOT HER POSITION-MATES, AND THE FIRST
    # VERSION GOT THAT WRONG. Comparing a setter only against OTHER SETTERS on
    # her roster needs three of them clearing the volume bar, which almost no
    # team has -- it covered 107 players out of 456. The right question is how
    # her sets do against everything her team does.
    #
    # ⚠ AND IT SUMS COUNTS RATHER THAN AVERAGING RATES. A mean of per-player
    # rates weights a libero's 40 receptions the same as a passer's 900.
    tt = collections.defaultdict(lambda: collections.Counter())
    for _t, _k in pbp_raw.items():
        pass
    for key, m in pbp.items():
        nm = pbp_team_name.get(key[0])
        if not nm:
            continue
        c = tt[nm]
        for f in ("set_att", "set_kill", "srv_rally", "srv_won",
                  "recv", "recv_sideout"):
            c[f] += m.get(f) or 0
    # ⚠ A BACKUP SETTER'S 207 SWINGS FLOATED TO THE TOP OF THE LIST. The bar is
    # not a number I picked: it is HALF HER TEAM'S BUSIEST, the same scaling
    # rule the leaderboards already use for set counts. It scales with how much
    # volleyball a team played and it keeps starters while dropping the
    # third-stringer whose rate is noise.
    peak = collections.defaultdict(lambda: collections.Counter())
    for pl in out:
        ps = pl.get("pass") or {}
        pk = peak[pl.get("team")]
        for f in ("set_att", "srv_rally", "receptions"):
            if (ps.get(f) or 0) > pk[f]:
                pk[f] = ps.get(f) or 0
    for pl in out:
        base = tt.get(pl.get("team"))
        ps = pl.get("pass")
        if not base or not ps:
            continue
        pk = peak.get(pl.get("team")) or collections.Counter()
        if (ps.get("set_att") or 0) < 0.5 * pk["set_att"]:
            ps.pop("set_kill_rate", None)
            ps.pop("set_att", None)
        if (ps.get("srv_rally") or 0) < 0.5 * pk["srv_rally"]:
            ps.pop("srv_win", None)
            ps.pop("srv_rally", None)
        for num, den, field, rel in (
                ("set_kill", "set_att", "set_kill_rate", "set_kill_rel"),
                ("srv_won", "srv_rally", "srv_win", "srv_win_rel"),
                ("recv_sideout", "recv", "sideout", "sideout_rel")):
            v = ps.get(field)
            if v is None or base[den] < 200:
                continue
            # ⚠ SHE CANNOT BE COMPARED WITH A BASELINE SHE IS MOST OF.
            # A full-time setter delivers ~90% of her team's balls, so her own
            # rate IS the team rate and the difference is near zero by
            # construction -- while a backup setting in easy spots shows a big
            # positive. Measured, and the number was unambiguous: this
            # "vs team" figure scores 0.380 AUC against All-America selection,
            # BELOW CHANCE, and adding it to the setter rating made it worse
            # (0.954 -> 0.942). Suppressed where she is the majority of the
            # denominator; the raw rate and its sample still render.
            share = (ps.get(den) or 0) / float(base[den]) if base[den] else 0.0
            if share > 0.5:
                ps[rel + "_suppressed"] = round(share, 3)
                continue
            ps[rel] = round(v - base[num] / float(base[den]), 4)

    # ⚠ SIX-ROTATION AND FRONT-ROW PINS ARE DIFFERENT JOBS AND MUST NOT SHARE A
    # RANKING. An outside who passes every rotation and one who is replaced by a
    # defensive specialist in the back row are being asked to do different
    # things, and comparing their dig and reception numbers is meaningless. The
    # boundary is measured from the shape of the distribution, not chosen.
    role_cut = {}
    for pos in POS_ORDER:
        shares = [((p.get("pass") or {}).get("recv_share"))
                  for p in out if p["pos"] == pos]
        shares = [x for x in shares if x is not None]
        role_cut[pos] = antimode(shares)
    # ⚠ TWO DIFFERENT QUESTIONS, AND I HAD THEM UNDER ONE NAME. Reception share
    # measures how much SERVE-RECEIVE she is trusted with. Whether she plays the
    # back row at all is a different fact, and calling the reception split
    # "six-rotation" was simply wrong -- it labelled 658 outsides front-row when
    # only 32 of them never enter the back row.
    #
    # ⚠ AND THE ROTATION ANSWER IS EXACT RATHER THAN INFERRED. A player reaches
    # the service line only by standing in position 1, so serving proves she
    # plays the back row. NEGATIVE CONTROL, and it is clean: of the players who
    # never serve, ZERO have a single back-row attack. Ever serving and ever
    # standing in the back row are the same fact.
    for pl in out:
        sh = (pl.get("pass") or {}).get("recv_share")
        cut = role_cut.get(pl["pos"]) or 0.0
        if sh is None:
            pl["pass_role"] = None
        elif pl["pos"] == "LDS":
            pl["pass_role"] = "primary" if sh >= cut else "reserve"
        else:
            pl["pass_role"] = "passer" if sh >= cut else "seldom"
        pz = pl.get("pbp") or {}
        srv, bk = pz.get("serves"), pz.get("att_back")
        if srv is None and bk is None:
            pl["rotation_role"] = None
        else:
            pl["rotation_role"] = ("six" if (srv or 0) > 0 or (bk or 0) > 0
                                   else "front")
        # ⚠ BACK-ROW SHARE IS REPORTED ONLY WHERE THE SLOT IS ONE PLAYER.
        # A middle shares her rotation slot with the libero, so the serve order
        # cannot say which of them was on court -- classified that way a libero
        # comes out 41.8% front row, which is physically impossible.
        f, b = pz.get("att_front"), pz.get("att_back")
        if pl["pos"] in ("OH", "OPP", "S") and f is not None and (f + b) >= 30:
            pl["back_row_share"] = round(float(b) / (f + b), 4)
        else:
            pl["back_row_share"] = None

    # ---- ranks WITHIN position, for each board separately -------------------
    boards = {}
    for pos in POS_ORDER:
        grp = [p for p in out if p["pos"] == pos]
        ref = sorted(c["score"] for c in
                     (composite(rr, pos, scale) for rr in by_pos[pos]))
        grp.sort(key=lambda x: -x["power"])
        for i, p in enumerate(grp, 1):
            p["power_rank"] = i
        # ⚠ RESUME RANKS ONLY THOSE WITH A SEASON LINE. A player who has not
        # played has no resume -- ranking her last would read as "worst", which
        # is a claim the data does not make. She is absent from that board.
        played = [p for p in grp if p["resume_score"] is not None]
        played.sort(key=lambda x: -x["resume_score"])
        for i, p in enumerate(played, 1):
            p["resume_rank"] = i
        for p in grp:
            p.setdefault("resume_rank", None)
        for p in grp:
            p["power_pct"] = round(percentile(ref, p["power"]), 1)
        grp.sort(key=lambda x: x["power_rank"])
        boards[pos] = {
            "label": POS_LABEL[pos],
            "support": SUPPORT[pos][0],
            "support_auc": SUPPORT[pos][1],
            "caveat": SUPPORT[pos][2],
            "n": len(grp),
            "n_played": len(played),
            "weights": WEIGHTS[pos],
        }

    doc = {
        "meta": {
            "season": SEASON,
            "prior_season": PRIOR,
            "source_tier": "DERIVED",
            "built": None,
            "n_players": len(out),
            "n_unresolved_position": unresolved,
            "n_prior_ambiguous_names": len(prior_ambiguous),
            "n_roster_joined": ujoined,
            "n_roster_join_rejected": umismatch,
            "scale_from": ("%d full season -- a finished distribution, so an "
                           "early-season rate is not scored against whoever "
                           "happens to have played" % PRIOR),
            "criterion": ("weights fitted to predict AVCA All-America "
                          "selection with team strength held constant; "
                          "validated among players on comparable teams"),
            "blend": BLEND,
            "blend_note": ("measured, not chosen: share of the rating carried "
                           "by this season at n matches played"),
            "no_cross_position_board": True,
            "opponent_adjustment": {
                "slopes": OPP_SLOPE,
                "prior_strength_source": zp_src,
                "season_strength_source": zc_src,
                "note": ("every component is normalised to a neutral schedule "
                         "using within-player slopes; a player whose opponents "
                         "are unrated is left unadjusted and flagged"),
            },
            "cannot_see": ("serve-receive is absent from the feed, so passing "
                           "-- a libero's and an outside's primary job -- is "
                           "not measured anywhere in this rating"),
        },
        "boards": boards,
        "scale": scale,
        "players": out,
    }
    # ⚠ THE OVERALL BOARD RANKS BY PERCENTILE WITHIN POSITION, WHICH IS THE
    # ONLY CROSS-POSITION CURRENCY THIS DATA SUPPORTS. It says "she is further
    # above the field of outsides than that setter is above the field of
    # setters" -- a comparison of standing, not of value. It does NOT claim a
    # libero at #8 is better than a middle at #12, because nothing in a box
    # score can support that and pretending otherwise would be the one thing
    # this whole rating is built to avoid.
    for pl in out:
        pl["overall_pct"] = pl.get("power_pct")
    ranked = [p for p in out if p.get("overall_pct") is not None]
    ranked.sort(key=lambda x: (-x["overall_pct"], x["power_rank"]))
    for i, pl in enumerate(ranked, 1):
        pl["overall_rank"] = i
    doc_overall = {
        "basis": "percentile within her own position",
        "n": len(ranked),
        "note": ("a comparison of standing, not of value: it says how far "
                 "above her own position's field she is, and never that one "
                 "position outranks another"),
    }

    doc["all_star"] = all_star_teams(out)
    doc["overall"] = doc_overall
    doc["meta"]["role_split"] = {
        "cuts": role_cut,
        "pass_role_note": ("how much serve-receive she is trusted with -- NOT "
                           "whether she plays the back row"),
        "rotation_note": ("six-rotation is proven by serving: reaching the "
                          "service line requires standing in position 1. Of "
                          "the players who never serve, zero have a back-row "
                          "attack."),
        "note": ("reception share where the distribution itself separates a "
                 "six-rotation pin from a front-row one -- the valley in the "
                 "histogram, not a chosen "
                 "threshold"),
    }
    doc["meta"]["passing_season"] = PRIOR
    doc["meta"]["not_rating_inputs"] = (
        "setting and serving outcomes are CONTEXT, never rating inputs. "
        "Measured against All-America selection: team-relative setting alone "
        "scores 0.380 AUC (below chance, because a primary setter is most of "
        "her own baseline), and adding setting or serving to the setter "
        "rating lowered it from 0.954 to 0.942 and 0.898. They describe a "
        "player; they do not rank her.")
    doc["meta"]["passing_note"] = (
        "passing, touches and rotation role come from the %d play-by-play; "
        "there is no live source for them this season" % PRIOR)
    doc["meta"]["all_star_note"] = (
        "constructed from the position boards, not voted on; each slot is "
        "filled from its own position's board and no libero is ever compared "
        "with a middle")

    p = os.path.join(REPO, "data/player_rating_%d.json" % SEASON)
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=1, sort_keys=True))
    print("wrote %s" % p)
    print("  %d rated | %d with no resolvable position"
          % (len(out), unresolved))
    for pos in POS_ORDER:
        g = [x for x in out if x["pos"] == pos]
        if not g:
            print("  %-4s none yet" % pos)
            continue
        top = min(g, key=lambda x: x["power_rank"])
        print("  %-4s n=%3d  top: %-24s %-16s POWER %+.2f (%.0f%% this season)"
              % (pos, len(g), top["name"], top["team"] or "?", top["power"],
                 100 * top["season_weight"]))
    a = doc["all_star"]
    for t in a["teams"]:
        names = ["%s %s" % (x["pos"], x["player"]["name"]) if x["player"]
                 else "%s VACANT" % x["pos"] for x in t["slots"]]
        print("  team %d (5-1): %s" % (t["tier"], " | ".join(names)))
    print("  6-2 alt:     %s" % " | ".join(
        ("%s %s" % (x["pos"], x["player"]["name"])) if x["player"]
        else "%s VACANT" % x["pos"] for x in a["alt_62"]["slots"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
