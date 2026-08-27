#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The official-source ledger: strict schema, field-level support, and conflicts.

⚠ WHY THIS EXISTS SEPARATELY FROM fixtures.py. The first ledger accepted an
entry that carried ONE quote and overrode FIVE independent facts -- site,
venue, city, state and event -- so nothing tied any single fact to the sentence
that supported it. That is exactly the shape of claim this project refuses
everywhere else: a number is only as good as the thing it was read from.

Three record kinds, and they are not interchangeable:

  CORRECTION  an official source contradicts the NCAA record and we believe it.
              Every overridden field needs its OWN support: url, retrieved
              date, and the exact text it was read from.

  CONFLICT    two official sources disagree with each other. BOTH claims are
              preserved, the fact is rendered unavailable, and the NCAA value
              is NOT quietly preferred. A conflict is not a weaker correction;
              it is a statement that we do not know.

  Both carry `review_by`. ⚠ A SCHEDULE CLAIM IS PERISHABLE. Schools move
  fixtures; a reading from three weeks ago is a historical fact about a web
  page, not a fact about the match. Past its review date an entry stops being
  applied as truth and starts rendering as "verify".

Python 3.9 target.
"""

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── THE ALLOWLIST. A ledger may override these and nothing else. ────────
# ⚠ NOT "any field on the record". An entry naming an unknown field is a typo
# or a misunderstanding, and silently ignoring it would let a correction look
# applied while doing nothing.
OVERRIDABLE = {
    "site":        ("home", "away", "neutral"),      # enumerated
    "venue":       str,
    "city":        str,
    "state_usps":  re.compile(r"^[A-Z]{2}$"),
    "event":       str,
    "start_time_epoch": int,
}

KINDS = ("correction", "conflict")
GID_RE = re.compile(r"^\d{5,9}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# ⚠ HTTPS ONLY, AND A REAL HOST. A source we cannot re-read is not a source.
URL_RE = re.compile(r"^https://[a-z0-9.-]+\.[a-z]{2,}/[^\s\"'<>]*$", re.I)


def _is_date(v):
    if not (isinstance(v, str) and DATE_RE.match(v)):
        return False
    try:
        datetime.date(*[int(x) for x in v.split("-")])
        return True
    except ValueError:
        return False


def _check_value(field, value):
    """Does this value fit the allowlisted type for this field?"""
    spec = OVERRIDABLE.get(field)
    if spec is None:
        return "not an overridable field"
    if isinstance(spec, tuple):
        return None if value in spec else "must be one of %s" % (spec,)
    if spec is str:
        return None if (isinstance(value, str) and value.strip()) else "must be a non-empty string"
    if spec is int:
        return None if isinstance(value, int) and value > 0 else "must be a positive integer"
    if hasattr(spec, "match"):
        return None if (isinstance(value, str) and spec.match(value)) else "malformed"
    return "unsupported spec"


def _check_support(sup):
    """Field-level support: url + retrieved + the exact text."""
    if not isinstance(sup, dict):
        return "support must be an object"
    if not URL_RE.match(str(sup.get("url", ""))):
        return "url must be https and absolute"
    if not _is_date(sup.get("retrieved")):
        return "retrieved must be YYYY-MM-DD"
    txt = sup.get("text")
    if not (isinstance(txt, str) and len(txt.strip()) >= 12):
        return "text must quote the source (>=12 chars)"
    return None


def validate_entry(e):
    # type: (Dict[str, Any]) -> List[str]
    """Every reason this entry is not usable. Empty list means it is."""
    errs = []
    gid = str(e.get("game_id", ""))
    if not GID_RE.match(gid):
        errs.append("game_id %r is malformed" % gid)
    kind = e.get("kind")
    if kind not in KINDS:
        errs.append("kind must be one of %s, got %r" % (KINDS, kind))
    if not _is_date(e.get("review_by")):
        errs.append("review_by must be YYYY-MM-DD")

    if kind == "correction":
        fields = e.get("fields")
        if not isinstance(fields, dict) or not fields:
            errs.append("a correction needs at least one field")
            fields = {}
        support = e.get("support")
        if not isinstance(support, dict):
            errs.append("a correction needs per-field support")
            support = {}
        for f, v in (fields or {}).items():
            bad = _check_value(f, v)
            if bad:
                errs.append("field %r: %s" % (f, bad))
            # ⚠ EVERY OVERRIDDEN FACT NEEDS ITS OWN CITATION.
            if f not in support:
                errs.append("field %r has no support entry" % f)
            else:
                bad = _check_support(support[f])
                if bad:
                    errs.append("support for %r: %s" % (f, bad))
        for f in support:
            if f not in (fields or {}):
                errs.append("support for %r overrides nothing" % f)

    elif kind == "conflict":
        f = e.get("field")
        if f not in OVERRIDABLE:
            errs.append("conflict field %r is not overridable" % f)
        claims = e.get("claims")
        if not isinstance(claims, list) or len(claims) < 2:
            errs.append("a conflict needs at least two cited claims")
            claims = []
        for i, c in enumerate(claims or []):
            if not isinstance(c, dict):
                errs.append("claim %d is not an object" % i)
                continue
            bad = _check_support(c.get("support") or {})
            if bad:
                errs.append("claim %d support: %s" % (i, bad))
            if "value" not in c:
                errs.append("claim %d has no value" % i)
            else:
                bad = _check_value(f, c["value"]) if f in OVERRIDABLE else None
                if bad:
                    errs.append("claim %d value: %s" % (i, bad))
    return errs


def load(path=None, today=None):
    # type: (Optional[str], Optional[str]) -> Dict[str, Any]
    """Read, validate, and split the ledger into what may be applied.

    Returns {corrections, conflicts, stale, invalid} keyed by game id.
    ⚠ NOTHING INVALID IS SILENTLY DROPPED -- it is returned under `invalid`
    with its reasons, and test_ledger.py fails the build on any.
    """
    path = path or os.path.join(REPO, "data/raw/2026/fixture_ledger.json")
    today = today or datetime.date.today().isoformat()
    out = {"corrections": {}, "conflicts": {}, "stale": {}, "invalid": {},
           "entries": []}
    if not os.path.exists(path):
        return out
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except ValueError as exc:
        out["invalid"]["__file__"] = ["not valid JSON: %s" % exc]
        return out

    seen = set()
    for e in doc.get("entries") or []:
        gid = str(e.get("game_id", ""))
        key = "%s:%s:%s" % (gid, e.get("kind"), e.get("field") or "")
        errs = validate_entry(e)
        # ⚠ A DUPLICATE (game, kind, field) IS AN ERROR, NOT A LAST-WINS.
        if key in seen:
            errs.append("duplicate entry for %s" % key)
        seen.add(key)
        if errs:
            out["invalid"].setdefault(gid or "?", []).extend(errs)
            continue
        out["entries"].append(e)
        # ⚠ PERISHABLE. Past review_by it is no longer applied as truth.
        if e["review_by"] < today:
            out["stale"].setdefault(gid, []).append(e)
            continue
        if e["kind"] == "correction":
            out["corrections"][gid] = e
        else:
            out["conflicts"].setdefault(gid, []).append(e)
    return out
