#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Cody/START-HERE.html -- one page, everything on it.

Supersedes the two-page split (hub + rankings board). Cody reads this on a
desktop and asked not to bounce between files, so scores, rankings, the
projected bracket, the schedule and the TV listings are tabs on one document.

DESIGN NOTE, because it is load-bearing rather than decoration: a volleyball
match is not one score, it is three to five SETS, and how close each set was
carries information a 3-1 throws away. Louisville beating Texas A&M 25-20,
25-23, 20-25, 25-21 is a different match from a comfortable sweep, and the set
strip shows that at a glance. That strip is the one flourish here; everything
else stays a dense, quiet data table.

R5 STILL APPLIES. Missing values render as an em dash. The bracket's team slots
are real projections and say so; nothing is invented to fill a gap.

Python 3.9 target.
"""

import json
import os
import re
import sys
import glob
import datetime
from typing import Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:          # pragma: no cover -- no tz database
    ET = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_rankings_board as BOARD  # noqa: E402

OUT = os.path.join(REPO, "Cody", "START-HERE.html")
SEASON = 2026


def load(p, default=None):
    path = os.path.join(REPO, p)
    return json.load(open(path)) if os.path.exists(path) else default


def _et_date(epoch) -> str:
    """Calendar date in US Eastern -- the timezone the sport schedules in."""
    if ET is not None:
        return datetime.datetime.fromtimestamp(int(epoch), ET).strftime("%Y-%m-%d")
    # fall back to a fixed -4h offset (EDT), correct for the Aug-Oct window
    return (datetime.datetime.utcfromtimestamp(int(epoch))
            - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")


def _et_time(epoch) -> str:
    if ET is None:
        return ""
    return datetime.datetime.fromtimestamp(int(epoch), ET).strftime("%-I:%M %p ET")


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------- results
def results() -> List[Dict]:
    """Every final 2026 match, newest first, with its per-set scores."""
    path = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if not os.path.exists(path):
        return []
    best = {}
    for line in open(path):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        # A record that parses but is not an object is still garbage. An
        # append-only log written by several code paths WILL eventually carry a
        # null line -- one did, and it crashed two builds rather than being
        # skipped like a torn line already is.
        if not isinstance(g, dict) or not g.get("game_id"):
            continue
        gid = str(g.get("game_id"))
        # final beats non-final, then last wins -- the project's dedup rule
        prev = best.get(gid)
        if prev and prev.get("game_state") == "F" and g.get("game_state") != "F":
            continue
        best[gid] = g

    out = []
    for g in best.values():
        if g.get("game_state") != "F":
            continue
        teams = g.get("teams") or []
        if len(teams) != 2:
            continue
        home = next((t for t in teams if t.get("is_home")), None)
        away = next((t for t in teams if not t.get("is_home")), None)
        if not home or not away:
            continue
        sets = []
        for s in g.get("linescores") or []:
            try:
                sets.append((int(s.get("visit")), int(s.get("home"))))
            except (TypeError, ValueError):
                continue
        ep = g.get("start_time_epoch")
        # DATE IN EASTERN, NOT UTC. Kentucky beat Wisconsin at 9pm ET on the
        # 21st, which is 01:00 UTC on the 22nd -- bucketing by UTC filed a
        # Friday-night match under Saturday. Every evening game in the country
        # lands on the wrong day that way, and it is the kind of error a reader
        # spots instantly and a test never would.
        out.append({
            "date": (_et_date(ep) if ep else None),
            "epoch": int(ep) if ep else 0,
            "away": away.get("name_short"), "home": home.get("name_short"),
            "away_sets": away.get("sets_won"), "home_sets": home.get("sets_won"),
            "away_rank": away.get("team_rank"), "home_rank": home.get("team_rank"),
            "away_d1": away.get("division") == 1, "home_d1": home.get("division") == 1,
            "time": _et_time(ep) if ep else "",
            "loc": g.get("location") or None,
            "gid": str(g.get("game_id")),
            "sets": sets,
        })
    out.sort(key=lambda r: -r["epoch"])
    return out


# --------------------------------------------------------------- schedule
def schedule(limit_days: int = 21) -> List[Dict]:
    """Upcoming fixtures from today forward."""
    today = datetime.date.today().isoformat()
    rows = []
    for path in sorted(glob.glob(os.path.join(REPO, "data/raw/%d/scoreboard/*.json" % SEASON))):
        date = os.path.basename(path)[:-5]
        if date < today:
            continue
        try:
            payload = json.load(open(path))
        except ValueError:
            continue
        for entry in payload.get("games") or []:
            g = entry.get("game", entry)
            a = (g.get("away") or {}).get("names", {}).get("short")
            h = (g.get("home") or {}).get("names", {}).get("short")
            if not a or not h:
                continue
            rows.append({
                "d": date, "a": a, "h": h,
                "t": (g.get("startTime") or "").strip(),
                "ar": (g.get("away") or {}).get("rank") or "",
                "hr": (g.get("home") or {}).get("rank") or "",
            })
        if len(set(r["d"] for r in rows)) > limit_days:
            break
    return rows


def tv() -> List[Dict]:
    p = os.path.join(REPO, "Cody", "data", "tv_listings_2026.txt")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or line.count("|") < 3:
            continue
        d, m, n, t = line.split("|", 3)
        out.append({"day": d, "m": m, "n": n, "t": t})
    return out



# ------------------------------------------------------------- team index
def _fixture_pick(pred_by_pair, f, me):
    """This team's own win probability for an upcoming fixture, or None."""
    key = (f["d"], me, f["opp"]) if not f["home"] else (f["d"], f["opp"], me)
    p = pred_by_pair.get(key)
    if not p:
        return None
    return round(p["home_win"] if f["home"] else p["away_win"], 3)


def team_index(teams, res, pred_by_pair, sim_of):
    """Everything about one team in one place: fixtures, results, projection.

    Built as a payload the page renders on demand rather than 348 pre-rendered
    blocks -- the schedule alone is 9,672 team-fixtures, and emitting all of it
    as markup would quadruple the file for content nobody looks at at once.
    """
    played = {}
    for r in res:
        for side, opp, mine, theirs, home in (
                ("away", r["home"], r["away_sets"], r["home_sets"], False),
                ("home", r["away"], r["home_sets"], r["away_sets"], True)):
            played.setdefault(r[side], []).append({
                "d": r["date"], "opp": opp, "home": home,
                "mine": mine, "theirs": theirs,
                # sets are stored (visitor, home). On a team's own page the
                # scores must read from THAT team's side, so the home team's
                # view is the flipped one -- not the away team's. Getting this
                # backwards showed Kentucky winning 3-0 with every set score
                # printed as a loss.
                "sets": ([[h_, a_] for a_, h_ in r["sets"]] if home else
                         [list(x) for x in r["sets"]]),
                "venue": ", ".join(x for x in ((r.get("loc") or {}).get("venue"),
                                               (r.get("loc") or {}).get("city")) if x),
            })

    fixtures = {}
    today = datetime.date.today().isoformat()
    for path in sorted(glob.glob(os.path.join(REPO, "data/raw/%d/scoreboard/*.json" % SEASON))):
        date = os.path.basename(path)[:-5]
        try:
            payload = json.load(open(path))
        except ValueError:
            continue
        for entry in payload.get("games") or []:
            g = entry.get("game", entry)
            a = (g.get("away") or {}).get("names", {}).get("short")
            h = (g.get("home") or {}).get("names", {}).get("short")
            if not a or not h:
                continue
            t = (g.get("startTime") or "").strip()
            fixtures.setdefault(a, []).append(
                {"d": date, "opp": h, "home": False, "t": t})
            fixtures.setdefault(h, []).append(
                {"d": date, "opp": a, "home": True, "t": t})

    proj = {r["team"]: r for r in
            ((load("data/projection_2026.json") or {}).get("teams") or [])}
    # headshot URLs, keyed by team then squashed name. URLS ONLY -- the images
    # are never downloaded or committed; they load from each school's own
    # server, and a player without one shows initials rather than a placeholder
    # pretending to be a photo.
    photos = {}
    for tname, rec in ((load("data/raw/%d/rosters_%d.json" % (SEASON, SEASON)) or {})
                       .get("teams", {}) or {}).items():
        for pl in rec.get("players") or []:
            if pl.get("photo"):
                key = re.sub(r"[^a-z]", "", (pl.get("name_raw") or "").lower())
                photos.setdefault(tname, {})[key] = pl["photo"]
    ret = (load("data/returning_2026.json") or {}).get("teams", {})

    out = {}
    for t in teams:
        nm = t["team"]
        rec = ret.get(nm) or {}
        p = proj.get(nm) or {}
        out[nm] = {
            "conf": t["conf"],
            "rank": t["rank26"],
            "rank25": t["rank25"],
            "avca": t.get("avca"), "vt": t.get("vt"),
            "massey": t.get("massey"), "rpi": t.get("rpi"),
            "record25": ("%s-%s" % (t.get("wins"), t.get("losses"))
                         if t.get("wins") is not None else None),
            "ret": t["ret"],
            "rotation": [dict(c, photo=(photos.get(nm) or {}).get(
                re.sub(r"[^a-z]", "", (c.get("name") or "").lower())))
                for c in (p.get("rotation") or [])],
            "n_ret": len(rec.get("returning") or []),
            "n_dep": len(rec.get("departed") or []),
            "n_new": len(rec.get("new_or_unplayed") or []),
            "n_tin": len(rec.get("transfer_in_official") or []),
            "sim": sim_of.get(nm),
            "top_dep": sorted((rec.get("departed") or []),
                              key=lambda x: -(x.get("pts") or 0))[:3],
            "played": played.get(nm, []),
            "fixtures": [dict(f, pick=_fixture_pick(pred_by_pair, f, nm))
                         for f in fixtures.get(nm, []) if f["d"] >= today][:40],
        }
    return out


