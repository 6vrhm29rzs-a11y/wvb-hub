#!/usr/bin/env python3
"""The NCAA Division I women's volleyball RPI, in the committee's format (Cody, 2026-11-22).

SOURCE: 2026-27 NCAA Division I Women's Volleyball Prechampionship Manual, Section 2.2.
  Factors I-III   25% D-I winning pct, 50% opponents', 25% opponents' opponents' (rpi_2025.rpi_from_games)
  Factor IV, measured against ranks in the ORIGINAL (Factors I-III) RPI:
    + 2 positions per win over 1-25          + 1 per win over 26-50
    - 1 position per loss to 288-312         - 2 per loss to 313 or below, or to a non-D-I team
    + 2 for playing 50% of the nonconference schedule against 1-75
    - 2 for playing 50% of it against 263 or below and non-NCAA opponents

The manual gives Factor IV only in APPROXIMATE positions and the NCAA publishes no decimal. One position is
implemented as the RPI range divided by (teams - 1). That choice was tested against the alternatives on all ten
official 2026 tables and was the closest on every one; the measured agreement with the newest table is stored in
the output, so the page can state it. The official table remains the authority: this adds the days since it
was published.
"""
import datetime, json, os, re, statistics, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(REPO, "data", "rpi_committee_%d.json" % SEASON)


def adjust(di_games, nondi, keys, conf):
    """di_games [(winner, loser, id)], nondi [(winner, loser)] with exactly one D-I side.
    Returns {team: wp/owp/oowp/wins/losses/rpi (base)/adj/net/base_rank/rank and the Factor IV counts}."""
    import rpi_2025 as R
    keys = list(keys)
    b = R.rpi_from_games(di_games, keys)
    order = sorted(keys, key=lambda k: (-b[k]["rpi"], k))
    br = dict((k, i + 1) for i, k in enumerate(order))
    f = dict((k, {"w25": 0, "w50": 0, "l288": 0, "l313": 0, "lnon": 0, "nc": 0, "top75": 0, "low": 0}) for k in keys)
    for w, l, _ in di_games:
        if br[l] <= 25:
            f[w]["w25"] += 1
        elif br[l] <= 50:
            f[w]["w50"] += 1
        if 288 <= br[w] <= 312:
            f[l]["l288"] += 1
        elif br[w] >= 313:
            f[l]["l313"] += 1
        for me, op in ((w, l), (l, w)):
            if conf.get(me) != conf.get(op):
                f[me]["nc"] += 1
                f[me]["top75"] += br[op] <= 75
                f[me]["low"] += br[op] >= 263
    for w, l in nondi:
        for me in (w, l):
            if me in f:
                f[me]["nc"] += 1
                f[me]["low"] += 1
        if l in f:
            f[l]["lnon"] += 1
    vals = [b[k]["rpi"] for k in order]
    step = (vals[0] - vals[-1]) / max(1, len(vals) - 1)
    out = {}
    for k in keys:
        x = f[k]
        sched_b = 2 if x["nc"] and x["top75"] * 2 >= x["nc"] else 0
        sched_p = 2 if x["nc"] and x["low"] * 2 >= x["nc"] else 0
        net = 2 * x["w25"] + x["w50"] - x["l288"] - 2 * (x["l313"] + x["lnon"]) + sched_b - sched_p
        out[k] = dict(b[k], adj=b[k]["rpi"] + net * step, net=net, base_rank=br[k], sched_bonus=sched_b, sched_penalty=sched_p, **x)
    for i, k in enumerate(sorted(keys, key=lambda k: (-out[k]["adj"], br[k]))):
        out[k]["rank"] = i + 1
    return out


def counted_games():
    """Every counted final as (ET date, winner, loser, id), through the one classification + correction chain."""
    import season_counts as SC
    from gamelog import load_games_jsonl
    from reconcile_2025 import norm
    raw = load_games_jsonl(os.path.join(RAW, "games.jsonl"))
    cls, corr, last = SC.classify(raw, SEASON), SC.corrections(SEASON), {}
    for g in raw:
        k = str(g.get("game_id"))
        if k not in last or g.get("game_state") == "F" or last[k].get("game_state") != "F":
            last[k] = g
    out = []
    for k, g in last.items():
        if g.get("game_state") != "F" or cls.get(k) != "ok" or not g.get("start_time_epoch") or len(g.get("teams") or []) != 2:
            continue
        g = SC.apply_correction(g, corr)
        w = SC.winner_index(g)
        if w is None:
            continue
        a, b = [norm(t["name_short"]) for t in g["teams"]]
        out.append((time.strftime("%Y-%m-%d", time.gmtime(int(g["start_time_epoch"]) - 5 * 3600)), (a, b)[w], (b, a)[w], k))
    return out


