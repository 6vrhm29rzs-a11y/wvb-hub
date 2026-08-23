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


# Cody watches from the Pacific timezone, so the page reads in Pacific. The
# SPORT still schedules in Eastern and the feed still publishes in Eastern --
# that is why the placeholder check below runs on the Eastern string BEFORE any
# conversion. A 1:00 AM ET placeholder becomes a perfectly ordinary-looking
# 10:00 PM PT, so converting first would launder a non-time into a plausible one.
try:
    PT = ZoneInfo("America/Los_Angeles")
except Exception:                                      # noqa: BLE001
    PT = None


def _pt_date(epoch) -> str:
    """Calendar date as Cody sees it."""
    if PT is not None:
        return datetime.datetime.fromtimestamp(int(epoch), PT).strftime("%Y-%m-%d")
    return (datetime.datetime.utcfromtimestamp(int(epoch))
            - datetime.timedelta(hours=7)).strftime("%Y-%m-%d")


def _pt_time(epoch) -> str:
    if PT is None:
        return ""
    return datetime.datetime.fromtimestamp(int(epoch), PT).strftime("%-I:%M %p PT")


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


def blob(o) -> str:
    """JSON for embedding in a <script> block.

    `</` is escaped because a value containing `</script>` would end the block
    and break every line below it. Every payload was feed-derived until Digby,
    whose text is MODEL-WRITTEN -- the first content here that could contain
    arbitrary characters. Escaping `/` inside a JSON string is valid JSON and
    round-trips losslessly.
    """
    return json.dumps(o, separators=(",", ":")).replace("</", "<\\/")


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
            "date": (_pt_date(ep) if ep else None),
            "epoch": int(ep) if ep else 0,
            "away": away.get("name_short"), "home": home.get("name_short"),
            "away_sets": away.get("sets_won"), "home_sets": home.get("sets_won"),
            "away_rank": away.get("team_rank"), "home_rank": home.get("team_rank"),
            "away_d1": away.get("division") == 1, "home_d1": home.get("division") == 1,
            "time": _pt_time(ep) if ep else "",
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

# Implausible in EASTERN -- the zone the sport schedules in and the feed
# publishes in. Widened from 12-5 AM to 12-7 AM after a 6:00 AM ET fixture
# turned up at Charlotte. 8 AM is the floor because genuine morning matches DO
# happen: an August tournament routinely opens at 10:00 AM ET, which is a real
# 7:00 AM for a Pacific viewer and must not be suppressed.
_EARLY_AM = re.compile(r"^(12|[1-7]):\d\d\s*AM", re.I)


def listed_time(start_time, home_team, epoch=None):
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
    # Real time -- now show it in Cody's timezone. Converted from the EPOCH,
    # not by re-parsing the Eastern string, so there is one conversion and no
    # chance of drifting an hour on a DST boundary.
    if epoch and PT is not None:
        try:
            return datetime.datetime.fromtimestamp(int(epoch), PT).strftime("%-I:%M %p PT")
        except (TypeError, ValueError, OSError):
            pass
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
                "t": listed_time(g.get("startTime"), h, g.get("startTimeEpoch")),
                "ar": (g.get("away") or {}).get("rank") or "",
                "hr": (g.get("home") or {}).get("rank") or "",
            })
        if len(set(r["d"] for r in rows)) > limit_days:
            break
    return rows


_TV_T = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*$", re.I)


def _tv_pt(t):
    """TV listings are transcribed in EASTERN. Shift them to Pacific.

    A plain -3h works here and a timezone conversion would not be safer: the
    listing carries no date-time, only "6 p.m.", and both zones observe the same
    daylight-saving dates, so the offset between them is 3 hours year-round.
    Anything that does not parse is passed through UNCHANGED rather than
    guessed at -- a garbled time is better than a confidently wrong one.
    """
    m = _TV_T.match(t or "")
    if not m:
        return t
    hr = int(m.group(1)) % 12
    if m.group(3).lower() == "p":
        hr += 12
    hr = (hr - 3) % 24
    ampm = "a.m." if hr < 12 else "p.m."
    h12 = hr % 12 or 12
    mins = m.group(2)
    return "%d%s %s" % (h12, (":" + mins) if mins else "", ampm)


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
        out.append({"day": d, "m": m, "n": n, "t": _tv_pt(t)})
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
                prior_pos=None, site_pos=None, id2name=None, live_floor=0,
                photos=None, art=None):
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
            # HER OWN PHOTOGRAPH, where her school published one. The exact URLs
            # the projected six already uses -- the full roster simply never
            # asked for them. URL only: never downloaded, never committed.
            "ph": ((art or {}).get(re.sub(r"[^a-z]", "", (name or "").lower()))
                   or (photos or {}).get(re.sub(r"[^a-z]", "", (name or "").lower()))),
        }
        if lv and lv.get("sets"):
            # THIS SEASON'S RATE, from raw counts (the feed's own `points`
            # column is unusable as a season total). Once she has played a real
            # share of what has been possible, THIS is the headline number and
            # last season becomes context -- 2026 is the season being watched,
            # and a 2025 rate sitting in the primary slot in November would be
            # answering a question nobody asked.
            _pts = ((lv.get("kills") or 0) + (lv.get("aces") or 0)
                    + (lv.get("block_solos") or 0)
                    + 0.5 * (lv.get("block_assists") or 0))
            _r26 = round(_pts / lv["sets"], 2) if lv["sets"] else None
            row["l26"] = {"m": lv.get("matches"), "sets": lv.get("sets"),
                          "kills": lv.get("kills"), "pos": lv.get("pos"),
                          "num": lv.get("num"), "r": _r26}
            # same qualifying rule as the leaderboard, so there is one
            # definition of "enough of this season to rank on"
            row["live_primary"] = bool(_r26 is not None
                                       and live_floor
                                       and lv["sets"] >= live_floor)
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


def team_index(teams, res, pred_by_pair, sim_of, live_floor=0, tstats=None,
               aq_of=None, sched_n=None):
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
            t = listed_time(g.get("startTime"), h, g.get("startTimeEpoch"))
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
    # Digby's team summaries. PRIVATE ONLY -- they are model-written, they cost
    # money to make, and the public page has no server behind it. An absent or
    # rejected summary simply is not there, and the panel shows nothing.
    digby = {}
    if not PUBLIC:
        digby = ((load("data/digby_summaries_%d.json" % SEASON) or {})
                 .get("teams", {}) or {})

    # 2025 SERVING ROTATIONS, derived from the NCAA's own play-by-play (which
    # names a server on every rally, unlike ncaa.com's feed). Keyed on NCAA team
    # names, so joined through the SAME normaliser everything else uses rather
    # than a second one -- R4, and the "LSU New Orleans " lesson.
    rot25 = {}
    _rotdoc = load("data/rotations_%d.json" % (SEASON - 1)) or {}
    if _rotdoc:
        _byn = {}
        for _k, _v in (_rotdoc.get("teams") or {}).items():
            _byn[team_norm(_k)] = _v

    # Hand-drawn player art, if any: Cody/players/<Team>/<name>.png. Matched on
    # the same squashed-name key the photos use, so one definition of "the same
    # player" (R4). PRIVATE BUILD ONLY.
    player_art = {}
    _artdir = os.path.join(REPO, "Cody", "players")
    if os.path.isdir(_artdir) and not PUBLIC:
        for _team in os.listdir(_artdir):
            _td = os.path.join(_artdir, _team)
            if not os.path.isdir(_td):
                continue
            for _fn in os.listdir(_td):
                _stem, _ext = os.path.splitext(_fn)
                if _ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    continue
                _key = re.sub(r"[^a-z]", "", _stem.lower())
                # URL-ENCODED: "Brooklyn DeLeye.png" has a space in it, and an
                # unencoded space silently fails to load -- the img renders as a
                # blank box with no error anywhere.
                import urllib.parse as _up
                player_art.setdefault(_team, {})[_key] = "players/%s/%s" % (
                    _up.quote(_team), _up.quote(_fn))

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
                             (site_pos_all.get(nm) or {}).get("positions"), id2name,
                             live_floor,
                             photos=(photos.get(nm) or photos.get(_rk) or {}),
                             art=(player_art.get(nm) or player_art.get(_rk) or {}))
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
            "digby": (digby.get(nm) or {}).get("summary"),
            "lineup": lineup.get(nm),
            "rot25": (_byn.get(team_norm(nm)) if _rotdoc else None),
            "tstats": (tstats or {}).get(nm),
            "aq": (aq_of or {}).get(t["conf"]),
            "sched_n": (sched_n or {}).get(team_norm(nm), 0),
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
    # team_id -> name. Built from LAST season's dataset AND this season's game
    # log, because a non-D-I opponent this year need not appear in last year's
    # teams list at all. When it did not, the box score printed the raw id --
    # "45905" sat where "Elizabeth City St." belonged, which is an internal key
    # shown to a reader (R5's cousin: the value was not invented, but it was not
    # a name either).
    team_of = {}
    ds = load("data/data_2025.json") or {}
    for t in ds.get("teams", []):
        if t.get("team_id"):
            team_of[str(t["team_id"])] = t["name_short"]
    gl = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if os.path.exists(gl):
        with open(gl) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                for t in (rec.get("teams") or []):
                    tid, nm = str(t.get("team_id") or ""), t.get("name_short")
                    if tid and nm:
                        team_of.setdefault(tid, nm)

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

def team_season_stats(boxes, res):
    # type: (Dict, Any) -> Dict[str, Any]
    """Season team totals for 2026, from the same raw counts the box scores use.

    BOTH SIDES OF THE BALL. Every box score carries both teams, so the same pass
    that totals what a team DID also totals what it ALLOWED -- opponent hitting
    percentage is the single most useful defensive number in the sport and it
    falls out for free. A page that shows only the offence is showing half a
    team.

    RATES ARE PER SET, and the denominator is the MATCH's sets, not the sum of
    the players' -- six players are on court at once, so summing their set
    counts gives roughly six times the truth. That mistake makes every rate look
    a sixth of what it is, which is subtle enough to survive a glance.

    Hitting percentage is (K - E) / TA from the SUMMED counts, never the mean of
    the players' percentages.
    """
    acc = {}                                            # type: Dict[str, Any]

    def blank():
        return {"k": 0.0, "e": 0.0, "ta": 0.0, "ast": 0.0, "digs": 0.0,
                "bs": 0.0, "ba": 0.0, "aces": 0.0, "sets": 0.0, "matches": 0,
                "board": 0.0}                           # points on the scoreboard

    # SCOREBOARD POINTS, from the linescores, keyed by game. A team's points are
    # NOT the sum of its kills, aces and blocks: MEASURED across the 2026
    # matches so far, 18-35% of every team's points are opponent errors, which
    # nobody is credited with. Both numbers are real and they are different, so
    # the page shows both rather than picking one and calling it "points".
    board = {}                                          # type: Dict[str, Dict[str, float]]
    for r in (res or []):
        sets = r.get("sets") or []
        if not sets or not r.get("gid"):
            continue
        # `sets` is [[away, home], ...] -- the same order as away_sets/home_sets.
        board[str(r["gid"])] = {
            r.get("away"): float(sum(p[0] for p in sets if len(p) == 2)),
            r.get("home"): float(sum(p[1] for p in sets if len(p) == 2)),
        }

    for gid, rows in (boxes or {}).items():
        by_team = {}
        for r in rows or []:
            by_team.setdefault(r.get("team"), []).append(r)
        if len(by_team) != 2:
            continue                                    # cannot form an opponent
        names = list(by_team)
        for i, team in enumerate(names):
            opp = names[1 - i]
            mine = acc.setdefault(team, {"own": blank(), "opp": blank()})
            for src, dst in ((by_team[team], mine["own"]),
                             (by_team[opp], mine["opp"])):
                sets = 0.0
                for r in src:
                    for f in ("k", "e", "ta", "ast", "digs", "bs", "ba", "aces"):
                        dst[f] += float(r.get(f) or 0)
                    sets = max(sets, float(r.get("sets") or 0))
                dst["sets"] += sets
                dst["matches"] += 1
            mine["own"]["board"] += (board.get(str(gid)) or {}).get(team, 0.0)
            mine["opp"]["board"] += (board.get(str(gid)) or {}).get(opp, 0.0)

    out = {}
    for team, sides in acc.items():
        row = {}
        for key in ("own", "opp"):
            d = sides[key]
            n = d["sets"] or 0
            row[key] = {
                "matches": d["matches"], "sets": round(n, 1),
                "kills": d["k"], "errors": d["e"], "attacks": d["ta"],
                "assists": d["ast"], "digs": d["digs"], "aces": d["aces"],
                "blocks": d["bs"] + d["ba"] * 0.5,
                "hit": (round((d["k"] - d["e"]) / d["ta"], 3) if d["ta"] else None),
                "kps": (round(d["k"] / n, 2) if n else None),
                "asps": (round(d["ast"] / n, 2) if n else None),
                "dps": (round(d["digs"] / n, 2) if n else None),
                "bps": (round((d["bs"] + d["ba"] * 0.5) / n, 2) if n else None),
                "aps": (round(d["aces"] / n, 2) if n else None),
                # EARNED points: kills + aces + blocks, the volleyball scoring
                # formula. Computed from raw counts, not the box score's own
                # `points` column -- that column is missing from some games, so
                # a season sum of it silently undercounts.
                "earned": d["k"] + d["aces"] + d["bs"] + d["ba"] * 0.5,
                "pps": (round((d["k"] + d["aces"] + d["bs"] + d["ba"] * 0.5) / n, 2)
                        if n else None),
                "board": d["board"],
                "bpps": (round(d["board"] / n, 2) if n else None),
            }
        out[team] = row
    return out


