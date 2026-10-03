# POWER Correction Addendum: Paper Identities, Hudl Data Access, Home Terms, Exposure Weighting, Inference Plan, Digs, and 2026 Event Data

Several earlier claims were wrong as stated: the arXiv author attributions, the blanket Volleymetrics "cannot be downloaded" restriction, the "internal inconsistency" allegation about home terms, the 5/3 rally-weighting and "scale-equivalence" argument, and the invented detectable-effect calculation. Others stand once properly qualified: digs ≤ opponent zero attacks as an accounting check, serving-team inference from rally scoring once an anchor is known, and the StatBroadcast/ProBoards/Hudl automation prohibitions. No primary NCAA Division I women's volleyball home-edge estimate and no published prospective NCAA volleyball Brier/log-loss benchmark were found in this pass (NOT FOUND, which is not proof that none exist).

## TL;DR
- The three arXiv papers are now correctly attributed (1911.01815 Egidi & Ntzoufras, Italian men's SuperLega 2017/18; 1911.04541 Ntzoufras, Palaskas & Drikos, Greek men's A1 2016/17; 1911.08791 Gabrio, Italian women's Serie A1 2017/18). All three are 12-team round-robin professional leagues, so their model *structures* transfer to NCAA and their fitted numbers and validation results do not.
- Hudl's own documentation limits the "cannot be downloaded or shared" rule to the VM Network (matches outside a team's level of play). DVW files within a team's level of play are a purchasable add-on, and DVW/XML export is "currently supported in Volleymetrics" with Hudl support "coming later". What POWER itself is entitled to remains UNKNOWN, and Hudl's User Terms separately prohibit automated extraction.
- Nothing in the evidence establishes double-counting between the rating's h = 1.0878 and the forecast's 0.2675. Weighting by sets conditions on the outcome. Detectable effects cannot be quoted until the paired per-match log-loss difference SD and its clustering are measured on 2025 with the Round-2 harness. The next three investigations should be (1) a clean chronological re-benchmark plus venue audit, (2) one pre-registered hitting-channel comparison at live k=10, and (3) a rights-first test of serving-team inference validated against 2025 files where servers are named.

---

## 1. Plain-English takeaway

- The old 0.172 Brier is a historical artifact. It is not a held-out score for today's model, and no replacement has been computed. Before any "is feature X worth it" claim, POWER needs one clean chronological benchmark of the *current* code, scored once per match.
- The two home numbers (1.0878 in the rating, 0.2675 in the forecast) do different jobs at different stages, so a numerical gap between them proves nothing. A venue-aware residual audit could reveal a real problem. Comparing the two numbers cannot.
- Hitting evidence is neither proven useless nor proven valuable at live settings. The earlier AUC gain and the newer log-loss result measure different things in different harnesses at a different k.
- Rich serve and side-out description is feasible *historically* (2025 files name every server). For 2026 it depends on data rights and on anchoring each set's serving sequence, and neither is settled.
- Descriptive team profiles (serving pressure, side-out rate, opponent hitting allowed) are legitimate even where they have not earned a forecast weight.

---

## 2. Corrections and evidence table

