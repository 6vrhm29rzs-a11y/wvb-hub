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
import time
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
def exhibitions():
    # type: () -> Dict[str, Dict]
    """Game ids that do NOT count, keyed by id.

    ⚠ THE FEED CANNOT TELL US THIS. Checked game 6640217 directly: there is no
    type, gameType or exhibition field anywhere on the contest, division reads
    1, and both teams show record (0-0). An exhibition is indistinguishable
    from a match that counts, so this file is maintained BY HAND with a source
    on every entry, the same way venue corrections are.

    ⚠ AND MIXING ONE IN IS NOT COSMETIC. Spikes Under the Lights plays its
    first two sets to 21 rather than 25 (huskers.com match notes, 2026-08-26).
    Every rate here is per SET, so a 21-point set quietly deflates points per
    set, swings per set, the opponent adjustment and the rally model for four
    of the best teams in the country -- and nothing on the page would look
    wrong. That format is also the proof it cannot be an NCAA result: the
    playing rules put a set at 25.
    """
    doc = load("data/raw/%d/exhibitions.json" % SEASON) or {}
    return dict((str(k), v) for k, v in (doc.get("exhibitions") or {}).items())


def exhibition_rules():
    # type: () -> List[Dict]
    """Venue+date rules, for matches whose id does not exist yet.

    ⚠ AN ID LEDGER HAS A DEADLINE AND A DEADLINE IS NOT A CONTROL. The
    championship match of this event had no game id while the semi-finals were
    still being played -- the scoreboard only lists it once the field is known.
    An id-only ledger would have missed it and the 2:15am crawl would have
    counted a fake result into two teams' records. A rule does not depend on
    anyone remembering to come back.
    """
    doc = load("data/raw/%d/exhibitions.json" % SEASON) or {}
    return doc.get("rules") or []


def results() -> List[Dict]:
    """Every final 2026 match, newest first, with its per-set scores."""
    path = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if not os.path.exists(path):
        return []
    _exh = exhibitions()
    _exh_rules = exhibition_rules()
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
                _pair = (int(s.get("visit")), int(s.get("home")))
            except (TypeError, ValueError):
                continue
            # ⚠ A 0-0 ROW ON A FINAL IS A SET THAT WAS NEVER PLAYED. The feed
            # keeps the scaffold: both Spikes Under the Lights finals came back
            # with a third linescore reading 0-0 -- the best-of-3 ended 2-0 and
            # the unplayed set's row shipped anyway. A set someone actually
            # played cannot end 0-0 (a set ends when a side reaches the
            # target), so on a FINAL -- this loop only sees finals, the guard
            # above just checked game_state -- an all-zero pair is always the
            # feed's placeholder, never a result. Caught in CI by the guard
            # that recomputes each match score from its own line scores.
            if _pair == (0, 0):
                continue
            sets.append(_pair)
        ep = g.get("start_time_epoch")
        # DATE IN EASTERN, NOT UTC. Kentucky beat Wisconsin at 9pm ET on the
        # 21st, which is 01:00 UTC on the 22nd -- bucketing by UTC filed a
        # Friday-night match under Saturday. Every evening game in the country
        # lands on the wrong day that way, and it is the kind of error a reader
        # spots instantly and a test never would.
        # ⚠ MARKED, NOT DROPPED. A match against good opposition still says
        # something about a team even when it does not count, so the record
        # rides along and every consumer that builds a RECORD or a RATE filters
        # on this flag. Deleting it would throw away real evidence; counting it
        # would corrupt four teams' seasons.
        _exh_hit = _exh.get(str(g.get("game_id")))
        if not _exh_hit and _exh_rules:
            _loc = g.get("location") or {}
            _vn = (_loc.get("venue") or "").strip()
            _dt = _pt_date(ep) if ep else None
            for _r in _exh_rules:
                _m = _r.get("match_on") or {}
                if (_m.get("venue") and _vn == _m["venue"]
                        and _m.get("date") and _dt == _m["date"]):
                    _exh_hit = _r
                    break
        out.append({
            "exhibition": bool(_exh_hit),
            "exhibition_event": (_exh_hit or {}).get("event"),
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


def today_pt():
    # type: () -> datetime.date
    """Today, in the zone this page renders in.

    ⚠ NOT datetime.date.today(). That is the BUILDER's clock -- Pacific on
    Cody's Mac, UTC on a GitHub runner. The daily job runs at 09:15 UTC, which
    is 2:15am Pacific, so on every published build UTC was already the next day.
    Measured: schedule() under a UTC clock dropped TODAY'S FIXTURES ENTIRELY --
    the earliest date it returned jumped from 2026-08-24 to 2026-08-28 -- so the
    published Schedule tab and the week band have been missing the current day.
    Same root cause as the day-label bug fixed earlier today; this is the rest
    of it.
    """
    return (datetime.datetime.now(PT).date() if PT
            else datetime.datetime.utcnow().date())


def day_label(iso, today=None):
    """"Sun Aug 30" -- a calendar date the way a reader reads one.

    A bare ISO date on a scoreboard is a formatting failure: "2026-08-30" is
    unambiguous and makes the reader do arithmetic to learn it is a Sunday.

    ⚠ IT LIVES AT MODULE LEVEL BECAUSE TWO RENDERERS NEED IT and they run at
    different points in build(). The first version was nested inside build(),
    defined AFTER the score cards were assembled -- so the cards kept printing
    raw ISO dates while the week box directly below them said "Today", one page
    showing two date formats at once. Mirrored in the page script as
    dayLabel(); no timezone is involved, an ISO calendar date is already a day.
    """
    # ⚠ "TODAY" IS PACIFIC, NOT THE MACHINE'S. datetime.date.today() is the
    # BUILDER's date -- Pacific on Cody's Mac, UTC on a GitHub runner. The daily
    # job runs at 09:15 UTC, which is 2:15am Pacific, so UTC is already the next
    # day: every published page built overnight labelled the current day
    # "Yesterday" while the page's own JavaScript, which correctly uses
    # America/Los_Angeles, called it "Today". Invisible on a laptop where both
    # clocks agree; caught only because the two implementations are compared
    # against each other, and only when that comparison ran in CI.
    today = today or today_pt()
    try:
        d = datetime.date(*[int(x) for x in (iso or "").split("-")])
    except (TypeError, ValueError):
        return iso or ""
    if d == today:
        return "Today"
    if d == today + datetime.timedelta(days=1):
        return "Tomorrow"
    if d == today - datetime.timedelta(days=1):
        return "Yesterday"
    return d.strftime("%a %b %-d")


# ⚠ THE MEDIA HOST LIST COMES FROM intel.py, WHICH IS WHERE THE AUDIT LIVES.
# Re-typing it here would be two allowlists with one name -- and the one that
# governs what a browser will load would be the copy nobody audited.
try:
    from intel import MEDIA_HOSTS as INTEL_MEDIA_HOSTS
except Exception:                                          # noqa: BLE001
    INTEL_MEDIA_HOSTS = ()

RANK_TITLE = "AVCA coaches poll rank"

# ══ THE RULERS ════════════════════════════════════════════════════════════
# ⚠ A RANK WITHOUT ITS RULER IS NOT A FACT, IT IS A NUMBER. This page carries
# at least nine different orderings of the same 348 teams, and a bare "#21"
# silently means whichever one the reader had in mind. It was measured in the
# Court Signal phase: the Rally Tape showed Kansas at #15 (AVCA, from the
# scoreboard feed) four inches above a readiness panel showing the same match
# with Kansas at #21 (Digby's Top 25). Both correct. Neither labelled. The only
# reason that pair was caught is that they happened to land on one screen --
# everywhere else the two rulers are far enough apart that nothing LOOKS wrong,
# which is worse.
#
# So: one table, here, and both render paths read it. Each entry is
#   key: (visible label, compact label, what it actually is)
# The compact label is SHORTER, never ABSENT -- "space is tight" is not a
# reason to publish an ambiguous number.
RULERS = {
    "avca":      ("AVCA", "AVCA", "AVCA coaches poll"),
    "power":     ("POWER", "PWR", "our POWER rating -- how strong a team is"),
    "digby":     ("DIGBY", "DGB", "Digby's Top 25 -- this site's own "
                                  "in-season ranking"),
    "resume":    ("R\u00c9SUM\u00c9", "RES", "our r\u00e9sum\u00e9 rank -- "
                                           "what a team has earned"),
    "rpi":       ("RPI", "RPI", "official NCAA RPI"),
    "ballot":    ("MY BALLOT", "MINE", "your own saved ballot"),
    "vt":        ("VT", "VT", "VolleyTalk community poll"),
    "massey":    ("MASSEY", "MSY", "Massey Ratings"),
    "power25":   ("2025", "2025", "final 2025 POWER rank"),
    "committee": ("TOP 16", "T16", "the DI Committee's in-season Top 16 "
                                   "reveal"),
    "seed":      ("SEED", "SEED", "projected tournament seed"),
}


# ⚠ TWO OF THESE RULERS NAME SOMEBODY ELSE'S PRODUCT, and this table is
# SERIALISED INTO THE PAGE. Adding them shipped the strings "VolleyTalk" and
# "Massey Ratings" straight into the public build -- and the fail-closed gate
# stopped the build, which is exactly what it is for. The values were already
# dropped at BOARD.build(); it was the LABELS that leaked, through a data
# structure nobody would think of as markup.
# The general lesson this project keeps relearning: when the question is "did
# we publish X", grep the DATA. A table is data.
PRIVATE_RULERS = ("vt", "massey")


def public_rulers():
    """The ruler table as the built page should carry it."""
    return {k: list(v) for k, v in RULERS.items()
            if not (PUBLIC and k in PRIVATE_RULERS)}


def rank_badge(basis, v, compact=False, text=False):
    """The one way a rank is rendered. BASIS IS REQUIRED.

    ⚠ THERE IS DELIBERATELY NO DEFAULT. A default basis is how the previous
    version of this function -- which hard-coded AVCA -- ended up being the
    right answer at four call sites and the wrong answer at none only by luck.
    An unknown or missing basis renders a LOUD marker rather than a bare
    number, and test_rulers.py asserts that marker never reaches a built page.
    A silent fallback would put the failure back where it started.
    """
    if not v:
        return ""
    r = RULERS.get(basis)
    if r is None:
        # visible, ugly, and guarded -- never a bare numeral
        if text:
            return "rank basis? "
        return '<i class="rnk rnkbad" title="no ruler named">rank basis?</i> '
    label = r[1] if compact else r[0]
    if text:
        # ⚠ NOT EVERY CONSUMER RENDERS HTML. The game-day readiness panel's
        # `matchup` is a TEXT field, and returning markup for it printed the
        # whole tag on screen: `<i class="rnk" title="Digby's Top 25...`. The
        # component owns both renderings rather than a second one existing
        # somewhere with its own idea of the labels (R4).
        return "%s #%s " % (label, v)
    # ⚠ AND THE TITLE SAID "ranking rank". The descriptions are already noun
    # phrases naming the ruler, so appending the word doubled it.
    return ('<i class="rnk" title="%s"><span class="rank-label">%s</span>'
            '#%s</i> ' % (r[2], label, v))



import digby_art as DIGBY_ART            # noqa: E402
import icons as ICONS                    # noqa: E402
import trend as TREND                    # noqa: E402


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
    """game_id -> where it is played, what event, and whether we may say so.

    ⚠ THIS NO LONGER DEDUPES. It reads scripts/fixtures.canonical_fixtures(),
    which is the one place a game id becomes one record. The previous body
    walked games.jsonl applying "final beats non-final, then LAST WINS" -- and
    with no crawl timestamp on any record in that file, "last" meant whichever
    line the crawler happened to append last. Measured on the real data: 1,048
    ids hold more than one record, and among them 37 disagree about state, 34
    about start time, 26 about location and 5 about which side is home. File
    order decided all of it.

    What comes back now carries `site` (which may be "unconfirmed"), the
    official-school correction if one applies, and `conflict` -- a list of
    material disagreements a view must NOT paper over.
    """
    import fixtures as FX
    out = {}
    for gid, rec in FX.canonical_fixtures().items():
        out[gid] = {
            "venue": rec.get("venue"),
            "city": rec.get("city"),
            "state_usps": rec.get("state_usps"),
            "state": rec.get("game_state"),
            "site": rec.get("site"),
            "event": rec.get("event"),
            "epoch": rec.get("start_time_epoch"),
            "time_unannounced": rec.get("time_unannounced"),
            "conflict": FX.blocking_conflicts(rec),
            "corrected": rec.get("corrected_fields") or [],
            "correction": rec.get("correction"),
            "source": rec.get("source"),
            "site_basis": rec.get("site_basis"),
        }
    return out

def schedule(limit_days: int = 21) -> List[Dict]:
    """Upcoming fixtures from today forward, with WHERE and WHAT KIND."""
    today = today_pt().isoformat()
    vidx = venue_index()
    tvx = tv_index()
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
            # ⚠ THE TIME COMES FROM THE CANONICAL EPOCH, NOT THE SCOREBOARD
            # STRING. One conversion, one source. The scoreboard's own epoch is
            # a per-date snapshot; the canonical one has already had unannounced
            # placeholders excluded from the vote across every snapshot of this
            # id, so a fixture whose real time was announced in a later crawl
            # gets the real time here instead of whichever the file held last.
            _ep = v.get("epoch") or g.get("startTimeEpoch")
            rows.append({
                "d": date, "a": a, "h": h,
                "t": listed_time(g.get("startTime"), h, _ep),
                "ar": (g.get("away") or {}).get("rank") or "",
                "hr": (g.get("home") or {}).get("rank") or "",
                "gid": gid,
                "venue": v.get("venue"), "city": v.get("city"),
                "st": v.get("state_usps"),
                "site": v.get("site"), "event": v.get("event"),
                "kind": kind, "conf": ac if kind == "conf" else "",
                # ⚠ CONFLICT TRAVELS WITH THE FIXTURE. A view that has this and
                # ignores it is choosing to; a view that never received it
                # could not have known.
                "conflict": v.get("conflict") or [],
                "corrected": v.get("corrected") or [],
                # ⚠ WHERE TO WATCH. The feed carries none, so this is the
                # joined listing or nothing -- never a guess.
                "tv": (tvx.get(gid) or {}).get("net"),
                "csrc": ((v.get("correction") or {}).get("source_url")
                         if v.get("correction") else None),
                "cverified": ((v.get("correction") or {}).get("verified_on")
                              if v.get("correction") else None),
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


def tv_index():
    # type: () -> Dict[str, Dict]
    """game_id -> where to watch it. Private only.

    ⚠ THE FEED CARRIES NO BROADCAST AT ALL -- measured, `network` is empty on
    all 1,971 scoreboard entries. The only broadcast data that exists here is
    Cody's own transcribed listings, which until now rendered as a standalone
    table joined to nothing: the schedule could tell you a match existed and
    never tell you where to watch it, which is the first thing he actually
    wants to know.

    ⚠ JOINED STRICTLY, AND NEVER GUESSED. A listing attaches only when exactly
    ONE fixture that day is between exactly those two teams, matched through
    reconcile_2025.norm() -- the normaliser that already exists because
    "LSU New Orleans" vs "New Orleans" has bitten this project three times.
    Measured on the real file: 187 of 220 listings name two teams, 130 join to
    exactly one fixture, and ZERO are ambiguous. That zero is what makes a
    strict join safe. The 30 that name no teams are conference-tournament
    placeholders ("B1G Tournament") whose brackets do not exist until November;
    they stay in the standalone table and are counted, never invented onto a
    fixture.

    ⚠ PRIVATE. The listings are transcribed from a forum, so they are stripped
    from the public build exactly as tv() already is.
    """
    if PUBLIC:
        return {}
    import datetime as _dt
    try:
        from reconcile_2025 import norm as _norm
    except Exception:                                       # noqa: BLE001
        def _norm(x):
            return re.sub(r"[^a-z]", "", (x or "").lower())

    import fixtures as FX
    by_pair = {}
    for gid, rec in FX.canonical_fixtures().items():
        ts = rec.get("teams") or []
        ep = rec.get("start_time_epoch")
        if len(ts) != 2 or not ep:
            continue
        try:
            d = _dt.datetime.utcfromtimestamp(int(ep) - 4 * 3600).date().isoformat()
        except (ValueError, TypeError):
            continue
        key = (d, frozenset(_norm(t.get("name_short")) for t in ts))
        by_pair.setdefault(key, []).append(gid)

    out, joined, missed = {}, 0, 0
    for row in tv():
        m = re.sub(r"^[^:]*:\s*", "", row.get("m") or "")
        sides = re.split(r"\s+vs\.?\s+|\s+at\s+", m, flags=re.I)
        if len(sides) != 2:
            missed += 1
            continue
        try:
            day = row.get("day", "").split(",")[1].strip()
            iso = _dt.datetime.strptime("%s %d" % (day, SEASON),
                                        "%b %d %Y").date().isoformat()
        except (ValueError, IndexError):
            missed += 1
            continue
        cand = by_pair.get((iso, frozenset(_norm(x) for x in sides))) or []
        if len(cand) != 1:
            missed += 1
            continue
        out[cand[0]] = {"net": row.get("n"), "t": row.get("t")}
        joined += 1
    out["_stats"] = {"joined": joined, "unjoined": missed, "total": joined + missed}
    return out


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
            # ⚠ NORMALISED, NOT RAW. This is the value the Player Ratings
            # column renders; passing the school's own string through put
            # "Jr" and "Senior" in the same sorted column.
            "c": class_code(pl.get("class_raw")
                            or (p25 or {}).get("class") or None),
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
    _di_pl = di_teams()
    for r in res:
        for side, opp, mine, theirs, home in (
                ("away", r["home"], r["away_sets"], r["home_sets"], False),
                ("home", r["away"], r["home_sets"], r["away_sets"], True)):
            played.setdefault(r[side], []).append({
                # ⚠ THE GAME ID TRAVELS WITH THE ROW. Without it a team's
                # own result could not open the match it describes -- the one
                # place a reader is most likely to want the detail -- so five
                # entry points reached the match page and two dead-ended.
                "gid": r.get("gid"),
                "d": r["date"], "opp": opp, "home": home,
                # Same caveat as the player match log: the RESULT row names the
                # opponent, so it is where the division belongs. A 3-0 win over
                # a Division-II side and a 3-0 win over an SEC side rendered
                # identically.
                "nondi": bool(_di_pl) and opp not in _di_pl,
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

    # THIS season's W-L, from the very same `played` list the fixtures, the form
    # pills and the standings all come from -- and a team with no completed
    # match is ABSENT rather than "0-0", which would read as played-and-drawn.
    #
    # ⚠ DIVISION-I ONLY, and the comment here used to claim "one source, so the
    # four cannot disagree". That was FALSE. `standings()` has always dropped
    # non-D-I opponents (correctly -- it is the NCAA's own convention, the
    # official RPI `Record` column excludes them and breaks them out as
    # `Non-Div I`), while this counted every match. So Norfolk St. carried a
    # "2026 1-0" chip in its team header directly above a standings row reading
    # "Overall 0-0". Sharing an input is not the same as sharing a DEFINITION
    # (R4). The non-D-I split rides along so a consumer can show it rather than
    # silently lose the result.
    _w26 = {}
    for _nm, _gs in played.items():
        _di_g = [g for g in _gs if not g.get("nondi")]
        _nd_g = [g for g in _gs if g.get("nondi")]
        _w = sum(1 for g in _di_g if (g["mine"] or 0) > (g["theirs"] or 0))
        _nw = sum(1 for g in _nd_g if (g["mine"] or 0) > (g["theirs"] or 0))
        _w26[_nm] = (_w, len(_di_g) - _w, _nw, len(_nd_g) - _nw)

    fixtures = {}
    # ⚠ THE COUNT WAS NORMALISED AND THE LIST WAS NOT. `sched_n` keys through
    # team_norm() -- fixed when "LSU New Orleans" vs "New Orleans" first bit --
    # but THIS loop, over the same scoreboard files, kept using the raw feed
    # name. So New Orleans' page said "29 scheduled matches" and listed ZERO:
    # the count and the list came from two loops and only one was joined
    # properly. The existing guard checks `sched_n`, which is the half that
    # was already right, so it passed throughout.
    # `teams` is the hub's own roster of names; a feed name that normalises to
    # one of them is DISPLAYED as the hub spells it, so a crest and a link
    # resolve. A name we do not know keeps exactly what the feed said.
    _hub_disp = {}
    for _t in (teams or []):
        _n = _t.get("team") if isinstance(_t, dict) else _t
        if _n:
            _hub_disp.setdefault(team_norm(_n), _n)
    vidx = venue_index()
    today = today_pt().isoformat()
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
            base = {"gid": gid, "d": date, "t": t, "venue": v.get("venue"),
                    "city": v.get("city"), "st": v.get("state_usps"),
                    "site": v.get("site"), "event": v.get("event"), "kind": kind}
            _ka, _kh = team_norm(a), team_norm(h)
            aw = dict(base); aw.update({"opp": _hub_disp.get(_kh, h),
                                        "home": False})
            hm = dict(base); hm.update({"opp": _hub_disp.get(_ka, a),
                                        "home": True})
            fixtures.setdefault(_ka, []).append(aw)
            fixtures.setdefault(_kh, []).append(hm)

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

    # ⚠ THE PROJECTED SIX IS THE ONLY PER-TEAM NAME SOURCE THAT COVERS A TEAM
    # WHICH HAS NOT PLAYED. The 2026 player payload is built from box scores,
    # so in August it holds 11 teams -- and the briefs name players on all 348.
    # Enriching these entries here (rather than in project_lineups.py) keeps the
    # derived artifact untouched and puts the join at the single point the page
    # consumes it (R4).
    _xfer_six = transfer_index()
    # parts-vs-whole and returning-by-position (scripts/team_parts.py), plus
    # rotation side-out (scripts/pbp_player_metrics.py). All three are absent
    # on a machine without them and every consumer must render that as "not
    # available", never as a zero.
    _tp = load("data/team_parts_%d.json" % SEASON) or {}
    _parts = _tp.get("parts") or {}
    _retpos = _tp.get("returning_by_position") or {}
    _rotso = (load("data/rotation_sideout_%d.json" % (SEASON - 1))
              or {}).get("teams") or {}
    _stars = team_stars()

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
            # POWER and R\u00c9SUM\u00c9 travel with the team so the header can
            # lead with our two rankings instead of burying them among five of
            # other people's.
            "power": t.get("power"),
            "resume_rank": t.get("resume_rank"),
            "wab": t.get("wab"),
            "rank25": t["rank25"],
            "avca": t.get("avca"), "vt": t.get("vt"),
            "massey": t.get("massey"), "rpi": t.get("rpi"),
            "record25": ("%s-%s" % (t.get("wins"), t.get("losses"))
                         if t.get("wins") is not None else None),
            # THIS season's record, from the same results list the standings
            # and the form pills are built from -- one source, so the three
            # cannot disagree. None until a team has played, never "0-0" for a
            # team with no fixtures on file.
            "record26": (("%d-%d" % (_w26[nm][0], _w26[nm][1]))
                         if nm in _w26 else None),
            # The non-D-I record, as its own field so no consumer has to
            # re-derive it and none can accidentally fold it into the record.
            "record26_nondi": (("%d-%d" % (_w26[nm][2], _w26[nm][3]))
                               if nm in _w26 and
                               (_w26[nm][2] or _w26[nm][3]) else None),
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
            "lineup": _six_enriched(lineup.get(nm), _xfer_six,
                                    photos.get(nm) or photos.get(_rk) or {},
                                    nm, transferred_out),
            "rot25": (_byn.get(team_norm(nm)) if _rotdoc else None),
            "stars": _stars.get(nm),
            "parts": _parts.get(nm),
            "retpos": _retpos.get(nm),
            "rotso": _rotso.get(nm),
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
                         for f in fixtures.get(team_norm(nm), [])
                         if f["d"] >= today][:40],
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
    # THIRD SOURCE, AND IT IS THE ONE THAT COVERED THE BIG PROGRAMMES. 52 schools
    # -- Nebraska, Kentucky, UCLA, Penn St. among them -- have no /coaches path
    # at all; every variant 404s, and their staff is a section of the ROSTER
    # page. recover_coaches_from_roster.py reads it there. It goes ABOVE the
    # hand-entered rows and below nothing else, because it is a crawl: where a
    # sourced hand entry exists, that still wins.
    for team, rec in (((load("data/raw/%d/coaches_from_roster_%d.json" % (SEASON, SEASON))
                        or {}).get("teams")) or {}).items():
        if (rec or {}).get("name"):
            out[team] = {"name": rec["name"], "title": rec.get("title"),
                         "source": rec.get("url"),
                         "corroborated": rec.get("corroborated")}
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
                          "cw": 0, "cl": 0,
                          # ⚠ NON-D-I RESULTS ARE COUNTED SEPARATELY, NOT
                          # DROPPED IN SILENCE. The record here is
                          # Division-I-only, which is CORRECT and is the NCAA's
                          # own convention -- the official RPI table's `Record`
                          # column excludes non-D-I opponents and breaks them
                          # out as `Non-Div I`. What was wrong was saying
                          # nothing: Norfolk St. beat a Division-II side and
                          # its row read "Overall 0-0" next to a Form of "W"
                          # and a differential of "+9.67" -- a win with no
                          # matches, because Form and +/- are built from a
                          # source that keeps every opponent. One event, three
                          # consumers, two answers (R4).
                          "nw": 0, "nl": 0,
                          "rank": t["rank26"]}
    for r in res:
        h, a = r["home"], r["away"]
        hw = (r["home_sets"] or 0) > (r["away_sets"] or 0)
        # A match with a non-D-I side still HAPPENED to the D-I team in it.
        if (h in rec) != (a in rec):
            for nm, won in ((h, hw), (a, not hw)):
                if nm in rec:
                    rec[nm]["nw" if won else "nl"] += 1
            continue
        if h not in rec or a not in rec:
            continue                                # neither side is D-I
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

# ⚠ A NORMALISATION, NOT AN INFERENCE. These nine are the standard published
# abbreviations for the same nine words; expanding "So" to "Sophomore" adds no
# information and removes none. Anything NOT on this list is preserved exactly
# as the school published it -- a value we cannot expand without guessing is
# left alone rather than mapped to the nearest thing that looks similar.
CLASS_FULL = {
    "FR": "Freshman", "R-FR": "Redshirt Freshman",
    "SO": "Sophomore", "R-SO": "Redshirt Sophomore",
    "JR": "Junior", "R-JR": "Redshirt Junior",
    "SR": "Senior", "R-SR": "Redshirt Senior",
    "GR": "Graduate",
}


# The reverse map, so a spelled-out value normalises too. Built from
# CLASS_FULL rather than typed a second time -- two maps for one relation is
# how the two ends drift apart.
# Title case, because that is how the column has always read ("Sr", not "SR").
CLASS_SHORT = dict([(k, "-".join([w.capitalize() for w in k.split("-")]))
                    for k in CLASS_FULL])
CLASS_CODE = {}
for _k, _v in CLASS_FULL.items():
    CLASS_CODE[re.sub(r"[.\s-]", "", _k).upper()] = CLASS_SHORT[_k]
    CLASS_CODE[re.sub(r"[.\s-]", "", _v).upper()] = CLASS_SHORT[_k]


def class_code(raw):
    """The class year as ONE canonical short code: Fr, So, Jr, Sr, Gr, R-Sr...

    ⚠ THE SAME COLUMN WAS SHOWING TWO FORMATS. The Player Ratings board read
    the school's raw string, so one sorted column held "Jr" (12), "Sr" (16),
    "Senior" (6), "Junior" (2), "R-Sr", "Redshirt Junior" -- ten spellings of
    five classes, because `class_full()` existed but was wired to only one of
    the two places a class reaches the page (R4).

    An unrecognised value comes back UNCHANGED and a missing one stays missing:
    this normalises a LABEL, it never invents a class for a player who has no
    published one.
    """
    if not raw:
        return raw
    key = re.sub(r"[.\s-]", "", str(raw)).upper()
    return CLASS_CODE.get(key, raw)


def class_full(raw):
    """The published class year, spelled out when it is a known abbreviation.

    Case and full stops vary between schools ("So.", "so", "R-Fr."), so the
    lookup is normalised. An unknown value comes back UNCHANGED -- including
    one already spelled out, which simply is not in the map.

    Goes through class_code() first so a value the school spelled out ("Senior")
    and one it abbreviated ("Sr.") land on the same answer.
    """
    if not raw:
        return raw
    key = re.sub(r"[.\s]", "", str(class_code(raw))).upper()
    return CLASS_FULL.get(key, raw)


def roster_identity_index():
    """(team_norm, nkey(name)) -> official identity, from the 2026 rosters.

    ⚠ THE ROSTER IS THE AUTHORITY ON HOW A NAME IS SPELLED AND WHAT YEAR SHE
    IS. The box-score feed spells the same player differently between matches
    ("DeLeye" one night, "Deleye" the next); the school's own roster does not.
    So display spelling and class year come from here, and the FEED only ever
    supplies counts.

    Returns (index, ambiguous). `ambiguous` holds any team where two DIFFERENT
    roster players normalise to one key -- two real people the canonical key
    cannot tell apart. They are deliberately NOT merged and NOT joined; a guard
    asserts the list is empty so the day it stops being empty is the day
    somebody looks, rather than the day two players quietly become one.
    """
    rosters = ((load("data/raw/%d/rosters_%d.json" % (SEASON, SEASON)) or {})
               .get("teams", {}) or {})
    for _t, _r in ((load("data/raw/%d/rosters_recovered_%d.json" % (SEASON, SEASON))
                    or {}).get("teams", {}) or {}).items():
        if _r.get("players") and not ((rosters.get(_t) or {}).get("players")):
            rosters[_t] = _r
    idx, ambiguous = {}, []
    for team, rec in rosters.items():
        tn = team_norm(team)
        seen = {}
        for pl in (rec.get("players") or []):
            nm = (pl.get("name_raw")
                  or ("%s %s" % (pl.get("first") or "", pl.get("last") or "")).strip())
            k = nkey(nm)
            if not k:
                continue
            if k in seen and seen[k] != nm:
                ambiguous.append({"team": team, "key": k,
                                  "names": sorted({seen[k], nm})})
                continue
            seen[k] = nm
            idx[(tn, k)] = {
                "display": nm,
                "class": class_full((pl.get("class_raw") or "").strip()) or None,
                "pos": (pl.get("pos_raw") or "").strip() or None,
                "num": pl.get("num_raw"),
            }
    return idx, ambiguous


def _six_enriched(lu, xfer, photos, team_name, out_map):
    # type: (Optional[Dict], Dict, Dict, str, Dict) -> Optional[Dict]
    """Attach transfer line and photo to each projected-six entry.

    Purely additive: a player with no transfer record and no photo comes back
    exactly as she went in. Nothing is synthesised -- a missing field is absent,
    never zeroed, so the card that reads this renders an omission rather than a
    stand-in (R5).

    ⚠ A TRANSFER HAS A DIRECTION, AND ATTACHING IT WITHOUT ONE PRODUCES
    NONSENSE. `xfer` is keyed by name and describes an INCOMING move -- the
    school she came FROM. A departed player still sits in her old team's 2025
    six, so a bare name lookup hung her own record on the team she LEFT and the
    card read "Ayden Ames \u00b7 Transfer \u00b7 Texas" on Texas's page.
    So the from-school is attached only when it is not this team, and the
    opposite direction is served by `out_map` -- the existing
    (from_team_id, name) -> destination index -- which is the fact that
    actually matters about a player who has gone: where she went.
    """
    if not isinstance(lu, dict):
        return lu
    six = lu.get("usual_six_2025")
    if not isinstance(six, list):
        return lu
    outsix = []
    for c in six:
        if not isinstance(c, dict):
            outsix.append(c)
            continue
        k = nkey(c.get("name"))
        d = dict(c)
        xf = xfer.get(k)
        if xf and (xf.get("from_team") or "") != team_name:
            d["xf"] = xf
        dest = out_map.get((str(lu.get("team_id")), k))
        if dest and dest != team_name:
            d["went_to"] = dest
        ph = photos.get(re.sub(r"[^a-z]", "", (c.get("name") or "").lower()))
        if ph:
            d["photo"] = ph
        outsix.append(d)
    return dict(lu, usual_six_2025=outsix)


def transfer_index():
    # type: () -> Dict[str, Dict]
    """normalised name -> where she transferred from, and her line there.

    ⚠ THE SAME ANCHOR AS EVERYWHERE ELSE: (from_team_id, name), never the name
    alone. A bare-name lookup across ~6,000 players is precisely the
    wrong-person match R8 exists for, and this one would attribute a whole
    season at the wrong school.

    Built standalone because the equivalent dict already existed inside the
    team-page builder and was not reachable from the player payload -- which is
    why a player card could show her class and her stats and stay silent about
    the fact she played somewhere else last year.
    """
    out = {}
    ret = load("data/returning_%d.json" % SEASON) or {}
    # ⚠ REUSE THE EXISTING BUILDERS. My first draft invented _prior_lines()
    # and _team_id_to_name(), neither of which exists -- the real ones are
    # prior_pos_index() and a small map off data_2025.json, both already used
    # by the team-page builder for exactly this purpose.
    prior_pos = prior_pos_index()
    id2name = {}
    for _t in ((load("data/data_2025.json") or {}).get("teams") or []):
        id2name[str(_t.get("team_id"))] = _t.get("name_short") or _t.get("name_full")
    for team_rec in (ret.get("teams") or {}).values():
        for pl in (team_rec.get("transfer_in_official") or []):
            if not isinstance(pl, dict):
                continue
            k = nkey(pl.get("name"))
            if not k:
                continue
            prev = (prior_pos or {}).get(
                (str(pl.get("from_team_id")), k)) or {}
            out[k] = {
                "from_team": (id2name or {}).get(str(pl.get("from_team_id"))),
                "prior_pts": prev.get("pts") if prev.get("sets") else None,
                "prior_sets": prev.get("sets") or None,
                "prior_pos": prev.get("pos"),
            }
    return out


def box_and_players(res, photos=None, honours=None, xfer=None,
                    count_gids=None):
    """Per-match box scores, and a per-player season view with a game log.

    ⚠ THESE TWO OUTPUTS NEED DIFFERENT INPUTS AND I HAD THEM SHARING ONE.
    Passing only the counting matches kept an exhibition out of every rate --
    correct -- but it also meant the match had NO BOX SCORE AT ALL, so a night
    against Nebraska simply vanished. Cody asked for the opposite: keep it out
    of the ratings, but log it.
    So `res` is every match, and the BOXES are built from all of it; only the
    per-player SEASON AGGREGATE is restricted, to `count_gids`. A reader can
    open the exhibition and read every line in it; nothing in a career total,
    a per-set rate or a rating can see it.

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

    def _richer(a, b):
        """Is game record `a` a fuller line than `b`? Deterministic, so the
        surviving row never depends on which arrived first."""
        ka = ((a.get("sets") or 0),
              (a.get("ta") or 0) + (a.get("k") or 0) + (a.get("digs") or 0)
              + (a.get("ast") or 0))
        kb = ((b.get("sets") or 0),
              (b.get("ta") or 0) + (b.get("k") or 0) + (b.get("digs") or 0)
              + (b.get("ast") or 0))
        return ka > kb

    # Hoisted: the membership set is needed while building each game record,
    # not only when the Division-I directory is filtered further down. Same
    # call, one place, so the flag on a match and the filter on the list can
    # never disagree about who is Division I.
    _di_now = di_teams()

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    _roster_ident, _roster_ambiguous = roster_identity_index()

    # None means "everything counts", which is what every other caller wants.
    _counts = None if count_gids is None else set(str(x) for x in count_gids)
    boxes = {}
    players = {}
    _skipped_from_totals = set()
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
            # ⚠ THE DEFECT THIS REPLACES. The key was the team plus the name AS
            # THE FEED SPELLED IT, so "Brooklyn DeLeye" and "Brooklyn Deleye"
            # were two players with one match each -- and the same for Kassie
            # O'Brien/O'brien and Abby Vander Wal/Vander wal. Measured: 3
            # duplicate identities across 152 rows. The canonical key is the
            # team plus nkey(), the lowercase-letters-only convention already
            # used for photos, honours and the transfer join.
            _nk = nkey(nm)
            # ⚠ THE ROW IS STILL BUILT AND STILL LANDS IN THE BOX SCORE -- only
            # the season aggregate skips it. That is the whole distinction:
            # logged, not counted.
            if _counts is not None and gid not in _counts:
                _skipped_from_totals.add(gid)
                continue
            _ident = _roster_ident.get((team_norm(row["team"]), _nk)) or {}
            pk = row["team"] + "|" + _nk
            p = players.setdefault(pk, {
                # official roster spelling wins; the feed only supplies counts
                "name": _ident.get("display") or nm,
                "nkey": _nk,
                "class": _ident.get("class"),
                "team": row["team"],
                "pos": row["pos"] or _ident.get("pos") or "",
                "num": row["num"], "games": {},
                # Her own headshot, so the player panel and the Players table
                # show the same face as the roster and the stats page.
                "photo": ((photos or {}).get(row["team"]) or {}).get(_nk),
                "aa": (honours or {}).get("%s|%s" % (row["team"], _nk)),
                # ⚠ WHERE SHE CAME FROM. Absent for a player who did not
                # transfer -- absent, not an empty string, so the card can tell
                # "did not transfer" from "we do not know".
                "xf": (xfer or {}).get(_nk),
            })
            # ⚠ NOTHING IS ACCUMULATED HERE ANY MORE. Totals used to be summed
            # as rows arrived and the match log deduped afterwards, so a second
            # row for the SAME player in the SAME match showed one line in the
            # log and counted twice in the season totals -- a log and a total
            # that disagree, with nothing on the page to show which was wrong.
            # The unique game record is chosen first; every total and rate is
            # derived from those records below.
            _game = {
                "d": date_of.get(gid), "gid": gid,
                "opp": opp_of.get((gid, row["team"])),
                # ⚠ WHETHER THE OPPONENT IS DIVISION I TRAVELS WITH THE MATCH.
                # The site deliberately does NOT filter non-D-I opponents --
                # filtering would change what every number means without saying
                # so -- and it states that on the Stats table. It did not state
                # it on the PLAYER card, which is where a reader actually meets
                # the number: Catori Crawford's whole 2026 line is one match
                # against Elizabeth City St. (Division II) and rendered ".500
                # HIT" in the same type as an SEC hitter's .164 over 73 swings.
                # The caveat has to sit on the row, not one view away.
                # "not Division I" is what we can actually show: the team is
                # absent from the D-I membership set. It does not say D-II.
                "nondi": bool(_di_now) and
                         (opp_of.get((gid, row["team"])) or "") not in _di_now,
                "k": k, "e": e, "ta": a, "hit": row["hit"],
                "digs": row["digs"], "bs": bs, "ba": ba,
                # ⚠ ASSISTS BELONG ON A MATCH LINE. Without them a setter's
                # game log reads as if she did nothing: Izzy Starck's 41-assist
                # night showed "2k · 0e · 3ta · 13d" and no sign of the number
                # that was actually her match.
                "ast": row["ast"],
                "aces": row["aces"], "sets": sets, "pts": row["pts"],
            }
            # Same canonical player, same game: keep the RICHER valid row --
            # more sets, then more counted volume as a deterministic tiebreak,
            # so the choice never depends on file order.
            _prev = p["games"].get(gid)
            if _prev is None or _richer(_game, _prev):
                p["games"][gid] = _game
        if rows:
            boxes[gid] = rows

    out = []
    # ⚠ THE BOX SCORES KEEP EVERYONE; THIS LIST DOES NOT. `boxes` is untouched,
    # so a D-II opponent's players still appear in the box score of the match
    # they actually played -- that is a record of what happened. The Players TAB
    # is a Division-I directory, so it carries Division-I players.
    _di = _di_now
    for p in players.values():
        if _di and p.get("team") and p["team"] not in _di:
            continue
        # THE SEASON IS THE SUM OF THE UNIQUE GAMES, by construction.
        p["games"] = sorted(p["games"].values(), key=lambda g: (g["d"] or ""),
                            reverse=True)
        for f in ("sets", "k", "e", "ta", "aces", "digs", "bs", "ba", "ast",
                  "pts"):
            p[f] = float(sum(g.get(f) or 0 for g in p["games"]))
        s_ = p["sets"] or 1
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
    _di_ms = di_teams()

    def blank():
        return {"k": 0.0, "e": 0.0, "ta": 0.0, "ast": 0.0, "digs": 0.0,
                "bs": 0.0, "ba": 0.0, "aces": 0.0, "sets": 0.0, "matches": 0,
                # ⚠ HOW MANY OF THOSE MATCHES WERE AGAINST A NON-D-I SIDE.
                # Norfolk St.'s 2026 page read "Hitting % .390" against
                # opponents' ".037" -- both true, both from ONE Division-II
                # match. The sample size was already printed; the DIVISION of
                # the opponent was not, and that is the part that makes .390
                # mean something other than what it looks like.
                "nondi": 0,
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

    # ⚠ ONLY THE MATCHES THAT COUNT. `boxes` deliberately carries every match
    # including exhibitions -- that is what lets an exhibition's box score be
    # VIEWED -- but these are SEASON totals, and the D-I split below cannot
    # exclude an exhibition because Nebraska v Florida is D-I on both sides.
    # So the standings' +/- showed Nebraska a differential from a match its
    # record on the same row refuses to count. The counting set is `res` --
    # the same list the record is built from -- so the two cannot disagree.
    _cnt_gids = set(str(r.get("gid")) for r in (res or []) if r.get("gid"))
    for gid, rows in (boxes or {}).items():
        if _cnt_gids and str(gid) not in _cnt_gids:
            continue                                    # exhibition or otherwise non-counting
        by_team = {}
        for r in rows or []:
            by_team.setdefault(r.get("team"), []).append(r)
        if len(by_team) != 2:
            continue                                    # cannot form an opponent
        names = list(by_team)
        for i, team in enumerate(names):
            opp = names[1 - i]
            mine = acc.setdefault(team, {"own": blank(), "opp": blank(),
                                         # ⚠ THE SAME TOTALS, DIVISION-I
                                         # OPPONENTS ONLY. The standings row
                                         # shows a Division-I-only record and
                                         # was showing a +/- built from EVERY
                                         # opponent beside it -- Norfolk St.
                                         # read "Overall 0-0 ... +9.67", a
                                         # differential earned in a match the
                                         # record on the same row does not
                                         # count. Two bases in one row, which
                                         # is the mix R4 exists to stop.
                                         # Accumulated in the same pass so the
                                         # two can never drift.
                                         "own_di": blank(),
                                         "opp_di": blank()})
            _opp_is_di = not (_di_ms and opp not in _di_ms)
            _pairs = [(by_team[team], mine["own"]), (by_team[opp], mine["opp"])]
            if _opp_is_di:
                _pairs += [(by_team[team], mine["own_di"]),
                           (by_team[opp], mine["opp_di"])]
            for src, dst in _pairs:
                sets = 0.0
                for r in src:
                    for f in ("k", "e", "ta", "ast", "digs", "bs", "ba", "aces"):
                        dst[f] += float(r.get(f) or 0)
                    sets = max(sets, float(r.get("sets") or 0))
                dst["sets"] += sets
                dst["matches"] += 1
                # The opponent's division, from the same membership set the
                # listing filter below uses -- one answer to "who is D-I".
                if _di_ms and opp not in _di_ms:
                    dst["nondi"] += 1
            mine["own"]["board"] += (board.get(str(gid)) or {}).get(team, 0.0)
            mine["opp"]["board"] += (board.get(str(gid)) or {}).get(opp, 0.0)
            if _opp_is_di:
                mine["own_di"]["board"] += (board.get(str(gid)) or {}).get(team, 0.0)
                mine["opp_di"]["board"] += (board.get(str(gid)) or {}).get(opp, 0.0)

    out = {}
    for team, sides in acc.items():
        row = {}
        for key in ("own", "opp", "own_di", "opp_di"):
            d = sides[key]
            n = d["sets"] or 0
            row[key] = {
                "matches": d["matches"], "nondi": d["nondi"],
                "sets": round(n, 1),
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
    _di = _di_ms
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


def roster_index():
    # type: () -> List[Dict]
    """Every rated player, compact, so the directory covers Division I.

    ⚠ THE PLAYERS TAB ONLY KNEW WHOEVER HAD A 2026 BOX-SCORE LINE. In August
    that is 149 people, so searching for Bergen Reilly -- a First-Team
    All-American who simply has not played yet -- returned nothing, which reads
    as "we have never heard of her" rather than "the season has not started".
    ⚠ MEASURED BEFORE ADDING IT: 142 bytes a head, 392 KB for all 2,828, on a
    page that is already 9.4 MB. Four percent for the difference between a
    directory and a fragment. The full card stays behind the click.
    """
    doc = load("data/player_rating_%d.json" % SEASON)
    if not doc:
        return []
    out = []
    for p in (doc.get("players") or []):
        pr = p.get("prior") or {}
        ps = p.get("pass") or {}

        def val(k):
            c = pr.get(k) or {}
            return c.get("value")
        r = {"n": p.get("name"), "t": p.get("team"), "p": p.get("pos"),
             "r": p.get("power_rank"), "pc": p.get("overall_pct")}
        for key, v in (("c", p.get("cls")), ("nu", p.get("num")),
                       ("ro", p.get("rotation_role"))):
            if v:
                r[key] = v
        for key, v in (("k", val("kps")), ("h", val("hit")),
                       ("d", val("dps")), ("b", val("bps"))):
            if v is not None:
                r[key] = round(v, 2)
        if p.get("prior_sets"):
            r["s"] = int(p["prior_sets"])
        if ps.get("recv_share") is not None:
            r["rc"] = round(ps["recv_share"], 2)
        # whether a full 2026 card exists behind the name
        if p.get("matches"):
            r["live"] = 1
        out.append(r)
    out.sort(key=lambda x: (x.get("t") or "", x.get("n") or ""))
    return out


def team_stars(limit=3):
    # type: (int) -> Dict
    """The players worth knowing on each team, for a match preview.

    ⚠ RANKED BY PERCENTILE WITHIN POSITION, NOT BY RAW RATING. The raw scores
    are on different scales per position -- an outside's spread is wider than a
    setter's -- so sorting a mixed list by the raw number would hand every
    slot to outsides and quietly hide the setter who runs the offence. The
    percentile asks the same question of each of them: how far above her own
    position's field is she.

    ⚠ AND A LABEL PER PLAYER, BECAUSE A NUMBER ALONE IS NOT SCOUTING. "6-rot
    outside, 23% of swings from the back row" tells you what to watch for; a
    rating of +11.4 does not.
    """
    doc = load("data/player_rating_%d.json" % SEASON)
    if not doc:
        return {}
    by = collections.defaultdict(list)
    for r in (doc.get("players") or []):
        if r.get("team") and r.get("overall_pct") is not None:
            by[r["team"]].append(r)
    out = {}
    for team, rows in by.items():
        rows.sort(key=lambda x: -(x.get("overall_pct") or 0))
        picked = []
        for r in rows[:limit]:
            ps = r.get("pass") or {}
            picked.append({
                "n": r.get("name"), "pos": r.get("pos"),
                "cls": r.get("cls"), "num": r.get("num"),
                "pct": r.get("overall_pct"), "pwr": r.get("power_rank"),
                "role": r.get("rotation_role"),
                "brs": r.get("back_row_share"),
                "recv": ps.get("recv_share"),
                # her headline rate, from whichever season actually has one
                # ⚠ A HEADLINE STAT HAS TO SUIT THE POSITION. Kills per set is
                # meaningless for a libero -- Bryant's Carrina Barron rendered
                # "-0.0 kills/set", a negative zero, because a defender's
                # schedule-adjusted kill rate sits at nothing and the
                # adjustment can push it just below. Digs travel too, so the
                # card can lead with the number that describes her job.
                "kps": ((r.get("season") or {}).get("components", {})
                        .get("kps", {}) or {}).get("value")
                       or ((r.get("prior") or {}).get("kps", {}) or {}).get("value"),
                "dps": ((r.get("season") or {}).get("components", {})
                        .get("dps", {}) or {}).get("value")
                       or ((r.get("prior") or {}).get("dps", {}) or {}).get("value"),
                "bps": ((r.get("season") or {}).get("components", {})
                        .get("bps", {}) or {}).get("value")
                       or ((r.get("prior") or {}).get("bps", {}) or {}).get("value"),
                # ⚠ asps IS ASSISTS/SET, sps IS ACES, aps IS ATTACKS -- verified
                # against player_rating.py:213-215 and by magnitude (setter
                # median asps 4.68, sps 0.19). This project has already shipped
                # one build where two files disagreed about which key meant
                # aces and which meant assists (R4); check the definition, do
                # not infer it from the name.
                "asps": ((r.get("season") or {}).get("components", {})
                         .get("asps", {}) or {}).get("value")
                        or ((r.get("prior") or {}).get("asps", {}) or {}).get("value"),
                "live": bool(r.get("matches")),
            })
        if picked:
            out[team] = picked
    return out


def attach_ratings(plist):
    # type: (List[Dict]) -> int
    """Put each player's own rating onto her card entry.

    ⚠ JOINED ON (team, name), WHICH IS SAFE HERE AND ONLY HERE. Both sides are
    already scoped to one team, so this cannot become the cross-team
    wrong-person match R8 exists for. A player the ratings do not carry simply
    gets nothing -- her card then says the rating is not available rather than
    showing a blank number where one belongs (R5).
    """
    doc = load("data/player_rating_%d.json" % SEASON)
    if not doc:
        return 0
    idx = {}
    for r in (doc.get("players") or []):
        if r.get("team") and r.get("name"):
            idx[(r["team"], nkey(r["name"]))] = r
    n = 0
    for p in plist:
        r = idx.get((p.get("team"), nkey(p.get("name"))))
        if not r:
            continue
        n += 1
        p["rt"] = {
            "pos": r.get("pos"),
            "pw": r.get("power"), "pwr": r.get("power_rank"),
            "rs": r.get("resume_score"), "rsr": r.get("resume_rank"),
            "pct": r.get("overall_pct"),
            "w": r.get("season_weight"), "hp": r.get("has_prior"),
            "ps": r.get("prior_sets"),
            "role": r.get("rotation_role"), "prole": r.get("pass_role"),
            "brs": r.get("back_row_share"),
            "pass": r.get("pass"),
            "n": (doc.get("boards") or {}).get(r.get("pos"), {}).get("n"),
            "sup": (doc.get("boards") or {}).get(r.get("pos"), {}).get("support"),
        }
    return n


def player_rating_payload():
    # type: () -> Dict
    """The position boards, trimmed to what the page renders.

    ⚠ TRIMMED, BECAUSE THE FULL FILE IS ~2,800 PLAYERS WITH A FULL COMPONENT
    BREAKDOWN EACH. Shipping all of it would add megabytes to a page that is
    already 9 MB. Each board carries its top rows plus the evidence for those
    rows; the rest stays on disk.

    Returns an empty shell rather than failing when the ratings have not been
    built -- the view then says so instead of rendering an empty table.
    """
    doc = load("data/player_rating_%d.json" % SEASON)
    if not doc:
        return {"ok": False, "boards": {}, "rows": {}, "all_star": None}
    keep = 60
    rows = {}
    for pos, board in (doc.get("boards") or {}).items():
        grp = [p for p in doc.get("players") or [] if p.get("pos") == pos]
        grp.sort(key=lambda x: x.get("power_rank") or 10 ** 6)
        # ⚠ KEEP THE TOP OF EACH ROLE, NOT JUST THE TOP OF THE POSITION. A
        # six-rotation filter over a list trimmed on the combined board would
        # show whichever six-rotation players happened to make the overall top
        # 60 -- which is not the top of that role, and would silently be a
        # different question from the one the filter asks.
        take, seen = [], collections.Counter()
        for p in grp:
            r = p.get("role") or "-"
            if seen[r] < keep or len(take) < keep:
                seen[r] += 1
                take.append(p)
        out = []
        for p in take:
            src = p.get("prior") if p.get("season") is None else \
                (p.get("season") or {}).get("components")
            drv = []
            for f, c in sorted((src or {}).items(),
                               key=lambda kv: -abs(kv[1].get("contrib") or 0)):
                if c.get("value") is None:
                    continue
                drv.append({"f": f, "v": c.get("value"),
                            "c": c.get("contrib")})
            out.append({
                "n": p.get("name"), "t": p.get("team"), "pos": pos,
                # ⚠ NORMALISED HERE, AT THE BOUNDARY. player_rating.py reads
                # the school's own string via roster_class(), so this column
                # held "Jr" and "Senior" and "Redshirt Junior" at once -- ten
                # spellings of five classes in one sorted column. The map is
                # not copied into player_rating.py; the value is canonicalised
                # where it enters the page, so there is one definition (R4).
                "cls": class_code(p.get("cls")), "num": p.get("num"),
                "pw": p.get("power"), "pwr": p.get("power_rank"),
                "rs": p.get("resume_score"), "rsr": p.get("resume_rank"),
                "w": p.get("season_weight"), "m": p.get("matches"),
                "sets": p.get("sets"), "hp": p.get("has_prior"),
                "ps": p.get("prior_sets"), "oz": p.get("opp_z"),
                "role": p.get("rotation_role"),
                "prole": p.get("pass_role"),
                "brs": p.get("back_row_share"),
                "pct": p.get("overall_pct"),
                "orank": p.get("overall_rank"),
                "pass": p.get("pass"),
                "drv": drv[:4],
            })
        rows[pos] = out
    star = doc.get("all_star") or {}

    def thin(pl):
        if not pl:
            return None
        return {"n": pl.get("name"), "t": pl.get("team"),
                "pw": pl.get("power"), "pwr": pl.get("power_rank"),
                "cls": pl.get("cls")}
    st = None
    if star:
        st = {
            "teams": [{"tier": t["tier"], "system": t["system"],
                       "profile": t["profile"],
                       "slots": [{"pos": x["pos"], "p": thin(x["player"])}
                                 for x in t["slots"]]}
                      for t in star.get("teams") or []],
            "alt": ({"system": star["alt_62"]["system"],
                     "profile": star["alt_62"]["profile"],
                     "slots": [{"pos": x["pos"], "p": thin(x["player"])}
                               for x in star["alt_62"]["slots"]]}
                    if star.get("alt_62") else None),
            "hm": dict((k, [thin(x) for x in v])
                       for k, v in (star.get("honourable") or {}).items()),
        }
    # the overall board: the best of each position by how far above her own
    # position's field she stands
    allrows = []
    for v in rows.values():
        allrows.extend(v)
    allrows = [r for r in allrows if r.get("pct") is not None]
    allrows.sort(key=lambda r: -(r.get("pct") or 0))
    # ⚠ RENUMBER OVER WHAT IS ACTUALLY SHOWN. The stored overall_rank is
    # computed across all 2,829 rated players, but only the top of each
    # position board is shipped -- so the rendered column read 1, 2, 4, 5, 33,
    # and gaps in a rank column read as a bug rather than as trimming. The
    # percentile beside it is the real datum; this is just its index.
    allrows = [dict(r, orank=i) for i, r in enumerate(allrows[:60], 1)]
    return {"ok": True, "meta": doc.get("meta") or {},
            "boards": doc.get("boards") or {}, "rows": rows,
            "overall": doc.get("overall") or {},
            "overall_rows": allrows, "all_star": st}


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
    # ⚠ THE COLUMN KEEPS ITS IDENTITY EVEN WHEN THE VALUE IS MISSING. The first
    # version emitted `class="n"` for an absent value and `class="n hx dv"` for
    # a present one -- so the SAME logical column had two different class sets
    # depending on its contents, and any rule that targets it (a mobile hide, a
    # width, a colour) silently applied to some rows and not others. That is how
    # a column meant to be hidden at 390px reappeared for exactly the teams with
    # no data.
    #
    # `hx` is deliberately NOT added here: it is what paints the gradient, and
    # an absent measurement must never be painted as a neutral one (R5). The
    # column class is identity; `hx` is "there is a value".
    if v is None:
        return '<td class="n %s">&mdash;</td>' % kind
    t = 0.5 if hi == lo else (float(v) - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return '<td class="n hx %s" style="--t:%.3f"><b>%s</b></td>' % (kind, t, txt)



def gameday_readiness():
    """The Friday panel's facts. Read-only, and honest about what is unproven.

    ⚠ IT MAY NEVER IMPLY LIVE STATS ARE ESTABLISHED. The whole point of the
    four checkpoints is that the question is open; a panel that quietly read
    "ready" would answer it by decoration.
    """
    try:
        import preflight_live as PF
        import probe_observe as PO
    except Exception:                                        # noqa: BLE001
        return None
    try:
        cands = PF.candidates()[:1]
    except Exception:                                        # noqa: BLE001
        cands = []
    if not cands:
        return {"none": True}
    c = cands[0]
    done = {}
    try:
        for r in PO.read_observations():
            if str(r.get("game_id")) == c["game_id"]:
                done[r.get("checkpoint")] = r.get("outcome")
    except Exception:                                        # noqa: BLE001
        done = {}
    # ⚠ "PROVEN" MEANS ONE THING ONLY: a real match observed serving team
    # totals while in progress. Nothing else sets it.
    proven = any(v == "live_with_team_stats" for v in done.values())
    return {
        "none": False,
        "game_id": c["game_id"],
        # ⚠ THESE RANKS ARE DIGBY'S TOP 25, NOT THE AVCA POLL -- preflight_live
        # reads data/digby_top25_*.json. This panel printed a bare "#21 Kansas"
        # directly beneath a Rally Tape printing "#15 Kansas" from the AVCA
        # feed. Both numbers were right; the screen was not.
        "matchup": "%s%s at %s%s" % (
            rank_badge("digby", c["away_rank"], compact=True, text=True),
            c["away"],
            rank_badge("digby", c["home_rank"], compact=True, text=True),
            c["home"]),
        "when_pt": c["when_pt"],
        "link": c["link"],
        "steps": [("pre", "Before first serve"), ("live", "During play"),
                  ("final", "Right after final"), ("box", "Official box score")],
        "done": done,
        "live_stats_proven": proven,
    }

def calendar_tracks():
    """The weekly ranking calendar: three tracks, kept apart on purpose.

    ⚠ THREE RULERS, THREE CADENCES, AND MOVEMENT NEVER CROSSES THEM. Digby
    Weekly is DERIVED (ours, from results through a stated Sunday cutoff); the
    AVCA poll is OFFICIAL (coaches vote, we only capture it); VolleyTalk is
    COMMUNITY and arrives by hand. Subtracting a rank on one from a rank on
    another is arithmetic on two different things -- the mistake
    test_rankings_history.py already exists to prevent -- so each track's
    movement is computed only against its own previous entry.

    ⚠ AND VOLLEYTALK IS DISPLAY-ONLY. It is read here, rendered, and reaches
    nothing else: no rating, no projection, no ballot. Guarded.
    """
    import weekly as WK

    out = {"digby": [], "avca": [], "vt": [], "waiting": None}

    # ---- Digby Weekly (DERIVED) -------------------------------------------
    hist = os.path.join(REPO, "data", "rankings_history_%d.jsonl" % SEASON)
    if os.path.exists(hist):
        for line in open(hist, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            # ⚠ THE LEGACY ROWS STAY EXACTLY AS WRITTEN and are shown for what
            # they are. The first blended week archived only 35 teams, so it
            # cannot support movement for team 36 onward; saying "35 of 348"
            # is the honest label. Nothing is backfilled.
            n = len(r.get("teams") or [])
            legacy = r.get("track") != "digby_weekly"
            out["digby"].append({
                "week": r.get("week"),
                "label": r.get("label") or ("Week of %s" % (r.get("date") or "?")),
                "cutoff": r.get("cutoff"),
                "captured": r.get("captured_utc") or r.get("date"),
                "n": n,
                "finals": r.get("finals_included"),
                "withdrawn": r.get("withdrawn_excluded"),
                "policy": r.get("disposition_policy"),
                "completeness": r.get("completeness") or ("legacy" if legacy else None),
                "source": r.get("source"),
                "partial": n < 300,
                "legacy": legacy,
            })
    out["digby"].sort(key=lambda x: (x.get("cutoff") or "", x.get("week") or ""))

    # ---- what the NEXT freeze is waiting for -------------------------------
    try:
        st = WK.status(SEASON)
        by = {}
        for b in st["blocking"]:
            by[b["why"]] = by.get(b["why"], 0) + 1
        # ⚠ BLOCKERS GROUPED, NOT NARRATED. A list of 39 fixtures is a wall;
        # "29 withdrawn, 0 live, 0 unknown" is the same information a reader
        # can act on. Each group keeps a couple of examples so it is checkable
        # rather than merely asserted.
        eg = {}
        for b in st["blocking"]:
            eg.setdefault(b["why"], []).append(
                "%s %s" % (b["date"], " v ".join(x or "?" for x in b["teams"])))
        out["waiting"] = {
            "label": st["label"], "cutoff": st["cutoff"], "state": st["state"],
            "finals": st["finals"], "blocking": len(st["blocking"]),
            "why": by, "examples": dict((k, v[:3]) for k, v in eg.items()),
            "withdrawn": len(st["withdrawn"]),
            "policy": st.get("policy"),
            "publishable": st.get("publishable"),
            "frozen": any(d.get("cutoff") == st["cutoff"] for d in out["digby"]),
        }
    except Exception:                                    # noqa: BLE001
        out["waiting"] = None

    # ---- AVCA (OFFICIAL) ---------------------------------------------------
    avca = os.path.join(REPO, "data", "raw", str(SEASON), "polls_avca.jsonl")
    if os.path.exists(avca):
        for line in open(avca, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out["avca"].append({
                # BOTH TIMES. The poll's own "Through Games" stamp is what it
                # claims to cover; captured_utc is when this hub saw it. They
                # are different facts and a reader needs both.
                "stamp": r.get("stamp"),
                "captured": r.get("captured_utc"),
                "n": len(r.get("rows") or []),
                "prev_season": bool(r.get("is_previous_season")),
            })
    out["avca"].sort(key=lambda x: x.get("captured") or "")

    # ---- the community track (manual import) -------------------------------
    # ⚠ PRIVATE ONLY, AND THE GATE CAUGHT ME TWICE. This is somebody else's
    # community poll; the build already refuses to republish it. The first
    # version shipped the track to the public page and the gate ABORTED --
    # correctly. The second version gated only the RENDER, and the gate aborted
    # again on the literal name still sitting in the page script and in two of
    # my own comments. Comments are bytes on a public page like any other.
    # The track is not BUILT for the public page rather than hidden in it:
    # hiding third-party data still ships it, which this project already
    # learned once with the rank VALUES inside const TEAMS.
    if PUBLIC:
        for k in [k for k in list(out) if k == "vt" or k.startswith("vt_")]:
            out.pop(k, None)
        return out
    vt = load("data/volleytalk_polls.json") or {}
    for r in (vt.get("polls") or []):
        out["vt"].append({
            "published": r.get("published"), "through": r.get("through"),
            "url": r.get("url"), "n": len(r.get("rows") or []),
        })
    out["vt"].sort(key=lambda x: x.get("published") or "")
    out["vt_home"] = vt.get("source_home") or ""
    # ⚠ THE TRACK'S NAME AND COPY LIVE IN THE PAYLOAD, NOT IN THE PAGE SCRIPT.
    # Gating the RENDER on `CAL.vt` was not enough: the source still carried
    # the literal name, and the public gate aborted on it -- correctly. With
    # the name here, the public build's JavaScript contains nothing to strip.
    out["vt_name"] = vt.get("source_name") or "Community poll"
    out["vt_tag"] = "Community \u00b7 manual"
    out["vt_empty"] = (
        "Not imported yet. This is a community poll and is never scraped, "
        "logged into, or posted to from here \u2014 an entry appears only when "
        "one is added by hand. It informs nothing else on this site.")
    return out


def powercell(t):
    """POWER, with the scale carried in its own tooltip.

    A number out of 100 that does not say what 100 means is decoration, and
    this one has a specific meaning: 50 is an average Division-I team, and
    every 12.5 points is one standard deviation of team strength.

    ⚠ IT IS A MONOTONE RESCALING OF THE RATING THAT PRODUCES THE RANK BESIDE
    IT, so the two can never disagree. The first version scored last season's
    composite next to a rank taken from the preseason projection -- two
    different quantities -- and put #7 SMU above #6 Louisville, and #348 above
    #347. A score that contradicts the rank printed next to it is worse than no
    score, because both look authoritative.

    ⚠ AND IT IS NOT A BLEND OF HAND-PICKED COMPONENTS. Both AI proposals Cody
    relayed specify a 100-point mix (25 strength / 20 resume / 15 SOS / ...).
    rating_factors.py has now tested fifteen weighting schemes and nine profile
    metrics against held-out matches: nothing beat the fitted composite and nine
    ideas measurably hurt. A nine-way blend would replace a validated ordering
    with an invented one and hide it behind a confident number out of 100.
    """
    v = t.get("power")
    if v is None:
        return '<td class="n pw">&mdash;</td>'
    basis = ("this season's results" if t.get("power_basis") == "live"
             else "the preseason projection, which reads no 2026 result yet")
    return ('<td class="n pw hx seq" style="--t:%.3f" title="Power %.1f. '
            '50 is an average D-I team; every 12.5 points is one standard '
            'deviation. Built from %s."><b>%.1f</b></td>'
            % (max(0.0, min(1.0, (v - 10.0) / 80.0)), v, basis, v))


def resumecell(t, active):
    """RESUME rank -- what a team has EARNED, beside how good it is.

    Two questions, two numbers, and keeping them apart is R3. POWER answers
    "who would win tomorrow" and is driven by margin; this answers "who has
    earned a bid" and ignores margin entirely -- a win is a win.

    ⚠ WHEN IT DOES NOT EXIST YET IT SAYS SO. A resume off one match is not a
    thin resume, it is not a resume: the measure is what a team has earned
    against the schedule it has played, and in August nobody has earned
    anything. Printing a precise-looking rank there would be exactly the kind
    of authoritative-looking non-measurement R5 exists to stop.
    """
    if not active:
        return ('<td class="n rs"><span class="rsoff" title="A r&eacute;sum&eacute; '
                'measures what a team has earned against the schedule it has '
                'played. Too little of the season has been played for anyone to '
                'have earned anything yet.">&mdash;</span></td>')
    v = t.get("resume_rank")
    if v is None:
        return '<td class="n rs">&mdash;</td>'
    wab = t.get("wab")
    tip = "R&eacute;sum&eacute; #%d" % v
    if wab is not None:
        tip += (" &mdash; %+.1f wins above what a bubble team would have taken "
                "from this schedule" % wab)
    return '<td class="n rs" title="%s"><b>%d</b></td>' % (tip, v)


def rank_stamp_pt(utc_iso, now_epoch=None):
    """Human PT phrase for a ranking's own generated_at_utc, or None.

    None -- not a placeholder -- when the stamp is missing or unreadable:
    the caller drops the sentence entirely rather than invent a time (R5).
    """
    ep = parse_logged_utc(utc_iso)
    if ep is None or PT is None:
        return None
    dt = datetime.datetime.fromtimestamp(ep, PT)
    now = datetime.datetime.fromtimestamp(
        now_epoch if now_epoch is not None else time.time(), PT)
    clock = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == now.date():
        return "%s PT today" % clock
    if dt.date() == now.date() - datetime.timedelta(days=1):
        return "%s PT yesterday" % clock
    return dt.strftime("%b %d, ") + clock + " PT"


def top25_view(avca=None):
    # type: (Optional[Dict[str, int]]) -> Dict[str, str]
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
    # The form strip keeps EVERY result, including non-D-I ones -- a match that
    # was played is form. The record beside it counts D-I only, so the pill
    # names the division rather than leaving a "W" that the record does not
    # explain.
    _di_form = di_teams()
    for g in sorted(results() or [], key=lambda x: x.get("epoch") or 0):
        for me, them, mine, theirs in ((g["away"], g["home"], g["away_sets"], g["home_sets"]),
                                       (g["home"], g["away"], g["home_sets"], g["away_sets"])):
            if mine is None or theirs is None:
                continue
            form.setdefault(me, []).append({
                "won": mine > theirs, "score": "%s-%s" % (mine, theirs),
                "opp": them, "opp_rank": ranked.get(them), "date": g.get("date"),
                "nondi": bool(_di_form) and them not in _di_form,
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
    from snapshot_rankings import basis as _basis
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
            # ⚠ MATCH THE BASIS, NOT THE SPELLING. This read
            # `row.get("source") != "digby"`, an exact string -- so the first
            # weekly freeze, written canonically as "blend", was skipped and
            # the Top 25 kept saying "vs preseason" with a real prior week
            # sitting in the archive. THIRD place this same alias drift has
            # appeared; it goes through snapshot_rankings.basis() now, which is
            # the one definition of what a ruler is called.
            if _basis(row.get("source")) != "blend" or \
                    row.get("week") == this_week:
                continue
            # ⚠ PREFER A COMPLETED WEEKLY FREEZE. The legacy row stored only
            # the 35 displayed teams, so comparing against it would leave
            # movement blank for everyone below 35 -- a real prior week beats a
            # partial one even when the partial is more recent.
            def _key(r):
                return (1 if r.get("track") == "digby_weekly" else 0,
                        r.get("cutoff") or r.get("week") or "")
            if best is None or _key(row) > _key(best):
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
    # POWER FOR THE TOP 25, FROM ITS OWN SCORE. Same scale as the Rankings tab
    # (50 = average D-I, 12.5 = one SD) so the two numbers are comparable, but
    # derived from THIS table's blended score rather than the rankings board's
    # composite -- the two tables order teams differently, and a score borrowed
    # from the other one would contradict the rank beside it. That mistake was
    # made once already this session and is guarded.
    _smu = m.get("score_mean")
    _ssd = m.get("score_sd") or 1.0

    def _t25power(r):
        if _smu is None or r.get("score") is None:
            return '<td class="n pw">&mdash;</td>'
        v = max(0.0, min(100.0, 50.0 + 12.5 * (r["score"] - _smu) / _ssd))
        return ('<td class="n pw hx seq" style="--t:%.3f" title="Power %.1f. '
                '50 is an average D-I team; every 12.5 points is one standard '
                'deviation. From this ranking\u2019s own blended score."><b>%.1f</b>'
                '</td>' % (max(0.0, min(1.0, (v - 10.0) / 80.0)), v, v))

    _nets = [abs(r["net_pts_per_set"]) for r in top
             if r.get("net_pts_per_set") is not None]
    nmax = max(_nets) if _nets else 1.0

    # THE COACHES POLL, BESIDE OURS. This page carries two rankings and they
    # disagree; showing only one of them is a claim of consensus that does not
    # exist. The AVCA number is the OFFICIAL one, so it gets the plain numeral,
    # and the gap is stated from OUR side -- a team we rate lower than the poll
    # reads as a positive gap, because the sentence being made is "we are N
    # places more sceptical than the coaches", not the reverse.
    #
    # ⚠ A TEAM THE POLL DOES NOT RANK IS "NR", NOT A BIG GAP. The poll is 25
    # deep; treating unranked as rank 26 would invent a precise disagreement out
    # of an absent number (R5). No gap is shown at all in that case.
    avca = avca or {}

    def _pollcell(team, ours):
        a = avca.get(team)
        if not a:
            return ('<td class="n poll"><span class="nr" title="not in the '
                    'AVCA top 25">NR</span></td>')
        d = ours - a
        if d == 0:
            return ('<td class="n poll" title="the coaches poll agrees">'
                    '<b>%d</b> <i class="pg0">=</i></td>' % a)
        return ('<td class="n poll" title="AVCA coaches poll #%d; our rating '
                'has them %d place%s %s">'
                '<b>%d</b> <i class="%s">%s%d</i></td>'
                % (a, abs(d), "" if abs(d) == 1 else "s",
                   "lower" if d > 0 else "higher", a,
                   "pgdn" if d > 0 else "pgup",
                   "\u2212" if d > 0 else "+", abs(d)))

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
            '<td class="tm">%s%s</td><td class="mvc">%s</td>%s%s<td class="cf">%s</td>'
            '<td class="rec">%s</td><td class="form">%s</td>'
            '%s<td class="n wt">%s</td></tr>'
            % (esc(team), (colors.get(team) or {}).get("primary") or "var(--line)",
               r["rank"], logo_img(team, logos), esc(team), mv,
               _t25power(r),
               _pollcell(team, r["rank"]),
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

    # WHERE WE DISAGREE WITH THE COACHES, stated from the numbers rather than
    # characterised in advance (R1). Every value in this sentence is computed
    # from the two rankings; nothing here is a phrase written before the data.
    _gaps = [(r["rank"] - avca[r["team"]], r["team"], avca[r["team"]], r["rank"])
             for r in top if avca.get(r["team"])]
    poll_txt = ""
    if _gaps:
        _agree = sum(1 for g in _gaps if g[0] == 0)
        _big = max(_gaps, key=lambda g: abs(g[0]))
        _nr = sum(1 for r in top if not avca.get(r["team"]))
        poll_txt = (
            "<b>Against the coaches poll:</b> we agree exactly on %d of the %d "
            "teams both rankings carry%s. The widest gap is <b>%s</b> &mdash; "
            "we have them <b>#%d</b>, the poll has them <b>#%d</b>. "
            % (_agree, len(_gaps),
               (", and %d of our 25 are unranked by the poll" % _nr) if _nr else "",
               esc(_big[1]), _big[3], _big[2]))

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
    _st = rank_stamp_pt(m.get("generated_at_utc"))
    if _st:
        lead += (" <span class=\"rkstamp\">Last recomputed <b>%s</b>, from the "
                 "%d finals in at that moment &mdash; a final folds in on the "
                 "next recompute, not the instant a match ends.</span>"
                 % (_st, played))
    foot = (
        mv_txt + poll_txt +
        "<b>Why so little movement in August?</b> %.1f is not a preference "
        "&mdash; it is the per-match spread (%.2f points/set) divided by how "
        "much the projection still gets wrong (it predicts the next season at "
        "rho %.2f out of sample). One Friday night genuinely is that little "
        "evidence. &nbsp;<b>This is not a resume ranking:</b> it answers who "
        "would win a match, not who has earned a bid &mdash; the bracket tab is "
        "the second question. &nbsp;<b>Who you played is accounted for.</b> "
        "A result is scored as the strength it <i>implies</i> &mdash; the "
        "opponent&rsquo;s own rating plus how far you beat them, with home "
        "court (%+.2f points/set, measured on 2025) taken out &mdash; so losing "
        "narrowly to a top-five team and losing to nobody are not the same "
        "evidence. Tested on 2025 by predicting matches the model had not seen: "
        "it is worth <b>+0.021 AUC</b> at this blend weight, the largest single "
        "improvement measured, with the confidence interval clear of zero at "
        "every reaction speed tried."
        % (k, (m.get("per_match_variance") or 0) ** 0.5,
           m.get("prior_rho_out_of_sample") or 0,
           m.get("home_advantage_pts_per_set") or 0.0))
    return {"rows": "".join(rows), "also": also, "lead": lead, "foot": foot,
            "season": str(SEASON),
            "movehead": ("vs last week" if basis == "week" else "vs preseason")}



def parse_logged_utc(text):
    """Epoch seconds for a prediction-log stamp, or None if it cannot be read."""
    if not text or not isinstance(text, str):
        return None
    try:
        return datetime.datetime.strptime(
            text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def played_forecast(rows, epoch):
    """What a FINISHED match may quote as "what we expected" -- (home_win, why).

    ⚠ THE WHOLE POINT. data/predictions_2026.json is rebuilt every night from
    everything known at the time, so for a match already played it has SEEN the
    result. Reading a forecast out of it after the fact would print a number
    that looks exactly like a real prediction and is not one -- invisible, and
    the most dishonest thing this page could do.

    So a number is shown ONLY on positive proof, all four parts required:
      1. the official start-time epoch exists and parses;
      2. the log row's timestamp exists and parses;
      3. that timestamp is STRICTLY earlier than first serve -- equal is not
         earlier, and a stamp equal to tipoff proves nothing about what was
         known beforehand;
      4. among the rows that satisfy 2 and 3, the EARLIEST one is shown.
    Anything else renders "forecast unavailable" and says which proof is
    missing. Absence of evidence is not evidence: we do not know that an
    undateable row saw the result, and that is exactly why it cannot be shown.

    ⚠ AN UNDATED ROW MUST NOT SUPPRESS A GOOD ONE EITHER. It is skipped, not
    treated as the answer -- the earlier version collapsed the log to one row
    before asking any of this, and a missing stamp sorts first.
    """
    if rows is None:
        rows = []
    elif isinstance(rows, dict):
        rows = [rows]

    # (1) the start time must exist and parse. Epoch 0 is 1970, not a volleyball
    # match, so it counts as absent rather than as a tipoff everything postdates.
    tip = None
    if epoch is not None and not isinstance(epoch, bool):
        try:
            tip = float(epoch)
        except (TypeError, ValueError):
            tip = None
        if tip is not None and tip <= 0:
            tip = None
    if tip is None:
        return (None, "no official start time is on record, so no forecast can "
                      "be shown to predate first serve")

    best = None
    saw_any = saw_undated = saw_late = False
    for r in rows:
        if not isinstance(r, dict):
            continue
        saw_any = True
        if r.get("home_win") is None:
            continue
        t = parse_logged_utc(r.get("logged_utc"))          # (2)
        if t is None:
            saw_undated = True
            continue
        if not t < tip:                                     # (3) STRICTLY before
            saw_late = True
            continue
        if best is None or t < best[0]:                     # (4) earliest valid
            best = (t, r)

    if best is not None:
        return best[1].get("home_win"), "logged %s" % best[1].get("logged_utc")
    if saw_late:
        return None, "the only logged forecast is not earlier than first serve"
    if saw_undated:
        return None, "the logged forecast carries no usable timestamp"
    if saw_any:
        return None, "no forecast was logged before this match"
    return None, "no forecast was logged before this match"

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
    # ⚠ TWO LISTS, ON PURPOSE, AND THE SPLIT IS THE WHOLE POINT.
    #   `res`      -- everything, for anything that DISPLAYS a match. An
    #                 exhibition against good opposition is still worth seeing.
    #   `res_cnt`  -- only what counts, for anything that builds a RECORD or a
    #                 RATE: standings, the 2026 record chip, team season stats,
    #                 player lines.
    # Spikes Under the Lights plays its first two sets to 21 rather than 25, so
    # folding it in would deflate every PER-SET number for Nebraska, Florida,
    # SMU and Penn St. -- four of the best teams in the country -- and nothing
    # on the page would look wrong. It would also invent wins and losses that
    # the NCAA does not recognise.
    res_cnt = [r for r in res if not r.get("exhibition")]
    _n_exh = len(res) - len(res_cnt)
    # ⚠ RESULTS_JSON TAKES res_cnt TOO. That payload is what the form pills and
    # the Top 25's W/L strip read, so an exhibition there would put a result in
    # a team's form that its own record does not contain -- the two would
    # disagree on the same screen, which is how this project has been bitten
    # before (R4: sharing an input is not sharing a definition).
    # School colours read out of each logo SVG (scripts/crawl_team_colors.py).
    # A team with no readable colour is simply absent, and the avatar falls
    # back to a neutral rather than to an invented hue.
    team_colors = ((load("data/team_colors_%d.json" % SEASON) or {})
                   .get("teams") or {})
    _t25 = top25_view(dict((t["team"], t["avca"]) for t in teams
                           if t.get("avca")))
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
    # Division-I membership, once, for everything in this function that needs
    # to say whether an opponent qualifies.
    _di_all = di_teams()
    # ⚠ ALL the matches for the box scores, only the counting ones for the
    # season totals. Passing res_cnt for both kept the exhibition out of every
    # rate and also made it disappear entirely -- no box score, no line, as
    # though it had never been played.
    boxes, plist = box_and_players(res, player_photos(), avca_honours(),
                                   transfer_index(),
                                   count_gids=[r["gid"] for r in res_cnt])
    _nrt = attach_ratings(plist)
    # Season team totals for 2026, both what a team does and what it allows.
    tstats = team_season_stats(boxes, res_cnt)
    stand = standings(teams, res_cnt)
    for _rows in stand.values():
        for _r in _rows:
            _ts = tstats.get(_r["team"]) or {}
            # ⚠ DIVISION-I ONLY, THE SAME MATCH SET AS THE RECORD BESIDE IT.
            # This used to read `own`/`opp`, which count every opponent, so a
            # row could show "Overall 0-0" and "+9.67" together -- a
            # differential from a match the record excludes. A team with no
            # D-I match yet has no D-I differential and renders "--" rather
            # than borrowing a number from a match that does not qualify.
            _o, _d = (_ts.get("own_di") or {}), (_ts.get("opp_di") or {})
            _r["diff"] = (round(_o["pps"] - _d["pps"], 2)
                          if _o.get("pps") is not None and _d.get("pps") is not None
                          else None)
            _r["diff_n"] = _o.get("matches") or 0
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
    tindex = team_index(teams, res_cnt, pred_by_pair, sim_of, ldr_floor,
                        tstats=tstats, aq_of=aq_of, sched_n=sched_n)
    proj_meta = (load("data/projection_2026.json") or {}).get("meta", {})
    level = load("data/level_effect.json") or {}

    first_played = res[0]["date"] if res else None
    played = len(res)

    # ---- rankings rows ---------------------------------------------------
    _bcolors = ((load("data/team_colors_%d.json" % SEASON) or {}).get("teams") or {})

    # Whether the resume exists yet at all -- see resumecell().
    _resume_active = bool((meta or {}).get("resume_active"))

    rrows = []
    for t in sorted(teams, key=lambda x: x["rank26"]):
        def c(v):
            # ⚠ A RANK CARRIES ITS HASH. Every reference column here holds a
            # POSITION, not a score, and a bare "4" beside POWER's "83.6" reads
            # as another measurement. One helper, so all five columns agree.
            return "&mdash;" if v is None else ("#%s" % v)

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
                   '<td></td><td colspan="12">' + why_html
                   + '<div class="dh">The six this projection is built from '
                     '&mdash; each player&rsquo;s 2025 points per set, then '
                     'normalised to a neutral schedule.</div>'
                     '<div class="pls">' + cells + '</div></td></tr>')
        # ⚠ EVERY CELL CARRIES THE NAME OF ITS RULER. Five reference columns
        # rendered as bare "#1 #1 #1 #1 #1" in one row: identical-looking
        # numbers from five different organisations. `data-l` is the label the
        # phone layout prints in front of the value, so a rank is never read
        # without knowing whose it is -- on any width.
        _ti = tindex.get(t["team"]) or {}
        _rec = _ti.get("record26")
        _recn = _ti.get("record26_nondi")
        rec_cell = ('<td class="n rec" data-l="Record">'
                    + (esc(_rec) if _rec else '<span class="dim">&ndash;</span>')
                    + (('<i class="nvd">+%s nD1</i>' % esc(_recn)) if _recn else '')
                    + '</td>')
        rrows.append(
            '<tr class="row" data-r="%d" data-team="%s" tabindex="0" role="link" '
            'style="--tc:%s"><td class="rk">%d%s</td>'
            '<td class="tm">%s%s%s</td><td class="cf" data-l="Conf">%s</td>'
            '%s%s%s<td class="n c-avca" data-l="AVCA">%s</td>'
            '<td class="n hi c-ref" data-l="2025">%s</td>%s'
            '<td class="n c-ref" data-l="RPI">%s</td>%s'
            '<td class="n c-ref" data-l="Ret">%s</td>'
            '<td class="n hi c-ref" data-l="Tourn">%s</td></tr>'
            % (t["rank26"], esc(t["team"]),
               # the school's own colour, same source the Top 25 uses -- the two
               # tables of the same teams should not look like different sites
               (_bcolors.get(t["team"]) or {}).get("primary") or "var(--line2)",
               t["rank26"], mover(t),
               logo_img(t["team"], logos), esc(t["team"]),
               (' <b class="pl6">%s</b>' % t["rot"]) if t.get("rot") and t["rot"] < 6 else "",
               esc(t["conf"]),
               powercell(t),
               resumecell(t, _resume_active),
               rec_cell,
               c(t.get("avca")),
               c(t["rank25"]),
               "" if PUBLIC else ('<td class="n c-ref" data-l="VT">%s</td>'
                                  '<td class="n c-ref" data-l="Massey">%s</td>'
                                  % (c(t.get("vt")), c(t.get("massey")))),
               c(t.get("rpi")),
               "" if PUBLIC else ('<td class="n sp c-ref" data-l="Others">%s</td>'
                                  % (spread or "&mdash;")),
               "&mdash;" if t["ret"] is None else "%.0f%%" % (100 * t["ret"]),
               "&mdash;" if tourn_of.get(t["team"]) is None
               else "%.0f%%" % tourn_of[t["team"]]))

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
            "composite that beat RPI out of sample in 2025. Frozen every "
            "Monday so the movement column has something to measure against."
            % (len(_live), sorted(_gp)[len(_gp) // 2]))
        _rst = rank_stamp_pt(
            ((meta.get("rank_stamp") or {}).get("generated_at_utc")))
        if _rst:
            _rn = (meta.get("rank_stamp") or {}).get("matches_in")
            rank_basis += (
                " <span class=\"rkstamp\">Last recomputed <b>%s</b>%s.</span>"
                % (_rst, (", through %d finals" % _rn) if _rn else ""))
    else:
        _blend = [t for t in teams if t.get("rank_source") == "blend"]
        if _blend:
            _played = [t for t in _blend if (t.get("blend_matches") or 0)]
            _w = max([t.get("blend_season_weight") or 0 for t in _blend] or [0])
            # ⚠ THREE FACTS, NOT TWELVE LINES. The lead had grown to a
            # twelve-line essay standing between a reader and the table -- the
            # methodology was collapsed and the intro absorbed it, which is the
            # opposite of progressive disclosure. What a reader needs before
            # looking at the rankings is: it moves, how much of it is this
            # season, and that the two columns answer different questions.
            # Everything else is in the Methodology panel below the table.
            # ⚠ THE SEASON IS NAMED IN THE LEAD. A standing invariant here --
            # this page carries 2025 context beside 2026 numbers, and a view
            # that does not say which year it is describing is how a finished
            # season leaked into a live one once already.
            _rst = rank_stamp_pt(
                ((meta.get("rank_stamp") or {}).get("generated_at_utc")))
            rank_basis = (
                "<b>Our %d ranking, and it moves with every result.</b> "
                "<b>%d of %d teams have played</b>; the most any team is judged "
                "on this season so far is <b>%d%%</b>. "
                "<b class=\"kpow\">POWER</b> is how strong a team is. "
                "<b class=\"kres\">R&Eacute;SUM&Eacute;</b> is what it has "
                "earned &mdash; %s."
                % (SEASON, len(_played), len(_blend), round(100 * _w),
                   ("live" if _resume_active else
                    "not live until %d D-I matches have been played (%d so far)"
                    % ((meta.get("resume") or {}).get("min_matches") or 200,
                       (meta.get("resume") or {}).get("matches") or 0))))
            if _rst:
                _rn = (meta.get("rank_stamp") or {}).get("matches_in")
                rank_basis += (
                    " <span class=\"rkstamp\">POWER last recomputed <b>%s</b>%s"
                    " &mdash; a final folds in on the next recompute, not the "
                    "instant a match ends.</span>"
                    % (_rst, (", through %d finals" % _rn) if _rn else ""))
        else:
            rank_basis = (
                "<b>Still the preseason projection &mdash; not yet a "
                "result-based ranking.</b> It is 2026 rosters &times; 2025 "
                "production and reads <b>no</b> 2026 result, so it does not "
                "move when a team wins or loses. Run "
                "<code>scripts/digby_top25.py</code> to blend it with what has "
                "actually happened.")

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
    # ⚠ ONE STRUCTURED SOURCE FOR THE LEDGER. The Scores tab was a wall of
    # pre-rendered HTML strings, which is why it could not be filtered by state
    # or grouped by day without re-rendering on the server. The same rows are
    # emitted as data; the page decides how to show them.
    ledger = []
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
        # ⚠ AN ALIAS HID TWO MORE CONSUMERS OF THIS FUNCTION. `rank = rank_badge`
        # meant a grep for "rank_badge(" found four call sites when there were
        # six, and the build only revealed the other two by throwing. Kept --
        # it reads well locally -- but the basis is now named at each call, so
        # the alias can no longer carry a hidden default.
        rank = rank_badge
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
            % (esc(r.get("gid") or ""), esc(day_label(r["date"])), esc(r["time"]), nond1,
               "win" if awin else "", rank("avca", r["away_rank"]),
               logo_img(r["away"], logos), esc(r["away"]), r["away_sets"],
               "" if awin else "win", rank("avca", r["home_rank"]),
               logo_img(r["home"], logos), esc(r["home"]), r["home_sets"],
               strip, venue))

        ledger.append({
            "gid": str(r.get("gid") or ""),
            "d": r["date"], "t": r["time"],
            "a": r["away"], "h": r["home"],
            "as": r["away_sets"], "hs": r["home_sets"],
            "ar": r.get("away_rank"), "hr": r.get("home_rank"),
            "sets": r["sets"],
            "venue": (loc.get("venue") or None),
            "city": (loc.get("city") or None), "st": (loc.get("state") or None),
            "site": site, "event": ev,
            "state": "final",          # `res` is the FINAL-only crawl (R2)
        })

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

    # THE COMING WEEK, as data. Today's slate and the week's headline matches
    # both need fixtures the client can read; the schedule itself is rendered
    # server-side as HTML, so eight days are emitted as JSON rather than the
    # whole 1,524-fixture season -- enough for both jobs, a fraction of the size.
    _today = today_pt()
    _horizon = (_today + datetime.timedelta(days=7)).isoformat()
    _today_s = _today.isoformat()
    # TWO RANKINGS, NAMED. `ar`/`hr` come from the feed and ARE the AVCA coaches
    # poll -- verified against the published poll (BYU 24, Kansas 15, Indiana
    # 16 all agree, and all three differ from ours). That is the official
    # ranking and it leads. `ao`/`ho` are OUR Top 25, carried alongside so the
    # page can show where we disagree instead of quietly presenting one number
    # as "the" ranking. Rendering an unlabelled rank was the real problem: the
    # page showed AVCA numbers with nothing saying whose they were.
    #
    # ⚠ COMPUTED HERE, NOT IN THE PAGE SCRIPT. `TEAMS` is declared near the end
    # of the script and a const in the temporal dead zone THROWS on access --
    # including from typeof -- so a renderer that runs earlier cannot read it.
    # That has already cost this project the standings differential once.
    _ourrank = {}
    for _r in ((load("data/digby_top25_%d.json" % SEASON) or {}).get("top") or []):
        if _r.get("team") and _r.get("rank"):
            _ourrank[_r["team"]] = int(_r["rank"])

    # ---- MATCH DESK ------------------------------------------------------
    # "What should I watch today, why does it matter, and what did it mean
    # after final?" Presentation only: every field below already exists and is
    # copied, never derived. No new rating, no composite score.
    #
    # ⚠ THE FORECAST FOR A FINISHED MATCH COMES FROM THE APPEND-ONLY LOG, AND
    # ONLY FROM A ROW LOGGED BEFORE TIPOFF. data/predictions_2026.json is
    # regenerated nightly from whatever is known NOW -- for a match that has
    # been played, that includes the result, so quoting it as "what we expected"
    # would be inventing a prediction after the fact. score_predictions.py
    # already applies exactly this rule (logged_utc < start_time_epoch); the
    # same rule is applied here rather than a second, looser one.
    _plog = {}
    _plog_path = os.path.join(REPO, "data", "raw", str(SEASON),
                              "prediction_log.jsonl")
    if os.path.exists(_plog_path):
        for _line in open(_plog_path, encoding="utf-8"):
            _line = _line.strip()
            if not _line:
                continue
            try:
                _r = json.loads(_line)
            except ValueError:
                continue
            _gid = str(_r.get("game_id") or "")
            if not _gid or _r.get("home_win") is None:
                continue
            # ⚠ KEEP EVERY ROW. This used to collapse to the lexicographically
            # earliest logged_utc -- and a MISSING timestamp sorts before every
            # real one, so an undated row won the slot and suppressed a
            # perfectly good pre-tipoff row behind it. Which row may be shown
            # is a question about proof, so played_forecast() decides it.
            _plog.setdefault(_gid, []).append(_r)

    _fwd = {}
    for _r in ((load("data/predictions_%d.json" % SEASON) or {}).get("games") or []):
        _fwd[str(_r.get("game_id"))] = _r

    _epoch_of = {}
    _final_of = {}
    for _g in ((load("data/data_%d.json" % SEASON) or {}).get("games") or []):
        _gid = str(_g.get("game_id"))
        _epoch_of[_gid] = _g.get("start_time_epoch")
        if _g.get("state") == "F":
            _final_of[_gid] = _g

    def _desk_forecast(gid, is_final):
        """(home_win, source) or (None, why). Never a post-hoc forecast."""
        gid = str(gid)
        if is_final:
            return played_forecast(_plog.get(gid), _epoch_of.get(gid))
        row = _fwd.get(gid)
        if not row:
            rows = sorted(_plog.get(gid) or [],
                          key=lambda r: r.get("logged_utc") or "")
            row = rows[0] if rows else None
        if not row or row.get("home_win") is None:
            return None, "no forecast on record"
        return row.get("home_win"), "current forecast"

    # ⚠ COMPUTED FOR EVERY TEAM, AND TODAY EVERY ONE IS THE UNAVAILABLE STATE.
    # trend.usable() refuses a line unless there are 3+ dated observations ON
    # ONE BASIS; the 2026 archive holds a preseason week and a digby week, so
    # 0 of 348 are drawable. That is the correct answer rather than a gap, and
    # it turns itself on with no code change once the archive earns it.
    # ⚠ THE FRAMEWORK STAYS; THE 348 IDENTICAL "UNAVAILABLE" BLOCKS DO NOT.
    # Refusing to draw a misleading chart was right. Printing that refusal on
    # every team page was not: it added a module-sized block of copy to 348
    # pages to say nothing, which is decoration made of an apology. A team gets
    # the component only when it has a real same-basis series; the fact that
    # none do yet is stated ONCE, on the Rankings tab, where a reader is
    # already thinking about ranking history.
    _trends = {}
    _trend_ready = 0
    for _t in teams:
        _pts, _why = TREND.usable(TREND.series(TREND.load_history(SEASON),
                                               _t["team"]))
        if _pts:
            _trends[_t["team"]] = TREND.trend_html(SEASON, _t["team"], "POWER")
            _trend_ready += 1
    _trend_note = TREND.history_note(SEASON)

    _pr = dict((t["team"], t["rank26"]) for t in teams if t.get("rank26"))
    _av = dict((t["team"], t.get("avca")) for t in teams if t.get("avca"))
    _tourn = dict((r["team"], r.get("tournament_pct"))
                  for r in (sim.get("teams") or []))
    _desk_today = _today.isoformat()
    _desk_end = (_today + datetime.timedelta(days=6)).isoformat()

    _exh_ledger = exhibitions()
    _desk = []
    for r in sched:
        if not (_desk_today <= r["d"] <= _desk_end):
            continue
        gid = str(r.get("gid") or "")
        fin = _final_of.get(gid)
        hw, src = _desk_forecast(gid, bool(fin))
        row = {
            "gid": gid, "d": r["d"], "dl": day_label(r["d"], _today),
            "t": r["t"], "a": r["a"], "h": r["h"],
            # AVCA and OUR rank only. VolleyTalk and Massey are other people's
            # and the public gate forbids them; the desk never carries them.
            "ar": r.get("ar") or "", "hr": r.get("hr") or "",
            "ao": _av.get(r["a"]) or "", "ho": _av.get(r["h"]) or "",
            "ap": _pr.get(r["a"]), "hp": _pr.get(r["h"]),
            "venue": r.get("venue"), "city": r.get("city"), "st": r.get("st"),
            "site": r.get("site"), "event": r.get("event"), "kind": r.get("kind"),
            "tv": r.get("tv"),
            "conflict": r.get("conflict") or [], "corrected": r.get("corrected") or [],
            # ⚠ THE MATCH HAS TO SAY IT DOES NOT COUNT. Without this the data is
            # right and the screen still misleads: Nebraska beats Florida and
            # its record reads 0-0 the next morning, which looks like a broken
            # site rather than a decision. The event name rides along because
            # "exhibition" alone invites the question this answers.
            "exh": (_exh_ledger.get(gid) or {}).get("event") if gid in _exh_ledger else None,
            "csrc": r.get("csrc"), "cverified": r.get("cverified"),
            "hw": hw, "fsrc": src,
            "at": _tourn.get(r["a"]), "ht": _tourn.get(r["h"]),
        }
        if fin:
            ts = fin.get("teams") or []
            home = next((t for t in ts if t.get("is_home")), None)
            away = next((t for t in ts if not t.get("is_home")), None)
            ls = [l for l in (fin.get("linescores") or [])
                  if l.get("home") is not None]
            row["final"] = {
                "hs": (home or {}).get("sets_won"),
                "as": (away or {}).get("sets_won"),
                "sets": [[l["visit"], l["home"]] for l in ls],
            }
        _desk.append(row)

    # ⚠ A STATED ORDERING, NOT A SCORE. The brief forbids inventing a composite
    # "watch score", and it is right to: a single number would hide which fact
    # moved it. This is a documented sort -- ranked-vs-ranked, then any ranked
    # side, then how close the forecast is -- and the page says so in those
    # words, so a reader can see the reason rather than a rating.
    def _desk_order(x):
        both = 1 if (x["ar"] and x["hr"]) else 0
        one = 1 if (x["ar"] or x["hr"]) else 0
        close = -abs((x["hw"] if x["hw"] is not None else 0.5) - 0.5)
        return (-both, -one, close, x["d"], x["t"] or "")

    _desk.sort(key=lambda x: (x["d"],) + _desk_order(x)[:3])
    _desk_json = json.dumps(_desk, separators=(",", ":"))

    # ---- WHAT CHANGED: completed matches, ranked ones first --------------
    # Ranks shown are OUR power rank AS OF NOW, not as of the match -- we do not
    # store a rank history per match, and implying we did would be a fabricated
    # provenance. The tooltip says so.
    _pr = dict((t["team"], t["rank26"]) for t in teams if t.get("rank26"))
    _chg = []
    for r in sorted(res, key=lambda x: -(x.get("epoch") or 0)):
        aw = (r.get("away_sets") or 0) > (r.get("home_sets") or 0)
        win, lose = (r["away"], r["home"]) if aw else (r["home"], r["away"])
        ws, ls = ((r["away_sets"], r["home_sets"]) if aw
                  else (r["home_sets"], r["away_sets"]))
        wr, lr = _pr.get(win), _pr.get(lose)
        if wr is None and lr is None:
            continue                      # neither side is one of the 348
        _chg.append({"win": win, "lose": lose, "ws": ws, "ls": ls,
                     "wr": wr, "lr": lr,
                     "both": bool(wr and lr and wr <= 25 and lr <= 25),
                     "epoch": r.get("epoch") or 0})
    _chg.sort(key=lambda x: (not x["both"], -x["epoch"]))
    _chg = _chg[:4]

    def _chgcard(c):
        def side(nm, rk, cls):
            badge = ('<i class="pwr" title="our POWER rank as of now, not as of '
                     'the match">%d</i> ' % rk) if rk else ""
            return ('<span class="%s">%s%s%s</span>'
                    % (cls, badge, logo_img(nm, logos), esc(nm)))
        return ('<div class="chgc%s">%s<b class="sc">%s&ndash;%s</b>%s</div>'
                % (" mk" if c["both"] else "",
                   side(c["win"], c["wr"], "w"), c["ws"], c["ls"],
                   side(c["lose"], c["lr"], "l")))

    _chg_html = "".join(_chgcard(c) for c in _chg)
    _chg_meta = ("%d ranked v ranked" % sum(1 for c in _chg if c["both"])
                 if any(c["both"] for c in _chg) else "latest results")

    _week_rows = [
        {"d": r["d"], "dl": day_label(r["d"], _today), "a": r["a"], "h": r["h"], "t": r["t"],
         "ar": r.get("ar") or "", "hr": r.get("hr") or "",
         "ao": _ourrank.get(r["a"]) or "", "ho": _ourrank.get(r["h"]) or "",
         "venue": r.get("venue"), "city": r.get("city"), "st": r.get("st"),
         "site": r.get("site"), "event": r.get("event"), "kind": r.get("kind"),
         "conflict": r.get("conflict") or [], "corrected": r.get("corrected") or [],
         "csrc": r.get("csrc"), "gid": str(r.get("gid") or "")}
        for r in sched if _today_s <= r["d"] <= _horizon]

    # ⚠ EVERY FIXTURE IS EMITTED, NOT THE FIRST 600. The copy above promises
    # that search reaches any of the rest, and search filters RENDERED rows --
    # so capping the emit made that promise impossible to keep. The initial
    # view is still 600 (a 1,763-row table is not a thing anyone reads), but
    # the rest are present and marked `beyond`, so a search finds them and a
    # button reveals them. Showing fewer than we have is a display choice;
    # not having them is a lie about what the page contains.
    SCHED_INITIAL = 600
    srows = []
    # the hand-maintained exhibition ledger, read ONCE for this table
    _sched_exh = dict([(k, (v or {}).get("event") or "exhibition")
                       for k, v in exhibitions().items()])
    for _i, r in enumerate(sched):
        pick, cls = _pick(r)
        # WHERE. A venue we do not have is stated as such -- never inferred
        # from the nominal home team, which is exactly how two AVCA First Serve
        # matches on a neutral floor in Milwaukee came to be labelled home games
        # (R5). "at" becomes "vs" when the floor is neutral, because "Texas at
        # Arizona St." is a false sentence about a match in Milwaukee.
        neutral = r.get("site") == "neutral"
        # ⚠ FAIL CLOSED. "at" is a claim that one team travelled to the other's
        # building. It is now printed ONLY for a site we have confirmed as
        # home/away; "vs" only for a confirmed neutral. Anything else -- the
        # feed carried no location, or its snapshots disagree -- renders a
        # neutral connector that asserts nothing. The old code printed "at" for
        # everything that was not explicitly neutral, which meant every
        # unconfirmed fixture in the season made a confident claim about where
        # it was played.
        confirmed_site = r.get("site") in ("home", "away", "neutral")
        conflicted = bool(r.get("conflict"))
        connector = ("vs" if neutral else "at") if (confirmed_site and not conflicted) else "v"
        where = ""
        if conflicted:
            # ⚠ NO CONFIDENT VENUE WHEN THE SOURCES DISAGREE.
            flds = ", ".join(sorted({c["field"] for c in r["conflict"]}))
            where = ('<span class="wconf" title="The scheduled %s differs '
                     'between snapshots of the official record, and none of '
                     'them carries a crawl time to prefer. Check the schools\u2019 '
                     'own schedules.">schedule conflict \u2014 verify</span>'
                     % esc(flds))
        elif r.get("venue"):
            city = ", ".join(x for x in (r.get("city"), r.get("st")) if x)
            where = ('<b>%s</b>%s' % (esc(r["venue"]),
                                      ('<span class="wc">%s</span>' % esc(city)) if city else ""))
            if r.get("corrected"):
                # ⚠ A CORRECTED FACT SAYS SO, AND LINKS ITS SOURCE.
                where += ('<a class="wsrc" href="%s" target="_blank" '
                          'rel="noopener noreferrer" title="This fixture is '
                          'corrected from the school\u2019s own schedule: %s">'
                          'school-confirmed</a>'
                          % (esc(r.get("csrc") or "#"),
                             esc(", ".join(r.get("corrected") or []))))
        else:
            where = '<span class="wu">venue not listed</span>'
        # ⚠ AN EVENT AND A MATCH TYPE ARE BOTH TRUE AND ARE SHOWN TOGETHER.
        # A named event used to REPLACE the type, so "Big Ten/SEC Challenge"
        # hid that it is also a non-conference match.
        _typ = ("conference" if r["kind"] == "conf" else "non-conf")
        _tcls = "cf" if r["kind"] == "conf" else "nc"
        if r.get("event"):
            badge = ('<span class="kind %s" title="%s match">%s</span>'
                     '<span class="kind ev" title="in-season tournament">%s</span>'
                     % (_tcls, _typ, _typ, esc(r["event"])))
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
        # ⚠ AN EXHIBITION HAS TO SAY SO HERE TOO. The Scoreboard tagged these
        # EXH and the Schedule did not, so one fixture had two answers on one
        # page -- and the answer the Schedule gave was the misleading one:
        # "non-conf" implies a match that counts, and Florida-Nebraska and
        # SMU-Penn St. count toward nobody's record. The badge is built from
        # the same hand-maintained ledger the rest of the page reads, so there
        # is one definition of "does not count" (R4).
        _ex = _sched_exh.get(str(r.get("gid") or ""))
        if _ex:
            badge = ('<span class="kind exh" title="%s &mdash; does not count '
                     'toward either record">exhibition</span>' % esc(_ex)) + badge
        srows.append(
            '<tr%s%s><td class="cd" data-d="%s">%s</td><td class="n">%s</td><td class="tm">%s%s%s</td>'
            '<td class="at">%s</td><td class="tm">%s%s%s</td>'
            '<td class="wh l">%s%s</td>'
            '<td class="n pick %s">%s</td></tr>'
            % ((' class="rkd both"' if (r["ar"] and r["hr"])
                else (' class="rkd"' if (r["ar"] or r["hr"]) else "")),
               (' data-beyond="1"' if _i >= SCHED_INITIAL else ""),
               # ONE DATE FORMAT ON THE PAGE. The ISO string stays in data-d
               # so any future sort or filter still has a sortable key -- the
               # reason the table kept ISO in the first place -- while the cell
               # a person reads says "Fri Aug 28" like every other date here.
               r["d"], day_label(r["d"]), r["t"] or "&mdash;",
               rank_badge("avca", r["ar"]),
               logo_img(r["a"], logos), esc(r["a"]),
               connector,
               rank_badge("avca", r["hr"]),
               logo_img(r["h"], logos), esc(r["h"]),
               badge, where,
               cls, pick))
    srows = "".join(srows)

    # ⚠ A BROADCAST LISTING IS FORWARD-LOOKING, AND THIS ONE OPENED WITH
    # HISTORY. The transcribed file is chronological from the start of the
    # season, so on 2026-08-27 the first four rows were Aug 21-24 -- already
    # played -- and tonight's listing was below them. The Schedule tab already
    # solved this ("fixtures from today forward").
    # ⚠ NOTHING IS DROPPED. Past rows are marked and collapsed behind a stated
    # count, the same way the schedule holds its later fixtures: showing fewer
    # than we have is a display choice, not having them is a lie about what the
    # page contains. A day that does not parse is ALWAYS shown -- the file is
    # hand-transcribed prose, and an unreadable date must not make a listing
    # disappear.
    _today_iso = datetime.date.today().isoformat()
    def _tv_iso(day):
        # "Fri, Aug 21" -> "2026-08-21"; None when it cannot be read
        m = re.search(r"([A-Z][a-z]{2})\w*\.?\s+(\d{1,2})", str(day or ""))
        if not m:
            return None
        try:
            mo = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                  "Sep", "Oct", "Nov", "Dec"].index(m.group(1)) + 1
        except ValueError:
            return None
        return "%d-%02d-%02d" % (SEASON, mo, int(m.group(2)))
    _tv_past = 0
    _tr = []
    for r in tvrows:
        _iso = _tv_iso(r["day"])
        _is_past = bool(_iso and _iso < _today_iso)
        if _is_past:
            _tv_past += 1
        _tr.append(
            '<tr%s><td class="cd">%s</td><td class="tm">%s</td>'
            '<td class="tvnet"><span class="netchip">%s</span></td>'
            '<td class="n">%s</td></tr>'
            % (' class="tvpast" hidden' if _is_past else "",
               esc(r["day"]), esc(r["m"]), esc(r["n"]), esc(r["t"])))
    trows = "".join(_tr)
    if _tv_past:
        trows = ('<tr class="tvearlier"><td colspan="4">'
                 '<button type="button" id="tvpastbtn">Show %d earlier '
                 'listing%s</button></td></tr>' % (_tv_past,
                                                   "" if _tv_past == 1 else "s")
                 ) + trows

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
                                    _teams_seen,
                                    esc(day_label(_last) if _last else "&mdash;")))
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
        .replace("{{ICON_CSS}}", ICONS.CSS) \
        .replace("{{ICON_FINAL}}", ICONS.icon("final")) \
        .replace("{{ICON_LIVE}}", ICONS.icon("live")) \
        .replace("{{ICON_NEUTRAL}}", ICONS.icon("neutral")) \
        .replace("{{ICON_TV}}", ICONS.icon("tv")) \
        .replace("{{ICON_ROAD}}", ICONS.icon("road")) \
        .replace("{{ICON_UNAVAIL}}", ICONS.icon("unavailable")) \
        .replace("{{TREND_CSS}}", TREND.CSS) \
        .replace("{{TREND_JSON}}", json.dumps(_trends)) \
        .replace("{{TREND_NOTE}}", _trend_note) \
        .replace("{{DIGBY_BRIEF}}", DIGBY_ART.digby_svg("briefing", 76)) \
        .replace("{{DIGBY_CLIP}}", "" if PUBLIC
                 else DIGBY_ART.digby_svg("clipboard", 76)) \
        .replace("{{DIGBY_WATCH}}", DIGBY_ART.digby_svg("watching", 76)) \
        .replace("{{DIGBY_CHEER}}", "" if PUBLIC
                 else DIGBY_ART.digby_svg("celebrate", 76)) \
        .replace("{{DIGBY_SVG}}", "" if PUBLIC else DIGBY_SVG) \
        .replace("{{DIGBY_COACH}}",
                 ('<img class="digby-coach" src="%s" alt="">' % DIGBY_COACH)
                 if (DIGBY_COACH and not PUBLIC) else "") \
        .replace("{{RULERS_JSON}}",
                 json.dumps(public_rulers(), separators=(",", ":"))) \
        .replace("{{INTEL_MEDIA_HOSTS_JSON}}",
                 "[]" if PUBLIC else json.dumps(list(INTEL_MEDIA_HOSTS),
                                                separators=(",", ":"))) \
        .replace("{{T25_ROWS}}", _t25["rows"]) \
        .replace("{{T25_ALSO}}", _t25["also"]) \
        .replace("{{T25_LEAD}}", _t25["lead"]) \
        .replace("{{T25_FOOT}}", _t25["foot"]) \
        .replace("{{T25_SEASON}}", _t25["season"]) \
        .replace("{{T25_MOVEHEAD}}", _t25["movehead"]) \
        .replace("{{RANK_BASIS}}", rank_basis) \
        .replace("{{AQ_MECH}}", aq_mech) \
        .replace("{{RANK_ROWS}}", "".join(rrows)) \
        .replace("{{LEDGER_JSON}}", json.dumps(ledger)) \
        .replace("{{SCORE_CARDS}}", "".join(cards) or
                 '<div class="empty">No completed matches yet.</div>') \
        .replace("{{SEED_ROWS}}", "".join(seeds)) \
        .replace("{{DESK_JSON}}", _desk_json) \
        .replace("{{CHANGED_ROWS}}", _chg_html) \
        .replace("{{CHANGED_META}}", esc(_chg_meta)) \
        .replace("{{CHANGED_HIDDEN}}", "" if _chg else "hidden") \
        .replace("{{SEASON_YEAR}}", str(SEASON)) \
        .replace("{{RESUME_ACTIVE_JS}}", "true" if _resume_active else "false") \
        .replace("{{WEEK_JSON}}", json.dumps(_week_rows, separators=(",", ":"))) \
        .replace("{{FIXTURES_JSON}}", json.dumps(
            {str(r["gid"]): {
                "gid": str(r["gid"]), "d": r["d"],
                "dl": day_label(r["d"], _today), "t": r["t"],
                "a": r["a"], "h": r["h"],
                "ar": r.get("ar") or "", "hr": r.get("hr") or "",
                "venue": r.get("venue"), "city": r.get("city"),
                "st": r.get("st"), "site": r.get("site"),
                "event": r.get("event"), "kind": r.get("kind"),
                "tv": r.get("tv"),
                "conflict": r.get("conflict") or [],
                "corrected": r.get("corrected") or [],
                "csrc": r.get("csrc"),
             } for r in sched if r.get("gid")},
            separators=(",", ":"))) \
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
        .replace("{{N_SHOWN}}", "{:,}".format(min(600, len(sched)))) \
        .replace("{{N_TV}}", str(len(tvrows))) \
        .replace("{{STANDINGS_JSON}}", json.dumps(stand, separators=(",", ":"))) \
        .replace("{{RESULTS_JSON}}", blob(
            [{"away": r["away"], "home": r["home"],
              "away_sets": r["away_sets"], "home_sets": r["home_sets"],
              "epoch": r.get("epoch")}
             for r in sorted(res_cnt, key=lambda x: x.get("epoch") or 0)])) \
        .replace("{{GAMEDAY_JSON}}",
                 json.dumps(gameday_readiness() or {}, separators=(",", ":"))) \
        .replace("{{MSTATE_JSON}}", __import__("match_state").js_table()) \
        .replace("{{CALENDAR_JSON}}",
                 json.dumps(calendar_tracks(), separators=(",", ":"))) \
        .replace("{{NONDI_JSON}}", json.dumps(
            sorted(set(
                nm for r in res for nm in (r["home"], r["away"])
                if _di_all and nm not in _di_all)),
            separators=(",", ":"))) \
        .replace("{{LOGOS_JSON}}", json.dumps(logos, separators=(",", ":"))) \
        .replace("{{COLORS_JSON}}", json.dumps(team_colors, separators=(",", ":"))) \
        .replace("{{BOXES_JSON}}", json.dumps(boxes, separators=(",", ":"))) \
        .replace("{{PLAYERS_JSON}}", json.dumps(plist, separators=(",", ":"))) \
        .replace("{{PRANK_JSON}}", json.dumps(
            player_rating_payload(), separators=(",", ":"))) \
        .replace("{{ROSTER_JSON}}", json.dumps(
            roster_index(), separators=(",", ":"))) \
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
        .replace("{{LAST}}", esc(day_label(first_played) if first_played else "not yet")) \
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
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
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
  /* ── THE FILM ROOM ────────────────────────────────────────────────────
     Named from the brief, so a value here can be checked against it rather
     than argued about. Court Navy is the ground; Chalk is the reading ink
     and the wash under a sheet you are meant to READ rather than scan.
     ⚠ RALLY BLUE IS A SURFACE COLOUR, NOT AN INK. #1F66D1 on Court Navy is
     about 3:1 -- fine as a fill or a 3px rule, not as body text. So it gets
     its own name and a separate lighter token for anything a reader has to
     read. Repointing one token to serve both is how a page ends up with
     text nobody can see (R4). */
  --court:#07172B; --chalk:#F5F1E8; --rally:#1F66D1;
  --gold:#D99A29; --coral:#E55E4F; --slate:#8390A1;

  --page:#07172B; --card:#0C1F36; --alt:#112741;
  --ink:#F5F1E8; --ink2:#B7C2D2; --ink3:#8390A1;
  --line:#1B3050; --line2:#2C4A72;
  --navy:#5BA8F5; --blue:#7FC1FF; --amber:#D99A29; --amber-bg:#33280A;
  --sand:#12283F;
  /* the chalk sheet: a reading surface, not another card */
  --sheet:rgba(245,241,232,.035); --sheet2:rgba(245,241,232,.055);
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
  /* THREE ROLES, NAMED BY JOB. Display is for scores, ranks and short
     labels -- condensed type is fast in three words and slow in three
     sentences. Editorial is for anything anyone actually reads. Utility is
     for stamps, records and set lines, where the digits must line up. */
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --sans:"Source Sans 3",-apple-system,BlinkMacSystemFont,"SF Pro Text",
         "Segoe UI",Roboto,sans-serif;
  --disp:"Barlow Condensed","Oswald","Avenir Next Condensed",
         "HelveticaNeue-CondensedBold","Arial Narrow",var(--sans);
}
/* COURTSIGNAL-TOKENS-BEGIN */
/* ══ COURT SIGNAL ═════════════════════════════════════════════════════════
   The brief names five colours. Four of them ALREADY EXIST on this page under
   older names, and repointing an existing token to a new meaning is exactly
   the failure R4 is written about -- so this is an ALIAS LAYER, not a
   replacement. Nothing above changes value; these names simply say, in the
   brief's own vocabulary, which of the existing values plays which part. Only
   one colour here is genuinely new.

     midnight ink  = --court  #07172B   the ground
     court blue    = --rally  #1F66D1   structure, fills, rules
     optic white   = --chalk  #F5F1E8   reading ink
     signal gold   = --gold   #D99A29   the live/active signal
     serve cyan    = NEW      #4CD4E4   serve and set-state only

   ⚠ SERVE CYAN IS RATIONED ON PURPOSE. A bright cyan used generally on a dark
   ground is the "terminal / sci-fi" look the brief explicitly rules out. It is
   allowed in exactly three places -- the serve indicator, the set-cell rule on
   a set in progress, and the focus ring -- and nowhere else. That restriction
   is a guard, not a preference: test_court_signal.py counts its uses. */
:root{
  --cs-ink:var(--court); --cs-blue:var(--rally); --cs-white:var(--chalk);
  --cs-gold:var(--gold); --cs-cyan:#4CD4E4;
  /* the cyan lifted for anything a reader must actually READ (the fill value
     is a 3px rule colour, not an ink -- the same distinction --rally already
     carries above, and for the same reason) */
  --cs-cyan-ink:#8FE7F2;
  /* semantic pair, reused rather than redefined */
  --cs-pos:var(--good); --cs-neg:var(--bad);
  /* structural greys of the tape itself */
  --cs-cell:#0E2338; --cs-edge:#1B3050; --cs-edge2:#2C4A72;
}
/* THE COURT-LINE TEXTURE. One reusable inline-SVG ground: the net (dashed, in
   the middle), the two attack lines 3m either side of it, and the service-zone
   ticks at the ends. It is 3.5% white on navy -- you are meant to feel the
   geometry, not read it -- sits behind content, and never takes a pointer. */
.cs-court{position:relative;isolation:isolate}
.cs-court::before{content:"";position:absolute;inset:0;pointer-events:none;
  z-index:0;opacity:.55;
  /* ⚠ THE FIRST TILE DREW ITS OWN BORDER, so the repeat printed a visible
     LATTICE across every surface -- a grid of boxes, which is a spreadsheet,
     not a court. Measured on the team header: tile edges at x=670, 1030, 1290,
     nothing to do with the sport. The outline is gone; what is left is the
     markings themselves.
     ⚠ AND THE NET CAME OUT OF THE TILE TOO. A dashed vertical every 240px put
     four "nets" behind the Rally Tape, competing with the ONE net the tape
     draws as the border of its set cells -- the single line the whole diagram
     depends on. The texture is now attack lines and service ticks; the net is
     drawn once, by the component that means it. */
  background-image:url("data:image/svg+xml;utf8,\
<svg xmlns='http://www.w3.org/2000/svg' width='300' height='150' viewBox='0 0 300 150'>\
<g fill='none' stroke='%23F5F1E8' stroke-opacity='.07'>\
<line x1='0' y1='37.5' x2='300' y2='37.5' stroke-width='1'/>\
<line x1='0' y1='112.5' x2='300' y2='112.5' stroke-width='1'/>\
<line x1='50' y1='0' x2='50' y2='13' stroke-width='1'/>\
<line x1='50' y1='137' x2='50' y2='150' stroke-width='1'/>\
<line x1='150' y1='0' x2='150' y2='13' stroke-width='1'/>\
<line x1='150' y1='137' x2='150' y2='150' stroke-width='1'/>\
<line x1='250' y1='0' x2='250' y2='13' stroke-width='1'/>\
<line x1='250' y1='137' x2='250' y2='150' stroke-width='1'/>\
</g></svg>");
  background-size:300px 150px}
.cs-court>*{position:relative;z-index:1}
/* COURTSIGNAL-TOKENS-END */
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
/* ── TABULAR NUMERALS: TESTED, AND NOT NEEDED HERE ───────────────────────
   Do not re-add this. It is standard advice for a data product and it is a
   NO-OP on this page, which was established by measuring GLYPH WIDTHS rather
   than by reading a CSS property.

   Every numeric column already renders in ui-monospace: "11111" and "77777"
   both measure 40.64px in td.pw, td.rk and td.n, so there is no jitter to fix.
   The only column whose digits differ in width is td.tm -- the TEAM NAME
   column, set in Oswald (29.52 vs 32.84px), where a tabular figure is neither
   wanted nor supported by the face.

   ⚠ HOW THIS ALMOST SHIPPED. The first check counted tables whose computed
   `font-variant-numeric` contained "tabular" and reported 0 of 40 -- a real
   property reading, and a useless one. The property says what was ASKED FOR;
   the widths say whether it changed anything. Same lesson as the phantom nav
   underline: measure the pixels, not the declaration.  */
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

header{color:var(--ink);padding:16px 24px 0;position:relative;
  background:
    radial-gradient(120% 180% at 12% -40%, rgba(91,168,245,.30), transparent 60%),
    radial-gradient(90% 160% at 92% -30%, rgba(255,199,44,.20), transparent 62%),
    linear-gradient(180deg,var(--chrome2) 0%,var(--chrome) 78%,#08101F 100%)}
.mast{max-width:1280px;margin:0 auto;display:flex;align-items:flex-end;
  justify-content:space-between;gap:20px;flex-wrap:wrap}
/* ⚠ THE WORDMARK IS A LOCKUP, NOT A HEADING THAT HAPPENS TO BE BIG. A rule
   under the season line and a tighter, heavier condensed face make it read as
   a masthead; the previous 40px/.92 sat at the same weight as a section
   title, which is why the page opened like a dashboard. */
h1{margin:0;font:700 52px/.86 var(--disp);letter-spacing:-.005em;
  color:var(--chalk);text-transform:uppercase}
h1 em{font-style:normal;color:var(--gold)}
.season{font:600 10px/1 var(--mono);color:var(--slate);letter-spacing:.36em;
  text-transform:uppercase;margin-bottom:10px;padding-bottom:9px;
  border-bottom:1px solid var(--line);display:inline-block}
.meta{font:11.5px/1.7 var(--mono);color:var(--slate);text-align:right}
.meta b{color:var(--chalk);font-weight:600}
/* The net: white mesh under a taut yellow tape. It is the one thing in the
   sport every viewer can draw from memory, so it carries the masthead. */
.net{max-width:1280px;margin:12px auto 0;height:11px;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.30) 0 1px,transparent 1px 6px),
             repeating-linear-gradient(0deg,rgba(255,255,255,.30) 0 1px,transparent 1px 6px);
  border-top:3px solid var(--amber);
  box-shadow:0 -1px 22px -2px rgba(255,199,44,.55),0 6px 30px -14px rgba(255,199,44,.35)}
/* COURTSIGNAL-TAPE-CSS-BEGIN */
/* ══ THE RALLY TAPE ═══════════════════════════════════════════════════════
   The site's one bold move, and it is bold because of its GEOMETRY rather
   than because of an effect. Volleyball is the only major sport whose score
   is a ROW OF BOXES with a net standing in the middle of it, and that row is
   a diagram every viewer of the sport can already read. So the tape is that
   diagram: two crested sides, the net, five set cells.

   ⚠ EVERY CELL IN IT IS A FACT OR IT IS EMPTY. A set that has not been played
   renders a court dot, never a 0 -- '' is not zero, the same distinction
   match_state.py had to make. An upcoming match shows no score at all. A
   quiet day shows the NEXT REAL FIXTURE, and if there is not one it says so.
   There is no state of this component that invents activity (R5).

   ⚠ AND IT IS NOT A TICKER. A looping marquee is what a broadcast band is
   usually copied AS, and it would be ambient motion on a page that may be
   looking at nothing. The tape is still. */
.cs-tape{max-width:1280px;margin:12px auto 0;
  border:1px solid var(--cs-edge);border-top:0;
  background:linear-gradient(180deg,#0B1D33 0%,#091829 100%);
  display:grid;grid-template-columns:150px minmax(0,340px) auto minmax(0,1fr);
  align-items:stretch}
/* ⚠ THE NET ENDED UP AT THE FAR RIGHT EDGE. The teams column was the 1fr, so
   it absorbed every spare pixel and pushed the set cells -- and the dashed net
   line that is their left border -- against the frame, with 600px of empty
   court between the names and the score. The net has to stand in the MIDDLE of
   the scoreline or the diagram is not the diagram. Fixed by giving the names a
   bounded track and putting the 1fr in a fourth, empty column, which is now
   simply court showing through. */
.cs-pad{grid-row:1;grid-column:4}
.cs-tape.cs-court::before{opacity:.62}

/* --- the state column: what this band IS ------------------------------- */
.cs-st{grid-row:1;display:flex;flex-direction:column;justify-content:center;
  gap:5px;padding:11px 14px;border-right:1px solid var(--cs-edge);
  background:rgba(7,23,43,.5)}
.cs-stl{font:700 12px/1 var(--disp);letter-spacing:.2em;text-transform:uppercase;
  color:var(--cs-white);display:flex;align-items:center;gap:7px}
.cs-live .cs-stl{color:var(--cs-gold)}
.cs-when{font:500 10.5px/1.35 var(--mono);color:var(--slate);
  letter-spacing:.06em;text-transform:uppercase}
/* the live dot is the ONLY looping motion on the page, and it loops only
   while something is genuinely live */
.cs-dot{width:8px;height:8px;border-radius:50%;background:var(--cs-gold);
  flex:0 0 auto;box-shadow:0 0 0 0 rgba(217,154,41,.6)}
.cs-live .cs-dot{animation:cs-pulse 1.9s ease-out infinite}
@keyframes cs-pulse{
  0%{box-shadow:0 0 0 0 rgba(217,154,41,.55)}
  70%{box-shadow:0 0 0 7px rgba(217,154,41,0)}
  100%{box-shadow:0 0 0 0 rgba(217,154,41,0)}}
.cs-quiet .cs-dot{background:var(--slate);box-shadow:none;animation:none}

/* --- the two sides ------------------------------------------------------ */
.cs-teams{grid-row:1;display:flex;flex-direction:column;justify-content:center;
  padding:7px 16px;min-width:0;gap:1px}
/* ⚠ THE RANK TRACK IS max-content, NOT A FIXED WIDTH. It held a bare "#15" at
   30px; a labelled "AVCA#15" needs 39, so the number ran out of its own cell
   and under the crest -- measured, not guessed: scrollWidth 39 against
   clientWidth 26 on the phone. Adding a label to a number changes how much
   room the number needs, and every fixed track that held the old one has to be
   revisited. There are four of them. */
.cs-side{display:grid;
  grid-template-columns:max-content 26px minmax(0,1fr) 34px;
  align-items:center;gap:9px;padding:4px 0;min-width:0}
.cs-trk{font:700 12px/1 var(--mono);color:var(--cs-gold);text-align:right;
  font-variant-numeric:tabular-nums}
.cs-side img{width:24px;height:24px;object-fit:contain}
/* ⚠ THE CREST SLOT IS ALWAYS EMITTED. The same four-column-grid-with-three-
   children defect the ribbon paid for: logo() returns '' for a team we hold no
   crest for, every cell shifts one column left, and the name lands in the 26px
   crest track. This hits every non-Division-I opponent. */
.cs-nologo{width:24px;height:24px;border:1px solid var(--cs-edge2);
  border-radius:2px;opacity:.5}
.cs-nm{font:600 20px/1.12 var(--disp);letter-spacing:.005em;color:var(--ink2);
  text-transform:uppercase;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;min-width:0}
.cs-won .cs-nm{color:var(--cs-white)}
.cs-sets{font:700 26px/1 var(--disp);color:var(--ink3);text-align:right;
  font-variant-numeric:tabular-nums}
.cs-won .cs-sets{color:var(--cs-white)}
.cs-side.cs-serve .cs-trk::after{content:"";display:inline-block;width:5px;
  height:5px;border-radius:50%;background:var(--cs-cyan);margin-left:5px;
  vertical-align:.14em}

/* --- the set cells, with the net standing in front of them -------------- */
.cs-cells{grid-row:1;display:flex;align-items:stretch;
  border-left:2px dashed rgba(245,241,232,.32);
  padding:9px 12px 9px 14px;gap:5px}
.cs-cell{width:38px;display:flex;flex-direction:column;justify-content:center;
  gap:3px;background:var(--cs-cell);border:1px solid var(--cs-edge);
  border-radius:2px;padding:6px 0}
.cs-cell i{font:600 15px/1 var(--mono);font-style:normal;text-align:center;
  color:var(--ink2);font-variant-numeric:tabular-nums}
.cs-cell i.cs-cw{color:var(--cs-white);font-weight:700}
/* an unplayed set is a court dot, never a zero */
.cs-cell.cs-empty{background:rgba(245,241,232,.02);border-style:dashed;
  border-color:rgba(245,241,232,.2)}
.cs-cell.cs-empty i{color:var(--ink3);opacity:.8}
.cs-cell.cs-now{border-color:var(--cs-cyan);
  box-shadow:inset 0 -2px 0 -0px var(--cs-cyan)}
.cs-setno{font:600 9px/1 var(--mono);letter-spacing:.1em;color:var(--ink3);
  text-align:center;text-transform:uppercase}

/* --- one factual context line ------------------------------------------ */
.cs-ctx{grid-column:1/-1;grid-row:2;border-top:1px solid var(--cs-edge);
  padding:8px 16px;font:12.5px/1.45 var(--sans);color:var(--ink2);
  background:rgba(7,23,43,.42);
  display:flex;gap:9px;align-items:baseline;flex-wrap:wrap}
.cs-ctx b{color:var(--cs-white);font-weight:600}
.cs-ctx .cs-sep{color:var(--cs-edge2)}
.cs-ctx a{color:var(--navy);text-decoration:none;border-bottom:1px solid transparent}
.cs-ctx a:hover{border-bottom-color:var(--navy)}
.cs-unk{color:var(--ink3);font-style:italic}

/* --- the quiet band ----------------------------------------------------- */
.cs-quiet .cs-nm{color:var(--ink2)}
.cs-quiet .cs-sets{display:none}
.cs-quiet .cs-side{grid-template-columns:max-content 26px minmax(0,1fr)}
/* with no set cells, the quiet marquee is two columns, not four */
.cs-tape.cs-quiet{grid-template-columns:150px minmax(0,1fr)}
/* the ranks label and any other stated-provenance aside in the context line */
.cs-ctx .cs-unk{font-style:normal;font:11px/1.5 var(--mono);
  letter-spacing:.04em}
.cs-at{font:600 10px/1 var(--mono);letter-spacing:.18em;color:var(--ink3);
  text-transform:uppercase;padding:1px 0 1px 74px}
/* nothing at all on the card: still the tape's geometry, honestly empty */
.cs-none{grid-column:1/-1;grid-row:1;padding:16px;
  font:14px/1.5 var(--sans);color:var(--ink2);display:flex;gap:10px;
  align-items:center}
.cs-none b{color:var(--cs-white)}
/* Digby as a SIGNAL GUIDE, at two moments only: the tape with nothing to show,
   and the Intel wire with nothing to report. Both are honest-empty states --
   the place a page is most tempted to invent something -- so a small friendly
   marker there is a cue, not decoration. He is 26px and he does not appear on
   any surface carrying data. */
.cs-guide{flex:0 0 auto;display:inline-flex}
.cs-guide img{width:26px;height:26px}

/* --- ONE orchestrated entrance, and only one --------------------------- */
.cs-tape{animation:cs-in .5s cubic-bezier(.22,1,.36,1) both}
.cs-tape .cs-cell{animation:cs-cellin .34s cubic-bezier(.22,1,.36,1) both;
  animation-delay:calc(120ms + var(--cs-i,0) * 55ms)}
@keyframes cs-in{from{opacity:0;transform:translateY(-7px)}
                 to{opacity:1;transform:none}}
@keyframes cs-cellin{from{opacity:0;transform:translateY(5px)}
                     to{opacity:1;transform:none}}
/* ⚠ A QUIET DAY DOES NOT ANIMATE. The entrance is a response to a match
   existing; playing it over an empty schedule is decoration pretending to be
   state, which is the thing this whole page is built not to do. */
.cs-quiet,.cs-quiet .cs-cell{animation:none}
@media (prefers-reduced-motion:reduce){
  .cs-tape,.cs-tape .cs-cell{animation:none}
  .cs-live .cs-dot{animation:none;box-shadow:0 0 0 3px rgba(217,154,41,.28)}
}
.cs-tape a:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}

/* --- the control-room status strip -------------------------------------- */
/* ⚠ VERTICAL BUDGET IS REAL. The status strip plus the tape pushed the nav to
   y=321 -- a third of a laptop viewport spent before the first control. The
   strip is a single tight line and the tape's own padding came down to match;
   the identity survives, the nav stays above the fold. */
.cs-status{max-width:1280px;margin:0 auto;display:flex;flex-wrap:wrap;
  gap:0 20px;align-items:center;padding:7px 0 0;
  font:11px/1.5 var(--mono);color:var(--slate);letter-spacing:.05em}
.cs-status span{display:flex;align-items:center;gap:6px}
.cs-status b{color:var(--ink2);font-weight:600}
.cs-status .cs-fresh{color:var(--cs-white)}
.cs-status .cs-stale{color:var(--cs-gold)}

@media (max-width:860px){
  .cs-tape{grid-template-columns:minmax(0,1fr) auto}
  .cs-pad{display:none}
  /* ⚠ THE BASE RULE'S justify-content:center SURVIVES THE DIRECTION FLIP. In
     a column it centres vertically, which is right; the moment the narrow
     block makes it a ROW the same declaration centres it HORIZONTALLY, and
     "NEXT SERVE  FRI AUG 28" floated in the middle of the phone band while
     every other line was flush left. Flipping direction means re-stating
     alignment. */
  .cs-st{grid-row:1;grid-column:1/-1;border-right:0;
    border-bottom:1px solid var(--cs-edge);flex-direction:row;
    justify-content:flex-start;align-items:center;gap:11px;padding:9px 13px}
  .cs-teams{grid-row:2;grid-column:1}
  .cs-cells{grid-row:2;grid-column:2}
  .cs-ctx{grid-row:3}
}
/* ⚠ THE PHONE KEEPS THE TAPE. The brief's instruction, and it is the right
   one: the identity band is the reason the page does not look like a list of
   tables, so collapsing it behind a hamburger on the device it is most often
   read on would delete the identity exactly where it is needed. It gets
   smaller, the set cells scroll sideways in their own box, and that is all. */
@media (max-width:560px){
  .cs-tape{margin-top:12px;grid-template-columns:minmax(0,1fr)}
  .cs-pad{display:none}
  .cs-teams{grid-row:2;grid-column:1;padding:8px 12px}
  .cs-cells{grid-row:3;grid-column:1;border-left:0;
    border-top:2px dashed rgba(245,241,232,.3);
    padding:9px 12px;overflow-x:auto;-webkit-overflow-scrolling:touch}
  .cs-ctx{grid-row:4;padding:8px 12px;font-size:12px}
  .cs-side{grid-template-columns:max-content 22px minmax(0,1fr) 28px;gap:7px}
  .cs-quiet .cs-side{grid-template-columns:max-content 22px minmax(0,1fr)}
  .cs-side img,.cs-nologo{width:20px;height:20px}
  .cs-nm{font-size:17px}
  .cs-sets{font-size:21px}
  .cs-cell{width:34px}
  .cs-at{padding-left:55px}
  .cs-status{gap:0 14px;font-size:10px;padding-top:7px}
}

/* COURTSIGNAL-VIEWS-CSS-BEGIN */
/* ══ COURT SIGNAL ON THE PRIORITY SCREENS ═════════════════════════════════
   The tape is the one bold move. Everything below is the opposite discipline:
   the same court geometry and the same five colours, applied as STRUCTURE --
   a rule, an edge, a texture -- so the screens read as one system without any
   of them competing with the band at the top.

   ⚠ NOTHING HERE CHANGES A NUMBER, A ROUTE OR A PIECE OF MARKUP. It is edges,
   grounds and type. The one markup change in this phase is the team header
   gaining its own programme colour, which comes from COLORS -- measured from
   each school's own logo -- and is absent rather than invented when we do not
   hold one. */

/* ── TEAM PAGE: a programme identity panel ─────────────────────────────── */
#teamcard>.thead.cs-prog{padding:16px 18px 15px;
  border-left:4px solid var(--tc,var(--cs-blue));
  border-bottom:2px solid var(--cs-edge2);
  background:linear-gradient(90deg,
    color-mix(in oklab,var(--tc,var(--cs-blue)) 13%,transparent),
    transparent 46%)}
#teamcard>.thead.cs-prog::before{opacity:.5}

/* ── RANKINGS / TOP 25: a strong editorial index ───────────────────────── */
/* ⚠ NUMBERED MARKERS ARE USUALLY DECORATION AND HERE THEY ARE THE DATA. A
   ranking IS an ordered index, so setting the rank as an index -- large,
   right-aligned, tabular, in the display face -- encodes something true. The
   same treatment on a list that merely happens to have rows would be the
   generic move. The rule sizes already shipped; this adds the court ground
   under the table head so the board reads as a board. */
.t25 thead th{background:rgba(31,102,209,.09);
  border-bottom:2px solid var(--cs-edge2);
  font:700 10px/1 var(--disp);letter-spacing:.15em;text-transform:uppercase}
.t25 tbody tr td:first-child::before{width:4px}

/* ⚠ THE PRIVATE SURFACES' COURT SIGNAL RULES ARE NOT HERE, AND THAT IS THE
   POINT. My first version styled all three of them in this block -- which
   sits OUTSIDE every fence, so their selectors shipped in the published
   stylesheet. No values leaked, but three guards failed and were right to:
   this project has already shipped a payload behind removed columns once, and
   "the markup is gone" is not the same claim as "it was not published". Each
   treatment now lives inside the fence for the surface it styles, so the strip
   carries it away with the rest of the feature, and there is one place per
   feature rather than two.
   ⚠ AND THE REWRITE OF THIS COMMENT IS ITSELF THE SECOND LESSON: naming those
   features here, in an unfenced block, tripped the public gate on the marker
   words alone. A comment that documents a removed section both describes
   something that is not there and fails the check. Say "three private
   surfaces"; the fences say which. */

/* MATCHMOMENT-CSS-BEGIN */
/* ══ THE MATCH MOMENT ═════════════════════════════════════════════════════
   A result poster built entirely from data we already hold and have already
   reconciled: crests, the two schools' own colours, the ruler-labelled ranks,
   the score or the start time, the per-set strip once sets exist, and where it
   was played.

   ⚠ IT IS DELIBERATELY NOT PHOTOGRAPHIC, and that is the honest design rather
   than a limitation being dressed up. This project does not draw likenesses of
   named players, and a "generated action shot" beside real headshots would be
   the R5 failure in picture form -- a synthesised thing standing where a
   measurement belongs. What it CAN show, it shows exactly: every value on it
   is checkable against the match.

   It shares the Rally Tape's vocabulary on purpose -- court lines, condensed
   display type, the set cells -- because they are the same sport rendered at
   two sizes. 16:9 so it can occupy the slot a photograph would. */
.mm{margin:0;position:relative;display:grid;
  grid-template-rows:auto 1fr auto auto;
  aspect-ratio:16/9;min-height:190px;overflow:hidden;
  border:1px solid var(--cs-edge2);
  background:linear-gradient(180deg,#0B1D33 0%,#07172B 100%)}
/* the two schools' colours as edges, never as a full-bleed theme */
.mm::after{content:"";position:absolute;left:0;right:0;top:0;height:4px;
  background:linear-gradient(90deg,var(--ta,var(--cs-blue)) 0 50%,
                                    var(--tb,var(--cs-blue)) 50% 100%);
  z-index:2}
.mm.cs-court::before{opacity:.85}
.mm-top{display:flex;align-items:center;gap:10px;padding:12px 14px 0;
  z-index:1}
.mm-state{font:700 11px/1 var(--disp);letter-spacing:.2em;text-transform:uppercase;
  color:var(--cs-white);display:flex;align-items:center;gap:6px}
.mm.is-live .mm-state{color:var(--cs-gold)}
.mm-when{font:500 10.5px/1 var(--mono);color:var(--slate);letter-spacing:.06em;
  text-transform:uppercase;margin-left:auto;text-align:right}
.mm-body{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;
  gap:12px;padding:6px 14px;min-width:0;z-index:1}
.mm-side{display:flex;flex-direction:column;gap:5px;min-width:0}
.mm-side.b{align-items:flex-end;text-align:right}
.mm-side img{width:38px;height:38px;object-fit:contain}
.mm-nologo{width:38px;height:38px;border:1px solid var(--cs-edge2);
  border-radius:2px;opacity:.45}
.mm-nm{font:700 21px/1.05 var(--disp);letter-spacing:.005em;color:var(--ink2);
  text-transform:uppercase;overflow-wrap:anywhere}
.mm-side.won .mm-nm{color:var(--cs-white)}
.mm-rk{font:600 10px/1 var(--mono)}
.mm-sc{font:700 40px/1 var(--disp);color:var(--cs-white);
  font-variant-numeric:tabular-nums;white-space:nowrap}
.mm-sc i{font-style:normal;color:var(--ink3);margin:0 3px}
.mm-time{font:700 21px/1.1 var(--disp);color:var(--cs-white);text-align:center;
  white-space:nowrap}
.mm-time span{display:block;font:500 10px/1.4 var(--mono);color:var(--slate);
  letter-spacing:.1em;text-transform:uppercase}
.mm-sets{display:flex;gap:4px;padding:0 14px 6px;flex-wrap:wrap;z-index:1}
.mm-set{font:600 11px/1 var(--mono);color:var(--ink2);
  border:1px solid var(--cs-edge);background:var(--cs-cell);
  padding:4px 6px;border-radius:2px;font-variant-numeric:tabular-nums}
.mm-foot{border-top:1px solid var(--cs-edge);padding:8px 14px;
  font:11.5px/1.4 var(--sans);color:var(--ink2);
  background:rgba(7,23,43,.5);display:flex;gap:8px;flex-wrap:wrap;z-index:1}
.mm-foot .mm-sep{color:var(--cs-edge2)}
.mm-unk{color:var(--ink3);font-style:italic}
.mm-site{font:600 9.5px/1 var(--disp);letter-spacing:.14em;text-transform:uppercase;
  color:var(--cs-gold);border:1px solid var(--cs-edge2);padding:3px 5px;
  border-radius:2px}
a.mmlink{display:block;text-decoration:none}
a.mmlink:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
@media (max-width:560px){
  .mm{min-height:0;aspect-ratio:4/3}
  .mm-nm{font-size:17px}.mm-sc{font-size:32px}.mm-time{font-size:17px}
  .mm-side img,.mm-nologo{width:30px;height:30px}
  .mm-body{gap:8px;padding:4px 11px}
  .mm-top,.mm-foot,.mm-sets{padding-left:11px;padding-right:11px}
  .mm-foot{font-size:11px}
}
/* the featured pairing: poster beside the score header, one match */
.deskfeat{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);
  gap:16px;align-items:start;margin:14px 0 4px}
.deskfeat .deskfeatside{min-width:0}
.deskfeat .deskfeatside>*{margin-top:0}
@media (max-width:860px){.deskfeat{grid-template-columns:minmax(0,1fr)}}
/* MATCHMOMENT-CSS-END */
/* COURTSIGNAL-VIEWS-CSS-END */
/* ── THE RAIL: the compact shape, for every screen that is not Today ──── */
/* ⚠ ONE LINE. The marquee is 129px; this is ~34px and carries the same three
   facts -- what is on, when, and a way in. A deep page gets context without
   surrendering its first third to it. */
/* ── YOUR NEXT WATCHES ───────────────────────────────────────────────── */
.tdnow{font:700 13px/1 var(--disp);letter-spacing:.16em;text-transform:uppercase;
  color:var(--slate)}
.tdlivenow{display:inline-flex;align-items:center;gap:7px;margin-left:14px;
  font:700 12px/1 var(--disp);letter-spacing:.15em;text-transform:uppercase;
  color:var(--cs-gold)}
.wgrid{display:grid;gap:14px;
  grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.wcard{display:flex;flex-direction:column;gap:9px;min-width:0;padding:15px;
  text-decoration:none;border:1px solid var(--cs-edge2);
  border-left:3px solid var(--cs-gold);
  background:linear-gradient(180deg,#0B1D33,#091829)}
.wcard.islive{border-left-color:var(--live)}
.wcard:hover{border-color:var(--navy);border-left-color:var(--cs-white)}
.wcard:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
.wtop{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.wwhen{display:flex;align-items:center;gap:6px;
  font:600 10.5px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
  color:var(--slate)}
/* ⚠ THE CHANNEL IS THE POINT. It is the first thing he asked for and the feed
   carries none of it, so a fixture with a joined listing shows the network
   loudly and one without says so rather than implying it is not on. */
.wnet{margin-left:auto;font:700 11px/1 var(--disp);letter-spacing:.11em;
  text-transform:uppercase;color:var(--ink-on-accent);background:var(--cs-gold);
  padding:5px 8px;border-radius:2px;white-space:nowrap}
/* ⚠ AN UNKNOWN BROADCAST IS NOT A DATA POINT AND MUST NOT LOOK LIKE ONE. This
   carried a dashed border in the exact slot where FOX, BTN and ESPN2 appear,
   so "TV NOT LISTED" read as a featured fact -- in the one place Cody is
   scanning for a channel. It stays on the card, because silence would imply
   "not televised" when what we mean is "we do not know", but it is now plain
   muted type rather than a badge competing with the real ones. */
.wnet.none{background:transparent;color:var(--ink3);border:0;padding:5px 0;
  font:400 10.5px/1 var(--sans);letter-spacing:.02em;text-transform:none;
  opacity:.65}
.wteams{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  font:700 20px/1.12 var(--disp);text-transform:uppercase;color:var(--cs-white)}
.wteams i{font-style:normal;font:500 11px/1 var(--mono);color:var(--ink3);
  text-transform:lowercase}
.wmeta{font:12px/1.45 var(--sans);color:var(--ink2)}
.wacts{display:flex;align-items:center;gap:10px;margin-top:2px}
.wgo{font:600 11.5px/1 var(--sans);color:var(--navy)}
.wcard:hover .wgo{color:var(--cs-white)}
.wofficial{font:500 10px/1 var(--mono);color:var(--ink3);letter-spacing:.06em}
/* secondary, and it looks it */
.mbsecondary{margin-top:8px;opacity:.92}
.mbsecondary .mbrow{padding-top:7px;padding-bottom:7px}
/* a person's name in prose reads as a person */
.pname{color:var(--cs-white);text-decoration:none;font-weight:600;
  border-bottom:1px solid color-mix(in oklab,var(--cs-gold) 55%,transparent)}
.pname:hover{color:var(--cs-gold)}
.pname:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
/* ── PLAYER CARD: transfer history and video ─────────────────────────── */
.partsbox .partsrow{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
.partsbox .pv{font:700 26px/1 var(--disp)}
.partsbox .over .pv{color:#5fd39a}
.partsbox .under .pv{color:#e88}
.partsbox .pl{font-size:12px;color:var(--ink3)}
.rprow{display:flex;align-items:center;gap:9px;margin:5px 0;font-size:12.5px}
.rplab{width:78px;color:var(--ink3)}
.rpbar{flex:1;max-width:200px;height:7px;border-radius:4px;
  background:var(--cs-edge2);overflow:hidden}
/* ⚠ NOT SERVE CYAN. That colour is reserved for serve, set-in-progress
   and focus, and a returning-production bar is none of those -- it is a
   magnitude. Optic white carries magnitude without claiming a meaning
   the palette has already assigned. */
.rpbar i{display:block;height:100%;background:rgba(245,241,232,.62)}
.rppct{width:38px;font-weight:700}
.rotgrid{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;max-width:420px}
.rotcell{border:1px solid var(--cs-edge2);border-radius:7px;padding:6px 4px;
  text-align:center;display:flex;flex-direction:column;gap:1px}
.rotcell .rotlab{font:700 10px/1 var(--disp);color:var(--ink3)}
.rotcell .rotv{font:700 15px/1 var(--disp)}
.rotcell.best{border-color:#3a7;background:rgba(60,180,120,.10)}
.rotcell.worst{border-color:#a55;background:rgba(190,80,80,.10)}
.ratingbox{border:1px solid var(--cs-edge2);border-radius:10px;
  padding:11px 12px;margin-bottom:12px;background:rgba(255,255,255,.02)}
.rchips{display:flex;flex-wrap:wrap;gap:8px}
.rchip{display:flex;flex-direction:column;gap:1px;border:1px solid var(--cs-edge2);
  border-radius:8px;padding:6px 10px;font:700 17px/1 var(--disp)}
.rchip b{font:700 9.5px/1 var(--disp);letter-spacing:.08em;color:var(--ink3)}
.rchip i{font-style:normal;font:400 10.5px/1.2 var(--sans);color:var(--ink3)}
.rchip.pw{border-color:var(--gold,#c9a227)}
.rchip.off{opacity:.6}
.rtags{display:flex;flex-wrap:wrap;gap:6px;align-items:baseline;margin-top:8px}
.rtag{font-size:11px;padding:2px 7px;border-radius:4px;
  border:1px solid var(--cs-edge2);color:var(--ink3)}
.rfoot{margin-top:8px;line-height:1.4}
.starcols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:560px){.starcols{grid-template-columns:1fr}}
.starcol{border:1px solid var(--cs-edge2);border-radius:9px;padding:9px 10px}
.stt{display:flex;align-items:center;gap:6px;font:700 12px/1 var(--disp);
  letter-spacing:.05em;text-transform:uppercase;margin-bottom:7px}
.starrow{display:grid;grid-template-columns:34px 1fr;gap:6px;
  text-decoration:none;color:inherit;padding:5px 0;border-top:1px solid var(--cs-edge2)}
.starrow:first-of-type{border-top:0}
.starrow:hover .sn{text-decoration:underline}
.starrow .sp{font:700 9.5px/1.6 var(--disp);color:var(--ink3)}
.starrow .sn{font-size:13.5px;color:var(--cs-white)}
.starrow .sd{grid-column:2;font-size:11px;color:var(--ink3)}
.tdstars{display:flex;flex-wrap:wrap;gap:6px;align-items:baseline;margin-top:4px}
.tdstars .pk{font-size:11.5px;color:var(--ink3);white-space:nowrap}
.tdstars .pk i{font-style:normal;font:700 9px/1 var(--disp);letter-spacing:.06em;
  margin-right:4px;opacity:.75}
.tdstars .pkv{font-size:10px;opacity:.5}
/* ⚠ 16px IS NOT A STYLE CHOICE ON A PHONE, IT IS THE ZOOM THRESHOLD. iOS
   Safari zooms the whole page in when you focus a form control whose
   font-size is under 16px, and it does NOT zoom back out afterwards -- so the
   page stays scaled and every subsequent scroll feels wrong. Cody reported
   exactly that from his iPhone ("text boxes are kinda wonky", "scrolling"),
   and all 43 controls on the page measured between 11.5px and 14px.
   ⚠ THE ALTERNATIVE FIX IS WORSE. Adding maximum-scale=1 to the viewport meta
   also stops the zoom, by disabling pinch-zoom entirely -- which takes the
   page away from anyone who needs to magnify it. Sizing the control is the fix
   that costs nobody anything.
   ⚠ PHONE WIDTHS ONLY: desktop typography is untouched. */
/* ⚠ !important, DELIBERATELY, AND THIS IS THE ONE PLACE IT IS RIGHT. The plain
   rule lost to about forty more-specific ones (.ctl input, #pq) and to every
   `font:` SHORTHAND on the page, which resets font-size as a side effect --
   84 controls still measured under 16px with it in place. This is not a
   preference being enforced over a designer's; it is a browser threshold that
   has to hold or the behaviour returns. */
/* ⚠ A READABILITY FLOOR ON A PHONE, MEASURED NOT GUESSED. Cody reads this hub
   on an iPhone and said the formatting was wonky. Audited at 386px: the
   Rankings view alone rendered 381 text nodes under 10.5px. Most were the
   movement column's en-dashes, which are fine as glyphs -- but the rest were
   TABLE HEADERS at 9.5-10px ("Our system", "Coaches poll", "Our outlook",
   "Form"), which is squinting distance on a handset.
   ⚠ VERIFIED IT COSTS NOTHING: with the floor applied at 386px the page still
   measured scrollWidth 386 against clientWidth 386 -- no new overflow, because
   these tables already scroll inside their own box. Desktop is untouched. */
@media (max-width:560px){
  th{font-size:11px !important}
  .pl6,.nvd{font-size:11px !important}
  /* ⚠ THE WORST OFFENDER WAS A PHRASE, NOT A TOKEN. A short uppercase tracked
     tag like "OH" or "non-conf" reads fine at 9px; "Before first serve" set at
     8px does not, and that is the difference the floor has to respect. Short
     badges are nudged, phrase-length labels are lifted properly. */
  .mrow .mtg,.mbhd .mbpriv{font-size:9.5px !important}
  .gd-step i,.fr-facts>i,.fr-prevnums i{font-size:10px !important}
  /* the label above each figure in the team header's fact strip */
  .vx-facts i{font-size:9.5px !important}
}
@media (max-width:560px){
  input,select,textarea{font-size:16px !important}
  /* keep the control from growing now that its text is larger */
  .ctl input,.ctl select{padding:9px 10px}
}
.notyet{margin-top:14px}
.nyhd{font:700 12px/1 var(--disp);letter-spacing:.06em;text-transform:uppercase;
  padding:10px 12px;border-bottom:1px solid var(--cs-edge2);
  display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.nyrow{cursor:pointer}
.nyrow:hover td{background:rgba(255,255,255,.04)}
.nyrow td{font-size:13px}
.exhban{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;
  border:1px solid var(--cs-edge2);border-left:4px solid var(--gold,#c9a227);
  border-radius:8px;padding:9px 12px;margin-bottom:12px;font-size:12.5px}
.exhban b{font:700 11px/1 var(--disp);letter-spacing:.08em;text-transform:uppercase;
  color:var(--gold,#c9a227)}
.exhtag{display:inline-block;flex:0 0 auto;align-self:center;width:auto;
  font:700 9px/1.5 var(--disp);letter-spacing:.07em;padding:2px 6px;
  border-radius:3px;border:1px solid var(--gold,#c9a227);
  color:var(--gold,#c9a227);vertical-align:middle}
/* ── TEAM DOSSIER ─────────────────────────────────────────────────────── */
.tdnav{display:flex;gap:2px;flex-wrap:wrap;margin:16px 0 0;
  border-bottom:1px solid var(--cs-edge2);padding-bottom:0}
.tdnav button{appearance:none;background:none;border:0;cursor:pointer;
  font:700 12px/1 var(--disp);letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink3);padding:11px 14px;border-bottom:2px solid transparent;
  margin-bottom:-1px;white-space:nowrap}
.tdnav button:hover{color:var(--ink2)}
.tdnav button.on{color:var(--chalk);border-bottom-color:var(--cs-gold)}
.tdnav button:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:-3px}
.tdpanel{padding-top:16px}
.tdpanel[hidden]{display:none}
.tdlab{display:block;font:700 10px/1 var(--disp);letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink3);margin-bottom:8px}
/* the next match: the single decision this page exists to serve */
.tdnext{border:1px solid var(--cs-edge2);border-left:3px solid var(--cs-gold);
  border-radius:10px;padding:12px 14px;margin-bottom:14px}
.tdnextrow{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;
  text-decoration:none;color:inherit}
.tdnextrow:hover b{text-decoration:underline}
.tdvs{display:flex;align-items:center;gap:7px;font:700 22px/1.1 var(--disp);
  color:var(--chalk)}
.tdvs b{font-weight:700}
.tdwhen{font:700 13px/1 var(--disp);letter-spacing:.05em;color:var(--ink2)}
.tdtv{font:700 11px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink-on-accent);background:var(--cs-gold);padding:4px 7px;
  border-radius:2px}
.tdwhere{margin:7px 0 0;font-size:12.5px;color:var(--ink3)}
.tdnotv{margin:4px 0 0;font-size:11.5px}
.tdnext.empty p{margin:0}
/* players to know */
.tdknow{margin-bottom:14px}
.tdpgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:10px}
.tdpcard{display:grid;grid-template-columns:44px 1fr;gap:3px 11px;
  align-items:center;border:1px solid var(--cs-edge2);border-radius:10px;
  padding:10px 12px;text-decoration:none;color:inherit}
.tdpcard:hover{background:rgba(255,255,255,.03)}
.tdpcard:hover .tdpn{text-decoration:underline}
.tdface{grid-row:1/4;width:44px;height:44px;border-radius:50%;
  object-fit:cover;background:var(--cs-edge2);display:flex;
  align-items:center;justify-content:center;font:700 15px/1 var(--disp);
  color:var(--ink2)}
.tdpn{font:700 15px/1.15 var(--disp);color:var(--chalk)}
.tdpm{font-size:11.5px;color:var(--ink3)}
.tdpick{font-style:normal;color:var(--good);font-weight:700}
.tdppct{font:700 13px/1 var(--disp);color:var(--ink2)}
.tdppct i{font-style:normal;font:400 10px/1 var(--sans);color:var(--ink3);
  margin-left:5px}
.tdpl{grid-column:2;font-size:11.5px;color:var(--ink3)}
@media (max-width:560px){
  /* ⚠ ONE COLUMN, NOTHING SIDEWAYS. The dossier's whole point on a phone is a
     simple vertical flow; a grid that keeps two columns at 390px produces the
     squeeze this redesign exists to remove. */
  .tdpgrid{grid-template-columns:1fr}
  .tdnav{gap:0}
  .tdnav button{padding:10px 11px;font-size:11px}
  .tdvs{font-size:19px}
}
.prkctl{flex-wrap:wrap;gap:10px}
.segbar{display:inline-flex;border:1px solid var(--cs-edge2);border-radius:8px;
  overflow:hidden}
.segbar button{font:600 11px/1 var(--disp);letter-spacing:.06em;
  text-transform:uppercase;background:none;border:0;color:var(--ink3);
  padding:8px 11px;cursor:pointer;white-space:nowrap}
.segbar button+button{border-left:1px solid var(--cs-edge2)}
.segbar button.on{background:var(--cs-edge2);color:var(--cs-white)}
.prksupport{margin:10px 0 4px}
.prkcav{font-size:12.5px;line-height:1.45;padding:9px 11px;border-radius:8px;
  border:1px solid var(--cs-edge2);background:rgba(255,255,255,.02)}
.prkbadge{font:700 10px/1 var(--disp);letter-spacing:.08em;padding:3px 6px;
  border-radius:4px;margin-right:6px;background:var(--cs-edge2);
  color:var(--cs-white)}
.sup-good .prkbadge{background:#1f5c3a;color:#d9f2e3}
.sup-fair .prkbadge{background:#5c4a1f;color:#f2e8d0}
.sup-weak .prkbadge{background:#5c2a2a;color:#f2d9d9}
#prktable td{vertical-align:top}
.prkrow{cursor:pointer}
.prkrow:hover td{background:rgba(255,255,255,.04)}
.prkrow:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:-2px}
.prknum{font:700 15px/1 var(--disp);color:var(--cs-white)}
.prkval{font:700 15px/1 var(--disp);white-space:nowrap}
.prkconf{font-size:11.5px;white-space:nowrap}
.prkdrv{max-width:340px}
.prkd{display:inline-block;font-size:11px;padding:2px 6px;margin:1px 4px 1px 0;
  border-radius:4px;border:1px solid var(--cs-edge2);white-space:nowrap}
.prkd.neg{opacity:.6}
.prkpass{margin-top:4px;display:flex;flex-wrap:wrap;gap:6px;align-items:baseline}
.prkp{font-size:11px;color:var(--ink3)}
.prkrolet.alt{opacity:.75}
.prkpos,.prkrolet{font:700 9.5px/1 var(--disp);letter-spacing:.06em;
  text-transform:uppercase;padding:2px 5px;border-radius:3px;
  background:var(--cs-edge2);color:var(--ink3);margin-left:4px}
.prkh{font-family:var(--disp);font-size:19px;margin:22px 0 4px}
.starteam{margin:12px 0;padding:11px 12px;border:1px solid var(--cs-edge2);
  border-radius:10px}
.sthead{font:700 12px/1 var(--disp);letter-spacing:.07em;text-transform:uppercase;
  color:var(--cs-white);margin-bottom:9px}
.stgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
  gap:8px}
.star{border:1px solid var(--cs-edge2);border-radius:8px;padding:7px 9px;
  display:flex;flex-direction:column;gap:2px}
.star.vac{opacity:.5}
.spos{font:700 10px/1 var(--disp);letter-spacing:.08em;color:var(--ink3)}
.sname{font-size:13.5px;color:var(--cs-white)}
.steam{font-size:11px;color:var(--ink3);display:flex;align-items:center;gap:4px}
.spw{font:700 12px/1 var(--disp)}
.sprof{margin-top:9px;font-size:12px;color:var(--ink3)}
.hmrow{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin:4px 0;
  font-size:12px}
.hmn{white-space:nowrap}
.pname-brief{font:inherit;background:none;border:0;padding:0;cursor:pointer}
.namepop{position:absolute;z-index:120;width:min(330px,calc(100vw - 20px));
  background:var(--cs-ink2,#111c2e);border:1px solid var(--cs-edge2);
  border-radius:10px;box-shadow:0 14px 40px rgba(0,0,0,.55);padding:12px 13px}
.namepop .nphead{display:flex;gap:10px;align-items:flex-start}
.namepop .npname{font-family:var(--disp);font-size:17px;line-height:1.15;
  color:var(--cs-white)}
.namepop .sub{font-size:11.5px;color:var(--ink3);margin-top:2px}
.namepop .npface{width:48px;height:48px;border-radius:50%;object-fit:cover;
  flex:0 0 auto}
.namepop .npx{margin-left:auto;background:none;border:0;color:var(--ink3);
  font-size:19px;line-height:1;cursor:pointer;padding:0 2px}
.namepop .npx:hover{color:var(--cs-white)}
.namepop .npbody{margin-top:9px;display:flex;flex-direction:column;gap:6px}
.namepop .nprow{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;
  font-size:12.5px}
.namepop .npfoot{margin-top:2px;line-height:1.35}
.pxfer,.pvid{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;
  margin-top:9px;font:12.5px/1.5 var(--sans);color:var(--ink2)}
.pxlab{font:700 9.5px/1 var(--disp);letter-spacing:.14em;text-transform:uppercase;
  color:var(--slate);flex:0 0 auto}
.pxfer a{color:var(--cs-white);text-decoration:none;font-weight:600;
  border-bottom:1px solid var(--cs-edge2)}
.pxfer a:hover{border-bottom-color:var(--cs-gold)}
.pxstat{color:var(--slate)}
.pvid a{color:var(--navy);text-decoration:none;border:1px solid var(--cs-edge2);
  border-radius:2px;padding:4px 8px;font:600 11px/1 var(--sans)}
.pvid a:hover{color:var(--cs-white);border-color:var(--navy)}
.pvid a:focus-visible,.pxfer a:focus-visible{outline:2px solid var(--cs-cyan);
  outline-offset:2px}
.pvid .munk{font-size:11px}
.tdrule{margin:26px 0 0;padding-top:14px;border-top:1px solid var(--cs-edge);
  font:12px/1.6 var(--sans);color:var(--slate)}
.tdrule a{color:var(--navy);text-decoration:none}
.tdrule a:hover{color:var(--cs-white)}
@media (max-width:560px){
  .wgrid{grid-template-columns:minmax(0,1fr)}
  .wteams{font-size:17px}
  .wnet{margin-left:0}
}
/* ── TODAY ────────────────────────────────────────────────────────────── */
/* ── SCOREBOARD ───────────────────────────────────────────────────────── */
/* the season ledger, deliberately behind a name */
.sbfull{margin-top:30px;border-top:1px solid var(--cs-edge);padding-top:8px}
.sbfull>summary{cursor:pointer;list-style:none;padding:11px 0;
  font:700 11px/1 var(--disp);letter-spacing:.17em;text-transform:uppercase;
  color:var(--navy)}
.sbfull>summary::-webkit-details-marker{display:none}
.sbfull>summary::before{content:"\25B8";display:inline-block;margin-right:8px}
.sbfull[open]>summary::before{content:"\25BE"}
.sbfull>summary:hover{color:var(--cs-white)}
.sbfull>summary:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
.sbbar{display:flex;flex-direction:column;gap:12px;margin:0 0 22px;
  padding-bottom:16px;border-bottom:2px solid var(--cs-edge2)}
.sbdate{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sbnav{appearance:none;width:36px;height:36px;flex:0 0 auto;cursor:pointer;
  border:1px solid var(--cs-edge2);background:var(--cs-cell);color:var(--cs-white);
  font:600 15px/1 var(--sans);border-radius:2px}
.sbnav:hover{border-color:var(--navy);color:var(--cs-gold)}
.sbnav:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
.sbday{display:flex;flex-direction:column;gap:2px;min-width:150px}
.sbday b{font:700 21px/1 var(--disp);letter-spacing:.01em;color:var(--cs-white);
  text-transform:uppercase}
.sbday span{font:500 10.5px/1 var(--mono);color:var(--slate);letter-spacing:.07em}
.sbtoday{appearance:none;cursor:pointer;border:1px solid var(--cs-edge2);
  background:transparent;color:var(--navy);border-radius:2px;padding:9px 12px;
  font:600 11px/1 var(--disp);letter-spacing:.13em;text-transform:uppercase}
.sbtoday:disabled{opacity:.4;cursor:default}
.sbtoday:not(:disabled):hover{color:var(--cs-white);border-color:var(--navy)}
.sbtoday:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
.sbpick{display:flex;align-items:center;gap:7px;margin-left:auto;
  font:500 10.5px/1 var(--mono);color:var(--slate);letter-spacing:.07em;
  text-transform:uppercase}
.sbpick input{background:var(--cs-cell);border:1px solid var(--cs-edge2);
  color:var(--ink);border-radius:2px;padding:7px 8px;font:12px/1 var(--mono)}
.sbfilters{flex-wrap:wrap}
/* ⚠ SAME SPECIFICITY, LATER SOURCE WINS. `.tdmarq` sets three columns and is
   defined after this block, so `.sbtop` alone lost the tie and four cards
   wrapped 3+1. Qualified so it wins on class count rather than on position,
   which is the thing that changes when blocks move. */
.tdmarq.sbtop{grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:1100px){.tdmarq.sbtop{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){
  .tdmarq.sbtop{grid-template-columns:minmax(0,1fr)}
  .sbpick{margin-left:0;width:100%}
  .sbday{min-width:0;flex:1 1 auto}
  .sbday b{font-size:18px}
  /* ⚠ TOUCH TARGETS. Measured in a real 384px viewport: the Today control came
     out 31px tall, which is tappable but mean. Every control on this bar is
     given a 40px floor on a phone -- the filters too, which were sized for a
     mouse. */
  .sbtoday,.sbnav,.sbfilters .segb{min-height:40px}
  .sbpick input{min-height:40px}
}
.tdquiet{font:14.5px/1.6 var(--sans);color:var(--ink2);margin:0 0 20px;
  padding-bottom:16px;border-bottom:1px solid var(--cs-edge)}
.tdquiet b{color:var(--cs-white)}
.tdblock{margin:0 0 26px}
.tdblock h3{display:flex;align-items:baseline;gap:11px;margin:0 0 12px;
  font:700 11px/1 var(--disp);letter-spacing:.19em;text-transform:uppercase;
  color:var(--cs-white);padding-bottom:9px;
  border-bottom:1px solid var(--cs-edge)}
.tdblock h3 span{font:500 11px/1 var(--mono);letter-spacing:.05em;
  text-transform:none;color:var(--slate);margin-left:auto}
/* ⚠ THREE AT MOST, and they are cards because each carries its own reasons --
   a row cannot hold them legibly. Everything else on this page stays a row. */
.tdmarq{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.tdcard{display:flex;flex-direction:column;gap:8px;min-width:0;
  padding:14px;text-decoration:none;
  border:1px solid var(--cs-edge2);border-left:3px solid var(--cs-gold);
  background:linear-gradient(180deg,#0B1D33,#091829)}
.tdcard:hover{border-left-color:var(--cs-white)}
.tdcard:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
.tdwhen{font:500 10px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase;
  color:var(--slate)}
.tdteams{display:flex;align-items:center;gap:7px;flex-wrap:wrap;
  font:700 18px/1.15 var(--disp);text-transform:uppercase;color:var(--cs-white)}
.tdteams i{font-style:normal;font:500 11px/1 var(--mono);color:var(--ink3);
  text-transform:lowercase}
.tdwhere{font:12px/1.45 var(--sans);color:var(--ink2)}
.tdwhy{display:flex;flex-wrap:wrap;gap:5px;margin-top:2px}
.tdtag{font:600 9.5px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  padding:4px 6px;border-radius:2px;border:1px solid var(--cs-edge2);
  color:var(--ink2);white-space:nowrap}
.tdtag.rv{color:var(--cs-gold);border-color:color-mix(in oklab,var(--cs-gold) 45%,transparent)}
.tdtag.mb{color:var(--vx-ballot,#b8a6ff);border-color:color-mix(in oklab,#b8a6ff 40%,transparent)}
.tdtag.lv{color:var(--live);border-color:color-mix(in oklab,var(--live) 45%,transparent)}
/* ⚠ NOT CYAN. Serve cyan is rationed to three roles -- serve, set in
   progress, focus -- and a tag colour is none of them. The guard caught this
   the moment it shipped, which is what the rationing rule is for. */
.tdtag.dg{color:var(--blue);border-color:color-mix(in oklab,#7FC1FF 40%,transparent)}
.tdlist{border-top:1px solid var(--cs-edge)}
.tdprompt{display:flex;gap:10px;flex-wrap:wrap;padding-top:6px}
.tdprompt a{font:600 12px/1 var(--sans);color:var(--navy);text-decoration:none;
  border:1px solid var(--cs-edge2);border-radius:2px;padding:9px 12px}
.tdprompt a:hover{color:var(--cs-white);border-color:var(--navy)}
.tdprompt a:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
@media (max-width:900px){.tdmarq{grid-template-columns:minmax(0,1fr)}}
.cs-rail{max-width:1280px;margin:10px auto 0;display:flex;align-items:center;
  gap:14px;flex-wrap:wrap;padding:8px 14px;
  border:1px solid var(--cs-edge);border-top:0;
  background:linear-gradient(180deg,#0B1D33 0%,#091829 100%);
  font:13px/1.35 var(--sans)}
.cs-rlab{display:flex;align-items:center;gap:7px;flex:0 0 auto;
  font:700 10px/1 var(--disp);letter-spacing:.2em;text-transform:uppercase;
  color:var(--slate)}
.cs-rail.cs-live .cs-rlab{color:var(--cs-gold)}
.cs-rmatch{display:flex;align-items:center;gap:7px;min-width:0;
  color:var(--cs-white);text-decoration:none;
  font:600 15px/1.2 var(--disp);text-transform:uppercase;letter-spacing:.01em}
.cs-rmatch:hover{color:var(--cs-gold)}
.cs-rmatch:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:3px}
.cs-rv{color:var(--ink3);font:500 11px/1 var(--mono);text-transform:lowercase}
.cs-rwhen{font:500 11px/1 var(--mono);color:var(--slate);letter-spacing:.05em;
  text-transform:uppercase;flex:0 0 auto}
.cs-rmore{margin-left:auto;flex:0 0 auto;color:var(--navy);text-decoration:none;
  font:600 11px/1 var(--sans)}
.cs-rmore:hover{color:var(--cs-white)}
.cs-rmore:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
@media (max-width:560px){
  .cs-rail{gap:8px 10px;padding:7px 11px;font-size:12px}
  .cs-rmatch{font-size:13.5px}
  .cs-rmore{margin-left:0}
}
/* COURTSIGNAL-TAPE-CSS-END */
/* the Scores route compresses the shared hero: identity in one line,
   the tape kept (it is the broadcast state), the counters hidden */
body[data-view=scores] .mast{padding-top:10px;padding-bottom:2px}
body[data-view=scores] .mast h1{font-size:30px}
body[data-view=scores] .mast .meta{display:none}
body[data-view=scores] .season{display:none}
body[data-view=scores] #v-scores .vh{display:none}
nav{position:sticky;top:0;z-index:6;
  background:linear-gradient(180deg,rgba(12,23,45,.88),rgba(8,14,28,.92));
  backdrop-filter:saturate(1.6) blur(14px);
  border-bottom:1px solid transparent;
  border-image:linear-gradient(90deg,transparent,rgba(120,180,255,.5) 18%,
    rgba(255,199,44,.55) 52%,rgba(120,180,255,.5) 84%,transparent) 1}
/* ⚠ THE LIT SLOT IS GONE. A filled, glowing tab is the generic dashboard
   move and it made twelve tabs shout equally. The active item is now marked by
   the gold rule alone, and RANK is carried by type size instead. */
nav .inner{max-width:1280px;margin:0 auto;display:flex;gap:0;flex-wrap:wrap;
  padding:0 8px;align-items:center}
nav button{appearance:none;border:0;background:transparent;color:var(--slate);
  font:600 12px/1 var(--disp);letter-spacing:.12em;padding:15px 13px;cursor:pointer;
  border-bottom:3px solid transparent;text-transform:uppercase;
  transition:color .16s ease}
/* the four that answer the brief's questions read a size larger */
nav button.pri{font-size:15px;letter-spacing:.07em;color:var(--ink2);padding:15px 15px}
nav .navdiv{width:1px;height:17px;background:var(--line2);margin:0 12px;
  flex:0 0 auto}
nav button:hover{color:var(--ink)}
nav button[aria-selected=true]{color:var(--ink)}
nav .inner{position:relative}
nav .inner::after{content:"";position:absolute;bottom:0;left:0;height:3px;
  width:var(--barw,0px);transform:translateX(var(--barx,0px));background:var(--amber);
  transition:transform .26s cubic-bezier(.4,0,.2,1),width .26s cubic-bezier(.4,0,.2,1);
  pointer-events:none}
@media (prefers-reduced-motion:reduce){nav .inner::after{transition:none}}
/* ⚠ THE FOCUS RING WAS THE SAME GOLD AS THE SELECTED UNDERLINE, which is the
   whole of the "double active state". Click Rankings, then open a team: the
   route is right, Teams carries the gold underline -- and Rankings still wears
   a gold box, in the identical colour the page uses to mean "you are here".
   Two golds, two claims, one of them false.
   Selection is GOLD and it is an underline. Focus is SERVE CYAN and it is a
   ring. Different colour, different shape, different job. */
nav button:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:-3px}
#moremenu button:focus-visible,.morebtn:focus-visible{
  outline:2px solid var(--cs-cyan);outline-offset:-2px}
/* the routed region, when focus is moved to it -- visible only to a keyboard
   user, because :focus-visible does not match a programmatic focus that
   followed a mouse click */
main section:focus{outline:none}
main section:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:4px}

main{max-width:1280px;margin:0 auto;padding:22px 16px 70px}
section[hidden]{display:none}
.lead{color:var(--ink2);font-size:14px;max-width:74ch;margin:0 0 16px}
.lead b{color:var(--ink)}
.rkstamp{color:var(--ink3);font-size:12.5px}
.rkstamp b{color:var(--ink2)}

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
  border:1px solid transparent;border-radius:4px;
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
  border-radius:4px;
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
/* OUR RANKING, WHERE IT DISAGREES. Deliberately quiet -- the AVCA number is the
   official one and keeps the prominent slot; this is the second opinion, and it
   should read as a footnote rather than compete with the matchup. */
.ourrk{font:600 11px/1.3 var(--mono);color:var(--ink2);letter-spacing:.02em;
  margin-top:6px;padding-top:6px;border-top:1px dotted var(--line)}
/* THE POLL COLUMN. Green where we are higher on a team than the coaches are,
   red where we are lower -- the same good/bad reading the rest of the page
   uses. The gap is deliberately smaller and quieter than the poll rank itself:
   the rank is the fact, the gap is the commentary. */
.t25 td.poll b{font:700 14px/1 var(--disp);color:var(--ink)}
/* ══ MOBILE: A PURPOSE-BUILT LIST, NOT A CLIPPED TABLE ═══════════════════
   MEASURED BEFORE WRITING ANY OF THIS: the page had 19 mobile rules and NOT
   ONE of them touched the rankings table or the nav. So at 390px a reader met
   a thirteen-column desktop table cut off at the edge with no cue that it
   scrolled, under a primary navigation that wrapped onto three rows before the
   content started. That is not a table that needs tuning; it is a layout that
   was never designed for the width.

   ⚠ VERIFIED BY LIFTING THIS BLOCK AND ASSERTING ON THE RESULT (R6).
   resize_window reports success and does NOT change the rendering viewport --
   window.innerWidth stays ~1512 and this media query never matches -- which
   once cost five review cycles on four fixes that were never tested.  */
@media (max-width:560px){
  /* NAV: one scrolling row. Wrapping to three rows pushes every page's content
     below the fold before it has said anything. */
  /* ⚠ NO HORIZONTAL TAB STRIP ON A PHONE. Twelve tabs had to scroll sideways,
     which hid destinations behind a gesture with no affordance. Five plus More
     wrap onto two short rows and every destination is visible at once. */
  nav .inner{flex-wrap:wrap;overflow-x:visible;scrollbar-width:none;
    -webkit-overflow-scrolling:touch;padding:0 6px;justify-content:center}
  nav .inner::-webkit-scrollbar{display:none}
  nav button{flex:0 0 auto;white-space:nowrap}
  /* ⚠ THE WRAP IS DELIBERATE (no sideways gesture); the SHAPE of it was not.
     At 390px the five primaries filled row one and MORE sat alone at the left
     of row two beside a field of nothing -- Cody's screenshot. Centred and a
     step tighter, the same six wrap as two balanced rows. */
  nav button.pri{font-size:13px;padding:12px 7px}
  /* four primaries on a phone; the ballot rides in More (see the menu) */
  nav button.pri[data-v=ballot]{display:none}
  nav button{font-size:11px;padding:12px 6px}
  nav .morebtn{padding:12px 6px}

  /* SCOREBOARD CONTROLS, phone shape (Cody's screenshots, 2026-08-28):
     -- the six filters wrapped 5+1 with UPCOMING orphaned and the count
        floating mid-control. A 3-per-row grid wraps 6 as two full rows (the
        public build's five as 3+2), and the count gets its own line.
     -- the date bar and lead ate half the first screen before a score. */
  .seg.sbfilters{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
  .seg.sbfilters .segb{width:100%}
  .sbfilters .count{grid-column:1/-1;text-align:right;padding-top:2px}
  .sbbar{gap:8px;margin-bottom:14px;padding-bottom:10px}
  #v-scores .lead{font-size:12.5px;line-height:1.5;margin-bottom:10px}
  .tdmarq.sbtop .tdcard{padding:10px 12px;gap:5px}

  /* bottom clearance so a fixed floating control never covers the last row
     at scroll-end; harmless padding on a build that has no such control.
     (Do not name the control here: this comment SHIPS, and the public gate
     aborts on the name -- which is exactly what it is for.) */
  main{padding-bottom:72px}

  /* RANKINGS + TOP 25 become a two-line row per team.
     Line 1: rank, crest, team, movement.
     Line 2: the four numbers worth carrying -- POWER, RESUME, record, AVCA.
     Everything else stays in the DOM for search and for the desktop view; it
     is hidden here rather than removed, so nothing is lost and no second
     renderer can drift from the first. */
  .rk3 tr.grp,
  .rk3 thead th.c-ref:not(.c-avca),.rk3 tbody td.c-ref:not(.c-avca),
  .rk3 thead th:nth-child(3),.rk3 tbody td.cf,
  .rk3 thead th:nth-last-child(-n+2),.rk3 tbody td:nth-last-child(-n+2){display:none}
  .rk3,.rk3 tbody,.rk3 thead,.rk3 tr{display:block;width:100%}
  .rk3 thead{display:none}
  /* ⚠ EXPLICIT COLUMNS, NOT STACKED CELLS NUDGED WITH margin-left. The first
     version put POWER, R\00c9SUM\00c9 and AVCA in ONE grid area and pushed them
     apart with fixed left margins -- which is a guess about how wide a number
     is, and it was wrong: "85.4" printed straight through the rank digit. Give
     each cell a real column and the browser does the arithmetic. */
  .rk3 tbody tr.row{display:grid;
    grid-template-columns:32px auto auto 1fr;
    align-items:center;gap:3px 12px;padding:9px 11px 10px;
    border-bottom:1px solid var(--line2)}
  .rk3 tbody tr.row td{border:0;padding:0;background:none}
  /* ⚠ width:48px FROM THE DESKTOP RULE SURVIVES INTO THE GRID. A grid TRACK
     does not clamp a cell that sets its own width, so the 48px rank box ran
     16px into the team name's column and the two overlapped. Found by
     measuring the rects, not by reading the CSS -- the computed padding was
     already 0, which made it look handled. */
  .rk3 tbody td.rk{grid-column:1;grid-row:1;width:auto;min-width:0;
    font:700 17px/1 var(--disp)}
  .rk3 tbody td.tm{grid-column:2 / -1;grid-row:1;font-size:15px;min-width:0;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .rk3 tbody td.pw{grid-column:2;grid-row:2;justify-self:start}
  .rk3 tbody td.rs{grid-column:3;grid-row:2;justify-self:start}
  .rk3 tbody td.c-avca{grid-column:4;grid-row:2;justify-self:start;
    opacity:1;color:var(--ink2)}
  .rk3 tbody tr.det{display:none}
  /* ⚠ THE GRADIENT BAR IS A COLUMN DEVICE AND THERE IS NO COLUMN HERE. On
     desktop td.hx::before draws a bar whose WIDTH encodes the value, which
     works because the eye compares it down a column of identical cells. In a
     card list each row stands alone, so the bar has nothing to be read
     against -- it just prints a green block behind the number and the whole
     figure reads as a smudge. Drop the bar, keep the colour on the digits. */
  .rk3 tbody td.hx::before,.t25 tbody td.hx::before{content:none}
  .rk3 tbody td.pw b{color:#31D07E}

  /* The header row is gone on mobile, so each number carries its own label.
     ⚠ position:static IS LOAD-BEARING. These labels re-use ::before, the SAME
     pseudo-element td.hx::before already declared as position:absolute for the
     gradient bar. Setting content:none above removed the bar but NOT the
     positioning, so every label was absolutely positioned on top of its own
     value -- "POWER" printed through "85.4". A pseudo-element is one element:
     re-purposing it inherits whatever the earlier rule said about it. */
  .rk3 tbody td.pw::before,.rk3 tbody td.rs::before,.rk3 tbody td.c-avca::before,
  .t25 tbody td.pw::before,.t25 tbody td.poll::before{
    position:static;display:inline;width:auto;height:auto;
    top:auto;right:auto;bottom:auto;left:auto;background:none;border:0;
    animation:none;font:700 9px/1 var(--sans);letter-spacing:.1em;
    margin-right:4px;vertical-align:baseline}
  .rk3 tbody td.pw::before{content:"POWER ";color:#31D07E;opacity:.9}
  .rk3 tbody td.rs::before{content:"R\00c9SUM\00c9 ";color:#F2B441;opacity:.9}
  .rk3 tbody td.c-avca::before{content:"AVCA ";color:var(--ink3,var(--ink2));opacity:.8}
  /* the numbers sit left in their own cells, not right-aligned as in a table */
  .rk3 tbody td.pw,.rk3 tbody td.rs,.rk3 tbody td.c-avca,
  .t25 tbody td.pw,.t25 tbody td.poll{text-align:left;width:auto}

  /* TOP 25 -- same idea, different columns. It carries a record and a form
     guide, which are the two things a poll reader looks at after the rank, so
     those survive and conference / net-per-set / season-weight do not. */
  .t25 thead{display:none}
  .t25,.t25 tbody,.t25 tr{display:block;width:100%}
  .t25 tbody tr.row{display:grid;
    grid-template-columns:30px auto auto 1fr;
    align-items:center;gap:4px 12px;padding:10px 11px 11px;
    border-bottom:1px solid var(--line2)}
  .t25 tbody tr.row td{border:0;padding:0;background:none}
  .t25 td.rk{grid-column:1;grid-row:1;width:auto;min-width:0;
    font:700 18px/1 var(--disp)}
  .t25 td.tm{grid-column:2 / 4;grid-row:1;font-size:16px;min-width:0;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .t25 td.mvc{grid-column:4;grid-row:1;justify-self:end}
  .t25 td.pw{grid-column:2;grid-row:2;justify-self:start}
  .t25 td.poll{grid-column:3;grid-row:2;justify-self:start}
  .t25 td.rec{grid-column:4;grid-row:2;justify-self:end;
    font:600 13px/1 var(--mono);color:var(--ink2)}
  .t25 td.form{grid-column:2 / -1;grid-row:3;justify-self:start}
  .t25 td.cf,.t25 td.wt,.t25 td.dv{display:none}
  .t25 tbody td.pw::before{content:"POWER ";color:#31D07E;opacity:.9}
  .t25 tbody td.poll::before{content:"AVCA ";color:var(--ink3,var(--ink2));opacity:.8}

  /* Long prose becomes readable rather than a wall */
  .tabhint,.note{font-size:13px;line-height:1.5}
}

/* ── THREE RANKINGS, THREE IDENTITIES ────────────────────────────────────
   POWER, R\00c9SUM\00c9 and the AVCA poll answer different questions and were
   rendering as thirteen identical numeric columns. Colour carries the
   distinction so it survives a glance: OURS is the green/amber pair, REFERENCE
   is deliberately recessed, and the group row above the header says which is
   which without a reader having to find the prose.  */
.rk3 tr.grp th{font:700 9.5px/1 var(--sans);letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink3,var(--ink2));padding:9px 10px 3px;
  border-bottom:0;background:transparent;text-align:center}
.rk3 tr.grp th.g-ours{color:#31D07E;
  box-shadow:inset 0 -2px 0 color-mix(in oklab,#31D07E 55%,transparent)}
.rk3 tr.grp th.g-ref{color:var(--ink2);opacity:.72;
  box-shadow:inset 0 -2px 0 color-mix(in oklab,var(--line2) 90%,transparent)}
.rk3 tr.grp th.g-proj{color:var(--navy);
  box-shadow:inset 0 -2px 0 color-mix(in oklab,var(--navy) 45%,transparent)}
.rk3 th.c-pow{color:#31D07E}
.rk3 th.c-res{color:#F2B441}
/* the reference block recedes -- present, checkable, and visibly not ours */
.rk3 th.c-ref{color:var(--ink2);opacity:.7;font-weight:600}
.rk3 td.c-ref,.rk3 tbody tr td.c-ref{color:var(--ink2);opacity:.78}
.rk3 th.c-avca{color:var(--ink2)}
/* R\00c9SUM\00c9 gets its own ramp -- amber, so it can never be mistaken for the
   green POWER column at a glance, which is the whole point of having two. */
.rs b{font:700 14px/1 var(--disp);color:#F2B441}
.rs .rsoff{color:var(--ink3,var(--ink2));opacity:.55}
/* ── TEAM HEADER: THREE TIERS, NOT TWELVE EQUAL CHIPS ────────────────────
   Our two rankings lead at full weight, the projection sits under them, and
   everything external or historical recedes behind a "Context" label. The old
   header opened with five other organisations' rankings styled identically to
   ours.  */
.chiptiers{display:flex;flex-direction:column;gap:7px;margin-top:10px}
.chips.tier1{gap:8px}
.chips.tier1 .chip{font-size:13.5px;padding:7px 12px;border-width:1px}
.chips.tier1 .chip b{font:700 17px/1 var(--disp)}
.chip.pow b{color:#31D07E}
.chip.res b{color:#F2B441}
.chips.tier2 .chip{font-size:12px;padding:5px 9px}
.chips.tier3{align-items:center;gap:5px;opacity:.72}
.chips.tier3 .chip{font-size:11.5px;padding:3px 8px;border-color:var(--line2);
  background:transparent}
.chips.tier3 .chip b{font-weight:600;color:var(--ink2)}
.tierlab{font:700 9px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink3,var(--ink2));opacity:.8;margin-right:2px}
/* ── COLLAPSIBLE METHODOLOGY ─────────────────────────────────────────────
   The reasoning stays on the page in full; it stops being the first thing a
   reader has to get past. */
details.method{margin-top:14px;border-top:1px solid var(--line2);padding-top:10px}
details.method>summary{cursor:pointer;list-style:none;
  font:13px/1.5 var(--sans);color:var(--ink2);padding:4px 0;
  display:flex;align-items:baseline;gap:7px}
details.method>summary::-webkit-details-marker{display:none}
details.method>summary::before{content:"\25B8";color:var(--navy);
  font-size:11px;transition:transform .15s ease;display:inline-block}
details.method[open]>summary::before{transform:rotate(90deg)}
details.method>summary:hover{color:var(--ink)}
details.method .note{margin-top:6px}
/* the two rankings keep their colours wherever they are named in prose */
b.kpow{color:var(--vx-power)}
b.kres{color:#F2B441}
/* ══ BALLOT WORKSHOP ══════════════════════════════════════════════════════
   The ballot is the object, so the SLOT is the loudest thing in a row and the
   evidence sits under it in one quiet line. No cards-in-cards, no charts: this
   is a list a person edits, and it should look like one. */
/* BALLOT-CSS-BEGIN -- everything to BALLOT-CSS-END is ballot-only and is
   stripped from the published build. VERIFIED BALLOT-ONLY BEFORE FENCING:
   every selector in the region is .bw*, #bw*, or .privtag, and .privtag has
   exactly one use in the whole file -- the Ballot Workshop heading. Adding a
   SHARED rule inside this fence would silently delete it from the public
   page, so put shared styles outside it. */
/* ── BALLOT WORKSHOP: a submitted poll sheet ───────────────────────────── */
/* The hierarchy built in the previous phase is untouched. This is the SHEET
   the list sits on: a ruled ground and a bounded column -- the look of a
   ballot that gets sent in, which is exactly what this list is. */
.bwlist{border-top:2px solid var(--cs-edge2);
  border-bottom:2px solid var(--cs-edge2)}
.bwrow{border-bottom:1px solid var(--cs-edge)}
.bwrow:last-child{border-bottom:0}
.bwrow:nth-child(odd){background:rgba(245,241,232,.018)}
.privtag{font:700 9px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;
  color:#F2B441;background:color-mix(in oklab,#F2B441 14%,transparent);
  border:1px solid color-mix(in oklab,#F2B441 32%,transparent);
  border-radius:3px;padding:3px 6px;vertical-align:middle;margin-left:9px}
.bwbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:12px 0 16px;
  padding-bottom:13px;border-bottom:1px solid var(--line2)}
.bwbtn{appearance:none;border:1px solid var(--line);background:var(--card);
  color:var(--ink);font:600 13px/1 var(--sans);padding:9px 14px;border-radius:4px;
  cursor:pointer}
.bwbtn:hover{border-color:var(--navy);color:#fff}
.bwbtn.primary{border-color:color-mix(in oklab,#31D07E 45%,var(--line));
  background:color-mix(in oklab,#31D07E 12%,var(--card))}
.bwstate{font:12px/1.4 var(--mono);color:var(--ink2);margin-left:auto}
.bwstate.good{color:#31D07E}
.bwstate.warn{color:#F2B441}
.bwgrid{display:grid;grid-template-columns:1fr 320px;gap:22px;align-items:start}
.bwh{font:700 11px/1 var(--sans);letter-spacing:.13em;text-transform:uppercase;
  color:var(--ink2);margin:20px 0 6px}
.bwsub{font:12.5px/1.5 var(--sans);color:var(--ink2);margin:0 0 8px}
.bwlist{list-style:none;margin:0;padding:0;counter-reset:none}
.bwrow{border-bottom:1px solid var(--line2);padding:10px 0 11px}
/* ⚠ THE ROW OVERFLOWED ITS OWN COLUMN. Measured on the desk: scrollWidth 952
   against clientWidth 906, which clipped the last control ("+ MY BOARD") --
   the row read as a rank list right up to the point where a control silently
   vanished. The identity block takes the slack and may shrink; the controls
   never do, because a control you cannot reach is worse than a wrapped name. */
.bwtop{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  row-gap:6px;min-width:0}
.bwtop>.bwnm,.bwtop>.bwid{flex:1 1 auto;min-width:0;overflow-wrap:anywhere}
.bwtop>.bwctl{flex:0 0 auto;margin-left:auto}
/* ⚠ THE REAL OFFENDER WAS THE MY BOARD BUTTON, not the row. It was being
   squeezed to 24px while its own label needed 71 -- so the text overflowed
   inside the button and pushed the whole row past its column. Measured before
   guessing: the row reported 952/906, but every direct child fitted; only a
   walk of the descendants found a control shrunk to a third of its content.
   Scoped to the ballot row so the My Board rules stay in their own fence. */
.bwctl .mbbtn{flex:0 0 auto;white-space:nowrap;min-width:0;width:auto}
/* ⚠ THE 1-25 LIST IS THE LOUDEST THING ON THIS PAGE. It was competing with
   its own evidence line and its own review panel; the slot numeral now reads
   as a scoreboard number and everything else steps back a size. */
.bwslot{font:700 30px/1 var(--disp);color:var(--chalk);min-width:40px;
  text-align:right;font-variant-numeric:tabular-nums}
.bwteam{letter-spacing:-.005em}
/* evidence recedes by SCALE and COLOUR, never by being faded to unreadable */
.bwev{font-size:11.5px;opacity:.92}
/* a note should feel like writing in a margin, not filling in a form */
.bwnote{border:0!important;border-bottom:1px dashed var(--line2)!important;
  border-radius:0!important;padding-left:0!important;font-style:italic;
  font-size:13.5px}
.bwnote:focus{border-bottom-color:var(--gold)!important;font-style:normal}
.bwnote::placeholder{font-style:italic;opacity:.55}
/* the review and pre-save areas are WORK SURFACES, not headline panels */
.bwreview{background:var(--sheet);border-color:var(--line)}
.bwpre{border-width:1px;background:var(--sheet)}
.bwprehd b{font-size:13px;letter-spacing:.05em;text-transform:uppercase}
/* the active ballot row carries the rally line -- the third and last place it
   is allowed to appear */
.bwrow:focus-within{background:var(--sheet)}
.bwrow:focus-within .bwslot{color:var(--gold)}
.bwmv{font:700 10px/1 var(--mono);padding:2px 4px;border-radius:3px}
.bwmv.up{color:#31D07E;background:color-mix(in oklab,#31D07E 14%,transparent)}
.bwmv.dn{color:#FF6B6B;background:color-mix(in oklab,#FF6B6B 14%,transparent)}
.bwmv.flat{color:var(--ink2)}
.bwmv.new{color:#F2B441;background:color-mix(in oklab,#F2B441 14%,transparent)}
.bwteam{font:600 16px/1 var(--disp);display:flex;align-items:center;gap:7px;flex:1;
  min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bwctl{display:flex;align-items:center;gap:3px}
.bwctl button{appearance:none;border:1px solid var(--line2);background:transparent;
  color:var(--ink2);width:26px;height:26px;border-radius:4px;cursor:pointer;
  font-size:11px;line-height:1}
.bwctl button:hover{color:var(--ink);border-color:var(--navy)}
.bwctl .bwx:hover{color:#FF6B6B;border-color:#FF6B6B}
/* ⚠ THE PADDING HAD TO BE STATED. A generic input rule supplies 8px 12px, which
   on a 42px box leaves 18px of content area and CLIPS THE DIGIT -- measured
   scrollWidth 46 against clientWidth 40, so the slot number was invisible in
   the control that sets it. The spinner is hidden for the same reason: it is
   half the width of the field and this is a type-a-number box. */
.bwjump{width:44px;height:26px;border:1px solid var(--line2);background:transparent;
  color:var(--ink);border-radius:4px;font:600 12px/1 var(--mono);text-align:center;
  padding:0 2px;box-sizing:border-box;-moz-appearance:textfield}
.bwjump::-webkit-outer-spin-button,.bwjump::-webkit-inner-spin-button{
  -webkit-appearance:none;margin:0}
/* the evidence: one quiet line, never competing with the slot */
.bwev{display:flex;flex-wrap:wrap;gap:5px 12px;margin:7px 0 0 40px;
  font:12px/1.4 var(--mono);color:var(--ink2)}
.bwe i{font-style:normal;font:700 9px/1 var(--sans);letter-spacing:.11em;
  margin-right:4px;opacity:.85}
.bwe.pw i{color:#31D07E}
.bwe.rs i{color:#F2B441}
.bwe.rs.off{opacity:.62}
.bwe.ref i{color:var(--ink3,var(--ink2))}
.bwe.form i{display:inline-block;width:14px;height:14px;line-height:14px;
  text-align:center;border-radius:3px;font:700 9px/14px var(--sans);margin-right:2px}
.bwe.form i.fw{color:#31D07E;background:color-mix(in oklab,#31D07E 16%,transparent)}
.bwe.form i.fl{color:#FF6B6B;background:color-mix(in oklab,#FF6B6B 16%,transparent)}
/* ── THE WEEKLY BRIEFING ──────────────────────────────────────────────────
   Facts about YOUR ballot, in one calm block. Not a card grid, not metrics:
   a labelled line per fact, with the ruler named wherever a rank appears. */
.bwbrief{border-top:2px solid var(--line2);border-bottom:1px solid var(--line);
  padding:14px 0 13px;margin:12px 0 4px}
.bwbrief h3{margin:0 0 3px;font:700 11px/1 var(--disp);letter-spacing:.18em;
  text-transform:uppercase;color:var(--gold)}
.bwbrief .bwbsub{margin:0 0 11px;font:12px/1.55 var(--sans);color:var(--slate)}
.bwbfacts{display:flex;flex-wrap:wrap;gap:10px 30px}
.bwbf{min-width:0}
.bwbf em{display:block;font:600 9px/1 var(--disp);letter-spacing:.15em;
  text-transform:uppercase;color:var(--slate);font-style:normal;margin-bottom:5px}
.bwbf b{font:700 21px/1 var(--disp);color:var(--chalk)}
.bwbf span{font:12.5px/1.5 var(--sans);color:var(--ink2);display:block;
  margin-top:3px;max-width:42ch}
.bwbf .none{color:var(--slate);font-style:italic}
.bwbf .bwrulerline{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 2px}
.bwbf .bwrulerline i{color:var(--line2);font-style:normal;margin:0 4px}
/* ── THE REVIEW QUEUE: one trigger per item, named ───────────────────────── */
.bwtrig{font:600 9.5px/1 var(--disp);letter-spacing:.09em;text-transform:uppercase;
  border:1px solid var(--line2);border-radius:2px;padding:3px 6px;color:var(--slate)}
.bwtrig.pw{color:var(--good);border-color:color-mix(in oklab,var(--good) 40%,transparent)}
.bwtrig.av{color:#7aa7ff;border-color:color-mix(in oklab,#7aa7ff 40%,transparent)}
.bwtrig.res{color:var(--chalk);border-color:var(--line2)}
.bwtrig.mine{color:#e8b13a;border-color:color-mix(in oklab,#e8b13a 45%,transparent)}
/* ⚠ ONE COLOUR PER RULER, EVERYWHERE. My ballot is amber, POWER is green, AVCA
   is blue. Movement uses ARROWS and never borrows a ruler's colour, so a green
   number is always POWER and never "went up". */
.bwv{font:600 12px/1 var(--mono)}
.bwv.mine{color:var(--vx-ballot)} .bwv.pw{color:var(--vx-power)}
.bwv.av{color:var(--vx-avca)}
.bwv.off{color:var(--slate);font-style:italic}
/* ── COMPARISON WORKSPACE ────────────────────────────────────────────────── */
.bwcompare{margin:8px 0 14px;border:1px solid var(--line);border-radius:4px;
  background:rgba(255,255,255,.012)}
.bwcompare>summary{cursor:pointer;padding:9px 12px;font-size:13px}
.bwcompare .bwsub{padding:0 12px}
.bwcmppick{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:0 12px 10px}
.bwcmppick label{font:600 9.5px/1 var(--disp);letter-spacing:.13em;
  text-transform:uppercase;color:var(--slate)}
.bwcmppick input{flex:1 1 190px;min-width:0;background:transparent;
  border:1px solid var(--line2);border-radius:3px;color:var(--ink);
  padding:7px 9px;font:13px var(--sans)}
#bwteamcmp{padding:0 12px 12px}
.bwcmptbl{width:100%;border-collapse:collapse}
.bwcmptbl th{text-align:left;font:600 9.5px/1 var(--disp);letter-spacing:.13em;
  text-transform:uppercase;color:var(--slate);padding:8px 10px 8px 0;
  border-bottom:1px solid var(--line2);vertical-align:bottom}
.bwcmptbl th.tm{font:700 17px/1.1 var(--disp);letter-spacing:-.005em;
  color:var(--chalk);text-transform:none}
.bwcmptbl td{padding:8px 10px 8px 0;border-bottom:1px solid var(--line);
  font-size:13px;color:var(--ink2);vertical-align:top}
.bwcmptbl td.lab{font:600 9.5px/1.4 var(--disp);letter-spacing:.12em;
  text-transform:uppercase;color:var(--slate);width:118px}
.bwcmptbl .un{color:var(--slate);font-style:italic}
/* ── HISTORY AS AN EDITORIAL RECORD ──────────────────────────────────────── */
.bwweek{border-top:1px solid var(--line);padding:9px 0}
.bwweek:first-child{border-top:0}
.bwweek .wkhd{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.bwweek .wkhd b{font:700 12px/1 var(--disp);color:var(--chalk)}
.bwweek .wkhd span{font:11px/1 var(--mono);color:var(--slate)}
.bwweek .wkline{margin-top:5px;font-size:12px;color:var(--ink2);line-height:1.6}
.bwweek button{margin-top:6px}
.bwro{border:1px solid var(--gold);border-radius:4px;padding:11px 12px;
  margin:10px 0;background:rgba(217,154,41,.05)}
.bwro .rohd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  font:700 11px/1 var(--disp);letter-spacing:.14em;text-transform:uppercase;
  color:var(--gold);margin-bottom:8px}
.bwro ol{margin:0;padding-left:22px;font-size:13px;line-height:1.75;
  color:var(--ink2);columns:2;column-gap:26px}
.bwro .ronote{margin:8px 0 0;font-size:12px;color:var(--slate);line-height:1.6}
@media (max-width:560px){
  .bwbfacts{gap:9px 18px}
  .bwbf b{font-size:18px}
  .bwcmppick input{flex:1 1 100%}
  .bwcmptbl td.lab{width:88px}
  .bwro ol{columns:1}
}
/* ---- Ballot review: evidence is SECONDARY, the slots stay dominant ------ */
.bwrulers{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0 4px;
  font-size:11.5px;color:var(--ink2)}
.bwr i{font:600 10px/1 var(--disp);letter-spacing:.07em;text-transform:uppercase;
  margin-right:5px;font-style:normal}
.bwr.mine i{color:#e8b13a}.bwr.pow i{color:#31D07E}.bwr.av i{color:#7aa7ff}
.bwr.off i{color:var(--ink3)}.bwr.off{color:var(--ink3)}
.bwreview{margin:8px 0 14px;border:1px solid var(--line);border-radius:4px;
  background:rgba(255,255,255,.012)}
.bwreview>summary{cursor:pointer;padding:9px 12px;font-size:13px}
.bwreview .bwsub{padding:0 12px}
.bwrn{color:var(--ink3);font-size:11.5px;margin-left:6px}
.bwgrp{border-top:1px solid var(--line);padding:8px 12px 10px}
.bwgrp>h4{margin:0 0 2px;font:600 10px/1.3 var(--disp);letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink2)}
.bwgrp>p{margin:0 0 7px;font-size:11.5px;color:var(--ink3)}
.bwcase{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;padding:5px 0;
  border-top:1px dotted rgba(255,255,255,.06);font-size:12.5px}
.bwcase:first-of-type{border-top:0}
.bwcase .bwcn{font:700 13px/1 var(--disp);min-width:118px}
.bwcase .bwcd{font:700 12px/1 var(--disp);color:#e8b13a}
.bwcase em{font-style:normal;color:var(--ink3)}
.bwcase .bwwhy,.bwprecols .bwwhy{color:#e0553f;font-size:11.5px}
.bwpin{background:none;border:1px solid var(--line);color:var(--ink2);
  border-radius:3px;font-size:10.5px;padding:2px 6px;cursor:pointer}
.bwpin.on{color:#e8b13a;border-color:#e8b13a}
.bwpre{margin:10px 0 14px;border:1px solid #e8b13a;border-radius:4px;
  background:rgba(232,177,58,.05)}
.bwprehd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:10px 12px;border-bottom:1px solid var(--line)}
.bwprehd b{font:700 14px/1 var(--disp)}
.bwprecols{display:grid;grid-template-columns:repeat(3,1fr);gap:0}
.bwprecols>div{padding:10px 12px;border-right:1px solid var(--line)}
.bwprecols>div:last-child{border-right:0}
.bwprecols h4{margin:0 0 6px;font:600 10px/1.3 var(--disp);letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink2)}
.bwprecols ul{margin:0;padding-left:15px;font-size:12.5px;line-height:1.7}
.bwprecols .none{color:var(--ink3);font-size:12.5px}
.bwcmp{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.bwh4{margin:0 0 6px;font:600 10px/1.3 var(--disp);letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink2)}
.bwcmprow{display:flex;align-items:center;gap:6px;font-size:11.5px}
.bwcmprow select{flex:1;min-width:0}
#bwcmpout{margin-top:8px;font-size:12.5px;line-height:1.65}
@media (max-width:560px){
  .bwprecols{grid-template-columns:1fr}
  .bwprecols>div{border-right:0;border-bottom:1px solid var(--line)}
  .bwcase .bwcn{min-width:0}
}
/* the human-judgment prompt: appears only when a slot is far from POWER */
.bwask{margin:8px 0 0 40px;padding:8px 10px;border-radius:4px;
  border:1px solid color-mix(in oklab,#F2B441 30%,var(--line2));
  background:color-mix(in oklab,#F2B441 6%,transparent)}
.bwask.done{border-color:var(--line2);background:transparent}
.bwask label{display:block;font:12px/1.45 var(--sans);color:var(--ink2);margin-bottom:6px}
.bwask label b{color:#F2B441}
.bwaskrow{display:flex;gap:7px}
.bwask select{flex:0 0 auto;background:var(--card);color:var(--ink);
  border:1px solid var(--line2);border-radius:4px;padding:5px 7px;font:12px var(--sans)}
.bwask input{flex:1;min-width:0}
.bwask input,.bwnote{background:transparent;border:1px solid var(--line2);
  border-radius:4px;padding:6px 8px;color:var(--ink);font:12.5px var(--sans)}
.bwnote{display:block;width:100%;margin:7px 0 0 40px;max-width:calc(100% - 40px);
  box-sizing:border-box}
.bwnote:focus,.bwask input:focus{outline:none;border-color:var(--navy)}
.bwpool{display:flex;flex-wrap:wrap;gap:6px}
.bwchip{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;
  border:1px solid var(--line2);border-radius:4px;font:12.5px var(--sans);
  color:var(--ink)}
.bwchip button{appearance:none;border:0;background:transparent;cursor:pointer;
  color:var(--ink2);font:700 10px var(--sans)}
.bwchip button:hover{color:#31D07E}
.bwnone,.bwempty{color:var(--ink2);font:13px var(--sans)}
.bwlink{appearance:none;border:0;background:none;color:var(--navy);cursor:pointer;
  font:13px var(--sans);text-decoration:underline;padding:0}
.bwadd{margin-top:12px}
.bwadd input{width:100%;max-width:340px;background:transparent;color:var(--ink);
  border:1px solid var(--line2);border-radius:4px;padding:9px 11px;font:13px var(--sans)}
.bwside{display:flex;flex-direction:column;gap:14px;position:sticky;top:64px}
.bwcard{border:1px solid var(--line2);border-radius:4px;padding:12px 14px;
  background:var(--card)}
.bwcard .bwh{margin-top:0}
.bwcard textarea{width:100%;box-sizing:border-box;background:transparent;
  color:var(--ink);border:1px solid var(--line2);border-radius:4px;padding:8px;
  font:12.5px/1.5 var(--sans);resize:vertical}
.bwdl{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}
.bwdrow{font:12.5px var(--sans);color:var(--ink)}
.bwdrow i{font-style:normal;font:700 10px var(--mono)}
.bwdrow i.up{color:#31D07E}
.bwdrow i.dn{color:#FF6B6B}
.bwhrow{display:flex;align-items:baseline;gap:8px;padding:5px 0;
  border-bottom:1px solid var(--line2);font:12px var(--mono);color:var(--ink)}
.bwhrow:last-child{border-bottom:0}
.bwlatest{font:700 9px/1 var(--sans);letter-spacing:.1em;text-transform:uppercase;
  color:#31D07E;margin-left:auto}
/* ⚠ A GRID ITEM'S DEFAULT min-width IS auto, NOT 0, so collapsing to one
   column is not enough: the column still cannot shrink below its content's
   min-content width, and the workshop sat 26px wider than a 390px phone
   with no sideways scrollbar to show for it. Measured, not guessed:
   .bwmain reported min-width:auto while every descendant read 0. */
.bwmain,.bwside{min-width:0}
@media (max-width:900px){ .bwgrid{grid-template-columns:1fr} .bwside{position:static} }
@media (max-width:560px){
  /* a deliberate ranked list: slot and team on one line, evidence under it,
     controls big enough for a thumb -- never a squeezed desktop row */
  .bwev,.bwnote,.bwask{margin-left:0;max-width:100%}
  /* ⚠ SLOT AND TEAM BELONG ON THE SAME LINE. The first version put the team
     name on its own row BELOW the controls, so a ranked list read as "1 ▲▼✕"
     then "Nebraska" -- the number and the thing it ranks separated by the
     buttons. A ranked list is "1 Nebraska"; the controls are secondary and go
     underneath. */
  .bwtop{flex-wrap:wrap;gap:6px 8px}
  .bwslot{font-size:24px;min-width:26px;text-align:left;order:1}
  .bwmv{order:2}
  .bwteam{flex:1 1 auto;order:3;font-size:17px}
  .bwctl{order:4;flex:1 1 100%;justify-content:flex-end;margin-left:0}
  .bwctl button{width:34px;height:34px;font-size:13px}
  .bwjump{width:46px;height:34px}
  .bwbar{gap:7px}
  .bwbtn{flex:1 1 auto;text-align:center}
  .bwstate{margin-left:0;flex:1 1 100%}
  .bwaskrow{flex-direction:column}
  .bwask select{width:100%}
}

/* ── THE VOTER'S DESK: status first, ballot central, finishing last ────────
   ⚠ EVERY RULE HERE IS INSIDE THE BALLOT-CSS FENCE ON PURPOSE. The selector
   names alone enumerate a private feature -- that is why the whole stylesheet
   is stripped from the public build, and why nothing below may drift outside
   these sentinels. */
.bwstatus{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:1px;background:var(--vx-rule);border:1px solid var(--vx-rule);
  border-radius:4px;overflow:hidden;margin:0 0 18px}
.bwstatus>div{background:var(--sheet);padding:10px 13px;display:flex;
  flex-direction:column;gap:3px;min-width:0}
.bwstatus i{font-style:normal;font:700 9px/1.4 var(--disp);letter-spacing:.12em;
  text-transform:uppercase;color:var(--slate)}
.bwstatus b{font:700 14px/1.2 var(--disp);color:var(--chalk);
  overflow-wrap:anywhere}
.bwstatus b.dim{color:var(--ink3);font-weight:600}
.bwstatus b.warn{color:#F2B441}
.bwstatus b.ok{color:var(--vx-power)}

/* the ruler key: a swatch and a word, not a sentence each */
.bwrulers{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 16px;
  padding:0 0 14px;border-bottom:1px solid var(--vx-rule)}
.bwrulers .bwr{display:inline-flex;align-items:center;gap:7px;
  font:700 10px/1 var(--disp);letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink2);background:none;border:0;padding:0}
.bwrulers .bwsw{width:8px;height:8px;border-radius:1px;flex:0 0 8px}
.bwrulers .mine .bwsw{background:var(--vx-ballot)}
.bwrulers .pow  .bwsw{background:var(--vx-power)}
.bwrulers .av   .bwsw{background:var(--vx-avca)}
.bwrulers .off  .bwsw{background:var(--line2)}
.bwrulers .off{color:var(--ink3)}

/* finishing block */
.bwfinish{margin:22px 0 0;padding:14px 0 0;border-top:1px solid var(--vx-rule)}
.bwfinlab{font:700 10px/1 var(--disp);letter-spacing:.16em;text-transform:uppercase;
  color:var(--slate);margin:0 0 9px}
.bwfinish .bwbar{margin:0;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
/* ⚠ THE DESTRUCTIVE ONE IS QUIET AND LAST. Reset replaces all 25 slots; it
   should not sit beside Save looking like a peer. */
.bwbtn.bwquiet{margin-left:auto;opacity:.68;font-weight:600}
.bwbtn.bwquiet:hover{opacity:1;border-color:#F2B441;color:#F2B441}

@media (max-width:560px){
  .bwstatus{grid-template-columns:1fr 1fr}
  .bwstatus>div{padding:8px 10px}
  .bwstatus b{font-size:13px}
  .bwrulers{gap:5px 13px}
  .bwfinish .bwbar{gap:8px}
  .bwbtn.bwquiet{margin-left:0;width:100%}
}

/* BALLOT-CSS-END */

.leadhint{color:var(--ink2);opacity:.8}
/* ── THE RANKING SHEET ────────────────────────────────────────────────────
   The table IS the page here, so it gets a reading surface of its own -- a
   chalk wash rather than another bordered card -- and the group header is the
   loudest thing above it. The three rulers are separated by a RULE, not by
   three different background colours, so no group looks more official than
   another. */
#v-rankings .panel{background:var(--sheet);border:0;border-top:2px solid var(--line2);
  border-radius:0}
#v-rankings .rk3{border-collapse:collapse}
.rk3 thead tr.grp th{font:600 9.5px/1 var(--disp);letter-spacing:.16em;
  text-transform:uppercase;padding:11px 10px 7px;color:var(--slate);
  border-bottom:1px solid var(--line)}
.rk3 thead tr.grp th.g-ours{color:var(--good);
  box-shadow:inset 2px 0 0 color-mix(in oklab,var(--good) 55%,transparent)}
.rk3 thead tr.grp th.g-ref{color:var(--gold);
  box-shadow:inset 2px 0 0 color-mix(in oklab,var(--gold) 55%,transparent)}
.rk3 thead tr.grp th.g-proj{color:var(--navy);
  box-shadow:inset 2px 0 0 color-mix(in oklab,var(--navy) 55%,transparent)}
/* the rank numeral is the anchor of the row */
.rk3 tbody td.rk{font:700 19px/1 var(--disp);color:var(--chalk)}
/* zebra by READING GROUP, five rows at a time, so the eye can track across
   thirteen columns without a border round every cell */
.rk3 tbody tr:nth-child(10n+1) td,.rk3 tbody tr:nth-child(10n+2) td,
.rk3 tbody tr:nth-child(10n+3) td,.rk3 tbody tr:nth-child(10n+4) td,
.rk3 tbody tr:nth-child(10n+5) td{background:var(--sheet)}
.rk3 tbody tr:hover td{background:var(--sheet2)}

/* ── THE TEAM PAGE LOCKUP ─────────────────────────────────────────────────
   ⚠ WRITTEN AGAINST THE REAL MARKUP. My first pass styled .thd/.trulers/.tbox,
   none of which exist -- dead rules that would have shipped looking like work.
   The panel actually emits .thead, .chiptiers, .glance and .tsec, read off the
   rendered DOM rather than assumed.
   Crest, name, record and three NAMED rulers, then the evidence. The identity
   is a lockup with a rule under it, not a field of equally loud badges. */
#teamcard>.thead{border-bottom:2px solid var(--line2);padding-bottom:15px}
/* the panel itself is the page, not a card sitting on it */
#teamcard>div{border-radius:0}
#teamcard .tcols{border-top:1px solid var(--line);padding-top:4px}
#teamcard .thead h2{font:700 42px/.94 var(--disp);letter-spacing:-.012em;
  color:var(--chalk);text-transform:uppercase;display:flex;align-items:center;
  gap:12px;margin:0}
#teamcard .thead h2 .lg{width:44px;height:44px;flex:none}
#teamcard .thead .sub{font:12.5px/1.6 var(--sans);color:var(--slate)}
/* the three rulers sit on one quiet line; the tier labels name them */
#teamcard .chiptiers{margin-top:12px}
#teamcard .tierlab{font:600 9px/1 var(--disp);letter-spacing:.16em;
  text-transform:uppercase;color:var(--slate)}
#teamcard .chip{border-radius:3px}
#teamcard .chip.ours{border-color:color-mix(in oklab,var(--good) 45%,transparent)}
/* "at a glance" is the first evidence a reader wants, so it gets air and the
   headline number gets scale */
/* ⚠ FOUR EQUAL BOXES SAY ALL FOUR MATTER THE SAME. They are four facts on one
   surface, so they get column gutters and a single rule instead of a border
   each -- and FORM gets the room, because "how are they playing" is the
   question a team page is opened to answer, ahead of a season stat. */
#teamcard .glance{border-top:0;padding:14px 0 4px;gap:0}
#teamcard .gl{border:0!important;background:transparent!important;
  border-radius:0;padding:2px 18px;border-left:1px solid var(--line)!important}
#teamcard .gl:first-child{padding-left:0;border-left:0!important}
#teamcard .glance .gl:nth-child(2){flex:1.3}
#teamcard .glbig{font:700 26px/1 var(--disp);color:var(--chalk)}
#teamcard .gll{font:600 9px/1 var(--disp);letter-spacing:.14em;
  text-transform:uppercase;color:var(--slate)}
/* every later section is a SECTION on one working surface -- a rule and a
   label, not a box inside a box */
#teamcard .tsec{background:transparent;border:0;border-top:1px solid var(--line);
  border-radius:0;padding:15px 0 6px}
#teamcard .tsec h4,#teamcard .tsec .wh2{font:600 10px/1 var(--disp);
  letter-spacing:.15em;text-transform:uppercase;color:var(--slate)}

/* ── FOCUS AND MOTION ─────────────────────────────────────────────────────
   ⚠ ONE FOCUS TREATMENT FOR THE WHOLE SITE. Buttons had a gold ring, links and
   inputs had whatever the browser supplies -- and a keyboard user needs the
   same signal everywhere, on both the navy ground and the chalk sheet. */
:focus-visible{outline:2px solid var(--gold);outline-offset:2px;border-radius:2px}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,
textarea:focus-visible,summary:focus-visible,[tabindex]:focus-visible{
  outline:2px solid var(--gold);outline-offset:2px}
/* a global stop, so a future animation cannot opt itself out of the promise */
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.001ms!important;
    animation-iteration-count:1!important;transition-duration:.001ms!important}
}

/* ── DIGBY, THE ICON LANGUAGE AND THE TREND ───────────────────────────────
   ⚠ DIGBY IS SUBORDINATE TO DATA, AND THE CSS IS WHERE THAT IS ENFORCED. He
   is capped at 76px, sits at 88% opacity, and appears only in an empty state
   or an earned moment -- never in a row, never over a score. */
.digbox{display:flex;align-items:flex-start;gap:16px;padding:18px 0 6px}
.digbox .digby-art{flex:none;width:76px;height:76px;opacity:.88}
.digbox .dsay{font:15px/1.6 var(--sans);color:var(--ink2);max-width:52ch}
.digbox .dsay b{color:var(--chalk);font-weight:600}
.digbox .dwho{font:600 9.5px/1 var(--disp);letter-spacing:.16em;
  text-transform:uppercase;color:var(--gold);margin-bottom:7px}
@media (max-width:560px){
  .digbox{gap:12px}
  .digbox .digby-art{width:54px;height:54px}
  .digbox .dsay{font-size:14px}
}
/* ── THE MATCH STORY STRIP ────────────────────────────────────────────────
   A broadcast graphic made of facts that already exist: the set line, what was
   forecast BEFORE first serve, and what the result was. No invented metric. */
.mstory{border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  margin:12px 0 4px;padding:11px 0;display:flex;flex-wrap:wrap;
  align-items:center;gap:10px 22px}
.mstory .msl{font:600 9px/1 var(--disp);letter-spacing:.15em;
  text-transform:uppercase;color:var(--slate);display:block;margin-bottom:5px}
.mstory .msv{font:600 15px/1 var(--mono);color:var(--chalk)}
.mstory .msv small{font-size:11.5px;color:var(--ink3);font-weight:400}
.mstory .msets{display:flex;gap:5px}
.mstory .msets span{font:600 12px/1 var(--mono);color:var(--ink2);
  border:1px solid var(--line2);border-radius:2px;padding:4px 6px}
@media (max-width:560px){.mstory{gap:9px 16px}.mstory .msv{font-size:13.5px}}
{{ICON_CSS}}{{TREND_CSS}}
/* ⚠ A DETAIL IS A PAGE, NOT A HIGHLIGHTED ROW ABOVE THE WHOLE DIRECTORY. The
   full 149-row table used to sit directly under an exact player profile,
   competing with it and repeating it. */
#v-players.detail-open #ptable{display:none}
#v-players.detail-open .pdirhint{display:block}
.pdirhint{display:none;margin:16px 0 0;font-size:12.5px;color:var(--slate)}
.linkbtn{appearance:none;border:0;background:none;color:var(--navy);
  cursor:pointer;font:inherit;padding:0;text-decoration:underline}
.statline{display:flex;flex-wrap:wrap;align-items:baseline;gap:7px;
  font:var(--mono);margin:2px 0 6px}
.statline .sv{font:600 15px/1 var(--mono);color:var(--chalk)}
.statline .sl{font:600 9.5px/1 var(--disp);letter-spacing:.12em;color:var(--slate)}
.statline .sd{color:var(--line2);font-style:normal;margin:0 3px}
@media (max-width:560px){.statline .sv{font-size:14px}}

/* ⚠ THE MATCH LOG RAN OFF A 390px PHONE. .gline is a flex row of date,
   opponent, a long stat string and the result; with nothing allowed to wrap it
   measured 431-570px inside a 370px column and clipped, with no scrollbar to
   say so. The stat string wraps now and the row reflows. */
@media (max-width:560px){
  .gline{flex-wrap:wrap;row-gap:3px}
  .gline .ss{flex:1 1 100%;min-width:0;white-space:normal}
  .gline .dt{min-width:0}
}

/* ⚠ `hidden` LOSES TO A `display` RULE. .cards{display:flex} beat the UA's
   [hidden]{display:none}, so a band marked hidden in the markup rendered
   anyway -- which is how the old result cards were still on screen under the
   new ledger. One global rule settles it for every future case. */
[hidden]{display:none!important}
/* ⚠ THE LEDGER OWNS MATCH ROWS ON SCORES. The Live / Just finished / Later
   today bands were full cards for CLOSED matches, which is exactly what the
   ledger replaces -- and showing both meant the same match twice, once as a
   card and once as a row. The nodes stay in the DOM on purpose: the live
   poller writes to them and the just-finished seam logic reads #resultcards to
   know what the crawl has already caught. They are data plumbing now, not a
   surface. "What changed" stays -- it is a one-line digest, not a card list. */
#v-scores #live,#v-scores #justin,#v-scores #today,
#v-scores #weekbox,#v-scores #resultcards{display:none!important}
/* the date jump moves INTO the ledger's control row, where its target is */
#v-scores .datejump{display:flex;align-items:center;gap:8px;margin-left:auto;
  font:11.5px/1 var(--mono);color:var(--slate)}


/* GAMEDAY-CSS-BEGIN */
.gd-panel{border:1px solid var(--vx-rule);border-left:3px solid var(--gold);
  border-radius:4px;padding:13px 15px;margin:0 0 20px;background:var(--alt)}
.gd-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:0 0 10px}
.gd-head b{font:700 16px/1.2 var(--disp);color:var(--chalk)}
.gd-head span{font:12px/1 var(--mono);color:var(--ink2)}
.gd-head a{font:700 9px/1 var(--disp);letter-spacing:.09em;text-transform:uppercase;
  color:var(--vx-avca);text-decoration:none}
.gd-steps{list-style:none;margin:0 0 10px;padding:0;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
.gd-step{display:flex;flex-direction:column;gap:2px;padding:7px 9px;
  border:1px solid var(--vx-rule);border-radius:3px}
.gd-step i{font-style:normal;font:700 9px/1.4 var(--disp);letter-spacing:.11em;
  text-transform:uppercase;color:var(--slate)}
.gd-step b{font:600 11.5px/1.3 var(--mono);color:var(--ink3)}
.gd-step.done{border-color:var(--vx-power)}
.gd-step.done b{color:var(--vx-power)}
.gd-claim{margin:0;font-size:12.5px;color:var(--ink2);line-height:1.55}
.gd-claim b{color:#F2B441}
.gd-none{margin:0;font-size:12.5px;color:var(--ink3)}
@media (max-width:560px){
  .gd-steps{grid-template-columns:1fr 1fr}
  .gd-head b{font-size:15px}
}
/* GAMEDAY-CSS-END */

/* INTEL-CSS-BEGIN */
/* ══ THE WIRE ═════════════════════════════════════════════════════════════
   An editorial desk, not a card grid: ONE lead with a picture, then dense
   ruled rows. Everything here is inside the Intel fence and is stripped whole
   from the public build -- markup, styles and the host list alike. */
.in-lead{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);
  gap:18px;align-items:start;padding:0 0 18px;
  border-bottom:2px solid var(--cs-edge2);margin-bottom:16px}
.in-lead.read{opacity:.72}
.in-leadtext{min-width:0;display:flex;flex-direction:column;gap:9px}
.in-leadtitle{font:700 27px/1.14 var(--disp);letter-spacing:-.004em;
  color:var(--cs-white);text-decoration:none;text-transform:uppercase;
  overflow-wrap:anywhere}
.in-leadtitle:hover{color:var(--cs-gold)}
.in-leadtitle:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:3px}
.in-out{font:600 12px/1 var(--sans);color:var(--navy);text-decoration:none;
  border:1px solid var(--cs-edge2);border-radius:2px;padding:8px 11px}
.in-out:hover{color:var(--cs-white);border-color:var(--navy)}
.in-out:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
.in-fmt{font:600 9.5px/1 var(--disp);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink3);border:1px solid var(--cs-edge);padding:3px 5px;
  border-radius:2px}

/* ── the three media states ────────────────────────────────────────────── */
/* ⚠ ONE FIXED-RATIO BOX FOR ALL THREE, so swapping between them -- including
   an image that 404s after load -- shifts nothing. */
/* ⚠ THE PHOTO LOADED AND PAINTED NOTHING, AND NO MEASUREMENT COULD SEE IT.
   The first version was `aspect-ratio:16/9` on this box with
   `width:100%;height:100%` on the child. The image fetched, decoded
   (naturalWidth 1280, naturalHeight 720), sat topmost under
   elementFromPoint, reported opacity 1, visibility visible, no filter, no
   transform, no clip -- and the box rendered flat navy.
   The clincher: swapping aspect-ratio for an explicit height made it appear
   INSTANTLY, and the computed heights either way were 236.25px against 236px.
   Every number was the same in the broken state and the working one. There was
   no reading available that told them apart; only the pixels did.
   (The inverse of the lesson this project already paid for -- there I trusted
   getComputedStyle over the screen and chased a phantom for six turns. Here
   the measurements were all correct and the render was still wrong. The rule
   that survives both: look at the screen, then measure to explain it.)
   The fix keeps aspect-ratio -- it is what reserves the space and stops the
   layout shifting -- and drops the percentage height: an absolutely positioned
   child resolves against the padding box and needs no definite parent height.
   Guarded in test_wire.py. */
/* ⚠ AND THE FIX IS NOT "absolute child" EITHER -- I SHIPPED THAT AND IT WAS
   STILL BLANK. Isolated properly the second time: `aspect-ratio` on this box
   is the whole cause, on its own, whatever the child does. Toggling ONLY
   aspect-ratio:16/9 -> auto plus an explicit height makes the photograph
   appear, and the geometry is byte-identical across the two states -- box
   420x236, image 418x234, position absolute, in both.
   So the space is reserved the way it was reserved before `aspect-ratio`
   existed: padding-top as a percentage of WIDTH. 9/16 = 56.25%. Same
   no-layout-shift guarantee, no dependence on the property that suppresses
   the paint. */
.in-media{position:relative;height:0;padding-top:56.25%;overflow:hidden;
  border:1px solid var(--cs-edge2);background:#0B1D33}
.in-media img{position:absolute;inset:0;width:100%;height:100%;
  object-fit:cover;display:block}
/* ⚠ NO opacity:0 START. An earlier attempt began the image transparent and
   revealed it on load, on the theory that the class change would force the
   repaint. It did not help, and it added a way for the picture to be invisible
   FOREVER if onload never fired. The image is opaque from the start; the
   is-shown class is kept only as the hook the guard asserts. */
.in-media.is-shown{--in-loaded:1}
.in-media .mm{position:absolute;inset:0;aspect-ratio:auto;border:0}
.in-media .in-nomedia{position:absolute;inset:0}
/* ⚠ THE SOURCE IS NAMED ON THE PICTURE ITSELF. A borrowed image must never be
   able to read as ours, and a credit that lives only in a caption gets lost
   the moment anything is rearranged. */
.in-credit{position:absolute;right:0;bottom:0;z-index:3;
  font:600 9px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
  color:var(--chalk);background:rgba(7,23,43,.82);padding:4px 6px}
.in-nomedia{display:flex;align-items:center;
  justify-content:center;text-align:center;
  border:1px dashed var(--cs-edge2);background:rgba(245,241,232,.02)}
.in-nomedia span{font:500 11.5px/1.5 var(--mono);color:var(--ink3);
  letter-spacing:.05em;max-width:70%}

/* ── the rail ──────────────────────────────────────────────────────────── */
.in-railhd{font:700 10px/1 var(--disp);letter-spacing:.2em;text-transform:uppercase;
  color:var(--slate);padding-bottom:8px;border-bottom:1px solid var(--cs-edge);
  margin-bottom:2px}
.in-rail .in-row{border-bottom:1px solid var(--cs-edge);padding:11px 0}
.in-rail .in-row:last-child{border-bottom:0}
.in-also{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;
  font:11.5px/1.4 var(--sans)}
.in-also i{font-style:normal;color:var(--ink3);
  font:600 9.5px/1 var(--disp);letter-spacing:.13em;text-transform:uppercase}
.in-also a{color:var(--navy);text-decoration:none;
  border:1px solid var(--cs-edge);border-radius:2px;padding:3px 6px;
  font:600 10px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase}
.in-also a:hover{color:var(--cs-white);border-color:var(--navy)}
.in-also a:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
.in-more{appearance:none;background:transparent;border:0;
  border-top:1px solid var(--cs-edge);width:100%;text-align:left;
  padding:11px 2px;color:var(--navy);font:600 12px/1 var(--sans);cursor:pointer}
.in-more:hover{color:var(--cs-white)}
.in-more:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:-2px}

@media (max-width:700px){
  /* ⚠ LEAD FIRST, AND IT KEEPS ITS PICTURE. The brief's instruction and the
     right one: the lead is the reason this reads as a desk rather than a list,
     so it stacks rather than shrinking into a thumbnail. */
  .in-lead{grid-template-columns:minmax(0,1fr);gap:12px}
  .in-leadtitle{font-size:21px}
}
@media (max-width:560px){
  .in-leadtitle{font-size:19px}
  .in-meta{flex-wrap:wrap;row-gap:5px}
  /* metadata stays legible -- no 9px on a phone */
  .in-src,.in-row time,.in-fmt{font-size:11px}
  .in-acts{flex-wrap:wrap;row-gap:7px}
  .in-out{padding:9px 12px}
}
/* ── INTEL: the same treatment one distance out -- a wire ──────────────── */
#v-intel{position:relative}
#v-intel .in-bar{border-top:1px solid var(--cs-edge);
  border-bottom:1px solid var(--cs-edge);padding:9px 0}
#v-intel .in-state{font:11px/1.5 var(--mono);letter-spacing:.05em;
  color:var(--slate);text-transform:uppercase}
#v-intel .privtag{vertical-align:.22em}
.in-bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 10px}
.in-state{margin:0 0 16px;font:12px/1.5 var(--mono);color:var(--ink3)}
.in-row{border-bottom:1px solid var(--vx-rule);padding:11px 0 12px}
.in-row.read{opacity:.55}
.in-meta{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:0 0 4px}
.in-src{font:700 9px/1.5 var(--disp);letter-spacing:.11em;text-transform:uppercase;
  color:var(--vx-avca);background:var(--vx-avca-dim);padding:2px 7px;border-radius:3px}
.in-meta time{font:11.5px/1 var(--mono);color:var(--ink3)}
.in-teams{display:inline-flex;align-items:center;gap:5px}
.in-teams img{width:16px;height:16px}
.in-teams b{font:600 11px/1 var(--sans);color:var(--gold)}
.in-title{display:block;font:700 16px/1.3 var(--disp);color:var(--chalk);
  text-decoration:none;overflow-wrap:anywhere}
.in-title:hover{color:var(--gold)}
.in-acts{display:flex;gap:8px;margin:7px 0 0}
.in-acts button{font:700 9px/1 var(--disp);letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink3);background:none;border:0;
  padding:3px 0;cursor:pointer}
.in-acts button:hover{color:var(--gold)}
.in-note{border-left:2px solid var(--line2);padding:8px 0 8px 12px;margin:0 0 14px;
  font-size:12.5px;color:var(--ink2)}
.in-note.warn{border-left-color:#F2B441}
.in-note b{color:var(--chalk)}
.in-foot{margin:18px 0 0;font-size:11.5px;color:var(--ink3);max-width:70ch}
@media (max-width:560px){
  .in-bar{gap:8px}
  .in-bar .seg{flex-wrap:wrap;width:100%}
  .in-title{font-size:15px}
  .in-meta{gap:7px}
}
/* INTEL-CSS-END */

/* FILMROOM-CSS-BEGIN */
/* ── FILM ROOM: a scouting notebook, not a generic private tool ────────── */
#v-film{position:relative}
#v-film .fr-bar{border-top:1px solid var(--cs-edge);
  border-bottom:1px solid var(--cs-edge);padding:9px 0}
#v-film .fr-new{border-left:3px solid var(--cs-gold);padding-left:14px}
#v-film .privtag{vertical-align:.22em}
/* ── FILM ROOM: a notebook, ruled and dated ────────────────────────────────
   ⚠ INSIDE A SENTINEL PAIR. The selector names alone say what this feature
   records; the public build removes the whole block. */
.fr-new{margin:0 0 20px;padding:0 0 18px;border-bottom:1px solid var(--vx-rule)}
.fr-form{display:flex;flex-direction:column;gap:11px}
.fr-form label{display:flex;flex-direction:column;gap:4px;
  font:700 9px/1.4 var(--disp);letter-spacing:.12em;text-transform:uppercase;
  color:var(--slate);min-width:0}
.fr-form input,.fr-form select,.fr-form textarea{font:13px/1.5 var(--sans);
  color:var(--chalk);background:var(--alt);border:1px solid var(--line2);
  border-radius:3px;padding:8px 10px;letter-spacing:0;text-transform:none;
  min-width:0;width:100%}
.fr-form textarea{resize:vertical}
.fr-row{display:grid;grid-template-columns:1fr 1fr;gap:11px}
.fr-full{width:100%}
.fr-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.fr-btn{font:700 10px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  padding:10px 15px;border-radius:3px;border:1px solid var(--line2);
  background:none;color:var(--ink2);cursor:pointer}
.fr-btn.primary{border-color:var(--gold);color:var(--gold)}
.fr-btn:hover{color:var(--chalk);border-color:var(--chalk)}
.fr-freeze{flex-direction:row!important;align-items:center;gap:6px!important;
  text-transform:none!important;letter-spacing:0!important;font:12px/1.4 var(--sans)!important;
  color:var(--ink2)!important}
.fr-freeze input{width:auto}
.fr-state{font:12px/1.4 var(--mono);color:var(--ink3);margin-left:auto}

.fr-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 16px}
.fr-bar input[type=search]{flex:1 1 200px;min-width:0}
.fr-bar input,.fr-bar select{font:13px/1.4 var(--sans);color:var(--chalk);
  background:var(--alt);border:1px solid var(--line2);border-radius:3px;
  padding:8px 10px}

.fr-day{margin:0 0 22px}
.fr-entry{border-left:2px solid var(--line2);padding:0 0 14px 14px;
  margin:0 0 14px;position:relative}
.fr-entry:hover{border-left-color:var(--gold)}
.fr-meta{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:0 0 5px}
.fr-meta time{font:12px/1 var(--mono);color:var(--ink3)}
.fr-ctx{font:700 9px/1.5 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  padding:2px 7px;border-radius:3px;background:var(--line);color:var(--ink2)}
.fr-ctx.pre{color:var(--vx-avca);background:var(--vx-avca-dim)}
.fr-ctx.during{color:#FF9E5A;background:rgba(255,158,90,.14)}
.fr-ctx.post{color:var(--vx-power);background:var(--vx-power-dim)}
.fr-src{font:11px/1 var(--mono);color:var(--ink3)}
.fr-del{margin-left:auto;background:none;border:0;color:var(--ink3);
  cursor:pointer;font-size:13px;padding:2px 5px}
.fr-del:hover{color:#FF7A7A}
.fr-entry h4{margin:0 0 4px;font:700 15px/1.25 var(--disp);color:var(--chalk)}
.fr-body{margin:0 0 7px;font-size:13.5px;line-height:1.6;color:var(--ink2);
  white-space:pre-wrap;overflow-wrap:anywhere}
.fr-tags{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0 0 6px}
.fr-tags img{width:18px;height:18px}
.fr-tag{font:600 11px/1 var(--sans);color:var(--ink2);background:var(--alt);
  border:1px solid var(--line);border-radius:3px;padding:3px 7px}
.fr-tag.pl{border-style:dashed}
/* ⚠ A FROZEN CHIP CARRIES ITS DATE. Without the stamp it reads as a live
   value, and a note kept for a month would quietly become wrong. */
.fr-facts{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:0 0 6px}
.fr-facts>i{font-style:normal;font:700 9px/1.4 var(--disp);letter-spacing:.11em;
  text-transform:uppercase;color:var(--slate)}
.fr-chip{font:11px/1 var(--mono);color:var(--ink2);background:var(--alt);
  border:1px solid var(--line2);border-radius:3px;padding:3px 7px;
  display:inline-flex;align-items:center;gap:5px}
.fr-chip b{color:var(--slate);font-weight:700;font-size:9px;
  letter-spacing:.06em;text-transform:uppercase}
.fr-chip em{font-style:normal;color:var(--ink3);font-size:10px}
.fr-link{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;
  font-size:11.5px;margin:0 0 4px}
.fr-link a{color:var(--vx-avca)}
.fr-link span{color:var(--ink3)}
.fr-open{font:700 9px/1 var(--disp);letter-spacing:.09em;text-transform:uppercase;
  color:var(--gold);text-decoration:none}

/* the restrained count on a team or match page */
.fr-count{font:700 9px/1 var(--disp);letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);text-decoration:none;border:1px solid var(--line2);
  border-radius:3px;padding:5px 9px;display:inline-block}
.fr-count.has{color:var(--gold);border-color:var(--gold)}

@media (max-width:560px){
  /* ⚠ RAPID CAPTURE ON A PHONE MEANS ONE COLUMN. Two side-by-side selects at
     390px leaves each ~170px, which is not a usable control while a match is
     going on. */
  .fr-row{grid-template-columns:1fr}
  .fr-bar{gap:8px}
  .fr-bar input[type=search]{flex:1 1 100%}
  .fr-actions{gap:9px}
  .fr-state{margin-left:0;flex:1 1 100%}
  .fr-entry{padding-left:11px}
}
.fr-export{margin:26px 0 0;padding:16px 0 0;border-top:1px solid var(--vx-rule)}
.fr-exwhy{margin:0 0 10px;font-size:12.5px;color:var(--ink3);max-width:60ch}
.fr-exrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.fr-state.good{color:var(--vx-power)}
.fr-state.warn{color:#F2B441}
.fr-rawwhy{margin:12px 0 6px;font-size:12.5px;color:var(--ink2)}
.fr-raw{width:100%;font:11.5px/1.5 var(--mono);color:var(--ink2);
  background:var(--alt);border:1px solid var(--line2);border-radius:3px;
  padding:9px 10px;resize:vertical}
@media (max-width:560px){
  .fr-exrow{gap:8px}
  .fr-exrow .fr-btn{flex:1 1 auto}
  .fr-state{flex:1 1 100%;margin-left:0}
}
.fr-import{margin:22px 0 0;padding:16px 0 0;border-top:1px solid var(--vx-rule)}
.fr-import .fr-raw{margin:10px 0 0}
.fr-btn.fr-danger{border-color:#8A3B3B;color:#FF9E9E}
.fr-btn.fr-danger:hover{border-color:#FF7A7A;color:#FF7A7A}
label.fr-btn{cursor:pointer;display:inline-block}
#frprev{margin:14px 0 0;border:1px solid var(--vx-rule);border-radius:4px;
  padding:14px 15px;background:var(--alt)}
.fr-prevhd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
  margin:0 0 11px}
.fr-prevhd b{font:700 13px/1 var(--disp);letter-spacing:.06em;
  text-transform:uppercase;color:var(--chalk)}
.fr-prevhd span{font:12px/1 var(--mono);color:var(--ink3)}
.fr-prevnums{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:10px;margin:0 0 12px}
.fr-prevnums>div{display:flex;flex-direction:column;gap:2px}
.fr-prevnums i{font-style:normal;font:700 9px/1.4 var(--disp);letter-spacing:.11em;
  text-transform:uppercase;color:var(--slate)}
.fr-prevnums b{font:700 20px/1 var(--disp);color:var(--ink2)}
.fr-prevnums b.fr-ok{color:var(--vx-power)}
.fr-prevnums b.fr-warn{color:#F2B441}
.fr-prevlist{margin:0 0 11px}
.fr-prevlist>i{font-style:normal;font:700 9px/1.4 var(--disp);letter-spacing:.11em;
  text-transform:uppercase;color:var(--slate)}
.fr-prevlist ul{list-style:none;margin:5px 0 0;padding:0;display:flex;
  flex-direction:column;gap:3px}
.fr-prevlist li{font-size:12.5px;color:var(--ink2);overflow-wrap:anywhere}
.fr-prevlist li i{font-style:normal;font:700 9px/1 var(--disp);letter-spacing:.09em;
  text-transform:uppercase;color:var(--slate);margin-right:7px}
.fr-prevlist li.more{color:var(--ink3)}
.fr-prevacts{display:flex;gap:9px;flex-wrap:wrap;align-items:center;
  margin:12px 0 0;padding:11px 0 0;border-top:1px solid var(--vx-rule)}
.fr-prevbad{display:flex;flex-direction:column;gap:6px}
.fr-prevbad b{font:700 13px/1 var(--disp);color:#FF9E9E;letter-spacing:.05em;
  text-transform:uppercase}
.fr-prevbad span{font-size:13px;color:var(--ink2)}
.fr-prevbad ul{margin:3px 0 0;padding-left:18px;color:var(--ink3);font-size:12px}
@media (max-width:560px){
  .fr-prevnums{grid-template-columns:1fr 1fr}
  .fr-prevacts .fr-btn{flex:1 1 100%}
}
/* FILMROOM-CSS-END */

/* MYBOARD-CSS-BEGIN */
/* ── MY BOARD ─────────────────────────────────────────────────────────────
   A pinned film strip inside the Match Desk, not a second dashboard. Compact
   ruled rows, one small private label, and it only exists when Cody has put
   something on it. */
.mbpanel{border-top:2px solid var(--gold);border-bottom:1px solid var(--line);
  padding:12px 0 10px;margin:6px 0 2px}
.mbhd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.mbhd b{font:700 11px/1 var(--disp);letter-spacing:.18em;text-transform:uppercase;
  color:var(--gold)}
.mbhd .mbpriv{font:600 9px/1 var(--disp);letter-spacing:.14em;
  text-transform:uppercase;color:var(--slate);border:1px solid var(--line2);
  border-radius:2px;padding:3px 5px}
.mbhd .mbn{font:11.5px/1 var(--mono);color:var(--slate)}
.mbhd .mbclear{margin-left:auto}
.mblane{margin-top:9px}
.mblane>i{display:block;font:600 9px/1 var(--disp);letter-spacing:.15em;
  text-transform:uppercase;color:var(--slate);font-style:normal;
  padding-bottom:5px;border-bottom:1px solid var(--line)}
.mbrow{display:grid;grid-template-columns:118px 1fr auto;align-items:center;
  gap:12px;padding:8px 2px;border-bottom:1px solid var(--line);width:100%;
  background:none;border-left:0;border-right:0;border-top:0;text-align:left;
  color:inherit;font:inherit;cursor:pointer}
.mbrow:hover{background:var(--sheet)}
.mbrow:last-child{border-bottom:0}
.mbrow .mbteam{display:flex;align-items:center;gap:7px;min-width:0}
.mbrow .mbteam img{width:20px;height:20px;flex:none;object-fit:contain}
.mbrow .mbteam b{font:600 14px/1.2 var(--disp);color:var(--chalk);
  overflow-wrap:anywhere}
.mbrow .mbwhat{font-size:12.5px;color:var(--ink2);min-width:0;line-height:1.5}
.mbrow .mbwhat em{font-style:normal;color:var(--slate)}
.mbrow .mbwhen{font:11px/1.5 var(--mono);color:var(--ink3);text-align:right}
.mbrow .mbsc{font:700 15px/1 var(--mono);color:var(--chalk)}
.mbrow .mbnone{color:var(--slate);font-style:italic}
.mbrow.mbgone{cursor:default;opacity:.85}
.mbrow.mbgone:hover{background:none}
/* an opened match is the destination; the board steps aside for it */
#v-desk.detailopen #mbpanel{display:none}
.rbside .mbslot{grid-column:3 / -1;justify-self:start;margin-top:4px}
/* the add/remove control, wherever a team is already named */
.mbbtn{appearance:none;background:transparent;border:1px solid var(--line2);
  border-radius:3px;color:var(--slate);font:600 9.5px/1 var(--disp);
  letter-spacing:.1em;text-transform:uppercase;padding:4px 7px;cursor:pointer;
  white-space:nowrap}
.mbbtn:hover{color:var(--chalk);border-color:var(--navy)}
.mbbtn[aria-pressed=true]{color:var(--gold);border-color:var(--gold)}
.mbwarn{font-size:12px;color:var(--slate);line-height:1.6;margin:6px 0 0}
@media (max-width:560px){
  .mbrow{grid-template-columns:1fr auto;gap:6px 10px}
  .mbrow .mbwhat{grid-column:1 / -1}
  .mbhd .mbclear{margin-left:0}
  /* ⚠ ADDING A BUTTON TO A BALLOT ROW WIDENED IT PAST THE PHONE. .bwctl is a
     fixed row of small controls; one more pushed the whole two-column grid to
     419px inside a 370px column. The control wraps to its own line there
     rather than the slot list scrolling sideways. */
  .bwctl{flex-wrap:wrap;row-gap:5px}
  .bwctl .mbbtn{flex:1 0 100%;text-align:center}
}
/* MYBOARD-CSS-END */
/* ══ THE MATCH BOARD ══════════════════════════════════════════════════════
   ONE signature surface: a broadcast scoreboard ribbon, used for the featured
   match and reused verbatim as the match-detail header so a score header has
   exactly one definition. Everything else on the board is a RULED ROW, not a
   card -- a fixture on a list is not independently actionable, so it does not
   get a box. No gradients, no pills, no glow: state is carried by weight,
   colour and a rule. */
.ribbon{border-top:2px solid var(--line2);border-bottom:1px solid var(--line);
  padding:16px 0 14px;margin:2px 0 6px}
/* ⚠ ONE FIRST-SCREEN BROADCAST MODULE (outside review, 2026-08-28: "the
   important line score begins below a large empty field"). The ribbon was
   two full-width team rows whose only number sat at the FAR right edge, with
   the reference table floating centered BELOW -- so the first screen spent
   ~350px saying very little. Now a two-column grid: team identities left,
   the reference table right, vertically centered across both team rows. The
   lone far-right tally is hidden when the table is present -- its S column
   already states it, and one fact should not render twice at two sizes. */
.ribbon.hasdls{display:grid;grid-template-columns:minmax(0,1fr) auto;
  column-gap:30px;align-items:center}
.ribbon.hasdls .rbtop{grid-column:1 / -1}
.ribbon.hasdls .dlswrap{grid-column:2;grid-row:2 / span 2;margin:0;
  justify-self:end;align-self:center}
.ribbon.hasdls .rbside{grid-column:1}
.ribbon.hasdls .rbsc{display:none}
@media (max-width:760px){
  .ribbon.hasdls{display:block}
  .ribbon.hasdls .dlswrap{margin:12px 0 2px}
}
.ribbon.live{border-top-color:var(--coral)}
.ribbon.final{border-top-color:var(--line2)}
.ribbon.upcoming{border-top-color:var(--navy)}
.rbtop{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.rbstate{font:700 9.5px/1 var(--disp);letter-spacing:.16em;text-transform:uppercase;
  padding:4px 8px;border:1px solid currentColor;border-radius:2px}
.rbstate.live{color:var(--coral)} .rbstate.final{color:var(--ink2)}
.rbstate.upcoming{color:var(--navy)}
.rbwhen{font:600 12px/1 var(--mono);color:var(--slate)}
.rbwhy{flex:1 1 100%;font:12.5px/1.5 var(--sans);color:var(--ink2);margin-top:2px}
.rbwhy b{color:var(--chalk);font-weight:600}
.rbside{display:grid;grid-template-columns:26px 34px 1fr auto;align-items:center;
  gap:12px;padding:7px 0}
.rbside+.rbside{border-top:1px solid var(--line)}
.rbside .rbrk{font:600 10px/1 var(--disp);color:var(--gold);text-align:right}
/* holds the crest column open when a team has no crest -- see the note in
   ribbonHTML: without it every cell in the row shifts one column left */
.rbside .rbnologo{display:block;width:34px;height:1px}
.rbside .rbnm{min-width:0;overflow-wrap:anywhere}
.rbside .rbnm{font:700 30px/1 var(--disp);letter-spacing:-.01em;color:var(--ink2);
  text-transform:uppercase}
.rbside.won .rbnm{color:var(--chalk)}
.rbside .rbsc{font:700 34px/1 var(--mono);color:var(--ink3);
  font-variant-numeric:tabular-nums}
.rbside.won .rbsc{color:var(--chalk)}
.ribbon.live .rbside .rbsc{color:var(--chalk)}
.rbside img{width:34px;height:34px;object-fit:contain}
/* the rally ledger: one cell per completed set */
/* the day view's lane heading carries which day it is about, quietly */
.dayhn{font:500 11px/1 var(--mono);color:var(--slate);letter-spacing:.05em;
  text-transform:none;margin-left:9px}
.dayhc{margin-left:auto;font:600 10px/1 var(--mono);color:var(--ink3)}
/* ── FIXTURE TRUTH ────────────────────────────────────────────────────── */
/* a fixture whose sources disagree says so instead of picking one */
.wconf{color:var(--gold);font:600 11.5px/1.4 var(--sans);
  border:1px dashed color-mix(in oklab,var(--gold) 55%,transparent);
  border-radius:2px;padding:2px 6px;white-space:nowrap}
/* a corrected fact names the school that confirmed it */
.wsrc{margin-left:8px;font:600 9.5px/1 var(--disp);letter-spacing:.11em;
  text-transform:uppercase;color:var(--good);text-decoration:none;
  border:1px solid color-mix(in oklab,var(--good) 45%,transparent);
  border-radius:2px;padding:3px 5px;white-space:nowrap}
.wsrc:hover{color:var(--chalk);border-color:var(--good)}
.wsrc:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:2px}
td.at{white-space:nowrap}
/* the scouting note, now BELOW the identity and compressed */
#teamcard .scoutread{margin:4px 0 18px}
#teamcard .scoutread p{margin:0 0 8px}
.scoutmore summary{cursor:pointer;font:600 11px/1 var(--disp);
  letter-spacing:.12em;text-transform:uppercase;color:var(--navy);
  padding:6px 0;list-style:none}
.scoutmore summary::-webkit-details-marker{display:none}
.scoutmore summary::before{content:"\25B8";display:inline-block;
  margin-right:6px;transition:transform .15s ease}
.scoutmore[open] summary::before{content:"\25BE"}
.scoutmore summary:hover{color:var(--chalk)}
.scoutmore summary:focus-visible{outline:2px solid var(--cs-cyan);
  outline-offset:2px}
.scoutmore p{margin:2px 0 0}
@media (prefers-reduced-motion:reduce){.scoutmore summary::before{transition:none}}
.daygrp .dayhd{display:flex;align-items:baseline;gap:0}
.lanemore{appearance:none;background:transparent;border:0;
  border-top:1px solid var(--line);width:100%;text-align:left;padding:9px 2px;
  color:var(--navy);font:600 12px/1 var(--sans);cursor:pointer}
.lanemore:hover{color:var(--chalk)}
.lanemore:focus-visible{outline:2px solid var(--cs-cyan);outline-offset:-2px}
.rledger{display:flex;gap:5px;margin-top:12px;flex-wrap:wrap}
.rledger .rl{min-width:46px;border:1px solid var(--line2);border-radius:2px;
  padding:5px 7px;text-align:center;font:600 12px/1.35 var(--mono);color:var(--ink2)}
.rledger .rl i{display:block;font:600 9px/1 var(--disp);letter-spacing:.12em;
  color:var(--slate);font-style:normal;margin-bottom:3px}
.rledger .rl.aw{color:var(--chalk)}
/* ── LANES ──────────────────────────────────────────────────────────────── */
.lane{margin:22px 0 0}
.lanehd{display:flex;align-items:baseline;gap:10px;padding-bottom:7px;
  border-bottom:2px solid var(--line2)}
.lanehd b{font:700 11px/1 var(--disp);letter-spacing:.18em;text-transform:uppercase}
.lane.live .lanehd b{color:var(--coral)}
.lane.final .lanehd b{color:var(--ink2)}
.lane.up .lanehd b{color:var(--navy)}
.lanehd span{font:11.5px/1 var(--mono);color:var(--slate)}
.lanemore{margin:9px 0 0;font-size:12.5px;color:var(--slate);line-height:1.6}
.lanemore a{color:var(--navy);text-decoration:none;border-bottom:1px solid var(--line2)}
.lanemore a:hover{border-bottom-color:var(--navy)}
/* a compact, scannable row -- deliberately NOT a miniature card */
/* ⚠ FOUR COLUMNS NOW: the line score sits in what was dead space. The
   team column is minmax(0,1fr) rather than 1fr so a long school name
   wraps instead of pushing the sets off the row. */
/* ⚠ THE TEAM COLUMN IS CAPPED, NOT 1fr. Left to flex it absorbed every
   spare pixel and pushed the line score to the far edge, ~830px from
   the names it belongs to. The context column takes the slack instead,
   which is what the space is actually for. */
.mrow{display:grid;
  grid-template-columns:64px minmax(210px,300px) auto minmax(0,1fr);
  align-items:center;
  gap:12px;padding:10px 2px;border-bottom:1px solid var(--line);cursor:pointer;
  background:none;border-left:0;border-right:0;border-top:0;width:100%;
  text-align:left;color:inherit;font:inherit}
.mrow:hover{background:var(--sheet)}
.mrow:last-child{border-bottom:0}
.mrow .mwhen{font:600 11px/1.4 var(--mono);color:var(--slate)}
.mrow .mteams{display:flex;flex-direction:column;gap:3px;min-width:0}
.mrow .mrt{display:flex;align-items:center;gap:7px;min-width:0}
.mrow .mrt img{width:19px;height:19px;flex:none;object-fit:contain}
.mrow .mrt b{font:600 15px/1.15 var(--disp);color:var(--ink2);overflow-wrap:anywhere}
.mrow .mrt.won b{color:var(--chalk)}
.mrow .mrt .mrk{font:600 9.5px/1 var(--disp);color:var(--gold);flex:none}

.mrow .msc{font:700 17px/1.2 var(--mono);color:var(--ink3);text-align:right;
  font-variant-numeric:tabular-nums}
.mrow .mrt.won .msc,.mrow.islive .msc{color:var(--chalk)}
.mrow .mmeta{display:flex;flex-direction:column;align-items:flex-end;gap:3px;
  min-width:0;overflow:hidden;text-align:right}
.mvn{font:11px/1.4 var(--sans);color:var(--slate);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:100%}
/* the two numerals stack so they line up with the two team rows above */
/* under a time heading the row's own clock is redundant; hiding it takes
   .mwhen out of grid flow, so the remaining four cells map to four
   columns and the row reclaims the width */
.tdlist.bytime .mrow{grid-template-columns:minmax(210px,300px) auto minmax(0,1fr)}
.tdlist.bytime .mrow .mwhen{display:none}
/* ⚠ A LIVE ROW'S "when" IS THE SET, NOT THE CLOCK -- hiding it under a time
   heading removed the one label that says where the match stands. Cody's
   desktop screenshot: live rows with no period anywhere. The clock is
   redundant under its heading; the period never is. */
.tdlist.bytime .mrow.islive{grid-template-columns:64px minmax(210px,300px) auto minmax(0,1fr)}
.tdlist.bytime .mrow.islive .mwhen{display:block}
/* ⚠ THE PHONE CARD MUST OUTRANK THE bytime DESKTOP TEMPLATES. Those two rules
   above are not media-scoped and carry three classes, so the 560px card
   template (one class, earlier in the sheet) lost everywhere inside a time
   group -- the teams area collapsed to 64px and every NAME vanished, leaving
   crest-and-points cards. Cody's phone would have shown a scoreboard with no
   teams on it. Same selectors, media-scoped, declared after. */
@media (max-width:560px){
  .mrow,.tdlist.bytime .mrow,.tdlist.bytime .mrow.islive{
    grid-template-columns:1fr;
    grid-template-areas:"when" "teams" "mls" "meta"}
  .tdlist.bytime .mrow .mwhen{display:none}
  .tdlist.bytime .mrow.islive .mwhen{display:block}
}
@media (max-width:560px){
  .tdlist.bytime .mrow{grid-template-columns:minmax(0,1fr) auto}
}
a.card.morecard{display:flex;flex-direction:column;justify-content:center;align-items:center;gap:3px;text-decoration:none;border-style:dashed}
a.card.morecard b{font:700 17px/1 var(--disp);color:var(--ink2)}
a.card.morecard span{font:11px/1 var(--sans);color:var(--slate)}
a.card.morecard:hover b{color:var(--chalk)}
h4.sbtime{display:flex;align-items:baseline;gap:8px;margin:16px 0 0;padding:0 2px 6px;border-bottom:1px solid var(--line);font:700 11px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase;color:var(--slate)}
h4.sbtime span{font:600 10px/1 var(--mono);color:var(--ink3)}
/* THE BOX: the set in progress, one live accent (Cody: "boxing things makes
   it cleaner"). Two stacked grid cells drawn as one box -- top cell carries
   the top and sides, bottom cell the bottom and sides. Larger numerals (they
   are the ones moving); the side ahead in the set reads gold; no winner-bold,
   because nobody has won a set still being played. */
.mlc.cur{font:700 15.5px/1.2 var(--mono);color:var(--chalk);
  border:1px solid color-mix(in oklab,var(--cs-gold) 55%,transparent);
  padding:1px 5px}
.mlc.cur.ca{border-bottom:0;border-radius:3px 3px 0 0}
.mlc.cur.ch{border-top:0;border-radius:0 0 3px 3px}
.mlc.cur.up{color:var(--cs-gold)}
/* THE LINESCORE GRID -- broadcast shape: one column per set, tally ruled off.
   Two rows in source order away-then-home, matching the names beside it. */
.mls{display:grid;
  grid-template-columns:repeat(var(--mlsn,0),minmax(25px,auto));
  justify-content:end;align-content:center;column-gap:1px;row-gap:4px}
.mls.hastally{grid-template-columns:auto repeat(var(--mlsn,0),minmax(25px,auto))}
.mlc{font:600 13.5px/1.2 var(--mono);color:var(--slate);text-align:center;
  padding:0 4px;font-variant-numeric:tabular-nums;font-style:normal}
.mlc.w{color:var(--chalk);font-weight:700}
.mlt{font:700 15px/1.1 var(--mono);color:var(--ink2);text-align:center;
  margin-right:9px;padding-right:11px;border-right:1px solid var(--cs-edge2);
  font-variant-numeric:tabular-nums}
.mlt.w{color:var(--chalk)}
/* THE DETAIL LINESCORE -- the reference table, drawn as a table */
.dlswrap{overflow-x:auto;margin:12px 0 2px}
/* width:auto beats the page-wide `table{width:100%}` -- the reference is
   a COMPACT centred table, not columns stretched across the viewport */
.dls{border-collapse:collapse;margin:0 auto;width:auto}
/* ⚠ position:static, or the page-wide sticky-th rule (the sticky-header
   saga's survivor) slides this header row DOWN over the away line -- it
   rendered BETWEEN the two teams, striped, and read as a defect. */
.dls th{position:static;font:700 11px/1 var(--disp);letter-spacing:.08em;color:var(--slate);
  padding:5px 0 7px;text-align:center;min-width:40px}
.dls td{font:600 16px/1.2 var(--mono);color:var(--slate);text-align:center;
  padding:8px 0;min-width:40px;font-variant-numeric:tabular-nums;
  border-top:1px solid var(--cs-edge)}
.dls td.w{color:var(--chalk);font-weight:700}
.dls .dtm{min-width:44px}
.dls .dtm img{width:22px;height:22px;object-fit:contain;vertical-align:middle}
.dls .dst{border-left:1px solid var(--cs-edge2);font-weight:700;
  color:var(--ink2);min-width:44px}
.dls td.dst.w{color:var(--chalk)}
/* the one live accent: the current column boxed, same as the rows */
.dls td.cur{font-weight:700;color:var(--chalk);
  border-left:1px solid color-mix(in oklab,var(--cs-gold) 55%,transparent);
  border-right:1px solid color-mix(in oklab,var(--cs-gold) 55%,transparent)}
.dls td.cur.ca{border-top:1px solid color-mix(in oklab,var(--cs-gold) 55%,transparent)}
.dls td.cur.ch{border-bottom:1px solid color-mix(in oklab,var(--cs-gold) 55%,transparent)}
.dls td.cur.up{color:var(--cs-gold)}
.dls th.ct{color:var(--cs-gold)}
.mrow .mctx{display:flex;flex-direction:column;gap:2px;min-width:0;overflow:hidden}
.mctxe{font:600 10.5px/1.3 var(--disp);letter-spacing:.04em;text-transform:uppercase;color:var(--gold);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

.mrow .mtags{display:flex;gap:5px;justify-content:flex-end;flex-wrap:wrap;
  margin-top:3px}
.mrow .mtg{font:600 9px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  color:var(--slate);border:1px solid var(--line);border-radius:2px;padding:3px 5px}
.mrow .mtg.rv{color:var(--gold);border-color:color-mix(in oklab,var(--gold) 40%,transparent)}
.mrow .mtg.lv{color:var(--coral);border-color:color-mix(in oklab,var(--coral) 45%,transparent)}
/* ⚠ A LIVE ROW ALREADY SAYS SO TWICE -- its eyebrow shows the set period and
   the whole row wears the live treatment -- so the LIVE chip was a third
   statement of one fact, on all twenty rows of a live lane at once (Cody's
   phone screenshot: LIVE + NEUTRAL right-aligned on every row, reading as
   noise). The chip stays in the DOM for anything that filters on it; it is
   hidden only where the row itself is already marked live. */
.mrow.islive .mtg.lv{display:none}
/* ── THE STATE CONTROL AND DAY GROUPS ON SCORES ─────────────────────────── */
.daygrp{margin:20px 0 0}
.dayhd{font:700 10.5px/1 var(--disp);letter-spacing:.17em;text-transform:uppercase;
  color:var(--slate);padding-bottom:6px;border-bottom:1px solid var(--line2)}
.emptylane{font:13px/1.6 var(--sans);color:var(--slate);padding:14px 0 2px;
  max-width:70ch}
/* ── MATCH DETAIL ───────────────────────────────────────────────────────── */
.mdet{margin-top:4px}
#v-scores.detailopen .hero,#v-scores.detailopen #changed,
#v-scores.detailopen .lead,#v-scores.detailopen .tabhint,
#v-desk.detailopen .vh,#v-desk.detailopen #desklead,
#v-desk.detailopen .livehead,#v-desk.detailopen #desksoon{display:none}
.mdet .msec{border-top:1px solid var(--line);padding:15px 0 6px;margin-top:14px}
.mdet .msec h3{margin:0 0 9px;font:600 10px/1 var(--disp);letter-spacing:.16em;
  text-transform:uppercase;color:var(--slate)}
.mdet .mfact{display:flex;flex-wrap:wrap;gap:8px 26px;font-size:13px;
  color:var(--ink2);line-height:1.65}
.mdet .mfact em{font-style:normal;color:var(--slate);margin-right:6px;
  font:600 9.5px/1 var(--disp);letter-spacing:.12em;text-transform:uppercase}
.mdet .munk{color:var(--slate);font-style:italic}
.lmcbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:4px}
.lmcbtn{appearance:none;background:transparent;border:1px solid var(--line2);
  border-radius:3px;color:var(--ink2);font:600 10.5px/1 var(--disp);
  letter-spacing:.1em;text-transform:uppercase;padding:7px 10px;cursor:pointer}
.lmcbtn:hover{color:var(--chalk);border-color:var(--navy)}
.lmcnote{font:11.5px/1.5 var(--mono);color:var(--slate)}
@media (max-width:560px){.lmcbar{gap:8px}.lmcnote{flex:1 1 100%}}
@media (max-width:560px){
  /* ⚠ THE CONTROL ROW COULD NOT WRAP. .seg is nowrap by design elsewhere, and
     four state buttons plus a count plus a date picker measured 535px inside a
     370px column -- clipped, with no scrollbar to reveal it. The date jump
     drops to its own line rather than the states scrolling out of reach. */
  #v-scores #ledgerwrap .seg{flex-wrap:wrap;row-gap:8px}
  /* the count reads "today - none - showing either side" and was clipped at
     the seg's right edge once the buttons wrapped; give it its own line */
  #v-scores #ledgercnt{flex:1 0 100%;margin:0;padding-top:2px}
  #v-scores .datejump{margin-left:0;flex:1 1 100%}
  .rbside{grid-template-columns:22px 26px 1fr auto;gap:8px}
  .rbside .rbnm{font-size:21px}
  .rbside .rbsc{font-size:26px}
  .rbside img{width:26px;height:26px}
  /* ⚠ A DEDICATED MATCH CARD, NOT A COMPRESSED DESKTOP ROW (design review
     via Cody, 2026-08-28). Same DOM, re-laid as a card:
       state row (period, small)
       away line:  crest  name .............. current points
       home line
       completed sets, small and dim, left-aligned under the names
     Venue and network stay in the match detail at this width. */
  .mrow{grid-template-columns:1fr;
    grid-template-areas:"when" "teams" "mls" "meta";
    gap:4px;padding:12px 2px}
  .mrow .mwhen{grid-area:when;display:none;font-size:10px}
  .mrow.islive .mwhen{display:block}
  .mrow .mteams{grid-area:teams}
  .mrow .mls{grid-area:mls;justify-content:start;margin-left:27px;row-gap:2px}
  /* venue and network as the card's quiet last line -- secondary, one line,
     ellipsized; the design review's sketch ends the card exactly this way */
  .mrow .mmeta{display:flex;grid-area:meta;align-items:center;gap:8px;
    margin-left:27px}
  .mrow .mvn{font:10.5px/1.3 var(--sans);color:var(--ink3)}
  .mlc{font-size:11.5px;padding:0 3px;color:var(--ink3)}
  .mlt{font-size:12.5px;margin-right:6px;padding-right:8px}
  .mrt .mcur{font-size:21px}
  .mrow .mrt{min-width:0}
  .mrow .mrt b.tn{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    overflow-wrap:normal}
  /* an upcoming match card: time left of the names on one line */
  .mrow:not(.islive) .mwhen{display:block;font-size:10px;color:var(--slate)}
  .mrow .mctx{display:none}
  .mrow .mrt b{font-size:14px}
  .mrow .msc{font-size:15px}
  .mdet .mfact{gap:6px 16px}
}

/* ── THE MORE MENU ────────────────────────────────────────────────────────
   Everything the twelve-tab strip could reach, one keystroke away. It is a
   real menu: Escape closes it, arrow keys move through it, focus returns to
   the button, and it is reachable by keyboard on a phone. */
.moreWrap{position:relative;display:inline-block}
.morebtn{appearance:none;background:transparent;border:0;color:var(--slate);
  font:600 12px/1 var(--disp);letter-spacing:.12em;text-transform:uppercase;
  padding:15px 13px;cursor:pointer;display:inline-flex;align-items:center;gap:5px;
  border-bottom:3px solid transparent}
.morebtn:hover,.morebtn[aria-expanded=true]{color:var(--ink)}
.moremenu .phoneonly{display:none}
@media (max-width:560px){.moremenu .phoneonly{display:block}}
.moremenu{position:absolute;top:100%;right:0;z-index:20;min-width:206px;
  background:var(--chrome2);border:1px solid var(--line2);border-radius:4px;
  padding:5px;box-shadow:0 18px 40px -18px rgba(0,0,0,.85)}
.moremenu button{display:block;width:100%;text-align:left;appearance:none;
  background:transparent;border:0;color:var(--ink2);font:600 13px/1 var(--sans);
  padding:10px 11px;border-radius:3px;cursor:pointer}
.moremenu button:hover,.moremenu button:focus-visible{background:var(--sheet2);
  color:var(--chalk)}
.moremenu button[aria-current=page]{color:var(--gold)}
@media (max-width:560px){
  .moremenu{right:auto;left:0;min-width:min(74vw,240px)}
}
/* ── BREADCRUMB AND RETURN PATH ───────────────────────────────────────────
   ⚠ THE ONLY ESCAPE USED TO BE "CLICK A TOP TAB AND HOPE". A detail page now
   says where it came from and offers the way back. */
.crumb{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 12px;
  font:12px/1.4 var(--sans);color:var(--slate)}
.crumb a{color:var(--ink2);text-decoration:none;border-bottom:1px solid var(--line2)}
.crumb a:hover{color:var(--chalk);border-bottom-color:var(--navy)}
.crumb .sep{opacity:.5}
.crumb b{color:var(--chalk);font-weight:600}
.backlink{display:inline-flex;align-items:center;gap:6px;appearance:none;
  background:transparent;border:1px solid var(--line2);border-radius:3px;
  color:var(--ink2);font:600 11.5px/1 var(--sans);padding:7px 10px;cursor:pointer;
  margin-bottom:14px}
.backlink:hover{color:var(--chalk);border-color:var(--navy)}
.parentlink{color:inherit;text-decoration:none;border-bottom:1px solid transparent}
.parentlink:hover{border-bottom-color:var(--navy)}

/* ── THE RALLY LINE ───────────────────────────────────────────────────────
   The single signature: a 1px court line that marks THE ACTIVE THING. It is a
   connection cue, never decoration, so it appears on exactly three surfaces --
   the featured match, a rank that moved, and the ballot row being edited.
   ⚠ IT NEVER GOES IN A TABLE AS TEXTURE. If it appeared on every row it would
   stop meaning "this one" and become a background. */
.rally{position:relative}
.rally::before{content:"";position:absolute;left:0;right:0;top:0;height:2px;
  background:linear-gradient(90deg,var(--navy) 0%,transparent 62%);
  opacity:.9}
.rally.gold::before{background:linear-gradient(90deg,var(--gold) 0%,transparent 62%)}
.rally.hot::before{background:linear-gradient(90deg,var(--coral) 0%,transparent 62%)}
/* one 350ms flash on a live score change, then it settles and stays still */
@keyframes rallyflash{0%{opacity:.25}35%{opacity:1}100%{opacity:.85}}
.rally.hot::before{animation:rallyflash 350ms ease-out 1}
@media (prefers-reduced-motion:reduce){
  .rally.hot::before{animation:none}
  *{scroll-behavior:auto!important}
}
/* a directional tick beside a rank change -- same ranking's prior state only */
.tick{font:600 10px/1 var(--disp);letter-spacing:.04em}
.tick.up{color:var(--good)} .tick.dn{color:var(--bad)} .tick.flat{color:var(--ink3)}

/* ══ MATCH DESK ═══════════════════════════════════════════════════════════
   Editorial, not a dashboard: a match is a headline with facts under it. No
   score badges, no gauges, no card-inside-a-card. The team names are the
   loudest thing, because that is what a reader is looking for. */
#v-desk .livehead{margin-top:6px}
.dsoonrest{font:12.5px/1.5 var(--sans);color:var(--ink2);margin:0 0 8px}
/* ── THE RUNDOWN ──────────────────────────────────────────────────────────
   One lead, then a board. The difference is carried by SCALE and RULE, not by
   a border round each item -- a card has to earn its box by being separately
   actionable, and a fixture on a list is not. */
.dlead{padding-top:14px;margin-bottom:6px}
.dlead .dcard{border-bottom:0;padding:4px 0 14px}
.dlead .dside b{font-size:34px;line-height:1.02}
.dlead .dwhen{font-size:13px;color:var(--ink2)}
.dlead .dfinal b{font-size:26px}
.dboard{border-top:1px solid var(--line)}
.dboard .dcard{padding:11px 2px 12px}
.dboard .dside b{font-size:18px}
.dboard .dtag{font-size:9px;padding:3px 6px}
.dboard .dwhy{display:none}          /* context is one line on a board row */
.dcard{border-bottom:1px solid var(--line2);padding:15px 2px 16px}
.dcard:last-child{border-bottom:0}
.dcard.islive{border-left:3px solid var(--live);padding-left:13px;
  background:linear-gradient(90deg,color-mix(in oklab,var(--live) 5%,transparent),transparent 55%)}
.dcard.isfinal{border-left:3px solid var(--line);padding-left:13px}
.dhead{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:9px}
.dwhen{font:600 12px/1 var(--mono);color:var(--ink2);letter-spacing:.02em}
.dtag{font:700 9.5px/1 var(--sans);letter-spacing:.1em;text-transform:uppercase;
  padding:4px 7px;border-radius:3px;border:1px solid var(--line2);color:var(--ink2)}
.dtag.rv{color:#F2B441;border-color:color-mix(in oklab,#F2B441 40%,transparent);
  background:color-mix(in oklab,#F2B441 10%,transparent)}
.dtag.rk{color:var(--navy);border-color:color-mix(in oklab,var(--navy) 40%,transparent)}
.dtag.cl{color:#31D07E;border-color:color-mix(in oklab,#31D07E 38%,transparent)}
.dtag.lv{color:#fff;background:var(--live);border-color:var(--live)}
.dtag.ev{text-transform:none;letter-spacing:.02em;font-size:10.5px}
.dteams{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.dside{display:flex;align-items:center;gap:7px;font:600 19px/1.15 var(--disp)}
.dside b{font-weight:600}
.dside.won b{color:var(--ink)}
.dside:not(.won) b{color:var(--ink)}
.dcard.isfinal .dside:not(.won) b{color:var(--ink2);font-weight:500}
.dat{font:600 11px/1 var(--sans);color:var(--ink3,var(--ink2));text-transform:uppercase;
  letter-spacing:.12em}
.dpow{font:700 9.5px/1 var(--mono);color:#31D07E;
  background:color-mix(in oklab,#31D07E 12%,transparent);padding:3px 5px;border-radius:3px}
.dfc{display:flex;align-items:baseline;gap:8px;margin-top:11px;
  font:13.5px/1 var(--sans);color:var(--ink)}
.dfc b{font:700 15px/1 var(--disp)}
.dfcl{font:700 9px/1 var(--sans);letter-spacing:.13em;text-transform:uppercase;
  color:var(--ink3,var(--ink2))}
.dfcs{font:11px/1 var(--mono);color:var(--ink3,var(--ink2));opacity:.75}
.dfc.none{color:var(--ink2);font-style:italic}
/* ⚠ A RELATIVE SIZE WITH NO FLOOR COMPOUNDS UNTIL IT IS UNREADABLE.
   This is .72em, and .62em in the compact contexts below, so inside an
   11px parent it resolved to 6.82px -- measured on the Today view at
   phone width, 27 instances of it. Nothing looked broken; the label just
   quietly shrank below legibility. max() keeps the proportional scaling
   where the parent is big enough and stops it where it is not. */
.rank-label{font-size:max(9.5px,.72em);letter-spacing:.06em;opacity:.72;margin-right:2px}
/* ⚠ THE RULER LABEL IS NEVER DECORATION AND MAY NEVER BE HIDDEN. It is the
   difference between a fact and a number. Anything that shrinks it has a floor
   of 9px; nothing may set it to display:none. Guarded in test_rulers.py. */
.rank-label{font-weight:700;text-transform:uppercase;white-space:nowrap}
.rnk{font-style:normal;white-space:nowrap}
/* the loud marker for a rank rendered with no ruler named -- it must be
   impossible to mistake for a real badge, and it must never reach a build */
.rnkbad{color:var(--bad);border:1px dashed var(--bad);padding:0 4px;
  font:700 10px/1.5 var(--mono);text-transform:uppercase}
/* the tape and the ribbon carry the label at their own scale */
.cs-trk .rank-label,.rbrk .rank-label,.mrk .rank-label{font-size:max(9px,.62em);
  opacity:.8;margin-right:1px;display:inline}
.cs-trk .rnk,.rbrk .rnk,.mrk .rnk{color:inherit}
.dlive{margin-top:11px;display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.dopen{margin-left:auto;font:600 10px/1 var(--disp);letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink2);background:transparent;
  border:1px solid var(--line);border-radius:3px;padding:5px 9px;cursor:pointer}
.dopen:hover{color:var(--ink);border-color:var(--ink2)}
.lmc{margin-top:10px;border-top:1px solid var(--line);padding-top:10px}
.lmc .lhd{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;
  font:600 10px/1.3 var(--disp);letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink2)}
.lmc .lhd .ldot{width:6px;height:6px;border-radius:50%;background:#e0553f;
  display:inline-block}
.lmc .lnote{margin:7px 0 0;font-size:12.5px;color:var(--ink2);line-height:1.5}
.lmc table{width:100%;max-width:520px;border-collapse:collapse;margin-top:9px}
.lmc th,.lmc td{padding-left:10px}
.lmc th{font:600 9.5px/1 var(--disp);letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink3);text-align:right;padding:0 0 6px}
.lmc th:first-child{text-align:left}
.lmc td{padding:5px 0;font-size:13px;text-align:right;
  border-top:1px solid var(--line)}
.lmc td:first-child{text-align:left;font:600 14px/1.2 var(--disp)}
.lmc .lmcldr{margin-top:9px;font-size:12.5px;color:var(--ink2);line-height:1.6}
.lmc .lmcldr b{color:var(--ink);font-weight:600}
@media (max-width:560px){
  .lmc th,.lmc td{font-size:12px}
  .lmc td:first-child{font-size:13px}
  .dopen{margin-left:0;margin-top:6px}
}
.dlv{font:700 9px/1 var(--sans);letter-spacing:.13em;color:#fff;background:var(--live);
  padding:4px 6px;border-radius:3px}
.dlive b{font:700 16px/1 var(--disp)}
.dper{font:11px/1 var(--mono);color:var(--ink2)}
.dsrc{flex:1 1 100%;font:11px/1.4 var(--mono);color:var(--ink3,var(--ink2));opacity:.8}
.dsets{display:flex;gap:5px;flex:1 1 100%;margin-top:6px}
.dsets span{font:600 11.5px/1 var(--mono);color:var(--ink2);
  border:1px solid var(--line2);border-radius:3px;padding:3px 6px}
.dstory{margin-top:11px}
.dfinal{display:flex;align-items:baseline;gap:8px;font:15px/1 var(--sans)}
.dfl{font:700 9px/1 var(--sans);letter-spacing:.13em;color:var(--ink3,var(--ink2))}
.dfinal b{font:700 17px/1 var(--disp);color:var(--ink)}
.dsaid{margin:8px 0 0;font:13px/1.55 var(--sans);color:var(--ink2)}
.dsaid b{color:#F2B441}
.dsaid.none{font-style:italic}
.dwhere{margin-top:9px;font:12px/1.4 var(--mono);color:var(--ink2)}
.dwhere .wc{margin-left:6px;opacity:.75}
.dwhere .wu{font-style:italic;opacity:.7}
.dwhy{margin:11px 0 0;padding-left:16px}
.dwhy li{font:12.5px/1.6 var(--sans);color:var(--ink2);margin-bottom:2px}
.dempty{font:13px/1.6 var(--sans);color:var(--ink2);padding:10px 0}
#desksoon{margin-top:26px}
@media (max-width:560px){
  /* deliberate cards, not a squeezed table: the matchup stacks and every
     supporting fact sits under it at a readable size */
  .dcard{padding:13px 0 14px}
  .dcard.islive,.dcard.isfinal{padding-left:11px}
  .dteams{flex-direction:column;align-items:flex-start;gap:4px}
  .dside{font-size:18px}
  .dat{margin-left:2px}
  .dhead{gap:6px}
  .dfc{flex-wrap:wrap;gap:6px}
  .dfcs{flex:1 1 100%}
  .dsets{flex-wrap:wrap}
  .dwhy{padding-left:15px}
}



/* ── WHAT CHANGED ────────────────────────────────────────────────────────
   Editorial rather than another row of cards: a result reads as a sentence --
   winner, score, loser -- with the ranked ones marked. */
.livehead b.chg{color:#F2B441}
.chgrow{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}
.chgc{display:flex;align-items:center;gap:9px;padding:9px 13px;
  border:1px solid var(--line2);border-radius:4px;background:var(--card);
  font:14px/1 var(--sans)}
.chgc.mk{border-color:color-mix(in oklab,#F2B441 45%,var(--line2));
  background:linear-gradient(180deg,color-mix(in oklab,#F2B441 7%,var(--card)),var(--card))}
.chgc .w{font-weight:700;color:var(--ink);display:flex;align-items:center;gap:5px}
.chgc .l{color:var(--ink2);display:flex;align-items:center;gap:5px}
.chgc .sc{font:700 15px/1 var(--disp);color:var(--ink);letter-spacing:.02em}
.chgc .pwr{font:700 10px/1 var(--mono);font-style:normal;color:#31D07E;
  padding:2px 4px;border-radius:3px;
  background:color-mix(in oklab,#31D07E 14%,transparent)}
@media (max-width:560px){
  .chgrow{flex-direction:column;gap:6px}
  .chgc{width:100%;justify-content:space-between}
}


@media (max-width:560px){
  .chips.tier1 .chip{font-size:12.5px;padding:6px 10px}
  .chips.tier1 .chip b{font-size:15px}
}


.t25 td.poll i{font:700 10.5px/1 var(--mono);font-style:normal;margin-left:4px;
  padding:1px 3px;border-radius:3px}
.t25 td.poll .pgup{color:#31D07E;background:color-mix(in oklab,#31D07E 14%,transparent)}
.t25 td.poll .pgdn{color:#FF6B6B;background:color-mix(in oklab,#FF6B6B 14%,transparent)}
.t25 td.poll .pg0{color:var(--ink2)}
.t25 td.poll .nr{font:600 11px/1 var(--mono);color:var(--ink3,var(--ink2));opacity:.65}
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
.bgame{background:var(--card);border:1px solid var(--line);border-radius:4px;
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
.bcbox{background:var(--card);border:1px solid var(--line2);border-radius:4px;
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
  object-position:50% 12%;border-radius:4px;border:1px solid var(--line2);
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
tr.tvearlier td{padding:6px 0 10px;border:0}
#tvpastbtn{appearance:none;background:none;border:1px dashed var(--line2);
  border-radius:4px;color:var(--slate);cursor:pointer;padding:6px 11px;
  font:700 10px/1 var(--disp);letter-spacing:.09em;text-transform:uppercase}
#tvpastbtn:hover{color:var(--chalk);border-color:var(--cs-edge2)}
.cstrip{padding:6px 15px 4px}
/* the head mirrors .crow's grid so the labels land over their columns */
/* ⚠ THE SAME TRACK LIST AS .crow, or the labels sit over the wrong
   columns -- 118px name, 1fr track, 34px median, 26px count. */
.chead{display:grid;grid-template-columns:118px 1fr 34px 26px;gap:10px;
  align-items:end;padding:0 15px 4px;
  font:700 9px/1 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink3)}
.chead .chlab{grid-column:3 / span 2;text-align:right;white-space:nowrap}

.crow{display:grid;grid-template-columns:118px 1fr 34px 26px;gap:10px;
  align-items:center;padding:5px 0;border-bottom:1px solid var(--line)}
.crow:last-child{border-bottom:0}
.cnm{font:600 11.5px/1.2 var(--sans);color:var(--ink2);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctrack{position:relative;height:14px;border-radius:4px;
  background:linear-gradient(90deg,rgba(63,146,222,.16),rgba(63,146,222,.03));min-width:0}
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
/* ⚠ A FIXED 30px COLUMN CLIPPED THE VALUE IT EXISTS TO SHOW. The median rank
   runs to five characters once a conference sits past 100 -- "149.5", "176.5",
   "192.5" -- and at 11.5px mono that needs 35px. Seven conferences rendered a
   TRUNCATED number on a phone: correct data, displayed as something else.
   Sized to its content now, so a wider value can never be cut again. */
@media (max-width:560px){.crow{grid-template-columns:82px 1fr auto 22px}}
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
.band{position:relative;height:14px;border-radius:4px;
  background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.02));
  border:1px solid var(--line)}
.bandfill{position:absolute;top:1px;bottom:1px;border-radius:4px;
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
  margin:12px 0 0;padding:9px 14px;border-radius:4px;
  background:linear-gradient(90deg,rgba(120,180,255,.10),rgba(120,180,255,.02));
  border-left:3px solid var(--amber)}
.coachline .cl{font:700 9.5px/1 var(--mono);letter-spacing:.18em;
  text-transform:uppercase;color:var(--ink3)}
.coachline b{font:600 16px/1.2 var(--disp);color:var(--ink);letter-spacing:.01em}
.coachline .ct{font:11.5px/1.3 var(--mono);color:var(--ink3)}
/* the week's headline matches: a ranked-v-ranked card earns the ball's yellow */
.card.marquee{border-left:3px solid var(--amber)}
.card.marquee .cd .tag{margin-left:8px}
#weekcards .card{border-style:solid}
/* ⚠ auto-fit, NOT repeat(4,1fr). The strip is not always four tiles: the
   dossier removes "Next" because its Overview card says the same thing
   with more in it, and a hard-coded four then left a dead quarter-width
   column on every team page. auto-fit collapses the unfilled track and
   the survivors take the space, so the strip is correct at three or at
   four without either count being written down. */
.glance{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:14px 0 18px}
.gl{padding:13px 15px;border-radius:4px;border:1px solid transparent;
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
h3 .cnt{margin-left:8px;padding:2px 7px;border-radius:4px;
  background:rgba(120,180,255,.14);color:var(--ink2);
  font:700 10px/1.5 var(--mono)}
.moreb{display:block;width:calc(100% - 30px);margin:2px 15px 12px;padding:9px;
  border-radius:4px;border:1px solid var(--line2);cursor:pointer;
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
.hero{position:relative;overflow:hidden;border-radius:4px;margin:0 0 20px;
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
  border-radius:4px;
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
  gap:3px;min-width:116px;padding:14px 14px 12px;border-radius:4px;
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
/* ⚠ THE HERO WAS BROKEN AT 390px AND THIS RULE WAS WHY IT LOOKED HANDLED.
   It set .heroR to full width but never touched grid-template-columns, so the
   grid stayed `1fr auto` -- and with the podium demanding its natural width in
   a 358px box the LEFT column collapsed to ZERO. Measured: `0px 292px`. The
   masthead then wrapped to one word per line and printed straight through the
   podium cards.
   A two-column grid cannot become one column by resizing a child; the template
   itself has to change. Stack it. */
@media (max-width:560px){
  .hero{grid-template-columns:1fr;grid-template-rows:auto auto auto;
    padding:20px 18px;gap:16px}
  .heroL{grid-column:1;grid-row:1;min-width:0}
  .heroR{grid-column:1;grid-row:2;width:100%}
  /* the decorative court is clipped to a floating net fragment at this width
     and costs vertical space the live scores need -- drop it, keep the type */
  .courtwrap{display:none}
  .hero h1,.hero .htitle{font-size:30px;line-height:1.02}
  .pod{flex:1 1 0;min-width:0}
  .pod b,.pod .podv{font-size:15px}
}
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
/* an exhibition is the one badge here that changes what a result MEANS,
   so it is the one that is outlined rather than filled */
.kind.exh{background:transparent;color:var(--gold);border:1px solid color-mix(in oklab,var(--gold) 45%,transparent)}
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
  border-radius:4px;padding:4px 8px;margin-left:8px;vertical-align:2px;
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
  border-radius:4px;padding:3px 7px}
.rrow{display:grid;grid-template-columns:1fr auto;grid-template-areas:
  "av stat" "meta stat";align-items:center;gap:0 10px;
  padding:7px 9px 7px 6px;border-left:3px solid transparent;
  border-bottom:1px solid var(--line);transition:background .12s ease}
.rrow:last-child{border-bottom:0}
/* ⚠ THE SAME min-width:auto FLOOR AS THE BALLOT'S TWO-COLUMN GRID, on a
   different grid. A 1fr
   column cannot shrink below its content unless told it may, so a long
   player name held the roster 96px wider than a 390px phone -- clipped inside
   the cell, with no sideways scrollbar to reveal it. Pre-existing; measured at
   466/368 before this pass and fixed here because the team page is one of the
   surfaces this visual system has to carry. */
.rrow>*{min-width:0}
.rrow .nm,.rrow .meta{overflow-wrap:anywhere}
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
/* A form pill for a result the Division-I record excludes. Outlined, not
   filled, and carrying its own two-and-a-bit characters of text -- so it reads
   as "this happened but is not counted" at a glance and on a phone, where no
   hover exists. The suffix is deliberately not an icon: an icon would need the
   very tooltip this replaces. */
/* ⚠ .fw/.fl IS A FIXED 19x19 BOX. Appending the suffix inside it overflowed
   the pill -- measured at a 358px phone width, scrollWidth beyond clientWidth
   -- so the marked pill is given its own auto width. Height and line-height
   are kept at 19px so it still sits on the same baseline as the pills beside
   it; only the width grows. */
.fw.fnd,.fl.fnd{width:auto;min-width:19px;padding:0 4px;
  background:transparent;border:1px dashed currentColor}
.fndt{font-style:normal;font-weight:700;font-size:9px;letter-spacing:.03em;
  margin-left:3px;opacity:.9}
@media (max-width:560px){.fw.fnd,.fl.fnd{padding:0 3px}
  .fndt{font-size:9px;margin-left:2px}}



/* ---- WEEKLY RANKING CALENDAR ----------------------------------------------
   Three tracks that must never look like one table. Each carries a tag saying
   what KIND of ranking it is -- Derived (ours), Official (the coaches poll),
   Community (a forum poll, entered by hand) -- because the cadence and the
   authority are
   different for each and a reader deciding a ballot needs to know which is
   which before reading a single number. */
.calwrap{max-width:960px}
.calnow{border:1px solid var(--line2);border-left:3px solid var(--slate);
  border-radius:4px;padding:13px 15px;margin:0 0 20px;background:var(--alt)}
.calnow.wait{border-left-color:#F2B441}
.calnow.ok{border-left-color:#31D07E}
.calnowhead{display:flex;align-items:center;gap:9px;flex-wrap:wrap;
  margin-bottom:7px}
.calnowhead b{font:700 17px/1.2 var(--disp);color:var(--chalk)}
.calnow p{margin:0 0 6px;font-size:13px;color:var(--ink2);line-height:1.55}
.calnow p:last-child{margin-bottom:0}
.calfine{font-size:12px;color:var(--ink3)}
.caltag{font:700 9px/1.5 var(--disp);letter-spacing:.1em;text-transform:uppercase;
  padding:3px 7px;border-radius:3px;white-space:nowrap}
.caltag.derived{color:#8FD3FF;background:rgba(91,168,245,.14)}
.caltag.official{color:#FFD98A;background:rgba(242,180,65,.14)}
.caltag.community{color:var(--ink3);background:var(--line)}
.caltrack{margin:0 0 24px}
.calhead{display:flex;align-items:center;gap:10px;margin:0 0 9px}
.calhead h3{margin:0;font:700 13px/1 var(--disp);letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink2)}
.caltbl th{font:700 9px/1.4 var(--disp);letter-spacing:.08em;
  text-transform:uppercase;color:var(--slate);text-align:left;white-space:nowrap}
.caltbl td{font-size:13px;vertical-align:top}
.caltbl td:first-child{font-weight:600;color:var(--chalk)}
.calstate{font:700 9px/1.5 var(--mono);letter-spacing:.03em;padding:2px 6px;
  border-radius:3px;white-space:nowrap;background:var(--line);color:var(--ink3)}
.calstate.complete{color:#31D07E;background:rgba(49,208,126,.12)}
.calstate.forced{color:#F2B441;background:rgba(242,180,65,.12)}
.calwarn{font:700 9px/1.4 var(--mono);letter-spacing:.03em;color:#F2B441;
  background:rgba(242,180,65,.12);padding:1px 5px;border-radius:3px;
  margin-left:5px}
.caltbl .dim{color:var(--ink3)}




/* a result row that opens its match */
.gline.gopen{cursor:pointer;border-radius:3px}
.gline.gopen:hover{background:rgba(91,168,245,.06)}
.gline.gopen:focus-visible{outline:2px solid var(--gold);outline-offset:-2px}



/* the ruler key on the selector itself: the swatch answers "whose ranking is
   this" before the label is read */
.seg .segb .vx-key{margin-right:7px}
.seg .segb{display:inline-flex;align-items:center}
/* and the underline of the ACTIVE ruler takes its colour */
.seg .segb.on[data-r="ours"]{box-shadow:inset 0 -2px 0 var(--vx-power)}
.seg .segb.on[data-r="avca"]{box-shadow:inset 0 -2px 0 var(--vx-avca)}
.seg .segb.on[data-r="digby"]{box-shadow:inset 0 -2px 0 var(--vx-digby)}
/* the calendar tags use the same four colours, so a track and a ruler that
   mean the same thing look the same */
.caltag.derived{color:var(--vx-digby);background:var(--vx-digby-dim)}
.caltag.official{color:var(--vx-avca);background:var(--vx-avca-dim)}


/* ── Digby's Top 25: an editorial list, not a dense table ──────────────── */
/* ⚠ THE RANK IS THE POINT OF A TOP 25, so it is sized like one. Everything
   else recedes: the crest and name carry identity, the record and form carry
   evidence, and the amber edge marks the ruler this list belongs to. */
/* ⚠ A PRE-EXISTING PODIUM RULE WAS WINNING ON SPECIFICITY, AND ONLY FOR THE
   TOP THREE. `tbody tr:nth-child(1..3) td.rk{font-size:19px}` (search "THE TOP
   THREE LOOK LIKE THE TOP THREE") is UNSCOPED -- written for the 348-row
   rankings board, where shrinking #1..#3 to 19px from a 14px base is an
   ENLARGEMENT. It reaches into every tbody on the site, so in the Top 25,
   whose base is 26px, it was a REDUCTION: ranks 1-3 rendered 19px beside
   26px for 4-25. Measured on the live page before this fix.

   Specificity, which is the whole bug: the podium rule is (0,2,3) -- two
   class-likes (.rk, :nth-child) and three elements -- while `.t25 .rk` is
   only (0,2,0). Adding `table` and the intermediate elements makes this
   (0,2,4), which wins on element count without `!important` and without
   touching any other table. The podium rule still applies to the rankings
   board, the leaders tables and the bracket seeds exactly as before -- all
   four use `td.rk`, so scoping IT would have changed three surfaces to fix
   one. */
table.t25 tbody tr td.rk{padding-right:10px;font:700 26px/1 var(--disp);
  color:var(--vx-digby);font-variant-numeric:tabular-nums;text-align:right;
  width:58px}
/* The podium idea is kept, in the direction it was meant to go: the top three
   are LARGER here, never smaller. */
table.t25 tbody tr:nth-child(-n+3) td.rk{font-size:30px}
.t25 tbody tr{border-left:3px solid transparent}
.t25 tbody tr:hover{background:rgba(233,169,61,.05)}
.t25 tbody tr td:first-child{position:relative}
.t25 tbody tr td:first-child::before{content:"";position:absolute;left:0;top:6px;
  bottom:6px;width:3px;background:var(--tc,transparent);border-radius:2px}
.t25 td{padding:11px 14px}
.t25 th{color:var(--slate);font-weight:700}

/* ── section labels: a rule with a name on it, replacing the gradient bar ─ */
/* The old heading was a gradient strip on every section, which made twelve
   sections look like twelve equally important things. A hairline rule and a
   small caps label give the same structure without the shouting. */
.tsec h3{margin:0;padding:11px 15px 9px;font:700 10px/1 var(--disp);
  letter-spacing:.16em;text-transform:uppercase;color:var(--slate);
  background:none;border-bottom:1px solid var(--vx-rule);position:relative}
.tsec h3 .cnt,.tsec h3 .h3n{color:var(--ink3)}

@media (max-width:560px){
  /* raised to match the desktop rule above, or the 26px would win here */
  table.t25 tbody tr td.rk{font-size:20px;width:42px;padding-right:7px}
  table.t25 tbody tr:nth-child(-n+3) td.rk{font-size:23px}
  .t25 td{padding:9px 8px}
}


@media (max-width:560px){
  /* ⚠ FIVE RULER BUTTONS PLUS SWATCHES DO NOT FIT 390px. Measured: `.seg`
     overflowed its section. It wraps rather than scrolling sideways -- a
     horizontal scroller hides the last ruler behind a gesture nobody knows is
     there, and the whole point of the key is that all of them are visible. */
  .rulerbar{align-items:flex-start}
  .seg{display:flex;flex-wrap:wrap;gap:6px;width:100%}
  .seg .segb{flex:0 1 auto}
  /* ⚠ TWO ROSTER COLUMNS IN 358px GIVES 168px EACH, and a name plus a rate
     does not fit -- the block measured 386px against a 358px box. One column
     on a phone. */
  .rbody{column-count:1}
}

/* ═══ VISUAL SYSTEM ═══════════════════════════════════════════════════════
   Broadcast graphics + scouting notebook. Everything new lives under `vx-`,
   a namespace verified free against all 868 existing class names
   (scripts/css_names.py) -- eight silent collisions in this file are eight
   too many.

   THE RULER KEY. Four rankings answer four different questions, and a reader
   should know which one they are looking at before reading a word. One colour
   each, used identically on the rankings tab, the calendar, a team page and
   the ballot desk -- never decorative, always the same meaning:

     POWER      amber   ours, predictive
     AVCA       blue    theirs, official
     DIGBY 25   green   ours, editorial
     MY BALLOT  violet  mine, a judgement

   Team colour is a LOCAL identity signal -- a 3px edge on a row that belongs
   to one team -- never a page theme. 348 schools cannot each own the page. */
:root{
  /* ⚠ THE KEY ADOPTS THE COLOURS THIS SITE ALREADY USES rather than imposing
     new ones. POWER has been green since the rating shipped -- `b.kpow`,
     `.bwv.pw` and, decisively, the green sequential heat scale on the POWER
     column itself. Making the label amber while the column stayed green would
     have been a fresh inconsistency introduced by the very system meant to
     remove them. Digby's Top 25 takes the amber instead: it is ours and it is
     the editorial one. */
  --vx-power:#31D07E;   --vx-power-dim:rgba(49,208,126,.14);
  --vx-avca:#7AA7FF;    --vx-avca-dim:rgba(122,167,255,.14);
  --vx-digby:#E9A93D;   --vx-digby-dim:rgba(233,169,61,.14);
  --vx-ballot:#A98BE8;  --vx-ballot-dim:rgba(169,139,232,.14);
  --vx-rule:rgba(255,255,255,.10);
  --vx-rule-strong:rgba(255,255,255,.20);
}

/* ── section label: a rule line with a name on it ──────────────────────── */
.vx-label{display:flex;align-items:center;gap:10px;margin:0 0 10px;
  font:700 10px/1 var(--disp);letter-spacing:.16em;text-transform:uppercase;
  color:var(--slate)}
.vx-label::after{content:"";flex:1;height:1px;background:var(--vx-rule)}
.vx-label b{font-weight:700;color:var(--chalk);letter-spacing:.16em}
.vx-label .vx-key{width:8px;height:8px;border-radius:1px;flex:0 0 8px}

/* the key swatch, wherever a ruler is named */
.vx-key{display:inline-block;width:8px;height:8px;border-radius:1px;
  vertical-align:middle;padding:0;border:0;flex:0 0 8px}
/* ⚠ THE MODIFIERS ARE NAMESPACED TOO, AND THAT WAS NOT PARANOIA. The first
   version wrote `.vx-key.digby` -- and `.digby` is an EXISTING block style
   with its own background, border and 12px padding, so the Digby swatch
   inherited it and rendered 32x26px beside two 8x8 squares. I had checked the
   `vx-` prefix and not the modifier. All four of `power`, `avca`, `digby` and
   `ballot` were already taken. Collision number nine, caught by the tool
   written for this phase (scripts/css_names.py). */
.vx-key.vx-k-power{background:var(--vx-power)}
.vx-key.vx-k-avca{background:var(--vx-avca)}
.vx-key.vx-k-digby{background:var(--vx-digby)}
.vx-key.vx-k-ballot{background:var(--vx-ballot)}


/* ── fact strip: label over value, in a row, no chips ──────────────────── */
.vx-facts{display:flex;flex-wrap:wrap;gap:2px 26px;margin:0}
.vx-facts>div{display:flex;flex-direction:column;gap:2px;min-width:0}
.vx-facts i{font-style:normal;font:700 9px/1.4 var(--disp);
  letter-spacing:.12em;text-transform:uppercase;color:var(--slate)}
.vx-facts b{font:700 15px/1.15 var(--disp);color:var(--chalk);
  overflow-wrap:anywhere}
.vx-facts b.sm{font-size:13px;font-weight:600;color:var(--ink2)}

/* ── team identity row: crest, name, and that team's own colour ────────── */
.vx-idrow{display:grid;grid-template-columns:3px 30px minmax(0,1fr) auto;
  align-items:center;gap:11px;padding:7px 0}
.vx-idrow .vx-edge{width:3px;height:26px;border-radius:2px;
  background:var(--tc,var(--line2))}
.vx-idrow .vx-crest{width:30px;height:30px;display:flex;align-items:center;
  justify-content:center}
.vx-idrow .vx-crest img{max-width:30px;max-height:30px}
.vx-idrow .vx-nm{font:700 17px/1.1 var(--disp);color:var(--chalk);
  min-width:0;overflow-wrap:anywhere}

/* ── empty state: a deliberate page, not a blank one ───────────────────── */
.vx-empty{border:1px solid var(--vx-rule);border-radius:5px;
  padding:26px 24px;text-align:center;background:var(--alt)}
.vx-empty h4{margin:0 0 6px;font:700 17px/1.2 var(--disp);color:var(--chalk);
  letter-spacing:.01em}
.vx-empty p{margin:0 auto 14px;max-width:52ch;font-size:13px;color:var(--ink2);
  line-height:1.55}
.vx-empty .vx-emptyacts{display:flex;gap:10px;justify-content:center;
  flex-wrap:wrap}
.vx-empty a{font:700 10px/1 var(--disp);letter-spacing:.1em;
  text-transform:uppercase;color:var(--chalk);text-decoration:none;
  border:1px solid var(--vx-rule-strong);border-radius:3px;padding:9px 13px}
.vx-empty a:hover{border-color:var(--gold);color:var(--gold)}

/* ── today's read: one line per fact, rule-separated, no cards ─────────── */
.vx-read{display:flex;flex-direction:column;border-top:1px solid var(--vx-rule);
  border-bottom:1px solid var(--vx-rule);margin:0 0 20px}
.vx-read .vx-readrow{display:grid;grid-template-columns:104px minmax(0,1fr);
  gap:14px;align-items:baseline;padding:9px 0}
.vx-read .vx-readrow+.vx-readrow{border-top:1px solid var(--vx-rule)}
.vx-read i{font-style:normal;font:700 9px/1.5 var(--disp);letter-spacing:.12em;
  text-transform:uppercase;color:var(--slate)}
.vx-read .vx-readv{font-size:13.5px;color:var(--ink2);min-width:0}
.vx-read .vx-readv b{color:var(--chalk);font-weight:700}
.vx-read a.vx-readv{text-decoration:none}
.vx-read a.vx-readv:hover b{color:var(--gold)}

@media (max-width:560px){
  .vx-read .vx-readrow{grid-template-columns:1fr;gap:2px;padding:8px 0}
  .vx-facts{gap:2px 18px}
  .vx-facts b{font-size:14px}
  .vx-empty{padding:20px 16px}
  .vx-idrow{grid-template-columns:3px 26px minmax(0,1fr) auto;gap:9px}
  .vx-idrow .vx-crest{width:26px;height:26px}
  .vx-idrow .vx-crest img{max-width:26px;max-height:26px}
  .vx-idrow .vx-nm{font-size:15px}
}

/* ⚠ MOTION ONLY WHERE IT REPORTS STATE. One pulse, on the live dot, because
   "this is happening now" is the single thing on this page that changes
   without the reader acting. Everything else is static on purpose. */
@keyframes vxpulse{0%,100%{opacity:1}50%{opacity:.35}}
.vx-livedot{display:inline-block;width:7px;height:7px;border-radius:50%;
  background:#FF5A5A;margin-right:6px;animation:vxpulse 1.8s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){
  .vx-livedot{animation:none}
}

/* the honest "not yet" state, where a table would otherwise be */
.mpend{display:flex;flex-direction:column;gap:4px;padding:12px 14px;
  border:1px dashed var(--line2);border-radius:4px;background:var(--alt)}
.mpend b{font:700 12px/1 var(--disp);letter-spacing:.08em;text-transform:uppercase;
  color:var(--chalk)}
.mpend span{font-size:12.5px;color:var(--ink2)}
.mpend .mfine{font-size:12px;color:var(--ink3)}
.msrc{margin:10px 0 0;font-size:11.5px;color:var(--ink3)}

/* the active week's counts, read at a glance */
.calcounts{display:flex;flex-wrap:wrap;gap:6px 18px;margin:2px 0 10px;
  font-size:12.5px;color:var(--ink2)}
.calcounts b{font:700 15px/1 var(--disp);color:var(--chalk);margin-right:4px}
.calcounts .bad b{color:#F2B441}
.calnow.okw{border-left-color:#8FD3FF}
.calblock{list-style:none;margin:0 0 10px;padding:0;display:flex;
  flex-direction:column;gap:5px}
.calblock li{display:flex;align-items:center;gap:7px;flex-wrap:wrap;
  font-size:12px;color:var(--ink2)}
.calblock b{font:700 12px/1 var(--mono);color:var(--chalk)}
.calblock i{font-style:normal;font-size:11px;color:var(--ink3);
  background:var(--line);padding:1px 6px;border-radius:3px;white-space:nowrap}
.calblock i.more{background:none;padding-left:0}
.calwhy{font:700 9px/1.5 var(--disp);letter-spacing:.09em;
  text-transform:uppercase;padding:2px 6px;border-radius:3px;
  background:var(--line);color:var(--ink3)}
.calwhy.live{color:#F2B441;background:rgba(242,180,65,.14)}
.calwhy.unknown{color:#FF9E9E;background:rgba(255,120,120,.12)}
.calstate.complete_with_withdrawals{color:#8FD3FF;background:rgba(91,168,245,.12)}
@media (max-width:560px){
  .calcounts{gap:4px 14px;font-size:12px}
  .calcounts b{font-size:14px}
  .calblock i{font-size:10.5px}
}

/* ⚠ PHONE: the calendar is the surface a voter checks ON A PHONE on a Monday,
   so it becomes a stack of labelled rows rather than four columns squeezed
   into 390px. The header row is dropped and each cell names itself. */
@media (max-width:560px){
  .calnowhead b{font-size:15px}
  .caltbl thead{display:none}
  .caltbl,.caltbl tbody,.caltbl tr{display:block;width:100%}
  .caltbl tr{padding:9px 0;border-bottom:1px solid var(--line)}
  .caltbl td{display:block;border:0;padding:1px 0;font-size:12.5px;
    text-align:left}
  .caltbl td:first-child{font-size:14px;margin-bottom:3px}
  /* the column name in front of the value -- without it a stacked cell is a
     bare "-" with nothing saying which column it came from */
  .caltbl td[data-l]:not(:first-child)::before{content:attr(data-l) " ";
    font:700 9px/1 var(--disp);letter-spacing:.08em;color:var(--slate);
    text-transform:uppercase;margin-right:4px}
  .caltrack .panel,.caltrack .scroll{overflow:visible}
}

/* ---- RANKINGS: RULER BAR, COMPARISON, AND THE PHONE RANK-STRIP ------------
   ⚠ THE PROBLEM THIS SOLVES. The tab was thirteen equal columns, five of them
   bare ranks from five different organisations -- a row could read
   "#1 #1 #1 #1 #1" and nothing on screen said whose was whose. The fix is
   hierarchy, not deletion: the five fields a voter reads are the default, the
   reference columns are one checkbox away, and every rank carries its label
   the moment the table stops being a table. */
.rulerbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:0 0 10px}
.refsel{display:flex;align-items:center;gap:7px;font:600 10px/1 var(--disp);
  letter-spacing:.1em;text-transform:uppercase;color:var(--slate)}
.refsel select{font:inherit;letter-spacing:0;text-transform:none;
  font-size:12px;padding:5px 8px}
.rulerwhat{margin:0 0 14px;max-width:66ch;font-size:13px;color:var(--ink2);
  line-height:1.5}
.rulerwhat b{color:var(--chalk)}
.refcols{display:flex;align-items:center;gap:6px;font-size:12px;
  color:var(--ink2);white-space:nowrap;cursor:pointer}
/* ⚠ THE GROUP ROW SPANS THE COLUMNS IT LABELS, so hiding columns without
   hiding their group leaves the remaining group headings sitting over the
   wrong columns -- 9 spans across 7 columns, measured. Ret and Tourn are ours
   (group "Our outlook") but they are reference-depth detail, so they hide with
   the rest and their group header hides with them. */
.rk3.hideref .c-ref,
.rk3.hideref th.g-ref,
.rk3.hideref th.g-proj{display:none}
.rk3 tr.row{cursor:pointer}
.rk3 tr.row:focus-visible{outline:2px solid var(--gold);outline-offset:-2px}
.rk3 td.rec .nvd{display:inline;margin-left:5px}
.rk3 td.rec .dim{color:var(--ink3)}

/* the comparison surface */
.gaptbl td.tm{font-size:15px}
.gaptbl tr[data-team]{cursor:pointer}
.gaptbl tr[data-team]:hover td{background:rgba(91,168,245,.06)}
.gaptbl tr[data-team]:focus-visible{outline:2px solid var(--gold);outline-offset:-2px}
.gaptbl .rl{display:block;font:700 9px/1.4 var(--disp);letter-spacing:.09em;
  color:var(--slate);font-style:normal}
.gaptbl .gapn{font:700 17px/1 var(--disp);color:var(--chalk)}
.nrtag{font:700 9px/1.5 var(--mono);letter-spacing:.04em;color:var(--ink3);
  background:var(--alt);padding:2px 5px;border-radius:3px}
.gapwrap .tsec{margin-top:18px}

/* ⚠ PHONE: A RANK-STRIP, NOT A SIDEWAYS SPREADSHEET. Fourteen columns cannot
   fit 390px and must not force the essential fields into a horizontal scroll.
   Each row becomes a compact strip -- rank, crest and team, then the labelled
   values -- and the reference columns are simply not shown, because they are
   reference. `data-l` supplies the label so a rank is never bare. */
@media (max-width:560px){
  .rk3 thead{display:none}
  .rk3,.rk3 tbody,.rk3 tr.row{display:block;width:100%}
  /* ⚠ EVERY CELL GETS ITS OWN GRID SLOT. The first version put conference,
     resume, record and AVCA all in one named area -- and grid STACKS items
     that share an area, so the four printed on top of each other and the row
     read as garbled overlapping text. Nothing measured caught it: the row did
     not overflow, the cells were visible, the labels were present. A
     screenshot caught it in one look. Explicit row/column placement cannot
     overlap. */
  .rk3 tr.row{position:relative;display:grid;
    grid-template-columns:32px auto auto minmax(0,1fr) auto;
    column-gap:10px;row-gap:3px;padding:9px 10px 9px 6px;
    border-bottom:1px solid var(--line);align-items:baseline}
  .rk3 tr.row td{display:block;border:0;padding:0;font-size:12.5px;
    white-space:nowrap}
  .rk3 tr.row td.rk{grid-row:1/3;grid-column:1;align-self:center;
    font:700 18px/1 var(--disp);text-align:right}
  .rk3 tr.row td.tm{grid-row:1;grid-column:2/5;font-size:15px;min-width:0;
    white-space:normal;overflow-wrap:anywhere}
  .rk3 tr.row td.pw{grid-row:1;grid-column:5;font:700 16px/1 var(--disp);
    text-align:right}
  .rk3 tr.row td.cf{grid-row:2;grid-column:2}
  .rk3 tr.row td.rec{grid-row:2;grid-column:3}
  .rk3 tr.row td.c-avca{grid-row:2;grid-column:4}
  .rk3 tr.row td.rs{grid-row:2;grid-column:5;text-align:right}
  .rk3 tr.row td.c-ref{display:none}
  /* the label rides in front of the value, so no number is anonymous */
  .rk3 tr.row td[data-l]::before{content:attr(data-l) " ";
    font:700 9px/1 var(--disp);letter-spacing:.08em;color:var(--slate);
    text-transform:uppercase;margin-right:3px}
  .rulerbar{gap:10px}
  .refcols{display:none}
  .gaptbl .gapn{font-size:15px}
}

/* The basis, stamped on the column header itself so the number cannot be
   read as something wider than it is. */
.thb{display:block;font:700 9px/1.4 var(--mono);letter-spacing:.06em;
  color:var(--ink3);font-weight:700}

/* The non-D-I record, shown beside the record it is excluded from. Quiet:
   it is a footnote to the number, not a competing number. */
.nvd{display:block;font:600 9px/1.4 var(--mono);color:var(--ink3);
  font-style:normal;letter-spacing:.02em;white-space:nowrap}

/* The division caveat, wherever a rate is read. Emphatic but not an error
   state: this is a fact about the schedule, not a fault. */
.dicaveat{color:var(--chalk);font-weight:700}
.tm .nondi,
.gline .nondi{margin-left:6px;padding:1px 5px;border-radius:3px;
  font:700 9px/1.5 var(--mono);letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink3);background:var(--alt);vertical-align:middle;}
h3 .h3n{font:700 10px/1 var(--mono);color:var(--ink3);background:var(--alt);
  border-radius:4px;padding:3px 7px;margin-left:7px;vertical-align:2px}
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
.dbtn{font:inherit;font-size:13px;padding:8px 12px;border-radius:4px;
  border:1px solid var(--line2);background:var(--card);color:var(--ink);cursor:pointer}
.dbtn:hover{border-color:var(--navy);color:var(--navy)}
.stgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}
.brk{display:flex;gap:18px;overflow-x:auto;padding-bottom:8px}
.brkcol{flex:none;min-width:210px}
.brkhead{font:700 11px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:9px}
.brkgame{background:var(--card);border:1px solid var(--line);border-radius:4px;
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
.why{background:var(--card);border:1px solid var(--line);border-radius:4px;
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
.pl{background:var(--card);border:1px solid var(--line);border-radius:4px;
  padding:8px 11px;text-align:left}
.pl b{display:block;font-size:13.5px}
.pl span{display:block;font-size:11.5px;color:var(--ink2);text-transform:capitalize}
.pl i{font-style:normal;font:700 12px/1.5 var(--mono);color:var(--navy)}
.pl i em{font-style:normal;color:var(--ink3);font-size:10px;margin:0 4px 0 2px}

/* ---- team page ---- */
.thead{background:var(--card);border:1px solid var(--line);border-radius:4px;
  padding:18px 20px;margin-bottom:14px;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.thead h2{margin:0 0 4px;font:600 34px/1 var(--disp);letter-spacing:.005em}
.thead .sub{color:var(--ink2);font-size:13.5px}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}
.chip{font:700 11.5px/1 var(--mono);border:1px solid var(--line2);border-radius:4px;
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
input,select{font:inherit;font-size:14px;padding:8px 12px;border-radius:4px;
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
  <!-- COURTSIGNAL-STATUS-BEGIN -->
  <!-- ⚠ THE CONTROL ROOM STRIP. A broadcast gallery shows you the state of the
       plant before it shows you the programme: what day it is, how fresh the
       feed is, and whether anything is actually happening. Every value here is
       filled in by csStatus() from data that already exists -- the build stamp,
       today's Pacific date, and a count of live matches. It renders "quiet"
       when nothing is live, which is a true statement rather than an empty
       one. -->
  <div class="cs-status" id="csstatus" role="status" aria-live="polite"></div>
  <!-- COURTSIGNAL-STATUS-END -->
  <div class="net"></div>
  <!-- COURTSIGNAL-TAPE-BEGIN -->
  <!-- THE RALLY TAPE. Mounted once, here, directly under the net -- so it is
       the visual anchor of every screen and the Match Desk opens straight into
       it, which is both things the brief asks for from ONE instance rather
       than two that could drift apart (R4). Empty until csTape() fills it;
       there is no hand-written fallback markup to go stale. -->
  <div id="cstape"></div>
  <!-- COURTSIGNAL-TAPE-END -->
  </header>
  <nav role="tablist"><div class="inner">
    <!-- ⚠ FIVE DESTINATIONS, NOT TWELVE. A flat strip of twelve makes every
         page a sibling of every other, which is why the hub read as a pile of
         pages. These five are the daily job -- follow the day, check a
         ranking, research a team, keep the ballot. The reference tools keep
         every capability they had; they move behind More. -->
    <button role="tab" aria-selected="true" data-v="desk" class="pri">Today</button>
    <button role="tab" aria-selected="false" data-v="scores" class="pri">Scores</button>
    <button role="tab" aria-selected="false" data-v="rankings" class="pri">Rankings</button>
    <button role="tab" aria-selected="false" data-v="teams" class="pri">Teams</button>
    <!-- PRIVATE. Cody's own weekly VolleyTalk ballot, not a ranking this site
         publishes. Stripped from the public build. -->
    <button role="tab" aria-selected="false" data-v="ballot" class="pri">My Ballot</button>
    <div class="moreWrap">
      <button type="button" class="morebtn" id="morebtn" aria-haspopup="true"
        aria-expanded="false" aria-controls="moremenu">More<span aria-hidden="true">&#9662;</span></button>
      <div class="moremenu" id="moremenu" role="menu" aria-labelledby="morebtn" hidden>
        <!-- PRIVATE. The ballot rides here on a PHONE ONLY (design review
             via Cody, 2026-08-28): six text tabs across a phone is too
             cramped, so four primaries stay visible and the nav's ballot
             button hides at that width -- reachable exactly once either way.
             The strip removes any PRIVATE-commented ballot button, this one
             included. -->
        <button role="menuitem" data-v="ballot" class="phoneonly">My Ballot</button>
        <button role="menuitem" data-v="leaders">Stats</button>
        <button role="menuitem" data-v="players">Players</button>
        <button role="menuitem" data-v="prank">Player ratings</button>
        <button role="menuitem" data-v="standings">Standings</button>
        <button role="menuitem" data-v="bracket">Projected bracket</button>
        <button role="menuitem" data-v="schedule">Schedule</button>
        <button role="menuitem" data-v="tv">On TV</button>
        <!-- INTEL-MENU-BEGIN -->
        <button role="menuitem" data-v="intel">Intel</button>
        <!-- INTEL-MENU-END -->
        <!-- FILMROOM-MENU-BEGIN -->
        <button role="menuitem" data-v="film">Film Room</button>
        <!-- FILMROOM-MENU-END -->
      </div>
    </div>
  </div></nav>

<main>

<section id="v-scores" hidden>
  <!-- ⚠ THE SEASON HERO AND THE "WHAT CHANGED" RIBBON USED TO OPEN THIS PAGE.
       Measured before the change: a reader asking "what is on today" met a
       full-width "THE 2026 SEASON, MEASURED" panel with court art, a podium of
       three teams, a results ribbon, and a paragraph about per-set scores --
       roughly a screen and a half before the first date control. Those are
       real jobs; none of them is this page's job.
       They now live on Today (which is where "what changed" belongs) and the
       season summary is reachable from there. This page answers exactly one
       question: what matches are happening on the selected date. -->
  <h2 class="vh">Scoreboard</h2>
  <!-- ⚠ THE SEASON IS STATED IN THE MARKUP, NOT INJECTED. This lead was
       filled by JS, so the SERVED html carried an empty <p class="lead"> --
       and the guard that requires every view to name its season was right to
       fail it: a reader (or a fetch, or the public page) sees the document,
       not the script that would have populated it. The sentence is static
       anyway; nothing here depended on the selected date. -->
  <!-- ⚠ THE WORKING SCOREBOARD CARRIES ALMOST NO PROSE (design review via
       Cody, 2026-08-28: "You know what the page does"). The methodology moved
       behind a disclosure; the season is still named for the guard that
       requires a view to say which year it describes. -->
  <details class="method sbmeth" id="sbLead"><summary><b>2026 season</b> &mdash; where these numbers come from</summary>
    <div class="note"><p>Every Division-I match on the selected date, from the
    same canonical fixture record the rest of the hub reads. A rank carries the
    ranking it came from; a venue is the one the feed or a school published,
    never inferred.</p></div></details>

  <!-- THE DATE IS THE PAGE. Previous / next / today, then the filters. -->
  <div class="sbbar">
    <div class="sbdate">
      <button type="button" class="sbnav" id="sbPrev" aria-label="Previous day">&larr;</button>
      <div class="sbday"><b id="sbDayLabel"></b><span id="sbDayIso"></span></div>
      <button type="button" class="sbnav" id="sbNext" aria-label="Next day">&rarr;</button>
      <button type="button" class="sbtoday" id="sbToday">Today</button>
      <label class="sbpick"><span>Jump to</span>
        <input type="date" id="sbDate" min="2026-08-21" max="2026-12-31"></label>
    </div>
    <div class="seg sbfilters" role="tablist" aria-label="Which matches">
      <button class="segb on" data-sbf="all" type="button">All</button>
      <!-- MYBOARD-HTML-BEGIN -->
      <!-- ⚠ THIS FILTER NAMES A PRIVATE FEATURE, so it is fenced like the rest
           of My Board. It shipped unfenced and the public gate caught it: the
           published page carried the words on a control that could not work
           there, because the board itself is stripped. -->
      <button class="segb" data-sbf="board" type="button">My Board</button>
      <!-- MYBOARD-HTML-END -->
      <button class="segb" data-sbf="ranked" type="button">Ranked</button>
      <button class="segb" data-sbf="live" type="button">Live</button>
      <button class="segb" data-sbf="final" type="button">Final</button>
      <button class="segb" data-sbf="upcoming" type="button">Upcoming</button>
      <span class="count" id="sbCount"></span>
    </div>
  </div>
  <div id="sbBody"></div>

  <div id="justin" hidden>
    <div class="livehead"><b class="justin">Just finished</b><span id="justinmeta"></span></div>
    <div class="cards" id="justincards"></div>
  </div>
  <!-- ⚠ "WHAT CHANGED" MOVED TO TODAY. It answers "what happened while I was
       away", which is Today's second question, not this page's only one. Two
       date controls and a results ribbon on one screen made the Scoreboard
       argue with itself about what it was for. -->
  <div id="today" hidden></div>
  <div id="weekbox" hidden></div>
  <div id="scoredetail" hidden></div>
  <!-- ⚠ THE FULL SEASON LEDGER IS KEPT AND NAMED. It is a different question
       -- "everything, across the season" -- so it is a deliberate disclosure
       under the day view rather than a second set of controls competing with
       it. Nothing was deleted. -->
  <details class="sbfull"><summary>Full season ledger &mdash; every fixture and result</summary>
  <div id="ledgerwrap">
    <div class="seg" role="tablist" aria-label="Match state">
      <!-- ⚠ THIS TAB USED TO OPEN ON "ALL": 472 matches, newest first, and
           because "newest first" includes DECEMBER, the first screen of a
           volleyball results page was a wall of fixtures that have not been
           played. The daily question -- what is on, what just finished, what
           is next -- was somewhere below the fold.
           Today is the default. The full ledger is not removed, it is named
           and one click away. -->
      <button class="segb on" data-ls2="today">Today</button>
      <button class="segb" data-ls2="live">Live</button>
      <button class="segb" data-ls2="final">Final</button>
      <button class="segb" data-ls2="upcoming">Upcoming</button>
      <button class="segb" data-ls2="all">Full ledger</button>
      <span class="count" id="ledgercnt"></span>
      <span class="datejump"><label for="ldate">Jump to a date</label>
        <input type="date" id="ldate">
        <button type="button" class="linkbtn" id="lclear">clear</button></span>
    </div>
    <div id="ledgerbody"></div>
  </div>
  <div class="cards" id="resultcards" hidden>{{SCORE_CARDS}}</div>
  </details>
</section>

<section id="v-desk">
  <div id="deskdetail" hidden></div>
  <div id="deskboard">
  <!-- ⚠ NOT "Your next watches": the first SECTION inside this view is
       titled exactly that, so the words appeared twice within sixty
       pixels on a phone (Cody's screenshot). The view header names the
       view -- the product's own name for it -- and the section keeps
       the words, because it is the one carrying the note. -->
  <h2 class="vh">Match desk</h2>
  <p class="tabhint" id="desklead"></p>

  <div id="desktoday">
    <span id="desktodaymeta" hidden></span>
    <div id="desktodaycards"></div>
  </div>

  <!-- ⚠ MY BOARD IS LAST, AND SMALL. It was the FIRST block on the landing
       page -- four rows of watched teams above the matches worth watching --
       so the personal list outranked the reason for opening the page. It is a
       secondary, personal aid: it belongs after the watches, the weekend and
       the results that moved the picture. -->
  <!-- MYBOARD-HTML-BEGIN -->
  <div class="mbpanel mbsecondary" id="mbpanel" role="region" aria-label="My Board" hidden></div>
  <!-- MYBOARD-HTML-END -->

  <div id="desksoon">
    <span id="desksoonmeta" hidden></span>
    <div id="desksooncards"></div>
    <p class="dsoonrest" id="desksoonrest"></p>
  </div>

  <details class="method">
    <summary><b>How this page chooses and what the forecast is</b></summary>
    <div class="note">
      <p><b>The order is a stated sort, not a score.</b> Ranked-vs-ranked first,
      then any ranked side, then how close the forecast is. There is deliberately
      no single &ldquo;watch rating&rdquo;: one number would hide which fact
      moved it, and every tag on a card names the fact it came from.</p>
      <p><b>The forecast is a probability, not a pick.</b> It is the rally model
      backtested on 2025 at a Brier score of 0.1289. It says how often a match
      like this goes each way &mdash; a 70% side loses three times in ten, and
      those three are not mistakes.</p>
      <p><b>After a match is final the forecast comes from the append-only log,
      and only from a row written BEFORE tipoff.</b> The forward-looking file is
      regenerated nightly from everything known at the time, which for a played
      match includes the result &mdash; quoting it afterwards would be inventing
      a prediction after the fact. Where no pre-tipoff row exists the card says
      <i>forecast unavailable</i> rather than showing one.</p>
      <p><b>Live scores never reach the ratings.</b> An in-progress card is read
      straight from the scoreboard feed and is labelled as such; POWER,
      R&eacute;sum&eacute;, records, player leaders and the rankings all wait
      for the official final and the next verified refresh.</p>
    </div>
  </details>
  </div>
</section>

<section id="v-top25" hidden>
  <h2 class="vh">Digby&rsquo;s Top 25 &mdash; {{T25_SEASON}}</h2>
  <p class="tabhint">{{T25_LEAD}}</p>
  <div class="scroll"><table class="t25">
    <thead><tr>
      <th>#</th><th>Team</th><th title="how the rank changed">{{T25_MOVEHEAD}}</th>
      <th class="n" title="POWER: 50 is an average Division-I team and every 12.5 points is one standard deviation. Same scale as the Rankings tab.">Power</th>
      <th class="n" title="the AVCA coaches poll rank, and how far our rating differs from it">AVCA</th>
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
  <!-- ⚠ THREE RULERS AT FULL WEIGHT, THE REST BEHIND A SECONDARY CONTROL.
       Five equal buttons said that the committee's top 16 and the NCAA's RPI
       are the same kind of thing as our own order and the coaches poll. They
       are reference. The three a voter actually works in lead; the rest sit in
       a select that does not compete for attention. -->
  <div class="rulerbar">
    <div class="seg" role="tablist" aria-label="Which ranking">
      <button class="segb on" data-r="ours"><i class="vx-key vx-k-power"></i>POWER</button>
      <button class="segb" data-r="avca"><i class="vx-key vx-k-avca"></i>AVCA coaches poll</button>
      <button class="segb" data-r="digby"><i class="vx-key vx-k-digby"></i>Digby&rsquo;s Top 25</button>
      <button class="segb" data-r="gap">POWER vs AVCA</button>
      <button class="segb" data-r="cal">Weekly calendar</button>
    </div>
    <label class="refsel"><span>Reference</span>
      <select id="refpick" aria-label="Reference ranking">
        <option value="">Choose&hellip;</option>
        <option value="top16">DI Committee top 16</option>
        <option value="rpi">NCAA RPI</option>
      </select>
    </label>
  </div>
  <!-- ⚠ ONE SENTENCE PER RULER, FROM ONE MAP. A rank means nothing without
       knowing whose ruler it is; this is the line that says so, and it is
       keyed by view so a new view cannot ship without one. -->
  <p class="rulerwhat" id="rulerwhat"></p>
  <div id="pollview" hidden></div>
  <!-- ⚠ SAID ONCE. "nothing here feeds the model" was appearing three times on
       this tab -- in the group header above the columns, in RANK_BASIS, and
       again here. Repeating a caveat does not make it more believed; it makes
       the page read as anxious. The group row carries it now. -->
  <p class="histnote">{{TREND_NOTE}}</p>
  <p class="lead" id="ranklead">{{RANK_BASIS}}
  <!-- ⚠ THE HINT MUST DESCRIBE WHAT THE ROW ACTUALLY DOES. It said "click a
       team to see the six players the number is built from", which described
       the in-place expansion this view no longer has -- the projected six
       lives on the team page, which is where a row now goes. An instruction
       that no longer works is worse than none. -->
  <span class="leadhint">Open a team for its full dossier &mdash; including the
  six players this projection is built from.</span></p>
  <div class="ctl">
    <input type="search" id="q" placeholder="Search a team&hellip;">
    <select id="conf"><option value="">All conferences</option></select>
    <select id="top">
      <option value="50">Top 50</option><option value="64">Top 64</option>
      <option value="100">Top 100</option><option value="0">All</option>
    </select>
    <label class="refcols"><input type="checkbox" id="refcols">
      <span>Reference columns</span></label>
    <span class="count" id="cnt"></span>
  </div>
  <!-- ⚠ ADDRESSED BY ID, NOT BY ".panel". renderPoll() used to reach for
       `#v-rankings .panel`, which was unique until the comparison view began
       injecting its own panels into #pollview -- a node that sits EARLIER in
       this section, so the selector silently started returning the wrong
       element and switching back to POWER toggled the comparison surface
       instead. Same shape as the duplicate-id bug that made the just-finished
       band query the schedule tbody. -->
  <div class="panel" id="rankpanel"><div class="scroll"><table class="rk3">
    <!-- ⚠ A GROUPED HEADER, BECAUSE THIRTEEN EQUAL COLUMNS SAY NOTHING ABOUT
         WHAT IS OURS AND WHAT IS SOMEBODY ELSE'S. POWER and R&eacute;sum&eacute;
         are two different questions this site answers; everything to their
         right is either last season or another organisation's opinion, and the
         page said so only in prose a reader had to find. The group row says it
         above the columns themselves. -->
    <thead>
    <tr class="grp">
      <th colspan="3"></th>
      <th class="g-ours" colspan="3">Our system</th>
      <th class="g-poll" colspan="1">Coaches poll</th>
      <!-- ⚠ Ret and Tourn are OURS and stay out of the reference group. Sweeping
           them under "none of it feeds our model" would be a false label on two
           columns this site computes itself. -->
      <th class="g-ref" colspan="5">Reference &mdash; none of it feeds our model</th>
      <th class="g-proj" colspan="2">Our outlook</th>
    </tr>
    <tr>
      <th>#</th><th class="l">Team</th><th class="l">Conf</th>
      <th class="n c-pow" title="POWER &mdash; how strong a team is; who would win tomorrow. 50 is an average Division-I team and every 12.5 points is one standard deviation. A monotone rescaling of the rating that produces the rank beside it, not a blend of hand-picked components.">Power</th>
      <th class="n c-res" title="R&Eacute;SUM&Eacute; &mdash; what a team has EARNED. Ranked by RPI, which beat every alternative against the 64 teams the committee actually selected in 2025. Margin is ignored on purpose: a win is a win. A different question from Power, and the two are meant to disagree.">R&eacute;sum&eacute;</th>
      <th class="n rec" title="Won-lost against DIVISION-I opponents this season, the NCAA&rsquo;s own convention. A non-Division-I result is shown beside it and is not counted in the record.">Record</th>
      <th class="n c-avca" title="AVCA coaches poll &mdash; the official poll, published by the American Volleyball Coaches Association. External reference: it does not feed our model.">AVCA&nbsp;Poll</th>
      <th class="c-ref" title="our fitted composite, final 2025">2025</th>
      <th class="c-ref" title="VolleyTalk Top 25, preseason &mdash; external reference">VT</th>
      <th class="c-ref" title="Massey Ratings, 2026 preseason &mdash; external reference">Massey</th>
      <th class="c-ref" title="official NCAA RPI rank, final 2025">RPI</th>
      <th class="c-ref" title="range the other systems put this team in">Others</th>
      <th class="c-ref" title="share of 2025 production on the 2026 roster">Ret</th>
      <th class="c-ref" title="simulated NCAA tournament odds; backtested at 42 of the real 64 from a preseason prior">Tourn</th>
    </tr></thead>
    <tbody id="rbody">{{RANK_ROWS}}</tbody></table></div>
    <!-- ⚠ PROGRESSIVE DISCLOSURE, NOT DELETION. This methodology is the most
         valuable thing on the tab and it was also 1,250 characters of essay
         standing between a reader and the rankings. Collapsed, never cut: the
         summary carries the three facts that change how the table should be
         read, and the derivation is one click away. -->
    <details class="method">
      <summary><b>Methodology</b> &mdash; how this ranking is built, what it
        cannot see, and why it barely moves in August</summary>
    <div class="note">
      <p><b>Why it barely moves in August.</b> A result is weighted
      <code>n/(n+k)</code> with <b>k measured, not chosen</b>, so a team needs
      about k matches before this season counts as much as the projection does.
      Reacting harder was tested against 2025 and it predicts <i>worse</i>:
      blending at every speed from k=0.5 to k=50, the best value was 25, and
      every faster setting was worse than the one above it &mdash; reacting hard
      to each result scored below ignoring results altogether. One Friday night
      genuinely is that little evidence. The fitted composite takes over
      automatically once 50 matches are in.</p>
      <p><b>Two rankings, and they are meant to disagree.</b> POWER answers who
      would win tomorrow and margin drives it. R&eacute;sum&eacute; answers who
      has earned a bid, ranked by RPI because that beat every alternative
      against the 64 teams the committee actually selected in 2025; margin is
      ignored there on purpose, because a win is a win. A very good team that
      has not played anybody is correctly high on one and nowhere on the
      other.</p>
      <p><b>How the preseason half works.</b> The ranking above is this
      projection <i>blended with 2026 results</i>; what follows describes the
      projection, which is where a team starts before it has played.
      Each returning player and incoming transfer
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
    </details>
  </div>
</section>

<!-- INTEL-HTML-BEGIN -->
<section id="v-intel" hidden>
  <h2 class="vh">Intel <span class="privtag" title="A private wire. Headlines and links only, read on this device; nothing is published, stored in the repository, or sent anywhere.">private</span></h2>
  <p class="tabhint">Official volleyball news, headline and link only. Reading
    happens at the publisher &mdash; nothing here copies their article, and
    nothing about what you have read leaves this device.</p>

  <div class="in-bar">
    <div class="seg" role="tablist" aria-label="Which stories">
      <button class="segb on" data-inf="new" type="button">New</button>
      <button class="segb" data-inf="board" type="button">My Board</button>
      <button class="segb" data-inf="national" type="button">National</button>
      <button class="segb" data-inf="read" type="button">Read</button>
    </div>
    <button type="button" class="fr-btn" id="intelrefresh">Check now</button>
    <span class="count" id="intelcount"></span>
  </div>
  <p class="in-state" id="intelstate"></p>
  <div id="intelbody"></div>

  <p class="in-foot">Source: NCAA.com Division I women&rsquo;s volleyball.
    The list of sources is fixed in code and audited in
    <code>docs/intel_sources.md</code>; this page cannot be pointed at
    anything else.</p>
</section>
<!-- INTEL-HTML-END -->

<!-- FILMROOM-HTML-BEGIN -->
<section id="v-film" hidden>
  <h2 class="vh">Film Room <span class="privtag" title="Your notebook. It stays on this device: nothing is published, nothing feeds a rating, and nothing is posted anywhere.">private</span></h2>
  <p class="tabhint">Your own observations, kept on this device. A note is
    <b>what you wrote</b>; a chip beside it is a hub value <b>frozen at the
    moment you saved it</b>. Nothing here is read by any rating, projection or
    ballot, and no link you paste is ever fetched.</p>

  <div class="fr-new" id="frnew"></div>

  <div class="fr-bar">
    <input type="search" id="frq" placeholder="Search your notes&hellip;">
    <select id="frfctx" aria-label="Filter by context">
      <option value="">Any moment</option>
      <option value="pre">Pre-match</option>
      <option value="during">During match</option>
      <option value="post">Post-match</option>
    </select>
    <select id="frfsrc" aria-label="Filter by source">
      <option value="">Any source</option>
      <option value="self">Watched myself</option>
      <option value="official">Official stat/source</option>
      <option value="article">Article</option>
      <option value="community">Community discussion</option>
      <option value="other">Other</option>
    </select>
    <span class="count" id="frcount"></span>
  </div>

  <div id="frbody"></div>

  <!-- ⚠ EXPORT IS A LOCAL ACT. Both buttons end at this device: a file the
       browser saves, or the clipboard. Nothing is sent anywhere, and the
       status line says which of the two actually happened. -->
  <div class="fr-export">
    <div class="vx-label"><b>Export</b></div>
    <p class="fr-exwhy">Your notebook as JSON, on this device only. Nothing is
      uploaded, posted, or written to the repository.</p>
    <div class="fr-exrow">
      <button type="button" class="fr-btn" id="frexdl">Download JSON</button>
      <button type="button" class="fr-btn" id="frexcopy">Copy JSON</button>
      <span class="fr-state" id="frexstate"></span>
    </div>
    <div id="frout" hidden></div>
  </div>

  <!-- ⚠ IMPORT READS ONLY WHEN CHOSEN. No drag-and-drop auto-read, no
       clipboard sniffing: a file is opened because the file input was used,
       or text is checked because Preview was pressed. Nothing is written
       until the preview has been seen and a button pressed. -->
  <div class="fr-import">
    <div class="vx-label"><b>Import</b></div>
    <p class="fr-exwhy">Restore or move your own notebook. The file is read on
      this device, checked note by note, and shown to you before anything
      changes. Nothing is uploaded and nothing is overwritten by default.</p>
    <div class="fr-exrow">
      <label class="fr-btn" for="frfile">Choose a .json file
        <input type="file" id="frfile" accept="application/json,.json"
               hidden></label>
      <button type="button" class="fr-btn" id="frpaste">Preview pasted
        JSON</button>
      <span class="fr-state" id="frimpstate"></span>
    </div>
    <textarea class="fr-raw" id="frpastebox" rows="4"
      placeholder="Or paste an exported notebook here, then press Preview."></textarea>
    <div id="frprev" hidden></div>
  </div>
</section>
<!-- FILMROOM-HTML-END -->

<section id="v-ballot" hidden>
  <h2 class="vh">Ballot Workshop <span class="privtag" title="Your own ballot. It is not published here, it feeds no model, and nothing is posted anywhere.">private</span></h2>
  <p class="tabhint" id="ballotlead"></p>

  <!-- ⚠ STATUS FIRST, ACTIONS LAST. The workshop used to open with three
       buttons -- Save, Copy, Reset -- so the first thing on a voter's desk was
       a way to finish. What a voter needs first is WHERE THEY ARE: which
       ranking week this is, whether that week's results are actually complete,
       whether there are unsaved edits, and what they last submitted. The
       actions moved to the end of the flow, where finishing belongs. -->
  <div class="bwstatus" id="bwstatus"></div>

  <!-- ⚠ NONE OF THESE THREE IS A RECOMMENDATION. Each is a difference between
       two orderings, stated so it can be looked at before saving. -->
  <div class="bwpre" id="bwpre" hidden>
    <div class="bwprehd">
      <b>Before you save</b>
      <button type="button" class="bwbtn primary" id="bwpresave">Save ballot</button>
      <button type="button" class="bwbtn" id="bwpreback">Keep editing</button>
    </div>
    <div class="bwprecols" id="bwprebody"></div>
  </div>

  <!-- THREE RULERS, NAMED. The whole point of the workshop is that these are
       different questions; a reader who cannot tell them apart cannot use it. -->
  <!-- ⚠ FOUR RULERS, ONE KEY, THE SAME COLOURS AS EVERY OTHER TAB. This was
       four sentence-long chips that wrapped to three lines. The distinction it
       protects is the point of the workshop -- My ballot is a judgement, POWER
       is ours, AVCA is theirs, and Résumé does not exist yet -- so it stays,
       but as a key rather than a paragraph. -->
  <div class="bwrulers" aria-label="Which ranking is which">
    <span class="bwr mine"><i class="bwsw"></i>My ballot</span>
    <span class="bwr pow"><i class="bwsw"></i>POWER</span>
    <span class="bwr av"><i class="bwsw"></i>AVCA</span>
    <!-- ⚠ THE FULL SENTENCE STAYS. Shortening this to "inactive" lost WHY,
         and an honest inactive state is one of the things this workshop is
         careful about -- a résumé does not exist yet because too little of the
         season has been played, not because a switch is off. The compact key
         gets its brevity from the other three, not from this one. -->
    <span class="bwr off"><i class="bwsw"></i>R&Eacute;SUM&Eacute; &mdash; inactive until enough games are played</span>
  </div>

  <!-- WEEKLY BRIEFING. Facts about YOUR ballot and the week since you saved
       it. Never a recommended Top 25, and never a verb telling you what to do. -->
  <div class="bwbrief" id="bwbrief" role="region" aria-label="Weekly briefing"></div>
  <div class="bwro" id="bwro" hidden></div>

  <details class="bwreview" id="bwreview">
    <summary><b>Review</b> <span class="bwrn" id="bwrevn"></span></summary>
    <p class="bwsub">Teams where something OBSERVABLE changed. Each item names
      the exact trigger and shows the ranks it came from. There is no urgency
      score, no ordering by importance, and nothing here says what to do about
      it &mdash; that is the part only you can write.</p>
    <div id="bwqueue"></div>
  </details>

  <!-- COMPARISON WORKSPACE. You pick both teams. Nothing is auto-selected and
       no "debate" is proposed. -->
  <details class="bwcompare" id="bwcompare">
    <summary><b>Compare two teams</b> <span class="bwrn">you choose both</span></summary>
    <p class="bwsub">Only fields that already exist on this site, each labelled
      with which ruler it comes from. No case for or against, no scouting
      language, no sentiment.</p>
    <div class="bwcmppick">
      <label for="bwcA">Team A</label>
      <input type="search" id="bwcA" list="bwlist-teams" autocomplete="off"
        placeholder="Type a team&hellip;">
      <label for="bwcB">Team B</label>
      <input type="search" id="bwcB" list="bwlist-teams" autocomplete="off"
        placeholder="Type a team&hellip;">
      <button type="button" class="bwbtn" id="bwcclear">Clear</button>
    </div>
    <div id="bwteamcmp"></div>
  </details>

  <div class="bwgrid">
    <div class="bwmain">
      <ol class="bwlist" id="bwlist"></ol>
      <h3 class="bwh">Also considered</h3>
      <p class="bwsub">Teams you are weighing but have not slotted. Adding one from
        here pushes everything below it down; nobody leaves your ballot silently.</p>
      <div class="bwpool" id="bwpool"></div>
      <div class="bwadd">
        <input type="search" id="bwq" list="bwlist-teams" placeholder="Add a team to consider&hellip;" autocomplete="off">
        <datalist id="bwlist-teams"></datalist>
      </div>
    </div>

    <aside class="bwside">
      <div class="bwcard">
        <h3 class="bwh">Since your last ballot</h3>
        <div id="bwdiff"></div>
      </div>
      <div class="bwcard">
        <h3 class="bwh">Notes / biggest moves</h3>
        <p class="bwsub">Appended to the copied text. Yours, in your words.</p>
        <textarea id="bwsummary" rows="4" placeholder="Optional. e.g. why your #1 is not the POWER #1."></textarea>
      </div>
      <div class="bwcard">
        <h3 class="bwh">Saved ballots</h3>
        <div id="bwhistory"></div>
        <div class="bwcmp">
          <h4 class="bwh4">Compare two saves</h4>
          <div class="bwcmprow">
            <select id="bwcmpa" aria-label="Earlier ballot"></select>
            <span>vs</span>
            <select id="bwcmpb" aria-label="Later ballot"></select>
          </div>
          <div id="bwcmpout"></div>
        </div>
      </div>
    </aside>
  </div>

  <!-- ⚠ FINISHING IS A STEP, NOT A TOOLBAR. Save and Copy sit after the
       ballot because that is when they are used. Reset is here too, and last,
       because it is the destructive one. -->
  <div class="bwfinish">
    <div class="bwfinlab">Finish</div>
    <div class="bwbar">
      <button class="bwbtn primary" id="bwsave" type="button">Save this ballot</button>
      <button class="bwbtn" id="bwcopy" type="button">Copy for VolleyTalk</button>
      <span class="bwstate" id="bwstate"></span>
      <button class="bwbtn bwquiet" id="bwseed" type="button" title="Replace the 25 slots with Digby&rsquo;s current POWER order. Your notes and reasons are kept.">Reset to POWER order</button>
    </div>
  </div>

  <details class="method">
    <summary><b>How this works</b> &mdash; what is stored, and what this is not</summary>
    <div class="note">
      <p><b>It is your ballot.</b> The list starts from Digby&rsquo;s POWER order
      because a blank twenty-five is a bad starting point, not because POWER is
      the answer. Every slot is editable and your order is what gets saved and
      copied.</p>
      <p><b>Two kinds of movement.</b> The arrow beside a team is movement
      against <i>your previous saved ballot</i> &mdash; what you changed your
      mind about. The POWER column beside it is a different comparison, and the
      two are meant to differ.</p>
      <p><b>Reasons are words, never numbers.</b> When you place a team well
      away from its POWER rank the workshop asks why, and stores what you write.
      It is not scored, weighted, or fed into POWER, R&eacute;sum&eacute;, the
      simulator or the projector. Ideas like composure and late-set nerve were
      measured against 2025 and made the rating <i>worse</i>; the honest place
      for them is a person&rsquo;s judgment, labelled as such.</p>
      <p><b>Storage.</b> Each save appends a timestamped line to
      <code>data/ballots_{{SEASON_YEAR}}.jsonl</code>. Nothing is ever rewritten, so
      a past ballot cannot be lost by saving a new one. Without the local server
      running, saves fall back to this browser only &mdash; the bar above says
      which is in force.</p>
      <p><b>It posts nowhere.</b> &ldquo;Copy for VolleyTalk&rdquo; puts text on
      your clipboard for you to read and paste. What gets submitted, and whether
      it is right, is yours.</p>
    </div>
  </details>
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
  <p class="lead">Every rated player in Division I for the {{SEASON_YEAR}}
  season. <b>{{N_PLAYERS}}</b> have a 2026 line so far — click one for her
  season and every match she has played. The rest are listed underneath with
  <b>last season's</b> numbers, because the season has barely started.</p>
  <div class="ctl">
    <input type="search" id="pq" list="plist" placeholder="Type a player&hellip;" autocomplete="off">
    <datalist id="plist"></datalist>
    <span class="count" id="pcnt"></span>
  </div>
  <div id="playercard"></div>
  <div id="pnotyet"></div>
  <div class="panel" id="ptable"><div class="scroll"><table>
    <thead><tr><th class="l">Player</th><th class="l">Team</th><th>Pos</th>
      <th>Sets</th><th>Kills</th><th>Hit%</th>
      <th title="assists -- the setter's number, and the one this table used to omit">Ast</th>
      <th>Digs</th><th>Blk</th><th>Aces</th>
      <th>Pts/set</th></tr></thead>
    <tbody id="pbody"></tbody></table></div></div>
  <p class="pdirhint">Showing one player. <button type="button" class="linkbtn"
    id="pbackdir">Back to the full directory</button></p>
</section>

<section id="v-prank" hidden>
  <p class="lead">Player ratings for the {{SEASON_YEAR}} season, within position
  only. <b>POWER</b> is how good she is now &mdash; last season blended with this
  one. <b>R&Eacute;SUM&Eacute;</b> is what she has produced this season, and
  nothing else.</p>
  <div class="prkwrap">
    <div class="ctl prkctl">
      <span class="segbar" id="prkpos" role="tablist"></span>
      <span class="segbar" id="prkrole" role="tablist" hidden></span>
      <span class="segbar" id="prkmode" role="tablist">
        <button type="button" data-m="power" class="on">POWER</button>
        <button type="button" data-m="resume">R&Eacute;SUM&Eacute;</button>
      </span>
      <span class="count" id="prkcnt"></span>
    </div>
    <div id="prksupport" class="prksupport"></div>
    <div class="panel"><div class="scroll"><table id="prktable">
      <thead><tr><th>#</th><th class="l">Player</th><th class="l">Team</th>
        <th>Cl</th><th>Rating</th><th>This season</th>
        <th class="l">What is driving it</th></tr></thead>
      <tbody id="prkbody"></tbody></table></div></div>
    <div id="prkstars"></div>
  </div>
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
  <!-- ⚠ THIS COPY USED TO SAY THE SCHEDULE WAS "STRAIGHT FROM NCAA.COM" AND
       THAT WAS NO LONGER TRUE. ncaa.com is still the base source for every
       fixture, but a small ledger of official-school corrections now governs
       specific verified facts on specific games, and the page has to say so or
       it is misdescribing where its own numbers come from.
       ⚠ AND IT USED TO IMPLY THE WHOLE SCHEDULE WAS ON SCREEN. The table
       renders the first {{N_SHOWN}} rows; the count now names both numbers. -->
  <!-- ⚠ THREE FACTS, THEN THE TABLE. This lead had grown to a ten-line
       essay standing between a reader and the fixtures -- the identical
       problem already fixed on the Rankings tab, where the note reads "the
       methodology was collapsed and the intro absorbed it, which is the
       opposite of progressive disclosure". None of the detail was wrong or
       is dropped: it moved into the disclosure below, which is where a
       reader who wants to know what `v` means will go looking. -->
  <p class="lead"><b>2026 schedule.</b> Showing <b>{{N_SHOWN}}</b> of
  <b>{{N_SCHED}}</b> fixtures from today forward &mdash; search below to reach
  any of the rest. Each row says <b>where</b> it is played, and a fixture whose
  sources disagree says <b>schedule conflict &mdash; verify</b> rather than
  picking one of them.</p>
  <details class="method">
    <summary><b>How to read a row</b> &mdash; sources, and what
      <b>at</b> / <b>vs</b> / <b>v</b> each assert</summary>
    <div class="note">
      <p>The base source is <b>ncaa.com</b>. Where its record is stale or
      disagrees with itself, a small ledger of <b>official-school
      corrections</b> governs the specific facts that were verified against a
      school&rsquo;s own published schedule, and those rows are marked
      <b>school-confirmed</b> with a link to the source.</p>
      <p><b>at</b> is printed only for a confirmed home floor and <b>vs</b>
      only for a confirmed neutral one; anything unconfirmed reads a plain
      <b>v</b> and asserts nothing. A row carries whether it is a conference
      match, a non-conference match, or both a match type and a named event
      &mdash; and an <b>exhibition</b> where the fixture does not count toward
      either record.</p>
    </div>
  </details>
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
    <tbody id="sbody">{{SCHED_ROWS}}</tbody></table></div>
    <button type="button" class="lanemore" id="schedall" hidden></button></div>
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
/* ⚠ A NODE THAT NO LONGER EXISTS MUST NOT TAKE THE PAGE WITH IT. The Scoreboard
   rebuild removed the old live / later-today / this-week / legacy-date stack,
   and several pollers still addressed those ids. `getElementById(x).textContent
   = ...` on a null throws, and because these run inside one boot sequence the
   throw took everything after it: the whole page rendered as an empty Today
   with no header rail.
   $$ returns a harmless stand-in for a missing node, so a stale writer writes
   into nothing instead of exploding. It is NOT a licence to leave orphans --
   test_today_scoreboard.py fails on any id referenced but not rendered. */
const NOWHERE = { textContent: '', innerHTML: '', hidden: true, value: '',
                  style: {}, classList: { add(){}, remove(){}, toggle(){} },
                  addEventListener(){}, querySelectorAll(){ return []; },
                  setAttribute(){}, removeAttribute(){}, focus(){} };
function $$(id) { return document.getElementById(id) || NOWHERE; }

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

/* ── THE MORE MENU ────────────────────────────────────────────────────────
   A real menu, not a hover popover: Escape closes it and returns focus, the
   arrow keys walk it, and a click anywhere else dismisses it. */
function closeMore() {
  const m = document.getElementById('moremenu'), b = document.getElementById('morebtn');
  if (!m || m.hidden) return;
  m.hidden = true; b.setAttribute('aria-expanded', 'false');
}
function openMore() {
  const m = document.getElementById('moremenu'), b = document.getElementById('morebtn');
  if (!m) return;
  m.hidden = false; b.setAttribute('aria-expanded', 'true');
  const f = m.querySelector('button'); if (f) f.focus();
}
(function wireMore() {
  const m = document.getElementById('moremenu'), b = document.getElementById('morebtn');
  if (!m || !b) return;
  b.addEventListener('click', e => {
    e.stopPropagation();
    m.hidden ? openMore() : closeMore();
  });
  m.addEventListener('keydown', e => {
    const items = [...m.querySelectorAll('button')];
    const i = items.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); closeMore(); b.focus(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); items[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); items[items.length - 1].focus(); }
  });
  b.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); openMore(); }
  });
  document.addEventListener('click', e => {
    if (!m.hidden && !m.contains(e.target) && e.target !== b) closeMore();
  });
})();

/* ── THE ROUTER ───────────────────────────────────────────────────────────
   A hash router, because this page is served from a file:// path, a localhost
   static server AND GitHub Pages, none of which can be asked to rewrite URLs.
   ⚠ ONE HANDLER FOR EVERY NAVIGATION. Primary nav, the More menu, a ranking
   row, a roster row, a stats row and the player search all call go(); nothing
   flips a section's hidden attribute on its own any more. That is what makes
   Back, Forward and a direct refresh land in the same place as a click.  */
/* ⚠ THE PRIMARY ROUTE IS `today`; `match-desk` IS KEPT AS AN ALIAS. Every
   ⚠ AND THIS COMMENT MUST NOT NAME A PRIVATE FEATURE. It first cited "a Film
   Room note" as an example of somewhere the old path is written down; that
   string is a strip marker, so an unfenced comment mentioning it aborted the
   public build -- the same trap the On TV comment sprang once before.
   Every link ever copied, bookmarked or saved into a private note points at
   the old path, and breaking those to rename a tab would trade the reader's
   history for a label. VIEW_OF_ROUTE resolves both; ROUTE_OF_VIEW emits only
   the new one, so nothing new is minted under the old name. */
const ROUTE_ALIASES = { 'match-desk': 'desk' };
const ROUTE_OF_VIEW = { desk:'today', scores:'scores', rankings:'rankings',
  teams:'teams', ballot:'ballot', leaders:'stats', players:'players',
  prank:'player-ratings',
  standings:'standings', bracket:'bracket', schedule:'schedule', tv:'tv',
  /* FILMROOM-ROUTE-BEGIN */ film:'film-room', /* FILMROOM-ROUTE-END */
  /* INTEL-ROUTE-BEGIN */ intel:'intel' /* INTEL-ROUTE-END */ };
const VIEW_OF_ROUTE = Object.keys(ROUTE_OF_VIEW)
  .reduce((a,k)=>{a[ROUTE_OF_VIEW[k]]=k;return a;},{});
Object.keys(ROUTE_ALIASES).forEach(k => { VIEW_OF_ROUTE[k] = ROUTE_ALIASES[k]; });

function slug(s) {
  return (s || '').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
}
function unslugTeam(sl) {
  return Object.keys(TEAMS).find(t => slug(t) === sl) || null;
}
function playerBySlug(teamSlug, personSlug) {
  return PLAYERS.find(p => slug(p.team) === teamSlug && slug(p.name) === personSlug) || null;
}
function routeFor(view, rest) {
  return '#/' + (ROUTE_OF_VIEW[view] || 'match-desk') + (rest ? '/' + rest : '');
}
/* navigate: push a hash and let the single handler do the work */
function go(hash, replace) {
  if (('#' + (location.hash || '').replace(/^#/,'')) === hash) { route(); return; }
  if (replace) location.replace(hash); else location.hash = hash;
}

let ROUTE_ORIGIN = null;   // where a detail page was opened from

function showView(view) {
  document.querySelectorAll('nav button[role=tab]').forEach(x =>
    x.setAttribute('aria-selected', x.dataset.v === view));
  document.querySelectorAll('#moremenu button').forEach(x =>
    x.setAttribute('aria-current', x.dataset.v === view ? 'page' : 'false'));
  /* the More button reads as active when one of its own is showing */
  const mb = document.getElementById('morebtn');
  if (mb) mb.classList.toggle('on', !!document.querySelector(
    '#moremenu button[aria-current=page]'));
  moveNavBar();
  /* ⚠ Direct children ONLY. The lanes inside a view are themselves
     <section class="tdblock"> elements, and the un-scoped 'main section'
     swept them too: one navigation stamped hidden on every nested lane, the
     parent view was then un-hidden but the lanes stayed dark, and the page
     read as "the buttons stopped working". A poll re-render recreated the
     lanes and they vanished again on the next click. */
  document.querySelectorAll('main > section').forEach(s => { s.hidden = true; });
  /* the view name on <body>, so a view can shape the shared chrome without
     JS -- the Scores control room compresses the hero this way */
  document.body.dataset.view = view;
  const el = $('#v-' + view);
  if (el) el.hidden = false;
  /* ⚠ A STALE NAV CONTROL KEPT BOTH DOM FOCUS AND ITS RING. Setting
     aria-selected is not enough: the button the reader last pressed is still
     the focused element, so the screen shows the new destination underlined
     AND the old one ringed. Blurring would be the quick fix and is the wrong
     one -- a keyboard reader who pressed Enter on a tab would be dropped to
     the top of the document with nothing focused.
     Focus moves to the region that just appeared, which is the standard answer
     for a routed view: the stale ring goes, and a keyboard reader lands
     exactly where the thing they asked for now is. Only when focus was ON a
     nav control -- never while someone is typing in a filter box. */
  /* ⚠ THE HEADER SHAPE DEPENDS ON THE ROUTE, so it has to be repainted when
     the route changes -- otherwise the marquee painted at boot on Today would
     follow the reader onto Rankings, which is the whole defect. */
  try { if (typeof csTape === 'function') csTape(); } catch (e) { }
  if (el) {
    const a = document.activeElement;
    const stale = a && a.closest && a.closest('nav') &&
      !(a.getAttribute && a.getAttribute('aria-selected') === 'true');
    if (stale) {
      if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
      try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
    }
  }
  return el;
}

function route() {
  const raw = (location.hash || '').replace(/^#\/?/, '');
  const q = raw.split('?');
  const parts = q[0].split('/').filter(Boolean);
  const params = new URLSearchParams(q[1] || '');
  const view = VIEW_OF_ROUTE[parts[0]] || 'desk';
  ROUTE_ORIGIN = params.get('from') || null;
  showView(view);

  /* INTEL-WIRE-BEGIN */
  if (view === 'intel' && typeof inWire === 'function') inWire();
  /* INTEL-WIRE-END */
  /* FILMROOM-WIRE-BEGIN */
  if (view === 'film' && typeof frWire === 'function') frWire();
  /* FILMROOM-WIRE-END */
  if (view === 'rankings') {
    const want = parts[1] === 'power' ? 'ours' : (parts[1] || 'ours');
    /* ⚠ THE REFERENCE VIEWS HAVE NO BUTTON ANY MORE, so gating the render on
       finding one would make #/rankings/rpi land on a blank panel. Render any
       ruler this tab knows about; fall back to POWER for anything else. */
    renderPoll(RULER_WHAT[want] ? want : 'ours');
  }
  /* a match is a destination on either parent, and the parent is the route */
  closeMatchDetail();
  if ((view === 'desk' || view === 'scores') && parts[1]) {
    renderMatchDetail(decodeURIComponent(parts[1]),
                      view === 'scores' ? 'scores' : 'desk');
  } else if (view === 'scores') {
    renderLedger();
  wireScoreboard(); renderScoreboard();
    wireScoreboard(); renderScoreboard();
  }
  if (view === 'prank') { renderPrank(); }
  if (view === 'teams') {
    const t = parts[1] ? unslugTeam(parts[1]) : null;
    if (t) {
      showTeam(t);
    } else if (!document.querySelector('#teamcard .thead')) {
      /* The Teams tab used to open COMPLETELY BLANK -- a lone "Type a team"
         box with no sign of what lived here. Land on the top-ranked team; a
         real selection is never overwritten. Moved off the tab-click handler
         so a direct #/teams load and a Back both get it too. */
      const first = Object.keys(TEAMS).filter(k => TEAMS[k] && TEAMS[k].rank)
        .sort((x, y) => TEAMS[x].rank - TEAMS[y].rank)[0];
      if (first) showTeam(first);
    }
  }
  if (view === 'leaders' && parts[1]) {
    const b = document.querySelector('#v-leaders .segb[data-ls="' +
      (parts[1] === 'teams' ? 'team' : 'player') + '"]');
    if (b) b.click();
  }
  if (view === 'players' && parts[1] && parts[2]) {
    const pl = playerBySlug(parts[1], parts[2]);
    if (pl) { renderPlayerDetail(pl); }
  } else if (view === 'players') {
    const card = document.getElementById('playercard');
    if (card) card.innerHTML = '';
    const sec = document.getElementById('v-players');
    if (sec) sec.classList.remove('detail-open');
  }
  renderCrumbs(view, parts);
  /* a NEW destination starts at the top; Back is left to the browser, which
     restores the scroll position it recorded for that entry */
  if (!ROUTE_POP) window.scrollTo({ top: 0 });
  ROUTE_POP = false;
}
let ROUTE_POP = false;
addEventListener('hashchange', () => { route(); });
addEventListener('popstate', () => { ROUTE_POP = true; });

function renderCrumbs(view, parts) {
  /* ⚠ A MATCH DETAIL OWNS ITS OWN CRUMB, and this used to delete it. The
     sweep ran after renderMatchDetail() had painted, so the breadcrumb and the
     back button vanished from every match page -- the detail rendered, then
     lost its way out. Nodes inside a detail host are that host's business. */
  document.querySelectorAll('.crumb,.backlink').forEach(n => {
    if (n.closest('#deskdetail,#scoredetail')) return;
    n.remove();
  });
  if (view === 'players' && parts[1] && parts[2]) {
    const pl = playerBySlug(parts[1], parts[2]);
    if (!pl) return;
    const host = document.getElementById('playercard');
    if (!host) return;
    let trail, back;
    if (ROUTE_ORIGIN === 'teams') {
      trail = '<a href="' + routeFor('teams') + '">Teams</a><span class="sep">&rsaquo;</span>' +
        '<a href="' + routeFor('teams', slug(pl.team)) + '">' + esc(pl.team) + '</a>' +
        '<span class="sep">&rsaquo;</span><b>' + esc(pl.name) + '</b>';
      back = ['&larr; Back to ' + esc(pl.team), routeFor('teams', slug(pl.team))];
    } else if (ROUTE_ORIGIN === 'stats') {
      trail = '<a href="' + routeFor('leaders', 'players') + '">Stats</a>' +
        '<span class="sep">&rsaquo;</span><b>' + esc(pl.name) + '</b>';
      back = ['&larr; Back to Stats', routeFor('leaders', 'players')];
    } else {
      trail = '<a href="' + routeFor('players') + '">Players</a>' +
        '<span class="sep">&rsaquo;</span><b>' + esc(pl.name) + '</b>';
      back = ['&larr; Back to Players', routeFor('players')];
    }
    const bar = document.createElement('div');
    bar.className = 'crumb';
    bar.innerHTML = trail;
    host.parentNode.insertBefore(bar, host);
    const bb = document.createElement('button');
    bb.type = 'button'; bb.className = 'backlink'; bb.innerHTML = back[0];
    bb.addEventListener('click', () => go(back[1]));
    host.parentNode.insertBefore(bb, host);
  }
  if (view === 'teams' && parts[1]) {
    const t = unslugTeam(parts[1]);
    const host = document.getElementById('teamcard');
    if (!t || !host) return;
    const bar = document.createElement('div');
    bar.className = 'crumb';
    bar.innerHTML = '<a href="' + routeFor('teams') + '">Teams</a>' +
      '<span class="sep">&rsaquo;</span><b>' + esc(t) + '</b>';
    host.parentNode.insertBefore(bar, host);
  }
}

document.querySelectorAll('nav button[role=tab], #moremenu button').forEach(b =>
  b.addEventListener('click', () => {
  closeMore();
  go(routeFor(b.dataset.v));
  return;
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
/* ⚠ A RANK ROW OPENS THE TEAM, IT DOES NOT UNFOLD IN PLACE. The row used to
   expand a pseudo-detail describing the projection; that same content already
   exists on the team page as "Projected six", so the expansion was a second
   half-answer competing with the real one. Keyboard reachable, because a row
   that only responds to a mouse is not a link. */
function openRankRow(tr) {
  const nm = tr && tr.dataset.team;
  if (!nm || !TEAMS[nm]) return;
  go(routeFor('teams', slug(nm)));
}
$('#rbody').addEventListener('click', e => {
  const tr = e.target.closest('tr.row'); if (tr) openRankRow(tr);
});
$('#rbody').addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const tr = e.target.closest('tr.row'); if (!tr) return;
  e.preventDefault(); openRankRow(tr);
});
/* A row in the Top 25 opens that team, the same as clicking it anywhere else --
   a ranking you cannot click through from is a dead end. */
const t25body = document.getElementById('t25body');
if (t25body) t25body.addEventListener('click', e => {
  const tr = e.target.closest('tr[data-team]'); if (!tr) return;
  const nm = tr.dataset.team;
  if (!TEAMS[nm]) return;
  const q = document.getElementById('tmq'); if (q) q.value = nm;
  go(routeFor('teams', slug(nm)));
});
['q', 'conf', 'top'].forEach(id => $('#' + id).addEventListener('input', renderRank));
/* The secondary control is a route like any other, so Back works from it. */
const refpick = document.getElementById('refpick');
if (refpick) refpick.addEventListener('change', () => {
  if (refpick.value) go(routeFor('rankings', refpick.value));
});
/* Reference columns are available, not compulsory. Thirteen columns wide is a
   spreadsheet; the five a voter reads are the default and the rest are one
   click away. */
const refcols = document.getElementById('refcols');
if (refcols) {
  const applyRef = () => {
    document.querySelector('#v-rankings table.rk3')
      .classList.toggle('hideref', !refcols.checked);
  };
  refcols.addEventListener('change', applyRef); applyRef();
}
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
/* A CALENDAR DATE, THE WAY A READER READS ONE. "2026-08-30" is unambiguous and
   makes the reader do arithmetic to find out it is a Sunday. Mirror of
   build_hub.day_label(); a bare ISO date on a scoreboard is a formatting
   failure, not a data one, and the page was printing both formats at once --
   the week cards said "Today" while the slate directly above said "2026-08-24".
   No timezone is involved: an ISO calendar date is already a day. */
function dayLabel(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso || '';
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  if (iso === today) return 'Today';
  const p = iso.split('-').map(Number);
  const d = new Date(Date.UTC(p[0], p[1] - 1, p[2]));
  const t = new Date(today + 'T00:00:00Z');
  const days = Math.round((d - t) / 86400000);
  if (days === 1) return 'Tomorrow';
  if (days === -1) return 'Yesterday';
  // formatToParts, not format(): en-US renders "Sat, Aug 29" with a comma while
  // build_hub.day_label() renders "Sat Aug 29" without one. Two mirrors of the
  // same rule that disagree on punctuation put both spellings on one page --
  // the schedule table is server-rendered and the fixture list is not, and they
  // sit two inches apart. Assembled from parts so the two cannot drift.
  const p2 = new Intl.DateTimeFormat('en-US',
    { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric' })
    .formatToParts(d).reduce((a, x) => (a[x.type] = x.value, a), {});
  return p2.weekday + ' ' + p2.month + ' ' + p2.day;
}

/* ══ THE RULERS ═══════════════════════════════════════════════════════════
   ⚠ THIS TABLE IS NOT WRITTEN HERE. It is emitted from build_hub.RULERS, so
   the Python render path and this one cannot say different things about the
   same ranking -- which they previously could, and did: the same fixture read
   #15 in one view and #21 in another with nothing on screen to tell a reader
   the two numbers were measuring different things.
   Each entry is [visible label, compact label, what it actually is]. */
const RULERS = {{RULERS_JSON}};

/* THE ONE WAY A RANK IS RENDERED. Mirror of build_hub.rank_badge().
   ⚠ BASIS IS REQUIRED AND THERE IS NO DEFAULT. The previous version of this
   function took only a number and hard-coded AVCA, which was correct at every
   call site it had and would have been silently wrong at the next one. An
   unknown basis renders a loud marker; test_rulers.py asserts that marker
   never reaches a built page. A quiet fallback would restore the bug. */
/* The plain-text twin, for the handful of consumers that render text rather
   than markup. Same table, same labels. */
function rankText(basis, v, compact) {
  if (!v) return '';
  const r = RULERS[basis];
  if (!r) return 'rank basis? ';
  return (compact ? r[1] : r[0]) + ' #' + v + ' ';
}
function rankHTML(basis, v, compact) {
  if (v === null || v === undefined || v === '' || !v) return '';
  const r = RULERS[basis];
  if (!r) return '<i class="rnk rnkbad" title="no ruler named">rank basis?</i> ';
  return '<i class="rnk" title="' + esc(r[2]) + '">' +
    '<span class="rank-label">' + esc(compact ? r[1] : r[0]) + '</span>#' +
    esc(String(v)) + '</i> ';
}
/* Kept as the AVCA shorthand the scoreboard-feed views already read well with.
   It is a NAMED call through the component, not a second implementation. */
function rank(v) { return rankHTML('avca', v); }
/* ---- THE WEEK'S HEADLINE MATCHES -------------------------------------
   What a scoreboard puts at the top: not every fixture, the ones worth
   watching. Ranked-versus-ranked first, ordered by how good the pair is
   (the two ranks added -- #2 v #7 beats #11 v #12), then the best
   single-ranked games if there are not five of those.

   ⚠ THE RANKS ARE THE AVCA COACHES POLL, not ours, and that is deliberate:
   an official poll is the shared language a reader already speaks, so it is
   what sits next to a team name. Our own order lives on the Rankings and
   Digby's Top 25 tabs, where it is labelled as ours. Verified rather than
   assumed -- ncaa.com's scoreboard rank matches the AVCA poll on every team
   where the two orders differ (BYU 24 to our 16, Kansas 15 to our 21,
   Indiana 16 to our 24). */
function renderWeek() {
  const box = document.getElementById('weekbox');
  if (!box || typeof WEEK === 'undefined') return;
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  const up = WEEK.filter(r => r.d >= today);
  const score = r => {
    const a = +r.ar || 0, h = +r.hr || 0;
    if (a && h) return a + h;              // both ranked: lower is better
    if (a || h) return 100 + (a || h);     // one ranked: after every pairing
    return 9999;
  };
  const top = up.filter(r => r.ar || r.hr)
                .sort((x, y) => score(x) - score(y) || x.d.localeCompare(y.d))
                .slice(0, 5);
  if (!top.length) { box.hidden = true; return; }
  box.hidden = false;
  const both = top.filter(r => r.ar && r.hr).length;
  $$('weekmeta').textContent =
    (both ? (both + ' ranked v ranked') : 'best of the next seven days')
    + ' \u00b7 ranks are the AVCA coaches poll';
  /* WHOSE NUMBER IS THAT? The inline rank is the AVCA coaches poll -- the
     official one -- and it now says so on hover instead of appearing as a bare
     numeral. Where our own Top 25 disagrees, the disagreement is printed rather
     than hidden: a reader who sees "24 BYU" on a page that ranks BYU 16th is
     owed the second number, and a page that shows only one of them is claiming
     more agreement than exists. Both ranks are computed server-side (see the
     TEAMS temporal-dead-zone note in build()). */
  const rk = rank;
  const ours = r => {
    const bits = [];
    if (r.ao && r.ao != r.ar) bits.push(r.a + ' ' + r.ao);
    if (r.ho && r.ho != r.hr) bits.push(r.h + ' ' + r.ho);
    return bits.length
      ? '<div class="ourrk" title="our rating disagrees with the coaches poll">'
        + 'our Top 25: ' + bits.join(' \u00b7 ') + '</div>'
      : '';
  };
  $$('weekcards').innerHTML = top.map(r =>
    '<div class="card soon' + (r.ar && r.hr ? ' marquee' : '') + '">' +
    /* the server label if present, otherwise format it here -- never the raw
       ISO string, which is what this fallback used to be */
    '<div class="cd">' + (r.dl || dayLabel(r.d)) + (r.t ? ' \u00b7 ' + r.t : '') +
      (r.ar && r.hr ? '<span class="tag">ranked v ranked</span>' : '') + '</div>' +
    '<div class="mt"><div class="side">' + rk(r.ar) + logo(r.a) + r.a + '</div>' +
    '<div class="side">' + rk(r.hr) + logo(r.h) + r.h + '</div></div>' +
    ours(r) +
    '<div class="venue">' + (r.venue
        ? r.venue + (r.city ? ', ' + r.city + (r.st ? ' ' + r.st : '') : '')
        : 'venue not listed') + '</div></div>').join('');
}

/* TODAY'S FIXTURES WITHOUT A SERVER. The live band and the slate were both fed
   by /api/live, which only exists behind live_server.py -- so on the PUBLISHED
   page the fetch failed and the whole block stayed hidden. The published page is
   the one being read on a phone, and "what is on today" is the first thing a
   scoreboard owes anyone.
   In-progress SCORES genuinely cannot work on a static host; the slate can,
   because the schedule is already embedded in the page. So the fixtures come
   from SCHED and the live scores are an upgrade applied when a server is there,
   rather than the whole block depending on one. */
const WEEK = {{WEEK_JSON}};
function slateFromSchedule() {
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  return WEEK
    .filter(r => r.d === today)
    .map(r => ({ date: r.d, away: r.a, home: r.h, time: r.t,
                 away_rank: r.ar, home_rank: r.hr, state: 'pre' }));
}

async function pollLive() {
  let d = null;
  try {
    const r = await fetch('/api/live', { cache: 'no-store' });
    if (r.ok) d = await r.json();
  } catch (e) { d = null; }
  /* no server: fall back to the schedule that is already on the page */
  const all = (d && d.games && d.games.length) ? d.games : slateFromSchedule();
  /* A match that has ENDED must leave the live band even while the feed still
     reports it in progress. The scoreboard flips `period` to FINAL before the
     state field catches up, so for a few minutes the band showed a card headed
     LIVE whose own first line said FINAL. Trust whichever source says it is
     over. */
  const isOver = g => /final|complete/i.test(g.period || '') ||
                      /final|^f$/i.test(g.state || '') ||
                      /* three sets is a win by rule -- the feed can lag both
                         state and period past the final rally */
                      (+g.away_sets >= 3 || +g.home_sets >= 3);
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
  /* ⚠ THE SAME STRING-TIME SORT THAT BROKE THE SCOREBOARD LIVES HERE TOO.
     Concatenating date+time and comparing lexically is right about the date
     and wrong about the clock: "6:00 AM PT" sorts after "5:30 PM PT" because
     '6' > '5'. Compare the date as a string (ISO, so that is correct) and the
     time as MINUTES. Fixing one call site and not the other is how two views
     end up disagreeing about the same slate. */
  const pre = all.filter(g => g.state === 'pre' && g.date >= todayISO)
                 .sort((a, b) => String(a.date).localeCompare(String(b.date)) ||
                   ((ma, mb) => (ma === null && mb === null) ? 0
                     : ma === null ? 1 : mb === null ? -1 : ma - mb
                   )(tMinutes(a.time), tMinutes(b.time)));
  const todays = pre.filter(g => g.date === todayISO);
  const soon = todays.length ? todays
                            : pre.filter(g => pre.length && g.date === pre[0].date);
  /* ⚠ THIS BRANCH HAD NEVER RUN, AND IT WOULD HAVE THROWN TOMORROW. The
     Scoreboard rebuild removed the slate band's markup -- #todaymeta,
     #todaycards and the `.soon` label are all gone, and #today survives as an
     empty hidden div. The live band below was guarded when that happened; this
     one was not, because reaching it needs a match in state 'pre' and every
     day the page had rendered held two finals. On the first Friday, with 196
     scheduled, `querySelector('#today .soon').textContent` throws -- and the
     throw is inside the poll callback, so the just-finished band and the live
     band never run either, every 60 seconds, all day.
     Guarded the same way as the live band: if the markup is not here, this
     poller has nothing to say and says nothing. */
  const tbox = document.getElementById('today');
  const tmeta = $$('todaymeta'), tcards = $$('todaycards');
  const tlabel = tbox && tbox.querySelector('.soon');
  if (!tbox || !tmeta || !tcards || !tlabel) { /* band removed -- nothing to do */ }
  else if (!soon.length) { tbox.hidden = true; }
  else {
    tbox.hidden = false;
    tlabel.textContent = todays.length ? 'Later today' : 'Next up';
    /* ⚠ CAP IT, AND NEVER SILENTLY. On the first Friday this band would have
       rendered 196 cards above the curated rundown -- a wall in the one place
       the page is supposed to be answering "what should I watch". The count
       beside the heading is the TRUE total, and what is not shown is stated
       with a link to the view that holds it. A cap nobody is told about reads
       as "this is all there is". */
    const SLATE_CAP = 12;
    const shownSoon = soon.slice(0, SLATE_CAP);
    tmeta.textContent =
      soon.length + ' scheduled' + (todays.length ? '' : ' \u00b7 ' + dayLabel(soon[0].date)) +
      (soon.length > SLATE_CAP
        ? ' \u00b7 showing the first ' + SLATE_CAP : '');
    tcards.innerHTML = shownSoon.map(g =>
      '<div class="card soon"><div class="cd">' + dayLabel(g.date) + '</div>' +
      '<div class="mt"><div class="side">' + rank(g.away_rank) + logo(g.away) + g.away + '</div>' +
      '<div class="side">' + rank(g.home_rank) + logo(g.home) + g.home + '</div></div>' +
      '<div class="venue"><span class="tipoff">' + (g.time || 'time TBA') + '</span></div>' +
      '</div>').join('') +
      (soon.length > SLATE_CAP
        ? '<a class="card morecard" href="' + routeFor('scores') + '">' +
          '<b>+' + (soon.length - SLATE_CAP) + ' more</b>' +
          '<span>on the scoreboard</span></a>' : '');
  }

  /* JUST FINISHED, not yet crawled. Rendered from the feed so a match is never
     invisible: it leaves the live band the moment the scoreboard says FINAL,
     but the results list below is built from the last crawl and will not carry
     it until the next one runs. Without this it falls between the two. */
  /* ⚠ CHECKING THE PARENT IS NOT CHECKING THE CHILDREN. `jbox` was tested and
     then #justinmeta and #justincards were written to unchecked -- the same
     shape as the slate-band crash above, one level down. They exist today;
     the slate band's did too, until a rebuild removed them. */
  const jbox = document.getElementById('justin');
  const jmeta = $$('justinmeta'), jcards = $$('justincards');
  if (jbox && jmeta && jcards) {
    const known = new Set([...document.querySelectorAll('#resultcards [data-gid]')]
      .map(el => el.dataset.gid));
    const fresh = justEnded.filter(g => !known.has(String(g.id)));
    if (!fresh.length) { jbox.hidden = true; }
    else {
      jbox.hidden = false;
      /* ⚠ SAY WHAT IS ACTUALLY HAPPENING. "not yet in the archive below" reads
         as if the result is missing or the site is broken. It is neither: the
         match IS final, and the ratings, records and player stats that depend
         on it are recomputed by the next verified refresh rather than the
         instant the scoreboard flips. Naming that is the difference between a
         site that looks stale and one that is honest about its own pipeline. */
      jmeta.textContent =
        fresh.length + (fresh.length === 1 ? ' result' : ' results') +
        ' \u2014 final, awaiting the next rating refresh';
      jcards.innerHTML = fresh.map(g => {
        const aw = +g.away_sets > +g.home_sets;
        return '<div class="card done"><div class="cd">' + dayLabel(g.date || '') +
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

  /* ⚠ THIS BAND'S MARKUP IS GONE. The Scoreboard rebuild removed the old
     live/just-finished/what-changed stack from the top of that page, and this
     poller still ran against it -- `box.hidden` on a null throws, which would
     have taken the rest of the poll callback with it. The Scoreboard renders
     its own live lane from the same LIVE_BY_ID. Guarded rather than deleted:
     the function still serves the elements that DO survive. */
  const box = $$('live');
  if (!box) return;
  if (!live.length) { box.hidden = true; return; }
  box.hidden = false;
  const lm = $$('livemeta');
  if (lm) lm.textContent =
    (d.error ? d.error + ' \u00b7 ' : '') + 'updated ' + (d.updated || '');
  const lc = $$('livecards');
  if (!lc) return;
  /* 29 matches share a 4:00 PM slot on the first Friday, so "everything that
     is live" is a plausible 29-card wall. Same rule as the slate: cap, and say
     what is not shown. */
  const LIVE_CAP = 12;
  const liveShown = live.slice(0, LIVE_CAP);
  lc.innerHTML = liveShown.map(g => {
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
  }).join('') +
    (live.length > LIVE_CAP
      ? '<a class="card morecard" href="' + routeFor('scores') + '">' +
        '<b>+' + (live.length - LIVE_CAP) + ' more live</b>' +
        '<span>on the scoreboard</span></a>' : '');
  if (lm) lm.textContent += (live.length > LIVE_CAP
    ? ' \u00b7 showing ' + LIVE_CAP + ' of ' + live.length : '');
}
pollLive();
setInterval(pollLive, 60000);


/* ---- logos, box scores, player pages ---------------------------------- */
const LOGOS = {{LOGOS_JSON}};
const COLORS = {{COLORS_JSON}};
const BOXES = {{BOXES_JSON}};
const PLAYERS = {{PLAYERS_JSON}};
const PRANK = {{PRANK_JSON}};
const ROSTER = {{ROSTER_JSON}};
/* ⚠ DECLARED HERE, BESIDE THE PAYLOAD, AND NOT NEXT TO THE CODE THAT USES IT.
   These sat with renderPrank() ~2,000 lines further down, which is AFTER the
   router that calls it -- and a `const` in the temporal dead zone THROWS on
   access rather than reading as undefined, so the whole view rendered blank
   with no message. Same family as the `const TEAMS` bug this project has now
   paid for three times. A `typeof` guard does not help; only the ordering
   does. */
const PRK_ORDER = ['ALL', 'OH', 'OPP', 'MB', 'S', 'LDS'];
/* ⚠ TWO DIFFERENT SPLITS, AND THEY USED TO SHARE A NAME. Whether she plays the
   back row (proven by serving) is not the same question as how much
   serve-receive she is trusted with, and labelling the passing split
   "six-rotation" called 658 outsides front-row when only 112 never enter the
   back row. */
const PRK_ROLES = {
  OH:  [['', 'All'], ['six', 'Six-rotation'], ['front', 'Front-row only']],
  OPP: [['', 'All'], ['six', 'Six-rotation'], ['front', 'Front-row only']]
};
let PRK_ROLE = '';
const PRK_FLAB = { kps: 'kills/set', hit: 'hitting %', dps: 'digs/set',
  bps: 'blocks/set', sps: 'aces/set', asps: 'assists/set',
  aps: 'swings/set' };
let PRK_POS = 'OH', PRK_MODE = 'power';
const POSFULL = { OH: 'Outside', OPP: 'Opposite', MB: 'Middle',
  S: 'Setter', LDS: 'Libero/DS' };
/* ⚠ WITH THE PAYLOAD, NOT WITH THE FUNCTION. Seventh temporal-dead-zone
   blank view in this file: a top-level const read before its declaration
   line has run THROWS, and the throw lands inside showTeam's assembly, so
   the team card renders with its sections orphaned and no error on screen. */
const TD_GROUPS = [['overview', 'Overview'], ['matches', 'Matches'],
                   ['roster', 'Roster'], ['numbers', 'Numbers'],
                   ['scouting', 'Scouting'], ['outlook', 'Outlook']];
/* Heading -> section. A heading nobody has claimed lands in Numbers, which is
   visible and wrong-ish rather than invisible and lost. */
const TD_MAP = [
  [/^results/i, 'matches'], [/^upcoming/i, 'matches'], [/^next up/i, 'matches'],
  [/^postseason/i, 'outlook'], [/^outlook/i, 'outlook'],
  [/^projected six/i, 'roster'], [/^full roster/i, 'roster'],
  [/^returning avca/i, 'roster'], [/^biggest losses/i, 'roster'],
  [/^roster turnover/i, 'roster'], [/^who arrived/i, 'roster'],
  [/^team stats/i, 'numbers'], [/^match by match/i, 'numbers'],
  [/^parts vs whole/i, 'numbers'],
  [/^what it returns/i, 'numbers'], [/power/i, 'numbers'],
  [/^side-out by rotation/i, 'scouting'], [/^serving rotation/i, 'scouting'],
  [/^who came in/i, 'scouting'], [/^most-started six/i, 'scouting'],
  [/^rotation/i, 'scouting']
];
let TD_TAB = 'overview';

const PRK_ROLELAB = { six: '6-rotation', front: 'front-row only' };
const PRK_PROLELAB = { passer: 'passes', seldom: 'seldom passes',
  primary: 'primary passer', reserve: 'reserve' };



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
/* BALLOT-CONST-BEGIN */
/* ---- BALLOT WORKSHOP CONSTANTS AND HELPERS ---------------------------- */
const SEASON_YEAR = {{SEASON_YEAR}};
/* whether a RESUME rank exists yet at all -- the workshop must say "not active"
   rather than print a rank it does not have (R5) */
const RESUME_ACTIVE = {{RESUME_ACTIVE_JS}};

/* BALLOT-CONST-END */

/* ⚠ SHARED, AND IT USED TO BE PRIVATE. esc() was written for the ballot -- the
   only place that echoed free text the user typed -- so it lived inside the
   BALLOT-CONST region that the public build strips. The Matchday phase then
   made it a dependency of matchRow(), ribbonHTML(), renderLedger() and
   renderMatchDetail(), all of which run on the PUBLIC page. Result: the
   published Scores ledger threw "esc is not defined" and rendered ZERO rows,
   and opening a match did nothing. Every test passed, because the public
   checks only ever asserted what must be ABSENT -- nothing asserted the page
   still worked. It lives outside the fence now. */
/* ⚠ ONE DEFINITION OF THE DIVISION CAVEAT. It is rendered in four places --
   the player match log, the team page's Results row and its stats note, and
   the team stats table's row tooltip. Written out separately they drift, and
   the first draft already had: the table tooltip read "1 of these 1 matches
   is", which nobody would write on purpose. `where` names the subject so one
   sentence reads naturally in each spot. */
function nonDiPhrase(n, total, where) {
  if (!n) return '';
  if (n === total) {
    return (total === 1 ? 'The only match ' : 'Every match ') + where +
           ' is against a non-Division-I opponent';
  }
  return n + ' of these ' + total + ' matches ' +
    (n === 1 ? 'is against a non-Division-I opponent'
             : 'are against non-Division-I opponents');
}
const NONDI_WHY = 'Nothing is filtered out \u2014 filtering would change what ' +
  'the numbers mean without saying so.';

/* points per set, rendered the one way this site renders it */
function ppsFmt(v) {
  const n = Number(v);
  return (v === null || v === undefined || !isFinite(n)) ? '\u2014' : n.toFixed(2);
}

function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
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
/* ⚠ THE DIRECTORY SEARCHES ALL OF DIVISION I, NOT ONLY WHOEVER HAS PLAYED.
   PLAYERS holds a 2026 box-score line, which in August is 149 people -- so a
   search for a First-Team All-American who has not played yet came back empty,
   reading as "never heard of her" rather than "the season has not started".
   ROSTER is every rated player; a name in both resolves to the PLAYERS entry,
   because that one has a full season card behind it. */
function playerSearch(q) {
  const seen = Object.create(null);
  const out = [];
  PLAYERS.forEach(p => {
    if (!q || (p.name + ' ' + p.team).toLowerCase().includes(q)) {
      seen[p.team + '|' + p.name] = 1;
      out.push({ live: p, r: null, name: p.name, team: p.team });
    }
  });
  if (typeof ROSTER !== 'undefined') {
    ROSTER.forEach(r => {
      const k = r.t + '|' + r.n;
      if (seen[k]) return;
      if (!q || ((r.n || '') + ' ' + (r.t || '')).toLowerCase().includes(q)) {
        seen[k] = 1;
        out.push({ live: null, r: r, name: r.n, team: r.t });
      }
    });
  }
  return out;
}

/* A card for a player who has not been on court this season.
   ⚠ SHE CANNOT USE showPlayer(). That card is built from 2026 box-score fields
   -- points per set, sets, a match log -- and she has none of them. Filling
   those with zeros would render a player who played and did nothing, which is
   a different claim from a player who has not played (R5). This card states
   last season and her standing, and nothing else. */
function showRated(r) {
  const card = document.getElementById('playercard');
  if (!card || !r) return;
  const teamHref = routeFor('teams', slug(r.t || ''));
  const sub = [
    '<a class="parentlink" href="' + teamHref + '">' + esc(r.t || '') + '</a>',
    r.c ? esc(r.c) : null,
    r.p ? esc(POSFULL[r.p] || r.p) : null,
    r.nu ? '#' + esc(String(r.nu)) : null
  ].filter(Boolean).join(' · ');
  const board = (typeof PRANK !== 'undefined' && PRANK.boards)
    ? (PRANK.boards[r.p] || {}) : {};
  const chips = [];
  if (r.r != null) {
    chips.push('<span class="rchip pw"><b>POWER</b> #' + r.r + '<i>of ' +
      (board.n || '?') + ' ' +
      esc((POSFULL[r.p] || r.p || '').toLowerCase()) + 's</i></span>');
  }
  chips.push('<span class="rchip off"><b>RÉSUMÉ</b> —' +
    '<i>no 2026 line yet</i></span>');
  if (r.pc != null) {
    chips.push('<span class="rchip"><b>' + r.pc.toFixed(1) +
      '</b><i>percentile at her position</i></span>');
  }
  const stat = (lab, v, f) => v == null ? '' :
    '<span class="chip">' + lab + ' <b>' + f(v) + '</b></span>';
  const line = [
    stat('Kills/set', r.k, x => x.toFixed(2)),
    stat('Hit%', r.h, x => pct(x)),
    stat('Digs/set', r.d, x => x.toFixed(2)),
    stat('Blocks/set', r.b, x => x.toFixed(2)),
    stat('Sets', r.s, x => String(x))
  ].filter(Boolean).join('');
  const tags = [];
  if (r.ro) tags.push(PRK_ROLELAB[r.ro] || r.ro);
  if (r.rc != null) tags.push('takes ' + Math.round(r.rc * 100) +
    '% of serve-receive');
  const q = encodeURIComponent((r.n || '') + ' ' + (r.t || '') +
    ' volleyball highlights');
  card.innerHTML =
    '<div class="ratingbox"><div class="rchips">' + chips.join('') + '</div>' +
      (tags.length ? '<div class="rtags">' + tags.map(t =>
        '<span class="rtag">' + esc(t) + '</span>').join('') +
        '<span class="munk">2025</span></div>' : '') +
      '<div class="munk rfoot">Ranked against ' +
      esc((POSFULL[r.p] || r.p || '').toLowerCase()) +
      's only — never across positions.</div></div>' +
    '<div class="thead phead">' + avatar(r.p, r.t, 72) + '<div><h2>' +
      '<a class="parentlink" href="' + teamHref + '">' + logo(r.t, 'lg') +
      '</a>' + esc(r.n || '') + '</h2>' +
      '<div class="sub">' + sub + '</div>' +
      '<div class="chips">' + line + '</div>' +
      '<div class="pvid"><span class="pxlab">Video</span>' +
        '<a href="https://www.youtube.com/results?search_query=' + q + '" ' +
        'target="_blank" rel="noopener noreferrer">Search YouTube</a>' +
        '<a href="https://www.google.com/search?tbm=vid&q=' + q + '" ' +
        'target="_blank" rel="noopener noreferrer">Search video</a>' +
        '<span class="munk">a search, not a verified reel</span></div>' +
    '</div></div>' +
    '<div class="tsec"><h3>2025 season</h3><div class="body">' +
      '<p class="tnote">These are <b>last season’s</b> numbers. She has ' +
      'not been on court in ' + SEASON_YEAR + ' yet, so there is no 2026 line ' +
      'and no match log to show.</p></div></div>';
  card.scrollIntoView({ block: 'start' });
}

function renderPlayers() {
  const q = document.getElementById('pq').value.toLowerCase().split('·')[0].trim();
  const hits = playerSearch(q);
  const rows = hits.filter(x => x.live).map(x => x.live);
  const only = hits.filter(x => !x.live).map(x => x.r);
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
  /* ⚠ THE NOT-YET-PLAYED ROWS RENDER UNDER THEIR OWN HEADING RATHER THAN
     MIXED IN. Their columns are LAST SEASON's; putting them in the same table
     as 2026 rates would compare two different seasons in one sort. */
  const host = document.getElementById('pnotyet');
  if (host) {
    /* ⚠ NOTHING UNTIL SHE TYPES, AND THAT IS THE FIX AFTER TWO WRONG ONES.
       I blamed the row count, then the crests, then the per-keystroke render,
       and each time the tab still hung -- because the hang was on ROUTE ENTRY,
       with an empty query, before anybody had typed at all. Whatever the
       browser is doing with a 2,679-row search on top of a 10 MB page and
       5,000 images, the honest answer is that this list is for FINDING a
       player, not for browsing two thousand of them. An empty box now renders
       an invitation instead of a wall, which is the better product as well as
       the thing that does not fall over. */
    const show = q ? only.slice(0, 40) : [];
    if (!q && only.length) {
      host.innerHTML = '<p class="tnote munk">' + only.length + ' more rated ' +
        'players have not been on court yet this season. Type a name or a ' +
        'team above to find one.</p>';
    } else {
    host.innerHTML = !show.length ? '' :
      '<div class="panel notyet"><div class="nyhd">Not yet on court this ' +
      'season <span class="munk">' + only.length + ' rated ' +
      (only.length === 1 ? 'player' : 'players') + ' · the numbers below are ' +
      '2025</span></div><div class="scroll"><table><thead><tr>' +
      '<th class="l">Player</th><th class="l">Team</th><th>Pos</th>' +
      '<th>Cl</th><th>Sets</th><th>K/set</th><th>Hit%</th>' +
      '<th>Rank at her position</th></tr></thead><tbody>' +
      show.map(r =>
        '<tr class="nyrow" data-nyk="' + esc(r.t + '|' + r.n) + '">' +
        '<td class="l tm"><b>' + esc(r.n || '') + '</b>' +
          (r.nu ? ' <span class="munk">#' + esc(String(r.nu)) + '</span>' : '') +
        '</td>' +
        /* ⚠ NO CREST IN THIS TABLE, AND THAT IS THE FIX, NOT A STYLE CHOICE.
           Each crest is a REMOTE image, so 200 rows meant 200 requests -- and
           this table rebuilds on every keystroke, so typing a name fired
           thousands of image loads and hung the renderer. Measured: building
           and attaching 200 rows costs 8ms and 31ms, so the rows were never
           the problem; the images were. The team name is text here. */
        '<td class="l tm">' + esc(r.t || '') + '</td>' +
        '<td class="n">' + esc(r.p || '') + '</td>' +
        '<td class="n">' + esc(r.c || '—') + '</td>' +
        '<td class="n">' + (r.s == null ? '—' : r.s) + '</td>' +
        '<td class="n">' + (r.k == null ? '—' : r.k.toFixed(2)) + '</td>' +
        '<td class="n">' + (r.h == null ? '—' : pct(r.h)) + '</td>' +
        '<td class="n">' + (r.r == null ? '—' : '#' + r.r) + '</td>' +
        '</tr>').join('') + '</tbody></table></div>' +
      (only.length > show.length
        ? '<p class="tnote munk">Showing ' + show.length + ' of ' +
          only.length + ' — narrow the search to see the rest.</p>' : '') +
      '</div>';
    }
  }
  const total = rows.length + only.length;
  document.getElementById('pcnt').textContent =
    total + (total === 1 ? ' matching player' : ' matching players') +
    (only.length ? ' · ' + rows.length + ' with a 2026 line' : '');
  if (rows.length === 1 && !only.length) showPlayer(rows[0]);
}
/* The router's entry point for a player. showPlayer() paints the card; this
   also makes the DIRECTORY TABLE stop competing with an exact selection --
   a detail page is a page, not a highlighted row above the full list. */
/* 13 K · 11 E · 42 ATT · .048 HIT · 6 DIG · 3 ACE · 16.0 PTS
   Abbreviations a box score already uses, so nothing has to be learned. A
   value we do not have renders as an em dash and keeps its label. */
function statLine(p) {
  const n = v => (v === null || v === undefined) ? '&mdash;'
    : (Math.round(v * 10) % 10 === 0 ? String(Math.round(v)) : v.toFixed(1));
  const bits = [
    [n(p.k), 'K'], [n(p.e), 'E'], [n(p.ta), 'ATT'],
    [p.hit === null || p.hit === undefined ? '&mdash;' : pct(p.hit), 'HIT'],
    [n(p.digs), 'DIG'], [n(p.aces), 'ACE'],
    [(p.pts === null || p.pts === undefined) ? '&mdash;' : p.pts.toFixed(1), 'PTS']
  ];
  return bits.map(b => '<span class="sv">' + b[0] +
    '</span><span class="sl">' + b[1] + '</span>').join('<i class="sd">·</i>');
}

(function wirePlayerDir() {
  const b = document.getElementById('pbackdir');
  if (b) b.addEventListener('click', () => go(routeFor('players')));
})();

function renderPlayerDetail(p) {
  const sec = document.getElementById('v-players');
  if (sec) sec.classList.add('detail-open');
  /* ⚠ THE ROUTE IS THE TRUTH, AND IT USED TO LOSE A RACE TO THE SEARCH BOX.
     renderPlayers() ends with `if (rows.length === 1) showPlayer(rows[0])` --
     a convenience from before routing existed. So arriving at
     #/players/kentucky/kassie-o-brien while the box still held "Brooklyn
     DeLeye" painted Kassie, then immediately repainted Brooklyn over her: the
     URL said one player, the breadcrumb said one player, and the card showed
     another. Nothing errored and both halves looked right on their own.
     Two fixes, and both are needed. The box is made to AGREE with the route
     rather than left holding a stale name, and the routed player is painted
     LAST so no later auto-open can win. */
  const q = document.getElementById('pq');
  if (q && q.value.trim() !== p.name) { q.value = p.name; }
  renderPlayers && renderPlayers();
  showPlayer(p);
}

/* Her standing on her own position's board, with the two things that decide
   how much it is worth: how thin the sample is, and how well the box score
   supports that position at all. */
/* The team-relative half of an outcome rate. Absolute kill rate off her sets
   mostly measures her hitters and absolute serve-win rate mostly measures her
   team's defence and schedule -- the difference from her own team is the part
   that belongs to her, so it is shown beside the raw figure rather than
   instead of it. */
/* ⚠ AN MIT LICENCE IS A CONDITION, NOT A COURTESY. Passing, setting, serving,
   back-row share and rotation side-out are all derived from the ncaavolleyballr
   play-by-play mirror, and the credit has to travel with them. It existed on
   the old serving-rotation panel and nowhere else, so four new surfaces were
   rendering that data uncredited. One definition, used by all of them. */
const PBP_CREDIT = 'From NCAA play-by-play via the ncaavolleyballr dataset ' +
  '(J. R. Stevens, MIT). Derived here.';

function relBit(v) {
  /* ⚠ PLAIN TEXT, NOT MARKUP. These strings go through esc() at render time --
     which is correct and should stay that way -- so a bold tag written here
     printed on the card as its own angle brackets instead of as emphasis. */
  if (v == null) return '';
  const sign = v > 0 ? '+' : '\u2212';
  return ' (' + sign + Math.abs(Math.round(v * 100)) + ' vs team)';
}

function ratingHTML(p) {
  const r = p.rt;
  if (!r) return '';
  const SUPLAB = { good: 'well supported', fair: 'partly supported',
                   weak: 'weakly supported' };
  const posn = POSFULL[r.pos] || r.pos;
  /* ⚠ RESUME IS ABSENT, NOT LAST, FOR A PLAYER WITH NO SEASON LINE. Ranking
     her at the bottom would be a claim; having no resume yet is the fact. */
  const chips = [
    '<span class="rchip pw"><b>POWER</b> #' + r.pwr + '<i>of ' +
      (r.n || '?') + ' ' + esc(posn.toLowerCase()) + 's</i></span>',
    (r.rsr != null
      ? '<span class="rchip"><b>RÉSUMÉ</b> #' + r.rsr +
        '<i>this season</i></span>'
      : '<span class="rchip off"><b>RÉSUMÉ</b> —' +
        '<i>no 2026 line yet</i></span>')
  ];
  if (r.pct != null) {
    chips.push('<span class="rchip"><b>' + r.pct.toFixed(1) +
      '</b><i>percentile at her position</i></span>');
  }
  const tags = [];
  if (r.role) tags.push(PRK_ROLELAB[r.role] || r.role);
  if (r.prole) tags.push(PRK_PROLELAB[r.prole] || r.prole);
  if (r.brs != null) {
    tags.push(Math.round(r.brs * 100) + '% of swings from the back row');
  }
  const ps = r['pass'] || {};
  if (ps.recv_share != null) {
    tags.push('takes ' + Math.round(ps.recv_share * 100) + '% of serve-receive');
  }
  if (ps.sideout != null) {
    tags.push('sides out ' + Math.round(ps.sideout * 100) + '% when she passes' +
      relBit(ps.sideout_rel));
  }
  /* ⚠ TWO SKILLS THE BOX SCORE CANNOT SEE, AND BOTH CARRY THEIR SAMPLE.
     An assist counts a ball that became a kill, which measures the hitter as
     much as the setter; what her hitters do WHEN SHE SETS, against what the
     same team does overall, is closer to her. And aces per set rewards the ace
     while ignoring the commoner thing a good server does, which is stop the
     other side getting out of system. */
  if (ps.set_kill_rate != null) {
    /* ⚠ NO "vs team" FOR A PRIMARY SETTER, AND THE CARD SAYS WHY RATHER THAN
       GOING QUIET. She delivers most of her team's balls, so she IS the
       baseline and the difference would be near zero by construction. */
    const solo = ps.set_kill_rel_suppressed;
    tags.push('her sets are killed ' + Math.round(ps.set_kill_rate * 100) +
      '% of the time' + relBit(ps.set_kill_rel) +
      ' · ' + ps.set_att + ' swings' +
      (solo ? ' · sets ' + Math.round(solo * 100) +
        '% of her team\u2019s balls, so there is no one to compare her with'
        : ''));
  }
  if (ps.srv_win != null) {
    tags.push('her team wins ' + Math.round(ps.srv_win * 100) +
      '% of rallies she serves' + relBit(ps.srv_win_rel) +
      ' · ' + ps.srv_rally + ' rallies');
  }
  const thin = !r.w ? 'rated on last season only'
    : (Math.round(r.w * 100) + '% of this rating is this season');
  return '<div class="ratingbox">' +
    '<div class="rchips">' + chips.join('') + '</div>' +
    (tags.length ? '<div class="rtags">' + tags.map(t =>
      '<span class="rtag">' + esc(t) + '</span>').join('') +
      '<span class="munk">2025</span></div>' : '') +
    (tags.length ? '<div class="munk rfoot">' + esc(PBP_CREDIT) + '</div>' : '') +
    '<div class="munk rfoot">Ranked against ' + esc(posn.toLowerCase()) +
      's only — never across positions. ' + esc(thin) + '. This board is ' +
      esc(SUPLAB[r.sup] || 'partly supported') + ' by what a box score can ' +
      'see.</div>' +
    '</div>';
}

function showPlayer(p) {
  const face = p.photo
    ? '<img class="phero" src="' + p.photo + '" alt="" ' +
      'onerror="this.replaceWith(document.createRange()' +
      '.createContextualFragment(this.dataset.fb))" data-fb=\'' +
      avatar(p.pos, p.team, 72) + '\'>'
    : avatar(p.pos, p.team, 72);
  /* ⚠ THE TEAM IS A LINK, NOT A LABEL. A player belongs to a team and the
     crest is the obvious way back to it -- the page used to print the team as
     dead text and leave the top nav as the only escape.
     Subtitle order is team, official class, position, number: the class year
     comes from the school's own roster, so it is stated before anything the
     box-score feed supplied. A field we do not have is omitted, never zeroed. */
  const teamHref = routeFor('teams', slug(p.team));
  const sub = [
    '<a class="parentlink" href="' + teamHref + '">' + esc(p.team) + '</a>',
    p['class'] ? esc(p['class']) : null,
    p.pos ? esc(p.pos) : null,
    p.num ? '#' + esc(String(p.num)) : null
  ].filter(Boolean).join(' · ');

  /* ⚠ WHERE SHE PLAYED BEFORE, WHEN SHE PLAYED SOMEWHERE BEFORE. A card that
     shows a senior's class and her rate and says nothing about the fact she
     spent three years at another school is hiding the most useful thing about
     her. Anchored on (from_team_id, name) upstream, never a bare-name match.
     Her prior line is labelled with the school it was earned at, because a
     rate carries the place it came from or it is misattributed. */
  const xf = p.xf && p.xf.from_team
    ? '<div class="pxfer"><span class="pxlab">Transfer</span>' +
        '<a class="parentlink" href="' + routeFor('teams', slug(p.xf.from_team)) +
        '">' + esc(p.xf.from_team) + '</a>' +
        (p.xf.prior_pts && p.xf.prior_sets
          ? '<span class="pxstat">' +
            (p.xf.prior_pts / p.xf.prior_sets).toFixed(2) +
            ' pts/set there over ' + p.xf.prior_sets + ' sets</span>'
          : '<span class="pxstat munk">no prior D-I line on record</span>') +
      '</div>'
    : '';

  /* ⚠ THIS IS A SEARCH, AND IT SAYS SO. There is no approved highlight source
     for college volleyball, so the honest affordance is a link that runs a
     search on her name and school -- not a "highlights" button implying a
     verified reel that may not exist or may be a different person with the
     same name. The wording is deliberate: "Search video for", never
     "Highlights". */
  const q = encodeURIComponent(p.name + ' ' + p.team + ' volleyball highlights');
  const vid = '<div class="pvid"><span class="pxlab">Video</span>' +
    '<a href="https://www.youtube.com/results?search_query=' + q + '" ' +
    'target="_blank" rel="noopener noreferrer">Search YouTube</a>' +
    '<a href="https://www.google.com/search?tbm=vid&q=' + q + '" ' +
    'target="_blank" rel="noopener noreferrer">Search video</a>' +
    '<span class="munk">a search, not a verified reel</span></div>';
  document.getElementById('playercard').innerHTML =
    ratingHTML(p) +
    '<div class="thead phead">' + face + '<div><h2>' +
      '<a class="parentlink" href="' + teamHref + '" aria-label="Back to ' +
      esc(p.team) + '">' + logo(p.team, 'lg') + '</a>' + esc(p.name) + '</h2>' +
    '<div class="sub">' + sub + '</div>' +
    '<div class="chips">' +
      '<span class="chip ours">Pts/set <b>' + p.pps.toFixed(2) + '</b></span>' +
      '<span class="chip">Kills/set <b>' + p.kps.toFixed(2) + '</b></span>' +
      '<span class="chip">Hit% <b>' + pct(p.hit) + '</b></span>' +
      '<span class="chip">Digs/set <b>' + p.dps.toFixed(2) + '</b></span>' +
      '<span class="chip">Sets <b>' + p.sets + '</b></span>' +
    '</div>' + xf + vid + '</div></div>' +
    /* ⚠ TOTALS AND THE MATCH LOG ARE DIFFERENT THINGS AND NOW SAY SO. The
       card ran season rates straight into a per-match table with no heading
       between them, so a reader could take either row for the other. */
    '<div class="tsec"><h3>2026 season</h3><div class="body">' +
      '<div class="statline">' + statLine(p) + '</div>' +
      '<div class="tnote">Totals across ' + p.games.length +
      (p.games.length === 1 ? ' match' : ' matches') + ' this season.</div>' +
    '</div></div>' +
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
    p.games.map(g => '<div class="gline"><span class="dt">' + dayLabel(g.d || '') + '</span>' +
      '<span class="op">' + esc(g.opp || '') +
      /* the caveat sits on the row, beside the number it qualifies */
      (g.nondi ? '<b class="nondi" title="Not a Division-I opponent. This ' +
        'site does not filter these matches out -- filtering would change ' +
        'what every rate means without saying so -- so it is marked ' +
        'instead.">non-D-I</b>' : '') + '</span>' +
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
    /* ⚠ SAID ONLY WHEN IT IS TRUE, and it says how much of the season it is.
       "one of her two matches" and "her only match" are different facts and
       the reader needs the second one loudly. */
    ((p.games || []).some(g => g.nondi)
      ? '<div class="tnote"><b class="dicaveat">' +
        nonDiPhrase(p.games.filter(g => g.nondi).length, p.games.length,
                    'on file') +
        '</b>, so the rates above are not measured against Division-I ' +
        'competition. ' + NONDI_WHY + '</div>'
      : '') +
    '</div></div>';
}
document.getElementById('pbody').addEventListener('click', e => {
  const tr = e.target.closest('.prow'); if (!tr || !tr.dataset.k) return;
  const parts = tr.dataset.k.split('|');
  /* routed, so Back returns to the directory and a refresh keeps the player */
  openPlayer(parts[1], parts[0], 'players');
});
/* ⚠ DEBOUNCED. The directory now spans all of Division I, so a keystroke
   rebuilds a 2,800-row search and two tables. Firing that per character is what
   froze the tab -- and typing a full name is the normal case, not an edge one. */
/* ⚠ A BOARD ROW OPENS HER CARD, AND THE ROUTE HAS TO CHANGE FIRST. Painting
   the card while the reader is still on the ratings view puts it somewhere
   they cannot see; the players view has to be the destination, and only then
   does the card get painted. A player with a 2026 line gets her full page; one
   without gets the last-season card, which is the same split the directory
   already makes. */
function openFromBoard(team, name) {
  const live = (typeof PLAYERS !== 'undefined')
    ? PLAYERS.find(p => p.team === team && p.name === name) : null;
  if (live) { go(routeFor('players', slug(team) + '/' + slug(name))); return; }
  const hit = (typeof ROSTER !== 'undefined')
    ? ROSTER.find(r => r.t === team && r.n === name) : null;
  if (!hit) return;
  /* ⚠ PAINT AFTER THE ROUTER, NOT BEFORE IT. The players route CLEARS
     #playercard on entry, so calling go() and then painting put the card up
     and had it wiped a moment later -- the route changed, the card was blank,
     and nothing errored. This is the same ordering the routed-player fix
     already had to learn: the destination settles first, then the thing the
     reader asked for is painted on top. */
  go(routeFor('players'));
  setTimeout(() => {
    const box = document.getElementById('pq');
    if (box) { box.value = name; renderPlayers(); }
    showRated(hit);
  }, 0);
}
document.addEventListener('click', e => {
  const row = e.target.closest && e.target.closest('.prkrow');
  if (!row || (e.target.closest && e.target.closest('a'))) return;
  const k = row.getAttribute('data-pk') || '';
  const i = k.indexOf('|');
  if (i > 0) openFromBoard(k.slice(0, i), k.slice(i + 1));
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const row = e.target.closest && e.target.closest('.prkrow');
  if (!row) return;
  const k = row.getAttribute('data-pk') || '';
  const i = k.indexOf('|');
  if (i > 0) { e.preventDefault(); openFromBoard(k.slice(0, i), k.slice(i + 1)); }
});

/* clicking a not-yet-played row opens her card */
document.addEventListener('click', e => {
  const row = e.target.closest && e.target.closest('.nyrow');
  if (!row) return;
  const k = row.getAttribute('data-nyk') || '';
  const i = k.indexOf('|');
  if (i < 0 || typeof ROSTER === 'undefined') return;
  const t = k.slice(0, i), n = k.slice(i + 1);
  const hit = ROSTER.find(r => r.t === t && r.n === n);
  if (hit) showRated(hit);
});

let PQ_T = null;
document.getElementById('pq').addEventListener('input', () => {
  if (PQ_T) clearTimeout(PQ_T);
  PQ_T = setTimeout(renderPlayers, 140);
});
renderPlayers();


/* ---- standings --------------------------------------------------------- */
const STANDINGS = {{STANDINGS_JSON}};
const RESULTS = {{RESULTS_JSON}};
/* ⚠ THE NON-DIVISION-I OPPONENTS THAT APPEAR IN THESE RESULTS, as an explicit
   list rather than "not in TEAMS". TEAMS is declared near the END of this
   script, so reading it from a const initialiser up here throws
   `Cannot access 'TEAMS' before initialization` -- the temporal dead zone that
   has already broken routing and My Board in this file. An explicit set has no
   ordering hazard and is a handful of names. */
const NONDI_OPP = new Set({{NONDI_JSON}});
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
                                    score: mine + '-' + theirs,
                                    nondi: NONDI_OPP.has(them)});
    });
  });
  return by;
})();
function formPills(team, n) {
  const gs = FORM[team] || [];
  if (!gs.length) return '<span class="noform" title="no results yet">&mdash;</span>';
  return gs.slice(-(n || 5)).map(g =>
    /* ⚠ A "W" THE RECORD DOES NOT COUNT MUST SAY SO ON THE FACE OF THE PILL.
       A hover title is not a label: it does not exist on a phone, it is not
       read out, and it cannot be seen while scanning a column. The marker is
       therefore TEXT in the pill -- "W nD1" -- and the pill is outlined
       rather than filled so the eye separates it from a counted result even
       before reading it. The title stays as the long form. */
    '<span class="' + (g.won ? 'fw' : 'fl') + (g.nondi ? ' fnd' : '') +
    '" title="' +
    (g.won ? 'beat ' : 'lost to ') + g.opp + ' ' + g.score +
    /* ⚠ ONE UNBROKEN STRING. Split as '...it is not ' + 'counted in the...'
       the sentence never appears contiguously in the built page, so a guard
       searching for the phrase cannot find it -- which is exactly what
       happened. Keep a user-visible sentence in one literal. */
    (g.nondi
      ? ' \u2014 a non-Division-I opponent. It happened, and it is not counted in the Division-I record.'
      : '') + '">' +
    (g.won ? 'W' : 'L') +
    (g.nondi ? '<i class="fndt">nD1</i>' : '') + '</span>').join('');
}

/* The TV table opens on what is still to come; earlier listings are present
   and one click away, never removed. */
document.addEventListener('click', function (e) {
  const b = e.target.closest && e.target.closest('#tvpastbtn');
  if (!b) return;
  const rows = document.querySelectorAll('tr.tvpast');
  const showing = b.getAttribute('data-on') === '1';
  rows.forEach(r => { r.hidden = showing; });
  b.setAttribute('data-on', showing ? '0' : '1');
  b.textContent = showing
    ? 'Show ' + rows.length + ' earlier listing' + (rows.length === 1 ? '' : 's')
    : 'Hide earlier listings';
});

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
        '<table><thead><tr><th class="l">Team</th><th>Conf</th>' +
        '<th title="Division-I opponents only, the NCAA\u2019s own convention ' +
        '\u2014 the official RPI table excludes non-Division-I results from a ' +
        'record and breaks them out separately. A team with such a result ' +
        'shows it beside this column.">Overall</th>' +
        '<th class="l" title="last five, oldest first">Form</th>' +
        '<th title="Points scored minus points allowed, per set, against ' +
        'DIVISION-I OPPONENTS ONLY \u2014 the same matches the record beside ' +
        'it counts. A team with no Division-I match yet shows a dash.">' +
        '+/-<span class="thb">D-I</span></th>' +
        '<th>Rk</th></tr></thead><tbody>' +
        rows.map(r => {
          const diff = r.diff === undefined ? null : r.diff;
          return '<tr><td class="tm">' + logo(r.team) + r.team + '</td>' +
          '<td class="n">' + r.cw + '-' + r.cl + '</td>' +
          /* ⚠ THE D-I RECORD, PLUS ANY NON-D-I RESULT BESIDE IT. Dropping
             those matches from the record is right and is what the NCAA does;
             dropping them SILENTLY is what produced "Overall 0-0" on a row
             whose own Form column said "W". */
          '<td class="n">' + r.w + '-' + r.l +
          ((r.nw || r.nl)
            ? '<i class="nvd" title="' + r.nw + '-' + r.nl + ' against ' +
              'non-Division-I opponents. Not counted in the record above, ' +
              'which follows the NCAA convention of Division-I results only.">' +
              '+' + r.nw + '-' + r.nl + ' nD1</i>'
            : '') + '</td>' +
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
    /* ⚠ THE LEGEND WAS 32 ROWS BELOW THE NUMBERS IT EXPLAINS. There is a
       footer reading "median rank · teams", but the reader meets the columns
       at row 1 -- Big 12 showing a bare `44  15` -- and the legend is off the
       bottom of the screen. The hover title says it too, and a phone has no
       hover. Same labels, repeated at the head of the chart where the first
       number is. */
    /* ⚠ ONE LABEL ACROSS BOTH COLUMNS. "MEDIAN" is ~42px at 9px condensed
       with .1em tracking and the column is 34px, so two separate headings
       rendered as "MEDIANTEAMS". Widening the columns would move the chart;
       one right-aligned label spanning them says the same thing in the space
       that exists, and uses the footer's exact wording. */
    '<div class="chead"><span></span><span></span>' +
      '<span class="chlab">median &middot; teams</span></div>' +
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

/* BALLOT-WORKSHOP-BEGIN */
/* ══ BALLOT WORKSHOP ══════════════════════════════════════════════════════
   Cody's own weekly VolleyTalk Top 25. His ranking is the object; POWER is a
   starting point he can overrule; his reasons are recorded as words.

   ⚠ NOTHING HERE FEEDS A MODEL. Move reasons are stored text. The rating
   engine was measured on exactly the ideas people put in these boxes --
   composure, five-set nerve, clutch -- and every one made it predict WORSE
   (docs/rating_factors_2025.md). That is precisely why they belong to a human
   with a name on the ballot rather than to a coefficient.

   ⚠ AND IT PUBLISHES NOTHING. One button puts text on the clipboard. */
const BW_KEY = 'wvb_ballot_' + SEASON_YEAR;
const DIGBY_CLIP = `{{DIGBY_CLIP}}`;
const BW_MOVE_REASONS = ['tournament projection', 'matchup concern',
  'returning experience', 'injury / availability', 'late-set composure',
  'schedule context', 'head-to-head', 'other'];
/* how far off POWER a slot has to be before the workshop asks why. Not a
   scoring threshold -- it decides when a QUESTION is shown, nothing else. */
const BW_ASK_AT = 4;
/* and how far a team must move against YOUR OWN previous ballot before the
   workshop says a reason is missing. Three slots, as specified -- it gates a
   QUESTION, never a score, and entering or dropping always counts. */
const BW_MOVE_AT = 3;

let BW = { teams: [], summary: '' };
let BW_HIST = [];
let BW_DURABLE = null;          // null = unknown, true = server, false = browser

function bwPower() {
  /* Digby's POWER order, top 25 first. The seed, never the answer. */
  return Object.keys(TEAMS)
    .filter(t => TEAMS[t] && TEAMS[t].rank)
    .sort((a, b) => TEAMS[a].rank - TEAMS[b].rank);
}
function bwSeed() {
  const keep = {};
  (BW.teams || []).forEach(t => { keep[t.team] = t; });
  const order = bwPower().slice(0, 25);
  BW.teams = order.map((t, i) => Object.assign({}, keep[t] || {},
    { team: t, rank: i + 1 }));
  /* anyone previously on the ballot who is no longer in the POWER 25 keeps a
     place in "also considered" rather than vanishing */
  Object.keys(keep).forEach(t => {
    if (order.indexOf(t) < 0) BW.teams.push(Object.assign({}, keep[t], { team: t, rank: null }));
  });
}
function bwRanked() {
  return BW.teams.filter(t => t.rank).sort((a, b) => a.rank - b.rank);
}
function bwPool() { return BW.teams.filter(t => !t.rank); }
function bwEntry(name) {
  for (let i = 0; i < BW.teams.length; i++) {
    if (BW.teams[i].team === name) return BW.teams[i];
  }
  return null;
}
function bwSlot(name) { const e = bwEntry(name); return e ? e.rank : null; }
function bwRenumber() {
  bwRanked().forEach((t, i) => { t.rank = i + 1; });
}
function bwSig(b) {
  return (b.teams || []).filter(t => t.rank).sort((a, c) => a.rank - c.rank)
    .map(t => t.rank + ':' + t.team).join('|');
}
/* WHAT THE ARROWS COMPARE AGAINST.
   Normally the latest saved ballot. But the instant you save, the draft IS the
   latest save -- so every arrow would collapse to "–" and the panel would read
   "identical to your last saved ballot", which is true and useless. When the
   draft matches the latest save, step back one: the useful question then is
   what changed between your last two ballots. */
function bwPrev() {
  if (!BW_HIST.length) return null;
  const latest = BW_HIST[BW_HIST.length - 1];
  if (BW_HIST.length > 1 && bwSig(latest) === bwSig(BW)) return BW_HIST[BW_HIST.length - 2];
  return latest;
}
function bwPrevRank(team) {
  const p = bwPrev();
  if (!p) return null;
  const hit = (p.teams || []).find(x => x.team === team && x.rank);
  return hit ? hit.rank : null;
}

/* ---- one row of evidence, deliberately secondary to the slot -------------
   ⚠ EVERY VALUE HERE IS READ FROM THE PAGE'S OWN DATA. A team with no result
   shows "no result yet", never a zero; RÉSUMÉ says it is not active
   rather than printing a rank it does not have. */
/* ---- the case row: ONLY facts already on this page --------------------
   Nothing here is scouting, importance, momentum or consensus. Every value is
   copied from a field that exists elsewhere in the build, and each says which
   ruler it belongs to. A team we have nothing for shows nothing, not a zero. */
function bwNextFixture(name) {
  const t = TEAMS[name] || {};
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  const up = (t.fixtures || []).filter(f => f.d >= today)
    .sort((a, b) => (a.d < b.d ? -1 : 1));
  return up.length ? up[0] : null;
}

function bwCase(name, driver) {
  const t = TEAMS[name] || {};
  const slot = bwSlot(name);
  const prev = bwPrevRank(name);
  const base = bwPrev();
  const bits = [];
  bits.push('<span class="bwcn">' + logo(name) + esc(name) + '</span>');
  if (driver) bits.push('<span class="bwcd">' + driver + '</span>');
  bits.push(slot ? '<em>my ballot</em> #' + slot
                 : '<em>my ballot</em> not slotted');
  if (base) {
    bits.push(prev == null ? '<em>vs last save</em> new'
      : (prev === slot ? '<em>vs last save</em> –'
        : '<em>vs last save</em> ' + (prev > slot ? '▲' : '▼') +
          Math.abs(prev - (slot || prev))));
  }
  if (t.rank) bits.push('<em>POWER</em> #' + t.rank);
  bits.push('<em>AVCA</em> ' + (t.avca ? '#' + t.avca : 'NR'));
  if (t.record26) bits.push('<em>record</em> ' + esc(t.record26));
  const played = (t.played || []).slice().sort((a, b) => (a.d < b.d ? 1 : -1));
  if (played.length) {
    const L = played[0];
    bits.push('<em>last</em> ' + (L.mine > L.theirs ? 'beat ' : 'lost to ') +
      esc(L.opp) + ' ' + L.mine + '–' + L.theirs);
  }
  const nx = bwNextFixture(name);
  if (nx) {
    bits.push('<em>next</em> ' + (nx.home ? 'v ' : 'at ') + esc(nx.opp) +
      ' ' + esc(dayLabel(nx.d)));
  }
  /* ⚠ MARKED UNEXPLAINED, NEVER FILLED IN. The workshop says a big move has no
     reason yet; it does not write one, and it does not stop the save. */
  const ent = bwEntry(name) || {};
  const un = bwUnexplained(name, slot);
  if (un) {
    bits.push('<span class="bwwhy">no reason written yet' +
      (un.personal && un.power ? ' (moved, and far from POWER)'
        : (un.personal ? ' (you moved them)' : ' (far from POWER)')) +
      '</span>');
  }
  bits.push('<button type="button" class="bwpin' + (ent.pinned ? ' on' : '') +
    '" data-pin="' + esc(name) + '">' + (ent.pinned ? 'pinned' : 'pin') +
    '</button>');
  return '<div class="bwcase">' + bits.join('') + '</div>';
}

/* ── THE WEEKLY BRIEFING ──────────────────────────────────────────────────
   ⚠ EVERY COMPARISON HERE IS AGAINST CODY'S OWN LAST SAVED BALLOT, never
   against POWER. "What changed" means what HE changed his mind about; the
   model's opinion is a separate column and is labelled as one. */
function bwLastSaved() {
  if (!BW_HIST || !BW_HIST.length) return null;
  return BW_HIST[BW_HIST.length - 1];
}
function bwIsoWeek(d) {
  const t = new Date(d.getTime());
  t.setUTCHours(0, 0, 0, 0);
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return t.getUTCFullYear() + '-W' +
    String(Math.ceil((((t - y0) / 86400000) + 1) / 7)).padStart(2, '0');
}

/* results finished SINCE the last save -- only when a date proves it */
function bwResultsSince(iso) {
  if (!iso) return [];
  const day = iso.slice(0, 10);
  const out = [];
  Object.keys(TEAMS).forEach(n => {
    (TEAMS[n].played || []).forEach(g => {
      if (g.d && g.d >= day) {
        const key = [n, g.opp].sort().join('|') + g.d;
        out.push({ key: key, team: n, g: g });
      }
    });
  });
  const seen = {};
  return out.filter(r => (seen[r.key] ? false : (seen[r.key] = true)));
}

/* Opening an archived ballot. It renders into its OWN container, carries no
   input, and offers only a close button -- there is no path from here back
   into the working ballot, which is what makes overwriting impossible. */
function bwOpenArchived(i) {
  const b = BW_HIST[i];
  const host = document.getElementById('bwro');
  if (!b || !host) return;
  const r = (b.teams || []).filter(x => x.rank).sort((a, c) => a.rank - c.rank);
  const notes = (b.summary || '').trim();
  host.hidden = false;
  host.innerHTML = '<div class="rohd">Saved ballot &mdash; ' +
      esc((b.saved_utc || '').slice(0, 10)) +
      '<span style="color:var(--slate)">read-only</span>' +
      '<button type="button" class="linkbtn" id="bwroclose">Close</button></div>' +
    '<ol>' + r.map(t => '<li>' + esc(t.team) + '</li>').join('') + '</ol>' +
    (notes ? '<p class="ronote"><b>Your notes:</b> ' + esc(notes) + '</p>' : '') +
    '<p class="ronote">This is the archive. Nothing here can be edited and ' +
    'nothing here writes back &mdash; your working ballot below is untouched.</p>';
  host.scrollIntoView({ block: 'nearest' });
  const c = document.getElementById('bwroclose');
  if (c) c.addEventListener('click', () => { host.hidden = true; host.innerHTML = ''; });
}

function renderBriefing() {
  const host = document.getElementById('bwbrief');
  if (!host) return;
  const prev = bwLastSaved();
  const ranked = bwRanked();
  const f = [];

  if (!prev) {
    f.push('<div class="bwbf"><em>Last saved ballot</em>' +
      '<b class="none">None yet</b><span>This will be your first. Once saved it ' +
      'becomes the baseline every later week is measured against.</span></div>');
  } else {
    const when = (prev.saved_utc || '').slice(0, 10);
    f.push('<div class="bwbf"><em>Last saved ballot</em><b>' + esc(when) +
      '</b><span>' + esc(bwIsoWeek(new Date(prev.saved_utc))) + ' &middot; ' +
      (prev.teams || []).filter(t => t.rank).length + ' ranked</span></div>');

    const pr = {};
    (prev.teams || []).forEach(t => { if (t.rank) pr[t.team] = t.rank; });
    const now = {};
    ranked.forEach(t => { now[t.team] = t.rank; });
    let moved = 0;
    ranked.forEach(t => {
      if (pr[t.team] != null && pr[t.team] !== t.rank) moved++;
    });
    const entered = ranked.filter(t => pr[t.team] == null).map(t => t.team);
    const dropped = Object.keys(pr).filter(n => now[n] == null);
    f.push('<div class="bwbf"><em>Moved in your ballot</em><b>' + moved +
      '</b><span>' + (moved
        ? 'teams sit at a different slot than you saved them at'
        : 'nothing has moved since you saved') + '</span></div>');
    f.push('<div class="bwbf"><em>Entered your ballot</em><b>' + entered.length +
      '</b><span>' + (entered.length
        ? esc(entered.slice(0, 4).join(', ')) + (entered.length > 4 ? '…' : '')
        : '<span class="none">none</span>') + '</span></div>');
    f.push('<div class="bwbf"><em>Left your ballot</em><b>' + dropped.length +
      '</b><span>' + (dropped.length
        ? esc(dropped.slice(0, 4).join(', ')) + (dropped.length > 4 ? '…' : '')
        : '<span class="none">none</span>') + '</span></div>');

    /* ⚠ ONLY WHEN A DATE PROVES IT. A result counts as "since your last
       ballot" only if its own date is on or after the save; if we cannot date
       it, it is not claimed. */
    const res = bwResultsSince(prev.saved_utc);
    f.push('<div class="bwbf"><em>Results since then</em><b>' + res.length +
      '</b><span>' + (res.length
        ? 'completed matches dated on or after your save'
        : 'no completed match is dated after your save') + '</span></div>');
  }

  /* the two external rulers, stated as positions and named */
  const top = ranked.length ? ranked[0].team : null;
  if (top) {
    const t = TEAMS[top] || {};
    const rulers = [
      '<span class="bwv pw">POWER ' + (t.rank ? '#' + t.rank : '\u2014') + '</span>',
      '<span class="bwv av">AVCA ' + (t.avca ? '#' + t.avca : 'NR') + '</span>',
      (RESUME_ACTIVE && t.resume_rank
        ? '<span class="bwv">R\u00c9SUM\u00c9 #' + t.resume_rank + '</span>'
        : '<span class="bwv off">R\u00c9SUM\u00c9 not active yet</span>')
    ];
    f.push('<div class="bwbf"><em>Your #1</em><b>' + esc(top) + '</b>' +
      '<span class="bwrulerline">' + rulers.join('<i> &middot; </i>') +
      '</span></div>');
  }

  host.innerHTML = '<h3>This week</h3>' +
    '<p class="bwbsub">Facts about <b>your</b> ballot and what has happened ' +
    'since you saved it. Nothing here is a recommended Top 25, and nothing ' +
    'here tells you to move a team.</p>' +
    '<div class="bwbfacts">' + f.join('') + '</div>';
}

/* ── THE COMPARISON WORKSPACE ─────────────────────────────────────────────
   Both teams are chosen by Cody. Only fields that already exist, each labelled
   with the ruler it belongs to. */
function bwCmpRow(label, a, b, cls) {
  const v = x => (x === null || x === undefined || x === '')
    ? '<span class="un">not available</span>' : x;
  return '<tr><td class="lab">' + label + '</td><td>' + v(a) + '</td><td>' +
    v(b) + '</td></tr>';
}
function renderCompare() {
  const host = document.getElementById('bwteamcmp');
  if (!host) return;
  const A = (document.getElementById('bwcA') || {}).value || '';
  const B = (document.getElementById('bwcB') || {}).value || '';
  const ta = TEAMS[A], tb = TEAMS[B];
  if (!ta || !tb) {
    host.innerHTML = '<p class="bwsub">Choose two teams to compare. Nothing is ' +
      'selected for you.</p>';
    return;
  }
  /* ⚠ THESE THREE READ AS BARE NUMERALS SEPARATED ONLY BY COLOUR. `.bwv.pw`
     and `.bwv.av` set a hue and nothing else, so "my #4  #6  #9" was three
     different rankings distinguished by hue alone -- ambiguous to read and
     invisible to anyone who does not separate those hues. */
  const slot = n => { const e = bwEntry(n);
    return e && e.rank ? rankHTML('ballot', e.rank, true) : null; };
  const prevRank = n => { const r = bwPrevRank(n);
    return r ? rankHTML('ballot', r, true) : null; };
  const mine = n => {
    const v = slot(n);
    return v ? '<span class="bwv mine">' + v + '</span>' : null;
  };
  const pw = n => (TEAMS[n].rank
    ? '<span class="bwv pw">' + rankHTML('power', TEAMS[n].rank, true) +
      '</span>' : null);
  const av = n => (TEAMS[n].avca
    ? '<span class="bwv av">' + rankHTML('avca', TEAMS[n].avca, true) +
      '</span>'
    : '<span class="bwv av">NR</span>');
  const last = n => {
    const p = (TEAMS[n].played || []).slice().sort((x, y) => x.d < y.d ? 1 : -1)[0];
    return p ? (p.mine > p.theirs ? 'beat ' : 'lost to ') + esc(p.opp) + ' ' +
      p.mine + '\u2013' + p.theirs + ' (' + esc(dayLabel(p.d)) + ')' : null;
  };
  const next = n => {
    const today = new Intl.DateTimeFormat('en-CA',
      { timeZone: 'America/Los_Angeles' }).format(new Date());
    const u = (TEAMS[n].fixtures || []).filter(x => x.d >= today)
      .sort((x, y) => x.d < y.d ? -1 : 1)[0];
    return u ? (u.home ? 'v ' : 'at ') + esc(u.opp) + ' ' + esc(dayLabel(u.d)) : null;
  };
  const proj = n => {
    const sm = TEAMS[n].sim;
    return sm && sm.proj_wins_mean != null
      ? sm.proj_wins_mean.toFixed(1) + ' projected wins' : null;
  };
  /* ⚠ HEAD-TO-HEAD IS DATED, AND MOST OF IT IS LAST SEASON. Presenting a 2025
     meeting as evidence about 2026 without saying so would be the single most
     misleading thing this table could do. */
  const h = (TEAMS[A].h2h || {})[B];
  let h2h = null;
  if (h) {
    const yr = (h.d || '').slice(0, 4);
    h2h = esc(A) + ' ' + h.mine + '\u2013' + h.theirs + ' ' + esc(B) +
      ', ' + esc(h.d) + (yr && yr !== String(SEASON_YEAR)
        ? ' <span class="un">(' + yr + ' season, not this one)</span>' : '');
  }

  host.innerHTML =
    '<table class="bwcmptbl"><thead><tr><th></th>' +
      '<th class="tm">' + logo(A) + esc(A) + '</th>' +
      '<th class="tm">' + logo(B) + esc(B) + '</th></tr></thead><tbody>' +
      bwCmpRow('My ballot', mine(A), mine(B)) +
      bwCmpRow('My last saved', prevRank(A), prevRank(B)) +
      bwCmpRow('POWER', pw(A), pw(B)) +
      bwCmpRow('AVCA poll', av(A), av(B)) +
      bwCmpRow('R\u00c9SUM\u00c9',
        RESUME_ACTIVE ? null : '<span class="un">not active yet</span>',
        RESUME_ACTIVE ? null : '<span class="un">not active yet</span>') +
      bwCmpRow('Record 2026', esc(TEAMS[A].record26 || ''), esc(TEAMS[B].record26 || '')) +
      bwCmpRow('Last result', last(A), last(B)) +
      bwCmpRow('Next match', next(A), next(B)) +
      bwCmpRow('Projection', proj(A), proj(B)) +
    '</tbody></table>' +
    '<p class="bwsub" style="margin-top:10px">Head to head: ' +
      (h2h || '<span class="un">these two have not met in the records held here</span>') +
      '</p>' +
    '<p class="bwsub"><a class="parentlink" href="' + routeFor('teams', slug(A)) +
      '">Open ' + esc(A) + '</a> &middot; <a class="parentlink" href="' +
      routeFor('teams', slug(B)) + '">Open ' + esc(B) + '</a></p>';
}

/* Four groups. Each is ONE named difference, sorted by its own size -- no
   blending, so every position in every list can be checked by hand. */
/* ⚠ FIVE TRIGGERS, EACH A STATED FACT. An item is here because something
   OBSERVABLE changed -- never because a score decided it deserves attention.
   Every entry carries the exact trigger and the ranks it came from, and no
   list is ordered by "importance": each is sorted by the size of its own
   named difference, which is a number the reader can check. */
function bwQueue() {
  const prev = bwPrev();
  const prevRank = {};
  if (prev) (prev.teams || []).forEach(t => { if (t.rank) prevRank[t.team] = t.rank; });
  const ranked = bwRanked();
  const nowRank = {};
  ranked.forEach(t => { nowRank[t.team] = t.rank; });
  const out = [];

  /* 1. my PRIOR ballot slot differs from current POWER */
  const vsPower = Object.keys(prevRank).map(n => {
    const p = (TEAMS[n] || {}).rank;
    return p ? { team: n, d: p - prevRank[n], mine: prevRank[n], pw: p } : null;
  }).filter(Boolean).filter(x => Math.abs(x.d) >= 3)
    .sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 10);
  out.push(['Your last ballot differs from POWER',
    'Your saved slot against the current POWER rank. Positive means you had ' +
    'them higher than POWER does.',
    vsPower.map(x => bwCase(x.team,
      '<span class="bwtrig mine">my #' + x.mine + '</span>' +
      '<span class="bwtrig pw">POWER #' + x.pw + '</span>' +
      '<span class="bwtrig">' + (x.d > 0 ? '+' : '') + x.d + '</span>'))]);

  /* 2. AVCA differs from my PRIOR ballot */
  const vsAvca = Object.keys(prevRank).map(n => {
    const a = (TEAMS[n] || {}).avca;
    return a ? { team: n, d: a - prevRank[n], mine: prevRank[n], av: a } : null;
  }).filter(Boolean).filter(x => Math.abs(x.d) >= 3)
    .sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 10);
  out.push(['The AVCA poll differs from your last ballot',
    'The coaches poll against your saved slot. An external opinion, not ours.',
    vsAvca.map(x => bwCase(x.team,
      '<span class="bwtrig mine">my #' + x.mine + '</span>' +
      '<span class="bwtrig av">AVCA #' + x.av + '</span>' +
      '<span class="bwtrig">' + (x.d > 0 ? '+' : '') + x.d + '</span>'))]);

  /* 3. a verified result dated since the prior save */
  let played = [];
  if (prev) {
    const day = (prev.saved_utc || '').slice(0, 10);
    Object.keys(prevRank).concat(Object.keys(nowRank)).forEach(n => {
      if (played.some(x => x.team === n)) return;
      const g = (TEAMS[n] || {}).played || [];
      const since = g.filter(x => x.d && x.d >= day);
      if (since.length) {
        const L = since.sort((a, b) => a.d < b.d ? 1 : -1)[0];
        played.push({ team: n, g: L, n: since.length });
      }
    });
  }
  out.push(['Played since your last ballot',
    prev ? 'A completed match dated on or after the day you saved. Only ' +
           'results the data can date are counted.'
         : 'Nothing saved yet, so there is no date to count results from.',
    played.slice(0, 12).map(x => bwCase(x.team,
      '<span class="bwtrig res">' +
        (x.g.mine > x.g.theirs ? 'beat ' : 'lost to ') + esc(x.g.opp) + ' ' +
        x.g.mine + '\u2013' + x.g.theirs + '</span>' +
      (x.n > 1 ? '<span class="bwtrig">' + x.n + ' since</span>' : '')))]);

  /* 4. entered or dropped my ballot */
  const inout = [];
  ranked.forEach(t => {
    if (prev && prevRank[t.team] == null) {
      inout.push({ team: t.team,
        tag: '<span class="bwtrig mine">entered at #' + t.rank + '</span>' });
    }
  });
  Object.keys(prevRank).forEach(n => {
    if (nowRank[n] == null) {
      inout.push({ team: n,
        tag: '<span class="bwtrig mine">dropped, was #' + prevRank[n] + '</span>' });
    }
  });
  out.push(['Entered or left your ballot',
    'Movement in and out is a different decision from moving a team a few ' +
    'slots, so it is counted separately.',
    inout.map(x => bwCase(x.team, x.tag))]);

  /* 5. in the comparison universe with no personal rank at all */
  const universe = Object.keys(TEAMS).filter(n =>
    (TEAMS[n].rank && TEAMS[n].rank <= 30) || TEAMS[n].avca);
  const unranked = universe.filter(n => prevRank[n] == null && nowRank[n] == null)
    .sort((a, b) => ((TEAMS[a].rank || 99) - (TEAMS[b].rank || 99))).slice(0, 12);
  out.push(['In the picture, but never on your ballot',
    'Teams inside the current comparison universe \u2014 POWER top 30 or ' +
    'AVCA-ranked \u2014 that you have neither saved nor slotted.',
    unranked.map(n => bwCase(n,
      '<span class="bwtrig pw">POWER ' +
        (TEAMS[n].rank ? rankHTML('power', TEAMS[n].rank, true)
                       : '\u2014') + '</span>' +
      '<span class="bwtrig av">AVCA ' +
        (TEAMS[n].avca ? rankHTML('avca', TEAMS[n].avca, true)
                       : 'NR') + '</span>'))]);

  return out;
}

function renderBallotReview() {
  const host = document.getElementById('bwqueue');
  if (!host) return;
  const groups = bwQueue();
  host.innerHTML = groups.map(g =>
    '<div class="bwgrp"><h4>' + g[0] + ' <span class="bwrn">' +
    g[2].length + '</span></h4><p>' + g[1] + '</p>' +
    (g[2].length ? g[2].join('')
                 : '<p class="bwnone">Nothing in this group.</p>') +
    '</div>').join('');
  const n = document.getElementById('bwrevn');
  if (n) n.textContent = groups.reduce((a, g) => a + g[2].length, 0) +
    ' teams across ' + groups.length + ' triggers';
}

/* ---- pre-submit: three DIFFERENCES, named, none of them advice --------- */
function bwPreReview() {
  const base = bwPrev();
  const ranked = bwRanked();
  const cols = [];

  let changed = [];
  if (!base) {
    changed = null;
  } else {
    const pr = {};
    (base.teams || []).forEach(t => { if (t.rank) pr[t.team] = t.rank; });
    const now = {};
    ranked.forEach(t => { now[t.team] = t.rank; });
    /* ⚠ THE FLAG HERE IS ABOUT YOUR OWN MOVEMENT ONLY. Section 2 is the
       separate POWER comparison; a team can appear in one, the other, or
       both, and conflating them would make "unexplained" ambiguous. */
    const flag = n => {
      const e = bwEntry(n) || {};
      return (e.reason || '').trim() ? ''
        : ' <span class="bwwhy">(no reason written)</span>';
    };
    ranked.forEach(t => {
      if (pr[t.team] == null) {
        changed.push(esc(t.team) + ' entered at ' + t.rank + flag(t.team));
      } else if (pr[t.team] !== t.rank) {
        const d = Math.abs(pr[t.team] - t.rank);
        changed.push(esc(t.team) + ' ' + pr[t.team] + '→' + t.rank +
          (d >= BW_MOVE_AT ? flag(t.team) : ''));
      }
    });
    Object.keys(pr).forEach(n => {
      if (now[n] == null) {
        changed.push(esc(n) + ' dropped out (was ' + pr[n] + ')' + flag(n));
      }
    });
  }
  cols.push(['1 · Versus your last saved ballot',
    changed === null
      ? '<p class="none">This is your first saved ballot, so there is nothing to compare it against.</p>'
      : (changed.length ? '<ul><li>' + changed.join('</li><li>') + '</li></ul>'
                        : '<p class="none">Identical to your last save.</p>')]);

  const vp = ranked.map(t => {
    const p = (TEAMS[t.team] || {}).rank;
    return p ? { team: t.team, d: p - t.rank } : null;
  }).filter(Boolean).filter(x => Math.abs(x.d) >= 3)
    .sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 10);
  cols.push(['2 · Where your ballot differs from POWER',
    vp.length ? '<ul><li>' + vp.map(x => esc(x.team) + ' — you #' +
        bwSlot(x.team) + ', POWER #' + (TEAMS[x.team] || {}).rank +
        (bwEntry(x.team) && (bwEntry(x.team).reason || '').trim()
          ? '' : ' <span class="bwwhy">(no reason written)</span>')
      ).join('</li><li>') + '</li></ul>'
      : '<p class="none">Nothing three or more slots away from POWER.</p>']);

  const ap = Object.keys(TEAMS).map(n => {
    const t = TEAMS[n];
    return (t.avca && t.rank) ? { team: n, d: t.avca - t.rank } : null;
  }).filter(Boolean).filter(x => Math.abs(x.d) >= 5)
    .sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 10);
  cols.push(['3 · Where AVCA and POWER differ',
    ap.length ? '<ul><li>' + ap.map(x => esc(x.team) + ' — AVCA #' +
        TEAMS[x.team].avca + ', POWER #' + TEAMS[x.team].rank
      ).join('</li><li>') + '</li></ul>'
      : '<p class="none">No large gaps between the two.</p>']);

  document.getElementById('bwprebody').innerHTML = cols.map(c =>
    '<div><h4>' + c[0] + '</h4>' + c[1] + '</div>').join('');
  document.getElementById('bwpre').hidden = false;
  document.getElementById('bwpre').scrollIntoView({ block: 'start' });
}

/* ---- compare any two SAVED ballots ------------------------------------- */
function bwHistoryOptions() {
  const a = document.getElementById('bwcmpa');
  const b = document.getElementById('bwcmpb');
  if (!a || !b) return;
  const rows = BW_HIST || [];
  const opts = rows.map((r, i) =>
    '<option value="' + i + '">' + esc((r.saved_utc || '').slice(0, 16)
      .replace('T', ' ')) + '</option>').join('');
  const keepA = a.value, keepB = b.value;
  a.innerHTML = opts; b.innerHTML = opts;
  a.value = keepA || (rows.length > 1 ? rows.length - 2 : 0);
  b.value = keepB || (rows.length ? rows.length - 1 : 0);
}

function bwCompareSaved() {
  const out = document.getElementById('bwcmpout');
  if (!out) return;
  const rows = BW_HIST || [];
  const A = rows[+document.getElementById('bwcmpa').value];
  const B = rows[+document.getElementById('bwcmpb').value];
  if (!A || !B) {
    out.innerHTML = '<p class="bwnone">Save two ballots to compare them.</p>';
    return;
  }
  const ra = {}, rb = {};
  (A.teams || []).forEach(t => { if (t.rank) ra[t.team] = t.rank; });
  (B.teams || []).forEach(t => { if (t.rank) rb[t.team] = t.rank; });
  const lines = [];
  Object.keys(rb).forEach(n => {
    if (ra[n] == null) lines.push(esc(n) + ' entered at ' + rb[n]);
    else if (ra[n] !== rb[n]) lines.push(esc(n) + ' ' + ra[n] + '→' + rb[n] +
      ' (' + (ra[n] > rb[n] ? '▲' : '▼') + Math.abs(ra[n] - rb[n]) + ')');
  });
  Object.keys(ra).forEach(n => {
    if (rb[n] == null) lines.push(esc(n) + ' dropped out (was ' + ra[n] + ')');
  });
  out.innerHTML = lines.length
    ? '<ul style="margin:0;padding-left:15px">' +
      lines.map(l => '<li>' + l + '</li>').join('') + '</ul>'
    : '<p class="bwnone">No difference between these two saves.</p>';
}

function bwEvidence(name) {
  const t = TEAMS[name] || {};
  const bits = [];
  if (t.rank) {
    bits.push('<span class="bwe pw"><i>POWER</i> #' + t.rank +
      (t.power != null ? ' · ' + t.power : '') + '</span>');
  }
  bits.push(RESUME_ACTIVE && t.resume_rank
    ? '<span class="bwe rs"><i>RÉSUMÉ</i> #' + t.resume_rank + '</span>'
    : '<span class="bwe rs off" title="A résumé measures what a team has earned against the schedule it has played. Not enough of the season has been played yet."><i>RÉSUMÉ</i> not active yet</span>');
  bits.push('<span class="bwe ref"><i>AVCA</i> ' +
    (t.avca ? '#' + t.avca : 'unranked') + '</span>');
  bits.push('<span class="bwe">' + (t.record26 || 'no result yet') + '</span>');
  const played = (t.played || []).slice().sort((a, b) => (a.d < b.d ? 1 : -1));
  if (played.length) {
    const f = played.slice(0, 5).reverse().map(g =>
      '<i class="' + (g.mine > g.theirs ? 'fw' : 'fl') + '" title="' +
      (g.mine > g.theirs ? 'beat ' : 'lost to ') + esc(g.opp) + ' ' +
      g.mine + '-' + g.theirs + '">' + (g.mine > g.theirs ? 'W' : 'L') + '</i>').join('');
    bits.push('<span class="bwe form">' + f + '</span>');
    const L = played[0];
    bits.push('<span class="bwe last">' + (L.mine > L.theirs ? 'beat' : 'lost to') +
      ' ' + esc(L.opp) + ' ' + L.mine + '–' + L.theirs + '</span>');
  }
  return bits.join('');
}

function bwMoveState(name, slot) {
  const p = (TEAMS[name] || {}).rank;
  if (!p) return null;
  const d = p - slot;                       // positive = you have them HIGHER
  if (Math.abs(d) < BW_ASK_AT) return null;
  return { delta: d, power: p };
}

/* ⚠ A MOVE AGAINST YOUR OWN LAST BALLOT IS A DIFFERENT EVENT FROM A GAP TO
   POWER, and it was invisible. Moving a team from 6 to 20 while POWER also had
   them ~20 changed your mind by fourteen slots and asked nothing, because the
   only test was distance from POWER. These two are independent: either one on
   its own is worth a sentence, and neither implies the other. */
function bwPersonalMove(name, slot) {
  const base = bwPrev();
  if (!base) return null;                   // nothing saved: nothing to move from
  const prev = bwPrevRank(name);
  if (prev == null && slot) return { kind: 'entered', size: null, from: null };
  if (prev != null && !slot) return { kind: 'dropped', size: null, from: prev };
  if (prev == null || !slot) return null;
  const d = prev - slot;                    // positive = you moved them UP
  if (Math.abs(d) < BW_MOVE_AT) return null;
  return { kind: 'moved', size: d, from: prev };
}

/* True when a move deserves a note and none has been written. It NEVER writes
   one and NEVER blocks the save -- it only decides whether to say so. */
function bwUnexplained(name, slot) {
  const ent = bwEntry(name) || {};
  if ((ent.reason || '').trim()) return null;
  const pm = bwPersonalMove(name, slot);
  const ps = slot ? bwMoveState(name, slot) : null;
  if (!pm && !ps) return null;
  return { personal: pm, power: ps };
}

function renderBallot() {
  const list = document.getElementById('bwlist');
  if (!list) return;
  bwRenumber();
  const rows = bwRanked();
  list.innerHTML = rows.map(t => {
    /* ⚠ BLANK AND "–" MEAN DIFFERENT THINGS, and so does NEW. With no saved
       ballot at all there is nothing to compare against, so every row rendered
       NEW -- twenty-five badges asserting a change that was never measured.
       Blank = no comparison exists. "–" = compared, did not move. NEW = this
       team was genuinely not on your last ballot. Same rule the rankings
       movement column already follows. */
    const prev = bwPrevRank(t.team);
    const base = bwPrev();
    const mv = !base ? ''
      : (prev == null ? '<span class="bwmv new" title="not on your last ballot">NEW</span>'
      : (prev === t.rank ? '<span class="bwmv flat" title="same slot as your last ballot">–</span>'
        : (prev > t.rank
          ? '<span class="bwmv up">▲' + (prev - t.rank) + '</span>'
          : '<span class="bwmv dn">▼' + (t.rank - prev) + '</span>')));
    const ms = bwMoveState(t.team, t.rank);
    const pm = bwPersonalMove(t.team, t.rank);
    /* Two independent prompts, one input. The wording says WHICH move is being
       asked about, because "why?" against POWER and "why?" against your own
       last ballot are different questions with different answers. */
    let asklbl = '';
    if (ms && pm && pm.kind === 'moved') {
      asklbl = 'You moved ' + esc(t.team) + ' <b>' + Math.abs(pm.size) +
        ' slot' + (Math.abs(pm.size) === 1 ? '' : 's') + ' ' +
        (pm.size > 0 ? 'up' : 'down') + '</b> from your last ballot (#' +
        pm.from + '), and have them <b>' + Math.abs(ms.delta) + ' ' +
        (ms.delta > 0 ? 'higher' : 'lower') + '</b> than POWER (#' +
        ms.power + '). Why?';
    } else if (pm && pm.kind === 'moved') {
      asklbl = 'You moved ' + esc(t.team) + ' <b>' + Math.abs(pm.size) +
        ' slot' + (Math.abs(pm.size) === 1 ? '' : 's') + ' ' +
        (pm.size > 0 ? 'up' : 'down') + '</b> from your last ballot (#' +
        pm.from + '). Why?';
    } else if (pm && pm.kind === 'entered') {
      asklbl = 'You added ' + esc(t.team) + ', who was <b>not on your last ' +
        'ballot</b>. Why?';
    } else if (ms) {
      asklbl = 'You have ' + esc(t.team) + ' <b>' + Math.abs(ms.delta) + ' ' +
        (ms.delta > 0 ? 'higher' : 'lower') + '</b> than POWER (#' + ms.power +
        '). Why?';
    }
    const ask = asklbl ? '<div class="bwask' + (t.reason ? ' done' : '') + '">' +
        '<label>' + asklbl + '</label>' +
        '<div class="bwaskrow">' +
        '<select data-reasonkind="' + esc(t.team) + '">' +
          '<option value="">choose…</option>' +
          BW_MOVE_REASONS.map(r => '<option' +
            (t.reason_kind === r ? ' selected' : '') + '>' + r + '</option>').join('') +
        '</select>' +
        '<input type="text" data-reason="' + esc(t.team) + '" value="' +
          esc(t.reason || '') + '" placeholder="in your words — stored, never scored">' +
        '</div></div>' : '';
    return '<li class="bwrow" data-team="' + esc(t.team) + '">' +
      '<div class="bwtop">' +
        '<span class="bwslot">' + t.rank + '</span>' + mv +
        '<span class="bwteam">' + logo(t.team) + esc(t.team) + '</span>' +
        '<span class="bwctl">' +
          '<button type="button" data-up="' + esc(t.team) + '" title="up one slot" aria-label="Move ' + esc(t.team) + ' up">▲</button>' +
          '<button type="button" data-dn="' + esc(t.team) + '" title="down one slot" aria-label="Move ' + esc(t.team) + ' down">▼</button>' +
          '<input class="bwjump" type="number" min="1" max="25" value="' + t.rank +
            '" data-jump="' + esc(t.team) + '" title="type a slot" aria-label="Slot for ' + esc(t.team) + '">' +
          '<button type="button" class="bwx" data-drop="' + esc(t.team) + '" title="move to also considered" aria-label="Remove ' + esc(t.team) + ' from the ballot">✕</button>' +
        '</span>' +
      '</div>' +
      '<div class="bwev">' + bwEvidence(t.team) + '</div>' +
      ask +
      '<input class="bwnote" type="text" data-note="' + esc(t.team) + '" value="' +
        esc(t.note || '') + '" placeholder="private note on ' + esc(t.team) + '…">' +
      '</li>';
  }).join('') || '<li class="bwempty">No teams on the ballot yet. ' +
      '<button type="button" class="bwlink" id="bwseed2">Start from the POWER order</button>.</li>';

  const pool = document.getElementById('bwpool');
  pool.innerHTML = bwPool().map(t =>
    '<span class="bwchip">' + logo(t.team) + esc(t.team) +
    '<button type="button" data-promote="' + esc(t.team) + '" title="add to the ballot at 25">add</button>' +
    '<button type="button" data-forget="' + esc(t.team) + '" title="stop considering">✕</button>' +
    '</span>').join('') || '<span class="bwnone">Nothing set aside.</span>';

  renderBallotDiff();
  renderBallotHistory();
  renderBallotReview();
  renderBriefing();
  renderCompare();
  if (typeof mbRenderAll === 'function') mbRenderAll();
  const lead = document.getElementById('ballotlead');
  if (lead) {
    lead.innerHTML = '<b>Your ' + SEASON_YEAR + ' VolleyTalk ballot.</b> ' +
      'It starts from Digby’s POWER order and is yours to change. ' +
      'The arrow beside a team is movement against <b>your last saved ballot</b>, ' +
      'not against POWER. Nothing here is published or fed into any rating.';
  }
}


/* ---- comparison against the PREVIOUS SAVED BALLOT ---------------------- */
function renderBallotDiff() {
  const box = document.getElementById('bwdiff');
  if (!box) return;
  const prev = bwPrev();
  if (!prev) {
    box.innerHTML = '<p class="bwsub">No saved ballot yet. Save one and this ' +
      'fills with what you changed — additions, drops, the biggest moves, and ' +
      'what you left alone.</p>';
    return;
  }
  const cur = {}; bwRanked().forEach(t => { cur[t.team] = t.rank; });
  const old = {}; (prev.teams || []).filter(t => t.rank).forEach(t => { old[t.team] = t.rank; });
  const entered = Object.keys(cur).filter(t => !(t in old)).sort((a,b)=>cur[a]-cur[b]);
  const dropped = Object.keys(old).filter(t => !(t in cur)).sort((a,b)=>old[a]-old[b]);
  const moved = Object.keys(cur).filter(t => t in old && old[t] !== cur[t])
    .map(t => ({ t, from: old[t], to: cur[t], d: old[t] - cur[t] }))
    .sort((a, b) => Math.abs(b.d) - Math.abs(a.d));
  const same = Object.keys(cur).filter(t => t in old && old[t] === cur[t]).length;
  const when = (prev.saved_utc || '').replace('T', ' ').replace('Z', ' UTC');
  const justSaved = BW_HIST.length > 1 &&
    bwSig(BW_HIST[BW_HIST.length - 1]) === bwSig(BW);
  let h = '<p class="bwsub">' + (justSaved
    ? 'your last two saved ballots' : 'vs your ballot saved ' + esc(when)) + '</p>';
  if (moved.length) {
    h += '<div class="bwdl">' + moved.slice(0, 6).map(m =>
      '<span class="bwdrow"><b>' + esc(m.t) + '</b> ' +
      (m.d > 0 ? '<i class="up">▲' + m.d + '</i>' : '<i class="dn">▼' + (-m.d) + '</i>') +
      ' <span class="bwsub">' + m.from + '→' + m.to + '</span></span>').join('') + '</div>';
  }
  if (entered.length) h += '<p class="bwsub"><b>In:</b> ' + entered.map(esc).join(', ') + '</p>';
  if (dropped.length) h += '<p class="bwsub"><b>Out:</b> ' + dropped.map(esc).join(', ') + '</p>';
  if (!moved.length && !entered.length && !dropped.length) {
    h += '<p class="bwsub">Identical to your last saved ballot.</p>';
  } else {
    h += '<p class="bwsub">' + same + ' unchanged.</p>';
  }
  box.innerHTML = h;
}

function renderBallotHistory() {
  const box = document.getElementById('bwhistory');
  if (!box) return;
  bwHistoryOptions();
  bwCompareSaved();
  if (!BW_HIST.length) {
    /* first ballot of the season: an empty list is a moment, not a gap */
    box.innerHTML = '<div class="digbox">' + DIGBY_CLIP +
      '<div><div class="dwho">Digby</div><div class="dsay">' +
      '<b>Nothing saved yet.</b> Your first save becomes the baseline every ' +
      'later week is measured against &mdash; movement, entries and drops are ' +
      'all counted from it.</div></div></div>';
    bwHistoryOptions();
    return;
  }
  /* ⚠ A WEEK-BY-WEEK RECORD, AND REOPENING ONE IS READ-ONLY. A saved ballot
     is history; opening it must never become a way to overwrite it, so the
     view has no editing controls and no save path at all -- it renders from
     the archived row and nothing writes back. */
  const rows = BW_HIST.slice().reverse();
  box.innerHTML = rows.slice(0, 10).map((b, i) => {
    const r = (b.teams || []).filter(x => x.rank).sort((a, c) => a.rank - c.rank);
    const when = (b.saved_utc || '').slice(0, 10);
    const idx = BW_HIST.length - 1 - i;
    let line = r.length ? '#1 ' + esc(r[0].team) : 'no ranked teams';
    const older = rows[i + 1];
    if (older) {
      const pr = {};
      (older.teams || []).forEach(t => { if (t.rank) pr[t.team] = t.rank; });
      let mv = 0, ent = 0;
      r.forEach(t => {
        if (pr[t.team] == null) ent++;
        else if (pr[t.team] !== t.rank) mv++;
      });
      line += ' &middot; ' + mv + ' moved, ' + ent + ' entered vs the week before';
    } else {
      line += ' &middot; first saved ballot';
    }
    return '<div class="bwweek"><div class="wkhd"><b>' + esc(when) + '</b>' +
      '<span>' + esc(bwIsoWeek(new Date(b.saved_utc))) + ' &middot; ' +
      r.length + ' ranked</span>' +
      (i === 0 ? '<span class="bwlatest">latest</span>' : '') + '</div>' +
      '<div class="wkline">' + line + '</div>' +
      '<button type="button" class="linkbtn" data-openballot="' + idx +
      '">Open read-only</button></div>';
  }).join('');
}

/* ---- the plain text, mirroring scripts/ballot.py:as_text() -------------- */
function bwText() {
  const rows = bwRanked();
  const lines = rows.map(t => t.rank + '. ' + t.team);
  const extra = [];
  const sum = (document.getElementById('bwsummary').value || '').trim();
  if (sum) extra.push(sum);
  const prev = bwPrev();
  if (prev) {
    const cur = {}; rows.forEach(t => { cur[t.team] = t.rank; });
    const old = {}; (prev.teams || []).filter(t => t.rank).forEach(t => { old[t.team] = t.rank; });
    const bits = [];
    Object.keys(cur).filter(t => t in old && Math.abs(old[t] - cur[t]) >= 3)
      .map(t => ({ t, from: old[t], to: cur[t], d: old[t] - cur[t] }))
      .sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 4)
      .forEach(m => bits.push(m.t + ' ' + (m.d > 0 ? 'up ' : 'down ') +
        Math.abs(m.d) + ' (' + m.from + '→' + m.to + ')'));
    const ins = Object.keys(cur).filter(t => !(t in old));
    const outs = Object.keys(old).filter(t => !(t in cur));
    if (ins.length) bits.push('in: ' + ins.slice(0, 4).join(', '));
    if (outs.length) bits.push('out: ' + outs.slice(0, 4).join(', '));
    if (bits.length) extra.push('Biggest moves: ' + bits.join(' | '));
  }
  if (extra.length) { lines.push(''); lines.push('Notes / biggest moves'); extra.forEach(e => lines.push(e)); }
  return lines.join('\n');
}

function bwSay(msg, kind) {
  const el = document.getElementById('bwstate');
  if (!el) return;
  el.textContent = msg;
  el.className = 'bwstate' + (kind ? ' ' + kind : '');
  bwStatusBar();
}

/* ⚠ WHERE AM I, BEFORE WHAT DO I DO. Four facts, from data that already
   exists on this page: which ranking week this is, whether that week's results
   are actually complete (the Digby Weekly cutoff, which the fixture ledger now
   settles), whether there are unsaved edits, and what was last submitted.
   Nothing here recommends anything -- it is a position report. */
function bwStatusBar() {
  const host = document.getElementById('bwstatus');
  if (!host) return;
  const cell = (lab, val, cls) =>
    '<div><i>' + lab + '</i><b' + (cls ? ' class="' + cls + '"' : '') + '>' +
    val + '</b></div>';

  /* the week this ballot is for, and how settled its results are */
  let week = '&mdash;', weekCls = 'dim', settle = 'not known', setCls = 'dim';
  try {
    const w = (typeof CAL !== 'undefined' && CAL) ? CAL.waiting : null;
    if (w) {
      week = esc(String(w.label || '').replace('Digby Weekly \u00b7 ', ''));
      weekCls = '';
      if (w.blocking) {
        settle = w.blocking + ' unresolved';
        setCls = 'warn';
      } else if (w.withdrawn) {
        settle = 'complete \u00b7 ' + w.withdrawn + ' withdrawn';
        setCls = 'ok';
      } else {
        settle = 'complete';
        setCls = 'ok';
      }
    }
  } catch (e) { /* the calendar payload is absent: the cells say so */ }

  /* unsaved edits, from the same signature the save path uses */
  let dirty = 'no changes', dCls = 'dim';
  try {
    const last = bwLastSaved();
    if (!last) { dirty = 'never saved'; dCls = 'warn'; }
    else if (bwSig(BW) !== bwSig(last.ballot || last)) {
      dirty = 'unsaved changes'; dCls = 'warn';
    } else { dirty = 'saved'; dCls = 'ok'; }
  } catch (e) { /* fall through to the default */ }

  /* what was last submitted */
  let lastTxt = 'none yet', lCls = 'dim';
  try {
    const last = bwLastSaved();
    if (last && last.saved) {
      lastTxt = esc(String(last.saved).slice(0, 16).replace('T', ' '));
      lCls = '';
    }
  } catch (e) { /* no history */ }

  host.innerHTML =
    cell('Ranking week', week, weekCls) +
    cell('Results', settle, setCls) +
    cell('This draft', dirty, dCls) +
    cell('Last saved', lastTxt, lCls);
}

/* ---- persistence -------------------------------------------------------
   The server appends to data/ballots_YYYY.jsonl. Without it, the browser is
   the only store -- and the bar SAYS SO, because a save that silently went
   nowhere durable is worse than a refused one. */
function bwLocalSave() {
  try { localStorage.setItem(BW_KEY, JSON.stringify({ draft: BW, hist: BW_HIST })); }
  catch (e) { /* private window / storage off: the page still works, nothing persists */ }
}
function bwLocalLoad() {
  try {
    const raw = localStorage.getItem(BW_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) { return null; }
}

async function bwSave() {
  bwRenumber();
  const payload = { teams: BW.teams, summary: document.getElementById('bwsummary').value || '' };
  if (!bwRanked().length) { bwSay('Nothing to save — the ballot is empty.', 'warn'); return; }
  let ok = false;
  try {
    const r = await fetch('/api/ballot', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const j = await r.json();
    if (j.ok) {
      ok = true; BW_DURABLE = true;
      /* ⚠ TWO SEPARATE FACTS, REPORTED SEPARATELY. The save happened -- that is
         settled the moment the server answers ok. Whether the private backup
         also went through is a different question, and a green tick that
         covers both would be claiming something nobody checked. A pending
         backup is stated, with its reason. */
      const b = j.backup || {};
      if (b.state === 'synced') {
        bwSay('Saved · ' + j.count + ' on file · backed up', 'good');
      } else if (b.state === 'nothing-to-back-up') {
        bwSay('Saved · ' + j.count + ' on file', 'good');
      } else {
        bwSay('Saved · ' + j.count + ' on file · BACKUP PENDING — ' +
              (b.detail || 'not synced'), 'warn');
      }
    }
    else bwSay('Not saved: ' + j.error, 'warn');
  } catch (e) {
    BW_DURABLE = false;
    ok = true;
    bwSay('Saved in this browser only — the local server is not running, so ' +
      'this is not in data/ballots_' + SEASON_YEAR + '.jsonl', 'warn');
  }
  if (ok) {
    const row = Object.assign({}, payload, { saved_utc: new Date().toISOString().replace(/\.\d+Z$/, 'Z') });
    BW_HIST.push(JSON.parse(JSON.stringify(row)));
    bwLocalSave();
    renderBallot();
  }
}

async function bwLoadHistory() {
  const local = bwLocalLoad();
  try {
    const r = await fetch('/api/ballot');
    const j = await r.json();
    if (j.ok) {
      BW_HIST = j.ballots || [];
      BW_DURABLE = true;
      bwSay('Saving to data/ballots_' + SEASON_YEAR + '.jsonl', 'good');
    }
  } catch (e) {
    BW_DURABLE = false;
    BW_HIST = (local && local.hist) || [];
    bwSay('Local server not running — saves stay in this browser only', 'warn');
  }
  /* an unsaved draft outlives a reload; the saved history is the record */
  if (local && local.draft && (local.draft.teams || []).length) BW = local.draft;
  else bwSeed();
  const sum = document.getElementById('bwsummary');
  if (sum) sum.value = BW.summary || '';
  renderBallot();
}

/* ---- wiring ------------------------------------------------------------
   ⚠ NOT SELF-INVOKING, AND THAT IS LOAD-BEARING. This reads TEAMS, which is a
   `const` declared near the END of the page script -- so an IIFE here throws
   "Cannot access 'TEAMS' before initialization" and the whole tab renders
   nothing, silently. A `typeof` guard does not help: a const in the temporal
   dead zone throws for that too. Called after TEAMS instead. Third time this
   project has hit this; the fix is always ordering, never a guard. */
function bwWire() {
  const list = document.getElementById('bwlist');
  if (!list) return;

  function move(team, to) {
    const rows = bwRanked();
    const i = rows.findIndex(t => t.team === team);
    if (i < 0) return;
    const dest = Math.max(0, Math.min(rows.length - 1, to));
    if (dest === i) return;
    rows.splice(dest, 0, rows.splice(i, 1)[0]);
    rows.forEach((t, k) => { t.rank = k + 1; });
    bwLocalSave(); renderBallot();
  }

  document.getElementById('v-ballot').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    const rows = bwRanked();
    const idx = t => rows.findIndex(x => x.team === t);
    if (b.dataset.up) move(b.dataset.up, idx(b.dataset.up) - 1);
    else if (b.dataset.dn) move(b.dataset.dn, idx(b.dataset.dn) + 1);
    else if (b.dataset.drop) {
      const t = BW.teams.find(x => x.team === b.dataset.drop);
      if (t) { t.rank = null; bwRenumber(); bwLocalSave(); renderBallot(); }
    } else if (e.target.dataset && e.target.dataset.pin) {
      /* ⚠ PIN NEVER CHANGES THE BALLOT. It marks a team for another look and
         nothing else -- no slot moves, nothing is dropped, and an unpin does
         not remove the team from the pool either. */
      const ent = bwEntry(e.target.dataset.pin);
      if (ent) { ent.pinned = !ent.pinned; bwLocalSave(); renderBallot(); }
    } else if (b.dataset.promote) {
      const t = BW.teams.find(x => x.team === b.dataset.promote);
      if (t) { t.rank = bwRanked().length + 1; bwRenumber(); bwLocalSave(); renderBallot(); }
    } else if (b.dataset.forget) {
      BW.teams = BW.teams.filter(x => x.team !== b.dataset.forget);
      bwLocalSave(); renderBallot();
    } else if (b.id === 'bwseed' || b.id === 'bwseed2') {
      bwSeed(); bwLocalSave(); renderBallot();
      bwSay('Reset to the POWER order — your notes were kept.', '');
    } else if (b.id === 'bwsave') { bwPreReview(); }
    else if (b.id === 'bwpresave') {
      document.getElementById('bwpre').hidden = true;
      bwSave();
    } else if (b.id === 'bwpreback') {
      document.getElementById('bwpre').hidden = true;
    }
    else if (b.id === 'bwcopy') {
      const txt = bwText();
      const done = () => bwSay('Copied ' + bwRanked().length + ' lines — read it before you post.', 'good');
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(done, () => bwSay('Could not copy.', 'warn'));
      } else {
        const ta = document.createElement('textarea');
        ta.value = txt; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); done(); } catch (err) { bwSay('Could not copy.', 'warn'); }
        ta.remove();
      }
    }
  });

  document.addEventListener('click', e => {
    const o = e.target.closest && e.target.closest('[data-openballot]');
    if (o) bwOpenArchived(+o.dataset.openballot);
  });
  ['bwcA', 'bwcB'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', renderCompare);
  });
  const cclr = document.getElementById('bwcclear');
  if (cclr) cclr.addEventListener('click', () => {
    ['bwcA', 'bwcB'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
    renderCompare();
  });
  ['bwcmpa', 'bwcmpb'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', bwCompareSaved);
  });
  document.getElementById('v-ballot').addEventListener('change', e => {
    const el = e.target;
    const find = n => BW.teams.find(x => x.team === n);
    if (el.dataset.jump) {
      const n = parseInt(el.value, 10);
      if (n >= 1 && n <= 25) move(el.dataset.jump, n - 1); else renderBallot();
    } else if (el.dataset.note) { const t = find(el.dataset.note); if (t) { t.note = el.value; bwLocalSave(); } }
    else if (el.dataset.reason) { const t = find(el.dataset.reason); if (t) { t.reason = el.value; bwLocalSave(); } }
    else if (el.dataset.reasonkind) { const t = find(el.dataset.reasonkind); if (t) { t.reason_kind = el.value; bwLocalSave(); } }
    else if (el.id === 'bwsummary') { BW.summary = el.value; bwLocalSave(); }
  });

  const q = document.getElementById('bwq');
  if (q) {
    const dl = document.getElementById('bwlist-teams');
    Object.keys(TEAMS).sort().forEach(t => {
      const o = document.createElement('option'); o.value = t; dl.appendChild(o);
    });
    q.addEventListener('change', () => {
      const nm = q.value.trim();
      if (!nm || !TEAMS[nm]) return;
      if (!BW.teams.find(x => x.team === nm)) BW.teams.push({ team: nm, rank: null });
      q.value = ''; bwLocalSave(); renderBallot();
    });
  }

  bwLoadHistory();
}
/* BALLOT-WORKSHOP-END */


/* ══ MATCH DESK ═══════════════════════════════════════════════════════════
   "What should I watch today, why does it matter, and what did it mean after
   final?" Presentation and decision support: every value shown is copied from
   a field that already exists. Nothing here rates anything.

   ⚠ NO COMPOSITE WATCH SCORE. The order is a stated sort and every tag names
   the fact behind it, so a reader can disagree with the reason rather than
   with a number whose ingredients are hidden.

   ⚠ AND NOTHING HERE REACHES A RATING. Live scores upgrade a card and stop
   there; POWER, RESUME, records, leaders and the rankings all wait for the
   official final and the next verified refresh. */
const DESK = {{DESK_JSON}};
const DESK_SOON_SHOWN = 12;
/* |p - 0.5| at or under this is called "close". A stated cutoff for a WORD, not
   a threshold that changes any number. */
const DESK_CLOSE = 0.10;

function deskPct(p) { return Math.round(p * 100) + '%'; }

function deskTags(m, live) {
  /* Facts only. Each tag is a thing that is true of this match, named. */
  const t = [];
  if (m.ar && m.hr) t.push(['rv', 'ranked vs ranked']);
  else if (m.ar || m.hr) t.push(['rk', 'ranked team']);
  if (m.hw != null && Math.abs(m.hw - 0.5) <= DESK_CLOSE) t.push(['cl', 'close forecast']);
  if (m.site === 'neutral') t.push(['nu', 'neutral site']);
  if (m.kind === 'conf') t.push(['cf', 'conference match']);
  if (m.event) t.push(['ev', m.event]);
  if (live) t.push(['lv', 'live']);
  /* An icon only where it adds a second channel to the word -- neutral floor
     and live. "ranked vs ranked" and "close forecast" are already words that
     say exactly what they mean, and a glyph beside them would be noise. */
  const ic = { nu: ICON_NEUTRAL, lv: ICON_LIVE };
  return t.map(x => '<span class="dtag ' + x[0] + '">' +
    (ic[x[0]] ? ic[x[0]] + ' ' : '') + esc(x[1]) + '</span>').join('');
}

function deskWhere(m) {
  if (!m.venue) return '<span class="wu">venue not listed</span>';
  const city = [m.city, m.st].filter(Boolean).join(' ');
  return esc(m.venue) + (city ? '<span class="wc">' + esc(city) + '</span>' : '');
}

function deskSide(name, avca, power, cls) {
  /* AVCA is the external poll and is labelled; POWER is ours. Both only when
     present -- a team with neither shows neither, never a placeholder rank. */
  const bits = [];
  if (avca) bits.push(rank(avca));
  return '<div class="dside ' + (cls || '') + '">' + bits.join('') +
    logo(name) + '<b>' + esc(name) + '</b>' +
    (power ? '<span class="dpow" title="our POWER rank -- how strong a team is">' +
      '<span class="rank-label">POWER</span>#' + power + '</span>' : '') +
    '</div>';
}

function deskForecast(m) {
  if (m.hw == null) {
    return '<div class="dfc none" title="' + esc(m.fsrc || '') +
      '">forecast unavailable</div>';
  }
  const homeFav = m.hw >= 0.5;
  const fav = homeFav ? m.h : m.a;
  const p = homeFav ? m.hw : 1 - m.hw;
  return '<div class="dfc"><span class="dfcl">forecast</span>' +
    '<b>' + esc(fav) + ' ' + deskPct(p) + '</b>' +
    '<span class="dfcs">' + esc(m.fsrc || '') + '</span></div>';
}

/* ---- why it matters: measured facts, nothing else --------------------- */
function deskWhy(m) {
  const out = [];
  if (m.ar && m.hr) {
    out.push('Both sides are ranked in the AVCA poll (#' + m.ar + ' and #' + m.hr + ').');
  } else if (m.ar || m.hr) {
    out.push('A ranked side: #' + (m.ar || m.hr) + ' ' + esc(m.ar ? m.a : m.h) + '.');
  }
  if (m.hw != null && Math.abs(m.hw - 0.5) <= DESK_CLOSE) {
    out.push('The forecast is close &mdash; ' + deskPct(Math.max(m.hw, 1 - m.hw)) +
      ' for the favourite, which is about as even as this model gets.');
  }
  if (m.event) out.push('Part of ' + esc(m.event) + '.');
  else if (m.site === 'neutral') out.push('A neutral floor: neither side is at home.');
  if (m.kind === 'conf') out.push('A conference match, so it counts toward the league table.');
  const tp = [];
  if (m.at != null) tp.push(esc(m.a) + ' ' + Math.round(m.at) + '%');
  if (m.ht != null) tp.push(esc(m.h) + ' ' + Math.round(m.ht) + '%');
  if (tp.length) {
    out.push('Simulated tournament odds: ' + tp.join(' · ') + '.');
  }
  /* ⚠ RESUME IS NAMED AS INACTIVE RATHER THAN OMITTED. Leaving it out would
     read as though it had been considered. */
  if (!RESUME_ACTIVE) {
    out.push('R&eacute;sum&eacute; is not active yet, so nothing here reflects ' +
      'what either team has earned.');
  }
  if (!out.length) return '';
  return '<ul class="dwhy">' + out.map(x => '<li>' + x + '</li>').join('') + '</ul>';
}

/* ---- the story after final: logged forecast vs what happened ---------- */
function deskHow(f) {
  const w = Math.max(+f.hs, +f.as), l = Math.min(+f.hs, +f.as);
  if (!w && !l) return '';
  if (l === 0) return ' in a sweep';
  if (w + l === 5) return ', but it went five';
  return ', dropping ' + (l === 1 ? 'a set' : l + ' sets');
}

/* ── THE MATCH STORY STRIP ────────────────────────────────────────────────
   Every value is one that already exists: the set line from the box score,
   what the append-only log forecast BEFORE first serve, and the result. If the
   forecast cannot be proved pre-tipoff it says so, exactly as the card does --
   a broadcast graphic is still not allowed to invent a number. */
function matchStrip(m) {
  const f = m.final;
  if (!f) return '';
  const awayWon = (+f.as) > (+f.hs);
  const winner = awayWon ? m.a : m.h;
  const sets = (f.sets || []).map(x =>
    '<span>' + x[0] + '&ndash;' + x[1] + '</span>').join('');
  const bits = [];
  bits.push('<div><span class="msl">' + ICON_FINAL + ' Final</span>' +
    '<span class="msv">' + esc(winner) + ' ' +
    (awayWon ? f.as + '&ndash;' + f.hs : f.hs + '&ndash;' + f.as) + '</span></div>');
  if (sets) {
    bits.push('<div><span class="msl">Set by set</span>' +
      '<div class="msets">' + sets + '</div></div>');
  }
  bits.push('<div><span class="msl">Forecast before first serve</span>' +
    '<span class="msv">' +
    (m.hw == null
      ? '<small>' + esc(m.fsrc || 'not available') + '</small>'
      : deskPct(awayWon ? (1 - m.hw) : m.hw) + ' ' + esc(winner) +
        ' <small>' + esc(m.fsrc || '') + '</small>') +
    '</span></div>');
  return '<div class="mstory">' + bits.join('') + '</div>';
}

function deskStory(m, proseOnly) {
  const f = m.final;
  if (!f) return '';
  const awayWon = (+f.as) > (+f.hs);
  const winner = awayWon ? m.a : m.h;
  const line = f.sets && f.sets.length
    ? '<div class="dsets">' + f.sets.map(s =>
        '<span>' + s[0] + '&ndash;' + s[1] + '</span>').join('') + '</div>'
    : '';
  let said = '';
  if (m.hw == null) {
    said = '<p class="dsaid none">No pre-match forecast was logged, so there is ' +
      'nothing to compare this against. ' + esc(m.fsrc || '') + '.</p>';
  } else {
    const pWinner = awayWon ? (1 - m.hw) : m.hw;
    const called = pWinner >= 0.5;
    said = '<p class="dsaid">Beforehand the model gave ' + esc(winner) + ' ' +
      deskPct(pWinner) + '. ' +
      (called
        ? 'The favourite won' + deskHow(f) + '.'
        : '<b>The underdog won</b>' + deskHow(f) + ' &mdash; which a forecast of ' +
          'that size expects to happen about ' + deskPct(pWinner) + ' of the time.') +
      '</p>';
  }
  if (proseOnly) return '<div class="dstory">' + said + '</div>';
  return '<div class="dstory"><div class="dfinal"><span class="dfl">FINAL</span>' +
    '<b>' + esc(winner) + '</b> ' + (awayWon ? f.as + '&ndash;' + f.hs
                                             : f.hs + '&ndash;' + f.as) + '</div>' +
    line + said + '</div>';
}

function deskCard(m, live, full) {
  const isFinal = !!m.final || (live && /final/i.test(live.state || ''));
  const cls = 'dcard' + (live && !isFinal ? ' islive' : '') + (isFinal ? ' isfinal' : '');
  let head = '<div class="dhead"><span class="dwhen">' +
    esc(m.dl || m.d) + (m.t ? ' · ' + esc(m.t) : '') + '</span>' +
    deskTags(m, live && !isFinal) + '</div>';
  let body = '<div class="dteams">' +
    deskSide(m.a, m.ao, m.ap, isFinal && m.final && +m.final.as > +m.final.hs ? 'won' : '') +
    '<span class="dat">' + connector(m) + '</span>' +
    deskSide(m.h, m.ho, m.hp, isFinal && m.final && +m.final.hs > +m.final.as ? 'won' : '') +
    '</div>';

  /* LIVE: read straight from the scoreboard feed, labelled, and never mixed
     into anything derived. */
  let livebox = '';
  if (live && !isFinal) {
    const sets = (live.sets || []).map(s =>
      '<span>' + s[0] + '&ndash;' + s[1] + '</span>').join('');
    livebox = '<div class="dlive"><span class="dlv">' + ICON_LIVE + ' LIVE</span>' +
      '<b>' + esc(live.away) + ' ' + live.away_sets + ' &ndash; ' +
      live.home_sets + ' ' + esc(live.home) + '</b>' +
      '<span class="dper">' + esc(live.period || '') + '</span>' +
      (sets ? '<div class="dsets">' + sets + '</div>' : '') +
      '<span class="dsrc">scoreboard feed, ' + esc(LIVE_STAMP || 'just now') +
      ' &mdash; not yet in any rating</span>' +
      /* ⚠ THE ROUTED DETAIL OWNS LIVE STATS NOW. A card-level inset meant the
         same match could be open in two places with two copies of the same
         panel; the route is the single destination. */
      '</div>';
  }

  return '<article class="' + cls + '">' + head + body +
    /* the strip is the FEATURED treatment only -- on a board row it would be
       the same facts twice, at the same weight as the lead */
    (full && isFinal ? matchStrip(m) : '') +
    (livebox || (isFinal ? deskStory(m, full) : deskForecast(m))) +
    '<div class="dwhere">' + deskWhere(m) + '</div>' +
    (full ? deskWhy(m) : '') + '</article>';
}

/* ---- Live Match Center: detail for the ONE card you opened -------------
   ⚠ LOCAL ONLY, AND HONEST ON A STATIC HOST. /api/match exists only behind
   live_server.py. On the published page the fetch fails, and the inset says
   so rather than spinning forever or implying it works.
   Nothing here reaches POWER, RESUME, records, forecasts or rankings -- it is
   read, shown, and thrown away. */
const LMC_OPEN = {};
const LMC_DATA = {};
let LMC_TIMER = null;

function lmcNum(v, d) {
  return (v === null || v === undefined || v === '') ? '&mdash;'
    : (typeof v === 'number' ? (d === 3 ? v.toFixed(3).replace(/^0/, '')
                                        : (Math.round(v * 10) / 10)) : esc(v));
}

function lmcBody(d) {
  if (!d) {
    return '<p class="lnote">Loading the official box score&hellip;</p>';
  }
  if (d.unreachable) {
    return '<p class="lnote">Live detail needs the local server ' +
      '(<code>scripts/live_server.py</code>). This published copy can show the ' +
      'schedule and finished results, but not live box scores.</p>';
  }
  if (!d.ok) {
    return '<p class="lnote">' + esc(d.reason || 'Detail unavailable.') + '</p>';
  }
  /* NB: the set line is NOT repeated here -- the live band directly above the
     inset already carries it, and printing it twice reads as two sources. */
  let out = '';
  if (!d.stats_available) {
    /* THE EXPECTED PATH until a live match proves otherwise. Say what we have
       and what we do not; never a zero, never a placeholder. */
    out += '<p class="lnote">' +
      (d.state === 'final'
        ? 'This match is <b>final</b>. '
        : 'Live score above is from the official scoreboard. ') +
      'Box-score detail is <b>not available from the official feed</b>' +
      (d.stats_reason ? ' &mdash; ' + esc(d.stats_reason) : '') + '.</p>';
    return out;
  }
  const t = d.teams || [];
  out += '<table><thead><tr><th>Team</th><th>K</th><th>E</th><th>TA</th>' +
    '<th>Hit%</th><th>Digs</th><th>Blk</th><th>Aces</th></tr></thead><tbody>' +
    t.map(x => '<tr><td>' + esc(x.team || x.team_id) + '</td>' +
      '<td>' + lmcNum(x.kills) + '</td><td>' + lmcNum(x.attackErrors) + '</td>' +
      '<td>' + lmcNum(x.attackAttempts) + '</td>' +
      '<td>' + lmcNum(x.hitpct, 3) + '</td><td>' + lmcNum(x.digs) + '</td>' +
      '<td>' + lmcNum(x.blocks) + '</td><td>' + lmcNum(x.serviceAces) + '</td>' +
      '</tr>').join('') + '</tbody></table>';
  /* ⚠ THIS TABLE WILL NOT ADD UP TO THE SCOREBOARD, AND A READER WILL TRY.
     Cody did, mid-match: "these stats add up to 10 points for florida but it's
     9-11". The stats are what a team EARNED -- kills, blocks, aces, which is
     his own settled definition of a point. The rest of a scoreboard is the
     OPPONENT's errors, and that is a large share of it: measured live in this
     very match, Florida held 12 points having earned 7.5, the other 4.5
     arriving from Nebraska's six attack errors.
     Saying so costs one line and stops the table reading as broken. */
  out += '<p class="lnote">Kills, blocks and aces are what a team <b>earned</b>' +
    ' — they will not add up to the score, because the rest of a scoreboard is' +
    ' the other team\u2019s errors.</p>';
  if (d.leaders && d.leaders.length) {
    out += '<p class="lmcldr">' + d.leaders.map(p =>
      '<b>' + esc(p.name) + '</b> ' + esc(p.team) + ' &middot; ' +
      p.kills + 'k' + (p.aces ? ', ' + p.aces + ' ace' + (p.aces > 1 ? 's' : '') : '') +
      (p.digs ? ', ' + p.digs + ' digs' : '')).join('<br>') + '</p>';
  }
  return out;
}

function lmcRender(gid) {
  const host = document.getElementById('lmc-' + gid);
  if (!host) return;
  const d = LMC_DATA[gid];
  const stamp = d && d.scoreboard_updated ? d.scoreboard_updated : '';
  const stale = d && d.stale;
  host.innerHTML =
    '<div class="lhd"><span class="ldot"></span>' +
    (d && d.state === 'final' ? 'Final' : 'Live') +
    ' &mdash; official NCAA feed' +
    (stamp ? ' &mdash; refreshed ' + esc(stamp) : '') +
    (stale ? ' &mdash; <b>stale, retrying</b>' : '') +
    '<span style="color:var(--ink3)">Not used in ratings until final</span>' +
    '</div>' + lmcBody(d);
  /* the freshness line beside the manual control, so the reader can see when
     the last SUCCESSFUL refresh was without reading the panel */
  /* ⚠ ONE LIVE-BOX STATE, EVERY SECTION TOGETHER. The Box score section is
     rendered once from the BULK feed's verdict, which is 'live_score_only'
     for every live match -- the scoreboard call cannot see stats. This
     per-match fetch CAN, and the page was leaving both verdicts standing:
     a populated Live-stats table above a note reading "the source is not
     serving statistics for this match yet" (caught by outside review,
     2026-08-28, on Stanford-Wisconsin). The per-match resolve is the more
     informed one, so when it lands it OWNS the state note -- same words,
     same table (match_state.py), later knowledge. */
  const mp = document.getElementById('mpendnote');
  if (mp && d && !d.unreachable && d.state_label && d.state_note) {
    mp.innerHTML = '<b>' + esc(d.state_label) + '</b><span>' +
      esc(d.state_note) + '</span>';
  }
  const sp = document.getElementById('lmcstamp');
  if (sp) {
    sp.textContent = !d ? 'contacting the local server\u2026'
      : d.unreachable ? 'live stats need the local server'
      : d.state === 'final' ? 'final \u2014 refreshing has stopped'
      : (d.stale ? 'stale, retrying \u2014 last good ' : 'refreshed ') +
        (d.scoreboard_updated || 'just now') +
        (d.age_seconds ? ' (' + d.age_seconds + 's ago)' : '');
  }
}

async function lmcFetch(gid) {
  let d = null;
  try {
    const r = await fetch('/api/match?id=' + encodeURIComponent(gid),
                          { cache: 'no-store' });
    d = await r.json();
  } catch (e) {
    d = { unreachable: true };                 /* static host: say so plainly */
  }
  LMC_DATA[gid] = d;
  lmcRender(gid);
}

/* ── LIVE STATS, SCOPED TO THE OPEN ROUTE ─────────────────────────────────
   ⚠ EXACTLY ONE MATCH POLLS, AND ONLY WHILE ITS ROUTE IS OPEN. The phase-1
   timer walked every card that had been expanded, so leaving a card open and
   navigating away kept it polling. This one knows the single game id it is
   for and stops itself on a route change, on a switch to another match, and
   the moment the feed says final -- a finished match has nothing left to
   refresh, and the verified result comes through the normal pipeline. */
let LMC_ROUTE_GID = null;

function lmcStop() {
  if (LMC_TIMER) { clearInterval(LMC_TIMER); LMC_TIMER = null; }
  LMC_ROUTE_GID = null;
}

function lmcStart(gid) {
  if (LMC_ROUTE_GID === gid && LMC_TIMER) return;   /* already on this one */
  lmcStop();
  LMC_ROUTE_GID = gid;
  lmcFetch(gid);
  LMC_TIMER = setInterval(() => {
    if (LMC_ROUTE_GID !== gid) { lmcStop(); return; }
    const d = LMC_DATA[gid];
    if (d && d.state === 'final') { lmcStop(); lmcRender(gid); return; }
    lmcFetch(gid);
  }, LMC_EVERY_MS);
}

const LMC_EVERY_MS = 20000;

/* the section the routed detail hosts */
function lmcSection(gid) {
  return '<div class="msec"><h3>Live stats</h3>' +
    '<div class="lmcbar">' +
      '<button type="button" class="lmcbtn" id="lmcrefresh">Refresh live stats</button>' +
      '<span class="lmcnote" id="lmcstamp"></span>' +
    '</div>' +
    '<div class="lmc" id="lmc-' + esc(gid) + '">' +
      '<p class="lnote">Loading the official box score&hellip;</p></div></div>';
}

/* Digby's poses, inlined once. The public build gets the two that carry no
   private context and an empty string for the two that do. */
const ICON_FINAL = `{{ICON_FINAL}}`;
const ICON_LIVE = `{{ICON_LIVE}}`;
const ICON_NEUTRAL = `{{ICON_NEUTRAL}}`;
const ICON_TV = `{{ICON_TV}}`;
const ICON_ROAD = `{{ICON_ROAD}}`;
const ICON_UNAVAIL = `{{ICON_UNAVAIL}}`;
const TRENDS = {{TREND_JSON}};
const DIGBY_BRIEF = `{{DIGBY_BRIEF}}`;
const DIGBY_WATCH = `{{DIGBY_WATCH}}`;

let LIVE_STAMP = '';
let LIVE_BY_ID = {};


/* GAMEDAY-JS-BEGIN */
/* ⚠ A READINESS PANEL, NOT A DEVELOPER DASHBOARD. Four checkpoints, what has
   actually been observed, and one sentence that refuses to overclaim. It shows
   on the Match Desk only while the question is open. */
const GAMEDAY = {{GAMEDAY_JSON}};

function gdPanel() {
  const g = GAMEDAY;
  if (!g || g.none === undefined) return '';
  if (g.none) {
    return '<div class="gd-panel"><div class="vx-label"><b>Live validation' +
      '</b></div><p class="gd-none">No upcoming Division-I fixture on file, ' +
      'so there is nothing to validate against yet.</p></div>';
  }
  const step = (k, label) => {
    const got = (g.done || {})[k];
    return '<li class="gd-step' + (got ? ' done' : '') + '">' +
      '<i>' + esc(label) + '</i>' +
      '<b>' + (got ? esc(got) : 'not yet observed') + '</b></li>';
  };
  return '<div class="gd-panel">' +
    '<div class="vx-label"><b>Next live validation</b></div>' +
    '<div class="gd-head"><b>' + esc(g.matchup) + '</b>' +
      '<span>' + esc(g.when_pt) + '</span>' +
      '<a href="' + esc(g.link) + '" target="_blank" rel="noopener noreferrer">' +
      'game ' + esc(g.game_id) + '</a></div>' +
    '<ol class="gd-steps">' +
      (g.steps || []).map(x => step(x[0], x[1])).join('') + '</ol>' +
    /* ⚠ THE SENTENCE THAT MUST NOT DRIFT. */
    '<p class="gd-claim">' + (g.live_stats_proven
      ? 'A real match has been observed serving team totals in progress.'
      : 'Live team and player statistics are <b>not established</b>. ' +
        'Nothing on this site claims they are until a match has been ' +
        'observed serving them.') + '</p>' +
    '</div>';
}
/* GAMEDAY-JS-END */

/* INTEL-JS-BEGIN */
/* ═══ INTEL DESK ═════════════════════════════════════════════════════════
   A private wire. The browser NEVER fetches a feed: it asks the local server,
   which only ever requests URLs from its own allowlist. Read state lives on
   this device; nothing about what Cody has read goes anywhere.

   ⚠ FOUR FIELDS PER STORY -- title, link, time, source -- and the click goes
   to the publisher. No article text, no blurb, no thumbnail, no summary. */

const IN_KEY = 'wvb.intel.read.v1';
let IN_ITEMS = [];
let IN_SRC = [];
let IN_READ = {};
let IN_OK = true;
let IN_FILTER = 'new';
let IN_CHECKED = 0;

function inLoad() {
  try {
    const raw = window.localStorage.getItem(IN_KEY);
    const v = raw ? JSON.parse(raw) : {};
    IN_READ = (v && typeof v === 'object' && !Array.isArray(v)) ? v : {};
    IN_OK = true;
  } catch (e) { IN_READ = {}; IN_OK = false; }
  return IN_READ;
}
function inSave() {
  try { window.localStorage.setItem(IN_KEY, JSON.stringify(IN_READ)); IN_OK = true; }
  catch (e) { IN_OK = false; }
}

/* ⚠ RELEVANCE IS CONSERVATIVE ON PURPOSE. A story attaches to a My Board team
   only when that team's normalised name appears as a WHOLE phrase in the
   headline -- no fuzzy matching, no nicknames, and "Texas" cannot swallow
   "Texas A&M" by prefix because both sides are padded with spaces. An
   uncertain match stays National. A wrong match is worse than an unsorted one:
   this is the surface where a guess would look like a fact. */
function inNorm(t) {
  return ' ' + String(t || '').toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim() + ' ';
}
function inMatch(title) {
  const hay = inNorm(title);
  const hits = [];
  let board = [];
  try { mbLoad(); board = (typeof MB !== 'undefined' && Array.isArray(MB)) ? MB : []; }
  catch (e) { board = []; }
  board.forEach(team => {
    const needle = inNorm(team);
    if (needle.trim().length < 3) return;
    if (hay.indexOf(needle) < 0) return;
    /* ⚠ A LONGER TEAM NAME WINS, AND THIS WAS A REAL FALSE MATCH. Padding
       with spaces stops "Texarkana" matching "Texas" -- but not "Texas A&M",
       which normalises to "texas a m" and CONTAINS " texas ". The headline
       "SMU sweeps Texas A&M" was being filed under Texas, which is precisely
       the guess-that-looks-like-a-fact this desk must not make.
       So: if any OTHER Division-I team whose name contains this one is also
       in the headline, this match is ambiguous and is dropped. Unmatched is
       the safe answer; National is not a failure state. */
    let shadowed = false;
    try {
      for (const other in TEAMS) {
        if (other === team) continue;
        const on = inNorm(other);
        if (on.length <= needle.length) continue;
        if (on.indexOf(needle.trim()) < 0) continue;   /* not a longer form */
        if (hay.indexOf(on) >= 0) { shadowed = true; break; }
      }
    } catch (e) { /* payload not ready: keep the plain match */ }
    if (!shadowed) hits.push(team);
  });
  return hits;
}

function inWhen(s) {
  const d = new Date(s);
  if (!isFinite(d)) return String(s || '').slice(0, 16);
  const p = n => (n < 10 ? '0' : '') + n;
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
         ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

/* ══ THE WIRE ═════════════════════════════════════════════════════════════
   Three media states, named, and a story never silently changes between them.

     source-provided  a direct HTTPS URL the AUDITED feed delivered in its own
                      <enclosure>, on the one approved host. Private build
                      only. Never downloaded, never rehosted, never ours.
     derived-native   a Match Moment built from data we already hold, used only
                      when a story can be tied to a known match CONSERVATIVELY.
     unavailable      no picture. A designed court panel that says so, never a
                      grey box and never a stand-in photograph.

   ⚠ THE GATE IS SERVER-SIDE (intel.media_url) AND THIS SIDE TRUSTS NOTHING.
   The page re-checks scheme and host before it will emit an <img>, because a
   cached payload from an older build is a real thing that can reach this code.
   Two gates is not belt-and-braces here; the two run in different processes
   with different lifetimes. */
const IN_MEDIA_HOSTS = {{INTEL_MEDIA_HOSTS_JSON}};

function inImageOK(u) {
  if (!u || typeof u !== 'string') return null;
  try {
    const p = new URL(u);
    if (p.protocol !== 'https:') return null;
    if (p.username || p.password || p.port) return null;
    if (IN_MEDIA_HOSTS.indexOf(p.hostname.toLowerCase()) < 0) return null;
    if (p.pathname.indexOf('/_flysystem/') !== 0) return null;
    return u;
  } catch (e) { return null; }
}

/* ⚠ TIE A STORY TO A MATCH ONLY WHEN IT IS UNAMBIGUOUS. Both teams named in
   the headline, one match today or in the last two days between exactly those
   two -- otherwise no Moment. A poster attached to the wrong match would be a
   confident, checkable, wrong statement, which is worse than no picture. */
function inMatchOf(title) {
  const teams = inMatch(title);
  if (teams.length !== 2) return null;
  const by = allMatches();
  const today = todayPT();
  const cand = Object.keys(by).map(k => by[k]).filter(m => {
    if (!m.d || m.d > today) return false;
    const days = (new Date(today) - new Date(m.d)) / 86400000;
    if (days > 2) return false;
    const pair = [mAway(m), mHome(m)];
    return pair.indexOf(teams[0]) >= 0 && pair.indexOf(teams[1]) >= 0;
  });
  return cand.length === 1 ? cand[0] : null;   /* exactly one, or none */
}

function inMediaState(it) {
  const img = inImageOK(it.image);
  if (img) return { kind: 'source-provided', url: img };
  const m = inMatchOf(it.title);
  if (m) return { kind: 'derived-native', match: m };
  return { kind: 'unavailable' };
}

function inMediaHTML(it, big) {
  const st = inMediaState(it);
  if (st.kind === 'source-provided') {
    /* ⚠ FIXED RATIO, LAZY, ASYNC, AND AN ERROR PATH THAT IS NOT A BROKEN
       GLYPH. The audit found no declared type and no dimensions, and the URL
       carries a Drupal ?itok= token that CAN be invalidated later -- so an
       image that loads today may 404 next week. The container reserves 16:9
       either way, so nothing shifts when it fails. */
    return '<div class="in-media ' + (big ? 'big' : '') + '" data-media="source">' +
      /* ⚠ NO loading="lazy" AND NO decoding="async" HERE, AND THE REASON IS
         MEASURED. With either of them the photograph fetched and decoded --
         complete:true, naturalWidth 1280, naturalHeight 720 -- and the box
         painted flat navy anyway. Rebuilding the identical element, from the
         identical URL, in the identical container, WITHOUT them renders it
         immediately. These images are created by innerHTML inside a section
         that is `hidden` until its route opens, and both attributes exist to
         let the browser defer work; deferred inside a hidden subtree, the
         paint is never scheduled once the bytes land.
         The brief asked for lazy and async, and they are the right defaults in
         general. They are wrong HERE, and a blank box is a worse outcome than
         an eager fetch of one above-the-fold image. Stated rather than quietly
         dropped. referrerpolicy stays: it costs nothing and keeps the hub's
         own URL out of the publisher's logs. */
      '<img src="' + esc(st.url) + '" alt="" ' +
      'referrerpolicy="no-referrer" ' +
      'onload="inImgShown(this)" onerror="inImgFail(this)">' +
      '<span class="in-credit">Image: NCAA.com</span></div>';
  }
  if (st.kind === 'derived-native') {
    return '<div class="in-media ' + (big ? 'big' : '') + '" data-media="derived">' +
      momentHTML(st.match, LIVE_BY_ID[st.match.gid], { nolink: true }) +
      '</div>';
  }
  return '<div class="in-media ' + (big ? 'big' : '') + '" data-media="none">' +
    '<div class="in-nomedia cs-court"><span>No picture with this story</span>' +
    '</div></div>';
}

/* ⚠ THE PHOTO LOADED AND THE PAGE NEVER REPAINTED IT. Measured, after two
   wrong diagnoses of my own:
     - the file fetched and decoded -- complete:true, naturalWidth 1280,
       naturalHeight 720, and the same URL renders perfectly on its own;
     - elementFromPoint at the box centre returned the <img> itself, opacity 1,
       visibility visible, no filter, transform, clip or blend;
     - and the box painted flat navy.
   I first blamed `aspect-ratio` + `height:100%`, then `aspect-ratio` alone --
   BOTH "isolations" were confounded, because the way I turned the property off
   was an INLINE STYLE WRITE, and that forces a repaint. The repaint was doing
   the work, not the property. The proof is a no-op: setting opacity to 0.999,
   which changes no geometry at all, makes the photograph appear.
   So the mechanism is invalidation. These images are created inside a section
   that is `hidden` until the route opens, they carry loading="lazy" and
   decoding="async" -- both of which exist to let the browser defer -- and
   nothing ever tells it the region needs repainting once the bytes land.
   The fix addresses that rather than guessing at an attribute: onload marks
   the container, which invalidates it. lazy and async are kept, because the
   reason for them (no layout shift, no blocking decode) is still right.
   ⚠ A GEOMETRY ASSERTION CANNOT CATCH THIS. Every reading was identical in the
   broken state and the working one. test_wire.py asserts the onload hook
   exists, because the hook is the part that was missing. */
function inImgShown(img) {
  const box = img.parentNode;
  if (box && box.classList) box.classList.add('is-shown');
}

/* ⚠ AN IMAGE CAN FINISH BEFORE ITS HANDLER IS BOUND. innerHTML parses the
   markup and a cached file can be complete by the time the browser gets to the
   onload attribute, in which case the event never fires and -- now that the
   image starts transparent -- it would stay invisible forever. The fix is not
   to make the CSS forgiving; it is to ask, once, after painting the list. */
function inSweepImages(host) {
  if (!host) return;
  host.querySelectorAll('.in-media img').forEach(im => {
    if (im.complete && im.naturalWidth) inImgShown(im);
  });
}

/* the error path, global so the inline handler can reach it */
function inImgFail(img) {
  const box = img.parentNode;
  if (!box) return;
  box.setAttribute('data-media', 'none');
  box.innerHTML = '<div class="in-nomedia cs-court">' +
    '<span>The publisher&rsquo;s image did not load</span></div>';
}

/* ⚠ FORMAT FROM THE PUBLISHER'S OWN URL SHAPE, and only shapes I have seen.
   Anything else is "Story" rather than a guess. */
function inFormat(link) {
  const p = String(link || '');
  if (/\/video\//i.test(p)) return 'Video';
  if (/\/live-updates\//i.test(p)) return 'Live updates';
  if (/\/news\//i.test(p)) return 'Story';
  return 'Story';
}

/* ══ STORY FAMILIES ═══════════════════════════════════════════════════════
   The feed runs an article and a video of the same thing within minutes.
   Grouping them is a READING convenience and must not become an editorial act:
   nothing is deleted, every original link survives, and no "canonical version"
   is invented -- the first by publication time leads and the rest are listed
   with their format.

   ⚠ CONSERVATIVE ON PURPOSE. Same source, published within 36 hours, and a
   token overlap of 0.6 or better on the headline. Two genuinely different
   stories that happen to share vocabulary stay apart, which is the failure
   worth having. */
const IN_RAIL = 6;          /* four to six information-dense rows */
let IN_RAIL_ALL = false;
const IN_FAMILY_J = 0.6;
const IN_FAMILY_HOURS = 36;
const IN_STOP = ('the a an and or of in on at to for with vs v is are was were '
  + 'as by from its it this that day final').split(' ');

function inTokens(title) {
  const t = String(title || '').toLowerCase()
    .replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/)
    .filter(w => w && w.length > 2 && IN_STOP.indexOf(w) < 0);
  return t;
}
function inJaccard(a, b) {
  const A = {}, B = {};
  a.forEach(w => A[w] = 1); b.forEach(w => B[w] = 1);
  const ka = Object.keys(A), kb = Object.keys(B);
  if (!ka.length || !kb.length) return 0;
  let inter = 0;
  ka.forEach(w => { if (B[w]) inter++; });
  return inter / (ka.length + kb.length - inter);
}
function inTime(it) {
  const d = new Date(it.published || 0);
  return isNaN(d.getTime()) ? 0 : d.getTime();
}

function inFamilies(rows) {
  const used = {};
  const out = [];
  rows.forEach((it, i) => {
    if (used[i]) return;
    const fam = [it];
    used[i] = 1;
    const ta = inTokens(it.title);
    rows.forEach((jt, j) => {
      if (j <= i || used[j]) return;
      if (jt.source_key !== it.source_key) return;
      const hrs = Math.abs(inTime(jt) - inTime(it)) / 3600000;
      if (!(hrs <= IN_FAMILY_HOURS)) return;
      if (inJaccard(ta, inTokens(jt.title)) < IN_FAMILY_J) return;
      fam.push(jt);
      used[j] = 1;
    });
    /* oldest first -- the original report leads, the follow-ups are listed */
    fam.sort((x, y) => inTime(x) - inTime(y));
    out.push(fam);
  });
  return out;
}

/* THE LEAD. One story, given room -- source, time, headline, the link out,
   and one picture in whichever of the three states applies. */
function inLead(fam) {
  const it = fam[0];
  const teams = inMatch(it.title);
  const read = !!IN_READ[it.id];
  return '<article class="in-lead' + (read ? ' read' : '') + '" data-in="' +
    esc(it.id) + '">' +
    inMediaHTML(it, true) +
    '<div class="in-leadtext">' +
      '<div class="in-meta"><span class="in-src">' + esc(it.source) + '</span>' +
        '<time>' + esc(inWhen(it.published)) + '</time>' +
        '<span class="in-fmt">' + esc(inFormat(it.link)) + '</span>' +
        (teams.length ? '<span class="in-teams">' +
          teams.map(t => logo(t) || '').join('') +
          teams.map(t => '<b>' + esc(t) + '</b>').join('') + '</span>' : '') +
      '</div>' +
      '<a class="in-leadtitle" href="' + esc(it.link) + '" target="_blank" ' +
        'rel="noopener noreferrer">' + esc(it.title) + '</a>' +
      inAlso(fam) +
      '<div class="in-acts">' +
        '<a class="in-out" href="' + esc(it.link) + '" target="_blank" ' +
          'rel="noopener noreferrer">Read at ' + esc(it.source) + ' &rarr;</a>' +
        '<button type="button" data-inread="' + esc(it.id) + '">' +
          (read ? 'Mark unread' : 'Mark read') + '</button>' +
        '<button type="button" data-innote="' + esc(it.id) + '">Note this</button>' +
      '</div>' +
    '</div></article>';
}

/* ⚠ THE OTHER MEMBERS OF A FAMILY ARE LISTED, NOT SWALLOWED. Every original
   link survives with its own format label. Nothing is deleted and no canonical
   version is invented -- this is a reading convenience, not an edit. */
function inAlso(fam) {
  if (!fam || fam.length < 2) return '';
  return '<div class="in-also"><i>Also from ' + esc(fam[0].source) + '</i>' +
    fam.slice(1).map(x =>
      '<a href="' + esc(x.link) + '" target="_blank" rel="noopener noreferrer">' +
      esc(inFormat(x.link)) + '</a>').join('') + '</div>';
}

function inRow(it) {
  const teams = inMatch(it.title);
  const read = !!IN_READ[it.id];
  return '<article class="in-row' + (read ? ' read' : '') + '" data-in="' +
    esc(it.id) + '">' +
    '<div class="in-meta"><span class="in-src">' + esc(it.source) + '</span>' +
    '<time>' + esc(inWhen(it.published)) + '</time>' +
    '<span class="in-fmt">' + esc(inFormat(it.link)) + '</span>' +
    (teams.length
      ? '<span class="in-teams">' + teams.map(t => logo(t) || '').join('') +
        teams.map(t => '<b>' + esc(t) + '</b>').join('') + '</span>'
      : '') +
    '</div>' +
    /* ⚠ THE HEADLINE IS A LINK TO THE PUBLISHER. Reading happens there. */
    '<a class="in-title" href="' + esc(it.link) + '" target="_blank" ' +
    'rel="noopener noreferrer">' + esc(it.title) + '</a>' +
    (it._fam ? inAlso(it._fam) : '') +
    '<div class="in-acts">' +
      '<button type="button" data-inread="' + esc(it.id) + '">' +
      (read ? 'Mark unread' : 'Mark read') + '</button>' +
      '<button type="button" data-innote="' + esc(it.id) + '">Note this</button>' +
    '</div></article>';
}

function inRender() {
  const host = document.getElementById('intelbody');
  if (!host) return;
  inLoad();
  const board = (() => { try { mbLoad(); return (typeof MB !== 'undefined' && Array.isArray(MB)) ? MB : []; } catch (e) { return []; } })();
  let rows = IN_ITEMS.slice();
  if (IN_FILTER === 'new') rows = rows.filter(i => !IN_READ[i.id]);
  else if (IN_FILTER === 'read') rows = rows.filter(i => !!IN_READ[i.id]);
  else if (IN_FILTER === 'board') rows = rows.filter(i => inMatch(i.title).length);
  else if (IN_FILTER === 'national') rows = rows.filter(i => !inMatch(i.title).length);

  const cnt = document.getElementById('intelcount');
  if (cnt) cnt.textContent = rows.length + (rows.length === 1 ? ' story' : ' stories');

  /* ⚠ EVERY STATE IS ITS OWN SENTENCE. "Nothing new" and "the source is
     down" are different facts and must not share a blank screen. */
  const bad = IN_SRC.filter(x => !x.ok);
  const stale = IN_SRC.filter(x => x.stale);
  let banner = '';
  if (bad.length) {
    banner = '<div class="in-note warn"><b>' + esc(bad[0].source) +
      ' is not reachable.</b> ' + esc(bad[0].error || '') +
      ' Nothing has been lost \u2014 this is what was last collected.</div>';
  } else if (stale.length) {
    banner = '<div class="in-note warn"><b>Showing the last successful ' +
      'check.</b> ' + esc(stale[0].error || 'The source did not answer just now.') +
      '</div>';
  }
  if (!IN_OK) {
    banner += '<div class="in-note warn"><b>This browser is not letting the ' +
      'page store anything</b>, so read marks will not survive a reload.</div>';
  }

  if (!rows.length) {
    const why = IN_FILTER === 'new'
      ? 'Nothing unread. Everything on the wire has been seen.'
      : (IN_FILTER === 'board'
          ? (board.length
              ? 'No story on the wire mentions a team on My Board.'
              : 'My Board is empty, so nothing can be matched to it yet.')
          : 'Nothing here under this filter.');
    host.innerHTML = banner + '<div class="vx-empty"><h4>Nothing to read</h4>' +
      '<p>' + esc(why) + '</p></div>';
    return;
  }
  /* ⚠ GROUP FIRST, THEN LEAD, THEN RAIL. Grouping after choosing a lead would
     let a follow-up video become the lead while its own article sat below it.
     ⚠ AND MY BOARD ORDERS, IT DOES NOT RANK. Stories matching a watched team
     sort first under that filter; every one keeps its source and its time, and
     nothing is labelled more important than anything else. */
  const fams = inFamilies(rows);
  if (IN_FILTER === 'board' && board.length) {
    fams.sort((a, b) => (inMatch(b[0].title).length ? 1 : 0)
                      - (inMatch(a[0].title).length ? 1 : 0));
  }
  const lead = fams[0];
  const rail = IN_RAIL_ALL ? fams.slice(1) : fams.slice(1, 1 + IN_RAIL);
  const restN = Math.max(0, fams.length - 1 - rail.length);
  const paint = banner +
    inLead(lead) +
    (rail.length
      ? '<div class="in-railhd">The wire</div><div class="in-rail">' +
        rail.map(f => {
          const it = Object.assign({}, f[0]);
          it._fam = f;
          return inRow(it);
        }).join('') + '</div>'
      : '') +
    (restN
      ? '<button type="button" class="in-more" id="inmore">Show ' + restN +
        ' more ' + (restN === 1 ? 'story' : 'stories') + '</button>'
      : '');
  host.innerHTML = paint;
  inSweepImages(host);
}

/* ⚠ THE PAGE ASKS THE LOCAL SERVER. It never requests a feed itself, and it
   passes no URL -- only an optional `force`. Opened straight from Finder this
   fetch fails and the desk says the local server is not running, which is the
   truth rather than an empty wire. */
/* ⚠ "CHECKING..." MUST END, AND IT MUST NOT DESTROY WHAT IS ALREADY THERE.
   The previous version had two faults that only appear when the endpoint is
   slow or gone: fetch() carries no timeout of its own, so a hung local server
   left the word on screen indefinitely with nothing to distinguish it from a
   slow answer; and the catch() emptied IN_ITEMS, so a failed refresh threw
   away stories that were on the page a second earlier. A wire that goes blank
   because the CHECK failed is saying something false about the wire.
   Now: an abort at IN_TIMEOUT_MS, cached stories retained, and a plain
   sentence saying no update was received. */
const IN_TIMEOUT_MS = 12000;

function inFetch(force) {
  const st = document.getElementById('intelstate');
  if (st) st.textContent = 'Checking…';
  const ctl = (typeof AbortController === 'function') ? new AbortController() : null;
  let timedOut = false;
  const timer = setTimeout(function () {
    timedOut = true;
    if (ctl) { try { ctl.abort(); } catch (e) { } }
  }, IN_TIMEOUT_MS);

  const done = function (msg) {
    clearTimeout(timer);
    if (st) st.textContent = msg;
    inRender();
  };

  fetch('/api/intel' + (force ? '?force=1' : ''),
        Object.assign({ cache: 'no-store' }, ctl ? { signal: ctl.signal } : {}))
    .then(r => r.json())
    .then(j => {
      const items = (j && Array.isArray(j.items)) ? j.items : [];
      /* ⚠ ONLY REPLACE WHAT IS THERE WITH SOMETHING. An empty answer is not a
         reason to clear a wire that is already populated. */
      if (items.length) {
        IN_ITEMS = items;
        IN_SRC = (j && Array.isArray(j.sources)) ? j.sources : [];
        IN_CHECKED = Date.now();
        done('Checked ' + inWhen(new Date(IN_CHECKED).toISOString()));
      } else {
        IN_SRC = (j && Array.isArray(j.sources)) ? j.sources : IN_SRC;
        done(IN_ITEMS.length
          ? 'No update received. Showing what was last collected.'
          : ((j && j.error) ? 'The source did not return any stories.'
                            : 'Nothing came back.'));
      }
    })
    .catch(() => {
      const why = timedOut
        ? 'The check timed out after ' + Math.round(IN_TIMEOUT_MS / 1000) +
          ' seconds. No update received.'
        : 'The local server is not running, so the wire cannot be checked.';
      done(IN_ITEMS.length ? why + ' Showing what was last collected.'
                           : why + ' Everything else on this page still works.');
    });
}

function inWire() {
  const host = document.getElementById('v-intel');
  if (!host || host.dataset.wired) return;
  host.dataset.wired = '1';

  host.addEventListener('click', e => {
    const seg = e.target.closest('[data-inf]');
    if (seg) {
      IN_FILTER = seg.dataset.inf;
      host.querySelectorAll('[data-inf]').forEach(b =>
        b.classList.toggle('on', b === seg));
      inRender();
      return;
    }
    const rd = e.target.closest('[data-inread]');
    if (rd) {
      const id = rd.dataset.inread;
      if (IN_READ[id]) delete IN_READ[id]; else IN_READ[id] = 1;
      inSave(); inRender();
      return;
    }
    const nt = e.target.closest('[data-innote]');
    if (nt) {
      /* ⚠ PREFILLED, NEVER SAVED. The note is opened with the source's title
         and link filled in and the body left EMPTY -- the takeaway has to be
         Cody's, so nothing is created until he writes one and presses Save. */
      const it = IN_ITEMS.find(x => x.id === nt.dataset.innote);
      if (!it) return;
      go(routeFor('film'));
      setTimeout(() => {
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        set('frtitle', it.title);
        set('frurl', it.link);
        set('frsrc', 'article');
        set('frnote', '');
        const teams = inMatch(it.title);
        if (teams.length) set('frteams', teams.join(', '));
        const body = document.getElementById('frnote');
        if (body) { body.focus(); }
        const stt = document.getElementById('frstate');
        if (stt) stt.textContent = 'Add your own takeaway, then Save.';
      }, 250);
      return;
    }
    if (e.target.closest('#inmore')) { IN_RAIL_ALL = true; inRender(); return; }
    if (e.target.closest('#intelrefresh')) inFetch(true);
  });
  inFetch(false);
}

/* INTEL-JS-END */

/* FILMROOM-JS-BEGIN */
/* ═══ FILM ROOM / VOTING NOTEBOOK ═════════════════════════════════════════
   Cody's own observations, kept on Cody's own device.

   ⚠ THE PRIVACY MODEL IS MY BOARD'S, DELIBERATELY. localStorage only, fail
   soft, and NOTHING about a note -- its text, its links, its tags, even the
   fact that one exists -- reaches the public build, the rating payload, a
   prediction, the ballot file, Digby's facts, or git. The whole feature lives
   inside these sentinels so the public build removes it wholesale rather than
   hiding it; hiding private content still ships it, which this project has
   already learned once with third-party rank VALUES hidden in a payload.

   ⚠ AND NOTES NEVER BECOME EVIDENCE THE SITE CITES. A note is Cody's opinion
   or Cody's transcription. It is displayed back to him and nowhere else -- it
   does not weight a rating, fill a ballot, or turn into a "reason". The one
   thing a note may carry that IS checkable is a FROZEN FACT CHIP: a value
   copied out of the hub at a stated moment, stamped with that moment, so a
   month later it is clear the number is a snapshot and not a live read. */

const FR_KEY = 'wvb.filmroom.v1';
let FR = [];
let FR_OK = true;

/* the three moments a note can belong to, and where a note came from */
const FR_CTX = [['pre', 'Pre-match'], ['during', 'During match'],
                ['post', 'Post-match']];
const FR_SRC = [['self', 'Watched myself'], ['official', 'Official stat/source'],
                ['article', 'Article'], ['community', 'Community discussion'],
                ['other', 'Other']];

function frLoad() {
  try {
    const raw = window.localStorage.getItem(FR_KEY);
    const v = raw ? JSON.parse(raw) : [];
    FR = Array.isArray(v) ? v : [];
    FR_OK = true;
  } catch (e) {
    /* ⚠ FAIL SOFT AND SAY SO. Private window, blocked site data or a full
       quota all land here. The notebook then works for this session and
       persists nothing, and the view says that plainly rather than pretending
       to have saved. */
    FR = [];
    FR_OK = false;
  }
  return FR;
}

function frSave() {
  try {
    window.localStorage.setItem(FR_KEY, JSON.stringify(FR));
    FR_OK = true;
  } catch (e) { FR_OK = false; }
  return FR_OK;
}

function frId() {
  return 'n' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

/* ⚠ A FROZEN FACT IS STAMPED AT THE MOMENT IT IS TAKEN. It is read out of the
   payload once and stored as text; it is never re-read later. That is the
   whole point -- "Kentucky POWER #3" means #3 on the day it was captured, and
   a chip that silently updated itself would be a different claim. */
function frFreezeTeam(team) {
  const out = [];
  try {
    const t = TEAMS[team];
    if (!t) return out;
    if (t.rank) out.push({ k: 'POWER', v: '#' + t.rank });
    if (t.avca) out.push({ k: 'AVCA', v: '#' + t.avca });
    if (t.record26) out.push({ k: 'Record', v: t.record26 });
  } catch (e) { /* payload not ready: no chips rather than wrong ones */ }
  return out.map(c => ({ k: c.k, v: c.v, at: new Date().toISOString() }));
}

function frFreezeMatch(gid) {
  const out = [];
  try {
    const m = matchByGid(gid);
    if (!m) return out;
    const sc = matchScore(m, LIVE_BY_ID[gid]);
    out.push({ k: 'Match', v: mAway(m) + ' ' + connector(m) + ' ' + mHome(m) });
    if (sc && sc[0] !== null && sc[0] !== undefined) {
      out.push({ k: 'Score', v: sc[0] + '\u2013' + sc[1] });
    }
    if (m.d) out.push({ k: 'Date', v: m.d });
  } catch (e) { /* nothing rather than something invented */ }
  return out.map(c => ({ k: c.k, v: c.v, at: new Date().toISOString() }));
}

function frAdd(note) {
  frLoad();
  const n = {
    id: frId(),
    created: new Date().toISOString(),
    ctx: note.ctx || 'post',
    title: (note.title || '').slice(0, 200),
    body: (note.body || '').slice(0, 4000),
    teams: (note.teams || []).slice(0, 8),
    players: (note.players || []).slice(0, 8),
    gid: note.gid || '',
    src: note.src || '',
    /* ⚠ THE URL IS STORED; THE PAGE BEHIND IT IS NEVER FETCHED. No request is
       made, nothing is scraped, and no third-party text is copied in. What is
       kept is Cody's own link and Cody's own takeaway. */
    url: (note.url || '').slice(0, 500),
    facts: note.facts || []
  };
  FR.unshift(n);
  frSave();
  return n;
}

function frRemove(id) {
  frLoad();
  const i = FR.findIndex(n => n.id === id);
  if (i >= 0) { FR.splice(i, 1); frSave(); }
  return i >= 0;
}

function frFor(opts) {
  frLoad();
  const o = opts || {};
  return FR.filter(n => {
    if (o.team && (n.teams || []).indexOf(o.team) < 0) return false;
    if (o.player && (n.players || []).indexOf(o.player) < 0) return false;
    if (o.gid && n.gid !== o.gid) return false;
    if (o.ctx && n.ctx !== o.ctx) return false;
    if (o.src && n.src !== o.src) return false;
    if (o.q) {
      const hay = (n.title + ' ' + n.body + ' ' + (n.teams || []).join(' ') +
                   ' ' + (n.players || []).join(' ')).toLowerCase();
      if (hay.indexOf(o.q.toLowerCase()) < 0) return false;
    }
    return true;
  });
}

function frCount(opts) { return frFor(opts).length; }

/* ---- the notebook, rendered ------------------------------------------- */
/* the calendar day this timestamp falls on WHERE THE READER IS */
function frLocalDay(t) {
  const p = n => (n < 10 ? '0' : '') + n;
  return t.getFullYear() + '-' + p(t.getMonth() + 1) + '-' + p(t.getDate());
}

function frCtxLabel(c) {
  const f = FR_CTX.find(x => x[0] === c); return f ? f[1] : c;
}
function frSrcLabel(c) {
  const f = FR_SRC.find(x => x[0] === c); return f ? f[1] : '';
}

/* one entry: ruled, dated, and clear about what is mine and what is frozen */
function frEntry(n, compact) {
  /* shown in the reader's own time, for the same reason */
  const _t = new Date(n.created);
  const when = isFinite(_t)
    ? frLocalDay(_t) + ' ' + String(_t.getHours()).padStart(2, '0') + ':' +
      String(_t.getMinutes()).padStart(2, '0')
    : String(n.created || '').slice(0, 16).replace('T', ' ');
  const crest = (n.teams || []).slice(0, 3)
    .map(t => logo(t) || '').join('');
  return '<article class="fr-entry" data-fr="' + esc(n.id) + '">' +
    '<div class="fr-meta">' +
      '<span class="fr-ctx ' + esc(n.ctx) + '">' + esc(frCtxLabel(n.ctx)) +
      '</span>' +
      '<time>' + esc(when) + '</time>' +
      (n.src ? '<span class="fr-src">' + esc(frSrcLabel(n.src)) + '</span>' : '') +
      (compact ? '' : '<button type="button" class="fr-del" data-frdel="' +
        esc(n.id) + '" title="Delete this note">&#10005;</button>') +
    '</div>' +
    (n.title ? '<h4>' + esc(n.title) + '</h4>' : '') +
    /* ⚠ WHAT CODY WROTE IS MARKED AS WHAT CODY WROTE. The body is his
       observation; the chips beside it are hub values frozen at a stated
       moment. Mixing the two would turn an opinion into a citation. */
    (n.body ? '<p class="fr-body">' + esc(n.body) + '</p>' : '') +
    ((n.teams || []).length || (n.players || []).length
      ? '<div class="fr-tags">' + crest +
        (n.teams || []).map(t => '<span class="fr-tag">' + esc(t) + '</span>').join('') +
        (n.players || []).map(t => '<span class="fr-tag pl">' + esc(t) + '</span>').join('') +
        '</div>'
      : '') +
    ((n.facts || []).length
      ? '<div class="fr-facts"><i>Frozen from the hub</i>' +
        n.facts.map(f => '<span class="fr-chip"><b>' + esc(f.k) + '</b>' +
          esc(f.v) + '<em>' + esc(String(f.at || '').slice(0, 10)) + '</em></span>')
          .join('') + '</div>'
      : '') +
    (n.url
      ? '<div class="fr-link"><a href="' + esc(n.url) + '" target="_blank" ' +
        'rel="noopener noreferrer">source link</a>' +
        '<span>the page is never fetched or copied &mdash; the takeaway above ' +
        'is yours</span></div>'
      : '') +
    (n.gid ? '<a class="fr-open" href="' + matchRoute(n.gid, 'scores') +
             '">open the match</a>' : '') +
    '</article>';
}

/* the capture form -- three contexts, optional source, optional frozen facts */
function frForm(pre) {
  const p = pre || {};
  const opt = (arr, sel) => arr.map(x =>
    '<option value="' + x[0] + '"' + (x[0] === sel ? ' selected' : '') + '>' +
    x[1] + '</option>').join('');
  return '<form class="fr-form" id="frform">' +
    '<div class="fr-row">' +
      '<label>When<select id="frctx">' + opt(FR_CTX, p.ctx || 'post') +
      '</select></label>' +
      '<label>Source<select id="frsrc"><option value="">&mdash;</option>' +
      opt(FR_SRC, p.src || '') + '</select></label>' +
    '</div>' +
    '<label class="fr-full">Title<input type="text" id="frtitle" ' +
      'maxlength="200" placeholder="What you want to remember"></label>' +
    /* ⚠ NOT `frbody` -- THAT IS THE NOTES LIST. Naming the textarea and the
       list the same thing meant getElementById returned the TEXTAREA (it comes
       first in the DOM), so every render wrote the notebook into the form
       field: innerHTML 905 characters, zero child elements, no visible notes.
       Same shape as the `sbody` collision that made the just-finished band
       query the schedule tbody. The name inventory cannot catch this one --
       it compares against names that already exist, not against the two I add
       in the same change. */
    '<label class="fr-full">Your note<textarea id="frnote" rows="4" ' +
      'placeholder="Your own words. Nothing here is published or read by the ' +
      'model."></textarea></label>' +
    '<label class="fr-full">Link (optional)<input type="url" id="frurl" ' +
      'placeholder="https://&hellip; — stored as a link only"></label>' +
    '<div class="fr-row">' +
      '<label>Teams<input type="text" id="frteams" list="bwlist-teams" ' +
      'value="' + esc((p.teams || []).join(', ')) + '" ' +
      'placeholder="comma separated"></label>' +
      '<label>Players<input type="text" id="frplayers" ' +
      'value="' + esc((p.players || []).join(', ')) + '" ' +
      'placeholder="comma separated"></label>' +
    '</div>' +
    (p.gid ? '<input type="hidden" id="frgid" value="' + esc(p.gid) + '">' : '') +
    '<div class="fr-actions">' +
      '<button type="submit" class="fr-btn primary">Save note</button>' +
      (p.freeze
        ? '<label class="fr-freeze"><input type="checkbox" id="frfreeze" checked>' +
          'Attach current hub values, stamped now</label>' : '') +
      '<span class="fr-state" id="frstate"></span>' +
    '</div></form>';
}


/* ---- the Film Room view ------------------------------------------------ */
let FR_FILTER = {};

function frRender() {
  const host = document.getElementById('frbody');
  if (!host) return;
  frLoad();
  const rows = frFor(FR_FILTER);
  const cnt = document.getElementById('frcount');
  if (cnt) cnt.textContent = rows.length + (rows.length === 1 ? ' note' : ' notes');

  /* ⚠ TWO DIFFERENT EMPTY STATES, AND THEY ARE NOT THE SAME PROBLEM. An empty
     notebook is a beginning; a blocked one is a browser setting that will lose
     work. Showing the friendly copy for the second would be a lie. */
  if (!FR_OK) {
    /* one literal: a sentence split across a concatenation never appears
       contiguously in the built page, so a guard cannot find it */
    host.innerHTML = '<div class="vx-empty"><h4>This browser is not letting the page store anything</h4>' +
      '<p>Private windows and blocked site data ' +
      'both do this. The notebook still works for this session, but nothing ' +
      'will be here when you come back. Nothing is sent anywhere either way.' +
      '</p></div>';
    return;
  }
  if (!FR.length) {
    host.innerHTML = '<div class="vx-empty"><h4>Your notebook is empty</h4>' +
      '<p>Add a note from a team page, a player, a match, or from here. Notes ' +
      'stay on this device: they are not published, not read by any rating, ' +
      'and never posted anywhere.</p></div>';
    return;
  }
  if (!rows.length) {
    host.innerHTML = '<p class="emptylane">No note matches these filters.</p>';
    return;
  }
  /* grouped by day, newest first -- a notebook reads by date */
  /* ⚠ GROUP BY THE LOCAL DAY, NOT THE UTC SLICE. `created` is an ISO string
     in UTC, so a note written at 7pm Pacific carries tomorrow's UTC date --
     and the notebook filed it under a heading reading "Tomorrow". A notebook
     is read by the day the person was watching, which is their day. */
  const byDay = {};
  rows.forEach(n => {
    const t = new Date(n.created);
    const d = isFinite(t) ? frLocalDay(t) : String(n.created || '').slice(0, 10);
    (byDay[d] = byDay[d] || []).push(n);
  });
  host.innerHTML = Object.keys(byDay).sort().reverse().map(d =>
    '<div class="fr-day"><div class="vx-label"><b>' + esc(dayLabel(d)) +
    '</b></div>' + byDay[d].map(n => frEntry(n)).join('') + '</div>').join('');
}

function frWire() {
  const host = document.getElementById('v-film');
  if (!host || host.dataset.wired) return;
  host.dataset.wired = '1';

  const newBox = document.getElementById('frnew');
  if (newBox) newBox.innerHTML = frForm({});

  host.addEventListener('submit', e => {
    const f = e.target.closest('#frform');
    if (!f) return;
    e.preventDefault();
    const val = id => (document.getElementById(id) || {}).value || '';
    const list = id => val(id).split(',').map(x => x.trim()).filter(Boolean);
    const teams = list('frteams');
    const gid = val('frgid');
    let facts = [];
    const fz = document.getElementById('frfreeze');
    if (fz && fz.checked) {
      if (gid) facts = frFreezeMatch(gid);
      else if (teams.length) facts = frFreezeTeam(teams[0]);
    }
    if (!val('frtitle') && !val('frnote')) {
      const st = document.getElementById('frstate');
      if (st) st.textContent = 'A note needs a title or a body.';
      return;
    }
    frAdd({ ctx: val('frctx'), src: val('frsrc'), title: val('frtitle'),
            body: val('frnote'), url: val('frurl'), teams: teams,
            players: list('frplayers'), gid: gid, facts: facts });
    const st = document.getElementById('frstate');
    if (st) st.textContent = FR_OK ? 'Saved on this device.'
                                   : 'Kept for this session only.';
    f.reset();
    frRender();
    frSyncCounts();
  });

  host.addEventListener('click', e => {
    const del = e.target.closest('[data-frdel]');
    if (del) {
      frRemove(del.dataset.frdel);
      frRender(); frSyncCounts();
    }
  });

  const dl = document.getElementById('frexdl');
  if (dl) dl.addEventListener('click', () => frExport('download'));
  const cp = document.getElementById('frexcopy');
  if (cp) cp.addEventListener('click', () => frExport('copy'));

  /* ⚠ THE FILE IS READ WITH FileReader, LOCALLY. No upload, no fetch, no
     form: the bytes never leave the machine. A read failure says so. */
  const fi = document.getElementById('frfile');
  if (fi) fi.addEventListener('change', () => {
    const f = fi.files && fi.files[0];
    if (!f) return;
    if (f.size > FR_MAX_BYTES) {
      frImpSay('That file is too large to be a notebook.', 'warn');
      fi.value = ''; return;
    }
    const rd = new FileReader();
    rd.onerror = () => frImpSay('That file could not be read.', 'warn');
    rd.onload = () => { frPreview(String(rd.result || '')); fi.value = ''; };
    try { rd.readAsText(f); }
    catch (e) { frImpSay('That file could not be read.', 'warn'); }
  });
  const pb = document.getElementById('frpaste');
  if (pb) pb.addEventListener('click', () => {
    const box = document.getElementById('frpastebox');
    frPreview(box ? box.value : '');
  });

  host.addEventListener('click', e => {
    if (e.target.closest('#frdoadd')) { frApply('add'); return; }
    if (e.target.closest('#frdorepl')) {
      /* ⚠ THE DESTRUCTIVE PATH ASKS, AND NAMES THE NUMBER. */
      const n = FR_PENDING ? FR_PENDING.cls.localCount : 0;
      if (window.confirm('Replace your whole Film Room?\n\n' + n +
            ' note' + (n === 1 ? '' : 's') + ' on this device will be deleted ' +
            'and replaced by the file. This cannot be undone after you close ' +
            'the tab.')) {
        frApply('replace');
      }
      return;
    }
    if (e.target.closest('#frcancel')) {
      FR_PENDING = null;
      const pv = document.getElementById('frprev');
      if (pv) { pv.hidden = true; pv.innerHTML = ''; }
      frImpSay('Cancelled. Nothing changed.', '');
      return;
    }
    if (e.target.closest('#frundo')) { frUndo(); }
  });

  ['frq', 'frfctx', 'frfsrc'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', () => {
      FR_FILTER = { q: (document.getElementById('frq') || {}).value || '',
                    ctx: (document.getElementById('frfctx') || {}).value || '',
                    src: (document.getElementById('frfsrc') || {}).value || '' };
      frRender();
    });
  });
  frRender();
}

/* ⚠ A COUNT, NOT A WALL. A team page or a match says how many notes exist and
   links to them; it does not print them. The page belongs to the data, and the
   notebook belongs to the notebook. */
function frSyncCounts() {
  document.querySelectorAll('[data-frcount]').forEach(el => {
    const key = el.dataset.frcount;
    const kind = el.dataset.frkind || 'team';
    const o = {};
    o[kind] = key;
    const n = frCount(o);
    el.textContent = n ? (n + (n === 1 ? ' note' : ' notes')) : 'no notes yet';
    el.classList.toggle('has', !!n);
  });
}


/* ⚠ AN ENTRY POINT IS A COUNT AND A LINK, NOT A PANEL. A team page belongs to
   the data; the notebook belongs to the notebook. */
function frLink(kind, key) {
  return '<a class="fr-count" href="' + routeFor('film') + '" ' +
    'data-frcount="' + esc(key) + '" data-frkind="' + esc(kind) + '">' +
    'no notes yet</a>';
}

/* Beside the My Board control that already marks the same objects. */
function frInject() {
  /* ⚠ ANCHOR ON THE CONTROL, NOT ON A WRAPPER. The first version looked for
     `.mbslot`, which only wraps the ROSTER path -- the team header's My Board
     button has an unclassed parent, so the busiest entry point got nothing.
     Every My Board control is a team the notebook can be filtered to, wherever
     it sits. */
  document.querySelectorAll('[data-mb]').forEach(btn => {
    const host = btn.parentNode;
    if (!host || host.querySelector('.fr-count')) return;
    const nm = btn.dataset.mb;
    if (nm) btn.insertAdjacentHTML('afterend', ' ' + frLink('team', nm));
  });
  document.querySelectorAll('#bwqueue .bwcase').forEach(c => {
    if (c.querySelector('.fr-count')) return;
    const nm = ((c.querySelector('.bwcn') || {}).textContent || '').trim();
    if (nm) c.insertAdjacentHTML('beforeend', ' ' + frLink('team', nm));
  });
  frSyncCounts();
}


/* ---- export: this device, and nowhere else ----------------------------- */
/* ⚠ THERE IS NO NETWORK PATH HERE, AND THERE MUST NOT BE. Export produces a
   string from data already in this browser and hands it to the browser. It
   does not POST, it does not fetch, it does not touch git, and it names no
   host. The only two destinations are a local file and the clipboard.

   ⚠ AND A DOWNLOAD THAT SILENTLY DOES NOTHING IS THE FAILURE MODE TO PLAN
   FOR. A page-initiated download can be refused by a sandbox or a policy with
   no error and no event -- the click simply achieves nothing. So the flow is:
   try the download, then VERIFY NOTHING ABOUT IT (because nothing can be
   verified), and always offer the clipboard beside it. If both routes are
   unavailable the JSON is put on screen, selected, and the reader is told to
   copy it by hand. Every outcome is stated. */

const FR_FORMAT = 'wvb.filmroom';
const FR_VERSION = 1;

function frExportDoc() {
  frLoad();
  return {
    format: FR_FORMAT,
    version: FR_VERSION,
    exported: new Date().toISOString(),
    count: FR.length,
    /* ⚠ THE WHOLE NOTE, FIELD FOR FIELD. An export that quietly dropped a
       field would be a backup that loses work without saying so. */
    notes: FR.map(n => ({
      id: n.id, created: n.created, ctx: n.ctx, title: n.title, body: n.body,
      teams: n.teams || [], players: n.players || [], gid: n.gid || '',
      src: n.src || '', url: n.url || '', facts: n.facts || []
    }))
  };
}

function frExportText() {
  return JSON.stringify(frExportDoc(), null, 2);
}

function frExportName() {
  const t = new Date();
  const p = n => (n < 10 ? '0' : '') + n;
  return 'filmroom-' + t.getFullYear() + '-' + p(t.getMonth() + 1) + '-' +
         p(t.getDate()) + '.json';
}

function frSay(msg, kind) {
  const el = document.getElementById('frexstate');
  if (!el) return;
  el.textContent = msg;
  el.className = 'fr-state' + (kind ? ' ' + kind : '');
}

/* Put the JSON on screen, selected, as the last honest resort. */
function frShowRaw(text, why) {
  const host = document.getElementById('frout');
  if (!host) return;
  host.hidden = false;
  host.innerHTML = '<p class="fr-rawwhy">' + esc(why) + ' The notebook is ' +
    'below \u2014 select all and copy it wherever you want it.</p>' +
    '<textarea class="fr-raw" id="frraw" rows="8" readonly></textarea>';
  const ta = document.getElementById('frraw');
  if (ta) { ta.value = text; ta.focus(); ta.select(); }
}

function frCopy(text) {
  /* modern API first; it is the one that can be denied */
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(
        () => true, () => frCopyLegacy(text));
    }
  } catch (e) { /* fall through */ }
  return Promise.resolve(frCopyLegacy(text));
}

function frCopyLegacy(text) {
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand && document.execCommand('copy');
    document.body.removeChild(ta);
    return !!ok;
  } catch (e) { return false; }
}

function frDownload(text, name) {
  /* ⚠ RETURNS WHETHER THE ATTEMPT WAS MADE, NOT WHETHER IT LANDED. The
     browser gives no signal either way, and claiming success we cannot see
     would be exactly the kind of confident wrong statement this project
     refuses elsewhere. The wording downstream says "started", not "saved". */
  try {
    if (typeof Blob === 'undefined' || !window.URL || !URL.createObjectURL) {
      return false;
    }
    const a = document.createElement('a');
    if (!('download' in a)) return false;
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    a.href = url;
    a.download = name;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      try { document.body.removeChild(a); URL.revokeObjectURL(url); }
      catch (e) { /* already gone */ }
    }, 0);
    return true;
  } catch (e) { return false; }
}

function frExport(mode) {
  frLoad();
  if (!FR.length) {
    frSay('There is nothing to export yet.', 'warn');
    return;
  }
  const text = frExportText();
  const out = document.getElementById('frout');
  if (out) { out.hidden = true; out.innerHTML = ''; }

  if (mode !== 'copy') {
    if (frDownload(text, frExportName())) {
      frSay('Download started \u2014 ' + frExportName() + '. If your browser ' +
            'blocked it, use Copy instead.', 'good');
      return;
    }
    frSay('This browser will not let the page save a file. Trying the ' +
          'clipboard\u2026');
  }
  Promise.resolve(frCopy(text)).then(ok => {
    if (ok) {
      frSay('Copied to the clipboard \u2014 ' + FR.length +
            (FR.length === 1 ? ' note' : ' notes') + ', as JSON.', 'good');
    } else {
      /* ⚠ SAY WHAT WAS ACTUALLY TRIED. Pressing Copy attempts the clipboard
         and nothing else, so reporting that "neither saving nor copying" is
         available names a failure that never happened. The download path DOES
         try both, and says so. */
      const tried = (mode === 'copy')
        ? 'The clipboard is not available in this browser.'
        : 'Neither saving a file nor the clipboard is available in this browser.';
      frSay(tried, 'warn');
      frShowRaw(text, tried);
    }
  });
}


/* ---- import: validate everything, write nothing until told --------------- */
/* ⚠ THE ORDER MATTERS AND IS THE WHOLE SAFETY MODEL:
       parse -> validate every note -> classify against what is here now ->
       SHOW a preview -> wait for an explicit choice -> back up -> write.
   Nothing touches localStorage before the confirmation, and the destructive
   option is a separate button that names how many notes it will destroy.

   ⚠ AN IMPORTED FILE IS UNTRUSTED DATA. Its text and its URLs are somebody
   else's bytes even when that somebody is Cody last month. Everything is
   rendered through esc() as text; nothing from a file is ever inserted as
   markup or evaluated. */

const FR_BAK = 'wvb.filmroom.backup.v1';
const FR_MAX_BYTES = 2 * 1024 * 1024;   /* a notebook is text; 2 MB is generous */
const FR_MAX_NOTES = 5000;
const FR_VERSIONS = [1];
let FR_PENDING = null;                  /* the validated import, awaiting a choice */
let FR_UNDO = null;                     /* the previous notebook, this session */

function frIsStr(v) { return typeof v === 'string'; }
function frIsArr(v) { return Array.isArray(v); }

/* One note, fully checked. Returns an error string, or '' when it is sound. */
function frBadNote(n, i) {
  if (!n || typeof n !== 'object' || frIsArr(n)) return 'note ' + (i + 1) + ' is not a note';
  if (!frIsStr(n.id) || !n.id.trim()) return 'note ' + (i + 1) + ' has no id';
  if (!frIsStr(n.created) || isNaN(new Date(n.created).getTime())) {
    return 'note ' + (i + 1) + ' has no usable date';
  }
  if (!frIsStr(n.ctx) || !FR_CTX.some(c => c[0] === n.ctx)) {
    return 'note ' + (i + 1) + ' has an unknown moment';
  }
  if (!frIsStr(n.title) || !frIsStr(n.body)) return 'note ' + (i + 1) + ' has bad text';
  if (!n.title.trim() && !n.body.trim()) return 'note ' + (i + 1) + ' is empty';
  if (!frIsArr(n.teams) || !n.teams.every(frIsStr)) return 'note ' + (i + 1) + ' has bad teams';
  if (!frIsArr(n.players) || !n.players.every(frIsStr)) return 'note ' + (i + 1) + ' has bad players';
  if (!frIsStr(n.gid)) return 'note ' + (i + 1) + ' has a bad match reference';
  if (n.src && (!frIsStr(n.src) || !FR_SRC.some(c => c[0] === n.src))) {
    return 'note ' + (i + 1) + ' has an unknown source type';
  }
  if (!frIsStr(n.url)) return 'note ' + (i + 1) + ' has a bad link';
  /* ⚠ A LINK IS ONLY EVER http(s), AND IT IS NEVER FETCHED. Refusing
     javascript: and data: here means a stored link can never become code even
     if something later renders it as an anchor. */
  if (n.url && !/^https?:\/\//i.test(n.url)) {
    return 'note ' + (i + 1) + ' has a link that is not a web address';
  }
  if (!frIsArr(n.facts)) return 'note ' + (i + 1) + ' has bad frozen facts';
  for (const f of n.facts) {
    if (!f || typeof f !== 'object' || !frIsStr(f.k) || !frIsStr(f.v)) {
      return 'note ' + (i + 1) + ' has a broken frozen fact';
    }
  }
  return '';
}

/* Keep only the fields we know. Anything else in the file is discarded rather
   than stored -- an import must not smuggle new keys into the notebook. */
function frClean(n) {
  return {
    id: n.id, created: n.created, ctx: n.ctx,
    title: String(n.title).slice(0, 200), body: String(n.body).slice(0, 4000),
    teams: n.teams.slice(0, 8), players: n.players.slice(0, 8),
    gid: n.gid, src: n.src || '', url: n.url || '',
    facts: n.facts.map(f => ({ k: String(f.k).slice(0, 40),
                               v: String(f.v).slice(0, 80),
                               at: frIsStr(f.at) ? f.at : '' }))
  };
}

function frValidate(text) {
  const out = { ok: false, why: '', meta: null, valid: [], bad: [] };
  if (!frIsStr(text) || !text.trim()) {
    out.why = 'There was nothing to read.'; return out;
  }
  if (text.length > FR_MAX_BYTES) {
    out.why = 'That file is much larger than a notebook should be, so it has ' +
              'not been opened.';
    return out;
  }
  let doc;
  try { doc = JSON.parse(text); }
  catch (e) {
    out.why = 'That is not readable as JSON. If you pasted it, check nothing ' +
              'was cut off.';
    return out;
  }
  if (!doc || typeof doc !== 'object' || frIsArr(doc)) {
    out.why = 'That file is not a Film Room export.'; return out;
  }
  if (doc.format !== FR_FORMAT) {
    out.why = 'That file is not a Film Room export.'; return out;
  }
  if (FR_VERSIONS.indexOf(doc.version) < 0) {
    out.why = 'That export was written by a different version of the ' +
              'notebook (' + esc(String(doc.version)) + ') and cannot be read here.';
    return out;
  }
  if (!frIsArr(doc.notes)) {
    out.why = 'That export has no notes in it.'; return out;
  }
  if (doc.notes.length > FR_MAX_NOTES) {
    out.why = 'That export contains more notes than this can handle safely.';
    return out;
  }
  const seen = {};
  doc.notes.forEach((n, i) => {
    const why = frBadNote(n, i);
    if (why) { out.bad.push(why); return; }
    if (seen[n.id]) { out.bad.push('note ' + (i + 1) + ' repeats an id'); return; }
    seen[n.id] = 1;
    out.valid.push(frClean(n));
  });
  out.meta = { exported: frIsStr(doc.exported) ? doc.exported : '',
               count: doc.notes.length };
  out.ok = out.valid.length > 0;
  if (!out.ok && !out.why) {
    out.why = 'Nothing in that file could be read as a note.';
  }
  return out;
}

/* What would happen, without doing any of it. */
function frClassify(valid) {
  frLoad();
  const mine = {};
  FR.forEach(n => { mine[n.id] = n; });
  const fresh = [], dupe = [], clash = [];
  const sig = n => JSON.stringify([n.ctx, n.title, n.body, n.teams, n.players,
                                   n.gid, n.src, n.url, n.facts]);
  valid.forEach(n => {
    const here = mine[n.id];
    if (!here) fresh.push(n);
    else if (sig(here) === sig(n)) dupe.push(n);
    else clash.push(n);
  });
  return { fresh: fresh, dupe: dupe, clash: clash, localCount: FR.length };
}


/* ---- preview, then a choice -------------------------------------------- */
function frImpSay(msg, kind) {
  const el = document.getElementById('frimpstate');
  if (!el) return;
  el.textContent = msg;
  el.className = 'fr-state' + (kind ? ' ' + kind : '');
}

function frPreview(text) {
  const host = document.getElementById('frprev');
  if (!host) return;
  const v = frValidate(text);
  FR_PENDING = null;
  if (!v.ok) {
    host.hidden = false;
    host.innerHTML = '<div class="fr-prevbad"><b>Nothing was imported.</b>' +
      '<span>' + esc(v.why) + '</span>' +
      (v.bad.length
        ? '<ul>' + v.bad.slice(0, 6).map(b => '<li>' + esc(b) + '</li>').join('') +
          (v.bad.length > 6 ? '<li>and ' + (v.bad.length - 6) + ' more</li>' : '') +
          '</ul>'
        : '') + '</div>';
    frImpSay('That file was not imported.', 'warn');
    return;
  }
  const c = frClassify(v.valid);
  FR_PENDING = { valid: v.valid, cls: c, meta: v.meta, bad: v.bad };

  /* ⚠ A SAMPLE, NOT THE WHOLE FILE. Five titles is enough to recognise the
     notebook; printing all of them turns a confirmation into a wall. */
  const sample = list => list.slice(0, 5).map(n =>
    '<li><i>' + esc(frCtxLabel(n.ctx)) + '</i>' +
    esc(n.title || n.body.slice(0, 60)) + '</li>').join('') +
    (list.length > 5 ? '<li class="more">and ' + (list.length - 5) +
      ' more</li>' : '');

  host.hidden = false;
  host.innerHTML =
    '<div class="fr-prevhd"><b>Before importing</b>' +
      '<span>' + (v.meta.exported
        ? 'exported ' + esc(String(v.meta.exported).slice(0, 10)) : 'no date') +
      ' &middot; ' + v.meta.count +
      (v.meta.count === 1 ? ' note in the file' : ' notes in the file') +
      '</span></div>' +
    '<div class="fr-prevnums">' +
      '<div><i>Will be added</i><b class="fr-ok">' + c.fresh.length + '</b></div>' +
      '<div><i>Already here</i><b>' + c.dupe.length + '</b></div>' +
      '<div><i>Same id, different note</i><b class="fr-warn">' + c.clash.length +
        '</b></div>' +
      '<div><i>Unreadable</i><b' + (v.bad.length ? ' class="fr-warn"' : '') + '>' +
        v.bad.length + '</b></div>' +
    '</div>' +
    (c.fresh.length
      ? '<div class="fr-prevlist"><i>To be added</i><ul>' + sample(c.fresh) +
        '</ul></div>' : '') +
    (c.clash.length
      ? '<div class="fr-prevlist"><i>Skipped &mdash; an id you already have, ' +
        'with different content</i><ul>' + sample(c.clash) + '</ul></div>' : '') +
    '<div class="fr-prevacts">' +
      '<button type="button" class="fr-btn primary" id="frdoadd">Add ' +
        c.fresh.length + ' new note' + (c.fresh.length === 1 ? '' : 's') +
        '</button>' +
      '<button type="button" class="fr-btn" id="frcancel">Cancel</button>' +
      /* ⚠ THE DESTRUCTIVE ONE IS SEPARATE, LAST, AND NAMES THE COST. */
      '<button type="button" class="fr-btn fr-danger" id="frdorepl">' +
        'Replace my whole notebook (' + c.localCount + ' note' +
        (c.localCount === 1 ? '' : 's') + ' deleted)</button>' +
    '</div>';
  frImpSay('Nothing has changed yet.', '');
}

/* ⚠ ONE BACKUP BEFORE ANY WRITE, AND AN UNDO FOR THIS SESSION. The backup is
   another local key; it goes nowhere. Undo is held in memory so it dies with
   the tab -- a long-lived undo would be a second copy of the notebook nobody
   asked for. */
function frBackup() {
  try {
    window.localStorage.setItem(FR_BAK, JSON.stringify(
      { at: new Date().toISOString(), notes: FR }));
    return true;
  } catch (e) { return false; }
}

function frApply(mode) {
  if (!FR_PENDING) return;
  frLoad();
  FR_UNDO = FR.slice();
  const backed = frBackup();
  const c = FR_PENDING.cls;
  let msg;
  if (mode === 'replace') {
    FR = FR_PENDING.valid.slice();
    msg = 'Replaced. ' + FR.length + ' note' + (FR.length === 1 ? '' : 's') +
          ' now, ' + c.localCount + ' removed.';
  } else {
    c.fresh.forEach(n => FR.unshift(n));
    msg = 'Added ' + c.fresh.length + '. Skipped ' + c.dupe.length +
          ' already here and ' + c.clash.length + ' with a clashing id.';
  }
  const ok = frSave();
  frImpSay(msg + (ok ? '' : ' (this browser will not store it, so it lasts ' +
                          'for this session only)') +
           (backed ? '' : ' No backup could be written.'),
           ok ? 'good' : 'warn');
  FR_PENDING = null;
  const host = document.getElementById('frprev');
  if (host) {
    host.innerHTML = '<div class="fr-prevacts"><button type="button" ' +
      'class="fr-btn" id="frundo">Undo this import</button></div>';
  }
  frRender();
  frSyncCounts();
}

function frUndo() {
  if (!FR_UNDO) return;
  FR = FR_UNDO.slice();
  FR_UNDO = null;
  frSave();
  frImpSay('Undone. Your notebook is back to ' + FR.length + ' note' +
           (FR.length === 1 ? '' : 's') + '.', 'good');
  const host = document.getElementById('frprev');
  if (host) { host.hidden = true; host.innerHTML = ''; }
  frRender();
  frSyncCounts();
}

/* FILMROOM-JS-END */

/* MYBOARD-JS-BEGIN */
/* ══ MY BOARD ═════════════════════════════════════════════════════════════
   Cody's private watchlist. It lives in ONE place -- localStorage in his own
   browser -- and nowhere else: no file, no endpoint, no backup, no payload, no
   model input. The whole feature is inside this sentinel so the published
   build carries none of it, not even the storage key.

   ⚠ NOTHING IS EVER ADDED FOR HIM. Not a highly ranked team, not a team from
   his ballot, not a team he looked at twice. An empty board stays empty until
   he presses a button, because a watchlist that fills itself is a
   recommendation wearing a preference's clothes. */
const MB_KEY = 'wvb.myboard.v1';
let MB_OK = true;            // does this browser actually give us storage?
let MB = [];

function mbLoad() {
  try {
    const raw = window.localStorage.getItem(MB_KEY);
    MB = raw ? (JSON.parse(raw) || []) : [];
    if (!Array.isArray(MB)) MB = [];
    MB_OK = true;
    /* ⚠ TEAMS IS NOT READY YET. `const TEAMS` is declared near the END of this
       script, so touching it here throws "Cannot access 'TEAMS' before
       initialization" -- and because this block is a try/catch, that throw was
       being SWALLOWED and reported as "this browser is not letting the page
       store anything". A real storage failure and a load-order mistake would
       have looked identical. Names are checked at render time instead, when
       TEAMS exists. */
  } catch (e) {
    /* ⚠ FAIL SOFT AND SAY SO. Private mode, blocked site data or a full quota
       all throw here. The board simply does not persist; the rest of the hub
       is untouched and the panel explains itself rather than looking broken. */
    MB = [];
    MB_OK = false;
  }
}
function mbSave() {
  try {
    window.localStorage.setItem(MB_KEY, JSON.stringify(MB));
    MB_OK = true;
  } catch (e) { MB_OK = false; }
}
function mbHas(team) { return MB.indexOf(team) >= 0; }
/* safe before TEAMS exists: a name is "known" only once the payload is there */
function mbKnown(team) {
  try { return !!(TEAMS && TEAMS[team]); } catch (e) { return false; }
}
/* removing works for ANY saved name, including one this build no longer
   knows -- otherwise an unavailable team could never be taken off the board */
function mbRemove(team) {
  const i = MB.indexOf(team);
  if (i < 0) return;
  MB.splice(i, 1);
  mbSave();
  mbRenderAll();
}
function mbToggle(team) {
  if (!mbKnown(team)) return;
  const i = MB.indexOf(team);
  if (i >= 0) MB.splice(i, 1); else MB.push(team);
  mbSave();
  mbRenderAll();
}
function mbClear() {
  if (!MB.length) return;
  if (!window.confirm('Clear My Board? This removes all ' + MB.length +
      ' team' + (MB.length === 1 ? '' : 's') + ' you have added. ' +
      'Nothing else is affected.')) return;
  MB = [];
  mbSave();
  mbRenderAll();
}

/* the control, used wherever a team is already named by its own markup */
function mbControl(team, size) {
  if (!mbKnown(team)) return '';
  const on = mbHas(team);
  return '<button type="button" class="mbbtn" data-mb="' + esc(team) + '"' +
    ' aria-pressed="' + (on ? 'true' : 'false') + '"' +
    ' aria-label="' + (on ? 'Remove ' : 'Add ') + esc(team) +
    (on ? ' from' : ' to') + ' My Board">' +
    (on ? 'On My Board' : '+ My Board') + '</button>';
}

/* ── THE PANEL ────────────────────────────────────────────────────────────
   Watched teams by TRUE state, using the same matchState() the general board
   uses. A team with nothing on is said to have nothing on -- never a
   fabricated scoreline and never a placeholder standing in for a time. */
function mbFindMatch(team) {
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  const mine = DESK.filter(m => m.a === team || m.h === team);
  const todays = mine.filter(m => m.d === today);
  for (let i = 0; i < todays.length; i++) {
    if (matchState(todays[i], LIVE_BY_ID[todays[i].gid]) === 'live') {
      return { m: todays[i], st: 'live' };
    }
  }
  for (let i = 0; i < todays.length; i++) {
    if (matchState(todays[i], LIVE_BY_ID[todays[i].gid]) === 'final') {
      return { m: todays[i], st: 'final' };
    }
  }
  const ahead = mine.filter(m => m.d >= today)
    .sort((a, b) => (a.d < b.d ? -1 : a.d > b.d ? 1 : 0));
  if (ahead.length) return { m: ahead[0], st: 'upcoming' };
  return null;
}

function mbRow(team) {
  const hit = mbFindMatch(team);
  const t = TEAMS[team] || {};
  const ranks = [];
  if (t.rank) ranks.push('<span class="bwv pw">POWER #' + t.rank + '</span>');
  if (t.avca) ranks.push('<span class="bwv av">AVCA #' + t.avca + '</span>');
  const head = '<span class="mbteam">' + logo(team) + '<b>' + esc(team) +
    '</b></span>';
  if (!hit) {
    return '<button type="button" class="mbrow" data-mbteam="' + esc(team) + '">' +
      head + '<span class="mbwhat mbnone">No match in the current window.' +
      '</span><span class="mbwhen">' + ranks.join(' ') + '</span></button>';
  }
  const m = hit.m, live = LIVE_BY_ID[m.gid];
  const opp = m.a === team ? m.h : m.a;
  const where = m.site === 'neutral' ? 'neutral'
    : (m.h === team ? 'home' : 'away');
  const sc = matchScore(m, live);
  const mineIdx = m.a === team ? 0 : 1;
  let what;
  if (hit.st === 'live') {
    what = '<em>' + esc((live && live.period) || 'live') + '</em> v ' + esc(opp) +
      ' &middot; <span class="mbsc">' + sc[mineIdx] + '&ndash;' +
      sc[1 - mineIdx] + '</span>';
  } else if (hit.st === 'final') {
    const won = +sc[mineIdx] > +sc[1 - mineIdx];
    what = '<em>Final</em> ' + (won ? 'beat ' : 'lost to ') + esc(opp) +
      ' <span class="mbsc">' + sc[mineIdx] + '&ndash;' + sc[1 - mineIdx] +
      '</span>';
  } else {
    what = '<em>' + esc(m.dl || m.d) + '</em> ' +
      (where === 'neutral' ? 'v ' : where === 'home' ? 'v ' : 'at ') + esc(opp) +
      (m.t ? ' &middot; ' + esc(m.t) : '');
  }
  const tvl = (typeof TV !== 'undefined' && TV) ? (TV[m.gid] || null) : null;
  const meta = [where, tvl].filter(Boolean).map(esc).join(' &middot; ');
  return '<button type="button" class="mbrow" data-mbmatch="' + esc(m.gid) +
    '">' + head + '<span class="mbwhat">' + what + '</span>' +
    '<span class="mbwhen">' + (meta ? meta + '<br>' : '') + ranks.join(' ') +
    '</span></button>';
}

function mbRenderPanel() {
  const host = document.getElementById('mbpanel');
  if (!host) return;
  if (!MB.length) { host.hidden = true; host.innerHTML = ''; return; }
  const lanes = { live: [], final: [], upcoming: [], none: [], gone: [] };
  MB.slice().sort().forEach(n => {
    if (!mbKnown(n)) { lanes.gone.push(n); return; }
    const hit = mbFindMatch(n);
    lanes[hit ? hit.st : 'none'].push(n);
  });
  const lane = (key, label) => lanes[key].length
    ? '<div class="mblane"><i>' + label + '</i>' +
      lanes[key].map(mbRow).join('') + '</div>' : '';
  host.hidden = false;
  host.innerHTML =
    '<div class="mbhd"><b>My Board</b>' +
      '<span class="mbpriv">private</span>' +
      '<span class="mbn">' + MB.length + ' team' +
        (MB.length === 1 ? '' : 's') + ' you added</span>' +
      '<button type="button" class="mbbtn mbclear" id="mbclear">Clear My Board</button>' +
    '</div>' +
    lane('live', 'Live now') + lane('final', 'Just finished') +
    lane('upcoming', 'Coming up') +
    lane('none', 'No match in the current window') +
    (lanes.gone.length
      ? '<div class="mblane"><i>Not in the current directory</i>' +
        lanes.gone.map(n =>
          '<div class="mbrow mbgone"><span class="mbteam"><b>' + esc(n) +
          '</b></span><span class="mbwhat mbnone">This saved team is not in ' +
          'the current directory.</span>' +
          '<span class="mbwhen"><button type="button" class="mbbtn" ' +
          'data-mbdrop="' + esc(n) + '" aria-label="Remove ' + esc(n) +
          ' from My Board">Remove</button></span></div>').join('') +
        '</div>'
      : '') +
    (MB_OK ? '' : '<p class="mbwarn">This browser is not letting the page ' +
      'store anything, so My Board will empty when you reload. Everything ' +
      'else on the hub works normally.</p>');
}

/* ⚠ THE BUTTON IS INJECTED, NOT BAKED IN. The team panel and the ballot rows
   are SHARED markup that the public build also renders, so putting the control
   in their templates would ship it. Private code adds it after those views
   render, which keeps every trace of My Board inside this sentinel. */
function mbInject() {
  const th = document.querySelector('#teamcard .thead');
  if (th && !th.querySelector('[data-mb]')) {
    const nm = (th.querySelector('h2') || {}).textContent || '';
    if (nm && mbKnown(nm.trim())) {
      const holder = document.createElement('div');
      holder.style.marginTop = '10px';
      holder.innerHTML = mbControl(nm.trim());
      th.appendChild(holder);
    }
  }
  document.querySelectorAll('#deskdetail .ribbon .rbnm,' +
                            '#scoredetail .ribbon .rbnm').forEach(a => {
    const nm = (a.textContent || '').trim();
    if (!mbKnown(nm) || a.parentNode.querySelector('[data-mb]')) return;
    /* ⚠ THE RIBBON IS A FOUR-COLUMN GRID. An appended span became a fifth
       grid item squeezed to 12px, so the control was clipped inside its own
       box. It takes a row of its own instead. */
    const sp = document.createElement('span');
    sp.className = 'mbslot';
    sp.innerHTML = mbControl(nm);
    a.parentNode.appendChild(sp);
  });
  /* FILMROOM-HOOK-BEGIN */
  if (typeof frInject === 'function') frInject();
  /* FILMROOM-HOOK-END */
  /* inside the private ballot: review queue, comparison, and each slot */
  document.querySelectorAll('#bwqueue .bwcase').forEach(c => {
    if (c.querySelector('[data-mb]')) return;
    const nm = (c.querySelector('.bwcn') || {}).textContent || '';
    if (mbKnown(nm.trim())) c.insertAdjacentHTML('beforeend', mbControl(nm.trim()));
  });
  document.querySelectorAll('#bwteamcmp .bwcmptbl th.tm').forEach(th2 => {
    if (th2.querySelector('[data-mb]')) return;
    const nm = (th2.textContent || '').trim();
    if (mbKnown(nm)) th2.insertAdjacentHTML('beforeend', ' ' + mbControl(nm));
  });
  document.querySelectorAll('.bwrow[data-team]').forEach(r => {
    if (r.querySelector('[data-mb]')) return;
    const ctl = r.querySelector('.bwctl');
    if (ctl && mbKnown(r.dataset.team)) {
      ctl.insertAdjacentHTML('beforeend', mbControl(r.dataset.team));
    }
  });
}

/* ⚠ EVERY EXISTING CONTROL IS REFRESHED, NOT JUST NEW ONES. mbInject() adds a
   button only where there is none, so after a toggle the button that was
   pressed still read "+ My Board" while storage already held the team -- the
   control and the truth disagreed on screen. */
function mbSyncControls() {
  document.querySelectorAll('[data-mb]').forEach(b => {
    const on = mbHas(b.dataset.mb);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.setAttribute('aria-label', (on ? 'Remove ' : 'Add ') + b.dataset.mb +
      (on ? ' from' : ' to') + ' My Board');
    b.textContent = on ? 'On My Board' : '+ My Board';
  });
}

function mbRenderAll() {
  /* ⚠ AN UNKNOWN NAME IS NOT DELETED. It used to be silently filtered out
     here, so a school that was renamed or reclassified simply vanished from
     his board with nothing said -- a saved preference disappearing on its own.
     It stays, listed as unavailable, with a Remove button and nothing else. */
  mbRenderPanel();
  mbInject();
  mbSyncControls();
}

document.addEventListener('click', e => {
  const drop = e.target.closest && e.target.closest('[data-mbdrop]');
  if (drop) { e.preventDefault(); e.stopPropagation();
              mbRemove(drop.dataset.mbdrop); return; }
  const b = e.target.closest && e.target.closest('[data-mb]');
  if (b) { e.preventDefault(); e.stopPropagation(); mbToggle(b.dataset.mb); return; }
  if (e.target.closest && e.target.closest('#mbclear')) { mbClear(); return; }
  const row = e.target.closest && e.target.closest('.mbrow');
  if (row) {
    if (row.dataset.mbmatch) go('#/match-desk/' + encodeURIComponent(row.dataset.mbmatch));
    else if (row.dataset.mbteam) go(routeFor('teams', slug(row.dataset.mbteam)));
  }
});
addEventListener('hashchange', () => setTimeout(mbInject, 60));
mbLoad();
/* MYBOARD-JS-END */

/* ══ SHARED MATCH COMPONENTS ══════════════════════════════════════════════
   ⚠ ONE DEFINITION OF A MATCH HEADER AND A MATCH ROW, used by the Match Desk,
   the Scores ledger and the match detail. Three renderers for the same object
   is how a scoreline ends up phrased three ways and drifts (R4). */
const LEDGER = {{LEDGER_JSON}};

/* TRUE STATE, never a guess. `live` is the scoreboard feed; a match with a
   final result is final; everything else has not started. */
/* ⚠ THE STATE TABLE COMES FROM PYTHON (scripts/match_state.py). Labels, notes
   and what each state MAY display are defined once, server-side, and handed to
   the page. Writing the rules twice is how three renderers came to disagree
   about whether a match was live. */
const MSTATE = {{MSTATE_JSON}};

/* Is there a real set count here? ⚠ '' IS NOT 0 -- the scoreboard serves an
   empty string before first serve and Number('') is 0, which renders an
   unplayed match as 0-0. Measured; see docs/live_endpoint_audit.md. */
function mNum(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === 'string' && !v.trim()) return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

function mOver(live, m) {
  if (live && (/final|complete/i.test(live.state || '') ||
               /final|complete/i.test(live.period || ''))) return true;
  /* ⚠ THE THIRD OVER-SIGNAL: THE TALLY ITSELF. Seen live on 2026-08-28,
     FIU-Merrimack: the feed carried away_sets "3" while state was still
     "live" and period still "3RD SET" -- the inverse of the documented
     period-flips-first lag. A side with three sets has WON by rule (a match
     ends the moment a side reaches three), so the tape showed the impossible
     "LIVE - 3RD SET" beside a 3-0 tally for several minutes. Whichever field
     says it is over first is believed; this one is not even a feed field, it
     is the sport. */
  if (live && (mNum(live.away_sets) >= 3 || mNum(live.home_sets) >= 3)) {
    return true;
  }
  return !!(m && (m.final || mNum(m.as) !== null));
}

/* The six states, resolved the same way the server resolves them. `box` is
   whether a VERIFIED box score exists for this match on this page. */
/* ══ THE CONNECTOR ════════════════════════════════════════════════════════
   ⚠ "at" IS A CLAIM ABOUT WHERE A MATCH IS PLAYED, and until this phase the
   page printed it for anything that was not explicitly flagged neutral --
   including every fixture whose venue the feed had never published. That is
   how "Kentucky at Penn St." came to describe a match at Wrigley Field.

   at   only for a confirmed home/away site
   vs   only for a confirmed neutral floor
   v    for anything unconfirmed or in conflict -- a connector that joins two
        names and asserts nothing about the building. */
function connector(m) {
  if (m && m.conflict && m.conflict.length) return 'v';
  if (m && m.site === 'neutral') return 'vs';
  if (m && (m.site === 'home' || m.site === 'away')) return 'at';
  return 'v';
}

function matchState6(m, live, box) {
  if (mOver(live, m)) return box ? 'final_with_box' : 'final_box_pending';
  /* ⚠ TRUST THE SERVER'S VERDICT, ALL OF IT. This said it trusted state6 and
     then honoured exactly TWO of its five values; everything else fell through
     to `if (live) return 'live_score_only'` -- so merely APPEARING on today's
     scoreboard made a match live.
     Cody caught it on the season's first night: at 4:45pm Pacific, with first
     serve at 5:00 and 6:00, Florida at Nebraska and SMU at Penn St. both read
     LIVE. The feed had said `state:"pre"`, `state6:"upcoming"`, "Not started."
     for both. We were told the right answer and threw it away.
     The whole point of one resolved state model is that a renderer asks
     instead of deriving. Ask properly: any state the server names is the
     state, and the fall-through applies only when it named none. */
  if (live && live.state6 && MSTATE.caps && MSTATE.caps[live.state6]) {
    return live.state6;
  }
  if (live) return 'live_score_only';
  return 'upcoming';
}

/* Back-compat for the lanes and rows, which think in three buckets. */
function matchState(m, live) {
  const s6 = matchState6(m, live, false);
  if (s6 === 'upcoming') return 'upcoming';
  if (s6.indexOf('final') === 0) return 'final';
  return 'live';
}

function mCaps(state6) {
  return (MSTATE.caps && MSTATE.caps[state6]) || MSTATE.caps.unavailable;
}
/* ══ ONE SET, READ ONE WAY ════════════════════════════════════════════════
   ⚠ A SET IS AN ARRAY PAIR [away, home]. Not an object. Measured on both
   sources that produce one:
     live_server.py:228  sets.append([int(s.get("visit")), int(s.get("home"))])
     the crawled ledger  [[25,22],[19,25],[16,25],[25,23],[8,15]]
   and the match ribbon has always read x[0]/x[1] accordingly.

   ⚠ THE RALLY TAPE AND THE MATCH MOMENT READ `sv.a` / `sv.h` -- AN OBJECT
   SHAPE THAT NOTHING PRODUCES. Every real live match would have rendered five
   empty court dots instead of the score, on both of the surfaces built to show
   it, and nothing would have thrown.

   ⚠ AND HERE IS WHY IT SURVIVED TWO COMMITS OF TESTING: the only live data I
   ever had was a fixture I wrote myself, in the shape my own code expected. A
   fixture authored to match the code under test confirms exactly what it was
   built to confirm -- the same failure as a nickname map authored from the
   cases it adjudicates. It surfaced the moment the rehearsal put the tape and
   the ribbon side by side on one screen and they disagreed: 25-22 against
   "undefined-undefined".

   Returns [away, home] as numbers, or null when the set has not been played.
   '' IS NOT ZERO -- the feed serves an empty string for a score that does not
   exist yet, and '' coerces to 0. */
function setPair(v) {
  if (!v) return null;
  const a = Array.isArray(v) ? v[0] : undefined;
  const h = Array.isArray(v) ? v[1] : undefined;
  if (a === '' || h === '' || a === null || h === null ||
      a === undefined || h === undefined) return null;
  const na = Number(a), nh = Number(h);
  if (isNaN(na) || isNaN(nh)) return null;
  return [na, nh];
}

function matchSets(m, live) {
  if (live && live.sets && live.sets.length) return live.sets;
  if (m.final && m.final.sets) return m.final.sets;
  return m.sets || [];
}
function matchScore(m, live) {
  if (live) return [live.away_sets, live.home_sets];
  if (m.final) return [m.final.as, m.final.hs];
  if (m.as !== undefined && m.as !== null) return [m.as, m.hs];
  return [null, null];
}
function mAway(m) { return m.a; }
function mHome(m) { return m.h; }

/* THE RIBBON. The featured match, and the detail header -- the same bar. */
function ribbonHTML(m, live, why) {
  const st = matchState(m, live);
  const sc = matchScore(m, live);
  const sets = matchSets(m, live);
  const aw = (sc[0] !== null && sc[1] !== null) ? +sc[0] > +sc[1] : false;
  const hw = (sc[0] !== null && sc[1] !== null) ? +sc[1] > +sc[0] : false;
  const when = st === 'live'
      ? esc((live && live.period) || 'in progress')
      : esc((m.dl || m.d || '') + (m.t ? ' · ' + m.t : ''));
  const side = (name, rk, won, score) =>
    '<div class="rbside ' + (won ? 'won' : '') + '">' +
      '<span class="rbrk">' + rankHTML('avca', rk, true) + '</span>' +
      /* ⚠ THE CREST SLOT IS ALWAYS EMITTED, EVEN WHEN THERE IS NO CREST.
         `.rbside` is a FOUR-column grid and logo() returns an empty string for
         a team we hold no crest for -- so the row had three children, every
         cell shifted one column left, and the team name landed in the 34px
         crest track. Measured on Elizabeth City St.: the name wrapped to three
         lines at 91px tall and the score sat in the 1fr column beside it
         instead of at the right edge. This hits EVERY non-Division-I opponent,
         which is precisely the population we just spent a phase surfacing.
         An empty span keeps the column count right. */
      (logo(name) || '<span class="rbnologo"></span>') +
      '<a class="rbnm parentlink" href="' + routeFor('teams', slug(name)) + '">' +
        esc(name) + '</a>' +
      '<span class="rbsc">' + (score === null || score === undefined ? '&mdash;' : score) +
      '</span></div>';
  /* ⚠ THE REFERENCE TABLE IS THE MATCH-DETAIL STANDARD (Cody's broadcast
     screenshots + the design review: "the reference score graphic should
     become the match-detail standard"). Set numbers across the top, a crest
     per row, the points in order, sets-won ruled off at the right -- and on a
     live match the current column boxed, the same one live accent the
     scoreboard rows use. Replaces the old "Set 1 8-15" tile strip. */
  let ledger = '';
  if (sets.length) {
    const nS = sets.length;
    const isL = st === 'live';
    let head = '<tr><th></th>';
    for (let i = 0; i < nS; i++) {
      head += '<th' + (isL && i === nS - 1 ? ' class="cur ct"' : '') + '>' +
        (i + 1) + '</th>';
    }
    head += '<th class="dst" title="sets won">S</th></tr>';
    const rowOf = (name, idx, tally) => {
      let tr = '<tr><td class="dtm">' + logo(name) + '</td>';
      for (let i = 0; i < nS; i++) {
        const v = sets[i][idx], o = sets[i][1 - idx];
        const cur = isL && i === nS - 1;
        tr += '<td class="' +
          (cur ? 'cur ' + (idx === 0 ? 'ca' : 'ch') + (+v > +o ? ' up' : '')
               : (+v > +o ? 'w' : '')) + '">' + v + '</td>';
      }
      tr += '<td class="dst' + (!isL && +sc[idx] > +sc[1 - idx] ? ' w' : '') +
        '">' + (tally === null || tally === undefined ? '&mdash;' : tally) +
        '</td></tr>';
      return tr;
    };
    ledger = '<div class="dlswrap"><table class="dls">' + head +
      rowOf(mAway(m), 0, sc[0]) + rowOf(mHome(m), 1, sc[1]) +
      '</table></div>';
  }
  return '<div class="ribbon ' + st + (ledger ? ' hasdls' : '') + '">' +
    '<div class="rbtop"><span class="rbstate ' + st + '">' +
      (st === 'live' ? ICON_LIVE + ' Live' : st === 'final' ? 'Final' : 'Upcoming') +
      '</span><span class="rbwhen">' + when + '</span>' +
      (why ? '<span class="rbwhy">' + why + '</span>' : '') + '</div>' +
    side(mAway(m), m.ar, aw, sc[0]) + side(mHome(m), m.hr, hw, sc[1]) +
    ledger + '</div>';
}

/* A COMPACT ROW. Scannable, ruled, not a miniature card. */
/* THE LINESCORE, AS BROADCAST TV DRAWS IT (Cody's reference, 2026-08-28:
   "More like this! Clean it upppp" -- a table of set columns, winner-bold
   numbers, and the sets-won tally separated by a rule). One aligned grid per
   match replaces what had become THREE scattered clusters on a row: per-team
   points floating mid-column, a separate history strip far right, and the
   current set shown twice.

   Layout: two rows (away above home, same order as the names beside it),
   one column per set plus a ruled-off tally column.

     19  18  25  25  15 | 2
     25  25  18  23  12 | 2

   ⚠ TWO SOURCES THAT DO NOT OVERLAP: the crawled ledger carries `sets` on a
   final; the live feed carries them in play and EMPTIES the array at the
   whistle. A just-ended match has line scores in neither until the crawl
   catches up -- and then only the tally column renders. Nothing is
   zero-filled, ever.
   ⚠ NO SET IS VALIDATED AGAINST 25 -- the exhibition's real 24-22 set is why.
   ⚠ THE SET IN PROGRESS IS MARKED, NOT CROWNED: its column is tinted and its
   numbers carry no winner-bold, because nobody has won it. */
function rowLinescore(m, live, st) {
  const full = (live && live.sets && live.sets.length) ? live.sets
    : (m.sets && m.sets.length ? m.sets : null);
  const sc = matchScore(m, live);
  const tally = (sc && sc[0] !== null && sc[0] !== undefined) ? sc : null;
  if (!full && !tally) return '<span class="mls"></span>';
  const playing = st === 'live';
  const raw = full;
  const n = raw ? raw.length : 0;
  /* THE SHAPE, all of it Cody's (2026-08-28): sets-won FIRST, rule on its
     right; then the sets strictly in order, set one leftmost; and the set in
     progress is the LAST column, BOXED -- "make sure the current set is boxed
     or bordered and clear that it's ongoing. i think boxing things makes it
     cleaner." The box is the one live accent; its numerals are larger because
     they are the ones moving, and they carry no winner-bold -- nobody has won
     a set that is still being played. */
  let cells = '';
  for (let r = 0; r < 2; r++) {
    if (tally) {
      cells += '<b class="mlt' +
        (!playing && +tally[r] > +tally[1 - r] ? ' w' : '') +
        '" title="sets won">' + esc(String(tally[r])) + '</b>';
    }
    for (let i = 0; i < n; i++) {
      const a = raw[i][0], h = raw[i][1];
      const v = r === 0 ? a : h, o = r === 0 ? h : a;
      const cur = playing && i === n - 1;
      cells += '<i class="mlc' +
        (cur ? ' cur ' + (r === 0 ? 'ca' : 'ch') + (+v > +o ? ' up' : '')
             : (+v > +o ? ' w' : '')) +
        '" title="set ' + (i + 1) + (cur ? ' (in progress)' : '') + '">' +
        esc(String(v)) + '</i>';
    }
  }
  return '<span class="mls' + (tally ? ' hastally' : '') +
    '" style="--mlsn:' + n + '">' + cells + '</span>';
}

function matchContext(m) {
  /* ⚠ THE CLASS FOLLOWS WHAT THE VALUE IS, NEVER ITS POSITION. Keying the
     style on the array index meant the first bit always got the event's
     treatment -- so a fixture with no event rendered its VENUE in gold caps,
     and "CLIFF KEEN ARENA, ANN ARBOR" read as the name of a tournament. Same
     shape as every R4 case here: one slot, two meanings. */
  const bits = [];
  if (m.event) bits.push(['mctxe', esc(m.event)]);
  if (m.venue) {
    bits.push(['mctxv', esc(m.venue) + (m.city ? ', ' + esc(m.city) : '')]);
  }
  if (!bits.length) return '<span class="mctx"></span>';
  return '<span class="mctx" title="' +
    bits.map(b => b[1]).join(' \u00b7 ') + '">' +
    bits.map(b => '<span class="' + b[0] + '">' + b[1] + '</span>').join('') +
    '</span>';
}

/* One phrasing of a live match for a one-line eyebrow: sets tally, the set
   we are in, and the points in it -- "1-0 · 2ND SET · 18-15". The rows carry
   their numbers per team line; a CARD has one line, so it says all three
   there. Missing pieces are omitted, never zero-filled. */
function liveLine(m, live) {
  const sc = matchScore(m, live);
  const bits = [];
  if (sc && sc[0] !== null && sc[0] !== undefined) {
    bits.push(sc[0] + '\u2013' + sc[1]);
  }
  if (live && live.period) bits.push(esc(live.period));
  const cur = (live && live.sets && live.sets.length)
    ? live.sets[live.sets.length - 1] : null;
  if (cur && cur[0] !== null && cur[0] !== undefined) {
    bits.push(cur[0] + '\u2013' + cur[1]);
  }
  return bits.join(' \u00b7 ');
}

function matchRow(m, live, dest) {
  const st = matchState(m, live);
  const sc = matchScore(m, live);
  const done = sc[0] !== null && sc[0] !== undefined;
  const aw = done && +sc[0] > +sc[1], hw = done && +sc[1] > +sc[0];
  const tags = [];
  if (m.ar && m.hr) tags.push(['rv', 'ranked v ranked']);
  if (st === 'live') tags.push(['lv', 'live']);
  if (m.site === 'neutral') tags.push(['', 'neutral']);
  /* ⚠ A LIVE ROW SAYS THE POINTS, RIGHT HERE (Cody, mid-slate, with the
     NCAA.com card as the reference: "I shouldn't have to click on a match to
     see if someone is winning or losing"). This is the canonical live-
     scoreboard shape -- each team line ends in its own numbers: the CURRENT
     SET'S points, big, because they are the thing moving; the sets-won tally
     small beside them. The set is named in the row's own eyebrow (2ND SET).
     The leader of the current set is emphasised -- that is a fact about the
     set in progress, not a crowned winner. If the feed's per-set points have
     not arrived yet, only the tally renders: no invented zeros. */
  /* ⚠ ONE COMPOSED SCORE OBJECT (design review via Cody, 2026-08-28): the
     current set's points sit AT THE END OF EACH TEAM LINE -- the dominant
     number, because it is the one moving -- with the completed sets dimmed
     beside them and the tally behind a rule. No dead middle: the linescore is
     adjacent to the teams, and the venue is the quiet right edge. */
  /* the names stay clean (the review's "team names must remain the dominant
     text"); the current set lives in the linescore's boxed last column */
  const t = (name, rk, won) =>
    '<div class="mrt ' + (won ? 'won' : '') + '">' +
      (rk ? '<span class="mrk">' + rankHTML('avca', rk, true) + '</span>' : '') +
      logo(name) + '<b class="tn">' + esc(name) + '</b></div>';
  /* venue as quiet metadata, not a badged shout: "Neutral · Rec Hall, State
     College". The one badge that changes what a result MEANS -- exhibition --
     keeps its outline. Everything else is text. */
  const _mbits = [];
  if (m.site === 'neutral') _mbits.push('Neutral');
  if (m.event) _mbits.push(esc(m.event));
  if (m.venue) _mbits.push(esc(m.venue) + (m.city ? ', ' + esc(m.city) : ''));
  if (m.tv) _mbits.push(esc(m.tv));
  return '<button type="button" class="mrow ' + (st === 'live' ? 'islive' : '') +
    '" data-match="' + esc(m.gid) + '" data-dest="' + dest + '">' +
    '<span class="mwhen">' + esc(st === 'live'
        ? ((live && live.period) || 'live')
        : (m.t || m.dl || '')) + '</span>' +
    '<span class="mteams">' + t(mAway(m), m.ar, aw) + t(mHome(m), m.hr, hw) +
      '</span>' +
    rowLinescore(m, live, st) +
    '<span class="mmeta">' +
      (_mbits.length ? '<span class="mvn">' + _mbits.join(' \u00b7 ') +
        '</span>' : '') +
      (m.exh ? '<span class="mtags">' + exhTag(m) + '</span>' : '') +
    '</span></button>';
}

/* ⚠ WHY A MATCH IS FEATURED IS A STATED RULE, NOT A SCORE. Precedence only,
   from signals already in the payload, and the reason is printed. If nothing
   clears the bar there is NO featured match -- an ordinary Tuesday does not
   get a headline invented for it. */
function pickFeatured(today, liveOf) {
  const rank = m => {
    const live = liveOf(m), st = matchState(m, live);
    if (st === 'live' && m.ar && m.hr) return [0, 'Both sides ranked, and it is on now.'];
    if (st === 'live') return [1, 'It is the match in progress.'];
    if (st === 'final' && m.ar && m.hr) return [2, 'Both sides ranked, and it is settled.'];
    if (st === 'upcoming' && m.ar && m.hr) return [3, 'Both sides ranked.'];
    return [99, null];
  };
  let best = null;
  today.forEach(m => {
    const r = rank(m);
    if (r[1] && (!best || r[0] < best.score)) best = { m: m, score: r[0], why: r[1] };
  });
  return best;
}

/* ══ THE LEDGER AND THE MATCH DETAIL ══════════════════════════════════════ */
let LEDGER_STATE = 'today';

let ALL_MATCHES = null;

/* ⚠ EVERY SCHEDULED FIXTURE, NOT JUST THE NEXT WEEK. DESK is a today..+6
   window built for the rundown; LEDGER is crawled finals. allMatches() was the
   two of them, so matchByGid() -- and therefore the whole #/match/<id> route --
   knew nothing about a fixture eleven days out. The Schedule tab listed
   Kentucky v Penn State on Sept 6 and the match route said the game "may not
   have been crawled": one page holding two answers about the same fixture.
   FIXTURES is the canonical schedule, keyed by id, and it is the FLOOR here --
   DESK refines it for the current week, a final overrides both. */
const FIXTURES = {{FIXTURES_JSON}};

function allMatches() {
  /* the three sources, keyed by gid: every scheduled fixture, the desk window,
     and the crawled FINALS. A final is authoritative where they overlap -- it
     has the result.

     ⚠ BUILT ONCE. DESK and LEDGER are page constants -- nothing mutates them
     after load -- so rebuilding this index on every call was pure repetition:
     ~1,500 object copies each time, and matchByGid() did it for a SINGLE
     lookup. The day view, the ledger, the match detail, the live-stats poller
     and (new this phase) the Wire's story-to-match tie all call it.
     ⚠ MEMOISING IS ONLY SAFE BECAUSE LIVE DATA IS NOT IN HERE. Live scores
     live in LIVE_BY_ID and are read separately by matchState/matchScore, which
     is why a cached index cannot go stale mid-match. If a live field is ever
     folded into these rows, this cache has to go with it. */
  if (ALL_MATCHES) return ALL_MATCHES;
  const by = {};
  Object.keys(FIXTURES).forEach(g => { by[g] = Object.assign({}, FIXTURES[g]); });
  DESK.forEach(m => { by[m.gid] = Object.assign({}, by[m.gid] || {}, m); });
  LEDGER.forEach(r => { by[r.gid] = Object.assign({}, by[r.gid] || {}, r); });
  ALL_MATCHES = by;
  return by;
}
function matchByGid(gid) { return allMatches()[String(gid)] || null; }

/* ══ THE DAY VIEW ═════════════════════════════════════════════════════════
   What a daily sports product opens with: what is happening now, what just
   happened, what is next. Three lanes off ONE date, and the date defaults to
   today -- so the date jump is not a special case, it just moves which day
   this is about.

   ⚠ EVERY LANE IS A FILTER OVER THE SAME PAYLOAD THE FULL LEDGER READS, via
   the same matchState(). There is no second source and no second idea of what
   "final" means. A lane with nothing in it is ABSENT, not empty-with-a-zero.

   ⚠ AND A DAY WITH NO MATCHES IS ANSWERED WITH REAL FIXTURES, never filler:
   the next date that actually has matches, and the most recent day that
   actually has finals. If the schedule holds neither, it says so. */
let LEDGER_OPEN = {};       /* which lanes the reader has expanded */
const LANE_CAP = 8;         /* a stated cap, always with the remainder named */

function ledgerDayView(host, all, day, isToday) {
  const liveOf = m => LIVE_BY_ID[m.gid];
  const onDay = all.filter(m => m.d === day);
  const lane = st => onDay.filter(m => matchState(m, liveOf(m)) === st);
  /* ⚠ SORTED BY START TIME, and this took two goes. The lane first rendered in
     payload order, so a Friday read 4:00 PM, 11:00 AM, 12:00 PM, 4:00 PM,
     10:00 AM. The repair sorted on `a.ep` -- an epoch field that EXISTS ON NO
     MATCH IN THE PAYLOAD (measured: 0 of 1,594) -- so the subtraction was
     always 0 and every comparison fell through to `localeCompare` on the
     displayed clock string, which is the original bug wearing a fix. A dead
     sort key is worse than none: the comment above it says the problem is
     solved. Times are compared as MINUTES now. Ranked pairings still lift to
     the top of their lane -- a stated sort, not a score. */
  const order = (a, b) => {
    const ra = (a.ar && a.hr) ? 0 : (a.ar || a.hr) ? 1 : 2;
    const rb = (b.ar && b.hr) ? 0 : (b.ar || b.hr) ? 1 : 2;
    if (ra !== rb) return ra - rb;
    const ma = tMinutes(a.t), mb = tMinutes(b.t);
    if (ma === null && mb === null) return 0;
    if (ma === null) return 1;      /* an unreadable time sorts last */
    if (mb === null) return -1;
    return ma - mb;
  };
  const live = lane('live').sort(order);
  const fin = lane('final').sort(order);
  const up = lane('upcoming').sort(order);

  /* ⚠ A CAPPED LANE MUST NAME WHAT IT IS NOT SHOWING. The first version put
     all 195 matches of the next Friday under one heading -- the same wall this
     phase exists to remove, with a nicer label on it. Eight, then the
     remainder, counted and one click from being shown. */
  const block = (key, title, note, rows) => {
    if (!rows.length) return '';
    const open = LEDGER_OPEN[key];
    const show = open ? rows : rows.slice(0, LANE_CAP);
    const rest = rows.length - show.length;
    return '<div class="daygrp"><div class="dayhd">' + title +
      (note ? '<span class="dayhn">' + note + '</span>' : '') +
      '<span class="dayhc">' + rows.length + '</span></div>' +
      show.map(m => matchRow(m, liveOf(m), 'scores')).join('') +
      (rest > 0
        ? '<button type="button" class="lanemore" data-lane="' + esc(key) +
          '">Show ' + rest + ' more</button>'
        : (open && rows.length > LANE_CAP
            ? '<button type="button" class="lanemore" data-lane="' + esc(key) +
              '">Show fewer</button>' : '')) +
      '</div>';
  };

  let html = block('live', 'Live now', '', live) +
             block('final', 'Final today', '', fin) +
             block('up', 'Still to come', '', up);
  let shown = live.length + fin.length + up.length;
  let label = (isToday ? 'today' : dayLabel(day)) + ' \u00b7 ' + shown +
              (shown === 1 ? ' match' : ' matches');

  if (!shown) {
    const later = all.filter(m => (m.d || '') > day)
      .sort((a, b) => (a.d || '') < (b.d || '') ? -1 : 1);
    const nextDay = later.length ? later[0].d : null;
    const nextOn = nextDay ? later.filter(m => m.d === nextDay).sort(order) : [];
    const done = all.filter(m => (m.d || '') < day &&
                                 matchState(m, liveOf(m)) === 'final')
      .sort((a, b) => (a.d || '') < (b.d || '') ? 1 : -1);
    const lastDay = done.length ? done[0].d : null;
    const lastOn = lastDay ? done.filter(m => m.d === lastDay).sort(order) : [];
    /* ⚠ "No Division-I matches on Today." -- dayLabel() returns the word
       "Today", so the sentence built around it read as broken English on the
       one day it matters most. A relative label needs a different sentence,
       not the same sentence with a different noun in it. */
    html = '<p class="emptylane"><b>' + (isToday
        ? 'No Division-I matches today.'
        : 'No Division-I matches on ' + esc(dayLabel(day)) + '.') + '</b></p>' +
      block('next', 'Next match window',
            esc(nextDay ? dayLabel(nextDay) : ''), nextOn) +
      block('recent', 'Most recent finals',
            esc(lastDay ? dayLabel(lastDay) : ''), lastOn);
    /* ⚠ AND THE COUNT SAID "today - 197 matches" ON A DAY WITH NONE, because
       it counted the fallback. The count describes the day it names. */
    label = (isToday ? 'today' : dayLabel(day)) + ' \u00b7 none' +
      (nextOn.length || lastOn.length ? ' \u00b7 showing either side' : '');
    if (!nextOn.length && !lastOn.length) {
      html = '<p class="emptylane">' + (isToday
        ? 'No matches today, and the schedule holds nothing either side of it.'
        : 'No matches on ' + esc(dayLabel(day)) +
          ', and the schedule holds nothing either side of it.') + '</p>';
    }
  }
  host.innerHTML = html;
  document.getElementById('ledgercnt').textContent = label;
}

/* expand or re-collapse one lane, in place */
document.addEventListener('click', ev => {
  const b = ev.target.closest ? ev.target.closest('.lanemore') : null;
  if (!b) return;
  ev.preventDefault();
  const k = b.getAttribute('data-lane');
  LEDGER_OPEN[k] = !LEDGER_OPEN[k];
  renderLedger();
});

/* ══ THE SCOREBOARD ═══════════════════════════════════════════════════════
   One question: what matches are happening on the selected date?

   ⚠ THE DATE IS STATE, NOT A FILTER OVER EVERYTHING. The old page rendered a
   season and let you narrow it; this one renders a DAY and lets you move
   between days. That is the difference between a ledger and a scoreboard, and
   it is why previous/next/today are the first controls on the page.

   Everything reads canonical fixtures through matchState/matchScore, so no row
   here can disagree with Today, the header rail, or the match detail. */
let SB_DATE = null;      /* ISO string; null means "follow today" */
let SB_FILTER = 'all';

/* Minutes since midnight for a rendered clock time like "4:00 PM PT".

   ⚠ THE SCOREBOARD WAS SORTING TIMES AS STRINGS, and on a full slate the
   result was visibly wrong rather than subtly wrong: localeCompare puts
   "6:00 AM PT" after "5:30 PM PT" because '6' > '5', so the first Friday's
   order ran 5:30 PM, 6:00 AM, 6:00 PM, 7:00 AM, 7:00 PM, 7:30 AM -- morning
   matches scattered through the evening. It went unnoticed because every day
   the page had ever rendered held two matches.

   Returns null for anything it cannot read, INCLUDING "TBA". A time we cannot
   parse is not a time we may place: the caller sorts those last and prints
   what the feed said. */
function tMinutes(t) {
  const m = String(t == null ? '' : t).match(/^\s*(\d{1,2}):(\d{2})\s*(AM|PM)\b/i);
  if (!m) return null;
  const h = (+m[1] % 12) + (/pm/i.test(m[3]) ? 12 : 0);
  return h * 60 + (+m[2]);
}

function sbDate() { return SB_DATE || todayPT(); }

function sbShift(days) {
  const d = new Date(sbDate() + 'T12:00:00');
  d.setDate(d.getDate() + days);
  SB_DATE = new Intl.DateTimeFormat('en-CA').format(d);
  renderScoreboard();
}

function sbMatchesOn(iso) {
  const by = allMatches();
  return Object.keys(by).map(k => by[k]).filter(m => m.d === iso);
}

function sbPasses(m, live) {
  if (SB_FILTER === 'all') return true;
  const st = matchState(m, live);
  if (SB_FILTER === 'live') return st === 'live';
  if (SB_FILTER === 'final') return st === 'final';
  if (SB_FILTER === 'upcoming') return st === 'upcoming';
  if (SB_FILTER === 'ranked') return !!(m.ar || m.hr);
  /* MYBOARD-WIRE-BEGIN */
  if (SB_FILTER === 'board') {
    try {
      if (typeof mbLoad === 'function') { mbLoad();
        const MBs = (typeof MB !== 'undefined' && Array.isArray(MB)) ? MB : [];
        return MBs.indexOf(mAway(m)) >= 0 || MBs.indexOf(mHome(m)) >= 0; }
    } catch (e) { }
    return false;
  }
  /* MYBOARD-WIRE-END */
  return true;
}

function renderScoreboard() {
  const body = document.getElementById('sbBody');
  if (!body) return;
  const iso = sbDate();
  const isToday = iso === todayPT();
  const liveOf = m => LIVE_BY_ID[m.gid];

  const lab = document.getElementById('sbDayLabel');
  const sub = document.getElementById('sbDayIso');
  if (lab) lab.textContent = isToday ? 'Today' : dayLabel(iso);
  if (sub) sub.textContent = iso;
  const picker = document.getElementById('sbDate');
  if (picker && picker.value !== iso) picker.value = iso;
  const tbtn = document.getElementById('sbToday');
  if (tbtn) tbtn.disabled = isToday;

  const all = sbMatchesOn(iso);
  const rows = all.filter(m => sbPasses(m, liveOf(m)));
  const cnt = document.getElementById('sbCount');
  if (cnt) cnt.textContent = rows.length +
    (rows.length === 1 ? ' match' : ' matches') +
    (rows.length !== all.length ? ' of ' + all.length : '');

  /* ── TOP GAMES, FOR THIS DATE ONLY ───────────────────────────────── */
  /* ⚠ "TOP GAMES" MEANS A SELECTION. On a two-match evening every match was
     also a top game, so the band repeated the entire day directly above the
     list -- the same two fixtures twice, which reads as a broken page rather
     than as emphasis. It earns its place only when it is picking SOME of the
     card, so it hides when it would name all of it. */
  /* ⚠ TOP GAMES LEFT THIS PAGE (design review via Cody, 2026-08-28):
     highlights belong on Today; the Scoreboard is the working board and its
     first pixel row on a live day is Live now. The band's renderer lives on
     in the Today view; nothing here mounts it. */
  if (!rows.length) {
    /* ⚠ AN EMPTY DAY IS A STATE, NOT A BLANK. Say which day, say whether the
       filter caused it, and offer the nearest day that is not empty. */
    const near = all.length
      ? 'No match on this date matches the <b>' + esc(SB_FILTER) + '</b> filter.'
      : 'No Division-I matches on <b>' + esc(dayLabel(iso)) + '</b>.';
    const by = allMatches();
    const later = Object.keys(by).map(k => by[k])
      .filter(m => m.d && m.d > iso).sort((a, b) => a.d < b.d ? -1 : 1)[0];
    body.innerHTML = '<p class="tdquiet">' + near +
      (later ? ' The next day with matches is <a href="#" data-sbjump="' +
        esc(later.d) + '">' + esc(dayLabel(later.d)) + '</a>.' : '') + '</p>';
    return;
  }

  /* ── GROUPED BY STATE, THEN BY START TIME ─────────────────────────── */
  const lanes = [['live', 'Live now'], ['final', 'Final'],
                 ['upcoming', 'Scheduled']];
  /* ranked pairings first, then one side ranked, then the rest */
  const tier = m => (m.ar && m.hr) ? 0 : (m.ar || m.hr) ? 1 : 2;
  const byTier = (a, b) => tier(a) - tier(b);
  const byTime = (a, b) => {
    const ma = tMinutes(a.t), mb = tMinutes(b.t);
    /* a time we cannot read is not a time we may guess at: it sorts last and
       keeps whatever the feed said (TBA), rather than being placed */
    if (ma === null && mb === null) return 0;
    if (ma === null) return 1;
    if (mb === null) return -1;
    return ma - mb;
  };
  body.innerHTML = lanes.map(([st, title]) => {
    const in_ = rows.filter(m => matchState(m, liveOf(m)) === st);
    if (!in_.length) return '';
    const times = {};
    in_.forEach(m => { times[m.t || ''] = 1; });
    /* ⚠ GROUP ONLY WHEN THERE IS SOMETHING TO GROUP. On the first Friday the
       slate is 196 matches across 23 start times, which as one list is 15.7
       screens of undifferentiated rows; on a Tuesday it is four. Splitting
       four rows under four headings is worse than not splitting them, so the
       block stays whole until it is genuinely a wall. This is a presentation
       choice, not a verdict about the data. */
    const many = in_.length >= 12 && Object.keys(times).length >= 3;
    const head = (t, n) => '<h4 class="sbtime">' + esc(t || 'Time not set') +
      '<span>' + n + '</span></h4>';
    let inner;
    if (many) {
      const keys = Object.keys(times).sort((a, b) => byTime({ t: a }, { t: b }));
      inner = keys.map(k => {
        const g = in_.filter(m => (m.t || '') === k).sort(byTier);
        /* `bytime` drops the per-row clock: under a "3:00 PM PT" heading,
           twenty-eight rows each repeating "3:00 PM PT" is the heading said
           twenty-nine times. Done in CSS so matchRow keeps one signature and
           the other seven callers are untouched (R4). */
        return head(k, g.length) + '<div class="tdlist bytime">' +
          g.map(m => matchRow(m, liveOf(m), 'scores')).join('') + '</div>';
      }).join('');
    } else {
      inner = '<div class="tdlist">' +
        in_.slice().sort((a, b) => byTier(a, b) || byTime(a, b))
          .map(m => matchRow(m, liveOf(m), 'scores')).join('') + '</div>';
    }
    return '<section class="tdblock"><h3>' + title +
      '<span>' + in_.length + '</span></h3>' + inner + '</section>';
  }).join('');
}

function wireScoreboard() {
  const host = document.getElementById('v-scores');
  if (!host || host.dataset.sbwired) return;
  host.dataset.sbwired = '1';
  host.addEventListener('click', e => {
    const f = e.target.closest('[data-sbf]');
    if (f) {
      SB_FILTER = f.dataset.sbf;
      host.querySelectorAll('[data-sbf]').forEach(b =>
        b.classList.toggle('on', b === f));
      renderScoreboard();
      return;
    }
    const j = e.target.closest('[data-sbjump]');
    if (j) { e.preventDefault(); SB_DATE = j.dataset.sbjump; renderScoreboard(); return; }
    if (e.target.closest('#sbPrev')) { sbShift(-1); return; }
    if (e.target.closest('#sbNext')) { sbShift(1); return; }
    if (e.target.closest('#sbToday')) { SB_DATE = null; renderScoreboard(); return; }
  });
  const pick = document.getElementById('sbDate');
  if (pick) pick.addEventListener('change', () => {
    if (pick.value) { SB_DATE = pick.value; renderScoreboard(); }
  });
}

/* Opening the ledger renders it, so it cannot show what the page knew before
   the first poll landed. Bound once, on the document, because the <details>
   is present from load and never replaced. */
document.addEventListener('toggle', function (e) {
  const d = e.target;
  if (d && d.classList && d.classList.contains('sbfull') && d.open &&
      typeof renderLedger === 'function') renderLedger();
}, true);

function renderLedger() {
  const host = document.getElementById('ledgerbody');
  if (!host) return;
  const by = allMatches();
  const day = (document.getElementById('ldate') || {}).value || '';
  if (LEDGER_STATE === 'today') {
    /* the picked date if there is one, otherwise actually today (Pacific) */
    return ledgerDayView(host, Object.keys(by).map(k => by[k]),
                         day || todayPT(), !day);
  }
  const rows = Object.keys(by).map(k => by[k]).filter(m => {
    const st = matchState(m, LIVE_BY_ID[m.gid]);
    if (day && m.d !== day) return false;
    return LEDGER_STATE === 'all' || st === LEDGER_STATE;
  });
  rows.sort((a, b) => (a.d || '') < (b.d || '') ? 1 : (a.d || '') > (b.d || '') ? -1 : 0);
  document.getElementById('ledgercnt').textContent =
    rows.length + (rows.length === 1 ? ' match' : ' matches');
  if (!rows.length) {
    host.innerHTML = '<p class="emptylane">No ' +
      (LEDGER_STATE === 'all' ? '' : esc(LEDGER_STATE) + ' ') +
      'matches on record. Results appear here once the crawl confirms them ' +
      'final; nothing is shown before that.</p>';
    return;
  }
  /* GROUPED BY THE DAY IT WAS PLAYED, not one undifferentiated wall. */
  const days = [];
  const seen = {};
  rows.forEach(m => {
    const d = m.d || 'undated';
    if (!seen[d]) { seen[d] = []; days.push(d); }
    seen[d].push(m);
  });
  host.innerHTML = days.map(d =>
    '<div class="daygrp"><div class="dayhd">' +
      esc(d === 'undated' ? 'Date not recorded' : dayLabel(d)) +
      '</div>' + seen[d].map(m =>
        matchRow(m, LIVE_BY_ID[m.gid], 'scores')).join('') + '</div>').join('');
}

/* ONE match, as its own destination. The ribbon above is the SAME component
   the featured match uses -- there is one score header on this page and one
   definition of it. */
/* PLAYERS TO KNOW. The question a fan actually has in front of a fixture is
   "who am I watching", and a rating on its own does not answer it. Each name
   carries what she does, so the line reads as scouting rather than as a
   leaderboard. */
/* ⚠ ONE DEFINITION OF A STAR'S HEADLINE NUMBER. Three renderers each built
   their own stat line, and the negative-zero libero bug was fixed in ONE of
   them (the dossier) while this match-preview line kept printing raw kps --
   Cody's phone showed "Miabella Musignac ... -0.0 kills/set" on a live match
   preview hours after the dossier fix shipped. A defender leads with digs, a
   setter with assists, a middle with blocks, pins with kills, and a rate not
   meaningfully above zero is omitted rather than printed as nothing. */
function posHeadline(x) {
  const rate = (v, unit) => (v != null && v >= 0.05)
    ? v.toFixed(1) + ' ' + unit : null;
  return x.pos === 'LDS' ? rate(x.dps, 'digs/set')
    : x.pos === 'S' ? (rate(x.asps, 'assists/set') || rate(x.kps, 'kills/set'))
    : x.pos === 'MB' ? (rate(x.bps, 'blocks/set') || rate(x.kps, 'kills/set'))
    : rate(x.kps, 'kills/set');
}

function starLine(x) {
  const bits = [];
  if (x.role === 'six') bits.push('6-rotation');
  if (x.brs != null) bits.push(Math.round(x.brs * 100) + '% back row');
  if (x.recv != null && x.recv >= 0.15) {
    bits.push(Math.round(x.recv * 100) + '% of serve-receive');
  }
  const head = posHeadline(x);
  if (head) bits.push(head);
  return bits.slice(0, 3).join(' · ');
}

function starsSection(m) {
  const away = mAway(m), home = mHome(m);
  const ta = TEAMS[away], th = TEAMS[home];
  const sa = (ta || {}).stars, sh = (th || {}).stars;
  if (!sa && !sh) return '';
  /* ⚠ ONE SIDE MAY BE MISSING AND THAT IS RENDERED, NOT HIDDEN. A non-Division-I
     opponent has no rated players at all, and silently showing one team's stars
     would read as though the other side had nobody worth watching. */
  function col(team, list) {
    if (!list || !list.length) {
      return '<div class="starcol"><div class="stt">' + logo(team, 'sm') +
        esc(team) + '</div><p class="munk">No rated players — not a ' +
        'Division-I side, or nobody on the roster has a record yet.</p></div>';
    }
    return '<div class="starcol"><div class="stt">' + logo(team, 'sm') +
      esc(team) + '</div>' + list.map(x =>
      '<a class="starrow" href="' + routeFor('players', slug(team) + '/' +
        slug(x.n)) + '">' +
        '<span class="sp">' + esc(x.pos || '') + '</span>' +
        '<span class="sn">' + esc(x.n) + '</span>' +
        '<span class="sd">' + esc(starLine(x)) + '</span>' +
      '</a>').join('') + '</div>';
  }
  return '<div class="msec"><h3>Players to know</h3>' +
    '<div class="starcols">' + col(away, sa) + col(home, sh) + '</div>' +
    '<p class="mnote munk">The best on each side by how far above her own ' +
    'position she rates — never compared across positions. Serve-receive and ' +
    'back-row share are 2025. ' + esc(PBP_CREDIT) + '</p></div>';
}

/* ⚠ A MATCH THAT DOES NOT COUNT MUST SAY SO, ON ITSELF. The data being right
   is not enough: Nebraska beats Florida tonight, its record reads 0-0 in the
   morning, and without this the reader concludes the site is broken rather
   than that the match was an exhibition.
   It also says WHY, because "exhibition" alone invites the question -- the
   first two sets go to 21 rather than 25, so the per-set rates are on a
   different denominator and cannot be mixed with the rest of the season. */
function exhBanner(m) {
  if (!m || !m.exh) return '';
  return '<div class="exhban"><b>Exhibition</b>' +
    '<span>' + esc(m.exh) + '</span>' +
    '<span class="munk">Sets to 21, not 25 — so this does not count toward ' +
    'either record and its per-set numbers are kept out of every rating. ' +
    'The box score below is the full match.</span></div>';
}

/* The compact form, for a row in a list. */
function exhTag(m) {
  return (m && m.exh)
    ? '<span class="exhtag" title="' + esc(m.exh) +
      ' — does not count toward either record">EXH</span>' : '';
}

function renderMatchDetail(gid, dest) {
  const host = document.getElementById(dest === 'scores' ? 'scoredetail' : 'deskdetail');
  const board = document.getElementById(dest === 'scores' ? 'ledgerwrap' : 'deskboard');
  if (!host) return false;
  const m = matchByGid(gid);
  if (!m) {
    host.hidden = false; if (board) board.hidden = true;
    const s0 = document.getElementById(dest === 'scores' ? 'v-scores' : 'v-desk');
    if (s0) s0.classList.add('detailopen');
    host.innerHTML = '<p class="emptylane">That match is not in this season\'s ' +
      'records. It may not have been crawled yet.</p>' +
      '<button type="button" class="backlink" data-back="' + dest + '">&larr; Back</button>';
    return true;
  }
  const live = LIVE_BY_ID[m.gid];
  /* ⚠ ONE RESOLUTION, THEN EVERYTHING ASKS IT WHAT IT MAY DRAW. `hasBox` is
     whether a VERIFIED box score exists for this match -- not whether the
     match is over. A final without one is `final_box_pending`, which is a real
     state and renders as itself rather than as an empty table. */
  const hasBox = !!(typeof BOXES !== 'undefined' && BOXES[m.gid]
                    && BOXES[m.gid].length);
  const s6 = matchState6(m, live, hasBox);
  const caps = mCaps(s6);
  const st = matchState(m, live);
  const parent = dest === 'scores'
      ? ['Scores', routeFor('scores')] : ['Today', routeFor('desk')];
  const bits = [];
  const where = [m.venue, m.city, m.st].filter(Boolean).join(', ');
  bits.push('<span><em>Venue</em>' + (where ? esc(where)
      : '<span class="munk">not reported</span>') + '</span>');
  if (m.site === 'neutral') bits.push('<span><em>Floor</em>neutral site</span>');
  else if (m.site === 'home' || m.site === 'away') bits.push('<span><em>Floor</em>home floor</span>');
  else bits.push('<span><em>Floor</em><span class="munk">not confirmed</span></span>');
  if (m.conflict && m.conflict.length) {
    /* ⚠ SAY IT, DO NOT PICK ONE. */
    bits.push('<span><em>Sources</em><span class="wconf">schedule conflict &mdash; verify (' +
      esc(m.conflict.map(c => c.field).join(', ')) + ')</span></span>');
  }
  if (m.corrected && m.corrected.length && m.csrc) {
    bits.push('<span><em>Corrected</em><a class="wsrc" href="' + esc(m.csrc) +
      '" target="_blank" rel="noopener noreferrer">school-confirmed: ' +
      esc(m.corrected.join(', ')) + '</a></span>');
  }
  if (m.event) bits.push('<span><em>Event</em>' + esc(m.event) + '</span>');
  const tvl = (typeof TV !== 'undefined' && TV) ? (TV[m.gid] || null) : null;
  if (tvl) bits.push('<span><em>Watch</em>' + esc(tvl) + '</span>');

  /* the forecast, and only one that can be proved to predate first serve */
  let fc = '';
  if (st === 'final') {
    fc = m.hw === null || m.hw === undefined
      ? '<span class="munk">forecast unavailable' +
        (m.fsrc ? ' &mdash; ' + esc(m.fsrc) : '') + '</span>'
      : deskPct(m.hw) + ' ' + esc(mHome(m)) +
        ' <span class="munk">' + esc(m.fsrc || '') + '</span>';
  } else if (m.hw !== null && m.hw !== undefined) {
    fc = deskPct(m.hw) + ' ' + esc(mHome(m)) +
      ' <span class="munk">current forecast</span>';
  }

  /* ⚠ THE BOX SECTION IS DRAWN ONLY WHEN THE STATE PERMITS IT AND THE DATA
     EXISTS. Both, not either. A zero-filled table after a final is the exact
     thing this phase is meant to stop. */
  const box = (caps.player_lines && typeof boxHTML === 'function')
    ? boxHTML(m.gid) : '';
  host.hidden = false;
  if (board) board.hidden = true;
  const sec = document.getElementById(dest === 'scores' ? 'v-scores' : 'v-desk');
  if (sec) sec.classList.add('detailopen');
  host.innerHTML =
    '<div class="crumb"><a href="' + parent[1] + '">' + parent[0] + '</a>' +
      '<span class="sep">&rsaquo;</span><b>' + esc(mAway(m)) + ' ' + connector(m) + ' ' +
      esc(mHome(m)) + '</b></div>' +
    '<button type="button" class="backlink" data-back="' + dest + '">&larr; Back to ' +
      parent[0] + '</button>' +
    '<div class="mdet">' + exhBanner(m) + ribbonHTML(m, live, null) +
      '<div class="msec"><h3>Match facts</h3><div class="mfact">' +
        bits.join('') + '</div></div>' +
      /* ⚠ THE HEADING FOLLOWS THE STATE. "Forecast before first serve" is a
         claim about a match that HAS started; on an upcoming match it is
         simply the current forecast, and the two must not be labelled alike. */
      (fc ? '<div class="msec"><h3>' + (st === 'final'
              ? 'Forecast before first serve' : 'Forecast') + '</h3>' +
            '<div class="mfact"><span>' + fc + '</span></div></div>' : '') +
      /* live stats sit UNDER the single score ribbon, and only while this
         match is actually live on this route */
      /* live statistics, only while this match is live AND the state says
         team stats exist for it */
      (st === 'live' ? lmcSection(m.gid) : '') +
      starsSection(m) +
      /* ⚠ ONE SENTENCE PER STATE, FROM THE SHARED TABLE. Each of these is a
         true statement about the source at that moment -- not a placeholder
         standing where data should be. */
      '<div class="msec"><h3>Box score</h3>' +
        (box ? box
             : '<div class="mpend" id="mpendnote"><b>' + esc(MSTATE.label[s6] || '') +
               '</b><span>' + esc(MSTATE.note[s6] || '') + '</span>' +
               (s6 === 'final_box_pending'
                 ? '<span class="mfine">It is written to the site by the ' +
                   'verified crawl, usually within the hour. Nothing is ' +
                   'estimated in the meantime.</span>' : '') +
               '</div>') +
      '</div>' +
      /* where this came from and when -- compact, one line */
      '<p class="msrc">Official NCAA feed' +
        (live && live.updated ? ' &middot; live score updated ' +
          esc(String(live.updated)) : '') +
        (hasBox ? ' &middot; box score from the verified crawl' : '') +
        '</p>' +
    '</div>';
  if (st === 'live') { lmcStart(m.gid); } else { lmcStop(); }
  return true;
}

function closeMatchDetail() {
  lmcStop();
  ['v-desk', 'v-scores'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('detailopen');
  });
  ['deskdetail', 'scoredetail'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.hidden = true; el.innerHTML = ''; }
  });
  ['deskboard', 'ledgerwrap'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.hidden = false;
  });
}

/* every row routes; nothing opens a match by painting it in place */
/* THE canonical match URL. Every caller goes through here so a match cannot
   acquire a second address. */
function matchRoute(gid, dest) {
  const d = dest === 'scores' ? 'scores' : 'match-desk';
  return '#/' + d + '/' + encodeURIComponent(gid);
}

/* Keyboard parity: a row that only answers a mouse is not a link. */
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const row = e.target.closest && e.target.closest('[data-match]');
  if (!row) return;
  e.preventDefault();
  go(matchRoute(row.dataset.match, row.dataset.dest));
});

document.addEventListener('click', e => {
  if (e.target.closest && e.target.closest('#lmcrefresh')) {
    if (LMC_ROUTE_GID) lmcFetch(LMC_ROUTE_GID);
    return;
  }
  /* ⚠ ONE HANDLER FOR EVERY ENTRY POINT. It used to match `.mrow[data-match]`
     only, so the Match Desk and the ledger routed while a team's own result
     did not. Any element carrying data-match now reaches the same canonical
     URL -- there is one way to open a match, not one per surface. */
  const row = e.target.closest && e.target.closest('[data-match]');
  if (row) {
    go(matchRoute(row.dataset.match, row.dataset.dest));
    return;
  }
  const back = e.target.closest && e.target.closest('[data-back]');
  if (back) {
    go(back.dataset.back === 'scores' ? routeFor('scores') : routeFor('desk'));
  }
});
wirePrank();
(function wireLedgerDate() {
  const d = document.getElementById('ldate'), c = document.getElementById('lclear');
  if (d) d.addEventListener('input', renderLedger);
  if (c) c.addEventListener('click', () => {
    if (d) d.value = '';
    renderLedger();
    wireScoreboard(); renderScoreboard();
  });
})();
document.querySelectorAll('[data-ls2]').forEach(b =>
  b.addEventListener('click', () => {
    LEDGER_STATE = b.dataset.ls2;
    document.querySelectorAll('[data-ls2]').forEach(x =>
      x.classList.toggle('on', x === b));
    renderLedger();
    wireScoreboard(); renderScoreboard();
  }));

/* ⚠ TODAY'S READ IS ASSEMBLED, NOT WRITTEN. Every line is a fact already on
   this page -- a ranked pairing, a finished ranked result, the next match for
   a team on My Board -- restated in one place because they are the three
   questions the first screen owes an answer to. Nothing here characterises a
   match, predicts one, or manufactures urgency: if a fact does not exist
   today, its row is absent rather than filled with something softer. */
function todaysRead(mine, soon, liveOf) {
  const rows = [];
  const link = (gid, html) =>
    '<a class="vx-readv" href="' + matchRoute(gid, 'desk') + '">' + html + '</a>';
  /* ⚠ THIS IS THE LINE CODY NAMED. It read "#21 Kansas at #2 Pittsburgh"
     while the Rally Tape above it read "#15 Kansas" -- two valid rulers, one
     screen, and nothing on it saying which was which. */
  const nm = m => rankHTML('avca', m.ar, true) + esc(mAway(m)) + ' ' +
                  connector(m) + ' ' +
                  rankHTML('avca', m.hr, true) + esc(mHome(m));

  /* 1. what is live right now */
  const live = mine.filter(m => matchState(m, liveOf(m)) === 'live');
  if (live.length) {
    const m = live[0];
    rows.push(['<span class="vx-livedot"></span>Live',
      link(m.gid, '<b>' + nm(m) + '</b>' +
        (live.length > 1 ? ' <span class="munk">and ' + (live.length - 1) +
          ' other' + (live.length > 2 ? 's' : '') + '</span>' : ''))]);
  }

  /* 2. the ranked pairing on today's card, if there is one */
  const rr = mine.filter(m => m.ar && m.hr);
  if (rr.length) {
    const m = rr[0];
    rows.push(['Ranked v ranked',
      link(m.gid, '<b>' + nm(m) + '</b>' +
        (rr.length > 1 ? ' <span class="munk">+' + (rr.length - 1) +
          ' more today</span>' : ''))]);
  }

  /* 3. a finished result involving a ranked side */
  const done = mine.filter(m => matchState(m, liveOf(m)) === 'final'
                                && (m.ar || m.hr));
  if (done.length) {
    const m = done[0];
    const sc = matchScore(m, liveOf(m));
    rows.push(['Ranked result',
      link(m.gid, '<b>' + nm(m) + '</b> <span class="munk">' +
        (sc[0] === null || sc[0] === undefined ? '' : sc[0] + '\u2013' + sc[1]) +
        '</span>')]);
  }

  /* 4. the next match for a team on My Board -- private surface only, and
        silent when the board is empty rather than nagging about it */
  try {
    if (typeof mbLoad === 'function') {
      /* ⚠ mbLoad() POPULATES `MB`; IT DOES NOT RETURN IT. Reading its return
         value gave undefined, so this row silently never appeared -- a fact
         that was simply missing rather than wrong, which is the harder kind to
         notice. Call it, then read the list it fills. */
      mbLoad();
      const watched = new Set((typeof MB !== 'undefined' && Array.isArray(MB))
                              ? MB : []);
      if (watched.size) {
        const upcoming = mine.concat(soon).filter(m =>
          watched.has(mAway(m)) || watched.has(mHome(m)));
        if (upcoming.length) {
          const m = upcoming[0];
          const who = watched.has(mHome(m)) ? mHome(m) : mAway(m);
          rows.push(['On my board',
            link(m.gid, '<b>' + esc(who) + '</b> <span class="munk">' +
              esc(m.d === (mine[0] || {}).d ? (m.t || 'today')
                                            : dayLabel(m.d)) + '</span>')]);
        }
      }
    }
  } catch (e) { /* storage unavailable -- the row is simply absent */ }

  if (!rows.length) return '';
  return '<div class="vx-read">' + rows.map(r =>
    '<div class="vx-readrow"><i>' + r[0] + '</i>' + r[1] + '</div>').join('') +
    '</div>';
}

/* COURTSIGNAL-JS-BEGIN */
/* ══ THE RALLY TAPE ═══════════════════════════════════════════════════════
   Everything below reads DESK and LIVE_BY_ID -- the same two structures the
   Match Desk lanes read -- through the same matchState/matchScore/matchSets
   helpers. It holds no data of its own, so it cannot disagree with the lanes
   below it, and there is no path by which it can show something that is not
   already in the payload.

   ⚠ THE HONESTY RULES, EACH GUARDED IN test_court_signal.py:
     1. An upcoming match shows NO score and no numbered set cells.
     2. An unplayed set renders a court dot. Never 0. ('' is not zero -- the
        same distinction scripts/match_state.py had to make, and for the same
        reason: the feed serves '' and '' coerces to 0.)
     3. The context line is a fact from the feed or it says the fact is
        missing -- "venue not reported", never an inferred home floor.
     4. A quiet day carries the NEXT REAL FIXTURE, or states that there is not
        one. It never fabricates activity, and it does not animate.
     5. The live pulse runs only while something is genuinely live.        */

const CS_SETS = 5;   /* best-of-five: the shape of the diagram, not a guess */
/* the results ribbon, emitted server-side, now rendered on Today */
const CHANGED_ROWS_HTML = `{{CHANGED_ROWS}}`;
const CHANGED_META_TXT = `{{CHANGED_META}}`;
/* Empty string in the public build, by the same substitution the chat uses. */
const CS_DIGBY = {{DIGBY_FACE_JS}};

function csPick(mine, soon, liveOf) {
  /* Which single match the tape is about, in a STATED order of preference:
     live before finished before upcoming, and within each, ranked-vs-ranked
     before ranked before first. No composite score -- a list of reasons, and
     the first one that matches wins. */
  const st = m => matchState(m, liveOf(m));
  const rr = m => m.ar && m.hr;
  const rk = m => m.ar || m.hr;
  const live = mine.filter(m => st(m) === 'live');
  if (live.length) return [live.filter(rr)[0] || live.filter(rk)[0] || live[0],
                           'live', live.length];
  const done = mine.filter(m => st(m) === 'final');
  if (done.length) return [done.filter(rr)[0] || done.filter(rk)[0] ||
                           done[done.length - 1], 'final', done.length];
  const up = mine.filter(m => st(m) === 'upcoming');
  if (up.length) return [up.filter(rr)[0] || up.filter(rk)[0] || up[0],
                         'next', up.length];
  /* nothing today -- the next real fixture on the schedule, never filler */
  if (soon.length) {
    const d = soon[0].d;
    const on = soon.filter(m => m.d === d);
    return [on.filter(rr)[0] || on.filter(rk)[0] || on[0], 'next', on.length];
  }
  return [null, 'none', 0];
}

function csSide(name, rk, sets, won, serving, quiet) {
  /* ⚠ FOUR COLUMNS, FOUR CHILDREN, ALWAYS. logo() returns '' for a team we
     hold no crest for -- which is every non-Division-I opponent -- and a
     missing child shifts the name into the 26px crest track. The match ribbon
     paid for this exact defect once already. */
  return '<div class="cs-side' + (won ? ' cs-won' : '') +
    (serving ? ' cs-serve' : '') + '">' +
    /* ⚠ COMPACT, BUT NEVER BARE. The tape said "ranks: AVCA poll" once in its
       context line, which is a footnote, not a label at the point of use --
       and the readiness panel four inches below it ranks the same match by
       Digby. The label travels with the number now. */
    '<span class="cs-trk">' + rankHTML('avca', rk, true) + '</span>' +
    (logo(name) || '<span class="cs-nologo"></span>') +
    '<a class="cs-nm" href="' + routeFor('teams', slug(name)) + '">' +
      esc(name) + '</a>' +
    (quiet ? '' : '<span class="cs-sets">' +
      (sets === null || sets === undefined || sets === '' ? '&mdash;' : sets) +
      '</span>') +
    '</div>';
}

function csCells(sets, playing) {
  /* One cell per set of a best-of-five. A set that happened prints both
     scores with the winner emphasised; a set that has not prints a dot. */
  const out = [];
  for (let i = 0; i < CS_SETS; i++) {
    const pair = setPair(sets[i]);
    const a = pair ? pair[0] : null;
    const h = pair ? pair[1] : null;
    if (!pair) {
      out.push('<div class="cs-cell cs-empty" style="--cs-i:' + i + '">' +
        '<i>&middot;</i><i>&middot;</i></div>');
      continue;
    }
    const now = playing && i === sets.length - 1;
    out.push('<div class="cs-cell' + (now ? ' cs-now' : '') +
      '" style="--cs-i:' + i + '">' +
      '<i class="' + (a > h ? 'cs-cw' : '') + '">' + a + '</i>' +
      '<i class="' + (h > a ? 'cs-cw' : '') + '">' + h + '</i></div>');
  }
  return '<div class="cs-cells">' + out.join('') + '</div>';
}

function csWhere(m) {
  /* ⚠ AN INFERRED VENUE PRESENTED AS FACT IS AN R5 VIOLATION, and this page
     has already been wrong about exactly this -- two AVCA First Serve matches
     on a neutral floor at Fiserv Forum read as home games. The feed says it,
     or we say it did not. */
  if (!m.venue) return '<span class="cs-unk">venue not reported</span>';
  const city = [m.city, m.st].filter(Boolean).join(' ');
  return '<b>' + esc(m.venue) + '</b>' + (city ? ' ' + esc(city) : '');
}

function todayPT() {
  return new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
}

function csCtx(m, kind, n) {
  /* ONE factual line. Each piece is a field that exists, or it is absent.
     ⚠ ORDER IS BY WHAT THE READER WANTS FIRST, and that differs by state.
     Before a match the question is WHEN; after it the question is WHERE. The
     first version led with "venue not reported" on a fixture three days out,
     so the loudest thing in the band was a missing field. */
  const bits = [];
  if (kind === 'next' && m.t) bits.push('<b>' + esc(m.t) + '</b>');
  bits.push(csWhere(m));
  if (m.site === 'neutral') bits.push('neutral floor');
  if (m.event) bits.push(esc(m.event));
  if (n > 1) {
    /* ⚠ "ON THE CARD" WAS A FALSE SENTENCE ON A QUIET DAY. With nothing today
       the pick falls through to the next scheduled date, so those 194 matches
       are not on today's card at all -- and the link went to the Match Desk,
       which would have shown none of them. Say which day, and go where they
       actually are. */
    const same = kind !== 'next' || m.d === todayPT();
    bits.push('<a href="' + (same ? routeFor('desk') : routeFor('schedule')) +
      '">' + (n - 1) + ' other' + (n > 2 ? 's' : '') +
      (same ? ' on the card' : ' that day') + '</a>');
  }
  /* ⚠ TWO RANK BASES SAT INCHES APART, UNLABELLED. The tape's ranks come from
     the scoreboard feed, which carries the AVCA poll; the readiness panel
     directly below it ranks by Digby's Top 25. Kansas read #15 in one and #21
     in the other on the same match. Both are right. Neither said which it was,
     which is the R4 trap exactly -- one glyph, two meanings. */
  if (m.ar || m.hr) bits.push('<span class="cs-unk">ranks: AVCA poll</span>');
  return '<div class="cs-ctx">' +
    bits.join('<span class="cs-sep">/</span>') + '</div>';
}

/* ⚠ THE BAND WAS THE SAME SIZE ON EVERY SCREEN, AND THAT WAS THE PROBLEM.
   Measured before this change: 335px of chrome before any content on all six
   destinations -- 41% of an 825px viewport -- and the band was 129px of it,
   carrying a match two days away. On Rankings, Teams, Intel, My Ballot and
   match detail that is a marquee for something the reader did not ask about,
   sitting on top of the thing they did.

   Two shapes now, chosen by CONTEXT rather than by taste:

     marquee  the full diagram. Today only, and only when the match is
              genuinely near -- live now, or today, or tomorrow.
     rail     one compact line: what is on, when, and a link. Everywhere else,
              and on Today when the next match is days out.

   ⚠ AND AN UPCOMING MATCH NEVER RENDERS SET CELLS. Five dashed boxes with dots
   in them read as a score that failed to load. They are the shape of a
   best-of-five that has not happened, which is a fine thing to show ONCE a
   match is live, and noise before it. */
function csIsTodayRoute() {
  const h = (location.hash || '').replace(/^#\/?/, '').split('/')[0];
  return !h || h === 'today' || h === 'match-desk';
}

function csNearness(m, live) {
  if (live) return 'live';
  const today = todayPT();
  if (!m || !m.d) return 'far';
  if (m.d === today) return 'today';
  const t = new Date(today), d = new Date(m.d);
  const days = Math.round((d - t) / 86400000);
  return days === 1 ? 'tomorrow' : 'far';
}

function csTape() {
  const mount = document.getElementById('cstape');
  if (!mount) return;
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  const liveOf = m => LIVE_BY_ID[m.gid];
  const mine = DESK.filter(m => m.d === today);
  const soon = DESK.filter(m => m.d > today);
  const picked = csPick(mine, soon, liveOf);
  const m = picked[0], kind = picked[1], n = picked[2];

  /* ⚠ NOTHING SCHEDULED IS A STATE, NOT A FAILURE. The tape keeps its
     geometry and says the true thing. Digby appears HERE and in the Intel
     empty state and nowhere else -- a signal guide for the two moments where
     the honest answer is "there is nothing", which is exactly where a page
     most wants to invent something. */
  if (!m) {
    mount.innerHTML = '<div class="cs-tape cs-quiet cs-court" ' +
      'data-cs-state="none"><div class="cs-none">' +
      (CS_DIGBY ? '<span class="cs-guide">' + CS_DIGBY + '</span>' : '') +
      '<span><b>No matches on the schedule.</b> ' +
      'Nothing further has been published to the Division-I scoreboard feed ' +
      'yet.</span></div></div>';
    return;
  }

  const live = liveOf(m);
  const st = matchState(m, live);
  const quiet = st === 'upcoming';
  const sc = quiet ? [null, null] : matchScore(m, live);
  const sets = quiet ? [] : matchSets(m, live);
  const aw = (sc[0] !== null && sc[1] !== null) && +sc[0] > +sc[1];
  const hw = (sc[0] !== null && sc[1] !== null) && +sc[1] > +sc[0];
  const state6 = matchState6(m, live, !!(m.final && m.final.box));

  /* marquee only on Today, and only when the match is genuinely near */
  const near = csNearness(m, live);
  const marquee = csIsTodayRoute() && (near === 'live' || near === 'today' ||
                                       near === 'tomorrow' || st === 'final');
  const label = st === 'live' ? 'Live' : st === 'final' ? 'Final' : 'Next serve';
  const when = st === 'live' ? esc((live && live.period) || 'in progress')
             : esc(dayLabel(m.d));
  /* ⚠ THE DATE PRINTED TWICE, four inches apart -- once in the state column
     and once at the head of the context line, because both fixes for "say
     when" landed and neither looked at the other. The state column answers
     WHICH DAY; the context line answers what time and where. */

  /* ⚠ THE SERVE INDICATOR IS ONLY EVER SHOWN WHEN THE FEED SAYS SO, and today
     the feed carries no such field -- so it renders on nobody. The cyan dot
     exists in the stylesheet for the day probe_live_boxscore.py proves the
     feed carries it; until then this reads false for both sides rather than
     being guessed at from the score. */
  const servingAway = false, servingHome = false;

  if (!marquee) {
    /* ── THE RAIL. One line, no court, no set cells, no vertical budget. */
    mount.innerHTML =
      '<div class="cs-rail' + (st === 'live' ? ' cs-live' : '') +
        '" data-cs-state="' + esc(state6) + '" data-cs-shape="rail">' +
        '<span class="cs-rlab">' + (st === 'live' ? '<i class="cs-dot"></i>' : '') +
          label + '</span>' +
        '<a class="cs-rmatch" href="' + matchRoute(m.gid, 'desk') + '">' +
          rankHTML('avca', m.ar, true) + esc(mAway(m)) +
          '<span class="cs-rv">' + connector(m) + '</span>' +
          rankHTML('avca', m.hr, true) + esc(mHome(m)) + '</a>' +
        '<span class="cs-rwhen">' + when + '</span>' +
        (n > 1 ? '<a class="cs-rmore" href="' + routeFor('scores') + '">' +
          (n - 1) + ' more</a>' : '') +
      '</div>';
    return;
  }

  mount.innerHTML =
    '<div class="cs-tape cs-court ' +
      (st === 'live' ? 'cs-live' : quiet ? 'cs-quiet' : '') +
      '" data-cs-shape="marquee" data-cs-state="' + esc(state6) + '" data-cs-kind="' + kind + '">' +
      '<div class="cs-st"><span class="cs-stl"><i class="cs-dot"></i>' +
        label + '</span><span class="cs-when">' + when + '</span></div>' +
      '<div class="cs-teams">' +
        csSide(mAway(m), m.ar, sc[0], aw, servingAway, quiet) +
        (quiet ? '<div class="cs-at">at</div>' : '') +
        csSide(mHome(m), m.hr, sc[1], hw, servingHome, quiet) +
      '</div>' +
      /* ⚠ SET CELLS ARE DRAWN ONLY WHILE THERE IS A SCORELINE TO DRAW.
         The history here is two reversals and the comments had been stacked
         rather than reconciled, so the file argued with itself: an earlier
         note said five dashed cells were "the true thing to show before first
         serve", and the note directly beneath it said the opposite. The
         SECOND one won in code and is right -- `quiet` is exactly
         `st === 'upcoming'`, so a match that has not started draws none.
         Both suppressions exist for the same reason: an empty dashed cell can
         only ever mean "not yet", and beside a match that is not going to
         play any more sets it reads as a scoreline that failed to load.
           upcoming        -> no cells (nothing has happened)
           live / final    -> cells, showing the shape of a best-of-five
           final, no sets  -> no cells (the two-source seam: the live feed
                              empties `sets` at the whistle and the crawl has
                              not caught up; "we do not have it" renders as
                              nothing, the same rule the scoreboard row uses)
         csCells() stays the single definition of an unplayed set (R4). */
      /* ⚠ AND NOT AFTER THE LAST ONE EITHER. The reasoning above holds for a
         match that has not started -- five dashed cells are the shape of a
         best-of-five still to come. On a match that is OVER they say the
         opposite: Florida-Nebraska sat under the word FINAL at 0-2 with five
         empty boxes beside it, which reads as a scoreline that failed to
         load. It is the two-source seam -- the live feed empties `sets` the
         instant a match goes final and the crawl has not caught up -- and the
         honest rendering of "we do not have the line score" is nothing at
         all, the same rule the scoreboard row follows. (This one was also
         a best-of-THREE exhibition, so five cells were wrong twice over.) */
      (quiet || (st === 'final' && !sets.length)
        ? '' : csCells(sets, st === 'live')) +
      '<div class="cs-pad"></div>' +
      csCtx(m, kind, n) +
    '</div>';
}

/* ══ THE MATCH MOMENT ═════════════════════════════════════════════════════
   Built from DESK + LIVE_BY_ID through the same helpers everything else uses,
   so it cannot disagree with the tape above it or the lanes below it.

   ⚠ EVERY VALUE ON IT IS CHECKABLE AND NOTHING IS DECORATIVE-BUT-FACTUAL-
   LOOKING. Ranks carry their ruler (the contract from the wayfinding phase).
   An unplayed set is absent, not a 0. A venue is the feed's or it says it was
   not reported. Home/away/neutral comes from `site`, never inferred.

   ⚠ AND IT IS NOT A PHOTOGRAPH AND MUST NOT BE MISTAKEN FOR ONE. No likeness,
   no crowd, no invented action -- crests and type only. */
function momentHTML(m, live, opts) {
  opts = opts || {};
  const st = matchState(m, live);
  const sc = matchScore(m, live);
  const sets = matchSets(m, live);
  const aw = (sc[0] !== null && sc[1] !== null) && +sc[0] > +sc[1];
  const hw = (sc[0] !== null && sc[1] !== null) && +sc[1] > +sc[0];
  const ca = (typeof COLORS !== 'undefined' && COLORS[mAway(m)]) || '';
  const cb = (typeof COLORS !== 'undefined' && COLORS[mHome(m)]) || '';

  const side = (name, rk, won, cls) =>
    '<div class="mm-side ' + cls + (won ? ' won' : '') + '">' +
      (logo(name) || '<span class="mm-nologo"></span>') +
      '<span class="mm-nm">' + esc(name) + '</span>' +
      (rk ? '<span class="mm-rk">' + rankHTML('avca', rk, true) + '</span>' : '') +
    '</div>';

  /* ⚠ THE SCORE ONLY EXISTS ONCE IT EXISTS. Before first serve the middle of
     the poster carries the start time, which is the fact available then. */
  const middle = (st === 'upcoming' || sc[0] === null || sc[0] === undefined)
    ? '<div class="mm-time">' + esc(m.t || 'Time TBA') +
      '<span>' + esc(dayLabel(m.d)) + '</span></div>'
    : '<div class="mm-sc">' + sc[0] + '<i>–</i>' + sc[1] + '</div>';

  /* the per-set strip, only for sets that were actually played */
  const strip = sets.map(setPair).filter(Boolean);
  const setsHtml = strip.length
    ? '<div class="mm-sets">' + strip.map(v =>
        '<span class="mm-set">' + v[0] + '–' + v[1] + '</span>').join('') + '</div>'
    : '<div class="mm-sets"></div>';

  const where = m.venue
    ? esc(m.venue) + ([m.city, m.st].filter(Boolean).length
        ? ' ' + esc([m.city, m.st].filter(Boolean).join(' ')) : '')
    : '<span class="mm-unk">venue not reported</span>';
  /* ⚠ FROM `site`, NEVER INFERRED FROM WHO IS LISTED AT HOME -- and only the
     values that MEAN something to a reader. The first version printed
     esc(m.site) for anything non-neutral, which put the internal token
     "NO-VENUE" on the poster as though it were a fact about the match. It is
     not: `no-venue` is this pipeline's way of saying the feed published no
     venue for the fixture (132 of 463), which the footer already says in
     words. A badge is for a stated condition; an unknown token gets none. */
  const SITE_WORD = { neutral: 'Neutral floor', home: 'Home' };
  const siteTag = SITE_WORD[m.site]
    ? '<span class="mm-site">' + SITE_WORD[m.site] + '</span>' : '';

  const label = st === 'live' ? 'Live' : st === 'final' ? 'Final' : 'Upcoming';
  const when = st === 'live'
    ? esc((live && live.period) || 'in progress')
    : esc(dayLabel(m.d));

  const fig =
    '<figure class="mm cs-court ' + (st === 'live' ? 'is-live' : '') + '"' +
      (ca || cb ? ' style="' + (ca ? '--ta:' + esc(ca) + ';' : '') +
                   (cb ? '--tb:' + esc(cb) : '') + '"' : '') +
      ' data-mm-state="' + esc(matchState6(m, live, false)) + '">' +
      '<div class="mm-top"><span class="mm-state">' +
        (st === 'live' ? '<i class="cs-dot"></i>' : '') + label + '</span>' +
        '<span class="mm-when">' + when + '</span></div>' +
      '<div class="mm-body">' +
        side(mAway(m), m.ar, aw, 'a') + middle + side(mHome(m), m.hr, hw, 'b') +
      '</div>' + setsHtml +
      '<div class="mm-foot">' + siteTag + where + '</div>' +
    '</figure>';
  return opts.nolink ? fig
    : '<a class="mmlink" href="' + matchRoute(m.gid, opts.dest || 'desk') +
      '">' + fig + '</a>';
}

function csStatus() {
  /* The gallery readout: date, feed freshness, and an honest live/quiet word.
     ⚠ FRESHNESS IS REPORTED, NOT ASSERTED. LIVE_STAMP is empty on a static
     build because /api/live is not there -- which is a true and useful thing
     to say ("feed not connected"), and a quite different claim from "stale". */
  const el = document.getElementById('csstatus');
  if (!el) return;
  const today = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Los_Angeles', weekday: 'short', month: 'short',
    day: 'numeric' }).format(new Date());
  const liveOf = m => LIVE_BY_ID[m.gid];
  const day = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  const nlive = DESK.filter(m => m.d === day &&
                                 matchState(m, liveOf(m)) === 'live').length;
  /* ⚠ I SLICED A STRING WHOSE FORMAT I HAD NEVER LOOKED AT. The first
     version printed LIVE_STAMP.slice(11,16), assuming an ISO timestamp. The
     server actually sends "8:59:54 PM PT", so characters 11-16 are "PT" -- and
     the strip read "PT feed", a made-up value rendered with total confidence
     in the masthead. Measured, not reasoned about: fetch('/api/live').updated.
     Print what the server said. */
  const feed = LIVE_STAMP
    ? 'feed <b class="cs-fresh">' + esc(String(LIVE_STAMP)) + '</b>'
    : '<b class="cs-stale">feed not connected</b>';
  el.innerHTML =
    '<span>' + esc(today) + ' PT</span>' +
    '<span>' + feed + '</span>' +
    '<span>' + (nlive ? '<b class="cs-fresh">' + nlive + ' live</b>'
                      : '<b>quiet</b>') + '</span>';
}
/* COURTSIGNAL-JS-END */

/* ══ WHY A MATCH IS WORTH YOUR TIME ═══════════════════════════════════════
   ⚠ NAMED REASONS, NOT A RELEVANCE SCORE. Every tag below is a fact about the
   fixture that a reader can check and disagree with. A single blended number
   would be unarguable and unexplainable, which is the opposite of what a
   voter's tool is for -- and it is the one thing this page has refused since
   the Match Desk was built.

   Order is a STATED PRECEDENCE, not a weighting: a ranked pairing outranks a
   watched team outranks a televised match, and so on down. */
function todayReasons(m, live) {
  const out = [];
  if (m.ar && m.hr) out.push(['rv', 'ranked v ranked',
    'Both sides are in the AVCA poll']);
  /* MYBOARD-WIRE-BEGIN */
  /* ⚠ THE WATCHED-TEAM REASON IS PRIVATE and is fenced in both layers. It
     shipped unfenced and the public gate caught the words on the published
     page -- a reason a public reader could never see the basis for. */
  let watched = [];
  try {
    if (typeof mbLoad === 'function') { mbLoad();
      const MBs = (typeof MB !== 'undefined' && Array.isArray(MB)) ? MB : [];
      watched = [mAway(m), mHome(m)].filter(t => MBs.indexOf(t) >= 0); }
  } catch (e) { }
  if (watched.length) out.push(['mb', 'my board', watched.join(' and ') +
    ' on My Board']);
  /* MYBOARD-WIRE-END */
  if (m.tv) out.push(['tv', 'national TV', 'On ' + m.tv]);
  if (m.kind === 'conf') out.push(['cf', 'conference test',
    'A league match, so it counts toward the table']);
  /* ⚠ RANKING DISAGREEMENT IS A REAL, CHECKABLE FACT and it is the one a Top
     25 voter most wants surfaced: the two orders on this page disagree about
     a team by a wide margin, so the result is evidence either way. Both ranks
     are shown with their basis so the reader sees the disagreement itself. */
  const dis = [[mAway(m), m.ao, m.ap], [mHome(m), m.ho, m.hp]]
    .filter(x => x[1] && x[2] && Math.abs(x[1] - x[2]) >= 8);
  dis.forEach(x => out.push(['dg', 'ranking disagreement',
    x[0] + ' is AVCA #' + x[1] + ' and POWER #' + x[2]]));
  if (m.site === 'neutral' && m.event) out.push(['ev', esc(m.event),
    'Part of ' + m.event]);
  /* ⚠ SAME MISTAKE, SAME LINE OF REASONING: a feed entry exists for every
     match on today's card, started or not. Only a resolved live state earns
     the chip. */
  if (matchState(m, live) === 'live') {
    out.unshift(['lv', 'live now', 'In progress']);
  }
  return out;
}

/* One line of "who is on the floor" on a Today card. The decision this page
   exists to serve is whether to make time for a match, and a name you know is
   often the whole answer.
   ⚠ ONE NAME PER SIDE, NOT THREE. The full list lives on the match page; a
   card that turns into a roster stops being scannable, which is the thing
   Cody asked to fix in the first place. */
function starPeek(m) {
  const a = ((TEAMS[mAway(m)] || {}).stars || [])[0];
  const h = ((TEAMS[mHome(m)] || {}).stars || [])[0];
  if (!a && !h) return '';
  const bit = x => x
    ? '<span class="pk"><i>' + esc(x.pos || '') + '</i>' + esc(x.n) + '</span>'
    : '';
  return '<span class="tdstars">' + bit(a) +
    (a && h ? '<span class="pkv">vs</span>' : '') + bit(h) + '</span>';
}

function reasonChips(m, live, skip) {
  /* `skip` lists reason KEYS a caller already states elsewhere on the same
     card. The Top Games eyebrow says LIVE with the set tally, and the card
     then wore a second "live now" chip two lines down -- the same fact twice
     in forty pixels (Cody's phone screenshot). Existing callers pass two
     args and are untouched. */
  const rs = todayReasons(m, live)
    .filter(r => !skip || skip.indexOf(r[0]) < 0);
  if (!rs.length) return '';
  return '<span class="tdwhy">' + rs.map(r =>
    '<span class="tdtag ' + r[0] + '" title="' + esc(r[2]) + '">' +
    esc(r[1]) + '</span>').join('') + '</span>';
}

/* A match with at least one named reason is a "top game". Nothing else is. */
function topGames(list, liveOf, cap) {
  return list.map(m => [m, todayReasons(m, liveOf(m))])
    .filter(x => x[1].length)
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, cap || 6);
}

function renderDesk() {
  const todayBox = document.getElementById('desktodaycards');
  if (!todayBox) return;
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  const liveOf = m => LIVE_BY_ID[m.gid];
  const mine = DESK.filter(m => m.d === today);
  const soon = DESK.filter(m => m.d > today);

  /* THE DATE AND STATE HEADER: what day it is, and what is actually on it. */
  const lanes = { live: [], final: [], up: [] };
  mine.forEach(m => {
    const st = matchState(m, liveOf(m));
    lanes[st === 'live' ? 'live' : st === 'final' ? 'final' : 'up'].push(m);
  });
  const parts = [];
  if (lanes.live.length) parts.push(lanes.live.length + ' live');
  if (lanes.final.length) parts.push(lanes.final.length + ' final');
  if (lanes.up.length) parts.push(lanes.up.length + ' to come');
  /* ⚠ THE LEAD SAID "no Division-I matches scheduled" AND THE BLOCK BELOW IT
     SAID "No Division-I matches today" -- the same fact twice, four lines
     apart. On a quiet day the lead now carries only the date and the standing
     caveat; the state is stated once, by the block whose job it is. */
  /* ⚠ NO EXPLANATORY SENTENCE ON THE LANDING PAGE. This read "Today. Live
     scores come from the official scoreboard feed; a forecast is a probability
     from the rally model, not a pick." -- a caveat about the machinery, under
     a heading that already said Today, on the one screen that is supposed to
     answer what to watch. The caveats are still true and still stated where
     the numbers they qualify actually appear.
     What replaces it is a DATE and a COUNT, because that is the whole of what
     a landing page owes before its first row. */
  const _nlive = lanes.live.length;
  document.getElementById('desklead').innerHTML =
    '<span class="tdnow">' + esc(dayLabel(today)) + '</span>' +
    (_nlive ? '<span class="tdlivenow"><i class="cs-dot"></i>' + _nlive +
      ' live</span>' : '');
  document.getElementById('desktodaymeta').textContent = '';

  /* ══ THE LANDING PAGE ════════════════════════════════════════════════
     ⚠ THE HUB RECORDS ALL 348 DIVISION-I TEAMS. THIS SCREEN SHOWS A HANDFUL.
     That is the whole product rule, and it is not a filter applied late -- the
     crawl, the ratings, the ledger and the scoreboard all still carry every
     match in the division, including the ones in leagues nobody covers. What
     changes here is only what is put in front of a reader who has five
     seconds: the matches he is plausibly going to watch or vote on.

     ⚠ AND ABSENCE IS NEVER ANNOUNCED. The page used to lead with "No
     Division-I matches today. The next window is Friday, August 28 -- 195
     matches." Neither half helps: he does not care that 195 mid-major fixtures
     exist, and if the first row says Friday then there is obviously nothing
     before Friday. The dates carry that.

     Four blocks, in this order, each bounded:
       Your next watches            3-5, with WHERE TO WATCH
       Big weekend ahead            the rest of the ranked slate, compact
       Results that changed the picture
       the personal watchlist       small, last  (private; fenced elsewhere)
  */
  const by = allMatches();
  const every = Object.keys(by).map(k => by[k]);
  const soon7 = every.filter(m => m.d && m.d >= today &&
    (new Date(m.d) - new Date(today)) / 86400000 <= 7);

  /* ⚠ THE SELECTION RULE IS PRINTED, NOT HIDDEN. A reader who disagrees with
     what is on his own landing page should be able to see why it is there. */
  const watchable = m => {
    const rs = todayReasons(m, liveOf(m));
    if (!rs.length) return null;
    /* rank the reasons themselves -- a televised ranked pairing beats an
       untelevised one, and both beat a lone conference match */
    let w = 0;
    if (m.ar && m.hr) w += 40;
    else if (m.ar || m.hr) w += 18;
    if (m.tv) w += 25;
    if (rs.some(r => r[0] === 'mb')) w += 20;
    if (rs.some(r => r[0] === 'dg')) w += 10;
    /* ⚠ A FINISHED MATCH IS NOT A NEXT WATCH, AND THIS OFFERED ONE. Two
       separate faults, both here:
         * `if (liveOf(m))` is the truthiness mistake again -- a feed row
           exists for every match on today's card, finished ones included, so
           a completed match collected +100 and floated to the TOP of the list.
         * nothing ever removed it, because `done` below only looked at days
           BEFORE today.
       The result was Florida-Nebraska sitting in "Your next watches" as
       "TODAY 5:00 PM PT" while the masthead rail, the Scoreboard and the match
       detail all correctly said FINAL 0-2. One match, two answers, on one
       screen. */
    const st = matchState(m, liveOf(m));
    if (st === 'final') return null;
    if (st === 'live') w += 100;
    return w ? [m, rs, w] : null;
  };
  /* ⚠ THIRD SITE OF THE SAME DATE+TIME CONCATENATION. Comparing
     `date + "6:00 AM PT"` lexically is right about the date and wrong about
     the clock. Ties on watch weight are broken by the real chronology. */
  const ranked = soon7.map(watchable).filter(Boolean)
    .sort((a, b) => b[2] - a[2] ||
      String(a[0].d || '').localeCompare(String(b[0].d || '')) ||
      ((ma, mb) => (ma === null && mb === null) ? 0
        : ma === null ? 1 : mb === null ? -1 : ma - mb
      )(tMinutes(a[0].t), tMinutes(b[0].t)));

  const watches = ranked.slice(0, 5);
  const watchIds = watches.map(x => x[0].gid);
  const weekend = ranked.filter(x => watchIds.indexOf(x[0].gid) < 0).slice(0, 10);

  /* ⚠ INCLUDING TODAY. This read `m.d < today`, so a match that finished a few
     hours ago belonged to no section at all -- not a watch, not a result. It
     simply stayed where it was. A final is a final on the day it happens. */
  const done = every
    .filter(m => m.d && m.d <= today && matchState(m, liveOf(m)) === 'final')
    .sort((a, b) => a.d < b.d ? 1 : -1);
  /* ⚠ "CHANGED THE PICTURE" IS A STATED TEST, NOT AN EDITORIAL FEEL:
     a ranked side lost, or a ranked side was taken to five. */
  const changed = done.filter(m => {
    if (!(m.ar || m.hr)) return false;
    const sc = matchScore(m, liveOf(m));
    if (sc[0] === null || sc[0] === undefined) return false;
    const five = (+sc[0] + +sc[1]) === 5;
    const rankedLost = (m.ar && +sc[0] < +sc[1]) || (m.hr && +sc[1] < +sc[0]);
    return five || rankedLost;
  }).slice(0, 5);

  const watchCard = x => {
    const m = x[0];
    const live = liveOf(m);
    /* ⚠ BEING IN THE LIVE FEED IS NOT THE SAME AS BEING IN PROGRESS, AND THIS
       SHIPPED SAYING OTHERWISE. liveOf() returns the feed's entry for EVERY
       match on today's scoreboard, including ones it explicitly marks
       `state:"pre"` / `state6:"upcoming"` / "Not started." -- so at 4:45pm
       Pacific, with first serve at 5:00, Florida at Nebraska and SMU at Penn
       St. both rendered as LIVE. The feed was right the whole time; this card
       was answering a question it had not asked.
       The codebase already resolves this once, centrally, exactly so three
       renderers do not each invent it. Ask it. */
    const isLive = matchState(m, live) === 'live';
    return '<a class="wcard' + (isLive ? ' islive' : '') + '" href="' +
      matchRoute(m.gid, 'desk') + '">' +
      '<span class="wtop">' +
        /* ⚠ A LIVE CARD SAYS THE SCORE (Cody's phone screenshot: "LIVE -
           3RD SET" and not a number in sight). Set tally beside the period,
           the same rule as the Top Games eyebrow. */
        '<span class="wwhen">' + (isLive
          ? '<i class="cs-dot"></i>LIVE ' + (liveLine(m, live) || 'in progress')
          : esc(dayLabel(m.d)) + (m.t ? ' &middot; ' + esc(m.t) : '')) + '</span>' +
        /* ⚠ WHERE TO WATCH, OR NOTHING. Joined from Cody's own listings; the
           feed carries no broadcast at all. An unmatched fixture says so
           rather than implying it is not televised. */
        (m.tv ? '<span class="wnet">' + esc(m.tv) + '</span>'
              : '<span class="wnet none" title="No broadcast is listed in the '
                + 'TV file for this fixture. The feed carries no broadcast '
                + 'information at all, so this means unknown, not untelevised."'
                + '>no listing</span>') +
      '</span>' +
      '<span class="wteams">' +
        rankHTML('avca', m.ar, true) + esc(mAway(m)) +
        '<i>' + connector(m) + '</i>' +
        rankHTML('avca', m.hr, true) + esc(mHome(m)) +
      '</span>' +
      '<span class="wmeta">' + (m.venue ? esc(m.venue) : '<span class="munk">venue TBA</span>') +
        (m.event ? ' &middot; ' + esc(m.event) : '') + '</span>' +
      /* the eyebrow already says LIVE with the tally; a second chip
         repeating it is the duplication Cody's screenshot showed */
      reasonChips(m, live, isLive ? ['lv'] : null) +
      starPeek(m) +
      '<span class="wacts"><span class="wgo">Preview &rarr;</span>' +
        '<span class="wofficial" data-href="https://www.ncaa.com/game/' +
        esc(m.gid) + '">ncaa.com</span></span>' +
    '</a>';
  };

  const block = (title, note, bodyHtml) => bodyHtml
    ? '<section class="tdblock"><h3>' + title +
      (note ? '<span>' + note + '</span>' : '') + '</h3>' + bodyHtml + '</section>'
    : '';

  todayBox.innerHTML =
    block('Your next watches',
          watches.length ? 'next 7 days &middot; why each is here' : '',
          watches.length
            ? '<div class="wgrid">' + watches.map(watchCard).join('') + '</div>'
            : '<p class="tdquiet">No ranked or televised match in the next seven '
              + 'days. Everything still being recorded is on the '
              + '<a href="' + routeFor('scores') + '">scoreboard</a>.</p>') +
    block('Big weekend ahead', weekend.length + ' more ranked or televised',
          weekend.length
            ? '<div class="tdlist">' +
              weekend.map(x => matchRow(x[0], liveOf(x[0]), 'desk')).join('') +
              '</div>' : '') +
    block('Results that changed the picture',
          changed.length ? 'a ranked side lost or went five' : '',
          changed.length
            ? '<div class="tdlist">' +
              changed.map(m => matchRow(m, liveOf(m), 'scores')).join('') +
              '</div>' : '') +
    /* GAMEDAY-CALL2-BEGIN */ (typeof gdPanel === 'function' ? gdPanel() : '') + /* GAMEDAY-CALL2-END */
    /* ⚠ THE PRIVATE CRITERION IS FENCED. The rule is printed so a reader can
       argue with his own landing page -- but one of the criteria names a
       private feature, and the public gate caught it here twice. */
    '<p class="tdrule">Shown here: AVCA Top 25 pairings &middot; a ranked side ' +
      '&middot; on TV' +
      /* MYBOARD-WIRE-BEGIN */ ' &middot; My Board' + /* MYBOARD-WIRE-END */
      ' &middot; AVCA/POWER disagreement of 8 ' +
      'or more. Everything else in Division I is still recorded &mdash; ' +
      '<a href="' + routeFor('scores') + '">scoreboard</a> &middot; ' +
      '<a href="' + routeFor('schedule') + '">full schedule</a>.</p>';

  document.getElementById('desksooncards').innerHTML = '';
  document.getElementById('desksoonmeta').textContent = '';
  document.getElementById('desksoonrest').textContent = '';
  return;

  /* ONE FEATURED MATCH AT MOST, and only if it earns it. */
  const feat = pickFeatured(mine, liveOf);
  let html = /* GAMEDAY-CALL-BEGIN */ (typeof gdPanel === 'function' ? gdPanel() : '') + /* GAMEDAY-CALL-END */
             todaysRead(mine, soon, liveOf);
  if (feat) {
    /* ⚠ THE RIBBON STAYS. It is the score header this page has one definition
       of, and replacing it would reopen settled scope. The Moment sits BESIDE
       it as the poster treatment -- one featured match, two renderings of the
       same data through the same helpers, so they cannot disagree. Sparing by
       design: exactly one Moment on this screen, on the match already chosen
       by a stated rule. */
    html += '<div class="deskfeat">' +
      momentHTML(feat.m, liveOf(feat.m), { nolink: true, dest: 'desk' }) +
      '<div class="deskfeatside">' +
        ribbonHTML(feat.m, liveOf(feat.m), '<b>Featured:</b> ' + feat.why) +
      '</div></div>';
  }
  /* ⚠ A FULL MATCH DAY IS 195 FIXTURES, AND THE BOARD WAS PRINTING ALL OF
     THEM. Measured on a stubbed Friday: 206 rows, a 13,593px page -- about ten
     screens, and the "Coming up" lane alone was 155 undifferentiated rows.
     That is precisely the wall the Scores ledger exists to absorb, reappearing
     on the rundown. Each lane now shows the ones that sort first and says
     exactly how many it is not showing, with the way to see them.
     The payload is ordered ranked-v-ranked, then any ranked side, then how
     close the forecast is -- so the cap keeps the matches a reader came for,
     and the line below it makes the omission visible rather than silent.
     LIVE IS NEVER CAPPED: if six matches are in progress, all six are on. */
  const LANE_CAP = { live: 0, final: 8, up: 10 };
  const lane = (key, cls, label, rows) => {
    if (!rows.length) return '';
    const cap = LANE_CAP[key] || 0;
    const shownRows = cap ? rows.slice(0, cap) : rows;
    const hidden = rows.length - shownRows.length;
    return '<div class="lane ' + cls + '"><div class="lanehd"><b>' + label +
      '</b><span>' + rows.length + '</span></div>' +
      shownRows.map(m => matchRow(m, liveOf(m), 'desk')).join('') +
      (hidden
        ? '<p class="lanemore">' + hidden + ' more ' +
          (key === 'final' ? 'finished' : 'scheduled') + ' today &mdash; ' +
          '<a href="' + routeFor('scores') + '">the Scores ledger has ' +
          'every one</a>.</p>'
        : '') + '</div>';
  };
  /* the featured match is not repeated in its own lane -- the ribbon already
     carries its scoreline, and printing it twice is the thing the old board
     did that made everything look equally important */
  const notFeat = r => r.filter(m => !feat || m.gid !== feat.m.gid);
  html += lane('live', 'live', 'Live now', notFeat(lanes.live));
  html += lane('final', 'final', 'Just finished', notFeat(lanes.final));
  html += lane('up', 'up', 'Coming up', notFeat(lanes.up));
  todayBox.innerHTML = html;

  const shown = soon.slice(0, DESK_SOON_SHOWN);
  document.getElementById('desksooncards').innerHTML =
    shown.length ? '<div class="lane up"><div class="lanehd"><b>Next few days</b>' +
      '<span>' + soon.length + ' scheduled</span></div>' +
      shown.map(m => matchRow(m, null, 'desk')).join('') + '</div>'
    : '<p class="emptylane">Nothing scheduled in the next few days.</p>';
  document.getElementById('desksoonmeta').textContent = '';
  document.getElementById('desksoonrest').textContent =
    soon.length > shown.length
      ? (soon.length - shown.length) + ' more in the next week — the Schedule tab has all of them.'
      : '';

  Object.keys(LMC_OPEN).forEach(id => { if (LMC_DATA[id]) lmcRender(id); });
  if (typeof mbRenderAll === 'function') mbRenderAll();
}

/* One delegated listener rather than one per card -- the cards are replaced on
   every poll, and per-card handlers would be re-bound (and leak) each time. */
document.addEventListener('click', ev => {
  const b = ev.target.closest ? ev.target.closest('[data-lmc]') : null;
  if (!b) return;
  ev.preventDefault();
  lmcToggle(b.getAttribute('data-lmc'));
});

/* Live is an UPGRADE, never a requirement. On a static host the fetch fails and
   the desk stays a pregame board rather than an error. */
async function deskLive() {
  try {
    const r = await fetch('/api/live');
    const j = await r.json();
    LIVE_STAMP = j.updated || '';
    LIVE_BY_ID = {};
    (j.games || []).forEach(g => { LIVE_BY_ID[String(g.id)] = g; });
  } catch (e) {
    LIVE_BY_ID = {};
  }
  renderDesk();
  /* COURTSIGNAL-CALL-BEGIN */ csTape(); csStatus(); /* COURTSIGNAL-CALL-END */
  /* ⚠ THE SCOREBOARD WAS THE ONE VIEW THE POLL NEVER TOLD. renderDesk(), the
     rally tape and the open match detail were all refreshed when live data
     landed; the Scores list was not. So Florida-Nebraska finished 2-0, the
     masthead rail said FINAL, and the lane underneath still read SCHEDULED
     with no score and would have until the reader touched a filter.
     Cody saw exactly that and called the page a mess. It was. */
  if (typeof renderScoreboard === 'function') renderScoreboard();
  /* ⚠ AND THE LEDGER, WHICH IS THE SAME BUG ONE VIEW ACROSS. The note above
     says the Scoreboard was "the one view the poll never told" -- it was not.
     The full-season ledger reads the identical matchState(m, LIVE_BY_ID[...])
     and renders once at load, BEFORE the first poll returns, so with an empty
     LIVE_BY_ID every finished-but-not-yet-crawled match lands in the
     `upcoming` lane. Measured tonight: the ledger headed two matches that had
     been final for hours "STILL TO COME", and a forced re-render immediately
     changed it to "FINAL TODAY 2". On a match day the view whose own summary
     promises "every fixture and result" is the one that is wrong.
     Only when it is OPEN: it can hold 1,594 rows and rebuilding them into a
     collapsed <details> every 60 seconds is work nobody can see. It renders on
     open too, so a reader never sees the stale state either way. */
  const _lg = document.querySelector('details.sbfull');
  if (_lg && _lg.open && typeof renderLedger === 'function') renderLedger();
  /* ⚠ AND THE OPEN TEAM PAGE -- the THIRD member of the same family. Its
     "Next match" card reads matchState(m, LIVE_BY_ID[...]) and renders on
     route entry, which on a fresh load is BEFORE the first poll returns -- so
     Michigan's page said "Next match - 3:00 PM PT - 99% to win" while
     Michigan was mid-2nd-set, and nothing ever told it. Re-render only the
     team actually open; teamDossier() is idempotent by checking for its own
     nav, so this cannot double-build. */
  const _tm = (location.hash || '').match(/^#\/teams\/([^/]+)$/);
  if (_tm && typeof unslugTeam === 'function' &&
      typeof showTeam === 'function') {
    const _tn = unslugTeam(decodeURIComponent(_tm[1]));
    if (_tn) showTeam(_tn);
  }
  /* ⚠ THE DETAIL MUST RE-EVALUATE WHEN LIVE DATA LANDS. deskLive() is async and
     resolves AFTER the router has already painted, so a match that is live on
     the feed rendered as "upcoming" -- no Live stats section, no timer -- and
     nothing ever asked again. Re-render the open match, and only that one. */
  const open = (location.hash || '').replace(/^#\/?/, '').split('?')[0]
    .split('/').filter(Boolean);
  const view = VIEW_OF_ROUTE[open[0]];
  if ((view === 'desk' || view === 'scores') && open[1]) {
    renderMatchDetail(decodeURIComponent(open[1]),
                      view === 'scores' ? 'scores' : 'desk');
  }
}

renderStandings();
renderWeek();
/* the router is booted after TEAMS exists -- see the note at that call */

/* ---- date navigation on the scores tab --------------------------------- */
const sdate = $$('sdate');
function filterByDate() {
  const d = sdate.value;
  let n = 0;
  document.querySelectorAll('#v-scores .cards .card[data-gid]').forEach(c => {
    const txt = (c.querySelector('.cd') || {}).textContent || '';
    const show = !d || txt.indexOf(d) === 0;
    c.style.display = show ? '' : 'none';
    if (show) n++;
  });
  $$('dcnt').textContent =
    d ? (n + ' on ' + d) : '';
}
sdate.addEventListener('input', filterByDate);
$$('sclear').addEventListener('click', () => {
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
/* ⚠ ONE SENTENCE PER RULER, AND A VIEW CANNOT SHIP WITHOUT ONE. The tab
   showed five rank tables whose numbers looked identical -- a row could read
   "#1 #1 #1 #1 #1" -- with nothing on screen saying whose ruler each was.
   Keyed by view id, asserted by a guard. */
const RULER_WHAT = {
  ours: '<b>POWER</b> is our own predictive order: how strong a team is, ' +
        'who would win tomorrow. Margin drives it. It is not a poll and ' +
        'nobody votes in it.',
  avca: '<b>AVCA coaches poll</b> is the external poll voted by coaches and ' +
        'published by the American Volleyball Coaches Association. It is ' +
        'shown for reference and does not feed anything here.',
  digby: '<b>Digby\u2019s Top 25</b> is this site\u2019s own Top 25, blending ' +
         'the preseason projection with 2026 results. It is not the AVCA poll ' +
         'and it is not anybody\u2019s ballot.',
  gap: '<b>POWER vs AVCA</b> lists where our order and the coaches poll ' +
       'currently differ most. It is a statement of difference, nothing more.',
  cal: '<b>Weekly calendar</b> is the archive: what each ranking said, and ' +
       'when. Separate tracks \u2014 our own weekly freeze, the official ' +
       'coaches poll, and any community poll entered by hand \u2014 kept ' +
       'apart because they are different rulers on different cadences.',
  top16: '<b>DI Committee top 16</b> is the selection committee\u2019s own ' +
         'in-season reveal \u2014 the closest published thing to what the ' +
         'field projector is trying to predict.',
  rpi: '<b>NCAA RPI</b> is the NCAA\u2019s published Rating Percentage Index. ' +
       'External reference.'
};

/* ---- POWER vs AVCA ---------------------------------------------------------
   ⚠ A DIFFERENCE, NOT A VERDICT. This surface says only how far apart two
   published orders are for the same team. It does not say either is wrong, it
   ranks nobody as overrated or underrated, and it recommends no movement --
   the two rulers answer different questions and are MEANT to disagree (R3).
   ⚠ AND A TEAM THE POLL DOES NOT RANK HAS NO GAP. The poll is 25 deep; a team
   outside it has no position, and subtracting an absent number from a real one
   would invent a difference. Those teams are listed separately as AVCA NR with
   no number attached. */
function gapRows() {
  const rated = [], nr = [];
  Object.keys(TEAMS).forEach(nm => {
    const t = TEAMS[nm];
    if (!t || !t.rank) return;
    if (t.avca === null || t.avca === undefined) {
      if (t.rank <= 25) nr.push({ team: nm, rank: t.rank });
    } else {
      rated.push({ team: nm, rank: t.rank, avca: t.avca,
                   gap: Math.abs(t.rank - t.avca) });
    }
  });
  rated.sort((a, b) => b.gap - a.gap || a.rank - b.rank);
  nr.sort((a, b) => a.rank - b.rank);
  return { rated: rated, nr: nr };
}

function renderGap() {
  const host = document.getElementById('pollview');
  const g = gapRows();
  const q = (document.getElementById('gapq') || {}).value || '';
  const ql = q.toLowerCase().trim();
  const keep = r => !ql || r.team.toLowerCase().includes(ql);
  const rated = g.rated.filter(keep), nr = g.nr.filter(keep);
  const row = r =>
    '<tr data-team="' + esc(r.team) + '" tabindex="0" role="link">' +
    '<td class="tm">' + logo(r.team) + esc(r.team) + '</td>' +
    '<td class="n"><i class="rl">POWER</i>#' + r.rank + '</td>' +
    '<td class="n"><i class="rl">AVCA</i>#' + r.avca + '</td>' +
    '<td class="n gapn">' + r.gap + '</td></tr>';
  const nrRow = r =>
    '<tr data-team="' + esc(r.team) + '" tabindex="0" role="link">' +
    '<td class="tm">' + logo(r.team) + esc(r.team) + '</td>' +
    '<td class="n"><i class="rl">POWER</i>#' + r.rank + '</td>' +
    '<td class="n"><span class="nrtag">AVCA NR</span></td>' +
    '<td class="n dim">no gap</td></tr>';
  host.innerHTML =
    '<div class="gapwrap">' +
    '<div class="ctl"><input type="search" id="gapq" placeholder="Search a team\u2026" ' +
      'value="' + esc(q) + '"><span class="count">' + rated.length +
      (rated.length === 1 ? ' team' : ' teams') + ' ranked by both</span></div>' +
    '<div class="panel"><div class="scroll"><table class="gaptbl">' +
    '<thead><tr><th class="l">Team</th><th>POWER</th><th>AVCA</th>' +
    '<th title="how many places apart the two orders put this team">Differs by</th>' +
    '</tr></thead><tbody id="gapbody">' +
    (rated.length ? rated.slice(0, 30).map(row).join('')
                  : '<tr><td colspan="4" class="tnote">No team is ranked by ' +
                    'both right now.</td></tr>') +
    '</tbody></table></div></div>' +
    (nr.length
      ? '<div class="tsec"><h3>In our top 25, not in the coaches poll</h3>' +
        '<div class="body"><div class="panel"><div class="scroll">' +
        '<table class="gaptbl"><tbody>' + nr.map(nrRow).join('') +
        '</tbody></table></div></div>' +
        /* one literal: a sentence split across a concatenation never appears
           contiguously in the built page, so a guard cannot find it */
        '<div class="tnote">The coaches poll is 25 deep. A team outside it has no position there, so no difference is calculated for these \u2014 an absent rank is not a low one.</div></div></div>'
      : '') +
    '</div>';
  const gq = document.getElementById('gapq');
  if (gq) gq.addEventListener('input', () => {
    const v = gq.value; renderGap();
    const n = document.getElementById('gapq');
    if (n) { n.focus(); n.setSelectionRange(v.length, v.length); }
  });
  host.querySelectorAll('tr[data-team]').forEach(tr => {
    const open = () => { if (TEAMS[tr.dataset.team]) go(routeFor('teams', slug(tr.dataset.team))); };
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });
  });
}

/* ---- THE WEEKLY CALENDAR ---------------------------------------------------
   ⚠ THREE TRACKS, NEVER BLENDED. Digby Weekly is DERIVED and frozen on our own
   Sunday cutoff; AVCA is OFFICIAL and we only capture it; the third track is
   COMMUNITY and arrives by hand. Movement is computed only inside a track --
   the archive already refuses to compare across bases and this view must not
   reintroduce that through the back door. Nothing here is combined into a
   consensus, because a consensus of three different questions is not an
   answer to any of them. */
const CAL = {{CALENDAR_JSON}};

/* ⚠ EACH CELL CARRIES ITS COLUMN NAME. On a phone the header row is dropped
   and the row becomes a stack, so an unlabelled cell reads as a bare "-" or a
   bare "not stated" with nothing saying which column it came from. Same fix as
   the rank strip: the label rides in front of the value via data-l. */
function calRow(cells, cols, cls) {
  return '<tr' + (cls ? ' class="' + cls + '"' : '') + '>' +
    cells.map((c, i) => '<td data-l="' + esc((cols && cols[i]) || '') + '">' +
                        c + '</td>').join('') + '</tr>';
}

function renderCalendar() {
  const host = document.getElementById('pollview');
  const w = CAL.waiting;
  /* THE ACTIVE WEEK, said first and said plainly. */
  let head = '';
  if (w) {
    /* ⚠ THREE STATES ON THE FACE OF IT, and "publishable" is not "complete".
       A week whose only gap is fixtures the SOURCE withdrew can be published,
       but it is not a week where every scheduled match was played, and it
       does not get to claim that. */
    const cls = w.blocking ? 'wait' : (w.withdrawn ? 'okw' : 'ok');
    const counts =
      '<div class="calcounts">' +
      '<span><b>' + w.finals + '</b> final' + (w.finals === 1 ? '' : 's') +
      ' included</span>' +
      (w.withdrawn
        ? '<span title="Fixtures the source itself no longer lists for their ' +
          'date, each evidenced by the saved scoreboard for that date. They ' +
          'are excluded, never deleted."><b>' + w.withdrawn +
          '</b> source-withdrawn excluded</span>' : '') +
      '<span class="' + (w.blocking ? 'bad' : '') + '"><b>' + w.blocking +
      '</b> unresolved</span>' +
      '</div>';
    /* Blockers grouped, with a couple of examples each -- not a wall. */
    const groups = Object.keys(w.why || {});
    const list = groups.length
      ? '<ul class="calblock">' + groups.map(k =>
          '<li><span class="calwhy ' + esc(k) + '">' + esc(k) + '</span>' +
          '<b>' + w.why[k] + '</b>' +
          ((w.examples || {})[k] || []).map(x =>
            '<i>' + esc(x) + '</i>').join('') +
          (w.why[k] > ((w.examples || {})[k] || []).length
            ? '<i class="more">+' +
              (w.why[k] - ((w.examples || {})[k] || []).length) + ' more</i>'
            : '') + '</li>').join('') + '</ul>'
      : '';
    head =
      '<div class="calnow ' + cls + '">' +
      '<div class="calnowhead"><span class="caltag derived">Derived</span>' +
      '<b>' + esc(w.label) + '</b>' +
      '<span class="calstate ' + esc(w.state) + '">' +
      esc(String(w.state).replace(/_/g, ' ')) + '</span></div>' +
      counts + list +
      (w.blocking
        ? '<p class="calfine">Nothing partial is saved. A fixture the source ' +
          'has <b>withdrawn</b> no longer blocks \u2014 that is evidenced from ' +
          'the saved scoreboard for its date. Anything above is genuinely ' +
          'unresolved, not merely old.</p>'
        : (w.frozen
            ? '<p class="calfine">Frozen and archived.</p>'
            : '<p class="calfine">Ready to freeze on the next Monday run.</p>')) +
      (w.policy
        ? '<p class="calfine">Disposition policy <code>' + esc(w.policy) +
          '</code>.</p>' : '') +
      '</div>';
  }

  const track = (key, name, tag, tagcls, cols, rows, empty) =>
    '<div class="caltrack"><div class="calhead">' +
    '<span class="caltag ' + tagcls + '">' + tag + '</span><h3>' + name +
    '</h3></div>' +
    (rows.length
      ? '<div class="panel"><div class="scroll"><table class="caltbl">' +
        '<thead><tr>' + cols.map(c => '<th>' + c + '</th>').join('') +
        '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div></div>'
      : '<div class="tnote">' + empty + '</div>') +
    '</div>';

  /* DIGBY WEEKLY -- ours, derived. */
  const DG_COLS = ['Week', 'Through', 'Teams', 'Finals', 'Withdrawn', 'State'];
  const dg = (CAL.digby || []).slice().reverse().map(r => calRow([
    esc(r.label),
    r.cutoff ? esc(r.cutoff) : '<span class="dim">not stated</span>',
    r.n + ' team' + (r.n === 1 ? '' : 's') +
      (r.partial ? ' <b class="calwarn" title="This early archive stored only ' +
        'the displayed Top 25 plus also-receiving, so movement cannot be ' +
        'computed for the rest of the field. It is kept exactly as written.">' +
        'partial</b>' : ''),
    r.finals === null || r.finals === undefined
      ? '<span class="dim">&ndash;</span>' : r.finals,
    r.withdrawn === null || r.withdrawn === undefined
      ? '<span class="dim">&ndash;</span>' : r.withdrawn,
    r.legacy
      ? '<span class="calstate legacy" title="Written before the weekly ' +
        'cutoff rule existed. Kept exactly as archived.">archived</span>'
      : '<span class="calstate ' + esc(r.completeness || '') + '">' +
        esc(r.completeness || '') + '</span>',
  ], DG_COLS));

  /* AVCA -- official, theirs. Both dates, because they are different facts. */
  const AV_COLS = ['Through games', 'Captured by this hub', 'Size', 'Season'];
  const av = (CAL.avca || []).slice().reverse().map(r => calRow([
    esc(r.stamp || 'no stamp'),
    r.captured ? esc(String(r.captured).replace('T', ' ').replace('Z', ' UTC'))
               : '<span class="dim">&ndash;</span>',
    r.n + ' ranked',
    r.prev_season
      ? '<span class="calstate legacy">previous season</span>'
      : '<span class="calstate complete">this season</span>',
  ], AV_COLS));

  /* VOLLEYTALK -- community, by hand, and honest about being empty. */
  const VT_COLS = ['Published', 'Through', 'Size', 'Source'];
  const vt = (CAL.vt || []).map(r => calRow([
    esc(r.published || '?'),
    esc(r.through || '?'),
    r.n + ' ranked',
    r.url ? '<a href="' + esc(r.url) + '" rel="noopener noreferrer" ' +
            'target="_blank">thread</a>' : '<span class="dim">&ndash;</span>',
  ], VT_COLS));

  host.innerHTML = '<div class="calwrap">' + head +
    track('digby', 'Digby Weekly', 'Derived', 'derived',
          DG_COLS, dg,
          'No weekly freeze yet.') +
    track('avca', 'AVCA coaches poll', 'Official', 'official',
          AV_COLS, av,
          'No AVCA capture yet. The rankings endpoint is current-only, so a ' +
          'poll is captured on the day it publishes or not at all.') +
    (CAL.vt
      ? track('vt', esc(CAL.vt_name), esc(CAL.vt_tag), 'community',
              VT_COLS, vt,
              esc(CAL.vt_empty))
      : '') +
    '</div>';
}

function renderPoll(which) {
  const host = document.getElementById('pollview');
  const main = document.getElementById('rankpanel');
  const lead = document.getElementById('ranklead');
  document.querySelectorAll('#v-rankings .segb').forEach(b =>
    b.classList.toggle('on', b.dataset.r === which));
  /* The reference select shows a choice only while one of ITS views is up, so
     it never looks like the active ruler when POWER is. */
  const rp = document.getElementById('refpick');
  if (rp) rp.value = (which === 'top16' || which === 'rpi') ? which : '';
  /* Say which ruler this is, always. */
  const rw = document.getElementById('rulerwhat');
  if (rw) { rw.innerHTML = RULER_WHAT[which] || ''; rw.hidden = !RULER_WHAT[which]; }
  /* ⚠ DIGBY'S TOP 25 IS A RANKING, SO IT LIVES WITH THE RANKINGS. As a
     top-level tab it competed with Rankings for the same job and a reader had
     to know which of two destinations answered "who is best". The section is
     moved into this tab at load and shown as one of its views. */
  const t25 = document.getElementById('v-top25');
  if (t25 && t25.parentNode !== document.getElementById('v-rankings')) {
    document.getElementById('v-rankings').appendChild(t25);
  }
  if (t25) t25.hidden = (which !== 'digby');
  if (which === 'digby') {
    host.hidden = true; main.hidden = true; lead.hidden = true; return;
  }
  if (which === 'ours') {
    host.hidden = true; main.hidden = false; lead.hidden = false; return;
  }
  if (which === 'gap') {
    main.hidden = true; lead.hidden = true; host.hidden = false;
    renderGap(); return;
  }
  if (which === 'cal') {
    main.hidden = true; lead.hidden = true; host.hidden = false;
    renderCalendar(); return;
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
  b.addEventListener('click', () => {
    renderPoll(b.dataset.r);
    const want = routeFor('rankings', b.dataset.r === 'ours' ? 'power'
                                                        : b.dataset.r);
    if (location.hash !== want) history.replaceState(null, '', want);
  }));

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
    '<tr class="prow" data-p="' + i + '" data-k="' +
      esc(r.team + '|' + r.name) + '"><td class="rk">' + (i + 1) + '</td>' +
    '<td class="tm">' + playerCell(r, 34) + '</td>' +
    '<td class="cf">' + logo(r.team) + r.team + '</td>' +
    '<td class="n">' + r.sets + '</td>' +
    hcell(k === 'hit' ? r.hit : r[k],
          k === 'hit' ? r.hit.toFixed(3) : r[k].toFixed(2),
          lo, hi, 'high', 'seq') + '</tr>').join('');
  document.getElementById('lcnt').textContent =
    rows.length + (rows.length === 1 ? ' player' : ' players');
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
      /* ⚠ THE ROW SAYS IT, NOT ONLY THE NOTE UNDERNEATH. Norfolk St. ranks
         2nd in points/set and 1st in fewest points allowed -- both off ONE
         Division-II match. The panel note already warned that non-D-I
         opponents are not filtered out, but a blanket sentence under a sorted
         table does not say WHICH row it means, and the row is what a reader
         compares. */
      '<td class="tm">' + logo(r.team) + esc(r.team) +
      ((d.nondi || 0) > 0
        ? '<b class="nondi" title="' +
          nonDiPhrase(d.nondi, d.matches, 'in this sample') + '. ' +
          NONDI_WHY + '">non-D-I</b>'
        : '') + '</td>' +
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
function openPlayer(name, team, from) {
  const key = s => (s || '').toLowerCase().replace(/[^a-z]/g, '');
  const p = PLAYERS.find(x => key(x.name) === key(name) && key(x.team) === key(team));
  if (!p) return false;
  /* ⚠ ROUTED, NOT TOGGLED. It used to click the Players tab and paint the
     card, which left no history entry -- Back went to whatever came before the
     whole tab, and a refresh lost the player entirely. */
  go(routeFor('players', slug(p.team) + '/' + slug(p.name)) +
     (from ? '?from=' + from : ''));
  return true;
}
document.addEventListener('click', e => {
  const row = e.target.closest('#teamcard .rrow[data-player]');
  if (!row) return;
  const team = (document.querySelector('#teamcard .thead h2') || {}).textContent || '';
  openPlayer(row.dataset.player, team.trim(), 'teams');
});
document.getElementById('lbody').addEventListener('click', e => {
  const tr = e.target.closest('tr.prow');
  if (!tr || !tr.dataset.k) return;
  const parts = tr.dataset.k.split('|');
  openPlayer(parts[1], parts[0], 'stats');
});

['lq','lstat','lside'].forEach(id =>
  document.getElementById(id).addEventListener('input', renderStats));
renderLeaders();

/* ---- team page ---- */
const TEAMS = {{TEAMS_JSON}};
/* BALLOT-INIT-BEGIN */
/* the workshop reads TEAMS, so it is started here rather than at its
   definition -- see the temporal-dead-zone note on bwWire() */
if (typeof bwWire === 'function') bwWire();
/* the desk reads DESK and TEAMS; both are initialised by here */
if (typeof deskLive === 'function') deskLive();
/* BALLOT-INIT-END */
/* ⚠ THE ROUTER BOOTS HERE, NOT AT ITS DEFINITION, AND THIS WAS A LIVE BUG.
   route() reads TEAMS (unslugTeam) and `const TEAMS` is declared near the end
   of this script, so booting earlier threw "Cannot access 'TEAMS' before
   initialization" -- which aborted the rest of boot. A direct load or refresh
   of #/teams/<slug> therefore left the team panel EMPTY, while the same route
   reached by clicking worked, because TEAMS existed by then. I saw a symptom
   of this in the routing phase (an empty team header on direct load) and
   wrongly blamed the crest element.
   ⚠ AND IT MUST STAY OUTSIDE THE BALLOT SENTINEL ABOVE: that block is stripped
   from the public build, and routing is not private. */
if (!location.hash) { history.replaceState(null, '', routeFor('desk')); }
route();
if (typeof mbRenderAll === 'function') mbRenderAll();
/* COURTSIGNAL-CALL2-BEGIN */
/* Painted at boot from the static payload, then repainted whenever the live
   poll lands. TWO CALL SITES, ONE FUNCTION -- the tape can never be a
   different opinion from the lanes underneath it. */
try { csTape(); csStatus(); } catch (e) { }
/* COURTSIGNAL-CALL2-END */
const dl = document.getElementById('tmlist');
Object.keys(TEAMS).sort().forEach(n => {
  const o = document.createElement('option'); o.value = n; dl.appendChild(o);
});
function chip(label, val, cls) {
  if (val === null || val === undefined || val === '') return '';
  return '<span class="chip ' + (cls || '') + '">' + label + ' <b>' + val + '</b></span>';
}
/* ══ SCOUT'S READ ═════════════════════════════════════════════════════════
   The same sentences Digby wrote, in two parts: the first two up front, the
   rest behind a disclosure.

   ⚠ NOTHING HERE IS REWRITTEN, SUMMARISED OR RE-RANKED. It is a SPLIT, at a
   sentence boundary, of text that was already checked figure by figure against
   the source before it was stored. Compressing prose by generating new prose
   would mean a fresh set of claims that no gate has ever seen -- and the gate
   is the whole reason this text is trustworthy. If a shorter note is wanted,
   it has to come from digby.py, through the gate, not from here.

   ⚠ AND THE PROVENANCE LINE STAYS VISIBLE, not tucked inside the disclosure.
   It is the sentence that says what the note is and how it was checked; a
   reader who never opens the full note still needs it. */
/* ══ SPLIT A NOTE INTO SENTENCES ══════════════════════════════════════════
   ⚠ A PERIOD BETWEEN DIGITS IS A DECIMAL POINT, NOT A FULL STOP, and the first
   version of this did not know that. Nebraska's note says "Murray led the team
   at 4.215 points per set and Jackson added 3.472, and both are returning" --
   split naively, the lead ended mid-number and the remainder opened with
   "472, and both are returning". A number that never existed, in the same
   confident voice as the real ones, on the summary most likely to be the only
   thing a reader reads.
   Exactly the shape of the Digby gate reading the hyphen in a 23-7 record as a
   minus sign: one punctuation mark doing two jobs, and the pattern knowing
   about only one of them.
   A scanner rather than a regex, because the condition is contextual: a
   terminator counts only when it is not between digits AND what follows it is
   whitespace or the end of the note. */
function csSentences(text) {
  const out = [];
  let start = 0, i = 0;
  const isD = c => c >= '0' && c <= '9';
  const CLOSERS = '.!?")]\u201d\u2019';
  while (i < text.length) {
    const c = text[i];
    if (c !== '.' && c !== '!' && c !== '?') { i++; continue; }
    if (c === '.' && isD(text[i - 1] || '') && isD(text[i + 1] || '')) {
      i++; continue;                      /* 4.215 -- a decimal point */
    }
    let j = i + 1;
    while (j < text.length && CLOSERS.indexOf(text[j]) >= 0) j++;
    if (j >= text.length) { out.push(text.slice(start)); start = text.length; break; }
    if (!/\s/.test(text[j])) { i++; continue; }
    out.push(text.slice(start, j));
    start = j;
    while (start < text.length && /\s/.test(text[start])) start++;
    i = start;
  }
  if (start < text.length) out.push(text.slice(start));
  return out.filter(x => x.trim());
}

/* ══ NAMES IN PROSE BECOME PEOPLE ═════════════════════════════════════════
   ⚠ SCOPED TO ONE ROSTER, AND EXACT. A brief on Nebraska's page may name
   "Harper Murray"; linking that to whichever Murray a global search hits first
   is the wrong-person match R8 exists for, and it would be invisible -- the
   link would look fine and go to a stranger. So the candidate set is ONLY the
   players the payload holds FOR THIS TEAM, matched on the full name, longest
   first so "Bergen Reilly" is never clipped to a shorter overlapping name.

   ⚠ AND IT RUNS ON TEXT, NOT MARKUP. The brief is plain prose from digby.py;
   inserting anchors and then matching again would let a later name land inside
   an earlier href. Each name is consumed once, left to right. */
/* ---- PLAYER RATINGS -------------------------------------------------------
   WITHIN POSITION ONLY. There is deliberately no cross-position board: a box
   score gives a libero digs and a middle blocks, and nothing in it licenses
   ranking one against the other. Each board also prints how well the data
   supports it, measured rather than asserted. */

function prkFmt(f, v) {
  if (v === null || v === undefined) return '—';
  return f === 'hit' ? (v < 0 ? '-' : '') + Math.abs(v).toFixed(3).replace(/^0/, '')
                     : v.toFixed(2);
}

/* ⚠ CONFIDENCE IS THE SAMPLE, NOT A PERCENTAGE WE INVENT. It states how much
   of the rating this season carries and how thin that season is -- both
   measured -- rather than a made-up confidence score. */
function prkConf(r) {
  if (!r.m) {
    return r.hp
      ? '<span class="munk">last season only · ' + (r.ps || 0) + ' sets</span>'
      : '<span class="munk">no prior season on record</span>';
  }
  const pct = Math.round(100 * (r.w || 0));
  return '<b>' + pct + '%</b> <span class="munk">of the rating · ' +
    r.m + (r.m === 1 ? ' match' : ' matches') +
    (r.hp ? '' : ' · no prior') + '</span>';
}

function prkDrivers(r) {
  if (!r.drv || !r.drv.length) return '<span class="munk">—</span>';
  return r.drv.map(d =>
    '<span class="prkd' + (d.c < 0 ? ' neg' : '') + '">' +
    esc(PRK_FLAB[d.f] || d.f) + ' <b>' + prkFmt(d.f, d.v) + '</b></span>'
  ).join('');
}

/* ⚠ PASSING IS LAST SEASON'S AND THE CHIP SAYS SO. The play-by-play mirror
   runs to 2025 and there is no live route for this season, so a side-out rate
   here describes last year. Letting it sit unlabelled beside this season's
   rates would read as current form. */
function prkPass(r) {
  const p = r['pass'];
  if (!p) return '';
  const bits = [];
  if (p.recv_share != null) {
    bits.push('<span class="prkp">passes <b>' +
      Math.round(p.recv_share * 100) + '%</b> of serve-receive</span>');
  }
  if (p.sideout != null) {
    bits.push('<span class="prkp">sides out <b>' +
      Math.round(p.sideout * 100) + '%</b> when she passes</span>');
  }
  if (p.touch_per_set != null) {
    bits.push('<span class="prkp">touches <b>' +
      p.touch_per_set.toFixed(1) + '</b>/set</span>');
  }
  /* Reported only for outside, opposite and setter. A middle shares her
     rotation slot with the libero, so the serve order cannot say which of the
     two was on court -- classified that way a libero comes out 41.8% front
     row, which cannot happen. */
  if (r.brs != null) {
    bits.push('<span class="prkp"><b>' + Math.round(r.brs * 100) +
      '%</b> of her swings from the back row</span>');
  }
  if (!bits.length) return '';
  return '<div class="prkpass">' + bits.join('') +
    '<span class="munk">2025</span></div>';
}

function prkRow(r) {
  const overall = PRK_POS === 'ALL';
  const rank = overall ? r.orank : (PRK_MODE === 'resume' ? r.rsr : r.pwr);
  const val = overall ? r.pct : (PRK_MODE === 'resume' ? r.rs : r.pw);
  const shown = val === null || val === undefined ? '—'
    : (overall ? val.toFixed(1) : (val > 0 ? '+' : '') + val.toFixed(2));
  /* ⚠ THE BOARDS WERE A DEAD END. A reader who finds the best middle in the
     country could not click her -- the team was a link and the player was
     plain text, so the one thing the board is FOR had no way out of it. */
  return '<tr class="prkrow" data-pk="' + esc((r.t || '') + '|' + (r.n || '')) +
    '" tabindex="0">' +
    '<td class="prknum">' + (rank == null ? '—' : rank) + '</td>' +
    '<td class="l tm"><b>' + esc(r.n || '') + '</b>' +
      (r.num ? ' <span class="munk">#' + esc(String(r.num)) + '</span>' : '') +
      (overall ? ' <span class="prkpos">' + esc(r.pos) + '</span>' : '') +
      (r.role ? ' <span class="prkrolet">' +
        esc(PRK_ROLELAB[r.role] || r.role) + '</span>' : '') +
      (r.prole ? ' <span class="prkrolet alt">' +
        esc(PRK_PROLELAB[r.prole] || r.prole) + '</span>' : '') +
    '</td>' +
    '<td class="l tm">' + logo(r.t, 'sm') +
      '<a class="parentlink" href="' + routeFor('teams', slug(r.t || '')) +
      '">' + esc(r.t || '') + '</a></td>' +
    '<td>' + esc(r.cls || '—') + '</td>' +
    '<td class="prkval">' + shown + '</td>' +
    '<td class="prkconf">' + prkConf(r) + '</td>' +
    '<td class="l prkdrv">' + prkDrivers(r) + prkPass(r) + '</td>' +
    '</tr>';
}

function renderPrank() {
  const posbar = $$('prkpos'), modebar = $$('prkmode'), sup = $$('prksupport');
  const body = $$('prkbody'), cnt = $$('prkcnt');
  if (!body) return;
  if (!PRANK || !PRANK.ok) {
    sup.innerHTML = '<div class="prkcav">Player ratings have not been built ' +
      'yet. Run <code>scripts/player_rating.py</code>.</div>';
    body.innerHTML = ''; return;
  }
  posbar.innerHTML = PRK_ORDER.map(p => {
    const b = PRANK.boards[p] || {};
    const lab = p === 'ALL' ? 'Overall'
      : (b.label || p).replace('Libero / DS', 'Libero/DS');
    return '<button type="button" data-p="' + p + '"' +
      (p === PRK_POS ? ' class="on"' : '') + '>' + esc(lab) + '</button>';
  }).join('');
  /* ⚠ SIX-ROTATION AND FRONT-ROW PINS ARE DIFFERENT JOBS. An outside who
     passes every rotation and one who is replaced in the back row are not
     doing the same thing, so their dig and reception numbers are not
     comparable and the board offers the split rather than averaging over it. */
  const rolebar = $$('prkrole');
  const roles = PRK_ROLES[PRK_POS];
  if (roles) {
    rolebar.hidden = false;
    rolebar.innerHTML = roles.map(r =>
      '<button type="button" data-r="' + r[0] + '"' +
      (r[0] === PRK_ROLE ? ' class="on"' : '') + '>' + esc(r[1]) +
      '</button>').join('');
  } else {
    rolebar.hidden = true; rolebar.innerHTML = ''; PRK_ROLE = '';
  }
  const b = PRANK.boards[PRK_POS] || {};
  let rows = (PRK_POS === 'ALL'
    ? (PRANK.overall_rows || []) : (PRANK.rows[PRK_POS] || [])).slice();
  if (PRK_ROLE) rows = rows.filter(r => r.role === PRK_ROLE);
  /* ⚠ THE RESUME BOARD DROPS ANYONE WITH NO SEASON LINE RATHER THAN RANKING
     HER LAST. Last is a claim; absent is the truth. */
  const list = PRK_MODE === 'resume'
    ? rows.filter(r => r.rs !== null && r.rs !== undefined)
          .sort((a, b2) => a.rsr - b2.rsr)
    : rows.sort((a, b2) => a.pwr - b2.pwr);
  if (PRK_POS === 'ALL') {
    const ov = PRANK.overall || {};
    sup.innerHTML = '<div class="prkcav sup-fair">' +
      '<span class="prkbadge">STANDING, NOT VALUE</span> ' +
      'Ranked by <b>percentile within her own position</b>. ' + esc(ov.note || '') +
      '</div>';
    cnt.textContent = list.length + ' shown';
    body.innerHTML = list.map(prkRow).join('');
    renderStars();
    return;
  }
  sup.innerHTML =
    '<div class="prkcav sup-' + esc(b.support || 'fair') + '">' +
    '<span class="prkbadge">' + esc((b.support || '').toUpperCase()) +
    ' SUPPORT</span> ' + esc(b.caveat || '') +
    ' <span class="munk">Measured: this board separates All-Americans from ' +
    'their peers at ' + ((b.support_auc || 0).toFixed(3)) +
    ' AUC among players on comparable teams.</span></div>';
  cnt.textContent = list.length
    ? list.length + ' shown of ' + (b.n || 0) + ' rated'
    : 'nobody has a ' + (PRK_MODE === 'resume' ? 'season line' : 'rating') +
      ' yet';
  body.innerHTML = list.map(prkRow).join('');
  renderStars();
}

/* The constructed teams. ⚠ NOT AN AWARD AND IT SAYS SO ON THE PANEL: this is
   the position boards read in order and poured into a lineup. A slot nobody
   can fill renders VACANT rather than borrowing from another position. */
function renderStars() {
  const el = $$('prkstars');
  if (!el) return;
  const st = PRANK && PRANK.all_star;
  if (!st) { el.innerHTML = ''; return; }
  const NAMES = { 1: 'First team', 2: 'Second team', 3: 'Third team' };
  function slot(x) {
    if (!x.p) return '<div class="star vac"><span class="spos">' +
      esc(x.pos) + '</span><span class="munk">vacant</span></div>';
    return '<div class="star"><span class="spos">' + esc(x.pos) + '</span>' +
      '<span class="sname">' + esc(x.p.n) + '</span>' +
      '<span class="steam">' + logo(x.p.t, 'sm') + esc(x.p.t || '') + '</span>' +
      '<span class="spw">' + (x.p.pw > 0 ? '+' : '') +
      (x.p.pw || 0).toFixed(2) + '</span></div>';
  }
  function prof(p) {
    if (!p) return '';
    const bits = [];
    if (p.block_front !== null) bits.push('blocks <b>' + p.block_front.toFixed(2) + '</b>/set');
    if (p.kill !== null) bits.push('kills <b>' + p.kill.toFixed(2) + '</b>/set');
    if (p.hit !== null) bits.push('hits <b>' + p.hit.toFixed(3).replace(/^0/, '') + '</b>');
    if (p.dig !== null) bits.push('digs <b>' + p.dig.toFixed(2) + '</b>/set');
    if (p.serve !== null) bits.push('aces <b>' + p.serve.toFixed(2) + '</b>/set');
    return '<div class="sprof">' + bits.join(' · ') +
      (p.vacant ? ' <span class="munk">· ' + p.vacant + ' vacant</span>' : '') +
      '</div>';
  }
  el.innerHTML =
    '<h3 class="prkh">Best available lineups</h3>' +
    /* ⚠ THE LITERAL YEAR, NOT THE JS CONSTANT. The season guard reads the
       BUILT PAGE, and `+ SEASON_YEAR +` leaves no four-digit year in it -- so
       a view that names its season perfectly well at runtime still failed. */
    '<p class="lead munk">' + esc(PBP_CREDIT) + '</p>' +
    '<p class="lead">The best lineups available for the {{SEASON_YEAR}}' +
    ' season, built by reading each position board in order and filling a six ' +
    'plus the libero. <b>These are constructed, not voted on</b> — nobody ' +
    'selected them, and no player here is being compared with a player at ' +
    'another position.</p>' +
    st.teams.map(t =>
      '<div class="starteam"><div class="sthead">' + esc(NAMES[t.tier] || ('Team ' + t.tier)) +
      ' <span class="munk">' + esc(t.system) + '</span></div>' +
      '<div class="stgrid">' + t.slots.map(slot).join('') + '</div>' +
      prof(t.profile) + '</div>').join('') +
    (st.alt ? '<div class="starteam alt"><div class="sthead">First team, as a ' +
      esc(st.alt.system) +
      ' <span class="munk">two setters, no opposite — a different team, ' +
      'not a re-sort</span></div>' +
      '<div class="stgrid">' + st.alt.slots.map(slot).join('') + '</div>' +
      prof(st.alt.profile) + '</div>' : '') +
    '<div class="starteam hm"><div class="sthead">Honourable mention ' +
    '<span class="munk">by position</span></div>' +
    PRK_ORDER.map(p => {
      const v = (st.hm && st.hm[p]) || [];
      if (!v.length) return '';
      return '<div class="hmrow"><span class="spos">' + esc(p) + '</span>' +
        v.map(x => x ? '<span class="hmn">' + esc(x.n) +
          ' <span class="munk">' + esc(x.t || '') + '</span></span>' : '').join('') +
        '</div>';
    }).join('') + '</div>';
}

function wirePrank() {
  const posbar = $$('prkpos'), modebar = $$('prkmode');
  if (posbar) posbar.addEventListener('click', e => {
    const b = e.target.closest('button[data-p]');
    if (!b) return;
    PRK_POS = b.getAttribute('data-p'); PRK_ROLE = ''; renderPrank();
  });
  const rolebar = $$('prkrole');
  if (rolebar) rolebar.addEventListener('click', e => {
    const b = e.target.closest('button[data-r]');
    if (!b) return;
    PRK_ROLE = b.getAttribute('data-r'); renderPrank();
  });
  if (modebar) modebar.addEventListener('click', e => {
    const b = e.target.closest('button[data-m]');
    if (!b) return;
    PRK_MODE = b.getAttribute('data-m');
    [...modebar.querySelectorAll('button')].forEach(x =>
      x.classList.toggle('on', x === b));
    renderPrank();
  });
}

function nameCandidates(team, t) {
  /* ⚠ TWO SOURCES, BECAUSE ONE OF THEM IS EMPTY IN AUGUST. PLAYERS is built
     from 2026 box scores, so before a team has played it holds nothing for
     her -- and the briefs name players on all 348 teams. The projected six
     carries the rest: team, class, position, number, last season's points and
     her transfer line.
     A PLAYERS entry WINS when both have her, because that one has a real page
     behind it. Both are already scoped to this team, so the R8 wrong-person
     match is structurally impossible here. */
  const out = [];
  const seen = Object.create(null);
  if (typeof PLAYERS !== 'undefined') {
    PLAYERS.forEach(p => {
      if (p.team === team && p.name && !seen[p.name]) {
        seen[p.name] = 1;
        out.push({ name: p.name, p: p, six: null });
      }
    });
  }
  const six = ((t || {}).lineup || {}).usual_six_2025 || [];
  six.forEach(c => {
    if (c && c.name && !seen[c.name]) {
      seen[c.name] = 1;
      out.push({ name: c.name, p: null, six: c });
    }
  });
  return out;
}

/* A name in a brief resolves one of two ways, and the difference is real:
   she has a 2026 player page, or she does not. A page exists only once she has
   a box-score line, so in August most named players have none. The old code
   linked every name to a players route regardless -- which for an unplayed
   team is a link to nothing.
   ⚠ SO: a real page gets an anchor. Everyone else gets a BUTTON that opens a
   card built from what we actually hold -- team, class, position, number, last
   season's points, where she transferred from, and video search. No page is
   invented and no stat is stood in for. */
function nameChip(best, team) {
  const nm = esc(best.name);
  if (best.p) {
    const p = best.p;
    return '<a class="pname" href="' +
      routeFor('players', slug(p.team) + '/' + slug(p.name)) +
      '" title="' + esc(p.name + ' \u00b7 ' + p.team +
        (p['class'] ? ' \u00b7 ' + p['class'] : '') +
        (p.pos ? ' \u00b7 ' + p.pos : '') + ' \u2014 open her page') + '">' +
      nm + '</a>';
  }
  return '<button type="button" class="pname pname-brief" ' +
    'data-nteam="' + esc(team) + '" data-nname="' + esc(best.name) + '" ' +
    'aria-haspopup="dialog" title="' + esc(best.name + ' \u2014 who is this') +
    '">' + nm + '</button>';
}

/* The card for a player with no 2026 page yet. Every row is omitted when the
   field is absent -- there is no zero, no dash-shaped placeholder standing
   where a measurement belongs, and the header says plainly that she has not
   played this season rather than showing an empty stat block (R5). */
function briefCard(c, team) {
  const face = c.photo
    ? '<img class="npface" src="' + c.photo + '" alt="">'
    : avatar(c.pos, team, 48);
  /* ⚠ A DEPARTED PLAYER IS NOT ON THIS ROSTER, AND THE SUBTITLE MUST NOT READ
     AS THOUGH SHE IS. She still appears in the team's 2025 six -- that is what
     the record is -- so the school is stamped with the season it belongs to.
     Class is a 2026 roster field, so it is omitted entirely for someone who is
     no longer on it rather than shown against the wrong year. */
  const gone = c.status_2026 === 'departed';
  const sub = [
    '<a class="parentlink" href="' + routeFor('teams', slug(team)) + '">' +
      esc(team) + '</a>' + (gone ? ' <span class="munk">2025</span>' : ''),
    (!gone && c.class_2026) ? esc(c.class_2026) : null,
    c.pos ? esc(c.pos) : null,
    c.num ? '#' + esc(String(c.num)) : null
  ].filter(Boolean).join(' \u00b7 ');
  const rows = [];
  if (c.pts_2025 != null) {
    rows.push('<div class="nprow"><span class="pxlab">2025</span>' +
      '<span class="pxstat">' + esc(String(c.pts_2025)) + ' points' +
      (c.starts_2025 ? ' \u00b7 ' + esc(String(c.starts_2025)) + ' starts' : '') +
      '</span></div>');
  } else if (c.starts_2025) {
    rows.push('<div class="nprow"><span class="pxlab">2025</span>' +
      '<span class="pxstat">' + esc(String(c.starts_2025)) +
      ' starts</span></div>');
  }
  if (c.status_2026) {
    rows.push('<div class="nprow"><span class="pxlab">2026</span>' +
      '<span class="pxstat">' + esc(String(c.status_2026)) + '</span></div>');
  }
  if (c.went_to) {
    rows.push('<div class="nprow"><span class="pxlab">Moved to</span>' +
      '<a class="parentlink" href="' + routeFor('teams', slug(c.went_to)) +
      '">' + esc(c.went_to) + '</a></div>');
  }
  if (c.xf && c.xf.from_team) {
    rows.push('<div class="nprow"><span class="pxlab">Transfer</span>' +
      '<a class="parentlink" href="' + routeFor('teams', slug(c.xf.from_team)) +
      '">' + esc(c.xf.from_team) + '</a>' +
      (c.xf.prior_pts && c.xf.prior_sets
        ? '<span class="pxstat">' +
          (c.xf.prior_pts / c.xf.prior_sets).toFixed(2) +
          ' pts/set there over ' + esc(String(c.xf.prior_sets)) + ' sets</span>'
        : '<span class="pxstat munk">no prior D-I line on record</span>') +
      '</div>');
  }
  const q = encodeURIComponent(c.name + ' ' + team + ' volleyball highlights');
  const vid = '<div class="pvid"><span class="pxlab">Video</span>' +
    '<a href="https://www.youtube.com/results?search_query=' + q + '" ' +
    'target="_blank" rel="noopener noreferrer">Search YouTube</a>' +
    '<a href="https://www.google.com/search?tbm=vid&q=' + q + '" ' +
    'target="_blank" rel="noopener noreferrer">Search video</a>' +
    '<span class="munk">a search, not a verified reel</span></div>';
  return '<div class="nphead">' + face + '<div><div class="npname">' +
    esc(c.name) + '</div><div class="sub">' + sub + '</div></div>' +
    '<button type="button" class="npx" aria-label="Close">\u00d7</button></div>' +
    '<div class="npbody">' + rows.join('') + vid +
    '<div class="munk npfoot">' + (gone
      ? 'She is not on the 2026 roster, so there is no season page for her ' +
        'here. Everything above is her 2025 record at ' + esc(team) + '.'
      : 'No 2026 match line yet, so there is no season page for her. ' +
        'Everything here is last season\u2019s record and her roster listing.') +
    '</div></div>';
}

let NAMEPOP = null;
function closeNamePop() {
  if (NAMEPOP && NAMEPOP.parentNode) { NAMEPOP.parentNode.removeChild(NAMEPOP); }
  NAMEPOP = null;
}
function openNamePop(btn) {
  closeNamePop();
  const team = btn.getAttribute('data-nteam');
  const name = btn.getAttribute('data-nname');
  const cand = nameCandidates(team, (typeof TEAMS !== 'undefined' ? TEAMS[team] : null));
  let hit = null;
  cand.forEach(x => { if (x.name === name && x.six) hit = x.six; });
  if (!hit) return;
  const el = document.createElement('div');
  el.className = 'namepop';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', name);
  el.innerHTML = briefCard(hit, team);
  document.body.appendChild(el);
  NAMEPOP = el;
  /* Positioned from the button's MEASURED box, then pulled back inside the
     viewport -- a card anchored near the right edge would otherwise hang off
     the page, and on a phone it would be entirely unreachable. */
  const r = btn.getBoundingClientRect();
  const w = el.offsetWidth;
  let left = r.left + window.scrollX;
  const maxL = window.scrollX + document.documentElement.clientWidth - w - 10;
  if (left > maxL) left = maxL;
  if (left < window.scrollX + 10) left = window.scrollX + 10;
  let top = r.bottom + window.scrollY + 7;
  if (r.bottom + el.offsetHeight + 14 > window.innerHeight && r.top > el.offsetHeight) {
    top = r.top + window.scrollY - el.offsetHeight - 7;
  }
  el.style.left = left + 'px';
  el.style.top = top + 'px';
  const x = el.querySelector('.npx');
  if (x) x.addEventListener('click', function () { closeNamePop(); btn.focus(); });
}
document.addEventListener('click', function (e) {
  const b = e.target.closest && e.target.closest('.pname-brief');
  if (b) { e.preventDefault(); openNamePop(b); return; }
  if (NAMEPOP && !(e.target.closest && e.target.closest('.namepop'))) closeNamePop();
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && NAMEPOP) closeNamePop();
});

function linkNames(text, team, t) {
  if (!text) return '';
  const roster = nameCandidates(team, t);
  if (!roster.length) return esc(text);
  const byLen = roster.slice().sort((a, b) => b.name.length - a.name.length);
  const parts = [];
  let rest = String(text);
  let guard = 0;
  while (rest && guard++ < 400) {
    let best = null, at = -1;
    byLen.forEach(pl => {
      const i = rest.indexOf(pl.name);
      if (i >= 0 && (at < 0 || i < at)) { at = i; best = pl; }
    });
    if (!best) break;
    parts.push(esc(rest.slice(0, at)));
    parts.push(nameChip(best, team));
    rest = rest.slice(at + best.name.length);
  }
  parts.push(esc(rest));
  return parts.join('');
}

/* ⚠ THE TEAM NAME IS PASSED IN, NOT READ OFF THE RECORD. TEAMS is keyed by
   name and its records carry no `name`/`team` field, so the first version's
   `t.name || t.team || ''` was always the empty string -- the roster filter
   matched nobody and every brief rendered with zero links and no error.
   A silent no-op, which is the failure mode this project keeps paying for. */
/* ---- PARTS VS WHOLE, ROTATIONS, AND WHAT A TEAM RETURNS ------------------
   ⚠ ALL THREE ARE LAST SEASON AND EVERY ONE SAYS SO IN ITS OWN HEADING. The
   play-by-play mirror ends at 2025 and there is no live route, and the
   parts-vs-whole gap is only honest on a COMPLETED season: this season's team
   projection is built from last season's production, so comparing the two
   would be circular and the gap would measure nothing. */

function partsHTML(t) {
  const p = t.parts;
  if (!p) return '';
  const r = p.residual, sd = p.residual_sd;
  /* ⚠ THE VERDICT IS BUILT FROM THE NUMBER, NOT BEFORE IT (R1). And the band
     is stated rather than implied: inside one standard deviation is not a
     finding, it is noise, and the copy says so instead of dressing it up. */
  let verdict, cls;
  if (sd == null) { verdict = ''; cls = ''; }
  else if (sd >= 1) { verdict = 'beat what its roster predicted'; cls = 'over'; }
  else if (sd <= -1) { verdict = 'fell short of what its roster predicted'; cls = 'under'; }
  else { verdict = 'landed about where its roster predicted'; cls = 'level'; }
  return '<div class="tsec partsbox"><h3>Parts vs whole ' +
    '<span class="munk">2025</span></h3><div class="body">' +
    '<div class="partsrow ' + cls + '">' +
      '<span class="pv">' + (r > 0 ? '+' : '') + r.toFixed(2) + '</span>' +
      '<span class="pl">net points/set vs its players’ forecast</span>' +
    '</div>' +
    '<p class="tnote">Its top ' + p.rated_players + ' rated players forecast ' +
      p.predicted.toFixed(2) + '; it actually rated ' + p.actual.toFixed(2) +
      ', so it ' + verdict + (sd == null ? '' :
      ' (' + (sd > 0 ? '+' : '') + sd.toFixed(1) + ' SD)') + '.</p>' +
    '<p class="tnote munk">What the gap is, we do not claim. The obvious ' +
      'explanation — that rotation rules punish an unbalanced roster ' +
      '— was tested and failed: at equal average a team with one dominant ' +
      'hitter does <b>better</b>, not worse, and rotation imbalance predicts ' +
      'nothing at all. So this is reported as unexplained rather than ' +
      'attributed to something it might not be.</p>' +
    '</div></div>';
}

function retposHTML(t) {
  const rp = t.retpos;
  if (!rp) return '';
  const rows = PRK_ORDER.filter(x => x !== 'ALL').map(pos => {
    const v = rp[pos];
    if (!v) return '';
    /* ⚠ A POSITION WITH NO RECORDED PRODUCTION RENDERS AS UNKNOWN, NOT 0%.
       Zero percent returning reads as "they lost everyone there", which is a
       claim the data has not made. */
    const sh = v.share;
    const pct = sh == null ? null : Math.round(sh * 100);
    return '<div class="rprow">' +
      '<span class="rplab">' + esc(POSFULL[pos] || pos) + '</span>' +
      (pct == null
        ? '<span class="munk">not recorded</span>'
        : '<span class="rpbar"><i style="width:' + pct + '%"></i></span>' +
          '<span class="rppct">' + pct + '%</span>') +
      '<span class="munk">' + v.n_returning + ' back' +
        (v.n_departed ? ', ' + v.n_departed + ' gone' : '') + '</span>' +
      '</div>';
  }).join('');
  if (!rows) return '';
  return '<div class="tsec"><h3>What it returns, by position ' +
    '<span class="munk">2025 production</span></h3><div class="body">' +
    rows + '<p class="tnote munk">Share of last season’s points at each ' +
    'position that is back on the roster. One number for the whole squad ' +
    'hides the difference between losing a setter and losing a middle.</p>' +
    '</div></div>';
}

function rotsoHTML(t) {
  const doc = t.rotso;
  if (!doc || !doc.rotations) return '';
  const r = doc.rotations;
  const keys = ['1', '2', '3', '4', '5', '6'].filter(k => r[k]);
  if (keys.length < 6) return '';
  const vals = keys.map(k => r[k].sideout);
  const lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  const cells = keys.map(k => {
    const v = r[k].sideout;
    const cls = v === hi ? ' best' : (v === lo ? ' worst' : '');
    return '<div class="rotcell' + cls + '">' +
      '<span class="rotlab">S' + esc(k) + '</span>' +
      '<span class="rotv">' + (v * 100).toFixed(0) + '%</span>' +
      '<span class="munk">' + r[k].att + '</span></div>';
  }).join('');
  /* ⚠ WHOSE ROTATIONS THESE ARE, AND HOW MUCH OF THE SEASON THEY COVER.
     S1..S6 names where the setter stands, so it only means one thing if it is
     ONE setter -- and 135 of 348 teams give their most-used setter under 70%
     of the sets. Naming her and stating the coverage is the difference between
     a rotation profile and an average of two different teams. */
  const pct = Math.round((doc.share_of_season || 0) * 100);
  return '<div class="tsec"><h3>Side-out by rotation ' +
    '<span class="munk">2025</span></h3><div class="body">' +
    '<div class="rotgrid">' + cells + '</div>' +
    '<p class="tnote">Rotations are named by where the setter stands — these ' +
    'are <b>' + esc(doc.setter || 'the primary setter') + '</b>’s, covering ' +
    pct + '% of the season’s rallies. The team ranged from <b>' +
    (lo * 100).toFixed(0) + '%</b> to <b>' + (hi * 100).toFixed(0) +
    '%</b> across the six.</p>' +
    (pct < 70 ? '<p class="tnote munk">⚠ She set under 70% of the season, so ' +
      'the rest of it ran through somebody else and is not shown here.</p>'
      : '') +
    '<p class="tnote munk">Scouting, not a rating. Rotation imbalance was ' +
    'measured against team strength and predicts nothing (correlation ' +
    '−0.09), so it is deliberately kept out of the model. These are ' +
    '<b>2025</b> rotations — there is no live source for them. A team does ' +
    'not field one fixed six: the median side used 29 different serve orders ' +
    'last season, which is why these are anchored on the setter rather than ' +
    'on a lineup.</p>' +
    '<p class="tnote munk">' + esc(PBP_CREDIT) + '</p>' +
    '</div></div>';
}

function scoutRead(t, team) {
  if (!t.digby) return '';
  const parts = csSentences(String(t.digby));
  let lead = '', i = 0;
  /* two sentences, or three if the first two are very short -- a stated rule,
     and the remainder is never dropped either way */
  /* ⚠ REJOIN WITH A SPACE. The scanner skips the whitespace BETWEEN sentences
     rather than carrying it, so concatenating the parts directly produced
     "...all on the roster.Murray led the team..." -- correct text, unreadable
     rendering. The separator has to be put back explicitly. */
  while (i < parts.length && (i < 2 || (i === 2 && lead.length < 190))) {
    lead += (lead ? ' ' : '') + parts[i]; i++;
  }
  const rest = parts.slice(i).join(' ').trim();
  /* ⚠ NOT DIGBY_FACE. That const is block-scoped to the region showTeam()
     lives in, so calling it from here threw `ReferenceError: DIGBY_FACE is not
     defined` -- and because the throw happened inside showTeam's assembly, the
     team card rendered COMPLETELY EMPTY on a direct route. Nothing on screen
     said why. Same family as the `const TEAMS` temporal-dead-zone bug this
     project already paid for: a scoping error that presents as a blank panel,
     not as an error.
     CS_DIGBY is the page-level constant, and it is correctly the empty string
     in the public build by the same substitution. */
  return '<div class="digby scoutread"><div class="digby-tag">' +
    (typeof CS_DIGBY === 'string' ? CS_DIGBY : '') + 'Scout\u2019s read</div>' +
    '<p>' + linkNames(lead.trim(), team, t) + '</p>' +
    (rest
      ? '<details class="scoutmore"><summary>Full scouting note</summary>' +
        '<p>' + linkNames(rest, team, t) + '</p></details>'
      : '') +
    '<div class="digby-note">Written from this team\u2019s own numbers on ' +
    'this page. Every figure in it was checked against the source before it ' +
    'was saved \u2014 anything that did not match was thrown away rather ' +
    'than shown.</div></div>';
}

function showTeam(name) {
  const t = TEAMS[name];
  const box = document.getElementById('teamcard');
  if (!t) { box.innerHTML = ''; return; }
  const results = (t.played || []).map(g => {
    const won = g.mine > g.theirs;
    const strip = (g.sets || []).map(s => s[0] + '-' + s[1]).join(', ');
    /* ⚠ A TEAM'S OWN RESULT OPENS THE MATCH. This row described a match and
       could not open it, while five other surfaces could -- so the one place a
       reader is most likely to want the detail was the one dead end. Same
       canonical route as every other entry point. */
    return '<div class="gline' + (g.gid ? ' gopen' : '') + '"' +
      (g.gid ? ' data-match="' + esc(g.gid) + '" data-dest="scores"' +
               ' tabindex="0" role="link"' : '') + '>' +
      '<span class="dt">' + dayLabel(g.d) + '</span>' +
      '<span class="va">' + (g.home ? 'vs' : '@') + '</span>' +
      '<span class="op">' + esc(g.opp) +
      (g.nondi ? '<b class="nondi" title="Not a Division-I opponent. This ' +
        'site does not filter these matches out -- filtering would change ' +
        'what every rate means without saying so -- so it is marked ' +
        'instead.">non-D-I</b>' : '') + '</span>' +
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
  /* ⚠ THE RECORD IS DIVISION-I-ONLY, THE SAME AS THE STANDINGS AND THE SAME
     AS THE NCAA'S OWN. This card counted every match, so Norfolk St. read
     "1-0, 1 played" here while its standings row read "Overall 0-0" -- one
     event, two views, two answers (R4). The non-D-I result is not thrown
     away; it is shown beside the record, which is exactly what the official
     RPI table does with its `Non-Div I` column. */
  const _di = _played.filter(g => !g.nondi);
  const _nd = _played.filter(g => g.nondi);
  const _w = _di.filter(g => g.mine > g.theirs).length;
  const _l = _di.length - _w;
  const _nw = _nd.filter(g => g.mine > g.theirs).length;
  const _nl = _nd.length - _nw;
  const glanceCard = (label, body, cls) =>
    '<div class="gl ' + (cls || '') + '"><span class="gll">' + label + '</span>' +
    body + '</div>';
  const glanceHtml = '<div class="glance">' +
    glanceCard('Record 2026',
      _played.length
        ? '<b class="glbig">' + _w + '&ndash;' + _l + '</b>' +
          '<span class="gls">' + _di.length +
          (_di.length === 1 ? ' played' : ' played') +
          (_nd.length
            ? ' \u00b7 ' + _nw + '\u2013' + _nl + ' vs non-D-I'
            : '') + '</span>'
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
          _last.opp + ' &middot; ' + dayLabel(_last.d) + '</span>'
        : '<b class="glbig glmuted">&mdash;</b><span class="gls">first match to come</span>') +
    glanceCard('Next',
      _next
        ? '<b class="glnext">' +
          (_next.site === 'neutral' ? ICON_NEUTRAL + ' vs '
            : (_next.home ? 'vs ' : ICON_ROAD + ' at ')) +
          _next.opp + '</b>' +
          '<span class="gls">' + dayLabel(_next.d) + (_next.t ? ' &middot; ' + _next.t : '') +
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
    return '<div class="gline gl2"><span class="dt">' + dayLabel(f.d) + '</span>' +
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
    /* ⚠ TWO DECIMALS, LIKE EVERY OTHER POINTS-PER-SET ON THIS SITE. The value
       was printed raw, so a projection rendered as "5.572" beside "3.04" --
       inconsistent precision, and a third decimal on a PROJECTED quantity
       claims a resolution the fit does not have. Same measure, same
       rendering, everywhere (R4). */
    '</span><span class="rt">' + ppsFmt(c.adj !== undefined ? c.adj : c.rate) +
    '</span></div>').join('');
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
      'the same counts from the other side of the same box scores.' +
      /* ⚠ THE DIVISION OF THE OPPONENT, said where the rate is read. Stated
         only when it applies, and it names how much of the sample it is --
         "the only match" and "1 of 4" are different facts. */
      ((O.nondi || 0) > 0
        ? ' <b class="dicaveat">' + nonDiPhrase(O.nondi, O.matches, 'here') +
          '</b>, so these rates are not measured against Division-I ' +
          'competition. ' + NONDI_WHY
        : '') +
      '</div></div>';
  }
  /* ---- MATCH BY MATCH, THE TEAM AS A BOX-SCORE LINE --------------------
     Cody: "i want to see a team's points per set listed on their team page
     and stats per match and totals (kinda like players in a match is
     formatted)". Same table dress as the player box, same columns, and the
     numbers come from teamTotals() over the SAME BOXES payload the match
     view reads -- one definition, so this table and a clicked box score
     cannot disagree. A match whose box is not on file renders dashes, never
     a synthesized line (R5). Chronological, oldest first, like a log. */
  let mbmHtml = '';
  {
    const games = (t.played || []).slice().reverse();
    if (games.length && typeof BOXES !== 'undefined') {
      const agg = {k:0,e:0,ta:0,ast:0,digs:0,bs:0,ba:0,aces:0,pts:0,sets:0,n:0};
      const trs = games.map(g => {
        const mine = (BOXES[g.gid] || []).filter(r => r.team === name);
        const wl = (g.mine > g.theirs ? 'W' : 'L') + ' ' + g.mine + '\u2013' + g.theirs;
        const opp = (g.home ? 'v ' : 'at ') + g.opp +
          (g.nondi ? ' <i class="dicaveat" title="not a Division-I opponent">non-D-I</i>' : '');
        if (!mine.length) {
          return '<tr><td class="pn">' + g.d.slice(5) + '</td>' +
            '<td class="pn">' + opp + '</td><td>' + wl + '</td>' +
            '<td colspan="11" style="color:var(--ink3)">no box score on file</td></tr>';
        }
        const x = teamTotals(mine);
        agg.k += x.k; agg.e += x.e; agg.ta += x.ta; agg.ast += x.ast;
        agg.digs += x.digs; agg.bs += x.bs; agg.ba += x.ba; agg.aces += x.aces;
        agg.sets += x.sets; agg.n += 1;
        const earned = x.k + x.aces + x.bs + x.ba * 0.5;
        return '<tr data-match="' + g.gid + '" class="mbmr">' +
          '<td class="pn">' + g.d.slice(5) + '</td>' +
          '<td class="pn">' + opp + '</td><td>' + wl + '</td>' +
          '<td>' + x.sets + '</td><td>' + x.k + '</td><td>' + x.e + '</td>' +
          '<td>' + x.ta + '</td><td>' + pct(x.hit) + '</td><td>' + x.ast + '</td>' +
          '<td>' + x.digs + '</td><td>' + x.blk + '</td><td>' + x.aces + '</td>' +
          '<td>' + earned + '</td><td><b>' + (x.sets ? (earned / x.sets).toFixed(2) : '\u2014') + '</b></td></tr>';
      }).join('');
      const aBlk = agg.bs + agg.ba * 0.5;
      const aPts = agg.k + agg.aces + aBlk;
      const tot = agg.n
        ? '<tr class="btot"><td class="pn">Totals</td>' +
          '<td class="l">' + agg.n + (agg.n === 1 ? ' match' : ' matches') + '</td><td></td>' +
          '<td>' + agg.sets + '</td><td>' + agg.k + '</td><td>' + agg.e + '</td>' +
          '<td>' + agg.ta + '</td><td>' + pct(agg.ta ? (agg.k - agg.e) / agg.ta : null) + '</td>' +
          '<td>' + agg.ast + '</td><td>' + agg.digs + '</td><td>' + aBlk + '</td>' +
          '<td>' + agg.aces + '</td><td>' + aPts + '</td>' +
          '<td><b>' + (agg.sets ? (aPts / agg.sets).toFixed(2) : '\u2014') + '</b></td></tr>'
        : '';
      mbmHtml =
        '<div class="tsec" style="margin-top:14px"><h3>Match by match, 2026</h3>' +
        '<div class="scroll"><table class="box mbm"><thead><tr>' +
        '<th class="l">Date</th><th class="l">Opponent</th><th>Res</th>' +
        '<th>S</th><th>K</th><th>E</th><th>TA</th><th>Hit%</th><th>Ast</th>' +
        '<th>Digs</th><th>Blk</th><th>Aces</th><th>Pts</th><th>Pts/Set</th>' +
        '</tr></thead><tbody>' + trs + tot + '</tbody></table></div>' +
        '<div class="tnote"><b>Pts</b> are kills + blocks + aces, and the ' +
        'totals row recomputes hitting % and points per set from the summed ' +
        'counts \u2014 never by averaging the match rates. Click a row to ' +
        'open that match.</div></div>';
    }
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
    /* ⚠ THE LONG PROSE USED TO SIT HERE, ABOVE THE CREST. Opening a team page
       meant reading a paragraph before finding out whose page it was. Identity,
       ranks, record, form and next match come first; the scouting note follows
       them, compressed, with the full text one disclosure away. Moved, not
       cut -- see scoutRead(). */
    /* COURTSIGNAL-THEAD-BEGIN */
    /* PROGRAMME IDENTITY, from the school's own logo colour rather than a
       palette I chose. COLORS is the extracted map (373 of 384 teams); a team
       with no readable colour gets NO edge, not an invented hue -- the same
       rule crawl_team_colors.py already enforces for the avatars. */
    '<div class="thead cs-court cs-prog"' +
      (COLORS[name] ? ' style="--tc:' + esc(COLORS[name]) + '"' : '') +
      '><h2>' + logo(name, 'lg') + name + '</h2>' +
    /* COURTSIGNAL-THEAD-END */
    '<div class="sub">' + (t.conf || '') +
      (t.record25 ? ' \u00b7 ' + t.record25 + ' in 2025' : '') + '</div>' +
    /* ⚠ TWELVE CHIPS AT EQUAL WEIGHT SAY NOTHING ABOUT WHAT MATTERS. The
       header used to open with "Our 2026 #1, 2025 #1, AVCA #1, VT #1, Massey
       #1, RPI #1, Returning 70%, Proj wins..., Conf title..., Tournament...,
       In the Big Ten 1st of 18, Opp rank 68.1" -- five of the first six were
       OTHER PEOPLE'S RANKINGS, rendered identically to ours. A reader scanning
       it has to read all twelve to find the two that answer "how good are they"
       and "what have they earned".
       Three tiers now: our two rankings lead, the projection follows, and
       everything external or historical recedes into a labelled Context row. */
    '<div class="chiptiers">' +
      '<div class="chips tier1">' +
        chip('POWER', '#' + t.rank + (t.power != null ? ' \u00b7 ' + t.power : ''), 'ours pow') +
        chip('R\u00c9SUM\u00c9', t.resume_rank ? '#' + t.resume_rank : '\u2014', 'ours res') +
        (t.record26
          ? chip('2026', t.record26 +
                 (t.record26_nondi
                   ? ' <i class="nvd">+' + t.record26_nondi + ' nD1</i>' : ''),
                 'ours')
          : '') +
      '</div>' +
      (t.sim && t.sim.proj_wins_mean !== null
        ? '<div class="chips tier2">' +
            chip('Proj wins', t.sim.proj_wins_mean.toFixed(1) + ' (' +
                 t.sim.proj_wins_p10 + '\u2013' + t.sim.proj_wins_p90 + ')') +
            chip('Conf title', t.sim.conf_title_pct + '%') +
            chip('Tournament', t.sim.tournament_pct + '%') +
          '</div>'
        : '') +
      /* ⚠ SEVEN EQUAL CHIPS WERE A WALL, NOT A HIERARCHY. This row is
         reference: last season, four other people's rankings, and where the
         team sits in its league. As bordered pills they competed with POWER
         and the outlook above them, and the header carried thirteen chips in
         three tiers. As a fact strip -- small label over value, no borders --
         the same facts read in one pass and stop shouting. Values only; an
         absent one is dropped rather than rendered as an empty pill. */
      '<div class="vx-label">Context</div>' +
      '<div class="vx-facts">' +
        (function () {
          const f = [];
          const add = (k, v, sm) => {
            if (v === '' || v === null || v === undefined) return;
            f.push('<div><i>' + esc(k) + '</i><b' + (sm ? ' class="sm"' : '') +
                   '>' + v + '</b></div>');
          };
          add('2025', t.rank25 ? '#' + t.rank25 : '');
          add('AVCA poll', t.avca ? '#' + t.avca : '');
          add('VT', t.vt ? '#' + t.vt : '');
          add('Massey', t.massey ? '#' + t.massey : '');
          add('RPI', t.rpi ? '#' + t.rpi : '');
          add('Returning', t.ret !== null && t.ret !== undefined
                ? Math.round(t.ret * 100) + '%' : '');
          if (t.conf_pos && t.conf_size) {
            add('In the ' + (t.conf || 'conference'),
                ordinal(t.conf_pos) + ' of ' + t.conf_size, true);
          }
          if (t.sos) {
            add('Opponent rank', t.sos.mean_rank + ' avg' +
                (t.sos.top25 ? ' \u00b7 ' + t.sos.top25 + ' top-25' : ''), true);
          }
          return f.join('');
        })() +
      '</div>' +
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
    scoutRead(t, name) +
    partsHTML(t) + retposHTML(t) + rotsoHTML(t) +
    /* the POWER history, or an honest sentence saying why there is not one.
       Rendered server-side by trend.py so the rule about a same-basis series
       lives in exactly one place. */
    (TRENDS[name] || '') +
    '<div class="tcols">' +
      '<div>' +
        (results ? '<div class="tsec"><h3>Results</h3><div class="body">' + results +
                   '</div></div>' : '') +
        '<div class="tsec"' + (results ? ' style="margin-top:14px"' : '') +
          /* ⚠ THE PILL IS 8px CLEAR OF THE HEADING ON SCREEN, so this
             reads correctly to the eye. In the TEXT layer it did not: the
             heading's textContent was "Upcoming22", and a bare 22 beside a
             word does not say 22 of what. The count now names its own unit
             for a screen reader and for copied text, while the visible pill
             is unchanged. */
          '><h3>Upcoming<span class="cnt" role="text" aria-label="' +
          (t.fixtures || []).length + ' scheduled ' +
          ((t.fixtures || []).length === 1 ? 'fixture' : 'fixtures') + '">' +
          (t.fixtures || []).length +
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
        mbmHtml +
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
        /* same unlabelled-count fix as the Upcoming pill: "Full roster17"
           in the text layer, 17 of what. Visible pill unchanged. */
        '<span class="h3n" role="text" aria-label="' + rost.length +
        (rost.length === 1 ? ' player' : ' players') + '">' +
        rost.length + '</span></h3>' +
        '<div class="body rbody">' + rosterHtml + '</div>' +
        '<div class="tnote">Roster from the school\u2019s own site; position and ' +
        'production from official box scores. A <b>green bar</b> marks a player who ' +
        'started at least one match in 2025. A player with no Division-I record shows ' +
        '<b>&mdash;</b> rather than a number \u2014 about a fifth of a season\u2019s ' +
        'production comes from players like her, and we do not invent it.</div></div>'
      : '');
  /* ⚠ REORGANISE AFTER RENDERING, NOT INSTEAD OF IT. Everything above still
     builds exactly as it did; the dossier moves the finished sections into
     Overview / Matches / Roster / Numbers / Scouting / Outlook so the first
     screen answers who, how good, what next and who to watch. */
  teamDossier(box, t, name);
}
/* The sticky table headers offset themselves by the nav's real height; the tab
   row wraps on a narrow window, so this is measured rather than hard-coded. */
/* ══ THE TEAM DOSSIER ══════════════════════════════════════════════════════
   ⚠ A TEAM PAGE WAS 5,464 PIXELS OF EQUAL-WEIGHT REPORT -- 6.8 screens, 14
   sections, everything shouting at the same volume. Kentucky's page opened on
   "Parts vs whole 2025" and buried who was playing tonight three screens down.
   The information was good and the shape was wrong.

   ⚠ THIS REORGANISES THE RENDERED DOM RATHER THAN REWRITING THE ASSEMBLY.
   The assembly above is one 195-line concatenation carrying years of decisions
   and their reasoning; splitting it by hand is exactly the kind of edit that
   silently drops a branch. Every existing section is MOVED, not rebuilt, so
   nothing that was true a moment ago stops being true. */

function tdGroupOf(el) {
  const h = el.querySelector('h3');
  const txt = ((h && h.textContent) || '').trim();
  for (let i = 0; i < TD_MAP.length; i++) {
    if (TD_MAP[i][0].test(txt)) return TD_MAP[i][1];
  }
  return 'numbers';
}

/* ⚠ A REAL HEADSHOT OR HER INITIALS. Nothing else. No drawn likeness stands in
   for a photograph on a card that names a real person, and an empty frame is
   worse than initials because it reads as a failed image. */
function tdFace(nm, photo) {
  if (photo) {
    return '<img class="tdface" src="' + esc(photo) + '" alt="" ' +
      'onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),' +
      '{className:\'tdface tdinit\',textContent:this.dataset.i}))" ' +
      'data-i="' + esc(tdInitials(nm)) + '">';
  }
  return '<span class="tdface tdinit">' + esc(tdInitials(nm)) + '</span>';
}
function tdInitials(nm) {
  const p = String(nm || '').trim().split(/\s+/);
  return ((p[0] || ' ')[0] + (p.length > 1 ? (p[p.length - 1] || ' ')[0] : ''))
    .toUpperCase();
}

/* The one match a reader is deciding about: when, where, on what, and a way in. */
function tdNextMatch(t, name) {
  const today = new Intl.DateTimeFormat('en-CA',
    { timeZone: 'America/Los_Angeles' }).format(new Date());
  const fx = (t.fixtures || []).filter(f => f.d && f.d >= today);
  if (!fx.length) {
    return '<div class="tdnext empty"><span class="tdlab">Next match</span>' +
      '<p class="munk">No remaining fixture on file for this team.</p></div>';
  }
  const f = fx[0];
  const all = (typeof allMatches === 'function') ? allMatches() : {};
  const m = all[String(f.gid)] || null;
  const live = (typeof LIVE_BY_ID !== 'undefined') ? LIVE_BY_ID[f.gid] : null;
  const st = m ? matchState(m, live) : 'upcoming';
  const opp = f.opp || '';
  const where = f.site === 'neutral' ? 'neutral floor'
    : (f.home ? 'home' : 'away');
  const tv = m && m.tv ? m.tv : null;
  return '<div class="tdnext">' +
    '<span class="tdlab">' + (st === 'live' ? 'Playing now'
      : st === 'final' ? 'Most recent' : 'Next match') + '</span>' +
    '<a class="tdnextrow" href="' + matchRoute(f.gid, 'teams') + '">' +
      /* 'at Wisconsin' beside 'neutral floor - Pittsburgh' is a
         contradiction: 'at' claims their floor. Neutral gets 'v', the same
         connector rule the rest of the page uses. */
      '<span class="tdvs">' + (f.site === 'neutral' ? 'v '
                               : f.home ? 'vs ' : 'at ') + logo(opp, 'sm') +
        '<b>' + esc(opp) + '</b></span>' +
      /* ⚠ A CARD ABOUT A MATCH IN PROGRESS SAYS THE SCORE, NOT THE START
         TIME -- and NEVER the pre-match pick. "TODAY - 3:00 PM PT - 99% TO
         WIN" rendered beside a live match (Michigan, 2026-08-28): a
         simulator's PRE-match number sitting on a live card reads as a live
         win probability, which this site never shows. The pick
         is a statement about a match that has not started; the moment it has,
         the truthful line is the tally and the period. */
      '<span class="tdwhen">' + (st === 'live'
        /* ⚠ THE ONE LIVE PHRASING. This branch used to build its own
           "tally - period" line, so the dossier said "0-1 - 2ND SET" while
           every other surface also carried the current-set points (17-17).
           liveLine() is the single definition -- tally, period, current
           points when the feed supplies them, nothing invented when it
           does not. Caught by outside review, 2026-08-28. */
        ? (liveLine(m || f, live) || 'in progress')
        : st === 'final'
        ? (function () {
            const _sc = matchScore(m || f, live);
            return 'FINAL' + (_sc && _sc[0] !== null && _sc[0] !== undefined
                              ? ' ' + _sc[0] + '\u2013' + _sc[1] : '');
          })()
        : esc(dayLabel(f.d)) + (f.t ? ' &middot; ' + esc(f.t) : '')) +
        /* ⚠ THE MODEL'S PRE-MATCH PICK MOVED HERE FROM THE GLANCE STRIP,
           IT WAS NOT DROPPED. The strip's "Next" tile and this card said the
           same thing twice in one viewport; this card is the richer of the two
           (venue, broadcast), so the tile goes -- but only after the one
           number it carried that this card did not is carried here. Removing
           a tile before checking it is a strict subset is how a fact
           disappears in a tidy-up.
           ⚠ It is labelled, unlike the bare "93%" the strip showed: a naked
           percentage beside a start time invites being read as anything. It
           is the simulator's pre-match pick and says so. */
        (st === 'upcoming' && f.pick !== null && f.pick !== undefined
          ? ' &middot; <i class="tdpick" title="The season simulator\u2019s ' +
            'pre-match pick for this fixture.">' + Math.round(f.pick * 100) +
            '% to win</i>' : '') + '</span>' +
      (tv ? '<span class="tdtv">' + esc(tv) + '</span>' : '') +
    '</a>' +
    '<p class="tdwhere">' + esc(where) +
      (f.venue ? ' &middot; ' + esc(f.venue) : '') +
      (f.city ? ', ' + esc(f.city) : '') +
      (f.event ? ' &middot; ' + esc(f.event) : '') + '</p>' +
    (tv ? '' : '<p class="munk tdnotv">No broadcast listed for this fixture ' +
      '&mdash; that means unknown, not untelevised.</p>') +
    '</div>';
}

/* Two or three names, what each does, and a way to her page. */
function tdPlayers(t, name) {
  const stars = (t.stars || []).slice(0, 3);
  if (!stars.length) return '';
  const photoOf = {};
  (t.roster || []).forEach(r => { if (r.ph) photoOf[r.n] = r.ph; });
  return '<div class="tdknow"><span class="tdlab">Players to know</span>' +
    '<div class="tdpgrid">' + stars.map(x => {
      const bits = [];
      if (x.pos) bits.push(POSFULL[x.pos] || x.pos);
      if (x.cls) bits.push(x.cls);
      /* ⚠ THE RIGHT NUMBER FOR THE JOB, AND NEVER A NEGATIVE ZERO. A libero
         showed "-0.0 kills/set" -- schedule adjustment can push a
         non-attacker's kill rate a hair below zero, and rounding prints the
         sign. A defender leads with digs, a middle with blocks, everyone else
         with kills, and a rate that is not meaningfully above zero is simply
         left out rather than printed as nothing. */
      const line2 = [];
      /* posHeadline() is THE definition -- see its note; a second copy here is
         how the match preview kept the bug after the dossier was fixed */
      const head = posHeadline(x);
      if (head) line2.push(head);
      if (x.role === 'six') line2.push('all six rotations');
      if (x.recv != null && x.recv >= 0.15) {
        line2.push(Math.round(x.recv * 100) + '% of serve-receive');
      }
      return '<a class="tdpcard" href="' +
        routeFor('players', slug(name) + '/' + slug(x.n)) + '">' +
        tdFace(x.n, photoOf[x.n]) +
        '<span class="tdpn">' + esc(x.n) + '</span>' +
        '<span class="tdpm">' + esc(bits.join(' · ')) + '</span>' +
        (x.pct != null ? '<span class="tdppct">' + x.pct.toFixed(1) +
          '<i>percentile at her position</i></span>' : '') +
        (line2.length ? '<span class="tdpl">' + esc(line2.slice(0, 2).join(' · ')) +
          '</span>' : '') +
      '</a>';
    }).join('') + '</div>' +
    '<p class="munk">Ranked against her own position only, never across ' +
    'positions. Serve-receive and back-row share are 2025.</p></div>';
}

function teamDossier(box, t, name) {
  /* ⚠ THE STAMP ALONE IS NOT EVIDENCE THE WORK IS STILL THERE, and relying on
     it silently reverted the whole page. `dataset` lives on the #teamcard
     ELEMENT, which survives; what the stamp guards is the innerHTML, which the
     renderer replaces wholesale. So on team -> player -> Back the box was
     rebuilt with the flat 5,400px section wall, the stamp still read
     "Kentucky", this function returned early, and the reader got the old page
     back with no tabs and no Overview. Nothing errored -- the dossier simply
     was not there, which looks like it was never built rather than like a bug.
     The fix is to check for the thing itself: the nav only exists if the
     reorganisation survived the last render. */
  if (!box) return;
  if (box.dataset.dossier === name && box.querySelector('.tdnav')) return;
  /* every section that is not the identity block */
  const loose = [...box.children].filter(el =>
    el.classList.contains('tsec') || el.classList.contains('tcols') ||
    el.classList.contains('trend'));
  const sections = [];
  loose.forEach(el => {
    if (el.classList.contains('tcols')) {
      [...el.querySelectorAll(':scope > div > .tsec, :scope > .tsec')]
        .forEach(s => sections.push(s));
      [...el.children].forEach(col => {
        [...col.children].forEach(ch => {
          if (!ch.classList.contains('tsec')) sections.push(ch);
        });
      });
      el.remove();
    } else {
      sections.push(el);
    }
  });
  const scout = box.querySelector('.digby.scoutread');
  const panels = {};
  TD_GROUPS.forEach(g => {
    const d = document.createElement('div');
    d.className = 'tdpanel';
    d.setAttribute('data-tdp', g[0]);
    panels[g[0]] = d;
  });
  sections.forEach(el => {
    if (!el.parentNode && !el.isConnected) { /* already detached */ }
    panels[el.classList.contains('tsec') || el.classList.contains('trend')
      ? tdGroupOf(el) : 'numbers'].appendChild(el);
  });

  /* the Overview is assembled, not moved: it is the one thing that did not
     exist before */
  const ov = panels.overview;
  ov.insertAdjacentHTML('beforeend', tdNextMatch(t, name) + tdPlayers(t, name));
  /* The glance strip's "Next" tile is now a strict subset of the card above,
     down to the pre-match pick -- so it is removed rather than shown twice in
     the same viewport. If the card came back empty (no fixture on file) the
     tile is left alone, because then it is the only answer there is. */
  if (ov.querySelector('.tdnext:not(.empty)')) {
    box.querySelectorAll('.glance .gl').forEach(g => {
      const lab = g.querySelector('.gll');
      if (lab && lab.textContent.trim().toLowerCase() === 'next') g.remove();
    });
  }
  if (scout) ov.appendChild(scout);

  const nav = document.createElement('div');
  nav.className = 'tdnav';
  nav.setAttribute('role', 'tablist');
  nav.innerHTML = TD_GROUPS.filter(g => panels[g[0]].children.length)
    .map(g => '<button type="button" role="tab" data-tdt="' + g[0] + '"' +
      (g[0] === TD_TAB ? ' class="on" aria-selected="true"' :
       ' aria-selected="false"') + '>' + g[1] + '</button>').join('');
  box.appendChild(nav);
  TD_GROUPS.forEach(g => {
    if (!panels[g[0]].children.length) return;
    panels[g[0]].hidden = g[0] !== TD_TAB;
    box.appendChild(panels[g[0]]);
  });
  if (!nav.querySelector('[data-tdt="' + TD_TAB + '"]')) {
    TD_TAB = 'overview';
    const first = nav.querySelector('button');
    if (first) first.classList.add('on');
    if (panels.overview) panels.overview.hidden = false;
  }
  box.dataset.dossier = name;
}

document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.tdnav [data-tdt]');
  if (!b) return;
  TD_TAB = b.getAttribute('data-tdt');
  const box = b.closest('#teamcard');
  if (!box) return;
  box.querySelectorAll('.tdnav [data-tdt]').forEach(x => {
    const on = x === b;
    x.classList.toggle('on', on);
    x.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  box.querySelectorAll('[data-tdp]').forEach(p => {
    p.hidden = p.getAttribute('data-tdp') !== TD_TAB;
  });
  /* ⚠ SCROLL THE NAV INTO VIEW, NOT THE TOP. Jumping to the page top on a tab
     change hides the very control just used. */
  const nav = box.querySelector('.tdnav');
  if (nav) {
    const y = nav.getBoundingClientRect().top + window.scrollY -
      (parseFloat(getComputedStyle(document.documentElement)
        .getPropertyValue('--navh')) || 60) - 8;
    if (window.scrollY > y) window.scrollTo({ top: y });
  }
});

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
  document.getElementById('tmq').value = nm;
  go(routeFor('teams', slug(nm)));
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
let SCHED_ALL = false;

function filterSchedule() {
  const q = (document.getElementById('sq').value || '').toLowerCase().trim();
  const want = document.getElementById('srank').value;
  /* ⚠ A SEARCH REACHES EVERY FIXTURE, NOT JUST THE VISIBLE WINDOW. The
     initial 600 is a display window; the moment someone types, or narrows by
     rank, or presses the button, the window stops applying. Otherwise the
     page would answer "no such fixture" about a fixture it is holding. */
  const searching = !!q || want !== 'all';
  let shown = 0, hiddenBeyond = 0;
  document.querySelectorAll('#sbody tr').forEach(tr => {
    const cls = tr.className || '';
    const rankOk = want === 'all' ||
                   (want === 'one' && cls.includes('rkd')) ||
                   (want === 'both' && cls.includes('both'));
    const textOk = !q || tr.textContent.toLowerCase().includes(q);
    const beyond = tr.hasAttribute('data-beyond');
    const windowOk = SCHED_ALL || searching || !beyond;
    const show = rankOk && textOk && windowOk;
    tr.hidden = !show;
    if (show) shown++;
    else if (beyond && rankOk && textOk) hiddenBeyond++;
  });
  document.getElementById('scnt').textContent =
    shown + (shown === 1 ? ' fixture' : ' fixtures') +
    (hiddenBeyond ? ' \u00b7 ' + hiddenBeyond + ' more further out' : '');
  const btn = document.getElementById('schedall');
  if (btn) {
    btn.hidden = !hiddenBeyond && SCHED_ALL;
    btn.textContent = SCHED_ALL ? 'Show the next few weeks only'
                                : 'Show all ' + hiddenBeyond + ' later fixtures';
    btn.hidden = SCHED_ALL ? false : !hiddenBeyond;
  }
}
['sq', 'srank'].forEach(id =>
  document.getElementById(id).addEventListener('input', filterSchedule));
(function () {
  const b = document.getElementById('schedall');
  if (b) b.addEventListener('click', () => {
    SCHED_ALL = !SCHED_ALL; filterSchedule();
  });
})();
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
/* ⚠ NEVER OVER A SCORE (design review via Cody): on the working
   scoreboard the launcher is hidden entirely -- Digby is one tab away
   on Today and on every team page. */
body[data-view=scores] .asklaunch{display:none}
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
  /* ⚠ THIS READ A --bg TOKEN THAT HAS NEVER EXISTED. A phantom property
     falls back to inherited rather than erroring, so this input has been
     silently transparent instead of sitting on the panel colour. Found
     by the css-variable guard, not by looking at it. */
  border-radius:2px;background:var(--card);color:var(--ink);font:400 13.5px/1.3 var(--sans)}
.askform button{padding:8px 12px;border:1px solid var(--line);background:var(--alt);
  color:var(--ink);border-radius:2px;cursor:pointer;font:700 11px/1 var(--sans)}
@media (max-width:560px){.askwrap{right:8px;left:8px;bottom:8px;width:auto}
  /* ⚠ ICON-ONLY ON A PHONE, AND IT LIVES HERE, NOT IN THE SHARED BLOCK.
     The first version put these two rules in the page-wide 560px block, and
     the public gate ABORTED the build: "asklaunch, digby-face" -- dead CSS
     naming a private feature is still the private feature's name on a public
     page. Digby styling belongs inside Digby's own stripped region.
     The full-width pill sat on top of card content in Cody's screenshot; a
     fixed button always overlays SOMETHING, so make the something small. The
     accessible name survives (the text is present at zero size). */
  .asklaunch{right:8px;bottom:8px;font-size:0;padding:12px;border-radius:50%;
    letter-spacing:0}
  .asklaunch .digby-face{width:24px;height:24px;margin:0;display:block}}
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
      /* ⚠ AN UNAVAILABLE SERVICE DISABLES ITS COMPOSER. Leaving the box live
         invites the same question again and answers it the same way; and the
         old reply pasted a shell command naming a key variable into the
         conversation, which is a terminal recipe in a reading surface. */
      if (d.unavailable) {
        say('askmeta', d.answer ||
          'Digby chat is not connected on this local build. ' +
          'Hub data remains available.');
        q.value = '';
        q.disabled = true;
        q.placeholder = 'Chat unavailable on this build';
        var sb = form.querySelector('button[type=submit]');
        if (sb) sb.disabled = true;
        busy = false;
        return;
      }
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
                   "digby-face", "digby-coach",
                   # ── BALLOT WORKSHOP ──────────────────────────────────────
                   # Cody's own ballot, his private notes, and his reasons for
                   # disagreeing with the model. The strip removes the section,
                   # the script AND the init; these markers make that a checked
                   # fact rather than three regexes nobody re-reads.
                   'data-v="ballot"', 'id="v-ballot"', "Ballot Workshop",
                   "renderBallot", "bwWire", "BW_KEY", "bwText", "ballots_",
                   "BALLOT-WORKSHOP-BEGIN", "BALLOT-CONST-BEGIN",
                   "BALLOT-INIT-BEGIN",
                   # ── MY BOARD ─────────────────────────────────────────────
                   # Cody's private watchlist. It lives only in HIS browser --
                   # there is no file, no endpoint and no payload -- but the
                   # CODE that reads it, the storage key it reads, and the
                   # panel it draws are all private too, so the published file
                   # must contain none of them.
                   "MYBOARD-HTML-BEGIN", "MYBOARD-CSS-BEGIN",
                   "MYBOARD-JS-BEGIN", "wvb.myboard",
                   "FILMROOM-HTML-BEGIN", "FILMROOM-JS-BEGIN",
                   "FILMROOM-CSS-BEGIN", "wvb.filmroom", 'id="v-film"',
                   "Film Room", "FR_KEY",
                   "INTEL-HTML-BEGIN", "INTEL-JS-BEGIN", "INTEL-CSS-BEGIN",
                   "wvb.intel", 'id="v-intel"', "IN_KEY", "/api/intel",
                   "GAMEDAY-JS-BEGIN", "GAMEDAY-CSS-BEGIN", "gd-panel",
                   "live validation",
                   "rss.xml",
                   # ── ENDPOINTS THAT ONLY EXIST BEHIND THE LOCAL SERVER ────
                   # ⚠ /api/live IS DELIBERATELY ABSENT FROM THIS LIST. The
                   # live band fetches it and FAILS SOFT on a static host --
                   # slateFromSchedule() renders today's fixtures from the
                   # embedded schedule instead. Adding it here would abort
                   # every public build for a feature that is working as
                   # designed. Checked before writing this: the published file
                   # contains it twice, on purpose.
                   "/api/ballot",
                   # ── CREDENTIALS AND LOCAL PATHS ──────────────────────────
                   # None of these has ever appeared in a build. They are here
                   # because this is a PUBLIC repo and the cost of the check is
                   # nil, while the cost of one leak is not recoverable -- a
                   # published secret is published even if the commit is later
                   # removed.
                   "ANTHROPIC_API_KEY", "sk-ant-", "ghp_", "github_pat_",
                   "/Users/", "127.0.0.1", "localhost:")


def strip_private(html):
    # type: (str) -> str
    """Remove the third-party views from the public page.

    Done as a post-pass on the finished HTML rather than as conditionals inside
    a 1,000-line template: the transformation is then a single place to read,
    and it is ASSERTED below rather than assumed.
    """
    # the On TV tab and its section
    # ⚠ THE NAV BECAME A MENU AND THIS REGEX DID NOT KNOW. It matched
    # role="tab" only, so the More menu's own On TV item survived and the
    # public build ABORTED on its marker -- the gate doing exactly its job.
    html = re.sub(r'\s*<button role="menuitem"[^>]*data-v="tv"[^>]*>.*?</button>',
                  "", html, flags=re.S)
    html = re.sub(r'\s*<button role="tab"[^>]*data-v="tv"[^>]*>.*?</button>', "",
                  html, flags=re.S)
    html = re.sub(r'<section id="v-tv".*?</section>', "", html, flags=re.S)
    # ⚠ THE BALLOT WORKSHOP IS PRIVATE. It is Cody's own ballot, his private
    # notes, and his reasons for disagreeing with the model -- none of which is
    # ours to publish. Removed wholesale from the public build rather than
    # hidden, because hiding a section still ships its contents (this project
    # already shipped 151 Massey ranks inside a payload behind removed columns).
    # The nav entry, WITH the comment above it -- that comment explains the
    # privacy of the feature and names the forum, so leaving it behind both
    # documents a section that is no longer there and trips the marker check.
    html = re.sub(r'\s*<!--\s*PRIVATE\..*?-->\s*'
                  # ⚠ ANY button that routes to the ballot, not just the nav
                  # tab -- the phone More-menu entry (role="menuitem") slipped
                  # past the tab-shaped pattern and the gate caught
                  # data-v="ballot" in the published bytes.
                  r'<button role="(?:tab|menuitem)"[^>]*data-v="ballot"[^>]*>.*?</button>', "",
                  html, flags=re.S)
    html = re.sub(r'\s*<button role="tab"[^>]*data-v="ballot"[^>]*>.*?</button>', "",
                  html, flags=re.S)
    html = re.sub(r'<section id="v-ballot".*?</section>', "", html, flags=re.S)
    # ⚠ AND ITS SCRIPT, NOT JUST ITS MARKUP. Removing the section alone left the
    # workshop's JavaScript in the published file -- dead code for a private
    # feature, and it names the forum Cody posts to, which tripped the marker
    # assertion and ABORTED the build. That abort was the guard working
    # correctly: a private feature should not ship its code either. Sentinels
    # rather than a regex guessing where a block ends.
    html = re.sub(r"/\* BALLOT-WORKSHOP-BEGIN \*/.*?/\* BALLOT-WORKSHOP-END \*/",
                  "", html, flags=re.S)
    # ⚠ AND ITS STYLESHEET. The markup, the script, the payload and the endpoint
    # were all being removed while ~150 lines of .bw* rules stayed behind --
    # dead weight in the published file, and the selector names alone enumerate
    # a private feature (.bwreview, .bwpre, .bwpin, .bwcase). No ballot content
    # was ever in them, which is exactly why this survived four review passes.
    html = re.sub(r"/\* BALLOT-CSS-BEGIN.*?/\* BALLOT-CSS-END \*/",
                  "", html, flags=re.S)
    html = re.sub(r"/\* BALLOT-CONST-BEGIN \*/.*?/\* BALLOT-CONST-END \*/",
                  "", html, flags=re.S)
    html = re.sub(r"<!-- MYBOARD-HTML-BEGIN -->.*?<!-- MYBOARD-HTML-END -->",
                  "", html, flags=re.S)
    html = re.sub(r"/\* MYBOARD-CSS-BEGIN \*/.*?/\* MYBOARD-CSS-END \*/",
                  "", html, flags=re.S)
    # ⚠ AND THE SCOREBOARD'S MY BOARD FILTER, in both layers. The button is
    # fenced above; this removes the branch that would serve it, so the public
    # build carries neither the control nor the code behind it.
    html = re.sub(r"/\* MYBOARD-WIRE-BEGIN \*/.*?/\* MYBOARD-WIRE-END \*/",
                  "", html, flags=re.S)
    # ⚠ THE FILM ROOM IS PRIVATE IN EVERY LAYER. Markup, script, stylesheet,
    # its route, its menu item and the one line that wires it -- six sentinel
    # pairs, because a feature that ships any one of them has shipped a
    # private feature. The notebook itself never leaves the browser, but the
    # CODE names what Cody records and would enumerate the feature on a public
    # page exactly as the ballot's selector names once did.
    for _a, _b in (("<!-- FILMROOM-HTML-BEGIN -->", "<!-- FILMROOM-HTML-END -->"),
                   ("/* FILMROOM-JS-BEGIN */", "/* FILMROOM-JS-END */"),
                   ("/* FILMROOM-CSS-BEGIN */", "/* FILMROOM-CSS-END */"),
                   ("/* FILMROOM-ROUTE-BEGIN */", "/* FILMROOM-ROUTE-END */"),
                   ("<!-- FILMROOM-MENU-BEGIN -->", "<!-- FILMROOM-MENU-END -->"),
                   ("/* FILMROOM-WIRE-BEGIN */", "/* FILMROOM-WIRE-END */"),
                   ("/* FILMROOM-HOOK-BEGIN */", "/* FILMROOM-HOOK-END */"),
                   ("<!-- INTEL-HTML-BEGIN -->", "<!-- INTEL-HTML-END -->"),
                   ("/* INTEL-JS-BEGIN */", "/* INTEL-JS-END */"),
                   ("/* INTEL-CSS-BEGIN */", "/* INTEL-CSS-END */"),
                   ("/* INTEL-ROUTE-BEGIN */", "/* INTEL-ROUTE-END */"),
                   ("<!-- INTEL-MENU-BEGIN -->", "<!-- INTEL-MENU-END -->"),
                   ("/* INTEL-WIRE-BEGIN */", "/* INTEL-WIRE-END */"),
                   ("/* GAMEDAY-JS-BEGIN */", "/* GAMEDAY-JS-END */"),
                   ("/* GAMEDAY-CSS-BEGIN */", "/* GAMEDAY-CSS-END */"),
                   ("/* GAMEDAY-CALL-BEGIN */", "/* GAMEDAY-CALL-END */"),
                   ("/* GAMEDAY-CALL2-BEGIN */", "/* GAMEDAY-CALL2-END */")):
        html = re.sub(re.escape(_a) + r".*?" + re.escape(_b), "", html,
                      flags=re.S)

    html = re.sub(r"/\* MYBOARD-JS-BEGIN \*/.*?/\* MYBOARD-JS-END \*/",
                  "", html, flags=re.S)
    html = re.sub(r"/\* BALLOT-INIT-BEGIN \*/.*?/\* BALLOT-INIT-END \*/",
                  "", html, flags=re.S)
    # third-party ranking columns
    # ⚠ TOLERANT OF ATTRIBUTES BEFORE title=. These patterns used to require
    # `title` to follow `<th` immediately, so the moment the header gained a
    # class the strip silently stopped matching -- and the build aborted on its
    # own marker check, which is the guard doing exactly its job. Anchoring a
    # removal on attribute ORDER is brittle; match the attribute wherever it is.
    html = re.sub(r'\s*<th[^>]*\btitle="VolleyTalk[^>]*>.*?</th>', "", html, flags=re.S)
    html = re.sub(r'\s*<th[^>]*\btitle="Massey[^>]*>.*?</th>', "", html, flags=re.S)
    html = re.sub(r'\s*<th[^>]*\btitle="range the other systems[^>]*>.*?</th>', "", html,
                  flags=re.S)
    # ⚠ AND THE GROUP HEADER'S COLSPAN MUST SHRINK WITH IT. The reference group
    # spans the columns it labels; removing three of them without adjusting the
    # span pushes every heading after it out of line -- the exact misalignment
    # the column-count guard exists to catch, arriving through the back door.
    def _shrink(m):
        return '<th class="g-ref" colspan="%d">' % max(1, int(m.group(1)) - 3)
    html = re.sub(r'<th class="g-ref" colspan="(\d+)">', _shrink, html)

    # the sentence describing the reference columns, and the VT/Massey chips
    html = html.replace(
        "VolleyTalk and Massey are all forecasts of 2026.",
        "and the AVCA coaches poll are forecasts of 2026.")
    html = re.sub(r"chip\('VT',[^)]*\)\s*\+\s*", "", html)
    html = re.sub(r"chip\('Massey',[^)]*\)\s*\+\s*", "", html)
    return html


def public_leaks(html):
    # type: (str) -> List[str]
    """Everything private still present in a page about to be published.

    ⚠ IT CHECKS THE DATA, NOT ONLY THE MARKUP. The first version of this gate
    searched for the strings "VolleyTalk" and "Massey Ratings", passed, and the
    build shipped 25 VolleyTalk ranks and 151 Massey ranks INSIDE `const TEAMS`
    -- invisible on the page, one devtools open away on a public site. Removing
    a column is not the same as not publishing its values, so the payload is
    parsed and inspected.

    Returns a list of findings. Empty means publishable.
    """
    found = [m for m in PRIVATE_MARKERS if m in html]

    # the payload itself
    m = re.search(r"const TEAMS = (\{.*?\});\n", html, re.S)
    if m:
        try:
            teams = json.loads(m.group(1).replace("<\\/", "</"))
        except ValueError:
            teams = {}
        for field, label in (("vt", "VolleyTalk"), ("massey", "Massey")):
            n = sum(1 for t in teams.values()
                    if isinstance(t, dict) and t.get(field) is not None)
            if n:
                found.append("%d %s ranks inside const TEAMS" % (n, label))
    return found


if __name__ == "__main__":
    html = build()
    if PUBLIC:
        html = strip_private(html)
        leaked = public_leaks(html)
        if leaked:
            # ⚠ ABORTS BEFORE WRITING. The previous output/vb_dashboard.html is
            # left untouched on disk, so a failed gate cannot replace a clean
            # published page with a leaking one -- and because the workflow step
            # has no `||`, the job stops before the commit step ever runs.
            raise SystemExit(
                "PUBLIC BUILD ABORTED: private content still present: %s"
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
