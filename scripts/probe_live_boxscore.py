#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure what /game/{id}/boxscore ACTUALLY serves during a live match.

⚠ WHY THIS EXISTS. Live Match Center was written without knowing the answer.
On 2026-08-24 no D-I volleyball match was in progress (next slate 2026-08-28),
and men's and women's soccer on the same API were all final that night, so
there was nothing live anywhere to probe. Rather than assume the endpoint
carries partial stats mid-match -- or assume it does not -- the code treats
"nothing usable" as the ordinary path and this script settles it with evidence.

UNTIL THIS HAS BEEN RUN AGAINST A LIVE MATCH, NOTHING IN THIS PROJECT MAY CLAIM
THAT LIVE TEAM OR PLAYER STATISTICS ARE AVAILABLE.

Run it during an active window:

    python3 scripts/probe_live_boxscore.py                # auto-pick live ones
    python3 scripts/probe_live_boxscore.py --id 6639891   # one specific match
    python3 scripts/probe_live_boxscore.py --minutes 45

It appends one JSON row per poll to docs/live_boxscore_probe_<date>.jsonl and
prints a verdict at the end. It is READ-ONLY with respect to the dataset: it
never writes to data/, and its output is a measurement note, not a data source.
"""

import argparse
import datetime
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_detail as LD                                          # noqa: E402

try:
    from urllib.request import Request, urlopen
except ImportError:                                               # py2
    from urllib2 import Request, urlopen                          # noqa

API = "https://ncaa-api.henrygd.me"
UA = "wvb-hub/0.1 (personal research project; live measurement, <=1 req/20s)"


def get(path):
    req = Request(API + path, headers={"User-Agent": UA})
    try:
        return json.loads(urlopen(req, timeout=20).read().decode("utf-8"))
    except Exception:                                             # noqa: BLE001
        return None


def live_ids():
    now = datetime.datetime.utcnow() - datetime.timedelta(hours=4)   # ~ET
    sb = get("/scoreboard/volleyball-women/d1/%04d/%02d/%02d/all-conf"
             % (now.year, now.month, now.day)) or {}
    out = []
    for e in sb.get("games") or []:
        g = e.get("game", e)
        if (g.get("gameState") or "").lower() in ("live", "i", "in progress"):
            out.append((str(g.get("gameID")),
                        "%s at %s" % ((g.get("away") or {}).get("names", {}).get("short"),
                                      (g.get("home") or {}).get("names", {}).get("short"))))
    return out


def probe_once(gid):
    """One observation. Records WHAT WAS SEEN, and judges nothing it did not."""
    raw = get("/game/%s/boxscore" % gid)
    row = {"utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "game_id": gid, "http_ok": raw is not None}
    if raw is None:
        row["note"] = "no response"
        return row, None
    row["status"] = raw.get("status")
    row["period"] = raw.get("period")
    tb = raw.get("teamBoxscore") or []
    row["team_entries"] = len(tb)
    row["player_rows"] = sum(len(t.get("playerStats") or []) for t in tb
                             if isinstance(t, dict))
    teams, leaders, why = LD.validate(raw)
    row["validated"] = teams is not None
    row["reason"] = why
    if teams:
        row["kills"] = [t["kills"] for t in teams]
        row["attacks"] = [t["attackAttempts"] for t in teams]
        row["digs"] = [t["digs"] for t in teams]
        row["leaders"] = [p["name"] for p in leaders]
    return row, teams


def checkpoint_run(gid, checkpoint, note=""):
    """One CHECKPOINT: fetch, classify, record. The documented workflow.

    ⚠ FOUR CHECKPOINTS, RUN AT FOUR MOMENTS, AND EACH ANSWERS A DIFFERENT
    QUESTION about the source -- not four samples of one question:

        pre    before first serve   -- does the endpoint even answer?
        live   during play          -- are statistics served mid-match?
        final  right after the end  -- is there a pending window, and how long?
        box    once the box appears -- what does a complete one look like?

    Each writes ONE minimal record. Raw bodies are never stored.
    """
    import probe_observe as PO
    status, body, terr = None, None, None
    try:
        req = Request("%s/game/%s/boxscore" % (API, gid),
                      headers={"User-Agent": UA})
        resp = urlopen(req, timeout=25)
        status = getattr(resp, "status", 200) or 200
        body = resp.read().decode("utf-8", "replace")
    except Exception as exc:                                  # noqa: BLE001
        code = getattr(exc, "code", None)
        if code:
            status = code
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:                                 # noqa: BLE001
                body = None
        else:
            terr = type(exc).__name__

    sb = None
    try:
        board = get("/scoreboard/volleyball-women/d1/%s/all-conf"
                    % datetime.date.today().strftime("%Y/%m/%d"))
        for entry in ((board or {}).get("games") or []):
            g = entry.get("game", entry)
            if str(g.get("gameID")) == str(gid):
                sb = {"away_sets": (g.get("away") or {}).get("score"),
                      "home_sets": (g.get("home") or {}).get("score"),
                      "state": g.get("gameState")}
                break
    except Exception:                                         # noqa: BLE001
        sb = None

    cls = PO.classify(http_status=status, body=body, transport_error=terr,
                      scoreboard=sb)
    rec = PO.observation(gid, checkpoint, cls, note)
    res = PO.append_observation(rec)

    print("CHECKPOINT %s -- game %s" % (checkpoint.upper(), gid))
    print("  outcome : %s" % cls["outcome"])
    print("  why     : %s" % cls["why"])
    print("  http    : %s" % cls["http"])
    print("  shape   : json=%s teams=%s player_rows=%s status=%r period=%r"
          % (cls["shape"]["json"], cls["shape"]["team_entries"],
             cls["shape"]["player_rows"], cls["shape"]["status"],
             cls["shape"]["period"]))
    print("  score   : away=%r home=%r state=%r   (None means NO SCORE, not 0)"
          % (cls["score"]["away"], cls["score"]["home"], cls["score"]["state"]))
    print("  recorded: %s%s"
          % (res["written"], "" if res["written"] else " -- " + res["reason"]))
    print()
    print("PASTE THE BLOCK ABOVE BACK TO CLAUDE.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", choices=("pre", "live", "final", "box"),
                    help="run ONE documented checkpoint and record it")
    ap.add_argument("--note", default="")
    ap.add_argument("--id", action="append", default=[])
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--every", type=float, default=20.0)
    a = ap.parse_args()

    if a.checkpoint:
        if not a.id:
            print("--checkpoint needs --id GAMEID "
                  "(run scripts/preflight_live.py to pick one)")
            return 2
        return checkpoint_run(a.id[0], a.checkpoint, a.note)

    ids = [(i, i) for i in a.id] or live_ids()
    if not ids:
        print("No D-I women's volleyball match is live right now.")
        print("Nothing measured -- and nothing may be claimed. Re-run during "
              "an active window (matches resume 2026-08-28).")
        return 2

    out = os.path.join(REPO, "docs", "live_boxscore_probe_%s.jsonl"
                       % datetime.date.today().isoformat())
    print("probing %d live match(es), every %.0fs for %.0f min"
          % (len(ids), a.every, a.minutes))
    for gid, label in ids:
        print("   %s  %s" % (gid, label))

    seen, deadline = [], time.time() + a.minutes * 60
    while time.time() < deadline:
        for gid, _label in ids:
            row, _t = probe_once(gid)
            seen.append(row)
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            print("  %s %s  teams=%s players=%s validated=%s %s"
                  % (row["utc"], gid, row.get("team_entries"),
                     row.get("player_rows"), row.get("validated"),
                     row.get("reason") or ""))
            if (row.get("status") or "").upper() == "F":
                print("  -> that match went final; stopping it")
                ids = [x for x in ids if x[0] != gid]
        if not ids:
            break
        time.sleep(a.every)

    print("\n---- VERDICT (from %d observations) ----" % len(seen))
    live_obs = [r for r in seen if (r.get("status") or "").upper() != "F"]
    ok = [r for r in live_obs if r.get("validated")]
    print("  observations while NOT final : %d" % len(live_obs))
    print("  of those, coherent box score : %d" % len(ok))
    if live_obs:
        print("  player rows seen (max)       : %d"
              % max(r.get("player_rows") or 0 for r in live_obs))
        reasons = {}
        for r in live_obs:
            if not r.get("validated"):
                reasons[r.get("reason") or "?"] = reasons.get(r.get("reason") or "?", 0) + 1
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            print("  refused %-3d x %s" % (v, k))
    print("\n  written to %s" % os.path.relpath(out, REPO))
    print("  ⚠ Record the outcome in CLAUDE.md/AGENTS.md before any code or "
          "copy claims live stats are available.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
