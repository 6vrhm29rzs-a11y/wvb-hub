# NCAA D-I Women's Volleyball — championship format, rules and sources

**Written 2026-08-23** from the sources named below. This is the reference the
bracket, the field projector and the AQ map are built against, so that none of
them encodes a format detail that exists only in somebody's head.

Everything here is a FACT from an official source with the source named. Where
a detail is inferred or uncertain it says so.

---

## 1. The field

| | |
|---|---|
| Field size | **64 teams** |
| Automatic qualifiers | one per eligible conference — **31 in 2025**, **32 in 2026** (the rebuilt nine-member Pac-12 restores a bid) |
| At-large | the remainder — **33 in 2025**, **32 in 2026** |
| Seeded | top **32** nationally, in pods of four |

> *"Thirty-one conferences were awarded an automatic qualification, while the
> remaining 33 positions were filled with at-large selections to complete the
> bracket."*
> — ncaa.com, 2025 championship field announcement, 2025-11-30

**A conference label is not a conference.** 2026 has **33** conference labels
but only 32 that can award a bid: the WAC is down to a single D-I member
(UT Arlington) and no longer fields a volleyball championship. A league below
six D-I members cannot award a bid.

**Championship-ineligible programs** (reclassifying) are excluded from the field
but their games still count in opponents' RPI. For 2026: West Ga., Mercyhurst,
New Haven, West Florida. If one wins its conference, the AQ passes to the best
eligible finisher.

---

## 2. The rounds

From the official bracket, in order, mirrored left and right:

```
FIRST ROUND → SECOND ROUND → THIRD ROUND → QUARTERFINALS
                                              ↓
                                         SEMIFINALS
                                              ↓
                                        CHAMPIONSHIP
```

- **First and second rounds** — 16 campus sites, top seeds host. Four teams per
  site (a "pod"); the second game in each quadrant starts ~30 minutes after the
  first concludes.
- **Third round and quarterfinals** — the regional rounds, commonly called the
  **Sweet 16** and **Elite Eight**.
- **Semifinals and championship** — one predetermined neutral site.

Source: 2025 official bracket (ncaa.com/brackets/volleyball-women/d1/2025) and
ncaatickets.com championship information.

### Timeline

| when | what |
|---|---|
| late November | Selection Show, after conference tournaments conclude |
| early December | first and second rounds (campus sites) |
| mid December | regional rounds (Sweet 16, Elite Eight) |
| mid-to-late December | national semifinals and championship match |

### Neutral sites

| year | host |
|---|---|
| **2026** | **San Antonio — December 17 & 20** |
| 2027 | Columbus, OH — Nationwide Arena |

Source: <https://www.ncaatickets.com/womens-volleyball-championship-information>

---

## 3. Selection and seeding

The committee evaluates:

- automatic qualification from conference championships
- at-large selections
- overall win-loss record
- strength of schedule
- team rankings and performance metrics
- results against top opponents

Conference champions receive automatic bids; the rest come through the at-large
process. The committee also determines seeding, and **top seeds host the opening
rounds** before the tournament moves to the neutral site.

**⚠ This is a RESUME judgement, not a strength judgement.** Our composite is a
strength rating and relative to RPI it favours teams with *worse* records
(corr −0.205). The field projector must predict what the committee will do, so
it runs on the resume view — RPI, record, results vs the top 25/50 — not on the
composite. That is R3, and it is the single most load-bearing distinction here.

---

## 4. How each conference awards its automatic bid

**Confirmed for all 32.** Source: ncaa.com, *"Tracking all 31 automatic
qualifiers for the 2025 NCAA women's volleyball tournament"*, 2025-11-27, which
lists each conference's tournament rounds and shows **N/A** for those that hold
none.

- **Regular-season champion takes the bid (3):** ACC, Big 12, WCC
- **Conference tournament (29):** everyone else

**2026 changes applied on top:** the **Big Ten** holds its first-ever volleyball
tournament (top 15 of 18, Nov 20-25) and the **Pac-12** a new one (top 4, week of
Nov 23). Both were regular-season or nonexistent in 2025, so 2025 evidence
cannot show them.

⚠ **This is 2025 evidence.** A league that changes format for 2026 without
announcing it will be wrong here — exactly what the Big Ten did last year.
Machine-readable copy: `data/raw/2026/aq_mechanism_2026.json`.

---

## 5. Published rankings, and what each one is

The three ncaa.com publishes, from the rankings page dropdown:

| ranking | what it is | our use |
|---|---|---|
| **AVCA Rankings** | coaches poll; rank, school, first-place votes, total points | reference column only |
| **DI Committee's Top 16** | the selection committee's own in-season reveal | ⚠ **not yet captured — see below** |
| **NCAA Women's Volleyball RPI** | official RPI | reference column, and the AQ/at-large driver |

**⚠ OPEN: the committee's Top 16 is the closest published thing to the target
the field projector is trying to predict**, and we do not collect it. It is the
committee stating its own resume judgement mid-season. Worth capturing when it
starts publishing (typically late in the season).

**None of these feed the model.** Cody, 2026-08-18: *"don't use the other
rankings as part of our rating."* They are displayed beside our number, never
inside it.

---

## 6. Bracket presentation (what the official one does)

Recorded because the hub's bracket should read like the real thing:

- Each matchup is a **card of two rows**, one per team.
- A row is: **small team logo · seed · team name · sets won**.
- The **winner is bold and dark; the loser is greyed out.** That single contrast
  carries the whole bracket at a glance.
- **`FINAL`** sits above a completed matchup.
- **Unseeded teams show no number at all** — not a zero, not a dash.
- Round headers run across the top: `FIRST ROUND · SECOND ROUND · THIRD ROUND ·
  QUARTERFINALS`, mirrored on the right half.
- **Semifinals and championship sit in the middle**, below the two halves, with
  the champion in its own box beneath.

---

## 7. Sources

- 2025 official bracket — <https://www.ncaa.com/brackets/volleyball-women/d1/2025>
- 2025 field announcement — ncaa.com, 2025-11-30
- AQ tracker — ncaa.com, 2025-11-27
- Championship information — <https://www.ncaatickets.com/womens-volleyball-championship-information>
- Rankings — <https://www.ncaa.com/rankings/volleyball-women/d1/avca-rankings>

⚠ The saved PDFs of the bracket and rankings are **gitignored on purpose**: they
are NCAA/AVCA publications, and committing them to a public repo republishes
someone else's document. The facts above are ours to record; the documents are
not ours to redistribute. Same reasoning as the saved VolleyTalk pages.
