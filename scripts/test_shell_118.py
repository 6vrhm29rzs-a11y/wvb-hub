#!/usr/bin/env python3
"""mail 118: the shared shell and the cleaned Rankings screen.

1. STATIC, on both built pages: the everyday five (Scores, Rankings, Teams, Stats, Bracket) + More;
   My Ballot only in the private More group (absent from the public page); the score tape and ticker
   scoped to Scores; one concise status with diagnostics behind a named Details; Rankings opens with
   the POWER line and one controls row whose single Compare holds every alternative; the views stay
   OUTSIDE any fold; the method essay closed below the table; the stale method sentence corrected.
2. LIVE, on the served private page in headless Chrome (true device metrics, not a resized window):
   rendered text contrast on the main routes; 360/390/430/1440 layout (no page overflow, the first
   ranked row's height); a 150%-text phone equivalent; keyboard focus ring; search; Compare round
   trip; team -> Back keeps the search; reload keeps the route; Details survives the live re-render;
   the phone's hidden columns reachable through Compare -> Compare sources.
Not a physical iPhone Safari test.
"""
import asyncio, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = os.environ.get("WVB_RENDER_BASE", "http://localhost:8799")
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m)
    ok = ok and bool(c)


priv = open(os.path.join(REPO, "Cody", "START-HERE.html"), encoding="utf-8").read()
pub = open(os.path.join(REPO, "output", "vb_dashboard.html"), encoding="utf-8").read()

# ------------------------------------------------------------------ 1. static ----
def pri(h):
    nav = h[h.index("<nav role=\"tablist\">"):h.index("</nav>")]
    return [(v, t.strip()) for v, t in re.findall(r'<button role="tab"[^>]*data-v="([a-z]+)"[^>]*class="pri">([^<]+)</button>', nav)]
for nm, h in (("private", priv), ("public", pub)):
    check([v for v, _ in pri(h)] == ["scores", "rankings", "teams", "leaders", "bracket"],
          "%s: the everyday five in order (Scores, Rankings, Teams, Stats, Bracket) %s" % (nm, pri(h)))
    check('id="morebtn"' in h and 'data-v="players"' in h and 'data-v="standings"' in h,
          "%s: More keeps Players, Player ratings, Standings" % nm)
    if nm == "private":   # the cut line and conference tournaments are private views
        check("#/bracket/cutline" in h and "#/bracket/conference" in h,
              "%s: the RPI cut line and conference tournaments stay under Bracket (deep links)" % nm)
    check("body:not([data-view=scores]) #cstape,body:not([data-view=scores]) #livetick{display:none!important}" in h,
          "%s: the score tape and ticker are scoped to Scores (no permanent strip)" % nm)
    check("details class=\"cs-det\"" in h and "<summary>Details</summary>" in h,
          "%s: header diagnostics sit behind a named Details" % nm)
nav_priv = priv[priv.index("<nav role=\"tablist\">"):priv.index("</nav>")]
check('data-v="ballot"' in nav_priv[nav_priv.index("MOREPRIV-BEGIN"):nav_priv.index("MOREPRIV-END")]
      and not re.search(r'role="tab"[^>]*data-v="ballot"', nav_priv),
      "private: My Ballot is in the More overflow (private group), not a primary")
check('data-v="ballot"' not in pub and "mgpriv" not in pub, "public: no ballot entry and no private group")
sec = priv[priv.index('<section id="v-rankings"'):]
sec = sec[:sec.index("</section>")]
order = [sec.find(x) for x in ('id="rkline"', '<div class="ctl">', 'id="rkcompare"', 'id="pollview"', 'id="rankpanel"', 'id="rkhow"')]
check(all(o >= 0 for o in order) and order == sorted(order),
      "Rankings order: POWER line, controls row (with Compare), views, table, then the method fold %s" % order)
cmp_ = sec[sec.index('id="rkcompare"'):sec.index("</details>", sec.index('id="rkcompare"'))]
check(all(x in cmp_ for x in ('class="rulerbar"', 'id="refpick"', 'class="seg basisseg"', 'id="refcols"', "vx-key")),
      "Compare holds the other rankings, the reference picker, the POWER-order variants, the source columns and the key")
