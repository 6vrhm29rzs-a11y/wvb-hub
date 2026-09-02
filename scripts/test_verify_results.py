#!/usr/bin/env python3
"""Guards for the nightly result verifier (2026-09-01)."""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import verify_results_daily as V  # noqa: E402

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


PAGE = """
<table><tr><th>Date</th><th>Time</th><th>At</th><th>Opponent</th>
<th>Location</th><th>Result</th></tr>
<tr><td>Aug 14 (Fri)</td><td>6 p.m.</td><td>Home</td>
<td>Notre Dame (Exh.)</td><td>Bloomington, Ind.</td><td>N -</td></tr>
<tr><td>Aug 28 (Fri)</td><td>7 p.m.</td><td>Away</td><td>#7 Louisville</td>
<td>Louisville, Ky.</td><td>L 0-3</td></tr>
<tr><td>Aug 31 (Mon)</td><td>7 p.m.</td><td>Home</td><td>RV Dayton</td>
<td>Louisville, Ky.</td><td>W 3-0</td></tr>
<tr><td>Sep 1 (Tue)</td><td>6 p.m.</td><td>Neutral</td><td>Georgia</td>
<td>West Lafayette, Ind.</td><td>Big Ten/SEC Challenge</td><td> -</td></tr>
<tr><td>Sep 1 (Tue)</td><td>8 p.m.</td><td>Neutral</td><td>Purdue</td>
<td>West Lafayette, Ind.</td><td>Event</td><td>W 3-2</td></tr>
<tr><td>Jan 5 (Mon)</td><td>1 p.m.</td><td>Home</td><td>Somebody</td>
<td>X</td><td>W 3-1</td></tr>
</table>"""


def main():
    print("1. THE PARSER READS THE /schedule/text SURFACE")
    rows = V.parse_schedule_text(PAGE)
    check("all six rows parse", len(rows) == 6, len(rows))
    by = {(r["date"], r["opponent"]): r for r in rows}
    check("rank prefix '#7' is stripped",
          ("2026-08-28", "Louisville") in by)
    check("rank prefix 'RV' is stripped (paid for live: Louisville's page "
          "says 'RV Dayton')", ("2026-08-31", "Dayton") in by)
    check("an exhibition row is MARKED, not dropped",
          by.get(("2026-08-14", "Notre Dame"), {}).get("exhibition") is True)
    check("a not-posted result is None, never invented",
          by.get(("2026-09-01", "Georgia"), {}).get("result") is None)
    check("W/L results parse with set counts",
          by.get(("2026-08-31", "Dayton"), {}).get("result") == ("W", 3, 0))
    check("January belongs to the NEXT calendar year",
          ("2027-01-05", "Somebody") in by)
    check("'Sept. 1' and 'September 1' both parse",
          V.parse_sidearm_date("Sept. 1") == (9, 1) and
          V.parse_sidearm_date("September 1 (Tue)") == (9, 1))
    check("an unrecognised date cell parses to nothing, never a guess",
          V.parse_sidearm_date("9/1/2026") == (None, None))
    check("site classification survives",
          by.get(("2026-09-01", "Georgia"), {}).get("site") == "Neutral")

    print("\n2. VERDICTS -- corroboration is never verification")
    v = V.verdict
    check("both agree COMPLETELY -> VERIFIED_BOTH",
          v("AGREE_COMPLETE", "AGREE_COMPLETE") == "VERIFIED_BOTH")
    check("one agrees, one not posted -> CORROBORATED_ONE, never verified",
          v("AGREE_COMPLETE", "NOT_POSTED") == "CORROBORATED_ONE")
    check("both contradict -> CONTRADICTED_BOTH (the review candidate)",
          v("CONTRADICTS", "CONTRADICTS") == "CONTRADICTED_BOTH")
    check("schools disagreeing with each other is its own state",
          v("AGREE_COMPLETE", "CONTRADICTS") == "SCHOOL_CONFLICT")
    check("nothing usable -> UNVERIFIED",
          v("EVENT_NOT_FOUND", "SITE_UNPARSED") == "UNVERIFIED")
    # ⚠ THE CONSULT'S CATCH (2026-09-01): the old AGREE_PARTIAL state let
    # two schools that both said "3-1" VERIFY our 3-2. Winner-only agreement
    # is a set-count CONTRADICTION and two of them are a review candidate.
    check("[NEG] two schools agreeing on winner but contradicting our set "
          "count NEVER verify",
          v("CONTRADICTS_SETS", "CONTRADICTS_SETS") == "CONTRADICTED_BOTH")
    check("[NEG] one set-count contradiction beside a full agreement is a "
          "school conflict, not a verification",
          v("AGREE_COMPLETE", "CONTRADICTS_SETS") == "SCHOOL_CONFLICT")
    check("[NEG] AGREE_PARTIAL no longer exists as a state",
          "AGREE_PARTIAL" not in open(os.path.join(
              REPO, "scripts", "verify_results_daily.py")).read())

    print("\n3. THE VERIFIER CAN NEVER FILE A CORRECTION")
    src = open(os.path.join(REPO, "scripts",
                            "verify_results_daily.py")).read()
    check("result_corrections.json is never opened for writing",
          "result_corrections" not in src)
    check("candidates go to the review queue, merged never overwritten",
          "result_review_queue.json" in src and "q.setdefault" in src)
    check("the fetch log is append-only",
          '"result_verification_log.jsonl"), "a"' in src.replace("'", '"'))
    check("opponent identity dominates the date (doubleheaders)",
          "team_norm(r[\"opponent\"]) == want" in src)

    print("\n4. [NEG] negative controls")
    # a doubled date: matching by date alone would take Georgia's row for
    # a Purdue query; the opponent anchor must pick the right one
    sep1 = [r for r in rows if r["date"] == "2026-09-01"]
    check("[NEG] two matches on one date stay distinct rows",
          len(sep1) == 2 and {r["opponent"] for r in sep1} ==
          {"Georgia", "Purdue"})
    # tournament title in a cell must never be read as a result
    check("[NEG] an event title is not a result",
          by.get(("2026-09-01", "Georgia"), {}).get("result") is None and
          by.get(("2026-09-01", "Purdue"), {}).get("result") == ("W", 3, 2))

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL RESULT-VERIFIER GUARDS PASS")


if __name__ == "__main__":
    main()
