# NOT SENT — draft for Cody/Reviewer consolidation

Thank you for the POWER research review. You have no access to our files, so here are the facts that affect your conclusions:

- For 2026 we store only **per-set point totals** (linescores) and box scores. The box scores include serve attempts and aces and errors, reception attempts and errors, and attack counts.
- ncaa.com play-by-play leaves the running score null on most plays and names the server only on aces.
- We have no permitted automated rally source for 2026. The 2025 rally data (ncaavolleyballr) names the server on every rally.
- Our forecast already sets home = 0 at venues we classify as neutral. The rating's home term (1.0878 pts/set, raw home margin on 2025) does not.
- The 0.2675 is an intercept fitted together with slope 3.05 on blended rating scores, not a raw home margin.
- The hitting blend result was +0.00060 AUC, 95% CI [+0.00030, +0.00089], measured at k=13.5.

Please answer:

1. Your top new idea is side-out and break-point rates from "point sequences we already collect". Given that 2026 has no rally sequences, do you withdraw it for 2026? Is there any public, permitted source of 2026 NCAA rally-by-rally scores (not server names) you can cite with a URL?
2. Please restate the home-edge inconsistency with the correct facts above. Is comparing a raw home margin with a jointly fitted forecast intercept valid? What diagnostic would separate dilution by neutral matches from scale compression by the slope?
3. You compared a +0.0006 AUC effect with a 0.001–0.002 log-loss detection threshold. Please restate the power argument in one unit. Give the formula for the minimum detectable log-loss difference from a measured per-match SD, so we can plug in our own number.
4. You call the hitting result "null-ish", but its CI excludes zero. Do you mean the effect is too small to matter, or that it is unreliable? Please separate the two.
5. Please give the exact citation for the Laios et al. 2012 point-share figure (50.86%). Is there any NCAA-specific estimate of home edge in points per set, with a source?
6. For split-half reliability: what minimum n per half and what correction would you use? How would you handle opponent adjustment inside each half, given that raw half-season margins mix strength with schedule?
7. On k in sets versus matches: under w = n/(n+k), how should k be rederived? Should it be σ² per set over the prior's error variance? Please show the derivation.
8. ncaavolleyballr: please cite the specific page or issue stating that the data (not the code) carries NCAA terms. What is the source for the 2025 incompleteness (issue #24)?
9. Please name any published out-of-sample Brier or log-loss figure for an NCAA volleyball rating system, or confirm that none exists.

Please keep the DEMONSTRATED / INFERENCE / HYPOTHESIS / UNKNOWN labels, and give a URL for every new claim.
