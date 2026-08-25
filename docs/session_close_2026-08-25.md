# SESSION CLOSE 2026-08-25 — supersedes `session_close_2026-08-23b.md`

`23b` is still the right record of **why** the rating, the crawl and the poll
work are as they are. Everything it says about the **product** — tabs, Match
Desk, Scores, the ballot — is out of date. Nine commits landed today and the
shape of the site changed.

**Remote is `59d433e` (was `1eec0db` when this was first written -- the
line went stale within the day, which is exactly why it says this). Verify with
`git ls-remote origin` rather than trusting it.** Git is classifier-blocked in
auto mode: hand Cody the command.

---

## What the site is now

**Five primary destinations, not twelve.** Match Desk · Scores · Rankings ·
Teams · My Ballot, with the reference tools (Stats, Players, Standings,
Projected bracket, Schedule, On TV) behind a keyboard-accessible **More** menu.
Digby's Top 25 is a view *inside* Rankings, beside POWER and AVCA.

**Everything is routed.** A hash router (`#/match-desk`, `#/rankings/power`,
`#/teams/kentucky`, `#/players/kentucky/brooklyn-deleye`, `#/scores/<gid>`,
`#/match-desk/<gid>`) drives every navigation through one handler. Back,
Forward and a direct refresh all restore the same view. A player carries where
she was opened from, so the breadcrumb reads `Teams › Kentucky › Brooklyn
DeLeye` with a matching return action.

**Match Desk is a rundown**: date/state header, at most one featured match
chosen by a *stated precedence* (never a score), then `Live now` / `Just
finished` / `Coming up` lanes. **Scores is a ledger**: Live/Final/Upcoming/All,
grouped by the day played, compact ruled rows.

**One score header exists.** `ribbonHTML()` draws the featured match and the
match detail, so a scoreline cannot be phrased two ways.

**Private surfaces** (stripped from the public build, and the build ABORTS if a
marker survives): the Ballot Command Center — weekly briefing, five review
triggers, a two-team comparison workspace, read-only history — and **My Board**,
a watchlist held only in `localStorage`.

---

## ⚠ THINGS THAT WILL BITE THE NEXT SESSION

**1. A NESTED `<section>` INSIDE `#v-ballot` TRUNCATES THE PUBLIC STRIP.**
`strip_private` removes `<section id="v-ballot".*?</section>` **non-greedily**,
so an inner `</section>` ends the match early and the rest of the ballot ships.
The build aborted on its own marker when this happened. Use `<div>`.

**2. `const TEAMS` IS DECLARED NEAR THE END OF THE SCRIPT.** Anything that
reads it must run after it. `route()` is booted deliberately *after* `TEAMS`
and deliberately *outside* the `BALLOT-INIT` sentinel — that block is stripped
from the public build and routing is not private. Booting earlier threw
`Cannot access 'TEAMS' before initialization`, aborted the rest of boot, and
left a direct load of `#/teams/<slug>` showing an EMPTY panel. A `try/catch`
around such a read reports the dead zone as something else entirely: My Board's
loader reported it to the reader as "this browser is not letting the page store
anything".

