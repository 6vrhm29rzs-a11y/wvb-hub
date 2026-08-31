#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE SEASON-COUNT CONTRACT — one classification, every consumer.

Written 2026-08-30 after one build showed three season totals at once:
the masthead said 402 matches played, the rankings said through 397
finals, and the Result Ledger said 409 completed finals. All three were
"correct" -- each surface had hand-rolled its own exclusions from the raw
log, and two of them had QUIETLY DIVERGED from the exclusion ledgers:
digby's margins were folding in the two 21-point-set exhibitions, and the
rating fit's loader (bakeoff_2025.load) skipped neither duplicates nor
exhibitions and read the two ledger-corrected inverted winners at their
wrong raw values.

The contract: a final belongs to exactly ONE class, and every displayed
count is one of the NAMED totals below, computed here and nowhere else.

Classes (mutually exclusive, in precedence order):
  duplicate    a ledgered duplicate feed listing -- counts nowhere
               (data/raw/{s}/duplicate_listings.json, both schools cited)
  exhibition   a ledgered exhibition -- displayed, never counted in any
               record, rate or rating (data/raw/{s}/exhibitions.json)
  empty        a final asserting no result at all (no winner, no set
               counts, no set line) with no ledgered correction --
               visible only in the Result Ledger as official-only
  under_review a completed match whose result is DISPUTED: an independent
               official source conflicts with the feed and no curated
               correction resolves it yet (result_evidence.json entries
               with status 'conflicts', minus gids with a correction).
               Inspectable in the Result Ledger; counted NOWHERE -- not
               in records, ratings, resume, form, aggregates, Conference
               Lab, recaps or snapshots. A wrong result flowing into
               everything is worse than a late one (SMU-UC Davis,
               2026-08-30: the feed carried the true set sequence with
               the TEAMS SWAPPED, internally coherent and wrong).
  ok           a completed match that counts (result corrections from
               data/raw/{s}/result_corrections.json are applied BEFORE
               classification, so a corrected empty final is ok)

Named totals (reader-facing meaning, used verbatim on the page):
  feed_records        every completed record the feed served, all classes
                      -- the Result Ledger's population, because an audit
                      surface must show everything
  results_on_display  finals a reader can open: ok + exhibition (an
                      exhibition against good opposition is still worth
                      seeing -- Cody's rule; its badge says it counts
                      toward nothing)
  rating_eligible     ok, both sides D-I, with a per-set line -- the only
                      matches a margin can be computed from; what the
                      rankings mean by "finals in"
