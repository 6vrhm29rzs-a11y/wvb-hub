# Builder session-close — 2026-08-22

**Supersedes the 2026-08-11 close (I).** Read this, then `CLAUDE.md`.

## State: green

Season is live. First matches 8/21. All 7 test suites pass. Sim, predictions
and hub all rebuild clean.

Single page Cody opens: **`Cody/START-HERE.html`** (2.3 MB, self-contained).
Tabs: scores · rankings · teams · leaders · players · standings · bracket ·
schedule · tv. Served at `http://127.0.0.1:8799/START-HERE.html`.

## The model, as fitted (every constant measured, none hand-set)

| constant | value | how it was measured |
|---|---|---|
| `ROTATION` | 6 | top-6 median error −0.46 pts/set vs 5/7/8/9 |
| `CAL_SLOPE` (stacking) | 0.7965 | each extra point stacked returns 80% of itself |
| level effect | −0.215 pts/set per SD | within-player fixed effects, 914 players / 20,997 obs, 95% CI [−0.231, −0.200] |
| `COMPOSITE_PER_ADJ6` | 1.13122 | composite units per adj-6 unit |
| `ROSTER_DELTA_WEIGHT` | 0.0565 | joint 5-fold OOS fit, 2024→2025, n=323 |
| `CHURN_WEIGHT` | −0.1304 | same fit — worth ~2× the roster delta |
| `PRIOR_SLOPE` / residual SD | 0.8597 / 2.123 | season-to-season persistence |
| `HOME_ADV` | 0.333 | |
| match model Brier | 0.1289 | every bucket within 3.4 pts over 5,014 matches |

**Joint fit (the headline result of this session):**

```
prior alone              rho 0.8253
prior + roster delta     rho 0.8312
prior + churn            rho 0.8387
prior + delta + churn    rho 0.8405
z-weights: prior +2.178 | delta +0.123 | churn -0.284
```

Fitted jointly, not one at a time — the roster delta and churn both partly
measure production lost, so separately-fitted weights would double-count it.

## Cody's churn hypothesis: right, for a different reason

He observed that pollsters mark down heavy-turnover teams (SMU) because they
"haven't meshed yet." Two tests:

- **Retrospective** — if it were a chemistry cost, the penalty should fade.
  It does the opposite: high-churn quartile residual win% **−0.019 early →
  −0.060 late**. Not temporary. Durable talent loss.
- **Prospective** — share of last season's production that did not return to
  D-I anywhere, knowable the day rosters publish. This is the shipped feature.
  320/348 teams adjusted; a team with no returning share gets **no** adjustment
  rather than the field mean (an absent measurement is not a zero).

## Honest caveats that must stay on the page

- The roster aggregation **never beats the prior alone** out of sample
  (0.806 vs 0.827). It is a correction to last season's composite, not a
  foundation.
- **Texas is #2 largely because it was #2 last year.** Say so.
- Other rankings (AVCA / VolleyTalk / RPI / Massey) are **reference columns
  only** — never inputs. Cody was explicit.

## Open

1. **Rotations / starting positions — Cody's newest ask. FEASIBILITY DONE,
   BUILD NOT STARTED.** Endpoint is `/game/{id}/play-by-play` (200, ~70 KB;
   `pbp`/`playbyplay` both 422). It carries a six-name on-court group per set
   plus every substitution by name. Three things gate the build:
   - **2025 is populated, 2026 is EMPTY.** Louisville–Texas A&M (8/21/26):
     16 `starters:` lines, 0 filled. Six 2025 games: 100% filled. Projected
     lineups can be built from history; 2026 actuals cannot be confirmed yet.
   - **The feed's `teamId` and team name are WRONG on half these lines.**
     `"Pittsburgh starters: Bergen Reilly; Rebekah Allick; ..."` under
     `teamId 45986` — those are Nebraska players. Each lineup is listed twice,
     once correctly labelled and once under the opponent's name and id.
     **Attribute by matching names to rosters, never by the feed's label.**
   - **Order is NOT verified as rotation order.** The cyclic-shift test failed,
     but it ran on a parse that trusted the bad labels above, so the test is
     void — not the hypothesis. Re-run it with name-based attribution before
     shipping any "rotation 1-6" view. Inferring rotation from box-score
     totals instead would be R5.
2. Photos beyond the 132 teams covered — the other 215 use JS-loaded roster
   templates. A real ceiling, not a bug.
3. AQ mechanism confirmed for 6 of 32 conferences.
4. **Cody has not run `/code-review ultra`.** The Builder cannot launch it.

## Constraints that must persist

- **Git is classifier-blocked in auto mode.** Do the work, leave it on disk,
  hand Cody the exact command to paste.
- **The repo is PUBLIC.** Player photos are stored as **URLs only** — never
  downloaded, never committed. VolleyTalk forum content and TV listings stay
  in gitignored `Cody/`.
- Do not spoof user agents to defeat bot protection (VolleyballMag, Massey).
  Read those in Cody's browser instead.
- R5: never synthesise a displayed value. Missing renders as an em dash.

## Bugs fixed this session (all guarded)

Kassie O'Brien wrongly departed (HTML entity in surname + class-token filter +
dead domains) · unit error summing individual rates into a team rate ·
set-score orientation inverted · `null` written into `games.jsonl` ·
false event at Samford's gym · UTC vs ET date filing · template placeholder
collision · mixed `%`-format and concatenation · standings `selectedIndex` ·
`rpi_2025.py` and `reconcile_2025.py` crashing every run behind `|| true`.
