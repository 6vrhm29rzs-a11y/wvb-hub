#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A TRUE phone viewport for the built page (2026-09-06).

The R6 media-lift has two measured failure modes: it reorders the cascade
(wins specificity ties it loses in situ) and it cannot see non-CSS state
(the pollview-inside-a-fold bug). Headless Chrome's --window-size clamps
to a 500px layout and silently crops the screenshot. This script does it
right: headless Chrome + CDP Emulation.setDeviceMetricsOverride -- a real
390x844 mobile layout with the page's own cascade.

Usage: python3 scripts/phone_probe.py [route ...]
Reports per route: horizontal overflow, elements wider than the viewport,
and clipped text; writes /tmp/phone_<route>.png screenshots.
"""
import asyncio, base64, io, json, os, re, subprocess, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
PAGE = "file://" + os.path.join(REPO, "Cody", "START-HERE.html")

PROBE = '''(()=>{
  const out={inner:innerWidth,
    overflow: document.documentElement.scrollWidth > innerWidth+1,
    pageH: document.body.scrollHeight, wide:[], clipped:[]};
  for (const e of document.querySelectorAll('body *')){
    const cs=getComputedStyle(e);
    if (cs.display==='none' || (!e.offsetParent && cs.position!=='fixed')) continue;
    const b=e.getBoundingClientRect();
    if (b.width>innerWidth+2 && out.wide.length<8){
      let p=e.parentElement, contained=false;
      while(p && p.tagName!=='BODY'){
        const pcs=getComputedStyle(p);
        if (/(auto|scroll)/.test(pcs.overflowX)) {contained=true;break;}
        p=p.parentElement;
      }
      if (!contained)
        out.wide.push([e.id||e.tagName+'.'+String(e.className||'').slice(0,30),
                       Math.round(b.width)]);
    }
    if (e.children.length===0 && (e.textContent||'').trim().length>2 &&
        cs.overflow!=='hidden' && cs.textOverflow!=='ellipsis' &&
        e.scrollWidth>e.clientWidth+3 && b.width>20 && out.clipped.length<8)
      out.clipped.push([e.tagName+'.'+String(e.className||'').slice(0,26),
                        (e.textContent||'').trim().slice(0,20)]);
  }
  return JSON.stringify(out);
})()'''


async def probe(routes):
    import websockets
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu",
         "--remote-debugging-port=%d" % PORT, "--window-size=800,900",
         "--user-data-dir=/tmp/phoneprobe-prof", PAGE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                tabs = json.load(urllib.request.urlopen(
                    "http://localhost:%d/json" % PORT))
                break
            except Exception:
                time.sleep(0.4)
        ws_url = [t for t in tabs if t.get("type") == "page"][0][
            "webSocketDebuggerUrl"]
        async with websockets.connect(ws_url, max_size=10 ** 8) as ws:
            mid = [0]
            async def call(m, p=None):
                mid[0] += 1
                await ws.send(json.dumps(
                    {"id": mid[0], "method": m, "params": p or {}}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == mid[0]:
                        return r.get("result", {})
            await call("Emulation.setDeviceMetricsOverride",
                       {"width": 390, "height": 844,
                        "deviceScaleFactor": 2, "mobile": True})
            bad = 0
            for route in routes:
                await call("Page.navigate", {"url": PAGE + "#" + route})
                await asyncio.sleep(1.6)
                r = await call("Runtime.evaluate",
                               {"expression": PROBE, "returnByValue": True})
                v = json.loads(r["result"]["value"])
                tag = route.strip("/#").replace("/", "_") or "root"
                shot = await call("Page.captureScreenshot", {"format": "png"})
                open("/tmp/phone_%s.png" % tag, "wb").write(
                    base64.b64decode(shot["data"]))
                flag = v["overflow"] or v["wide"] or v["clipped"]
                bad += 1 if flag else 0
                print("%-22s %s  h=%d%s%s" % (
                    route, "FLAG" if flag else "ok  ", v["pageH"],
                    ("  wide=" + str(v["wide"])) if v["wide"] else "",
                    ("  clipped=" + str(v["clipped"])) if v["clipped"] else ""))
            return bad
    finally:
        proc.terminate()


def discovered_routes():
    """Every route the BUILT PAGE declares, read from its own router.

    ⚠ A HAND-WRITTEN LIST DRIFTS. This one carried 15 routes while the page
    declared 18, so bracket, TV, players, player-ratings, the result ledger,
    availability, intel and film-room were never probed at all -- the same
    failure as the CI suite list that ran 32 of 46 guards, and as the media
    query sweep that missed 700px. The router is the source of truth; a
    scanner that finds none is a loud failure, not a clean run.
    """
    src = io.open(PAGE.replace("file://", ""), encoding="utf-8").read()
    m = re.search(r"const ROUTE_OF_VIEW = \{(.*?)\};", src, re.S)
    if not m:
        raise SystemExit("phone_probe: could not read ROUTE_OF_VIEW from the "
                         "built page -- refusing to probe a guessed list")
    routes = ["/" + r for r in re.findall(r":\s*'([a-z0-9-]+)'", m.group(1))]
    if len(routes) < 10:
        raise SystemExit("phone_probe: found only %d routes; the page "
                         "declares more than that" % len(routes))
    # ⚠ THE DEEP ROUTES, WITH REAL SLUGS. Team slugs are LOWERCASE, and
    # "/teams/Nebraska" silently falls back to the default team -- which IS
    # Nebraska, so it looked like it worked and tested nothing. Auburn is
    # used because it is not the default and currently carries a
    # participation flag, so the newest markup is on the probed page.
    return routes + ["/teams/auburn", "/players/auburn/lauren-dreves",
                     "/rankings/avca", "/rankings/gap"]


if __name__ == "__main__":
    # ⚠ NO HAND-WRITTEN FALLBACK. A fallback list is how the old one drifted
    # to 15 of 18 routes: discovery would fail quietly and the stale list
    # would read as a clean sweep. Discovery raises instead.
    routes = sys.argv[1:] or discovered_routes()
    sys.exit(1 if asyncio.run(probe(routes)) else 0)
