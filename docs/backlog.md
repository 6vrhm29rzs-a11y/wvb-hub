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

**106 with a different match count — WORKED DOWN TO 92.** Agreement with
Evollve now reads **256 exact · 0 winner mismatches · 92 count mismatches**
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

### Twelve teams both external boards disagree with us about (2026-09-12)
Three-way rank comparison, all current through 2026-09-11 (346 teams on all
three boards). Agreement, as median rank gap:
  POWER vs Evollve 10 · POWER vs Massey 16 · **Massey vs Evollve 14**
The two external boards disagree with each other MORE than we disagree with
Evollve, so POWER is not the odd one out. But twelve teams are placed 40+
places apart by BOTH of them in the SAME direction, which is the shape a real
defect makes:
  we rate HIGHER: Miami (OH) 100 (M179/E142) · Fairfield 106 (178/161) ·
    Duquesne 115 (186/170) · N.C. A&T 148 (209/202) · UMBC 113 (173/166) ·
    FIU 127 (183/173) · Col. of Charleston 94 (142/140) ·
    Kennesaw St. 120 (160/162)
  we rate LOWER: New Mexico 219 (155/163) · Wright St. 140 (88/93) ·
    UC San Diego 210 (165/159) · Wake Forest 170 (130/117)
Both of theirs are point-level efficiency ratings and POWER is margin-based
with an RPI component, so some of this is method rather than error. **Worth
checking whether these twelve share anything — schedule shape, a common
opponent, a bad result — before concluding either way.**

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
- **Evollve metrics we can replicate and have not:** Srv Avg, ace rate,
  service-error rate, reception success rate, % of points won, Pythagorean
  win % and Luck, rally-denominated kill/block/dig rates, and a matchup
  score. All computable from data already on disk.
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
