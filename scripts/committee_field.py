#!/usr/bin/env python3
"""mail 104: a simple COMMITTEE-INFORMED projected field and bracket (LOCAL/PRIVATE).

Three separate steps, kept separate on the page:
  1. FIELD SELECTION -- the post-conference-tournament scenario's AQs and at-large gates (the same scenario the
     RPI Cut Line's post view uses), with at-large order by the hub's EXISTING quality-win rule
     (project_field.resume_score): ranking position - 2 x top-25 wins - 1 x top-50 wins, ties by the ranking.
     A transparent baseline, not the committee's weights. Every swap against the pure RPI field is explained with
     supporting evidence (significant losses, head-to-head, common opponents) -- evidence only, it changes nothing.
  2. SEED LINES -- the 2026 manual (Section 2.3): the top 32 are seeded in four sets of lines 1-8; the top 16, in
     rank order, take lines 1-4. Our order for the 32 = the same quality score.
  3. PLACEMENT -- approximated. Line 1-4 teams go to regions by the BALANCED top-16 grouping the official 2025
     bracket shows (TOP16_REGIONS: regions of overall #1..#4 hold [1,8,9,16] [2,7,10,15] [3,6,11,14] [4,5,12,13];
     a 2025-based convention supported by the official bracket -- the manual fixes the groups, it does not spell
     out a snake -- mail 115); lines 5-8 and the
     unseeded 32 are assigned to first/second-round pods by approximate distance (state centre to state centre),
     with first- and second-round conference matchups avoided (manual 2.3 and 2.5). Host bids are not known: every
     top-16 seed is assumed to host its pod and lines 1 the regionals.
Pure functions over the cut-line payload; the only I/O is reading the raw game log for home locations."""
import collections, json, math, os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# approximate geographic centre of each state (degrees); an APPROXIMATION used only to rank distances
STATE_LL = {
    "AL": (32.8, -86.8), "AK": (64.2, -149.5), "AZ": (34.3, -111.7), "AR": (34.9, -92.4), "CA": (37.2, -119.5),
    "CO": (39.0, -105.5), "CT": (41.6, -72.7), "DE": (39.0, -75.5), "DC": (38.9, -77.0), "FL": (28.6, -82.4),
    "GA": (32.7, -83.4), "HI": (20.8, -156.3), "ID": (44.4, -114.6), "IL": (40.0, -89.2), "IN": (39.9, -86.3),
    "IA": (42.1, -93.5), "KS": (38.5, -98.4), "KY": (37.5, -85.3), "LA": (31.1, -92.0), "ME": (45.4, -69.2),
    "MD": (39.0, -76.8), "MA": (42.3, -71.8), "MI": (44.3, -85.4), "MN": (46.3, -94.3), "MS": (32.7, -89.7),
    "MO": (38.4, -92.5), "MT": (47.0, -109.6), "NE": (41.5, -99.8), "NV": (39.3, -116.6), "NH": (43.7, -71.6),
    "NJ": (40.2, -74.7), "NM": (34.4, -106.1), "NY": (42.9, -75.5), "NC": (35.6, -79.4), "ND": (47.5, -100.5),
    "OH": (40.3, -82.8), "OK": (35.6, -97.5), "OR": (43.9, -120.6), "PA": (40.9, -77.8), "RI": (41.7, -71.5),
    "SC": (33.9, -80.9), "SD": (44.4, -100.2), "TN": (35.9, -86.4), "TX": (31.5, -99.3), "UT": (39.3, -111.7),
    "VT": (44.1, -72.7), "VA": (37.5, -78.9), "WA": (47.4, -120.5), "WV": (38.6, -80.6), "WI": (44.6, -89.9),
    "WY": (43.0, -107.6), "PR": (18.2, -66.5),
}
LINE_ORDER = [1, 8, 5, 4, 3, 6, 7, 2]       # the bracket's line order inside a quadrant (renderBracket's)
QUAD_OF_POS = [0, 3, 2, 1]                  # REGION ORIENTATION: overall 1 -> Q0, 2 -> Q3, 3 -> Q2, 4 -> Q1 (renderBracket's)
# mail 115: WHICH top-16 teams share a region. Read off the OFFICIAL 2025 bracket (Cody's 2025-2.pdf) against the
# committee's published overall order (2025 field release, p.4): Nebraska's region held overall 1, 8, 9 and 16
# (Louisville, Texas A&M, Kansas), Kentucky's 2, 7, 10, 15, Texas's 3, 6, 11, 14, Pittsburgh's 4, 5, 12, 13 -- all
# 16 slots verified, sources in research/sources/2025-ncaa-wvb-bracket/. It replaces the earlier repeated order
# (1/5/9/13 together), which put the strongest team of every line in #1's region. Region i of this table is the
# region of overall #(i+1), oriented by QUAD_OF_POS. Lines 5-8 and the unseeded are NOT snaked: they keep the
# geographic, conference-separated assignment within their fixed groups (the release: "assigned geographically").
TOP16_REGIONS = ((1, 8, 9, 16), (2, 7, 10, 15), (3, 6, 11, 14), (4, 5, 12, 13))
REGION_OF_OVERALL = {o: i for i, grp in enumerate(TOP16_REGIONS) for o in grp}
CONFLICT = 1e6                              # a same-conference first/second-round meeting


