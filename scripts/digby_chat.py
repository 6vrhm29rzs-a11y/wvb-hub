#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Digby, phase 2 -- answering a typed question from THIS hub's data.

    python3 scripts/digby_chat.py "how does Nebraska's rotation look for 2026?"

WHY RETRIEVAL AND NOT "JUST SEND THE PAGE"
------------------------------------------
The built page carries ~2.8 MB (~700k tokens) of team records. Sending it per
question would be slow and expensive, but the real objection is different: a
model given everything answers from a blur of it, and this project's standard is
that every number on screen was measured. So a question is matched against an
index of team names, conferences and player names, and ONLY the matched records
are sent -- typically 2-6 KB.

THE SAME GATE AS THE SUMMARIES. Every number in the answer must appear in the
context that was supplied, at the precision it was written, and every cited
field must exist. An answer that fails is not shown. This is `digby.verify()`
unchanged -- the merged context is a flat field -> value map exactly like a
single team's fact sheet, so the check does not need a second implementation.

"THAT IS NOT IN THE DATA" IS A REAL ANSWER. The system prompt says so and the
tool schema has a field for it. A question the hub cannot answer must produce a
refusal, not a guess -- most of what a volleyball fan would ask (injuries, who
looked good in warmups, transfer rumours) is genuinely absent here, and saying
so is the honest output.

R8 APPLIES TO RETRIEVAL TOO. A surname is only matched when it is unique across
the whole league. Two players share a surname and the wrong one is retrieved,
the numbers all check out against the wrong person's record, and the answer
reads perfectly -- the same failure mode the join rules exist to stop.

Python 3.9 target.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import digby                                            # noqa: E402
from digby import fact_sheet, teams_from_page, verify, _client, MODEL  # noqa: E402

# A question is one line of text. Anything longer is not a question, and the
# cap also bounds what a stray paste can cost.
MAX_QUESTION = 500

# How many teams may be pulled in full. A question naming eight teams is asking
# for a table, not a sentence; the ranked overview below covers that case at a
# fraction of the size.
MAX_TEAMS = 5

# The compact league overview that ships with EVERY question, so that "who is
# number one" and "who wins the Big Ten" work without naming a team.
OVERVIEW_N = 25


# ------------------------------------------------------------------ index
def _norm(s):
    # type: (str) -> str
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def build_index(teams):
    # type: (Dict) -> Dict[str, Any]
    """name -> team lookups, built once per process.

    Player names come from the same three lists the page renders (top scorers,
    the usual starting six, biggest departures), so anyone Digby can be asked
    about is someone the reader can see.
    """
    by_team = {}                                        # type: Dict[str, str]
    by_conf = {}                                        # type: Dict[str, List[str]]
    by_player = {}                                      # type: Dict[str, set]
    by_surname = {}                                     # type: Dict[str, set]

    for name, rec in teams.items():
        by_team[_norm(name)] = name
        conf = _norm(rec.get("conf") or "")
        if conf:
            by_conf.setdefault(conf, []).append(name)

        people = []
        people += [p.get("name") for p in (rec.get("rotation") or [])]
        people += [p.get("name") for p in ((rec.get("lineup") or {})
                                           .get("usual_six_2025") or [])]
        people += [p.get("name") for p in (rec.get("top_dep") or [])]
        for p in people:
            if not p:
                continue
            by_player.setdefault(_norm(p), set()).add(name)
            parts = _norm(p).split()
            if len(parts) > 1:
                by_surname.setdefault(parts[-1], set()).add(p)

    return {"team": by_team, "conf": by_conf,
            "player": by_player, "surname": by_surname}


def _row(name, rec):
    # type: (str, Dict) -> str
    """One team on one line -- rank, conference, both seasons' records."""
    rank = rec.get("rank")
    row = "#%s %s (%s)" % (rank if isinstance(rank, int) else "unranked",
                           name, rec.get("conf") or "?")
    sim = rec.get("sim") or {}
    if sim.get("record_so_far"):
        row += ", %s in 2026" % sim["record_so_far"]
    if rec.get("record25"):
        row += ", %s in 2025" % rec["record25"]
    return row


def _overview(teams):
    # type: (Dict) -> Dict[str, Any]
    """The ranked field, one short row each. Ships with every question."""
    ranked = [(r.get("rank"), n) for n, r in teams.items()
              if isinstance(r.get("rank"), int)]
    return dict(("ranked_%02d" % rank, _row(name, teams[name]))
                for rank, name in sorted(ranked)[:OVERVIEW_N])


