#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Duplicate-listing guards (round 11).

The rule these protect: NOTHING is ever deduplicated by heuristic. The
detector only creates audit candidates; a listing stops counting only when
the append-only ledger holds authoritative evidence (both schools' official
schedules), and then it stops counting EVERYWHERE while staying inspectable.

Run: python3 scripts/test_dupes.py -- no network.
"""

import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import confidence as C  # noqa: E402
from dupes import duplicate_gids  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)
    return ok


def G(gid, a, h, winner, setline, ep, placeholder=False, venue="V",
      has_box=True):
    return {"gid": gid, "a": a, "h": h, "winner": winner,
            "setline": setline, "ep": ep, "placeholder": placeholder,
            "venue": venue, "has_box": has_box}


def main():
    print("DUPLICATE LISTINGS\n")
    print("1. THE DETECTOR CREATES CANDIDATES, NEVER REMOVALS")
    line = ((25, 23), (29, 27), (21, 25), (23, 25), (15, 12))
    # the confirmed shape: identical everything + asymmetry
    c1 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 1000, placeholder=True, venue=None,
          has_box=False),
        G("2", "A", "B", "9", line, 1000 + 14 * 3600)])
    check("identical pair with asymmetry -> ONE pending candidate",
          len(c1) == 1 and "verification pending" in c1[0]["status"])
    # a real two-match series: same teams, same winner, DIFFERENT set line
    c2 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 1000),
        G("2", "A", "B", "9", ((25, 20), (25, 22), (25, 18)),
          1000 + 20 * 3600, placeholder=True)])
    check("a real repeat meeting (different line) is NEVER flagged",
          not c2)
    # identical line but no quality asymmetry: also only silence
    c3 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 1000),
        G("2", "A", "B", "9", line, 1000 + 3600)])
    check("identical line WITHOUT asymmetry is not flagged either", not c3)
    # outside the window
    c4 = C.duplicate_candidates([
        G("1", "A", "B", "9", line, 0, placeholder=True),
        G("2", "A", "B", "9", line, 40 * 3600)])
    check("a 40-hour gap is outside the review window", not c4)

    print("\n2. ONLY THE LEDGER STOPS A COUNT, AND THEN EVERYWHERE")
    led = duplicate_gids(SEASON)
    check("the ledger holds the two verified entries",
          led.get("6640357") == "6625089" and led.get("6640332") == "6624350")
    data = json.load(open(os.path.join(REPO, "data",
                                       "data_%d.json" % SEASON)))
    marked = dict((str(g["game_id"]), g.get("duplicate_of"))
                  for g in data["games"])
    check("the dataset MARKS the duplicates (raw preserved, inspectable)",
          marked.get("6640357") == "6625089"
          and marked.get("6640332") == "6624350")
    check("...and the canonical gids are not marked",
          not marked.get("6625089") and not marked.get("6624350"))
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(hub):
        h = io.open(hub, encoding="utf-8").read()
        T = json.loads(re.search(r"const TEAMS\s*=\s*(.*?);\s*\n", h,
                                 re.S).group(1))
        for team, gid in (("UMES", "6640357"), ("Mississippi Val.", "6640357"),
                          ("Boise St.", "6640332"),
                          ("Middle Tenn.", "6640332")):
            gids = [p.get("gid") for p in (T.get(team) or {}).get("played")
                    or []]
            check("%s: duplicate out, canonical in" % team,
                  gid not in gids and led[gid] in gids,
                  "dup in list" if gid in gids else "canonical missing")
        # ⚠ MEETING COUNTS, NOT PINNED RECORDS. The first fix pinned the
        # school-verified records (1-1, 1-0) -- and UMES then PLAYED AGAIN
        # the same afternoon, so a correct 2-1 failed a guard about
        # duplicates. The duplicate invariant is that each ledgered pair
        # counts ONCE: exactly one UMES-MVSU meeting and one played
        # Boise-MT Aug-28 meeting in the played lists (the real Aug-29
        # rematch has its own gid and may add more meetings legitimately).
        def _meetings(team, opp):
            return [p for p in (T.get(team) or {}).get("played") or []
                    if p.get("opp") == opp]
        check("UMES counts exactly one MVSU meeting",
              len(_meetings("UMES", "Mississippi Val.")) == 1,
              str([p.get("gid") for p in _meetings("UMES",
                                                   "Mississippi Val.")]))
        _bmt = _meetings("Middle Tenn.", "Boise St.")
        check("Middle Tenn. counts the Aug-28 Boise meeting once "
              "(rematch, own gid, may add another)",
              sum(1 for p in _bmt if p.get("gid") == "6624350") == 1
              and not any(p.get("gid") == "6640332" for p in _bmt),
              str([p.get("gid") for p in _bmt]))
    lab = json.load(open(os.path.join(REPO, "data",
                                      "conference_lab_%d.json" % SEASON)))
    in_matrix = set()
    for cell in lab["matrix"].values():
        for g in cell["games"]:
            in_matrix.add(str(g["gid"]))
    check("Conference Lab counts neither duplicate",
          "6640357" not in in_matrix and "6640332" not in in_matrix)
    check("...but still counts the canonical matches",
          "6625089" in in_matrix and "6624350" in in_matrix)

    print("\n3. THE DUPLICATE STAYS VISIBLE, WITH THE REASON")
    rc = json.load(open(os.path.join(REPO, "data",
                                     "result_confidence_%d.json" % SEASON)))
    dups = dict((r["gid"], r["duplicate_of"]) for r in rc["finals"]
                if r.get("duplicate_of"))
    # ⚠ WAS AN EXACT-DICT PIN and broke the night a THIRD legitimate
    # duplicate was ledgered (Bradley-WIU, 2026-09-05). The invariant:
    # every ledgered duplicate appears in the Result Ledger with its
    # canonical, and the two founding pairs are still among them.
    _ledger = json.load(open(os.path.join(
        REPO, "data", "raw", "2026", "duplicate_listings.json")))
    # two field spellings coexist in the ledger's history
    _led = dict((g, v.get("canonical_gid") or v.get("duplicate_of"))
                for g, v in (_ledger.get("duplicates") or {}).items())
    # the page marks every ledgered duplicate THAT WENT FINAL; a ledgered
    # placeholder that never resolved has no row to mark. Everything the
    # page marks must be ledgered, and the founding pairs stay present.
    _final_gids = set(r["gid"] for r in rc["finals"])
    check("every FINAL ledgered duplicate is marked, and nothing unledgered is",
          dups == dict((g, c) for g, c in _led.items()
                       if g in _final_gids)
          and {"6640357": "6625089",
               "6640332": "6624350"}.items() <= dups.items())
    check("no pending candidate remains (both were verified, not assumed)",
          rc["meta"]["counts"]["duplicate_candidates_pending"] == 0)
    check("the evidence names BOTH schools' official schedules per pair",
          all(len(v["evidence"]) >= 2 and
              all(e["kind"] == "school_site" for e in v["evidence"])
              for v in json.load(open(os.path.join(
                  REPO, "data", "raw", str(SEASON),
                  "duplicate_listings.json")))["duplicates"].values()))

    print("\n4. EMPTY FINALS: VISIBLE FOR AUDIT, COUNTED NOWHERE")
    empty = [r for r in rc["finals"] if r["gid"] == "6625090"]
    check("6625090 is visible in the Result Ledger", len(empty) == 1)
    if os.path.exists(hub):
        gids_all = set()
        for team in ("Mississippi Val.", "Delaware St."):
            for p in (T.get(team) or {}).get("played") or []:
                gids_all.add(p.get("gid"))
        check("...and appears in no team's played list",
              "6625090" not in gids_all)

    print("\n5. THE LEDGER UI RENDERS THE DUPLICATE STATE (behavioural)")
    # node executes the page's own renderConfidence + rcDrill against
    # fixtures -- an artifact field that never reaches the DOM is invisible,
    # which is exactly what round 12 reopened this for.
    import subprocess
    from test_scoreboard_density import block as _js_block
    src2 = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                   encoding="utf-8").read()

    def _fn(name):
        i = src2.find("function %s(" % name)
        return _js_block(src2, i) if i >= 0 else None
    rc_render, rc_drill = _fn("renderConfidence"), _fn("rcDrill")

    def run_ui(render_src, drill_src):
        js = """
