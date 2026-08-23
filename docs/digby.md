# Digby

A dig is the defensive save — the thing that retrieves what looked gone. Digby
digs up the answer.

He writes a short summary of each team from **this hub's own numbers** and
nothing else. Chat comes next; the summaries prove the machinery first.

## Run it

```
export ANTHROPIC_API_KEY='sk-ant-...your real key...'          # your shell, never a file in this repo
python3 scripts/digby.py --limit 5      # try five teams
python3 scripts/digby.py                # all 348
python3 scripts/build_hub.py            # render them
```

**The key never passes through anything but your own shell.** It is read from
the environment, used in memory, and never logged, never written to the cache,
never embedded in the page. The public build carries no trace of Digby at all.

`--force` regenerates even when nothing changed. `--team "Nebraska"` does one.

## Cost

`claude-opus-5`, low effort, ~1–2 KB of facts per team. **About $4 for all 348**,
then close to nothing: each team stores a hash of its facts and regenerates only
when its numbers actually move. A daily rebuild costs $0 until results change.

## Why it is built this way

The page holds ~2.8 MB of data — roughly 700k tokens. Nothing reads that per
request, and it should not: Digby answers from **our** data, not from its memory
of college volleyball. Each request carries a small, flat fact sheet.

Flat matters. `top_scorer_1_points_per_set: 4.215` can be cited exactly; a
nested blob cannot, and the check below depends on "which field did this number
come from?" having one answer.

## The gate

Digby returns the prose **and** a list of claims, each naming the field its
number came from. Before anything is stored:

- every number in the text must match a fact **at the precision it was written**
- every cited field must exist
- **one failure discards the whole summary** — the panel shows nothing rather
  than something unverified

Precision-matching is the trick. Exact string comparison rejects honest prose: a
model given `4.215` writes "4.22", and `24.54` becomes "24.5" or "25". A
tolerance of half a unit at the written precision accepts those and still
catches a number that is merely close — the fact is `70`, so "71%" fails.

`scripts/test_digby.py` proves it, including a **negative control**: a fluent
sentence carrying an invented `.312` hitting percentage must be rejected. Two
real bugs came out of writing that test — a regex that read `.312` as `312`, and
a rounding rule that rejected a truthful `4.22`.

## What Digby will not do

- state a number that is not in the facts
- compute, average, convert or estimate anything new
- fill a gap — if the data does not say, he says nothing
- appear on the public site

## A hazard worth remembering

Digby is the **first model-written text** to enter the page's JSON payloads.
Those embed with `json.dumps` and no escaping, which was safe while every value
came from a feed. A summary containing `</script>` would end the script block and
break everything below it. `blob()` in `build_hub.py` escapes `</`; a test
asserts it.


## Running it, and what protects the bill

```
export ANTHROPIC_API_KEY='sk-ant-...your real key...'   # your shell, never a file here
python3 scripts/digby.py --limit 5                      # five teams first
```

The key comes from `console.anthropic.com` -> API keys. Nothing in this repo
writes it, logs it, caches it, or embeds it in the page.

**Three separate things stop a bad run from spending money**, all added after
the first live run made 348 doomed requests because the key was the literal
placeholder `...` from the instructions:

1. **Preflight.** The key's presence and shape are checked before the first
   request. Unset, `...`, or anything not starting `sk-ant-` prints what to do
   and sends nothing.
2. **A rejected key is fatal, not per-team.** A wrong key is wrong for every
   team, so the run stops on the first one instead of repeating the same error
   348 times and burying it.
3. **`--limit` caps ATTEMPTS, not successes.** The original counted successes,
   which meant a run where nothing succeeded had no cap at all. Separately, five
   failures with nothing written stops the run.

Guarded by `scripts/test_digby.py`, including a positive control that a healthy
run is *not* cut short. All four guards were verified to fail against the old
behaviour.
