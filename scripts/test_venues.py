#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for neutral-site detection.

The failure this prevents is quiet arithmetic, not a crash. The rating solves
for a home-advantage coefficient, and a match played on a neutral floor has no
home advantage to attribute. The 2026 season opened with two of its three
matches at Fiserv Forum in Milwaukee -- AVCA First Serve, with Wisconsin and
Texas A&M listed at home purely as bookkeeping. Credit them a home edge and
every rating built from that weekend is wrong by a little, permanently, with
nothing to see in any log.

The two rules under test:
  1. MULTI-HOST. A real home floor has exactly one home team. A venue with
     several, and no dominant one, is nobody's home.
  2. MODAL VENUE. Once a team has played enough home matches, the venue it is
     usually home in IS its home; anywhere else is neutral.

And the abstention that matters as much as either: with too little played, a
match is "unknown", never "neutral". Guessing moves a rating.

Python 3.9 target. Run: python3 scripts/test_venues.py
"""

import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILED = []


def test_event_candidates_are_one_occasion():
    """An event candidate must be a run of dates, not a whole venue's season.

    PAID FOR. The detector grouped every neutral match at a building into one
    candidate, so Fiserv Forum reported "9 matches, 2026-08-21 to 2026-11-13" --
    the eight of the AVCA First Serve plus one unrelated November match, offered
    as a single tournament spanning three months. The candidate list exists so a
    human can NAME events in Cody/data/events_2026.txt, and a cluster that is not
    one occasion cannot be given one name.

    The invariant: inside a candidate, consecutive dates never differ by more
    than EVENT_GAP_DAYS. A college tournament runs over a weekend, sometimes a
    week; a longer gap is a different occasion.
    """
    import json as _json
    import venues as V
    p = os.path.join(REPO, "data", "venues_%d.json" % V.SEASON)
    if not os.path.exists(p):
        print("  skip (no venue classification yet)")
        return
    doc = _json.load(open(p))
    worst = None
    bad_n = 0
    for e in (doc.get("events") or []):
        a, b = e.get("first_date"), e.get("last_date")
        if not (a and b):
            continue
        span = V._days_between(a, b)
        # a run of N matches can legitimately be longer than one gap, so the
        # span is bounded by gap * (matches - 1) at the very worst
        limit = V.EVENT_GAP_DAYS * max(1, e.get("matches", 1) - 1)
        if span > limit:
            bad_n += 1
            if worst is None or span > worst[1]:
                worst = (e.get("venue"), span, e.get("matches"))
    check("no event candidate spans longer than its own match count allows",
          bad_n, 0)
    if worst:
        print("     worst: %s spans %d days over %d matches" % worst)


def check(name, got, want):
    ok = got == want
    print("  %-60s %s" % (name, "ok" if ok else "FAIL (got %r, want %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


def game(gid, home_id, away_id, venue, city="X", state="ZZ", state_code="F"):
    return {
        "game_id": gid, "game_state": state_code,
        "location": {"venue": venue, "city": city, "state": state} if venue else None,
        "teams": [
            {"team_id": home_id, "is_home": True, "name_short": "H" + home_id},
            {"team_id": away_id, "is_home": False, "name_short": "A" + away_id},
        ],
        "linescores": [],
    }


def run(games, season=2026):
    """Build venue classifications from a synthetic game log."""
    tmp = tempfile.mkdtemp(prefix="wvb-venues-")
    try:
        raw = os.path.join(tmp, "data", "raw", str(season))
        os.makedirs(raw)
        with open(os.path.join(raw, "games.jsonl"), "w") as fh:
            for g in games:
                fh.write(json.dumps(g) + "\n")
        import venues
        prev_games, prev_out, prev_season = venues.GAMES, venues.OUT, venues.SEASON
        venues.GAMES = os.path.join(raw, "games.jsonl")
        venues.OUT = os.path.join(tmp, "out.json")
        venues.SEASON = season
        try:
            out = venues.build()
        finally:
            venues.GAMES, venues.OUT, venues.SEASON = prev_games, prev_out, prev_season
        return {r["game_id"]: r["site"] for r in out["games"]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("NEUTRAL-SITE GUARDS\n")

    print("0. Event candidates are a single occasion, not a venue's season")
    test_event_candidates_are_one_occasion()

    print("1. Multi-host venue with no dominant team is neutral (the Fiserv case)")
    sites = run([
        game("g1", "wisc", "uk", "Fiserv Forum"),
        game("g2", "tamu", "lou", "Fiserv Forum"),
    ])
    check("Kentucky at 'Wisconsin' on a shared floor is neutral", sites["g1"], "neutral")
    check("Louisville at 'Texas A&M' on the same floor is neutral", sites["g2"], "neutral")

    print("\n2. A school hosting a tournament is still at home in its own matches")
    # host plays 3 matches at its own gym; two visitors meet there once
    gs = [game("h%d" % i, "host", "v%d" % i, "Host Gym") for i in range(3)]
    gs.append(game("x1", "v9", "v8", "Host Gym"))
    sites = run(gs)
    check("the host's own matches stay home", sites["h0"], "home")
    check("two visitors meeting in the host's gym is neutral", sites["x1"], "neutral")

    print("\n3. Once a home venue is established, elsewhere is neutral")
    gs = [game("a%d" % i, "team", "opp%d" % i, "Home Arena") for i in range(4)]
    gs.append(game("away1", "team", "opp9", "Some Other Arena"))
    sites = run(gs)
    check("matches in the usual arena are home", sites["a0"], "home")
    check("a 'home' match somewhere else is neutral", sites["away1"], "neutral")

    print("\n4. It abstains rather than guessing")
    sites = run([game("solo", "t1", "t2", "Unknown Gym")])
    check("one match at one venue is 'unknown', not 'neutral'", sites["solo"], "unknown")
    sites = run([game("nov", "t1", "t2", None)])
    check("a match with no venue reported is 'no-venue'", sites["nov"], "no-venue")

    print("\n5. The rating actually consumes it")
    # bakeoff reads its season at import time, and _site_factor looks for
    # venues_{SEASON}.json -- so this has to be imported in 2026's context or it
    # correctly finds nothing and correctly returns the ordinary home sign.
    os.environ["WVB_SEASON"] = "2026"
    import bakeoff_2025 as B
    B._SITE_CACHE.clear()
    real = os.path.join(REPO, "data", "venues_2026.json")
    if os.path.exists(real):
        v = json.load(open(real))
        neutral = [r["game_id"] for r in v["games"] if r["site"] == "neutral"]
        if neutral:
            check("a neutral match contributes no home term",
                  B._site_factor(neutral[0]), 0)
        else:
            print("  %-60s %s" % ("(no neutral match on record yet to check)", "skip"))
        check("an unclassified match keeps the ordinary home term",
              B._site_factor("no-such-game"), 1)
    else:
        print("  %-60s %s" % ("(data/venues_2026.json not built yet)", "skip"))

    print()
    if FAILED:
        print("FAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - %s" % f)
        return 1
    print("ALL NEUTRAL-SITE GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
