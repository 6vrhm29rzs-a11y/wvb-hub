#!/usr/bin/env python3
"""mail 100 guards: seeded entry rounds, venue use, probability totals, upsets advance, actual-result precedence,
post-tournament field agreement, duplicate fixtures and stale forecasts; rendered views when the local server is up."""
import json, os, sys, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")   # mail 105: an isolated copy serves on its own port
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
import conf_tournaments as CT
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


# ---- bracket structure (pure)
t = CT.build_tree(15, "bigten15")
er = dict((s, CT.entry_round(t, s)) for s in range(1, 16))
check(all(er[s] == 2 for s in (1, 2, 3, 4)) and all(er[s] == 1 for s in (5, 6, 7, 8, 9)) and all(er[s] == 0 for s in range(10, 16)),
      "Big Ten: 1-4 enter in the quarterfinals, 5-9 in round two (8 v 9), 10-15 in round one")
check(any(m[1] == 8 and m[2] == 9 for m in CT.matches(t)), "Big Ten: the 8 v 9 match exists")
t = CT.build_tree(8, "horizon8")
er = dict((s, CT.entry_round(t, s)) for s in range(1, 9))
check(er[1] == er[2] == 2 and er[3] == er[4] == 1 and all(er[s] == 0 for s in range(5, 9)), "Horizon: staggered entry (1-2 semis, 3-4 round two, 5-8 round one)")
t = CT.build_tree(6)
er = dict((s, CT.entry_round(t, s)) for s in range(1, 7))
check(er[1] == er[2] == 1 and all(er[s] == 0 for s in (3, 4, 5, 6)), "six-team standard: seeds 1-2 bye, 3-6 play first")
t = CT.build_tree(10)
check(len(CT.matches(t)) == 9 and sum(1 for m in CT.matches(t) if m[3] == 0) == 2, "ten-team standard: 9 matches, 2 play-in matches")
for n in (4, 6, 8, 10, 13, 15):
    tt = CT.build_tree(n, "bigten15" if n == 15 else "standard")
    check(len(CT.matches(tt)) == n - 1, "%d teams -> %d matches (single elimination)" % (n, n - 1))

# ---- venue use
cand = json.load(open(os.path.join(REPO, "Cody", "data", "power_candidate", "v2so_preview.json")))
T = cand["teams"]; names = sorted(T, key=lambda n: T[n]["rank"])
seeds = {1: names[10], 2: names[11]}
pn, _, _ = CT.make_prob(cand, "neutral", seeds)
ph, _, home_of = CT.make_prob(cand, names[11], seeds)        # seed 2's school hosts
pt, _, home_t = CT.make_prob(cand, "top_seed", seeds)
check(ph(1, 2) < pn(1, 2) and home_of(1, 2) == names[11], "a named host school is at home when it plays (p moves toward the host)")
check(pt(1, 2) > pn(1, 2) and home_t(1, 2) == names[10], "top_seed hosting gives the No. 1 seed home court")
check(abs(pn(1, 2) + pn(2, 1) - 1) < 1e-12, "neutral probabilities are complementary")
# ---- probability totals, upsets advance, actual precedence
row = {"field": 4, "structure": "standard", "host": "neutral"}
s4 = dict((i + 1, names[20 + i]) for i in range(4))
r = CT.project("TEST", row, s4, cand, n=4000)
check(abs(sum(r["aq_prob"].values()) - 1) < 1e-9, "AQ probabilities sum to 1")
r2 = CT.project("TEST", row, s4, cand, n=4000)
check(r2["aq_prob"] == r["aq_prob"], "reproducible with the fixed seed")
upset = {(0, frozenset((s4[1], s4[4]))): s4[4]}              # actual: No. 4 beat No. 1 in the semifinal (round 0)
r3 = CT.project("TEST", row, s4, cand, actual=upset, n=2000)
check(r3["aq_prob"][s4[1]] == 0 and any(m["source"] == "actual" and m["winner"] == s4[4] for m in r3["chalk"]),
      "an actual result overrides the simulation (No. 1 eliminated in every run)")
