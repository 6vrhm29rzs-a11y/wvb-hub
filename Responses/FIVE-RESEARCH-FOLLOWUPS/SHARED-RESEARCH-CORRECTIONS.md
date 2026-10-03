# Shared research correction — attach with each follow-up
2026-09-26. Supersedes conflicting claims in earlier packets. Research only; no implementation approved.

## Forecast benchmark
The historical 0.1718 (rounded 0.172) Brier score is a recorded result of an older calibration exercise, NOT a clean held-out estimate of today's live POWER model. Brier is a probability-error score, not a percent-correct accuracy score.
Reviewer inspected scripts/measure_forecast_calibration.py, especially its full-season variance/home calculations, checkpoint split, fit_rows, held_rows and probs paths:
- Home and signal-scale estimates use the full 2025 season before chronological checkpoints.
- Even checkpoints are used to fit the forecast slope and odd checkpoints to report results, but each checkpoint includes every later match. The SAME match outcomes can therefore occur in both slope fitting and reported evaluation. This is outcome overlap as well as dependence among forecasts.
- 11,284 counts checkpoint/forecast observations, not independent unique matches. The packet reports 5,131 matches in the underlying season. Exact unique scored-match and overlap counts have not been recomputed in this review.
- The older exercise uses preseason opponent strengths and separate margin/hitting averages. Current code uses per-match channel blending and iterative opponent updating.
Consequently the reported number remains a historical artifact, with neither a clean production-model generalization claim nor independent-match sample size. We have NOT calculated a replacement score. These defects do not quantify how much the number would change. Do not compare it directly to current 2026 performance or describe it as measured optimism of a known magnitude. The 0.1289 simulator-on-observed-margin result is a different estimand, not its replacement.

## Current implementation and experiment boundaries
- Current forecast code explicitly removes its direct home term for venues classified neutral (scripts/predict_2026.py). The rating evidence still uses nominal home/away flags (scripts/digby_top25.py). Different-stage home constants need not match numerically.
- Live prior blending uses k=10. Earlier hitting-weight evidence used k=13.5. An earlier small positive AUC result and the newer Round-2 inconclusive log-loss result are different experiments/units; neither proves the hitting channel useless nor validates every proposed scale change.
- The hitting-scale floor comparison itself has not been settled by switching a channel off. Separate fitting population, floor, weight and forecast recalibration. Approximately 0.0668 is an SD on its measured population; do not transplant it unchanged to a different sample.
- Code computes an initial opponent-adjusted result from the prior, then four update-loop passes. A comment claims convergence; no convergence diagnostic was run in this review. Four iterations alone do not prove convergence or meaningful error.
- Replica parity at one cutoff was reported (346/346 teams within 1e-3). That is useful implementation evidence, not all-cutoff parity, an untouched holdout, or proof of every upstream time boundary.

## Data availability: keep claims bounded
Builder reports no complete automated 2026 rally sequence dataset in the current project pipeline. Existing 2025 event data and derived sideout/rotation artifacts provide a possible historical research base; exact completeness and data rights still require their own checks. Missing 2026 data here is NOT proof that no suitable authorized source exists anywhere.
The project's docs/rotations_finding.md explicitly limits its negative ncaa.com finding and documents a browser-observed StatBroadcast serving sequence, with automation/access constraints. Serving order is not the complete six-player on-court lineup. Do not bypass restrictions or claim a 2025 source audit proves every 2026 feed is permanently unchanged.
Passing capture: 709 parsed rows, not 709 validated matches; 510 candidates are not matches either. Game joins, source/observation scope, grading method and quality remain unresolved. One poster is not necessarily one grader.

## Scope and user priorities
We want connected volleyball analysis: earned PPS, attack termination/efficiency, serve pressure, errors, blocking/floor defense, opponent strength, positions, opportunities, trends, availability and lineup context. Descriptive usefulness does not automatically confer a forecast weight; an inconclusive prediction experiment does not prohibit informative descriptive analysis.
No approved model replacement, implementation, purchase, new source collection or integration follows from this packet. Product/tool ideas remain welcome when they solve a specific problem and have evidence, cost, access and stop conditions. Do not import another project's hardware, accounts or credentials. Distinguish missing evidence from impossible capability.
