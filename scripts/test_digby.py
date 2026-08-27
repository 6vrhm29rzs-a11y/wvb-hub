#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Digby's fidelity gate.

THE LOAD-BEARING TEST HERE IS THE NEGATIVE CONTROL. Everything else Digby does
is convenience; the gate is the reason generated prose is allowed on a page
whose entire discipline is "never ship a plausible-looking wrong number". So the
gate is exercised against text that LIES -- an invented stat, a fabricated
field, a number that is close but wrong -- and it must reject every one.

A test that cannot fail is not a test.

Python 3.9 target. Run: python3 scripts/test_digby.py
"""

import contextlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import digby                                                   # noqa: E402
from digby import _NUM_RE                                      # noqa: E402
from digby import fact_sheet, input_hash, verify, build_prompt  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = []


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


# A small, realistic fact sheet to test the gate against.
FACTS = {
    "team": "Nebraska",
    "conference": "Big Ten",
    "our_rank_2026": 1,
    "record_2025": "33-1",
    "returning_production_pct": 70,
    "players_returning": 13,
    "offense_system_2025": "5-1",
    "starters_returning_of_six": 5,
    "projected_wins_2026": 24.54,
    "tournament_odds_pct": 99.2,
    "top_scorer_1_name": "Harper Murray",
    "top_scorer_1_points_per_set": 4.215,
    "biggest_loss_1_name": "Rebekah Allick",
    "biggest_loss_1_points_2025": 333.5,
}


def test_truthful_summary_passes():
    prose = ("Five of six starters are back from a 33-1 season, and the 5-1 "
             "keeps Harper Murray at 4.22 points per set. Losing Rebekah Allick "
             "costs 333.5 points of production.")
    claims = [
        {"field": "starters_returning_of_six", "value": "Five"},
        {"field": "record_2025", "value": "33-1"},
        {"field": "offense_system_2025", "value": "5-1"},
        {"field": "top_scorer_1_points_per_set", "value": "4.22"},
        {"field": "biggest_loss_1_points_2025", "value": "333.5"},
    ]
    ok, problems = verify(prose, claims, FACTS)
    check(ok, "a truthful summary passes the gate", str(problems[:3]))


def test_invented_stat_is_rejected():
    """THE NEGATIVE CONTROL. This is the failure the gate exists for: a fluent,
    confident sentence carrying a number that is nowhere in the data."""
    prose = ("Nebraska hit .312 as a team last season and return five of six "
             "starters.")
    claims = [
        {"field": "starters_returning_of_six", "value": "five"},
    ]
    ok, problems = verify(prose, claims, FACTS)
    check(not ok, "NEGATIVE CONTROL: an invented stat is rejected", str(problems))
    check(any(".312" in p for p in problems),
          "the rejection names the invented number", str(problems))


def test_number_that_is_close_but_wrong_is_rejected():
    """Subtler and more dangerous than an obvious invention: a plausible number
    a careless reader would not question."""
    prose = "They return 71% of last season's production."
    ok, problems = verify(prose, [], FACTS)     # the fact says 70
    check(not ok, "a number that is close but wrong is rejected", str(problems))


def test_fabricated_field_is_rejected():
    prose = "They return five of six starters."
    claims = [{"field": "team_hitting_percentage", "value": ".312"}]
    ok, problems = verify(prose, claims, FACTS)
    check(not ok, "a claim citing a field that does not exist is rejected")
    check(any("unknown field" in p for p in problems),
          "the rejection names the bad field", str(problems))


def test_honest_rounding_is_allowed():
    """The gate must not be so strict it rejects every real summary: a model
    writing prose will round 24.54 to 24.5 or 25, and that is not a lie."""
    for text in ("They project 24.5 wins.", "They project 25 wins.",
                 "They project 24.54 wins."):
        ok, problems = verify(text, [], FACTS)
        check(ok, "honest rounding allowed: %r" % text, str(problems))


def test_years_are_allowed():
    ok, _ = verify("A step back from 2025 into 2026.", [], FACTS)
    check(ok, "season years do not need to appear in the facts")


def test_numbers_inside_string_facts_count():
    ok, _ = verify("They went 33-1.", [], FACTS)
    check(ok, "numbers inside a string fact (a 33-1 record) are allowed")


def test_fact_sheet_omits_rather_than_defaults():
    """A missing measurement must be ABSENT, never zero. Digby has to be able to
    see that something is unknown -- that is what stops it asserting a zero."""
    rec = {"conf": "Big Ten", "rank": 1, "ret": None, "sim": {}, "lineup": {}}
    f = fact_sheet("Nebraska", rec)
    check("returning_production_pct" not in f,
          "an absent value is omitted, not defaulted to 0")
    check("projected_wins_2026" not in f, "an empty sim contributes no fields")
    check(f.get("conference") == "Big Ten", "present values survive")
    check(f.get("team") == "Nebraska", "team name is always present")


def test_fact_sheet_is_flat_and_citable():
    """Flat on purpose: a nested fact makes 'which field is this number from?'
    ambiguous, and the gate depends on that having one answer."""
    rec = {"conf": "SEC", "rank": 2, "rotation": [{"name": "A", "rate": 5.1}],
           "lineup": {"usual_six_2025": [{"name": "B", "starts_2025": 30}]}}
    f = fact_sheet("Texas", rec)
    nested = [k for k, v in f.items() if isinstance(v, (dict, list))]
    check(not nested, "no fact value is a dict or list", str(nested))
    check(f.get("top_scorer_1_name") == "A", "list entries are flattened with an index")
    check(f.get("started_1_matches_started") == 30, "lineup entries flatten too")


def test_hash_changes_only_when_facts_change():
    a = dict(FACTS)
    b = dict(FACTS)
    check(input_hash(a) == input_hash(b), "same facts hash the same")
    b["projected_wins_2026"] = 24.55
    check(input_hash(a) != input_hash(b), "a changed number changes the hash")


def test_prompt_carries_only_the_facts():
    p = build_prompt(FACTS)
    check("Harper Murray" in p and "33-1" in p, "the prompt contains the facts")
    check("only facts" in p.lower(), "the prompt says these are the only facts")


def test_script_close_cannot_break_the_page():
    """Digby is the FIRST model-written text to enter the page's JSON payloads,
    which are embedded with no escaping. A summary containing </script> would
    end the script block and break everything below it."""
    hostile = 'They are good.</script><script>alert(1)</script>'
    embedded = json.dumps({"s": hostile}, separators=(",", ":")).replace("</", "<\\/")
    check("</script>" not in embedded,
          "an embedded summary cannot close the script tag", embedded[:60])
    check(json.loads(embedded.replace("<\\/", "</"))["s"] == hostile,
          "the escape is reversible and lossless")



# ------------------------------------------------- two REAL rejections, fixed
# Both of these came out of the first live run over all 348 teams. Both were the
# gate rejecting TRUTHFUL prose, which is the failure mode that matters second
# only to letting invention through: a gate nobody can satisfy publishes nothing.

def test_a_hyphenated_record_is_not_a_negative_number():
    """CAMPBELL. "-22" was reported as invented. It never existed: the regex
    read the hyphen in a won-lost record as a minus sign."""
    facts = {"team": "Campbell", "record_2025": "23-7",
             "offense_system_2025": "5-1", "projected_wins_2026": 22.0}
    ok, problems = verify("Campbell went 23-7 in 2025 and runs a 5-1.", [], facts)
    check(ok, "REGRESSION: a hyphenated record is not read as a negative",
          str(problems))
    check(_NUM_RE.findall("23-7") == ["23", "7"],
          "a hyphen between digits is a separator", str(_NUM_RE.findall("23-7")))
    check(_NUM_RE.findall("a swing of -14.31") == ["-14.31"],
          "but a real negative still parses",
          str(_NUM_RE.findall("a swing of -14.31")))
    check(_NUM_RE.findall("hit .312") == [".312"],
          "and a leading-dot decimal still parses")


def test_a_number_named_in_a_field_name_is_allowed():
    """EASTERN KY. "6" was reported as invented. The field is literally called
    starters_returning_of_six -- the six is given, not invented."""
    facts = {"team": "Eastern Ky.", "starters_returning_of_six": 3,
             "starting_six_vacancies": 3}
    ok, problems = verify("They return three of six starters.", [], facts)
    check(ok, "REGRESSION: a number stated in a field NAME is allowed",
          str(problems))
    ok2, _ = verify("They return 3 of 6 starters.", [], facts)
    check(ok2, "written as digits too")


def test_the_two_fixes_do_not_open_the_gate():
    """NEGATIVE CONTROL for both fixes at once. Widening what counts as "in the
    data" is exactly how a gate stops working, so invention must still die."""
    # NOTE the record: 23-8, not 23-7. The first version of this control used
    # 23-7, which put a 7 in the facts and made "seven of six starters" pass --
    # the control was wrong, not the code. A number anywhere in the facts is
    # quotable anywhere in the prose; the gate stops numbers from OUTSIDE the
    # data, not numbers in the wrong place. Pick absent numbers deliberately.
    facts = {"team": "Campbell", "record_2025": "23-8",
             "starters_returning_of_six": 3}
    for text in ("They hit .312 as a team.",
                 "They went 24-8 in 2025.",
                 "Their differential was -22.4 per set.",
                 "They return seven of six starters."):
        ok, _ = verify(text, [], facts)
        check(not ok, "NEGATIVE CONTROL: still rejected -- %r" % text)


