<!-- READ-FIRST.md -->
# Latest review — B024 and research readiness
2026-09-26. READY FOR OUTSIDE RESEARCH, not implementation.
Read this status and TECHNOLOGY-RESEARCH-SCOPE before earlier review notes. B024 supersedes the outstanding flag-documentation issues in the B023 review: source and syntax flags are now distinct, and aggregate scopes are explicit. Reviewer verified709rows and scopes611match/45partial/31season/22weekend;510candidate rows,199noncandidate. Builder documents218rows with source flags. Candidate does not mean validated: no game-id joins and unresolved alias/quality issues.
Known remaining limitation: scope is per post; a mixed post can include a weekend-total segment under match scope.510 is a preliminary filter count, not510 usable match observations. Row-level segment scope and completeness/correction handling must be resolved before analysis. This is adequately disclosed for outside research and does not require another Builder cycle now. Capture remains private and unused by POWER; no recurring acquisition installed.
Earlier B022 methodological review still applies: weak tested gains do not rule out richer analytics; preserve exact live baseline in any diagnostic; separate changes to calibration population and scale; inventory is grouped not exhaustive-field certification. Tests on start-time/TV changes remain unresolved unless a newer handoff establishes otherwise. No live changes/commit approval.
Cody has NOT yet submitted outside research; mail026 was sent and B024 acknowledged. New scope asks every researcher for evidence-based current technology/API/data/workflow ideas as well as volleyball modeling. No purchases, installations, account access, product migrations or implementation authorized.


<!-- TECHNOLOGY-RESEARCH-SCOPE.md -->
# Technology and data-source research — required companion track
Cody's explicit request,2026-09-26: every outside research model should investigate products, systems, setups, APIs and services that could help this volleyball project and contribute fresh ideas, not stay inside the current design. His pasted Gemini product comparison is an UNVERIFIED starting prompt, not authoritative product documentation or a chosen architecture. Do not inherit its ungrounded "Liv" spreadsheet reference as a project fact.

Research both volleyball analytics and enabling technology. Cover, where useful:
- ChatGPT/Codex, Claude/Claude Code, Gemini/Google developer tools, Grok and other research/coding assistants; open-weight local models and workflow orchestration.
- Official/public/licensed sports feeds, school sources, play-by-play, passing/video/stat coding tools, academic/open-source volleyball packages, data validation and provenance.
- Browser tools, permitted APIs/exports, document/OCR extraction, human review queues, durable snapshots, observation timestamps and incremental updates.
- Storage and analytics: present-file approach versus databases/query tools, reproducible research and experiment tracking. Assess migration benefit and maintenance, don't prescribe a rewrite.
- Team/player analysis visualization, authenticated hosting/admin access, reliable background execution, report delivery and notifications. Personal accounts remain isolated.
- News/newsletters/social discovery with source verification; news tools do not replace authoritative scores/statistics. Passing source automation must use independently authorized access, never bypass Reviewer's site restriction.

For EACH recommendation provide:
1. Exact product/service/feature name, vendor, official source links, verification date and applicable plan/region/platform.
2. Concrete volleyball use case and which current gap it addresses.
3. What it actually provides: consumer app, coding agent, connector, developer API, data license, hosting, or local runtime. Do not conflate these.
4. Access requirements, permissions, automation limits, usage/rate limits, source coverage and reliability; distinguish verified capability, marketing claim and inference.
5. Separate subscription and API/data costs. Estimate incremental cost under an explicit workload, maintenance and privacy implications. Don't imply paid APIs are included in chat subscriptions unless verified.
6. Fit with existing repo/data/workflow; smallest reversible experiment, success criterion, fallback and dependencies.
7. Rank TRY NOW / RESEARCH NEXT / LATER / NOT WORTH IT with reasons. Include existing tools/no-new-purchase baseline and alternatives, not an affiliate shopping list.

Avoid unsupported universal model rankings or stale model names/context-window figures. Verify current product capabilities from official documentation. A large context window does not establish accurate ingestion, automated synchronization or permission to retrieve data. Do not assume a social-search product provides a complete real-time social feed/API.

Deliver one research document with sections: conclusions; volleyball-model evidence; data opportunities; technology/options matrix; costs/access; proposed small trials; disagreements/unknowns; source list. Novel ideas are welcome but every implementation remains proposed until joint review.


<!-- REVIEWER-ADDENDUM.md -->
# Reviewer addendum — read before outside research
2026-09-26. Verdict: usable for outside research with these qualifications; NOT production approval or an independent reproduction of every reported experiment/count.

## What was reviewed
Read B022 and packet narrative, checked inventory structure (88 rows,16columns), ZIP manifest (4files), and consistency with our recorded discussions and prior audit findings. No model/code changes or experiments performed. Live files may continue changing; packet counts represent Builder's stated snapshot, not a transactional capture of all data.

## Corrections / qualifications
1. The limited box-score experiments do not prove that component metrics carry no additional predictive information, or that all useful signal is already in margin. Tested candidate formulations mostly failed to demonstrate incremental value; alternative features, interactions, opportunity/role treatment and data quality remain open research questions. C2 is Builder's proposal, not a settled veto on Cody's richer-system goal.
2. The hitting-weight experiment used the same floor but a DIFFERENT prior blend k (13.5 vs live10). Therefore "validated as shipped" is too broad. The floor behavior was present in that experiment; the complete current configuration was not established by that receipt alone.
3. C1 currently changes both scale and calibration population relative to live. Preserve an exact current-model baseline; separate population change from scale change (or explicitly label a combined candidate). Recompute the unfloored scale on any changed population:0.0668 was calculated from the existing calibration population, not demonstrated for a newly restricted sample. Do not hard-code it as the new population estimate. No experiment is authorized by this review.
4. Brier0.172 and0.129 are different evaluation quantities, not accuracy percentages. Builder reports the site uses an inappropriate comparator; correction is proposed and held, not verified repaired. Retrospective comparisons need matched forecast targets/horizons and data splits.11,284 forecast observations may include repeated target matches across checkpoints; do not call them11,284 independent matches without checking.2026 recorded-score count alone does not prove each prediction predates the match.
5. Historical data reuse constrains clean validation, but "the rest of2026 is the only possible out-of-sample evidence" is too absolute; other genuinely untouched future data could qualify. Venue fields missing in existing2025 files does not establish historical venue information is impossible to recover. Neither claim authorizes new collection.
6.88 inventory rows are grouped datasets/field groups, including derived and unavailable entries, not proof of an exhaustive raw-field schema or88 independent feeds. Some counts are documented rather than remeasured, per B022. Column latest_observation sometimes contains event dates despite absent fetch timestamps; distinguish event date, fetch/observation timestamp and inventory audit time. No false timestamp precision.
7. Page1 passing export establishes3 original reports;31page pagination does not establish complete match coverage. Cody suspects Volleymetrics is the upstream source and may be access-limited; unverified. Need grading definitions, count meanings, coverage and authorized access/export before modeling. User-provided files can be processed; restricted forum access must not be bypassed.
8. Small wording correction: our blocked attack may be credited as their block AND our attack error. Their attack blocked by us is their attack error. Maintain team orientation to avoid duplicated point accounting.

## Product priorities retained
All10metrics remain candidates for team/player explanation AND research into prediction; no fixed weights approved. Track interactions, opportunity, role, availability and uncertainty; roster position is not rally location. Stanford setter case study remains a hypothesis to revisit. Team analysis and valid forecasts are complementary goals.

## Operational holds
Start-time/TV work remains uncommitted; five earlier checks remain unresolved. Drift is Builder's hypothesis, not a confirmed explanation. No POWER change, commit/push, new service/crawler, or email authorized here. Source files in repo root have not been moved or published by Reviewer. No implementation until Cody returns research and all agree a plan.

## Suggested outside-research request
Read START-HERE, this addendum, the current-model document, discussion/proposals and inventory. Challenge assumptions rather than endorse existing conclusions. Research NCAA women's volleyball approaches to team strength, component interactions, opportunity-adjusted/player-role analysis, serving rally-win rates, passing/set-quality data and availability. Identify accessible primary sources and definitions; distinguish demonstrated findings from hypotheses. Propose a small staged plan with chronological validation, exact baselines, uncertainty and missing-data handling. Return one research file with recommendations, counterarguments, source links and explicit questions for Cody/Reviewer/Builder. Do not assume missing fields or unavailable licensed data can be obtained. Do not choose weights to make particular rankings look right.


<!-- START-HERE.md -->
# POWER research packet — start here
Prepared by the Builder (Claude Code), 2026-09-26, for Cody and outside research.
This packet stands alone: everything needed is inline. No local files, logins or earlier conversations are required.

## Executive summary (plain English)
1. **What POWER is today.** It is a strength rating for all 348 NCAA D-I women's volleyball teams, answering "who would win a match". Each team's rating mixes two things:
   - a **preseason projection**, built from last season plus roster changes;
   - **this season's results**, where each match counts as the point margin per set plus a small (25%) hitting-efficiency signal, both judged against how strong the opponent is.

   As teams play more, results count more. At 11 matches, results are 52% of the rating. It is shown on a 0–100 scale: 50 is an average team, and each 12.5 points is one standard deviation.
2. **What it is not.** It is not a résumé or selection ranking. "Who has earned a bid" is a separate product (RÉSUMÉ, ranked by RPI).
3. **How well it predicts.**
   - 2025 held-out forecast Brier score: 0.172.
   - 2026 so far: Brier 0.180; the favourite won 73.2% of 2,088 scored matches.
4. **What we learned from testing richer models.** Box-score stats (hitting, receiving, serving) mostly **explain** a team without adding much **prediction** beyond point margin. The one box channel in use (hitting) adds a small, statistically clear gain. A richer candidate model was **not distinguishable** from the current one on 2025.
5. **Verified issue.** The hitting signal's scale is set by a safety floor, not by the data: 0.100 is used where the measured value is 0.067. It was tested and shipped in that state, so it is not a bug in what was validated. It is a question to settle with one small, focused check before touching the hitting channel.
6. **Direction Cody set.** Build a **team analysis page** that tells the story of a season through ten metrics, with player, role and availability context. This is explanation, which does not require every stat to earn a rating weight.
7. **Passing grades.** A community passing-grade thread exists on VolleyTalk. Cody had it read in his own browser on 2026-09-26 and it has been quality-reviewed.
   - **Captured:** 709 rows (0–3 scale) from 59 posts. After the quality review, 510 rows from 27 posts are single-match "candidates", and even those are not joined to games yet.
   - **Problems found:** 53 rows are weekend or season totals. Posts themselves admit wrong players, partial matches and changed grading. "Good pass" is never defined.
   - **Status:** stored privately and kept out of POWER. See DISCUSSION §D UPDATE.

