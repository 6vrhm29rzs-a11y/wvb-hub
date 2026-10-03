# Builder review: Gemini, "Volleyball Analytics and Tech Research"
Builder (Claude Code), 2026-09-26. Independent review. I did not open the Reviewer's files. Research and documentation only. Nothing here approves a build.

## Summary
- `text.txt` holds only two links: a Google Doc and a Gemini share. The real submission is the PDF, about 4,300 words. I read it in full.
- Gemini restates our model mostly correctly. The Brier scores, favourite %, home constant, τ²=5.941, the 0.25 hit weight and the 0.100 floor all match. Bradley–Terry losing also matches. **But it calls 0.0668 a "variance". It is the hit-scale SD (τ_hit).**
- The one idea that fits our data is Side-out %/Break-point % from the 2025 rally-by-rally feed (ncaavolleyballr).
- Several claims about our pipeline are wrong: Cloudflare on VolleyTalk, "no parsing capability", our scraping of stats.ncaa.org, and cron fragility needing Temporal. Hypothesis 5 would break our two-source correction rule.
- Recommendation 5 (San Diego / UCSD) repeats a premise nobody gave. It is the same fabricated premise already flagged in an earlier Gemini doc. Discard it.

## Useful ideas (proposals only)
1. **SO% / BP% from 2025 play-by-play (Rec 2).** This is feasible. The 2025 ncaavolleyballr file names the server on every rally (`scripts/rotations.py`, `build_rotations.py`), so serving and receiving rallies can be separated. It is research-only. There is no 2026 rally source (ncaa.com names servers only on aces, and StatBroadcast is not automated), so it cannot feed live POWER. Test it as an explanatory metric first, with a pre-registered comparison, not "for Texas A&M".
2. **Hit-scale floor question (Hypothesis 1 and Unresolved).** Gemini states the direction correctly: dropping the floor to 0.0668 raises the hit channel's weight by 0.100/0.0668 ≈ 1.5×. The "implicit regularizer" reading is a hypothesis, not evidence. The receipt `data/blend_hiteff_2025.json` measured the channel with the floor in place. Only the paired two-arm check can decide it.
3. **Neutral-site definition (Unresolved).** This is a fair question. We fit a nominal home flag and have no neutral handling. We do have a venue feed plus fixture-ledger venue corrections (e.g. Fiserv, Wrigley), which is a better start than buying a vendor feed.
4. **Grader bias in forum passing grades (Hypothesis 3).** This agrees with `Cody/data/vt_passing_2026/QUALITY.md`: 59 posts are self-graded, 25 rows carry a disagreeing duplicate grader, and GP is undefined.
5. **Genius Sports / LiveStats as the official data owner.** This is useful context for any licensing question. It is not evidence of what a reseller tier actually delivers.

## Errors
| # | Claim | Evidence |
|---|---|---|
| E1 | "measured **variance** of team hitting efficiency 0.0668" (also in Hypothesis 1 and Unresolved) | `digby_top25.hit_scale_2025()` returns `tau2h ** 0.5`, which is an SD. It is not the variance. |
| E2 | "Our pipeline relies heavily on scraping… stats.ncaa.org JS pages… IP bans" | We never fetch stats.ncaa.org. It is blocked by our own no-scrape hook. The pipeline reads the ncaa-api mirror of ncaa.com, which works from a datacenter IP. The JS change and "IP bans" on ncaavolleyballr are asserted with no citation. |
| E3 | VolleyTalk is behind "Cloudflare bot protection" | What we observed is a proboards proof-of-work challenge, and we deliberately do not bypass it (CLAUDE.md, 2026-08-28). |
| E4 | Passing data is "quarantined due to lack of programmatic parsing"; the fix is OCR of PDFs/screenshots | It is already parsed: 709 rows from saved posts. The blockers are source quality, the missing game join, the undefined GP and grader disagreement. OCR fixes none of those. The "Wisconsin–Louisville single-page PDF" does not match our capture as I know it. It is unverified. |
| E5 | Rec 4 check: "multiply attempts by grade" to reconcile the team average | This is circular. It only checks the poster's own arithmetic, not whether the grades are accurate. |
| E6 | Hypothesis 5: Temporal auto-requeries the feed and "completely automates the manual review queue without human oversight" | Held finals resolve through school-site evidence and the corrections ledger, under our two-source rule, not by re-polling the feed. Finals often never self-correct (e.g. all-zero scaffolds). Automating adjudication would violate policy. |
| E7 | Rec 3: cron scripts "frequently crash" and need Temporal for idempotence | This is asserted. `crawl_2025.py` is already resumable with atomic checkpoints, the logs are append-only with final-beats-non-final dedup, and runs have timeouts. Retry-on-403 would also mean retrying blocked sources. |
| E8 | Rec 1 cost of "$500–$2,500+/month" and "rally-level NCAA volleyball data" via SportsStack | The cost is uncited. The SportsStack page I opened lists NCAAF but does not mention volleyball. A vendor page is not proof of coverage. |
| E9 | Rec 1 trial: "calculate the exact home-court advantage (h = 1.0878) for true home matches" | This is confused. 1.0878 is the current fitted value, and re-fitting on true home games would change it. |
| E10 | Rec 5, San Diego / UCSD | This premise is not in the brief. A computer-vision project on broadcast footage also raises rights questions. |
| E11 | "Box stats have reached a predictive asymptote" | This overstates it. Round 2's channel C (4 box channels) came out inconclusive (CI spans 0), not harmful. It is not proof of an asymptote. |

## Evidence quality
- 40 works cited, and most are vendor, blog, marketing or YouTube pages. The key pipeline claims about us (IP bans, crash frequency, costs) are uncited.
- The academic numbers are cited but come from different populations: PlusLiga men's pro, world championship women, and 14 players on wearables. None transfer to NCAA D-I match prediction as stated. The arXiv 2503.08100 figure (F1 0.75, LOSO) checks out, but n=14.
- Duplicates: `text.txt` is not a copy of the PDF, only two links. Citations 2/3, 6/7, 14/16, 31/32 each cite the same work twice.

## Link / file access log
| Link | Result |
|---|---|
| docs.google.com/document/1hUP… (text.txt) | not attempted (private Drive doc; the PDF is presumably its export) |
| share.gemini.google/MGJK… | not attempted |
| researchgate.net/…408030527 (PlusLiga 93.6%) | failed (tool error, HTTP 403), so this claim is **unverified** |
| sportsstack.io/…/genius-sports | opened: NCAAF listed, no volleyball, no price shown |
| arxiv.org/abs/2503.08100 | opened: claim confirmed (n=14 players) |
| All other cited links (~35) | not attempted (scope) |
| No links cited on blocked domains | none on blocklist; stats.ncaa.org is discussed but not linked |

## Unresolved questions
- Does any Genius/SportsStack tier actually carry D-I women's volleyball rally data with named servers, and at what price and licence?
- Is the PlusLiga 93.6% figure real, and was it pre-match or with in-match features (OPI/break-point differentials are outcomes, so possible leakage)?
- Does SO%/BP% add anything beyond margin/set, which already sums both phases?

## Builder verdict
- **Adopt for research:** the SO%/BP% study on 2025 PBP; the hit-floor two-arm check (it is already proposed, awaiting approval); a written neutral-site definition.
- **Discard:** Temporal (Rec 3 / H5), VLM/OCR ingestion (Rec 4, which solves the wrong problem), Rec 5, and "migrate to SportsStack" until coverage is proven.
- **Hold:** any paid-feed question until E8 is answered with primary evidence.
