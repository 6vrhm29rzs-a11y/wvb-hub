#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Cody's notes log and the local backup (2026-09-13).

He asked for a place his notes are logged "so i know you didn't forget it".
These are the checks that make that claim structurally true rather than a
promise: his words are stored verbatim, an item can never quietly stop being
mentioned, the file is append-only, the whole feature is private, and the
backup refuses to copy a credential.

Run: python3 scripts/test_notes_log.py -- no network.
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:110]))
    if not ok:
        FAILS.append(label)


def _code_only(src):
    """Python source minus comments and docstrings (the recurring lesson:
    a check that matches the COMMENT documenting its own rule)."""
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


def _repo_bodies_contaminated():
    """True if this suite's fixture text landed in the REAL handoff/msg.

    ⚠ AND THE REAL FOLDER MAY NOT EXIST. handoff/ is gitignored, so in CI --
    and in any fresh checkout -- there is nothing to contaminate and
    os.listdir raised FileNotFoundError, killing the suite. That is the
    SECOND gitignored path in this file to do it: the first (the notes log)
    was fixed this morning, and fixing it simply let the suite run far enough
    to hit this one. Patching the line the error names is not the same as
    auditing the file, which is what should have happened the first time.
    No folder means no contamination is possible, which is the honest answer
    rather than a skipped check.
    """
    d = os.path.join(REPO, "handoff", "msg")
    if not os.path.isdir(d):
        return False
    return any(f.startswith("CL-0001")
               and os.path.getsize(os.path.join(d, f)) < 100
               for f in os.listdir(d))


