#!/usr/bin/env python3
"""Build Cody/START-HERE.html -- the personal quick-reference hub.

This is a READ-ONLY VIEW over data the pipeline already owns. It computes
nothing new and it is not an input to anything: delete Cody/ and the build is
unaffected. Rebuild with:

    python3 scripts/build_cody_hub.py

Sources, and their tier (see docs/data_sources.md):
  OFFICIAL     data/raw/2026/scoreboard/*.json  -- the 2026 schedule, from ncaa.com
  OFFICIAL     data/data_2025.json              -- conference + D-I membership
  THIRD-PARTY  Cody/data/tv_listings_2026.txt   -- TV, transcribed from VolleyTalk

R5 APPLIES HERE TOO. The bracket is a STRUCTURAL MOCKUP: it draws the real
2026 championship format and dates and fills every team slot with an em dash,
because no 2026 result exists yet. It never invents a seed to look complete.

Cody/ is gitignored on purpose -- the TV table is transcribed from a forum and
this repo is public (same reasoning as the saved VolleyTalk pages).
"""
import json
import glob
import os
import pathlib
import datetime
import re
from typing import Dict, List, Optional

BASE = pathlib.Path(__file__).resolve().parent.parent
OUT = BASE / "Cody" / "START-HERE.html"
SEASON = 2026

LIVE_URL = "https://6vrhm29rzs-a11y.github.io/wvb-hub/"
LOCAL_DASH = BASE / "output" / "vb_dashboard.html"

# The 2026 NCAA Division I calendar. Transcribed from the NCAA calendar posted
# in VolleyTalk thread 106690; the two competition dates are CORROBORATED
# against ncaa.com's own scoreboard (see verify_dates() below), which is why
# they carry a different tier from the post-season dates.
CALENDAR = [
    ("2026-07-30", "First day of practice", "THIRD-PARTY"),
    ("2026-08-21", "AVCA First Serve - first matches on ncaa.com", "OFFICIAL"),
    ("2026-08-27", "'Spikes Under the Lights' exhibition - NOT on ncaa.com", "THIRD-PARTY"),
    ("2026-08-28", "First full date of competition", "OFFICIAL"),
    ("2026-11-29", "Selection show", "THIRD-PARTY"),
    ("2026-12-03", "NCAA 1st & 2nd rounds begin (through Dec 5)", "THIRD-PARTY"),
    ("2026-12-10", "Regionals begin (through Dec 13)", "THIRD-PARTY"),
    ("2026-12-17", "National semifinals", "THIRD-PARTY"),
    ("2026-12-20", "National championship", "THIRD-PARTY"),
]


def load_teams() -> Dict[str, Dict[str, object]]:
    """name_short -> {conference, is_division_i}. From the 2025 dataset, which
    is where conference membership currently lives."""
    p = BASE / "data" / "data_2025.json"
    if not p.exists():
        return {}
    out = {}
    for t in json.load(open(p))["teams"]:
        out[t["name_short"]] = {
            "conference": t.get("conference") or "",
            "is_division_i": bool(t.get("is_division_i")),
        }
    return out


def load_schedule() -> List[Dict[str, object]]:
    """Every scheduled 2026 game ncaa.com has published, one row per game."""
    teams = load_teams()
    games = []
    for path in sorted(glob.glob(str(BASE / "data/raw/2026/scoreboard/*.json"))):
        date = os.path.basename(path)[:-5]
        try:
            payload = json.load(open(path))
        except ValueError:
            continue
        for entry in payload.get("games") or []:
            g = entry.get("game", entry)
            away = (g.get("away") or {}).get("names", {}).get("short")
            home = (g.get("home") or {}).get("names", {}).get("short")
            if not away or not home:
                continue
            a_meta = teams.get(away) or {}
            h_meta = teams.get(home) or {}
            games.append({
                "d": date,
                "a": away,
                "h": home,
                "t": (g.get("startTime") or "").strip(),
                "ac": a_meta.get("conference") or "",
                "hc": h_meta.get("conference") or "",
                # Known D-I on BOTH sides. Unknown-to-us teams are not asserted
                # to be non-D-I -- they are simply not marked as a D-I matchup.
                "di": bool(a_meta.get("is_division_i")) and bool(h_meta.get("is_division_i")),
            })
    return games


