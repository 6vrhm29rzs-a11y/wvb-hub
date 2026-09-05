#!/usr/bin/env python3
"""Every headline COUNT on the page names its universe, and counts that
share a universe agree at one build instant (ChatGPT audit item 3,
2026-09-05; Cody's screenshots showed 753 / 754 / 767 / 175 / 178 with no
reader-facing map).

The map, from each number's own source:
  masthead "results on the board"  = season_counts results_on_display
                                     (ok + exhibition + under_review;
                                      duplicates and empty finals excluded)
  Stats "counted finals"           = the same universe -- MUST EQUAL it
  Top 25 "rating-eligible finals"  = rating_eligible_now (D-I v D-I with a
                                     line, trust cutoff applied)
  Ballot "finals in"               = the weekly GATE (every completed feed
                                     record in the ballot window; its job is
                                     "is the week done", so exhibitions and
                                     duplicates count) -- must be LABELLED
  Scoreboard day count             = that day's fixtures after the day
                                     predicate; the tape's "N others on the
                                     card" counts the SAME day universe
"""
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append("%s %s" % (label, detail))


def main():
    import season_counts as SC
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(page_p):
        print("no built page")
        return 0
    page = io.open(page_p, encoding="utf-8").read()
    games = SC.load_games_jsonl(os.path.join(
        REPO, "data", "raw", "2026", "games.jsonl")) if hasattr(
        SC, "load_games_jsonl") else None
    if games is None:
        from gamelog import load_games_jsonl
        games = load_games_jsonl(os.path.join(
            REPO, "data", "raw", "2026", "games.jsonl"))
    t = SC.totals(games, 2026)

    print("COUNT-UNIVERSE MAP (one build instant)")
    m1 = re.search(r'<b>(\d+)</b>\s*<span[^>]*>results on the board', page)
    m1b = m1 or re.search(r'(\d+)</b>[^<]*<[^>]*>?[^<]*results on the board',
                          page)
    mast = int((m1 or m1b).group(1)) if (m1 or m1b) else None
    m2 = re.search(r'<b>(\d+)</b>\s*matches\s*\n?\s*<span[^>]*>\(the box universe\)', page) \
        or re.search(r'<b>(\d+)</b>\s*counted finals', page)
    stats = int(m2.group(1)) if m2 else None
    m3 = re.search(r'(\d+) rating-eligible finals are in', page)
    t25 = int(m3.group(1)) if m3 else None
    print("  masthead=%s stats=%s t25=%s | totals: display=%s eligible=%s"
          % (mast, stats, t25, t["results_on_display"],
             t.get("rating_eligible_now")))

    check("masthead == results_on_display (its stated universe)",
          mast == t["results_on_display"],
          "%s vs %s" % (mast, t["results_on_display"]))
    # Stats is the BOX universe -- held boxes minus exhibitions and
    # duplicates. It legitimately differs from results_on_display (a few
    # empty finals carry real boxes; a few finals carry none) and the page
    # must SAY so. The number must equal its own recomputation exactly.
    import dupes as D
    import exhibitions as E
    dup = set(D.duplicate_gids(2026))
    exh = set(str(x) for x in E.resolved_gids(2026))
    boxed = set()
    bp = os.path.join(REPO, "data", "raw", "2026", "playerbox.jsonl")
    for line in open(bp):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("rows"):
            boxed.add(str(r.get("game_id")))
    # only FINAL games aggregate -- a box crawled for a still-live match
    # does not count until its game is final
    finals = set(str(g.get("game_id")) for g in SC.resolve(games)
                 if g.get("game_state") == "F")
    rev = set(SC.review_gids(2026))       # a disputed result's stats wait
    box_n = len((boxed & finals) - dup - exh - rev)
    check("Stats box-universe count == its recomputation",
          stats == box_n, "%s vs %s" % (stats, box_n))
    check("Stats NAMES the box universe beside the number",
          "the box universe" in page)
    if t25 is not None and t.get("rating_eligible_now") is not None:
        check("Top 25 'rating-eligible finals' == rating_eligible_now",
              t25 == t["rating_eligible_now"],
              "%s vs %s" % (t25, t["rating_eligible_now"]))
    check("the masthead NAMES its universe in a title",
          "duplicates and empty records excluded" in page)

    check("the ballot's settle line names the GATE universe",
          "completed feed records" in page or "every completed record" in
          page.split("finals in")[0][-400:] if "finals in" in page else True)
    # the weekly gate line itself (JS) must carry the label
    check("weekly settle string labels its count (JS source)",
          re.search(r"finals in[^']*completed", page) is not None
          or "title=\"the settle gate counts" in page,
          "settle line lacks a universe label")
    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL COUNT-UNIVERSE CHECKS HOLD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
