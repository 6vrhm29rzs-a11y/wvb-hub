# POWER outside research — volleyball models and enabling technology

**Author role:** outside researcher (Grok), reading the 2026-09-26 packet plus current official/public sources.  
**Date:** 2026-09-26.  
**Status:** research only. No implementation, purchase, crawl, commit, live POWER change, or account access is authorized by this file.  
**Method:** packet critique first; then independent literature and product verification. Gemini product notes in the prompt are treated as unverified starting material, not architecture. The “Liv” spreadsheet is not treated as a project fact.

Verification dates are listed in §8. Product claims that could not be confirmed from official pages are marked as marketing, inference, or unknown.

---

## 0. How to read this file

Four kinds of statement are kept apart:

- **Evidence:** measured in the packet, or independently published with a method.
- **Hypothesis:** plausible, not demonstrated on POWER’s corpus or on a clean future split.
- **Recommendation:** a smallest reversible experiment, with a success criterion and a fallback.
- **Unresolved question:** for Cody / Reviewer / Builder.

Ranks used in the matrix: **TRY NOW** / **RESEARCH NEXT** / **LATER** / **NOT WORTH IT**.  
“TRY NOW” means a read-only or local experiment that does not change live POWER. It is not approval to ship.

---

## 1. Conclusions

1. **POWER’s predictive core is already in the same family as the best-documented public volleyball ratings.** Pablo converts point percentage into a rating difference. VolleyDork / BTVB fit a serve-level Bradley–Terry. Evollve (SSAC 2025) treats point-win percentage versus an average D-I opponent as the bulk of the rating. RallyIQ (collegevolleyball.app, live 2026) splits that into opponent-adjusted serve strength and receive strength. POWER’s live blend — opponent-adjusted scoreboard margin per set, a small hitting channel, and a preseason prior — is not an idiosyncratic invention. It is a defensible member of that family. That is a strength, not a reason to freeze inquiry.

2. **The packet’s own experiments and the external literature agree on a narrow claim and disagree on a broader one.** Narrow claim (supported): once you have opponent-adjusted point or rally outcomes, extra box-score channels add little *match-win prediction* on 2025-sized samples. Broader claim (not supported): component metrics carry no additional information, so they should never enter a rating. Reviewer addendum item 1 is correct. Round-2 C was “not distinguishable,” not “proven empty.” The CI on the 2025 rolling harness included both harm and help.

3. **Do not add weights to POWER before two cheap diagnostics and one prospective rule.** (a) Hitting-scale floor at live `k = 10` on the countable D-I set (Builder C1). (b) Neutral-site `H = 0` as a 2026-only shadow using stored venues (Builder C4). (c) If a richer candidate is still wanted, freeze one spec and score it pre-match on the rest of 2026 (Builder C3). Choosing weights so that a ranking “looks right” is explicitly out of scope.

4. **The analysis page and the rating should stay different products.** Cody’s ten metrics belong first as explanation with counts, roles, availability, and opponent context. That does not require a rating weight. It also does not require waiting for a prediction win. Descriptive work can start on data POWER already has.

5. **Licensed rally / pass-grade data is the real missing layer, and it is not available by scraping harder.** Hudl VolleyMetrics is the upstream touch-by-touch product used in the strongest player papers (e.g. arXiv:2402.01083; Kovar & Bame-Aldred SRP/M). College pricing is quote-only. Public-site republication of coded DVW files is not a documented right. VolleyTalk 0–3 grades are a community overlay with admitted errors; 510 candidate rows are not joined to game IDs. Forum crawling remains blocked and is not an option.

6. **ncaavolleyballr does not publish in-season 2026.** Confirmed 2026-09-26 from the GitHub README, CRAN citation (v0.5.1), and the package data page: extracted coverage is 2020–2025; 2025 D1 files were added after the season; NCAA stats pages now use live-browser scraping, are slow, and trigger IP bans. That answers packet question F4 in the negative for an open in-season feed.

7. **2026 team-level rally outcomes may still be recoverable from public PBP even if named servers are not.** RallyIQ claims to fit 2026 serve/receive strengths from public NCAA PBP that reproduces official set scores. That is team-level break % and sideout %, not a named-server file. POWER’s inventory marks named 2026 servers UNAVAILABLE; that can remain true while a team-level serve/receive split is still buildable from feeds POWER already crawls. Those two gaps should not be conflated.

8. **Technology spend should follow provenance, not model fashion.** The highest-leverage engineering changes are observation timestamps on every append, a review queue for user-supplied passing exports, a local DuckDB lens over existing JSONL, and keeping the live formula frozen while shadows run. Buying a second coding agent, a cloud warehouse, or a sports-data license does not fix leakage, aliases, or unjoined grades.

9. **Baseline to beat is the exact live model, not a reconstructed cousin.** Preserve `k = 10`, τ_hit = 0.100, hitting weight 0.25, and the current calibration population as A_live. Do not treat 0.0668 as “the new number” until it is re-estimated on whatever population the candidate uses. Do not treat Brier 0.129 and Brier 0.172 as the same quantity.

---

## 2. Volleyball-model evidence

### 2.1 What public systems actually use

