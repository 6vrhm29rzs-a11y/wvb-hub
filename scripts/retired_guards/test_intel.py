#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the private Intel Desk.

⚠ WHAT IS AT STAKE. This is the only feature that reaches the open internet on
Cody's behalf and stores what he has been reading. Two boundaries matter:
the SOURCE list (nothing else may be fetched) and the DATA (headlines, links
and read state never enter git, the public build, or any computation).

Python 3.9 target. Run: python3 scripts/test_intel.py
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
FIX = os.path.join(REPO, "tests", "fixtures", "intel")
sys.path.insert(0, SCRIPTS)
import intel as IN  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def fx(name):
    return io.open(os.path.join(FIX, name), encoding="utf-8").read()


def main():
    print("INTEL DESK GUARDS\n")
    src = io.open(os.path.join(SCRIPTS, "build_hub.py"), encoding="utf-8").read()

    print("1. THE SOURCE LIST IS THE BOUNDARY")
    check("there is exactly one source today", len(IN.SOURCES) == 1,
          str(list(IN.SOURCES)))
    url = IN.SOURCES["ncaa-d1-wvb"]["url"]
    check("...and it is the NCAA's own D-I women's volleyball feed",
          url == "https://www.ncaa.com/news/volleyball-women/d1/rss.xml", url)
    # ⚠ fetch_source TAKES A KEY. If it took a URL the allowlist would be
    # decoration -- anything could ask it to fetch anything.
    fn = src if False else io.open(os.path.join(SCRIPTS, "intel.py"),
                                   encoding="utf-8").read()
    check("fetch_source takes a KEY, never a URL",
          "def fetch_source(source_key" in fn)
    check("...and refuses a key it does not know",
          IN.fetch_source("not-a-source")["ok"] is False)
    # only allowlisted hosts appear at all
    hosts = set(re.findall(r"https?://([a-z0-9.\-]+)", fn))
    check("no host outside the allowlist is named in the code",
          hosts <= {"www.ncaa.com"}, str(sorted(hosts)))
    # ⚠ AND THE FORBIDDEN ONES ARE NAMED, so a future edit is obvious.
    for bad in ("volleytalk", "twitter", "x.com", "facebook", "instagram",
                "reddit", "avca"):
        check("[-] never reaches %-12s" % bad, bad not in fn.lower())
    check("the audit document exists",
          os.path.exists(os.path.join(REPO, "docs", "intel_sources.md")))

    print("\n2. ONLY FOUR FIELDS SURVIVE")
    r = IN.parse_rss(fx("ncaa_normal.xml"), "ncaa-d1-wvb")
    check("the real feed parses", r["ok"] and len(r["items"]) == 20,
          "%d items" % len(r["items"]))
    keys = set(r["items"][0])
    check("an item carries title, link, time, category, source",
          {"title", "link", "published", "category", "source"} <= keys)
    # ⚠ THE PUBLISHER'S OWN WRITING IS NOT KEPT. That is the principle, and it
    # is unchanged. What changed -- deliberately, through the media audit of
    # 2026-08-25 -- is that a media URL is now retained.
    #
    # ⚠ A URL IS A REFERENCE; AN ARTICLE IS CONTENT. This project already drew
    # exactly that line for player headshots: "URLS ONLY, NEVER THE FILES --
    # storing a reference is a different act from republishing the file." The
    # blurb, the byline and the article text remain absent, because showing
    # those instead of the publisher's page is the thing worth refusing.
    for gone in ("description", "summary", "content", "enclosure",
                 "thumbnail", "creator", "author"):
        check("[-] %-11s is never stored" % gone, gone not in keys)
    check("[+] a media URL IS retained, by audit", "image" in keys,
          "docs/intel_sources.md records the decision")
    check("[-] ...and only ever through the gate",
          all(IN.media_url(i.get("image")) == i.get("image")
              for i in r["items"] if i.get("image")),
          "an item's image must be exactly what media_url() would allow")
    check("[-] ...and nothing is downloaded",
          "urlretrieve" not in open(
              os.path.join(REPO, "scripts", "intel.py"), encoding="utf-8").read())
    check("[+] the feed really does carry a description to discard",
          "<description>" in fx("ncaa_normal.xml"))
    check("no stored value contains article prose",
          all(len(i["title"]) < 300 for i in r["items"]))

    print("\n3. FEED FAILURES ARE HANDLED, NOT CRASHED")
    for name, want_ok, why in (
            ("ncaa_malformed.xml", False, "readable feed"),
            ("ncaa_empty.xml", False, "no stories"),
            ("ncaa_dupe.xml", True, "")):
        p = IN.parse_rss(fx(name), "ncaa-d1-wvb")
        check("%-20s -> ok=%s" % (name, want_ok), p["ok"] == want_ok,
              str(p["error"])[:40])
        if why:
            check("   ...and says why", why in p["error"], p["error"])
    d = IN.parse_rss(fx("ncaa_dupe.xml"), "ncaa-d1-wvb")
    # ⚠ DEDUPE BY CANONICAL LINK: the same story with a tracking query is the
    # same story, and an item with no link cannot be opened so it is dropped.
    check("a duplicate link collapses to one story", len(d["items"]) == 1,
          str([i["link"] for i in d["items"]]))
    check("...and an item with no link is dropped",
          all(i["link"] for i in d["items"]))
    check("parse never raises on rubbish",
          IN.parse_rss("<<<not xml", "ncaa-d1-wvb")["ok"] is False)
    check("...or on nothing at all", IN.parse_rss("", "ncaa-d1-wvb")["ok"] is False)

    print("\n4. A FAILED FETCH NEVER DESTROYS THE CACHE")
    tmp = tempfile.mkdtemp(prefix="wvb-intel-")
    old_dir = IN.CACHE_DIR
    IN.CACHE_DIR = tmp
    try:
        good = lambda u: fx("ncaa_normal.xml")            # noqa: E731
        boom = lambda u: (_ for _ in ()).throw(IOError("down"))  # noqa: E731
        a = IN.fetch_source("ncaa-d1-wvb", urlopen=good, now=1000.0, force=True)
        check("a good fetch fills the cache", a["ok"] and len(a["items"]) == 20)
        b = IN.fetch_source("ncaa-d1-wvb", urlopen=boom, now=99999.0, force=True)
        check("a dead source still returns the last good stories",
              b["ok"] and len(b["items"]) == 20, str(b)[:60])
        check("...marked stale, with a reason", b["stale"] and b["error"])
        c = IN.fetch_source("ncaa-d1-wvb", urlopen=lambda u: fx("ncaa_malformed.xml"),
                            now=99999.0, force=True)
        check("a malformed feed also leaves the cache intact",
              c["ok"] and len(c["items"]) == 20 and c["stale"])
        # ⚠ AND A COLD START WITH A DEAD SOURCE IS HONEST, NOT EMPTY-AND-SILENT
        IN.CACHE_DIR = tempfile.mkdtemp(prefix="wvb-intel2-")
        e = IN.fetch_source("ncaa-d1-wvb", urlopen=boom, now=1.0, force=True)
        check("no cache and no source says so", not e["ok"] and e["error"])
    finally:
        IN.CACHE_DIR = old_dir

    print("\n5. THE CACHE IS NEVER COMMITTED")
    gi = io.open(os.path.join(REPO, ".gitignore"), encoding="utf-8").read()
    check(".intel_cache/ is gitignored", ".intel_cache/" in gi)
    # ⚠ THE FRESH-CHECKOUT HARNESS EXTRACTS A TREE WITH NO `.git`, so every
    # git command here exits non-zero and these checks failed against a
    # perfectly correct build. The .gitignore assertion above still runs
    # everywhere; the two that need a repository say so when there is none.
    if not os.path.isdir(os.path.join(REPO, ".git")):
        print("     (no .git here -- the two repository checks need one)")
    else:
        out = subprocess.run(["git", "check-ignore", "-q",
                              ".intel_cache/x.json"], cwd=REPO)
        check("...and git agrees", out.returncode == 0)
        tracked = subprocess.run(["git", "ls-files", ".intel_cache"], cwd=REPO,
                                 stdout=subprocess.PIPE,
                                 universal_newlines=True)
        check("[-] nothing under it is tracked", not tracked.stdout.strip(),
              tracked.stdout[:60])

    print("\n6. INTEL REACHES NOTHING THAT COMPUTES")
    for mod in ("rating_2025.py", "digby_top25.py", "project_2026.py",
                "project_field.py", "simulate_season_2026.py",
                "build_rankings_board.py", "ballots.py", "digby.py",
                "digby_chat.py", "snapshot_rankings.py", "weekly.py",
                "fixture_disposition.py", "build_hub.py"):
        p2 = os.path.join(SCRIPTS, mod)
        if not os.path.exists(p2):
            continue
        body = io.open(p2, encoding="utf-8").read()
        hit = [t for t in ("import intel", "intel.all_sources",
                           "intel.fetch_source", "IN_ITEMS =") if t in body]
        # build_hub renders the desk, so it may hold IN_ITEMS -- but it must
        # never import the fetcher.
        hit = [h for h in hit if not (mod == "build_hub.py" and h == "IN_ITEMS =")]
        check("[-] %-26s never fetches intel" % mod, not hit, str(hit))

    print("\n7. THE PUBLIC BUILD HAS NONE OF IT")
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if not os.path.exists(pub):
        print("  (no public build -- skipping)")
    else:
        ph = io.open(pub, encoding="utf-8").read()
        for sym in ("IN_KEY", "wvb.intel", "/api/intel", "inFetch", "inRender",
                    "inMatch", 'id="v-intel"', "INTEL-", "rss.xml",
                    "Intel Desk", "intelbody"):
            check("public: no %r" % sym, sym not in ph)
        css = re.findall(r"\.in-[a-z-]+\s*[{,]", ph)
        check("public: not one .in-* rule", not css, str(css[:4]))
        priv = os.path.join(REPO, "Cody", "START-HERE.html")
        if os.path.exists(priv):
            pv = io.open(priv, encoding="utf-8").read()
            have = sum(1 for x in ("IN_KEY", 'id="v-intel"', ".in-row{",
                                   "/api/intel") if x in pv)
            check("[+] the PRIVATE page carries every layer", have == 4,
                  "%d of 4" % have)

    print("\n8. THE BROWSER NEVER FETCHES A FEED ITSELF")
    m = re.search(r"/\* INTEL-JS-BEGIN \*/.*?/\* INTEL-JS-END \*/", src, re.S)
    js = m.group(0) if m else ""
    check("[+] the intel script was found", bool(js))
    check("it calls only the local endpoint",
          "fetch('/api/intel'" in js)
    check("[-] and no remote URL", not re.search(r"fetch\(['\"]https?://", js))
    check("[-] no feed host appears in the page script",
          "ncaa.com/news" not in js and "rss.xml" not in js)
    # the server endpoint takes no url
    ls = io.open(os.path.join(SCRIPTS, "live_server.py"), encoding="utf-8").read()
    seg = ls[ls.index('"/api/intel"'):]
    seg = seg[:seg.index("if self.path")]
    check("[-] the endpoint accepts no url parameter", '"url"' not in seg
          and "get('url'" not in seg)
    check("...only an optional force flag", 'q.get("force")' in seg)
    check("...and local requests only", "_is_local()" in seg)

    print("\n9. MATCHING IS CONSERVATIVE")
    # ⚠ THE REAL FALSE MATCH THIS CAUGHT: "SMU sweeps Texas A&M" was filed
    # under Texas, because "Texas A&M" normalises to "texas a m" and contains
    # " texas ". A longer team name now wins and the short one is dropped.
    check("a longer team name shadows a shorter one", "shadowed" in src)
    check("...explained where it happens", "Texas A&M" in src)
    check("names are padded so a substring cannot match",
          "' ' + String(t || '')" in src)
    check("[-] no fuzzy or nickname matching exists",
          "levenshtein" not in src.lower() and "difflib" not in src.lower())

    print("\n10. A NOTE IS PREFILLED, NEVER CREATED")
    check("the handoff fills title and link",
          "set('frtitle', it.title)" in js and "set('frurl', it.link)" in js)
    check("[-] ...and leaves the takeaway empty",
          "set('frnote', '')" in js)
    check("[-] it never saves a note itself", "frAdd(" not in js)
    check("...and says what is needed",
          "Add your own takeaway, then Save." in js)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL INTEL DESK GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
