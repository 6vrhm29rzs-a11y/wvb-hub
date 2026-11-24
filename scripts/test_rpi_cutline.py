#!/usr/bin/env python3
"""098 guards for the private RPI Cut Line: counts, no duplicate bids, AQ-below-line behaviour, at-large
eligibility and strict RPI order, unresolved-slot handling, and the rendered served view (local only)."""
import asyncio, copy, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")   # mail 105: an isolated copy serves on its own port
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


import build_hub as B
import build_rankings_board as BOARD
import project_field as PF
if not os.path.exists(os.path.join(REPO, "data", "raw", "2026", "polls_rpi.jsonl")):
    print("SKIP: no stored RPI capture"); sys.exit(0)
os.environ["WVB_POWER_DEFAULT"] = "candidate"
teams, field, _, _, _ = BOARD.build()
c = B.rpi_cutline(teams, field)
F = c["field"]
check(len(F) == 64 and len(set(r["team"] for r in F)) == 64, "64 bids, no team twice (%d)" % len(F))
check(c["n_aq"] + c["n_al"] + len(c["unresolved_aq"]) == 64, "AQ + at-large + held slots = 64 (%d + %d + %d)" % (c["n_aq"], c["n_al"], len(c["unresolved_aq"])))
confs = [r["conf"] for r in F if r["bid"] == "AQ"]
check(len(confs) == len(set(confs)) and c["ncaa_conferences"] == 32, "one AQ per conference; 32 conferences in the official table")
al = [r for r in F if r["bid"] == "At-large"]
ranks = [r["rank"] for r in al]
check(ranks == sorted(ranks) and ranks[-1] == c["cut_rank"], "at-large slots are strict RPI order; cut = last at-large (#%s)" % c["cut_rank"])
inel = set(PF.INELIGIBLE_2026)
from reconcile_2025 import norm
check(not [r for r in F if norm(r["team"]) in inel], "no championship-ineligible team in the field")
out_ranks = [r["rank"] for r in c["first_out"]]
aqset = set(r["team"] for r in F if r["bid"] == "AQ")
check(all(rk > c["cut_rank"] for rk in out_ranks) and not [r for r in c["first_out"] if r["team"] in aqset],
      "first-out teams sit below the line and hold no AQ")
check(all(next(r for r in F if r["team"] == t)["rank"] > c["cut_rank"] for t in c["aq_below_line"]) and c["aq_below_line"],
      "AQs ranked below the line still make the field (%d of them)" % len(c["aq_below_line"]))
# the AQ is the projected regular-season leader of its conference (Cody 2026-11-05)
proj, _ = B.project_conf_champions([dict(team=r["team"], ckey=B._ckey(r["conf"])) for r in F] +
                                   [])
import json as _j
rpi_rows = _j.loads(open(os.path.join(REPO, "data", "raw", "2026", "polls_rpi.jsonl")).read().splitlines()[-1])["rows"]
allr = [{"team": (lambda t: t["team"] if t else r["School"])(dict((norm(x["team"]), x) for x in teams).get(norm(r["School"]))),
         "ckey": B._ckey(r["Conf"])} for r in rpi_rows]
proj, pm = B.project_conf_champions(allr)
import aq_status as _AQS
_aq = _AQS.load()
_favs = B._ct_favourites(teams)
bad = []
for r in [x for x in F if x["bid"] == "AQ"]:
    ck = B._ckey(r["conf"])
    # a decided tournament settles the bid outright; otherwise the leader among teams still alive holds it
    champ = [x["team"] for x in allr if x["ckey"] == ck and _aq["champions"].get(norm(x["team"]))]
    if champ:
        if r["team"] != champ[0]:
            bad.append(r["team"])
        continue
    # an open tournament: the team most likely to win what is left of the real bracket holds it
    if _favs.get(ck):
        if r["team"] != _favs[ck]:
            bad.append(r["team"])
        continue
    best = max((proj[x["team"]]["ppct"] or 0) for x in allr
               if x["ckey"] == ck and norm(x["team"]) not in inel and norm(x["team"]) not in _aq["eliminated"])
    if norm(r["team"]) in _aq["eliminated"] or abs((proj[r["team"]]["ppct"] or 0) - best) > 1e-12:
        bad.append(r["team"])