# -------------------------------------------------------------- leaders
def leaders():
    """Season leaders from the per-player aggregate, per set.

    PER SET, NOT TOTALS. Totals just rank whoever has played most, which in
    August means whoever opened against a five-set opponent. Rates are
    comparable from the first week.

    The set minimum SCALES with the season: a leaderboard built on one good
    match is noise, so a player must have played a real share of what has been
    possible so far. Early on that admits almost everyone, which is honest --
    the alternative is a table that looks authoritative in week one and is not.
    """
    data = load("data/raw/%d/players_%d.json" % (SEASON, SEASON)) or {}
    rows = data.get("players") or []
    if not rows:
        return [], 0, 0
    ds = load("data/data_2025.json") or {}
    names = {str(t["team_id"]): t["name_short"] for t in ds.get("teams", [])
             if t.get("team_id")}

    max_sets = max((r.get("sets") or 0) for r in rows)
    floor = max(3, int(round(max_sets * 0.5)))

    out = []
    for r in rows:
        sets = r.get("sets") or 0
        if sets < floor:
            continue
        atts = r.get("atts") or 0
        kills = r.get("kills") or 0
        errs = r.get("errors") or 0
        blocks = (r.get("block_solos") or 0) + 0.5 * (r.get("block_assists") or 0)
        pts = kills + (r.get("aces") or 0) + (r.get("block_solos") or 0) \
            + 0.5 * (r.get("block_assists") or 0)
        out.append({
            "name": ("%s %s" % (r.get("first") or "", r.get("last") or "")).strip(),
            "team": names.get(str(r.get("team_id"))) or str(r.get("team_id")),
            "pos": r.get("pos") or "",
            "sets": sets,
            "kps": round(kills / float(sets), 2),
            "pps": round(pts / float(sets), 2),
            "dps": round((r.get("digs") or 0) / float(sets), 2),
            "bps": round(blocks / float(sets), 2),
            "aps": round((r.get("aces") or 0) / float(sets), 2),
            "asps": round((r.get("assists") or 0) / float(sets), 2),
            # hitting % is only meaningful with a real number of swings
            "hit": (round((kills - errs) / float(atts), 3) if atts >= 20 else None),
        })
    out.sort(key=lambda r: -r["pps"])
    return out, floor, len(rows)


# ------------------------------------------------------- box scores & players

def standings(teams, res):
    """Conference tables, built from results as they land.

    Overall and conference records both, because early in a season almost every
    match is non-conference and a conference-only table would be empty for weeks.
    """
    conf_of = {t["team"]: t["conf"] for t in teams}
    rec = {}
    for t in teams:
        rec[t["team"]] = {"team": t["team"], "conf": t["conf"], "w": 0, "l": 0,
                          "cw": 0, "cl": 0, "rank": t["rank26"]}
    for r in res:
        h, a = r["home"], r["away"]
        if h not in rec or a not in rec:
            continue
        hw = (r["home_sets"] or 0) > (r["away_sets"] or 0)
        same = conf_of.get(h) and conf_of.get(h) == conf_of.get(a)
        for nm, won in ((h, hw), (a, not hw)):
            rec[nm]["w" if won else "l"] += 1
            if same:
                rec[nm]["cw" if won else "cl"] += 1
    by = {}
    for v in rec.values():
        if v["conf"]:
            by.setdefault(v["conf"], []).append(v)
    for c in by:
        by[c].sort(key=lambda x: (-(x["cw"] - x["cl"]), -(x["w"] - x["l"]), x["rank"]))
    return by

def box_and_players(res):
    """Per-match box scores, and a per-player season view with a game log.

    Both come from the same per-game rows (playerbox.jsonl), which the pipeline
    has been collecting daily since the season opened but nothing displayed.
    Keyed by game id so a score card can open its own box score, and by player
    so a name can be looked up directly.
    """
    path = os.path.join(REPO, "data/raw/%d/playerbox.jsonl" % SEASON)
    if not os.path.exists(path):
        return {}, []
    team_of = {}
    ds = load("data/data_2025.json") or {}
    for t in ds.get("teams", []):
        if t.get("team_id"):
            team_of[str(t["team_id"])] = t["name_short"]

    date_of = {r["gid"]: r["date"] for r in res}
    opp_of = {}
    for r in res:
        opp_of[(r["gid"], r["home"])] = r["away"]
        opp_of[(r["gid"], r["away"])] = r["home"]

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    boxes = {}
    players = {}
    for line in open(path):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        gid = str(rec.get("game_id"))
        rows = []
        for r in rec.get("rows") or []:
            tid = str(r.get("team_id") or "")
            nm = ("%s %s" % (r.get("first") or "", r.get("last") or "")).strip()
            if not nm:
                continue
            k, e, a = num(r.get("kills")), num(r.get("errors")), num(r.get("atts"))
            bs, ba = num(r.get("bs")), num(r.get("ba"))
            sets = num(r.get("gp"))
            row = {
                "team": team_of.get(tid, tid), "name": nm,
                "pos": r.get("pos") or "", "num": r.get("num"),
                "sets": sets, "k": k, "e": e, "ta": a,
                "hit": round((k - e) / a, 3) if a >= 1 else None,
                "aces": num(r.get("aces")), "digs": num(r.get("digs")),
                "bs": bs, "ba": ba, "ast": num(r.get("assists")),
                "pts": k + num(r.get("aces")) + bs + 0.5 * ba,
            }
            rows.append(row)
            pk = row["team"] + "|" + nm
            p = players.setdefault(pk, {
                "name": nm, "team": row["team"], "pos": row["pos"],
                "num": row["num"], "games": [],
                "sets": 0.0, "k": 0.0, "e": 0.0, "ta": 0.0,
                "aces": 0.0, "digs": 0.0, "bs": 0.0, "ba": 0.0,
                "ast": 0.0, "pts": 0.0,
            })
            for f in ("sets", "k", "e", "ta", "aces", "digs", "bs", "ba", "ast", "pts"):
                p[f] += row[f]
            p["games"].append({
                "d": date_of.get(gid), "gid": gid,
                "opp": opp_of.get((gid, row["team"])),
                "k": k, "e": e, "ta": a, "hit": row["hit"],
                "digs": row["digs"], "bs": bs, "ba": ba,
                "aces": row["aces"], "sets": sets, "pts": row["pts"],
            })
        if rows:
            boxes[gid] = rows

    out = []
    for p in players.values():
        s_ = p["sets"] or 1
        p["games"].sort(key=lambda g: (g["d"] or ""), reverse=True)
        out.append(dict(p,
                        kps=round(p["k"] / s_, 2),
                        pps=round(p["pts"] / s_, 2),
                        dps=round(p["digs"] / s_, 2),
                        hit=(round((p["k"] - p["e"]) / p["ta"], 3)
                             if p["ta"] >= 1 else None)))
    out.sort(key=lambda p: -p["pts"])
    return boxes, out

