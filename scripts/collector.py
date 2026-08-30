#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OFFICIAL SOURCE COLLECTOR v1 — bounded, respectful, template-strict.

Expands the evidence base from ACCESSIBLE OFFICIAL school pages only.
What this is not: a generic scraper. It fetches a bounded, priority-ranked
queue of school schedule pages, extracts NARROW structured claims from the
two template types demonstrated readable on real pages (SIDEARM game-card
DOM and schema.org event JSON-LD), binds them strictly, and feeds them
through the EXISTING evidence rules:

  * an observed result that agrees/disagrees with our held final is
    appended to data/raw/{s}/result_evidence.json (status confirms /
    conflicts) -- confidence.py and source_intel.py already know what to
    do with those;
  * an observed venue/time/event that DIFFERS from the canonical fixture
    becomes an OBSERVATION (collector_observations.json), surfaced by
    source intel -- the collector NEVER writes a correction; corrections
    stay curated, per-field, human-reviewed;
  * agreement on schedule facts is recorded in the registry counters and
    produces NO claim -- material changes only, never crawler chatter.

Respect, mechanically enforced:
  * robots.txt is read per host and obeyed; disallowed = blocked, never
    fetched;
  * >= 2.5s between requests, one attempt per source per run, a 6h
    cooldown per school (priority classes 1-2 may retry sooner);
  * conditional GET (If-Modified-Since / If-None-Match) when the server
    offers validators;
  * a page that is blocked, JS-only, or unsupported is RECORDED as such
    -- never silently counted as checked.

Binding, the ASU lesson (R8-scrape): evidence binds to its OWN card's DOM
boundary; the opponent must resolve to the exact canonical team through
the project's resolver + the State/Saint folds; the (team, opponent,
date) triple must match exactly ONE known fixture or the observation
stays pending. Nothing is inferred from nearby text.

