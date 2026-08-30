# Source Intelligence Foundation — source & capability inventory

2026-08-30. Every access claim below is MEASURED — either probed today or
carrying the date of the recorded measurement (docs/data_sources.md,
CLAUDE.md). A source that cannot be fetched reliably by a plain, honest
client is listed as NOT an automated source, whatever it contains.

## Source classes and what each can reliably provide

### official_ncaa — ncaa.com via ncaa-api (probe today: HTTP 200)
The pipeline's existing feed. Scoreboard by date, /game detail (teams,
linescores, venue, epoch), boxscores, PBP, rankings (current-only).
RELIABILITY CAVEATS ARE MEASURED AND LEDGERED: start times hours wrong,
`pre` long after a final, empty finals, inverted winners, phantom 0-0
sets, deleted games, duplicate listings. It is the BACKBONE and it is
exactly why the evidence ledgers exist.
Provides: schedules, results, box stats, venues (sometimes), TV network
(sparse). Role: primary record, never sole confirmation.

### official_school — athletics sites (probe today: usctrojans.com 200)
346/348 rosters already crawl from these; schedule pages carry results
("W, 3-0"), venue, event, time, and schema.org events. Templates:
SIDEARM/WMT readable as HTML; some (thesundevils.com) are JS shells —
those schools are read-only-by-browser and are NOT automated sources.
Recaps/gamebooks exist per school; formats vary too much for v1
automation — used on demand as citations (the Kent St., Iona, USC cases).
Provides: result confirmation, venue/event/time correction evidence,
availability announcements (rare, but official when present).
Role: THE confirmation tier. Already powering result_evidence.json,
fixture_ledger.json, result_corrections.json, duplicate_listings.json.
⚠ Card-boundary rule (R8-scrape): evidence binds to its own DOM card.

### official_broadcast — TV listings
Current source is the hand-transcribed file (Cody/data/tv_listings_2026.txt,
private, not ours to publish) plus the feed's sparse `network` field
(carried on some games — Kansas-Stanford showed ESPN today). No open,
reliable, automatable national TV API was found earlier and none is
claimed now. Role: fixture_update evidence when the feed carries it;
the transcription stays private context.

### reputable_media — AVCA, beat coverage
AVCA poll via ncaa.com rankings endpoint (already crawled daily;
avca.org/polls/ itself 404s — the ncaa.com mirror IS the poll page,
measured 2026-08-11). Beat reporting is browser-reading, not crawling.
Role: poll capture (automated, already live); everything else is
lead/citation only.

### community — VolleyTalk (probe today: HTTP 202 proof-of-work challenge)
NOT an automated source. curl receives a bot challenge; we do not script
around bot protection. Readable in Cody's real Chrome as ordinary
browsing. Role: LEADS ONLY — a community claim can never confirm
anything and never renders as more than a signal.

### blocked / out of bounds (unchanged)
statbroadcast.com, bcsstats.com, stats.ncaa.org, volleyballmag.com,
masseyratings.com — no-scrape hook enforces. Paywalled or
access-controlled anything: not sources.

## What v1 therefore automates
The six evidence ledgers already practice evidence-first capture
(url + exact excerpt + retrieved + per-field support + review dates).
v1 UNIFIES them into one claims layer with the seven states, feeds a
bounded "What changed" area on Today, and adds team-page timelines —
no new crawling, no new source risk, no ranking input.
