#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Screenshot ONE element of the built page, at a chosen width.

Why this exists: this project's own hardest-won debugging rule is "look at
the screen" -- a DOM measurement can be wrong about the pixels, the pixels
cannot. phone_probe.py answers "does anything overflow"; it captures the
VIEWPORT, so anything below the fold is invisible to review. Visual work
needs the opposite: point at a component and see it.

Usage:  python3 scripts/shot.py '<route>' '<css selector>' [width] [out.png]
        python3 scripts/shot.py '/teams/Nebraska' '.tdprof' 390
        python3 scripts/shot.py '/teams/Nebraska' '.cxd' 390 out.png '[data-tdt=numbers]' 

⚠ Uses CDP Emulation.setDeviceMetricsOverride, never --window-size, which
Chrome CLAMPS to a 500px layout and then crops the screenshot to the width
you asked for -- a phantom-bug generator (measured 2026-09-06).
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9334
PAGE = "file://" + os.path.join(REPO, "Cody", "START-HERE.html")


async def shoot(route, sel, width, out, click=None):
    import websockets
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu",
         "--remote-debugging-port=%d" % PORT, "--window-size=1200,900",
         "--user-data-dir=/tmp/shot-prof", PAGE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        tabs = None
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
                       {"width": width, "height": 900,
                        "deviceScaleFactor": 2, "mobile": width <= 560})
            await call("Page.navigate", {"url": PAGE + "#" + route})
            await asyncio.sleep(2.0)
            # a panel behind a tab has no box until the tab is open, and an
            # element with no box is not a missing element (the zero-width
            # bracket lesson): click first, then measure.
            if click and click.startswith("JS:"):
                await call("Runtime.evaluate", {"expression": click[3:],
                                                "returnByValue": True})
                await asyncio.sleep(0.8)
            elif click:
                await call("Runtime.evaluate", {"expression":
                    "(()=>{const c=document.querySelector(" + json.dumps(click) +
                    ");if(c)c.click();return !!c;})()", "returnByValue": True})
                await asyncio.sleep(1.0)
            expr = ("(()=>{const e=document.querySelector(" + json.dumps(sel) +
                    ");if(!e)return 'null';e.scrollIntoView();"
                    "const b=e.getBoundingClientRect();"
                    "return JSON.stringify({x:b.x+scrollX,y:b.y+scrollY,"
                    "w:b.width,h:b.height});})()")
            r = await call("Runtime.evaluate",
                           {"expression": expr, "returnByValue": True})
            v = r["result"]["value"]
            if v == "null":
                print("selector not found: %s  (route %s)" % (sel, route))
                return 1
            b = json.loads(v)
            if b["h"] < 1 or b["w"] < 1:
                print("element has no box: %s" % sel)
                return 1
            # ⚠ PAD THE CLIP. Clipping exactly to the element's box shaves
            # the last pixel column at deviceScaleFactor 2, so a value sitting
            # 2px inside its container photographs as "sam" instead of "same"
            # -- and I chased that as a layout bug twice before measuring
            # scrollWidth and finding nothing wrong with the page. An
            # instrument that crops is an instrument that invents defects.
            pad = 8
            shot = await call("Page.captureScreenshot", {
                "format": "png", "captureBeyondViewport": True,
                "clip": {"x": max(0, b["x"] - pad), "y": max(0, b["y"] - pad),
                         "width": b["w"] + pad * 2, "height": b["h"] + pad * 2,
                         "scale": 2}})
            open(out, "wb").write(base64.b64decode(shot["data"]))
            print("%s  %dx%d  -> %s" % (sel, round(b["w"]), round(b["h"]), out))
            return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    _route, _sel = sys.argv[1], sys.argv[2]
    _w = int(sys.argv[3]) if len(sys.argv) > 3 else 390
    _out = sys.argv[4] if len(sys.argv) > 4 else "/tmp/shot.png"
    _click = sys.argv[5] if len(sys.argv) > 5 else None
    sys.exit(asyncio.run(shoot(_route, _sel, _w, _out, _click)))
