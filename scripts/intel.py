#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Intel Desk -- a private, local news wire.

⚠ THE SOURCE LIST IS THE SECURITY BOUNDARY. `SOURCES` below is the complete set
of URLs this program will ever request. `fetch_source()` takes a KEY, not a
URL, so nothing -- not the page, not a Film Room note, not a query string --
can redirect it. Adding a source means editing this list AND
docs/intel_sources.md, which records the audit behind it.

⚠ AND ONLY FOUR FIELDS SURVIVE PARSING. The feed carries `description` (the
publisher's own blurb), `enclosure` (a thumbnail) and `dc:creator`; all three
are discarded. Keeping the blurb would be storing somebody else's writing to
show instead of theirs. Title, link, time, category -- enough to decide whether
to click, and the click goes to them.

⚠ NOTHING HERE IS COMMITTED. The cache lives in `.intel_cache/`, which is
gitignored, and no Intel value enters any dataset, rating, ballot or the public
build.

Python 3.9 target.
"""

import datetime
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, ".intel_cache")
UA = ("wvb-hub/0.1 (personal research project; one feed poll per refresh)")
TIMEOUT = 20
MIN_REFRESH_SECONDS = 15 * 60

# ══ THE MEDIA ALLOWLIST ═══════════════════════════════════════════════════
# ⚠ SEPARATE FROM THE SOURCE ALLOWLIST, AND DELIBERATELY NARROWER. A source we
# will REQUEST is one thing; a host whose bytes we will let a browser load is
# another, and conflating them is how a feed ends up able to point the page at
# anything. Today they happen to be the same host, which is the safest possible
# case and is not a reason to merge the two lists.
#
# Audited 2026-08-25 (scripts/audit_intel_media.py, docs/intel_sources.md):
# every one of 20 items carries an <enclosure> whose URL is HTTPS on
# www.ncaa.com under /_flysystem/public-s3, in a large_16x9 derivative.
MEDIA_HOSTS = ("www.ncaa.com",)
MEDIA_PATH_PREFIXES = ("/_flysystem/",)


def media_url(raw):
    # type: (Any) -> Optional[str]
    """A feed-supplied image URL, or None. Never raises.

    ⚠ THIS IS A GATE, NOT A CLEANER. It does not repair a URL, strip a
    credential or upgrade a scheme -- anything that is not already exactly what
    was approved comes back as None and the story renders with no photo. A
    validator that fixes its input is a validator that accepts its input.
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if len(raw) > 600 or any(c in raw for c in " \t\r\n<>\"'"):
        return None
    try:
        from urllib.parse import urlparse
        u = urlparse(raw)
    except (ValueError, ImportError):
        return None
    # ⚠ HTTPS ONLY. A private page loading http:// would leak what is being
    # read to anything on the path, and mixed content is blocked anyway.
    if u.scheme != "https":
        return None
    # ⚠ NO USERINFO, NO PORT. `https://www.ncaa.com@evil.example/x` parses with
    # hostname `evil.example` -- the check below catches that, but a URL
    # carrying credentials at all is malformed for this purpose and is refused
    # before hostname comparison rather than after it.
    if u.username or u.password or u.port:
        return None
    if (u.hostname or "").lower() not in MEDIA_HOSTS:
        return None
    if not any((u.path or "").startswith(p) for p in MEDIA_PATH_PREFIXES):
        return None
    return raw


# THE COMPLETE ALLOWLIST. See docs/intel_sources.md for the audit behind each.
SOURCES = {
    "ncaa-d1-wvb": {
        "label": "NCAA.com",
        "category": "National",
        "url": "https://www.ncaa.com/news/volleyball-women/d1/rss.xml",
    },
}


def _text(el, tag):
    e = el.find(tag)
    return (e.text or "").strip() if e is not None and e.text else ""


def parse_rss(xml_text, source_key):
    # type: (str, str) -> Dict[str, Any]
    """Minimal items from an RSS body. Never raises on bad input."""
    src = SOURCES.get(source_key) or {}
    out = {"ok": False, "items": [], "error": ""}
    if not xml_text or not xml_text.strip():
        out["error"] = "the source returned nothing"
        return out
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        out["error"] = "the source did not return a readable feed"
        return out
    nodes = root.findall(".//item")
    if not nodes:
        out["error"] = "the feed contained no stories"
        return out
    seen = set()
    for it in nodes:
        title = _text(it, "title")
        link = _text(it, "link")
        # ⚠ A STORY WITHOUT A LINK IS NOT USABLE: the whole point is that
        # reading happens at the publisher, so an item we cannot send you to
        # is dropped rather than shown as a dead headline.
        if not title or not link:
            continue
        if not re.match(r"^https?://", link):
            continue
        # ⚠ DEDUPE BY CANONICAL LINK. A feed can repeat an item across
        # refreshes and sometimes within one document.
        canon = link.split("#")[0].split("?")[0].rstrip("/")
        if canon in seen:
            continue
        seen.add(canon)
        out["items"].append({
            "id": canon,
            "title": title,
            "link": link,
            "published": _text(it, "pubDate"),
            "category": _text(it, "category") or src.get("category") or "",
            "source": src.get("label") or source_key,
            "source_key": source_key,
            # ⚠ THE ENCLOSURE URL IS CDATA ELEMENT TEXT, NOT A url= ATTRIBUTE.
            # This feed's <enclosure> carries zero attributes, which is not
            # what RSS 2.0 specifies -- so `.get("url")` returns nothing and a
            # spec-shaped parser would find no media at all. Read the text,
            # and put it through the gate.
            "image": media_url(_text(it, "enclosure")),
            # NOTE: description and creator remain deliberately absent. The
            # description contains an <img> on every item and it is NOT used:
            # that is the publisher's article markup inside their blurb, and
            # lifting a picture out of it is scraping the description.
        })
    out["ok"] = bool(out["items"])
    if not out["ok"]:
        out["error"] = "the feed contained no usable stories"
    return out


def cache_path(source_key):
    return os.path.join(CACHE_DIR, "%s.json" % re.sub(r"[^\w.-]", "_", source_key))


def read_cache(source_key):
    p = cache_path(source_key)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return None


def write_cache(source_key, doc):
    try:
        if not os.path.isdir(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        with open(cache_path(source_key), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return True
    except OSError:
        return False


def fetch_source(source_key, urlopen=None, now=None, force=False):
    # type: (str, Any, Optional[float], bool) -> Dict[str, Any]
    """One allowlisted source, cache-first.

    ⚠ TAKES A KEY, NEVER A URL. That is what makes the allowlist real.
    ⚠ AND A FAILURE NEVER DESTROYS THE CACHE. If the source is down, the last
    good items are returned with `stale: True` and the reason -- an empty wire
    would be a worse lie than an old one that says it is old.
    """
    if source_key not in SOURCES:
        return {"ok": False, "items": [], "error": "unknown source", "stale": False}
    now = now if now is not None else datetime.datetime.utcnow().timestamp()
    cached = read_cache(source_key)
    if (cached and not force
            and (now - float(cached.get("fetched_at") or 0)) < MIN_REFRESH_SECONDS):
        return {"ok": True, "items": cached.get("items") or [], "error": "",
                "stale": False, "fetched_at": cached.get("fetched_at"),
                "from_cache": True}

    body, err = None, ""
    try:
        if urlopen is None:
            from urllib.request import Request, urlopen as _uo
            req = Request(SOURCES[source_key]["url"], headers={"User-Agent": UA})
            body = _uo(req, timeout=TIMEOUT).read().decode("utf-8", "replace")
        else:
            body = urlopen(SOURCES[source_key]["url"])
    except Exception as exc:                                   # noqa: BLE001
        err = "the source could not be reached (%s)" % type(exc).__name__

    if body is not None:
        parsed = parse_rss(body, source_key)
        if parsed["ok"]:
            doc = {"fetched_at": now, "items": parsed["items"]}
            write_cache(source_key, doc)
            return {"ok": True, "items": parsed["items"], "error": "",
                    "stale": False, "fetched_at": now, "from_cache": False}
        err = parsed["error"]

    if cached:
        return {"ok": True, "items": cached.get("items") or [], "error": err,
                "stale": True, "fetched_at": cached.get("fetched_at"),
                "from_cache": True}
    return {"ok": False, "items": [], "error": err or "no stories available",
            "stale": False, "fetched_at": None, "from_cache": False}


def all_sources(urlopen=None, now=None, force=False):
    """Every allowlisted source, merged. One source failing cannot empty the
    others: each is fetched and reported independently."""
    items, notes = [], []
    for key in SOURCES:
        r = fetch_source(key, urlopen=urlopen, now=now, force=force)
        items.extend(r["items"])
        notes.append({"source": SOURCES[key]["label"], "key": key,
                      "ok": r["ok"], "error": r["error"], "stale": r["stale"],
                      "fetched_at": r.get("fetched_at")})
    return {"items": items, "sources": notes,
            "checked_at": (now if now is not None
                           else datetime.datetime.utcnow().timestamp())}
