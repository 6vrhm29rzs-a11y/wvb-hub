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

import collections
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
# The team-name normaliser + alias map that reconcile already owns. Reused
# rather than re-implemented so the two cannot drift apart.
from reconcile_2025 import norm as team_norm  # noqa: E402

# PUBLIC BUILD. Same page, same code, minus every input that is somebody
# else's property. This repo is PUBLIC, so the public build carries only
# official NCAA feeds, the schools' own rosters and our own model:
#   * the TV listings are transcribed from VolleyTalk       -> dropped
#   * the VolleyTalk Top 25 is their poll                    -> dropped
#   * Massey Ratings are their product, hand-transcribed     -> dropped
# Venue/event names stay: data/venues_2026.json is already a tracked file.
# One builder, two outputs -- so the private and public pages cannot drift
# into two different UIs, which is what made the old dashboard feel like a
# different product.
PUBLIC = "--public" in sys.argv
OUT = (os.path.join(REPO, "output", "vb_dashboard.html") if PUBLIC
       else os.path.join(REPO, "Cody", "START-HERE.html"))
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
# Programs whose local clock is far enough behind Eastern that a midnight-to-6am
# ET tip is an ordinary evening match at home. Hawaii (UTC-10) is the only D-I
# women's volleyball program this applies to: 1:00 AM ET is 7:00 PM in Honolulu.
FAR_WEST_HOME = ("Hawaii",)

_EARLY_AM = re.compile(r"^(12|[1-5]):\d\d\s*AM", re.I)


def listed_time(start_time, home_team):
    """The feed's start time, or "TBA" when that time is a placeholder.

    ncaa.com fills an unannounced start with a midnight-ish sentinel that
    renders as 12:00-3:00 AM ET. Measured 2026-08-22:

      * In the COMPLETED 2025 season only 13 of 5,133 fixtures carried an
        early-AM time, and ALL THIRTEEN were at Hawaii -- 1:00 AM ET is 7:00 PM
        HST, a normal evening start in Honolulu.
      * In the 2026 schedule 192 do: 16 at Hawaii, and 176 at schools like
        Nebraska, Alabama and Wisconsin, which do not host at 1 AM. Those are
        placeholders, replaced with a real time as the date approaches.

    Printing the sentinel as an announced start is R5 -- a synthesised value
    standing where a measurement belongs, and it looks authoritative because it
    is formatted exactly like a real time. "TBA" is the feed's OWN
    representation for an unknown start (83 fixtures carry it), so an unknown
    time renders the way the page already renders unknown times.
    """
    st = (start_time or "").strip()
    if not st:
        return st
    if _EARLY_AM.match(st) and (home_team or "") not in FAR_WEST_HOME:
        return "TBA"
    return st


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
                "t": listed_time(g.get("startTime"), h),
                "ar": (g.get("away") or {}).get("rank") or "",
                "hr": (g.get("home") or {}).get("rank") or "",
            })
        if len(set(r["d"] for r in rows)) > limit_days:
            break
    return rows


def tv() -> List[Dict]:
    if PUBLIC:
        return []
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



# Position buckets, in the order a volleyball person reads a roster: the setter
# first, then the players who attack, then the back-row specialists.
POS_ORDER = ("S", "OPP", "OH", "MB", "L/DS", "")
POS_LABEL = {"S": "Setters", "OPP": "Opposites", "OH": "Outside hitters",
             "MB": "Middle blockers", "L/DS": "Libero / defensive specialists",
             "": "Position not listed"}


def mover(t):
    """Movement since the LAST WEEKLY FREEZE, the way a poll shows it.

    Blank when there is no earlier snapshot to compare against -- a first week
    has no movement, and inventing a dash that looks like "unchanged" would be
    a claim we cannot support.
    """
    mv = t.get("move")
    if mv is None:
        return ""
    if mv > 0:
        return '<span class="mv up">&#9650;%d</span>' % mv
    if mv < 0:
        return '<span class="mv dn">&#9660;%d</span>' % abs(mv)
    return '<span class="mv sm">&ndash;</span>'


def pos_bucket(p):
    """School sites and box scores spell positions a dozen ways. Anything we do
    not recognise falls into "" and is LABELLED as unlisted -- never guessed
    into a slot, because a player shown at the wrong position reads as fact."""
    p = (p or "").upper().strip()
    if not p:
        return ""
    if p.startswith("OPP") or p.startswith("RS"):
        return "OPP"
    if p.startswith("OH"):
        return "OH"
    if p.startswith("MB") or p.startswith("M"):
        return "MB"
    if p.startswith("L") or p.startswith("DS"):
        return "L/DS"
    if p.startswith("S"):
        return "S"
    return ""


