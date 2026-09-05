#!/usr/bin/env python3
"""The capsule rail (2026-09-05, the brief Cody forwarded): a capsule
shows WHOLE or not at all; nothing marches; every hidden match is one
explicit action away."""
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def main():
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()
    i = src.find("#livetick{display:flex")   # the MAIN rule, not the phone override
    rail = src[i:i + 1200]
    check("the rail does not scroll sideways",
          "overflow-x:auto" not in rail and "overflow:hidden" in rail)
    check("the rail is height-bounded (<=56px desktop)",
          re.search(r"#livetick\{[^}]*max-height:56px", src) is not None)
    check("phone: one capsule, <=72px, All-live pulled right",
          "#livetick{max-height:72px}" in src and
          ":nth-of-type(n+2){display:none}" in src)
    check("capsules never shrink (flex:0 0 auto -- names never squeeze)",
          re.search(r"#livetick \.tkm\{flex:0 0 auto", src) is not None)
    check("the fit pass drops WHOLE capsules from the end",
          "caps[caps.length - 1].remove()" in src)
    check("...and never the first capsule",
          "caps.length <= 1) break" in src)
    check("the shown label reports what SURVIVED the fit",
          "reports what SURVIVED" in src and ".tkshown" in src)
    check("All-live renders whenever more than one match is live",
          "live.length > 1" in src.split("data-alllive")[0][-400:])
    check("the quiet state carries a View schedule action",
          "data-viewsched" in src and
          "View schedule" in src)
    # the dot's pulse is the ONE allowed animation; anything else moving
    # on the rail (translate/scroll/marquee) is the marching tape back
    check("[NEG] no marching animation on the rail",
          "marquee" not in rail and "translate" not in rail and
          "animation" not in re.sub(r"animation:tkpulse[^;}]*", "", rail))
    print("\n  ONE LIVE SNAPSHOT, ONE RULER (P0.1)")
    check("the poller publishes the live gid SET",
          "window.LIVE_GIDS = new Set(" in src)
    check("liveState() is the one classifier",
          "function liveState(" in src)
    for site in ("lanes[st === 'live'", "rows.filter(m => liveState",
                 "onDay.filter(m => liveState",
                 "const st = m => liveState"):
        check("lane classifier on the snapshot ruler: %s..." % site[:28],
              site in src)
    check("[NEG] a snapshot-stripped 'live' match reads as final",
          "if (st === 'live') return 'final'" in src)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL LIVE-RAIL GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
