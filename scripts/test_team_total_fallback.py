#!/usr/bin/env python3
"""Team-total fallback against INDEPENDENT hand-written expectations
(Reviewer, B032): the expected totals below are typed from the fixture, not
computed by the helper under test."""
import json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import build_hub as B
import season_counts as SC
FAIL = []
def check(n, ok):
    print("  %-66s %s" % (n, "ok" if ok else "FAIL"))
    if not ok: FAIL.append(n)

def ts(k, e, ta, gp, ba=0, bs=0):
    return {"kills": str(k), "attackErrors": str(e), "attackAttempts": str(ta), "gamesPlayed": str(gp),
            "assists": "0", "digs": "0", "blockSolos": str(bs), "blockAssists": str(ba),
            "serviceAces": "1", "serviceErrors": "2", "serveAttempts": "0",
            "receptionAttempts": "0", "receptionErrors": "3"}
tmp = tempfile.mkdtemp(); d = os.path.join(tmp, "data", "raw", str(B.SEASON)); os.makedirs(d)
recs = [
  {"game_id": "N1", "teams": [{"team_id": "1", "name_short": "Alpha", "team_stats": ts(40, 10, 100, 3, ba=10, bs=2)},
                              {"team_id": "2", "name_short": "Beta",  "team_stats": ts(30, 15, 95, 3)}]},
  # swapped attribution in the raw record: the ledger says 3<->4
  {"game_id": "SW", "teams": [{"team_id": "3", "name_short": "Gamma", "team_stats": ts(50, 5, 120, 4)},
                              {"team_id": "4", "name_short": "Delta", "team_stats": ts(20, 20, 110, 4)}]},
  {"game_id": "MIX", "teams": [{"team_id": "2", "name_short": "Beta", "team_stats": ts(33, 3, 90, 3)},
                               {"team_id": "3", "name_short": "Gamma", "team_stats": ts(22, 8, 88, 3)}]},
  # one side has no team totals at all -> the match stays out
  {"game_id": "HALF", "teams": [{"team_id": "1", "name_short": "Alpha", "team_stats": ts(9, 1, 30, 3)},
                                {"team_id": "5", "name_short": "Eps", "team_stats": {}}]},
]
open(os.path.join(d, "boxscores.jsonl"), "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
res = [{"gid": "N1", "home": "Alpha", "away": "Beta"}, {"gid": "SW", "home": "Gamma", "away": "Delta"},
       {"gid": "HALF", "home": "Alpha", "away": "Eps"},
       {"gid": "NAMED", "home": "Alpha", "away": "Beta"}, {"gid": "MIX", "home": "Beta", "away": "Gamma"}]
boxes = {"NAMED": [{"team": "Alpha", "name": "A One", "k": 5}, {"team": "Beta", "name": "B One", "k": 4}],
         "MIX": [{"team": "Beta", "name": "B Two", "k": 7}]}   # the hub drops nameless rows, so only one side survives
orig_repo, orig_sw = B.REPO, SC.box_team_swaps
B.REPO = tmp; SC.box_team_swaps = lambda season: {"SW": {"3": "4", "4": "3"}}
try:
    out, only = B._team_total_fallback(boxes, res, set(r["gid"] for r in res))
finally:
    B.REPO, SC.box_team_swaps = orig_repo, orig_sw
n1 = dict((r["team"], r) for r in out.get("N1", []))
check("nameless match gets one team row per side", sorted(n1) == ["Alpha", "Beta"])
check("Alpha totals equal the typed fixture (40 K, 10 E, 100 TA, 3 sets)",
      (n1["Alpha"]["k"], n1["Alpha"]["e"], n1["Alpha"]["ta"], n1["Alpha"]["sets"]) == (40, 10, 100, 3))
check("team block assists carried raw (10), for the team 1/2 rule downstream", n1["Alpha"]["ba"] == 10)
check("unrecorded attempts beside real errors stay 0 (paired pooling excludes them)",
      n1["Alpha"]["sa"] == 0 and n1["Alpha"]["se"] == 2)
sw = dict((r["team"], r) for r in out.get("SW", []))
check("a ledgered swap puts Delta's line under Gamma (50 K -> Delta)", sw["Delta"]["k"] == 50 and sw["Gamma"]["k"] == 20)
check("a side with no team totals keeps the whole match out", "HALF" not in out)
check("a fully named match is untouched", out["NAMED"] is boxes["NAMED"])
check("a MIXED match (one side unnamed) is replaced wholesale, never double-counted",
      len(out.get("MIX", [])) == 2 and all(r.get("team_total") for r in out["MIX"]) and
      not any(r.get("name") for r in out["MIX"]) and
      dict((r["team"], r["k"]) for r in out["MIX"]) == {"Beta": 33, "Gamma": 22})
check("every fallback row is a team row with no player name", all(r["team_total"] and r["name"] == "" for g in ("N1", "SW") for r in out[g]))
check("coverage counts: Alpha 1, Beta 2, Gamma 2, Delta 1", only == {"Alpha": 1, "Beta": 2, "Gamma": 2, "Delta": 1})
check("the input BOXES dict is not modified", set(boxes) == {"NAMED", "MIX"})
print("FAILED: %s" % FAIL if FAIL else "ALL TEAM-TOTAL FALLBACK CHECKS HOLD"); sys.exit(1 if FAIL else 0)