def team_logos():
    # type: () -> Dict[str, str]
    """team -> crest URL, from each school's ncaa.com seoname."""
    out = {}
    for t in (load("data/data_2025.json") or {}).get("teams", []):
        if t.get("seoname"):
            out[t["name_short"]] = (
                "https://www.ncaa.com/sites/default/files/images/logos/schools/"
                "bgl/%s.svg" % t["seoname"])
    return out


def logo_img(team, logos, cls=""):
    # type: (str, Dict[str, str], str) -> str
    """A team's crest, or nothing. Never a placeholder mark.

    Server-side twin of the page's `logo()`: rows rendered in Python could not
    reach the JS one, which is how five views ended up crest-less while the
    team panel and box scores had them. `onerror` hides a crest that 404s
    rather than leaving a broken-image glyph in a table.
    """
    u = (logos or {}).get(team)
    if not u:
        return ""
    return ('<img class="tlogo %s" src="%s" alt="" loading="lazy" '
            'onerror="this.style.display=\'none\'">' % (cls, esc(u)))


def top25_view():
    # type: () -> Dict[str, str]
    """Rows and copy for Digby's Top 25.

    EVERY SENTENCE HERE IS BUILT FROM A MEASURED VALUE (R1). The lead states
    what fraction of the rating is this season, computed from k and the matches
    actually played -- not a phrase written in advance about how the season is
    going.
    """
    doc = load("data/digby_top25_%d.json" % SEASON) or {}
    colors = ((load("data/team_colors_%d.json" % SEASON) or {}).get("teams") or {})
    logos = team_logos()
    top = doc.get("top") or []
    if not top:
        return {"rows": "", "also": "", "lead":
                "No Top 25 yet &mdash; run <code>scripts/digby_top25.py</code>.",
                "foot": "", "season": str(SEASON)}
    m = doc.get("meta") or {}

    # WHAT "MOVE" MEANS, and it must say which. Prefer the most recent WEEKLY
    # snapshot that is (a) not this week and (b) on the SAME basis -- comparing
    # a Top 25 rank against a preseason-projection rank is arithmetic on two
    # different rulers, the mistake `test_rankings_history.py` was written for.
    # Until such a week exists, fall back to the preseason order and LABEL it.
    pre, basis = {}, "preseason"
    hist_p = os.path.join(REPO, "data", "rankings_history_%d.jsonl" % SEASON)
    if os.path.exists(hist_p):
        import datetime as _dt
        this_week = _dt.date.today().isocalendar()
        this_week = "%d-W%02d" % (this_week[0], this_week[1])
        best = None
        for line in open(hist_p, encoding="utf-8"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("source") != "digby" or row.get("week") == this_week:
                continue
            if best is None or (row.get("week") or "") > (best.get("week") or ""):
                best = row
        if best:
            for r in (best.get("ranking") or best.get("teams") or []):
                if r.get("rank"):
                    pre[r["team"]] = r["rank"]
            basis = "week"
    if not pre:
        for r in ((load("data/projection_2026.json") or {}).get("teams") or []):
            if r.get("blend_rank"):
                pre[r["team"]] = r["blend_rank"]

    rows = []
    for r in top:
        team = r["team"]
        was = pre.get(team)
        if was is None:
            mv = ""
        elif was == r["rank"]:
            mv = '<span class="mv-flat">&ndash;</span>'
        elif was > r["rank"]:
            mv = '<span class="mv-up">&#9650;%d</span>' % (was - r["rank"])
        else:
            mv = '<span class="mv-dn">&#9660;%d</span>' % (r["rank"] - was)
        wt = r.get("weight_on_season") or 0
        rows.append(
            '<tr class="row" data-team="%s" style="--tc:%s"><td class="rk">%d</td>'
            '<td class="tm">%s%s</td><td class="mvc">%s</td><td class="cf">%s</td>'
            '<td class="rec">%s</td><td class="n">%s</td><td class="n wt">%s</td></tr>'
            % (esc(team), (colors.get(team) or {}).get("primary") or "var(--line)",
               r["rank"], logo_img(team, logos), esc(team), mv,
               esc(r.get("conf") or ""),
               r.get("record") or "0-0",
               ("%+.2f" % r["net_pts_per_set"]) if r.get("net_pts_per_set") is not None
               else "&mdash;",
               ("%d%%" % round(100 * wt)) if wt else "&mdash;"))

    also = " &middot; ".join(
        "%s <span class=\"arv\">%s</span>" % (esc(a["team"]), a.get("record") or "0-0")
        for a in (doc.get("also_receiving") or []))

    played = m.get("matches_counted") or 0
    k = m.get("k_matches") or 0
    withres = m.get("teams_with_a_result") or 0
    maxw = max([r.get("weight_on_season") or 0 for r in top] or [0])
    lead = (
        "A <b>strength</b> ranking that moves with every result. It starts from "
        "the preseason projection and lets this season pull it, weighted "
        "<code>n/(n+%.1f)</code> &mdash; so a team needs <b>%.1f matches</b> "
        "before this season counts as much as the projection does. "
        "%d D-I matches are in; %d of the 25 have played, and the most any team "
        "is being judged on this season is <b>%d%%</b>."
        % (k, k, played, sum(1 for r in top if r.get("matches")),
           round(100 * maxw)))
    foot = (
        "<b>Why so little movement in August?</b> %.1f is not a preference "
        "&mdash; it is the per-match spread (%.2f points/set) divided by how "
        "much the projection still gets wrong (it predicts the next season at "
        "rho %.2f out of sample). One Friday night genuinely is that little "
        "evidence. &nbsp;<b>This is not a resume ranking:</b> it answers who "
        "would win a match, not who has earned a bid &mdash; the bracket tab is "
        "the second question. &nbsp;<b>And the schedule is barely adjusted for "
        "yet</b>: with %d matches played there is no schedule graph, so beating "
        "nobody still looks like beating somebody. That corrects itself as the "
        "season fills in."
        % (k, (m.get("per_match_variance") or 0) ** 0.5,
           m.get("prior_rho_out_of_sample") or 0, played))
    return {"rows": "".join(rows), "also": also, "lead": lead, "foot": foot,
            "season": str(SEASON),
            "movehead": ("vs last week" if basis == "week" else "vs preseason")}


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
    # School colours read out of each logo SVG (scripts/crawl_team_colors.py).
    # A team with no readable colour is simply absent, and the avatar falls
    # back to a neutral rather than to an invented hue.
    team_colors = ((load("data/team_colors_%d.json" % SEASON) or {})
                   .get("teams") or {})
    _t25 = top25_view()
    sched = schedule()
    tvrows = tv()
    sim = load("data/season_sim_%d.json" % SEASON) or {}
    sim_of = {r["team"]: r for r in sim.get("teams", [])}
    tourn_of = {r["team"]: r.get("tournament_pct") for r in sim.get("teams", [])}
    preds = load("data/predictions_%d.json" % SEASON) or {}
    pred_by_pair = {}
    for r in preds.get("games", []):
        pred_by_pair[(r["date"], r["away"], r["home"])] = r
    logos = team_logos()
    boxes, plist = box_and_players(res)
    # Season team totals for 2026, both what a team does and what it allows.
    tstats = team_season_stats(boxes, res)
    stand = standings(teams, res)
    ldrs, ldr_floor, ldr_pool = leaders()
    # How a conference awards its automatic bid, and how many matches each team
    # actually has on the schedule -- both needed to say honestly what the
    # projection covers.
    aq_of = ((load("data/raw/%d/aq_mechanism_%d.json" % (SEASON, SEASON)) or {})
             .get("conferences") or {})
    sched_n = {}
    for _p in sorted(glob.glob(os.path.join(REPO, "data/raw/%d/scoreboard/*.json" % SEASON))):
        try:
            _pay = json.load(open(_p))
        except ValueError:
            continue
        for _e in _pay.get("games") or []:
            _g = _e.get("game", _e)
            for _side in ("away", "home"):
                _n = (_g.get(_side) or {}).get("names", {}).get("short")
                if _n:
                    # THROUGH THE NORMALISER, not the raw name. The scoreboard
                    # says "LSU New Orleans" and the hub says "New Orleans", so
                    # a raw-name count gave that team ZERO fixtures -- the same
                    # join that `reconcile_2025.norm()` already exists to fix.
                    _k = team_norm(_n)
                    sched_n[_k] = sched_n.get(_k, 0) + 1
    tindex = team_index(teams, res, pred_by_pair, sim_of, ldr_floor,
                        tstats=tstats, aq_of=aq_of, sched_n=sched_n)
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
            '<td class="tm">%s%s%s</td><td class="cf">%s</td>'
            '<td class="n hi">%s</td><td class="n">%s</td>%s'
            '<td class="n">%s</td>%s<td class="n">%s</td><td class="n hi">%s</td></tr>%s'
            % (t["rank26"], t["rank26"], mover(t),
               logo_img(t["team"], logos), esc(t["team"]),
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

    # Same computed sentence as the board: a hard-coded "6 of 32" understates
    # what we know the moment the map is filled in, and a stale caveat is worse
    # than none.
    _aqdoc = load("data/raw/%d/aq_mechanism_%d.json" % (SEASON, SEASON)) or {}
    _aqrows = _aqdoc.get("conferences") or {}
    _aqconf = sum(1 for v in _aqrows.values() if "CONFIRMED" in (v.get("tier") or ""))
    _aqreg = sorted(k for k, v in _aqrows.items()
                    if v.get("mechanism") == "REGULAR_SEASON")
    if _aqrows and _aqconf == len(_aqrows):
        aq_mech = ("How each league awards its bid is confirmed for all %d "
                   "conferences: %d by tournament, and %s by regular-season "
                   "champion. That is 2025 evidence \u2014 the Big Ten and "
                   "Pac-12 both added a tournament for 2026, which is applied."
                   % (len(_aqrows), len(_aqrows) - len(_aqreg),
                      ", ".join(_aqreg) if _aqreg else "none"))
    else:
        aq_mech = ("The AQ mechanism is confirmed for %d of %d conferences; the "
                   "rest default to tournament and are flagged unverified."
                   % (_aqconf, len(_aqrows) or 32))

    # The published rankings, as their own views. The whole point of this page
    # is not having to open ncaa.com and the AVCA site, and a rank shown as a
    # bare column is not the poll -- the poll is an ordering with points and
    # first-place votes behind it.
    def _latest(name):
        """Newest capture for THIS season; if none exists, the newest from a
        previous one, flagged as such.

        ⚠ The rankings endpoint is CURRENT-ONLY, and in August "current" is
        still LAST season's final table -- the RPI feed served "Through Games
        Dec. 21 2025" (Nebraska 33-1) on 2026-08-23. Showing that under a 2026
        heading would silently mix two seasons, so a fallback has to announce
        itself rather than pass as this year's."""
        for yr in range(SEASON, SEASON - 3, -1):
            pth = os.path.join(REPO, "data", "raw", str(yr), "polls_%s.jsonl" % name)
            rec = None
            if os.path.exists(pth):
                for ln in open(pth):
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        rec = json.loads(ln)
                    except ValueError:
                        continue
            if rec:
                rec = dict(rec)
                rec["_season"] = yr
                rec["_is_prev"] = (yr != SEASON)
                return rec
        return {}
    polls = {}
    for _n in ("avca", "top16", "rpi"):
        _r = _latest(_n)
        if _r.get("rows"):
            polls[_n] = {"stamp": _r.get("stamp"), "title": _r.get("title"),
                         "captured": _r.get("date"), "rows": _r["rows"],
                         "season": _r.get("_season"), "prev": _r.get("_is_prev")}

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
            '<div class="card done" data-gid="%s"><div class="cd">%s &middot; %s%s</div>'
            '<div class="mt"><div class="side %s">%s%s%s<b>%s</b></div>'
            '<div class="side %s">%s%s%s<b>%s</b></div></div>'
            '<div class="sets">%s</div>'
            '<div class="venue">%s</div></div>'
            % (esc(r.get("gid") or ""), esc(r["date"] or ""), esc(r["time"]), nond1,
               "win" if awin else "", rank(r["away_rank"]),
               logo_img(r["away"], logos), esc(r["away"]), r["away_sets"],
               "" if awin else "win", rank(r["home_rank"]),
               logo_img(r["home"], logos), esc(r["home"]), r["home_sets"],
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
            '<tr><td class="cd">%s</td><td class="n">%s</td><td class="tm">%s%s%s</td>'
            '<td class="at">at</td><td class="tm">%s%s%s</td>'
            '<td class="n pick %s">%s</td></tr>'
            % (r["d"], r["t"] or "&mdash;",
               ('<i class="rnk">%s</i> ' % r["ar"]) if r["ar"] else "",
               logo_img(r["a"], logos), esc(r["a"]),
               ('<i class="rnk">%s</i> ' % r["hr"]) if r["hr"] else "",
               logo_img(r["h"], logos), esc(r["h"]),
               cls, pick))
    srows = "".join(srows)

    trows = "".join(
        '<tr><td class="cd">%s</td><td class="tm">%s</td>'
        '<td class="net">%s</td><td class="n">%s</td></tr>'
        % (esc(r["day"]), esc(r["m"]), esc(r["n"]), esc(r["t"]))
        for r in tvrows)

    slope = level.get("recommended_slope")
    return TEMPLATE \
        .replace("{{POLLS_JSON}}", json.dumps(polls, separators=(",", ":"))) \
        .replace("{{ASK_CSS}}", "" if PUBLIC else ASK_CSS) \
        .replace("{{DIGBY_FACE_JS}}",
                 json.dumps("" if PUBLIC else DIGBY_SVG)) \
        .replace("{{ASK_HTML}}", "" if PUBLIC else ASK_HTML) \
        .replace("{{ASK_JS}}", "" if PUBLIC else ASK_JS) \
        .replace("{{DIGBY_CSS}}", "" if PUBLIC else DIGBY_CSS) \
        .replace("{{DIGBY_SVG}}", "" if PUBLIC else DIGBY_SVG) \
        .replace("{{DIGBY_COACH}}",
                 ('<img class="digby-coach" src="%s" alt="">' % DIGBY_COACH)
                 if (DIGBY_COACH and not PUBLIC) else "") \
        .replace("{{T25_ROWS}}", _t25["rows"]) \
        .replace("{{T25_ALSO}}", _t25["also"]) \
        .replace("{{T25_LEAD}}", _t25["lead"]) \
        .replace("{{T25_FOOT}}", _t25["foot"]) \
        .replace("{{T25_SEASON}}", _t25["season"]) \
        .replace("{{T25_MOVEHEAD}}", _t25["movehead"]) \
        .replace("{{RANK_BASIS}}", rank_basis) \
        .replace("{{AQ_MECH}}", aq_mech) \
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
        .replace("{{COLORS_JSON}}", json.dumps(team_colors, separators=(",", ":"))) \
        .replace("{{BOXES_JSON}}", json.dumps(boxes, separators=(",", ":"))) \
        .replace("{{PLAYERS_JSON}}", json.dumps(plist, separators=(",", ":"))) \
        .replace("{{N_PLAYERS}}", str(len(plist))) \
        .replace("{{LEADERS_JSON}}", json.dumps(ldrs, separators=(",", ":"))) \
        .replace("{{TSTATS_JSON}}", blob(
            [dict(team=k, conf=(tindex.get(k) or {}).get("conf"), **v)
             for k, v in sorted(tstats.items())])) \
        .replace("{{LDR_FLOOR}}", str(ldr_floor)) \
        .replace("{{LDR_POOL}}", str(ldr_pool)) \
        .replace("{{TEAMS_JSON}}", blob(tindex)) \
        .replace("{{CONF_JSON}}", json.dumps(sorted(set(t["conf"] for t in teams if t["conf"])))) \
        .replace("{{SLOPE}}", ("%.3f" % slope) if slope else "&mdash;") \
        .replace("{{LAST}}", esc(first_played or "not yet")) \
        .replace("{{BUILT}}", (
            datetime.datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT") if PT
            else datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%MZ")))


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- Oswald: the condensed, squared display face broadcast graphics are built on.
     Linked rather than embedded -- three weights inline is ~150 KB in a file
     that is already 4.8 MB, and this page is opened from a machine that has a
     network. The fallback stack is Apple's own condensed faces, so offline it
     degrades to something narrow rather than to a wide system sans. -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>NCAA Women's Volleyball 2026</title>
<style>
/* Legibility first. Cody asked for something that reads like a scores site --
   NCAA, ESPN, a team page -- so this is light, high-contrast and quiet. The
   volleyball identity lives in one place, the per-set strip, rather than in a
   loud palette. Navy for structure, amber for the set a team won, red for live. */
:root{
  /* PALETTE FROM THE SPORT'S OWN MATERIALS, not a UI kit.
     The neutrals here used to be Tailwind's default grey ramp (#111827 /
     #4B5563 / #9CA3AF / #E2E6EC), which is why the page read as generic: those
     five values sit under a very large share of dashboards on the internet.
     Replaced with warm, sand-tinted neutrals taken from an indoor court's
     playing surface, and an accent pair taken from the Molten ball the NCAA
     actually plays with -- deep blue and a hard yellow. Warm ground under cool
     blue is the whole identity; keep it. */
  --page:#F6F1E7; --card:#FFFFFF; --alt:#FBF7EF;
  --ink:#141210; --ink2:#5A5347; --ink3:#9A8F7D;
  --line:#E7DECD; --line2:#D2C5AC;
  --navy:#0B4F87; --blue:#1D6FD0; --amber:#FFC72C; --amber-bg:#FFF4D6;
  --sand:#EFE3CC;
  --live:#C8322B; --win:#0F7A3D;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;
  /* Display: condensed and loud, for anything that behaves like a headline or a
     scoreboard. Body copy stays in the system sans -- condensed type is fast to
     read in three words and slow to read in three sentences. */
  --disp:"Oswald","Avenir Next Condensed","HelveticaNeue-CondensedBold",
         "Arial Narrow",var(--sans);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);
  font:15px/1.55 var(--sans);font-feature-settings:"tnum" 1}

header{background:var(--navy);color:#fff;padding:20px 24px 0}
.mast{max-width:1280px;margin:0 auto;display:flex;align-items:flex-end;
  justify-content:space-between;gap:20px;flex-wrap:wrap}
h1{margin:0;font:600 40px/.92 var(--disp);letter-spacing:.005em;
  color:#fff;text-transform:uppercase}
h1 em{font-style:normal;color:var(--amber)}
.season{font:700 10px/1 var(--mono);color:#8FB6DC;letter-spacing:.34em;
  text-transform:uppercase;margin-bottom:9px}
.meta{font:12px/1.65 var(--mono);color:#B9CBE4;text-align:right}
.meta b{color:#fff}
/* The net: white mesh under a taut yellow tape. It is the one thing in the
   sport every viewer can draw from memory, so it carries the masthead. */
.net{max-width:1280px;margin:17px auto 0;height:11px;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.30) 0 1px,transparent 1px 6px),
             repeating-linear-gradient(0deg,rgba(255,255,255,.30) 0 1px,transparent 1px 6px);
  border-top:3px solid var(--amber)}
nav{background:var(--navy);position:sticky;top:0;z-index:6}
nav .inner{max-width:1280px;margin:0 auto;display:flex;gap:2px;flex-wrap:wrap;padding:0 8px}
nav button{appearance:none;border:0;background:transparent;color:#B9CBE4;
  font:500 14.5px/1 var(--disp);letter-spacing:.055em;padding:14px 16px;cursor:pointer;
  border-bottom:3px solid transparent;text-transform:uppercase;
  transition:color .16s ease}
nav button:hover{color:#fff}
nav button[aria-selected=true]{color:#fff}
nav .inner{position:relative}
nav .inner::after{content:"";position:absolute;bottom:0;left:0;height:3px;
  width:var(--barw,0px);transform:translateX(var(--barx,0px));background:var(--amber);
  transition:transform .26s cubic-bezier(.4,0,.2,1),width .26s cubic-bezier(.4,0,.2,1);
  pointer-events:none}
@media (prefers-reduced-motion:reduce){nav .inner::after{transition:none}}
nav button:focus-visible{outline:2px solid var(--amber);outline-offset:-3px}

main{max-width:1280px;margin:0 auto;padding:22px 16px 70px}
section[hidden]{display:none}
.lead{color:var(--ink2);font-size:14px;max-width:74ch;margin:0 0 16px}
.lead b{color:var(--ink)}

.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;
  overflow:hidden;box-shadow:0 1px 2px rgba(16,24,40,.05)}
table{width:100%;border-collapse:collapse}
th{font:500 12px/1 var(--disp);letter-spacing:.08em;text-transform:uppercase;
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
/* align-items:start, or a card that opens its box score drags every sibling in
   its row to the same height and leaves a column of dead white space beside it. */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;
  align-items:start}
/* an opened card gets the full width -- a 12-column box score cannot live in a
   330px cell, which is why the last columns were being clipped off */
.card.open{grid-column:1/-1}
/* A result reads like a line on a scoresheet, not a rounded app card: squared
   corners, a court-blue rule down the left, and the winner carrying the weight. */
.card{background:var(--card);border:1px solid var(--line);border-radius:2px;
  border-left:3px solid var(--line2);
  padding:14px 16px 13px;box-shadow:0 1px 0 rgba(20,18,16,.04)}
.card.done{border-left-color:var(--navy)}
.cd{font:700 11.5px/1 var(--mono);color:var(--ink2);letter-spacing:.06em;
  margin-bottom:11px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.mt{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}
.side{display:flex;align-items:baseline;gap:8px;color:var(--ink2);font-size:16px}
/* The match score is the loudest number on the card. It is the only thing most
   people are looking for, so it is sized like a scoreboard rather than like
   body text. */
.side b{margin-left:auto;font:600 34px/1 var(--disp);color:var(--ink3);
  letter-spacing:.01em;font-variant-numeric:tabular-nums;
  transition:color .18s ease}
.side.win{color:var(--ink);font-weight:700}
.side{font:400 17px/1.2 var(--disp);letter-spacing:.012em}
.side.win b{color:var(--navy)}
/* the signature: each set is a column, visitor above, home below, winner lit */
.sets{display:flex;gap:5px;margin-bottom:10px}
.set{flex:0 1 64px;display:flex;flex-direction:column;border:1px solid var(--line2);
  border-radius:2px;overflow:hidden;min-width:40px}
.set span{font:700 12.5px/1 var(--mono);padding:6px 0;text-align:center;
  color:var(--ink3);background:var(--alt)}
/* the set winner is LIT -- the ball's yellow, the one place it appears at full
   strength, so the eye reads a 25-23 differently from a 25-12 at a glance */
.set span.w{color:#3A2A00;background:var(--amber);font-weight:800}
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
.livehead b.justin{color:#12864B}
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

/* ---- bracket, drawn like the official one ---- */
.bwrap{overflow-x:auto;padding-bottom:6px;--bgame-h:62px;--bgame-gap:8px;
  position:relative;display:flex;gap:10px;align-items:flex-start}
/* Connectors are drawn behind everything and never intercept a click. */
.blines{position:absolute;left:0;top:0;pointer-events:none;z-index:0;
  color:var(--line2);overflow:visible}
.bwrap > .bhalf,.bwrap > .bfinal{position:relative;z-index:1}
/* Mirrored side: seed and score swap ends so the row reads outward-in, the way
   the right half of a printed bracket does. */
.bhalf.mirror .bside{flex-direction:row-reverse;text-align:right}
.bhalf.mirror .bhd{text-align:right;padding-right:2px}
.bhalf{display:flex;gap:10px;align-items:flex-start;min-width:940px}
.bcol{flex:1;min-width:168px;display:flex;flex-direction:column}
/* Every column's game area is the SAME height and distributes its games evenly,
   so a later round sits centred between the two games that feed it. That is
   what makes a bracket read as a bracket instead of five unrelated lists. */
.bgames{display:flex;flex-direction:column;justify-content:space-around;
  height:calc(16 * (var(--bgame-h) + var(--bgame-gap)))}
.bhd{font:700 9.5px/1 var(--sans);letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink2);padding:0 0 7px 2px}
.bgame{background:var(--card);border:1px solid var(--line);border-radius:7px;
  overflow:hidden;height:var(--bgame-h);box-sizing:border-box}
.bside{display:flex;align-items:center;gap:6px;padding:6px 8px;font-size:12.5px}
.bside+.bside{border-top:1px solid var(--line)}
/* the official bracket carries the whole story in one contrast: the winner is
   dark and bold, the loser is greyed. Everything else is chrome. */
.bside.won .bnm{font-weight:700;color:var(--ink)}
.bside.lost .bnm{color:var(--ink3)}
.bside.lost .bsc{color:var(--ink3)}
.bside.empty{opacity:.45}
.bsd{font:700 9.5px/1 var(--mono);color:var(--ink3);width:14px;text-align:right;
  flex:none}
.bnm{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bsc{font:700 12px/1 var(--mono);color:var(--navy);flex:none;min-width:10px;
  text-align:right}
.bfinal{min-width:210px;padding:0 12px;align-self:center;text-align:center}
.bfinal .bhd{text-align:center;padding-left:0}
.bchamp{font:700 9.5px/1 var(--sans);letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink2);margin:14px 0 7px}
.bcbox{background:var(--card);border:1px solid var(--line2);border-radius:7px;
  padding:14px 10px;font:700 14px/1 var(--sans);color:var(--ink3)}
@media(max-width:900px){.bhalf{min-width:820px}.bcol{min-width:150px}}

/* ---- full roster ---- */
.tsec--wide{margin-top:14px}
/* 5-1 / 6-2: how many setters the team actually starts. Shown only when its
   lineups agree; a team with thin position data gets no badge, not a guess. */
.wentto{display:block;font:600 10.5px/1 var(--sans);color:var(--ink3);margin-top:3px}
.tabhint{margin:0 0 12px;font-size:12.5px;color:var(--ink2)}
/* Digby speaks in his own box, never inline with measured numbers -- a reader
   should always be able to see which words were written and which were counted. */
.digby{background:var(--alt);border:1px solid var(--line);border-left:3px solid var(--amber);
  border-radius:2px;padding:12px 14px;margin:0 0 14px;max-width:760px}
/* Crests sit inline with the team name at text size -- a logo bigger than the
   word beside it reads as an advert, not a label. */
.tm .tlogo,.side .tlogo{width:18px;height:18px;object-fit:contain;vertical-align:-3px;
  margin-right:7px;flex:none}
.side .tlogo{vertical-align:-4px}
.t25 .tm .tlogo{width:22px;height:22px;vertical-align:-5px}
/* Team colour, used as an edge. Real school colours (373 of them, read out of
   the logos) turn a uniform table into something with a pulse -- and unlike a
   decorative palette it carries information you can check at a glance. */
.t25 .tm{position:relative;padding-left:14px}
.t25 .tm::before{content:"";position:absolute;left:6px;top:50%;transform:translateY(-50%);
  width:4px;height:24px;border-radius:2px;background:var(--tc,var(--line))}
.tstat{width:100%;border-collapse:collapse;max-width:520px}
.tstat th{font:500 11px/1 var(--disp);letter-spacing:.07em;text-transform:uppercase;
  color:var(--ink3);text-align:right;padding:6px 10px;border-bottom:1px solid var(--line);
  background:none;position:static}
.tstat th.l,.tstat td.l{text-align:left;color:var(--ink2);font:400 12.5px/1.3 var(--sans)}
.tstat td{padding:7px 10px;border-bottom:1px solid var(--line);
  font:700 14px/1 var(--mono);text-align:right}
.tstat td.op{color:var(--ink3)}
.tstat tr:last-child td{border-bottom:0}
/* SHARED TABLE TREATMENT. Applied to every data table so the site reads as one
   design -- the Top 25 was restyled first and everything else kept the old
   look, which is the worst of both. */
table th{font-family:var(--disp);font-weight:500;letter-spacing:.08em}
#rbody tr td:not(.tm),#sbody tr td:not(.tm){font-size:13.5px}
.panel table td{padding:11px 12px}
.panel table th{padding:11px 12px}
/* Team names carry the display face wherever they appear. */
td.tm,.bnm,.boxteam{font-family:var(--disp);font-weight:600;letter-spacing:.01em}
td.tm{font-size:15px}
/* The poll's names are deliberately larger -- it is the headline view, and
   hierarchy between views is not the same thing as inconsistency. */
.t25 td.tm{font-size:17px}
/* Digby's Top 25. A poll, so it reads as a list first and a table second. */
.t25{width:100%;border-collapse:collapse}
.t25 th{font:500 11px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink3);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);
  white-space:nowrap}
.t25 td{padding:12px 14px;border-bottom:1px solid var(--line);font-size:13.5px}
.t25 th{padding:10px 14px}
/* Rank, colour bar, crest and name were running into each other. The rank gets
   its own column width and the name cell starts clear of the bar. */
.t25 .rk{padding-right:6px}
.t25 .tm{padding-left:20px}
.t25 .tm .tlogo{margin-right:9px}
.t25 tbody tr:hover{background:var(--alt);cursor:pointer}
.t25 .rk{font:600 26px/1 var(--disp);color:var(--ink3);width:54px;font-variant-numeric:tabular-nums}
.t25 tbody tr:hover .rk{color:var(--navy)}
.t25 .tm{font:600 17px/1.1 var(--disp);letter-spacing:.01em}
.t25 .cf{color:var(--ink2);font-size:12px}
.t25 .rec{font:600 13px/1 var(--mono)}
.t25 .n{text-align:right;font:600 13px/1 var(--mono)}
.t25 .wt{color:var(--ink3)}
.mv-up{color:#12864B;font:700 11px/1 var(--mono)}
.mv-dn{color:#B3261E;font:700 11px/1 var(--mono)}
.mv-flat{color:var(--ink3);font:700 11px/1 var(--mono)}
.t25h{font:700 10.5px/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink3);margin:18px 0 8px}
.alsorx{font-size:13px;line-height:1.9;color:var(--ink);max-width:900px}
.arv{font:600 11px/1 var(--mono);color:var(--ink3)}
{{DIGBY_CSS}}.digby-tag svg{width:18px;height:18px;margin-right:5px}
.digby-tag{display:inline-flex;align-items:center}
.digby-tag{font:700 9.5px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink3);margin-bottom:7px}
.digby p{margin:0;font-size:14px;line-height:1.55;color:var(--ink)}
.digby-note{margin-top:8px;font-size:11.5px;color:var(--ink2)}
/* The rotation is a ring, so it is drawn as one row of six that wraps, not a
   list -- the shape carries the meaning that "after 6 comes 1 again". */
.rotgrid{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin:2px 0 10px;max-width:760px}
.rotcell{background:var(--alt);border:1px solid var(--line);border-top:2px solid var(--amber);
  border-radius:2px;padding:7px 6px;min-width:0}
.rotn{font:700 9px/1 var(--sans);color:var(--ink3);letter-spacing:.1em;margin-bottom:4px}
.rotnm{font:600 11.5px/1.25 var(--sans);color:var(--ink);overflow-wrap:anywhere}
.rotpos{font:600 9.5px/1 var(--sans);color:var(--ink3);margin-top:3px;letter-spacing:.06em}
@media (max-width:560px){.rotgrid{grid-template-columns:repeat(3,1fr)}}
{{ASK_CSS}}/* A season mismatch is the loudest thing on the view, because a 2025 table
   under a 2026 heading is the error that looks completely correct. */
.seasonwarn{background:var(--amber-bg);border:1px solid #E7CE96;border-left:4px solid var(--amber);
  border-radius:2px;padding:11px 13px;margin:0 0 12px;font-size:13px;color:#3A2A00;max-width:760px}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:3px;
  overflow:hidden;margin:0 0 14px;background:var(--card)}
.segb{appearance:none;border:0;background:transparent;font:700 11.5px/1 var(--sans);
  letter-spacing:.06em;text-transform:uppercase;color:var(--ink2);padding:9px 14px;
  cursor:pointer;border-right:1px solid var(--line)}
.segb:last-child{border-right:0}
.segb:hover{color:var(--ink)}
.segb.on{background:var(--navy);color:#fff}
.segb:focus-visible{outline:2px solid var(--amber);outline-offset:-2px}
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
.rrow{display:grid;grid-template-columns:28px 32px 1fr auto;grid-template-areas:
  "av num name stat" "av num meta stat";align-items:center;gap:0 8px;
  padding:7px 9px 7px 6px;border-left:3px solid transparent;
  border-bottom:1px solid var(--line);transition:background .12s ease}
.rrow:last-child{border-bottom:0}
.rrow:hover{background:var(--alt)}
/* A starter is marked by a bar rather than a fill: the fill was too faint to
   read, and the legend under the table names this bar explicitly. */
.rrow--starter{border-left-color:#12864B}
.rrow--starter .rname{font-weight:700}
.ravatar{grid-area:av;display:flex;align-items:center}
.ravatar svg{display:block;width:26px;height:26px}
.rmug{width:26px;height:26px;border-radius:50%;object-fit:cover;display:block;background:var(--alt)}
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
.boxwrap{margin-top:12px;border-top:1px solid var(--line);padding-top:12px;
  overflow-x:auto}
table.box{min-width:640px}
table.box td.pn{white-space:nowrap}
.box tr.btot td{border-top:2px solid var(--line2);font-weight:700;
  background:var(--alt);font-family:var(--mono)}
.box tr.btot .pn{font:600 12px/1 var(--disp);letter-spacing:.06em;
  text-transform:uppercase}
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
.thead h2{margin:0 0 4px;font:600 34px/1 var(--disp);letter-spacing:.005em}
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
    <button role="tab" aria-selected="false" data-v="top25">Digby&rsquo;s Top 25</button>
    <button role="tab" aria-selected="false" data-v="rankings">Rankings</button>
    <button role="tab" aria-selected="false" data-v="teams">Teams</button>
    <button role="tab" aria-selected="false" data-v="leaders">Stats</button>
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
  <div id="justin" hidden>
    <div class="livehead"><b class="justin">Just finished</b><span id="justinmeta"></span></div>
    <div class="cards" id="justincards"></div>
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
  <p class="lead"><b>2026 results.</b> Every completed match, newest first. The strip under each result is
  the <b>per-set score</b> &mdash; visitor on top, home below, the set winner lit.
  A 25&ndash;23 and a 25&ndash;12 are not the same match.</p>
  <div class="cards" id="sbody">{{SCORE_CARDS}}</div>
</section>

<section id="v-top25" hidden>
  <h2 class="vh">Digby&rsquo;s Top 25 &mdash; {{T25_SEASON}}</h2>
  <p class="tabhint">{{T25_LEAD}}</p>
  <div class="scroll"><table class="t25">
    <thead><tr>
      <th>#</th><th>Team</th><th title="how the rank changed">{{T25_MOVEHEAD}}</th>
      <th>Conf</th><th>Record</th>
      <th class="n" title="net points per set this season">Net/set</th>
      <th class="n" title="how much of the rating is this season rather than the preseason projection">This season</th>
    </tr></thead>
    <tbody id="t25body">{{T25_ROWS}}</tbody>
  </table></div>
  <h3 class="t25h">Also receiving votes</h3>
  <div class="alsorx">{{T25_ALSO}}</div>
  <p class="tabhint">{{T25_FOOT}}</p>
</section>

<section id="v-rankings" hidden>
  <div class="seg" role="tablist" aria-label="Which ranking">
    <button class="segb on" data-r="ours">Our 2026</button>
    <button class="segb" data-r="avca">AVCA poll</button>
    <button class="segb" data-r="top16">Committee top 16</button>
    <button class="segb" data-r="rpi">NCAA RPI</button>
  </div>
  <div id="pollview" hidden></div>
  <p class="lead" id="ranklead">{{RANK_BASIS}} The other columns are
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
  <h2 class="vh">2026 stats</h2>
  <div class="seg" role="tablist" aria-label="Player or team stats">
    <button class="segb on" data-ls="player">Players</button>
    <button class="segb" data-ls="team">Teams</button>
  </div>
  <p class="lead" id="lplead"><b>2026 season</b> leaders, <b>per set</b> rather than totals &mdash; totals just rank
  whoever has played most. A player needs {{LDR_FLOOR}} sets to qualify; that minimum rises
  with the season.</p>
  <p class="lead" id="ltlead" hidden><b>2026 team stats</b>, per set, from the box scores.
  <b>Allowed</b> is the same count from the other side of the same matches &mdash; what this
  team's opponents managed against it. Everything here is a handful of matches so far;
  the match count is in the table.</p>
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
    <select id="lside" hidden>
      <option value="own">This team</option>
      <option value="opp">Allowed to opponents</option>
    </select>
    <span class="count" id="lcnt"></span>
  </div>
  <div class="panel" id="lplayer"><div class="scroll"><table>
    <thead><tr><th>#</th><th class="l">Player</th><th class="l">Team</th><th>Pos</th>
      <th>Sets</th><th id="lhead">Pts/set</th></tr></thead>
    <tbody id="lbody"></tbody></table></div>
    <div class="note">Hitting percentage needs at least 20 swings before it means
    anything, so a player below that shows an em dash rather than a number built on
    four attempts.</div>
  </div>
  <div class="panel" id="lteam" hidden><div class="scroll"><table>
    <thead><tr><th>#</th><th class="l">Team</th><th class="l">Conf</th>
      <th>M</th><th>Sets</th><th id="lthead">Pts/set</th></tr></thead>
    <tbody id="ltbody"></tbody></table></div>
    <div class="note">Team rates come from the same box scores as the player
    numbers, so they agree by construction. <b>Points</b> are kills + blocks +
    aces. A team is listed once it has a box score on file.
    <b>Every opponent counts, including non-Division-I ones</b> &mdash; nothing is
    filtered out, so a team that has played a Division-II side will look better
    than it is. With this few matches, read the <b>M</b> column before the rate.</div>
  </div>
</section>

<section id="v-standings" hidden>
  <p class="lead"><b>2026 standings.</b> Conference tables, filling in as results land. Conference record first,
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
      it can go to anyone who wins it. {{AQ_MECH}}</p>
      <p>Seeding here is our order, not a committee&rsquo;s. The committee seeds on resume
      &mdash; RPI, record against the top 25 and 50, head to head &mdash; and our field
      projector, which reproduced 62 of the actual 64 for 2025, needs played matches
      before it can run. It takes over once there are results.</p>
    </div>
  </div>
</section>

<section id="v-schedule" hidden>
  <p class="lead"><b>2026 schedule.</b> {{N_SCHED}} fixtures from today forward, straight from ncaa.com.</p>
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
  <p class="lead"><b>2026 broadcasts.</b> {{N_TV}} nationally televised matches, transcribed from VolleyTalk
  &mdash; not verified against the networks.</p>
  <div class="ctl">
    <input type="search" id="tq" placeholder="Search team or network&hellip;">
    <span class="count" id="tcnt"></span>
  </div>
  <div class="panel"><div class="scroll"><table>
    <thead><tr><th class="l">Date</th><th class="l">Matchup</th>
      <th class="l">Network</th><th>Time PT</th></tr></thead>
    <tbody id="tbody">{{TV_ROWS}}</tbody></table></div></div>
</section>

</main>
{{ASK_HTML}}
<script>
const CONFS = {{CONF_JSON}};
const $ = s => document.querySelector(s);

/* tabs */
/* Drive the sliding underline. Measured from the button rather than guessed,
   so it stays right when the tabs wrap to a second row on a narrow screen. */
function moveNavBar() {
  const inner = document.querySelector('nav .inner');
  const on = document.querySelector('nav button[aria-selected=true]');
  if (!inner || !on) return;
  const p = inner.getBoundingClientRect();
  const r = on.getBoundingClientRect();
  inner.style.setProperty('--barw', r.width + 'px');
  inner.style.setProperty('--barx', (r.left - p.left) + 'px');
}
addEventListener('resize', moveNavBar);
addEventListener('load', moveNavBar);
document.fonts && document.fonts.ready.then(moveNavBar);   /* the face changes the widths */

document.querySelectorAll('nav button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach(x => x.setAttribute('aria-selected', x === b));
  moveNavBar();
  document.querySelectorAll('main section').forEach(s => { s.hidden = true; });
  $('#v-' + b.dataset.v).hidden = false;
  /* The bracket redraws itself when it becomes visible -- see the observer
     below. Hooking the tab click was a proxy for that and kept missing. */
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
/* A row in the Top 25 opens that team, the same as clicking it anywhere else --
   a ranking you cannot click through from is a dead end. */
const t25body = document.getElementById('t25body');
if (t25body) t25body.addEventListener('click', e => {
  const tr = e.target.closest('tr[data-team]'); if (!tr) return;
  const nm = tr.dataset.team;
  if (!TEAMS[nm]) return;
  document.querySelector('nav button[data-v="teams"]').click();
  const q = document.getElementById('tmq'); if (q) q.value = nm;
  showTeam(nm);
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
  /* A match that has ENDED must leave the live band even while the feed still
     reports it in progress. The scoreboard flips `period` to FINAL before the
     state field catches up, so for a few minutes the band showed a card headed
     LIVE whose own first line said FINAL. Trust whichever source says it is
     over. */
  const isOver = g => /final|complete/i.test(g.period || '') ||
                      /final|^f$/i.test(g.state || '');
  const live = all.filter(g => LIVE_STATES.includes(g.state) && !isOver(g));
  const justEnded = all.filter(isOver);

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
      '<div class="mt"><div class="side">' + rank(g.away_rank) + logo(g.away) + g.away + '</div>' +
      '<div class="side">' + rank(g.home_rank) + logo(g.home) + g.home + '</div></div>' +
      '<div class="venue"><span class="tipoff">' + (g.time || 'time TBA') + '</span></div>' +
      '</div>').join('');
  }

  /* JUST FINISHED, not yet crawled. Rendered from the feed so a match is never
     invisible: it leaves the live band the moment the scoreboard says FINAL,
     but the results list below is built from the last crawl and will not carry
     it until the next one runs. Without this it falls between the two. */
  const jbox = document.getElementById('justin');
  if (jbox) {
    const known = new Set([...document.querySelectorAll('#sbody [data-gid]')]
      .map(el => el.dataset.gid));
    const fresh = justEnded.filter(g => !known.has(String(g.id)));
    if (!fresh.length) { jbox.hidden = true; }
    else {
      jbox.hidden = false;
      document.getElementById('justinmeta').textContent =
        fresh.length + (fresh.length === 1 ? ' result' : ' results') +
        ' \u2014 not yet in the archive below';
      document.getElementById('justincards').innerHTML = fresh.map(g => {
        const aw = +g.away_sets > +g.home_sets;
        return '<div class="card done"><div class="cd">' + (g.date || '') +
          ' \u00b7 final</div><div class="mt">' +
          '<div class="side' + (aw ? ' win' : '') + '">' + rank(g.away_rank) +
            logo(g.away) + g.away + '<b>' + g.away_sets + '</b></div>' +
          '<div class="side' + (aw ? '' : ' win') + '">' + rank(g.home_rank) +
            logo(g.home) + g.home + '<b>' + g.home_sets + '</b></div></div>' +
          setStrip(g.sets, false) +
          '<div class="venue">' + (g.venue || 'venue not reported') + '</div></div>';
      }).join('');
    }
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
        rank(g.away_rank) + logo(g.away) + g.away + '<b>' + g.away_sets + '</b></div>' +
      '<div class="side' + (aw ? '' : ' win') + '">' +
        rank(g.home_rank) + logo(g.home) + g.home + '<b>' + g.home_sets + '</b></div></div>' +
      setStrip(g.sets, true) +
      '<div class="venue">' + venue + '</div></div>';
  }).join('');
}
pollLive();
setInterval(pollLive, 60000);


/* ---- logos, box scores, player pages ---------------------------------- */
const LOGOS = {{LOGOS_JSON}};
const COLORS = {{COLORS_JSON}};
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
      (function () {
        const t = teamTotals(rs);
        return '<tr class="btot"><td class="pn">Team</td><td></td>' +
          '<td>' + t.sets + '</td><td>' + t.k + '</td><td>' + t.e + '</td>' +
          '<td>' + t.ta + '</td><td>' + pct(t.hit) + '</td><td>' + t.ast + '</td>' +
          '<td>' + t.digs + '</td><td>' + t.blk + '</td>' +
          '<td>' + t.aces + '</td><td>' + t.pts + '</td></tr>';
      })() +
      '</tbody></table>';
  }
  return out + '</div>';
}
/* TEAM TOTALS for one side of a box score.
   Hitting % is computed from the SUMMED raw counts -- (K-E)/TA -- never by
   averaging the players' percentages, which weights a libero's one swing the
   same as an outside's thirty. Blocks follow the NCAA convention: a solo is
   one, an assist is a half. Sets are the MATCH's sets, not the sum of the
   players' (six players on court means that sum is ~6x the truth). */
function teamTotals(rs) {
  const t = {k:0, e:0, ta:0, ast:0, digs:0, bs:0, ba:0, aces:0, pts:0, sets:0};
  rs.forEach(r => {
    t.k += r.k || 0; t.e += r.e || 0; t.ta += r.ta || 0; t.ast += r.ast || 0;
    t.digs += r.digs || 0; t.bs += r.bs || 0; t.ba += r.ba || 0;
    t.aces += r.aces || 0; t.pts += r.pts || 0;
    t.sets = Math.max(t.sets, r.sets || 0);
  });
  t.hit = t.ta ? (t.k - t.e) / t.ta : null;
  t.blk = t.bs + t.ba * 0.5;
  return t;
}
document.querySelector('#v-scores').addEventListener('click', e => {
  const card = e.target.closest('.card');
  if (!card || !card.dataset.gid) return;
  let box = card.querySelector('.boxwrap');
  if (box) { box.remove(); card.classList.remove('open'); return; }
  /* one open at a time: two full-width box scores stacked is just scrolling */
  document.querySelectorAll('#v-scores .card.open').forEach(c => {
    const b = c.querySelector('.boxwrap'); if (b) b.remove();
    c.classList.remove('open');
  });
  card.classList.add('open');
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

  /* THE REAL SHAPE, drawn the way the official bracket draws it.
     64 -> 32 -> 16 -> 8 -> 4 -> 2 -> 1, which the NCAA labels First round,
     Second round, Third round (Sweet 16), Quarterfinals (Elite Eight),
     Semifinals, Championship. Split into two halves with the title match
     between them, because one column of 32 games is unreadable.

     WHAT IS REAL AND WHAT IS NOT: the first-round PAIRINGS are implied by the
     seed order -- seed N against the Nth-from-last unseeded team -- and are NOT
     the committee's bracketing, which also weighs geography. Every later round
     is left EMPTY. That is not a gap; an unplayed bracket has empty later
     rounds, and filling them with projected matchups would be inventing
     results (R5). They populate as matches are played. */
  const seeded = seeds.slice(0, 32), rest = seeds.slice(32);
  const games = seeded.map((s2, i) => [s2, rest[rest.length - 1 - i]].filter(Boolean));

  const side = (t, cls) => {
    if (!t) return '<div class="bside empty"><span class="bsd"></span>' +
                   '<span class="bnm">&nbsp;</span><span class="bsc"></span></div>';
    return '<div class="bside ' + (cls || '') + '">' +
      /* unseeded teams show NO number -- not a zero, not a dash, exactly as the
         official bracket prints them */
      '<span class="bsd">' + (t.seed && t.seed <= 32 ? t.seed : '') + '</span>' +
      logo(t.team) + '<span class="bnm">' + t.team + '</span>' +
      '<span class="bsc">' + (t.sets === undefined ? '' : t.sets) + '</span></div>';
  };
  const game = g => '<div class="bgame">' + side(g && g[0]) + side(g && g[1]) + '</div>';
  const blanks = n => Array.from({length: n}, () => game(null)).join('');

  const col = (head, inner) =>
    '<div class="bcol"><div class="bhd">' + head + '</div>' +
    '<div class="bgames">' + inner + '</div></div>';
  /* The right half is MIRRORED. Both halves used to run first-round-to-semifinal
     left to right, which put the right side's semifinal at the far edge and the
     championship in the middle -- so that half flowed AWAY from the final. A
     real bracket converges. */
  const half = (gs, mirror) => {
    const cols = [
      col('First round', gs.map(game).join('')),
      col('Second round', blanks(8)),
      col('Third round', blanks(4)),
      col('Quarterfinals', blanks(2)),
      col('Semifinal', blanks(1)),
    ];
    if (mirror) cols.reverse();
    return '<div class="bhalf' + (mirror ? ' mirror' : '') + '">' + cols.join('') + '</div>';
  };

  host.innerHTML =
    '<div class="bwrap">' +
      half(games.slice(0, 16), false) +
      '<div class="bfinal"><div class="bhd">Championship</div>' + game(null) +
        '<div class="bchamp">2026 national champion</div>' +
        '<div class="bcbox">&mdash;</div></div>' +
      half(games.slice(16), true) +
    '</div>' +
    '<p class="tnote">First-round pairings are <b>implied by seed order</b>, not the ' +
    'committee\u2019s bracket \u2014 it also weighs geography, and nothing has been ' +
    'announced. Later rounds are <b>empty on purpose</b>: they fill in as matches are ' +
    'played rather than being guessed.</p>';
}

/* ---- published polls: the AVCA coaches poll and the NCAA RPI, as published,
   so the page answers the question without sending anyone to another site ---- */
const POLLS = {{POLLS_JSON}};
function renderPoll(which) {
  const host = document.getElementById('pollview');
  const main = document.querySelector('#v-rankings .panel');
  const lead = document.getElementById('ranklead');
  document.querySelectorAll('#v-rankings .segb').forEach(b =>
    b.classList.toggle('on', b.dataset.r === which));
  if (which === 'ours') {
    host.hidden = true; main.hidden = false; lead.hidden = false; return;
  }
  const p = POLLS[which];
  main.hidden = true; lead.hidden = true; host.hidden = false;
  if (!p) {
    host.innerHTML = '<div class="tnote">No capture of this ranking yet. It is ' +
      'collected daily; the source publishes only its current version, so there ' +
      'is nothing to show until the next publication.</div>';
    return;
  }
  const cols = Object.keys(p.rows[0]);
  /* "final" is only true of a table published at the END of a season. The
     committee's Top 16 is a MID-season reveal, so the warning names the stamp
     rather than asserting a finality it does not have. */
  const stale = p.prev
    ? '<div class="seasonwarn"><b>This is ' + p.season + ', not this season.</b> ' +
      'Last published ' + (p.stamp || 'in ' + p.season) + '. The source serves only ' +
      'its current version, and it stays on ' + p.season + ' until enough ' +
      (p.season + 1) + ' matches have been played for a new one. Kept as ' +
      'reference, labelled.</div>'
    : '';
  host.innerHTML = stale +
    '<div class="panel"><div class="scroll"><table><thead><tr>' +
      cols.map((c, i) => '<th' + (i === 1 ? ' class="l"' : '') + '>' + c + '</th>').join('') +
    '</tr></thead><tbody>' +
      p.rows.map(r => '<tr class="row">' + cols.map((c, i) =>
        '<td' + (i === 1 ? ' class="tm"' : ' class="n"') + '>' + (r[c] === '' ? '&mdash;' : r[c]) +
        '</td>').join('') + '</tr>').join('') +
    '</tbody></table></div>' +
    '<div class="note"><p><b>' + (p.title || '') + '</b> as published, ' +
    (p.stamp ? '<b>' + p.stamp + '</b>, ' : '') + 'captured ' + (p.captured || '') +
    '. ' +
    (which === 'top16'
      ? 'This is the <b>selection committee\u2019s own</b> in-season reveal &mdash; ' +
        'the closest published thing to the judgement our projected bracket is ' +
        'trying to anticipate. It appears only late in the season. '
      : '') +
    (which === 'avca'
      ? 'A number in brackets after a school is its first-place votes. ' : '') +
    'This is a reference ranking &mdash; nothing here feeds our model.</p></div></div>';
}
document.querySelectorAll('#v-rankings .segb').forEach(b =>
  b.addEventListener('click', () => renderPoll(b.dataset.r)));

/* ---- leaders ---- */
const LEADERS = {{LEADERS_JSON}};
const TSTATS = {{TSTATS_JSON}};
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
/* TEAM STATS, the other half of the Stats tab. Same box scores as the player
   numbers, so the two agree by construction. "Allowed" is the identical count
   from the other side of the same matches -- the defensive view most sites do
   not show, and it costs nothing because every box score carries both teams. */
function renderTeamStats() {
  const q = document.getElementById('lq').value.toLowerCase().trim();
  const k = document.getElementById('lstat').value;
  const side = document.getElementById('lside').value;
  document.getElementById('lthead').textContent =
    LSTAT[k] + (side === 'opp' ? ' allowed' : '');
  /* For everything except hitting percentage, "allowed" is better when it is
     LOWER -- so the sort flips, or the table would rank the worst defence
     first and look like a bug. */
  const asc = side === 'opp';
  const rows = TSTATS
    .filter(r => r[side] && r[side][k] !== null && r[side][k] !== undefined)
    .filter(r => !q || (r.team + ' ' + (r.conf || '')).toLowerCase().includes(q))
    .sort((a, b) => asc ? a[side][k] - b[side][k] : b[side][k] - a[side][k]);
  document.getElementById('ltbody').innerHTML = rows.map((r, i) => {
    const d = r[side];
    return '<tr><td class="rk">' + (i + 1) + '</td>' +
      '<td class="tm">' + logo(r.team) + r.team + '</td>' +
      '<td class="cf">' + (r.conf || '') + '</td>' +
      '<td class="n">' + d.matches + '</td><td class="n">' + d.sets + '</td>' +
      '<td class="n hi">' + (k === 'hit' ? d.hit.toFixed(3) : d[k].toFixed(2)) +
      '</td></tr>';
  }).join('');
  document.getElementById('lcnt').textContent = rows.length + ' teams';
}

let LSIDE = 'player';
function renderStats() {
  const team = LSIDE === 'team';
  document.getElementById('lplayer').hidden = team;
  document.getElementById('lteam').hidden = !team;
  document.getElementById('lplead').hidden = team;
  document.getElementById('ltlead').hidden = !team;
  document.getElementById('lside').hidden = !team;
  document.getElementById('lq').placeholder =
    team ? 'Search team or conference\u2026' : 'Search player or team\u2026';
  if (team) renderTeamStats(); else renderStats();
}
document.querySelectorAll('#v-leaders .segb').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('#v-leaders .segb').forEach(x => x.classList.toggle('on', x === b));
    LSIDE = b.dataset.ls;
    renderStats();
  }));
['lq','lstat','lside'].forEach(id =>
  document.getElementById(id).addEventListener('input', renderStats));
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

/* PLAYER AVATARS. Pose = her real position, colour = her school's own logo
   colour. Shown only where there is NO photograph -- a real picture always
   wins. Nothing here claims anything about the person: no face, no hair, no
   skin tone. The libero is drawn in the accent because the rules require a
   contrasting jersey, which is the one thing the picture actually tells you.
   Shapes are generated from scripts/avatars.py so the preview sheet and this
   page cannot drift. */
const AV = {"poses":{"S":{"body":"<circle cx=\"20\" cy=\"13\" r=\"3.9\"/><path d=\"M20 17.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M16.6 19.6 14.6 12.8M23.4 19.6l2-6.8\"/>","hands":[[14.2,11.8],[25.8,11.8]],"ball":[20,7.6,3.2]},"MB":{"body":"<circle cx=\"20\" cy=\"15\" r=\"3.9\"/><path d=\"M20 19.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M14.4 22.4 13.6 9.6M25.6 22.4l.8-12.8\"/>","hands":[[13.4,8.4],[26.6,8.4]],"ball":null},"OH":{"body":"<circle cx=\"21.5\" cy=\"14\" r=\"3.9\"/><path d=\"M21.5 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M25 20.4 30 13.4\"/><path d=\"M18 21.4 10.8 25.4\"/>","hands":[[30.6,12.4],[9.8,26]],"ball":[32.4,7.4,2.9]},"L/DS":{"body":"<circle cx=\"23\" cy=\"15.5\" r=\"3.9\"/><path d=\"M23 20c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M19.8 22.8 10.4 28.4M25.6 23.4 10.4 28.4\"/>","hands":[[9.4,29]],"ball":null},"OPP":{"body":"<circle cx=\"21.5\" cy=\"14\" r=\"3.9\"/><path d=\"M21.5 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M25 20.4 30 13.4\"/><path d=\"M18 21.4 10.8 25.4\"/>","hands":[[30.6,12.4],[9.8,26]],"ball":[32.4,7.4,2.9]},"RS":{"body":"<circle cx=\"21.5\" cy=\"14\" r=\"3.9\"/><path d=\"M21.5 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M25 20.4 30 13.4\"/><path d=\"M18 21.4 10.8 25.4\"/>","hands":[[30.6,12.4],[9.8,26]],"ball":[32.4,7.4,2.9]},"DS":{"body":"<circle cx=\"23\" cy=\"15.5\" r=\"3.9\"/><path d=\"M23 20c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M19.8 22.8 10.4 28.4M25.6 23.4 10.4 28.4\"/>","hands":[[9.4,29]],"ball":null},"L":{"body":"<circle cx=\"23\" cy=\"15.5\" r=\"3.9\"/><path d=\"M23 20c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M19.8 22.8 10.4 28.4M25.6 23.4 10.4 28.4\"/>","hands":[[9.4,29]],"ball":null}},"unknown":{"body":"<circle cx=\"20\" cy=\"14\" r=\"3.9\"/><path d=\"M20 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M16.4 21.6 13.4 27.4M23.6 21.6l3 5.8\"/>","hands":[],"ball":null},"libero":["L/DS","L","DS"],"neutral":"#9A8F7D","onNeutral":"#FFFFFF"};
function avatar(pos, team, size) {
  const c = (COLORS && COLORS[team]) || {};
  let bg = c.primary || AV.neutral, ink = c.on_primary || AV.onNeutral;
  if (AV.libero.indexOf(pos) >= 0) {
    bg = c.accent || bg; ink = c.on_accent || ink;
  }
  const p = AV.poses[pos] || AV.unknown;
  const hands = (p.hands || []).map(h =>
    '<circle cx="' + h[0] + '" cy="' + h[1] + '" r="1.9"/>').join('');
  const ball = p.ball
    ? '<circle cx="' + p.ball[0] + '" cy="' + p.ball[1] + '" r="' + p.ball[2] +
      '" fill="' + bg + '" stroke="' + ink + '" stroke-width="1.6"/>' : '';
  return '<svg viewBox="0 0 40 40" width="' + size + '" height="' + size +
    '" class="mug pav" aria-hidden="true" focusable="false">' +
    '<circle cx="20" cy="20" r="20" fill="' + bg + '"/>' +
    '<g fill="' + ink + '">' + p.body + hands + '</g>' +
    '<g fill="none" stroke="' + ink + '" stroke-width="2.5" stroke-linecap="round">' +
    p.limbs + '</g>' + ball + '</svg>';
}
  const initials = n => n.split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
  const six = (t.rotation || []).map(c =>
    '<div class="plrow">' +
    (c.photo ? '<img class="mug" src="' + c.photo + '" alt="" ' +
               'onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),' +
               '{className:\'mug mug--none\',textContent:\'' + initials(c.name) + '\'}))">'
             : avatar(c.pos, name, 34)) +
    '<span class="nm">' + c.name + '</span>' +
    '<span class="kd">' + (c.pos ? c.pos + ' \u00b7 ' : '') + c.kind +
    (c.kind === 'transfer' && c.from ? ' \u00b7 ' + c.from : '') +
    '</span><span class="rt">' + (c.adj !== undefined ? c.adj : c.rate) + '</span></div>').join('');
  const DIGBY_FACE = {{DIGBY_FACE_JS}};
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
        /* 2026 IS THE SEASON BEING WATCHED, so it takes the headline as soon
           as a player has played a real share of it -- the same qualifying rule
           the leaderboard uses, so there is one definition. Until then the
           headline is last season, and either way the number is LABELLED with
           its year: an unlabelled "pts/set" drifts away from its heading the
           moment results pile up (R4). */
        const live = r.live_primary && r.l26 && r.l26.r !== null;
        const stat = live
          ? r.l26.r + '<em>2026 pts/set</em>'
          : ((r.r !== null && r.r !== undefined)
              ? r.r + '<em>' + (r.k === 'transfer' ? '2025 elsewhere' : '2025 pts/set') + '</em>'
              : '<span class="none">&mdash;</span>');
        const sub = [];
        if (r.c) sub.push(r.c);
        if (r.praw) sub.push(r.praw);
        if (r.st) sub.push('started ' + r.st +
          (lu && lu.matches_with_lineup ? ' of ' + lu.matches_with_lineup : ''));
        /* only when 2025 is not already spelled out below as context */
        if (r.sets && !live) sub.push(r.sets + ' sets in 2025');
        if (KIND_TAG[r.k]) sub.push(KIND_TAG[r.k] + (r.k === 'transfer' && r.from ? ' from ' + r.from : ''));
        /* THE SAMPLE SIZE TRAVELS WITH THE RATE. When 2026 takes the headline
           it may be four sets old; a rate without its denominator in August
           reads like an established number and is not one. Last season stays
           visible underneath as the larger sample. */
        if (r.l26) sub.push('<b>2026: ' + r.l26.sets + ' set' +
          (r.l26.sets === 1 ? '' : 's') + '</b>');
        if (live && r.r !== null && r.r !== undefined)
          sub.push('2025: ' + r.r + ' pts/set over ' + (r.sets || 0) + ' sets');
        rosterHtml += '<div class="rrow' + (r.st ? ' rrow--starter' : '') + '">' +
          '<span class="ravatar">' + (r.ph
             ? '<img class="rmug" src="' + r.ph + '" alt="" loading="lazy" ' +
               'onerror="this.replaceWith(document.createRange()' +
               '.createContextualFragment(this.dataset.fb))" data-fb=\'' +
               avatar(r.p, name, 26) + '\'>'
             : avatar(r.p, name, 26)) + '</span>' +
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
  /* SERVING ROTATION, 2025. A team serves in rotation order by rule, so the
     order its players take the serve IS the rotation -- derived, not inferred.
     Shown with how many sets agree, because a team runs several across a
     season and a single "the rotation" would overstate it. */
  /* TEAM STATS, 2026 -- what they do beside what they ALLOW. Showing only the
     offence is half a team, and the opponent column comes free because every
     box score carries both sides. Rates are per SET, and the sample is stated
     next to them: three sets in August is not a season, and a rate without its
     denominator reads like an established number. */
  /* POSTSEASON. Two honest jobs: say how this conference awards its automatic
     bid, and say what the win projection does and does not count. It counts
     SCHEDULED fixtures only -- no conference tournament (those are not on the
     feed until November) and no bracketed in-season tournament match whose
     opponent is still undecided, which is why Kentucky's Paradise Invitational
     shows one match and not two. So the projection is a FLOOR for teams in
     those events, and the page says so rather than letting the number imply a
     completeness it does not have. */
  /* NO 2026 SCHEDULE AT ALL. Saint Francis is carried here because it was
     Division I in 2025 (official RPI, 20-9) and the D-I list comes from that
     table -- but the 2026 feed does not contain it in a single fixture, and
     already served it as division 3 in 2025. So the page shows a 2025 team
     with no 2026 anywhere, and without a word of explanation that reads like a
     bug in the site rather than a fact about the programme. The simulator
     already declines to project it; this says why. */
  let goneHtml = '';
  if (t.sched_n === 0) {
    goneHtml =
      '<div class="seasonwarn"><b>No 2026 Division-I schedule.</b> ' +
      'This programme does not appear in a single 2026 fixture on the feed, ' +
      'and the feed already listed it outside Division I in 2025. It is here ' +
      'because Division-I membership is taken from the 2025 official RPI table, ' +
      'where it went 20\u20139. Everything below is <b>2025</b>; there are no ' +
      '2026 projections because there is nothing to project.</div>';
  }
  const aq = t.aq;
  let postHtml = '';
  if (aq) {
    const tourn = aq.mechanism === 'TOURNAMENT';
    const sim = t.sim || {};
    postHtml =
      '<div class="tsec" style="margin-top:14px"><h3>Postseason</h3>' +
      '<div class="body">' +
      '<div class="plrow"><span class="nm">' + (t.conf || 'Conference') +
        ' automatic bid<span class="wentto">' +
        (tourn ? 'won by the conference tournament'
               : 'goes to the regular-season champion') + '</span></span>' +
      '<span class="kd">' + (tourn ? 'tournament' : 'regular season') + '</span></div>' +
      (sim.tournament_pct !== undefined && sim.tournament_pct !== null
        ? '<div class="plrow"><span class="nm">NCAA tournament<span class="wentto">' +
          'our simulated chance of making the 64</span></span>' +
          '<span class="rt">' + sim.tournament_pct + '%</span></div>' : '') +
      (sim.conf_title_pct !== undefined && sim.conf_title_pct !== null
        ? '<div class="plrow"><span class="nm">Conference title<span class="wentto">' +
          (tourn ? 'regular-season finish, not the tournament'
                 : 'which is the automatic bid here') + '</span></span>' +
          '<span class="rt">' + sim.conf_title_pct + '%</span></div>' : '') +
      '</div>' +
      '<div class="tnote">' +
      (aq.detail ? aq.detail.charAt(0).toUpperCase() + aq.detail.slice(1) + '. ' : '') +
      (aq.evidence_season === 2025
        ? '<b>That is 2025 evidence</b> \u2014 a league that changes format for 2026 ' +
          'without announcing it would be wrong here. ' : '') +
      '<b>Projected wins counts the ' + (t.sched_n || 0) + ' matches currently on ' +
      'the schedule</b> \u2014 not the conference tournament, and not a bracketed ' +
      'in-season tournament match whose opponent is undecided (those appear only ' +
      'once the pairing is set). Read it as a floor.</div></div>';
  }
  const ts = t.tstats;
  let statHtml = '';
  if (ts && ts.own && ts.own.sets) {
    const O = ts.own, D = ts.opp;
    const rowsOf = [
      ['Points / set', O.pps, D.pps, 'n2',
       'kills + blocks + aces \u2014 the box-score definition'],
      ['Hitting %',   O.hit,  D.hit,  'pct', 'higher is better; opponent lower is better'],
      ['Kills / set', O.kps,  D.kps,  'n2',  ''],
      ['Assists / set', O.asps, D.asps, 'n2',  ''],
      ['Digs / set',  O.dps,  D.dps,  'n2',  ''],
      ['Blocks / set', O.bps, D.bps,  'n2',  'a solo counts one, an assist a half'],
      ['Aces / set',  O.aps,  D.aps,  'n2',  ''],
    ];
    const f = (v, kind) => v === null || v === undefined ? '&mdash;'
      : (kind === 'pct' ? (v < 0 ? '-' : '') + Math.abs(v).toFixed(3).replace(/^0/, '')
                        : v.toFixed(2));
    statHtml =
      '<div class="tsec" style="margin-top:14px"><h3>Team stats, 2026</h3>' +
      '<table class="tstat"><thead><tr><th class="l"></th>' +
      '<th>' + name + '</th><th>Opponents</th></tr></thead><tbody>' +
      rowsOf.map(r => '<tr' + (r[4] ? ' title="' + r[4] + '"' : '') + '>' +
        '<td class="l">' + r[0] + '</td>' +
        '<td class="n">' + f(r[1], r[3]) + '</td>' +
        '<td class="n op">' + f(r[2], r[3]) + '</td></tr>').join('') +
      '</tbody></table>' +
      '<div class="tnote"><b>Points</b> are kills + blocks + aces, the ' +
      'box-score definition &mdash; ' + O.earned + ' of them here. ' +
      'From the box scores of <b>' + O.matches +
      (O.matches === 1 ? ' match' : ' matches') + '</b> (' + O.sets +
      ' sets). Totals: ' + O.kills + ' kills on ' + O.attacks + ' attacks with ' +
      O.errors + ' errors. <b>Opponents</b> is what this team allowed &mdash; ' +
      'the same counts from the other side of the same box scores.</div></div>';
  }
  const rt = t.rot25;
  let rotHtml = '';
  if (rt && rt.rotation && rt.rotation.length === 6) {
    const posOf = {};
    ((t.lineup || {}).usual_six_2025 || []).forEach(p => { posOf[p.name] = p.pos; });
    const cells = rt.rotation.map((n, i) =>
      '<div class="rotcell"><div class="rotn">' + (i + 1) + '</div>' +
      '<div class="rotnm">' + n + '</div>' +
      '<div class="rotpos">' + (posOf[n] || '\u2014') + '</div></div>').join('');
    const subs = (rt.substitutions || []).slice(0, 4).map(x =>
      '<div class="plrow"><span class="nm">' + x.sub +
      '<span class="wentto">for ' + x.starter + '</span></span>' +
      '<span class="rt">' + x.sets + ' sets</span></div>').join('');
    const back = ((t.lineup || {}).usual_six_2025 || [])
      .filter(p => p.status_2026 === 'returning').map(p => p.name);
    rotHtml =
      '<div class="tsec" style="margin-top:14px"><h3>Serving rotation, 2025</h3>' +
      '<div class="rotgrid">' + cells + '</div>' +
      '<div class="tnote">Read left to right and wrap around \u2014 after 6 comes 1 again. ' +
      'Whoever serves stands at position 1; the next three to serve are the ' +
      '<b>front row</b>. So when ' + rt.rotation[0] + ' serves, ' +
      rt.rotation.slice(1, 4).join(', ') + ' are at the net.<br>' +
      '<b>' + rt.sets_with_this_rotation + ' of ' + rt.sets_resolved +
      ' sets</b> used this exact order (' + Math.round(rt.agreement * 100) + '%), across ' +
      rt.distinct_rotations + ' the team used in all \u2014 lineups move over a season.<br>' +
      '\u26a0 This is the <b>serving</b> six, not the six on court: a libero replaces a ' +
      'middle as she rotates to the back row, which is where the serve is, so middles ' +
      'often never appear here.<br>' +
      'Source: NCAA play-by-play, via the <b>ncaavolleyballr</b> dataset ' +
      '(J. R. Stevens, MIT). Rotation derived here.</div>' +
      (subs ? '<h3 style="margin-top:12px">Who came in for whom</h3><div class="body">' +
              subs + '</div><div class="tnote">A substitute serves from the slot of the ' +
              'player she replaced, so these pairings are read off the rotation rather ' +
              'than guessed.</div>' : '') +
      '</div>';
  }
  box.innerHTML =
    goneHtml +
    (t.digby
      ? '<div class="digby"><div class="digby-tag">' + DIGBY_FACE + 'Digby</div>' +
        '<p>' + t.digby + '</p>' +
        '<div class="digby-note">Written from this team\u2019s own numbers on ' +
        'this page. Every figure in it was checked against the source before it ' +
        'was saved \u2014 anything that did not match was thrown away rather ' +
        'than shown.</div></div>'
      : '') +
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
             ' Listed by matches started.</div></div>' : '') +
        statHtml +
        postHtml +
        rotHtml +
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


/* BRACKET CONNECTORS. Drawn as one SVG behind the cards, from the MEASURED
   position of every box rather than from assumptions about the layout -- the
   columns distribute with space-around inside a scrolling box, so the maths for
   "where does round 3 sit" is the browser's job, not mine. Redrawn on resize
   and whenever the tab is opened, because a box measured while its section is
   `hidden` has no size at all. */
function drawBracketLines(tries) {
  const wrap = document.querySelector('#brkview .bwrap');
  if (!wrap) return;
  /* A box inside a hidden section measures as zero. Rather than trying to catch
     the exact frame after the section is revealed -- three attempts, three
     misses -- notice the zero and come back. */
  if (!wrap.getBoundingClientRect().width) {
    if ((tries || 0) < 20) setTimeout(function () { drawBracketLines((tries || 0) + 1); }, 50);
    return;
  }
  wrap.querySelectorAll('svg.blines').forEach(el => el.remove());
  const NS = 'http://www.w3.org/2000/svg';
  const wr = wrap.getBoundingClientRect();
  const ox = wrap.scrollLeft - wr.left, oy = wrap.scrollTop - wr.top;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', 'blines');
  svg.setAttribute('width', wrap.scrollWidth);
  svg.setAttribute('height', wrap.scrollHeight);
  const paths = [];
  const box = el => { const r = el.getBoundingClientRect();
    return { l: r.left + ox, r: r.right + ox, y: r.top + oy + r.height / 2 }; };

  /* One elbow: out of A, along to the midpoint, vertically to B's row, into B.
     `dir` is +1 when the round advances rightwards and -1 when mirrored. */
  const elbow = (a, b, dir) => {
    const ax = dir > 0 ? a.r : a.l, bx = dir > 0 ? b.l : b.r;
    const mx = (ax + bx) / 2;
    paths.push('M' + ax + ' ' + a.y + 'H' + mx + 'V' + b.y + 'H' + bx);
  };

  wrap.querySelectorAll('.bhalf').forEach(half => {
    const mirror = half.classList.contains('mirror');
    let cols = [...half.querySelectorAll('.bcol')];
    if (mirror) cols.reverse();                        /* back into round order */
    for (let c = 0; c < cols.length - 1; c++) {
      const from = [...cols[c].querySelectorAll('.bgame')];
      const to = [...cols[c + 1].querySelectorAll('.bgame')];
      from.forEach((g, i) => {
        const t = to[Math.floor(i / 2)];
        if (t) elbow(box(g), box(t), mirror ? -1 : 1);
      });
    }
    /* semifinal into the championship, which sits between the halves */
    const semi = cols[cols.length - 1].querySelector('.bgame');
    const fin = wrap.querySelector('.bfinal .bgame');
    if (semi && fin) elbow(box(semi), box(fin), mirror ? -1 : 1);
  });

  const path = document.createElementNS(NS, 'path');
  path.setAttribute('d', paths.join(' '));
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '1.5');
  svg.appendChild(path);
  wrap.insertBefore(svg, wrap.firstChild);
}
addEventListener('resize', drawBracketLines);

renderBracket();
/* DRAW WHEN THE SECTION IS REVEALED. Three attempts got this wrong and each
   failure was the same shape -- watching a proxy instead of the condition:
     * rAF after the tab click: fired before the section was un-hidden;
     * an IntersectionObserver: the bracket sits BELOW a seeds table, so it is
       off-screen when the tab opens and never intersects until you scroll.
   The actual condition is `#v-bracket` losing its `hidden` attribute, so watch
   exactly that. A box inside a hidden section measures as zero, which is why
   drawing early produces an empty SVG rather than an error. */
(function () {
  const sec = document.getElementById('v-bracket');
  if (!sec || !window.MutationObserver) return;
  new MutationObserver(() => {
    if (!sec.hidden) drawBracketLines();
  }).observe(sec, { attributes: true, attributeFilter: ['hidden'] });
})();
drawBracketLines();
filter('sq', 'sbody', 'scnt', 'fixtures');
filter('tq', 'tbody', 'tcnt', 'matches');
{{ASK_JS}}
</script>
</body></html>"""


# Markers that must not survive into a PUBLIC build. Asserted after the strip,
# so a template edit that reintroduces one fails the build instead of quietly
# republishing somebody else's work.
# Markers must not collide with real DATA. "Massey" alone tripped on Addison
# Massey and Alexis Massey -- actual players on actual rosters. Match the
# product and the markup, never a bare word that can be somebody's surname.
def _b64(path):
    """A local image as a data URI. The page is one self-contained document --
    an external URL is a request the CSP blocks and a file that can go missing.
    Kept small on purpose: the head is 96px, the figure 200px."""
    import base64
    full = os.path.join(REPO, path)
    if not os.path.exists(full):
        return ""
    ext = "png" if path.lower().endswith(".png") else "jpeg"
    return "data:image/%s;base64,%s" % (
        ext, base64.b64encode(open(full, "rb").read()).decode("ascii"))


# Digby, drawn by Cody. The head alone for anything small -- at 18px a whole
# figure is a smudge and only the ball reads. PRIVATE BUILD ONLY, like the rest
# of the Digby feature, which also keeps the Molten/NCAA marks on his head off
# the public page.
DIGBY_HEAD = _b64("assets/digby_head.png")
DIGBY_COACH = _b64("assets/digby_coach.png")
# Styles for the drawn face live with it, so both are gated together and a
# rule can never keep a marker alive in a build the image is stripped from.
DIGBY_CSS = (".digby-face{vertical-align:middle;margin-right:6px}\n"
             ".digby-tag img{width:18px;height:18px;margin-right:6px;flex:none}\n")
DIGBY_SVG = ('<img class="digby-face" src="%s" alt="" width="18" height="18">'
             % DIGBY_HEAD) if DIGBY_HEAD else ""


# ------------------------------------------------------------------ Ask Digby
# PRIVATE ONLY. The chat needs scripts/live_server.py behind it (which holds the
# key); the public page has no server, so the whole feature is absent there
# rather than present and broken.
#
# The answer is MODEL-WRITTEN TEXT and is inserted with textContent, never
# innerHTML. Every other string on this page came from a feed; this one did not,
# and the rule that made </script> safe in the payloads applies to the DOM too.
ASK_CSS = """.digby-hello{float:right;margin:-4px 0 4px 10px}
.digby-coach{width:62px;height:auto;display:block}
.askhead img,.asklaunch img{width:20px;height:20px;margin-right:6px;flex:none}
.askhead svg,.asklaunch svg{width:18px;height:18px;margin-right:5px}
.askhead .t,.asklaunch{display:inline-flex;align-items:center}
/* Ask Digby. A launcher rather than a tab: the question is about whatever is
   already on screen, so it must not cost a navigation. Fixed position keeps it
   out of the sticky-nav offset trap that once hid the #1 team. */
.asklaunch{position:fixed;right:16px;bottom:16px;z-index:60;border:1px solid var(--line);
  background:var(--card);color:var(--ink);border-left:3px solid var(--amber);
  border-radius:2px;padding:10px 14px;cursor:pointer;box-shadow:0 3px 14px rgba(0,0,0,.16);
  font:700 11px/1 var(--sans);letter-spacing:.1em;text-transform:uppercase}
.asklaunch:hover{background:var(--alt)}
.askwrap{position:fixed;right:16px;bottom:16px;z-index:61;width:min(420px,calc(100vw - 32px));
  background:var(--card);border:1px solid var(--line);border-top:3px solid var(--amber);
  border-radius:2px;box-shadow:0 6px 30px rgba(0,0,0,.24);display:none}
.askwrap.on{display:block}
.askhead{display:flex;align-items:center;justify-content:space-between;
  padding:10px 12px;border-bottom:1px solid var(--line)}
.askhead .t{font:700 9.5px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink3)}
.askx{border:0;background:none;font-size:17px;line-height:1;cursor:pointer;color:var(--ink3)}
.askbody{padding:12px;max-height:min(52vh,420px);overflow:auto}
/* pre-wrap because an answer may carry a command on its own line, and a
   collapsed newline turns two commands into one unrunnable string. */
