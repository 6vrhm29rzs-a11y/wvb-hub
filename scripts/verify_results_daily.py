#!/usr/bin/env python3
"""Nightly result verification against the schools' own published schedules.

Cody's directive (2026-09-01, after the third feed attribution inversion):
"each night, scores/wins should be verified against official team websites
and not rely solely on the ncaa site." Design refined with an external
review the same evening (docs/trust_layer_consult_2026-09-01.md).

WHAT IT DOES: for each of the day's counted D-I finals, fetch BOTH schools'
published schedule (SIDEARM's /schedule/text surface first -- a structured
page carrying "W 3-1"-style results and an explicit Home/Away/Neutral
column), find the row for this match by OPPONENT IDENTITY on the date
(never "first event of the date" -- doubleheaders), and compare
winner + set count against our canonical record.

WHAT IT NEVER DOES: correct anything. Two schools agreeing against the feed
produces a loud REVIEW CANDIDATE in data/raw/2026/result_review_queue.json
with both citations; a human files the correction ledger entry. One school
agreeing is corroboration, not verification. "Not posted yet" is NOT
disagreement -- schools post final results minutes to hours after the whistle.

Per-school states: AGREE_COMPLETE / CONTRADICTS_SETS (winner agrees, set
count does not -- a contradiction, never an agreement) / CONTRADICTS /
NOT_POSTED / EVENT_NOT_FOUND / SITE_UNPARSED / SITE_BLOCKED /
SITE_HTTP_MISS / SITE_NETWORK_ERROR / SITE_NOT_CONFIGURED.
Match verdicts: VERIFIED_BOTH / CORROBORATED_ONE / UNVERIFIED /
CONTRADICTED_BOTH / SCHOOL_CONFLICT / CONTRADICTED_ONE.

Every fetch attempt -- success, block, miss -- is appended to
data/raw/2026/result_verification_log.jsonl. Append-only, like every raw log.
"""
import datetime
import html as _html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_counts as SC                                   # noqa: E402
from reconcile_2025 import norm as _norm_raw                 # noqa: E402
from external_refs import _ref_norm                          # noqa: E402


def team_norm(name):
    """Join key for school-page opponents vs hub names.

    external_refs._ref_norm underneath, NOT the bare reconcile norm: school
    sites spell out "Norfolk State" / "Michigan State" where the hub says
    "St." -- the Penn State lesson, again. Two further standard folds,
    applied to BOTH sides so a key can never drift one-sided:
    - the dotted "N.C."/"S.C." expands to the state name (hub "N.C.
      Central" vs page "North Carolina Central"; undotted "NC State" is
      untouched and keeps its existing behaviour);
    - a bare "College" suffix folds away (page "Presbyterian College" vs
      hub "Presbyterian"; "Boston College" folds identically on both
      sides, so it still matches itself and collides with nobody).
    """
    t = re.sub(r"^University of (the )?", "", name.strip(),
               flags=re.IGNORECASE)
    t = re.sub(r"\b([NS])\.C\.", lambda m: (
        "North" if m.group(1) == "N" else "South") + " Carolina", t)
    n = _ref_norm(t)
    # ⚠ THE RESIDUAL-PAIR TABLE ALREADY EXISTED, IN THE OTHER DIRECTION.
    # external_refs.FIG_ALIASES maps an OUTSIDE source's spelling to the
    # hub's, keyed on exactly this _ref_norm form -- "northern arizona" ->
    # "northern ariz", "army" -> "army west point", "college of charleston"
    # -> "col of charleston", "unc wilmington" -> "uncw". A school's own
    # schedule page spells its opponents the same long way FIGstats does, so
    # the verifier was hand-maintaining a five-entry table beside a
    # forty-entry one solving the identical problem (measured 2026-09-13: 91
    # of 170 EVENT_NOT_FOUND observations this season were name-match
    # failures on pages that HAD published the result).
    # It is consulted on the _ref_norm form AND on the folded form, because
    # some of its keys are pre-fold ("southern indiana") and some post-fold.
    n = _EXT_ALIASES.get(n, n)
    n = _fold_key(n)
    n = _EXT_ALIASES.get(n, n)
    n = _fold_key(n)
    return _VERIFIER_ALIASES.get(n, n)


def _fold_key(n):
    """Word-level folds on an already-normalised key, applied to BOTH sides."""
    n = re.sub(r"\bcollege\b", " ", n)
    # "Charleston Southern" (page) vs "Charleston So." (hub) -- the same
    # word folded the same way on both sides
    n = re.sub(r"\bsouthern\b", "so", n)
    return re.sub(r"\s+", " ", n).strip()


# ⚠ A GLOBAL PARENTHETICAL STRIP IS BANNED HERE: Miami (FL) and Miami (OH)
# would merge. The loose pass below may drop one, and only ever when the
# result is UNIQUE across the hub -- which refuses exactly that pair.
_LOOSE_CONTRACT = {
    "valley": "val", "indiana": "ind", "california": "cal",
    "carolina": "caro", "arizona": "ariz", "illinois": "ill",
    "tennessee": "tenn", "mississippi": "miss", "florida": "fla",
    "kentucky": "ky", "louisiana": "la", "michigan": "mich",
    "washington": "wash", "wisconsin": "wis", "nebraska": "neb",
    "minnesota": "minn", "connecticut": "conn", "massachusetts": "mass",
    "pennsylvania": "pa", "colorado": "colo", "oklahoma": "okla",
    "virginia": "va", "georgia": "ga", "alabama": "ala", "arkansas": "ark",
    "missouri": "mo", "montana": "mont", "nevada": "nev", "oregon": "ore",
}
_LOOSE_DROP = ("college", "col", "of", "the", "university", "u")
_STATE_TAG = ("ny", "ca", "mn", "nc", "fl", "oh", "la", "md", "pa", "tx",
              "mo", "in", "ky", "sc", "va", "wi", "ga", "il")


def loose_key(name):
    """A deliberately over-folded key for the LAST matching pass only.

    Every fold here is one a school page and the hub genuinely disagree on:
    a spelled-out state ("Mississippi Valley State" vs "Mississippi Val."),
    a campus tag the page omits ("St. John's (NY)" vs "St. John's"), a
    trailing "State"/"A&M" the hub drops ("Alcorn State" vs "Alcorn"), and
    "College of X" against "Col. of X".

    ⚠ IT IS ONLY SAFE BECAUSE ITS CALLER REFUSES AN AMBIGUOUS RESULT. Folded
    this hard, 30 hub keys collide -- every "X" against "X St." (Ohio/Ohio
    St., Texas/Texas A&M/Texas St.). The pass checks the folded key against
    the whole hub and declines rather than guess, the same gate _strip_inst's
    pass already uses (R8: a name match must not be resolved by hope).
    """
    k = team_norm(name)
    k = re.sub(r"\([^)]*\)", " ", k)
    ws = [_LOOSE_CONTRACT.get(w, w) for w in k.split()
          if w not in _LOOSE_DROP]
    while ws and (ws[-1] in ("st", "a", "and", "m")
                  or (len(ws) > 1 and ws[-1] in _STATE_TAG)):
        ws.pop()
    return " ".join(ws).strip()


_LOOSE_HUB = {}
_LOOSE_HUB_LOCK = threading.Lock()