fin = [m for m in r3["chalk"] if m["round"] == 1][0]
check(s4[4] in (fin["a"], fin["b"]), "the upset winner advances to the final (later matchup changes)")
rem = {(1, frozenset((s4[1], s4[4]))): s4[4]}                # same pair filed for the WRONG round (they meet in round 0)
r4 = CT.project("TEST", row, s4, cand, actual=rem, n=2000)
check(r4["aq_prob"][s4[1]] > 0 and not any(m["source"] == "actual" for m in r4["chalk"]) and r4["unbound_actuals"],
      "a result bound to another round (or a regular-season rematch) never overrides the forecast, and is reported unbound")
# ---- mail 101 structures
t = CT.build_tree(16, "sec16")
er = dict((s_, CT.entry_round(t, s_)) for s_ in range(1, 17))
check(all(er[x] == 2 for x in (1, 2, 3, 4)) and all(er[x] == 1 for x in (5, 6, 7, 8)) and all(er[x] == 0 for x in range(9, 17))
      and len(CT.matches(t)) == 15, "SEC: 16 teams, 1-4 two byes, 5-8 one bye, 9-16 open, 15 matches")
t = CT.build_tree(10, "sunbelt10")
pairs = set((m[1], m[2]) for m in CT.matches(t) if isinstance(m[1], int) and isinstance(m[2], int))
check({(9, 5), (4, 10), (7, 3), (2, 8)} <= pairs and len(CT.matches(t)) == 9,
      "Sun Belt: official bracket (W4 v E5, E4 v W5, W2 v E3, E2 v W3), 9 matches")
er = dict((s_, CT.entry_round(t, s_)) for s_ in range(1, 11))
check(er[1] == er[6] == 1 and er[2] == er[3] == er[7] == er[8] == 1 and all(er[x] == 0 for x in (4, 5, 9, 10)),
      "Sun Belt: division 1-3 seeds start in the quarterfinals, 4-5 in round one")
t = CT.build_tree(10)
check(set((m[1], m[2]) for m in CT.matches(t) if m[3] == 0) == {(8, 9), (7, 10)}, "SoCon: 8 v 9 and 7 v 10 open")
s6 = dict((i + 1, names[30 + i]) for i in range(6))
pr, _, ho = CT.make_prob(cand, "r0_higher_then_top", s6)
check(ho(3, 6, 0) == s6[3] and ho(4, 5, 0) == s6[4] and ho(1, 4, 1) == s6[1] and ho(2, 3, 1) is None,
      "Patriot/Metro: first round at the higher seed, later rounds at the No. 1 seed only")
# ---- build-level checks
import build_hub as B, build_rankings_board as BOARD
os.environ["WVB_POWER_DEFAULT"] = "candidate"
teams, field, *_ = BOARD.build()
ct, scen, _ = B.conf_tournaments(teams, use_observed=False)   # the projection path, independent of how far the real tournaments have got
cfg = CT.load_cfg()
check(ct["SEC"]["seeds"] and len(ct["SEC"]["seeds"]) == 16, "SEC projected with 16 teams")
check(len(ct["Big Sky"]["seeds"]) == 8, "Big Sky projected with 8 teams")
check(ct["Big East"]["host_effective"] == "Creighton" and ct["Pac-12"]["host_effective"] == "Colorado St.", "Big East at Creighton, Pac-12 at Colorado St. (home court)")
sbd = cfg["conferences"]["Sun Belt"]["divisions"]
check(all(ct["Sun Belt"]["seeds"][i] in sbd["East"] for i in range(1, 6)) and all(ct["Sun Belt"]["seeds"][i] in sbd["West"] for i in range(6, 11)),
      "Sun Belt seeded within divisions (E1-E5, W1-W5)")
