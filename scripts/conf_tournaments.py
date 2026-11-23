#!/usr/bin/env python3
"""Conference tournament projections (mail 100). LOCAL/PRIVATE use from build_hub; pure functions, no I/O
except reading the sourced format file and the frozen forecast candidate.

  * brackets come from data/raw/2026/conf_tournaments_2026.json (sourced 2026 formats; status per league)
  * seeds = projected FINAL conference standings (build_hub.project_conf_champions order: projected conference
    win pct, then current conference win pct, then official RPI rank, then name -- published league tiebreakers
    are NOT modelled, stated on the page)
  * each match uses the hub's match model (the frozen Current POWER candidate's calibrated mapping, the same
    cand_win formula predict_2026 uses), with the venue: a named host school is at home when it plays;
    top_seed / first_half_leader -> the No. 1 seed is at home when it plays; higher_seed -> the better seed is at
    home; neutral otherwise. A pair the model cannot rate gets a LABELLED 50/50 fallback, never a seed rule.
  * an actual result overrides the simulation ONLY when it carries tournament provenance bound to a bracket
    round (data/raw/2026/conf_tournament_results.json, validated against the counted final): actual is keyed by
    (round_index, frozenset(teams)), so a regular-season rematch, or a result filed for another round, never applies
  * simulate(): match by match, reproducible seed; an upset changes the later matchup by construction
"""
import json, math, os, random
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(REPO, "data", "raw", "2026", "conf_tournaments_2026.json")
N_SIMS = 10000
SEED = 2026


def load_cfg():
    return json.load(open(CFG))


# ---------------------------------------------------------------- bracket trees
# a node is an int (seed) or a tuple ("m", left, right, round_index)
def _std_order(p):
    order = [1, 2]
    while len(order) < p:
        n = len(order) * 2
        order = [x for s in order for x in (s, n + 1 - s)]
    return order


def build_tree(n, structure="standard"):
    if structure == "bigten15":
        r1 = {10: ("m", 10, 15, 0), 11: ("m", 11, 14, 0), 12: ("m", 12, 13, 0)}
        r2 = {"89": ("m", 8, 9, 1), "5": ("m", 5, r1[12], 1), "6": ("m", 6, r1[11], 1), "7": ("m", 7, r1[10], 1)}
        qf = [("m", 1, r2["89"], 2), ("m", 4, r2["5"], 2), ("m", 3, r2["6"], 2), ("m", 2, r2["7"], 2)]
        return ("m", ("m", qf[0], qf[1], 3), ("m", qf[2], qf[3], 3), 4)
    if structure == "sec16":                    # SEC regulations: 1-4 two byes, 5-8 one bye, 9-16 open (pairings inferred)
        r1 = {9: ("m", 9, 16, 0), 10: ("m", 10, 15, 0), 11: ("m", 11, 14, 0), 12: ("m", 12, 13, 0)}
        r2 = [("m", 8, r1[9], 1), ("m", 5, r1[12], 1), ("m", 6, r1[11], 1), ("m", 7, r1[10], 1)]
        qf = [("m", 1, r2[0], 2), ("m", 4, r2[1], 2), ("m", 3, r2[2], 2), ("m", 2, r2[3], 2)]
        return ("m", ("m", qf[0], qf[1], 3), ("m", qf[2], qf[3], 3), 4)
    if structure == "sunbelt10":                # official 2026 bracket; seeds 1-5 = East 1-5, 6-10 = West 1-5
        m1, m2 = ("m", 9, 5, 0), ("m", 4, 10, 0)          # W4 v E5, E4 v W5
        m3, m4 = ("m", 7, 3, 1), ("m", 1, m1, 1)          # W2 v E3, E1 v M1
        m5, m6 = ("m", 6, m2, 1), ("m", 2, 8, 1)          # W1 v M2, E2 v W3
        return ("m", ("m", m3, m4, 2), ("m", m5, m6, 2), 3)
    if structure == "horizon8":
        r1a, r1b = ("m", 5, 8, 0), ("m", 6, 7, 0)
        r2a, r2b = ("m", 4, r1a, 1), ("m", 3, r1b, 1)
        return ("m", ("m", 1, r2a, 2), ("m", 2, r2b, 2), 3)
    p = 1
    while p < n:
        p *= 2
    slots = [s if s <= n else None for s in _std_order(p)]
    level, rnd = slots, 0
    while len(level) > 1:
        nxt = []
        for a, b in zip(level[0::2], level[1::2]):
            if a is None or b is None:              # a bye: the seeded team advances untouched
                nxt.append(a if b is None else b)
            else:
                nxt.append(("m", a, b, rnd))
        level, rnd = nxt, rnd + 1
    return level[0]


