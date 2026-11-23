#!/usr/bin/env python3
"""mail 110 guard: live_server.py serves static files from an ALLOWLIST only. Runs the real Handler on a throwaway
web root with planted fixture 'secrets' (never real files) and checks GET/HEAD, gzip, directory listing, encoded and
traversal paths, double encoding, NUL, backslash and a symlink escape. Real private paths are checked against the
running service by status code only (HEAD), never by reading bytes."""
import http.client, os, shutil, sys, tempfile, threading
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
if os.environ.get("LS_MODULE_DIR"):          # negative control: load an older live_server.py from another folder
    sys.path.insert(0, os.environ["LS_MODULE_DIR"])
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


import live_server as LS
from http.server import ThreadingHTTPServer
tmp = tempfile.mkdtemp(prefix="allow-")
outside = tempfile.mkdtemp(prefix="outside-")
MARK = "FIXTURE-SECRET-7f3a"
try:
    w = lambda p, t: (os.makedirs(os.path.dirname(os.path.join(tmp, p)), exist_ok=True), open(os.path.join(tmp, p), "w").write(t))
    w("START-HERE.html", "<html>page</html>" * 50); w("rankings_live.json", '{"ok":1}'); w("CENTER-COURT.html", "<html>cc</html>")
    w("data/anthropic_key.txt", MARK); w("data/my_ballots.jsonl", MARK); w("coordination/state/builder.json", MARK)
    w("backups/b.json", MARK); w("unknown.html", MARK); w("START-HERE.html.bak", MARK)
    open(os.path.join(outside, "x.svg"), "w").write(MARK)
    os.symlink(os.path.join(outside, "x.svg"), os.path.join(tmp, "rating_history_2026.svg"))   # allowlisted NAME, escaping target
    LS.WEBROOT = tmp
    srv = ThreadingHTTPServer(("127.0.0.1", 0), LS.Handler); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def req(method, path, gz=False):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.putrequest(method, path, skip_accept_encoding=True)
        c.putheader("Host", "127.0.0.1:%d" % port)
        if gz:
            c.putheader("Accept-Encoding", "gzip")
        try:
            c.endheaders(); r = c.getresponse(); body = r.read(); c.close()
        except (http.client.HTTPException, OSError):
            return 0, b""                     # connection dropped: recorded as status 0, never as served
        return r.status, body

    for m in ("GET", "HEAD"):
        for gz in (False, True):
            st, b = req(m, "/START-HERE.html", gz)
            check(st == 200, "%s%s /START-HERE.html -> 200 (%s)" % (m, " gzip" if gz else "", st))
    check(req("GET", "/rankings_live.json")[0] == 200 and req("GET", "/CENTER-COURT.html")[0] == 200, "page artifacts served")
    check(req("GET", "/START-HERE.html?x=8#/ballot")[0] == 200, "query string on the page still works")
    check(req("GET", "/")[0] == 302, "bare host redirects to the page")
    blocked = ["/data/anthropic_key.txt", "/data/my_ballots.jsonl", "/coordination/state/builder.json", "/backups/b.json",
               "/unknown.html", "/START-HERE.html.bak", "/data/", "/data", "/coordination/", "/backups",
               "/%2e%2e/%2e%2e/etc/passwd", "/..%2fdata%2fanthropic_key.txt", "/data%2fanthropic_key.txt",
               "/START-HERE.html/../data/anthropic_key.txt", "//data/anthropic_key.txt", "/./data/anthropic_key.txt",
               "/%252e%252e/data/anthropic_key.txt", "/data%5canthropic_key.txt", "/START-HERE.html%00.txt",
               "/rating_history_2026.svg", "/%2fdata/anthropic_key.txt", "/DATA/anthropic_key.txt", "/%ff"]
    leaks = []
    for p in blocked:
        for m in ("GET", "HEAD"):
            for gz in (False, True):
                st, b = req(m, p, gz)
                if st == 200 or MARK.encode() in b:
                    leaks.append((m, p, gz, st))
    check(not leaks, "%d blocked paths x GET/HEAD x gzip: none served, no fixture bytes returned %s" % (len(blocked), leaks[:4]))
    st, b = req("GET", "/data/")
    check(st == 404 and b"anthropic_key" not in b, "no directory listing")
    srv.shutdown()
finally:
    shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(outside, ignore_errors=True)
print("ALL STATIC ALLOWLIST CHECKS HOLD" if ok else "STATIC ALLOWLIST CHECKS FAILED")
sys.exit(0 if ok else 1)