| System | Unit of evidence | Opponent adjustment | Home | Box / skill channels | Prior | Public reproducibility | 2026 status |
|---|---|---|---|---|---|---|---|
| POWER (live) | Scoreboard pts/set + 25% hitting efficiency | Fixed-point current blended z, 4 iterations | Nominal home always; `h = 1.0878` pts/set from 2025 | Hitting only | 2025 + roster-delta + churn; blend `k = 10` | Internal repo | Live |
| Pablo (Rich Kern) | Point % converted to rating gap; later mixed with W/L | Yes (iterative / relative) | Adjustable; FAQ historically ~200 Pablo points | No public box channels | Not fully documented | Method described; code and current weights not open | Rankings page exists; full FAQ fetch was thin on 2026-09-26 |
| VolleyDork / BTVB (Wynne) | Serve-level Bradley–Terry (point when serving) | Joint MLE | Estimated serve and home offsets | None in the published ranking; separate expected-points work uses pass value | Mentioned as a planned Bayesian prior | R code on GitHub (`dpwynne/BTVB`) | Method page dated 2023; treat as method reference, not a 2026 live audit |
| RallyIQ (collegevolleyball.app) | Team break % and sideout % from PBP rallies | One-pass logistic, opponent receive/serve strengths | +0.7 pp on break and sideout (0.027 logits); **no neutral-site correction** after they tested it | AdjHit O/D from box scores; **explicitly not used in forecasts** | Last season RallyIQ −10% to mean + returning production; ridge ≈ 3 matches | Methodology page public | Live 2026 board; backtest quoted on site |
| Evollve (SSAC 2025 talk) | Expected point-win % vs average D-I on a neutral floor | Yes | Home teams win ~51% of points → ~59% of matches (talk claim) | Secondary | Prior-season × roster continuity | Talk, not a paper | Independent public product |
| Massey | Proprietary “Rat” / “Pwr” / HFA / SoS | Yes | Per-team HFA column shown | Unknown internally | Unknown | Closed | Live college volleyball board |
| NCAA / project RÉSUMÉ | RPI 25/50/25 unweighted D-I W% | Implicit via opponents’ W% | Not in RPI | No | None | Standard formula | Live, separate product |

**What this proves.** Several independent authors converged on *points or rallies, opponent-adjusted*, not on a ten-metric weighted index. Pablo’s documented conversion `game score = 25650 × (point% − 0.5)`, capped near 59% point share, is the same idea as POWER’s margin channel with a different link function. VolleyDork’s decision to model the serve rather than the match is the cleanest published alternative to POWER’s match-level margin.

**What this does not prove.** No public system published a clean, pre-registered 2026 forecast bake-off against POWER. RallyIQ’s own 2026 forward-chain numbers (site text: 74.5% accuracy, log loss 0.465 on 1,245 matches through 2026-09-19; 2025 OOS 77.6%, log loss 0.448 on 4,585) are **their** claims on **their** split. They are useful as an existence proof that a two-parameter serve/receive model can be calibrated, not as a license to copy their weights.

### 2.2 Packet results that still stand

These should not be re-run as fishing expeditions. They are evidence.

- Opponent-adjusting the season term helped: +0.021 AUC, CI clear (`blend_k_2025.json`).
- Live `k = 10` beat derived `k = 13.52` in the 2025 forecast receipt: Δ AUC +0.00147, CI clear. Derived k remains a crossover *gate*, and that gate is held.
- Hitting at 0.25 helped in the checkpoint walk: Δ AUC +0.00060, CI [+0.00030, +0.00089], at **k = 13.5 with the floor in place**. Hit-only was worse than margin.
- Receive-error channel: 0.25 mix inconclusive; 0.50 mix and receive-only harmed. Not shipped.
- Margin caps ±8/±10: inconclusive to negative. Refused.
- Round 2, 2025, 3,470 test matches, 7-day blocks: dynamic W/L-only (B) worse than A_clean (Δ log loss −0.0142, CI clear of zero, but grid-edge constrained). Dynamic set-strength + 4 box channels (C) Δ +0.0027, CI [−0.0073, +0.0117], **not distinguishable**. Hitting 0 vs 0.25 indistinguishable in that harness.
- 2026 live forecast record in the packet: 2,088 scored, Brier 0.180, favourite 73.2%. Held-out 2025 forecast Brier 0.172. The 0.129 figure is the rally simulator on *true* margin — a different quantity.

**Qualification the Reviewer already made, restated.** A_clean is a partially refit development baseline. 11,284 forecast observations are not 11,284 independent matches. 2025 has been reused for design, so it cannot validate a new idea cleanly.

### 2.3 Hitting-scale floor (packet §5) — evidence, not a bug report

Recomputed in the packet on 5,131 matches / 349 teams (≥8 matches): raw τ_hit = 0.0668, floored helper lifts it to 0.100. Effect: each match’s hitting evidence is divided by 0.100 instead of 0.0668, so the channel is ~0.67× a strictly measured scale. The shipped 0.25 weight was validated **with that floor**. Changing only the floor would move the channel to an untested ~1.5× strength.

Additionally: `hit_scale_2025()` read all 2025 finals, not the countable D-I set, which is why the team count is 349. Live `k` is 10, receipt `k` was 13.5. Those two mismatches are why C1 is a two-arm check, not a rewrite.

**Hypothesis, not evidence:** the floor is a useful regularizer. **Counter-hypothesis:** the measured scale is better and the 0.25 weight should be re-fit with it. Only the two-arm walk can separate those.

### 2.4 Do serve-receive or serve-pressure metrics predict beyond margin?

**Packet:** reception-error mix did not earn a weight. That is a team-box *error rate*, not a 0–3 pass grade, and not first-ball side-out.

**External evidence that uses richer data:**

- Kovar & Bame-Aldred (SSRN, 2025): Serve Reception Plus/Minus from VolleyMetrics PBP, 2021–2023. First-ball side-out % was the best tournament predictor in their bake-off; SRP/M helped when the two teams differed significantly. This is **licensed touch data**, not ncaa.com boxes.
- arXiv:2402.01083 (2022 NCAAW, 4,147 matches, 600k+ points, 5M+ contacts): Markov point model + hierarchical skill effects in a common “points gained” unit. Reception points-gained differs by role (DS vs front-only OH). Again VolleyMetrics-coded contacts.
- Substack “What Really Wins Sets?” (Power-4 set-level, 630 matches): Side-out % r ≈ 0.93 with set wins; point-scoring % ≈ 0.91; attack efficiency ≈ 0.89. Good-pass % beat perfect-pass %. **This is contemporaneous association with the same set’s result**, not a forecast of the *next* match. It is consistent with “components explain the margin they already sit inside.”
- VolleyDork “Top Servers” (2022): expected point value of the *pass the serve created*, isolating reception from the offense that follows. Requires pass grades.
- Art of Coaching 0–3 scale (public coaching notes): 3 = middle available, 2 = outside in system, 1 = free-ball, 0 = no return. Team rating = attempt-weighted mean. This is the same *stated* scale as the VolleyTalk thread. It is a coaching convention, not a validated grader.