check('id="pollview"' not in cmp_ and 'id="rankpanel"' not in cmp_, "no VIEW sits inside the Compare fold")
check('<details class="rkhow" id="rkhow">' in sec and '<details class="rkhow" open' not in sec,
      "the method essay is a closed, named fold below the table")
check(sec.index('id="rkline"') < sec.index('vx-key'), "no permanent legend precedes the rows (the key is inside Compare)")
check("blank until the second freeze" not in priv and "own private weekly freeze" in priv,
      "the stale movement sentence is corrected, not just hidden")

# ------------------------------------------------------------------ 2. live ----
CONTRAST = open(os.path.join(REPO, "scripts", "shell_contrast.js"), encoding="utf-8").read()



GEOM = r"""(()=>{const rows=[...document.querySelectorAll('#rbody tr.row')].filter(r=>r.offsetParent).slice(0,6);
 const bad=[],zero=[],clip=[];let cells=0;
 for(const tr of rows){const tds=[...tr.children].filter(td=>getComputedStyle(td).display!=='none'&&td.textContent.trim());
  const R=tds.map(td=>({td,r:td.getBoundingClientRect()}));cells+=R.length;
  for(const a of R){if(a.r.width<1)zero.push((tr.dataset.team||'')+':'+(a.td.dataset.l||a.td.className));
   if(!a.td.classList.contains('tm')&&!a.td.classList.contains('cf')&&a.td.scrollWidth>a.td.clientWidth+1)clip.push((tr.dataset.team||'')+':'+(a.td.dataset.l||a.td.className)+' '+a.td.scrollWidth+'>'+a.td.clientWidth);}
  for(let i=0;i<R.length;i++)for(let j=i+1;j<R.length;j++){const a=R[i].r,b=R[j].r;const w=Math.min(a.right,b.right)-Math.max(a.left,b.left),h=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
   if(w>1&&h>1)bad.push((tr.dataset.team||'')+': '+(R[i].td.dataset.l||R[i].td.className)+' x '+(R[j].td.dataset.l||R[j].td.className));}}
 const rs=rows[0]&&rows[0].querySelector('td.rs'),av=rows[0]&&rows[0].querySelector('td.c-avca');
 return {rows:rows.length,cells,overlap:bad.slice(0,6),n_overlap:bad.length,zero:zero.slice(0,6),clip:clip.slice(0,6),
   rs:rs?[Math.round(rs.getBoundingClientRect().left),Math.round(rs.getBoundingClientRect().top)]:null,
   avca:av?[Math.round(av.getBoundingClientRect().left),Math.round(av.getBoundingClientRect().top)]:null,
   w:innerWidth,d:document.documentElement.scrollWidth}})()"""
