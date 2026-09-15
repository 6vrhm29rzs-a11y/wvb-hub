# SESSION CLOSE — 2026-09-15 (pre-macOS-27 upgrade)

**⚑ READ THIS FIRST ON THE NEXT BOOT**, then `handoff/STATUS.md`.
Supersedes `docs/session_close_2026-09-08.md` on the product; that close is
still the right record of the committee-basis field selection and the
ultrareview round.

---

## STATE AT CLOSE

- **94 of 94 guard suites pass.** Private and public pages both rebuilt from a
  coherent corpus (`local_refresh --force` last, so nothing is half-built).
- **HEAD is `02adaa2`. NOTHING FROM THIS SESSION IS COMMITTED.** `origin/main`
  agrees with local HEAD, so the uncommitted work is the whole delta.
- **Private files are snapshotted** to `Cody/backups/2026-09-15T1604/` (29
  files). Git does not carry `handoff/`, `Cody/` or the ChatGPT drop folder —
  that snapshot is their only copy besides the originals.
- `com.codyrose.wvb-live` has `RunAtLoad` + `KeepAlive`, so the phone site
  restarts by itself after the upgrade. The two mail agents fire at 07:00 and
  23:00 and need nothing.

## WHAT THIS SESSION BUILT

**Notes & ideas tab** (private) — Cody's notes stored verbatim and
append-only, each with a status and a line saying what happened; a decline
must carry a reason. `scripts/notes_log.py`, 17 notes logged.

**The Claude↔Codex handoff record** — `handoff/` is authoritative for that
exchange and **supersedes the Drive-only mailbox workflow for that pair
only** (the Drive bus still stands for the Claude-app seat; recorded in
`CLAUDE.md`). `STATUS.md` is the index; `messages.jsonl` append-only; bodies
written once. CL-0001 … CL-0009.

**Away/home mode + catch-up + review scopes** — declared, never inferred.
Review scope is the **sha256 of every file in it**, re-checked at render time,
because a commit hash says nothing while work is uncommitted.

**Local backups** — `scripts/backup_local.py`, wired into the refresh loop at
`--if-stale`, refuses credential-shaped filenames.

**Cody's Week 3 ballot** archived (as submitted, plus an amendment recording
that the Minnesota-corrected copy was never sent).

## WHAT THIS SESSION MEASURED AND CLOSED — three negative results

1. **Gamebook PDFs → rotations: NOT BUILDABLE.** Format census over 20
   schools: **1** publishes the NCAA LiveStats gamebook (the only format with
   play-by-play), 13 publish a SIDEARM box with none, 6 none found.
2. **Our own box data: NO GAP.** Where our data and a school's own gamebook
   overlap they agree **exactly, 16 of 16 fields, both teams.** ⚠ An earlier
   claim that ours was "partial" was me reading `boxscores.jsonl` instead of
   `playerbox.jsonl`.
3. **Serve-receive as a rating channel: REFUSED.** Best variant +0.00006, CI
   `[-0.00062, +0.00071]`; heavier weights measurably hurt. Receipt
   `data/blend_recv_2025.json`.
4. **Rally-denominated rates: no difference.** All nine per-set vs per-rally
   pairs overlap. Built, kept in the measurement, nothing restructured.

## BUGS FIXED

- **The nav underline pointed at the wrong tab on ten More-menu routes** —
  `moveNavBar()` bailed when no primary tab was selected and the bar stayed
  where it last was. Found in a phone screenshot; the DOM was correct.
- **Disputed start times** now flag on all three surfaces (Schedule, Today,
  team page), not just one.
- **Correction 85** — San Francisco def. UNLV 3-2; the feed had the teams
  inverted (0 of 32 box rows fit their filed team).
- `ingest()` defaulted an unrecognised filename to **codex**, which could
  falsely verify two-way exchange. Quarantined now; verification needs an
  explicit acknowledgment, which is a **local workflow step, not authenticated
  identity**.
- `fixture_time_check` discarded timezone offsets and assumed UTC.
- Six guards were pinning a calendar phase, a file, or the shape of a fix
  rather than the fix, and each failed CORRECT code.

## OPEN — Cody's decisions

1. **Suspended matches** — own display state, or keep the badge?
2. **Petersen Events Center** — when the feed is silent on a final, should a
   cited pregame venue still render with its provenance?
3. **Tab audit** — merge `/players` + `/player-ratings`; filter
   `/result-ledger` (139k px); keep or cut `/intel` and `/film-room`.
4. **Wollard's availability status expired** on its own `review_by` (n0014).
   Needs a fresh Purdue source or a box-verified return. Not extended by me.

## OPEN — awaiting Codex

Two review scopes are `queued_for_review` (notes/handoff privacy; start-time
flags), fingerprints current. ⚠ **Two-way exchange is still UNVERIFIED** —
Codex has read access and has written nothing into the record.

## NEXT ACTION

Cody runs the commit (git is his command; the message is staged at
`.git/WVB_COMMIT_MSG.txt`, though it predates the last few days' work and is
worth rewriting). After the upgrade: confirm `live_server` came back, then
`python3 scripts/local_refresh.py --force` before trusting the page.