**Inference.** Serve-receive can predict when it is a graded, opponent-adjusted, first-ball statistic. POWER has not tested that object. POWER has tested reception *errors*, which are a thin tail of the same skill. Failure of the thin tail is not failure of the full skill.

**Stabilization.** No published split-half reliability curve for NCAA WVB pass grades by match count was found in this pass. Treat “how many matches until a passer rating stabilizes” as an open measurement on 2025 ncaavolleyballr PBP (reception outcome, no 0–3 grade) and, separately, on any future authorized grade file.

### 2.5 Opportunity denominators

Standard coaching / NCAA-manual practice, not a new invention:

| Metric | Weak denominator | Better opportunity denominator |
|---|---|---|
| Kills / set | Sets | Attack attempts; also share of team attempts |
| Hitting % | Already an attempt rate | Split by rotation / role / in-system vs out-of-system if tagged |
| Digs / set | Sets | Opponent attacks that are diggable (attacks minus stuff blocks minus attack errors), or opponent kill attempts in play |
| Team blocks / set | Sets | Opponent attack attempts |
| Aces / S, SE / S | Sets | Service attempts |
| Reception errors | Sets | Reception attempts (already in the NCAA box) |
| Assists / set | Sets | Team attack attempts or team kills (assists ≠ set quality) |

NCAA Official Volleyball Statisticians’ Manual (2026 edition, verified 2026-09-26): team blocks = BS + ½ BA; hitting % = (K−E)/TA from summed counts; points column on some feeds is not a season total. Packet conventions already match the manual. Keep them.

**Hypothesis:** opponent-adjusted component profiles (Builder C5) are the right *analysis* frame. They are not, on current evidence, a rating input.

### 2.6 Home edge and neutral sites

**Packet:** `h = 1.0878` pts/set and `h_hit = 0.0292` on 2025, using the nominal home flag. Neutral sites are stored in 2026 venues and unused. Every match currently gets a home term.

**External:**

- Forman preprint (Oct 2025, ResearchGate, not peer-reviewed): across Elo / Glicko / SRS / BT / Colley / RPI on multi-season NCAA indoor VB, modern systems implied home-win odds ratios ≈ 1.54–1.64 at parity (about 60–62% home win). BT / Colley / RPI home estimates were specification-fragile. Treat magnitudes as provisional.
- Evollve SSAC talk: home teams win ~51% of points, ~59% of matches.
- RallyIQ: +0.7 percentage points on both break % and sideout %; they report that a neutral-site correction **did not improve forecasts**, so they omitted it.
- Chinese WVL study (Taylor & Francis, 2021): home set-win rates highest in sets 4, 5, and 1; skill-level home/away gaps small and set-specific.
- Big Ten realignment UROP abstract (2023–24): travel and nights away hypothesized to move home advantage; not a usable effect size for POWER.

**Synthesis.** A home edge of roughly 0.4–0.5 τ (packet: 1.09 / 2.44 ≈ 0.45) is large enough that crediting it on a true neutral floor is *interpretively* wrong. Whether fixing it improves *forecasts* is an empirical 2026-only question. RallyIQ’s negative forecast result is a prior that the gain may be small. That is not a reason to leave a known-wrong term in a strength rating that is shown to humans as “who would win tomorrow.”

### 2.7 Setter systems (Stanford case)

Packet: Stanford is Cody’s named hypothesis, not a finding. 5-1 vs 6-2 is already detected from starting lineups for 253 teams.

External: Berkeley Sports Analytics Group note “Set, Rotate, Dominate” reports 5-1 teams with higher kills/set and hitting % and 6-2 teams with slightly more blocks/set, on an unspecified sample. That is association, heavily confounded by which programs choose which system.

arXiv:2402.01083 discusses 5-1 vs 6-2 as a workload/role issue, not as a match-win predictor.

**Evidence-based position:** treat system and setter change as *analysis context* (workload, availability, who is setting out-of-system balls). Do not put a 5-1 dummy in POWER. Revisit Stanford only with rotation-level 2025 PBP plus 2026 lineup files, pre-registered, and with opponent adjustment.

### 2.8 Champion PPS profiles

Packet examples: Texas 2023 season PPS 18.03 (verified); Texas A&M 2025 18.48; Cody sheet mean ~18.69 across 13 seasons, **not all independently verified**. A&M won the 2025 final at 16.67 PPS and won 10 of 13 matches below 18.

**Required comparison, still missing:** champions vs non-champions at the *same date* in the season. October snapshots are not complete-season numbers. Until that table exists, 18.7 is a historical descriptive cluster, not a cutoff and not a model feature.

### 2.9 Fresh modeling ideas that are not in the current design

These are proposals for shadows or analysis, not live changes.

1. **Two-parameter serve/receive strength (RallyIQ / VolleyDork shape) as a frozen 2026 shadow.** Fit team break and sideout strengths with a home offset and a preseason ridge. Predict match win from a rally/set Markov already in `simulate_2025.match_dist`. Compare log loss to A_live. Uses team-level rally outcomes, not named servers.
2. **Split-half reliability by n matches** for each of the ten metrics, opponent-adjusted and raw. Tells the analysis page when a number is noise. Does not need a new feed.
3. **Hierarchical player points-gained on 2025 ncaavolleyballr PBP only.** Server rally-win, reception outcome (not 0–3), attack/block/dig if coded. Publish as player-page research, not POWER. 2026 stays unavailable for named servers unless an authorized source appears.
4. **Availability overlay, never a rating input until a pre-registered test says otherwise.** Packet already flags 1,149 2026 box-score absences. Pair with the sourced desk (12 evidence players) and show “lineup without X, margin in that window” as association.
5. **Exact-baseline plus one change.** Every candidate must publish A_live unchanged, then either (population change) or (scale change), not both unlabeled (Reviewer addendum item 3).
6. **As-known-then log.** Without observation timestamps, every 2026 backtest can leak later corrections (89+ already). This is a data-model prerequisite, not an analytics flourish.