check(not bad and pm["upcoming_conf_matches"] > 0, "every AQ is its league's real champion, or else its likeliest tournament champion, or else its best projected record among teams still alive (%d upcoming conference matches used)%s" % (pm["upcoming_conf_matches"], " -- " + ", ".join(bad) if bad else ""))
# missing-data: a conference with no projection -> its slot is held open, not converted to an extra at-large
real_p = B.project_conf_champions
def no_bigten(rpi):
    o, m = real_p(rpi)
    for r in rpi:
        if r["ckey"] == "bigten":
            o[r["team"]] = dict(o[r["team"]], ppct=None)
    return o, m
real_f = B._ct_favourites
B.project_conf_champions = no_bigten
B._ct_favourites = lambda _t: {}          # the missing-projection path, with no tournament favourite to fall back on
try:
    c2 = B.rpi_cutline(teams, field)
finally:
    B.project_conf_champions = real_p
    B._ct_favourites = real_f
check(len(c2["unresolved_aq"]) == 1 and c2["n_al"] == c["n_al"] and len(c2["field"]) == 63,
      "a missing AQ is reported as an unresolved slot and NOT filled by an extra at-large (%s)" % c2["unresolved_aq"])

# projected end-of-regular-season RPI (Cody 2026-11-05): same formula, remaining matches to the forecast favourite
fut, fm = B.rpi_futures()
added = sum((v["proj_w"] + v["proj_l"]) - (v["now_w"] + v["now_l"]) for v in fut.values())
check(fm["projected_games"] > 0 and added == 2 * fm["projected_games"],
      "every projected match adds exactly one win and one loss (%d matches through %s)" % (fm["projected_games"], fm["last_scheduled_date"]))
check(sorted(v["proj_rank"] for v in fut.values()) == list(range(1, len(fut) + 1)), "projected RPI ranks are a complete 1..N order")
cp = B.rpi_cutline(teams, field, ranking="projected")
Fp = cp["field"]; alp = [r["rank"] for r in Fp if r["bid"] == "At-large"]
check(len(Fp) == 64 and len(set(r["team"] for r in Fp)) == 64 and alp == sorted(alp) and alp[-1] == cp["cut_rank"],
      "projected cut line: 64 unique bids, at-large in strict projected-RPI order, cut #%s (last in %s)" % (cp["cut_rank"], cp["last_in"]["team"]))
l4 = c["last_four_in"]; o4 = c["first_out"][:4]
check([x["rank"] for x in l4] == sorted(x["rank"] for x in l4) and l4[-1]["rank"] == c["cut_rank"] and
      [x["rank"] for x in o4] == sorted(x["rank"] for x in o4) and o4[0]["rank"] > c["cut_rank"],
      "last four in end at the cut; first four out start just below it, both in RPI order (%s | %s)" % ([x["team"] for x in l4], [x["team"] for x in o4]))
check(set(r["team"] for r in Fp if r["bid"] == "AQ") == set(r["team"] for r in F if r["bid"] == "AQ"),
      "both views use the same projected regular-season champions as AQs")

# at-large gates (mail 099): synthetic records, real selection code
real_rec = B.cut_records
def gated(projected=False, extra=None):
    r = real_rec(projected, extra=extra)
    r = dict((k, dict(v)) for k, v in r.items())
    tgt_a, tgt_b = norm(c["last_four_in"][0]["team"]), norm(c["last_four_in"][1]["team"])
    r[tgt_a].update(w=10, l=12)                       # below .500
    r[tgt_b].update(di=int(r[tgt_b]["n"] * 0.7))      # under 80% D-I
    aq0 = norm(next(x["team"] for x in F if x["bid"] == "AQ"))
    r[aq0].update(w=8, l=14)                          # an AQ below .500
    return r
B.cut_records = gated
try:
    cg = B.rpi_cutline(teams, field)
finally:
    B.cut_records = real_rec
outs = dict((g["team"], g["why"]) for g in cg["at_large_gate_out"])
ta, tb = c["last_four_in"][0]["team"], c["last_four_in"][1]["team"]
check(ta in outs and "below .500" in outs[ta] and tb in outs and "80%" in outs[tb]
      and ta not in [x["team"] for x in cg["field"]] and tb not in [x["team"] for x in cg["field"]],
      "a high non-AQ below .500 and one under 80%% D-I are kept out of the at-large pool (%s)" % outs)
