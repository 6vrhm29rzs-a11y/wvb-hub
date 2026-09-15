#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cody's notes, ideas and side research -- logged, statused, never lost.

Cody, 2026-09-13: "whenever i send you notes or ideas, you don't have to stop
what you're doing and change work paths. you can finish what you need to and
log my messages and notes somewhere to come back to later... maybe the site
needs a separate tab/page for my ideas and thoughts and things like that that
you log and mark to review later so i know you didn't forget it."

THE RULES THIS FILE ENFORCES, and why each one is here:

  1. HIS WORDS ARE STORED VERBATIM AND ARE NEVER REWRITTEN. A note is his
     claim, not mine. Summarising it into my own phrasing on the way in is
     how "I already captured that" becomes "I captured something else" --
     the same discipline the evidence ledgers use for a quoted source.
  2. EVERY NOTE CARRIES A STATUS, AND A DECLINE CARRIES A REASON. The point
     of the tab is that he can see nothing was forgotten; an item that
     quietly stops having anything said about it is exactly the failure.
  3. APPEND-ONLY. A status change appends an update row; the original note
     row is never edited. Resolution is last-wins per field per id, the
     same rule the crawl outputs use.
  4. PRIVATE. The file lives under Cody/, which is gitignored, because it is
     his own writing on a PUBLIC repo. scripts/backup_local.py is what keeps
     it durable instead of git.

Usage:
  python3 scripts/notes_log.py add --kind thought --topic "..." --text "..."
  python3 scripts/notes_log.py add --kind chatgpt --topic "..." --file note.txt
  python3 scripts/notes_log.py set n0007 --status done --note "shipped X"
  python3 scripts/notes_log.py list