def nkey(name):
    return re.sub(r"[^a-z]", "", (name or "").lower())


def prior_pos_index():
    """(team_id, name) -> position from last season's box scores.

    Exists for TRANSFERS. A transfer has no 2025 line at her new school, so the
    roster showed her with no position -- but she played D-I somewhere, and the
    join already records which team_id she came from. Anchoring the lookup on
    that team_id (not on the name alone) keeps it precise: 573 of 574 transfers
    resolve, and a bare-name lookup across 6,017 players would invite exactly
    the wrong-person match R8 exists to prevent."""
    idx = {}
    for r in ((load("data/raw/2025/players_2025.json") or {}).get("players") or []):
        nm = ((r.get("first") or "") + " " + (r.get("last") or "")).strip()
        if not nm:
            continue
        sets = r.get("sets") or 0
        # Production from RAW COUNTS. The feed's own `points` column is unusable
        # as a season total -- it is carried for only some games, so the sum
        # undercuts by a different amount per player (measured: below the raw
        # formula for 3,270 of 4,601 players, median ratio 0.61).
        pts = ((r.get("kills") or 0) + (r.get("aces") or 0)
               + (r.get("block_solos") or 0) + 0.5 * (r.get("block_assists") or 0))
        idx.setdefault((str(r.get("team_id")), nkey(nm)),
                       {"pos": r.get("pos"), "sets": sets, "pts": pts})
    return idx