aq0 = next(x["team"] for x in F if x["bid"] == "AQ")
check(aq0 in [x["team"] for x in cg["field"] if x["bid"] == "AQ"] and aq0 in cg["aq_under_500"],
      "an otherwise eligible AQ below .500 keeps its automatic bid (%s)" % aq0)
check(len(cg["field"]) == 64 and cg["cut_rank"] > c["cut_rank"], "two gated teams push the cut down (%s -> %s)" % (c["cut_rank"], cg["cut_rank"]))
check(sorted(x["team"] for x in F if x["bid"] == "AQ") == sorted(x["team"] for x in cp["field"] if x["bid"] == "AQ"),
      "AQs are selected once on a shared basis (identical in both views)")
check(not c["not_awarding"] and "UAC" in c["wac_note"], "the manual's WAC slot is the UAC's single slot (nothing left 'not awarding')")

# rendered served view (local only)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
try:
    urllib.request.urlopen(BASE + "/START-HERE.html", timeout=5)
    served = True
except Exception:
    served = False
JS = r'''(async function(){ const w = ms => new Promise(f => setTimeout(f, ms));
 for (let i = 0; i < 40 && !document.getElementById('cutline'); i++) await w(250);
 const cl = document.getElementById('cutline'); const o = {exists: !!cl, visible: cl && !cl.hidden,
   rows: cl ? cl.querySelectorAll('#cl-now .cl-t tr.cl-aq, #cl-now .cl-t tr.cl-al').length : 0, line: cl ? cl.querySelectorAll('#cl-now .cl-t tr.cl-line').length : 0, l4: cl ? cl.querySelectorAll('#cl-now .cl-ol')[0].children.length : 0, o4: cl ? cl.querySelectorAll('#cl-now .cl-ol')[1].children.length : 0, layoutW: innerWidth, docW: document.documentElement.scrollWidth,
   sum: cl ? cl.querySelector('#cl-now .cl-sum').innerText.replace(/\s+/g, ' ').slice(0, 160) : '',
   bracketHidden: (document.getElementById('brkview') || {}).hidden};
 const b = document.querySelector('#v-bracket [data-bv="bracket"]'); if (b) { b.click(); await w(200); }
 o.backToBracket = cl && cl.hidden && !(document.getElementById('brkview') || {}).hidden; o.hashAfter = location.hash;
 return JSON.stringify(o); })()'''
