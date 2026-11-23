#!/usr/bin/env python3
"""097 guards: the matched POWER 2.0 snapshot refreshes on real fit-input changes, skips no-change and
timestamp-only cycles, keeps the last verified snapshot on failure, and is retried by the refresh gate.
Snapshot writes go to a temp folder; the refresh cycle is driven with every subprocess stubbed."""
import copy, datetime, json, os, sys, tempfile
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
ok = True


def check(c, m):
    global ok
    print(("PASS " if c else "FAIL ") + m); ok = ok and bool(c)


# ---- B. refresh-gate integration (always runs; no research code needed) ----
import local_refresh as LR
state = {"dig": {}, "calls": [], "fail": False, "fp": "f1"}
def _stub(args, env_extra=None, season="2026"):
    state["calls"].append(args[0])
    if args[0] == LR.POWER20:
        return (1 if state["fail"] else 0), "x"
    return 0, "ok"
LR._run = _stub
LR.fingerprint = lambda: state["fp"]
LR.digests = lambda fp: {"finals": fp, "rating": "r", "presentation": "p"}
LR.load_digests = lambda: dict(state["dig"])
LR.save_digests = lambda d: state.__setitem__("dig", dict(d))
recs = []
LR._record = lambda outcome, **kw: recs.append(dict(kw, outcome=outcome))
def cycle(fail, fp=None):
    state["fail"] = fail; state["calls"] = []
    if fp:
        state["fp"] = fp
    LR._cycle(False, 0)
    return list(state["calls"])
c1 = cycle(True)
check(LR.POWER20 in c1 and recs[-1]["outcome"] == "rebuilt" and recs[-1]["power20"] == "failed_pending_retry"
      and state["dig"].get("power20_pending"), "full rebuild with a failed snapshot: page still rebuilt, snapshot marked pending")
c2 = cycle(False)
c2 = [x for x in c2 if x != "scripts/test_crawl_freshness.py" and x not in [a[0] for a in LR.CRAWL] and x not in [a[0] for a in LR.PREGATE]]
check(c2 == [LR.POWER20, "scripts/build_hub.py"],
      "next cycle with unchanged inputs retries the snapshot, then rebuilds the page (%s)" % c2)
check(recs[-1]["outcome"] in ("power20_retried",) and not state["dig"].get("power20_pending"), "successful retry clears pending")
c3 = cycle(False)
check(LR.POWER20 not in c3 and "scripts/build_hub.py" not in c3 and recs[-1]["outcome"] == "no_new_final", "settled: idle cycle runs no snapshot fit")
c4 = cycle(False, fp="f2")
check(LR.POWER20 in c4 and recs[-1]["power20"] == "ok", "a real input change (new fingerprint) refits the snapshot in the full rebuild")
order = [a[0] for _, a in LR.REBUILD]
check(order.index("scripts/season_only_candidate.py") < order.index(LR.POWER20) < order.index("scripts/build_hub.py"),
      "snapshot runs after the fit inputs are rebuilt and before the page reads it")

# ---- A/C. snapshot command (local only: research code present) ----
RANKDIR = os.path.join(REPO, "Cody", "coordination", "research", "POWER-S0-RANKING-2026-11-05")
if os.path.exists(os.path.join(RANKDIR, "rank.py")):
    sys.path.insert(0, RANKDIR)
    import rank as RK
    RK.OUT = tempfile.mkdtemp(prefix="p20refresh-")
    cut = datetime.date(2026, 11, 6)
    s1 = RK.run(cut, if_changed=True)
    check(s1.get("_written") and not s1.get("unchanged"), "first run writes a snapshot")
    s2 = RK.run(cut, if_changed=True)
    check(s2.get("unchanged") and len([f for f in os.listdir(RK.OUT) if f.startswith("snapshot_")]) == 1,
          "no-change run skips (no new snapshot)")
    rc, rid, blob = RK.build_receipt(cut)
    rc2 = copy.deepcopy(rc); rc2["input_files_sha256"] = dict((k, "0" * 16) for k in rc["input_files_sha256"])
    check(RK.content_id(rc2) == rid, "timestamp-only change (input FILE hashes differ, fit inputs identical) keeps the same identity")
    # a real fit-input change at the SAME cutoff: one corrected set score
    real = RK.AV.data_for
    def altered(season):
        d = real(season); d = dict(d); ms = [dict(m) for m in d["ms"]]
        for m in ms:
            if m["day"] < cut:
                m["sets"] = [tuple(x) for x in m["sets"]]; a, b = m["sets"][0]; m["sets"][0] = (a + 1, b); break
        d["ms"] = ms; return d
    RK.AV.data_for = altered
    try:
        s3 = RK.run(cut, if_changed=True)
    finally:
        RK.AV.data_for = real
    vp = s3.get("vs_previous") or {}
    check(s3.get("_written") and vp.get("changed_existing_matches") == 1 and vp.get("new_matches") == 0,
          "a corrected score at the same cutoff refits and is labelled as a changed input (%s)" % {k: vp.get(k) for k in ("new_matches", "changed_existing_matches")})
    latest = open(os.path.join(RK.OUT, "latest.json")).read()
    orig = RK.ST.fit_both
    RK.ST.fit_both = lambda *a, **k: dict(orig(*a, **k), h=float("nan"))
    try:
        RK.run(cut, if_changed=False); check(False, "a failing fit must not write")
    except RK.NoRanking:
        check(open(os.path.join(RK.OUT, "latest.json")).read() == latest, "a failing fit keeps the last verified snapshot unchanged")
    finally:
        RK.ST.fit_both = orig
else:
    print("SKIP snapshot checks: research code absent (CI)")
print("ALL POWER 2.0 REFRESH CHECKS HOLD" if ok else "POWER 2.0 REFRESH CHECKS FAILED"); sys.exit(0 if ok else 1)