def roster_rows(roster_rec, ret_rec, lu_rec, live_by_team, team_id,
                prior_pos=None, site_pos=None, id2name=None):
    """The full 2026 roster, each player carrying what we actually know.

    Sources, and what each may and may not say:
      * the school's own roster page  -> who is on the team, class year (OFFICIAL)
      * 2025 box scores               -> position and production (OFFICIAL)
      * 2025 set-1 play-by-play       -> how many matches they started
      * 2026 box scores               -> live production, empty early in the year

    A player with no D-I record -- a true freshman, a JUCO or international
    arrival -- carries NO stats and renders as an em dash. That is the whole
    point: 22% of a season's production comes from players like her, and
    inventing a number for them is exactly what R5 forbids.
    """
    if not roster_rec:
        return []
    ret_rec = ret_rec or {}

    prod = {}
    for pl in (ret_rec.get("returning") or []):
        prod[nkey(pl.get("name"))] = pl
    # Transfers carry last season's production under DIFFERENT field names and
    # with no set count, because it was earned at another school. Normalised
    # here rather than at the render site, and the previous school is kept so
    # the page can say where the number came from.
    transfers = {}
    for pl in (ret_rec.get("transfer_in_official") or []):
        if not isinstance(pl, dict):
            continue
        # Her full line at the school she came from: position, sets AND
        # production, so a transfer shows a real rate instead of an em dash.
        prev = (prior_pos or {}).get(
            (str(pl.get("from_team_id")), nkey(pl.get("name")))) or {}
        transfers[nkey(pl.get("name"))] = {
            "class": pl.get("class"),
            "pts": prev.get("pts") if prev.get("sets") else None,
            "kills": pl.get("kills_2025"),
            "sets": prev.get("sets") or None,
            "from_team_id": pl.get("from_team_id"),
            "from_team": (id2name or {}).get(str(pl.get("from_team_id"))),
            "pos": prev.get("pos"),
        }

    def _one_name(x):
        """These lists are not uniformly shaped: new_or_unplayed holds plain
        strings, unresolved holds [name, reason] pairs, transfer_in_official
        holds dicts. Reading them as one type is how this crashed."""
        if isinstance(x, str):
            return x
        if isinstance(x, (list, tuple)):
            return x[0] if x else ""
        if isinstance(x, dict):
            return x.get("name") or ""
        return ""

    def _names(key):
        return set(nkey(_one_name(x)) for x in (ret_rec.get(key) or []))

    new_names = _names("new_or_unplayed")
    unres_names = _names("unresolved")
    tin_names = _names("transfer_in_official")

    starts = dict((nkey(k), v) for k, v in
                  ((lu_rec or {}).get("starts_by_player_2025") or {}).items())

    live = {}
    for r in (live_by_team.get(str(team_id)) or []):
        live[nkey((r.get("first") or "") + (r.get("last") or ""))] = r

    rows = []
    for pl in (roster_rec.get("players") or []):
        name = pl.get("name_raw") or ((pl.get("first") or "") + " " + (pl.get("last") or "")).strip()
        k = nkey(name)
        p25 = prod.get(k) or transfers.get(k)
        lv = live.get(k)

        if k in tin_names:
            kind = "transfer"
        elif p25:
            kind = "returning"
        elif k in new_names:
            kind = "new"
        elif k in unres_names:
            kind = "unresolved"
        else:
            kind = "new"

        sets25 = (p25 or {}).get("sets")
        pts25 = (p25 or {}).get("pts")
        # Position, best source first. The school's own listing wins; a second
        # pass over the roster page fills some of the gap (most templates render
        # the roster in JavaScript, so this is a real ceiling, not a bug); then
        # last season's box score; then, for a transfer, her previous school.
        pos_raw = (pl.get("pos_raw")
                   or (site_pos or {}).get(name)
                   or (p25 or {}).get("pos"))
        if isinstance(pos_raw, dict):
            pos_raw = pos_raw.get("pos")
        row = {
            "n": name,
            "c": pl.get("class_raw") or (p25 or {}).get("class") or None,
            # position: the school's own listing wins, box score fills the gap
            "p": pos_bucket(pos_raw),
            "praw": pos_raw or None,
            "num": pl.get("num_raw"),
            "k": kind,
            "from": (p25 or {}).get("from_team") if kind == "transfer" else None,
            "st": starts.get(k) or 0,
            "sets": sets25,
            "kills": (p25 or {}).get("kills"),
            # points per set, the same quantity the projection uses
            "r": (round(pts25 / sets25, 2) if (pts25 is not None and sets25) else None),
        }
        if lv and lv.get("sets"):
            row["l26"] = {"m": lv.get("matches"), "sets": lv.get("sets"),
                          "kills": lv.get("kills"), "pos": lv.get("pos"),
                          "num": lv.get("num")}
            if not row["praw"] and lv.get("pos"):
                row["p"] = pos_bucket(lv.get("pos"))
                row["praw"] = lv.get("pos")
            if row["num"] is None:
                # Only from THIS season's box score. Do NOT backfill a jersey
                # number from 2025: players change numbers between seasons, and
                # roster number vs box-score number are already known to be
                # different fields -- on the 6 surname-anchored joins where both
                # were known they agreed 0 times. A wrong number looks right.
                row["num"] = lv.get("num")
        rows.append(row)

    order = dict((p, i) for i, p in enumerate(POS_ORDER))
    rows.sort(key=lambda r: (order.get(r["p"], 99), -(r["st"] or 0),
                             -(r["r"] or 0), r["n"]))
    return rows


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
            t = listed_time(g.get("startTime"), h)
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
    # Photos the roster crawl could not see, from schema.org image URLs on
    # JS-rendered roster pages (scripts/crawl_roster_photos.py). URLS ONLY --
    # the files are never downloaded or committed; a player without one renders
    # her initials, never a stand-in image.
    for _tname, _rec in ((load("data/raw/%d/roster_photos_%d.json" % (SEASON, SEASON))
                          or {}).get("teams", {}) or {}).items():
        for _nm, _url in (_rec.get("photos") or {}).items():
            photos.setdefault(_tname, {}).setdefault(
                re.sub(r"[^a-z]", "", (_nm or "").lower()), _url)

    ret = (load("data/returning_2026.json") or {}).get("teams", {})
    # Who a team ACTUALLY started in 2025 (set-1 play-by-play). Distinct from
    # "rotation" above, which is the six highest projected SCORERS -- different
    # question, different answer. Keeping both under one name is the R4 trap.
    lineup = (load("data/lineups_2026.json") or {}).get("teams", {})
    rosters = ((load("data/raw/%d/rosters_%d.json" % (SEASON, SEASON)) or {})
               .get("teams", {}) or {})
    # ncaa.com spells the same school differently across endpoints, and one key
    # carries a trailing space: the hub calls it "New Orleans", the roster file
    # says "LSU New Orleans ". A missed lookup renders as "no roster", which
    # looks like a crawl failure rather than a naming mismatch -- exactly the
    # trap CLAUDE.md flags about joining on team NAMES.
    roster_by_norm = {}
    for _k, _v in rosters.items():
        roster_by_norm.setdefault(team_norm(_k), _k)
    # Rosters the main crawl could not find, recovered by reading the school's
    # own home page for its roster URL (scripts/recover_missing_rosters.py).
    # Additive: only fills teams that came back empty.
    for _t, _r in ((load("data/raw/%d/rosters_recovered_%d.json" % (SEASON, SEASON))
                    or {}).get("teams", {}) or {}).items():
        if _r.get("players") and not ((rosters.get(_t) or {}).get("players")):
            rosters.setdefault(_t, {}).update(
                {"players": _r["players"], "url": _r.get("url"),
                 "status": "recovered"})
    # 2026 per-player lines as they accumulate. Empty in the opening days, which
    # is why 2025 stays the baseline and 2026 is shown as an addition to it
    # rather than a replacement -- three matches is not a season.
    prior_pos = prior_pos_index()
    # team_id -> name, so a transfer can say which school she came from rather
    # than just "transfer in".
    id2name = {}
    for _t in ((load("data/data_2025.json") or {}).get("teams") or []):
        id2name[str(_t.get("team_id"))] = _t.get("name_short") or _t.get("name_full")

    # Where a departed player WENT. "Departed" lumps a graduating senior in with
    # a transfer out, and those mean very different things for a team. Every
    # official transfer record names the school she came FROM, so inverting that
    # map says which of a team's losses walked to another D-I programme.
    # Anchored on (from_team_id, name), never the name alone -- a bare-name
    # lookup across the whole country is the wrong-person match R8 exists for.
    transferred_out = {}
    for _dest, _rec in ret.items():
        for _p in (_rec.get("transfer_in_official") or []):
            if not isinstance(_p, dict):
                continue
            transferred_out[(str(_p.get("from_team_id")), nkey(_p.get("name")))] = _dest
    # Second-pass roster positions (scripts/crawl_roster_positions.py). Additive:
    # absent file simply means no extra positions.
    site_pos_all = ((load("data/raw/%d/roster_positions_%d.json" % (SEASON, SEASON))
                     or {}).get("teams", {}) or {})
    live_by_team = collections.defaultdict(list)
    for r in ((load("data/raw/%d/players_%d.json" % (SEASON, SEASON)) or {})
              .get("players") or []):
        live_by_team[str(r.get("team_id"))].append(r)

    out = {}
    for t in teams:
        nm = t["team"]
        rec = ret.get(nm) or {}
        p = proj.get(nm) or {}
        _rk = nm if nm in rosters else roster_by_norm.get(team_norm(nm))
        roster = roster_rows(rosters.get(_rk), rec, lineup.get(nm), live_by_team,
                             (lineup.get(nm) or {}).get("team_id"), prior_pos,
                             (site_pos_all.get(nm) or {}).get("positions"), id2name)
        # Position for the projected six, reused from the roster we just built.
        # Showing it is a CLARITY fix: this list ranks by scoring, so it can
        # come out as four outsides and no setter -- which makes plain, at a
        # glance, that it is not a starting lineup (R4: the name and the meaning
        # must not drift apart).
        rpos = dict((nkey(r["n"]), r.get("praw")) for r in roster)
        out[nm] = {
            "conf": t["conf"],
            "rank": t["rank26"],
            "rank25": t["rank25"],
            "avca": t.get("avca"), "vt": t.get("vt"),
            "massey": t.get("massey"), "rpi": t.get("rpi"),
            "record25": ("%s-%s" % (t.get("wins"), t.get("losses"))
                         if t.get("wins") is not None else None),
            "ret": t["ret"],
            "rotation": [dict(c, pos=rpos.get(nkey(c.get("name"))),
                              photo=(photos.get(nm) or {}).get(
                                  re.sub(r"[^a-z]", "", (c.get("name") or "").lower())))
                         for c in (p.get("rotation") or [])],
            "n_ret": len(rec.get("returning") or []),
            "n_dep": len(rec.get("departed") or []),
            "n_new": len(rec.get("new_or_unplayed") or []),
            "n_tin": len(rec.get("transfer_in_official") or []),
            "lineup": lineup.get(nm),
            "roster": roster,
            "sim": sim_of.get(nm),
            "top_dep": [
                dict(d, to=transferred_out.get(
                    (str((lineup.get(nm) or {}).get("team_id")), nkey(d.get("name")))))
                for d in sorted((rec.get("departed") or []),
                                key=lambda x: -(x.get("pts") or 0))[:3]],
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
    if PUBLIC:
        # STRIP THE VALUES, NOT JUST THE COLUMNS. Removing the VT and Massey
        # <th>/<td> only hid them: their actual ranks still shipped inside the
        # TEAMS payload -- 25 VolleyTalk and 151 Massey rows, readable in
        # devtools on a public page. Hiding third-party data is not the same as
        # not publishing it. Dropped here, at the single point they enter the
        # build, so no downstream consumer can reintroduce them.
        for _t in teams:
            _t["vt"] = None
            _t["massey"] = None
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
            '<tr class="row" data-r="%d"><td class="rk">%d%s</td>'
            '<td class="tm">%s%s</td><td class="cf">%s</td>'
            '<td class="n hi">%s</td><td class="n">%s</td>%s'
            '<td class="n">%s</td>%s<td class="n">%s</td><td class="n hi">%s</td></tr>%s'
            % (t["rank26"], t["rank26"], mover(t), esc(t["team"]),
               (' <b class="pl6">%s</b>' % t["rot"]) if t.get("rot") and t["rot"] < 6 else "",
               esc(t["conf"]),
               c(t["rank25"]), c(t.get("avca")),
               "" if PUBLIC else ('<td class="n">%s</td><td class="n">%s</td>'
                                  % (c(t.get("vt")), c(t.get("massey")))),
               c(t.get("rpi")),
               "" if PUBLIC else ('<td class="n sp">%s</td>' % (spread or "&mdash;")),
               "&mdash;" if t["ret"] is None else "%.0f%%" % (100 * t["ret"]),
               "&mdash;" if tourn_of.get(t["team"]) is None
               else "%.0f%%" % tourn_of[t["team"]], det))

    # State plainly WHICH ranking this is. A preseason projection and a
    # results-based rating are different claims, and a tab labelled "Rankings"
    # is read as the second one -- so if we are still showing the first, the
    # page has to say so rather than let the heading imply otherwise.
    _live = [t for t in teams if t.get("rank_source") == "live"]
    if _live:
        _gp = [t.get("gp") or 0 for t in _live]
        rank_basis = (
            "<b>Our ranking, from 2026 results.</b> %d teams rated on matches "
            "played this season (median %d each), using the same fitted "
            "composite that beat RPI out of sample in 2025. Updated every "
            "morning; frozen every Monday so the movement column has something "
            "to measure against."
            % (len(_live), sorted(_gp)[len(_gp) // 2]))
    else:
        rank_basis = (
            "<b>Still the preseason projection &mdash; not yet a result-based "
            "ranking.</b> It is 2026 rosters &times; 2025 production and reads "
            "<b>no</b> 2026 result, so it does not move when a team wins or "
            "loses. The live rating takes over automatically once 50 matches "
            "have been played; under that there is not enough of a schedule "
            "graph to rate anyone honestly.")

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
        .replace("{{RANK_BASIS}}", rank_basis) \
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
nav{background:var(--navy);position:sticky;top:0;z-index:6}
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
  border-bottom:2px solid var(--line2);position:sticky;top:var(--navh,0px);
  z-index:2;white-space:nowrap}
/* A header inside its OWN scroll box sticks to that box, not to the page, so
   the nav offset does not apply -- adding it pushed the header 42px DOWN, on
   top of row 1, and the #1 team vanished behind it ("Nebraska fell off the
   rankings"). Only page-level sticky headers need to clear the nav. */
.scroll th{top:0}
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

/* ---- full roster ---- */
.tsec--wide{margin-top:14px}
/* 5-1 / 6-2: how many setters the team actually starts. Shown only when its
   lineups agree; a team with thin position data gets no badge, not a guess. */
.wentto{display:block;font:600 10.5px/1 var(--sans);color:var(--ink3);margin-top:3px}
.tabhint{margin:0 0 12px;font-size:12.5px;color:var(--ink2)}
.mv{display:inline-block;margin-left:5px;font:700 9.5px/1 var(--mono);vertical-align:1px}
.mv.up{color:#12864B}
.mv.dn{color:#B3261E}
.mv.sm{color:var(--ink3)}
.sysbadge{font:700 10px/1 var(--mono);color:#fff;background:var(--navy);
  border-radius:20px;padding:4px 8px;margin-left:8px;vertical-align:2px;
  letter-spacing:.04em}
.tsec{scroll-margin-top:calc(var(--navh,0px) + 10px)}
.rbody{max-height:none}
/* Multi-column on a wide screen: a 20-player roster as one tall list wastes the
   width and forces scrolling past it to reach anything below. Groups are kept
   unbroken so a position never splits across columns. */
@media(min-width:900px){
  .rbody{column-count:2;column-gap:22px}
}
@media(min-width:1350px){
  .rbody{column-count:3}
}
.rgrp{margin-bottom:15px;break-inside:avoid;page-break-inside:avoid}
.rgrp:last-child{margin-bottom:0}
.rgrp-h{display:flex;align-items:center;gap:8px;font:700 10.5px/1 var(--sans);
  letter-spacing:.08em;text-transform:uppercase;color:var(--ink2);
  padding:0 0 6px;border-bottom:1px solid var(--line2);margin-bottom:2px}
.rgrp-n{font:700 10px/1 var(--mono);color:var(--ink3);background:var(--alt);
  border-radius:20px;padding:3px 7px}
.rrow{display:grid;grid-template-columns:32px 1fr auto;grid-template-areas:
  "num name stat" "num meta stat";align-items:center;gap:0 8px;
  padding:7px 9px 7px 6px;border-left:3px solid transparent;
  border-bottom:1px solid var(--line);transition:background .12s ease}
.rrow:last-child{border-bottom:0}
.rrow:hover{background:var(--alt)}
/* A starter is marked by a bar rather than a fill: the fill was too faint to
   read, and the legend under the table names this bar explicitly. */
.rrow--starter{border-left-color:#12864B}
.rrow--starter .rname{font-weight:700}
.rnum{grid-area:num;font:700 11.5px/1 var(--mono);color:var(--ink3);text-align:right}
.rname{grid-area:name;font-size:13.5px;font-weight:600}
.rmeta{grid-area:meta;font-size:11.5px;color:var(--ink2);margin-top:2px}
.rstat{grid-area:stat;font:700 14px/1 var(--mono);color:var(--navy);text-align:right;
  white-space:nowrap;padding-left:10px}
.rstat em{display:block;font:600 9px/1 var(--sans);letter-spacing:.05em;
  text-transform:uppercase;color:var(--ink3);font-style:normal;margin-top:3px}
.rstat .none{color:var(--ink3);font-weight:400}
h3 .h3n{font:700 10px/1 var(--mono);color:var(--ink3);background:var(--alt);
  border-radius:20px;padding:3px 7px;margin-left:7px;vertical-align:2px}
@media (max-width:560px){
  .rrow{grid-template-columns:26px 1fr auto;padding-right:4px}
  .rname{font-size:13px}
  .rmeta{font-size:11px}
  .rstat{font-size:13px;padding-left:6px}
}

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
  <p class="lead">{{RANK_BASIS}} The other columns are
  <b>reference only</b> &mdash; nothing here feeds the model. Click a team to see the six
  players the number is built from.</p>
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
  <p class="tabhint">Start typing, or click any team on the Rankings, Scores or
    Schedule tab to open it here.</p>
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
  /* The Teams tab used to open COMPLETELY BLANK -- a lone "Type a team" box,
     with no indication that anything lived here or which names it would accept.
     Land on the top-ranked team so the tab is never empty; a real selection is
     never overwritten. */
  if (b.dataset.v === 'teams' && !document.querySelector('#teamcard .thead')) {
    const first = Object.keys(TEAMS)
      .filter(k => TEAMS[k] && TEAMS[k].rank)
      .sort((x, y) => TEAMS[x].rank - TEAMS[y].rank)[0];
    if (first) showTeam(first);
  }
  /* Back to the top of the new tab.
     Since the nav became sticky you can switch tabs from anywhere on a very
     long page, and the scroll position carried over -- so Rankings opened with
     its first rows tucked under the sticky nav AND the sticky table header,
     and the #1 team was simply not on screen. Reported as "Nebraska fell off
     the rankings". Only scrolls up: if the user is already at the top this is
     a no-op and does not fight them. */
  if (window.scrollY > 0) window.scrollTo({top: 0, behavior: 'auto'});
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
    '<span class="kd">' + (c.pos ? c.pos + ' \u00b7 ' : '') + c.kind +
    (c.kind === 'transfer' && c.from ? ' \u00b7 ' + c.from : '') +
    '</span><span class="rt">' + (c.adj !== undefined ? c.adj : c.rate) + '</span></div>').join('');
  const LU_STATUS = {returning: 'back', departed: 'gone',
                     unknown: 'unresolved', no_roster: '\u2014'};
  const lu = t.lineup;
  const started = !lu ? '' : (lu.usual_six_2025 || []).map(c =>
    '<div class="plrow"><span class="nm">' + c.name + '</span>' +
    '<span class="kd">' + (c.pos || '') +
      (c.num !== null && c.num !== undefined ? ' \u00b7 #' + c.num : '') +
      ' \u00b7 ' + (LU_STATUS[c.status_2026] || c.status_2026) + '</span>' +
    '<span class="rt">' + c.starts_2025 + '</span></div>').join('');
  const POS_LABEL = {S:'Setters', OPP:'Opposites', OH:'Outside hitters',
                     MB:'Middle blockers', 'L/DS':'Libero / defensive specialists',
                     '':'Position not listed'};
  const POS_SEQ = ['S','OPP','OH','MB','L/DS',''];
  /* "unmatched" was internal jargon on a page a human reads. The two cases are
     genuinely different and both must stay honest: 'new' means the roster join
     placed her and she has no Division-I record at all; 'unresolved' means the
     join could not confirm her against 2025 at all, so she MIGHT have played
     and we simply cannot say. Neither gets a number. */
  const KIND_TAG = {returning:'', transfer:'transfer in', new:'no D-I record',
                    unresolved:'no 2025 stats matched'};
  const rost = t.roster || [];
  let rosterHtml = '';
  if (rost.length) {
    for (const grp of POS_SEQ) {
      const inGrp = rost.filter(r => r.p === grp);
      if (!inGrp.length) continue;
      rosterHtml += '<div class="rgrp"><div class="rgrp-h">' + POS_LABEL[grp] +
                    '<span class="rgrp-n">' + inGrp.length + '</span></div>';
      for (const r of inGrp) {
        /* Label the season on the number itself. It is a 2025 rate, and once
           2026 results pile up an unlabelled "pts/set" reads as current-season
           form -- the field meaning drifting away from its heading (R4). */
        const stat = (r.r !== null && r.r !== undefined)
          ? r.r + '<em>' + (r.k === 'transfer' ? '2025 elsewhere' : '2025 pts/set') + '</em>'
          : '<span class="none">&mdash;</span>';
        const sub = [];
        if (r.c) sub.push(r.c);
        if (r.praw) sub.push(r.praw);
        if (r.st) sub.push('started ' + r.st +
          (lu && lu.matches_with_lineup ? ' of ' + lu.matches_with_lineup : ''));
        if (r.sets) sub.push(r.sets + ' sets in 2025');
        if (KIND_TAG[r.k]) sub.push(KIND_TAG[r.k] + (r.k === 'transfer' && r.from ? ' from ' + r.from : ''));
        if (r.l26) sub.push('<b>2026: ' + r.l26.sets + ' sets</b>');
        rosterHtml += '<div class="rrow' + (r.st ? ' rrow--starter' : '') + '">' +
          '<span class="rnum">' + (r.num !== null && r.num !== undefined ? '#' + r.num : '') + '</span>' +
          '<span class="rname">' + r.n + '</span>' +
          '<span class="rmeta">' + sub.join(' \u00b7 ') + '</span>' +
          '<span class="rstat">' + stat + '</span></div>';
      }
      rosterHtml += '</div>';
    }
  }
  const dep = (t.top_dep || []).map(d =>
    '<div class="plrow"><span class="nm">' + d.name +
    (d.to ? '<span class="wentto">\u2192 ' + d.to + '</span>' : '') + '</span>' +
    '<span class="kd">departed</span><span class="rt">' + (d.pts || 0) + ' pts</span></div>'
  ).join('');
  box.innerHTML =
    '<div class="thead"><h2>' + logo(name, 'lg') + name + '</h2>' +
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
        (six ? '<div class="tnote">The six highest projected <b>scorers</b> \u2014 points per set, ' +
               'normalised to a neutral schedule. This is <b>not</b> a starting lineup: it ranks by ' +
               'scoring, so setters and defensive players drop out of it.</div>' : '') +
        '</div>' +
        (started ? '<div class="tsec" style="margin-top:14px">' +
             '<h3>Most-started six, 2025' +
             (lu.offense_system_2025
               ? '<span class="sysbadge" title="' +
                 (lu.offense_system_2025 === '5-1'
                   ? 'One setter on the floor: five hitters, one setter.'
                   : 'Two setters, opposite each other: six hitters, two setters.') +
                 '">' + lu.offense_system_2025 + '</span>' : '') +
             '</h3><div class="body">' + started + '</div>' +
             '<div class="tnote">Who this team actually started, from set-1 play-by-play. ' +
             'Right-hand number is matches started of ' + (lu.matches_with_lineup || 0) + ' on file' +
             (lu.coverage_ok === false ? ' (thin coverage \u2014 read it as partial)' : '') + '. ' +
             (lu.roster_join_available === false
                ? 'No 2026 roster for this team, so who is back is <b>unknown</b>, not zero.'
                : (lu.returning_of_six !== null && lu.returning_of_six !== undefined
                   ? '<b>' + lu.returning_of_six + ' of 6</b> are back for 2026' +
                     (lu.vacancies ? '; ' + lu.vacancies + ' slot' + (lu.vacancies > 1 ? 's are' : ' is') +
                      ' open \u2014 we do not guess who fills ' + (lu.vacancies > 1 ? 'them' : 'it') + '.' : '.')
                   : '')) +
             ' Listed by matches started. <b>Rotation order 1\u20136 is not available</b> \u2014 ' +
             'the feed orders its six by jersey number.</div></div>' : '') +
        (dep ? '<div class="tsec" style="margin-top:14px"><h3>Biggest losses</h3>' +
               '<div class="body">' + dep + '</div></div>' : '') +
        '<div class="tsec" style="margin-top:14px"><h3>Roster turnover</h3><div class="body">' +
          '<div class="plrow"><span class="nm">Returning</span><span class="rt">' + t.n_ret + '</span></div>' +
          '<div class="plrow"><span class="nm">Departed</span><span class="rt">' + t.n_dep + '</span></div>' +
          '<div class="plrow"><span class="nm">Transfers in</span><span class="rt">' + t.n_tin + '</span></div>' +
          '<div class="plrow"><span class="nm">New / no D-I record</span><span class="rt">' + t.n_new + '</span></div>' +
        '</div></div>' +
      '</div>' +
    '</div>' +
    (rosterHtml
      ? '<div class="tsec tsec--wide"><h3>Full roster' +
        '<span class="h3n">' + rost.length + '</span></h3>' +
        '<div class="body rbody">' + rosterHtml + '</div>' +
        '<div class="tnote">Roster from the school\u2019s own site; position and ' +
        'production from official box scores. A <b>green bar</b> marks a player who ' +
        'started at least one match in 2025. A player with no Division-I record shows ' +
        '<b>&mdash;</b> rather than a number \u2014 about a fifth of a season\u2019s ' +
        'production comes from players like her, and we do not invent it.</div></div>'
      : '');
}
/* The sticky table headers offset themselves by the nav's real height; the tab
   row wraps on a narrow window, so this is measured rather than hard-coded. */
function syncNavHeight() {
  const nav = document.querySelector('nav');
  if (nav) document.documentElement.style.setProperty('--navh', nav.offsetHeight + 'px');
}
syncNavHeight();
window.addEventListener('resize', syncNavHeight);

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


# Markers that must not survive into a PUBLIC build. Asserted after the strip,
# so a template edit that reintroduces one fails the build instead of quietly
# republishing somebody else's work.
# Markers must not collide with real DATA. "Massey" alone tripped on Addison
# Massey and Alexis Massey -- actual players on actual rosters. Match the
# product and the markup, never a bare word that can be somebody's surname.
PRIVATE_MARKERS = ("VolleyTalk", "Massey Ratings", "Massey Ratings, 2026",
                   'data-v="tv"', 'id="v-tv"', "tv_listings",
                   "chip('Massey'", "chip('VT'")


def strip_private(html):
    # type: (str) -> str
    """Remove the third-party views from the public page.

    Done as a post-pass on the finished HTML rather than as conditionals inside
    a 1,000-line template: the transformation is then a single place to read,
    and it is ASSERTED below rather than assumed.
    """
    # the On TV tab and its section
    html = re.sub(r'\s*<button role="tab"[^>]*data-v="tv"[^>]*>.*?</button>', "",
                  html, flags=re.S)
    html = re.sub(r'<section id="v-tv".*?</section>', "", html, flags=re.S)
    # third-party ranking columns
    html = re.sub(r'\s*<th title="VolleyTalk[^>]*>.*?</th>', "", html, flags=re.S)
    html = re.sub(r'\s*<th title="Massey[^>]*>.*?</th>', "", html, flags=re.S)
    html = re.sub(r'\s*<th title="range the other systems[^>]*>.*?</th>', "", html,
                  flags=re.S)
    # the sentence describing the reference columns, and the VT/Massey chips
    html = html.replace(
        "VolleyTalk and Massey are all forecasts of 2026.",
        "and the AVCA coaches poll are forecasts of 2026.")
    html = re.sub(r"chip\('VT',[^)]*\)\s*\+\s*", "", html)
    html = re.sub(r"chip\('Massey',[^)]*\)\s*\+\s*", "", html)
    return html


if __name__ == "__main__":
    html = build()
    if PUBLIC:
        html = strip_private(html)
        leaked = [m for m in PRIVATE_MARKERS if m in html]
        if leaked:
            raise SystemExit(
                "PUBLIC BUILD ABORTED: private source(s) still present: %s"
                % ", ".join(leaked))
    if not os.path.isdir(os.path.dirname(OUT)):
        os.makedirs(os.path.dirname(OUT))
    open(OUT, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))

    if PUBLIC:
        # Cache-bust the redirect. Fastly holds the object for ~10 minutes, so
        # without a new URL a freshly deployed page keeps serving old bytes long
        # enough for a phone check to test the previous build and report the fix
        # as broken. (Inherited from build_vb.py, which this supersedes.)
        import hashlib
        ver = hashlib.sha1(html.encode("utf-8")).hexdigest()[:12]
        idx = os.path.join(REPO, "index.html")
        if os.path.exists(idx):
            txt = open(idx, encoding="utf-8").read()
            txt = re.sub(r"output/vb_dashboard\.html(\?v=[0-9a-f]+)?",
                         "output/vb_dashboard.html?v=" + ver, txt)
            open(idx, "w", encoding="utf-8").write(txt)
            print("index.html -> output/vb_dashboard.html?v=%s" % ver)
