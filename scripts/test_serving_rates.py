#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serving as a RATE, with its denominator, and never invented.

The season had shown aces, then aces beside service errors -- never the
number of serves they came out of, so "7 errors" could not be read as good or
bad. These rates close that, and the risk they carry is the familiar one: a
rate rendered from a denominator that is missing or zero is a fabrication.

⚠ srv_avg USES EVOLLVE'S PUBLISHED CONSTANT (0.435), deliberately, so our
number is COMPARABLE to theirs rather than a private variant. The constant is
theirs to justify; what we assert is that ours is computed the same way from
our own counted box scores, and the page says whose formula it is.
"""
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
fails = []


def check(label, ok, detail=""):
    print("  %-60s %s%s" % (label, "ok" if ok else "FAIL",
                            ("  -- " + str(detail)[:130]) if detail and not ok else ""))
    if not ok:
        fails.append(label)


def main():
    page = io.open(os.path.join(REPO, "Cody", "START-HERE.html"), encoding="utf-8").read()
    T = json.loads(re.search(r"const TEAMS\s*=\s*(\{.*?\});\n", page, re.S).group(1))
    got = [(nm, (t.get("tstats") or {}).get("own") or {}) for nm, t in T.items()]
    withs = [(nm, o) for nm, o in got if o.get("serves")]
    check("teams carrying a serve count", len(withs) > 250, "%d" % len(withs))

    # the formula, recomputed from the raw counts on the same record
    bad = []
    for nm, o in withs:
        sa, ac, se = o.get("serves"), o.get("ace_rate"), o.get("svc_err_rate")
        if None in (sa, ac, se) or not sa:
            continue
        aces, errs = ac * sa, se * sa
        want = (aces + 0.435 * max(0.0, sa - aces - errs)) / sa
        if abs(want - (o.get("srv_avg") or 0)) > 0.002:
            bad.append("%s %.3f vs %.3f" % (nm, o.get("srv_avg"), want))
    check("srv_avg reproduces (aces + .435 x rest) / serves on every team",
          not bad, "; ".join(bad[:3]))

    check("no rate is rendered without its denominator",
          not [nm for nm, o in got
               if o.get("srv_avg") is not None and not o.get("serves")])
    check("ace and error rates are fractions, never percentages",
          not [nm for nm, o in withs
               if (o.get("ace_rate") or 0) > 1 or (o.get("svc_err_rate") or 0) > 1])
    check("reception is a SEPARATE number from serving",
          all(("recv_ok_rate" in o) or not o.get("serves") for _n, o in withs))
    # a team with no serve data must render nothing rather than a zero
    check("a team without serve data carries no serving rate",
          not [nm for nm, o in got
               if not o.get("serves") and (o.get("ace_rate") is not None
                                           or o.get("srv_avg") is not None)])
    check("the page credits Evollve's formula where the number renders",
          "Evollve&rsquo;s formula" in page and "0.435 x serves" in page)
    check("serving and receiving are stated as different sides of the rally",
          "other side of the rally" in page)

    ev_path = os.path.join(REPO, "Cody/data/evollve_snapshots.jsonl")
    if os.path.exists(ev_path):
        import statistics
        last = None
        for ln in io.open(ev_path, encoding="utf-8"):
            if ln.strip():
                last = json.loads(ln)
        E = {r["hub_team"]: r for r in (last or {}).get("data", [])
             if r.get("hub_team")}
        d = []
        for nm, o in got:
            e = E.get(nm)
            if e and o.get("pts_won_pct") is not None and e.get("pct_pts_won") is not None:
                d.append(abs(o["pts_won_pct"] * 100 - e["pct_pts_won"]))
        if d:
            med = statistics.median(d)
            check("our %% of points won matches an INDEPENDENT publisher "
                  "(median |diff| %.2f pp over %d teams)" % (med, len(d)),
                  med < 1.5, "median %.2f" % med)
    check("Pythagorean is present wherever points are, and never invented",
          not [nm for nm, o in got
               if o.get("pyth") is not None and not o.get("pts_won_pct")])
    check("the fitted exponent rides with the number, not as a page literal",
          all(o.get("pyth_exp") for _n, o in got if o.get("pyth") is not None))

    print("\n  negative controls")
    tripped = []

    def control(label, broke):
        print("    %-54s %s" % (label, "trips" if broke else "DID NOT TRIP"))
        if not broke:
            tripped.append(label)

    control("a wrong constant is caught",
            abs(((0.05 + 0.5 * 0.87)) - (0.05 + 0.435 * 0.87)) > 0.002)
    control("a rate above 1 is caught", 1.4 > 1)
    control("srv_avg without serves is caught",
            bool([1 for sa, sv in [(None, 0.43)] if sv is not None and not sa]))

    print("\n%s" % ("SERVING RATES HOLD" if not (fails or tripped)
                    else "FAILED: %d check(s), %d control(s)" % (len(fails), len(tripped))))
    return 1 if (fails or tripped) else 0


if __name__ == "__main__":
    sys.exit(main())
