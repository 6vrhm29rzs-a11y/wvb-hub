# POWER Research Review: Volleyball-Model Evidence, Data Access, and Tooling Options (as of 2026-09-26)

The evidence does not support putting more box-score or passing channels into POWER's predictive core yet. Before any model tuning, three problems deserve attention: (1) no observation timestamps, (2) home and neutral handling, which may be inconsistent inside the model itself, and (3) evaluation power too low to detect effects of the size already measured. Most of the "fresh" data POWER wants for 2026 (rally-level servers, pass grades) has no permitted automated route. The one clearly new, permitted, low-cost modeling idea is to derive side-out and break-point rates from the point sequences POWER already collects.

## TL;DR
- **Model:** The packet's conclusion that the "signal is already in margin" is plausible but not demonstrated. The hitting and serve-receive tests were too small, and in one case confounded (the τ_hit floor changes both the weight and the scale), to rule anything in or out. The largest likely fixable error is home and neutral handling. The rating uses h = 1.09 pts/set, the forecast intercept is only 0.27 pts/set, and neutral sites are coded as home or away. Exposure (sets, not matches) is a second cheap candidate.
- **Data:** ncaavolleyballr is useful only for 2020–2025 history. Its code is MIT-licensed; the NCAA data is not. The published files include WVB D1 2025 play-by-play, but there is no 2026 in-season feed. stats.ncaa.org now requires a headless browser and risks IP blocks. StatBroadcast and ProBoards terms prohibit automated collection. Volleymetrics data cannot be downloaded or shared, even by subscribers. There is no hobbyist route to licensed pass-quality data.
- **Tools:** Nothing needs to be bought. The best trials are free and reversible: observation timestamps plus content hashes, DuckDB reading the existing JSONL in place, a launchd job with a free dead-man's-switch ping, and a pre-registered prospective log. Claude Code Desktop scheduled tasks skip runs while the Mac sleeps. GitHub Actions cron is officially best-effort and can drop runs. Neither should be the only trigger for the 05:45 job.

---

## 1. Conclusions (bottom line up front)

### What the evidence supports
- **DEMONSTRATED (published, rating-system level):** Margin-based ratings are the norm among the credible public volleyball systems. Pablo scores each match on point percentage (`game score = 25650*(point% – 0.5)`), and its FAQ says the maximum match score of 2500 is reached at a point share of about 0.59. That is an effective margin cap. Pablo now blends "Pure Points" with a W/L model, and its FAQ states that "the accuracy of the combined model is similar to that of the pure points approach." VolleyDork fits a Bradley-Terry model **rally by rally** from NCAA play-by-play, with offsets for serving team and home court. In tennis (Kovalchik 2020, International Journal of Forecasting), every margin-of-victory Elo variant using within-set statistics predicted better than standard Elo.
- **DEMONSTRATED (academic, pro/elite volleyball):** Home advantage in volleyball is real but modest. Laios, Kountouris & Kyprianou (2012, International Journal of Performance Analysis in Sport), covering Italian and Greek first divisions ("6.681 games, 25.324 sets, 1.122.064 points"), reported home wins of 58.1% of games, 55.6% of sets and 50.86% of points, and "the only case when the home advantage was ineffectual was the fifth set of the 5-set games." It also used a Markov-chain simulation to show that the point-level edge reproduces the set-level edge. Marcelino et al. (2009) found home teams won 57.5% of matches. A Bayesian model of Italian volleyball estimated home effects of 0.16 at set level and 0.20 at point level (log-odds posterior medians).
- **DEMONSTRATED (academic, but concurrent rather than predictive):** Reception quality, side-out success and reception errors separate winners from losers *within the same match*. For example, Palao (2018, Journal of Sports Analytics), analysing "2,435 rallies from 48 sets of the Missouri Valley Conference (NCAA Division I)," found winning teams "obtained a point in more than six out of 10 side-outs (63.5%)." None of the studies found measures whether these metrics predict **future** matches beyond point margin.

### What the evidence does not support
- That box components or serve-receive carry **no** incremental information. The experiments measured +0.0006 AUC for hitting (CI +0.0003 to +0.0009, run at k = 13.5 rather than the live k = 10), and serve-receive was inconclusive at 0.25. Those are underpowered null-ish results, not evidence of absence.
- That a champion PPS band (18.03–19.295) discriminates champions. There is no non-champion base rate at matched dates yet, and only 13 positives.
- That VolleyTalk pass grades are a reliable measurement. The grader is unknown, 626 of 709 rows come from one account, and the scale mapping is undefined.

### Top actions, ranked
1. **C8 first: add observation timestamps and content hashes to every appended record.** TRY NOW. Zero cost, and every prospective claim depends on it. Fresh idea: git commit times of the raw JSONL files can serve as *upper-bound* observation times for historical records, recovering a partial as-known-then view.
2. **Audit home and neutral handling as one problem (C4 extended).** Reconcile h = 1.0878 pts/set in the rating with +0.2675 pts/set in the forecast. Estimate how many 2026 matches are neutral from stored venues, then test H = 0.
3. **Re-scope C3.** Pre-register **one** candidate for the rest of 2026, chosen for expected effect size, not convenience. Neutral/home correction or set-based exposure are better candidates than hitting-scale tweaks, whose measured effects are below what ~10 weeks of matches can detect.
4. **Reframe C1** as a decomposition of weight and scale (details in §2), not a two-arm "τ_hit" test.
5. **New modeling channel: side-out and break-point rates from point sequences.** The serving team on each rally can be inferred from who won the previous rally, so this needs no server names. It is VolleyDork's approach, uses data POWER already has for 2026, and gives an opponent-adjusted "serve vs receive" split without StatBroadcast or pass grades. This is a HYPOTHESIS to validate on 2025, where ncaavolleyballr names servers.
6. **C2/C5: build the ten-metric analysis page with opportunity-normalized denominators and shrinkage,** kept out of the predictive core. Replace "assists/set as setter evaluation" (assists mostly track team kills) and label every metric as descriptive.
7. **Infrastructure trials (free, reversible):** DuckDB over the existing JSONL (read-only), launchd plus a Healthchecks.io free-tier ping for 05:45, and self-hosting the henrygd API in Docker to remove the dependency on a community instance.
8. **Passing grades: stop acquisition work until permission is sorted out.** Contact the poster/grader directly for a shared file or permission, and keep grades in a provenance-heavy side table (C7).

