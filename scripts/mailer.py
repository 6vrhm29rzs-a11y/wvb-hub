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
SENDER = "wvbhub.desk@gmail.com"   # == APPROVED_SENDER below
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

# ⚠ THE EMAIL IDENTITY BOUNDARY (Cody decision, 2026-09-25;
# Cody/coordination/decisions/2026-09-25-email-identity.md). ONE sender, ONE
# recipient, both enforced here before any transport is touched. No fallback
# to any personal Gmail, iCloud, browser default or Mail.app default account:
# if the WVB identity cannot be verified, the report is saved and the failure
# is reported. The Mail.app path that existed briefly on 2026-09-25 used
# Mail's DEFAULT account and sent two emails as Cody's personal iCloud; it is
# removed, and 'mailapp' now means "Mail.app, sending AS the WVB account only".
APPROVED_SENDER = "wvbhub.desk@gmail.com"
# The approved RECIPIENT is Cody's personal address, so it lives in the private
# policy file, never in this public source. Missing file -> no send.
POLICY_FILE = os.path.join(REPO, "Cody", "data", "mail_policy.json")


def approved_recipient():
    try:
        v = json.load(io.open(POLICY_FILE, encoding="utf-8")).get("recipient") or ""
    except (IOError, ValueError):
        return ""
    return v.strip().lower()

MAILAPP_CHECK = """
tell application "Mail"
  set out to ""
  repeat with a in every account
    if (email addresses of a) contains "{sender}" then set out to out & (name of a) & "|" & (enabled of a) & linefeed
  end repeat
  return out
end tell
"""

MAILAPP_SCRIPT = """
set subj to read POSIX file "{subject}" as «class utf8»
set bod to read POSIX file "{body}" as «class utf8»
tell application "Mail"
  set m to make new outgoing message with properties {{subject:subj, content:bod, visible:false, sender:"WVB Hub <{sender}>"}}
  -- never carry a personal signature: an AppleScript-built message picks up
  -- Mail's default (Cody's iCloud "Cody Rose") even though the WVB account
  -- has none -- measured 2026-09-25 with a draft read-back, both ways
  set message signature of m to missing value
  tell m to make new to recipient at end of to recipients with properties {{address:"{to}"}}
  if (sender of m) does not contain "{sender}" then error "sender did not bind to {sender}"
  send m
end tell
"""


def transport():
    """'off' (default), 'mailapp' (Mail.app AS the WVB account only), or
    'gmail' (SMTP as the WVB account). Anything else is off."""
    if os.path.exists(TRANSPORT_FILE):
        v = io.open(TRANSPORT_FILE, encoding="utf-8").read().strip().lower()
        if v in ("mailapp", "gmail", "off"):
            return v
    return "off"


OSA_TIMEOUT_S = 90


def _osa(script, timeout=OSA_TIMEOUT_S):
    """Run AppleScript with a hard time bound (review 012 finding 2).
    A timeout returns rc 124, never hangs the caller."""
    import subprocess
    try:
        r = subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "osascript timed out after %d s" % timeout
    return r.returncode, r.stdout.decode("utf-8", "replace").strip()


def mailapp_identity():
    """(ok, detail): is there an ENABLED Mail.app account whose addresses
    include the WVB sender? Read-only; never reads a mailbox."""
    rc, out = _osa(MAILAPP_CHECK.format(sender=APPROVED_SENDER))
    if rc != 0:
        return False, "could not ask Mail.app: %s" % out
    rows = [x for x in out.splitlines() if x.strip()]
    if not rows:
        return False, "no Mail.app account carries %s" % APPROVED_SENDER
    if not any(x.endswith("|true") for x in rows):
        return False, "the %s account in Mail.app is disabled" % APPROVED_SENDER
    return True, "Mail.app account for %s is present and enabled" % APPROVED_SENDER


def preflight(to, tr):
    """Every check that must pass before ANY send. Returns (ok, reason)."""
    appr = approved_recipient()
    if not appr:
        return False, "no approved recipient in Cody/data/mail_policy.json"
    if to.strip().lower() != appr:
        return False, "recipient on file is not the approved destination"
    if tr == "mailapp":
        return mailapp_identity()
    if tr == "gmail":
        return True, "SMTP authenticates as %s" % APPROVED_SENDER
    return False, "mail transport is OFF"


def send_mailapp(to, subject, body):
    """Send through Mail.app AS the WVB account. Subject and body travel
    through temp files, never the command line. The script refuses to send
    if the message's sender did not bind to the WVB address."""
    import tempfile
    d = tempfile.mkdtemp(prefix="wvbmail-")
    sp, bp = os.path.join(d, "s.txt"), os.path.join(d, "b.txt")
    io.open(sp, "w", encoding="utf-8").write(subject)
    io.open(bp, "w", encoding="utf-8").write(body)
    try:
        rc, out = _osa(MAILAPP_SCRIPT.format(subject=sp, body=bp,
                                             sender=APPROVED_SENDER,
                                             to=to.replace('"', "")))
    finally:
        for f in (sp, bp):
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(d)
    if rc != 0:
        raise RuntimeError("Mail.app refused: %s" % out)


