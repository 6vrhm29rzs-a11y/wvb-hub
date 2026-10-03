#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repair feed-corrupted player names -- ONE definition, three consumers.

Written 2026-08-30, after the feed served East Carolina's Taryn Gilreath two
ways in consecutive games: '\\u200bTaryn Gilreath' (a leading zero-width
space) and 'A-circumflex \\x80\\x8btaryn Gilreath' (the same zero-width space
as UTF-8 bytes misdecoded through Latin-1, then case-mangled by the feed's
own titlecasing). The aggregate keyed them as two players and split her
season 3+4 kills across two rows.

Used by crawl_2025's aggregate key, build_hub.nkey and player_rating.nkey.
Order matters and is load-bearing:

  1. try the WHOLE-STRING mojibake repair first (round-trip latin-1 ->
     utf-8, plus a case-restored variant) -- names like 'Kria\\x8dkovia\\x87'
     NEED their C1 bytes for the round trip, so stripping first would
     destroy exactly what the repair reads;
  2. only if repair fails, drop each remaining C1 control (U+0080-U+009F)
     TOGETHER WITH the character before it -- that character is the
     misdecoded UTF-8 lead byte, not a letter of anyone's name;
  3. drop format characters (Cf: zero-width space and friends) always.

Pure-ASCII strings pass through byte-for-byte unchanged.
"""

import re
import unicodedata

_C1_PAIR = re.compile(u".[-]+")


def repair(s):
    # type: (str) -> str
    s = s or ""
    if not any(ord(c) > 0x7F for c in s):
        return s
    cased = "".join(
        chr(ord(c) - 0x20)
        if (0xE0 <= ord(c) <= 0xFE and i + 1 < len(s)
            and 0x80 <= ord(s[i + 1]) <= 0xBF)
        else c
        for i, c in enumerate(s))
    for cand in (s, cased):
        try:
            r = cand.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if r != cand:
            s = r
            break
    else:
        s = _C1_PAIR.sub("", s)
    return "".join(c for c in s if unicodedata.category(c) != "Cf")


def join_key(name):
    """THE player identity key -- one definition for every screen (mail 047;
    Analysis had its own letters-only key, which silently merged names the
    player page keeps apart). repair() first, then an NFKD accent fold, then
    lowercase letters only. Pure-ASCII keys are unchanged."""
    import re as _re
    import unicodedata as _ud
    s = repair(name or "")
    if any(ord(c) > 0x7F for c in s):
        s = _ud.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return _re.sub(r"[^a-z]", "", s.lower())


_ID_OVERRIDES = None


def _load_id_overrides():
    global _ID_OVERRIDES
    if _ID_OVERRIDES is None:
        import json as _json
        import os as _os
        _ID_OVERRIDES = {}
        repo = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        p = _os.path.join(repo, "data", "raw", "2026", "player_identity_overrides.json")
        try:
            for o in _json.load(open(p, encoding="utf-8")).get("overrides") or []:
                if not o.get("evidence"):
                    continue                     # an uncited override is ignored
                first, _, last = o["canonical"].partition(" ")
                for g in o.get("gids") or []:
                    _ID_OVERRIDES[(str(g), str(o["team_id"]), o["feed_spelling"])] = (first, last)
        except (OSError, ValueError, KeyError):
            _ID_OVERRIDES = {}
    return _ID_OVERRIDES


def apply_identity_override(row, gid):
    """ONE shared, cited, team-scoped identity repair (mails 051/052).
    Matches only the exact (game, team_id, repaired "first last") listed in
    data/raw/2026/player_identity_overrides.json; returns a COPY with the
    school's spelling and the feed's kept as first_src/last_src. Any other
    row is returned unchanged. Never fuzzy."""
    if not isinstance(row, dict):
        return row
    ov = _load_id_overrides()
    out = row
    nm = ("%s %s" % (repair(row.get("first") or ""), repair(row.get("last") or ""))).strip()
    hit = ov.get((str(gid), str(row.get("team_id")), nm)) if ov else None
    if hit:
        out = dict(row)
        out["first_src"], out["last_src"] = row.get("first"), row.get("last")
        out["first"], out["last"] = hit
        nm = "%s %s" % hit
    # participation overrides share the same single row-override point
    pv = _load_part_overrides().get((str(gid), str(row.get("team_id")), nm))
    if pv:
        out = dict(out)
        out["gp_src"] = out.get("gp")
        out["gp"] = pv["gp"]
        out["participation_corrected"] = pv["label"]
    return out


_PART = None


def _load_part_overrides():
    global _PART
    if _PART is None:
        import json as _json
        import os as _os
        _PART = {}
        repo = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        p = _os.path.join(repo, "data", "raw", "2026", "participation_overrides.json")
        try:
            for o in _json.load(open(p)).get("overrides") or []:
                if o.get("evidence"):
                    _PART[(str(o["gid"]), str(o["team_id"]), o["player"])] = o
        except (OSError, ValueError, KeyError):
            _PART = {}
    return _PART
