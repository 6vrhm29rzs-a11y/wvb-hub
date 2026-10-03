#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the team Analysis tab (Phase B, private build).

  1. Rates are summed counts over their own denominator -- recomputed here by
     VALUE from synthetic box lines, never trusted from the code path.
  2. A match without a box score is MISSING, never zero, and leaves every
     rate untouched.
  3. The historical reference reconciles to Texas A&M's verified 2025 PDF.
  4. The tab is private in every layer and cannot take the team page down
     (hoisted data, guarded hook).
  5. No causal or verdict language in what the tab renders.

Run: python3 scripts/test_team_analysis.py
"""
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import team_analysis as TA  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-70s %s" % (label, "ok" if ok else "FAIL %s" % (detail,)))
    if not ok:
        FAILS.append(label)


def row(team, name, pos, sets, **kw):
    r = {"team": team, "name": name, "pos": pos, "sets": sets}
    for f in TA.FIELDS:
        r[f] = kw.get(f, 0)
    return r


def synthetic():
    boxes = {
        "g1": [row("A", "Ann", "OH", 3, k=10, e=2, ta=30, aces=2, sa=20, se=3, bs=1, ba=2, ra=15, re=1),
               row("A", "Sue", "S", 3, ast=9, digs=5, sa=10, se=0),
               row("B", "Bee", "OH", 3, k=8, e=5, ta=35, aces=1, sa=25, se=4, ba=2, ra=18, re=2)],
        "g2": [row("A", "Ann", "OH", 4, k=20, e=4, ta=40, aces=0, sa=15, se=1, bs=0, ba=4, ra=20, re=0),
               row("C", "Cat", "MB", 4, k=12, e=6, ta=44, aces=3, sa=22, se=2, ra=10, re=1)],
    }
    res = [{"gid": "g1", "date": "2026-09-01", "home": "A", "away": "B",
            "home_sets": 3, "away_sets": 0, "sets": [(20, 25), (22, 25), (18, 25)]},
           {"gid": "g2", "date": "2026-09-03", "home": "C", "away": "A",
            "home_sets": 1, "away_sets": 3, "sets": [(25, 20), (23, 25), (25, 21), (25, 23)]},
           {"gid": "g3", "date": "2026-09-05", "home": "A", "away": "D",
            "home_sets": 3, "away_sets": 1, "sets": [(20, 25), (25, 22), (20, 25), (19, 25)]}]
    return boxes, res


def main():
    print("1. RATES ARE SUMMED COUNTS OVER THEIR OWN DENOMINATOR")
    boxes, res = synthetic()
    a = TA.analyze(boxes, res, 2026, only={"A"})["A"]
    t = a["totals"]
    # own: K 30, E 6, TA 70, aces 2, BS 1, BA 6 -> blk 4, sets 7
    check("sets are the MATCHES' sets (3 + 4), not the sum of players' sets", t["sets"] == 7, t["sets"])
    check("earned pts/set = (K + aces + BS + BA/2) / sets", t["earned_pps"] == round((30 + 2 + 1 + 3) / 7.0, 2), t["earned_pps"])
    check("hitting % from summed counts", t["hit_pct"] == round((30 - 6) / 70.0, 3), t["hit_pct"])
    check("[NEG] not the average of the match hitting %s",
          t["hit_pct"] != round(((10 - 2) / 30.0 + (20 - 4) / 40.0) / 2, 3))
    check("aces per SERVE attempt, not per set", t["ace_per_sa"] == round(2 / 45.0, 3), t["ace_per_sa"])
    check("reception error rate per reception", t["rec_err_per_ra"] == round(1 / 35.0, 3), t["rec_err_per_ra"])
    # scoreboard: sets are (away, home). g1 A home: 25*3 = 75; g2 A away: 25+23+25+25 = 98
    check("scoreboard points are a separate quantity from earned points",
          t["board_pps"] == round((75 + 98) / 7.0, 2), t["board_pps"])
    check("opponent side summed too (B + C)", t["opp_counts"]["k"] == 20.0, t["opp_counts"]["k"])

    print("\n2. A MATCH WITH NO BOX SCORE IS MISSING, NEVER ZERO")
    check("g3 (no box) is listed as missing", a["missing_box"] == ["g3"], a["missing_box"])
    check("[NEG] it adds no sets to any rate", t["sets"] == 7)
    m3 = [m for m in a["series"] if m["gid"] == "g3"][0]
    check("its trend row says no box, it carries no metrics", m3["box"] is False and "m" not in m3)
    zero = TA.derive(TA._blank(), TA._blank(), 0)
    check("[NEG] a zero denominator gives None, not 0", zero["hit_pct"] is None and zero["earned_pps"] is None)

    print("\n3. PLAYERS AND ROLES")
    ann = [p for p in a["players"] if p["name"] == "Ann"][0]
    check("TA share = player TA / team TA", ann["ta_share"] == 1.0, ann["ta_share"])
    check("listed position is carried as 'listed_pos'", ann["listed_pos"] == "OH")

    print("\n4. HISTORICAL REFERENCE RECONCILES TO A&M'S VERIFIED 2025 PDF")
    # ⚠ ENVIRONMENT, NOT CALENDAR: 2025 player box lines are gitignored
    # (data/raw/2025/playerbox.jsonl), so a clean checkout / CI has none. The
    # reconcile runs wherever the file exists and says so plainly where it
    # does not -- the same honest-absence mode as test_external_refs.
    if not os.path.exists(os.path.join(REPO, "data", "raw", "2025", "playerbox.jsonl")):
        print("  --   2025 player box lines not present in this checkout "
              "(gitignored); A&M reconcile skipped here, runs locally")
        b25 = None
    else:
        b25, r25 = TA.season_inputs(2025)
    if b25 is None:
        am = None
    else:
        am = TA.analyze(b25, r25, 2025, only={"Texas A&M"}).get("Texas A&M")
    if am is not None:
        c = am["totals"]["counts"]
        check("118 sets", am["totals"]["sets"] == 118, am["totals"]["sets"])
        check("1,716 kills", c["k"] == 1716, c["k"])
        check("157 aces", c["aces"] == 157, c["aces"])
        check("307.5 team blocks (41 solo + 533 assists)", c["bs"] + 0.5 * c["ba"] == 307.5)
        check("18.48 earned pts/set, opponents 14.42",
              am["totals"]["earned_pps"] == 18.48 and am["totals"]["opp_earned_pps"] == 14.42)

    print("\n5. PRIVATE IN EVERY LAYER, AND IT CANNOT BREAK THE TEAM PAGE")
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"), encoding="utf-8").read()
    for tag in ("TANALYSIS-JS", "TANALYSIS-HOOK", "TANALYSIS-CSS"):
        check("strip list removes %s" % tag,
              '("/* %s-BEGIN */", "/* %s-END */")' % (tag, tag) in src)
    check("the analysis is only computed when not PUBLIC", "if not PUBLIC:\n        try:\n            import team_analysis" in src)
    blk = src[src.index("/* TANALYSIS-JS-BEGIN */"):src.index("/* TANALYSIS-JS-END */")]
    top_const = re.findall(r"^(?:const|let) \w+", blk, re.M)
    check("[NEG] no top-level const/let in the tab code (temporal dead zone at boot)",
          not top_const, top_const)
    hook = src[src.index("/* TANALYSIS-HOOK-BEGIN */"):src.index("/* TANALYSIS-HOOK-END */")]
    check("the hook is wrapped in try/catch", "try {" in hook and "catch" in hook)
    page = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(page):
        pub = io.open(page, encoding="utf-8").read()
        check("[NEG] the published page carries no trace of the tab",
              "tanRender" not in pub and "tanData" not in pub)

    print("\n6. NO CAUSAL OR VERDICT LANGUAGE IN THE RENDERED TEXT")
    strings = " ".join(re.findall(r"'([^']*)'", blk)).lower()
    for w in ("because", "caused", "due to", "proves", "the reason", "is a better setter", "is worse"):
        check("[NEG] rendered text never says %r" % w, w not in strings)
    check("the setter view says it is not a quality verdict",
          re.search(r"<b>not</b> a '\s*\+\s*'setter-quality verdict", blk) is not None
          or "not</b> a setter-quality verdict" in blk)


    print("\n7. MAIL 030 CORRECTIONS")
    # (a) a partial box (covers 3 of 4 sets) is left out, never divided by
    #     either basis -- the Nebraska-Georgia Tech case
    b2 = {"p1": [row("A", "Ann", "OH", 3, k=40, ta=90, sa=60),
                 row("B", "Bee", "OH", 3, k=30, ta=95, sa=55)]}
    r2 = [{"gid": "p1", "date": "2026-09-12", "home": "A", "away": "B",
           "home_sets": 3, "away_sets": 1, "sets": [(24, 26), (25, 17), (25, 18), (25, 12)]}]
    a2 = TA.analyze(b2, r2, 2026, only={"A"})["A"]
    check("a 3-set box for a 4-set match is PARTIAL and out of every rate",
          a2["partial_box"] == ["p1"] and a2["totals"]["sets"] == 0, a2["partial_box"])
    check("its trend row says so", "covers 3 of 4 sets" in (a2["series"][0].get("box_note") or ""))
    check("[NEG] box_complete rejects a mismatch", not TA.box_complete(b2["p1"][:1], b2["p1"][1:], 4))
    # (b) paired coverage: aces from a match with NO serve attempts never
    #     reach the per-serve rate
    b3 = {"s1": [row("A", "Ann", "OH", 3, k=10, ta=30, aces=4, sa=0, se=2),
                 row("B", "Bee", "OH", 3, k=8, ta=30, sa=40)],
          "s2": [row("A", "Ann", "OH", 3, k=10, ta=30, aces=2, sa=40, se=4),
                 row("B", "Bee", "OH", 3, k=8, ta=30, sa=40)]}
    r3 = [{"gid": g, "date": "2026-09-0%d" % i, "home": "A", "away": "B",
           "home_sets": 3, "away_sets": 0, "sets": [(20, 25)] * 3}
          for i, g in ((1, "s1"), (2, "s2"))]
    t3 = TA.analyze(b3, r3, 2026, only={"A"})["A"]["totals"]
    check("ace/serve uses only matches that recorded serves (2/40)", t3["ace_per_sa"] == 0.05, t3["ace_per_sa"])
    check("[NEG] not (4+2)/40 from unpaired counts", t3["ace_per_sa"] != round(6 / 40.0, 3))
    check("coverage is stated: 1 match with serve data", t3["serve_cov_matches"] == 1)
    # (c) individual block credit is BS + BA per set (assists count fully)
    b4 = {"k1": [row("A", "Mid", "MB", 3, bs=1, ba=6, ta=10), row("B", "X", "OH", 3, ta=30)]}
    r4 = [{"gid": "k1", "date": "2026-09-01", "home": "A", "away": "B",
           "home_sets": 3, "away_sets": 0, "sets": [(20, 25)] * 3}]
    a4 = TA.analyze(b4, r4, 2026, only={"A"})["A"]
    mid = [p for p in a4["players"] if p["name"] == "Mid"][0]
    check("player B/S = (BS + BA) / sets = 7/3", mid["bps"] == round(7 / 3.0, 2), mid["bps"])
    check("team blocks still use BS + BA/2 = 4/3", a4["totals"]["bps"] == round(4 / 3.0, 2), a4["totals"]["bps"])
    # (d) page copy
    check("[NEG] no Texas A&M default column on team pages", "tanRef" not in blk and "refT" not in blk)
    check("[NEG] Cody's internal Stanford note is gone from the product",
          "cody" not in strings and "setter case study" not in strings)
    check("rows are keyboard-openable", 'tabindex="0" role="link"' in blk and "keydown" in blk)
    check("'not integrated and verified' wording, not a flat 'not in our data'",
          "not integrated and" in blk and "Not in our data" not in blk)
    check("tstats and the Analysis tab share one completeness rule",
          "_TAc.box_complete(" in src)
    check("tstats per-serve rates use the paired pools", '"ace_rate": (round(d.get("ace_s", 0)' in src)


    print("\n8. MAIL 036: PLAYER BLOCKS ONE DEFINITION; RULER/BASIS INDEPENDENT")
    import re as _re
    js = src
    for label, pat in (("tdLeaders", r"\['blocks/set', p => \(p\.bs \|\| 0\) \+\s*0\.5"),
                       ("player page chip", r"\(\(p\.bs \|\| 0\) \+ 0\.5 \* \(p\.ba"),
                       ("player season table", r"\(p\.bs \+ p\.ba \* 0\.5\)"),
                       ("box score player row", r"\(r\.bs \+ r\.ba \* 0\.5\)"),
                       ("match log", r"const blk = g\.bs \+ g\.ba \* 0\.5")):
        check("[NEG] %s no longer shows player blocks as BS + BA/2" % label,
              _re.search(pat, js) is None)
    check("the leaderboard aggregate uses BS + BA for player blocks",
          'blocks = (r.get("block_solos") or 0) + (r.get("block_assists") or 0)' in js)
    check("...while earned points keep the team half-assist convention",
          '+ 0.5 * (r.get("block_assists") or 0)' in js)
    check("Overview star rows take displayed blocks from box counts, not the model",
          '_st["bps_basis"] = "individual BS+BA per set, 2026 box counts"' in js)
    check("the ruler click handler is scoped to ruler buttons only",
          "document.querySelectorAll('#v-rankings .segb[data-r]').forEach(b =>\n  b.addEventListener('click'" in js)
    check("[NEG] no handler binds renderPoll to every Rankings .segb",
          "document.querySelectorAll('#v-rankings .segb').forEach(b =>\n  b.addEventListener('click'" not in js)

    print("\n%s" % ("ALL TEAM-ANALYSIS GUARDS PASS" if not FAILS else
                    "FAILED: %d\n   - %s" % (len(FAILS), "\n   - ".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