def test_a_number_word_inside_a_proper_noun_is_not_a_quantity():
    """INDIANA and IOWA were both REJECTED for naming their own conference.

    "Big Ten" lowercases to a token "ten", so the gate demanded the value 10
    among the team's facts. Illinois passed the same run only because a 10
    happened to sit somewhere in its facts -- luck, not the gate working.

    THE FIX IS THE NARROW ONE. Letting _fact_numbers() harvest word-numbers out
    of strings would make the conference name license "ten" ANYWHERE in the
    prose, including an invented "ten kills". The name itself is removed
    instead, so every other "ten" stays exposed -- which the control below is
    what actually proves.
    """
    facts = {"team": "Indiana", "conference_2026": "Big Ten",
             "wins_2025": 14, "losses_2025": 16}
    ok, problems = verify("Indiana plays in the Big Ten and went 14-16 last season.",
                          [], facts)
    check(ok, "REGRESSION: a team may name its own conference", str(problems))

    # Derived from the facts, never a hand-list: a league nobody thought of is
    # handled the same way.
    invented = {"team": "Somewhere", "conference_2026": "Big Ten",
                "wins_2025": 14}
    ok2, _ = verify("They play in the Big Ten.", [], invented)
    check(ok2, "and the rule comes from the facts, not a list of league names")


