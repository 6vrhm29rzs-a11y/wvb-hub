#!/usr/bin/env python3
"""Mail 052 A-C: one identity across consumers, the cited Lambert participation
override, the shared complete-box season basis. Reads built artifacts."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
FAIL = []
def check(n, ok, x=""):
    print("  %-72s %s%s" % (n, "ok" if ok else "FAIL", ("  " + x) if x else ""))
    if not ok: FAIL.append(n)
import nameclean as N
# ---- row helper, pure
r = {"team_id": "45995", "first": "Lejla", "last": "Hadåÿiredåÿepovic", "gp": "3"}
o = N.apply_identity_override(r, "6624495")
check("identity override: exact gid+team+spelling -> school spelling, source kept",
      o["last"] == "Hadžiredžepovic" and o["last_src"] == "Hadåÿiredåÿepovic")
check("[NEG] same spelling in another game is NOT rewritten", N.apply_identity_override(r, "6624278") is r)
check("[NEG] same spelling on another team is NOT rewritten",
      N.apply_identity_override(dict(r, team_id="1"), "6624495").get("last") == "Hadåÿiredåÿepovic")
L = {"team_id": "46003", "first": "Lolo", "last": "Lambert", "gp": "5", "kills": "0"}
lo = N.apply_identity_override(L, "6624778")
check("participation override: Lambert/Troy gp 5 -> 0, labelled, feed value kept",
      lo["gp"] == "0" and lo["gp_src"] == "5" and "school-report" in lo["participation_corrected"])
for _nm in ("Brooklyn Vigil", "Nene Hawkins", "Harley Krause", "Taylor Gaines", "Olivia Brown"):
    _f, _, _l = _nm.partition(" ")
    _o = N.apply_identity_override({"team_id": "46003", "first": _f, "last": _l, "gp": "5"}, "6624778")
    check("participation override (mail 053): %s Troy gp 5 -> 0" % _nm, _o["gp"] == "0" and _o["gp_src"] == "5")
check("[NEG] her other matches are untouched", N.apply_identity_override(dict(L, gp="4"), "6624774")["gp"] == "4")
# ---- aggregate + rating + availability consumers
pp = json.load(open(os.path.join(REPO, "data/raw/2026/players_2026.json"))); pl = pp.get("players", pp)
pl = list(pl.values()) if isinstance(pl, dict) else pl
agg = [p for p in pl if "epovic" in (p.get("last") or "")]
check("season aggregate: ONE Lejla entry", len(agg) == 1, str([(p.get("last"), p.get("gp") or p.get("sets")) for p in agg]))
pr = json.load(open(os.path.join(REPO, "data/player_rating_2026.json"))); rows = pr.get("players", pr)
rt = [x for x in rows if isinstance(x, dict) and "epovic" in (x.get("name") or "")]
check("player ratings: ONE Lejla entry", len(rt) == 1, str([(x.get("name")) for x in rt]))
av = json.load(open(os.path.join(REPO, "data/availability_2026.json")))
check("availability: no garbled-spelling identity", not any("åÿ" in a["name"] for f in av["flagged"] for a in f["absent"]))
# ---- page
page = open(os.path.join(REPO, "Cody", "START-HERE.html"), encoding="utf-8").read()
def grab(pat):
    i = re.search(pat, page).start(1); d = 0; j = i; ins = esc = False
    while True:
        c = page[j]
        if ins:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': ins = False
        elif c == '"': ins = True
        elif c in "[{": d += 1
        elif c in "]}":
            d -= 1
            if d == 0: break
        j += 1
    return json.loads(page[i:j + 1])
P = grab(r"const PLAYERS = (\[)"); T = grab(r"const TEAMS = (\{)")
lam = [p for p in P if p["name"] == "Lolo Lambert" and p["team"] == "Louisiana"][0]
tg = [g for g in lam["games"] if g["gid"] == "6624778"][0]
check("page: Lambert/Troy line shows 0 sets, labelled school-corrected", tg["sets"] == 0 and tg.get("src_corrected"))
check("page: her season sets exclude the 5 erroneous sets", lam["sets"] == sum(g["sets"] for g in lam["games"] if not g.get("partial_box")))
check("page: Louisiana team totals unchanged by it (K 60 in that match)",
      T["Louisiana"]["tstats"]["mbm"]["6624778"]["k"] == 60)
mer = [p for p in P if p["team"] == "Merrimack" and p.get("partial_box_matches")]
check("partial box flagged in game logs and left out of season totals (%d Merrimack players)" % len(mer),
      mer and all(p["sets"] == sum(g["sets"] for g in p["games"] if not g.get("partial_box")) for p in mer))
so = [g for p in P for g in p["games"] if not g.get("partial_box") and
      (g["k"] + g["ta"] + g["digs"] + g["ast"] + g["aces"] + g["bs"] + g["ba"]) == 0
      and ((g.get("sa") or 0) > 0 or (g.get("ra") or 0) > 0)]
check("serve/reception-only lines carry their attempts in the game log (%d lines)" % len(so), len(so) > 0)
za = [g for p in P for g in p["games"] if g["sets"] > 0 and not g.get("src_corrected") and
      (g["k"] + g["ta"] + g["digs"] + g["ast"] + g["aces"] + g["bs"] + g["ba"] + (g.get("sa") or 0) + (g.get("ra") or 0)) == 0]
check("zero-action lines WITHOUT a school report keep their reported sets (%d kept)" % len(za), len(za) > 0)
lj = [p for p in P if p["team"] == "St. John's (NY)" and "epovic" in p["name"]]
# Relative, not pinned: the old "51 sets" broke the day St. John's played again.
lj_sets = (sum(g["sets"] for g in lj[0]["games"] if not g.get("partial_box") and str(g.get("gid")) != "6624495")
           if len(lj) == 1 else None)
check("page: ONE Lejla, season sets == her counted game log (held 6624495 excluded)",
      len(lj) == 1 and lj[0]["sets"] == lj_sets, str([(p["name"], p["sets"], lj_sets) for p in lj]))
# ---- held / accepted transition (mail 055)
import season_counts as SC, gamelog
G = gamelog.load_games_jsonl(os.path.join(REPO, "data/raw/2026/games.jsonl"))
check("St. John's-Creighton (6624495) is held", "6624495" in SC.held_gids(2026, G))
agg_lejla = [p for p in pl if "epovic" in (p.get("last") or "")]
check("held match's lines are out of the season aggregate (aggregate == page's counted sets)",
      len(agg_lejla) == 1 and lj_sets is not None and (agg_lejla[0].get("sets") or agg_lejla[0].get("gp")) == lj_sets,
      str([(p.get("sets"), p.get("gp")) for p in agg_lejla]))
_orig = SC.corrections
def _with_fix(season):
    c = dict(_orig(season))
    g = [x for x in G if str(x.get("game_id")) == "6624495"][-1]
    cre = [t for t in g["teams"] if t["name_short"] == "Creighton"][0]
    home = [t for t in g["teams"] if t.get("is_home")][0]
    c["6624495"] = {"field": "result", "correct": {"winner_team_id": str(cre["team_id"]),
                    "home_sets": 1 if home["name_short"] != "Creighton" else 3,
                    "away_sets": 3 if home["name_short"] != "Creighton" else 1,
                    "linescores_replace": True, "linescores": []}}
    return c
SC.corrections = _with_fix
try:
    held_after = SC.held_gids(2026, G)
finally:
    SC.corrections = _orig
check("[transition] a ledgered repair makes it ACCEPTED (re-enters automatically)", "6624495" not in held_after)
check("[transition] ...and no other match changes status (no double counting)",
      SC.held_gids(2026, G) - {"6624495"} == held_after)
print("FAILED: %s" % FAIL if FAIL else "ALL POPULATION/IDENTITY CHECKS HOLD"); sys.exit(1 if FAIL else 0)
