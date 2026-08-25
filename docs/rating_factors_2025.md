# What actually makes a volleyball rating better — measured, 2025

`scripts/rating_factors.py` · guards in `scripts/test_rating_factors.py`
Data: 5,048 completed D-I matches, 100% with box scores.

## The question

Cody asked how a ranking should weight early matches against late ones, strong
opponents against weak, a 3–0 against a 3–2, a 25–12 sweep against a 25–23
sweep, a match a team was outscored in but won, home against road against
neutral, a team's earned points against points its opponent gave away, and
rest/travel/turnaround.

A separate 260-item proposal (via ChatGPT) recommended specific answers to
several of these. **Four of its central recommendations are measurably wrong on
this sport's data**, which is the whole reason to measure rather than choose.

## Method

Split the season **by date**, never at random — a ranking exists to predict what
happens next, so the test has to be the future. Fit on everything up to a
cutoff, score on everything after. Three cutoffs (45%, 60%, 75%), because one
split is one sample. Scored by AUC (can it pick winners), RMSE (can it predict
margin), and a **paired bootstrap CI** on the AUC difference from baseline.

Opponent strength and home advantage are **not candidates** — the ridge already
fits `mu + off_i − def_j + h·home_sign`, so they are in every scheme including
the baseline. The question is what to add on top.

## Results

Baseline (equal weight, rally point margin per set — what ships today):
**AUC 0.8498, RMSE 3.901**.

| Scheme | ΔAUC | CI 95% | Verdict |
|---|---|---|---|
| earned-blend-25 | +0.0016 | [−0.0003, +0.0036] | promising, **not proven** |
| earned-blend-50 | +0.0009 | [−0.0027, +0.0050] | not distinguishable |
| recency, half-life 90d | +0.0002 | [−0.0007, +0.0010] | not distinguishable |
| recency, half-life 60d | +0.0001 | [−0.0012, +0.0014] | not distinguishable |
| recency, half-life 45d | +0.0000 | [−0.0015, +0.0017] | not distinguishable |
| recency, half-life 30d | −0.0005 | [−0.0027, +0.0020] | not distinguishable |
| root-0.75 (diminishing returns) | −0.0012 | [−0.0026, +0.0002] | not distinguishable |
| cap ±8 pts/set | −0.0013 | [−0.0033, +0.0004] | not distinguishable |
| root-0.5 (sqrt margin) | −0.0043 | [−0.0072, −0.0012] | **worse** |
| recency, half-life 14d | −0.0043 | [−0.0088, +0.0006] | not distinguishable |
| cap ±5 pts/set | −0.0065 | [−0.0104, −0.0022] | **worse** |
| earned-only | −0.0068 | [−0.0142, +0.0009] | not distinguishable |
| recency-45 + cap-5 | −0.0069 | [−0.0115, −0.0026] | **worse** |
| cap ±3 pts/set | −0.0113 | [−0.0171, −0.0060] | **worse** |
| sets-target (3–0 vs 3–2) | −0.0137 | [−0.0199, −0.0081] | **worse** |

**Nothing beat the baseline with a CI clear of zero.** Five things are
measurably worse.

## What this settles

**1. Recency weighting does not help.** Half-lives from 14 to 90 days all land
on the baseline or below; the *shortest* half-life is the worst of them. The
proposal to ramp September→November from 100% to 130% (and postseason to 150%)
is not supported: a full season weighted equally predicts future matches as well
as any decay tested. Intuition says a team in November is a different team from
the one in September; over a whole league, the data says the extra information
in an old match outweighs its staleness.