"""

import argparse
import datetime
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(REPO, "Cody", "data", "notes_log.jsonl")

# ⚠ A CONTROLLED VOCABULARY, NOT FREE TEXT. Five states, each meaning one
# thing. "deferred" is deliberately distinct from "declined": deferred means
# not now and still his to call, declined means I am not doing it and the
# reason is on the row. A status outside this set is refused rather than
# stored, because a typo'd status would silently drop the note out of every
# count on the page.
STATUS = ("logged", "in_progress", "done", "deferred", "declined")
OPEN_STATUS = ("logged", "in_progress", "deferred")
STATUS_LABEL = {
    "logged": "logged — not looked at yet",
    "in_progress": "being worked on",
    "done": "done",
    "deferred": "not now — Cody's call",
    "declined": "not doing it",
}
# where the note came from. "chatgpt" is its own kind because those arrive as
# long third-party briefs that need evaluating rather than implementing.
KIND = ("thought", "chatgpt", "observation", "ask", "bug")
KIND_LABEL = {
    "thought": "thought",
    "chatgpt": "from ChatGPT",
    "observation": "watching the site",
    "ask": "ask",
    "bug": "something looked wrong",
}


def _now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()
    except Exception:
        return datetime.datetime.now().isoformat()


def _rows():
    if not os.path.exists(PATH):
        return []
    out = []
    for line in io.open(PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            # a malformed line is a defect in whatever wrote it; it is skipped
            # rather than raising, because one bad row must not hide the rest
            # of his notes behind a traceback.
            continue
    return out


def _append(row):
    d = os.path.dirname(PATH)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load():
    """Resolved notes, newest first. [] when the file does not exist.

    ⚠ THE RESOLUTION IS LAST-WINS PER FIELD, NOT PER ROW. An update that
    sets only the status must not blank the response note somebody wrote in
    an earlier update -- which is what replacing the whole record would do.
    """
    notes = {}
    order = []
    for r in _rows():
        nid = str(r.get("id") or "")
        if not nid:
            continue
        if r.get("op") == "note":
            if nid not in notes:
                order.append(nid)
            n = notes.setdefault(nid, {"id": nid, "status": "logged",
                                       "response": "", "history": []})
            n.update({"received": r.get("received"), "kind": r.get("kind"),
                      "topic": r.get("topic") or "", "text": r.get("text") or "",
                      # ⚠ A BACKFILLED NOTE SAYS SO. The first dozen rows were
                      # read back out of the conversation after the log was
                      # built, so their DATE is when they were written down,
                      # not when he said them. Stamping a precise arrival time
                      # I do not have would be inventing a measurement (R5).
                      "by": r.get("by") or "cody",
                      "backfilled": bool(r.get("backfilled"))})
        elif r.get("op") == "update":
            n = notes.get(nid)
            if not n:
                continue
            if r.get("status"):
                n["status"] = r["status"]
            if r.get("note"):
                n["response"] = r["note"]
            if r.get("by_fix"):
                n["by"] = r["by_fix"]
            n["updated"] = r.get("at")
            n["history"].append({"at": r.get("at"), "status": r.get("status"),
                                 "note": r.get("note") or ""})
    out = [notes[i] for i in order if i in notes]
    out.sort(key=lambda n: n.get("received") or "", reverse=True)
    return out


def counts(notes):
    c = dict((s, 0) for s in STATUS)
    for n in notes:
        c[n.get("status", "logged")] = c.get(n.get("status", "logged"), 0) + 1
    c["open"] = sum(c[s] for s in OPEN_STATUS)
    c["total"] = len(notes)
    return c


def next_id(rows=None):
    rows = _rows() if rows is None else rows
    n = 0
    for r in rows:
        if r.get("op") == "note":
            try:
                n = max(n, int(str(r.get("id"))[1:]))
            except ValueError:
                pass
    return "n%04d" % (n + 1)


def add(kind, text, topic="", received=None, backfilled=False,
        by="cody"):
    if kind not in KIND:
        raise SystemExit("notes_log: unknown kind %r (want one of %s)"
                         % (kind, ", ".join(KIND)))
    text = (text or "").strip()
    if not text:
        raise SystemExit("notes_log: refusing to log an empty note")
    nid = next_id()
    # ⚠ WHO WROTE IT IS PART OF THE RECORD. This log's promise is that
    # CODY's words are stored verbatim -- so a note Claude writes into it
    # (an observation, a surfaced action item) must be marked as such, or
    # the promise quietly becomes "somebody's words, unattributed". Caught
    # by the verbatim guard when the first Claude-authored note landed.
    _append({"op": "note", "id": nid, "received": received or _now(),
             "kind": kind, "topic": topic.strip(), "text": text,
             "by": by, "backfilled": bool(backfilled)})
    return nid


def set_status(nid, status=None, note=""):
    if status and status not in STATUS:
        raise SystemExit("notes_log: unknown status %r (want one of %s)"
                         % (status, ", ".join(STATUS)))
    # ⚠ A DECLINE WITHOUT A REASON IS REFUSED. The whole value of this log to
    # Cody is that he can see what happened to each item; "declined" with no
    # sentence beside it is indistinguishable from the note being dropped.
    if status == "declined" and not (note or "").strip():
        raise SystemExit("notes_log: a declined note must carry a reason")
    if not any(n["id"] == nid for n in load()):
        raise SystemExit("notes_log: no note %r" % nid)
    _append({"op": "update", "id": nid, "at": _now(),
             "status": status, "note": (note or "").strip()})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("add")
    a.add_argument("--kind", default="thought")
    a.add_argument("--topic", default="")
    a.add_argument("--text", default="")
    a.add_argument("--file")
    a.add_argument("--received")
    a.add_argument("--backfilled", action="store_true")
    a.add_argument("--by", default="cody")
    s = sub.add_parser("set")
    s.add_argument("id")
    s.add_argument("--status")
    s.add_argument("--note", default="")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    if args.cmd == "add":
        text = args.text
        if args.file:
            text = io.open(args.file, encoding="utf-8").read()
        print(add(args.kind, text, args.topic, args.received,
                  args.backfilled, args.by))
    elif args.cmd == "set":
        set_status(args.id, args.status, args.note)
        print("ok")
    else:
        notes = load()
        c = counts(notes)
        print("%d notes -- %d open, %d done, %d deferred, %d declined"
              % (c["total"], c["open"], c["done"], c["deferred"], c["declined"]))
        for n in notes:
            print("  %s  %-12s %-11s %s" % (
                n["id"], n.get("status"), (n.get("kind") or "")[:11],
                (n.get("topic") or n.get("text", ""))[:64].replace("\n", " ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
