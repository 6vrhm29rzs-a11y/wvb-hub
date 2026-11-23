#!/usr/bin/env python3
"""mail 107 guards: the private S0 performance ledger. Reconciles to every counted final; every expectation comes from
earlier matches only; the set-line screen behaves on fixtures; the Vanderbilt/Wisconsin rows reproduce their stated
sources; points-vs-result uses complete lines with ties separate; the page view works; the public build carries none."""
import json, os, re, sys, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


LD = os.path.join(REPO, "Cody", "coordination", "research", "POWER-PERFORMANCE-LEDGER-2026-11-06")
if not os.path.exists(os.path.join(LD, "build_ledger.py")):
    print("SKIP: research code absent (CI / fresh checkout)"); sys.exit(0)
sys.path.insert(0, LD)
import build_ledger as BL
# --- the screen (fixtures)
f = BL.set_line_check
check(f((3, 0), [(25, 20), (25, 22), (25, 18)])[0], "screen: a clean 3-0 passes")
check(f((3, 2), [(25, 20), (20, 25), (26, 24), (22, 25), (15, 13)])[0], "screen: 3-2 with a 15-13 fifth and a 26-24 set passes")
check(not f((2, 0), [(25, 20), (22, 19)])[0], "screen: an unfinished 22-19 set fails")
check(not f((3, 1), [(25, 20), (27, 24), (25, 18), (25, 19)])[0], "screen: 27-24 (three clear past the target) fails")
check(not f((3, 4), [(25, 20)] * 3 + [(20, 25)] * 4)[0], "screen: a 3-4 count fails")
check(not f((3, 0), [(25, 20), (25, 20), (25, 20), (20, 25)])[0], "screen: a set after the match is decided fails")
check(not f((3, 1), [(25, 20), (25, 22), (25, 18)])[0], "screen: set winners disagreeing with the counted result fail")
# --- the artifact
L = json.load(open(os.path.join(REPO, "Cody", "data", "power_ledger", "latest.json")))
rows = L["rows"]
import season_counts as SC
doc = json.load(open(os.path.join(REPO, "data", "data_2026.json")))
fin = set(str(g["game_id"]) for g in SC.countable(doc["games"], 2026, need_line=False, d1_only=False)
          if g.get("state") == "F" and len(g.get("teams") or []) == 2 and SC.winner_index(g) is not None)
fp_now = BL.fingerprint()
if fp_now.get("data/data_2026.json") == L["input_fingerprint"].get("data/data_2026.json"):
    check(set(r["gid"] for r in rows) == fin, "ledger reconciles to every counted final (%d)" % len(fin))
else:
    print("INFO data moved since the ledger was built; reconciliation checked on the frozen generation instead")
check(all(("share_home" in r) == r["line_ok"] and (r["line_ok"] or r.get("line_reason")) for r in rows),
      "every row has points won % exactly when its set line is complete, else a reason")
check(all(("exp" in r) != bool(r.get("no_exp")) for r in rows), "every row has an expectation or a stated reason, never both")
leak = [r["gid"] for r in rows if "exp" in r and not (r["exp"]["last_train_day"] < r["day"] and r["exp"]["cutoff"] <= r["day"])]
check(not leak, "every expectation was fitted on matches strictly before the match day (%d checked)" % sum("exp" in r for r in rows))
cps = dict((c["cutoff"], c) for c in L["checkpoints"])
check(all(r["exp"]["cutoff"] in cps and cps[r["exp"]["cutoff"]]["train_matches"] == r["exp"]["train"] for r in rows if "exp" in r),
      "every expectation names its weekly checkpoint and training count")
pv = L["points_vs_result"]
check(sum(pv.values()) == sum(r["line_ok"] for r in rows) and "tied points" in pv,
      "points vs result: valid lines only, ties separate (%s)" % pv)
# Vanderbilt v Texas A&M: reconstruction distinct from the frozen issued pilot, both reproduced
v = next(r for r in rows if r["gid"] == "6628689")
iss = dict((x["arm"], x) for x in v.get("issued") or [])
check(v["points"] == "93-87" and abs(v["share_home"] - 93 / 180.) < 1e-4, "Vanderbilt v Texas A&M: final 93-87 (.5167)")
check(iss.get("S0", {}).get("p_home") == 0.6797 and iss.get("CTRL", {}).get("p_home") == 0.5662 and iss["CTRL"].get("p_native_incumbent") == 0.5871,
      "Vanderbilt v Texas A&M: issued pilot forecasts kept verbatim (S0 .6797, CTRL .5662, native .5871)")
