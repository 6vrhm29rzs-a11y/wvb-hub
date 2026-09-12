#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Save a MANUALLY CAPTURED VolleyTalk thread.

⚠ DOES NOT FETCH, AND MUST NOT. volleytalk.proboards.com serves a
proof-of-work bot challenge (HTTP 202 + a headless check) to every
non-browser client; scripting around that is bot-detection bypass. Reading
the forum in Cody's own Chrome is ordinary browsing, and the capture is a
file saved out of that session -- the same route Massey, FIGstats and
Evollve use here.

⚠ THIS IS OTHER PEOPLE'S WRITING AND THE REPO IS PUBLIC. Captures land in
Cody/data/, which is gitignored in full, and the build's private markers
already strip anything VolleyTalk from the published page. Nothing in here
is ever republished; it exists so the hub can be READ against what people
who watch these matches are saying.

⚠ AND A FORUM POST IS EVIDENCE OF A CONVERSATION, NOT OF A FACT. The
standing rule on this project: community text may raise a SIGNAL and may
never set an availability status, a result, or a rating input. A post
saying a player is hurt is a prompt to go and look, nothing more.
"""
import hashlib
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "Cody", "data", "volleytalk_threads.jsonl")

# proboards repeats the poster and timestamp inside the message body, and
# prefixes a quoted reply with the whole quoted post. Strip the chrome so the
# stored text is what the person actually wrote.
BOILER = re.compile(
    r"^\s*(?:[^\n]{0,40}ago|[A-Z][a-z]{2} \d{1,2}, \d{4}[^\n]*)"
    r"(?: via mobile)?[^\n]*\n"
    r"(?:[^\n]{0,120}like(?:s)? this\s*\n)?"
    r"(?:Quote\s*\n)?(?:Post by [^\n]+\n)?", re.M)
QUOTED = None   # see the note above: handled structurally at capture


def clean(t):
    t = BOILER.sub("", t or "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: ingest_volleytalk.py <captured.json> [...]")
    saved = 0
    seen = set()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8"):
            try:
                seen.add(json.loads(line).get("sha256"))
            except ValueError:
                pass
    with io.open(OUT, "a", encoding="utf-8") as fh:
        for src in sys.argv[1:]:
            doc = json.load(io.open(src, encoding="utf-8"))
            posts = []
            for p in (doc.get("posts") or []):
                txt = clean(p.get("text"))
                if txt:
                    rec_p = {"user": p.get("user"), "when": p.get("when"),
                             "text": txt}
                    if p.get("quoting"):
                        rec_p["quoting"] = p["quoting"]
                    posts.append(rec_p)
            if not posts:
                print("  %s -- no posts parsed, skipped" % os.path.basename(src))
                continue
            payload = json.dumps(posts, sort_keys=True, ensure_ascii=False)
            sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if sha in seen:
                print("  %s -- identical capture already stored, skipped"
                      % os.path.basename(src))
                continue
            rec = {"source": "volleytalk.proboards.com",
                   "url": doc.get("url"), "title": doc.get("title"),
                   "captured": doc.get("captured"),
                   "capture": "manual browser review (bot challenge to clients)",
                   "posts": len(posts), "sha256": sha,
                   "usage": ("reference only -- may raise a signal, may never "
                             "set a status, a result or a rating input"),
                   "data": posts}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            seen.add(sha)
            saved += 1
            print("  saved %-46s %d posts" % ((doc.get("title") or "")[:46], len(posts)))
    print("volleytalk: %d thread capture(s) stored -> %s" % (saved, OUT))


if __name__ == "__main__":
    main()