---

## 3. Data opportunities

### 3.1 What POWER already has that is under-used for *explanation*

Already in inventory, unused or under-used for the analysis page:

- Team and player boxes 2025–2026: K, E, TA, SA, SE, serve attempts, RA, RE, digs, BS, BA, assists.
- 2026 venues and fixture ledger (neutral-site detection).
- Set-1 starting six and 5-1/6-2 detection.
- 2025 rotations and player-rally metrics from ncaavolleyballr (server rally-win, reception outcome, back-row share).
- Availability flags + small sourced desk.
- School-site verification graph (VERIFIED_BOTH 1,113 etc.).
- Returning production, churn, transfers.

That is enough to ship a *descriptive* ten-metric page with opponent context, role splits from roster position (labeled as roster position, not rally location), and sample sizes. It is not enough for pass quality, set location, block touches, coverage, or 2026 named servers.

### 3.2 Public / official feeds

| Source | What it actually is | Volleyball use | Access | Reliability | Rank |
|---|---|---|---|---|---|
| ncaa.com via self-hosted `ncaa-api` (henrygd/ncaa-api v3.2.0, MIT, Docker) | Unofficial HTML→JSON wrapper of public ncaa.com pages: scoreboard, game, boxscore, PBP | Current POWER raw path | Public demo 5 rps/IP; **self-host for reliability** | Upstream format changes have already broken game subroutes (v3.0.0 notes 502 / empty for some sports/seasons) | Keep; prefer self-host over the public demo. Not an official NCAA API. |
| stats.ncaa.org via ncaavolleyballr 0.5.1 | R scraper of official stats site; season / match / PBP | Historical 2020–2025 PBP with named servers (2025 used in POWER rotations) | Open-source; **not a license to hammer the site**. Author warns of IP bans and JS live-html slowness | 2026 in-season files are **not** published. 2025 D1 added post-season | RESEARCH NEXT for a one-time 2025 enrichment audit; **NOT WORTH IT** as a 2026 live crawler |
| School athletics sites / WMT website-api | Official school results, TV, rosters | Verification ledger, TV column, roster priors | Per-site; already in pipeline | Incomplete HTML; 169/185 availability-scan teams unreadable | Keep as human-cited verification, not as a new crawl wave |
| ESPN site/core API (unofficial community docs) | Scoreboard, teams, standings, news for `womens-college-volleyball` | Cross-check start times and finals; not a box-score system of record | Undocumented, unofficial, can change | Coverage thinner than ncaa.com for boxes | LATER as a disagreement detector, never as primary |
| Sportradar Volleyball API | Licensed live timelines, win probs, standings | Global indoor/beach; NCAA WVB coverage must be checked on their coverage matrix before any assumption | Paid developer license | Commercial SLA | NOT WORTH IT unless coverage matrix explicitly lists NCAA D-I WVB *and* a republication license exists. Do not infer NCAA coverage from “volleyball API.” |
| Hudl VolleyMetrics | Coach video + coded touches + optional DVW add-on | Pass grades, rotation, first-ball, setter quality | College packages **quote-only**. Club volleyball public menu is $500–$2,500/team/year and is the wrong product. DVW is an add-on on some tiers. Collegiate DataVolley roster files are free *to collegiate teams* | Gold-standard for player papers | RESEARCH NEXT only as a **permission conversation** with the data owner or a cooperating program. **NOT WORTH IT** as an unauthorized scrape or as a hoped-for public API |
| VolleyTalk passing thread | Forum 0–3 grades | Possible descriptive passing table | Reviewer browser blocked; bot challenge; Cody-session snapshot already taken | 218 source-flagged rows; 53 aggregates; 510 unjoined candidates | TRY NOW only on **user-supplied exports** + review queue. Crawler = not an option |
| Massey / FIG / Monster Block / AVCA | External boards | Benchmark columns, already captured manually | Browser / workbook | Third-party | Keep as disclosure references, never as inputs |

### 3.3 Passing grades — current honest state

B024 / mail 026 numbers, not re-litigated: 709 parsed rows, 510 single-match candidates, 0 game-id joins, 218 rows with source flags, 53 aggregate rows. Scale 0–3 and parenthetical attempts are forum-stated. GP% threshold undefined. Poster ≠ grader. One account posted 626/709 rows.

That snapshot is enough to design an ingest schema. It is not enough to compute a team passing rating.

**Minimum schema before any analytic use** (agrees with packet §D):

- match attribution (`gid`) confirmed against the fixture list  
- team_id, player_id after alias review  
- scale definition and attempt meaning as stated by that post  
- provenance: URL, author, post time, export file  
- syntax flag and source flags kept separate  
- scope: match / match_partial / weekend / season  
- no recomputed team mean until attempts reconcile  

Automation option A (user-supplied PDF/PNG → parse → review queue) is the only option that respects the site restriction.

### 3.4 2026 rally-level reality check

| Object | 2025 | 2026 |
|---|---|---|
| Named server on every rally | Yes, via ncaavolleyballr / stats.ncaa.org PBP (packet: 8,350/8,350 in a sample) | ncaa.com names servers on aces only. stats.ncaa.org scrape is hostile. StatBroadcast terms + 403. Inventory: UNAVAILABLE |
| Serving *team* and rally winner | Reconstructable from good PBP | RallyIQ claims this is available from public NCAA PBP for 2026 finals that reproduce set scores. POWER should verify on its own `pbp` / ncaa-api play-by-play for a 20-match sample before treating it as a feed |
| Rotation state | 96.5% of 2025 set-teams | Set-1 six in jersey order only |
| Pass grade 0–3 | Not in NCAA PBP | Not in NCAA PBP |

