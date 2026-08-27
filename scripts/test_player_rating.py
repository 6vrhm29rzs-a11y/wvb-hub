#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the position-relative player ratings.

WHAT WENT WRONG WHILE BUILDING THIS, in the order it was caught -- each is a
check below, because each was silent:

  1. The reference distribution and the boards included NON-DIVISION-I teams.
     The top middle in the country came out as a Palm Beach Atlantic player and
     the top libero as one from Christian Brothers, both D-II, both with rates
     built against weaker opposition. Nothing errored.
  2. The opponent adjustment was keyed on POSITION as well as name. A player's
     listed position varies match to match, so it matched a minority and Andi
     Jackson was among the misses. It looked like it was working.
  3. The seeded roster path was scored with RAW rates against a scale built
     from ADJUSTED ones -- two different footings, one table.
  4. A player with no prior season got 100% weight on her own sample, which put
     a two-match player 7th in the country.
  5. Two roster lookups guessed the file's field names and both returned an
     EMPTY dict. An empty lookup is indistinguishable from "she has no class
     listed", so every played player's class rendered as a dash and positions
     silently fell back.

Python 3.9 target. Run: python3 scripts/test_player_rating.py
"""

import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-68s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    f = os.path.join(REPO, "data/player_rating_2026.json")
    if not os.path.exists(f):
        print("no ratings built -- run scripts/player_rating.py")
        return 1
    d = json.load(io.open(f, encoding="utf-8"))
    P = d["players"]
    meta = d["meta"]
    import player_rating as PR

    # the built page, read once -- several sections below assert on it
    page = None
    for c in ("Cody/START-HERE.html", "output/vb_dashboard.html"):
        pth = os.path.join(REPO, c)
        if os.path.exists(pth):
            page = io.open(pth, encoding="utf-8").read()
            break


    print("1. STRUCTURE")
    check("there is no cross-position board", meta.get("no_cross_position_board") is True)
    check("every board states a support level and a caveat",
          all(b.get("support") and b.get("caveat") and b.get("support_auc")
              for b in d["boards"].values()), str(list(d["boards"])))
    check("weights on the page match the fitted constants",
          all(d["boards"][p]["weights"] == PR.WEIGHTS[p] for p in d["boards"]),
          "a weight drifted from what was fitted")
    # ⚠ JSON HAS NO TUPLES. Comparing the round-tripped list of lists against
    # the in-code list of tuples failed on a correct build.
    check("the blend is the measured curve, not a formula",
          [list(x) for x in (meta.get("blend") or [])] ==
          [list(x) for x in PR.BLEND] and len(PR.BLEND) >= 6)

    print("\n2. DIVISION I ONLY")
    di = set(t["team"] for t in json.load(io.open(
        os.path.join(REPO, "data/rating_2025.json"), encoding="utf-8"))["teams"])
    bad = sorted(set(p["team"] for p in P if p.get("team") not in di))
    check("no non-Division-I team appears on any board", not bad, str(bad[:4]))

    print("\n3. THE BLEND")
    noplay = [p for p in P if not p.get("matches")]
    check("a player who has not played carries 0% of this season",
          all(p["season_weight"] == 0.0 for p in noplay), "%d" % len(noplay))
    check("...and her POWER is exactly her prior rating",
          all(abs(p["power"] - p["prior_score"]) < 1e-6
              for p in noplay if p.get("prior_score") is not None))
    played = [p for p in P if p.get("matches")]
    check("a played player's season weight is inside the measured range",
          all(0 < p["season_weight"] <= PR.BLEND_CEIL + 1e-9 for p in played),
          "%d played" % len(played))
    # a player with NO prior must be shrunk toward the position average, never
    # taken at face value on a handful of matches
    noprior = [p for p in played if not p.get("has_prior")]
    shrunk = [p for p in noprior
              if abs(p["power"]) <= abs(p["resume_score"]) + 1e-9]
    check("a player with no prior is shrunk toward the position average",
          len(shrunk) == len(noprior), "%d of %d" % (len(shrunk), len(noprior)))

    print("\n4. RESUME IS THIS SEASON ONLY")
    check("nobody without a season line is ranked on the resume board",
          all(p.get("resume_rank") is None
              for p in P if p.get("resume_score") is None))
    check("everyone with a season line IS ranked on it",
          all(p.get("resume_rank") is not None
              for p in P if p.get("resume_score") is not None))

    print("\n5. THE SCHEDULE ADJUSTMENT REACHES EVERYONE")
    withprior = [p for p in P if p.get("prior_sets")]
    adj = [p for p in withprior if p.get("prior_opp_z") is not None]
    check("prior ratings are schedule-adjusted",
          len(adj) >= 0.97 * len(withprior),
          "%d of %d" % (len(adj), len(withprior)))
    check("every position has a measured slope for every feature",
          all(set(PR.OPP_SLOPE[p]) == set(PR.FEATS) for p in PR.OPP_SLOPE))
    check("harder opponents suppress kills at every position",
          all(PR.OPP_SLOPE[p]["kps"] < 0 for p in PR.OPP_SLOPE),
          "a positive kill slope means the sign convention flipped")

    print("\n6. LOOKUPS THAT MUST NOT SILENTLY RETURN NOTHING")
    rc, rp = PR.roster_class(), PR.roster_positions()
    check("roster class lookup is populated", len(rc) > 2000, "%d" % len(rc))
    check("roster position lookup is populated", len(rp) > 800, "%d" % len(rp))
    check("no player is left without a resolvable position",
          meta.get("n_unresolved_position", 0) == 0,
          str(meta.get("n_unresolved_position")))

    print("\n7. THE CONSTRUCTED LINEUPS")
    st = d.get("all_star") or {}
    teams = st.get("teams") or []
    check("three teams are built", len(teams) == 3, str(len(teams)))
    seen = {}
    dupes = []
    for t in teams:
        for sl in t["slots"]:
            pl = sl.get("player")
            if not pl:
                continue
            k = (pl["team_id"], pl["name"])
            if k in seen:
                dupes.append(pl["name"])
            seen[k] = 1
    check("no player appears on two teams", not dupes, str(dupes[:3]))
    check("every slot is filled from its own position",
          all(sl["player"] is None or sl["player"]["pos"] == sl["pos"]
              for t in teams for sl in t["slots"]),
          "a slot borrowed a player from another position")
    # the data file calls it alt_62; only the trimmed page payload renames it
    alt = st.get("alt_62") or st.get("alt")
    check("the 6-2 alternative fields two setters and no opposite",
          alt is not None and
          sum(1 for s in alt["slots"] if s["pos"] == "S") == 2 and
          not any(s["pos"] == "OPP" for s in alt["slots"]),
          str(sorted(s["pos"] for s in (alt or {}).get("slots", []))))

    print("\n8. NEGATIVE CONTROLS -- a test that cannot fail is not a test")
    fake = [{"team": "Palm Beach Atl.", "pos": "MB"}]
    tripped = [p for p in fake if p["team"] not in di]
    check("[NEG] a reintroduced non-D-I player IS caught",
          len(tripped) == 1, str(tripped))
    # the blend must actually move with n, or the curve is being ignored
    w1, w8 = PR.blend_w(1), PR.blend_w(8)
    check("[NEG] the blend curve is not flat", w8 > w1 + 0.15,
          "w(1)=%.3f w(8)=%.3f" % (w1, w8))
    check("[NEG] zero matches earns zero weight", PR.blend_w(0) == 0.0)
    check("[NEG] the blend never fully erases the prior",
          PR.blend_w(400) <= PR.BLEND_CEIL,
          "%.3f" % PR.blend_w(400))

    print("\n9. WHAT THE ACCURACY AUDIT FOUND")
    # (a) the play-by-play source ships some matches TWICE
    pbf = os.path.join(REPO, "data/pbp_player_2025.json")
    if os.path.exists(pbf):
        pb = json.load(io.open(pbf, encoding="utf-8"))
        pm = pb["meta"]
        pts = 0
        for ln in io.open(os.path.join(REPO, "data/raw/2025/games.jsonl"),
                          encoding="utf-8"):
            try:
                g = json.loads(ln)
            except Exception:
                continue
            if g.get("game_state") != "F":
                continue
            for per in (g.get("linescores") or []):
                try:
                    pts += int(per.get("home") or 0) + int(per.get("visit") or 0)
                except Exception:
                    pass
        gap = abs(pm["rallies"] - pts) / float(pts)
        check("rallies extracted match the points actually scored",
              gap < 0.03, "%d vs %d (%.1f%%) -- duplicate matches are back"
              % (pm["rallies"], pts, 100 * gap))
        check("the duplicate-match skip is doing work",
              pm.get("duplicate_matches_skipped", 0) > 500,
              str(pm.get("duplicate_matches_skipped")))
        rows = pb["players"]
        sv = sum(r.get("ev_Serve", 0) for r in rows)
        ac = sum(r.get("ev_Ace", 0) for r in rows)
        se = sum(r.get("ev_Service_error", 0) for r in rows)
        rc = sum(r.get("recv", 0) for r in rows)
        check("serves minus aces minus service errors equals receptions",
              abs((sv - ac - se) - rc) / float(rc) < 0.01,
              "%d vs %d" % (sv - ac - se, rc))
        so = sum(r.get("recv_sideout", 0) for r in rows) / float(rc)
        check("league side-out rate is physically plausible",
              0.45 < so < 0.75, "%.4f" % so)

    # (b) the school's roster outranks the box score on position
    check("position prefers the school's roster over the feed",
          '(rp, "roster") if rp else' in io.open(
              os.path.join(REPO, "scripts/player_rating.py"),
              encoding="utf-8").read(),
          "the feed calls 43 right-side hitters outsides")
    known = {"Olivia Babcock": "OPP", "Kennedy Martin": "OPP"}
    got = {}
    for pl in P:
        if pl.get("name") in known:
            got[pl["name"]] = pl.get("pos")
    check("right-side hitters are not filed as outsides",
          all(got.get(k) == v for k, v in known.items()), str(got))

    # (c) reclassifying a position must NOT orphan her own prior season
    orphan = [pl["name"] for pl in P
              if pl.get("pos_source") == "roster" and pl.get("matches")
              and not pl.get("has_prior") and (pl.get("sets") or 0) > 0]
    reclass = [pl for pl in P if pl.get("name") in known]
    check("a reclassified player keeps her prior season",
          all(pl.get("prior_sets") for pl in reclass),
          str([(p["name"], p.get("prior_sets")) for p in reclass]))
    check("the prior index is keyed without position",
          "prior_by_key[_nkp] = rr" in io.open(
              os.path.join(REPO, "scripts/player_rating.py"),
              encoding="utf-8").read(),
          "keying the prior by position orphans anyone reclassified")

    # (d) ambiguous names get NO prior rather than someone else's (R8)
    check("shared full names are dropped, not merged",
          meta.get("n_prior_ambiguous_names", 0) > 0,
          "14 names are shared by 2+ players among those with 20+ sets")

    print("\n10. ROTATION, PASSING AND ROW")
    six = [pl for pl in P if pl.get("rotation_role") == "six"]
    front = [pl for pl in P if pl.get("rotation_role") == "front"]
    check("both rotation roles are populated",
          len(six) > 200 and len(front) > 20,
          "six=%d front=%d" % (len(six), len(front)))
    # THE CONTROL THAT DEFINES THE SPLIT: never serving and never standing in
    # the back row must be the same fact.
    leak = [pl["name"] for pl in front
            if ((pl.get("pbp") or {}).get("att_back") or 0) > 0]
    check("[NEG] nobody who never serves has a back-row attack",
          not leak, str(leak[:4]))
    # the two splits must be DIFFERENT questions, or one of them is mislabelled
    both = [pl for pl in P
            if pl.get("rotation_role") and pl.get("pass_role")]
    same = sum(1 for pl in both
               if (pl["rotation_role"] == "six") ==
               (pl["pass_role"] == "passer"))
    check("passing role and rotation role are not the same field",
          both and same < 0.9 * len(both),
          "%d of %d identical -- one of them is mislabelled" % (same, len(both)))
    brs = [pl for pl in P if pl.get("back_row_share") is not None]
    check("back-row share is reported only where the slot is one player",
          all(pl["pos"] in ("OH", "OPP", "S") for pl in brs),
          "a middle or libero shares her slot; the serve order cannot say "
          "which of them was on court")
    check("back-row share is a share", all(0 <= pl["back_row_share"] <= 1
                                           for pl in brs))
    oh = [pl["back_row_share"] for pl in brs if pl["pos"] == "OH"]
    if oh:
        mean_oh = sum(oh) / len(oh)
        check("outsides hit a plausible share from the back row",
              0.05 < mean_oh < 0.45, "%.3f" % mean_oh)

    print("\n11. ROTATIONS ARE SCOPED TO ONE SETTER")
    rf = os.path.join(REPO, "data/rotation_sideout_2025.json")
    if os.path.exists(rf):
        rd = json.load(io.open(rf, encoding="utf-8"))
        T = rd["teams"]
        check("every team's rotations name one setter",
              all(v.get("setter") for v in T.values()))
        check("...and state how much of the season she covers",
              all(0 < (v.get("share_of_season") or 0) <= 1
                  for v in T.values()))
        check("all six rotations are present or the team is withheld",
              all(len(v.get("rotations") or {}) == 6 for v in T.values()))
        lo = [k for k, v in T.items()
              if (v.get("share_of_season") or 0) < 0.7]
        print("       %d of %d teams below 70%% setter coverage"
              % (len(lo), len(T)))

    print("\n11b. SETTING AND SERVING ARE CONTEXT, NOT RATING INPUTS")
    # ⚠ MEASURED, AND THE MEASUREMENT SAID NO. Team-relative setting scores
    # 0.380 AUC against All-America -- BELOW CHANCE -- because a primary setter
    # is most of her own baseline. Adding it to the setter rating lowered it
    # from 0.954 to 0.954->0.942, and adding serving too took it to 0.898.
    check("the file records that these are not rating inputs",
          "not_rating_inputs" in meta, "")
    setw = PR.WEIGHTS.get("S") or {}
    check("no setting or serving term leaked into the fitted weights",
          not any(k in setw for k in
                  ("set_kill_rate", "set_kill_rel", "srv_win", "srv_win_rel")),
          str(sorted(setw)))
    sup = [pl for pl in P
           if (pl.get("pass") or {}).get("set_kill_rel_suppressed")]
    kept = [pl for pl in P
            if (pl.get("pass") or {}).get("set_kill_rel") is not None]
    check("a setter who IS her team's baseline gets no comparison",
          len(sup) > 50, "%d suppressed" % len(sup))
    check("...and one who sets a minority still gets one",
          len(kept) > 100, "%d kept" % len(kept))
    both = [pl for pl in P
            if (pl.get("pass") or {}).get("set_kill_rel") is not None
            and (pl.get("pass") or {}).get("set_kill_rel_suppressed")]
    check("[NEG] no player carries both a comparison and its suppression",
          not both, str([pl["name"] for pl in both[:3]]))
    if page:
        check("the card explains a missing comparison rather than going quiet",
              "no one to compare her with" in page)

    print("\n12. THE RATING REACHES THE PLACES IT IS USED")
    if page:
        check("a player card carries her own standing",
              "function ratingHTML" in page and "ratingbox" in page)
        check("...ranked against her position, and it says so",
              "never across positions" in page)
        check("a player with no season line shows no resume rank",
              "no 2026 line yet" in page,
              "ranking her last would be a claim; absent is the fact")
        check("a match names the players to know on both sides",
              "function starsSection" in page and "Players to know" in page)
        # ⚠ THE ORDERING IS THE WHOLE POINT. Sorting a mixed-position list by
        # the RAW rating hands every slot to outsides, whose spread is widest,
        # and silently drops the setter who runs the offence.
        # ⚠ THE SORT HAPPENS SERVER-SIDE, so assert on the builder, not the
        # rendered page. The first version searched the HTML and failed against
        # correct code.
        bh = io.open(os.path.join(REPO, "scripts/build_hub.py"),
                     encoding="utf-8").read()
        i0 = bh.find("def team_stars(")
        seg = bh[i0:i0 + 2500] if i0 > 0 else ""
        check("players to know are ranked by percentile, not raw rating",
              'overall_pct' in seg and '"power"' not in seg.split("sort")[-1][:120],
              "raw scores are on different scales per position, so sorting a "
              "mixed list by them hands every slot to outsides")
        # ⚠ THESE STRINGS ARE ESCAPED AT RENDER TIME, which is right. A tag
        # built with markup in it prints the tags literally on the card.
        i0 = page.find("function relBit")
        check("team-relative text carries no markup",
              i0 < 0 or "<b>" not in page[i0:i0 + 400],
              "esc() will print the tag literally")
        check("a side with no rated players says so",
              "No rated players" in page,
              "hiding one column reads as though nobody there is worth "
              "watching")

    # the payload itself
    tj = page.find("const TEAMS = ") if page else -1
    if tj > 0:
        import re as _re
        nstars = len(_re.findall(r'"stars":', page))
        check("team star lists are actually shipped", nstars > 200,
              "%d teams carry one" % nstars)

    print("\n12b. THE DIRECTORY COVERS DIVISION I, NOT JUST WHO HAS PLAYED")
    if page:
        import re as _re
        n = len(_re.findall(r'"pc":', page.split("const ROSTER = ")[-1][:900000])) \
            if "const ROSTER = " in page else 0
        check("a roster index is shipped", "const ROSTER = " in page)
        check("...covering thousands, not the handful who have played",
              n > 2000, "%d entries seen" % n)
        # ⚠ THE THING THAT HUNG THE TAB. On route entry the query is empty, and
        # rendering ~2,700 rows there froze the renderer -- three times, through
        # two wrong diagnoses (row count, then crests, then per-keystroke
        # re-render). An empty box must render an INVITATION, never a wall.
        check("an empty search renders no not-yet rows",
              "const show = q ? only.slice(0, 40) : []" in page,
              "an empty query must not build the big table")
        check("...and says so instead of going blank",
              "have not been on court yet this season" in page)
        check("the search is debounced",
              "PQ_T = setTimeout(renderPlayers" in page,
              "a keystroke rebuilding a 2,800-row search is the failure mode")
        check("the not-yet table carries no remote crests",
              "logo(r.t, 'sm') + esc(r.t" not in page,
              "each crest is a network request, rebuilt on every keystroke")

    print("\n13. THE PAGE SAYS WHAT IT IS")
    if page:
        check("the view names its season", "Player ratings for the 2026" in page)
        check("it says the lineups are constructed, not awarded",
              "constructed, not voted on" in page)
        check("it states there is no cross-position comparison",
              "another position" in page)
        check("the support caveat is rendered, not just stored",
              "SUPPORT" in page and "prkbadge" in page)
        # ⚠ A ROTATION PROFILE WITHOUT A NAME IS AN AVERAGE OF LINEUPS. The
        # median team used 29 distinct serve orders last season, so the page
        # has to say whose rotations these are and how much of the season they
        # cover, or the six numbers quietly blend several different teams.
        check("the rotation panel names its setter and its coverage",
              "s, covering " in page and "of the season" in page)
        check("...and says a team does not field one fixed six",
              "29 different serve orders" in page)

    if page:
        # ⚠ FIVE BLANK VIEWS AND COUNTING. A top-level `const` read before it
        # is initialised THROWS rather than reading as undefined, and because
        # the throw lands inside the boot sequence the whole view renders empty
        # with nothing on screen saying why. PRK_ORDER did it, PRK_ROLELAB did
        # it, POSFULL did it. A `typeof` guard does not help; only ordering
        # does.
        #
        # ⚠ AND THIS GUARD IS DELIBERATELY DUMB, AFTER TWO CLEVERER ONES
        # FAILED. Comparing declaration position against use position passed a
        # fixture that reproduced the real bug, because the bug is about
        # EXECUTION order, not textual order -- something runs at load and
        # reaches the table before that line has been evaluated. Deciding that
        # statically needs a call graph: there are 52 top-level calls in the
        # page and renderRank() is one of them, so "declared before the first
        # call" would condemn tables that are perfectly safe.
        # So the rule guarded is the FIX that is known to work: these tables
        # live with the payload they belong to. It is a registry, maintained by
        # hand, and a new table has to be added here. That is a real limit and
        # it is written down rather than papered over.
        TABLES = ["PRK_ORDER", "PRK_ROLES", "PRK_ROLELAB", "PRK_PROLELAB",
                  "PRK_FLAB", "POSFULL"]
        anchor = page.find("const PRANK =")
        missing = [t for t in TABLES if ("const %s" % t) not in page
                   and ("let %s" % t) not in page]
        check("every render-helper table still exists", not missing,
              str(missing))
        # ⚠ ANCHOR ON THE GROUP, NOT ON A FIXED WINDOW AFTER `const PRANK`.
        # That declaration carries the whole payload inline -- hundreds of
        # kilobytes of JSON -- so "within 4,000 characters of it" condemned
        # tables that sit directly underneath it.
        pos = {}
        for t in TABLES:
            for kw in ("const", "let"):
                d = page.find("%s %s" % (kw, t))
                if d > 0:
                    pos[t] = d
                    break
        if pos and anchor > 0:
            lo, hi = min(pos.values()), max(pos.values())
            check("render-helper tables sit together, below the payload",
                  lo > anchor and (hi - lo) < 4000,
                  "spread over %d chars; payload at %d, first table at %d"
                  % (hi - lo, anchor, lo))

    print("\n%s" % ("ALL PASS" if not FAILS else "FAILED: %s" % FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
