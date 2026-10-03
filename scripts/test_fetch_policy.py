#!/usr/bin/env python3
"""fetch_policy: blocked hosts refused BEFORE every hop (mail 054).
Blocked destinations are exercised only through a LOCAL redirecting server;
no request is ever sent to a blocked host."""
import http.server, os, socket, sys, threading, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fetch_policy as FP
FAIL = []
def check(n, ok, x=""):
    print("  %-72s %s%s" % (n, "ok" if ok else "FAIL", ("  " + x) if x else ""))
    if not ok: FAIL.append(n)

B = "https://stats.statbroadcast.com/broadcast/?id=1"
check("list is read from the hook itself", "statbroadcast.com" in FP.blocked_hosts())
for url, want in ((B, True),
                  ("https://stats.statbroadcast.com:443/x", True),
                  ("https://user:pw@stats.statbroadcast.com/x", True),
                  ("HTTPS://Stats.StatBroadcast.COM/x", True),
                  ("https://statbroadcast.com/", True),
                  ("https://stats.ncaa.org/game/1", True),
                  ("https://notstatbroadcast.com/", False),
                  ("https://statbroadcast.com.example.org/", False),
                  ("https://purduesports.com/boxscore/1", False),
                  ("not a url", True)):
    check("is_blocked(%s) == %s" % (url[:46], want), FP.is_blocked(url) is want)
try:
    FP.blocked_hosts("/nonexistent/no_scrape.py"); closed = False
except FP.PolicyUnavailable:
    closed = True
check("fail closed: an unloadable hook raises PolicyUnavailable (refuse everything)", closed)

# ---- local server: /ok, /redir -> blocked, /chain -> /redir2 -> blocked
hits = []
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        hits.append(self.path)
        if self.path == "/ok":
            self.send_response(200); self.end_headers(); self.wfile.write(b"fine")
        elif self.path == "/redir":
            self.send_response(302); self.send_header("Location", B); self.end_headers()
        elif self.path == "/redir-port":
            self.send_response(301); self.send_header("Location", "https://Stats.StatBroadcast.com:443/y"); self.end_headers()
        elif self.path == "/chain":
            self.send_response(302); self.send_header("Location", "/chain2"); self.end_headers()
        elif self.path == "/chain2":
            self.send_response(307); self.send_header("Location", B); self.end_headers()
        elif self.path == "/local-ok-chain":
            self.send_response(302); self.send_header("Location", "/ok"); self.end_headers()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = http.server.HTTPServer(("127.0.0.1", port), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % port
# guard: any attempt to open a blocked host at the socket layer is recorded
real_create = socket.create_connection
attempts = []
def guarded(addr, *a, **k):
    if "statbroadcast" in str(addr[0]).lower():
        attempts.append(addr); raise OSError("test guard: blocked host would have been contacted")
    return real_create(addr, *a, **k)
socket.create_connection = guarded
try:
    check("ordinary allowed request succeeds", FP.urlopen(base + "/ok", timeout=5).read() == b"fine")
    check("allowed redirect chain still succeeds", FP.urlopen(base + "/local-ok-chain", timeout=5).read() == b"fine")
    for path, label in (("/redir", "redirect to a blocked host"), ("/redir-port", "redirect to blocked host, explicit port + mixed case"),
                        ("/chain", "chained redirects ending at a blocked host")):
        try:
            FP.urlopen(base + path, timeout=5); ok = False
        except FP.BlockedURL:
            ok = True
        check("%s is refused" % label, ok)
    try:
        FP.urlopen(B, timeout=5); ok = False
    except FP.BlockedURL:
        ok = True
    check("direct request to a blocked host is refused", ok)
    check("NO connection to a blocked host was attempted at the socket layer", attempts == [], str(attempts))
    # [NEG] the stock urllib opener WOULD have followed the redirect
    try:
        urllib.request.urlopen(base + "/redir", timeout=5)
    except Exception:
        pass
    check("[NEG] stock urlopen follows the same redirect toward the blocked host (guard caught it)", len(attempts) == 1)
finally:
    socket.create_connection = real_create
    srv.shutdown()
# every retrofitted fetcher routes through the policy
for f in ("verify_results_daily", "crawl_rosters", "crawl_tv", "collector", "gamebook_census", "gamebook_pilot",
          "crawl_team_colors", "crawl_aq", "ingest_monsterblock", "watch_sources", "crawl_avca_rv", "audit_intel_media", "intel"):
    src = open(os.path.join(HERE, f + ".py")).read()
    check("%s routes through fetch_policy (no bare urllib.request.urlopen)" % f,
          "fetch_policy" in src and "urllib.request.urlopen(" not in src)
print("FAILED: %s" % FAIL if FAIL else "ALL FETCH-POLICY CHECKS HOLD"); sys.exit(1 if FAIL else 0)
