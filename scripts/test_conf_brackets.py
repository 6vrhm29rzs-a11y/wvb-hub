#!/usr/bin/env python3
"""Real conference brackets and full-field bid odds (Cody, 2026-11-23). Synthetic fixtures; no stored data."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf_brackets as CB

fails = []


def check(ok, msg):
    print("%s %s" % ("PASS" if ok else "FAIL", msg))
    if not ok:
        fails.append(msg)


def match(gid, ep, a, b, winner=None, sets=None):
    return {"game_id": gid, "epoch": ep, "date": "2026-11-%02d" % (20 + ep), "a": a, "b": b, "winner": winner,
            "state": "F" if winner else "P", "sets": sets, "round": 0}


TEAMS = ["A", "B", "C", "D"]
CAND = {"teams": {"A": {"theta": 2.0, "sets": 40}, "B": {"theta": 1.0, "sets": 40}, "C": {"theta": 0.0, "sets": 40}, "D": {"theta": -1.0, "sets": 40}},
        "win_model": {"a": 0.2, "b": 1.0, "c": 0.0, "s_now": 1.0}, "home_setshare": 0.0}
ROW = {"structure": "standard", "host": "neutral"}

tree = CB.template(4, "standard")
fit = CB.fit_seeds(tree, 4, [match("1", 0, "A", "D", "A", [3, 0]), match("2", 0, "B", "C", "C", [1, 3])], TEAMS)
check(fit and fit[0] == {1: "A", 2: "B", 3: "C", 4: "D"} and fit[2] == 0, "published order that fits the real pairings is kept exactly")
bad = CB.fit_seeds(tree, 4, [match("1", 0, "A", "B", "A", [3, 0]), match("2", 1, "A", "C", "C", [0, 3]), match("3", 2, "A", "D", "A", [3, 0])], TEAMS)
check(bad is None, "NEGATIVE CONTROL: a team playing on after losing cannot be placed on a bracket shape")
moved = CB.fit_seeds(tree, 4, [match("1", 0, "A", "B", "A", [3, 0]), match("2", 0, "C", "D", "C", [3, 1])], TEAMS)
check(moved and moved[0] != {1: "A", 2: "B", 3: "C", 4: "D"}, "NEGATIVE CONTROL: an order the real pairings contradict is not returned as-is")

obs = {"field": 4, "champion": None, "matches": [match("1", 0, "A", "D", "A", [3, 0]), match("2", 0, "B", "C", "C", [1, 3])]}
b = CB.build("T", ROW, obs, TEAMS, CAND, {"A": "20-5"}, {"A": "10-2"}, n=4000)
check(abs(sum(b["aq_prob"].values()) - 1) < 1e-9 and set(b["aq_prob"]) == {"A", "C"}, "only teams still alive can win the bid")
check(b["favourite"] == "A" and b["aq_prob"]["A"] > b["aq_prob"]["C"], "the likeliest champion is the stronger survivor")
final = b["bracket"]
check(final["state"] == "upcoming" and all(s["known"] for s in final["slots"]), "a final between two known survivors is upcoming, not guessed")
check(all(k["state"] == "final" for k in final["kids"]), "played rounds show as final")
sem = [k for k in final["kids"] if {s["team"] for s in k["slots"]} == {"B", "C"}][0]
i = [s["team"] for s in sem["slots"]].index("C")
check(sem["winner"] == i and sem["sets"][i] == 3, "the winner and set score stay with the right team")
check(sum(1 for m in b["chalk"] if m["source"] == "actual") == 2 and b["chalk"][-1]["winner"] == "A", "the scenario keeps real results and sends the favourite through")
import random
champ, ms = b["sampler"](random.Random(1))
check(champ in ("A", "C") and len(ms) == 1, "a simulated run plays only the unplayed match")

done = dict(obs, champion="C", matches=obs["matches"] + [match("3", 1, "A", "C", "C", [2, 3])])
d = CB.build("T", ROW, done, TEAMS, CAND, n=500)
check(d["aq_prob"] == {"C": 1.0} and d["decided"], "a decided tournament gives its champion the bid outright")

KEYS = ["t%02d" % i for i in range(70)]
games = [(KEYS[i], KEYS[j], "g%d-%d" % (i, j)) for i in range(70) for j in range(i + 1, min(i + 6, 70))]
recs = dict((k, {"w": 5, "l": 5, "n": 10, "di": 10}) for k in KEYS)
conf = dict((k, "c%d" % (i % 7)) for i, k in enumerate(KEYS))
fixed = dict(("c%d" % i, KEYS[i]) for i in range(7))
o = CB.bid_odds(games, [], KEYS, conf, [], {}, fixed, set(KEYS), recs, 0.5, 0.8, n=20)
check(abs(sum(v["in"] for v in o.values()) - 64) < 1e-9 and abs(sum(v["aq"] for v in o.values()) - 7) < 1e-9,
      "every simulated field has 64 teams and one bid per league")
check(all(abs(v["aq"] + v["al"] - v["in"]) < 1e-9 and v["aq"] * v["al"] == 0 for v in o.values()),
      "with fixed champions no team holds an automatic and an at-large bid in the same run")
import build_hub as BH
slot = {"win": 0.87, "known": True, "seed": 5, "team": "A", "rec": "20-5", "conf_rec": "10-2"}
check("87%" in BH._ct_slot(slot, None, None, "upcoming"), "an upcoming match shows its chance")
check("87%" not in BH._ct_slot(slot, None, None, "live"), "NEGATIVE CONTROL: a match in progress never shows a pre-match chance")
print("ALL CONFERENCE BRACKET CHECKS HOLD" if not fails else "CONFERENCE BRACKET CHECKS FAILED")
sys.exit(1 if fails else 0)
