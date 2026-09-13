#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the third results witness (themonsterblock.com).

⚠ WHY THIS SOURCE IS HELD TO A JOIN GUARD AT ALL. It is the only independent
witness we have on a result -- the schools of 13 of the top 50 render their
schedules client-side, so when the feed inverts one of THOSE matches nothing
else catches it. Measured 2026-09-13: the ingester resolved both sides on only
138 of 160 rows, and the 22 misses were the RANKED matches, because the site
prefixes a ranked team with its AVCA rank ("#15 Creighton") and serves names
HTML-escaped ("Alabama A&amp;M", "St. John&#x27;s (NY)"). The witness was blind
in exactly the place it was captured for. That is what these checks hold shut.

The snapshot keeps the page's own string in `away`/`home`; the joinable name
lives in `away_name`/`home_name`, and the rank the site published is kept as
its own datum rather than thrown away.

Python 3.9 target. Run: python3 scripts/test_monsterblock.py
"""

import io
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-70s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def row_html(aslug, araw, hslug, hraw, sets, status="FINAL", awin=True):
    return (
        '<tr><td>'
        '<span class="%s"><a class="team-link" href="/teams/%s/">%s</a></span>'
        ' @ '
        '<span class="%s"><a class="team-link" href="/teams/%s/">%s</a></span>'
        '<span class="sets">(%s)</span>'
        '</td><td class="status">%s</td></tr>'
        % ("winner" if awin else "loser", aslug, araw,
           "loser" if awin else "winner", hslug, hraw, sets, status))


def main():
    import ingest_monsterblock as MB

    page = ('<h2 class="date-heading">Saturday, September 12, 2026</h2>'
            + row_html("creighton", "#15 Creighton 1",
                       "louisville", "#5 Louisville 3",
                       "25-22, 21-25, 20-25, 18-25", awin=False)
            + row_html("alabama-am", "Alabama A&amp;M 0",
                       "loyola-chicago", "Loyola Chicago 3",
                       "12-25, 15-25, 17-25", awin=False)
            + row_html("njit", "NJIT 1",
                       "st-johns-ny", "St. John&#x27;s (NY) 3",
                       "25-21, 22-25, 19-25, 20-25", awin=False))
    rows = MB.parse(page)

    print("1. THE PAGE'S STRING IS KEPT; A JOINABLE NAME IS DERIVED")
    check("all three rows parse", len(rows) == 3, "%d parsed" % len(rows))
    r = rows[0]
    check("the raw string is preserved verbatim", r["away"] == "#15 Creighton",
          repr(r.get("away")))
    check("the joinable name drops the rank prefix",
          r["away_name"] == "Creighton", repr(r.get("away_name")))
    check("the rank the SITE published is kept, not discarded",
          r["away_rank_listed"] == 15 and r["home_rank_listed"] == 5,
          "%r/%r" % (r.get("away_rank_listed"), r.get("home_rank_listed")))
    check("an unranked side carries no invented rank",
          rows[1]["away_rank_listed"] is None)
    check("HTML entities are decoded in the joinable name",
          rows[1]["away_name"] == "Alabama A&M"
          and rows[2]["home_name"] == "St. John's (NY)",
          "%r / %r" % (rows[1].get("away_name"), rows[2].get("home_name")))
    check("sets and the winner still parse",
          r["sets"] == [[25, 22], [21, 25], [20, 25], [18, 25]]
          and r["winner"] == "home", str(r.get("sets")))

    print("\n2. THE JOIN REACHES THE HUB -- INCLUDING THE RANKED MATCHES")
    season = int(os.environ.get("WVB_SEASON", "2026"))
    hub_path = os.path.join(REPO, "data", "data_%d.json" % season)
    if not os.path.exists(hub_path):
        check("hub dataset present to join against", False, hub_path)
    else:
        hub = json.load(io.open(hub_path, encoding="utf-8"))
        keys = MB.hub_keys(hub)
        hit = MB.attach_hub(rows, keys)
        check("every fixture row resolves on BOTH sides", hit == 3,
              "%d of 3; unresolved %s" % (hit, [
                  (x["away"], x["home"]) for x in rows
                  if not (x["away_hub"] and x["home_hub"])]))
        check("the ranked row resolves to the hub's own spelling",
              rows[0]["away_hub"] == "Creighton"
              and rows[0]["home_hub"] == "Louisville",
              "%r/%r" % (rows[0].get("away_hub"), rows[0].get("home_hub")))

        # NEGATIVE CONTROL: join on the page's raw string, as the ingester did
        # before 2026-09-13, and the ranked + escaped rows must fall out again.
        from external_refs import _ref_norm
        raw_hit = sum(1 for x in rows
                      if keys.get(_ref_norm(x["away"]))
                      and keys.get(_ref_norm(x["home"])))
        check("[-] ...and joining on the RAW string loses them (control)",
              raw_hit == 0, "%d still resolved" % raw_hit)

        # NEGATIVE CONTROL: a cleaner that does not strip the rank prefix.
        name, rank = MB.clean_name("#1 Nebraska")
        check("[-] ...and clean_name really is what strips it (control)",
              name == "Nebraska" and rank == 1, "%r/%r" % (name, rank))

    print("\n3. AN UNCHANGED DAY IS NOT WRITTEN AGAIN")
    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        io.open(tmp, "w", encoding="utf-8").write(
            json.dumps({"content_sha256": "abc"}) + "\n")
        check("the same content is recognised as already stored",
              MB.unchanged(tmp, "abc") is True)
        check("different content is not", MB.unchanged(tmp, "def") is False)
        io.open(tmp, "w", encoding="utf-8").write("")
        check("an empty log stores the first snapshot",
              MB.unchanged(tmp, "abc") is False)
        check("a missing log stores the first snapshot",
              MB.unchanged(tmp + ".nope", "abc") is False)
        # ⚠ APPEND-ONLY IS NOT WEAKENED: the newest row decides, and nothing
        # already written is ever rewritten or removed.
        io.open(tmp, "w", encoding="utf-8").write(
            json.dumps({"content_sha256": "old"}) + "\n"
            + json.dumps({"content_sha256": "new"}) + "\n")
        check("the NEWEST stored row is the one compared",
              MB.unchanged(tmp, "new") is True
              and MB.unchanged(tmp, "old") is False)
    finally:
        os.unlink(tmp)

    print("\n4. THE SOURCE STAYS A REFERENCE, NOT AN AUTHORITY")
    src = io.open(os.path.join(REPO, "scripts/ingest_monsterblock.py"),
                  encoding="utf-8").read()
    check("it says a disagreement is a place to look, not a correction",
          "NOT A CORRECTION" in src.upper())
    check("it writes no correction and no evidence file",
          "result_corrections" not in src and "result_evidence" not in src)
    check("its own fetch time is stamped by the script, not by an env var",
          'datetime.datetime.utcnow()' in src and
          'os.environ.get("MB_RETRIEVED", "")' in src,
          "a fetching script knows when it fetched")

    print("\n%s" % ("ALL CHECKS PASS" if not FAILS
                    else "FAILED: %d\n   - %s" % (len(FAILS),
                                                  "\n   - ".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
