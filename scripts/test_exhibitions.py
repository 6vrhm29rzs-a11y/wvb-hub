#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for matches that do not count.

⚠ THE FEED CANNOT TELL US AN EXHIBITION FROM A REAL MATCH. Checked game
6640217 on the night it was played: no type, no gameType, no exhibition field,
`division: 1`, and both teams showing `record (0-0)`. It is byte-for-byte an
ordinary fixture. So the ledger is maintained BY HAND with a source per entry.

⚠ AND GETTING THIS WRONG IS NOT COSMETIC. Spikes Under the Lights plays its
first two sets to 21 rather than 25 (huskers.com match notes, 2026-08-26).
Every rate in this hub is per SET, so folding one in deflates points per set,
swings per set, the opponent adjustment and the rally model for four of the
best teams in the country -- and nothing on screen would look wrong. The
format is also the proof it cannot be an NCAA result: the playing rules put a
set at 25.

Python 3.9 target. Run: python3 scripts/test_exhibitions.py
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-68s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    import build_hub as B

    print("1. THE LEDGER")
    exh = B.exhibitions()
    check("the exhibition ledger loads", isinstance(exh, dict) and len(exh) >= 2,
          "%d entries" % len(exh))
    check("every entry names a source",
          all((v or {}).get("source") for v in exh.values()),
          "an entry with no source is a guess wearing a fact's clothes")
    check("every entry says it does not count",
          all((v or {}).get("counts_toward_record") is False
              for v in exh.values()))
    doc = json.load(io.open(os.path.join(
        REPO, "data/raw/2026/exhibitions.json"), encoding="utf-8"))
    check("the file records WHY the feed cannot answer this",
          "no type, gameType or exhibition field" in
          json.dumps(doc.get("meta") or {}),
          "the next reader will otherwise try to automate it")

    print("\n2. RESULTS MARK THEM RATHER THAN DROPPING THEM")
    # ⚠ MARKED, NOT DELETED. Cody's point: a match against good opposition
    # still says something about a team even when it does not count.
    src = io.open(os.path.join(REPO, "scripts/build_hub.py"),
                  encoding="utf-8").read()
    check("results() carries an exhibition flag",
          '"exhibition": bool(_exh_hit)' in src)
    check("the build splits counting results from displayable ones",
          'res_cnt = [r for r in res if not r.get("exhibition")]' in src)
    for fn in ("box_and_players(res_cnt", "team_season_stats(boxes, res_cnt)",
               "standings(teams, res_cnt)", "team_index(teams, res_cnt"):
        check("...and %s uses it" % fn.split("(")[0], fn in src,
              "this one would count an exhibition into a record or a rate")

    print("\n3. THE FILTER ACTUALLY WORKS -- ON A SYNTHETIC EXHIBITION")
    # ⚠ REHEARSED RATHER THAN WAITED FOR. The real matches are not crawled yet,
    # and finding out at 2:15am that four teams' records were wrong is not a
    # test, it is a discovery.
    fake = [
        {"gid": "X1", "date": "2026-08-27", "epoch": 1, "away": "Florida",
         "home": "Nebraska", "away_sets": 0, "home_sets": 2,
         "away_rank": None, "home_rank": None,
         "away_d1": True, "home_d1": True, "time": "", "loc": None,
         "sets": [[18, 21], [19, 21]], "exhibition": True,
         "exhibition_event": "Spikes Under the Lights"},
        {"gid": "X2", "date": "2026-08-30", "epoch": 2, "away": "Texas",
         "home": "Nebraska", "away_sets": 1, "home_sets": 3,
         "away_rank": None, "home_rank": None,
         "away_d1": True, "home_d1": True, "time": "", "loc": None,
         "sets": [[25, 22], [20, 25], [23, 25], [21, 25]], "exhibition": False},
    ]
    counting = [r for r in fake if not r.get("exhibition")]
    teams = [{"team": "Nebraska", "conf": "Big Ten", "rank26": 1},
             {"team": "Florida", "conf": "SEC", "rank26": 17},
             {"team": "Texas", "conf": "SEC", "rank26": 2}]
    st = B.standings(teams, counting)
    neb = None
    for rows in st.values():
        for r in rows:
            if r["team"] == "Nebraska":
                neb = r
    check("Nebraska's record counts only the match that counted",
          neb is not None and (neb["w"], neb["l"]) == (1, 0),
          "got %r" % ((neb["w"], neb["l"]) if neb else None,))
    # the same table built WITHOUT the filter must disagree -- otherwise this
    # test would pass even if the filter did nothing
    st_all = B.standings(teams, fake)
    neb_all = None
    for rows in st_all.values():
        for r in rows:
            if r["team"] == "Nebraska":
                neb_all = r
    check("[NEG] counting the exhibition really does change the record",
          neb_all is not None and (neb_all["w"], neb_all["l"]) != (neb["w"], neb["l"]),
          "the filter is a no-op, so this guard proves nothing")

    print("\n%s" % ("ALL EXHIBITION GUARDS PASS" if not FAILS
                    else "FAILED: %s" % FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