const esc = s => String(s == null ? '' : s);
const matchRoute = (gid, d) => '#/match-desk/' + gid;
const RC_LABEL = { official: 'Official', reconciled: 'Reconciled',
  confirmed: 'Confirmed', disputed: 'Under review' };
let RC_FILTER = 'all';
const CONFIDENCE = { meta: { counts: { finals: 2 } }, finals: [
  { gid: 'DUP', a: 'A', h: 'B', d: '2026-08-28', overall: 'reconciled',
    duplicate_of: 'CANON', dup_reason: 'one meeting only, per both schools',
    dup_asym: 'placeholder start on the duplicate',
    dup_evidence: [
      { school: 'A University', url: 'https://a.example/schedule',
        text: 'exactly one meeting listed', retrieved: '2026-08-29' },
      { school: 'B University', url: 'https://b.example/schedule',
        text: 'W, 3-0 -- the only entry', retrieved: '2026-08-29' }],
    states: {}, n_indep: 0, n_attempted: 0, sources: [] },
  { gid: 'CANON', a: 'A', h: 'B', d: '2026-08-28', overall: 'reconciled',
    duplicate_of: null, states: {}, n_indep: 0, n_attempted: 0,
    sources: [] }]};
const els = {};
const mk = id => els[id] = { id, innerHTML: '', hidden: false,
  scrollIntoView: () => {} };
