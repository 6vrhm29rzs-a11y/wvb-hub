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
              '<span class="rank-label">AVCA</span>#' in h)
        check("%s: the POWER badge says POWER on the page" % label,
              '<span class="rank-label">POWER</span>#' in h)
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

    print("\n15. CLOSEOUT A -- BALLOT CSS IS STRIPPED FROM THE PUBLIC BUILD")
    # ⚠ .bwrap IS NOT BALLOT. It is the bracket wrapper (#brkview .bwrap), and
    # a naive "anything starting .bw" guard fails on it -- which is exactly the
    # false positive that would get this test disabled.
    BALLOT_SELECTORS = (
        ".privtag", ".bwbar", ".bwbtn", ".bwstate", ".bwgrid", ".bwh", ".bwsub",
        ".bwlist", ".bwrow", ".bwtop", ".bwslot", ".bwmv", ".bwteam", ".bwctl",
        ".bwjump", ".bwev", ".bwe", ".bwrulers", ".bwr", ".bwreview", ".bwrn",
        ".bwgrp", ".bwcase", ".bwwhy", ".bwpin", ".bwpre", ".bwprehd",
        ".bwprecols", ".bwcmp", ".bwcmprow", "#bwcmpout", ".bwask", ".bwaskrow",
        ".bwnote", ".bwpool", ".bwchip", ".bwnone", ".bwempty", ".bwlink",
        ".bwadd", ".bwside", ".bwcard", ".bwdl", ".bwdrow", ".bwhrow",
        ".bwlatest", ".bwh4")
    src = open(os.path.join(REPO, "scripts", "build_hub.py"),
               encoding="utf-8").read()
    check("the ballot CSS region is fenced by sentinels",
          "BALLOT-CSS-BEGIN" in src and "/* BALLOT-CSS-END */" in src)
    region = re.search(r"BALLOT-CSS-BEGIN.*?/\* BALLOT-CSS-END \*/", src, re.S)
    check("the fence encloses a real region", region is not None)
    if region:
        body = region.group(0)
        # ⚠ NOTHING SHARED MAY LIVE INSIDE THE FENCE -- it would be deleted from
        # the public page silently. Every selector must be ballot-only.
        sels = re.findall(r"^\s*([.#][A-Za-z][^{,\n]*)(?:,|\{)", body, re.M)
        stray = [x.strip() for x in sels
                 if not (x.strip().startswith((".bw", "#bw", ".privtag")))]
        check("the fence contains no shared selector", not stray, str(stray[:4]))
        check("...and it is substantial, not an empty fence",
              body.count("{") > 40, str(body.count("{")))
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    priv = os.path.join(REPO, "Cody", "START-HERE.html")
    if os.path.exists(pub):
        ph = open(pub, encoding="utf-8").read()
        def present(sel, doc):
            # a selector ends where a CSS name can no longer continue
            return re.search(re.escape(sel) + r"(?![A-Za-z0-9_-])", doc) is not None
        left = [x for x in BALLOT_SELECTORS if present(x, ph)]
        check("NO ballot selector survives in the published HTML", not left,
              str(left[:6]))
        # ⚠ CONTROL THE CHECK, NOT THE BUILD. Disabling the strip does not make
        # this test red: the public build ABORTS instead (the fence comment
        # names the Workshop, which is a private marker), so the old good file
        # stays on disk and the test reads that. Fail-closed is the stronger
        # behaviour -- but it means the only way to show this check can fail is
        # to feed it a document that really does carry the CSS.
        doctored = ph + "\n.bwreview{margin:8px}\n.privtag{color:red}\n"
        caught = [x for x in BALLOT_SELECTORS if present(x, doctored)]
        check("[+] ...and the check FIRES when it is there (control)",
              ".bwreview" in caught and ".privtag" in caught, str(caught[:4]))
        check("[-] the token match does not confuse .bwr with .bwrap",
              not present(".bwr", ".bwrap{display:block}"))
        check("[+] ...but does find .bwr when it is a real rule",
              present(".bwr", ".bwr i{color:red}"))
        check("...and neither does the fence itself",
              "BALLOT-CSS-BEGIN" not in ph)
        # .bwrap must SURVIVE: it belongs to the bracket, not the ballot.
        check("[+] the bracket's own .bwrap is NOT collateral damage",
              ".bwrap" in ph)
        # ⚠ THE LEAK THE FENCE CANNOT SEE FROM THE INSIDE. A class defined
        # inside the fence but USED by public markup would ship unstyled --
        # found exactly this: the Match Desk had borrowed .bwsub. The check is
        # on the consumer side, where the damage would actually appear.
        fenced = set(re.findall(r"[.#](bw[A-Za-z0-9_-]*|privtag)", region.group(0)))
        used = set()
        for attr in re.findall(r'class="([^"]+)"', ph):
            for cl in attr.split():
                used.add(cl)
        orphan = sorted(c for c in used if c in fenced)
        check("no PUBLIC markup uses a class whose CSS was stripped",
              not orphan, str(orphan))
    if os.path.exists(priv):
        vh = open(priv, encoding="utf-8").read()
        # POSITIVE CONTROL: the private page must still be styled, or "stripped
        # from public" would be satisfied by deleting the CSS everywhere.
        kept = [x for x in BALLOT_SELECTORS
                if re.search(re.escape(x) + r"(?![A-Za-z0-9_-])", vh)]
        check("[+] the PRIVATE page keeps its ballot CSS",
              len(kept) > 30, "only %d of %d" % (len(kept), len(BALLOT_SELECTORS)))

    print("\n16. CLOSEOUT B -- RANK LABELS ARE SEMANTIC, AND STILL VISIBLE")
    # ⚠ <s> MEANS "no longer accurate". It was being used to make a label small,
    # which says the opposite of what the label is for -- and a screen reader
    # announces struck-through text as deleted.
    for label, path in (("private", priv), ("public", pub)):
        if not os.path.exists(path):
            continue
        h = open(path, encoding="utf-8").read()
        check("%s: no <s> wraps a rank label" % label,
              "<s>AVCA</s>" not in h and "<s>POWER</s>" not in h)
        check("%s: the label uses a neutral element" % label,
              '<span class="rank-label">' in h)
        check("%s: AVCA is still VISIBLE beside its number" % label,
              '<span class="rank-label">AVCA</span>#' in h)
        check("%s: POWER is still VISIBLE beside its number" % label,
              '<span class="rank-label">POWER</span>#' in h)
        bare = re.findall(r'<i class="rnk"[^>]*>\s*\d+\s*</i>', h)
        check("%s: still no bare external numeral" % label, not bare,
              str(bare[:1]))
    check("both renderers emit the same element (python)",
          '<span class="rank-label">AVCA</span>#%s' in src)
    check("...and javascript",
          "'<span class=\"rank-label\">AVCA</span>#'" in src)
    check("the label no longer has to cancel a line-through",
          ".rank-label{" in src and ".rnk>s" not in src)

    print("\n17. CLOSEOUT C -- A MOVE AGAINST MY OWN BALLOT IS UNEXPLAINED TOO")
    check("there is a separate threshold for a personal move",
          "const BW_MOVE_AT = 3;" in src)
    check("...and it is independent of the POWER one",
          "const BW_ASK_AT = 4;" in src)
    check("a personal-move detector exists", "function bwPersonalMove" in src)
    check("...and one place decides whether a note is missing",
          "function bwUnexplained" in src)
    check("the pre-save 'vs last ballot' column flags them",
          "no reason written" in src and "bwwhy" in src)
    # Run the real functions under node with the page's own state stubbed out.
    node = shutil.which("node")
    if not node:
        print("  (no node on PATH -- skipping the behavioural check)")
    else:
        fns = []
        for fn in ("bwPersonalMove", "bwUnexplained"):
            m = re.search(r"function %s\(.*?\n\}" % fn, src, re.S)
            if m:
                fns.append(m.group(0))
        harness = """
const BW_MOVE_AT = 3, BW_ASK_AT = 4;
let PREV = null, POWER = {}, REASON = {};
function bwPrev() { return PREV; }
function bwPrevRank(n) { return PREV && PREV[n] != null ? PREV[n] : null; }
function bwEntry(n) { return { reason: REASON[n] || '' }; }
function bwMoveState(n, slot) {
  const p = POWER[n]; if (!p) return null;
  const d = p - slot; if (Math.abs(d) < BW_ASK_AT) return null;
  return { delta: d, power: p };
}
""" + "\n".join(fns) + """
const out = [];
function t(label, prev, power, reason, name, slot) {
  PREV = prev; POWER = power; REASON = reason;
  const pm = bwPersonalMove(name, slot);
  const un = bwUnexplained(name, slot);
  out.push([label, pm ? pm.kind : null, pm && pm.size, !!un,
            un && !!un.personal, un && !!un.power]);
}
// close to POWER, but moved 3 against my own ballot -- the case that was blind
t('moved 3, near POWER', {A:22}, {A:20}, {}, 'A', 19);
t('moved 2, near POWER', {A:21}, {A:20}, {}, 'A', 19);
t('entered', {B:1}, {A:20}, {}, 'A', 19);
t('dropped', {A:5}, {A:20}, {}, 'A', null);
t('moved 3 but explained', {A:22}, {A:20}, {A:'my reason'}, 'A', 19);
t('far from POWER only', {A:19}, {A:30}, {}, 'A', 19);
t('no previous ballot', null, {A:20}, {}, 'A', 19);
console.log(JSON.stringify(out));
"""
        got = json.loads(subprocess.check_output(
            [node, "-e", harness], universal_newlines=True).strip())
        by = dict((r[0], r) for r in got)
        check("[+] moved 3 slots near POWER is now unexplained",
              by['moved 3, near POWER'][3] is True
              and by['moved 3, near POWER'][4] is True
              and by['moved 3, near POWER'][5] is False, str(by['moved 3, near POWER']))
        check("[-] moved 2 slots is NOT flagged (threshold is 3)",
              by['moved 2, near POWER'][3] is False, str(by['moved 2, near POWER']))
        check("[+] entering the ballot counts", by['entered'][1] == 'entered'
              and by['entered'][3] is True, str(by['entered']))
        check("[+] dropping out counts", by['dropped'][1] == 'dropped'
              and by['dropped'][3] is True, str(by['dropped']))
        check("[-] a written reason clears it",
              by['moved 3 but explained'][3] is False,
              str(by['moved 3 but explained']))
        check("[+] the POWER marker still works on its own",
              by['far from POWER only'][3] is True
              and by['far from POWER only'][4] is False
              and by['far from POWER only'][5] is True,
              str(by['far from POWER only']))
        check("[-] with nothing saved there is no personal move to report",
              by['no previous ballot'][1] is None
              and by['no previous ballot'][3] is False,
              str(by['no previous ballot']))

    print("\n18. THE BALLOT COMMAND CENTER IS PRIVATE, ENTIRELY")
    NEW_PRIVATE = ("bwbrief", "bwqueue", "bwcompare", "bwteamcmp", "bwcA", "bwcB",
                   "bwro", "renderBriefing", "renderCompare", "bwOpenArchived",
                   "bwResultsSince", "data-openballot", "bwtrig", "bwcmptbl",
                   "bwweek", "bwrulerline")
    if os.path.exists(pub):
        ph2 = open(pub, encoding="utf-8").read()
        left = [x for x in NEW_PRIVATE if x in ph2]
        check("no briefing/queue/compare markup, css or code is published",
              not left, str(left[:5]))
        # ⚠ A NESTED <section> TRUNCATED THE STRIP AND SHIPPED THE WORKSHOP.
        # strip_private removes <section id="v-ballot".*?</section> NON-GREEDILY,
        # so an inner </section> ends the match early. The build aborted on its
        # own marker, which is the gate working -- this keeps it from recurring.
        bsec = re.search(r'<section id="v-ballot".*?</section>', src, re.S)
        check("the workshop contains no nested <section>",
              bsec is not None and "<section" not in bsec.group(0)[len('<section'):],
              "a nested section truncates the public strip")
    if os.path.exists(priv):
        vh2 = open(priv, encoding="utf-8").read()
        have = [x for x in NEW_PRIVATE if x in vh2]
        check("[+] ...and the PRIVATE page has all of it",
              len(have) == len(NEW_PRIVATE),
              "missing %s" % [x for x in NEW_PRIVATE if x not in vh2])

    print("\n19. REVIEW TRIGGERS STATE A FACT, NEVER AN INSTRUCTION")
    q = src[src.index("function bwQueue()"):]
    q = q[:q.index("\nfunction ")]
    for label in ("Your last ballot differs from POWER",
                  "The AVCA poll differs from your last ballot",
                  "Played since your last ballot",
                  "Entered or left your ballot",
                  "In the picture, but never on your ballot"):
        check("trigger present: %s" % label[:44], label in q)
    # ⚠ NO IMPERATIVE MAY REACH THIS SCREEN. A review queue that says "move
    # this team up" has stopped organising evidence and started voting.
    # ⚠ AND THE FIRST VERSION OF THIS CHECK FAILED ON ITS OWN DENIALS: the page
    # says "Nothing here is a recommended Top 25" and the source says "never
    # ordered by importance", and a bare substring search cannot tell a promise
    # from a violation. Every occurrence must sit in a sentence that NEGATES
    # it -- which is a statement about meaning, not about spelling.
    NEG = ("nothing", "never", "not ", "no ", "cannot", "n't")
    def sentences_with(phrase, text):
        out = []
        low = text.lower()
        i = low.find(phrase.lower())
        while i >= 0:
            a = max(0, low.rfind(".", 0, i) + 1)
            b = low.find(".", i)
            out.append(text[a:(b if b > 0 else len(text))])
            i = low.find(phrase.lower(), i + 1)
        return out
    for verb in ("Move this team", "should be ranked", "we recommend",
                 "recommended Top 25", "deserves to be", "move up", "move down"):
        hits = sentences_with(verb, src)
        # ⚠ NORMALISE FIRST. A negation split across a line break ("and no\n
        # list is ordered by...") is still a negation; matching raw text made
        # the checker blind to it and it accused a promise of being a breach.
        bare = [h for h in hits
                if not any(n in re.sub(r"\s+", " ", h).lower() for n in NEG)]
        check("[-] %r appears only inside a denial" % verb, not bare,
              repr(bare[:1]))
    for word in ("urgency", "importance"):
        hits = sentences_with(word, src)
        bare = [h for h in hits
                if not any(n in re.sub(r"\s+", " ", h).lower() for n in NEG)]
        check("[-] no unqualified %r anywhere" % word, not bare, repr(bare[:1]))
    check("[+] ...and the scan can tell the two apart (control)",
          not [h for h in sentences_with("x", "we recommend x.")
               if any(n in h.lower() for n in NEG)]
          and bool(sentences_with("recommend", "we recommend x.")))
    check("each item shows the ranks its trigger came from",
          "bwtrig mine" in q and "bwtrig pw" in q and "bwtrig av" in q)

    print("\n20. COMPARISON RENDERS ONLY SUPPORTED FIELDS")
    c = src[src.index("function renderCompare()"):]
    c = c[:c.index("\nfunction ")]
    check("both teams are chosen by the user, none auto-selected",
          "bwcA" in c and "bwcB" in c and "auto" not in c.lower())
    check("nothing is compared until both are chosen", "if (!ta || !tb)" in c)
    for lab in ("My ballot", "My last saved", "POWER", "AVCA poll",
                "Record 2026", "Last result", "Next match", "Projection"):
        check("compares %r" % lab, "'" + lab + "'" in c)
    # bwCmpRow is where a value is rendered, so that is where the honest
    # fallback lives -- not in renderCompare, which only assembles rows.
    row_fn = src[src.index("function bwCmpRow"):]
    row_fn = row_fn[:row_fn.index("\nfunction ")]
    check("a missing value says so rather than showing a zero",
          "not available" in row_fn, "checked bwCmpRow")
    check("a missing head-to-head is stated",
          "have not met in the records" in c)
    # ⚠ MOST HEAD-TO-HEAD ON FILE IS LAST SEASON. Presenting a 2025 meeting as
    # evidence about 2026 without saying so would be the worst thing here.
    check("a prior-season head-to-head names its season",
          "season, not this one" in c)
    check("[-] no generated scouting language",
          all(x not in c.lower() for x in ("case for", "case against",
                                           "momentum", "should win")))
    check("both teams link into the routed team pages",
          c.count("routeFor('teams'") == 2)

    print("\n21. COMPARISON IS AGAINST CODY'S SAVED BALLOT, NOT POWER")
    b = src[src.index("function renderBriefing()"):]
    b = b[:b.index("\nfunction ")]
    check("the briefing reads the last SAVED ballot", "bwLastSaved()" in b)
    check("...and movement is measured from it, not from POWER",
          "prev.teams" in b and "TEAMS[n].rank" not in b.split("Moved in your")[0][-400:])
    check("an honest first-ballot state exists", "None yet" in b)
    check("results are only counted when a DATE proves it",
          "function bwResultsSince" in src and "g.d >= day" in src)
    check("...and the copy says so",
          "no completed match is dated after your save" in b)

    print("\n22. HISTORY IS APPEND-ONLY AND REOPENING IS READ-ONLY")
    ro = src[src.index("function bwOpenArchived"):]
    ro = ro[:ro.index("\nfunction ")]
    check("the archive view renders into its own container", "'bwro'" in ro)
    check("[-] it contains no input, textarea or save control",
          all(x not in ro for x in ("<input", "<textarea", "bwSave(", "bwLocalSave")))
    check("[-] ...and never writes to the working ballot",
          "BW.teams" not in ro and "bwRenumber" not in ro)
    check("it says plainly that nothing writes back",
          "nothing here writes back" in ro)
    check("the working ballot still saves by append only",
          "bwSave" in src)

    print("\n23. THE EXPORT IS STILL ONLY HIS BALLOT AND HIS NOTES")
    t = src[src.index("function bwText()"):]
    t = t[:t.index("\nfunction ")]
    check("[-] the copy adds no branding", "wvb" not in t.lower()
          and "hub" not in t.lower())
    check("[-] ...and no generated commentary",
          all(x not in t.lower() for x in ("power", "avca", "because",
                                           "our model")))
    check("it carries the author's own summary", "summary" in t)

    print("\n24. MY BOARD IS PRIVATE, LOCAL, AND NEVER FILLS ITSELF")
    MB_MARKS = ("MYBOARD-HTML-BEGIN", "MYBOARD-CSS-BEGIN", "MYBOARD-JS-BEGIN",
                "wvb.myboard", "MB_KEY", "mbToggle", "mbRenderPanel",
                "mbControl", "mbClear", "mbpanel", "mbrow", "mbbtn",
                "data-mb", "mbFindMatch", "mbSyncControls")
    if os.path.exists(pub):
        ph3 = open(pub, encoding="utf-8").read()
        # ⚠ SUBSTRING MATCHING HITS REAL DATA. "mbrow" is inside the player
        # surname "Stambrowska", exactly as ".bwr" was inside ".bwrap". Match
        # each marker as a whole token.
        def tok(x, doc):
            return re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(x) +
                             r"(?![A-Za-z0-9_-])", doc) is not None
        left = [x for x in MB_MARKS if tok(x, ph3)]
        check("no My Board code, markup, css or storage key is published",
              not left, str(left[:5]))
        check("...and the panel host is gone too", 'id="mbpanel"' not in ph3)
        # the guarded call is allowed: it is how the public build stays quiet
        check("[+] the public build only carries a typeof guard",
              ph3.count("typeof mbRenderAll === 'function'") >= 1)
    if os.path.exists(priv):
        vh3 = open(priv, encoding="utf-8").read()
        missing = [x for x in MB_MARKS if not tok(x, vh3)]
        check("[+] ...and the PRIVATE page has all of it", not missing,
              str(missing[:4]))

    print("\n25. THE WATCHLIST REACHES NOTHING ELSE")
    # ⚠ STRUCTURAL. The board lives in localStorage and nowhere else -- no file,
    # no endpoint, no backup, no payload, no model input.
    mb = src[src.index("/* MYBOARD-JS-BEGIN */"):]
    mb = mb[:mb.index("/* MYBOARD-JS-END */")]
    for bad_s in ("fetch(", "/api/", "XMLHttpRequest", "ballots_", "ballot.py",
                  "BW.teams", "bwSave", "bwLocalSave", "PLAYERS", "rating",
                  "projection"):
        check("[-] My Board never touches %r" % bad_s, bad_s not in mb)
    check("it stores in localStorage only",
          "localStorage" in mb and mb.count("localStorage") <= 4)
    for fn in ("scripts/ballot.py", "scripts/ballot_backup.py",
               "scripts/digby.py", "scripts/rating_2025.py",
               "scripts/project_2026.py", "scripts/predict_2026.py",
               "scripts/simulate_season_2026.py", "scripts/digby_top25.py"):
        fp = os.path.join(REPO, fn)
        if not os.path.exists(fp):
            continue
        body = open(fp, encoding="utf-8").read()
        hit = [w for w in ("myboard", "MY_BOARD", "watchlist") if w in body]
        check("%s knows nothing of a watchlist" % os.path.basename(fn),
              not hit, str(hit))

    print("\n26. NOTHING IS EVER ADDED FOR HIM")
    check("the board starts empty", "let MB = [];" in mb)
    check("[-] it is never seeded from the ballot",
          "BW_HIST" not in mb and "bwRanked" not in mb)
    check("[-] ...nor from a ranking", "rank26" not in mb and "avca" not in
          mb.split("function mbRow")[0])
    check("adding is an explicit press", "mbToggle(b.dataset.mb)" in mb)
    check("clearing asks first", "window.confirm(" in mb)
    check("...and says what it will do", "removes all" in mb)

    print("\n27. IT FAILS SOFT AND STAYS HONEST")
    check("storage failure is caught", "catch (e)" in mb and "MB_OK = false" in mb)
    check("...and is explained rather than looking broken",
          "not letting the page" in mb)
    check("a watched team with no match says so",
          "No match in the current window" in mb)
    # strip comments first: the block explains that it never fabricates a
    # scoreline, and the explanation must not read as the violation.
    mb_code = re.sub(r"/\*.*?\*/", "", mb, flags=re.S)
    mb_code = re.sub(r"//.*", "", mb_code)
    check("[-] never invents a fabricated scoreline or placeholder time",
          all(x not in mb_code for x in ("'0-0'", '"0-0"', "'TBD'", '"TBD"')))
    check("[+] ...and the control-stripping actually removed something",
          len(mb_code) < len(mb))
    check("state comes from the shared matchState()", "matchState(" in mb)
    check("rank context is labelled POWER or AVCA",
          "POWER #" in mb and "AVCA #" in mb)
    check("every row routes to a match or a team",
          "'#/match-desk/'" in mb and "routeFor('teams'" in mb)

    print("\n28. STILL FIVE PRIMARY DESTINATIONS")
    if os.path.exists(priv):
        prim2 = re.findall(r'<button role="tab"[^>]*data-v="([a-z0-9]+)"',
                           open(priv, encoding="utf-8").read())
        check("no sixth primary tab was added", len(prim2) == 5, str(prim2))
        check("...and My Board is not a route",
              "'myboard'" not in src.split("ROUTE_OF_VIEW")[1][:400])

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
