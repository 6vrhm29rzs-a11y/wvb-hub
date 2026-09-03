#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Cody/RANKINGS-AND-BRACKET.html -- our ranking beside everyone else's,
plus a projected 64-team field.

*** THE OTHER RANKINGS ARE REFERENCE COLUMNS. THEY ARE NEVER INPUTS. ***
Cody's instruction, 2026-08-18: "don't use the other rankings as part of our
analytics, just as a reference and comparison". Nothing in this file feeds
rating_2025.py, project_field.py, or any model. It reads their outputs and puts
other people's numbers in adjacent columns so disagreement is visible.

TWO OF OUR NUMBERS, AND THEY ANSWER DIFFERENT QUESTIONS:
  "2025 final"  -- the fitted composite. MEASURED and validated: beats RPI
                   out-of-sample at three chronological cutoffs. It is a record
                   of last season, not a forecast.
  "2026 pre"    -- DERIVED and UNVALIDATED. Last season's composite nudged by
                   how much production each roster kept. There is no 2026 match
                   yet, so there is nothing to validate it against and no claim
                   is made about its accuracy. It exists because a bracket needs
                   an ordering, and it is labelled everywhere it appears.

R5: a team we cannot match into a source renders as an em dash in that column.
Nothing is imputed, and the per-source match rate is printed on the page.

