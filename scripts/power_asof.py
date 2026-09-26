#!/usr/bin/env python3
"""POWER as of a moment: the same model, recomputed with an earlier cutoff.

For the daily reports (Cody/coordination to-builder 009): "POWER ratings and
changes vs prior-day and Sunday-night snapshots". Stored daily snapshots
would drift from the model and go missing whenever a run fails (the weekly
archive missed W37-W39 exactly that way), so nothing is stored: the prior
day and the Sunday lock are RECOMPUTED by digby_top25 with
WVB_RATING_CUTOFF_EPOCH set -- the mechanism the Rankings "vs Sun lock"
column already uses. One model, one ruler, every comparison.

POWER here is the site's 0-100 scale: 50 + 12.5 * z of the blend score
across all rated teams, the same transform build_rankings_board applies.

Python 3.9 target.
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:                                      # pragma: no cover
    PT = None


def pt_midnight(day):
    """00:00 America/Los_Angeles on a date, as an epoch (DST-safe)."""
    return int(datetime.datetime(day.year, day.month, day.day, tzinfo=PT).timestamp())


def _power_table(doc):
    rows = [r for r in (doc.get("all") or []) if r.get("score") is not None]
    if len(rows) < 30:
        return {}
    vals = [r["score"] for r in rows]
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
    out = {}
    for r in rows:
        z = (r["score"] - mu) / sd
        out[r["team"]] = {"rank": r.get("rank"),
                          "power": round(max(0.0, min(100.0, 50.0 + 12.5 * z)), 1)}
    return out


def current():
    p = os.path.join(REPO, "data", "digby_top25_%d.json" % SEASON)
    doc = json.load(open(p))
    return _power_table(doc), (doc.get("meta") or {})


def as_of(epoch):
    """POWER table using only finals that started before `epoch`."""
    fd, out = tempfile.mkstemp(suffix=".json", prefix="power_asof_")
    os.close(fd)
    env = dict(os.environ, WVB_SEASON=str(SEASON), WVB_DIGBY_OUT=out,
               WVB_RATING_CUTOFF_EPOCH=str(int(epoch)))
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "digby_top25.py")],
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        if r.returncode != 0:
            raise RuntimeError("as-of recompute failed: %s"
                               % r.stdout.decode("utf-8", "replace")[-400:])
        doc = json.load(open(out))
    finally:
        if os.path.exists(out):
            os.remove(out)
    return _power_table(doc), (doc.get("meta") or {})


def week_lock_epoch(now=None):
    import digby_top25 as D
    return D.week_lock_epoch(now)


def deltas(now_tab, base_tab):
    """team -> (power change, places moved up); None where a side is missing."""
    out = {}
    for t, cur in now_tab.items():
        b = base_tab.get(t)
        if not b:
            out[t] = (None, None)
            continue
        dp = round(cur["power"] - b["power"], 1)
        dr = (b["rank"] - cur["rank"]) if (b.get("rank") and cur.get("rank")) else None
        out[t] = (dp, dr)
    return out


if __name__ == "__main__":
    today = datetime.datetime.now(PT).date()
    cur, _ = current()
    prev, _ = as_of(pt_midnight(today))
    d = deltas(cur, prev)
    for t, v in sorted(cur.items(), key=lambda kv: kv[1]["rank"])[:10]:
        print("%2d %-20s %5.1f  day %s" % (v["rank"], t, v["power"], d[t]))
