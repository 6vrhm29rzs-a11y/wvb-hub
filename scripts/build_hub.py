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


def venue_index():
    # type: () -> Dict[str, Dict]
    """game_id -> where it is played and what event it belongs to.

    THE SCOREBOARD FEED CARRIES NO LOCATION AT ALL -- it enumerates fixtures and
    nothing more. Venue lives only on /game/{id}, which DOES answer for an
    unplayed match (gameState "P" still returns a full location block). That is
    why crawl_2025.py grew a `fixtures` phase: without it a schedule can say who
    and when but never where, and "at <home team>" is an inference presented as
    a fact -- the error that put Kentucky-Wisconsin in Lexington when it was
    played on a neutral floor in Milwaukee.
    """
    out = {}
    path = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                g = json.loads(line)
            except ValueError:
                continue
            gid = str(g.get("game_id") or "")
            loc = g.get("location") or {}
            if not gid:
                continue
            prev = out.get(gid)
            # final beats non-final, then last wins -- the project's dedup rule
            if prev and prev.get("state") == "F" and g.get("game_state") != "F":
                continue
            out[gid] = {"venue": loc.get("venue"), "city": loc.get("city"),
                        "state_usps": loc.get("state"), "state": g.get("game_state")}
    # site classification and event names, already derived by venues.py
    vdoc = load("data/venues_%d.json" % SEASON) or {}
    for row in (vdoc.get("games") or []):
        gid = str(row.get("game_id") or "")
        if gid in out:
            out[gid]["site"] = row.get("site")
            out[gid]["event"] = row.get("event")
    return out


def schedule(limit_days: int = 21) -> List[Dict]:
    """Upcoming fixtures from today forward, with WHERE and WHAT KIND."""
    today = datetime.date.today().isoformat()
    vidx = venue_index()
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
            gid = str(g.get("gameID") or g.get("id") or "")
            v = vidx.get(gid) or {}
            # CONFERENCE OR NOT, from the fixture's own two conference slugs.
            # Cheap and exact: the scoreboard tags each side with its league, so
            # this needs no join against a roster of conferences and cannot go
            # stale the way a name-keyed lookup can.
            ac = ((g.get("away") or {}).get("conferences") or [{}])[0].get("conferenceSeo")
            hc = ((g.get("home") or {}).get("conferences") or [{}])[0].get("conferenceSeo")
            kind = "conf" if (ac and hc and ac == hc) else "non"
            if v.get("event"):
                kind = "event"
            rows.append({
                "d": date, "a": a, "h": h,
                "t": listed_time(g.get("startTime"), h, g.get("startTimeEpoch")),
                "ar": (g.get("away") or {}).get("rank") or "",
                "hr": (g.get("home") or {}).get("rank") or "",
                "gid": gid,
                "venue": v.get("venue"), "city": v.get("city"),
                "st": v.get("state_usps"),
                "site": v.get("site"), "event": v.get("event"),
                "kind": kind, "conf": ac if kind == "conf" else "",
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
                photos=None, art=None, honours=None, team_name=None):
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
            "aa": (honours or {}).get("%s|%s" % (
                team_name or "", re.sub(r"[^a-z]", "", (name or "").lower()))),
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
               aq_of=None, sched_n=None, honours=None):
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
    vidx = venue_index()
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
            gid = str(g.get("gameID") or g.get("id") or "")
            v = vidx.get(gid) or {}
            ac = ((g.get("away") or {}).get("conferences") or [{}])[0].get("conferenceSeo")
            hc = ((g.get("home") or {}).get("conferences") or [{}])[0].get("conferenceSeo")
            kind = ("event" if v.get("event")
                    else ("conf" if (ac and hc and ac == hc) else "non"))
            # NEUTRAL IS NEITHER HOME NOR AWAY, and a team page that says
            # "home" for a tournament in Milwaukee is wrong about the one thing
            # a schedule is for. `home` stays a bool for existing consumers;
            # `site` carries the third state (R4 -- new meaning, new name).
            base = {"d": date, "t": t, "venue": v.get("venue"),
                    "city": v.get("city"), "st": v.get("state_usps"),
                    "site": v.get("site"), "event": v.get("event"), "kind": kind}
            aw = dict(base); aw.update({"opp": h, "home": False})
            hm = dict(base); hm.update({"opp": a, "home": True})
            fixtures.setdefault(a, []).append(aw)
            fixtures.setdefault(h, []).append(hm)

    # ---- CONFERENCE POSITION, SCHEDULE STRENGTH, HEAD-TO-HEAD ------------
    # All three are derived from data already on the page. Nothing here is an
    # estimate: the position is a sort, the schedule strength is a mean of
    # opponents' own ranks, and the head-to-head is read out of the completed
    # 2025 game log.
    _rank_of = dict((t["team"], t["rank26"]) for t in teams if t.get("rank26"))
    _conf_of = dict((t["team"], t.get("conf")) for t in teams)
    _conf_pos, _conf_size = {}, {}
    _by_conf = {}
    for _t in teams:
        if _t.get("conf") and _t.get("rank26"):
            _by_conf.setdefault(_t["conf"], []).append(_t)
    for _c, _rows in _by_conf.items():
        _rows.sort(key=lambda x: x["rank26"])
        _conf_size[_c] = len(_rows)
        for _i, _r in enumerate(_rows, 1):
            _conf_pos[_r["team"]] = _i

    # HEAD-TO-HEAD, from the completed 2025 season. Keyed both ways so either
    # team's page can find the meeting.
    _h2h = {}
    for _g in ((load("data/data_2025.json") or {}).get("games") or []):
        _ts = _g.get("teams") or []
        if len(_ts) != 2:
            continue
        _a, _b = _ts[0], _ts[1]
        _an = _a.get("name_short") or _a.get("name_full")
        _bn = _b.get("name_short") or _b.get("name_full")
        if not (_an and _bn):
            continue
        _asets, _bsets = _a.get("sets_won"), _b.get("sets_won")
        if _asets is None or _bsets is None:
            continue
        _date = None
        _ep = _g.get("start_time_epoch")
        if _ep:
            try:
                _date = datetime.datetime.utcfromtimestamp(int(_ep)).strftime("%Y-%m-%d")
            except Exception:                              # noqa: BLE001
                _date = None
        _h2h.setdefault((_an, _bn), []).append(
            {"d": _date, "mine": _asets, "theirs": _bsets, "opp": _bn})
        _h2h.setdefault((_bn, _an), []).append(
            {"d": _date, "mine": _bsets, "theirs": _asets, "opp": _an})

    # ---- SCHEDULE STRENGTH, from the fixtures each team actually has -------
    # The mean of the opponents' OWN ranks, plus how many are inside the top 25.
    # An opponent we do not rate -- an unranked or non-D-I side -- contributes
    # nothing rather than a guess, and the count of rated opponents rides along
    # so the page can state what the mean rests on. Early in a season a short
    # schedule is a small sample and saying so is the point.
    _coaches = head_coaches()
    _sos_of, _h2h_for = {}, {}
    for _team, _fx in fixtures.items():
        _ranks = [_rank_of[f["opp"]] for f in _fx if f.get("opp") in _rank_of]
        if _ranks:
            _sos_of[_team] = {
                "mean_rank": round(sum(_ranks) / float(len(_ranks)), 1),
                "rated": len(_ranks),
                "fixtures": len(_fx),
                "top25": sum(1 for r in _ranks if r <= 25),
            }
        # the previous meeting with each opponent this team is due to play
        _seen = {}
        for f in _fx:
            _o = f.get("opp")
            if not _o or _o in _seen:
                continue
            _prev = _h2h.get((_team, _o))
            if _prev:
                _prev = sorted(_prev, key=lambda x: x.get("d") or "")[-1]
                _seen[_o] = _prev
        if _seen:
            _h2h_for[_team] = _seen

    proj = {r["team"]: r for r in
            ((load("data/projection_2026.json") or {}).get("teams") or [])}
    photos = player_photos()

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

    honours = avca_honours()
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
                             art=(player_art.get(nm) or player_art.get(_rk) or {}),
                             honours=honours, team_name=nm)
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
            # position within its own conference on our 2026 order -- a sort of
            # data already on the page, not a new opinion
            "coach": _coaches.get(nm),
            "conf_pos": _conf_pos.get(nm),
            "conf_size": _conf_size.get(t.get("conf")),
            # SCHEDULE STRENGTH: the mean rank of the opponents this team
            # actually plays, and how many of them are inside the top 25. A
            # fixture against an unranked or non-D-I side contributes nothing
            # rather than a guess, and the count of rated opponents is carried
            # so the page can say what the mean rests on.
            "sos": _sos_of.get(nm),
            # the last meeting with each opponent, from the completed 2025
            # season -- read, never inferred
            "h2h": _h2h_for.get(nm),
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
    # ⚠ A SUMMARY IS ONLY VALID FOR THE FACTS IT WAS WRITTEN FROM.
    # Measured: a day after they were generated, 326 of 340 stored summaries
    # failed their own fidelity gate -- not because anything was wrong when
    # written, but because a completed match shifts every projection slightly
    # ("13.62 projected wins" had become 13.66). The gate exists so a displayed
    # number is a checked number, so a summary whose facts have moved is
    # WITHHELD rather than shown with a stale figure inside it.
    # The durable/volatile split in digby.py stops this recurring; the stored
    # ones were written before that split existed.
    if digby:
        try:
            import digby as _DG
            _bad = 0
            for _nm, _rec in out.items():
                _st = digby.get(_nm)
                if not _st:
                    continue
                if _st.get("hash") != _DG.input_hash(
                        _DG.durable(_DG.fact_sheet(_nm, _rec))):
                    _rec["digby"] = None
                    _bad += 1
            if _bad:
                print("  %d Digby summaries withheld -- their facts moved since "
                      "they were written; rerun scripts/digby.py" % _bad)
        except Exception as _e:                          # noqa: BLE001
            print("  could not verify Digby summaries (%s); withholding all"
                  % type(_e).__name__)
            for _rec in out.values():
                _rec["digby"] = None
    return out


# -------------------------------------------------------------- leaders
def head_coaches():
    # type: () -> Dict[str, Dict]
    """team -> head coach, from the school's own staff page.

    TWO SOURCES, hand-verified first. coaches_2026.json holds names taken from
    AVCA award citations, entered by hand with the citation recorded; those win.
    coaches_found_2026.json is the crawl of each school's coaches page.

    ⚠ The two agree where they overlap: the crawl returned Dan Fisher for
    Pittsburgh, which is what the 2024 AVCA Coach of the Year citation already
    said. That is two unrelated sources concurring, which is the corroboration
    this project prefers over any single scrape.

    A team with no coach on either renders nothing -- never a guess (R5).
    """
    out = {}
    for team, rec in (((load("data/raw/%d/coaches_found_%d.json" % (SEASON, SEASON))
                        or {}).get("teams")) or {}).items():
        if (rec or {}).get("name"):
            out[team] = {"name": rec["name"], "title": rec.get("title"),
                         "source": rec.get("source")}
    for team, rec in (((load("data/raw/%d/coaches_%d.json" % (SEASON, SEASON))
                        or {}).get("coaches")) or {}).items():
        if (rec or {}).get("name"):
            out[team] = {"name": rec["name"], "title": rec.get("title"),
                         "source": rec.get("source"), "note": rec.get("note")}
    return out


def di_teams():
    # type: () -> set
    """The 348 Division-I programmes, from the archived official RPI table.

    ⚠ THIS IS A LISTING FILTER, NOT A DATA FILTER, and the distinction is the
    whole point. Cody: "Elizabeth City St. doesn't really need to be listed in
    the stats page... just keep the score and stats for Norfolk St.'s purposes
    but keep this as a D1 site."

    So a non-D-I opponent keeps everything it contributes to a D-I team -- the
    result stands, the box score stands, and Norfolk St.'s own totals still
    include that match, because Norfolk St. really did earn those numbers on
    that night. What changes is that a Division-II programme and its players
    stop appearing in leaderboards that claim to rank Division I.

    Membership comes from the archived RPI table, which CLAUDE.md establishes as
    the only self-consistent list -- the per-game `division` flag is the team's
    CURRENT division and is unreliable retroactively.
    """
    doc = load("data/raw/2025/rpi_official.json") or {}
    return set(r["School"] for r in (doc.get("data") or []) if r.get("School"))


def leaders(photos=None, honours=None):
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
    # THIS IS A DIVISION-I SITE. A D-II opponent's players keep everything they
    # contributed to the D-I team they played -- the result, the box score, that
    # team's totals -- but they do not appear in a leaderboard that says it
    # ranks Division I.
    _di = di_teams()

    max_sets = max((r.get("sets") or 0) for r in rows)
    floor = max(3, int(round(max_sets * 0.5)))

    out = []
    for r in rows:
        _tm = names.get(str(r.get("team_id")))
        if _tm and _di and _tm not in _di:
            continue
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
            "num": r.get("num") or r.get("number"),
            "aa": (honours or {}).get("%s|%s" % (
                names.get(str(r.get("team_id"))) or "",
                re.sub(r"[^a-z]", "",
                       ("%s%s" % (r.get("first") or "", r.get("last") or "")).lower()))),
            "photo": ((photos or {}).get(
                names.get(str(r.get("team_id"))) or "") or {}).get(
                re.sub(r"[^a-z]", "",
                       ("%s %s" % (r.get("first") or "", r.get("last") or "")).lower())),
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

def box_and_players(res, photos=None, honours=None):
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
                # Her own headshot, so the player panel and the Players table
                # show the same face as the roster and the stats page.
                "photo": ((photos or {}).get(row["team"]) or {}).get(
                    re.sub(r"[^a-z]", "", (nm or "").lower())),
                "aa": (honours or {}).get("%s|%s" % (
                    row["team"], re.sub(r"[^a-z]", "", (nm or "").lower()))),
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
                # ⚠ ASSISTS BELONG ON A MATCH LINE. Without them a setter's
                # game log reads as if she did nothing: Izzy Starck's 41-assist
                # night showed "2k · 0e · 3ta · 13d" and no sign of the number
                # that was actually her match.
                "ast": row["ast"],
                "aces": row["aces"], "sets": sets, "pts": row["pts"],
            })
        if rows:
            boxes[gid] = rows

    out = []
    # ⚠ THE BOX SCORES KEEP EVERYONE; THIS LIST DOES NOT. `boxes` is untouched,
    # so a D-II opponent's players still appear in the box score of the match
    # they actually played -- that is a record of what happened. The Players TAB
    # is a Division-I directory, so it carries Division-I players.
    _di = di_teams()
    for p in players.values():
        if _di and p.get("team") and p["team"] not in _di:
            continue
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

def player_photos():
    # type: () -> Dict[str, Dict[str, str]]
    """team -> squashed name -> headshot URL.

    ONE DEFINITION. This was inline in `team_index()`, so the leaderboard could
    not reach it and stat rows had no photographs while roster rows did. URLS
    ONLY -- the images are never downloaded or committed; they load from each
    school's own server, and a player without one renders a position avatar,
    never a stand-in photograph.

    Two sources, best first: the roster crawl's own `photo`, then the
    schema.org `image` URLs recovered from JS-rendered roster pages
    (`crawl_roster_photos.py`), which is what took coverage from 133 teams to
    290.
    """
    out = {}                                            # type: Dict[str, Dict[str, str]]
    for tname, rec in ((load("data/raw/%d/rosters_%d.json" % (SEASON, SEASON)) or {})
                       .get("teams", {}) or {}).items():
        for pl in rec.get("players") or []:
            if pl.get("photo"):
                key = re.sub(r"[^a-z]", "", (pl.get("name_raw") or "").lower())
                out.setdefault(tname, {})[key] = pl["photo"]
    for tname, rec in ((load("data/raw/%d/roster_photos_%d.json" % (SEASON, SEASON))
                        or {}).get("teams", {}) or {}).items():
        for nm, url in (rec.get("photos") or {}).items():
            out.setdefault(tname, {}).setdefault(
                re.sub(r"[^a-z]", "", (nm or "").lower()), url)
    # THIRD SOURCE, and the one that finally covers the table-style rosters.
    # 33 teams -- Nebraska, LSU, Stanford, UCLA, Texas A&M, Virginia -- render
    # the roster as a TABLE with no photograph anywhere in the HTML, which is
    # why the first two paths found nothing and why this was written off as a
    # JavaScript ceiling. Their tables link to each player, and HER page carries
    # og:image. 26 of the 33 recovered, 0 rejected.
    # Attribution is by construction: the photo is reached through that
    # player's own link, so there is no name match that can go wrong (R8).
    for tname, rec in ((load("data/raw/%d/player_page_photos_%d.json" % (SEASON, SEASON))
                        or {}).get("teams", {}) or {}).items():
        for nm, url in (rec.get("photos") or {}).items():
            out.setdefault(tname, {}).setdefault(
                re.sub(r"[^a-z]", "", (nm or "").lower()), url)
    return out


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
    # ⚠ A LISTING FILTER, NOT A DATA FILTER. The non-D-I side keeps everything
    # it gave the D-I team it played -- those totals were built from the same
    # box score and Norfolk St. really did earn them that night. What it does
    # not get is a row of its own in a table that ranks Division I.
    _di = di_teams()
    if _di:
        out = dict((k, v) for k, v in out.items() if k in _di)
    return out


