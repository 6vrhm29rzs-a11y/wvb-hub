# Backlog — notes, errors and observations to work later

Cody's mid-session observations get logged here rather than interrupting the
task in hand (his instruction, 2026-09-12). His offhand notes have repeatedly
turned into the largest measured gains on this project, so nothing is dropped:
an item leaves this file only when it is done or is written up somewhere
better, and each one records what was observed and what is actually known.

---

## OPEN

### CLOSED 2026-09-13 — the top-50 verification gap
The 13 top-50 programmes with no readable schedule are readable now. All of
them run the same platform, whose own page fetches a plain JSON API on the
school's domain (`/website-api/schedule-events`, sport id read per site from
`/website-api/sports`). **12 of the 13 answer it** — Kentucky is the
exception: `ukathletics.com` redirects `/website-api/*` to a 2018 news page.
Measured across every school whose site had never answered usefully this
season: **16 of 31 now readable**. Still dark and worth a browser look one
day: **Arkansas, South Carolina, Southern California, Kansas St.** (that one
already reads through the completed-event label parser), Tennessee Tech,
Central Conn. St. The rest of the list is non-D-I and Cody has ruled it out.

### CLOSED 2026-09-13 — held matches are verified now
`finals_for()` skipped everything `classify()` did not call `ok`, so the
matches that count NOWHERE — the ones a school's own word could settle — were
never taken to the schools at all. Eleven held finals from 09-12 had no
verification record; nine now do, and every one of them is corrected and
counting. Held matches are OBSERVED (`HELD_BOTH_REPORT` / `HELD_ONE_REPORTS`
/ `HELD_NO_REPORT`), never verified: no canonical exists, so nothing can
agree with one and none of it can move a ranking.

### Kentucky's site is the one remaining unreadable top-50 programme (2026-09-13)
`/website-api/*` 301s to `https://ukathletics.com/news/2018/08/08/sports-video/`.
Its schedule page does render results, so the data is fetched from somewhere —
the next step is one browser look at the network panel on
`ukathletics.com/sports/wvball/schedule` to see which endpoint it calls.


### Record disagreements vs Evollve — WORKED (2026-09-12)
Reconciled team by team through a 2026-09-11 cutoff, with the counting chain
applied. **238 exact · 4 winner disagreements · 106 different match count.**

The four winner disagreements were settled at the SCHOOLS, and they did not
all go one way:
- **Kansas St. / Weber St.** (one match, gid 6627513) — WE WERE WRONG. The
  feed inverted the teams; both schools say Kansas St. won 3-1. **Correction
  49 filed.** Kansas St. 4-1→5-0 (rank 55→45), Weber St. 6-1→5-2 (145→175).
  ⚠ It was reported in the 2026-09-11 Night Desk email as the night's third
  upset, "Weber St. #163 def Kansas St. #46". That upset did not happen.
- **Cleveland St.** (ours 2-5, theirs 3-4) — EVOLLVE IS WRONG; csuvikings.com
  matches us exactly.
- **Mississippi Val.** (ours 1-5, theirs 0-6) — EVOLLVE IS WRONG;
  mvsusports.com carries the Wiley win we count.

**106 with a different match count — WORKED DOWN TO 87.** Agreement with
Evollve now reads **261 exact · 0 winner mismatches · 87 count mismatches**
(from 238 · 4 · 106 this morning). 13 matches were restored by going to the
schools for finals the feed had served with no usable result; 6 more by
resolving lapsed conflicts. What remains is below.

**The 92 still open.** Sampling says they split three ways: our diff's name
matching (fixed — compare match COUNTS PER DATE, never names), genuine feed
gaps (App State–UNCG on 09-05 appears in no scoreboard file we hold), and
Evollve counting something we do not. The date-level differ (/tmp/datediff.py
pattern) is the tool; it should be made permanent and pointed at all 92.
Earlier notes: Six of them turned out
to be results sitting in an expired conflict or an inverted feed record, all
now corrected (see below). Sampling six teams against their own schedules
found the rest split three ways: some are our diff's name-matching failing
("Binghamton University" vs "Binghamton"), some are genuine feed gaps (App
State–UNCG on 09-05 is in no scoreboard file we hold), and some are Evollve
counting something we do not. **Still open:** 80 of them are ours
minus theirs = −1 (they hold one more match than we do), 16 are +1. This is
an INCLUSION question, not a winner question, and it is the remaining lead.
The BYU case is the type specimen: they carry a seventh match we have never
seen in any state. Next step is to take a handful of the −1 teams and diff
our match list against the school's own published schedule, which is what
settled every case above.