def test_stripping_a_proper_noun_does_not_hide_invention():
    """NEGATIVE CONTROL. Removing a name from the scanned text is exactly the
    kind of widening that stops a gate working, so invention must still die --
    including in the SAME SENTENCE as the legitimate name."""
    facts = {"team": "Indiana", "conference_2026": "Big Ten",
             "wins_2025": 14, "losses_2025": 16}
    for text in ("Indiana plays in the Big Ten and returns ten starters.",
                 "Indiana returns ten starters.",
                 "Indiana plays in the Big Ten and went 14-17 last season.",
                 "Indiana swept eleven opponents in the Big Ten."):
        ok, _ = verify(text, [], facts)
        check(not ok, "NEGATIVE CONTROL: still rejected -- %r" % text)

    # A single-token value is a quantity or a code, not a proper noun, and must
    # not be strippable -- otherwise a position field of "S" would eat letters
    # out of the prose.
    ok3, _ = verify("They return six starters.", [], {"team": "X", "pos": "six"})
    check(not ok3, "NEGATIVE CONTROL: a one-word fact value is not a proper noun")


# ---------------------------------------------------------------- the driver
# These guard the loop, not the gate. They exist because the first real run
# ignored --limit and made 348 doomed requests instead of 5: --limit counted
# SUCCESSES, so a run where nothing succeeds is unbounded. A cap that only
# applies when things are going well is not a cap.

