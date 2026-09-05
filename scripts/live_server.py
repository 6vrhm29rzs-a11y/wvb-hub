#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serve the hub with a live scoreboard behind it.

    python3 scripts/live_server.py          # then open the URL it prints

WHY A SERVER AND NOT JUST THE PAGE. ncaa-api sends no Access-Control-Allow-Origin
header, so a browser refuses to let a page fetch it directly -- measured, not
assumed. A local process is therefore the only way to poll it, and having one
also means N open tabs still cost ONE upstream request per cycle instead of N.

WHAT LIVE ACTUALLY GIVES US, measured on Louisville at Wisconsin mid-match:
    gameState "I", currentPeriod "1ST SET", linescores [{period 1, home 24,
    visit 15}], records updating to (0-1) / (1-0), and the venue.
So the running score inside the current set is available, not just the set count.
That is the thing worth putting on screen.

POLITENESS. One request per REFRESH_SECONDS for the scoreboard, plus one per
in-progress match for its running score. A quiet night is 1 request/minute; a
busy Friday with 40 simultaneous matches would be 41, which is why matches are
only detailed while they are actually in progress.

The static page works without this server -- it just shows completed matches and
no live band. Nothing here is required to read the hub.

Python 3.9 target, standard library only.
"""

import json
import os
import socket
import subprocess
import sys
import time
import threading
import datetime
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Optional, Tuple

import match_state as MS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBROOT = os.path.join(REPO, "Cody")
API = "https://ncaa-api.henrygd.me"
UA = "wvb-hub/0.1 (personal research project; live scoreboard, 1 req/min)"
PORT = int(os.environ.get("WVB_LIVE_PORT", "8799"))
REFRESH_SECONDS = int(os.environ.get("WVB_LIVE_REFRESH", "60"))
TIMEOUT = 20

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                    # pragma: no cover
    ET = None


_ATTR_LEDGER = os.path.join(REPO, "data", "raw", "2026",
                            "live_attribution_watch.json")
_attr_cache = {"mtime": None, "swaps": {}}


def _attr_swaps():
    """gid -> one-line correction basis, for ledger entries with
    display_swap: true. Hot-reloads on the ledger's mtime, same reasoning as
    the digby module reload: a server left running must see a ledger edit.
    Entries WITHOUT display_swap stay label-only and are not returned here.
    An unreadable ledger returns the last good copy -- a syntax slip while
    editing must not silently drop a correction mid-match."""
    try:
        mt = os.path.getmtime(_ATTR_LEDGER)
    except OSError:
        return {}
    if mt != _attr_cache["mtime"]:
        try:
            doc = json.load(open(_ATTR_LEDGER))
            out = {}
            for gid, e in doc.items():
                if gid.startswith("_") or not isinstance(e, dict):
                    continue
                if e.get("display_swap") and e.get("evidence"):
                    out[gid] = {
                        "note": e.get("display_note") or (
                            "Score attribution corrected from cited sources; "
                            "the upstream feed has the sides inverted."),
                        # ⚠ THE SWAP IS CONDITIONED ON THE FEED ORIENTATION
                        # THE EVIDENCE DESCRIBED (paid for live, 2026-09-01:
                        # the feed SELF-CORRECTED at final by swapping the
                        # team names, and the blind numeric swap re-inverted
                        # a correct record). No applies_when -> never swaps.
                        "applies_when": e.get("applies_when") or None,
                    }
            _attr_cache["swaps"] = out
            _attr_cache["mtime"] = mt
        except (ValueError, OSError):
            pass
    return _attr_cache["swaps"]


def _get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _et_now():
    return datetime.datetime.now(ET) if ET else datetime.datetime.utcnow()


_HUB = [None]


def _hub():
    """build_hub, imported lazily. It owns the one rule for displaying a time."""
    if _HUB[0] is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import build_hub
        _HUB[0] = build_hub
    return _HUB[0]


BALLOT_MAX_BODY = 256 * 1024          # a 25-team ballot with notes is ~4 KB

_BALLOT = [None]


def _ballot_mod():
    """scripts/ballot.py, imported lazily and hot-reloaded like digby.

    Same reason as digby: this server is meant to be left running for hours, and
    Python caches an imported module for the life of the process -- so without
    this an edit to ballot.py would have no effect and would look like a failed
    fix.
    """
    import importlib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if _BALLOT[0] is None:
        import ballot
        _BALLOT[0] = ballot
    else:
        try:
            importlib.reload(_BALLOT[0])
        except Exception:                                 # noqa: BLE001
            pass
    return _BALLOT[0]


def _now_pt():
    """Now, in the zone the page renders in."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        return datetime.datetime.now()