SOURCES_ON = r"""(async()=>{const c=document.getElementById('refcols');if(!c.checked)c.click();await new Promise(s=>setTimeout(s,500));return c.checked})()"""
# TEST-ONLY text enlargement: every element's COMPUTED font size x1.5 written inline (this is what
# scales fixed-pixel labels too), plus the card's pseudo-element labels (which inline style cannot
# reach) raised by one injected rule. The user's browser preferences are never touched.
ENLARGE = r"""(()=>{
 /* mail 120: TWO PHASES. Phase 1 reads every element's ORIGINAL computed size before any mutation;
    phase 2 writes 1.5x each captured value. (Reading and writing in one parent-first pass made an
    inheriting child read its already-enlarged parent and compound.) Pseudo-element labels are
    scaled from their OWN measured baseline, per selector, not set to a fixed size. */
 const P=[['.rk3 tr.row td[data-l]','::before'],['.rk3 tbody td.rs','::before'],['.rk3 tr.row td.c-ref','::before']];
 const REP={status:'#csstatus .cs-now b',changed:'#csstatus span[title] b',nav:'nav button.pri',navmore:'.morebtn',
   value:'#rbody tr.row td.pps',power:'#rbody tr.row td.pw',name:'#rbody tr.row td.tm',search:'#q'};
 const px=e=>parseFloat(getComputedStyle(e).fontSize);
 const els=[...document.querySelectorAll('body *')];const orig=els.map(px);
 const pse=P.map(([sel,ps])=>{const e=document.querySelector(sel);return e?parseFloat(getComputedStyle(e,ps).fontSize):null});
 const before={};for(const k in REP){const e=document.querySelector(REP[k]);before[k]=e?px(e):null}
 for(const k of [0,1,2]){const e=document.querySelector(P[k][0]);before['pseudo'+k]=pse[k]}
 els.forEach((e,i)=>{if(orig[i])e.style.setProperty('font-size',(orig[i]*1.5)+'px','important')});
 const st=document.createElement('style');st.textContent=P.map(([sel,ps],i)=>pse[i]?sel+ps+'{font-size:'+(pse[i]*1.5)+'px!important}':'').join('');
 document.head.appendChild(st);
 const after={};for(const k in REP){const e=document.querySelector(REP[k]);after[k]=e?px(e):null}
 for(const k of [0,1,2]){const e=document.querySelector(P[k][0]);after['pseudo'+k]=e?parseFloat(getComputedStyle(e,P[k][1]).fontSize):null}
 const ratio={};for(const k in before)ratio[k]=before[k]&&after[k]?+(after[k]/before[k]).toFixed(3):null;
 window.__ENL={before,after,ratio};return els.length})()"""
# NEGATIVE CONTROL: the 118 placement (Resume left in row 2 beside AVCA; two references per line
# in content-sized tracks) must be caught
OLD_118 = r"""(()=>{const st=document.createElement('style');const K='.rk3:not(.hideref) tr.row td.c-ref';st.textContent=
 '.rk3:not(.hideref) tr.row td.rs{grid-row:2!important;grid-column:5!important;text-align:right!important;white-space:nowrap!important}'+
 K+':nth-child(14),'+K+':nth-child(15){grid-row:5!important}'+K+':nth-child(16),'+K+':nth-child(17){grid-row:6!important}'+
 K+':nth-child(18),'+K+':nth-child(19){grid-row:7!important}'+K+':nth-child(20),'+K+':nth-child(21){grid-row:8!important}'+
 K+':nth-child(even){grid-column:2/4!important}'+K+':nth-child(odd){grid-column:4/-1!important}'+
 K+'{white-space:nowrap!important}'+
 '.rk3 tr.row td.pps,.rk3 tr.row td.opps,.rk3 tr.row td.dpps,.rk3 tr.row td.hitp,.rk3 tr.row td.ohit,.rk3 tr.row td.dhit{white-space:nowrap!important;min-width:auto!important}';
 document.head.appendChild(st);return 1})()"""
CTLS = r"""(()=>{const els=[...document.querySelectorAll('nav .pri, nav .morebtn, #q, #conf, #top, #rksort, #rkcompare > summary')].filter(e=>e.offsetParent||e.tagName==='SUMMARY');
 const R=els.map(e=>[e.id||e.textContent.trim().slice(0,10),e.getBoundingClientRect()]);const bad=[];
 for(let i=0;i<R.length;i++)for(let j=i+1;j<R.length;j++){const a=R[i][1],b=R[j][1];if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)bad.push(R[i][0]+' x '+R[j][0])}
 const navclip=[...document.querySelectorAll('nav .pri, nav .morebtn')].filter(b=>b.scrollWidth>b.clientWidth+1).map(b=>b.textContent.trim());
 return {n:R.length,overlap:bad,navclip,right:Math.max(...R.map(x=>x[1].right)),w:innerWidth,d:document.documentElement.scrollWidth}})()"""


async def session(jobs):
    import websockets
    prof = tempfile.mkdtemp(prefix="sh118-")
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9381",
                          "--user-data-dir=" + prof, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = {}
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen("http://localhost:9381/json")); break
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
            async def ev(x):
                r = await call("Runtime.evaluate", {"expression": x, "returnByValue": True, "awaitPromise": True})
                return (r.get("result") or {}).get("value")
            async def key(k, code, kc):
                for t in ("keyDown", "keyUp"):
                    await call("Input.dispatchKeyEvent", {"type": t, "key": k, "code": code, "windowsVirtualKeyCode": kc})
            await call("Runtime.enable")
            for name, fn in jobs:
                errs.clear()
                out[name] = await fn(call, ev, key)
                out[name + ":errs"] = list(errs)
    finally:
        p.terminate(); shutil.rmtree(prof, ignore_errors=True)
    return out