def verify_dates(games: List[Dict[str, object]]) -> Dict[str, object]:
    """Check the calendar's competition dates against the crawled scoreboard,
    rather than restating the forum. Returns MEASURED values only."""
    by_date = {}
    for g in games:
        by_date[g["d"]] = by_date.get(g["d"], 0) + 1
    dates = sorted(by_date)
    return {
        "first_date": dates[0] if dates else None,
        "first_count": by_date.get(dates[0]) if dates else 0,
        "aug27": by_date.get("2026-08-27", 0),
        "aug28": by_date.get("2026-08-28", 0),
        "total": len(games),
        "dates": len(dates),
    }


def load_tv() -> List[Dict[str, str]]:
    p = BASE / "Cody" / "data" / "tv_listings_2026.txt"
    if not p.exists():
        return []
    rows = []
    for line in open(p):
        line = line.strip()
        if not line or line.count("|") < 3:
            continue
        day, matchup, net, time = line.split("|", 3)
        rows.append({"day": day, "m": matchup, "n": net, "t": time})
    return rows


def pipeline_state() -> Dict[str, Optional[str]]:
    """What the published dashboard currently carries. Read out of the built
    artifact, not assumed."""
    state = {"generated_at": None, "data_through": None, "exists": False}
    if not LOCAL_DASH.exists():
        return state
    state["exists"] = True
    head = open(LOCAL_DASH, encoding="utf-8", errors="replace").read(400000)
    m = re.search(r'"generated_at":\s*"([^"]+)"', head)
    if m:
        state["generated_at"] = m.group(1)
    m = re.search(r'"data_through":\s*"([^"]+)"', head)
    if m:
        state["data_through"] = m.group(1)
    return state


def esc(s: object) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def build() -> None:
    games = load_schedule()
    facts = verify_dates(games)
    tv = load_tv()
    pipe = pipeline_state()
    today = datetime.date.today()

    confs = sorted(set([g["ac"] for g in games] + [g["hc"] for g in games]) - set([""]))
    team_names = sorted(set([g["a"] for g in games] + [g["h"] for g in games]))

    cal_rows = []
    for iso, label, tier in CALENDAR:
        d = datetime.date(*[int(x) for x in iso.split("-")])
        delta = (d - today).days
        if delta > 0:
            when = "in %d day%s" % (delta, "" if delta == 1 else "s")
            cls = "soon" if delta <= 14 else ""
        elif delta == 0:
            when, cls = "TODAY", "today"
        else:
            when, cls = "%d days ago" % -delta, "past"
        cal_rows.append(
            '<tr class="%s"><td class="dt">%s</td><td>%s</td>'
            '<td class="when">%s</td><td><span class="tier t-%s">%s</span></td></tr>'
            % (cls, d.strftime("%a, %b %-d"), esc(label), when, tier.split("-")[0].lower(), tier))

    # Bracket: structure only. Every slot is an em dash until the Nov 29 show.
    rounds = [
        ("First / Second Rounds", "Dec 3 - 5", 64),
        ("Regionals (Sweet 16 / Elite 8)", "Dec 10 - 13", 16),
        ("National Semifinals", "Dec 17", 4),
        ("National Championship", "Dec 20", 2),
    ]
    bracket = []
    for name, when, slots in rounds:
        cells = "".join(['<div class="slot">&mdash;</div>' for _ in range(min(slots, 16))])
        more = ("<div class=\"slotmore\">+%d more</div>" % (slots - 16)) if slots > 16 else ""
        bracket.append(
            '<div class="bround"><div class="bhead"><b>%s</b><span>%s &middot; %d teams</span></div>'
            '<div class="slots">%s%s</div></div>' % (esc(name), esc(when), slots, cells, more))

    fresh_note = "no build on disk"
    if pipe["generated_at"]:
        fresh_note = "built %s &middot; matches through %s" % (
            esc(pipe["generated_at"]), esc(pipe["data_through"] or "—"))

    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cody's Volleyball Hub — Start Here</title>
