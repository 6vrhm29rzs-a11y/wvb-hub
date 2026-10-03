# Builder review — ChatGPT submission "POWER: Critical Research Review" (2026-09-26)

Independent review. I did not open REVIEWER-REVIEW.md, REVIEWER-FOLLOWUP-DRAFT.md or any other reviewer file. This is research only: nothing here approves a build.

## Summary
- **Files.** `volleyball-research.txt` is the Markdown version of `POWER-OUTSIDE-RESEARCH-2026-09-26.pdf`. The content is the same (pdftotext gives about 10.0k words, the .txt about 9.6k, and the difference is layout and the table of contents). I treat them as one document. `text.txt` is a short chat summary of it.
- **Overall.** This is a careful submission that labels its own evidence (P/V/H/R/U), and most of its claims about our system hold up against our code. Every model-side claim I checked against code or receipts was correct.
- **Most valuable point.** It says the "11,284 held-out matches" figure counts repeated forecasts of the same matches, not unique matches. I verified this in the code (see Errors §A). It is a real weakness in how we describe our own evidence.
- **Main weakness: scope creep.** About 40% of the document (sections 4–5) covers AI product pricing and tooling: GPT-6/Claude/Gemini/Grok prices, Firecrawl, Tavily, n8n, MLX. That work is marginal to POWER, I could not verify it, and it goes stale quickly.
- **Genuinely new ideas.** A convergence receipt for the 4 opponent iterations, a 2025 PBP serving study, and treating reliability as a function of opportunity count instead of a match count.

## Useful ideas (proposals only)
1. **Convergence certificate for the opponent iterations (§2.6).** `scripts/digby_top25.py:243` sets `OPP_ITERATIONS = 4`, with the comment "converges well before 4". No receipt supports that comment. The loop at lines 468–469 starts from `zprior`, and each pass re-blends as `(1-w)·prior + w·zobs`. The contraction factor is therefore about max w = n/(n+10) (about 0.7 by late season), so 4 passes leave roughly 0.7⁴ ≈ 0.24 of the initial gap. A comparison against a converged solution on a frozen copy would be cheap. This fits our setup well.
2. **Exact-baseline / as-of audit (T1/T2).** A partial version already exists: RESEARCH-ROUND2-CHECKPOINT §2 shows parity of 346/346 within 1e-3 at one cutoff. Extending it to several cutoffs is the right next step.
3. **Our own finding that supports the submission's warning about baselines.** `scripts/measure_forecast_calibration.py:129-160` does not score the live model:
   - It uses opponents at their **preseason** z. The live model uses the 4-iteration current blend.
   - It mixes the hitting channel as `0.75·mean(margin) + 0.25·mean(hit)` over separate lists. The live model mixes per match.
   - It computes `home_adv` and τ over **all** matches, including future ones.

   So the published Brier of 0.1718 is for a sibling model, not the live POWER.
4. **2025 PBP serving / side-out study (§2.4, T3).** This fits our data: 2025 ncaavolleyballr PBP names the server on every rally, and `data/rotations_2025.json` exists. No 2026 source exists, and the submission says so correctly.
5. **Kill / error / continued-rally count model with lagged, past-only features (§2.3).** The data for this is already in the box-score counts.
6. **Source lineage split: origin → transport → transform (§3.1).** Two school pages can share one upstream scorer. This adds to our two-source rule without replacing it.
7. **Pass-grade distributions instead of means (§2.7).** This is correct and fits the limits of the VT capture (QUALITY.md: no game joins, GP undefined).

## Errors / mismatches
- **A. Not an error: "11,284 held-out matches" is correctly challenged.** The code at `measure_forecast_calibration.py:133-160` uses `future = matches[cut:]` for each checkpoint. The held-out checkpoints (0.06, 0.20, 0.50) therefore each re-score every later match, so a late-season match is counted up to three times. `heldout_n = len(P)` counts forecast pairs. The bootstrap unit and the wording "held-out matches" both need correcting.
- **B. Minor math.** The submission writes the iteration as `z_next = a + W P z`. The code applies the weights inside the opponent lookup, which is closer to `P((1-W)z_prior + W z)`. The bound (max w < 1) is the same, and the submission labels it H, so this is not consequential.
- **C. Mismatched to us.** It suggests testing venue recovery historically. We confirmed there is no venue field in `data/raw/2025/games.jsonl` (0 of 5,131 records). That means any historical subset needs new collection from school archives, which is a new acquisition rather than "existing data". The submission does say that no collection is authorized.
- **D. Overreach on external facts.** The Section 5 price table and the Grok/X/Firecrawl/Tavily figures are presented as "V — verified". I cannot confirm them: some named models are unfamiliar to me, and I did not fetch the pricing pages. They should not drive any decision without a dated recheck.
- **E. Double-counting warning (§2.3).** A blocked attack is also an attack error for the attacker, so the warning is correct for an additive ledger. It does not apply to our displayed PPS (K+B+A) or to margin, which comes from the scoreboard. Neither of those double-counts.
- **F. The hitting receipt uses k=13.5.** Verified: `blend_hiteff_2025.json` has k=13.5, as do `blend_upgrades` and `forecast_blend_k`. The submission is right that the hitting weight was never re-receipted at the live k=10.

## Evidence quality
- The claims about our system cite packet sections (P0), and every one I checked is accurate: the POWER formula, the 0.100 floor versus 0.0668, 0.1289 versus 0.1718, and the nominal home flag.
- External claims: three were checked and confirmed (arXiv S01, issue #24, Figshare), one was blocked by the site, and the rest were not attempted. Vendor pages are correctly treated as claims, not evidence.
- Duplication: the PDF and the .txt are the same text.

## Link / file access log
| Source | Result |
|---|---|
| S01 arxiv.org/abs/2402.01083 | **opened.** Confirmed: Powers/Stancil/Consiglio, 2 Feb 2024, 2022 D-I women, 4,147 matches, 600k+ points, 5M+ contacts. |
| S06 ncaavolleyballr issue #24 | **opened.** Confirmed: fatfryer, 12 Mar 2026, open, team-match CSV about half complete; other files look full. |
| S07 Figshare 30472025 | **failed (HTTP 403 tool error).** The "men's" claim is unverified by me, not refuted. |
| S02–S05, S08–S45 | not attempted (time-boxed). Unverified, not failed. |
| Blocklisted domains | none cited, so none needed. |

## Unresolved questions
- Whether the Figshare record really is men's volleyball (403 on fetch).
- Whether the 4 iterations have converged. This is measurable with no new data.
- The effective unique-match n and the correct bootstrap unit for 0.1718.
- The current pricing and product names in §5.

## Builder verdict (research only)
**Adopt for research:**
- the convergence certificate;
- honest re-labelling of the held-out n, plus a calibration receipt scored on the actual live model;
- the multi-cutoff baseline audit;
- the 2025 PBP serving study;
- the lagged count-model idea;
- the source-lineage fields;
- grade distributions for passing.

**Discard or defer:**
- the AI vendor and pricing matrix (§4–5) beyond a one-line "cap any cloud trial";
- Hudl, Sportradar and n8n;
- DuckDB, unless a real query pain shows up.

**No build approved.**
