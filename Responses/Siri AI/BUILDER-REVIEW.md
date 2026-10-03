# Builder review — Siri AI, Response 1

Independent review by the Builder. I read only the original submission files; the reviewer files were not opened.

## Summary
- **Duplicates:** `Response 1.pdf` and `Volleyball Analytics Research response 1.png` are the same phone screenshot of one response. `Response 1 chart cut off .txt` is a transcript of its section 4 table, which is cut off on the right in the image. I treat them as one submission.
- It is short and mostly generic. The model numbers it repeats (Brier 0.172, hitting floor 0.100 vs a raw value of 0.0668, k=10) match what we gave it. It adds no new measurements.
- Its three trials are either already done (the hitting-scale check), not feasible for us (video computer vision), or aimed at vendors that don't cover NCAA D-I women's volleyball as far as anything shown.
- It cites four sources, all vendor or repo landing pages. None of them backs a claim about NCAA coverage.

## Useful ideas (proposals only)
1. **Hitting-scale floor diagnostic (trial 1).** The question is fair, but it is already mostly answered. `RESEARCH-ROUND2-CHECKPOINT.md:9,104` shows that hitting weight 0 vs 0.25 makes no measurable difference: Δ log loss −0.0001 [−0.0012, +0.0008]. Comparing the floor with the raw value is a smaller effect than switching the whole channel off. Expect an inconclusive result, which makes this low priority.
2. **Descriptive vs predictive (section 6).** This is a legitimate framing, and our own receipts agree with it: `data/blend_recv_2025.json` gives reception-only HURTS (Δ −0.027 AUC) and mix25 inconclusive. Worth keeping as a principle: team-page context is not a rating input.
3. **Video/CV (volleyball_analytics).** This could only matter as a long-range research note. It needs match video we don't hold and can't legally bulk-collect, and it needs GPU work. It does not fit the current pipeline.

## Errors / mismatches
- **"25% hitting efficiency signal" presented as a driver of predictive success.** Our measurement says the 25% hitting weight is indistinguishable from 0 on 2025 (checkpoint line 9). The original 2025 hiteff receipt showed only a tiny AUC gain. The response overstates its role.
- **"Box-score stats mostly explain past performance… already captured in point margin"** is asserted with no evidence. For reception, our receipts partly support it. For the other stats it is untested, so this is not established fact.
- **"Structured APIs … replace fragile web-scraping … reliable access to real-time box scores, play-by-play"** is mismatched to us. Our core feed (ncaa-api / ncaa.com) is not a scrape of a restricted site. It is reconciled 348/348 and already has live box scores. The response names no vendor that is documented to cover NCAA D-I women. Data Sports Group is described, by the response itself, as FIVB/CEV. A vendor landing page does not prove NCAA coverage.
- **"Unverified forum scraping" framing.** We don't scrape the forum. VolleyTalk data is a manual browser capture (`Cody/data/vt_passing_2026/QUALITY.md`). That dataset's real limits are 709 rows, none joined to games, a 0–3 scale stated only by the forum, and an undefined GP. The response doesn't engage with any of them.
- **Brier 0.172** is our held-out 2025 figure. The response doesn't mention the 2026 live figure (0.1796), so it presents the backtest as current performance.
- It never mentions the 2025 play-by-play (ncaavolleyballr, MIT), which already gives rally-level serve data for 2025. It proposes video to get rally data we already partly have.

## Evidence quality
It is asserted throughout, with no numbers of its own. The sources are four landing pages plus "github.com +3" (the three extra links are not visible). There are no NCAA coverage statements and no prices beyond Julius ~$20/mo (not verified).

## Link/file access log
- Local files: all three opened and read (PDF and PNG as images; the text shown is a screenshot).
- github.com/masouduut94/volleyball_analytics: not attempted (review done read-only without web fetch). Status unverified, not a failure.
- broadage.com/sports-data-api/volleyball: not attempted. Unverified.
- datasportsgroup.com/coverage/volleyball/: not attempted. Unverified.
- julius.ai: not attempted. Unverified.
- The "+3" hidden links can't be recovered from the screenshot.

## Unresolved questions
- Does Broadage or DSG actually carry NCAA D-I women's volleyball, and with what licensing, latency and cost?
- What accuracy does volleyball_analytics reach on NCAA broadcast video, and where would video come from legally?
- What is the evidence for "box-score components are descriptive only", and for which stats?

## Builder verdict
- **Keep for research:** descriptive vs predictive as a design principle. Also keep vendor coverage as an open question, and only if a vendor documents NCAA D-I women coverage.
- **Discard / deprioritise:** the hitting-floor trial (already effectively answered), the video CV pipeline (no data source, out of scope), Julius AI (not relevant), and the "replace scraping" premise (it doesn't match our pipeline).
- Nothing here is approved to build.
