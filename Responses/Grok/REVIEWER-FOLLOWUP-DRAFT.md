# Follow-up prompt draft — Grok

**DRAFT — hold until Builder independently reviews. Not sent.**

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
