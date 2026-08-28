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
    # ⚠ box_and_players IS DELIBERATELY NOT ON THIS LIST. It takes the FULL
    # list, because its box scores are the log; only its season aggregate is
    # restricted, via count_gids. Section 2b checks that half.
    for fn in ("team_season_stats(boxes, res_cnt)",
               "standings(teams, res_cnt)", "team_index(teams, res_cnt"):
        check("...and %s uses it" % fn.split("(")[0], fn in src,
              "this one would count an exhibition into a record or a rate")

    print("\n2b. LOGGED, NOT COUNTED -- THE BOX SCORE STILL EXISTS")
    # ⚠ THE FIRST FIX OVER-CORRECTED. Passing only the counting matches to
    # box_and_players kept the exhibition out of every rate, and also gave it
    # NO BOX SCORE -- a night against Nebraska simply vanished. Cody asked for
    # the opposite: out of the ratings, but logged.
    check("boxes are built from every match",
          "boxes, plist = box_and_players(res, player_photos()" in src,
          "passing res_cnt here deletes the match instead of discounting it")
    check("...while the season totals take only what counts",
          "count_gids=[r[\"gid\"] for r in res_cnt]" in src)
    check("the row still reaches the box score before the skip",
          src.find("rows.append(row)", src.find("def box_and_players")) <
          src.find("_skipped_from_totals.add(gid)"),
          "skipping before the append would drop the line from the box too")

    print("\n2c. A RULE CATCHES WHAT THE ID LEDGER CANNOT")
    # ⚠ THE CHAMPIONSHIP MATCH HAD NO GAME ID while the semi-finals were being
    # played -- the scoreboard lists it only once the field is known. An
    # id-only ledger would have missed it and the 2:15am crawl would have
    # counted a result that does not exist into two teams' records.
    rules = B.exhibition_rules()
    check("a venue+date rule exists", bool(rules), "id-only has a deadline")
    check("...and it names a venue and a date",
          all((r.get("match_on") or {}).get("venue")
              and (r.get("match_on") or {}).get("date") for r in rules))
    check("...and says it does not count",
          all(r.get("counts_toward_record") is False for r in rules))
    check("results() consults the rules, not just the ids",
          "_exh_rules = exhibition_rules()" in src and
          'if not _exh_hit and _exh_rules:' in src)

    print("\n2d. THE RATING PIPELINE, NOT JUST THE DISPLAY")
    # ⚠ THE REVIEW THAT FOUND THIS IS THE POINT. The first pass put the filter
    # in build_hub.py alone: records, standings and per-set rates on the PAGE
    # were right, while build_dataset.py -- the dataset the RATING, the RPI,
    # the simulator and the field projector all read -- filtered on
    # `game_state == "F"` and nothing else. An exhibition is final too. Cody's
    # instruction was "keep the stats out of the ratings and rankings"; the
    # display was the half that mattered least.
    import exhibitions as X
    check("there is ONE shared definition of a non-counting match",
          hasattr(X, "is_exhibition") and hasattr(X, "resolved_gids"))
    gids = X.resolved_gids(2026)
    check("it resolves the known exhibition ids", len(gids) >= 2, str(sorted(gids)))
    bd = io.open(os.path.join(REPO, "scripts/build_dataset.py"),
                 encoding="utf-8").read()
    check("build_dataset excludes them from the RATING dataset",
          "_EXH.is_exhibition(g, SEASON, _local_date(g))" in bd,
          "filtering on game_state alone lets a final exhibition through")
    check("...using a PACIFIC date, not UTC",
          "America/Los_Angeles" in bd,
          "a UTC date pushes a 5pm Pacific match to the next day and the "
          "venue rule silently never fires")
    cr = io.open(os.path.join(REPO, "scripts/crawl_2025.py"),
                 encoding="utf-8").read()
    check("the player season aggregate excludes them too",
          "_skip_gids" in cr and "resolved_gids(SEASON)" in cr,
          "this file becomes per-set player rates; a 21-point set deflates them")

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

    print("\nEVERY VIEW THAT SHOWS THE FIXTURE SAYS IT DOES NOT COUNT")
    # ⚠ ONE FIXTURE, TWO ANSWERS ON ONE PAGE. The Scoreboard tagged these EXH
    # and the Schedule did not -- and the answer the Schedule gave was the
    # misleading one: it labelled them "non-conf", which describes a match that
    # counts. Florida-Nebraska and SMU-Penn St. count toward nobody's record.
    # Both badges are now built from the same hand-maintained ledger.
    import os as _o
    _hub = _o.path.join(REPO, "Cody", "START-HERE.html")
    if not _o.path.exists(_hub):
        print("  --   no built page; skipping")
    else:
        h = open(_hub, encoding="utf-8").read()
        # (this module already binds the ledger via B.exhibitions() at the top
        #  of main; `EX` was a name I invented and nothing defines it)
        led = B.exhibitions()
        gids = sorted(led)
        check("[+] there are exhibitions on file to check", len(gids) > 0,
              "%d" % len(gids))
        # the scoreboard/desk row helper
        check("the row helper tags an exhibition", "function exhTag(m)" in h)
        # ⚠ THE SCHEDULE SHOWS TODAY FORWARD, SO THIS CANNOT ASSERT A BADGE
        # UNCONDITIONALLY. The first version required `class="kind exh"` to be
        # present, which was true while the Spikes Under the Lights fixtures
        # were upcoming and became FALSE the morning after they were played --
        # a guard that fails on a date rather than on a regression. Check the
        # mechanism always, and the rendered badge only when an exhibition is
        # actually inside the range the table draws.
        src_ = open(_o.path.join(REPO, "scripts", "build_hub.py"),
                    encoding="utf-8").read()
        check("the schedule renderer has an exhibition branch",
              'class="kind exh"' in src_ and "_sched_exh" in src_,
              "a fixture that does not count must not read as 'non-conf' alone")
        # is any exhibition still in the displayed range (today forward)?
        import datetime as _dt
        import re as _re2
        _today = _dt.date.today().isoformat()
        _m = _re2.search(r"const FIXTURES = (\{)", h)
        _upcoming = 0
        if _m:
            _i = _m.start(1)
            _d, _j, _in, _es = 0, _i, False, False
            while _j < len(h):
                _c = h[_j]
                if _in:
                    if _es:
                        _es = False
                    elif _c == "\\":
                        _es = True
                    elif _c == '"':
                        _in = False
                elif _c == '"':
                    _in = True
                elif _c in "[{":
                    _d += 1
                elif _c in "]}":
                    _d -= 1
                    if _d == 0:
                        break
                _j += 1
            _fx = json.loads(h[_i:_j + 1])
            _upcoming = sum(1 for f in _fx.values()
                            if str(f.get("gid")) in led and (f.get("d") or "") >= _today)
        if _upcoming:
            check("...and the table actually renders it",
                  'class="kind exh"' in h, "%d upcoming exhibition(s)" % _upcoming)
        else:
            print("  --   no exhibition in the displayed range today; "
                  "mechanism checked, badge not applicable")
        check("...and says what it means, not just that it is one",
              "does not count toward either record" in h)
        # and the badge is not invented per-view: one ledger, both readers
        # the page must not carry a second, inlined copy of the ledger
        check("[-] neither view keeps its own list of exhibitions",
              "_sched_exh" not in h,
              "the ledger must not be inlined into the page twice")

    print("\n%s" % ("ALL EXHIBITION GUARDS PASS" if not FAILS
                    else "FAILED: %s" % FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
