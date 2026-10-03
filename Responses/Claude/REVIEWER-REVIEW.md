# Reviewer review — Claude

**Useful audit questions, but several factual and statistical corrections are needed before use.** Timestamp uncertainty, reliability, and serve/receive analysis are valuable. Some conclusions are stronger than the evidence supports.

## Required corrections
1. **Paper identities:** arXiv 1911.01815 is Egidi & Ntzoufras' unified model; 1911.04541 is Ntzoufras, Palaskas & Drikos on set differences; 1911.08791 is Gabrio's hierarchical model. Correct the bibliography and map each proposed method to its actual study population and target.
2. **Volleymetrics export access:** a blanket claim that subscribers cannot download data is incorrect. Hudl documents DVW/XML exports and discusses DVW add-ons. This does not establish Cody's entitlement, price, or redistribution rights. Distinguish a particular network restriction from the whole product.
3. **Home-court constants:** the performance adjustment and the separately calibrated forecast intercept estimate different quantities. Their numerical difference alone does not establish misspecification.
4. **Exposure:** five sets are not automatically 5/3 as many rallies as three sets; a deciding fifth set is shorter, deuce varies, and match length is outcome-dependent. Weighting must match the target, not merely match length.
5. **Scale/weight equivalence:** rescaling one signal and changing its mixing weight are not necessarily globally equivalent through a preseason prior, missing-box fallback, opponent iterations, and display normalization. Separate the population change from removal of the scale floor.
6. **Evaluation thresholds:** the proposed minimum detectable improvement and calibration bounds need explicit assumptions, practical effect size, dependence structure, and uncertainty. A non-significant result is inconclusive, not proof of equivalence. Features need not beat margin individually to add complementary information.
7. **Passing and event coverage:** one prolific poster does not establish one grader. Available 2026 point sequences, first servers, substitutions, penalties, corrections, and named-server coverage still require audit.

## Digs: retain the accounting check, change the interpretation
The NCAA manual states that digs cannot exceed the opponent's zero attacks: attempts minus kills minus errors. Thus that accounting bound is supported. But digs divided by zero attacks is not a clean defensive success probability: the denominator conditions on an attack not already becoming a kill or error. It does not identify all balls a defender could reasonably save. Do not discard the arithmetic check; label the ratio honestly.

## Sources checked
- https://arxiv.org/abs/1911.01815
- https://arxiv.org/abs/1911.04541
- https://arxiv.org/abs/1911.08791
- https://www.hudl.com/products/volleymetrics/transition/faq
- https://www.hudl.com/blog/the-essential-preseason-checklist-for-volleymetrics
- https://s3.amazonaws.com/fs.ncaa.org/Docs/stats/Stats_Manuals/Volleyball.pdf

## Access
Summary and full Markdown were read; PDF text was readable and compared. The PDF has source/domain labels but no usable clickable annotations found. The Claude shared-chat URL could not be opened by the web tool; the saved files supplied the report. Request direct claim-level links in the addendum.

**Follow-up priority:** corrections first, then a bounded evaluation and data-feasibility specification.

## Scope and status
Reviewed 2026-09-26. Research only. These are Reviewer findings, not approved implementation instructions. Original submissions were preserved. Source checks were selective, not an audit of every citation or every vendor/model price. Project facts below come from the existing research packet and handoffs; the live model was not rerun during this review. Builder should independently verify code-dependent claims.
