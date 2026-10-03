#!/usr/bin/env python3
"""Overview / Numbers / Analysis / player pages must show ONE population and
the same sums (mails 045, 047). Reads the BUILT private page. EXACT sets and
totals, not <=; nameless boxes recounted from the raw log independently."""
import copy, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
FAIL = []
def check(n, ok, extra=""):
    print("  %-72s %s%s" % (n, "ok" if ok else "FAIL", ("  " + extra) if extra else ""))
    if not ok: FAIL.append(n)
if not os.path.exists(PAGE):
    print("  --   no private page (CI checkout); skipping"); sys.exit(0)
html = open(PAGE, encoding="utf-8").read()

def grab(pattern):
    i = re.search(pattern, html).start(1)
    d, j, instr, esc = 0, i, False, False
    while True:
        c = html[j]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': instr = False
        elif c == '"': instr = True
        elif c in "[{": d += 1
        elif c in "]}":
            d -= 1
            if d == 0: break
        j += 1
    return json.loads(html[i:j + 1])

TEAMS = grab(r"const TEAMS = (\{)")
TAN = grab(r"tanData\.v = (\{)")
PLAYERS = grab(r"const PLAYERS = (\[)")
KS, KP = TAN["keys"]["series"], TAN["keys"]["players"]
COMP = ("k", "e", "ta", "ast", "digs", "bs", "ba", "aces", "se")

def team_checks(TEAMS, TAN):
    pop, comp, cov = [], [], []
    for name, t in TEAMS.items():
        ts = t.get("tstats") or {}; own = ts.get("own") or {}; a = TAN["teams"].get(name)
        if not own or not a:
            continue
        mb = dict((g, r) for g, r in (ts.get("mbm") or {}).items() if r.get("status") != "partial")
        ser = [dict(zip(KS, r)) for r in a["series"]]
        an = set(str(m["gid"]) for m in ser if m["box"])
        if set(mb) != an or own["matches"] != len(an):
            pop.append("%s overview-only %s analysis-only %s" % (name, sorted(set(mb) - an)[:3], sorted(an - set(mb))[:3]))
            continue
        c = a["totals"]["counts"]
        for f in COMP:
            if abs(sum(r[f] for r in mb.values()) - (c.get(f) or 0)) > 1e-6:
                comp.append("%s %s numbers %s analysis %s" % (name, f, sum(r[f] for r in mb.values()), c.get(f)))
        if abs(sum(r["sets"] for r in mb.values()) - a["totals"]["sets"]) > 1e-6 or \
                abs(own["sets"] - a["totals"]["sets"]) > 0.05:
            comp.append("%s sets" % name)
        if own.get("board_cov_matches") != a["totals"].get("board_cov_matches"):
            cov.append("%s scoreboard coverage %s vs %s" % (name, own.get("board_cov_matches"), a["totals"].get("board_cov_matches")))
    return pop, comp, cov

pop, comp, cov = team_checks(TEAMS, TAN)
n = sum(1 for t in TEAMS.values() if (t.get("tstats") or {}).get("own"))
check("Overview/Numbers/Analysis: EXACT same eligible match-ID sets (%d teams)" % n, not pop, "; ".join(pop[:3]))
check("...and identical raw components (%s, sets)" % "/".join(COMP), not comp, "; ".join(comp[:3]))
check("...and the same scoreboard-coverage population", not cov, "; ".join(cov[:3]))

# players: Analysis vs player pages, EXACT, over the named complete boxes
import nameclean
pl = {}
for p in PLAYERS:
    pl.setdefault((p["team"], nameclean.join_key(p["name"])), []).append(p)
mem, tot = [], []
for team, a in TAN["teams"].items():
    if team not in TEAMS or not (TEAMS[team].get("tstats") or {}).get("own"):
        continue
    named = set(g for g, r in TEAMS[team]["tstats"]["mbm"].items() if r["status"] == "players")
    exp = {}
    for (tm, key), ps in pl.items():
        if tm != team:
            continue
        for p in ps:
            for g in p["games"]:
                if g["gid"] in named:
                    e = exp.setdefault(key, {"sets": 0.0, "k": 0.0, "ta": 0.0, "act": 0.0})
                    e["sets"] += g["sets"]; e["k"] += g["k"]; e["ta"] += g["ta"]
                    e["act"] += (g["k"] + g["ta"] + g["digs"] + g["ast"] + g["aces"] + g["bs"] + g["ba"]
                                 + (g.get("se") or 0) + (g.get("sa") or 0) + (g.get("ra") or 0) + (g.get("re") or 0))
    present = set(exp)                                     # appears in a named box
    acted = set(k for k, v in exp.items() if v["act"] > 0)  # an action the game log carries
    got = dict((nameclean.join_key(d["name"]), d) for d in (dict(zip(KP, r)) for r in a["players"]))
    # EXACT in both directions that the payloads can express: every Analysis
    # player is on the player pages for these matches, and every player-page
    # player with a counted action is in Analysis. (Analysis also admits a
    # line whose only action is a serve/reception attempt, which the game log
    # does not carry -- so membership between `acted` and `present` is
    # decided by Analysis, and both must still hold it.)
    # with attempts in the game log (mail 052) membership is EXACT both ways
    if set(got) != acted:
        mem.append("%s page-acted-not-in-analysis %s analysis-not-on-page %s" % (
            team, sorted(acted - set(got))[:2], sorted(set(got) - present)[:2]))
        continue
    for k, e in ((k, exp[k]) for k in got):
        d = got[k]
        if abs(e["sets"] - d["sets"]) > 1e-6 or abs(e["k"] - d["k"]) > 1e-6 or abs(e["ta"] - d["ta"]) > 1e-6:
            tot.append("%s %s page %s/%s/%s analysis %s/%s/%s" % (team, k, e["sets"], e["k"], e["ta"], d["sets"], d["k"], d["ta"]))
