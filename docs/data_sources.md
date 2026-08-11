# Source Access Inventory — measured 2026-08-11 (UTC)

## Context

Cody asked, across several rounds, whether the Builder can reach a set of volleyball
sources — AVCA, ncaa.com, VolleyballMag, VolleyTalk — plus a batch of files he
downloaded locally. The ask was **access verification only**: establish what is
reachable and record it, with the use for it to be decided later.

Every row below was tested by fetching it, not inferred. Method is stated so any
row can be re-checked. All web fetches used the project's self-identifying UA
(`wvb-hub/0.1 …`) at the usual polite rate.


---

## 1. Live web sources

| Source | Status | Notes |
|---|---|---|
| `avca.org` (root) | **200** | 279 KB |
| `avca.org/polls-awards/polls/?_season=2026&_divisions=division-i-women` | **200** | Exposes direct `.xlsx` links |
| `avca.org/polls-awards/polls/?_season=2025&_divisions=division-i-women` | **200** | Same, 2025 files |
| `avca.org/resource/division-i-women-top-25-poll-archives/` | **200** | 3 `.xlsx` record files |
| `avca.org/news-events/stay-up-to-date/newsletter/` | **200** | Newsletter index; no structured data, no PDFs |
| `avca.org/event/ncaa-division-i-womens-volleyball-championship-2/` | **200** | Carries 2026 championship dates: **Dec 17 and Dec 20, 2026** |
| `ncaa.com/sports/volleyball-women/d1` | **200** | Hub page |
| `ncaa.com/rankings/volleyball-women/d1` | **200** | **This is the AVCA poll** — see §4 |
| `ncaa.com/brackets/volleyball-women/d1/2025` | **200** | 363 KB, official tournament bracket |
| `volleytalk.proboards.com` (root) | **200** | 81 KB |
| `volleytalk.proboards.com/board/5/…` (+ `?page=N`, `?action=recent`) | **200** | Pagination works; see §3 |
| `volleytalk.proboards.com/thread/104233/…` | **200** | 47-page thread, fetches fine |
| `volleyballmag.com` — any HTML page | **403** | Cloudflare challenge ("Just a moment…") |
| `volleyballmag.com/feed/` | **200** | RSS works — but see §5 |
| `volleyballmag.com/category/…/feed/`, `/wp-json/…`, `/sitemap.xml`, `/newsletter/`, `/subscribe/` | **403** | All challenged |

**One blocked domain: VolleyballMag. Everything else is open.**

---

## 2. Local files (all readable)

In `/Users/codyrose/Womens_College_Volleyball_2026/`:

| File | Read via | Contents |
|---|---|---|
| `12-22-25-AVCA-Division-I-WVB-FINAL-Poll-1.xlsx` | openpyxl | 36×6 — Rank, School, Total Points, First-Place Votes, W-L, Previous Rank |
| `12-22-25-AVCA-DI-WVB-Poll-Week-by-Week.xlsx` | openpyxl | 60×18 — every ranked team's rank at each weekly poll, dated |
| `AVCA-DI-Womens-Poll-Records-Overview.xlsx` | openpyxl | 4,709×23 — per-school totals across **660 polls** |
| `AVCA-DI-Womens-Poll-Records-By-Year.xlsx` | openpyxl | 1,117×53, 3 sheets |
| `AVCA-DI-Womens-Poll-Records-Final-Polls.xlsx` | openpyxl | 207×54 |
| `AVCA-DI-WVB-Polls-Week-by-Week-1982-2025/` | openpyxl | **44 season files**, 1982–2025, incl. COVID split (`2020-21 - Spring`, `2021 - Fall`) |
| `Fall 2025 Match Threads … .html` | text | Identical to live fetch — see §3 |
| `Fall 2025 Match Threads … .pdf` (and ` 2.pdf`) | Read tool | Renders fully; posts, usernames, timestamps, schedule all legible |
| `Fall 2025 Match Threads … .webarchive` | `plistlib` | Parses; 154 KB main resource + 38 subresources |

`openpyxl` 3.1.5 is present. **`pandas` is not installed** — parse with `openpyxl` directly.

---

## 3. VolleyTalk — measured detail