def at(width, route, wait=8):
    async def go(call, ev, key):
        await call("Emulation.setDeviceMetricsOverride", {"width": width, "height": 844 if width < 600 else 1000,
                                                         "deviceScaleFactor": 2 if width < 600 else 1, "mobile": width < 600})
        # a FRESH document per job: a same-URL hash navigation does not reload, so test-only state
        # (enlarged fonts, toggled columns) would leak from one job into the next
        await call("Page.navigate", {"url": "about:blank"}); await asyncio.sleep(.3)
        await call("Page.navigate", {"url": BASE + "/START-HERE.html#/" + route}); await asyncio.sleep(wait)
    return go


def job_layout(width):
    async def fn(call, ev, key):
        await at(width, "rankings")(call, ev, key)
        return await ev("""(()=>{const r=document.querySelector('#rbody tr');return {w:innerWidth,d:document.documentElement.scrollWidth,
          hdr:document.querySelector('header').offsetHeight,row:r?Math.round(r.getBoundingClientRect().top+scrollY):-1,
          nav:Math.max(...[...document.querySelectorAll('nav .pri, nav .morebtn')].map(b=>b.getBoundingClientRect().right)),
          tape:getComputedStyle(document.getElementById('livetick')).display,
          clipped:[...document.querySelectorAll('#rbody td.tm')].filter(c=>c.offsetParent&&c.scrollWidth>c.clientWidth+1).length}})()""")
    return fn


def job_contrast(route, width):
    async def fn(call, ev, key):
        await at(width, route)(call, ev, key)
        return await ev(CONTRAST)
    return fn


async def job_interact(call, ev, key):
    r = {}
    await at(390, "rankings")(call, ev, key)
    # search
    r["search"] = await ev("""(async()=>{const q=document.getElementById('q');q.value='Kent';q.dispatchEvent(new Event('input',{bubbles:true}));
      await new Promise(s=>setTimeout(s,600));return [...document.querySelectorAll('#rbody tr')].filter(t=>t.offsetParent).map(t=>t.dataset.team||t.textContent.trim().slice(0,20)).slice(0,5)})()""")
    # team -> Back keeps the search
    r["back"] = await ev("""(async()=>{const row=[...document.querySelectorAll('#rbody tr')].find(t=>t.offsetParent);
      (row.querySelector('a,td.tm')||row).click();await new Promise(s=>setTimeout(s,1500));const there=location.hash;
      history.back();await new Promise(s=>setTimeout(s,1500));return {there,back:location.hash,q:document.getElementById('q').value}})()""")
    await ev("(()=>{const q=document.getElementById('q');q.value='';q.dispatchEvent(new Event('input',{bubbles:true}))})()")
    # Compare round trip
    r["compare"] = await ev("""(async()=>{const d=document.getElementById('rkcompare');d.open=true;
      const b=[...d.querySelectorAll('.rulerbar .segb')].find(x=>x.dataset.r==='avca');b.click();await new Promise(s=>setTimeout(s,800));
      const lab=document.getElementById('rkcmpv').textContent, pv=!document.getElementById('pollview').hidden;
      [...d.querySelectorAll('.rulerbar .segb')].find(x=>x.dataset.r==='ours').click();await new Promise(s=>setTimeout(s,800));
      return {lab,pv,back:document.getElementById('rkcmpv').textContent,table:!!document.querySelector('#rankpanel:not([hidden]) #rbody tr')}})()""")
    # phone: the hidden reference columns are reachable through Compare -> Compare sources
    r["refcols"] = await ev("""(async()=>{const c=document.getElementById('refcols');const before=[...document.querySelectorAll('#rbody tr:first-child td.c-ref')].filter(t=>t.offsetParent).length;
      c.click();await new Promise(s=>setTimeout(s,600));const after=[...document.querySelectorAll('#rbody tr:first-child td.c-ref')].filter(t=>t.offsetParent).map(t=>t.textContent.trim());
      c.click();document.getElementById('rkcompare').open=false;return {before,after}})()""")
    # Details survives the live re-render
    r["details"] = await ev("""(async()=>{const d=document.querySelector('#csstatus details.cs-det');if(!d)return null;d.open=true;
      for(let i=0;i<75;i++){await new Promise(s=>setTimeout(s,1000));}const d2=document.querySelector('#csstatus details.cs-det');
      return {same:d===d2,open:!!(d2&&d2.open),txt:(d2&&d2.textContent||'').slice(0,160)}})()""")
    # reload keeps the route
    await call("Page.reload"); await asyncio.sleep(8)
    r["reload"] = await ev("location.hash+' '+document.body.dataset.view")
    # keyboard: Tab until a nav button holds focus, then read its ring
    await ev("document.activeElement&&document.activeElement.blur();window.scrollTo(0,0)")
    ring = None
    for _ in range(14):
        await key("Tab", "Tab", 9)
        ring = await ev("""(()=>{const a=document.activeElement;if(!a||!a.closest('nav,#rkcmp'))return null;const cs=getComputedStyle(a);
          return {el:a.textContent.trim().slice(0,12),outline:cs.outlineStyle+' '+cs.outlineWidth}})()""")
        if ring:
            break
    r["focus"] = ring
    # larger text: the 390 phone at 150% text = a 260-CSS-px layout
    await call("Emulation.setDeviceMetricsOverride", {"width": 260, "height": 563, "deviceScaleFactor": 3, "mobile": True})
    await call("Page.navigate", {"url": BASE + "/START-HERE.html#/rankings"}); await asyncio.sleep(8)
    r["big"] = await ev("({w:innerWidth,d:document.documentElement.scrollWidth,nav:Math.max(...[...document.querySelectorAll('nav .pri, nav .morebtn')].map(b=>b.getBoundingClientRect().right))})")
    return r


