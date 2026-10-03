#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""School-declared match sites, as an evidence ledger for venues.py.

WHY. 1,690 fixtures carry no venue in the feed, so venues.py could only call them
"no-venue" and the rating gave them the ordinary home edge. The daily result
verification (verify_results_daily.py) already reads each school's own schedule,
which states Home / Away / Neutral for every match it finds -- 1,740 matches by
2026-09-28, 172 of them no-venue fixtures the schools call NEUTRAL, plus 27 where
the feed and a school disagree. This turns those rows into a ledger venues.py can
apply, with the evidence (school, URL, report date) on every entry. No new
collection: it reads data/result_verification_{season}-*.json only.

RULE. For a match: NEUTRAL if any school row says Neutral; HOME (for the feed's
home side) if every row is consistent with that; CONFLICT if rows disagree with
each other or with the feed's home flag. venues.py applies neutral/home ONLY where
its own verdict is no-venue/unknown; conflicts are never applied, only listed.
Python 3.9 target. Writes data/raw/{season}/venue_site_evidence.json.
"""
import datetime
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from reconcile_2025 import norm  # noqa: E402

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "raw", str(SEASON), "venue_site_evidence.json")


def build():
    doc = json.load(open(os.path.join(REPO, "data", "data_%d.json" % SEASON)))["games"]
    home_of = {}
    for g in doc:
        for t in g.get("teams") or []:
            if t.get("is_home"):
                home_of[str(g["game_id"])] = norm(t.get("name_short") or "")
    says = {}
    for p in sorted(glob.glob(os.path.join(REPO, "data", "result_verification_%d-*.json" % SEASON))):
        rep = json.load(open(p))
        for m in rep.get("matches") or []:
            for school, rec in (m.get("schools") or {}).items():
                s = (rec.get("site_says") or "").strip().lower()
                if s not in ("home", "away", "neutral"):
                    continue
                says.setdefault(str(m["gid"]), {})[school] = {
                    "site": s, "url": rec.get("url"), "report": os.path.basename(p), "assertion": rec.get("assertion")}
    entries = {}
    for gid, rows in says.items():
        h = home_of.get(gid)
        votes = set()
        for school, r in rows.items():
            if r["site"] == "neutral":
                votes.add("neutral")
            elif (r["site"] == "home") == (norm(school) == h):
                votes.add("home")
            else:
                votes.add("flip")           # the school's home/away disagrees with the feed's home flag
        verdict = "neutral" if votes == {"neutral"} else ("home" if votes == {"home"} else "conflict")
        entries[gid] = {"verdict": verdict, "schools": rows, "feed_home": h}
    return {"meta": {"season": SEASON, "source_tier": "OFFICIAL", "source": "school athletics schedules via result_verification reports",
                     "generated_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "rule": "neutral if every school row says neutral; home if every row agrees with the feed's home flag; otherwise conflict (listed, never applied)",
                     "counts": {"matches": len(entries), "neutral": sum(1 for e in entries.values() if e["verdict"] == "neutral"),
                                "home": sum(1 for e in entries.values() if e["verdict"] == "home"),
                                "conflict": sum(1 for e in entries.values() if e["verdict"] == "conflict")}},
            "games": entries}


if __name__ == "__main__":
    out = build()
    json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
    print("wrote %s  %s" % (OUT, out["meta"]["counts"]))