**Trial before any 2026 serve/receive model:** on 20 recent 2026 finals, parse ncaa-api `/game/{id}/play-by-play` and count (a) rallies with a serving team, (b) rallies with a named server, (c) agreement with official set scores. Success: ≥95% of rallies have a serving team and the reconstructed set scores match. If that fails, 2026 RallyIQ-style models are not buildable from POWER’s current feed.

---

## 4. Technology / options matrix

Each row: exact product, what it *is*, volleyball use, access, cost posture, fit, rank.

### 4.1 Research and coding assistants

| Product | Vendor / official page | What it actually is | Volleyball use / gap | Access and limits | Cost (separate chat vs API) | Fit / smallest trial | Rank |
|---|---|---|---|---|---|---|---|
| Claude + Claude Code | Anthropic, claude.com/pricing (checked 2026-09-26) | Consumer chat + terminal/web coding agent. Paid plans include Claude Code; usage shared with chat | Already the Builder. Good for packet work, receipts, guarded refactors | Pro $20/mo ($17 annual); Max from $100/mo (5× or 20×). API is a different bill (rate card PDF 2026-06-30; later cards through 2026-09-22). Do not assume chat tokens = API tokens | Subscription ≠ data license ≠ hosting | Keep. Trial = none needed | **Baseline / TRY NOW (already in use)** |
| ChatGPT + Codex CLI/app | OpenAI, developers.openai.com/codex/pricing.md and chatgpt.com/codex/pricing (checked 2026-09-26) | Chat assistant + coding agent bundled into ChatGPT plans; optional API-key billing | Second opinion on a frozen spec; unit tests; not a replacement Builder | Plus ~$20; Pro from $100 (5×) / $200 (20×). Codex usage is credit/token based as of Apr 2026. Model names move quickly (GPT-5.5 retirement posted for 2026-10-14 on ChatGPT/Codex) | Chat plan does not include a sports data API | Optional shadow reviewer on C1/C3 code, read-only | RESEARCH NEXT if a second agent is wanted; not required |
| Gemini / Gemini CLI / Code Assist / Antigravity | Google for Developers quota pages (updated 2026-06–08) | Consumer Gemini chat ≠ Code Assist seat ≠ Gemini API key ≠ Vertex. June 18, 2026: unpaid / AI Pro / AI Ultra Gemini CLI traffic moved to Antigravity CLI. Code Assist Standard/Enterprise still advertise Gemini CLI quotas (1,500 / 2,000 req/user/day) | Large-corpus document Q&A; possible OCR on passing screenshots | Code Assist Standard ~$19–22.80/user/mo annual/monthly (third-party summaries of Cloud pricing; confirm on Cloud console before buying). Gemini API is usage-based and separate | Do not inherit any Gemini-proposed architecture | Only if Google OCR/Workspace connectors are needed. Not a sports feed | LATER |
| Grok | xAI (this session) | Research assistant with live web tools | Outside research, literature pass, product verification — this document | SuperGrok session | No extra sports-data rights | Use for the research track, not for writing live rating code | **TRY NOW (this track)** |
| Local open-weight via Ollama | ollama.com (local runtime free; Cloud Pro $20/mo with $60 credits as of 2026-08-31 blog) | Local runtime + optional hosted open models | Private notes, alias review, passing-post classification without sending forum text to a cloud trainer | Local: hardware + electricity only. Cloud is a different product | Good for `Cody/data/vt_passing_2026/` classification if those files must not leave the machine | TRY NOW only if private-text handling is a hard constraint; otherwise existing cloud Builder is fine |
| Open-weight coding models (Qwen / gpt-oss / Gemma via Ollama or LM Studio) | Model cards on ollama.com / Hugging Face | Local weights, not a product support contract | Offline receipt regeneration, JSONL linting | VRAM-bound; 27B-class Q4 needs ~16–24 GB | Not a substitute for Claude Code on a multi-file repo | LATER |

**Rule:** a large context window does not grant ingestion rights, does not sync ncaa.com, and does not make a social search product into a complete live feed.

### 4.2 Storage, analytics, tracking

| Product | What it is | Use | Cost | Trial | Rank |
|---|---|---|---|---|---|
| Current JSONL + derived JSON | Files in repo | Provenance-friendly, append-only, diffable | $0 | Keep as system of record | **Baseline** |
| DuckDB (local, open source) | In-process analytical SQL over Parquet/JSON | Inventory audits, reliability curves, opponent-adjusted component profiles without a warehouse | $0 | Point DuckDB at `data_2026.json` / box JSONL; reproduce Kentucky/A&M/Stanford scores | **TRY NOW** |
| MotherDuck | Hosted DuckDB. Free/Lite: official docs 2026-09-25 list Lite with 10 CU-hours + Pulse; marketing page also shows a $25 Lite and $100–$250 Business — **figures disagree across official surfaces, so treat paid tiers as “confirm on checkout”** | Shared SQL if more than one analyst queries the same snapshot | Do not buy until local DuckDB is useful | RESEARCH NEXT only after local DuckDB earns its keep | LATER |
| SQLite | Embedded relational | Same niche as DuckDB, weaker analytics | $0 | Inferior to DuckDB for this workload | NOT WORTH IT vs DuckDB |
| MLflow / W&B / sacred | Experiment trackers | Receipts already live as JSON in `data/blend_*` and `Cody/coordination/research/prototype/` | W&B is SaaS; MLflow can be local | A folder of frozen JSON receipts plus git is enough at this scale | NOT WORTH IT until many concurrent shadows exist |
| dbt / SQLMesh | Transformation layer | Overkill for 88 inventory rows and one season builder | Time cost | Skip | NOT WORTH IT |

### 4.3 Extraction, review, orchestration

