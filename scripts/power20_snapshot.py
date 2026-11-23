#!/usr/bin/env python3
"""LOCAL-ONLY, PRIVATE (mail 097): refresh the matched current-POWER / POWER 2.0 snapshot inside the
local refresh, after the fit inputs are rebuilt and before the private page reads them.

Runs the frozen-recipe ranking command (Cody/coordination/research/POWER-S0-RANKING-2026-11-05/rank.py) with
  --under-refresh  local_refresh already holds the input lock (re-taking it would block on itself)
  --if-changed     refit only when the receipt's FIT INPUTS changed (scores, corrections, sites, earned
                   counts, start features, conference map) or the code changed; timestamp-only rewrites skip
On failure the previous verified snapshot stays (rank.py writes only after a valid fit) and this exits
non-zero, so local_refresh marks it pending and retries next cycle. Absent research code (CI) -> exit 0."""
import os, subprocess, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANK = os.path.join(REPO, "Cody", "coordination", "research", "POWER-S0-RANKING-2026-11-05", "rank.py")
# mail 107: the private S0 performance ledger rides the same safe step (skips when its inputs are unchanged; a failure
# keeps the previous latest.json and does not fail the POWER 2.0 snapshot)
LEDGER = os.path.join(REPO, "Cody", "coordination", "research", "POWER-PERFORMANCE-LEDGER-2026-11-06", "build_ledger.py")


def main():
    if not os.path.exists(RANK):
        print("power 2.0 snapshot: research code absent (CI/fresh checkout) -- skipped")
        return 0
    r = subprocess.run([sys.executable, RANK, "--under-refresh", "--if-changed"], cwd=REPO,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    tail = [l for l in (r.stdout or "").splitlines() if "Warning" not in l and "np." not in l]
    print("power 2.0 snapshot: " + (" ".join(tail[-8:]) if tail else "(no output)"))
    if os.path.exists(LEDGER):
        l = subprocess.run([sys.executable, LEDGER, "--if-changed"], cwd=REPO,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        lt = [x for x in (l.stdout or "").splitlines() if x.startswith("ledger")]
        print("performance ledger: " + (lt[-1] if lt else "failed (previous ledger kept): exit %d" % l.returncode))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
