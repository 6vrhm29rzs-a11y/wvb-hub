#!/usr/bin/env python3
"""mail 108 tap-through: headless Chrome (Blink engine, NOT iPhone Safari) with mobile emulation at 360/430 and desktop
1440, isolated profile (never Cody's ballot; ballot is opened read-only). Private page via the served local route,
public page from its file. Smoke every top-level route; deep paths: Current POWER -> Oregon team page -> back,
POWER 2.0 Wisconsin/Vanderbilt ledger and the Vanderbilt v Texas A&M match details, Scores date/prev/next/open match/
revisit/reload, live poll failure and recovery. Checks DOM bounds, overflow, console errors, and saves screenshots."""
import asyncio, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SHOTS = os.path.join(REPO, "Cody", "coordination", "research", "POWER-PREVIEW-2026-11-05", "tap108")
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


_ledger = json.load(open(os.path.join(REPO, "Cody", "data", "power_ledger", "latest.json")))
_wisc_expected = sum(1 for x in _ledger["rows"] if "Wisconsin" in (x["home"], x["away"]))

async def session(port, fn):
    import websockets
    prof = tempfile.mkdtemp(prefix="tap108-")
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof,
                          "--allow-file-access-from-files", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try: tabs = json.load(urllib.request.urlopen("http://localhost:%d/json" % port)); break
            except Exception: time.sleep(.3)
        async with websockets.connect([x for x in tabs if x["type"] == "page"][0]["webSocketDebuggerUrl"], max_size=10 ** 9) as ws:
            st = {"mid": 0, "errs": []}
            async def call(m, par=None):
                st["mid"] += 1; i = st["mid"]; await ws.send(json.dumps({"id": i, "method": m, "params": par or {}}))
                while True:
                    rr = json.loads(await ws.recv())
                    if rr.get("method") == "Runtime.exceptionThrown": st["errs"].append(rr["params"]["exceptionDetails"].get("text") + " " + str(rr["params"]["exceptionDetails"].get("exception", {}).get("description", ""))[:160])
                    if rr.get("id") == i: return rr.get("result", {})
            async def ev(js, wait=True):
                r = await call("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": wait})
                v = r.get("result", {}).get("value")
                if isinstance(v, str):
                    try:
                        return json.loads(v)
                    except ValueError:
                        return v
                return v
            async def shot(name):
                os.makedirs(SHOTS, exist_ok=True)
                s = await call("Page.captureScreenshot", {"format": "png"})
                open(os.path.join(SHOTS, name + ".png"), "wb").write(base64.b64decode(s["data"]))
            await call("Runtime.enable"); await call("Network.enable")
            return await fn(call, ev, shot, st)
    finally:
        p.terminate(); shutil.rmtree(prof, ignore_errors=True)


WAIT = "(async(c,n)=>{for(let i=0;i<(n||300);i++){if(eval(c))return true;await new Promise(r=>setTimeout(r,50));}return false;})"


