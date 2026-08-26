# Intel Desk — source registry and audit

Every source here is **allowlisted in code** (`scripts/intel.py: SOURCES`). The
endpoint takes no URL parameter: there is no way for the page, a note, or a
pasted string to make this fetch something else. Adding a source means editing
that list and adding a row here — both, in one change.

## Active sources

### 1. NCAA.com — Division I Women's Volleyball

| field | value |
|---|---|
| **URL** | `https://www.ncaa.com/news/volleyball-women/d1/rss.xml` |
| **Owner** | NCAA (ncaa.com), the sport's own governing body |
| **Format** | RSS 2.0, `application/xml` |
| **Measured** | 2026-08-25 — HTTP 200, 20,432 bytes, **20 items** |
| **Fields present** | `title`, `link`, `description`, `pubDate`, `dc:creator`, `enclosure`, `category`, `atom:link` |
| **Fields RETAINED** | `title`, `link`, `pubDate`, `category` — and nothing else |
| **Fields deliberately DISCARDED** | `description` (the article blurb), `enclosure` (thumbnail), `dc:creator` |
| **Refresh** | On demand from the local server, and at most once every 15 minutes; the cache is served in between |
| **Failure** | Any non-200, timeout, or unparseable body leaves the previous cache in place and the view says the source was unreachable and when it last succeeded |
| **Robots** | Same host the whole pipeline already reads (`ncaa.com`), one request per refresh at most |

⚠ **WHY `description` IS THROWN AWAY.** It is the publisher's own summary of
their article — their words, their work. Storing it would be keeping a copy of
somebody else's writing to display instead of theirs. The title and the link
are what a wire needs: enough to decide whether to click, and the click goes to
them.

## Audited and NOT APPROVED

### AVCA — audited 2026-08-25, verdict **not approved**

⚠ **IT PASSES ON PERMISSION AND FAILS ON USEFULNESS.** This is not a "we can't"
— it is a "we shouldn't yet", and the evidence is below so nobody re-derives it.

**Permission — clear.**

    curl -s https://www.avca.org/robots.txt

    User-agent: *
    Disallow: /wp-admin/
    Allow: /wp-admin/admin-ajax.php
    Sitemap: https://www.avca.org/sitemaps.xml

Everything except `/wp-admin/` is permitted. No terms-of-use restriction on
machine reading was found in that guidance.

**There is no RSS or Atom feed.** The homepage declares no
`application/rss+xml` alternate. What it DOES declare, in its own `<head>`, is
the WordPress REST API:

    <link rel="alternate" title="JSON" type="application/json"
          href="https://www.avca.org/wp-json/wp/v2/pages/2" />

So the machine-readable source, if there is one, is **WP REST v2** — official
(the site's own domain, the site's own declaration, WordPress core's documented
API), public, and unauthenticated.

**Measurements.**

| request | result |
|---|---|
| `GET /wp-json/wp/v2/posts?per_page=5` | HTTP 200, JSON, `x-wp-total: 840`, 168 pages, **268 KB** (carries full `content`) |
| `GET …&_fields=title,link,date_gmt,categories,division` | HTTP 200, **6.6 KB / 30 items** — `_fields` is the documented way to stay lean |
| `GET /wp-json/wp/v2/division?per_page=100` | HTTP 200, 20 taxonomy terms, incl. **id 59 = "Division I Women"** |
| `GET /wp-json/wp/v2/posts?division=59&per_page=10` | HTTP 200, `x-wp-total: 127`, filter honoured (every item tagged 59) |

**Fields available**: `title.rendered`, `link`, `date_gmt`, `categories` (numeric
ids), `division` (numeric ids), plus `content`, `excerpt`, `author`,
`featured_media` — the last four would be discarded under this project's
retention rule.

**Why it is not approved — three findings, all measured.**

