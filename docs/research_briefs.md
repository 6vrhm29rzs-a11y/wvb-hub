# Briefs for the other seats (Claude app / ChatGPT / Gemini)

Paste one whole block into a fresh chat. Each is self-contained — they have no
access to this repo and should not be sent looking for one.

**⚠ Do NOT tell them to read the Google Drive.** Five stale docs sit in the root
with neutral titles, and the worst is called "00 - START HERE". It says TCV is
the agreed metric — TCV *lost* the bake-off. They would read it first and build
on it.

**Keep them out of:** architecture (the Drive already holds a rejected Cloud Run
+ BigQuery + Firebase proposal), anything needing the code or data, and UI.

**How their answers get used here:** as CLAIMS to verify, not facts. Anything
about a specific player becomes an explicit, sourced override — never an
inferred adjustment. A brief with no source attached is not usable.

---

## 1. Conference tournament formats for 2026  ← highest value

> I need to know, for the 2026 NCAA Division I **women's volleyball** season,
> how each conference awards its automatic bid to the NCAA tournament: by
> **conference tournament**, or by **regular-season champion**.
>
> I already have 2025 evidence for all of them, from NCAA.com's own tracker: 29
> awarded by tournament, 3 by regular-season champion (ACC, Big 12, WCC). What I
> need is **what changed for 2026**. I know of two changes: the Big Ten and the
> Pac-12 are both adding a conference tournament for 2026.
>
> Please check each of these 32 conferences for 2026 and tell me whether it
> holds a volleyball conference tournament, and if so how many teams qualify:
> ACC, America East, American, ASUN, Atlantic 10, Big 12, Big East, Big Sky,
> Big South, Big Ten, Big West, CAA, Conference USA, Horizon, Ivy, MAAC, MAC,
> MEAC, Missouri Valley, Mountain West, NEC, Ohio Valley, Pac-12, Patriot, SEC,
> Southern, Southland, Summit, Sun Belt, SWAC, WCC, Western Athletic.
>
> Rules for your answer:
> - Give me a **link** for each one — the conference's own site or its 2026
>   championship page is best.
> - If you cannot confirm one for 2026, say **"not confirmed"** and tell me what
>   the 2025 format was. Do not guess, and do not carry a 2025 format forward as
>   if it were 2026. A wrong answer here is worse than no answer.
> - Flag anything that looks like a format change from 2025.
> - Note: the Western Athletic Conference has only one D-I volleyball member
>   left (UT Arlington). Tell me whether it awards a bid at all for 2026.

---

## 2. Injury and availability context for the top ~30 teams

> I follow NCAA Division I **women's volleyball**. Official box-score data tells
> me who played and how they did — it never tells me *why* someone's numbers are
> what they are. I want the context that only beat writers, coaches' pressers
> and forums carry.
>
> For the top ~30 teams going into 2026 (Nebraska, Texas, Kentucky, Louisville,
> Pittsburgh, Wisconsin, Stanford, Penn St., Creighton, Arizona St., SMU,
> Purdue, Minnesota, Texas A&M, and similar), please find:
>
> 1. **Players who played through a known injury in 2025** — their 2025 stats
>    understate them. (Example I already know: Brooklyn DeLeye of Kentucky played
>    the whole 2025 season on a torn meniscus and had off-season surgery.)
> 2. **Players who got hurt late in 2025** and whose availability for 2026 is in
>    question — their 2025 stats *overstate* what they'll give in 2026.
> 3. **Season-ending injuries already announced for 2026.**
> 4. **Announced redshirts, medical retirements, or players who left the
>    programme after the roster published.**
>
> For each: player, school, what happened, expected status, **and a link**.
> Say "no reliable reporting found" where there is none — I would rather have a
> short sourced list than a long unsourced one. Do not infer an injury from a
> drop in playing time; I can see playing time already.

---

## 3. StatBroadcast — is there a legitimate way to get the data?

> StatBroadcast (statbroadcast.com) hosts live official scoring for a lot of US
> college sports. Their live play-by-play names the server on **every rally**,
> which for volleyball means the serving rotation is fully recoverable — the
> NCAA's own public API does not include this.
>
> Their pages return HTTP 403 to any non-browser client, and their terms say
> access is for "personal, non-commercial use **through the standard
> StatBroadcast web interface**".
>
> I want to use this for a personal, non-commercial project — one person's
> hobby site, not redistributed. Please tell me:
> 1. What their terms of service and any developer/API documentation actually
>    say about automated access. Quote the relevant passages with links.
> 2. Whether they offer a data product, API, or personal-use licence, and what
>    it costs.
> 3. Who to contact and what a personal-use access request should say.
> 4. Whether any **other** public source carries per-rally serve order for NCAA
>    women's volleyball — NCAA.com's API does not (serves are only named on
>    aces).
>
> Do not suggest ways to get around the 403 or the terms. I am asking how to do
> this **with permission**, or to establish that I cannot.

---

## 4. Two sources I am blocked from

> Two websites block me and I want to know whether there is a legitimate route.
>
> 1. **VolleyballMag.com** — every page returns 403 (Cloudflare). Their RSS feed
>    works but carries no NCAA women's content. Do they offer a subscription,
>    API, newsletter or syndication feed that includes NCAA D-I women's
>    volleyball coverage?
> 2. **Massey Ratings** (masseyratings.com) — do they publish terms for personal,
>    non-commercial use of their ratings, and is there a data feed or licence?
>
> Also: where can I get the **historical AVCA coaches poll** for women's
> volleyball — every weekly poll for past seasons, not just the current one? I
> believe AVCA publishes an archive. Links please.
>
> Quote terms with links. Do not suggest circumventing any block.

---

## 5. Pre-registered predictions (makes my model falsifiable)

> I run a statistical model for NCAA D-I women's volleyball. Before I measure
> anything, I want your predictions written down first, so I can score them
> honestly rather than explaining results after the fact.
>
> Give me a number or a direction for each, plus one sentence of reasoning:
>
> 1. How much of a team's 2026 performance is predicted by its 2025 performance
>    alone? (I measure it as a rank correlation.)
> 2. Does adding roster turnover to that prediction help, and by how much?
> 3. Does the share of last season's production that left the programme entirely
>    predict a decline, prospectively?
> 4. Which matters more for winning a match: hitting percentage differential, or
>    points-per-set differential?
> 5. How big is home-court advantage in college volleyball, in points per set?
> 6. Name three teams you think the 2026 preseason polls have **wrong**, and say
>    which direction.
>
> Commit to specific numbers where you can. I will tell you afterwards what I
> measured. Do not hedge every answer into uselessness — a wrong specific
> prediction is more useful to me than a vague right one.