"""

import io
import json
import os
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFINITIONS = {
    "feed_records": ("every completed record the NCAA feed served, "
                     "including duplicate listings, exhibitions and "
                     "finals that assert no result"),
    "results_on_display": ("completed matches a reader can open -- "
                           "exhibitions and under-review results included "
                           "and badged, duplicates and empty records "
                           "excluded"),
    "rating_eligible": ("completed D-I v D-I matches with a per-set "
                        "line, exhibitions and duplicates excluded -- "
                        "the matches a rating can be computed from"),
}


def _load(path):
    if not os.path.exists(path):
        return {}
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except ValueError:
        return {}


def corrections(season):
    # type: (int) -> Dict[str, Dict]
    p = os.path.join(REPO, "data/raw/%d/result_corrections.json" % season)
    return (_load(p).get("corrections") or {})


def apply_correction(g, corr):
    # type: (Dict, Dict) -> Dict
    """One definition of applying a result correction to a game record.

    Fill-only on linescores; winner/sets replace the feed's derived
    fields. Mirrors build_dataset._apply_result_correction (which
    remains the dataset's writer; this exists for consumers that read
    the RAW log and must see the same truth)."""
    c = corr.get(str(g.get("game_id")))
    if not c:
        return g
    fix = c.get("correct") or {}
    g = dict(g)
    g["result_corrected"] = True
    if fix.get("winner_team_id"):
        g["winner_team_id"] = fix["winner_team_id"]
    ts = []
    for t in (g.get("teams") or []):
        t = dict(t)
        if fix.get("winner_team_id"):
            t["is_winner"] = (str(t.get("team_id"))
                              == str(fix["winner_team_id"]))
        if t.get("is_home") and fix.get("home_sets") is not None:
            t["sets_won"] = fix["home_sets"]
        if not t.get("is_home") and fix.get("away_sets") is not None:
            t["sets_won"] = fix["away_sets"]
        ts.append(t)
    g["teams"] = ts
    if fix.get("linescores") and (
            fix.get("linescores_replace") or not [
            l for l in (g.get("linescores") or [])
            if l.get("home") is not None]):
        # coerce to ints -- the dataset stores ints, and a correction
        # written in the feed's string convention crashed digby's margin
        # sum with int+str (2026-08-31)
        g["linescores"] = [
            {k: (int(v) if isinstance(v, str) and v.isdigit() else v)
             for k, v in r.items()} for r in fix["linescores"]]
    return g


def box_team_swaps(season):
    # type: (int) -> Dict[str, Dict[str, str]]
    """gid -> {team_id: corrected_team_id} from evidenced corrections.

    SMU-UC Davis (2026-08-30): the feed swapped TEAM ATTRIBUTION wholesale
    -- linescores AND all 33 player rows (verified: 16/16 rows under UC
    Davis's id are SMU roster players, 17/17 the reverse). The raw log is
    never rewritten; every derived consumer of player rows applies this
    map at read."""
    out = {}
    for gid, c in corrections(season).items():
        m = (c.get("correct") or {}).get("box_team_swap")
        if m:
            out[str(gid)] = {str(k): str(v) for k, v in m.items()}
    return out


def review_gids(season):
    # type: (int) -> set
    """Gids under result review: an unresolved official conflict."""
    ev = (_load(os.path.join(
        REPO, "data/raw/%d/result_evidence.json" % season))
        .get("evidence") or {})
    corr = corrections(season)
    out = set()
    for gid, entries in ev.items():
        if str(gid) in corr:
            continue                       # a curated correction resolves it
        if any(isinstance(e, dict) and e.get("status") == "conflicts"
               for e in entries):
            out.add(str(gid))
    return out


def is_empty_final(g):
    # type: (Dict) -> bool
    """A final that asserts no result: no winner, no set counts, no line."""
    if g.get("winner_team_id"):
        return False
    if any(t.get("sets_won") is not None for t in (g.get("teams") or [])):
        return False
    return not [l for l in (g.get("linescores") or [])
                if l.get("home") is not None]


def resolve(games):
    # type: (List[Dict]) -> List[Dict]
    """ONE record per gid: final beats non-final, then last-written wins.

    The audit's fixture corpus (2026-08-31) falsified the old behaviour:
    countable() fed a NON-deduped list passed a live record -- or a
    second final revision -- through alongside the final. Every caller
    happened to pass pre-deduped lists, which is exactly the kind of
    luck a contract must not rest on. The rule is gamelog's, restated
    here on an in-memory list (gamelog.load_games_jsonl owns the same
    rule for the file)."""
    best, order = {}, []
    for g in games or []:
        gid = str(g.get("game_id"))
        if gid == "None":
            continue
        prev = best.get(gid)
        if prev is None:
            order.append(gid)
            best[gid] = g
        elif (g.get("game_state") or g.get("state")) == "F" or \
                (prev.get("game_state") or prev.get("state")) != "F":
            best[gid] = g
    return [best[g] for g in order]


def classify(games, season):
    # type: (List[Dict], int) -> Dict[str, str]
    """gid -> class, for every completed record. Corrections applied first."""
    import dupes
    import exhibitions as EXH
    games = resolve(games)
    dup = dupes.duplicate_gids(season)
    exh = EXH.resolved_gids(season)
    corr = corrections(season)
    review = review_gids(season)
    out = {}
    for g in games:
        state = g.get("game_state") or g.get("state")
        if state != "F":
            continue
        gid = str(g.get("game_id"))
        if gid in dup or g.get("duplicate_of"):
            out[gid] = "duplicate"
        elif gid in exh:
            out[gid] = "exhibition"
        elif gid in review:
            out[gid] = "under_review"
        elif is_empty_final(apply_correction(g, corr)):
            out[gid] = "empty"
        else:
            out[gid] = "ok"
    return out


def _d1_both(g):
    ts = g.get("teams") or []
    return len(ts) == 2 and all(t.get("division") == 1 for t in ts)


def _has_line(g):
    return bool([l for l in (g.get("linescores") or [])
                 if l.get("home") is not None])


def totals(games, season):
    # type: (List[Dict], int) -> Dict[str, int]
    """The named totals, from ONE list of game records (one snapshot)."""
    games = resolve(games)
    cls = classify(games, season)
    corr = corrections(season)
    by = {str(g.get("game_id")): g for g in games
          if (g.get("game_state") or g.get("state")) == "F"}
    n = {"feed_records": len(cls),
         "duplicate": sum(1 for v in cls.values() if v == "duplicate"),
         "exhibition": sum(1 for v in cls.values() if v == "exhibition"),
         "under_review": sum(1 for v in cls.values()
                             if v == "under_review"),
         "empty": sum(1 for v in cls.values() if v == "empty"),
         "ok": sum(1 for v in cls.values() if v == "ok")}
    # under_review stays ON DISPLAY (badged, inspectable) while counting
    # nowhere -- hiding a disputed row would bury the dispute
    n["results_on_display"] = n["ok"] + n["exhibition"] + n["under_review"]
    n["rating_eligible"] = sum(
        1 for gid, v in cls.items()
        if v == "ok"
        and _d1_both(by[gid])
        and _has_line(apply_correction(by[gid], corr)))
    return n


def countable(games, season, need_line=False, d1_only=False):
    # type: (List[Dict], int, bool, bool) -> List[Dict]
    """The 'ok' games, corrections applied -- THE list a counting consumer
    iterates. need_line/d1_only narrow to the rating-eligible subset."""
    games = resolve(games)
    cls = classify(games, season)
    corr = corrections(season)
    out = []
    for g in games:
        gid = str(g.get("game_id"))
        if cls.get(gid) != "ok":
            continue
        g = apply_correction(g, corr)
        if need_line and not _has_line(g):
            continue
        if d1_only and not _d1_both(g):
            continue
        out.append(g)
    return out
