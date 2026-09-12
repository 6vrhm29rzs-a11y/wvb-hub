#!/usr/bin/env python3
"""Guards for the parallel school-site sweep (2026-09-11).

WHY THIS EXISTS. verify_results_daily was 651.6s of an 860s rebuild in CI --
76% of it, and the reason the half-hourly refresh started hitting its own
25-minute bound. It is pure I/O wait, so the sweep now runs schools
concurrently. The whole safety of that rests on ONE property: a given
athletics site must still see our requests strictly one at a time. These
guards assert the property, not the shape of the fix -- they drive the real
gather_evidence() with a stubbed transport and watch what the transport sees.
"""
import os
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import verify_results_daily as V  # noqa: E402

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


# ── a stubbed transport that records exactly when each host was in flight ──
FETCH_DELAY = 0.04


class Recorder(object):
    def __init__(self):
        self.spans = []          # (host, t_enter, t_exit)
        self.lock = threading.Lock()

    def fetch(self, url, timeout=20):
        host = url.split("/")[2]
        t0 = time.time()
        time.sleep(FETCH_DELAY)
        t1 = time.time()
        with self.lock:
            self.spans.append((host, t0, t1))
        # never parseable -> every school walks the FULL ladder, which is the
        # expensive case the change is aimed at
        return 404, "", url

    def overlaps(self):
        """Pairs of requests to ONE host whose in-flight windows intersect."""
        bad = []
        by = {}
        for h, a, b in self.spans:
            by.setdefault(h, []).append((a, b))
        for h, iv in by.items():
            iv.sort()
            for i in range(1, len(iv)):
                if iv[i][0] < iv[i - 1][1] - 1e-6:
                    bad.append((h, iv[i - 1], iv[i]))
        return bad


class FastTime(object):
    """Keeps the politeness spacing real but scaled, so the guard is quick."""
    def sleep(self, s):
        time.sleep(s * 0.02)


def finals(n, dupe_host=False):
    out = []
    for i in range(n):
        w, l = "W%d" % i, "L%d" % i
        if dupe_host and i == 1:
            w = "W0"          # same school, second match of a doubleheader
        out.append({"gid": "g%d" % i, "winner": w, "loser": l,
                    "w_sets": 3, "l_sets": 1})
    return out


def sites_for(fs):
    s = {}
    for f in fs:
        for t in (f["winner"], f["loser"]):
            s[t] = "https://%s.example.com" % t.lower()
    return s


def run(fs, workers, patch_lock=None):
    rec = Recorder()
    old_fetch, old_time = V._fetch, V.time
    old_lock = V._host_lock
    V._fetch, V.time = rec.fetch, FastTime()
    if patch_lock is not None:
        V._host_lock = patch_lock
    V._HOST_LOCKS.clear()
    try:
        t0 = time.time()
        done, logs = V.gather_evidence(fs, sites_for(fs), "2026-09-11",
                                       workers=workers)
        return done, logs, time.time() - t0, rec
    finally:
        V._fetch, V.time, V._host_lock = old_fetch, old_time, old_lock


