#!/usr/bin/env python3
"""mail 116: a match already PLAYED must not also be simulated or projected as a REMAINING match.

The defect: data/predictions_2026.json runs from TODAY forward and (deliberately) keeps today's finished
matches -- the pre-match pick is what gets scored. simulate_season_2026 simulated every row in it while
also tallying the same matches as results, so each of today's finals counted twice: 60 of 619 fixtures on
2026-11-07, on both the public and the candidate simulation. The page's projections (Projected RPI,
conference standings, cut-line evidence) skip a row whose listed start has passed, which misses a match
played BEFORE its listed start.

1. DETERMINISTIC FIXTURE (synthetic gids, no team names from the live season): every final class.
2. The real producers use the one definition (source + behaviour), with a NEGATIVE CONTROL.
3. LIVE CONSISTENCY on the artifacts on disk: no simulated or projected fixture is a played match, and
   the simulation's metadata names its input generation.
"""
import json, os, sys, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("WVB_SEASON", "2026")
import season_counts as SC

ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m)
    ok = ok and bool(c)


def team(tid, home, win, sets):
    return {"team_id": tid, "name_short": "T" + tid, "is_home": home, "division": 1,
            "sets_won": sets, "is_winner": win}


def lines(*pairs):
    return [{"period": i + 1, "home": h, "visit": v} for i, (h, v) in enumerate(pairs)]


T0 = 1790000000
G = [
    # played and counted: home wins 3-0
    {"game_id": "900001", "game_state": "F", "start_time_epoch": T0, "winner_team_id": "1",
     "teams": [team("1", True, True, 3), team("2", False, False, 0)],
     "linescores": lines((25, 20), (25, 21), (25, 19))},
    # the feed's EMPTY final: F before first serve, no winner, no sets, no lines (the USC-Rutgers shape)
    {"game_id": "900002", "game_state": "F", "start_time_epoch": T0 + 86400 * 3, "winner_team_id": None,
     "teams": [team("3", True, False, None), team("4", False, False, None)], "linescores": []},
    # not started
    {"game_id": "900003", "game_state": "P", "start_time_epoch": T0 + 86400 * 3,
     "teams": [team("5", True, False, None), team("6", False, False, None)], "linescores": []},
    # played but SELF-CONTRADICTORY (flag says home, its own complete lines say away): held, still played
    {"game_id": "900004", "game_state": "F", "start_time_epoch": T0, "winner_team_id": "7",
     "teams": [team("7", True, True, 3), team("8", False, False, 0)],
     "linescores": lines((20, 25), (21, 25), (19, 25))},
    # played and counted, but LISTED to start in the future (finished before its listed start)
    {"game_id": "900005", "game_state": "F", "start_time_epoch": T0 + 86400 * 5, "winner_team_id": "10",
     "teams": [team("9", True, False, 1), team("10", False, True, 3)],
     "linescores": lines((25, 20), (20, 25), (18, 25), (22, 25))},
]
cls = SC.classify(G, 2026)
check(cls == {"900001": "ok", "900002": "empty", "900004": "self_contradictory", "900005": "ok"},
      "fixture: classification is the existing policy (ok / empty / self_contradictory), no new rule %s" % cls)
done = SC.completed_gids(G, 2026)
check(done == {"900001", "900004", "900005"},
      "completed = every final class except empty; the empty final and the unstarted match stay forecastable %s" % sorted(done))
rows = [{"game_id": g["game_id"], "start_epoch": g["start_time_epoch"], "home_win": .6} for g in G]
kept, dropped = SC.remaining_fixtures(rows, done)
check([r["game_id"] for r in kept] == ["900002", "900003"] and len(dropped) == 3,
      "remaining_fixtures: the three played matches leave, the empty final and the unstarted match stay")
counted = set(str(g["game_id"]) for g in SC.countable(G, 2026))
check(not (counted & set(r["game_id"] for r in kept)),
      "no match is both a counted result and a remaining fixture")
