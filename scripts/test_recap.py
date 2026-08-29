#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verified Match Recap guards (round 13).

The contract: every recap claim is a held fact wearing its source label, a
match without an aligned box says so instead of estimating, a duplicate
listing gets no recap at all, and no causal language ever rides on a
number. Behaviour is executed under node with fixtures -- the artifact
holding a field is not the same as the page saying it.

Run: python3 scripts/test_recap.py -- no network.
"""

import io
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from test_scoreboard_density import block as js_block  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)
    return ok


def main():
    print("VERIFIED MATCH RECAPS\n")
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()

    def fn(name):
        i = src.find("function %s(" % name)
        return js_block(src, i) if i >= 0 else None
    recap, aligned, totals = fn("recapHTML"), fn("recapAligned"), \
        fn("teamTotals")
    score, msets, mnum = fn("matchScore"), fn("matchSets"), fn("mNum")

    def run(recap_src, case):
        js = """
const esc = s => String(s == null ? '' : s);
const mAway = m => m.a, mHome = m => m.h;
const DUP_GIDS = ['DUPGID'];
%s
%s
%s
%s
%s
%s
const box = [
 {team:'Alpha', name:'P One', sets:4, k:18, e:3, ta:40, ast:1, digs:9,
  bs:1, ba:4, aces:2, pts:22},
 {team:'Alpha', name:'P Two', sets:4, k:3, e:1, ta:9, ast:49, digs:12,
  bs:0, ba:2, aces:1, pts:5},
 {team:'Beta', name:'Q One', sets:4, k:14, e:8, ta:44, ast:0, digs:22,
  bs:0, ba:2, aces:0, pts:15},
 {team:'Beta', name:'Q Two', sets:4, k:5, e:2, ta:15, ast:40, digs:8,
  bs:2, ba:0, aces:3, pts:9}];
const BOXES = { ALIGNED: box,
                MISALIGNED: box.map(r => Object.assign({}, r, {sets: 3})) };
const m = { ALIGNED: {gid:'ALIGNED', a:'Alpha', h:'Beta',
              final:{as:3, hs:1, sets:[[25,20],[23,25],[25,18],[25,21]]}},
            NOBOX: {gid:'NOBOX', a:'Alpha', h:'Beta',
              final:{as:3, hs:0, sets:[[25,20],[25,18],[25,21]]}},
            MISALIGNED: {gid:'MISALIGNED', a:'Alpha', h:'Beta',
              final:{as:3, hs:1, sets:[[25,20],[23,25],[25,18],[25,21]]}},
            DUP: {gid:'DUPGID', a:'Alpha', h:'Beta',
              final:{as:3, hs:1, sets:[[25,20],[23,25],[25,18],[25,21]]}} };
const html = recapHTML(m['%s']);
console.log(JSON.stringify(html));
""" % (mnum, score, msets, totals, aligned, recap_src, case)
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        if r.returncode != 0:
            return None, (r.stdout + r.stderr).strip()
        import json as _j
        return _j.loads(r.stdout.strip().splitlines()[-1]), ""

    print("1. A COMPLETE ALIGNED BOX RENDERS THE FULL RECAP")
    h, err = run(recap, "ALIGNED")
    check("the recap renders", bool(h), err[:120])
    if h:
        check("final and set line, labelled official scoreboard",
              "3\\u20131" in h.replace("\\\\u", "\\u") or "3–1" in h,
              h[:80])
        check("...the source tag is present", "official scoreboard" in h)
        check("both teams get a labelled edge",
              h.count("edge") >= 2 and "match-aligned box" in h)
        check("leaders are named with metric, value and sample",
              "P One" in h and "18 kills" in h and "4 sets" in h)
        check("digs leader crosses teams honestly",
              "Q One" in h and "22 digs" in h)
        check("What decided it carries two named values per metric",
              "What decided it" in h and re.search(
                  r"hit <b>\.\d{3}</b> to .*<b>\.\d{3}</b>", h))
        check("no causal language anywhere",
              not re.search(r"won because|dominat|collaps|clutch|cruis|"
                            r"outclass", h, re.I))

    print("\n2. NO ALIGNED BOX: A USEFUL FINAL, NOTHING INVENTED")
    h2, err2 = run(recap, "NOBOX")
    check("the module still renders the final", bool(h2) and "3\\u20130"
          in h2.replace("\\\\u", "\\u") or (h2 and "3–0" in h2), err2[:120])
    if h2:
        check("the explicit no-box state is stated",
              "Detailed box not available" in h2)
        # structural, not word-level: the no-box prose legitimately SAYS
        # "team edges and stat leaders are omitted"
        check("no team or player detail is invented",
              "rcedge" not in h2 and "rcldr" not in h2
              and "What decided it" not in h2)
    h3, _ = run(recap, "MISALIGNED")
    check("a box that disagrees with the match is treated as absent",
          h3 is not None and "Detailed box not available" in (h3 or ""))

    print("\n3. A DUPLICATE LISTING GETS NO RECAP")
    h4, _ = run(recap, "DUP")
    check("duplicate gid renders nothing (ledger-only)", h4 == "")

    print("\n4. NEGATIVE CONTROLS")
    # remove the provenance/state gate: recap renders detail off an
    # UNALIGNED box -- the aligned() call is bypassed
    bogus = recap.replace("const byTeam = recapAligned(gid, sets.length);",
                          "const byTeam = (function(){const o={};"
                          "(BOXES[gid]||[]).forEach(r=>(o[r.team]=o[r.team]"
                          "||[]).push(r));return Object.keys(o).length===2"
                          "?o:null;})();")
    h5, err5 = run(bogus, "MISALIGNED")
    check("[NEG] removing the alignment gate is caught (detail appears "
          "where the suite requires absence)",
          h5 is not None and "What decided it" in (h5 or ""), err5[:120])
    bogus2 = recap.replace(" <i class=\"rcsrctag\">match-aligned box</i>", "")
    bogus2 = bogus2.replace("'match-aligned box</span></div>'",
                            "'</span></div>'")
    bogus2 = bogus2.replace(" <i class=\"rcsrctag\">official scoreboard</i>", "")
    h6, _ = run(bogus2, "ALIGNED")
    check("[NEG] stripping the source tags is caught",
          h6 is not None and "match-aligned box" not in (h6 or "")
          and "official scoreboard" not in (h6 or ""))

    print("\n5. PLACEMENT AND REUSE")
    check("the recap renders on finals only, after Match facts",
          "(st === 'final' ? recapHTML(m) : '')" in src
          and src.find("Match facts") < src.find(
              "(st === 'final' ? recapHTML(m) : '')"))
    check("one grammar: exactly one recapHTML definition",
          src.count("function recapHTML(") == 1)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL RECAP GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
