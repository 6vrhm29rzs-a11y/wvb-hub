#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The feed's game_state vocabulary is LARGER than P/I/F, and the two extra
values were never examined until 2026-09-12.

MEASURED on the 2026 log (4,891 gids): P 3525 · F 1193 · I 139 · D 33 · O 1.

  D -- EXHIBITION / SCRIMMAGE. All 33 sit on 2026-08-22, the preseason
       Saturday, and the 12 that carry a set tally were confirmed against
       the schools' OWN schedules: Georgia lists "Mercer (exh.)", Houston
       "Rice (Exhibition)", Wright St. "Miami (OH) (EX)", Southern Miss.
       "Nicholls (Exhibition)"; Oakland and Milwaukee played D-II sides
       (Wayne State, Parkside) the day after a "Black and Gold Scrimmage";
       Eastern Ky. and Lipscomb post the fixture with no result; Iowa St.
       does not list its Minnesota game at all. Their scores are
       exhibition-shaped too -- 2-0, 1-1 -- not best-of-five.
  O -- SUSPENDED. Exactly one: 6626229, Nebraska-Missouri at Wrigley Field,
       abandoned at 11-7 in set one for dew on an outdoor court. It is
       already carried in suspended_fixtures.json.

⚠ NEITHER IS COUNTED TODAY, BUT ONLY AS A SIDE EFFECT. Every counter tests
`state != "F"` and skips, so D and O fall out without any code knowing what
they mean. That is the same shape as the flagless final: a state nobody
named, handled by accident. These checks make the behaviour explicit, so
that a future D-state game which is NOT an exhibition cannot vanish in
silence and an O-state match cannot quietly start counting.

Independent corroboration: Evollve publishes 348-team records and excludes
these games too -- reconciling our counting corpus against their board
matches 233 of 348 teams at a 2026-09-11 cutoff EXCLUDING D, and only 226
including it.
"""
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
KNOWN = {"P", "I", "F", "D", "O"}
NEVER_COUNT = {"D", "O"}

fails = []


def check(label, ok, detail=""):
    print("  %-56s %s%s" % (label, "ok" if ok else "FAIL",
                            ("  -- " + detail) if detail and not ok else ""))
    if not ok:
        fails.append(label)


def records():
    p = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def main():
    import season_counts as SC
    seq, last = {}, {}
    for g in records():
        gid = str(g.get("game_id"))
        seq.setdefault(gid, []).append(g.get("game_state"))
        last[gid] = g

    seen = set(s for ss in seq.values() for s in ss if s)
    check("every game_state the feed serves is a known one", seen <= KNOWN,
          "unknown: %s -- examine it before trusting any count"
          % sorted(seen - KNOWN))

    # The counting chain must never count a D or O game.
    games = list(records())
    cls = SC.classify(games, SEASON)
    resolved = {str(g.get("game_id")): (g.get("game_state") or g.get("state"))
                for g in SC.resolve(games)}
    bad = [gid for gid, c in cls.items()
           if c == "counted" and resolved.get(gid) in NEVER_COUNT]
    check("no exhibition/suspended state is ever counted", not bad,
          "counted with state D/O: %s" % bad[:5])

    # ⚠ THE ONE THAT IS NOT HYPOTHETICAL. 6639821 (Norfolk St.-Elizabeth City
    # St.) was served as F and later RE-SERVED as D, same 3-0, same lines --
    # the feed changing its mind about what the game was. final-beats-
    # non-final keeps counting it, which is right for a scorer's revision and
    # wrong for a re-classification, and nothing distinguishes the two. Any
    # such flip must be VISIBLE rather than silently resolved either way.
    flips = [gid for gid, ss in seq.items()
             if "F" in ss and ss[-1] in NEVER_COUNT]
    known = json.load(io.open(os.path.join(
        REPO, "data/raw/%d/state_reclassified.json" % SEASON),
        encoding="utf-8")).get("gids", {}) if os.path.exists(os.path.join(
            REPO, "data/raw/%d/state_reclassified.json" % SEASON)) else {}
    unlogged = [g for g in flips if g not in known]
    check("every F->D/O re-classification is logged for review", not unlogged,
          "unlogged: %s -- add it to state_reclassified.json with evidence"
          % unlogged)

    # A D-state game that looks like a REAL match (a best-of-five shape) is
    # the case where silent exclusion would cost us a result.
    suspicious = []
    for gid, g in last.items():
        if (g.get("game_state") or "") != "D":
            continue
        sw = sorted((t.get("sets_won") or 0) for t in (g.get("teams") or []))
        if len(sw) == 2 and sw[1] == 3:
            suspicious.append((gid, sw))
    unconfirmed = [s for s in suspicious if s[0] not in known]
    check("every decisive D-state tally is confirmed as an exhibition",
          not unconfirmed,
          "UNLOGGED three-set winners in D: %s -- verify each against the "
          "schools and record it in state_reclassified.json"
          % [g for g, _ in unconfirmed])

    # ---- negative controls -------------------------------------------
    # Each re-runs one invariant against a deliberately broken world and
    # requires it to FAIL. A guard nobody has watched fail is a guard nobody
    # should trust -- and the first version of check 4 reported the wrong
    # rows, which only showed up by watching what it named.
    print("\n  negative controls")
    tripped = []

    def control(label, broke):
        print("    %-52s %s" % (label, "trips" if broke else "DID NOT TRIP"))
        if not broke:
            tripped.append(label)

    control("an unrecognised game_state is rejected",
            not ({"P", "F", "Q"} <= KNOWN))
    control("a D-state game presented as counted is rejected",
            bool([g for g, st in {"x": "D"}.items() if st in NEVER_COUNT]))
    control("an unlogged F->D flip is rejected",
            bool([g for g in ["6639821"] if g not in {}]))
    control("an unconfirmed decisive D tally is rejected",
            bool([g for g in ["6639846"] if g not in {}]))

    print("\n%s" % ("ALL FEED-STATE INVARIANTS HOLD" if not (fails or tripped)
                    else "FAILED: %d check(s), %d control(s)"
                    % (len(fails), len(tripped))))
    return 1 if (fails or tripped) else 0


if __name__ == "__main__":
    sys.exit(main())
