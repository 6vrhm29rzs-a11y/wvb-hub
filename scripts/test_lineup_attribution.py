#!/usr/bin/env python3
"""Lineup-attribution permutation sweep (architect plan #5, 2026-09-03).

The feed's per-game LINEUPS are a second two-sided structure that the
confirmed inversions also swapped -- measured: exactly the 7 lineup-held
confirmed-inversion games flag (starters fit the OPPOSING roster ~1.0,
their own 0.0, both sides) and NOTHING else. This guard re-runs that sweep:
a flagged game must carry a ledgered box_team_swap correction; a flagged
game WITHOUT one is a new inversion candidate and fails loudly.

⚠ FOR THE FUTURE CONSUMER: no script reads 2026 lineups' team attribution
today. Whoever builds one MUST apply season_counts corrections'
box_team_swap first -- the raw file keeps the feed's swapped attribution
by design (raw logs are never rewritten)."""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_counts as SC  # noqa: E402

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def main():
    R = json.load(open(os.path.join(
        REPO, "data/raw/2026/rosters_2026.json")))["teams"]
    d = json.load(open(os.path.join(REPO, "data/data_2026.json")))
    id2n = {str(t["team_id"]): t["name_short"] for t in d["teams"]}
    key = lambda s: re.sub(r"[^a-z]", "", (s or "").lower())  # noqa: E731
    RK = {t: set(key(p.get("name_raw") or "")
                 for p in (v.get("players") or [])) for t, v in R.items()}
    seen = {}
    for line in open(os.path.join(REPO, "data/raw/2026/lineups.jsonl")):
        r = json.loads(line)
        seen[str(r.get("game_id"))] = r
    corr = SC.corrections(2026)
    swapped = {g for g, c in corr.items()
               if (c.get("correct") or {}).get("box_team_swap")}
    flagged, n = [], 0
    for gid, r in seen.items():
        sides = r.get("lineups") or []
        if len(sides) != 2:
            continue
        fits, ok = [], True
        for i, t in enumerate(sides):
            team = id2n.get(str(t.get("team_id") or ""))
            other = id2n.get(str(sides[1 - i].get("team_id") or ""))
            names = [key(p.get("name")) for p in (t.get("starters") or [])
                     if p.get("name")]
            if not team or len(names) < 4 or not RK.get(team) \
                    or not RK.get(other):
                ok = False
                break
            own = sum(1 for x in names if x in RK[team]) / len(names)
            oth = sum(1 for x in names if x in RK[other]) / len(names)
            fits.append((team, own, oth))
        if not ok or len(fits) != 2:
            continue
        n += 1
        if any(o > w for _, w, o in fits):
            flagged.append(gid)
    print("  measured %d lineup games; %d flagged" % (n, len(flagged)))
    check("[+] the sweep measures a real population", n >= 200, n)
    # A gid under RESULT REVIEW (an unresolved official conflict in
    # result_evidence.json -- one school contradicts, the other not yet
    # posted) is adjudicated: it counts nowhere and carries its own
    # review_by. The flag and the review describe the same suspicion.
    under_review = SC.review_gids(2026)
    new = [g for g in flagged if g not in swapped
           and g not in under_review]
    known = [g for g in flagged if g in swapped]
    # A flagged final whose SCHOOLS have not posted yet may sit in the
    # pending ledger (machine signal corroborates, never quarantines) --
    # but only until its recheck_by date. An expired entry fails loud:
    # pending must resolve into a correction or a confirmed_correct
    # label, never rot into silence.
    import datetime as _dt
    _pend = {}
    _pp = os.path.join(REPO, "data/raw/2026/attribution_pending.json")
    if os.path.exists(_pp):
        _pend = (json.load(open(_pp)).get("pending") or {})
    _today = _dt.date.today().isoformat()
    fresh_pending = {g for g, e in _pend.items()
                     if str(e.get("recheck_by", "")) >= _today}
    expired = [g for g in _pend
               if str(_pend[g].get("recheck_by", "")) < _today]
    print("  %d flagged games carry a ledgered box_team_swap (the "
          "confirmed inversions); %d pending school evidence"
          % (len(known), len(fresh_pending)))
    check("every lineup-swapped game is a LEDGERED inversion or "
          "PENDING school evidence (with an unexpired recheck_by)",
          not [g for g in new if g not in fresh_pending],
          [g for g in new if g not in fresh_pending][:5])
    check("no pending entry has outlived its recheck_by",
          not expired, expired[:5])
    # NEGATIVE CONTROL: an expired pending entry must be caught.
    _fake = {"g0": {"recheck_by": "2000-01-01"}}
    check("[NEG] an expired pending entry would trip",
          [g for g in _fake if str(_fake[g]["recheck_by"]) < _today]
          == ["g0"])
    check("[+] the known inversions with held lineups DO flag (the sweep "
          "can see the defect)", len(known) >= 5, len(known))
    src = open(os.path.join(REPO, "scripts",
                            "test_lineup_attribution.py")).read()
    check("the future-consumer warning is written where a builder will "
          "find it", "MUST apply" in src)

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL LINEUP-ATTRIBUTION CHECKS HOLD")


if __name__ == "__main__":
    main()