| Earlier claim | Status | Corrected statement | Primary source (section/date) |
|---|---|---|---|
| (a) "Gabrio, arXiv 1911.01815"; "Egidi & Ntzoufras, arXiv 1911.04541" | CORRECTED | 1911.01815 = Egidi & Ntzoufras, "A Bayesian Quest for Finding a Unified Model for Predicting Volleyball Games" (v2, 15 Apr 2020). 1911.04541 = Ntzoufras, Palaskas & Drikos, "Bayesian Models for Prediction of the Set-Difference in Volleyball" (IMA J. Management Mathematics). 1911.08791 = Gabrio, "Bayesian Hierarchical Models for the Prediction of Volleyball Results" (compiled 21 Nov 2019). | https://arxiv.org/abs/1911.01815 ; https://arxiv.org/abs/1911.04541 ; https://arxiv.org/abs/1911.08791 (abstract pages and PDF title pages) |
| (b) Blanket "Volleymetrics data cannot be downloaded or shared" | CORRECTED (scope) | The sentence "Video and data files in the VM Network cannot be downloaded or shared" applies to the **VM Network page**, which Hudl describes as where "you can find matches that are played outside your level of play". Separately, "DVW files are available as an add-on to some subscription tiers… a downloadable DVW file for every match within your level of play, so long as you have access to the match and it has been analyzed." | https://support.hudl.com/s/article/vm-network-recruiting-development-volleymetrics (section "Download"); https://support.hudl.com/s/article/data-volley-material-and-information-volleymetrics ("How do I access DVW files?") |
| (c) "Internal inconsistency" between h = 1.0878 and intercept 0.2675, implying double-counting/misspecification | CORRECTED (withdrawn) | The two constants sit at different stages, fit different targets and use different populations and neutral handling, so a numerical difference is not evidence of a defect. A valid audit is specified in §3 Q3 and Appendix C. | Packet model facts; code facts per Reviewer (scripts/predict_2026.py, scripts/digby_top25.py) |
| (d) Weight by sets/rallies ("3-2 ≈ 5/3 the rallies of 3-0"); k in sets; τ_hit ×1.497 "equivalent" to 0.667:0.333 weights, "total evidence scale inflated 12.4%"; 3-arm C1 | CORRECTED | The fifth set is played to 15, so 5/3 overstates exposure. Set count also depends on the outcome, so weighting by it conditions on the outcome. The ×1.497 ratio and the 0.667:0.333 normalisation are arithmetically right **only for the performance-deviation terms**. They are not equivalent to a weight change, because the z_opp terms, margin-only matches, prior blending, opponent iterations and the 348-team display normalisation all break equivalence. "12.4%" is a sum of coefficients, not an evidence-scale change. C1 is replaced by three separate comparisons (Appendix A). | Fifth set to 15: Egidi & Ntzoufras, arXiv 1911.01815 §2(e) and eq. (4) "rs = 25−10×I(Rs=5)" |
| (e) C3 power "SE ≈ 0.0005–0.0009, MDE ≈ 0.001–0.002; hitting effect smaller than that"; AUC 0.0006 compared with a log-loss threshold | CORRECTED (withdrawn) | The SD values were assumed, not measured, and the AUC-versus-log-loss comparison mixes metrics. The replacement is a formula plus measurement plan (§3 Q5, Appendix B). The Round-2 intervals themselves have half-widths of about 0.009 for their specific arm pairs, which argues against sub-0.002 resolution for arbitrary pairs. | Packet Round-2 results |
| (f) digs/(opp TA − opp K − opp E) as defensive opportunity metric | QUALIFIED | Valid as an **accounting check**: "A team's total digs cannot exceed the number of 'zero attacks' by its opponent" (put-backs explain shortfalls). It is **not** a defensive success probability. See §3 Q6. | 2026 NCAA Volleyball Statisticians' Manual, "Statistics Accuracy Check" (5)–(6); Section 4 Art. 1; https://s3.amazonaws.com/fs.ncaa.org/Docs/stats/Stats_Manuals/Volleyball.pdf |
| (g) Infer serving team per rally from previous-rally winner | QUALIFIED (stands conditionally) | Under rally scoring, the rally winner serves next. So once the serving team at **any one rally in a set** is known (first server, or a named ace or service error), a complete and correct score sequence gives every rally's serving team. Missing rallies and unlogged replays break the inference, and so do documented score reversals: NCAA Rule 8.1.4.1 (new for 2026) lets referees correct scoring discrepancies "without a coach's protest" and "consult the statistics crew or use the Challenge Review System", and Rules 10.3.2.3 and 13.2.3.2 require points to be "canceled" after position or rotation faults. | NCAA Women's Volleyball Rules 8.1.3.1.1–2: "If the serving team wins a rally, it scores a point and continues to serve… If the receiving team wins a rally, it scores a point and gains the right to serve." (see §7) |
| (h) Point-share home edge 50.86% ≈ 0.8 pts/set; POWER h ≈ 51.2%; VolleyDork HCA +44/1886 | QUALIFIED | 50.86% comes from Italian and Greek first-division men's and women's leagues (6,681 games, 25,324 sets, 1,122,064 points), not NCAA. Using that paper's own 44.3 points/set, 50.86% ≈ 0.76 pts/set, so "≈0.8" is arithmetically fine for *that* population. Mapping h to 51.2% assumes an NCAA rallies-per-set figure that has not been measured, and treats a per-match evidence adjustment as a population share. VolleyDork was not re-verified and is not primary. **A primary NCAA D-I women's home-edge estimate was NOT FOUND.** | Laios, Kountouris & Kyprianou, "The Existence of Home Advantage in Volleyball," Int. J. Perf. Analysis in Sport 12(2), Aug 2012, pp. 272–281 (authors per Crossref): https://www.tandfonline.com/doi/abs/10.1080/24748668.2012.11868599 (abstract) |
| (i) ncaavolleyballr MIT covers code not data; stats.ncaa.org needs headless browser; StatBroadcast and ProBoards terms prohibit automated collection; no hobbyist route to Volleymetrics | QUALIFIED / mostly STANDS | CRAN lists "License: MIT + file LICENSE" for the package (v0.5.1, published 2026-01-07). No separate data licence was found, which is different from data being "prohibited". The package imports `chromote` (headless Chrome), and its README warns that NCAA site changes have "greatly slowed data scraping and has resulted in unstable connections". StatBroadcast and ProBoards prohibitions STAND with quoted clauses (§4). "No hobbyist route" becomes: no individual or hobbyist tier found in the Hudl documents reviewed. The support articles are addressed to team Administrator/Coach roles. | https://cran.r-project.org/web/packages/ncaavolleyballr/index.html ; https://jeffreyrstevens.github.io/ncaavolleyballr/ ; §4 terms rows |

