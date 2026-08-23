#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Digby -- an assistant that answers from THIS hub's data and nothing else.

A dig is the defensive save: the thing that retrieves what looked gone. Digby
digs up the answer.

WHY THE DESIGN IS SHAPED THIS WAY
---------------------------------
This project's whole discipline is: never ship a plausible-looking wrong number
(R1, R5). A bot that invents a stat is WORSE than no bot -- it is confident,
unverifiable at a glance, and it sits next to numbers that were measured. So the
goal here is not "add an LLM", it is to make hallucination structurally hard:

  1. RETRIEVAL, NOT RECALL. The page holds ~2.8 MB (~700k tokens). Nothing reads
     that per question, and it should not: Digby answers from OUR data, not from
     its memory of college volleyball. Each request carries a small, exact fact
     sheet.
  2. FLAT, CITABLE FACTS. The fact sheet is a flat field -> value map, so a
     claim can name exactly where it came from and be checked mechanically.
  3. A GATE ON THE WAY OUT. Every number in the prose must appear in the facts,
     and every cited field must exist. A summary that fails is NOT published --
     the panel shows nothing rather than something unverified.

The gate is the point. It is a mechanical invariant rather than trust, which is
the same move every other guard in this repo makes, and it is why generated
prose can sit beside measured numbers without lowering the page's standard.

