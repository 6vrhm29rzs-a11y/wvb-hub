# Rotations and starting lineups — what the feed does and does not have

> ## ⚠ SUPERSEDED IN PART — 2026-08-23. ROTATIONS ARE RECOVERABLE.
>
> Everything below is still true **about ncaa.com's feed**, and that feed is
> still the daily pipeline. What was wrong was the scope of the conclusion:
> "rotations 1-6 cannot be built" was stated as a fact about the sport's data
> when it was only a fact about **one source**.
>
> **StatBroadcast names the server on every rally.** A team serves in rotation
> order by rule, so the serve sequence IS the rotation — derived, not inferred,
> with no threshold chosen. Verified on Louisville–Wisconsin set 1 (43 rallies):
> both teams produce a clean period-6 cycle over two full turns of the order.
>
>     Louisville  1 Meester · 2 Petersen · 3 Kenny · 4 Chicoine · 5 Bultema · 6 Cabello
>     Wisconsin   1 Simon · 2 Lopez · 3 Egan · 4 Flanagan · 5 Hoppe · 6 Fuerbringer
>
> Three things §2b and §2c said were unavailable now are:
> - **Setter front row vs back row, per rotation** — exact, because the
>   setter's own slot is known. This was Cody's actual question.
> - **Substitution pairings** — a substitute serves from the slot of the player
>   she replaced, so the pairing is read off the cycle. Louisville's Jessica
>   Drapp for Brooke Bultema, recovered outright. The NCAA feed managed 4%.
> - **The 5-1 / 6-2 signature**, which scored at chance on ncaa.com's jersey
>   ordering, now appears: Louisville's two setters sit exactly 3 apart
>   (Kenny slot 3, Cabello slot 6) — the textbook 6-2.
>
> **⚠ THE LIMIT, MEASURED: the serve order gives the SERVING six, not the six on
> the court.** A libero replaces a middle the moment that middle rotates to the
> back row, and the back row is where the serve is — so the middle never serves
> and never appears. **None** of Wisconsin's five middles appear in its serve
> order, and only one of Louisville's five does, while Auguste and Tarnow both
> recorded kills in that same set. Rotation *order* is exact; a slot whose
> server is a libero or DS belongs to a front-row player the serve order does
> not name, and it is flagged rather than filled in (R5).
>
> Built: `scripts/rotations.py`, guarded by `scripts/test_rotations.py` with a
> positive control (a true rotation must be recovered) and a negative control
> (a shuffled sequence must be rejected — a method that finds a rotation in
> anything has found nothing).
>
> **Not yet wired to a source.** StatBroadcast 403s every non-browser client and
> its terms grant access "through the standard StatBroadcast web interface", so
> there is no crawler and will not be one without permission. See
> `docs/statbroadcast.md`. The deriver is finished, so a serve list pasted or
> read from a page becomes a full rotation immediately.
>
> **The lesson is the one this project keeps paying for:** the earlier finding
> generalised from a single source, exactly as the "half the lines are
> mislabelled" claim generalised from a single match. A negative result is about
> the data you looked at.


**Measured 2026-08-22.** Answers Cody's ask: *"six on the court at all times,
but having projected lineups and rotations 1-6 vs opponent rotations 1-6 could
help us even more."*

**Short answer: projected lineups YES, rotations 1-6 NO.** The order the feed
prints its six names in is **jersey number**, not rotation order. This is not a
"we couldn't figure it out" — it is a measured negative with a positive control
behind it.

---

## 1. Rotation order is NOT in this feed

### The test

A lineup written in rotation order has a hard structural fingerprint. In a 5-1
(what nearly every D-I team runs) the players in slots *i* and *i+3* are
opposite each other, so the two middles sit exactly 3 apart, as do the two
outsides, and the setter and opposite. That fingerprint survives any cyclic
shift, so it does not matter where the listing starts.

Positions come from the box score, which we already had.

### The result — 206-game spread sample of 2025, 407 lineups

| check | feed's order | chance (same six, shuffled) |
|---|---|---|
| two MBs 3 apart | **15.8%** (n=336) | 19.8% |
| two OHs 3 apart | **19.3%** (n=171) | 20.3% |
| S and OPP 3 apart | **11.2%** (n=80) | 20.0% |

At or **below** chance on all three. Restricting to lineups with a textbook 5-1
composition (exactly S, OPP, 2×MB, 2×OH), where all three checks apply cleanly:
**16.7% / 16.7% / 16.7%** against a ~20% null. No signal.

### The positive control — why the negative is trustworthy

A negative result is worthless if the test could not have detected a positive.
The identical checker, run on synthetic lineups that genuinely ARE in rotation
order (random cyclic shifts of S, OH, MB, OPP, OH, MB):

**100.0% / 100.0% / 100.0%.**

So the test detects rotation order perfectly when it is there. It is not there.

### What the order actually is

**Ascending jersey number — 91.5% of lineups** (n=446). The remaining 8.5% are
scattered (1–4 out-of-order steps) and were tested separately in case a minority
of scoring systems emit true rotation order: they do not (MB 17.9%, OH 11.8%,
S-OPP 0.0%, all against a ~20% null).

### Why we cannot recover rotation order another way

- **Serves are named only on aces.** A service error prints as bare
  `Service error.` with no name, and a serve that stays in play produces no
  event at all. So the serve sequence — which *is* rotation order — cannot be
  read off the feed.
- **The score fields are too gappy to reconstruct it**: `homeScore`/
  `visitorScore` are `null` on most plays, so rally-by-rally serve possession
  cannot be rebuilt reliably either.