check(all(v.get("seed_basis") == "projected" for v in ct.values() if not v.get("error")), "no league has announced seeds yet: every league says projected")
check(len(ct) == 29 and not [k for k, v in ct.items() if v.get("error")], "29 tournament conferences projected, none unresolved")
check(all(abs(sum(v["aq_prob"].values()) - 1) < 1e-9 for v in ct.values()), "every league's AQ chances sum to 1")
check(all(len(v["seeds"]) == min(cfg["conferences"][k]["field"], len(v["seeds"])) for k, v in ct.items()), "field sizes follow the sourced format")
check(not [k for k, v in ct.items() if v["fallback_pairs"]], "no 50/50 fallback needed (every pair rated)")
cpost = B.rpi_cutline(teams, field, ranking="post", scenario=scen)
aq_post = dict((B._ckey(r["conf"]) if B._ckey(r["conf"]) != "wac" else "uac", r["team"]) for r in cpost["field"] if r["bid"] == "AQ")
check(all(aq_post.get(ck) == tm for ck, tm in scen["aq"].items() if ck in aq_post), "post-tournament AQs are the scenario's tournament champions")
check(len(cpost["field"]) == 64 and len(set(r["team"] for r in cpost["field"])) == 64, "post-tournament field: 64 unique bids (cut #%s)" % cpost["cut_rank"])
fm = cpost["futures"]
check(fm["scenario_games"] == len(scen["games"]), "every scenario tournament match enters the post-tournament RPI (%d)" % fm["scenario_games"])
# ---- provenance and overlapping regular-season / tournament fixtures (synthetic, real code) -- mail 102
real_load = B.load
sec = ct["SEC"]["seeds"]; ta, tb = sec[1], sec[8]
import season_counts as SC
from reconcile_2025 import norm as _nm
fin_doc = real_load("data/data_2026.json")
# a real counted SEC-vs-SEC final, for the actual-side rejected-entry check
secset = set(_nm(t) for t in sec.values())
rf = next(g for g in SC.countable(fin_doc["games"], 2026, need_line=True, d1_only=True)
          if g.get("state") == "F" and SC.winner_index(g) is not None and len(g["teams"]) == 2
          and all(_nm(t["name_short"]) in secset for t in g["teams"]))
rf_t = [t["name_short"] for t in rf["teams"]]; rf_loser = rf_t[1 - SC.winner_index(rf)]
def fake_load(path):
    d = real_load(path)
    if path.endswith("conf_tournament_results.json"):
        return {"results": [
            {"conf": "SEC", "round": 2, "teams": [ta, tb], "winner": tb, "game_id": "CT-REJ", "source": "x"},           # not a final
            {"conf": "SEC", "round": 0, "teams": rf_t, "winner": rf_loser, "game_id": str(rf["game_id"]), "source": "x"},  # wrong winner
        ], "scheduled_fixtures": [
            {"conf": "SEC", "teams": [ta, tb], "game_id": "CT-OK", "date": "2026-11-22", "source": "SEC bracket (synthetic)"},
            {"conf": "SEC", "teams": [ta, tb], "game_id": "CT-NOSRC", "date": "2026-11-22"},                               # no source
        ], "announced_seeds": {}}
    if path.endswith("predictions_2026.json") and d:
        d = dict(d); g0 = dict(next(g for g in d["games"] if (g.get("start_epoch") or 0) > time.time()))
        mk = lambda gid, dt, off: dict(g0, game_id=gid, date=dt, home=ta, away=tb, start_epoch=time.time() + 86400 * off, home_win=.6)
        d["games"] = d["games"] + [mk("RS-1", "2026-11-14", 8), mk("RS-W", "2026-11-22", 16), mk("CT-REJ", "2026-11-22", 16),
                                   mk("CT-NOSRC", "2026-11-22", 16), mk("CT-OK", "2026-11-22", 16)]
    return d
def fresh():
    if hasattr(B, "_CT_CTX"): del B._CT_CTX
    B._CT_EXCL.clear()