async def private_run(call, ev, shot, st):
    res = {}
    for name, w, mob in (("phone-360", 360, True), ("phone-430", 430, True), ("desktop-1440", 1440, False)):
        r = res[name] = {}
        st["errs"].clear()
        await call("Emulation.setDeviceMetricsOverride", {"width": w, "height": 860, "deviceScaleFactor": 2, "mobile": mob})
        await call("Page.navigate", {"url": BASE + "/START-HERE.html#/rankings"})
        await ev(WAIT + "(\"document.readyState==='complete' && !!document.querySelector('[data-team=\\\"Oregon\\\"]')\",400)")
        await asyncio.sleep(2)
        r["nodes"] = await ev("JSON.stringify(document.getElementsByTagName('*').length)")
        r["scores_nodes_hidden"] = await ev("JSON.stringify(document.getElementById('v-scores').getElementsByTagName('*').length)")
        # smoke every top-level route
        routes = await ev("JSON.stringify(Object.values(ROUTE_OF_VIEW))")
        smoke = {}
        for rt in routes or []:
            await ev("location.hash='#/%s'" % rt, False); await asyncio.sleep(1.2)
            smoke[rt] = await ev("JSON.stringify({vis:[...document.querySelectorAll('main > section')].filter(s=>!s.hidden).map(s=>s.id), d:document.documentElement.scrollWidth, w:innerWidth})")
        r["smoke"] = smoke
        # Current POWER -> Oregon -> back
        await ev("location.hash='#/rankings'", False); await asyncio.sleep(1.5)
        await ev("(()=>{const e=[...document.querySelectorAll('[data-team=\"Oregon\"]')].find(x=>x.offsetParent!==null);e.scrollIntoView({block:'center'});})()", False)
        await asyncio.sleep(.5); y0 = await ev("JSON.stringify(Math.round(scrollY))")
        await ev("[...document.querySelectorAll('[data-team=\"Oregon\"]')].find(x=>x.offsetParent!==null).click()", False)
        r["oregon_open"] = await ev(WAIT + "(\"location.hash.indexOf('teams/oregon')>=0 && (document.querySelector('#teamcard')||{textContent:''}).textContent.length>500\",200)")
        await asyncio.sleep(1); await shot("oregon-team-" + name)
        await ev("window.scrollTo(0, document.documentElement.scrollHeight)", False); await asyncio.sleep(1)
        await shot("oregon-team-bottom-" + name)
        await ev("history.back()", False)
        r["back_to_rankings"] = await ev(WAIT + "(\"!document.getElementById('v-rankings').hidden && location.hash.indexOf('rankings')>=0\",200)")
        await asyncio.sleep(1); r["scroll_back"] = [y0, await ev("JSON.stringify(Math.round(scrollY))")]
        # POWER 2.0: Wisconsin search, Vanderbilt picker, Vandy-A&M details
        await ev("location.hash='#/rankings/p20'", False)
        await ev(WAIT + "(\"!!document.querySelector('table.p20t tbody tr')\",200)")
        r["p20_paired"] = await ev("JSON.stringify((document.querySelector('table.p20t tbody tr td.st')||{textContent:''}).textContent)")
        r["p20_cols_visible"] = await ev("JSON.stringify([...document.querySelectorAll('table.p20t thead th')].filter(t=>t.offsetWidth>0).length)")
        r["p20_table_fits"] = await ev("JSON.stringify((()=>{const t=document.querySelector('table.p20t');return t.scrollWidth<=t.parentElement.clientWidth+1})())")
        r["picker_above_table"] = await ev("JSON.stringify((()=>{const s=document.getElementById('p20lt'),t=document.querySelector('table.p20t');return !!s && s.getBoundingClientRect().top < t.getBoundingClientRect().top && s.getBoundingClientRect().height>=40})())")
        await ev("(()=>{const q=document.getElementById('p20q');q.value='Wisconsin';q.dispatchEvent(new Event('input'));})()", False)
        await asyncio.sleep(.8)
        r["wisc_rows"] = await ev("JSON.stringify(document.querySelectorAll('#p20led tr.p20lr').length)")
        await ev("(()=>{const q=document.getElementById('p20q');q.value='';q.dispatchEvent(new Event('input'));const s=document.getElementById('p20lt');s.value='Vanderbilt';s.dispatchEvent(new Event('change'));})()", False)
        await asyncio.sleep(.8)
        r["vandy_rows"] = await ev("JSON.stringify(document.querySelectorAll('#p20led tr.p20lr').length)")
        await ev("(()=>{const tr=[...document.querySelectorAll('#p20led tr.p20lr')].find(t=>t.textContent.indexOf('Texas A&M')>=0 && t.textContent.indexOf('11-06')>=0);tr.scrollIntoView({block:'center'});tr.click();})()", False)
        await asyncio.sleep(.6)
        r["vandy_detail"] = await ev("JSON.stringify((()=>{const tr=[...document.querySelectorAll('#p20led tr.p20lr')].find(t=>t.textContent.indexOf('11-06')>=0);const x=tr.nextElementSibling;const td=x.firstElementChild;const tb=tr.closest('table');const box=tb.parentElement;return {open:!x.hidden,txt:td.textContent.slice(0,400),fits:td.scrollWidth<=td.clientWidth+1 && tb.scrollWidth<=box.clientWidth+1 && td.getBoundingClientRect().right<=innerWidth+1}})())")
        await shot("p20-vandy-detail-" + name)
        r["p20_overflow"] = await ev("JSON.stringify(document.documentElement.scrollWidth)")
        # Scores: direct entry, prev/next, open a match, revisit, reload
        await ev("location.hash='#/scores'", False)
        r["scores_open"] = await ev(WAIT + "(\"!document.getElementById('v-scores').hidden && document.querySelectorAll('#sbBody *').length>20\",200)")
        await ev("document.getElementById('sbPrev').click()", False); await asyncio.sleep(.6)
        d1 = await ev("JSON.stringify(document.getElementById('sbDayIso').textContent)")
        await ev("document.getElementById('sbNext').click()", False); await asyncio.sleep(.6)
        d2 = await ev("JSON.stringify(document.getElementById('sbDayIso').textContent)")
        r["scores_prev_next"] = [d1, d2]
        await ev("document.getElementById('sbPrev').click()", False); await asyncio.sleep(.6)
        clicked = await ev("JSON.stringify((()=>{const row=document.querySelector('#sbBody [data-match], #sbBody [data-gid]');if(!row)return null;row.click();return row.getAttribute('data-match')||row.getAttribute('data-gid');})())")
        await asyncio.sleep(1.2)
        r["scores_match_open"] = [clicked, await ev("JSON.stringify(location.hash)"), await ev("JSON.stringify(!!document.querySelector('#scoredetail:not([hidden]), .mdl:not([hidden]), body.mdlopen'))")]
        await shot("scores-match-" + name)
        await ev("history.back()", False); await asyncio.sleep(1)
        r["scores_nodes_visible"] = await ev("JSON.stringify(document.getElementById('v-scores').getElementsByTagName('*').length)")
        await call("Page.reload"); await ev(WAIT + "(\"document.readyState==='complete' && !document.getElementById('v-scores').hidden && document.querySelectorAll('#sbBody *').length>20\",400)")
        r["scores_reload"] = await ev("JSON.stringify(location.hash)")
        await ev("location.hash='#/rankings'", False); await asyncio.sleep(1); await ev("location.hash='#/scores'", False); await asyncio.sleep(1)
        r["scores_revisit"] = await ev("JSON.stringify(document.querySelectorAll('#sbBody *').length)")
        r["errors"] = list(st["errs"])
    # live poll failure, then recovery (desktop width)
    st["errs"].clear()
    await call("Network.setBlockedURLs", {"urls": ["*/api/live*"]})
    await call("Page.navigate", {"url": BASE + "/START-HERE.html#/scores"}); await asyncio.sleep(12)
    res["live_blocked"] = {"errors": list(st["errs"]), "rows": await ev("JSON.stringify(document.querySelectorAll('#sbBody *').length)")}
    st["errs"].clear()
    await call("Network.setBlockedURLs", {"urls": []})
    await call("Page.reload"); await asyncio.sleep(12)
    res["live_ok"] = {"errors": list(st["errs"]), "rows": await ev("JSON.stringify(document.querySelectorAll('#sbBody *').length)")}
    return res