---

## 2. Volleyball-model evidence

Labels: **DEMONSTRATED** = shown in a named source with a stated method. **INFERENCE** = my reasoning from demonstrated facts. **HYPOTHESIS** = testable, not yet tested. **UNKNOWN** = searched and not found.

### Q1. Published rating systems, their inputs, and out-of-sample evidence

| System | Inputs | Home/neutral handling | Published out-of-sample accuracy |
|---|---|---|---|
| **Pablo** (RichKern.com; paywalled beyond a free comparison page) | Point % per match, capped (max 2500 at ~0.59 point share); now blended with a W/L model | Terry Pettit's profile of Rich Kern says Pablo "does factor in whether the match was played at home, on the road, or at a neutral site." Detection method: UNKNOWN (the ratings use scores logged at richkern.com, which is volunteer-curated) | FAQ asserts predictive value and says the combined model's accuracy is "similar" to pure points. **No Brier or log-loss figures published** (UNKNOWN). The richkern.com FAQ blocks automated fetching, so the claims come from search excerpts and a third-party reposting of the FAQ. |
| **VolleyDork** (Dwight Wynne; R code on GitHub "BTVB") | Rally-level Bradley-Terry: P(serving team wins rally) = f(rating diff + serve offset ± home) using NCAA play-by-play only. Matches without play-by-play are dropped. | Explicit home-court offset. Neutral handling not described (UNKNOWN). | None published. The example uses volleysim to turn side-out probabilities into match and 3-0/3-1/3-2 probabilities. |
| **Massey** (masseyratings.com cvol) | Not verified in this pass | Massey's general methods are known to include home/neutral terms, but the volleyball specifics were NOT VERIFIED | UNKNOWN |
| **FIGstats, Monster Block, VolleyMetrics research** | Not found in this pass | — | UNKNOWN. Treat any claims as unverified. |
| **Academic Bayesian volleyball** (Gabrio, arXiv 1911.01815; Egidi & Ntzoufras, arXiv 1911.04541) | Set and point abilities, zero-inflated Poisson components, set-difference outcomes | Home terms at set and point level (0.16 / 0.20 log-odds medians) | Model comparison by goodness-of-fit and predictive checks on single European leagues. Not NCAA; no transferable Brier figures. |
| **Margin-of-victory Elo** (Kovalchik 2020, tennis; Moreland & Superdock, arXiv 1802.00527) | Win/loss plus margin | — | Kovalchik: all MOV variants using within-set statistics improved predictive performance over standard Elo. Only the joint additive model gave unbiased ratings with stable variance in simulation. |

**INFERENCE, a counterpoint to the packet:** "Margin caps refused" contrasts with Pablo's design, which saturates at ~0.59 point share. POWER's refusal may be right, since caps discard information in lopsided D-I mismatches. But it was not tested against a *soft* cap or a logistic transform of point share. Pablo's cap exists because a point-share → win-probability curve is nonlinear. A per-set margin that is linear in z treats 25-10 as 2.6× the evidence of 25-19. That may overweight blowouts against weak opponents, which are common in a 348-team D-I.

**HYPOTHESIS H1 (exposure):** Evidence per match should be weighted by sets or rallies played, and k expressed in the same units. A 3-2 match carries ~5/3 the rallies of a 3-0. Under w = n/(n+k), counting matches treats them as equally informative. Convert k = 10 matches to k ≈ 10 × (mean sets per match) in sets and test chronologically. This is cheap and directly addresses the packet's own open question.

**Point margin vs set margin vs W/L — DEMONSTRATED in volleyball:** the multi-league home-advantage study showed that a Markov chain driven by point-level probabilities reproduces set-level outcomes. That means set results are a noisy, coarsened function of point-level strength. Pablo reports that adding W/L to points leaves accuracy about the same. POWER's own dynamic Bradley-Terry W/L-only model was worse (log loss 0.4809 vs 0.4667). All three agree: **points ≥ sets ≥ W/L as signal.** No published NCAA comparison with log loss was found (UNKNOWN).

### Q2. Do serve-receive or serve-pressure metrics predict future matches beyond margin?
- **DEMONSTRATED (concurrent only):** Peña, Rodríguez-Guerra, Buscà & Serra (J Strength Cond Res 2013, Spanish Superliga 2010–11) found "every additional point in Complex II increased the odds of winning a match by 1.5 times. Every reception and blocked ball error decreased the possibility of winning by 0.6 and 0.7 times." Palao (2018) found better reception led to better side-out in women's college volleyball. Sitting-volleyball work (PMC11658986) ties serve efficacy to match outcome. All of these are same-match associations. A same-match reception error is already *one point in the margin*, so these studies cannot show value beyond margin.
- **UNKNOWN:** No published split-half reliability of NCAA pass ratings, in-system %, or side-out % by matches played was found.
- **INFERENCE:** The only mechanism by which components beat margin on future matches is **stability**: a component with higher season-to-season or half-to-half reliability than margin, or one that predicts future margin better than past margin does. POWER's finding that "opponent-adjusted hitting diff is the strongest single factor over a full season" fits that mechanism. The small +0.0006 AUC suggests most of that stability is already captured by margin at k = 10.
- **Recommended measurement (not in the packet):** compute split-half reliability (odd vs even matches, Spearman-Brown corrected) for margin/set, hitting diff, side-out %, ace %, and service-error % at n = 4, 8, 12, 16, 20 matches on 2021–2025. Where a component's reliability curve exceeds margin's at small n, it earns a prospective test. Where it does not, drop it from the core.