def _loose_hub_count(key):
    """How many hub teams share this loose key. Built once, under a lock --
    the sweep is threaded and a doubled counter would silently refuse real
    matches (the _stripped_hub_count lesson, same shape)."""
    if not _LOOSE_HUB:
        with _LOOSE_HUB_LOCK:
            if not _LOOSE_HUB:
                built = {}
                try:
                    d = json.load(open(os.path.join(
                        REPO, "data", "data_%d.json" % SEASON)))
                    for t in d.get("teams") or []:
                        k = loose_key(t.get("name_short") or "")
                        built[k] = built.get(k, 0) + 1
                except (OSError, ValueError):
                    return 2          # cannot check -> refuse the pass
                _LOOSE_HUB.update(built)
    return _LOOSE_HUB.get(key, 0)


def _strip_inst(n):
    """Trailing ' university' / ' u' removed from a NORMALIZED key."""
    return re.sub(r"\s+(?:university|u)$", "", n).strip()


_STRIPPED_HUB = {}
_STRIPPED_HUB_LOCK = threading.Lock()


def _stripped_hub_count(key):
    """⚠ BUILT ONCE, UNDER A LOCK -- it is a lazily-built COUNTER, and the
    sweep is threaded (2026-09-11). Two threads both finding it empty would
    each increment the SAME shared dict and leave every count at twice the
    truth. Its one consumer refuses a name match when a stripped key is
    ambiguous (> 1), so doubled counts would silently refuse legitimate
    matches -- intermittently, and only ever under concurrency, which is the
    hardest possible thing to diagnose after the fact. Build into a local
    dict, publish once."""
    if not _STRIPPED_HUB:
        with _STRIPPED_HUB_LOCK:
            if not _STRIPPED_HUB:     # another thread may have finished while
                built = {}            # we waited on the lock
                try:
                    d = json.load(open(os.path.join(
                        REPO, "data", "data_%d.json" % SEASON)))
                    for t in d.get("teams") or []:
                        k = _strip_inst(team_norm(t.get("name_short") or ""))
                        built[k] = built.get(k, 0) + 1
                except (OSError, ValueError):
                    return 2          # cannot check -> refuse pass 2
                _STRIPPED_HUB.update(built)
    return _STRIPPED_HUB.get(key, 0)


from external_refs import FIG_ALIASES as _EXT_ALIASES  # noqa: E402

_VERIFIER_ALIASES = {
    # the long form a school writes out in full: "University of North
    # Carolina Wilmington" (Harvard's page, 2026-09-12) against the hub's
    # "UNCW". Entered per measured miss, never speculatively -- and NOT as a
    # general "north caro X" -> "unc X" fold, because the hub spells N.C.
    # Central "N.C. Central" and that fold would break it.
    "north caro wilmington": "uncw",
    "north caro greensboro": "unc greensboro",
    "north caro asheville": "unc asheville",
    "ucsb": "uc santa barbara",
    "queens": "queens nc",
    "queens university of charlotte": "queens nc",   # Duke's spelling
    "texas a and m corpus christi": "a and m corpus christi",
    "usc": "so california",              # texassports' spelling
}

SEASON = 2026
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
UA = ("wvb-hub result verifier (personal research project; "
      "~2 requests per school per night)")
SPORT_PATHS = [
    "/sports/womens-volleyball/schedule/text",
    "/sports/volleyball/schedule/text",       # no men's program (Nebraska)
    "/sports/wvball/schedule/text",           # WMT naming (Kentucky)
    "/sports/wvb/schedule/text",              # short code (LSU)
]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def parse_sidearm_date(cell):
    """'Sep 1 (Tue)' / 'Sept. 1' / 'September 1' -> (month, day) or
    (None, None). Speculative formats are NOT added -- unrecognised
    event-like cells are for the log to surface, and live failures grow
    the parser (review consult, 2026-09-01)."""
    m = re.match(r"([A-Z][a-z]+)\.?\s+(\d{1,2})", cell.strip())
    if not m:
        return None, None
    name = m.group(1)[:3]
    if m.group(1).startswith("Sept"):
        name = "Sep"
    if name not in MONTHS:
        return None, None
    return MONTHS[name], int(m.group(2))


def _sites():
    sites = json.load(open(os.path.join(RAW, "athletics_sites.json")))
    ov = json.load(open(os.path.join(RAW, "athletics_sites_overrides.json")))
    out = {}
    for team, rec in sites.items():
        u = (rec or {}).get("url")
        if u:
            out[team] = u.rstrip("/")
    for team, u in (ov.get("teams") or {}).items():
        out[team] = u.rstrip("/")
    return out


def _fetch(url, timeout=20):
    """-> (status, body, final_url). urlopen follows redirects SILENTLY, so
    the final URL is part of the evidence -- /schedule/text 302ing to the JS
    /schedule page is exactly how SITE_UNPARSED happens (review consult,
    2026-09-01)."""
    class _P308(urllib.request.HTTPRedirectHandler):
        def http_error_308(self, req, fp, code, msg, headers):
            return self.http_error_301(req, fp, 301, msg, headers)

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        opener = urllib.request.build_opener(_P308)
        with opener.open(req, timeout=timeout) as r:
            return (getattr(r, "status", r.getcode()),
                    r.read().decode("utf-8", "replace"), r.geturl())
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:                                    # noqa: BLE001
        return None, str(e)[:120], url


# How many DIFFERENT schools may be in flight at once. Per-host serialisation
# (_host_lock) is what keeps this polite, so this bounds our own outbound
# connections, not the load any one athletics site sees.
VERIFY_WORKERS = max(1, int(os.environ.get("WVB_VERIFY_WORKERS", "8")))

_HOST_LOCKS = {}
_HOST_LOCKS_GUARD = threading.Lock()


def _host_lock(url):
    """One lock per hostname, held for a whole school ladder. A given
    athletics site therefore never sees two of our requests at once -- the
    politeness the sequential version got for free, now kept explicitly."""
    host = urllib.parse.urlsplit(url).netloc.lower()
    with _HOST_LOCKS_GUARD:
        lk = _HOST_LOCKS.get(host)
        if lk is None:
            lk = _HOST_LOCKS[host] = threading.Lock()
    return lk


def _cells(row_html):
    return [_html.unescape(re.sub(r"<[^>]+>", " ", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>",
                                row_html, re.S | re.I)]


def parse_schedule_text(page, season=SEASON):
    """SIDEARM /schedule/text -> normalized rows.

    Columns observed: Date | Time | At | Opponent | Location [| Tournament]
    | Result. The result is wherever a "W 3-1" / "L 0-3" token sits -- the
    column count varies by school, so the row is scanned for the token
    rather than trusting a position.
    """
    rows = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = _cells(m.group(1))
        if len(cells) < 4:
            continue
        mo, day = parse_sidearm_date(cells[0])
        if not mo:
            continue
        # Aug-Dec belong to the season year; Jan+ would be the next
        year = season if mo >= 8 else season + 1
        date = "%04d-%02d-%02d" % (year, mo, day)
        site = next((c for c in cells[1:4]
                     if c in ("Home", "Away", "Neutral")), None)
        # the opponent is the cell after the site column, rank prefix
        # stripped; "(Exh.)" is a marker, not part of the name
        try:
            opp_raw = cells[cells.index(site) + 1] if site else cells[3]
        except (ValueError, IndexError):
            continue
        exh = "(Exh.)" in opp_raw or "Exhibition" in opp_raw
        # rank prefixes come in three spellings: "#7 ", "No. 7 ", and "RV "
        # (receiving votes -- found live on Louisville's page, where the
        # opponent read "RV Dayton" and the row went unmatched)
        opp = re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "",
                     opp_raw.replace("(Exh.)", "")).strip()
        res = None
        for c in cells:
            rm = re.fullmatch(r"([WL])[,\s]+(\d)\s*-\s*(\d)", c.strip())
            if rm:
                res = (rm.group(1), int(rm.group(2)), int(rm.group(3)))
        rows.append({"date": date, "site": site, "opponent": opp,
                     "exhibition": exh, "result": res, "raw": cells})
    return rows