MAILAPP_PREVIEW = """
set subj to read POSIX file "{subject}" as «class utf8»
set bod to read POSIX file "{body}" as «class utf8»
tell application "Mail"
  set m to make new outgoing message with properties {{subject:subj, content:bod, visible:false, sender:"WVB Hub <{sender}>"}}
  set message signature of m to missing value
  tell m to make new to recipient at end of to recipients with properties {{address:"{to}"}}
  set s to sender of m
  set t to ""
  repeat with r in to recipients of m
    set t to t & (address of r) & ","
  end repeat
  set sj to subject of m
  delete m
  return s & linefeed & t & linefeed & sj
end tell
"""


def preview(subject, body):
    """Build the message through the SAME Mail.app path the reports use, read
    back the sender/recipients Mail actually bound, and discard it -- never
    sent, never saved. Writes Cody/mail/preview-<time>.txt for Cody."""
    import tempfile
    to = recipient()
    ok, why = preflight(to, "mailapp")
    if not ok:
        print("PREVIEW REFUSED -- %s" % why)
        return 1
    d = tempfile.mkdtemp(prefix="wvbprev-")
    sp, bp = os.path.join(d, "s.txt"), os.path.join(d, "b.txt")
    io.open(sp, "w", encoding="utf-8").write(subject)
    io.open(bp, "w", encoding="utf-8").write(body)
    try:
        rc, out = _osa(MAILAPP_PREVIEW.format(subject=sp, body=bp,
                                              sender=APPROVED_SENDER,
                                              to=to.replace('"', "")))
    finally:
        for f in (sp, bp):
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(d)
    if rc != 0:
        print("PREVIEW FAILED -- Mail.app: %s" % out)
        return 1
    lines = out.splitlines() + ["", "", ""]
    bound_from, bound_to, bound_subj = lines[0], lines[1].rstrip(","), lines[2]
    from_ok = APPROVED_SENDER in bound_from
    to_ok = bound_to.strip().lower() == approved_recipient()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    pdir = os.path.join(REPO, "Cody", "mail")
    os.makedirs(pdir, exist_ok=True)
    path = os.path.join(pdir, "preview-%s.txt" % stamp)
    io.open(path, "w", encoding="utf-8").write(
        "UNSENT PREVIEW -- built by Mail.app, read back, then discarded\n"
        "From (as Mail bound it): %s   [%s]\n"
        "To   (as Mail bound it): %s   [%s]\n"
        "Subject: %s\n\n%s\n"
        % (bound_from, "OK" if from_ok else "WRONG", bound_to,
           "OK" if to_ok else "WRONG", bound_subj, body))
    print("preview: from=%s [%s] to=%s [%s] -> %s"
          % (bound_from, "OK" if from_ok else "WRONG", bound_to,
             "OK" if to_ok else "WRONG", os.path.relpath(path, REPO)))
    return 0 if (from_ok and to_ok) else 1


def log_records():
    """Parsed send-log records (malformed lines skipped, never guessed at)."""
    out = []
    try:
        for line in io.open(LOG, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(r)
    except IOError:
        pass
    return out


def send(subject, body, dry=False, attempt=None):
    # type: (str, str, bool, str) -> int
    """`attempt` is the scheduler's claim id; it is written into the send
    log's success record so a later reconcile can match THIS attempt exactly,
    not a subject substring (review 012 finding 1)."""
    to = recipient()
    if not to:
        print("no recipient on file (%s)" % os.path.relpath(TO_FILE, REPO))
        return 1
    tr = transport()
    if not dry:
        ok, why = preflight(to, tr)
        if not ok:
            print("NOT SENT -- %s (report kept)" % why)
            return 1
    if transport() == "mailapp" and not dry:
        send_mailapp(to, subject, body)
        rec = {"utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
               "subject": subject, "from": APPROVED_SENDER, "to": to,
               "via": "mailapp", "ok": True, "attempt": attempt,
               "bytes": len(body.encode("utf-8"))}
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print("sent via Mail.app as %s: %s  (%d bytes)"
              % (APPROVED_SENDER, subject, rec["bytes"]))
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
           "subject": subject, "from": SENDER, "to": to, "via": "gmail",
           "ok": True, "attempt": attempt,
           "bytes": len(body.encode("utf-8"))}
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print("sent: %s  (%d bytes)" % (subject, rec["bytes"]))
    return 0


if __name__ == "__main__":
    body = sys.stdin.read()
    subj = sys.argv[1] if len(sys.argv) > 1 else "WVB Hub"
    if "--preview" in sys.argv:
        sys.exit(preview(subj, body))
    sys.exit(send(subj, body, dry="--dry" in sys.argv))