['rcsummary','rclist','rcdrill'].forEach(mk);
global.document = { getElementById: id => els[id] || null };
%s
%s
renderConfidence();
const list = els['rclist'].innerHTML;
const bad = [];
if (!/DUPLICATE LISTING \\u00b7 DOES NOT COUNT|DUPLICATE LISTING \u00b7 DOES NOT COUNT/.test(list)
    && list.indexOf('DUPLICATE LISTING') < 0)
  bad.push('duplicate row does not render the duplicate state');
const canonRow = (list.match(/<button[^>]*data-rcgid="CANON"[\\s\\S]*?<\\/button>/) || [''])[0];
if (!canonRow) bad.push('canonical row not rendered');
if (canonRow.indexOf('DUPLICATE LISTING') >= 0)
  bad.push('the canonical row is wrongly labelled duplicate');
rcDrill('DUP');
const drill = els['rcdrill'].innerHTML;
if (drill.indexOf('does not') < 0 || drill.indexOf('count') < 0)
  bad.push('drill lacks the plain-English exclusion');
if (drill.indexOf('#/match-desk/CANON') < 0)
  bad.push('drill lacks a real route to the canonical match');
if (drill.indexOf('one meeting only, per both schools') < 0)
  bad.push('drill lacks the readable reason');
if (drill.indexOf('exactly one meeting listed') < 0
    || drill.indexOf('W, 3-0') < 0)
  bad.push('drill lacks the school citations');
if (drill.indexOf('2026-08-29') < 0)
  bad.push('drill lacks retrieval dates');
rcDrill('CANON');
if (els['rcdrill'].innerHTML.indexOf('Duplicate feed listing') >= 0)
  bad.push('a normal final renders the duplicate block');
if (bad.length) { console.log('UI-FAIL: ' + bad.join(' | ')); process.exit(1); }
console.log('UI-OK'); process.exit(0);
""" % (render_src, drill_src)
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    okui, why = run_ui(rc_render, rc_drill)
    check("BEHAVIOUR: rows + drill render the full duplicate audit",
          okui, why[:200])
    # ⚠ PROVE THE FAILURE MODE: with the render branches stripped,
    # duplicate_of exists only in JSON -- and the same invariant must fail.
    okstr, whystr = run_ui(rc_render.replace("r.duplicate_of", "false"),
                           rc_drill.replace("r.duplicate_of", "false"))
    check("[NEG] duplicate_of living only in JSON is caught",
          not okstr and "duplicate" in whystr.lower(), whystr[:160])

    print("\n6. NEGATIVE CONTROLS")
    check("[NEG] a heuristic that excluded the identical pair on its own "
          "would break: the detector's output carries no exclusion field",
          "exclude" not in json.dumps(c1))
    bogus = dict(led)
    bogus["9999999"] = "1111111"
    check("[NEG] an unledgered gid is not marked in the dataset",
          "9999999" not in marked)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL DUPLICATE-LISTING GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
