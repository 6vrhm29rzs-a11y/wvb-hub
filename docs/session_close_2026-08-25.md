# SESSION CLOSE 2026-08-25 — supersedes `session_close_2026-08-23b.md`

`23b` is still the right record of **why** the rating, the crawl and the poll
work are as they are. Everything it says about the **product** — tabs, Match
Desk, Scores, the ballot — is out of date. Nine commits landed today and the
shape of the site changed.

**This line deliberately does NOT name a commit.** It used to. It said
`1eec0db`, then `59d433e`, and each correction was itself a commit that made
the new value wrong the moment it was pushed -- an unwinnable line. The only
statement here that stays true is the instruction:

    git ls-remote origin main

**Run that.** Git is classifier-blocked in auto mode, so the Builder cannot
commit or push: hand Cody the command.

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

**5. A NON-DIVISION-I OPPONENT WAS UNMARKED ON THE PLAYER CARD.** The site
deliberately does not filter non-D-I opponents out -- filtering would change
what every rate means without saying so -- and it **states** that. But it
stated it only in the Stats -> Teams panel note, one view away from where a
reader meets the number. Catori Crawford's card read **`Hit% .500`** in the
same type as an SEC hitter's `.164`; her entire 2026 line is one match against
Elizabeth City St., a Division-II side.

The caveat now sits on the row it qualifies: a quiet `non-D-I` marker beside
the opponent, plus a note under the log that says **how much** of the season it
covers -- "her only match", "every match", or "2 of these 3". 15 of 209 game
rows carry it.

⚠ **It says "not Division I", never "Division II".** What we actually know is
that the team is absent from the D-I membership set. The stronger claim is not
ours to make.

⚠ **The class name `ndi` was rejected before it was written**: it matches 53
substrings in this page (sta*ndi*ngs, I*ndi*ana). `nondi` is clean. That is
collision number seven, caught by checking first for once rather than after.

⚠ **THE MIXED CASE CANNOT HAPPEN IN REAL DATA YET** -- two days into a season
every player is all-D-I or all-non-D-I. I exercised it anyway, by flagging one
of Olivia Babcock's two real matches in the live payload and reverting it.
**That is the only reason two grammar defects were found:** the branch rendered
"1 of these 2 matches **are** against non-Division-I **opponents**" -- wrong
verb and wrong noun for a singular count. A guard covering all four states now
sits in `test_player_aggregation.py`.

⚠ **Be honest about what that guard is.** Its `note_for()` is a
**reimplementation** of the page's branch, so it tests the arithmetic, not the
renderer; the page-side phrasings are asserted separately as strings. The
end-to-end proof was the browser run above, done once by hand. If that branch
is edited, re-run it the same way.

