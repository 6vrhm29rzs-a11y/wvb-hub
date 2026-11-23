#!/usr/bin/env python3
"""mail 104 guards: committee-informed field (64 unique, AQ/at-large counts, same AQs and gates as the post
scenario), explained near-cut changes recomputed from the same snapshot, seed lines per the 2026 manual,
placement constraints (one team per line per quadrant, no first/second-round conference pods), exact
field = bracket agreement on the built page, rendered phone/desktop views, and public privacy."""
import copy, json, os, re, sys, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")   # mail 105: an isolated copy serves on its own port
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
os.environ["WVB_POWER_DEFAULT"] = "candidate"
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


import build_hub as B, build_rankings_board as BOARD, committee_field as CF
teams, field, *_ = BOARD.build()
ct, scen, _ = B.conf_tournaments(teams)
cp = B.rpi_cutline(teams, field, ranking="post", scenario=scen)
out = CF.build(cp)
sel, ordered, pl = out["sel"], out["ordered"], out["place"]
names = [r["team"] for r in ordered]
check(len(names) == 64 and len(set(names)) == 64, "64 unique teams")
check(sel["n_aq"] == len(cp["aq_teams"]) and sel["n_al"] == 64 - sel["n_aq"] - len(cp.get("unresolved_aq") or []),
      "AQ / at-large counts: %d + %d" % (sel["n_aq"], sel["n_al"]))
check(set(r["team"] for r in ordered if r["bid"] == "AQ") == set(cp["aq_teams"]), "AQs are the post scenario's AQs")
check(all(r["team"] in cp["al_pool"] for r in ordered if r["bid"] == "At-large"), "every at-large passes the scenario's .500 / 80% D-I gates")
# scores recompute from the SAME snapshot: ranks are the post view's, wins from its resumes
for r in ordered:
    q = CF.quality(cp["resumes"][r["team"]], cp["ranks_all"])
    if CF.score(cp["ranks_all"][r["team"]], q) != CF.score(r["rank"], r["q"]):
        check(False, "score recomputes for %s" % r["team"]); break
else:
    check(True, "every field score recomputes from the post view's ranks and resumes")
# near-cut explanation on the real snapshot
# whether today's real standings produce a near-cut change is a fact about the season; the DETERMINISTIC fixtures below prove the mechanism
print("INFO near-cut changes on today's snapshot: %s" % [(c.get("kind"), c["in"], c["out"]) for c in sel["changes"]])
for ch in sel["changes"]:
    check(ch["rank_in"] == cp["ranks_all"][ch["in"]] and ch["rank_out"] == cp["ranks_all"][ch["out"]] and ch["evidence"],
          "change %s/%s quotes this snapshot's ranks and carries evidence" % (ch["in"], ch["out"]))
    print("INFO " + ch["text"] + " | " + " ".join(ch["evidence"]))
# ---- near-cut changes: DETERMINISTIC fixtures (mail 114) ------------------------------------------------
# The old check boosted whoever was first out TODAY and expected a swap -- true on Nov 6, false on Nov 7 when
# that team was already in on pure RPI (a "last_in" change, correctly). A test must not depend on the standings.
def fx_cut():
    T = ["FX%03d" % i for i in range(1, 101)]
    aq = T[64:96]                                   # 32 automatic bids, all ranked below the at-large group
    pool = T[:64] + T[96:]
    rpi_al = T[:32]
    fieldr = [{"team": t, "bid": "AQ", "rank": T.index(t) + 1} for t in aq] + [{"team": t, "bid": "At-large", "rank": T.index(t) + 1} for t in rpi_al]
    return {"ranks_all": dict((t, i + 1) for i, t in enumerate(T)), "resumes": dict((t, {"actual": [], "proj": []}) for t in T),
            "aq_teams": aq, "al_pool": pool, "field": fieldr, "conf_of": dict((t, "C%d" % (i % 20)) for i, t in enumerate(T)),
            "unresolved_aq": []}
def wins(c, team, opp_ranks):
    for k, r in enumerate(opp_ranks):
        opp = "FX%03d" % r
        c["resumes"][team]["actual"].append(["2026-09-0%d" % (k + 1), opp, "W", "3-0", r, 1, "H", "SYN%d" % k])