- **Saved copies are unnecessary.** The live fetch and Cody's saved `.html` are
  identical: same 12 posts, same extracted text, same 19 usernames. Post text
  compares equal. Anonymous access sees what his logged-in session sees.
- **Pagination** is `?page=N`, ~25 threads/page, with `data-timestamp` in epoch-ms
  (so dating is exact, no parsing of display strings).
- **Depth map:** p10 → May 2026 · p25 → Dec 2025 · p50 → Oct 2025 · p100 → Nov 2024
  · p200 → Sep 2023. Back one year ≈ **page 55–60**.
- **Cost:** index-only (titles/dates/URLs) for a year ≈ 60 requests, under a minute.
  Full thread contents for a year ≈ 3,000–7,500 requests, 1–2 hours.
- A public RSS exists at `/rss/public`; `?action=recent` also works for change
  detection.
- Thread taxonomy is useful as-is: a **jobs thread** (coaching changes), per-team
  threads (`Wisconsin Badgers 2026`, `Texas Longhorns 2026`), conference threads,
  match threads, and a `2026 AVCA Preseason Poll` thread.

---

## 4. The significant find: ncaa.com already serves the AVCA poll

`ncaa.com/rankings/volleyball-women/d1` parses cleanly today:

```
RANK | SCHOOL          | TOTAL POINTS
1    | Nebraska (57)   | 1568
2    | Texas (1)       | 1427
3    | Kentucky (4)    | 1398
```

First-place votes in parentheses; stamped **"Through Games AUG. 10, 2026"**.

Why it matters: `ncaa.com` is already a **measured-working domain from a datacenter
IP**, so the existing GitHub Actions job could fetch the poll with no new
dependency. **Caveat:** this endpoint family is current-only and **cannot be
season-pinned** (already recorded in CLAUDE.md) — history has to come from the
AVCA `.xlsx` archive.

**Name-join feasibility (measured):** across all 44 archive seasons there are 125
distinct schools. With `reconcile_2025.norm()` plus a `State`→`St.` rule, **102
match** our 348. The 23 that don't are tidy classes: full-name vs abbreviation
(`Brigham Young`→BYU, `Louisiana State`→LSU), format variants
(`Arkansas-Little Rock`→Little Rock), **five** spellings of Saint Mary's, two
apostrophe variants of Hawai'i, one renamed program (`Southwest Missouri State`),
and one typo in AVCA's own file (`UC Santa Barabara`). ≈20 alias entries.

---

## 5. VolleyballMag — what was tried

- Site-wide RSS (`/feed/`) **is** reachable and returns 88 KB of valid XML — but it
  carries only 10 items, categorised `Club/HS`, `NCAA Men`, `News`. **No NCAA
  women's content**, newest item April 2026. The category-specific feed and the
  WordPress JSON API are both 403. The open door leads nowhere useful.
- **Not attempted:** spoofing a browser user-agent to defeat the challenge. That
  would contradict the self-identifying-crawler convention used everywhere else in
  this project, and it is a deliberate decision rather than an oversight.
- **Untested routes that would work if the content is ever wanted:**
  Claude-in-Chrome (loads in a real browser session; manual, cannot run in CI), or
  Cody's proposed email-subscription route. Note the signup pages are themselves
  403, so subscribing would have to happen through the browser or by hand — and
  **CI cannot read Gmail**, so anything arriving by email is readable only inside a
  Claude session, never by the daily pipeline.

---

## 6. Caveat worth carrying forward

AVCA's own poll page is **mislabelled**: the heading reads *"2025 AVCA-Taraflex
Division I WVB Preseason Poll – Aug. 10"* while its publish date is
**August 10, 2026**. If anything is ever pulled from there, key on publish date and
never on the title string — same class of trap as the banned `/current/` endpoint.

---

## Re-verification

Every row re-checks with a single command; nothing here needs credentials:

```bash
curl -sS -o /dev/null -w "%{http_code} %{url_effective}\n" -L --max-time 30 \
  -A "wvb-hub/0.1 (personal research project; github.com/6vrhm29rzs-a11y/wvb-hub)" \
  "<url>"
```

Local spreadsheets: `python3 -c "import openpyxl; ..."`.
No source here requires a login, an API key, or a paid tier.
