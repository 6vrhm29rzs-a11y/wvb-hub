#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture the published rankings daily: the AVCA coaches poll and the NCAA RPI.

WHY THIS EXISTS. The AVCA poll was captured ONCE, by hand, into
`avca_poll_2026-08-18.json`, and `build_rankings_board.py` loaded that exact
filename. Nothing refreshed it. The poll updates weekly all season, so the page
would have shown the PRESEASON poll in November while telling the reader it was
the AVCA poll -- and the one thing this hub is for is not having to go and check
the AVCA site.

⚠ THE RANKINGS ENDPOINT IS CURRENT-ONLY. It cannot be season-pinned; every
pinned variant 404s. So a poll not captured on the day it was published is gone.
That is why each run writes a DATED capture and the history is append-only:
these files are the only record of what the poll said at the time, and they
cannot be rebuilt later.

Captures are skipped when the source has not moved -- the poll carries a
"Through Games ..." label, so a re-run on the same publication is a no-op rather
than a duplicate row.

Python 3.9 target.
"""

import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://ncaa-api.henrygd.me"
UA = ("wvb-hub/0.1 (personal research project; "
      "contact via github.com/6vrhm29rzs-a11y/wvb-hub)")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))

FEEDS = {
    "avca": "rankings/volleyball-women/d1/avca-rankings",
    "rpi": "rankings/volleyball-women/d1/ncaa-womens-volleyball-rpi",
    # The selection committee's own in-season reveal. This is the closest
    # published thing to what the field projector is trying to predict -- the
    # committee stating its own resume judgement -- so missing a week of it is
    # a real loss. It only appears late in the season, and like every ranking
    # here the endpoint is current-only: uncaptured is gone.
    "top16": "rankings/volleyball-women/d1/di-committees-top-16",
}


SEASON_RE = re.compile(r"(20\d{2})")


def data_season(stamp, default):
    """The season the DATA describes -- NOT the season we captured it in.

    ⚠ These are different, and conflating them is how 2025 ends up on a 2026
    page. The rankings endpoint is CURRENT-ONLY, and "current" means the last
    thing published: in August 2026 the RPI feed still serves the FINAL 2025
    table ("Through Games Dec. 21 2025", Nebraska 33-1). Filing that under 2026
    would put last season's finished table inside this season's data.

    A volleyball season runs Aug-Dec within one calendar year, so the year in
    the stamp IS the season.
    """
    m = SEASON_RE.search(stamp or "")
    return int(m.group(1)) if m else default


def fetch(path):
    req = urllib.request.Request(API + "/" + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    os.makedirs(RAW, exist_ok=True)
    today = datetime.datetime.utcnow()
    wrote = 0

    for name, path in FEEDS.items():
        try:
            payload = fetch(path)
        except (urllib.error.URLError, urllib.error.HTTPError,
                ValueError, OSError) as exc:
            print("  %-5s FAILED %s" % (name, exc))
            continue

        rows = payload.get("data") or payload.get("rows") or []
        # the poll's own "Through Games ..." stamp is the identity of a
        # publication; re-running on the same one must not add a row
        stamp = str(payload.get("updated") or "")
        # FILE IT UNDER THE SEASON IT DESCRIBES, not the season we are running.
        ds = data_season(stamp, SEASON)
        raw_dir = os.path.join(REPO, "data", "raw", str(ds))
        os.makedirs(raw_dir, exist_ok=True)
        out = os.path.join(raw_dir, "polls_%s.jsonl" % name)

        seen = set()
        if os.path.exists(out):
            with open(out) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        seen.add(json.loads(line).get("stamp"))
                    except ValueError:
                        continue
        if stamp and stamp in seen:
            print("  %-5s unchanged (%s) -- no new row" % (name, stamp[:40]))
            continue

        rec = {
            "captured_utc": today.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date": today.date().isoformat(),
            "season": ds,
            "captured_during_season": SEASON,
            "is_previous_season": ds != SEASON,
            "stamp": stamp,
            "title": payload.get("title"),
            "source_tier": "OFFICIAL",
            "source": "%s/%s" % (API, path),
            "note": ("The rankings endpoint is CURRENT-ONLY and cannot be "
                     "season-pinned. This capture is the only record of what "
                     "this ranking said on this date."),
            "rows": rows,
        }
        with open(out, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        wrote += 1
        flag = "" if ds == SEASON else "  <-- %d DATA, filed under %d" % (ds, ds)
        print("  %-5s captured %d rows (%s)%s"
              % (name, len(rows), stamp[:40] or "no stamp", flag))

    print("done: %d new capture(s)" % wrote)
    return 0


if __name__ == "__main__":
    sys.exit(main())
