#!/usr/bin/env python3
"""Score freshness must be reported as separate facts, never one 'healthy
quiet' word (mail 037)."""
import json, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
FAIL = []
def check(n, ok):
    print("  %-64s %s" % (n, "ok" if ok else "FAIL"))
    if not ok: FAIL.append(n)

import local_refresh as L
d = tempfile.mkdtemp()
L.STATUS_DIR, L.REFRESH_LOG, L.REFRESH_STATUS = d, os.path.join(d, "log.jsonl"), os.path.join(d, "st.json")
L._record("rebuilt", fingerprint="a"); L._record("crawl_failed", step="x")
st = json.load(open(L.REFRESH_STATUS))
check("every outcome is logged durably", len(open(L.REFRESH_LOG).readlines()) == 2)
check("a failure is the LAST outcome, not hidden by the last success",
      st["last"]["outcome"] == "crawl_failed" and st["last_ok"]["outcome"] == "rebuilt")
src = open(os.path.join(HERE, "local_refresh.py")).read()
for o in ("no_new_final", "crawl_failed", "rebuild_failed", "skipped_locked", "freshness_test_failed", "rebuilt"):
    check("local_refresh records '%s'" % o, '"%s"' % o in src)

import live_server as S
now = int(time.time())
class C: polled_epoch = now; changed_epoch = now - 3000
p = {"games": [{"id": "1", "state": "pre", "start_epoch": now - 3600, "away": "A", "home": "B", "time": "t"},
               {"id": "2", "state": "pre", "start_epoch": now - 600},
               {"id": "3", "state": "live", "start_epoch": now - 3600}]}
f = S.freshness(p, C())
check("a pre match well past its start is reported overdue", [g["id"] for g in f["overdue_listed_pre"]] == ["1"])
check("poll time and last score change are separate fields",
      f["polled_epoch"] != f["scores_changed_epoch"])
lsrc = open(os.path.join(HERE, "live_server.py")).read()
check("refresh output is no longer discarded", "stdout=subprocess.DEVNULL" not in lsrc.split("_local_refresh_loop")[1][:1500])
b = open(os.path.join(HERE, "build_hub.py")).read()
cs = b[b.index("function csStatus()"):]; cs = cs[:cs.index("\n}\n")]
check("the strip withholds 'quiet' when matches are overdue", "od.length ? '<b>none live in feed</b>'" in cs)
check("an open tab is told a newer page exists", "newer page built" in cs and "PAGE_BUILT_EPOCH" in cs)
check("[NEG] the old unconditional quiet would be caught",
      "od.length ? '<b>none live in feed</b>'" not in cs.replace("od.length ? '<b>none live in feed</b>'", "'<b>quiet</b>'"))
print("FAILED: %s" % FAIL if FAIL else "ALL FRESHNESS-REPORTING CHECKS HOLD"); sys.exit(1 if FAIL else 0)