async def drive():
    import websockets
    prof = tempfile.mkdtemp(prefix="clprobe-"); res = {}
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9341", "--user-data-dir=" + prof, "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try: tabs = json.load(urllib.request.urlopen("http://localhost:9341/json")); break
            except Exception: time.sleep(.3)
        async with websockets.connect([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], max_size=10 ** 9) as ws:
            mid = [0]; errs = []
            async def call(m, par=None):
                mid[0] += 1; await ws.send(json.dumps({"id": mid[0], "method": m, "params": par or {}}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("method") == "Runtime.exceptionThrown": errs.append(r["params"]["exceptionDetails"].get("text"))
                    if r.get("id") == mid[0]: return r.get("result", {})
            await call("Runtime.enable")
            for name, w_, mob in (("phone-360", 360, True), ("phone-430", 430, True), ("desktop-1440", 1440, False)):
                errs.clear()
                await call("Emulation.setDeviceMetricsOverride", {"width": w_, "height": 900, "deviceScaleFactor": 2, "mobile": mob})
                await call("Page.navigate", {"url": BASE + "/START-HERE.html#/bracket/cutline"}); await asyncio.sleep(7)
                import base64
                s = await call("Page.captureScreenshot", {"format": "png"})
                open(os.path.join(REPO, "Cody", "coordination", "research", "POWER-PREVIEW-2026-11-05", "cutline-%s.png" % name), "wb").write(base64.b64decode(s["data"]))
                r = await call("Runtime.evaluate", {"expression": JS, "awaitPromise": True, "returnByValue": True})
                await call("Page.navigate", {"url": BASE + "/START-HERE.html#/bracket/cutline/projected"}); await asyncio.sleep(6)
                r2 = await call("Runtime.evaluate", {"expression": "JSON.stringify({proj: !document.getElementById('cl-proj').hidden, now: !document.getElementById('cl-now').hidden, rows: document.querySelectorAll('#cl-proj .cl-t tr.cl-aq, #cl-proj .cl-t tr.cl-al').length, line: document.querySelectorAll('#cl-proj .cl-t tr.cl-line').length, w: innerWidth, d: document.documentElement.scrollWidth})", "returnByValue": True})
                s2 = await call("Page.captureScreenshot", {"format": "png"})
                open(os.path.join(REPO, "Cody", "coordination", "research", "POWER-PREVIEW-2026-11-05", "cutline-proj-%s.png" % name), "wb").write(base64.b64decode(s2["data"]))
                o = json.loads(r["result"]["value"]); o["projview"] = json.loads(r2["result"]["value"])
                await call("Page.navigate", {"url": BASE + "/START-HERE.html#/bracket"}); await asyncio.sleep(6)
                r3 = await call("Runtime.evaluate", {"expression": "JSON.stringify({seeds: [...document.querySelectorAll('#brkseeds tbody tr')].map(tr => [tr.cells[1].textContent.trim(), tr.cells[3].textContent.trim()]), boxes: document.querySelectorAll('#brkview .bteam, #brkview [data-team]').length, w: innerWidth, d: document.documentElement.scrollWidth, lead: (document.querySelector('#v-bracket > p.lead')||{}).textContent || ''})", "returnByValue": True})
                o["bracket"] = json.loads(r3["result"]["value"])
                s3 = await call("Page.captureScreenshot", {"format": "png"})
                open(os.path.join(REPO, "Cody", "coordination", "research", "POWER-PREVIEW-2026-11-05", "bracket-%s.png" % name), "wb").write(base64.b64decode(s3["data"]))
                res[name] = (o, list(errs))
    finally:
        p.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return res
if served and os.path.exists(CHROME):
    for name, (o, errs) in asyncio.run(drive()).items():
        dw = int(name.split("-")[1])
        check(o["exists"] and o["visible"] and o["rows"] == 64 and o["bracketHidden"], "%s: #/bracket/cutline opens the cut line (64 rows)" % name)
        check(o["line"] == 1 and o["l4"] == 4 and o["o4"] == 4, "%s: one visual cut-line row; last four in and first four out listed (%s/%s/%s)" % (name, o["line"], o["l4"], o["o4"]))
        check("RPI #%s" % c["cut_rank"] in o["sum"], "%s: summary shows the cut line and last in / first out (%s)" % (name, o["sum"][:90]))
        check(o["backToBracket"] and o["hashAfter"] == "#/bracket", "%s: switching back shows the projected bracket" % name)
        check(o["layoutW"] == dw and o["docW"] <= dw, "%s: layout fits the device width (%s/%s)" % (name, o["layoutW"], o["docW"]))
        pv = o["projview"]
        check(pv["proj"] and not pv["now"] and pv["rows"] == 64 and pv["line"] == 1 and pv["w"] == dw and pv["d"] <= dw,
              "%s: #/bracket/cutline/projected shows the projected view (64 rows) and fits (%s)" % (name, pv))
        br = o["bracket"]
        # mail 104: the private bracket is the COMMITTEE-INFORMED post-tournament field (test_committee_field.py
        # checks it in depth); here, its 64 teams and bid labels must equal that field exactly
        global _CMF
        try:
            _CMF
        except NameError:
            import committee_field as _CF
            _ct, _scen, _ = B.conf_tournaments(teams)
            _CMF = _CF.build(B.rpi_cutline(teams, field, ranking="post", scenario=_scen))["ordered"]
        want = sorted([(x["team"], "AQ" if x["bid"] == "AQ" else "at-large") for x in _CMF])
        check(sorted(tuple(x) for x in br["seeds"]) == want, "%s: the bracket's 64 teams and bid labels equal the committee-informed field" % name)
        check("Projected RPI" in br["lead"] and br["w"] == dw and br["d"] <= dw, "%s: bracket labels its field basis and fits the width" % name)
        check(not errs, "%s: no script errors %s" % (name, errs[:2]))
else:
    print("SKIP rendered checks: local server or Chrome unavailable")
print("ALL RPI CUT LINE CHECKS HOLD" if ok else "RPI CUT LINE CHECKS FAILED"); sys.exit(0 if ok else 1)
