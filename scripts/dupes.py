#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One reader for the duplicate-listings ledger (round 11).

duplicate_gids() -> {duplicate_gid: canonical_gid}. Every COUNTING consumer
(records, conference results, player aggregates, form, rating inputs,
scores lists, snapshots) skips the keys; the raw log and the Result Ledger
keep them visible with the reason. Entries exist only on authoritative
evidence recorded in the ledger file -- there is NO heuristic
deduplication anywhere, so a real doubleheader can never be swallowed.
"""

import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def duplicate_gids(season=None):
    season = season or int(os.environ.get("WVB_SEASON", "2026"))
    p = os.path.join(REPO, "data", "raw", str(season),
                     "duplicate_listings.json")
    if not os.path.exists(p):
        return {}
    doc = json.load(open(p, encoding="utf-8"))
    return dict((str(k), str((v or {}).get("canonical_gid") or ""))
                for k, v in (doc.get("duplicates") or {}).items())
