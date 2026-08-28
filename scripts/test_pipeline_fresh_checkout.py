#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard: the daily pipeline must complete from a FRESH CHECKOUT.

WHY THIS EXISTS. Twice in one day the nightly run broke the same way, and the
shape is worth naming: a script is season-parameterised, the job pins
WVB_SEASON=2026, and so CI quietly stops building a **2025** artifact that a
later step hard-requires. Both artifacts are gitignored build outputs -- pure
functions of the committed raw -- so they exist on the laptop and never in CI.
Everything looks fine locally and the nightly run is the only thing that sees
the fault.

  data_2025.json    test_projection re-derives ROTATION=6 from it. Missing ->
                    the guard hard-failed on its own input and the run went red.
  rating_2025.json  build_rankings_board.build() requires it as the BASE
                    (rating_2026.json is the optional live overlay, and is
                    correctly absent until 50 matches are played). Missing ->
                    build_hub.py exits 1.

The second was INVISIBLE for its whole life because build_hub ran as
`build_hub.py --public || echo ...`. A `|| echo` is a declaration that a command
is allowed to fail; putting one on a command that is actually required converts
a hard failure into a log line nobody reads. That is the real lesson here, and
it is what this test encodes.

WHAT IT ASSERTS. The workflow's own command list is READ FROM daily.yml -- never
copied into this file. A guard that restates the thing it guards rots away from
it, which is exactly how the comment above the guards step came to claim
test_projection "skips itself on a fresh checkout" when only check 2 ever did.
Then, in a tree containing ONLY tracked files:

  every command the workflow does NOT tolerate failing must exit 0.

Commands carrying a `||` fallback are allowed to fail -- that is their declared
contract, and this test holds them to it rather than second-guessing it.

NEGATIVE CONTROL. A test that cannot fail is not a test. The control strips the
WVB_SEASON=2025 lines back out and asserts build_hub.py fails again. If it were
to pass without them, this file would be checking nothing.

Python 3.9 target. Run: python3 scripts/test_pipeline_fresh_checkout.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "daily.yml")

# The steps whose commands must survive a fresh checkout. Deliberately NOT the
# whole file: the crawl steps need the network, and the commit steps need CI
# credentials. These two are the offline heart of the run, and both bugs were
# here.
STEPS = ["Rebuild derived outputs", "Invariant guards"]

# ⚠ RECURSION. This file is itself listed in the "Invariant guards" step, so
# running that step verbatim would re-enter this test forever. Excluded by name.
SELF = os.path.basename(__file__)

# The network lives in the crawl steps, but crawl_polls.py is invoked from the
# rebuild step. A guard must not depend on a live host, so it is skipped -- and
# it carries a `|| echo` fallback, so the pipeline already declares it optional.
SKIP = re.compile(r"scripts/crawl_")

FAILURES = []


