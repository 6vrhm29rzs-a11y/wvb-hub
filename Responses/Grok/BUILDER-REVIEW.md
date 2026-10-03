# Builder review: Grok outside research (2026-09-26)

Independent Builder review. I read only the original submission files. The Reviewer's files were not opened. This is research only: no build is approved, and every item below that proposes work is a **proposal**.

**Files:** `POWER-OUTSIDE-RESEARCH-2026-09-26.md` is the full report (517 lines). `Response 1 text.txt` is not a duplicate. It is Grok's chat summary of that report plus a share link (grok.com/share/...). The two files make the same claims, so I reviewed them as one submission.

## Summary
- This is a careful, well-bounded report. It restates our packet mostly correctly: k=10 against the derived 13.52, the 0.100/0.0668 hitting floor, Round-2 C "not distinguishable", and Brier 0.172 vs 0.129 kept apart.
- Its strongest contribution is how it frames the evidence: a failed reception-error channel is not a failure of graded serve-receive. It also proposes a 2026 team-level serve/receive (break/sideout) shadow.
- Its main factual weakness: it treats 2026 serving-team recovery from ncaa.com play-by-play (PBP) as open, "may still be recoverable". We have a documented negative result on that feed (see Errors). The question can only reopen on new evidence.
- It misses that forecasts already set H=0 at neutral sites (`venues.py`). Only the rating's home term is venue-blind. Its T0 "freeze a live replica" is largely done already: Round 2 parity was 346/346 teams.
- Several product and literature numbers are asserted without verification: Pablo's formula, Evollve's figures, RallyIQ's backtest numbers and ridge size, and VolleyMetrics as the source of arXiv:2402.01083.

## Useful ideas (fit to our system)
1. **Frame receive-error failure as "thin tail, not full skill"** (§2.4). This matches `blend_recv_2025.json`. It is useful wording for DISCUSSION §C, and nothing needs to be built.
2. **Team break/sideout strength shadow (S-rally, §2.9.1 / T5).** On 2025 this is feasible from ncaavolleyballr PBP, which names a server on every rally (our rotations work). It could feed the existing `simulate_2025.match_dist`. On 2026 it is feasible only if a serving-team source exists. Proposal: a 2025-only research fit.
3. **Separate "interpretive honesty" from "forecast gain" for neutral sites (§7.1).** This is a fair point for C4. Our mechanism already exists: `predict_2026.py:176` uses `venues.py` site classification. A rating-side shadow could reuse that classification rather than a new "home arena" rule.
4. **Split-half reliability by match count** for the ten metrics (§2.9.2). This is cheap, uses existing boxes, and serves the analysis page (T6).
5. **Opportunity denominators table (§2.5).** It fits box fields already in DATA-INVENTORY (serve attempts, RA/RE, opponent TA).
6. **Champion-vs-field PPS at matched dates (T7).** This is the correct test before 18.7 is used as anything more than a description.
7. **Observation timestamps (C8).** This agrees with CURRENT-MODEL §6 on the leakage risk.
8. **DuckDB as a read-only lens over the JSONL files.** It is harmless and reversible. It is also low priority, because Python readers already exist.