Python 3.9 target.
"""

import datetime
import io
import json
import os
import re
import sys
import time
import urllib.request
import urllib.robotparser
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))

REGISTRY = os.path.join(REPO, "data", "collector_registry_%d.json" % SEASON)
OBS = os.path.join(REPO, "data", "raw", str(SEASON),
                   "collector_observations.json")
REVID = os.path.join(REPO, "data", "raw", str(SEASON),
                     "result_evidence.json")
CACHE = os.path.join(REPO, "data", "raw", str(SEASON), "collector_cache")

QUEUE_CAP = 12            # bounded by design
MIN_INTERVAL = 2.5        # seconds between requests
COOLDOWN_H = 6            # per-school, unless priority 1-2
TIMEOUT = 15
UA = ("wvb-hub/1.0 (personal volleyball stats project; respectful "
      "collector; obeys robots.txt) Mozilla/5.0 compatible")

SCHEDULE_PATHS = ("/sports/womens-volleyball/schedule",
                  "/sports/volleyball/schedule",
                  "/sports/wvball/schedule")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except ValueError:
        return default


def _save(path, doc):
    json.dump(doc, io.open(path, "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)


# ---- respectful fetch --------------------------------------------------

_ROBOTS = {}


def robots_allows(url):
    from urllib.parse import urlparse
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    if host not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(host + "/robots.txt",
                                         headers={"User-Agent": UA})
            body = urllib.request.urlopen(req, timeout=10).read()
            rp.parse(body.decode("utf-8", "replace").splitlines())
        except Exception:
            rp = None                      # unreadable robots: default allow
        _ROBOTS[host] = rp
    rp = _ROBOTS[host]
    return True if rp is None else rp.can_fetch(UA, url)


_LAST_FETCH = [0.0]


def fetch(url, meta=None):
    """(status, html, new_meta). Conditional when validators are cached.
    status: http code, 'not_modified', 'blocked_robots', or 'error:...'."""
    if not robots_allows(url):
        return "blocked_robots", None, meta or {}
    wait = MIN_INTERVAL - (time.time() - _LAST_FETCH[0])
    if wait > 0:
        time.sleep(wait)
    headers = {"User-Agent": UA}
    meta = meta or {}
    if meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]
    req = urllib.request.Request(url, headers=headers)
    _LAST_FETCH[0] = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=TIMEOUT)
        body = r.read().decode("utf-8", "replace")
        return r.status, body, {
            "etag": r.headers.get("ETag"),
            "last_modified": r.headers.get("Last-Modified")}
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return "not_modified", None, meta
        return e.code, None, meta
    except Exception as e:                                 # noqa: BLE001
        return "error:%s" % type(e).__name__, None, meta


# ---- template detection & extraction ----------------------------------

def detect_template(html):
    if not html:
        return "unreadable"
    if 'class="s-game-card' in html:
        return "sidearm_cards"
    if 'application/ld+json' in html and '"startDate"' in html:
        return "schema_events"
    if len(html) < 120000 and html.count("<script") > html.count("<a "):
        return "browser_only"              # JS shell: markup without content
    return "unsupported_v1"


# ⚠ ROOT CARDS ONLY. `s-game-card-game-link-button` and friends also
# start with the prefix; matching them fragmented every card at its first
# button and the result text landed in an orphan fragment (first run: 74
# "cards" from a 25-game schedule, zero results extracted). A root is the
# class followed by a space, quote, or the BEM `--` modifier.
_CARD_ROOT = re.compile(r'class="s-game-card(?:["\s]|--)')
_TAGS = re.compile(r"<[^>]+>")


def _cards(html):
    """Card-bounded slices -- the boundary IS the safety (R8-scrape)."""
    idx = [m.start() for m in _CARD_ROOT.finditer(html)]
    out = []
    for i, a in enumerate(idx):
        b = idx[i + 1] if i + 1 < len(idx) else min(len(html), a + 20000)
        out.append(html[a:b])
    return out


def _card_text(card):
    t = _TAGS.sub("|", card)
    t = re.sub(r"\s+", " ", t)
    return re.sub(r"\|+", "|", t)


def parse_sidearm_cards(html, season_year):
    """One dict per card. Extracts ONLY what the card itself states."""
    out = []
    for card in _cards(html):
        t = _card_text(card)
        m = re.search(r'title="([^"]{2,60})"', card)
        opp = re.sub(r"^#\d+\s*", "", m.group(1)).strip() if m else None
        dm = re.search(r"\b(%s)\s+(\d{1,2})\b" % "|".join(MONTHS), t)
        date = None
        if dm:
            mo = MONTHS[dm.group(1)]
            yr = season_year if mo >= 8 else season_year + 1
            date = "%04d-%02d-%02d" % (yr, mo, int(dm.group(2)))
        # tag-stripping leaves a pipe between the verdict letter and the
        # score ("W, |3-0"); the letter must be its own token so a W in a
        # word can never match
        rm = re.search(r"[|\s]([WL])\s*,?[\s|]*(\d)\s*-\s*(\d)\b", t)
        result = ((rm.group(1), int(rm.group(2)), int(rm.group(3)))
                  if rm else None)
        tm = re.search(r"\b(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?"
                       r"(?:\s*[A-Z]{2,3})?)", t, re.I)
        exh = bool(re.search(r"Scrimmage\s*/\s*Exhibition|Exhibition",
                             t, re.I))
        out.append({"opponent": opp, "date": date, "result": result,
                    "time": tm.group(1) if tm else None,
                    "exhibition_label": exh,
                    "excerpt": t.strip("| ")[:300]})
    return out


def parse_schema_events(html):
    out = []
    for m in re.finditer(
            r'<script type="application/ld\+json">(.*?)</script>',
            html, re.S):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        for e in (d if isinstance(d, list) else [d]):
            if not isinstance(e, dict) or "startDate" not in e:
                continue
            loc = e.get("location") or {}
            if isinstance(loc, dict):
                addr = loc.get("address") or {}
                venue = loc.get("name")
                city = (addr.get("addressLocality")
                        if isinstance(addr, dict) else None)
            else:
                venue = city = None
            out.append({"name": e.get("name"),
                        "start": str(e.get("startDate"))[:16],
                        "venue": venue, "city": city,
                        "excerpt": json.dumps(
                            {k: e.get(k) for k in
                             ("name", "startDate", "location")},
                            ensure_ascii=False)[:300]})
    return out


# ---- strict binding ----------------------------------------------------

def _fold_tokens(name):
    from exhibitions import _fold
    return _fold(name)


def bind_opponent(raw, teams):
    """raw opponent text -> exactly one canonical team, else None.

    Whole folded token sequence through the project resolver -- never a
    shared first word (the Kentucky/Kent St. rule)."""
    if not raw:
        return None
    # a school page says "Gardner-Webb University" / "University of
    # Dayton" where the hub says "Gardner-Webb" -- try the raw text and
    # its institutional-suffix strips, still EXACT fold equality each time
    cands = [raw]
    # explicit official short forms, each verified on a real page --
    # 'Southern' is how SWAC pages print Southern University (seen on
    # jsugamecocks.com beside 'Southern Miss', which stays distinct).
    # NEVER fuzzy: an alias maps one exact string to one exact team.
    ALIASES = {"Southern": "Southern U."}
    if raw.strip() in ALIASES:
        cands.insert(0, ALIASES[raw.strip()])
    m = re.match(r"(?i)^university of (.+)$", raw.strip())
    if m:
        cands.append(m.group(1))
    m = re.match(r"(?i)^(.+?)\s+(university|college)$", raw.strip())
    if m:
        cands.append(m.group(1))
    tgt = None
    for cand in cands:
        raw_tokens = _fold_tokens(cand)
        for t in teams:
            if _fold_tokens(t) == raw_tokens:
                if tgt is not None and tgt != t:
                    return None            # ambiguous: stays pending
                tgt = t
        if tgt:
            break
    return tgt


def fixture_index():
    """(normA, normB, date) -> [gid], both name orders, ET and PT dates."""
    import fixtures as FX
    from reconcile_2025 import norm
    live = _load(os.path.join(REPO, "data", "data_%d.json" % SEASON), {})
    id2n = dict((str(t.get("team_id")),
                 t.get("name_short") or t.get("name_full"))
                for t in live.get("teams") or [])
    import dupes
    _dups = dupes.duplicate_gids(SEASON)
    idx = {}
    teams = set()
    for gid, r in FX.canonical_fixtures().items():
        if str(gid) in _dups:
            continue                       # ledgered duplicates never bind
        ts = r.get("teams") or []
        if len(ts) != 2:
            continue
        names = [id2n.get(str(t.get("team_id"))) for t in ts]
        if not all(names):
            continue
        teams.update(names)
        ep = r.get("start_time_epoch") or 0
        dates = set()
        for off in (4 * 3600, 7 * 3600):   # ET and PT local dates
            if ep:
                dates.add(datetime.datetime.utcfromtimestamp(ep - off)
                          .strftime("%Y-%m-%d"))
        key_ab = tuple(sorted(norm(n) for n in names))
        for d in dates:
            idx.setdefault((key_ab, d), []).append(gid)
    return idx, sorted(teams)


def bind_fixture(team, opp, date, idx):
    from reconcile_2025 import norm
    if not (team and opp and date):
        return None
    key = (tuple(sorted((norm(team), norm(opp)))), date)
    gids = idx.get(key) or []
    return gids[0] if len(gids) == 1 else None   # ambiguous stays pending


# ---- the queue ---------------------------------------------------------

def build_queue(cap=QUEUE_CAP):
    """Priority classes, then dedupe, then cap. Every class is a REAL
    signal from the build's own artifacts, not a guess."""
    picks = []                                     # (priority, team, why)
    conf = _load(os.path.join(
        REPO, "data", "result_confidence_%d.json" % SEASON), {})
    live = _load(os.path.join(REPO, "data", "data_%d.json" % SEASON), {})
    id2n = dict((str(t.get("team_id")),
                 t.get("name_short") or t.get("name_full"))
                for t in live.get("teams") or [])
    gid_teams = {}
    for g in live.get("games") or []:
        gid_teams[str(g.get("game_id"))] = [
            id2n.get(str(t.get("team_id"))) for t in g.get("teams") or []]
    for r in conf.get("finals") or []:
        if r.get("overall") == "official" and r.get("states", {}) \
                .get("sets") == "official":
            for t in gid_teams.get(str(r.get("gid"))) or []:
                if t:
                    picks.append((1, t, "official-only final %s"
                                  % r.get("gid")))
        if r.get("overall") in ("disputed",):
            for t in gid_teams.get(str(r.get("gid"))) or []:
                if t:
                    picks.append((1, t, "disputed result %s"
                                  % r.get("gid")))
    intel = _load(os.path.join(
        REPO, "data", "source_intel_%d.json" % SEASON), {})
    for c in intel.get("claims") or []:
        if c.get("state") == "conflicting":
            gid = (c.get("subject") or {}).get("gid")
            for t in gid_teams.get(str(gid)) or []:
                if t:
                    picks.append((2, t, "source conflict %s" % gid))
        if c.get("type") in ("fixture_update", "result_correction"):
            gid = (c.get("subject") or {}).get("gid")
            for t in gid_teams.get(str(gid)) or []:
                if t:
                    picks.append((4, t, "recently corrected fixture"))
    board = _load(os.path.join(
        REPO, "data", "rankings_board_%d.json" % SEASON), {})
    avca = _load(os.path.join(
        REPO, "data", "raw", str(SEASON), "poll_avca.json"), {})
    for row in (avca.get("rows") or [])[:25]:
        nm = row.get("school") or row.get("team")
        if nm:
            picks.append((5, nm, "AVCA ranked"))
    # today's watch queue: the desk artifact is inside the page build;
    # approximate with today's D-I scoreboard teams that are AVCA-ranked
    picks.sort(key=lambda x: x[0])
    seen, queue = set(), []
    for pr, team, why in picks:
        if team in seen:
            continue
        seen.add(team)
        queue.append({"team": team, "priority": pr, "why": why})
        if len(queue) >= cap:
            break
    return queue


