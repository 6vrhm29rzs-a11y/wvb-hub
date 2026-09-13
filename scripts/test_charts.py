#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the chart toolkit and the team-page visuals (2026-09-13).

Cody: "I want to SEE more, not read more." The audit that prompted the work
found 19 views, 16 tables and ZERO data graphics -- the 362 <svg> already on
the page were crests, icons and avatars.

What these guards hold shut:
  * a missing measurement draws NOTHING and prints an em dash. A zero-length
    bar and "we do not have this" look identical on screen, which is R5
    exactly, and a chart is the easiest place in the codebase to violate it.
  * the diverging pair stays the MEASURED one. Green/red is the classic
    colour-vision trap and our own good/bad tokens prove it (dE 3.8 under
    protanopia); the shipped pair scores 22.5. W/L pills keep green/red
    because they also carry the letter -- a bar carries no letter.
  * a percentile knows which direction is good. Serve errors and everything
    in the ALLOWED column are better LOW, and a renderer that guesses from a
    key name is R4 with a new face.
  * a face is a photograph or initials, never a drawn likeness and never an
    empty frame.

Behaviour is executed under node with fixtures; the artifact holding a field
is not the same as the page drawing it. Run: python3 scripts/test_charts.py
"""

import io
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
# ⚠ THE MODULE'S OWN HELPER, READ RATHER THAN ASSUMED. block() takes an
# INDEX; fn() takes a NAME. Guessing which cost a crashed suite here,
# and that is the fifth time in this codebase that a test module's
# conventions were assumed instead of read.
from test_scoreboard_density import fn as js_block  # noqa: E402

PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
SRC = os.path.join(REPO, "scripts", "build_hub.py")
FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)


def _strip_js_comments(src):
    """JS source minus /* */ and // comments.

    ⚠ Needed because this guard kept matching the COMMENT that documents
    the bug it checks for -- the tenth time in this codebase that a check has
    matched the prose describing it. Stripping comments is strictly stronger
    than rewording the comment: the rule stays written down AND enforced.
    """
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if src.startswith("//", i):
            j = src.find(chr(10), i)
            i = n if j < 0 else j
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def node(js):
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    if r.returncode != 0:
        return None, (r.stdout + r.stderr).strip()
    return r.stdout.strip().splitlines()[-1], ""


def main():
    page = io.open(PAGE, encoding="utf-8").read()
    src = io.open(SRC, encoding="utf-8").read()
    esc = "function esc(s){return String(s==null?'':s).replace(/[&<>\"']/g," \
          "c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'," \
          "\"'\":'&#39;'}[c]));}"
    bars = js_block(page, "cxBars")
    diff = js_block(page, "cxDiff")
    line = js_block(page, "cxLine")
    head = js_block(page, "cxHead")
    labv = js_block(page, "cxLabVars")

    print("1. THE TOOLKIT IS ON THE PAGE, ONCE EACH")
    for fn in ("cxBars", "cxDiff", "cxLine", "cxHead", "cxLabVars"):
        check("%s is defined exactly once" % fn,
              len(re.findall(r"^function %s\(" % fn, page, re.M)) == 1,
              len(re.findall(r"^function %s\(" % fn, page, re.M)))
    check("the charts are actually used on the team page",
          "tdProfile(" in page and "tdMargin(" in page and "tdSquad(" in page)

    print("\n2. A MISSING MEASUREMENT IS NOT A ZERO (R5)")
    js = esc + bars + head + labv + """
const rows=[{label:'Known',value:5,pct:0.5,text:'5.00'},
            {label:'Absent',value:null,text:null}];
console.log(JSON.stringify(cxBars(rows,{})));"""
    out, err = node(js)
    check("cxBars runs", bool(out), err[:130])
    if out:
        html = json.loads(out)
        # ⚠ THE LABEL APPEARS TWICE PER ROW -- once in the row's title, once
        # in the visible label -- so splitting on it and taking [1] reads the
        # gap BETWEEN them and finds neither the fill nor the dash. Anchor on
        # the row boundary instead. (This guard was wrong before the code was:
        # it failed working output, which is the trap this file documents.)
        rows_html = html.split('<div class="cxrow"')
        known = rows_html[1]
        absent = rows_html[2]
        check("the known value draws a fill", 'cxfill' in known)
        check("[NEG] the absent value draws NO fill at all",
              'cxfill' not in absent, absent[:120])
        check("...and prints an em dash rather than a number",
              "—" in absent)

    print("\n3. POLARITY USES THE MEASURED PAIR, NOT GREEN/RED")
    check("the cool/warm tokens are declared",
          "--cx-cool:#2563C9" in src and "--cx-warm:#C2553F" in src)
    css = src[src.find("CHART TOOLKIT"):src.find("CHART TOOLKIT") + 4000]
    check("[NEG] no bar fill is painted with the good/bad token pair",
          "--good" not in css and "--bad" not in css, "green/red in chart CSS")
    check("the file records WHY (the measured dE), so it is not undone",
          "protanopia" in css)
    js = esc + diff + head + labv + """
