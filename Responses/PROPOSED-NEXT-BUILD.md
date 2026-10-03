# Proposed next build: for joint decision (Builder, 2026-09-26, mail 029)
**PROPOSAL ONLY. Nothing here is approved, and no code has been changed.** Every build hold stays in force until Cody approves a scope.

Three phases, in recommended order. A and B can run side by side, because they touch different files. C waits for A's evaluation contract. Effort figures are **Builder estimates**, not commitments.

---

## Phase A: prediction and evaluation integrity
**Goal:** know exactly what we can honestly claim about forecast accuracy, and make every future comparison trustworthy.

### What is true today (read-only inspection)
- **`predict_2026.py:append_log`** writes the **first-ever** forecast per game id, permanently, with game, date, teams, `home_win`, `neutral`, `played_2026` and `logged_utc`.
  - It stores **no model version, no k, no input or corpus fingerprint, no data cutoff**.
  - The first forecast for a fixture is often days before the match. It is not the last pre-match forecast.
- **`score_predictions.py:build`** checks timing: it excludes a forecast logged **strictly after** the **stored** feed start epoch.
  - It fails **open**: a missing epoch, a missing `logged_utc` or a parse error is still scored. The Reviewer found 0 such cases in the current snapshot.
  - It excludes team-name mismatches (68).
- **Stored snapshot:** 2,101 scored, Brier 0.1799, favourite 73.2% (Reviewer inspection). The 0.1289 "reference" printed beside it is a different estimand and is misleading.
- **Retrospective numbers:** the 0.1718 calibration run reuses outcomes in fit and evaluation, on a different implementation. There is no clean retrospective number for today's model.

### Proposed changes (minimal)
1. **Provenance on every new log row.** Add `model_version` (git commit), `k`, `hit_weight`, `tau_hit`, the blend corpus fingerprint, the rating cutoff epoch and an input hash.
   - Existing rows are **never rewritten**; they are labelled `provenance: pre-2026-09-xx (unversioned)`.
2. **Two issuance streams, never mixed.**
   - Keep **first-issued** (the current behaviour, renamed so nobody mistakes it).
   - Add **last-pre-match**: the latest forecast whose `logged_utc` precedes the stored start, frozen at start.
   - Each is scored and labelled separately.
3. **Fail-closed scoring.** A missing or unparseable time is **excluded and counted**, not scored. Equal timestamps count as late.
4. **Honest display labels:**
   - the live accuracy line reads "Recorded first-issued forecast performance, as of <snapshot>; timing against the listed start";
   - the misleading 0.1289 reference is removed;
   - nothing claims "held-out" or "validated".
5. **A development replay harness** (offline, `Cody/coordination/research/prototype`, reusing Round-2): replay the **exact live code** on frozen 2025 inputs.
   - Label it **development evidence**. 2025 already informed the design, so it is not validation.
   - It is kept strictly separate from the prospective 2026 streams.

- **Files likely affected:** `scripts/predict_2026.py`, `scripts/score_predictions.py`, `scripts/build_hub.py` (accuracy label), `data/raw/2026/prediction_log.jsonl` (append-only, new fields), `test_score_predictions.py`, a new test.
- **Dependencies:** none. It does not touch the POWER formula.
- **Smallest user-visible deliverable:** the accuracy line on the site states what it is and as of when. A new "Prediction record" note appears in Methodology.
- **Checks:**
  - new rows carry every provenance field;
  - old rows are unchanged byte-for-byte (hash);
  - fail-closed has negative controls (a missing time must be excluded);
  - the two streams never mix;
  - scoring the existing log still reproduces 2,101 / 0.1799 under the first-issued stream.
- **Effort (estimate):** 0.5–1 day, plus a half-day for the replay harness.
- **Decision needed from Cody:**
  1. Approve adding the last-pre-match stream, or keep first-issued only.
  2. Approve removing the 0.1289 reference line. It is display text, currently held.

---

## Phase B: one team + player analysis page (Stanford first)
**Goal:** Cody's product direction. The statistics tell the story of a team's season, with facts separated from hypotheses. **No rating weights change.**

### Scope
- One new **Analysis** panel inside the existing team dossier (Overview/Matches/Roster/Numbers/Scouting/Outlook already exist). It is built for **Stanford 2026**, and reuses the same code for any team.
- A **historical comparison block: Texas A&M 2025.** It is feasible from our own 2025 box scores (`data/raw/2025/boxscores.jsonl`, `playerbox.jsonl`) and cross-checks against the verified A&M PDF figures (18.48 PPS, 118 sets).

### Content (all from box scores we already hold)
- **The ten metrics as team season and rolling values:**
  - earned PPS with its components;
  - opponent earned PPS and scoreboard points allowed;
  - kill%, error%, hitting% and attempts per set;
  - assists, digs and blocks per set (team scoring blocks kept separate from player participation);
  - aces and service errors, **per serve attempt** and per set.
- **Per-match trend** with counts, and match-to-match spread. No trend claims without the opponent shown.
- **Opponent context:** each match shows the opponent's POWER at the time (existing `oppChips`).
- **Role context** (pins / middles / setter / libero):
  - who carried the attempts (share of team TA);
  - each player's own baseline;
  - roster position labelled **"listed position"**, never "attack location".