### Passing stats: real data, not ours to take (2026-09-12)
VolleyTalk's `2026 Passing Stats Thread` carries genuine serve-receive
quality — per player per match on the sport's 0–3 scale, with reception
counts: `Stafford 2.10 (34)`, `Wisconsin 2.36 team`. This is the measure the
sport actually uses and the NCAA feed does not carry at all.

⚠ **Do not build on it.** It is hand-posted for a handful of matches by one
poster, and it comes from VolleyMetrics — a paid scouting platform (a post
in the thread says "VM has her in as Tonga-Davis"). It is someone else's
proprietary data shared informally in a forum. Read it, do not ingest it.

**What it taught us instead, and this is measurable.** Our own reception
number is BINARY — a reception is an error or it is not — so it counts aces
conceded and says nothing about the quality of the other 90%. Measured over
342 teams with 5+ matches: reception success correlates **+0.466** with win
rate, where hitting % manages **+0.789** and % of points won **+0.890**. Its
entire range is 0.871–0.977. That narrowness *is* the limitation. The page
now says so in the tooltip rather than letting a weak number sit beside
hitting % implying equal weight.
**If a passing scale ever becomes available legitimately, it is the single
biggest metric gap we have.**

### Ideas and sources from VolleyTalk (2026-09-12)
Scoured the board. What is worth having:

**A third results source: themonsterblock.com.** Built by a VT member
(kingofcrank), publishes every match with its FULL SET LINE by conference,
plus rankings, standings, team and player stats, and a daily 7 AM email.
⚠ **It is independently sourced, not a feed mirror** — proven on the match I
corrected today: it shows "Holy Cross 3 @ Manhattan 1 (18-25, 26-24, 27-25,
25-18)", Holy Cross's column matching my corrected line DIGIT FOR DIGIT while
the NCAA feed says Manhattan won. That makes it a genuine third check on
inversions, which is exactly what the two-source rule is short of. No
robots.txt; it is a hobbyist site, so read lightly and never crawl it hard.
**Next:** capture it the way Massey/Evollve are captured, and use it as the
second source for the matches whose schools do not parse (Little Rock, Wiley).

**"Almosts" — BUILT.** Their season-long upset thread tracks near-misses as
well as upsets, on the reasoning that those are what you want to look back
on. The night email now has a **CLOSE CALLS** section: a favourite ranked
40+ places higher that still dropped two sets. First night it fired on three.

**Upsets by poll rank vs by rating.** The room argues about whether a result
is *"an upset only in name recognition sense"* — they judge by AVCA rank, we
judge by POWER places. Both are defensible and they answer different
questions. **Idea:** show both in the email — the AVCA framing is the one
people actually argue about.

**Threads worth watching** (availability signals ONLY, never a status — a
post saying a player is out is a prompt to go and look):
`2026 Upset Alerts` · per-team threads (Nebraska, Wisconsin, Washington,
Minnesota, Tennessee, Hawaii, Iowa) · `Fall 2026 Match Threads & stream
links` · `2026 Passing Stats Thread` — passing/serve-receive quality, which
the NCAA feed does not carry at all and which we cannot compute.
Example caught today: *"a&m without stowers"*.

### The reconciliation is a permanent script now (2026-09-12)
`scripts/school_reconcile.py` diffs our counted matches against every school's
own schedule BY DATE. Full run through 09-11: **265 of 351 teams agree on
every date**, 48 differ, 38 sites unreadable.

Of the 48, most are **August exhibition dates** the schools list and we
correctly exclude (8/12–8/23), plus two non-D-I schools in the site list
(Fla. Southern, Southwest Minn. St.) whose schedules we never crawl.

**The real yield was three DOUBLE-COUNTED matches** — two feed records for
one meeting, both classed ok:
  South Dakota St.–Western Ill. · Indiana St.–Northwestern St. · Lafayette–FDU
All three now ledgered as duplicate listings, each on both schools' evidence.
⚠ The duplicate detector never flagged them; the per-date school
reconciliation did.

**38 unreadable school sites was the next lever — LARGELY PULLED
2026-09-13.** The platform JSON API reads 16 of the 31 that had never
answered, Nebraska, Stanford, Penn St., Purdue, UCLA, BYU, Georgia Tech,
Texas A&M, UCF, Vanderbilt, Clemson, Notre Dame, Virginia Tech, UTSA, San
Diego St. and San Jose St. among them. See the CLOSED note at the top for
what is still dark.

