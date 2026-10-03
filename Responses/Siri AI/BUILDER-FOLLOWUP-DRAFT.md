# NOT SENT — draft for Cody/Reviewer consolidation

Context: thanks for the review. You don't have our files, so here is what matters. We rate NCAA Division I women's volleyball (348 teams). Our match data comes from ncaa.com's public JSON: box scores, per-set scores and live scores, reconciled against the official RPI table for all 348 teams. We do not scrape forums. Forum passing grades were copied by hand and are not joined to matches. Our rating blends opponent-adjusted points-per-set margin (75%) with hitting-efficiency differential (25%). In our testing, the 25% hitting weight vs 0% made no measurable difference (Δ log loss −0.0001, 95% CI [−0.0012, +0.0008]). A reception-only signal made prediction worse (AUC −0.027). Held-out 2025 Brier is 0.1718; 2026 live is 0.1796. We have rally-level serve data for 2025 from a public play-by-play dataset, but no automated rally source for 2026.

Please answer precisely, and mark anything you can't source as "unverified":

1. You describe the hitting efficiency signal as part of why the model predicts well. Given the null result above, do you still hold that view? If so, what evidence supports it?
2. For "box-score stats mostly describe past performance rather than predict," please cite studies or analyses, and say which stats they cover (digs, blocks, aces, reception errors).
3. Broadage and Data Sports Group: link each vendor's own documentation that states coverage of **NCAA Division I women's** volleyball, not FIVB/CEV. For each, state which fields are covered (point-by-point? named server?), latency, licensing terms that allow a personal website, and price. A marketing page with no NCAA mention does not count.
4. Please list the three sources hidden behind "github.com +3" in full.
5. volleyball_analytics: what action-detection accuracy has been reported on broadcast footage (not training clips), and on what dataset? What would running it on one full NCAA match realistically take in compute and setup time?
6. Where could full-match NCAA video be obtained in a way that permits automated analysis? If you don't know of a way, say so.
7. Besides video, is there any lawful, automatable source of 2026 NCAA rally-level data (server per rally, reception quality)? Name it and give its terms.
8. Given the null hitting result, what experiment would you propose instead of the hitting-floor check to improve forecasts? State the expected effect size and how it would be measured out of sample.
