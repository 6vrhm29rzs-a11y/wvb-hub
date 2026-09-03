#!/usr/bin/env python3
"""Certified properties -- the contract layer between producers and consumers.

Architect-approved design (2026-09-03, consult round; docs/
certified_properties_design.md as amended): producers CERTIFY named,
versioned properties with their measurements and the generations of their
inputs; consumers REQUIRE the exact property they need, by name, and the
build fails closed on absence, wrong policy, or wrong generation pairing.

The two rules that make the Lehigh class unwritable:
- A property name is a CONTRACT and is stable; hashes and numbers are
  MEASUREMENTS inside it (never `built_from_corpus:<hash>` names).
- A property is valid only for the exact policy and exact generation of
  the inputs that produced it. A certification whose dependency
  fingerprints do not match what the consumer holds is stale and raises --
  "the right property for the wrong generation" cannot cross the build.

A certified value of False is a LEGITIMATE state the consumer handles
(e.g. "not mature -> use the blend"). Absence is a structural error and
always raises; False and absent are never the same thing.

Python 3.9 target.
"""
from typing import Any, Dict, Optional

# The policy registry: version identifiers live HERE; the calculations
# stay with their owners (properties.py never recomputes business logic).
POLICY = {
    "FIT": "rating-fit-v3",
    "OOS_VALIDATION": "chrono-validation-v2",
    "PUBLIC_RANK_MATURITY": "blend-crossover-v1",
    "BLEND_WEIGHT": "blend-weight-v1",
    "RESUME_POPULATED": "resume-populated-v1",
    "CANONICAL_CORPUS": "canonical-corpus-v1",
}


class PropertyCertificationError(RuntimeError):
    """A consumer's requirement was not met. Always fail-closed."""


def certify(meta, name, value, policy, measurement=None, dependencies=None,
            corpus_fingerprint=None):
    # type: (Dict, str, Any, str, Optional[Dict], Optional[Dict], Optional[str]) -> Dict
    """Record a certification in meta["certifies"][name]. Returns the record.

    dependencies: {artifact_name: {"generation_fingerprint": ..., ...}} --
    the exact generations of the inputs this certification was measured
    against. A consumer holding different generations must refuse it.
    """
    rec = {"value": value, "policy": policy}
    if measurement is not None:
        rec["measurement"] = measurement
    if dependencies is not None:
        rec["dependencies"] = dependencies
    if corpus_fingerprint is not None:
        rec["corpus_fingerprint"] = corpus_fingerprint
    meta.setdefault("certifies", {})[name] = rec
    return rec


def require_property(artifact, name, consumer, expected=True,
                     corpus_fingerprint=None, allowed_policies=None,
                     dependency_fingerprints=None):
    # type: (Dict, str, str, Any, Optional[str], Optional[list], Optional[Dict]) -> Dict
    """Return the certification record, or raise PropertyCertificationError.

    Raises on: absent property (structural error -- nobody certified what
    this consumer needs), a policy outside allowed_policies, a corpus
    pairing mismatch, or a dependency-generation mismatch. A present
    record whose value != expected is ALSO a raise when expected is not
    None -- consumers that can handle both states pass expected=None and
    branch on the returned record's value.
    """
    meta = (artifact or {}).get("meta") or {}
    certs = meta.get("certifies") or {}
    rec = certs.get(name)
    if rec is None:
        raise PropertyCertificationError(
            "%s requires property %r and the artifact certifies nothing by "
            "that name -- absence is not 'false', it is uncertified"
            % (consumer, name))
    if allowed_policies is not None and rec.get("policy") \
            not in allowed_policies:
        raise PropertyCertificationError(
            "%s: property %r certified under policy %r, not one of %r"
            % (consumer, name, rec.get("policy"), allowed_policies))
    if corpus_fingerprint is not None and \
            rec.get("corpus_fingerprint") is not None and \
            rec["corpus_fingerprint"] != corpus_fingerprint:
        raise PropertyCertificationError(
            "%s: property %r was certified against corpus %s; this build "
            "holds %s -- right property, wrong generation"
            % (consumer, name, rec["corpus_fingerprint"],
               corpus_fingerprint))
    if dependency_fingerprints:
        deps = rec.get("dependencies") or {}
        for art, want_fp in dependency_fingerprints.items():
            got = (deps.get(art) or {}).get("generation_fingerprint")
            if got is not None and want_fp is not None and got != want_fp:
                raise PropertyCertificationError(
                    "%s: property %r depends on %s generation %s; the "
                    "consumer holds %s -- stale certification"
                    % (consumer, name, art, got, want_fp))
    if expected is not None and rec.get("value") != expected:
        raise PropertyCertificationError(
            "%s: property %r is certified %r, required %r"
            % (consumer, name, rec.get("value"), expected))
    return rec
