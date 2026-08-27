#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BEFORE SHIPPING: one command, one verdict.

⚠ THE VERIFICATION WAS ALWAYS THERE; WHAT WAS MISSING WAS A SINGLE DOOR. Every
phase in this project has ended with the same sequence -- run the suites, build
both pages, check the public gate, run the fresh-checkout guard -- typed out by
hand each time. A sequence held together by memory is a sequence that gets
shortened on the night it matters, and it also means "green" is a claim rather
than an artefact.

⚠ IT DISCOVERS THE SUITES RATHER THAN LISTING THEM. A hard-coded list would
pass on the day someone adds test_something.py and forgets to add it here --
the failure mode is silence, which is the one this file exists to remove.

Run: python3 scripts/preflight.py [--quick]
  --quick  skip the fresh-checkout guard (minutes, and it materialises a tree)
Exit 0 = safe to commit.
"""

import glob
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOW = ("test_pipeline_fresh_checkout.py",)


def run(cmd, label):
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=REPO, shell=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.communicate()[0].decode("utf-8", "replace")
    dt = time.time() - t0
    ok = p.returncode == 0
    print("  %-52s %s  %4.1fs" % (label, "ok  " if ok else "FAIL", dt))
    return ok, out


def main():
    quick = "--quick" in sys.argv
    print("PREFLIGHT -- everything that must be true before shipping\n")
    failures = []

    # 1. every suite, discovered
    suites = sorted(os.path.basename(p) for p in
                    glob.glob(os.path.join(REPO, "scripts", "test_*.py")))
    print("1. TEST SUITES (%d discovered)" % len(suites))
    for s in suites:
        if quick and s in SLOW:
            print("  %-52s skipped (--quick)" % s)
            continue
        ok, out = run("python3 scripts/%s" % s, s)
        if not ok:
            failures.append((s, out))

    # 2. both builds
    print("\n2. BUILDS")
    for cmd, label in (("python3 scripts/build_hub.py", "private build"),
                       ("python3 scripts/build_hub.py --public",
                        "public build (aborts if a marker survives)")):
        ok, out = run(cmd, label)
        if not ok:
            failures.append((label, out))

    # 3. the public gate, on the VALUES not the words
    print("\n3. PUBLIC GATE (values, not words)")
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if not os.path.exists(pub):
        failures.append(("public artefact missing", ""))
        print("  %-52s FAIL" % "the published artefact exists")
    else:
        h = open(pub, encoding="utf-8").read()
        import re
        probes = ["VolleyTalk", "Massey Ratings", 'data-v="tv"', "askform",
                  "/api/digby", "intelbody", "in-media", "IN_MEDIA_HOSTS",
                  "_flysystem", "bwlist", "fr-new"]
        leaks = [p for p in probes if p in h]
        media = [u for u in re.findall(r'<img[^>]+src="(https?://[^"]+)"', h)
                 if "/_flysystem/" in u]
        ok = not leaks and not media
        print("  %-52s %s  %s" % ("no private marker or media URL in the build",
                                  "ok  " if ok else "FAIL",
                                  "" if ok else str(leaks + media[:1])))
        if not ok:
            failures.append(("public gate", str(leaks + media[:1])))
        # ⚠ POSITIVE CONTROL: a truncated or empty artefact passes every
        # absence check above for entirely the wrong reason.
        big = len(h) > 500000
        print("  %-52s %s" % ("[+] ...over a full-size page (%d KB)"
                              % (len(h) / 1024), "ok  " if big else "FAIL"))
        if not big:
            failures.append(("public artefact suspiciously small", str(len(h))))

    print()
    if failures:
        print("PREFLIGHT FAILED -- %d problem(s). DO NOT SHIP.\n" % len(failures))
        for name, out in failures:
            print("  === %s ===" % name)
            for line in [l for l in out.splitlines()
                         if l.strip().startswith("- ") or "FAIL" in l][:6]:
                print("     %s" % line.strip())
        return 1
    print("PREFLIGHT CLEAN -- safe to commit.")
    print("After pushing, run:  python3 scripts/verify_shipped.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
