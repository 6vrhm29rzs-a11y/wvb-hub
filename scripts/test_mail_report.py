#!/usr/bin/env python3
"""Guards for the daily reports, the mailer's identity rules and the schedule.

Nothing here sends mail or talks to Mail.app: the mailer checks run on its
pure functions with the transport and policy stubbed, and the report checks
render a PAST day from the built page. Skips cleanly where the private page
or data is absent (CI checks out a tree without Cody/).
"""
import datetime
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILED = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILED.append(label)


def test_mailer_identity():
    import mailer as M
    print("\n1. MAILER IDENTITY RULES")
    check("the only sender is the WVB account", M.APPROVED_SENDER == "wvbhub.desk@gmail.com")
    src = open(os.path.join(REPO, "scripts", "mailer.py"), encoding="utf-8").read()
    check("no personal address is written in the public source",
          "codyl" not in src and "@me.com" not in src and "@icloud.com" not in src)
    check("the Mail.app send sets the sender explicitly",
          'sender:"WVB Hub <{sender}>"' in M.MAILAPP_SCRIPT)
    check("...and refuses if it did not bind",
          'does not contain "{sender}"' in M.MAILAPP_SCRIPT)
    check("...and clears Mail's default signature",
          "set message signature of m to missing value" in M.MAILAPP_SCRIPT)
    orig = M.approved_recipient
    try:
        M.approved_recipient = lambda: "approved@example.org"
        check("a different recipient is refused",
              not M.preflight("someone@example.org", "gmail")[0])
        check("transport off is refused", not M.preflight("approved@example.org", "off")[0])
        check("[+] the approved recipient over the WVB route passes",
              M.preflight("approved@example.org", "gmail")[0])
        M.approved_recipient = lambda: ""
        check("no policy file means no send", not M.preflight("approved@example.org", "gmail")[0])
    finally:
        M.approved_recipient = orig
    check("an unknown transport value reads as off",
          "return \"off\"" in src)


def test_reports():
    print("\n2. REPORTS RENDER FROM THE PAGE")
    if not os.path.exists(os.path.join(REPO, "Cody", "START-HERE.html")):
        print("  --   no private page in this checkout; skipping")
        return
    import mail_report as R
    day = (datetime.datetime.now(R.PT).date() - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    c = R.collect("night", day)
    a, b = R.render_a(c), R.render_b(c)
    check("variant A carries the POWER table with day and week changes",
          "POWER TOP 15" in a and "vs day" in a and "vs week" in a)
    check("variant B is HTML with the same POWER table",
          b.startswith("<div") and "POWER top 15" in b)
    check("rating change and place change are separate columns/labels",
          "change in rating points, then places" in a)
    check("the week baseline names its Sunday",
          "Sunday-night lock (" in a)
    check("nothing invented: news section states it is not connected",
          "no verified news source" in R.render_a(R.collect("morning", day)))
    check("[-] a report never claims a result it did not render",
          all(r["w"] in a for r in c["upsets"]))


def test_schedule():
    print("\n3. SCHEDULE RULES")
    import mail_scheduler as S
    check("deadline is 21:30", S.DEADLINE == (21, 30))
    src = open(os.path.join(REPO, "scripts", "mail_scheduler.py"), encoding="utf-8").read()
    check("delivered only after the Outbox clears", 'outbox_clear(subject)' in src
          and '"delivered" if outbox_clear' in src)
    check("an early delivery suppresses the deadline run",
          'already delivered -- nothing to do' in src)
    check("an unreachable live feed is not completion",
          "cannot prove the slate is over" in src)
    check("no fixtures logged is not completion", "no fixtures logged for today" in src)
    if os.path.exists(os.path.join(REPO, "data", "data_2026.json")):
        past = (datetime.datetime.now(S.PT).date() - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        ok, n, nf, why = S.slate_status(past)
        check("[+] a finished past day reads complete (%s)" % why, ok or n == 0)


def main():
    test_mailer_identity()
    test_reports()
    test_schedule()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all mail checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
