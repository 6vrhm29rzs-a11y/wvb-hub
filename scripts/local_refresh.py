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
import json
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
    # POLLS LOCALLY TOO (2026-09-25). Only the nightly job fetched them, and
    # with every nightly failing since 09-19 the page showed the Sep 14 AVCA
    # poll beside every team for a week. Both append only when the poll moves.
    ["scripts/crawl_polls.py"],
    ["scripts/crawl_avca_rv.py"],
]

# ⚠ MIRRORS refresh.yml -- "Rebuild derived outputs" step, minus --public
# (publishing is CI's job; the local page is Cody/START-HERE.html).
# The 2025 base is kept even though it exists locally: one sequence, one
# definition (R4), and it measures at ~20s.
REBUILD = [
    # THE TRUST CUTOFF's intraday half (2026-09-04): verify today's new
    # finals against school sites BEFORE the rating rebuilds, so a
    # verified final enters POWER this cycle and an unverified feed claim
    # does not. Incremental: already-settled verdicts are not re-fetched.
    ({}, ["scripts/verify_results_daily.py", "--incremental"]),
    ({"WVB_SEASON": "2025"}, ["scripts/build_dataset.py"]),
    ({"WVB_SEASON": "2025"}, ["scripts/rpi_2025.py"]),
    ({"WVB_SEASON": "2025"}, ["scripts/rating_2025.py"]),
    # LOCAL-ONLY (Cody 2026-09-28, "Fix the venue file"): refresh the school-declared
    # site ledger from the verification reports before venues.py applies it. CI uses
    # the committed ledger as-is.
    ({}, ["scripts/venue_site_evidence.py"]),
    ({}, ["scripts/venues.py"]),
    ({}, ["scripts/availability.py"]),
    # ranks what availability.py merely flags: 750 undifferentiated
    # team-match flags are not a thing anyone can read.
    ({}, ["scripts/participation_radar.py"]),
    # the two outside-source legs: does the school agree about when a
    # match starts, and do its own words say anything about the
    # players the box scores flagged.
    ({}, ["scripts/fixture_time_check.py", "--days", "4"]),
    # ⚠ LOCAL-ONLY: broadcast listings from each school's own schedule page
    # (Cody, 2026-09-26: TV/streaming "listed for every match and noted if
    # none were found", and "tv changes" so re-read about daily). Each
    # school is refetched once its entry is 20h old, at most 40 per cycle,
    # so the ~377 schools roll over in a few hours instead of one long stall.
    ({}, ["scripts/crawl_tv.py", "--limit=40"]),
    ({}, ["scripts/availability_scan.py"]),
    ({}, ["scripts/build_dataset.py"]),
    ({}, ["scripts/rpi_2025.py"]),
    ({}, ["scripts/rating_2025.py"]),
    # the blend first -- forecasts and the simulator stand on it
    ({}, ["scripts/conference_repair.py"]),
    ({}, ["scripts/digby_top25.py"]),
    # ⚠ LOCAL-ONLY, PRIVATE (Cody, 2026-09-27): refreeze the season-only POWER
    # comparison candidate at Current POWER's exact cut-off. Not HARD: a
    # failure leaves the previous frozen file, whose own cut-off the page shows.
    ({}, ["scripts/season_only_candidate.py"]),
    # ⚠ LOCAL-ONLY, PRIVATE (Cody, 2026-09-28): prospective scorecard -- logs both
    # models' pre-match win chances once, scores them when final. Not HARD.
    ({}, ["scripts/season_only_scorecard.py"]),
    ({}, ["scripts/predict_2026.py"]),
    ({}, ["scripts/simulate_season_2026.py"]),
    ({}, ["scripts/score_predictions.py"]),
    ({}, ["scripts/project_lineups.py"]),
    ({}, ["scripts/resume_2025.py"]),
    ({}, ["scripts/certify_rankings.py"]),
    ({}, ["scripts/confidence.py"]),
    ({}, ["scripts/availability_desk.py"]),
    ({}, ["scripts/source_intel.py"]),
    ({}, ["scripts/collector.py", "--recheck-reviews"]),
    ({}, ["scripts/provenance.py", "--check"]),
    # ⚠ PLAYER RATINGS, REBUILT BEFORE THE PAGE (mail 055). The crawl step
    # re-aggregates player lines every cycle, but ratings were only rebuilt
    # by the daily CI job -- so the local page could carry ratings older than
    # the aggregate it shows beside them. HARD: if it fails the cycle stops
    # before build_hub, the previous page stays up, and the failure is
    # recorded -- never a fresh-looking page with silently stale ratings.
    ({}, ["scripts/player_rating.py"]),
    ({}, ["scripts/build_hub.py"]),
    # ⚠ LOCAL-ONLY: Cody's Center Court dashboard (2026-09-24). Writes into
    # the gitignored Cody/ tree and reads only artifacts rebuilt above, so it
    # runs right after the hub and never in CI.
    ({}, ["scripts/build_dashboard.py"]),
    # --- reference checks: read-only, local-only, never gate the build ---
    ({}, ["scripts/ingest_monsterblock.py"]),
    ({}, ["scripts/board_bakeoff.py"]),
    # ⚠ LOCAL-ONLY AND IT HAS TO BE. This snapshots the files git is
    # DELIBERATELY not carrying -- Cody's notes log, his ballots, the manual
    # browser captures -- and CI checks out a tree with none of them. It is
    # last because the notes log may have been written to earlier in the same
    # cycle, and --if-stale means it lands about daily rather than every 20
    # minutes churning through its own retention window.
    ({}, ["scripts/backup_local.py", "--if-stale"]),
]