### One match the feed never finished (2026-09-12)
**6627939, Siena 3-0 Le Moyne, 2026-09-11.** Our record is still `state=I`
with the tally at 2-0: the feed stopped updating mid-match and never declared
a final. Both schools published it — Siena "Le Moyne W 3 0", Le Moyne "Siena
University L 0 3" — so it is a real result we are missing, and it costs both
teams a match.

⚠ **A result correction cannot rescue it**, because `classify()` only
considers records in state F; a correction on a non-final never reaches the
counting chain. Building a "the feed never finalised it" mechanism would be
the right move for a class — but measured across the whole season this is
**the only one**, so it is recorded here rather than engineered around.
**Revisit:** if the feed finalises it, it counts automatically and this note
can go. If it is still `I` in a week, that is the moment to build the
mechanism, not now.

### A local full sweep races the refresh loop (2026-09-12)
The sweep takes ~17.5 minutes; `live_server` rebuilds the whole chain every
20. So a local run very often has the counted corpus change underneath it,
and when it does the certificate suites and the season-count contract fail on
a **healthy** tree. That misdiagnosis cost three separate investigations
today. `run_all_guards.py` now fingerprints the corpus at both ends and says
plainly when it moved, so contention is distinguishable from regression
instead of being guessed at. For a genuinely clean sweep, stop the refresh
first (`WVB_LOCAL_REFRESH_SECONDS=0`) — CI does not have this problem because
it runs against a static checkout.

### CLOSED — Cody's priority call (2026-09-12)
> "I don't give a shit about d2. If a 300+ rank d1 team plays a d2 team and
> we don't have info from that match, I do not care. It doesn't affect the
> top 50 that I care about."

That settles three things that were sitting open as decisions, and they stop
being decisions:
- **Nicholls–Wiley** stays uncounted. Wiley is not D-I and no second source
  will ever exist. Not worth another minute.
- **Norfolk St.–Elizabeth City St.** stays as it is. One win, one team, rank
  329.
- **D-II fixtures on the board** (Tampa at West Florida): leave them. They
  cost a slate count of one and nothing that matters.
- The unreadable sites of **Little Rock, Central Conn. St., Wheeling, Fla.
  Southern, Southwest Minn. St.** stop being a priority.

⚠ **AND IT REDIRECTS THE REAL PROBLEM.** Measured the same day: **13 of the
top 50 cannot be second-sourced at all** — Nebraska, Stanford, Penn St.,
Purdue, UCLA, Kentucky, Arizona St., Auburn, BYU, Georgia Tech, Texas A&M,
UCF, Vanderbilt. Every one renders its schedule client-side, so no static
parser can read it and no second OFFICIAL source exists. **If the feed
inverts a Nebraska result, nothing currently catches it** — and that is
squarely inside what Cody cares about, unlike anything above.
**This is now the top verification priority.** The Monster Block is their
only independent witness today, so its cross-check flags a top-50
disagreement loudly and sorts it first. Confirming one still needs a human
in a browser, which does work — that is the escalation path.

### Two conflicts the two-source rule cannot settle by waiting (2026-09-12)
Both stay uncounted, both now carry a recorded recheck:
- **6628157 Little Rock – Northwestern St.** Northwestern St. publishes
  "Little Rock L 0 3", so Little Rock won 3-0 — but Little Rock's own site
  still does not parse, so it is one attributable source. The rule is not
  waived because a site is awkward; the fix is a working parser for that host.
- **6640584 Nicholls – Wiley.** Nicholls publishes "Wiley W 3 0" against the
  feed's Wiley 3-0. ⚠ **A second source may never exist**: Wiley is not a
  Division-I programme and has no entry in athletics_sites. This is the case
  the two-source rule cannot resolve by waiting, and it needs a decision —
  either a stated exception for a non-D-I opponent (where the D-I school's
  own record is the only record anyone keeps), or it stays uncounted forever.
  **Cody's call.**

