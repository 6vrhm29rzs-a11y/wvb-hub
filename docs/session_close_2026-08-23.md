# Builder session-close — 2026-08-23 (early)

**Supersedes `session_close_2026-08-22.md`.** Read this, then `CLAUDE.md`.

## State: green

All 8 test suites pass (7 previous + `test_lineups.py`). Sim, predictions, hub
all rebuild clean. `origin/main` = `a25bb7f` (Cody pushed it this session).

## 1. Cody's rotations ask — ANSWERED, and the answer is partly "no"

**Rotations 1-6 cannot be built from this feed. Question closed.**
Full working: `docs/rotations_finding.md`.

- The order the feed prints its six names in is **ascending jersey number
  (91.5%)**, not rotation order. Tested with the 5-1 structural fingerprint
  (MBs 3 apart, OHs 3 apart, S/OPP 3 apart): **15.8% / 19.3% / 11.2%** against
  a shuffled-chance null of ~20%. **The positive control is what makes this
  trustworthy — the same checker scores 100.0% on synthetic true-rotation
  lineups.**
- Rotation order is not recoverable indirectly either: **serves are named only
  on aces**, and the score fields are `null` on most plays.
- **"Who subs for who" is also not recoverable: 4.0%.** The feed records only
  the player coming IN, never who went out. The volleyball rule that a sub
  swaps with one specific starter resolves the pairing only when exactly one
  non-starter is off court: **439 of 11,074 entries**, 3,608 ambiguous. Not
  shippable, not shipped.
- **Setter front-row vs back-row IS the rotation order.** Not derivable.

## 2. What WAS built

- **`crawl_pbp.py`** — extract-and-discard (raw PBP is ~296 MB/season; we keep
  six names a match). **5,109 of 5,131 games**; the 22 misses are a persistent
  server-side 502, retried and confirmed.
- **`project_lineups.py`** → each team's most-started six,each player marked
  returning / departed / unknown, vacancies never filled with a guess.
  **336 teams** have a 2025 starting six, 324 with enough matches.
- **Offence system, 5-1 vs 6-2**, from how many setters a team actually starts:
  **280 · 4 · 64 not stated**. Badged only when a team's own lineups agree
  >=80%. Hand-verified on Missouri St. and Grand Canyon.
- **Full roster on every team page** — 322 of 348 — grouped setters/opposites/
  outsides/middles/liberos, with class, number, starts, sets and 2025 pts/set.
- **Roster positions 39.5% → 81.2%** via `crawl_roster_positions.py` (own file,
  never rewrites the roster) plus transfers' positions from their previous
  school. Remainder is a JS-template ceiling.
- **Transfers reconcile both ways** — rate × sets == departure points,
  **185 of 185, 0 mismatches** — and **191 transfers out** are now named with
  their destination.
- **`recover_missing_rosters.py`** — asks each school's home page for its own
  roster URL, falls back to schema.org `Person` blocks for JS-rendered pages,
  and accepts a domain only on independent confirmation. **26 rosters
  recovered; 346 of 348 teams now have one.**
- **`athletics_sites_overrides.json`** — 20 corrected domains. ncaa.com's own
  school pages carry the dead ones.

## 2b. The public site now runs the same page

`build_hub.py --public` builds `output/vb_dashboard.html`; `build_vb.py` is
superseded and out of the daily workflow. The two pages were separate products,
which is why the public one was three tabs and years behind. The public build
strips the VolleyTalk poll, Massey and the TV listings, **aborts** if a marker
survives, and rewrites `index.html` with a cache-busting hash.

## 2c. Photos, and a leak the first guard missed

- **Photo coverage 133 -> 290 teams** (38.4% -> 89.9% of projected-six slots).
  Same JSON-LD route as the rosters: JS-rendered pages still ship the squad as
  schema.org `Person` blocks carrying `image.url`. **196 teams, 3,240 URLs**,
  14/14 sampled return HTTP 200. **URLs only, never downloaded.**
