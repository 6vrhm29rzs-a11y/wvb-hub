#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for The Wire: media states, story families, and public stripping.

⚠ THE RISK HERE IS NOT A WRONG NUMBER, IT IS A BORROWED PICTURE. Three things
could go wrong that no other suite would notice: an image could be loaded from
a host nobody audited; a hub-made graphic could be mistaken for a photograph of
the match it describes; and a private media URL could reach the public build.
Each has its own section below.

Python 3.9 target. Run: python3 scripts/test_wire.py
"""

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel as INTEL

FAILS = []


def check(label, ok, detail=""):
    print("  %-68s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def code_only(s):
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"(?m)^\s*#(?!\w).*$", " ", s)
    return s


def main():
    print("THE WIRE -- MEDIA, FAMILIES AND STRIPPING\n")
    priv = os.path.join(REPO, "Cody", "START-HERE.html")
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    S = open(os.path.join(REPO, "scripts", "build_hub.py"), encoding="utf-8").read()
    C = code_only(S)

    # ── 1. THE MEDIA GATE ───────────────────────────────────────────────
    print("1. THE MEDIA URL GATE (intel.media_url)")
    OK = ("https://www.ncaa.com/_flysystem/public-s3/styles/large_16x9/"
          "public-s3/images/2026-08/x.jpg?h=a1e1a043&itok=4iZE2YlO")
    cases = [
        ("an approved feed URL", OK, True),
        ("plain http", OK.replace("https://", "http://"), False),
        ("protocol-relative", "//www.ncaa.com/_flysystem/x.jpg", False),
        ("a disallowed host", "https://evil.example/_flysystem/x.jpg", False),
        ("a lookalike host", "https://www.ncaa.com.evil.example/_flysystem/x.jpg", False),
        # ⚠ THIS ONE IS THE REASON THE GATE REFUSES USERINFO. It parses with
        # hostname `evil.example`, and a reader scanning the string sees
        # "www.ncaa.com" at the front.
        ("credentials smuggling a host", "https://www.ncaa.com@evil.example/_flysystem/x.jpg", False),
        ("an explicit port", "https://www.ncaa.com:8443/_flysystem/x.jpg", False),
        ("an approved host on the wrong path",
         "https://www.ncaa.com/news/whatever.jpg", False),
        ("a malformed string", "not a url", False),
        ("a javascript: URL", "javascript:alert(1)", False),
        ("a data: URL", "data:image/png;base64,AAAA", False),
        ("whitespace injection", "https://www.ncaa.com/_flysystem/x.jpg\n<script>", False),
        ("empty", "", False),
        ("None", None, False),
        ("a non-string", 42, False),
    ]
    for label, raw, want in cases:
        got = INTEL.media_url(raw) is not None
        check("%-38s -> %s" % (label, "accepted" if want else "refused"),
              got == want, "got %s" % got)
    check("[+] the approved case really does come back unchanged",
          INTEL.media_url(OK) == OK)
    # ⚠ THE GATE MUST NOT REPAIR ITS INPUT.
    check("[-] the gate never upgrades http to https",
          INTEL.media_url(OK.replace("https://", "http://")) is None,
          "a validator that fixes its input is a validator that accepts it")

    print("\n1b. THE ALLOWLIST IS THE AUDIT")
    check("exactly one media host is approved",
          tuple(INTEL.MEDIA_HOSTS) == ("www.ncaa.com",), str(INTEL.MEDIA_HOSTS))
    check("...and it is a path-scoped allowlist, not a whole host",
          tuple(INTEL.MEDIA_PATH_PREFIXES) == ("/_flysystem/",),
          str(INTEL.MEDIA_PATH_PREFIXES))
    check("the source allowlist was NOT widened for media",
          set(INTEL.SOURCES) == {"ncaa-d1-wvb"}, str(set(INTEL.SOURCES)))
    check("the audit is written down and re-runnable",
          os.path.exists(os.path.join(REPO, "scripts", "audit_intel_media.py")) and
          "MEDIA AUDIT" in open(os.path.join(REPO, "docs", "intel_sources.md"),
                                encoding="utf-8").read())

    print("\n1c. THE ENCLOSURE IS READ FROM ELEMENT TEXT, NOT AN ATTRIBUTE")
    # ⚠ THE MEASURED SHAPE OF THIS FEED: <enclosure> with ZERO attributes and
    # the URL as CDATA. A spec-shaped parser finds nothing here.
    xml = ('<rss><channel><item><title>T</title>'
           '<link>https://www.ncaa.com/news/a</link>'
           '<enclosure><![CDATA[%s]]></enclosure>'
           '</item></channel></rss>' % OK)
    got = INTEL.parse_rss(xml, "ncaa-d1-wvb")
    check("an attribute-less enclosure still yields an image",
          got["ok"] and got["items"][0].get("image") == OK,
          str(got["items"][:1]))
    # and a bad one is dropped rather than passed through
    xml_bad = xml.replace(OK, "https://evil.example/_flysystem/x.jpg")
    got_bad = INTEL.parse_rss(xml_bad, "ncaa-d1-wvb")
    check("[-] a disallowed host becomes no image, and the story survives",
          got_bad["ok"] and got_bad["items"][0].get("image") is None)
    check("[+] ...and the story itself is still usable",
          got_bad["items"][0]["title"] == "T")
    # the description's <img> is NOT harvested
    xml_desc = ('<rss><channel><item><title>T</title>'
                '<link>https://www.ncaa.com/news/a</link>'
                '<description><![CDATA[<img src="%s"> blurb]]></description>'
                '</item></channel></rss>' % OK)
    d = INTEL.parse_rss(xml_desc, "ncaa-d1-wvb")
    check("[-] an <img> inside the description is NOT harvested",
          d["ok"] and not d["items"][0].get("image"),
          "that is article markup in a blurb, not a media field")
    check("[-] ...and the blurb itself is still discarded",
          "description" not in d["items"][0])

    # ── 2. THE PAGE RE-CHECKS WHAT THE SERVER APPROVED ──────────────────
    print("\n2. THE PAGE DOES NOT TRUST THE PAYLOAD")
    check("a client-side gate exists", "function inImageOK(" in C)
    for frag in ("protocol !== 'https:'", "p.username || p.password || p.port",
                 "IN_MEDIA_HOSTS.indexOf", "'/_flysystem/'"):
        check("  ...it checks %s" % frag, frag in C)
    check("the host list is EMITTED from intel.py, not retyped",
          "from intel import MEDIA_HOSTS as INTEL_MEDIA_HOSTS" in S and
          '{{INTEL_MEDIA_HOSTS_JSON}}' in S)

    # ── 3. THE THREE STATES ─────────────────────────────────────────────
    print("\n3. THREE NAMED MEDIA STATES")
    for st in ("source-provided", "derived-native", "unavailable"):
        check("the state '%s' exists" % st, "'%s'" % st in C)
    check("an unavailable story gets a designed panel, not a grey box",
          "No picture with this story" in C and "in-nomedia" in C)
    check("a load failure falls back in place", "function inImgFail(" in C and
          "The publisher&rsquo;s image did not load" in C)
    # ⚠ THE PAINT BUG. A geometry assertion cannot see this one.
    check("[-] the load hook that forces the repaint is present",
          "function inImgShown(" in C and 'onload="inImgShown(this)"' in C,
          "without it a decoded image can sit in an unpainted box")
    check("[-] ...and images already complete are swept",
          "function inSweepImages(" in C and "im.complete && im.naturalWidth" in C,
          "onload never fires for a file that finished before the handler bound")
    check("[-] no lazy/async deferral on wire images",
          'loading="lazy"' not in C.split("function inMediaHTML")[1][:1200],
          "measured: deferred inside a hidden section, the paint is never scheduled")
    check("the container reserves space so nothing shifts",
          "padding-top:56.25%" in S)

    print("\n3b. A BORROWED IMAGE IS NEVER OURS")
    check("the source is credited on the picture itself", "in-credit" in C and
          "Image: NCAA.com" in C)
    check("the original link is always present", "Read at ' + esc(it.source)" in C)
    check("[-] nothing is downloaded or rehosted",
          "urlretrieve" not in S and "shutil.copyfileobj" not in S)

    # ── 4. TYING A STORY TO A MATCH ─────────────────────────────────────
    print("\n4. A MOMENT IS ONLY ATTACHED WHEN IT IS UNAMBIGUOUS")
    check("the tie requires exactly two named teams",
          "if (teams.length !== 2) return null;" in C)
    check("[-] ...and exactly one candidate match", "cand.length === 1" in C,
          "two candidates means we do not know which, so no picture")
    check("[-] ...and never a future fixture", "m.d > today" in C)

    # ── 5. STORY FAMILIES ───────────────────────────────────────────────
    print("\n5. STORY FAMILIES GROUP, THEY DO NOT EDIT")
    check("families are computed", "function inFamilies(" in C)
    check("same publisher only", "jt.source_key !== it.source_key" in C)
    check("inside a stated time window", "IN_FAMILY_HOURS" in C)
    check("above a stated similarity", "IN_FAMILY_J" in C)
    check("[-] every original link survives", "function inAlso(" in C and
          "fam.slice(1).map" in C)
    check("[-] ...labelled with its format", "function inFormat(" in C)
    check("[-] and no canonical version is invented",
          "fam.sort((x, y) => inTime(x) - inTime(y))" in C,
          "oldest leads -- a stated rule, not a judgement about which is best")
    # a real similarity check, ported
    def toks(t):
        stop = set(('the a an and or of in on at to for with vs v is are was were '
                    'as by from its it this that day final').split())
        return [w for w in re.sub(r"[^a-z0-9 ]+", " ", t.lower()).split()
                if len(w) > 2 and w not in stop]

    def jac(a, b):
        A, B = set(a), set(b)
        return len(A & B) / float(len(A | B)) if A and B else 0.0
    same = jac(toks("Top 5 returning middle blockers in college volleyball for 2026"),
               toks("Top 5 returning middle blockers in college volleyball for 2026"))
    diff = jac(toks("Kentucky, Louisville open AVCA First Serve with top-10 wins"),
               toks("Top 5 returning setters for the 2026 women's volleyball season"))
    check("identical headlines group (J=%.2f >= 0.60)" % same, same >= 0.60)
    check("[NEG] unrelated headlines do NOT group (J=%.2f < 0.60)" % diff,
          diff < 0.60, "if this fails the grouping is merging real stories")

    # ── 6. PUBLIC STRIPPING ─────────────────────────────────────────────
    print("\n6. NOTHING PRIVATE REACHES THE PUBLIC BUILD")
    if not os.path.exists(pub):
        check("the public build exists", False, "run build_hub.py --public")
    else:
        h = open(pub, encoding="utf-8").read()
        for probe in ("_flysystem", "IN_MEDIA_HOSTS", "inImageOK", "inMediaHTML",
                      "in-media", "in-lead", "in-credit", "inFamilies",
                      "in-nomedia", "inImgShown", "intelbody", "IN_FAMILY_J"):
            check("public: no %r" % probe, probe not in h,
                  "%d occurrences" % h.count(probe))
        # ⚠ ASSERT THE VALUE, NOT THE WORD. This project shipped 151 Massey
        # ranks inside a payload behind removed columns once.
        imgs = re.findall(r'<img[^>]+src="(https?://[^"]+)"', h)
        media = [u for u in imgs if "/_flysystem/" in u]
        check("[-] public: not one feed media URL is present", not media,
              str(media[:1]))
        check("[+] ...over a page that does carry remote images at all",
              len(imgs) > 100, "%d" % len(imgs),)
        check("the host allowlist is emitted EMPTY in public",
              'const IN_MEDIA_HOSTS = []' in h or "IN_MEDIA_HOSTS" not in h)
        # the Match Moment IS ours and SHOULD survive
        check("[+] the Match Moment survives -- it is our own data",
              "momentHTML" in h and ".mm-sc{" in h)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL WIRE GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