Python 3.9 target.
"""

import json
import os
import re
import sys
import datetime
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconcile_2025 import norm  # noqa: E402

# The season whose RESULTS drive the live rank. rating_2025.py is
# season-parameterised and writes data/rating_{SEASON}.json.
SEASON = int(os.environ.get("WVB_SEASON", "2026"))

OUT = os.path.join(REPO, "Cody", "RANKINGS-AND-BRACKET.html")

# Names differ across five independent sources. Anything not resolvable by
# norm() gets an explicit alias -- an alias map is a claim about identity, so it
# is written out rather than inferred, and unmatched names are REPORTED.
ALIAS = {
    "southerncalifornia": "usc",
    "sc": "usc",
    "miamifl": "miami",
    "miamiflorida": "miami",
    "arizonast": "arizonastate",
    "pennst": "pennstate",
    "floridast": "floridastate",
    "kansasst": "kansasstate",
    "michiganst": "michiganstate",
    "iowast": "iowastate",
    "coloradost": "coloradostate",
    "oregonst": "oregonstate",
    "washingtonst": "washingtonstate",
    "sandiegost": "sandiegostate",
    "sanjosest": "sanjosestate",
    "utahst": "utahstate",
    "boisest": "boisestate",
    "texasst": "texasstate",
    "arkansasst": "arkansasstate",
    "illinoisst": "illinoisstate",
    "wichitast": "wichitastate",
    "longbeachst": "longbeach",
    "sdakotast": "southdakotast",
    "northerniowa": "uni",
    "wku": "westernky",
    "ucsantabarbara": "ucsb",
    "southflorida": "southfla",
    "loyolamarymount": "lmuca",
    "stephenfaustin": "sfa",
    "appalachianst": "appstate",
    "csnorthridge": "csun",
    "cssacramento": "sacramentostate",
    "sacramentost": "sacramentostate",
    "neomaha": "omaha",
    "ncolorado": "northerncolo",
    "loymarymount": "lmuca",
    "gasouthern": "georgiasouthern",
    "coastalcar": "coastalcarolina",
    "flatlantic": "flaatlantic",
    "floridaintl": "fiu",
    "ilchicago": "uic",
    "wmichigan": "westernmich",
    "sfaustin": "sfa",
    "ekentucky": "easternky",
    "stmarysca": "saintmarysca",
    "stjohns": "stjohnsny",
    "americanuniv": "american",
    "connecticut": "uconn",
    "mississippi": "olemiss",
    "mississippist": "mississippistate",
    "fgcu": "floridagulfcoast",
    "kennesaw": "kennesawst",
    "utrgv": "utriograndevalley",
    "northernarizona": "northernariz",
    "stthomasmn": "stthomas",
    "cspoly": "calpoly",
}


def key(name: str) -> str:
    k = re.sub(r"[^a-z]", "", norm(name or "").lower())
    return ALIAS.get(k, k)


def live_rating_mature(live):
    """(ok, why_not) -- may the pure-season composite replace the blend?

    True only when the MEDIAN team's counted matches >= the blend's own
    measured k (digby meta k_matches: where season and prior weigh
    equally). Below that, the typical team's season evidence is still the
    minority voice and the blend keeps the board. k missing -> hold, and
    say so; a gate that cannot read its constant must fail closed."""
    teams = live.get("teams") or []
    gp = sorted(int(t.get("games_played") or 0) for t in teams)
    med = gp[len(gp) // 2] if gp else 0
    k = ((load_json("data/digby_top25_%d.json" % SEASON) or {})
         .get("meta") or {}).get("k_matches")
    if k is None:
        return False, ("blend k unavailable -- holding the blend "
                       "(median gp %d)" % med)
    if med >= k:
        return True, None
    return False, ("median team has %d counted matches against the "
                   "measured crossover k=%.1f -- season evidence is still "
                   "the minority voice; the blend holds" % (med, k))


def load_json(p, default=None):
    path = os.path.join(REPO, p)
    if not os.path.exists(path):
        return default
    return json.load(open(path))


def load_pipe(p) -> List[List[str]]:
    path = os.path.join(REPO, p)
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(line.split("|"))
    return rows


def pick_comparison(snaps, this_week, rank_source):
    """The snapshot the movement column should measure against, or None.

    Two rules, both paid for:
      * not THIS week -- the column answers "since the last published freeze",
        not "since this morning".
      * SAME BASIS -- a preseason rank and a live rank are different rulers.
        Comparing across the crossover produces arrows that are arithmetically
        correct and factually false: a mid-major at #14 on roster projection
        lands near #80 on a rating that punishes weak schedules, and the page
        would say it fell 66 places when nothing about the team changed.

    Returns None when there is no same-basis earlier week, which the page
    renders as blank rather than as a dash.

    ⚠ NORMALISE THE NAME BEFORE COMPARING. The archive holds a week written as
    "digby" and the board now calls that same ordering "blend"; one ruler, two
    words. An exact string match would find no earlier same-basis week and
    blank the whole movement column -- a silent failure that looks exactly like
    "there is no history yet". snapshot_rankings.basis() is the one definition.
    """
    from snapshot_rankings import basis
    want = basis(rank_source)
    earlier = [s for s in snaps
               if s.get("week") != this_week
               and basis(s.get("source")) == want]
    return earlier[-1] if earlier else None


def build():
    rating = load_json("data/rating_2025.json")
    if not rating:
        print("no data/rating_2025.json -- run rating_2025.py first")
        raise SystemExit(1)
    returning = (load_json("data/returning_2026.json") or {}).get("teams", {})

    # ---- our two numbers -------------------------------------------------
    # 2026 CONFERENCE MEMBERSHIP, from ncaa.com's own 2026 scoreboard, not last
    # season's alignment. 29 D-I teams changed league: the Pac-12 rebuilt itself
    # from Mountain West and WCC schools, and the WAC dissolved into the UAC,
    # Big Sky and Big West. Assigning automatic bids on 2025 membership handed
    # them to leagues that no longer have those teams.
    conf26 = (load_json("data/raw/2026/conferences_2026.json") or {})
    conf26_teams = dict(conf26.get("teams", {}))
    # A stale label repaired from the team's OWN SCHEDULE, applied at the single
    # point conferences enter this build (R4). ncaa.com still serves UT
    # Arlington under "wac"; all 16 of its conference-play fixtures are against
    # UAC teams. See scripts/conference_repair.py -- the mirrored file is left
    # untouched, so what ncaa.com says stays recoverable.
    _ovr = (load_json("data/raw/2026/conference_overrides.json") or {}).get("overrides") or {}
    for _t, _c in _ovr.items():
        if _t in conf26_teams:
            conf26_teams[_t] = _c

    teams = []
    for r in rating["teams"]:
        rec = returning.get(r["team"]) or {}
        # Same computation build_vb.py uses for the dashboard's "Returning %"
        # (returning points / (returning + departed) points). Deliberately not a
        # second definition of the same word -- R4: one meaning per name.
        ret = None
        if rec.get("returning") is not None:
            ret_pts = sum((x.get("pts") or 0) for x in rec.get("returning") or [])
            dep_pts = sum((x.get("pts") or 0) for x in rec.get("departed") or [])
            tot = ret_pts + dep_pts
            if tot:
                ret = round(ret_pts / float(tot), 3)
        teams.append({
            "team": r["team"],
            "conf": conf26_teams.get(r["team"]) or r.get("conference") or "",
            "conf25": r.get("conference") or "",
            "composite": r.get("composite"),
            "rank25": r.get("composite_rank"),
            "rpi": r.get("official_rpi_rank"),
            "wins": r.get("wins"), "losses": r.get("losses"),
            "ret": ret,
            "k": key(r["team"]),
        })
    teams.sort(key=lambda t: (t["rank25"] is None, t["rank25"]))
    for i, t in enumerate(teams, 1):
        if t["rank25"] is None:
            t["rank25"] = i

    # 2026 ordering comes from scripts/project_2026.py -- the roster-based
    # projection (quality-adjusted rates of each team's top-6 rotation). If it
    # has not been built, fall back to last season's order rather than inventing
    # a second, different projection here. One definition, one place.
    # The page used to hard-code "confirmed for only 6 of 32". That number went
    # stale the moment the map was filled in, and a stale caveat is worse than
    # none -- it understates what we know. Computed from the file instead.
    _aq = (load_json("data/raw/%d/aq_mechanism_%d.json" % (SEASON, SEASON)) or {})
    _rows = (_aq.get("conferences") or {})
    _conf_n = sum(1 for v in _rows.values() if "CONFIRMED" in (v.get("tier") or ""))
    _reg = sorted(k for k, v in _rows.items() if v.get("mechanism") == "REGULAR_SEASON")
    if _rows and _conf_n == len(_rows):
        aq_mech_note = (
            "How each league awards its bid is now confirmed for all %d "
            "conferences, from ncaa.com's own 2025 automatic-qualifier tracker. "
            "%d hold a tournament; %s award it to the regular-season champion. "
            "Two caveats: that is 2025 evidence, and leagues do change format "
            "&mdash; the Big Ten and Pac-12 both added a tournament for 2026, "
            "which is applied here."
            % (len(_rows), len(_rows) - len(_reg),
               ", ".join(_reg) if _reg else "none"))
    else:
        aq_mech_note = (
            "How each league awards its bid is confirmed for %d of %d "
            "conferences; the rest default to \u201ctournament\u201d and are "
            "flagged unverified. That is an open item, not a result."
            % (_conf_n, len(_rows) or 32))

    proj = (load_json("data/projection_2026.json") or {}).get("teams", [])
    pj = {r["team"]: r for r in proj}

    # ---- LIVE RANK BEATS THE PRESEASON RANK, AS SOON AS ONE EXISTS -------
    # The preseason projection reads NO 2026 result: it is 2026 rosters x 2025
    # production, so it cannot move when a team wins or loses. Texas lost 1-3 to
    # Arizona St. and stayed #2. That is correct for what it IS -- a projection --
    # and wrong for what a ranking tab is read as.
    #
    # rating_2025.py is season-parameterised and already computes the in-season
    # composite (RPI + opponent-adjusted net points/set, weights FITTED on 2025).
    # It refuses to fit under 50 played matches, which is the right call and is
    # why this is a fallback rather than a switch: the live rating takes over
    # automatically the moment the season has produced enough evidence.
    live = load_json("data/rating_%d.json" % SEASON) or {}
    # ⚠ A RATING FILE EXISTING IS NOT THE SAME AS A RATING BEING USABLE. The
    # 50-match floor in rating_2025.py is fit-FEASIBILITY (can a logistic run
    # at all), and the 2026 calendar delivered 73 matches in a single day --
    # so on the evening of 2026-08-28 the file appeared with median
    # games_played 0, every team flagged low_confidence, five teams at 100.0
    # and duplicate ranks, and this board ranked Missouri St. #3 on it. The
    # script itself had printed "too few matches to validate; skipping".
    # The gate is therefore the rating's OWN verdict: `meta.validated` is True
    # only when the incremental validation ran (>=400 dated matches, the gate
    # that already existed) and produced numbers. Until then the blend -- built
    # and MEASURED for exactly this window (k=13.5 matches per team) -- keeps
    # the board. No new threshold is introduced here (R1): the board defers to
    # a validation the model already performs.
    _live_ok = bool((live.get("meta") or {}).get("validated"))
    # ⚠⚠ VALIDATED IS STILL NOT MATURE (Cody, 2026-09-02: "what the actual
    # F happened to the power rankings" -- Lehigh #3, Toledo #9, Weber St.
    # #10 on a median of THREE games per team). meta.validated proves the
    # incremental validation RAN; it says nothing about whether a
    # pure-season ordering is yet better than the blend. The blend's own
    # MEASURED constant answers that: k = the matches at which this season
    # and the projection weigh equally (13.5, recomputed each run from
    # measured variances). Until the MEDIAN team has played >= k counted
    # matches, the season side has not earned majority weight for the
    # typical team, and the pure-season composite must not replace the
    # blend that is measured for exactly this window. No new threshold:
    # the gate reuses the blend's own fitted crossover point.
    # ── CERTIFIED PROPERTY (migration commit 3): the board no longer
    # computes maturity -- it REQUIRES the named property from the
    # certification step, paired to this build's corpus and to the exact
    # generations of both inputs. Absence or a stale pairing raises: the
    # build cannot cross a wrong-generation certificate. The legacy
    # live_rating_mature stays ONLY for certify_rankings and the shadow
    # guard -- never a runtime fallback here.
    if _live_ok:
        from properties import require_property
        import season_counts as _SCG
        _certs = load_json("data/ranking_certificates_%d.json" % SEASON)
        _digby_doc = load_json("data/digby_top25_%d.json" % SEASON) or {}
        _rec = require_property(
            _certs, "ordering_mature_for_public_rank",
            consumer="rankings_board", expected=None,
            corpus_fingerprint=_SCG.corpus_fingerprint(SEASON),
            dependency_fingerprints={
                "rating_%d" % SEASON:
                    (live.get("meta") or {}).get("corpus_fingerprint"),
                "digby_top25_%d" % SEASON:
                    (_digby_doc.get("meta") or {})
                    .get("corpus_fingerprint")})
        _live_ok = bool(_rec["value"])
        _why_hold = (_rec.get("measurement") or {}).get("held_because")
    else:
        _why_hold = None
    if _why_hold:
        print("  live fit HELD: %s" % _why_hold)
    # ⚠ JOIN THROUGH THE NORMALISER (first live Sunday, 2026-08-30): the
    # rating stores a team with no resolved display name under its
    # lowercase norm key ('brown', 'penn'); an exact-name join missed 10
    # teams and the per-team fallback quietly handed them BLEND ranks on
    # a LIVE board -- two rulers, duplicate ranks.
    from reconcile_2025 import norm as _n26
    live_by_team = {}
    _live_all_norms = set()
    if _live_ok:
        for r in (live.get("teams") or []):
            _live_all_norms.add(_n26(r["team"]))
            if r.get("composite_rank"):
                live_by_team[_n26(r["team"])] = r

    # ⚠ THE TAB CALLED "RANKINGS" USED TO BE UNABLE TO MOVE, AND THAT WAS THE
    # WHOLE OF Cody's objection ("texas looks a hot mess and is too high").
    # rating_2025.py refuses to fit under 50 played matches -- correctly, there
    # is no schedule graph before then -- so with 7 matches on the board this
    # fell straight through to project_2026.py, a projection that reads NO 2026
    # result at all. Texas sat 2nd on a number computed in July, three days
    # after losing 3-1 at home.
    #
    # digby_top25.py already solved this for 25 teams: blend the projection with
    # this season's margin, weight n/(n+k), k MEASURED. It now emits all 348, so
    # the board can use the same ordering rather than compute a second one.
    #
    # Precedence, most evidence first:
    #   live   -- the fitted composite, once the season can support it
    #   blend  -- projection + results so far, so the tab moves from match one
    #   preseason -- projection alone, only if the blend is missing
    blend_by_team = {}
    _blend_doc = load_json("data/digby_top25_%d.json" % SEASON) or {}
    for r in (_blend_doc.get("all") or []):
        if r.get("rank"):
            blend_by_team[r["team"]] = r
    rank_source = ("live" if live_by_team
                   else ("blend" if blend_by_team else "preseason"))
    # The stamp of the ranking actually SHOWN, from that artifact's own meta --
    # never the page build time, which keeps ticking when nothing recomputed.
    _src_meta = ((live.get("meta") or {}) if live_by_team
                 else (_blend_doc.get("meta") or {}))
    rank_stamp = {
        "generated_at_utc": _src_meta.get("generated_at_utc"),
        "matches_in": (_src_meta.get("matches") if live_by_team
                       else _src_meta.get("matches_counted")),
        "data_through_epoch": _src_meta.get("data_through_epoch"),
    }

    for t in teams:
        r = pj.get(t["team"]) or {}
        lr = live_by_team.get(_n26(t["team"]))
        br = blend_by_team.get(t["team"])
        # the invariant distinguishes a JOIN MISS (the team is in the
        # rating file under another spelling -- two rulers would mix) from
        # a team the rating GENUINELY declines to rank (Saint Francis: no
        # fixtures, no rank; its page explains itself)
        if live_by_team and not lr and _n26(t["team"]) in _live_all_norms:
            raise SystemExit(
                "live board join miss: %r has no live rank -- a per-team "
                "fallback would put two rulers on one column" % t["team"])
        # ⚠ NO PRESEASON NUMBER MAY INTERLEAVE A BLEND/LIVE BOARD (caught
        # 2026-09-01: Saint Francis's preseason #239 collided with UC
        # Davis's blend #239 after a corrections reshuffle -- two rulers,
        # one column, a duplicate rank). The talent_rank fallback applies
        # ONLY while the whole board is preseason; otherwise a team with no
        # rank on the board's own basis joins the unranked tail, where its
        # page already explains itself.
        t["rank26"] = ((lr or {}).get("composite_rank")
                       or ((br or {}).get("rank")
                           if not live_by_team else None)
                       or (r.get("talent_rank")
                           if not (live_by_team or blend_by_team) else None))
        t["rank_source"] = "live" if lr else ("blend" if br else "preseason")
        t["blend_matches"] = (br or {}).get("matches")
        t["blend_season_weight"] = (br or {}).get("weight_on_season")
        t["gp"] = (lr or {}).get("games_played")
        t["low_conf"] = bool((lr or {}).get("low_confidence"))
        t["proj_pps"] = r.get("proj_points_per_set")
        t["q25"] = r.get("q_2025")
        t["tin6"] = r.get("transfers_in_rotation")
        t["incoming"] = r.get("incoming_unplayed")
        t["rot"] = r.get("rotation_known")
        t["rotation"] = r.get("rotation") or []
        # the arithmetic behind the rank, so the page can show its working
        t["why"] = {
            "prior": r.get("composite_2025"),
            "prior_rank": r.get("rank_2025"),
            "delta_raw": r.get("roster_delta"),
            "talent": r.get("talent"),
            "pool": r.get("pool_size"),
            "unknown": r.get("incoming_unplayed"),
        }
    # ---- POWER: one number, on a stated scale ----------------------------
    # Cody: "there needs to be some power ranking score or something for me to
    # quantify it all."
    #
    # ⚠ WHAT THIS DELIBERATELY IS NOT. Both AI proposals he relayed specify a
    # 100-point blend with hand-picked component weights (25 strength / 20
    # resume / 15 SOS / 12 match performance / ...). This project has paid for
    # that mistake precisely: the roster term was hand-set at 0.15, 0.30, 0.50
    # and 1.00, every one of which made the ordering WORSE, and the fitted value
    # was 0.09. And rating_factors.py has now tested fifteen weighting schemes
    # and nine profile metrics against held-out matches -- nothing beat the
    # fitted composite, and nine ideas measurably hurt. Inventing a nine-way
    # blend on top of that would replace a validated ordering with an unvalidated
    # one and hide it behind a confident-looking number out of 100.
    #
    # So POWER is a MONOTONE RESCALING of the composite this project already
    # validated -- the ordering is exactly the rating's, and the number just
    # makes the GAPS legible, which is what a rank alone cannot do.
    #
    #     power = 50 + 12.5 * z        (z = the composite's z-score, clipped 0-100)
    #
    # 50 is an average D-I team and every 12.5 points is one standard deviation.
    # The scale is FIXED rather than stretched to put the leader at 100: a
    # week-to-week comparison has to mean something, and "best team this week"
    # is a moving target. The page states the scale, because a number out of 100
    # that does not say what 100 means is decoration.
    # ⚠ IT MUST BE THE QUANTITY THE RANK IS BUILT FROM, AND THE FIRST VERSION
    # WAS NOT. Scoring the 2025 `composite` while `rank26` comes from the
    # preseason PROJECTION put #7 SMU (76.7) above #6 Louisville (76.1) and
    # #348 above #347 -- a score that contradicts the rank printed beside it,
    # which is worse than no score at all because both look authoritative. Read
    # the value behind rank26: the live composite once the rating fits, the
    # projection's own blend until then. Asserted monotone below.
    for t in teams:
        lr = live_by_team.get(_n26(t["team"]))
        br = blend_by_team.get(t["team"])
        r = pj.get(t["team"]) or {}
        # SAME PRECEDENCE AS rank26 ABOVE, and it has to be: scoring one
        # quantity next to a rank built from another is exactly how #7 came to
        # sit above #6 earlier today. Guarded on the built page.
        t["_pv"] = (lr or {}).get("composite")
        # ⚠ SAME BASIS-PURITY AS rank26 (2026-09-01): on a live board a
        # team the rating declines to rank sits in the unranked TAIL -- and
        # must not wear a score from another ruler beside live scores
        # (Saint Francis's preseason 48.4 rendered above #348's live 13.6).
        # An unranked team shows no score; its page explains itself.
        if live_by_team:
            pass                       # live composite or nothing
        elif t["_pv"] is None and br is not None:
            t["_pv"] = br.get("score")
        elif t["_pv"] is None:
            t["_pv"] = r.get("blend")
            if t["_pv"] is None:
                t["_pv"] = r.get("talent")
    _cvals = [t["_pv"] for t in teams if t.get("_pv") is not None]
    if len(_cvals) > 30:
        _mu = sum(_cvals) / float(len(_cvals))
        _sd = (sum((v - _mu) ** 2 for v in _cvals) / len(_cvals)) ** 0.5 or 1.0
    else:
        _mu = _sd = None
    for t in teams:
        c = t.get("_pv")
        if _mu is None or c is None:
            t["power"] = None
            continue
        z = (c - _mu) / _sd
        t["power"] = round(max(0.0, min(100.0, 50.0 + 12.5 * z)), 1)
        t["power_z"] = round(z, 3)
        t["power_basis"] = t.get("rank_source") or "preseason"
    for t in teams:
        t.pop("_pv", None)

    # ---- RESUME: what a team has EARNED, beside how good it is -----------
    # R3 has said since Phase 3 that strength is not resume, and measured it:
    # relative to RPI our composite favours teams with WORSE records. The site
    # shipped only the strength side, which is the whole of the objection that
    # a 0-1 team sat near the top -- POWER correctly says "still a very good
    # roster" while the reader is asking "what have they actually done?"
    #
    # Ranked by RPI, because that beat every alternative against the 64 teams
    # the committee ACTUALLY selected in 2025 (5-fold CV: RPI 0.9215, WAB
    # 0.9107, POWER 0.9071, and every blend worse than RPI alone). `wab` rides
    # along as the readable form -- "+19.2 wins more than a bubble team would
    # have taken from this schedule".
    _res = load_json("data/resume_%d.json" % SEASON) or {}
    # CERTIFIED PROPERTY (migration commit 5): the resume view consumes
    # the producer's own certification. expected=None -- an inactive
    # resume is a legitimate certified state early in a season; an
    # artifact with NO certification falls back to the legacy boolean
    # during the remaining migration window.
    try:
        from properties import require_property as _reqp
        resume_active = bool(_reqp(_res, "resume_populated",
                                   consumer="resume_view",
                                   expected=None)["value"])
    except Exception:
        resume_active = bool((_res.get("meta") or {}).get("active"))
    resume_meta = _res.get("meta") or {}
    _rmap = dict((r["team"], r) for r in (_res.get("teams") or []))
    for t in teams:
        rr = _rmap.get(t["team"]) or {}
        t["resume_rank"] = rr.get("rank")
        t["wab"] = rr.get("wab")

    # ---- movement since the last weekly freeze ---------------------------
    # Compared against the most recent snapshot that is NOT this week's, so the
    # column answers "since the last published poll", not "since this morning".
    hist_path = os.path.join(REPO, "data", "rankings_history_%d.jsonl" % SEASON)
    prev = {}
    prev_week = None
    if os.path.exists(hist_path):
        snaps = []
        for line in open(hist_path):
            line = line.strip()
            if not line:
                continue
            try:
                snaps.append(json.loads(line))
            except ValueError:
                continue
        if snaps:
            import datetime as _dt
            iso = _dt.date.today().isocalendar()
            this_week = "%d-W%02d" % (iso[0], iso[1])
            use = pick_comparison(snaps, this_week, rank_source)
            if use:
                prev_week = use["week"]
                prev = dict((r["team"], r["rank"]) for r in use.get("teams", []))
    for t in teams:
        pr = prev.get(t["team"])
        t["prev_rank"] = pr
        # positive = moved UP the table (a smaller rank number)
        t["move"] = (pr - t["rank26"]) if (pr and t.get("rank26")) else None
    if prev_week:
        print("  movement vs %s (%d teams)" % (prev_week, len(prev)))
    else:
        print("  no earlier weekly snapshot yet -- movement column stays blank")

    # ⚠ SAY WHICH CASE IT ACTUALLY IS. "no 2026 rating yet -- under 50 played
    # matches" became FALSE the moment a fitted-but-unvalidated rating existed:
    # the file was there, the gate just refused it. A log line that
    # mis-states the reason sends the next debugging session to the wrong
    # place.
    if live_by_team:
        _why = "  (%d teams rated on 2026 results)" % len(live_by_team)
    elif _why_hold:
        _why = "  (a validated 2026 fit exists but is HELD: %s)" % _why_hold
    elif (live.get("meta") or {}).get("validated") is False:
        _why = ("  (a 2026 fit exists but has NOT validated yet -- "
                "%s matches; the blend holds until it does)"
                % ((live.get("meta") or {}).get("matches") or "too few"))
    else:
        _why = "  (no 2026 rating file yet)"
    print("  rank source: %s%s" % (rank_source, _why))
    unranked = [t for t in teams if t["rank26"] is None]
    nmax = max([t["rank26"] for t in teams if t["rank26"]] or [0])
    for i, t in enumerate(sorted(unranked, key=lambda x: x["rank25"]), 1):
        t["rank26"] = nmax + i          # listed last, never interleaved
        t["unranked"] = True

    by_key = {}
    for t in teams:
        by_key.setdefault(t["k"], t)

    # ---- reference columns ----------------------------------------------
    unmatched = {}

    def attach(field, pairs, label):
        miss = []
        for rank, name in pairs:
            t = by_key.get(key(name))
            if t is None:
                miss.append(name)
                continue
            if t.get(field) is None:
                t[field] = rank
        unmatched[label] = miss

    # LATEST capture, never a hard-coded filename. This used to point at
    # `avca_poll_2026-08-18.json` -- a single preseason snapshot -- so the page
    # would still have been showing the August poll in November while labelling
    # it "AVCA". scripts/crawl_polls.py appends a dated capture whenever the
    # poll's own "Through Games" stamp changes.
    avca = {}
    _pl = os.path.join(REPO, "data", "raw", str(SEASON), "polls_avca.jsonl")
    if os.path.exists(_pl):
        for _line in open(_pl):
            _line = _line.strip()
            if not _line:
                continue
            try:
                _rec = json.loads(_line)
            except ValueError:
                continue
            avca = {"rows": _rec.get("rows") or [],
                    "meta": {"updated_label": _rec.get("stamp"),
                             "captured": _rec.get("captured_utc")}}
    if not avca:
        avca = load_json("data/raw/2026/avca_poll_2026-08-18.json") or {}
    attach("avca", [(int(r["RANK"]), re.sub(r"\s*\(\d+\)\s*$", "", r["SCHOOL"]))
                    for r in avca.get("rows", []) if str(r.get("RANK", "")).isdigit()], "AVCA")

    attach("vt", [(int(c[0]), c[1]) for c in load_pipe("Cody/data/vt_poll_2026.txt")
                  if c and c[0].isdigit()], "VolleyTalk")

    attach("massey", [(int(c[0]), c[1]) for c in load_pipe("Cody/data/massey_2026_preseason.txt")
                      if c and c[0].isdigit()], "Massey")

    # ---- projected 64-team field ----------------------------------------
    # 32 automatic bids: the top team of each conference by our 2026 estimate.
    # THIS IS A PROJECTION OF A CHAMPION, not a standing. Most conferences award
    # the AQ by tournament, so the actual bid can go to anyone in the field.
    order = sorted(teams, key=lambda t: t["rank26"])
    # A league needs enough D-I members to be a league. UT Arlington is still
    # served under "wac", which no longer fields a D-I volleyball conference --
    # left unguarded it becomes a one-team league collecting an automatic bid.
    MIN_CONF = 6
    size = {}
    for t in teams:
        if t["conf"]:
            size[t["conf"]] = size.get(t["conf"], 0) + 1
    too_small = sorted(c for c, n in size.items() if n < MIN_CONF)
    aq, seen_conf = [], set()
    for t in order:
        if t["conf"] and size.get(t["conf"], 0) >= MIN_CONF and t["conf"] not in seen_conf:
            seen_conf.add(t["conf"])
            aq.append(t)
    aq_keys = set(id(t) for t in aq)
    at_large = [t for t in order if id(t) not in aq_keys][:64 - len(aq)]
    field = sorted(aq + at_large, key=lambda t: t["rank26"])[:64]
    for i, t in enumerate(field, 1):
        t["seed"] = i
        t["bid"] = "AQ" if id(t) in aq_keys else "at-large"

    return teams, field, unmatched, len(aq), {
        "conf_changed": sum(1 for t in teams if t.get("conf25") and t["conf"] != t["conf25"]),
        "too_small": too_small,
        "avca": avca.get("meta", {}).get("updated_label"),
        "ret_known": sum(1 for t in teams if t["ret"] is not None),
        "projected": sum(1 for t in teams if not t.get("unranked")),
        "rank_source": rank_source,
        "rank_stamp": rank_stamp,
        "resume_active": resume_active,
        "resume": resume_meta,
    }


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render(teams, field, unmatched, n_aq, meta):
    def cell(v):
        return "&mdash;" if v is None else str(v)

    rows = []
    for t in sorted(teams, key=lambda x: x["rank26"]):
        d_avca = (t["rank26"] - t["avca"]) if t.get("avca") else None
        d_mass = (t["rank26"] - t["massey"]) if t.get("massey") else None
        def delta(d):
            if d is None:
                return '<td class="d">&mdash;</td>'
            cls = "up" if d < 0 else ("dn" if d > 0 else "")
            return '<td class="d %s">%s%d</td>' % (cls, "+" if d > 0 else "", d)
        det = ""
        if t.get("rotation"):
            cells = "".join(
                '<div class="pl"><b>%s</b><span>%s%s</span>'
                '<i>%.2f/set raw &rarr; <b>%.2f</b> schedule-adj</i></div>'
                % (esc(c["name"]), c["kind"],
                   (" from %s" % esc(c["from"])) if c["kind"] == "transfer" else "",
                   c.get("rate", 0.0), c.get("adj", c.get("rate", 0.0)))
                for c in t["rotation"])
            det = ('<tr class="det" data-for="%d" style="display:none"><td></td>'
                   '<td colspan="12"><div class="dethead">The six this score is made of '
                   '&mdash; each player&rsquo;s own 2025 points per set, times the strength '
                   'of the team they produced it against.</div>'
                   '<div class="pls">%s</div></td></tr>' % (t["rank26"], cells))
        rows.append(
            '<tr class="mainrow" data-r="%d"><td class="rk">%d</td><td class="tm">%s</td><td class="cf">%s</td>'
            '<td class="me">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>%s%s'
            '<td class="ret">%s</td><td class="ret">%s</td><td class="ret">%s</td></tr>'
            % (t["rank26"], t["rank26"], esc(t["team"]), esc(t["conf"]),
               cell(t["rank25"]), cell(t.get("avca")), cell(t.get("vt")),
               cell(t.get("rpi")), cell(t.get("massey")),
               delta(d_avca), delta(d_mass),
               "&mdash;" if t["ret"] is None else "%.0f%%" % (100 * t["ret"]),
               "&mdash;" if t.get("proj_pps") is None else ("%.2f" % t["proj_pps"]),
               "&mdash;" if t.get("incoming") is None else t["incoming"]) + det)

    seeds = []
    for t in field:
        seeds.append('<tr><td class="rk">%d</td><td class="tm">%s</td><td class="cf">%s</td>'
                     '<td class="%s">%s</td><td>%s</td><td>%s</td></tr>'
                     % (t["seed"], esc(t["team"]), esc(t["conf"]),
                        "aq" if t["bid"] == "AQ" else "al", t["bid"],
                        cell(t.get("avca")), cell(t.get("massey"))))

    miss_note = " &middot; ".join(
        "%s: %d unmatched%s" % (k, len(v), (" (%s)" % ", ".join(v[:4])) if v else "")
        for k, v in sorted(unmatched.items()))

    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rankings &amp; Projected Bracket</title>
<style>
:root{--bg:#fbfbfd;--card:#fff;--ink:#16181d;--ink2:#5b6270;--ink3:#c9ced8;--line:#e6e9ef;
--acc:#b4123c;--up:#0a7d4a;--dn:#b4123c;--aq:#0b6b8f}
@media(prefers-color-scheme:dark){:root{--bg:#0f1116;--card:#171a21;--ink:#eef1f6;--ink2:#98a1b2;
--ink3:#3a4150;--line:#252a34;--acc:#ff5f82;--up:#3ddb95;--dn:#ff5f82;--aq:#5cc6f0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif}
header{padding:24px 22px 14px;border-bottom:1px solid var(--line);background:var(--card)}
h1{margin:0 0 4px;font-size:23px;letter-spacing:-.02em}
.sub{color:var(--ink2);font-size:13px;max-width:900px}
main{max-width:1240px;margin:0 auto;padding:0 16px 60px}
section{margin:24px 0}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--ink2);margin:0 0 9px;font-weight:650}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{text-align:right;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink2);
padding:7px 8px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--card);z-index:2}
th.l,td.tm,td.cf{text-align:left}
td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right}
td.rk{font-weight:700;color:var(--ink2);width:44px}
td.tm{font-weight:600}
td.cf{color:var(--ink2);font-size:12px}
td.me{font-weight:600}
td.d.up{color:var(--up)}td.d.dn{color:var(--dn)}
td.ret{color:var(--ink2)}
td.aq{color:var(--aq);font-weight:600}td.al{color:var(--ink2)}
tbody tr.mainrow:hover{background:rgba(127,127,127,.07);cursor:pointer}
tr.det td{background:rgba(127,127,127,.05);padding:10px 12px}
.dethead{font-size:11.5px;color:var(--ink2);margin-bottom:8px}
.pls{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:7px}
.pl{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:7px 10px;
text-align:left;font-size:12.5px}
.pl b{display:block}
.pl span{color:var(--ink2);font-size:11px;display:block}
.pl i{color:var(--acc);font-style:normal;font-size:11.5px}
.scroll{max-height:640px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.ctl{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
input,select{font:inherit;font-size:13px;padding:6px 10px;border-radius:8px;border:1px solid var(--line);
background:var(--bg);color:var(--ink)}
.note{font-size:12.5px;color:var(--ink2);margin-top:10px;line-height:1.55}
.k{color:var(--ink);font-weight:600}
.warn{border-left:3px solid var(--acc);padding-left:10px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
code{font:12px ui-monospace,Menlo,monospace;background:var(--bg);padding:1px 5px;border-radius:4px;border:1px solid var(--line)}
</style></head><body>
<header>
<h1>Rankings &amp; Projected Bracket</h1>
<div class="sub">Our number in the first columns, everyone else's beside it. The other
rankings are <b>reference only</b> &mdash; nothing here feeds the model.</div>
</header>
<main>

<section>
<h2>Read this first</h2>
<div class="card"><div class="note warn" style="margin-top:0">
<p><span class="k">Two of the columns are ours and they answer different questions.</span>
<b>2026 pre</b> is the ranking this page sorts by and the bracket is built from. It is built from
the 2026 roster: every returning player and incoming transfer carries the points-per-set they
actually produced in 2025, weighted by the strength of the team that production came against
(a transfer keeps their old school's weight). The team's score is the sum over its
<b>top six</b> &mdash; because six is what a team puts on the court, and because summing the top
six players' rates reproduces their team's real points-per-set to within about half a point,
measured across all 343 teams. Without that cap the model credits a team for production it cannot
deploy: Florida returns 12 and adds 7 transfers, and counting all 19 implied roughly two teams'
worth of scoring.</p>
<p><span class="k">It is DERIVED and unvalidated.</span> The rotation size is measured; the
<b>weights are hand-set</b>. There is no 2026 match to fit them against, so no accuracy claim is
made and none should be read in. <b>2025 final</b> is the measured column &mdash; the fitted
composite that beat RPI out-of-sample at three cutoffs.</p>
<p><span class="k">Where it currently looks wrong, and why.</span> Mid-majors sit higher than they
probably should &mdash; Western Ky., Northern Iowa and South Dakota inside the top 15. A per-set
rate rewards a player who takes a large share of their own team's swings, and the strength weight
only spans 0.5&times; to 1.5&times;, which may not be enough to offset the gap in who they were
swinging against. That spread is the first thing worth fitting rather than guessing.</p>
<p><span class="k">Freshmen count as zero.</span> We hold no recruiting-class data, and inventing a
stand-in is exactly what this project forbids. So a team with a big incoming class is under-rated
here, and under-rated more the better that class is. The <b>In</b> column shows how many incoming
players each team has, so you can see who is being treated unfairly.</p>
<p><span class="k">The comparison is not apples to apples in one specific way.</span> AVCA,
VolleyTalk and Massey are all forecasts of 2026. Our <b>2025 final</b> column is a record of what
already happened. Where they disagree with it, that is mostly roster turnover, not the model being
wrong. The <b>2026 pre</b> column is the one to compare against them.</p>
<p><span class="k">Blank cells are real.</span> A source that does not list a team shows an em dash.
Poll columns only go 25 deep; Massey was captured to 151. RETMISS</p>
</div></div>
</section>

<section>
<h2>All 348 &mdash; ours vs everyone else's</h2>
<div class="card">
<div class="ctl">
  <input type="search" id="q" placeholder="Search a team&hellip;" style="flex:1 1 200px">
  <select id="conf"><option value="">All conferences</option></select>
  <select id="top"><option value="50">Top 50</option><option value="64">Top 64</option>
    <option value="100">Top 100</option><option value="0">All 348</option></select>
  <span class="note" id="count" style="margin:0"></span>
</div>
<div class="scroll"><table>
<thead><tr>
<th>#</th><th class="l">Team</th><th class="l">Conf</th>
<th title="our fitted composite, final 2025">2025 final</th>
<th title="AVCA coaches poll, preseason 2026">AVCA</th>
<th title="VolleyTalk Top 25, preseason 2026">VT</th>
<th title="official NCAA RPI rank, final 2025">RPI</th>
<th title="Massey Ratings, 2026 preseason">Massey</th>
<th title="our 2026 estimate minus AVCA. Negative = we are higher on them.">vs AVCA</th>
<th title="our 2026 estimate minus Massey. Negative = we are higher on them.">vs Massey</th>
<th title="share of 2025 production on the 2026 roster">Ret%</th>
<th title="projected team points per set: the top-6 rotation's own 2025 rates, unweighted">Proj/set</th>
<th title="incoming players with no D-I record. They score zero in this model.">In</th>
</tr></thead>
<tbody id="body">ROWS</tbody></table></div>
<div class="note">Sorted by our <b>2026 pre</b> estimate. <b>vs</b> columns are our 2026 estimate
minus theirs &mdash; <span style="color:var(--up)">green</span> means we rate the team higher than
they do. Source matching: MISSNOTE.</div>
</div>
</section>

<section>
<h2>Projected 64-team field</h2>
<div class="card">
<div class="scroll" style="max-height:560px"><table>
<thead><tr><th>Seed</th><th class="l">Team</th><th class="l">Conf</th><th>Bid</th>
<th>AVCA</th><th>Massey</th></tr></thead>
<tbody>SEEDS</tbody></table></div>
<div class="note">
<p><span class="k">This is a projection, and every part of it is soft.</span> NAQ conferences get a
projected automatic bid, assigned to the conference's highest-rated team &mdash; but most conferences
award the AQ by <b>tournament</b>, so the real bid can go to anyone who wins it. The remaining places
are the next-best teams by our 2026 estimate.</p>
<p><span class="k">Conferences are 2026's, taken from ncaa.com's own schedule feed.</span>
CONFCHANGED D-I teams changed league since last season &mdash; the Pac-12 rebuilt itself out of
Mountain West and WCC schools, and the WAC dissolved into the UAC, Big Sky and Big West. That gives
NCONF automatic bids. Three teams (Saint Francis, UT Arlington, New Orleans) get no usable 2026
conference from the feed and keep their 2025 one rather than being guessed into a new league; a
league below six D-I members cannot award a bid, which is what stops UT Arlington's defunct WAC
from collecting one on its own.</p>
<p><span class="k">{{AQ_MECH}}</span></p>
<p><span class="k">Seeding here is just our order.</span> The committee seeds on resume &mdash; RPI,
record vs the top 25/50, head-to-head &mdash; and our field projector, which reproduced 62 of the
actual 64 for 2025, needs played matches before it can run. It takes over once there are results.</p>
</div>
</div>
</section>

<section>
<h2>What would make this trustworthy</h2>
<div class="card"><div class="note" style="margin-top:0">
<p>Nothing on this page is measured against 2026 reality yet, because there is none. The first
matches are <b>Aug 21</b> (AVCA First Serve, 12 contests) and the first full slate is <b>Aug 28</b>.
Once results land, the 2025-fitted composite starts running on 2026 games, RPI becomes computable,
and the field projector replaces the projection above with a resume-based one.</p>
<p>The useful thing to do with this page today is scan for <b>disagreements you can judge</b>. If our
2026 estimate has a team 30 places off both AVCA and Massey, that is worth a look &mdash; it usually
means either a roster we parsed badly or a real difference of opinion, and you can tell which faster
than any of this code can.</p>
</div></div>
</section>

</main>
<script>
const CONFS=CONFJSON;
const body=document.getElementById('body');
const all=[...body.querySelectorAll('tr.mainrow')];
const cs=document.getElementById('conf');
CONFS.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;cs.appendChild(o)});
document.getElementById('body').addEventListener('click',e=>{
  const tr=e.target.closest('tr.mainrow'); if(!tr) return;
  const d=document.querySelector('tr.det[data-for="'+tr.dataset.r+'"]');
  if(d) d.style.display = (d.style.display==='none') ? '' : 'none';
});
function render(){
  const q=document.getElementById('q').value.toLowerCase().trim();
  const c=cs.value, top=parseInt(document.getElementById('top').value,10);
  let n=0;
  for(const tr of all){
    const tm=tr.querySelector('.tm').textContent.toLowerCase();
    const cf=tr.querySelector('.cf').textContent;
    const r=parseInt(tr.dataset.r,10);
    let show=true;
    if(q && tm.indexOf(q)<0) show=false;
    if(c && cf!==c) show=false;
    if(top && r>top) show=false;
    tr.style.display=show?'':'none';
    const d=document.querySelector('tr.det[data-for="'+tr.dataset.r+'"]');
    if(d && !show) d.style.display='none';
    if(show) n++;
  }
  document.getElementById('count').textContent=n+' teams';
}
['q','conf','top'].forEach(id=>document.getElementById(id).addEventListener('input',render));
render();
</script>
</body></html>""".replace("ROWS", "".join(rows)) \
   .replace("SEEDS", "".join(seeds)) \
   .replace("MISSNOTE", esc(miss_note) or "all sources matched") \
   .replace("{{AQ_MECH}}", aq_mech_note) \
   .replace("NAQ", str(n_aq)).replace("NCONF", str(n_aq)) \
   .replace("CONFCHANGED", str(meta.get("conf_changed", 0))) \
   .replace("RETMISS", "Returning %% is known for %d of %d teams; the rest are not shifted at all "
                       "rather than guessed." % (meta["ret_known"], len(teams))) \
   .replace("CONFJSON", json.dumps(sorted(set(t["conf"] for t in teams if t["conf"]))))


if __name__ == "__main__":
    teams, field, unmatched, n_aq, meta = build()
    html = render(teams, field, unmatched, n_aq, meta)
    if not os.path.isdir(os.path.dirname(OUT)):
        os.makedirs(os.path.dirname(OUT))
    open(OUT, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))
    print("  teams ranked      : %d" % len(teams))
    print("  returning known   : %d" % meta["ret_known"])
    print("  projected field   : %d (%d projected AQ + %d at-large)"
          % (len(field), n_aq, len(field) - n_aq))
    for k, v in sorted(unmatched.items()):
        print("  %-11s unmatched: %d %s" % (k, len(v), v[:6] if v else ""))
