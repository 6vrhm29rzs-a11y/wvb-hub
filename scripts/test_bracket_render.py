#!/usr/bin/env python3
"""mail 114: the DRAWN bracket must be the committee-informed placement -- tested on the processed artifact.

Why this file exists: strip_retired() (which runs on BOTH builds) carried the CMF-HOOK fence, so the private
page's drawing silently fell back to seed-order pairings while the panel beside it listed a different
placement. test_committee_field checked the placement FUNCTIONS and the payload's presence, so it stayed green.

Three layers:
  1. FROZEN FIXTURE, pure: 64 synthetic teams with hand-set home states, so the committee placement provably
     differs from seed-order pairings. committee_field.seed/place on it is the canonical placement.
  2. THE BUILT PAGE'S OWN renderBracket(), extracted from Cody/START-HERE.html and run in headless Chrome on that
     frozen fixture: every drawn first-round box (team, seed line, bid) and every phone region/pod must equal
     the canonical placement. Negative controls: the hook stripped (must WITHHOLD, never draw seed order) and
     the pre-fix behaviour (stripped, no withhold) must FAIL the equality check.
  3. LIVE-GENERATION CONSISTENCY on the served private page at 360/430/1440, plus the public build's privacy.
Also: strip_retired() must keep the hook; a strip_retired that lists it must fail that check.
"""
import asyncio, base64, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
PUB = os.path.join(REPO, "output", "vb_dashboard.html")
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m)
    ok = ok and bool(c)


import committee_field as CF

# ---------------------------------------------------------------- 1. frozen fixture (pure) ----
STATES = ["CA", "NE", "TX", "PA", "WA", "IA", "OK", "NY", "OR", "KS", "LA", "NJ", "AZ", "MN", "AR", "MD"]
TEAMS = ["Fixture %02d" % i for i in range(1, 65)]
CONF = dict((t, "Conf %02d" % ((i % 16) + 1)) for i, t in enumerate(TEAMS))      # 16 leagues x 4, spread by rank
HOME = dict((t, STATES[(i * 7) % 16]) for i, t in enumerate(TEAMS))              # deterministic, not rank-ordered
sel = {"field": [{"team": t, "bid": "AQ" if i >= 32 else "At-large", "rank": i + 1, "conf": CONF[t]}
                 for i, t in enumerate(TEAMS)],
       "qual": dict((t, {"t25w": [0, 0], "t50w": [0, 0]}) for t in TEAMS), "ranks": dict((t, i + 1) for i, t in enumerate(TEAMS))}
CF._HOME = dict((CF._norm(t), (HOME[t], None, 5)) for t in TEAMS)
ordered = CF.seed(sel)
pl = CF.place(ordered)
CANON = [[{"seed": t["order"] if t["order"] <= 32 else 99, "team": t["team"], "conf": t["conf"],
           "bid": "AQ" if t["bid"] == "AQ" else "at-large"} for t in g] for g in pl["games"]]
