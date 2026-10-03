# POWER outside-research addendum

**Date:** 2026-09-26  
**Status:** research only. No build, install, purchase, vendor contact, crawl, or live ranking change.  
**Reads with:** original Grok file `POWER-OUTSIDE-RESEARCH-2026-09-26.md` plus `SHARED-RESEARCH-CORRECTIONS.md` (corrections win on conflicts).

---

## Plain-English takeaway

Keep live POWER frozen. Use it as a strength rating with a separate forecast mapper. Build the analysis page from counts you already have. Do not add component weights because a page needs a story.

Three facts from the shared correction change the first report:

1. The historical 0.1718 Brier is **not** a clean held-out score of today’s live model. Do not compare it to 2026 Brier 0.180 as like-with-like.
2. Forecast code already zeros the home term on venues classified neutral. The *rating* still uses nominal home/away. Those are different stages.
3. Missing a complete automated 2026 rally file **in this pipeline** is not proof that no authorized 2026 source exists anywhere.

Three facts this addendum corrects in the first Grok report:

1. RallyIQ on 2026-09-26 is a **joint penalized binomial** serve/receive model. The one-pass box adjustment is **hitting**, and it does not feed forecasts. Several numeric performance claims I quoted are **not on the current methodology page** and are withdrawn as current-page evidence.
2. Digs should not subtract both opponent attack errors and stuff blocks. A blocked swing is already an attack error in NCAA accounting.
3. SQLite and DuckDB do different jobs. Dismissing SQLite because DuckDB is good at analytics was wrong.

---

## Corrections and evidence