def avca_honours():
    # type: () -> Dict[str, List[Dict[str, Any]]]
    """team|squashed-name -> AVCA honours, most recent first.

    R8 APPLIES. Keyed on the school AND the exact full name; a selection whose
    school did not resolve is skipped rather than guessed. An All-America badge
    on the wrong player is the same class of error as attributing her stats, and
    it is the kind that looks right.

    Only the last two seasons are loaded. A 2003 honour is a fact about somebody
    who is not on a 2026 roster; the file keeps the rest for later.
    """
    doc = load("data/avca_awards.json") or {}
    out = {}                                            # type: Dict[str, List[Dict]]
    for sel in doc.get("selections") or []:
        if sel.get("season", 0) < SEASON - 2 or not sel.get("team"):
            continue
        key = "%s|%s" % (sel["team"], re.sub(
            r"[^a-z]", "", ("%s%s" % (sel.get("first"), sel.get("last"))).lower()))
        out.setdefault(key, []).append(
            {"season": sel["season"], "honour": sel.get("honour")})
    for v in out.values():
        v.sort(key=lambda x: -x["season"])

    # NATIONAL AWARDS, attached to the player they belong to. Player of the Year
    # is a different order of thing from a First-Team selection and should not
    # be flattened into one; it is stored on the same key so her page can lead
    # with it. Coach awards have no player to attach to and are kept separately.
    schools = {}
    for t in ((load("data/data_2025.json") or {}).get("teams") or []):
        for k in (t.get("name_full"), t.get("name_short")):
            if k:
                schools.setdefault(re.sub(r"[^a-z0-9]", "", k.lower()),
                                   t.get("name_short"))
    for year, awards in (doc.get("awards") or {}).items():
        if int(year) < SEASON - 2:
            continue
        for a in awards:
            txt = (a.get("text") or "").strip()
            label = (a.get("award") or "").strip()
            parts = [x.strip() for x in txt.split(",")]
            if len(parts) < 2:
                continue
            who, school = parts[0], parts[1]
            if "coach" in label.lower():
                out.setdefault("__coach_awards__", []).append(
                    {"season": int(year), "award": label, "who": who,
                     "school": school})
                continue
            short = schools.get(re.sub(r"[^a-z0-9]", "", school.lower()))
            if not short:
                # A national award we cannot place on a team is recorded, not
                # dropped -- it is still true, and a silent drop hides it.
                out.setdefault("__unplaced_awards__", []).append(
                    {"season": int(year), "award": label, "who": who,
                     "school": school})
                continue
            key = "%s|%s" % (short, re.sub(r"[^a-z]", "", who.lower()))
            out.setdefault(key, []).append(
                {"season": int(year), "honour": label, "national": True})
    for v in out.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "season" in v[0]:
            v.sort(key=lambda x: (-x.get("season", 0), not x.get("national")))
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


def form_strip(games, n=5):
    # type: (List[Dict], int) -> str
    """The last few results as W/L pills, oldest first.

    A ranked opponent is named on the pill's tooltip and marked, because
    "beat #8" and "beat an unranked team" are different evidence -- the rating
    already weighs them differently and the row should not hide that.
    """
    if not games:
        return '<span class="noform" title="no results yet">&mdash;</span>'
    out = []
    for g in games[-n:]:
        cls = "fw" if g["won"] else "fl"
        opp = ("#%d %s" % (g["opp_rank"], g["opp"])) if g.get("opp_rank") else g["opp"]
        out.append('<span class="%s%s" title="%s %s %s">%s</span>'
                   % (cls, " frk" if g.get("opp_rank") else "",
                      "beat" if g["won"] else "lost to", esc(opp), g["score"],
                      "W" if g["won"] else "L"))
    return "".join(out)


def hcell_py(v, txt, lo, hi, kind="seq"):
    # type: (Optional[float], str, float, float, str) -> str
    """Server-side twin of the page's hcell(): emits a cell carrying only --t.

    The colour, the bar, the easing and the two ramps all live in ONE CSS rule,
    so this function -- like its JS counterpart -- never names a colour. That is
    the whole point: the Top 25 is rendered in Python and the Stats tables in
    JavaScript, and a page whose two halves each hold their own opinion about
    what "good" looks like is how the crests came to be missing from every
    server-rendered view.

    A missing value renders as an em dash with no scale at all (R5) -- an
    absent measurement must not be painted as a neutral one.
    """
    if v is None:
        return '<td class="n">&mdash;</td>'
    t = 0.5 if hi == lo else (float(v) - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return '<td class="n hx %s" style="--t:%.3f"><b>%s</b></td>' % (kind, t, txt)


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
    # RECENT FORM. A ranking that moves without saying why is a number to argue
    # with; the result that moved it is the answer. Ranked opponents are marked,
    # because beating #8 and beating an unranked team are not the same evidence
    # and the rating already knows that even if the row does not show it.
    ranked = {}
    for r in ((load("data/digby_top25_%d.json" % SEASON) or {}).get("top") or []):
        ranked[r["team"]] = r["rank"]
    form = {}                                           # type: Dict[str, List[Dict]]
    for g in sorted(results() or [], key=lambda x: x.get("epoch") or 0):
        for me, them, mine, theirs in ((g["away"], g["home"], g["away_sets"], g["home_sets"]),
                                       (g["home"], g["away"], g["home_sets"], g["away_sets"])):
            if mine is None or theirs is None:
                continue
            form.setdefault(me, []).append({
                "won": mine > theirs, "score": "%s-%s" % (mine, theirs),
                "opp": them, "opp_rank": ranked.get(them), "date": g.get("date"),
            })
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

    # Symmetric about zero so +4 and -4 sit the same distance from neutral, and
    # scaled to the biggest margin actually on the board rather than a constant
    # I picked -- in August that is a handful of matches, in November it is a
    # season, and a fixed cap would wash the whole column out by then.
    _nets = [abs(r["net_pts_per_set"]) for r in top
             if r.get("net_pts_per_set") is not None]
    nmax = max(_nets) if _nets else 1.0

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
            '<td class="rec">%s</td><td class="form">%s</td>'
            '%s<td class="n wt">%s</td></tr>'
            % (esc(team), (colors.get(team) or {}).get("primary") or "var(--line)",
               r["rank"], logo_img(team, logos), esc(team), mv,
               esc(r.get("conf") or ""),
               r.get("record") or "0-0",
               form_strip(form.get(team) or []),
               hcell_py(r.get("net_pts_per_set"),
                        ("%+.2f" % r["net_pts_per_set"])
                        if r.get("net_pts_per_set") is not None else "",
                        -nmax, nmax, "dv"),
               ("%d%%" % round(100 * wt)) if wt else "&mdash;"))

    also = " &middot; ".join(
        "%s <span class=\"arv\">%s</span>" % (esc(a["team"]), a.get("record") or "0-0")
        for a in (doc.get("also_receiving") or []))

    movers = []
    for r in top:
        was = pre.get(r["team"])
        if was and was != r["rank"]:
            movers.append((was - r["rank"], r["team"], was, r["rank"]))
    movers.sort(key=lambda x: -abs(x[0]))
    mv_txt = ""
    if movers:
        def _one(d, team, was, now):
            return ("%s %s%d (%d\u2192%d)"
                    % (esc(team), "\u25b2" if d > 0 else "\u25bc", abs(d), was, now))
        mv_txt = ("<b>Biggest movers:</b> "
                  + " &middot; ".join(_one(*x) for x in movers[:4]) + ". ")

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
        mv_txt +
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
    boxes, plist = box_and_players(res, player_photos(), avca_honours())
    # Season team totals for 2026, both what a team does and what it allows.
    tstats = team_season_stats(boxes, res)
    stand = standings(teams, res)
    for _rows in stand.values():
        for _r in _rows:
            _ts = tstats.get(_r["team"]) or {}
            _o, _d = (_ts.get("own") or {}), (_ts.get("opp") or {})
            _r["diff"] = (round(_o["pps"] - _d["pps"], 2)
                          if _o.get("pps") is not None and _d.get("pps") is not None
                          else None)
    ldrs, ldr_floor, ldr_pool = leaders(player_photos(), avca_honours())
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
    _bcolors = ((load("data/team_colors_%d.json" % SEASON) or {}).get("teams") or {})
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
            '<tr class="row" data-r="%d" style="--tc:%s"><td class="rk">%d%s</td>'
            '<td class="tm">%s%s%s</td><td class="cf">%s</td>'
            '<td class="n hi">%s</td><td class="n">%s</td>%s'
            '<td class="n">%s</td>%s<td class="n">%s</td><td class="n hi">%s</td></tr>%s'
            % (t["rank26"],
               # the school's own colour, same source the Top 25 uses -- the two
               # tables of the same teams should not look like different sites
               (_bcolors.get(t["team"]) or {}).get("primary") or "var(--line2)",
               t["rank26"], mover(t),
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
            "graph to rate anyone honestly. <b>For a ranking that moves with "
            "every result today, use Digby&rsquo;s Top 25</b> \u2014 it blends "
            "this projection with what has actually happened, weighted by how "
            "much has been played.")

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
        # HOW CLOSE EACH SET WAS, SHOWN RATHER THAN ONLY SAID. The copy above
        # the results already tells the reader that a 25-23 and a 25-12 are not
        # the same match; the strip did not show it. Each set gains a bar whose
        # width is the MARGIN -- 2 points is a sliver, a 13-point rout fills the
        # cell. Scaled against 13, which is the margin of a 25-12: past that the
        # bar is full and the numbers carry the rest, because a scale stretched
        # to the rare 25-3 would squash every ordinary set into nothing.
        strip = ""
        for i, (av, hv) in enumerate(r["sets"], 1):
            aw = av > hv
            _m = abs((av or 0) - (hv or 0))
            _w = min(100.0, _m / 13.0 * 100.0)
            strip += ('<div class="set" title="set %d: %d-%d, %d point%s">'
                      '<span class="%s">%d</span>'
                      '<span class="%s">%d</span>'
                      '<i class="mg" style="width:%.0f%%"></i></div>'
                      % (i, av, hv, _m, "" if _m == 1 else "s",
                         "w" if aw else "", av, "" if aw else "w", hv, _w))
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
        # WHERE. A venue we do not have is stated as such -- never inferred
        # from the nominal home team, which is exactly how two AVCA First Serve
        # matches on a neutral floor in Milwaukee came to be labelled home games
        # (R5). "at" becomes "vs" when the floor is neutral, because "Texas at
        # Arizona St." is a false sentence about a match in Milwaukee.
        neutral = r.get("site") == "neutral"
        where = ""
        if r.get("venue"):
            city = ", ".join(x for x in (r.get("city"), r.get("st")) if x)
            where = ('<b>%s</b>%s' % (esc(r["venue"]),
                                      ('<span class="wc">%s</span>' % esc(city)) if city else ""))
        else:
            where = '<span class="wu">venue not listed</span>'
        if r.get("event"):
            badge = '<span class="kind ev" title="in-season tournament">%s</span>' % esc(r["event"])
        elif neutral:
            # WE KNOW IT IS AN EVENT; WE DO NOT KNOW ITS NAME. venues.py only
            # attaches a name that a human supplied in Cody/data/events_2026.txt
            # -- it never invents one from the venue. So a neutral floor with no
            # name says exactly that much and no more, rather than being filed
            # as an ordinary non-conference road match, which is what it is not.
            badge = ('<span class="kind nu" title="neutral floor -- an event, '
                     'name not supplied">neutral site</span>')
        elif r["kind"] == "conf":
            badge = '<span class="kind cf" title="conference match">conference</span>'
        else:
            badge = '<span class="kind nc" title="non-conference match">non-conf</span>'
        srows.append(
            '<tr%s><td class="cd">%s</td><td class="n">%s</td><td class="tm">%s%s%s</td>'
            '<td class="at">%s</td><td class="tm">%s%s%s</td>'
            '<td class="wh l">%s%s</td>'
            '<td class="n pick %s">%s</td></tr>'
            % ((' class="rkd both"' if (r["ar"] and r["hr"])
                else (' class="rkd"' if (r["ar"] or r["hr"]) else "")),
               r["d"], r["t"] or "&mdash;",
               ('<i class="rnk">%s</i> ' % r["ar"]) if r["ar"] else "",
               logo_img(r["a"], logos), esc(r["a"]),
               "vs" if neutral else "at",
               ('<i class="rnk">%s</i> ' % r["hr"]) if r["hr"] else "",
               logo_img(r["h"], logos), esc(r["h"]),
               badge, where,
               cls, pick))
    srows = "".join(srows)

    trows = "".join(
        '<tr><td class="cd">%s</td><td class="tm">%s</td>'
        '<td class="tvnet"><span class="netchip">%s</span></td><td class="n">%s</td></tr>'
        % (esc(r["day"]), esc(r["m"]), esc(r["n"]), esc(r["t"]))
        for r in tvrows)

    # ---- HERO -----------------------------------------------------------
    # EVERY STRING HERE IS BUILT FROM A MEASURED VALUE AT PRINT TIME (R1).
    # There is no sentence written in advance about how the season is going;
    # the counts are read from the same results and Top 25 the tabs render.
    _hero_top = (load("data/digby_top25_%d.json" % SEASON) or {}).get("top") or []
    _colors = ((load("data/team_colors_%d.json" % SEASON) or {}).get("teams") or {})
    _logos = team_logos()
    _played = len(res)
    _teams_seen = len(set([r["home"] for r in res] + [r["away"] for r in res]))
    _last = max([r["date"] for r in res], default=None)
    _hero = {
        "eyebrow": ("%d matches in" % _played) if _played
                   else "Season opens soon",
        "title": "The 2026 season, measured",
        "sub": ("%s teams rated &middot; %d matches played across %d teams &middot; "
                "last result %s" % ("{:,}".format(len(teams)), _played,
                                    _teams_seen, esc(_last or "&mdash;")))
               if _played else
               ("%s teams rated &middot; no matches played yet"
                % "{:,}".format(len(teams))),
        "podium": "",
    }
    _pod = []
    for _r in _hero_top[:3]:
        _nm = _r["team"]
        _c = (_colors.get(_nm) or {}).get("primary") or "var(--line2)"
        # net points/set is absent until a team has played -- say so rather
        # than printing a zero (R5).
        _net = _r.get("net_pts_per_set")
        _pod.append(
            '<div class="pod" style="--tc:%s"><span class="podrk">%d</span>'
            '%s<span class="podnm">%s</span>'
            '<span class="podv %s"%s>%s</span>'
            '<span class="podl">%s</span></div>'
            % (_c, _r["rank"], logo_img(_nm, _logos), esc(_nm),
               # ⚠ COLOUR BY SIGN, NOT BY RANK. #3 on the podium was rendering
               # its -4.25 in the "good" green purely for being third-best --
               # a colour asserting the opposite of the number beside it.
               ("pos" if _net > 0 else "neg") if _net is not None else "nil",
               (' data-count="%.2f"' % _net) if _net is not None else "",
               ("%+.2f" % _net) if _net is not None else "&mdash;",
               "net pts/set" if _net is not None else "not played"))
    _hero["podium"] = "".join(_pod)

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
        .replace("{{HERO_EYEBROW}}", _hero["eyebrow"]) \
        .replace("{{HERO_TITLE}}", _hero["title"]) \
        .replace("{{HERO_SUB}}", _hero["sub"]) \
        .replace("{{HERO_PODIUM}}", _hero["podium"]) \
        .replace("{{N_SCHED}}", "{:,}".format(len(sched))) \
        .replace("{{N_TV}}", str(len(tvrows))) \
        .replace("{{STANDINGS_JSON}}", json.dumps(stand, separators=(",", ":"))) \
        .replace("{{RESULTS_JSON}}", blob(
            [{"away": r["away"], "home": r["home"],
              "away_sets": r["away_sets"], "home_sets": r["home_sets"],
              "epoch": r.get("epoch")}
             for r in sorted(res, key=lambda x: x.get("epoch") or 0)])) \
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
     #4B5563 / #66748F / #1E2A42), which is why the page read as generic: those
     five values sit under a very large share of dashboards on the internet.
     Replaced with warm, sand-tinted neutrals taken from an indoor court's
     playing surface, and an accent pair taken from the Molten ball the NCAA
     actually plays with -- deep blue and a hard yellow. Warm ground under cool
     blue is the whole identity; keep it. */
  --page:#070B14; --card:#0E1524; --alt:#131C2E;
  --ink:#EDF2FB; --ink2:#9CABC6; --ink3:#66748F;
  --line:#1E2A42; --line2:#33456A;
  --navy:#5BA8F5; --blue:#7FC1FF; --amber:#FFC72C; --amber-bg:#3A2D06;
  --sand:#1A2436;
  /* ⚠ --navy CHANGED MEANING when the page went dark: it used to be a dark
     blue used BOTH as chrome and as ink. On a dark ground the ink has to be
     light, so --navy is now the bright blue INK and the chrome that used to be
     navy gets its own name. Renaming rather than silently repointing is the
     whole of R4 -- the alternative is a masthead painted in a text colour. */
  --chrome:#0A1428; --chrome2:#132743;
  --ink-on-accent:#06101F;
  --live:#FF5F57; --win:#2FD07A;
  /* The good -> bad pair. Both are LIFTED for a dark ground: #0E7C4A and
     #FF5F6E were chosen to sit on sand and go muddy on near-black, where a
     colour needs more light than the ink around it, not less. */
  --good:#31D07E; --bad:#FF5F6E; --mid:#8494B2;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;
  --disp:"Oswald","Avenir Next Condensed","HelveticaNeue-CondensedBold",
         "Arial Narrow",var(--sans);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
/* THE GROUND IS LIT, NOT FLAT. Three fixed radial washes -- one cool, one warm,
   one deep -- sit under everything and do not scroll, so the page reads as a
   room with lights in it rather than a sheet of paper. They are 6-14% alpha:
   the point is that you cannot see where they start. */
