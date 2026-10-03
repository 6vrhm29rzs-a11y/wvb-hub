# Outside research review — five submissions

Prepared 2026-09-26. **All five reports reviewed. No implementation approved or performed.** Cody has not yet read the reports. The next step is Builder's independent review, followed by a consolidated decision about which outside chats need follow-up.

## Main conclusion
Build toward a richer volleyball explanation system while keeping changes to the forecast model evidence-driven. Team/player trends, opportunities, position, opponent quality, availability, and uncertainty should be visible even when they do not yet have a predictive weight. The reports provide useful ideas, but agreement among AI reports is not independent validation.

## Proposed order — for discussion, not a build queue
1. **Establish trustworthy comparisons.** Document the exact current method and information cutoff. Separate the scale floor, fitting population and forecast calibration. Preserve old predictions and correction history so future tests are genuinely prospective.
2. **Specify a useful team/player dossier using available data.** Show earned PPS, kills/attempt, hitting efficiency, serve pressure and errors, block/dig context, opponent performance, trends and sample sizes. Separate pins/middles and observed facts from hypotheses about setter quality, passing, injury or lineup changes. Stanford remains a user-suggested later case study, not a diagnosed conclusion.
3. **Audit event-level feasibility before selecting a new model.** Clean point sequences can support team serve/receive outcomes; first-ball, transition, player-server effects, pass grade and set location need richer verified observations. Then test one feasible candidate against the exact baseline.

No universal championship PPS threshold, arbitrary new metric weights, vendor purchase, video pipeline, or automatic model replacement is justified by this pass.

## Report disposition
| Submission | Useful contribution | Main follow-up |
|---|---|---|
| Chat GPT | Evidence timing, experiment separation, dossier and contact-value ideas | Remove other-project assumptions; field-level feasibility; narrow priorities. |
| Claude | Reliability, exposure and calibration audit questions | Correct bibliography/export claims; qualify inference and scale equivalence. |
| Gemini | Vendor and infrastructure leads | Correction-first revision: coverage, guarantees, units and study interpretation. |
| Grok | RallyIQ comparison and event-data direction | Correct competitor method, digs denominator and experiment design. |
| Siri AI | Video-analysis and feed leads | Separate demonstrated features from future features; small feasibility proposal. |

## Important corrections for the joint review
- Home-court constants at different modeling stages do not need to be numerically identical; inspect their roles before alleging a bug.
- Hitting scale approximately 0.0668 is a standard deviation, not variance. The 0.100 live minimum comes from a variance floor of 0.01. Recompute training scale after a population change; do not silently change several things in one comparison.
- A confidence interval spanning zero is inconclusive, not proof that models are equivalent. Weak standalone signals can still add conditional information. Conversely, richer-looking models do not automatically predict better.
- A clean rally winner is not a recorded pass, set, attack or player opportunity. Do not manufacture phase or causal labels from aggregate box scores.
- NCAA's zero-attack bound supports a digs accounting check, not a general save-success denominator. Subtracting blocks separately from attack errors can double-count exclusions.
- The existing passing capture has 709 parsed rows, not hundreds of independently validated matches. Poster identity is not necessarily grader identity. Match joins, observation scope and quality remain unresolved.
- Provider partnerships and generic product pages do not demonstrate accessible NCAA women's data with the required fields or rights. Export availability and actual customer entitlement are different questions.
- Temporal retries do not eliminate the need for idempotency and cannot repair persistently incorrect source data by themselves.
- Published aggregate fit and accuracy numbers are not directly comparable with our prospective match forecasts. Inspect target, chronology, unit of observation and split.
- Another project's Mac, models, accounts or services are not automatically available WVB resources.

## Files produced
Each of the five source folders now contains:
- REVIEWER-REVIEW.md — findings, corrections, useful ideas and access notes.
- REVIEWER-FOLLOWUP-DRAFT.md — tailored standalone follow-up, marked DRAFT / NOT SENT.

FILE-AND-LINK-ACCESS.md records the file inventory and tool access limits. All local reports were readable; four shared links did not open in the web tool. Key supporting sources are linked in the individual reviews. Not every citation or current price was verified.

## Builder handoff
Mail 027 asks Builder to independently read the originals first, save its own findings and follow-up drafts in each folder, then compare with these Reviewer files. Keep disagreements explicit and identify evidence that would resolve them. Research/documentation only; all live-change holds remain. Saving mail does not wake Builder or prove it has read it.

**Cody's next action:** Tell Builder: “Check mail 027. Do the independent five-response research review and save your findings and follow-up drafts. Research only—do not build yet.”
**Do not send the five outside follow-ups yet.** Combine both reviews first so each outside chat receives one useful request.