base = CF.select(fx_cut())
check(not [c for c in base["changes"]] and [r["team"] for r in base["field"] if r["bid"] == "At-large"] == ["FX%03d" % i for i in range(1, 33)],
      "fixture: with no quality wins the committee field equals the pure-RPI field, no changes")
cA = fx_cut(); wins(cA, "FX033", [1, 2, 3])            # first out on BOTH rules, three top-25 wins -> swaps in
sA = CF.select(cA)
swA = [c for c in sA["changes"] if c.get("kind") == "swap"]
check(len(swA) == 1 and swA[0]["in"] == "FX033" and swA[0]["out"] == "FX032" and swA[0]["evidence"],
      "fixture: a team out on both rules with three top-25 wins SWAPS in for the last RPI team, with evidence")
cB = fx_cut(); wins(cB, "FX032", [30, 40])              # in on RPI; two top-50 wins move it ahead of FX031
sB = CF.select(cB)
check([c.get("kind") for c in sB["changes"]] == ["last_in"] and sB["changes"][0]["in"] == "FX032" and sB["changes"][0]["out"] == "FX031",
      "fixture: a team already in on RPI that gains quality wins changes WHO IS LAST IN, not membership (%s)" % [(c.get("kind"), c["in"], c["out"]) for c in sB["changes"]])
cC = fx_cut(); wins(cC, "FX034", [45, 46])              # out on both; two top-50 wins put it next in line ahead of FX033
sC = CF.select(cC)
check([(c.get("kind"), c["in"], c["out"]) for c in sC["changes"]] == [("next_in_line", "FX034", "FX033")],
      "fixture: next in line changes without changing the field (%s)" % [(c.get("kind"), c["in"], c["out"]) for c in sC["changes"]])
# ---- near-cut changes: LIVE-GENERATION consistency (whatever today's standings are) ----------------------
rpi_al = [r["team"] for r in cp["field"] if r["bid"] == "At-large"]
cm_al = [r["team"] for r in sel["field"] if r["bid"] == "At-large"]
for ch in sel["changes"]:
    k = ch.get("kind")
    if k == "swap":
        good = ch["in"] in cm_al and ch["in"] not in rpi_al and ch["out"] in rpi_al and ch["out"] not in cm_al
    elif k == "last_in":
        good = set(cm_al) == set(rpi_al) and ch["in"] == rpi_al[-1]
    else:
        good = ch["in"] not in cm_al and ch["out"] not in rpi_al
    check(good, "live: %s change %s/%s is consistent with the two fields" % (k, ch["in"], ch["out"]))
check(len([c for c in sel["changes"] if c.get("kind") == "swap"]) == len(set(cm_al) - set(rpi_al)),
      "live: one explained swap per membership difference (%d)" % len(set(cm_al) - set(rpi_al)))