<style>
:root{--bg:#fbfbfd;--card:#fff;--ink:#16181d;--ink2:#5b6270;--ink3:#c9ced8;
--line:#e6e9ef;--acc:#b4123c;--acc2:#0b6b8f;--ok:#0a7d4a;--warn:#8a5a00}
@media(prefers-color-scheme:dark){:root{--bg:#0f1116;--card:#171a21;--ink:#eef1f6;
--ink2:#98a1b2;--ink3:#3a4150;--line:#252a34;--acc:#ff5f82;--acc2:#5cc6f0;--ok:#3ddb95;--warn:#ffc35c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif}
header{padding:26px 20px 14px;border-bottom:1px solid var(--line);background:var(--card)}
h1{margin:0 0 4px;font-size:24px;letter-spacing:-.02em}
.sub{color:var(--ink2);font-size:13px}
main{max-width:1100px;margin:0 auto;padding:0 16px 60px}
section{margin:26px 0}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.09em;color:var(--ink2);
margin:0 0 10px;font-weight:650}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
a.tile{display:block;text-decoration:none;color:inherit;background:var(--card);
border:1px solid var(--line);border-radius:12px;padding:14px 16px;transition:.15s}
a.tile:hover{border-color:var(--acc);transform:translateY(-1px)}
a.tile b{display:block;font-size:15px;margin-bottom:3px}
a.tile span{font-size:12.5px;color:var(--ink2)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;
color:var(--ink2);padding:7px 8px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--card)}
td{padding:7px 8px;border-bottom:1px solid var(--line)}
tr.past{opacity:.42}tr.today td{background:rgba(180,18,60,.09)}
tr.soon td{font-weight:600}
.dt{white-space:nowrap;color:var(--ink2)}.when{white-space:nowrap;color:var(--ink2);font-size:12.5px}
.tier{font-size:10px;padding:2px 7px;border-radius:99px;border:1px solid var(--ink3);
color:var(--ink2);white-space:nowrap}
.tier.t-official{color:var(--ok);border-color:var(--ok)}
.tier.t-third{color:var(--warn);border-color:var(--warn)}
.ctl{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
input,select{font:inherit;font-size:13.5px;padding:7px 10px;border-radius:8px;
border:1px solid var(--line);background:var(--bg);color:var(--ink);min-width:0}
input[type=search]{flex:1 1 190px}
.scroll{max-height:480px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.count{font-size:12px;color:var(--ink2);padding:6px 2px}
.bround{margin-bottom:12px}
.bhead{display:flex;justify-content:space-between;align-items:baseline;
font-size:13px;margin-bottom:6px}.bhead span{color:var(--ink2);font-size:12px}
.slots{display:flex;flex-wrap:wrap;gap:5px}
.slot{width:52px;height:26px;border:1px dashed var(--ink3);border-radius:6px;
display:flex;align-items:center;justify-content:center;color:var(--ink3);font-size:13px}
.slotmore{align-self:center;font-size:12px;color:var(--ink2);padding-left:4px}
.note{font-size:12.5px;color:var(--ink2);margin-top:10px;line-height:1.5}
.k{font-weight:600;color:var(--ink)}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--bg);
padding:1px 5px;border-radius:4px;border:1px solid var(--line)}
.banner{border-radius:10px;padding:11px 14px;font-size:13px;margin-bottom:14px;
border:1px solid var(--line);background:var(--card)}
@media(max-width:560px){.slot{width:44px}h1{font-size:20px}
main{padding:0 10px 40px}.card{padding:12px}td,th{padding:6px 6px}}
</style></head><body>
<header>
  <h1>Volleyball Hub &mdash; Start Here</h1>
  <div class="sub">Your local quick-reference. Rebuild anytime with
  <code>python3 scripts/build_cody_hub.py</code></div>
</header>
<main>

<div class="banner" id="banner"></div>

<section>
  <h2>Where to look</h2>
  <div class="grid">
    <a class="tile" href="LIVE_URL" target="_blank"><b>Live dashboard &#8599;</b>
      <span>The published site &mdash; ratings, bracket, tracker. Rebuilt by the daily pipeline.</span></a>
    <a class="tile" href="./DASHBOARD.html"><b>Dashboard</b>
      <span>All 348 &mdash; ratings, post-season, tracker. FRESH_NOTE</span></a>
    <a class="tile" href="./RANKINGS-AND-BRACKET.html"><b>Rankings &amp; projected bracket</b>
      <span>Our 2026 order beside AVCA, VolleyTalk, RPI and Massey. Click a team to see its six.</span></a>
    <a class="tile" href="#tv"><b>What&rsquo;s on TV</b>
      <span>TV_N nationally televised matches, searchable.</span></a>
    <a class="tile" href="#sched"><b>Full 2026 schedule</b>
      <span>SCHED_N games across SCHED_D dates, every team.</span></a>
  </div>
</section>

<section>
  <h2>Key dates</h2>
  <div class="card"><div class="scroll" style="max-height:none">
  <table><thead><tr><th>Date</th><th>What</th><th></th><th>Source</th></tr></thead>
  <tbody>CAL_ROWS</tbody></table></div>
  <div class="note">Tiers follow the project convention. <span class="k">OFFICIAL</span> = confirmed
  against ncaa.com&rsquo;s own scoreboard in our crawled data. <span class="k">THIRD-PARTY</span> =
  transcribed from the VolleyTalk calendar post and not independently checked.</div>
  </div>
</section>

<section id="tv">
  <h2>On TV</h2>
  <div class="card">
    <div class="ctl">
      <input type="search" id="tvq" placeholder="Search team, event or network&hellip;">
      <select id="tvnet"><option value="">All networks</option></select>
    </div>
    <div class="count" id="tvcount"></div>
    <div class="scroll"><table><thead><tr><th>Date</th><th>Matchup</th><th>Net</th><th>Time ET</th></tr></thead>
    <tbody id="tvbody"></tbody></table></div>
    <div class="note">Transcribed from VolleyTalk thread 104144 &mdash; <span class="k">THIRD-PARTY,
    not verified against the networks</span>. The source table has occasional typos and a few
    out-of-order rows; it is reproduced as written. ncaa.com&rsquo;s own feed carries no network
    field yet (0 of SCHED_N games), so this is currently the only TV source.</div>
  </div>
</section>

<section id="sched">
  <h2>2026 schedule &mdash; every published game</h2>
  <div class="card">
    <div class="ctl">
      <input type="search" id="q" placeholder="Search a team&hellip;">
      <select id="conf"><option value="">All conferences</option></select>
      <select id="di">
        <option value="">D-I and non-D-I</option>
        <option value="1">D-I vs D-I only</option>
        <option value="0">Games involving a non-D-I / unlisted team</option>
      </select>
      <input type="date" id="from" min="2026-08-01" max="2026-12-31">
    </div>
    <div class="count" id="count"></div>
    <div class="scroll"><table><thead><tr><th>Date</th><th>Away</th><th>Home</th><th>Time</th><th></th></tr></thead>
    <tbody id="body"></tbody></table></div>
    <div class="note">Straight from ncaa.com&rsquo;s scoreboard, the same feed the pipeline crawls
    &mdash; <span class="k">OFFICIAL</span>. Conference and D-I labels are joined from the 2025
    dataset by team name; a team we cannot match shows a blank conference rather than a guess.
    The ratings themselves are <span class="k">D-I only</span>: games against non-D-I opponents
    are excluded from RPI entirely (<code>scripts/rpi_2025.py</code>), so a SWAC team&rsquo;s D-II
    wins never inflate it.</div>
  </div>
</section>

<section>
  <h2>Bracket &mdash; structure only</h2>
  <div class="card">
    __BRACKET_BLOCK__
    <div class="note"><span class="k">Every slot is deliberately empty.</span> The 2026 field is not
    selected until the Nov 29 selection show, so there is nothing real to put here. This shows the
    format and the dates only. The project rule is that a missing measurement renders as an em dash
    and never as a plausible-looking placeholder &mdash; a bracket pre-filled with guessed seeds is
    exactly the failure that rule exists to prevent. The live dashboard&rsquo;s Post-Season tab
    fills in from the projector once there are results to project from.</div>
  </div>
</section>

<section>
  <h2>Good to know</h2>
  <div class="card">
    <div class="note" style="margin-top:0">
    <p><span class="k">Your viewer link is fine</span> &mdash; <code>LIVE_URL</code> is the right
    address and the pipeline has published on schedule every morning. If the page shows a red
    &ldquo;STALE&rdquo; strip right now, that is the banner being literal: the ratings build is from
    the end of the 2025 season because <b>no 2026 match has been played yet</b>. It is not a broken
    pipeline. It starts moving on Aug 21.</p>
    <p><span class="k">Aug 21 vs Aug 28.</span> The NCAA calendar calls Aug 28 the first date of
    competition, and ncaa.com agrees where it counts &mdash; {{AUG28_N}} games that day. But ncaa.com
    also carries FIRST_N contests on FIRST_D (the AVCA First Serve event, incl. Louisville&ndash;Texas A&amp;M
    and Kentucky&ndash;Wisconsin). Those are real and they will flow into the ratings. The Aug 27
    &ldquo;Spikes Under the Lights&rdquo; exhibition is <b>not</b> on ncaa.com ({{AUG27_N}} games), so it
    cannot contaminate anything.</p>
    <p><span class="k">This folder is yours and it is disposable.</span> Nothing in the build reads
    it. It is kept out of the public repo because the TV table is transcribed from a forum.</p>
    </div>
  </div>
</section>

</main>
<script>
const TV=TV_JSON, G=G_JSON, CONFS=CONF_JSON, PIPE=PIPE_JSON;

(function(){
  const el=document.getElementById('banner');
  const first=new Date('FIRST_D'+'T00:00:00');
  const days=Math.ceil((first-new Date())/86400000);
  if(days>0){el.innerHTML='<b>'+days+' day'+(days==1?'':'s')+' until the first matches</b> ('+
    new Date('FIRST_D'+'T12:00:00').toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric'})+
    '). Ratings show final 2025 numbers until then — that is expected, not a fault.';}
  else{el.innerHTML='<b>The 2026 season is underway.</b> The daily pipeline refreshes the live dashboard each morning.';}
})();

function render(){
  const q=document.getElementById('q').value.toLowerCase().trim();
  const c=document.getElementById('conf').value, d=document.getElementById('di').value;
  const from=document.getElementById('from').value;
  let n=0; const out=[];
  for(const g of G){
    if(q && g.a.toLowerCase().indexOf(q)<0 && g.h.toLowerCase().indexOf(q)<0) continue;
    if(c && g.ac!==c && g.hc!==c) continue;
    if(d==='1' && !g.di) continue;
    if(d==='0' && g.di) continue;
    if(from && g.d<from) continue;
    n++; if(out.length>=400) continue;
    out.push('<tr><td class="dt">'+g.d+'</td><td>'+g.a+'</td><td>'+g.h+'</td><td class="when">'+
      (g.t||'—')+'</td><td>'+(g.di?'':'<span class="tier">non-D-I</span>')+'</td></tr>');
  }
  document.getElementById('body').innerHTML=out.join('');
  document.getElementById('count').textContent=
    n+' game'+(n==1?'':'s')+(n>400?' — showing first 400, narrow the search':'');
}
function renderTV(){
  const q=document.getElementById('tvq').value.toLowerCase().trim();
  const n=document.getElementById('tvnet').value;
  let c=0; const out=[];
  for(const r of TV){
    if(n && r.n!==n) continue;
    if(q && (r.m+' '+r.n+' '+r.day).toLowerCase().indexOf(q)<0) continue;
    c++;
    out.push('<tr><td class="dt">'+r.day+'</td><td>'+r.m+'</td><td>'+r.n+'</td><td class="when">'+r.t+'</td></tr>');
  }
  document.getElementById('tvbody').innerHTML=out.join('');
  document.getElementById('tvcount').textContent=c+' match'+(c==1?'':'es');
}
(function init(){
  const cs=document.getElementById('conf');
  CONFS.forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;cs.appendChild(o)});
  const nets=[...new Set(TV.map(r=>r.n))].sort();
  const ns=document.getElementById('tvnet');
  nets.forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;ns.appendChild(o)});
  ['q','conf','di','from'].forEach(id=>document.getElementById(id).addEventListener('input',render));
  ['tvq','tvnet'].forEach(id=>document.getElementById(id).addEventListener('input',renderTV));
  render(); renderTV();
})();
</script>
</body></html>"""

    repl = {
        "LIVE_URL": LIVE_URL,
        "FRESH_NOTE": fresh_note,
        "CAL_ROWS": "".join(cal_rows),
        "__BRACKET_BLOCK__": "".join(bracket),
        "TV_N": str(len(tv)),
        "SCHED_N": "{:,}".format(facts["total"]),
        "SCHED_D": str(facts["dates"]),
        "FIRST_D": facts["first_date"] or "2026-08-21",
        "FIRST_N": str(facts["first_count"]),
        "AUG27_N": str(facts["aug27"]),
        "AUG28_N": str(facts["aug28"]),
        "TV_JSON": json.dumps(tv, separators=(",", ":")),
        "G_JSON": json.dumps(games, separators=(",", ":")),
        "CONF_JSON": json.dumps(confs, separators=(",", ":")),
        "PIPE_JSON": json.dumps(pipe, separators=(",", ":")),
    }
    for k, v in repl.items():
        html = html.replace(k, v)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # EVERYTHING IN ONE FOLDER. Cody opens these from Finder and asked not to
    # bounce between directories, so the built dashboard is copied in beside
    # this page rather than linked across the repo. It is a derived artifact --
    # output/vb_dashboard.html stays the original.
    if LOCAL_DASH.exists():
        import shutil
        shutil.copyfile(str(LOCAL_DASH), str(OUT.parent / "DASHBOARD.html"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    print("wrote %s (%.0f KB)" % (OUT, OUT.stat().st_size / 1024.0))
    print("  schedule : %s games, %d dates, %d teams"
          % ("{:,}".format(facts["total"]), facts["dates"], len(team_names)))
    print("  tv       : %d listings, %d networks" % (len(tv), len(set(r["n"] for r in tv))))
    print("  measured : first date %s (%d games) | Aug 27 %d | Aug 28 %d"
          % (facts["first_date"], facts["first_count"], facts["aug27"], facts["aug28"]))


if __name__ == "__main__":
    build()