/* ---- THE GROUND IS BUILT, NOT WASHED ---------------------------------
   Four layers, all fixed so the page moves over a room that does not:
     1. a COURT floor in perspective along the bottom -- the sport's own
        geometry, at 3% so you read it as texture rather than as a picture;
     2. a fine grain, because a flat gradient on a large dark surface bands
        visibly on an ordinary monitor and grain is what breaks the banding;
     3. two arena washes, cool from the left and the ball's yellow from the
        right, as if two lighting rigs were up;
     4. the base.
   Deliberately NOT the near-black-plus-one-acid-accent look: that is the
   default every dark dashboard reaches for. The accents here are the sport's
   own -- Molten blue and the hard yellow off the ball. */
body{margin:0;color:var(--ink);font:15px/1.55 var(--sans);
  font-feature-settings:"tnum" 1;
  background:
    radial-gradient(1400px 520px at 50% 128%, rgba(91,168,245,.16), transparent 70%),
    radial-gradient(1100px 700px at 4% -10%, rgba(91,168,245,.13), transparent 62%),
    radial-gradient(900px 640px at 98% 2%, rgba(255,199,44,.10), transparent 58%),
    var(--page);
  background-attachment:fixed;
  background-repeat:no-repeat}
/* THE FLOOR. Flat vertical stripes read as stripes; a court reads as a court
   only in perspective, so this is a grid rotated back in X and faded out as it
   recedes. 4% opacity: the eye should register that the page is standing on
   something without ever being asked to look at it. */
