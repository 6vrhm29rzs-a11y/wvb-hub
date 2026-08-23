# SUPERSEDES session_close_2026-08-23.md — close of 2026-08-23 (afternoon)

Read this first. The earlier close of the same date covers the morning (polls,
Pacific time, public-build hardening) and is still accurate for that; everything
below happened after it.

---

## ⚑ RESUME HERE

**Nothing is committed.** 154 modified, 41 new, 4 deleted. `origin/main` is still
`e613601`. Git is classifier-blocked in auto mode — Cody must paste the command.

```
cd /Users/codyrose/Womens_College_Volleyball_2026
git add -A && git commit -m "Digby Top 25, rotations, team stats, visual pass" && git push origin main
```

**Verify remote state with `git ls-remote origin` before trusting that line.**

Everything runs: **14 test suites pass**, the nightly sequence completes clean
end-to-end (dry-run of the real workflow steps), and the build was verified to
work from a **fresh checkout with no `Cody/` directory** — which is what CI has.

---

## What changed, in rough order of importance

### 1. Rotations are recoverable after all — and are built

`docs/rotations_finding.md` closed this as impossible. That was right **about
ncaa.com** and wrong as a general claim. The NCAA's own play-by-play names the
server on **every rally**, and a team serves in rotation order by rule.

- `scripts/rotations.py` derives the rotation; `scripts/build_rotations.py`
  streams a 739 MB season CSV into `data/rotations_2025.json`.
- **48,625 of 50,410 set-teams resolved (96.5%)**, 357 teams, 348 matched.
- Validated by the 5-1 structural signature — the same test that scored **at
  chance** on ncaa.com's jersey ordering scores **82.2%** here (n=169) against a
  21.3% null.
- Free corroboration: the derived substitution `Taylor Landfair for Teraya
  Sigler, 21 sets` matches beat reporting about Sigler's back injury.
- ⚠ **It is the SERVING six, not the six on court** — the libero replaces a
  middle exactly as she rotates to the back row, so middles rarely appear.

Source is the MIT-licensed `ncaavolleyballr` dataset. **We never fetch
stats.ncaa.org** — it 403s non-browser clients and the no-scrape hook blocks it.

### 2. Digby

- **Summaries**: 340 of 348 teams. Every number machine-checked against a fact
  sheet before storage. 41 cited numbers hand-verified across three teams; 1,600
  player names checked, zero fabricated.
- **Chat**: `Ask Digby` panel, served by `live_server.py` with the key from the
  environment only.
- 8 rejections: **6 were my bugs** (hyphen-as-minus in records, and numbers named
  in a field name), both fixed; **2 were genuine catches** — San Diego St. and
  UTEP each cited a number that is nowhere in their data.

### 3. Digby's Top 25 — a ranking that moves from day one

The Rankings tab is a preseason projection that cannot move, and the in-season
rating refuses to fit under 50 matches. `digby_top25.py` blends them with
`w = n/(n+k)` where **k is measured, not chosen**.

⚠ **The subtle part, and the first version got it wrong:** shrinkage weights a
prior by **its own error variance**, not the population spread. Using the
between-team variance treats the projection as if it were "an average D-I team"
and gave one match **20%** of a team's rating. Corrected via the projection's
measured out-of-sample rho (0.8379): **k = 13.5 matches**, one match ≈ 7%.

### 4. Team stats, both sides of the ball

Box scores gained a **Team totals** row; team pages gained a **Team stats** box
showing what a team does beside **what it allows**. The Leaders tab became
**Stats** with a Players/Teams toggle and a This-team/Allowed selector.

⚠ **Points per set is kills + blocks + aces.** I briefly showed rally points off
the set scores as a second row; Cody corrected it — that is not what the sport
calls points. One row now.

### 5. Visual pass

Oswald condensed display face; real school colours (373, read out of the logo
SVGs) as row edges and avatar fills; sliding nav underline; **SVG bracket
connectors with the right half mirrored** so both sides converge on the final;
crests in every view (1,581).

### 6. Public build switched OFF

`output/vb_dashboard.html` is a **separate tracked file in a PUBLIC repo served
on GitHub Pages** — the only thing anything was ever stripped from. Cody wants
one build with everything, so the published copy is no longer produced.
`strip_private()` and its guards are intact; **re-read them before re-enabling**,
because what they remove is other people's.

⚠ **Cost: the GitHub Pages URL no longer updates.** Phone access is gone until
either the repo goes private (paid) or something else serves it.

---

## Data corrections worth keeping

- **32 conferences, not 33.** ncaa.com still serves UT Arlington as `wac`; all 16
  of its conference fixtures are UAC. `conference_repair.py` derives a team's
  conference from its own schedule when its league is undersized and every
  opponent agrees.
- **The AQ map had a WAC row and no UAC row**, so the UAC was silently riding a
  default.
- **New Orleans showed 0 scheduled matches** — the feed says `LSU New Orleans`.
  Third time this alias has bitten. Count through `reconcile_2025.norm()`.
- **Saint Francis is genuinely 0** — not in a single 2026 fixture, and the feed
  listed it as division 3 in 2025. Its page now says so.

---

## LOCAL ONLY (on disk, not in git)

| Path | Why |
|---|---|
| `Cody/` | the page itself, player art, `_superseded/` |
| `data/raw/2025/pbp/wvb_pbp_div1_2025.csv` | 739 MB third-party mirror |
| `reference/` | research documents, official PDFs, VolleyTalk saves |
| `assets/digby_*_full.png` | full-size source art |

---

## Open

- **Cody has still not run `/code-review ultra`** — the Builder cannot launch it.
- **8 Digby summaries** retry free on the next `digby.py` run with the key.
- **Coaches**: `data/raw/2026/coaches_2026.json` is scaffolded with the top 50,
  all null. Not derivable from any feed we can reach — school coaches pages are
  JavaScript-rendered. It is a sourced-entry job.
- **Rotations are not wired to a live 2026 source.** The deriver is finished; the
  historical CSV covers 2020–2025. Live 2026 would need StatBroadcast permission
  or the NCAA's own pages, neither of which we fetch.
- Two teams still have no 2026 roster: Central Conn. St., Tennessee Tech.
