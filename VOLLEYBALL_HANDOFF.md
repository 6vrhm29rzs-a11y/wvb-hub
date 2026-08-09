# NCAA Women's Volleyball Ratings Tool — Handoff

**For:** a fresh Claude session. **Owner:** Cody. Personal use.
**Last worked:** Sat Aug 8 2026 (evening), paused by owner ("save for tonight").

---

## 1. What this is

An interactive HTML dashboard for NCAA D-I **women's indoor** volleyball: a **ranking system (Cody's own model)**, a **post-season bracket**, and a **data tracker** — inspired by masseyratings.com and figstats RPI. Built as a published Artifact.

**Live artifact (republish the SAME file path to keep this URL):**
`https://claude.ai/code/artifact/1198d9b4-ca3f-414c-8b7a-f9e3bc1b5fd8`

---

## 2. Cody's rating model — REVERSE-ENGINEERED & VERIFIED (do not re-derive)

From his sheet, reproduced to the decimal (rank order exact, Z error <0.01, **population** stdev):

- **PPS** (points/set) = Kills/set + Aces/set + Blocks/set  *(offense only)*
- **Z_Points** = zscore(PPS) over the pool
- **Z_SOS** = (mean_rank − SOS_rank) / sd(rank)   — tougher schedule (lower rank #) → higher
- **Adj Score = Z_Points + 2 × Z_SOS**  → rank descending. The **2× on SOS is his signature choice.**
- He also tracks **SSF** = SOS including future games (Adj uses played-only SOS).

Verify/regenerate: `scripts/parse_cody_model.py` (prints the reproduction check AND emits `data/vb_model.json`).

His two source sheets are **complementary, not duplicates**:
- Sheet 1 `1O5RmMmFDdNd7OYwBDBAqYPtHiwCWZKjh5gUftXU7Unc` = **rating engine** (K/A/B/PPS, Z, Adj, SOS, SSF), 40 teams, **thru Oct 22**.
- Sheet 2 `1SHyfF2i80h2-PaJEiG0DIOfwIIaABI6avGAn1AwP0rc` = **résumé/RPI side** (weekly W12–14 breakdowns, records, streaks, **avg-opponent-RPI SOS**, non-conf SOS). **No Adj math in it.** 600KB export → parsed by subagent to `data/vb_cody_workbook.json`.

---

## 3. Pipeline & files (all in this bundle)

```
data/vb_model.json      ← Cody's Adj inputs (40 teams, sheet 1, thru Oct 22). Emitted by parse_cody_model.py.
data/vb2025.json        ← bracket + tournament results + official_sources (from research). Feeds Bracket & Tracker.
data/vb_cody_workbook.json ← résumé-workbook extract (records + oppRPI). Merged in at build time.
output/vb_template.html ← THE SOURCE. Has __DATA__ and __MODEL__ injection tokens. Edit here.
scripts/build_vb.py     ← reads the 3 JSONs, merges workbook record+oppRPI onto model teams (28/40 match,
                          alias Pittsburgh→Pitt), injects → output/vb_dashboard.html
output/vb_dashboard.html← generated, self-contained. THIS is what gets published as the Artifact.
```

**Build & publish:** `python3 scripts/build_vb.py` then publish `output/vb_dashboard.html` via the Artifact tool **with the same file_path** (keeps the URL). All rating math (Z, Adj, SOS dial, returning %) lives in the template's JS; build only injects data.

**Verify after any change:** extract `<script>` and `node --check` it; there's no browser to self-screenshot (see §6).

---

## 4. What the tool currently contains

- **Rankings tab = Cody's Adj Score model.** Columns: #, Team(+conf), **Rec**, Adj Score (bar), Pts/Set (bar), K/s, A/s, B/s, SOS (model rank heatmap, drives Adj), **Opp RPI** (his résumé SOS). Sortable. **SOS-weight dial (1×–3×, default 2×)** recomputes Adj live. Stat tiles: Top Rated, Best Offense, Toughest Slate, **Schedule Lift** (e.g. Penn State +19). Tracks correct **2025-26 conferences** (Texas=SEC, Stanford=ACC, etc.) — NOT the workbook's stale ones.
- **Post-Season tab** = real 2025 bracket built from results: Regional Finals → Final Four → Final. **Texas A&M def. Kentucky 3–0.** Plus top-16 seed grid (advancers bold).
- **Data Tracker tab** = 2025 postseason results feed + a team card showing the Adj math (per-set production → Z(pts), Z(SOS) → Adj).
- **Season toggle → 2026** = **Returning Production** board (Rankings tab): real 2025 Pts/Set, **Returning %** (currently ILLUSTRATIVE, badged), Proj 2026 Pts/Set, Outlook pill (Veteran core ≥80 / Reload 60–80 / Rebuild <60). Bracket/Tracker show 2026 "not set" states.
- Footer cites official NCAA source URLs.

**Design:** "broadcast analytics console." Accent orange (attack line), court teal, arena-navy neutrals. Both light/dark themes (token-level). System fonts (CSP blocks CDNs). Validated palette per dataviz skill.

---

## 5. Data provenance (Cody requires historical data from OFFICIAL NCAA sites)

Verified this session (`data/vb2025.json` → `official_sources`):
- ✅ **Champion / runner-up / score / Final Four / top-4 seeds / 31-auto+33-at-large** — confirmed on official NCAA.com pages (cited).
- ⚠️ **Seeds 5–16** — NOT on any official page; rest on ESPN/Wikipedia. Flagged in footer.
- ⚠️ **Opp RPI column** — from his workbook, labeled "average opponent **2024** RPI" (prior-season proxy, his tracker — NOT official 2025 NCAA).
- ℹ️ **NCAA publishes RPI + official stats + the bracket, but NOT a Top-25 poll** (those are AVCA/AP). The tool's ranking is his Adj model, so this is moot.

Official landing URLs (in the JSON + footer):
- Stats (records, K/A/B per set): `https://stats.ncaa.org/rankings?sport_code=WVB&division=1`
- RPI: `https://www.ncaa.com/rankings/volleyball-women/d1/ncaa-womens-volleyball-rpi`
- Bracket: `https://www.ncaa.com/brackets/volleyball-women/d1/2025`

---

## 6. OPEN BLOCKERS & DECISIONS (resume here)

1. **Official re-pull is GATED on the browser.** Cody approved re-pulling records + SOS from `stats.ncaa.org`, BUT that site **403s the server-side fetcher** and NCAA.com is a JS SPA (blank to fetch). Needs the **Claude Chrome extension connected** (it read as disconnected all session). Once connected: drive stats.ncaa.org to pull official records/SOS for all 40 teams AND 2025 **player per-set stats** (for real Returning %). Check with `tabs_context_mcp` first.
2. **2026 Returning % is illustrative placeholder** (deterministic hash 45–90%, badged "illustrative"). Method is defined in the tool: Returning % = 2025 per-set production by players still on 2026 roster ÷ team's 2025 production; incoming transfers/signees = separate "added" figure, not blended.
3. **DECISION Cody still owes:** transfer-portal ins/outs & signees are **not on any official NCAA page**. Official-only ⇒ graduation-only returning %. Complete returning % ⇒ needs a labeled non-official portal tracker (VolleyballMag/On3). He hasn't chosen.
4. Offered but not done: make the **Opp-RPI column drive Adj** (currently Adj uses sheet-1 SOS rank; Opp RPI is display-only).

**Immediate next step when resuming:** ask Cody to connect the Chrome extension + answer the portal-source question (#3), then do the official pull.

---

## 7. Gotchas

- **Large inline content to Google Drive / long blobs are unreliable to reproduce** — keep payloads small & plain; verify by read-back. (See memory `drive-large-inline-content-unreliable`.) This is why data flows through JSON files + a build script, never hand-transcribed.
- No browser this session → **no artifact was visually verified.** Ask Cody to eyeball, or connect the extension.
- Leftover in Cody's Drive (no delete tool available; needs browser): two `_sparkline_test` sheets + one broken earlier "Cody's MLB Playoff Dashboard 2026" (the one with `#ERROR!` cells) from the *other* (MLB) task.

---

## 8. Unrelated: the original MLB task (this bundle's HANDOFF.md)

This session started on the **MLB** handoff (`HANDOFF.md`) — made a Google-Sheets visual dashboard (`data/dashboard2.csv` → sheet `16DYylcTMP3g_15GQeHVRq7TB6J0Of_qmgl9Qs7HFfbQ`), then Cody pivoted to volleyball. MLB dashboard was delivered (monospace/color polish still pending a browser). Separate track.