def retrieve(question, teams, index=None):
    # type: (str, Dict, Optional[Dict]) -> Tuple[Dict[str, Any], List[str]]
    """question -> (flat context, which teams were sent in full).

    Flat and prefixed by team, so `verify()` works on it unchanged and a claim
    can name exactly one field.

    A CONFERENCE IS NOT FIVE OF ITS TEAMS. Sending full records for the first
    few and letting Digby answer "who is best in the Big Ten" would produce a
    confident ranking of a third of the league -- right-looking, wrong, and
    invisible to the gate, since every number it quoted would be real. So a
    named conference contributes a ONE-LINE row for every one of its members,
    and full records only for the few at the top. Breadth where the question is
    about a field, depth where it is about a team.
    """
    index = index or build_index(teams)
    q = _norm(question)
    padded = " %s " % q
    named = []                                          # type: List[str]
    confs = []                                          # type: List[str]

    def add(bucket, item):
        if item not in bucket:
            bucket.append(item)

    # Longest names first: "Miami (OH)" must not lose to "Miami (FL)" because
    # one happened to be scanned earlier.
    for key in sorted(index["team"], key=len, reverse=True):
        if key and (" %s " % key) in padded:
            add(named, index["team"][key])

    for key in index["conf"]:
        if key and (" %s " % key) in padded:
            add(confs, key)

    for key, names in index["player"].items():
        if key and (" %s " % key) in padded:
            for n in names:
                add(named, n)

    # A bare surname, on two conditions, both necessary.
    #
    #   (a) UNIQUE league-wide. Four players are called Murray, so "how did
    #       Murray do" has no answer and must not be given one -- the numbers
    #       would all check out against the wrong person, which is exactly the
    #       failure R8 exists to stop.
    #   (b) CAPITALISED in what was actually typed. Measured: "who is the best
    #       team in the WCC" retrieved GREEN BAY, because Best is a unique
    #       surname on its roster. Roughly a quarter of surnames here are also
    #       ordinary words -- Best, Ball, Battle, Beach, Archer -- so a bare
    #       lowercase token is not evidence that a person was meant.
    #
    # Capitalisation is the signal a writer already gives for a proper noun. It
    # needs no word list (the system dictionary is useless here: it holds
    # Murray, Anderson and Alexander, so it would block real names), and it
    # fails toward "not found" rather than toward the wrong player. A FULL name
    # still matches in any case -- two tokens is evidence on its own.
    capitalised = set(_norm(w) for w in re.findall(r"\b[A-Z][A-Za-z'-]+", question or ""))
    ambiguous = []                                      # type: List[str]
    unresolved = []                                     # type: List[str]
    for sur, people in index["surname"].items():
        if not sur or (" %s " % sur) not in padded:
            continue
        if len(people) > 1:
            ambiguous.append(sur)
        elif sur in capitalised:
            for n in index["player"].get(_norm(list(people)[0]), ()):
                add(named, n)
        else:
            unresolved.append(sur)

    # Members of every named conference, one line each -- the whole league.
    members = []                                        # type: List[str]
    for c in confs:
        for n in index["conf"][c]:
            add(members, n)

    def _rank(n):
        r = teams[n].get("rank")
        return r if isinstance(r, int) else 10 ** 6

    # With no team named, the conference's own leaders get the full treatment.
    full = list(named)
    for n in sorted(members, key=_rank):
        if len(full) >= MAX_TEAMS:
            break
        add(full, n)
    full = full[:MAX_TEAMS]

    ctx = {}                                            # type: Dict[str, Any]
    for name in full:
        for k, v in fact_sheet(name, teams[name]).items():
            ctx["%s.%s" % (name, k)] = v
    for name in sorted(members, key=_rank):
        if name not in full:
            ctx["conference_member.%s" % name] = _row(name, teams[name])
    ctx.update(_overview(teams))

    if confs:
        ctx["note_conference_coverage"] = (
            "every member of %s is listed; only the top few carry full records"
            % ", ".join(teams[n].get("conf") or "?" for n in full[:1] or members[:1]))
    # Only worth saying when nothing else resolved. "harper murray" resolves
    # perfectly well, and appending "the hub flags an ambiguous-surname issue"
    # to that answer is noise about machinery the reader did not ask about.
    if ambiguous and not named:
        ctx["note_ambiguous_surnames"] = (
            "more than one player has the surname %s, so no single player was "
            "looked up -- ask with the full name."
            % ", ".join(sorted(set(ambiguous))))
    # Same rule, and it matters more here: "who is the best team in the ICC"
    # made Digby volunteer that "best" might have been an uncapitalised
    # surname. True, and completely irrelevant to what was asked.
    if unresolved and not named and not confs:
        ctx["note_unmatched_name"] = (
            "%s may be a surname but was not capitalised, so it was read as an "
            "ordinary word and no player was looked up."
            % ", ".join(sorted(set(unresolved))))
    return ctx, full


