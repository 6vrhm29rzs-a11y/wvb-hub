# Backlog — notes, errors and observations to work later

Cody's mid-session observations get logged here rather than interrupting the
task in hand (his instruction, 2026-09-12). His offhand notes have repeatedly
turned into the largest measured gains on this project, so nothing is dropped:
an item leaves this file only when it is done or is written up somewhere
better, and each one records what was observed and what is actually known.

---

## OPEN

### Records disagree with Evollve on ~115 teams (2026-09-12)
Reconciling our counting corpus against Evollve's published 348-team board:
**233 of 348 match exactly** at a 2026-09-11 cutoff. The residual is NOT one
cause — three are already ruled in or out by measurement:
- **Ruled IN:** they lag us by about a day (24 teams explained by today's
  results alone).
- **Ruled OUT:** exhibition handling. Including the `D`-state games makes
  agreement *worse* (226 vs 233), so they exclude them exactly as we do.
- **Ruled OUT:** non-D-I opponents explains only 7.
What remains is per-match, and at least some are winner-level disagreements
rather than inclusion differences (Norfolk St. is one win / one loss apart
from us on the same number of matches). **Next: a systematic per-match diff
against their board, not team-by-team.** That is the error-finding pass.

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
- **VolleyTalk**: only the weekly Top-25 poll is saved, through Week 2
  (2026-09-07). Week 3 exists. The forum *posts* — the actual ask — have
  never been persisted; extraction worked weeks ago, the save pipeline and
  its privacy fencing were never built.
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
