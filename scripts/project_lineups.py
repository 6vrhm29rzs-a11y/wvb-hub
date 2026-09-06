#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-team starting lineups: who actually started in 2025, and who is back.

WHAT THIS IS, PRECISELY -- the framing matters more than the code:

  It reports the six players a team ACTUALLY started most often in 2025 (from
  set-1 play-by-play, measured) and marks each one returning or departed (from
  the existing R8-compliant roster join). It does NOT invent a 2026 starting
  six. A vacated slot renders as a VACANCY, never as a guessed name -- there is
  no evidence in any feed about who fills it, and manufacturing one would be
  exactly the R5 failure (a synthesised value shown where a measurement belongs).

  It also does NOT order the six by rotation. The feed's order is jersey
  number; rotation order is provably absent (docs/rotations_finding.md, with a
  positive control). Players are listed by how often they started.

Inputs : data/raw/2025/lineups.jsonl  (scripts/crawl_pbp.py)
         data/returning_2026.json     (scripts/join_players.py)
         data/data_2025.json          (team_id -> name)
Output : data/lineups_2026.json

Python 3.9 target.
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lineups import norm, surname  # noqa: E402


def pos_bucket(p):
    """Coarse position. Unknown stays unknown -- never guessed into a slot."""
    p = (p or "").upper().strip()
    if not p:
        return "?"
    if p.startswith("OPP") or p.startswith("RS"):
        return "OPP"
    if p.startswith("OH"):
        return "OH"
    if p.startswith("MB") or p.startswith("M"):
        return "MB"
    if p.startswith("L") or p.startswith("DS"):
        return "L"
    if p.startswith("S"):
        return "S"
    return "?"


def offense_system(setter_counts):
    """5-1 or 6-2, from how many setters a team actually starts.

    One setter on the floor is a 5-1, two is a 6-2 -- the basic fact about how
    a team runs its offence, and it falls straight out of the starting six.
    Measured across 2025: 252 teams consistently start one setter, 4 start two,
    which is the real shape of D-I women's volleyball.

    Returns None unless the team is CONSISTENT (>=80% of its lineups agree).
    A team whose lineups disagree, or whose position data is too thin to show a
    setter at all, gets no label rather than a guess -- 6 teams show zero
    setters in their six, which is missing position data, not a system.
    """
    counts = [c for c in setter_counts if c is not None]
    if len(counts) < MIN_MATCHES:
        return None
    tally = collections.Counter(counts)
    modal, n = tally.most_common(1)[0]
    if n / float(len(counts)) < 0.8:
        return None
    if modal == 1:
        return "5-1"
    if modal == 2:
        return "6-2"
    return None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINEUPS = os.path.join(REPO, "data", "raw", "2025", "lineups.jsonl")
RETURNING = os.path.join(REPO, "data", "returning_2026.json")
DATA2025 = os.path.join(REPO, "data", "data_2025.json")
OUT = os.path.join(REPO, "data", "lineups_2026.json")

# A team's "usual six" is only meaningful if we saw enough of its season. Below
# this we still publish the counts but flag the coverage rather than implying a
# settled lineup.
MIN_MATCHES = 5


def fullkey(name):
    return norm(name)


