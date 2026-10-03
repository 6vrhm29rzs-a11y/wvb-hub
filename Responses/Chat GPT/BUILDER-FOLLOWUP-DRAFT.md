# NOT SENT — draft for Cody/Reviewer consolidation

**Context.** You reviewed our POWER research packet for an NCAA D-I women's volleyball rating hub. You cannot see our files, so here is what we checked against the code.

- **Your challenge to "11,284 held-out matches" is correct.** Each held-out checkpoint re-scores every later match, so the count is forecast pairs, not unique matches.
- **The 0.1718 calibration was computed on a sibling of the live model, not the live model itself.** The sibling differs in three ways:
  - opponents are taken at their preseason rating;
  - margin and hitting are averaged separately;
  - the home and scale constants were fitted using all matches.
- **Your other packet-derived facts were accurate.**
- **2025 data has no venue fields.**
- **The live opponent update** starts from the prior and re-blends as (1−w)·prior + w·season each pass, with w = n/(n+10), for 4 passes.

Please answer briefly and concretely.

1. **Evaluation unit.** Given overlapping checkpoints, what bootstrap unit and effective-n do you recommend? Options include resampling unique matches with all their checkpoint forecasts, week blocks, or something else. Give a citation if one exists.
2. **Convergence.** Please restate your contraction bound for the exact update above, with the weights applied inside the opponent lookup. What tolerance counts as "negligible", measured in rank crossings and forecast-probability change?
3. **Figshare 30472025.** We got HTTP 403 on this record. Quote the exact description text that says it covers men's volleyball, and give the DOI and version.
4. **Section 5 prices.** Mark which figures you fetched live on 2026-09-26 and which you recalled from memory. For each model name (GPT-6 Luna/Sol, Claude Sonnet 5, Gemini 3.5 Flash-Lite, Grok 4.7), give the exact pricing-page wording.
5. **Serving study.** For 2025 rally data that names the server on every rally, but where the on-court six is not known (liberos replace middles in the back row), specify:
   - the minimum model for rally-win % on each player's serve;
   - how to handle serving-order versus on-court differences;
   - one published NCAA or FIVB reference for serve-reliability estimates by attempt count.
6. **Count model.** Give the exact likelihood you would use for kill/error/continued rally, with opponent effects. Name one peer-reviewed or preprint source that validates it forward in time, as opposed to in-sample.
7. **Set-aware likelihood.** Does Egidi & Ntzoufras (S02) report out-of-sample match-level Brier or log loss? If so, quote the value. If not, say so.
8. **Powers et al. (S01).** Is their charted 2022 corpus available to outside researchers, and under what terms? Please quote the wording, not an inference.
9. **Priority.** Drop the tooling section. Out of convergence audit, calibration re-receipt, serving study and count model, which one would you run first, and why? Answer in three sentences or fewer.

Label every claim as fetched-today (with URL), recalled, or inference.
