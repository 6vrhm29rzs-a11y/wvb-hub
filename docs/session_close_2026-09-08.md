# Session close — 2026-09-07 → 09-08

Supersedes `session_close_2026-08-27.md` on the product. Read that one for the
scoreboard/dossier era; read the CLAUDE.md condensed entries for 09-03→09-06
(trust cutoff, hitting channel, popout, visual identity, suspended mechanism).

## What shipped these two days

**The projected field runs on committee criteria now (Cody's directive:
"use the same metrics the selection committee uses").** The bracket's 64 was
being selected and seeded by `rank26` — the STRENGTH blend, the exact R3 leak
`project_field.py`'s docstring forbids (measured: the composite favours
good-margin/bad-record teams vs RPI, corr −0.205). Now: at-larges and every
seed by **projected final RPI** (median rank across the 4,000-iteration season
simulation — in September the committee-predictive resume is the projected
one), tie-broken by live resume rank; each league's AQ to its **most likely
champion** by simulated title odds. KPI proprietary, absent, stated. This
retired the Saint Francis artifact (zero fixtures → no odds → no bid; LIU
correctly holds the NEC) and put Missouri/Villanova in, Michigan St. out —
strength #16, projected resume outside the field, which is R3 in one team.
Guards: committee basis stated; no zero-fixture team in field or on a bid; an
AQ without title odds only when its whole league lacks them; seed order
monotone in projected RPI with a negative control proving the strength
ordering fails it. Honest, RENDERED fallback prose when no sim is on disk.

**The AVCA join (Cody's catch: "Arizona State vs ASU... showing NR").** Two
consumers joined poll rows via `_hub_name()`, the feed-name mapper, which does
not fold the AVCA's own spellings — Arizona St./Penn St./USC rendered AVCA NR
while ranked. Both now join through `build_rankings_board.key()`;
`southerncal→usc` alias added (USC had been NR on the board itself for a
week). Coverage guard: every captured poll school must key to a hub team —
proven to trip on the pre-fix state. Sep-7 poll captured (25/25 join).

**Freeze-Monday movement was comparing the ranking against itself.**
Weekly-track rows are labelled by the week they COMPLETE and captured the
Monday after, so the "not this week" exclusion (label == today's ISO week)
matched nothing — on freeze Monday both movement columns compared against a
snapshot minutes old and rendered every team flat.
`snapshot_rankings.captured_week()` is the one definition; both pickers
exclude on capture week. Also: test_top25's movers guard was reading the My
Ballot table's `mv-` marks (classname collision) — scoped to the t25 region.

**The daily workflow verified results AFTER building the ratings.** The
audit-manifest gate caught it live (digby 932 counted vs 934 eligible — a
build refusing its own stale artifact). refresh.yml and local_refresh already
verified first; daily.yml was the unmirrored copy. Reordered, and
`check_verifier_precedes_ratings` asserts the order in every workflow file
plus local_refresh's REBUILD sequence.

**The FIFTH New Orleans alias bite, in the prediction chain.** predict_2026
joined raw scoreboard names against hub-keyed strength — "LSU New Orleans "
with the trailing space — silently dropping all 29 fixtures: no forecasts, no
title odds, no projected RPI. Both predict and the simulator's played-loop now
join through `reconcile_2025.norm`.

**Ultrareview ran (Cody launched it; free run 2 of 3) — five findings, all
real, all fixed.** Two were live: the `played_2026` counter still keyed by
feed spelling (would have written permanent zeros for aliased teams into the
append-only prediction log — my own half-applied fix from hours earlier), and
the strength-fallback field basis stated only in meta while both pages shipped
committee prose. Two were guards not guarding: a nonexistent `SEQUENCE`
attribute behind a hasattr (silently skipped), and a computed-never-asserted
evidence list. Plus a loop hoist. **The R7 receipt: a fresh-context reviewer
caught in one pass what the author verified past four times.** Mechanics for
next time: the tool diffs against the MERGE-BASE of HEAD and the base arg, so
an isolated-code branch checked out locally (old commit + one commit carrying
only the code changes) is the way to review code without the data churn.

**Correction 42 — Florida A&M–Coastal Carolina, the 20th ledgered feed
inversion.** The pending alarm fired in CI (recheck_by expired on the UTC
boundary); by then both schools had posted the same alternative: Coastal won
3-1 on a neutral floor (Dolphin Classic, Jacksonville), against the feed's
internally-coherent claim that FAMU won 3-1 at home. Bryant–Brown remains the
only pending hold.

**Phone-access infrastructure (Cody's evening).** Lid-close was killing the
site: `sudo pmset -a disablesleep 1` (his terminal; revert with 0). Tailscale
Serve had been disabled at the TAILNET level — he re-enabled it and
`tailscale serve --bg 8799` wires HTTPS; the CLI needs the GUI app running or
it errors `CLIError 3`. Tailscale key expiry disabled by Cody — the ~09-10
deadline is gone. Fallbacks that never depend on the Mac being awake: the
GitHub Pages copy; and `http://codys-macbook-pro.tail069aa6.ts.net:8799`
works without Serve.

**Availability signal:** Lilly Wachholz (OH #13, Iowa St., the only Wachholz
in D-I box scores) went down mid-match vs Iowa per VolleyTalk — recorded as a
community signal, sets no status, review-by 09-15.

## Operational lessons paid for (again)

- **CI raced pushes twice**: a red nightly can be a stale checkout — check
  the run's headSha against the fix's commit time before diagnosing code.
- **The 16 permanently-502ing gids** are finals whose linescores never
  arrived; the crawl's retry is tolerated on purpose (suppressing it deletes
  the chance of ever collecting those tapes).
- **Raw-log merges are now routine**: games.jsonl/verification log = line
  union (newer side first, other side's unique lines appended);
  boxscores/playerbox/lineups = per-gid last-wins preferring the newer crawl;
  single-JSON = take the newer, regenerate via `local_refresh.py --force`.
- **check() argument order**: test_rankings_board is `check(label, ok)` — I
  inverted it and five guards passed vacuously, visible only because the
  printed labels read "True". Assumed-helpers count reached ~15 (SEQUENCE,
  load_board, ROOT-vs-REPO, io import). READ THE MODULE FIRST remains unpaid.
- **`git stash` on a path can eat a fix**: verify the working tree after any
  stash used to test a guard against HEAD.

## State at close

78 suites green · pushed through `9a15dd6` · corrections at 42 · pending:
Bryant–Brown (recheck 09-09) · Wrigley suspended review-by 09-14 · W37 frozen
· Sep-7 AVCA poll archived · committee-basis field live on the bracket ·
1 free ultrareview remaining.
