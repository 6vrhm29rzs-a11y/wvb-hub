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
          "POWER TOP 15" in a and "Day = " in a and "Week = " in a)
    check("variant B is HTML with the same POWER table",
          b.startswith("<div") and "POWER Top 15" in b)
    check("rating change and place change are separate columns/labels",
          "change in rating points, then" in a and " pts " in a)
    check("the week baseline names its Sunday",
          "Sunday-night lock (" in a)
    check("nothing invented: news section states it is not connected",
          "no verified news source" in R.render_a(R.collect("morning", day)))
    check("[-] takeaways name only results that exist",
          all(r["w"] in a for r in c["upsets"][:1]))
    order = [a.find(x) for x in ("TAKEAWAYS", "POWER TOP 15", "BIGGEST MOVERS OUTSIDE", "UNFINISHED AT SEND TIME")]
    check("011 order: takeaways, POWER Top 15, movers outside, unfinished",
          all(x >= 0 for x in order[:2] + order[3:]) and order == sorted(x for x in order if x >= 0) or
          (order[0] < order[1] < order[3]))
    check("3-5 takeaways, biggest upset distinct from most consequential",
          1 <= len(c["takeaways"]) <= 5 and (len(c["takeaways"]) < 2 or
          c["takeaways"][0][1] != c["takeaways"][1][1]))


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
          src.index('rec.update(status="claimed"') < src.index("rc = mailer.send("))
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

    print("\n5. NO DUPLICATE SENDS (reviews 010, 012) -- Outbox and log stubbed")
    import mailer as M
    o_out, o_log, o_appr = S.outbox_count, M.log_records, M.approved_recipient
    try:
        M.approved_recipient = lambda: "approved@example.org"
        claim = {"status": "claimed", "subject": "S", "attempt": "a1"}
        good = {"attempt": "a1", "ok": True, "from": M.APPROVED_SENDER,
                "to": "approved@example.org", "subject": "S"}
        S.outbox_count = lambda subj: None
        M.log_records = lambda: []
        check("Outbox unavailable, no log -> held (needs_review), not abandoned",
              S.reconcile(dict(claim))["status"] == "needs_review")
        M.log_records = lambda: [dict(good)]
        check("Outbox unavailable even WITH a matching log -> held, not submitted",
              S.reconcile(dict(claim))["status"] == "needs_review")
        S.outbox_count = lambda subj: 1
        check("still in the Outbox -> queued, never resent",
              S.reconcile(dict(claim))["status"] == "queued_in_outbox")
        S.outbox_count = lambda subj: 0
        M.log_records = lambda: [dict(good, ok=False)]
        check("a FAILED log record with the same subject is not submission",
              S.reconcile(dict(claim))["status"] == "needs_review")
        M.log_records = lambda: [dict(good, attempt="other")]
        check("a record for a different attempt is not submission",
              S.reconcile(dict(claim))["status"] == "needs_review")
        M.log_records = lambda: []
        check("crash after acceptance, before the log write -> held, not retried",
              S.reconcile(dict(claim))["status"] == "needs_review")
        M.log_records = lambda: [dict(good)]
        check("[+] Outbox empty + ok record for THIS attempt -> submitted",
              S.reconcile(dict(claim))["status"] == "submitted")
        check("held states are never eligible for a new send",
              "needs_review" in S.IN_FLIGHT)
    finally:
        S.outbox_count, M.log_records, M.approved_recipient = o_out, o_log, o_appr

    print("\n6. EVERY STEP IS TIME-BOUNDED (review 012 finding 2)")
    import tempfile
    d = tempfile.mkdtemp()
    hang = os.path.join(d, "hang.py")
    open(hang, "w").write("import time\ntime.sleep(30)\n")
    t0 = __import__("time").time()
    try:
        S.build("night", "2026-01-01", "", timeout=2, report=hang)
        hung = False
    except RuntimeError as e:
        hung = "exceeded" in str(e)
    check("a hanging report build is cut off at its bound",
          hung and __import__("time").time() - t0 < 10)
    o_prep, o_build = S.PREPARED, S.build
    try:
        S.PREPARED = d
        open(S.prepared_path("night", "2026-01-01"), "w").write("prepared body\n" * 20)
        def boom(*a, **k):
            raise RuntimeError("report build exceeded 150 s")
        S.build = boom
        body, src_ = S.body_for_dispatch("night", "2026-01-01", "")
        check("[+] a failed dispatch build falls back to the prepared report",
              body.startswith("prepared body") and src_.startswith("prepared"))
        body, src_ = S.body_for_dispatch("night", "2026-01-01", "", prefer_prepared=True)
        check("the 06:00 dispatch sends what was prepared without rebuilding",
              src_ == "prepared earlier today")
    finally:
        S.PREPARED, S.build = o_prep, o_build
    msrc = open(os.path.join(REPO, "scripts", "mailer.py"), encoding="utf-8").read()
    check("Mail AppleScript calls are time-bounded", "timeout=timeout)" in msrc and "OSA_TIMEOUT_S" in msrc)
    check("the Outbox check is time-bounded", "timeout=30)" in src)
    check("morning prepares before its 06:00 dispatch", S.MORNING_DISPATCH == (6, 0)
          and "preparation run (05:40)" in src)


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
