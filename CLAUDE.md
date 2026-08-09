# wvb-hub — NCAA D-I Women's College Volleyball personal hub

**Working dir:** `/Users/codyrose/Womens_College_Volleyball_2026` (GitHub repo name: `wvb-hub`).
**You are:** Claude Code = the **Builder** (pure builder on auto mode — build/test, post logs to Drive, do NOT make product decisions or pre-assign roles). Team: **Cody** (Principal/decider), **Gemini** (Architect — Google + math), **Claude app** (Research & Review). Seats share NO memory/session — **Google Drive is the only shared bus.**

## Read first
1. Your **memory** (loaded automatically — see `wvb-hub-next-session-migration`, `ncaa-volleyball-tool`, `cody-collaboration-workflow`, `cody-volleyball-rating-model`).
2. Drive folder **"Women's College Volleyball 2026"** (`1uOBksR-O3TRPU6Ej84ymei0F4gFPqLe4`) → **Builder_Logs/ "Builder Session-Close 2026-08-09-2230 (pre-migration handoff)"** = the full handoff. Mailbox subfolders: Research/ · Specs_for_Builder/ · Builder_Logs/ · Data/. Write build logs to Builder_Logs/; end each session with a session-close incl. a **LOCAL ONLY** list (what's on disk but not on Drive).

## Cody's settled decisions (build against these)
- **History:** every run commits a **timestamped data snapshot to git** (no DB).
- **Schema:** **raw counts, never derived rates** — pull the ncaa.com superset (ids 45–51: kills, attack errors, total attacks, assists, digs, aces, block solos + block assists SEPARATE) + opponent points (box scores) + set scores + a **SOURCE-TIER** field (OFFICIAL/DERIVED/THIRD-PARTY/UNVERIFIED).
- **Architecture:** minimal — **Python compute + git + GitHub Pages.** No Sheets-as-DB / Cloud Run / Firebase / Apps Script. Hosting = phone access only (no auth/domain/polish). GH Pages private repo needs a paid plan → if not paid, make the repo **public** (public stats).
- **Display:** compute all 348, show top-N with a toggle for all.
- **Do NOT build the rating metric yet** — pipeline first, then measure net-points/set vs TCV vs original Adj against 2025 outcomes.

## Measured facts (don't re-derive)
- `ncaa.com` works from a **datacenter IP** (Akamai block is only `stats.ncaa.org`) → daily pipeline can be fully cloud.
- Team per-set stats: `ncaa-api.henrygd.me/stats/volleyball-women/d1/current/team/{id}` (or parse ncaa.com), paginated 7×50 = 348. **45 Hitting% (Kills/Errors/Total Attacks), 46 Kills/Set, 47 Assists/Set, 48 Aces/Set, 49 Blocks/Set (Solos+Assists sep), 50 Digs/Set, 51 W-L%.** RPI ranking endpoint = 348 teams but no raw RPI/SOS → derive + reconcile vs official rank ordering + figstats.
- Open gap: **opponent points/set** → verify ncaa.com box scores (`/game/{id}/boxscore`) yield it. Class year → school roster pages (annual). KPI = proprietary, fetch-only. AQ count/method → config + per-conference data.

## What exists here
`output/vb_dashboard.html` (built dashboard, **40-team sample**, embedded logos) + `vb_template.html` (source; `scripts/build_vb.py` injects data). `data/vb_*.json` = the 40-team datasets (model, rosters, transfers, official RPI, logos). Scale to **all 348** in Phase 1.

## Next steps
1. **git init + commit + push** to a GitHub repo `wvb-hub` (public if Cody isn't on a paid plan) — Cody must OK the repo/push.
2. **Phase 1:** fetch all 348 (ids 45–51, raw, paced); **verify box-score → opponent points/set**; produce clean 2025 `data.json` in `Data/` (metric-agnostic, source-tiered, dated); reconcile vs official RPI rank ordering.