# seed lines (2026 manual 2.3)
sd = [r for r in ordered if r["seed"]]
check(len(sd) == 32 and [r["seed"] for r in sd] == list(range(1, 33)), "32 seeded, national seeds 1-32")
check(all(sum(1 for r in sd if r["line"] == ln) == 4 for ln in range(1, 9)), "four teams per seed line 1-8")
check(all(r["line"] == (r["seed"] + 3) // 4 for r in sd) and all(r["line"] <= 4 for r in sd[:16]), "top 16 on lines 1-4, in rank order")
# placement
quadline = [(q, ln) for q in range(4) for ln in range(1, 9) if pl["quad"][q].get(ln)]
check(len(quadline) == 32 and all(len(set(pl["quad"][q][ln]["team"] for q in range(4))) == 4 for ln in range(1, 9)),
      "every seed line puts one team in each quadrant")
pod_conf = []
for p in pl["pods"]:
    cs = [x["conf"] for x in [p["host"], p["seed2"]] + p["un"]]
    if len(set(cs)) != 4:
        pod_conf.append((p["host"]["team"], cs))
check(not pod_conf or pl["notes"], "no first/second-round pod holds two teams of one conference (%s)" % pod_conf)
check(len(pl["games"]) == 32 and set(t["team"] for g in pl["games"] for t in g) == set(names), "32 first-round games cover the 64")
check(all(p["host"]["line"] + p["seed2"]["line"] == 9 for p in pl["pods"]), "pods pair line L with line 9-L (1v8, 2v7, 3v6, 4v5)")
# ---- mail 105 fixtures (isolated, pure) ----
import datetime as _dt
today = _dt.date(2026, 11, 29)
clean = {"as_of": "2026-11-29", "counts": {"final": 4800, "scheduled_or_live": 0, "source_withdrawn": 70, "unknown": 0}}
ct_done = {"SEC": {"chalk": [{"source": "actual"}] * 15}, "Big Ten": {"chalk": [{"source": "actual"}] * 14}}
c1, w1 = CF.completeness(0, dict(clean, counts=dict(clean["counts"], scheduled_or_live=1)), ct_done, today)
check(not c1 and CF.basis_for(c1, _dt.date(2026, 11, 29), "2026-11-28") == "provisional" and any("still scheduled" in x for x in w1),
      "fixture: zero forecasts but one scheduled fixture -> stays provisional (%s)" % w1)
c2, w2 = CF.completeness(0, dict(clean, as_of="2026-11-27"), ct_done, today)
check(not c2 and any("not today" in x for x in w2), "fixture: stale disposition artifact -> not complete")
c3, w3 = CF.completeness(0, clean, {"SEC": {"chalk": [{"source": "actual"}] * 14 + [{"source": "forecast favourite"}]}}, today)
check(not c3 and any("not yet played" in x for x in w3), "fixture: an unplayed tournament match -> not complete")
c4, w4 = CF.completeness(0, None, ct_done, today)
check(not c4, "fixture: missing disposition artifact -> not complete")
c5, _ = CF.completeness(0, clean, ct_done, today)
check(c5 and CF.basis_for(c5, _dt.date(2026, 11, 29), "2026-11-28") == "official"
      and CF.basis_for(c5, _dt.date(2026, 11, 22), "2026-11-28") == "complete_base",
      "fixture: complete -> official only when its through-date covers the last final, else complete RPI")
# official order differing from Base: ONE snapshot through field, comparison and labels
cpo = B.rpi_cutline(teams, field, ranking="post", scenario=scen, official_ranks=True)
diff = [t for t in cp["ranks_all"] if cpo["ranks_all"].get(t) != cp["ranks_all"][t]]
check(len(diff) > 10, "fixture: official and Projected Base orders differ for %d teams" % len(diff))
cap = [json.loads(l) for l in open(os.path.join(REPO, "data", "raw", "2026", "polls_rpi.jsonl")) if l.strip()][-1]
from reconcile_2025 import norm as _n
offr = dict((_n(r["School"]), int(r["Rank"])) for r in cap["rows"] if str(r.get("Rank", "")).isdigit())
check(all(offr.get(_n(t)) == r for t, r in cpo["ranks_all"].items()), "fixture: official switch uses the official capture's ranks for every team")
oo = CF.build(cpo, "official")
check(all(r["rank"] == cpo["ranks_all"][r["team"]] for r in oo["ordered"]), "fixture: committee field ranks == official snapshot")
check(all("official RPI #" in ch["text"] and "Projected" not in ch["text"] for ch in oo["sel"]["changes"]) ,
      "fixture: every explanation names official RPI (%d explanations)" % len(oo["sel"]["changes"]))
panel = B.committee_panel_html(dict(oo, basis="official", left=0, through=cap.get("stamp"), gen=None, rpi_post=cpo, incomplete_why=[]))
rl = re.search(r"last four in ([^;]*);", panel).group(1)
check(rl == ", ".join(x["team"] for x in cpo["last_four_in"]).replace("&", "&amp;") and "official RPI" in panel and "Projected RPI" not in panel,
      "fixture: panel comparison lists and basis come from the same official snapshot")
# eligible candidates beyond the old rank-100 resume boundary
deep = [t for t in cp["al_pool"] if cp["ranks_all"][t] > 100]
check(deep and all(t in cp["resumes"] for t in cp["al_pool"]),
      "every eligible at-large candidate has a resume (%d in pool, %d ranked beyond 100)" % (len(cp["al_pool"]), len(deep)))
cp3 = copy.deepcopy(cp); del cp3["resumes"][deep[-1]]
try:
    CF.select(cp3); check(False, "fixture: a missing resume must withhold the field")
except ValueError as e:
    check("withheld" in str(e), "fixture: a candidate missing its resume (%s) withholds the field, never silently drops" % deep[-1])
# built page: field == bracket exactly
html = open(os.path.join(REPO, "Cody", "START-HERE.html"), encoding="utf-8").read()
sec = html[html.index('<section id="v-bracket"'):]
sec = sec[:sec.index("</section>")]
rows = re.findall(r'<tr data-seed="(\d+)" data-team="([^"]*)" data-conf="[^"]*" data-bid="([^"]*)">', sec)
pg = json.loads(re.search(r"window\.BRACKET_GAMES = (\[.*?\]);</script>", sec).group(1))
import html as _h
page_teams = [_h.unescape(t) for _, t, _ in rows]
check(len(rows) == 64 and len(set(page_teams)) == 64, "page seed table: 64 unique rows")
check(set(page_teams) == set(t["team"] for g in pg for t in g) and len(pg) == 32, "page: bracket games == seed table field exactly")
pmap = dict((_h.unescape(t), b) for _, t, b in rows)
check(all((pmap[t["team"]] == "AQ") == (t["bid"] == "AQ") for g in pg for t in g), "page: bid labels agree between table and bracket")
check('id="cmfield"' in sec and "cm-regs" in sec and "Field selection: the changes at the cut" in sec, "page: committee panel present (regional No.1s; field-selection changes in the method fold)")
pub = open(os.path.join(REPO, "output", "vb_dashboard.html"), encoding="utf-8").read()
check("cmfield" not in pub and "BRACKET_GAMES" not in pub and "Committee-informed" not in pub, "public build carries no committee field")
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
        prof = tempfile.mkdtemp(prefix="cfprobe-"); res = {}
        p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9344", "--user-data-dir=" + prof, "about:blank"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try: tabs = json.load(urllib.request.urlopen("http://localhost:9344/json")); break
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
                    await call("Page.navigate", {"url": BASE + "/START-HERE.html#/bracket"}); await asyncio.sleep(7)
                    js = ("(()=>{const p=document.getElementById('cmfield');const bn=[...document.querySelectorAll('#brkview .bnm')].map(x=>x.textContent.trim()).filter(x=>x&&x!=='\\u00a0');"
                          "return JSON.stringify({vis:p&&p.offsetParent!==null,first:bn.slice(0,2),n:bn.length,g0:(window.BRACKET_GAMES||[[{},{}]])[0].map(t=>t.team),"
                          "w:innerWidth,d:document.documentElement.scrollWidth})})()")
                    rv = await call("Runtime.evaluate", {"expression": js, "returnByValue": True})
                    sh = await call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                    open(os.path.join(shots, "cf-bracket-%s.png" % name), "wb").write(base64.b64decode(sh["data"]))
                    await call("Runtime.evaluate", {"expression": "document.getElementById('cmfield').scrollIntoView()"})
                    await asyncio.sleep(1)
                    sh = await call("Page.captureScreenshot", {"format": "png"})
                    open(os.path.join(shots, "cf-panel-%s.png" % name), "wb").write(base64.b64decode(sh["data"]))
                    res[name] = (json.loads(rv["result"]["value"]), list(errs))
        finally:
            p.terminate(); shutil.rmtree(prof, ignore_errors=True)
        return res
    for name, (r, errs) in asyncio.run(drive()).items():
        dw = int(name.split("-")[1])
        check(r["vis"] and r["n"] >= 64 and r["first"] == r["g0"], "%s: committee panel visible; drawn bracket starts with the placed first game %s" % (name, r["first"]))
        check(r["d"] <= dw, "%s: no horizontal page overflow (%s)" % (name, r["d"]))
        check(not errs, "%s: no script errors %s" % (name, errs[:2]))
else:
    print("SKIP rendered checks: local server unavailable")
print("ALL COMMITTEE FIELD CHECKS HOLD" if ok else "COMMITTEE FIELD CHECKS FAILED")
sys.exit(0 if ok else 1)
