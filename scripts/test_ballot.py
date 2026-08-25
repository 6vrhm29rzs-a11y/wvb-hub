#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the Ballot Workshop: saved-history integrity and output format.

TWO THINGS HAVE TO BE TRUE OR THE FEATURE IS WORSE THAN A TEXT FILE.

  1. A SAVED BALLOT IS NEVER LOST. The whole point of weekly history is to see
     what you changed your mind about; a save that overwrites last week's
     destroys the only record of that. Append-only is the mechanism, and it is
     asserted rather than trusted.

  2. THE COPIED TEXT IS WHAT GETS POSTED. It goes on a forum under Cody's name.
     A stray character, a missing slot or a renumbered list is his problem, not
     ours -- so the format is pinned exactly.

⚠ AND ONE THING THAT MUST NEVER BECOME TRUE: a move reason must not turn into a
number. The rating engine was measured on precisely these ideas -- clutch,
composure, five-set nerve -- and every one made it predict WORSE
(docs/rating_factors_2025.md). They belong to a person's judgment, recorded as
words. This asserts the ballot never reaches any rating input.

Python 3.9 target. Run: python3 scripts/test_ballot.py
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ballot as B  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-62s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def mk(pairs, **kw):
    d = {"teams": [{"team": t, "rank": r} for r, t in pairs]}
    d.update(kw)
    return d


