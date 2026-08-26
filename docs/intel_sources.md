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
