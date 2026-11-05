#!/usr/bin/env python3
"""Bounded rally-data coverage audit (work order 071, 2026-11-04).

Reads only what is ALREADY held: the local evidence file written during normal
collection (Cody/data/rallies_2026.jsonl) and the 3-match feasibility sample
(Cody/coordination/research/SOURCE-FEASIBILITY-070/pbp_*.json). No fetching.

Reports, from the stored evidence: match/set counts, dates, teams, flags
(missing/duplicate/backwards/mismatch), score reconciliation, first-serve
uncertainty, the ace/service-error check of "winner serves next", observed vs
reconstructed points, and side-out % / point-scoring % on KNOWN-serving rallies
only, with numerators, denominators and the opponent complement check.
Season-style aggregates use summed numerators and denominators.

Writes: Cody/coordination/research/SOURCE-FEASIBILITY-070/rally_audit.json
Python 3.9. Run: python3 scripts/rally_audit.py
"""
import collections
import glob
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import rally_sequence as RS  # noqa: E402

EVID = os.path.join(REPO, "Cody", "data", "rallies_2026.jsonl")
SAMPLE = os.path.join(REPO, "Cody", "coordination", "research", "SOURCE-FEASIBILITY-070")
OUT = os.path.join(SAMPLE, "rally_audit.json")


def games_by_id():
    import gamelog
    return dict((str(g.get("game_id")), g) for g in
                gamelog.load_games_jsonl(os.path.join(REPO, "data", "raw", "2026", "games.jsonl"))
                if g.get("game_state") == "F")


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / float(n)
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


def load_records():
    recs, src = {}, {}
    if os.path.exists(EVID):
        for l in open(EVID):
            try:
                r = json.loads(l)
                recs[r["game_id"]] = r
                src[r["game_id"]] = "normal collection"
            except (ValueError, KeyError):
                continue
    G = games_by_id()
    for p in sorted(glob.glob(os.path.join(SAMPLE, "pbp_*.json"))):
        gid = os.path.basename(p)[4:-5]
        if gid in recs:
            continue
        payload = json.load(open(p))
        g = G.get(gid) or {}
        ls = [l for l in (g.get("linescores") or []) if l.get("home") is not None]
        ts = payload.get("teams") or []
        hid = next((str(t.get("teamId")) for t in ts if t.get("isHome")), None)
        vid = next((str(t.get("teamId")) for t in ts if not t.get("isHome")), None)
        recs[gid] = RS.match_record(gid, payload, ls, hid, vid, None, "feasibility sample (070)")
        src[gid] = "feasibility sample"
    return recs, src, G


def main():
    recs, src, G = load_records()
    flags = collections.Counter()
    out_matches = []
    tot = {"sets": 0, "reconciled": 0, "usable": 0, "points": 0, "observed": 0,
           "first_known": 0, "serve_checks": 0, "serve_agree": 0, "known_rallies": 0,
           "unknown_rallies": 0}
    for gid, r in sorted(recs.items()):
        g = G.get(gid) or {}
        names = dict((str(t.get("team_id")), t.get("name_short")) for t in g.get("teams") or [])
        hn, vn = names.get(str(r.get("home_id"))), names.get(str(r.get("visit_id")))
        agg = {"home": {"srv": 0, "srv_won": 0, "rcv": 0, "rcv_won": 0},
               "visit": {"srv": 0, "srv_won": 0, "rcv": 0, "rcv_won": 0}}
        sets_out = []
        for s in r["sets"]:
            # recompute from the stored evidence so the audit tests the code, not the file
            tot["sets"] += 1
            flags.update(s["flags"])
            tot["reconciled"] += s["reconciled"]
            tot["usable"] += s["usable"]
            tot["points"] += s["points"]
            tot["observed"] += s["observed_points"]
            tot["serve_checks"] += s["serve_checks"]
            tot["serve_agree"] += s["serve_agree"]
            fk = bool(s["rallies"] and s["rallies"][0].get("server"))
            tot["first_known"] += fk
            c, unk = RS.phase_counts(s)
            tot["unknown_rallies"] += unk
            tot["known_rallies"] += sum(c[x]["srv"] for x in c)
            if s["usable"]:
                for side in agg:
                    for k in agg[side]:
                        agg[side][k] += c[side][k]
            sets_out.append({"set": s["set"], "final": s["final"], "points": s["points"],
                             "observed_points": s["observed_points"], "flags": s["flags"],
                             "reconciled": s["reconciled"], "usable": s["usable"],
                             "first_serve_known": fk, "unknown_server_rallies": unk})
        teams = {}
        for side, nm in (("home", hn), ("visit", vn)):
            a = agg[side]
            teams[nm or side] = {
                "side_out": {"won": a["rcv_won"], "of": a["rcv"],
                             "pct": round(a["rcv_won"] / a["rcv"], 4) if a["rcv"] else None,
                             "ci95": wilson(a["rcv_won"], a["rcv"])},
                "point_scoring": {"won": a["srv_won"], "of": a["srv"],
                                  "pct": round(a["srv_won"] / a["srv"], 4) if a["srv"] else None,
                                  "ci95": wilson(a["srv_won"], a["srv"])}}
        # complement: home's received rallies are exactly visit's served rallies
        comp = (agg["home"]["rcv"] == agg["visit"]["srv"]
                and agg["home"]["rcv_won"] + agg["visit"]["srv_won"] == agg["visit"]["srv"]
                and agg["visit"]["rcv"] == agg["home"]["srv"]
                and agg["visit"]["rcv_won"] + agg["home"]["srv_won"] == agg["home"]["srv"])
        out_matches.append({"game_id": gid, "source": src[gid], "teams": [hn, vn],
                            "date_epoch": g.get("start_time_epoch"), "sets": sets_out,
                            "known_serving_phase": teams, "complement_holds": comp})
    summary = dict(tot, matches=len(recs), flags=dict(flags),
                   sources=dict(collections.Counter(src.values())),
                   serve_check_agreement=(round(tot["serve_agree"] / tot["serve_checks"], 4)
                                          if tot["serve_checks"] else None),
                   known_rally_share=(round(tot["known_rallies"] /
                                            float(tot["known_rallies"] + tot["unknown_rallies"]), 4)
                                      if (tot["known_rallies"] + tot["unknown_rallies"]) else None))
    json.dump({"summary": summary, "matches": out_matches}, open(OUT, "w"), indent=1)
    print(json.dumps(summary, indent=1))
    for m in out_matches:
        print(m["game_id"], m["teams"], "complement", m["complement_holds"])
        for t, v in m["known_serving_phase"].items():
            print("   %-14s SO %s/%s  PS %s/%s" % (t, v["side_out"]["won"], v["side_out"]["of"],
                                                   v["point_scoring"]["won"], v["point_scoring"]["of"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