console.log(JSON.stringify(cxDiff([{label:'up',value:4,text:'+4'},
                                   {label:'down',value:-2,text:'-2'}],{})));"""
    out, err = node(js)
    check("cxDiff runs", bool(out), err[:130])
    if out:
        html = json.loads(out)
        check("a positive value uses the cool side", 'cxbar pos' in html)
        check("a negative value uses the warm side", 'cxbar neg' in html)
        check("both sit against a zero rule", html.count('cxzero') == 2)
        # the scale is the largest magnitude, so the biggest bar is the widest
        widths = [float(w) for w in re.findall(r'cxbar (?:pos|neg)" style="width:([0-9.]+)%', html)]
        check("the larger magnitude draws the longer bar",
              len(widths) == 2 and widths[0] > widths[1], widths)

    print("\n4. THE TREND SCALES UNIFORMLY")
    js = esc + line + head + """
console.log(JSON.stringify(cxLine([{x:'W1',y:3},{x:'W2',y:1},{x:'W3',y:2}],
  {title:'rank', invert:true})));"""
    out, err = node(js)
    check("cxLine runs", bool(out), err[:130])
    if out:
        html = json.loads(out)
        check("[NEG] it never stretches the geometry",
              'preserveAspectRatio="none"' not in html,
              "non-uniform scaling renders dots as ellipses")
        check("a one-point series draws nothing rather than a dot on a line",
              json.loads(node(esc + line + head +
                              "console.log(JSON.stringify(cxLine([{x:'a',y:1}],{})))")[0]) == "")

    print("\n5. PERCENTILE DIRECTION IS DECLARED, NOT GUESSED")
    os.environ.setdefault("WVB_SEASON", "2026")
    import build_hub as B
    ts = {}
    for i in range(10):
        ts["T%d" % i] = {
            "own_di": {"matches": 5, "hit": 0.100 + i * 0.02,
                       "svc_err_rate": 0.05 + i * 0.01},
            "opp_di": {"matches": 5, "hit": 0.100 + i * 0.02,
                       "svc_err_rate": 0.05 + i * 0.01},
        }
    prof = B.team_profiles(ts)
    check("every sampled team gets a profile", len(prof) == 10, len(prof))
    best_hit = prof["T9"]["hit"]["p"]
    worst_hit = prof["T0"]["hit"]["p"]
    check("a HIGH-is-good metric ranks the highest value top",
          best_hit > worst_hit and best_hit > 90, (worst_hit, best_hit))
    hi_err = prof["T9"]["svc_err_rate"]["p"]
    lo_err = prof["T0"]["svc_err_rate"]["p"]
    check("[NEG] a LOW-is-good metric inverts (most serve errors ranks worst)",
          lo_err > hi_err and hi_err < 10, (lo_err, hi_err))
    # what a team ALLOWS is good when it is low, so it inverts against its own
    # pool's direction -- the opposite of the same key on the own_di side
    allow_best = prof["T0"]["hit"]["ap"]
    allow_worst = prof["T9"]["hit"]["ap"]
    check("...and ALLOWED hitting inverts too (conceding least ranks top)",
          allow_best > allow_worst and allow_best > 90,
          (allow_best, allow_worst))
    thin = {"X": {"own_di": {"matches": 1, "hit": 0.4},
                  "opp_di": {"matches": 1, "hit": 0.1}}}
    check("[NEG] a team under the sample floor gets NO profile",
          B.team_profiles(thin) == {}, "a percentile from one match is theatre")
    check("the floor is stated in the payload contract",
          B.PROFILE_MIN_MATCHES >= 3)

    print("\n6. A FACE IS A PHOTOGRAPH OR INITIALS")
    squad = js_block(page, "tdSquad")
    init = js_block(page, "tdInitials")
    # ⚠ tdSquad gained real dependencies when the participation radar
    # landed (the OUTBOX map and the page's identity fold). Stubbed here
    # rather than guarded away in the page: on the real page a missing
    # OUTBOX should fail loudly, not silently stop marking absences.
    js = esc + init + squad + """