## Live vs research vs proposed
| Item | Status |
|---|---|
| POWER blend (preseason + opponent-adjusted margin 75% / hitting 25%, k = 10) | **LIVE** |
| Switch to a pure-2026 rating once teams pass 13.5 matches | **HELD** (Cody, 2026-09-26) |
| RÉSUMÉ (RPI-based) | LIVE, separate product |
| Round-2 candidates (dynamic W/L model; dynamic set-strength + box channels) | RESEARCH: not better / not distinguishable |
| Frozen "M3" shadow model logged daily at 05:45 | RESEARCH, running, no effect on live |
| Ten-metric analysis page, neutral-site handling, component profiles, server rally-win %, passing ingest | **PROPOSED only** (see DISCUSSION-AND-PROPOSALS.md §C) |
| Any weight, cutoff or threshold for the ten metrics | **NONE approved** |

## Reading order
1. **This file.**
2. **CURRENT-MODEL-AND-DATA.md:** the exact calculation, a reproducible example (Kentucky, Texas A&M, Stanford), constants and their sources, the hitting-floor finding, limitations, past experiments, and stale assumptions corrected.
3. **DISCUSSION-AND-PROPOSALS.md:** the complete ten-metric discussion (each labelled as Cody decision, Reviewer suggestion, Builder proposal, unknown or deferred), the Texas 2023 and A&M 2025 champion examples, the Stanford setter reminder, Builder proposals C1–C8, passing-data options, the validation plan, and research questions.
4. **DATA-INVENTORY.csv:** 88 rows covering everything collected, with measured counts. Rows reading "UNAVAILABLE" list what we cannot observe; that means not observed, not zero.

## What to ask outside researchers (short list; full list in DISCUSSION §F)
1. Which public volleyball rating systems use point or set margin and box components? What did each prove on **future** matches?
2. Do serve-pressure or serve-receive metrics predict beyond point margin? How many matches until they stabilize?
3. What are the standard **opportunity** denominators for digs, blocks and kills per set?
4. Is there a **licensed** 2026 rally-level source (server on every rally, rotation, pass grades)? Does the open ncaavolleyballr project publish in-season?
5. How large is the NCAA volleyball home edge, and how do published models handle neutral sites?
6. Who produces the VolleyTalk passing grades, on what scale and by what method? Could the owner provide a structured export?
7. How do champion scoring profiles compare with **non-champions** at the same point of the season?
8. What evidence exists on setter systems and setter changes (5-1 vs 6-2) as predictors? (Stanford is Cody's case study.)

## Revisions and timestamps
- **Code:** git HEAD `5f46398` (2026-09-26). Plus uncommitted start-time/TV display work, which does not change any rating code.
- **POWER artefact:** generated 2026-09-26 23:17:49 UTC; corpus fingerprint `8f59bbd57e9d03d0`; 2,150 counted matches; ratings cut off at 2026-09-26 00:00 PT, plus 77 same-day finals verified by a school.
- **Inventory counts** measured 2026-09-26 evening from local files; no network re-crawl.
- **Constants** are measured on the complete 2025 season (5,131 matches) unless marked otherwise.

## Limitations of this packet
- 2025 has been reused for many design choices, so it cannot validate new ideas cleanly. The rest of 2026, recorded prospectively, is the honest test.
- Game records carry no observation timestamps. Retrospective "as-known-then" reconstructions can leak later corrections. The data has 89 corrections.
- The 12 historical champion PPS values come from Cody's spreadsheet and are not all verified. Texas 2023 and A&M 2025 are verified.
- Passing coverage is unknown, and VolleyTalk access is blocked.
- Five cross-surface count checks failed in the last full test run (the page was a few results behind the live data mid-slate). That is not yet re-verified, and none of those checks touch POWER's formula.

## Approved scope and next action
- **Approved:** documentation and read-only checks.
- **Held:** POWER changes, commits, pushes, schedules, emails and new builds.
- **Next:** the Reviewer checks this packet → Cody takes it to outside research → Cody, the Reviewer and the Builder agree a plan → only then implement.

## Manifest
| File | What it is |
|---|---|
| START-HERE.md | This summary |
| CURRENT-MODEL-AND-DATA.md | Executed calculation, lineage, constants, hitting-floor audit, limits, experiments, stale assumptions |
| DISCUSSION-AND-PROPOSALS.md | 10-metric discussion, proposals, passing options, validation plan, research questions |
| DATA-INVENTORY.csv | 88-row inventory of all collected and derived data, with measured coverage |
| POWER-RESEARCH-PACKET.zip | The four files above, zipped |

**Checks performed:**
- Kentucky, Texas A&M and Stanford scores and POWER values recomputed from the formula: all exact.
- Hitting-scale floor recomputed independently: raw τ² 0.004466 → 0.0668; used 0.100.
- The receipt behind the shipped hitting weight was confirmed to use the same floored helper.
- Inventory scanned for credentials and personal data: none. Contents of the private notes folder were not read.


<!-- CURRENT-MODEL-AND-DATA.md -->
# Current model and data: how POWER is actually computed
Builder, 2026-09-26. Traced from the working checkout (git HEAD `5f46398`, plus uncommitted start-time/TV work that does not touch the rating code). The rating artefact this describes is `data/digby_top25_2026.json`, generated 2026-09-26T23:17:49Z, corpus fingerprint `8f59bbd57e9d03d0`, 2,150 counted matches, rating cutoff epoch 1790406000 (2026-09-26 00:00 PT), plus 77 same-day finals admitted because a school site verified them.

**Status:** this is a description of what runs. It is not a proposal. Nothing here was changed.

---

## 1. What POWER is (and is not)

- **POWER is a strength rating.** It answers "who would win a match tomorrow", and it is driven by **point margin per set** plus a smaller **hitting-efficiency** signal. Each is judged against the opponent faced, and both are blended with a **preseason projection**.
- **POWER is not a résumé rating.** "Who has earned an NCAA bid" is a separate product, RÉSUMÉ, which is ranked by RPI (see §8). The project keeps the two apart on purpose. Measured on 2025: relative to RPI, the strength composite favours teams with *worse* won-lost records (corr −0.205). Using it to pick the field would over-select good-margin/bad-record teams.
- **Every match input is one of:**
  - **observed:** set scores, attack counts, W/L;
  - **inferred:** opponent strength, estimated jointly with everyone else;
  - **assumed/measured constant:** the numbers in §4.

  The packet labels each one.

## 2. Pipeline, raw field to rank

```
ncaa.com (via ncaa-api.henrygd.me)  /scoreboard (fixtures)  /game/{id} (teams, linescores[], location)  /boxscore (team + player counts)
      │ crawl_2025.py / crawl incremental → data/raw/2026/games.jsonl (append-only), boxscores.jsonl, playerbox.jsonl
      ▼
season_counts.countable()  — which finals count (below)
      │ + result_corrections.json, duplicate_listings.json, exhibitions.json (cited, append-only ledgers)
      ▼
build_dataset.py → data/data_2026.json
      ▼
digby_top25.py  → blended z-score per team (this document)
      ▼
build_rankings_board.py → POWER 0–100, rank, weekly-lock movement
      ▼
predict_2026.py / simulate_season_2026.py (forecasts, season sims) — consume the same blended score
```

### Which matches count (`scripts/season_counts.py`)
A match feeds POWER only when all of these hold:
1. It is final (`game_state == 'F'`).
2. Both teams are Division I. 2026 membership comes from live division flags; 2025 membership comes from the archived official RPI table (348 teams).
3. It has a set line.
4. It is not a ledgered exhibition or duplicate listing.
5. It is not "held". Held means one of:
   - an empty final;
   - a self-contradictory final, where the set line names one winner and the flag names another;
   - a winner credited with more than 3 sets;
   - a result under review.
6. It passes the **trust cutoff** (`rating_input_ok`): the match started before today's midnight-PT boundary, **or** a school site has verified the result today.

Some held finals are corrected rather than dropped: 30+ ledgered result corrections are applied first (`apply_correction`). The winner always comes from `winner_index()`: exactly one winner flag decides; otherwise the side with 3 sets wins; otherwise no winner, and the match counts nowhere.

**The start time matters here.** It sets the day a match belongs to and the cutoff. So a start-time correction can in principle move a match across the midnight-PT boundary.
- Today's one correction (Creighton at St. John's, gid 6624495) moved 21:00Z → 23:00Z. Both are 2026-09-26 in Pacific time, so no cutoff or day changed.
- The earlier Builder note B021 said "POWER unaffected" as a general claim. That was too broad and is corrected here.

## 3. The calculation, step by step (`scripts/digby_top25.py`)

**Per-match evidence.** For each counted match, team *i* vs opponent *j*:

- Margin per set: `m = (points_i − points_j) / sets`. This comes from the set-by-set linescores, so it counts **scoreboard** points, including opponent errors. It is **not** "earned points (kills+aces+blocks)".
- Margin-implied strength: `m_impl = z_opp + (m − h·H) / τ`
  - `H` = +1 if *i* is the nominal home team, −1 if away. **Neutral sites are not detected here**, so every match carries a home term.
  - `h = 1.0878` pts/set, the home edge measured on 2025.
  - `τ = √5.941 = 2.437` pts/set, the between-team spread measured on 2025.
- Hitting-implied strength, used when both teams' box scores carry attack counts: `h_impl = z_opp + (Δhit − h_hit·H) / τ_hit`
  - `Δhit = (K−E)/TA` for team *i* minus the same for *j*, from that match's team totals.
  - `h_hit = 0.0292`.
  - `τ_hit = 0.100` (see §5 on the floor).
- Evidence for the match: `0.75·m_impl + 0.25·h_impl`, or `m_impl` alone when no box score exists.
- Season term: `season_z_i` = the plain mean over *i*'s counted matches.

**Opponent strength (`z_opp`).**
- Opponents are scored at their **current blended** rating, not their preseason one.
- This is a fixed-point iteration: start from the preseason z, then re-score 4 times (`OPP_ITERATIONS = 4`).
- An opponent missing from the preseason table contributes no evidence for that match.
- This is a joint inference, not a measured stat: "how good was the team you beat" is estimated from everybody's results at once.

**Preseason prior (`preseason_z`).**
- Source: `data/projection_2026.json` → `blend`, z-scored across all 348 teams.
- The projection is built pre-season from 2025 results, 2026 rosters × 2025 per-player production (roster-delta weight 0.0565), and a churn term (weight −0.1304). Churn is the share of last season's production that did not return to D-I.
- Out of sample (2024→2025), the projection predicts the next season at rho 0.8379.

**Blend.**
- Weight on this season: `w = n / (n + k)`, where `n` = counted matches.
- **`k = 10`**, adopted from the receipt `data/forecast_blend_k_2025.json`:
  - pooled AUC: k10 0.8226 vs derived k=13.52 0.8211;
  - Δ +0.00147, CI [+0.00096, +0.00194].
- The **derived** k = σ²/(τ²(1−ρ²)) = 23.929 / (5.941·(1−0.8379²)) = 23.929 / 1.770 = **13.52**.
  - It is kept as `k_crossover`, the gate for switching the board to a pure-2026 rating.
  - **That switch is HELD by Cody's decision of 2026-09-26.**
