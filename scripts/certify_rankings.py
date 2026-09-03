#!/usr/bin/env python3
"""The ranking-chain certification step (architect commit 2, 2026-09-03).

Runs AFTER the rating fit and the digby blend, and certifies the property
both the board and the weekly archive consume:

    ordering_mature_for_public_rank

measured HERE, against the exact generations of both inputs -- because
letting the rating certify it directly fossilizes a time-of-check/
time-of-use defect (rating reads yesterday's k, digby regenerates
tonight, the board consumes mismatched generations). The certificate
records the generation fingerprints of BOTH inputs; require_property's
pairing check refuses it the moment either regenerates.

Writes data/ranking_certificates_2026.json -- never rewrites rating or
digby after creation just to attach metadata.
"""
import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import season_counts as SC  # noqa: E402
from properties import certify, POLICY  # noqa: E402

SEASON = 2026
OUT = os.path.join(REPO, "data", "ranking_certificates_%d.json" % SEASON)


def _load(rel):
    try:
        return json.load(open(os.path.join(REPO, rel)))
    except (OSError, ValueError):
        return None


def build():
    rating = _load("data/rating_%d.json" % SEASON) or {}
    digby = _load("data/digby_top25_%d.json" % SEASON) or {}
    corpus = SC.corpus_fingerprint(SEASON)

    # ⚠ ONE maturity logic. During migration it lives in
    # build_rankings_board.live_rating_mature and is IMPORTED here so the
    # shadow guard can prove certificate == old gate; commit 3+ makes the
    # consumers read the certificate and this call becomes the only site.
    import build_rankings_board as BB
    validated = bool((rating.get("meta") or {}).get("validated"))
    mature, why = (BB.live_rating_mature(rating) if validated
                   else (False, "rating not validated"))
    k = ((digby.get("meta") or {}).get("k_matches"))
    gp = sorted(int(t.get("games_played") or 0)
                for t in (rating.get("teams") or []))
    med = gp[len(gp) // 2] if gp else 0

    meta = {"season": SEASON,
            "generated_utc": datetime.datetime.utcnow()
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "corpus_fingerprint": corpus}
    certify(meta, "ordering_mature_for_public_rank",
            bool(validated and mature),
            POLICY["PUBLIC_RANK_MATURITY"],
            measurement={"median_counted_matches": med,
                         "required_crossover_k": k,
                         "rating_validated": validated,
                         "held_because": (None if (validated and mature)
                                          else why)},
            dependencies={
                "rating_%d" % SEASON: {
                    "generation_fingerprint":
                        (rating.get("meta") or {})
                        .get("corpus_fingerprint"),
                },
                "digby_top25_%d" % SEASON: {
                    "generation_fingerprint":
                        (digby.get("meta") or {})
                        .get("corpus_fingerprint"),
                    "k_matches": k,
                },
            },
            corpus_fingerprint=corpus)
    json.dump({"meta": meta}, open(OUT, "w"), indent=1)
    rec = meta["certifies"]["ordering_mature_for_public_rank"]
    print("ranking certificates: ordering_mature_for_public_rank=%s "
          "(median gp %s vs k %s; corpus %s)"
          % (rec["value"], med, k, corpus))
    return meta


if __name__ == "__main__":
    build()
