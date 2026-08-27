#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The fixture-conflict report: what disagrees, on what basis, and whether the
site may render it.

Run: python3 scripts/audit_fixtures.py [--all] [--json]
Writes docs/fixture_conflicts.json and prints a reviewable table.
"""

import collections
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as FX


def name_of(rec):
    ts = rec.get("teams") or []
    if len(ts) != 2:
        return "(%d teams)" % len(ts)
    away = [t for t in ts if not t.get("is_home")]
    home = [t for t in ts if t.get("is_home")]
    if len(away) == 1 and len(home) == 1:
        return "%s / %s" % (away[0].get("name_short"), home[0].get("name_short"))
    return " / ".join(sorted(t.get("name_short") or "?" for t in ts))


def main():
    show_all = "--all" in sys.argv
    fx = FX.canonical_fixtures()
    conflicted = {g: r for g, r in fx.items() if r["conflicts"]}
    blocked = {g: r for g, r in fx.items() if FX.blocking_conflicts(r)}
    corrected = {g: r for g, r in fx.items() if r["corrected_fields"]}

    print("FIXTURE CONFLICT REPORT")
    print("=" * 78)
    print("  canonical fixtures              %5d" % len(fx))
    print("  with at least one conflict      %5d" % len(conflicted))
    print("  BLOCKED from a confident render %5d" % len(blocked))
    print("  carrying an official correction %5d" % len(corrected))
    print()

    by_field = collections.Counter()
    for r in fx.values():
        for c in r["conflicts"]:
            by_field[c["field"] + ("" if not c.get("non_blocking")
                                   else " (non-blocking)")] += 1
    print("  conflicts by field:")
    for k, n in by_field.most_common():
        print("    %-28s %4d" % (k, n))
    print()

    print("BLOCKED FIXTURES -- these render as 'schedule conflict, verify'")
    print("-" * 78)
    if not blocked:
        print("  none")
    for g, r in sorted(blocked.items()):
        print("  %s  %s" % (g, name_of(r)))
        print("     records for this id: %d (all retained; none rewritten)"
              % r["record_count"])
        for c in FX.blocking_conflicts(r):
            print("     field %-18s competing: %s"
                  % (c["field"], " | ".join(v[:58] for v in c["values"][:3])))
        print("     basis: %d raw /game snapshots, no crawl timestamp on any"
              % r["considered"])
        print("     safe to render? NO")
    print()

    if show_all and conflicted:
        print("ALL CONFLICTS (including non-blocking)")
        print("-" * 78)
        for g, r in sorted(conflicted.items()):
            if g in blocked:
                continue
            print("  %s  %s" % (g, name_of(r)))
            for c in r["conflicts"]:
                why = c.get("non_blocking")
                print("     %-18s %s" % (c["field"],
                                         ("non-blocking: " + why) if why
                                         else " | ".join(c["values"][:2])))
            print("     safe to render? YES")
        print()

    print("OFFICIAL-SCHOOL CORRECTIONS IN FORCE")
    print("-" * 78)
    for g, r in sorted(corrected.items()):
        c = r["correction"]
        print("  %s  %s" % (g, name_of(r)))
        print("     corrects : %s" % ", ".join(r["corrected_fields"]))
        print("     now says : site=%s venue=%s, %s %s  event=%s"
              % (r["site"], r["venue"], r["city"], r["state_usps"], r["event"]))
        print("     source   : %s  (read %s)" % (c["source_url"], c["verified_on"]))
        if c.get("corroborating_url"):
            print("     confirmed: %s" % c["corroborating_url"])
        print("     quote    : \"%s\"" % (c["quote"] or "")[:110])
    print()

    out = {
        "counts": {"fixtures": len(fx), "conflicted": len(conflicted),
                   "blocked": len(blocked), "corrected": len(corrected)},
        "by_field": dict(by_field),
        "blocked": {g: {"matchup": name_of(r), "conflicts": r["conflicts"],
                        "records": r["record_count"]}
                    for g, r in sorted(blocked.items())},
        "corrections": {g: {"matchup": name_of(r),
                            "fields": r["corrected_fields"],
                            "source_url": r["correction"]["source_url"],
                            "verified_on": r["correction"]["verified_on"]}
                        for g, r in sorted(corrected.items())},
    }
    p = os.path.join(REPO, "docs", "fixture_conflicts.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