Python 3.9 target.
"""

import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
CACHE = os.path.join(REPO, "data", "digby_summaries_%d.json" % SEASON)

MODEL = "claude-opus-5"

# Seasons are always contextual rather than claims about a team, so they are
# allowed in prose without appearing in the facts.
ALLOWED_YEARS = {"2023", "2024", "2025", "2026", "2027"}

# Numbers named in a fact's KEY are as given as numbers in its value.
# `starters_returning_of_six` states the six; "three of six starters return" is
# the natural way to write it and was being rejected as an invented number.
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12}


def _key_numbers(facts):
    # type: (Dict) -> List[float]
    out = []                                            # type: List[float]
    for key in (facts or {}):
        for tok in re.split(r"[^a-z0-9]+", str(key).lower()):
            if tok in _WORD_NUM:
                out.append(float(_WORD_NUM[tok]))
            elif tok.isdigit():
                out.append(float(tok))
    return out


# --------------------------------------------------------------- fact sheet
def _num(v):
    # type: (Any) -> Optional[float]
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fact_sheet(team, rec):
    # type: (str, Dict) -> Dict[str, Any]
    """A flat, citable view of one team.

    FLAT ON PURPOSE. A nested structure makes "which field is this number from?"
    ambiguous, and the gate depends on that question having exactly one answer.
    Anything absent is simply left out rather than defaulted -- a missing
    measurement is not a zero, and Digby must be able to see that it is missing.
    """
    f = {"team": team}                                   # type: Dict[str, Any]

    def put(key, val):
        if val is not None and val != "":
            f[key] = val

    put("conference", rec.get("conf"))
    put("our_rank_2026", rec.get("rank"))
    put("our_rank_2025_final", rec.get("rank25"))
    put("record_2025", rec.get("record25"))
    put("avca_preseason_rank", rec.get("avca"))
    put("rpi_rank_2025_final", rec.get("rpi"))

    ret = rec.get("ret")
    if ret is not None:
        put("returning_production_pct", round(100.0 * ret))

    put("players_returning", rec.get("n_ret"))
    put("players_departed", rec.get("n_dep"))
    put("transfers_in", rec.get("n_tin"))
    put("newcomers_no_di_record", rec.get("n_new"))

    lu = rec.get("lineup") or {}
    put("offense_system_2025", lu.get("offense_system_2025"))
    put("starters_returning_of_six", lu.get("returning_of_six"))
    put("starting_six_vacancies", lu.get("vacancies"))
    put("matches_with_a_known_lineup_2025", lu.get("matches_with_lineup"))

    sim = rec.get("sim") or {}
    put("projected_wins_2026", sim.get("proj_wins_mean"))
    put("projected_wins_low", sim.get("proj_wins_p10"))
    put("projected_wins_high", sim.get("proj_wins_p90"))
    put("conference_title_pct", sim.get("conf_title_pct"))
    put("tournament_odds_pct", sim.get("tournament_pct"))
    put("record_so_far_2026", sim.get("record_so_far"))
    put("matches_played_2026", sim.get("played"))

    for i, c in enumerate((rec.get("rotation") or [])[:6], 1):
        put("top_scorer_%d_name" % i, c.get("name"))
        put("top_scorer_%d_position" % i, c.get("pos"))
        put("top_scorer_%d_points_per_set" % i, c.get("rate"))
        put("top_scorer_%d_status" % i, c.get("kind"))

    for i, s in enumerate((lu.get("usual_six_2025") or [])[:6], 1):
        put("started_%d_name" % i, s.get("name"))
        put("started_%d_position" % i, s.get("pos"))
        put("started_%d_matches_started" % i, s.get("starts_2025"))
        put("started_%d_back_for_2026" % i, s.get("status_2026"))

    # 2026 TEAM STATS, both sides. Added after the box scores started carrying
    # them: Digby was answering "how are they playing" from a preseason
    # projection because nothing else was in front of him.
    ts = rec.get("tstats") or {}
    own, opp = (ts.get("own") or {}), (ts.get("opp") or {})
    put("matches_with_a_box_score_2026", own.get("matches"))
    put("sets_played_2026", own.get("sets"))
    put("hitting_pct_2026", own.get("hit"))
    put("opponent_hitting_pct_2026", opp.get("hit"))
    put("points_per_set_2026", own.get("pps"))
    put("opponent_points_per_set_2026", opp.get("pps"))
    put("kills_per_set_2026", own.get("kps"))
    put("digs_per_set_2026", own.get("dps"))
    put("blocks_per_set_2026", own.get("bps"))
    put("aces_per_set_2026", own.get("aps"))

    # THE SERVING ROTATION, which is the one thing on the page a reader is most
    # likely to ask about and could not previously be answered.
    rot = rec.get("rot25") or {}
    for i, nm in enumerate(rot.get("rotation") or [], 1):
        put("serving_rotation_2025_slot_%d" % i, nm)
    put("rotation_sets_agreeing", rot.get("sets_with_this_rotation"))
    put("rotation_sets_resolved", rot.get("sets_resolved"))

    # How the conference awards its bid, and how much of a season is scheduled.
    aq = rec.get("aq") or {}
    put("conference_bid_awarded_by",
        "conference tournament" if aq.get("mechanism") == "TOURNAMENT"
        else ("regular-season champion" if aq.get("mechanism") else None))
    put("matches_on_the_2026_schedule", rec.get("sched_n"))

    # AVCA honours still on the roster -- the difference between returning a
    # good scorer and returning an All-American.
    dec = [r for r in (rec.get("roster") or []) if r.get("aa")]
    put("players_with_an_avca_honour", len(dec) or None)
    for i, r in enumerate(dec[:6], 1):
        best = sorted(r["aa"], key=lambda x: -x.get("season", 0))[0]
        put("avca_honour_%d_player" % i, r.get("n"))
        put("avca_honour_%d_award" % i, best.get("honour"))
        put("avca_honour_%d_season" % i, best.get("season"))

    for i, d in enumerate((rec.get("top_dep") or [])[:3], 1):
        put("biggest_loss_%d_name" % i, d.get("name"))
        put("biggest_loss_%d_position" % i, d.get("pos"))
        put("biggest_loss_%d_points_2025" % i, d.get("pts"))
        put("biggest_loss_%d_went_to" % i, d.get("to"))

    return f


def input_hash(facts):
    # type: (Dict) -> str
    """Fingerprint of the facts, so a team regenerates only when its numbers
    actually move. A daily rebuild then costs nothing."""
    blob = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------- the gate
# Leading-dot decimals matter here: a hitting percentage is written ".312", and
# a regex that misses the dot silently reads it as the integer 312 -- which then
# gets compared against the wrong things.
# A HYPHEN BETWEEN TWO DIGITS IS A SEPARATOR, NOT A MINUS SIGN. Without the
# lookbehind, "23-7" reads as 23 and MINUS 7, so every record, set score and
# range in prose invents a negative number that is nowhere in the data --
# which is exactly how a truthful Campbell summary was rejected for "-22".
# A real negative still parses, because its minus follows a space, not a digit.
_NUM_RE = re.compile(r"(?<![\w.])-?(?:\d+(?:\.\d+)?|\.\d+)")


def _decimals(tok):
    # type: (str) -> int
    return len(tok.split(".")[1]) if "." in tok else 0


def _fact_numbers(facts):
    # type: (Dict) -> List[float]
    """Every number the facts contain, including ones inside strings -- a
    record of "33-1" legitimately licenses writing 33 and 1."""
    out = []                                            # type: List[float]
    for v in facts.values():
        n = _num(v)
        if n is not None:
            out.append(n)
        if isinstance(v, str):
            for tok in _NUM_RE.findall(v):
                m = _num(tok)
                if m is not None:
                    out.append(m)
    return out


def verify(prose, claims, facts):
    # type: (str, List[Dict], Dict) -> Tuple[bool, List[str]]
    """Check generated text against the facts it was given.

    Two independent checks, both mechanical:
      * every CITED FIELD must exist in the fact sheet
      * every NUMBER in the prose must match some fact value AT THE PRECISION
        IT WAS WRITTEN

    That last clause is the whole trick. Exact string matching rejects honest
    prose -- a model given 4.215 will write "4.22", and 24.54 becomes "24.5" or
    "25". Comparing at the written precision allows the rounding a writer
    actually does while still catching a number that is merely close: the fact
    is 70, so "71%" rounds to 71 and is rejected.

    Returns (ok, problems). One problem fails the whole summary -- partial trust
    in a paragraph is not something a reader can act on.
    """
    problems = []                                       # type: List[str]

    for c in (claims or []):
        field = (c or {}).get("field")
        if not field:
            problems.append("a claim cites no field")
            continue
        if field not in facts:
            problems.append("claim cites unknown field %r" % field)

    nums = _fact_numbers(facts) + _key_numbers(facts)

    # NUMBERS WRITTEN AS WORDS WERE NEVER CHECKED AT ALL. The gate only ever
    # matched digits, so "they return seven of six starters" sailed through
    # while "7 of 6" would have been caught. Found by the negative control on
    # the field-name fix, not by inspection.
    #
    # "one" is deliberately excluded: in prose it is nearly always article-like
    # ("one of the best", "no one"), and checking it would reject honest
    # sentences. That is a judgement about English, not a measured threshold,
    # and it is stated here rather than buried.
    for tok in re.findall(r"[a-z]+", (prose or "").lower()):
        if tok == "one" or tok not in _WORD_NUM:
            continue
        val = float(_WORD_NUM[tok])
        if not any(abs(n - val) <= 1e-9 for n in nums):
            problems.append("the number %r in the text is not in the data" % tok)
    for tok in _NUM_RE.findall(prose or ""):
        if tok in ALLOWED_YEARS:
            continue
        val = _num(tok)
        if val is None:
            continue
        d = _decimals(tok)
        # Half a unit at the written precision. Using round() directly fails on
        # exact halves: 4.215 is stored just under the half, so round(_, 2)
        # gives 4.21 while a writer given 4.215 writes "4.22". Both are honest
        # renderings of the same fact, and a tolerance accepts both without
        # widening the window enough to admit a wrong number -- the fact is 70,
        # so "71" is 1.0 away at precision 0 and still fails.
        tol = 0.5 * (10 ** -d) + 1e-9
        hit = any(abs(n - val) <= tol for n in nums)
        if not hit:
            problems.append("number %s in the text is not in the data" % tok)

    return (not problems), problems


# --------------------------------------------------------------- prompt
SYSTEM = """You are Digby, an assistant inside a personal NCAA Division I
women's volleyball hub. You write a short summary of one team.

