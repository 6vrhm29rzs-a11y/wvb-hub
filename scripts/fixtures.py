#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ONE CANONICAL FIXTURE PER GAME ID, and an honest account of what conflicts.

⚠ THE PROBLEM THIS REPLACES. Fixture facts were assembled independently by
each view from three sources that disagree:
  - the SCOREBOARD (data/raw/2026/scoreboard/<date>.json) enumerates fixtures
    and carries teams, rank, start time -- and NO location at all;
  - GAME DETAIL (data/raw/2026/games.jsonl) carries location and is_home, and
    is APPEND-ONLY, so one id can hold up to 6 records that disagree;
  - venues_2026.json derives site/event from the above.
The old dedup was "final beats non-final, then last wins". Measured on the real
file: 8,836 records over 4,856 ids, 1,048 ids with more than one record, and
among those 37 disagree on state, 34 on start time, 26 on location and 5 flip
which side is home. ⚠ AND NOT ONE RECORD CARRIES A CRAWL TIMESTAMP. "Last
wins" therefore means "whichever line the crawler happened to append last",
which is physical file order dressed up as recency.

⚠ THE RULE HERE IS DELIBERATELY NOT "PICK A WINNER". For a COMPLETED match,
final detail supersedes pregame -- a result is later by definition. For a
FUTURE fixture, disagreement about teams, time, site, venue or event is
recorded as a CONFLICT and the field is returned as unconfirmed, because with
no timestamps there is no honest basis for preferring one snapshot over
another. A view then says "schedule conflict -- verify" instead of asserting
one of two things it cannot choose between.

⚠ CORRECTIONS WIN ONLY WHERE THEY WERE VERIFIED. An official-school entry in
data/raw/2026/fixture_corrections.json overrides exactly the fields it lists
and nothing else; every other field stays sourced from the NCAA record.

