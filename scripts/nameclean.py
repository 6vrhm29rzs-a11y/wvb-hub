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