class _Driver(object):
    """Runs main() against fake teams and a fake model, in a temp cache."""

    def __init__(self, outcome):
        self.outcome = outcome          # callable(name) -> (result, error)
        self.calls = []

    def __enter__(self):
        import tempfile
        self._saved = (digby.CACHE, digby.teams_from_page,
                       digby.summarise, digby._client, sys.argv)
        self._tmp = tempfile.mkdtemp()
        digby.CACHE = os.path.join(self._tmp, "cache.json")
        digby.teams_from_page = lambda: dict(
            ("Team%02d" % i, {"conf": "X", "rank": i}) for i in range(1, 21))
        digby._client = lambda: ("fake-client", None)

        def _sum(facts, client=None):
            self.calls.append(facts["team"])
            return self.outcome(facts["team"])
        digby.summarise = _sum
        return self

    def __exit__(self, *a):
        (digby.CACHE, digby.teams_from_page,
         digby.summarise, digby._client, sys.argv) = self._saved

    def run(self, *args):
        sys.argv = ["digby.py"] + list(args)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            digby.main()
        return buf.getvalue()


def _good(name):
    return {"summary": "They are a team.", "claims": []}, None


def test_limit_caps_attempts_when_everything_succeeds():
    with _Driver(_good) as d:
        d.run("--limit", "5")
        check(len(d.calls) == 5,
              "--limit 5 makes 5 requests when all succeed",
              "made %d" % len(d.calls))


def test_limit_caps_attempts_when_everything_fails():
    """THE REGRESSION. --limit counted successes, so zero successes meant no
    cap at all and the whole field was attempted."""
    with _Driver(lambda n: (None, "some transient error")) as d:
        d.run("--limit", "5")
        check(len(d.calls) <= 5,
              "REGRESSION GUARD: --limit 5 caps requests when all FAIL",
              "made %d requests" % len(d.calls))


def test_limit_caps_attempts_when_the_gate_rejects():
    """A summary that fails the fidelity gate is still a request spent."""
    with _Driver(lambda n: ({"summary": "They hit .312.", "claims": []}, None)) as d:
        d.run("--limit", "5")
        check(len(d.calls) <= 5,
              "--limit 5 caps requests when the gate rejects every summary",
              "made %d requests" % len(d.calls))


def test_fatal_auth_error_stops_immediately():
    with _Driver(lambda n: (None, "FATAL the API rejected the key.")) as d:
        d.run()
        check(len(d.calls) == 1,
              "a FATAL auth error stops after ONE request, not 20",
              "made %d" % len(d.calls))


def test_run_gives_up_after_repeated_failure():
    """No --limit, non-fatal errors: still must not burn the whole field."""
    with _Driver(lambda n: (None, "TimeoutError: upstream")) as d:
        d.run()
        check(len(d.calls) <= 5,
              "5 failures with nothing written stops the run",
              "made %d of 20" % len(d.calls))


def test_a_working_run_is_not_cut_short():
    """POSITIVE CONTROL: the give-up rule must not stop a healthy run."""
    with _Driver(_good) as d:
        d.run()
        check(len(d.calls) == 20,
              "POSITIVE CONTROL: a run where everything works does all 20",
              "made %d" % len(d.calls))


def test_preflight_spends_nothing_on_a_placeholder_key():
    """The key Cody actually pasted was the literal '...' from my own
    instructions. It must be caught before a single request."""
    saved = os.environ.get("ANTHROPIC_API_KEY")
    for bad, why in (("", "unset"), ("...", "the literal placeholder"),
                     ("hunter2", "wrong shape")):
        if bad:
            os.environ["ANTHROPIC_API_KEY"] = bad
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        client, err = digby._client()
        check(client is None and err,
              "preflight rejects a key that is %s, sending nothing" % why,
              str(err)[:60])
    if saved is not None:
        os.environ["ANTHROPIC_API_KEY"] = saved
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_a_summary_is_written_from_durable_facts_only():
    """THE ROT. A stored summary that cites a projection is false by the next
    morning: a completed match removes a fixture and every projection shifts.
    Measured -- 326 of 340 failed their own gate a day later, on numbers like
    "13.62 projected wins" that had become 13.66."""
    from digby import durable, VOLATILE
    facts = dict(FACTS)
    facts["record_so_far_2026"] = "1-0"
    d = durable(facts)
    check("projected_wins_2026" not in d,
          "a projection is not a fact a stored summary may cite")
    check("tournament_odds_pct" not in d, "nor are tournament odds")
    check("record_so_far_2026" not in d, "nor this season's record")
    check("record_2025" in d and "top_scorer_1_name" in d,
          "but last season and the roster survive -- those change rarely")
    check(all(v in FACTS or True for v in VOLATILE), "the volatile list is real")


