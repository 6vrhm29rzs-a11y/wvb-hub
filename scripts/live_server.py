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
import sys
import time
import threading
import datetime
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

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


def _get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _et_now():
    return datetime.datetime.now(ET) if ET else datetime.datetime.utcnow()


def _fmt_time(epoch):
    if not epoch or not ET:
        return ""
    return datetime.datetime.fromtimestamp(int(epoch), ET).strftime("%-I:%M %p ET")


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
                    "time": _fmt_time(g.get("startTimeEpoch")),
                    "period": g.get("currentPeriod") or "",
                    "away": (a.get("names") or {}).get("short"),
                    "home": (h.get("names") or {}).get("short"),
                    "away_rank": a.get("rank") or "",
                    "home_rank": h.get("rank") or "",
                    "away_sets": a.get("score") or "0",
                    "home_sets": h.get("score") or "0",
                    "sets": [],
                    "venue": "",
                })

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

        with self.lock:
            # Keep the last good payload on a failed cycle rather than blanking
            # the board -- a momentary upstream hiccup should not look like
            # "no games tonight".
            if games or not self.payload.get("games"):
                self.payload = {
                    "games": games,
                    "updated": _et_now().strftime("%-I:%M:%S %p ET"),
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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        kw["directory"] = WEBROOT
        SimpleHTTPRequestHandler.__init__(self, *a, **kw)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/live":
            body = json.dumps(CACHE.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return SimpleHTTPRequestHandler.do_GET(self)

    def log_message(self, fmt, *args):
        pass                                          # keep the console quiet


def main():
    if not os.path.isdir(WEBROOT):
        print("no %s -- run scripts/build_hub.py first" % WEBROOT)
        return 1
    t = threading.Thread(target=CACHE.run)
    t.daemon = True
    t.start()

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d/START-HERE.html" % PORT
    print("live scoreboard running")
    print("  open: %s" % url)
    print("  refreshing every %ds -- one upstream request per cycle" % REFRESH_SECONDS)
    print("  ctrl-c to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        CACHE.stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