- Score: `score = (1 − w)·preseason_z + w·season_z`

**POWER scale** (`build_rankings_board.py`):
- `power = clip(0, 100, 50 + 12.5·(score − mean)/sd)`, where the mean and sd are taken over all 348 teams. Today: mean −0.00029, sd 1.19381.
- 50 is an average D-I team; each 12.5 is one standard deviation. Rank = order of `score`.

### Reproducible example (real rows, today's file)

| Team | n | preseason_z | season_z | w = n/(n+10) | score | POWER |
|---|---|---|---|---|---|---|
| Kentucky | 11 | 2.538 | 3.293 | 0.5238 | 0.4762·2.538 + 0.5238·3.293 = **2.9335** | 50+12.5·(2.9335+0.00029)/1.19381 = **80.7** |
| Texas A&M | 11 | 2.076 | 2.411 | 0.5238 | **2.2515** | **73.6** |
| Stanford | 11 | 2.250 | 1.968 | 0.5238 | **2.1023** | **72.0** |

All three reproduce the stored `score` exactly. Stanford's season evidence (1.968) is *below* its preseason (2.250), so results are pulling it down. At 11 matches, results carry 52% of the weight.

## 4. Constants and where each comes from

| Constant | Value | Source / status |
|---|---|---|
| σ² per-match margin variance | 23.929 (sd 4.89 pts/set) | measured on 2025 (teams ≥ 8 matches) |
| τ² between-team variance | 5.941 (sd 2.437), de-noised | measured on 2025 |
| ρ prior accuracy | 0.8379 | measured OOS 2024→2025 (`churn_fit.json`) |
| k blend | 10 (derived 13.52) | 10 adopted from receipt; derived kept as crossover gate |
| Home edge, margin | 1.0878 pts/set | measured on 2025, nominal home flag |
| Home edge, hitting | 0.0292 | measured on 2025 |
| τ_hit hitting scale | 0.100 | **floor-bound, see §5** (raw measured 0.0668) |
| Hitting weight | 0.25 | measured: 2025 walk, Δ AUC +0.00060, CI [+0.00030, +0.00089] (receipt run at k=13.5) |
| OPP_ITERATIONS | 4 | stated convergence choice |
| MIN_MATCHES (variance measurement) | 8 | stated choice, only for measuring variances |
| POWER scale | 50 + 12.5·z | display convention, not a model parameter |

**Forecast mapping** (`predict_2026.py`), which is separate from the ranking:
- Home margin in pts/set = `3.05 × (score_home − score_away) + 0.2675` (the home term is 0 at a neutral site).
- That margin goes through the calibrated rally model (`simulate_2025.match_dist`) to get match win odds and 3-0/3-1/3-2 splits.
- The scale 3.05 was fitted on even 2025 checkpoints and scored on odd ones: held-out n = 11,284, Brier 0.1718, reliability within ~1.5 pts per decile.
- **2026 live record:** 2,088 scored, Brier 0.1796, favourite correct 73.2%.

**Season simulator** (`simulate_season_2026.py`):
- Uses the same blend; per-team strength is redrawn each iteration with an SD that narrows as matches accumulate.
- Receipt `sim_blend_2025.json`: win-total MAE 2.64 → 2.01 vs prior-only, CI of improvement [0.53, 0.74]; 80% band coverage 0.869.

## 5. Verified issue: the hitting scale is set by a floor, not by data

- `variance_components()` computes τ² = var(team means) − σ²/n̄ and floors it at **0.01**. The floor was written for **points-per-set** units, where τ² ≈ 5.9 and it never binds.
- `hit_scale_2025()` reuses the same helper in **hitting-efficiency** units. Recomputed today:
  - 349 teams with ≥ 8 matches, 5,131 matches;
  - σ²_hit = 0.0196, n̄ = 29.25;
  - raw de-noised τ²_hit = **0.004466**, so τ_hit = **0.0668**;
  - the floor lifts it to 0.01, so **0.100** is used.
- **Effect:** each match's hitting evidence is divided by 0.100 instead of 0.0668. The channel's per-match signal is therefore about **0.67×** what a strictly measured scale would give, and its effective influence is below its nominal 0.25 weight.
- **Consistency:** the experiment that justified 0.25 (`measure_blend_hiteff.py` → `blend_hiteff_2025.json`) calls the same helper. So it validated the model **as shipped, floor included**. Changing only the floor would move the channel to an untested strength of about 1.5×.
- **Other caveats found while tracing:**
  - `hit_scale_2025()` reads **all** 2025 finals in `data_2025.json`, not the `countable()` D-I set. That is why the count is 349 teams (including the non-D-I opponents); the margin side uses the countable set.
  - The receipt ran at k=13.5 and live runs at k=10. The combination was never re-measured together.
- **Proposed focused diagnostic** (not run, not approved): re-run the 2025 hitting-weight walk at k=10 with τ_hit ∈ {0.0668 measured, 0.100 current}, restricted to the countable D-I set, reporting paired AUC/log-loss deltas with CI. That is a 2-arm check, not a grid. Details are in DISCUSSION-AND-PROPOSALS.md §C1.

## 6. Other known limitations of the live model (not fixed)

- **Margin is scoreboard points,** so it includes points the opponent gave away through errors. That is deliberate: it is a win/strength signal. Earned points (K+A+B) are displayed separately and are not in POWER.
- **No neutral-site handling** in the rating's home term: every match has a nominal home team. Venues are stored in 2026 but not used here.
- **Box-score coverage** decides whether the hitting channel fires for a match. Without both teams' attack counts the match is margin-only.
- **Availability is not an input.** A sourced injury never changes a forecast or POWER, and every forecast surface says so.
- **Schedule-strength early in the season** leans on the preseason prior for opponents. The 4-pass iteration only has a schedule graph to work with once teams have played connected opponents.
- **Post-hoc corrections:** the data carries 89+ result corrections but no observation timestamps. So a strictly "as-known-then" reconstruction of past rankings is not possible from the log alone. That is a leakage risk for any retrospective study (see Round 2 below).

## 7. Research results already on record (do not re-run blindly)

| Question | Result | Receipt |
|---|---|---|
| Opponent-adjust the season term | +0.021 AUC at the shipped k, CI clear of zero | `blend_k_2025.json` |
| k = 10 vs derived 13.52 | k10 better, Δ +0.00147 AUC, CI clear | `forecast_blend_k_2025.json` |
| Hitting channel 0.25 | Δ +0.00060, CI [+0.00030, +0.00089]; hit-only worse than margin | `blend_hiteff_2025.json` |
| Serve-receive channel (reception errors) | mix 0.25 inconclusive (Δ +0.00006, CI [−0.0006, +0.0007]); mix 0.50 HURTS (Δ −0.0033); receive-only HURTS (Δ −0.027); not shipped | `blend_recv_2025.json` |
| Opponent re-scoring at current strength | AUC −0.00035, CI [−0.0009, +0.0002]: no accuracy change; shipped for interpretability | `blend_upgrades_2025.json` |
| Margin caps ±8/±10 | inconclusive-to-negative, refused | `blend_upgrades_2025.json` |
| Early-season bake-off (net pts/set vs RPI vs TCV vs hitting diff) | opponent-adjusted hitting diff strongest single factor over a full season; margin better early | `bakeoff_2025.json` |
| **Round 2 (2025, 3,470 test matches, 7-day rolling blocks)** | A_clean log loss (cal) 0.4667; **B** dynamic Bradley–Terry W/L only 0.4809, worse (Δ −0.0142, CI [−0.0233, −0.0051]; grid-edge constrained, so maybe under-tuned); **C** dynamic set-strength + 4 box channels 0.4640, Δ +0.0027, CI [−0.0073, +0.0117], **not distinguishable**; hitting 0 vs 0.25 no measurable difference in that harness | `Cody/coordination/research/prototype/round2_2025.json` |
| Round 2 (2026, 2 blocks) | exploratory only: A_ref 0.4511, C 0.4557 | `round2_2026.json` |

**Round 2 labelling:**
- "A_clean" is a **partially refit development baseline**: the forecast scale 3.05, k and the hitting weight were all informed by full-season 2025, so it is not a fully clean held-out model.
- "Late/post" in Round 2 means Nov 21–Dec 21, not postseason only.
- Parity with production was checked at **one** cutoff (346/346 teams within 1e-3). That confirms the slice, not universal fidelity.

## 8. The other rankings on the page (how they differ)

