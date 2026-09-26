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


TRANSPORT_FILE = os.path.join(REPO, "Cody", "data", "mail_transport.txt")

MAILAPP_SCRIPT = """
set subj to read POSIX file "{subject}" as «class utf8»
set bod to read POSIX file "{body}" as «class utf8»
tell application "Mail"
  set m to make new outgoing message with properties {{subject:subj, content:bod, visible:false}}
  tell m to make new to recipient at end of to recipients with properties {{address:"{to}"}}
  send m
end tell
"""


def transport():
    """'mailapp' (default) or 'gmail'.

    ⚠ MAIL.APP IS THE DEFAULT SINCE 2026-09-25. Google disabled the
    wvbhub.desk account twice (Sep 12, Sep 14) and, after it was restored on
    appeal, still answered every scripted SMTP login with 534
    WebLoginRequired -- a fresh app password did not change that. Each failed
    login adds to the record that got it disabled, so the reports no longer
    touch that account unless mail_transport.txt says 'gmail'. Mail.app sends
    from an account Cody already uses (iCloud), with no password in this repo.
    """
    if os.path.exists(TRANSPORT_FILE):
        v = io.open(TRANSPORT_FILE, encoding="utf-8").read().strip().lower()
        if v in ("mailapp", "gmail", "off"):
            return v
    # ⚠ OFF BY DEFAULT (2026-09-25, Cody): Mail.app sent the reports from his
    # PERSONAL address -- "you cannot use my personal gmail". Nothing sends
    # until a transport that uses only the WVB account is chosen explicitly.
    return "off"


def send_mailapp(to, subject, body):
    """Hand the message to Mail.app, which sends from its default account.
    Subject and body travel through temp files, never the command line."""
    import subprocess
    import tempfile
    d = tempfile.mkdtemp(prefix="wvbmail-")
    sp, bp = os.path.join(d, "s.txt"), os.path.join(d, "b.txt")
    io.open(sp, "w", encoding="utf-8").write(subject)
    io.open(bp, "w", encoding="utf-8").write(body)
    script = MAILAPP_SCRIPT.format(subject=sp, body=bp, to=to.replace('"', ""))
    try:
        r = subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=120)
    finally:
        for f in (sp, bp):
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(d)
    if r.returncode != 0:
        raise RuntimeError("Mail.app refused: %s"
                           % r.stdout.decode("utf-8", "replace").strip())


def send(subject, body, dry=False):
    # type: (str, str, bool) -> int
    to = recipient()
    if not to:
        print("no recipient on file (%s)" % os.path.relpath(TO_FILE, REPO))
        return 1
    if transport() == "off" and not dry:
        print("mail transport is OFF -- nothing sent (report kept); see "
              "Cody/data/mail_transport.txt")
        return 1
    if transport() == "mailapp" and not dry:
        send_mailapp(to, subject, body)
        rec = {"utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
               "subject": subject, "to": to, "via": "mailapp",
               "bytes": len(body.encode("utf-8"))}
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print("sent via Mail.app: %s  (%d bytes)" % (subject, rec["bytes"]))
        return 0
    pw = password()
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
