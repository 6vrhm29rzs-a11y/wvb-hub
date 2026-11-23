#!/usr/bin/env python3
"""077: the Rankings basis toggle (Blend / 2026 only / Movers) must WORK on
both builds -- tapped in a real browser, each control shows its own panel with
content and Blend brings the board back. Function-name presence is not the
test. Negative control: the public page with the toggle code stripped (what the
misplaced RKCMP fence shipped) must FAIL the same check.

Runs headless Chrome with CDP mobile emulation in an isolated throwaway profile
(no real ballot/storage). Skips honestly where Chrome or a built page is absent
(CI). Screenshots: set WVB_SHOTS=<dir>."""
import asyncio, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGES = {"public": os.path.join(REPO, "output", "vb_dashboard.html"),
         "private": os.path.join(REPO, "Cody", "START-HERE.html")}
VIEWS = [("phone-360", 360, 780, 3, True), ("phone-430", 430, 932, 3, True),
         ("desktop-1440", 1440, 900, 2, False)]
PORT = 9336
ok = True


def check(c, msg):
    global ok
    print(("PASS " if c else "FAIL ") + msg)
    ok = ok and bool(c)


SEQ = r'''(async function(){
 const wait = ms => new Promise(f => setTimeout(f, ms));
 const out = [];
 const cmp = document.getElementById('rkcompare'); if (cmp) cmp.open = true;   /* the toggle lives in the Compare menu */
 const vis = el => !!el && !el.hidden && el.getBoundingClientRect().height > 0;
 for (const b of ['r26', 'movers', 'blend']) {
   const btn = document.querySelector('.basisseg [data-basis="' + b + '"]');
   if (!btn) { out.push({b, err: 'no button'}); continue; }
   btn.scrollIntoView({block: 'center'}); await wait(150);
   const r = btn.getBoundingClientRect();
   const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
   btn.click(); await wait(350);
   if (b === 'r26') {           /* 078: the 2026-only table itself */
     const t = document.querySelector('#r26panel table.r26t');
     const ths = t ? Array.from(t.querySelectorAll('thead th')) : [];
     const shown = ths.filter(h => getComputedStyle(h).display !== 'none' && h.getBoundingClientRect().width > 0)
                      .map(h => h.textContent.trim());
     const row = t ? t.querySelector('tbody tr') : null;
     const cells = row ? Array.from(row.children).filter(c => getComputedStyle(c).display !== 'none'
                      && c.getBoundingClientRect().width > 0).length : 0;
     const box = t ? t.closest('.scroll') : null;
     const fitsOrScrolls = box ? (box.scrollWidth <= box.clientWidth + 1 || getComputedStyle(box).overflowX === 'auto') : false;
     const note = (document.querySelector('#r26panel .tnote') || {}).textContent || '';
     window.__r26 = {shown, cells, fitsOrScrolls, pageOverflow: document.documentElement.scrollWidth > innerWidth + 1,
       key: !!document.querySelector('#r26panel .r26key'), stale: /median has|minority voice|unstable/.test(note),
       count: /\d+ matches/.test(note), utc: /latest match date \d{4}-\d\d-\d\d \(UTC\)/.test(note), rk3: !!document.querySelector('#r26panel table.rk3')};
   }
   const p26 = document.getElementById('r26panel'), pmv = document.getElementById('moverspanel'),
         pbd = document.getElementById('rankpanel');
   out.push({b, hit: !!(top && top.closest && top.closest('[data-basis="' + b + '"]')),
     on: btn.classList.contains('on'),
     r26: vis(p26) ? p26.querySelectorAll('tbody tr').length : -1,
     movers: vis(pmv) ? pmv.querySelectorAll('.mvcol').length : -1,
     board: vis(pbd) ? pbd.querySelectorAll('tbody tr').length : -1,
     tgt: Math.round(r.width) + 'x' + Math.round(r.height)});
 }
 out.push({b: 'r26table', t: window.__r26 || null});
 return JSON.stringify(out);
})()'''


def judge_table(res):
    t = dict((x["b"], x) for x in res).get("r26table", {}).get("t") or {}
    return (t.get("shown") == ["#", "Team", "W-L", "M", "Adj", "SOS"] and t.get("cells") == 6
            and t.get("fitsOrScrolls") and not t.get("pageOverflow") and t.get("key")
            and not t.get("stale") and t.get("count") and t.get("utc") and not t.get("rk3")), t


def judge(res):
    """True when every control did its job."""
    by = dict((x["b"], x) for x in res)
    try:
        return (by["r26"]["on"] and by["r26"]["r26"] > 0 and by["r26"]["board"] == -1
                and by["movers"]["on"] and by["movers"]["movers"] > 0 and by["movers"]["r26"] == -1
                and by["blend"]["on"] and by["blend"]["board"] > 0
                and by["blend"]["r26"] == -1 and by["blend"]["movers"] == -1
                and all(x.get("hit", True) for x in res))
    except KeyError:
        return False