def parse_schedule_txt_plain(body, season=SEASON):
    """The legacy SIDEARM /services/schedule_txt.ashx plain-text export --
    the fallback for schools whose /schedule/text redirects to the JS page.
    Fixed-width columns, sliced by the header row's own offsets (measured on
    daytonflyers.com): Date / Time / At / Opponent / Location / Tournament /
    Result."""
    lines = body.splitlines()
    hdr = next((i for i, l in enumerate(lines)
                if l.strip().startswith("Date") and "Opponent" in l), None)
    if hdr is None:
        return []
    h = lines[hdr]
    cols = ["Date", "Time", "At", "Opponent", "Location", "Tournament",
            "Result"]
    starts = []
    for c in cols:
        j = h.find(c)
        if j < 0:
            return []
        starts.append(j)
    rows = []
    for l in lines[hdr + 1:]:
        if not l.strip():
            continue
        cells = {}
        for k, c in enumerate(cols):
            end = starts[k + 1] if k + 1 < len(cols) else len(l)
            cells[c] = l[starts[k]:end].strip()
        mo, day = parse_sidearm_date(cells["Date"])
        if not mo:
            continue
        year = season if mo >= 8 else season + 1
        opp_raw = cells["Opponent"]
        # ⚠ a hosted-tournament row names two OTHER teams ("Santa Clara vs.
        # Eastern Illinois" on Dayton's page) -- the school is not playing
        # in it and it must never match
        if " vs. " in opp_raw:
            continue
        exh = "(Exh.)" in opp_raw or "Exhibition" in opp_raw
        opp = re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "",
                     opp_raw.replace("(Exh.)", "")).strip()
        res = None
        rm = re.match(r"([WL])[,\s]+(\d)\s*-\s*(\d)", cells["Result"])
        if rm:
            res = (rm.group(1), int(rm.group(2)), int(rm.group(3)))
        rows.append({"date": "%04d-%02d-%02d" % (year, mo, day),
                     "site": cells["At"] if cells["At"] in
                     ("Home", "Away", "Neutral") else None,
                     "opponent": opp, "exhibition": exh, "result": res,
                     "raw": [cells[c] for c in cols]})
    return rows


# per-event boundary markers for the modern JS-rendered schedule pages --
# one marker per rendered game card, across the template families measured
# 2026-09-01: WMT/virginiasports ("schedule-event-item__date-box"),
# WMT-variant/odusports ("schedule-event-date__day"), and modern SIDEARM
# ("s-game-card", the class the USC incident already taught us to treat as
# the card BOUNDARY -- evidence binds inside one card, never across).
_CARD_MARKS = re.compile(
    r'class="[^"]*(?:schedule-event-item__date-box|'
    r'schedule-event-date__day|schedule-event-date__month-day|'
    r's-game-card|schedule-item__date)')


def parse_completed_events(page, season=SEASON):
    """Modern SIDEARM/Vue templates that DO render results into the HTML.

    ⚠ MOST OF THEM DO NOT. Auburn, Kentucky and BYU ship the schedule
    scaffold and fetch the results client-side -- their Nuxt payload carries
    config and no events -- so no static parser can read them and they stay
    honestly unreadable (the JS ceiling this project already hit on rosters).
    The ones that DO write an accessibility label are readable, and that is
    what this reads:

      "Completed Event: Volleyball versus Weber State on September 11, 2026 ,
       Win , 3, to, 1"          -- kstatesports.com, measured 2026-09-12

    plus the visible-row form some sites use instead:

      "Sep 4 1:00 PM PDT vs. (rv) Cal Poly L 1-3 (22-25, 22-25, 25-20, 24-26)"
                                -- goaztecs.com, measured 2026-09-12

    ⚠⚠ A ROW HERE MUST CARRY THE SAME SHAPE AS EVERY OTHER PARSER'S, AND
    THIS ONE DID NOT (found 2026-09-13). It emitted `result` as the STRING
    "W 3 1" where the contract is the tuple ("W", 3, 1), and it omitted
    `exhibition` entirely -- so `_judge_rows` raised KeyError('exhibition')
    on the first row it produced, inside a thread-pool map, which aborts the
    WHOLE run -- and an aborted run writes no report at all, so the failure
    is silent and looks like a quiet night. What is measured: this parser
    landed 2026-09-12 21:15Z; the 2026-09-12 report's last write is 22:33Z
    and holds 104 matches against 149 counted finals, while EVERY other date
    this season was written by the next-morning sweep (03:00-04:00Z). That
    date never got its nightly sweep.
    The contract is: date, opponent (or tokens), exhibition (bool), result as
    (W/L, sets_for, sets_against) or None, raw.
    """
    import html as _html
    flat = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", page)))
    rows = []
    for chunk in flat.split("Completed Event:")[1:]:
        txt = chunk[:180]
        mm = re.search(r"(?:versus|vs\.?|at)\s+(.+?)\s+on\s+"
                       r"([A-Z][a-z]+ \d{1,2}, \d{4})\s*,?\s*"
                       r"(Win|Loss)\s*,\s*(\d+)\s*,\s*to\s*,\s*(\d+)", txt)
        if not mm:
            continue
        try:
            when = datetime.datetime.strptime(mm.group(2), "%B %d, %Y")
        except ValueError:
            continue
        if when.year != season:
            continue
        w, a, b = mm.group(3), int(mm.group(4)), int(mm.group(5))
        rows.append({"date": when.strftime("%Y-%m-%d"),
                     "opponent": re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "",
                                        mm.group(1).strip()),
                     "result": ("W" if w == "Win" else "L", a, b),
                     "exhibition": "xhibition" in txt,
                     "site": "", "location": "", "tournament": "",
                     "raw": txt[:120],
                     "parser": "completed_event_label"})
    if rows:
        return rows
    for m in re.finditer(
            r"([A-Z][a-z]{2})\s+(\d{1,2})\b.{0,60}?"
            r"(?:vs\.?|at)\s+(?:\(\w+\)\s*)?([A-Za-z&'.\- ]{3,40}?)\s+"
            r"([WL])\s*(\d)-(\d)\b", flat):
        try:
            when = datetime.datetime.strptime(
                "%s %s %d" % (m.group(1), m.group(2), season), "%b %d %Y")
        except ValueError:
            continue
        rows.append({"date": when.strftime("%Y-%m-%d"),
                     "opponent": m.group(3).strip(),
                     "result": (m.group(4), int(m.group(5)), int(m.group(6))),
                     "exhibition": False,
                     "site": "", "location": "", "tournament": "",
                     "raw": m.group(0),
                     "parser": "visible_row"})
    return rows


