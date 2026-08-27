#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AFTER SHIPPING: check what is actually being SERVED, not what was built.

⚠ EVERY GATE IN THIS PROJECT UNTIL NOW RAN ON A LOCAL FILE. That is the right
place for most of them, but it cannot answer the one question that matters once
something is public: what do the bytes on the internet say? A page can be built
correctly, staged correctly, committed correctly and still be wrong at the URL
-- stale CDN object, a failed Pages build, a push that never landed, or an
artefact committed from a different tree than the source beside it.

So this fetches the published page and checks it on its own terms:
  1. the served redirect and the served dashboard agree with each other;
  2. the served dashboard carries no private content;
  3. how far behind the served copy is from the local commit, stated in
     minutes rather than asserted as fresh.

⚠ IT REPORTS LAG, IT DOES NOT FAIL ON IT. GitHub Pages takes minutes to build
and Fastly holds an object for ~10; a verifier that cried failure during a
normal deploy would be ignored within a week, which is worse than not having
one. Lag is printed. Private content is a hard failure.

Run: python3 scripts/verify_shipped.py [--url <base>]
Exit 0 = nothing private is public and the served pair is coherent.
"""

import hashlib
import os
import re
import sys

try:
    from urllib.request import Request, urlopen
except ImportError:                                        # pragma: no cover
    from urllib2 import Request, urlopen

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://6vrhm29rzs-a11y.github.io/wvb-hub/"
UA = "wvb-hub/0.1 (self-check of our own published page)"

# ⚠ THE SAME PROBES THE BUILD GATE USES, PLUS THE VALUES. This project has
# shipped a payload behind removed columns once; a word-search on markup would
# have passed that build. Each entry is (probe, what it would mean).
PRIVATE = [
    ("VolleyTalk", "a third-party poll we may not republish"),
    ("Massey Ratings", "a third-party rating we may not republish"),
    ('data-v="tv"', "the transcribed TV listings"),
    ("askform", "the private Digby chat"),
    ("/api/digby", "the private Digby endpoint"),
    ("intelbody", "the private Intel wire"),
    ("in-media", "Wire media markup"),
    ("in-lead", "Wire lead-story markup"),
    ("IN_MEDIA_HOSTS", "the media host allowlist"),
    ("inImageOK", "the client-side media gate"),
    ("_flysystem", "a feed media URL"),
    ("bwlist", "the private Ballot Workshop"),
    ("fr-new", "the private Film Room"),
]

FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def get(url):
    req = Request(url, headers={"User-Agent": UA})
    r = urlopen(req, timeout=30)
    return r.read().decode("utf-8", "replace"), dict(r.headers)


def main():
    base = BASE
    if "--url" in sys.argv:
        base = sys.argv[sys.argv.index("--url") + 1]
    base = base.rstrip("/") + "/"
    print("VERIFYING WHAT IS SERVED\n  %s\n" % base)

    try:
        idx, _ = get(base + "index.html")
    except Exception as e:                                 # noqa: BLE001
        print("  could not reach the published page: %s" % e)
        print("\n  NOT A PASS AND NOT A FAILURE OF THE PAGE -- state unknown.")
        return 2

    m = re.search(r"output/vb_dashboard\.html\?v=([0-9a-f]{6,})", idx)
    check("the served redirect names a dashboard build", bool(m),
          "no ?v= hash in the served index.html")
    if not m:
        return 1
    served_ver = m.group(1)
    print("     served redirect -> ?v=%s" % served_ver)

    try:
        dash, _ = get(base + "output/vb_dashboard.html?v=" + served_ver)
    except Exception as e:                                 # noqa: BLE001
        check("the served dashboard is reachable", False, str(e))
        return 1

    # 1. INTERNAL COHERENCE ------------------------------------------------
    print("\n1. THE SERVED PAIR AGREES WITH ITSELF")
    actual = hashlib.sha1(dash.encode("utf-8")).hexdigest()[:12]
    check("the served dashboard IS the build the redirect names",
          actual == served_ver,
          "redirect says %s, bytes hash to %s -- a stale CDN object or a "
          "half-deployed push" % (served_ver, actual))

    # 2. NOTHING PRIVATE IS PUBLIC ----------------------------------------
    print("\n2. NOTHING PRIVATE IS PUBLIC")
    leaks = [(p, why) for p, why in PRIVATE if p in dash]
    for p, why in leaks:
        print("     LEAK: %r -- %s" % (p, why))
    check("no private marker survives in the served bytes", not leaks,
          "%d leaked" % len(leaks))
    imgs = re.findall(r'<img[^>]+src="(https?://[^"]+)"', dash)
    media = [u for u in imgs if "/_flysystem/" in u]
    check("[-] not one feed media URL is served", not media, str(media[:1]))
    # ⚠ POSITIVE CONTROL. If the fetch returned an error page, every probe
    # above passes for the wrong reason.
    check("[+] ...over a real page that carries remote images at all",
          len(imgs) > 100, "%d images -- is this the dashboard?" % len(imgs))
    check("[+] ...and looks like the hub", "Volleyball" in dash and
          len(dash) > 500000, "%d bytes" % len(dash))

    # 3. HOW FAR BEHIND ----------------------------------------------------
    print("\n3. HOW FAR BEHIND THE SERVED COPY IS (reported, not failed)")
    stamp = re.search(r"built (\d{4}-\d{2}-\d{2} [\d:]+ [AP]M PT)", dash)
    print("     served build stamp : %s" % (stamp.group(1) if stamp else "not found"))
    local = os.path.join(REPO, "output", "vb_dashboard.html")
    if os.path.exists(local):
        lh = hashlib.sha1(open(local, encoding="utf-8").read()
                          .encode("utf-8")).hexdigest()[:12]
        print("     local artefact     : %s" % lh)
        if lh == served_ver:
            print("     -> the served copy IS the local artefact")
        else:
            print("     -> the served copy is a DIFFERENT build from the local"
                  " one. Normal for a few minutes after a push (Pages builds,"
                  " then Fastly holds ~10 min); a problem if it persists.")

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("WHAT IS SERVED IS CLEAN AND COHERENT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
