#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which matches do not count — one definition, for every consumer.

⚠ THIS EXISTS BECAUSE THE FIRST VERSION LIVED IN build_hub.py ALONE. The hub's
records, standings and per-set rates excluded tonight's exhibition correctly,
and `build_dataset.py` -- which produces the dataset the RATING, the RPI, the
simulator and the field projector all read -- had never heard of it. It filters
on `game_state == "F"` and nothing else, so the moment the match went final it
would have flowed into every rating in the project. Cody's instruction was
explicitly "keep the stats out of the ratings and rankings"; the display layer
was the half that did not matter most.

⚠ THE FEED CANNOT TELL US THIS. Checked game 6640217 during play: no `type`,
no `gameType` (that field exists on the boxscore endpoint and is None), no
exhibition flag, `division: 1`, both teams `(0-0)`. An exhibition is
indistinguishable from a counting match, so this is a hand-maintained ledger
with a source on every entry.

⚠ AND THE STATS ARE NOT MERELY UNOFFICIAL, THEY ARE ON A DIFFERENT SCALE.
Spikes Under the Lights plays its first two sets to 21 rather than 25
(huskers.com match notes, 2026-08-26). Every rate this project computes is per
SET, so a 21-point set deflates points/set, swings/set, the opponent adjustment
and the rally model. The format is also the proof it cannot be an NCAA result:
the playing rules put a set at 25.

Two ways to match, because ids alone have a deadline:
  * by game id, for matches already on the scoreboard
  * by venue + date, for one that is not -- the championship match had no id
    while the semi-finals were being played, and an id-only ledger would have
    missed it entirely.

Python 3.9 target.
"""

import io
import json
import os
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(season):
    # type: (int) -> Dict[str, Any]
    p = os.path.join(REPO, "data/raw/%d/exhibitions.json" % season)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except ValueError:
        return {}


EXH_WORDS = ("exhibition", "scrimmage")


def entry_problems(gid, e):
    # type: (str, Dict) -> List[str]
    """Why this exhibition entry may NOT be believed. Empty list = valid.

    ⚠ WRITTEN AFTER THE USC-ARIZONA ST. INCIDENT (2026-08-29). A counting
    match was ledgered as an exhibition for about an hour, on a "Scrimmage /
    Exhibition" label that belonged to a NEIGHBOURING card on USC's schedule
    page -- evidence gathered for a start-time correction was reused for a
    classification it never supported. Nothing refused the entry, because
    nothing validated this file at all: the Spikes entries carried their own
    proof (sets to 21 cannot be an NCAA result) and the reader trusted
    whatever else was written beside them.

    Classification is ITS OWN FACT. A neutral site, an event name, a time
    discrepancy, missing metadata or an incomplete feed result can never
    imply exhibition. An entry must carry one of exactly two proofs:

      * a FORMAT proof: a NON-DECIDING set target other than 25. NCAA
        playing rules put a set at 25 -- EXCEPT the deciding set (third of
        five in a best-of-3-shaped listing, fifth of five), which is played
        to 15 by rule. So [25,25,25,25,15] is an ordinary five-set match
        and proves NOTHING; the early 21-point sets of Spikes Under the
        Lights ([21,21,15]) are the format that cannot be an NCAA result.
        Only the LAST listed target may be the deciding set; a nonstandard
        target anywhere else is the proof. ⚠ This rule was repaired the day
        after it shipped: the first version took ANY non-25 target as
        proof, which would have called every legitimate five-setter an
        exhibition -- the exact false exclusion the validator exists to
        prevent. If position cannot establish a nonstandard NON-deciding
        target, the entry must carry the bound quote instead; or
      * an explicit CLASSIFICATION_EVIDENCE object: url + retrieved + a
        quoted text that (a) contains the word exhibition or scrimmage and
        (b) STRICTLY names both teams, so the quote is bound to this
        matchup and a label lifted from a neighbouring card cannot satisfy
        it. ⚠ Strictly means the full canonical name resolves, never a
        shared first word or substring -- the first version reduced a team
        to its leading token, so "USC vs Arizona" could have bound an
        Arizona St. entry and "Kentucky" a Kent St. one. See
        _team_bound_in().
    """
    errs = []
    if e.get("counts_toward_record") is not False:
        errs.append("counts_toward_record must be exactly False")
    if not e.get("date"):
        errs.append("no date")
    teams = e.get("teams") or []
    if len(teams) != 2:
        errs.append("must name exactly two teams")
    fmt = _nonstandard_targets(e.get("sets_to") or [])
    ce = e.get("classification_evidence") or {}
    txt = ce.get("text") or ""
    quote_ok = (ce.get("url") and ce.get("retrieved")
                and any(w in txt.lower() for w in EXH_WORDS)
                and len(teams) == 2
                and all(_team_bound_in(txt, t) for t in teams))
    if not fmt and not quote_ok:
        errs.append(
            "no classification proof: needs sets_to with a non-25 target "
            "(format proof) or classification_evidence whose quoted text "
            "contains 'exhibition'/'scrimmage' AND names both teams")
    return errs


def _nonstandard_targets(sets_to):
    # type: (List) -> List
    """Targets that are nonstandard FOR THEIR POSITION -- the only kind
    that is exhibition evidence. The last listed target is the deciding
    set, and a deciding set to 15 is the NCAA's own format: zero evidence.
    A non-25 target in any NON-deciding position (Spikes' 21s) cannot be
    an NCAA match. A deciding-set target that is neither 25 nor 15 is also
    nonstandard and counts."""
    out = []
    n = len(sets_to)
    for i, t in enumerate(sets_to):
        deciding = (i == n - 1)
        if t == 25:
            continue
        if deciding and t == 15:
            continue
        out.append(t)
    return out


def _fold(name):
    # type: (str) -> List[str]
    """A team name's canonical comparable tokens.

    reconcile_2025.norm() is the project's ONE team-name resolver (aliases,
    punctuation, &->and); on top of it, exactly the two official-variant
    folds the AVCA join already uses: State->St and Saint->St. Nothing
    fuzzy -- 'Kentucky' and 'Kent St' share no folded token sequence."""
    import re as _re
    from reconcile_2025 import norm as _cn
    t = _cn(name or "")
    t = _re.sub(r"\bstate\b", "st", t)
    t = _re.sub(r"\bsaint\b", "st", t)
    return t.split()


def _team_bound_in(text, team):
    # type: (str, str) -> bool
    """True only when the quote names THIS team in full.

    ⚠ REPLACES first-word substring binding, which was not binding at all:
    'USC vs Arizona' satisfied an Arizona St. entry and 'Kentucky' a
    Kent St. one, because sharing a leading geographic word is common and
    substring presence proves nothing. The rule now: some contiguous run
    of the quote's own words must FOLD TO EXACTLY the team's canonical
    token sequence -- whole tokens, full name, through the project's
    resolver plus its two official-variant folds. 'Arizona State' binds
    'Arizona St.'; 'Arizona' alone binds nothing with a two-token name."""
    tgt = _fold(team)
    if not tgt:
        return False
    words = [w for w in
             (text or "").replace("|", " ").replace("/", " ").split()
             if w]
    limit = len(tgt) + 2               # folds can merge/split a token
    for n in range(1, limit + 1):
        for i in range(len(words) - n + 1):
            if _fold(" ".join(words[i:i + n])) == tgt:
                return True
    return False


def validate(season):
    # type: (int) -> List[str]
    """All problems across the season's ledger. Empty = clean."""
    out = []
    doc = _load(season)
    for gid, e in (doc.get("exhibitions") or {}).items():
        for p in entry_problems(str(gid), e):
            out.append("%s: %s" % (gid, p))
    for i, r in enumerate(doc.get("rules") or []):
        if r.get("counts_toward_record") is not False:
            out.append("rule %d: counts_toward_record must be exactly False" % i)
        m = r.get("match_on") or {}
        if not (m.get("venue") and m.get("date")):
            out.append("rule %d: match_on needs venue and date" % i)
    return out


