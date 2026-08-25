#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Live Match Center (Phase 1).

The feature shows numbers taken from a match that is still being played, so the
ways it can go wrong are all versions of the same thing: showing something that
is not true yet. These guards are therefore mostly NEGATIVE -- they assert what
must be refused.

⚠ AND THE POSITIVE CONTROLS MATTER JUST AS MUCH. "Refuse everything" would pass
every negative check here and ship a feature that never displays anything, so a
real, coherent box score (today's actual finals) must still validate.

Python 3.9 target. Run: python3 scripts/test_live_match.py
"""

import copy
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_detail as LD                                          # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def box(kills=(30, 40), attacks=(90, 95), errors=(10, 12), digs=(25, 30),
        aces=(3, 5), sets_played=3, players=True):
    """A synthetic but structurally faithful box score."""
    tb = []
    for i in (0, 1):
        st = {"kills": str(kills[i]), "attackErrors": str(errors[i]),
              "attackAttempts": str(attacks[i]), "assists": str(max(0, kills[i] - 2)),
              "digs": str(digs[i]), "serviceAces": str(aces[i]),
              "serviceErrors": "4", "blockSolos": "2", "blockAssists": "6",
              "sets": str(sets_played)}
        ps = []
        if players:
            ps = [{"firstName": "A%d" % i, "lastName": "Player",
                   "kills": str(kills[i] // 2), "serviceAces": "1",
                   "blockSolos": "1", "blockAssists": "2", "digs": "5"}]
        tb.append({"teamId": str(100 + i), "teamStats": st, "playerStats": ps})
    return {"teamBoxscore": tb,
            "teams": [{"teamId": "100", "nameShort": "Alpha"},
                      {"teamId": "101", "nameShort": "Beta"}]}


def main():
    print("LIVE MATCH CENTER GUARDS\n")

    print("1. A coherent official box score validates (positive control)")
    t, lead, why = LD.validate(box())
    check("[+] a well-formed box score is accepted", t is not None, why)
    if t:
        check("[+] both teams come back", len(t) == 2)
        check("[+] hitting % is (K-E)/TA from summed counts",
              abs(t[0]["hitpct"] - round((30 - 10) / 90.0, 3)) < 1e-9,
              str(t[0]["hitpct"]))
        # ⚠ RAW COUNTS, NEVER THE FEED'S `points` COLUMN.
        check("[+] points = kills + aces + solo + half assists",
              t[0]["points"] == 30 + 3 + 2 + 3.0, str(t[0]["points"]))
        check("[+] blocks = solo + half assists", t[0]["blocks"] == 5.0)
        check("[+] player leaders are derived", len(lead) > 0)

    print("\n   ...and so do the two REAL box scores from 2026-08-24")
    real = 0
    for gid in ("6639891", "6639887"):
        p = os.path.join(REPO, "data", "raw", "2026", "boxscore_%s.json" % gid)
        if not os.path.exists(p):
            continue
        tt, _l, w = LD.validate(json.load(open(p, encoding="utf-8")))
        check("[+] real box %s validates" % gid, tt is not None, w)
        real += 1
    if not real:
        print("     (no sample box scores on disk -- synthetic controls only)")

    print("\n2. Nonsense is refused, never rendered")
    cases = [
        ("no payload at all", None),
        ("a string instead of a payload", "nope"),
        ("only one team", {"teamBoxscore": [box()["teamBoxscore"][0]]}),
        ("three teams", {"teamBoxscore": box()["teamBoxscore"] + [{}]}),
        ("no teamBoxscore key", {"teams": []}),
        ("a malformed team entry", {"teamBoxscore": ["x", "y"]}),
    ]
    for label, payload in cases:
        t, _l, why = LD.validate(payload)
        check("[-] %s is refused" % label, t is None, "got %r" % (t,))
        check("    ...with a stated reason", bool(why))

    print("\n3. Partial and impossible counts are refused")
    b = box(); b["teamBoxscore"][0]["teamStats"]["kills"] = ""
    check("[-] a blank count is not a zero", LD.validate(b)[0] is None)
    b = box(); b["teamBoxscore"][0]["teamStats"]["digs"] = "-"
    check("[-] a dash is not a zero", LD.validate(b)[0] is None)
    b = box(); del b["teamBoxscore"][1]["teamStats"]["digs"]
    check("[-] a missing field is not a zero", LD.validate(b)[0] is None)
    b = box(); b["teamBoxscore"][0]["teamStats"]["kills"] = "-5"
    check("[-] a negative count is refused", LD.validate(b)[0] is None)
    b = box(kills=(95, 40), attacks=(90, 95))
    check("[-] more kills than attempts is refused", LD.validate(b)[0] is None)
    b = box(); b["teamBoxscore"][0]["teamStats"]["attackErrors"] = "500"
    check("[-] more errors than attempts is refused", LD.validate(b)[0] is None)
    b = box(kills=(0, 0), attacks=(0, 0), errors=(0, 0), digs=(0, 0), aces=(0, 0))
    t, _l, why = LD.validate(b)
    check("[-] an ALL-ZERO box is refused, not shown as 0-0", t is None, why)
    check("    ...and says the box is still empty", "empty" in why, why)
    b = box(sets_played=9)
    check("[-] an implausible set count is refused", LD.validate(b)[0] is None)
    b = box(sets_played=1)
    check("[-] a box behind the scoreboard is refused",
          LD.validate(b, expect_sets=4)[0] is None)
    check("[+] ...but a box level with it is fine",
          LD.validate(box(sets_played=3), expect_sets=3)[0] is not None)

    print("\n4. Number parsing does not invent zeros")
    for bad in (None, "", "  ", "-", "--", "N/A", "abc", "1.5", {}, [], True):
        check("[-] _int(%r) is None, not 0" % (bad,), LD._int(bad) is None)
    for good, want in (("12", 12), (12, 12), ("0", 0), (7.0, 7), ("  9 ", 9)):
        check("[+] _int(%r) == %d" % (good, want), LD._int(good) == want)

    print("\n5. The cache: one match, few entries, fail soft")
    clock = [1000.0]
    calls = []

    def fake(gid):
        calls.append(gid)
        return {"gid": gid, "n": len(calls)}

    c = LD.DetailCache(fake, ttl=20.0, cap=3, clock=lambda: clock[0])
    c.get("A"); c.get("A"); c.get("A")
    check("[+] repeat reads inside the TTL cost ONE upstream call",
          len(calls) == 1, str(calls))
    clock[0] += 21
    c.get("A")
    check("[+] after the TTL it refetches", len(calls) == 2, str(calls))
    check("[-] it never fetches a match nobody opened",
          set(calls) == {"A"}, str(calls))
    for k in ("B", "C", "D", "E"):
        clock[0] += 1
        c.get(k)
    check("[+] the entry cap holds", len(c._entries) <= 3, str(len(c._entries)))

    # fail soft: upstream dies, last good survives and is MARKED stale
    clock[0] += 1
    good = LD.DetailCache(fake, ttl=10.0, clock=lambda: clock[0])
    good.get("Z")
    boom = {"n": 0}

    def dead(gid):
        boom["n"] += 1
        raise IOError("upstream down")

    good._fetch = dead
    clock[0] += 11
    payload, age, stale, err = good.get("Z")
    check("[+] a failed refresh keeps the last coherent response",
          payload is not None, str(payload))
    check("[+] ...and marks it stale", stale is True)
    check("[+] ...and says why", bool(err), repr(err))
    check("[+] ...and reports its age", age >= 11, str(age))
    clock[0] += LD.STALE_MAX + 5
    payload, _a, _s, err = good.get("Z")
    check("[-] but it gives up once too old to mean anything",
          payload is None, str(payload))

    def none_fetch(gid):
        return None

    c2 = LD.DetailCache(none_fetch, clock=lambda: clock[0])
    payload, _a, _s, err = c2.get("Q")
    check("[-] an empty upstream response yields nothing, not {}",
          payload is None, str(payload))
    check("    ...with a reason", bool(err))

    print("\n6. The endpoint's own rules")
    src = open(os.path.join(REPO, "scripts", "live_server.py"),
               encoding="utf-8").read()
    check("/api/match exists and is separate from /api/live",
          '"/api/match"' in src and '"/api/live"' in src)
    check("it is local-only, like the other write/spend endpoints",
          '/api/match' in src and '_is_local()' in src)
    check("the server still binds to 127.0.0.1",
          '127.0.0.1' in src and 'HOST' not in src.split('PORT')[0][-200:])
    check("a non-numeric id is rejected before any upstream call",
          "gid.isdigit()" in src)
    check("a FINAL hands off to the verified pipeline rather than scraping",
          "the verified result enters the site" in src)
    check("an unknown id is not looked up (no fishing)",
          "not on the current scoreboard" in src)
    # ⚠ THE PROPERTY THAT MATTERS MOST, AND IT IS STRUCTURAL: this module has
    # no writer. Nothing it produces can reach the dataset.
    # ⚠ SCAN THE CODE, NOT THE PROSE. The first version matched this module's
    # own docstring -- which says it never writes to data/raw -- and reported
    # the promise as the violation.
    import ast
    ld_src = open(os.path.join(REPO, "scripts", "live_detail.py"),
                  encoding="utf-8").read()
    tree = ast.parse(ld_src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) \
                and ast.get_docstring(node):
            node.body = node.body[1:]
    ld = "\n".join(l.split("#")[0] for l in ast.dump(tree).splitlines())
    for bad in ("open", "json.dump", "data/raw", "commit", "write"):
        check("[-] live_detail.py never calls %s" % bad,
              bad not in ld, "found %r" % bad)

    print("\n7. The page states its source and never claims more")
    for label, path in (("private", os.path.join(REPO, "Cody", "START-HERE.html")),
                        ("public", os.path.join(REPO, "output",
                                                "vb_dashboard.html"))):
        if not os.path.exists(path):
            continue
        h = open(path, encoding="utf-8").read()
        check("%s: the inset names the official feed" % label,
              "official NCAA feed" in h)
        check("%s: it says live is not used in ratings" % label,
              "Not used in ratings until final" in h)
        check("%s: a missing box score says so honestly" % label,
              "not available from the official feed" in h)
        check("%s: a static host is told it needs the local server" % label,
              "Live detail needs the local server" in h)
        check("%s: staleness is visible" % label, "stale, retrying" in h)
        # ⚠ NO THIRD RANK BESIDE AVCA AND POWER. Checked as the inset's actual
        # column list rather than by grepping for a phrase -- the first version
        # matched the source comment that DENIES a watch score.
        import re as _re
        # anchored INSIDE lmcBody: an unanchored search found the
        # standings table (Rk/Conf/Overall) and accused the inset of it.
        hdr = _re.search(
            r"function lmcBody.*?<table><thead><tr>(.*?)</tr>", h, _re.S)
        cols = _re.findall(r"<th>(.*?)</th>", hdr.group(1)) if hdr else []
        check("%s: the inset shows counted stats only" % label,
              cols == ["Team", "K", "E", "TA", "Hit%", "Digs", "Blk", "Aces"],
              str(cols))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL LIVE MATCH CENTER GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