const OUTBOX={};
function nkeyJS(s){return String(s||'').replace(/[^A-Za-z]/g,'').toLowerCase();}
function dshort(){return 'a date';}
const t={roster:[{n:'Ada One',p:'S',num:2,ph:'https://x.test/a.jpg',l26:{sets:9}},
                 {n:'Bea Two',p:'OH',num:7,l26:{sets:3}},
                 {n:'Cal Three',p:'MB',num:9},
                 {n:'Dee Four',p:'L',num:1}]};
console.log(JSON.stringify(tdSquad(t,'Test')));"""
    out, err = node(js)
    check("tdSquad runs", bool(out), err[:130])
    if out:
        html = json.loads(out)
        check("a player WITH a photo renders an image", '<img class="sqf"' in html)
        check("...with an initials fallback if it 404s",
              'data-i="AO"' in html and 'sqi' in html)
        check("a player WITHOUT one renders her initials",
              '<span class="sqi">BT</span>' in html, html[:150])
        check("[NEG] no drawn likeness is reachable from the squad wall",
              'avatar(' not in squad,
              "a drawn face beside real photographs is a different claim")
        check("[NEG] and no empty frame is emitted",
              '<span class="sqi"></span>' not in html)
        check("every card routes to its player", html.count('data-player=') == 4)
        check("coverage is stated rather than implied",
              '1 of 4' in html, html[-260:])

    print("\n7. DOTS, WHERE A BAR WOULD LIE EITHER WAY")
    # ⚠ THE LEADERBOARD IS THE CASE. The top twelve at points per set sit
    # between 4.98 and 6.50: a zero-based bar draws twelve near-identical
    # bars and says nothing, and a truncated bar exaggerates a small spread
    # into a large one. A dot encodes POSITION, which a truncated axis does
    # not distort -- so the axis is truncated deliberately and printed.
    dots = js_block(page, "cxDots")
    js2 = esc + dots + head + labv + """
const rows=[{label:'A',value:5.48,text:'5.48'},{label:'B',value:5.02,text:'5.02'},
            {label:'C',value:4.98,text:'4.98'}];
console.log(JSON.stringify(cxDots(rows,{fmt:v=>v.toFixed(2)})));"""
    out, err = node(js2)
    check("cxDots runs", bool(out), err[:130])
    if out:
        h2 = json.loads(out)
        check("each value is a positioned dot, not a length",
              h2.count('cxdot') == 3 and 'cxfill' not in h2)
        check("the BEST value is marked as the leader",
              h2.count('cxdot lead') == 1)
        check("both ends of the truncated axis are PRINTED",
              'cxax' in h2 and '4.9' in h2 and '5.5' in h2, h2[-300:])
        lefts = [float(x) for x in re.findall(r'cxdot[^"]*" style="left:([0-9.]+)%', h2)]
        check("a higher value sits further right",
              len(lefts) == 3 and lefts[0] > lefts[1] > lefts[2], lefts)
        one, _ = node(esc + dots + head + labv +
                      "console.log(JSON.stringify(cxDots([{label:'x',value:1}],{})))")
        check("[NEG] a single point draws no axis at all",
              json.loads(one) == "", "one dot on an invented axis is theatre")

    print("\n8. THE CHART FOLLOWS THE TABLE IN EVERY STATS MODE")
    # Stats has three modes and ONE chart host. A mode that does not feed it
    # leaves a picture of a different query standing above the rows -- which
    # really happened: renderTeamOffense referenced a `side` variable it does
    # not define, threw inside a click listener (silent), and the chart kept
    # the previous mode's content.
    for fname in ("renderLeaders", "renderTeamStats", "renderTeamOffense"):
        body = js_block(page, fname)
        check("%s feeds the chart" % fname, "renderLeaderChart(" in body,
              "mode renders a table with no matching picture")
    off = _strip_js_comments(js_block(page, "renderTeamOffense"))
    check("[NEG] ...and renderTeamOffense uses its own rows, not a `side` "
          "it never defines", "r[side]" not in off,
          "an undefined variable throws silently inside a listener")

    print("\n9. THE PAGE ACTUALLY DRAWS THEM")
    check("the built team payload carries percentile profiles",
          '"pctl":' in page)
    n_cx = page.count('class="cx ')
    check("charts render into the built page", n_cx >= 1, n_cx)

    print("\n%s" % ("ALL CHART GUARDS PASS" if not FAILS else
                    "FAILED: %d\n   - %s" % (len(FAILS), "\n   - ".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