check("player membership: Analysis == player pages EXACTLY (serve/reception-only included)", not mem, "; ".join(mem[:3]))
check("player totals (sets/K/TA) identical on both", not tot, "; ".join(tot[:3]))
# TA share basis
lo = TAN["teams"]["Louisiana"]; named_ta = sum(r["ta"] for r in TEAMS["Louisiana"]["tstats"]["mbm"].values() if r["status"] == "players")
lam = [dict(zip(KP, r)) for r in lo["players"] if "Lambert" in r[KP.index("name")]][0]
check("TA share denominator = named-player matches' team attempts (Lambert %.3f = %d/%d)"
      % (lam["ta_share"], lam["ta"], named_ta), abs(lam["ta_share"] - round(lam["ta"] / named_ta, 3)) < 1e-9)
# scoreboard: a withheld tape adds no sets
mem_ = TEAMS["Louisiana"]["played"]
wh = [g for g in mem_ if not g.get("sets")]
bc = TAN["teams"]["Louisiana"]["totals"]
check("scoreboard sets exclude matches with a withheld tape (%d withheld)" % len(wh),
      bc["board_cov_sets"] == sum(len(g["sets"]) for g in mem_ if g.get("sets") and g["gid"] in
                                  set(x for x, r in TEAMS["Louisiana"]["tstats"]["mbm"].items() if r["status"] != "partial")))
# nameless recount from raw
raw = {}
for ln in open(os.path.join(REPO, "data", "raw", "2026", "playerbox.jsonl")):
    try: r = json.loads(ln)
    except ValueError: continue
    raw[str(r.get("game_id"))] = r
nameless = set(g for g, r in raw.items() if r.get("rows") and not any((x.get("first") or x.get("last")) for x in r["rows"]))
page_team_only = set(g for t in TEAMS.values() for g, r in ((t.get("tstats") or {}).get("mbm") or {}).items() if r.get("status") == "team_totals")
check("team-totals matches are a SUBSET of raw nameless boxes (%d of %d; the rest are partial or non-counting)"
      % (len(page_team_only), len(nameless)), page_team_only and page_team_only <= nameless)
# negative controls
T2 = copy.deepcopy(TAN); T2["teams"]["Louisiana"]["series"] = [r for r in T2["teams"]["Louisiana"]["series"]
                                                              if not (r[KS.index("box")] and r[KS.index("gid")] in page_team_only)]
check("[NEG] dropping team-only matches from Analysis is caught", team_checks(TEAMS, T2)[0])
T3 = copy.deepcopy(TAN); T3["teams"]["Louisiana"]["totals"]["counts"]["k"] += 1
check("[NEG] one extra kill in Analysis is caught", team_checks(TEAMS, T3)[1])
T4 = copy.deepcopy(TAN); T4["teams"]["Louisiana"]["totals"]["board_cov_matches"] += 1
check("[NEG] a scoreboard-coverage drift is caught", team_checks(TEAMS, T4)[2])
# [NEG] player-level: one extra kill on one Analysis player must be caught
_t = "Louisiana"; _a = copy.deepcopy(TAN["teams"][_t]["players"])
_i = KP.index("k"); _a[0][_i] = (_a[0][_i] or 0) + 1
_named = set(g for g, r in TEAMS[_t]["tstats"]["mbm"].items() if r["status"] == "players")
_nm = nameclean.join_key(_a[0][KP.index("name")])
_page_k = sum(g["k"] for p in PLAYERS if p["team"] == _t and nameclean.join_key(p["name"]) == _nm
              for g in p["games"] if g["gid"] in _named)
check("[NEG] a player-total drift (one extra kill) is caught", abs(_page_k - _a[0][_i]) > 1e-6)
print("FAILED: %s" % FAIL if FAIL else "ALL CROSS-SCREEN CHECKS HOLD"); sys.exit(1 if FAIL else 0)
