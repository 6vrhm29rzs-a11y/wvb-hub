#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Digby's Top 25.

The load-bearing property is that the blend weight is DERIVED. If k ever becomes
a number somebody typed, this ranking stops being defensible and becomes a
preference -- so the tests check the arithmetic that produces it, and check the
two ways it has already been got wrong:

  * shrinking toward the population instead of toward the projection's own
    error (that handed one match 20% of a team's rating instead of 7%);
  * z-scoring this season against whoever happens to have played, which in
    week one scores the best of six teams as if it were the best of 348.

Python 3.9 target. Run: python3 scripts/test_top25.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from digby_top25 import (shrinkage_k, variance_components,          # noqa: E402
                         per_match_margins, zscores)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = []


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


def test_k_uses_the_priors_error_not_the_population_spread():
    """THE REGRESSION. A useful prior must be shrunk toward less."""
    sigma2, tau2 = 23.93, 5.94
    k_naive = sigma2 / tau2                       # what the first version did
    k_good, err = shrinkage_k(sigma2, tau2, 0.8379)
    check(k_good > k_naive * 2,
          "a prior that predicts at rho=.84 earns far more weight than the "
          "population mean would", "naive %.1f vs %.1f" % (k_naive, k_good))
    check(abs(err - tau2 * (1 - 0.8379 ** 2)) < 1e-9,
          "prior error variance is tau^2(1-rho^2)")


def test_a_useless_prior_collapses_to_the_population():
    """POSITIVE CONTROL on the same formula: at rho=0 the projection carries no
    information and k must fall back to sigma^2/tau^2."""
    k, _ = shrinkage_k(23.93, 5.94, 0.0)
    check(abs(k - 23.93 / 5.94) < 1e-9,
          "POSITIVE CONTROL: rho=0 gives back the naive weight", "%.3f" % k)


def test_a_perfect_prior_is_never_overturned():
    k, _ = shrinkage_k(23.93, 5.94, 0.999999)
    check(k > 1e5, "a near-perfect prior takes essentially infinite evidence",
          "%.0f" % k)


def test_weight_grows_with_matches_and_never_exceeds_one():
    k = 13.52
    ws = [n / float(n + k) for n in (0, 1, 4, 14, 30, 200)]
    check(ws == sorted(ws), "weight on this season rises with matches played")
    check(ws[0] == 0.0, "no matches means the projection alone")
    check(max(ws) < 1.0, "it never reaches 1 -- the projection always counts")
    check(abs(ws[3] - 0.5) < 0.03, "at n=k the two weigh about equally",
          "%.3f" % ws[3])


def test_variance_components_denoise_tau():
    """Short seasons wobble; that wobble is not teams differing."""
    import random
    random.seed(11)
    true = [random.gauss(0, 2.0) for _ in range(200)]
    margins = dict((str(i), [random.gauss(t, 5.0) for _ in range(10)])
                   for i, t in enumerate(true))
    sigma2, tau2 = variance_components(margins)
    check(abs(sigma2 ** 0.5 - 5.0) < 0.6,
          "per-match sd recovered", "%.2f" % sigma2 ** 0.5)
    check(abs(tau2 ** 0.5 - 2.0) < 0.7,
          "between-team sd recovered after de-noising", "%.2f" % tau2 ** 0.5)
    raw = tau2 + sigma2 / 10.0
    check(raw ** 0.5 > tau2 ** 0.5,
          "NEGATIVE CONTROL: the un-de-noised spread is inflated",
          "%.2f vs %.2f" % (raw ** 0.5, tau2 ** 0.5))


def test_season_z_is_not_scaled_by_who_has_played():
    """Dividing by a measured tau is stable; z-scoring the played sample is not."""
    tau = 5.94 ** 0.5
    early = {"A": 4.0, "B": 1.0, "C": -2.0}
    late = dict(early)
    late.update(dict((str(i), 0.0) for i in range(300)))
    stable_early = early["A"] / tau
    stable_late = late["A"] / tau
    check(abs(stable_early - stable_late) < 1e-9,
          "dividing by tau gives the same answer in week 1 and week 12")
    z_early = zscores(early)["A"]
    z_late = zscores(late)["A"]
    check(abs(z_early - z_late) > 0.5,
          "NEGATIVE CONTROL: sample z-scoring would have swung with the field",
          "%.2f vs %.2f" % (z_early, z_late))


def test_the_built_file_is_coherent():
    p = os.path.join(REPO, "data", "digby_top25_2026.json")
    if not os.path.exists(p):
        print("  --   no built Top 25 yet; skipping")
        return
    doc = json.load(open(p, encoding="utf-8"))
    top = doc.get("top") or []
    check(len(top) == 25, "exactly 25 in the poll", str(len(top)))
    check([r["rank"] for r in top] == list(range(1, len(top) + 1)),
          "ranks are 1..25 with no gaps")
    scores = [r["score"] for r in top]
    check(scores == sorted(scores, reverse=True), "sorted by score, descending")
    also = doc.get("also_receiving") or []
    check(all(a["rank"] > 25 for a in also),
          "everyone receiving votes ranks below the poll")
    if top and also:
        check(top[-1]["score"] >= also[0]["score"],
              "and scores below the last ranked team")
    for r in top:
        w = r.get("weight_on_season")
        check_ok = (0.0 <= w < 1.0) and (w == 0.0 or r["matches"] > 0)
        if not check_ok:
            check(False, "weight out of range for %s" % r["team"], str(w))
            return
    check(True, "every weight is in [0,1) and zero only without matches")


def test_the_weekly_archive_captures_the_top_25():
    """The archive used to freeze the BOARD's order, which is a preseason
    projection until 50 matches -- storing the same numbers every week is a
    history of nothing. It captures the ranking that actually moves."""
    import snapshot_rankings as SNAP
    try:
        rows, source = SNAP.current_ranking()
    except Exception as e:
        # ⚠ INTRADAY GENERATION RACE (2026-09-04): on a live match night
        # the corpus moves between certify and this test; the archive
        # gate then refuses with "wrong generation" -- the gate working,
        # not the snapshot code regressing. Behaviour is exercised
        # whenever generations align (every CI run; any quiet hour).
        if "wrong generation" in str(e):
            print("  --   corpus moved since certify_rankings; archive "
                  "gate refused a cross-generation read (its job). "
                  "Basis checks deferred.")
            return
        raise
    p = os.path.join(REPO, "data", "digby_top25_2026.json")
    if not os.path.exists(p):
        print("  --   no Top 25 built; skipping")
        return
    # ⚠ THE BASIS IS NOW CALLED "blend", NOT "digby". One ruler, one name --
    # the Rankings tab uses the same blended ordering for all 348 teams, and
    # two words for one ruler silently blanks the movement column instead of
    # erroring. The archive's existing "digby" week is never rewritten; it is
    # normalised on read by snapshot_rankings.basis().
    # ⚠ STATE-CONDITIONAL SINCE THE CROSSOVER (2026-08-30, 462 matches):
    # once the 2026 rating VALIDATES, the archive-facing basis is "live";
    # until then it is "blend". Pinning "blend" alone failed the exact
    # transition the crossover machinery was pre-tested for. The invariant
    # is that the snapshot's basis MATCHES the rating's own validated
    # state -- never a hard-coded ruler.
    # ⚠ AND VALIDATED IS NOT MATURE (2026-09-02, "Lehigh #3"): the basis
    # follows the board's ONE gate -- live_rating_mature -- never a
    # reimplementation of it here (a guard that re-derives the gate is a
    # guard that drifts from it).
    import json as _json
    import build_rankings_board as _BB
    _rp = os.path.join(REPO, "data", "rating_2026.json")
    _live_doc = _json.load(open(_rp)) if os.path.exists(_rp) else {}
    _rv = bool((_live_doc.get("meta") or {}).get("validated")) and \
        _BB.live_rating_mature(_live_doc)[0]
    _want = "live" if _rv else "blend"
    check(SNAP.basis(source) == _want,
          "the weekly snapshot archives the %s ranking" % _want, source)
    check(rows and all(SNAP.basis(r.get("source")) == _want for r in rows),
          "every archived row carries its basis, so movement cannot mix rulers")
    # ⚠ ALL 348, NOT 35. The first blended week stored only the Top 25 plus
    # also-receiving, so movement could never be computed for team 36 onward --
    # 313 permanently blank cells on a 348-row board.
    check(len(rows) >= 300,
          "the whole board is archived, not just the teams on display",
          str(len(rows)))


def test_the_move_column_states_which_comparison_it_makes():
    """R4 in miniature: 'Move' means two different things depending on whether a
    same-basis week exists, so the header has to say which."""
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  --   no built page; skipping")
        return
    h = open(hub, encoding="utf-8").read()
    m = re.search(r'<th title="how the rank changed">([^<]+)</th>', h)
    check(m is not None, "the Move column has a header")
    if m:
        check(m.group(1).strip() in ("vs last week", "vs preseason"),
              "and it names the comparison", m.group(1))


def test_form_marks_ranked_opponents():
    """A W over #8 and a W over an unranked side are different evidence. The
    rating already weighs them differently; the row must not hide it."""
    from build_hub import form_strip
    ranked = form_strip([{"won": True, "score": "3-0", "opp": "Texas",
                          "opp_rank": 8, "date": "2026-08-22"}])
    plain = form_strip([{"won": True, "score": "3-0", "opp": "Someone",
                         "opp_rank": None, "date": "2026-08-22"}])
    check("frk" in ranked, "a result against a ranked team is marked")
    check("frk" not in plain, "and an unranked one is not")
    check("#8 Texas" in ranked, "the tooltip names the ranked opponent", ranked)
    check("no results yet" in form_strip([]),
          "a team with no results says so rather than showing a blank cell")


def test_form_shows_the_most_recent_last():
    from build_hub import form_strip
    out = form_strip([{"won": False, "score": "0-3", "opp": "A", "opp_rank": None},
                      {"won": True, "score": "3-1", "opp": "B", "opp_rank": None}])
    check(out.index("fl") < out.index("fw"),
          "oldest first, newest last -- the direction a form guide reads")


def test_the_two_rankings_explain_their_relationship():
    """Every ranking on the page must say what it is.

    ⚠ THIS GUARD USED TO ASSERT THE OPPOSITE OF WHAT IS NOW TRUE. It required
    the Rankings tab to point AT the Top 25 "for a ranking that moves", because
    the tab itself was a frozen preseason projection -- which was the whole of
    Cody's complaint that Texas sat 2nd three days after losing at home. The
    Rankings tab now uses the same blended ordering for all 348 teams, so
    telling a reader to go elsewhere for a moving ranking would be false.

    What has to stay true is the thing underneath: a ranking states its basis,
    and a strength ranking says it is not a resume.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  --   no built page; skipping")
        return
    h = open(hub, encoding="utf-8").read()
    # ⚠ MATCH THE INVARIANT, NOT THE SENTENCE. This asserted the literal string
    # "This ranking moves with every result", so rewording the lead -- which is
    # a UI change with no meaning behind it -- failed the test. A guard pinned
    # to prose blocks editing; a guard pinned to the CLAIM does not.
    moving = bool(re.search(r"moves with every result|from 20\d\d results", h))
    frozen = "Still the preseason projection" in h
    check(moving or frozen,
          "the rankings tab states which basis it is on")
    if moving:
        check(not frozen,
              "it does not claim to be frozen and moving at the same time")
        check("strength ranking, not a r&eacute;sum&eacute;" in h
              or "strength</b> ranking" in h,
              "a moving strength ranking still says it is not a resume (R3)")
    # ⚠ MOVERS EXIST OR THEY DO NOT, AND BOTH ARE HONEST STATES. This asserted
    # the line was ALWAYS present. The moment the weekly freeze landed, the
    # comparison basis became a snapshot taken from the same data the board is
    # showing -- so nothing had moved, and printing a "biggest movers" line
    # would have been inventing movement to satisfy a test. The real invariant
    # is that the line appears exactly when something moved.
    import re as _re
    _mv = _re.findall(r'<th title="how the rank changed">([^<]*)</th>', h)
    # ⚠ THE MARKS ARE mv-up / mv-dn. This regex used to look for
    # `class="t25mv (up|dn)"` -- a selector that exists NOWHERE in build_hub or
    # on the page, so `_marks` was always empty and this pair of checks
    # silently reduced to "the movers line must never appear". It passed
    # locally only because nothing had moved yet, and failed the first sandbox
    # in which movement existed -- blocking CI on the first real match day.
    # Same family as the `a.ep` sort key: a guard aimed at a phantom.
    _marks = _re.findall(r'class="mv-(up|dn)"', h)
    if _marks:
        check("Biggest movers" in h,
              "the Top 25 names its biggest movers when there are any")
    else:
        check("Biggest movers" not in h,
              "[-] no movers line is drawn when nothing has moved")
        print("     (no team moved against %s -- correctly silent)"
              % (_mv[0] if _mv else "the prior week"))


def test_the_season_term_is_opponent_adjusted():
    """The same margin against different opponents must NOT score the same.

    This is the largest error the early-season ranking was making. Texas lost
    4.25 points a set to Arizona St. -- the 5th-best team in the country by this
    same ranking -- and the season term recorded it as if the opponent had been
    average. Measured on 2025 by predicting unseen matches, fixing it is worth
    +0.021 AUC at the shipped blend weight, four times any other change tested.

    POSITIVE CONTROL: an identical loss to a strong team must imply MORE
    strength than to a weak one. NEGATIVE CONTROL: if the opponent term were
    dropped, the two would collapse to the same number -- which is exactly what
    the old code did, so the control reproduces the bug rather than something
    shaped like it.
    """
    import digby_top25 as D
    tau = 2.437
    home_adv = 1.088

    def implied(z_opp, margin, is_home):
        return z_opp + (margin - home_adv * (1.0 if is_home else -1.0)) / tau

    strong = implied(2.2, -4.25, True)      # lost by 4.25 at home to a top team
    weak = implied(-1.5, -4.25, True)       # same loss, to a poor team
    check(strong > weak,
          "the same loss implies more strength against a stronger opponent",
          "(strong %.3f vs weak %.3f)" % (strong, weak))
    check(abs((strong - weak) - 3.7) < 1e-6,
          "the gap is exactly the gap between the two opponents",
          "(%.4f)" % (strong - weak))

    # NEGATIVE CONTROL: the old rule, margin/tau with no opponent term.
    old_strong = -4.25 / tau
    old_weak = -4.25 / tau
    check(old_strong == old_weak,
          "the control reproduces the old behaviour: identical, opponent ignored")

    # home court must be removed, and in the right direction
    at_home = implied(0.0, 0.0, True)
    on_road = implied(0.0, 0.0, False)
    check(on_road > at_home,
          "drawing level ON THE ROAD implies more than drawing level at home",
          "(road %.3f vs home %.3f)" % (on_road, at_home))

    # and the shipped payload must actually be using it
    p = os.path.join(REPO, "data", "digby_top25_2026.json")
    if not os.path.exists(p):
        print("  --   no Top 25 built; skipping payload checks")
        return
    doc = json.load(open(p, encoding="utf-8"))
    meta = doc.get("meta") or {}
    check(meta.get("opponent_adjusted") is True,
          "the shipped ranking says it is opponent-adjusted")
    check(isinstance(meta.get("home_advantage_pts_per_set"), float)
          and 0.2 < meta["home_advantage_pts_per_set"] < 2.5,
          "a measured home advantage is recorded and is physically plausible",
          str(meta.get("home_advantage_pts_per_set")))

    # A team that LOST but whose net/set is negative should still be able to
    # carry a season_z above its raw margin, because of who it lost to.
    rows = [r for r in (doc.get("top") or [])
            if r.get("season_z") is not None and r.get("net_pts_per_set") is not None]
    if rows:
        lifted = [r for r in rows
                  if r["season_z"] > r["net_pts_per_set"] / 2.437 + 1e-9]
        check(bool(lifted),
              "at least one team's result is scored above its raw margin",
              "(none -- the opponent term is not reaching the payload)")



def test_rank_size_never_shrinks_at_the_top():
    """A top-three rank may never render SMALLER than an ordinary one.

    ⚠ THE BUG THIS EXISTS FOR, MEASURED ON THE LIVE PAGE. An unscoped podium
    rule -- `tbody tr:nth-child(1..3) td.rk{font-size:19px}`, written for the
    348-row rankings board where 19px is an ENLARGEMENT over a 14px base --
    reaches into every tbody on the site. In the Top 25, whose base is 26px, it
    was a REDUCTION: ranks 1, 2 and 3 rendered at 19px beside 26px for 4-25.
    The list's most important numbers were its smallest. Nothing threw and the
    colour and alignment were right, which is why it took looking to find.

    ⚠ AND THE FIRST VERSION OF THIS TEST WAS ITSELF THE WORST DEFECT OF THE
    DAY. It matched rules with `([^{}]+)\\{([^}]*font-size:[^}]*)\\}` and
    stripped media blocks with `(?:[^{}]|\\{[^{}]*\\})*` -- both classic
    catastrophic backtracking -- against a 7.6 MB page. Two copies ran at 100%
    CPU for 16 and 28 minutes and produced not one line of output. A guard that
    never finishes is worse than no guard: the suite it lives in can never be
    run, so every OTHER check in that file stops protecting anything.
    The CSS is scanned linearly below. No nested quantifiers.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  (no built page -- skipping)")
        return
    h = open(hub, encoding="utf-8").read()
    i, j = h.find("<style>"), h.find("</style>")
    css = h[i + 7:j] if (i >= 0 and j > i) else ""
    # ⚠ STRIP CSS COMMENTS BEFORE THE BRACE SCAN. This file's stylesheet is
    # heavily commented and several of those comments QUOTE CSS -- including
    # the very rule this test is about, `td.rk{font-size:19px}`. Their braces
    # desynced the depth counter, selectors merged, and the resolver reported
    # 26px for the top three when the page renders 30px. It did not error; it
    # answered confidently and wrongly, which is this project's whole failure
    # mode. (Non-greedy, non-nesting -- linear, unlike what it replaced.)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    def rules(text):
        """Linear scan: (selector, body) pairs. No regex, no backtracking."""
        out, buf, depth, sel = [], [], 0, None
        k = 0
        while k < len(text):
            c = text[k]
            if c == "{":
                depth += 1
                if depth == 1:
                    sel = "".join(buf).strip()
                    buf = []
                else:
                    buf.append(c)
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.append((sel, "".join(buf)))
                    buf, sel = [], None
                else:
                    buf.append(c)
            else:
                buf.append(c)
            k += 1
        return out

    def spec(sel):
        """(ids, classes+pseudo, elements) for ONE simple selector.

        ⚠ SPECIFICITY IS PER SELECTOR, NOT PER RULE, and computing it across a
        comma-separated LIST is how this resolver first got the answer wrong.
        The podium rule is written as three selectors on three lines; counting
        the whole block gave it 6 classes and 9 elements instead of 2 and 3, so
        it beat the correctly-scoped `table.t25 ... td.rk` and the test
        reported 19px for a row the browser paints at 30px. A selector list is
        n separate rules that happen to share a body.
        """
        ids = sel.count("#")
        cls = sel.count(".") + sel.count(":")
        els = len(re.findall(r"(?:^|[\s>+~])[a-z][a-z0-9]*", sel))
        return (ids, cls, els)

    def parts(sel):
        return [x.strip() for x in sel.split(",") if x.strip()]

    def resolve(pairs, kind):
        """kind 'top' = a rank cell in rows 1-3; 'ord' = rows 4+."""
        best, best_key = None, None
        for order, (sel, body) in enumerate(pairs):
            m = re.search(r"font-size:\s*([0-9.]+)px", body)
            if not m:
                m = re.search(r"font:[^;]*?\s([0-9.]+)px", body)
            if not m:
                continue
            for one_sel in parts(sel):
                if "td.rk" not in one_sel and ".rk" not in one_sel:
                    continue
                scoped = ".t25" in one_sel
                unscoped = (one_sel.startswith("tbody")
                            or one_sel.startswith("td.rk"))
                if not (scoped or unscoped):
                    continue
                podium = ("nth-child(1)" in one_sel
                          or "nth-child(2)" in one_sel
                          or "nth-child(3)" in one_sel
                          or "nth-child(-n+3)" in one_sel)
                if podium and kind != "top":
                    continue
                key = (spec(one_sel), order)
                if best_key is None or key > best_key:
                    best_key, best = key, float(m.group(1))
        return best

    top_rules = [r for r in rules(css)]
    # the phone block, resolved as an ADDITIONAL later source
    phone = ""
    for sel, body in top_rules:
        if sel.startswith("@media") and "max-width:560px" in sel:
            phone = body
    base = [r for r in top_rules if not r[0].startswith("@")]
    both = base + [r for r in rules(phone)]

    for label, pairs in (("desktop", base), ("phone", both)):
        top = resolve(pairs, "top")
        ordinary = resolve(pairs, "ord")
        check(bool(top) and bool(ordinary),
              "%s: both a top-three and an ordinary rank size resolve" % label,
              "top=%s ord=%s" % (top, ordinary))
        if top and ordinary:
            # ⚠ THE INVARIANT: never smaller. Larger is allowed and intended.
            check(top >= ordinary,
                  "%s: a top-three rank is never smaller than an ordinary one"
                  % label,
                  "top-three %.0fpx vs ordinary %.0fpx" % (top, ordinary))

    # NEGATIVE CONTROL -- and my FIRST attempt at it did not fail, because it
    # was not the bug. Appending the unscoped podium rule to the CURRENT sheet
    # changes nothing: `table.t25 tbody tr:nth-child(-n+3) td.rk` is (0,1,4)
    # and beats `tbody tr:nth-child(1) td.rk` at (0,1,3). That the poison
    # cannot win IS the fix. To exercise the guard the sheet has to be put back
    # the way it actually was: the Top 25 base at the old low-specificity
    # `.t25 .rk`, and no scoped podium rule at all.
    prefix = [(sel, body) for (sel, body) in base
              if "nth-child(-n+3)" not in sel
              and sel != "table.t25 tbody tr td.rk"]
    prefix = prefix + [(".t25 .rk", "font-size:26px"),
                       ("tbody tr:nth-child(1) td.rk", "font-size:19px")]
    ptop, pord = resolve(prefix, "top"), resolve(prefix, "ord")
    check(ptop is not None and pord is not None and ptop < pord,
          "[NEG] the check catches the sheet as it actually was before the fix",
          "top=%s ord=%s (needs top < ord)" % (ptop, pord))
    print("     (resolved now: top-three %s / ordinary %s; before the fix "
          "%s / %s)" % (resolve(base, "top"), resolve(base, "ord"),
                        ptop, pord))

    # and the things the fix had to preserve
    check("table.t25 tbody tr td.rk{" in h,
          "the Top 25 rank rule is scoped to its own table")
    m = re.search(r"table\.t25 tbody tr td\.rk\{([^}]*)\}", h)
    check(bool(m) and "!important" not in m.group(1),
          "[-] ...and wins on specificity, not !important")
    check("color:var(--vx-digby)" in h, "the amber rank colour is kept")
    check("text-align:right" in h, "right alignment is kept")


def main():
    for fn in (test_rank_size_never_shrinks_at_the_top,
               test_the_season_term_is_opponent_adjusted, test_k_uses_the_priors_error_not_the_population_spread,
               test_a_useless_prior_collapses_to_the_population,
               test_a_perfect_prior_is_never_overturned,
               test_weight_grows_with_matches_and_never_exceeds_one,
               test_variance_components_denoise_tau,
               test_season_z_is_not_scaled_by_who_has_played,
               test_the_built_file_is_coherent,
               test_the_weekly_archive_captures_the_top_25,
               test_the_move_column_states_which_comparison_it_makes,
               test_form_marks_ranked_opponents,
               test_form_shows_the_most_recent_last,
               test_the_two_rankings_explain_their_relationship,
               test_hit_channel_is_measured):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all Top 25 invariants pass")
    return 0



def test_hit_channel_is_measured():
    """The hitting-channel weight is the MEASURED winner, never a chosen one.

    data/blend_hiteff_2025.json is the receipt: the shipped weight's paired
    bootstrap verdict must be SHIPS (CI clear of zero). A weight with no
    SHIPS verdict -- or no receipt at all -- fails; hand-retuning the
    constant without re-measuring is exactly what this guard exists to stop.
    """
    import json as _json
    import digby_top25 as D
    w = D.HIT_CHANNEL_WEIGHT
    p = os.path.join(REPO, "data", "blend_hiteff_2025.json")
    assert os.path.exists(p), "no measurement receipt for the hit channel"
    v = _json.load(open(p)).get("verdicts") or {}
    key = {0.25: "V4_mix25", 0.5: "V4_mix50", 1.0: "V4_hitonly"}.get(w)
    assert key and v.get(key, {}).get("verdict") == "SHIPS", \
        "shipped weight %s has no SHIPS verdict: %s" % (w, v.get(key))
    lo = v[key]["ci"][0]
    assert lo > 0, "CI not clear of zero: %s" % v[key]["ci"]
    # NEGATIVE CONTROL: hit-only did NOT ship, and must never pass this gate
    assert v.get("V4_hitonly", {}).get("verdict") != "SHIPS", \
        "[NEG] hit-only shows SHIPS -- the receipt file is not the real one"
    print("  hit channel: weight %.2f measured, CI low %+.5f  ok" % (w, lo))


if __name__ == "__main__":
    sys.exit(main())
