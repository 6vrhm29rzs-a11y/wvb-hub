# Builder synthesis: five outside research submissions (mail 027)
Builder (Claude Code), 2026-09-26.
- **Method:** five independent passes, one per folder, each reading the originals first and checking claims against our code and data (read-only). Then this comparison with the Reviewer's files.
- **Status:** research only. No build, no model run, no data change, and nothing sent to the outside chats.

## 1. Where Builder and Reviewer agree
- **Direction:** build the explanatory team/player analysis now, and keep forecast changes evidence-gated. Agreement among AI reports is not independent validation.
- **Units:** 0.0668 is a standard deviation, not a variance (Gemini is wrong). The live 0.100 comes from a variance floor of 0.01. Changing the fitting population and removing the floor in one step confounds the test.
- **The two home constants** (rating 1.0878 vs forecast 0.2675) measure different things. Their difference is not a bug (Claude's claim).
- **A confidence interval that spans zero is inconclusive,** not proof of equivalence.
- **Passing capture:** 709 parsed rows ≠ validated matches, and poster ≠ grader.
- **Vendor pages do not prove NCAA D-I women's coverage, fields or rights.** No purchase is justified. The Genius/NCAA partnership is for sportsbooks.
- **Digs:** attempts − kills − errors is an accounting bound, not a save-success rate. Subtracting blocks separately double-counts blocked attacks (Grok is wrong).
- **Keep the experiment menu small:** baseline and evaluation contract first, then the dossier, then one candidate.
- **Another project's hardware, models or accounts** are not WVB resources (ChatGPT's report).

## 2. Findings only the Builder pass surfaced (checked in code)
These change what our own packet says. They are for the Reviewer to confirm.

1. **The 0.1718 held-out Brier was NOT measured on the live model, and its n is inflated.** `scripts/measure_forecast_calibration.py`:
   - It fits τ, τ_hit and the home constants on the WHOLE 2025 season, including the future matches it then scores. That leaks information forward.
   - It averages the margin and hitting channels as separate lists, where live averages the per-match 0.75/0.25 mix.
   - It scores opponents at preseason strength, where live re-scores them over 4 passes.
   - It re-scores every later match at each odd checkpoint (`future = matches[cut:]`), so `heldout_n` = 11,284 counts forecasts, not unique matches: 2025 has 5,131 matches.

   **Consequence:** CURRENT-MODEL §4 and START-HERE describe 0.1718 as the model's held-out accuracy. It is a partially leaky, partially different-model figure, and its uncertainty is overstated. It needs correcting in the packet. That is a documentation change, not done yet.
2. **Live k and the evidence behind the hitting weight don't match.** `blend_hiteff`, `blend_recv`, `blend_upgrades` and `forecast_blend_k` all ran at **k = 13.5**; live runs at **k = 10**. The Round-2 harness found hitting weight 0 vs 0.25 **indistinguishable** (Δ log loss −0.0001, CI [−0.0012, +0.0008]). So the hitting channel's case now rests on one harness at a different k.
3. **The "4 opponent passes converge well before 4" comment (`digby_top25.py:243`) has no measurement behind it.** A cheap read-only check (score change at pass 3→4 and 4→5) would settle it. Not run.
4. **Neutral sites:**
   - The **forecast already sets the home term to 0 at neutral venues** (`predict_2026.py:176`, venues from `venues.py`). Only the **rating** applies ±1 everywhere (`digby_top25.py`). Claude and Grok both claimed neutral sites are unhandled everywhere; that is half wrong.
   - 2025 holds **0 of 5,131** games with a venue, so the rating cannot be neutral-backtested on 2025 without new collection.
5. **Rally/point sequences for 2026 do not exist in our data.**
   - `games.jsonl` has per-set totals only.
   - `crawl_pbp.py` keeps raw play-by-play only with `--keep-raw` and otherwise stores starting lineups.
   - ncaa.com names servers only on aces, and the running score is null on most plays.

   So side-out/break-point work is **2025-only**, from ncaavolleyballr (MIT; server named on every rally), and `data/rotation_sideout_2025.json` already exists. Claude's "point sequences POWER already collects" and Grok's "2026 serving data may be recoverable" are both wrong for 2026.