def _norm(x):
    from reconcile_2025 import norm
    return norm(x or "")


_HOME = None


def home_states():
    """team(norm) -> (state, city, n): where a team plays its home matches, from the raw game log -- each GAME counted
    once (any record of it that carries a location; later records of a final often drop the field). Accepted only
    when CLEAR: at least two home matches in that state and at least twice the next state. The feed tags neutral
    showcases as 'home' (Nebraska: one match each in Lincoln, Las Vegas and Arlington), so anything less is unknown,
    never guessed."""
    global _HOME
    if _HOME is not None:
        return _HOME
    loc, home = {}, {}
    pth = os.path.join(REPO, "data", "raw", "2026", "games.jsonl")
    for ln in open(pth, encoding="utf-8"):
        try:
            g = json.loads(ln)
        except ValueError:
            continue
        gid = str(g.get("game_id")); l = g.get("location") or {}
        s = l.get("stateUsps") or l.get("state")
        if s:
            loc[gid] = (s, l.get("city"))
        for t in g.get("teams") or []:
            if t.get("is_home"):
                home[gid] = _norm(t.get("name_short"))
    c = collections.defaultdict(collections.Counter)
    for gid, h in home.items():
        if gid in loc:
            c[h][loc[gid][0]] += 1
    out = {}
    for k, v in c.items():
        m = v.most_common(2)
        if m[0][1] >= 2 and (len(m) == 1 or m[0][1] >= 2 * m[1][1]):
            out[k] = (m[0][0], None, m[0][1])
    _HOME = out
    return out


def miles(a, b):
    """approximate miles between two teams' home STATES; None when either is unknown."""
    hs = home_states()
    sa, sb = hs.get(_norm(a)), hs.get(_norm(b))
    if not sa or not sb or sa[0] not in STATE_LL or sb[0] not in STATE_LL:
        return None
    (la1, lo1), (la2, lo2) = STATE_LL[sa[0]], STATE_LL[sb[0]]
    p1, p2 = math.radians(la1), math.radians(la2)
    d = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 3959 * 2 * math.asin(math.sqrt(d))


def quality(res, ranks):
    """top-25 / top-50 wins and sub-100 losses, split actual vs projected (opponent ranks = the scenario's)."""
    q = {"t25w": [0, 0], "t50w": [0, 0], "l100": [0, 0], "wins_of_note": [], "bad_losses": []}
    for kind, rows in (("actual", res.get("actual") or []), ("proj", res.get("proj") or [])):
        i = 0 if kind == "actual" else 1
        for m in rows:
            r = m[4]
            if m[2] == "W" and r and r <= 25:
                q["t25w"][i] += 1
            if m[2] == "W" and r and r <= 50:
                q["t50w"][i] += 1
                q["wins_of_note"].append((r, m[1], kind))
            if m[2] == "L" and (not r or r > 100) and m[5]:
                q["l100"][i] += 1
                q["bad_losses"].append((r, m[1], kind))
            if m[2] == "L" and not m[5]:
                q["l100"][i] += 1
                q["bad_losses"].append((None, m[1] + " (non-D-I)", kind))
    q["wins_of_note"].sort(); q["bad_losses"].sort(key=lambda x: -(x[0] or 999))
    return q


def score(rank, q):
    """the hub's existing quality-win rule (project_field.resume_score), on this scenario's ranking."""
    return rank - 2.0 * sum(q["t25w"]) - 1.0 * sum(q["t50w"])


def _h2h(ra, b):
    return [m for m in (ra.get("actual") or []) if m[1] == b]


