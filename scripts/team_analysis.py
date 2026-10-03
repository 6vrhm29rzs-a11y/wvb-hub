#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Team analysis: the ten-metric story of one team's season (Phase B,
approved by Cody 2026-09-26, PRIVATE build only).

WHAT THIS IS. Descriptive season analysis built from the SAME two inputs the
page's team stats already use -- the per-match box lines (`boxes`, player
rows with team names, swaps applied) and the counted results (`res_cnt`) --
so this panel and every other team number on the page cannot disagree (R4).
Nothing here is a rating input and nothing feeds POWER or a forecast.

RULES, each one paid for elsewhere in this project:
  * Season rates are SUMMED counts over the right denominator, never an
    average of match percentages. The denominator travels with the rate.
  * Per-set rates divide by the MATCH's sets (from the result's set line),
    never the sum of players' sets.
  * Team blocks = solo + 1/2 assist (NCAA convention).
  * Earned points = kills + aces + team blocks. Scoreboard points (from the
    set scores) are a DIFFERENT quantity and are carried separately.
  * A match with no box score is listed as MISSING, never as zero.
  * Data we do not hold (pass grades, set location, block touches, 2026
    rally-by-rally data) is not a field here at all -- the page says
    "not available", it is never rendered as 0.
  * Roster/box position is "listed position", never "attack location".
  * Setter-lineup rows are OBSERVED ASSOCIATION between who started at
    setter and how the team played -- not a setter-quality verdict.

Python 3.9 target.
"""

import json
import os
import re
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the per-match trend carries only what the panel charts (size: the full
# derive() per match for 348 teams was 4.7 MB of page)
SERIES_KEYS = ("earned_pps", "opp_earned_pps", "hit_pct", "opp_hit_pct",
               "kill_pct", "err_pct", "ta_ps", "ace_per_sa", "se_per_sa",
               "rec_err_per_ra", "digs_ps", "bps")

FIELDS = ("k", "e", "ta", "ast", "digs", "bs", "ba", "aces", "se", "sa", "ra", "re")


def _repair(s):
    try:
        import sys
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import nameclean
        return nameclean.repair(s or "")
    except Exception:                                   # noqa: BLE001
        return s or ""


def _nk(s):
    """The shared identity key (nameclean.join_key) -- not a private one."""
    import sys
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import nameclean
    return nameclean.join_key(s)


def _rate(num, den, nd=3):
    """num/den, or None when the denominator is zero/absent -- never 0."""
    try:
        if den is None or float(den) <= 0:
            return None
        return round(float(num) / float(den), nd)
    except (TypeError, ValueError):
        return None


# PAIRED COVERAGE (mail 030). A per-attempt rate must take its numerator and
# denominator from the SAME matches. Box rows turn a missing field into 0, so
# a match whose feed carried aces but no serve attempts would otherwise add to
# the numerator and not the denominator. These pooled fields hold counts only
# from matches where the denominator was actually recorded (team total > 0 --
# no team plays a real match without serving, receiving and attacking).
POOL = ("ace_s", "se_s", "sa_s", "re_r", "ra_r", "n_sa", "n_ra")


def _blank():
    return dict((f, 0.0) for f in FIELDS + POOL)


def _pool(acc, gate=None):
    """Fill pooled fields for ONE team-match. `gate` is the team's own
    match totals (for a player row); default: the row itself."""
    g = gate or acc
    if g["sa"] > 0:
        acc["ace_s"], acc["se_s"], acc["sa_s"], acc["n_sa"] = acc["aces"], acc["se"], acc["sa"], 1.0
    if g["ra"] > 0:
        acc["re_r"], acc["ra_r"], acc["n_ra"] = acc["re"], acc["ra"], 1.0
    return acc


def _other_side(rows, team, opp):
    """The opponent's box rows. By exact name first; failing that, when the
    box holds exactly two teams, the one that is not `team` -- the feed and
    the result record spell some schools differently ("LSU New Orleans" vs
    "New Orleans"), and an exact-name miss made Analysis report "no box
    score" for a match the Overview counted (mail 045)."""
    out = [x for x in rows if x.get("team") == opp]
    if out:
        return out
    names = set(x.get("team") for x in rows)
    if len(names) == 2 and team in names:
        return [x for x in rows if x.get("team") != team]
    return []


