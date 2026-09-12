#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard wrapper: no box may sit attributed to the wrong team unhandled.

The work is in box_attribution_sweep.py, which is also useful to run by hand.
This exists so run_all_guards discovers it -- the sweep found three whole-match
inversions the first time it ran, one of which (Manhattan-Holy Cross) NO
result check could see, because the feed's line was internally coherent and
only the player rows gave it away.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
r = subprocess.call([sys.executable,
                     os.path.join(REPO, "scripts", "box_attribution_sweep.py")])
print("\n%s" % ("BOX ATTRIBUTION HOLDS" if r == 0 else "FAILED"))
sys.exit(r)
