# wvb-hub — NCAA D-I Women's College Volleyball personal hub

**Working dir:** `/Users/codyrose/Womens_College_Volleyball_2026` (GitHub repo name: `wvb-hub`).
**You are:** Claude Code = the **Builder** (pure builder on auto mode — build/test, post logs to Drive, do NOT make product decisions or pre-assign roles). Team: **Cody** (Principal/decider), **Gemini** (Architect — Google + math), **Claude app** (Research & Review). Seats share NO memory/session — **Google Drive is the only shared bus.**

## Read first
1. Your **memory** (loaded automatically). Only two memories live at this path: `wvb-hub-drive-bus` (Drive IDs) and `drive-large-inline-content-unreliable`. Four older memories (`wvb-hub-next-session-migration`, `ncaa-volleyball-tool`, `cody-collaboration-workflow`, `cody-volleyball-rating-model`) stayed behind at `~/.claude/projects/-Users-codyrose-Downloads-handoff/memory/` and are **deliberately not migrated** — the Drive handoff + this file supersede them. Don't go looking for them.
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
- **SOLVED 2026-08-09 — opponent points/set.** Not in `/boxscore`; it's in **`/game/{id}` → `linescores[]`** = `{period, home, visit}` per set (both teams ⇒ points for AND against, per set). `/boxscore` → `teamBoxscore[].teamStats.points` = the **match total** (rally points, NOT the kills+aces+blocks stat formula), and its per-set `sets[]` array is **attack-only** (kills/attackErrors/attackAttempts/hit%) — no scores. **Cross-check: Σ linescores == teamStats.points**, verified on 4 games (3-set, two 5-set incl. 15-13/15-12 deciders, championship 6500718). Game ids via `/scoreboard/volleyball-women/d1/{YYYY}/{MM}/{DD}/all-conf`. Dead endpoints: `gameInfo`/`scoringSummary`/`teamStats`/`linescore` → 422.
- **Python is 3.9.6** (system, Command Line Tools) — **target 3.9**: no `X | Y` unions, no builtin generics (`list[str]`) in annotations, no `match`. Use `typing.List/Dict/Optional/Union`. Decided over upgrading, to avoid a version change mid-build.
- Class year → school roster pages (annual). KPI = proprietary, fetch-only. AQ count/method → config + per-conference data.

## What exists here
`output/vb_dashboard.html` (built dashboard, **40-team sample**, embedded logos) + `vb_template.html` (source; `scripts/build_vb.py` injects data). `data/vb_*.json` = the 40-team datasets (model, rosters, transfers, official RPI, logos). Scale to **all 348** in Phase 1.

## Git
Repo initialized 2026-08-09 on `main`, commit `499a537` (20 files). Identity set **repo-local** (`Cody` / GitHub noreply) — global config untouched. `.gitignore` blocks credentials preventively (there are none: Drive auth is the claude.ai MCP connector's server-side OAuth, not a local `token.json`), plus `.claude/settings.local.json` and `full terminal convo.pdf` (transcript, not a build input — one line to re-include). `gh` authed as `6vrhm29rzs-a11y`.
**Pushed 2026-08-09 ~23:50** — live and public at `https://github.com/6vrhm29rzs-a11y/wvb-hub`, remote `main` = `a240483`.
**Verify remote state with `git ls-remote origin` on boot** — do NOT trust the last written statement about it. (A 2345 session-close said "PUSH NOT LANDED"; the correcting amendment was filed as a *separate* Drive doc and went unread on the next boot. Corrections go in the doc they correct, or the superseded doc carries a pointer.)

## Next steps
**Phase 1** (do not start mid-session — a paced 7 cats × 7 pages crawl, and an interrupted run leaves a partial dataset that looks complete): fetch all 348 (ids 45–51, raw counts, ~1–2 req/s); build the game-log side on `/game/{id}` linescores for points for/against per set; produce clean 2025 `data.json` in `Data/` (metric-agnostic, source-tiered, dated); reconcile vs official RPI rank ordering. **Metric still deferred by design** — measure net-points/set vs TCV vs original Adj against 2025 outcomes.