### Q3. Opportunity vs efficiency (for the analysis page, C2/C5)
Opportunity-normalized forms that current NCAA box scores support (INFERENCE from box fields):
- **Kills:** kills/set = (TA/set) × (K/TA). Show both factors, because the first is opportunity (pace, rally length, setter distribution) and the second is termination.
- **Blocks:** blocks per opponent attack attempt, with team blocks = solo + ½ assists. Blocks/set conflates opponent volume with blocking skill.
- **Digs:** digs per *opponent non-terminal attack* = digs / (opp TA − opp K − opp E), bounded above by 1 plus dig error handling. Digs/set rewards playing opponents who hit lots of balls in.
- **Assists/set (challenge to metric 6):** under NCAA scoring an assist is credited only on a kill, so assists/set is mostly team kills/set. It is not a setter-quality measure. Setter evaluation needs set quality (not in public box scores) or, at best, team K% conditional on setter being in the lineup.
- **Serving:** aces/attempt and errors/attempt as a pair. Rally-win % while X serves (including errors) is sensible but confounded by rotation and opponent reception.
- **DataVolley/VolleyMetrics conventions (DEMONSTRATED):** DataVolley evaluates each skill on # + ! − / =. The openvolley `datavolley` package documents a "default" decoding (the DataVolley manual) and a separate "volleymetrics" style, confirming the two vendors use *different* conventions for the same symbols. Balltime/Hudl conventions: not verified.

### Q4. See §3 (data opportunities).

### Q5. Neutral sites and home edge
- **DEMONSTRATED (pro/elite):** point-share home edge is about 50.86% in Laios et al. (2012; Italy and Greece). Over a set of roughly 45 rallies (my assumption for typical NCAA sets), that is about 0.8 pts/set. VolleyDork's first 2023 fit had HCA = +44 on a scale of 1886, about 0.023 logit per rally. By my calculation that implies roughly 0.5 pts/set (INFERENCE from one early-season snapshot).
- **POWER's h = 1.0878 pts/set** implies a home point share of about 51.2% (assuming ~45 rallies/set). That is above both references. Neutral matches coded as ±1 should *bias h down*, not up, so the high value is not explained by contamination alone. It could reflect genuinely larger NCAA crowd and travel effects (HYPOTHESIS) or scheduling structure, where strong teams host weak teams and residual strength misfit leaks into h (HYPOTHESIS).
- **Internal inconsistency (INFERENCE, flag for Builder):** the forecast uses a home intercept of **+0.2675 pts/set**, about a quarter of the rating's h. If both were fit on 2025 data with neutral matches coded ±1, one of them is mis-specified. Possible explanations are dilution by neutral matches, the forecast being fit on blended scores that already absorbed home effects, or different populations. Settle this before C4.
- **Is the neutral correction material?** h/τ = 1.0878/2.437 ≈ 0.45 z per mislabeled match, applied in opposite directions to the two teams. It averages toward zero for teams with balanced tournament exposure but is systematic for teams whose early schedule is mostly neutral-site events. Early-season events are precisely when n is small and the per-match weight in the season term is largest. **INFERENCE:** material for early-season rankings of specific teams, probably small for aggregate full-season Brier. It is testable in 2026 from stored venues.
- **Variation by venue/crowd (DEMONSTRATED in the literature generally, not NCAA-specific):** home advantage varies by set (largest in sets 1, 4 and 5 in Marcelino et al.; none in set 5 in the multi-league study). Attendance links appear in pro studies. Pollard, Prieto & Gómez (2017, IJPAS 17(4):586–599) found home advantage across "31–35 countries (total: 328 seasons)," with "M = 56.62% in men's and M = 55.26% in women's premier-league volleyball" (2011–2015). NCAA venue-specific estimates: UNKNOWN.
- **Detection best practice (INFERENCE):** use a three-state H ∈ {+1, 0, −1} from a venue field compared with each team's home arena list. ncaavolleyballr's `team_season_info()` extracts arena information, which could supply 2020–2025 home arenas. Also add a separate "semi-home" flag for tournaments hosted by one participant.

### Q6. Reliability of forum passing grades
- **DEMONSTRATED (scale conventions):** DataVolley reception symbols # + ! − / = are defined in its handbook. VolleyStation's help centre defines # perfect, + good, ! within the 3 m line, − poor, / overpass, = error. US 0–3 and 0–4 numeric scales are common coach conventions with varying definitions; one analyst notes DataVolley's vote system can assign −3 to reception errors. A "0–3 grade" posted on VolleyTalk therefore depends on an **unstated mapping**, especially where "!" and "/" fall.
- **UNKNOWN:** No inter-rater reliability study of volleyball pass grading was found in this pass. Grader identity is unknown, and one account posted 88% of rows (626/709). Treat as single-rater, unvalidated data.
- **Licensed route for an individual: NOT FOUND.** Volleymetrics' VM Network states "Video and data files in the VM Network cannot be downloaded or shared." Its workflows in Hudl are limited to "Division I programs and pro teams in North America."
- **Terms risk (new, flag for Cody):** ProBoards' terms prohibit using "any engine, software, tool, agent, or other device or mechanism (including without limitation browsers, spiders, robots…) to harvest or otherwise collect information from the Website for any use." Reading in Chrome is ordinary use. Systematically transcribing 709 rows into a dataset arguably falls within "harvest or otherwise collect." The team's no-bypass stance is correct. The cleanest path is asking the poster for permission or a file.