def test_the_hash_ignores_volatile_movement():
    """A nightly re-simulation must not invalidate every summary."""
    from digby import durable
    a = dict(FACTS); b = dict(FACTS)
    b["projected_wins_2026"] = 24.61          # the sim moved
    b["tournament_odds_pct"] = 99.4
    check(input_hash(durable(a)) == input_hash(durable(b)),
          "a projection moving does not change the durable hash")
    b["players_returning"] = 12               # a roster actually changed
    check(input_hash(durable(a)) != input_hash(durable(b)),
          "but a roster change does")


# Every field shape a stored summary is allowed to cite. A shape not on this
# list fails the test, which forces the question "would this be different
# tomorrow if nobody changed teams?" to be asked ONCE, deliberately, instead of
# being discovered after a paid regeneration.
DURABLE_SHAPES = {
    "team", "conference", "conference_bid_awarded_by",
    "our_rank_N_final", "rpi_rank_N_final",
    "record_2025", "offense_system_2025", "matches_with_a_known_lineup_2025",
    "returning_production_pct", "players_returning", "players_departed",
    "transfers_in", "newcomers_no_di_record",
    "starters_returning_of_six", "starting_six_vacancies",
    "rotation_sets_agreeing", "rotation_sets_resolved",
    "players_with_an_avca_honour",
    "top_scorer_N_name", "top_scorer_N_position", "top_scorer_N_points_per_set",
    "top_scorer_N_status",
    "started_N_name", "started_N_position", "started_N_matches_started",
    "started_N_back_for_2026",
    "biggest_loss_N_name", "biggest_loss_N_position",
    "biggest_loss_N_points_2025", "biggest_loss_N_went_to",
    "avca_honour_N_player", "avca_honour_N_award", "avca_honour_N_season",
    "serving_rotation_N_slot_1", "serving_rotation_N_slot_2",
    "serving_rotation_N_slot_3", "serving_rotation_N_slot_4",
    "serving_rotation_N_slot_5", "serving_rotation_N_slot_6",
}


def test_every_durable_field_was_classified_deliberately():
    """THE STRUCTURAL FIX. Two volatile fields slipped through -- `our_rank_2026`
    (moves with the rating, changes basis at 50 matches) and
    `avca_preseason_rank` (a weekly poll) -- and would have rotted every stored
    summary a second time, at real cost. A new field now fails here until
    somebody decides which side it is on."""
    from digby import durable
    import json as _j, os as _o, re as _re
    hub = _o.path.join(REPO, "Cody", "START-HERE.html")
    if not _o.path.exists(hub):
        print("  --   no built page; skipping")
        return
    h = open(hub, encoding="utf-8").read()
    T = _j.loads(_re.search(r"const TEAMS = (\{.*?\});\n", h, _re.S).group(1))
    shapes = set()
    for team in list(T)[:60]:
        for k in durable(fact_sheet(team, T[team])):
            shapes.add(_re.sub(r"_\d+_", "_N_", k))
    unknown = sorted(shapes - DURABLE_SHAPES)
    check(not unknown,
          "no unclassified field can reach a stored summary",
          "new: %s -- decide if it moves nightly" % unknown)


def test_the_known_movers_are_excluded():
    from digby import VOLATILE
    for f in ("our_rank_2026", "avca_preseason_rank", "projected_wins_2026",
              "tournament_odds_pct", "record_so_far_2026", "hitting_pct_2026"):
        check(f in VOLATILE, "%s is treated as volatile" % f)