def check(label, ok, detail=""):
    print("  %-58s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILURES.append(label)


def workflow_env():
    # type: () -> str
    """The season the job pins. Read, not assumed -- it is half of the bug."""
    src = open(WORKFLOW).read()
    m = re.search(r"WVB_SEASON:\s*\$\{\{[^}]*?'(\d{4})'\s*\}\}", src)
    return m.group(1) if m else "2026"


def step_commands(step, workflow=None):
    # type: (str, str) -> list
    """The shell lines of one named step, in order, read from the workflow itself.

    ⚠ READ, NEVER RESTATED. If this file listed the commands, it would drift
    from the job it claims to verify and go on passing while the real pipeline
    broke.
    """
    lines = open(workflow or WORKFLOW).read().splitlines()
    out = []
    i = 0
    while i < len(lines) and lines[i].strip() != "- name: %s" % step:
        i += 1
    if i >= len(lines):
        return []
    while i < len(lines) and not lines[i].strip().startswith("run:"):
        i += 1
    if i >= len(lines):
        return []
    # ⚠ `run:` COMES IN TWO SHAPES AND THIS ONLY UNDERSTOOD ONE. A block
    # (`run: |`) puts the commands on following lines; an INLINE `run: cmd`
    # puts it right there. Reading only the block form, an inline step returned
    # NO commands and the guard reported the step as "renamed or restructured"
    # -- failing a workflow that was correct. Other steps in this file already
    # use the inline form.
    inline = lines[i].strip()[4:].strip()
    if inline and inline != "|" and not inline.startswith("|"):
        return [inline]
    i += 1
    for ln in lines[i:]:
        if ln.strip() and not ln.startswith("          "):
            break                                  # dedent ends the block
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(s)
    # ⚠ JOIN SHELL LINE CONTINUATIONS. A command split across lines with a
    # trailing backslash arrived here as two entries: the first looked like a
    # REQUIRED command (its `||` was on the next line) and, run alone, ended in
    # a dangling backslash and exited non-zero. So reformatting a workflow line
    # for readability failed this guard while changing nothing about the
    # pipeline -- a guard that objects to whitespace is a guard people learn to
    # ignore.
    joined = []
    for cmd in out:
        if joined and joined[-1].endswith("\\"):
            joined[-1] = joined[-1][:-1].rstrip() + " " + cmd
        else:
            joined.append(cmd)
    return joined


def materialise(dest):
    # type: (str) -> None
    """Tracked files only -- which is precisely what CI checks out.

    Everything gitignored (data_2025.json, rating_2025.json, the built page) is
    absent by construction. That absence IS the test.
    """
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO).split(b"\0")
    tar = subprocess.Popen(["tar", "-cf", "-", "-T", "-"], cwd=REPO,
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    tar.stdin.write(b"\n".join(n for n in names if n))
    tar.stdin.close()
    subprocess.check_call(["tar", "-xf", "-"], cwd=dest, stdin=tar.stdout)
    tar.wait()


def run_sequence(cmds, cwd, season, stop_on_required_failure=True):
    # type: (list, str, str, bool) -> list
    """Run the step's commands. Returns [(cmd, tolerated, rc)]."""
    env = dict(os.environ)
    env["WVB_SEASON"] = season
    env.pop("ANTHROPIC_API_KEY", None)      # never spend money from a guard
    results = []
    # ⚠ THE SELF-EXCLUSION USED TO WORK BY NAME, AND THE NAME MOVED. This
    # suite skips any workflow command that mentions it -- otherwise it runs
    # itself inside its own sandbox forever. The daily job now invokes the
    # guards through run_all_guards.py, so this file's name no longer appears
    # in any command and the cycle came back. The exclusion travels in the
    # environment instead, and the runner prints what it skipped.
    env = dict(env or os.environ)
    # ⚠ THE SANDBOX IS NARROWER THAN CI, AND THE EXCLUSIONS SAY SO. This test
    # runs only the workflow's "Rebuild derived outputs" and "Invariant guards"
    # steps; the real job also crawls and rebuilds the 2025 base, so two suites
    # assert on inputs that exist in CI and not here:
    #   test_player_rating     -- schedule-adjusted priors need the 2025
    #                             opponent graph (data/rating_2025.json), which
    #                             is gitignored and rebuilt by steps this
    #                             sandbox does not run. Measured here: 0 of
    #                             2,789 priors carried an opponent z.
    #   test_today_scoreboard  -- its TV assertions read
    #                             Cody/data/tv_listings_2026.txt, which lives
    #                             inside the gitignored private folder and is
    #                             not ours to publish. It cannot exist here.
    # Both still run in CI and in preflight, where their inputs are present.
    # They are excluded from THIS sandbox only, and the runner prints each skip
    # so an exclusion can never be silent.
    env["WVB_GUARD_EXCLUDE"] = ",".join(
        [SELF, "test_player_rating.py", "test_today_scoreboard.py"])
    for c in cmds:
        if SELF in c or SKIP.search(c):
            continue
        tolerated = "||" in c
        # ⚠ A GUARD THAT HIDES WHY IT FAILED COSTS MORE THAN IT SAVES. Output
        # is suppressed so the ordinary pass is quiet, but when a required
        # command fails the reason is exactly what you need and it was being
        # thrown away -- reproducing it by hand took several wrong attempts.
        # WVB_TEST_VERBOSE=1 lets it through.
        _verbose = os.environ.get("WVB_TEST_VERBOSE") == "1"
        if _verbose:
            print("       $ %s" % c)
        rc = subprocess.call(
            c, shell=True, cwd=cwd, env=env,
            stdout=(None if _verbose else subprocess.DEVNULL),
            stderr=(None if _verbose else subprocess.DEVNULL))
        results.append((c, tolerated, rc))
        if rc != 0 and not tolerated and stop_on_required_failure:
            break
    return results


REFRESH = os.path.join(REPO, ".github", "workflows", "refresh.yml")
REFRESH_STEPS = ["Rebuild derived outputs", "Invariant guards"]


def check_refresh_runs_from_a_fresh_checkout(season):
    # type: (str) -> None
    """The in-season refresh must work on a tree with only tracked files.

    ⚠ IT IS A DIFFERENT SEQUENCE FROM THE DAILY JOB and therefore needs its own
    pass. It deliberately omits the 2025 base build, on the reasoning that the
    completed season is committed and does not change in-season -- which is true
    of the DATA and was very nearly not true of the derived artifacts. Both of
    2026-08-23's nightly breakages were invisible on a laptop that already had
    the gitignored files; this is the check that would have caught them.
    """
    if not os.path.exists(REFRESH):
        print("  (no refresh workflow -- skipping)")
        return
    cmds = []
    for st in REFRESH_STEPS:
        cmds += step_commands(st, REFRESH)
    cmds = [c for c in cmds if SELF not in c and not SKIP.search(c)]
    tmp = tempfile.mkdtemp(prefix="wvb-refresh-")
    try:
        materialise(tmp)
        # ⚠ THE FIRST VERSION OF THIS TEST BUILT THE 2025 BASE HERE FIRST, AND
        # THAT IS WHY IT PASSED WHILE THE REAL JOB FAILED. I had written in
        # refresh.yml that "the 2025 base is committed and does not change
        # in-season" -- true of the RAW DATA and false of the derived artifacts,
        # which are gitignored and must be rebuilt on every checkout. CI starts
        # from a clean tree every run, so build_hub exited 1 with "no
        # data/rating_2025.json". A test that pre-supplies the missing input is
        # not testing the sequence, it is accommodating its bug.
        #
        # Nothing is pre-built now. The refresh workflow must stand on its own,
        # exactly as CI runs it.
        results = run_sequence(cmds, tmp, season)
        bad = [(c, rc) for c, tol, rc in results if rc != 0 and not tol]
        for c, rc in bad:
            print("       refresh command failed (rc=%d): %s" % (rc, c))
        check("the refresh sequence runs from a fresh checkout", not bad,
              "(%d failed)" % len(bad))
        check("the refresh built a page",
              os.path.exists(os.path.join(tmp, "Cody", "START-HERE.html")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("FRESH-CHECKOUT PIPELINE GUARD\n")
    season = workflow_env()

    print("1. The workflow is readable and still has the steps this guards")
    cmds = []
    for st in STEPS:
        c = step_commands(st)
        check("step %r found with commands" % st, bool(c),
              "(renamed or restructured? update STEPS)")
        cmds.extend(c)
    if FAILURES:
        return 1
    runnable = [c for c in cmds if SELF not in c and not SKIP.search(c)]
    print("     %d commands, %d runnable, WVB_SEASON=%s"
          % (len(cmds), len(runnable), season))

    tmp = tempfile.mkdtemp(prefix="wvb-fresh-")
    try:
        print("\n2. Every command the workflow does not tolerate failing succeeds")
        materialise(tmp)
        gone = [p for p in ("data/data_2025.json", "data/rating_2025.json")
                if not os.path.exists(os.path.join(tmp, p))]
        check("the derived artifacts really are absent to begin with",
              len(gone) == 2, "(found %s -- not a fresh checkout)" % (gone,))

        results = run_sequence(cmds, tmp, season)
        bad = [(c, rc) for c, tol, rc in results if rc != 0 and not tol]
        for c, rc in bad:
            print("       required command failed (rc=%d): %s" % (rc, c))
        check("no required command failed", not bad,
              "(%d failed)" % len(bad))

        # ⚠ TOLERATED IS NOT THE SAME AS EXPECTED, AND THIS GUARD USED TO TREAT
        # THEM ALIKE. simulate_season_2026.py carries a `||`, so when it exited
        # 1 on a fresh checkout -- because it reads data/rating_2025.json and
        # that was built LATER in the same step -- this test stayed green and
        # said nothing. A real nightly run then failed for a whole different
        # reason and only the log revealed it. A command allowed to fail is
        # still worth reporting; a nightly that quietly skips its season
        # simulation every night is not a nightly that runs.
        tolerated = [(c, rc) for c, tol, rc in results if rc != 0 and tol]
        if tolerated:
            print("     %d tolerated command(s) did not run -- allowed, but "
                  "look at them:" % len(tolerated))
            for c, rc in tolerated:
                print("       (rc=%d) %s" % (rc, c.split("||")[0].strip()))
        else:
            print("     every tolerated command also succeeded")
        check("the page was built", os.path.exists(os.path.join(tmp, "Cody", "START-HERE.html")))

        # ---- NEGATIVE CONTROL ------------------------------------------
        # Strip the base-season lines back out. build_hub.py must fail, or
        # this whole file is asserting nothing.
        print("\n3. Negative control: without the 2025 base, the run must break")
        shutil.rmtree(tmp)
        tmp = tempfile.mkdtemp(prefix="wvb-fresh-neg-")
        materialise(tmp)
        stripped = [c for c in cmds if "WVB_SEASON=2025" not in c]
        check("the control actually removed something",
              len(stripped) < len(cmds),
              "(no WVB_SEASON=2025 lines -- has the fix been reverted?)")
        neg = run_sequence(stripped, tmp, season)
        broke = [(c, rc) for c, tol, rc in neg if rc != 0 and not tol]
        check("a required command fails without the base", bool(broke),
              "(nothing failed -- this guard would not catch the bug)")
        if broke:
            print("       and it is the expected one: %s" % broke[0][0])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n4. The in-season refresh, also from a fresh checkout")
    check_refresh_runs_from_a_fresh_checkout(season)

    print("\n%s" % ("ALL CHECKS PASS, negative control tripped as expected"
                    if not FAILURES else "FAILED: %d check(s)" % len(FAILURES)))
    for f in FAILURES:
        print("   - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