try:
    urllib.request.urlopen(BASE + "/START-HERE.html", timeout=5); served = True
except Exception:
    served = False
ONLY = os.environ.get("SHELL118_ONLY")
if served and os.path.exists(CHROME) and ONLY == "enlarge":
    def _geom_job(width, enlarge):
        async def fn(call, ev, key):
            await at(width, "rankings")(call, ev, key)
            await ev(SOURCES_ON)
            if enlarge:
                await ev(ENLARGE); await asyncio.sleep(.8)
            g = await ev(GEOM)
            if enlarge:
                g["ctl"] = await ev(CTLS); g["enl"] = await ev("window.__ENL")
            return g
        return fn
    R = asyncio.run(session([("geo390", _geom_job(390, False)), ("geo390big", _geom_job(390, True))]))
    g = R["geo390"]
    check(g["n_overlap"] == 0 and not g["zero"] and not g["clip"] and g["d"] <= g["w"],
          "390 normal state, sources on: no overlap/zero/clip, no overflow (%d cells)" % g["cells"])
    gb = R["geo390big"]; E = gb.get("enl") or {}; good = {k: v for k, v in (E.get("ratio") or {}).items() if v is not None}
    check(len(good) >= 9 and all(1.45 <= v <= 1.55 for v in good.values()),
          "ENLARGED TEXT is a uniform 1.5x (measured after/before): %s; before px %s" % (good, E.get("before")))
    check(gb["n_overlap"] == 0 and not gb["zero"] and not gb["clip"] and gb["d"] <= gb["w"],
          "390 ENLARGED 1.5x, sources on: no overlap/zero/clip, no overflow %s" % (gb["overlap"] + gb["zero"] + gb["clip"])[:4])
    c = gb["ctl"]
    check(not c["overlap"] and not c["navclip"] and c["right"] <= c["w"] + 1 and c["d"] <= c["w"],
          "390 ENLARGED 1.5x: nav and Rankings controls do not overlap/clip, no overflow %s" % c)
    print("SHELL-118 (enlarge only) " + ("PASSED" if ok else "FAILED")); sys.exit(0 if ok else 1)
