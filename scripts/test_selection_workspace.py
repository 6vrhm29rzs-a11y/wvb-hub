#!/usr/bin/env python3
"""mail 103 guards: the selection board (ranks 1-60 + AQs below), status labels, bid-based field counts, the
two-team resume comparison (actual vs projection inputs, reconciled to the record source), scenario separation,
rendered phone/desktop views when the local server is up, and public privacy."""
import json, os, re, sys, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")   # mail 105: an isolated copy serves on its own port
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
os.environ["WVB_POWER_DEFAULT"] = "candidate"
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


import build_hub as B, build_rankings_board as BOARD
from reconcile_2025 import norm as _n
teams, field, *_ = BOARD.build()
ct, scen, _ = B.conf_tournaments(teams)
views = {"now": B.rpi_cutline(teams, field), "proj": B.rpi_cutline(teams, field, ranking="projected"),
         "post": B.rpi_cutline(teams, field, ranking="post", scenario=scen)}
for v, c in views.items():
    bd = c["board"]; ranks = [b["rank"] for b in bd]
    top = [b for b in bd if b["rank"] <= 60]
    check(sorted(set(b["rank"] for b in top)) == sorted(b["rank"] for b in top) and len(top) >= 58,
          "%s: board lists every ranked team 1-60 (%d rows; ties allowed)" % (v, len(top)))
    check(all(b["status"] in ("AQ", "At-large") for b in bd if b["rank"] > 60), "%s: below 60 only field teams (AQs / deep at-large)" % v)
    fset = set(r["team"] for r in c["field"])
    check(set(b["team"] for b in bd if b["status"] in ("AQ", "At-large")) == fset and len(fset) == 64,
          "%s: board AQ + at-large == the 64-team field, counts from bids" % v)
    check(all(b["status"] == "Out" or b["status"] == "Ineligible" or b["team"] in fset for b in bd), "%s: every status consistent" % v)
    check(all(b["why"] for b in bd if b["status"] == "Ineligible"), "%s: every ineligible row states why" % v)
    check(ranks == sorted(ranks), "%s: board in rank order" % v)
    # resume reconciliation: actual W-L equals the at-large gate's counted record (same chain)
    recs = B.cut_records(projected=False)
    bad = [t for t, r in c["resumes"].items() if (lambda x: x and (sum(m[2] == "W" for m in r["actual"]), sum(m[2] == "L" for m in r["actual"])) != (x["w"], x["l"]))(recs.get(_n(t)))]
    check(not bad, "%s: every resume's actual W-L equals the counted record (%s)" % (v, bad[:3]))
    check(all(m[7] for r in c["resumes"].values() for m in r["actual"]), "%s: every actual line carries its game id" % v)
    if v == "now":
        check(all(not r["proj"] for r in c["resumes"].values()), "now: no projection inputs in today's view")
    else:
        check(any(r["proj"] for r in c["resumes"].values()), "%s: projection inputs present and separate" % v)
    if v == "post":
        check(any(m[6] == "conference tournament scenario" for r in c["resumes"].values() for m in r["proj"]), "post: scenario tournament matches labelled")
    # opponent ranks are this view's ranks
    rk = dict((b["team"], b["rank"]) for b in bd)
    mis = [(t, m[1]) for t, r in c["resumes"].items() for m in r["actual"] if m[1] in rk and m[4] != rk[m[1]]]
    check(not mis, "%s: opponent ranks are this view's ranks (%s)" % (v, mis[:2]))
# a real pair: head-to-head symmetry and common opponents both ways
c = views["now"]; a, b = c["last_in"]["team"], c["first_out"][0]["team"]
ra, rb = c["resumes"][a]["actual"], c["resumes"][b]["actual"]
h_ab = sorted(m[7] for m in ra if m[1] == b); h_ba = sorted(m[7] for m in rb if m[1] == a)
check(h_ab == h_ba, "real pair %s v %s: head-to-head identical from both sides (%d)" % (a, b, len(h_ab)))
for m in ra:
    if m[1] == b:
        mb = [x for x in rb if x[7] == m[7]][0]
        check({m[2], mb[2]} == {"W", "L"} and m[3] == "-".join(reversed(mb[3].split("-"))), "real pair: H2H result mirrored (%s)" % m[7])
com = set(m[1] for m in ra) & set(m[1] for m in rb) - {a, b}
print("INFO %s v %s: %d actual / %d actual, %d common opponents" % (a, b, len(ra), len(rb), len(com)))
# rendered
html = open(os.path.join(REPO, "Cody", "START-HERE.html"), encoding="utf-8").read()
check(html.count('class="panel cl-cmp"') == 3, "page: one comparison per scenario view")
pub = open(os.path.join(REPO, "output", "vb_dashboard.html"), encoding="utf-8").read()
check("cl-cmp" not in pub and "window.CLD" not in pub and "Compare two r" not in pub, "public build carries no selection workspace")
try:
    urllib.request.urlopen(BASE + "/START-HERE.html", timeout=5); served = True
