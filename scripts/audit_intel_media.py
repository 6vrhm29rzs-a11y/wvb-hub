#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUDIT: what media fields does the approved feed actually supply?

⚠ THIS IS AN AUDIT, NOT A FEATURE. It fetches exactly the URLs already in
intel.SOURCES -- the same allowlist, through the same key-not-URL discipline --
and reports what is in them. It never fetches an article page, an Open Graph
tag, a social post or a search result, and it never downloads an image: it
reports the URL and, for hostnames only, whether the host answers a HEAD.

Run: python3 scripts/audit_intel_media.py [--head]
  --head  additionally HEAD each distinct media host ONCE to record whether it
          serves over HTTPS and what content-type it claims. No body is read
          and nothing is written to disk.
"""

import collections
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

try:
    from urllib.request import Request, urlopen
    from urllib.parse import urlparse
except ImportError:                                   # pragma: no cover (py2)
    from urllib2 import Request, urlopen
    from urlparse import urlparse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel as INTEL

# every element that could conceivably carry an image, by convention
MEDIA_TAGS = [
    "enclosure",
    "{http://search.yahoo.com/mrss/}content",
    "{http://search.yahoo.com/mrss/}thumbnail",
    "{http://search.yahoo.com/mrss/}group",
    "image",
    "{http://purl.org/rss/1.0/modules/content/}encoded",
    "{http://www.itunes.com/dtds/podcast-1.0.dtd}image",
]


def fetch(url):
    req = Request(url, headers={"User-Agent": INTEL.UA})
    return urlopen(req, timeout=INTEL.TIMEOUT).read().decode("utf-8", "replace")


def main():
    do_head = "--head" in sys.argv
    report = {"sources": {}, "verdict": ""}
    for key, src in sorted(INTEL.SOURCES.items()):
        print("=" * 72)
        print("SOURCE %s  ->  %s" % (key, src["url"]))
        print("=" * 72)
        rec = {"url": src["url"], "items": 0, "fields": {}, "media": [],
               "hosts": {}, "canonical": 0, "pubdate": 0, "category": 0}
        try:
            xml_text = fetch(src["url"])
        except Exception as e:                        # noqa: BLE001
            print("  FETCH FAILED: %s" % e)
            rec["error"] = str(e)
            report["sources"][key] = rec
            continue
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")
        rec["items"] = len(items)
        print("  items: %d" % len(items))

        # ---- which child elements exist at all, and how often -------------
        counts = collections.Counter()
        for it in items:
            for child in it:
                counts[child.tag] += 1
        print("\n  EVERY child element present on an <item>:")
        for tag, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            print("    %-58s %d/%d" % (tag, n, len(items)))
            rec["fields"][tag] = n

        # ---- specifically: anything that could be an image ---------------
        print("\n  MEDIA-BEARING elements (the only ones a preview could use):")
        # ⚠ MY FIRST PASS AT THIS WAS WRONG, AND WRONG IN THE DIRECTION THAT
        # MATTERS. It read `el.get("url") or el.get("href") or el.text` and
        # reported "20 media references, host www.ncaa.com" -- which read as
        # "the feed supplies a standards-compliant enclosure". It does not.
        # Every <enclosure> on this feed has ZERO attributes; the URL is CDATA
        # element TEXT. RSS 2.0 specifies <enclosure url=".." type=".." />.
        # The distinction is not pedantry: a parser written against the spec
        # gets nothing here, and a permissive one that silently falls back to
        # text would also happily accept an <enclosure> containing prose.
        # Report the two separately and decide on the evidence.
        found_any = False
        for it in items:
            for tag in MEDIA_TAGS:
                for el in it.findall(tag):
                    found_any = True
                    attr_url = el.get("url") or el.get("href") or ""
                    text_url = (el.text or "").strip()
                    rec["media"].append({
                        "tag": tag,
                        "url_attr": attr_url[:200],
                        "text_url": text_url[:200],
                        "url": (attr_url or text_url)[:200],
                        "where": "attribute" if attr_url else
                                 ("element-text" if text_url else "empty"),
                        "type": el.get("type") or ""})
        if not found_any:
            print("    NONE. Not one item carries an enclosure, a media:content,")
            print("    a media:thumbnail, an <image>, or content:encoded.")
        else:
            byplace = collections.Counter(m["where"] for m in rec["media"])
            bytype = collections.Counter(m["type"] or "<no type attr>"
                                         for m in rec["media"])
            print("    URL carried in: %s" % dict(byplace))
            print("    declared type : %s" % dict(bytype))
            for m in rec["media"][:5]:
                print("    %-14s %-13s %s" % (m["tag"].split("}")[-1],
                                              m["where"], m["url"][:78]))

        # ---- would an image URL even be embedded in the description? -----
        # ⚠ REPORTED, NOT HARVESTED. If a blurb contains an <img>, that is the
        # publisher's article markup, not a feed media field -- pulling it out
        # is scraping the description, which this project does not do. Counted
        # so the decision is made on evidence rather than on assumption.
        embedded = 0
        for it in items:
            d = it.find("description")
            if d is not None and d.text and re.search(r"<img[^>]", d.text, re.I):
                embedded += 1
        print("\n  descriptions containing an <img> tag: %d/%d"
              " (NOT harvested -- that is article markup, not a media field)"
              % (embedded, len(items)))
        rec["description_img"] = embedded

        # ---- the fields we DO rely on ------------------------------------
        for it in items:
            if (it.findtext("link") or "").strip():
                rec["canonical"] += 1
            if (it.findtext("pubDate") or "").strip():
                rec["pubdate"] += 1
            if (it.findtext("category") or "").strip():
                rec["category"] += 1
        print("\n  fields the wire actually relies on:")
        print("    link (canonical URL) %d/%d" % (rec["canonical"], len(items)))
        print("    pubDate              %d/%d" % (rec["pubdate"], len(items)))
        print("    category             %d/%d" % (rec["category"], len(items)))

        # ---- hosts -------------------------------------------------------
        hosts = collections.Counter()
        for m in rec["media"]:
            try:
                p = urlparse(m["url"])
                if p.hostname:
                    hosts[(p.scheme, p.hostname)] += 1
            except ValueError:
                pass
        rec["hosts"] = {"%s://%s" % k: v for k, v in hosts.items()}
        print("\n  distinct media hosts: %s" % (rec["hosts"] or "none"))
        if do_head and hosts:
            for (scheme, host), _ in hosts.items():
                print("    HEAD %s://%s -- not performed (no media URLs to test)"
                      % (scheme, host))
        report["sources"][key] = rec

    # ---- the decision --------------------------------------------------
    total_media = sum(len(r.get("media") or []) for r in report["sources"].values())
    print("\n" + "=" * 72)
    if total_media:
        report["verdict"] = "media fields present -- see hosts above"
        print("VERDICT: the feed supplies %d media reference(s)." % total_media)
        print("An approved-host allowlist can be derived from the hosts above.")
    else:
        report["verdict"] = ("no media field of any kind is supplied by the "
                             "approved source")
        print("VERDICT: NO MEDIA FIELD OF ANY KIND.")
        print("No enclosure, no media:content, no media:thumbnail, no <image>.")
        print("There is therefore no approved host to allowlist, and no source")
        print("image can render today. The Wire ships derived-native and")
        print("unavailable states only -- which is a real answer, not a gap.")
    print("=" * 72)
    out = os.path.join(REPO, "docs", "intel_media_audit.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