async def public_run(call, ev, shot, st):
    res = {}
    pub = "file://" + os.path.join(REPO, "output", "vb_dashboard.html")
    for name, w, mob in (("phone-360", 360, True), ("desktop-1440", 1440, False)):
        st["errs"].clear()
        await call("Emulation.setDeviceMetricsOverride", {"width": w, "height": 860, "deviceScaleFactor": 2, "mobile": mob})
        await call("Page.navigate", {"url": pub + "#/scores"}); await asyncio.sleep(8)
        routes = await ev("JSON.stringify(Object.values(ROUTE_OF_VIEW))")
        sm = {}
        for rt in routes or []:
            await ev("location.hash='#/%s'" % rt, False); await asyncio.sleep(1)
            sm[rt] = await ev("JSON.stringify({vis:[...document.querySelectorAll('main > section')].filter(s=>!s.hidden).map(s=>s.id), d:document.documentElement.scrollWidth})")
        await ev("location.hash='#/scores'", False); await asyncio.sleep(1.5)
        res[name] = {"smoke": sm, "nodes": await ev("JSON.stringify(document.getElementsByTagName('*').length)"),
                     "sb": await ev("JSON.stringify(document.querySelectorAll('#sbBody *').length)"), "errors": list(st["errs"])}
        await shot("public-scores-" + name)
    return res


