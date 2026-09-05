#!/usr/bin/env python3
"""Cody's stored VolleyTalk ballots: private, verbatim, hub-resolvable.

2026-09-05. The ballots are HIS OWN posts, stored so his ranking can be
tracked over time. Invariants: every ranked team resolves to a hub name;
the commentary is stored VERBATIM (it is availability intel and the record
of his judgement -- paraphrase is corruption); the module renders on the
private page and leaves ZERO trace on the public build."""
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    p = os.path.join(REPO, "Cody", "data", "my_ballots.jsonl")
    if not os.path.exists(p):
        print("no ballots stored in this checkout (CI) -- structural "
              "checks only")
        entries = []
    else:
        entries = [json.loads(l) for l in open(p, encoding="utf-8")
                   if l.strip()]
        check("at least the W1 ballot is stored", len(entries) >= 1)
        for e in entries:
            check("%s: 25 ranked teams" % e.get("week"),
                  len(e.get("ranks") or []) == 25)
            unresolved = [r["as_written"] for r in e["ranks"]
                          if not r.get("team")]
            check("%s: every team resolves to a hub name" % e.get("week"),
                  not unresolved, unresolved[:3])
            check("%s: submitted_at + source recorded" % e.get("week"),
                  bool(e.get("submitted_at")) and bool(e.get("source")))
            check("%s: commentary stored (verbatim field)" % e.get("week"),
                  "comment_verbatim" in e)

    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()
    check("my_ballots() returns '' on the public build",
          "def my_ballots" in src and
          "if PUBLIC:" in src.split("def my_ballots")[1][:900])
    check("the module lives INSIDE the ballot section (stripped whole)",
          "{{MY_BALLOTS}}" in src.split('<section id="v-ballot"')[1]
          .split("</section>")[0])
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        pg = io.open(pub, encoding="utf-8").read()
        check("public page carries no ballot-module trace",
              "bwmyb" not in pg and "Your submitted ballots" not in pg)
    # NEGATIVE CONTROL: a fake entry with an unresolvable team must fail
    fake = {"week": "x", "ranks": [{"rank": 1, "as_written": "Nowhere U",
                                    "team": None}]}
    check("[NEG] an unresolvable team would be caught",
          [r["as_written"] for r in fake["ranks"] if not r.get("team")]
          == ["Nowhere U"])
    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL MY-BALLOT GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
