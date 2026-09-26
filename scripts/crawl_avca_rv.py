#!/usr/bin/env python3
"""AVCA 'others receiving votes' -- the part of the poll ncaa.com does not carry.

Cody 2026-09-25: rank badges should read 1-25, RV or NR for every team, and
"you can see the receiving votes on the avca site ballot". The ncaa.com
rankings endpoint (crawl_polls.py) serves the Top 25 only; AVCA publishes the
full poll, receiving votes included, as a weekly .xlsx linked from
avca.org/polls-awards/polls (open, 200, docs/data_sources.md).

Appends one row per poll date to data/raw/2026/avca_rv.jsonl, only when the
poll date moves (append-only, like polls_avca.jsonl). RV means "listed on two
or more ballots" -- AVCA names only those; the teams on a single ballot are
counted but not named, so they stay NR rather than being guessed at.

Python 3.9 target.
"""
import datetime
import io
import json
import os
import re
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "raw", str(SEASON), "avca_rv.jsonl")
INDEX = ("https://www.avca.org/polls-awards/polls/?_season=%d"
         "&_divisions=division-i-women" % SEASON)
UA = {"User-Agent": "wvb-hub/0.1"}


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                  timeout=30).read()


def parse(xlsx_bytes):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb.worksheets[0]
    title, ranked, rv = None, [], []
    for row in ws.iter_rows(values_only=True):
        cells = [c for c in row if c is not None]
        if not cells:
            continue
        first = str(cells[0])
        if title is None and "Poll" in first:
            title = first
        if isinstance(row[0], (int, float)) and row[1]:
            ranked.append({"rank": int(row[0]), "school": str(row[1]).strip()})
        m = re.search(r"receiving votes[^:]*:\s*(.*)", first, re.I)
        if m:
            for part in m.group(1).replace("\xa0", " ").split(";"):
                pm = re.match(r"\s*(.+?)\s+(\d+)\s*$", part)
                if pm:
                    rv.append({"school": pm.group(1).strip(),
                               "points": int(pm.group(2))})
    return title, ranked, rv


def hub_name(school, hub):
    from external_refs import _ref_norm
    key = _ref_norm(school)
    return hub.get(key)


def main():
    html = fetch(INDEX).decode("utf-8", "replace")
    links = sorted(set(re.findall(
        r"https://www\.avca\.org/wp-content/uploads/[^\"']+?-AVCA-Division-I-WVB-Poll\.xlsx",
        html)))
    if not links:
        print("no AVCA poll workbook linked -- nothing captured")
        return 0
    url = links[-1]
    m = re.search(r"/(\d\d)-(\d\d)-(\d\d)-AVCA", url)
    poll_date = "20%s-%s-%s" % (m.group(3), m.group(1), m.group(2)) if m else None
    last = None
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            if line.strip():
                last = json.loads(line)
    if last and last.get("poll_date") == poll_date:
        print("avca rv unchanged (%s) -- no new row" % poll_date)
        return 0
    title, ranked, rv = parse(fetch(url))
    teams = (json.load(open(os.path.join(REPO, "data", "digby_top25_%d.json" % SEASON)))
             .get("all") or [])
    from external_refs import _ref_norm
    hub = dict((_ref_norm(t["team"]), t["team"]) for t in teams)
    for r in rv + ranked:
        r["team"] = hub_name(r["school"], hub)
    unmatched = [r["school"] for r in rv + ranked if not r["team"]]
    row = {"captured_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "poll_date": poll_date, "title": title, "source": url,
           "source_tier": "OFFICIAL", "ranked": ranked, "receiving_votes": rv,
           "rv_rule": "named = listed on two or more ballots (AVCA's own rule); "
                      "single-ballot teams are not named and stay NR",
           "unmatched": unmatched}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print("avca rv captured %s: %d ranked, %d receiving votes%s"
          % (poll_date, len(ranked), len(rv),
             ("; UNMATCHED %s" % unmatched) if unmatched else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