- Inferring a rotation from box-score totals instead would be an **R5**
  violation — a synthesised value presented as a measurement. Not doing it.

**Do not ship a "rotation 1-6" view.** Guarded by
`scripts/test_lineups.py::test_feed_order_is_not_rotation`, which fails if the
feed order ever starts showing the signature — at which point this finding gets
revisited *before* anything is built.

---

## 2. Starting lineups ARE available (2025), and are clean

- **Set 1 carries a real starting six.** 414 of 416 set-1 lines held exactly
  six names; 403 of 410 groups matched a box score on all six.
- **Sets 2+ DO NOT.** Their `starters:` line is **cumulative** — everyone who
  has appeared so far, 6 to 14 names. Reading it as a lineup is simply wrong,
  and it is the most likely way someone re-derives this badly later. Only
  period 1 is parsed.
- Coverage is complete: all 206 sampled games had usable set-1 lines.

### Two traps in the parsing

1. **The separator varies by game** — `;` in some feeds, `,` in others.
2. **The feed's own `teamId` and team name are sometimes wrong.** Measured:
   wrong on **2 of 409** set-1 lines — rarer than the earlier session-close
   estimate of "half", which generalised from a single match (Nebraska–
   Pittsburgh 6482612, where Nebraska's six is printed under Pittsburgh's
   teamId *and* Pittsburgh's name). Rare is not zero, and a mis-attributed
   lineup is invisible downstream, so **attribution is by matching names to
   that game's box score**, never by the feed's label. Same shape as R8.
   Disagreements are recorded (`feed_label_agreed`) so the rate stays
   measurable.

---

## 2b. "Who subs for who" — NOT recoverable, measured

Cody's follow-up asked for substitution pairings: *"if a team starts with their
setter front row and their stud opposite subbed out with a DS to start."*

**The feed records only the player coming IN. It never records who went out.**
99.5% of `subs:` lines carry exactly one name (1,994 of 2,004 sampled); the
handful with more are cumulative lists, the same shape as the sets 2+ starters
lines.

Volleyball rules give one lever: a substitute may swap with only one specific
starter, so a starter and her sub must alternate. That makes the pairing
deterministic in one case — exactly one non-starter is on court and a starter
enters, so that starter must be replacing her.

Measured over 206 games, tracking on-court state from the set-1 six:

| | |
|---|---|
| substitution entries seen | 11,074 |
| pairings that resolve deterministically | **439 (4.0%)** |
| starter returns that stay ambiguous | 3,608 |

**4% is not shippable.** The ambiguity is structural, not a parsing gap: teams
routinely have several substitutes off the court at once, and most entries are
the libero going in and out every rotation anyway. A pairing shown for 4% of
substitutions would look exactly as authoritative as one shown for all of them.

Not built. Not inferred.

## 2c. Setter front row vs back row — the same wall

Whether a team starts its setter front-row or back-row **is** the rotation
order, and section 1 shows the feed does not carry it. Not derivable.

One adjacent thing IS visible: whether the libero appears among the six listed
at the start. Across teams with 5+ lineups, that varies match to match for 171
of 279 — so it is partly real. But 93 teams never show a libero in the six and
15 always do, which is a scorer convention rather than a fact about play.
Reading it as tactics would be reading a habit. Left out.

## 2d. What the starting-six data DOES support

- **The offence: 5-1 or 6-2.** One setter in the starting six is a 5-1, two is
  a 6-2. Measured across 2025: **253 teams consistently start one setter, 4
  start two**, 81 not stated. Shown as a badge only when a team's own lineups
  agree (>=80%); a team whose position data cannot show a setter at all gets no
  label rather than a guess. Verified by hand: Missouri St. and Grand Canyon
  both genuinely start two setters.
- **Who starts and who does not** — matches started per player, against the
  team's match count.
- **Who is back for 2026**, per starter, and how many slots are vacant.

---

## 3. 2026 is PARTLY populated (corrected)

**Corrected the same day.** The first version of this section said 2026 was
empty. That generalised from **one match** — 6639844 (Louisville–Texas A&M),
which really does return 16 `starters:` lines with 0 names filled.

Crawling all three 2026 finals gives **2 of 3 with real lineups**. Kentucky, for
example: Trinity Ward L/DS #1 · Kassie O'Brien S #6 · Kennedy Washington MB #10
· Lizzie Carr MB #15 · Brooklyn DeLeye OH #17 · Asia Thigpen OH #20.

So live lineups **are** collectable, match by match, and `crawl_pbp.py` now runs
daily to take them as they happen. `starters_lines_with_names` records whether a
given match carried them.

All four 2026 lineups are in ascending jersey order, so **the rotation finding in
section 1 holds for the live season too**.

Re-check with one command:

```
curl -s -A "wvb-hub/0.1" https://ncaa-api.henrygd.me/game/6639844/play-by-play \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print(sum(1 for p in d['periods'] for e in p['playbyplayStats'] \
      for x in e['plays'] if 'starters' in (x['playText'] or '').lower() \
      and (x['playText'].split(':',1)[1].strip() if ':' in x['playText'] else '')))"
```

Prints the number of *filled* starters lines. `0` means still empty.

---

## 4. Storage decision

The raw play-by-play is ~58 KB/game — **296 MB for a season**. That is not
committed to a public repo for six names a game. `scripts/crawl_pbp.py`
extracts and discards, writing the compact `data/raw/{season}/lineups.jsonl`.
Pass `--keep-raw` to retain payloads locally. Re-fetch is one command.