# Steps that MUST succeed for the cycle to continue. Everything else is
# tolerated exactly as CI tolerates it ("|| echo ... skipping").
HARD = {"scripts/crawl_2025.py", "scripts/build_dataset.py",
        "scripts/player_rating.py", "scripts/build_hub.py"}


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


STATUS_DIR = os.path.join(REPO, "Cody", "data")
REFRESH_LOG = os.path.join(STATUS_DIR, "refresh_log.jsonl")
REFRESH_STATUS = os.path.join(STATUS_DIR, "refresh_status.json")


def _record(outcome, **kw):
    """DURABLE CYCLE OUTCOME (mail 037). live_server discards this script's
    stdout, so until now a failed crawl, a failed rebuild and a quiet 'no new
    final' were indistinguishable from outside. Every cycle -- and a cycle
    refused by the lock -- leaves one line here and overwrites the status
    file the live API reports. Private (Cody/ is gitignored); CI checkouts
    have no Cody/ and simply skip it."""
    if not os.path.isdir(STATUS_DIR):
        return
    rec = {"at_epoch": int(time.time()),
           "at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
           "outcome": outcome}
    rec.update(kw)
    try:
        with open(REFRESH_LOG, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        prev = {}
        if os.path.exists(REFRESH_STATUS):
            try:
                prev = json.load(open(REFRESH_STATUS))
            except ValueError:
                prev = {}
        prev["last"] = rec
        if outcome in ("rebuilt", "no_new_final"):
            prev["last_ok"] = rec
        if outcome == "rebuilt":
            prev["last_rebuilt"] = rec
        tmp = REFRESH_STATUS + ".tmp"
        json.dump(prev, open(tmp, "w"), indent=1)
        os.replace(tmp, REFRESH_STATUS)
    except OSError:
        pass


def cycle(force=False):
    t0 = time.time()
    try:
        return _cycle(force, t0)
    except Exception as exc:
        _record("error", detail=repr(exc)[:300], seconds=round(time.time() - t0))
        raise


def _cycle(force, t0):
    # The freshness semantics are what make a frequent poll safe -- same
    # gate, same position as CI: before any network call.
    code, out = _run(["scripts/test_crawl_freshness.py"])
    if code != 0:
        print("freshness regression test FAILED -- refusing to crawl")
        print(out[-2000:])
        _record("freshness_test_failed", detail=out[-600:])
        return 1

    before = fingerprint()
    for args in CRAWL:
        code, out = _run(args)
        if code != 0 and args[0] in HARD:
            print("crawl step failed: %s" % " ".join(args))
            print(out[-2000:])
            _record("crawl_failed", step=" ".join(args), detail=out[-600:],
                    seconds=round(time.time() - t0))
            return 1
    after = fingerprint()

    if not force and before is not None and after == before:
        print("no new final since the last cycle -- nothing to rebuild")
        _record("no_new_final", fingerprint=after, seconds=round(time.time() - t0))
        return 0

    print("new final(s) landed -- rebuilding (%s -> %s)" % (before, after))
    for env_extra, args in REBUILD:
        code, out = _run(args, env_extra=env_extra)
        if code != 0:
            if args[0] in HARD:
                print("rebuild step failed: %s" % " ".join(args))
                print(out[-2000:])
                _record("rebuild_failed", step=" ".join(args), detail=out[-600:],
                        seconds=round(time.time() - t0))
                return 1
            print("  %s skipped (as CI tolerates)" % args[0])
    print("local page rebuilt -- rankings now include the new finals")
    _record("rebuilt", fingerprint=after, forced=bool(force),
            seconds=round(time.time() - t0))
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
        _record("skipped_locked")
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