def _common(ra, rb, a, b):
    oa, ob = collections.defaultdict(list), collections.defaultdict(list)
    for m in ra.get("actual") or []:
        if m[1] != b:
            oa[m[1]].append(m)
    for m in rb.get("actual") or []:
        if m[1] != a:
            ob[m[1]].append(m)
    com = sorted(set(oa) & set(ob))
    wa = sum(1 for k in com for m in oa[k] if m[2] == "W"); la = sum(1 for k in com for m in oa[k] if m[2] == "L")
    wb = sum(1 for k in com for m in ob[k] if m[2] == "W"); lb = sum(1 for k in com for m in ob[k] if m[2] == "L")
    return com, (wa, la), (wb, lb)


def _qtxt(q):
    t25, t50, l1 = q["t25w"], q["t50w"], q["l100"]
    def part(v, word):
        s = "%d %s" % (sum(v), word)
        return s + (" (%d still projected)" % v[1] if v[1] else "")
    return "%s, %s, %s" % (part(t25, "top-25 wins"), part(t50, "top-50 wins"), part(l1, "losses outside the top 100"))


RANK_LABEL = {"projected": "Projected RPI", "provisional": "Projected RPI",
              "official": "official RPI", "complete_base": "complete RPI"}


def completeness(left, disposition, ct_payload, today):
    """mail 105: AFFIRMATIVE season completeness. Zero remaining forecasts proves nothing on its own (a missing or stale
    forecast file also gives zero). Complete only when ALL hold: no forecast match left; the fixture-disposition
    artifact is from today and lists no scheduled/live or unknown fixture; every conference-tournament match is an
    actual, ledger-bound result. Returns (complete, reasons-not-complete)."""
    why = []
    if left:
        why.append("%d matches are still forecast" % left)
    d = disposition or {}
    if not d:
        why.append("no fixture-disposition artifact")
    else:
        if str(d.get("as_of")) != str(today):
            why.append("fixture disposition is from %s, not today (%s)" % (d.get("as_of"), today))
        cnt = d.get("counts") or {}
        if cnt.get("scheduled_or_live"):
            why.append("%d fixtures still scheduled or live" % cnt["scheduled_or_live"])
        if cnt.get("unknown"):
            why.append("%d fixtures with unknown status" % cnt["unknown"])
    if not ct_payload:
        why.append("no conference-tournament projection")
    else:
        bad = [k for k, v in ct_payload.items() if v.get("error")]
        open_ = sum(1 for v in ct_payload.values() if not v.get("error") for m in v.get("chalk") or [] if m.get("source") != "actual")
        if bad:
            why.append("conference tournaments without a bracket: %s" % ", ".join(bad))
        if open_:
            why.append("%d conference-tournament matches not yet played and verified" % open_)
    return (not why), why


def basis_for(complete, through_date, last_final):
    """projected/provisional while incomplete; once complete, official only when its through-date covers the last final."""
    if not complete:
        return "provisional"
    if through_date and last_final and str(through_date) >= str(last_final):
        return "official"
    return "complete_base"


