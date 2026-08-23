# StatBroadcast — what it has, and why we do not crawl it

**Measured 2026-08-23.** Cody pointed at StatBroadcast's live stats pages.

## It has the thing I said we could not have

I closed the rotations question as impossible. That was right **about
ncaa.com's feed** — there, serves are named only on aces, so the serve sequence
cannot be rebuilt. StatBroadcast names the server on **every rally**:

```
[Serve: Thiebaud,Blair] Service error. -- SET WISCONSIN. SV: LOU - PT: WIS (25-18)
[Serve: Simon,Kristen]  Kill by Meester,Chloe (assist from Cabello,Nayelis)
[Serve: Chicoine,Chloe] Kill by Flanagan,Audrey (assist from Fuerbringer,Charlie)
```

**Serve order is rotation order.** A full serve sequence per set gives the
rotation directly, with no inference. The conclusion in
`docs/rotations_finding.md` stands for the ncaa.com feed and is **superseded as
a general claim**: the data exists, in a source we do not currently use.

## Why there is no crawler

`stats.statbroadcast.com` returns **403 to every non-browser client** — tested
with our own honest user-agent, not a spoofed one — and gates the page behind:

> "Access to StatBroadcast services is granted only for **personal,
> non-commercial use through the standard StatBroadcast web interface** and is
> conditioned on acceptance of these Terms."

Personal and non-commercial describes this hub exactly. **"Through the standard
web interface" is the part that rules out an automated client**, and the 403 is
that term being enforced. The "Accept & Continue" gate was **not** clicked on
Cody's behalf.

So: no crawler. Not a technical limit — a terms one, and it does not go away by
being clever about headers.

## The three honest routes

- **A — read it, paste it.** Same pattern as the TV listings: Cody reads a
  match in his browser (which is the permitted use), pastes the lineup or
  rotation, and it is stored as a sourced entry and rendered labelled. Manual,
  and only for matches worth the effort.
- **B — ask them.** StatBroadcast sells data services. A personal-use request
  costs an email and is the only route to doing this automatically.
- **C — leave it.** Rotations stay marked unavailable, as they are now.

## The other two sources

- **VolleyStation** (`avcafirstserve.volleystation.com`) — real match data and
  per-set player stats, and the markup contains a `div.court` and a "Play by
  play" heading. For Louisville–Texas A&M **both are empty** and the scoresheet
  download is 0 bytes. No rotation data there today; worth re-checking during a
  live match, when it may populate.
- **VolleyTalk** — forum content. Already understood: stays out of the public
  repo.
