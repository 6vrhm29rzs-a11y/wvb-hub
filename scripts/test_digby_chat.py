#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Digby's retrieval -- what gets SENT with a question.

Retrieval is where this can go wrong invisibly. The output gate checks that
every number came from the context; it cannot check that the context was about
the right team. Send Green Bay's record and ask about the WCC and every figure
in the answer is real, cited, and wrong.

Two defects found by writing these, both fixed:
  * "who is the best team in the WCC" retrieved GREEN BAY -- Best is a unique
    surname on its roster, and a bare lowercase word was being read as a name.
  * A conference question sent full records for five teams and let Digby rank
    the league off a third of it.

Synthetic league on purpose: a guard that depends on who is currently on a
roster stops being a guard the moment somebody transfers.

Python 3.9 target. Run: python3 scripts/test_digby_chat.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from digby import verify                                       # noqa: E402
from digby_chat import build_index, retrieve, ask, MAX_QUESTION  # noqa: E402

FAILED = []


def check(cond, label, detail=""):
    if cond:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s %s" % (label, detail))
        FAILED.append(label)


def _team(conf, rank, players):
    return {"conf": conf, "rank": rank, "record25": "20-10",
            "rotation": [{"name": p, "pos": "OH", "rate": 3.5,
                          "kind": "returning"} for p in players],
            "lineup": {}, "sim": {}, "top_dep": []}


# A league with the two traps in it: an ordinary English word as a surname, and
# a surname shared by two players on different teams.
LEAGUE = {
    "Riverton":   _team("Gulf", 1, ["Ana Best", "Kim Delacroix"]),
    "Northfield": _team("Gulf", 2, ["Jo Murray"]),
    "Eastwick":   _team("Gulf", 3, ["Pat Murray"]),
    "Southport":  _team("Gulf", 4, ["Lee Vance"]),
    "Westbury":   _team("Gulf", 5, ["Sam Orr"]),
    "Kingsley":   _team("Gulf", 6, ["Tess Ilo"]),
    "Ashford":    _team("Ridge", 7, ["Nia Quill"]),
    "Barrow":     _team("Ridge", 8, ["Rae Fenn"]),
}
IDX = build_index(LEAGUE)


def test_common_word_surname_does_not_hijack():
    """THE REGRESSION. 'best' is a word before it is a name.

    The question names NO conference on purpose. The first version asked about
    the Gulf, which pulled Riverton in legitimately as the league's top team --
    so the test could not tell a hijack from correct behaviour. A guard that
    cannot distinguish the bug from the fix is not a guard.
    """
    ctx, full = retrieve("who has the best record", LEAGUE, IDX)
    check("Riverton" not in full,
          "REGRESSION GUARD: a lowercase word matching a surname does NOT pull "
          "in that player's team", str(full))
    check(not full, "and nothing is retrieved in full at all", str(full))


def test_an_internal_note_is_not_raised_when_the_question_resolved():
    """Digby volunteered 'the hub flags an ambiguous-surname issue' on an answer
    that worked perfectly. Notes are for explaining a failure, not decorating a
    success."""
    _, full = retrieve("what about jo murray", LEAGUE, IDX)
    ctx, _ = retrieve("what about jo murray", LEAGUE, IDX)
    check(full == ["Northfield"], "the full name resolved", str(full))
    check("note_ambiguous_surnames" not in ctx,
          "and no ambiguity note is attached to a resolved question")
    ctx2, full2 = retrieve("who is the best team in the Gulf", LEAGUE, IDX)
    check("note_unmatched_name" not in ctx2,
          "nor an unmatched-name note when a conference resolved")


def test_capitalised_surname_still_resolves():
    """POSITIVE CONTROL. Without this the fix could be 'never match surnames',
    which would pass the test above and be useless."""
    ctx, full = retrieve("how is Best doing", LEAGUE, IDX)
    check(full == ["Riverton"],
          "POSITIVE CONTROL: a capitalised unique surname resolves", str(full))