async def drive(targets, shots):
    import websockets
    prof = tempfile.mkdtemp(prefix="basisprobe-")
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu",
                             "--remote-debugging-port=%d" % PORT, "--user-data-dir=" + prof,
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = {}
    try:
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen("http://localhost:%d/json" % PORT)); break
            except Exception:
                time.sleep(0.4)
        ws_url = [t for t in tabs if t.get("type") == "page"][0]["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url, max_size=10 ** 8) as ws:
            mid = [0]; errs = []

            async def call(m, p=None):
                mid[0] += 1
                await ws.send(json.dumps({"id": mid[0], "method": m, "params": p or {}}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("method") == "Runtime.exceptionThrown":
                        errs.append(r["params"]["exceptionDetails"].get("text"))
                    if r.get("id") == mid[0]:
                        return r.get("result", {})
            await call("Runtime.enable")
            for name, path in targets:
                for vname, w, h, dpr, mobile in VIEWS:
                    errs.clear()
                    await call("Emulation.setDeviceMetricsOverride",
                               {"width": w, "height": h, "deviceScaleFactor": dpr, "mobile": mobile})
                    await call("Emulation.setTouchEmulationEnabled", {"enabled": mobile})
                    await call("Page.navigate", {"url": "file://" + path + "#/rankings"})
                    await asyncio.sleep(4.5)
                    r = await call("Runtime.evaluate", {"expression": SEQ, "awaitPromise": True,
                                                        "returnByValue": True})
                    try:
                        res = json.loads(r["result"]["value"])
                    except Exception:
                        res = []
                    results[(name, vname)] = (res, list(errs))
                    if shots and not name.startswith("NEG"):
                        await call("Runtime.evaluate", {"expression":
                            "document.querySelector('.basisseg [data-basis=\"r26\"]').click();"
                            "document.querySelector('.basisseg').scrollIntoView({block:'start'})"})
                        await asyncio.sleep(0.5)
                        import base64
                        s = await call("Page.captureScreenshot", {"format": "png"})
                        open(os.path.join(shots, "basis-%s-%s.png" % (name, vname)), "wb").write(
                            base64.b64decode(s["data"]))
    finally:
        proc.terminate()
        shutil.rmtree(prof, ignore_errors=True)
    return results


def main():
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("SKIP: websockets not available"); return 0
    if not os.path.exists(CHROME):
        print("SKIP: Chrome not available here (CI) -- behaviour unverified in this environment"); return 0
    targets = [(n, p) for n, p in PAGES.items() if os.path.exists(p)]
    if not targets:
        print("SKIP: no built page"); return 0
    # negative control: the public page as the misplaced fence shipped it
    neg = None
    if os.path.exists(PAGES["public"]):
        html = open(PAGES["public"], encoding="utf-8").read()
        m = re.search(r"function renderR26\(\).*?document\.addEventListener\('click', e => \{\n"
                      r"  const b = e\.target\.closest && e\.target\.closest\('\.basisseg \[data-basis\]'\);\n"
                      r"  if \(b\) setBasis\(b\.dataset\.basis\);\n\}\);\n", html, re.S)
        check(m, "public page carries the basis toggle code (the 077 fix)")
        if m:
            neg = os.path.join(tempfile.mkdtemp(prefix="basisneg-"), "neg.html")
            open(neg, "w", encoding="utf-8").write(html[:m.start()] + html[m.end():])
            targets.append(("NEG-public-stripped", neg))
    shots = os.environ.get("WVB_SHOTS")
    if shots:
        os.makedirs(shots, exist_ok=True)
    res = asyncio.run(drive(targets, shots))
    for (name, view), (r, errs) in sorted(res.items()):
        if name.startswith("NEG"):
            continue
        check(judge(r), "%s %s: 2026 only / Movers / Blend each show their own panel%s"
              % (name, view, "" if judge(r) else " " + json.dumps(r)))
        okt, t = judge_table(r)
        check(okt, "%s %s: 2026-only table shows #/Team/W-L/M/Adj/SOS, key, factual copy %s"
              % (name, view, "" if okt else json.dumps(t)))
        check(not errs, "%s %s: no exceptions %s" % (name, view, errs[:2]))
    negs = [v for (n, _), v in res.items() if n.startswith("NEG")]
    if neg:
        check(negs and not any(judge(r) for r, _ in negs),
              "negative control: public page with the toggle code stripped FAILS the same check")
    print("ALL BASIS TOGGLE CHECKS HOLD" if ok else "BASIS TOGGLE CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
