#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest a MANUALLY CAPTURED Evollve team-ratings table.

⚠ EVOLLVE IS NOT CRAWLABLE AND THIS SCRIPT DOES NOT FETCH. Its robots.txt is
"User-agent: * / Disallow: /" followed by an allow-list of Googlebot, Bingbot,
Yandex, Baidu, Facebot, Twitterbot, Slurp, DuckDuckBot and ia_archiver
(measured 2026-09-12); we are none of those, so evollve.net sits on the
no-scrape hook beside masseyratings.com and figstats.net. The input here is a
file saved out of Cody's own browser while reading the page normally -- the
same manual-snapshot route Massey and FIGstats already use.

Writes an append-only snapshot with the publisher's own values, our fetch
time and a sha256 of the reviewed payload. EXTERNAL REFERENCE ONLY: nothing
here feeds POWER, Digby, the resume or any rating -- guarded, both directions.
"""
import hashlib
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "Cody", "data", "evollve_snapshots.jsonl")

# The cell format is "value~rank": Evollve prints the rank under each number.
CELL = re.compile(r"^(?P<val>[-\d.]+%?)~(?P<rank>\d+)$")
# "Nebraska (6-0)" -> name, wins, losses
TEAM = re.compile(r"^(?P<name>.+?)\s*\((?P<w>\d+)-(?P<l>\d+)\)$")

# ⚠ THE HEADER HAS TWO COLUMNS LITERALLY NAMED "SIDEOUT %" -- one is the
# schedule-ADJUSTED receive rating under EVOLLVE RATINGS, the other the raw
# season rate under UNADJUSTED. Keying on the printed label would silently
# collapse them (R4, and the exact aces/assists collision this codebase has
# already shipped once). Position decides, and the names say which is which.
FIELDS = ["evollve_rtg", "adj_points_scored", "adj_sideout", "sos",
          "pct_pts_won", "pt_score_pct", "sideout_pct", "win_pct",
          "pyth_pct", "luck"]


def _num(s):
    s = (s or "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse(path):
    doc = json.load(io.open(path, encoding="utf-8"))
    cols, rows = doc["cols"], doc["rows"]
    if len(cols) != 2 + len(FIELDS):
        raise SystemExit("layout changed: %d columns, expected %d -- re-read "
                         "the page before trusting this parser (%s)"
                         % (len(cols), 2 + len(FIELDS), cols))
    out = []
    for r in rows:
        m = TEAM.match(r[0].strip())
        if not m:
            raise SystemExit("unparsed team cell: %r" % r[0])
        rec = {"team_raw": m.group("name").strip(),
               "wins": int(m.group("w")), "losses": int(m.group("l")),
               "conf": r[1].strip()}
        for i, f in enumerate(FIELDS):
            cm = CELL.match(r[2 + i].strip())
            if not cm:
                rec[f], rec[f + "_rank"] = _num(r[2 + i]), None
            else:
                rec[f] = _num(cm.group("val"))
                rec[f + "_rank"] = int(cm.group("rank"))
        out.append(rec)
    return doc, out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/Downloads/evollve_team_ratings.json")
    if not os.path.exists(src):
        raise SystemExit("no capture at %s -- save the ratings table from the "
                         "browser first" % src)
    doc, rows = parse(src)

    from external_refs import _ref_norm
    hub = json.load(io.open(os.path.join(REPO, "data", "data_%d.json" % SEASON),
                            encoding="utf-8"))
    names = set()
    for t in (hub.get("teams") or []):
        if isinstance(t, dict) and t.get("name_short"):
            names.add(t["name_short"])
    by_key = {}
    for n in names:
        by_key.setdefault(_ref_norm(n), n)

    hit = 0
    for r in rows:
        k = _ref_norm(r["team_raw"])
        r["hub_team"] = by_key.get(k)
        if r["hub_team"]:
            hit += 1

    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    snap = {
        "source": "evollve.net",
        "kind": "team_ratings",
        "season": SEASON,
        "retrieved": doc.get("retrieved"),
        "capture": "manual browser review (robots.txt disallows crawlers)",
        "rows": len(rows),
        "resolved_to_hub": hit,
        "unresolved": sorted(r["team_raw"] for r in rows if not r["hub_team"]),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "data": rows,
    }
    with io.open(OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
    print("evollve snapshot: %d rows, %d resolved to hub teams, %d unresolved"
          % (len(rows), hit, len(rows) - hit))
    if snap["unresolved"]:
        print("  unresolved:", ", ".join(snap["unresolved"][:12]))
    print("  ->", OUT)


if __name__ == "__main__":
    main()