def main():
    if not os.path.exists(LINEUPS):
        print("no %s -- run scripts/crawl_pbp.py first" % LINEUPS)
        return 1

    id2name = {}
    d25 = json.load(open(DATA2025))
    for t in d25.get("teams", []):
        id2name[str(t["team_id"])] = t.get("name_short") or t.get("name_full")

    ret = json.load(open(RETURNING))["teams"]

    # team_id -> player key -> {starts, name, pos, num}
    starts = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"starts": 0, "name": "", "pos": "", "num": None}))
    matches = collections.Counter()
    setters_seen = collections.defaultdict(list)
    games_seen = 0
    label_disagreements = 0
    lineups_total = 0

    for line in open(LINEUPS):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        games_seen += 1
        for lu in rec.get("lineups", []):
            lineups_total += 1
            if not lu.get("feed_label_agreed", True):
                label_disagreements += 1
            tid = lu["team_id"]
            matches[tid] += 1
            buckets = [pos_bucket(p.get("pos")) for p in lu["starters"]]
            if "?" not in buckets:
                setters_seen[tid].append(buckets.count("S"))
            for p in lu["starters"]:
                k = fullkey(p["name"])
                slot = starts[tid][k]
                slot["starts"] += 1
                slot["name"] = p["name"]
                slot["pos"] = p.get("pos") or ""
                slot["num"] = p.get("num")

    teams_out = {}
    stat = collections.Counter()
    for tid, players in starts.items():
        name = id2name.get(tid)
        if not name:
            stat["no_team_name"] += 1
            continue
        # A team missing from the roster join entirely (no athletics site / no
        # roster found -- ~39 of 348) is NOT the same as six departed players.
        # Without this split, "0 of 6 returning" reads as total turnover when
        # the truth is that we have no 2026 roster at all. Measured: the
        # unknown-count distribution is bimodal, 0 or 6, exactly because of it.
        has_join = name in ret
        tret = ret.get(name) or {}
        back = {}
        for p in tret.get("returning", []) or []:
            back[fullkey(p.get("name", ""))] = p
        gone = set(fullkey(p.get("name", "")) for p in (tret.get("departed") or []))

        ranked = sorted(players.items(),
                        key=lambda kv: (-kv[1]["starts"], kv[1]["name"]))
        six = []
        for k, v in ranked[:6]:
            if k in back:
                status = "returning"
            elif k in gone:
                status = "departed"
            else:
                # Not in either list: the roster join could not resolve this
                # player. Unknown is reported as unknown.
                status = "unknown"
            r = back.get(k) or {}
            six.append({
                "name": v["name"],
                "pos": v["pos"],
                "num": v["num"],
                "starts_2025": v["starts"],
                "status_2026": status,
                "class_2026": r.get("class") or None,
                "pts_2025": r.get("pts"),
            })
        if not has_join:
            for p in six:
                p["status_2026"] = "no_roster"
        # Every player who started at least once, not just the top six -- the
        # roster view needs "started 12 of 28" for depth players too.
        # ⚠ FOLD FEED SPELLINGS BEFORE KEYING (2026-09-06): the 2025 feed
        # spelled Teodora Krickovic two ways (mojibake in some games), so the
        # display map carried her twice, 28 starts + 5. nameclean.repair is
        # the one definition; colliding spellings SUM.
        import nameclean as _nc
        all_starts = {}
        for k, v in ranked:
            _nm = _nc.repair(v["name"])
            all_starts[_nm] = all_starts.get(_nm, 0) + v["starts"]
        n_ret = sum(1 for p in six if p["status_2026"] == "returning")
        n_unk = sum(1 for p in six if p["status_2026"] == "unknown")
        stat["teams"] += 1
        teams_out[name] = {
            "team_id": tid,
            "matches_with_lineup": matches[tid],
            "coverage_ok": matches[tid] >= MIN_MATCHES,
            "usual_six_2025": six,
            "starts_by_player_2025": all_starts,
            "offense_system_2025": offense_system(setters_seen.get(tid, [])),
            "roster_join_available": has_join,
            # None, not 0, when there is no 2026 roster to compare against --
            # an absent measurement is not a zero.
            "returning_of_six": n_ret if has_join else None,
            "unknown_of_six": n_unk if has_join else None,
            # The honest name for the gap. Never filled with a guess.
            "vacancies": (6 - n_ret - n_unk) if has_join else None,
        }

    meta = {
        "built_utc": None,
        "source_tier": "DERIVED",
        "source": ("2025 set-1 starting lineups from ncaa.com play-by-play "
                   "(OFFICIAL) x 2026 roster join (DERIVED)"),
        "what_this_is": ("The six a team STARTED most often in 2025, each "
                         "marked returning/departed/unknown for 2026. It is "
                         "NOT a predicted 2026 lineup: vacated slots are "
                         "reported as vacancies, never filled with a guess."),
        "rotation_order": ("NOT AVAILABLE. The feed orders its six by jersey "
                           "number, not rotation. See docs/rotations_finding.md "
                           "-- measured at chance against a positive control "
                           "that scores 100%."),
        "games_parsed": games_seen,
        "lineups_extracted": lineups_total,
        "feed_label_disagreements": label_disagreements,
        "min_matches_for_coverage_ok": MIN_MATCHES,
        "teams": len(teams_out),
    }
    json.dump({"meta": meta, "teams": teams_out}, open(OUT, "w"), indent=1)

    print("games parsed          : %d" % games_seen)
    print("lineups extracted     : %d" % lineups_total)
    print("teams with a lineup   : %d" % len(teams_out))
    print("feed label disagreed  : %d (attribution used names, not the label)"
          % label_disagreements)
    ok = sum(1 for v in teams_out.values() if v["coverage_ok"])
    print("teams with >=%d matches: %d" % (MIN_MATCHES, ok))
    if teams_out:
        no_join = sum(1 for v in teams_out.values() if not v["roster_join_available"])
        print("teams with no 2026 roster join: %d (reported as such, not as 0 returning)"
              % no_join)
        rets = [v["returning_of_six"] for v in teams_out.values()
                if v["coverage_ok"] and v["roster_join_available"]]
        if rets:
            dist = collections.Counter(rets)
            print("returning starters of the usual six (teams with coverage):")
            for k in sorted(dist):
                print("   %d of 6 : %d teams" % (k, dist[k]))
    syscount = collections.Counter(v["offense_system_2025"] for v in teams_out.values())
    print("offence system from the starting six: %s"
          % dict((k or "not stated", v) for k, v in syscount.items()))
    print("-> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
