# Reliability Architecture Audit — 2026-08-31

Objective: prove or falsify, for every counted 2026 match, the chain

    raw append-only feed records
    → fixture / result corrections, duplicate & exhibition classification
    → ONE canonical resolved match by gid
    → ONE counting classification
    → ONE versioned derived snapshot
    → every consumer surface.

This document is the audit record. §2 (reader map) and §3 (bypass
inventory) were produced BEFORE any code changed.

## 1. The canonical contracts

These are the contracts the system already asserts piecewise; the audit
states them once and tests them as a set (scripts/test_fixture_corpus.py).

**C1 — Canonical resolved match.** For a gid, the resolved match is the
LAST final record in the append-only log (final-beats-non-final, then
last-wins: gamelog/build_dataset), with `season_counts.apply_correction`
applied. Winner, per-side sets_won and the linescores come from this and
nowhere else. A correction replaces non-empty feed linescores only when
it carries `linescores_replace`, justified by two-source evidence.

**C2 — Canonical box attribution.** Player/box rows belong to the team
the feed says EXCEPT where a correction carries `box_team_swap`
(season_counts.box_team_swaps); every derived consumer of box rows
applies the same map at read. The raw log is never rewritten.

**C3 — One counting classification.** Every completed record wears
exactly one class from `season_counts.classify`, precedence:
duplicate → exhibition → under_review → empty → ok.

**C4 — Visibility.** `results_on_display = ok + exhibition +
under_review` (badged); duplicates and empty finals are Result-Ledger
-only. A raw record stays auditable in the ledger but cannot re-enter
counted math.

**C5 — Rating eligibility.** ok ∧ both sides D-I ∧ per-set line
(`season_counts.countable(need_line=True, d1_only=True)` /
`totals()["rating_eligible"]`).

**C6 — Displayed record eligibility.** A team's W-L counts `ok` matches
against D-I opponents only (official RPI convention). Form pills and
standings derive from the same list as the record (the res builder), so
they cannot disagree.

**C7 — Evidence / provenance state.** `confidence.field_state` per
field; a curated correction SUPERSEDES its conflict evidence; corrected
results wear the correction-aware provenance tag, never the feed's
badge. Independent confirmation needs kinds {box, school}; the NCAA
feed never corroborates itself.