def matches(tree, out=None):
    out = [] if out is None else out
    if isinstance(tree, tuple):
        matches(tree[1], out); matches(tree[2], out); out.append(tree)
    return out


def entry_round(tree, seed, depth=None):
    """round index in which a seed plays its first match"""
    for m in matches(tree):
        if m[1] == seed or m[2] == seed:
            return m[3]
    return None


# ---------------------------------------------------------------- probabilities
def make_prob(cand, host_rule, seeds, nickname=None):
    """returns p(a beats b | seeds) and a counter of fallbacks"""
    T = (cand or {}).get("teams") or {}
    wm = (cand or {}).get("win_model")
    fallbacks = {"n": 0, "pairs": set()}
    def home_of(sa, sb, rnd=None):
        ta, tb = seeds[sa], seeds[sb]
        if host_rule == "r0_higher_then_top":       # first round at the higher seed, later rounds at the No. 1 seed
            if rnd == 0:
                return ta if sa < sb else tb
            return ta if sa == 1 else (tb if sb == 1 else None)
        if host_rule in ("top_seed", "first_half_leader"):
            return ta if sa == 1 else (tb if sb == 1 else None)
        if host_rule == "higher_seed":
            return ta if sa < sb else tb
        if host_rule == "neutral":
            return None
        return host_rule if host_rule in (ta, tb) else None
    def p(sa, sb, rnd=None):
        ta, tb = seeds[sa], seeds[sb]
        if not wm or ta not in T or tb not in T:
            fallbacks["n"] += 1; fallbacks["pairs"].add((ta, tb)); return 0.5
        h = home_of(sa, sb, rnd)
        m = wm; dep = min(1.0, min(T[ta].get("sets", 40), T[tb].get("sets", 40)) / 40.0)
        k = m["b"] + m["c"] * m["s_now"] + m.get("e", 0.0) * dep
        if h is None:
            return 1 / (1 + math.exp(-(k * (T[ta]["theta"] - T[tb]["theta"]))))
        hh, aa = (ta, tb) if h == ta else (tb, ta)
        ph = 1 / (1 + math.exp(-(m["a"] + k * (T[hh]["theta"] - T[aa]["theta"] + (cand.get("home_setshare") or 0.0)))))
        return ph if h == ta else 1 - ph
    return p, fallbacks, home_of


# ---------------------------------------------------------------- simulation
def play(tree, p, rng, actual, seeds, log=None):
    if not isinstance(tree, tuple):
        return tree
    a, b = play(tree[1], p, rng, actual, seeds, log), play(tree[2], p, rng, actual, seeds, log)
    key = (tree[3], frozenset((seeds[a], seeds[b])))
    if key in actual:
        w = a if actual[key] == seeds[a] else b
    else:
        w = a if rng.random() < p(a, b, tree[3]) else b
    if log is not None:
        log.append((tree[3], a, b, w))
    return w


def chalk(tree, p, actual, seeds, log):
    """one internally consistent scenario: the forecast favourite wins every unplayed match"""
    if not isinstance(tree, tuple):
        return tree
    a, b = chalk(tree[1], p, actual, seeds, log), chalk(tree[2], p, actual, seeds, log)
    key = (tree[3], frozenset((seeds[a], seeds[b])))
    pa = p(a, b, tree[3])
    if key in actual:
        w = a if actual[key] == seeds[a] else b; src = "actual"
    else:
        w = a if pa >= 0.5 else b; src = "forecast favourite"
    log.append({"round": tree[3], "a": seeds[a], "sa": a, "b": seeds[b], "sb": b, "p_a": round(pa, 4), "winner": seeds[w], "source": src})
    return w


def frontier(obs, byes=()):
    """What is left of a real bracket, in play order: each entry is a team (already through) or an open pair.
    Byes are placed ahead of each open first-round match, the standard shape for a six-team bracket."""
    last = {}
    for m in obs["matches"]:
        last[m["a"]] = m; last[m["b"]] = m
    seen, slots = set(), []
    for t in obs["alive"]:
        m = last[t]
        if m["game_id"] in seen:
            continue
        seen.add(m["game_id"])
        slots.append((m["epoch"], (m["a"], m["b"]) if not m["winner"] else t))
    slots = [s for _, s in sorted(slots, key=lambda x: (x[0], str(x[1])))]
    if byes:
        mixed = []
        for i, s in enumerate(slots):
            if i < len(byes):
                mixed.append(byes[i])
            mixed.append(s)
        slots = mixed + list(byes[len(slots):])
    return slots


