#!/usr/bin/env python3
"""Guards for the school-published TV/streaming layer (2026-09-04).

Cody: "make sure streaming or live tv viewing information is listed for
each game." The invariants: a network label is the school's own words or
nothing (generic action labels never count); binding is R8-strict
(opponent-anchored, never date alone); the transcribed forum layer stays
private while the school layer ships on both builds."""
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    import crawl_tv as CT

    print("1. A NETWORK LABEL IS THE SCHOOL'S OWN WORDS OR NOTHING")
    check("media.tv wins when stated",
          CT._network_from({"tv": "FS1", "video": {"title": "ESPN+"}}) == "FS1")
    check("video.title supplies the streaming network",
          CT._network_from({"tv": "", "video": {"title": "SEC Network+"}})
          == "SEC Network+")
    for g in ("Watch", "watch", "Live", "Live Stream",
              "Video for Volleyball vs X", "Watch Live"):
        check("[NEG] generic label %r is not a network" % g,
              CT._network_from({"tv": "", "video": {"title": g}}) is None)
    check("no media -> None, never invented", CT._network_from({}) is None)

    print("\n2. THE CRAWLED FILE HOLDS THE SAME RULE")
    p = os.path.join(REPO, "data", "raw", "2026", "tv_auto.json")
    if os.path.exists(p):
        d = json.load(open(p))
        bad = []
        for k, v in d.items():
            if k.startswith("_") or not isinstance(v, dict):
                continue
            for e in (v.get("events") or []):
                if (e.get("network") or "").lower() in (
                        "watch", "live", "video", "live stream",
                        "live video", "stream", "watch live"):
                    bad.append((k, e.get("network")))
        check("no generic label survives in the crawled file",
              not bad, bad[:4])
        check("every entry states its parse status",
              all(isinstance(v, dict) and v.get("status")
                  for k, v in d.items()
                  if not k.startswith("_")), "")
    else:
        print("    (no tv_auto.json -- crawl has not run in this checkout)")

    print("\n3. THE JOIN IS OPPONENT-ANCHORED, NEVER DATE ALONE")
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()
    i = src.find("THE SCHOOL-PUBLISHED LAYER")
    seg = src[i:i + 4000]
    check("the binder keys on (team, opponent) before any date test",
          "_norm(_e.get(\"opponent\"))" in seg and "_byteam" in seg)
    check("the date is a WINDOW on an opponent match, not the key",
          "abs((_ed - _fd).days) > 1" in seg)

    print("\n4. PRIVATE VS PUBLIC, BY LAYER")
    check("tv() (the forum transcription) is public-gated",
          re.search(r"def tv\(\)[^\n]*:\s*\n\s*if PUBLIC:\s*\n\s*return \[\]",
                    src) is not None)
    check("tv_index no longer blanket-returns {} on public "
          "(the school layer ships)",
          "THE TRANSCRIBED LAYER IS PRIVATE" in src and
          re.search(r"def tv_index\(\):(?:(?!def )[\s\S]){0,2400}if PUBLIC:\s*\n\s*return \{\}",
                    src) is None)
    check("school entries carry their src label",
          '"src": "school"' in src)

    print("\n5. LIVE AND FINAL LANES SORT BY WHO IS IN THEM")
    check("the scoreboard's live/final lanes use the rank key",
          "st === 'live' || st === 'final'" in src and "bestRank" in src)
    check("[NEG] the rank key never falls through to the clock",
          "tMinutes" not in src[src.find("const bestRank"):
                                src.find("const bestRank") + 400])
    check("upcoming keeps its time grouping",
          "in_.length >= 12" in src)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL TV-LAYER GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
