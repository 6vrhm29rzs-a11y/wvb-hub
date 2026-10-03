# Consolidated follow-up — Grok

**READY FOR CODY TO SEND — not sent by either agent.**

Attach SHARED-RESEARCH-CORRECTIONS.md with this prompt. It supersedes conflicting facts in the original packet. This combines Reviewer and Builder questions into ONE follow-up; answer overlapping questions once. Prioritize material corrections and decisions, and keep unsupported specifics marked unknown.

We are reviewing outside research for Cody's NCAA Division I women's volleyball hub. This is a research-only addendum: do not build, install, purchase, subscribe, contact vendors, send messages, or change live rankings. We want a holistic volleyball analysis system that explains team/player performance, opportunities, positions, trends and uncertainty—not a collection of arbitrary weights. Descriptive usefulness and predictive usefulness are separate.

Use your original report plus the questions below. Correct errors explicitly; if you disagree with this review, show the evidence. Separate verified facts, hypotheses and unknowns. Cite direct primary URLs and the relevant section/date. Do not imply that a marketing page proves specific NCAA coverage. Keep the answer focused rather than repeating your whole report.

1. Recheck https://collegevolleyball.app/methodology . The current page describes a joint penalized binomial serve/receive model; its one-pass adjustment concerns hitting. Correct your comparison or provide the dated source for your stated algorithm, home-court constants, prior equivalent and validation results. Mark external performance as self-reported and avoid cross-dataset accuracy comparisons.
2. Rewrite the scale experiment: exact live baseline; separate population change from removal of the floor; recompute unfloored training scale within the chosen population. Do not hardcode 0.0668 after changing the sample. Separate fixed forecast calibration from later nested recalibration. An interval containing zero does not establish equivalence.
3. Correct the digs denominator. Blocked attacks already contribute to opponent attack errors, so subtracting both errors and stuff blocks duplicates exclusions. The NCAA TA-K-E bound is useful for accounting but conditions on outcomes and is not a clean save probability. Offer clearly named descriptive alternatives.
4. Distinguish aggregate serve/reception indicators from actual first-ball sideout and transition events. Specify the event schema and identify which proposed quantities are estimable now versus conditional on data we have not verified.
5. Design a stratified event-data audit, not a convenient 20-match sample promoted into national coverage. Include platform/conference/venue differences, missing rallies, first-rally servers, corrections, penalties, match joins and final-score reconciliation. Clarify that the ncaavolleyballr issue concerns a particular dataset, not all possible data.
6. Explain how a joint model uses opposing serve/receive outcomes without falsely doubling the independent sample. Distinguish team server-side performance from individual-server causal quality; cover rotations and sample uncertainty.
7. Narrow software options by actual job and incremental value. Do not dismiss SQLite because DuckDB is useful for analysis. Verify only the shortlisted services' current availability and prices; mark all other figures unverified.

Return a corrected outside-model comparison, data requirements, three prioritized research steps and one volleyball example that combines role/opportunity/context without invented coefficients.

## Additional questions from Builder's independent review
- The shared correction explains forecast-neutral handling and the documented source-specific rally limitation. Do not ask us to rediscover a feed limitation without new evidence; do not declare all possible 2026 sources impossible either. Identify RallyIQ's actual documented source, or mark it unknown.
- Provide dated evidence for the quoted RallyIQ figures: 74.5%/0.465 (2026), 77.6%/0.448 (2025), +0.7 percentage-point home edge, 0.027 logits and ridge equivalent of three matches. We did not locate these on the methodology page. Distinguish changed page from unsupported claim.
- Supply sources/locations for Pablo's 25650×(point%-0.5) formula and cap, Evollve's home-point/match rates, Forman's odds ratios, and any claimed ncaavolleyballr IP-ban warning. Correct or withdraw unsupported specifics without inventing estimates.
- Verify the asserted Volleymetrics origin of the contact-value paper; charted does not alone establish the vendor. Attribute our feed-specific points-column finding to the project, not automatically the NCAA manual.
- Specify any aggregate S-comp feature honestly; box-only data cannot establish first-ball outcomes merely by renaming a feature. Do not estimate the neutral-site change's effect size from an assumed tournament share alone.

## Requested response format
A short plain-English takeaway; a corrections/evidence table; answers to the consequential open questions; and at most three recommended next investigations with required data, validation and stop conditions. Keep supporting technical detail in an appendix. Ideas about tools/products are welcome when useful; no purchase or build is approved. Return a self-contained Markdown or text report with direct citations and an access-failures list.
