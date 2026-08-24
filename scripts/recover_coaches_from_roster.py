#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Head coaches from the page we already know works: the team's own ROSTER page.

    python3 scripts/recover_coaches_from_roster.py [Team ...]
        -> data/raw/{SEASON}/coaches_from_roster_{SEASON}.json

WHY THIS EXISTS. `crawl_coaches.py` reads /sports/<vb>/coaches and found 296 of
348. The other 52 are the biggest programmes in the sport -- Nebraska, Kentucky,
Stanford, UCLA, Penn St. -- and the reason is not that their pages are
JavaScript-rendered. It is that THE PATH DOES NOT EXIST: every /coaches,
/staff, /coaching-staff and /staff-directory variant under their volleyball
section returns 404, including the ones derived from their own working roster
URL. On those templates the coaching staff is a SECTION OF THE ROSTER PAGE.

Which is a page this project already fetches successfully for 346 of 348 teams.
So this reads no new kind of source and needs no new permission -- it re-reads a
document we already have a working URL for, and looks further down it.

⚠ IT WRITES ITS OWN FILE AND NEVER TOUCHES `coaches_found_2026.json` OR
`coaches_2026.json`. Same discipline as crawl_roster_positions.py: a recovery
pass that rewrites the primary artifact can silently drop rows it did not
recover, and the hand-entered, individually sourced rows in coaches_2026.json
are the last thing that should be at risk from a crawler.

--- THE TWO WAYS TO GET THE WRONG PERSON, AND WHAT STOPS EACH ---

1. "HEAD COACH" IS A SUBSTRING OF "ASSOCIATE HEAD COACH" AND "ASSISTANT HEAD
   COACH", and on several of these pages the associate is listed FIRST. A
   substring match hands you the deputy with total confidence. The title test is
   imported from crawl_coaches (_IS_HEAD / _NOT_HEAD) rather than rewritten, so
   there is ONE definition of what a head coach's title looks like (R4) -- and
   it is the definition that already survived 296 schools.

   It has to be a rule rather than an exact string, because the title genuinely
   varies: Purdue's is "Art and Connie Euler Women's Volleyball Head Coach" (an
   endowment, and a real head coach), while Stanford's page carries "The
   Kimberly and Beverly Oden Associate Head Coach" -- which ends in "Head Coach"
   and is NOT one. Ends-with matching gets that pair exactly backwards.

2. THE NEAREST NAME TO A TITLE MIGHT BE A PLAYER. The staff block sits below
   the squad on some templates, so a careless proximity search reaches back into
   the roster. Every candidate is therefore rejected if it matches a player on
   that same team's roster.

--- AND WHY TWO STRATEGIES, NOT ONE ---

Some of these templates ship the staff twice: once as rendered HTML and once
inside the page's own embedded data payload, as adjacent JSON strings
("Dani","Busboom Kelly","Head Coach"). Where both fire they must AGREE, and
that agreement is free corroboration of a kind this project usually has to pay
for -- two extractions, different code paths, same document. A disagreement is
recorded and the row is left unresolved rather than one being picked.