### Twelve teams both external boards disagree with us about — WORKED (2026-09-12)
**Not a data defect.** Ran the date-level differ over all thirteen (the list
moved slightly after the day's corrections): **eleven of twelve agree with
their own school on every date.** The two exceptions are August 12/15/21/22 —
preseason exhibition dates the schools list and we correctly exclude. No
missing matches, no phantom ones, no wrong records.

So the disagreement is METHOD: our board is on the blend, which at a median
of 7 matches is still roughly two-thirds preseason projection, while Massey
and Evollve are entirely this-season. Measured: corr(our gap vs the external
consensus, the PRESEASON gap vs that consensus) = **0.598**. But it is not
simply the projection dragging us — of the 33 teams differing by 40+, **17
are closer to the externals than the preseason was**, so the season component
is already pulling us toward them.

**Whose ordering is better is now measured, not argued.**
`scripts/board_bakeoff.py` scores all three on finals that landed AFTER every
board's stated data horizon, and appends so the sample grows. First run, 55
held-out matches: POWER 76.4%, Evollve 70.9%, Massey 61.8%; paired, POWER
beat Massey 9-1 (p=0.021) and Evollve 6-3 (p=0.51, i.e. nothing).
⚠ **One day is not evidence** and the script says so. Run it daily; revisit
when n is in the hundreds.

### Norfolk St. – Elizabeth City St. (gid 6639821): counted, contested
The only gid all season whose feed state went **F → D**. Left counted, on the
strength of Norfolk St.'s own schedule showing `W 3-0` with no exhibition
marker. Everything else points the other way (every other D-state game is a
confirmed exhibition, same date, D-II opponent, and Evollve excludes it).
Worth exactly one win on one team's record. Recorded with both sides in
`data/raw/2026/state_reclassified.json`. **Cody's call.**

### NCAA feed can leave a whole wave of fixtures stale
2026-09-12 11:32 PT: 26 fixtures — the entire 11:00 AM wave, including
Kentucky–SMU and Creighton–Louisville — still `pre` 32 minutes after their
listed start, while 25 other matches were live and our poller was healthy.
Cody spotted it because he was watching the matches on another service.
**Done:** the row now marks `feed not updated · start time passed` instead of
showing a clean SCHEDULED. **Not done:** nothing recovers the live score
itself; the only automated source we have is the one that is stale.

### Still not pulled / built
- **Massey** and **FIGstats** captures are 13 days old (last 2026-08-30).
- **VolleyTalk**: the save pipeline now EXISTS (`ingest_volleytalk.py`,
  first thread stored 2026-09-12). Still to do: the weekly Top-25 poll is
  only current through Week 2 (2026-09-07) and Week 3 is out; and no routine
  captures the threads regularly — each one is a manual browser save,
  because the forum serves a bot challenge to every non-browser client.
- **Evollve metrics — SERVING IS DONE (2026-09-12).** Srv Avg (Evollve's own
  formula and constant, credited on the page), ace rate, service-error rate
  and reception success rate now compute per team and render on the team
  stats panel. Coverage measured first: 1,344 of 1,363 games carry serve
  attempts (98.6%), all-or-nothing per game; a team without them renders
  nothing rather than a zero. Guarded in `test_serving_rates.py`.
  **% of points won, Pythagorean and the actual win rate are DONE too**
  (2026-09-12). The exponent is FITTED — 8.559 on the complete 2025 season,
  349 teams, RMSE 0.049 win% against 0.198 for a model that calls every team
  .500 (`scripts/fit_pythagorean.py`, receipt in `data/pythagorean_fit.json`).
  ⚠ Our % of points won matches Evollve's published figure to a **median 0.22
  percentage points across 346 teams**, computed independently from our own
  linescores — which is a stronger check on our scoreboard data than anything
  self-referential, and it is now a standing guard.
  **Still to build:** rally-denominated kill/block/dig rates, and a matchup
  score like their EMS.
- **Cannot replicate without play-by-play** (2026 has none): Point-Scoring %,
  Sideout %, RAPM, and the two real Four Factors (serve-receive vs transition
  hitting). The serve/points algebra is genuinely underdetermined — one
  equation, two unknowns — so this is a data gap, not an effort gap.

### Older, still open
- Jersey number, name, position and photo on **every** page (Cody, "for later").
- Mobile cleanup items Cody noticed but has not enumerated.
- Newspaper tab rendering — foundation committed, awaiting an explicit
  "approved".
- Kennesaw St. – Alabama A&M: a counted final with an impossible 26-21 line;
  display withholds the tape but it still counts. Needs the evidence route.
- Massey/FIG gaps we do not compute: per-team home advantage, forward
  schedule strength, opponents' combined record, three RPI variants.

## DECISIONS WAITING ON CODY
- Should a **suspended** match get its own display state? (Wrigley,
  Nebraska–Missouri, currently renders on its own day with a SUSPENDED badge.)
- When the feed is **silent** on a final, should a cited pregame venue still
  render with its provenance? (Petersen Events Center.)
- Should the board hide **D-II fixtures** the feed serves (today: Tampa at
  West Florida)? They are why our slate count and the board's differ by one.