| Product | What it is | Use | Notes | Rank |
|---|---|---|---|---|
| Existing Python parse + human review queue | In-repo pattern already used for result_review_queue | Passing ingest option A | Extend; do not replace | **TRY NOW** |
| OCR (existing stack first: ocrmypdf / tesseract; cloud Vision APIs only if needed) | Document text | Cody-supplied passing PDFs/PNGs | Page-1 PDF in the packet is already text-extractable | TRY NOW on supplied files only |
| Browser automation | Playwright etc. | **Not for VolleyTalk.** Permitted only on sources already in policy (school sites, ncaa.com via current crawlers) | Reviewer site restriction stands | NOT WORTH IT for passing |
| GitHub Actions / existing 05:45 research job | Scheduler | Already records frozen shadows | Add C1/C4 shadows here when approved; do not add new third-party cron SaaS | Baseline |
| n8n / Zapier / Make | iPaaS | Notifications | Personal accounts stay isolated; a mail/Slack ping is not worth a new vendor | LATER / probably NOT WORTH IT |

### 4.4 Visualization and hosting

Team analysis page is a product goal, not a vendor goal. Ship HTML/static from the current builder first. Observable / Streamlit / Dash are optional later and none of them supply data. Authenticated admin access is an ops decision for Cody/Reviewer, not a research result. No hosting vendor is recommended in this pass.

---

## 5. Costs and access (workload-explicit)

Assumed research workload, next 8 weeks, **no live change**:

- 1–2 humans reviewing receipts and passing queues  
- existing Builder agent on the repo  
- no new crawl of blocked sites  
- one or two frozen shadow models logged beside M3  

| Item | Incremental $ | What you get | What you do not get | Privacy |
|---|---|---|---|---|
| Status quo (files + current crawl + current agents) | $0 extra | Live POWER, inventory, M3 shadow | Named 2026 servers, pass grades | Current |
| DuckDB local | $0 | SQL over existing files | Collaboration / hosting | Data stays local |
| Claude / ChatGPT / Grok subscriptions already in use | $0 incremental if seats exist | Research + code review | Sports licenses | Vendor training policies differ; do not paste private passing dumps into a tool whose training default is on |
| Second coding-agent seat | $20–$200/mo | Redundant opinions | Accuracy | Extra copy of repo context in another vendor |
| MotherDuck Lite/Business | $0–$250/mo plus compute; confirm live SKU | Hosted SQL | Better ratings | Data leaves the machine |
| Hudl VolleyMetrics college package | Quote-only; club menu $500–$2,500/team/yr is the wrong SKU | Video + coded touches for *subscribed programs* | A public republication license (not documented) | Contractual; Shared Data license in Hudl TOS is broad **for Hudl**, not for a third-party public board |
| Sportradar Volleyball API | Sales quote | If and only if NCAA WVB is in the coverage matrix | Pass grades | Contract |
| ncaavolleyballr 2026 live scrape | $0 money, high ban/ToS risk | Maybe PBP | A stable feed | Against author’s own guidance |
| Self-hosted ncaa-api | One small VM or local Docker | Independence from 5 rps public demo | Official NCAA blessing (there is none) | Same public pages as today |

**Do not imply** that a ChatGPT, Claude, Gemini, or Grok subscription includes a sports API, VolleyMetrics, or ncaa.com bulk rights. Those are separate products.

**NCAA.com terms** (ncaa.org terms of service, page current as of 2026-09-11) assert ownership of statistics and scores and restrict reproduction beyond the terms. The project already consumes public pages through an unofficial wrapper. That is an existing legal/ops posture, not something this research expands. No new scraper is recommended.

---

## 6. Proposed small trials

Each trial is reversible, has a success test, and names a fallback. None is approved by being written here.

### T0 — Freeze the live replica (prerequisite)

- **Do:** serialize A_live constants (`k=10`, τ_hit=0.100, hit weight 0.25, h=1.0878, current prior file, countable-match definition) into a dated receipt. Recompute Kentucky / Texas A&M / Stanford from that receipt.
- **Success:** exact match to `digby_top25_2026.json` scores in the packet example.
- **Fallback:** stop. Do not run T1–T4 against a moving target.
- **Rank:** TRY NOW.

### T1 — Hitting floor two-arm check (Builder C1)

- **Do:** 2025 checkpoint walk, live `k=10`, countable D-I only, τ_hit ∈ {0.100, 0.0668}. Paired Δ AUC, Δ log loss, Δ Brier, block bootstrap CI. No grid. Do not recompute 0.0668 on a new population and then treat it as sacred.
- **Success:** a CI that is either clearly helpful, clearly harmful, or clearly a wash. Document the floor as a regularizer if it is a wash or harmful to remove.
- **Fallback:** keep 0.100 and say so.
- **Rank:** TRY NOW (read-only).

### T2 — Neutral-site shadow on 2026 only (Builder C4)

- **Do:** from `venues_2026.json` + fixture ledger, set H=0 when the venue is not either team’s home arena. Leave 2025 untouched. Score 2026 forecasts against A_live on log loss. Report how many matches flip classification.
- **Success:** a documented match list + paired log-loss delta. Promotion is *not* automatic even if the delta is good.
- **Fallback:** keep nominal home; show a “neutral, unadjusted” badge on those matches on the analysis page.
- **Rank:** TRY NOW (shadow).

### T3 — Twenty-match 2026 PBP audit

- **Do:** for 20 school-verified 2026 finals, parse current PBP. Count serving-team tags, named servers, reconstructed set scores vs official.
- **Success:** serving-team present on ≥95% of rallies and set scores match. Then a RallyIQ-shaped shadow is *eligible* to specify (T5). Named-server rate is a separate number and may stay near zero.
- **Fallback:** mark 2026 rally splits UNAVAILABLE with evidence, not folklore.
- **Rank:** TRY NOW.

### T4 — Passing ingest on user exports only (option A)

- **Do:** parse Cody’s existing PDF/PNG plus any new exports he drops in. Alias table. Review queue for every syntax or source flag. Attempt `gid` join against fixtures by team pair + date window (post date ≠ match date).
- **Success:** a table in which every analytic row has gid, scope=match, and no blocking source flag. Target is not “510.” It is “N joined and reviewed.”
- **Fallback:** leave passing out of every page.
- **Rank:** TRY NOW. No crawler.

### T5 — One pre-registered 2026 shadow (only if T0 and T3 pass)

