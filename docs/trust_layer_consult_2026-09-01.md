# Trust-layer consult — ChatGPT, 2026-09-01

Cody's directive after the IU–Georgia live inversion: *"ask chat gpt for
guidance and brainstorming solutions for this. this errodes the trust layer."*
Two conversations, in his Chrome (the second on his logged-in account with
the GitHub connector).

## Consult 1 — the attribution-inversion defect class

Framed the problem correctly as **attribution integrity, separate from score
integrity**: our coherence layer asks "is this record self-consistent?", the
defect is "is this permutation of a self-consistent record the right one?"
Warned the neutral-site correlation is a strong correlation, not a confirmed
root cause.

**Detection — test permutations, not contradictions.** For each record score
two hypotheses (H0 attribution correct / H1 sides swapped) against evidence
the linescore can't see:
1. Cumulative W-L record deltas (independent of the linescore).
2. Season game-graph consistency — reciprocal `X beat Y / Y beat X` edges on
   one date are a loud anomaly; catches the defect before records propagate.
3. Player/roster attribution under both hypotheses (box rows matching the
   opposing roster = WHOLE_SIDE_PERMUTATION_CANDIDATE).
4. Player season-total continuity (pre-match total + match line ≈ post-match
   published total, under each assignment).
5. Neutral-site / nominal-home≠host as a prior — and an epidemiological test:
   measure the inversion rate in that population vs ordinary fixtures.
Combine as a logged, component-by-component suspicion score (starting
weights stated, not gospel; log each component so a reviewer sees WHY).
**Optimize for high-quality review candidates, zero automatic corrections.**

**Live data — downgrade the claim, don't "fix" it.** Under suspected
inversion you don't know who leads; distinguish *feed state* from *trusted
state* and say "feed reports" rather than asserting. (We went one step
further the same evening with a CITED display swap — and its trap fired:
see below.)

**Two-source rule traps:**
- *Non-independence*: a school page that itself syndicates NCAA stats is not
  a second source; record backend provenance, not just two URLs.
- *Temporal conflict*: two sources at different revisions is
  TEMPORAL_CONFLICT, not CONFLICT — keep observed_at vs event_time.
  **This fired live within the hour**: the NCAA feed self-corrected at final
  by swapping its team names back, and our standing numeric swap re-inverted
  a correct record for one poll cycle. Fix: the swap is conditioned on the
  exact feed orientation the evidence described (`applies_when`).
- *Per-field authority*: a school's final is authoritative for winner/score,
  not necessarily for every stat column.

**Evidence architecture:** claims + evidence with provenance (source,
captured, supports), corrections as a higher-level interpretation over an
intact raw observation — "at 7:42 we displayed what the feed said; at 9:13
two independent official sources established the inversion."

## Consult 2 — the nightly result verifier

- **Primary surface: SIDEARM `/sports/<sport>/schedule/text`** — structured,
  carries `W 3-1` results and an explicit Home/Away/Neutral column; both
  IU and Georgia expose it. Don't anchor on undocumented JSON APIs;
  `/services/sportnames.aspx` discovers sport paths. WMT: statistics game
  JSON, else box-score HTML. Presto: schedule pages include exhibitions —
  the non-counting distinction must survive ingestion.
- **One adapter architecture, not 348 parsers**: vendor+surface adapters
  returning one normalized shape; school config only for exceptional routing.
- **Matching**: opponent identity dominates the date (doubleheaders); event
  titles are never opponents; strip rank prefixes (#7 / No. 7 / RV).
- **States**: AGREE_COMPLETE / AGREE_PARTIAL / CONTRADICTS / NOT_POSTED /
  EVENT_NOT_FOUND — "not posted yet" must never read as disagreement.
  One school agreeing = PARTIAL_CORROBORATION, never verification. Two
  schools agreeing against the feed = the review candidate that satisfies
  the two-source rule (both citations captured); a human still files it.
- Both schools' text pages independently mark IU–Georgia **Neutral** — event
  identity can ignore the feed's home/visit labels entirely.

Implemented same night: `scripts/verify_results_daily.py`,
`scripts/test_verify_results.py`, wired into `daily.yml` (tolerated step).
First live run: 13 finals, 1 VERIFIED_BOTH / 4 CORROBORATED_ONE /
0 contradictions; per-school 6 agree · 3 not-posted · 11 unparsed (JS
schedule pages — next adapter rung) · 5 unreachable · 1 event-not-found.

## Consult 3 — the architect error-hunting plan (2026-09-02)

Trigger: the live composite seized the board at median 3 games/team
(meta.validated proves validation RAN — the wrong property). Fixed with the
measured maturity gate (median gp ≥ blend k) before the consult; the plan
targets the class.

Ranked sweeps, with status:
1. **Cross-surface truth reconciliation** — per-team TruthSnapshot from the
   season_counts contract vs every reader-facing aggregate.
   BUILT (`test_cross_surface.py`); first run found the fifth New Orleans
   bite (res rows carried the feed's raw spelling; standings counted every
   New Orleans match non-D-I for the opponent). Fixed via `_hub_name()`
   against the membership authority.
2. **Generation-fingerprint coherence** — fail publication when
   truth-bearing artifacts disagree on the canonical games/corrections
   fingerprint. PARTIAL (audit manifest holds totals); full per-artifact
   stamping is open.
3. **Lead-vs-table contradictions** — re-derive every generated summary
   sentence from the rows rendered beneath it, never via the helper that
   wrote it. BUILT (`test_lead_vs_table.py`), four leads covered; all hold.
4. **One-record-log semantics** — classify every jsonl reader (event log /
   snapshot / archive) and check the discipline. AUDITED: all seven
   playerbox/boxscores/lineups readers key by gid last-wins. Clean.
5. **Permutation beyond scores** — the swap-coherence question applied to
   any two-sided structure (player rows, set lines, records_at_time,
   starters). PARTIAL (detector covers teams[]/box/records); starters and
   set-line orientation open.
6. **Ledger/archive internal consistency** — each archive row consistent
   with its own captured ruler, never current artifacts. OPEN.
7. **Architecture** — named certified properties
   (`certifies: {ordering_mature_for_public_rank: …}`) with
   `require_property(consumer)`; no generic booleans crossing subsystem
   boundaries, no property satisfying another by implication. OPEN — the
   structural answer to the wrong-property-gate class; needs a design pass.

Web finding worth its own line: **henrygd/ncaa-api v3 moved off the old
Casablanca endpoints to NCAA's new GraphQL backend (sdataprod.ncaa.com),
propagating upstream `team.isHome`/`team.isWinner` directly.** The
inversion epidemic is therefore plausibly NCAA's own structured data — not
established (no public issue reports it), but it reframes the defect as
upstream-attribution, which is exactly what the school-site verification
layer exists to catch.