if served and os.path.exists(CHROME):
    jobs = [("lay%d" % w, job_layout(w)) for w in (360, 390, 430, 1440)]
    jobs += [("c:%s:%d" % (rt, w), job_contrast(rt, w)) for rt, w in
             (("rankings", 1440), ("rankings", 360), ("scores", 1440), ("scores", 390), ("teams/nebraska", 390),
              ("stats", 1440), ("bracket", 1440), ("bracket/cutline", 1440), ("standings", 1440), ("ballot", 1440))]
    jobs += [("interact", job_interact)]
    def job_geom(width, enlarge=False, control=False):
        async def fn(call, ev, key):
            await at(width, "rankings")(call, ev, key)
            await ev(SOURCES_ON)
            if enlarge:
                await ev(ENLARGE); await asyncio.sleep(.8)
            if control:
                await ev(OLD_118); await asyncio.sleep(.5)
            g = await ev(GEOM)
            if enlarge:
                g["ctl"] = await ev(CTLS)
                g["enl"] = await ev("window.__ENL")
            return g
        return fn
    jobs += [("geo%d" % w, job_geom(w)) for w in (360, 390, 430)]
    jobs += [("geo390big", job_geom(390, enlarge=True)), ("geo390neg", job_geom(390, control=True))]


    async def job_cmp_desk(call, ev, key):
        await at(1440, "rankings")(call, ev, key)
        return await ev("""(async()=>{const c=document.getElementById('refcols');if(c.checked)c.click();
          document.getElementById('rkcompare').open=true;await new Promise(s=>setTimeout(s,400));
          const b=document.querySelector('#rkcompare .rkcmpb').getBoundingClientRect();
          const d=document.documentElement.scrollWidth;
          const wide=d>innerWidth?[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&e.offsetParent)
            .slice(0,4).map(e=>e.tagName+'.'+(typeof e.className==='string'?e.className:'')+'#'+e.id+' '+Math.round(e.getBoundingClientRect().right)):[];
          return {l:Math.round(b.left),r:Math.round(b.right),w:innerWidth,d,wide,src:document.getElementById('refcols').checked}})()""")
    jobs += [("cmpdesk", job_cmp_desk)]

    async def job_src_desk(call, ev, key):
        await at(1440, "rankings")(call, ev, key)
        return await ev("""(async()=>{const c=document.getElementById('refcols');if(!c.checked)c.click();await new Promise(s=>setTimeout(s,500));
          const sc=document.querySelector('#rankpanel .rkscroll');const r={w:innerWidth,d:document.documentElement.scrollWidth,
          inner:[sc.scrollWidth,sc.clientWidth,getComputedStyle(sc).overflowX]};c.click();return r})()""")
    jobs += [("srcdesk", job_src_desk)]
    R = asyncio.run(session(jobs))
    for w in (360, 390, 430, 1440):
        L = R["lay%d" % w]
        check(L["w"] == w and L["d"] <= w and L["nav"] <= w + 1 and not L["clipped"] and L["tape"] == "none",
              "%d: true viewport, no page overflow, nav fits, no clipped names, no ticker off Scores %s" % (w, L))
        check(L["row"] < (520 if w < 600 else 360) and L["hdr"] <= (130 if w < 600 else 60),
              "%d: the first ranked team is near the top (row at %spx; header %spx; before: 711 phone / 842 desktop)" % (w, L["row"], L["hdr"]))
        check(not R["lay%d:errs" % w], "%d: no script errors %s" % (w, R["lay%d:errs" % w][:2]))
    for k in [k for k in R if k.startswith("c:") and not k.endswith(":errs")]:
        c = R[k] or {}
        check(c.get("count") == 0 and c.get("measured", 0) > 20,
              "%s: rendered contrast >= 4.5:1 (3:1 only for >=24px, or >=18.67px bold) on %s measured text elements + %s pseudo labels; "
              "NOT measured: %s %s" % (k[2:], c.get("measured"), c.get("pseudo_measured"), c.get("skipped"), (c.get("groups") or [])[:2]))

    for w in (360, 390, 430):
        g = R["geo%d" % w]
        check(g["rows"] >= 3 and g["n_overlap"] == 0 and not g["zero"] and not g["clip"] and g["d"] <= g["w"],
              "%d, Compare sources ON: no overlapping cells, no zero-width or clipped values, no page overflow "
              "(%d cells in %d cards; Resume at %s, AVCA at %s) %s" % (w, g["cells"], g["rows"], g["rs"], g["avca"],
                                                                      (g["overlap"] + g["zero"] + g["clip"])[:3]))
    gb = R["geo390big"]
    check(gb["n_overlap"] == 0 and not gb["zero"] and not gb["clip"] and gb["d"] <= gb["w"],
          "390 with ENLARGED TEXT (every rendered font x1.5, card labels 16px), sources on: no overlap/zero/clip, no overflow %s"
          % (gb["overlap"] + gb["zero"] + gb["clip"])[:3])
    E = gb.get("enl") or {}
    rat = E.get("ratio") or {}
    good = {k: v for k, v in rat.items() if v is not None}
    check(len(good) >= 9 and all(1.45 <= v <= 1.55 for v in good.values()),
          "ENLARGED TEXT is a uniform 1.5x, measured after/before on inherited, fixed-px and pseudo labels "
          "(status, nav, card value/name/POWER, search, 3 card label pseudos): %s; before px %s"
          % (good, E.get("before")))
    c = gb["ctl"]
    check(not c["overlap"] and not c["navclip"] and c["right"] <= c["w"] + 1 and c["d"] <= c["w"],
          "390 with ENLARGED TEXT: navigation and Rankings controls do not overlap or clip, page does not overflow %s" % c)
    gn = R["geo390neg"]
    check(gn["n_overlap"] > 0 or gn["zero"],
          "NEGATIVE CONTROL: the 118 placement (Resume beside AVCA, two per line) IS caught (%d overlaps, zero-width %s)"
          % (gn["n_overlap"], gn["zero"][:2]))
    D = R["srcdesk"]
    check(D["d"] <= D["w"] and D["inner"][2] == "auto",
          "1440 with Compare sources ON: the wide table scrolls inside its own box, the page does not overflow %s" % D)
    C = R["cmpdesk"]
    check(C["l"] >= 0 and C["r"] <= C["w"] and C["d"] <= C["w"],
          "1440: the open Compare panel stays inside the viewport, no page overflow %s" % C)
    I = R["interact"]
    check(I["search"] and all("Kent" in x for x in I["search"]), "search filters the rows %s" % I["search"])
    check("/teams/" in I["back"]["there"] and I["back"]["back"].startswith("#/rankings") and I["back"]["q"] == "Kent",
          "team -> Back returns to Rankings with the search kept %s" % I["back"])
    check(I["compare"]["pv"] and "AVCA" in I["compare"]["lab"] and I["compare"]["back"] == "" and I["compare"]["table"],
          "Compare -> AVCA shows that view and NAMES it; back to POWER restores the table %s" % I["compare"])
    check(I["refcols"]["before"] == 0 and len(I["refcols"]["after"]) >= 5,
          "phone: the reference columns are hidden by default and reachable via Compare -> Compare sources %s" % I["refcols"])
    check(I["details"] and I["details"]["open"], "header Details stays open through a 75 s live re-render %s" % I["details"])
    check(I["reload"].startswith("#/rankings") and I["reload"].endswith("rankings"), "reload keeps the route (%s)" % I["reload"])
    check(I["focus"] and "solid" in I["focus"]["outline"], "keyboard Tab reaches the nav with a visible focus ring %s" % I["focus"])
    check(I["big"]["d"] <= I["big"]["w"] and I["big"]["nav"] <= I["big"]["w"] + 1,
          "REFLOW stress (a 260 CSS px viewport -- narrower layout, NOT enlarged text): no page overflow, nav fits %s" % I["big"])
else:
    print("SKIP live checks: the served page or Chrome is unavailable")
print("SHELL-118 CHECKS " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
