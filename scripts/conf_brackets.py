#!/usr/bin/env python3
"""Real conference-tournament brackets (Cody, 2026-11-23). Pure functions; no I/O.

Seeds. The feed publishes none. A league's bracket has a known shape and its real matches show who met whom, so the
seed order is the assignment closest to the final conference standings that places EVERY real match on a node of
that shape. Ties in the standings resolve themselves wherever the pairings distinguish them. A league whose real
matches fit no assignment gets no seed numbers: its bracket is drawn from the matches alone and says so.

A node is conf_tournaments' ("m", left, right, round_index); a leaf is a seed number.
"""
import conf_tournaments as CT


def _prev_links(ms):
    """for each match, each team's previous match in this tournament (None = its first)"""
    last, out = {}, {}
    for m in sorted(ms, key=lambda x: (x["epoch"], str(x["game_id"]))):
        out[m["game_id"]] = (last.get(m["a"]), last.get(m["b"]))
        last[m["a"]] = last[m["b"]] = m["game_id"]
    return out


def fit_seeds(tree, n, ms, standing):
    """Returns (seeds {seed: team}, node_of {game_id: node}, cost), or None when no assignment fits."""
    ms = sorted(ms, key=lambda x: (x["epoch"], str(x["game_id"])))
    teams = set(t for m in ms for t in (m["a"], m["b"]))
    if len(teams) > n or len(ms) > max(0, n - 1):
        return None
    prev = _prev_links(ms)
    # a team absent from the standings sorts last rather than breaking the fit
    pos = dict((t, i + 1) for i, t in enumerate(standing))
    order = list(standing) + sorted(teams - set(standing))
    for i, t in enumerate(order):
        pos.setdefault(t, i + 1)
    nodes = CT.matches(tree)
    best = [None, float("inf")]
    def compat(child, team, prev_gid, seed_of, team_of, node_of):
        if prev_gid is not None:
            return isinstance(child, tuple) and node_of.get(prev_gid) is child
        if isinstance(child, tuple):
            return False
        if child in team_of:
            return team_of[child] == team
        return team not in seed_of
    def walk(i, seed_of, team_of, node_of, used, cost):
        if cost >= best[1]:
            return
        if i == len(ms):
            s, c = dict(team_of), cost
            rest = [t for t in order if t not in seed_of]
            free = [k for k in range(1, n + 1) if k not in s]
            if len(rest) < len(free):
                return
            for k, t in zip(free, rest):
                s[k] = t; c += (k - pos[t]) ** 2
            if c < best[1]:
                best[0], best[1] = (s, dict(node_of)), c
            return
        m = ms[i]
        pa, pb = prev[m["game_id"]]
        for T in nodes:
            if id(T) in used:
                continue
            for ca, cb in ((T[1], T[2]), (T[2], T[1])):
                if not compat(ca, m["a"], pa, seed_of, team_of, node_of) or not compat(cb, m["b"], pb, seed_of, team_of, node_of):
                    continue
                added, c2 = [], cost
                for ch, t, pv in ((ca, m["a"], pa), (cb, m["b"], pb)):
                    if pv is None and ch not in team_of:
                        team_of[ch] = t; seed_of[t] = ch; added.append((ch, t)); c2 += (ch - pos[t]) ** 2
                node_of[m["game_id"]] = T; used.add(id(T))
                walk(i + 1, seed_of, team_of, node_of, used, c2)
                used.discard(id(T)); del node_of[m["game_id"]]
                for ch, t in added:
                    del team_of[ch]; del seed_of[t]
    walk(0, {}, {}, {}, set(), 0)
    if best[0] is None:
        return None
    return best[0][0], best[0][1], best[1]


def template(n, structure):
    """the league's bracket shape; a named shape applies only at its own field size"""
    sized = {"bigten15": 15, "sec16": 16, "sunbelt10": 10, "horizon8": 8}
    return CT.build_tree(n, structure if sized.get(structure) == n else "standard")


# ---------------------------------------------------------------- the bracket, simulated from what is left
N_SIMS = 10000
ROUND_NAMES = ["Final", "Semifinals", "Quarterfinals", "Second round", "First round"]


def round_label(depth_from_final, total):
    if depth_from_final <= 2:
        return ROUND_NAMES[depth_from_final]
    n = total - depth_from_final
    return {1: "First round", 2: "Second round"}.get(n, "Round %d" % n)


def _depth(node):
    return 0 if not isinstance(node, tuple) else 1 + max(_depth(node[1]), _depth(node[2]))


def _host_for(row, seeds):
    host = row.get("host", "neutral")
    if host in ("neutral", "top_seed", "higher_seed", "first_half_leader", "r0_higher_then_top"):
        return host
    return host if host in seeds.values() else "neutral"