- **Lineup context:** set-1 starting six from `lineups.jsonl`, plus 5-1/6-2 detection.
  - **Stanford:** show setter lineups and the team's efficiency by setter-start **as observed association**, plainly labelled as not a setter-quality verdict. This is Cody's case study, recorded as his hypothesis.
- **Availability:** sourced statuses only. Box-score absence is labelled "not in box", never "injured".

### Rules
- **Identity:** player identity comes from the name-normalized feed keys (the existing `nkey`).
- **Denominators:** season rates are always summed counts ÷ the right denominator (sets, TA, serve attempts), shown next to the rate.
- **Coverage:** matches without a box score are listed as missing, not zero.
- **Data not held** (passing grade, set location, block touches, 2026 rally data) shows "not available", not zero.
- **No composite score, no invented thresholds** (no "18.7 = champion").

### Design
Preserve current decisions:
- Oswald display type / system body / Roboto Mono numerals;
- the lavender layer system and floating panels;
- the depth radii tokens;
- the provenance tags;
- phone-first, verified with `scripts/phone_probe.py` at 390 px, no horizontal page overflow.

- **Files likely affected:** `scripts/build_hub.py` (the dossier panel and payload), possibly a new `scripts/team_analysis.py` (pure computation), a new `scripts/test_team_analysis.py`.
- **Dependencies:** none on Phase A or C.
- **Smallest user-visible deliverable:** Stanford's team page gains an "Analysis" tab showing the ten metrics with trends, opponent context and role splits.
- **Checks:**
  - every displayed rate recomputed from summed counts (reconcile by value, like the existing team-stats guard);
  - the A&M 2025 block reproduces the verified PDF totals (1,716 kills, 157 aces, 307.5 team blocks, 118 sets);
  - "not available" never renders as 0;
  - no causal wording (lexicon guard);
  - phone_probe clean;
  - public-build rules respected (no private sources).
- **Effort (estimate):** 2–4 days for Stanford plus the generic panel; +0.5–1 day for the A&M comparison.
- **Decisions needed from Cody:**
  1. Stanford first (recommended), or another team.
  2. Private build only, or public too.
  3. Include the setter-start association view now, or defer it.

---

## Phase C: isolated offline diagnostics, then one shadow candidate
**Goal:** answer the open model questions cleanly **before** any POWER change. No diagnostic runs until separately approved.

### Frozen inputs
A snapshot of `data_2025.json`, the 2025 box scores, the current code at a named commit, and the prior file, each fingerprinted.

### Diagnostics
1. **Hitting-scale floor (DISCUSSION C1, corrected).** Three arms: exact live (A), population-only (B), floor removal on B's freshly fitted raw variance (C). Non-positive raw variance means "not estimable", with no new minimum.
2. **Opponent-iteration convergence:** the change in scores at passes 3→4 and 4→5 on 2025 and 2026 frozen inputs. **Reported, not tuned.**
3. **Neutral-site sensitivity (rating only):** 2026 only, since 2025 has no venues. Rating with H = 0 at classified-neutral venues vs nominal. A descriptive difference in ranks, not a performance claim.

### Evaluation rules
- **Primary metric:** per-unique-match log loss, with one forecast per match at a stated information cutoff (past days only). Delta = candidate − baseline, **negative = better**. Brier and calibration are safeguards.
- **Uncertainty:** weekly block bootstrap, 14-day sensitivity.
- **Wording:** a CI spanning zero is **inconclusive**, never "equivalent" or "beneficial".
- **Promotion criteria, set in advance by Cody + Reviewer + Builder, not by the Builder alone.**
  - Suggested form: the paired log-loss CI is wholly below zero on 2025 development replay, **and** the candidate is not worse on the prospective 2026 shadow over a pre-set window.
  - It must also stay calibrated (slope CI covers 1).

### Shadow
If a diagnostic motivates a candidate, **one** candidate is frozen and logged daily next to live POWER, using Phase A's provenance. The existing 05:45 research job already records three models. The candidate is promoted only by the pre-set criteria.

- **Files likely affected:** research prototypes only (`Cody/coordination/research/prototype/`). Nothing live until promotion.
- **Dependencies:** Phase A's provenance and cutoff definitions.
- **Smallest deliverable:** a one-page diagnostics receipt per question, each with numbers, CI and sign.
- **Checks:**
  - leakage tests (same-day and later results can't move pregame values; reuse `test_round2.py`);
  - replica parity at **several** cutoffs, not just one;
  - fingerprints recorded.
- **Effort (estimate):** 1–2 days for the three diagnostics; the shadow is ongoing.
- **Decision needed from Cody:** approve running the diagnostics, and agree the promotion rule.

---

## Deferred (backlog, kept)
These stay deferred until data, rights and benefit are known. All are recorded in `Cody/coordination/ideas/`.
- Passing grades: captured; the game join and quality issues are open.
- Set location, block touches, 2026 rally data.
- Computer vision / manual rally tagging pilot. This needs a recording and a rubric; the thresholds (0.85, 70%, 2 minutes) are not adopted.
- Paid feeds, local models.
- 2025 server rally-win % and side-out/break descriptive history. Possible in Phase B later, from ncaavolleyballr (MIT) 2025 data, once completeness and rights are checked.

## Recommended decision
Approve **A and B now**; they are independent. **C's diagnostics** follow A. Keep POWER unchanged until C's pre-set criteria say otherwise.