def test_ambiguous_surname_resolves_to_nobody():
    ctx, full = retrieve("how did Murray do", LEAGUE, IDX)
    check(not full, "a surname shared by two players retrieves no team", str(full))
    check("note_ambiguous_surnames" in ctx, "and the ambiguity is stated")


def test_full_name_matches_regardless_of_case():
    for q in ("what about jo murray", "what about Jo Murray"):
        ctx, full = retrieve(q, LEAGUE, IDX)
        check(full == ["Northfield"], "a full name resolves: %r" % q, str(full))


def test_conference_question_carries_every_member():
    """A conference is not five of its teams."""
    ctx, full = retrieve("how is the Gulf conference looking", LEAGUE, IDX)
    rows = [k for k in ctx if k.startswith("conference_member.")]
    named = set(k.split(".", 1)[1] for k in rows) | set(full)
    gulf = set(n for n, r in LEAGUE.items() if r["conf"] == "Gulf")
    check(gulf <= named,
          "every Gulf team is present (full record or one-line row)",
          "missing %s" % (gulf - named))
    check(len(full) <= 5, "but only a few carry full records", str(len(full)))


def test_context_is_flat_so_the_gate_works():
    ctx, _ = retrieve("tell me about Riverton", LEAGUE, IDX)
    nested = [k for k, v in ctx.items() if isinstance(v, (dict, list))]
    check(not nested, "no context value is a dict or list", str(nested))
    ok, _ = verify("They are ranked 1.", [], ctx)
    check(ok, "a true number passes the gate against a retrieved context")
    ok, problems = verify("They hit .312 as a team.", [], ctx)
    check(not ok, "NEGATIVE CONTROL: an invented number fails against context",
          str(problems))


def test_longer_team_name_wins():
    league = dict(LEAGUE)
    league["Riverton North"] = _team("Ridge", 9, ["Ivy Pell"])
    idx = build_index(league)
    _, full = retrieve("how is Riverton North doing", league, idx)
    check(full and full[0] == "Riverton North",
          "the longer team name wins over its prefix", str(full))


def test_overview_ships_with_every_question():
    ctx, full = retrieve("who is number one", LEAGUE, IDX)
    check(not full, "a question naming no team retrieves no full record")
    check(any(k.startswith("ranked_") for k in ctx),
          "but the ranked overview is always present")


def test_an_overlong_question_is_refused_before_the_api():
    r = ask("x" * (MAX_QUESTION + 1), teams=LEAGUE, client="must-not-be-used")
    check(r.get("ok") is False, "an overlong question is refused")
    check("under" in r.get("answer", ""), "and says what the limit is")


def test_an_empty_question_is_refused_before_the_api():
    r = ask("   ", teams=LEAGUE, client="must-not-be-used")
    check(r.get("ok") is False, "an empty question is refused without an API call")


def test_the_prompt_forbids_field_names_in_the_prose():
    """Real usage put snake_case straight on the page: "5.06 points per set
    (top_scorer_2_points_per_set)". The claims list already carries provenance
    and is checked mechanically; the reader is looking at a volleyball page."""
    import digby_chat
    sysp = digby_chat.SYSTEM
    check("NEVER" in sysp and "write a field name in the answer" in sysp,
          "the system prompt forbids field names in the prose")
    check("Do not describe your own retrieval" in sysp,
          "and forbids narrating its own retrieval")
    check("note_" in sysp and "INTERNAL" in sysp,
          "and marks note_ fields as internal rather than as facts")


def main():
    for fn in (test_common_word_surname_does_not_hijack,
               test_an_internal_note_is_not_raised_when_the_question_resolved,
               test_capitalised_surname_still_resolves,
               test_ambiguous_surname_resolves_to_nobody,
               test_full_name_matches_regardless_of_case,
               test_conference_question_carries_every_member,
               test_context_is_flat_so_the_gate_works,
               test_longer_team_name_wins,
               test_overview_ships_with_every_question,
               test_an_overlong_question_is_refused_before_the_api,
               test_an_empty_question_is_refused_before_the_api,
               test_the_prompt_forbids_field_names_in_the_prose):
        print(fn.__name__)
        fn()
    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), FAILED))
        return 1
    print("all Digby retrieval invariants pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