**C8 — Live vs final.** A match is over when the crawl says
`game_state == 'F'` OR the live feed says so (`period` final/complete,
`state` final, or a side's set tally reaches 3 — mOver/isOver). Live
figures are provisional: never accumulated, never cached, never written
to data/. The crawl-vs-live seam is bridged by the "just finished" band
and by ledger re-render on poll.

**C9 — External references are inert.** FIG / Massey snapshots are
display-only, private; adding, mutating or removing them changes no
hub-owned byte (proven with absent AND adversarial snapshots).

## 2. Reader map (inventory, produced before any change)

CANONICAL (route through season_counts / the corrected dataset fields):
  bakeoff_2025 -> rating (classify + apply_correction) · rpi_2025 (same)
  · digby_top25._eligible (countable) · external_refs.hub_records
  (countable) · crawl_2025 player aggregate (dup+exh+review skips +
  box_team_swaps) · collector rechecks (review_gids) · conference_lab
  (dataset duplicate_of/under_review fields + exh id-ledger)
  · confidence.py (finals only BY DESIGN -- it audits everything)
  · snapshot_rankings / snapshot_conferences (freeze precomputed
  artifacts) · digby chat (reads the built page).

SAFE-RAW (deliberately raw, no counting): fixtures.py (pregame truth
  layer) · freshness.py (change fingerprint) · venues.py (venue
  inference) · weekly.py (freeze completeness gate) ·
  fixture_disposition · live_detail / live_server (never persisted) ·
  source_intel (ledgers are its subject) · box_and_players' games.jsonl
  re-read (id->name map only).

THE RES BUILDER (build_hub.results, L181-343): a structural duplicate
  of the whole chain (own dedup, own correction application, own
  empty-final rule) that consults the same ledgers and is FENCED by the
  build-time SystemExit (res_cnt must equal
  season_counts.totals.results_on_display). Guarded duplicate.

## 3. Bypass inventory — DANGEROUS DUPLICATES, prioritized

P0 — counting bugs on ballot surfaces (verified live 2026-08-31):
  D4 resume_2025.py L117-132: counts 14 non-ok matches into the LIVE
     RESUME rank -- 2 exhibitions, 6 duplicates, 5 empty finals; and
     `home_win = sets> comparison` credits the AWAY side with a W on an
     empty final (0>0 false -> 0). Measured: loop count 478 vs contract
     464 ok D-I.
  D3 digby_top25.py W-L loop L296-306: finals+duplicate only ->
     exhibitions inflate records (Nebraska 3-0, SMU 4-0 measured) and
     an empty final scores BOTH sides a loss (is_winner None).
  D1 build_hub.top25_view L2926-2935: second raw results() read, no
     exhibition/under-review filter -> the Top 25 form strip renders
     the Nebraska-Florida EXHIBITION as `beat #21 Florida 2-0`
     (confirmed on the live page).
  F4 build_hub._final_of L4162-4178: no under_review skip -> a
     disputed result would bake into a Match Desk final card.
  F5 build_hub "What changed" L4286-4299: iterates ALL res ->
     exhibitions/under-review eligible.

P1 — ratings/projection inputs:
  D7 player_rating.py: three raw playerbox reads with NO box_team_swap
     and NO dup/exh/review eligibility; games.jsonl read with no state
     filter. The swapped SMU-UC Davis rows enter opponent-defence /
     faced-defence / schedule strength attributed to the wrong team.
  D5 simulate_season_2026.py L100-116: FIRST-seen-wins dedup (a stale
     record beats its own revision -- the exact anti-pattern R2 bans),
     no exclusions, no corrections, and a winnerless final scores the
     non-winner as a LOSS.
  D6 project_field.py L110-129: raw log, no exclusions, no
     corrections.

P2 — structural (latent, no live divergence measured):
  F1 season_counts.countable/classify accept a non-deduped list: a
     live record or second final revision of a gid passes through
     (fixture corpus falsified it; every current caller happens to
     pass deduped lists).
  D2 THREE implementations of apply-a-result-correction:
     season_counts.apply_correction, build_dataset
     ._apply_result_correction, build_hub.results inline -- differing
     linescore-fill guards.
  D8 availability.py / availability_desk.py: playerbox rows unswapped
     (participation could attribute a swapped match's rows to the
     wrong team); desk includes exhibitions/review in participation --
     DEFENSIBLE (participation is an observed fact, not a count) and
     kept, stated here.
  D9 confidence.box_teams(): unswapped -- harmless today (a swap is
     between the match's own two teams) -- noted.
  G1 conference_lab exhibition check reads the id ledger only; a
     future venue+date RULE exhibition would count there. Also
     weekly.py freeze gate counts exhibition finals as finals (gate
     semantics, acceptable) -- stated.
  FIVE independent game-log dedup rules (gamelog, weekly, venues,
     freshness, simulate first-seen) -- gamelog's is the contract.

P3 — clocks and labels:
  F8 _tv_iso compares against the BUILDER's local clock (UTC in CI),
     not today_pt() -> TV "earlier listings" split can shift a day.
  F9 sbShift() date arithmetic uses the VIEWER's local zone (the one
     non-PT date computation on the page).
  F7 tdForm label says "counted D-I finals only" while t.played
     includes marked non-D-I rows.
  Collector date binding uses hand-rolled fixed offsets (deliberate
     two-date net; acceptable, stated).

## 4. Fixture corpus

scripts/test_fixture_corpus.py builds the ten-case corpus and asserts
class membership, resolved result, box ownership and provenance state
for each, against the real season_counts/confidence code with injected
ledgers.

## 5. Release invariant

The build emits `data/audit_manifest_{season}.json` from the exact
dataset bytes it consumed: dataset sha256, the class totals, and a hash
of the counted-gid set. Counted surfaces are checked against it at
build time and the build FAILS CLOSED on divergence.

## 6. Repairs executed (all from the inventory above) and results

Every P0/P1/P2/P3 item above was repaired except the ones marked kept-
by-design (desk participation facts, box_teams, weekly gate,
collector's two-date net). Before/after, measured:
  resume counted matches 478 -> 464 · digby records Nebraska 3-0 -> 2-0,
  SMU 4-0 -> 3-0 · Top 25 exhibition pill now outlined EXH with the
  full sentence in its title · player_rating consumes 468 of 482
  playerbox records (the 14 non-ok excluded), swaps applied.
Fixture corpus: 10/10 shapes hold (it FAILED 3 before season_counts.
resolve()). Audit manifest emitted per build: 468 counted (464 D-I) of
482 feed records, all counted surfaces agree; the build fails closed on
divergence. 62/62 suites, both builds, public gate, fresh checkout.

## 7. What remains structurally risky (report to Cody)

1. build_hub.results() is still a parallel implementation of the chain
   (its own dedup + ledger consultation), fenced by two build-time
   gates (results_on_display + the manifest). Folding it onto
   season_counts.countable is a larger refactor with display-shape
   risk; deferred deliberately.
2. Three scoreboard-file passes (schedule(), team_index fixtures,
   sched_n) are independent loops over the same files; they agree
   today and have no counting authority, but they can drift in
   display terms.
3. weekly.py's freeze gate counts exhibition finals as finals -- gate
   semantics (completeness, not counting); stated, not changed.
4. venues.py / freshness.py keep their own dedup rules -- harmless to
   counting (venue inference, change fingerprint), but they are two
   more copies of a rule gamelog owns.
5. The JS layer trusts payload fields (nondi, mine/theirs, state) --
   correct so long as payloads come from res_cnt; no independent JS
   recount of records exists except the dossier's nondi filter, which
   reads flags the server set.
6. External snapshots remain manual browser reviews; staleness is
   labelled, never inferred. FIG coverage 339/348 and Massey current
   175/349 are described as partial where shown.