def ledger(season):
    # type: (int) -> Dict[str, Dict]
    """game id -> entry. REFUSES an unvalidatable ledger rather than
    believing or silently dropping it: dropping an invalid entry would let a
    genuine exhibition COUNT, and believing it is the USC incident."""
    probs = validate(season)
    if probs:
        raise ValueError("exhibitions ledger invalid: %s" % "; ".join(probs))
    doc = _load(season)
    return dict((str(k), v) for k, v in (doc.get("exhibitions") or {}).items())


def rules(season):
    # type: (int) -> List[Dict]
    """venue+date rules, for matches whose id does not exist yet."""
    return _load(season).get("rules") or []


def match_of(game, season, date=None):
    # type: (Dict, int, Optional[str]) -> Optional[Dict]
    """Return the ledger entry or rule this game matches, else None.

    `game` is a raw record from games.jsonl. `date` is the LOCAL date string if
    the caller has already computed one; otherwise only the id is checked,
    because deriving a date here would give two callers two answers to the same
    question (R4).
    """
    gid = str(game.get("game_id") or game.get("gid") or "")
    hit = ledger(season).get(gid)
    if hit:
        return hit
    if not date:
        return None
    loc = game.get("location") or {}
    venue = (loc.get("venue") or "").strip()
    if not venue:
        return None
    for r in rules(season):
        m = r.get("match_on") or {}
        if m.get("venue") == venue and m.get("date") == date:
            return r
    return None


def is_exhibition(game, season, date=None):
    # type: (Dict, int, Optional[str]) -> bool
    return match_of(game, season, date) is not None


def resolved_gids(season, games_path=None):
    # type: (int, Optional[str]) -> set
    """Every exhibition game id for a season: ledger entries AND rule matches.

    ⚠ A CONSUMER THAT ONLY HAS A GAME ID CANNOT APPLY A VENUE RULE. The player
    aggregate walks playerbox.jsonl, whose records carry a game_id and rows and
    nothing else -- no venue, no date -- so it cannot evaluate "every match at
    AT&T Stadium on this date". Resolving the rule ONCE here, against the game
    log, hands every such consumer a plain set of ids and keeps one definition
    of the question (R4).
    """
    out = set(ledger(season).keys())
    rs = rules(season)
    if not rs:
        return out
    path = games_path or os.path.join(
        REPO, "data/raw/%d/games.jsonl" % season)
    if not os.path.exists(path):
        return out
    import datetime
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")
    except Exception:
        tz = None
    for line in io.open(path, encoding="utf-8"):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if not isinstance(g, dict) or not g.get("game_id"):
            continue
        gid = str(g["game_id"])
        if gid in out:
            continue
        ep = g.get("start_time_epoch")
        if not ep:
            continue
        # ⚠ PACIFIC. The ledger is written in the timezone the hub displays; a
        # UTC date would push a 5pm Pacific match to the next day and the rule
        # would silently never fire.
        try:
            d = (datetime.datetime.fromtimestamp(int(ep), tz) if tz
                 else datetime.datetime.utcfromtimestamp(int(ep))
                 ).strftime("%Y-%m-%d")
        except Exception:
            continue
        if match_of(g, season, d):
            out.add(gid)
    return out
