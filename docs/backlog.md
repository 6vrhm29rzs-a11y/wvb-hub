# Backlog — notes, errors and observations to work later

Cody's mid-session observations get logged here rather than interrupting the
task in hand (his instruction, 2026-09-12). His offhand notes have repeatedly
turned into the largest measured gains on this project, so nothing is dropped:
an item leaves this file only when it is done or is written up somewhere
better, and each one records what was observed and what is actually known.

---

## OPEN

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

**38 unreadable school sites is the next lever.** Every one is a team whose
results can never be second-sourced, which is why Little Rock and Wiley sit
uncounted. Auburn, BYU, Kentucky, Kansas St., Arizona St., Clemson, LSU and
Cincinnati are among them — these are not obscure programmes, and a parser
that handles their templates would unblock verification across the board.

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
