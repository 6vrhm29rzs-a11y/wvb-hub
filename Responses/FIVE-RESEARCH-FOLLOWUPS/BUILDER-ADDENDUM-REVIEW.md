# Builder review: follow-up addenda (ChatGPT, Claude, Grok, Siri AI)
Builder, 2026-09-26, mail 029. This was a bounded review.
- **Method:** the originals were read first, via two focused passes (greps plus targeted reads, not every line). Claims were checked against our code, then compared with the Reviewer's `REVIEWER-ADDENDUM-REVIEW.md` files and `FOLLOWUP-DECISION-BRIEF.md`.
- **Gemini** errored and is absent; this is not blocking.
- **Duplicate tree:** `Responses/wvb power build/` mirrors this folder. It was not used, moved or deleted.
- **Research only.**

## ChatGPT (volleyball-research-addendum.md; .txt identical)
- **Answered:** yes.
  - A field-by-field feasibility table (box-score panels feasible now; complete on-court lineups need more data).
  - An exact-live / population-only / floor-only design, with each scale recomputed inside its own sample and no reuse of 0.0668.
  - A 2025 rerun called *development* evidence, not a holdout.
  - The k=13.5 vs 10 distinction.
- **Issues:**
  - The contrast between arms has **no sign convention**; it needs one before any run.
  - "Serving-order-slot context" presumes named servers, which we have only in 2025 ncaavolleyballr data. It is framed conditionally, so that's acceptable.
  - The proposed 05:45 daily issuance is a **new policy**, not what `prediction_log` does today (first-write-wins). Agree with the Reviewer.
- **Useful:**
  - one forecast per canonical match from a frozen issuance, with proof it preceded first serve ("a file label asserting pre-serve is not the receipt");
  - "unresolved is not impossible".

## Claude (Correction Addendum .md; the PDF is the same)
- **Answered:** all 7 questions.
  - Paper attributions corrected.
  - Hudl restriction re-scoped to the VM Network, with DVW exports a paid add-on and Cody's entitlement unknown.
  - Home terms explained as different stages.
  - The 5/3 exposure claim withdrawn (set 5 is to 15).
- **Wrong: the first-server inference.** It proposes anchoring the serving team on a named ace and propagating "forwards and backwards through a complete score sequence".
  - **The data premise fails on 2026 ncaa.com.** Scores are null on most plays, serves that stay in play emit no event, and service errors carry no name. So no complete sequence exists (measured 2026-08-22).
  - **The logic premise also fails even with complete rally winners:** the server at rally t > 1 is the winner of rally t−1, so rally 1's server is not recoverable from later anchors. This agrees with the Reviewer's counterexample.
  - Keep the first server **unknown** unless it is directly observed.
- **Other issues:**
  - The primary contrast is hitting weight 0.25 vs 0. That answers "is the channel useful", not the requested separation of floor and population.
  - No sign convention.
  - The "~2,000 matches / meaningful pick flips" SESOI example is unsourced. Pick flips are not the same thing as a probability-forecast gain (agree with the Reviewer).
  - Appendix A again calls 13.52 the live k (Reviewer). Live is 10.
- **Useful:**
  - TOST with a SESOI set in advance;
  - "underpowered, not no effect" as a stop rule;
  - complementarity through partial correlation or stacking;
  - split-half reliability with opponents estimated *without* the team's own halves, used to inform shrinkage, **not** to gate display;
  - flags for penalty and score-correction events, from rulebook citations.

## Grok (POWER-OUTSIDE-RESEARCH-ADDENDUM)
- **Answered:** mostly.
  - Population separated from the floor, with no pasting of 0.0668.
  - The digs denominator corrected to TA − K − E.
  - The neutral-home point corrected.
  - The ncaavolleyballr scope bounded.
  - Vendor attribution removed from arXiv 2402.01083.
  - SQLite vs DuckDB decided by job.
- **Wrong:**
  - **Sign:** "CI entirely above zero = candidate better" holds only if Δ = baseline − candidate, and Δ is never defined. The natural reading (candidate − baseline, lower loss better) would invert its verdicts.
  - **"If movement is inside noise, document the floor as a regularizer"** turns an inconclusive result into a claimed benefit. It also contradicts its own line 92. Correct reading: *inconclusive → leave live unchanged; regularization stays a hypothesis.*
  - The 349-team population figure is quoted from our packet, not re-verified.
- **Useful:**
  - the opponent-kill% family of descriptive measures;
  - "opponent earned PPS ≠ defence";
  - no-impossibility framing.

  On a low-reliability rate: the Builder prefers the Reviewer's position. Show the rate with its sample and interval rather than hiding it.

## Siri AI (IMG_7069–7077)
- **Answered:** at headline level only, with **no citations or URLs** despite being asked. It came back as screenshots again.
- **Unsourced thresholds, not adopted:** reliability > 0.85 (the statistic is not even named), accuracy < 70%, 2 minutes per rally, a 1–3 pass scale. The forum's own scale is 0–3.
- **Vendors:** makes no NCAA D-I coverage claim; "robust international coverage" is unevidenced.
- **The worked rally example** labels a hypothetical chain as fact.
- **Useful (backlog only):**
  - a small manual tagging pilot with pre-registered agreement (we choose the statistic);
  - measuring correction time rather than assuming it;
  - an occlusion stop rule;
  - separate licence audits for code, weights, data and video.

## Builder vs Reviewer
- **Agreement on every material point:** first server, sign conventions, "inconclusive ≠ beneficial", pick flips ≠ forecast gain, new-issuance policy, unsourced Siri thresholds.
- **Builder addition:** Claude's first-server path fails on **data availability** as well as logic, since ncaa.com has no complete 2026 score sequence.
- **Snapshot difference:** the Reviewer's live-record snapshot (2,101 scored, Brier 0.1799) is later than the packet's (2,088, 0.1796). Both are snapshot counts of an evolving file. The packet now dates its figure.
- **Next research round:** not needed. The remaining corrections are handled internally in `PROPOSED-NEXT-BUILD.md` (sign convention, A/B/C design, fail-closed scoring, split issuance streams).