def parse_modern_cards(page, season=SEASON):
    """JS-rendered schedule pages -> normalized rows, by TOKEN SCHEMA.

    The templates differ; the token stream rhymes: a month-day date, an
    at/vs marker, the opponent, and a result shaped W/L + N-N ("W|Win|3-0"
    on WMT, "W, 3-0" on SIDEARM cards). Discovery is by schema, not by
    variable or class names (per the design consult) -- with one exception:
    the block BOUNDARY is a card marker class, because token proximity
    across card boundaries is exactly how the USC misread happened.
    The opponent is NOT extracted here -- the judge knows who it expects,
    and a block matches only if a single token normalizes to that name.
    """
    # slice from the marker tag's own '<' -- starting mid-attribute leaves
    # an unstripped tag fragment glued to the first token (found on
    # odusports.com, where the date text follows the class attr directly)
    marks = [page.rfind("<", 0, m.start()) for m in _CARD_MARKS.finditer(page)]
    marks = [m for m in marks if m >= 0]
    rows = []
    for k, st in enumerate(marks):
        end = marks[k + 1] if k + 1 < len(marks) else min(len(page),
                                                          st + 20000)
        blk = page[st:end]
        toks = [x.strip() for x in
                re.sub(r"<[^>]+>", "|", _html.unescape(blk)).split("|")
                if x.strip()]
        date = None
        for tk in toks:
            mo, day = parse_sidearm_date(tk)
            if mo:
                year = season if mo >= 8 else season + 1
                date = "%04d-%02d-%02d" % (year, mo, day)
                break
        if not date:
            continue
        exh = any(re.search(r"exh|intrasquad|scrimmage", tk, re.I)
                  for tk in toks)
        res = None
        for j, tk in enumerate(toks):
            m1 = re.fullmatch(r"([WL])[,.]?\s*(\d)\s*-\s*(\d)", tk)
            if m1:
                res = (m1.group(1), int(m1.group(2)), int(m1.group(3)))
                break
            if re.fullmatch(r"[WL][,.]?", tk):
                for tk2 in toks[j + 1:j + 4]:
                    m2 = re.fullmatch(r"(\d)\s*-\s*(\d)", tk2)
                    if m2:
                        res = (tk[0], int(m2.group(1)), int(m2.group(2)))
                        break
                if res:
                    break
        site = next((tk.capitalize() for tk in toks
                     if tk.lower() in ("home", "away", "neutral")), None)
        rows.append({"date": date, "site": site, "opponent": None,
                     "tokens": toks, "exhibition": exh, "result": res,
                     "raw": toks[:14], "surface": "modern_card"})
    return rows


_WMT_SPORT = {}
_WMT_SPORT_LOCK = threading.Lock()


def wmt_sport_id(base, log):
    """The site's OWN id for women's volleyball, read from its sports table.

    ⚠⚠ THIS IS THE SURFACE THAT CLOSES THE TOP-50 VERIFICATION GAP
    (found 2026-09-13). Thirteen of the top fifty -- Nebraska, Stanford, Penn
    St., Purdue, UCLA, Kentucky, Arizona St., Auburn, BYU, Georgia Tech,
    Texas A&M, UCF and Vanderbilt -- render their schedules client-side, so
    no static parser could read them and no second official source existed
    for any of their results. If the feed inverted a Nebraska result, nothing
    caught it. All thirteen run the same WMT platform, and its page fetches
    its own data from a plain JSON API on the school's own domain. Measured:
    /website-api/sports answers 200 on 12 of the 13 (Kentucky redirects), and
    the events it returns carry the result, the full set line, the venue, an
    is_exhibition flag and a status.
    ⚠ The sport id is per-SITE, never global: Volleyball is 16 at Nebraska
    and 17 at Georgia Tech. It is read, never assumed, and the name must
    match EXACTLY -- "Beach Volleyball" and "Men's Volleyball" are different
    sports and a substring test would take them (R8's lesson, applied to a
    sport rather than a surname).
    """
    with _WMT_SPORT_LOCK:
        if base in _WMT_SPORT:
            return _WMT_SPORT[base]
    url = base + "/website-api/sports?per_page=100"
    status, body, _fu = _fetch(url)
    sid = None
    if status == 200 and body:
        try:
            doc = json.loads(body)
        except ValueError:
            doc = {}
        cands = [x for x in (doc.get("data") or [])
                 if (x.get("name") or "").strip().lower()
                 in ("volleyball", "women's volleyball", "womens volleyball")]
        # exactly one, or nothing -- an ambiguous sports table is not guessed
        if len(cands) == 1:
            sid = cands[0].get("id")
        elif cands:
            womens = [x for x in cands
                      if (x.get("name") or "").lower().startswith("w")]
            sid = womens[0].get("id") if len(womens) == 1 else None
    log.append({"team": None, "url": url, "http": status,
                "retrieved_utc": datetime.datetime.utcnow()
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "state": "wmt_sports_probe", "sport_id": sid})
    with _WMT_SPORT_LOCK:
        _WMT_SPORT[base] = sid
    return sid


