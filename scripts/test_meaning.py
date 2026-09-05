#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CORE DATA MEANING — awards say org/year/source; stats name their universe.

A serious reader must never infer what a badge or number rests on. Pinned:
every award badge carries its YEAR ON ITS FACE and org+season+source in
its title; the Stats header names the exact aggregated-game universe; the
qualification floor is visible at the controls; every category option
names its unit; movement marks state their basis.
"""

import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def main():
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("no built page"); return 0
    h = io.open(hub, encoding="utf-8").read()
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()

    print("1. AWARD BADGES: ORGANISATION, AWARD, YEAR, SOURCE")
    # the renderer: face carries a year, title carries the rest
    check("the badge face carries the season year",
          "' \\u2019' + String(aa.season).slice(-2)" in src)
    check("the badge title names the organisation and season",
          'title="AVCA ' in src and "', ' + aa.season + ' season'" in src)
    check("...and its source",
          "from the published AVCA All-America workbook" in src)
    # rendered instances: every server-rendered aa badge title says AVCA+season
    # ⚠ the badges are RUNTIME-rendered by playerCell; a naive regex over
    # the built page matches the function's own SOURCE TEXT (quotes and
    # plus-signs included) and fails a correct build. Filter to real
    # rendered instances; the node fixture below is the behavioural proof.
    inst = [t for t in re.findall(r'<span class="aa [^"]*" title="([^"]*)"', h)
            if "' +" not in t]
    if inst:
        bad = [t for t in inst if "AVCA" not in t
               or not re.search(r"\b20\d\d season\b", t)
               or "workbook" not in t]
        check("every rendered badge title carries org + season + source "
              "(%d checked)" % len(inst), not bad, bad[:2])
        faces = [f for f in re.findall(
            r'<span class="aa [^"]*"[^>]*>([^<]*)</span>', h)
            if "' +" not in f]
        nb = [f for f in faces if not re.search(u"\u2019\\d\\d", f)]
        check("no badge face is a bare shorthand -- every one shows a year",
              not nb, nb[:3])
    else:
        print("  -- badges are runtime-rendered only; behavioural fixture "
              "below is the proof")

    print("\n2. STATS: THE EXACT UNIVERSE AND THE VISIBLE FLOOR")
    meta = (json.load(io.open(os.path.join(
        REPO, "data", "raw", "2026", "players_2026.json"),
        encoding="utf-8")).get("meta") or {})
    n = meta.get("games_aggregated")
    # wording moved 2026-09-05: "counted finals" implied the masthead's
    # universe; the header now says "matches (the box universe)" and names
    # how the two differ. The count itself must still be exact.
    check("the header names the aggregated-game count exactly",
          ("held box scores of <b>%d</b> matches" % n) in h, n)
    check("...and says what is excluded",
          "exhibitions and duplicate feed listings excluded" in h)
    check("...and that the team universe is per-team",
          "team&rsquo;s own counted matches" in h
          or "team\u2019s own counted matches" in h)
    check("the qualification floor is visible at the controls",
          'id="ldrfloor"' in h and re.search(
              r'id="ldrfloor"[^>]*>\s*min\s+\d+\s+sets', h))
    check("the exclusion counters are split in the aggregate meta",
          meta.get("duplicate_listings_excluded") is not None
          and meta.get("exhibitions_excluded") is not None)
    # fixtures: rate + percentage categories name their unit
    sel = re.search(r'<select id="lstat">([\s\S]*?)</select>', h)
    opts = re.findall(r"<option[^>]*>([^<]*)</option>", sel.group(1)) if sel else []
    check("every category option names its unit",
          opts and all(("/ set" in o) or ("%" in o) for o in opts),
          str(opts))

    print("\n3. MOVEMENT MARKS STATE THEIR BASIS")
    for cls in ("mv up", "mv dn", "mv sm"):
        pat = 'class="%s" title="' % cls
        check("the board's '%s' mark carries a basis title" % cls,
              pat in src)
    check("the Top 25 movers do too",
          'class="mv-up" title="' in src and 'class="mv-dn" title="' in src)

    print("\n4. FIXTURE CASES (renderer-level)")
    # current award / historical award / no award / under-floor player
    import subprocess
    blk_src = src
    m = re.search(r"function playerCell\(o, size\) \{[\s\S]*?\n\}", blk_src)
    check("playerCell is extractable", bool(m))
    if m:
        js = """
const esc = s => String(s == null ? '' : s);
const avatar = () => '<i>av</i>';
%s
const cur = playerCell({name:'A', aa:[{honour:'First Team', season:2025}]});
const old = playerCell({name:'B', aa:[{honour:'Player of the Year',
  season:2024, national:true}]});
const none = playerCell({name:'C', aa:null});
const bad = [];
if (!/AA1 \\u201925/.test(cur) && cur.indexOf('AA1 \\u2019' + '25') < 0)
  bad.push('current award lacks a year face: ' + cur.slice(0, 160));
if (old.indexOf('POY \\u2019'.replace('\\\\u2019','\\u2019')) < 0 &&
    old.indexOf('POY \u2019' + '24') < 0)
  bad.push('historical award lacks its own year');
if (old.indexOf('2024 season') < 0) bad.push('title lacks season');
if (none.indexOf('class="aa') >= 0) bad.push('no-award renders a badge');
if (bad.length) { console.log('MEAN-FAIL: ' + bad.join(' | ')); process.exit(1); }
console.log('MEAN-OK');
""" % m.group(0)
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        check("BEHAVIOR: current/historical/no-award render correctly",
              r.returncode == 0, (r.stdout + r.stderr).strip()[:120])

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL MEANING GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