sec_rows = [{"team": t_, "ckey": "sec", "conf": "SEC", "orank": 1, "eligible": True} for t_ in sec.values()]
# the baseline is an EMPTY ledger: the fake ledger below replaces the real one, so comparing it with the real
# (now populated) ledger would measure the real tournament results rather than the synthetic entries
B.load = lambda path: ({"results": [], "scheduled_fixtures": [], "announced_seeds": {}}
                       if path.endswith("conf_tournament_results.json") else real_load(path))
fresh(); base_pj, _ = B.project_conf_champions(sec_rows); base_fx, base_fm = B.rpi_futures(); base_cr = B.cut_records(projected=True)
B.load = fake_load
try:
    fresh()
    ctx = B.ct_context()
    whys = dict((str(r.get("game_id")), r["rejected"]) for r in ctx["rejected"])
    check(whys.get("CT-REJ") == "game id is not a counted final" and whys.get(str(rf["game_id"])) == "winner does not match the final"
          and whys.get("CT-NOSRC") == "no tournament source" and not ctx["bound"],
          "rejected ledger entries (not a final / wrong winner / unsourced fixture) are rejected, never applied")
    check(ctx["scheduled_gids"] == {"CT-OK"}, "only the sourced scheduled fixture is a confirmed tournament fixture")
    pj, pm = B.project_conf_champions(sec_rows)
    check("CT-OK" in B._CT_EXCL and not ({"RS-1", "RS-W", "CT-REJ", "CT-NOSRC"} & B._CT_EXCL),
          "same pair: only the confirmed tournament fixture leaves the regular-season path; in-window RS-W, rejected and unsourced ids stay")
    check("RS-W" in ctx["candidates"] and "CT-REJ" in ctx["candidates"], "the window only surfaces candidates (RS-W, CT-REJ listed)")
    # each kept fixture counts exactly once in standings expectations: 4 extra same-pair matches
    d_left = pj[ta]["left"] - base_pj[ta]["left"]
    check(d_left == 4, "standings: RS-1, RS-W, CT-REJ, CT-NOSRC each add exactly one remaining match (got %s)" % d_left)
    check(pj[rf_t[0]]["cw"] + pj[rf_t[0]]["cl"] == base_pj[rf_t[0]]["cw"] + base_pj[rf_t[0]]["cl"],
          "actual side: a final behind a REJECTED ledger entry stays in regular-season standings")
    fx, fm2 = B.rpi_futures()
    check(fm2["projected_games"] - base_fm["projected_games"] == 4 and "CT-OK" in B._CT_EXCL,
          "Projected RPI: the four kept fixtures enter once each; the confirmed one is excluded")
    cr = B.cut_records(projected=True)
    k = _nm(ta)
    check(cr[k]["n"] - base_cr[k]["n"] == 4, "projected records: same four, exactly once")
finally:
    B.load = real_load
    fresh()
ids_s = [g[2] for g in scen["games"]]
check(len(ids_s) == len(set(ids_s)) and all(g[2].startswith("ct-") for g in scen["games"]),
      "each simulated tournament match enters the post-tournament scenario exactly once")
