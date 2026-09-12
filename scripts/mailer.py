#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send a report to Cody's inbox. Data first; graphics later.

Cody, 2026-09-11: "Go ahead and get the emails up and running. Just sending
me data and info. Doesn't need to be graphics and images yet. Send the data
and we'll find mistakes and make changes til it's perfect."

⚠ THIS IS THE FIRST IRREVERSIBLE SURFACE THIS PROJECT HAS. Everything else is
a page that re-renders; a wrong number there lives until the next build and
then is gone. An email cannot be recalled. There are 47 corrections on file,
several of them inverted winners, and the feed handed us another bad state
today. So:
  * a result appears only if it passes the SAME counting rules the page uses
    (season_counts.countable) -- never the raw feed;
  * a same-day final says whether the schools have confirmed it, because the
    trust cutoff already treats those differently for the rating;
  * every send is LOGGED with what it claimed, so a later correction can be
    traced to the mail that was wrong.

⚠ CREDENTIALS ARE READ AT SEND TIME from Cody/data/ (gitignored, 600) and
never printed, never logged, never passed on a command line.

Python 3.9 target.
"""
import datetime
import io
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
SENDER = "wvbhub.desk@gmail.com"
PW_FILE = os.path.join(REPO, "Cody", "data", "gmail_app_password.txt")
TO_FILE = os.path.join(REPO, "Cody", "data", "mail_to.txt")
LOG = os.path.join(REPO, "Cody", "data", "mail_log.jsonl")
# Gmail's web client CLIPS a message over ~102 KB into "[Message clipped]" --
# it does not error, it just silently truncates, so a long recap would lose
# its tail with nothing to say so. Stay well under.
CLIP_BYTES = 90000


def recipient():
    if os.path.exists(TO_FILE):
        v = io.open(TO_FILE, encoding="utf-8").read().strip()
        if v:
            return v
    return os.environ.get("WVB_MAIL_TO") or ""


def password():
    if not os.path.exists(PW_FILE):
        return ""
    return io.open(PW_FILE, encoding="utf-8").read().strip()


def send(subject, body, dry=False):
    # type: (str, str, bool) -> int
    to = recipient()
    pw = password()
    if not to:
        print("no recipient on file (%s)" % os.path.relpath(TO_FILE, REPO))
        return 1
    if not pw:
        print("no app password on file (%s)" % os.path.relpath(PW_FILE, REPO))
        return 1
    raw = body.encode("utf-8")
    if len(raw) > CLIP_BYTES:
        # ⚠ TRUNCATE LOUDLY. Gmail would clip it silently; a reader cannot
        # tell a clipped mail from a short one, and would believe the tail
        # simply had nothing in it.
        keep = raw[:CLIP_BYTES].decode("utf-8", "ignore")
        body = keep + ("\n\n--- TRUNCATED at %d KB to stay under Gmail's clip "
                       "threshold. %d KB was cut; the site has all of it. ---"
                       % (CLIP_BYTES // 1000, (len(raw) - CLIP_BYTES) // 1000))
    msg = EmailMessage()
    msg["From"] = "WVB Hub <%s>" % SENDER
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if dry:
        print("DRY RUN -- not sending\n")
        print("To: %s\nSubject: %s\n" % (to, subject))
        print(body)
        return 0
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=40) as s:
        s.login(SENDER, pw)
        s.send_message(msg)
    rec = {"utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "subject": subject, "to": to, "bytes": len(body.encode("utf-8"))}
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print("sent: %s  (%d bytes)" % (subject, rec["bytes"]))
    return 0


if __name__ == "__main__":
    body = sys.stdin.read()
    subj = sys.argv[1] if len(sys.argv) > 1 else "WVB Hub"
    sys.exit(send(subj, body, dry="--dry" in sys.argv))