.askbody p{margin:0 0 8px;font-size:13.5px;line-height:1.55;white-space:pre-wrap}
.askq{font-weight:700;color:var(--ink2)}
.askmeta{font-size:11px;color:var(--ink3);margin:0 0 12px}
.askform{display:flex;gap:6px;padding:10px 12px;border-top:1px solid var(--line)}
.askform input{flex:1;min-width:0;padding:8px 10px;border:1px solid var(--line);
  border-radius:2px;background:var(--bg);color:var(--ink);font:400 13.5px/1.3 var(--sans)}
.askform button{padding:8px 12px;border:1px solid var(--line);background:var(--alt);
  color:var(--ink);border-radius:2px;cursor:pointer;font:700 11px/1 var(--sans)}
@media (max-width:560px){.askwrap{right:8px;left:8px;bottom:8px;width:auto}
  .asklaunch{right:8px;bottom:8px}}
"""

ASK_HTML = """<button class="asklaunch" id="asklaunch" aria-expanded="false"
  aria-controls="askwrap">{{DIGBY_SVG}} Ask Digby</button>
<div class="askwrap" id="askwrap" role="dialog" aria-label="Ask Digby">
  <div class="askhead"><span class="t">{{DIGBY_SVG}} Ask Digby</span>
    <button class="askx" id="askx" aria-label="Close">&times;</button></div>
  <div class="askbody" id="askbody">
    <div class="digby-hello">{{DIGBY_COACH}}</div>
    <p>Ask about any team, conference or player on this page &mdash; the 2026
      outlook, who is back, what the projection rests on.</p>
    <p class="askmeta">Digby answers only from this hub&rsquo;s data, and every
      number is checked against it before you see it. If something is not here
      &mdash; injuries, recruiting, how a team looked &mdash; he says so.</p>
  </div>
  <form class="askform" id="askform">
    <input id="askq" type="text" maxlength="500" autocomplete="off"
      placeholder="e.g. what does Nebraska&rsquo;s rotation look like?">
    <button type="submit">Ask</button>
  </form>