check(not scen["ledger_rejected"] and not scen["unprovenanced_in_window_finals"], "real ledger: nothing rejected, no unprovenanced in-window finals")
# duplicates and stale forecasts
preds = json.load(open(os.path.join(REPO, "Cody", "data", "power_candidate", "predictions_2026.json")))
now = time.time()
fut = [g for g in preds["games"] if (g.get("start_epoch") or 0) > now]
ids = [g["game_id"] for g in fut]
pairs = [(g["date"], tuple(sorted((g["home"], g["away"])))) for g in fut]
check(len(ids) == len(set(ids)) and len(pairs) == len(set(pairs)), "no duplicate future fixtures (%d)" % len(ids))
# mail 116: "final" = the AUTHORITATIVE played-match set (season_counts.completed_gids: every final class
# except 'empty'). Raw state=='F' also matched the feed's EMPTY final -- USC at Rutgers, flipped to F with no
# winner, sets or lines before first serve -- which counts nowhere and is correctly still forecast.
import gamelog as _GLt, season_counts as _SCt
finals = _SCt.completed_gids(_GLt.load_games_jsonl(os.path.join(REPO, "data", "raw", "2026", "games.jsonl")), 2026)
check(not [g for g in fut if str(g["game_id"]) in finals], "no forecast is used for a match that is already final (played, by the authoritative policy)")
_raw = set(str(g["game_id"]) for g in json.load(open(os.path.join(REPO, "data", "data_2026.json")))["games"] if g.get("state") == "F")
_empty_fut = [g["game_id"] for g in fut if str(g["game_id"]) in _raw and str(g["game_id"]) not in finals]
print("  note: %d future fixture(s) the feed marks F with no result (empty final, still forecast): %s" % (len(_empty_fut), _empty_fut[:3]))
check(len(set(g[2] for g in scen["games"])) == len(scen["games"]), "no duplicate scenario tournament matches")

# ---- rendered (local only)
try:
    urllib.request.urlopen(BASE + "/START-HERE.html", timeout=5); served = True
except Exception:
    served = False
if served:
    import asyncio, shutil, subprocess, tempfile, base64
    CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    async def drive():
        import websockets
        prof = tempfile.mkdtemp(prefix="ctprobe-"); out = {}
        p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9342", "--user-data-dir=" + prof, "about:blank"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try: tabs = json.load(urllib.request.urlopen("http://localhost:9342/json")); break
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
                    for route, js in (("#/bracket/conference", "JSON.stringify({vis: !document.getElementById('conftour').hidden, cards: document.querySelectorAll('#conftour .ct-card').length, w: innerWidth, d: document.documentElement.scrollWidth})"),
                                      ("#/bracket/cutline/post", "JSON.stringify({vis: !document.getElementById('cl-post').hidden, rows: document.querySelectorAll('#cl-post .cl-t tr.cl-aq, #cl-post .cl-t tr.cl-al').length, line: document.querySelectorAll('#cl-post .cl-t tr.cl-line').length, w: innerWidth, d: document.documentElement.scrollWidth})")):
                        await call("Page.navigate", {"url": BASE + "/START-HERE.html" + route}); await asyncio.sleep(6)
                        rv = await call("Runtime.evaluate", {"expression": js, "returnByValue": True})
                        res[route] = json.loads(rv["result"]["value"])
                        sh = await call("Page.captureScreenshot", {"format": "png"})
                        open(os.path.join(REPO, "Cody", "coordination", "research", "POWER-PREVIEW-2026-11-05",
                                          "ct-%s-%s.png" % (route.split("/")[-1], name)), "wb").write(base64.b64decode(sh["data"]))
                    out[name] = (res, list(errs))
        finally:
            p.terminate(); shutil.rmtree(prof, ignore_errors=True)
        return out
    for name, (res, errs) in asyncio.run(drive()).items():
        dw = int(name.split("-")[1]); c1 = res["#/bracket/conference"]; c2 = res["#/bracket/cutline/post"]
        check(c1["vis"] and c1["cards"] == 29 and c1["w"] == dw and c1["d"] <= dw, "%s: conference view shows 29 tournaments and fits (%s)" % (name, c1))
        check(c2["vis"] and c2["rows"] == 64 and c2["line"] == 1 and c2["d"] <= dw, "%s: post-tournament cut line view (64 rows, one line) fits" % name)
        check(not errs, "%s: no script errors %s" % (name, errs[:2]))
else:
    print("SKIP rendered checks: local server unavailable")
print("ALL CONFERENCE TOURNAMENT CHECKS HOLD" if ok else "CONFERENCE TOURNAMENT CHECKS FAILED"); sys.exit(0 if ok else 1)