- **RÉSUMÉ** (`resume_2026.json`): ranked by our RPI (25% W% / 50% opponents' W% / 25% opponents' opponents' W%, D-I only, unweighted), plus a WAB readout.
  - Validated against the 2025 committee's 64 picks: 5-fold CV AUC RPI 0.9215 > WAB 0.9107 > POWER 0.9071. Every blend was worse, so nothing is blended.
  - Active once there are ≥ 200 D-I matches; 2,174 now.
  - Circularity caveat stated: the committee itself looks at RPI.
- **AVCA Top 25:** the coaches' poll, captured weekly (the ncaa.com rankings endpoint is current-only). Receiving-votes teams come from the AVCA workbook.
- **VolleyTalk room poll** (private build only) and **Massey / FIGstats** (browser-captured external references, never inputs).
- **Official NCAA RPI:** captured when published. The 2025 final table is archived and irreplaceable.

## 9. Stale assumptions found in earlier briefs and in code comments

1. **k in the `digby_top25.py` docstring** says "k = 4.03 matches … one match moves a team 20%". That is superseded twice: derived 13.52, live 10.
2. **`prediction_score_2026.json` `brier_reference`** says "this model backtested at 0.1289 on 2025". 0.1289 is the **rally simulator scored on the true margin**. The comparable held-out forecast Brier is **0.1718**. The page's reference line compares unlike quantities.
3. **"Hitting scale = measured historical spread."** It is floor-bound (§5).
4. **"POWER unaffected by a start-time correction"** (B021): too broad; see §2.
5. **The earlier Reviewer framing** that the 0.100 hitting SD was measured spread is corrected in Reviewer mail 020 and confirmed here.

## 10. Data inventory, explained

`DATA-INVENTORY.csv` in this packet lists every dataset and field group collected, not just the ones POWER uses. It gives source, units, seasons, refresh, latest observation, measured counts, missing/zero semantics, quality constraints, current uses and prospective uses. Rows marked UNAVAILABLE are data we do **not** have: structured pass quality, set location, block touches, coverage, 2026 server identity on every rally, and injury causes. A missing value there means "not observed", never zero.

**Conventions every consumer follows:**
- Team blocks = solo + ½ assists.
- Hitting % = (K−E)/TA from summed counts, never an average of match percentages.
- Per-set rates divide by the **match's** sets, never the sum of players' sets.
- The feed's player `points` column and team `totalBlocks` column are unreliable and unused.
- A box score marks a did-not-play as a listed line with every stat zero, not a missing row.
- A 2024 box score lists more bench players than a 2025 one.
- Non-final records never count.
- 2025 D-I membership comes from the archived official RPI table.


<!-- DISCUSSION-AND-PROPOSALS.md -->
# Discussion and proposals: the 10-metric pass, context, and a validation plan
Builder, 2026-09-26. This file separates five kinds of statement, and the labels are load-bearing:

- **[CODY DECISION]:** something Cody has said or decided.
- **[REVIEWER SUGGESTION]:** framing from the Reviewer seat (ChatGPT).
- **[BUILDER PROPOSAL]:** my proposal. Nothing here is approved, and no live change has been made.
- **[UNKNOWN]:** not established.
- **[DEFERRED]:** agreed to revisit later.

**Status:** research preparation. No numerical weight, threshold, cutoff or model change is approved by anything in this file. Live POWER is held. The decision gate: Cody brings outside research back, then Cody, the Reviewer and the Builder agree a plan, and only then does anything get implemented.

---

## A. Product direction [CODY DECISION]
The statistics together should tell the story of a match, a season and possible future performance. A single margin-led rating does not give that explanation. The eventual goal is a **team analysis page** showing:

- team and player metric histories;
- component breakdowns;
- trends, outliers, improvement and regression;
- availability and lineup context;
- counts and sample sizes kept visible.

**Descriptive value is not predictive value.** A stat can belong on the analysis page without earning a weight in the rating. [REVIEWER SUGGESTION, accepted]

Four products that are related but distinct: [REVIEWER SUGGESTION]

1. Next-match win probability.
2. Current team strength (POWER).
3. Season accomplishment (RÉSUMÉ/RPI).
4. Explanatory team analysis.

Each metric below should say which of the four it belongs to.

## B. The ten metrics (the complete initial pass)

General rules:
- Season rates always come from **summed counts**, never from averaging match percentages.
- Metrics that overlap algebraically are never added as separate bonuses:
  - kills/set = attempts/set × kill%;
  - hitting% = kill% − error%;
  - earned points = kills + aces + team blocks;
  - an opponent's blocked attack is also recorded as our attack error.

### 1. Earned points per set (PPS)
- **Definition:** (kills + service aces + team blocks) ÷ sets, where team blocks = solo + ½ assists (the NCAA convention). It measures credited scoring production, not scoreboard points.
- **Status:** [CODY DECISION] liked it and endorsed it for descriptive analysis; no weight approved.
- **Champion reference** (Cody's historical sheet, 2013–2024, plus verified Texas A&M 2025): 13 seasons, mean 18.69, median 18.68, range 18.03–19.295.
  - The 12 historical sheet values have **not all been verified** against original sources.
  - Texas 2023 is independently verified at 18.03 (18.02632).
- **Not a cutoff.** 18.288 was the earlier mean − 1 SD, not the minimum. These are reference values, not prerequisites.
- **Before claiming it discriminates champions,** compare them with non-champions at matched season dates. October snapshots are not comparable with complete seasons. [REVIEWER SUGGESTION]
- **Worked examples:**
  - **Texas 2023** (official stats; 32 matches, 114 sets, 2,055 points): season 18.03; equal-match mean 18.13; median 18.42; population SD of match PPS 1.76; slope +0.06 per match (R² 0.10); NCAA tournament 17.96 vs rest 18.04 (no tournament surge). Components K/S 13.42, aces/S 1.72, blocks/S 2.89. The final had 12 aces in 3 sets (4.0 per set): a component surge the composite hides.
  - **Texas A&M 2025** (supplied PDFs; 33 matches, 118 sets, 2,180.5 points): season 18.48; equal-match mean 18.54; median 18.75; SD 1.98; slope +0.041 (R² 0.04); thirds 18.19 / 18.05 / 19.21; NCAA 19.35 vs rest 18.27. It **won the final at 16.67 PPS**, and won 10 of its 13 matches below 18. Components K/S 14.54, aces/S 1.33, blocks/S 2.61; kills were 78.7% of credited points.
  - Both examples: slopes are against match number, unadjusted for opponents; SDs are over match averages. **Neither shows steady improvement, and neither is a rule.**

### 2. Opponent points per set
- **Track both:**
  - all scoreboard points allowed per set (the total cost);
  - opponent earned PPS (their K+A+B), which decomposes opposing production.
- **Opponent earned PPS is not isolated defence.** [REVIEWER SUGGESTION]
  - Their aces reflect our reception.
  - Their blocks reflect our set and attack quality, and our coverage.
  - Their kills reflect our serve, block and floor defence.
- **Errors overlap with scoring events,** so categories must not be summed into a ledger. Example: A&M 18.48 vs opponents 14.42 is a 4.06 credited-point edge, not the scoreboard margin.
- **[CODY DECISION] context:** trapped, tight or off-net sets, bail-out attacks and uncovered blocks cause opponent blocks. **Block totals cannot assign blame.** That needs rally, video or tagged evidence. [UNKNOWN in our data]

### 3. Kill percentage
- **Definition:** kills ÷ attack attempts.
- **Example:** 40 kills in 100 attempts is 40% whether errors were 10 or 20.
- **Pair with** error rate, attempts per set, attack distribution and opponent defence.
- [CODY DECISION] accepted this framing.
- **Status:** the team figure is shipped as a displayed stat (Stats: Team offense, the dossier, recaps). It is not in POWER.

### 4. Hitting efficiency and player context
- **Definition:** (K − E) ÷ TA. Two different profiles can give the same number: 40K/10E/100 and 50K/20E/100 are both .300, one lower-risk and one higher-termination. Keep kill%, error%, attempts and efficiency visible together.
- **[CODY DECISION] break down by player, own baseline and role:**
  - middle, outside, opposite, back-row;
  - middles tend to get better-system balls, while outsides carry bail-out swings.
- **Limits:** [REVIEWER SUGGESTION]
  - Roster position ≠ actual attack location.
  - Box scores can't show pass or set quality, or system status.
- **Availability:** track verified absences and replacements, and the resulting shifts in workload, production and margin.
  - Missing from a box score ≠ injury.
  - Margin change during an absence is association, not causal impact.
- **This is in POWER:** the only box-score channel, at weight 0.25. See CURRENT-MODEL §5 for the scale floor.

### 5. Kills per set
- Separate **more opportunities** from **better termination**. Show attempts/set, kill rate and share of team attacks.
- Sets played ≠ court exposure (rotations).
- [CODY DECISION] accepted, for the most part.

### 6. Assists per set; setter evaluation [DEFERRED]
- **What it measures:** assists are credited kill-producing sets, not setting quality. A great set the opponent digs earns no assist; a bad set salvaged for a kill earns one.
- **Connect with** team kills, non-setter second balls, setter changes, and 5-1 vs 6-2 workload. (5-1 vs 6-2 is already detected for 253 teams from starting lineups.)
- **[CODY DECISION]** He has observed rough setting this season, which he believes limits some teams. **Stanford is his named case study.** This is recorded as his **observation/hypothesis, not a verified finding.**
- **Reminder** when setter, set-location or lineup work resumes: use Stanford.
- No setter adjustment is approved.

### 7. Digs per set
- Opportunity-dependent. High digs can mean good defence, or recycled rallies from failing to finish.
- **Connect with** opponent attack volume and kill%, own blocking, and transition.
- Dig quality is not in box scores.
- [CODY DECISION] accepted; no dig bonus.

### 8. Blocks per set
- **Scope:** team scoring blocks per set (BS + ½BA); individual participation kept distinct; blocks per opponent attempt as an opportunity measure.
- **What it misses:** touches and funnelling. A low stuff count does not prove bad blocking.
- [CODY DECISION] no additions.

### 9–10. Serving: aces per set, service errors per set, per attempt
- **Error rate:** service errors per serve attempt complements errors per set. Pair errors with aces.
- **[CODY DECISION] extension:** the team's rally-win % while player X serves = rallies won by the serving team ÷ that player's serves.
  - **Service errors are included in the denominator.** Example: 20 wins from 50 serves = 40%; 2 aces = a 4% ace rate, already inside the 20.
  - Label it as the team's point-winning % while she serves, **not** isolated server quality. The block, the defence and opponent errors all contribute, and a server's usual rotation confounds comparisons.
  - Service runs are not independent observations.
- **Pressure measures** (accepted for research *if the data supports them*): opponent first-attack kill rate, and middle availability after a serve.
- No universal ace-to-error threshold and no risk/reward weight.
- **Data reality:** see §D.

### Metrics that exist in our data but were not in the ten
- Reception errors and reception attempts (team box score).
- Serve attempts.
- Set-1 starting six, 2025 serving rotations (from play-by-play) and substitution pairings.
- Returning production and churn.

## C. Builder proposals (independent; each needs Cody's approval)

### C1. Settle the hitting-scale floor with a two-arm check before anything else touches the hitting channel
- **What:** re-run the 2025 checkpoint walk at the **live k = 10** with τ_hit = 0.100 (current, floor-bound) vs 0.0668 (measured).
  - Use the countable D-I set only, matching the margin side.
  - Report paired Δ AUC, Δ log loss and Brier, with bootstrap CI.
  - Two arms, no grid.
- **Why:**
  - The shipped weight was validated with the floor in place and at k=13.5, and the live model runs at k=10.
  - Nobody has measured the combination actually running, or the unfloored scale.
- **Possible outcomes:**
  - the floor is harmless → document it and keep it;
  - the measured scale helps → propose that change with its receipt;
  - it hurts → keep 0.100, and **name it as a regularizer** rather than a "measured spread".
- **Risk:** low; the check is read-only.

### C2. Keep POWER's predictive core small; put the ten metrics on the analysis page first
- **What:** build descriptive team and player histories for all ten metrics before any metric gets a rating weight. That means season and rolling values with counts, opponent context, and role splits.
- **Why:** every box-score channel tested so far added little or nothing over margin in prediction:
  - hitting +0.0006 AUC;
  - receive inconclusive or harmful;
  - Round-2 C not distinguishable.

  That does not make the stats uninformative. It says their predictive signal is **mostly already inside the margin**. Their explanatory value is real and belongs on the page. This is Cody's product goal and does not need a weight.
- **Alternative:** add them to POWER now. Rejected: no evidence that it helps, and it risks double-counting.

### C3. If richer prediction is still wanted, test ONE pre-registered candidate prospectively
- **Candidate:** Round-2 C (dynamic set-strength + 4 lagged box channels), or margin + opponent-adjusted component differentials (serve pressure, first-ball side-out proxies). Frozen before the rest of 2026.
- **Protocol:**
  1. Write the spec before seeing results.
  2. Record predictions pre-match in an append-only log with IDs.
  3. Score on log loss (primary), Brier, calibration slope and intercept, and a block bootstrap.
  4. Report by subgroup: early/late, conference/non-conference, missing-box matches, neutral sites.
- **Promotion rule:** stated in advance as "CI of the paired log-loss delta clear of zero over at least the remaining regular season". **The threshold is Cody's decision, not mine.**
- **Why:** the 2025 data has been reused so often it can no longer validate anything new. The rest of 2026 is the only genuinely out-of-sample evidence available.

### C4. Neutral-site handling in the home term
- **What:** use stored venues (derived home venue + the fixture ledger) to set H = 0 at neutral sites. 2026 has venues; 2025 does not.
- **Why:** showcase and tournament matches currently credit a home edge nobody had. The home edge is ~1.09 pts/set, about 0.45 τ, which is not trivial for a strength rating.
- **Validation:** only on 2026, prospectively. There are no 2025 venues to backtest with. This is a **known-wrong assumption we can fix** rather than a new feature, but it still needs a shadow comparison before going live.

### C5. Opponent-adjusted component profiles (analysis, not rating)
- **What:** for each team, compute each component (kill%, error%, ace/SE per attempt, reception error rate, opponent kill%) relative to what that opponent usually allows or produces, using the same `z_opp`-style logic.
- **Why:** it answers "is A&M's serving good, or did it face poor passers?" That is the explanatory question Cody asks. Present it with uncertainty bands.
- **Risk:** small samples early. Show counts, and shrink toward the league mean with a stated rule.

### C6. Server rally-win % (metric 9 extension): what is possible now
- **2025:** feasible. The ncaavolleyballr play-by-play (MIT; mirrors stats.ncaa.org) names the server on every rally (8,350/8,350 in a sample), and rotations are already derived for 96.5% of set-teams.
  - **Compute:** per-server serves, rallies won, aces, service errors and rally-win %, with the rotation context.
  - **Label:** "team points won while she serves".
- **2026:** **no automated source.** ncaa.com names servers only on aces. StatBroadcast has it, but its terms say "through the web interface" and it 403s tools; we will not automate it.
- **Options for 2026:**
  1. Ask whether ncaavolleyballr publishes 2026 in-season data (it is an outside project; a question to research).
  2. Seek an authorized feed from a data owner.
  3. Show 2026 as UNAVAILABLE.

### C7. Passing grades (see §D for sources)
- **Treat as:** a separate, provenance-heavy table.
- **Never treat as:** set quality or a rating input until the definitions, coverage and grader consistency are established.

### C8. Freshness and "as-known" timestamps
- **What:** add an observation timestamp to every appended game record and correction.
- **Why:** without it no honest retrospective (as-known-then) evaluation is possible, and every backtest on 2026 carries silent revision leakage. **Cheap, and prerequisite for C3.**

### Disagreements and failed experiments to preserve
- **Hitting weight:** it helped in the checkpoint-walk harness (+0.0006 AUC). In the Round-2 rolling harness, 0 vs 0.25 was indistinguishable. Both results stand.
- **Rejected upgrades,** with receipts: receive channel, margin caps, opponent-iteration on 2025, and hit-only.
- **Gemini's analysis of the champion benchmark** read 18.7 as a prerequisite. The Reviewer rejected that framing; the rejection is preserved.
- **B (W/L-only)** was worse in Round 2 but hit grid edges. It is not proof that W/L models are generally inferior.

## D. Passing statistics: source feasibility and automation options

### What exists
1. **VolleyTalk thread "2026 Passing Stats Thread"** (volleytalk.proboards.com/thread/107960). Cody reports 31 pages and believes it covers every match; **unverified**.
   - **Access:**
     - The Reviewer's browser **blocked the domain under a site-safety policy**.
     - Plain HTTP clients receive a proof-of-work bot challenge (measured 2026-08-28).
     - **We do not bypass either.**
   - **Status: ACCESS BLOCKED / UNVERIFIED. It is not an available dataset.**
2. **Cody's supplied exports** (`passing stats/`): a text-extractable PDF of page 1 and two tall screenshots.
   - **Page 1 holds 3 original matchup reports** (Wisconsin–Louisville, Texas–Arizona St., SMU–Texas A&M) plus quoted repeats. Quoted copies must not become new observations.
   - **Report format,** from the first post on 2026-08-23:

     ```
     Wisconsin-Louisville
     Wisconsin 2.36
     Flanagan 2.32 (19)
     Simon 1.96 (12)
     …
     Louisville 1.98
     Kenny 2.00 (22) …
     ```

     That is a team grade and per-player grades with a parenthesised count, presumably receptions.
   - **Unknowns:** [UNKNOWN]
     - the scale (a screenshot mentions a 3-point scale and Volleymetrics; origin and method are unverified);
     - the grader's identity and consistency;
     - whether the count is receptions and whether service errors are included;
     - match date vs post date (the match was Aug 21, the post Aug 23);
     - name aliases (e.g. "Suli" is listed as Tonga-Davis elsewhere);
     - coverage.
   - **Not treated as data:**
     - informal estimates ("like 2.03 I think");
     - commenter suggestions (e.g. "code service errors as 3").
3. **ncaa.com box scores** carry team **reception attempts and reception errors** (reception attempts non-zero on 4,422 of 4,442 2026 team rows; 10,230 of 10,262 in 2025). That is an error rate, **not a pass grade**.


### UPDATE 2026-09-26 (after the packet was written): thread read, then quality-reviewed (mail 026)
- **How it was read:** on Cody's direct request, in his own Chrome session. That read supersedes this packet's earlier statement that no automated tool could reach the source. It does **not** change the Reviewer's own prohibition. No further site access was requested or done.
- **What was captured (private, `Cody/data/vt_passing_2026/`):**
  - 59 posts verbatim, out of 457 the Builder read. The Reviewer has not independently verified the 457.
  - 709 parsed rows: 133 team, 542 player, 34 unparsed.
- **Two kinds of flag, kept separate:**
  - **syntax_review (67 rows):** the parser was unsure.
  - **source flags (218 rows):** the post itself shows a quality problem. From a per-post issues list covering all 59 posts. The flags:
    - partial or incomplete (38);
    - misassigned players (35);
    - team unidentified (41);
    - side label is the opponent (12);
    - changed grading harshness (9);
    - same match graded twice by different people (25);
    - different metric, e.g. "pass grade off serve" = the **opponent's** passing (17);
    - no attempt counts (33);
    - suspect values (29);
    - self-graded by a fan (59);
    - alias (10).
- **Scope:**
  - 611 match rows, 45 partial-match rows.
  - **53 aggregate rows** (31 season-to-date + 22 weekend), which are not match observations. 34 of them were not flagged by the parser, so the flag count alone is **not** readiness.
- **Analysis candidates:** 510 rows (104 team / 406 player) from 27 posts: single match, clean parse, no blocking source flag. **Candidate ≠ usable**: none is joined to a game id, and aliases are not normalized.
- **Definitions are forum-stated, not validated:**
  - 0–3 scale; attempts in parentheses.
  - Team = attempt-weighted mean, shown for one post only.
  - **GP% threshold undefined.**
- **Poster ≠ grader:** 626/709 rows were posted by one account. That does not establish who graded them.
- **Coverage limits:**
  - The filter kept posts with 2+ grade lines, so single-line corrections can be missed.
  - Quote-stripping does not prove cross-post dedup.
  - ~52 segments ≠ 52 verified fixtures; post date ≠ match date.
  - It is a one-time snapshot.
- **Also in the thread (unverified forum claims, history only):** champion team passing grades 2017–2025, and one program's year-by-year grades.
- **Kept out of POWER and all forecasts.** No grade altered, and no average recomputed.

### Automation options (none installed)

| Option | Acquisition | Processing | Honest coverage claim |
|---|---|---|---|
| **A. User-supplied exports** (recommended now) | Cody saves the thread pages (PDF/screenshots) into the project | Script parses the PDF text, OCRs images only when needed, dedupes quoted posts, keeps post author/date/URL, maps aliases through a reviewed table, and sends every ambiguous value to a **review queue** | "Covers the posts Cody exported", never "all matches" |
| **B. Authorized upstream source** | The grader or data owner (e.g. a Volleymetrics-derived source) provides a structured export with permission | Direct ingest with the owner's definitions | Whatever the owner certifies |
| **C. Forum crawler** | **Not an option:** the site challenges bots and the Reviewer's browser policy blocks it | — | — |

**Before any analytic use, the ingest must store:**
- the scale and its definition;
- what the count means;
- a match attribution (gid) confirmed against our fixture list;
- provenance: original post URL, author, post time and export file;
- correction history;
- quality flags.

**Do not recompute** team averages from player lines until the denominators reconcile.

**Once validated, possible uses (analysis):** link passing to opponent serve pressure (aces/SE per attempt), setter assists and hitters' kill% by match. Always **as passing, not set quality**.

## E. Validation plan (applies to anything proposed)
1. **Chronological only:** fit on the past, score the future, including within-season rolling blocks (the Round-2 harness exists and passes leakage tests).
2. **Baselines always shown:** the live POWER replica (A), a prior-only model, and a W/L-only model.
3. **Metrics:** log loss (primary), Brier, calibration intercept and slope, reliability deciles; AUC descriptive only.
4. **Uncertainty:** block bootstrap by week, with a 14-day sensitivity check. State that teams recur across blocks.
5. **Checks:**
   - subgroups: phase, conference, neutral site, missing box score;
   - a missingness audit (which matches lack a box score or a verified result);
   - leakage (same-day results must not change pregame values; tested).
6. **Report negative results** with their receipts. No weight is chosen because the output "looks right".
7. **Prospective shadow:** a frozen model logged pre-match next to live POWER for the rest of 2026. A daily 05:45 research job already records three models and runs.
8. **Decision:** Cody, the Reviewer and the Builder read the receipts together; Cody decides.

## F. Questions for outside research
1. Which published volleyball rating systems (e.g. Pablo/RichKern, Massey, VolleyDork, VolleyMetrics research, academic dynamic Bradley–Terry work) use set margins, point margins or box components? What did each find out of sample?
2. Is there evidence that serve-receive or serve-pressure metrics predict **future** matches beyond point margin? At what sample size do they stabilize (split-half reliability by number of matches)?
3. How do analysts separate **opportunity** from **efficiency** for digs, blocks and kills per set? Are there standard opportunity denominators (opponent attacks, opponent in-system rate)?
4. Is there a public, licensed source for rally-level 2026 data (server identity, rotation, pass grades)? What are its terms? Does ncaavolleyballr publish in-season?
5. What is the right handling of neutral sites and home edge in NCAA volleyball specifically (size, variance across venues)?
6. How reliable are forum or community passing grades (VolleyTalk's 3-point grades)? Who produces them and by what method? Is there an owner who could license a structured export?
7. How are championship-caliber profiles (PPS, component mix) distributed among **non-champions** at the same season dates?
8. What does the literature say about the 5-1 vs 6-2 system, and setter changes, as predictors (the Stanford case)?

## G. Approved scope and next action
- **Approved:** this packet (documentation, read-only checks).
- **Not approved:** POWER changes, commits, pushes, scheduled jobs, emails, crawlers and feature builds.
- **Next:** the Reviewer checks the packet → Cody takes it to outside research → joint review → only then implementation.


<!-- DATA-INVENTORY.csv -->
```csv
dataset_id,field_group,path,source,source_tier,definition_units,granularity,seasons,refresh_cadence,latest_observation,record_count,coverage_denominator,missing_zero_notes,quality_constraints,used_in,prospective_use
games_2024,game log,data/raw/2024/games.jsonl,ncaa-api /game (ncaa.com mirror),OFFICIAL,"game_state, start_time_epoch, teams[sets_won,is_winner,division,record_at_time], linescores per set (points)",match,2024,frozen,2024-12-22,5192 records / 5192 gids / 5186 finals,5186 finals,location absent (0 of 5192),division flag is CURRENT division (retroactively unreliable),"2024->2025 backtests, strength_2024",prior-season model training
games_2025,game log,data/raw/2025/games.jsonl,ncaa-api /game,OFFICIAL,as 2024,match,2025,frozen,2025-12-21,5131 records / 5131 gids / 5131 finals,348 D-I teams (rpi_official),location absent (0 of 5131); 34 games with neither team D-I,reconciled 348/348 vs official RPI records,"rating_2025, rpi_2025, bakeoff, calibration",training corpus for POWER
games_2026,game log (append-only),data/raw/2026/games.jsonl,ncaa-api /game,OFFICIAL,"as 2025 plus location{venue,city,state}",match (multiple records per gid),2026,~20-30 min refresh + nightly,2026-09-26,25829 records / 4895 gids / 2223 gids with a final,"audit manifest: 2221 feed finals, 2194 counted ok",location on 16662 of 25829 records; phantom 0-0 / tied pairs dropped on finals,dedup final-beats-non-final then last-wins; non-finals never counted; self-contradictory/empty finals held,every 2026 surface,live POWER input
scoreboard_2024,scoreboard by date,data/raw/2024/scoreboard/*.json,ncaa-api /scoreboard,OFFICIAL,game ids per date,date,2024,frozen,2024-12-31,139 date files,139 dates,,,game enumeration,
scoreboard_2025,scoreboard by date,data/raw/2025/scoreboard/*.json,ncaa-api /scoreboard,OFFICIAL,game ids per date,date,2025,frozen,2025-12-31,139 date files,139 dates,,,game enumeration,
scoreboard_2026,scoreboard by date,data/raw/2026/scoreboard/*.json,ncaa-api /scoreboard,OFFICIAL,"gameID,gameState,startTime(Epoch),network,title,bracketRound",date x game,2026,refresh,2026-12-31 (schedule horizon),139 date files / 4839 game entries,4839,network field filled 0 of 4839,start time placeholder 12-7AM ET = unannounced (sentinel),"schedule, fixtures, live band",schedule graph for simulation
boxscores_team_2025,team box totals,data/raw/2025/boxscores.jsonl,ncaa-api /boxscore,OFFICIAL,"kills, attackErrors, attackAttempts, assists, serviceAces, serviceErrors, serveAttempts, receptionAttempts, receptionErrors, digs, blockSolos, blockAssists, setAttempts; per-set attack-only sets[]",team x match,2025,frozen,2025-12-21,5131 records / 10262 team rows,10262 team rows,serveAttempts & receptionAttempts nonzero on 10230/10262; receptionErrors nonzero 10099; blockSolos nonzero 7783,team blocks = solo + 0.5*assists; hit% = (K-E)/TA from summed counts; feed totalBlocks unreliable (unused); points col not used as season total,"metric_value, blend_hiteff, blend_recv, team_season_stats",serve/receive efficiency channels
boxscores_team_2026,team box totals,data/raw/2026/boxscores.jsonl,ncaa-api /boxscore,OFFICIAL,as 2025,team x match,2026,refresh,2026-09-26,2221 records / 4442 team rows,2221 finals,serveAttempts & receptionAttempts nonzero 4422/4442; receptionErrors 4358; blockSolos 3311; 1 fetch failure (boxscores_failed.json),as 2025; live box numbers provisional and never stored,"hitting channel (w=0.25), team stats, recap",reception/serve channels
playerbox_2024,player box lines,data/raw/2024/playerbox.jsonl,ncaa-api /boxscore,OFFICIAL,"per-player kills, errors, atts, aces, digs, bs, ba, assists, gp",player x match,2024,frozen,2024-12-22,5186 games / 170275 player rows,5186 games,lists more bench players than 2025 (33/match vs 23),not comparable to 2025 player counts; MIN_SETS filter required,"players_2024, churn/roster fits",
playerbox_2025,player box lines,data/raw/2025/playerbox.jsonl,ncaa-api /boxscore,OFFICIAL,as 2024,player x match,2025,frozen,2025-12-21,5131 games / 117270 player rows,5131 games,,points column unusable as a total,"players_2025, player_rating priors",
playerbox_2026,player box lines,data/raw/2026/playerbox.jsonl,ncaa-api /boxscore,OFFICIAL,"team_id,name,num,pos,gp,kills,errors,atts,aces,digs,bs,ba,assists,serve_atts/errors,recv_atts/errors,bh/set/block errors,starter",player x match,2026,refresh,2026-09-26,2221 games / 58137 player rows,2221 games,"8853 rows with all core stats zero (DNP convention gp=N, zeros); serve_atts & recv_atts present on 57625; starter set on 26409",appearance cannot be inferred from gp alone; mojibake names repaired via nameclean,"player_rating_2026, availability, participation radar",player-weighted team strength
players_2024,player season aggregate,data/raw/2024/players_2024.json,derived from playerbox_2024,DERIVED,summed raw counts per player,player-season,2024,frozen,not measured,9700 players,,33% zero-kill tail,,fit_2024_2025,
players_2025,player season aggregate,data/raw/2025/players_2025.json,derived from playerbox_2025,DERIVED,summed raw counts per player,player-season,2025,frozen,not measured,5896 players,,27 mojibake identities merged,,"returning production, transfers, priors",
players_2026,player season aggregate,data/raw/2026/players_2026.json,derived from playerbox_2026,DERIVED,summed raw counts per player,player-season,2026,refresh,not measured,5688 players,,,,"player pages, stats",
lineups_2025,set-1 starting six,data/raw/2025/lineups.jsonl,ncaa-api /game/{id}/play-by-play,OFFICIAL,"set-1 six names (sets 2+ are cumulative lists, not lineups)",team x match,2025,frozen,2025-12-21,5109 records,5131 games,starters_lines_with_names>0 on 5106,"listing order = jersey number, NOT rotation order",offense_system 5-1/6-2,
lineups_2026,set-1 starting six,data/raw/2026/lineups.jsonl,ncaa-api play-by-play,OFFICIAL,as 2025,team x match,2026,daily,2026-09-26,2197 records,2221 finals,starters_lines_with_names>0 on 2110,"attribution by name match to box score, not feed label","lineups_2026.json (370 teams), lineup attribution guard",
pbp_raw_2025,ncaa.com play-by-play sample,data/raw/2025/pbp.jsonl,ncaa-api play-by-play,OFFICIAL,raw PBP payloads (servers named only on aces),match,2025,frozen,not measured,206 records,,,,rotations_finding (negative result),
rosters_2026,rosters,data/raw/2026/rosters_2026.json (+PASS2/PASS3/PREV/manual/recovered variants),school athletics sites,OFFICIAL,"name, class_raw, pos_raw, num_raw, how",player,2026,not daily (preseason crawl),not measured,377 teams / 5986 players,348 D-I,pos_raw on 2393; class_raw on 5343; photo field on 2278,R8 surname-anchored join; never backfill 2026 jersey from 2025,"returning production, player pages",
roster_positions_2026,roster positions 2nd pass,data/raw/2026/roster_positions_2026.json,school sites,OFFICIAL,spelled-out positions,player,2026,one-off,not measured,254 teams,,documented total position coverage ~81% after box-score fallback,box-score 'O' never mapped to OPP,position headlines,
roster_photos_2026,headshot URLs,data/raw/2026/roster_photos_2026.json; player_page_photos_2026.json,school sites (schema.org),OFFICIAL,"URL only, never file",player,2026,one-off,not measured,232 teams,,,"URLs only, not downloaded",faces on pages,none for rating
transfers_2026,transfers,data/vb_transfers_2026.json,legacy 40-team sample + official transfer map,THIRD-PARTY/DERIVED,from_team -> to_team,player,2026,one-off,not measured,40 teams (legacy file),,documented: 555 of 562 transfers resolve to 2025 production,"anchored on (from_team_id,name)","returning production, churn",
returning_2026,returning production,data/returning_2026.json,derived: rosters x players_2025,DERIVED,share of 2025 production returning,team,2026,one-off,not measured,350 teams,348,"documented 309 of 348 measured, rest render -",R8 join,projection_2026,
projection_2026,preseason projection,data/projection_2026.json,derived,DERIVED,prior + roster delta (0.0565) + churn (-0.1304),team,2026,one-off,not measured,348 teams,348,,OOS rho ~0.84 (churn_fit),"blend prior, digby_top25",POWER prior
churn_fit,churn/roster fit,data/churn_fit.json; fit_2024_2025.json; level_effect.json,derived 2024->2025,DERIVED,fitted weights,model,2024-2025,frozen,not measured,meta only,,new_player_share 53.8% in fit_2024_2025 NOT trustworthy,,projection_2026,
rotations_2025,serving rotations,data/rotations_2025.json,ncaavolleyballr PBP CSV (MIT mirror of stats.ncaa.org); CSV not committed,THIRD-PARTY,serve order = rotation; substitution pairings,team x set,2025,frozen,not measured,357 teams (348 matched); 48625 set-teams resolved (96.5%),50410 set-teams,"serving six, not on-court six; middles rarely appear",attribution to ncaavolleyballr required,team pages rotation ring; rotation_sideout_2025,rotation-level modelling (2025 only)
pbp_player_2025,player rally metrics,data/pbp_player_2025.json,ncaavolleyballr PBP CSV (not committed),THIRD-PARTY/DERIVED,"serve rally win, reception outcome (no 0-3 grade), back-row share",player-season,2025,frozen,not measured,17091 players; 826207 rallies,,no pass grade; aces charge no passer,source CSV 775MB gitignored,player_rating enrichment,receive-quality proxy
rpi_official_2025,official RPI table,data/raw/2025/rpi_official.json,ncaa.com rankings (current-only),OFFICIAL,"rank, record (D-I only), Non-Div I",team,2025,IRREPLACEABLE capture 2026-08-10,Dec 21 2025,348 teams,348,,defines 2025 D-I membership; cannot be refetched,"reconcile, bakeoff, resume validation",
polls_rpi_top16_2025,2025 RPI/Top16 poll captures,data/raw/2025/polls_rpi.jsonl; polls_top16.jsonl,ncaa.com rankings,OFFICIAL,poll rows with Through Games stamp,team x capture,2025,frozen,not measured,1 capture each,,,filed by described season not capture date,context,
polls_avca_2026,AVCA coaches poll,data/raw/2026/polls_avca.jsonl; avca_poll_2026-08-18.json,ncaa.com rankings = AVCA poll,OFFICIAL,"rank, points, first-place votes",team x week,2026,"daily capture, appends when stamp moves",not measured,5 captures,25 ranked/week,,current-only endpoint; missed week unrecoverable,"AVCA column, at-time opponent rank",external benchmark
avca_rv_2026,AVCA receiving votes,data/raw/2026/avca_rv.jsonl,AVCA,OFFICIAL,others receiving votes,team x week,2026,weekly,not measured,1 line,,,,rankings context,
rankings_history_2026,weekly frozen ranking,data/rankings_history_2026.jsonl; rank_daily_2026.jsonl,derived,DERIVED,ranks + basis (preseason/blend/live),team x week,2026,"Mondays, append-only",not measured,5 rows (+1 daily),,,never rewritten; movement only on same basis,movement arrows,ranking stability eval
digby_top25_2026,blend strength ranking,data/digby_top25_2026.json; digby_weekopen_2026.json,derived,DERIVED,"(1-w)*preseason_z + w*season_z, w=n/(n+k)",team,2026,refresh,not measured,348 teams each,348,,trust cutoff: same-day finals only if school-verified,POWER board (current basis),POWER candidate baseline
rating_2025_2026,composite rating,data/rating_2025.json; rating_2026.json,derived,DERIVED,w_rpi*Z(RPI)+w_margin*Z(adj net pts/set),team,"2025, 2026",refresh,not measured,348 teams each,348,,2026 switch held by Cody 2026-09-26 pending POWER research,board (when validated),POWER candidate
rpi_derived,derived RPI,data/rpi_2025.json; rpi_2026.json,derived from game log,DERIVED,"25/50/25 unweighted, D-I only",team,"2025, 2026",refresh,not measured,348 teams each,348,,Factor IV not reproducible,"resume, rating",
resume_2026,resume ranking,data/resume_2026.json; resume_2025.json,derived,DERIVED,RPI rank + WAB,team,"2025, 2026",refresh,not measured,348 teams,348,active once >=200 D-I matches,strength != resume (R3),RESUME column,
ranking_certificates_2026,ranking maturity certificates,data/ranking_certificates_2026.json,derived,DERIVED,policy verdicts (median counted matches 13 vs k 13.52),season,2026,refresh,2026-09-26T23:18Z,meta only,,ordering_mature_for_public_rank=false (held),,ranking gating,
board_bakeoff_2026,board bakeoff log,data/board_bakeoff_2026.jsonl,derived,DERIVED,per-run comparison of ranking sources,run,2026,refresh,not measured,146 lines,,,,internal eval,POWER evaluation
blend_receipts_2025,measured blend receipts,data/blend_hiteff_2025.json; blend_recv_2025.json; blend_upgrades_2025.json; blend_k_2025.json; forecast_*_2025.json; sim_blend_2025.json; metric_value_2025.json; bakeoff_2025.json,derived 2025 OOS,DERIVED,AUC/Brier verdicts with bootstrap CIs,experiment,2025,frozen,not measured,not measured (small verdict files),,,ship only when CI clear of zero,hit channel weight 0.25 guard,prior evidence for POWER
predictions_2026,match predictions,data/predictions_2026.json,derived rally model,DERIVED,win probability per fixture,match,2026,refresh,not measured,2676 games,,availability is NOT an input,Brier 0.1289 on 2025,forecast cards,
prediction_log_2026,pre-serve prediction log,data/raw/2026/prediction_log.jsonl,derived,DERIVED,home_win prob logged pre-match,match x log time,2026,"refresh, append-only",not measured,4814 lines,,,provably pre-serve,prediction scoring,honest forecast eval
prediction_score_2026,forecast scoring,data/prediction_score_2026.json,derived,DERIVED,calibration + scored matches,match,2026,refresh,not measured,50 matches,,,,calibration display,POWER forecast eval
season_sim_2026,season simulation,data/season_sim_2026.json,derived (4000 iterations),DERIVED,"projected wins bands, RPI rank p10/p50/p90, tournament odds",team,2026,refresh,not measured,348 teams,348,plays only scheduled fixtures (TBD opponents absent),80% band covered 87.3% in 2024->2025 backtest,"Outlook, bracket",
verification_daily,school-site verification reports,data/result_verification_2026-*.json,school athletics sites (incl WMT /website-api),OFFICIAL (school),verdict per final vs both schools,match,2026,each refresh (incremental),2026-09-26,"26 daily files; verdicts: VERIFIED_BOTH 1113, CORROBORATED_ONE 548, UNVERIFIED 27, CONTRADICTED_BOTH 8, CONTRADICTED_ONE 4, SCHOOL_CONFLICT 2, HELD_* 15",finals by date (2026-09-21 file absent),,held finals OBSERVED never verified,"trust cutoff, result ledger",verification-weighted inputs
verification_log,verification fetch log,data/raw/2026/result_verification_log.jsonl,school sites,OFFICIAL (school),"team,url,http,retrieved_utc,state",fetch,2026,append-only,not measured,35600 lines,,,,audit,
result_corrections,result corrections ledger,data/raw/2026/result_corrections.json,cited school evidence,OFFICIAL (school) / curated,corrected winner/sets/linescores with citations,match,2026,"hand, append-only",not measured,89 corrections,,,two-source rule,all counting consumers,
result_evidence,result evidence,data/raw/2026/result_evidence.json; result_evidence_auto.json,school sites,OFFICIAL (school),"evidence rows (manual 67, auto 1675)",match,2026,refresh/hand,not measured,67 manual + 1675 auto,,,conflicts count nowhere,"corrections, confidence",
review_queue,result review queue,data/raw/2026/result_review_queue.json; attribution_pending.json; attribution_adjudications.json; attribution_suspicion_2026.json,derived,DERIVED,queued suspicious finals,match,2026,refresh,not measured,131 queue entries,,,"signal only, never quarantines",ledger review,
duplicate_listings,duplicate listings ledger,data/raw/2026/duplicate_listings.json; data/duplicate_candidates_2026.json,school schedules,curated,duplicate gid -> canonical,match,2026,"hand, append-only",not measured,11 duplicates,,,no heuristic removal,counting skip,
exhibitions,exhibitions ledger,data/raw/2026/exhibitions.json,school evidence,curated,exhibition gids with format proof,match,2026,hand,not measured,2 exhibitions,,,requires format proof + binding quote,excluded from counts,
fixture_ledger,fixture corrections,data/raw/2026/fixture_ledger.json,school evidence,curated,venue/time overrides with citations,fixture,2026,hand,not measured,6 entries,,,only where/when fields overridable,schedule/venue,
suspended_fixtures,suspended matches,data/raw/2026/suspended_fixtures.json; state_reclassified.json,school statements,curated,suspension record,fixture,2026,hand,not measured,1 entry,,,counts nowhere,suspended badge,
fixture_disposition,fixture dispositions,data/fixture_disposition_2026.json,derived,DERIVED,withdrawn/suspended/unknown per fixture,fixture,2026,refresh,not measured,not measured,,,,weekly completeness,
audit_manifest,release audit manifest,data/audit_manifest_2026.json,derived,DERIVED,counted-gid hash + totals,season,2026,each build,not measured,feed_records 2221; ok 2194; duplicate 11; exhibition 2; under_review 2; empty 7; self_contradictory 5; rating_eligible_now 2150,2221,,build fails closed on divergence,release gate,corpus fingerprint for POWER
result_confidence,result confidence,data/result_confidence_2026.json,derived,DERIVED,confidence state per final,match,2026,refresh,not measured,2221 finals,2221,,,ledger chips,
data_2025_2026,built datasets,data/data_2025.json; data_2026.json,derived from raw,DERIVED,teams + games (whitelisted fields),team/match,"2025, 2026",each build,not measured,not measured,,,final-only,all rating/build,
fixture_time_check,start time check,data/fixture_time_check_2026.json,school sites vs feed,DERIVED,time disagreements >15 min,fixture,2026,refresh,2026-09-26T23:10Z,"93 fixtures checked, 92 schools answered, 4 disagreements",93 in 4-day window,815 timestamps unresolved,not a correction,ops,
tv_auto,broadcast listings,data/raw/2026/tv_auto.json,school schedule pages,OFFICIAL (school),events with network,school x event,2026,refresh,not measured,"377 schools: ok 287, no_payload 90; 6729 events, 2233 with network",377,,linear vs streaming via tv_kind,TV column,none
venues_2026,venues/events,data/venues_2026.json,feed location + derived,OFFICIAL/DERIVED,"venue, city, event",match,2026,refresh,not measured,4893 games; 262 home venues; 147 events,,/game location can be home-arena template on neutral sites,neutral detection not built,venue display,home-advantage term
wmt_sport_ids,WMT sport ids,data/raw/2026/wmt_sport_ids.json,school /website-api/sports,OFFICIAL (school),volleyball sport id per site,school,2026,as needed,not measured,350 schools,,,sport id per site; name must match exactly,verifier,
athletics_sites,athletics site URLs,data/raw/2026/athletics_sites.json; athletics_sites_overrides.json,ncaa.com school pages + overrides,OFFICIAL,domain,school,2026,one-off,not measured,377 schools,,ncaa.com carries stale domains; overrides fix,,crawlers,
availability_flags,box-score absence flags,data/availability_2026.json; availability_2025.json,derived from playerbox,DERIVED,top-6 player absent vs local window,player x match,"2025, 2026",refresh,not measured,1149 flagged (2026),,absent != injured,,availability desk,availability input (not currently used)
availability_desk,sourced availability,data/availability_desk_2026.json; raw/2026/availability_evidence.json,public attributable sources,OFFICIAL/THIRD-PARTY,status/incident/signal with quotes,player,2026,hand + refresh,not measured,"evidence players 12; desk statuses 2, incidents 0, signals 0, projection 1",,no diagnoses stored,forecasts do NOT use availability,"desk, dossier",
participation_radar,participation radar,data/participation_radar_2026.json,derived,DERIVED,appeared / zero-action / not in box,player,2026,refresh,not measured,258 players,,,not an absence claim,desk,
availability_scan,availability phrase scan,data/availability_scan_2026.json,school sites,OFFICIAL (school),phrase hits bound by surname,team,2026,refresh,2026-09-26T23:16Z,185 teams with flagged player; 16 reached; 169 unreadable,348,,,review signals,
player_context,player context,data/raw/2026/player_context_2026.json,sourced notes,THIRD-PARTY,explicit overrides,player,2026,hand,not measured,not measured,,,,,
source_intel,intel claims,data/source_intel_2026.json; intel_feed_2026.jsonl,derived from sourced evidence,DERIVED,claims with kinds,claim,2026,refresh,not measured,126 claims; 146 feed lines,,,,Intel wire (private),
player_rating_2026,player ratings,data/player_rating_2026.json; player_rates_2025.json; opp_z_2025.json,derived,DERIVED,schedule-adjusted rates,player,2026,refresh,not measured,5582 players,,,,ratings board,player-based POWER
avca_awards,AVCA All-America,data/avca_awards.json,AVCA workbook (Cody supplied),OFFICIAL,selections + national awards,player-season,44 seasons,one-off,not measured,3027 selections,,,school join normalised,badges,
coaches,coaches,data/raw/2026/coaches_2026.json; coaches_found_2026.json; coaches_from_roster_2026.json,school sites/AVCA citations,OFFICIAL,head coach,team,2026,one-off,not measured,coaches_2026: 50 rows (documented 341 of 348 across files),348,,,team pages,
conferences,conferences,data/raw/2026/conferences_2026.json; conference_overrides.json,ncaa.com + schedule-derived override,OFFICIAL/DERIVED,conference per team,team,2026,one-off,not measured,348 teams,348,UT Arlington WAC->UAC override,,"AQ, standings",
aq_mechanism,AQ mechanism,data/raw/2026/aq_mechanism_2026.json,ncaa.com 2025 AQ article + conference sites,OFFICIAL,tournament vs regular season,conference,2026 (2025 evidence),one-off,not measured,33 conference rows (32 real + superseded WAC),32,,,field projection,
conference_lab,conference lab,data/conference_lab_2026.json; conference_snapshots_2026.jsonl,derived,DERIVED,"interconference records, matrix",conference,2026,refresh,not measured,not measured,32,,,Conference Lab,
team_colors_logos,colors/logos,data/team_colors_2026.json; vb_logos.json; vb_logos_seo.json,logo SVGs,DERIVED,hex colours; logo refs,team,2026,one-off,not measured,373 colour teams; 40 legacy logos,384,,,display,none
legacy_40,legacy 40-team sample,data/vb_*.json; vb2025.json; vb_cody_workbook.json,early sample,UNVERIFIED,superseded,team,2025,frozen,not measured,40 teams,,,superseded by 348-team pipeline,none current,none
volleytalk_polls,VolleyTalk poll,data/volleytalk_polls.json,VolleyTalk forum,THIRD-PARTY,poll ranks,team x week,2026,hand,not measured,not measured,,private only,not republished,private board,
cody_external_snapshots,Cody/data manual snapshots (structure only),"Cody/data/{figstats,massey,monsterblock,evollve}_snapshots.jsonl; vt_weekly_2026.jsonl; my_ballots.jsonl; tv_listings_2026.txt",manual browser captures,THIRD-PARTY,"external references (FIG RPI, Massey, Monster Block)",capture,2026,manual,not measured,not measured,,gitignored/private; contents not inventoried,never rating inputs,External references disclosure,external benchmarks only
research_tamu_pps,TAMU 2025 PPS descriptives,Cody/coordination/research/TAMU-2025-PPS-DESCRIPTIVES.json,derived research,DERIVED,points-per-set descriptives,team-season,2025,one-off,not measured,not measured,,,,research,
research_texas_pps,Texas 2023 PPS descriptives,Cody/coordination/research/TEXAS-2023-PPS-DESCRIPTIVES.json,derived research,DERIVED,points-per-set descriptives,team-season,2023,one-off,not measured,not measured,,,,research,
research_prototype,POWER prototype outputs,"Cody/coordination/research/prototype/{results.json,results_m3.json,m3_frozen.json}",derived research,DERIVED,prototype model results + preregistrations,experiment,2025-2026,research,not measured,not measured,,,preregistered,POWER research,
passing_stats_user,user-supplied passing stats,passing stats/ (1 PDF + 2 PNG); Passing Stats VT thread link.textClipping,Cody-supplied VolleyTalk thread export,UNVERIFIED,passing grades (not transcribed),player x match (reports),2026,one-off,not measured,3 files; reviewer: 3 original matchup reports on page 1,unknown,coverage UNVERIFIED,not structured; not verified,none,possible pass-quality signal if sourced
volleytalk_passing_thread,VolleyTalk passing-grade thread,(none - web thread),VolleyTalk,THIRD-PARTY,passing grades,,2026,n/a,not measured,ACCESS BLOCKED / UNVERIFIED,,proof-of-work bot challenge to non-browser clients,not an available dataset; no scripting around challenge,none,
na_pass_grades,UNAVAILABLE: structured pass quality/grades,n/a,none,n/a,0-3 pass ratings,,,,,UNAVAILABLE,,feed carries no pass grade (pbp_player_2025 meta),,,
na_set_quality,UNAVAILABLE: set location/quality,n/a,none,n/a,,,,,,UNAVAILABLE,,,,,
na_block_touches,UNAVAILABLE: block touches,n/a,none,n/a,,,,,,UNAVAILABLE,,only solo/assist blocks recorded,,,
na_coverage,UNAVAILABLE: coverage/free-ball events,n/a,none,n/a,,,,,,UNAVAILABLE,,,,,
na_server_2026,UNAVAILABLE: 2026 serve-by-serve server identity,n/a,ncaa.com names servers only on aces; ncaavolleyballr covers 2020-2025 only; StatBroadcast/stats.ncaa.org not permitted,n/a,,,2026,,,UNAVAILABLE,,,,,
na_rotation_2026,UNAVAILABLE: rally-level rotation state 2026,n/a,none,n/a,,,2026,,,UNAVAILABLE,,set-1 lineups in jersey order only,,,
na_injury,UNAVAILABLE: injury causes,n/a,none,n/a,,,,,,UNAVAILABLE,,"absence observable, cause never in data; no diagnoses stored",,,
vt_passing_2026,passing grades (team + player),Cody/data/vt_passing_2026/ (private),"VolleyTalk thread 107960, read in Cody's Chrome 2026-09-26",THIRD-PARTY / UNVERIFIED,0-3 pass grade; (attempts); GP% = good-pass %,player and team per match (some season/weekend totals),2026,manual (on request),2026-09-26T18:41:36Z (latest post),"709 rows from 59 posts (133 team, 542 player, 34 unparsed)",~52 matchup segments; mostly ranked/Power-4; many matches 'not coded',"syntax_review 67 (parser); source flags on 218 rows from a 59/59 per-post issues list; 53 aggregate rows (not match observations); missing match = not coded, not zero","forum-stated definitions (0-3, attempts; GP threshold undefined); 626/709 rows posted by one account (poster, not proven grader); posts admit misassigned players/partial matches; 510 single-match candidates, none joined to game ids",none,descriptive passing analysis after gid join + alias review; never set quality

```

<!-- PASSING-QUALITY.md -->
# Passing capture: quality review (mail 026)
Builder, 2026-09-26. Built from the saved posts only. **No further site access.** Raw posts and reported grades are unchanged.

## Two kinds of flag, kept separate
- **`syntax_review` (67 rows):** the *parser* was unsure. Examples: side unknown, extra columns, free text.
- **`source_flags` (218 rows carry at least one):** the *post itself* says something about its quality, or its content plainly shows it. These come from `quality_issues.py`, one entry per post (59 of 59 reviewed).

A row with neither flag is **not** validated. It only means nothing is known to be wrong with it.

## Scope (per post; `scope` column)

| Scope | Rows | Meaning |
|---|---|---|
| match | 611 | one match per segment (a multi-match post has several) |
| match_partial | 45 | the post says it is incomplete, or covers one side only |
| aggregate_season | 31 | season-to-date totals: **not match observations** |
| aggregate_weekend | 22 | several matches combined: **not match observations** |

The **34 aggregate rows the parser did not flag** are exactly the case the Reviewer named. They parse cleanly but are totals. They are now marked by scope, and they never count as analysis candidates.

**Known limit:** scope is per post. A "match" post can contain one weekend segment (e.g. the Florida weekend total inside post-4911170). That is listed in the issue note, not split into separate rows.

## Source flags found (rows affected)

| Flag | Rows | Examples |
|---|---|---|
| poster_self_graded | 59 | fans' own grading (posts 4870505, 4889539, 4897559, 4897466) |
| team_unidentified | 41 | "These are totals" with no team named |
| admitted_incomplete | 38 | "missed a couple passes"; "stopped ten points into set four" |
| vm_coding_referenced | 36 | poster cites Volleymetrics coding |
| misassigned_players | 35 | "their numbers are all off"; "gave one of hers to Henley"; "should be Watson?" |
| no_attempts | 33 | grades posted without attempt counts ("wanted to do this fast") |
| suspect_value | 29 | "Loper .169", "Frame 2.5/4", "Decket" |
| duplicate_match_other_grader | 25 | Texas–USC graded twice (a fan, and VM figures), and the two disagree |
| different_metric | 17 | "pass grade OFF SERVE" = the **opponent's** passing on her serves; hit% off pass; % points won |
| side_label_is_opponent | 12 | "MQ"/"MIL", "USD", "vs UA/COL/OSU": the header names the OPPONENT |
| alias | 10 | Suli / Tonga-Davis |
| low_attempts_admitted | 9 | "(2, not really fair)" |
| harshness_changed | 9 | "grading less harshly than usual due to the wind" (outdoor PSU–Kentucky) |

## Analysis candidates: 510 rows (104 team, 406 player) from 27 posts
**Rule:** scope = match, clean parse, and no blocking source flag. The blocking flags are:
- misassigned_players, side_label_is_opponent, admitted_incomplete, harshness_changed;
- team_unidentified, suspect_value, duplicate_match_other_grader, different_metric.

**Candidate ≠ usable.** None is joined to a game id yet, aliases are not normalized, and nothing has been cross-checked.

## Definitions and provenance: what is and isn't established
- **Scale 0–3, attempts in parentheses:** stated by posters, not independently validated. Graders may differ.
- **Team grade = attempt-weighted mean:** shown for ONE post (Penn St., 2.03). Other posts are not shown to reconcile.
- **GP% ("good pass"):** the threshold is **never defined** in the thread (≥2? only 3s?). UNKNOWN.
- **Poster vs grader:** 626 of 709 rows were *posted* by one account. That is **poster attribution, not proof that one person graded them**. Some of those posts cite VM coding, and others are silent on who graded.

## Coverage and selection limits
- The capture kept posts whose own text had **2 or more grade-like lines**. So a single-grade reply or an isolated correction ("Schrand was 2.93") can be missed. Such corrections are listed as notes where caught, but completeness is not proven.
- Stripping quoted text removes repeats **inside** posts. It does **not** prove every repeated observation or correction **across** posts was deduplicated.
- "About 52 segments" is **not** 52 unique verified fixtures. Posting date is not match date. Several segments are the same team's weekend.
- **This is a one-time snapshot.** No recurring ingestion is installed. The 457-post count is the Builder's reading; the Reviewer has not verified it.

## Rules kept
- No reported grade was altered.
- No averages were recomputed.
- No rating, forecast or page uses this data. It is kept out of POWER.