**3. CLASS AND ID COLLISIONS ARE THE MOST COMMON BUG IN THIS FILE.** Six so far:
`.lead` (a view's lead sentence), `.why` (a bordered card), `.bwsub` and
`.bwlink` (fenced ballot classes borrowed by public markup), `.mt` (the Scores
card's team block, `flex-direction:column`), and `#bwcmpout` (a duplicate id).
**Check a new name against `git show HEAD:scripts/build_hub.py` before using
it.** There is an id-uniqueness guard and a fenced-class guard; both have fired
for real.

**4. `hidden` LOSES TO A `display` RULE.** `.cards{display:flex}` beat the UA's
`[hidden]{display:none}`. There is now a global `[hidden]{display:none!important}`.

**5. SUBSTRING MATCHING IN A GUARD HITS REAL DATA.** `.bwr` matched `.bwrap`
(the bracket); `mbrow` matched the player surname **Sta*mbrow*ska**. Match
class names as whole tokens.

**6. A GUARD THAT GREPS FOR A PHRASE WILL FIND YOUR OWN DENIAL.** This has
happened seven times: comments saying "never a TBD", "no composite watch
score", "nothing here is a recommended Top 25", "no momentum" all tripped the
guards forbidding those words. Guards now either strip comments first or
require each hit to sit in a **negating sentence**.

---

## ⚠ THE ONE THAT ACTUALLY SHIPPED

`esc()` was written for the ballot and lived inside the region the public build
strips. A later phase made it a dependency of `matchRow()`, `ribbonHTML()`,
`renderLedger()` and `renderMatchDetail()` — all of which run on the **public**
page. The published Scores ledger threw `esc is not defined` and rendered
**zero rows**; opening a match did nothing. Every suite stayed green, because
the public checks only ever asserted what must be **absent**.

**Absence of private things is not presence of a working page.**

There is now a **call-graph guard**: for every function the public build
defines, any function it calls that exists in the private build but not the
public one is a stripped dependency. No names are hard-coded. 396 functions
checked. Its negative control puts `esc()` back inside the fence and the guard
names the call sites itself.

---

## ⚠ A CORRECTION I OWE THE RECORD

Commit `dd9ca23` claims two page-aware test fixes "would have turned tomorrow's
nightly red". **That is wrong.** `daily.yml` runs `python3 scripts/build_hub.py`
— which writes `Cody/START-HERE.html` — at line 200, *before* the Invariant
guards at line 225. CI therefore reads the private page like any other run.
Verified by deleting `Cody/`, running the build, and watching it come back.

What those fixes actually buy is robustness when the suite is pointed at the
**public** page, which `page()` falls back to whenever `Cody/` is absent — a
condition I create locally, not one CI produces. The `test_freshness_refresh`
finding in that same commit **is** real: it ran in neither workflow and now
runs nightly.

---

## State of the automation

- **The scheduled `daily.yml` went green on `schedule`** (`32833964386`,
  09:49Z). That was the last open question from the Aug 23/24 failures.
- **`refresh.yml` runs hourly in 23–29s and stops at "Nothing new"**, skipping
  the Invariant guards. No match has gone final since it was built, so the
  publish path has not run with this week's code.
- **Every suite on disk now runs nightly** — checked by diffing the workflow's
  command list against `scripts/test_*.py`.
- 24 suites pass with `Cody/` present and 24 with it moved aside.

---

## ⚑ NEXT ACTION: FRIDAY 2026-08-28

Three things have their first real test on the first match day of the season,
and none can be brought forward:

1. **Run `python3 scripts/probe_live_boxscore.py` during a live match.** It is
   the measurement that settles whether `/game/{id}/boxscore` carries usable
   team and player stats mid-match. **Nothing in this repo may claim live stats
   are available until that has run.** Everything is built so "no usable stats"
   is the ordinary path; if Friday shows otherwise, the display path is already
   wired and it becomes a copy change.
2. **The refresh publish path**, end to end, for the first time.
3. **The board under a genuine slate.** It has been tested against a stubbed
   Friday (195 fixtures) — where it printed 206 rows and a 13,593px page before
   the lane caps, now 30 rows and 2,743px — but a stub shares my assumptions in
   a way real data does not.

## Still open, unchanged

- 3 Digby summaries withheld: their facts moved, and regenerating needs Cody's
  API key. **Read the VOLATILE-field rule in `CLAUDE.md` before touching
  `digby.fact_sheet()`** — getting it wrong cost ~$4 once already.
- 338 Digby summaries still unwritten (10 exist and are verified stable).
- GitHub Pages does not update: the public build is off at Cody's instruction.
  The `esc()` breakage above was therefore never live to a reader.
- Cody has still not run `/code-review ultra`.
- Rotations have no live 2026 source.

## What the tests are and are not good at

Every defect found today — the public `esc()` breakage, the CI-condition
question, and the 206-row Match Desk — was found by **looking at the thing**,
not by a failing test. The suites are good at holding ground already taken.
They did not catch what went wrong on the way in. The call-graph guard closes
one of those three; realistic-volume rendering is still only checked when
someone remembers to stub a busy day.

---

## Addendum -- the team-page sweep (same day)

Three defects, all found by reading the page rather than by a failing test.
That is now the fourth session running in which looking beat the suites, and it
is the honest summary of what they are for.

**1. PROJECTED POINTS PER SET PRINTED RAW.** The projected-six list emitted
`(c.adj !== undefined ? c.adj : c.rate)` with no formatting, so whatever
precision the JSON happened to carry reached the page: Kentucky read `5.572`,
`5.188`, `3.04`, `2.185` in one column. Two problems in one -- precision that
changes row to row, and a **third decimal on a projected quantity**, which
claims a resolution the fit does not have. Every other points-per-set on the
site is `toFixed(2)`. Now routed through one `ppsFmt()` helper: same measure,
same rendering, everywhere (R4). A null renders an em dash rather than `NaN`.

⚠ **The other two `.rt` call sites were audited and deliberately left alone** --
one is a start count (`33`) and one is `"N pts"`. They share a CLASS, not a
measure. Formatting them would have been the R4 error in the opposite
direction.

**2. TWO COUNT PILLS WERE UNLABELLED IN THE TEXT LAYER.** `<h3>Upcoming<span
class="cnt">22</span></h3>` renders with an 8px gap and a tinted pill, so it is
correct **to the eye**. Its `textContent` is `Upcoming22`, which is what a
screen reader and a copy-paste get -- a bare number beside a word, saying 22 of
what. Both pills (`.cnt` on Upcoming, `.h3n` on Full roster) now carry an
`aria-label` naming the unit, singular and plural. **The visible pill is
unchanged**; this was never a layout bug.

⚠ **Worth noticing: the two pills use different classes for the same job** --
`.cnt` and `.h3n`. They were found separately because a grep for one did not
find the other. If a third count heading is ever added, unify them first.

**3. A rendering that looks right can still be wrong in the layer you did not
look at.** That is the general form of both findings above, and it is the same
lesson as the sticky-header bug (the number was right and the page lied) and
the public `esc()` breakage (the tests asserted absence, not function). Check
the pixels, then check the text, then check the published copy.

**4. THE LOCAL SERVER WAS SERVING A STALE PAGE, AND IT LOOKS EXACTLY LIKE A
FIX THAT DID NOT WORK.** Found while verifying fix 2: the file on disk carried
the patch and the loaded document did not. `live_server.py` sent
`Cache-Control: no-store` on its **JSON** endpoints only; static files went out
with nothing but a `Last-Modified`, so Chrome cached `START-HERE.html`
heuristically and a rebuild simply did not appear -- through a hash change, and
through re-assigning `location.href` to the same URL, neither of which reloads.

This is the same problem the **public** build solves with a content hash in
`index.html`. The local server has no such indirection, so it now says plainly
that nothing may be reused: an `end_headers()` override on the handler, which
covers every response including 404s.

⚠ **The override made the two existing explicit sends redundant** -- left in,
they would have emitted `Cache-Control` twice. Both removed, and verified on
the wire: static HTML, `/api/live` and `/api/ballot` each carry the header
**exactly once**, with their bodies intact.

⚠ **`curl -I` sends HEAD and never reaches `do_GET`**, so it 404s every JSON
route here and proves nothing about them. Use `curl -s -D -`.

**State at close:** 24 suites pass with `Cody/` present and 24 with it moved
aside. Tree is clean apart from the three fixes above. Nothing here changes
data, ratings, or the crawl -- all three are display-layer only.