def _fmt_time(epoch, start_time=None, home_team=None):
    """A start time, rendered the way the rest of the page renders one.

    TWO THINGS THAT MUST NOT BE MERGED. `ET` above decides which DATES to ask
    the scoreboard for -- the feed is keyed by the Eastern calendar day and
    that stays Eastern. What a reader SEES is Pacific, because Cody is.

    This used to format the epoch in Eastern and append the literal "ET", so
    tonight's slate read "6:00 PM ET" on a page whose every other time was
    Pacific -- two clocks on one screen, three hours apart, with nothing saying
    which was which.

    It defers to build_hub.listed_time() rather than converting here, so the
    midnight sentinel is judged in EASTERN terms before any conversion (a 1:00
    AM ET placeholder becomes a perfectly ordinary-looking 10:00 PM PT, so
    converting first would launder a non-time into a plausible one) and Hawaii's
    genuine late starts survive. One definition of "how a time is shown" (R4).
    """
    st = (start_time or "").strip()
    if not st and epoch and ET:
        try:
            st = datetime.datetime.fromtimestamp(int(epoch), ET).strftime("%-I:%M %p ET")
        except (TypeError, ValueError, OSError):
            return ""
    if not st:
        return ""
    try:
        return _hub().listed_time(st, home_team, epoch)
    except Exception:
        return st


class Cache(object):
    """Holds the last good scoreboard. Never serves a half-built one."""

    def __init__(self):
        self.payload = {"games": [], "updated": None, "error": None}
        self.lock = threading.Lock()
        self.stop = threading.Event()

    def snapshot(self):
        with self.lock:
            return dict(self.payload)

    def refresh(self):
        now = _et_now()
        days = [now.date()]
        # a match that starts at 9pm ET finishes after midnight UTC, and late
        # west-coast matches roll past midnight ET, so yesterday stays in view
        days.append(now.date() - datetime.timedelta(days=1))

        games, err = [], None
        for d in days:
            sb = _get("/scoreboard/volleyball-women/d1/%04d/%02d/%02d/all-conf"
                      % (d.year, d.month, d.day))
            if sb is None:
                err = "scoreboard unavailable"
                continue
            for entry in sb.get("games") or []:
                g = entry.get("game", entry)
                state = (g.get("gameState") or "").lower()
                a, h = g.get("away") or {}, g.get("home") or {}
                games.append({
                    "id": g.get("gameID"),
                    "state": state,
                    "date": d.isoformat(),
                    "time": _fmt_time(g.get("startTimeEpoch"), g.get("startTime"),
                                     (h.get("names") or {}).get("short")),
                    "period": g.get("currentPeriod") or "",
                    "away": (a.get("names") or {}).get("short"),
                    "home": (h.get("names") or {}).get("short"),
                    "away_rank": a.get("rank") or "",
                    "home_rank": h.get("rank") or "",
                    # ⚠ NOT `or "0"`. The scoreboard serves score:'' before
                    # first serve (measured; docs/live_endpoint_audit.md), and
                    # `'' or "0"` makes an unplayed match read 0-0 -- which is
                    # indistinguishable from a real 0-0 at first serve. Pass
                    # the absence through and let the state model decide.
                    "away_sets": a.get("score"),
                    "home_sets": h.get("score"),
                    "sets": [],
                    "venue": "",
                })

        # ⚠ CITED LIVE ATTRIBUTION CORRECTION, APPLIED AT THE ONE CHOKE
        # POINT (Cody, 2026-09-01, IU-Georgia: "are you ignoring the fact
        # that indiana is up 2-1"). The feed inverts team attribution on some
        # matches -- real per-set scores, sides swapped. When the ledger
        # (data/raw/2026/live_attribution_watch.json) carries an entry with
        # display_swap: true and attributable evidence, the NUMBERS are
        # reattributed here -- teams stay put, away/home payloads swap -- so
        # every consumer (rows, ticker, cards, detail) gets the corrected
        # score at once. Nothing is invented: these are the feed's own
        # numbers under the attribution two cited sources report. The FINAL
        # still goes through the two-source correction ledger; this governs
        # only the live display.
        swaps = _attr_swaps()

        def _swap_applies(row):
            sw = swaps.get(str(row.get("id") or ""))
            if not sw or not sw.get("applies_when"):
                return None
            aw = sw["applies_when"]
            if row.get("away") == aw.get("away") and \
               row.get("home") == aw.get("home"):
                return sw
            return None

        for row in games:
            sw = _swap_applies(row)
            if not sw:
                continue
            row["away_sets"], row["home_sets"] = row["home_sets"], row["away_sets"]
            row["attribution_corrected"] = sw["note"]

        # ⚠ ONE STATE MODEL, RESOLVED HERE. Every consumer of this payload --
        # the Match Desk band, the Scores ledger, the match detail -- reads
        # `state6` rather than deciding for itself what "live" or "over" means.
        # Three renderers each deciding was how a finished match ended up in
        # "Coming up" and how a 0-0 match showed a leader.
        for row in games:
            r = MS.resolve(feed=row)
            row["state6"] = r["state"]
            row["state_label"] = r["label"]
            row["state_note"] = r["note"]
            row["caps"] = r["caps"]

        # Only in-progress matches get a detail call -- a finished match is
        # already in the committed game log, and an unplayed one has nothing.
        for row in games:
            if row["state"] not in ("live", "in progress", "i"):
                continue
            det = _get("/game/%s" % row["id"])
            if not det:
                continue
            c = (det.get("contests") or [{}])[0]
            row["period"] = c.get("currentPeriod") or row["period"]
            loc = c.get("location") or {}
            row["venue"] = ", ".join(
                x for x in (loc.get("venue"), loc.get("city"), loc.get("stateUsps")) if x)
            sets = []
            for s in c.get("linescores") or []:
                try:
                    sets.append([int(s.get("visit")), int(s.get("home"))])
                except (TypeError, ValueError):
                    continue
            row["sets"] = sets
            for t in c.get("teams") or []:
                if t.get("isHome"):
                    row["home_sets"] = str(t.get("score") or 0)
                else:
                    row["away_sets"] = str(t.get("score") or 0)
            # the detail call refills from the feed -- re-apply the cited
            # swap, under the same orientation condition
            if _swap_applies(row):
                row["away_sets"], row["home_sets"] = (row["home_sets"],
                                                      row["away_sets"])
                row["sets"] = [[b, a] for a, b in row["sets"]]

        with self.lock:
            # Keep the last good payload on a failed cycle rather than blanking
            # the board -- a momentary upstream hiccup should not look like
            # "no games tonight".
            if games or not self.payload.get("games"):
                self.payload = {
                    "games": games,
                    # ⚠ THE PAGE IS PACIFIC. _et_now() stays Eastern because
                    # the scoreboard is keyed by the Eastern calendar day, but
                    # the stamp a reader SEES must match every other time on
                    # the page -- it was printing "9:33 PM ET" directly above
                    # fixtures listed in PT, which is the same two-clocks bug
                    # already fixed for start times.
                    "updated": _now_pt().strftime("%-I:%M:%S %p PT"),
                    "error": err,
                }
            else:
                self.payload["error"] = err

    def run(self):
        while not self.stop.is_set():
            try:
                self.refresh()
            except Exception as exc:                 # never let the poller die
                with self.lock:
                    self.payload["error"] = "poller: %s" % exc
            self.stop.wait(REFRESH_SECONDS)


