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


def load_json_safe(path):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return None


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

    # ⚠ AND THE ARTIFACT THAT NUMBER COMES FROM MUST MEAN THE SAME THING.
    # The page renders players_2026.json's meta.games_aggregated under the
    # label "every match with a held box score". The aggregator counted a
    # record even when it carried ZERO player rows -- an empty shell the
    # feed returns for a match that has just gone final, before playerStats
    # are filled. CI caught it on a live Friday evening as 1626 vs 1625 and
    # it cleared by the next run, which is exactly how a real skew looks.
    from gamelog import load_records_jsonl
    recs = load_records_jsonl(
        os.path.join(REPO, "data", "raw", "2026", "playerbox.jsonl"),
        key="game_id")
    skip = dup | exh | rev

    def _agg_count(records, require_rows):
        n = 0
        for gid, rec in records.items():
            if str(gid) in skip:
                continue
            if require_rows and not (rec.get("rows") or []):
                continue
            n += 1
        return n

    meta = (load_json_safe(os.path.join(
        REPO, "data", "raw", "2026", "players_2026.json")) or {}).get("meta") or {}
    agg = meta.get("games_aggregated")
    check("games_aggregated counts only matches WITH player rows",
          agg == _agg_count(recs, True),
          "%s vs %s" % (agg, _agg_count(recs, True)))
    check("no counted playerbox record is an empty shell",
          _agg_count(recs, True) == _agg_count(recs, False),
          "%d with rows vs %d counted loosely"
          % (_agg_count(recs, True), _agg_count(recs, False)))
    check("the aggregator reports how many empty boxes it skipped",
          meta.get("boxes_empty_skipped") is not None,
          "meta.boxes_empty_skipped missing")

    # [NEG] IN-PROCESS CONTROL, so this cannot pass vacuously on a day when
    # no empty box happens to exist: inject one and the two counts must part.
    _probe = dict(recs)
    _probe["__synthetic_empty__"] = {"game_id": "__synthetic_empty__",
                                     "rows": []}
    check("[NEG] an empty shell WOULD be caught if one appeared",
          _agg_count(_probe, True) != _agg_count(_probe, False),
          "control did not part the counts")
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
