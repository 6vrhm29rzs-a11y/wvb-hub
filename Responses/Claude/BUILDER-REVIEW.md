# BUILDER REVIEW: Claude submission ("POWER Research Review", 2026-09-26)

This is an independent Builder review. I did not open the Reviewer's files. Everything here is research only and does not approve any build.

Files: the `.md` report and the `.pdf` carry the same report, so I treat them as one; I read the .md. `text.txt` holds a claude.ai share link and a chat summary of that same report, so it adds no new claims.

## Summary
- This is the most careful of the outside reports I have seen. It separates DEMONSTRATED, INFERENCE, HYPOTHESIS and UNKNOWN, and it marks the prices and vendors it could not verify.
- Its main new idea is wrong for 2026. It says side-out and break-point rates can come from "point sequences POWER already collects". We do not collect 2026 point sequences, only per-set totals (details under Errors).
- Its home-edge "internal inconsistency" is partly wrong. The forecast already sets the home term to 0 at neutral sites. The 1.0878 and 0.2675 figures are also fitted at different stages, so they are not directly comparable. The question is still worth answering.
- Several points are correct and useful: the C1 split of weight versus scale (the arithmetic checks out), the repeated-target concern about `heldout_n = 11284`, scoring one forecast per match, the weekly block bootstrap, and the split-half reliability curves.
- Its data and terms findings match our own policy. The healthchecks.io and henrygd details I checked agree with the official pages.

## Useful ideas (proposals)
1. **Split C1 into weight and scale (§2 "Hitting floor").** Moving τ_hit from 0.100 to 0.0668 multiplies the hitting term by 1.497. The mix becomes 0.667:0.333 and total evidence grows by 12.4%. I checked the arithmetic. The three-arm design (live / new τ with the forecast refit / same scale with weight 0.333) fits `digby_top25.py:412-436` and `forecast_calibration_2025.json` (slope 3.05).
2. **Score one forecast per match.** `data/forecast_calibration_2025.json` reports `heldout_n: 11284` from the odd checkpoints. 2025 had 5,131 games, so matches are counted more than once. The report's worry about understated uncertainty is supported.
3. **Use split-half reliability curves** for margin, hitting difference, side-out % and serve rates. 2025 has the needed inputs: box scores plus `pbp_player_2025.json` and `rotation_sideout_2025.json`, the side-out work that already exists.
4. **Test k in sets instead of matches (H1).** Cheap to try, because linescores give the number of sets.
5. **Audit home and neutral sites together (C4 extended).** Proposed: re-estimate h with three states from 2026 venues (`data/venues_2026.json`).
6. **Opportunity-normalised metrics for the analysis page:** kills = attempts × kill rate, blocks per opponent attempt, digs per opponent non-terminal attempt, and a warning that assists per set mostly tracks team kills. All of these fields are in our box scores (DATA-INVENTORY `boxscores_team_2026`).
7. **Observation timestamps and content hashes (C8).** Git commit times can serve as upper-bound observation times: `data/raw/2026/games.jsonl` is committed on every refresh (`git log` shows "refresh: new final(s)" commits). That also answers its Cody question 3.
8. **Free infrastructure trials:** launchd plus a healthchecks.io ping, DuckDB for read-only queries, and a self-hosted ncaa-api.

## Errors
- **E1 (factual, wrong against our system): the 2026 side-out channel from "point sequences POWER already collects".**
  - We store per-set **totals** only: `games.jsonl` linescores are one row per set.
  - `crawl_pbp.py` throws the raw play-by-play away after pulling out lineups (`OUT` is written "only with --keep-raw", lines 47 and 109).
  - CLAUDE.md records that ncaa.com play-by-play has `homeScore`/`visitorScore` null on most plays and names servers only on aces. So rally order, and therefore the serving team, cannot be rebuilt for 2026.
  - DATA-INVENTORY lists both `na_server_2026` and `na_rotation_2026` as UNAVAILABLE.
  - The idea works for 2025 only, where `rotation_sideout_2025.json` already exists.
- **E2 (mismatched): "neutral sites are coded as home or away" and the h-versus-intercept "inconsistency".**
  - It is true for the rating: `digby_top25.py:426` applies home_adv ±1 on every match.
  - It is false for the forecast: `predict_2026.py:176` uses `adv = 0.0 if site == "neutral"`.
  - The two numbers are different quantities. 1.0878 is the raw home margin per set. 0.2675 is an intercept fitted together with slope 3.05 on blended scores (`forecast_calibration_2025.json` `home_adv_pts`). Comparing them directly is not valid. The question of why they differ is still worth answering.
- **E3 (unit mix): comparing AUC with log loss.** The report sets a +0.0006 **AUC** difference against a log-loss detection threshold of 0.001–0.002 and concludes the hitting effect is "smaller". Those units do not compare.
- **E4 (characterisation): calling the hitting result "null-ish".** The hitting result had a CI clear of zero (`blend_hiteff_2025.json`: +0.00060, CI [+0.00030, +0.00089], verdict SHIPS). It is small, but it was measured, not null. The k=13.5 versus k=10 caveat is correct and already flagged in the packet.
- **E5 (minor):**
  - The detection-threshold calculation assumes the per-match log-loss SD is 0.03–0.05. That number is not measured. The report does admit it.
  - Its "~45 rallies/set" is an assumption. Our 2025 linescores could measure it.

## Evidence quality
- Academic citations are specific (journal, volume and pages, PMC and arXiv IDs). I did not open them.
- The Pablo claims come second-hand from search excerpts and a repost, which the report says itself.
- Commercial vendors are explicitly left UNKNOWN, which is correct.
- The pdf repeats the md, and text.txt repeats the summary.

## Link/file access log
- All three original files were read (md; pdf treated as a duplicate and not parsed; txt).
- healthchecks.io/pricing: **opened**. Confirms $0/20 jobs, $5, $20/100 jobs, $80/1,000 jobs.
- github.com/henrygd/ncaa-api: **opened**. Confirms 5 req/s per IP, the Docker command and `NCAA_HEADER_KEY`.
- claude.ai share link: **not attempted** (it holds the chat, not a source).
- masseyratings.com, stats.ncaa.org, statbroadcast.com, volleytalk.proboards.com: **not attempted (blocked by policy)**.
- The other cited sources (the Claude Code, GitHub Actions and Gemini docs, DuckDB, CRAN, the papers) were **not attempted** in this pass. They are unverified, not failed.

## Unresolved questions
- Why h (1.0878) and the forecast intercept (0.2675) differ, and how much of it comes from neutral matches coded ±1 in 2025.
- The measured per-match SD of the log-loss difference in 2025. This sets how much a prospective test can detect.
- Whether ncaavolleyballr's pbp data terms allow **publishing** derived rally metrics. Our public build would need that answer.

## Builder verdict
- **Adopt for research:**
  - the C1 three-arm split;
  - scoring one forecast per match with weekly blocks and log loss as the primary metric;
  - split-half reliability on 2021–2025;
  - k in sets;
  - the home/neutral audit, framed correctly;
  - timestamps and hashes plus git-time recovery;
  - the opportunity-normalised metric definitions.
- **Discard or correct:**
  - the 2026 side-out channel (no data; limit it to 2025 only);
  - the "forecast ignores neutral" claim;
  - the AUC-versus-log-loss comparison.
- **Later:** the infrastructure trials, which are Cody's call.
