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


def ledger(today=None):
    # type: (Optional[str]) -> Dict[str, Any]
    """The validated official-source ledger. See scripts/ledger.py.

    ⚠ THE OLD corrections() ACCEPTED AN ENTRY WITH ONE QUOTE BEHIND FIVE
    INDEPENDENT FACTS. Support is now per field, kinds are separated
    (correction vs conflict), and an entry past its review_by is no longer
    applied -- schools move fixtures, so a reading is a fact about a page on a
    date, not a permanent fact about the match.
    """
    import ledger as LG
    return LG.load(today=today)


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


def _et(epoch):
    """An epoch as a real America/New_York datetime, or None.

    ⚠ NOT A FIXED UTC-4. The previous version subtracted four hours and called
    it Eastern, which is EDT only. Any fixture in the first week of November --
    when the NCAA season is at its busiest -- would have been read an hour off,
    and the sentinel window is defined in wall-clock Eastern. zoneinfo carries
    the real rules.
    """
    if not epoch:
        return None
    try:
        import datetime
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/New_York")
        except Exception:                                  # noqa: BLE001
            return None
        return datetime.datetime.fromtimestamp(int(epoch), tz)
    except (ValueError, TypeError, OverflowError):
        return None


# ⚠ THE SENTINEL IS EXACTLY MIDNIGHT EASTERN, AND NOTHING ELSE.
# The previous rule was "any Eastern hour before 08:00", which is not a
# sentinel test -- it is a guess that happens to catch the sentinel and also
# catches every genuinely early start. Measured on the completed 2025 season,
# 13 of 5,133 fixtures carried an early-AM Eastern time and ALL THIRTEEN were
# at Hawaii, where 1:00 AM ET is an ordinary 7:00 PM local evening start. Under
# the old rule those thirteen real fixtures were classified as "unannounced".
#
# What ncaa.com actually emits for a time it has not set is midnight Eastern.
# So that -- and only that -- is what this recognises. A real 00:00 ET start
# does not exist in the sport, and if one ever did, the honest outcome is the
# same as the sentinel's: we cannot tell, so the time renders unavailable.
SENTINEL_ET_HOUR = 0
SENTINEL_ET_MINUTE = 0


def is_placeholder_epoch(epoch):
    """True only for the exact midnight-Eastern sentinel ncaa.com emits.

    ⚠ IF THE RAW DATA CANNOT DISTINGUISH A REAL EARLY START FROM A
    PLACEHOLDER, THIS RETURNS FALSE and the disagreement becomes a conflict --
    which renders the time as unavailable. Guessing would trade a visible
    "verify" for an invisible wrong time.
    """
    et = _et(epoch)
    if et is None:
        return False
    return et.hour == SENTINEL_ET_HOUR and et.minute == SENTINEL_ET_MINUTE


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
    L = ledger()
    corr = L["corrections"]
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
            # ⚠ A PREGAME SCHEDULE CORRECTION IS NOT A RESULT FACT. Once a
            # match is final, where it was going to be played is settled by
            # what happened, not by a schedule page read three weeks earlier.
            # ⚠ EXCEPT when the entry says `applies_to_final: true` -- an
            # explicit, per-entry assertion that its evidence is corroborated
            # by the COMPLETED match, not merely a pregame reading. Written
            # for USC-Arizona St. (6627523): the feed's final kept a start
            # time three hours late while USC's card and the official box
            # agree on 2:00 PM CT, so withholding the correction left a
            # provably wrong clock on a finished match. The flag is opt-in
            # per entry precisely so no OTHER match's withheld correction
            # changes behaviour (the Petersen question stays open).
            if rec["completed"] and not c.get("applies_to_final"):
                rec["correction_withheld"] = "match is final; pregame schedule correction not applied"
            else:
                sup = c.get("support") or {}
                for k, v in (c.get("fields") or {}).items():
                    rec[k] = v
                    rec["corrected_fields"].append(k)
                rec["conflicts"] = [x for x in rec["conflicts"]
                                    if x["field"] not in rec["corrected_fields"]]
                rec["correction"] = {
                    "why": c.get("why"),
                    "review_by": c.get("review_by"),
                    # ⚠ SUPPORT IS PER FIELD, and travels per field.
                    "support": {k: {"url": sup[k]["url"],
                                    "retrieved": sup[k]["retrieved"],
                                    "text": sup[k]["text"]}
                                for k in c.get("fields") or {} if k in sup},
                }
                rec["source"] = "ncaa+official-school"

        # ⚠ AN OFFICIAL-SOURCE CONFLICT IS NOT A WEAKER CORRECTION. Both cited
        # claims are kept, the fact is cleared, and the NCAA value is NOT
        # quietly preferred -- preferring it would be choosing a side in a
        # disagreement we just said we cannot resolve.
        for cf in L["conflicts"].get(gid, []) if not rec["completed"] else []:
            f = cf["field"]
            rec[f] = None
            rec["conflicts"].append({
                "field": f,
                "values": [str(cl.get("value")) for cl in cf["claims"]],
                "records": len(pool),
                "official_conflict": True,
                "claims": [{"value": cl.get("value"),
                            "url": (cl.get("support") or {}).get("url"),
                            "retrieved": (cl.get("support") or {}).get("retrieved"),
                            "text": (cl.get("support") or {}).get("text")}
                           for cl in cf["claims"]],
            })
            if f in rec["corrected_fields"]:
                rec["corrected_fields"].remove(f)

        # ⚠ A STALE ENTRY DOES NOT VANISH -- it turns the fact into "verify".
        for st in L["stale"].get(gid, []) if not rec["completed"] else []:
            for f in ([st.get("field")] if st.get("kind") == "conflict"
                      else list((st.get("fields") or {}).keys())):
                if not f:
                    continue
                rec.setdefault("stale_fields", []).append(f)
                rec["conflicts"].append({
                    "field": f,
                    "values": ["an official reading from %s has passed its "
                               "review date (%s)" % (st.get("review_by"), st.get("review_by"))],
                    "records": len(pool), "stale": True,
                })

        # ⚠ A CORRECTED VENUE CAN SETTLE A SITE THAT WAS ONLY UNCONFIRMED
        # BECAUSE THE VENUE WAS MISSING -- but only from ownership, and only
        # when neither a correction nor a conflict has already spoken for it.
        # ⚠ THIS BLOCK SILENTLY STOPPED RUNNING when the ledger rewrite spliced
        # the conflict and staleness loops in above it: the dedent was wrong by
        # four spaces, so it became the body of a `for` over an empty list.
        # Nothing threw; game 6625717 just quietly went back to "unconfirmed".
        # An indentation slip in Python is a behaviour change with no error.
        if ("site" not in rec["corrected_fields"]
                and not any(x["field"] == "site" for x in rec["conflicts"])
                and rec["site"] == SITE_UNCONFIRMED and rec.get("venue")):
            owners = [str(t.get("team_id")) for t in (rec["teams"] or [])
                      if home_venue_of.get(str(t.get("team_id")), "")
                      .lower().startswith(rec["venue"].lower())]
            if len(owners) == 1:
                rec["site"] = SITE_HOME
                rec["site_basis"] = ("the venue on this fixture is that team's "
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