def build():
    teams, field, unmatched, n_aq, meta = BOARD.build()
    venues = load("data/venues_%d.json" % SEASON) or {}
    site_of = {r["game_id"]: r["site"] for r in venues.get("games", [])}
    event_of = {}
    for e in venues.get("events", []):
        if e.get("name"):
            for gid in e.get("game_ids", []):
                event_of[gid] = e["name"]
    res = results()
    sched = schedule()
    tvrows = tv()
    sim = load("data/season_sim_%d.json" % SEASON) or {}
    sim_of = {r["team"]: r for r in sim.get("teams", [])}
    tourn_of = {r["team"]: r.get("tournament_pct") for r in sim.get("teams", [])}
    preds = load("data/predictions_%d.json" % SEASON) or {}
    pred_by_pair = {}
    for r in preds.get("games", []):
        pred_by_pair[(r["date"], r["away"], r["home"])] = r
    logos = {}
    for t in (load("data/data_2025.json") or {}).get("teams", []):
        if t.get("seoname"):
            logos[t["name_short"]] = (
                "https://www.ncaa.com/sites/default/files/images/logos/schools/"
                "bgl/%s.svg" % t["seoname"])
    boxes, plist = box_and_players(res)
    stand = standings(teams, res)
    tindex = team_index(teams, res, pred_by_pair, sim_of)
    ldrs, ldr_floor, ldr_pool = leaders()
    proj_meta = (load("data/projection_2026.json") or {}).get("meta", {})
    level = load("data/level_effect.json") or {}

    first_played = res[0]["date"] if res else None
    played = len(res)

    # ---- rankings rows ---------------------------------------------------
    rrows = []
    for t in sorted(teams, key=lambda x: x["rank26"]):
        def c(v):
            return "&mdash;" if v is None else str(v)

        # consensus spread: where the other systems put this team
        others = [v for v in (t.get("avca"), t.get("vt"), t.get("massey")) if v]
        spread = ""
        if others:
            lo, hi = min(others), max(others)
            spread = ('<span class="spread" title="others put them %d&ndash;%d">'
                      '%d&ndash;%d</span>' % (lo, hi, lo, hi))
        det = ""
        if t.get("rotation"):
            cells = "".join(
                '<div class="pl"><b>%s</b><span>%s%s</span>'
                '<i>%.2f<em>raw</em> &rarr; %.2f<em>adj</em></i></div>'
                % (esc(c2["name"]), c2["kind"],
                   (" &middot; from %s" % esc(c2["from"])) if c2["kind"] == "transfer" else "",
                   c2.get("rate", 0.0), c2.get("adj", c2.get("rate", 0.0)))
                for c2 in t["rotation"])
            w = t.get("why") or {}
            eff = (w.get("delta_raw") or 0.0) * 0.09
            _f = lambda v: ("%.2f" % v) if v is not None else "&mdash;"
            unknown_txt = ("%d players on the 2026 roster have no D-I record and "
                           "count as zero. " % w["unknown"]) if w.get("unknown") else ""
            why_html = (
                '<div class="why">'
                '<div class="whyline"><span>Last season&rsquo;s rating</span>'
                '<b>' + _f(w.get("prior")) + '</b><i>#'
                + str(w.get("prior_rank") or "?") + '</i></div>'
                '<div class="whyline"><span>Roster change, at the fitted weight '
                '(9% of the prior)</span><b>' + ("%+.2f" % eff) + '</b><i></i></div>'
                '<div class="whyline tot"><span>2026 projection</span>'
                '<b>' + _f(w.get("talent")) + '</b><i>#' + str(t["rank26"]) + '</i></div>'
                '<div class="whynote">This ranking is <b>mostly last season</b>. The '
                'roster is fitted to move a team by about a tenth of its prior, because '
                'that is all it was measured to be worth &mdash; out of sample, adding it '
                'moved accuracy from 0.825 to 0.832. ' + unknown_txt
                + str(w.get("pool") if w.get("pool") is not None else "?")
                + ' of its players have a 2025 line we can use.</div></div>')
            # Built by concatenation, not %-formatting: why_html carries a
            # literal "9%" and mixing the two silently turned that into a
            # format placeholder.
            det = ('<tr class="det" data-for="' + str(t["rank26"]) + '" hidden>'
                   '<td></td><td colspan="10">' + why_html
                   + '<div class="dh">The six this projection is built from '
                     '&mdash; each player&rsquo;s 2025 points per set, then '
                     'normalised to a neutral schedule.</div>'
                     '<div class="pls">' + cells + '</div></td></tr>')
        rrows.append(
            '<tr class="row" data-r="%d"><td class="rk">%d</td>'
            '<td class="tm">%s%s</td><td class="cf">%s</td>'
            '<td class="n hi">%s</td><td class="n">%s</td><td class="n">%s</td>'
            '<td class="n">%s</td><td class="n">%s</td>'
            '<td class="n sp">%s</td><td class="n">%s</td><td class="n hi">%s</td></tr>%s'
            % (t["rank26"], t["rank26"], esc(t["team"]),
               (' <b class="pl6">%s</b>' % t["rot"]) if t.get("rot") and t["rot"] < 6 else "",
               esc(t["conf"]),
               c(t["rank25"]), c(t.get("avca")), c(t.get("vt")),
               c(t.get("massey")), c(t.get("rpi")), spread or "&mdash;",
               "&mdash;" if t["ret"] is None else "%.0f%%" % (100 * t["ret"]),
               "&mdash;" if tourn_of.get(t["team"]) is None
               else "%.0f%%" % tourn_of[t["team"]], det))

    # ---- score cards -----------------------------------------------------
    cards = []
    for r in res:
        strip = ""
        for i, (av, hv) in enumerate(r["sets"], 1):
            aw = av > hv
            strip += ('<div class="set"><span class="%s">%d</span>'
                      '<span class="%s">%d</span></div>'
                      % ("w" if aw else "", av, "" if aw else "w", hv))
        awin = (r["away_sets"] or 0) > (r["home_sets"] or 0)
        rank = lambda v: ('<i class="rnk">%s</i> ' % v) if v else ""
        nond1 = "" if (r["away_d1"] and r["home_d1"]) else \
            ' <span class="tag">non&#8209;D&#8209;I</span>'
        # THE VENUE IS REPORTED, NOT INFERRED. The first version printed
        # "at <home team>", which is a guess dressed as a fact -- and it was
        # wrong on the very first weekend: both AVCA First Serve matches were at
        # Fiserv Forum in Milwaukee, a neutral floor, with Wisconsin and Texas
        # A&M merely listed as home. When ncaa.com gives us no venue we say so
        # rather than filling it in.
        site = site_of.get(r.get("gid"))
        loc = r.get("loc") or {}
        where = ", ".join(x for x in (loc.get("venue"), loc.get("city"),
                                      loc.get("state")) if x)
        venue = esc(where) if where else "venue not reported"
        if site == "neutral":
            venue += ' <span class="tag neutral">neutral site</span>'
        ev = event_of.get(r.get("gid"))
        if ev:
            venue += ' <span class="tag event">%s</span>' % esc(ev)
        cards.append(
            '<div class="card" data-gid="%s"><div class="cd">%s &middot; %s%s</div>'
            '<div class="mt"><div class="side %s">%s%s<b>%s</b></div>'
            '<div class="side %s">%s%s<b>%s</b></div></div>'
            '<div class="sets">%s</div>'
            '<div class="venue">%s</div></div>'
            % (esc(r.get("gid") or ""), esc(r["date"] or ""), esc(r["time"]), nond1,
               "win" if awin else "", rank(r["away_rank"]), esc(r["away"]), r["away_sets"],
               "" if awin else "win", rank(r["home_rank"]), esc(r["home"]), r["home_sets"],
               strip, venue))

    # ---- bracket ---------------------------------------------------------
    seeds = []
    for t in field:
        seeds.append('<tr><td class="rk">%d</td><td class="tm">%s</td>'
                     '<td class="cf">%s</td><td class="n %s">%s</td>'
                     '<td class="n">%s</td></tr>'
                     % (t["seed"], esc(t["team"]), esc(t["conf"]),
                        "aq" if t["bid"] == "AQ" else "al", t["bid"],
                        "&mdash;" if t.get("avca") is None else t["avca"]))

    def _pick(r):
        p = pred_by_pair.get((r["d"], r["a"], r["h"]))
        if not p:
            return "&mdash;", ""
        fav = p["home"] if p["home_win"] >= 0.5 else p["away"]
        pct = max(p["home_win"], p["away_win"])
        # a coin flip is information; dressing 51% as a pick is not
        cls = "toss" if pct < 0.58 else ""
        return "%s <b>%.0f%%</b>" % (esc(fav), 100 * pct), cls

    srows = []
    for r in sched[:600]:
        pick, cls = _pick(r)
        srows.append(
            '<tr><td class="cd">%s</td><td class="n">%s</td><td class="tm">%s%s</td>'
            '<td class="at">at</td><td class="tm">%s%s</td>'
            '<td class="n pick %s">%s</td></tr>'
            % (r["d"], r["t"] or "&mdash;",
               ('<i class="rnk">%s</i> ' % r["ar"]) if r["ar"] else "", esc(r["a"]),
               ('<i class="rnk">%s</i> ' % r["hr"]) if r["hr"] else "", esc(r["h"]),
               cls, pick))
    srows = "".join(srows)

    trows = "".join(
        '<tr><td class="cd">%s</td><td class="tm">%s</td>'
        '<td class="net">%s</td><td class="n">%s</td></tr>'
        % (esc(r["day"]), esc(r["m"]), esc(r["n"]), esc(r["t"]))
        for r in tvrows)

    slope = level.get("recommended_slope")
    return TEMPLATE \
        .replace("{{RANK_ROWS}}", "".join(rrows)) \
        .replace("{{SCORE_CARDS}}", "".join(cards) or
                 '<div class="empty">No completed matches yet.</div>') \
        .replace("{{SEED_ROWS}}", "".join(seeds)) \
        .replace("{{SCHED_ROWS}}", srows) \
        .replace("{{TV_ROWS}}", trows) \
        .replace("{{N_PLAYED}}", str(played)) \
        .replace("{{N_AQ}}", str(n_aq)) \
        .replace("{{N_TEAMS}}", str(len(teams))) \
        .replace("{{N_SCHED}}", "{:,}".format(len(sched))) \
        .replace("{{N_TV}}", str(len(tvrows))) \
        .replace("{{STANDINGS_JSON}}", json.dumps(stand, separators=(",", ":"))) \
        .replace("{{LOGOS_JSON}}", json.dumps(logos, separators=(",", ":"))) \
        .replace("{{BOXES_JSON}}", json.dumps(boxes, separators=(",", ":"))) \
        .replace("{{PLAYERS_JSON}}", json.dumps(plist, separators=(",", ":"))) \
        .replace("{{N_PLAYERS}}", str(len(plist))) \
        .replace("{{LEADERS_JSON}}", json.dumps(ldrs, separators=(",", ":"))) \
        .replace("{{LDR_FLOOR}}", str(ldr_floor)) \
        .replace("{{LDR_POOL}}", str(ldr_pool)) \
        .replace("{{TEAMS_JSON}}", json.dumps(tindex, separators=(",", ":"))) \
        .replace("{{CONF_JSON}}", json.dumps(sorted(set(t["conf"] for t in teams if t["conf"])))) \
        .replace("{{SLOPE}}", ("%.3f" % slope) if slope else "&mdash;") \
        .replace("{{LAST}}", esc(first_played or "not yet")) \
        .replace("{{BUILT}}", datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%MZ"))


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NCAA Women's Volleyball 2026</title>
<style>
/* Legibility first. Cody asked for something that reads like a scores site --
   NCAA, ESPN, a team page -- so this is light, high-contrast and quiet. The
   volleyball identity lives in one place, the per-set strip, rather than in a
   loud palette. Navy for structure, amber for the set a team won, red for live. */
:root{
  --page:#F2F4F7; --card:#FFFFFF; --alt:#F8FAFC;
  --ink:#111827; --ink2:#4B5563; --ink3:#9CA3AF;
  --line:#E2E6EC; --line2:#CBD2DC;
  --navy:#123A6B; --blue:#1D6FD0; --amber:#E8A013; --amber-bg:#FDF3DC;
  --live:#C8322B; --win:#0F7A3D;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);
  font:15px/1.55 var(--sans);font-feature-settings:"tnum" 1}

header{background:var(--navy);color:#fff;padding:20px 24px 0}
.mast{max-width:1280px;margin:0 auto;display:flex;align-items:flex-end;
  justify-content:space-between;gap:20px;flex-wrap:wrap}
h1{margin:0;font-size:27px;letter-spacing:-.02em;font-weight:800;line-height:1;color:#fff}
h1 em{font-style:normal;color:var(--amber)}
.season{font:700 11px/1 var(--mono);color:#9DB6D6;letter-spacing:.2em;
  text-transform:uppercase;margin-bottom:8px}
.meta{font:12px/1.65 var(--mono);color:#B9CBE4;text-align:right}
.meta b{color:#fff}
.net{max-width:1280px;margin:16px auto 0;height:7px;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.32) 0 1px,transparent 1px 7px);
  border-top:2px solid var(--amber)}
nav{background:var(--navy)}
nav .inner{max-width:1280px;margin:0 auto;display:flex;gap:2px;flex-wrap:wrap;padding:0 8px}
nav button{appearance:none;border:0;background:transparent;color:#B9CBE4;
  font:700 12.5px/1 var(--sans);letter-spacing:.05em;padding:13px 16px;cursor:pointer;
  border-bottom:3px solid transparent;text-transform:uppercase}
nav button:hover{color:#fff}
nav button[aria-selected=true]{color:#fff;border-bottom-color:var(--amber)}
nav button:focus-visible{outline:2px solid var(--amber);outline-offset:-3px}

main{max-width:1280px;margin:0 auto;padding:22px 16px 70px}
section[hidden]{display:none}
.lead{color:var(--ink2);font-size:14px;max-width:74ch;margin:0 0 16px}
.lead b{color:var(--ink)}

.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;
  overflow:hidden;box-shadow:0 1px 2px rgba(16,24,40,.05)}
table{width:100%;border-collapse:collapse}
th{font:700 11px/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink2);text-align:right;padding:12px 10px;background:var(--alt);
  border-bottom:2px solid var(--line2);position:sticky;top:0;z-index:2;white-space:nowrap}
th.l{text-align:left}
td{padding:10px;border-bottom:1px solid var(--line);text-align:right;font-size:14px}
tbody tr:nth-child(even of .row){background:var(--alt)}
td.n{font-family:var(--mono);font-size:13.5px}
td.rk{font:700 13px/1 var(--mono);color:var(--ink2);width:48px}
td.tm{text-align:left;font-weight:650;letter-spacing:-.005em}
td.cf{text-align:left;color:var(--ink2);font-size:12.5px}
td.cd{text-align:left;font-family:var(--mono);font-size:12.5px;color:var(--ink2);white-space:nowrap}
td.at{color:var(--ink3);font-size:12px;width:26px;text-align:center}
td.net{text-align:left;font-family:var(--mono);font-size:12.5px;color:var(--navy);font-weight:600}
td.hi{color:var(--navy);font-weight:800}
td.sp .spread{font-family:var(--mono);font-size:11.5px;color:var(--ink2);
  border:1px solid var(--line2);border-radius:4px;padding:2px 6px;background:var(--alt)}
td.aq{color:var(--blue);font-weight:700;font-size:12.5px}
td.al{color:var(--ink2);font-size:12.5px}
tr.row:hover td{background:#EEF4FD;cursor:pointer}
i.rnk{font:800 11px/1 var(--mono);color:var(--amber);font-style:normal;vertical-align:1px}
b.pl6{font:800 10px/1 var(--mono);color:var(--live);vertical-align:2px;margin-left:5px}
.scroll{max-height:72vh;overflow:auto}

/* ---- score cards ---- */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px 13px;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.cd{font:700 11.5px/1 var(--mono);color:var(--ink2);letter-spacing:.06em;
  margin-bottom:11px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.mt{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}
.side{display:flex;align-items:baseline;gap:8px;color:var(--ink2);font-size:16px}
.side b{margin-left:auto;font:700 19px/1 var(--mono);color:var(--ink3)}
.side.win{color:var(--ink);font-weight:750}
.side.win b{color:var(--win)}
/* the signature: each set is a column, visitor above, home below, winner lit */
.sets{display:flex;gap:5px;margin-bottom:10px}
.set{flex:0 1 64px;display:flex;flex-direction:column;border:1px solid var(--line2);
  border-radius:5px;overflow:hidden;min-width:40px}
.set span{font:700 12px/1 var(--mono);padding:5px 0;text-align:center;
  color:var(--ink3);background:var(--alt)}
.set span.w{color:#6B4A00;background:var(--amber-bg)}
.venue{font:12px/1.5 var(--mono);color:var(--ink2)}
.card[data-gid]{cursor:pointer}
.card[data-gid]:hover{border-color:var(--line2);box-shadow:0 2px 6px rgba(16,24,40,.09)}
.empty{padding:30px;text-align:center;color:var(--ink2);font-size:14px}
.tag{font:700 10px/1 var(--mono);color:#7A5A12;background:var(--amber-bg);
  border:1px solid #E7CE96;border-radius:4px;padding:3px 5px;letter-spacing:.05em}
.tag.neutral{color:var(--navy);background:#E8F0FB;border-color:#BFD5F0;margin-left:6px}
td.pick{color:var(--navy)}
td.pick.toss{color:var(--ink2)}
td.pick b{color:var(--navy)}
.tag.event{color:#5B3A00;background:#FBEFD6;border-color:#E3C68C;margin-left:6px}

/* ---- live ---- */
#live{margin-bottom:26px}
.livehead{display:flex;align-items:center;gap:9px;margin-bottom:12px}
.livehead b{font:800 12.5px/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;
  color:var(--live)}
.livehead b.soon{color:var(--navy)}
#today{margin-bottom:26px}
.card.soon:before{content:none}
.card.soon{border-style:dashed}
.card.soon .cd{color:var(--navy)}
.tipoff{font:700 15px/1 var(--mono);color:var(--navy);margin-left:auto}
.livehead #livemeta{font:12px/1 var(--mono);color:var(--ink2);margin-left:auto}
.dot{width:9px;height:9px;border-radius:50%;background:var(--live);
  box-shadow:0 0 0 0 rgba(200,50,43,.6);animation:pulse 2s infinite}
@keyframes pulse{70%{box-shadow:0 0 0 8px rgba(200,50,43,0)}
  100%{box-shadow:0 0 0 0 rgba(200,50,43,0)}}
@media(prefers-reduced-motion:reduce){.dot{animation:none}}
.card.islive{border-color:#EFC3C0;box-shadow:0 1px 3px rgba(200,50,43,.13)}
.card.islive .cd{color:var(--live)}
.set.now{border-color:var(--live)}
.set.now span{background:#FCEDEC;color:var(--live)}

/* ---- rotation detail ---- */
tr.det td{background:var(--alt);padding:13px 15px}
.dh{font-size:12.5px;color:var(--ink2);margin-bottom:10px}
.dlab{font-size:13px;color:var(--ink2)}
.dbtn{font:inherit;font-size:13px;padding:8px 12px;border-radius:8px;
  border:1px solid var(--line2);background:var(--card);color:var(--ink);cursor:pointer}
.dbtn:hover{border-color:var(--navy);color:var(--navy)}
.stgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}
.brk{display:flex;gap:18px;overflow-x:auto;padding-bottom:8px}
.brkcol{flex:none;min-width:210px}
.brkhead{font:700 11px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:9px}
.brkgame{background:var(--card);border:1px solid var(--line);border-radius:8px;
  margin-bottom:8px;overflow:hidden}
.brkside{display:flex;align-items:center;gap:7px;padding:7px 10px;font-size:13px}
.brkside+.brkside{border-top:1px solid var(--line)}
.brkside .sd{font:700 10px/1 var(--mono);color:var(--ink3);width:18px}
.brkside .nmm{flex:1;font-weight:600}
.brkside.fav{background:#F5F9FF}
.brkside .pc{font:700 11.5px/1 var(--mono);color:var(--navy)}
.tlogo{width:20px;height:20px;object-fit:contain;vertical-align:-4px;margin-right:7px}
.tlogo.lg{width:44px;height:44px;vertical-align:-10px;margin-right:12px}
.boxwrap{margin-top:12px;border-top:1px solid var(--line);padding-top:12px}
.boxteam{font:700 11.5px/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink2);margin:10px 0 6px}
table.box{width:100%;border-collapse:collapse;font-size:12.5px}
table.box th{position:static;background:transparent;border-bottom:1px solid var(--line2);
  padding:5px 6px;font-size:10px}
table.box td{padding:5px 6px;border-bottom:1px solid var(--line);font-size:12.5px}
table.box td.pn{text-align:left;font-weight:600}
.pgl{font-size:12.5px}
.why{background:var(--card);border:1px solid var(--line);border-radius:8px;
  padding:12px 14px;margin-bottom:12px;max-width:640px}
.whyline{display:flex;align-items:baseline;gap:10px;font-size:13px;padding:4px 0}
.whyline span{flex:1;color:var(--ink2)}
.whyline b{font:700 14px/1 var(--mono);min-width:66px;text-align:right}
.whyline i{font:700 12px/1 var(--mono);color:var(--ink3);font-style:normal;
  min-width:44px;text-align:right}
.whyline.tot{border-top:1px solid var(--line2);margin-top:4px;padding-top:8px}
.whyline.tot b,.whyline.tot i{color:var(--navy)}
.whynote{font-size:12px;color:var(--ink2);line-height:1.55;margin-top:9px;
  border-top:1px dashed var(--line);padding-top:9px}
.pls{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:8px}
.pl{background:var(--card);border:1px solid var(--line);border-radius:7px;
  padding:8px 11px;text-align:left}
.pl b{display:block;font-size:13.5px}
.pl span{display:block;font-size:11.5px;color:var(--ink2);text-transform:capitalize}
.pl i{font-style:normal;font:700 12px/1.5 var(--mono);color:var(--navy)}
.pl i em{font-style:normal;color:var(--ink3);font-size:10px;margin:0 4px 0 2px}

/* ---- team page ---- */
.thead{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:18px 20px;margin-bottom:14px;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.thead h2{margin:0 0 4px;font-size:26px;letter-spacing:-.02em;font-weight:800}
.thead .sub{color:var(--ink2);font-size:13.5px}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}
.chip{font:700 11.5px/1 var(--mono);border:1px solid var(--line2);border-radius:99px;
  padding:6px 11px;color:var(--ink2);background:var(--alt)}
.chip b{color:var(--navy)}
.chip.ours{background:#EEF4FD;border-color:#BFD5F0;color:var(--navy)}
.tcols{display:grid;grid-template-columns:1.25fr 1fr;gap:14px;align-items:start}
@media(max-width:900px){.tcols{grid-template-columns:1fr}}
.tsec{background:var(--card);border:1px solid var(--line);border-radius:10px;
  overflow:hidden;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.tsec h3{margin:0;padding:12px 15px;font:700 11.5px/1 var(--sans);letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink2);background:var(--alt);
  border-bottom:1px solid var(--line)}
.tsec .body{padding:4px 0}
.gline{display:flex;align-items:center;gap:10px;padding:9px 15px;
  border-bottom:1px solid var(--line);font-size:14px}
.gline:last-child{border-bottom:0}
.gline .dt{font:12px/1 var(--mono);color:var(--ink2);width:78px;flex:none}
.gline .va{color:var(--ink3);font-size:12px;width:16px;flex:none}
.gline .op{flex:1;font-weight:600}
.gline .rs{font:700 13px/1 var(--mono);flex:none}
.gline .rs.w{color:var(--win)}.gline .rs.l{color:var(--live)}
.gline .ss{font:11.5px/1 var(--mono);color:var(--ink2);flex:none}
.plrow{display:flex;align-items:baseline;gap:9px;padding:8px 15px;
  border-bottom:1px solid var(--line);font-size:13.5px}
.plrow:last-child{border-bottom:0}
.plrow .nm{flex:1;font-weight:600}
/* Six per team, so they load eagerly -- lazy loading only left a row of empty
   circles while a 1024px source came down for a 34px avatar. The school's
   imgproxy URLs are signed, so the size cannot be rewritten to something
   smaller without breaking them. */
.mug{width:34px;height:34px;border-radius:50%;object-fit:cover;flex:none;
  background:var(--alt);border:1px solid var(--line)}
img.mug{color:transparent}
.mug--none{display:flex;align-items:center;justify-content:center;
  font:700 11px/1 var(--mono);color:var(--ink3)}
.plrow{align-items:center}
.plrow .kd{font-size:11.5px;color:var(--ink2);text-transform:capitalize}
.plrow .rt{font:700 12.5px/1 var(--mono);color:var(--navy)}
.tnote{font-size:12.5px;color:var(--ink2);padding:11px 15px;background:var(--alt);
  border-top:1px solid var(--line)}

/* ---- controls ---- */
.ctl{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:13px;align-items:center}
input,select{font:inherit;font-size:14px;padding:8px 12px;border-radius:8px;
  border:1px solid var(--line2);background:var(--card);color:var(--ink)}
input[type=search]{flex:1 1 220px}
input:focus-visible,select:focus-visible{outline:2px solid var(--blue);outline-offset:1px}
.count{font:12px/1 var(--mono);color:var(--ink2);margin-left:auto}
.note{font-size:13px;color:var(--ink2);line-height:1.65;padding:14px 16px;
  border-top:1px solid var(--line);background:var(--alt)}
.note b{color:var(--ink)}
.note p{margin:0 0 9px}.note p:last-child{margin:0}
@media(max-width:640px){
  main{padding:16px 10px 50px}h1{font-size:22px}
  td,th{padding:8px 7px}.meta{text-align:left}
}
</style></head><body>

<header>
  <div class="mast">
    <div>
      <div class="season">NCAA Division I &middot; Women&rsquo;s Indoor</div>
      <h1>Volleyball <em>2026</em></h1>
    </div>
    <div class="meta">
      <b>{{N_PLAYED}}</b> matches played &middot; <b>{{N_TEAMS}}</b> teams rated<br>
      last result <b>{{LAST}}</b> &middot; built {{BUILT}}
    </div>
  </div>
  <div class="net"></div>
  </header>
  <nav role="tablist"><div class="inner">
    <button role="tab" aria-selected="true" data-v="scores">Scores</button>
    <button role="tab" aria-selected="false" data-v="rankings">Rankings</button>
    <button role="tab" aria-selected="false" data-v="teams">Teams</button>
    <button role="tab" aria-selected="false" data-v="leaders">Leaders</button>
    <button role="tab" aria-selected="false" data-v="players">Players</button>
    <button role="tab" aria-selected="false" data-v="standings">Standings</button>
    <button role="tab" aria-selected="false" data-v="bracket">Projected bracket</button>
    <button role="tab" aria-selected="false" data-v="schedule">Schedule</button>
    <button role="tab" aria-selected="false" data-v="tv">On TV</button>
  </div></nav>

<main>

<section id="v-scores">
  <div id="live" hidden>
    <div class="livehead">
      <span class="dot"></span><b>Live</b>
      <span id="livemeta"></span>
    </div>
    <div class="cards" id="livecards"></div>
  </div>
  <div id="today" hidden>
    <div class="livehead"><b class="soon">Later today</b><span id="todaymeta"></span></div>
    <div class="cards" id="todaycards"></div>
  </div>
  <div class="ctl">
    <label class="dlab" for="sdate">Jump to a date</label>
    <input type="date" id="sdate" min="2026-08-21" max="2026-12-31">
    <button class="dbtn" id="sclear" type="button">All results</button>
    <span class="count" id="dcnt"></span>
  </div>
  <p class="lead">Every completed match, newest first. The strip under each result is
  the <b>per-set score</b> &mdash; visitor on top, home below, the set winner lit.
  A 25&ndash;23 and a 25&ndash;12 are not the same match.</p>
  <div class="cards">{{SCORE_CARDS}}</div>
</section>

<section id="v-rankings" hidden>
  <p class="lead">Our 2026 projection beside everyone else&rsquo;s. The other columns are
  <b>reference only</b> &mdash; nothing here feeds the model. Click a team to see the six
  players its projection is built from.</p>
  <div class="ctl">
    <input type="search" id="q" placeholder="Search a team&hellip;">
    <select id="conf"><option value="">All conferences</option></select>
    <select id="top">
      <option value="50">Top 50</option><option value="64">Top 64</option>
      <option value="100">Top 100</option><option value="0">All</option>
    </select>
    <span class="count" id="cnt"></span>
  </div>
  <div class="panel"><div class="scroll"><table>
    <thead><tr>
      <th>#</th><th class="l">Team</th><th class="l">Conf</th>
      <th title="our fitted composite, final 2025">2025</th>
      <th title="AVCA coaches poll, preseason">AVCA</th>
      <th title="VolleyTalk Top 25, preseason">VT</th>
      <th title="Massey Ratings, 2026 preseason">Massey</th>
      <th title="official NCAA RPI rank, final 2025">RPI</th>
      <th title="range the other systems put this team in">Others</th>
      <th title="share of 2025 production on the 2026 roster">Ret</th>
      <th title="simulated NCAA tournament odds; backtested at 42 of the real 64 from a preseason prior">Tourn</th>
    </tr></thead>
    <tbody id="rbody">{{RANK_ROWS}}</tbody></table></div>
    <div class="note">
      <p><b>How the projection works.</b> Each returning player and incoming transfer
      carries the points per set she actually produced in 2025, normalised to a neutral
      schedule using a measured level effect ({{SLOPE}} points per set per standard
      deviation of opponent strength, from 20,997 player-matches). A team&rsquo;s six best
      are summed, and the result moves the team off its 2025 rating &mdash; which on its
      own predicts the following season at 0.86, and is too strong to throw away.</p>
      <p><b>What it cannot see, and by how much.</b> Freshmen count as zero, because no
      recruiting data is held and inventing a number is worse than admitting the gap. That
      gap is now measured rather than hand-waved: across 348 teams in 2025, players with no
      prior D-I record supplied a median <b>22%</b> of their team's production, and for some
      teams far more &mdash; Hampton 94%, Vanderbilt 73%. So a team with a large incoming
      class is under-rated here by roughly that much. A red number beside a team name means
      we know fewer than six of its players.</p>
    </div>
  </div>
</section>

<section id="v-teams" hidden>
  <div class="ctl">
    <input type="search" id="tmq" list="tmlist" placeholder="Type a team&hellip;" autocomplete="off">
    <datalist id="tmlist"></datalist>
  </div>
  <div id="teamcard"></div>
</section>

<section id="v-leaders" hidden>
  <p class="lead">Season leaders, <b>per set</b> rather than totals &mdash; totals just rank
  whoever has played most. A player needs {{LDR_FLOOR}} sets to qualify; that minimum rises
  with the season.</p>
  <div class="ctl">
    <input type="search" id="lq" placeholder="Search player or team&hellip;">
    <select id="lstat">
      <option value="pps">Points / set</option>
      <option value="kps">Kills / set</option>
      <option value="hit">Hitting %</option>
      <option value="dps">Digs / set</option>
      <option value="bps">Blocks / set</option>
      <option value="aps">Aces / set</option>
      <option value="asps">Assists / set</option>
    </select>
    <span class="count" id="lcnt"></span>
  </div>
  <div class="panel"><div class="scroll"><table>
    <thead><tr><th>#</th><th class="l">Player</th><th class="l">Team</th><th>Pos</th>
      <th>Sets</th><th id="lhead">Pts/set</th></tr></thead>
    <tbody id="lbody"></tbody></table></div>
    <div class="note">Hitting percentage needs at least 20 swings before it means
    anything, so a player below that shows an em dash rather than a number built on
    four attempts.</div>
  </div>
</section>

<section id="v-standings" hidden>
  <p class="lead">Conference tables, filling in as results land. Conference record first,
  overall beside it &mdash; early in a season nearly every match is non-conference, so the
  conference column stays empty for a while by nature.</p>
  <div class="ctl">
    <select id="stconf"></select>
    <span class="count" id="stcnt"></span>
  </div>
  <div id="standings"></div>
</section>

<section id="v-players" hidden>
  <p class="lead">{{N_PLAYERS}} players with a 2026 line so far. Search a name, or click
  one for her season and every match she has played.</p>
  <div class="ctl">
    <input type="search" id="pq" list="plist" placeholder="Type a player&hellip;" autocomplete="off">
    <datalist id="plist"></datalist>
    <span class="count" id="pcnt"></span>
  </div>
  <div id="playercard"></div>
  <div class="panel" id="ptable"><div class="scroll"><table>
    <thead><tr><th class="l">Player</th><th class="l">Team</th><th>Pos</th>
      <th>Sets</th><th>Kills</th><th>Hit%</th><th>Digs</th><th>Blk</th>
      <th>Pts/set</th></tr></thead>
    <tbody id="pbody"></tbody></table></div></div>
</section>

<section id="v-bracket" hidden>
  <p class="lead">A projected 64-team field: {{N_AQ}} conference champions plus the
  next best at large, ordered by our 2026 projection.</p>
  <div id="brkview"></div>
  <div class="panel"><div class="scroll"><table>
    <thead><tr><th>Seed</th><th class="l">Team</th><th class="l">Conf</th>
      <th>Bid</th><th>AVCA</th></tr></thead>
    <tbody>{{SEED_ROWS}}</tbody></table></div>
    <div class="note">
      <p><b>Every part of this is soft.</b> Conference champions are projected as each
      league&rsquo;s highest-rated team, but most leagues award the bid by tournament, so
      it can go to anyone who wins it. The AQ mechanism is confirmed for only 6 of 32
      conferences.</p>
      <p>Seeding here is our order, not a committee&rsquo;s. The committee seeds on resume
      &mdash; RPI, record against the top 25 and 50, head to head &mdash; and our field
      projector, which reproduced 62 of the actual 64 for 2025, needs played matches
      before it can run. It takes over once there are results.</p>
    </div>
  </div>
</section>

<section id="v-schedule" hidden>
  <p class="lead">{{N_SCHED}} fixtures from today forward, straight from ncaa.com.</p>
  <div class="ctl">
    <input type="search" id="sq" placeholder="Search a team&hellip;">
    <span class="count" id="scnt"></span>
  </div>
  <div class="panel"><div class="scroll"><table>
    <thead><tr><th class="l">Date</th><th>Time</th><th class="l">Visitor</th>
      <th></th><th class="l">Home</th>
      <th title="rally model, calibrated Brier 0.1289 on 2025">Projected</th></tr></thead>
    <tbody id="sbody">{{SCHED_ROWS}}</tbody></table></div></div>
</section>

<section id="v-tv" hidden>
  <p class="lead">{{N_TV}} nationally televised matches, transcribed from VolleyTalk
  &mdash; not verified against the networks.</p>
  <div class="ctl">
    <input type="search" id="tq" placeholder="Search team or network&hellip;">
    <span class="count" id="tcnt"></span>
  </div>
  <div class="panel"><div class="scroll"><table>
    <thead><tr><th class="l">Date</th><th class="l">Matchup</th>
      <th class="l">Network</th><th>Time ET</th></tr></thead>
    <tbody id="tbody">{{TV_ROWS}}</tbody></table></div></div>
</section>

</main>
<script>
const CONFS = {{CONF_JSON}};
const $ = s => document.querySelector(s);

/* tabs */
document.querySelectorAll('nav button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach(x => x.setAttribute('aria-selected', x === b));
  document.querySelectorAll('main section').forEach(s => { s.hidden = true; });
  $('#v-' + b.dataset.v).hidden = false;
}));

/* rankings */
const cs = $('#conf');
CONFS.forEach(c => { const o = document.createElement('option'); o.value = o.textContent = c; cs.appendChild(o); });
const rrows = [...document.querySelectorAll('#rbody tr.row')];
function renderRank() {
  const q = $('#q').value.toLowerCase().trim(), c = cs.value, top = +$('#top').value;
  let n = 0;
  for (const tr of rrows) {
    const nm = tr.querySelector('.tm').textContent.toLowerCase();
    const cf = tr.querySelector('.cf').textContent;
    const r = +tr.dataset.r;
    const show = (!q || nm.includes(q)) && (!c || cf === c) && (!top || r <= top);
    tr.hidden = !show;
    const d = document.querySelector('tr.det[data-for="' + r + '"]');
    if (d && !show) d.hidden = true;
    if (show) n++;
  }
  $('#cnt').textContent = n + ' teams';
}
$('#rbody').addEventListener('click', e => {
  const tr = e.target.closest('tr.row'); if (!tr) return;
  const d = document.querySelector('tr.det[data-for="' + tr.dataset.r + '"]');
  if (d) d.hidden = !d.hidden;
});
['q', 'conf', 'top'].forEach(id => $('#' + id).addEventListener('input', renderRank));
renderRank();

/* simple text filters */
function filter(inputId, bodyId, countId, unit) {
  const rows = [...document.querySelectorAll('#' + bodyId + ' tr')];
  const run = () => {
    const q = $('#' + inputId).value.toLowerCase().trim();
    let n = 0;
    for (const tr of rows) {
      const show = !q || tr.textContent.toLowerCase().includes(q);
      tr.hidden = !show; if (show) n++;
    }
    $('#' + countId).textContent = n + ' ' + unit;
  };
  $('#' + inputId).addEventListener('input', run); run();
}
/* ---- live scoreboard ----------------------------------------------------
   Served by scripts/live_server.py. Opened straight from Finder this fetch
   fails and the band simply never appears -- the completed matches below are
   the page's real content either way, so a missing server degrades to a
   perfectly good static page rather than an error. */
const LIVE_STATES = ['live', 'in progress', 'i'];
function setStrip(sets, live) {
  if (!sets || !sets.length) return '';
  return '<div class="sets">' + sets.map((s, i) => {
    const [av, hv] = s, aw = av > hv;
    const now = live && i === sets.length - 1;
    return '<div class="set' + (now ? ' now' : '') + '">' +
      '<span class="' + (!now && aw ? 'w' : '') + '">' + av + '</span>' +
      '<span class="' + (!now && !aw ? 'w' : '') + '">' + hv + '</span></div>';
  }).join('') + '</div>';
}
function rank(v) { return v ? '<i class="rnk">' + v + '</i> ' : ''; }
async function pollLive() {
  let d;
  try {
    const r = await fetch('/api/live', { cache: 'no-store' });
    if (!r.ok) throw 0;
    d = await r.json();
  } catch (e) { return; }
  const all = d.games || [];
  const live = all.filter(g => LIVE_STATES.includes(g.state));

  /* Tonight's slate, shown as soon as the page loads rather than only once a
     match tips off -- the question "what is on later" is the other half of a
     scoreboard, and the data is already in this response. */
  const todayISO = new Date().toISOString().slice(0, 10);
  const soon = all.filter(g => g.state === 'pre' && g.date >= todayISO)
                  .sort((a, b) => (a.time || '').localeCompare(b.time || ''));
  const tbox = document.getElementById('today');
  if (!soon.length) { tbox.hidden = true; }
  else {
    tbox.hidden = false;
    document.getElementById('todaymeta').textContent = soon.length + ' scheduled';
    document.getElementById('todaycards').innerHTML = soon.map(g =>
      '<div class="card soon"><div class="cd">' + g.date + '</div>' +
      '<div class="mt"><div class="side">' + rank(g.away_rank) + g.away + '</div>' +
      '<div class="side">' + rank(g.home_rank) + g.home + '</div></div>' +
      '<div class="venue"><span class="tipoff">' + (g.time || 'time TBA') + '</span></div>' +
      '</div>').join('');
  }

  const box = document.getElementById('live');
  if (!live.length) { box.hidden = true; return; }
  box.hidden = false;
  document.getElementById('livemeta').textContent =
    (d.error ? d.error + ' \u00b7 ' : '') + 'updated ' + (d.updated || '');
  document.getElementById('livecards').innerHTML = live.map(g => {
    const aw = +g.away_sets > +g.home_sets;
    const venue = g.venue || 'venue not reported';
    return '<div class="card islive"><div class="cd">' +
      (g.period || 'in progress') + '</div>' +
      '<div class="mt"><div class="side' + (aw ? ' win' : '') + '">' +
        rank(g.away_rank) + g.away + '<b>' + g.away_sets + '</b></div>' +
      '<div class="side' + (aw ? '' : ' win') + '">' +
        rank(g.home_rank) + g.home + '<b>' + g.home_sets + '</b></div></div>' +
      setStrip(g.sets, true) +
      '<div class="venue">' + venue + '</div></div>';
  }).join('');
}
pollLive();
setInterval(pollLive, 60000);


/* ---- logos, box scores, player pages ---------------------------------- */
const LOGOS = {{LOGOS_JSON}};
const BOXES = {{BOXES_JSON}};
const PLAYERS = {{PLAYERS_JSON}};

function logo(team, cls) {
  const u = LOGOS[team];
  return u ? '<img class="tlogo ' + (cls || '') + '" src="' + u + '" alt="" ' +
             'onerror="this.style.display=\'none\'">' : '';
}
const n1 = v => (v === null || v === undefined) ? '—' : v;
const pct = v => (v === null || v === undefined) ? '—' : v.toFixed(3);

/* a completed match opens its own box score */
function boxHTML(gid) {
  const rows = BOXES[gid];
  if (!rows || !rows.length) return '<div class="tnote">No box score on file for this match.</div>';
  const byTeam = {};
  rows.forEach(r => (byTeam[r.team] = byTeam[r.team] || []).push(r));
  let out = '<div class="boxwrap">';
  for (const team of Object.keys(byTeam)) {
    const rs = byTeam[team].slice().sort((a, b) => b.pts - a.pts);
    out += '<div class="boxteam">' + logo(team) + team + '</div>' +
      '<table class="box"><thead><tr><th class="l">Player</th><th>Pos</th>' +
      '<th>S</th><th>K</th><th>E</th><th>TA</th><th>Hit%</th><th>Ast</th>' +
      '<th>Digs</th><th>Blk</th><th>Aces</th><th>Pts</th></tr></thead><tbody>' +
      rs.map(r => '<tr><td class="pn">' + r.name + '</td><td>' + (r.pos || '') + '</td>' +
        '<td>' + r.sets + '</td><td>' + r.k + '</td><td>' + r.e + '</td>' +
        '<td>' + r.ta + '</td><td>' + pct(r.hit) + '</td><td>' + r.ast + '</td>' +
        '<td>' + r.digs + '</td><td>' + (r.bs + r.ba * 0.5) + '</td>' +
        '<td>' + r.aces + '</td><td>' + r.pts + '</td></tr>').join('') +
      '</tbody></table>';
  }
  return out + '</div>';
}
document.querySelector('#v-scores').addEventListener('click', e => {
  const card = e.target.closest('.card');
  if (!card || !card.dataset.gid) return;
  let box = card.querySelector('.boxwrap');
  if (box) { box.remove(); return; }
  card.insertAdjacentHTML('beforeend', boxHTML(card.dataset.gid));
});

/* players */
const pdl = document.getElementById('plist');
PLAYERS.forEach(p => { const o = document.createElement('option');
  o.value = p.name + ' · ' + p.team; pdl.appendChild(o); });
function renderPlayers() {
  const q = document.getElementById('pq').value.toLowerCase().split('·')[0].trim();
  const rows = PLAYERS.filter(p => !q || (p.name + ' ' + p.team).toLowerCase().includes(q));
  document.getElementById('pbody').innerHTML = rows.slice(0, 300).map(p =>
    '<tr class="prow" data-k="' + p.team + '|' + p.name + '">' +
    '<td class="tm">' + p.name + '</td><td class="cf">' + logo(p.team) + p.team + '</td>' +
    '<td class="n">' + (p.pos || '') + '</td><td class="n">' + p.sets + '</td>' +
    '<td class="n">' + p.k + '</td><td class="n">' + pct(p.hit) + '</td>' +
    '<td class="n">' + p.digs + '</td><td class="n">' + (p.bs + p.ba * 0.5) + '</td>' +
    '<td class="n hi">' + p.pps.toFixed(2) + '</td></tr>').join('');
  document.getElementById('pcnt').textContent = rows.length + ' players';
  if (rows.length === 1) showPlayer(rows[0]);
}
function showPlayer(p) {
  document.getElementById('playercard').innerHTML =
    '<div class="thead"><h2>' + logo(p.team, 'lg') + p.name + '</h2>' +
    '<div class="sub">' + p.team + (p.pos ? ' · ' + p.pos : '') +
      (p.num ? ' · #' + p.num : '') + '</div>' +
    '<div class="chips">' +
      '<span class="chip ours">Pts/set <b>' + p.pps.toFixed(2) + '</b></span>' +
      '<span class="chip">Kills/set <b>' + p.kps.toFixed(2) + '</b></span>' +
      '<span class="chip">Hit% <b>' + pct(p.hit) + '</b></span>' +
      '<span class="chip">Digs/set <b>' + p.dps.toFixed(2) + '</b></span>' +
      '<span class="chip">Sets <b>' + p.sets + '</b></span>' +
    '</div></div>' +
    '<div class="tsec"><h3>Match log</h3><div class="body">' +
    p.games.map(g => '<div class="gline"><span class="dt">' + (g.d || '') + '</span>' +
      '<span class="op">' + (g.opp || '') + '</span>' +
      '<span class="ss pgl">' + g.k + 'k · ' + g.e + 'e · ' + g.ta + 'ta · ' +
      pct(g.hit) + ' · ' + g.digs + 'd · ' + g.aces + 'a</span>' +
      '<span class="rs">' + g.pts + ' pts</span></div>').join('') +
    '</div></div>';
}
document.getElementById('pbody').addEventListener('click', e => {
  const tr = e.target.closest('.prow'); if (!tr) return;
  const [team, name] = tr.dataset.k.split('|');
  const p = PLAYERS.find(x => x.team === team && x.name === name);
  if (p) { showPlayer(p); document.getElementById('playercard').scrollIntoView({block:'start'}); }
});
document.getElementById('pq').addEventListener('input', renderPlayers);
renderPlayers();


/* ---- standings --------------------------------------------------------- */
const STANDINGS = {{STANDINGS_JSON}};
const stsel = document.getElementById('stconf');
Object.keys(STANDINGS).sort().forEach(c => {
  const o = document.createElement('option'); o.value = o.textContent = c; stsel.appendChild(o);
});
const optAll = document.createElement('option');
optAll.value = ''; optAll.textContent = 'All conferences';
stsel.insertBefore(optAll, stsel.firstChild);
/* Inserting at the front does NOT move selectedIndex -- it stays on what is now
   index 1, so the page opened on whichever conference happened to be first
   alphabetically instead of on all of them. */
stsel.selectedIndex = 0;
function renderStandings() {
  const only = stsel.value;
  const confs = only ? [only] : Object.keys(STANDINGS).sort();
  document.getElementById('standings').innerHTML =
    '<div class="stgrid">' + confs.map(c => {
      const rows = STANDINGS[c];
      return '<div class="tsec"><h3>' + c + '</h3><div class="body">' +
        '<table><thead><tr><th class="l">Team</th><th>Conf</th><th>Overall</th>' +
        '<th>Rk</th></tr></thead><tbody>' +
        rows.map(r => '<tr><td class="tm">' + logo(r.team) + r.team + '</td>' +
          '<td class="n">' + r.cw + '-' + r.cl + '</td>' +
          '<td class="n">' + r.w + '-' + r.l + '</td>' +
          '<td class="n hi">' + r.rank + '</td></tr>').join('') +
        '</tbody></table></div></div>';
    }).join('') + '</div>';
  document.getElementById('stcnt').textContent = confs.length + ' conferences';
}
stsel.addEventListener('change', renderStandings);
renderStandings();

/* ---- date navigation on the scores tab --------------------------------- */
const sdate = document.getElementById('sdate');
function filterByDate() {
  const d = sdate.value;
  let n = 0;
  document.querySelectorAll('#v-scores .cards .card[data-gid]').forEach(c => {
    const txt = (c.querySelector('.cd') || {}).textContent || '';
    const show = !d || txt.indexOf(d) === 0;
    c.style.display = show ? '' : 'none';
    if (show) n++;
  });
  document.getElementById('dcnt').textContent =
    d ? (n + ' on ' + d) : '';
}
sdate.addEventListener('input', filterByDate);
document.getElementById('sclear').addEventListener('click', () => {
  sdate.value = ''; filterByDate();
});

/* ---- the bracket, as rounds rather than a list ------------------------- */
function renderBracket() {
  const host = document.getElementById('brkview');
  if (!host) return;
  const seeds = [...document.querySelectorAll('#v-bracket tbody tr')].map(tr => {
    const c = tr.cells;
    return { seed: +c[0].textContent, team: c[1].textContent.trim(),
             conf: c[2].textContent.trim(), bid: c[3].textContent.trim() };
  });
  if (!seeds.length) return;
  /* The committee seeds 32 and pairs them against unseeded teams. Without a
     published bracket we can only show the shape the seeding implies, so the
     first round is drawn as seed N vs the Nth unseeded team and labelled a
     pairing, not a matchup anyone has announced. */
  const seeded = seeds.slice(0, 32), rest = seeds.slice(32);
  const games = seeded.map((s, i) => [s, rest[rest.length - 1 - i]].filter(Boolean));
  host.innerHTML =
    '<div class="brk"><div class="brkcol"><div class="brkhead">First round &middot; implied pairings</div>' +
    games.map(g => '<div class="brkgame">' + g.map((t, j) =>
      '<div class="brkside' + (j === 0 ? ' fav' : '') + '">' +
      '<span class="sd">' + t.seed + '</span>' + logo(t.team) +
      '<span class="nmm">' + t.team + '</span>' +
      '<span class="pc">' + t.bid + '</span></div>').join('') +
      '</div>').join('') + '</div></div>';
}

/* ---- leaders ---- */
const LEADERS = {{LEADERS_JSON}};
const LSTAT = {pps:'Pts/set',kps:'Kills/set',hit:'Hit %',dps:'Digs/set',
               bps:'Blocks/set',aps:'Aces/set',asps:'Asst/set'};
function renderLeaders() {
  const q = document.getElementById('lq').value.toLowerCase().trim();
  const k = document.getElementById('lstat').value;
  document.getElementById('lhead').textContent = LSTAT[k];
  const rows = LEADERS
    .filter(r => r[k] !== null && r[k] !== undefined)
    .filter(r => !q || (r.name + ' ' + r.team).toLowerCase().includes(q))
    .sort((a, b) => b[k] - a[k]).slice(0, 200);
  document.getElementById('lbody').innerHTML = rows.map((r, i) =>
    '<tr><td class="rk">' + (i + 1) + '</td><td class="tm">' + r.name + '</td>' +
    '<td class="cf">' + r.team + '</td><td class="n">' + (r.pos || '') + '</td>' +
    '<td class="n">' + r.sets + '</td><td class="n hi">' +
    (k === 'hit' ? r.hit.toFixed(3) : r[k].toFixed(2)) + '</td></tr>').join('');
  document.getElementById('lcnt').textContent = rows.length + ' players';
}
['lq','lstat'].forEach(id => document.getElementById(id).addEventListener('input', renderLeaders));
renderLeaders();

/* ---- team page ---- */
const TEAMS = {{TEAMS_JSON}};
const dl = document.getElementById('tmlist');
Object.keys(TEAMS).sort().forEach(n => {
  const o = document.createElement('option'); o.value = n; dl.appendChild(o);
});
function chip(label, val, cls) {
  if (val === null || val === undefined || val === '') return '';
  return '<span class="chip ' + (cls || '') + '">' + label + ' <b>' + val + '</b></span>';
}
function showTeam(name) {
  const t = TEAMS[name];
  const box = document.getElementById('teamcard');
  if (!t) { box.innerHTML = ''; return; }
  const results = (t.played || []).map(g => {
    const won = g.mine > g.theirs;
    const strip = (g.sets || []).map(s => s[0] + '-' + s[1]).join(', ');
    return '<div class="gline"><span class="dt">' + g.d + '</span>' +
      '<span class="va">' + (g.home ? 'vs' : '@') + '</span>' +
      '<span class="op">' + g.opp + '</span>' +
      '<span class="rs ' + (won ? 'w' : 'l') + '">' + (won ? 'W' : 'L') + ' ' +
        g.mine + '-' + g.theirs + '</span>' +
      '<span class="ss">' + strip + '</span></div>';
  }).join('');
  const upcoming = (t.fixtures || []).map(f =>
    '<div class="gline"><span class="dt">' + f.d + '</span>' +
    '<span class="va">' + (f.home ? 'vs' : '@') + '</span>' +
    '<span class="op">' + f.opp + '</span>' +
    '<span class="ss">' + (f.t || '') + '</span>' +
    (f.pick !== null && f.pick !== undefined
      ? '<span class="rs ' + (f.pick >= 0.5 ? 'w' : 'l') + '">' +
        Math.round(f.pick * 100) + '%</span>' : '') +
    '</div>').join('');
  const initials = n => n.split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
  const six = (t.rotation || []).map(c =>
    '<div class="plrow">' +
    (c.photo ? '<img class="mug" src="' + c.photo + '" alt="" ' +
               'onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),' +
               '{className:\'mug mug--none\',textContent:\'' + initials(c.name) + '\'}))">'
             : '<span class="mug mug--none">' + initials(c.name) + '</span>') +
    '<span class="nm">' + c.name + '</span>' +
    '<span class="kd">' + c.kind + (c.kind === 'transfer' && c.from ? ' \u00b7 ' + c.from : '') +
    '</span><span class="rt">' + (c.adj !== undefined ? c.adj : c.rate) + '</span></div>').join('');
  const dep = (t.top_dep || []).map(d =>
    '<div class="plrow"><span class="nm">' + d.name + '</span>' +
    '<span class="kd">departed</span><span class="rt">' + (d.pts || 0) + ' pts</span></div>'
  ).join('');
  box.innerHTML =
    '<div class="thead"><h2>' + name + '</h2>' +
    '<div class="sub">' + (t.conf || '') +
      (t.record25 ? ' \u00b7 ' + t.record25 + ' in 2025' : '') + '</div>' +
    '<div class="chips">' +
      chip('Our 2026', '#' + t.rank, 'ours') + chip('2025', '#' + t.rank25) +
      chip('AVCA', t.avca ? '#' + t.avca : '') + chip('VT', t.vt ? '#' + t.vt : '') +
      chip('Massey', t.massey ? '#' + t.massey : '') +
      chip('RPI', t.rpi ? '#' + t.rpi : '') +
      chip('Returning', t.ret !== null ? Math.round(t.ret * 100) + '%' : '') +
      (t.sim && t.sim.proj_wins_mean !== null
        ? chip('Proj wins', t.sim.proj_wins_mean.toFixed(1) + ' (' +
               t.sim.proj_wins_p10 + '\u2013' + t.sim.proj_wins_p90 + ')') +
          chip('Conf title', t.sim.conf_title_pct + '%') +
          chip('Tournament', t.sim.tournament_pct + '%')
        : '') +
    '</div></div>' +
    '<div class="tcols">' +
      '<div>' +
        (results ? '<div class="tsec"><h3>Results</h3><div class="body">' + results +
                   '</div></div>' : '') +
        '<div class="tsec"' + (results ? ' style="margin-top:14px"' : '') +
          '><h3>Upcoming</h3><div class="body">' +
          (upcoming || '<div class="tnote">No remaining fixtures on file.</div>') +
        '</div></div>' +
      '</div>' +
      '<div>' +
        '<div class="tsec"><h3>Projected six</h3><div class="body">' +
          (six || '<div class="tnote">No roster on file for this team, so it is ranked on its 2025 rating alone.</div>') +
        '</div>' +
        (six ? '<div class="tnote">Points per set, normalised to a neutral schedule.</div>' : '') +
        '</div>' +
        (dep ? '<div class="tsec" style="margin-top:14px"><h3>Biggest losses</h3>' +
               '<div class="body">' + dep + '</div></div>' : '') +
        '<div class="tsec" style="margin-top:14px"><h3>Roster turnover</h3><div class="body">' +
          '<div class="plrow"><span class="nm">Returning</span><span class="rt">' + t.n_ret + '</span></div>' +
          '<div class="plrow"><span class="nm">Departed</span><span class="rt">' + t.n_dep + '</span></div>' +
          '<div class="plrow"><span class="nm">Transfers in</span><span class="rt">' + t.n_tin + '</span></div>' +
          '<div class="plrow"><span class="nm">New / no D-I record</span><span class="rt">' + t.n_new + '</span></div>' +
        '</div></div>' +
      '</div>' +
    '</div>';
}
document.getElementById('tmq').addEventListener('input', e => {
  if (TEAMS[e.target.value]) showTeam(e.target.value);
});
/* clicking a team name in the rankings opens its page */
document.getElementById('rbody').addEventListener('click', e => {
  const cell = e.target.closest('td.tm'); if (!cell) return;
  const nm = cell.textContent.trim().replace(/\s+\d+$/, '');
  if (!TEAMS[nm]) return;
  e.stopPropagation();
  document.querySelector('nav button[data-v="teams"]').click();
  document.getElementById('tmq').value = nm;
  showTeam(nm);
});

renderBracket();
filter('sq', 'sbody', 'scnt', 'fixtures');
filter('tq', 'tbody', 'tcnt', 'matches');
</script>
</body></html>"""


if __name__ == "__main__":
    html = build()
    if not os.path.isdir(os.path.dirname(OUT)):
        os.makedirs(os.path.dirname(OUT))
    open(OUT, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))
