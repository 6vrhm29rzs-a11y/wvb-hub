#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ballot Workshop -- storage, comparison and output for Cody's weekly Top 25.

    python3 scripts/ballot.py list          # what has been saved
    python3 scripts/ballot.py text          # the latest ballot as VolleyTalk text
    python3 scripts/ballot.py diff          # latest vs the one before it

WHAT THIS IS. Cody submits a Top 25 to VolleyTalk each week. This is the private
workspace where he forms that ballot: his ranking is the object, POWER is a
starting point he can overrule, and his reasons are recorded as text.

⚠ WHAT IT IS NOT, AND THE DISTINCTION IS THE POINT.
  * NOT a model. Nothing here feeds POWER, RESUME, the simulator or the
    projector. A ballot is an opinion with the author's name on it.
  * NOT an automatic ballot generator. It seeds from POWER because a blank
    twenty-five is a bad starting point, not because POWER is the answer.
  * NOT a scorer of subjective traits. "Clutch", "composure", "IT" and the rest
    are recorded as WORDS in a reason field and are never turned into a number.
    The rating engine has been measured on exactly those ideas and they made it
    worse (docs/rating_factors_2025.md); the place for them is a human's
    judgment, stated as such.
  * NOT connected to anything. It formats text for Cody to read and copy. It
    posts nowhere.

STORAGE: `data/ballots_{SEASON}.jsonl`, APPEND-ONLY, one JSON object per save.
Same convention as rankings_history and polls_avca -- git-committable, diffable,
and append-only is what makes "never overwrite a past ballot" structural rather
than a promise. A save is a new line; nothing is ever rewritten in place.

