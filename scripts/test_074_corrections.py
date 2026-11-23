#!/usr/bin/env python3
"""074 guards. #1: a failed candidate fit is retried by the OUTER refresh gate
on the next cycle, through the real local_refresh._cycle (every subprocess and
all persistence stubbed -- no crawl, no model run, no real state touched).
#2: an empty/failed live poll keeps the last good live map (node runs the
page's own deskApply). #3 is checked by the rendered phone probe (handoff)."""
import json, os, re, subprocess, sys, tempfile
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
ok = True


def check(c, msg):
    global ok
    print(("PASS " if c else "FAIL ") + msg)
    ok = ok and bool(c)


def run_cycles(script):
    """script: list of per-cycle dicts {cand_fail: bool, finals: str}. Returns
    (candidate call counts per cycle, records, final digests)."""
    import local_refresh as LR
    state = {"dig": {}, "cand": 0, "rec": [], "fail": False, "fp": "f1"}
    LR._run = lambda args, env_extra=None, season="2026": (
        (state.__setitem__("cand", state["cand"] + 1) or (1 if state["fail"] else 0), "x")
        if args[0] == LR.CANDIDATE and "--weekly-only" not in args else (0, "ok"))
    LR.fingerprint = lambda: state["fp"]
    LR.digests = lambda fp: {"finals": fp, "rating": "r", "presentation": "p"}
    LR.load_digests = lambda: dict(state["dig"])
    LR.save_digests = lambda d: state.__setitem__("dig", dict(d))
    LR._record = lambda outcome, **kw: state["rec"].append(dict(kw, outcome=outcome))
    counts = []
    for step in script:
        state["fail"] = step["cand_fail"]
        state["fp"] = step.get("finals", state["fp"])
        before = state["cand"]
        rc = LR._cycle(False, 0)
        counts.append((state["cand"] - before, rc))
    return counts, state["rec"], state["dig"]


# failure -> retry fails -> retry succeeds -> idle
counts, rec, dig = run_cycles([{"cand_fail": True}, {"cand_fail": True},
                               {"cand_fail": False}, {"cand_fail": False}])
check(counts[0][0] == 1 and rec[0]["outcome"] == "rebuilt"
      and rec[0]["candidate"] == "refit_failed_pending_retry",
      "cycle 1: page rebuilt, candidate failure recorded separately (%s)" % rec[0])
check(counts[1][0] == 1 and rec[1]["outcome"] == "candidate_retry_failed",
      "cycle 2 (inputs unchanged): candidate RETRIED and failure kept pending")
check(counts[2][0] == 1 and rec[2]["outcome"] == "candidate_retried",
      "cycle 3: retry succeeds")
check(counts[3][0] == 0 and rec[3]["outcome"] == "no_new_final" and dig.get("candidate_pending") is False,
      "cycle 4: settled -- idle, candidate not invoked")
# negative control: without the pending flag the old gate never retried
import local_refresh as LR
real = LR._candidate_retry
LR._candidate_retry = lambda prev, t0: None
counts2, rec2, _ = run_cycles([{"cand_fail": True}, {"cand_fail": False}])
LR._candidate_retry = real
check(counts2[1][0] == 0, "negative control: with the retry removed, cycle 2 never calls the fit (the 074 bug)")
# a new final while pending: the full rebuild itself refits and clears pending
counts3, rec3, dig3 = run_cycles([{"cand_fail": True}, {"cand_fail": False, "finals": "f2"}])
check(rec3[1]["outcome"] == "rebuilt" and rec3[1]["candidate"] == "refit_ok" and not dig3["candidate_pending"],
      "new final while pending: full rebuild refits and clears pending")

# ---- #2: live poll response semantics, executed in node ----
src = open(os.path.join(REPO, "scripts", "build_hub.py"), encoding="utf-8").read()
m = re.search(r"function liveResponseUsable\(.*?\n\}\n", src, re.S)
check(m, "liveResponseUsable() exists in the page source")
if m:
    js = m.group(0) + r"""
const out = {};
const NOW = 1000;
out.err = liveResponseUsable(null, 55);
out.empty_transient = liveResponseUsable({games: []}, 55);
out.empty_authoritative = liveResponseUsable({games: [], complete: true}, 55);
out.populated = liveResponseUsable({games: [{id: 1}]}, 55);
out.empty_when_none_known = liveResponseUsable({games: []}, 0);
out.bad_shape = liveResponseUsable({games: "x"}, 55);
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
    r = subprocess.run(["node", fh.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    try:
        o = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        o = {}
        print(r.stdout)
    check(o.get("err") is False, "error/no payload: last good live map kept")
    check(o.get("bad_shape") is False, "malformed payload: kept")
    check(o.get("empty_transient") is False, "empty slate WITHOUT an authoritative flag over a populated map: kept")
    check(o.get("empty_authoritative") is True, "empty slate the server marks complete: applied (stale matches clear)")
    check(o.get("populated") is True, "populated payload: applied")
    check(o.get("empty_when_none_known") is True, "empty slate when nothing is known: applied (nothing to protect)")
check("liveResponseUsable(" in src.split("function deskApply")[1][:1500] if "function deskApply" in src else False,
      "deskApply consults liveResponseUsable before replacing the map")
print("ALL 074 CHECKS HOLD" if ok else "074 CHECKS FAILED")
sys.exit(0 if ok else 1)
