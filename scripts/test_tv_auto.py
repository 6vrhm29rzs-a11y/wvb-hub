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
    seg = src[i:i + 9000]
    check("the binder keys on (team, opponent) before any date test",
          "(_tnorm(_school), _tnorm(_o))" in seg and "_byteam" in seg)
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

    print("\n6. LINEAR VS STREAMING IS A CLASSIFIED FACT (P0.3)")
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import build_hub as BH
    check("ESPN+ classifies as streaming", BH.tv_kind("ESPN+") == "streaming")
    check("FS1 classifies as linear", BH.tv_kind("FS1") == "linear")
    check("SEC Network+ is streaming; SEC Network is linear",
          BH.tv_kind("SEC Network+") == "streaming"
          and BH.tv_kind("SEC Network") == "linear")
    check("[NEG] an unknown network classifies as NOTHING, never guessed",
          BH.tv_kind("Podunk Sports Net") is None)
    check("the Watch-Now reason is linear-only and says LINEAR",
          "m.tvk === 'linear'" in src and "'linear TV'" in src)
    check("[NEG] the old 'national TV' reason wording is gone from the "
          "reason builder",
          "out.push(['tv', 'national TV'" not in src)
    check("streaming earns no Watch-Now priority weight",
          "m.tvk === 'linear') w += 25" in src)
    check("the watch line labels the kind",
          "STREAMING \\u00b7" in src and "LINEAR TV \\u00b7" in src)


    print("\n7. WMT CARDS, AND EVERY MATCH SAYS WHERE TO WATCH OR 'NONE FOUND'")
    card = ('<div class="schedule-event" data-aos="x"><span class="schedule-event-date__day">Sep 27</span>'
            '<span class="schedule-event-item-team__rank">#4</span>'
            '<strong class="schedule-event-item-team__name">Michigan State</strong>'
            '<a href="https://www.foxsports.com/live/btn" class="schedule-event__tv-link">'
            '<span>Watch | BTN</span><span class="sr-only"> Opens in a new window </span></a></div>'
            '<div class="schedule-event" data-aos="x"><span class="schedule-event-date__day">Oct 1</span>'
            '<strong class="schedule-event-item-team__name">Nebraska</strong></div>')
    ev = CT.parse_wmt_cards(card) or []
    check("a WMT card yields its own network and link",
          ev and ev[0]["network"] == "BTN" and ev[0]["date"] == "2026-09-27"
          and "foxsports" in (ev[0]["watch_url"] or ""), ev)
    check("the opponent is the name, not the rank chip", ev and ev[0]["opponent"] == "Michigan State", ev)
    check("[NEG] a card with no watch link contributes nothing (never borrowed from its neighbour)",
          len(ev) == 1, ev)
    check("[NEG] an unknown label keeps the link but names no network",
          (CT.parse_wmt_cards(card.replace("Watch | BTN", "Watch | Mystery Net")) or [{}])[0].get("network") is None)
    src = open(os.path.join(REPO, "scripts", "build_hub.py"), encoding="utf-8").read()
    check("one wording constant for 'none found'", src.count("NOTV_NOTE = (") == 1)
    check("the none-found note says unknown, never 'not televised'",
          "never \\u201cnot televised" in src)
    check("Scores rows say 'no TV listing found' for a match not yet final",
          "else if (st !== 'final') _mbits.push('<span class=\"notv\"" in src)
    check("the Schedule table has a Watch column filled by watch_cell",
          ">Watch</th>" in src and "watch_cell(r)" in src)
    check("[NEG] a Schedule row with no listing is never blank",
          'none found</span>' in src)
    check("an upcoming row with no clock says Time TBA",
          "'Time TBA'" in src)
    import crawl_tv as _C
    check("a parser upgrade refetches schools that found nothing", _C.PARSER_V >= 3)
    lr = open(os.path.join(REPO, "scripts", "local_refresh.py"), encoding="utf-8").read()
    check("broadcast listings are re-read by the local refresh (bounded per cycle)",
          '"scripts/crawl_tv.py", "--limit=' in lr)


    print("\n8. ANOTHER SPORT'S BROADCAST NEVER LANDS ON A VOLLEYBALL MATCH")
    import json as _j
    def _pl(sport):
        return ('<script type="application/json" id="__NUXT_DATA__">' +
                _j.dumps([{"a": 1}, {"start_date": 2, "opponent": 3, "media": 4, "sport": 5},
                          "2026-09-26T00:00:00", {"title": 6}, {"tv": 7},
                          sport, "Cincinnati", "ESPN2"]) + '</script>')
    fb = CT.parse_nuxt(_pl({"title": 8, "shortname": 9}).replace('"ESPN2"]', '"ESPN2", "Football", "football"]'))
    vb = CT.parse_nuxt(_pl({"title": 8, "shortname": 9}).replace('"ESPN2"]', '"ESPN2", "Volleyball", "wvball"]'))
    check("[NEG] a football event on ESPN2 is dropped", not fb, fb)
    check("the volleyball event with the same shape is kept",
          vb and vb[0]["network"] == "ESPN2" and vb[0]["date"] == "2026-09-26", vb)
    mvb = CT.parse_nuxt(_pl({"title": 8}).replace('"ESPN2"]', '"ESPN2", "Men\'s Volleyball"]'))
    check("[NEG] men's volleyball is not women's volleyball", not mvb, mvb)

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
