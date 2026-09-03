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
import time
import urllib.request
import urllib.error

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
    n = re.sub(r"\bcollege\b", " ", n)
    # "Charleston Southern" (page) vs "Charleston So." (hub) -- the same
    # word folded the same way on both sides
    n = re.sub(r"\bsouthern\b", "so", n)
    n = re.sub(r"\s+", " ", n).strip()
    # the residual pairs no general fold covers -- the FIG_ALIASES pattern,
    # keyed on the FOLDED form, both directions where needed. A global
    # parenthetical strip is banned: Miami (FL) and Miami (OH) would merge.
    return _VERIFIER_ALIASES.get(n, n)


def _strip_inst(n):
    """Trailing ' university' / ' u' removed from a NORMALIZED key."""
    return re.sub(r"\s+(?:university|u)$", "", n).strip()


_STRIPPED_HUB = {}


def _stripped_hub_count(key):
    if not _STRIPPED_HUB:
        try:
            d = json.load(open(os.path.join(
                REPO, "data", "data_%d.json" % SEASON)))
            for t in d.get("teams") or []:
                k = _strip_inst(team_norm(t.get("name_short") or ""))
                _STRIPPED_HUB[k] = _STRIPPED_HUB.get(k, 0) + 1
        except (OSError, ValueError):
            return 2          # cannot check -> refuse pass 2
    return _STRIPPED_HUB.get(key, 0)


_VERIFIER_ALIASES = {
    "ucsb": "uc santa barbara",
    "queens": "queens nc",
    "queens university of charlotte": "queens nc",   # Duke's spelling
    "texas a and m corpus christi": "a and m corpus christi",
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
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:                                    # noqa: BLE001
        return None, str(e)[:120], url


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
    r'schedule-event-date__day|s-game-card)')


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
        exh = any(re.search(r"Exh|Intrasquad|Scrimmage", tk)
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
        return "EVENT_NOT_FOUND", {"url": url, "rows_on_date": [
            (r["opponent"] if r.get("opponent") is not None
             else " ".join((r.get("tokens") or [])[:6]))
            for r in rows if r["date"] == date]}
    r, opp_src = cand[0]
    if not r["result"]:
        return "NOT_POSTED", {"url": url, "row": r["raw"]}
    wl, a, b = r["result"]
    won = wl == "W"
    c_won = canonical["winner"] == team
    c_sets = (canonical["w_sets"], canonical["l_sets"]) if c_won \
        else (canonical["l_sets"], canonical["w_sets"])
    det = {"url": url, "assertion": "%s %s %d-%d vs %s"
           % (team, wl, a, b, opp_src),
           "opponent_source": opp_src,
           "site_says": r["site"]}
    if r.get("surface"):
        det["surface"] = r["surface"]
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
            mrows = parse_modern_cards(body)
            entry["state"] = "unparsed"
            entry["modern_blocks"] = len(mrows)
            log.append(entry)
            if mrows:
                st, det = _judge_rows(mrows, final_url, team, opponent,
                                      date, canonical)
                if st in ("AGREE_COMPLETE", "CONTRADICTS",
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
        mrows = parse_modern_cards(mbody)
        log.append({"team": team, "url": murl, "http": mstatus,
                    "retrieved_utc": datetime.datetime.utcnow()
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "state": "modern_probe", "modern_blocks": len(mrows)})
        if not mrows:
            continue
        st, det = _judge_rows(mrows, mfinal, team, opponent, date,
                              canonical)
        if st in ("AGREE_COMPLETE", "CONTRADICTS", "CONTRADICTS_SETS",
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
                  "NOT_POSTED"):
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
    for g in SC.resolve(games):
        if cls_of.get(str(g.get("game_id"))) != "ok":
            continue
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
        w = next((t for t in ts if t.get("is_winner")), None)
        l = next((t for t in ts if not t.get("is_winner")), None)
        if not w or not l:
            continue
        out.append({"gid": str(g.get("game_id")),
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


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")
    sites = _sites()
    finals = finals_for(date)
    print("verifying %d counted finals for %s against both schools' "
          "published schedules" % (len(finals), date))
    log, report, queue_adds = [], [], []
    for f in finals:
        sa, da = school_evidence(f["winner"], f["loser"], date, f, sites, log)
        sb, db = school_evidence(f["loser"], f["winner"], date, f, sites, log)
        v = verdict(sa, sb)
        row = {"gid": f["gid"], "date": date,
               "canonical": "%s def. %s %d-%d" % (
                   f["winner"], f["loser"], f["w_sets"], f["l_sets"]),
               "verdict": v,
               "schools": {f["winner"]: {"state": sa, **da},
                           f["loser"]: {"state": sb, **db}}}
        report.append(row)
        if v in ("CONTRADICTED_BOTH", "CONTRADICTED_ONE", "SCHOOL_CONFLICT"):
            queue_adds.append(row)
        print("  %-22s %s" % (v, row["canonical"]))

    # append-only fetch log
    with open(os.path.join(RAW, "result_verification_log.jsonl"), "a") as f:
        for e in log:
            f.write(json.dumps(e) + "\n")
    # the day's report (rewritten per run -- it is derived, the log is raw)
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