def parse_wmt_events(doc, season=SEASON):
    """WMT's own schedule JSON -> rows in the SAME shape every parser emits.

    ⚠ THE RESULT NUMBERS ARE NOT OWN-FIRST, AND NOT CONSISTENTLY ANYTHING.
    Georgia Tech's loss to Nebraska reads winning_score 3 / losing_score 1
    while its loss to Baylor reads 0 / 3. The LETTER is the school's
    authoritative claim and the numbers are the two set counts -- exactly the
    convention already measured on the text schedules, so the orientation fix
    in _judge_rows handles both and nothing new is needed here.
    """
    rows = []
    for r in (doc.get("data") or []):
        dt = r.get("datetime")
        if not dt:
            continue
        try:
            when = datetime.datetime.strptime(dt[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        # the feed stamps UTC; the verifier dates everything Eastern
        when = when - datetime.timedelta(hours=4)
        if when.year != season:
            continue
        opp = (r.get("opponent_name")
               or (r.get("opponent") or {}).get("name") or "").strip()
        if not opp:
            continue
        res = r.get("schedule_event_result") or {}
        letter = (res.get("result") or "").strip().lower()
        out = None
        if letter in ("win", "loss"):
            try:
                a = int(float(res.get("winning_score")))
                b = int(float(res.get("losing_score")))
            except (TypeError, ValueError):
                a = b = None
            if a is not None:
                out = ("W" if letter == "win" else "L", a, b)
        site = {"home": "Home", "away": "Away",
                "neutral": "Neutral"}.get(r.get("venue_type"))
        rows.append({"date": when.strftime("%Y-%m-%d"),
                     "site": site,
                     "opponent": re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "",
                                        opp),
                     # the platform states this itself -- no name-sniffing
                     "exhibition": bool(r.get("is_exhibition")),
                     "result": out,
                     "raw": [dt, opp, res.get("text") or "",
                             r.get("status_text") or ""],
                     "surface": "wmt_api"})
    return rows


def wmt_api_rows(base, log, team):
    """Both requests, or nothing. Returns (rows, url)."""
    sid = wmt_sport_id(base, log)
    if sid is None:
        return [], None
    url = (base + "/website-api/schedule-events?filter%5Bschedule.sport_id%5D="
           + str(sid) + "&filter%5Bpast%5D=true&per_page=25&sort=-datetime"
           "&include=opponent,scheduleEventResult")
    status, body, _fu = _fetch(url)
    rows = []
    if status == 200 and body:
        try:
            rows = parse_wmt_events(json.loads(body))
        except ValueError:
            rows = []
    log.append({"team": team, "url": url, "http": status,
                "retrieved_utc": datetime.datetime.utcnow()
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "state": "wmt_api", "rows": len(rows)})
    return rows, url


def legacy_txt_rows(base, log, team):
    """Find the schedule_txt.ashx link on the vendor schedule page and parse
    its plain-text export. Returns (rows, url) or (None, None)."""
    for sport in ("womens-volleyball", "volleyball", "wvball", "wvb"):
        url = base + "/sports/%s/schedule" % sport
        status, body, _fu = _fetch(url)
        time.sleep(0.5)
        if status != 200 or not body:
            continue
        # ⚠ a page can carry SEVERAL schedule ids (other sports' footers,
        # archived seasons) -- the first match was the wrong one on UCSB
        # ("Schedule not found" / another sport). Try each distinct id.
        ids = list(dict.fromkeys(re.findall(
            r"/services/schedule_txt\.ashx\?schedule=\d+", body)))[:4]
        for frag in ids:
            turl = base + frag
            status2, txt, _fu2 = _fetch(turl)
            time.sleep(0.5)
            log.append({"team": team, "url": turl, "http": status2,
                        "retrieved_utc": datetime.datetime.utcnow()
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "state": "legacy_txt"})
            if status2 == 200 and txt:
                rows = parse_schedule_txt_plain(txt)
                if rows:
                    return rows, turl
    return None, None


def _judge_rows(rows, url, team, opponent, date, canonical):
    """Match the row and compare it to the canonical result.

    ⚠ OPPONENT IDENTITY DOMINATES THE DATE: a tournament day can hold two
    matches, and "first row of the date" is how the wrong match gets
    verified. R8's lesson, applied to scraping."""
    want = team_norm(opponent)

    def _match_token(r):
        """The SOURCE token that satisfied the match, or None.

        ⚠ EVIDENCE QUOTES THE SOURCE, NOT OUR EXPECTATION (consult catch,
        2026-09-01): the assertion used to say "vs Presbyterian" -- our
        name -- when the page said "Presbyterian College". Matching may use
        prior knowledge; the retained evidence text must be the page's own
        words. A row that cannot hand back its source token cannot match.
        """
        if r.get("opponent") is not None:
            return r["opponent"] if team_norm(r["opponent"]) == want \
                else None
        # a token row (modern card): exact single-token normalization --
        # never a substring, never across the card boundary (R8, and the
        # USC misread)
        for tk in (r.get("tokens") or []):
            bare = re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "", tk)
            if team_norm(bare) == want:
                return tk
        return None

    cand = [(r, _match_token(r)) for r in rows if r["date"] == date
            and not r["exhibition"]]
    cand = [(r, tok) for r, tok in cand if tok]
    if not cand:
        # PASS 2 -- trailing-institution strip ("Tarleton State University"
        # vs hub "Tarleton St."), gated on UNIQUENESS: if two hub teams
        # share the stripped form (Boston U. / Boston College -> "boston"),
        # this pass refuses rather than guess (R8).
        want2 = _strip_inst(want)
        if want2 != want and _stripped_hub_count(want2) > 1:
            want2 = None
        if want2:
            def _match2(r):
                toks = ([r["opponent"]] if r.get("opponent") is not None
                        else (r.get("tokens") or []))
                for tk in toks:
                    bare = re.sub(r"^(?:#\d+|No\.\s*\d+|RV)\s+", "", tk)
                    if _strip_inst(team_norm(bare)) == want2:
                        return tk
                return None
            cand = [(r, _match2(r)) for r in rows if r["date"] == date
                    and not r["exhibition"]]
            cand = [(r, tok) for r, tok in cand if tok]
    if not cand:
        # PASS 3 -- the LOOSE key ("Mississippi Valley State" vs the hub's
        # "Mississippi Val.", "St. John's" vs "St. John's (NY)"), gated on
        # the same uniqueness rule: a fold this hard collides "Ohio" with
        # "Ohio St.", so an ambiguous key refuses rather than guesses.
        # ⚠ MEASURED BEFORE IT WAS BUILT (2026-09-13): 91 of this season's
        # 170 EVENT_NOT_FOUND observations were pages that HAD published the
        # result under a spelling this could not read.
        wantl = loose_key(opponent)
        if wantl and _loose_hub_count(wantl) == 1:
            def _match3(r):
                toks = ([r["opponent"]] if r.get("opponent") is not None
                        else (r.get("tokens") or []))
                for tk in toks:
                    bare = re.sub(r"^\(?(?:#\d+|No\.\s*\d+|RV)\)?\s+",
                                  "", tk)
                    if loose_key(bare) == wantl:
                        return tk
                return None
            cand = [(r, _match3(r)) for r in rows if r["date"] == date
                    and not r["exhibition"]]
            cand = [(r, tok) for r, tok in cand if tok]
    if not cand:
        return "EVENT_NOT_FOUND", {"url": url, "rows_on_date": [
            (r["opponent"] if r.get("opponent") is not None
             else " ".join((r.get("tokens") or [])[:6]))
            for r in rows if r["date"] == date]}
    r, opp_src = cand[0]
    if not r["result"]:
        return "NOT_POSTED", {"url": url, "row": r["raw"]}
    wl, a, b = r["result"]
    # ⚠ SET-ORDER CONVENTION, MEASURED (Alabama A&M, 2026-09-02): some
    # schools list a LOSS opponent-first -- "L 3-0" meaning lost nil-three.
    # "L" with a>b (or "W" with a<b) is internally incoherent read own-
    # first, and the LETTER is the school's authoritative claim; the
    # numbers are the set counts, so orientation follows the letter.
    if (wl == "L" and a > b) or (wl == "W" and a < b):
        a, b = b, a
    won = wl == "W"
    det = {"url": url, "assertion": "%s %s %d-%d vs %s"
           % (team, wl, a, b, opp_src),
           "opponent_source": opp_src,
           "site_says": r["site"]}
    if r.get("surface"):
        det["surface"] = r["surface"]
    if canonical.get("held"):
        # ⚠ A HELD MATCH HAS NO CANONICAL TO AGREE WITH -- that is what being
        # held MEANS. So the school's own row is recorded as an observation
        # and judged by nobody here: AGREE/CONTRADICT are claims about our
        # counted result, and we are not counting one. A human reads these
        # and files a correction on two of them (2026-09-13).
        return "REPORTS", det
    # a held canonical carries no winner, so these are read only below it
    c_won = canonical["winner"] == team
    c_sets = (canonical["w_sets"], canonical["l_sets"]) if c_won \
        else (canonical["l_sets"], canonical["w_sets"])
    if won == c_won and (a, b) == c_sets:
        return "AGREE_COMPLETE", det
    if won == c_won:
        # ⚠ NOT "partial agreement" (review consult, 2026-09-01): the school
        # agrees on the winner but CONTRADICTS our set count. Two schools in
        # this state means two official sources say the feed's score line is
        # wrong -- that must surface as a review candidate, never verify.
        return "CONTRADICTS_SETS", det
    return "CONTRADICTS", det


