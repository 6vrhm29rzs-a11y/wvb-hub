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
            doc[team] = {"status": "no_site", "retrieved": now_s}
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
            if events:
                used = site + path
                break
            # a page fetched but with no payload: remember we tried
            used = used or (site + path)
            if "__NUXT_DATA__" not in (page or ""):
                break                    # not this template family; stop
        fetched += 1
        if events:
            nets = sum(1 for e in events if e.get("network"))
            doc[team] = {"status": "ok", "source_url": used,
                         "retrieved": now_s, "events": events,
                         "events_with_network": nets}
            withtv += 1
            print("  %-24s %d events, %d with a network" % (team, len(events), nets))
        else:
            doc[team] = {"status": "no_payload", "source_url": used,
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
