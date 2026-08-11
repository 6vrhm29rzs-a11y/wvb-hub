#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Join 2026 rosters to 2025 per-player production. Reports FOUR categories.

THE JOIN IS THE RISK. Two institutions spell the same person differently:
production comes from ncaa.com boxscores, rosters from school athletics sites.
A wrong join silently attributes one player's production to another -- plausible
output, wrong answer, the failure pattern this project keeps hitting.

FOUR CATEGORIES, reported separately. Conflating any two of them turns a normal
situation into a fake problem or hides a real one:

  RETURNING      on the 2026 roster AND produced in 2025
  DEPARTED       produced in 2025, NOT on the 2026 roster        <- the signal
  NEW/UNPLAYED   on the 2026 roster, no 2025 production          <- NOT a failure
                 (true freshmen, redshirts, incoming transfers, injured)
  UNRESOLVED     a name that could not be resolved either way    <- the actual
                 join failure, and the only one that is a defect

WITHIN-TEAM ONLY, and conservative. The candidate pool per team is ~15-22
players, so: exact match first, then one narrow normalisation pass (case,
punctuation, diacritics, suffixes). Anything resolved by the looser pass is
reported SEPARATELY so it can be eyeballed. Never fuzzy-match across teams.

Python 3.9 target.
"""

import difflib
import json
import os
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTERS = os.path.join(REPO, "data", "raw", "2026", "rosters_2026.json")
PLAYERS = os.path.join(REPO, "data", "raw", "2025", "players_2025.json")
OUT = os.path.join(REPO, "data", "returning_2026.json")
NICKNAMES = os.path.join(REPO, "data", "nicknames.json")

SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\.?$", re.I)


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def fullkey(first, last):
    """All name parts, normalised and concatenated -- split-position agnostic.

    Two sources can split a three-part name differently: a roster renders
    "Anna Claire Brown" as first="Anna" last="Claire Brown", while the boxscore
    feed has first="Anna Claire" last="Brown". Keying on the whole name matches
    regardless of where either source put the boundary. This was a real miss --
    an exact same-team match that the first/last key could not see.
    """
    whole = strip_accents(("%s %s" % (first or "", last or "")).lower())
    whole = SUFFIX.sub("", whole).strip()
    return re.sub(r"[^a-z]", "", whole)


def production(p):
    """A player's 2025 scoring, DERIVED FROM RAW COUNTS -- never the feed's own
    `points` column.

    MEASURED, not assumed: across 4,601 players with more than 20 sets, the
    feed's `points` is NEVER above kills + aces + solo blocks + half of block
    assists, and is BELOW it for 3,270 of them -- median ratio 0.61. Rita
    Benidio reads 155 kills and 106 "points". That is the signature of a
    column the box score only carries for SOME games, so the season sum
    silently undercounts by a different amount for every player.

    Using it would have put a wrong number under a heading that says
    "kills + aces + block credit" -- computed correctly, labelled wrongly,
    which is the R4 failure. Nothing else in the pipeline reads the field
    (checked by grep), so the defect stops here.
    """
    k = p.get("kills") or 0
    a = p.get("aces") or 0
    bs = p.get("block_solos") or 0
    ba = p.get("block_assists") or 0
    return round(k + a + bs + 0.5 * ba, 1)


def parts(first, last):
    """Name split into [given, surname tokens...], normalised."""
    whole = strip_accents(("%s %s" % (first or "", last or "")).lower())
    whole = SUFFIX.sub("", whole).strip()
    return [t for t in re.split(r"[^a-z]+", whole) if t]


_NICK = None


def nickname_linked(a, b):
    """Are these two given names a published diminutive pair?

    The list is EXTERNAL and fixed before it meets the data
    (scripts/build_nickname_map.py). A pair it does not cover does not join.
    """
    global _NICK
    if _NICK is None:
        try:
            _NICK = json.load(open(NICKNAMES))["links"]
        except (IOError, ValueError):
            _NICK = {}
    return b in _NICK.get(a, ()) or a in _NICK.get(b, ())


def first_compatible(a, b):
    """Is one given name a plausible rendering of the other?

    Measured against the confirmed misses: the population is nicknames
    (Madi/Madison, Katie/Kathryn), formal-to-short (Bella/Isabella -- note the
    initial DIFFERS), and one-character typos (Cailyn/Caitlyn). No single test
    covers all three, so this is a union of narrow ones rather than one loose
    one.

    A BARE SHARED INITIAL USED TO COUNT HERE. It no longer does. Claude-app's
    review (2026-08-11) named the hole: one sister in the 2025 pool, the other
    on the 2026 roster. Mutual uniqueness cannot see it -- there is only one
    candidate -- so "Kate Smith" would absorb "Kathryn Smith"'s season. A
    shared first letter is not evidence that two names are one person; it was
    carrying 25 of 60 joins on its own.

    The published nickname list replaces it, and only ever CONFIRMS: a pair
    the list does not cover stays unresolved and renders as an em dash. If an
    uncovered pair could still join, the list would be decorative and the risk
    unchanged.
    """
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    if nickname_linked(a, b):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.72


def nkey(first, last):
    """Narrow normalisation: accents, case, punctuation, suffixes."""
    f = strip_accents((first or "").lower())
    l = strip_accents((last or "").lower())
    l = SUFFIX.sub("", l).strip()
    f = re.sub(r"[^a-z]", "", f)
    l = re.sub(r"[^a-z]", "", l)
    return f, l


def main():
    if not os.path.exists(PLAYERS):
        print("no %s yet -- run: python3 scripts/crawl_2025.py players" % PLAYERS)
        return 1
    rosters = json.load(open(ROSTERS))["teams"]
    prod = json.load(open(PLAYERS))["players"]

    by_team = {}
    for p in prod:
        by_team.setdefault(p["team_id"], []).append(p)

    # CROSS-TEAM NAME INDEX -- used ONLY to CLASSIFY, never to attribute
    # production. Three cases look identical as "upperclassman with no
    # within-team 2025 production": a D-I transfer in (has production under a
    # different team_id), a D-II/JUCO/international arrival (no D-I production
    # exists), and a genuine name-match failure. Only the third is a defect.
    # Searching the other 347 teams separates the first from the other two.
    everywhere = {}
    for p in prod:
        everywhere.setdefault(nkey(p.get("first"), p.get("last")), []).append(p)

    print("=" * 78)
    print("JOIN — 2026 rosters x 2025 production")
    print("=" * 78)

    totals = {"returning": 0, "departed": 0, "new": 0, "unresolved": 0,
              "loose": 0, "transfer_in": 0, "surname": 0}
    report = {}
    for team, meta in sorted(rosters.items()):
        roster = meta.get("players") or []
        tid = meta.get("team_id")
        if not roster or not tid:
            continue
        pool = by_team.get(str(tid), [])
        if not pool:
            report[team] = {"status": "no 2025 production data for this team_id"}
            continue

        # index production by exact and normalised keys
        exact, loose, whole = {}, {}, {}
        for p in pool:
            exact[((p.get("first") or "").strip(), (p.get("last") or "").strip())] = p
            loose.setdefault(nkey(p.get("first"), p.get("last")), []).append(p)
            whole.setdefault(fullkey(p.get("first"), p.get("last")), []).append(p)

        matched_ids, returning, new, unresolved, loose_hits = set(), [], [], [], []
        transfers = []
        surname_hits = []
        matches = []          # (roster_player, production_player, how)
        claimed = set()       # id() of production rows already taken
        pending = []          # roster players unmatched after pass 1

        # ---- PASS 1: exact, then narrow normalisation, then whole-name key ----
        for r in roster:
            f, l = (r.get("first") or "").strip(), (r.get("last") or "").strip()
            hit = exact.get((f, l))
            how = "exact"
            if hit is None:
                cands = loose.get(nkey(f, l), [])
                if len(cands) == 1:
                    hit, how = cands[0], "normalised"
                elif len(cands) > 1:
                    unresolved.append((r.get("name_raw"), "ambiguous: %d candidates"
                                       % len(cands)))
                    continue
                if hit is None:
                    wc = whole.get(fullkey(f, l), [])
                    if len(wc) == 1:
                        hit, how = wc[0], "whole-name"
                    elif len(wc) > 1:
                        unresolved.append((r.get("name_raw"),
                                           "ambiguous on whole name: %d" % len(wc)))
                        continue
            if hit is None:
                pending.append(r)
                continue
            claimed.add(id(hit))
            matches.append((r, hit, how))

        # ---- PASS 2: SURNAME-ANCHORED, run only on what pass 1 left over ----
        # 673 unresolved names, audited by near-name search inside each team's
        # own pool (scripts/audit_unresolved.py): 59 had a near name, and those
        # 59 split cleanly on surname agreement -- 54 at ratio 1.000, four at
        # 0.20-0.60, one at 0.833. The four are the dangerous population:
        # "Lauren Pyle" -> "Lauren Malone", same given name, entirely different
        # surname, 316 kills. Joining those would attribute one player's season
        # to another -- plausible output, wrong answer, the exact failure this
        # file exists to prevent. So the anchor is an EXACT surname token and
        # the given name is what flexes, never the reverse.
        #
        # FOUR GUARDS, because a lone uniqueness test is not enough when the
        # cost of a wrong join is a wrong number on the page:
        #   1. surname token must match EXACTLY (no fuzzy surnames, ever)
        #   2. the production row must be UNCLAIMED by pass 1 -- one person
        #      cannot be two roster entries
        #   3. the pairing must be mutually unique: the roster player's only
        #      candidate AND that row's only claimer. Computed over all pending
        #      players before anything is accepted, so the result does not
        #      depend on roster order.
        #   4. true freshmen are excluded -- a first-year cannot have produced
        #      for this team last season, so a surname match there is somebody
        #      else (a graduated sister, a coincidence).
        # Every join made here is reported separately and counted, never folded
        # silently into "returning".
        if pending:
            by_sur = {}
            for p in pool:
                if id(p) in claimed:
                    continue
                pp = parts(p.get("first"), p.get("last"))
                for s in pp[1:]:
                    by_sur.setdefault(s, []).append((p, pp))
            cand_of = {}
            for r in pending:
                cls = (r.get("class_raw") or "").lower()
                if cls.startswith(("fr", "freshman", "redshirt fr", "r-fr")):
                    continue
                rp = parts(r.get("first"), r.get("last"))
                if len(rp) < 2:
                    continue
                seen_c = {}
                for s in rp[1:]:
                    for p, pp in by_sur.get(s, []):
                        # The given name has the same split-position problem
                        # the surname had: "Bernardita Aguilar" on the roster
                        # against "Maria Bernardita Aguilar Toranza" in the
                        # feed -- a Spanish compound given name where the two
                        # sources kept different halves. Token membership
                        # catches it; the uniqueness guard still rejects the
                        # sister case ("Maria Gomez" against a pool holding
                        # both "Maria Gomez" and "Ana Maria Gomez" yields two
                        # candidates and stays unresolved).
                        if (first_compatible(rp[0], pp[0])
                                or rp[0] in pp or pp[0] in rp):
                            seen_c[id(p)] = p
                if len(seen_c) == 1:
                    cand_of[id(r)] = list(seen_c.values())[0]
            claimers = {}
            for rid, p in cand_of.items():
                claimers.setdefault(id(p), []).append(rid)
            still = []
            for r in pending:
                p = cand_of.get(id(r))
                if p is not None and len(claimers.get(id(p), [])) == 1:
                    claimed.add(id(p))
                    matches.append((r, p, "surname-anchored"))
                    surname_hits.append((r.get("name_raw"),
                                         "%s %s" % (p.get("first"), p.get("last")),
                                         production(p)))
                else:
                    still.append(r)
            pending = still

        # ---- what neither pass could tie to this team's 2025 production ----
        for r in pending:
            f, l = (r.get("first") or "").strip(), (r.get("last") or "").strip()
            # genuinely absent from 2025 production: could be a true
            # freshman/transfer (expected) OR a name we failed to resolve.
            # Distinguishable only by class year: a returning player with
            # 2025 production should not be a first-year.
            cls = (r.get("class_raw") or "").lower()
            if cls.startswith(("fr", "freshman", "redshirt fr", "r-fr")):
                new.append(r.get("name_raw"))
                continue
            # upperclassman with no production HERE -- transfer or defect?
            elsewhere = [q for q in everywhere.get(nkey(f, l), [])
                         if str(q.get("team_id")) != str(tid)]
            if len(elsewhere) == 1:
                q = elsewhere[0]
                transfers.append({"name": r.get("name_raw"),
                                  "class": r.get("class_raw"),
                                  "from_team_id": q.get("team_id"),
                                  "points_2025": q.get("points"),
                                  "kills_2025": q.get("kills")})
            elif len(elsewhere) > 1:
                unresolved.append((r.get("name_raw"),
                                   "ambiguous across %d teams" % len(elsewhere)))
            else:
                unresolved.append((r.get("name_raw"),
                                   "no D-I production anywhere, class=%s"
                                   % (r.get("class_raw") or "?")))

        # ---- record everything both passes matched ----
        for r, hit, how in matches:
            matched_ids.add((hit.get("first"), hit.get("last")))
            returning.append({"name": r.get("name_raw"), "class": r.get("class_raw"),
                              "how": how, "pos": hit.get("pos") or "",
                              "kills": hit.get("kills"), "aces": hit.get("aces"),
                              "blocks": round((hit.get("block_solos") or 0)
                                              + 0.5 * (hit.get("block_assists") or 0), 1),
                              "pts": production(hit),
                              "sets": hit.get("sets")})
            if how in ("normalised", "whole-name"):
                loose_hits.append((r.get("name_raw"),
                                   "%s %s" % (hit.get("first"), hit.get("last"))))

        departed = [{"name": "%s %s" % (p.get("first"), p.get("last")),
                     "pos": p.get("pos") or "",
                     "kills": p.get("kills"), "aces": p.get("aces"),
                     "blocks": round((p.get("block_solos") or 0)
                                     + 0.5 * (p.get("block_assists") or 0), 1),
                     "pts": production(p), "sets": p.get("sets")}
                    for p in pool
                    if (p.get("first"), p.get("last")) not in matched_ids
                    and production(p) > 0]

        report[team] = {
            "returning": returning, "departed": departed,
            "new_or_unplayed": new, "unresolved": unresolved,
            "transfer_in_official": transfers,
            "resolved_by_normalisation": loose_hits,
            "resolved_by_surname_anchor": surname_hits,
        }
        totals["surname"] += len(surname_hits)
        totals["returning"] += len(returning)
        totals["departed"] += len(departed)
        totals["new"] += len(new)
        totals["unresolved"] += len(unresolved)
        totals["loose"] += len(loose_hits)
        totals["transfer_in"] += len(transfers)

        print("  %-11s returning=%-3d departed=%-3d new=%-3d xfer-in=%-3d "
              "UNRESOLVED=%-3d loose=%d"
              % (team, len(returning), len(departed), len(new), len(transfers),
                 len(unresolved), len(loose_hits)))

    print()
    print("  TOTALS  returning=%d departed=%d new/unplayed=%d transfer-in=%d "
          "UNRESOLVED=%d"
          % (totals["returning"], totals["departed"], totals["new"],
             totals["transfer_in"], totals["unresolved"]))
    roster_n = totals["returning"] + totals["new"] + totals["transfer_in"] + totals["unresolved"]
    if roster_n:
        print("  JOIN RATE (roster players classified without defect): %.1f%%  "
              "-- go/no-go bar is 90%%" % (100.0 * (roster_n - totals["unresolved"]) / roster_n))
    print("  resolved only by normalisation (eyeball these): %d" % totals["loose"])
    print("  resolved by surname anchor (nickname/compound surname): %d"
          % totals["surname"])
    print()
    if totals["surname"]:
        print("  SURNAME-ANCHORED JOINS — roster name -> production name (2025 pts).")
        print("  Exact surname, flexible given name, mutually unique, unclaimed,")
        print("  non-freshman. Listed in full because each one is a judgement:")
        for team, r in sorted(report.items()):
            for a, b, pts in (r.get("resolved_by_surname_anchor") or []):
                print("    %-16s %-26s -> %-26s pts=%s" % (team, a, b, pts))
        print()

    # CLUSTERED vs EVEN. If unresolved upperclassmen pile up at a few schools
    # the heuristic is catching transfer intake, not join failures; if they
    # spread evenly it is finding real name mismatches. Those call for
    # completely different responses, so the distinction is reported, not the
    # bare count.
    per = {t: len(r.get("unresolved") or []) for t, r in report.items()
           if isinstance(r.get("unresolved"), list)}
    if per:
        vals = sorted(per.values(), reverse=True)
        tot = sum(vals) or 1
        top2 = sum(vals[:2])
        nz = sum(1 for v in vals if v)
        print("  DISTRIBUTION of unresolved across %d schools: %s"
              % (len(vals), ", ".join("%s=%d" % (t, n)
                                      for t, n in sorted(per.items(),
                                                         key=lambda kv: -kv[1]) if n)
                 or "none"))
        if tot:
            print("    top-2 schools hold %d/%d (%.0f%%); %d of %d schools have any"
                  % (top2, tot, 100.0 * top2 / tot, nz, len(vals)))
            print("    -> %s" % ("CLUSTERED: likely transfer intake, not join failure"
                                 if (top2 / float(tot)) > 0.6 and nz <= max(2, len(vals) // 3)
                                 else "SPREAD: likely genuine name mismatches"))
        print()

    # NAME-SHAPE PATTERNS in the failures -- a fixable pattern vs random churn.
    shapes = {"hyphenated": 0, "suffix": 0, "diacritic": 0, "three_plus_parts": 0,
              "initial": 0, "apostrophe": 0}
    for r in report.values():
        for nm, _why in (r.get("unresolved") or []):
            n = nm or ""
            if "-" in n:
                shapes["hyphenated"] += 1
            if SUFFIX.search(n.split(" ")[-1] if " " in n else ""):
                shapes["suffix"] += 1
            if any(ord(c) > 127 for c in n):
                shapes["diacritic"] += 1
            if len(n.split()) >= 3:
                shapes["three_plus_parts"] += 1
            if re.search(r"\b[A-Z]\.", n):
                shapes["initial"] += 1
            if "'" in n or "\u2019" in n:
                shapes["apostrophe"] += 1
    if any(shapes.values()):
        print("  NAME-SHAPE PATTERNS among unresolved: %s"
              % ", ".join("%s=%d" % (k, v) for k, v in shapes.items() if v))
        print()

    print("  UNRESOLVED NAMES — the actual join failures, listed not counted:")
    any_un = False
    for team, r in sorted(report.items()):
        for nm, why in (r.get("unresolved") or []):
            print("    %-12s %-26s %s" % (team, nm, why))
            any_un = True
    if not any_un:
        print("    none")
    print()
    if totals["loose"]:
        print("  RESOLVED BY NORMALISATION — roster name -> production name:")
        for team, r in sorted(report.items()):
            for a, b in (r.get("resolved_by_normalisation") or []):
                print("    %-12s %-26s -> %s" % (team, a, b))
        print()

    json.dump({"meta": {"source_tier": "DERIVED",
                        "note": "roster (school sites, OFFICIAL) x production "
                                "(ncaa.com boxscores, OFFICIAL); join is DERIVED",
                        "totals": totals},
               "teams": report}, open(OUT, "w"), indent=1)
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
