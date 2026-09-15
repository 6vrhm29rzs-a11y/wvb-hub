#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What actually separates good teams from bad ones? Measure it.

Cody, 2026-09-13: "What makes a team good, bad, meh? I want to see it."

THE METHOD, WRITTEN DOWN BEFORE THE NUMBERS EXIST (R1). For each team
metric:
  * build every team's 2025 season rate from its Division-I matches;
  * for a given match, REBUILD both teams' rates with that match removed
    (leave-one-out), so no match helps predict itself;
  * the metric "calls" the team with the better rate;
  * score = the share of matches it calls correctly, ties counted as half.
    On a balanced two-outcome problem that share IS the AUC of a
    single-feature ranker -- threshold-free, so no cutoff is chosen here
    (R1 again: a verdict resting on a cutoff I picked has tested nothing).
  * a 1,000-resample bootstrap over matches gives the interval.

⚠ THIS IS SEPARATION, NOT CAUSATION, and the difference matters. A season
rate is partly the RESULT of being good: a strong team faces scrambling
defences and hits better because of it. Nor is schedule controlled -- a
team with pretty rates may have played nobody. So this answers "which
qualities distinguish the teams that win" and NOT "do this and you will
win". The page says so wherever it draws this.

Writes data/metric_value_2025.json. Run: python3 scripts/what_makes_good.py
"""

import io
import json
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SEASON = 2025
OUT = os.path.join(REPO, "data", "metric_value_%d.json" % SEASON)

# (key, label, what it is, higher_is_better)
METRICS = [
    ("hit", "Hitting %", "(kills - errors) / attacks", True),
    ("killpct", "Kill %", "kills / attacks", True),
    ("kps", "Kills / set", "kills per set", True),
    ("pps", "Points / set", "kills + blocks + aces per set", True),
    ("bps", "Blocks / set", "solo + half assists, per set", True),
    ("aps", "Aces / set", "service aces per set", True),
    ("dps", "Digs / set", "digs per set", True),
    ("asps", "Assists / set", "assists per set", True),
    ("recv_ok_rate", "Reception, clean", "1 - reception errors / attempts",
     True),
    ("svc_err_rate", "Serve errors", "service errors / serve attempts",
     False),
    ("err_ps", "Attack errors / set", "attack errors per set", False),
    # ⚠ RALLY-DENOMINATED, the backlog's open ask. A per-SET rate is
    # distorted by how long the sets ran: a 30-28 set gives a team far more
    # chances than a 25-15 one, so "kills per set" partly measures how close
    # the match was. Rallies are the real denominator -- every rally ends in
    # exactly one point, so the count is the points both teams scored.
    # Whether it actually SEPARATES better is the question, not the premise.
    ("kpr", "Kills / rally", "kills per rally played", True),
    ("bpr", "Blocks / rally", "solo + half assists, per rally", True),
    ("dpr", "Digs / rally", "digs per rally played", True),
]
# the same metric measured on what a team ALLOWS, and the differential
SIDES = ("own", "opp", "diff")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load():
    """Per-match, per-team raw counts for every Division-I 2025 final."""
    # ⚠ D-I MEMBERSHIP COMES FROM THE ARCHIVED RPI TABLE, and the join goes
    # through the project's own normaliser -- ncaa.com renders the same school
    # differently across endpoints, and joining on raw names is the mistake
    # this codebase has paid for four times.
    from reconcile_2025 import norm
    di = set()
    rpi = json.load(io.open(os.path.join(
        REPO, "data/raw/2025/rpi_official.json"), encoding="utf-8"))
    for r in (rpi.get("data") or rpi.get("rows") or []):
        nm = r.get("School") or r.get("SCHOOL") or r.get("school")
        if nm:
            di.add(norm(nm))
    if len(di) < 300:
        raise SystemExit("only %d D-I schools parsed from the RPI table -- "
                         "refusing to measure on a broken membership join"
                         % len(di))

    finals = {}
    for line in io.open(os.path.join(REPO, "data/raw/2025/games.jsonl"),
                        encoding="utf-8"):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if (g.get("game_state") or g.get("state")) != "F":
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        finals[str(g.get("game_id"))] = g

    boxes = {}
    for line in io.open(os.path.join(REPO, "data/raw/2025/boxscores.jsonl"),
                        encoding="utf-8"):
        try:
            b = json.loads(line)
        except ValueError:
            continue
        boxes[str(b.get("game_id"))] = b

    rows = []
    for gid, g in finals.items():
        b = boxes.get(gid)
        if not b or len(b.get("teams") or []) != 2:
            continue
        ts = g["teams"]
        names = {str(t.get("team_id")): (t.get("name_short") or "").strip()
                 for t in ts}
        if not all(norm(names.get(str(t.get("team_id"))) or "") in di
                   for t in ts):
            continue                      # D-I vs D-I only
        win = None
        for t in ts:
            if t.get("is_winner"):
                win = str(t.get("team_id"))
        if win is None:
            continue
        side = {}
        ok = True
        for tb in b["teams"]:
            tid = str(tb.get("team_id"))
            st = tb.get("team_stats") or {}
            sets_ = _num(st.get("gamesPlayed"))
            ta = _num(st.get("attackAttempts"))
            if sets_ <= 0 or ta <= 0:
                ok = False
                break
            side[tid] = {
                "sets": sets_, "k": _num(st.get("kills")),
                "e": _num(st.get("attackErrors")), "ta": ta,
                "ast": _num(st.get("assists")),
                "aces": _num(st.get("serviceAces")),
                "serr": _num(st.get("serviceErrors")),
                "satt": _num(st.get("serveAttempts")),
                "digs": _num(st.get("digs")),
                "ra": _num(st.get("receptionAttempts")),
                "re": _num(st.get("receptionErrors")),
                "bs": _num(st.get("blockSolos")),
                "ba": _num(st.get("blockAssists")),
                "rally": 0.0,
            }
        if not ok or len(side) != 2:
            continue
        # ⚠ RALLIES ARE READ FROM THE LINE SCORE, NOT ESTIMATED. Every rally
        # ends in exactly one point, so the rallies played in a match are the
        # points both sides scored. A match whose tape is missing or whose
        # pairs are tied (the frozen-partial shape) contributes NO rally
        # count rather than a guessed one, and its rally metrics stay None.
        rall = 0.0
        for ls in (g.get("linescores") or []):
            try:
                v, h = int(ls["visit"]), int(ls["home"])
            except (TypeError, ValueError, KeyError):
                rall = 0.0
                break
            if v == h:
                rall = 0.0
                break
            rall += v + h
        for tid in side:
            side[tid]["rally"] = rall
        ids = list(side)
        rows.append({"gid": gid, "a": ids[0], "b": ids[1], "win": win,
                     "stats": side, "names": names})
    return rows


FIELDS = ("sets", "k", "e", "ta", "ast", "aces", "serr", "satt", "digs",
          "ra", "re", "bs", "ba", "rally")


def rates(tot):
    """Season totals -> the rate for every metric. None where undefined."""
    s, ta, satt, ra = tot["sets"], tot["ta"], tot["satt"], tot["ra"]
    out = {}
    out["hit"] = (tot["k"] - tot["e"]) / ta if ta else None
    out["killpct"] = tot["k"] / ta if ta else None
    out["kps"] = tot["k"] / s if s else None
    blocks = tot["bs"] + tot["ba"] / 2.0
    out["pps"] = (tot["k"] + blocks + tot["aces"]) / s if s else None
    out["bps"] = blocks / s if s else None
    out["aps"] = tot["aces"] / s if s else None
    out["dps"] = tot["digs"] / s if s else None
    out["asps"] = tot["ast"] / s if s else None
    out["recv_ok_rate"] = (1.0 - tot["re"] / ra) if ra else None
    out["svc_err_rate"] = (tot["serr"] / satt) if satt else None
    out["err_ps"] = tot["e"] / s if s else None
    rl = tot.get("rally") or 0.0
    out["kpr"] = tot["k"] / rl if rl else None
    out["bpr"] = blocks / rl if rl else None
    out["dpr"] = tot["digs"] / rl if rl else None
    return out


def main():
    rows = load()
    print("2025 Division-I finals with a usable box on both sides: %d"
          % len(rows))
    if len(rows) < 500:
        raise SystemExit("too few matches to measure anything")

    # season totals, own and allowed
    own, opp = {}, {}
    for r in rows:
        a, b = r["a"], r["b"]
        for me, you in ((a, b), (b, a)):
            for store, src in ((own, me), (opp, you)):
                d = store.setdefault(me, dict((f, 0.0) for f in FIELDS))
                for f in FIELDS:
                    d[f] += r["stats"][src][f]

    MIN_SETS = 40          # a rate under ~13 matches is noise, stated not fitted
    calls = dict(((k, s), [0.0, 0]) for k, _l, _d, _h in METRICS
                 for s in SIDES)
    per_match = dict(((k, s), []) for k, _l, _d, _h in METRICS for s in SIDES)

    for r in rows:
        a, b, win = r["a"], r["b"], r["win"]
        loo = {}
        ok = True
        for tid in (a, b):
            for store, src in ((own, tid), (opp, a if tid == b else b)):
                pass
            o = dict((f, own[tid][f] - r["stats"][tid][f]) for f in FIELDS)
            other = b if tid == a else a
            p = dict((f, opp[tid][f] - r["stats"][other][f]) for f in FIELDS)
            if o["sets"] < MIN_SETS or p["sets"] < MIN_SETS:
                ok = False
                break
            loo[tid] = {"own": rates(o), "opp": rates(p)}
        if not ok:
            continue
        for key, _lab, _desc, hi in METRICS:
            for side in SIDES:
                if side == "diff":
                    va = (None if loo[a]["own"][key] is None
                          or loo[a]["opp"][key] is None
                          else loo[a]["own"][key] - loo[a]["opp"][key])
                    vb = (None if loo[b]["own"][key] is None
                          or loo[b]["opp"][key] is None
                          else loo[b]["own"][key] - loo[b]["opp"][key])
                    better_high = hi
                else:
                    va, vb = loo[a][side][key], loo[b][side][key]
                    # ALLOWED is good when LOW, so the direction flips
                    better_high = hi if side == "own" else not hi
                if va is None or vb is None:
                    continue
                if va == vb:
                    sc = 0.5
                else:
                    pick = a if ((va > vb) == better_high) else b
                    sc = 1.0 if pick == win else 0.0
                calls[(key, side)][0] += sc
                calls[(key, side)][1] += 1
                per_match[(key, side)].append(sc)

    rnd = random.Random(20260913)
    results = []
    for key, lab, desc, hi in METRICS:
        for side in SIDES:
            vals = per_match[(key, side)]
            n = len(vals)
            if n < 500:
                continue
            auc = sum(vals) / n
            boots = []
            for _ in range(1000):
                s = sum(vals[rnd.randrange(n)] for _ in range(n))
                boots.append(s / n)
            boots.sort()
            results.append({
                "metric": key, "label": lab, "definition": desc,
                "side": side,
                "higher_is_better": (hi if side != "opp" else (not hi)),
                "auc": round(auc, 4),
                "lo": round(boots[24], 4), "hi": round(boots[974], 4),
                "n": n,
            })
    results.sort(key=lambda r: -r["auc"])
    doc = {
        "season": SEASON,
        "question": "Which team qualities separate the side that wins from "
                    "the side that loses?",
        "method": "For each metric, both teams' season rates are rebuilt with "
                  "the match itself removed (leave-one-out); the metric calls "
                  "the team with the better rate; the score is the share of "
                  "matches called correctly, ties as half. On a two-outcome "
                  "problem that share is the AUC of a single-feature ranker, "
                  "so no threshold is chosen. 1,000-resample bootstrap for "
                  "the interval.",
        "caveat": "Separation, not causation. A season rate is partly the "
                  "RESULT of being good, and schedule strength is not "
                  "controlled here.",
        "matches": len(rows), "min_sets": MIN_SETS,
        "sides": {"own": "what the team does",
                  "opp": "what it allows its opponents",
                  "diff": "the team minus its opponents"},
        "results": results,
    }
    json.dump(doc, io.open(OUT, "w", encoding="utf-8"), indent=1)
    print("wrote %s" % OUT)
    print("\n%-22s %-5s %6s   %s" % ("metric", "side", "calls", "95% interval"))
    for r in results[:18]:
        print("%-22s %-5s %6.1f%%   %.1f-%.1f%%  (n=%d)"
              % (r["label"], r["side"], r["auc"] * 100,
                 r["lo"] * 100, r["hi"] * 100, r["n"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