def school_evidence(team, opponent, date, canonical, sites, log):
    """One school's published word on one match. Returns (state, detail)."""
    base = sites.get(team)
    if not base:
        return "SITE_NOT_CONFIGURED", {"why": "no athletics site on file"}
    # ⚠ A SURFACE FAILURE IS AN OBSERVATION, NOT A VERDICT (review consult,
    # 2026-09-01): the old ladder returned SITE_UNPARSED / EVENT_NOT_FOUND
    # from the FIRST surface that half-answered, so a school whose text page
    # was a JS shell never reached the legacy export. Every surface is
    # tried; the best observation wins, and only a judged row short-circuits.
    best = ("SITE_UNREACHABLE", {"why": "no schedule surface answered"})
    rank = {"SITE_UNREACHABLE": 0, "SITE_HTTP_MISS": 1, "SITE_BLOCKED": 1,
            "SITE_NETWORK_ERROR": 1, "SITE_UNPARSED": 2,
            "EVENT_NOT_FOUND": 3, "NOT_POSTED": 4}
    def better(st, det):
        nonlocal_best = rank.get(st, 0) > rank.get(best[0], 0)
        return (st, det) if nonlocal_best else best
    for path in SPORT_PATHS:
        url = base + path
        status, body, final_url = _fetch(url)
        time.sleep(0.5)
        entry = {"team": team, "url": url, "http": status,
                 "retrieved_utc": datetime.datetime.utcnow()
                 .strftime("%Y-%m-%dT%H:%M:%SZ")}
        if final_url != url:
            entry["final_url"] = final_url
            entry["redirected"] = True
        if status is None:
            entry["state"] = "network_error"
            log.append(entry)
            best = better("SITE_NETWORK_ERROR", {"url": url, "why": body})
            continue
        if status in (401, 403, 429):
            entry["state"] = "blocked"
            log.append(entry)
            best = better("SITE_BLOCKED", {"url": url, "http": status})
            continue
        if status != 200:
            entry["state"] = "miss"
            log.append(entry)
            best = better("SITE_HTTP_MISS", {"url": url, "http": status})
            continue
        # ⚠ "the word schedule appears somewhere" is not a schedule surface
        # -- a branded 404 or the JS shell both contain it. The evidence is
        # successful row extraction, nothing weaker.
        rows = parse_schedule_text(body)
        if not rows:
            # the modern JS page (often what /schedule/text silently
            # redirected to) -- reuse THIS body rather than refetching
            mrows = parse_completed_events(body) or parse_modern_cards(body)
            entry["state"] = "unparsed"
            entry["modern_blocks"] = len(mrows)
            log.append(entry)
            if mrows:
                st, det = _judge_rows(mrows, final_url, team, opponent,
                                      date, canonical)
                if st in ("AGREE_COMPLETE", "CONTRADICTS", "REPORTS",
                          "CONTRADICTS_SETS", "NOT_POSTED"):
                    return st, det
                best = better(st, det)
                continue
            best = better("SITE_UNPARSED", {"url": final_url})
            continue
        entry["state"] = "parsed"
        log.append(entry)
        st, det = _judge_rows(rows, url, team, opponent, date, canonical)
        if st in ("AGREE_COMPLETE", "CONTRADICTS", "CONTRADICTS_SETS",
                  # ⚠ REPORTS IS A JUDGED ROW TOO -- a held match's only
                  # possible outcome. Left out of these ladders it fell to
                  # better(), whose rank table scores an unknown state 0, so
                  # every school's published word on a held match was silently
                  # discarded and all 11 read HELD_NO_REPORT.
                  "REPORTS",
                  "NOT_POSTED"):
            return st, det
        best = better(st, det)
    # the modern schedule pages directly (WMT 404s every /text path, so the
    # loop above never even saw a body for those schools)
    for sport in ("womens-volleyball", "volleyball", "wvball", "wvb"):
        murl = base + "/sports/%s/schedule" % sport
        mstatus, mbody, mfinal = _fetch(murl)
        time.sleep(0.5)
        if mstatus != 200 or not mbody:
            continue
        mrows = parse_completed_events(mbody) or parse_modern_cards(mbody)
        log.append({"team": team, "url": murl, "http": mstatus,
                    "retrieved_utc": datetime.datetime.utcnow()
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "state": "modern_probe", "modern_blocks": len(mrows)})
        if not mrows:
            continue
        st, det = _judge_rows(mrows, mfinal, team, opponent, date,
                              canonical)
        if st in ("AGREE_COMPLETE", "CONTRADICTS", "CONTRADICTS_SETS",
                  # ⚠ REPORTS IS A JUDGED ROW TOO -- a held match's only
                  # possible outcome. Left out of these ladders it fell to
                  # better(), whose rank table scores an unknown state 0, so
                  # every school's published word on a held match was silently
                  # discarded and all 11 read HELD_NO_REPORT.
                  "REPORTS",
                  "NOT_POSTED"):
            return st, det
        best = better(st, det)
        break
    # the legacy plain-text export -- reached even when every path above
    # produced only observations
    rows2, turl = legacy_txt_rows(base, log, team)
    if rows2:
        st, det = _judge_rows(rows2, turl, team, opponent, date, canonical)
        if st in ("AGREE_COMPLETE", "CONTRADICTS", "CONTRADICTS_SETS",
                  # ⚠ REPORTS IS A JUDGED ROW TOO -- a held match's only
                  # possible outcome. Left out of these ladders it fell to
                  # better(), whose rank table scores an unknown state 0, so
                  # every school's published word on a held match was silently
                  # discarded and all 11 read HELD_NO_REPORT.
                  "REPORTS",
                  "NOT_POSTED"):
            return st, det
        best = better(st, det)
    # ⚠ THE PLATFORM'S OWN JSON, LAST AND ONLY WHEN NOTHING ELSE ANSWERED.
    # Two extra requests, so it is reached only by the schools whose HTML
    # surfaces cannot be read -- which is exactly the set that matters: 13 of
    # the top 50 had NO readable second source at all before this (see
    # wmt_sport_id). The ~300 schools whose text export already parses see
    # the same traffic they saw before.
    rows3, aurl = wmt_api_rows(base, log, team)
    if rows3:
        st, det = _judge_rows(rows3, aurl, team, opponent, date, canonical)
        if st in ("AGREE_COMPLETE", "CONTRADICTS", "CONTRADICTS_SETS",
                  "REPORTS", "NOT_POSTED"):
            return st, det
        best = better(st, det)
    return best


def verdict(sa, sb):
    """Only complete agreement verifies. A set-count disagreement is a
    contradiction of the canonical record -- two schools in that state is
    the review candidate, not a verification (the consult's catch: the old
    retired winner-only 'partial agreement' state let two officially-published 3-1s verify our 3-2)."""
    con = {"CONTRADICTS", "CONTRADICTS_SETS"}
    if sa == "AGREE_COMPLETE" and sb == "AGREE_COMPLETE":
        return "VERIFIED_BOTH"
    if sa in con and sb in con:
        return "CONTRADICTED_BOTH"
    if (sa in con) != (sb in con) and "AGREE_COMPLETE" in (sa, sb):
        return "SCHOOL_CONFLICT"
    if sa in con or sb in con:
        return "CONTRADICTED_ONE"
    if "AGREE_COMPLETE" in (sa, sb):
        return "CORROBORATED_ONE"
    return "UNVERIFIED"