## Errors and mismatches
1. **2026 serving team from ncaa.com PBP (§1.7, §3.4, T3).** Our own finding (`docs/rotations_finding.md`, `pbp_raw_2025` inventory row) is that ncaa.com PBP names servers only on aces. A service error prints bare. `homeScore`/`visitorScore` are null on most plays, so rally-by-rally serve possession could not be rebuilt. That was measured on 2025 ncaa.com payloads. A 20-match 2026 audit could only confirm it, not unlock a feed. Grok also treats RallyIQ's "public NCAA game data" as proof that ncaa.com carries serving-team data. The methodology page does not name ncaa.com. The source could be stats.ncaa.org, which we do not fetch.
2. **Neutral sites (§2.6, T2).** The report says "set H=0 when the venue is not either team's home arena" and "score 2026 forecasts". But the forecast mapping already applies H=0 on floors that `venues.py` calls neutral (`predict_2026.py:176,223`). What is missing is the rating term (`digby_top25`, nominal H). T2 has to target the rating, and its effect on forecasts only flows through the score.
3. **T0 is mostly done.** `RESEARCH-ROUND2-CHECKPOINT.md` §2 shows the replica within 1e-3 on 346/346 teams, and the packet reproduces the Kentucky, A&M and Stanford scores exactly. The report presents this as a prerequisite still to do.
4. **Misattribution to the NCAA manual (§2.5).** The claim that the "points column on some feeds is not a season total" is this project's measured finding (CLAUDE.md, 2026-08-11), not the Statisticians' Manual.
5. **arXiv:2402.01083 described as "VolleyMetrics-coded".** The abstract (fetched) says "charted data" from 2022 D-I, 4,147 matches, and does not name VolleyMetrics. This is unverified, not wrong.
6. **RallyIQ specifics.** The methodology page (fetched) states the source as "public NCAA game data". It confirms that a neutral-site correction was tested and dropped, and that AdjHit does not feed forecasts. It does **not** show the quoted 74.5%/0.465 and 77.6%/0.448 figures, "+0.7 pp", "0.027 logits" or "ridge ≈ 3 matches". Those may be on /ratings, which I did not fetch, so they are unverified.
7. **ncaavolleyballr "IP bans / slow".** The data page (fetched) confirms coverage of 2020 to 2025. It says nothing about bans or slowness, so that claim rests on the README, which I did not fetch. The conclusion that the package has no in-season 2026 data stands.
8. **The S-comp wording is garbled.** "Opponent kill % on our serve-receive error rate" is not a well-defined metric and needs a spec.
9. **Minor.** The packet's "live Brier 0.1796" is rounded to 0.180, which is fine. "Hitting 0 vs 0.25 indistinguishable in that harness" is correct, and it slightly undercuts the report's own emphasis on T1. The report acknowledges this implicitly.

## Evidence quality
- Packet numbers are cited accurately: 1,149 absence flags, 169/185 unreadable teams, 709/510/218/53 passing rows, VERIFIED_BOTH 1,113 (from the packet review).
- External claims are sourced by URL, but many specifics are asserted beyond what the pages show: the Pablo `25650×(p−0.5)` formula, Evollve's 51%/59%, Forman's odds ratios, the Berkeley note and the Substack correlations.
- Vendor pricing (Claude, Codex, Gemini, MotherDuck, Hudl) is irrelevant to model quality. The report itself flags the MotherDuck price disagreement.
- Duplicates: the summary file repeats the report, as noted above.

## Link/file access log
| Link | Status |
|---|---|
| collegevolleyball.app/methodology | opened (backtest numbers not on this page) |
| jeffreyrstevens.github.io/ncaavolleyballr/articles/data.html | opened |
| arxiv.org/abs/2402.01083 | opened |
| masseyratings.com/... | not attempted (blocked by policy) |
| grok.com/share/... | not attempted (share page, not a source) |
| All other cited URLs (VolleyDork, BTVB, DigNittany, RichKern, YouTube, ResearchGate, SSRN, Substack, AoC PDF, Berkeley, NCAA manual, GitHub repos, ESPN notes, Sportradar, Hudl, vendor pricing) | not attempted (time budget); unverified, not failed |

## Unresolved questions
- What is RallyIQ's actual 2026 source for serving team: ncaa.com PBP or stats.ncaa.org?
- Is the RallyIQ backtest published, and on what split?
- Who charted the arXiv 2022 data?
- Does 2026 ncaa.com PBP differ from 2025's in carrying score-per-play or server? This is only worth checking if the Reviewer considers it in bounds.

## Builder verdict (research only)
- **Adopt for research:** the thin-tail framing, S-rally as a 2025-only fit, the split-half reliability study, the matched-date PPS test, timestamps (C8), the opportunity denominators, and a rating-side neutral-site shadow that reuses `venues.py`.
- **Discard or correct:** T0 as new work, since it is done. T2 aimed at forecasts rather than the rating. T3 framed as an open unlock rather than confirming a known negative. The NCAA-manual misattribution. The vendor, pricing and agent matrix is out of scope for POWER.
- Nothing here justifies a live POWER change.
