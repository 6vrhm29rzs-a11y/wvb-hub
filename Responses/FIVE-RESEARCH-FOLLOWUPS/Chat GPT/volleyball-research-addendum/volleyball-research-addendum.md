# WVB research addendum: corrections, feasible analysis, and three investigations

**For Cody, Reviewer, and Builder — 2026-09-26**  
**Research only. No experiment, installation, purchase, source collection, vendor contact, message, or live change is authorized by this document.**

## Takeaway

**Keep POWER unchanged, establish a defensible forecast benchmark, and build the explanatory dossier before choosing a replacement model.** The old benchmark reuses some outcomes in both fitting and evaluation—not merely correlated forecasts. Its replacement score remains unknown. [P0, “Forecast benchmark”]

Boxes can explain workload and attack outcomes. Audited rally data can add sideout and team points won while a player serves. Passing, setter choices and middle availability need further observations, not inferred weights.

The three investigations below address **baseline validity, immediate descriptive usefulness, and missing contact evidence**, respectively. Technology is conditional support for those investigations.

### Evidence and scope

**P = supplied project evidence, not independently rerun. V = verified primary-source documentation. H = hypothesis or mathematical inference. R = proposed research design. U = unknown.**

[P0] is `SHARED-RESEARCH-CORRECTIONS.md`, dated September 26, 2026; it controls over [P1], `POWER-RESEARCH-PACKET-REVIEWED.md`, and [P2], my original `POWER-OUTSIDE-RESEARCH-2026-09-26.md`. WVB source code and raw corpora were not independently executed or certified here. External sources were checked September 26, 2026; direct URLs and relevant sections appear inline or in the source register.

## 1. Corrections and evidence that affect decisions