def main():
    print("BALLOT WORKSHOP GUARDS\n")

    tmp = tempfile.mkdtemp(prefix="wvb-ballot-")
    real = B.PATH
    B.PATH = os.path.join(tmp, "ballots_test.jsonl")
    try:
        print("1. Saved history is append-only and never silently overwritten")
        b1 = mk([(1, "Nebraska"), (2, "Texas"), (3, "Pittsburgh")], summary="week one")
        B.append(b1)
        b2 = mk([(1, "Pittsburgh"), (2, "Nebraska"), (3, "Kentucky")])
        B.append(b2)
        rows = B.load()
        check("both saves are on file", len(rows) == 2, "(%d)" % len(rows))
        check("the first ballot survives the second, unchanged",
              [t["team"] for t in rows[0]["teams"]] == ["Nebraska", "Texas", "Pittsburgh"])
        check("each save is one line", sum(
            1 for l in open(B.PATH, encoding="utf-8") if l.strip()) == 2)
        check("saves carry a timestamp assigned by the writer",
              all(r.get("saved_utc") for r in rows))
        check("...and the season and schema, so a file is self-describing",
              all(r.get("season") and r.get("schema") for r in rows))

        # NEGATIVE CONTROL: saving again must ADD, never replace.
        before = open(B.PATH, encoding="utf-8").read()
        B.append(mk([(1, "Texas")]))
        after = open(B.PATH, encoding="utf-8").read()
        check("a third save leaves the first two bytes untouched",
              after.startswith(before),
              "the file was rewritten rather than appended to")

        print("\n2. A malformed ballot is refused, with a reason")
        for bad_ballot, why in (
                (mk([(1, "A"), (1, "B")]), "two teams share a slot"),
                ({"teams": [{"team": "A", "rank": 1}, {"team": "A", "rank": 2}]},
                 "the same team twice"),
                (mk([(1, "A"), (3, "B")]), "a gap in the slots"),
                (mk([(26, "A")]), "a rank outside 1-25"),
                ({"teams": []}, "an empty ballot"),
                ({"teams": [{"team": "A", "rank": 1, "note": "x" * 999}]},
                 "an over-long note")):
            check("refused: %s" % why, B.validate(bad_ballot) is not None)
        check("a legitimate ballot is accepted", B.validate(b1) is None,
              str(B.validate(b1)))
        # POSITIVE CONTROL: an "also considered" team (rank None) is fine.
        ok_pool = {"teams": [{"team": "A", "rank": 1}, {"team": "B", "rank": None}]}
        check("a team set aside with no slot is allowed",
              B.validate(ok_pool) is None, str(B.validate(ok_pool)))

        print("\n3. The copied text is exactly what a forum post needs")
        cur = mk([(1, "Nebraska"), (2, "Texas"), (3, "Kentucky")], summary="my note")
        prev = mk([(1, "Texas"), (2, "Nebraska"), (3, "Pittsburgh")])
        txt = B.as_text(cur, prev)
        lines = txt.split("\n")
        check("line 1 is '1. Team'", lines[0] == "1. Nebraska", repr(lines[0]))
        check("slots are numbered 1..N with '. ' after the number",
              all(re.match(r"^%d\. \S" % (i + 1), lines[i]) for i in range(3)),
              repr(lines[:3]))
        check("no markup, no branding, nothing the author did not write",
              not re.search(r"<[a-z/]|\*\*|&[a-z]+;|Digby|POWER", txt), repr(txt[:90]))
        check("the notes heading appears once when there is something to say",
              txt.count("Notes / biggest moves") == 1)
        check("the author's own summary is carried through", "my note" in txt)
        check("a team that entered is named", "in: Kentucky" in txt, repr(txt))
        check("a team that dropped is named", "out: Pittsburgh" in txt, repr(txt))

        bare = B.as_text(cur, prev, include_notes=False)
        check("notes can be left off entirely",
              "Notes" not in bare and bare.count("\n") == 2)

        first = B.as_text(mk([(1, "A"), (2, "B")]), None)
        check("a first-week ballot needs no comparison to format",
              first == "1. A\n2. B", repr(first))

        print("\n4. Comparison is against the PREVIOUS BALLOT, not against POWER")
        c = B.compare(cur, prev)
        check("a team that moved up is reported as up",
              any(m["team"] == "Nebraska" and m["move"] == 1 for m in c["moved"]),
              str(c["moved"]))
        check("a team that moved down is reported as down",
              any(m["team"] == "Texas" and m["move"] == -1 for m in c["moved"]))
        check("entered and dropped are separated",
              c["entered"] == ["Kentucky"] and c["dropped"] == ["Pittsburgh"])
        check("the first week says so rather than inventing movement",
              B.compare(cur, None)["first_week"] is True)
        same = B.compare(cur, cur)
        check("an unchanged ballot reports no movement",
              not same["moved"] and len(same["unchanged"]) == 3)
    finally:
        B.PATH = real
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n5. The two formatters agree, character for character")
    # ⚠ THERE ARE TWO IMPLEMENTATIONS OF ONE FORMAT: ballot.py:as_text() and the
    # page's bwText(). This project has already shipped two mirrors of one rule
    # that disagreed on PUNCTUATION -- day_label rendered "Sat Aug 29" while
    # dayLabel rendered "Sat, Aug 29", two inches apart on the same screen.
    # Here the stakes are higher: this text gets posted on a forum under Cody's
    # name. So the page's own function is EXTRACTED AND RUN, not eyeballed.
    import shutil as _sh
    import subprocess
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not _sh.which("node"):
        print("  %-62s %s" % ("the two formatters agree (node not installed)", "skip"))
    elif not os.path.exists(hub):
        print("  %-62s %s" % ("the two formatters agree (no built page)", "skip"))
    else:
        page = open(hub, encoding="utf-8").read()
        m = re.search(r"function bwText\(\) \{.*?\n\}", page, re.S)
        if not m:
            check("bwText() could be found in the page", False,
                  "the cross-implementation check is testing nothing")
        else:
            cur = mk([(1, "Nebraska"), (2, "Texas"), (3, "Kentucky")],
                     summary="my note")
            prv = mk([(1, "Texas"), (2, "Nebraska"), (3, "Pittsburgh")])
            # stub only what bwText reads from the page
            prog = (
                "const CUR=%s, PRV=%s;\n"
                "function bwRanked(){return CUR.teams.filter(t=>t.rank)"
                ".sort((a,b)=>a.rank-b.rank);}\n"
                "function bwPrev(){return PRV;}\n"
                "const document={getElementById:()=>({value:CUR.summary||''})};\n"
                % (json.dumps(cur), json.dumps(prv))
                + m.group(0) + "\nprocess.stdout.write(bwText());")
            fh = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                             encoding="utf-8")
            fh.write(prog)
            fh.close()
            try:
                r = subprocess.run(["node", fh.name], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
                got = r.stdout.decode("utf-8")
                want = B.as_text(cur, prv)
                if r.returncode != 0:
                    check("bwText() runs", False, got.strip()[:150])
                else:
                    check("the page's text is byte-identical to ballot.py's",
                          got == want,
                          "\n      js : %r\n      py : %r" % (got[-90:], want[-90:]))
            finally:
                os.unlink(fh.name)

    print("\n6. First week says nothing rather than asserting change")
    hub2 = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(hub2):
        page2 = open(hub2, encoding="utf-8").read()
        # blank when there is no baseline; NEW only against a real prior ballot
        check("a row shows no movement badge when no ballot has been saved",
              re.search(r"const base = bwPrev\(\);\s*\n\s*const mv = !base \? ''",
                        page2) is not None,
              "with no baseline every row asserted NEW -- a change nobody measured")

    print("\n7. The ballot feeds no rating, and is not published")
    # ⚠ THE INVARIANT THAT MATTERS MOST. Reasons are words; if any rating input
    # ever read this file, a subjective trait would have become a coefficient.
    # ⚠ THE SCAN IS OVER MODEL CODE, NOT OVER GUARDS -- and the first version
    # was not, which its own run exposed: test_display_invariants.py contains
    # the literal string "data/ballots_2026.jsonl" as a NEGATIVE CONTROL for
    # the publishing gate. It does not read the file; it injects the string to
    # prove the gate catches it. Flagging that would have pushed me to weaken
    # a real guard to satisfy this one.
    #
    # A test naming the path is fine. A RATING script naming it is not, and
    # that is the invariant: no model input may ever read a ballot, or a
    # subjective trait would have become a coefficient.
    hits = []
    for fn in sorted(os.listdir(os.path.join(REPO, "scripts"))):
        if not fn.endswith(".py"):
            continue
        if fn.startswith("test_") or fn in ("ballot.py", "live_server.py",
                                            "build_hub.py"):
            continue
        src = open(os.path.join(REPO, "scripts", fn), encoding="utf-8").read()
        if "ballots_" in src or re.search(r"^\s*import ballot\b", src, re.M):
            hits.append(fn)
    check("no rating, projection or simulator script reads the ballot file",
          not hits, str(hits))
    # POSITIVE CONTROL: the scan can see a real reader, or it proves nothing.
    check("...and the scan would notice one that did",
          "ballots_" in open(os.path.join(REPO, "scripts", "ballot.py"),
                             encoding="utf-8").read())

    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        h = open(pub, encoding="utf-8").read()
        leaked = [m for m in ('id="v-ballot"', 'data-v="ballot"', "renderBallot",
                              "BW_KEY", "Ballot Workshop") if m in h]
        check("the workshop is absent from the public build", not leaked, str(leaked))
    else:
        print("  (no public build on disk -- skipping the leak check)")

    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(hub):
        h = open(hub, encoding="utf-8").read()
        check("the private page HAS the workshop", 'id="v-ballot"' in h)
        # the page must not imply it submits anything
        sec = re.search(r'<section id="v-ballot".*?</section>', h, re.S)
        body = sec.group(0) if sec else ""
        check("the page never claims to post or submit for him",
              not re.search(r"\bsubmit(s|ted)? (it|your|the) ballot\b|posts? to\b",
                            body, re.I))
        check("it says the responsibility is his",
              "is yours" in body or "responsib" in body.lower())

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL BALLOT GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
