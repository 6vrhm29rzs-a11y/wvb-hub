#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One LOCAL refresh cycle: poll for finals, rebuild the page if any landed.

WHY THIS EXISTS (Cody, 2026-08-28). The power rankings said they move with
every result, and in CI they do -- refresh.yml reruns the whole derived
sequence each cycle. But the page Cody actually reads is the LOCAL build
served by live_server, and nothing on this machine reran the pipeline: his
rankings were frozen at whatever the last manual run computed, on the
season's first 196-match day. live_server polls scores every 60s, which
makes the page LOOK live while the rankings under it are not.

This script is the local twin of refresh.yml's crawl + rebuild steps, and
scripts/test_local_refresh.py asserts the two stay in step -- if a script is
added to the workflow and not here, the guard fails, because a silent drift
between "what CI rebuilds" and "what the local page rebuilds" is exactly how
the gap this fixes would creep back.

Run one cycle:   python3 scripts/local_refresh.py
Loop forever:    python3 scripts/local_refresh.py --loop        (20 min default)
Force a rebuild: python3 scripts/local_refresh.py --force       (skip fingerprint)

Safe to run alongside a manual pipeline: a non-blocking flock on
data/.local_refresh.lock means the second starter exits politely instead of
interleaving crawls. The crawl itself is append-only with atomic checkpoints,
so even a crash mid-cycle cannot corrupt the log (R2 semantics, tested by
test_crawl_freshness.py, which runs FIRST every cycle exactly as CI does).
"""

import fcntl
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or "python3"
LOCK = os.path.join(REPO, "data", ".local_refresh.lock")
LOOP_SECONDS = int(os.environ.get("WVB_LOCAL_REFRESH_SECONDS", "1200"))

# ⚠ MIRRORS .github/workflows/refresh.yml -- "Poll for finals" step.
# test_local_refresh.py compares this list against the workflow file.
CRAWL = [
    ["scripts/crawl_2025.py", "recent"],
    ["scripts/crawl_2025.py", "games"],
    ["scripts/crawl_2025.py", "boxscores"],
    ["scripts/crawl_2025.py", "players"],
    ["scripts/crawl_pbp.py"],            # optional in CI too
]

# ⚠ MIRRORS refresh.yml -- "Rebuild derived outputs" step, minus --public
# (publishing is CI's job; the local page is Cody/START-HERE.html).
# The 2025 base is kept even though it exists locally: one sequence, one
# definition (R4), and it measures at ~20s.
REBUILD = [
    ({"WVB_SEASON": "2025"}, ["scripts/build_dataset.py"]),
    ({"WVB_SEASON": "2025"}, ["scripts/rpi_2025.py"]),
    ({"WVB_SEASON": "2025"}, ["scripts/rating_2025.py"]),
    ({}, ["scripts/venues.py"]),
    ({}, ["scripts/availability.py"]),
    ({}, ["scripts/build_dataset.py"]),
    ({}, ["scripts/rpi_2025.py"]),
    ({}, ["scripts/rating_2025.py"]),
    ({}, ["scripts/predict_2026.py"]),
    ({}, ["scripts/simulate_season_2026.py"]),
    ({}, ["scripts/score_predictions.py"]),
    ({}, ["scripts/project_lineups.py"]),
    ({}, ["scripts/conference_repair.py"]),
    ({}, ["scripts/digby_top25.py"]),
    ({}, ["scripts/resume_2025.py"]),
    ({}, ["scripts/confidence.py"]),
    ({}, ["scripts/availability_desk.py"]),
    ({}, ["scripts/source_intel.py"]),
    ({}, ["scripts/collector.py", "--recheck-reviews"]),
    ({}, ["scripts/provenance.py", "--check"]),
    ({}, ["scripts/build_hub.py"]),
]

# Steps that MUST succeed for the cycle to continue. Everything else is
# tolerated exactly as CI tolerates it ("|| echo ... skipping").
HARD = {"scripts/crawl_2025.py", "scripts/build_dataset.py",
        "scripts/build_hub.py"}


def _run(args, env_extra=None, season="2026"):
    env = dict(os.environ)
    env.setdefault("WVB_SEASON", season)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([PY] + [os.path.join(REPO, a) if a.endswith(".py")
                               else a for a in args],
                       cwd=REPO, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def fingerprint():
    code, out = _run(["scripts/freshness.py"])
    return out.strip() if code == 0 else None


def cycle(force=False):
    # The freshness semantics are what make a frequent poll safe -- same
    # gate, same position as CI: before any network call.
    code, out = _run(["scripts/test_crawl_freshness.py"])
    if code != 0:
        print("freshness regression test FAILED -- refusing to crawl")
        print(out[-2000:])
        return 1

    before = fingerprint()
    for args in CRAWL:
        code, out = _run(args)
        if code != 0 and args[0] in HARD:
            print("crawl step failed: %s" % " ".join(args))
            print(out[-2000:])
            return 1
    after = fingerprint()

    if not force and before is not None and after == before:
        print("no new final since the last cycle -- nothing to rebuild")
        return 0

    print("new final(s) landed -- rebuilding (%s -> %s)" % (before, after))
    for env_extra, args in REBUILD:
        code, out = _run(args, env_extra=env_extra)
        if code != 0:
            if args[0] in HARD:
                print("rebuild step failed: %s" % " ".join(args))
                print(out[-2000:])
                return 1
            print("  %s skipped (as CI tolerates)" % args[0])
    print("local page rebuilt -- rankings now include the new finals")
    return 0


def main():
    force = "--force" in sys.argv
    loop = "--loop" in sys.argv
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    fh = open(LOCK, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another local refresh is already running -- exiting")
        return 0
    try:
        if not loop:
            return cycle(force=force)
        while True:
            t0 = time.time()
            try:
                cycle(force=force)
            except Exception as exc:               # never let the loop die
                print("cycle error: %s" % exc)
            force = False
            wait = max(60, LOOP_SECONDS - int(time.time() - t0))
            print("next check in %d min" % (wait // 60))
            time.sleep(wait)
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


if __name__ == "__main__":
    sys.exit(main())
