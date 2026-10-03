#!/usr/bin/env python3
"""Targeted, rate-limited refetch of IDENTIFIED partial/nameless box scores
(mail 036 item 4, authorized by Cody). Not a crawl: only the gids listed in
the targets file, through crawl_2025.fetch (same throttle, same UA).

APPEND-ONLY, AND ONLY WHEN BETTER. boxscores.jsonl / playerbox.jsonl are
per-gid last-wins, so appending a refetch that is no more complete than what
is on disk would replace a record with an equal-or-worse one. A refetch is
appended only when it is strictly more complete (partial: max player sets
reaches the match's sets; nameless: rows now carry names). Every attempt --
accepted or not -- is logged with its reason to box_repair_log.jsonl, which
is the provenance record. Nothing is zero-filled; nothing is deleted.
"""
import datetime
import json
import os
import sys

os.environ.setdefault("WVB_SEASON", "2026")
os.environ.setdefault("WVB_REQ_INTERVAL", "1.5")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_2025 as C  # noqa: E402

LOG = os.path.join(C.RAW, "box_repair_log.jsonl")
PB = os.path.join(C.RAW, "playerbox.jsonl")

PLAYER_FIELDS = (  # same raw-count mapping crawl_players() stores
    ("first", "firstName"), ("last", "lastName"), ("num", "number"),
    ("pos", "position"), ("gp", "gamesPlayed"), ("kills", "kills"),
    ("errors", "attackErrors"), ("atts", "attackAttempts"),
    ("aces", "serviceAces"), ("digs", "digs"), ("bs", "blockSolos"),
    ("ba", "blockAssists"), ("assists", "assists"), ("points", "points"),
    ("serve_errors", "serviceErrors"), ("serve_atts", "serveAttempts"),
    ("recv_atts", "receptionAttempts"), ("recv_errors", "receptionErrors"),
    ("bh_errors", "ballHandlingErrors"), ("set_errors", "setErrors"),
    ("block_errors", "blockingErrors"), ("starter", "starter"))


def num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def extract(payload):
    teams, rows = [], []
    for tb in payload.get("teamBoxscore") or []:
        ts = dict(tb.get("teamStats") or {})
        ts.pop("__typename", None)
        tid = str(tb.get("teamId"))
        teams.append({"team_id": tid, "team_stats": ts})
        for ps in tb.get("playerStats") or []:
            if not ps.get("participated"):
                continue
            r = {"team_id": tid}
            for k, src in PLAYER_FIELDS:
                r[k] = ps.get(src)
            rows.append(r)
    meta = dict((str(t.get("teamId")), {"name_short": t.get("nameShort"),
                                        "is_home": t.get("isHome")})
                for t in payload.get("teams") or [])
    for t in teams:
        t.update(meta.get(t["team_id"], {}))
    return teams, rows


def quality(rows):
    gps = [num(r.get("gp")) for r in rows]
    gps = [g for g in gps if g is not None]
    by = {}
    for r in rows:
        g = num(r.get("gp"))
        if g is not None:
            by[r["team_id"]] = max(by.get(r["team_id"], 0), g)
    named = sum(1 for r in rows if (r.get("first") or r.get("last")))
    return {"rows": len(rows), "named": named,
            "max_gp_by_team": sorted(by.values())}


def main():
    tg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/repair_targets.json"))
    work = [(p[0], "partial", int(p[4])) for p in tg["partial"]] + \
           [(g, "nameless", None) for g in tg["missing"]]
    acc = 0
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with open(LOG, "a") as log:
        for gid, kind, nsets in work:
            payload = C.fetch("/game/%s/boxscore" % gid)
            entry = {"game_id": gid, "kind": kind, "expected_sets": nsets,
                     "fetched_at": now, "source": "ncaa-api /game/%s/boxscore" % gid}
            if not payload:
                entry.update(accepted=False, reason="fetch failed / 404")
            else:
                teams, rows = extract(payload)
                q = quality(rows)
                entry["refetch_quality"] = q
                if kind == "partial":
                    ok = len(q["max_gp_by_team"]) == 2 and all(g >= nsets for g in q["max_gp_by_team"])
                    why = "complete: every side reaches %d sets" % nsets if ok else \
                          "still partial (max gp %s of %d)" % (q["max_gp_by_team"], nsets)
                else:
                    ok = q["named"] > 0
                    why = "rows now carry names (%d)" % q["named"] if ok else "still nameless"
                entry.update(accepted=ok, reason=why)
                if ok:
                    with open(C.BOX_JSONL, "a") as fb:
                        fb.write(json.dumps({"game_id": gid, "teams": teams,
                                             "source_tier": "OFFICIAL",
                                             "source": entry["source"],
                                             "repair": "box_repair_log " + now}) + "\n")
                    with open(PB, "a") as fp:
                        fp.write(json.dumps({"game_id": gid, "rows": rows,
                                             "repair": "box_repair_log " + now}) + "\n")
                    acc += 1
            log.write(json.dumps(entry) + "\n")
            print(gid, kind, entry["accepted"], entry["reason"], flush=True)
    print("accepted %d of %d" % (acc, len(work)))


if __name__ == "__main__":
    main()