# ------------------------------------------------------------------ ask
SYSTEM = """You are Digby, an assistant inside a personal NCAA Division I
women's volleyball hub. You answer ONLY from the context supplied with the
question. That context is the whole of what you know.

Rules, in order of importance:
1. NEVER state a number that is not in the context. Not from memory, not
   estimated, not derived. Every figure you write must appear in the context.
2. If the context does not answer the question, say so plainly and say what
   would be needed. "That isn't in the hub's data" is a correct and useful
   answer -- injuries, recruiting, coaching changes and anything about how a
   team looked are genuinely not here.
3. Cite the exact field name behind every number in the CLAIMS list. NEVER
   write a field name in the answer itself. "5.06 points per set" is right;
   "5.06 points per set (top_scorer_2_points_per_set)" is not -- the reader is
   a person looking at a volleyball page, not a schema. The claims list is
   where the provenance goes and it is checked mechanically.
4. Do not describe your own retrieval. No "the data I have loaded", no "the
   context contains". Answer, or say the hub does not have it.
5. Context fields whose names begin `note_` are INTERNAL notes about the
   lookup, not facts about volleyball. Mention one only when it directly
   explains why you cannot answer -- never as an aside on an answer that
   worked.
6. Be brief and concrete. Two to five sentences. Speak like someone who watches
   volleyball -- rotation, the pin, serve-receive -- not like a report.
7. Field names carry their season (2025 vs 2026). Never present one season's
   number as the other's. Early-season 2026 rates rest on very few sets; if you
   quote one, say how few.
"""

TOOL = {
    "name": "digby_answer",
    "description": "Answer the question from the supplied context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string",
                       "description": "The answer, 2-5 sentences."},
            "answered": {"type": "boolean",
                         "description": "False if the context does not contain "
                                        "what the question asks for."},
            "claims": {
                "type": "array",
                "description": "Every number used, with the field it came from.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["field", "value"],
                },
            },
        },
        "required": ["answer", "answered", "claims"],
    },
}


def build_prompt(question, ctx):
    # type: (str, Dict) -> str
    lines = ["These are the ONLY facts you may use:", ""]
    for k in sorted(ctx):
        lines.append("%s = %s" % (k, ctx[k]))
    lines += ["", "Question: %s" % question]
    return "\n".join(lines)


def ask(question, teams=None, client=None, index=None):
    # type: (str, Optional[Dict], Any, Optional[Dict]) -> Dict[str, Any]
    """The whole round trip. Always returns a dict -- never raises at a caller."""
    question = (question or "").strip()
    if not question:
        return {"ok": False, "answer": "Ask me something about the hub's data."}
    if len(question) > MAX_QUESTION:
        return {"ok": False,
                "answer": "That is longer than a question -- keep it under %d "
                          "characters." % MAX_QUESTION}

    teams = teams_from_page() if teams is None else teams
    if not teams:
        return {"ok": False,
                "answer": "No built page to read -- run scripts/build_hub.py."}

    ctx, matched = retrieve(question, teams, index)

    if client is None:
        client, err = _client()
        if client is None:
            return {"ok": False, "answer": err}

    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1500, system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(question, ctx)}],
            tools=[TOOL], tool_choice={"type": "tool", "name": "digby_answer"},
            output_config={"effort": "low"},
        )
    except Exception as exc:                            # noqa: BLE001
        msg = str(exc)
        if "authentication" in msg.lower() or "api_key" in msg:
            return {"ok": False,
                    "answer": "The API rejected the key. Check it at "
                              "console.anthropic.com -> API keys."}
        return {"ok": False, "answer": "%s" % type(exc).__name__}

    out = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            out = dict(block.input)
            break
    if out is None:
        return {"ok": False, "answer": "No structured answer came back."}

    prose = out.get("answer", "")
    ok, problems = verify(prose, out.get("claims") or [], ctx)
    if not ok:
        # NOT SHOWN. Same rule as the summaries: an answer that fails the check
        # is withheld rather than shown with a caveat, because a caveat next to
        # a confident number is not something a reader can act on.
        return {"ok": False,
                "answer": "I had an answer but it did not check out against the "
                          "data, so I am not showing it.",
                "problems": problems[:3], "teams": matched}

    return {"ok": True, "answer": prose, "answered": bool(out.get("answered")),
            "claims": out.get("claims") or [], "teams": matched,
            "context_fields": len(ctx)}


def main():
    q = " ".join(sys.argv[1:])
    if not q:
        print('usage: python3 scripts/digby_chat.py "your question"')
        return 1
    r = ask(q)
    print(r.get("answer", ""))
    if r.get("teams"):
        print("\n  [retrieved: %s]" % ", ".join(r["teams"]))
    if r.get("problems"):
        print("  [%s]" % "; ".join(r["problems"]))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
