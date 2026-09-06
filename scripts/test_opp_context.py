#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Opponent context on team pages (Cody, 2026-09-06): every played/upcoming
match carries the opponent's POWER rank as of now; a played match carries the
AVCA rank AT THE TIME of the match, from the poll archive; and the
quality-of-results scale averages opponent POWER in wins and losses with no
stand-ins. The at-time check RECOMPUTES from the archive rather than pinning
a team name, so it survives the polls moving."""
import io, json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
FAILS = []


def check(label, ok, extra=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(extra)[:80]))
    if not ok:
        FAILS.append(label)


def teams_payload(h):
    i = h.find("const TEAMS = ")
    j = h.find(";\nconst", i)
    if j < 0:
        j = h.find(";\n", i + 20)
    return json.loads(h[i + len("const TEAMS = "):j])


def poll_maps():
    out = []
    fp = os.path.join(REPO, "data", "raw", str(SEASON), "polls_avca.jsonl")
    if not os.path.exists(fp):
        return out
    for ln in io.open(fp, encoding="utf-8"):
        if not ln.strip():
            continue
        row = json.loads(ln)
        if str(row.get("season")) != str(SEASON) or \
                row.get("is_previous_season") in (True, "True"):
            continue
        m = {}
        for r in (row.get("rows") or []):
            nm = re.sub(r"\s*\(\d+\)\s*$", "", str(r.get("SCHOOL") or ""))
            try:
                m[nm] = int(r.get("RANK"))
            except (TypeError, ValueError):
                pass
        if m and row.get("date"):
            out.append((str(row["date"]), m))
    out.sort()
    return out


def main():
    if not os.path.exists(PAGE):
        print("  (no built private page -- skipping)")
        return 0
    h = io.open(PAGE, encoding="utf-8").read()
    T = teams_payload(h)

    print("1. THE PAYLOAD")
    check("every team carries wlq", all("wlq" in t for t in T.values()),
          sum(1 for t in T.values() if "wlq" not in t))
    bad = []
    for nm, t in T.items():
        q = t.get("wlq") or {}
        for side, n in (("w", "nw"), ("l", "nl")):
            v = q.get(side)
            if v is not None and not (0 <= v <= 100):
                bad.append("%s %s=%s" % (nm, side, v))
            if v is None and q.get(n):
                bad.append("%s: %d %s-matches but no average" % (nm, q[n], side))
            if v is not None and not q.get(n):
                bad.append("%s: an average with a zero count" % nm)
        if q.get("nw", 0) + q.get("nl", 0) > len(t.get("played") or []):
            bad.append("%s: counts exceed matches" % nm)
    check("wlq averages in [0,100], counts coherent, no value without a count",
          not bad, bad[:3])

    # opr must equal the opponent's own rank in the same payload
    bad = []
    for nm, t in T.items():
        for g in (t.get("played") or []) + (t.get("fixtures") or []):
            r = g.get("opr")
            if r is None:
                continue
            ot = T.get(g.get("opp"))
            if ot and ot.get("rank") != r:
                bad.append("%s vs %s: opr %s != rank %s"
                           % (nm, g.get("opp"), r, ot.get("rank")))
    check("opr always equals the opponent's own current rank", not bad, bad[:3])
    n_opr = sum(1 for t in T.values() for g in (t.get("played") or [])
                if g.get("opr"))
    check("played rows actually carry opr", n_opr > 100, n_opr)

    print("2. AT-TIME AVCA -- recomputed from the archive")
    polls = poll_maps()
    if len(polls) >= 2:
        def at(d):
            best = polls[0][1]
            for pd, m in polls:
                if pd <= d:
                    best = m
            return best
        checked = mism = 0
        for nm, t in T.items():
            for g in (t.get("played") or []):
                if "oav" not in g:
                    continue
                want = at(g.get("d") or "").get(g.get("opp"))
                # the archive spells some schools its own way; a name the
                # archive map cannot address is not a mismatch
                if want is None:
                    continue
                checked += 1
                if want != g["oav"]:
                    mism += 1
        check("every oav equals the poll in effect on the match date "
              "(%d checked)" % checked, checked > 50 and mism == 0, mism)
        movers = [t for t in polls[0][1]
                  if t in polls[-1][1] and polls[0][1][t] != polls[-1][1][t]]
        early = [g for t in T.values() for g in (t.get("played") or [])
                 if g.get("oav") and g.get("opp") in movers
                 and (g.get("d") or "") < polls[-1][0]]
        proved = [g for g in early if g["oav"] == polls[0][1][g["opp"]]
                  and g["oav"] != polls[-1][1][g["opp"]]]
        check("at least one early match proves at-time != current",
              bool(proved), "%d early rows vs movers" % len(early))
        # negative control: an always-current oav must trip the recompute
        if proved:
            g = dict(proved[0])
            g["oav"] = polls[-1][1][g["opp"]]
            trips = at(g["d"]).get(g["opp"]) != g["oav"]
            check("negative control: a current-rank oav on an early match "
                  "is caught", trips)
    else:
        print("  (fewer than two polls on file -- at-time checks idle, "
              "stated not skipped silently)")

    print("3. THE RENDERERS")
    check("oppChips is defined once",
          h.count("function oppChips(") == 1, h.count("function oppChips("))
    check("all three surfaces call it", h.count("oppChips(") >= 4,
          h.count("oppChips("))
    check("a missing rank renders nothing, never NR",
          "g.opr ?" in h and "'NR'" not in
          h[h.find("function oppChips"):h.find("function oppChips") + 600])
    check(".oprk chip CSS exists", ".oprk{" in h)
    check("the quality scale renders from t.wlq", "const q = t.wlq;" in h)
    check("a null side draws no dot", "v == null ? ''" in h)
    check("dots are clamped to the track",
          "Math.max(0, Math.min(100, v))" in h)
    check("the note owns the exclusions",
          "contribute nothing rather" in h)

    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        hp = io.open(pub, encoding="utf-8").read()
        check("public build carries the same context (ours to publish)",
              '"opr":' in hp and '"wlq":' in hp)

    if FAILS:
        print("\nFAILED: %d" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("\nALL OPPONENT-CONTEXT GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