def main():
    try:
        urllib.request.urlopen(BASE + "/START-HERE.html", timeout=5)
    except Exception:
        print("SKIP: local server unavailable"); return 0
    pr = asyncio.run(session(9348, private_run))
    for name, r in ((k, v) for k, v in pr.items() if k.startswith(("phone", "desktop"))):
        dw = int(name.split("-")[1])
        bad = dict((k, v) for k, v in r["smoke"].items() if len(v["vis"]) != 1 or v["d"] > dw)
        check(r["smoke"] and not bad, "%s private: all %d top-level routes show exactly one view without overflow %s" % (name, len(r["smoke"]), bad))
        check(r["scores_nodes_hidden"] < 20000, "%s: hidden Scores holds %d elements (was ~112,700)" % (name, r["scores_nodes_hidden"]))
        check(r["oregon_open"] and r["back_to_rankings"], "%s: Current POWER -> Oregon team page -> back to rankings" % name)
        check("cur" in (r["p20_paired"] or "") and r["p20_table_fits"], "%s: POWER 2.0 shows both strengths (%r) and fits" % (name, r["p20_paired"]))
        check(r["picker_above_table"], "%s: Season matches picker sits above the table, touch-sized" % name)
        check(r["wisc_rows"] == _wisc_expected and r["vandy_rows"] >= 20, "%s: Wisconsin %s rows, Vanderbilt %s rows" % (name, r["wisc_rows"], r["vandy_rows"]))
        vd = r["vandy_detail"]
        check(vd["open"] and "Set 1" in vd["txt"] and "Issued forecast" in vd["txt"] and vd["fits"], "%s: Vanderbilt v Texas A&M opens with sets and issued forecasts, no overflow" % name)
        check(r["p20_overflow"] <= dw, "%s: POWER 2.0 page has no horizontal overflow (%s)" % (name, r["p20_overflow"]))
        check(r["scores_open"] and r["scores_prev_next"][0] != r["scores_prev_next"][1], "%s: Scores opens; previous/next day move (%s)" % (name, r["scores_prev_next"]))
        check(r["scores_match_open"][0] is not None, "%s: a Scores match opens (%s)" % (name, r["scores_match_open"]))
        check(r["scores_revisit"] > 20 and "scores" in (r["scores_reload"] or ""), "%s: Scores survives reload and revisit" % name)
        check(not r["errors"], "%s: no script errors %s" % (name, r["errors"][:2]))
    check(not pr["live_blocked"]["errors"] and pr["live_blocked"]["rows"] > 20, "live poll blocked: page still renders, no script errors")
    check(not pr["live_ok"]["errors"] and pr["live_ok"]["rows"] > 20, "live poll restored: page renders, no script errors")
    pb = asyncio.run(session(9349, public_run))
    for name, r in pb.items():
        bad = dict((k, v) for k, v in r["smoke"].items() if len(v["vis"]) != 1)
        check(r["smoke"] and not bad and r["sb"] > 0, "public %s: %d routes each show one view; Scores renders (%d)" % (name, len(r["smoke"]), r["sb"]))
        check(not r["errors"], "public %s: no script errors %s" % (name, r["errors"][:2]))
    json.dump({"private": pr, "public": pb}, open(os.path.join(SHOTS, "tapthrough.json"), "w"), indent=1)
    print("ALL TAP-THROUGH CHECKS HOLD" if ok else "TAP-THROUGH CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
