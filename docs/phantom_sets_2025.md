# Phantom set counts: 3.4% of 2025 box scores credit every player with the full match

**Measured 2026-08-23. Not corrected — the fix changes published numbers, so it is Cody's call.**

## What the feed does

`/boxscore` gives each player a `gamesPlayed`, and `crawl_2025.py` maps it
straight to `sets` (`("gp", "sets")`). That is the denominator of every per-set
rate on the site.

It is normally correct. Across the 7 games of 2026 so far, `gp` varies between
players in 6 of them — starters get the full match, substitutes get 1 or 2.

## Where it breaks

In some games every listed player reports the same `gp` — the match's set count
— including players whose line is entirely empty. A player who never took the
floor cannot have played four sets, so in those games the field is not
per-player data at all.

| | 2025 (completed) | 2026 (so far) |
|---|---|---|
| games | 5,131 | 7 |
| games with a uniform `gp` across every player | **173 (3.4%)** | 1 |
| phantom lines (empty, credited with the full match) | 444 | 13 |
| of those players, produced in another match | **331** | **0** |

This is the same shape CLAUDE.md already records for 2024, where bench players
were marked as having participated. It says 2025 "does not" do this. It mostly
does not — 96.6% of the time.

## Why it matters

A phantom line adds sets to a player's season denominator without adding
production, so her per-set rate is understated. For the 295 affected 2025
players where the effect is computable:

- **median understatement 16.7%**
- p90 **66.7%**, max 92.3%
- **205 players** off by more than 10%, **120** by more than 25%

2025 per-set rates feed the 2026 projection's roster delta, the projected six on
every team page, returning-production shares, and Digby's fact sheets. So this
is not cosmetic.

## Why it is NOT already fixed

Deciding that a player did not play *because her line is empty* is an inference
about an individual, and inferring a correction to the source is how a dataset
stops being the dataset (R5).

There is a narrower rule that does not require that inference:

> In a game where `gp` is identical for **every** player **and** at least one
> line is entirely empty, the `gp` field is demonstrably not per-player. Do not
> use it as a set count for that game.

That is a judgement about the FIELD's validity in one record, not about who
played. It is defensible and it is still a change to published numbers, which is
why it is written up rather than applied.

**Open question for Cody:** apply that rule, or leave the numbers as the feed
gives them and state the limitation on the page?

## Guarded meanwhile

`test_display_invariants.check_phantom_sets_are_harmless()` watches the LIVE
season and fails the moment a phantom line starts diluting a player who has
produced elsewhere. Today that count is 0 of 13, so the distortion is real and
inert. ⚠ The guard is explicitly scoped to the live season: this module defaults
SEASON to 2025 while `build_hub.py` defaults to 2026, which is how the check
first reported 331 failures for a live-season question.
