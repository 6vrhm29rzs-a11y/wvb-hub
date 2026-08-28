# Live box scores ARE available during a match — measured 2026-08-27

**Status: SETTLED.** Until tonight this project was forbidden from claiming that
live team or player statistics were obtainable, because nobody had ever run the
probe against a match in progress. `scripts/probe_live_boxscore.py` ran during
Florida–Nebraska (game `6640217`) at AT&T Stadium and the question is answered.

## What 54 consecutive polls during play showed

Every poll was taken with `gameState: "I"` (in progress), first set:

| | |
|---|---|
| HTTP 200 | 54 / 54 |
| Team stats present | 54 / 54 |
| **Player rows present** | **54 / 54**, median **36 rows** |
| Internally validated | 54 / 54 |
| Named statistical leaders | 54 / 54 |
| Polls reporting any problem | **0** |

`/game/{id}/boxscore` serves a full live box score: per-team totals
(`kills`, `attackErrors`, `attackAttempts`, `hittingPercentage`, `assists`,
`serviceAces`, `serviceErrors`, `digs`, `blockSolos`, `blockAssists`,
`totalBlocks`, `receptionAttempts`, `receptionErrors`, `points`) **and** the
per-player rows behind them, with a per-set breakdown under `teamStats.sets`.

Raw evidence: `docs/live_boxscore_probe_2026-08-27.jsonl`.

## ⚠ The caveat that matters as much as the headline

**Live figures are revised, and they go DOWN as well as up.** Measured in the
same window: at poll 30 Nebraska's kills fell from **9 to 8** — an official
scorer's correction, not a feed error. Attack attempts never fell across the
same 54 polls, so the revision is specific rather than general.

Cody saw this from the other side while it was happening, reading 9 kills on
one refresh and 8 on the next.

**Consequences, and they are not optional:**

* A live number is **provisional**. Nothing may accumulate it, cache it as a
  season total, or write it into `data/`.
* Anything derived from a live poll must be recomputed from the next poll, not
  incremented.
* The existing rule stands and is now justified by evidence rather than by
  caution: an exhibition and an in-progress match are both kept out of records
  and ratings until the match is final and crawled.

## Field names, since two obvious guesses are wrong

The team block uses **`attackAttempts`** (not `totalAttacks`) and
**`serviceAces`** (not `aces`). Querying the obvious names returns `None` and
looks exactly like "the feed does not carry this mid-match", which is the wrong
conclusion — it cost an hour on the night this was measured.

## What still is NOT available

`gameType` on the boxscore endpoint is `None`, so an **exhibition cannot be
detected from the feed**. That remains a hand-maintained ledger
(`data/raw/2026/exhibitions.json`).
