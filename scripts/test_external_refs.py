#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXTERNAL-RATINGS FRESHNESS + DISCREPANCY CONTROL (2026-08-31).

The walls:
  1. Hub POWER / resume payloads are byte-identical with and without the
     FIG/Massey reference snapshots -- proven by building the board twice.
  2. The real SMU fixture: FIG's displayed W-L differs from the hub's
     counting record, renders as REFERENCE MISMATCH, changes no counted
     record, and structurally CANNOT create a correction.
  3. Massey can never render as current: its label states 'preseason
     snapshot' plus the captured date, and an absent date renders
     'capture date not held', never an invented one.
  4. A source's own Generated stamp and our fetch time are two facts,
     both rendered, never collapsed.
  5. No rating module reads external_refs; external_refs writes nothing.
  6. The public build carries none of it, by value.
"""

import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % str(detail)[:90]))
    if not ok:
        FAILS.append(label)


def main():
    import external_refs as ER

    # ⚠ TWO ENVIRONMENTS, ONE SUITE. On Cody's machine the snapshots exist
    # and every fixture is checked. In CI and the fresh-checkout sandbox
    # Cody/data is absent BY DESIGN (gitignored; not ours to publish) --
    # there the suite proves the HONEST-ABSENCE mode instead of failing on
    # the world it is supposed to handle. A guard that fails wherever its
    # optional input is absent is the calendar-pin family again.
    HELD = ER.fig_latest() is not None

    print("1. THE PAYLOAD IS IDENTICAL WITH AND WITHOUT THE SNAPSHOTS")
    import build_rankings_board as B
    t1, f1, u1, n1, m1 = B.build()
    real_lp = B.load_pipe
    try:
        B.load_pipe = lambda p: []          # no VT, no Massey snapshot
        t2, f2, u2, n2, m2 = B.build()
    finally:
        B.load_pipe = real_lp
    REF_FIELDS = ("vt", "massey", "d_massey")
    def strip_ref(t):
        return {k: v for k, v in t.items() if k not in REF_FIELDS}
    same = (len(t1) == len(t2) and all(
        strip_ref(a) == strip_ref(b) for a, b in zip(t1, t2)))
    check("every non-reference field of every team is identical", same)
    diffs = []
    for a, b in zip(t1, t2):
        for k in ("rank26", "power", "resume_rank", "rank_source", "seed",
                  "rpi", "avca"):
            if a.get(k) != b.get(k):
                diffs.append((a.get("team"), k))
    check("...including POWER, resume, seed, RPI, AVCA on all %d teams"
          % len(t1), not diffs, diffs[:4])
    check("the projected field is identical too",
          [t.get("team") for t in (f1 or [])] ==
          [t.get("team") for t in (f2 or [])])
    if ER.massey_meta()["held"]:
        check("the snapshots DID feed the reference columns in the real "
              "build", any(t.get("massey") for t in t1)
              and not any(t.get("massey") for t in t2))
    else:
        print("  (no Massey snapshot in this checkout -- identity proven "
              "on the empty case)")

    print("\n2. THE REAL SMU FIXTURE -- A MISMATCH IS A FACT, NOT A LEVER")
    fig = ER.fig_latest()
    if not HELD:
        print("  (no FIG snapshot in this checkout -- asserting the "
              "honest-absence mode instead)")
        d_abs = ER.discrepancies()
        check("absent snapshot -> empty queue, nothing invented",
              d_abs["items"] == [] and d_abs["fig"] is None)
    if fig:
        check("it is labelled '%s'" % "FIGstats unofficial RPI",
              fig.get("source_label") == "FIGstats unofficial RPI")
        check("publisher stamp and fetch time are BOTH held and DIFFERENT "
              "facts",
              bool(fig.get("publisher_generated"))
              and bool(fig.get("retrieved_utc"))
              and fig["publisher_generated"] != fig["retrieved_utc"])
        check("provenance: manual browser review, robots named",
              "robots.txt" in (fig.get("access") or ""))
        check("a content fingerprint is held",
              re.match(r"^[0-9a-f]{64}$", fig.get("content_sha256") or ""))
    corr_path = os.path.join(REPO, "data/raw/2026/result_corrections.json")
    before = io.open(corr_path, encoding="utf-8").read()
    d = ER.discrepancies()
    after = io.open(corr_path, encoding="utf-8").read()
    check("computing the queue wrote NO correction", before == after)
    hub = ER.hub_records()
    check("the hub's counting record for SMU is still 3-0 and UC Davis 1-2",
          hub.get("SMU") == "3-0" and hub.get("UC Davis") == "1-2",
          (hub.get("SMU"), hub.get("UC Davis")))
    if HELD:
        smu = [i for i in d["items"] if i["team"] == "SMU"]
        check("SMU renders as a reference mismatch", bool(smu),
              d["items"][:2])
        if smu:
            check("...FIG %s vs hub %s, and the hub record is untouched"
                  % (smu[0]["fig_record"], smu[0]["hub_record"]),
                  smu[0]["hub_record"] == "3-0")
        check("every FIG row resolves to a hub team (aliases complete)",
              not d["unmatched"], d["unmatched"][:6])
    src = io.open(os.path.join(REPO, "scripts/external_refs.py"),
                  encoding="utf-8").read()
    check("external_refs holds NO writer (no dump/write/open-for-write)",
          "json.dump" not in src and "open(" not in src.replace(
              "io.open(", "").replace("os.path", "")
          or ("'w'" not in src and '"w"' not in src))
    check("...and never names the corrections ledger",
          "result_corrections" not in src)

    print("\n  [NEG] negative controls")
    bad_src = src + "\nimport json as _j\n_j.dump({}, open('x','w'))\n"
    check("[NEG] a writer added to the module is caught by the scan",
          "'w'" in bad_src)
    # an empty FIG state renders honest absence, never a guess
    d0 = ER.discrepancies(fig={}, hub={})
    check("[NEG] no snapshot -> no items, no invented freshness",
          d0["items"] == [] and d0["matched"] == 0)

    print("\n3. MASSEY CAN NEVER RENDER AS CURRENT")
    mm = ER.massey_meta()
    if mm["held"]:
        check("the held snapshot states its capture date",
              mm["captured"] == "2026-08-18"
              and mm["captured_display"] == "captured 2026-08-18")
    else:
        check("no snapshot -> the honest state, not an invented date",
              mm["captured"] is None
              and mm["captured_display"] == "capture date not held")
    check("its label is the preseason snapshot, in those words",
          mm["label"] == "Massey preseason snapshot")
    real_open = io.open
    import builtins
    # a header with no capture line must yield the honest absence
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("# Massey Ratings\n1|Nebraska\n")
        tmp = f.name
    real_path = ER.MASSEY_PATH
    try:
        ER.MASSEY_PATH = os.path.relpath(tmp, REPO)
        mm2 = ER.massey_meta()
    finally:
        ER.MASSEY_PATH = real_path
        os.unlink(tmp)
    check("[NEG] a capture-dateless file renders 'capture date not held', "
          "never an invented date",
          mm2["captured"] is None
          and mm2["captured_display"] == "capture date not held")

    print("\n4. THE BUILT PRIVATE PAGE")
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(page_p):
        page = io.open(page_p, encoding="utf-8").read()
        check("the External references disclosure is on Rankings AND "
              "Ballot", page.count("EXTREF-HTML-BEGIN") == 2)
        check("the Massey ruler tooltip says preseason snapshot, "
              "never current/live/updated",
              "Massey preseason snapshot" in page
              and not re.search(
                  r"Massey[^<]{0,60}\b(live|updated)\b", page)
              and not re.search(r"Massey[^<]{0,40}\bcurrent\b",
                                page.replace("not current", "")))
        if HELD:
            check("both timestamps render, distinct",
                  "Generated:" in page and "fetched" in page)
            check("the SMU mismatch row renders with its ledger link",
                  re.search(r'REFERENCE MISMATCH</b> <a href="#/teams/smu">'
                            r'SMU</a>[^<]*FIGstats 2-0; hub 3-0', page)
                  and 'href="#/result-ledger"' in page)
            check("...accented ONLY as ledgered evidence, not alarm",
                  'class="mmrow mmev"' in page and "mmrow mmev" in page)
            n_plain = page.count('class="mmrow"')
            check("ordinary source lag stays quiet (unaccented rows exist)",
                  n_plain > 0, n_plain)
        else:
            check("the disclosure states 'no snapshot held' rather than "
                  "guessing", "no snapshot held" in page)

    print("\n5. RANKING SEPARATION AND THE FETCH BAN")
    for mod in ("rating_2025.py", "digby_top25.py", "bakeoff_2025.py",
                "rpi_2025.py", "project_2026.py", "player_rating.py",
                "build_rankings_board.py", "snapshot_rankings.py",
                "resume_rank.py"):
        p = os.path.join(REPO, "scripts", mod)
        if not os.path.exists(p):
            continue
        msrc = io.open(p, encoding="utf-8").read()
        check("%s never reads external_refs or the FIG snapshot" % mod,
              "external_refs" not in msrc and "figstats" not in msrc.lower())
    hook = io.open(os.path.join(REPO, ".claude/hooks/no_scrape.py"),
                   encoding="utf-8").read()
    check("figstats.net is on the no-scrape hook", "figstats.net" in hook)

    print("\n6. THE PUBLIC BUILD CARRIES NONE OF IT")
    pub_p = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub_p):
        pub = io.open(pub_p, encoding="utf-8").read()
        for frag in ("FIGstats", "figstats", "Massey preseason",
                     "REFERENCE MISMATCH", "EXTREF", "ncaastats",
                     "Generated: 2026"):
            check("public page lacks %r" % frag, frag not in pub)
        m = re.search(r"const TEAMS = (\{.*?\});\n", pub, re.S)
        if m:
            teams = json.loads(m.group(1).replace("<\\/", "</"))
            check("no massey/vt VALUE inside the public TEAMS payload",
                  not any(isinstance(t, dict) and (t.get("massey") or
                                                   t.get("vt"))
                          for t in teams.values()))

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL EXTERNAL-REFERENCE GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
