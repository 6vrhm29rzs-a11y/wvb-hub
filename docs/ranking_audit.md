# Ranking engine audit — what it does, where it can be wrong

Written 2026-08-24, in response to: *"the rankings aren't true to what i feel...
texas looks a hot mess and is too high."*

Nothing here is tuned to make Texas fall. The whole point is to find the
structural reason, and there is one.

---

## A. What the current model does

There are **three different rankings** in the codebase, and only two are on the
page. Confusing them is the root of the complaint.

### 1. The composite rating — `rating_2025.py` (season-parameterised)

```
composite = 1.2705 · Z(RPI) + 1.2703 · Z(opponent-adjusted net points/set)
```

Both weights **fitted** by a two-feature logistic on match outcomes, not chosen.
Ratio 1.0001 : 1 — they came out equal, which was not designed.

| Input | Where it comes from |
|---|---|
| **RPI** | `rpi_2025.py`, built from our own game log. 25% win% / 50% opponents' win% / 25% opponents' opponents' win%. **Unweighted — no home/road multiplier**, because volleyball's manual has none. D-I opponents only. |
| **Net points/set** | `/game/{id}` linescores, summed per set. This is where 25-12 vs 25-23 lives, and where a match a team was outscored in but won carries a **negative** value. |
| **Opponent adjustment** | Ridge least squares over the whole game graph: `y(i vs j) ~ mu + off_i − def_j + h·home_sign`, coordinate descent, 300 sweeps, ridge = 3.0 pseudo-games. |
| **Home / road / neutral** | The `h` term above. **Neutral floors get no home term** — `venues.py` decides from the venue itself and abstains when it cannot tell. |
| **Sample size** | Ridge shrinkage in pseudo-games (a 3-match team is pulled hard to the mean, a 30-match team barely moves) + a `low_confidence` flag under 10 matches. |

**It refuses to fit under 50 played matches.** The 2026 season has 7. So this
rating **does not exist yet**.

### 2. The preseason projection — `project_2026.py`

2026 rosters × each player's actual 2025 points/set, normalised to a neutral
schedule by a measured level effect (−0.214 pts/set per SD of opponent
strength). Top **6** summed (measured: best-fitting cut). Then two fitted
corrections on last season's composite: `ROSTER_DELTA_WEIGHT = 0.0565`,
`CHURN_WEIGHT = −0.1304`. `W_FRESHMAN = 0.00` — no recruiting data exists.

**It reads no 2026 result at all.** It cannot move.

### 3. Digby's Top 25 — `digby_top25.py`

```
score = (1−w)·preseason_z + w·season_z,     w = n/(n+k),   k = 13.5
```

The only ranking on the site that moves during the season.

---

## B. Problems found

### B1. THE HEADLINE PROBLEM: the tab called "Rankings" cannot move.

With 7 matches played, `rank_source = "preseason"`. So the Rankings tab is
**the projection** — Texas is #2 there because it was projected #2 in July, and
its 3-1 home loss to Arizona St. is not an input. The page says so in its lead
sentence, but it is the tab named "Rankings", and a reader is entitled to
assume a ranking responds to results.

**This is the main thing Cody is looking at, and his objection to it is correct.**

### B2. The season term is NOT opponent-adjusted.

In `digby_top25.py`, `season_z = observed margin / tau`. Texas's −4.25 pts/set
is treated exactly as if it had come against an average D-I team. It came
against **Arizona St., which the same model ranks 7th**. Losing to the 7th-best
team is weak evidence of being bad; the model currently cannot tell.

⚠ Note this cuts **against** the complaint: correcting it moves Texas **up**,
not down. The implied strength from that match is `z(ASU) + margin/tau ≈
2.15 − 1.74 = +0.41`, versus the −1.74 currently used. The page already admits
this ("the schedule is barely adjusted for early"), but it is a real defect.

### B3. There is no résumé ranking on the site.

R3 has said since Phase 3 that **strength ≠ résumé**, and measured it: relative
to RPI the composite favours teams with *worse* records (corr −0.205). The site
shows a strength ranking and a projection. It does not show "what have you
actually done", which is the question Cody's eye is asking when it says a 0-1
team is too high.

### B4. No explicit quality-win or bad-loss term.

Both enter only implicitly, through RPI's opponent terms and the ridge. There is
no "beat a top-25 team" credit and no "lost at home to #180" penalty.

### B5. Nothing models availability, and the data exists.

