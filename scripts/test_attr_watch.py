#!/usr/bin/env python3
"""Guards for the live attribution watch (2026-09-01, IU-Georgia).

The mechanism: data/raw/2026/live_attribution_watch.json labels a live match
whose feed attribution is disputed, and -- ONLY with display_swap: true and
attributable evidence -- reattributes the numbers at live_server's choke
point. Nothing is invented, nothing counted; finals still go through the
two-source correction ledger.
"""
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import live_server as LS  # noqa: E402

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  " + why) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def with_ledger(doc):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(doc, f)
    f.close()
    LS._ATTR_LEDGER = f.name
    LS._attr_cache["mtime"] = None
    return LS._attr_swaps()


def main():
    print("1. THE LOADER'S REFUSALS")
    sw = with_ledger({"_readme": "x",
                      "111": {"claim": "c", "evidence": [{"kind": "host_livestat"}],
                              "display_swap": True},
                      "222": {"claim": "c", "evidence": [{"kind": "x"}]},
                      "333": {"claim": "c", "display_swap": True}})
    check("an evidenced display_swap entry swaps", "111" in sw)
    check("a label-only entry never swaps", "222" not in sw)
    check("display_swap WITHOUT evidence never swaps", "333" not in sw)
    check("underscore keys are metadata, not matches", "_readme" not in sw)

    print("\n2. THE CHOKE POINT REALLY REATTRIBUTES BOTH FILLS")
    src = open(os.path.join(REPO, "scripts", "live_server.py")).read()
    check("the swap is applied before the state model",
          src.find('swaps = _attr_swaps()') < src.find('ONE STATE MODEL'))
    check("the detail refill re-applies the swap (the feed refills sets "
          "and away/home after the first swap)",
          "re-apply the cited swap" in src and
          '[[b, a] for a, b in row["sets"]]' in src)
    check("the payload names the correction",
          '"attribution_corrected"' in src)

    print("\n3. THE PAGE STATES WHICH CLAIM IT IS MAKING")
    page = open(os.path.join(REPO, "Cody", "START-HERE.html"),
                encoding="utf-8").read()
    check("corrected and under-review are distinct wordings",
          "SCORE ATTRIBUTION CORRECTED." in page and
          "SCORE ATTRIBUTION UNDER REVIEW." in page)
    check("emphasis is suppressed only while UNcorrected",
          "!ATTR_WATCH[m.gid].corrected" in page)

    print("\n4. [NEG] negative controls")
    # a rogue entry claiming a swap with no evidence list at all
    sw2 = with_ledger({"999": {"display_swap": True}})
    check("[NEG] evidence-free swap request is refused", "999" not in sw2)
    # cache: an unreadable ledger must keep the last good copy, not blank it
    sw3 = with_ledger({"444": {"claim": "c", "evidence": [{}],
                               "display_swap": True}})
    bad = LS._ATTR_LEDGER
    open(bad, "w").write("{not json")
    LS._attr_cache["mtime"] = None
    sw4 = LS._attr_swaps()
    check("[NEG] a broken ledger edit keeps the last good swaps mid-match",
          "444" in sw4)

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL ATTRIBUTION-WATCH GUARDS PASS")


if __name__ == "__main__":
    main()