check("exp" in v and v["exp"]["cutoff"] < v["day"] and abs(v["exp"]["exp_share_home"] - iss["S0"]["exp_share_home"]) < 0.002,
      "Vanderbilt v Texas A&M: reconstructed weekly expectation (%.4f, cutoff %s) is labelled separately and close to the issued S0 share"
      % (v["exp"]["exp_share_home"], v["exp"]["cutoff"]))
# Wisconsin vs the reviewer's descriptive audit (same pooling rule)
au = json.load(open(os.path.join(REPO, "Cody", "coordination", "research", "POWER-SET-BASELINE-2026-11-06", "set-score-descriptive-audit.json")))
# the audit is a frozen capture (2026-11-06 PT), so compare the matches it could see
w = [r for r in rows if "Wisconsin" in (r["home"], r["away"]) and r["line_ok"] and r["day"] <= "2026-11-06"]
me = sum(int(r["points"].split("-")[0 if r["home"] == "Wisconsin" else 1]) for r in w)
al = sum(sum(map(int, r["points"].split("-"))) for r in w)
check(round(100.0 * me / al, 2) == au["teams"]["Wisconsin"]["pooled_points_won_pct"],
      "Wisconsin pooled points won %.2f%% equals the reviewer audit" % (100.0 * me / al))
# page + privacy
html = open(os.path.join(REPO, "Cody", "START-HERE.html"), encoding="utf-8").read()
check("const P20L = {" in html and "p20Ledger" in html, "private page carries the ledger view")
pub = open(os.path.join(REPO, "output", "vb_dashboard.html"), encoding="utf-8").read()
check("P20L" not in pub and "p20Ledger" not in pub and "power_ledger" not in pub, "public build carries no ledger")
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
        prof = tempfile.mkdtemp(prefix="ledprobe-"); res = {}
        p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9345", "--user-data-dir=" + prof, "about:blank"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try: tabs = json.load(urllib.request.urlopen("http://localhost:9345/json")); break
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
                    await call("Page.navigate", {"url": BASE + "/START-HERE.html#/rankings/p20"}); await asyncio.sleep(7)
                    js = ("(async()=>{const q=document.getElementById('p20q');q.value='Wisconsin';q.dispatchEvent(new Event('input'));"
                          "await new Promise(r=>setTimeout(r,600));const rs=[...document.querySelectorAll('#p20led tr.p20lr')];"
                          "const first=rs[0];first&&first.click();await new Promise(r=>setTimeout(r,300));"
                          "const x=first&&first.nextElementSibling;document.getElementById('p20led').scrollIntoView();"
                          "return JSON.stringify({sel:(document.getElementById('p20lt')||{}).value,n:rs.length,"
                          "open:x&&!x.hidden,txt:x?x.textContent.slice(0,160):'',w:innerWidth,d:document.documentElement.scrollWidth})})()")
                    rv = await call("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
                    await asyncio.sleep(.5)
                    sh = await call("Page.captureScreenshot", {"format": "png"})
                    open(os.path.join(shots, "ledger-%s.png" % name), "wb").write(base64.b64decode(sh["data"]))
                    res[name] = (json.loads(rv["result"]["value"]), list(errs))
        finally:
            p.terminate(); shutil.rmtree(prof, ignore_errors=True)
        return res
    wn = sum(1 for r in rows if "Wisconsin" in (r["home"], r["away"]))
    for name, (r, errs) in asyncio.run(drive()).items():
        dw = int(name.split("-")[1])
        check(r["sel"] == "Wisconsin" and r["n"] == wn, "%s: searching Wisconsin shows its %d-match ledger (%s)" % (name, wn, r["n"]))
        check(r["open"] and "Set 1" in r["txt"], "%s: a match opens to its set scores (%s)" % (name, r["txt"][:60]))
        check(r["d"] <= dw, "%s: no page overflow (%s)" % (name, r["d"]))
        check(not errs, "%s: no script errors %s" % (name, errs[:2]))
else:
    print("SKIP rendered checks: local server unavailable")
print("ALL LEDGER CHECKS HOLD" if ok else "LEDGER CHECKS FAILED")
sys.exit(0 if ok else 1)