def build(cname, row, obs, standing, cand, records=None, conf_records=None, seeds=None, n=N_SIMS, seed=2026):
    """One league's bracket from its real results. Returns None when the real matches fit no seed assignment."""
    records, conf_records = records or {}, conf_records or {}
    ms = list((obs or {}).get("matches") or [])
    if seeds:
        size = len(seeds)
        tree = template(size, row.get("structure"))
        node_of = {}
    else:
        size = obs["field"]
        tree = template(size, row.get("structure"))
        fit = fit_seeds(tree, size, ms, standing)
        if not fit:
            return None
        seeds, node_of, _ = fit
    sd_of = dict((t, s) for s, t in seeds.items())
    host = _host_for(row, seeds)
    p0, fb, _ = CT.make_prob(cand, host, seeds)
    cache = {}
    def p(a, b, r):
        k = (a, b, r)
        if k not in cache:
            cache[k] = p0(a, b, r)
        return cache[k]
    forced, m_at = {}, {}
    for m in ms:
        T = node_of.get(m["game_id"])
        if T is None:
            continue
        m_at[id(T)] = m
        if m["winner"]:
            forced[id(T)] = sd_of[m["winner"]]
    champ = (obs or {}).get("champion")
    if champ and (obs or {}).get("awaiting_feed") and champ in sd_of:
        forced[id(tree)] = sd_of[champ]
    nodes = CT.matches(tree)
    reach = dict((id(T), {}) for T in nodes)
    wins = dict((id(T), {}) for T in nodes)
    def once(rng, node, out=None):
        if not isinstance(node, tuple):
            return node
        a, b = once(rng, node[1], out), once(rng, node[2], out)
        f = forced.get(id(node))
        if f in (a, b):
            w = f
        else:
            w = a if rng.random() < p(a, b, node[3]) else b
            if out is not None:
                out.append((seeds[w], seeds[b if w == a else a]))
        if out is None:
            rn, wn = reach[id(node)], wins[id(node)]
            rn[a] = rn.get(a, 0) + 1; rn[b] = rn.get(b, 0) + 1; wn[w] = wn.get(w, 0) + 1
        return w
    rng = __import__("random").Random("%s|%s|bracket" % (seed, cname))
    for _ in range(n):
        once(rng, tree)
    aq_prob = dict((seeds[s], c / float(n)) for s, c in wins[id(tree)].items())
    favourite = seeds[max(wins[id(tree)], key=lambda s: (wins[id(tree)][s], -s))]
    # the single scenario: the likeliest champion wins through; everywhere else the favourite wins
    fav_sd = sd_of[favourite]
    log = []
    def contains(node, s):
        return node == s if not isinstance(node, tuple) else contains(node[1], s) or contains(node[2], s)
    def scen(node):
        if not isinstance(node, tuple):
            return node
        a, b = scen(node[1]), scen(node[2])
        pa = p(a, b, node[3])
        f = forced.get(id(node))
        m = m_at.get(id(node))
        if f in (a, b):
            w = f
            src = "actual" if m and m.get("winner") else "ncaa result, not yet in feed"
        else:
            w = fav_sd if fav_sd in (a, b) else (a if pa >= 0.5 else b)
            src = "forecast favourite"
        e = {"round": node[3], "a": seeds[a], "sa": a, "b": seeds[b], "sb": b, "p_a": round(pa, 4), "winner": seeds[w], "source": src}
        if m:
            e.update(date=m["date"], sets=m.get("sets"), game_id=m["game_id"])
        log.append(e)
        return w
    scen(tree)
    total = _depth(tree)
    def slot(child, node):
        """who is in this side of the match: a known team, or the likeliest entrant"""
        s = child if not isinstance(child, tuple) else forced.get(id(child))
        known = s is not None
        if not known:
            r = dict((k, v) for k, v in reach[id(node)].items() if contains(child, k))
            s = max(r, key=lambda k: (r[k], -k))
        t = seeds[s]
        return {"team": t, "seed": s, "known": known, "rec": records.get(t), "conf_rec": conf_records.get(t),
                "win": wins[id(node)].get(s, 0) / float(n)}
    def draw(node, depth):
        if not isinstance(node, tuple):
            return None
        m = m_at.get(id(node))
        L, R = slot(node[1], node), slot(node[2], node)
        state = "future"
        if id(node) in forced:
            state = "final"
        elif m:
            state = "live" if m.get("state") == "I" else "upcoming"
        elif L["known"] and R["known"]:
            state = "upcoming"
        win_i, sets = None, None
        if id(node) in forced:
            win_i = 0 if seeds[forced[id(node)]] == L["team"] else 1
        if m and m.get("sets") and len(m["sets"]) == 2:
            sets = list(m["sets"]) if m["a"] == L["team"] else list(reversed(m["sets"]))
        return {"round_label": round_label(depth, total), "depth": depth, "state": state, "date": (m or {}).get("date"),
                "slots": [L, R], "winner": win_i, "sets": sets, "game_id": (m or {}).get("game_id"),
                "kids": [draw(node[1], depth + 1), draw(node[2], depth + 1)]}
    def sampler(r):
        out = []
        w = once(r, tree, out)
        return seeds[w], out
    return {"seeds": seeds, "aq_prob": aq_prob, "favourite": favourite, "chalk": log, "bracket": draw(tree, 0), "rounds": total,
            "round_labels": [round_label(d, total) for d in range(total - 1, -1, -1)], "n_sims": n,
            "fallback_pairs": sorted(fb["pairs"]), "sampler": sampler, "decided": bool(forced.get(id(tree)))}


