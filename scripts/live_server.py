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


_HUB = [None]


def _hub():
    """build_hub, imported lazily. It owns the one rule for displaying a time."""
    if _HUB[0] is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import build_hub
        _HUB[0] = build_hub
    return _HUB[0]


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


# ------------------------------------------------------------------ Digby
# The chat endpoint. It exists here rather than in the page because the API key
# must never reach the browser: the page asks this process, this process holds
# the key, and the key comes from the environment and is never written down.
#
# THIS SERVER BINDS TO 127.0.0.1 AND MUST STAY THAT WAY. The moment it answers
# on a routable address, anything on the network can spend the key. The Host
# check below is the second lock -- it stops a DNS-rebinding page in the
# browser from reaching an endpoint that only expects to hear from localhost.

DIGBY_MAX_BODY = 4096
DIGBY_MIN_GAP = float(os.environ.get("WVB_DIGBY_MIN_GAP", "2"))
DIGBY_MAX_PER_RUN = int(os.environ.get("WVB_DIGBY_MAX", "200"))
_digby = {"last": 0.0, "count": 0, "index": None, "teams": None,
          "mtimes": {}}
_digby_lock = threading.Lock()


def _digby_answer(question):
    """One question -> a dict for the page. Never raises."""
    try:
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
        r["answer"] = ("Digby has no API key. This server was started without "
                       "one \u2014 stop it, then restart it with:\n"
                       "    export ANTHROPIC_API_KEY=sk-ant-<your key>\n"
                       "    python3 scripts/live_server.py\n"
                       "Everything else on the page works without it.")
    return r


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        kw["directory"] = WEBROOT
        SimpleHTTPRequestHandler.__init__(self, *a, **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _is_local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "[::1]", "::1")

    def do_POST(self):
        if self.path.split("?")[0] != "/api/digby":
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


def main():
    if not os.path.isdir(WEBROOT):
        print("no %s -- run scripts/build_hub.py first" % WEBROOT)
        return 1
    t = threading.Thread(target=CACHE.run)
    t.daemon = True
    t.start()

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
    # Say plainly whether the chat will work, at the moment it can still be
    # fixed. Finding out by clicking the button and reading an error is worse.
    if (os.environ.get("ANTHROPIC_API_KEY") or "").startswith("sk-ant-"):
        print("  Ask Digby: ready")
    else:
        print("  Ask Digby: OFF -- no ANTHROPIC_API_KEY in this shell.")
        print("             Everything else on the page works without it.")
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