def project_observed(conf, cfg_row, obs, cand, byes=(), n=N_SIMS, seed=SEED):
    """AQ chances from the REAL remaining bracket. Played matches are facts and are never simulated.
    Remaining pairings follow play order (adjacent sessions feed the same next match); returned as inferred."""
    played = [m for m in obs["matches"] if m["winner"]]
    log = [{"round": m["round"], "a": m["a"], "sa": 0, "b": m["b"], "sb": 0, "p_a": None, "winner": m["winner"],
            "source": "actual", "date": m["date"], "sets": m.get("sets"), "game_id": m["game_id"]} for m in played]
    base = {"entry_round": {}, "n_sims": n, "seed": "%s|%s" % (seed, conf), "fallback_pairs": [], "unbound_actuals": [],
            "rounds": max([m["round"] for m in obs["matches"]] or [-1]) + 1}
    champ = obs.get("champion")
    if champ and not obs.get("awaiting_feed"):
        return dict(base, aq_prob={champ: 1.0}, chalk=log, chalk_champion=champ)
    slots = frontier(obs, byes)
    numbered, seeds = [], {}
    def num(t):
        i = len(seeds) + 1; seeds[i] = t; return i
    r0 = base["rounds"]
    for s in slots:
        numbered.append(("m", num(s[0]), num(s[1]), r0) if isinstance(s, tuple) else num(s))
    level, r = numbered, r0 + 1
    while len(level) > 1:
        nxt = [("m", level[i], level[i + 1], r) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level, r = nxt, r + 1
    tree = level[0]
    host = cfg_row.get("host", "neutral")
    host = host if host in seeds.values() else "neutral"       # the real seed order is not known here
    p, fb, _ = make_prob(cand, host, seeds)
    if champ:                                                  # NCAA.com has the result; our crawl has not stored it
        a, b = tree[1], tree[2]
        forced = {(tree[3], frozenset((seeds[a], seeds[b]))): champ}
    else:
        forced = {}
    rng = random.Random("%s|%s" % (seed, conf))
    wins = dict((t, 0) for t in seeds.values())
    for _ in range(n):
        wins[seeds[play(tree, p, rng, forced, seeds)]] += 1
    fut = []
    w = seeds[chalk(tree, p, forced, seeds, fut)]
    for m in fut:
        if m["source"] == "actual":
            m["source"] = "ncaa result, not yet in feed"
    return dict(base, aq_prob=dict((t, wins[t] / float(n)) for t in wins), chalk=log + fut, chalk_champion=w,
                fallback_pairs=sorted(fb["pairs"]))


def project(conf, cfg_row, seeds, cand, actual=None, n=N_SIMS, seed=SEED):
    """seeds: {seed_number: team}. Returns AQ probabilities, the chalk scenario and diagnostics."""
    actual = actual or {}
    tree = build_tree(len(seeds), cfg_row.get("structure", "standard"))
    host = cfg_row.get("host", "neutral")
    p, fb, home_of = make_prob(cand, host, seeds)
    rng = random.Random("%s|%s" % (seed, conf))
    wins = dict((t, 0) for t in seeds.values())
    for _ in range(n):
        wins[seeds[play(tree, p, rng, actual, seeds)]] += 1
    log = []
    champ = seeds[chalk(tree, p, actual, seeds, log)]
    entry = dict((seeds[s], entry_round(tree, s)) for s in seeds)
    used = set((m["round"], frozenset((m["a"], m["b"]))) for m in log if m["source"] == "actual")
    unbound = [{"round": k[0], "teams": sorted(k[1])} for k in actual if k not in used]
    return {"aq_prob": dict((t, wins[t] / float(n)) for t in wins), "chalk": log, "chalk_champion": champ,
            "entry_round": entry, "n_sims": n, "seed": "%s|%s" % (seed, conf), "fallback_pairs": sorted(fb["pairs"]), "unbound_actuals": unbound,
            "rounds": max(m[3] for m in matches(tree)) + 1 if matches(tree) else 0}
