# Availability-to-Forecast Truth Audit — 2026-09-01

Trigger: Texas showed Abby Vander Wal "Out for the 2026 season" beside
an 84% win forecast v USC. The reader must never guess whether the
forecast knows about the status beside it.

## 1. Input map (measured, per surface)

| Surface | Number | Producer | Inputs | Reads availability? |
|---|---|---|---|---|
| Team dossier next-match pick / fixtures list | "84% to win" | predict_2026.py → predictions_2026.json | rating_2025 blend strengths, venue site map, counted game log | **No** |
| Match detail "Forecast (before first serve)" | pre-serve pick | prediction_log.jsonl (frozen at log time) + predictions | same as above | **No** |
| Today / Watch Now forecast chips | deskForecast | DESK payload ← predictions | same | **No** |
| Rankings POWER | 0–100 rating | rating_2025/bakeoff fit | counted match margins + RPI, corrections applied via season_counts | **No** |
| Rankings Tourn %, dossier Proj wins / Conf title / Tournament odds | simulator | simulate_season_2026.py | rating prior (shrunk 0.860, resampled), predictions, counted W-L | **No** |
| Projected bracket / seeds | project_field / board seeds | ratings + AQ map + RPI | **No** |
| Résumé rank | resume_2026 | counted results only (classify=='ok') | **No** |
| Digby blend / Top 25 | digby_top25 | projection + counted margins via season_counts.countable | **No** |

Refresh boundary: predictions/ratings/simulator regenerate each refresh
cycle, fingerprint-gated on NEW FINALS ONLY — an availability status
arriving at any hour changes no input and triggers no recompute. A
status therefore ALWAYS post-dates or bypasses the forecast; the
Vander Wal trace: her ACL report (Aug 31) exists nowhere in any input
above, and the 84% derives from team strengths fitted on played
matches plus the preseason roster projection.

Claim classes that can influence a forecast: **none**. Community
signals, incidents, statuses, expired evidence: none reach any
producer (source-scanned and behaviorally verified — predictions are
byte-identical with the evidence file absent).

## 2. Adopted contract: availability is NOT an input

One sentence, one definition, on every surface, discoverable from the
number itself:

    Forecast does not incorporate availability.

- `FORECAST_AVAIL_NOTE` (python) is substituted into the page as the JS
  `FORECAST_NOTE` const — one definition, two languages, cannot drift.
- Titles on: the dossier next-match pick, the fixtures-list pick chips,
  the Today forecast card, the Tourn column header.
- Visible text on: the match-detail Forecast section, the dossier
  Outlook box (which also states a sourced status changes no Power /
  win probability / résumé / bracket number), the projected-bracket
  lead, and the Rankings methodology (which also states why no
  hand-set adjustment will be built).
- POWER (a rating, not a forecast) carries the companion sentence
  "Sourced availability is not an input." on its ruler tooltip.

## 3. No fake injury adjustment

Nothing was added to any model. A future availability-aware model is a
separate evidence/methodology phase (stated in the shipped
methodology), consistent with the standing R5/injury rule: "Do not
invent an injury adjustment."

## 4. Verification

scripts/test_forecast_availability.py: producer source scan (with a
negative control), behavioral predictions-identity with the evidence
file absent, disclosure presence on every surface, the Texas numeric
trace (pick == predictions file == DESK payload), Purdue/Heaney
controls (status vs incident never conflated; forecasts unchanged),
public fencing.