**Where I disagree with the reviewers (with evidence).** The critique describes a dig as charged only on an attack "that would have resulted in a kill". The 2026 manual does not say that. Section 4, Article 1 reads: "A dig (D) is awarded when a player passes the ball that has been attacked by the opposition. Digs are given only when players receive an attacked ball and it is kept in play, not when a ball is brought up off a 'put back' (blocked ball)." The "would have" wording in the manual appears in Section 1 A.R. 3, and it concerns whether a setter's dump counts as an attack attempt. The reviewers' conclusion (digs/zero-attacks is not a success probability) still holds, for the reasons in §3 Q6.

---

## 3. Answers to the open questions

### Q1. Paper identities, designs and transfer

| | 1911.01815 Egidi & Ntzoufras | 1911.04541 Ntzoufras, Palaskas & Drikos | 1911.08791 Gabrio |
|---|---|---|---|
| Population (VERIFIED) | Italian SuperLega (men's professional), 2017/18 | Greek A1 men's professional, 2016/17: 132 regular-season matches, 494 sets, 12 teams, double round-robin, plus play-offs | Italian women's Serie A1, 2017/18 regular season: 132 matches, 12 teams |
| Target (VERIFIED) | Two levels: set winner (logistic), then loser's points given the set winner (right-truncated negative binomial, r = 25 or 15), plus a Poisson inflation for extra points past deuce. Home effect and team abilities on every layer. | Match set-difference (−3…+3), via an ordered multinomial logistic model and a truncated Skellam model | Three joint modules: points per team (independent Poisson, log-linear attack/defence plus home λ), fifth-set indicator, match winner. Match-level serve/attack/defence/block efficiencies enter as covariates. |
| Validation (VERIFIED in outline) | Goodness-of-fit diagnostics and out-of-sample prediction measures (Section 5), plus MCMC replications reconstructing the final table (Section 5.3). The abstract reports "exceptional reproducibility of the final league table and a satisfactory predictive ability". The exact holdout split was not extracted in this pass (UNKNOWN). | Posterior predictive regeneration of the league. Out-of-sample: (i) mid-season split-half (first half trains, second half tests); (ii) play-off prediction from regular season plus earlier rounds | "Two alternative model specifications… validated using data from" the 2017/18 season. Whether any validation was out-of-sample was not extracted (UNKNOWN). |
| What transfers (HYPOTHESIS) | Set-then-points hierarchy; explicit 15-point fifth set; deuce inflation; within-match set correlation via random effects. All are useful if POWER ever models set or point outcomes directly. | Ordinal set-difference likelihood as an alternative target to margin per set; the split-half and play-off validation *templates* | Joint modelling of margin, fifth-set occurrence and winner |
| What does not transfer (HYPOTHESIS) | Fitted parameters, predictive-accuracy claims and the 12-team dense round-robin identification. NCAA has 348 teams, a sparse schedule graph, a large strength spread and preseason priors. | Same issues; its data were touch-level scouting data collected by a co-author, which POWER does not have in-season | Box-score efficiencies *from the match being predicted* are not available pre-match, so as specified it is not a pre-match forecaster unless those covariates are themselves forecast. The independent-Poisson points assumption is criticised by Ntzoufras et al. §1.1. |

Bottom line: none of the three validates anything about POWER. They are sources for likelihood structures, not benchmarks.

### Q2. Volleymetrics / Hudl access (VERIFIED facts; entitlement UNKNOWN)

Product and access layers, kept separate:

- **Volleymetrics, own level of play.** Video exchange runs through conference "Open Exchange" participation. DVW download is a paid add-on "for every match within your level of play, so long as you have access to the match and it has been analyzed" (DataVolley Material & Information article). The Online Statistics page has no export ("There is not currently a way to export or print statistics directly from the Online Statistics Page") (Statistics Explained article).
- **VM Network.** This covers matches *outside* the team's level of play, available through sharing or a purchased package: "Video and data files in the VM Network cannot be downloaded or shared." This network-specific rule does not govern a team's own-level coded files.
- **Hudl (post-transition).** The FAQ says "Data Volley DVW and Sportscode XML file exports are currently supported in Volleymetrics and support will be coming to Hudl later." Volleymetrics remains usable through 2026-27, and "Starting summer 2027, all teams will move to Hudl." (https://www.hudl.com/products/volleymetrics/transition/faq)
- **Balltime / Hudl Assist volleyball.** Balltime documents "Export > Spreadsheet (CSV)" for stats from selected games (https://support.hudl.com/s/article/export-stats-balltime). The Hudl Assist volleyball page is a marketing page. It does not show which NCAA teams or matches are covered.
- **Redistribution and automation.** The Hudl User Terms prohibit using "any automated means, including bots, scrapers, crawlers, or artificial intelligence tools, to access, collect, or extract data from the Services… except… as Hudl may otherwise expressly permit in writing" (https://www.hudl.com/terms). Redistribution rights for DVW files sit in team subscription agreements, which are not public (UNKNOWN).
- **Individual eligibility.** The support articles are scoped to "roleOnTeam: Administrator, Coach" at "Elite" organisations. No individual tier was found (NOT FOUND).

Establishing POWER's entitlement would need: (1) the named program(s) whose account would supply the data; (2) that program's subscription tier and whether the DVW add-on was purchased; (3) the subscription agreement's clauses on third-party use, derivative analytics and sharing; (4) written permission for any automated retrieval under the Hudl User Terms; (5) where other teams' matches arrive via exchange, whether exchange terms allow use outside the receiving team.

### Q3. Why h and the forecast intercept can differ, and a valid audit

VERIFIED structure: h (1.0878 pts/set) is subtracted from each observed margin, using the *nominal* home flag, before the margin is converted to opponent-adjusted evidence. The forecast intercept (0.2675 pts/set) is a separately calibrated constant in margin = 3.05·Δscore + 0.2675, and it is set to zero for venues classified neutral.

Reasons the two can legitimately differ (HYPOTHESES, none yet measured):
1. **Different regression target.** h adjusts observed performance within a match. The intercept is the expected margin at Δscore = 0 after mapping *shrunken, display-normalised* scores through a fitted slope.
2. **Shrinkage and attenuation.** Scores are blended toward preseason priors (w = n/(n+k)) and normalised over 348 teams. If Δscore is noisy relative to true strength, the fitted slope and intercept absorb part of that error.
3. **Venue-strength confounding.** If stronger programs host more often, Δscore correlates with H, and some of the home-associated margin can load on the slope rather than the intercept.
4. **Neutral mislabelling.** The rating uses nominal flags, and neutral detection is not built (the /game location can be a home-arena template). Any stage fitted with nominal flags on neutral-heavy data attenuates toward zero, and the two stages may attenuate by different amounts.
5. **Different populations and seasons** for the two fits.

**Valid audit (Appendix C has details).** Use 2025, chronological, one last pre-match forecast per match, from the Round-2 rolling-block harness running the *current* code. Venue class comes from a hand-verified label set (true home, true away, verified neutral). Compute:
- (i) The residual margin r = observed − predicted, regressed on venue class, with week-block bootstrap or two-way team clustering.
- (ii) Calibration-in-the-large and logistic recalibration slope and intercept for win probability, by venue class.
- (iii) The chained home swing (predicted margin for the same pair at home minus away).
- (iv) A team-level test: forecast residual against the share of home matches in the team's *past* schedule.

**What would indicate a problem:**
- A residual home coefficient whose CI excludes zero *and* exceeds a pre-registered practical size.
- Neutral-class calibration offsets.
- A non-zero slope in (iv), since over-adjustment by h would under-rate home-heavy teams, who would then beat their forecasts everywhere.

A numerical mismatch alone indicates nothing.

### Q4. Rally exposure and scale equivalence (CORRECTED; see Appendix A)

- Sets are unequal exposure (the fifth is to 15). The number of sets is decided by the outcome, so weighting by sets or rallies gives a dominant 3-0 less weight than a scrappy 3-2 and biases evidence against dominant teams.
- Per-set margin already normalises by duration.
- Proper alternatives:
  - A per-point or per-rally likelihood, e.g. Egidi & Ntzoufras's set/points hierarchy.
  - Heteroskedastic variance modelled on *pre-match expected* closeness, not realised set count.
  - Sandwich/robust variance for inference.
- The rescaling of τ_hit is not equivalent to a weight change once priors, margin-only matches, z_opp, opponent iterations and display normalisation are included.
- Three comparisons must stay separate:
  - (1) an exact replica of the live configuration;
  - (2) the countable D-I population with its **own re-measured** τ_hit (0.0668 is not transplanted);
  - (3) the floor versus the measured scale on the *same* population.

### Q5. Inference plan (see Appendix B)

Order of operations: (1) fix a chronological design; (2) fix the unit; (3) estimate dependence-aware uncertainty; (4) only then discuss detectable effects.

- **Unit.** One forecast per match: the last pre-match forecast. If checkpoints are used instead, cluster by match and by week.
- **Dependence.**
  - Matches share teams, and weeks share information states.
  - Use 7-day block bootstrap (as in Round-2) or two-way clustering (team-pair × week).
  - Report effective sample size n_eff = n / DEFF.
- **Multiplicity.** Pre-register **one** primary comparison and metric. Everything else is secondary and labelled exploratory.
- **Practical size.** Cody should set a smallest effect size of interest (SESOI) in product terms before running: for example, a change large enough to flip a meaningful number of favourite picks among ~2,000 matches, to move reliability-bin calibration, or to change top-25 membership week to week. It should not be an arbitrary log-loss number.
- **Equivalence.** Non-significance is not equivalence. Declare equivalence only if the 90% CI of the mean paired difference lies inside ±SESOI (two one-sided tests, TOST).
- **AUC versus log-loss (qualitative only).** AUC measures ranking discrimination and is blind to calibration. Log-loss rewards both calibration and sharpness. A small AUC gain can coexist with zero or negative log-loss change (and vice versa), so the two are not interchangeable thresholds.
- **Three layers, kept distinct.** The +0.00060 AUC interval excluding zero (checkpoint walk, k=13.5) is *statistical evidence* in that harness. Its *practical size* is undetermined. *Transfer* to live k=10 is untested. Round-2's hitting 0 vs 0.25 "indistinguishable" is not evidence of no effect.
- **Complementarity.** A weak standalone feature can still add information through its partial correlation with future margin after conditioning on margin evidence (orthogonalised component), through out-of-fold stacking, or through different reliability at small n (early season). Test these explicitly rather than inferring from standalone results.

### Q6. Digs and defensive opportunity

VERIFIED (2026 manual):
- Total attacks = kills + errors + zero attacks.
- A zero attack "is any attack attempt that is kept in play by the opposition".
- Accuracy check (6): digs ≤ opponent zero attacks; the shortfall includes put-backs, which "do not count as blocks statistically".
- Free balls, overpasses and keep-alive plays are **not** attack attempts (Section 1 exceptions), so they are outside TA altogether.

Why digs/zero-attacks is not a defensive success probability:
1. The denominator mixes very different balls:
   - attacks deflected off the block and played by defenders (a dig, A.R. 13c);
   - blocked-and-recycled balls kept in play by the attacking side (a "0 attack" with no dig, A.R. 7c);
   - aggressive setter dumps (A.R. 3/4);
   - down balls that count as attacks only "in the opinion of the statistician" (A.R. 2b).
2. Attacks that deflect off a block out of bounds are **kills**, not zero attacks (A.R. 13a), so some genuine defensive failures never enter the denominator.
3. A saved ball that the team cannot keep in play earns no dig and becomes the attacker's kill (Section 4 A.R. 1; Section 1 A.R. 6).
4. Statistician judgment varies by host, and judgment calls are final once ruled (Compilation Guidelines).

So the ratio mostly measures the gap from put-backs and scoring practice. It works as a data-quality flag, not as skill.

Honest descriptive alternatives from the current box score (VERIFIED as computable; interpretation HYPOTHESIS):
- Opponent kill% allowed (oppK/oppTA).
- Opponent hitting efficiency allowed ((oppK−oppE)/oppTA).
- Opponent attempts per set.
- Block share: team blocks (BS+½BA)/oppTA, and blocks/oppE. The manual guarantees team blocks ≤ opponent hitting errors.
- Opponent attacks-in-play rate (opp zero attacks/oppTA), which reflects both attacker and defence.
- Opponent-adjusted versions of each: allowed minus the opponents' attempt-weighted typical value against *other* teams.

Extra observations needed to measure real defensive opportunities: attack outcome coding with block-touch flags, dig quality grades, transition outcome (whether the dig led to a kill), free-ball versus attack context, and rally-level sequences.

### Q7. 2026 event availability and passing

- **First server per set.**
  - The packet says ncaa.com play-by-play names servers only on aces (VERIFIED per Builder). ncaavolleyballr's stats.ncaa.org-derived files (2020–2025) name servers on every rally.
  - For 2026 ncaa.com data, the first server is not directly given. It can be *inferred* (HYPOTHESIS, testable): any named ace, or a named service error if present, anchors that rally's serving team, and the rally rule then propagates forwards and backwards through a complete score sequence.
  - The inference breaks with missing rallies (score jumps), score corrections (score decreases; NCAA Rule 8.1.4.1, new for 2026, lets referees correct scoring discrepancies "without a coach's protest", and Rules 10.3.2.3 and 13.2.3.2 require points to be "canceled" after position or rotation faults), unlogged replays, and penalty or point adjustments recorded out of order. Penalty points do not all follow the rally rule. Individual misconduct penalties give "Point and service awarded to opponent" (Rules Table 1). A non-compliant-uniform red card, however, "does not change the service order" (Rule 6.5.1.2), and the Table 3 note says "Service does not switch. Serving team continues to serve." Those sanctions must be flagged.
  - Under the 2026–2027 NCAA Women's Volleyball Rules, Rule 13.1.2, "the first service of the match and any deciding set is executed by the team determined by the coin toss… The other non-deciding sets start with service by the team that did not serve first in the previous set." So one anchor in set 1 fixes the first server of sets 2–4, while set 5 still needs its own anchor.
  - Serving order is **not** the six-player on-court lineup.
- **Coverage.**
  - Which schools and conferences post ncaa.com play-by-play is UNKNOWN; it has to be measured.
  - StatBroadcast's "315+ Universities, 40+ Conferences" is a marketing claim and does not establish volleyball play-by-play coverage.
  - Sidearm/WMT/Presto host school box scores. Genius Sports/NCAA LiveStats coverage and terms were not researched (UNKNOWN).
- **VolleyTalk passing.**
  - 709 parsed rows are not validated matches.
  - The poster may be relaying a team's, a broadcaster's or another fan's grades. Grading scale, observer and match selection are unknown.
  - Joins to games remain unresolved.
  - Treat these as anecdotal until grader identity and scale can be documented.

### Builder's additional questions

- **Benchmark (VERIFIED per Reviewer).** The historical 0.1718 mixed full-season home and signal-scale estimates with checkpoints whose later matches overlap between slope fitting and scoring. Its 11,284 is checkpoint observations, not unique matches. No replacement exists, and it must not be compared with the 2026 live Brier of 0.1796.
- **Split-half reliability.** Design in Appendix D. Opponent strength estimates enter both halves and induce dependence, so opponents must be estimated without the team's own halves. Reliability informs shrinkage; it does not gate inclusion.
- **k in sets.** Derivation in Appendix A. k is the ratio of noise variance to prior variance *in the chosen exposure unit*, and converting it requires measured per-set variance and within-match correlation.
- **NCAA home edge.** NOT FOUND in primary form.
  - Pollard & Gómez (2015, Coll. Antropol. 39(3):583–589) compared college and professional sports, but its college sports were baseball, basketball, football, hockey, lacrosse, soccer and women's basketball, not volleyball (PubMed 26898053).
  - Forman (2025, J. Sports Sci. 43(23), doi 10.1080/02640414.2025.2567806) used 33,220 NCAA matches (2023–24 and 2024–25) and reports only a visitor–home **ball-handling-error** gap that shrank by 0.000384 BHE/point. It reports no home win or point share, and "scoring balance remained unchanged."
  - Non-NCAA context: professional volleyball home win probability for women was 55.39% (Psychol. Sport Exerc. 2023, PMID 37665863), and the global figure was women 55.26% (Pollard et al. 2017, as cited there).
- **Prospective NCAA volleyball Brier/log-loss benchmarks.** NOT FOUND.

---

## 4. Feasible-data table

| Source | Fields | First server | Completeness | Rights/terms (quoted) | Automation permitted | Status |
|---|---|---|---|---|---|---|
| ncaa.com play-by-play via henrygd API | Score sequence; servers named on aces only (per Builder) | Inferable from anchors (HYPOTHESIS) | Coverage by conference UNKNOWN | NCAA.com ToS §4: "You may not modify, reproduce, publish, transmit… create derivative works, use for commercial purposes, or in any way exploit, any of the NCAA Content… except as provided." Operated by Turner Sports Interactive (https://www.ncaa.com/tos). henrygd is third-party: "public API is limited to 5 requests per second per IP." | UNKNOWN (no explicit automation clause seen in the fetched portion; the henrygd API is not an NCAA authorisation) | Research use pending rights review |
| stats.ncaa.org | Box scores; play-by-play naming servers every rally (per packet) | Yes (named) | 2020–2025 mirrored by ncaavolleyballr | NCAA.org ToS §4 prohibits "unauthorized robots, spiders… scraping, or harvesting"; §9: "You may not frame, capture, harvest, or collect any part of the Site or Content without the NCAA's advance written consent" (https://www.ncaa.org/terms-of-service/). Whether these terms govern stats.ncaa.org is UNKNOWN. | No (without consent) under NCAA.org terms, if applicable | Do not automate; seek consent |
| ncaavolleyballr files (2020–2025) | Team/player season and match stats; play-by-play with rally/event counters (v0.5.1) | Yes | 96.5% of 2025 set-teams got derived rotations (packet) | Package "MIT + file LICENSE"; no data licence found | N/A (static files); underlying-data rights UNKNOWN | Historical research base, rights check needed |
| StatBroadcast | Live stats and play-by-play as browser-observed | Serving sequence browser-observed (docs/rotations_finding.md) | UNKNOWN | "Collect, harvest, compile, store, cache, aggregate, derive, or otherwise systematically extract any data… whether manually or through automated or semi-automated means, without the prior express written consent"; access "strictly limited to human-initiated interaction through the standard StatBroadcast web interface" | **No** | Excluded unless written consent |
| School sites (Sidearm/WMT/Presto) | Box scores, sometimes play-by-play | Varies/UNKNOWN | UNKNOWN | Sidearm ToS (updated Apr 11, 2023): "The contents of the Services… are intended for your personal, noncommercial use." WMT/Presto not checked. | UNKNOWN | Needs per-vendor review |
| Genius Sports / NCAA LiveStats | UNKNOWN | UNKNOWN | UNKNOWN | Not researched | UNKNOWN | Open |
| Hudl/Volleymetrics DVW exports | Touch-level coded events, lineups, grades | Yes (DVW requires lineups per set) | Own level of play, analysed matches only | VM Network: "cannot be downloaded or shared." Hudl Terms: no "automated means… to access, collect, or extract data" | No (automation); manual export per entitlement | Entitlement UNKNOWN |
| VolleyTalk user-supplied exports (ProBoards) | Passing grades as posted | No | 709 parsed rows, unvalidated | ProBoards support rules: "Automated account creation, participation, and content scraping is not permitted" (https://support.proboards.com/page/rules); ToS §19(g) (2016 wording) bars tools "to harvest or otherwise collect information" | **No** | Anecdotal only |
| Massey / Pablo / VolleyDork | Ratings | No | N/A | Not re-checked | UNKNOWN | External comparators only, manual |

---

## 5. Bounded test proposal (maximum three)

**T1: Clean re-benchmark plus venue audit (2025).**
- *Data:* 2025 finals, current code, Round-2 harness, and a hand-verified neutral-site label set.
- *Design:* 7-day rolling blocks, last pre-match forecast per match, block bootstrap plus team clustering.
- *Primary metric (pre-registered):* mean log-loss of the exact live configuration (k=10). Brier and favourite accuracy are secondary.
- *Also computed:* SD and autocorrelation of paired differences, and DEFF.
- *Stop condition:* replica parity fails at any audited cutoff.
- *Not concluded:* 2026 performance, cross-season generalisation, or double-counting unless Appendix C's criteria are met.

**T2: A single pre-registered hitting-channel comparison at k=10.**
- *Primary:* live (hitting 0.25, τ_hit 0.100) versus hitting weight 0, with SESOI set beforehand and TOST.
- *Secondary, separately reported:* floor versus re-measured τ_hit on the same population; partial-correlation and stacking checks; split-half reliability (Appendix D).
- *Stop condition:* T1's SD/DEFF shows the harness cannot resolve the SESOI with 2025 data. Report "underpowered", not "no effect".
- *Not concluded:* anything about descriptive usefulness of hitting.

**T3: Rights-first test of serving-team inference.**
- *Step 1:* document the data rights for the 2025 ncaavolleyballr files and for any 2026 source. Proceed only where use is permitted.
- *Step 2:* on 2025 files where servers are named on every rally, hide all server names except aces, infer serving team from anchors plus the rally rule, and score accuracy against the truth.
- *Primary metric:* share of rallies with correctly inferred serving team, plus the share of sets with no anchor.
- *Stop condition:* accuracy below a pre-set threshold, or unresolved rights.
- *Not concluded:* 2026 feed completeness, permission to automate, or full lineups.

---

## 6. Appendix

### A. Corrected exposure and scale arithmetic

- **Scale ratio.** 0.100/0.0668 = 1.497. The hitting deviation coefficient becomes 0.25×1.497 = 0.374, and normalised weights are 0.75/1.124 = 0.667 and 0.374/1.124 = 0.333. These numbers are correct *for the deviation terms*.
- **Why it is not a weight change.**
  - h_impl = z_opp + dev/τ_hit, and the z_opp coefficient stays at 1, so the change is not a uniform rescaling.
  - Margin-only matches are unaffected.
  - The inflated variance of season_z shifts the effective prior balance at fixed w.
  - Opponent updates propagate the change.
  - Mean/sd normalisation over 348 teams cancels only uniform scale changes.
  - The evidence SD changes by sqrt(Var(0.75a+0.374b)/Var(0.75a+0.25b)), which equals 1.124 only if a and b are perfectly correlated. "12.4%" was therefore overstated.
- **k in sets.** The live k = σ²_match/(τ²(1−ρ²)) = 23.929/(5.941×0.2979) = 13.52. In set units, k_set = σ²_set/V_prior, with V_prior = τ²(1−ρ²) in the same pts/set² scale. Relating it to k_match needs Var(match mean) = σ²_set·(1+(s−1)ρ_w)/s, where ρ_w is within-match set correlation, and a separate variance for fifth sets. Assuming independent identical sets (ρ_w = 0) would make k_set ≈ k_match·s̄, but that assumption is untested, and s itself depends on the outcome. If precision weighting is wanted, use expected set count or variance from the *pre-match* forecast.

### B. Power formula (to be filled with measured quantities)

MDE ≈ (z₁₋α/₂ + z₁₋β) · SD_d · sqrt(DEFF / n), where d_i is the paired per-match log-loss difference and DEFF comes from block bootstrap or two-way clustering. Measure SD_d and DEFF on 2025 with the Round-2 harness for the *specific* arm pair. For calibration of expectations only: the Round-2 intervals' half-widths (≈0.0091 and ≈0.0095 on 3,470 matches) imply an SE of about 0.0046–0.0048 for *those* pairs. Nested arms may have much smaller SD_d, so no value is transplanted.

### C. Home-term audit design

- **Labels.** Hand-verified venue classes for all audited 2025 matches (nominal flags are not accepted).
- **Primary estimand.** β_venue in r_i = α + β_home·1[home] + β_neutral·1[neutral] + ε, with block-bootstrap CIs.
- **Secondary.** Reliability curves by venue class; chained home swing; team residual versus past home share.
- **Problem criteria (pre-registered).** A CI excluding zero *and* exceeding the SESOI in pts/set, or a significant slope in the home-share test.

### D. Opponent-adjusted split-half reliability

1. For each team, split matches by chronological odd/even order, and repeat with many random within-week splits.
2. Estimate opponent strengths **excluding the focal team's matches** (leave-team-out), or from preseason priors, so the shared opponent estimates do not inflate agreement between halves.
3. Compute attempt-weighted metrics per half, e.g. Σ(K−E)/ΣTA against the opponent-expected value.
4. Correlate halves across teams (weighted by harmonic-mean attempts), then apply Spearman–Brown: r_full = 2r/(1+r).
5. Get CIs by bootstrapping teams over repeated splits.
6. Report schedule-strength correlation between halves as a diagnostic.
7. Use the results to set per-channel shrinkage. Features less reliable than margin are not rejected on that basis.

### Plain-English example (hypothetical numbers, illustrative only)

"Team X served 12 aces and 15 errors across four sets, and the opponent's reception errors equalled those 12 aces (the manual requires aces = opponent reception errors). Using inferred serving teams, Team X sided out on 62% of 600 receive rallies this season." The naive binomial SE is √(0.62·0.38/600) ≈ 2.0 points. Clustering by match widens it. That supports a statement like "sides out at roughly 58–66% of receive rallies," subject to correct server inference. It does **not** show pass quality, which of Team X's servers created pressure, rotation effects (serving order ≠ full lineup), or that the rate predicts future wins.

---

## 7. Access failures and substitutions

- https://www.proboards.com/tos: returned "JavaScript Required". Substituted: support forum rules page (fetched via search) and the 2016 §19(g) wording quoted by ProBoards support staff (support.proboards.com/thread/600825, relayed by the research subagent, not fetched by me). The current clause number, wording and date are unverified.
- https://www.statbroadcast.com/terms.php: seen only as a search snippet showing "Last Updated: July 19, 2011". The prohibition text comes from the bcsstats.com mirror snippet and the research subagent, which reported bot blocking and a "May 28, 2026" date. **The date conflict is unresolved.**
- https://www.ncaa.com/tos: fetched but truncated at §12. An explicit automated-access clause was not seen. NCAA.org's cookie notice states it does not apply to NCAA.com, so the NCAA.org terms were not transplanted.
- Forman 2025 full text (T&F): not accessible. Abstract only.
- 2012 IJPAS home-advantage paper: abstract only. Crossref lists the authors as Alexandros Laios, Panagiotis Kountouris and Miltiades Kyprianou (IJPAS 12(2), Aug 2012, pp. 272–281).
- Pollard et al. 2017: not opened. Cited via PMID 37665863.
- NCAA women's volleyball rulebook: not fetched by me. Rules 6.5.1.2, 8.1.3.1.1–2, 8.1.4.1, 10.3.2.3, 13.1.2, 13.2.3.2 and Tables 1 and 3 are quoted from the enrichment pass of the 2026 and 2027 NCAA Women's Volleyball Rules.
- Genius Sports/NCAA LiveStats, WMT, Presto terms: not researched (search budget).
- VolleyDork, Massey, Pablo: not re-checked.
- Off the Block home-win figures (60.4% in 2020, 58.5% in 2021): reported by the subagent from a secondary blog. Not used as evidence.
- Repository scripts and docs (predict_2026.py, digby_top25.py, measure_forecast_calibration.py, docs/rotations_finding.md): not inspected directly. All code facts come from the Reviewer/Builder packet.