def box_complete(own_rows, opp_rows, nsets):
    """A box counts toward per-set rates only if BOTH sides' box covers every
    set of the match. A partial box (the feed dropped a set's lines) would
    otherwise divide one basis by another: Nebraska-Georgia Tech 2026-09-12
    was 4 sets with a 3-set box, which made the Overview (box sets) and this
    tab (match sets) disagree. Measured 2026-09-26: 61 of 4,393 team-boxes."""
    try:
        return (bool(own_rows) and bool(opp_rows) and nsets > 0
                and max(float(x.get("sets") or 0) for x in own_rows) == nsets
                and max(float(x.get("sets") or 0) for x in opp_rows) == nsets)
    except ValueError:
        return False


def _add(acc, row):
    for f in FIELDS + POOL:
        try:
            acc[f] += float(row.get(f) or 0)
        except (TypeError, ValueError):
            pass


def derive(own, opp, sets, board_for=None, board_against=None):
    """The ten metrics (+ components) from summed counts and a set count."""
    blk = own["bs"] + 0.5 * own["ba"]
    oblk = opp["bs"] + 0.5 * opp["ba"]
    earned = own["k"] + own["aces"] + blk
    oearned = opp["k"] + opp["aces"] + oblk
    return {
        "sets": sets,
        # 1-2: earned points both ways, with components
        "earned_pps": _rate(earned, sets, 2),
        "kps": _rate(own["k"], sets, 2), "aps": _rate(own["aces"], sets, 2),
        "bps": _rate(blk, sets, 2),
        "opp_earned_pps": _rate(oearned, sets, 2),
        "opp_kps": _rate(opp["k"], sets, 2), "opp_aps": _rate(opp["aces"], sets, 2),
        "opp_bps": _rate(oblk, sets, 2),
        "board_pps": _rate(board_for, sets, 2) if board_for is not None else None,
        "board_allowed_pps": (_rate(board_against, sets, 2)
                              if board_against is not None else None),
        # 3-5: attack
        "kill_pct": _rate(own["k"], own["ta"]),
        "err_pct": _rate(own["e"], own["ta"]),
        "hit_pct": _rate(own["k"] - own["e"], own["ta"]),
        "ta_ps": _rate(own["ta"], sets, 2),
        "opp_kill_pct": _rate(opp["k"], opp["ta"]),
        "opp_hit_pct": _rate(opp["k"] - opp["e"], opp["ta"]),
        # 6-8: assists, digs, blocks (+ blocks per opponent attempt)
        "ast_ps": _rate(own["ast"], sets, 2),
        "digs_ps": _rate(own["digs"], sets, 2),
        "blk_per_opp_ta": _rate(blk, opp["ta"]),
        # 9-10: serving per ATTEMPT and per set; reception error rate
        "ace_per_sa": _rate(own["ace_s"], own["sa_s"]),
        "se_per_sa": _rate(own["se_s"], own["sa_s"]),
        "se_ps": _rate(own["se"], sets, 2),
        "rec_err_per_ra": _rate(own["re_r"], own["ra_r"]),
        "opp_ace_per_sa": _rate(opp["ace_s"], opp["sa_s"]),
        "serve_cov_matches": own["n_sa"], "recv_cov_matches": own["n_ra"],
        # the raw counts, so every rate can be checked by hand
        "counts": dict((f, own[f]) for f in FIELDS + POOL),
        "opp_counts": dict((f, opp[f]) for f in FIELDS + POOL),
    }


