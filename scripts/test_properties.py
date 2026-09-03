#!/usr/bin/env python3
"""Unit guards for the certified-properties layer (architect commit 1)."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from properties import (certify, require_property,  # noqa: E402
                        PropertyCertificationError, POLICY)

FAILED = []


def check(name, ok, why=""):
    print(("  ok   " if ok else "  FAIL ") + name +
          (("  " + str(why)) if (why and not ok) else ""))
    if not ok:
        FAILED.append(name)


def raises(fn):
    try:
        fn()
        return False
    except PropertyCertificationError:
        return True


def main():
    meta = {}
    certify(meta, "ordering_mature_for_public_rank", False,
            POLICY["PUBLIC_RANK_MATURITY"],
            measurement={"median_counted_matches": 3,
                         "required_crossover_k": 13.5},
            dependencies={"digby_top25_2026":
                          {"generation_fingerprint": "BBB"}},
            corpus_fingerprint="AAA")
    art = {"meta": meta}

    print("1. THE FOUR REFUSALS, EACH DISTINCT")
    check("absent property RAISES (structural error, not false)",
          raises(lambda: require_property(art, "no_such_property",
                                          consumer="t")))
    check("wrong policy RAISES",
          raises(lambda: require_property(
              art, "ordering_mature_for_public_rank", consumer="t",
              expected=False, allowed_policies=["some-other-v9"])))
    check("wrong corpus pairing RAISES (right property, wrong generation)",
          raises(lambda: require_property(
              art, "ordering_mature_for_public_rank", consumer="t",
              expected=False, corpus_fingerprint="ZZZ")))
    check("stale dependency generation RAISES",
          raises(lambda: require_property(
              art, "ordering_mature_for_public_rank", consumer="t",
              expected=False,
              dependency_fingerprints={"digby_top25_2026": "CCC"})))

    print("\n2. FALSE IS A STATE, ABSENT IS AN ERROR")
    check("a certified False satisfies expected=False",
          require_property(art, "ordering_mature_for_public_rank",
                           consumer="t", expected=False)["value"] is False)
    check("a certified False RAISES against expected=True",
          raises(lambda: require_property(
              art, "ordering_mature_for_public_rank", consumer="t",
              expected=True)))
    rec = require_property(art, "ordering_mature_for_public_rank",
                           consumer="t", expected=None)
    check("expected=None returns the record for consumer branching",
          rec["value"] is False and rec["policy"]
          == POLICY["PUBLIC_RANK_MATURITY"])

    print("\n3. THE CONTRACT SHAPE")
    check("property names are stable; measurements carry the numbers",
          "measurement" in rec and "median_counted_matches"
          in rec["measurement"])
    check("matching corpus + dependency pairing passes",
          require_property(art, "ordering_mature_for_public_rank",
                           consumer="t", expected=False,
                           corpus_fingerprint="AAA",
                           dependency_fingerprints={"digby_top25_2026":
                                                    "BBB"})["value"]
          is False)
    check("the policy registry is the one home for version identifiers",
          all(isinstance(v, str) and "-v" in v for v in POLICY.values()))

    if FAILED:
        print("\nFAILED: %d" % len(FAILED))
        for f in FAILED:
            print("   - " + f)
        sys.exit(1)
    print("\nALL PROPERTY-LAYER GUARDS PASS")


if __name__ == "__main__":
    main()