CACHE = Cache()


# ------------------------------------------------- one open match's detail
# ⚠ SEPARATE FROM /api/live ON PURPOSE. The scoreboard poller runs on a timer
# for every match of the night; this runs ONLY when Cody opens a card, only for
# that card, and at most once per DETAIL_TTL. A busy Friday costs the upstream
# exactly what a quiet Monday does.
def _detail_fetch(gid):
    return _get("/game/%s/boxscore" % gid)


_DETAIL = [None]


def _detail_cache():
    if _DETAIL[0] is None:
        import live_detail
        _DETAIL[0] = live_detail.DetailCache(_detail_fetch)
    return _DETAIL[0]


def _live_state(gid):
    """What the scoreboard poller currently says about this id."""
    for g in (CACHE.snapshot().get("games") or []):
        if str(g.get("id")) == str(gid):
            return g
    return None


def match_detail(gid):
    """The payload behind /api/match. Never raises; never fabricates."""
    import live_detail

    row = _live_state(gid)
    if row is None:
        # Not on today's or yesterday's scoreboard. We will not go fishing for
        # arbitrary ids -- that is how a detail endpoint becomes a crawler.
        return {"ok": False, "id": str(gid), "state": "unknown",
                "state6": MS.UNAVAILABLE,
                "state_note": MS.DETAIL_NOTE[MS.UNAVAILABLE],
                "caps": MS.CAPABILITIES[MS.UNAVAILABLE],
                "reason": "that match is not on the current scoreboard"}

    state = (row.get("state") or "").lower()
    base = {
        "ok": True, "id": str(gid), "state": state,
        "away": row.get("away"), "home": row.get("home"),
        "away_sets": row.get("away_sets"), "home_sets": row.get("home_sets"),
        "period": row.get("period") or "", "sets": row.get("sets") or [],
        "venue": row.get("venue") or "",
        "scoreboard_updated": CACHE.snapshot().get("updated"),
        "source": "official NCAA feed",
        "stats_available": False, "stats_reason": "", "teams": [],
        "leaders": [], "stale": False, "age_seconds": 0,
    }
    # The shared state, resolved once. `box` is filled in below only for a
    # live match; a final's official box score reaches the page through the
    # committed archive, so from here a final is `final_box_pending` and the
    # page upgrades it to `final_with_box` when the archive has the totals.
    _r = MS.resolve(feed=row)
    base["state6"] = _r["state"]
    base["state_label"] = _r["label"]
    base["state_note"] = _r["note"]
    base["caps"] = dict(_r["caps"])

    # ⚠ A FINAL IS HANDED BACK TO THE VERIFIED PIPELINE, NOT SCRAPED HERE. The
    # inset says "final" and stops; the result reaches the site through the
    # existing crawl/refresh path, which is the only thing allowed to write it.
    if MS.is_over(row):
        base["stats_reason"] = ("final -- the official box score reaches the "
                                "page through the verified crawl, not from "
                                "here")
        return base

    if state not in ("live", "in progress", "i"):
        base["stats_reason"] = "not under way yet"
        return base

    payload, age, stale, err = _detail_cache().get(gid)
    base["stale"] = bool(stale)
    base["age_seconds"] = int(age)
    if payload is None:
        base["stats_reason"] = err or "the official box score is not available"
        return base

    expect = len(row.get("sets") or []) or None
    teams, leaders, why = live_detail.validate(payload, expect_sets=expect)
    if teams is None:
        base["stats_reason"] = why or "the official box score is not usable yet"
        return base
    base["stats_available"] = True
    base["teams"] = teams
    base["leaders"] = leaders
    # ⚠ THE STATE IS RE-RESOLVED WITH THE BOX IN HAND, not patched by hand.
    # A live match that IS serving team totals is `live_with_team_stats`, and
    # the capabilities come from the same table everything else reads -- so
    # `player_lines` stays false here unless the payload really carries them.
    _r2 = MS.resolve(feed=row, box={"teams": teams, "players": leaders})
    base["state6"] = _r2["state"]
    base["state_label"] = _r2["label"]
    base["state_note"] = _r2["note"]
    base["caps"] = dict(_r2["caps"])
    return base