**2. Do NOT cap or discount blowout margins.** This is the clearest result in
the table and it is the exact opposite of the recommendation ("use logarithmic
diminishing returns", "cap margin effects so teams can't farm points"). Capping
at ±3 pts/set costs **−0.0113 AUC** with the CI well clear of zero; ±5 costs
−0.0065; a square-root transform costs −0.0043. **25–12, 25–12, 25–12 really is
much stronger evidence than 25–23, 25–23, 25–23**, and squashing it throws
away information the rating needs.

The fear behind the recommendation — that a team farms points against bad
opponents — is real but it is *already handled*, by the opponent adjustment
rather than by a cap. Beating a poor team by 13/set is what the model expects
of a good team; it earns very little. Capping punishes the honest signal to
defend against a problem that is solved elsewhere.

**3. Rank on points, not sets.** Using set margin (3–0 = +3, 3–2 = +1) is the
worst scheme tested, −0.0137. The set score is a *coarsening* of the point
margin: 25–23, 25–23, 25–23 and 25–12, 25–12, 25–12 are both "+3" to it. So the
3–0 vs 3–2 question answers itself — the point margin already knows, in more
detail, and it knows about the match a team was outscored in but won (that
match has a **negative** margin and the rating treats it accordingly).

**4. Rest and same-day turnaround: nothing.** A team playing its second match
of a day wins **49.2%** (n=2,635) against **50.3%** otherwise — about one
percentage point. Adding a rest term, fitted on the training half and scored on
the held-out half, moved AUC by **−0.00002**, CI [−0.00007, +0.00002]. There is
no measurable turnaround penalty at league scale.

**5. The one promising idea is "earned points".** Blending 25% of an
earned-point margin (kills + blocks + aces, ignoring points the opponent gave
away) into the rally margin is the only scheme that beat the baseline —
+0.0016 AUC and the best RMSE in the table, 3.890. Its CI includes zero, so it
is **not proven**, and it does not ship on a point estimate. It is the one
worth re-testing as 2026 accumulates. Note `earned-only` is clearly worse: a
team's gifted points are not noise, they are partly *caused* by its serving
pressure, so discarding them entirely loses real signal.

## What could not be measured, and why

**Travel, time zones and local start times.** Cody asked specifically about a
Pacific team playing 8am Eastern and turning around that afternoon. The
turnaround part is above. The rest is unmeasurable on 2025 data: `crawl_2025.py`
discarded `location` from `/game/{id}`, so 2025 carries no venue, city or state,
and re-crawling a past season is banned. Venue **is** stored from 2026
(`data/venues_2026.json`), so time zone and local start become measurable as
this season fills in — not now. Proxying them with something computable and
calling it travel would be worse than saying this.

## The honest headline

The rating that ships is at or above the best of fifteen alternatives, and the
most confident findings are all **negative** — four popular ideas that make it
worse. That is worth more than a new term: it means the next person who wants to
add recency decay or cap blowouts has a number to argue with.

⚠ One season, one league. These are measurements of 2025 D-I women's
volleyball, not laws. Re-run after 2026.

---

## Round 2 — the "clutch / grit / composure" family

Both AI proposals spend dozens of entries on this: clutch rating, grit index,
resilience, red-zone efficiency, composure, blowout avoidance, consistency,
five-set record. It reduces to a handful of quantities computable from set
scores, so it can be settled.

The only meaningful test is **incremental**. A clutch rating correlates with
winning because good teams also win close sets; the question is whether it says
anything the opponent-adjusted margin has not already said. Each feature gets a
coefficient fitted on the training half, then scored on matches from the future.

| Feature | ΔAUC | CI 95% | Verdict |
|---|---|---|---|
| blowout_for — sets won holding opp under 15 | +0.00018 | [−0.00009, +0.00043] | nothing |
| blowout_vs — sets lost scoring under 15 | +0.00004 | [−0.00021, +0.00032] | nothing |
| collapse — 2–0 leads lost | −0.00015 | [−0.00105, +0.00079] | nothing |
| consistency — steadiness of match margin | −0.00016 | [−0.00054, +0.00029] | nothing |
| earned_share — silent points, as a team rate | −0.00050 | [−0.00088, −0.00009] | **hurts** |
| comeback — 0–2 holes climbed out of (grit) | −0.00109 | [−0.00235, +0.00036] | nothing |
| deuce_win — sets past 25 (composure) | −0.00132 | [−0.00193, −0.00062] | **hurts** |
| close_win — sets decided by ≤2 (clutch) | −0.00294 | [−0.00465, −0.00096] | **hurts** |
| five_set_win — five-set record | −0.00552 | [−0.00957, −0.00014] | **hurts** |

**Not one of them helps. Four measurably hurt.** The bigger the reputation of
the metric, the worse it does: five-set record is the single most damaging
feature tested. A team's five-set record is a *history of coin flips*, not a
skill — using it to predict future matches makes the rating worse than ignoring
it, and it is worse than the "clutch" and "composure" versions that are built
on more sets and therefore less noisy.

This is the classic clutch-is-mostly-noise result, now measured for D-I women's
volleyball rather than assumed from another sport.

⚠ **One distinction worth keeping straight.** `earned_share` as a *team rate*
hurts (−0.0005), while blending an earned-point *margin* into the rating target
was the only positive result in round 1 (+0.0016). Those are different uses of
the same idea: the margin says "how many more points did you terminate than
they did", the rate says "what fraction of your points were terminations". The
first is a strength measure; the second is a style measure, and style does not
predict.

### What could not be tested, and why it was left out

"First to 20", performance at 22–22, and momentum after a timeout need
point-by-point data. ncaa.com does not carry it; the MIT-licensed play-by-play
mirror covers 2025 but has **no live 2026 feed**, so a term built on it could be
measured on history and never computed during a season. Half-building it would
put a number on the page that goes stale the moment the season starts.

## Where the two proposals disagreed with each other

They contradict on the single clearest result in the table. ChatGPT: *"use
logarithmic diminishing returns"*, *"cap margin effects so teams can't farm
points"*. Gemini: *"the model weights a 15-point victory far higher than a
2-point victory"*.

**Gemini is right.** Capping at ±3 costs −0.0113 AUC with the CI well clear of
zero. Don't squash blowouts.

They agree on one thing that turned out to matter: both independently propose
earned-vs-gifted points (ChatGPT's "point source profile", Gemini's "Silent
Points Ratio"). That is the only idea from either list that beat the baseline —
and it still is not statistically proven.
