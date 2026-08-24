#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Work out where each team actually plays, and which matches were neutral.

WHY THIS EXISTS. The rating fits a home-advantage term: `fit_off_def` takes a
sign per observation and solves for how many points a home floor is worth. That
is right for a normal match and wrong for a neutral one, and the very first
weekend of 2026 was neutral -- Kentucky-Wisconsin and Louisville-Texas A&M were
both AVCA First Serve matches at Fiserv Forum in Milwaukee, with Wisconsin and
Texas A&M listed at home purely as a bookkeeping convention. Crediting them a
home edge on a floor neither had ever played on is a small, silent, systematic
error, and early in a season when there are twelve results it is not small.

HOW A HOME VENUE IS DECIDED. Not from a lookup table anyone has to maintain: a
team's home venue is simply the venue it is most often listed at home in. That
self-populates as the season runs and needs no outside source.

WHAT IT REFUSES TO DO. Until a team has MIN_HOME_GAMES home matches on record,
its home venue is UNKNOWN and its matches are classified "unknown", not
"neutral". A guess in either direction moves a rating; an honest abstention does
not. Expect almost everything to be unknown in August and almost nothing by
October.

Python 3.9 target. Writes data/venues_{SEASON}.json.
"""

import json
import os
import sys
import collections
import datetime
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                       # pragma: no cover
    ET = None
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
GAMES = os.path.join(REPO, "data", "raw", str(SEASON), "games.jsonl")
OUT = os.path.join(REPO, "data", "venues_%d.json" % SEASON)

MIN_HOME_GAMES = 3
# Matches at one venue more than this many days apart are different occasions,
# not one tournament. A college event runs over a weekend, sometimes a week.
EVENT_GAP_DAYS = 7


def _days_between(a, b):
    # type: (str, str) -> int
    """Whole days between two YYYY-MM-DD strings."""
    import datetime as _dt
    try:
        da = _dt.date(*[int(x) for x in a.split("-")])
        db = _dt.date(*[int(x) for x in b.split("-")])
    except Exception:                                   # noqa: BLE001
        return 0
    return abs((db - da).days)      # below this, a "modal" venue is one data point wearing a hat


def venue_key(loc) -> Optional[str]:
    if not loc:
        return None
    parts = [loc.get("venue"), loc.get("city"), loc.get("state")]
    key = ", ".join(p for p in parts if p)
    return key or None


def load_games() -> List[Dict]:
    if not os.path.exists(GAMES):
        return []
    best = {}
    for line in open(GAMES):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        # A record that parses but is not an object is still garbage. An
        # append-only log written by several code paths WILL eventually carry a
        # null line -- one did, and it crashed two builds rather than being
        # skipped like a torn line already is.
        if not isinstance(g, dict) or not g.get("game_id"):
            continue
        gid = str(g.get("game_id"))
        prev = best.get(gid)
        # final beats non-final, then last wins -- the project's dedup rule
        if prev and prev.get("game_state") == "F" and g.get("game_state") != "F":
            continue
        best[gid] = g
    return list(best.values())


def load_events() -> List[Dict]:
    """Hand-supplied events: venue, name, and the window it runs.

    The window is the point. A venue hosting an event is nobody's home floor for
    those days, so every match there is neutral from the moment it is SCHEDULED
    -- which is what lets Texas vs Arizona St. be classified correctly before it
    is played, rather than waiting for enough finals to infer it.
    """
    p = os.path.join(REPO, "Cody", "data", "events_%d.txt" % SEASON)
    out = []
    if not os.path.exists(p):
        return out
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = [x.strip() for x in line.split("|")]
        out.append({
            "venue": parts[0],
            "name": parts[1] if len(parts) > 1 else None,
            "start": parts[2] if len(parts) > 2 else None,
            "end": parts[3] if len(parts) > 3 else None,
        })
    return out


def build():
    games = load_games()
    declared = load_events()
    game_date = {}
    for g in games:
        ep = g.get("start_time_epoch")
        if ep:
            # EASTERN, not UTC. An 8pm ET match on the 24th is 00:00 UTC on the
            # 25th, which pushed the First Serve window a day past the date the
            # organiser publishes.
            game_date[str(g.get("game_id"))] = (
                datetime.datetime.fromtimestamp(int(ep), ET).strftime("%Y-%m-%d")
                if ET else (datetime.datetime.utcfromtimestamp(int(ep))
                            - datetime.timedelta(hours=4)).strftime("%Y-%m-%d"))

    # 1. how often is each team listed at home in each venue?
    seen = collections.defaultdict(collections.Counter)
    for g in games:
        v = venue_key(g.get("location"))
        if not v:
            continue
        for t in g.get("teams") or []:
            if t.get("is_home"):
                seen[str(t.get("team_id"))][v] += 1

    # A SECOND RULE THAT FIRES IMMEDIATELY. The modal-venue rule above needs a
    # team to have played several home matches, so it says nothing in August.
    # But a real home floor has exactly ONE home team. Fiserv Forum shows
    # Wisconsin listed home in one match and Texas A&M in another -- no arena is
    # both, so it is nobody's home floor and both matches were neutral.
    #
    # Careful with the obvious counter-case: a tournament hosted BY a school
    # also produces several home teams at that venue, because matches between
    # two visitors get one of them nominally at home. So a venue is only wholly
    # neutral when NO team dominates it. Where one does -- the host -- its own
    # matches stay home and everyone else's are neutral.
    venue_hosts = collections.defaultdict(collections.Counter)
    for g in games:
        v = venue_key(g.get("location"))
        if not v:
            continue
        for t in g.get("teams") or []:
            if t.get("is_home"):
                venue_hosts[v][str(t.get("team_id"))] += 1
    venue_owner = {}
    for v, hosts in venue_hosts.items():
        if len(hosts) == 1:
            venue_owner[v] = list(hosts)[0]
            continue
        top, n = hosts.most_common(1)[0]
        rest = sum(hosts.values()) - n
        # a genuine host plays there more than all visitors-listed-home combined
        venue_owner[v] = top if n > rest else None

    home_venue, home_counts = {}, {}
    for tid, counter in seen.items():
        total = sum(counter.values())
        venue, n = counter.most_common(1)[0]
        home_counts[tid] = total
        if total >= MIN_HOME_GAMES:
            home_venue[tid] = venue

    # 2. classify each match
    rows = []
    tally = collections.Counter()
    for g in games:
        v = venue_key(g.get("location"))
        teams = g.get("teams") or []
        home = next((t for t in teams if t.get("is_home")), None)
        if not home:
            continue
        hid = str(home.get("team_id"))
        known = home_venue.get(hid)
        # A DECLARED EVENT WINS OVER INFERENCE. If the organiser says this venue
        # is hosting an event on this date, no team is at home there, and we do
        # not need several finals on record to work it out.
        gd = game_date.get(str(g.get("game_id")))
        declared_hit = None
        for e in declared:
            if e["venue"] != v:
                continue
            if e["start"] and e["end"] and gd and not (e["start"] <= gd <= e["end"]):
                continue
            declared_hit = e
            break
        owner = venue_owner.get(v) if v else None
        multi = v in venue_hosts and len(venue_hosts[v]) > 1
        if not v:
            verdict = "no-venue"
        elif declared_hit:
            verdict = "neutral"
        elif multi and owner is None:
            verdict = "neutral"          # nobody's home floor
        elif multi and owner != hid:
            verdict = "neutral"          # someone else's building
        elif known and v == known:
            verdict = "home"
        elif known:
            verdict = "neutral"
        elif multi and owner == hid:
            verdict = "home"
        else:
            verdict = "unknown"          # not enough played to know yet
        tally[verdict] += 1
        rows.append({
            "game_id": str(g.get("game_id")),
            "venue": v,
            "home_team_id": hid,
            "home_venue_on_record": known,
            "venue_owner": venue_owner.get(v) if v else None,
            "event": declared_hit["name"] if declared_hit else None,
            "site": verdict,
        })

    # ---- EVENTS: matches clustered by venue and date ---------------------
    # The feed carries no event name -- championship, bracketId and bracketRound
    # are all empty, and `title` is just the two team names. So "AVCA First
    # Serve" cannot be read from the data. What CAN be derived is the grouping:
    # several matches at one venue across adjacent days, involving teams that do
    # not play there, is an event whatever it is called. Names can be supplied
    # by hand in Cody/data/events_2026.txt; nothing is invented here.
    # ONLY VENUES WE ACTUALLY BELIEVE ARE NEUTRAL. Including "unknown" here
    # invented an event at Samford's own gym: two home matches, not enough on
    # record yet to establish the venue as theirs, so both came back unknown and
    # got grouped as a tournament. An event needs a neutral match or an explicit
    # declaration -- not an absence of evidence.
    declared_venues = set(e["venue"] for e in declared)
    byvenue = collections.defaultdict(list)
    for r in rows:
        if r["venue"] and (r["site"] == "neutral" or r["venue"] in declared_venues):
            byvenue[r["venue"]].append(r)
    # ⚠ A VENUE IS NOT AN EVENT. Grouping every neutral match at a building into
    # one candidate produced "9 matches at Fiserv Forum, 2026-08-21 to
    # 2026-11-13" -- the eight of the AVCA First Serve plus one unrelated match
    # in November, reported as a single tournament spanning three months. The
    # candidate list exists for a human to NAME events in
    # Cody/data/events_2026.txt, and a cluster that is not one event cannot be
    # given one name.
    #
    # A college tournament runs over a weekend, occasionally a week. Matches at
    # the same venue separated by more than EVENT_GAP_DAYS are different
    # occasions, so the run is split there. This only shapes the CANDIDATE list;
    # nothing is named automatically and no match's site classification changes.
    events = []
    for v, rs in byvenue.items():
        dated = [(game_date.get(r["game_id"]), r) for r in rs]
        # sort on the DATE only: two matches share a date constantly, and
        # falling through to compare the row dicts raises TypeError
        dated = sorted(((d, r) for d, r in dated if d), key=lambda x: x[0])
        undated = [r for r in rs if not game_date.get(r["game_id"])]
        runs, cur = [], []
        for d, r in dated:
            if cur and _days_between(cur[-1][0], d) > EVENT_GAP_DAYS:
                runs.append(cur)
                cur = []
            cur.append((d, r))
        if cur:
            runs.append(cur)
        # matches with no date cannot be placed in time; they ride with the
        # largest run rather than inventing a cluster of their own.
        if undated and runs:
            biggest = max(range(len(runs)), key=lambda i: len(runs[i]))
            runs[biggest].extend((None, r) for r in undated)
        nm = next((e["name"] for e in declared if e["venue"] == v), None)
        for run in runs:
            if len(run) < 2:
                continue
            ds = sorted(d for d, _ in run if d)
            events.append({
                "venue": v,
                "matches": len(run),
                "first_date": ds[0] if ds else None,
                "last_date": ds[-1] if ds else None,
                "game_ids": [r["game_id"] for _, r in run],
                "name": nm,
            })
    events.sort(key=lambda e: (-e["matches"], e.get("first_date") or ""))

    return {
        "meta": {
            "season": SEASON,
            "source_tier": "DERIVED",
            "rule": ("a team's home venue is the venue it is most often listed at "
                     "home in; a match somewhere else is neutral"),
            "min_home_games": MIN_HOME_GAMES,
            "note": ("'unknown' means we do not yet have %d home matches for that "
                     "team, so no claim is made either way -- it is not a synonym "
                     "for 'home'" % MIN_HOME_GAMES),
            "counts": dict(tally),
            "teams_with_known_home": len(home_venue),
            "teams_seen_at_home": len(home_counts),
        },
        "home_venues": home_venue,
        "events": events,
        "games": rows,
    }


def home_sign(game_id, venues=None) -> int:
    """+1/-1 for a normal match, 0 when the floor was neutral.

    Anything we cannot classify keeps the ordinary home sign: the convention
    that the listed home team is at home is right the overwhelming majority of
    the time, and zeroing it on a guess would introduce the opposite error.
    """
    if venues is None:
        if not os.path.exists(OUT):
            return 1
        venues = json.load(open(OUT))
    for r in venues.get("games", []):
        if r["game_id"] == str(game_id):
            return 0 if r["site"] == "neutral" else 1
    return 1


if __name__ == "__main__":
    out = build()
    json.dump(out, open(OUT, "w"), indent=1)
    m = out["meta"]
    print("wrote %s" % OUT)
    print("  matches classified: %s" % json.dumps(m["counts"]))
    print("  teams with a known home venue: %d of %d seen at home"
          % (m["teams_with_known_home"], m["teams_seen_at_home"]))
    for e in out.get("events", []):
        print("  event: %d matches at %s (%s to %s)%s"
              % (e["matches"], e["venue"], e["first_date"], e["last_date"],
                 "  -- %s" % e["name"] if e["name"] else
                 "  -- no name in the feed; add one in Cody/data/events_2026.txt"))
    neutral = [r for r in out["games"] if r["site"] == "neutral"]
    if neutral:
        print("  neutral-site matches:")
        for r in neutral:
            print("     %s at %s (home team usually plays %s)"
                  % (r["game_id"], r["venue"], r["home_venue_on_record"]))
    else:
        print("  no match can be called neutral yet -- not enough home games on "
              "record to know where anyone normally plays")
