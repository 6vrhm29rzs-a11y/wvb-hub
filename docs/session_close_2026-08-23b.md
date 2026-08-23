# SUPERSEDES session_close_2026-08-23.md — close of 2026-08-23 (afternoon/evening)

Read this first. The earlier close of the same date covers the morning (polls,
Pacific time, public-build hardening) and is still accurate for that.

---

## ⚑ RESUME HERE — DO THESE FIRST

**1. Verify the remote before trusting anything about it.**

```
git ls-remote origin
```

Last push was `60242c7`. There will be **uncommitted work after it** — check
`git status`. Git is classifier-blocked in auto mode: hand Cody the command,
never attempt it.

**2. There are 338 Digby summaries still to write.** 10 exist and are verified
stable. This is the one outstanding thing that costs money, and it is now safe:

```
export ANTHROPIC_API_KEY=sk-ant-<key>
python3 scripts/digby.py && python3 scripts/build_hub.py
```

**⚠ READ THE NEXT SECTION BEFORE TOUCHING `fact_sheet()`.** It cost Cody two
paid runs.

**3. Everything runs.** 14 test suites pass, the nightly sequence completes
clean end to end, the build works from a fresh checkout with no `Cody/`.

---

## ⚠⚠ THE EXPENSIVE MISTAKE, AND THE RULE THAT PREVENTS IT

A stored Digby summary is only valid for the facts it was written from. The
first 340 were written citing **projections** — and a completed match removes a
fixture, which shifts every projection slightly. Measured a day later: **326 of
340 failed their own fidelity gate**, on numbers like "13.62 projected wins"
that had become 13.66.

Fixing it required regenerating everything (~$4). Then I shipped the fix having
missed **two more movers** — `our_rank_2026` (moves with the rating, and changes
basis entirely at 50 played matches) and `avca_preseason_rank` (a weekly poll) —
which would have rotted them a **second** time. Cody stopped that run.

**THE RULE.** Before a field may reach a stored summary, ask:

> *Would this be different tomorrow if nobody changed teams?*

If yes it is VOLATILE and belongs in `digby.VOLATILE`. Ranks move, polls move,
projections move, records move, per-set rates move. Last season's production and
who is on the roster do not. The **chat** gets everything, because it answers
live and its answer is not stored.

**Guards now in place:**
- `test_digby.py` fails if **any new field** reaches a stored summary without
  being classified — the question gets asked once, deliberately.
- `build_hub.py` **withholds** any summary whose facts have moved rather than
  showing a stale figure. It prints how many.

**AND THE TEST THAT ACTUALLY PROVES IT — run this, it is free:** capture every
team's durable hash, run the whole nightly sequence, compare. Verified 2026-08-23:
a completed match, a re-crawl, a re-prediction and a re-simulation moved
**0 of 348**. The 10 written summaries then survived a second full nightly run
intact. *Do this before ever asking Cody to pay for a regeneration.*

---

## Built today (afternoon/evening)

| | |
|---|---|
| **Rotations** | `rotations.py` + `build_rotations.py` — 48,625 of 50,410 set-teams (96.5%) from the MIT `ncaavolleyballr` mirror. Validated by the 5-1 signature: **82.2%** (n=169) against a 21.3% null, where ncaa.com's jersey order scored at chance. ⚠ It is the SERVING six — liberos replace middles before they serve. |
| **Digby** | summaries behind a fidelity gate + a chat panel (`live_server.py`, key from the environment only). Fact sheet 82 → 112 fields. |
| **Digby's Top 25** | blends preseason with results, `w = n/(n+k)`, **k = 13.5** from the projection's own out-of-sample error (not the population spread — that gave one match 20%). Form column with ranked opponents marked; biggest-movers line; weekly archive. |
| **Team stats** | box-score team totals + a per-team season box showing what a team does beside **what it allows**. Leaders → **Stats** with players/teams toggle. |
| **AVCA honours** | 3,027 All-America selections, 842 All-Region, zero unresolved schools for 2024-25. Badges in the shared player cell; national awards outrank team selections. |
| **Visual** | Oswald condensed face, 373 school colours read out of logo SVGs, sliding nav underline, **SVG bracket connectors with a mirrored right half**, 1,581 crests, position avatars. |
| **Player cell** | one definition — photo, name, `#num · POS` beneath — used by roster, Stats and Players. Clicking opens her match log. |

**Data corrections:** 32 conferences not 33 (UT Arlington is UAC, derived from
its own schedule) · UAC added to the AQ map · New Orleans schedule join (`LSU
New Orleans`) · Saint Francis is genuinely 0 fixtures and says so.

**Bugs found and fixed:** duplicate element id (`sbody` twice) · a stale phone
override pinning roster names into a 26px slot · nobody highlighted at 0-0 ·
`const TEAMS` read before declaration (a `typeof` guard does **not** help in the
temporal dead zone) · reloading `digby` without `digby_chat` left the chat
holding the old `fact_sheet` · a match falling between the live band and the
archive.

---

## LOCAL ONLY (on disk, not in git)

`Cody/` · `data/raw/2025/pbp/*.csv` (739 MB) · `reference/` · `AVCA-*.xlsx` ·
`assets/digby_*_full.png` · the loose root PNG/webarchive drops.

⚠ The DeLeye illustration was committed in `7fd6ce4` and untracked in
`60242c7`. **It is still recoverable from history** unless Cody asks for a
rewrite.

---

## Open

- **338 Digby summaries** to write (see above).
- **`/code-review ultra`** — Cody has still not run it; the Builder cannot.
- **Coaches** — `data/raw/2026/coaches_2026.json`, top 50 scaffolded, 2 filled
  from AVCA Coach-of-the-Year citations. Not derivable from any feed: school
  coaches pages are JavaScript-rendered. A sourced-entry job.
- **Rotations have no live 2026 source.** The deriver is done; the historical
  CSVs cover 2020-2025. Live would need StatBroadcast permission — the
  no-scrape hook blocks it and their terms forbid automated access.
- Central Conn. St. and Tennessee Tech still have no 2026 roster.
- **GitHub Pages no longer updates** — the public build is off at Cody's
  instruction. Phone access would need a private repo (paid) or another host.
