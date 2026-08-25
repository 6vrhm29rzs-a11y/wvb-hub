#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Has anything AUTHORITATIVE changed? One digest, used to decide whether to publish.

    python3 scripts/freshness.py            # print the fingerprint
    python3 scripts/freshness.py explain    # and what it is made of

WHY THIS EXISTS. The in-season refresh runs every half hour. Rebuilding and
committing on every run would push ~48 commits a day and fire a GitHub Pages
deploy for each -- almost all of them carrying no new result, because the page
embeds a build timestamp and therefore differs on every run whether or not any
match finished. The fingerprint decides from the DATA instead.

⚠ IT COUNTS FINALS ONLY, AND THAT IS THE SAME RULE TWICE OVER.
A match in progress is refetched every poll and its score changes each time. If
the fingerprint noticed that, every poll during a live match would publish --
and worse, it would publish a page built while the match was unfinished. Keying
on `game_state == 'F'` means the only thing that can trigger a publish is a
match that has actually finished, which is exactly the rule every derived page
already applies. The freshness gate and the correctness rule are the same rule.

⚠ IT IS A CHANGE DETECTOR, NOT A VALIDATOR. It answers "is there new
authoritative data", nothing else. The guards decide whether that data is fit
to publish, and they run after this says yes.

Python 3.9 target.
"""

import hashlib
import json
import os
import sys
from typing import Dict, List, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))


def final_game_keys():
    # type: () -> List[str]
    """One stable key per FINAL game: id, state, and the set scores.

    The set scores are in the key on purpose. A game can be corrected after it
    is first posted final -- a scoring error fixed the next morning -- and that
    correction must republish even though the count of finals did not move.
    """
    p = os.path.join(RAW, "games.jsonl")
    if not os.path.exists(p):
        return []
    best = {}
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        state = str(rec.get("game_state") or rec.get("state") or "")
        if state != "F":
            continue
        gid = str(rec.get("game_id"))
        ls = rec.get("linescores") or []
        sets = ";".join("%s-%s" % (l.get("visit"), l.get("home")) for l in ls)
        # append-only log: the LAST final record for an id wins, matching
        # gamelog.py's final-beats-non-final, then last-wins dedup
        best[gid] = "%s|%s" % (gid, sets)
    return [best[k] for k in sorted(best)]


def parts():
    # type: () -> List[Tuple[str, str]]
    """(label, digest) for each authoritative input."""
    out = []
    keys = final_game_keys()
    h = hashlib.sha256()
    for k in keys:
        h.update(k.encode("utf-8"))
    out.append(("final games (%d)" % len(keys), h.hexdigest()[:12]))

    # Per-match box scores and player lines: these arrive with the final and are
    # what team stats, player pages and availability are built from. Counted by
    # line, because both files are append-only.
    for name in ("boxscores.jsonl", "playerbox.jsonl", "lineups.jsonl"):
        p = os.path.join(RAW, name)
        n = 0
        if os.path.exists(p):
            n = sum(1 for l in open(p, encoding="utf-8") if l.strip())
        out.append(("%s (%d lines)" % (name, n), hashlib.sha256(
            str(n).encode()).hexdigest()[:12]))
    return out


def fingerprint():
    # type: () -> str
    h = hashlib.sha256()
    for label, digest in parts():
        h.update(("%s=%s;" % (label, digest)).encode("utf-8"))
    return h.hexdigest()


def main(argv):
    if len(argv) > 1 and argv[1] == "explain":
        for label, digest in parts():
            print("  %-28s %s" % (label, digest))
        print("  %-28s %s" % ("FINGERPRINT", fingerprint()))
        return 0
    sys.stdout.write(fingerprint() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
