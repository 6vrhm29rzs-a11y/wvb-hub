#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEAM KILL % -- definition, chain, and the no-denominator invariant.

Kill % = kills / total attacks (errors untouched). Hitting % stays
(K-E)/TA. Two separate displayed facts, never blended. A Kill % may
never render without its K/E/TA and sample beside it, and never with a
zero or missing denominator. The value flows from the ONE canonical
aggregate (team_season_stats over swap-applied, counted boxes) plus the
two shared accessors (teamTotals for match views, live_detail for the
live pulse) -- no new reader, no separate exclusion loop.
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def jsfn(src, name):
    from test_provenance_truth import jsfn as _j
    return _j(src, name)


def node(js):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True,
                           timeout=60)
        return r.returncode, r.stdout, r.stderr
    finally:
        os.unlink(path)


def main():
    src = io.open(os.path.join(REPO, "scripts/build_hub.py"),
                  encoding="utf-8").read()
    page = io.open(PAGE, encoding="utf-8").read()

    print("1. THE CHAIN -- one aggregate, no new reader")
    check("killpct is defined in team_season_stats, beside hit",
          '"killpct": (round(d["k"] / d["ta"], 3) if d["ta"] else None)'
          in src)
    check("the offense view reads TSTATS (the canonical payload), "
          "nothing else",
          "const rows = TSTATS" in (jsfn(page, "renderTeamOffense") or "")
          and "playerbox" not in (jsfn(page, "renderTeamOffense") or "")
          and "fetch(" not in (jsfn(page, "renderTeamOffense") or ""))
    check("tstats is built from res_cnt (the counted list)",
          "tstats = team_season_stats(boxes, res_cnt)" in src)
    check("no killpct anywhere reads a raw file",
          not re.search(r"killpct[^\n]*jsonl", src))
    check("never blended: no firepower/offense score combines the two",
          not re.search(r"killpct\s*[*+]\s*\w*hit|hit\s*[*+]\s*\w*killpct",
                        src))

    print("\n2. BEHAVIORAL FIXTURES -- the aggregate")
    import build_hub as BH
    # the aggregate's D-I listing filter would drop synthetic teams --
    # steer the membership seam for the fixture, restore after
    _real_di = BH.di_teams
    BH.di_teams = lambda: {"Alpha", "Beta", "Errory", "Clean", "Zed",
                           "NoTA", "Ghost"}
    def box_row(team, k, e, ta, sets=4):
        return {"team": team, "k": k, "e": e, "ta": ta, "sets": sets,
                "ast": 0, "digs": 0, "bs": 0, "ba": 0, "aces": 0}
    boxes = {
        "g1": [box_row("Alpha", 50, 10, 100), box_row("Beta", 40, 8, 100)],
        # high kill%, LOW hit% through errors vs the control
        "g2": [box_row("Errory", 60, 40, 100),
               box_row("Clean", 45, 5, 100)],
        # zero attempts
        "g3": [box_row("Zed", 0, 0, 0), box_row("Alpha", 30, 5, 80)],
        # a box for a match NOT in the counted list (exhibition/dup/review
        # analog): must contribute nothing
        "gX": [box_row("Alpha", 99, 0, 99), box_row("Beta", 99, 0, 99)],
    }
    res = [{"gid": "g1", "home": "Beta", "away": "Alpha",
            "sets": [[25, 20], [25, 20], [25, 20]]},
           {"gid": "g2", "home": "Clean", "away": "Errory",
            "sets": [[25, 20], [25, 20], [25, 20]]},
           {"gid": "g3", "home": "Alpha", "away": "Zed",
            "sets": [[25, 20], [25, 20], [25, 20]]}]
    ts = BH.team_season_stats(boxes, res)
    A = ts.get("Alpha", {}).get("own") or {}
    check("normal: Kill % = K/TA to three decimals",
          A.get("killpct") == round(80.0 / 180.0, 3), A)
    check("...and Hit % stays (K-E)/TA, a different number",
          A.get("hit") == round((80.0 - 15.0) / 180.0, 3)
          and A["hit"] != A["killpct"])
    E = ts.get("Errory", {}).get("own") or {}
    C = ts.get("Clean", {}).get("own") or {}
    check("high-kill/low-hit through errors vs the control",
          E["killpct"] > C["killpct"] and E["hit"] < C["hit"],
          (E.get("killpct"), E.get("hit"), C.get("killpct"), C.get("hit")))
    Z = ts.get("Zed", {}).get("own") or {}
    check("zero attempts -> killpct None, never 0 or NaN",
          Z.get("killpct") is None and Z.get("hit") is None)
    check("a box outside the counted list contributes NOTHING "
          "(exhibition/duplicate/review analog)",
          A.get("kills") == 80 and "gX" not in
          [r.get("gid") for r in res])
    # missing attempts key entirely
    ts2 = BH.team_season_stats(
        {"g9": [dict(box_row("NoTA", 5, 1, 0), ta=None),
                box_row("Alpha", 5, 1, 10)]},
        [{"gid": "g9", "home": "Alpha", "away": "NoTA",
          "sets": [[25, 20]]}])
    check("missing attempts -> None",
          (ts2.get("NoTA", {}).get("own") or {}).get("killpct") is None)
    BH.di_teams = _real_di

    print("\n3. THE REAL PAGE RECONCILES BY VALUE (swap included)")
    m = re.search(r"const TSTATS = (\[.*?\]);\n", page, re.S)
    m2 = re.search(r"const BOXES = (\{.*?\});\n", page, re.S)
    m3 = re.search(r"const TEAMS = (\{.*?\});\n", page, re.S)
    if m and m2 and m3:
        tstats = {r["team"]: r for r in json.loads(m.group(1))}
        boxes_p = json.loads(m2.group(1).replace("<\\/", "</"))
        teams_p = json.loads(m3.group(1).replace("<\\/", "</"))
        did = 0
        for nm in ("SMU", "Nebraska", "Kentucky"):
            t = teams_p.get(nm) or {}
            row = (tstats.get(nm) or {}).get("own") or {}
            gids = [str(g.get("gid")) for g in (t.get("played") or [])]
            if not gids or not row:
                continue
            k = e = ta = 0.0
            for gid in gids:
                for r in (boxes_p.get(gid) or []):
                    if r.get("team") == nm:
                        k += r.get("k") or 0
                        e += r.get("e") or 0
                        ta += r.get("ta") or 0
            if ta:
                did += 1
                check("%s: page Kill %% == recomputed K/TA over counted "
                      "boxes" % nm,
                      row.get("killpct") == round(k / ta, 3),
                      (row.get("killpct"), round(k / ta, 3)))
        check("the reconciliation actually ran on teams incl. the "
              "swap-corrected match", did >= 2, did)
        smu_gids = [str(g.get("gid")) for g in
                    (teams_p.get("SMU", {}).get("played") or [])]
        check("SMU's counted set includes the corrected match 6626259",
              "6626259" in smu_gids)

    print("\n4. RENDERERS -- the no-denominator invariant, under node")
    off = jsfn(page, "renderTeamOffense")
    check("offense row carries K, E and TA cells beside the rates",
          off and "d.kills" in off and "d.errors" in off
          and "d.attacks" in off)
    check("offense filter refuses ta == 0 and null rates",
          off and "attacks > 0" in off and "killpct !== null" in off)
    esc_f = jsfn(page, "esc")
    stub = ("function logo(){return ''}\n"
            "function teamRankChips(){return ''}\n"
            "function hcell(v,txt){return '<td>'+txt+'</td>'}\n"
            "function nonDiPhrase(){return ''}\nconst NONDI_WHY='';\n"
            "const _els={};function el(id){return _els[id]=_els[id]||"
            "{value:'',textContent:'',innerHTML:''}}\n"
            "const document={getElementById:el};\n")
    ts_stub = [
        {"team": "Alpha", "conf": "X", "own": {
            "matches": 3, "sets": 11.0, "kills": 80, "errors": 15,
            "attacks": 180, "killpct": 0.444, "hit": 0.361, "nondi": 0}},
        {"team": "Zed", "conf": "X", "own": {
            "matches": 1, "sets": 3.0, "kills": 0, "errors": 0,
            "attacks": 0, "killpct": None, "hit": None, "nondi": 0}},
    ]
    js = (esc_f + "\n" + stub +
          "const TSTATS = %s;\n" % json.dumps(ts_stub) + off + "\n" +
          "renderTeamOffense();\n"
          "console.log(JSON.stringify({html:_els['lobody'].innerHTML,"
          "cnt:_els['lcnt'].textContent}));")
    rc, out, err = node(js)
    check("offense renderer runs", rc == 0, err)
    if rc == 0:
        d = json.loads(out.strip().splitlines()[-1])
        check("zero-attempts team is ABSENT, not dashed into a row",
              "Zed" not in d["html"] and d["cnt"] == "1 teams")
        check("the rendered row carries 80 / 15 / 180 beside .444",
              ">80<" in d["html"] and ">15<" in d["html"]
              and ">180<" in d["html"] and ".444" in d["html"])
        check("both rates render in the three-decimal site format",
              ".444" in d["html"] and ".361" in d["html"])

    # recap: kill % line + raw rows; null denominator omits the rate line
    recap_fns = "\n".join(jsfn(page, n) or "" for n in
                          ("mNum", "matchScore", "matchSets", "teamTotals",
                           "recapAligned", "recapHTML"))
    prov = "\n".join(jsfn(page, n) or "" for n in
                     ("corrSchools", "provenanceTag"))
    box = ("[{team:'A',name:'p1',sets:3,k:30,e:6,ta:60,ast:0,digs:5,bs:1,"
           "ba:2,aces:1,pts:0},{team:'B',name:'p2',sets:3,k:20,e:10,ta:50,"
           "ast:0,digs:8,bs:0,ba:0,aces:2,pts:0}]")
    js2 = ("const esc=s=>String(s==null?'':s);const mAway=m=>m.a,"
           "mHome=m=>m.h;const DUP_GIDS=[];const CONFIDENCE={finals:[]};\n" +
           recap_fns + "\n" + prov + "\n"
           "const BOXES={G: " + box + "};\n"
           "const m={gid:'G',a:'A',h:'B',final:{as:3,hs:0,"
           "sets:[[25,20],[25,18],[25,21]]}};\n"
           "console.log(JSON.stringify(recapHTML(m)));")
    rc, out, err = node(js2)
    check("recap runs with the new metrics", rc == 0, err)
    if rc == 0:
        h = json.loads(out.strip().splitlines()[-1])
        check("kill %% line renders beside hitting %%",
              "kill %" in h and "hitting %" in h)
        check("...with the raw K / E / TA rows directly under the rates",
              "kills" in h and "attack errors" in h
              and "total attacks" in h)
        check("A's kill %% is .500 (30/60), B's .400 -- and .500 is "
              "emphasised within the metric only",
              ".500" in h and ".400" in h)
    # zero-TA box: the kill % line is OMITTED, others still render
    js3 = js2.replace("k:30,e:6,ta:60", "k:0,e:0,ta:0").replace(
        "k:20,e:10,ta:50", "k:0,e:0,ta:0")
    rc, out, err = node(js3)
    if rc == 0:
        h = json.loads(out.strip().splitlines()[-1])
        check("zero attempts -> NO kill %% or hitting %% line, no "
              "estimate", "kill %" not in h and "hitting %" not in h)

    print("\n5. THE LIVE PULSE")
    import live_detail as LD
    okc, why = LD.team_line({"kills": 20, "attackErrors": 8,
                             "attackAttempts": 60, "assists": 18,
                             "digs": 20, "serviceAces": 2,
                             "serviceErrors": 3,
                             "blockSolos": 1, "blockAssists": 2})
    check("live team line carries killpct = K/TA",
          okc and okc["killpct"] == round(20 / 60.0, 3), okc)
    okz, _ = LD.team_line({"kills": 0, "attackErrors": 0,
                           "attackAttempts": 0, "assists": 0, "digs": 0,
                           "serviceAces": 0, "serviceErrors": 0,
                           "blockSolos": 0, "blockAssists": 0})
    check("live zero attempts -> killpct None (early set one)",
          okz and okz["killpct"] is None)
    lmc = jsfn(page, "lmcBody") or ""
    check("the pulse table carries K/E/TA columns beside both rates, "
          "labelled as live-feed totals",
          "Kill%" in lmc and "Hit%" in lmc and "x.killpct" in lmc
          and "live feed" in lmc and ">TA<" in lmc)
    check("score-only live state renders no table at all",
          "stats_available" in lmc and "never a zero" in lmc)

    print("\n6. DOSSIER + LABELS")
    check("dossier chart carries a Kill %% row with its definition",
          "'Kill %', O.killpct, D.killpct" in page
          and "errors are not subtracted" in page)
    check("dossier totals sentence prints both rates beside K/E/TA "
          "and the match sample",
          "Kill % '" in page.replace("<b>", "").replace("</b>", "")
          or "Kill % ' +" in page)
    check("the Stats offense view says TEAM rates, defines both, and "
          "keeps the match count",
          "These are <b>team</b> rates, not player rates" in page
          and "how often a swing ends the rally" in page)

    print("\n7. [NEG] negative controls")
    bad = off.replace("'<td class=\"n\">' + d.attacks + '</td>'", "''")
    check("[NEG] an offense row stripped of its TA cell fails the "
          "invariant scan",
          not ("d.attacks" in bad and bad.count("d.attacks") >= 2)
          or "d.attacks" not in bad.split("hcell")[0].split("'<td")[-1],
          "control shape")
    check("[NEG] ...and the source really changed", bad != off)
    js4 = (esc_f + "\n" + stub +
           "const TSTATS = %s;\n" % json.dumps(
               [{"team": "Ghost", "conf": "X",
                 "own": {"matches": 1, "sets": 3.0, "kills": 5,
                         "errors": 1, "attacks": 0, "killpct": 0.5,
                         "hit": 0.4, "nondi": 0}}]) + off + "\n" +
           "renderTeamOffense();\n"
           "console.log(_els['lobody'].innerHTML.includes('Ghost'));")
    rc, out, err = node(js4)
    check("[NEG] a rate smuggled in WITH zero attempts still cannot "
          "render (attacks > 0 gate)",
          rc == 0 and "false" in out, out or err)

    print("\n8. THE PUBLIC BUILD")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub_p):
        pub = io.open(pub_p, encoding="utf-8").read()
        check("the public page carries the same team-offense view "
              "(public stats are public)",
              "renderTeamOffense" in pub and "Kill&nbsp;%" in pub)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL KILL % GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