**6. THE SAME DEFECT SAT ONE VIEW OVER, AND I ONLY FOUND IT BY ASKING.**
Having fixed the player card, I checked whether the team page had it too. It
did, and worse: Norfolk St. read **`Hitting % .390`** against opponents'
**`.037`**, and **`Points / set 19.00`** against `9.33` -- every number true,
every number from one Division-II match. The sample was printed ("1 match, 3
sets"); the division was not. The `Results` row named the opponent with no
marker, so a 3-0 win over a D-II side rendered identically to a 3-0 win over an
SEC side.

Both surfaces now carry it. `team_season_stats()` counts non-D-I matches
alongside the ones it already counts, and the played row carries the flag from
the same membership set -- **one answer to "who is Division I"**, reused, not a
second copy.

⚠ **I NEARLY WORE A FENCED BALLOT CLASS.** The caveat was first written as
`<b class="warn">`. `.warn` is only ever defined as **`.bwstate.warn`** --
inside the region the public build strips -- so it would have styled nothing on
either page and would have been collision number eight, the same shape as Match
Desk borrowing `.bwsub`. Caught by grepping the definition before trusting the
name. It is `.dicaveat` now, defined in the open, and the guard asserts both
that the caveat does not use `class="warn"` and that `.dicaveat{` really
exists.

⚠ **A GUARD I WROTE COULD NOT FAIL, AND IT PRINTED ALL-OK.** The team-payload
block matched `const TEAMS = (\[...\])`. `TEAMS` is an **object**, so the
regex matched nothing, `if m4:` was false, and six assertions were skipped in
silence while the section still reported success. Fixed, and the missing
payload is now itself a **failure** rather than a skip. **Verified by negative
control**: forcing the flag to `False` makes the guard fail `0 of 17`, and the
restore brings it back green.

**7. THE CAVEAT HAS A THIRD HOME, AND NOW ONE DEFINITION.** The Stats ->
Teams table had the same problem as the other two views: **Norfolk St. ranks
2nd in points/set and 1st in fewest points allowed, both off one Division-II
match**, and the panel note underneath warned about non-D-I opponents in
general without saying which row it meant. A blanket sentence under a sorted
table does not qualify a row; the row is what a reader compares. Marked per
row.

Writing it a third time is how copy drifts, and it already had: the table
tooltip read **"1 of these 1 matches is"**. All four surfaces now call one
`nonDiPhrase(n, total, where)` -- `where` is "on file" / "here" / "in this
sample" so one sentence reads naturally in each. Guarded: exactly one
definition, at least three call sites, and no call site rebuilding the wording
by hand.

## ⚠ THE MISTAKE I MADE DOING IT -- READ THIS BEFORE EDITING build_hub.py

Consolidating those call sites, I replaced one block using **`s.index()`
arithmetic** instead of an exact-string replace: `s[:start] + new + s[end:]`,
where `end` was found by searching for a short, NON-UNIQUE fragment
(`'</div>'\n      : '') +`). It matched a much later occurrence and the splice
**deleted 1,787 lines** -- all of My Board, all of Live Match Center, and more.

**Nothing about it looked wrong.** The build completed. `node --check` on the
extracted script **passed**, because what was left was still valid JavaScript.
The page loaded. It failed only at runtime, as `mbLoad is not defined` and
`lmcStop is not defined` in the console.

**Rules that follow, and they are cheap:**
- **Never splice this file by index.** Anchor every edit on an exact string and
  `assert s.count(old) == 1` before replacing. A fragment that is not unique is
  not an anchor.
- **Print the net size change after a scripted edit.** `+340 chars` is a patch;
  `-1,787 lines` is a catastrophe, and the number says which instantly.
- **A syntax check is not a completeness check.** Deleting whole functions
  leaves valid syntax.

⚠ **AND THE PART I HAD TO MEASURE RATHER THAN ASSUME:** would the suites have
caught it? **Yes -- 3 of 24** (`test_ballot`, `test_pipeline_fresh_checkout`,
`test_player_aggregation`), verified by reproducing the deletion and running
them. Unlike the `esc()` breakage above, this damage class **is** covered. I
had simply looked at the page before running them. Run the suites first; they
are faster than a browser round-trip.

⚠ **A guard can fail against a page that is working.** Consolidating onto the
helper removed the literal sentences the guard was matching ("Her only match on
file"), so four checks failed on a correct page. **Assert the pieces and the
branches, not one implementation's literals.**

**8. A TEAM'S RECORD HAD TWO DEFINITIONS, AND A COMMENT SAYING IT COULDN'T.**
The biggest of today's findings, and it came from following the same thread one
view further. `standings()` has always dropped non-D-I opponents -- **correct,
and the NCAA's own convention**: the official RPI `Record` column excludes them
and breaks them out as `Non-Div I`. But `record26` counted every match. So:

| surface | Norfolk St. showed |
|---|---|
| team header chip | `2026 1-0` |
| team page glance | `1-0, 1 played` |
| standings row | `Overall 0-0` |
| standings Form | `W` |

**A win with no matches, and a chip contradicting a row on the same site.** The
comment above `_w26` claimed all of it came from "one source, so the four
cannot disagree". They shared an **input**, not a **definition** -- which is R4
in its purest form, and the comment made it harder to see, not easier.

Now: the record is Division-I-only everywhere, and the non-D-I result is
**shown beside it** rather than dropped in silence -- `0-0 +1-0 nD1` in the
standings, `0-0 · 1-0 vs non-D-I` on the team page, `2026 0-0 +1-0 nD1` in the
header chip, and the form pill's tooltip names the division for the W the
record does not count. `record26_nondi` is its own field so no consumer has to
re-derive it and none can fold it back in.

⚠ **All five consumers of `record26` were audited before changing it** (R4),
not after: the header chip, the glance card, the ballot comparison row, the
ballot brief line, and the Digby-facing bits line.

**Guarded** in `test_player_aggregation.py` 5c: every team's record must equal
its own standings row, and the non-D-I split must agree on both surfaces.
**Negative control**: restoring the all-matches count makes it fail with
`Norfolk St. chip=1-0 standings=0-0` -- the exact bug, named.

⚠ **AND THE POSITIVE CONTROL EARNED ITS PLACE ON THE FIRST RUN.** `TEAMS` is
keyed by name and its values carry **no `team` field**, so my cross-check
compared **zero teams** and reported "every team's record matches its standings
row -- ok". Only `[+] ...and teams were actually compared` caught it. **Every
cross-check needs a check that it compared anything at all**; without one, the
emptier the comparison the greener it looks.

**9. TWO CLARITY SEAMS CLOSED, AND BOTH WERE DECISIONS RATHER THAN BUGS.**

**(a) A hover title is not a label.** The non-D-I form pill explained itself
only in a `title`, which does not exist on a phone, is not announced while
scanning a column, and cannot be seen in a screenshot. The marker is now TEXT
on the face of the pill -- `W nD1` -- and the pill is **outlined rather than
filled**, so a result the record excludes separates from one it counts before
you read either. The long sentence stays in the title for anyone who does hover.
⚠ **`.fw`/`.fl` IS A FIXED 19x19 BOX**, so the suffix overflowed it -- measured
at a 358px phone width, `scrollWidth` past `clientWidth`. The marked pill gets
`width:auto` with height and line-height held at 19px, so it still shares a
baseline with the pills beside it. Both facts are guarded.

**(b) THE `+/-` BASIS IS NOW DECIDED AND STATED: DIVISION-I ONLY.** It was
built from `team_season_stats()`'s `own`/`opp`, which count **every** opponent,
and sat beside a Division-I-only record -- so Norfolk St. read
**`Overall 0-0 ... +9.67`**, a differential earned in the very match the record
on that row excludes. Two bases in one row.
The differential now comes from `own_di`/`opp_di`, **accumulated in the same
pass** as the all-opponent totals so the two cannot drift, and the column header
carries a visible `D-I` stamp rather than hiding the basis in a tooltip. A team
with no Division-I match yet shows **an em dash**, not a borrowed number --
which is what Norfolk St. correctly shows today.
**The team page's "Team stats, 2026" box deliberately keeps every opponent** --
a different view with a different job -- and says so in its own note. The two
are not in conflict; each states its basis.

⚠ **THERE ARE TWO FORM BUILDERS AND I ONLY FIXED ONE AT FIRST.** A Python one
(server-rendered) and a JS one built from `RESULTS`. `formPills()` uses the JS
one, so the first patch changed nothing visible. The JS side cannot ask
`TEAMS` whether an opponent is Division I -- `TEAMS` is declared near the END of
the script and reading it from a `const` initialiser throws
`Cannot access 'TEAMS' before initialization`, the same dead zone that has
already broken routing and My Board here. It is fed an explicit
`NONDI_OPP` set instead: no ordering hazard, and it is one name today.

⚠ **KEEP A USER-VISIBLE SENTENCE IN ONE STRING LITERAL.** The pill's
explanation was written as `'...it is not ' + 'counted in the...'`, so the
phrase never appeared contiguously in the built page and the guard looking for
it failed against correct output. Joined.

⚠ **AND `elementFromPoint` ONLY WORKS INSIDE THE VIEWPORT.** It reported the
marker as unpainted at both widths; the row was at y=5440. Scrolled into view,
it returns `I.fndt` "nD1". **Third time this session that a geometry read
disagreed with the pixels and the pixels were right.** Screenshot confirms it.

**Guards** (`test_display_invariants.py`): the marker must be rendered text and
must be conditional; the pill must be widened if `.fw/.fl` is a fixed box; a
phone-breakpoint rule must exist for it; `+/-` must read `own_di`/`opp_di` and
must NOT read `own`/`opp`; the header must carry the visible stamp; a
split-record team must exist to test; such a team must not carry a D-I
differential with no D-I match; and no row's `diff_n` may exceed its own
`w + l`. **Three negative controls, all verified to trip**: reverting the
basis, removing the visible text, and removing the width override.

## 10. RANKINGS INTELLIGENCE BOARD

**What was wrong.** Thirteen equal columns, five of them bare ranks from five
different organisations, so one row read **`#1 #1 #1 #1 #1`** with nothing on
screen saying whose ruler each number was. Five equal buttons implied the
committee's Top 16 and the NCAA's RPI were the same kind of thing as our own
order and the coaches poll.

**Decisions.**
1. **Three rulers at full weight** -- POWER, AVCA coaches poll, Digby's Top 25
   -- plus a **POWER vs AVCA** comparison. The committee Top 16 and NCAA RPI
   moved behind a restrained `Reference` select. Every selectable ruler has a
   one-line purpose sentence from **one map**, so a view cannot ship without
   one; Digby's explicitly disclaims being the poll or anybody's ballot.
2. **The POWER board defaults to seven columns** -- rank, team, conference,
   POWER, Resume, Record, AVCA -- with the seven reference/outlook columns
   behind a `Reference columns` checkbox. **Record is Division-I only** with
   the non-D-I split beside it, reusing the rules finished earlier today.
3. **Rows route.** The in-place expansion is gone; a row opens the team page,
   where the projected six already lives. Keyboard reachable.
4. **The comparison surface states a difference and nothing else.** No
   "overrated", no recommendation, no verdict. A team the poll does not rank is
   listed as **AVCA NR with no number** -- an absent rank is not a low one.
5. **Movement unchanged**: still nothing drawn, because there are only two
   snapshots and they are on different bases.

**⚠ THE BUG A SCREENSHOT CAUGHT AND MEASUREMENT DID NOT.** The first phone
layout put conference, resume, record and AVCA in ONE named grid area. **CSS
grid stacks items that share an area**, so all four painted on top of each
other and the row was unreadable. Every measurement passed: the row did not
overflow, the cells were "visible", the labels were present, `data-l` resolved.
One look at the pixels showed it instantly. **Fourth time this session that a
geometry read disagreed with the screen and the screen was right.** Each cell
now has an explicit row/column and a guard asserts no two share a slot.

**⚠ A SELECTOR THAT WAS UNIQUE UNTIL IT WASN'T.** `renderPoll()` reached for
`#v-rankings .panel`. That was unique until the comparison view began injecting
panels into `#pollview`, which sits EARLIER in the section -- so the selector
silently returned the wrong element and switching back to POWER toggled the
comparison surface. Addressed by id now (`#rankpanel`). Same shape as the
duplicate-id bug that made the just-finished band query the schedule tbody.

**⚠ THE GROUP HEADER MUST HIDE WITH ITS COLUMNS.** Hiding the reference columns
left 9 group spans over 7 columns. Ret and Tourn are *ours* and keep their own
"Our outlook" group rather than being swept under "none of it feeds our
model" -- that would be a false label -- but they hide together.

**⚠ TWO MORE OF THE RECURRING TRAPS, BOTH CAUGHT BY POSITIVE CONTROLS.** The
phone-CSS regex matched the FIRST of several `max-width:560px` blocks, so every
placement check failed against correct CSS while "no two cells share a slot"
passed **vacuously on zero slots**. And the ruler-purpose check swept EVERY
`<option>` on the page -- conferences, Top-50, stat pickers -- demanding a
purpose sentence for each. **A cross-check needs a check that it compared
anything at all**, now for the third time today.

**⚠ AND A GUARD FOUND MY OWN COMMENT AGAIN.** `public: no "My Board"` failed on
a source comment written hours earlier explaining the temporal dead zone.
Structural markers (markup, storage keys, functions) are asserted against the
raw page; human-facing names are scanned with comments stripped.

**Guards:** `scripts/test_rankings_board.py`, 25th suite, wired into both
workflows -- every ruler labelled; gap arithmetic recomputed independently and
never assigned to an NR team; ten recommendation words banned; inactive Resume
explicitly off; phone cells cannot share a slot; reference columns hidden at
560px; every row routes to its own team at its own rank; no fabricated
movement; public build free of ballot/My Board material and its header still
aligned. **Five negative controls, all verified to trip.**

**Deliberately deferred:** rank movement and any trend line stay unavailable
until two same-basis weekly snapshots exist -- that is the honest state, not a
gap. Resume stays inactive until 200 D-I matches. No consensus/blend ranking
was added.

## 11. WEEKLY RANKINGS CALENDAR

**THE CUTOFF POLICY, IN ONE PLACE (`scripts/weekly.py`).** A **Digby Weekly**
covers every completed match dated **on or before the prior Sunday, EASTERN**,
and nothing after it.

- **Eastern, not Pacific.** The sport schedules in Eastern and the AVCA's own
  "Through Games" stamp is an Eastern date. The hub still DISPLAYS Pacific for
  Cody; that is presentation and does not move the cutoff.
- **Monday is excluded even when finished.** It belongs to the next freeze.
  That is what makes the archive comparable to a poll.
- ⚠ **A HAWAII MATCH AT 7pm HST SUNDAY IS 1:00am EASTERN MONDAY and is
  therefore next week's.** Same for a 9pm-Pacific Sunday match. A real
  consequence of one zone rather than per-venue local dates, which we do not
  have and will not guess. Tested explicitly.
- **Non-D-I fixtures cannot hold the poll open.**

**WHAT HAPPENS WHEN LATE RESULTS ARE UNRESOLVED.** Nothing is written. The
calendar shows a waiting state naming the count and the reason: `live`,
`unresolved`, or `stale`. **It is live right now** -- the Aug 23 cutoff has 7
finals and **39 stale**, which is the known phenomenon where ncaa.com removes
fixtures from a past date (10 of the 12 crawled for Aug 21, 29 more on Aug 22).
Those records can never resolve, so **that week will not freeze on its own.**
Clearing it is a deliberate act (`snapshot_rankings.py --force`), and a forced
row is stamped `completeness: "forced"` with the count it overrode, so it can
never be mistaken for a complete one.

**Ordering.** The freeze runs after this job's own crawl and after
`refresh.yml` (22:00-11:00 UTC) has had the overnight hours to collect late
Sunday finals; a **new Monday 20:15 UTC run** is the second chance and also
catches the AVCA poll, which publishes Monday afternoon Eastern -- after the
09:15 run, and the endpoint is current-only, so a missed poll can be gone.

**Three tracks, never blended:** Digby Weekly `Derived`, AVCA `Official`,
community poll `Community / manual`. Movement stays inside a track.

**VolleyTalk is manual-import only** (`data/volleytalk_polls.json`, empty).
Nothing scrapes, logs into, or posts to it, and a guard proves no rating,
projection, board or ballot module reads the file.

⚠ **THE PUBLIC GATE CAUGHT ME THREE TIMES ON THAT TRACK** and was right every
time: first shipping it, then gating only the RENDER while the literal name sat
in the page script, then on **two of my own comments**. Comments are bytes on a
public page. The track is not BUILT for the public page, and its name and copy
live in the private-only payload so the public JavaScript has nothing to strip.

⚠ **I BROKE MY OWN RULE FROM SECTION 10 AND SPLICED BY INDEX AGAIN**, leaving a
duplicated `: '')` that took the whole page down with `Unexpected token ':'`.
`node --check` on the extracted script catches this in one second and is now
part of the routine after every build.

⚠ **AND I WROTE A ROW INTO THE REAL ARCHIVE** while testing `--force`. Restored
from git, verified byte-identical. `snapshot_rankings.py` now honours
`WVB_HISTORY_OUT` so tests can never touch the one artifact that cannot be
rebuilt.

**Week 35 is preserved exactly** -- 35 teams, no cutoff back-filled -- and the
calendar labels it `partial` / `archived` rather than pretending otherwise.

**Guards:** `scripts/test_weekly_calendar.py` (26th suite) -- Sunday final
included, live/unresolved/stale each block, Monday excluded, the Hawaii case,
non-D-I cannot block, visible cutoff label, 348-team snapshot with every field,
no duplicate cutoff, W35 intact, AVCA once-per-stamp, Monday cron present, and
the community poll reaching nothing. **Four negative controls, all verified to
trip.**

## 12. FIXTURE TRUTH LEDGER

**THE PROBLEM.** The weekly gate treated every non-final fixture as pending, so
the 39 records ncaa.com had already removed from Aug 21-22 blocked Week 34
permanently. A gate that always needs `--force` is not a gate.

**THE EVIDENCE RULE (`scoreboard-absence-v1`), and it contains no invented
threshold.** A non-final fixture is `source_withdrawn` only when ALL of:
1. its Eastern date is strictly past;
2. we hold a saved scoreboard observation of that exact date (all 139 are
   committed, so every verdict is reproducible from the repo);
3. that observation was taken at or after the fixture's own scheduled start;
4. **every game the observation lists is FINAL** -- the source has finished
   with the date; and
5. the fixture is absent from it.

Point 4 is what replaces "it is old enough". A cutoff in hours would have been
a number I chose, which is exactly the kind of threshold that makes a verdict
meaningless (R1). ⚠ **The observation stamp is read as UTC, the conservative
choice** -- it places the observation earlier in Eastern terms, so an ambiguity
in the source can only withhold evidence, never manufacture it.

**FINAL DISPOSITION COUNTS (2026):** `source_withdrawn` **41**, `final` 9,
`scheduled_or_live` 4,803, **`unknown` 0**. Through the Aug 23 cutoff: 39
non-final, **all 39 evidenced**, none assumed.

**WEEK 34 FROZE NORMALLY -- no `--force`.** 348 teams, 7 finals included, 39
source-withdrawn excluded, state `complete_with_withdrawals`.

**Three states, and publishable is not complete.** A week whose only gap is
documented withdrawals does not get to say "complete". A forced row is stamped
`forced` forever with the count and reasons it overrode.

⚠ **NOTHING ELSE STOPS BLOCKING.** Live, pending, unknown, no observation,
observation too early, source not finished with the date, still listed -- all
still block. With no ledger present the gate behaves exactly as before.

⚠ **THE SAME ALIAS DRIFT APPEARED FOR A THIRD TIME.** `"digby"` vs `"blend"`
is one ruler under two spellings. `SOURCES` did not list `blend` even though
the writer could already emit it; the Top 25's movement matched the string
exactly and so ignored the first real weekly freeze, still printing "vs
preseason" with a prior week sitting in the archive; and my own new guard
counted raw strings. All three now go through `snapshot_rankings.basis()`.
**Week uniqueness is per TRACK**: a weekly freeze keys on the Sunday it covers,
the legacy rows on the day they were captured, and both can read "2026-W34".

⚠ **TWO TESTS ASSERTED THINGS THAT STOPPED BEING TRUE, AND BOTH WERE RIGHT TO
FAIL.** "The Top 25 names its biggest movers" -- with the freeze taken from the
same data the board shows, nothing had moved, and printing a movers line would
have been inventing movement to satisfy a test. And an alias negative control
**expires by design** once a canonical row exists. Both now assert the honest
invariant instead.

**Guards:** `scripts/test_fixture_disposition.py` (27th suite) -- final
included; live blocks; date-not-passed blocks; **old-with-no-evidence blocks**;
observation-too-early blocks; source-not-finished blocks; still-listed blocks;
evidenced withdrawal does not block and stays visible; one unknown blocks the
whole week; Monday/Eastern/Hawaii unchanged; the real 39 carry evidence; the
ledger writes exactly one file and deletes nothing; no suite can touch raw logs
or the real history. **Four negative controls verified to trip.**

## 13. LIVE MATCH TRUTH / BOX SCORE READINESS

**THE AUDIT IS WRITTEN DOWN: `docs/live_endpoint_audit.md`.** Measured against
real fixtures, not inferred.

⚠ **BEFORE FIRST SERVE `/game/{id}/boxscore` RETURNS HTTP 502 WITH AN HTML
ERROR PAGE** -- not a 404, not an empty document. Three upcoming ids, all 502;
a final on the same run returned 200 JSON with full team and player lines. Any
caller assuming a JSON body throws.

⚠ **AND THE SCOREBOARD SERVES `score: ''` BEFORE FIRST SERVE -- AN EMPTY
STRING.** `Number('')` is 0, so a careless read renders an unplayed match as
0-0, indistinguishable from a real 0-0 at first serve. **`live_server.py` had
exactly this bug**: `a.get("score") or "0"`. Fixed; the absence now passes
through and the state model decides.

**ONE STATE MODEL (`scripts/match_state.py`), SIX STATES**, with a capability
table saying what each may display: `upcoming · live_score_only ·
live_with_team_stats · final_box_pending · final_with_box · unavailable`. The
rules live in Python and the table is **handed to the page** -- three renderers
each deciding for themselves is how a finished match once sat in "Coming up".

⚠ **CAPABILITY IS A CEILING, NOT A PROMISE.** `final_with_box` permits player
lines, but a box score carrying none still forbids the table. A live match
never unlocks player lines at all. **A stale live row never beats a stored
final** -- `resolve()` takes the strongest evidence, never the most recent.

**`final_box_pending` renders as itself**: a bordered "the official box score
has not been published yet", never an empty table, zeroes, or invented leaders.

**ONE CANONICAL MATCH URL.** `matchRoute()` is the only builder and the click
handler matches **any** `[data-match]` element. Team result rows now carry the
game id and open the match -- previously five surfaces routed and a team's own
result, the likeliest place to want the detail, dead-ended. Keyboard parity
added.

⚠ **A MEASURED LAYOUT BUG THAT HIT EXACTLY THE TEAMS THE LAST PHASE SURFACED.**
`.rbside` is a FOUR-column grid and `logo()` returns `''` for a team we hold no
crest for -- so the row had three children, **every cell shifted one column
left**, the name rendered inside the 34px crest track at three lines and 91px
tall, and the score sat stranded beside it instead of at the right edge.
**Every non-Division-I opponent was affected.** An always-emitted placeholder
holds the column open; name height 91px -> 31px, score right-aligned. Guarded.

**Not measured, and said so:** no D-I match has been in progress during any
probe window, so `live_score_only` and `live_with_team_stats` are covered by
fixtures only, as is `final_box_pending` (all 9 stored finals have box scores).
**The standing rule stands: nothing may claim live statistics are available
until `probe_live_boxscore.py` has run against a live match** -- Friday
2026-08-28.

**Guards:** `scripts/test_match_state.py` (28th suite) -- all six states
resolve and are distinct; a final is never upcoming (five feed shapes); `''` is
not 0; nothing displays above its state; a live match never unlocks player
lines; a stale live row never overwrites a final; the page's table matches
Python exactly, state by state; a final without a box shows no table and no
zero-filled fallback; every entry point uses one route; box-score totals
reconcile (18 team boxes); the ribbon keeps its column count; and the audit
states its own limits. **Five negative controls verified to trip.**

**State at close:** 28 suites pass with `Cody/` present and 24 with it moved
aside. Tree is clean apart from the three fixes above. Nothing here changes
data, ratings, or the crawl -- all three are display-layer only.