1. **Unfiltered it is ~10% relevant.** Of the 30 most recent posts: high-school
   girls and boys watch lists, club, two-year college, a Division II poll, a
   men's international result, and coaching-education columns. Adding that to a
   Division-I women's desk makes a low-noise inbox noisy, which is the opposite
   of what it is for.
2. **Filtered to `division=59` it is mostly BEACH, and stale.** Of the ten most
   recent Division-I-Women-tagged posts, **eight are Collegiate Beach polls**.
   The newest item of any kind is **2026-08-10 — fifteen days old**, and the
   indoor season began on 2026-08-21. The tagged stream is not a live indoor
   news wire.
3. ⚠ **Its one genuinely valuable item is ALREADY CAPTURED, by a system that
   must stay separate.** The single indoor item in that window is the
   *AVCA-Taraflex Division I WVB Preseason Poll – Aug. 10*, and
   `data/raw/2026/polls_avca.jsonl` already holds that exact publication
   (`Through Games AUG. 10, 2026`, 25 rows) via `crawl_polls.py`. Adding it to
   Intel would duplicate the official-poll system in a news feed, which is the
   blurring this project keeps apart on purpose.

**Nothing was changed.** The allowlist is still NCAA-only, no AVCA code path
exists, and no fixtures were saved — fixtures are for approved sources.

**What would change the verdict**, in order of what would matter most:

1. **A live indoor D-I women's stream.** Re-check `?division=59` during the
   season: if it starts carrying indoor items within a day or two of matches,
   that is a different source from the one measured here.
2. **A way to exclude beach.** The `division` taxonomy has a separate
   `National Collegiate Women's Beach` term (id 68); a query excluding it would
   need its own measurement, because a filter that silently drops the wrong
   thing is worse than no filter.
3. **A retention decision on `content`/`excerpt`** — both are present and both
   would be discarded, so the request must use `_fields` rather than fetch
   268 KB and throw most of it away.
4. **Deduplication against the poll crawler**, so the same publication cannot
   appear twice on the site through two systems.

**Requests made for this audit:** five, all read-only, all `GET` —
`robots.txt`, the homepage, `/wp-json/wp/v2/posts` (twice, the second lean via
`_fields`), and `/wp-json/wp/v2/division`. More than the "one conservative
request" the brief allowed for, and worth saying plainly: the first two
established permission and whether a feed exists at all, and the last two were
needed to answer the relevance question that decided the verdict. No page was
scraped for content and nothing was stored.

## Not sources, and will not become sources without a decision

- **VolleyTalk** — a community forum. Blocked by `.claude/hooks/no_scrape.py`
  and by policy; the Weekly Calendar's community track is manual entry only.
- **Social media** — no.
- **Team athletics sites** — already fetched for ROSTERS under a different
  rule; they are not a news source here.
- **Paywalled media** — no.
- **Arbitrary URLs** — there is no field anywhere that lets one be entered, and
  a link pasted into a Film Room note is **never fetched** (guarded).

## Before a second source is added

A new row here is not enough. All of these first:

1. **The owner's terms permit machine reading of that feed**, checked and
   quoted in this file.
2. **A measured audit line** — the same table above, with a real fetch: status,
   size, item count, and the exact field list.
3. **A decision about what is retained**, defaulting to title/link/time/category
   and never article text.
4. **A fixture** saved under `tests/fixtures/intel/` so the parser is tested
   against that source's real shape, including its failure shape.
5. **Failure behaviour stated** — what the desk shows when that source is down,
   and whether it can poison the cache of the others (it must not).

## Before alerts are added (email, text, push)

Not in this phase, and not without:

1. **A delivery decision** — anything leaving the machine is a new privacy
   boundary. Today nothing does.
2. **A rate rule**, so a busy Friday cannot produce forty messages.
3. **A relevance rule that is honest.** Matching is conservative on purpose;
   an alert makes a false match expensive rather than merely untidy.
4. **A quiet-hours rule.**
5. **An off switch that is the default**, and a record of what was sent.
