# Live match & box score: what the source actually serves

Measured 2026-08-25 against `ncaa-api.henrygd.me` with real fixtures. Re-run
any line with the command beside it; nothing here is inferred.

## The two endpoints

| endpoint | what it is |
|---|---|
| `/scoreboard/volleyball-women/d1/{Y}/{M}/{D}/all-conf` | the slate for one date; one row per match |
| `/game/{id}/boxscore` | the official box score, team totals + player lines |

## Field inventory — scoreboard row (identical shape in every state)

`gameID · gameState · currentPeriod · contestClock · finalMessage · startTime ·
startTimeEpoch · startDate · network · liveVideoEnabled · title · url ·
bracketId · bracketRound · home{} · away{}`

Each side carries `names{char6,short,seo,full} · score · rank · seed ·
description · conferences · winner`.

**The shape never changes; the CONTENT does.** That is the whole reason a state
model is needed: the same keys are present before first serve and after final,
so "the field exists" says nothing about whether it means anything.

| field | upcoming (`pre`) | final |
|---|---|---|
| `gameState` | `pre` | `final` |
| `currentPeriod` | `''` | `FINAL` |
| `contestClock` | `''` | `0:00` |
| `home.score` / `away.score` | `''` (empty string) | `'0'` / `'3'` |
| `network` | `''` on all sampled | `''` on all sampled |
| `rank` | `''` on all sampled | `''` on all sampled |

⚠ **AN EMPTY SCORE IS A STRING, NOT A NUMBER OR A NULL.** `''` coerces to 0 in
JavaScript, so a naive read shows an unplayed match as 0-0 — indistinguishable
from a real 0-0 at first serve. Every consumer must test for the empty string.

## `/game/{id}/boxscore` by state — MEASURED

    curl -s -o /dev/null -w '%{http_code}\n' \
      -A 'wvb-hub/0.1' https://ncaa-api.henrygd.me/game/<id>/boxscore

| state | sampled ids | result |
|---|---|---|
| upcoming | 6637146, 6627402, 6625689 | **HTTP 502, an HTML error page — not JSON** |
| final | 6639891, 6639887 | HTTP 200 JSON |

⚠ **BEFORE FIRST SERVE THE BOX SCORE ENDPOINT DOES NOT 404 AND DOES NOT RETURN
AN EMPTY DOCUMENT — IT RETURNS A 502 HTML PAGE.** Anything that assumes a JSON
body will throw on `json.loads`. Three ids, all three 502; a final on the same
run returned 200, so this is the endpoint's behaviour and not an outage.

### Final, box score present (6639891, Pittsburgh–Xavier)

    status: 'F'   period: 'FINAL'   teamBoxscore: 2 entries

`teamStats`: `assists · attackAttempts · attackErrors · ballHandlingErrors ·
blockAssists · blockSolos · blockingErrors · digs · gamesPlayed ·
hittingPercentage · kills · points · receptionAttempts · receptionErrors ·
serveAttempts · serviceAces · serviceErrors · setAttempts · setErrors`

`playerStats`: 13 rows for that side, each with the same counting stats plus
`firstName · lastName · number · position · participated · gamesPlayed`.

## What is NOT yet measured, and why

- **live score only** and **live with team stats** — no D-I women's volleyball
  match has been in progress during any probe window. Today's slate is empty;
  the next is Friday 2026-08-28 (195 fixtures).
- **final, box score pending** — this is a window of unknown length immediately
  after a match ends. It cannot be manufactured, only caught.

**Until `scripts/probe_live_boxscore.py` has run against a live match, nothing
in this project may claim live team or player statistics are available.** The
code therefore treats "no usable stats" as the ordinary path in both live
states, and the display degrades to score-only rather than assuming.

## The consequence for display

`final, box score pending` is a REAL state that must render as itself. A final
whose box score is a 502 must not produce an empty table, a zero-filled one, or
leaders derived from nothing.
