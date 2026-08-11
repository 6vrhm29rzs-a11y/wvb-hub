#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build data/nicknames.json from a PUBLISHED diminutive list.

WHY THE LIST IS EXTERNAL AND COMMITTED. The surname-anchored join needs to know
that "Katie" and "Kathryn" are one person while "Kate" and "Madison" are two.
Authoring that map from the 25 pairs it is about to adjudicate would confirm
exactly what it was built to confirm -- the n=2 threshold problem at larger n.
So the list is fixed BEFORE it meets the data: fetched once, committed to
data/raw/nicknames_source.csv, and never edited in response to a join result.

Source: carltonnorthern/nicknames (names.csv), rows of
    name1,has_nickname,name2
2,828 rows covering English given names and their diminutives.

If a pair the join needs is absent, the correct outcome is that the join does
NOT happen and the player renders as an em dash. Adding the missing pair by
hand would turn this file back into a self-confirming map. Do not do it.

Python 3.9 target.
"""

import csv
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data", "raw", "nicknames_source.csv")
OUT = os.path.join(REPO, "data", "nicknames.json")


def main():
    if not os.path.exists(SRC):
        print("missing %s -- fetch it once:" % SRC)
        print("  curl -sS -o %s \\\n"
              "    https://raw.githubusercontent.com/carltonnorthern/"
              "nicknames/master/names.csv" % SRC)
        return 1

    # canonical -> set(diminutives). Both directions are stored so a lookup
    # never depends on which spelling the roster happened to use.
    links = {}
    rows = 0
    with open(SRC) as fh:
        for rec in csv.reader(fh):
            if len(rec) < 3 or rec[1] != "has_nickname":
                continue
            a = "".join(c for c in rec[0].strip().lower() if c.isalpha())
            b = "".join(c for c in rec[2].strip().lower() if c.isalpha())
            if not a or not b or a == b:
                continue
            rows += 1
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)

    out = {k: sorted(v) for k, v in sorted(links.items())}
    json.dump({"meta": {"source_tier": "THIRD-PARTY",
                        "source": "carltonnorthern/nicknames names.csv",
                        "pairs": rows, "names": len(out),
                        "note": "fixed reference list; never extended in "
                                "response to a join result -- see the module "
                                "docstring for why"},
               "links": out}, open(OUT, "w"), indent=0)
    print("%d pairs -> %d names, wrote %s" % (rows, len(out), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