| Issue | Corrected finding and consequence | Evidence/status |
|---|---|---|
| Imported infrastructure | **I withdraw the WVB applicability of the Raven/M4/24GB/Ollama/Qwen/launchd/Tailscale/Tavily assumptions in my original report.** WVB hardware, local models, credentials, network access, integrations, quotas, and operating health are unknown unless independently established in the WVB packet. A documented shadow job does not identify its host or scheduler. | P0, “Scope”; P2 §§1.2, 4.8–4.11. **Correction.** |
| Historical Brier 0.1718 | Full-season home/scale estimation preceded checkpoints; even checkpoints fit the slope, odd checkpoints evaluated it, but each included later matches. **The same outcomes can occur on both sides.** The older rating construction also differs from live. Retain this number only as a historical calibration artifact—not held-out performance of current POWER. | P0, “Forecast benchmark.” **P.** |
| Sample size and comparator | 11,284 counts forecast/checkpoint rows, not independent matches. Exact unique scored matches and fit/evaluation overlap are unknown. The underlying packet reports 5,131 season matches. The 0.1289 observed-margin simulator score is another estimand, not a corrected forecast benchmark. No new score or quantified optimism is established. | P0, same section. **P/U.** |
| Hitting evidence | The earlier weight receipt used **k=13.5**, versus live **k=10**. It included the floor but did not establish the whole live configuration. Earlier AUC and Round-2 log-loss findings are different experiments. Neither proves the channel useless nor validates removing its floor. | P0, “Current implementation”; P1 Current Model §§5–7. **P.** |
| Home adjustment | Forecast code removes its direct home term for a venue classified neutral; rating evidence still uses nominal home/away. Do not describe both stages as lacking neutral handling, or require their differently scaled coefficients to be equal. | P0, “Current implementation.” **P.** |
| Iteration count | Correct description: **initial opponent adjustment using preseason opponents, then four further loop passes**. My four-step shorthand was incomplete. A convergence comment is neither a numerical certificate nor evidence of a production defect. | P0, same section. **P.** |
| Coverage and passing | No complete automated 2026 rally sequence is established in this pipeline. That is not a universal source impossibility. Serving order is not the six on court. Passing capture has **709 parsed rows / 510 candidate rows**, not those numbers of validated matches; poster identity is not grader identity. | P0, “Data availability”; P1 Passing Quality. **P/U.** |
| Figshare 30472025 | Zachary Jacques; posted **2025-10-28, 22:21**. Landing-page DOI: **[10.6084/m9.figshare.30472025](https://doi.org/10.6084/m9.figshare.30472025)**. Description specifies **2025 men's Division I**, match outcome and 19 performance variables; CC BY 4.0 is displayed. **Exact version, raw schema, collection method and successful file access remain unknown.** The unversioned DOI does not establish “v1.” | [S1], description/identifier/licence. **V metadata; U raw data.** |
| Powers, Stancil & Consiglio | The February 2, 2024 preprint describes 2022 NCAA D-I women's charted contacts and contextual Points Gained. **I could not establish who performed the charting, ownership of the corpus, or outside-researcher access from the accessible primary materials.** Do not attribute charting to the authors or Hudl by inference. A public paper is not a public dataset. | [S2], §2 and §6; arXiv record lists the 2025 journal article, DOI [10.1515/jqas-2024-0038](https://doi.org/10.1515/jqas-2024-0038). **V method; U access.** |
| Set-aware study | Egidi/Ntzoufras, revised preprint **April 15, 2020**, Italian men's SuperLega 2017/18. §5.4 reports posterior agreement of simulated and observed game/set outcomes; the midseason game figure is 78.26% with reported ±3% variation. **No match-level out-of-sample Brier or log-loss result was located in the accessed manuscript.** DIC and standings reconstruction are different quantities. This is a modeling lead, not evidence of a forecast-loss gain over POWER. | [S3], §§3.4, 5.3–5.4; [version record](https://arxiv.org/abs/1911.01815). **V, bounded to accessed text.** |

Powers §6.1 also acknowledges outcome-dependent opponent adjustment and simplified defensive responsibility. The method is a useful lead, not a promise of data access or causal attribution. [S2]

## 2. Field-by-field feasibility: now versus additional data

**Coverage is packet-reported as of September 26, not independently recounted.** “Now” means feasible after validation; field presence is not proof of accurate attribution. [P1, Data Inventory]

| Data level / feasibility | Required fields | What we can measure | What cannot be inferred | Missing-data policy and actual coverage evidence |
|---|---|---|---|---|
| **Team/player box scores — feasible now** | Canonical game/team/player IDs; final status; set count; K, E, TA, aces, service errors, recorded serve/reception attempts, reception errors, assists, digs, BS, BA; source/version. | Earned PPS; kill/error rates and efficiency; TA/set; player attack share; ace/error rates; opponent outcomes; role-labeled workload. | First-ball or transition outcomes; pass/set quality; real court exposure; block touches; injury cause; causal player value. | Unknown denominator → no rate. Missing row ≠ zero or injury; all-zero listed player ≠ proved court appearance. P1 reports 2026 **2,221 boxes / 4,442 team rows**, serve/reception attempts nonzero on **4,422**, and **58,137 player rows**. Coverage must be joined to the actual study's eligible games. [P1 inventory: `boxscores_team_2026`, `playerbox_2026`] |
| **Ordered point winners + serving team — historical feasibility; 2026 pipeline incomplete** | Game/set/rally IDs, chronological score transitions, initial serving team each set or an explicit serving-team field, point winner, penalty/replay/correction flags. | Sideout: receiving-team rally wins / receiving rallies; serving-team point-win rate; runs and score-state profiles. | Whether a receiving win happened on first attack or much later; which player served; successful passing or setting. | Reconcile all score increments and final set scores. Quarantine gaps/administrative points rather than manufacture rallies. After an ambiguous interval, resume state only at a valid anchor. P1 reports a 2025 derived corpus of **826,207 rallies**, not an independently certified complete population. P0 reports no complete automated 2026 sequence. |
| **Named server — historical pilot feasible** | Above plus server ID attached to **every serve**, including errors; identity joins; service-error/ace indicators where available. | **Team points won while player X serves**, plus opportunities, aces and errors. | Isolated serving skill, serve pressure on passing, or causal points created by the server. | Unresolved identities stay unresolved; report covered/all eligible serves. Never extrapolate an ace-only identity sample. P1's 8,350/8,350 named-server check was a sample, not a corpus guarantee. Public ncaavolleyballr catalog lists women's D-I 2025 PBP; no 2026 in-season commitment was verified. [P1 C6; S4] |
| **Serving-order slots — historical derived context** | Set seed/order, serving sequence, substitutions attached to slots, stable identities; explicit definition of slot numbering. | Team outcomes by the reconstructed serving-order slot, and substitution pairings. | The full six on court, actual attack location, or the number/identity of available hitters. | Preserve unresolved set-teams and state uncertainty; do not fill missing positions from roster labels. P1 reports **48,625/50,410 set-teams resolved (96.5%)**. This is serving-order resolution, not complete-lineup coverage. [P1 `rotations_2025`] |
| **Complete on-court lineup — needs more data** | Initial court/rotation state for every set, all substitutions, libero replacements, corrections and rally boundaries. | Court exposure, actual front/back-row participation and lineup-conditioned associations—after reconciliation. | Full-match lineups from set-one starters; accurate 5–1/6–2 exposure from a roster or starter label alone. | Unknown state remains unknown until re-anchored. P1 lists **2,197** 2026 lineup records, **2,110** with named starter lines, against 2,221 finals. Set-one names are not rotation order; later cumulative lists are not new lineups. [P1 `lineups_2026`] |
| **Individual contact sequence — needs authorized sample** | Every contact's order, team, player, skill, possession/phase, outcome, continuity and terminal point; explicit treatment of block touches/free balls. | First-attack and transition rates; contact-conditioned changes in rally-win probability; linked reception → set → attack paths. | Contacts that were never recorded, merely from final kill/dig descriptions; causal responsibility from a fitted value model. | Incomplete rallies excluded from phase-dependent denominators or visibly labeled partial. The WVB packet does not establish such a complete current dataset. Powers demonstrates the research method, not our access. [P0; S2] |
| **Pass quality — candidates need validation** | Game/player joins; grade rubric; reception counts/category histogram if available; grader, source, segment scope, corrections and completeness. | Reported passing summaries, then distributions/associations when definitions and joins pass review. | Set quality; middle availability; undefined GP%; a grade distribution from a rounded mean; representative national coverage. | Keep match/partial/weekend/season scope distinct at **segment** level. Never average incompatible graders/scales or count quoted corrections twice. 709 parsed rows, 510 candidates, no validated match joins established. Counts by category and grader identities remain unknown. [P0; P1 Passing Quality] |
| **Set quality + middle availability — needs contact/video observations** | Pass end location; setter identity/location; ball height/tempo/target; predeclared set-quality rubric; actual eligible hitters/approaches; phase, opposition and timestamped video evidence. | Conditional setter choices, attack options and hitter outcomes; observed cases of a usable pass followed by an unattackable or constrained set. | Availability from middle attack share, quality from assists, or setter blame from opponent blocks. | “Not set” ≠ “unavailable.” Code unseen/ambiguous options as unknown. No validated set-quality or middle-availability fields are established in this WVB packet. [P1 metric 6 and unavailable fields] |

### Denominators: three different volleyball questions

**R — These are proposed study conventions; provider definitions may differ.**

**Sideout rate** is receiving-team rally wins divided by all rallies the team began receiving. Include opponent service errors as receiving wins. This can be measured without the internal contact sequence; it includes wins after long rallies.

**First-ball sideout needs an explicit convention.** For the initial study, use the literal label **“first-attack kills per receiving rally”**: kills on the receiving team's initial attack divided by all receiving rallies. Opponent service errors remain in this denominator but not that numerator; display their separate contribution. Also report **first-attack kill percentage**, using initial attack attempts as its denominator. They are not the same rate. Do not silently call either a provider's FBSO metric unless its treatment of errors, overpasses and no-attack wins is documented.

**Transition attack efficiency** is `(transition K − transition E) / transition TA`, with transition defined in the coding guide as attack possessions following defense of an opponent attack. Keep free-ball offense and repeated attacks after coverage distinguishable. A transition **possession-conversion rate** would use possessions rather than attacks and is another metric. None can be recovered from ordinary box totals or point winners alone.

## 3. Consequential methodological answers

### 3.1 Smallest defensible model experiment: three arms, no recalibration initially

**P — Exact live baseline first.** Freeze code, constants, priors, eligible IDs, corrections, venues and input hashes. Reproduce eligibility and initial-plus-four updates. Reported 346-team parity at one cutoff does not certify other cutoffs. [P0; P1 Current Model §§2–5]

The documented baseline has `w_i = n_i/(n_i+10)`; per-match evidence is 75% margin and 25% hitting when both attack records are usable, otherwise margin-only. Rating constants include margin home adjustment 1.0878, margin scale approximately 2.437, hitting home adjustment 0.0292 and hitting scale 0.100. Forecast conversion uses `3.05 × score difference + 0.2675`, with that direct home term zero for classified-neutral venues, then the existing rally simulator. Preserve the actual code's precision and orientation rather than substituting these rounded numbers. [P1 Current Model §§3–4; P0]

**R — Separate the hitting-scale estimation population from forecast-probability calibration.**

| Arm | Hitting-scale estimation | Everything else | Identifiable comparison |
|---|---|---|---|
| **A: exact live** | Original live estimation population and helper; retain the variance floor of 0.01, reproducing SD 0.100. | Live k=10, hitting weight, constants, eligibility, missing-box rule, iteration count and forecast mapping. | Implementation reference. |
| **B: population only** | Restrict the scale-estimation sample to countable D-I matches; recompute all intermediate variance quantities on that sample; retain the **same floor rule**. | Identical to A. In this minimal design the hitting home coefficient remains fixed; changing it would be another intervention. | **B−A:** change in scale-estimation population alone. |
| **C: floor only on B's population** | Use B's freshly estimated raw variance without the 0.01 floor, provided the estimate is positive and usable. | Identical to B. | **C−B:** floor removal conditional on that population. |

Recompute the within/between-team variance ingredients and qualifying-team counts inside **each training sample**. The earlier approximately 0.0668 is not a plug-in estimate for B/C. If both A and B remain floor-bound, identical predictions may be the correct result. If C's raw variance is nonpositive or numerically unusable, mark C undefined; do not secretly introduce a new epsilon floor. Builder must disclose any helper coupling that prevents changing only this scale. [P0; R]

Use identical targets/cutoffs. Log loss is primary; Brier, calibration diagnostics and AUC are secondary. Hold forecast coefficients/simulator fixed. **Measure**, but do not apply, calibration intercept/slope. Keep the convergence diagnostic separate; do not substitute its solution into B/C.

For the smallest future trial, estimate each scale on frozen 2025 training data, then hold it fixed. A later rolling refit must use only pre-block data and is not an exact replay of fixed-constant A.

**A 2025 rerun remains development evidence.** Its outcomes informed k, weights, conversion and candidate selection; chronological rows cannot undo that exposure. Confirmation requires genuinely untouched future targets after a recorded specification freeze—not necessarily one particular season. [P0; P1 Current Model §7; R]

### 3.2 Chronological evaluation before a bootstrap

**R — First define which forecast is being evaluated.** A practical primary policy is one forecast per canonical match: the frozen daily 05:45 Pacific research issuance for matches scheduled in its following 24-hour window, and only when issuance demonstrably preceded first serve. This is a variable-lead daily forecast, **not** an exact 24-hours-before-first-serve forecast. Rescheduled matches need a predeclared reissue/selection rule; ambiguous timing is excluded from the primary analysis and counted separately. The packet's existing 05:45 job establishes a possible issuance pattern, not proof that these conditions currently hold. [P1 Validation §E]

After joint approval and a specification freeze at time `T0`, every scored target must lie after `T0`. All fitted quantities—including priors, home/scale estimates, feature transformations and any probability calibration—must use only information available before issuance. Freeze all arms on identical snapshots; store event time, observation time, forecast creation time, model/input hashes and the fixture-time version. Use a separate version for later-adjudicated outcome labels. Later corrections must not rewrite the input history.

For any retrospective rolling experiment, replace “all remaining season matches” with **disjoint next-block targets**. Full-2025 parameter estimates cannot accompany a claim of clean within-2025 testing. A past-only refitted baseline may be studied, but must be labeled separately from exact live A. Missing observation timestamps prevent blanket “as-known-then” certification; an immutable snapshot can prove a bounded case, not repair absent history. [P0; P1 Current Model §6; R]

**Later nested recalibration is a separate experiment.** Within each outer cutoff, generate earlier, genuinely prequential predictions, fit each arm's calibration only on those already-completed targets, and choose calibration settings using inner chronological splits. No inner fit or selection may use an outer-test outcome. Freeze the calibrator for the next outer block. Report both the fixed-mapping diagnostic and this calibrated comparison; they answer different questions.

**Unique-match versus repeated-horizon estimands:**

- **Primary:** average loss over `M` unique matches, one preselected forecast each. This answers the quality of that issuance policy.
- **Secondary:** either report each horizon separately, or average prespecified horizon losses *within each match* before averaging across matches. Report horizon completeness and common coverage. A naive average over all forecast rows gives extra weight to matches with more issuances.

All horizons for the same match share one outcome. Different matches share teams, seasonal conditions and sometimes tournaments. Dependence within evaluation affects uncertainty; **outcome overlap with fitting is a separate validity problem** that a bootstrap cannot repair. Report actual unique matches, forecast rows, teams, time blocks, excluded forecasts and fit/test outcome overlap. Do not manufacture an effective sample size.

Only after those checks: form paired loss differences on identical targets. A calendar-block bootstrap of target-match dates can retain local dependence; put every horizon of a match in its match-date block. Compare, for example, 7- and 14-day block choices as sensitivity analyses, not guaranteed solutions. Recurring teams create dependence beyond adjacent blocks; short follow-up periods may not support decisive intervals. Report that limitation and future-block consistency rather than treating thousands of repeated rows as independent evidence. These intervals concern the locked procedure's scored forecasts, not uncertainty from an unrestricted model search.

### 3.3 What the convergence investigation would establish

**H — Conditional mathematics, not a code finding.** With fixed priors, nonnegative normalized opponent weights and fixed blend weights below one, the documented update can be a contraction. Because blending occurs inside opponent lookup, the season-state operator is **P W**, whereas the equivalent blended-rating operator is **W P**. These are alternative state representations, not permission to blend twice. Appendix A provides the exact conditions and initialization.

**R — Frozen-input comparison:** reproduce production's initial-plus-four result; compare it with a tightly converged reference on the same inputs and unchanged forecast mapping. Use representative early/middle/late snapshots where available, including missing-box and disconnected-schedule cases. Record maximum raw-score difference, displayed POWER difference, rank crossings **with score gaps**, and maximum absolute probability difference on declared fixture/pair sets. A crossing of nearly tied teams does not by itself demonstrate meaningful error.

Proposed review tolerances—not approved production criteria—are **0.001 raw-score units** and **0.001 absolute match probability (0.1 percentage point)**. Require both on the specified test set and show the full difference distribution. Solve the reference substantially more tightly, such as a residual-based raw-score error bound of `1e-8`. Forecast numerical noise must be much smaller than the probability tolerance. Passing a numerical check says nothing about whether extra opponent iterations improve future prediction.

### 3.4 Minimum defensible named-server adjustment

**R — Keep the outcome label literal:** `Y=1` when the serving team wins the rally. All serves, including service errors, enter the denominator. Start with counts and raw rates; do not rename them server points created. [P1 metric 9]

A minimal adjusted model should partially pool serving-team and receiving-team effects, observed serving-order-slot context, and a player-within-team contribution where identifiable. Include opponent slot context when reconstructed reliably, and match/set conditions; handle within-run dependence in the uncertainty analysis. Use only pre-rally information. A practical logistic specification is in Appendix B.

**Identification matters more than adding terms.** When a player always serves in one slot, a server effect and that slot's effect cannot be cleanly separated by those observations. Report a combined **server-in-slot/team-context** estimate, or explicitly prior-sensitive estimates—not independent player and rotation abilities. Even crossover does not remove confounding by front-row blockers, defensive personnel, targeted receivers, substitutions, opponent tactics or unobserved serve characteristics. Full on-court lineups remain a separate data requirement.

Show actual serves, service runs, sets, matches and opponents beside partially pooled intervals; do not invent an effective opportunity count or universal stabilization threshold. Twenty audited matches can validate joins and state reconstruction, not establish stable national server rankings. A later predictive question would compare future-rally loss against a team/opponent/slot baseline; that is separate from producing a useful descriptive dossier.

## 4. Only three next investigations, in priority order

| Priority | Question and smallest useful scope | Required data / cost | Validation and stop condition |
|---|---|---|---|
| **1 — Baseline/evaluation certificate, then isolated scale diagnostic** | Can we reproduce exact live A, establish valid targets, and attribute B−A and C−B separately? Include the independent convergence receipt from §3.3, without changing arm definitions. | Frozen WVB code, priors, raw/derived inputs, correction/eligibility manifests, forecast/simulator settings and timing evidence. **$0 additional service required**; actual analyst/compute time unknown. | First establish parity across selected cutoffs and zero fit/test target overlap for any clean evaluation. Publish diagnostic differences even if null. **Stop** comparative performance claims for unexplained baseline mismatch, leaked targets or uncertifiable timing; stop C for unusable scale. Historical results cannot authorize promotion. |
| **2 — One connected team/player dossier** | Start with Stanford as Cody's named question, not as a verified setter diagnosis. Explain volume versus efficiency, player workload, opponent context, trends and missing evidence. Audit up to 20 existing 2025 PBP matches only for the optional named-server panel. | Current boxes/rosters and their coverage; verified availability notes; existing 2025 PBP plus rights check. Passing only after its joins/rubric are validated. **$0 new subscription required.** | Reconcile counts and identities to sources. Have Cody answer three concrete questions: who absorbed workload, whether termination or errors changed, and which explanation needs more evidence. **Stop or omit a panel** if denominators/state/rights fail; do not delay the valid box-score dossier waiting for contact data. No new rating weight. |
| **3 — Permissioned passing → setting → attack microstudy** | Determine whether observed contacts can distinguish reception constraints, setter choices and hitter execution. Smallest sample: two specified matches, all available receptions, with a predeclared coding rubric and a blinded independently coded subset. This is feasibility, not a causal or predictive effect estimate. | Existing authorized exports/video first; otherwise access remains an unresolved prerequisite. Game/phase/player joins, pass categories/end location, setter contact, eligible options, attack target/outcome, provenance and permission. **Data price unknown; annotation time must be measured.** | Resolve score/contact completeness; report agreement/confusion by category before adjudication; test reconciliation on both matches. **Stop** for absent rights, missing key fields, unresolvable rubric disagreement or costs disproportionate to a two-match case study. No national extrapolation or setter verdict. |

### What the dossier should connect

**R — Use one linked story, not ten unrelated leaderboards.** Show earned PPS and its components separately from scoreboard margin; attack attempts, kill/error rates and player shares; serving/reception opportunity rates; block and dig exposure proxies; setter participation; opponent context; and sourced availability. Pool raw counts before calculating season rates. Team scoring blocks are `BS + 0.5 BA`; assists are not set quality; digs/opponent attacks is an exposure proxy, not dig success. Player sets played are not rotations of court exposure. [P1 metric definitions and Current Model §10]

**H — Illustrative example only; these are not Stanford observations.** Suppose a team’s middle attack share falls from 20% to 10%, pin share rises from 70% to 80%, and the pins’ kill/error rates change from 40%/10% to 35%/15%. Their efficiency falls from .300 to .200. Boxes could establish those workload and outcome changes.

“Passing deteriorated, removing the quick middle and forcing high balls to the pins” is a plausible **hypothesis**, not the box-score finding. A validated same-rubric passing decline would support only the reception part. Establishing middle availability requires seeing whether an eligible middle was actually available to approach and be set. The setter may instead have chosen the pins; opposition, personnel, phase mix or tactics could explain the shift. Link selected rallies to pass end location, setter contact, available middle route, chosen hitter and attack outcome. This turns a statistical trend into a testable volleyball explanation without assigning arbitrary blame or weights.

## 5. Three conditional technology options—not an approved stack

The baseline alternative is **existing WVB scripts, files and human review**. No account, machine, local model or integration is presumed available. Proposed pilots remain part of the three investigations above, not additional independent projects.

| Conditional option | Verified capability and concrete WVB gap | Pilot, permissions, ongoing cost and stop condition |
|---|---|---|
| **DuckDB local query engine** — for investigation 2, only if repeated joins are cumbersome | Official docs support SQL over JSON; DuckDB is MIT-licensed/free. [S5] Query frozen boxes, identities and manifests for the dossier and coverage summaries. **Current Python can already do this**; the proposed benefit is simpler/reproducible analysis, not a missing fundamental capability. | Two read-only queries: one team history and one completeness table, checked against existing Python. Approve installation/file access separately; no cloud account or migration needed. **$0 software subscription**, local storage/compute and maintenance unmeasured. Stop for unexplained total differences or no material reduction in analyst effort. |
| **Ollama local structured-output HTTP API** — only if human scope/alias triage is a measured bottleneck | Official docs describe JSON-schema output, local-only operation and default loopback binding; runtime is MIT-licensed. [S6] It could propose extraction/scope flags from saved permitted text. It cannot supply missing contacts, validate a grader, or make schema-valid output true. Hardware fit and a suitable model are **unknown**. | A 100-example sealed benchmark versus rules/manual review, including missing values, mixed aggregates, decimals and adversarial instructions. Proposed success: at least 20% lower median review time at no increase in critical accepted-field errors; publish abstention and coverage too. Approve compatible hardware, runtime/model download and model licence first. No personal memory, credentials, external tools or truth-file writes. **$0 local runtime fee; model-specific terms, power and maintenance unknown.** Stop for no measured benefit, excessive latency or unsupported critical claims. |
| **Hudl Volleymetrics permissioned DVW/XML export** — access investigation for priority 3, not a national feed purchase | Hudl's transition FAQ explicitly documents DVW/XML exports in Volleymetrics and says corresponding Hudl support is forthcoming. The same FAQ limits the updated Hudl workflow to North American D-I/pro programs. [S7] This is stronger export evidence than my prior marketing-only review, **not proof of specific NCAA match coverage, fan eligibility, a public API or research/publication rights**. | Two named matches plus field dictionary and written allowed-use terms, through an authorized owner/account only after approval. Verify actual contact, phase, grade, lineup/libero and correction fields rather than relying on a demo. No credential sharing or unauthorized cloud upload. Applicable subscription/export fee and continuing cost are **unknown/quote-required**; no contact made. Stop for no eligible access, no target matches, unusable fields or incompatible storage/analysis/display rights. |

**R — Automation boundary:** approved snapshot → deterministic validation → optional AI proposals → human review → separate report. Record input/model/run versions; distinguish process success from input completeness. Keep truth ledgers untouched. Start manually; any later scheduling must use the verified WVB environment. No personal-system integration is needed.

### Prior product/pricing claims: what changes

The unsupported assumption was **WVB applicability/entitlement**: “already available local Qwen” and access to another project's keys, credits or infrastructure are withdrawn. Illustrative token bills were not measured operating costs.

Current official pages still support the earlier short-context standard input/output prices per million tokens: OpenAI GPT-6 Luna **$0.10/$0.50**, Sol **$2/$10**; Anthropic Haiku 4.5 **$1/$5**, Sonnet 5 **$2/$10**; Gemini 3.5 Flash-Lite **$0.30/$2.50**; Grok 4.7 **$2/$6**. These are verification results, **not additional tool recommendations**. They exclude applicable tools, retries, extra reasoning, regional premiums and account restrictions. [S8], [S9], [S10], [S11]

Claude Code's documented `--bare` mode still requires API/provider credentials rather than subscription login, and still has file/shell capabilities: bare does not mean read-only. [S12, “Start faster with bare mode”] Firecrawl still lists 1,000 free monthly credits and $19/month Hobby on monthly billing, while its Monitor text says **7 credits** and table/FAQ say **1 credit** per page/check. That discrepancy remains unresolved; do not budget Monitor. [S13, effective September 4, 2026] X Search remains priced per fetched post/profile, not simply search call. [S11, “Tools Pricing”]

Other prior consumer-plan, quota and renaming claims are not renewed as decision inputs or WVB entitlements.

## 6. Exact unanswered questions for Builder

| Area | Evidence needed—not an instruction to execute now |
|---|---|
| **Canonical baseline** | Which immutable revision, uncommitted-diff hash, artifact and input manifest define A? Which additional cutoffs have parity receipts, including same-day verification and time corrections? |
| **Scale isolation** | What exact match/team IDs and minimum-match filters enter the live hitting helper? Does it jointly return or re-estimate home advantage? Can B change only the scale population while preserving all other A behavior? What are its variance intermediates on each training sample? |
| **Iteration state** | What variable is initialized from preseason opponents, and are there exactly four subsequent synchronous updates? Is stored state season evidence or blended rating? Does lookup apply the opponent's `w_j`, and is any quantity restandardized/clipped inside the loop? |
| **Missing evidence and graph** | When a box/prior is missing, which numerator, denominator and `n_i` change? Is each opponent row nonnegative and normalized/subnormalized? What happens to zero-game teams and disconnected components? |
| **Forecast numerical behavior** | Does prediction consume raw score or displayed/restandardized POWER? Is the rally mapping deterministic? Which neutral classifications, precision and simulator settings must be frozen for probability tolerances? |
| **Evaluation ancestry** | Which outcome IDs occur in slope-fitting versus reported checkpoints, and how often? Which priors/constants/feature choices used those outcomes? What are the exact unique-match, forecast-row and overlap counts? |
| **Pre-serve proof** | Which forecasts have immutable creation/input-observation evidence and a defensible first-serve bound? What is the reschedule policy, and which historical snapshots preserve corrections as known then? A file label asserting “pre-serve” is not the receipt. |
| **2025 event contracts** | What precise file/version/licence is held? What competitions and matches does it cover? Do per-rally winners, named servers, first servers, substitutions, penalties and scorelines reconcile? Are rotation labels slots or physical states? |
| **Passing/contact readiness** | Can candidate rows be joined to canonical fixtures and segmented by scope, corrections and grader? Are category counts and GP definitions available? Are any authorized contact/video exports already held, with explicit permitted uses? |
| **WVB-only environment** | What host/OS/RAM, scheduler, dependencies, isolation boundaries and approved project credentials actually exist? Is any measured bottleneck large enough to justify DuckDB or a local model? |

## Appendix A. Fixed-point derivation and code conditions

**H — Derivation under assumptions, not a reproduction of Builder's code.** Let `p` be fixed preseason ratings; `W=diag(w_i)` with `w_i=n_i/(n_i+10)`; `P_ij` the fixed nonnegative share of team i's retained match evidence against j; and `c_i` its mean margin/hitting performance contribution after fixed scaling/home adjustments.

When both channels share the same opponent rating and blend 0.75/0.25, the opponent coefficient is one. Margin-only fallback also has coefficient one. Thus missing boxes change `c`, not necessarily `P`; this conclusion fails if the implementation uses separate channel populations/averages or changes match retention.

### Season-evidence representation: weights inside lookup

```
s[0]   = c + P p                         # initial prior-opponent calculation
r[t]   = (I - W) p + W s[t]              # opponent's blended rating
s[t+1] = c + P r[t]
       = c + P(I - W)p + P W s[t]
```

Four subsequent updates mean `s[1]` through `s[4]`, followed by its corresponding blended output. For this state, the operator is **P W**. A sufficient sup-norm contraction factor is

```
q_s = max_i sum_j P_ij w_j < 1.
```

For normalized/subnormalized rows and finite match counts with k=10, `q_s <= max_j w_j < 1`. The weights in this bound belong to the **opponents j**, not just focal team i.

### Equivalent blended-rating representation

Starting `z[0]=p`, define

```
z[t+1] = (I - W)p + Wc + W P z[t].
```

Here the operator is **W P**, with `q_z=max_i w_i sum_j P_ij < 1`. Under the stated equivalence, the initial calculation plus four additional passes yields `z[5]`, not `z[4]`. Do not introduce an extra W by mixing the two representations.

### Conditions Builder must verify

Priors, retained matches, weights, normalization and scaling must be frozen during iteration. Updates must use the asserted prior-pass state; in-place updates need a separately matched analysis. A missing-prior opponent must have an explicitly understood omission/fallback, and a zero-evidence team must have a defined prior-preserving treatment. State-dependent standardization can invalidate the affine argument: distinguish display-only POWER normalization from transformations inside opponent lookup. Negative or excessive row weights require computing the actual operator bound. An activated pure-season weight of one would also invalidate the simple strict-bound argument; that switch is held in the supplied evidence. [P0; P1]

Disconnected schedules do **not** prevent a unique anchored solution under these conditions: each component has prior anchoring. They do prevent the played matches alone from establishing strong cross-component comparisons. Numerical convergence is not national statistical identification.

For either affine map `F(x)=b+A x`, with induced norm bound `q<1`, a frozen-state residual gives

```
||x - x*||_infinity <= ||F(x) - x||_infinity / (1 - q).
```

A linear solve of `(I-A)x=b` is an optional reference only after affine equivalence is verified; check its residual and conditioning. Otherwise use a matched iterative reference and document the diagnostic's limitations. Raw-score errors must also be propagated through the actual forecast mapping: a two-team rating error can alter predicted margin by up to `3.05 × (|error_i|+|error_j|)`, but a probability bound needs that mapping's sensitivity. Evaluate probabilities directly rather than assuming a logistic derivative.

## Appendix B. Serving model, uncertainty and attribution

**R — Possible minimum specification, not a selected implementation:**

```
logit Pr(serving team wins rally r) =
    intercept
  + serving-team effect
  + receiving-team effect
  + observed own/opponent serving-slot context
  + identifiable server-within-team deviation
  + match/set context effect
  + prespecified pre-rally score/set-number terms.
```

Use partial pooling rather than unshrunk small-sample leaderboards. When server and slot do not vary independently, replace their separate deviations with an estimable combined cell effect and state the limitation. A prior can mathematically separate confounded coefficients without making that separation empirically identified.

Service runs are outcome-dependent sequences, not fixed independent trials. Preserve run/match structure in uncertainty checks; assess sensitivity to match-level resampling or an explicit correlated-rally model. Model-based intervals remain conditional on their assumptions. Report opportunity counts and interval width, not a universal “reliable after N serves” claim. Do not adjust away observed pass quality when estimating the overall serving association without stating that it is a downstream mechanism; any conditional estimand would differ.

For the dossier, separate observed rates, context-adjusted associations and hypotheses. No adjustment above identifies a causal server effect without stronger measurement and design.

## Appendix C. Access failures and limits of verification

| Source/action | What happened in this review | What remains unknown |
|---|---|---|
| [Figshare landing record](https://figshare.com/articles/dataset/NCAA_Division_I_Volleyball_Match_Data_2025_Season/30472025) | Metadata and unversioned DOI rendered. The visible Download action failed in the research browser. | Actual file contents, complete schema, collection method and downloadable version. |
| [Figshare article API](https://api.figshare.com/v2/articles/30472025), [versions endpoint](https://api.figshare.com/v2/articles/30472025/versions), and version-specific landing attempt | Research browser returned internal access errors; no usable version metadata. Builder's reported **403** is separate evidence; this tool did not expose an HTTP status proving the same failure. | Exact version and account/access requirements. A failed retrieval does not establish that login is required or data is private. |
| [DataCite metadata endpoint](https://api.datacite.org/dois/10.6084/m9.figshare.30472025) | Attempt did not return usable content through the research browser. | No supplemental version metadata confirmed. |
| [Powers journal DOI](https://doi.org/10.1515/jqas-2024-0038) / [publisher full text](https://www.degruyterbrill.com/document/doi/10.1515/jqas-2024-0038/html) | Full journal text could not be inspected through the research browser. The arXiv preprint, record and authors' NESSIS slides were available. | Whether the journal version supplies further data-owner/access information. No publicly downloadable corpus or outside-access terms were established. |
| Restricted volleyball sources and paid accounts | No new StatBroadcast/VolleyTalk acquisition, licensed-account login, vendor contact or bypass was attempted. | Applicable live coverage, contractual permissions, specific export fields and costs. |
| WVB repository/runtime | Relied on supplied packet/corrections; no live checkout, model run, data audit or hardware test was performed. | Exact code facts and operational readiness listed in §6. |

**Unresolved is not impossible.** The missing contact corpus/permissions, replacement benchmark and WVB local-AI readiness remain unestablished.

## Primary-source register

All external pages below were checked **2026-09-26**. An undated live page is not assigned an invented publication date. Vendor documentation verifies what is documented—not actual account access, coverage or performance.

**P0.** `SHARED-RESEARCH-CORRECTIONS.md` — supplied September 26, 2026. Sections “Forecast benchmark,” “Current implementation and experiment boundaries,” “Data availability,” “Scope.” Controlling project evidence.

**P1.** `POWER-RESEARCH-PACKET-REVIEWED.md` — supplied September 26, 2026. Embedded Current Model §§2–7/10; Discussion metrics, C6 and Validation §E; Data Inventory; Passing Quality. Earlier conflicting benchmark statements are superseded by P0.

**P2.** `POWER-OUTSIDE-RESEARCH-2026-09-26.md` — original report being corrected, especially §§1.2, 2.1/2.6, 3.2 and 4.8–4.11. Not an independent source validating its own claims.

**[S1] Figshare / Zachary Jacques.** Record posted October 28, 2025, 22:21; description, DOI, history and licence: https://figshare.com/articles/dataset/NCAA_Division_I_Volleyball_Match_Data_2025_Season/30472025

**[S2] Scott Powers, Luke Stancil, Naomi Consiglio.** *Estimating individual contributions to team success in women's college volleyball*, arXiv v1, February 2, 2024; §§2, 3, 6.1: https://arxiv.org/html/2402.01083v1 . Journal DOI metadata: https://arxiv.org/abs/2402.01083 . Authors' NESSIS 2023 slides, reviewed for source/access attribution: https://www.nessis.org/nessis23/Scott-Powers-approved.pdf . Charting owner and outside access remain unconfirmed.

**[S3] Leonardo Egidi, Ioannis Ntzoufras.** *A Bayesian Quest for Finding a Unified Model for Predicting Volleyball Games*, v1 November 5, 2019; v2 April 15, 2020. §§3.4, 5.3–5.4: https://arxiv.org/html/1911.01815 . Version history: https://arxiv.org/abs/1911.01815 . No target-matched Brier/log-loss benchmark located in accessed text.

**[S4] Jeffrey R. Stevens / ncaavolleyballr.** Maintainer's data catalog, “Play-by-play data,” women's D-I 2025 links; undated live documentation: https://jeffreyrstevens.github.io/ncaavolleyballr/articles/data.html . Presence of a file link is not a completeness or rights audit.

**[S5] DuckDB project.** FAQ, “Is DuckDB open-source?”: https://duckdb.org/faq . “JSON Overview”: https://duckdb.org/docs/current/data/json/overview . Live documentation.

**[S6] Ollama.** “Structured outputs”: https://docs.ollama.com/capabilities/structured-outputs . FAQ, local data handling, disabling cloud and network binding: https://docs.ollama.com/faq . Runtime MIT licence: https://github.com/ollama/ollama/blob/main/LICENSE . Model licences are separate; live documentation.

**[S7] Hudl.** “Volleymetrics to Hudl Transition Hub,” FAQs “Which teams can access…” and “What about Data Volley DVW / Sportscode XML data file exports?”: https://www.hudl.com/en_gb/products/volleymetrics/transition . Live 2026 transition documentation; public page does not establish an applicable Cody subscription or match-specific coverage.

**[S8] OpenAI.** API pricing, flagship models, **Standard / short context**: https://developers.openai.com/api/docs/pricing . Live price verification only; no WVB entitlement inferred.

**[S9] Anthropic.** Claude Platform pricing, base token prices: https://platform.claude.com/docs/en/about-claude/pricing . Live documentation.

**[S10] Google.** Gemini Developer API pricing, “Gemini 3.5 Flash-Lite,” Standard: https://ai.google.dev/gemini-api/docs/pricing . Live documentation.

**[S11] xAI.** API pricing, Text API and Tools Pricing / per-item X Search: https://docs.x.ai/developers/pricing . Live documentation.

**[S12] Anthropic.** “Run Claude Code programmatically,” “Start faster with bare mode”: https://code.claude.com/docs/en/headless . Live documentation.

**[S13] Firecrawl.** Pricing, “Pricing at a glance,” API Credits and FAQ; stated effective September 4, 2026: https://www.firecrawl.dev/pricing . Monitor's conflicting rates are not reconciled by this review.

[S1]: https://figshare.com/articles/dataset/NCAA_Division_I_Volleyball_Match_Data_2025_Season/30472025
[S2]: https://arxiv.org/html/2402.01083v1
[S3]: https://arxiv.org/html/1911.01815
[S4]: https://jeffreyrstevens.github.io/ncaavolleyballr/articles/data.html
[S5]: https://duckdb.org/faq
[S6]: https://docs.ollama.com/capabilities/structured-outputs
[S7]: https://www.hudl.com/en_gb/products/volleymetrics/transition
[S8]: https://developers.openai.com/api/docs/pricing
[S9]: https://platform.claude.com/docs/en/about-claude/pricing
[S10]: https://ai.google.dev/gemini-api/docs/pricing
[S11]: https://docs.x.ai/developers/pricing
[S12]: https://code.claude.com/docs/en/headless
[S13]: https://www.firecrawl.dev/pricing