### Q7. Championship profiles vs non-champions
- **UNKNOWN:** No published analysis of NCAA champion statistical profiles against non-champions was found.
- **Test design (recommended):** for each season 2013–2025 and each checkpoint date d (e.g., weekly), compute every team's PPS, *opponent-adjusted* PPS, and POWER. Report (a) the eventual champion's percentile at d, (b) how many teams exceed the champion band at d (the base rate), and (c) AUC for a larger positive class such as Final Four teams (~52 positives) or tournament match outcomes. With 13 champions and 348 teams, "champion" AUC has very wide uncertainty. Also note that A&M won the 2025 final at 16.67 PPS, below the band, which is a reminder that single-match PPS is noisy.
- **INFERENCE:** raw PPS mixes strength with schedule, since weak opponents give up more earned points. Any band must be opponent-adjusted before comparison.

### Q8. 5-1 vs 6-2 and setter changes
- **UNKNOWN:** No peer-reviewed evidence linking offensive system choice to team performance was found. Related work covers setter action range and first-tempo availability predicting side-out in European championships (PMC7504473), which is about set *location*, not system.
- **INFERENCE:** system choice is endogenous. Teams run a 6-2 when they lack a dominant setter or have surplus hitters, so any 5-1 vs 6-2 difference in outcomes is confounded. Stanford as a case study is n = 1 and generates hypotheses only. A defensible test is within-team switches: outcomes before and after a mid-season system change, compared with POWER's expectation. That sample will be small.

### Extra modeling topics

**Hitting floor (C1) — decomposition (INFERENCE, arithmetic):** evidence = 0.75·M + 0.25·(ΔHit/τ_hit). Moving τ_hit from 0.100 to 0.0668 multiplies the hitting term by 1.497. The effective weights become 0.75 : 0.374, which normalizes to 0.667 : 0.333, with total evidence scale inflated by 12.4%. The floor therefore matters in two ways: it silently lowers the hitting share to 0.25, and it changes the overall evidence scale that k, the display (50 + 12.5z) and the forecast slope (3.05) were fitted to. A clean C1 has three arms: (A) live; (B) τ_hit = 0.0668 with the forecast slope and intercept re-fitted on training data only; (C) live τ but weight 0.333, scale-matched. B vs C isolates scale from mix. That matches the Reviewer's request to separate scale change from calibration change.

**Shrinkage and prior blending:** the specifics of how KenPom, Sagarin, Massey and FiveThirtyEight blend preseason priors (their k-equivalents) could NOT be verified from official sources in this pass. Treat any quoted numbers as unverified. The principle, INFERENCE from Bayesian updating: w = n/(n+k) is the posterior weight when the prior and per-unit evidence variances are in ratio k. k should therefore be estimated in the same exposure unit as n (sets or rallies, per H1), from prior variance (preseason rho 0.8379) and per-set noise variance. That is a direct estimate, not a grid search on AUC.

**Calibration evaluation best practice (INFERENCE, standard methodology):**
- Use **log loss as the primary promotion metric** (strictly proper, punishes confident misses). Keep Brier as secondary, with a Murphy decomposition (reliability, resolution, uncertainty) and reliability plots by decile.
- Score **one forecast per match**, the last pre-match forecast, for promotion decisions. The 2025 "n = 11,284 observations" may count repeated targets across checkpoints, which understates uncertainty.
- Report paired per-match differences with a **block bootstrap by calendar week**. That is consistent with the Round-2 7-day blocks and respects shared teams and shared information within a week.
- Also report **AUC only as descriptive**. It ignores calibration.
- Live 2026 Brier of 0.1796 vs 0.1718 held-out 2025 is not an apples-to-apples decline. 2026 to date is early-season-heavy, where priors dominate and outcomes are harder to call. Compare on matched calendar windows.

**Power for C3 (INFERENCE):** roughly 348 teams × ~18 remaining matches ÷ 2 ≈ 3,000 D-I matches remain after 2026-09-26. If the per-match log-loss difference between two similar models has SD ≈ 0.03–0.05 (assumption; measure it on 2025), the standard error is ≈ 0.0005–0.0009. The minimum detectable improvement is therefore ≈ 0.001–0.002 log loss. The measured hitting effect is smaller than that. A candidate is only worth the one prospective slot if its expected effect is ≥ 0.002.

**Leakage without timestamps (INFERENCE):** the 89 ledgered corrections were applied retroactively, so backtests use data that was not available at the time. That is mildly optimistic. Mitigations:
- Bitemporal records: event_date, observed_at, source, content_sha256.
- As-known-then view = for each key, the latest record with observed_at ≤ t.
- For history, use git commit timestamps of raw files as upper bounds.
- Report backtest results both with the correction ledger applied and with it reversed.

**Experiment tracking (INFERENCE):** for a file-based project, git-tracked "receipts" are adequate and lowest-maintenance: a JSON file per run containing the config hash, data snapshot hash, code commit, metric values and bootstrap CIs. MLflow, W&B and DVC were NOT verified in this pass (pricing and terms), and they add operational burden disproportionate to one person.