body::after{content:"";position:fixed;left:-25%;right:-25%;bottom:-14vh;height:62vh;
  z-index:0;pointer-events:none;opacity:.055;
  transform:perspective(80vh) rotateX(62deg);transform-origin:bottom center;
  background:
    repeating-linear-gradient(90deg,#cfe4ff 0 2px,transparent 2px 132px),
    repeating-linear-gradient(0deg,#cfe4ff 0 2px,transparent 2px 132px);
  -webkit-mask-image:linear-gradient(to top,#000 0%,rgba(0,0,0,.55) 42%,transparent 82%);
  mask-image:linear-gradient(to top,#000 0%,rgba(0,0,0,.55) 42%,transparent 82%)}
/* the grain sits above the ground and below everything else */
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  opacity:.5;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml;utf8,\
<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'>\
<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/>\
<feColorMatrix type='saturate' values='0'/></filter>\
<rect width='140' height='140' filter='url(%23n)' opacity='.32'/></svg>")}
header,nav,main{position:relative;z-index:1}

header{color:var(--ink);padding:20px 24px 0;position:relative;
  background:
    radial-gradient(120% 180% at 12% -40%, rgba(91,168,245,.30), transparent 60%),
    radial-gradient(90% 160% at 92% -30%, rgba(255,199,44,.20), transparent 62%),
    linear-gradient(180deg,var(--chrome2) 0%,var(--chrome) 78%,#08101F 100%)}
.mast{max-width:1280px;margin:0 auto;display:flex;align-items:flex-end;
  justify-content:space-between;gap:20px;flex-wrap:wrap}
h1{margin:0;font:600 40px/.92 var(--disp);letter-spacing:.005em;
  color:var(--ink);text-transform:uppercase}
h1 em{font-style:normal;color:var(--amber)}
.season{font:700 10px/1 var(--mono);color:#8FB6DC;letter-spacing:.34em;
  text-transform:uppercase;margin-bottom:9px}
.meta{font:12px/1.65 var(--mono);color:#9CABC6;text-align:right}
.meta b{color:var(--ink)}
/* The net: white mesh under a taut yellow tape. It is the one thing in the
   sport every viewer can draw from memory, so it carries the masthead. */
.net{max-width:1280px;margin:17px auto 0;height:11px;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.30) 0 1px,transparent 1px 6px),
             repeating-linear-gradient(0deg,rgba(255,255,255,.30) 0 1px,transparent 1px 6px);
  border-top:3px solid var(--amber);
  box-shadow:0 -1px 22px -2px rgba(255,199,44,.55),0 6px 30px -14px rgba(255,199,44,.35)}
nav{position:sticky;top:0;z-index:6;
  background:linear-gradient(180deg,rgba(12,23,45,.88),rgba(8,14,28,.92));
  backdrop-filter:saturate(1.6) blur(14px);
  border-bottom:1px solid transparent;
  border-image:linear-gradient(90deg,transparent,rgba(120,180,255,.5) 18%,
    rgba(255,199,44,.55) 52%,rgba(120,180,255,.5) 84%,transparent) 1}
/* the active tab sits in a lit slot rather than merely being white text */
nav button[aria-selected=true]{background:linear-gradient(180deg,
  rgba(120,180,255,.14),rgba(120,180,255,.04));
  box-shadow:inset 0 -2px 0 rgba(255,199,44,.9),0 0 26px -8px rgba(255,199,44,.5)}
nav .inner{max-width:1280px;margin:0 auto;display:flex;gap:2px;flex-wrap:wrap;padding:0 8px}
nav button{appearance:none;border:0;background:transparent;color:#9CABC6;
  font:500 14.5px/1 var(--disp);letter-spacing:.055em;padding:14px 16px;cursor:pointer;
  border-bottom:3px solid transparent;text-transform:uppercase;
  transition:color .16s ease}
nav button:hover{color:var(--ink)}
nav button[aria-selected=true]{color:var(--ink)}
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

/* Surfaces fade rather than sit flat. Every box on this page was #0E1524 on
   #070B14 with a hairline, which is what made a dense stats page read as
   sterile: nothing had a top or a bottom. The gradient is 4% of a tone -- felt,
   not seen -- and the shadow is warm, tinted toward the sand ground rather
   than the neutral grey every UI kit ships. */
/* ---- A GRADIENT HAIRLINE, NOT A FLAT GREY BOX -------------------------
   Every surface on the page wore the same 1px #1E2A42 border, which is what
   made a dark page still read as a dark BOOTSTRAP page. The border is now a
   gradient -- brighter where the light is, fading as it falls away -- drawn as
   a padded background layer so the fill underneath stays independent. One
   definition, applied to every surface, so they belong to each other. */
.panel,.tsec,.hero,.card{
  border:1px solid transparent;border-radius:14px;
  background-origin:border-box;
  background-clip:padding-box,border-box}
.panel{background-image:
    linear-gradient(176deg,rgba(26,38,62,.94) 0%,rgba(14,21,36,.94) 55%,rgba(10,16,28,.96) 100%),
    linear-gradient(150deg,rgba(120,180,255,.42),rgba(255,199,44,.16) 42%,rgba(255,255,255,.04) 70%);
  overflow:hidden;
  box-shadow:0 1px 0 rgba(255,255,255,.06) inset,
             0 24px 60px -32px rgba(0,0,0,.95)}
/* ---- THE VALUE SCALE. ONE DEFINITION, BOTH RENDERERS. -----------------
   Python and JS each emit nothing but `style="--t:.73"`. Every colour and
   every dimension is decided here, so the server-rendered views and the
   script-rendered views cannot drift apart -- the same failure the crest
   helper was built to end (rankings/schedule/scores had no logos because the
   JS helper was unreachable from Python).

   t = 0 is the weakest value on screen, t = 1 the strongest. TWO RAMPS,
   deliberately not one:
     .seq  more is better and everything shown is already good -- a national
           top-50 leaderboard. Ramps sand -> green. Red here would call the
           48th-best hitter in the country "bad", which is false.
     .dv   a real zero exists (a point differential). Ramps red -> sand ->
           green, and only this one earns red.
   Lightness falls monotonically as t rises, so the ramp still reads as a ramp
   without hue -- and the number itself is always printed, so colour is never
   the only channel carrying the value. */
td.hx{position:relative;isolation:isolate}
td.hx.seq{--hc:color-mix(in oklab,var(--mid),var(--good) calc(var(--t,0)*100%))}
td.hx.dv{--hc:color-mix(in oklab,var(--bad),var(--good) calc(var(--t,.5)*100%))}
td.hx::before{content:"";position:absolute;z-index:-1;top:3px;bottom:3px;right:3px;
  width:calc((.08 + var(--w,var(--t,0))*.92) * 100%);
  border-radius:1px 4px 4px 1px;
  background:linear-gradient(90deg,
    color-mix(in oklab,var(--hc) 9%,transparent) 0%,
    color-mix(in oklab,var(--hc) 26%,transparent) 55%,
    color-mix(in oklab,var(--hc) 52%,transparent) 100%);
  /* A CRISP LEFT EDGE. The fill alone gives no precise place to compare one
     row against the next -- a soft gradient tip is unreadable at a glance, so
     the bar carries a hard rule where it actually ends. That edge is the
     measurement; the wash behind it is just weight. */
  border-left:2.5px solid color-mix(in oklab,var(--hc) 70%,transparent);
  transform-origin:right center;
  animation:hxin .42s cubic-bezier(.22,.9,.3,1) both}
/* NARROW COLUMNS GET A CHIP, NOT A BAR. The standings +/- column is ~60px:
   a proportional bar there has no room to be proportional, and its edge rule
   landed on top of the digits. Sign and intensity are the whole message in a
   diverging column, so the cell fills instead and length stops pretending to
   carry information it cannot. */
/* A DIVERGING CELL IS ALWAYS A CHIP, NEVER A BAR -- folded into .dv itself so
   a future call site cannot forget it. A bar anchored at the right edge grows
   LEFTWARD as the value falls, so a negative gets a short bar whose hard edge
   lands in the middle of its own digits ("-4|25"). A proper diverging bar would
   have to grow out from zero at the cell's centre, which is illegible in the
   ~90px these columns get. Sign and intensity are the message; the printed
   number is already the precise value. */
td.hx.dv::before,td.hx.fill::before{width:auto;left:3px;right:3px;border-left:0;border-radius:4px;
  background:linear-gradient(90deg,
    color-mix(in oklab,var(--hc) 10%,transparent),
    color-mix(in oklab,var(--hc) 34%,transparent))}
/* THE NUMERAL MUST STAY READABLE AT EVERY POINT ON THE RAMP. Mixing it 96%
   toward the ramp colour worked on a light ground, where the ramp's weak end
   was dark. On a dark ground that same end IS the background, and the value
   measured 1.07 contrast. Mixing toward the page ink keeps the hue as the
   signal and hands luminance back to the reader. */
td.hx b{position:relative;font-weight:700;
  color:color-mix(in oklab,var(--hc) 62%,var(--ink))}
@keyframes hxin{from{transform:scaleX(.04);opacity:0}to{transform:scaleX(1);opacity:1}}
@media (prefers-reduced-motion:reduce){td.hx::before{animation:none}}
table{width:100%;border-collapse:collapse}
th{font:500 12px/1 var(--disp);letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink2);text-align:right;padding:12px 10px;
  background:linear-gradient(180deg,rgba(30,42,66,.95),rgba(17,25,41,.95));
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
tr.row:hover td{background:#12233C;cursor:pointer}
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
.card{background-image:
    linear-gradient(168deg,rgba(27,40,64,.96) 0%,rgba(15,22,38,.96) 60%,rgba(11,17,30,.97) 100%),
    linear-gradient(155deg,rgba(120,180,255,.40),rgba(255,199,44,.14) 44%,rgba(255,255,255,.03) 74%);
  border-radius:10px;
  border-left:3px solid var(--line2);
  padding:14px 16px 13px;
  box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 14px 30px -22px rgba(0,0,0,.95);
  transition:box-shadow .18s ease,transform .18s ease,border-color .18s ease}
.card:hover{border-color:var(--line2);transform:translateY(-2px);
  box-shadow:0 1px 0 rgba(255,255,255,.07) inset,0 22px 44px -22px rgba(0,0,0,1),
             0 0 0 1px rgba(91,168,245,.10)}
@media (prefers-reduced-motion:reduce){.card{transition:none}.card:hover{transform:none}}
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
/* THE WINNER IS GREEN; THE LOSER IS NOT RED. Every match has a loser, so
   colouring both would put red on half the page and the signal would stop
   meaning anything -- red is kept for a number that is genuinely bad, like a
   negative differential. The winner's score also carries a soft halo so the
   result reads before the names do. */
.side b{font-size:38px}
.side.win b{color:var(--good);
  text-shadow:0 0 4px rgba(49,208,126,.55),0 0 26px rgba(49,208,126,.42),
              0 0 54px rgba(49,208,126,.22)}
/* the signature: each set is a column, visitor above, home below, winner lit */
.sets{display:flex;gap:5px;margin-bottom:10px}
.set{flex:0 1 64px;display:flex;flex-direction:column;border:1px solid var(--line2);
  border-radius:2px;overflow:hidden;min-width:40px}
.set span{font:700 12.5px/1 var(--mono);padding:6px 0;text-align:center;
  color:var(--ink3);background:var(--alt)}
/* the set winner is LIT -- the ball's yellow, the one place it appears at full
   strength, so the eye reads a 25-23 differently from a 25-12 at a glance */
.set span.w{color:#1A1200;background:var(--amber);font-weight:800}
.venue{font:12px/1.5 var(--mono);color:var(--ink2)}
.card[data-gid]{cursor:pointer}
.card[data-gid]:hover{border-color:var(--line2);box-shadow:0 2px 6px rgba(16,24,40,.09)}
.empty{padding:30px;text-align:center;color:var(--ink2);font-size:14px}
/* A PILL MUST NOT BREAK ACROSS LINES. "neutral site" wrapped to "neutral" /
   "site" with its border split across both rows -- which reads as text being
   cut off. The LINE may wrap; the chip may not. Same for the kind badges. */
.tag{white-space:nowrap;font:700 10px/1 var(--mono);color:#FFD97A;background:var(--amber-bg);
  border:1px solid #6B551C;border-radius:4px;padding:3px 5px;letter-spacing:.05em}
.tag.neutral{color:var(--navy);background:#12233C;border-color:#2A4570;margin-left:6px}
td.pick{color:var(--navy)}
td.pick.toss{color:var(--ink2)}
td.pick b{color:var(--navy)}
/* On the light ground this was dark amber ink on a pale amber chip. Both
   ends went dark in the flip and it landed at a contrast ratio of 1.3 --
   invisible. The chip keeps its amber identity; the ink is lifted. */
.tag.event{color:#FFD97A;background:#3A2D06;border-color:#6B551C;margin-left:6px}

/* ---- live ---- */
#live{margin-bottom:26px}
.livehead{display:flex;align-items:center;gap:9px;margin-bottom:12px}
.livehead b{font:800 12.5px/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;
  color:var(--live)}
.livehead b.justin{color:#31D07E}
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
.card.islive{border-color:#5E2229;box-shadow:0 1px 3px rgba(200,50,43,.13)}
.card.islive .cd{color:var(--live)}
.set.now{border-color:var(--live)}
.set.now span{background:#2B1114;color:var(--live)}

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
.phead{display:flex;align-items:flex-start;gap:16px}
.phero{width:72px;height:72px;border-radius:50%;object-fit:cover;
  object-position:50% 18%;flex:none;
  background:var(--alt);border:1px solid var(--line)}
.phead svg{flex:none}
.pcell{display:flex;align-items:center;gap:10px;min-width:0;max-width:100%}
/* An All-America badge. Sized like a footnote, not a trophy -- it sits beside a
   name, and a loud chip next to every good player is noise. */
.aa{display:inline-block;margin-left:7px;padding:2px 5px;border-radius:2px;
  font:700 9px/1 var(--mono);letter-spacing:.06em;vertical-align:2px;
  background:var(--alt);color:var(--ink2);border:1px solid var(--line)}
/* A national award is a different order of thing from a team selection. */
.aaNat{background:var(--navy);color:var(--ink-on-accent);border-color:var(--navy)}
.aaFirst{background:var(--amber);color:var(--ink-on-accent);border-color:#FFC72C}
.aaSecon{background:#12233C;color:var(--navy);border-color:#2A4570}
.aaThird{background:var(--alt);color:var(--ink2)}
.pcell .pmug{border-radius:50%;object-fit:cover;object-position:50% 18%;flex:none;background:var(--alt)}
.pcell svg{flex:none}
/* CLICK TO ENLARGE. The photo is hotlinked, never downloaded (the images belong
   to the schools and this repo is public), so the overlay simply asks for the
   same URL at a size that does it justice -- 2:3, uncropped, nothing cut. */
img.mug,img.pmug,img.phero{cursor:zoom-in}
#lbx{position:fixed;inset:0;z-index:60;display:none;align-items:center;
  justify-content:center;padding:28px;
  background:radial-gradient(120% 120% at 50% 0%,rgba(12,20,36,.82),rgba(4,7,14,.94));
  backdrop-filter:blur(6px)}
#lbx.on{display:flex}
/* ⚠ max-width ALONE DOES NOT ESTABLISH A WIDTH. As a flex item this figure
   collapsed to the image's intrinsic size, so a 100px thumbnail opened as a
   100px "enlargement" -- the overlay worked and enlarged nothing. */
#lbx figure{margin:0;width:min(92vw,460px);max-width:min(92vw,460px);text-align:center;
  animation:lbxin .22s cubic-bezier(.2,.9,.3,1) both}
#lbx img{width:100%;height:auto;aspect-ratio:2/3;object-fit:cover;
  object-position:50% 12%;border-radius:14px;border:1px solid var(--line2);
  box-shadow:0 30px 70px -20px rgba(0,0,0,.95)}
#lbx figcaption{margin-top:12px;font:600 17px/1.3 var(--disp);color:var(--ink);
  letter-spacing:.01em}
#lbx .sub{display:block;margin-top:3px;font:12px/1.4 var(--mono);color:var(--ink3)}
#lbx button{position:absolute;top:18px;right:20px;appearance:none;border:0;
  background:transparent;color:var(--ink2);font:300 30px/1 var(--sans);cursor:pointer}
#lbx button:hover{color:var(--ink)}
@keyframes lbxin{from{transform:scale(.94);opacity:0}to{transform:scale(1);opacity:1}}
@media (prefers-reduced-motion:reduce){#lbx figure{animation:none}}
.pinfo{display:flex;flex-direction:column;min-width:0;line-height:1.15}
/* A long name has to wrap rather than push the cell past its box -- at
   560px 17 roster cells were overflowing, which clips on a phone even
   though the page itself does not scroll sideways. */
.pnm{font:600 15px/1.2 var(--disp);letter-spacing:.01em;color:var(--ink);
  overflow-wrap:anywhere;min-width:0}
.pinfo{flex:1 1 auto}
.pmeta{font:600 10.5px/1 var(--mono);color:var(--ink3);margin-top:3px;letter-spacing:.03em}
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
/* A fixture with a ranked side gets a quiet edge; two ranked sides get a loud
   one. The schedule is long and the eye needs somewhere to land. */
.stgrid td.form{white-space:nowrap}
.stgrid td.pos{color:#31D07E}
.stgrid td.neg{color:#FF5F6E}
/* WHERE a match is played, and what kind of match it is. Both were absent:
   the schedule said who and when, and a reader had to assume the rest. */
/* the second line of a team-page fixture: where, and what kind */
.gline.gl2{flex-wrap:wrap}
.wh2{flex-basis:100%;display:flex;align-items:center;gap:7px;margin:3px 0 0 0;
  padding-left:2px}
.wh2 .pl{font:11.5px/1.4 var(--mono);color:var(--ink3)}
.wh2 .pl.u{font-style:italic}
.va.nt{color:var(--amber);font-weight:800}
/* THE MARGIN OF EACH SET, under its own column. Amber because it belongs to
   the set-winner language already established by the lit cell, and thin because
   the numbers remain the measurement -- this only makes a rout distinguishable
   from a scrap at a glance. */
.set{position:relative}
.set .mg{position:absolute;left:0;bottom:0;height:2px;background:var(--amber);
  opacity:.85;border-radius:0 1px 1px 0;
  transform-origin:left center;animation:cbin .45s cubic-bezier(.22,.9,.3,1) both}
@media (prefers-reduced-motion:reduce){.set .mg{animation:none}}
/* the bracket, in team colours */
.bside{position:relative}
.bside::before{content:"";position:absolute;left:0;top:3px;bottom:3px;width:3px;
  border-radius:2px;background:var(--tc,transparent)}
.bside.empty::before{background:transparent}
/* ---- ON TV: the network, as a chip -----------------------------------
   ⚠ THIS CELL USED CLASS "net", WHICH IS ALSO THE MASTHEAD'S VOLLEYBALL NET --
   a repeating-linear-gradient mesh. Every network cell was being painted with
   it, so the column rendered as a striped block and looked broken. One class
   name, two meanings, exactly the duplicate-id bug one layer down. Renamed to
   .tvnet, and the network now reads as a chip. */
td.tvnet{text-align:left}
.netchip{display:inline-block;white-space:nowrap;padding:3px 8px;border-radius:4px;
  font:700 10.5px/1.4 var(--mono);letter-spacing:.04em;
  color:var(--blue);background:color-mix(in oklab,var(--navy) 16%,transparent);
  border:1px solid color-mix(in oklab,var(--navy) 34%,transparent)}
/* ---- RANKINGS: the school's colour on the row edge --------------------
   Matches the Top 25, so the two tables of the same teams stop looking like
   two different products. */
#rbody tr.row td:first-child{position:relative}
#rbody tr.row td:first-child::before{content:"";position:absolute;left:0;
  top:50%;transform:translateY(-50%);width:3px;height:22px;border-radius:2px;
  background:var(--tc,var(--line2))}
#rbody tr.row:hover td{background:rgba(91,168,245,.06)}
/* ---- CONFERENCE STRENGTH STRIP ---------------------------------------
   One dot per team at its real rank. Dots overlap on purpose where a league is
   tightly packed -- that overlap IS the reading. A 2px ring in the surface
   colour keeps overlapping marks separable rather than merging into a blob. */
.csec{margin-bottom:18px}
.cnote{margin:0;padding:10px 15px 4px;font:12.5px/1.55 var(--sans);
  color:var(--ink2);max-width:80ch}
.cstrip{padding:6px 15px 4px}
.crow{display:grid;grid-template-columns:118px 1fr 34px 26px;gap:10px;
  align-items:center;padding:5px 0;border-bottom:1px solid var(--line)}
.crow:last-child{border-bottom:0}
.cnm{font:600 11.5px/1.2 var(--sans);color:var(--ink2);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctrack{position:relative;height:14px;border-radius:7px;
  background:linear-gradient(90deg,rgba(63,146,222,.16),rgba(63,146,222,.03))}
.cdot{position:absolute;top:4px;width:6px;height:6px;border-radius:50%;
  background:var(--ink3);box-shadow:0 0 0 2px var(--card);
  transform:translateX(-3px)}
.cdot.t25{background:#3F92DE;width:7px;height:7px;top:3.5px}
.cmed{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--amber);
  border-radius:1px;transform:translateX(-1px)}
.cmd{font:700 11.5px/1 var(--mono);color:var(--ink);text-align:right}
.ccount{font:11px/1 var(--mono);color:var(--ink3);text-align:right}
.cfoot{display:flex;justify-content:space-between;padding:8px 15px 12px;
  font:11px/1 var(--mono);color:var(--ink3)}
@media (max-width:560px){.crow{grid-template-columns:82px 1fr 30px 22px}}
/* ---- PROJECTED-WINS BAND ---------------------------------------------
   An interval, drawn as one. The band is the 80% range, the bright tick is the
   median, and the amber tick is what has ALREADY been won -- a fact rather than
   a projection, so it is a different colour and says so in the key. One axis:
   this team's own fixture count. */
.bandwrap{padding:12px 15px 10px;border-bottom:1px solid var(--line)}
.bandhd{display:flex;align-items:baseline;gap:8px;margin-bottom:9px}
.bandhd span{font:600 12px/1 var(--sans);color:var(--ink2)}
.bandhd b{font:700 20px/1 var(--mono);color:var(--ink)}
.bandhd i{font:11px/1 var(--mono);color:var(--ink3);font-style:normal}
.band{position:relative;height:14px;border-radius:7px;
  background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.02));
  border:1px solid var(--line)}
.bandfill{position:absolute;top:1px;bottom:1px;border-radius:6px;
  background:linear-gradient(90deg,
    color-mix(in oklab,#3F92DE 45%,transparent),
    color-mix(in oklab,#3F92DE 85%,transparent));
  transform-origin:left center;animation:cbin .55s cubic-bezier(.22,.9,.3,1) both}
.bandmed{position:absolute;top:-3px;bottom:-3px;width:3px;border-radius:2px;
  background:var(--ink);box-shadow:0 0 10px rgba(255,255,255,.45);
  transform:translateX(-1.5px)}
.bandwon{position:absolute;top:-3px;bottom:-3px;width:3px;border-radius:2px;
  background:var(--amber);transform:translateX(-1.5px)}
.bandft{display:flex;justify-content:space-between;align-items:center;gap:10px;
  margin-top:7px;font:11px/1.4 var(--mono);color:var(--ink3)}
.bandkey{text-align:center;flex:1}
.bandkey b{color:var(--ink2)}
.bandkey i.wonkey{display:inline-block;width:8px;height:8px;border-radius:2px;
  background:var(--amber);margin-right:5px;vertical-align:0}
/* ---- AT A GLANCE ------------------------------------------------------
   Four cards that answer what a team page is opened for: how they are going,
   how they have been going, what just happened, what is next. Sits directly
   under the name, above everything else. */
/* the previous meeting, on a fixture line */
.h2h{margin-left:auto;padding:2px 7px;border-radius:4px;white-space:nowrap;
  font:700 10px/1.5 var(--mono);letter-spacing:.03em}
.h2h.w{background:rgba(49,208,126,.14);color:var(--good)}
.h2h.l{background:rgba(255,95,110,.14);color:var(--bad)}
/* the head coach, directly under the programme's name -- where a team's
   identity lives, not buried in a table at the bottom */
.coachline{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
  margin:12px 0 0;padding:9px 14px;border-radius:10px;
  background:linear-gradient(90deg,rgba(120,180,255,.10),rgba(120,180,255,.02));
  border-left:3px solid var(--amber)}
.coachline .cl{font:700 9.5px/1 var(--mono);letter-spacing:.18em;
  text-transform:uppercase;color:var(--ink3)}
.coachline b{font:600 16px/1.2 var(--disp);color:var(--ink);letter-spacing:.01em}
.coachline .ct{font:11.5px/1.3 var(--mono);color:var(--ink3)}
.glance{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 18px}
.gl{padding:13px 15px;border-radius:12px;border:1px solid transparent;
  background-origin:border-box;background-clip:padding-box,border-box;
  background-image:
    linear-gradient(170deg,rgba(26,38,62,.94),rgba(12,19,33,.95)),
    linear-gradient(150deg,rgba(120,180,255,.36),rgba(255,199,44,.12) 48%,rgba(255,255,255,.03) 76%);
  display:flex;flex-direction:column;gap:5px;min-width:0}
.gll{font:700 9.5px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;
  color:var(--ink3)}
.glbig{font:600 27px/1 var(--disp);color:var(--ink);letter-spacing:.01em}
.glbig.glw{color:var(--good)}
.glbig.gll2{color:var(--bad)}
.glbig.glmuted{color:var(--ink3)}
.glnext{font:600 18px/1.15 var(--disp);color:var(--ink);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gls{font:11.5px/1.35 var(--mono);color:var(--ink3);
  overflow:hidden;text-overflow:ellipsis}
.glpick{font-style:normal;color:var(--good);font-weight:700}
.glform{display:flex;gap:3px;align-items:center;min-height:22px}
@media (max-width:760px){.glance{grid-template-columns:repeat(2,1fr)}}

/* a long list stops owning the page; the count says what is hidden */
.upc.clipped .gline:nth-of-type(n+7){display:none}
h3 .cnt{margin-left:8px;padding:2px 7px;border-radius:20px;
  background:rgba(120,180,255,.14);color:var(--ink2);
  font:700 10px/1.5 var(--mono)}
.moreb{display:block;width:calc(100% - 30px);margin:2px 15px 12px;padding:9px;
  border-radius:9px;border:1px solid var(--line2);cursor:pointer;
  background:rgba(120,180,255,.07);color:var(--ink2);
  font:600 12px/1 var(--sans);transition:background .15s ease,color .15s ease}
.moreb:hover{background:rgba(120,180,255,.14);color:var(--ink)}
/* ---- TABLE ROWS: A SIGNAL, NOT A STRIPE ------------------------------
   Hovering swapped the row's background, which reads as "this is a striped
   table" rather than "this row is selected". A lit edge slides in from the
   left instead -- the same language the team-colour bars already use -- and
   the row lifts a shade. Applies to every scrolling table on the page from one
   definition. */
tbody tr{position:relative;transition:background .14s ease}
tbody tr td:first-child{position:relative}
tbody tr td:first-child::after{content:"";position:absolute;left:0;top:0;bottom:0;
  width:2px;background:var(--amber);box-shadow:0 0 14px rgba(255,199,44,.85);
  transform:scaleY(0);transform-origin:center;transition:transform .16s ease}
tbody tr:hover td{background:rgba(120,180,255,.055)}
tbody tr:hover td:first-child::after{transform:scaleY(1)}
@media (prefers-reduced-motion:reduce){
  tbody tr td:first-child::after{transition:none}}

/* ---- THE TOP THREE LOOK LIKE THE TOP THREE ---------------------------
   A rank column where #1 and #180 are the same 13px monospace is a spreadsheet.
   The podium places get scale and light; everything below stays quiet, so the
   contrast does the work rather than colour everywhere. */
td.rk{font:700 14px/1 var(--mono);color:var(--ink3)}
tbody tr:nth-child(1) td.rk,
tbody tr:nth-child(2) td.rk,
tbody tr:nth-child(3) td.rk{font-size:19px;color:var(--ink)}
tbody tr:nth-child(1) td.rk{color:var(--amber);
  text-shadow:0 0 18px rgba(255,199,44,.55)}
/* ---- SECTION LABELS AS RIBBON, NOT AS SENTENCES -----------------------
   "Later today" and the lead paragraphs were plain text in the flow, so every
   band on the page began the same anonymous way. A scoreboard names its
   sections; this is that, in the ball's yellow, with a rule that runs out to
   the edge so the eye can find where one band stops and the next starts. */
.livehead{display:flex;align-items:center;gap:10px;margin:0 0 12px;
  font:700 11px/1 var(--mono);letter-spacing:.2em;text-transform:uppercase;
  color:var(--ink2)}
.livehead::after{content:"";flex:1;height:1px;
  background:linear-gradient(90deg,rgba(255,199,44,.5),transparent)}
.livehead b,.livehead .soon{position:relative;padding-left:13px;color:var(--ink)}
.livehead b::before,.livehead .soon::before{content:"";position:absolute;left:0;
  top:50%;transform:translateY(-50%);width:5px;height:5px;border-radius:1px;
  background:var(--amber);box-shadow:0 0 12px rgba(255,199,44,.9)}
.lead{position:relative;padding-left:14px}
.lead::before{content:"";position:absolute;left:0;top:3px;bottom:3px;width:2px;
  border-radius:1px;
  background:linear-gradient(180deg,var(--amber),rgba(91,168,245,.55),transparent)}

/* ---- THINGS ARRIVE, THEY DO NOT BLINK INTO EXISTENCE -------------------
   A short, staggered rise on the cards in a band. Capped at ten so a 600-row
   schedule does not spend six seconds animating, and off entirely under
   reduced-motion. */
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.cards .card{animation:rise .34s cubic-bezier(.22,.9,.3,1) both}
.cards .card:nth-child(1){animation-delay:.02s}
.cards .card:nth-child(2){animation-delay:.06s}
.cards .card:nth-child(3){animation-delay:.10s}
.cards .card:nth-child(4){animation-delay:.14s}
.cards .card:nth-child(5){animation-delay:.18s}
.cards .card:nth-child(6){animation-delay:.22s}
.cards .card:nth-child(n+7){animation-delay:.26s}
@media (prefers-reduced-motion:reduce){.cards .card{animation:none}}
/* ---- THE HERO --------------------------------------------------------
   Ambient light, a court motif at 5% and a podium of the current top three in
   their own school colours. The motion is deliberately small: one pulsing dot
   that means "this is live data", and a count-up on the three numbers on first
   paint. Nothing here animates on a loop -- a page you read every day should
   not have something moving in the corner of your eye forever. */
.hero{position:relative;overflow:hidden;border-radius:18px;margin:0 0 20px;
  padding:30px 30px;display:flex;gap:28px;align-items:center;
  justify-content:space-between;flex-wrap:wrap;
  background-image:
    radial-gradient(70% 140% at 8% 0%, rgba(91,168,245,.24), transparent 62%),
    radial-gradient(60% 130% at 92% 100%, rgba(255,199,44,.17), transparent 60%),
    linear-gradient(160deg, rgba(26,39,64,.97), rgba(10,16,29,.98)),
    linear-gradient(140deg,rgba(140,195,255,.55),rgba(255,199,44,.22) 40%,rgba(255,255,255,.04) 72%)}
/* the court: attack line + net, drawn once, sitting under everything */
/* ---- THE COURT ---------------------------------------------------------
   The previous one was two CSS gradients inside a rotated box: a rectangle with
   an off-centre cross through it, which is not a volleyball court and did not
   read as one. This is drawn to the REAL dimensions -- 18m x 9m, the net on the
   centre line, attack lines 3m either side of it -- as an SVG in a 180x90
   viewBox where one unit is a decimetre, then laid back in perspective.
   Everything on it is a line that exists on a court and nothing else is. */
/* THE COURT IS THE HERO'S SUBJECT, not a texture hidden behind the cards.
   Laid across the whole width at the bottom, seen from behind one baseline so
   the net runs across the middle distance -- the view from the stands. It is
   masked only at the far edge, where a real court would fall out of the light. */
/* ⚠ THE COURT GETS ITS OWN ROW. Twice I laid it behind the hero content and
   twice the net line drew straight through "THE 2026 SEASON" -- because to show
   any depth the far baseline has to rise, and that is exactly where the type
   is. Masks only hid the symptom. The hero is a grid now: the headline and
   podium on the top row, the floor on its own row beneath, so the court has
   room to recede and nothing has to be faded out of its way. */
.hero{display:grid;grid-template-columns:1fr auto;grid-template-rows:auto auto;
  gap:22px 28px;align-items:center;min-height:0}
.heroL{grid-column:1;grid-row:1}
.heroR{grid-column:2;grid-row:1}
.courtwrap{grid-column:1 / -1;grid-row:2;position:relative;height:104px;
  overflow:hidden;pointer-events:none;
  border-radius:10px;
  background:linear-gradient(180deg,rgba(8,14,28,0),rgba(91,168,245,.07));
  -webkit-mask-image:linear-gradient(to right,transparent,#000 8%,#000 92%,transparent);
  mask-image:linear-gradient(to right,transparent,#000 8%,#000 92%,transparent)}
.courtart{position:absolute;left:50%;bottom:-84px;width:60%;
  transform:translateX(-50%) perspective(300px) rotateX(60deg);
  transform-origin:bottom center;opacity:1}
/* The net sits at the depth the centre line reaches, so it is narrower than
   the near baseline -- that width IS the perspective. Tuned against the
   rendered floor rather than computed, because the floor's own projection
   depends on the wrapper's height. */
/* Placed on the centre line the floor actually draws, measured from the
   rendered court rather than guessed: that line lands 73px down a 104px band
   and spans 217px of a 1186px wrapper, so the net's base sits 31px up and it is
   18.3% wide. Its width IS the perspective -- a net as wide as the near
   baseline would be standing in the wrong place. */
/* The net's WIDTH is the court's width where the centre line falls -- measured
   from the rendered floor, 217px of an 1186px wrapper -- and its HEIGHT follows
   from the same scale rather than being chosen: the viewBox is 98 units wide by
   33 tall, so at 18.3% width the box is 33/98 as tall again. That keeps 2.24 m
   of net and the antenna's 10-foot reach in true proportion to the 9 m court
   beneath it. */
.netart{position:absolute;left:50%;transform:translateX(-50%);
  bottom:31px;width:18.3%;aspect-ratio:98 / 33;height:auto;opacity:.95;
  filter:drop-shadow(0 1px 10px rgba(120,180,255,.30))}
/* the hero's own content has to sit above the floor it is standing on */
.heroL,.heroR{position:relative;z-index:2}
.heroL{position:relative;z-index:1;min-width:min(100%,320px);flex:1 1 340px}
.eyebrow{display:flex;align-items:center;gap:8px;font:700 10.5px/1 var(--mono);
  letter-spacing:.22em;text-transform:uppercase;color:var(--ink3)}
.pulse{width:7px;height:7px;border-radius:50%;background:var(--good);
  box-shadow:0 0 0 0 rgba(49,208,126,.6);animation:pl 1.8s ease-in-out infinite}
@keyframes pl{0%{box-shadow:0 0 0 0 rgba(49,208,126,.55)}
  70%{box-shadow:0 0 0 9px rgba(49,208,126,0)}100%{box-shadow:0 0 0 0 rgba(49,208,126,0)}}
.herotitle{margin:11px 0 7px;font:600 clamp(28px,4.2vw,44px)/1 var(--disp);
  letter-spacing:.004em;color:var(--ink);text-transform:uppercase}
.herosub{margin:0;font:13px/1.6 var(--mono);color:var(--ink2);max-width:56ch}
.heroR{position:relative;z-index:1;display:flex;gap:12px;flex-wrap:wrap}
.pod{position:relative;display:flex;flex-direction:column;align-items:center;
  gap:3px;min-width:116px;padding:14px 14px 12px;border-radius:12px;
  background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.015));
  border:1px solid var(--line2);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06);
  transition:transform .2s ease,box-shadow .2s ease}
/* the school's own colour, as an edge -- carries identity without tinting text */
.pod::before{content:"";position:absolute;left:14px;right:14px;top:0;height:3px;
  border-radius:0 0 3px 3px;background:var(--tc)}
.pod:hover{transform:translateY(-2px);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 14px 30px -18px var(--tc)}
.pod .tlogo{width:26px;height:26px;margin:2px 0 1px}
.podrk{font:600 11px/1 var(--mono);color:var(--ink3)}
.podnm{font:600 14px/1.1 var(--disp);color:var(--ink);text-align:center;
  letter-spacing:.01em}
.podv{font:700 19px/1 var(--mono)}
.podv.pos{color:var(--good)}
.podv.neg{color:var(--bad)}
.podv.nil{color:var(--ink3)}
.podl{font:600 9px/1 var(--mono);color:var(--ink3);letter-spacing:.1em;
  text-transform:uppercase}
@media (prefers-reduced-motion:reduce){.pulse{animation:none}}
@media (max-width:560px){.hero{padding:20px 18px}.heroR{width:100%}
  .pod{flex:1 1 30%;min-width:0}}
/* ---- PAIRED BARS: what a team does vs what it allows ------------------
   Validated pair (see the render comment): both inside the dark lightness
   band, both above the chroma floor, dE 22.6 at worst under CVD, both over
   3:1 on this surface. Data-ends are rounded and anchored to the baseline;
   the two fills are separated by a surface gap so they never read as one bar. */
.cwrap{padding:4px 15px 12px}
.ckey{display:flex;gap:16px;padding:10px 15px 4px;font:600 11px/1 var(--sans);
  color:var(--ink2);letter-spacing:.03em}
.ckey i.sw{display:inline-block;width:10px;height:10px;border-radius:2px;
  margin-right:6px;vertical-align:-1px}
i.sw.own,i.cbf.own{background:#3F92DE}
i.sw.opp,i.cbf.opp{background:#C4763F}
.cbar{display:grid;grid-template-columns:112px 1fr;gap:12px;align-items:center;
  padding:7px 0;border-bottom:1px solid var(--line)}
.cbar:last-child{border-bottom:0}
.cbl{font:12.5px/1.25 var(--sans);color:var(--ink2)}
.cbt{display:flex;flex-direction:column;gap:2px;min-width:0}
.cbrow{display:grid;grid-template-columns:1fr 54px;gap:10px;align-items:center}
.cbtk{display:block;height:9px;min-width:0}
.cbf{display:block;height:9px;border-radius:2px 4px 4px 2px;
  transform-origin:left center;animation:cbin .5s cubic-bezier(.22,.9,.3,1) both}
.cbrow b{font:700 12px/1 var(--mono);color:var(--ink);text-align:right;
  white-space:nowrap}
@keyframes cbin{from{transform:scaleX(.02);opacity:.2}to{transform:scaleX(1);opacity:1}}
@media (prefers-reduced-motion:reduce){.cbf{animation:none}}
td.wh{font-size:12.5px;line-height:1.35;color:var(--ink2);max-width:280px}
td.wh b{display:block;font-weight:650;color:var(--ink);font-size:12.5px}
td.wh .wc{display:block;color:var(--ink3);font:11.5px/1.3 var(--mono)}
td.wh .wu{color:var(--ink3);font-style:italic}
.kind{display:inline-block;white-space:nowrap;margin-right:7px;padding:2px 6px;border-radius:3px;
  font:700 9.5px/1.5 var(--mono);letter-spacing:.06em;text-transform:uppercase;
  vertical-align:2px}
.kind.cf{background:color-mix(in oklab,var(--navy) 12%,transparent);color:var(--navy)}
.kind.nc{background:var(--sand);color:var(--ink2)}
/* A named event is the one that changes what the fixture MEANS -- an August
   tournament on a neutral floor is not a road trip -- so it gets the ball's
   yellow and the other two stay quiet. */
.kind.ev{background:var(--amber-bg);color:#FFD97A;border:1px solid var(--amber)}
.kind.nu{background:color-mix(in oklab,var(--amber) 14%,transparent);color:#FFD97A}
#sbody tr.rkd td:first-child{box-shadow:inset 3px 0 0 var(--line2)}
#sbody tr.both td:first-child{box-shadow:inset 3px 0 0 var(--amber)}
#sbody tr.both .tm{font-weight:700}
.t25 td.form{white-space:nowrap;padding-left:14px}
.fw,.fl{display:inline-block;width:19px;height:19px;line-height:19px;text-align:center;
  border-radius:2px;font:700 10.5px/19px var(--mono);margin-right:3px}
.fw{background:#0C2A1C;color:#31D07E;border:1px solid #1F5B3C}
.fl{background:#2B1114;color:#FF5F6E;border:1px solid #5E2229}
/* A result against a ranked side is marked -- it is stronger evidence. */
.fw.frk{background:#31D07E;color:var(--ink-on-accent);border-color:#31D07E}
.fl.frk{background:#FF5F6E;color:var(--ink-on-accent);border-color:#FF5F6E}
.noform{font:400 11.5px/1 var(--sans);color:var(--ink3)}
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
.mv-up{color:#31D07E;font:700 11px/1 var(--mono)}
.mv-dn{color:#FF5F6E;font:700 11px/1 var(--mono)}
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
.seasonwarn{background:var(--amber-bg);border:1px solid #6B551C;border-left:4px solid var(--amber);
  border-radius:2px;padding:11px 13px;margin:0 0 12px;font-size:13px;color:#1A1200;max-width:760px}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:3px;
  overflow:hidden;margin:0 0 14px;background:var(--card)}
.segb{appearance:none;border:0;background:transparent;font:700 11.5px/1 var(--sans);
  letter-spacing:.06em;text-transform:uppercase;color:var(--ink2);padding:9px 14px;
  cursor:pointer;border-right:1px solid var(--line)}
.segb:last-child{border-right:0}
.segb:hover{color:var(--ink)}
.segb.on{background:var(--navy);color:var(--ink-on-accent)}
.segb:focus-visible{outline:2px solid var(--amber);outline-offset:-2px}
.mv{display:inline-block;margin-left:5px;font:700 9.5px/1 var(--mono);vertical-align:1px}
.mv.up{color:#31D07E}
.mv.dn{color:#FF5F6E}
.mv.sm{color:var(--ink3)}
.sysbadge{font:700 10px/1 var(--mono);color:var(--ink-on-accent);background:var(--navy);
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
.rrow{display:grid;grid-template-columns:1fr auto;grid-template-areas:
  "av stat" "meta stat";align-items:center;gap:0 10px;
  padding:7px 9px 7px 6px;border-left:3px solid transparent;
  border-bottom:1px solid var(--line);transition:background .12s ease}
.rrow:last-child{border-bottom:0}
.rrow:hover{background:var(--alt)}
/* A starter is marked by a bar rather than a fill: the fill was too faint to
   read, and the legend under the table names this bar explicitly. */
.rrow--starter{border-left-color:#31D07E}
.rrow--starter .rname{font-weight:700}
.ravatar{grid-area:av;display:flex;align-items:center;min-width:0}
.rrow .pnm{font-size:15px}
.rrow--starter .pnm{font-weight:700}
/* A player's name opens her match log -- a roster you cannot click
   through from is a list, not a page. */
.rrow{cursor:pointer}
.rrow:hover .pnm{text-decoration:underline;text-underline-offset:2px}
.rnum{grid-area:num;font:700 11.5px/1 var(--mono);color:var(--ink3);text-align:right}
.rname{grid-area:name;font-size:13.5px;font-weight:600}
.rmeta{grid-area:meta;font-size:11.5px;color:var(--ink2);margin-top:3px;padding-left:50px}
.rstat{grid-area:stat;font:700 14px/1 var(--mono);color:var(--navy);text-align:right;
  white-space:nowrap;padding-left:10px}
.rstat em{display:block;font:600 9px/1 var(--sans);letter-spacing:.05em;
  text-transform:uppercase;color:var(--ink3);font-style:normal;margin-top:3px}
.rstat .none{color:var(--ink3);font-weight:400}
h3 .h3n{font:700 10px/1 var(--mono);color:var(--ink3);background:var(--alt);
  border-radius:20px;padding:3px 7px;margin-left:7px;vertical-align:2px}
@media (max-width:560px){
  .rrow{grid-template-columns:1fr auto;padding-right:4px}
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
.brkside.fav{background:#12233C}
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
.chip.ours{background:#12233C;border-color:#2A4570;color:var(--navy)}
.tcols{display:grid;grid-template-columns:1.25fr 1fr;gap:14px;align-items:start}
@media(max-width:900px){.tcols{grid-template-columns:1fr}}
.tsec{background-image:
    linear-gradient(176deg,rgba(26,38,62,.92),rgba(11,17,30,.94)),
    linear-gradient(150deg,rgba(120,180,255,.34),rgba(255,199,44,.12) 46%,rgba(255,255,255,.03) 72%);
  overflow:hidden;
  box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 18px 40px -28px rgba(0,0,0,.9)}
.tsec h3{margin:0;padding:12px 15px;font:700 11.5px/1 var(--sans);letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink2);
  background:linear-gradient(180deg,rgba(30,42,66,.9),rgba(16,24,40,.9));
  border-bottom:1px solid var(--line);position:relative}
/* A conference table earns a hairline of the ball's yellow at its head -- the
   one piece of chrome that says "this is a section" without a heavier device. */
.tsec h3::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;
  background:linear-gradient(90deg,var(--amber),color-mix(in oklab,var(--amber) 10%,transparent))}
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
/* ⚠ HEADS WERE BEING CROPPED OFF. Every roster photo the feed serves is a 2:3
   portrait (measured: 1332x2000 on every one loaded, aspect 0.666 across the
   board). Covering a 2:3 image into a SQUARE hides a third of its height, and
   the default `object-position: 50% 50%` splits that evenly top and bottom --
   so the visible window runs from ~17% to ~83% of the frame and takes the top
   of the head with it. Biasing the window upward keeps the face: at 18% the
   window starts around 6% of the frame instead of 17%.
   One value is safe here precisely BECAUSE the shape is uniform; if mixed
   aspect ratios ever arrive this needs revisiting rather than re-tuning. */
.mug{width:34px;height:34px;border-radius:50%;object-fit:cover;
  object-position:50% 18%;flex:none;
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
  <!-- THE HERO. The page used to open straight into a date picker. This is the
       first thing seen, so it carries the three things worth knowing on arrival:
       what the season is, who is on top, and where tonight stands. Every figure
       is read from the same payload the tabs use -- nothing here is written in
       advance (R1) and nothing is invented (R5). -->
  <div class="hero">
    <div class="heroL">
      <div class="eyebrow"><span class="pulse"></span>{{HERO_EYEBROW}}</div>
      <h2 class="herotitle">{{HERO_TITLE}}</h2>
      <p class="herosub">{{HERO_SUB}}</p>
    </div>
    <div class="heroR">{{HERO_PODIUM}}</div>
    <div class="courtwrap"><svg class="courtart" viewBox="-5 -5 100 190" aria-hidden="true">
      <defs>
        <linearGradient id="ctf" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#5BA8F5" stop-opacity=".08"/>
          <stop offset="1" stop-color="#5BA8F5" stop-opacity=".30"/>
        </linearGradient>
      </defs>
      <!-- ⚠ ORIENTATION IS THE WHOLE GEOMETRY. We are looking DOWN the court
           from behind one baseline, so the 9m width runs left-to-right and the
           18m length recedes: 90 wide by 180 deep, one unit per decimetre. The
           first version had these swapped -- 18m across and 9m deep, a view
           from the SIDE -- and then ran the net along the length, which is why
           it read as a stray line rather than a net. -->
      <rect x="0" y="0" width="90" height="180" fill="url(#ctf)"/>
      <rect x="0" y="0" width="90" height="180" fill="none"
            stroke="#dbe9ff" stroke-opacity=".85" stroke-width="1.3"/>
      <!-- attack lines, 3m either side of the net -->
      <line x1="0" y1="60" x2="90" y2="60" stroke="#dbe9ff" stroke-opacity=".62" stroke-width="1"/>
      <line x1="0" y1="120" x2="90" y2="120" stroke="#dbe9ff" stroke-opacity=".62" stroke-width="1"/>
      <!-- the centre line the net stands on -->
      <line x1="0" y1="90" x2="90" y2="90" stroke="#dbe9ff" stroke-opacity=".5" stroke-width=".9"/>
    </svg>
      <!-- ---- THE NET, TO THE ACTUAL SPECIFICATION ----------------------
           Same scale as the floor: ONE UNIT = ONE DECIMETRE, so the 9m court is
           90 units and everything below is the real measurement rather than a
           drawing that merely suggests a net.
             net height (women)  2.24 m   -> top edge 22.4 units above the floor
             mesh depth          1.00 m   -> 10 units
             mesh squares        10 cm    -> 1 unit
             top tape             7 cm    -> 0.7 units, white doubled canvas
             bottom band          5 cm    -> 0.5 units
             antennae            1.80 m   -> 18 units, 10 cm stripes (1 unit)
             antenna reach       80 cm above the net -> the top lands at
                                 2.24 + 0.80 = 3.04 m, which is 9 ft 11.6 in:
                                 the 10 feet Cody asked for, and it comes out of
                                 the measurements rather than being set to it.
           The antennae sit on the outer edge of the side bands, above the
           sidelines, on opposite sides of the net -- which is why one is drawn
           in front of the mesh and one behind. y increases downward, so the
           floor is y=32 and the antenna tops are near y=1.6. -->
      <svg class="netart" viewBox="-4 0 98 33" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <pattern id="mesh10" width="1" height="1" patternUnits="userSpaceOnUse">
            <path d="M1 0H0V1" fill="none" stroke="#eaf2ff" stroke-opacity=".38"
                  stroke-width=".08"/>
          </pattern>
          <linearGradient id="antw" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#e8eef7"/>
          </linearGradient>
        </defs>
        <!-- posts, set outside the sidelines, carrying the net at 2.24 m -->
        <rect x="-2.6" y="9.2" width="1.3" height="22.8" fill="#c9d8ee" fill-opacity=".55"/>
        <rect x="91.3" y="9.2" width="1.3" height="22.8" fill="#c9d8ee" fill-opacity=".55"/>
        <!-- the mesh: 1 m deep, 10 cm squares -->
        <rect x="0" y="9.6" width="90" height="10" fill="url(#mesh10)"/>
        <!-- 7 cm white tape along the top, 5 cm band beneath -->
        <rect x="0" y="9.6" width="90" height=".7" fill="#f7fbff" fill-opacity=".92"/>
        <rect x="0" y="19.1" width="90" height=".5" fill="#dce8f8" fill-opacity=".5"/>
        <!-- side bands, 5 cm wide, on the sidelines -->
        <rect x="0" y="9.6" width=".5" height="10" fill="#f7fbff" fill-opacity=".8"/>
        <rect x="89.5" y="9.6" width=".5" height="10" fill="#f7fbff" fill-opacity=".8"/>
        <!-- antennae: 1.8 m of 10 cm red/white stripes, 80 cm proud of the net -->
        <g>
          <rect x="-.35" y="1.6" width=".7" height="18" fill="url(#antw)"/>
          <rect x="89.65" y="1.6" width=".7" height="18" fill="url(#antw)"/>
        </g>
        <g fill="#D6291F">
          <rect x="-.35" y="1.6" width=".7" height="1"/><rect x="-.35" y="3.6" width=".7" height="1"/>
          <rect x="-.35" y="5.6" width=".7" height="1"/><rect x="-.35" y="7.6" width=".7" height="1"/>
          <rect x="-.35" y="9.6" width=".7" height="1"/><rect x="-.35" y="11.6" width=".7" height="1"/>
          <rect x="-.35" y="13.6" width=".7" height="1"/><rect x="-.35" y="15.6" width=".7" height="1"/>
          <rect x="-.35" y="17.6" width=".7" height="1"/>
          <rect x="89.65" y="1.6" width=".7" height="1"/><rect x="89.65" y="3.6" width=".7" height="1"/>
          <rect x="89.65" y="5.6" width=".7" height="1"/><rect x="89.65" y="7.6" width=".7" height="1"/>
          <rect x="89.65" y="9.6" width=".7" height="1"/><rect x="89.65" y="11.6" width=".7" height="1"/>
          <rect x="89.65" y="13.6" width=".7" height="1"/><rect x="89.65" y="15.6" width=".7" height="1"/>
          <rect x="89.65" y="17.6" width=".7" height="1"/>
        </g>
      </svg>
    </div>
  </div>
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
  <div class="cards" id="resultcards">{{SCORE_CARDS}}</div>
</section>

<section id="v-top25" hidden>
  <h2 class="vh">Digby&rsquo;s Top 25 &mdash; {{T25_SEASON}}</h2>
  <p class="tabhint">{{T25_LEAD}}</p>
  <div class="scroll"><table class="t25">
    <thead><tr>
      <th>#</th><th>Team</th><th title="how the rank changed">{{T25_MOVEHEAD}}</th>
      <th>Conf</th><th>Record</th><th class="l" title="most recent results, newest last">Form</th>
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
    <thead><tr><th>#</th><th class="l">Player</th><th class="l">Team</th>
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
  <div id="confstrength"></div>
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
      <th>Sets</th><th>Kills</th><th>Hit%</th>
      <th title="assists -- the setter's number, and the one this table used to omit">Ast</th>
      <th>Digs</th><th>Blk</th><th>Aces</th>
      <th>Pts/set</th></tr></thead>
    <tbody id="pbody"></tbody></table></div></div>
</section>

<section id="v-bracket" hidden>
  <p class="lead">A projected 64-team field: {{N_AQ}} conference champions plus the
  next best at large, ordered by our 2026 projection. <b>32 teams are seeded</b>
  and placed four to a line, so the bracket carries four&nbsp;#1s down to
  four&nbsp;#8s &mdash; the format since 2022. The number on a row is that
  <b>seed line</b>; its national seed (1&ndash;32) is on the tooltip.</p>
  <p class="lead"><b>What this bracket does not know: geography.</b> The
  committee brackets to NCAA travel rules &mdash; the top 16 seeds host the
  first two rounds, and a team inside the bus radius of its site travels by
  road rather than by air, which moves teams between pods. We hold each venue's
  city and state but no distances, so pairings here are the seed order alone
  (seed <i>N</i> against the <i>N</i>th-from-last unseeded team) and will differ
  from the real 2026 draw. Later rounds are left empty rather than projected.</p>
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
  <p class="lead"><b>2026 schedule.</b> {{N_SCHED}} fixtures from today forward,
  straight from ncaa.com. Each row says <b>where</b> it is played and whether it
  is a conference match, a non-conference match or part of a named event. A
  neutral floor reads <b>vs</b> rather than <b>at</b>. A venue the feed has not
  published yet says so rather than being guessed from the home team.
  A tournament is named only where the name was supplied by hand &mdash; a
  neutral floor whose event has no name says <b>neutral site</b> rather than
  borrowing the building's name for it.</p>
  <div class="ctl">
    <input type="search" id="sq" placeholder="Search a team&hellip;">
    <select id="srank">
      <option value="all">Every fixture</option>
      <option value="one">A ranked team</option>
      <option value="both">Top 25 v Top 25</option>
    </select>
    <span class="count" id="scnt"></span>
  </div>
  <div class="panel"><div class="scroll"><table>
    <thead><tr><th class="l">Date</th><th>Time</th><th class="l">Visitor</th>
      <th></th><th class="l">Home</th>
      <th class="l" title="venue from the feed; conference, non-conference or a named event">Where</th>
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
<div id="lbx" role="dialog" aria-modal="true" aria-label="Player photo" hidden>
  <button type="button" aria-label="Close">&times;</button>
  <figure><img alt=""><figcaption></figcaption></figure>
</div>
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
  /* ⚠ toISOString() IS UTC, AND THIS PAGE IS PACIFIC. At 9pm Pacific it is
     already tomorrow in UTC, so this band labelled the NEXT day's fixtures
     "Later today" -- caught on screen at 9:13pm PT showing 2026-08-24 matches
     under a heading that said today. Everything else on the page converts from
     the epoch into America/Los_Angeles; this was the one clock that did not.
     en-CA gives YYYY-MM-DD directly, so there is no re-parsing to drift. */
  const todayISO = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  /* ⚠ AND THE HEADING HAS TO MATCH WHAT IS SHOWN. The filter was `>= today`,
     so the band held every future fixture in the window under the words "Later
     today". Today's matches are today's; if there are none, the next date that
     HAS fixtures is shown and the heading says which day it is rather than
     claiming it is this one. */
  const pre = all.filter(g => g.state === 'pre' && g.date >= todayISO)
                 .sort((a, b) => (a.date + (a.time || '')).localeCompare(b.date + (b.time || '')));
  const todays = pre.filter(g => g.date === todayISO);
  const soon = todays.length ? todays
                            : pre.filter(g => pre.length && g.date === pre[0].date);
  const tbox = document.getElementById('today');
  if (!soon.length) { tbox.hidden = true; }
  else {
    tbox.hidden = false;
    document.querySelector('#today .soon').textContent =
      todays.length ? 'Later today' : 'Next up';
    document.getElementById('todaymeta').textContent =
      soon.length + ' scheduled' + (todays.length ? '' : ' \u00b7 ' + soon[0].date);
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
    const known = new Set([...document.querySelectorAll('#resultcards [data-gid]')]
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
    /* AT 0-0 NOBODY IS WINNING. `away > home` is false when the sets are level,
       so the "not away" branch bolded the HOME team from the first whistle --
       Kentucky-Pittsburgh showed Pittsburgh as the leader at 0-0. Three states,
       not two. */
    const lead = +g.away_sets === +g.home_sets ? 0 : (+g.away_sets > +g.home_sets ? -1 : 1);
    const venue = g.venue || 'venue not reported';
    return '<div class="card islive"><div class="cd">' +
      (g.period || 'in progress') + '</div>' +
      '<div class="mt"><div class="side' + (lead < 0 ? ' win' : '') + '">' +
        rank(g.away_rank) + logo(g.away) + g.away + '<b>' + g.away_sets + '</b></div>' +
      '<div class="side' + (lead > 0 ? ' win' : '') + '">' +
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

/* PLAYER AVATARS. Pose = her real position, colour = her school's own logo
 colour. Shown only where there is NO photograph -- a real picture always
 wins. Nothing here claims anything about the person: no face, no hair, no
 skin tone. The libero is drawn in the accent because the rules require a
 contrasting jersey, which is the one thing the picture actually tells you.
 Shapes are generated from scripts/avatars.py so the preview sheet and this
 page cannot drift. */
const AV = {"poses":{"S":{"body":"<circle cx=\"20\" cy=\"13\" r=\"3.9\"/><path d=\"M20 17.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M16.6 19.6 14.6 12.8M23.4 19.6l2-6.8\"/>","hands":[[14.2,11.8],[25.8,11.8]],"ball":[20,7.6,3.2]},"MB":{"body":"<circle cx=\"20\" cy=\"15\" r=\"3.9\"/><path d=\"M20 19.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M14.4 22.4 13.6 9.6M25.6 22.4l.8-12.8\"/>","hands":[[13.4,8.4],[26.6,8.4]],"ball":null},"OH":{"body":"<circle cx=\"21.5\" cy=\"14\" r=\"3.9\"/><path d=\"M21.5 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M25 20.4 30 13.4\"/><path d=\"M18 21.4 10.8 25.4\"/>","hands":[[30.6,12.4],[9.8,26]],"ball":[32.4,7.4,2.9]},"L/DS":{"body":"<circle cx=\"23\" cy=\"15.5\" r=\"3.9\"/><path d=\"M23 20c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M19.8 22.8 10.4 28.4M25.6 23.4 10.4 28.4\"/>","hands":[[9.4,29]],"ball":null},"OPP":{"body":"<circle cx=\"21.5\" cy=\"14\" r=\"3.9\"/><path d=\"M21.5 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M25 20.4 30 13.4\"/><path d=\"M18 21.4 10.8 25.4\"/>","hands":[[30.6,12.4],[9.8,26]],"ball":[32.4,7.4,2.9]},"RS":{"body":"<circle cx=\"21.5\" cy=\"14\" r=\"3.9\"/><path d=\"M21.5 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M25 20.4 30 13.4\"/><path d=\"M18 21.4 10.8 25.4\"/>","hands":[[30.6,12.4],[9.8,26]],"ball":[32.4,7.4,2.9]},"DS":{"body":"<circle cx=\"23\" cy=\"15.5\" r=\"3.9\"/><path d=\"M23 20c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M19.8 22.8 10.4 28.4M25.6 23.4 10.4 28.4\"/>","hands":[[9.4,29]],"ball":null},"L":{"body":"<circle cx=\"23\" cy=\"15.5\" r=\"3.9\"/><path d=\"M23 20c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M19.8 22.8 10.4 28.4M25.6 23.4 10.4 28.4\"/>","hands":[[9.4,29]],"ball":null}},"unknown":{"body":"<circle cx=\"20\" cy=\"14\" r=\"3.9\"/><path d=\"M20 18.6c2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2c0-2.6 1.5-4.4 4.4-4.4z\"/>","limbs":"<path d=\"M16.4 21.6 13.4 27.4M23.6 21.6l3 5.8\"/>","hands":[],"ball":null},"libero":["L/DS","L","DS"],"neutral":"#9A8F7D","onNeutral":"#0E1524"};
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

/* ONE PLAYER CELL, used by the stats table, the roster and anywhere else a
 person is named. Photo (or her position avatar), name, and number + position
 underneath in small type -- the identity block a sports site repeats
 everywhere. Defined once so the three places cannot drift apart. */
function playerCell(o, size) {
size = size || 34;
const meta = [o.num ? '#' + o.num : '', o.pos || ''].filter(Boolean).join(' \u00b7 ');
const face = o.photo
  ? '<img class="pmug" src="' + o.photo + '" alt="" loading="lazy" ' +
    'style="width:' + size + 'px;height:' + size + 'px" ' +
    'onerror="this.replaceWith(document.createRange()' +
    '.createContextualFragment(this.dataset.fb))" data-fb=\'' +
    avatar(o.pos, o.team, size) + '\'>'
  : avatar(o.pos, o.team, size);
/* AVCA honours. First Team gets the loudest treatment, then Second and Third
   -- the order the award itself has. Only the most recent shows inline; the
   full history is on her own page. Sized like a footnote, not a trophy. */
const RANKED = ['Player of the Year', 'Freshman of the Year', 'First Team',
                'Second Team', 'Third Team', 'Honorable Mention'];
const best = (list) => (list || []).slice().sort(
  (x, y) => (RANKED.indexOf(x.honour) + 99 * 0) - (RANKED.indexOf(y.honour)) ||
            y.season - x.season)[0];
const aa = best(o.aa);
const short = {'Player of the Year': 'POY', 'Freshman of the Year': 'FOY',
               'First Team': 'AA1', 'Second Team': 'AA2', 'Third Team': 'AA3',
               'Honorable Mention': 'HM'};
const badge = aa
  ? '<span class="aa ' + (aa.national ? 'aaNat' : 'aa' +
      (aa.honour || '').replace(/[^A-Za-z]/g, '').slice(0, 5)) +
    '" title="AVCA ' + aa.honour + (aa.national ? '' : ' All-American') + ', ' + aa.season +
    (o.aa.length > 1 ? ' \u2014 ' + o.aa.length + ' selections' : '') + '">' +
    (short[aa.honour] || 'AA') + '</span>'
  : '';
return '<span class="pcell">' + face +
  '<span class="pinfo"><span class="pnm">' + o.name + badge + '</span>' +
  (meta ? '<span class="pmeta">' + meta + '</span>' : '') +
  '</span></span>';
}
function logo(team, cls) {
  const u = LOGOS[team];
  return u ? '<img class="tlogo ' + (cls || '') + '" src="' + u + '" alt="" ' +
             'onerror="this.style.display=\'none\'">' : '';
}
const n1 = v => (v === null || v === undefined) ? '—' : v;
/* HITTING PERCENTAGE IS WRITTEN WITHOUT ITS LEADING ZERO -- .358, the way
   every box score in the sport prints it. The Players tab was the one
   place still showing 0.358, which reads as a different quantity from the
   .358 three tabs over. A negative keeps its sign in front of the dot. */
const pct = v => (v === null || v === undefined) ? '\u2014'
  : (v < 0 ? '-' : '') + Math.abs(v).toFixed(3).replace(/^0/, '');

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
  /* The column the table is sorted by carries the value scale, exactly as the
     Stats tab does -- 4.50 and 2.86 should not look alike in a list of 129. */
  const pv = rows.slice(0, 300).map(p => p.pps);
  const plo = pv.length ? Math.min.apply(null, pv) : 0;
  const phi = pv.length ? Math.max.apply(null, pv) : 1;
  document.getElementById('pbody').innerHTML = rows.slice(0, 300).map(p =>
    '<tr class="prow" data-k="' + p.team + '|' + p.name + '">' +
    '<td class="tm">' + playerCell(p, 32) + '</td>' +
    '<td class="cf">' + logo(p.team) + p.team + '</td>' +
    '<td class="n">' + (p.pos || '') + '</td><td class="n">' + p.sets + '</td>' +
    '<td class="n">' + p.k + '</td><td class="n">' + pct(p.hit) + '</td>' +
    '<td class="n">' + (p.ast || 0) + '</td>' +
    '<td class="n">' + p.digs + '</td><td class="n">' + (p.bs + p.ba * 0.5) + '</td>' +
    '<td class="n">' + (p.aces || 0) + '</td>' +
    hcell(p.pps, p.pps.toFixed(2), plo, phi, 'high', 'seq') + '</tr>').join('');
  document.getElementById('pcnt').textContent = rows.length + ' players';
  if (rows.length === 1) showPlayer(rows[0]);
}
function showPlayer(p) {
  const face = p.photo
    ? '<img class="phero" src="' + p.photo + '" alt="" ' +
      'onerror="this.replaceWith(document.createRange()' +
      '.createContextualFragment(this.dataset.fb))" data-fb=\'' +
      avatar(p.pos, p.team, 72) + '\'>'
    : avatar(p.pos, p.team, 72);
  document.getElementById('playercard').innerHTML =
    '<div class="thead phead">' + face + '<div><h2>' + logo(p.team, 'lg') + p.name + '</h2>' +
    '<div class="sub">' + p.team + (p.pos ? ' · ' + p.pos : '') +
      (p.num ? ' · #' + p.num : '') + '</div>' +
    '<div class="chips">' +
      '<span class="chip ours">Pts/set <b>' + p.pps.toFixed(2) + '</b></span>' +
      '<span class="chip">Kills/set <b>' + p.kps.toFixed(2) + '</b></span>' +
      '<span class="chip">Hit% <b>' + pct(p.hit) + '</b></span>' +
      '<span class="chip">Digs/set <b>' + p.dps.toFixed(2) + '</b></span>' +
      '<span class="chip">Sets <b>' + p.sets + '</b></span>' +
    '</div></div></div>' +
    (p.aa && p.aa.length
      ? '<div class="tsec"><h3>AVCA honours</h3><div class="body">' +
        p.aa.map(x => '<div class="plrow"><span class="nm">' + x.honour +
          (x.national ? '<span class="wentto">national award</span>' : '') +
          '</span><span class="rt">' + x.season + '</span></div>').join('') +
        '</div><div class="tnote">From the AVCA\u2019s published All-America ' +
        'workbook. Only the last two seasons are loaded \u2014 an older honour ' +
        'belongs to somebody who may not be on a 2026 roster.</div></div>'
      : '') +
    '<div class="tsec"><h3>Match log</h3><div class="body">' +
    p.games.map(g => '<div class="gline"><span class="dt">' + (g.d || '') + '</span>' +
      '<span class="op">' + (g.opp || '') + '</span>' +
      /* assists only appear when there are any, so a hitter's line is not
         padded with "0s" -- but a setter's night is no longer invisible */
      '<span class="ss pgl">' + g.k + 'k · ' + g.e + 'e · ' + g.ta + 'ta · ' +
      pct(g.hit) + ' · ' + g.digs + 'd · ' + g.aces + 'a' +
      /* blocks by the NCAA convention -- a solo counts one, an assist a half --
         the same arithmetic the team totals and Pts/set already use, so a
         middle's night is not the one line on the page that omits her work */
      ((g.bs + g.ba * 0.5) ? ' · ' + (g.bs + g.ba * 0.5) + 'b' : '') +
      (g.ast ? ' · ' + g.ast + ' ast' : '') + '</span>' +
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
const RESULTS = {{RESULTS_JSON}};
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
/* Form pills for the standings, built from RESULTS. The Top 25 builds the same
   strip server-side from the same source; both read one results list, so they
   cannot disagree. */
const FORM = (() => {
  const by = {};
  (RESULTS || []).forEach(g => {
    if (g.away_sets === null || g.home_sets === null) return;
    [[g.away, g.home, g.away_sets, g.home_sets],
     [g.home, g.away, g.home_sets, g.away_sets]].forEach(([me, them, mine, theirs]) => {
      (by[me] = by[me] || []).push({won: mine > theirs, opp: them,
                                    score: mine + '-' + theirs});
    });
  });
  return by;
})();
function formPills(team, n) {
  const gs = FORM[team] || [];
  if (!gs.length) return '<span class="noform" title="no results yet">&mdash;</span>';
  return gs.slice(-(n || 5)).map(g =>
    '<span class="' + (g.won ? 'fw' : 'fl') + '" title="' +
    (g.won ? 'beat ' : 'lost to ') + g.opp + ' ' + g.score + '">' +
    (g.won ? 'W' : 'L') + '</span>').join('');
}

function renderStandings() {
  const only = stsel.value;
  const confs = only ? [only] : Object.keys(STANDINGS).sort();
  /* ONE SCALE ACROSS EVERY CONFERENCE, not one per table. A per-table scale
     would make the best team in a weak league look identical to the best team
     in the ACC, which is the opposite of what a differential is for. Symmetric
     about zero so +2 and -2 are the same distance from neutral. */
  let dmax = 0;
  Object.keys(STANDINGS).forEach(c => STANDINGS[c].forEach(r => {
    if (r.diff !== null && r.diff !== undefined) dmax = Math.max(dmax, Math.abs(r.diff));
  }));
  dmax = dmax || 1;
  document.getElementById('standings').innerHTML =
    '<div class="stgrid">' + confs.map(c => {
      const rows = STANDINGS[c];
      return '<div class="tsec"><h3>' + c + '</h3><div class="body">' +
        '<table><thead><tr><th class="l">Team</th><th>Conf</th><th>Overall</th>' +
        '<th class="l" title="last five, oldest first">Form</th>' +
        '<th title="points won minus points allowed, per set">+/-</th>' +
        '<th>Rk</th></tr></thead><tbody>' +
        rows.map(r => {
          const diff = r.diff === undefined ? null : r.diff;
          return '<tr><td class="tm">' + logo(r.team) + r.team + '</td>' +
          '<td class="n">' + r.cw + '-' + r.cl + '</td>' +
          '<td class="n">' + r.w + '-' + r.l + '</td>' +
          '<td class="form">' + formPills(r.team) + '</td>' +
          (diff === null
            ? '<td class="n">&mdash;</td>'
            : hcell(diff, (diff >= 0 ? '+' : '') + diff.toFixed(2),
                    -dmax, dmax, 'high', 'dv fill')) +
          '<td class="n hi">' + r.rank + '</td></tr>';
        }).join('') +
        '</tbody></table></div></div>';
    }).join('') + '</div>';
  document.getElementById('stcnt').textContent = confs.length + ' conferences';
  renderConfStrength(confs);
}

/* ---- HOW STRONG IS EACH CONFERENCE -----------------------------------------
   A strip of every member's national rank, one row per league, sorted by the
   league's MEDIAN. A single bar of the median would hide the thing worth
   seeing: whether a conference is top-heavy (two contenders and a long tail) or
   genuinely deep. Every dot is one real team at its real rank -- no smoothing,
   no bucketing, nothing modelled here that is not already on the Rankings tab.
   One axis, 1 on the left, and it is stated. Teams inside the top 25 are marked
   so the eye can find them without colour carrying the whole message. */
function renderConfStrength(confs) {
  const host = document.getElementById('confstrength');
  if (!host) return;
  const rows = confs.map(c => {
    const rk = (STANDINGS[c] || []).map(r => r.rank).filter(v => v).sort((a, b) => a - b);
    if (!rk.length) return null;
    const mid = rk.length % 2 ? rk[(rk.length - 1) / 2]
                              : (rk[rk.length / 2 - 1] + rk[rk.length / 2]) / 2;
    return { conf: c, ranks: rk, median: mid, n: rk.length, best: rk[0] };
  }).filter(Boolean).sort((a, b) => a.median - b.median);
  if (!rows.length) { host.innerHTML = ''; return; }
  const MAX = Math.max.apply(null, rows.map(r => r.ranks[r.ranks.length - 1]));
  const pc = v => ((v - 1) / Math.max(1, MAX - 1) * 100);
  host.innerHTML =
    '<div class="tsec csec"><h3>Conference strength</h3>' +
    '<p class="cnote">Every member at its national rank, best on the left. ' +
    'Leagues are ordered by their <b>median</b> &mdash; the dot spread is the ' +
    'part worth reading: two contenders and a long tail is a different league ' +
    'from a deep one. Filled dots are inside the top 25.</p>' +
    '<div class="cstrip">' + rows.map(r =>
      '<div class="crow"><span class="cnm" title="' + r.conf + ' \u2014 ' + r.n +
        ' teams, median rank ' + r.median + '">' + r.conf + '</span>' +
      '<span class="ctrack">' +
        r.ranks.map(v => '<i class="cdot' + (v <= 25 ? ' t25' : '') +
          '" style="left:' + pc(v).toFixed(2) + '%" title="#' + v + '"></i>').join('') +
        '<i class="cmed" style="left:' + pc(r.median).toFixed(2) + '%" title="median #' +
          r.median + '"></i>' +
      '</span>' +
      '<span class="cmd">' + r.median + '</span>' +
      '<span class="ccount">' + r.n + '</span></div>').join('') +
    '</div>' +
    '<div class="cfoot"><span>#1</span><span>median rank &middot; teams</span>' +
      '<span>#' + MAX + '</span></div></div>';
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

  /* ---- BRACKET ORDER, READ OFF THE OFFICIAL 2025 SHEET -------------------
     We used to list seeds 1..32 straight down, which put all four #1s next to
     each other -- they would have met in round two. A bracket does the
     opposite: it keeps the best teams apart for as long as possible.

     The official sheet's top-left quadrant is
         1 Nebraska/LIU · Kansas St./8 San Diego · 5 Miami/Tulsa ·
         High Point/4 Kansas · 3 Texas A&M/Campbell · SFA/6 TCU ·
         7 Western Ky./Marquette · Loyola Chicago/2 Louisville
     i.e. seed lines in the order 1,8,5,4,3,6,7,2, so round two is 1v8, 5v4,
     3v6, 7v2. The next quadrant runs it mirrored (SMU 2 ... 1 Pittsburgh).
     Note also which side of the pair the seed sits on: TOP at even positions,
     BOTTOM at odd ones. That alternation is what makes the round-two lines
     meet correctly, and it is visible on the sheet (Nebraska top, San Diego
     bottom, Miami top, Kansas bottom).

     Each seed line has four teams; they go to four different quadrants, with
     the overall 1 and 2 placed in opposite halves. ⚠ WHICH quadrant a given
     team lands in is the committee's call and is driven by GEOGRAPHY, which we
     do not model -- so this is the right SHAPE with our own ordering inside it,
     and the page says so. */
  const LINE_ORDER = [1, 8, 5, 4, 3, 6, 7, 2];
  const QUAD_OF_POS = [0, 3, 2, 1];        // overall 1 -> Q0, 2 -> Q3, ...
  const byQuad = [[], [], [], []];
  seeded.forEach(t => {
    const line = Math.ceil(t.seed / 4);
    const pos = (t.seed - 1) % 4;
    byQuad[QUAD_OF_POS[pos]][line - 1] = t;   // one team per line per quadrant
  });

  const games = [];
  byQuad.forEach((lines, q) => {
    // the bottom half of each side mirrors, so the final converges
    const order = (q === 1 || q === 3)
      ? LINE_ORDER.slice().reverse() : LINE_ORDER;
    order.forEach((line, i) => {
      const sd = lines[line - 1];
      if (!sd) return;
      // weakest-seed-meets-strongest-unseeded, as before: this part is ours,
      // not the committee's.
      const opp = rest[rest.length - 1 - (sd.seed - 1)];
      games.push(i % 2 === 0 ? [sd, opp] : [opp, sd]);
    });
  });

  const side = (t, cls) => {
    if (!t) return '<div class="bside empty"><span class="bsd"></span>' +
                   '<span class="bnm">&nbsp;</span><span class="bsc"></span></div>';
    /* THE SCHOOL'S OWN COLOUR ON EACH SIDE. A bracket should look like it is
       made of teams, not of generic UI chrome -- and COLORS is already on the
       page for the avatars, so this reuses it rather than deriving a second
       opinion. A team with no readable colour gets the neutral line, never an
       invented hue (the same rule the avatars follow). */
    const _tc = (COLORS[t.team] || {}).primary;
    return '<div class="bside ' + (cls || '') + '"' +
      (_tc ? ' style="--tc:' + _tc + '"' : '') + '>' +
      /* THE NUMBER ON AN OFFICIAL BRACKET IS THE SEED LINE, NOT THE NATIONAL
         SEED. 32 teams are seeded nationally (1-32, the format since 2022) and
         then placed four to a line, so the printed bracket carries FOUR #1s,
         four #2s, down to four #8s -- on the 2025 sheet the #1s are Nebraska,
         Texas, Pittsburgh and Kentucky, and the #2s are Louisville, SMU,
         Stanford and Arizona St. We were printing 1,2,3...32 straight down,
         which reads as a national ordering the bracket does not assert.
             line = ceil(national seed / 4)
         The national seed is kept on the tooltip rather than thrown away.
         Unseeded teams show NO number -- not a zero, not a dash, exactly as the
         official bracket prints them. */
      '<span class="bsd"' + (t.seed && t.seed <= 32
        ? ' title="national seed ' + t.seed + ' of 32"' : '') + '>' +
      (t.seed && t.seed <= 32 ? Math.ceil(t.seed / 4) : '') + '</span>' +
      logo(t.team) +
      /* a long name ellipses in a bracket box ("Southern Califor…"), so the
         full one stays reachable rather than simply lost */
      '<span class="bnm" title="' + t.team +
        (t.seed && t.seed <= 32 ? ' \u2014 national seed ' + t.seed : '') +
        '">' + t.team + '</span>' +
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

/* t IN [0,1] FOR THE VALUE SCALE. The renderers compute only this number;
   what green is, how wide the bar runs and how it eases in all live in one CSS
   rule. Callers pass `good` = the direction that is better, which is the whole
   reason this is a parameter: on the Stats tab "allowed to opponents" INVERTS
   -- holding a team to a low hitting percentage is the BEST defence, and
   painting it red would be the R4 trap with colour instead of a column name.
   The sort already flips on the same flag, so the two cannot disagree. */
function hscale(v, lo, hi, good) {
  if (v === null || v === undefined || hi === lo) return 0.5;
  const t = (v - lo) / (hi - lo);
  return good === 'low' ? 1 - t : t;
}
function hcell(v, txt, lo, hi, good, kind) {
  return '<td class="n hi hx ' + (kind || 'seq') + '" style="--t:' +
    hscale(v, lo, hi, good).toFixed(3) + '"><b>' + txt + '</b></td>';
}
/* COUNT-UP ON THE PODIUM, ONCE. The number is already correct in the HTML --
   this only animates toward it, and it restores the exact printed text at the
   end rather than a re-rounded value, so what settles on screen is the figure
   the build produced. Skipped entirely under reduced-motion. */
(function(){
  const els = document.querySelectorAll('.podv[data-count]');
  if (!els.length) return;
  if (window.matchMedia && matchMedia('(prefers-reduced-motion:reduce)').matches) return;
  els.forEach(el => {
    const target = parseFloat(el.dataset.count);
    const final = el.textContent;
    const t0 = performance.now(), dur = 850;
    function step(now){
      const k = Math.min(1, (now - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      el.textContent = (target >= 0 ? '+' : '') + (target * e).toFixed(2);
      if (k < 1) requestAnimationFrame(step); else el.textContent = final;
    }
    requestAnimationFrame(step);
  });
})();
function ordinal(n){
  const s = ['th','st','nd','rd'], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
/* SHOW-ALL on a collapsed list. Delegated, because the team panel is rebuilt
   every time a different team is picked and a bound handler would go with it. */
document.addEventListener('click', e => {
  const b = e.target.closest('[data-more]');
  if (!b) return;
  const box = b.parentElement.querySelector('.upc');
  if (!box) return;
  const open = box.classList.toggle('clipped');
  b.textContent = open ? ('Show all ' + b.dataset.n + ' fixtures') : 'Show fewer';
});
/* CLICK A PHOTO TO ENLARGE IT. One delegated listener on the document, so it
   covers the roster, the Stats table, the Players table and anything rendered
   after load -- binding per render would quietly miss the views that redraw.
   Only real photographs open: the drawn avatar is an SVG and has nothing more
   to show at a larger size. The image is hotlinked, never downloaded. */
(function(){
  const box = document.getElementById('lbx');
  if (!box) return;
  const img = box.querySelector('img'), cap = box.querySelector('figcaption');
  let last = null;
  function close(){ box.classList.remove('on'); box.hidden = true;
                    if (last && last.focus) last.focus(); }
  /* ASK FOR A BIGGER CROP WHERE THE HOST ALLOWS IT. Roster thumbnails come
     through SIDEARM's /crop service with plain, unsigned width/height query
     params, so the enlarged view can request a real size instead of upscaling
     a 100px square into a 460px box. Only that one host is rewritten:
     imgproxy URLs (WMT, Kentucky, Nebraska) are SIGNED, and editing their path
     produces a 404 -- which is exactly why the 1024px size could never be
     rewritten smaller. Anything unrecognised is passed through untouched. */
  function bigger(src){
    try {
      const u = new URL(src, location.href);
      if (u.host !== 'images.sidearmdev.com' || !u.searchParams.has('width')) return src;
      u.searchParams.set('width', '600');
      if (u.searchParams.has('height')) u.searchParams.set('height', '600');
      return u.toString();
    } catch (e) { return src; }
  }
  function open(src, name, sub){
    last = document.activeElement;
    img.src = bigger(src); img.alt = name || 'Player photo';
    cap.innerHTML = (name || '') + (sub ? '<span class="sub">' + sub + '</span>' : '');
    box.hidden = false; box.classList.add('on');
    box.querySelector('button').focus();
  }
  document.addEventListener('click', e => {
    const el = e.target.closest('img.mug, img.pmug, img.phero');
    if (!el || !el.getAttribute('src')) return;
    /* a photo sits inside a clickable row; the click opens the PHOTO, not the
       row's own panel */
    e.stopPropagation();
    e.preventDefault();
    /* ⚠ THE NAME CLASS IS .pnm IN THE SHARED PLAYER CELL, WHICH THIS MISSED.
       The selector list guessed at .pn/.pname/.nm and none of them matched, so
       the caption fell through to .pmeta and Morgan Gaerte's photo opened
       labelled "#18 · OH" with no name on it at all. The classes actually in
       the page are .pnm/.pmeta (player cell), .nm (list rows) and .pn (box
       score), so all three are named here -- and if none match, the img's own
       alt carries the name rather than the caption silently becoming the
       subtitle. */
    const cell = el.closest('.pcell, .rrow, .plrow, .phead, tr');
    const nm = cell ? (cell.querySelector('.pnm, .pn, .nm, .pname, b, strong') || {}).textContent : '';
    const meta = cell ? (cell.querySelector('.pmeta, .psub, .sub') || {}).textContent : '';
    const label = (nm || el.alt || '').trim();
    open(el.src, label, (meta || '').trim() === label ? '' : (meta || '').trim());
  }, true);
  box.addEventListener('click', e => {
    if (e.target === box || e.target.tagName === 'BUTTON') close();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && box.classList.contains('on')) close();
  });
})();
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
  const vs = rows.map(r => k === 'hit' ? r.hit : r[k]);
  const lo = Math.min.apply(null, vs), hi = Math.max.apply(null, vs);
  document.getElementById('lbody').innerHTML = rows.map((r, i) =>
    '<tr class="prow" data-p="' + i + '"><td class="rk">' + (i + 1) + '</td>' +
    '<td class="tm">' + playerCell(r, 34) + '</td>' +
    '<td class="cf">' + logo(r.team) + r.team + '</td>' +
    '<td class="n">' + r.sets + '</td>' +
    hcell(k === 'hit' ? r.hit : r[k],
          k === 'hit' ? r.hit.toFixed(3) : r[k].toFixed(2),
          lo, hi, 'high', 'seq') + '</tr>').join('');
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
  /* SAME FLAG AS THE SORT. `asc` is true for the opponent view, where a lower
     number is the better performance -- so the scale is told 'low' is good and
     the strongest defence is the greenest row, not the reddest. */
  const tvs = rows.map(r => k === 'hit' ? r[side].hit : r[side][k]);
  const tlo = Math.min.apply(null, tvs), thi = Math.max.apply(null, tvs);
  const better = asc ? 'low' : 'high';
  document.getElementById('ltbody').innerHTML = rows.map((r, i) => {
    const d = r[side];
    return '<tr><td class="rk">' + (i + 1) + '</td>' +
      '<td class="tm">' + logo(r.team) + r.team + '</td>' +
      '<td class="cf">' + (r.conf || '') + '</td>' +
      '<td class="n">' + d.matches + '</td><td class="n">' + d.sets + '</td>' +
      hcell(k === 'hit' ? d.hit : d[k],
            k === 'hit' ? d.hit.toFixed(3) : d[k].toFixed(2),
            tlo, thi, better, 'seq') + '</tr>';
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
  /* ⚠ THIS CALLED ITSELF. renderStats is the DISPATCHER; the player table is
     drawn by renderLeaders. `else renderStats()` recursed until the stack blew,
     and because the hidden/visible toggle above runs FIRST, the panel appeared
     correctly populated with whatever was rendered last -- so it looked like it
     worked. What actually broke: 'lq' and 'lstat' are wired to this function,
     and LSIDE is 'player' on load, so the Stats search box and the stat
     selector silently did nothing at all. Measured in the page: selecting
     Kills/set left the header reading Pts/set and the rows untouched, and
     searching a team still returned all 48. An exception inside an event
     listener never reaches the caller, which is why nothing surfaced it. */
  if (team) renderTeamStats(); else renderLeaders();
}
document.querySelectorAll('#v-leaders .segb').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('#v-leaders .segb').forEach(x => x.classList.toggle('on', x === b));
    LSIDE = b.dataset.ls;
    renderStats();
  }));
/* CLICK THROUGH TO A PLAYER. Both the roster and the stats table resolve the
   same way -- name + team against the PLAYERS aggregate, which is the only
   list carrying a match log. A player with no 2026 line yet (a true freshman)
   has nothing to show, so the row simply does not respond rather than opening
   an empty panel. */
function openPlayer(name, team) {
  const key = s => (s || '').toLowerCase().replace(/[^a-z]/g, '');
  const p = PLAYERS.find(x => key(x.name) === key(name) && key(x.team) === key(team));
  if (!p) return false;
  document.querySelector('nav button[data-v="players"]').click();
  const q = document.getElementById('pq');
  if (q) { q.value = p.name; q.dispatchEvent(new Event('input', {bubbles: true})); }
  showPlayer(p);
  window.scrollTo({top: 0});
  return true;
}
document.addEventListener('click', e => {
  const row = e.target.closest('#teamcard .rrow[data-player]');
  if (!row) return;
  const team = (document.querySelector('#teamcard .thead h2') || {}).textContent || '';
  openPlayer(row.dataset.player, team.trim());
});
document.getElementById('lbody').addEventListener('click', e => {
  const tr = e.target.closest('tr.prow');
  if (!tr) return;
  const nm = tr.querySelector('.pnm'), tmc = tr.querySelector('.cf');
  if (nm && tmc) openPlayer(nm.textContent, tmc.textContent);
});

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
  /* A FIXTURE LINE NOW SAYS WHERE. Three states, not two: vs (home), @ (away)
     and N (neutral) -- an August tournament on a neutral floor is not a road
     trip, and calling it one is the same inference-as-fact that put an AVCA
     First Serve match in the host's gym. A venue the feed has not published is
     left blank rather than filled from the nominal home team. */
  /* NEXT MATCH, LAST RESULT, FORM, RECORD -- the four answers a team page owes
     you before you scroll. `played` is newest-first and `fixtures` is
     oldest-first, which is why one is [0] and the other is [0] of its own
     order; getting that backwards would show the season opener as "next". */
  const _played = t.played || [];
  const _fix = t.fixtures || [];
  const _last = _played[0] || null;
  const _next = _fix[0] || null;
  const _w = _played.filter(g => g.mine > g.theirs).length;
  const _l = _played.length - _w;
  const glanceCard = (label, body, cls) =>
    '<div class="gl ' + (cls || '') + '"><span class="gll">' + label + '</span>' +
    body + '</div>';
  const glanceHtml = '<div class="glance">' +
    glanceCard('Record 2026',
      _played.length
        ? '<b class="glbig">' + _w + '&ndash;' + _l + '</b>' +
          '<span class="gls">' + _played.length + ' played</span>'
        : '<b class="glbig glmuted">0&ndash;0</b><span class="gls">not started</span>') +
    glanceCard('Form',
      _played.length
        /* ⚠ TEAMS is keyed BY NAME and the object carries no `team` field, so
                   formPills(t.team) was formPills(undefined) and every team's
                   form read as a dash -- while the identical call in the
                   standings, which has the name in hand, rendered correctly. */
        ? '<span class="glform">' + formPills(name) + '</span>' +
          '<span class="gls">last five, oldest first</span>'
        : '<b class="glbig glmuted">&mdash;</b><span class="gls">no results yet</span>') +
    glanceCard('Last result',
      _last
        ? '<b class="glbig ' + (_last.mine > _last.theirs ? 'glw' : 'gll2') + '">' +
          _last.mine + '&ndash;' + _last.theirs + '</b>' +
          '<span class="gls">' + (_last.mine > _last.theirs ? 'beat ' : 'lost to ') +
          _last.opp + ' &middot; ' + _last.d + '</span>'
        : '<b class="glbig glmuted">&mdash;</b><span class="gls">first match to come</span>') +
    glanceCard('Next',
      _next
        ? '<b class="glnext">' + (_next.site === 'neutral' ? 'vs ' : (_next.home ? 'vs ' : 'at ')) +
          _next.opp + '</b>' +
          '<span class="gls">' + _next.d + (_next.t ? ' &middot; ' + _next.t : '') +
          (_next.pick !== null && _next.pick !== undefined
            ? ' &middot; <i class="glpick">' + Math.round(_next.pick * 100) + '%</i>' : '') +
          '</span>'
        : '<b class="glbig glmuted">&mdash;</b><span class="gls">no fixtures on file</span>') +
    '</div>';

  const upcoming = (t.fixtures || []).map(f => {
    const neutral = f.site === 'neutral';
    const va = neutral ? 'N' : (f.home ? 'vs' : '@');
    const place = f.venue
      ? f.venue + (f.city ? ', ' + f.city + (f.st ? ' ' + f.st : '') : '')
      : '';
    const tag = f.event
      ? '<span class="kind ev">' + f.event + '</span>'
      : neutral ? '<span class="kind nu" title="neutral floor -- an event, name not supplied">neutral</span>'
      : (f.kind === 'conf' ? '<span class="kind cf">conf</span>'
                           : '<span class="kind nc">non-conf</span>');
    /* THE LAST TIME THESE TWO MET, from the completed 2025 season. A fixture
       line that says only "vs Wisconsin" is missing the thing a fan already
       knows about it. Absent where they did not meet -- never inferred. */
    const h = (t.h2h || {})[f.opp];
    const hstr = h
      ? '<span class="h2h ' + (h.mine > h.theirs ? 'w' : 'l') + '" title="' +
        'last meeting, ' + h.d + '">' + (h.mine > h.theirs ? 'W' : 'L') + ' ' +
        h.mine + '&ndash;' + h.theirs + ' in ' + (h.d || '').slice(0, 4) + '</span>'
      : '';
    return '<div class="gline gl2"><span class="dt">' + f.d + '</span>' +
    '<span class="va' + (neutral ? ' nt' : '') + '"' +
      (neutral ? ' title="neutral site"' : '') + '>' + va + '</span>' +
    '<span class="op">' + f.opp + '</span>' +
    '<span class="ss">' + (f.t || '') + '</span>' +
    (f.pick !== null && f.pick !== undefined
      ? '<span class="rs ' + (f.pick >= 0.5 ? 'w' : 'l') + '">' +
        Math.round(f.pick * 100) + '%</span>' : '') +
    '<span class="wh2">' + tag +
      (place ? '<span class="pl">' + place + '</span>'
             : '<span class="pl u">venue not listed</span>') +
      hstr +
    '</span></div>';
  }).join('');

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
        rosterHtml += '<div class="rrow' + (r.st ? ' rrow--starter' : '') +
          '" data-player="' + r.n.replace(/"/g, '&quot;') + '">' +
          '<span class="ravatar">' +
            playerCell({name: r.n, team: name, pos: r.p, num: r.num, photo: r.ph, aa: r.aa}, 40) +
          '</span>' +
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
  /* RETURNING HONOURS. A count of the decorated players still on the roster --
     the difference between "returns its top scorer" and "returns three
     All-Americans", which is the thing a preseason number cannot say. */
  const aaRoster = (t.roster || []).filter(r => r.aa && r.aa.length);
  const aaNat = aaRoster.filter(r => r.aa.some(x => x.national));
  let honHtml = '';
  if (aaRoster.length) {
    honHtml =
      '<div class="tsec" style="margin-top:14px"><h3>Returning AVCA honours</h3>' +
      '<div class="body">' + aaRoster.map(r => {
        const best = r.aa.slice().sort((x, y) => y.season - x.season)[0];
        return '<div class="plrow"><span class="nm">' + r.n +
          '<span class="wentto">' +
          r.aa.map(x => x.honour + ' ' + x.season).join(' \u00b7 ') +
          '</span></span><span class="kd">' + (best.national ? 'national' : 'all-america') +
          '</span></div>';
      }).join('') + '</div>' +
      '<div class="tnote"><b>' + aaRoster.length +
      (aaRoster.length === 1 ? ' player' : ' players') + '</b> on this roster ' +
      'carried an AVCA honour in the last two seasons' +
      (aaNat.length ? ', including <b>' + aaNat.length + '</b> with a national award' : '') +
      '. From the AVCA\u2019s published workbook \u2014 nothing in the game feed ' +
      'carries this.</div></div>';
  }
  const aq = t.aq;
  let postHtml = '';
  if (aq) {
    const tourn = aq.mechanism === 'TOURNAMENT';
    const sim = t.sim || {};
    postHtml =
      '<div class="tsec" style="margin-top:14px"><h3>Postseason</h3>' +
      /* ---- THE PROJECTED-WINS BAND, AS AN INTERVAL --------------------
         The simulator plays every remaining fixture 4,000 times and returns
         p10 / p50 / p90. Printing only the median throws away the half of the
         answer that matters -- how WIDE the outcome is -- so the band is drawn
         and the median marked inside it. The axis is the team's own schedule,
         0 to the number of fixtures it actually has, which is why a short
         schedule reads as a short track rather than a weak team.
         Wins already banked are marked separately: they are a fact, not a
         projection, and the two must not look alike. */
      (sim.proj_wins_p50 !== undefined && sim.proj_wins_p50 !== null && sim.fixtures
        ? (function(){
            const N = sim.fixtures;
            const pc = v => Math.max(0, Math.min(100, v / N * 100));
            const won = (sim.record_so_far || '0-0').split('-')[0] * 1;
            return '<div class="bandwrap">' +
              '<div class="bandhd"><span>Projected wins</span>' +
                '<b>' + sim.proj_wins_p50 + '</b>' +
                '<i>of ' + N + ' scheduled</i></div>' +
              '<div class="band">' +
                '<span class="bandfill" style="left:' + pc(sim.proj_wins_p10).toFixed(1) +
                  '%;width:' + (pc(sim.proj_wins_p90) - pc(sim.proj_wins_p10)).toFixed(1) + '%"></span>' +
                '<span class="bandmed" style="left:' + pc(sim.proj_wins_p50).toFixed(1) + '%"></span>' +
                (won ? '<span class="bandwon" style="left:' + pc(won).toFixed(1) +
                       '%" title="' + won + ' already won"></span>' : '') +
              '</div>' +
              '<div class="bandft"><span>0</span>' +
                '<span class="bandkey">80% of simulations land between <b>' +
                  sim.proj_wins_p10 + '</b> and <b>' + sim.proj_wins_p90 + '</b>' +
                  (won ? ' &middot; <i class="wonkey"></i>' + won + ' won so far' : '') +
                '</span><span>' + N + '</span></div>' +
            '</div>';
          })()
        : '') +
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
    /* ---- THE SAME NUMBERS, AS A CHART ------------------------------------
       Each row is its OWN scale: a hitting percentage and a digs-per-set count
       do not share an axis, and putting them on one would be the dual-axis
       mistake wearing a different hat. Within a row the two bars DO share a
       scale, which is the only comparison the chart is making -- what this team
       does against what it allows.
       Every bar keeps its number as a direct label, so the chart never has to
       be trusted on its own, and the sample it rests on is printed underneath.
       Two series, so a legend is always present. The pair was validated rather
       than eyeballed: #3F92DE / #C4763F pass lightness band, chroma floor, CVD
       separation (dE 22.6 protan) and 3:1 contrast on this surface. */
    const barRow = r => {
      const a = r[1], b = r[2];
      if (a === null || a === undefined) return '';
      const hi = Math.max(Math.abs(a), Math.abs(b || 0)) || 1;
      const w = v => Math.max(1.5, Math.abs(v || 0) / hi * 100).toFixed(1);
      /* ⚠ THE LABEL GETS ITS OWN COLUMN. First version let the bar be a % of
         the whole row with the number after it, so a 100% bar pushed its own
         label off the edge and "15.86" rendered as "15.8" -- the same clipping
         that was reported on the pills. The bar is a % of a TRACK; the value
         sits in a fixed column beside it and can never be squeezed. */
      return '<div class="cbar"' + (r[4] ? ' title="' + r[4] + '"' : '') + '>' +
        '<div class="cbl">' + r[0] + '</div>' +
        '<div class="cbt">' +
          '<div class="cbrow"><span class="cbtk"><i class="cbf own" style="width:' +
            w(a) + '%"></i></span><b>' + f(a, r[3]) + '</b></div>' +
          '<div class="cbrow"><span class="cbtk"><i class="cbf opp" style="width:' +
            w(b) + '%"></i></span><b>' + f(b, r[3]) + '</b></div>' +
        '</div></div>';
    };
    statHtml =
      '<div class="tsec" style="margin-top:14px"><h3>Team stats, 2026</h3>' +
      '<div class="ckey"><span><i class="sw own"></i>' + name + '</span>' +
      '<span><i class="sw opp"></i>Opponents</span></div>' +
      '<div class="cwrap">' + rowsOf.map(barRow).join('') + '</div>' +
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
    /* where they sit in their own league, and how hard the schedule is. Both
       are sorts and means over numbers already on this page -- no new model. */
    (t.conf_pos && t.conf_size
      ? chip('In the ' + (t.conf || 'conference'),
             ordinal(t.conf_pos) + ' of ' + t.conf_size) : '') +
    (t.sos
      ? chip('Opp rank', t.sos.mean_rank + ' avg' +
             (t.sos.top25 ? ' \u00b7 ' + t.sos.top25 + ' top-25' : '')) : '') +
    '</div></div>' +
    /* ---- AT A GLANCE -------------------------------------------------
       ⚠ MEASURED BEFORE CHANGING ANYTHING: the team page ran to 3,648px and
       "Upcoming" alone was 2,416px of it. Two thirds of a team page was a
       fixture list, and the three things anyone actually opens a team page for
       -- what just happened, what is next, how are they going -- were either
       far below the fold or not on the page at all.
       Everything here is read from data already in the payload; nothing new is
       computed and nothing is estimated. */
    /* ⚠ THE PROVENANCE NOTE IS BOOKKEEPING, NOT COPY. Nebraska's row records in
       full why it was entered by hand and how it was verified -- which belongs
       in the data file and on the tooltip, not printed across the team page. A
       reader wants the coach's name; the audit trail is one hover away. */
    (t.coach
      ? '<div class="coachline" title="' +
        [t.coach.source ? 'Source: ' + t.coach.source : '', t.coach.note || '']
          .filter(Boolean).join(' \u2014 ').replace(/"/g, '&quot;') + '">' +
        '<span class="cl">Head coach</span>' +
        '<b>' + t.coach.name + '</b>' +
        (t.coach.title && !/^head coach$/i.test(t.coach.title)
          ? '<span class="ct">' + t.coach.title + '</span>' : '') +
        '</div>'
      : '') +
    glanceHtml +
    '<div class="tcols">' +
      '<div>' +
        (results ? '<div class="tsec"><h3>Results</h3><div class="body">' + results +
                   '</div></div>' : '') +
        '<div class="tsec"' + (results ? ' style="margin-top:14px"' : '') +
          '><h3>Upcoming<span class="cnt">' + (t.fixtures || []).length +
          '</span></h3><div class="body upc' +
          ((t.fixtures || []).length > 6 ? ' clipped' : '') + '">' +
          (upcoming || '<div class="tnote">No remaining fixtures on file.</div>') +
        '</div>' +
        ((t.fixtures || []).length > 6
          ? '<button type="button" class="moreb" data-more data-n="' +
            (t.fixtures || []).length + '">Show all ' +
            (t.fixtures || []).length + ' fixtures</button>' : '') +
        '</div>' +
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
             /* the badge needs a space before it or the heading reads
                "Most-started six, 20255-1" -- the year running straight into
                the 5-1 */
             '<h3>Most-started six, 2025 ' +
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
        honHtml +
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
/* Schedule filter: text AND rank together. 1,524 fixtures is a list you cannot
   read; 39 of them are Top 25 against Top 25, which is the question actually
   being asked when someone opens a schedule in August. */
function filterSchedule() {
  const q = (document.getElementById('sq').value || '').toLowerCase().trim();
  const want = document.getElementById('srank').value;
  let shown = 0;
  document.querySelectorAll('#sbody tr').forEach(tr => {
    const cls = tr.className || '';
    const rankOk = want === 'all' ||
                   (want === 'one' && cls.includes('rkd')) ||
                   (want === 'both' && cls.includes('both'));
    const textOk = !q || tr.textContent.toLowerCase().includes(q);
    const show = rankOk && textOk;
    tr.hidden = !show;
    if (show) shown++;
  });
  document.getElementById('scnt').textContent =
    shown + (shown === 1 ? ' fixture' : ' fixtures');
}
['sq', 'srank'].forEach(id =>
  document.getElementById(id).addEventListener('input', filterSchedule));
filterSchedule();
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
