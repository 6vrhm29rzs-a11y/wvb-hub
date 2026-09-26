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
          "POWER TOP 15" in a and "day = " in a and "week = " in a)
    check("variant B is HTML with the same POWER table",
          b.startswith("<div") and "POWER top 15" in b)
    check("rating change and place change are separate columns/labels",
          "change = rating pts, then places" in a and " pts " in a)
    check("the week baseline names its Sunday",
          "Sunday-night lock (" in a)
    check("nothing invented: news section states it is not connected",
          "no verified news source" in R.render_a(R.collect("morning", day)))
    check("[-] a report never claims a result it did not render",
          all(r["w"] in a for r in c["upsets"]))


def test_schedule():
    print("\n3. SCHEDULE RULES")
    import mail_scheduler as S
    check("the report is submitted by 21:30; the final attempt starts 21:15",
          S.DEADLINE == (21, 30) and S.FINAL_START == (21, 15))
    check("refresh is bounded", 0 < S.REFRESH_TIMEOUT_S <= 420)
    src = open(os.path.join(REPO, "scripts", "mail_scheduler.py"), encoding="utf-8").read()
    check("no state is called 'delivered' (the Outbox cannot prove receipt)",
          '"delivered"' not in src)
    check("a claim is persisted before the send",
          src.index('rec["status"] = "claimed"') < src.index("rc = mailer.send("))
    check("runs are serialized by a lock", "with Lock():" in src)

    print("\n4. FEED EVIDENCE (review 010 finding 1) -- stubbed, no network")
    t = S.now().replace(hour=22, minute=0, second=0, microsecond=0)
    day = t.strftime("%Y-%m-%d")
    games = [{"game_id": "1", "state": "F", "teams": [],
              "start_time_epoch": int(t.replace(hour=19).timestamp())}]
    fresh = "9:58:00 PM PT"
    cases = [
        ("an empty 200 is not completion", {"games": [], "updated": fresh}, False),
        ("a missing games key is not completion", {"updated": fresh}, False),
        ("a stale feed is not completion", {"games": [{"id": "1", "date": day, "state": "final"}],
                                            "updated": "8:00:00 PM PT"}, False),
        ("a malformed feed is not completion", ["x"], False),
        ("a feed error is not completion", {"games": [], "error": "x", "updated": fresh}, False),
        ("a live game blocks completion", {"games": [{"id": "1", "date": day, "state": "live"}],
                                           "updated": fresh}, False),
        ("a feed final not yet logged blocks completion",
         {"games": [{"id": "2", "date": day, "state": "final"}], "updated": fresh}, False),
        ("[+] fresh feed, all final and logged -> complete",
         {"games": [{"id": "1", "date": day, "state": "final"}], "updated": fresh}, True),
    ]
    for label, feed, want in cases:
        got = S.slate_status(day, feed=feed, t=t, games=games)[0]
        check(label, got is want, got)

    print("\n5. NO DUPLICATE SENDS (review 010 finding 3) -- stubbed Outbox")
    orig = S.outbox_count
    try:
        S.outbox_count = lambda subj: 1
        r = S.reconcile({"status": "claimed", "subject": "x"})
        check("a claim still in the Outbox stays in flight (never resent)",
              r["status"] == "queued_in_outbox")
        S.outbox_count = lambda subj: 0
        r = S.reconcile({"status": "queued_in_outbox", "subject": "never-logged-subject-zz"})
        check("a claim that never reached the mailer is marked abandoned, not submitted",
              r["status"] == "claim_abandoned")
    finally:
        S.outbox_count = orig


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