## 3. Where Builder differs from, or adds to, the Reviewer
- **Reviewer priority 3** says "clean point sequences can support team serve/receive". True for **2025 only**; see point 5. The feasibility audit is already answered for 2026: there is no automated source, and live use would need a new authorized feed.
- **Reviewer, on ChatGPT's convergence claim:** calls it "a question, not a demonstrated bug". Agreed; the Builder adds that the code comment claiming convergence is itself unmeasured (point 3).
- **Volleymetrics exports:** the Reviewer cites Hudl documentation of DVW/XML exports, correcting Claude's "subscribers can't download". The Builder did not independently check this. Accept it as the Reviewer's verified finding. Entitlement and rights for Cody remain unknown.
- **Siri AI:** the Builder's pass found its use of the hitting channel as part of why the model predicts well contradicted by Round 2. The Reviewer did not raise this.
- **Gemini's temporal/auto-resolve proposal** would settle held finals by re-polling "without human oversight". That **violates our two-source rule and the corrections ledger**, not just idempotency (Reviewer point 5). Discard it.

## 4. Link and file access (Builder pass)
- **Tool failures, not disproofs:**
  - ResearchGate PlusLiga paper: HTTP 403, from Gemini's report.
  - Figshare record: HTTP 403, from ChatGPT's report.
- **Opened and consistent with what the report says:**
  - Powers et al. (2022 D-I women, 4,147 matches);
  - ncaavolleyballr issue #24 (2025 team-match file about half complete) and its data page (2020–2025);
  - arXiv 2503.08100 (F1 0.75, but only 14 players);
  - arXiv 2402.01083;
  - RallyIQ methodology;
  - healthchecks.io pricing;
  - the henrygd ncaa-api README;
  - the SportsStack page (NCAAF only, no volleyball).
- **Not attempted, blocked by policy:** masseyratings.com and other no-scrape hosts. Siri's four links were not attempted (unverified, not failed).
- **Shared-chat links:** the Builder did not try them. The Reviewer logged 4 failures.
- **Duplicates:**
  - ChatGPT's PDF = its `volleyball-research.txt`.
  - Claude's PDF = its `.md`.
  - Siri's PDF = its PNG.
  - Each `text.txt` is a share link or summary, not independent evidence.

## 5. Which follow-ups actually matter (recommendation; nothing sent)

| Chat | Send? | Why |
|---|---|---|
| **Claude** | **Yes, high** | Reliability, exposure and calibration ideas are the most usable. Needs its 2026 point-sequence premise and bibliography corrected, plus a concrete split-half reliability design. |
| **Grok** | **Yes** | RallyIQ is the one relevant outside NCAA model. Ask for dated sources for its backtest figures, and a corrected dig denominator. |
| **ChatGPT** | Yes, narrow | Ask for a field-level feasibility addendum, with the other-project contamination removed. Its convergence and baseline-at-several-cutoffs ideas are already captured. |
| **Gemini** | Optional | Mostly corrections: units, vendor coverage, auto-resolve. Only useful if it can supply a vendor evidence matrix with primary documents. |
| **Siri AI** | Low | Few sourced claims; the video-vision idea is long-range. |

**Merge:** each folder has both a REVIEWER and a BUILDER follow-up draft. Send ONE merged prompt per chat. Builder drafts add the code-verified corrections above (§2.4–2.5); Reviewer drafts carry the source corrections (bibliography, Hudl, RallyIQ page).

## 6. Proposed priorities (for the joint plan; not approved)
1. **Correct the evidence record first (documentation):**
   - relabel 0.1718 and `heldout_n` (§2.1);
   - note the k-mismatch (§2.2);
   - record that the forecast is already neutral-aware.
2. **Re-establish an honest baseline number.** Score the exact live model, one forecast per match, fitted on training data only, using the Round-2 rolling harness. That harness already passes leakage tests and matches production parity.
3. **Two cheap read-only diagnostics:** opponent-iteration convergence, and the 2-arm hitting floor at live k=10.
4. **Dossier specification from data we hold:** components, opportunities, roles, counts and uncertainty. 2025 side-out/break rates are descriptive history only.
5. **Only then pick one candidate** to shadow prospectively for the rest of 2026.
