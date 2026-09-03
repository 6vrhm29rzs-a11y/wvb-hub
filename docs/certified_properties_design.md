# Certified properties — design for Cody's review (2026-09-03)

**The problem class, paid for twice:** a consumer gates on a boolean that
proves the wrong property. The 50-match floor proved *a fit can run*; the
board read it as *fit is good*. `meta.validated` proved *validation
executed*; the board read it as *ordering beats the blend* — and Lehigh sat
#3. Each fix added the right gate after the damage; nothing stops the next
producer/consumer pair from repeating the pattern.

**The structural fix (architect consult):** producers emit *named,
versioned properties they certify*; consumers *demand the property they
need by name*. A property can never satisfy another by implication.

## Producer side

Each truth-bearing artifact's meta gains:

```json
"certifies": {
  "fit_completed":            {"value": true,  "policy": "rating-fit-v3"},
  "out_of_sample_validated":  {"value": true,  "policy": "chrono-validation-v2"},
  "ordering_mature_for_public_rank": {
      "value": false,
      "measurement": {"median_counted_matches": 3, "required_crossover_k": 13.5},
      "policy": "blend-crossover-v1"
  }
}
```

## Consumer side

```python
require_property(rating, "ordering_mature_for_public_rank",
                 consumer="rankings_board")
```

`require_property` raises (fails closed) when the property is absent —
absence is *not certified*, never *assumed fine*. A consumer asking for a
property nobody emits is a build error, which is exactly the moment the
producer/consumer conversation should happen.

## Mapping onto what exists today

| current gate | becomes property | emitted by |
|---|---|---|
| `meta.validated` | `out_of_sample_validated` | bakeoff/rating |
| `live_rating_mature()` | `ordering_mature_for_public_rank` | rating (measured against digby's k) |
| resume `meta.active` | `resume_populated` | resume |
| digby's k-derivation | `blend_weight_derived_not_chosen` | digby |
| `corpus_fingerprint` match | `built_from_corpus:<hash>` | all four |
| snapshot same-basis rule | consumer demands `ordering_mature_for_public_rank` too | archive |

## Cost & migration

- ~1 day: a small `properties.py` (emit + require, ~60 lines), stamp the
  four producers, convert the three highest-risk consumers (board, archive,
  resume view). Old booleans stay during migration; guards assert the new
  path is the one consulted.
- The win: the *next* Lehigh-class incident becomes impossible to write
  accidentally — a consumer literally cannot compile against the wrong
  property, and a new gate must declare what it measures.

## Recommendation

Do it, scoped to the four ranking-chain artifacts first. Everything else
migrates opportunistically. Waiting for your go before touching subsystem
boundaries.
