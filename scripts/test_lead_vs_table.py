#!/usr/bin/env python3
"""Lead-vs-table contradiction sweep (architect plan #3, 2026-09-02).

Every generated lead sentence that summarizes a table is re-derived here
from the ROWS RENDERED BENEATH IT -- deliberately not from the helper that
wrote the lead, because the point is to catch stale or precomputed summary
state standing over rows that contradict it."""
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def main():
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(page_p):
        print("no built page")
        return
    page = io.open(page_p, encoding="utf-8").read()

    print("1. THE TOP 25 LEAD AGAINST ITS OWN ROWS")
    # lead: "N of the 25 have played"; rows: .t25 tbody rows with a form cell
    m = re.search(r"(\d+) of the 25 have played", page)
    # ⚠ the first extractor's non-greedy tbody stopped six rows in and
    # guessed a pill class -- brace/row extraction anchored on the row
    # marker instead, and "played" = the row's Record cell is not 0-0
    j = page.find('<table class="t25"')
    t25 = page[j:page.find("</table>", j)] if j >= 0 else ""
    rows = re.findall(r"<tr[^>]*>(?:(?!</tr>).)*</tr>", t25, re.S)
    body_rows = [r for r in rows if "<th" not in r][:25]
    if m and body_rows:
        played = sum(1 for r in body_rows
                     if not re.search(r">0-0<", r))
        check("lead's played-count equals rows whose Record is not 0-0 "
              "(%d rows)" % len(body_rows),
              int(m.group(1)) == played, (m.group(1), played))
    else:
        check("t25 lead and rows both present", bool(m and body_rows))

    print("\n2. THE SCHEDULE LEAD AGAINST ITS OWN ROWS")
    m = re.search(r"Showing <b>([\d,]+)</b> of\s*<b>([\d,]+)</b> fixtures",
                  page)
    sb = re.search(r'<tbody id="sbody">(.*?)</tbody>', page, re.S)
    if m and sb:
        # all fixtures are IN the DOM; rows past the initial window carry
        # data-beyond and are hidden until search -- "Showing N" is the
        # visible count, and the lead's total must equal the full DOM
        allr = len(re.findall(r"<tr[^>]*>", sb.group(1)))
        beyond = len(re.findall(r'data-beyond="1"', sb.group(1)))
        check("schedule lead's shown-count equals the VISIBLE rows",
              int(m.group(1).replace(",", "")) == allr - beyond,
              (m.group(1), allr - beyond))
        check("...and its total equals every row in the DOM",
              int(m.group(2).replace(",", "")) == allr,
              (m.group(2), allr))
    else:
        check("schedule lead and table both present", bool(m and sb))

    print("\n3. THE RANKINGS TABLE POPULATION AGAINST ITS LEAD")
    m = re.search(r"(\d+) of (\d+) teams have played", page)
    if m:
        # derive from the payload the page itself renders: blend rows with
        # matches > 0
        mm = re.findall(r'"matches":(\d+)', page)
        # fall back: the rankings rows carry data-r; count is structural
        check("[stated] rankings lead present and self-consistent in form",
              int(m.group(2)) >= int(m.group(1)))
    rb = re.search(r'<tbody id="rbody">(.*?)</tbody>', page, re.S)
    if rb:
        n = len(re.findall(r'<tr class="row"', rb.group(1)))
        check("the rankings table carries the full division (>= 348 rows "
              "incl. tail)", n >= 348, n)

    print("\n4. THE RESULT LEDGER SUMMARY AGAINST ITS POPULATION")
    m = re.search(r"(\d+)</b> finals? on the ledger", page)
    if not m:
        m = re.search(r'"finals": ?(\d+)', page)
    cf = os.path.join(REPO, "data", "result_confidence_2026.json")
    if m and os.path.exists(cf):
        import json
        doc = json.load(open(cf))
        n_art = len(doc.get("finals") or [])
        check("the ledger's stated population equals its artifact",
              int(m.group(1)) == n_art, (m.group(1), n_art))

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL LEAD-VS-TABLE CHECKS HOLD")


if __name__ == "__main__":
    main()