`availability.py` flags a match where a team's top-6 by scoring rate has no
box-score line — 23% of 2025 team-matches. It is **not** an input to any
rating. A loss with three starters out is currently identical to a loss at full
strength.

---

## C. What the measurements already rule out

This is the part that should shape any v2, because it is paid for. Full detail
in `docs/rating_factors_2025.md`; method is always **split by date, fit on the
past, score on matches that had not happened yet**, with bootstrap CIs.

| Proposal | Measured result |
|---|---|
| Time decay / recency weighting | **Nothing.** Half-lives 14–90 days all ≤ baseline; the shortest is worst. |
| Cap or discount blowout margins | **Worse.** cap ±3 = −0.0113 AUC, CI clear of zero. Do not squash blowouts. |
| Rank on sets (3-0 vs 3-2) | **Worst of all.** −0.0137. Point margin strictly dominates it. |
| Rest / same-day turnaround | **Nothing.** 49.2% vs 50.3%; a fitted rest term moves AUC −0.00002. |
| Clutch / close-set win rate | **Worse.** −0.0029, CI clear of zero. |
| Five-set record | **Worst of the family.** −0.0055. A history of coin flips. |
| Deuce-set win rate (composure) | **Worse.** −0.0013. |
| Grit / comeback, consistency, blowout rates | Nothing. |
| React faster to results (smaller k) | **Worse, monotonically.** Best k = 25 vs shipped 13.5, CI clear of zero. k = 0.5 is worse than ignoring results entirely. |
| Earned points ("silent points") | **The only positive.** +0.0016 AUC, best RMSE — but CI includes zero. Not proven. |

**Nine of the eleven ideas both AI proposals recommend are measurably neutral or
harmful.** Any v2 that adds a clutch term, a recency ramp, a five-set factor or
a margin cap is adding something that has been tested here and failed.

---

## D. Proposed architecture

Two numbers, not eleven — because two are measured and eleven would not be.

### D1. POWER — "who would win tomorrow"  *(exists, validated)*

The composite. Shipping. Beats RPI out of sample at three cutoffs. Displayed as
`50 + 12.5·z`.

**Change to make:** opponent-adjust the early-season term (B2). Implied strength
from a match is `z(opponent) + (margin − home_adv)/tau`, averaged. This is the
same quantity the ridge computes once a graph exists; it just substitutes the
prior for the opponent's strength while the graph is empty. **Measurable** with
the existing harness before it ships.

### D2. RÉSUMÉ — "what have you actually done"  *(does not exist; build it)*

Deliberately **not** predictive, and that is the point. It should be allowed to
say a 0-1 team with a home loss has done nothing yet, because that is true.

```
resume = Σ over matches of  credit(result, opponent_strength, location)
```

with credit rising in opponent quality and in road/neutral difficulty, and going
negative for a loss to a weak team. This is what the selection committee weighs,
which is why `project_field.py` must predict it rather than POWER (R3).

**Validation target is different and must not be AUC.** A résumé ranking is
scored against **what the committee actually did** — `actual_field_2025.json`
and the committee's own published Top 16, both of which we capture.

### D3. What to show

A team row that reads:

```
Texas   POWER #3 (80.2)   RÉSUMÉ #41   FORM 0-1
```

That is the honest answer to Cody's objection: the model thinks Texas is still
a very strong roster (POWER), and that it has accomplished nothing yet
(RÉSUMÉ). Showing only the first is what makes the page feel wrong.

---

## E. What I am NOT proposing, and why

- **A weighted blend of 8–11 components.** Every weight would be invented. The
  roster term was hand-set at 0.15/0.30/0.50/1.00 — all four made the ordering
  worse; the fitted value was 0.09.
- **A CLUTCH, CONSISTENCY or FIVE-SET component.** Measured; they hurt.
- **A recency ramp.** Measured; it does nothing.
- **A "Ranking Lab" with sliders.** Fun, and it would let anyone build an
  ordering with no validation behind it and read it as authoritative. Possible
  later *if* each preset is scored and the score is shown beside it.

---

## F. Order of work

1. **Make the Rankings tab move.** Use the Digby blend for all 348 teams instead
   of the frozen projection. Fixes B1, the actual complaint. *(no new maths)*
2. **Opponent-adjust the season term** (B2), measured before shipping.
3. **Re-fit k** from 13.5 toward the measured 25, or state why not.
4. **Build RÉSUMÉ** (D2) and show it beside POWER.
5. Only then revisit availability (B5) as a rating input.
