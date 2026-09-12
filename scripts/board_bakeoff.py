#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score POWER against the external boards on results none of them had seen.

⚠ WHY THIS EXISTS. Reconciling records against Evollve surfaced thirteen
teams the external boards place 40+ places away from us. Checking each one
against its own school showed the RECORDS are right -- eleven of twelve agree
with the school on every date -- so the disagreement is method, not data.
"Whose method is better" is then a question that must be MEASURED rather than
argued, and the only honest measure is out-of-sample: results that landed
after every board's stated data horizon.

⚠ AND IT MUST ACCUMULATE. A single day is 50-odd matches, which cannot
separate two good rankings; the first run gave POWER 42/55 against Evollve's
39 and Massey's 34, and the POWER-vs-Evollve split was 6-3 -- p=0.51, i.e.
nothing. Each run appends, so the sample grows and the verdict is allowed to
arrive late instead of being declared early (R1).

Rank-only prediction ignores margin, home floor and availability, so this
measures ORDERING and says so. It is a diagnostic and feeds no rating.
"""
import datetime
import io
import json
import os
import sys
from math import comb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "board_bakeoff_%d.jsonl" % SEASON)


def _last(path):
    if not os.path.exists(path):
        return None
    row = None
    for ln in io.open(path, encoding="utf-8"):
        if ln.strip():
            try:
                row = json.loads(ln)
            except ValueError:
                pass
    return row


def sign_p(k, n):
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1))
    return min(1.0, 2.0 * tail / 2 ** n)


def main():
    import re
    import season_counts as SC

    mas_row = _last(os.path.join(REPO, "Cody/data/massey_snapshots.jsonl")) or {}
    evo_row = _last(os.path.join(REPO, "Cody/data/evollve_snapshots.jsonl")) or {}
    mas = {r["hub_team"]: r.get("rank") for r in (mas_row.get("rows") or [])
           if isinstance(r, dict) and r.get("hub_team")}
    evo = {r["hub_team"]: r.get("evollve_rtg_rank") for r in (evo_row.get("data") or [])
           if isinstance(r, dict) and r.get("hub_team")}
    if not mas or not evo:
        print("no external snapshots held -- nothing to score against")
        return 0

    page = io.open(os.path.join(REPO, "Cody", "START-HERE.html"), encoding="utf-8").read()
    T = json.loads(re.search(r"const TEAMS\s*=\s*(\{.*?\});\n", page, re.S).group(1))
    pwr = {nm: t.get("rank") for nm, t in T.items() if t.get("rank")}

    # ⚠ THE HORIZON IS THE SNAPSHOTS', NOT TODAY'S. A board is only being
    # tested out of sample on matches it could not have seen, and the two
    # externals state their own through-date. Take the LATER of the two.
    cut = os.environ.get("WVB_BAKEOFF_CUT") or "2026-09-11"

    name = {t["team_id"]: t.get("name_short") for t in
            json.load(io.open(os.path.join(REPO, "data/data_%d.json" % SEASON),
                              encoding="utf-8"))["teams"]}
    best = {}
    for l in io.open(os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON),
                     encoding="utf-8"):
        try:
            g = json.loads(l)
        except ValueError:
            continue
        gid = str(g.get("game_id")); prev = best.get(gid)
        if prev is None or g.get("game_state") == "F" or prev.get("game_state") != "F":
            best[gid] = g
    cls = SC.classify(list(best.values()), SEASON)
    corr = SC.corrections(SEASON)

    def etd(g):
        ep = g.get("start_time_epoch")
        return (datetime.datetime.utcfromtimestamp(ep - 4 * 3600).strftime("%Y-%m-%d")
                if ep else None)

    tests = []
    for gid, g in best.items():
        d = etd(g)
        if cls.get(gid) != "ok" or not d or d <= cut:
            continue
        g2 = SC.apply_correction(g, corr)
        w = SC.winner_index(g2); ts = g2.get("teams") or []
        if w is None or len(ts) != 2:
            continue
        a, b = name.get(ts[w]["team_id"]), name.get(ts[1 - w]["team_id"])
        if a and b and all(x.get(a) and x.get(b) for x in (pwr, mas, evo)):
            tests.append((gid, d, a, b))
    if not tests:
        print("no finals after %s that all three boards rank -- nothing to score" % cut)
        return 0

    boards = {"POWER": pwr, "Massey": mas, "Evollve": evo}
    hits = {k: sum(1 for _, _, a, b in tests if d[a] < d[b]) for k, d in boards.items()}
    rec = {"run_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "cutoff": cut, "n": len(tests),
           "massey_through": mas_row.get("publisher_through"),
           "evollve_retrieved": evo_row.get("retrieved"),
           "hits": hits,
           "gids": [t[0] for t in tests],
           "what_it_measures": ("ORDERING only -- did the higher-ranked side win. "
                                "Ignores margin, home floor and availability. "
                                "Diagnostic; feeds no rating.")}
    pair = {}
    for x in boards:
        for y in boards:
            if x >= y:
                continue
            dis = [(a, b) for _, _, a, b in tests
                   if (boards[x][a] < boards[x][b]) != (boards[y][a] < boards[y][b])]
            xw = sum(1 for a, b in dis if boards[x][a] < boards[x][b])
            pair["%s_vs_%s" % (x, y)] = {"n": len(dis), "%s_right" % x: xw,
                                         "%s_right" % y: len(dis) - xw,
                                         "p": round(sign_p(xw, len(dis)), 4)}
    rec["paired"] = pair
    with io.open(OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # cumulative, which is the only number worth reading
    seen, cum, tot = set(), {k: 0 for k in boards}, 0
    for ln in io.open(OUT, encoding="utf-8"):
        if not ln.strip():
            continue
        r = json.loads(ln)
        fresh = [g for g in r.get("gids", []) if g not in seen]
        if not fresh:
            continue
        seen.update(fresh)
        share = float(len(fresh)) / max(1, r["n"])
        tot += len(fresh)
        for k in boards:
            cum[k] += r["hits"].get(k, 0) * share
    print("this run: %d held-out finals after %s" % (len(tests), cut))
    for k in ("POWER", "Evollve", "Massey"):
        print("   %-8s %3d/%d = %.1f%%" % (k, hits[k], len(tests), 100.0*hits[k]/len(tests)))
    for k, v in pair.items():
        print("   %-18s %s" % (k, v))
    print("\ncumulative across all runs: %d distinct matches" % tot)
    for k in ("POWER", "Evollve", "Massey"):
        print("   %-8s %.1f%%" % (k, 100.0*cum[k]/max(1, tot)))
    print("\n⚠ ONE DAY IS NOT EVIDENCE. Let it accumulate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
