# Session close — 2026-08-27

**SUPERSEDES `docs/session_close_2026-08-25.md`** on the product. That file is
still the right record of the five-destination routing, the Match Desk, the
`const TEAMS` dead-zone trap and the class/id collisions; it is out of date on
everything below.

**Read this first, then `CLAUDE.md`.** 13 commits, `956bef7 → c44ceac`, all
pushed. 46 guard suites green, both builds clean, public gate passes.

---

## ⚑ THE NEXT ACTION IS DATED: FRIDAY 2026-08-28

The season stands at **9 played matches**. Tomorrow schedules **196**, Saturday
**179**, and 2026-09-04 another **176**. Everything on this page had only ever
rendered a two-match day, and most of today went into finding what breaks at
100× that. Two things still need a real match day rather than a simulation:

1. **`python3 scripts/probe_live_boxscore.py` during a live match.** Still the
   measurement that settles whether live stats hold up over a full slate.
2. **The refresh job under a real crawl.** It fires every 30 minutes and
   publishes; it has never run against 196 finals.

---

## What was actually wrong, in order of what it would have cost

### 1. The 60-second poller would have thrown all day, and taken two bands with it
`pollLive()` writes to the slate band's markup, which an earlier Scoreboard
rebuild removed. **That branch had never executed**: reaching it needs a
fixture in state `pre`, and every day this page had rendered held two finals
and nothing scheduled. With 196 scheduled it throws — inside the poll callback,
so the just-finished band and the live band stop too, every 60 seconds, all
day, with nothing in the UI to say why. Found by feeding the poller a synthetic
first-Friday payload instead of waiting for Friday.

### 2. Start times were sorted as strings, in four places
`localeCompare` puts `6:00 AM PT` after `5:30 PM PT` because `'6' > '5'`.
Tomorrow's order would have run 5:30 PM → 6:00 AM → 6:00 PM → 7:00 AM. Fixed
with `tMinutes()` in the Scoreboard lanes, the slate band, the ledger day view
and the watch list. **In the day view it had already been "fixed" by sorting on
`a.ep` — a field that exists on 0 of 1,594 matches**, so the subtraction was
always 0 and it fell through to the broken compare beneath a comment saying the
problem was solved.

### 3. A guard was holding that bug in place
`test_wayfinding.py` asserted `"(a.ep || 0) - (b.ep || 0)" in C` under the label
*"lanes sort by time"*. It checked the **shape of a fix**, not the behaviour, so
it protected the broken version and read as proof it worked.

### 4. Fourteen of forty-six guards never ran in CI
The daily job named suites by hand and the list had drifted **three times** —
its own comments admitted the first two. By this morning it ran 32 of 46. The
half-hourly publish job was worse at **22 of 46**. Both now use
`scripts/run_all_guards.py`, which discovers, runs everything even after a
failure, and refuses to report a clean run if discovery comes back under 30.

### 5. Neither workflow had a timeout
Both share a concurrency group with `cancel-in-progress: false` — correct, a
crawl killed mid-write is what an append-only log must never see — but with no
`timeout-minutes` GitHub's default is **six hours**, so one hung run blocks a
whole match day. Bounded at 25 (refresh) and 90 (daily).

---

## What shipped as product

- **Team Dossier.** Kentucky 5,464px → 1,002px. Overview answers who / how
  good / what's next / who to watch / what changed; Matches · Roster · Numbers
  · Scouting · Outlook behind tabs. Built as a post-render DOM reorganisation
  so no rendering branch could be silently dropped.
- **Set-by-set line scores in the scoreboard row**, plus the reported event and
  venue in what used to be ~1,000px of dead space.
- **196 rows group by start time** (23 blocks) when a lane is genuinely a wall;
  a small day stays whole.
- **Schedule**: exhibition badge (it read "non-conf", which implies a match
  that counts), and a 10-line methodology lead cut to 3 with the rest behind a
  disclosure — five fixtures above the fold instead of one.
- **9px type floor** (27 rules had drifted to 8–8.5px), **canonical class
  labels** (ten spellings of five classes in one column).

---

## Verified in advance, and left alone because nothing was wrong

- **The rankings basis flips `blend → live` this weekend** once the season
  passes 50 matches. Movement correctly blanks across the ruler change. Note
  the precedence is now THREE-valued; the same-basis rule was written for two.
- **196 results will not rot the 348 Digby summaries** — 0 of 120 durable
  hashes move under a simulated results day. No regeneration bill.
- **CI is not shipping degraded ratings.** The Aug-26 CI dashboard had 0 pbp
  fields at 7.28 MB; Aug-27 had 1,448 at 9.86 MB, because the derived
  `data/pbp_player_2025.json` was committed on the 27th.
- **Page weight is fine.** 10.07 MB raw, **1.63 MB gzipped**, confirmed against
  the running server. A `t.fixtures` refactor would save ~1.5 MB raw and was
  not worth the R4 risk.
- **The Rankings tab's three counts** (9 matches / 10 teams / 8 D-I matches)
  look contradictory and are all correct — Norfolk St. played Division II.

---

## ⚠ The pattern that cost the most time today

**Guards that assert the shape of a fix rather than what it does.** Four failed
correct code this session, and one actively protected a bug. A sweep found
**9 such guards** in total; they are the ones pinned to a literal code
expression. When a guard fails, the claim it makes about the source needs
checking before the source does.

**And my own test scanners were wrong seven times**, each failing a correct
build: a non-greedy extractor that truncated at an inner arrow function; a
media-query lookup that read the first of forty blocks; a brace matcher that
treated a quote inside a comment as a string; a needle that matched a function
definition instead of its call site; a check satisfied by the very edit that
disabled it; a variable referenced before assignment; and a local shadowing a
module's own `src()`. Two of those crashed their suite rather than failing a
check, which is the only reason they surfaced.

---

## Open

- Cody has still not run `/code-review ultra`.
- Rotations have no live 2026 source.
- **Tailscale key expires ~2026-09-10** — phone access to the hub dies unless
  key expiry is disabled in the admin console. Only Cody can do this.
- 3 Digby summaries are withheld (Central Conn. St., Purdue Fort Wayne,
  Tennessee Tech); regenerating three is pennies. **Count the file before
  quoting a number here** — the old "338 to write" line was stale.