def main():
    import notes_log as NL

    print("1. THE LEDGER BEHAVES -- RUN AGAINST A THROWAWAY FILE")
    tmp = tempfile.mkdtemp()
    real = NL.PATH
    NL.PATH = os.path.join(tmp, "notes.jsonl")
    try:
        VERBATIM = ("thoughts: the 'record' column looks wrong\nand a second "
                    "line with  odd   spacing & an <angle> bracket")
        nid = NL.add("thought", VERBATIM, "a topic")
        got = NL.load()[0]
        # ⚠ VERBATIM MEANS BYTE-FOR-BYTE. Newlines, runs of spaces and
        # punctuation all survive; a store that normalises whitespace is a
        # store that has rewritten what he said.
        check("his text is stored byte-for-byte", got["text"] == VERBATIM,
              repr(got["text"])[:80])
        check("a new note starts at status 'logged'", got["status"] == "logged")
        check("...and says nothing happened yet", got["response"] == "")

        NL.set_status(nid, "in_progress", "started")
        NL.set_status(nid, "done")          # status only, no note
        got = NL.load()[0]
        # ⚠ LAST-WINS PER FIELD, NOT PER ROW. An update carrying only a status
        # must not blank a response written by an earlier update.
        check("a status-only update keeps the earlier response",
              got["status"] == "done" and got["response"] == "started",
              (got["status"], got["response"]))
        check("the original note text is untouched by updates",
              got["text"] == VERBATIM)
        check("every change is kept in history",
              len(got["history"]) == 2, got["history"])

        rows = [json.loads(l) for l in io.open(NL.PATH, encoding="utf-8")]
        # ⚠ APPEND-ONLY: three writes, three rows, and the first is still the
        # note. A store that rewrote in place would have fewer.
        check("[NEG] the file is append-only -- 3 writes, 3 rows",
              len(rows) == 3 and rows[0]["op"] == "note", len(rows))

        try:
            NL.set_status(nid, "declined")
            check("[NEG] a decline without a reason is refused", False)
        except SystemExit:
            check("[NEG] a decline without a reason is refused", True)
        try:
            NL.set_status(nid, "sorted-out")
            check("[NEG] an unknown status is refused", False)
        except SystemExit:
            check("[NEG] an unknown status is refused", True)
        try:
            NL.add("thought", "   ")
            check("[NEG] an empty note is refused", False)
        except SystemExit:
            check("[NEG] an empty note is refused", True)

        c = NL.counts(NL.load())
        check("counts reconcile with the notes themselves",
              c["total"] == len(NL.load())
              and c["open"] + c["done"] + c["declined"] == c["total"],
              c)
    finally:
        NL.PATH = real
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n2. THE FEATURE IS PRIVATE IN EVERY LAYER")
    bsrc = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                   encoding="utf-8").read()
    for a, b in (("<!-- NOTES-HTML-BEGIN -->", "<!-- NOTES-HTML-END -->"),
                 ("/* NOTES-ROUTE-BEGIN */", "/* NOTES-ROUTE-END */"),
                 ("<!-- NOTES-MENU-BEGIN -->", "<!-- NOTES-MENU-END -->"),
                 ("/* NOTES-CSS-BEGIN */", "/* NOTES-CSS-END */")):
        check("%s is fenced and the strip removes it" % a.strip("<!-/* "),
              a in bsrc and b in bsrc
              and bsrc.count('("%s", "%s")' % (a, b)) == 1,
              (a in bsrc, b in bsrc))
    check("the renderer returns nothing on the public build",
          "if PUBLIC:" in bsrc.split("def notes_log_html")[1][:1200])

    priv = os.path.join(REPO, "Cody", "START-HERE.html")
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(priv):
        page = io.open(priv, encoding="utf-8").read()
        check("the private page carries the tab", 'id="v-notes"' in page)
        notes = NL.load()
        # ⚠ THE VERBATIM PROMISE IS ABOUT CODY'S NOTES. A note Claude wrote
        # into the log (an observation surfaced from expiring evidence) is
        # his record but not his words, and this check is what caught the
        # first one going in unattributed.
        check("every note records who wrote it",
              all(n.get("by") for n in NL.load()),
              [n["id"] for n in NL.load() if not n.get("by")])
        _claude = [n for n in NL.load() if n.get("by") != "cody"]
        if _claude and os.path.exists(priv):
            _pg = io.open(priv, encoding="utf-8").read()
            check("[NEG] a note Claude wrote is LABELLED on the page, never "
                  "passed off as Cody's", "not Cody" in _pg)
        notes = [n for n in notes if (n.get("by") or "cody") == "cody"]
        # ⚠ AND ONLY IF THE PAGE IS NEWER THAN THE LOG. This check failed
        # every time a note was logged before the next rebuild -- which is
        # the normal order of events, not a regression. A guard that depends
        # on build order cries wolf exactly like one that depends on the
        # calendar. Say which case it is.
        # ⚠ AND THE LOG ITSELF MAY BE ABSENT. Cody/data/ is gitignored, so in
        # CI (and any fresh checkout) build_hub writes the private page while
        # the notes log never exists -- this getmtime raised FileNotFoundError
        # and killed the whole suite, which is an ENVIRONMENT pin of exactly
        # the kind test_external_refs already learned to state rather than
        # crash on. No log means no notes to render; say so and carry on.
        _logp = os.path.join(REPO, "Cody", "data", "notes_log.jsonl")
        if not os.path.exists(_logp):
            check("no notes log in this checkout -- asserting the "
                  "honest-absence mode instead (not a failure)", True)
            notes = []
        _stale = (os.path.exists(_logp)
                  and os.path.getmtime(_logp) > os.path.getmtime(priv))
        if _stale:
            check("page predates the newest note -- rebuild to verify "
                  "verbatim rendering (not a failure)", True)
            notes = []
        if notes:
            n = notes[0]
            # the rendered page must contain his words, not a paraphrase
            import html as _h
            frag = _h.escape(n["text"].strip().split("\n")[0][:48],
                             quote=False)
            check("...and his words appear on it verbatim",
                  frag in page or frag.replace("&#x27;", "'") in page,
                  frag[:60])
    if os.path.exists(pub):
        pubtxt = io.open(pub, encoding="utf-8").read()
        # ⚠ GREP THE DATA, NOT THE MARKUP -- the recurring rule. A stripped
        # section with his sentences still in a payload is still published.
        check("[NEG] the public build carries no trace of the log",
              'v-notes' not in pubtxt and 'nlsaid' not in pubtxt
              and 'notes_log' not in pubtxt)
        notes = NL.load()
        leak = [n["id"] for n in notes
                if n.get("text") and n["text"].strip()[:40] in pubtxt]
        check("[NEG] no note text reaches the public page", not leak, leak)
        # ⚠ A STALE PUBLIC FILE WOULD PASS THIS VACUOUSLY. The tab is new,
        # so an untouched older build carries no trace for reasons that have
        # nothing to do with the strip working. Say which case this is.
        # ⚠ pub IS TRACKED AND priv IS NOT, so "public present, private
        # absent" is a real state -- any fresh clone before a build. Comparing
        # their mtimes then raises instead of reporting.
        if os.path.exists(priv) and os.path.getmtime(pub) < os.path.getmtime(priv):
            print("      (note: the public build on disk predates the "
                  "private one -- the fence checks above are what prove "
                  "the strip, not this file)")
    else:
        check("no public build on disk to check (private-only tree)", True)

    print("\n3. THE BACKUP REFUSES A CREDENTIAL, AND KEEPS ONLY THE "
          "IRREPLACEABLE")
    bl = io.open(os.path.join(REPO, "scripts", "backup_local.py"),
                 encoding="utf-8").read()
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import backup_local as BL
    for name in ("anthropic_key.txt", "gmail_app_password.txt",
                 "oauth_token.json", "client.pem"):
        check("[NEG] %s is never copied" % name, BL._secretish(name))
    for name in ("notes_log.jsonl", "my_ballots.jsonl",
                 "tv_listings_2026.txt"):
        check("%s is copied" % name, not BL._secretish(name))
    code = _code_only(bl)
    # ⚠ A DERIVED ARTIFACT MUST NOT BE BACKED UP. data/*.json rebuilds from
    # data/raw plus the scripts, both of which git carries; a copy of an
    # answer is a copy that will one day be restored over a newer one.
    # ⚠ ASK GIT, DO NOT PATTERN-MATCH THE PATH. The first version tested
    # for the literal "Cody/" and failed the moment two legitimate sources
    # were added outside it (the ChatGPT drop folder and handoff/) -- a guard
    # asserting the SHAPE of the answer rather than the rule. The rule is:
    # every backed-up path must be one git is deliberately not carrying.
    import subprocess as _sp2
    # ⚠ AND THE RULE CAN ONLY BE ASKED WHERE GIT CAN ANSWER. The fresh-checkout
    # sandbox is a tar of `git ls-files` with NO .git directory, so
    # check-ignore exits 128 there and every path reads as "not ignored" --
    # failing a correct tree. That is the THIRD environment pin in this suite
    # (the notes log, handoff/msg, and now git itself); the pattern is that a
    # guard which consults something outside the source tree must say what it
    # does when that thing is absent.
    _isrepo = _sp2.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO,
                       stdout=_sp2.DEVNULL, stderr=_sp2.DEVNULL).returncode == 0
    if not _isrepo:
        check("no git repo in this checkout -- cannot ask whether the backup "
              "paths are ignored (not a failure)", True)
    else:
        not_ignored = []
        for pat in BL.SOURCES:
            probe = pat.replace("*", "probe")
            r = _sp2.run(["git", "check-ignore", "-q", probe], cwd=REPO)
            if r.returncode != 0:
                not_ignored.append(pat)
        check("it backs up only paths git is deliberately NOT carrying",
              not not_ignored, not_ignored)
    check("...and never the derived data/ artifacts",
          not any(pat.startswith("data/") and "ballots" not in pat
                  for pat in BL.SOURCES), BL.SOURCES)
    # ⚠ ANCHOR ON THE CALL, NOT ON THE WORD. The first version searched the
    # whole file for "commit" and failed on the PRINTED SENTENCE "local
    # commit(s) are NOT on origin" -- a guard matching prose that documents
    # the rule it enforces, for the thirteenth time in this codebase. Git
    # actions are Cody's to run; this script may only read.
    check("[NEG] it never runs git commit or push itself",
          '_git("commit"' not in code and '_git("push"' not in code
          and "subprocess.run((\"git\",)" in code)
    check("the retention count is a named constant", "KEEP" in code)
    check("local_refresh takes the snapshot",
          "backup_local.py" in io.open(
              os.path.join(REPO, "scripts", "local_refresh.py"),
              encoding="utf-8").read())

    print("\n4. THE HANDOFF RECORD -- SHARED, APPEND-ONLY, AND HONEST "
          "ABOUT WHO WROTE WHAT")
    import handoff as H
    tmp = tempfile.mkdtemp()
    saved = (H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS)
    H.ROOT = tmp
    H.LEDGER = os.path.join(tmp, "messages.jsonl")
    H.BODIES = os.path.join(tmp, "msg")
    H.INBOX = os.path.join(tmp, "inbox")
    H.STATUS = os.path.join(tmp, "STATUS.md")
    try:
        mid = H.post("claude", "a subject", "line one\n\nline two")
        check("a posted message gets a seat-stamped id",
              mid.startswith("CL-"), mid)
        m = H.load()[0]
        check("the body is a file, kept verbatim",
              H.body(m) == "line one\n\nline two\n", repr(H.body(m)))
        check("a new message has no outcome until somebody sets one",
              m["outcome"] == "")
        H.ack(mid, "queued", "will do after the sweep")
        H.ack(mid, "completed", "done")
        m = H.load()[0]
        check("outcomes append and the latest wins",
              m["outcome"] == "completed" and len(m["acks"]) == 2)
        check("the original body is untouched by an outcome",
              H.body(m) == "line one\n\nline two\n")
        for bad_outcome in ("declined", "blocked"):
            try:
                H.ack(mid, bad_outcome)
                check("[NEG] %s without a reason is refused" % bad_outcome,
                      False)
            except SystemExit:
                check("[NEG] %s without a reason is refused" % bad_outcome,
                      True)
        try:
            H.ack(mid, "acknowledged-ish")
            check("[NEG] an unknown outcome is refused", False)
        except SystemExit:
            check("[NEG] an unknown outcome is refused", True)

        # ⚠ THE CHECK THAT CAUGHT A REAL FALSE CLAIM ON DAY ONE. The status
        # file said "two-way exchange verified: yes" because a CX- row
        # existed -- a row I had filed MYSELF from a file Cody dropped. Cody
        # said explicitly not to assume the return leg works until both sides
        # verify it, so the test is provenance, never the row's existence.
        H.post("codex", "filed for it", "body", origin="adopted_by_other")
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("[NEG] a message filed ON a seat's behalf never counts as "
              "that seat writing here",
              "Two-way exchange verified: **NO.**" in st,
              [l for l in st.splitlines() if "Two-way" in l][:1])
        # the inbox door: a seat that can only write a FILE can still take part
        if not os.path.isdir(H.INBOX):
            os.makedirs(H.INBOX)
        io.open(os.path.join(H.INBOX, "codex-real-reply.md"), "w",
                encoding="utf-8").write("I wrote this myself.")
        got = H.ingest()
        check("the inbox door adopts a dropped file", len(got) == 1, got)
        cx = [x for x in H.load() if x["seat"] == "codex"
              and x.get("origin") == "inbox_claimed"]
        # ⚠ THESE TWO CHECKS PINNED THE RULE CODEX'S REVIEW OVERTURNED, and
        # they failed the moment the fix landed -- correctly. Adoption from
        # the inbox records a CLAIM of authorship (a filename), which is not
        # proof, and it does NOT verify the return leg. Section 5b carries
        # the controls; these now assert the corrected invariant.
        check("...and records the seat's CLAIM, not proof of authorship",
              len(cx) == 1, [(x["id"], x.get("origin")) for x in cx])
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("[NEG] ...which is NOT enough to verify the return leg",
              "Two-way exchange verified: **NOT YET.**" in st,
              [l for l in st.splitlines() if "Two-way" in l][:1])
        check("the dropped original is kept beside the adopted message",
              any(f.endswith(".original") for f in os.listdir(H.BODIES)))
        rows = [json.loads(l) for l in io.open(H.LEDGER, encoding="utf-8")]
        check("[NEG] the ledger is append-only -- nothing was rewritten",
              sum(1 for r in rows if r.get("op") == "msg") == 3
              and rows[0]["op"] == "msg", len(rows))
        try:
            H.post("claude", "empty", "   ")
            check("[NEG] an empty message is refused", False)
        except SystemExit:
            check("[NEG] an empty message is refused", True)
        # ⚠ THE CONTROL FOR THE CONTAMINATION THIS SUITE ITSELF CAUSED. An
        # earlier version of handoff.py built the body path from the repo
        # root rather than from BODIES, so this very test -- pointed at a
        # temp directory -- overwrote two real message bodies with its
        # fixture text. Two things are asserted now: the module writes where
        # it is pointed, and a body that already exists is never rewritten.
        check("[NEG] bodies are written where the module is pointed, not "
              "into the repo's own handoff folder",
              all(os.path.dirname(os.path.abspath(
                  os.path.join(H.BODIES, os.path.basename(x["body_file"]))))
                  == os.path.abspath(H.BODIES) for x in H.load())
              and not _repo_bodies_contaminated())
        # ⚠ PRE-CREATE THE EXACT FILE THE NEXT POST WILL TARGET. A control
        # that cannot actually collide proves nothing -- the first version of
        # this one copied a body to an id `next_id` would never return, so it
        # tested the happy path and called it a control.
        nxt = H.next_id("claude")
        target = os.path.join(H.BODIES, "%s.md" % nxt)
        io.open(target, "w", encoding="utf-8").write("already here")
        try:
            H.post("claude", "would clobber", "new text")
            check("[NEG] an existing body file is never overwritten", False,
                  "post() wrote over %s" % nxt)
        except SystemExit:
            check("[NEG] an existing body file is never overwritten",
                  io.open(target, encoding="utf-8").read() == "already here")
    finally:
        H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n5. AWAY/HOME MODE IS DECLARED, NEVER INFERRED")
    tmp2 = tempfile.mkdtemp()
    saved2 = (H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS)
    H.ROOT = tmp2
    H.LEDGER = os.path.join(tmp2, "messages.jsonl")
    H.BODIES = os.path.join(tmp2, "msg")
    H.INBOX = os.path.join(tmp2, "inbox")
    H.STATUS = os.path.join(tmp2, "STATUS.md")
    try:
        m, at, note = H.current_mode()
        check("with nothing declared the mode is UNDECLARED, not 'home'",
              m is None, m)
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("...and the status file says so in those words",
              "UNDECLARED" in st)
        # ⚠ THE CONTROL FOR THE MISTAKE I MADE MYSELF. The first mode row in
        # the real ledger was one I wrote, inferring "home" because Cody was
        # in the conversation on a Mac. He asked for his LAST DECLARED mode
        # and said not to infer his device or location. A row from another
        # seat is kept -- append-only -- and must not count.
        H.set_mode("home", "Claude guessed this", by="claude")
        m, at, note = H.current_mode()
        check("[NEG] a mode another seat wrote is NOT a declaration",
              m is None, m)
        H.set_mode("away", "on my phone", by="cody")
        m, at, note = H.current_mode()
        check("a mode Cody declares IS one, with its timestamp",
              m == "away" and bool(at), (m, at))
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("...and away mode states that queued work is not waived",
              "never released with the requirement waived" in st)
        try:
            H.set_mode("travelling")
            check("[NEG] an unknown mode is refused", False)
        except SystemExit:
            check("[NEG] an unknown mode is refused", True)

        H.log_work("a change", "queued_for_review",
                   tests="suite x", review_ask="check y")
        H.log_work("another", "tested", tests="suite z")
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("the catch-up separates self-tested from independently reviewed",
              "self-review only" in st and "independently reviewed" in st)
        check("...and lists what is waiting on a review before release",
              "Waiting on an independent look before release" in st)
        try:
            H.log_work("bad", "reviewed")
            check("[NEG] a 'reviewed' entry must name who and what", False)
        except SystemExit:
            check("[NEG] a 'reviewed' entry must name who and what", True)
        try:
            H.log_review("codex", [], "")
            check("[NEG] a review with no scope is refused", False)
        except SystemExit:
            check("[NEG] a review with no scope is refused", True)
        H.log_review("codex", ["CL-0001"], "abc1234", "read it")
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("a scoped review is recorded with its ids and revision",
              "CL-0001" in st and "abc1234" in st)
    finally:
        H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS = saved2
        shutil.rmtree(tmp2, ignore_errors=True)

    print("\n5b. A FILENAME IS A CLAIM OF AUTHORSHIP, NOT PROOF OF IT")
    # Codex review, 2026-09-13: ingest() defaulted the seat to "codex" for any
    # unrecognised filename and gave it inbox provenance, so an ordinary
    # dropped file could claim Codex posted it -- and that counted toward
    # "two-way exchange verified". A default that attributes authorship
    # fabricates evidence.
    tmp4 = tempfile.mkdtemp()
    saved4 = (H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS)
    H.ROOT, H.LEDGER = tmp4, os.path.join(tmp4, "messages.jsonl")
    H.BODIES, H.INBOX = os.path.join(tmp4, "msg"), os.path.join(tmp4, "inbox")
    H.STATUS = os.path.join(tmp4, "STATUS.md")
    try:
        if not os.path.isdir(H.INBOX):
            os.makedirs(H.INBOX)
        io.open(os.path.join(H.INBOX, "random-notes.md"), "w",
                encoding="utf-8").write("a stray file nobody claimed")
        got = H.ingest()
        seats = [m["seat"] for m in H.load()]
        check("[NEG] an unrecognised filename is NOT adopted as codex",
              "codex" not in seats, seats)
        check("[NEG] ...it is quarantined, not deleted and not guessed",
              os.path.exists(os.path.join(H.INBOX, "unrecognised",
                                          "random-notes.md")))
        check("...and the run reports it rather than staying silent",
              got and got[0][0] is None, got)

        io.open(os.path.join(H.INBOX, "codex-reply.md"), "w",
                encoding="utf-8").write("anyone could have named this file")
        H.ingest()
        cx = [m for m in H.load() if m["seat"] == "codex"]
        check("a codex-named file IS adopted, as a CLAIM",
              len(cx) == 1 and cx[0]["origin"] == "inbox_claimed",
              [(m["id"], m.get("origin")) for m in cx])
        st = io.open(H.write_status(), encoding="utf-8").read()
        # ⚠ THE CONTROL FOR THE EXACT HOLE: a relayed codex-*.md must NOT
        # verify the return leg.
        check("[NEG] a codex-named file does NOT verify two-way exchange",
              "Two-way exchange verified: **NOT YET.**" in st,
              [l for l in st.splitlines() if "Two-way" in l][:1])
        try:
            H.attest(cx[0]["id"], "claude")
            check("[NEG] claude may never attest authorship", False)
        except SystemExit:
            check("[NEG] claude may never attest authorship", True)
        try:
            H.attest("CX-9999", "cody")
            check("[NEG] attesting a message that does not exist is refused",
                  False)
        except SystemExit:
            check("[NEG] attesting a message that does not exist is refused",
                  True)
        H.attest(cx[0]["id"], "cody", "I watched Codex write it")
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("an explicit human attestation DOES verify the return leg",
              "Two-way exchange verified: yes" in st,
              [l for l in st.splitlines() if "Two-way" in l][:1])
    finally:
        H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS = saved4
        shutil.rmtree(tmp4, ignore_errors=True)

    print("\n5b2. ONE VERIFICATION RULE, READ BY BOTH SURFACES")
    # Codex review, 2026-09-13: build_hub's handoff_html() kept its OWN
    # self_posted/inbox_ingest test, so after the acknowledgment fix STATUS.md
    # said NOT YET while the private page still said "yes" -- one fact, two
    # answers (R4). Both now read handoff.verification_status().
    bsrc2 = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                    encoding="utf-8").read()
    bcode2 = _code_only(bsrc2)
    check("the page reads the shared helper",
          "HO.verification_status()" in bcode2)
    check("[NEG] the page keeps NO second copy of the rule",
          "cx_write" not in bcode2
          and "inbox_ingest" not in bcode2
          and "self_posted" not in bcode2)
    check("the page states acknowledgment is not authenticated identity",
          "not authenticated identity" in bsrc2)
    hsrc0 = io.open(os.path.join(REPO, "scripts", "handoff.py"),
                    encoding="utf-8").read()
    check("...and so does the helper itself",
          "not authenticated identity" in hsrc0
          and "caller-supplied" in hsrc0)

    tmp5 = tempfile.mkdtemp()
    saved5 = (H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS)
    H.ROOT, H.LEDGER = tmp5, os.path.join(tmp5, "messages.jsonl")
    H.BODIES, H.INBOX = os.path.join(tmp5, "msg"), os.path.join(tmp5, "inbox")
    H.STATUS = os.path.join(tmp5, "STATUS.md")
    try:
        if not os.path.isdir(H.INBOX):
            os.makedirs(H.INBOX)
        io.open(os.path.join(H.INBOX, "codex-note.md"), "w",
                encoding="utf-8").write("claimed, not confirmed")
        H.ingest()
        vs = H.verification_status()
        st = io.open(H.write_status(), encoding="utf-8").read()
        # BOTH surfaces read this one dict, so asserting it asserts both.
        check("[NEG] an unconfirmed message is UNVERIFIED in the shared rule",
              vs["verified"] is False, vs["plain"])
        check("[NEG] ...and the status file says so",
              "Two-way exchange verified: **NOT YET.**" in st)
        cx = [m for m in H.load() if m["seat"] == "codex"][0]
        H.attest(cx["id"], "cody", "confirmed by hand")
        vs2 = H.verification_status()
        st2 = io.open(H.write_status(), encoding="utf-8").read()
        check("a valid explicit acknowledgment flips the shared rule",
              vs2["verified"] is True and vs2["attested"] == cx["id"],
              (vs2["verified"], vs2["attested"]))
        check("...and the status file updates with it",
              "Two-way exchange verified: yes" in st2)
        check("...and the shared rule still says it is self-declared",
              "self-declared" in vs2["detail"] and "self-declared" in st2)
    finally:
        H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS = saved5
        shutil.rmtree(tmp5, ignore_errors=True)

    print("\n5c. TIMESTAMPS KEEP THEIR OFFSETS (offline)")
    # Codex review: dt[:19] discarded the zone and replace(tzinfo=utc)
    # assumed UTC, so an explicit -05:00 would have become a five-hour FALSE
    # disagreement -- manufactured by the very module whose job is flagging
    # real ones. Measured contract: 36 of 36 samples across 18 hosts emit Z.
    import fixture_time_check as FTC
    base = FTC.parse_dt("2026-11-21T01:00:00.000000Z")
    check("a Z timestamp parses", base is not None)
    for txt, label in (("2026-11-21T01:00:00Z", "bare Z"),
                       ("2026-11-21T01:00:00+00:00", "+00:00"),
                       ("2026-11-20T20:00:00-05:00", "-05:00"),
                       ("2026-11-20T20:00:00-0500", "-0500 no colon"),
                       ("2026-11-21T02:00:00+01:00", "+01:00")):
        got = FTC.parse_dt(txt)
        check("%s is the SAME INSTANT as the Z form" % label,
              got is not None and got.timestamp() == base.timestamp(),
              None if got is None else got.timestamp())
    check("[NEG] a timezone-NAIVE value is unresolved, never assumed UTC",
          FTC.parse_dt("2026-11-21T01:00:00") is None)
    check("[NEG] garbage is unresolved", FTC.parse_dt("not a date") is None
          and FTC.parse_dt("") is None)
    fsrc = io.open(os.path.join(REPO, "scripts", "fixture_time_check.py"),
                   encoding="utf-8").read()
    fcode = _code_only(fsrc)
    check("[NEG] the truncate-and-assume-UTC pattern is gone",
          "dt[:19]" not in fcode
          and "replace(\n                tzinfo=datetime.timezone.utc)"
          not in fcode)
    check("unresolved timestamps are counted in the artifact, not dropped",
          "timestamps_unresolved" in fcode)

    print("\n6. A REVIEW IS A STATEMENT ABOUT BYTES, AND DRIFT IS DETECTED")
    # Codex, via Cody (CY-0001): "the ledger references the existing commit
    # while the reviewed changes are uncommitted... Later edits must not
    # inherit an earlier review." Correct, and it was a real hole: a commit
    # hash says nothing about a working tree. The scope is now the sha256 of
    # every file in it, re-checked at render time.
    tmp3 = tempfile.mkdtemp()
    saved3 = (H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS)
    H.ROOT, H.LEDGER = tmp3, os.path.join(tmp3, "messages.jsonl")
    H.BODIES, H.INBOX = os.path.join(tmp3, "msg"), os.path.join(tmp3, "inbox")
    H.STATUS = os.path.join(tmp3, "STATUS.md")
    probe = os.path.join(tmp3, "probe.txt")
    try:
        io.open(probe, "w", encoding="utf-8").write("original")
        rel = os.path.relpath(probe, REPO)
        fp = H.fingerprint([rel])
        check("a fingerprint is a real sha256, not a commit hash",
              len(fp[rel]) == 64 and fp[rel] != H.base_commit(), fp[rel][:12])
        check("nothing has drifted while the bytes are unchanged",
              H.drift(fp) == [])
        io.open(probe, "a", encoding="utf-8").write("  edited later")
        # ⚠ THE CONTROL FOR THE EXACT HOLE CODEX NAMED.
        check("[NEG] an edited file drifts -- a later edit cannot inherit an "
              "earlier review", H.drift(fp) == [rel], H.drift(fp))
        os.remove(probe)
        check("[NEG] a DELETED file drifts too", H.drift(fp) == [rel])
        io.open(probe, "w", encoding="utf-8").write("original")
        check("restoring the exact bytes clears the drift", H.drift(fp) == [])

        H.log_work("scoped work", "queued_for_review", files=[rel])
        w = H.work_items()[-1]
        # ⚠ base_commit() IS `git rev-parse HEAD` AND RETURNS "" WITHOUT A
        # REPO -- which is exactly the fresh-checkout sandbox (a tar of
        # `git ls-files`, no .git). Asserting it is non-empty there fails a
        # correct tree. The FILE HASHES are the part that does not depend on
        # git and they are asserted unconditionally; the commit is asserted
        # only where git can supply one.
        _hasgit = bool(H.base_commit())
        check("a work entry records its file hashes",
              w["files"].get(rel) == fp[rel])
        if _hasgit:
            check("...and its base commit", bool(w.get("base_commit")))
        else:
            check("no git repo in this checkout -- base_commit is empty by "
                  "design, so it is not asserted (not a failure)", True)
        io.open(probe, "a", encoding="utf-8").write("moved again")
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("the status file REPORTS the drift rather than carrying the "
              "old verdict forward",
              "CHANGED SINCE LOGGED" in st and "no longer applies" in st)
        H.log_review("codex", ["CL-0001"], "", "read it", files=[rel])
        io.open(probe, "a", encoding="utf-8").write("and again")
        st = io.open(H.write_status(), encoding="utf-8").read()
        check("a completed review goes STALE when its files move",
              "STALE" in st)
        try:
            H.log_review("codex", [], "", "no scope at all")
            check("[NEG] a review with no scope of any kind is refused", False)
        except SystemExit:
            check("[NEG] a review with no scope of any kind is refused", True)
        check("an absent file is recorded as ABSENT, never silently skipped",
              H.fingerprint(["scripts/does_not_exist_xyz.py"])
              ["scripts/does_not_exist_xyz.py"] == "ABSENT")
    finally:
        H.ROOT, H.LEDGER, H.BODIES, H.INBOX, H.STATUS = saved3
        shutil.rmtree(tmp3, ignore_errors=True)

    hsrc = io.open(os.path.join(REPO, "scripts", "handoff.py"),
                   encoding="utf-8").read()
    hcode = _code_only(hsrc)
    # ⚠ NOTHING MAY INFER THE MODE. Cody named the three things: his device,
    # his location, Codex's availability. A scan for the machinery that would
    # be needed to guess any of them.
    # ⚠ CODE-SHAPED TOKENS ONLY. The first list carried the bare word "idle"
    # and matched the STATUS.md prose that says nothing reads an idle timer --
    # a guard failed by the sentence explaining the rule it enforces, for the
    # fourteenth time in this codebase, and this one could not be fixed by
    # stripping comments because the text is a real string literal the page
    # prints. An API name cannot appear by accident in a sentence.
    infer = [w for w in ("gethostname(", "platform.system", "psutil",
                         "getlogin(", "socket.", "geolocation",
                         "HIDIdleTime", "ioreg", "pmset")
             if w in hcode]
    check("[NEG] nothing in the handoff reads a device, a host or an idle "
          "timer", not infer, infer)
    check("the phone URL is read from Tailscale, not typed",
          "ts.net" not in hcode and "serve" in hcode.lower(),
          "a hard-coded tailnet name would one day be silently wrong")
    check("no polling loop or scheduled wakeup was built",
          "while True" not in hcode and "sched" not in hcode.lower()
          and "cron" not in hcode.lower())
    check("it states that a message is a proposal, not an instruction",
          "proposal, not an instruction" in hsrc)
    check("it records that it supersedes the Drive-only workflow for this pair",
          "SUPERSEDES THE DRIVE-ONLY" in hsrc.upper())
    # ⚠ THE RULE IS "NEVER WRITES WITH GIT", NOT "NEVER SAYS GIT". The first
    # version banned the substring "commit", which was right until the review
    # scope needed to record the BASE COMMIT it sat on -- a read. Reading
    # history is how a scope is anchored; writing it is Cody's alone. So the
    # check names the write verbs, and asserts the reads are the only ones
    # present. (`base_commit` the identifier is excluded before scanning, or
    # the ban matches the very function that performs the read.)
    hcode2 = re.sub(r"base_commit", "BASECMT", _code_only(hsrc))
    writes = [v for v in ("commit", "push", "add", "checkout", "reset",
                          "clean", "-f")
              if re.search(r'["\']%s["\']' % re.escape(v), hcode2)]
    check("[NEG] it runs no git WRITE -- reads only", not writes, writes)
    reads = set(re.findall(r'\["git",\s*"([a-z-]+)"', hcode2))
    check("...and the only git it runs at all is read-only",
          reads <= {"rev-parse", "ls-files", "status", "check-ignore",
                    "rev-list"}, sorted(reads))
    gi = io.open(os.path.join(REPO, ".gitignore"), encoding="utf-8").read()
    check("[NEG] handoff/ is gitignored", "\nhandoff/" in gi)
    import subprocess as _sp
    tracked = _sp.run(["git", "ls-files", "handoff"], cwd=REPO,
                      capture_output=True, text=True).stdout.strip()
    check("[NEG] and nothing under it has ever been committed",
          not tracked, tracked[:80])
    check("backup_local snapshots the handoff record",
          any("handoff" in pat for pat in BL.SOURCES), BL.SOURCES)
    # ⚠ THE MECHANISM ALWAYS; THE RENDERED OUTPUT ONLY WHEN THERE IS DATA.
    # handoff/ is gitignored, so on a CI checkout there is no handoff record
    # to render and asserting the heading fails a page that is behaving
    # correctly. Same shape as the exhibition-badge guard that broke at
    # midnight: check the branch exists always, check what it produced only
    # when the subject is actually present. (Fifth environment pin in this
    # file -- the rule is that a guard consulting anything outside the source
    # tree must say what it does when that thing is absent.)
    check("build_hub has the branch that renders the handoff record",
          "notes_log_html" in bsrc and "Claude and Codex" in bsrc)
    if os.path.exists(priv):
        page = io.open(priv, encoding="utf-8").read()
        if os.path.isdir(os.path.join(REPO, "handoff")):
            check("the notes tab renders the handoff record",
                  "Handoff &mdash; Claude and Codex" in page
                  or "Handoff \u2014 Claude and Codex" in page)
        else:
            check("no handoff record in this checkout -- nothing to render "
                  "(not a failure)", True)
    if os.path.exists(pub):
        pubtxt = io.open(pub, encoding="utf-8").read()
        # ⚠ GREP THE DATA. Bodies, ids and the seat names must all be absent.
        leak = [k for k in ("nlprov", "CX-0001", "CL-0001",
                            "Claude and Codex") if k in pubtxt]
        check("[NEG] no handoff trace reaches the public build", not leak, leak)

    print("")
    if FAILS:
        print("NOTES-LOG GUARDS FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL NOTES-LOG GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
