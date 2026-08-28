# -*- coding: utf-8 -*-
"""Run every guard suite in scripts/, discovered rather than listed.

⚠⚠ WHY THIS EXISTS. The daily workflow used to name each suite by hand, and
the list drifted THREE times. The step's own comments admitted the first two
("four suites were written today and never added here", then "FIVE MORE SUITES
THAT EXISTED AND DID NOT RUN HERE"); by 2026-08-27 it ran 32 of 46, so
FOURTEEN guards protected nothing in the one place that protects the live site
-- among them the ledger, the wayfinding checks and the shipping gate. All
fourteen passed the moment they were run. None had been excluded for a reason;
they were forgotten. A hand-maintained list of things that must not be
forgotten is the wrong shape.

Every suite runs even after one fails: on a nightly job the full list of what
broke is worth more than the first line of it.

Python 3.9 target. Run: python3 scripts/run_all_guards.py
"""
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")

# A suite may be skipped ONLY with a reason written here. Empty on purpose:
# nothing currently needs the network, an API key, or a display. Anything added
# to this map is a decision somebody has to defend, which is the point.
SKIP = {}

# ⚠ ONE CALLER HAS TO BE ABLE TO BREAK A CYCLE. test_pipeline_fresh_checkout
# re-runs the daily workflow's own commands inside a throwaway checkout, and
# this runner is now one of those commands -- so it would run the fresh-checkout
# suite, which would run this runner, forever. That suite already excluded
# itself BY NAME from the commands it executes; the name now sits behind this
# script, so it passes it here instead. Only a suite named in the environment
# is skipped, and the skip is printed, so it can never be silent.
_ENV_EXCLUDE = [x.strip() for x in
                (os.environ.get("WVB_GUARD_EXCLUDE") or "").split(",")
                if x.strip()]

# Discovery must never come back empty and quietly pass. This is the floor, not
# a target -- it only has to catch "the glob matched nothing".
MIN_SUITES = 30


def main():
    suites = sorted(f for f in os.listdir(SCRIPTS)
                    if f.startswith("test_") and f.endswith(".py"))
    if len(suites) < MIN_SUITES:
        print("only %d suites discovered -- expected at least %d. Discovery is "
              "broken; refusing to report a clean run."
              % (len(suites), MIN_SUITES))
        return 1

    failed, skipped, t0 = [], [], time.time()
    for s in suites:
        if s in _ENV_EXCLUDE:
            skipped.append((s, "excluded by WVB_GUARD_EXCLUDE (cycle break)"))
            print("SKIP  %-34s excluded by the caller (cycle break)" % s)
            continue
        if s in SKIP:
            skipped.append((s, SKIP[s]))
            print("SKIP  %-34s %s" % (s, SKIP[s]))
            continue
        t = time.time()
        r = subprocess.call([sys.executable, os.path.join(SCRIPTS, s)],
                            cwd=REPO)
        took = time.time() - t
        if r == 0:
            print("ok    %-34s %5.1fs" % (s, took))
        else:
            print("FAIL  %-34s %5.1fs  (exit %d)" % (s, took, r))
            failed.append(s)

    print("\n%d suites, %d failed, %d skipped, %.0fs"
          % (len(suites), len(failed), len(skipped), time.time() - t0))
    for s in failed:
        print("   FAILED: %s" % s)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