check(counted & set(r["game_id"] for r in rows) == {"900001", "900005"},
      "NEGATIVE CONTROL: without the filter, two counted results are ALSO remaining fixtures (the double count)")
now = T0 + 86400 * 2
clock_only = [r for r in rows if r["start_epoch"] > now]
check("900005" in [r["game_id"] for r in clock_only],
      "NEGATIVE CONTROL: the clock test alone keeps a match played before its listed start (900005)")

# ---------------------------------------------------- 2. the producers use the one definition ----
src = lambda f: open(os.path.join(REPO, "scripts", f), encoding="utf-8").read()
sim, hub, pred = src("simulate_season_2026.py"), src("build_hub.py"), src("predict_2026.py")
check("completed_gids(" in sim and "remaining_fixtures(" in sim,
      "simulate_season_2026 drops played matches through season_counts.completed_gids")
check(hub.count('if str(g.get("game_id")) in _played_gids():') == 4 and "completed_gids(" in hub,
      "all four page projections (conference standings, Projected RPI, cut-line rows, evidence) skip played matches")
check("_SCp.countable(_gl_all, SEASON)" in pred and 'g.get("game_state") != "F"' not in pred,
      "predict_2026's played_2026 column counts through the one counting chain, not raw state F")

# ------------------------------------------------- 3. live consistency on the artifacts on disk ----
import gamelog
gp = os.path.join(REPO, "data", "raw", "2026", "games.jsonl")
if os.path.exists(gp):
    gl = gamelog.load_games_jsonl(gp)
    live_done = SC.completed_gids(gl, 2026)
    for pf, sf in (("data/predictions_2026.json", "data/season_sim_2026.json"),
                   ("Cody/data/power_candidate/predictions_2026.json", "Cody/data/power_candidate/season_sim_2026.json")):
        P = os.path.join(REPO, pf); S = os.path.join(REPO, sf)
        if not (os.path.exists(P) and os.path.exists(S)):
            print("SKIP %s / %s absent" % (pf, sf)); continue
        pr = json.load(open(P)); sm = json.load(open(S)).get("meta", {})
        played_in_file = sum(1 for g in pr.get("games", []) if str(g["game_id"]) in live_done)
        check(sm.get("fixtures_dropped_already_played") is not None and sm.get("results_through_epoch"),
              "%s: meta names its input generation (dropped=%s, results through %s, predictions %s)"
              % (sf, sm.get("fixtures_dropped_already_played"),
                 time.strftime("%Y-%m-%d %H:%M", time.localtime(sm.get("results_through_epoch") or 0)),
                 sm.get("predictions_generated_utc")))
        check((pr.get("meta") or {}).get("results_through_epoch") is not None,
              "%s: the forecast names its data cutoff (results_through_epoch)" % pf)
        check(sm.get("predictions_results_through_epoch") == (pr.get("meta") or {}).get("results_through_epoch")
              and sm.get("results_through_epoch") == SC.results_through_epoch(gl, 2026),
              "%s: simulated from THIS forecast generation, on the current counted results (cutoff %s)"
              % (sf, sm.get("results_through_epoch")))
        if sm.get("predictions_results_through_epoch") == (pr.get("meta") or {}).get("results_through_epoch"):
            # same generation: dropped must equal the played rows the simulator could see
            # (rows a strength table excludes are dropped before this step, so <= )
            check((sm.get("fixtures_dropped_already_played") or 0) <= played_in_file
                  and (sm.get("fixtures_simulated") or 0) + (sm.get("fixtures_dropped_already_played") or 0) <= len(pr.get("games", [])),
                  "%s: simulated %s + dropped %s, against %s rows of which %s are played"
                  % (sf, sm.get("fixtures_simulated"), sm.get("fixtures_dropped_already_played"), len(pr.get("games", [])), played_in_file))
        else:
            print("NOTE %s was simulated from predictions %s; the file on disk is %s (a later generation)"
                  % (sf, sm.get("predictions_generated_utc"), (pr.get("meta") or {}).get("generated_utc")))
print("REMAINING-FIXTURE CHECKS " + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