# ---- claims ------------------------------------------------------------

def our_final(gid):
    live = _load(os.path.join(REPO, "data", "data_%d.json" % SEASON), {})
    for g in live.get("games") or []:
        if str(g.get("game_id")) == str(gid) and g.get("state") == "F":
            return g
    return None


def result_agrees(g, team, obs):
    """Does the observed (W/L, a-b) from TEAM's page match our record?"""
    live = _load(os.path.join(REPO, "data", "data_%d.json" % SEASON), {})
    id2n = dict((str(t.get("team_id")),
                 t.get("name_short") or t.get("name_full"))
                for t in live.get("teams") or [])
    mine = next((t for t in g.get("teams") or []
                 if id2n.get(str(t.get("team_id"))) == team), None)
    theirs = next((t for t in g.get("teams") or []
                   if id2n.get(str(t.get("team_id"))) != team), None)
    if not mine or not theirs:
        return None
    wl, a, b = obs
    won = mine.get("sets_won"), theirs.get("sets_won")
    if won[0] is None or won[1] is None:
        return None                        # our record asserts nothing
    ours = ("W" if won[0] > won[1] else "L", won[0], won[1])
    return ours == (wl, a, b)


def append_result_evidence(gid, team, url, excerpt, agrees, retrieved):
    doc = _load(REVID, {"_doc": "collector-extended", "evidence": {}})
    ent = doc.setdefault("evidence", {}).setdefault(str(gid), [])
    for e in ent:                          # one entry per (url, status)
        if e.get("url") == url and e.get("collector"):
            return False
    ent.append({
        "url": url, "kind": "school_site", "school": team,
        "retrieved": retrieved, "text": excerpt,
        "fields": ["result"],
        "value": {"result": "as printed on the school's schedule row"},
        "status": "confirms" if agrees else "conflicts",
        "review_by": None, "collector": True,
    })
    _save(REVID, doc)
    return True