def _setters(starters_by_gid, gid, team):
    """Setters (listed 'S') in this team's set-1 starting six, or None."""
    six = (starters_by_gid.get(gid) or {}).get(team)
    if not six:
        return None
    s = sorted(p["name"] for p in six if (p.get("pos") or "").upper() == "S")
    return s


def load_starters(season, boxes):
    """gid -> team -> set-1 starters, attributed by matching each starter's
    name to that game's OWN box rows (never the feed's team label, R8)."""
    p = os.path.join(REPO, "data", "raw", str(season), "lineups.jsonl")
    out = {}
    if not os.path.exists(p):
        return out
    for line in open(p, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        gid = str(rec.get("game_id"))
        rows = boxes.get(gid) or []
        by_name = {}
        for r in rows:
            by_name.setdefault(_nk(r.get("name")), set()).add(r.get("team"))
        for lu in rec.get("lineups") or []:
            six = []
            teams = set()
            for s in lu.get("starters") or []:
                # the feed double-encodes some names; repair them the way
                # every other displayed name on the page is repaired
                nm = _repair(s.get("name"))
                t = by_name.get(_nk(nm))
                if t and len(t) == 1:
                    teams |= t
                    six.append({"name": nm, "pos": s.get("pos")})
            if len(teams) == 1 and six:
                out.setdefault(gid, {})[teams.pop()] = six
    return out


def analyze(boxes, res_cnt, season, only=None, recent_n=5):
    # type: (Dict, List[Dict], int, Optional[set], int) -> Dict[str, Dict]
    """team -> analysis payload. `only` limits which teams are built."""
    res_by = dict((str(r["gid"]), r) for r in res_cnt if r.get("gid"))
    starters = load_starters(season, boxes)
    teams = {}
    for gid, r in sorted(res_by.items(), key=lambda kv: (kv[1].get("date") or "",
                                                          kv[0])):
        for side, opp_side in (("home", "away"), ("away", "home")):
            team, opp = r.get(side), r.get(opp_side)
            if not team or (only and team not in only):
                continue
            t = teams.setdefault(team, {"matches": [], "missing_box": [],
                                        "own": _blank(), "opp": _blank(),
                                        "sets": 0, "board_for": 0.0,
                                        "board_against": 0.0, "players": {},
                                        "setter_rows": {}})
            sets_pairs = [p for p in (r.get("sets") or []) if len(p) == 2]
            # THE MATCH'S SETS ARE ITS TALLY (mail 036). A frozen/truncated
            # line score (Sacramento St.-Saint Mary's: 2 pairs, 3-1 tally)
            # must not become the denominator; the tally is the one count.
            nsets = (int(r.get("away_sets") or 0)
                     + int(r.get("home_sets") or 0)) or len(sets_pairs)
            mine_sets = (r.get("%s_sets" % side) or 0)
            their_sets = (r.get("%s_sets" % opp_side) or 0)
            won = (mine_sets or 0) > (their_sets or 0)
            rows = boxes.get(gid) or []
            own_rows = [x for x in rows if x.get("team") == team]
            opp_rows = _other_side(rows, team, opp)
            entry = {"gid": gid, "date": r.get("date"), "opp": opp,
                     "site": side, "won": won,
                     "score": "%s-%s" % (mine_sets, their_sets),
                     "sets": nsets or None}
            if not own_rows or not opp_rows or not nsets:
                entry["box"] = False
                entry["box_note"] = "no box score"
                t["missing_box"].append(gid)
                t["matches"].append(entry)
                continue
            if not box_complete(own_rows, opp_rows, nsets):
                entry["box"] = False
                entry["box_note"] = "partial box: covers %d of %d sets" % (
                    int(max(float(x.get("sets") or 0) for x in own_rows)), nsets)
                t.setdefault("partial_box", []).append(gid)
                t["matches"].append(entry)
                continue
            team_only = any(x.get("team_total") for x in own_rows)
            if team_only:
                t["team_total_only"] = t.get("team_total_only", 0) + 1
                entry["box_note"] = ("official team totals only -- the feed "
                                     "served this box without player names")
            own, oppc = _blank(), _blank()
            for x in own_rows:
                _add(own, x)
            for x in opp_rows:
                _add(oppc, x)
            _pool(own)
            _pool(oppc)
            bf = ba_ = None
            # SCOREBOARD COVERAGE IS ITS OWN POPULATION (mail 047): points
            # enter only from a line score covering EVERY set, and they are
            # divided by those matches' sets alone -- a withheld or truncated
            # tape (Louisiana-Memphis) must not add sets without points.
            if sets_pairs and len(sets_pairs) == nsets:
                idx = 0 if side == "away" else 1
                bf = float(sum(p[idx] for p in sets_pairs))
                ba_ = float(sum(p[1 - idx] for p in sets_pairs))
                t["board_for"] += bf
                t["board_against"] += ba_
                t["board_sets"] = t.get("board_sets", 0) + nsets
                t["board_matches"] = t.get("board_matches", 0) + 1
            _add(t["own"], own)
            _add(t["opp"], oppc)
            t["sets"] += nsets
            if not team_only:
                # the named-player population's own team attempts: the only
                # honest denominator for a player's share of attacks
                t["named_ta"] = t.get("named_ta", 0.0) + own["ta"]
            d = derive(own, oppc, nsets, bf, ba_)
            entry.update({"box": True, "m": dict((k, d[k]) for k in SERIES_KEYS)})
            st = None if team_only else _setters(starters, gid, team)
            entry["setters"] = st
            t["matches"].append(entry)
            if st is not None:
                key = " + ".join(st) if st else "(no listed setter)"
                sr = t["setter_rows"].setdefault(key, {"own": _blank(),
                                                       "opp": _blank(),
                                                       "sets": 0, "n": 0, "w": 0})
                _add(sr["own"], own)
                _add(sr["opp"], oppc)
                sr["sets"] += nsets
                sr["n"] += 1
                sr["w"] += 1 if won else 0
            # players -- NAMED rows only; a team-total row is never a player
            for x in own_rows:
                if x.get("team_total") or not x.get("name"):
                    continue
                pk = _nk(x.get("name"))
                pl = t["players"].setdefault(pk, {"name": x.get("name"),
                                                  "pos": x.get("pos") or "",
                                                  "sets": 0.0, "matches": 0,
                                                  "c": _blank()})
                if x.get("pos") and not pl["pos"]:
                    pl["pos"] = x.get("pos")
                pl["sets"] += float(x.get("sets") or 0)
                pl["matches"] += 1
                _prow = _blank()
                _add(_prow, x)
                _pool(_prow, gate=own)
                for f in POOL:
                    pl["c"][f] += _prow[f]
                for f in FIELDS:
                    try:
                        pl["c"][f] += float(x.get(f) or 0)
                    except (TypeError, ValueError):
                        pass

    out = {}
    for team, t in teams.items():
        season_d = derive(t["own"], t["opp"], t["sets"])
        bs_ = t.get("board_sets", 0)
        season_d["board_pps"] = _rate(t["board_for"], bs_, 2) if bs_ else None
        season_d["board_allowed_pps"] = _rate(t["board_against"], bs_, 2) if bs_ else None
        season_d["board_cov_matches"] = t.get("board_matches", 0)
        season_d["board_cov_sets"] = bs_
        boxed = [m for m in t["matches"] if m.get("box")]
        team_ta = t.get("named_ta", 0.0)
        players = []
        for pk, pl in t["players"].items():
            c = pl["c"]
            if not any(c[f] for f in FIELDS):
                continue                  # listed but no recorded action
            # ⚠ INDIVIDUAL block credit is BS + BA per set -- a block assist is
            # a block for each player on it. The half-assist is the TEAM
            # scoring convention (earned points), not a player stat (mail 030).
            blk = c["bs"] + c["ba"]
            players.append({
                "name": pl["name"], "listed_pos": pl["pos"] or None,
                "matches": pl["matches"], "sets": pl["sets"],
                "k": c["k"], "e": c["e"], "ta": c["ta"],
                "ta_share": _rate(c["ta"], team_ta),
                "kill_pct": _rate(c["k"], c["ta"]),
                "hit_pct": _rate(c["k"] - c["e"], c["ta"]),
                "kps": _rate(c["k"], pl["sets"], 2),
                "ast_ps": _rate(c["ast"], pl["sets"], 2),
                "digs_ps": _rate(c["digs"], pl["sets"], 2),
                "bps": _rate(blk, pl["sets"], 2),
                "aces": c["aces"], "se": c["se"],
                "bs": c["bs"], "ba": c["ba"],
                "ace_per_sa": _rate(c["ace_s"], c["sa_s"]),
                "se_per_sa": _rate(c["se_s"], c["sa_s"]),
                "sa": c["sa_s"],
                "ra": c["ra_r"], "re": c["re_r"],
                "rec_err_per_ra": _rate(c["re_r"], c["ra_r"]),
            })
        players.sort(key=lambda p: -(p["ta"] + p["sets"] * 0.01))
        setter_rows = []
        for key, sr in t["setter_rows"].items():
            dd = derive(sr["own"], sr["opp"], sr["sets"])
            setter_rows.append({
                "setters": key, "matches": sr["n"], "won": sr["w"],
                "sets": sr["sets"], "hit_pct": dd["hit_pct"],
                "kill_pct": dd["kill_pct"], "earned_pps": dd["earned_pps"],
                "opp_hit_pct": dd["opp_hit_pct"]})
        setter_rows.sort(key=lambda s: -s["matches"])
        out[team] = {
            "season": season,
            "matches_counted": len(t["matches"]),
            "matches_with_box": len(boxed),
            "missing_box": t["missing_box"],
            "partial_box": t.get("partial_box", []),
            # TEAM vs PLAYER coverage, stated separately (mail 045)
            "team_total_only": t.get("team_total_only", 0),
            "player_matches": len(boxed) - t.get("team_total_only", 0),
            "share_basis": ("share of the team's attacks in the matches with "
                            "named player lines; team-totals-only matches "
                            "carry no per-player split"),
            "totals": season_d,
            "series": t["matches"],
            "players": players,
            "setter_lineups": setter_rows,
            "lineup_matches": sum(1 for m in boxed if m.get("setters") is not None),
        }
    return out


def recent_window(boxes, res_cnt, team, n=5):
    """Exact recent-n totals from counts (last n boxed matches)."""
    res = sorted([r for r in res_cnt if team in (r.get("home"), r.get("away"))],
                 key=lambda r: (r.get("date") or "", str(r.get("gid"))))
    own, opp, sets, used = _blank(), _blank(), 0, 0
    bf, bag = 0.0, 0.0
    team_only_n = 0
    for r in reversed(res):
        if used >= n:
            break
        rows = boxes.get(str(r.get("gid"))) or []
        side_opp = r["away"] if r["home"] == team else r["home"]
        orows = [x for x in rows if x.get("team") == team]
        prows = _other_side(rows, team, side_opp)
        sp = [p for p in (r.get("sets") or []) if len(p) == 2]
        ns = int(r.get("home_sets") or 0) + int(r.get("away_sets") or 0)
        if (not orows or not prows or not sp or len(sp) != ns
                or not box_complete(orows, prows, ns)):
            continue
        if any(x.get("team_total") for x in orows):
            team_only_n += 1
        o1, p1 = _blank(), _blank()
        for x in orows:
            _add(o1, x)
        for x in prows:
            _add(p1, x)
        _add(own, _pool(o1))
        _add(opp, _pool(p1))
        idx = 1 if r["home"] == team else 0
        bf += sum(p[idx] for p in sp)
        bag += sum(p[1 - idx] for p in sp)
        sets += len(sp)
        used += 1
    if not used:
        return None
    d = derive(own, opp, sets, bf, bag)
    d.pop("counts", None)
    d.pop("opp_counts", None)
    d["matches"] = used
    d["team_total_only_matches"] = team_only_n
    return d


def season_inputs(season):
    """(boxes, res) for a COMPLETED season from raw files -- the counted
    chain (season_counts.countable + corrections, player_rating's counted
    playerbox reader with box-team swaps), shaped like build_hub's inputs so
    `analyze` runs unchanged. Used for historical comparisons (A&M 2025)."""
    import sys
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import gamelog
    import season_counts as SC
    import player_rating as PR
    games = gamelog.load_games_jsonl(
        os.path.join(REPO, "data", "raw", str(season), "games.jsonl"))
    corr = SC.corrections(season)
    name_of = {}
    res = []
    for g in SC.countable(games, season):
        g = SC.apply_correction(g, corr)
        ts = g.get("teams") or []
        home = next((t for t in ts if t.get("is_home")), None)
        away = next((t for t in ts if not t.get("is_home")), None)
        if not home or not away:
            continue
        for t in ts:
            name_of[str(t.get("team_id"))] = t.get("name_short")
        ls = [l for l in (g.get("linescores") or [])
              if l.get("home") is not None and l.get("visit") is not None]
        res.append({"gid": str(g.get("game_id")),
                    "date": str(g.get("start_time_epoch") or ""),
                    "home": home.get("name_short"), "away": away.get("name_short"),
                    "home_sets": int(home.get("sets_won") or 0),
                    "away_sets": int(away.get("sets_won") or 0),
                    "sets": [(int(l["visit"]), int(l["home"])) for l in ls]})
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    boxes = {}
    for gid, rows in PR._counted_playerbox(season):
        out = []
        for r in rows:
            out.append({
                "team": name_of.get(str(r.get("team_id")), str(r.get("team_id"))),
                "name": ("%s %s" % (r.get("first") or "", r.get("last") or "")).strip(),
                "pos": r.get("pos") or "", "sets": num(r.get("gp")),
                "k": num(r.get("kills")), "e": num(r.get("errors")),
                "ta": num(r.get("atts")), "aces": num(r.get("aces")),
                "digs": num(r.get("digs")), "bs": num(r.get("bs")),
                "ba": num(r.get("ba")), "ast": num(r.get("assists")),
                "se": num(r.get("serve_errors")), "sa": num(r.get("serve_atts")),
                "ra": num(r.get("recv_atts")), "re": num(r.get("recv_errors"))})
        boxes[gid] = out
    return boxes, res


PLAYER_KEYS = ("name", "listed_pos", "matches", "sets", "k", "e", "ta", "bs", "ba",
               "ta_share", "kill_pct", "hit_pct", "kps", "ast_ps", "digs_ps",
               "bps", "aces", "se", "sa", "ace_per_sa", "se_per_sa", "ra", "re",
               "rec_err_per_ra")
SERIES_FIXED = ("gid", "date", "opp", "site", "won", "score", "sets", "box", "box_note")


def compact(payload):
    """Positional arrays instead of repeated keys for the page payload
    (3.6 MB -> about half). The page decodes with the same key lists, which
    are embedded beside the data so the two cannot drift."""
    out = {}
    for team, a in payload.items():
        ser = []
        for m in a["series"]:
            row = [m.get(k) for k in SERIES_FIXED]
            row.append([m["m"].get(k) for k in SERIES_KEYS] if m.get("m") else None)
            row.append(m.get("setters"))
            ser.append(row)
        out[team] = dict(a, series=ser,
                         players=[[p.get(k) for k in PLAYER_KEYS]
                                  for p in a["players"]])
    return {"keys": {"series": list(SERIES_FIXED) + ["m", "setters"],
                     "m": list(SERIES_KEYS), "players": list(PLAYER_KEYS)},
            "teams": out}
