# B026 and outside follow-up review — decision brief
2026-09-26. Reviewer read B026, the three complete written addenda (ChatGPT, Claude, Grok), and all nine Siri screenshots. Gemini missing after error, accepted as non-blocking. No code/model/data/live changes, tests, installs, purchases, commits or emails.

## Proposed next phase, not yet a build authorization
1. Establish what prediction performance we can honestly claim and how future comparisons will be recorded.
2. Specify one team/player analysis page from existing verified boxes, starting with Stanford as Cody's question and Texas A&M 2025 as a historical example. Show workload, efficiency, errors, roles, opponent context and trends, with missing-data labels.
3. Design small isolated rating diagnostics against frozen data; subsequently select one justified candidate for prospective comparison. Do not change live POWER simply because it feels insufficient or because an AI proposes coefficients.

The explanatory page and forecast evaluation are separate workstreams: neither requires buying a new system. Passing, set-location, complete lineups and computer vision stay conditional later work. No additional external research round is necessary now. Builder still needs to independently review these responses and return a concrete plan for Cody's decision.

## File reconciliation
The two supplied follow-up trees are byte-identical for every corresponding non-.DS_Store file found at inspection; SHA-256 inventory saved in FOLLOWUP-REVIEW-MANIFEST.json. ChatGPT's nested .md and .txt are also identical. Originals/duplicate trees were not moved or deleted. Added per-chat REVIEWER-ADDENDUM-REVIEW.md only in Responses/FIVE-RESEARCH-FOLLOWUPS/. The copied POWER-RESEARCH-PACKET-REVIEWED.md inside wvb power build is an older input, not a newly corrected canonical packet. Avoid sending it as current without its corrections.

## B026 documentation: partially accepted, follow-up required
The major historical 0.1718 correction is present and accurately describes overlap and model differences. The updated canonical packet still contains contradictory guidance:
- CURRENT-MODEL §5 says the old receipt validated the model as shipped, despite its k mismatch.
- Its proposed diagnostic and DISCUSSION C1 still prescribe 0.0668 after restricting the population. Recompute raw scale in the chosen training sample, and distinguish exact-live, population-only and floor removal. Do not run that stale two-arm recipe.
- The 2026 claim “only genuinely out-of-sample record” is too categorical without timing/version ancestry verification. It is also a snapshot of an evolving deployed system, not necessarily today's one model.

## Narrow live-record audit performed
Read scripts/score_predictions.py and scripts/predict_2026.py; loaded existing predictions/results through read-only loader functions with bytecode writes disabled. Did NOT call a writer, rebuild scores or run a model.
- 2,103 final candidates with matching team names.
- 2,101 prediction timestamps earlier than the currently stored result start epoch.
- 2 later predictions, correctly excluded by current comparator.
- 68 team-name mismatches excluded.
- 0 missing/unparseable timing fields among the 2,103 matching candidates inspected.
Stored score artifact at inspection: 2,101 scored, Brier .1799, favourite wins 1,538 / 2,101 = 73.2%. These are an inspection snapshot, not new independently rescored metrics.

This supports the existing logging discipline; it does NOT prove actual first-serve timing, correct original fixture times, immutable pre-result provenance of every input, or single-version performance. The scorer skips its timing guard if either time is missing and catches parse errors by continuing to score; no such missing/malformed matching cases were found in this snapshot. It excludes strictly-later timestamps, not equality. These are code-path concerns, not proof of contaminated records.
The writer records first-ever forecast per game, not last-pre-match/daily 05:45. It does not include code/input hashes in the shown record schema. Prospective claims must identify that issuance policy, changing model ancestry, corrected schedule times and coverage. The artifact's 0.1289 reference is still misleading; its code/output remains untouched under the hold.
Suggested wording: “Recorded first-issued forecast performance, subject to timestamp, fixture and version-provenance checks; figures as of [snapshot].” Do not label the entire record invalid either.

## Remaining research corrections
See each REVIEWER-ADDENDUM-REVIEW.md. Most important: Claude's backwards serving inference does not identify the first server from any later ace; hypothetical rally winner sequence A,B gives second server A irrespective of first server. Grok's loss-delta sign and inconclusive=>regularizer conclusion need correction. Siri's thresholds/rubric are unvalidated. ChatGPT's exact-live replay must remain distinct from past-only historical validation. These can be handled internally without another set of prompts.

## Access and verification limits
All provided substantive responses were readable. Claude PDF not separately reparsed; Markdown is the review source. Nine Siri screenshots overlap; no hidden citations inferred. No share-link retries, account access or restricted-source acquisition. Selectively checked RallyIQ ratings/methodology and official NCAA rulebook; did not recheck all citations, pricing or rights claims. Original reports' source-access failures remain attributed to those reports, not presented as newly verified facts.
Sources: https://collegevolleyball.app/ratings ; https://collegevolleyball.app/methodology ; https://ncaaorg.s3.amazonaws.com/championships/sports/volleyball/rules/women/PRWVB_RulesBook.pdf .

## Next action
Mail 029 requests Builder's independent follow-up review, remaining documentation cleanup and a bounded implementation PROPOSAL with acceptance checks. All build holds remain. No need to chase Gemini or have Cody read the long reports. Mail is saved, not automatically delivered.
