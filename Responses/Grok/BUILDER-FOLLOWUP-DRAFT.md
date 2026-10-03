# NOT SENT — draft for Cody/Reviewer consolidation

Thanks for the research file. Some context first: you cannot see our repo, so here are the facts that bear on your report.

- Our forecast mapping **already** sets the home term to 0 on floors our venue classifier marks neutral. Only the **rating's** home term (nominal H = ±1) ignores venues.
- Our replica of the live model already matches production within 1e-3 on 346/346 teams.
- We measured ncaa.com play-by-play on 2025 payloads. It names the server **only on aces**, a service error prints with no name, and the running score fields are null on most plays. So we could not rebuild serve possession rally by rally from that feed.

Please answer the questions below briefly. Mark each answer as verified (with a URL and a quote), inference, or unknown.

1. **RallyIQ's source.** Which feed does collegevolleyball.app use for 2026 serving team and rally winner? Is it ncaa.com play-by-play, stats.ncaa.org, or something else? Quote the page. Given our ncaa.com finding above, do you still expect a 20-match audit (your T3) of ncaa.com play-by-play to succeed? Why?
2. **RallyIQ figures.** Give the exact URL and quote for each of these: 74.5% accuracy / 0.465 log loss (2026), 77.6% / 0.448 (2025), "+0.7 pp" home edge, "0.027 logits", and "ridge ≈ 3 matches". The methodology page we opened does not show them.
3. **arXiv:2402.01083.** Where does the paper say its data is VolleyMetrics-coded? The abstract says only "charted data".
4. **Pablo.** Give the source and a quote for `game score = 25650 × (point% − 0.5)` and the ~59% cap.
5. **Evollve and Forman.** Give a timestamp or page for "home teams win ~51% of points and ~59% of matches". Give the sample and the table behind the 1.54–1.64 home odds ratios.
6. **ncaavolleyballr.** Quote where the author warns about IP bans and slowness. The data article does not mention either.
7. **Your NCAA manual citation.** The claim that a "points column is not a season total" comes from our own measurement, not the Statisticians' Manual. Please confirm or correct the attribution.
8. **Neutral sites.** Given the correction above, restate T2 as a rating-only shadow. What effect size would you expect when H is dropped from roughly 10–20% of early-season matches (tournaments and showcases)?
9. **S-comp.** Define "an opponent-adjusted first-ball proxy built from boxes" precisely. Use box fields only: service attempts, aces, service errors, reception attempts, reception errors, kills, attack errors, total attacks.
10. **Stabilization literature.** Is there any published split-half or reliability curve for team or player serve-receive (or pass) metrics in volleyball at any level? Give citations only.

Keep the answer to evidence we can check. Do not include vendor pricing.