# ------------------------------------------------------------------ Digby
# The chat endpoint. It exists here rather than in the page because the API key
# must never reach the browser: the page asks this process, this process holds
# the key, and the key comes from the environment and is never written down.
#
# THIS SERVER BINDS TO 127.0.0.1 AND MUST STAY THAT WAY. The moment it answers
# on a routable address, anything on the network can spend the key. The Host
# check below is the second lock -- it stops a DNS-rebinding page in the
# browser from reaching an endpoint that only expects to hear from localhost.

# ⚠ THE PRIVATE-HOST ALLOWLIST. Empty by default: out of the box only
# localhost reaches a private endpoint, exactly as before. Set it to the exact
# hostname a trusted reverse proxy will present, e.g.
#     export WVB_TRUSTED_HOSTS="codys-mac.tailnet-1234.ts.net"
# Comma-separated for more than one. Whitespace and case are normalised;
# entries with a scheme, a path, a port or a wildcard are DROPPED rather than
# guessed at, because a malformed entry that silently matched nothing would
# look identical to one that worked.
def _parse_trusted(raw):
    out = set()
    for part in (raw or "").split(","):
        h = part.strip().strip('"').strip("'").lower()
        if not h:
            continue
        if "*" in h or "/" in h or ":" in h or " " in h:
            continue
        out.add(h)
    return frozenset(out)


def _host_only(raw):
    """The hostname from a Host header, without its port.

    ⚠ SPLITTING ON ":" IS WRONG FOR IPv6, AND THE ORIGINAL CODE DID IT. The old
    check was `Host.split(":")[0] in ("127.0.0.1","localhost","[::1]","::1")`.
    For a bare `::1` that yields "" and for `[::1]:8799` it yields "[" -- so
    NEITHER IPv6 localhost form has ever actually matched, despite both being
    listed. Nothing broke, because browsers send `localhost` or `127.0.0.1`;
    it simply meant two of the four entries were decoration.
    RFC 3986 brackets an IPv6 literal in a host, so: bracketed -> take what is
    inside; more than one colon and no bracket -> a bare IPv6, keep it whole;
    otherwise -> split off the port.
    """
    h = (raw or "").strip().lower()
    if not h:
        return ""
    if h.startswith("["):
        end = h.find("]")
        return h[1:end] if end > 0 else ""
    if h.count(":") > 1:
        return h
    return h.split(":")[0]


TRUSTED_HOSTS = _parse_trusted(os.environ.get("WVB_TRUSTED_HOSTS", ""))

DIGBY_MAX_BODY = 4096
DIGBY_MIN_GAP = float(os.environ.get("WVB_DIGBY_MIN_GAP", "2"))
DIGBY_MAX_PER_RUN = int(os.environ.get("WVB_DIGBY_MAX", "200"))
_digby = {"last": 0.0, "count": 0, "index": None, "teams": None,
          "mtimes": {}}
_digby_lock = threading.Lock()


def _digby_key():
    """The Anthropic key, hot-read PER REQUEST -- env first, then the
    gitignored drop file. The key used to be read only at server LAUNCH, so
    a server started without it kept Digby dark for its whole life and the
    fix required a restart timed with an export (Cody hit exactly this,
    2026-09-05: "digby doesn't work on desktop or mobile"). Now: drop the
    key in Cody/data/anthropic_key.txt (one line; the whole Cody/ tree is
    gitignored, this repo is PUBLIC) and the NEXT question works, no
    restart. The key value is never logged and never echoed to the page."""
    k = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if k.startswith("sk-ant-"):
        return k
    p = os.path.join(REPO, "Cody", "data", "anthropic_key.txt")
    if os.path.exists(p):
        try:
            k = open(p, encoding="utf-8").read().strip()
        except OSError:
            return None
        if k.startswith("sk-ant-"):
            os.environ["ANTHROPIC_API_KEY"] = k   # digby's client reads env
            return k
    return None