def main():
    print("1. THE PARALLEL SWEEP AGREES WITH A SERIAL ONE")
    fs = finals(6)
    d1, l1, t1, _ = run(fs, 1)
    d8, l8, t8, _ = run(fs, 8)
    check("same verdict for every (final, school)", d1 == d8,
          "serial %r vs parallel %r" % (sorted(d1), sorted(d8)))
    check("same fetch-log content, in the same order",
          [[e["url"] for e in l1[k]] for k in sorted(l1)] ==
          [[e["url"] for e in l8[k]] for k in sorted(l8)])
    check("every (final, school) slot is filled",
          sorted(d8) == [(i, s) for i in range(len(fs)) for s in (0, 1)])

    print("\n2. IT IS ACTUALLY FASTER (the whole point)")
    check("parallel beats serial on wall clock",
          t8 < t1 * 0.6, "serial %.2fs vs parallel %.2fs" % (t1, t8))
    print("     serial %.2fs -> parallel %.2fs  (%.1fx)" % (t1, t8, t1 / t8))

    print("\n3. ONE HOST NEVER SEES TWO REQUESTS AT ONCE")
    # a doubleheader puts the SAME school in two tasks -- the only way two
    # workers can contend for one host, and the case the lock exists for
    fs2 = finals(6, dupe_host=True)
    _d, _l, _t, rec = run(fs2, 8)
    ov = rec.overlaps()
    check("no overlapping in-flight requests to any host", not ov,
          "%d overlapping pair(s): %r" % (len(ov), ov[:2]))
    check("the doubleheader really did share a host",
          sum(1 for h, _a, _b in rec.spans
              if h == "w0.example.com") > len(V.SPORT_PATHS),
          "shared-host traffic not exercised -- the check above is vacuous")

    print("\n4. NEGATIVE CONTROLS")
    import contextlib

    @contextlib.contextmanager
    def _nolock(_url):
        yield                      # the bug: no per-host serialisation

    _d, _l, _t, rec_bad = run(fs2, 8, patch_lock=_nolock)
    check("[NEG] removing the host lock is CAUGHT by the overlap check",
          bool(rec_bad.overlaps()),
          "no overlap detected even with the lock removed -- the check in "
          "section 3 cannot fail and is proving nothing")

    shuffled = dict(d8)
    k0, k1 = (0, 0), (1, 0)
    shuffled[k0], shuffled[k1] = shuffled[k1], shuffled[k0]
    check("[NEG] mis-ordered reassembly is CAUGHT by the equality check",
          shuffled != d1 or d8[k0] == d8[k1])

    print("\n5. THE LAZY COUNTER CACHE IS BUILT ONCE, NOT ONCE PER THREAD")
    # _stripped_hub_count memoises a COUNT per stripped team key. Built
    # concurrently without a lock, two threads each increment the same shared
    # dict and every count comes out DOUBLE -- and its consumer refuses a
    # name match when a count is > 1, so the damage is silently refused
    # matches, only under concurrency.
    def counts_after(n_threads, build):
        V._STRIPPED_HUB.clear()
        errs = []

        def go():
            try:
                build("anything")
            except Exception as e:            # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=go) for _ in range(n_threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        return dict(V._STRIPPED_HUB), errs

    serial, _e = counts_after(1, V._stripped_hub_count)
    conc, _e2 = counts_after(16, V._stripped_hub_count)
    check("concurrent build gives the same counts as a serial one",
          conc == serial and bool(serial),
          "serial keys %d / concurrent keys %d; %d differ"
          % (len(serial), len(conc),
             sum(1 for k in set(serial) | set(conc)
                 if serial.get(k) != conc.get(k))))
    check("no count exceeds its serial value (no double-increment)",
          all(conc.get(k, 0) <= serial.get(k, 0) for k in conc))

    # [NEG] the pre-fix build: no lock, increments straight into the global
    def unlocked(key):
        if not V._STRIPPED_HUB:
            try:
                d = __import__("json").load(open(os.path.join(
                    REPO, "data", "data_%d.json" % V.SEASON)))
                for t in d.get("teams") or []:
                    k = V._strip_inst(V.team_norm(t.get("name_short") or ""))
                    time.sleep(0)          # widen the window, no new logic
                    V._STRIPPED_HUB[k] = V._STRIPPED_HUB.get(k, 0) + 1
            except (OSError, ValueError):
                return 2
        return V._STRIPPED_HUB.get(key, 0)

    if serial:
        bad, _e3 = counts_after(16, unlocked)
        check("[NEG] the unlocked build IS caught (counts inflate)",
              bad != serial,
              "unlocked build produced identical counts -- the check above "
              "cannot fail and is proving nothing")
    else:
        check("[NEG] unlocked-build control", False,
              "data_%d.json unreadable, so the cache is empty and neither "
              "the check nor its control means anything" % V.SEASON)

    V._STRIPPED_HUB.clear()

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL PARALLEL-VERIFIER GUARDS PASS")


if __name__ == "__main__":
    main()
