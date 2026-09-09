#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The local refresh must stay in step with the CI refresh.

WHY. local_refresh.py exists because the page Cody reads is the LOCAL build,
and its rankings were frozen while CI happily rebuilt a page nobody was
looking at. The failure mode that recreates the gap is silent drift: a script
added to refresh.yml's rebuild list and not to the local twin. So the guard
does not trust either list -- it parses the workflow file and compares.

Run: python3 scripts/test_local_refresh.py
No network. Exits non-zero on violation.
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def bad(what, detail):
    FAILS.append("%s: %s" % (what, detail))


def ok(msg):
    print("  %-58s ok" % msg)


def workflow_scripts():
    """Every scripts/*.py the CI refresh invokes in its crawl+rebuild steps."""
    y = open(os.path.join(REPO, ".github", "workflows", "refresh.yml"),
             encoding="utf-8").read()
    names = []
    for m in re.finditer(r"python3 (scripts/[a-z_0-9]+\.py)", y):
        names.append(m.group(1))
    return names


def local_scripts(text=None):
    src = text if text is not None else open(
        os.path.join(REPO, "scripts", "local_refresh.py"),
        encoding="utf-8").read()
    return re.findall(r'"(scripts/[a-z_0-9]+\.py)"', src)


def check_in_step(local_text=None):
    ci = workflow_scripts()
    local = set(local_scripts(local_text))
    # CI-only by design: the guard-runner (the local cycle does not gate its
    # own publish on the full suite -- there is no publish), the public build
    # flag is an argument not a script, and freshness.py/test_crawl_freshness
    # are in BOTH by construction.
    ci_only_ok = {"scripts/run_all_guards.py"}
    missing = [s for s in ci if s not in local and s not in ci_only_ok]
    if missing:
        bad("local refresh drifted from refresh.yml",
            "CI runs %s but local_refresh.py does not -- the local page "
            "would rebuild without them" % ", ".join(sorted(set(missing))))
    else:
        ok("every CI crawl/rebuild script is in the local cycle")


def check_negative_control():
    """Remove one CI script from a COPY of the local list; the guard must trip."""
    src = open(os.path.join(REPO, "scripts", "local_refresh.py"),
               encoding="utf-8").read()
    bogus = src.replace('"scripts/digby_top25.py"', '"scripts/removed.py"')
    if bogus == src:
        bad("negative control setup", "digby_top25 not found in local list")
        return
    before = len(FAILS)
    check_in_step(local_text=bogus)
    if len(FAILS) == before:
        bad("negative control", "removing digby_top25.py from the local "
            "cycle did not trip the drift check -- the guard cannot fail")
    else:
        del FAILS[before:]
        ok("negative control: a dropped script is caught")


def check_lock_is_used():
    src = open(os.path.join(REPO, "scripts", "local_refresh.py"),
               encoding="utf-8").read()
    if "LOCK_EX | fcntl.LOCK_NB" not in src:
        bad("no non-blocking lock",
            "local_refresh.py must flock non-blocking so a manual pipeline "
            "run and the server loop cannot interleave crawls")
    else:
        ok("non-blocking flock guards against overlapping cycles")


def check_verifier_precedes_ratings():
    """In EVERY workflow that runs both, verification precedes the ratings.

    ⚠ Paid for 2026-09-07: daily.yml ran verify_results_daily AFTER
    rating_2025 and digby_top25, so finals verified mid-run grew the
    rating-eligible set (rating_input_ok) after digby's artifact was built,
    and the audit-manifest gate refused the build (932 counted vs 934
    eligible). refresh.yml and local_refresh had the right order; the daily
    job was the unmirrored copy. This asserts the ORDER, not a literal, in
    every workflow file plus local_refresh's own sequence.
    """
    import glob
    for wf in sorted(glob.glob(os.path.join(REPO, ".github/workflows/*.yml"))):
        text = open(wf, encoding="utf-8").read()
        # only lines that RUN the scripts, not comments naming them
        runs = [ln for ln in text.splitlines()
                if ln.strip().startswith("python3 scripts/")]
        def first(name):
            for i, ln in enumerate(runs):
                if name in ln:
                    return i
            return None
        v = first("verify_results_daily.py")
        for rated in ("rating_2025.py", "digby_top25.py"):
            r = first(rated)
            if v is not None and r is not None and v > r:
                bad("verifier order", "%s runs verify_results_daily AFTER %s"
                    % (os.path.basename(wf), rated))
    # local_refresh's own sequence
    # ⚠ the first version referenced a SEQUENCE attribute that does not
    # exist; the hasattr guard made the whole arm silently skip
    # (ultrareview 2026-09-08). The real constant is REBUILD -- (env, cmd)
    # tuples -- and the verifier lives there. CRAWL entries are bare lists
    # and never run the verifier, so they are not part of this order.
    _lr = __import__("local_refresh")
    seq = [" ".join(c) for _, c in _lr.REBUILD]
    if seq:
        vi = next((i for i, c in enumerate(seq)
                   if "verify_results_daily" in c), None)
        ri = next((i for i, c in enumerate(seq)
                   if "rating_2025" in c or "digby_top25" in c), None)
        if vi is not None and ri is not None and vi > ri:
            bad("verifier order", "local_refresh verifies after the rating")
    # NEGATIVE CONTROL: a reversed order must be caught by the same logic
    _runs = ["python3 scripts/rating_2025.py",
             "python3 scripts/verify_results_daily.py"]
    _v = next(i for i, ln in enumerate(_runs) if "verify_results" in ln)
    _r = next(i for i, ln in enumerate(_runs) if "rating_2025" in ln)
    if not (_v > _r):
        bad("verifier order", "negative control cannot trip -- guard is dead")
    ok("verification precedes the rating chain in every workflow")


def check_stamp_reaches_the_page():
    """The ranking's own recompute stamp must render, from artifact meta.

    A page build time is NOT the answer -- a rebuild without a recompute keeps
    old ranks under a fresh clock. So the page must carry the rkstamp span,
    and digby_top25.py must write the generated_at_utc it reads.
    """
    dg = open(os.path.join(REPO, "scripts", "digby_top25.py"),
              encoding="utf-8").read()
    if '"generated_at_utc"' not in dg:
        bad("digby_top25 has no run stamp",
            "meta.generated_at_utc missing -- the page cannot say when the "
            "ranking was last recomputed")
    else:
        ok("digby_top25 stamps generated_at_utc")
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping page-stamp check")
        return
    page = open(hub, encoding="utf-8").read()
    if 'class="rkstamp"' not in page or "Recomputed" not in page:
        bad("recompute stamp not on the page",
            "no rkstamp span -- the rankings do not say when they were "
            "last recomputed")
    else:
        ok("the page states when the rankings were last recomputed")


def main():
    print("local refresh invariants")
    check_in_step()
    check_negative_control()
    check_lock_is_used()
    check_verifier_precedes_ratings()
    check_stamp_reaches_the_page()
    if FAILS:
        print("\nFAILED:")
        for f in FAILS:
            print("  " + f)
        return 1
    print("all local-refresh checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