ABSOLUTE RULES:
- Use ONLY the facts given to you. You have no other knowledge of this team.
- Never state a number that is not in the facts. Do not compute new numbers,
  do not average, do not convert, do not estimate.
- If something interesting is missing from the facts, say nothing about it.
  Silence is correct; inventing is not.
- Every sentence containing a number must be supported by a claim naming the
  exact field that number came from.

STYLE:
- 2 to 4 sentences. Plain, specific, no hype, no cliches.
- Write for someone who follows the sport closely and reads the numbers.
- Lead with what is most distinctive about this team, not with its rank.
- Do not repeat the team name more than once.
"""

TOOL = {
    "name": "team_summary",
    # strict: the schema is enforced, so a malformed shape is the API's problem
    # rather than something this code has to defend against downstream
    "strict": True,
    "description": "Return the summary and the fields every number came from.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "2-4 sentences about the team, from the facts only.",
            },
            "claims": {
                "type": "array",
                "description": "One entry per number used in the summary.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string",
                                  "description": "Exact fact-sheet field name."},
                        "value": {"type": "string",
                                  "description": "The value as written in the summary."},
                    },
                    "required": ["field", "value"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "claims"],
        "additionalProperties": False,
    },
}


def build_prompt(facts):
    # type: (Dict) -> str
    lines = ["Facts about this team. These are the only facts you have.", ""]
    for k in sorted(facts):
        lines.append("%s: %s" % (k, facts[k]))
    return "\n".join(lines)


# --------------------------------------------------------------- the call
def _client():
    """Anthropic client, or None with a readable reason.

    THE KEY IS NEVER WRITTEN ANYWHERE BY THIS CODE. It is read from the
    environment (or an `ant auth` profile) and used in memory. It is never
    logged, never put in the cache file, never embedded in the page, and the
    public build carries no trace of Digby at all.
    """
    try:
        import anthropic
    except ImportError:
        return None, ("the anthropic SDK is not installed -- "
                      "python3 -m pip install --user anthropic")
    # PREFLIGHT. The SDK constructor succeeds with no credentials and only
    # fails at call time, so without this check a bad key produces one failed
    # request per team -- 348 identical errors, which is what happened the
    # first time this ran. Check the shape once, here, and spend nothing.
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None, ("ANTHROPIC_API_KEY is not set in this shell.\n"
                      "    Get a key at console.anthropic.com -> API keys, then:\n"
                      "    export ANTHROPIC_API_KEY=\'sk-ant-...your real key...\'")
    if key == "..." or set(key) <= set("."):
        return None, ("ANTHROPIC_API_KEY is set to the literal placeholder "
                      "'...' rather than a key.\n"
                      "    Paste the real key from console.anthropic.com -> API keys:\n"
                      "    export ANTHROPIC_API_KEY=\'sk-ant-...your real key...\'")
    if not key.startswith("sk-ant-"):
        return None, ("ANTHROPIC_API_KEY does not look like an Anthropic key "
                      "(they begin sk-ant-). Nothing was sent.")
    try:
        return anthropic.Anthropic(), None
    except Exception as exc:                            # noqa: BLE001
        return None, ("no API credentials found (%s). Set ANTHROPIC_API_KEY in "
                      "your shell before running this." % type(exc).__name__)


def summarise(facts, client=None):
    # type: (Dict, Any) -> Tuple[Optional[Dict], Optional[str]]
    """One team -> (result, error). Result carries the prose and its claims.

    The gate is applied by the CALLER, not here, so that the raw model output
    can be inspected when something fails the check.
    """
    if client is None:
        client, err = _client()
        if client is None:
            return None, err
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(facts)}],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "team_summary"},
            output_config={"effort": "low"},   # summarisation, not analysis
        )
    except Exception as exc:                            # noqa: BLE001
        msg = str(exc)
        # The SDK constructor succeeds without credentials and only fails at
        # call time, so the actionable message has to be produced here.
        if "authentication" in msg.lower() or "api_key" in msg:
            # FATAL, not per-team: the key is wrong for every team, so retrying
            # each one just bills nothing 348 times and buries the message.
            return None, ("FATAL the API rejected the key. Check it at "
                          "console.anthropic.com -> API keys, then re-export it.")
        return None, "%s: %s" % (type(exc).__name__, msg[:200])

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input), None
    return None, "the model returned no structured summary"


# --------------------------------------------------------------- cache
def load_cache():
    # type: () -> Dict
    if not os.path.exists(CACHE):
        return {"meta": {}, "teams": {}}
    try:
        return json.load(open(CACHE))
    except ValueError:
        return {"meta": {}, "teams": {}}


def save_cache(doc):
    # type: (Dict) -> None
    doc.setdefault("meta", {})
    doc["meta"].update({
        "season": SEASON,
        "model": MODEL,
        "source_tier": "DERIVED",
        "note": ("Written by a model from a fact sheet built out of this hub's "
                 "own data, then checked mechanically: every number in the text "
                 "must appear in the facts and every cited field must exist. A "
                 "summary that fails the check is not stored."),
    })
    # ATOMIC. json.dump truncates the file and then fills it, so a reader
    # arriving mid-write sees half a document -- and build_hub.py reads this
    # file, with both running from the same daily workflow. A crash mid-write
    # would also destroy summaries that cost real money to make. Write beside
    # it and rename; os.replace is atomic on this filesystem.
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, CACHE)


# --------------------------------------------------------------- driver
def teams_from_page():
    # type: () -> Dict
    """The same team records the page renders, read back out of the built page.

    Reading the BUILT artifact rather than rebuilding the pipeline means Digby
    summarises exactly what a reader sees -- if the page is stale, so is the
    summary, and there is no third version of the truth to drift.
    """
    page = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(page):
        return {}
    html = open(page, encoding="utf-8").read()
    m = re.search(r"const TEAMS = (\{.*?\});\n", html, re.S)
    return json.loads(m.group(1)) if m else {}


def main():
    argv = sys.argv[1:]
    only = None
    limit = None
    force = "--force" in argv
    for i, a in enumerate(argv):
        if a == "--team":
            only = argv[i + 1]
        elif a == "--limit":
            limit = int(argv[i + 1])

    teams = teams_from_page()
    if not teams:
        print("no built page -- run scripts/build_hub.py first")
        return 1

    doc = load_cache()
    cached = doc.get("teams") or {}
    names = [only] if only else sorted(teams)

    client, err = _client()
    if client is None:
        print(err)
        return 1

    done = skipped = failed = attempted = 0
    for name in names:
        if limit and attempted >= limit:
            break
        rec = teams.get(name)
        if rec is None:
            print("  %-22s not on the page" % name)
            continue
        facts = fact_sheet(name, rec)
        h = input_hash(facts)
        prev = cached.get(name) or {}
        if prev.get("hash") == h and not force:
            skipped += 1
            continue

        attempted += 1
        out, err = summarise(facts, client)
        if out is None:
            print("  %-22s FAILED %s" % (name, err))
            failed += 1
            if (err or "").startswith("FATAL"):
                break
            if failed >= 5 and done == 0:
                print("\n  stopping: 5 failures and nothing written. "
                      "Fix the cause rather than burning the rest of the field.")
                break
            continue

        ok, problems = verify(out.get("summary", ""), out.get("claims") or [], facts)
        if not ok:
            # NOT STORED. A summary that fails the check is not published --
            # the panel shows nothing rather than something unverified.
            print("  %-22s REJECTED %s" % (name, "; ".join(problems[:2])))
            failed += 1
            continue

        cached[name] = {"summary": out["summary"],
                        "claims": out.get("claims") or [],
                        "hash": h, "model": MODEL}
        done += 1
        print("  %-22s ok" % name)

    doc["teams"] = cached
    save_cache(doc)
    print("\nwritten %d, unchanged %d, rejected/failed %d -> %s"
          % (done, skipped, failed, CACHE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
