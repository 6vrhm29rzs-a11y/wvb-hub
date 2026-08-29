#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Availability & Participation Desk artifact (private).

The non-negotiable distinction (review round 9):
  * AVAILABILITY is sourced status -- only an attributable public source
    with exact quoted wording can set one (confirmed_unavailable or
    limited_gtd, preserving the source's words).
  * PARTICIPATION is an observed match fact: appeared (recorded actions),
    zero-action listing (in the box, every column zero -- the feed's DNP
    convention, measured on Auguste 2026-08-28: gp=4, all zeros, while the
    live box said setsPlayed:null), or not in the box at all.
  * A PARTICIPATION ANOMALY is a review signal against a stated baseline
    (availability.py's top-6 window flags), never a status.
  * None of these is a diagnosis, and no reason is ever inferred.

Community/forum items and Cody's own observations are stored as SIGNALS,
separately labelled; they can never set a status. Expired or out-of-range
evidence supports nothing and the player shows the honest default:
"no current sourced availability information."

Writes data/availability_desk_2026.json. PRIVATE: the payload reaches only
the private build (AVAIL-* strip fences); the artifact stays out of the
public page entirely.
"""

import datetime
import json
import os
import sys

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:                                      # noqa: BLE001
    PT = None


def pt_date(ep):
    if PT:
        return datetime.datetime.fromtimestamp(int(ep), PT).strftime("%Y-%m-%d")
    return datetime.datetime.utcfromtimestamp(int(ep)).strftime("%Y-%m-%d")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
ATTRIBUTABLE = ("school_release", "school_site", "beat_report", "broadcast")
SIGNAL_KINDS = ("community_forum", "cody_observation")
CLAIMS = ("confirmed_unavailable", "limited_gtd")


def load(p, default=None):
    path = os.path.join(REPO, p)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) \
        else default


def entry_state(e, today):
    """'status' | 'signal' | 'expired' | 'invalid' for one evidence entry."""
    if not isinstance(e, dict):
        return "invalid"
    rb = e.get("review_by")
    eff = e.get("effective") or {}
    expired = (rb and str(today) > str(rb)) or \
              (eff.get("to") and str(today) > str(eff["to"]))
    if e.get("kind") in SIGNAL_KINDS:
        return "expired" if expired else "signal"
    if e.get("kind") in ATTRIBUTABLE and e.get("claim") in CLAIMS \
            and e.get("quote") and e.get("url"):
        if expired:
            return "expired"
        if eff.get("from") and str(today) < str(eff["from"]):
            return "expired"               # not yet effective = not active
        return "status"
    return "invalid"


def participation(rows):
    """One box row list -> per-player participation facts. Facts only."""
    out = []
    for r in rows:
        nm = ("%s %s" % (r.get("first") or "", r.get("last") or "")).strip()
        if not nm:
            continue
        try:
            gp = int(float(r.get("gp") or 0))
        except (TypeError, ValueError):
            gp = 0
        acted = any(float(r.get(k) or 0) > 0 for k in
                    ("kills", "errors", "atts", "aces", "digs", "bs", "ba",
                     "assists"))
        state = ("appeared" if gp and acted
                 else "zero_action" if gp else "not_listed")
        out.append({"name": nm, "team_id": str(r.get("team_id")),
                    "sets": gp, "state": state})
    return out


def classify(ev, today):
    """(statuses, signals, expired) for one evidence map at one DATE.

    Pure and clock-injectable (round 10): the Saturday-morning regression
    was a suite that let the LIVE calendar decide whether a shipped test
    was green -- the Auguste observation was effective Aug 28 only, so at
    midnight it correctly expired and two calendar-pinned checks went red.
    Tests now call this with an explicit date and assert BOTH sides of the
    boundary; nothing here weakens expiry.
    """
    statuses, signals, expired = [], [], []
    for key, entries in (ev or {}).items():
        team, _, player = key.partition("|")
        for e in entries or []:
            st = entry_state(e, today)
            row = {"team": team, "player": player,
                   "kind": e.get("kind"), "quote": e.get("quote"),
                   "url": e.get("url"), "retrieved": e.get("retrieved"),
                   "effective": e.get("effective"),
                   "review_by": e.get("review_by"),
                   "claim": e.get("claim"), "note": e.get("note")}
            if st == "status":
                statuses.append(row)
            elif st == "signal":
                signals.append(row)
            elif st == "expired":
                # ⚠ HISTORY, NOT A COUNT. An expired item keeps its words
                # and gains WHY it expired -- it renders in the collapsed
                # Evidence history as "Historical -- sets no current
                # status", and its player keeps her participation timeline.
                eff = e.get("effective") or {}
                row["expired_on"] = (
                    ("effective range ended %s" % eff.get("to"))
                    if eff.get("to") and str(today) > str(eff["to"])
                    else ("review date %s passed" % e.get("review_by"))
                    if e.get("review_by")
                    and str(today) > str(e.get("review_by"))
                    else "not yet effective")
                expired.append(row)
    return statuses, signals, expired


def build(today=None):
    today = today or datetime.date.today().isoformat()
    ev = (load("data/raw/%d/availability_evidence.json" % SEASON) or {}) \
        .get("players") or {}
    statuses, signals, expired = classify(ev, today)

    # participation, from the crawled boxes, most recent match per team
    doc = load("data/data_%d.json" % SEASON) or {}
    id2n = dict((str(t["team_id"]), t.get("name_short"))
                for t in (doc.get("teams") or []))
    date_of = {}
    for g in (doc.get("games") or []):
        if g.get("state") == "F":
            date_of[str(g.get("game_id"))] = int(g.get("start_time_epoch")
                                                 or 0)
    per_team_latest = {}
    timelines = {}
    # ⚠ EXPIRED EVIDENCE KEEPS ITS TIMELINE. The watch set once held only
    # current statuses/signals, so the moment an observation expired, the
    # participation history that explains why it was recorded vanished with
    # it. Evidence of any age keeps its player's observed facts.
    watch = set((s["team"], s["player"])
                for s in signals + statuses + expired)
    path = os.path.join(REPO, "data", "raw", str(SEASON), "playerbox.jsonl")
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            gid = str(rec.get("game_id"))
            if gid not in date_of:
                continue
            facts = participation(rec.get("rows") or [])
            for f in facts:
                tn = id2n.get(f["team_id"], "")
                if not tn:
                    continue
                cur = per_team_latest.get(tn)
                if not cur or date_of[gid] > cur["ep"]:
                    per_team_latest.setdefault(tn, {"ep": 0, "gid": None,
                                                    "rows": []})
                if per_team_latest[tn]["gid"] != gid \
                        and date_of[gid] >= per_team_latest[tn]["ep"]:
                    per_team_latest[tn] = {"ep": date_of[gid], "gid": gid,
                                           "rows": []}
                if per_team_latest[tn]["gid"] == gid:
                    per_team_latest[tn]["rows"].append(f)
                if (tn, f["name"]) in watch:
                    timelines.setdefault(tn + "|" + f["name"], []).append(
                        {"gid": gid, "ep": date_of[gid], "sets": f["sets"],
                         "state": f["state"]})
    latest = {}
    for tn, rec in per_team_latest.items():
        zero = [r["name"] for r in rec["rows"] if r["state"] == "zero_action"]
        latest[tn] = {"gid": rec["gid"],
                      "d": pt_date(rec["ep"]),
                      "appeared": sum(1 for r in rec["rows"]
                                      if r["state"] == "appeared"),
                      "zero_action": zero}
    for k in timelines:
        timelines[k].sort(key=lambda x: x["ep"])

    # anomalies: availability.py's measured baseline flags, passed through
    av = load("data/availability_%d.json" % SEASON) or {}
    anomalies = av.get("flagged") or []

    out = {"meta": {
        "season": SEASON, "source_tier": "DERIVED",
        "generated_at_utc": datetime.datetime.utcnow().replace(
            microsecond=0).isoformat() + "Z",
        "counts": {"statuses": len(statuses), "signals": len(signals),
                   "expired": len(expired), "anomalies": len(anomalies)},
        "anomaly_baseline": (av.get("meta") or {}).get("measures"),
        "anomaly_floor": ("availability.py needs %s completed team matches "
                          "for a baseline; leagues below that show no "
                          "anomaly rather than a guessed one"
                          % ((av.get("meta") or {}).get("min_team_matches")
                             or 4)),
    },
        "statuses": statuses, "signals": signals, "expired": expired,
        "anomalies": anomalies, "latest": latest, "timelines": timelines}
    dst = os.path.join(REPO, "data", "availability_desk_%d.json" % SEASON)
    json.dump(out, open(dst, "w"), indent=1)
    c = out["meta"]["counts"]
    print("availability desk: %(statuses)d sourced status(es), %(signals)d "
          "labelled signal(s), %(expired)d expired, %(anomalies)d "
          "baseline anomalies" % c)
    return 0


if __name__ == "__main__":
    sys.exit(build())
