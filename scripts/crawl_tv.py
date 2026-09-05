#!/usr/bin/env python3
"""Per-match TV/streaming from the schools' OWN schedule payloads.

Cody, 2026-09-04: "make sure streaming or live tv viewing information is
listed for each game. A lot are on ESPN or ESPN+." The NCAA feed's
`network` field is empty for volleyball (measured: 0 of 178 on a full
Friday) -- but modern SIDEARM schedule pages embed a Nuxt payload with a
per-event media block: `media.tv` (linear network), `media.video.title`
(the streaming network -- "SEC Network+", "B1G+", "FS1") and
`media.video.url` (the watch link itself). School-published, covers
FUTURE matches, and is the school's own claim about its own broadcast.

A school whose template does not carry the payload contributes NOTHING
(R5) -- its parse state is recorded, never guessed. Output is
data/raw/2026/tv_auto.json, one entry per school with evidence fields.

Python 3.9. Polite: ~1 req/s, resumable (schools fetched within
--max-age hours are skipped unless --force).
"""
import json
import os
import re
import sys
import time
import datetime
import urllib.request
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
RAW = os.path.join(REPO, "data", "raw", str(SEASON))
OUT = os.path.join(RAW, "tv_auto.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) wvb-hub schedule reader"

SCHEDULE_PATHS = ["/sports/womens-volleyball/schedule",
                  "/sports/wvball/schedule",
                  "/sports/womens-volleyball/schedule/season/2026"]

# bump when a parser learns a new template family: entries that previously
# parsed NOTHING are refetched, entries that parsed stay on their cadence
PARSER_V = 2

# the school's own network badge, from its coverage-image filename. Only
# KNOWN network tokens map; an unrecognised badge stays unlabelled (the
# watch link still counts). ESPN-vs-ESPN+ ambiguity resolves in favour of
# what the badge itself shows.
_BADGE = {
    "espn": "ESPN", "espn2": "ESPN2", "espnu": "ESPNU", "espn3": "ESPN3",
    "espnplus": "ESPN+", "espn_plus": "ESPN+", "accn": "ACCN",
    "accnx": "ACCNX", "secn": "SECN", "sec_network": "SEC Network",
    "fs1": "FS1", "fs2": "FS2", "btn": "BTN", "big_ten": "BTN",
    "cbssn": "CBSSN", "nesn": "NESN", "cusa": "CUSA.tv", "flosports": "FloSports",
    "flovolleyball": "FloVolleyball", "twesn": "The W", "peacock": "Peacock",
}


def _badge_label(src):
    # type: (str) -> Optional[str]
    base = re.sub(r"\.(png|jpe?g|svg|gif|webp)$", "",
                  (src or "").rsplit("/", 1)[-1].lower())
    base = re.sub(r"[_-]?crop\d*$", "", base)
    base = re.sub(r"[_-]?\d+$", "", base).strip("_-")
    return _BADGE.get(base) or _BADGE.get(base.replace("-", "_"))


_MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def parse_sidearm_html(page):
    # type: (str) -> Optional[List[Dict]]
    """The server-rendered SIDEARM family: sidearm-schedule-game-row cards.

    Per row: opponent-name div, opponent-date div ("Sep 8 (Tue) 6:00 PM"),
    an optional coverage IMAGE whose filename is the school's own network
    badge, and an optional per-row watch link."""
    rows = [m.start() for m in
            re.finditer(r'class="sidearm-schedule-game-row', page)]
    if len(rows) < 5:
        return None
    rows.append(len(page))
    events = []
    for a, b in zip(rows, rows[1:]):
        card = page[a:b]
        opp = re.search(
            r'sidearm-schedule-game-opponent-name[^>]*>(.*?)</div>',
            card, re.S)
        dt = re.search(
            r'sidearm-schedule-game-opponent-date[^>]*>(.*?)</div>',
            card, re.S)
        if not opp or not dt:
            continue
        opp_t = re.sub(r"\s+", " ",
                       re.sub(r"<[^>]+>", " ", opp.group(1))).strip()
        dt_t = re.sub(r"\s+", " ",
                      re.sub(r"<[^>]+>", " ", dt.group(1))).strip()
        m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})", dt_t)
        if not m or not opp_t:
            continue
        mon = _MON.get(m.group(1).lower())
        if not mon:
            continue
        year = SEASON if mon >= 8 else SEASON + 1
        date = "%04d-%02d-%02d" % (year, mon, int(m.group(2)))
        net = None
        cov = re.search(
            r'sidearm-schedule-game-coverage.{0,800}?src="([^"]+)"',
            card, re.S)
        if cov:
            net = _badge_label(cov.group(1))
        url = None
        vid = re.search(
            r'aria-label="Watch[^"]*"[^>]*href="([^"]+)"', card) or             re.search(r'href="([^"]+)"[^>]*aria-label="Watch[^"]*"', card)
        if vid:
            url = vid.group(1)
        if net or url:
            events.append({"date": date, "opponent": opp_t,
                           "network": net, "watch_url": url})
    return events or None