HELD_FOR_VERIFICATION = ("self_contradictory", "empty", "under_review")


def held_verdict(sa, sb):
    """What the schools said about a match that counts nowhere.

    Deliberately a SEPARATE vocabulary from verdict(): none of these words
    may ever be mistaken for verification. A held match has no counted
    result, so nothing here can confirm one, and none of these states is in
    the set that lets a same-day final feed a rating.
    """
    n = sum(1 for st in (sa, sb) if st == "REPORTS")
    if n == 2:
        return "HELD_BOTH_REPORT"
    if n == 1:
        return "HELD_ONE_REPORTS"
    return "HELD_NO_REPORT"


def finals_for(date):
    games = []
    with open(os.path.join(RAW, "games.jsonl")) as f:
        for line in f:
            try:
                games.append(json.loads(line))
            except ValueError:
                continue
    out = []
    cls_of = SC.classify(games, SEASON)
    _corr = SC.corrections(SEASON)
    for g in SC.resolve(games):
        _cls = cls_of.get(str(g.get("game_id")))
        # ⚠⚠ THE MATCHES THAT NEED THE SCHOOLS MOST WERE THE ONES NEVER ASKED
        # (found 2026-09-13, by the third witness). This filter kept exactly
        # the counted results and dropped every HELD one -- and a held match
        # counts NOWHERE until somebody establishes what happened, which is
        # precisely what a school's own schedule does. The comment below,
        # written the day the flagless final was found, says a final with no
        # derivable winner "NEEDS verification most of all"; this line above
        # it had already thrown it away. 11 held matches from 2026-09-12 had
        # no verification record at all.
        # A held match is fetched for OBSERVATION, never for verification:
        # it has no canonical, so no school can agree with one, it can never
        # enter verified_result_gids, and no ranking moves on it.
        if _cls != "ok" and _cls not in HELD_FOR_VERIFICATION:
            continue
        # ⚠ VERIFY THE COUNTED RESULT, NOT THE FEED'S REFUTED CLAIM
        # (2026-09-04): before this line, an already-corrected inversion
        # reported CONTRADICTED_BOTH every night forever -- the schools
        # were "contradicting" a canonical the ledger had already
        # overturned. Both schools agreeing with the CORRECTION is the
        # nightly proof the correction still holds.
        g = SC.apply_correction(g, _corr)
        et = g.get("start_time_epoch")
        if not et:
            continue
        d = (datetime.datetime.fromtimestamp(et, datetime.timezone.utc)
             - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")
        if d != date:
            continue
        ts = g.get("teams") or []
        if len(ts) != 2:
            continue
        _wi = SC.winner_index(g)   # sets decide when is_winner is absent/
        if _cls != "ok" or _wi is None:
            # HELD: no canonical, so the two sides are carried in the order
            # the feed lists them and nothing is asserted about either.
            names = [t.get("name_short") for t in ts]
            if not all(names):
                continue
            out.append({"gid": str(g.get("game_id")),
                        "held": _cls or "empty",
                        "sides": names,
                        "winner": None, "loser": None,
                        "w_sets": None, "l_sets": None})
            continue
        w, l = ts[_wi], ts[1 - _wi]
        out.append({"gid": str(g.get("game_id")),
                    "sides": [w.get("name_short"), l.get("name_short")],
                    "winner": w.get("name_short"),
                    "loser": l.get("name_short"),
                    "w_sets": w.get("sets_won"),
                    "l_sets": l.get("sets_won")})
    return out


AUTO_EVIDENCE = os.path.join(RAW, "result_evidence_auto.json")


def write_auto_evidence():
    """Regenerate result_evidence_auto.json from every committed daily
    report: latest observation per (gid, school). Deterministic and
    disposable -- deleting the file loses nothing the reports do not hold."""
    import glob
    latest = {}
    for rp in sorted(glob.glob(os.path.join(
            REPO, "data", "result_verification_*.json"))):
        try:
            doc = json.load(open(rp))
        except ValueError:
            continue
        gen = doc.get("generated_utc") or ""
        for m in doc.get("matches") or []:
            gid = str(m.get("gid"))
            for school, e in (m.get("schools") or {}).items():
                st = e.get("state")
                if st not in ("AGREE_COMPLETE", "CONTRADICTS",
                              "CONTRADICTS_SETS"):
                    continue
                key = (gid, school)
                prev = latest.get(key)
                if prev and prev["generated"] > gen:
                    continue
                latest[key] = {
                    "url": e.get("url"),
                    "kind": "school_schedule",
                    "school": school,
                    "retrieved": (e.get("retrieved_utc") or gen),
                    "text": e.get("assertion"),
                    "fields": ["result"],
                    "status": ("confirms" if st == "AGREE_COMPLETE"
                               else "conflict_observed"),
                    "observed_state": st,
                    "origin": "nightly_verifier",
                    "generated": gen,
                }
    ev = {}
    for (gid, _school), entry in sorted(latest.items()):
        ev.setdefault(gid, []).append(entry)
    json.dump({
        "_doc": ("MACHINE-DERIVED evidence projection, regenerated by "
                 "verify_results_daily.py from the committed daily "
                 "verification reports -- the latest usable observation per "
                 "(gid, school). Do NOT hand-edit; hand-curated evidence "
                 "lives in result_evidence.json, and a validated "
                 "conflict_observed entry is PROMOTED there by a human as a "
                 "real 'conflicts' entry. conflict_observed can never lift "
                 "or dispute a state (confidence.entry_supports ignores "
                 "it); 'confirms' entries corroborate and, being the "
                 "'school' kind alone, can never cross-source CONFIRM a "
                 "result without an independent box-kind source."),
        "evidence": ev}, open(AUTO_EVIDENCE, "w"), indent=1)
    print("auto evidence: %d observation(s) across %d match(es) -> %s"
          % (len(latest), len(ev), os.path.relpath(AUTO_EVIDENCE, REPO)))


def gather_evidence(finals, sites, date, workers=None):
    """Both schools' ladders for every final, keyed (index, side) so the
    caller reassembles in the original order. `workers` defaults to
    VERIFY_WORKERS; workers=1 is a genuinely serial sweep, which is what the
    guard compares the parallel result against."""
    # ⚠ PARALLEL ACROSS SCHOOLS, STRICTLY SEQUENTIAL PER HOST (2026-09-11).
    # MEASURED in CI: this step was 651.6s of an 860s rebuild -- 76% of it,
    # and the reason the half-hourly refresh began hitting its own 25-minute
    # bound (the header's "run of about 3 minutes" had become 23). It is pure
    # I/O wait: up to 16 fetches per school, each spaced 0.5s and allowed a
    # 20s timeout, run one school strictly after another.
    #
    # WHAT CHANGES IS THE WALL CLOCK AND NOTHING ELSE. Each school's ladder
    # still runs in the same order with the same spacing, and _host_lock
    # holds one lock per hostname for the whole ladder -- so an individual
    # athletics site sees exactly the traffic it saw before. Only DIFFERENT
    # schools overlap. Results are reassembled in the original order, so the
    # report rows, the printed lines and the append-only fetch log come out
    # in the same sequence a serial run produced.
    tasks = []
    for _i, _f in enumerate(finals):
        # ⚠ PAIRED BY SIDES, NOT BY WINNER/LOSER -- a held match has no
        # winner, and reusing those keys for "the two teams" would be the
        # field-meaning trap this codebase keeps paying for (R4).
        _a, _b = _f["sides"]
        tasks.append((_i, 0, _f, _a, _b))
        tasks.append((_i, 1, _f, _b, _a))

    def _one(task):
        _idx, _side, _fin, team, opp = task
        mylog = []
        base = sites.get(team)
        if base is None:          # SITE_NOT_CONFIGURED -- no fetch, no host
            return task, school_evidence(team, opp, date, _fin, sites,
                                         mylog), mylog
        with _host_lock(base):
            return task, school_evidence(team, opp, date, _fin, sites,
                                         mylog), mylog

    done, logs = {}, {}
    if tasks:
        _w = VERIFY_WORKERS if workers is None else max(1, int(workers))
        with ThreadPoolExecutor(max_workers=min(_w, len(tasks))) as _ex:
            for task, res, mylog in _ex.map(_one, tasks):
                done[(task[0], task[1])] = res
                logs[(task[0], task[1])] = mylog
    return done, logs


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    incremental = "--incremental" in sys.argv
    date = args[0] if args else (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")
    sites = _sites()
    finals = finals_for(date)
    # --incremental (intraday, 2026-09-04): verify only finals with no
    # settled verdict yet, and MERGE into the day's report. A settled
    # verdict (VERIFIED_BOTH / CORROBORATED_ONE / CONTRADICTED_*) is not
    # re-fetched every 20 minutes; NOT_POSTED-class outcomes are retried,
    # because a school posting an hour after the final is the normal case.
    prior = {}
    if incremental:
        _pp = os.path.join(REPO, "data",
                           "result_verification_%s.json" % date)
        if os.path.exists(_pp):
            for r in json.load(open(_pp)).get("matches", []):
                prior[str(r.get("gid"))] = r
        settled = {g for g, r in prior.items()
                   if r.get("verdict") in ("VERIFIED_BOTH",
                                           "CORROBORATED_ONE",
                                           "CONTRADICTED_BOTH",
                                           "CONTRADICTED_ONE",
                                           "SCHOOL_CONFLICT",
                                           # both schools have published on a
                                           # held match: the evidence is in,
                                           # and a human files from here.
                                           "HELD_BOTH_REPORT")}
        # ⚠ A SETTLED VERDICT IS ABOUT A PARTICULAR CANONICAL, AND THE
        # CANONICAL CAN MOVE UNDER IT. File a correction on a match whose
        # verdict already settled and the stored row keeps describing the
        # refuted claim forever -- the 2026-09-11 report still read "Weber
        # St. def. Kansas St. 3-1" a day after the ledger overturned it, and
        # the nightly re-confirmation (both schools agreeing with the
        # CORRECTION) never runs for it. A row whose canonical no longer
        # matches is re-verified however settled it was.
        _canon_now = {}
        for _f in finals:
            _canon_now[_f["gid"]] = (
                "HELD as %s -- %s vs %s, no counted result"
                % (_f["held"], _f["sides"][0], _f["sides"][1])
                if _f.get("held") else
                "%s def. %s %d-%d" % (_f["winner"], _f["loser"],
                                      _f["w_sets"], _f["l_sets"]))
        settled = {g for g in settled
                   if prior[g].get("canonical") == _canon_now.get(g, object())}
        finals = [f for f in finals if f["gid"] not in settled]
    _n_held = sum(1 for f in finals if f.get("held"))
    print("verifying %d matches for %s against both schools' published "
          "schedules -- %d counted finals, %d HELD (observed only, never "
          "verified)%s" % (
              len(finals), date, len(finals) - _n_held, _n_held,
              " (incremental; %d already settled)" % len(prior)
              if incremental else ""))
    done, logs = gather_evidence(finals, sites, date)

    log, report, queue_adds = [], [], []
    for _i, f in enumerate(finals):
        sa, da = done[(_i, 0)]
        sb, db = done[(_i, 1)]
        log.extend(logs[(_i, 0)])
        log.extend(logs[(_i, 1)])
        _a, _b = f["sides"]
        if f.get("held"):
            v = held_verdict(sa, sb)
            canon = ("HELD as %s -- %s vs %s, no counted result"
                     % (f["held"], _a, _b))
        else:
            v = verdict(sa, sb)
            canon = "%s def. %s %d-%d" % (
                f["winner"], f["loser"], f["w_sets"], f["l_sets"])
        row = {"gid": f["gid"], "date": date,
               "canonical": canon,
               "verdict": v,
               "schools": {_a: {"state": sa, **da},
                           _b: {"state": sb, **db}}}
        if f.get("held"):
            row["held_as"] = f["held"]
        report.append(row)
        if v in ("CONTRADICTED_BOTH", "CONTRADICTED_ONE", "SCHOOL_CONFLICT",
                 # a held match a school HAS published on is the most
                 # actionable row in the report: it counts nowhere today and
                 # a school's own word is what ends that.
                 "HELD_BOTH_REPORT", "HELD_ONE_REPORTS"):
            queue_adds.append(row)
        print("  %-22s %s" % (v, row["canonical"]))

    # append-only fetch log
    with open(os.path.join(RAW, "result_verification_log.jsonl"), "a") as f:
        for e in log:
            f.write(json.dumps(e) + "\n")
    # the day's report (rewritten per run -- it is derived, the log is raw).
    # In incremental mode, fresh rows replace their gid's prior row and
    # settled prior rows are kept -- the report stays whole-day.
    if incremental and prior:
        fresh = {str(r["gid"]): r for r in report}
        prior.update(fresh)
        report = list(prior.values())
    outp = os.path.join(REPO, "data", "result_verification_%s.json" % date)
    counts = {}
    for r in report:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    json.dump({"date": date, "generated_utc": datetime.datetime.utcnow()
               .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "counts": counts, "matches": report},
              open(outp, "w"), indent=1)
    print("report: %s  %s" % (outp, counts))

    # ── the auto evidence projection ─────────────────────────────────────
    # (design settled with the external consult, 2026-09-01 evening)
    # A SEPARATE regenerable file, never the hand-curated ledger: the LATEST
    # usable observation per (gid, school), rebuilt from ALL committed daily
    # reports. Affirmative observations only -- NOT_POSTED / EVENT_NOT_FOUND
    # / SITE_* assert nothing and stay in the reports and the fetch log. A
    # contradiction is written as status "conflict_observed", which
    # confidence.py's entry_supports deliberately IGNORES for state lifting:
    # one parser slip must never auto-DISPUTE the public ledger. A human
    # promotes a validated conflict into result_evidence.json as a real
    # "conflicts" entry.
    write_auto_evidence()

    # review candidates -- NEVER corrections. Merged, never overwritten.
    if queue_adds:
        qp = os.path.join(RAW, "result_review_queue.json")
        q = json.load(open(qp)) if os.path.exists(qp) else {}
        for row in queue_adds:
            q.setdefault(row["gid"], row)
        json.dump(q, open(qp, "w"), indent=1)
        print("⚠ %d REVIEW CANDIDATE(S) written to %s -- a human files any "
              "correction" % (len(queue_adds), qp))


if __name__ == "__main__":
    main()