def select(c, basis="projected"):
    """c: the post-tournament cut-line payload. Returns the committee-informed field and the swap explanations."""
    ranks, res = c["ranks_all"], c["resumes"]
    lab = RANK_LABEL.get(basis, "Projected RPI")
    missing = [t for t in c["al_pool"] if t not in res]
    if missing:
        # a display limit must never be a selection limit: withhold the field rather than select from part of the pool
        raise ValueError("resumes missing for %d eligible at-large candidates (%s); committee field withheld"
                         % (len(missing), ", ".join(missing[:5])))
    aqs = list(c["aq_teams"])
    n_al = 64 - len(aqs) - len(c.get("unresolved_aq") or [])
    pool = list(c["al_pool"])                               # every eligible non-AQ team (checked above)
    qual = dict((t, quality(res[t], ranks)) for t in set(pool) | set(aqs) if t in res)
    # with simulated odds, at-large order is each team's chance of an at-large place if it does NOT win its league's
    # bid (one scenario flips on a single rank crossing 25 or 50); the quality-win score breaks ties
    odds = c.get("bid_odds") or {}
    def al_chance(t):
        x = odds.get(_norm(t)) or {}
        left = 1 - x.get("aq", 0)
        return round(x.get("al", 0) / left, 3) if left > 0 else 0.0
    if odds:
        order = sorted(pool, key=lambda t: (-al_chance(t), score(ranks[t], qual[t]), ranks[t], t))
    else:
        order = sorted(pool, key=lambda t: (score(ranks[t], qual[t]), ranks[t], t))
    q_al = order[:n_al]
    rpi_al = [r["team"] for r in c["field"] if r["bid"] == "At-large"]
    ins = [t for t in q_al if t not in rpi_al]
    outs = [t for t in rpi_al if t not in q_al]
    ins.sort(key=lambda t: (score(ranks[t], qual[t]), ranks[t]))
    outs.sort(key=lambda t: -ranks[t])
    def explain(a, b, verb):
        ra, rb = res[a], res[b]
        h = _h2h(ra, b)
        com, (wa, la), (wb, lb) = _common(ra, rb, a, b)
        qa, qb = qual[a], qual[b]
        sent = ("%s (%s #%d) %s %s (#%d). %s has %s; %s has %s. "
                "On the hub's quality-win rule that is a score of %.0f against %.0f (lower is better)."
                % (a, lab, ranks[a], verb, b, ranks[b], a, _qtxt(qa), b, _qtxt(qb), score(ranks[a], qa), score(ranks[b], qb)))
        if odds:
            sent += " Across the simulations of every remaining match, %s earns an at-large place %.0f%% of the time and %s %.0f%%." % (
                a, 100 * al_chance(a), b, 100 * al_chance(b))
        ev = []
        if h:
            ev.append("Head to head: " + "; ".join("%s %s %s %s %s" % (m[0], a, "beat" if m[2] == "W" else "lost to", b, m[3]) for m in h) + ".")
        else:
            ev.append("Head to head: they have not played.")
        ev.append(("Common opponents (%d, results only): %s %d-%d, %s %d-%d." % (len(com), a, wa, la, b, wb, lb)) if com else "Common opponents: none.")
        for t, q in ((a, qa), (b, qb)):
            if q["bad_losses"]:
                ev.append("%s's losses outside the top 100: %s." % (t, ", ".join(
                    "%s%s%s" % (x[1], (" (#%d)" % x[0]) if x[0] else "", " (projected)" if x[2] == "proj" else "") for x in q["bad_losses"][:4])))
        return {"in": a, "out": b, "rank_in": ranks[a], "rank_out": ranks[b], "text": sent, "evidence": ev,
                "score_in": score(ranks[a], qa), "score_out": score(ranks[b], qb)}
    changes = [dict(explain(a, b, "moves into the field ahead of"), kind="swap") for a, b in zip(ins, outs)]
    # order changes AT the cut that change no membership: who is last in, who is next in line
    rpi_order = [t for t in c["al_pool"]]
    rpi_last, q_last = rpi_al[-1] if rpi_al else None, order[n_al - 1] if len(order) >= n_al else None
    rpi_next = next((t for t in rpi_order if t not in rpi_al), None)
    q_next = order[n_al] if len(order) > n_al else None
    if q_last and rpi_last and q_last != rpi_last and not ins:
        changes.append(dict(explain(rpi_last, q_last, "is safer than"), kind="last_in",
                            note="Same at-large teams. On RPI alone %s is the last team in; on the quality-win rule it is %s." % (rpi_last, q_last)))
    if q_next and rpi_next and q_next != rpi_next:
        changes.append(dict(explain(q_next, rpi_next, "is next in line ahead of"), kind="next_in_line",
                            note="If one more at-large place opened, it goes to %s on the quality-win rule, %s on RPI alone." % (q_next, rpi_next)))
    field = [{"team": t, "bid": "AQ", "rank": ranks.get(t), "conf": c["conf_of"].get(t), "q": qual.get(t)} for t in aqs] + \
            [{"team": t, "bid": "At-large", "rank": ranks[t], "conf": c["conf_of"].get(t), "q": qual[t]} for t in q_al]
    # the four teams either side of the committee-informed cut, in order
    last4 = q_al[-4:]; first_out = order[n_al:n_al + 4]; next_out = order[n_al + 4:n_al + 8]
    return {"field": field, "changes": changes, "last_four_in": last4, "first_four_out": first_out, "next_four_out": next_out,
            "order": order[:n_al + 8], "n_aq": len(aqs), "n_al": len(q_al), "qual": qual, "ranks": ranks}


def seed(sel):
    """top 32 of the field by the same quality score (lines 1-8, four per line); the rest unseeded, same order."""
    qual, ranks = sel["qual"], sel["ranks"]
    def k(r):
        q = qual.get(r["team"]) or {"t25w": [0, 0], "t50w": [0, 0]}
        return (score(r["rank"] or 999, q), r["rank"] or 999, r["team"])
    ordered = sorted(sel["field"], key=k)
    for i, r in enumerate(ordered, 1):
        r["seed"] = i if i <= 32 else None
        r["line"] = (i + 3) // 4 if i <= 32 else None
        r["order"] = i
    return ordered