def fetch(url, timeout=25):
    # type: (str, int) -> Optional[str]
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _resolve(data, i, depth=0):
    if depth > 16:
        return None
    v = data[i] if isinstance(i, int) and 0 <= i < len(data) else i
    if isinstance(v, dict):
        return dict((k, _resolve(data, x, depth + 1)) for k, x in v.items())
    if isinstance(v, list):
        return [_resolve(data, x, depth + 1) for x in v[:80]]
    return v


def _network_from(media):
    # type: (Dict) -> Optional[str]
    """The school's own broadcast label, or None -- never invented.

    media.tv is the linear network when stated; media.video.title is the
    streaming network. A generic auto-title ("Video for Volleyball vs ...")
    names no network and is DISCARDED, not shown."""
    if not isinstance(media, dict):
        return None
    tv = (media.get("tv") or "").strip()
    if tv:
        return tv[:40]
    vid = media.get("video")
    if isinstance(vid, dict):
        t = (vid.get("title") or "").strip()
        tl = t.lower()
        # a generic action label names no network ("Watch", "Watch Live",
        # "Live", "Video", "Live Stream") -- the URL is still kept
        if t and not tl.startswith(("video for", "watch ", "live video")) \
                and tl not in ("watch", "live", "video", "live stream",
                               "live video", "stream", "watch live"):
            return t[:40]
    return None


def parse_nuxt(page):
    # type: (str) -> Optional[List[Dict]]
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>',
                  page, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    events = []
    for i, v in enumerate(data):
        if not (isinstance(v, dict) and "date" in v and "opponent" in v
                and "media" in v):
            continue
        ev = _resolve(data, i)
        if not isinstance(ev, dict):
            continue
        d = str(ev.get("date") or "")[:10]
        opp = ev.get("opponent") or {}
        opp_title = (opp.get("title") if isinstance(opp, dict) else None) or ""
        media = ev.get("media") or {}
        net = _network_from(media)
        vid = media.get("video") if isinstance(media, dict) else None
        url = (vid.get("url") if isinstance(vid, dict) else None) or None
        if re.match(r"\d{4}-\d{2}-\d{2}", d) and opp_title:
            events.append({"date": d, "opponent": opp_title.strip(),
                           "network": net, "watch_url": url})
    return events or None


def main():
    force = "--force" in sys.argv
    max_age_h = 20
    import verify_results_daily as V
    sites = V._sites()
    doc = {}
    if os.path.exists(OUT) and not force:
        try:
            doc = json.load(open(OUT))
        except ValueError:
            doc = {}
    doc.setdefault("_doc", (
        "Per-match TV/streaming, from each school's OWN schedule payload "
        "(the Nuxt media block: media.tv / media.video.title / "
        "media.video.url). A school whose template lacks the payload "
        "contributes nothing -- status says so; nothing is guessed."))
    now = datetime.datetime.utcnow()
    now_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    teams = sorted(k for k in sites if not k.startswith("_"))
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    done = fetched = withtv = 0
    for team in teams:
        if limit is not None and fetched >= limit:
            break
        ent = doc.get(team) or {}
        prev = ent.get("retrieved")
        # a parser upgrade refetches schools that previously parsed NOTHING
        if ent.get("status") not in (None, "ok") and \
                int(ent.get("parser_v") or 1) < PARSER_V:
            prev = None
        if prev and not force:
            try:
                age = (now - datetime.datetime.strptime(
                    prev, "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 3600.0
                if age < max_age_h:
                    done += 1
                    continue
            except ValueError:
                pass
        site = sites.get(team)
        if isinstance(site, dict):
            site = site.get("url")
        if not site or not isinstance(site, str):
            doc[team] = {"status": "no_site", "parser_v": PARSER_V, "retrieved": now_s}
            continue
        site = site.rstrip("/")
        events = None
        used = None
        for path in SCHEDULE_PATHS:
            page = fetch(site + path)
            time.sleep(1.0)
            if not page:
                continue
            events = parse_nuxt(page)
            if not events:
                events = parse_sidearm_html(page)
            if events:
                used = site + path
                break
            # a page fetched but with neither payload: remember we tried
            used = used or (site + path)
            if "__NUXT_DATA__" not in (page or "") and \
                    "sidearm-schedule-game" not in (page or ""):
                break                    # neither template family; stop
        fetched += 1
        if events:
            nets = sum(1 for e in events if e.get("network"))
            doc[team] = {"status": "ok", "parser_v": PARSER_V, "source_url": used,
                         "retrieved": now_s, "events": events,
                         "events_with_network": nets}
            withtv += 1
            print("  %-24s %d events, %d with a network" % (team, len(events), nets))
        else:
            doc[team] = {"status": "no_payload", "parser_v": PARSER_V, "source_url": used,
                         "retrieved": now_s}
    tmp = OUT + ".tmp"
    json.dump(doc, open(tmp, "w"), indent=1)
    os.replace(tmp, OUT)
    st = {}
    for k, v in doc.items():
        if k.startswith("_"):
            continue
        st[v.get("status")] = st.get(v.get("status"), 0) + 1
    print("tv_auto: %s -> %s" % (st, OUT))


if __name__ == "__main__":
    main()