- **⚠ The public build was leaking third-party DATA while passing its guard.**
  Removing the VolleyTalk/Massey columns was cosmetic: 25 VolleyTalk and 151
  Massey ranks still shipped inside `const TEAMS`, one devtools open away on a
  public site. Fixed at the point they enter the build; the guard now asserts
  the VALUES, not the words. **When the question is "did we publish X", grep
  the data, not the markup.**

## 2d. Live data pulled forward

Ran the daily crawl by hand rather than waiting for 09:15 UTC, so the page shows
last night's results: **Arizona St. 3 Texas 1** and Wisconsin 3 Louisville 0.
5 matches played. The model had Texas at 74.4% — scored as a miss (favourite
won 0 of 1). Worth noting how the log handled it: `/game/{id}` returned state
`P` with no linescores on two passes and `F` with full linescores on the third,
and the append-only final-beats-non-final dedup resolved it correctly. That is
R2 working as designed.

## 3. Bugs found and fixed

- **⚠ "Nebraska fell off the rankings" (Cody).** Nothing wrong with the data —
  the nav was made sticky and table headers were offset by its height, but
  rankings/leaders stick inside their **own** scroll box, so the offset pushed
  the header 42px **down over row 1**. `.scroll th{top:0}`. **A sticky offset is
  relative to the nearest scroll container, not the page.** `elementFromPoint`
  at a row's centre is what proves a row is actually painted.
- **129 fixtures showed a 1:00 AM ET start.** That is ncaa.com's placeholder
  for an unannounced time, formatted exactly like a real one. Proof: in the
  completed 2025 season only 13 of 5,133 fixtures had an early-AM time and
  **all 13 were at Hawaii** (1:00 AM ET = 7:00 PM HST). Renders as `TBA`;
  Hawaii's real late starts are preserved.
- **Jersey-number spans inside player links** (`<span>#1</span> Hailee Mack`)
  made whole rosters parse as empty.
- **"0 of 6 returning" for teams with no 2026 roster at all** — now reported as
  unknown, not zero.

## 4. Corrections to the record made this session

Both were **single-game generalisations**, and both were wrong:
- "The feed's teamId is wrong on half the lines" → **2 of 409**.
- "2026 play-by-play is EMPTY" → **2 of 3 games carry real lineups**. Kentucky's
  six comes through correctly. `crawl_pbp.py` now runs **daily** to take them.

## 5. Open

1. **Roster gap CLOSED: 346 of 348** (was 320). The cause was ncaa.com's own
   stale athletics-site URLs, not the parser — corrections in
   `data/raw/2026/athletics_sites_overrides.json`, each confirmed either by
   shared 2025 players or by the site naming the school. Only **Central Conn.
   St.** and **Tennessee Tech** remain.
2. Photos beyond 132 teams; AQ mechanism for 6 of 32 conferences.
3. **`/code-review ultra` still not run** — Builder cannot launch it.

## 6. LOCAL ONLY — committed nowhere yet

Everything from this session is on disk and **not committed**. `git` is
classifier-blocked in auto mode; Cody pushed `a25bb7f` himself earlier.
New: `scripts/crawl_pbp.py`, `lineups.py`, `project_lineups.py`,
`test_lineups.py`, `crawl_roster_positions.py`, `recover_missing_rosters.py`,
`docs/rotations_finding.md`, `data/raw/2025/lineups.jsonl`,
`data/raw/2026/{lineups,roster_positions_2026,rosters_recovered_2026}.json`,
`data/lineups_2026.json`. Modified: `build_hub.py`,
`test_display_invariants.py`, `CLAUDE.md`, `.gitignore`,
`.github/workflows/daily.yml`.
**`data/raw/2025/pbp.jsonl` is gitignored on purpose** — 12 MB of raw payloads
that the daily `git add data/raw` would otherwise push to a PUBLIC repo.