def _digby_answer(question):
    """One question -> a dict for the page. Never raises."""
    try:
        _digby_key()
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import digby_chat
        import digby
        from digby import teams_from_page
        # RELOAD WHEN THE SOURCE CHANGES. This server is meant to be left
        # running for hours, and Python caches an imported module for the life
        # of the process -- so edits to the prompt or the retrieval had NO
        # effect until a restart, while the page kept answering with the old
        # behaviour and looking like the fix had failed. That cost a round of
        # "I fixed it" / "it still does it".
        # ⚠ RELOAD BOTH WHEN EITHER CHANGES. `digby_chat` does
        # `from digby import fact_sheet`, so reloading `digby` alone leaves
        # digby_chat holding the OLD function object -- the chat kept answering
        # "that isn't in the hub's data" about fields that had just been added,
        # because only digby.py's mtime had moved. Dependency order matters
        # too: digby first, so digby_chat re-imports the new one.
        changed = False
        for mod in (digby, digby_chat):
            try:
                src = os.path.abspath(mod.__file__)
                mtime = os.path.getmtime(src)
                if _digby["mtimes"].get(src) is None:
                    _digby["mtimes"][src] = mtime
                elif mtime > _digby["mtimes"][src]:
                    _digby["mtimes"][src] = mtime
                    changed = True
            except Exception:                            # noqa: BLE001
                pass
        if changed:
            import importlib
            for mod in (digby, digby_chat):              # order is load-bearing
                try:
                    importlib.reload(mod)
                except Exception:                        # noqa: BLE001
                    pass
            _digby["index"] = None
            _digby["teams"] = None
            print("  [reloaded digby + digby_chat]")
        import digby_chat                                # rebind after reload
    except Exception as exc:                              # noqa: BLE001
        return {"ok": False, "answer": "Digby is unavailable (%s)."
                                       % type(exc).__name__}
    with _digby_lock:
        now = time.time()
        if _digby["count"] >= DIGBY_MAX_PER_RUN:
            return {"ok": False,
                    "answer": "That is %d questions this run -- restart the "
                              "server to keep going. The cap is here so a stuck "
                              "page cannot spend in a loop." % DIGBY_MAX_PER_RUN}
        if now - _digby["last"] < DIGBY_MIN_GAP:
            return {"ok": False, "answer": "One moment -- still thinking."}
        _digby["last"] = now
        _digby["count"] += 1
        page = os.path.join(WEBROOT, "START-HERE.html")
        try:
            pm = os.path.getmtime(page)
        except OSError:
            pm = None
        if pm and _digby.get("page_mtime") != pm:
            # The page is the source of every fact. A rebuild means the cached
            # team records are stale even when no code changed.
            _digby["page_mtime"] = pm
            _digby["teams"] = None
            _digby["index"] = None
        if _digby["teams"] is None:
            _digby["teams"] = teams_from_page()
            _digby["index"] = digby_chat.build_index(_digby["teams"])
    r = digby_chat.ask(question, teams=_digby["teams"], index=_digby["index"])
    # The key errors are written for someone at a prompt. A reader here is in a
    # browser, and the shell that matters is the one THIS SERVER was started
    # from -- so say that instead of "in this shell", which points at nothing
    # the reader can see.
    if not r.get("ok") and "ANTHROPIC_API_KEY" in (r.get("answer") or ""):
        # ⚠ NO SHELL COMMANDS IN A CHAT BUBBLE. This printed an export line
        # naming a key variable inside the conversation -- a terminal recipe
        # in a reading surface, and one that puts the shape of a secret on
        # screen. The page states availability; how to change it is not the
        # chat's business.
        r["answer"] = ("Digby chat is not connected on this local build. "
                       "Hub data remains available. (To connect it: put the "
                       "API key on one line in Cody/data/anthropic_key.txt "
                       "-- the private folder -- and ask again; no restart "
                       "needed.)")
        r["unavailable"] = True
    return r


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        kw["directory"] = WEBROOT
        SimpleHTTPRequestHandler.__init__(self, *a, **kw)

    # ⚠ THE PAGE IS REBUILT MANY TIMES AN HOUR AND THE BROWSER WAS KEEPING
    # THE OLD COPY. The JSON endpoints already sent "no-store"; static files
    # went out with only a Last-Modified, so Chrome served a heuristically
    # cached START-HERE.html and a rebuilt fix simply did not appear. That
    # reads exactly like a fix that did not work -- verified today, where the
    # file on disk carried a patch the loaded document did not.
    # This is the same failure the PUBLIC build solves with a content hash in
    # index.html; the local server has no such indirection, so it says plainly
    # that nothing here may be reused.
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        SimpleHTTPRequestHandler.end_headers(self)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_trusted(self):
        """May this request reach a private endpoint?

        ⚠ THE BIND IS THE FIRST LOCK AND IT DOES NOT CHANGE. This process
        answers on 127.0.0.1 only. Nothing here loosens that, and nothing here
        makes the server reachable from a network -- a reverse proxy in front
        of localhost is the only way a phone ever talks to it.

        ⚠ THIS IS THE SECOND LOCK: the Host header. A page in the browser can
        resolve a name it controls to 127.0.0.1 (DNS rebinding) and then fetch
        these endpoints as same-origin. The bind cannot see that; the Host can,
        because the attacker's page sends its own name.

        ⚠ WHY IT IS NO LONGER A HARDCODED LIST. Tailscale Serve terminates
        HTTPS and proxies to localhost, but PRESERVES the original Host -- so
        an iPhone request arrives with `something.ts.net`. Against the old
        fixed tuple every private endpoint would 403 and the page would look
        broken for no visible reason. The allowlist is EXACT-MATCH, empty by
        default, and comes from the environment: adding a host is a deliberate
        act, not a wildcard.

        ⚠ EXACT MATCH, NEVER A SUFFIX TEST. `endswith(".ts.net")` would accept
        `evil.ts.net`; `"ts.net" in host` would accept `ts.net.evil.com`. Both
        are refused here, and both have negative controls in the test suite.
        """
        host = _host_only(self.headers.get("Host"))
        if host in ("127.0.0.1", "localhost", "::1"):
            return True
        return host in TRUSTED_HOSTS

    # kept as the old name so nothing that already calls it changes meaning
    _is_local = _is_trusted

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/ballot":
            self._save_ballot()
            return
        if path != "/api/digby":
            self.send_error(404)
            return
        if not self._is_local():
            self._json({"ok": False, "answer": "local requests only."}, 403)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > DIGBY_MAX_BODY:
            self._json({"ok": False, "answer": "question too long."}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            question = (payload or {}).get("question") or ""
        except Exception:                                 # noqa: BLE001
            self._json({"ok": False, "answer": "could not read the question."}, 400)
            return
        self._json(_digby_answer(question))

    def _save_ballot(self):
        """Append one ballot to data/ballots_{SEASON}.jsonl.

        ⚠ APPEND-ONLY AND LOCAL-ONLY, both structural rather than promised.
        The file is opened for append and never rewritten, so "a past ballot is
        never overwritten" is a property of the storage rather than of the code
        remembering to be careful. The local check is the same one /api/digby
        uses -- this writes to Cody's disk, and nothing off this machine should
        be able to.
        """
        if not self._is_local():
            self._json({"ok": False, "error": "local requests only."}, 403)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > BALLOT_MAX_BODY:
            self._json({"ok": False, "error": "ballot too large."}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:                                 # noqa: BLE001
            self._json({"ok": False, "error": "could not read the ballot."}, 400)
            return
        try:
            B = _ballot_mod()
            row = B.append(payload)
        except ValueError as e:                           # validation, not a crash
            self._json({"ok": False, "error": str(e)}, 400)
            return
        except Exception as e:                            # noqa: BLE001
            self._json({"ok": False, "error": "could not save: %s" % e}, 500)
            return
        # ⚠ THE SAVE IS ALREADY DONE AND IS NOT CONDITIONAL ON THE BACKUP.
        # The ballot is on disk before this line; the mirror to the private repo
        # is attempted afterwards and reported honestly. A network failure, a
        # missing backup repo or a rejected push all come back as "pending" --
        # never as a green tick over a backup that did not happen, and never as
        # a failed save.
        backup = {"state": "pending", "detail": "not attempted"}
        try:
            import importlib
            import ballot_backup
            importlib.reload(ballot_backup)
            backup = ballot_backup.sync()
        except Exception as e:                            # noqa: BLE001
            backup = {"state": "pending",
                      "detail": "backup unavailable: %s" % str(e)[:100]}
        self._json({"ok": True, "saved_utc": row.get("saved_utc"),
                    "count": len(B.load()), "backup": backup})

    def do_GET(self):
        if self.path.split("?")[0] == "/api/ballot":
            # ⚠ THIS WAS UNGUARDED. It returns saved ballot history -- Cody's
            # own Top 25 and his reasons for it -- and was the one private
            # endpoint a rebinding page could read without passing the Host
            # check, because the check was simply never applied here.
            if not self._is_trusted():
                self._json({"ok": False, "reason": "local requests only."}, 403)
                return
            try:
                rows = _ballot_mod().load()
            except Exception as e:                        # noqa: BLE001
                self._json({"ok": False, "error": str(e)}, 500)
                return
            self._json({"ok": True, "ballots": rows})
            return
        if self.path.split("?")[0] == "/api/match":
            if not self._is_local():
                self._json({"ok": False, "reason": "local requests only."}, 403)
                return
            try:
                from urllib.parse import parse_qs, urlparse
                gid = (parse_qs(urlparse(self.path).query).get("id")
                       or [""])[0].strip()
            except Exception:                             # noqa: BLE001
                gid = ""
            # An id is digits. Anything else is not a game and is not looked up.
            if not gid or not gid.isdigit() or len(gid) > 12:
                self._json({"ok": False, "state": "unknown",
                            "reason": "a numeric game id is required"}, 400)
                return
            try:
                self._json(match_detail(gid))
            except Exception as e:                        # noqa: BLE001
                # Fail soft: the inset shows the live score and says detail is
                # unavailable. It never shows a traceback or a zero.
                self._json({"ok": False, "id": gid, "state": "error",
                            "reason": "detail unavailable: %s" % str(e)[:120]})
            return
        # ⚠ INTEL IS SERVER-SIDE ON PURPOSE. The browser never fetches a news
        # feed itself: it asks this local endpoint, which will only ever
        # request URLs from intel.SOURCES. There is NO url parameter -- the
        # request names a source KEY or nothing at all, so the page cannot
        # steer it anywhere. Local requests only, like the rest of /api.
        if self.path.split("?")[0] == "/api/intel":
            if not self._is_local():
                self._json({"ok": False, "reason": "local requests only."}, 403)
                return
            try:
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                force = (q.get("force") or ["0"])[0] == "1"
            except Exception:                             # noqa: BLE001
                force = False
            try:
                import intel
                self._json(intel.all_sources(force=force))
            except Exception as exc:                      # noqa: BLE001
                # Fail soft: the desk shows "source unavailable" and keeps
                # whatever it already had.
                self._json({"items": [], "sources": [],
                            "error": "intel unavailable: %s" % str(exc)[:120]})
            return
        if self.path.split("?")[0] == "/api/live":
            # ⚠ ALSO UNGUARDED. The payload is public scoreboard data, so the
            # exposure is small -- but an unguarded endpoint still confirms to
            # any page that this server exists and what it is, and there is no
            # reason for the live cache to be the one door left open.
            if not self._is_trusted():
                self._json({"ok": False, "reason": "local requests only."}, 403)
                return
            body = json.dumps(CACHE.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self._serve_static()

    # ⚠ THE PHONE WAS DOWNLOADING 10.5 MB WHEN 1.6 MB WOULD DO. GitHub Pages
    # gzips this page to 1.5 MB; SimpleHTTPRequestHandler does not compress at
    # all, and the local server is the one Cody's phone actually reads over
    # Tailscale -- so every visit pulled the whole uncompressed page over
    # cellular. 84% of that was avoidable and nothing about the content changes.
    #
    # ⚠ TEXT ONLY, AND ONLY WHEN ASKED. Images and fonts are already compressed
    # and re-compressing them wastes CPU for nothing; a client that does not
    # advertise gzip still gets the plain bytes.
    _GZIP_TYPES = ("text/html", "text/css", "application/javascript",
                   "text/javascript", "application/json", "image/svg+xml",
                   "text/plain")

    def _serve_static(self):
        import gzip as _gzip
        import posixpath
        import mimetypes
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return SimpleHTTPRequestHandler.do_GET(self)
        accepts = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
        ctype = mimetypes.guess_type(path)[0] or ""
        if not accepts or not ctype.startswith(self._GZIP_TYPES):
            return SimpleHTTPRequestHandler.do_GET(self)
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            # ⚠ FALL BACK, NEVER 500. A missing file is the base handler's job
            # to report, and it words it better than this would.
            return SimpleHTTPRequestHandler.do_GET(self)
        body = _gzip.compress(raw, 6)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return None

    def log_message(self, fmt, *args):
        pass                                          # keep the console quiet


def _who_has(port):
    """Name the process holding a port, so the fix is obvious."""
    try:
        import subprocess
        out = subprocess.check_output(
            ["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN"],
            stderr=subprocess.DEVNULL).decode("utf-8", "replace").splitlines()
        if len(out) > 1:
            f = out[1].split()
            return "  (PID %s, %s -- stop it with: kill %s)" % (f[1], f[0], f[1])
    except Exception:                                    # noqa: BLE001
        pass
    return ""


class _V6Server(ThreadingHTTPServer):
    """An IPv6 listener. ThreadingHTTPServer is AF_INET only by default."""
    address_family = socket.AF_INET6


def tailscale_self():
    # type: () -> Optional[Tuple[str, str]]
    """This Mac's tailnet IP and MagicDNS name, or None if Tailscale is off.

    ⚠ THE TAILNET INTERFACE IS NOT THE LAN AND IT IS NOT 0.0.0.0. Binding here
    exposes the hub to the devices on Cody's own tailnet and to nothing else:
    a machine on the same coffee-shop wifi cannot reach it, no router port is
    opened, and this is Tailscale's private mesh, never Funnel.
    ⚠ AND IT IS OPT-IN. Without WVB_TAILNET=1 the server binds 127.0.0.1 only,
    exactly as before.
    """
    exe = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    for cand in (exe, "tailscale"):
        try:
            out = subprocess.check_output([cand, "status", "--json"],
                                          stderr=subprocess.DEVNULL, timeout=20)
        except Exception:
            continue
        try:
            d = json.loads(out.decode("utf-8", "replace"))
        except Exception:
            continue
        me = d.get("Self") or {}
        # Tailscale gives every node an IPv4 (100.x) and an IPv6 (fd7a:...),
        # and both are bound.
        # ⚠ THE v4 ADDRESS IS THE ONE THAT MATTERS, AND I HAD THE REASON WRONG
        # BEFORE CHECKING. I assumed MagicDNS publishes AAAA and that iOS would
        # prefer it, making a v4-only bind a silent failure on the phone. It
        # does not: `dig @100.100.100.100 <node> AAAA` returns nothing, so the
        # MagicDNS name resolves to the 100.x address and Safari uses v4.
        # ⚠ AND THE v6 LISTENER IS UNVERIFIED, WHICH IS SAID RATHER THAN
        # GLOSSED. It binds and appears in lsof, but TCP to this host's own
        # tailnet v6 address times out here even though ping6 succeeds, so
        # there is no way to exercise it locally. It is kept as cover in case
        # MagicDNS ever starts publishing AAAA; it is not load-bearing today.
        ips = list(me.get("TailscaleIPs") or [])
        name = (me.get("DNSName") or "").rstrip(".")
        if ips:
            return ips, name
    return None


def main():
    if not os.path.isdir(WEBROOT):
        print("no %s -- run scripts/build_hub.py first" % WEBROOT)
        return 1
    t = threading.Thread(target=CACHE.run)
    t.daemon = True
    t.start()

    # ---- local refresh loop ------------------------------------------------
    # The score poll above keeps the LIVE numbers fresh; it does nothing for
    # the RANKINGS, which are baked into the page at build time. Without this,
    # the local page's power rankings sit frozen at the last manual pipeline
    # run while looking live -- found on the season's first full match day.
    # Each cycle shells out to scripts/local_refresh.py (the CI refresh's
    # local twin); its flock makes overlap with a manual run impossible, and
    # its fingerprint gate means a cycle with no new final rebuilds nothing.
    refresh_every = int(os.environ.get("WVB_LOCAL_REFRESH_SECONDS", "1200"))

    def _local_refresh_loop():
        while True:
            time.sleep(refresh_every)
            try:
                subprocess.run(
                    [sys.executable or "python3",
                     os.path.join(REPO, "scripts", "local_refresh.py")],
                    cwd=REPO, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=1800)
            except Exception:                     # never let the loop die
                pass

    if refresh_every > 0:
        threading.Thread(target=_local_refresh_loop, daemon=True).start()

    # A LEFTOVER SERVER FROM AN EARLIER SESSION IS THE NORMAL CASE, not an
    # exceptional one -- this thing is meant to be left running, and the old
    # behaviour was a nine-line traceback ending in "Address already in use",
    # which reads like the script is broken rather than like something is
    # already working. Say what is holding the port, then move to the next one
    # instead of refusing to start.
    srv = None
    for port in range(PORT, PORT + 12):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError as exc:
            if exc.errno not in (48, 98):               # EADDRINUSE (BSD, Linux)
                raise
            print("port %d is already in use%s" % (port, _who_has(port)))
    if srv is None:
        print("\nno free port in %d-%d. Stop the old server and try again:"
              % (PORT, PORT + 11))
        print("  pkill -f live_server.py")
        return 1
    PORT_IN_USE = srv.server_address[1]
    if PORT_IN_USE != PORT:
        print("  -> started on %d instead\n" % PORT_IN_USE)
    url = "http://127.0.0.1:%d/START-HERE.html" % PORT_IN_USE
    print("live scoreboard running")
    print("  open: %s" % url)
    print("  refreshing every %ds -- one upstream request per cycle" % REFRESH_SECONDS)
    if refresh_every > 0:
        print("  rankings: recomputed every %d min once a new final lands"
              " (WVB_LOCAL_REFRESH_SECONDS=0 to disable)"
              % (refresh_every // 60))
    else:
        print("  rankings: local refresh OFF -- the page only changes when"
              " the pipeline is run by hand")
    # Say plainly whether the chat will work, at the moment it can still be
    # fixed. Finding out by clicking the button and reading an error is worse.
    if (os.environ.get("ANTHROPIC_API_KEY") or "").startswith("sk-ant-"):
        print("  Ask Digby: ready")
    else:
        print("  Ask Digby: OFF -- no ANTHROPIC_API_KEY in this shell. "
              "Drop the key (one line) in Cody/data/anthropic_key.txt and "
              "the next question connects -- no restart needed.")
        print("             Everything else on the page works without it.")
    print("  ctrl-c to stop")
    # ---- optional second listener, on the tailnet interface only ---------
    ts_srv = None
    # ⚠ TAILNET IS ON BY DEFAULT (2026-09-01). It was opt-in via
    # WVB_TAILNET=1, and a restart from a shell without that variable
    # silently dropped the phone listener -- localhost kept working, so
    # nothing looked broken from the machine, and Cody's iPhone link just
    # died. Same failure class as the API key read at launch. The tailnet is
    # his own devices only; opt OUT with WVB_TAILNET=0.
    if os.environ.get("WVB_TAILNET", "1") != "0":
        info = tailscale_self()
        if not info:
            print("  tailnet: REQUESTED but Tailscale is not reachable "
                  "-- serving on 127.0.0.1 only")
        else:
            tips, tname = info
            bound = []
            for tip in tips:
                try:
                    if ":" in tip:
                        srv6 = _V6Server((tip, PORT_IN_USE), Handler)
                    else:
                        srv6 = ThreadingHTTPServer((tip, PORT_IN_USE), Handler)
                except OSError as exc:
                    print("  tailnet: could not bind %s:%d (%s)"
                          % (tip, PORT_IN_USE, exc))
                    continue
                threading.Thread(target=srv6.serve_forever,
                                 daemon=True).start()
                bound.append(tip)
                ts_srv = srv6
            tip = bound[0] if bound else None
            if bound:
                # ⚠ TAILSCALE PRESERVES THE ORIGINAL Host HEADER, so the
                # trusted-host allowlist has to know these two names or the
                # phone gets a refusal that looks like the server is down.
                # ⚠ REBOUND, NOT MUTATED. TRUSTED_HOSTS is a frozenset on
                # purpose -- it is a security allowlist and nothing should be
                # able to bolt an entry onto it at runtime. Adding these two
                # names is a deliberate, single, opt-in widening.
                # ⚠ AN IPv6 HOST HEADER ARRIVES IN BRACKETS. Safari sends
                # `Host: [fd7a:...]:8799`, and _host_only() strips them -- so
                # the bare form is what the allowlist must hold.
                globals()["TRUSTED_HOSTS"] = frozenset(
                    set(TRUSTED_HOSTS) | set(bound) |
                    set([tname] if tname else []))
                print("  tailnet: http://%s:%d/START-HERE.html"
                      % (tname or tip, PORT_IN_USE))
                for b in bound:
                    print("           (or http://%s:%d/START-HERE.html)"
                          % (("[%s]" % b) if ":" in b else b, PORT_IN_USE))
                print("           reachable from your own devices only, on "
                      "any network. Not the LAN, not the internet.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        CACHE.stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
