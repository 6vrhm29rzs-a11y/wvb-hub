# Reviewer review — Gemini

**Revision required before this can guide implementation.** There are useful leads, but the report repeatedly promotes possible capabilities into established coverage or guaranteed outcomes.

## Required corrections
1. **No demonstrated predictive ceiling.** Claims that ordinary box scores have reached an asymptote or that academic consensus requires phase data are unsupported. Richer events may help; that is a testable proposal.
2. **Scale units:** approximately 0.0668 is a standard deviation, not a variance. The corresponding variance is approximately 0.00447; the live minimum variance 0.01 produces a standard deviation of 0.100. Changing the fitting population and removing the floor in one arm confounds the result.
3. **Paid feed coverage is not established.** The NCAA/Genius announcement describes an expanded relationship and official data for licensed sportsbooks. It does not prove accessible, season-wide 2026 NCAA women's volleyball rally/server/rotation data for a personal website. SportsStack's unified schema cannot supply missing upstream rights or fields. Generic cost ranges are not quotes.
4. **Product distinctions matter.** Hudl club pricing is not necessarily collegiate Volleymetrics pricing. Soccer-oriented StatsBomb/Wyscout endpoints do not establish a volleyball API. No new vendor should be selected from this report alone.
5. **Temporal does not automatically make external work exactly-once.** Activities can execute again; application-level idempotency is required. Retries cannot guarantee resolution of persistently wrong results, held finals, or permission failures. A 403 is not permission to retry via alternative access routes.
6. **Passing capture already exists.** There are 709 parsed rows; 510 candidates are not 510 matches. The work is source reconciliation, match joining, scope validation, and grading-method uncertainty—not starting a parser from nothing. Adjusting a poster's mean may erase genuine team/sample differences unless overlap identifies grader bias.
7. **Headline study results are not directly comparable to our forecasts.** The cited R²=0.8497 concerns aggregate set-win-rate regression. A separate 93.65% classification result needs feature timing, split, target, and population scrutiny before being treated as pre-match evidence. Neither is interchangeable with Brier score or prospective NCAA performance.
8. **Avoid architectural invention.** A claim that the existing pipeline necessarily lacks auditability or needs wholesale Docker/workflow replacement is not established by the packet. MinerU is document extraction, not a volleyball contact-quality video model. Alleged motives for scraping restrictions are speculation.
9. **Volleyball interpretation:** high sideout and low break-point performance do not alone prove first-ball attack strength and weak defense. Opponent errors, serve pressure, rotations, and opportunities contribute.

## Primary checks
- https://www.geniussports.com/newsroom/ncaa-and-genius-sports-expand-partnership-through-2032/
- https://sportsstack.io/landing/providers/genius-sports
- https://docs.temporal.io/activity-definition
- https://www.nature.com/articles/s41598-025-26344-y
- https://www.hudl.com/products/volleymetrics/transition/faq

## Access
The saved PDF was fully extractable and read. Google Doc and Gemini share links failed in the web tool; saved PDF allowed review. The PMC study mirror presented a challenge page, but the publisher's full text opened. The 93.65% study was readable via an author-paper copy on ResearchGate; its reported accuracy was not reproduced.

**Follow-up priority:** a correction addendum and vendor evidence matrix, not a new infrastructure plan.

## Scope and status
Reviewed 2026-09-26. Research only. These are Reviewer findings, not approved implementation instructions. Original submissions were preserved. Source checks were selective, not an audit of every citation or every vendor/model price. Project facts below come from the existing research packet and handoffs; the live model was not rerun during this review. Builder should independently verify code-dependent claims.