def place(ordered):
    """approximate placement. Returns quadrants -> pods and the first-round games in renderBracket's order."""
    from scipy.optimize import linear_sum_assignment
    seeded = ordered[:32]; rest = ordered[32:]
    quad = [dict() for _ in range(4)]              # quad[q][line] = team row
    for r in seeded[:16]:                          # lines 1-4: the 2025-verified balanced grouping (TOP16_REGIONS)
        quad[QUAD_OF_POS[REGION_OF_OVERALL[r["seed"]]]][r["line"]] = r
    notes = []
    conf = lambda r: r.get("conf")
    def dist(a, b):
        m = miles(a["team"], b["team"])
        return m if m is not None else 1500.0     # unknown home location: a neutral middle distance
    # lines 5-8: each line's four teams to the four quadrants, partnered with the line (9-L) host
    for line in (5, 6, 7, 8):
        teams_l = [r for r in seeded if r["line"] == line]
        partner = 9 - line
        cost = [[(CONFLICT if conf(t) == conf(quad[q][partner]) else 0) + dist(t, quad[q][partner]) for q in range(4)] for t in teams_l]
        ri, ci = linear_sum_assignment(cost)
        for i, q in zip(ri, ci):
            quad[q][line] = teams_l[i]
            if cost[i][q] >= CONFLICT:
                notes.append("%s is in a pod with conference rival %s (no conflict-free option)" % (teams_l[i]["team"], quad[q][partner]["team"]))
    # pods: host = the line 1-4 team; its pod also holds the line 5-8 partner and two unseeded teams
    pods = []
    for q in range(4):
        for h in (1, 2, 3, 4):
            pods.append({"q": q, "host": quad[q][h], "seed2": quad[q][9 - h], "un": []})
    slots = [p for p in pods for _ in (0, 1)]
    cost = []
    for u in rest:
        row = []
        for p in slots:
            cf = CONFLICT if conf(u) in (conf(p["host"]), conf(p["seed2"])) else 0
            row.append(cf + dist(u, p["host"]))
        cost.append(row)
    ri, ci = linear_sum_assignment(cost)
    for i, j in zip(ri, ci):
        slots[j]["un"].append(rest[i])
    # repair: two unseeded teams of one conference in the same pod -> swap with another pod's unseeded team
    for p in pods:
        if len(p["un"]) == 2 and conf(p["un"][0]) == conf(p["un"][1]):
            fixed = False
            for p2 in pods:
                if p2 is p or fixed:
                    continue
                for j, v in enumerate(p2["un"]):
                    others2 = [p2["host"], p2["seed2"]] + [x for k, x in enumerate(p2["un"]) if k != j]
                    if conf(v) not in (conf(p["host"]), conf(p["seed2"]), conf(p["un"][0])) and \
                            conf(p["un"][1]) not in [conf(x) for x in others2]:
                        p["un"][1], p2["un"][j] = v, p["un"][1]; fixed = True; break
            if not fixed:
                notes.append("%s and %s (same conference) share a pod" % (p["un"][0]["team"], p["un"][1]["team"]))
    for p in pods:
        if len(p["un"]) == 2 and conf(p["un"][0]) == conf(p["un"][1]):
            pass
        for u in p["un"]:
            if conf(u) in (conf(p["host"]), conf(p["seed2"])):
                notes.append("%s shares a pod with a conference opponent (no conflict-free option)" % u["team"])
        # first round: the host meets the lower-ordered unseeded team, the line 5-8 seed the other
        p["un"].sort(key=lambda r: r["order"])
        p["r1"] = [(p["host"], p["un"][1]), (p["seed2"], p["un"][0])]
    # first-round games in renderBracket's order (quadrant, LINE_ORDER, alternate top/bottom)
    games = []
    for q in range(4):
        order = list(reversed(LINE_ORDER)) if q in (1, 3) else LINE_ORDER
        for i, line in enumerate(order):
            sd = quad[q][line]
            pod = next(p for p in pods if p["q"] == q and (p["host"] is sd or p["seed2"] is sd))
            opp = pod["r1"][0][1] if pod["host"] is sd else pod["r1"][1][1]
            games.append([sd, opp] if i % 2 == 0 else [opp, sd])
    hs = home_states()
    no_geo = sorted(r["team"] for r in ordered if _norm(r["team"]) not in hs)
    travel = []
    for p in pods:
        for t in [p["seed2"]] + p["un"]:
            m = miles(t["team"], p["host"]["team"])
            travel.append((t["team"], p["host"]["team"], m))
    return {"quad": quad, "pods": pods, "games": games, "notes": notes, "no_geo": no_geo, "travel": travel}


def build(c, basis="projected"):
    sel = select(c, basis)
    ordered = seed(sel)
    pl = place(ordered)
    return {"sel": sel, "ordered": ordered, "place": pl}