Python 3.9 target.
"""

import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
PATH = os.path.join(REPO, "data", "ballots_%d.jsonl" % SEASON)

SLOTS = 25
MAX_TEAMS = 60          # 25 ranked + a generous also-considered pool
MAX_NOTE = 600          # per-team note
MAX_SUMMARY = 2000      # the ballot-level notes


def load():
    # type: () -> List[Dict]
    """Every saved ballot, oldest first. A corrupt line is skipped, not fatal."""
    if not os.path.exists(PATH):
        return []
    out = []
    for line in open(PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    out.sort(key=lambda b: b.get("saved_utc") or "")
    return out


def validate(ballot):
    # type: (Dict) -> Optional[str]
    """None if the ballot can be saved, else why not.

    Deliberately strict about SHAPE and silent about CONTENT. It is Cody's
    ballot: any team may sit in any slot for any reason, or none. What is
    rejected is a payload that would corrupt the file or the comparison --
    duplicates, over-long text, a rank that is not a rank.
    """
    if not isinstance(ballot, dict):
        return "not an object"
    teams = ballot.get("teams")
    if not isinstance(teams, list) or not teams:
        return "a ballot needs at least one team"
    if len(teams) > MAX_TEAMS:
        return "too many teams (%d, max %d)" % (len(teams), MAX_TEAMS)
    seen = set()
    ranks = []
    for t in teams:
        if not isinstance(t, dict):
            return "a team entry is not an object"
        nm = (t.get("team") or "").strip()
        if not nm:
            return "a team entry has no name"
        if nm in seen:
            return "%s appears twice" % nm
        seen.add(nm)
        r = t.get("rank")
        if r is not None:
            if not isinstance(r, int) or r < 1 or r > SLOTS:
                return "%s has rank %r, which is not a slot 1-%d" % (nm, r, SLOTS)
            ranks.append(r)
        if len(str(t.get("note") or "")) > MAX_NOTE:
            return "the note on %s is too long" % nm
        if len(str(t.get("reason") or "")) > MAX_NOTE:
            return "the move reason on %s is too long" % nm
    if len(set(ranks)) != len(ranks):
        return "two teams share a slot"
    if ranks and sorted(ranks) != list(range(1, len(ranks) + 1)):
        return "the ranked slots are not 1..%d with no gaps" % len(ranks)
    if len(str(ballot.get("summary") or "")) > MAX_SUMMARY:
        return "the notes section is too long"
    return None


def append(ballot):
    # type: (Dict) -> Dict
    """Write one ballot as a new line. Never rewrites. Returns the stored row.

    ⚠ The timestamp is assigned HERE rather than trusted from the caller, so
    two saves can never claim the same instant and the file's order is the
    order things actually happened.
    """
    why = validate(ballot)
    if why:
        raise ValueError(why)
    row = dict(ballot)
    row["saved_utc"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    row["season"] = SEASON
    row["schema"] = 1
    d = os.path.dirname(PATH)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def ranked(ballot):
    # type: (Dict) -> List[Tuple[int, str]]
    """(rank, team) for the ranked slots only, in order."""
    out = [(t["rank"], t["team"]) for t in (ballot.get("teams") or [])
           if t.get("rank")]
    out.sort()
    return out


def compare(current, previous):
    # type: (Dict, Optional[Dict]) -> Dict
    """What changed between two ballots.

    ⚠ MOVEMENT IS AGAINST THE PREVIOUS BALLOT, NOT AGAINST POWER. Those are
    different questions and the page shows both, but this one is "what did I
    change my mind about", which is the whole reason to keep a history.
    """
    cur = dict((t, r) for r, t in ranked(current))
    if not previous:
        return {"first_week": True, "entered": sorted(cur, key=lambda t: cur[t]),
                "dropped": [], "moved": [], "unchanged": [], "previous_saved": None}
    prev = dict((t, r) for r, t in ranked(previous))
    entered = [t for t in sorted(cur, key=lambda x: cur[x]) if t not in prev]
    dropped = [t for t in sorted(prev, key=lambda x: prev[x]) if t not in cur]
    moved, unchanged = [], []
    for t in cur:
        if t not in prev:
            continue
        d = prev[t] - cur[t]              # positive = moved UP the ballot
        if d:
            moved.append({"team": t, "from": prev[t], "to": cur[t], "move": d})
        else:
            unchanged.append(t)
    moved.sort(key=lambda m: (-abs(m["move"]), m["to"]))
    unchanged.sort(key=lambda t: cur[t])
    return {"first_week": False, "entered": entered, "dropped": dropped,
            "moved": moved, "unchanged": unchanged,
            "previous_saved": previous.get("saved_utc")}


def as_text(ballot, previous=None, include_notes=True):
    # type: (Dict, Optional[Dict], bool) -> str
    """The ballot as plain text, ready to be read and copied.

    Exactly the shape a forum post wants: `1. Team` through `25. Team`, then an
    optional short notes block. No markup, no branding, no signature -- it is
    Cody's post, and anything this added would be words he did not write.
    """
    lines = []
    for r, t in ranked(ballot):
        lines.append("%d. %s" % (r, t))
    if not include_notes:
        return "\n".join(lines)

    extra = []
    summary = (ballot.get("summary") or "").strip()
    if summary:
        extra.append(summary)
    if previous:
        c = compare(ballot, previous)
        bits = []
        big = [m for m in c["moved"] if abs(m["move"]) >= 3][:4]
        for m in big:
            bits.append("%s %s%d (%d→%d)"
                        % (m["team"], "up " if m["move"] > 0 else "down ",
                           abs(m["move"]), m["from"], m["to"]))
        if c["entered"]:
            bits.append("in: " + ", ".join(c["entered"][:4]))
        if c["dropped"]:
            bits.append("out: " + ", ".join(c["dropped"][:4]))
        if bits:
            extra.append("Biggest moves: " + " | ".join(bits))
    if extra:
        lines.append("")
        lines.append("Notes / biggest moves")
        lines.extend(extra)
    return "\n".join(lines)


def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "list").lower()
    rows = load()
    if cmd == "list":
        if not rows:
            print("no ballots saved yet -- %s does not exist" % os.path.relpath(PATH, REPO))
            return 0
        for i, b in enumerate(rows, 1):
            r = ranked(b)
            print("%2d. %s  %d ranked  %s"
                  % (i, b.get("saved_utc"), len(r),
                     (", ".join(t for _, t in r[:5]) + " ...") if r else "(empty)"))
        return 0
    if not rows:
        print("no ballots saved yet")
        return 1
    if cmd == "text":
        print(as_text(rows[-1], rows[-2] if len(rows) > 1 else None))
        return 0
    if cmd == "diff":
        c = compare(rows[-1], rows[-2] if len(rows) > 1 else None)
        if c["first_week"]:
            print("first saved ballot -- nothing to compare against")
            return 0
        print("vs %s" % c["previous_saved"])
        for m in c["moved"][:10]:
            print("  %-22s %d -> %d  (%+d)" % (m["team"], m["from"], m["to"], m["move"]))
        if c["entered"]:
            print("  entered : %s" % ", ".join(c["entered"]))
        if c["dropped"]:
            print("  dropped : %s" % ", ".join(c["dropped"]))
        print("  unchanged: %d" % len(c["unchanged"]))
        return 0
    print("usage: ballot.py [list|text|diff]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
