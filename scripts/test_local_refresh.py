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