</div>"""

ASK_JS = r"""
(function () {
  var wrap = document.getElementById('askwrap'),
      launch = document.getElementById('asklaunch'),
      body = document.getElementById('askbody'),
      form = document.getElementById('askform'),
      q = document.getElementById('askq'),
      busy = false;
  if (!wrap) return;

  function open(on) {
    wrap.classList.toggle('on', on);
    launch.style.display = on ? 'none' : '';
    launch.setAttribute('aria-expanded', on ? 'true' : 'false');
    if (on) q.focus();
  }
  launch.addEventListener('click', function () { open(true); });
  document.getElementById('askx').addEventListener('click', function () { open(false); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && wrap.classList.contains('on')) open(false);
  });

  // textContent, never innerHTML: this is the only text on the page a model
  // wrote, so it is placed as text and can never be read as markup.
  function say(cls, text) {
    var p = document.createElement('p');
    if (cls) p.className = cls;
    p.textContent = text;
    body.appendChild(p);
    body.scrollTop = body.scrollHeight;
    return p;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = (q.value || '').trim();
    if (!text || busy) return;
    busy = true;
    q.value = '';
    say('askq', text);
    var pending = say('askmeta', 'Digging…');
    fetch('/api/digby', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text })
    }).then(function (r) { return r.json(); }).then(function (d) {
      pending.remove();
      say('', d.answer || 'No answer came back.');
      if (d.ok && d.teams && d.teams.length) {
        say('askmeta', 'Read from: ' + d.teams.join(', ') + '.');
      }
    }).catch(function () {
      pending.remove();
      // The static page opens fine from disk; only the chat needs the server.
      say('askmeta', 'No answer — Digby needs the local server running. '
        + 'Start it with: python3 scripts/live_server.py');
    }).then(function () { busy = false; });
  });
})();
"""


PRIVATE_MARKERS = ("VolleyTalk", "Massey Ratings", "Massey Ratings, 2026",
                   'data-v="tv"', 'id="v-tv"', "tv_listings",
                   "chip('Massey'", "chip('VT'",
                   # Digby: model-written text and an endpoint that only exists
                   # behind the local server. Neither belongs on a static public
                   # page, so their markers abort the build rather than relying
                   # on the `if not PUBLIC` guards having been remembered.
                   # NOT 'class="digby"': the panel's RENDERING code ships in
                   # both builds and only the data differs, which is the same
                   # distinction the Massey leak turned on -- grep the data, not
                   # the markup.
                   "/api/digby", "asklaunch", "Ask Digby",
                   # Digby's drawn face carries Molten and NCAA marks. It was
                   # inline SVG when the gate was written and slipped straight
                   # through when it became an image -- caught by grepping the
                   # built page, not by reading the code.
                   "digby-face", "digby-coach")


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
