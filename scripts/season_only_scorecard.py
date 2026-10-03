#!/usr/bin/env python3
"""LOCAL-ONLY, PRIVATE (Cody, 2026-09-28: "Sounds good" to a weekly scorecard):
a PROSPECTIVE comparison of Current POWER and the private 2026 candidate.

1. In the 48 hours before a match starts, record each model's home-win chance ONCE
   (the first refresh that sees it in that window). A logged forecast is never rewritten.
2. When the match is final (and counts), score both forecasts (log loss).
Nothing here is retrospective: only forecasts logged before first serve count.
Writes only Cody/data/power_candidate/scorecard_log.jsonl and scorecard.json.
Never gates the build; absent candidate file -> skipped.
"""
import datetime, json, math, os, sys, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
DIR = os.path.join(REPO, "Cody", "data", "power_candidate")
LOG = os.path.join(DIR, "scorecard_log.jsonl")
SUM = os.path.join(DIR, "scorecard.json")


def cand_prob(c, home, away, neutral):
    m, T = c.get("win_model"), c.get("teams") or {}
    if not m or home not in T or away not in T:
        return None
    d = T[home]["theta"] - T[away]["theta"]
    dep = min(1.0, min(T[home].get("sets", 40), T[away].get("sets", 40)) / 40.0)
    k = m["b"] + m["c"] * m["s_now"] + m.get("e", 0.0) * dep
    if neutral:
        z = k * d
    else:
        d += c.get("home_setshare") or 0.0
        z = m["a"] + k * d
    return 1.0 / (1.0 + math.exp(-z))


def main():
    cpath = os.path.join(DIR, "v2so_preview.json")
    if not os.path.exists(cpath):
        print("scorecard: no candidate file -- skipped"); return 0
    cand = json.load(open(cpath))
    preds = json.load(open(os.path.join(REPO, "data", "predictions_2026.json"))).get("games") or []
    logged = set()
    if os.path.exists(LOG):
        for l in open(LOG):
            try:
                logged.add(json.loads(l)["gid"])
            except (ValueError, KeyError):
                pass
    now = time.time(); new = 0
    with open(LOG, "a") as f:
        for g in preds:
            gid = str(g.get("game_id")); st = g.get("start_epoch") or 0
            # logged before first serve, and only inside the next 48 hours so each forecast
            # reflects the ratings as they stand going into that match
            if gid in logged or st <= now + 300 or st > now + 48 * 3600:
                continue
            pc = cand_prob(cand, g.get("home"), g.get("away"), bool(g.get("neutral")))
            if pc is None or g.get("home_win") is None:
                continue
            f.write(json.dumps({"gid": gid, "start_epoch": st, "home": g.get("home"), "away": g.get("away"),
                                "neutral": bool(g.get("neutral")), "p_current": g["home_win"], "p_candidate": round(pc, 5),
                                "candidate_version": cand.get("version"), "logged_utc": datetime.datetime.utcnow().isoformat() + "Z"}) + "\n")
            new += 1
    # score finished matches
    import season_counts as SC
    games = json.load(open(os.path.join(REPO, "data", "data_2026.json")))["games"]
    res = {}
    for g in SC.countable(games, 2026):
        wi = SC.winner_index(g)
        ts = g.get("teams") or []
        if wi is None or len(ts) != 2:
            continue
        res[str(g["game_id"])] = 1 if ts[wi].get("is_home") else 0
    rows = []
    for l in open(LOG):
        r = json.loads(l)
        if r["gid"] in res:
            y = res[r["gid"]]
            ll = lambda p: -(y * math.log(max(1e-4, min(1 - 1e-4, p))) + (1 - y) * math.log(max(1e-4, min(1 - 1e-4, 1 - p))))
            r.update(y=y, ll_current=ll(r["p_current"]), ll_candidate=ll(r["p_candidate"]),
                     week=datetime.datetime.utcfromtimestamp(r["start_epoch"]).strftime("%G-W%V"))
            rows.append(r)
    wk = {}
    for r in rows:
        w = wk.setdefault(r["week"], [0, 0.0, 0.0, 0, 0])
        w[0] += 1; w[1] += r["ll_current"]; w[2] += r["ll_candidate"]
        w[3] += (r["p_current"] > .5) == (r["y"] == 1); w[4] += (r["p_candidate"] > .5) == (r["y"] == 1)
    summ = {"note": "PROSPECTIVE: forecasts logged before first serve only. Lower log loss is better.",
            "matches_scored": len(rows), "logged_total": len(logged) + new,
            "overall": ({"current_logloss": round(sum(r["ll_current"] for r in rows) / len(rows), 4),
                         "candidate_logloss": round(sum(r["ll_candidate"] for r in rows) / len(rows), 4),
                         "current_correct": sum((r["p_current"] > .5) == (r["y"] == 1) for r in rows),
                         "candidate_correct": sum((r["p_candidate"] > .5) == (r["y"] == 1) for r in rows)} if rows else None),
            "by_week": dict((k, {"n": v[0], "current_logloss": round(v[1] / v[0], 4), "candidate_logloss": round(v[2] / v[0], 4),
                                 "current_correct": v[3], "candidate_correct": v[4]}) for k, v in sorted(wk.items()))}
    json.dump(summ, open(SUM, "w"), indent=1)
    print("scorecard: +%d logged, %d scored" % (new, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
