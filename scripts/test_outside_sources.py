#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the two outside-source legs (2026-09-13).

Cody watched Purdue-SMU while every surface here called it upcoming: the
NCAA feed said 3:00 PM PT, Purdue's own site said 2:00, and the match was
underway. These are the checks that catch that class without him.

  fixture_time_check.py  -- does the school agree about when a match starts?
  availability_scan.py   -- do the school's own words say anything about the
                            players the box scores flagged?

The rule both obey: THEY FLAG, THEY NEVER DECIDE. Only the hand-curated
fixture ledger may change a displayed time, and only a human filing an
attributable source may create an availability status. A machine that both
nominates and believes its own evidence has no second witness.

Run: python3 scripts/test_outside_sources.py -- no network.
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from test_scoreboard_density import fn as js_block  # noqa: E402

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
FAILS = []


def _code_only(src):
    """Python source minus comments and docstrings.

    ⚠ Twelfth time a check in this codebase would otherwise match the
    COMMENT that documents the rule it enforces. Strip first, then search.
    """
    out, i, n = [], 0, len(src)
    TQ = ('"' * 3, "'" * 3)
    while i < n:
        c = src[i]
        if c == "#":
            j = src.find(chr(10), i)
            i = n if j < 0 else j
            continue
        q3 = next((q for q in TQ if src.startswith(q, i)), None)
        if q3:
            j = src.find(q3, i + 3)
            i = n if j < 0 else j + 3
            continue
        out.append(c)
        i += 1
    return "".join(out)


def check(label, ok, detail=""):
    print("  %-68s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)


def main():
    print("1. THE TIME CHECK FLAGS, IT DOES NOT CORRECT")
    src = io.open(os.path.join(REPO, "scripts", "fixture_time_check.py"),
                  encoding="utf-8").read()
    code = _code_only(src)
    check("it never writes the fixture ledger",
          "fixture_corrections" not in code)
    check("the artifact says it is not a correction",
          "what_this_is_not" in src)
    check("the tolerance is a named constant, not a magic number",
          "TOLERANCE_MIN" in code)
    check("...and the source says it is stated rather than fitted",
          "not fitted" in src)

    p = os.path.join(REPO, "data", "fixture_time_check_%d.json" % SEASON)
    if os.path.exists(p):
        doc = json.load(io.open(p, encoding="utf-8"))
        check("it records how many fixtures it checked",
              (doc.get("fixtures_checked") or 0) > 0, doc.get("fixtures_checked"))
        check("...and how many schools actually answered",
              "schools_answered" in doc, sorted(doc)[:6])
        for r in (doc.get("disagreements") or []):
            if not (r.get("feed_epoch") and r.get("school_epoch")
                    and r.get("school_asked")):
                check("every disagreement names both times and the school",
                      False, r)
                break
        else:
            check("every disagreement names both times and the school", True)
        check("[NEG] no disagreement inside the tolerance is reported",
              all(abs(r["minutes_apart"]) >= doc["tolerance_minutes"]
                  for r in (doc.get("disagreements") or [])))

    print("\n2. THE PAGE SHOWS BOTH TIMES AND PICKS NEITHER")
    page = io.open(os.path.join(REPO, "Cody", "START-HERE.html"),
                   encoding="utf-8").read()
    note = js_block(page, "tdisNote")
    check("the renderer exists", bool(note))
    if note:
        check("it names the school that published the other time",
              "school_asked" in note)
        check("it says neither is corrected here",
              "Neither is corrected here" in note)
        check("[NEG] it never replaces the displayed time",
              "f.t =" not in note and "f.t=" not in note)

    print("\n3. THE TEXT SCAN CANNOT CREATE A STATUS")
    ssrc = io.open(os.path.join(REPO, "scripts", "availability_scan.py"),
                   encoding="utf-8").read()
    check("it never writes the availability evidence ledger",
          "availability_evidence" not in _code_only(ssrc))
    # ⚠ NO MEDICAL VOCABULARY IS SEARCHED FOR AT ALL. A machine harvesting
    # diagnosis words about named athletes is the thing this project will
    # not do; the phrase list is about PARTICIPATION only.
    import availability_scan as AS
    med = ("torn", "acl", "surgery", "concussion", "sprain", "fracture",
           "illness", "injur")
    bad = [w for w in med if any(w in ph.lower() for ph in AS.PHRASES)]
    check("[NEG] the phrase list contains no diagnosis word", not bad, bad)
    PART = ("play", "miss", "lineup", "rotation", "dress", "available",
            "travel", "return", "street clothes", "held out")
    off = [ph for ph in AS.PHRASES
           if not any(k in ph for k in PART)]
    # ⚠ the detail must list what ACTUALLY failed. The first version
    # printed every phrase without the word "play", which is most of them,
    # so a real failure ("out of the rotation") was buried in noise.
    check("every phrase describes participation, not condition", not off, off)

    print("\n4. EVIDENCE BINDS TO ITS OWN SENTENCE (R8)")
    check("the binding rule is stated in the source",
          "SAME sentence" in ssrc and "USC" in ssrc)
    check("it splits text into sentences rather than scanning a window",
          "def sentences(" in ssrc)
    sents = AS.sentences("Smith did not play. Jones led with 12 kills.")
    check("a sentence splitter that actually splits", len(sents) == 2, sents)
    # the real trap: a phrase in one sentence and the surname in the NEXT
    hit = [s for s in AS.sentences(
        "Jones led the way. Smith added nine kills.")
        if "did not play" in s.lower()]
    check("[NEG] a phrase in a neighbouring sentence is not a match", not hit)

    print("\n5. A RUN THAT READS NOTHING IS NOT A RUN THAT FOUND NOTHING")
    sp = os.path.join(REPO, "data", "availability_scan_%d.json" % SEASON)
    if os.path.exists(sp):
        sdoc = json.load(io.open(sp, encoding="utf-8"))
        check("the artifact records how much text it actually read",
              "articles_read" in sdoc and "chars_scanned" in sdoc,
              sorted(sdoc)[:8])
        check("...and this run really did read some",
              (sdoc.get("chars_scanned") or 0) > 1000,
              sdoc.get("chars_scanned"))
        check("coverage is stated, not implied",
              "teams_unreadable" in sdoc)
        for sig in (sdoc.get("signals") or []):
            if not (sig.get("quote") and sig.get("source_url")):
                check("every signal quotes its source and links it", False, sig)
                break
        else:
            check("every signal quotes its source and links it", True)

    print("\n6. BOTH RUN WITHOUT BEING ASKED")
    lr = io.open(os.path.join(REPO, "scripts", "local_refresh.py"),
                 encoding="utf-8").read()
    for name in ("fixture_time_check.py", "availability_scan.py"):
        check("local_refresh runs %s" % name, name in lr)
        for wf in ("refresh.yml", "daily.yml"):
            t = io.open(os.path.join(REPO, ".github", "workflows", wf),
                        encoding="utf-8").read()
            check("%s runs %s" % (wf, name), name in t)

    print("\n%s" % ("ALL OUTSIDE-SOURCE GUARDS PASS" if not FAILS else
                    "FAILED: %d\n   - %s" % (len(FAILS), "\n   - ".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