def split(games, keys, through=None):
    k = set(keys)
    gs = [x for x in games if through is None or x[0] <= through]
    return [(w, l, i) for _, w, l, i in gs if w in k and l in k], [(w, l) for _, w, l, _i in gs if (w in k) != (l in k)]


def official_tables():
    rows = [json.loads(l) for l in open(os.path.join(RAW, "polls_rpi.jsonl"), encoding="utf-8") if l.strip()]
    return [r for r in rows if r.get("season") == SEASON and not r.get("is_previous_season") and r.get("source_tier") == "OFFICIAL"]


def through_date(cap):
    m = re.search(r"(\w{3})\w*\.? (\d+),? (\d{4})", cap.get("stamp") or "")
    return datetime.datetime.strptime(" ".join(m.groups()), "%b %d %Y").strftime("%Y-%m-%d") if m else None


def main():
    from reconcile_2025 import norm
    caps = official_tables()
    if not caps:
        print("no official %d RPI table held" % SEASON); return 1
    cap = caps[-1]
    rows = cap["rows"]
    keys = [norm(r["School"]) for r in rows]
    conf = dict((norm(r["School"]), r.get("Conf")) for r in rows)
    games = counted_games()
    # agreement: the same calculation, cut at the official table's own through-date
    thru = through_date(cap)
    di, nd = split(games, keys, thru)
    then = adjust(di, nd, keys, conf)
    off = dict((norm(r["School"]), int(r["Rank"])) for r in rows)
    orec = dict((norm(r["School"]), r["Record"]) for r in rows)
    err = [abs(then[k]["rank"] - off[k]) for k in keys]
    rec_diff = sorted(k for k in keys if orec[k] != "%d-%d" % (then[k]["wins"], then[k]["losses"]))
    di, nd = split(games, keys)
    cur = adjust(di, nd, keys, conf)
    last = max([x[0] for x in games] or [""])
    teams = []
    for r in rows:
        k = norm(r["School"]); x = cur[k]
        teams.append({"team": r["School"], "conf": r.get("Conf"), "rank": x["rank"], "official": off[k],
                      "rec": "%d-%d" % (x["wins"], x["losses"]), "rpi": round(x["adj"], 4), "base": round(x["rpi"], 4),
                      "wp": round(x["wp"], 4), "owp": round(x["owp"], 4), "oowp": round(x["oowp"], 4), "net": x["net"],
                      "w25": x["w25"], "w50": x["w50"], "l288": x["l288"], "l313": x["l313"] + x["lnon"],
                      "sb": x["sched_bonus"], "sp": x["sched_penalty"]})
    teams.sort(key=lambda t: t["rank"])
    meta = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "through": last, "n_finals": len(di),
            "official_stamp": cap.get("stamp"), "official_through": thru, "official_captured": cap.get("date"),
            "agree_exact": sum(e == 0 for e in err), "agree_within_1": sum(e <= 1 for e in err), "n": len(err),
            "mean_error": round(statistics.mean(err), 2), "max_error": max(err),
            "top64_mean_error": round(statistics.mean(abs(then[k]["rank"] - off[k]) for k in keys if off[k] <= 64), 2),
            "record_differences": rec_diff,
            "source": "2026-27 NCAA Division I Women's Volleyball Prechampionship Manual, Section 2.2"}
    tmp = OUT + ".tmp"
    json.dump({"meta": meta, "teams": teams}, open(tmp, "w"), separators=(",", ":"))
    os.replace(tmp, OUT)
    print("committee RPI through %s: %d of %d exact vs official (%s), %d within 1, record differences %d"
          % (last, meta["agree_exact"], meta["n"], cap.get("stamp"), meta["agree_within_1"], len(rec_diff)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
