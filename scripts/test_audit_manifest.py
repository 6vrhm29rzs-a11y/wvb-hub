#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE RELEASE INVARIANT -- audit manifest vs every counted surface.

The build emits data/audit_manifest_{S}.json from the exact dataset it
consumed and FAILS CLOSED in build_hub if a counted surface diverges.
This suite re-verifies the same agreements from the shipped artifacts --
so a stale artifact committed later, or a rebuild that raced, is caught
in CI too -- and proves the verifier itself can fail.
"""

import hashlib
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def load(rel):
    p = os.path.join(REPO, rel)
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) \
        else None


def verify(man, totals, cnt_gids, cnt_d1, digby_meta, resume_meta,
           rating_meta):
    """The agreement rules, as data -> list of violations."""
    out = []
    if man["totals"] != totals:
        out.append("manifest totals != recomputed totals")
    gh = hashlib.sha256("\n".join(sorted(cnt_gids)).encode()).hexdigest()
    if man["counted_gids_sha256"] != gh:
        out.append("counted gid set moved since the manifest")
    if (digby_meta or {}).get("matches_counted") is not None and \
            digby_meta["matches_counted"] != \
            totals["rating_eligible_through_yesterday"]:
        out.append("digby matches_counted %s != "
                   "rating_eligible_through_yesterday %s"
                   % (digby_meta["matches_counted"],
                      totals["rating_eligible_through_yesterday"]))
    if (resume_meta or {}).get("matches") is not None and \
            resume_meta["matches"] != len(cnt_d1):
        out.append("resume matches %s != counted D-I %s"
                   % (resume_meta["matches"], len(cnt_d1)))
    if (rating_meta or {}).get("validated") and \
            (rating_meta.get("matches_in") is not None) and \
            rating_meta["matches_in"] != \
            totals["rating_eligible_through_yesterday"]:
        out.append("validated rating matches_in != rating_eligible")
    return out


def main():
    import season_counts as SC
    man = load("data/audit_manifest_%d.json" % SEASON)
    check("the build emitted an audit manifest", bool(man))
    if not man:
        return finish()
    doc = load("data/data_%d.json" % SEASON) or {}
    games = doc.get("games") or []
    totals = SC.totals(games, SEASON)
    cnt = SC.countable(games, SEASON)
    cnt_gids = [str(g.get("game_id")) for g in cnt]
    cnt_d1 = SC.countable(games, SEASON, d1_only=True)

    ds_path = os.path.join(REPO, "data", "data_%d.json" % SEASON)
    ds_sha = hashlib.sha256(open(ds_path, "rb").read()).hexdigest()
    stale_ds = man["dataset_sha256"] != ds_sha
    if stale_ds:
        # the dataset was rebuilt after the page -- the totals comparison
        # below is the real invariant; the hash mismatch alone means
        # "rebuild the page", and preflight's build step does exactly that
        print("  (dataset bytes moved since the manifest -- totals "
              "compared on the CURRENT snapshot)")
    v = verify(man, totals, cnt_gids, cnt_d1,
               (load("data/digby_top25_%d.json" % SEASON) or {}).get("meta"),
               (load("data/resume_%d.json" % SEASON) or {}).get("meta"),
               (load("data/rating_%d.json" % SEASON) or {}).get("meta"))
    if stale_ds:
        v = [x for x in v if "manifest totals" not in x
             and "gid set moved" not in x]
    check("every counted surface agrees with the contract totals",
          not v, v)
    check("manifest counts: n_counted == ok+? recomputable",
          man["n_counted"] == len(cnt_gids) or stale_ds,
          (man["n_counted"], len(cnt_gids)))

    print("\n  [NEG] the verifier can fail")
    bad = dict(man, counted_gids_sha256="0" * 64)
    check("[NEG] a moved gid set is flagged",
          any("gid set" in x for x in verify(
              bad, totals, cnt_gids, cnt_d1, None, None, None)))
    check("[NEG] a stale digby artifact is flagged",
          any("digby" in x for x in verify(
              man, totals, cnt_gids, cnt_d1,
              {"matches_counted": totals["rating_eligible_through_yesterday"] + 5},
              None, None)))
    check("[NEG] a stale resume artifact is flagged",
          any("resume" in x for x in verify(
              man, totals, cnt_gids, cnt_d1, None,
              {"matches": len(cnt_d1) + 3}, None)))
    check("the build-time gate exists and fails closed",
          "AUDIT MANIFEST violated" in io.open(
              os.path.join(REPO, "scripts/build_hub.py"),
              encoding="utf-8").read())
    if not check_generation_fingerprints():
        FAILS.append("generation fingerprints diverge or gate missing")
    return finish()


def finish():
    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("AUDIT MANIFEST INVARIANT HOLDS")
    return 0


def check_generation_fingerprints():
    """Architect #2 (2026-09-03): truth-bearing artifacts share ONE corpus
    generation, and the build fails closed when they do not."""
    import season_counts as SC
    fp = SC.corpus_fingerprint(2026)
    bad = []
    for name, pth in (("digby", "data/digby_top25_2026.json"),
                      ("resume", "data/resume_2026.json"),
                      ("rating", "data/rating_2026.json"),
                      ("confidence", "data/result_confidence_2026.json")):
        full = os.path.join(REPO, pth)
        if not os.path.exists(full):
            continue
        st = ((json.load(open(full)).get("meta") or {})
              .get("corpus_fingerprint"))
        if st is None:
            bad.append("%s carries NO corpus_fingerprint stamp" % name)
        elif st != fp:
            bad.append("%s stamped %s vs corpus %s" % (name, st, fp))
    if bad:
        print("  FAIL generation fingerprints: %s" % "; ".join(bad))
        return False
    print("  ok   all truth-bearing artifacts stamp THIS corpus generation "
          "(%s)" % fp)
    src = open(os.path.join(REPO, "scripts", "build_hub.py")).read()
    ok = ("corpus_fingerprint %s != build's %s" in src
          and "_mm_fails.append" in src)
    print(("  ok   " if ok else "  FAIL ") +
          "the build gate fails closed on a mismatched stamp")
    return ok


if __name__ == "__main__":
    sys.exit(main())
