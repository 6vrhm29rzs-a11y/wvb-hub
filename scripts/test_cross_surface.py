#!/usr/bin/env python3
"""Cross-surface truth reconciliation (architect plan #1, 2026-09-02).

One TruthSnapshot, rebuilt here independently from the season_counts
contract, compared against EVERY reader-facing aggregate: the page's TEAMS
records, the standings payload, the resume artifact, and the rating's
games-played under its stated through-yesterday boundary. Every number a
reader can see must reconcile with the one counting truth -- per TEAM, not
merely in total (the audit manifest already holds the totals; the ranking
incident showed per-team surfaces can rot while totals agree)."""
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_counts as SC  # noqa: E402
from gamelog import load_games_jsonl  # noqa: E402

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def truth():
    """team -> {w, l, matches} (D-I both sides), full and through-yesterday."""
    games = load_games_jsonl(os.path.join(REPO, "data/raw/2026/games.jsonl"))
    cls = SC.classify(games, 2026)
    corr = SC.corrections(2026)
    cut = SC.rating_cutoff_epoch()
    full, cutoff = {}, {}
    for g in SC.resolve(games):
        gid = str(g.get("game_id"))
        if cls.get(gid) != "ok" or g.get("game_state") != "F":
            continue
        g = SC.apply_correction(g, corr)
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        d1_both = all(t.get("division") == 1 for t in ts)
        for t in ts:
            # the ONE hub-name resolution (build_hub._hub_name) -- the
            # dataset's own spelling for New Orleans is the feed's raw
            # 'LSU New Orleans ', and a truth keyed on that misses the page
            import build_hub as _BH
            nm = _BH._hub_name(t.get("name_short"))
            for book, want in ((full, True),
                               (cutoff,
                                (g.get("start_time_epoch") or 0) < cut)):
                if not want:
                    continue
                r = book.setdefault(nm, {"w": 0, "l": 0, "m": 0,
                                         "nw": 0, "nl": 0})
                if d1_both:
                    r["m"] += 1
                    r["w" if t.get("is_winner") else "l"] += 1
                else:
                    r["nw" if t.get("is_winner") else "nl"] += 1
    return full, cutoff


def main():
    full, cutoff = truth()
    page_p = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(page_p):
        print("no built page -- truth snapshot stands alone")
        return
    page = io.open(page_p, encoding="utf-8").read()

    print("1. THE PAGE'S TEAM RECORDS AGAINST THE COUNTING TRUTH")
    # TEAMS payload record26 fields: "record26":"3-1"
    recs = dict(re.findall(r'"([^"]+)":\{"conf":"[^"]*","rank":[^{]*?'
                           r'"record26":"(\d+-\d+)"', page))
    bad = []
    for team, rec in recs.items():
        t = full.get(team)
        want = "%d-%d" % (t["w"], t["l"]) if t else "0-0"
        if rec != want:
            bad.append("%s: page %s vs truth %s" % (team, rec, want))
    check("every TEAMS record26 equals the counting truth (%d teams)"
          % len(recs), not bad, bad[:6])
    check("[+] the extraction found a real population", len(recs) >= 300,
          len(recs))

    print("\n2. THE STANDINGS PAYLOAD AGAINST THE SAME TRUTH")
    m = re.search(r"const STANDINGS = (\{.*?\});\n", page)
    bad2, n2 = [], 0
    if m:
        st = json.loads(m.group(1))
        for conf, rows in st.items():
            for r in rows:
                n2 += 1
                t = full.get(r["team"])
                if not t:
                    continue
                if (r.get("w"), r.get("l")) != (t["w"], t["l"]):
                    bad2.append("%s: standings %s-%s vs truth %s-%s"
                                % (r["team"], r.get("w"), r.get("l"),
                                   t["w"], t["l"]))
                if (r.get("nw") or 0, r.get("nl") or 0) != (t["nw"], t["nl"]):
                    bad2.append("%s: non-D-I %s-%s vs truth %s-%s"
                                % (r["team"], r.get("nw"), r.get("nl"),
                                   t["nw"], t["nl"]))
    check("every standings row equals the counting truth (%d rows)" % n2,
          m and not bad2, bad2[:6])

    print("\n3. THE RATING'S GAMES-PLAYED UNDER ITS STATED BOUNDARY")
    rp = os.path.join(REPO, "data", "rating_2026.json")
    if os.path.exists(rp):
        live = json.load(open(rp))
        bad3 = []
        for t in live.get("teams") or []:
            nm = t.get("team")
            tr = cutoff.get(nm)
            if tr is None:
                continue
            if int(t.get("games_played") or 0) != tr["m"]:
                bad3.append("%s: rating gp %s vs through-yesterday truth %d"
                            % (nm, t.get("games_played"), tr["m"]))
        check("rating games_played equals the through-yesterday truth",
              not bad3, bad3[:6])
    else:
        print("  -- no rating file; boundary check stands down honestly")

    print("\n4. THE MASTHEAD COUNT AGAINST THE CONTRACT")
    tot = SC.totals(load_games_jsonl(os.path.join(
        REPO, "data/raw/2026/games.jsonl")), 2026)
    mm = re.search(r"<b>(\d+)</b> <span[^>]*>results on the board", page)
    check("masthead results equal results_on_display",
          mm and int(mm.group(1)) == tot["results_on_display"],
          (mm and mm.group(1), tot["results_on_display"]))

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL CROSS-SURFACE RECONCILIATIONS HOLD")


if __name__ == "__main__":
    main()