check([r["team"] for r in ordered] == TEAMS and all(r["line"] == (i + 4) // 4 for i, r in enumerate(ordered[:32])),
      "fixture: model order 1-64 and seed lines 1-8 (four per line) are deterministic")
# what the page draws with no placement: seed N v the Nth-from-last unseeded, quadrants by the fixed order
LINE_ORDER, QUAD_OF_POS = CF.LINE_ORDER, CF.QUAD_OF_POS
by_q = [dict() for _ in range(4)]
for r in ordered[:32]:   # lines 1-4: the 2025-verified grouping (mail 115); 5-8 positional, as the fallback does
    by_q[QUAD_OF_POS[CF.REGION_OF_OVERALL[r["order"]] if r["order"] <= 16 else (r["order"] - 1) % 4]][r["line"]] = r
rest = ordered[32:]
seed_order = []
for q in range(4):
    lo = list(reversed(LINE_ORDER)) if q in (1, 3) else LINE_ORDER
    for i, ln in enumerate(lo):
        sd = by_q[q][ln]; opp = rest[len(rest) - 1 - (sd["order"] - 1)]
        seed_order.append([sd["team"], opp["team"]] if i % 2 == 0 else [opp["team"], sd["team"]])
canon_names = [[t["team"] for t in g] for g in CANON]
differ = sum(1 for a, b in zip(canon_names, seed_order) if a != b)
check(differ >= 8, "fixture: geographic placement differs from seed-order pairings in %d of 32 first-round games" % differ)
check(len(set(t for g in canon_names for t in g)) == 64, "fixture: canonical placement covers 64 unique teams")
check(all(len(set(CONF[t["team"]] for t in [p["host"], p["seed2"]] + p["un"])) == 4 for p in pl["pods"]) or pl["notes"],
      "fixture: no pod holds two teams of one conference (or the conflict is stated)")


# ------------------------------------- 1b. mail 115: the OFFICIAL 2025 top-16 placement, reproduced ----
# Expected values are WRITTEN DOWN from the sources, never regenerated from place():
#   overall order -- 2025 field release p.4 (research/sources/2025-ncaa-wvb-bracket/release.txt);
#   regions       -- the official 2025 bracket (2025-2.pdf): Nebraska upper left, Pittsburgh lower left,
#                    Texas upper right, Kentucky lower right; quadrant ids are renderBracket's (Q0 UL, Q1 LL, Q2 UR, Q3 LR).
TOP16_2025 = ["Nebraska", "Kentucky", "Texas", "Pittsburgh", "SMU", "Stanford", "Arizona St.", "Louisville",
              "Texas A&M", "Creighton", "Wisconsin", "Purdue", "Minnesota", "Indiana", "Southern California", "Kansas"]
EXPECT_2025 = {   # team -> (quadrant, seed line), read off the bracket sheet
    "Nebraska": (0, 1), "Louisville": (0, 2), "Texas A&M": (0, 3), "Kansas": (0, 4),
    "Pittsburgh": (1, 1), "SMU": (1, 2), "Purdue": (1, 3), "Minnesota": (1, 4),
    "Texas": (2, 1), "Stanford": (2, 2), "Wisconsin": (2, 3), "Indiana": (2, 4),
    "Kentucky": (3, 1), "Arizona St.": (3, 2), "Creighton": (3, 3), "Southern California": (3, 4)}
T25 = TOP16_2025 + ["Filler %02d" % i for i in range(17, 65)]
sel25 = {"field": [{"team": t, "bid": "At-large", "rank": i + 1, "conf": "C25 %02d" % i} for i, t in enumerate(T25)],
         "qual": dict((t, {"t25w": [0, 0], "t50w": [0, 0]}) for t in T25), "ranks": dict((t, i + 1) for i, t in enumerate(T25))}
_home_saved = CF._HOME
CF._HOME = dict((CF._norm(t), (STATES[i % 16], None, 5)) for i, t in enumerate(T25))


def top16_of(placement):
    return dict((placement["quad"][q][ln]["team"], (q, ln)) for q in range(4) for ln in (1, 2, 3, 4))


got25 = top16_of(CF.place(CF.seed(sel25)))
check(got25 == EXPECT_2025, "2025 fixture: place() reproduces the official 2025 top-16 regions and lines exactly (16/16)%s"
      % ("" if got25 == EXPECT_2025 else " -- wrong: %s" % sorted(t for t in EXPECT_2025 if got25.get(t) != EXPECT_2025[t])))
_saved = CF.REGION_OF_OVERALL
CF.REGION_OF_OVERALL = dict((o, (o - 1) % 4) for o in range(1, 17))          # the old repeated 1/5/9/13 order
bad25 = top16_of(CF.place(CF.seed(sel25)))
CF.REGION_OF_OVERALL = _saved
CF._HOME = _home_saved
wrong = sorted(t for t in EXPECT_2025 if bad25.get(t) != EXPECT_2025[t])
check(bad25 != EXPECT_2025 and len(wrong) >= 8,
      "NEGATIVE CONTROL: the old repeated mapping misplaces %d of the 2025 top 16 (%s ...)" % (len(wrong), ", ".join(wrong[:3])))
check(all(len({(o - 1) // 4 for o in g}) == 4 for g in CF.TOP16_REGIONS) and sorted(CF.REGION_OF_OVERALL) == list(range(1, 17)),
      "TOP16_REGIONS: each region holds exactly one team of each of lines 1-4, and all 16 are placed")


# ------------------------------------------------- JS extraction (comment- and string-aware) ----
def js_block(src, head):
    i = src.index(head)
    j = src.index("{", i)
    depth, k, n = 0, j, len(src)
    while k < n:
        c = src[k]
        if src.startswith("//", k):
            k = src.index("\n", k)
            continue
        if src.startswith("/*", k):
            k = src.index("*/", k) + 2
            continue
        if c in "'\"`":
            q = c; k += 1
            while src[k] != q:
                k += 2 if src[k] == "\\" else 1
            k += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    raise ValueError("unbalanced " + head)


page = open(PAGE, encoding="utf-8").read() if os.path.exists(PAGE) else ""
RB = js_block(page, "function renderBracket() {") if page else ""
check("CMF-HOOK-BEGIN" in RB and "placed = true" in RB, "built private page: renderBracket carries the committee placement hook")
check("host.dataset.expect === 'placed' && !placed" in RB, "built private page: a missing placement is withheld, not drawn in seed order")
STRIPPED = re.sub(r"/\* CMF-HOOK-BEGIN \*/.*?/\* CMF-HOOK-END \*/", "", RB, flags=re.S)
PREFIX = re.sub(r"  if \(host\.dataset\.expect === 'placed' && !placed\) \{.*?\n  \}\n", "", STRIPPED, flags=re.S)
check(STRIPPED != RB and PREFIX != STRIPPED, "negative-control sources built (hook stripped; hook stripped and no withhold)")


def harness(src, games, expect=True):
    rows = "".join('<tr data-seed="%d" data-team="%s" data-conf="%s" data-bid="%s"><td></td></tr>'
                   % (r["order"], r["team"], r["conf"], "AQ" if r["bid"] == "AQ" else "at-large") for r in ordered)
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            "<style>" + BRACKET_CSS + "</style><section id='v-bracket'><table id='brkseeds'><tbody>%s</tbody></table>"
            "<div id='brkview'%s></div></section><script>const COLORS={};function logo(){return ''}"
            "function esc(v){return String(v==null?'':v).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]))}"
            "%s\n%s\nrenderBracket();</script>"
            % (rows, " data-expect='placed'" if expect else "",
               ("window.BRACKET_GAMES = %s;" % json.dumps(games)) if games is not None else "", src))


def css_rules(src):
    """the page's own bracket CSS (the phone/desktop switch included), so the harness renders with the real rules"""
    keep = []
    for m in re.finditer(r"[^{}]*\{[^{}]*\}|@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", src):
        blk = m.group(0)
        if re.search(r"\.(bwrap|bregions|bregpick|bpod|bpodh|breg|bgame|bside|bhalf|bcol|bgames|bnm|bsd)\b", blk):
            keep.append(blk.strip())
    return "\n".join(keep)


styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", page, flags=re.S)) if page else ""
BRACKET_CSS = css_rules(styles)
check("bregions" in BRACKET_CSS and "max-width:560px" in BRACKET_CSS.replace(" ", ""),
      "harness carries the page's own bracket CSS, phone switch included")

READ = r'''(()=>{
 const host=document.getElementById('brkview');
 const first=[...host.querySelectorAll('.bwrap .bcol')].filter(c=>c.querySelector('.bhd').textContent==='First round');
 const drawn=first.flatMap(c=>[...c.querySelectorAll('.bgame')].map(g=>[...g.querySelectorAll('.bside')].map(s=>
   ({team:s.dataset.team,bid:s.dataset.bid,line:s.querySelector('.bsd').textContent.trim(),tip:s.querySelector('.bnm').title}))));
 const regs=[...host.querySelectorAll('.breg')].map(r=>({q:+r.dataset.rq,hidden:r.hidden,
   games:[...r.querySelectorAll('.bgame')].map(g=>[...g.querySelectorAll('.bside')].map(s=>s.dataset.team)),
   heads:[...r.querySelectorAll('.bpodh')].map(h=>h.textContent)}));
 const picks=[...host.querySelectorAll('.bregpick [data-rq]')].map(b=>[+b.dataset.rq,b.textContent]);
 const vis=e=>!!e&&getComputedStyle(e).display!=='none';
 const clipped=[...host.querySelectorAll('.bregions .bnm')].filter(n=>n.offsetParent&&n.scrollWidth>n.clientWidth+1).map(n=>n.textContent);
 return {drawn,regs,picks,withheld:!!host.querySelector('.seasonwarn'),text:host.textContent.slice(0,200),
   note:(host.querySelector(':scope > .tnote')||{}).textContent||'',
   treeVisible:vis(host.querySelector('.bwrap')),regionsVisible:vis(host.querySelector('.bregions')),
   w:innerWidth,d:document.documentElement.scrollWidth,clipped};})()'''

CLICK = r'''(()=>{const b=[...document.querySelectorAll('#brkview .bregpick [data-rq]')][2]; if(!b) return null; b.click();
 return [...document.querySelectorAll('#brkview .breg')].filter(r=>!r.hidden).map(r=>+r.dataset.rq).concat([+b.dataset.rq]);})()'''


async def cdp_session(port, jobs):
    import websockets
    prof = tempfile.mkdtemp(prefix="brk-")
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
                          "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof, "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = {}
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen("http://localhost:%d/json" % port)); break
            except Exception:
                time.sleep(.3)
        async with websockets.connect([x for x in tabs if x["type"] == "page"][0]["webSocketDebuggerUrl"], max_size=10 ** 9) as ws:
            mid = [0]; errs = []
            async def call(m, par=None):
                mid[0] += 1; await ws.send(json.dumps({"id": mid[0], "method": m, "params": par or {}}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("method") == "Runtime.exceptionThrown":
                        errs.append(r["params"]["exceptionDetails"].get("text"))
                    if r.get("id") == mid[0]:
                        return r.get("result", {})
            await call("Runtime.enable")
            for key, url, width, wait, extra in jobs:
                errs.clear()
                await call("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 2, "mobile": width < 600})
                await call("Page.navigate", {"url": url}); await asyncio.sleep(wait)
                r = await call("Runtime.evaluate", {"expression": READ, "returnByValue": True})
                res = r.get("result", {}).get("value") or {}
                if extra:
                    res["extra"] = (await call("Runtime.evaluate", {"expression": extra, "returnByValue": True})).get("result", {}).get("value")
                if key.startswith("live"):
                    sh = await call("Page.captureScreenshot", {"format": "png"})
                    shots = os.path.join(REPO, "Cody", "coordination", "research", "BRACKET-114")
                    os.makedirs(shots, exist_ok=True)
                    open(os.path.join(shots, "%s.png" % key), "wb").write(base64.b64decode(sh["data"]))
                res["errs"] = list(errs)
                out[key] = res
    finally:
        p.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return out


def drawn_matches(res, canon):
    d = res.get("drawn") or []
    want = [[(t["team"], t["bid"], str((t["seed"] + 3) // 4) if t["seed"] <= 32 else "") for t in g] for g in canon]
    got = [[(s["team"], s["bid"], s["line"]) for s in g] for g in d]
    return len(d) == 32 and got == want


def regions_match(res, canon):
    regs = res.get("regs") or []
    by_q = dict((r["q"], r["games"]) for r in regs)
    return len(regs) == 4 and all(by_q.get(q) == [[t["team"] for t in g] for g in canon[q * 8:q * 8 + 8]] for q in range(4))


have_chrome = os.path.exists(CHROME) and bool(page)
if have_chrome:
    tmp = tempfile.mkdtemp(prefix="brkh-")
    _pubsrc = open(PUB, encoding="utf-8").read() if os.path.exists(PUB) else ""
    PUBRB = js_block(_pubsrc, "function renderBracket() {") if "function renderBracket() {" in _pubsrc else STRIPPED
    files = {"good": harness(RB, CANON), "stripped": harness(STRIPPED, CANON), "prefix": harness(PREFIX, CANON),
             "public": harness(PUBRB, None, expect=False)}
    for k, v in files.items():
        open(os.path.join(tmp, k + ".html"), "w", encoding="utf-8").write(v)
    jobs = [("fx-desk", "file://" + os.path.join(tmp, "good.html"), 1440, 1.0, None),
            ("fx-phone", "file://" + os.path.join(tmp, "good.html"), 390, 1.0, CLICK),
            ("fx-stripped", "file://" + os.path.join(tmp, "stripped.html"), 1440, 1.0, None),
            ("fx-prefix", "file://" + os.path.join(tmp, "prefix.html"), 1440, 1.0, None),
            ("fx-public", "file://" + os.path.join(tmp, "public.html"), 1440, 1.0, None)]
    R = asyncio.run(cdp_session(9361, jobs))
    shutil.rmtree(tmp, ignore_errors=True)
    g = R["fx-desk"]
    check(drawn_matches(g, CANON), "fixture render (built page's renderBracket): all 32 drawn first-round games, seed lines and bid labels == canonical placement")
    check(all(s["tip"].endswith("model order %d" % next(r["order"] for r in ordered if r["team"] == s["team"]))
              for gg in g["drawn"] for s in gg if s["line"]),
          "fixture render: a seeded box's tooltip names seed line and MODEL order, never 'national seed'")
    check(all(not s["line"] for gg in g["drawn"] for s in gg if next(r["order"] for r in ordered if r["team"] == s["team"]) > 32),
          "fixture render: unseeded teams carry no number")
    check(g["treeVisible"] and not g["regionsVisible"] and not g["errs"] and "approximate committee-style placement" in g["note"], "fixture render, desktop: the tree shows, the phone regions do not, no script errors %s" % g["errs"][:2])
    ph = R["fx-phone"]
    check(regions_match(ph, CANON), "fixture render, phone: each region lists exactly its quadrant's 8 games (4 pods), same as the tree")
    check(not ph["treeVisible"] and ph["regionsVisible"] and ph["d"] <= ph["w"] and not ph["clipped"],
          "fixture render, phone: one region at a time, no desktop tree, no page overflow (%s/%s), no clipped names %s" % (ph["d"], ph["w"], ph["clipped"][:3]))
    check([p[1] for p in ph["picks"]] == [pl["quad"][q][1]["team"] for q in sorted(range(4), key=lambda q: pl["quad"][q][1]["order"])],
          "fixture render, phone: region tabs are the four line-1 teams in model order")
    check(all(h.startswith("Pod · ") and "(assumed host)" in h for r in ph["regs"] for h in r["heads"]),
          "fixture render, phone: every pod names its assumed host")
    check(ph.get("extra") and len(ph["extra"]) == 2 and ph["extra"][0] == ph["extra"][1], "fixture render, phone: choosing a region shows that region only")
    st = R["fx-stripped"]
    check(st["withheld"] and not st["drawn"], "NEGATIVE CONTROL: hook stripped -> drawing WITHHELD with a stated reason (%s)" % st["text"][:80])
    check(not drawn_matches(st, CANON), "NEGATIVE CONTROL: hook stripped -> the equality check fails")
    pr = R["fx-prefix"]
    check(pr["drawn"] and not drawn_matches(pr, CANON),
          "NEGATIVE CONTROL: the pre-fix behaviour (hook stripped, no withhold) draws seed order and FAILS the equality check")
    pu = R["fx-public"]
    check(len(pu["drawn"]) == 32 and not pu["withheld"] and "implied by seed order" in pu["note"]
          and not pu["errs"], "public path (no placement expected): draws seed order, labelled as such, no errors")
    check([[s["team"] for s in gg] for gg in pu["drawn"]] == seed_order,
          "public build's OWN renderBracket: drawn pairings == seed order with lines 1-4 on the 2025 grouping (exact)")
    _tbl = json.dumps([list(g) for g in CF.TOP16_REGIONS]).replace(" ", "")
    check(_tbl in RB.replace(" ", "") and _tbl in PUBRB.replace(" ", "") and "{{TOP16_REGIONS_JSON}}" not in RB + PUBRB,
          "both builds carry the one TOP16_REGIONS table, substituted from committee_field (no placeholder left)")
else:
    check(False, "Chrome and the built private page are required for the render checks")

# ------------------------------------------------------- strip_retired must keep the hook ----
import build_hub as B
sample = "a /* CMF-HOOK-BEGIN */ hook /* CMF-HOOK-END */ b"
check("CMF-HOOK-BEGIN" in B.strip_retired(sample), "strip_retired() keeps the committee placement hook (private build)")
check("CMF-HOOK-BEGIN" not in B.strip_private(sample), "strip_private() still removes it (public build)")
import inspect
bad_src = inspect.getsource(B.strip_retired).replace(
    '("/* FILMROOM-HOOK-BEGIN */", "/* FILMROOM-HOOK-END */"),',
    '("/* FILMROOM-HOOK-BEGIN */", "/* FILMROOM-HOOK-END */"), ("/* CMF-HOOK-BEGIN */", "/* CMF-HOOK-END */"),', 1)
ns = {"re": re, "RETIRED_VIEWS": B.RETIRED_VIEWS, "_drop_section": B._drop_section}
exec(bad_src, ns)
check("CMF-HOOK-BEGIN" not in ns["strip_retired"](sample),
      "NEGATIVE CONTROL: a strip_retired() that lists CMF-HOOK removes it, so the keep-check above would fail")

# --------------------------------------------- 3. live generation: the built and served page ----
sec = page[page.index('<section id="v-bracket"'):] if page else ""
sec = sec[:sec.index("</section>")] if sec else ""
m = re.search(r"window\.BRACKET_GAMES = (\[.*?\]);</script>", sec)
pg = json.loads(m.group(1)) if m else []
import html as _h
rows = [(int(a), _h.unescape(b), _h.unescape(c)) for a, b, c in
        re.findall(r'<tr data-seed="(\d+)" data-team="([^"]*)" data-conf="[^"]*" data-bid="([^"]*)">', sec)]
check(len(pg) == 32 and len(set(t["team"] for gg in pg for t in gg)) == 64, "built page: 32 placed games, 64 unique teams")
check(len(rows) == 64 and set(r[1] for r in rows) == set(t["team"] for gg in pg for t in gg), "built page: full-field table == placed field")
check(all((dict((r[1], r[2]) for r in rows)[t["team"]] == "AQ") == (t["bid"] == "AQ") for gg in pg for t in gg), "built page: bid labels agree")
lines = re.findall(r'<tr data-seed="(\d+)"[^>]*>(?:<td[^>]*>.*?</td>){4}<td class="n">(.*?)</td>', sec)
check(len(lines) == 64 and all((l == str((int(o) + 3) // 4)) if int(o) <= 32 else ("unseeded" in l) for o, l in lines),
      "built page: seed line shown for the top 32 only; the other 32 read 'unseeded', never 33-64 as seeds")
check('data-expect="placed"' in sec and 'id="cmfield"' in sec, "built page: the bracket declares it expects a placement")
check(sec.index('id="brkview"') < sec.index('id="brkfield"') and sec.index('cm-regs') < sec.index('id="brkview"'),
      "built page: regional No.1s, then the bracket, then the full field (in a fold)")
for blk in ("How this field is built", "Model order, seed lines and regions", "What this bracket does not know", "Full field"):
    check(re.search(r"<details[^>]*><summary><b>%s</b>" % re.escape(blk), sec) is not None, "built page: '%s' is a named disclosure" % blk)
check("2025-based placement convention, supported by the official bracket" in sec and "hub convention" not in sec,
      "built page: the line 1-4 grouping is labelled a 2025-based convention supported by the official bracket")
# the FINAL stripped private artifact's map table must follow the 2025 grouping; the old repeated order must not fit it
mp = re.findall(r"<tr><td[^>]*>(\d+)</td><td[^>]*>(.*?)</td><td[^>]*>(\d)</td><td[^>]*>(.*?)</td>",
                sec[sec.index("Model order, seed lines and regions"):] if "Model order, seed lines and regions" in sec else "")
reg_of = dict((int(o), re.sub("<[^>]+>", "", rg)) for o, _, _, rg in mp if int(o) <= 16)
fits = lambda f: len(reg_of) == 16 and all(len({reg_of[o] for o in range(1, 17) if f(o) == i}) == 1 for i in range(4)) \
    and len({reg_of[o] for o in range(1, 5)}) == 4
check(fits(lambda o: CF.REGION_OF_OVERALL[o]), "built page: model #1-16 sit in regions exactly by the 2025 grouping %s"
      % [[o for o in range(1, 17) if CF.REGION_OF_OVERALL[o] == i] for i in range(4)])
check(not fits(lambda o: (o - 1) % 4), "NEGATIVE CONTROL: the old repeated 1/5/9/13 grouping does NOT fit the built page")

try:
    urllib.request.urlopen(BASE + "/START-HERE.html", timeout=5); served = True
except Exception:
    served = False
if served and have_chrome:
    jobs = [("live-%d" % w, BASE + "/START-HERE.html#/bracket", w, 8.0,
             "JSON.stringify({regs:[...document.querySelectorAll('#cmfield .cm-reg b')].map(b=>b.textContent),"
             "lead:(document.querySelector('#v-bracket > p.lead')||{}).textContent||''})") for w in (360, 430, 1440)]
    L = asyncio.run(cdp_session(9362, jobs))
    ones = sorted([(t["seed"], t["team"]) for gg in pg for t in gg if t["seed"] <= 4])
    for k, r in L.items():
        w = int(k.split("-")[1])
        ex = json.loads(r.get("extra") or "{}")
        check(drawn_matches(r, pg), "%s: drawn first round == the page's placed games (team, line, bid)" % k)
        check(regions_match(r, pg), "%s: phone regions == the placed quadrants" % k)
        check(ex.get("regs") == [t for _, t in ones], "%s: regional No.1 cards == the four line-1 teams in model order %s" % (k, ex.get("regs")))
        check("2026" in ex.get("lead", "") and len(ex.get("lead", "")) < 400, "%s: short lead naming the season and basis" % k)
        check(r["d"] <= w and not r["errs"], "%s: no page overflow (%s), no script errors %s" % (k, r["d"], r["errs"][:2]))
        check(r["regionsVisible"] == (w <= 560) and r["treeVisible"] == (w > 560) and not r["clipped"],
              "%s: %s, no clipped names" % (k, "phone regions" if w <= 560 else "desktop tree"))
else:
    print("SKIP live render: the local server is not reachable at %s" % BASE)

pub = open(PUB, encoding="utf-8").read() if os.path.exists(PUB) else ""
if pub:
    check(all(x not in pub for x in ("cmfield", "BRACKET_GAMES", "Committee-informed", "CMF-HOOK", 'data-expect="placed"', "cm-regs")),
          "public build: no committee field, placement payload, hook or placed-expectation")
print("BRACKET RENDER CHECKS " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