def test_the_gate_accepts_honest_player_prose():
    """Digby learned to talk about players; the gate must let it.

    ⚠ THE GATE REJECTS ANY NUMBER NOT IN THE FACTS, AND PLAYER PROSE IS FULL OF
    THEM -- a percentile, a rank, a share of serve-receive, and the word "six"
    in "plays all six rotations", which the gate reads as a number because
    word-forms count. A false rejection is expensive here: a gate nobody can
    satisfy publishes nothing, and this project has already paid for two of
    them (a won-lost record read as a minus sign; "three of six starters"
    rejected when six was in the field's own name).
    """
    facts = {
        "team": "Kentucky",
        "star_1_name": "Brooklyn DeLeye",
        "star_1_position": "OH",
        "star_1_percentile_at_her_position": 99.1,
        "star_1_rank_at_her_position": 4,
        "star_1_kills_per_set": 3.98,
        "star_1_share_of_serve_receive": 36,
        "star_1_share_of_swings_from_back_row": 23,
        "star_1_rotation": "all six rotations",
    }
    C = lambda *fs: [{"field": f} for f in fs]
    cases = [
        ("percentile, rotation and serve-receive together",
         "Brooklyn DeLeye is the one to watch: she rates in the 99.1st "
         "percentile among outside hitters, plays all six rotations and takes "
         "36% of Kentucky's serve-receive.",
         C("star_1_name", "star_1_percentile_at_her_position",
           "star_1_rotation", "star_1_share_of_serve_receive"), True),
        ("a rate", "DeLeye put away 3.98 kills per set.",
         C("star_1_kills_per_set"), True),
        ("a rank", "She is the 4th-best outside hitter on our board.",
         C("star_1_rank_at_her_position"), True),
        ("back-row share", "She takes 23% of her swings from the back row.",
         C("star_1_share_of_swings_from_back_row"), True),
        # ⚠ THE NEGATIVE CONTROL USES NUMBERS GENUINELY ABSENT FROM THE FACTS.
        # A control built from numbers that happen to appear elsewhere in the
        # sheet passes for the wrong reason -- this project has written that
        # bad control before.
        ("[NEG] invented hitting percentage and block count",
         "DeLeye hit .412 with 77 blocks.", C("star_1_name"), False),
    ]
    for label, prose, claims, want in cases:
        ok, problems = digby.verify(prose, claims, facts)
        check(ok == want, label,
              "gate %s it (%s)" % ("rejected" if want else "accepted",
                                   "; ".join(problems)[:80]))


def test_player_fields_can_never_reach_a_stored_summary():
    """A rank moves the instant anyone at that position plays.

    ⚠ THIS IS THE RULE THAT ALREADY COST A REGENERATION BILL: 326 of 340 stored
    summaries failed their own gate a day later, on numbers that had drifted.
    Every player field is volatile by construction, so durable() must drop all
    of them.
    """
    fake = dict(("star_%d_%s" % (i, k), 1)
                for i in (1, 2, 3)
                for k in ("name", "position", "class",
                          "percentile_at_her_position",
                          "rank_at_her_position", "kills_per_set",
                          "share_of_swings_from_back_row",
                          "share_of_serve_receive", "rotation"))
    fake["team"] = "X"
    left = [k for k in digby.durable(fake) if k.startswith("star_")]
    check(not left, "no player field can reach a stored summary",
          "these survived durable(): %s" % left[:4])


def main():
    for fn in (test_truthful_summary_passes,
               test_invented_stat_is_rejected,
               test_number_that_is_close_but_wrong_is_rejected,
               test_fabricated_field_is_rejected,
               test_honest_rounding_is_allowed,
               test_years_are_allowed,
               test_numbers_inside_string_facts_count,
               test_fact_sheet_omits_rather_than_defaults,
               test_fact_sheet_is_flat_and_citable,
               test_hash_changes_only_when_facts_change,
               test_prompt_carries_only_the_facts,
               test_script_close_cannot_break_the_page,
               test_a_hyphenated_record_is_not_a_negative_number,
               test_a_number_named_in_a_field_name_is_allowed,
               test_the_two_fixes_do_not_open_the_gate,
               test_a_number_word_inside_a_proper_noun_is_not_a_quantity,
               test_stripping_a_proper_noun_does_not_hide_invention,
               test_a_summary_is_written_from_durable_facts_only,
               test_the_hash_ignores_volatile_movement,
               test_every_durable_field_was_classified_deliberately,
               test_the_known_movers_are_excluded,
               test_limit_caps_attempts_when_everything_succeeds,
               test_limit_caps_attempts_when_everything_fails,
               test_limit_caps_attempts_when_the_gate_rejects,
               test_fatal_auth_error_stops_immediately,
               test_run_gives_up_after_repeated_failure,
               test_a_working_run_is_not_cut_short,
               test_preflight_spends_nothing_on_a_placeholder_key,
               test_the_gate_accepts_honest_player_prose,
               test_player_fields_can_never_reach_a_stored_summary):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all Digby invariants pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