Python 3.9 target.
"""

import json
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as CR      # noqa: E402  -- fetch(), with the empty-200 fix
import crawl_coaches as CC      # noqa: E402  -- the head-vs-deputy title rule

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
ROSTERS = os.path.join(RAW, "rosters_%d.json" % SEASON)
RECOVERED = os.path.join(RAW, "rosters_recovered_%d.json" % SEASON)
FOUND = os.path.join(RAW, "coaches_found_%d.json" % SEASON)
OUT = os.path.join(RAW, "coaches_from_roster_%d.json" % SEASON)

# A person's name as a school prints it. Two to four capitalised words; this is
# deliberately strict, because the alternative to rejecting an odd name is
# publishing a job title as a person.
NAME = re.compile(r"^[A-Z][A-Za-z'\-\.]+(?: [A-Z][A-Za-z'\-\.]+){1,3}$")

# ⚠ "CAPITALISED WORDS" IS NOT "A PERSON". The first run published SEVEN section
# headings as head coaches -- "Volleyball Coaching Staff", "Women's Volleyball
# Coaching Staff", "Volleyball Staff", "Coaching Staff", "Additional Links" --
# every one of which satisfies the name shape above and sits a few hundred
# characters from a real "Head Coach" title. That is R5 exactly: a label
# rendered where a measurement belongs, and it would have appeared on a team
# page as the name of a human being.
#
# So a candidate carrying any word that belongs to the FURNITURE of an athletics
# site is refused. This can in principle reject a genuine surname (Staff and
# Coach are both real surnames), and that is the direction to be wrong in: the
# row stays unresolved and the page renders nothing, which is what it should do
# when we do not know.
_NOT_A_PERSON = re.compile(
    # PHRASES, NOT WORDS -- and this distinction was paid for. The first version
    # denied the single word "alma", to stop Arkansas publishing its "Alma
    # Mater" column header. Army West Point's head coach is ALMA KOVACI LEE.
    # A one-word denylist cannot tell a label from a name that happens to
    # contain the same token, and the failure is silent in the direction that
    # matters: it deletes a real person.
    #
    # This list is deliberately SMALL, because it is not the real defence. The
    # structural requirement below is -- a candidate must be the text of a link
    # to someone's own page, or of an element whose class says "name". Furniture
    # is neither, which is what catches phrases nobody thought to list
    # ("Printer Friendly Version" was the third one to turn up).
    r"\b(?:coaching\s+staff|volleyball\s+staff|alma\s+mater|printer\s+friendly|"
    r"additional\s+links|staff\s+directory|coaching\s+records?|full\s+bio|"
    r"quick\s+links|view\s+profile|related\s+links)\b"
    r"|\b(?:roster|schedule|tickets|volleyball|athletics|staff)\b", re.I)


# Some templates print the whole thing as one string -- Maryland's roster says
# "Head Coach Adam Hughes" in the title slot and has no separate name element.
# The name is right there; it just is not where the other 40 schools put it.
_TITLE_WITH_NAME = re.compile(
    r"^head\s+coach\s*[:\-\u2013]?\s+(?P<name>[A-Z][A-Za-z'\-\.]+"
    r"(?: [A-Z][A-Za-z'\-\.]+){1,3})$", re.I)

PAUSE = 0.7


def is_furniture(name):
    # type: (str) -> bool
    """Is this string a piece of an athletics site rather than a person?

    Split out from looks_like_a_person deliberately. The NAME shape is a rule
    for what THIS crawler will accept from a page it is reading loosely, and it
    is strict on purpose. It is the wrong test to apply to names gathered under
    a different rule: crawl_coaches reads a staff TABLE row, where the school
    itself has already told us the cell is a person, so it can safely keep
    'Ma-Kayla "MJayee" Johnson' and "Alicia Manguiat (Roth)" exactly as written.
    Judging those by this crawler's shape rule would delete two real coaches.
    """
    return bool(name and _NOT_A_PERSON.search(name))


def looks_like_a_person(name):
    # type: (str) -> bool
    return bool(name and NAME.match(name) and not is_furniture(name))


def load(p):
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except ValueError:
        return {}


def is_head_title(title):
    # type: (str) -> bool
    t = (title or "").strip()
    if not t or len(t) > 90:
        return False
    return bool(CC._IS_HEAD.search(t)) and not CC._NOT_HEAD.search(t)


def from_payload(body):
    # type: (str) -> Optional[Tuple[str, str]]
    """(name, title) from the page's embedded data payload.

    These templates serialise the staff as a flat run of strings, so a first
    name, a surname and a title sit adjacent: "Dani","Busboom Kelly","Head
    Coach". The title is validated by the same rule as the HTML path -- nothing
    is accepted because of its position alone.
    """
    for m in re.finditer(r'"([A-Z][^"]{0,30})","([A-Z][^"]{0,40})","([^"]{3,90})"', body or ""):
        first, last, title = m.group(1), m.group(2), m.group(3)
        if not is_head_title(title):
            continue
        name = CC.tidy_name(("%s %s" % (first, last)).strip())
        if looks_like_a_person(name):
            return name, title
    return None


# ⚠ A DENYLIST OF SITE VOCABULARY CANNOT BE FINISHED, AND TRYING COST THREE
# ROUNDS. The loose scan -- "any capitalised phrase near a Head Coach title" --
# returned "Volleyball Coaching Staff", then "Alma Mater", then "Printer
# Friendly Version", each from a template the previous fix had not seen. Every
# one of those satisfies the shape of a name; the list of things that are not
# people is simply longer than any list I can write.
#
# The structural fact is better than the vocabulary one: on every one of these
# templates a person's name is either the text of a LINK TO HER OWN PAGE or the
# contents of an element whose class says "name". Furniture is neither. So the
# candidate must carry that signal, and the loose scan is gone rather than kept
# as a fallback -- a fallback that produces a wrong name is worse than no name,
# because the page cannot tell the difference and neither can a reader.
_PERSON_EL = re.compile(
    r'<a\b[^>]*href="[^"]*(?:/staff/|/coaches/|/roster/|/bios?/)[^"]*"[^>]*>'
    r'|<(?:h[1-6]|span|div|p|strong|a)\b[^>]*class="[^"]*name[^"]*"[^>]*>', re.I)


def _person_elements(window):
    # type: (str) -> List[str]
    """Text of the elements that STRUCTURALLY hold a person's name.

    ⚠ THE NAME IS OFTEN NESTED. Nebraska writes
        <a href=".../staff/dani-busboom-kelly" class="table__roster-name">
          <span>Dani Busboom Kelly</span></a>
    so a pattern demanding bare text immediately inside the matched tag finds
    nothing at all -- which is how the first structural version went from three
    wrong names to zero right ones. Match the OPENING tag, then read the text
    that follows it with tags stripped.
    """
    from html import unescape
    out = []
    for m in _PERSON_EL.finditer(window or ""):
        inner = window[m.end():m.end() + 220]
        inner = re.split(r"</(?:a|h[1-6]|div|p|td|th|li)\b", inner, 1)[0]
        txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", inner))).strip()
        if txt:
            out.append(txt)
    return out


def from_html(body):
    # type: (str) -> Optional[Tuple[str, str]]
    """(name, title) from the rendered markup.

    The title is read from between tag boundaries, then the nearest name-shaped
    text BEFORE it is taken, falling back to the nearest one after -- templates
    disagree about whether the title precedes or follows the person (Stanford
    prints the title first, Kentucky prints it second).
    """
    from html import unescape
    for m in re.finditer(r">\s*([^<>{}]{3,90}?)\s*<", body or ""):
        title = unescape(m.group(1)).strip()
        if not is_head_title(title):
            continue
        # the name may BE the title on templates that print them as one string
        _mt = _TITLE_WITH_NAME.match(re.sub(r"\s+", " ", title))
        if _mt:
            _n = CC.tidy_name(_mt.group("name"))
            if looks_like_a_person(_n):
                return _n, "Head Coach"
        for window, reverse in ((body[max(0, m.start() - 900):m.start()], True),
                                (body[m.end():m.end() + 900], False)):
            cands = _person_elements(window)
            for c in (reversed(cands) if reverse else cands):
                c = CC.tidy_name(re.sub(r"\s+", " ", unescape(c)).strip())
                if looks_like_a_person(c):
                    return c, title
    return None


def player_names(team, rosters, recovered):
    # type: (str, Dict, Dict) -> set
    out = set()
    for src in (rosters, recovered):
        rec = (src.get("teams") or src).get(team) or {}
        for p in (rec.get("players") or []):
            n = (p.get("name") or "").strip()
            if n:
                out.add(n.lower())
    return out


def main(argv):
    rosters = load(ROSTERS)
    recovered = load(RECOVERED)
    rmap = rosters.get("teams") or rosters
    found = (load(FOUND).get("teams") or {})

    have = set()
    for t, v in found.items():
        if (v or {}).get("name"):
            have.add(t)

    # A TEAM WHOSE PRIMARY ROSTER 404ed STILL HAS A ROSTER. ncaa.com's mirrored
    # athletics URLs carry dead domains, so recover_missing_rosters.py found
    # working ones for 26 schools and wrote them to their own file. Arkansas,
    # LSU and Vanderbilt were skipped entirely on the first pass because this
    # only looked at the primary file -- three of the nine "missing" coaches
    # were an unread fallback, not an unreadable page.
    recmap = recovered.get("teams") or recovered
    for _t, _v in recmap.items():
        if (_v or {}).get("url") and not (rmap.get(_t) or {}).get("url"):
            rmap.setdefault(_t, {})["url"] = _v["url"]

    wanted = argv[1:] or [t for t in sorted(rmap) if t not in have]
    prev = (load(OUT).get("teams") or {})
    out = dict(prev)

    hits = disagree = norm = 0
    for i, team in enumerate(wanted, 1):
        rec = rmap.get(team) or {}
        url = rec.get("url")
        if not url:
            continue
        # ⚠ NOT EVERY "url" IS ONE. Four rosters were recovered from files Cody
        # saved by hand -- "manual drop: USC Athletics.webarchive" sits in the
        # url field. Fetching that produced "urlerror", which reads as a network
        # problem and invites a retry that can never work. There is no page to
        # re-fetch; say so.
        if not url.lower().startswith(("http://", "https://")):
            out[team] = {"name": None, "url": url,
                         "why": ("the roster came from a manual file drop, not a "
                                 "URL -- there is no page to read a coach from")}
            continue
        if team in out and out[team].get("name"):
            continue                                  # resumable; never re-fetch
        body, st = CR.fetch(url)
        time.sleep(PAUSE)
        if st != "ok" or not body:
            out[team] = {"name": None, "why": "roster page %s" % st, "url": url}
            continue
        a = from_payload(body)
        b = from_html(body)
        if a and b and a[0] != b[0]:
            disagree += 1
            out[team] = {"name": None, "url": url,
                         "why": "two extractions disagreed",
                         "payload_said": a[0], "html_said": b[0]}
            print("  %-24s DISAGREE  payload=%r html=%r" % (team, a[0], b[0]))
            continue
        pick = b or a
        if not pick:
            out[team] = {"name": None, "why": "no head-coach title on the roster page",
                         "url": url}
            continue
        name, title = pick
        if name.lower() in player_names(team, rosters, recovered):
            out[team] = {"name": None, "url": url,
                         "why": "candidate %r is a player on this roster" % name}
            print("  %-24s REJECT    %r is a player" % (team, name))
            continue
        hits += 1
        if a and b:
            norm += 1
        out[team] = {
            "name": name, "title": title, "url": url,
            "how": "roster page staff section",
            "corroborated": bool(a and b),
            "source_tier": "OFFICIAL",
        }
        print("  %-24s %-28s %s%s" % (team, name, title[:40],
                                      "  [both]" if (a and b) else ""))
        if i % 10 == 0:
            json.dump({"meta": _meta(), "teams": out}, open(OUT, "w"), indent=1)

    # ⚠ THE CHECK THAT CATCHES FURNITURE WITHOUT KNOWING ITS NAME. A denylist of
    # site vocabulary is incomplete by construction -- it caught "Volleyball
    # Coaching Staff" and then missed "Alma Mater", and there is no reason to
    # believe the next template will use a phrase either version anticipated.
    #
    # But a LABEL is shared and a PERSON is not. If the same string is returned
    # as the head coach of two different schools, it is almost certainly a piece
    # of page furniture rather than a coach with two jobs. So the whole set is
    # audited against itself: any name claimed by more than one team is pulled
    # and recorded, never published. Two coaches really can share a name, which
    # is why this reports rather than deletes -- the row goes back to unresolved
    # and says why, and a human can restore it with a source.
    byname = {}
    for t, v in out.items():
        if (v or {}).get("name"):
            byname.setdefault(v["name"], []).append(t)
    dupes = dict((n, ts) for n, ts in byname.items() if len(ts) > 1)
    for n, ts in dupes.items():
        for t in ts:
            out[t] = {"name": None, "url": out[t].get("url"),
                      "why": ("withheld: %r was returned for %d schools (%s) -- "
                              "a name shared across schools is page furniture, "
                              "not a coach" % (n, len(ts), ", ".join(sorted(ts))))}
        hits -= len(ts)
        print("  WITHHELD  %-28s claimed by %s" % (n, ", ".join(sorted(ts))))

    json.dump({"meta": _meta(), "teams": out}, open(OUT, "w"), indent=1)
    print("\n%d resolved (%d corroborated by both extractions), %d disagreements, "
          "%d attempted, %d withheld as shared names"
          % (hits, norm, disagree, len(wanted), sum(len(v) for v in dupes.values())))
    print("wrote %s" % OUT)
    return 0


def _meta():
    return {
        "season": SEASON,
        "source_tier": "OFFICIAL",
        "source": "each school's own volleyball ROSTER page, staff section",
        "why": ("the 52 schools missing from coaches_found have no /coaches "
                "path at all -- every variant 404s -- and carry their staff on "
                "the roster page instead"),
        "title_rule": ("imported from crawl_coaches: names a head coach and is "
                       "not a deputy. NOT an exact string -- Purdue's head "
                       "coach carries an endowed title, and Stanford's page "
                       "carries an endowed ASSOCIATE title that ends in the "
                       "same two words"),
        "never_rewrites": [ROSTERS, FOUND, "data/raw/%d/coaches_%d.json" % (SEASON, SEASON)],
        "photo": "not collected here",
    }


if __name__ == "__main__":
    sys.exit(main(sys.argv))
