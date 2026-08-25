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
import subprocess
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

    print("\n7. Ballot history stays off this machine")
    # ⚠ THIS REPOSITORY IS PUBLIC. A tracked ballot file would be world-readable
    # the moment the daily job committed it -- the ranking, the private per-team
    # notes, and the written reasons for overruling the model.
    ig = os.path.join(REPO, ".gitignore")
    rules = open(ig, encoding="utf-8").read() if os.path.exists(ig) else ""
    check("data/ballots_*.jsonl is gitignored",
          "data/ballots_*.jsonl" in rules,
          "a ballot saved locally would be committed to a public repo")
    # ⚠ EVERY SEASON, not just this one. A rule naming 2026 protects nothing on
    # 1 January, and the file is created automatically on first save.
    check("...by a glob, so a future season is covered too",
          "ballots_2026.jsonl" not in rules.replace("data/ballots_*.jsonl", ""),
          "a season-specific rule leaves next season exposed")
    # ⚠ ASK GIT ONLY WHERE THERE IS A GIT REPO. The fresh-checkout guard runs
    # this suite in a temp directory holding tracked FILES and no .git, where
    # `git check-ignore` exits 128 for "not a repository" -- which the first
    # version read as "not ignored" and turned the whole nightly run red for a
    # condition that was fine. Exit 1 means not ignored; 128 means there is
    # nothing to ask. The .gitignore content check above is the real invariant
    # and runs everywhere.
    inrepo = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                            cwd=REPO, capture_output=True, text=True)
    if inrepo.returncode != 0 or inrepo.stdout.strip() != "true":
        print("  (not a git work tree here -- skipping the git-level checks)")
    else:
        tracked = subprocess.run(["git", "ls-files", "data/ballots_*"],
                                 cwd=REPO, capture_output=True, text=True).stdout.strip()
        check("no ballot file is tracked by git", not tracked, repr(tracked))
        # git must actually refuse the path: the rule could be shadowed by a
        # later negation, which reading .gitignore would not reveal
        r = subprocess.run(["git", "check-ignore", "-q", "data/ballots_2099.jsonl"],
                           cwd=REPO)
        check("git itself refuses a ballot path", r.returncode == 0,
              "check-ignore exit %d (1 = not ignored)" % r.returncode)

    # the daily job must not force past the ignore
    wf = os.path.join(REPO, ".github", "workflows", "daily.yml")
    if os.path.exists(wf):
        y = open(wf, encoding="utf-8").read()
        forced = re.findall(r"git add[^\n]*-f\b[^\n]*", y)
        broad = re.findall(r"git add\s+(?:-A|\.|data/)\s*$", y, re.M)
        check("the daily job never force-adds an ignored file", not forced, str(forced))
        check("...and never adds data/ or . wholesale", not broad, str(broad))

    print("\n8. The private backup leaks nothing into the public repo")
    bb = os.path.join(REPO, "scripts", "ballot_backup.py")
    if not os.path.exists(bb):
        print("  (no backup script -- skipping)")
    else:
        src = open(bb, encoding="utf-8").read()
        # ⚠ THIS FILE IS COMMITTED TO A PUBLIC REPOSITORY. It must not name the
        # private destination -- not the repo, not a token, not even an
        # absolute local path. The remote is discovered from the backup
        # directory's own .git/config, outside this project.
        leaks = []
        if re.search(r'https?://\S*github', src, re.I):
            leaks.append("a github URL")
        if re.search(r"ghp_|github_pat_|sk-ant-|ANTHROPIC_API_KEY", src):
            leaks.append("a credential")
        if re.search(r"/Users/", src):
            leaks.append("an absolute home path")
        if "wvb-hub-private" in src:
            leaks.append("the private repo name")
        check("the backup script names no URL, credential or absolute path",
              not leaks, ", ".join(leaks))
        # POSITIVE CONTROL: the scan can see such a string when one is present.
        check("...and the scan would catch one (positive control)",
              bool(re.search(r'https?://\S*github', src + 'https://github.com/x')))
        # it must never be wired into CI
        wf2 = os.path.join(REPO, ".github", "workflows", "daily.yml")
        if os.path.exists(wf2):
            check("the daily job never runs the backup",
                  "ballot_backup" not in open(wf2, encoding="utf-8").read(),
                  "CI has no credentials for a private repo and no business "
                  "touching one")

    # a failed backup must never be reported as a success
    hub3 = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(hub3):
        h3 = open(hub3, encoding="utf-8").read()
        check("the workshop can say BACKUP PENDING", "BACKUP PENDING" in h3,
              "a failed sync would be indistinguishable from a good one")
        check("...and it is styled as a warning, not a success",
              re.search(r"BACKUP PENDING[^;]*?'warn'", h3, re.S) is not None)
    pub3 = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(pub3):
        check("no backup wording reaches the published page",
              "BACKUP PENDING" not in open(pub3, encoding="utf-8").read())

    print("\n9. The ballot feeds no rating, and is not published")
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
        # Excluded on purpose, each for a different reason:
        #   test_*        guards may NAME the path as a control fixture
        #   ballot.py     owns the file
        #   ballot_backup.py  copies it -- that IS its job, and it is not a
        #                 model input; it computes nothing and returns nothing
        #                 to any rating
        #   live_server / build_hub  serve and render, they do not rate
        if fn.startswith("test_") or fn in ("ballot.py", "ballot_backup.py",
                                            "live_server.py", "build_hub.py"):
            continue
        src = open(os.path.join(REPO, "scripts", fn), encoding="utf-8").read()
        if "ballots_" in src or re.search(r"^\s*import ballot\b", src, re.M):
            hits.append(fn)
    check("no rating, projection or simulator script reads the ballot file",
          not hits, str(hits))
    # ⚠ AND THE BACKUP MUST STAY INERT. It may read the ballot -- that is what a
    # backup does -- but it must never compute from it or hand it to anything.
    bbp = os.path.join(REPO, "scripts", "ballot_backup.py")
    if os.path.exists(bbp):
        bsrc = open(bbp, encoding="utf-8").read()
        modelish = [t for t in ("rating", "projection", "simulate", "digby_top25",
                                "composite", "resume_") if t in bsrc]
        check("the backup script imports and computes nothing model-related",
              not modelish, str(modelish))
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

    # ---------------------------------------------------------------- #
    print("\n10. THE THREE RULERS ARE NEVER CONFLATED")
    # ⚠ A TOOLTIP IS NOT A LABEL. Both rank badges used to render a bare
    # numeral whose only identification was title=, so on the page they were
    # interchangeable and a reader assigned them to whichever ranking they had
    # in mind. My ballot / POWER / AVCA answer three different questions and
    # RESUME answers a fourth it cannot answer yet.
    for label, path in (("private", os.path.join(REPO, "Cody", "START-HERE.html")),
                        ("public", os.path.join(REPO, "output",
                                                "vb_dashboard.html"))):
        if not os.path.exists(path):
            continue
        h = open(path, encoding="utf-8").read()
        bare = re.findall(r'<i class="rnk"[^>]*>\s*\d+\s*</i>', h)
        check("%s: no external rank renders as a bare numeral" % label,
              not bare, "%d bare badge(s), e.g. %s" % (len(bare), bare[:1]))
        check("%s: the AVCA badge says AVCA on the page" % label,
              "<s>AVCA</s>#" in h)
        check("%s: the POWER badge says POWER on the page" % label,
              "<s>POWER</s>#" in h)
        # RESUME is inactive: it must SAY so, and must not show a number.
        check("%s: an inactive resume says so rather than showing a rank" % label,
              "not active yet" in h)
    hp = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(hp):
        h = open(hp, encoding="utf-8").read()
        for ruler in ("My ballot", "POWER", "AVCA"):
            check("the legend names %r as its own ruler" % ruler,
                  ruler in h)
        check("the legend says RESUME is inactive",
              "inactive until enough games are played" in h)
        # Each is described as a DIFFERENT question, not three views of one.
        check("the legend distinguishes ours from the external poll",
              "the coaches poll" in h and "how strong a team is" in h)

    print("\n11. NO RATIONALE IS EVER INVENTED")
    src = open(os.path.join(REPO, "scripts", "build_hub.py"),
               encoding="utf-8").read()
    # A default would look like assigning a non-empty literal to a reason field.
    bad = re.findall(r"\breason(?:_kind)?\s*[:=]\s*['\"][^'\"]+['\"]", src)
    check("no default text is ever assigned to a reason field", not bad,
          str(bad[:3]))
    planted = 'ent.reason = "moved on recent form"'
    check("...and the scan would catch one (positive control)",
          bool(re.findall(r"\breason(?:_kind)?\s*[:=]\s*['\"][^'\"]+['\"]",
                          planted)))
    check("the workshop MARKS a missing reason instead of writing one",
          "no reason written yet" in src)
    check("...and never blocks the save for it",
          "bwPreReview" in src and "bwpresave" in src)
    # The stored note/reason are only ever read from the author's own input.
    check("reason and note come from input elements the author types into",
          'data-reason="' in src and 'data-note="' in src)

    print("\n12. A BALLOT CANNOT REACH ANY RATING OR PROJECTION")
    # ⚠ STRUCTURAL, NOT PROMISED. Every script that produces a rating, a
    # projection, a forecast or a simulation is read and must contain no
    # reference to the ballot module or its file.
    pipeline = ["rating_2025.py", "project_2026.py", "predict_2026.py",
                "simulate_season_2026.py", "project_field.py",
                "digby_top25.py", "build_rankings_board.py", "resume_2025.py",
                "snapshot_rankings.py", "build_dataset.py", "score_predictions.py"]
    for fn in pipeline:
        fp = os.path.join(REPO, "scripts", fn)
        if not os.path.exists(fp):
            continue
        body = open(fp, encoding="utf-8").read()
        hit = [w for w in ("import ballot", "ballots_", "ballot.load",
                           "ballot.py", "BW_") if w in body]
        check("%s never reads a ballot" % fn, not hit, str(hit))

    print("\n13. OLD BALLOT HISTORY STILL LOADS")
    # A row written before pinning existed carries none of the new fields.
    legacy = {"teams": [{"team": "Nebraska", "rank": 1},
                        {"team": "Texas", "rank": 2, "note": "old note"},
                        {"team": "Pittsburgh", "rank": None}],
              "summary": "written last week"}
    check("a ballot with no new fields still validates",
          B.validate(legacy) is None, str(B.validate(legacy)))
    check("...and still ranks", [t for _r, t in B.ranked(legacy)]
          == ["Nebraska", "Texas"])
    check("...and still formats", B.as_text(legacy).startswith("1. Nebraska"))
    check("a team with no slot survives as also-considered",
          any(t["team"] == "Pittsburgh" for t in legacy["teams"]))
    # And the new optional field is genuinely optional in BOTH directions.
    pinned = json.loads(json.dumps(legacy))
    pinned["teams"][2]["pinned"] = True
    check("an unknown/optional field does not break validation",
          B.validate(pinned) is None, str(B.validate(pinned)))
    check("...and does not change the text output",
          B.as_text(pinned) == B.as_text(legacy))
    check("...and does not change the ranked order",
          B.ranked(pinned) == B.ranked(legacy))

    print("\n14. THE PHONE LAYOUT IS DECLARED, NOT HOPED FOR")
    check("the two-column workshop collapses on a narrow screen",
          re.search(r"@media \(max-width:900px\)\{[^}]*\.bwgrid\{"
                    r"grid-template-columns:1fr\}", src) is not None)
    check("the pre-submit's three columns stack on a phone",
          ".bwprecols{grid-template-columns:1fr}" in src)
    check("a case row wraps rather than overflowing",
          ".bwcase{display:flex" in src and "flex-wrap:wrap" in src)

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