Python 3.9 target.
"""

import collections
import glob
import json
import os
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))

# fields whose disagreement on a FUTURE fixture is material enough to block a
# confident render. Rank is not here: it moves weekly by design.
MATERIAL = ("teams", "start_time_epoch", "site", "venue", "city", "event")

SITE_HOME = "home"
SITE_AWAY = "away"
SITE_NEUTRAL = "neutral"
SITE_UNCONFIRMED = "unconfirmed"


def _load(rel):
    p = os.path.join(REPO, rel)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except ValueError:
        return None


def valid_correction(c):
    # type: (Dict[str, Any]) -> bool
    """⚠ AN ENTRY WITHOUT PROVENANCE IS NOT A CORRECTION, IT IS AN OPINION.

    Lifted out of corrections() so a test can exercise the real rule rather
    than a paraphrase of it -- the first version of test_fixture_truth.py
    stubbed corrections() wholesale and therefore proved nothing about this.
    """
    if not isinstance(c, dict):
        return False
    if not (c.get("source_url") and c.get("verified_on") and c.get("quote")):
        return False
    return isinstance(c.get("fields"), dict) and bool(c["fields"])


def corrections():
    # type: () -> Dict[str, Dict[str, Any]]
    """The official-school ledger, keyed by game id. Never inferred."""
    doc = _load("data/raw/%d/fixture_corrections.json" % SEASON) or {}
    out = {}
    for c in doc.get("corrections") or []:
        gid = str(c.get("game_id") or "")
        if not gid:
            continue
        if not valid_correction(c):
            continue
        out[gid] = c
    return out


def _detail_records():
    # type: () -> Dict[str, List[Dict]]
    """Every raw /game record, grouped by id. Nothing is dropped."""
    by = collections.defaultdict(list)
    p = os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON)
    if not os.path.exists(p):
        return by
    for i, line in enumerate(open(p, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        gid = str(d.get("game_id") or "")
        if gid:
            d["_line"] = i          # provenance only -- NEVER a tiebreak
            by[gid].append(d)
    return by


def _team_sig(rec):
    ts = rec.get("teams") or []
    return tuple(sorted((str(t.get("team_id")), bool(t.get("is_home")))
                        for t in ts))


def _loc(rec):
    lo = rec.get("location") or {}
    return (lo.get("venue"), lo.get("city"), lo.get("state"))


def _et_hour(epoch):
    """Hour of day in US Eastern for an epoch, or None."""
    if not epoch:
        return None
    try:
        import datetime
        # ⚠ ET, NOT LOCAL AND NOT UTC. The sentinel is defined in Eastern
        # because that is the zone ncaa.com publishes in. September is EDT
        # (UTC-4); the window below is wide enough that the DST edge cannot
        # move a real evening start into it.
        return (datetime.datetime.utcfromtimestamp(int(epoch))
                - datetime.timedelta(hours=4)).hour
    except (ValueError, TypeError, OverflowError):
        return None


def is_placeholder_epoch(epoch):
    """A start time the feed has not actually announced yet.

    ⚠ THIS IS NOT A NEW RULE, IT IS AN OLD ONE APPLIED ONE LAYER EARLIER.
    build_hub.listed_time() already knows ncaa.com fills an unannounced start
    with a midnight-ish Eastern sentinel that formats exactly like a real time
    (measured: 13 of 5,133 completed-2025 fixtures carried an early-AM ET time
    and all thirteen were at Hawaii; 192 do in the 2026 schedule). It used that
    knowledge only for DISPLAY.

    Applying it here matters because a placeholder is not a competing opinion
    about the start time -- it is the absence of one. Game 6626809 holds three
    records at 00:00 ET and two at the announced 7:00 PM ET. Treating those as
    five votes produces a conflict; treating three of them as "not yet
    announced" produces the answer, for a stated reason rather than because the
    real time happened to be appended last.
    """
    h = _et_hour(epoch)
    return h is not None and h < 8


def _agree(values):
    """One value if every non-empty record agrees, else None + the set."""
    seen = [v for v in values if v not in (None, "", ())]
    if not seen:
        return None, []
    uniq = list(dict.fromkeys(seen))
    return (uniq[0] if len(uniq) == 1 else None), uniq


def canonical_fixtures():
    # type: () -> Dict[str, Dict[str, Any]]
    """game_id -> one record, plus its conflicts.

    ⚠ SELECTION RULE, STATED ONCE AND APPLIED EVERYWHERE:
      1. If any record for this id is FINAL (game_state 'F'), the final
         records are the only ones considered -- a result supersedes a
         forecast of itself.
      2. Among the considered records, a field is CANONICAL only if every
         record that has an opinion about it agrees.
      3. A field they disagree about is left unset and recorded in
         `conflicts`. There is no timestamp to break the tie with, so
         inventing a tiebreak would be inventing an answer.
      4. An official-school correction then overrides exactly the fields it
         lists, and CLEARS any conflict on those fields, because a sourced
         human reading beats two silent snapshots.
    """
    det = _detail_records()
    corr = corrections()
    vdoc = _load("data/venues_%d.json" % SEASON) or {}
    vidx = {str(r.get("game_id")): r for r in (vdoc.get("games") or [])}
    # ⚠ VENUE OWNERSHIP IS EVIDENCE; NOMINAL ORDERING IS NOT. venues.py already
    # records, per fixture, the home team's venue on record. Inverting that
    # gives team_id -> building, which lets a CORRECTED venue resolve a site
    # honestly: if the building belongs to a team that is playing, that team is
    # at home. This is not the forbidden inference -- that one reads which side
    # the scoreboard happened to list second.
    home_venue_of = {}
    for r in vdoc.get("games") or []:
        tid = str(r.get("home_team_id") or "")
        hv = (r.get("home_venue_on_record") or "").strip()
        if tid and hv:
            home_venue_of.setdefault(tid, hv)

    out = {}
    for gid, recs in det.items():
        finals = [r for r in recs if r.get("game_state") == "F"]
        pool = finals or recs
        completed = bool(finals)

        conflicts = []

        def resolve(name, values):
            v, uniq = _agree(values)
            if v is None and len(uniq) > 1:
                conflicts.append({"field": name,
                                  "values": [str(x) for x in uniq],
                                  "records": len(pool)})
            return v

        teams = resolve("teams", [_team_sig(r) for r in pool])
        # ⚠ PLACEHOLDERS ARE NOT VOTES. Drop them before comparing; if every
        # record carries one, the start time is genuinely not announced and the
        # placeholder is kept so listed_time() can render it as TBA.
        all_epochs = [r.get("start_time_epoch") for r in pool]
        real_epochs = [e for e in all_epochs if e and not is_placeholder_epoch(e)]
        epoch = (resolve("start_time_epoch", real_epochs) if real_epochs
                 else _agree(all_epochs)[0])
        time_unannounced = not real_epochs
        state = resolve("game_state", [r.get("game_state") for r in pool])
        locs = [_loc(r) for r in pool]
        venue = resolve("venue", [l[0] for l in locs])
        city = resolve("city", [l[1] for l in locs])
        stt = resolve("state_usps", [l[2] for l in locs])

        # site + event come from the derived venue doc, which reads ownership
        # rather than nominal ordering
        vrow = vidx.get(gid) or {}
        site = vrow.get("site")
        event = vrow.get("event")
        # ⚠ A HOME/AWAY FLIP AT A VENUE NEITHER TEAM OWNS IS EVIDENCE, NOT
        # NOISE. All five flips in this season's data are third-party arenas
        # hosting multi-team events. The flip does not let us name the site --
        # it tells us the feed cannot, which is exactly what unconfirmed means.
        flipped = any(c["field"] == "teams" for c in conflicts)
        if flipped and not vrow.get("venue_owner"):
            site = SITE_UNCONFIRMED
            conflicts.append({"field": "site",
                              "values": ["home/away flip across snapshots",
                                         "no venue owner on record"],
                              "records": len(pool)})
        if site in (None, "", "no-venue", "unknown"):
            site = SITE_UNCONFIRMED

        rec = {
            "game_id": gid,
            "teams": [dict(t) for t in ((pool[0].get("teams") or [])
                                        if pool else [])],
            "start_time_epoch": epoch,
            "time_unannounced": time_unannounced,
            "game_state": state,
            "completed": completed,
            "venue": venue, "city": city, "state_usps": stt,
            "site": site, "event": event,
            "source": "ncaa",
            "record_count": len(recs),
            "considered": len(pool),
            "conflicts": conflicts,
            "corrected_fields": [],
            "correction": None,
        }

        c = corr.get(gid)
        if c:
            for k, v in (c.get("fields") or {}).items():
                rec[k] = v
                rec["corrected_fields"].append(k)
            # a sourced reading settles the fields it covers
            rec["conflicts"] = [x for x in rec["conflicts"]
                                if x["field"] not in rec["corrected_fields"]]
            rec["correction"] = {
                "source_url": c.get("source_url"),
                "verified_on": c.get("verified_on"),
                "quote": c.get("quote"),
                "corroborating_url": c.get("corroborating_url"),
                "why": c.get("why"),
            }
            rec["source"] = "ncaa+official-school"

            # ⚠ A CORRECTED VENUE CAN SETTLE A SITE THAT WAS ONLY UNCONFIRMED
            # BECAUSE THE VENUE WAS MISSING -- but only from ownership, and
            # only when the correction did not name the site itself.
            if ("site" not in rec["corrected_fields"]
                    and rec["site"] == SITE_UNCONFIRMED and rec.get("venue")):
                owners = [str(t.get("team_id")) for t in (rec["teams"] or [])
                          if home_venue_of.get(str(t.get("team_id")), "")
                          .lower().startswith(rec["venue"].lower())]
                if len(owners) == 1:
                    rec["site"] = SITE_HOME
                    rec["site_basis"] = ("the corrected venue is this team's "
                                         "own building, on record")

        # ⚠ A HOME/AWAY FLIP STOPS MATTERING ONCE THE SITE IS CONFIRMED
        # NEUTRAL. The flip is only ever a problem because it would drive an
        # "at" claim; on a neutral floor the page says "vs" whichever way the
        # feed happened to order the two. The conflict is still RECORDED -- the
        # audit should show it -- it simply no longer blocks a render that does
        # not depend on it.
        if rec["site"] == SITE_NEUTRAL:
            for c in rec["conflicts"]:
                if c["field"] == "teams":
                    c["non_blocking"] = ("site is confirmed neutral, so no "
                                         "displayed fact depends on which "
                                         "side is nominally home")
        out[gid] = rec
    return out


def blocking_conflicts(rec):
    # type: (Dict[str, Any]) -> List[Dict]
    """Conflicts that must stop a confident render of a FUTURE fixture."""
    if rec.get("completed"):
        return []
    return [c for c in rec.get("conflicts") or []
            if c["field"] in MATERIAL and not c.get("non_blocking")]


def renderable(rec):
    # type: (Dict[str, Any]) -> bool
    return not blocking_conflicts(rec)


if __name__ == "__main__":
    fx = canonical_fixtures()
    bad = [r for r in fx.values() if r["conflicts"]]
    print("canonical fixtures: %d" % len(fx))
    print("with at least one conflict: %d" % len(bad))
    print("blocked from confident render: %d"
          % len([r for r in fx.values() if blocking_conflicts(r)]))
    print("carrying an official-school correction: %d"
          % len([r for r in fx.values() if r["corrected_fields"]]))
