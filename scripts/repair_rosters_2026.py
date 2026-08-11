#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot repair of rosters_2026.json for the "<Name> Photo" duplication.

WHY THIS EXISTS AS A SEPARATE SCRIPT. The bug is fixed in crawl_rosters.py, so
any future crawl produces clean data and never needs this. But the 348-school
crawl is already DONE and committed, the source HTML was not cached, and
re-crawling an hour of network work to fix 15 names would be the wrong trade.
This applies the identical two rules to the stored file.

THE BUG. WMT-platform sites wrap the headshot in its own anchor whose text is
"<Player Name> Photo". That is not a "Full Bio"-shaped string, so the existing
link-text exclusion missed it, and the de-duplicate step keyed on the EXACT
name string -- so "Avery Bain Photo" and "Avery Bain" survived as two people.
Miami (FL) shipped 30 "players" for a 15-player roster. Every Photo copy then
failed the join and landed in UNRESOLVED, which is the whole of Miami's 18 --
the single largest unresolved outlier in the 348-school run.

Found by scripts/audit_unresolved.py, not by looking: the audit's cross-team
search surfaced "Avery Bain Photo" as a name, which is not a name.

IDEMPOTENT. Running it twice is a no-op; running it on already-clean data
changes nothing and reports zero.

Python 3.9 target.
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTERS = os.path.join(REPO, "data", "raw", "2026", "rosters_2026.json")

MEDIA = re.compile(r"\s+(photo|headshot|image|picture)$", re.I)


def main():
    if not os.path.exists(ROSTERS):
        print("missing %s" % ROSTERS)
        return 1
    doc = json.load(open(ROSTERS))
    teams = doc["teams"]

    stripped = 0
    deduped = 0
    touched = []
    for team, meta in teams.items():
        players = meta.get("players") or []
        if not players:
            continue
        before = len(players)
        for p in players:
            nm = p.get("name_raw") or ""
            fixed = MEDIA.sub("", nm)
            if fixed != nm:
                stripped += 1
                p["name_raw"] = fixed
                p["first"] = fixed.split(" ")[0]
                p["last"] = " ".join(fixed.split(" ")[1:]) or None
        seen, out = set(), []
        for p in players:
            k = re.sub(r"[^a-z]", "", (p.get("name_raw") or "").lower())
            if k in seen:
                continue
            seen.add(k)
            out.append(p)
        meta["players"] = out
        if len(out) != before:
            deduped += before - len(out)
            touched.append((team, before, len(out)))

    print("media tokens stripped from names: %d" % stripped)
    print("duplicate roster entries removed:  %d" % deduped)
    for team, b, a in sorted(touched, key=lambda x: -(x[1] - x[2])):
        print("    %-16s %d -> %d" % (team, b, a))
    if not stripped and not deduped:
        print("nothing to repair (already clean)")
        return 0

    json.dump(doc, open(ROSTERS, "w"), indent=1)
    print("rewrote %s" % ROSTERS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