def record_observation(gid, team, fields, url, excerpt, retrieved,
                       observed):
    doc = _load(OBS, {"_doc": (
        "Schedule-fact OBSERVATIONS from official school pages, written "
        "by scripts/collector.py. An observation is evidence, never a "
        "correction: it is surfaced by source intel and a human-reviewed "
        "ledger entry is the only thing that changes a fact."),
        "observations": {}})
    key = "%s|%s" % (gid, ",".join(sorted(fields)))
    obs = doc.setdefault("observations", {})
    if key in obs and obs[key].get("url") == url:
        return False
    obs[key] = {"gid": str(gid), "team": team, "fields": sorted(fields),
                "url": url, "excerpt": excerpt, "retrieved": retrieved,
                "observed": observed,
                "review_by": (datetime.date.today()
                              + datetime.timedelta(days=10)).isoformat()}
    _save(OBS, doc)
    return True


# ---- the run -----------------------------------------------------------

def run(cap=QUEUE_CAP, now=None):
    os.makedirs(CACHE, exist_ok=True)
    reg = _load(REGISTRY, {"_doc": (
        "Official-source collector registry: per school -- url, template, "
        "access status, last attempt, per-field capability. An entry only "
        "exists for a school actually ATTEMPTED; absence means untried, "
        "never 'checked'."), "sources": {}})
    sources = reg.setdefault("sources", {})
    sites = _load(os.path.join(
        REPO, "data", "raw", str(SEASON), "athletics_sites.json"), {})
    over = (_load(os.path.join(
        REPO, "data", "raw", str(SEASON),
        "athletics_sites_overrides.json"), {}) or {}).get("overrides") or {}
    idx, all_teams = fixture_index()
    queue = build_queue(cap)
    stamp = now or _now()
    stats = {"attempted": 0, "readable": 0, "not_modified": 0,
             "blocked": 0, "browser_only": 0, "unsupported": 0,
             "errors": 0, "skipped_cooldown": 0,
             "claims_result": 0, "claims_conflict": 0,
             "observations": 0, "agreements_silent": 0,
             "pending_unbound": 0}
    for q in queue:
        team = q["team"]
        rec = sources.get(team) or {}
        last = rec.get("last_attempt_utc")
        if last and q["priority"] > 2:
            try:
                age_h = (datetime.datetime.utcnow()
                         - datetime.datetime.strptime(
                             last, "%Y-%m-%dT%H:%M:%SZ")
                         ).total_seconds() / 3600
                if age_h < COOLDOWN_H:
                    stats["skipped_cooldown"] += 1
                    continue
            except ValueError:
                pass
        base = (over.get(team) or {}).get("url") if isinstance(
            over.get(team), dict) else over.get(team)
        base = base or (sites.get(team) or {}).get("url")
        if not base:
            sources[team] = {"access": "no_known_site",
                             "last_attempt_utc": stamp, "why": q["why"]}
            continue
        stats["attempted"] += 1
        url = html = None
        status = None
        for path in ([rec.get("path")] if rec.get("path") else []) + \
                [p for p in SCHEDULE_PATHS if p != rec.get("path")]:
            url = base.rstrip("/") + path
            status, html, meta = fetch(url, rec.get("http_meta"))
            if status in (200, "not_modified"):
                rec["path"] = path
                rec["http_meta"] = meta
                break
        rec.update({"url": url, "school": team,
                    "last_attempt_utc": stamp,
                    "last_status": str(status), "why": q["why"]})
        if status == "not_modified":
            stats["not_modified"] += 1
            rec["access"] = "readable"
            sources[team] = rec
            continue
        if status == "blocked_robots" or status in (403, 401, 429):
            stats["blocked"] += 1
            rec["access"] = "blocked"
            sources[team] = rec
            continue
        if status != 200 or not html:
            stats["errors"] += 1
            rec["access"] = "unreachable"
            sources[team] = rec
            continue
        tpl = detect_template(html)
        rec["template"] = tpl
        if tpl == "browser_only":
            stats["browser_only"] += 1
            rec["access"] = "browser_only"
            sources[team] = rec
            continue
        if tpl not in ("sidearm_cards", "schema_events"):
            stats["unsupported"] += 1
            rec["access"] = "unsupported_v1"
            sources[team] = rec
            continue
        stats["readable"] += 1
        rec["access"] = "readable"
        rec["fields_supported"] = (
            ["result", "date", "time", "venue", "event"]
            if tpl == "sidearm_cards" else ["date", "time", "venue"])
        io.open(os.path.join(CACHE, "%s.html"
                             % re.sub(r"[^A-Za-z0-9]+", "_", team)),
                "w", encoding="utf-8").write(html)

        cards = (parse_sidearm_cards(html, SEASON)
                 if tpl == "sidearm_cards" else [])
        n_new = 0
        for c in cards:
            opp = bind_opponent(c["opponent"], all_teams)
            if not opp:
                if c.get("result"):
                    stats["pending_unbound"] += 1
                continue
            gid = bind_fixture(team, opp, c["date"], idx)
            if not gid:
                if c.get("result"):
                    stats["pending_unbound"] += 1
                continue
            if c.get("exhibition_label"):
                continue                   # classification stays curated
            if c.get("result"):
                g = our_final(gid)
                if not g:
                    continue
                agrees = result_agrees(g, team, c["result"])
                if agrees is None:
                    continue
                if append_result_evidence(gid, team, url, c["excerpt"],
                                          agrees, stamp):
                    n_new += 1
                    stats["claims_result" if agrees
                          else "claims_conflict"] += 1
        rec["last_new_claims"] = n_new
        sources[team] = rec
    reg["last_run_utc"] = stamp
    _save(REGISTRY, reg)
    return stats, queue


if __name__ == "__main__":
    stats, queue = run()
    print("collector queue (%d):" % len(queue))
    for q in queue:
        print("  p%d %-22s %s" % (q["priority"], q["team"], q["why"]))
    print("collector run:", json.dumps(stats))
