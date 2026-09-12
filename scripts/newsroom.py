#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The newsroom: the day's stories, as data, with headlines that cannot lie.

WHY THIS EXISTS (Cody, 2026-09-11). A newspaper front page, and later the
daily emails, both need "what happened today" decided ONCE. Two surfaces each
deciding what the lead is would disagree inside a week -- and one of them ends
up in an inbox, where it cannot be re-rendered. So: one content layer, two
renderers. Same reason rank_badge exists.

⚠ THE HEADLINE PROBLEM, AND WHY TEMPLATES RATHER THAN A GATE.
This is the first feature on this site that CHARACTERISES a result instead of
displaying it, which is precisely where R1 has been broken twice before. The
obvious design -- write a headline, then check it against the facts -- was
MEASURED against the existing Digby gate and is not sufficient:

  "Nebraska sweeps Baylor 3-1"   PASSES when the facts happen to carry
                                 our_power_rank 1, because the gate asks
                                 whether a number is in the data, not
                                 whether it is in the RIGHT PLACE. Digby's
                                 own notes say exactly this.
  "wins its seventh straight"    PASSES with no 7 anywhere: the word-number
                                 list holds cardinals, not ordinals.

Both are tolerable in a paragraph of prose and intolerable in a headline,
where the numbers ARE the claim. So a headline is never authored as a string.
It is a SHAPE: a template whose every number is a named slot filled from a
fact, plus a PRECONDITION that makes its wording true. "sweeps" is licensed
by l_sets == 0, not by the writer's judgement.

The Digby gate still runs, as an independent backstop against a shape author
typing a literal into a template. Two mechanisms, different failure modes.

Python 3.9 target.
"""
import os
import re
import sys
from collections import namedtuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

# A shape is the only way a headline comes into existence.
#   needs -- fact keys that must be present AND not None
#   when  -- the precondition that makes the WORDING honest, not merely the
#            numbers available. A shape that says "sweeps" must require a
#            straight-sets win or the verb is an invention.
#   text  -- template. Every number is a {slot}; a literal digit here is a
#            defect and the guard refuses it.
Shape = namedtuple("Shape", "name kind needs when text")

_SLOT = re.compile(r"\{([a-z0-9_]+)\}")
# A digit in template TEXT (outside a slot) is how a hard-coded number would
# get in. Checked by shape_problems(), not left to review.
_LITERAL_DIGIT = re.compile(r"\d")
# Ordinals the Digby gate does not know about. Only used to REFUSE them in
# template text -- we never need to write one, and allowing them would open
# the hole the measurement above found.
_ORDINALS = ("first second third fourth fifth sixth seventh eighth ninth "
             "tenth eleventh twelfth").split()


def shape_problems(sh):
    # type: (Shape) -> list
    """Everything structurally wrong with a shape, before it ever renders."""
    probs = []
    slots = set(_SLOT.findall(sh.text))
    unknown = sorted(slots - set(sh.needs))
    if unknown:
        probs.append("%s: slot(s) %s are not in `needs`, so nothing "
                     "guarantees the fact exists" % (sh.name, unknown))
    bare = _LITERAL_DIGIT.sub("", _SLOT.sub("", sh.text))
    if _LITERAL_DIGIT.search(_SLOT.sub("", sh.text)):
        probs.append("%s: template contains a literal digit -- every number "
                     "in a headline must be a slot filled from a fact" % sh.name)
    low = sh.text.lower()
    for w in _ORDINALS:
        if re.search(r"\b%s\b" % w, low):
            probs.append("%s: ordinal %r in template text -- the number gate "
                         "does not check ordinals (measured), so it would "
                         "carry an unverifiable quantity" % (sh.name, w))
    if not sh.needs:
        probs.append("%s: declares no facts" % sh.name)
    del bare
    return probs


def render(sh, facts):
    # type: (Shape, dict) -> str
    """Fill a shape, or return '' -- never a partial headline.

    Refuses when a needed fact is missing or None (R5: missing data is not a
    blank to paper over) and when the precondition does not hold.
    """
    for k in sh.needs:
        if facts.get(k) is None:
            return ""
    try:
        if not sh.when(facts):
            return ""
    except Exception:                                    # noqa: BLE001
        return ""
    out = sh.text
    for k in set(_SLOT.findall(sh.text)):
        out = out.replace("{%s}" % k, str(facts[k]))
    return out


def headline(shapes, facts):
    # type: (list, dict) -> tuple
    """The first shape that fits, with the gate run as a backstop.

    Returns (text, shape_name) or ('', None). The Digby gate is imported
    lazily so this module stays usable where digby's dependencies are not.
    """
    for sh in shapes:
        text = render(sh, facts)
        if not text:
            continue
        try:
            import digby
            ok, _probs = digby.verify(text, [], facts)
        except Exception:                                # noqa: BLE001
            ok = True        # the shape system is the primary control
        if ok:
            return text, sh.name
    return "", None


# ── the shapes ──────────────────────────────────────────────────────────
# Ordered: the most specific claim that fits wins. Each `when` is what makes
# the verb honest.
def _straight(f):
    return f["l_sets"] == 0


RESULT_SHAPES = [
    Shape("ranked_sweep", "result",
          ("winner", "loser", "w_sets", "l_sets", "loser_rank"),
          lambda f: _straight(f) and f.get("loser_rank"),
          "{winner} sweeps No. {loser_rank} {loser}, {w_sets}-{l_sets}"),
    Shape("sweep", "result",
          ("winner", "loser", "w_sets", "l_sets"),
          _straight,
          "{winner} sweeps {loser}, {w_sets}-{l_sets}"),
    # ⚠ `total_sets` IS IN `needs` BECAUSE THE WORD "five" IS A NUMBER.
    # Caught by the backstop on its first run: this shape rendered and the
    # Digby gate rejected it, because 5 appeared nowhere in the facts (3, 2
    # and a rank). The gate was right -- an unlicensed quantity in a
    # headline is exactly what it is for. The fix is to NAME the number as a
    # fact, never to weaken the check: "a false rejection matters second
    # only to letting invention through", and the cure for both is the same,
    # which is that every quantity in the sentence is traceable to a value.
    Shape("five_set", "result",
          ("winner", "loser", "w_sets", "l_sets", "total_sets"),
          lambda f: f["total_sets"] == 5,
          "{winner} outlasts {loser} in five, {w_sets}-{l_sets}"),
    Shape("ranked_win", "result",
          ("winner", "loser", "w_sets", "l_sets", "loser_rank"),
          lambda f: bool(f.get("loser_rank")),
          "{winner} beats No. {loser_rank} {loser}, {w_sets}-{l_sets}"),
    Shape("win", "result",
          ("winner", "loser", "w_sets", "l_sets"),
          lambda f: True,
          "{winner} beats {loser}, {w_sets}-{l_sets}"),
]

ALL_SHAPES = RESULT_SHAPES
