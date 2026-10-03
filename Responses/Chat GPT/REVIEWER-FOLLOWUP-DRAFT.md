# Follow-up prompt draft — Chat GPT

**DRAFT — hold until Builder independently reviews. Not sent.**

We are reviewing outside research for Cody's NCAA Division I women's volleyball hub. This is a research-only addendum: do not build, install, purchase, subscribe, contact vendors, send messages, or change live rankings. We want a holistic volleyball analysis system that explains team/player performance, opportunities, positions, trends and uncertainty—not a collection of arbitrary weights. Descriptive usefulness and predictive usefulness are separate.

Use your original report plus the questions below. Correct errors explicitly; if you disagree with this review, show the evidence. Separate verified facts, hypotheses and unknowns. Cite direct primary URLs and the relevant section/date. Do not imply that a marketing page proves specific NCAA coverage. Keep the answer focused rather than repeating your whole report.

1. Remove assumptions imported from Raven or another device/project. Treat WVB hardware, existing local models, credentials and integrations as unknown unless our WVB packet establishes them.
2. Give a field-by-field feasibility table: box scores; clean point winners/serving team; named servers; rotations/lineups; individual contacts and pass/set quality. For each, list what we can measure, what we cannot infer, required fields, missing-data policy and evidence of actual coverage. In particular, separate sideout from first-ball sideout and transition efficiency.
3. Specify the smallest defensible model experiment. Exact live baseline first; change calibration population separately from removing the hitting-scale floor. Recompute scale within each training population. Keep forecast calibration fixed for the initial diagnostic; describe any later nested recalibration separately. Account for the earlier weight receipt using k=13.5 versus live k=10. Explain why reusing historically tuned data is not a fresh holdout.
4. Your four-pass convergence idea is interesting. State the assumptions needed for the contraction argument and the exact code facts Builder must verify. Cover initialization, opponent priors, restandardization, missing boxes and disconnected schedules. Propose a frozen-input comparison without claiming a production bug exists.
5. Choose only three next investigations, ordered by information gained and cost. Include a team/player dossier that helps Cody understand performance before any model replacement. Show one volleyball example linking passing, middle availability, pin burden and attack outcomes while labeling the unobserved parts.
6. Narrow the technology list to at most three conditional options. Explain the task each solves, what current tools cannot do, a measurable pilot, ongoing cost, permission requirements and a stop condition. Do not presume access to personal systems.

Return: short corrections; feasible-now/needs-data table; three priorities; exact unanswered questions for Builder. Proposed experiments are not authorization to run them.