# ---------------------------------------------------------------- full-field bid odds
def regular_champion(rec, h2h, new, rank, eligible):
    """One simulated finish of a regular-season race. rec {team: (w, l)} is the league table now; new is this run's
    simulated results. Best conference win percentage takes it; a tie goes to head-to-head among the tied teams
    (real and simulated meetings), then to the better RPI rank in this run. Ineligible teams are skipped."""
    w = dict((t, float(x[0])) for t, x in rec.items()); n = dict((t, float(x[0] + x[1])) for t, x in rec.items())
    for a, b in new:
        if a in w and b in w:
            w[a] += 1; n[a] += 1; n[b] += 1
    pool = [t for t in rec if t in eligible and n[t]]
    if not pool:
        return None
    best = max(w[t] / n[t] for t in pool)
    tied = [t for t in pool if abs(w[t] / n[t] - best) < 1e-9]
    if len(tied) > 1:
        ts = set(tied); hw = dict((t, 0) for t in tied)
        for a, b in list(h2h) + list(new):
            if a in ts and b in ts:
                hw[a] += 1
        top = max(hw.values()); tied = [t for t in tied if hw[t] == top]
    return min(tied, key=lambda t: (rank(t), t))


def bid_odds(games, nondi, keys, conf, future, samplers, fixed_aq, eligible, recs, min_pct, min_di, n=2000, seed=2026,
             regular=None):
    """Play every remaining match n times; in each run recompute the committee-format RPI and select the field by the
    hub's rule: each league's champion takes its bid, then at-large by rank - 2 x top-25 wins - 1 x top-50 wins, with
    the .500 and 80% D-I gates. Returns {team key: {"aq","al","in"}} as shares of runs."""
    import random
    import numpy as np
    import rpi_committee as RC
    from reconcile_2025 import norm
    keys = list(keys)
    ix = dict((k, i) for i, k in enumerate(keys))
    W0 = np.array([ix[w] for w, l, _ in games], dtype=int)
    L0 = np.array([ix[l] for w, l, _ in games], dtype=int)
    nt = len(keys)
    base_w = np.array([recs.get(k, {}).get("w", 0) for k in keys], dtype=float)
    base_n = np.array([recs.get(k, {}).get("n", 0) for k in keys], dtype=float)
    base_di = np.array([recs.get(k, {}).get("di", 0) for k in keys], dtype=float)
    elig = np.array([k in eligible for k in keys], dtype=bool)
    aq_ct, al_ct = np.zeros(nt, dtype=int), np.zeros(nt, dtype=int)
    rng = random.Random("%s|bid-odds" % seed)
    for it in range(n):
        new = []
        for h, a, ph in future:
            if h in ix and a in ix:
                new.append((h, a) if rng.random() < ph else (a, h))
        aq = dict(fixed_aq)
        for ck, smp in samplers.items():
            champ, ms = smp(rng)
            new.extend((norm(w), norm(l)) for w, l in ms)
            if norm(champ) in eligible:
                aq[ck] = norm(champ)
        new = [(w, l) for w, l in new if w in ix and l in ix]
        r = RC.adjust(games + [(w, l, "s%d" % i) for i, (w, l) in enumerate(new)], nondi, keys, conf)
        rank = np.array([r[k]["rank"] for k in keys])
        for ck, rg in (regular or {}).items():
            champ = regular_champion(rg["rec"], rg["h2h"], new, lambda t: r[t]["rank"] if t in r else 999, eligible)
            if champ:
                aq[ck] = champ
        Wn = np.array([ix[w] for w, _ in new], dtype=int)
        Ln = np.array([ix[l] for _, l in new], dtype=int)
        W, L = np.concatenate([W0, Wn]), np.concatenate([L0, Ln])
        t25 = np.bincount(W[rank[L] <= 25], minlength=nt)
        t50 = np.bincount(W[rank[L] <= 50], minlength=nt)
        wins = base_w + np.bincount(Wn, minlength=nt)
        played = base_n + np.bincount(Wn, minlength=nt) + np.bincount(Ln, minlength=nt)
        di = base_di + np.bincount(Wn, minlength=nt) + np.bincount(Ln, minlength=nt)
        ok = elig & (played > 0)
        ok &= np.divide(wins, played, out=np.zeros(nt), where=played > 0) >= min_pct
        ok &= np.divide(di, played, out=np.zeros(nt), where=played > 0) >= min_di
        aq_i = sorted(set(ix[t] for t in aq.values() if t in ix))
        aq_ct[aq_i] += 1
        ok[aq_i] = False
        pool = np.nonzero(ok)[0]
        score = rank - 2.0 * t25 - 1.0 * t50
        order = pool[np.lexsort((rank[pool], score[pool]))]
        al_ct[order[:64 - len(aq_i)]] += 1
    return dict((k, {"aq": aq_ct[i] / float(n), "al": al_ct[i] / float(n), "in": (aq_ct[i] + al_ct[i]) / float(n)})
                for i, k in enumerate(keys) if aq_ct[i] or al_ct[i])