| Claim in first Grok report | Verdict | What stands now | Source (checked 2026-09-26) |
|---|---|---|---|
| 2025 forecast Brier 0.172 is a held-out estimate of live POWER | **Withdraw as production generalization.** Shared correction: older calibration exercise; full-season variance/home before checkpoints; even/odd split still lets the same later match appear in fit and report; 11,284 is checkpoint observations, not unique matches; older exercise used preseason opponent strengths and separate averages, live uses per-match blend + iterative opponents. No replacement score is computed here. | Historical artifact. Different estimand from 0.1289 (simulator on observed margin) and from 2026 live Brier. | `SHARED-RESEARCH-CORRECTIONS.md`; packet CURRENT-MODEL §4 |
| RallyIQ = one-pass logistic; hitting in the same fit | **Corrected.** Joint ridge-binomial on serve and receive together. Hitting is a separate one-pass box adjustment. | See §A below. | https://collegevolleyball.app/methodology |
| RallyIQ 2026 74.5% / log loss 0.465; 2025 77.6% / 0.448 | **Withdraw as current-page figures.** Not on `/methodology` today. Not on `/ratings` in the 2026-09-26 re-read. First-pass summarizer output is not a dated page quote. | Self-reported method exists; **self-reported accuracy numbers for those two seasons are unverified on the live pages.** Do not compare them to POWER. | `/methodology` and `/ratings` re-read 2026-09-26 |
| RallyIQ home +0.7 pp and h = 0.027 logits | **Keep, but locate them on `/ratings`, not `/methodology`.** | `/ratings` states home edge “+0.7 pp on both break % and sideout %” and “h = 0.027 logits.” `/methodology` writes `h·home` without those numbers. | https://collegevolleyball.app/ratings |
| Ridge ≈ three matches | **Keep as `/ratings` prose, not a measured reliability study.** | `/ratings`: pull “worth a fixed number of rallies, roughly three matches’ worth of serving.” `/methodology`: “The pull is worth a fixed number of rallies, so it fades as games accumulate.” No derivation shown. | same two pages |
| RallyIQ data source = public NCAA PBP, specified host | **Partially known.** | Documented: “public NCAA game data,” scoreboard polled every five minutes, box and PBP pulled when a match goes final, only PBP-verified finals enter RallyIQ. **Host (ncaa.com vs stats.ncaa.org vs other) is not named. Treat as unknown.** | `/methodology` |
| Neutral-site fix needed in the forecast mapper | **Overstated.** Shared correction: `predict_2026.py` already drops the direct home term for classified-neutral venues. Remaining issue is the **rating** home term in `digby_top25.py`. | Do not rediscover forecast-neutral handling. | Shared correction |
| ncaavolleyballr proves 2026 rally data is impossible | **Overstated.** | Package v0.5.1 documents extract coverage **2020–2025** and warns that frequent hits can block an IP. That is one dataset/tool. It does not close StatBroadcast (browser-observed serving sequence; automation constrained), a licensed feed, or a future NCAA change. | https://github.com/JeffreyRStevens/ncaavolleyballr README; shared correction; packet `docs/rotations_finding.md` (not re-opened here) |
| arXiv:2402.01083 is a VolleyMetrics paper | **Withdraw vendor attribution.** | Paper says “charted data” for 2022 NCAAW (4,147 matches, 600k+ points, 5M+ contacts). HTML copy names **no vendor**. Charted ≠ VolleyMetrics. | https://arxiv.org/html/2402.01083 |
| NCAA manual says the feed `points` column is unusable | **Mis-attributed.** | Unreliable `points` / `totalBlocks` is a **project feed finding**. The 2026 NCAA manual defines PTS = K+SA+BS+½BA on the official box. Do not collapse those. | Packet CURRENT-MODEL §10; https://s3.amazonaws.com/fs.ncaa.org/Docs/stats/Stats_Manuals/Volleyball.pdf |
| Digs opportunity = opponent attacks minus stuff blocks minus attack errors | **Wrong.** | A stuffed attack is already an attack error. Subtracting both double-removes. TA−K−E also conditions on how the attack ended. | NCAA accounting identity; this addendum §C |
| DuckDB replaces SQLite | **Wrong framing.** | DuckDB: local analytical SQL over files (MIT, https://duckdb.org/). SQLite: public-domain transactional store (https://www.sqlite.org/). Review queues and flags want SQLite; reliability curves want DuckDB. Neither requires a purchase. | official homepages 2026-09-26 |
| Pablo `25650*(point%−0.5)`, cap 2500 ≈ 59% | **Keep, secondary source.** | DigNittany reprint, “edited for length and clarity from Rich Kern’s website.” Constant noted as smaller than the 30-point-set era (27,700). Home “usually worth 200 points.” Current RichKern FAQ page did not return usable content in this project’s fetch. | https://dignittanyvolleyball.com/rich-kern-poll-comparisons/ |
| Evollve home ~51% of points / ~59% of matches | **Keep as talk-transcript claim only.** | SSAC 2025 YouTube talk, not a paper. No independent replication here. | https://www.youtube.com/watch?v=Ny-DEQBUs2Y |
| Forman OR ≈ 1.54–1.64 at parity | **Keep as preprint abstract only.** | ResearchGate Oct 2025 preprint; not peer-reviewed in this pass. Specification-sensitive for BT/Colley/RPI. | https://www.researchgate.net/publication/396741898_Comparing_Opponent-Strength_Measures_for_NCAA_Indoor_Volleyball_-_Predictive_Accuracy_and_Home_Advantage_Stability |
| MotherDuck / Gemini / Codex / Claude dollar grid | **Mostly withdrawn from decision use.** | Only shortlist prices re-verified below. Other 2026 list prices in the first file are unverified for action. Claude.com/pricing this session rendered EUR (€15/€18 Pro), so even the Claude USD figures are geo-dependent. | see §E |

**Disagreement with the review, where I still hold a line:** a CI that includes zero does **not** prove two hitting-scale arms equivalent, and it also does **not** prove the channel empty. The first report’s “not distinguishable ≠ empty” still stands. The shared correction already says the small positive AUC walk and Round-2 inconclusive log-loss are different experiments.

---

## A. Corrected outside-model comparison

| System | Evidence unit | How strengths are fit | Home | Box skills | Prior | What we can actually cite |
|---|---|---|---|---|---|---|
| POWER rating | Scoreboard pts/set + optional hitting channel | Season mean of opponent-adjusted match evidence; 4 opponent-update passes after a prior start. Convergence of those 4 passes is **untested** in the shared review. | Nominal H = ±1 in `digby_top25.py` | Hitting 0.25 when both boxes have attacks | Blend k=10 | Packet + shared correction |
| POWER forecast | Rating difference → margin → rally/set model | Separate mapper | Direct home term **removed** when venue classified neutral | Uses the rating, not a second box model | Same rating | Shared correction on `predict_2026.py` |
| RallyIQ | Rally win when serving / receiving | **One joint ridge-binomial** over serving blocks in PBP-verified finals. `P(server wins) = logistic(μ + S_serve − R_receive + h·home)`. Newton to one optimum. No rating-on-rating loop. | `/ratings`: +0.7 pp on break and sideout; h = 0.027 logits. Neutral-site correction tried and **not used**. | AdjHit O/D from a **separate** one-pass box fit; **do not feed forecasts** | Last season RallyIQ −10% to middle × returning production; λ = 60 on `/ratings`; pull fades with rallies | Pages dated by this re-read only. Accuracy figures withdrawn. Source host unknown. |
| Pablo | Point % → rating gap; later mixed with W/L | Secondary description only | “Usually” 200 Pablo points | None in the reprint | Not documented here | DigNittany reprint of RichKern FAQ. Current official FAQ not retrieved. |
| VolleyDork / BTVB | Serve-level Bradley–Terry | MLE with serve and home offsets | Estimated | None in the ranking writeup | Mentioned as future work in the repo FAQ | https://github.com/dpwynne/BTVB ; 2023 blog. Not a 2026 audit. |

Do not rank these by quoted accuracy. Different units, different seasons, different leakage stories.

---

## B. Rewritten hitting-scale experiment

**Live baseline (do not alter in the same run):**

- Blend k = 10  
- Hitting weight = 0.25 when both attack boxes exist, else margin only  
- τ_hit = 0.100 (floor-bound helper, as shipped)  
- Countable-match definition as live  
- Forecast mapper **held fixed** at current slope/home rules (including already-neutral forecast handling)

Call this **A_live**. Every arm reports against A_live on the same checkpoints.

**Two factors, crossed only if both are pre-registered. Otherwise run as two separate 2-arm studies.**

1. **Population.** All 2025 finals used by `hit_scale_2025()` (packet: 349 teams) vs countable D-I only (margin side).  
2. **Floor.** Helper floor on vs floor off.  
   - Floor off: recompute τ_hit **inside that population** as √(var(team means) − σ²/n̄).  
   - Do **not** paste 0.0668 into the D-I-only arm. 0.0668 was an SD on the population that produced it.

Do not change weight, k, or forecast slope in the same table. If someone later wants nested recalibration of the forecast mapper, that is a **second** study with its own pre-registration.

**Report:** paired Δ log loss and Δ Brier vs A_live, block bootstrap by week, sample = checkpoint observations with dependence named. AUC optional and secondary.

**How to read a CI:**

- CI for Δ entirely above zero: candidate better on that metric, still not a ship decision by itself.  
- CI entirely below zero: worse; keep the floor or the old population.  
- CI contains zero: **unresolved**, not “equivalent,” not “safe to change,” not “safe to ignore.”

**Stop:** if the only movement is inside noise, document the floor as a regularizer and leave live τ_hit = 0.100.

---

## C. Digs, first ball, and what is estimable now

### Digs — named descriptive alternatives

Do **not** use “opponent TA − K − E − stuff blocks.” Stuff blocks are already inside attack errors.

| Name | Formula | What it is | What it is not |
|---|---|---|---|
| Digs per set | digs / match sets | Workload / volume | Quality or save rate |
| Digs per opponent attack attempt | digs / opponent TA | Volume per swing | Save probability |
| Digs per continued attack | digs / (opponent TA − opponent K − opponent E) | Digs on swings that were neither a kill nor an error. Useful as an accounting remainder. | A probability. Conditioned on the attack already failing to kill or error, including stuffs. |
| Opponent kill % | opponent K / opponent TA | Termination allowed | Isolated floor defense |
| Opponent error % | opponent E / opponent TA | Errors allowed, including stuffs and unforced | Isolated blocking |

Show counts next to every rate. Role and opponent attack volume stay in the caption.

### Aggregate indicators vs first-ball / transition events

**Box-only aggregates (estimable now from team/player boxes):**

- Reception error rate = RE / RA  
- Service ace rate = SA / serve attempts; service error rate = SE / serve attempts  
- Side-out is **not** in the box. Break rate is **not** in the box.  
- Opponent kill % while we “should have been in receive” cannot be isolated from a box.

**First-ball side-out (FBSO) and transition** need a rally schema, not a renamed box column. Honest S-comp from boxes is only: opponent-adjusted RE/RA, SA/SE per attempt, Δhit, opponent kill %. Calling any of those “first-ball side-out” is a naming error.

**Event schema if a rally file is authorized and complete enough:**

```
match_id, set_n, rally_n
serving_team_id, receiving_team_id
server_player_id?          -- often missing on ncaa.com
first_receiver_player_id?
pass_grade?                -- not in NCAA PBP
first_set_player_id?
first_attack_player_id?
first_attack_result?       -- kill / error / blocked / dug / replay
rally_winner_team_id
point_type: serve_error | ace | first_ball | transition | unknown
rotation_index?            -- serving order ≠ on-court six
source, fetched_at, corrected_flag
```

**Estimable in this project today (bounded):**

- 2025 derived sideout / rotation artifacts already in inventory, completeness and rights still their own check.  
- 2026 team boxes: RE/RA, SA/SE, hitting, blocks as NCAA-defined.  
- 2026 named server on every rally: **not in the current automated pipeline.**  
- 2026 serving *team* and rally winner from ncaa.com PBP: **unknown completeness**; do not assume RallyIQ’s filter is your filter.

**Conditional on data not verified here:** FBSO %, in-system rate, pass 0–3, middle-available after serve, transition side-out, individual server quality net of rotation.

### Joint serve/receive without fake N

One rally produces one Bernoulli: serving team wins or not. The joint model uses that **single** outcome to update both S_server and R_receiver. That is sharing a parameter space, not doubling the sample. Effective information is the number of rallies, not 2× rallies.

Team serve strength ≠ individual server quality. Rotation, passer, block, and opponent error sit in the same rally. Label team figures “points won while this team served.” For a player, show attempts, rotation mix, and an interval. Service runs are dependent; do not treat 50 serves as 50 independent trials.

---

## D. Answers to the remaining open questions

**RallyIQ source.** Documented as “public NCAA game data” plus PBP-verified finals. Specific NCAA property is **unknown**.

**Do not declare all 2026 sources impossible.** The negative ncaa.com named-server finding is source-specific (packet rotations note; shared correction). StatBroadcast serving sequence was browser-observed and is not approved for automation. Licensed or school-shared files are out of scope until someone with rights offers them.

**Neutral-site effect size.** Not estimated here. No tournament-share guess. The live question is only: how many 2026 rating inputs currently get a nonzero H on a venue the fixture ledger would call neutral, and does flipping those H change ranks or forecasts. Forecast mapper already has a neutral branch.

**Passing rows.** 709 parsed rows, 510 candidates, zero required to be matches. Joins, grader vs poster, and scope remain open.

**Points column.** Project feed problem, not a manual rewrite.

---

## E. Narrowed tools (job → tool)

| Job | Tool | Verified 2026-09-26 | Incremental value | Stop |
|---|---|---|---|---|
| System of record, append-only games | Existing JSONL | Already in repo | None to replace | Keep |
| Review queue, alias table, flags, gid joins | **SQLite** (or the same idea in JSON with transactions) | Public domain, https://www.sqlite.org | Stops silent duplicate grades | If a folder of reviewed CSV already enforces unique (gid, player, source) |
| Reliability curves, opponent-adjusted rates | **DuckDB** local | MIT, https://duckdb.org | SQL on files without a warehouse | If one notebook already reproduces the three packet examples |
| Private classification of user-supplied passing text | Local runtime (Ollama local is free; cloud is separate) | https://ollama.com/pricing | Only if those files must not leave the machine | If Cody reviews the queue by hand |
| Coding / packet work | Assistant already in use | Claude.com/pricing this session showed Pro €15 annual / €18 monthly in this fetch; USD pages differ by region. Code is bundled on paid Claude plans per that page. | No second seat required for research | Do not buy a seat to “get a sports API” |

Not shortlisted, prices not re-verified for action: MotherDuck, Gemini/Antigravity, Codex tiers, Sportradar, Hudl college quotes, W&B, dbt.

---

## F. Three prioritized investigations

### 1. Hitting-scale two-factor diagnostic (read-only)

- **Data:** 2025 countable D-I set and the current `hit_scale_2025()` population, already on disk.  
- **Validation:** A_live frozen; one factor at a time as in §B; paired log loss / Brier; week-block bootstrap; dependence disclosed.  
- **Stop:** CI contains zero on both metrics → leave τ_hit = 0.100 and write “regularizer.” Do not then retune weight or k in the same pass.

### 2. Stratified event-file audit (read-only, current feeds only)

Not “20 convenient matches ⇒ national coverage.”

- **Frame:** all 2026 finals that already have a stored PBP payload in *this* repo, then a **stratified subsample** if the frame is large: conference (P4 / mid / low), site (home / away / listed neutral or tournament title), platform if the payload names one, early vs late season, school-verified vs not.  
- **Checks per match:** rally count vs sum of set points; missing rallies; whether rally 1 names a server; serving-team completeness; named-server completeness; penalty / replay / substitution rows; whether reconstructed set scores match the official line; whether a later correction exists in the ledger.  
- **Report:** coverage by stratum, not a single percentage.  
- **Stop:** if serving-team tags are sparse in several strata, do not spec a 2026 RallyIQ-shaped shadow. Historical 2025 sideout artifacts can still be used for description.  
- **Out of scope:** new collection, StatBroadcast automation, ncaavolleyballr 2026 live scrape.

### 3. Descriptive analysis objects from boxes + 2025 event artifacts

- **Data:** current team/player boxes; roster position labeled as roster position; availability flags; 2025 sideout/rotation files after a rights/completeness note.  
- **Build (research spec only):** earned PPS, kill% / error% / TA per set, opponent kill% and opponent earned PPS, RE/RA, SA/SE per attempt, team blocks per opponent TA, digs per opponent TA, n and a simple shrink-to-league-mean. No new weights.  
- **Validation:** reconcilable to summed counts; no double-counting of stuffs as extra errors; Stanford shown as a setter-workload case with lineup context, not a coefficient.  
- **Stop:** if a metric’s split-half reliability is unusable at current n, show the count and hide the rate, or keep the rate with a wide interval. Do not promote it into POWER.

Passing option A (user exports → review queue → gid join) can sit under (3) only for rows that survive flags. It is not a fourth live investigation.

---

## G. One example without invented coefficients

**Texas A&M, 2025 champion season, already in the packet.**

Season earned PPS 18.48 on 33 matches / 118 sets. Kills were 78.7% of credited points (K/S 14.54, aces/S 1.33, blocks/S 2.61). They won the final at **16.67** PPS and won 10 of 13 matches below 18.

Read that with role and opportunity, not with a new weight:

- 16.67 PPS in a final is low relative to *their own* season mean. It is not a failed season and not a rule that champions must clear 18.  
- Kills/set mix volume (attempts/set) and termination (kill%). The packet already separates those. Roster position (OH / MH / OPP) is not attack location; say so on the page.  
- Opponent earned PPS 14.42 is not “A&M defense.” Opponent aces include A&M reception; opponent blocks include A&M set/attack/coverage; opponent kills mix A&M serve, block, and floor.  
- Blocks cannot assign blame to the middle versus the pin versus coverage. That needs tagged rallies you do not have for 2026.  
- Availability: if a starter is missing from a box, that is absence from the sheet, not a diagnosed injury. Margin in that window is association.

Same template for 2026 A&M or Stanford: show the ten countable series with n, opponent, and lineup notes. Leave POWER’s 75/25 blend alone until investigation 1 says otherwise.

---

## Access-failures list

| URL / source | Result 2026-09-26 |
|---|---|
| https://collegevolleyball.app/methodology | Loaded. Joint ridge-binomial text present. No 74.5 / 0.465 / 77.6 / 0.448 / +0.7 pp / 0.027 logits / “three matches.” |
| https://collegevolleyball.app/ratings | Loaded. +0.7 pp, h = 0.027 logits, λ = 60, ×0.9, “roughly three matches’ worth of serving.” No 74.5 / 0.465 / 77.6 / 0.448 in this re-read. Games-in-fit counts moved between fetches (2,105 vs 2,190 in tool passes) — treat as a live page. |
| https://www.richkern.com/vb/rankings/FreePageRankings.asp | Earlier fetch returned insufficient FAQ content. Pablo formula taken from DigNittany reprint only. |
| https://arxiv.org/html/2402.01083 | Loaded. No VolleyMetrics/Hudl vendor string. |
| https://github.com/JeffreyRStevens/ncaavolleyballr | Loaded. 2020–2025 extract range; IP-block warning for frequent access. No 2026 in-season data drop. |
| RallyIQ underlying NCAA host | Not disclosed on the two pages. |
| Forman full PDF | Abstract/preprint metadata only in this pass. |
| Evollve method | YouTube talk only. |
| Claude.com/pricing | Loaded; this session rendered euro personal prices. Do not treat prior USD figures as universal. |
| Hudl college VolleyMetrics price | Still quote-only; not fetched as a number. |
| Sportradar NCAA WVB coverage matrix | Not checked match-by-match. Do not infer coverage from the generic volleyball API page. |

---

*End of addendum. No implementation authorized.*