Choose **one**:

- **S-rally:** team break/sideout strengths + existing Markov, ridge to current prior, or  
- **S-C:** frozen Round-2 C spec, or  
- **S-comp:** margin + one opponent-adjusted first-ball proxy built from boxes (opponent kill % on our serve-receive error rate is the honest box-only version)

Write the spec before seeing residuals. Log pre-match next to M3. Primary metric log loss; report early/late, conference, missing-box, neutral. Promotion rule is Cody’s, stated in advance.

- **Rank:** RESEARCH NEXT. Not simultaneous with a hitting-floor change.

### T6 — Descriptive analysis page from existing boxes

- **Do:** season and rolling values for the ten metrics, summed counts, opponent-adjusted versions with n and a simple league-mean shrink, role from roster position labeled as such, availability flags visible.
- **Success:** a page that answers “is A&M’s serving good, or did it face poor passers?” with uncertainty, without touching POWER.
- **Rank:** TRY NOW as product work; it is not a model change.

### T7 — Champion vs non-champion PPS at matched dates

- **Do:** for each historical champion week, take every D-I team’s PPS from the same date cutoff. Plot distributions. Verify the 12 sheet values against original box sources where possible.
- **Success:** a distribution, not a threshold.
- **Rank:** RESEARCH NEXT.

### Explicitly not trials

- Buying VolleyMetrics or Sportradar “to see.”  
- Switching warehouses.  
- Adding receive-error weight because the literature likes passing.  
- Re-fitting k, τ_hit, and population in one step.  
- Treating 510 passing candidates as observations.  
- Any start-time/TV commit (still unresolved operationally in the packet).

---

## 7. Disagreements, counterarguments, unknowns

### 7.1 Where this research disagrees with the packet narrative

- **“Box stats mostly explain without predicting” is directionally right and over-sold.** The receive test and Round-2 C support humility about *weights*. They do not support a veto on all future component models, especially not serve/receive models that use different objects than reception errors.
- **“The rest of 2026 is the only possible OOS evidence” is too absolute** (Reviewer item 5). Agreed. A frozen shadow on the remaining 2026 is still the *best available* honest test. Other future seasons would also qualify. That does not authorize 2025 re-mining.
- **RallyIQ’s “neutral site didn’t help forecasts” should not freeze C4.** Forecast utility and rating honesty are different. A strength number that assigns a home edge to a tournament floor is misleading even if log loss is flat.
- **ncaavolleyballr in-season 2026** is not an open question anymore. It does not publish it. Remaining question is whether *POWER’s own* 2026 PBP contains serving-team tags.

### 7.2 Where this research agrees with Reviewer over Builder

- C2 as sequencing (analysis page before new weights): agree.  
- C2 as a claim that richer prediction is closed: disagree.  
- Hitting receipt is not “validated as shipped” in the broad sense: agree. Floor behavior was present; live (`k=10` + floor + countable set) was not jointly measured.  
- C1 must not hard-code 0.0668 onto a new population.  
- Brier 0.172 vs 0.129 must stay separate.  
- 88 inventory rows are grouped field sets, not 88 feeds.

### 7.3 Where Builder C proposals should go

| ID | This research |
|---|---|
| C1 hitting floor | Do first. |
| C2 analysis-first | Do as product sequencing. Do not treat as a scientific close. |
| C3 one prospective candidate | Yes, after T0/T1/T3, one only. |
| C4 neutral sites | Shadow on 2026. Likely worth shipping for honesty even if forecasts are flat. |
| C5 opponent-adjusted components | Analysis page. No weight. |
| C6 server rally-win % | 2025 yes from existing PBP. 2026 named-server no unless T3 surprises. Team-level 2026 maybe. |
| C7 passing | Option A only. |
| C8 observation timestamps | Do; cheap; enables honest C3. |

### 7.4 Unknowns that still bind

1. Who actually grades the VolleyTalk numbers, and is Volleymetrics the upstream (Cody’s suspicion, unverified)?  
2. GP% definition.  
3. 2026 ncaa.com / ncaa-api PBP serving-team completeness (T3).  
4. True NCAA WVB home-win probability at parity on *POWER’s* countable set, with venues.  
5. Split-half reliability of each ten-metric series.  
6. Whether 2025 venue can be recovered from school schedules (Reviewer: absence in files ≠ impossibility). Not authorized to collect here.  
7. Start-time / TV five-check drift — operational, still unresolved, not a rating issue until a correction crosses the PT midnight boundary.  
8. Sportradar and other commercial matrices: NCAA D-I WVB listed or not. Not checked match-by-match in this pass.  
9. MotherDuck’s public price surfaces disagree with each other; any purchase needs a live checkout, not this memo.  
10. Legal posture of unofficial ncaa.com wrappers if the project becomes more public than it is today — ops/legal, not a model question.

### 7.5 Questions for Cody / Reviewer / Builder

**Cody**

- Is the analysis page the next public surface even if POWER stays frozen through the 2026 tournament?  
- For C3, which one candidate do you want frozen: S-rally, S-C, or S-comp?  
- Will you keep dropping VolleyTalk exports, and can you ask the thread owner / grader for a structured file?  
- Are you willing to treat 18.7 PPS as a historical cluster rather than a benchmark line on the page?

**Reviewer**

- Confirm T3 (20-match PBP audit) does not violate any site rule beyond current ncaa-api use.  
- Confirm passing option A (user files only) is in bounds.  
- What promotion threshold do you want written *before* T5 residuals exist?

**Builder**

- Can observation timestamps be added to the append path without touching the formula?  
- Can venues_2026 already distinguish “home-arena template printed on a neutral floor”? Packet already warns that `/game` location can be that template. If so, C4 needs the fixture ledger, not the raw location field.  
- Reproduce T0 against HEAD `5f46398` before any diagnostic branch.

---

## 8. Source list

Accessed or checked 2026-09-26 unless noted.

### Packet (given)