---

## 3. Data opportunities

| Source | Owner | Coverage | Access route | Terms / permission status | Cost | Reliability | POWER gap |
|---|---|---|---|---|---|---|---|
| **ncaa-api (henrygd)** | Community (Hank / henrygd), MIT code; data belongs to NCAA/Turner | Live and historical ncaa.com scoreboard, game, box score, play-by-play, scoring summary | Public demo instance, "limited to 5 requests per second per IP"; README: "Host your own if you need it to be reliable long term"; Docker image; optional `NCAA_HEADER_KEY` access key | Code MIT. Upstream ncaa.com terms (via search excerpt) prohibit reproducing, publishing or commercial use of "statistics, updated scores". ncaa.com robots.txt does not block general crawling but blocks Scrapy and AI-bot user agents. Private use is low risk (INFERENCE); republishing is not permitted. | Free | Medium. v3.0.0 had breaking changes when the upstream "casablanca" endpoints were disabled. | Current backbone; point sequences enable the side-out/break-point channel |
| **ncaavolleyballr** (Jeffrey R. Stevens) | Academic author; code "MIT + file LICENSE" on CRAN; v0.5.1 | Functions for 2020–2025 D1–D3 men's and women's. Pre-scraped CSVs: WVB D1 teamseason, teammatch, playerseason, playermatch and **pbp including 2025**; D2/D3 through 2024. 0.5.1 added rally and event counters to play-by-play. | Download CSVs from the GitHub data page, or scrape stats.ncaa.org yourself (now needs Chrome via chromote) | Code MIT; **the data is NCAA content, not MIT-licensed**. README: "Accessing the website too frequently… can result in your IP address being blocked." Open issue #24: incomplete 2025 data. | Free | Good for history; **no 2026 in-season publication found** | C6 server rally-win % (2025 only), rotation reconstruction, validating the side-out channel |
| **stats.ncaa.org** | NCAA | Official box scores and play-by-play | Browser; automated access increasingly blocked (loading page, 403s reported) | NCAA.org terms: may not "frame, capture, harvest, or collect any part of the Site or Content without the NCAA's advance written consent". robots.txt: UNVERIFIED (a third party claims it disallows all). | Free to view | Low for automation | Not recommended for automation |
| **StatBroadcast** | StatBroadcast | Live stats for many schools | Web interface only | Grants use "solely for your personal, non-commercial use through the standard StatBroadcast web interface"; prohibits extraction by any other tool and scraping without written consent | — | — | **NOT PERMITTED** for automation. Only route is written consent. |
| **School sites (Sidearm / WMT / PrestoSports)** | Schools / platforms | Rosters, box scores, recaps, some play-by-play | Per-site; WMT /website-api is already crawled | Per-site terms NOT VERIFIED this pass. No official public API documentation found. | Free | Varies | Verification, rosters, availability |
| **Volleymetrics (Hudl)** | Hudl | Coded DVW data for subscribing programs | Team subscriptions; D1 programs and pro teams | "Video and data files in the VM Network cannot be downloaded or shared" | Team pricing, not public | High quality | **No hobbyist path**; restricted |
| **Balltime (Hudl)** | Hudl | AI stats from footage *you upload* | App/web; Player $20/mo; Recruiting $25/mo billed $299/yr (Hudl pricing page) | Requires your own footage and rights | See left | Unvalidated for NCAA broadcast footage | NOT a data source for NCAA matches |
| **VolleyTalk passing thread** | Forum users; ProBoards host | 2026 per-player 0–3 grades, partial | Human reading; guest-visible RSS exists (forum-wide recent posts, exact URL unverified) | ProBoards terms prohibit harvesting tools "including… browsers, spiders, robots"; bot challenge in place | Free | Unknown grader reliability | C7 only with permission |
| **Pablo / RichKern** | Rich Kern / Pablo author | Ratings and scores | Paid subscription (price not verified); free comparison page | Site disallows automated access | Paid | High, long-running | Benchmark comparator only (manual) |
| **VolleyDork BTVB code** | Dwight Wynne | Rally-level Bradley-Terry R code | GitHub | License not verified | Free | — | Method template for the side-out channel |
| **Commercial feeds** (Genius Sports / NCAA LiveStats, Sportradar, Stats Perform, SportsDataIO, API-Sports, TheSportsDB, ESPN's undocumented API) | Vendors | **NOT VERIFIED this pass.** Whether any sells NCAA WVB play-by-play to individuals is UNKNOWN. | — | — | — | — | RESEARCH NEXT only if there is budget appetite; assume enterprise-only until shown otherwise |
| **Kaggle/GitHub open NCAA WVB play-by-play datasets** | Various | UNKNOWN beyond ncaavolleyballr | — | — | — | — | — |

---

## 4. Technology / options matrix

Verification date for all entries marked VERIFIED: 2026-09-26. **UNVERIFIED** means I could not confirm it from an official page in this session. Do not act on it until someone checks it.

| # | Option (vendor, official source) | Type | Volleyball use / gap | Access, limits, verification status | Cost (subscription vs API/data) under stated workload | Fit, smallest trial, success, fallback | Rank |
|---|---|---|---|---|---|---|---|
| 0 | **No-new-purchase baseline:** existing Claude Code (Builder), ChatGPT (Reviewer), Gemini, Python/JSONL/git/static site, macOS launchd | Existing | Everything below except hosting auth | Already in hand | $0 incremental | The reference arm for every comparison | **TRY NOW (default)** |
| 1 | **Observation timestamps + SHA-256 content hash per appended record** (Python stdlib) | Code pattern | Leakage, C3 prerequisite | VERIFIED as standard library capability | $0 | Add `observed_at`, `source_url`, `sha256` to the writer. Success: 7 days of records with no nulls; the as-known-then query reproduces the live board for a past date. Fallback: git timestamps. | **TRY NOW** |
| 2 | **DuckDB `read_json`** (duckdb.org docs) | Local analytics engine (library) | Fast ad-hoc joins across JSONL without migration | VERIFIED: reads newline-delimited JSON, globs, many files in parallel; `filename` virtual column since v1.3.0 | $0 | `SELECT … FROM read_json('raw/*.jsonl', format='newline_delimited')`, read-only. Success: recompute one board metric exactly. Fallback: delete it; nothing changed. | **TRY NOW** |
| 3 | **launchd job + Healthchecks.io ping** (healthchecks.io) | Local scheduler + hosted dead-man's switch | Keeps 05:45 reliable and observable | VERIFIED (official healthchecks.io/pricing page): Hobbyist $0/month, "Monitor 20 jobs," 100 log entries per job; Supporter $5/month (same limits); Business $20/month (100 jobs); Business Plus $80/month (1,000 jobs). Open source (BSD), self-hostable. | $0 at 1–3 checks | One `curl` at job start and end. Success: an alert arrives within grace time when the job is deliberately skipped. Fallback: self-hosted Uptime Kuma (UNVERIFIED specifics). | **TRY NOW** |
| 4 | **Claude Code Desktop scheduled tasks** (code.claude.com/docs/en/desktop-scheduled-tasks) | Coding agent scheduler (local) | Daily research job, review of anomalies | VERIFIED: runs "only while the desktop app is running and your computer is awake"; missed runs are skipped, with one catch-up for the most recent miss within 7 days; stagger delay of a few minutes; per-task permission modes; runs can stall on permission prompts | Included in Claude subscription (plan prices UNVERIFIED this pass) | Use for *LLM-judgment* tasks (e.g., summarizing anomalies), **not** as the deterministic 05:45 data job. Trial: one weekly review task in a worktree. | **RESEARCH NEXT** |
| 5 | **Claude Code cloud routines** (claude.com blog; docs) | Cloud agent scheduler | Off-machine checks | VERIFIED: research preview; Pro, Max, Team, Enterprise with Claude Code on the web; fresh repo clone, no local files; minimum interval 1 hour | Included in plan; usage limits apply | Poor fit: data lives on the Mac. Only if the repo holds everything needed. | **LATER** |
| 6 | **GitHub Actions schedule** (docs.github.com) | CI scheduler | Off-machine daily run | VERIFIED: "The schedule event can be delayed during periods of high loads… If the load is sufficiently high enough, some queued jobs may be dropped"; minimum interval 5 min; default branch only. Community reports of dropped/late runs since 2026-08-26 (third-party). | Free-minute allowances UNVERIFIED this pass | Only as a backup trigger at an off-hour minute (e.g., :17), paired with a healthcheck | **LATER** |
| 7 | **OpenAI Codex** (help centre; chatgpt.com/pricing) | Coding agent (CLI/IDE/cloud) | Reviewer-side code checks | Official help text (older snapshot): Codex "is included in your ChatGPT Plus, Pro, Business, Edu, or Enterprise plan", with usage limits across local and cloud tasks; local usage extendable with an API key (billed separately). Current plan tiers and model names come only from third-party sites (e.g., a $100 Pro tier with 5× Plus Codex usage reported by VentureBeat): **UNVERIFIED officially** | Subscription separate from API billing | Reviewer could run read-only code review on PRs. Trial: one PR review. | **RESEARCH NEXT** |
| 8 | **Gemini CLI** (geminicli.com quotas page; GitHub README) | Open-source terminal coding agent | Third opinion; long-context reading of the repo | VERIFIED: signing in with a Google account (Code Assist for individuals) gives 1,000 model requests/user/day; an unpaid API key gives 250/day, Flash only; README cites 60 requests/min. Data-use and privacy terms for the free tier: UNVERIFIED; check before pointing it at private data. | $0 free tier | Trial: ask it to audit the home/neutral code path. Success: finds or rules out the h vs intercept mismatch. | **TRY NOW (read-only)** |
| 9 | **Self-hosted ncaa-api (Docker)** (github.com/henrygd/ncaa-api) | Self-hosted proxy | Removes the dependency on the community instance; controllable rate | VERIFIED: `docker run --rm -p 3000:3000 henrygd/ncaa-api`; optional header key. Upstream ncaa.com terms still apply. | $0 (needs Docker or another container runtime on the Mac) | Trial: run locally and diff one day's output against the public instance. Fallback: the public instance. | **RESEARCH NEXT** |
| 10 | **Local LLM runtimes** (Ollama, LM Studio, llama.cpp, MLX) and open-weight models (Qwen, Gemma, gpt-oss, Llama, Mistral, DeepSeek, Phi) | Local runtime | Alias matching and entity resolution, availability-phrase triage, OCR post-processing | **Not verified this pass** (model sizes, memory, licenses) | $0 software; hardware-bound | Any extracted number must be validated deterministically against box scores. LLMs are for proposing matches only. | **RESEARCH NEXT** |
| 11 | **OCR** (Apple Vision via Shortcuts/Swift, Tesseract, PaddleOCR, Docling, Marker) | Local extraction | User-supplied screenshots of permitted content | **Not verified this pass** | $0 | Only after passing-grade permission is resolved. Trial workload: ~30 screenshots/week; success = ≥99% cell accuracy on a hand-checked sample. | **LATER** |
| 12 | **Review queue** (a Streamlit app or a Google Sheet; Label Studio/Argilla heavier) | Human-in-the-loop | 89+ result corrections, alias resolution | Not verified this pass | $0 | A Google Sheet with status columns is the smallest option | **RESEARCH NEXT** |
| 13 | **Validation** (Pydantic / Pandera) | Library | Schema checks on append | Not verified this pass (both are open source, to my knowledge) | $0 | Validate the new timestamp fields first | **RESEARCH NEXT** |
| 14 | **Private admin board** (Cloudflare Access, Tailscale, Vercel/Netlify protection) | Hosting auth | Private board | **Not verified this pass** | Free tiers exist per vendors (UNVERIFIED) | Keep the local static site until needed | **LATER** |
| 15 | **Notifications** (ntfy, Pushover, Telegram, Discord webhook, email APIs) | Delivery | Job-failure alerts | Not verified this pass | — | The Healthchecks.io integrations may cover this | **LATER** |
| 16 | **News discovery** (RSS readers, Google Alerts, Bluesky, Reddit, X API) | Discovery | Availability/injury leads | Not verified this pass. X API costs in particular must be checked; do not assume any feed is complete. | — | Discovery only, never authoritative | **LATER** |
| 17 | **Balltime / Volleymetrics / VolleyStation / DataVolley purchases** | Data/analysis products | Pass quality | Volleymetrics data cannot be downloaded or shared; Balltime needs your own footage | Balltime from $20/mo (Hudl page) | Does not solve NCAA coverage | **NOT WORTH IT** |
| 18 | **Automating StatBroadcast, VolleyTalk or stats.ncaa.org scraping, or bot-challenge bypass tools** (browser-use, Firecrawl, Apify actors) | — | — | Terms prohibit it (StatBroadcast, ProBoards) or technical blocks are in place (stats.ncaa.org) | — | — | **NOT WORTH IT / NOT PERMITTED** |

---

## 5. Costs / access summary

| Item | Subscription | API/data cost | Verified? | Workload note |
|---|---|---|---|---|
| Baseline tools (existing) | Already paid | $0 incremental | n/a | — |
| DuckDB, Python stdlib hashing, launchd | $0 | $0 | DuckDB docs VERIFIED | Local |
| Healthchecks.io | Hobbyist $0 (20 jobs); Supporter $5/mo; Business $20/mo (100 jobs) | — | VERIFIED (official pricing page) | 1–3 checks |
| Gemini CLI | $0 | $0 within 1,000 req/day (Google login) | VERIFIED (official quota page) | Code audits only |
| Claude Code scheduled tasks / routines | Included in plan | Usage limits | Behavior VERIFIED; prices UNVERIFIED | Not for the deterministic job |
| Codex | Included in ChatGPT plans | API key billed separately | Inclusion VERIFIED (older official text); tiers UNVERIFIED | — |
| GitHub Actions | Free minutes (amount UNVERIFIED) | — | Delay/drop behavior VERIFIED | Backup only |
| henrygd ncaa-api | $0 | $0; 5 req/s on the public instance | VERIFIED | ~50 games + boxes + play-by-play/day is ~150–250 requests (INFERENCE), well within limits if spaced |
| ncaavolleyballr CSVs | $0 | $0 | VERIFIED | One-time 2025 download |
| Balltime | $20/mo Player; $299/yr Recruiting | — | VERIFIED (Hudl page) | Not applicable |
| Volleymetrics | Team contract | Not shareable | VERIFIED restriction | Not available |
| StatBroadcast automation | — | Written consent required | VERIFIED (terms excerpt) | Not permitted |

---

## 6. Proposed small trials (staged, pre-registered, reversible)

**Baseline for all trials:** the live POWER replica (k = 10, τ = 2.437, h = 1.0878, 0.75/0.25 blend, τ_hit = 0.100 floor, 4-pass fixed point, forecast 3.05·Δ + 0.2675, calibrated rally simulator), frozen by commit hash.

**Stage 0 (week 1, prerequisites):**
- T0a, C8 timestamps and hashes. Success: 100% of new records carry the fields.
- T0b, a git-history recovery script estimating upper-bound observed_at for 2026 raw records.
- T0c, a Healthchecks ping.
- T0d, a DuckDB read-only replica of one board metric, matching to 1e-9.

**Stage 1 (retrospective on 2021–2025, chronological, diagnostics only; no promotion):**
- T1a, split-half reliability curves by matches played for margin/set, hitting diff, side-out %, ace/error rates. Report where each crosses margin's curve.
- T1b, the home/neutral audit. Re-estimate h with three-state H where 2025 venues can be recovered; explain the 1.0878 vs 0.2675 gap.
- T1c, the C1 three-arm decomposition (live; τ_hit = 0.0668 with re-fit forecast; weight 0.333 scale-matched) at **k = 10**. Weekly block bootstrap on the paired per-match log-loss difference, last pre-match forecast only.
- T1d, H1 exposure: k in sets vs matches.
- T1e, validate side-out/break-point inference from point sequences against 2025 ncaavolleyballr server names. Success: ≥99% of rallies assign the correct serving team.
- Missing data: matches without linescores or play-by-play keep margin-only evidence, with an indicator. Never impute pass grades.
- Report all arms whatever the outcome. **Do not choose weights to make rankings look right; no inspecting top-25 orderings during selection.**

**Stage 2 (prospective, rest of 2026, C3):**
- Pre-register **one** candidate from Stage 1, chosen by the largest expected log-loss gain with a Stage 1 CI excluding 0. Likely T1b or T1d.
- Append-only pre-match log with observed_at, written before first serve. The primary metric is paired log loss on D-I vs D-I matches.
- Promotion rule: the upper 95% weekly-block-bootstrap bound of (candidate − live) log loss is < 0, and calibration slope is within [0.9, 1.1].
- Expect ~3,000 matches, with a minimum detectable effect of ≈0.001–0.002 (INFERENCE). If the candidate's expected effect is smaller, do not spend the slot.

**Stage 3 (product, C2/C5/C7):** analysis page with opportunity-normalized metrics, empirical-Bayes shrinkage toward conference or division means, and a matched-date champion base-rate table (Q7 design). Passing grades appear only as a labelled side table with source, grader and count.

---

## 7. Disagreements, conflicts, and open questions

**Where I disagree with the packet**
- *Builder:* describing ncaavolleyballr as an "MIT-licensed mirror" overstates it. MIT covers the R code; the play-by-play is NCAA content subject to NCAA terms. Publishing derived rally data on the site is a separate permission question.
- *Builder:* C1 as specified confounds weight and scale (see §2).
- *Packet:* "margin caps refused" is untested against a soft transform, and Pablo, the longest-running public system, saturates.
- *Packet:* assists/set as setter evaluation is mostly team kills.
- *Reviewer (agree, and extend):* the 2025 reuse problem also applies to h, τ and the forecast intercept, not only to new channels.

**Source conflicts**
- Healthchecks.io paid-tier prices differ across third-party listings. The official healthchecks.io/pricing page settles it: Hobbyist $0 (20 jobs), Supporter $5/month, Business $20/month (100 jobs; $192/yr annual), Business Plus $80/month (1,000 jobs; $768/yr annual). The $17 "Hobbyist" figure seen elsewhere is wrong.
- Codex plan and model names exist only in third-party posts dated September 2026. Verify on chatgpt.com/pricing before relying on them.
- ncaavolleyballr documentation says the pre-scraped data covers "2020-2024", while its listed files include 2025 WVB D1. Open issue #24 reports incomplete 2025 data.

**Questions for Cody**
1. Is anything derived from ncaa.com or stats.ncaa.org published publicly, or is the board private? This changes the terms risk.
2. Will you ask the VolleyTalk poster for permission or a file before any further capture?
3. Are raw JSONL files committed to git daily? (This determines whether T0b recovery is possible.)

**Questions for the Builder**
4. Where do h = 1.0878 and the forecast intercept 0.2675 each come from (data, fit, H coding)?
5. What is the per-match SD of the log-loss difference between live and the M3 shadow model on 2025? (This sets C3 power.)
6. Does ncaa.com play-by-play give the first server of each set, or must it be inferred?

**Questions for the Reviewer**
7. Do you accept last-pre-match-forecast-only scoring with weekly blocks as the promotion standard?
8. Should the prospective slot go to the home/neutral fix even though it partly changes "data handling" rather than "model"?

---

## 8. Source provenance notes

- **Official vendor or primary sources used:** Claude Code docs (desktop scheduled tasks; /loop scheduled tasks), Anthropic's routines announcement, GitHub Actions "Events that trigger workflows", the Gemini CLI quota page and README, DuckDB JSON-loading docs, the henrygd/ncaa-api README and releases, the ncaavolleyballr CRAN, pkgdown and rdrr documentation, NCAA.org terms of service, ncaa.com terms and robots.txt (terms via search excerpt), StatBroadcast terms (via search excerpt and mirror), ProBoards terms (search excerpt), Hudl pages (Balltime pricing, Volleymetrics transition FAQ, VM Network support article, Hudl Assist volleyball), the healthchecks.io pricing page, the VolleyStation help centre, the DataVolley handbook, and the openvolley datavolley docs.
- **Academic:** Marcelino et al. 2009 (J Sports Sci Med, PMC3763279); Laios, Kountouris & Kyprianou 2012 (IJPAS 12(2):272–281); the Chinese Women's Volleyball Association League home-advantage paper (IJPAS 2021); Pollard, Prieto & Gómez 2017 (IJPAS 17(4):586–599); Gabrio (arXiv 1911.01815); Egidi & Ntzoufras (arXiv 1911.04541); Kovalchik 2020 (IJF, via RePEc abstract); Moreland & Superdock (arXiv 1802.00527); Palao 2018 (J Sports Analytics 4(4):243–250); Peña et al. 2013 (J Strength Cond Res 27(9):2487–93); sitting volleyball (PMC11658986); setter action range (PMC7504473).
- **Third-party (lower weight):** the Rich Kern/Pablo FAQ (fetch blocked; search excerpt and DigNittany reposting), the Terry Pettit article, VolleyDork's methods post, Healthchecks.io aggregator listings, Codex pricing blogs and VentureBeat, GitHub community discussions on cron drops, a third-party claim about stats.ncaa.org robots.txt, and the Peña et al. summary (secondhand).
- **Could not be verified this session:** prices and limits for Claude and ChatGPT plans, xAI, Copilot, Cursor, n8n/Prefect/Dagster/Airflow/Windmill/Temporal, Zapier/Make, MLflow/W&B/DVC, uv/pixi, local-model memory requirements, OCR tool accuracy, hosting and auth free tiers, notification services, the X/Bluesky/Reddit APIs, all commercial sports-data vendors, Massey's and KenPom's methods, the full ncaa.com terms text, the stats.ncaa.org robots.txt, and the exact VolleyTalk RSS URL. These are listed as RESEARCH NEXT and should be verified from official pages before any decision.
- Access dates: 2026-09-26 (research session).