except Exception:
    served = False
if served:
    import asyncio, shutil, subprocess, tempfile, base64
    CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    shots = os.path.join(REPO, "Cody", "coordination", "research", "POWER-PREVIEW-2026-11-05")
    async def drive():
        import websockets
        prof = tempfile.mkdtemp(prefix="swprobe-"); out = {}
        p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9343", "--user-data-dir=" + prof, "about:blank"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try: tabs = json.load(urllib.request.urlopen("http://localhost:9343/json")); break
                except Exception: time.sleep(.3)
            async with websockets.connect([x for x in tabs if x["type"] == "page"][0]["webSocketDebuggerUrl"], max_size=10 ** 9) as ws:
                mid = [0]; errs = []
                async def call(m, par=None):
                    mid[0] += 1; await ws.send(json.dumps({"id": mid[0], "method": m, "params": par or {}}))
                    while True:
                        rr = json.loads(await ws.recv())
                        if rr.get("method") == "Runtime.exceptionThrown": errs.append(rr["params"]["exceptionDetails"].get("text"))
                        if rr.get("id") == mid[0]: return rr.get("result", {})
                await call("Runtime.enable")
                for name, w_, mob in (("phone-360", 360, True), ("phone-430", 430, True), ("desktop-1440", 1440, False)):
                    errs.clear()
                    await call("Emulation.setDeviceMetricsOverride", {"width": w_, "height": 900, "deviceScaleFactor": 2, "mobile": mob})
                    res = {}
                    for route, pid in (("#/bracket/cutline", "cl-now"), ("#/bracket/cutline/projected", "cl-proj"), ("#/bracket/cutline/post", "cl-post")):
                        await call("Page.navigate", {"url": BASE + "/START-HERE.html" + route}); await asyncio.sleep(6)
                        js = ("(()=>{const P=document.getElementById('%s');const box=P.querySelector('.cl-cmp');const col=[...box.querySelectorAll('.cl-col h5')].map(x=>x.textContent);"
                              "const st=[...P.querySelectorAll('.cl-t .cl-s')].map(x=>x.getBoundingClientRect()).filter(r=>r.width>0);"
                              "box.scrollIntoView();const D=window.CLD[box.dataset.pid];return JSON.stringify({vis:!P.hidden,nb:D.board.length,a0:D.a,b0:D.b,cols:col,proj:box.querySelectorAll('.cl-proj').length,"
                              "rows:P.querySelectorAll('.cl-t tbody tr.cl-aq,.cl-t tbody tr.cl-al,.cl-t tbody tr.cl-out,.cl-t tbody tr.cl-inel').length,"
                              "line:P.querySelectorAll('.cl-t tr.cl-line').length,stv:st.length,stright:Math.max(...st.map(r=>r.right)),"
                              "w:innerWidth,d:document.documentElement.scrollWidth})})()") % pid
                        rv = await call("Runtime.evaluate", {"expression": js, "returnByValue": True})
                        res[pid] = json.loads(rv["result"]["value"])
                        sh = await call("Page.captureScreenshot", {"format": "png"})
                        open(os.path.join(shots, "sw-%s-%s.png" % (pid, name)), "wb").write(base64.b64decode(sh["data"]))
                    out[name] = (res, list(errs))
        finally:
            p.terminate(); shutil.rmtree(prof, ignore_errors=True)
        return out
    for name, (res, errs) in asyncio.run(drive()).items():
        dw = int(name.split("-")[1])
        for pid, r in res.items():
            exp = views[{"cl-now": "now", "cl-proj": "proj", "cl-post": "post"}[pid]]
            check(r["vis"] and r["rows"] == r["nb"] and r["line"] == 1, "%s %s: board renders %d rows, one cut line" % (name, pid, r["rows"]))
            check(r["cols"] == [r["a0"], r["b0"]] and r["a0"] and r["b0"], "%s %s: comparison defaults to last in v first out %s" % (name, pid, r["cols"]))
            check((r["proj"] == 2) == (pid != "cl-now"), "%s %s: projection inputs shown only in projected views" % (name, pid))
            check(r["d"] <= dw and r["stv"] > 0 and r["stright"] <= dw, "%s %s: fits width, status labels visible (%s)" % (name, pid, r))
        check(not errs, "%s: no script errors %s" % (name, errs[:2]))
else:
    print("SKIP rendered checks: local server unavailable")
print("ALL SELECTION WORKSPACE CHECKS HOLD" if ok else "SELECTION WORKSPACE CHECKS FAILED")
sys.exit(0 if ok else 1)
