# Consolidated follow-up — Chat GPT

**READY FOR CODY TO SEND — not sent by either agent.**

Attach SHARED-RESEARCH-CORRECTIONS.md with this prompt. It supersedes conflicting facts in the original packet. This combines Reviewer and Builder questions into ONE follow-up; answer overlapping questions once. Prioritize material corrections and decisions, and keep unsupported specifics marked unknown.

We are reviewing outside research for Cody's NCAA Division I women's volleyball hub. This is a research-only addendum: do not build, install, purchase, subscribe, contact vendors, send messages, or change live rankings. We want a holistic volleyball analysis system that explains team/player performance, opportunities, positions, trends and uncertainty—not a collection of arbitrary weights. Descriptive usefulness and predictive usefulness are separate.

Use your original report plus the questions below. Correct errors explicitly; if you disagree with this review, show the evidence. Separate verified facts, hypotheses and unknowns. Cite direct primary URLs and the relevant section/date. Do not imply that a marketing page proves specific NCAA coverage. Keep the answer focused rather than repeating your whole report.

1. Remove assumptions imported from Raven or another device/project. Treat WVB hardware, existing local models, credentials and integrations as unknown unless our WVB packet establishes them.
2. Give a field-by-field feasibility table: box scores; clean point winners/serving team; named servers; rotations/lineups; individual contacts and pass/set quality. For each, list what we can measure, what we cannot infer, required fields, missing-data policy and evidence of actual coverage. In particular, separate sideout from first-ball sideout and transition efficiency.
3. Specify the smallest defensible model experiment. Exact live baseline first; change calibration population separately from removing the hitting-scale floor. Recompute scale within each training population. Keep forecast calibration fixed for the initial diagnostic; describe any later nested recalibration separately. Account for the earlier weight receipt using k=13.5 versus live k=10. Explain why reusing historically tuned data is not a fresh holdout.
4. Your four-pass convergence idea is interesting. State the assumptions needed for the contraction argument and the exact code facts Builder must verify. Cover initialization, opponent priors, restandardization, missing boxes and disconnected schedules. Propose a frozen-input comparison without claiming a production bug exists.
5. Choose only three next investigations, ordered by information gained and cost. Include a team/player dossier that helps Cody understand performance before any model replacement. Show one volleyball example linking passing, middle availability, pin burden and attack outcomes while labeling the unobserved parts.
6. Narrow the technology list to at most three conditional options. Explain the task each solves, what current tools cannot do, a measurable pilot, ongoing cost, permission requirements and a stop condition. Do not presume access to personal systems.

Return: short corrections; feasible-now/needs-data table; three priorities; exact unanswered questions for Builder. Proposed experiments are not authorization to run them.

## Additional questions from Builder's independent review
- With outcome overlap between slope fitting and reported checkpoints, design a genuinely chronological evaluation before choosing a bootstrap. Explain unique-match versus repeated-horizon estimands and dependence; do not invent an effective sample size.
- The update first uses preseason opponents, then makes four further passes. Restate convergence conditions for weights inside opponent lookup and define practical tolerances in forecast probability as well as ratings. Rank crossings alone depend on ties.
- For Figshare record 30472025, provide DOI/version, population and access conditions; Builder received 403. For Powers et al., establish who charted the data and whether it is available to outside researchers. For the set-aware study, distinguish reported match-level out-of-sample Brier/log loss from other fit statistics.
- For the 2025 named-server study, distinguish serving-order slot from all six on court and from causal server ability. Specify the minimum hierarchical adjustment, uncertainty by opportunities, and remaining confounding.
- Briefly identify any unsupported prior tool/pricing claims. Keep only tools with a concrete role; Cody explicitly requested useful external-system ideas, so do not discard the topic wholesale.

## Requested response format
A short plain-English takeaway; a corrections/evidence table; answers to the consequential open questions; and at most three recommended next investigations with required data, validation and stop conditions. Keep supporting technical detail in an appendix. Ideas about tools/products are welcome when useful; no purchase or build is approved. Return a self-contained Markdown or text report with direct citations and an access-failures list.