- START-HERE.md, CURRENT-MODEL-AND-DATA.md, DISCUSSION-AND-PROPOSALS.md, DATA-INVENTORY.csv  
- Latest review B024, TECHNOLOGY-RESEARCH-SCOPE.md, REVIEWER-ADDENDUM.md, PASSING-QUALITY.md  

### Volleyball ratings and methods

- VolleyDork, “Rankings: How They Work,” https://www.volleydork.com/post/volleydork-rankings-how-they-work  
- VolleyDork, “Top Servers in NCAA Women’s Volleyball (2022),” https://www.volleydork.com/post/top-servers-in-ncaa-womens-volleyball-2022  
- BTVB, https://github.com/dpwynne/BTVB  
- DigNittany, Rich Kern / Pablo comparison and method excerpt, https://dignittanyvolleyball.com/rich-kern-poll-comparisons/  
- RichKern rankings page (thin fetch), https://www.richkern.com/vb/rankings/FreePageRankings.asp  
- RallyIQ ratings and methodology, https://collegevolleyball.app/ratings and https://collegevolleyball.app/methodology  
- Massey NCAA D1 women’s volleyball ratings, https://masseyratings.com/cvol2024/ncaa-d1/ratings  
- SSAC 2025 talk “Digging In” (Evollve method claims), https://www.youtube.com/watch?v=Ny-DEQBUs2Y  
- Forman, “Comparing Opponent-Strength Measures for NCAA Indoor Volleyball” (preprint, Oct 2025), https://www.researchgate.net/publication/396741898_Comparing_Opponent-Strength_Measures_for_NCAA_Indoor_Volleyball_-_Predictive_Accuracy_and_Home_Advantage_Stability  

### Player / component / passing literature

- “Estimating individual contributions to team success in women’s college volleyball,” arXiv:2402.01083, https://arxiv.org/html/2402.01083  
- Kovar & Bame-Aldred, “Serve Reception Plus/Minus,” SSRN 5339496, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5339496  
- “What Really Wins Sets?” (Power-4 correlations; contemporaneous, not forecast), https://substack.com/home/post/p-188992799  
- Art of Coaching serve-receive 0–3 notes (PDF), https://www.theartofcoachingvolleyball.com/wp-content/uploads/2022/07/AOC-HS-Champions-Clinic-Kyle-Mashima-Bonus-Presentation-Notes.pdf  
- Berkeley Sports Analytics Group, “Set, Rotate, Dominate,” https://sportsanalytics.studentorg.berkeley.edu/articles/set-rotate-dominate.html  
- NCAA 2026 Volleyball Statisticians’ Manual, https://s3.amazonaws.com/fs.ncaa.org/Docs/stats/Stats_Manuals/Volleyball.pdf  

### Home advantage and related

- Qiu et al., *International Journal of Performance Analysis in Sport* (2021), Chinese WVL home advantage  
- Michigan UROP abstract, Big Ten realignment and home advantage  
- JMM 2026 abstract, men’s NCAA home-court metrics  
- Joe Trinsey, Smarter Volley “Coin Flips” (receive-first set odds; small tournament sample)  

### Data tools and official-adjacent feeds

- ncaavolleyballr v0.5.1, https://github.com/JeffreyRStevens/ncaavolleyballr ; data page https://jeffreyrstevens.github.io/ncaavolleyballr/articles/data.html ; r-universe page dated 2026-09-19  
- henrygd/ncaa-api v3.2.0, https://github.com/henrygd/ncaa-api ; public OpenAPI https://ncaa-api.henrygd.me/  
- NCAA.org terms of service, https://www.ncaa.org/terms-of-service/ (page dated 2026-09-11)  
- NCAA women’s volleyball statistics hub, https://www.ncaa.org/championships/statistics-and-records/womens-volleyball/  
- ESPN unofficial volleyball endpoint notes, https://github.com/pseudo-r/Public-ESPN-API/blob/main/docs/sports/volleyball.md  
- Sportradar Volleyball API marketplace page, https://marketplace.sportradar.com/products/6531568e4c579e32d10a16c5  
- Hudl VolleyMetrics support (DVW add-on, 2026 NCAAW team files updated 17 Sep 2026), https://support.hudl.com/s/article/data-volley-material-and-information-volleymetrics  
- Hudl pricing hubs (college = quote; club volleyball published), https://www.hudl.com/pricing and https://www.hudl.com/pricing/club/volleyball  

### Assistants, local models, analytics infra

- Claude pricing, https://claude.com/pricing ; rate cards https://claude.com/pricing/rate-cards  
- OpenAI Codex pricing, https://developers.openai.com/codex/pricing.md ; https://chatgpt.com/codex/pricing/  
- Gemini CLI quotas, https://geminicli.com/docs/resources/quota-and-pricing/ ; Code Assist quotas https://developers.google.com/gemini-code-assist/resources/quotas ; FAQ on June 18 2026 Antigravity cutover  
- Ollama transparent pricing blog, 2026-08-31, https://ollama.com/blog/transparent-pricing  
- MotherDuck pricing model docs, https://motherduck.com/docs/about-motherduck/billing/pricing/ and marketing https://motherduck.com/product/pricing (surfaces disagree; flagged in §5)  

### Not used as authority

- Unverified Gemini product-comparison paste  
- Any affiliate “best AI coding agent of 2026” list  
- VolleyTalk thread content beyond what the packet already captured (no new site access)

---

## 9. One-page recommended sequence

If a joint review wants a default plan that does not spend money and does not touch live POWER:

1. T0 freeze A_live.  
2. T1 hitting-floor two-arm on 2025, countable D-I, `k=10`.  
3. C8 timestamps on the append path.  
4. T3 twenty-match 2026 PBP audit.  
5. T4 passing option A on files Cody already has.  
6. T6 descriptive ten-metric page from current boxes.  
7. T2 neutral-site 2026 shadow.  
8. Only then T5, one frozen shadow, rest of 2026.

Anything that requires a vendor quote, a new account, or a new crawl waits for a second joint review.

*— End of research file. No implementation authorized.*
