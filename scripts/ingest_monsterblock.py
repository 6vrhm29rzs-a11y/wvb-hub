#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture themonsterblock.com's daily results as a THIRD reference source.

⚠ WHY THIS ONE IS DIFFERENT FROM MASSEY AND EVOLLVE. Those publish ratings;
this publishes RESULTS -- every match with its full set line. And it is
INDEPENDENTLY SOURCED rather than a mirror of the NCAA feed, which was proven
on 2026-09-12: it carries "Holy Cross 3 @ Manhattan 1 (18-25, 26-24, 27-25,
25-18)" while the feed still says Manhattan won, and Holy Cross's column
matches the correction filed that day digit for digit.

That makes it a real third witness on inverted results -- the gap the
two-source rule keeps running into when a school's own site will not parse
(Little Rock, Wiley, and the 35 JS-rendered athletics sites).

⚠ IT IS A HOBBYIST SITE, run by a VolleyTalk member. There is no robots.txt,
so nothing disallows reading it -- but ONE page per run, no crawling, and it
is a REFERENCE only: it may raise a question about a result, and it may never
by itself correct one. The two-source rule still wants a school.
"""
import datetime
import hashlib
import html
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "Cody", "data", "monsterblock_snapshots.jsonl")
URL = "https://themonsterblock.com/"

ROW = re.compile(
    r'<tr>\s*<td>\s*'
    r'<span class="(winner|loser)"><a class="team-link" href="/teams/([^"]+)/">([^<]+)</a></span>'
    r'.*?'
    r'<span class="(winner|loser)"><a class="team-link" href="/teams/([^"]+)/">([^<]+)</a></span>'
    r'(?:\s*<span class="sets">\(([^)]*)\)</span>)?'
    r'.*?<td class="status">([^<]*)</td>', re.S)
NAME_SETS = re.compile(r"^(.*?)\s+(\d+)$")
RANK_PREFIX = re.compile(r"^#(\d+)\s+")


def clean_name(raw):
    """The source's team string -> (joinable name, the rank it published).

    Two things sit in front of a team name here and BOTH broke the join on
    exactly the matches that matter most (measured 2026-09-13: 22 of 160
    rows had a side that would not resolve, and they were the RANKED ones):
      * the site prefixes a ranked team with its AVCA rank -- "#15 Creighton";
      * team names arrive HTML-escaped -- "Alabama A&amp;M", "St. John&#x27;s (NY)".
    So the third witness was blind precisely where the verification gap is
    (the top 50), which is the inverse of what it was captured for.
    The raw string is kept on the row; this returns what may be joined.
    The published rank is returned rather than discarded -- it is the AVCA
    poll as a third party read it, a fact of its own.
    """
    txt = html.unescape(raw or "").strip()
    m = RANK_PREFIX.match(txt)
    return (txt[m.end():].strip() if m else txt), (int(m.group(1)) if m else None)


def parse(page):
    out, seen = [], set()
    for m in ROW.finditer(page):
        aw, aslug, araw, hw, hslug, hraw, sets, status = m.groups()
        a, h = NAME_SETS.match(araw.strip()), NAME_SETS.match(hraw.strip())
        if not a or not h:
            continue
        key = (aslug, hslug, araw, hraw)
        if key in seen:
            continue                       # a match listed under two conferences
        seen.add(key)
        pairs = []
        for chunk in (sets or "").split(","):
            mm = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", chunk)
            if mm:
                pairs.append([int(mm.group(1)), int(mm.group(2))])
        aname, arank = clean_name(a.group(1))
        hname, hrank = clean_name(h.group(1))
        out.append({"away_slug": aslug, "away": a.group(1).strip(),
                    "away_name": aname, "away_rank_listed": arank,
                    "away_sets": int(a.group(2)),
                    "home_slug": hslug, "home": h.group(1).strip(),
                    "home_name": hname, "home_rank_listed": hrank,
                    "home_sets": int(h.group(2)),
                    "winner": "away" if aw == "winner" else
                              ("home" if hw == "winner" else None),
                    "sets": pairs, "status": (status or "").strip()})
    return out


def hub_keys(hub):
    """Normalised team name -> the hub's own spelling."""
    from external_refs import _ref_norm
    keys = {}
    for t in hub["teams"]:
        n = t.get("name_short")
        if n:
            keys.setdefault(_ref_norm(n), n)
    return keys


def attach_hub(rows, keys):
    """Resolve both sides of each row to hub teams; return how many joined.

    Joins on the CLEANED name -- "away"/"home" stay exactly what the page said,
    so the snapshot remains a faithful record of the source.
    """
    from external_refs import _ref_norm
    hit = 0
    for r in rows:
        for side in ("away", "home"):
            r[side + "_hub"] = keys.get(_ref_norm(r[side + "_name"]))
        if r["away_hub"] and r["home_hub"]:
            hit += 1
    return hit


def unchanged(path, sha):
    """True when the newest stored snapshot already carries exactly this content.

    APPEND ONLY WHEN THE CONTENT MOVES -- the crawl_polls rule. local_refresh
    runs this ingester every cycle, so on a quiet evening the same day's results
    were written again every 20 minutes: 16 of the first 17 snapshots held
    byte-identical payloads. Append-only means a stored row is never rewritten,
    not that an unchanged one must be stored again.
    """
    prev = None
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            if line.strip():
                try:
                    prev = json.loads(line).get("content_sha256")
                except ValueError:
                    pass
    return prev is not None and prev == sha


def main():
    import urllib.request
    if "--file" in sys.argv:
        page = io.open(sys.argv[sys.argv.index("--file") + 1],
                       encoding="utf-8", errors="replace").read()
        fetched = "local file"
        # A file read is not a retrieval; only an env-supplied time can say
        # when the bytes were actually taken from the site.
        retrieved = os.environ.get("MB_RETRIEVED", "")
    else:
        req = urllib.request.Request(URL, headers={"User-Agent":
                                     "wvb-hub reference check (one page per run)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            page = r.read().decode("utf-8", "replace")
        fetched = URL
        # We did the fetching, so the retrieval time is a fact this script
        # holds -- it must not depend on an env var being remembered (14 of
        # the first 17 snapshots carried an empty one). The publisher's own
        # date heading stays a separate field: two facts, never collapsed.
        retrieved = os.environ.get("MB_RETRIEVED") or (
            datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    rows = parse(page)
    if not rows:
        raise SystemExit("no match rows parsed -- the page layout may have "
                         "changed; look before trusting anything downstream")
    date = None
    dm = re.search(r'<h2 class="date-heading">([^<]+)</h2>', page)
    if dm:
        date = dm.group(1).strip()

    hub = json.load(io.open(os.path.join(REPO, "data/data_%d.json" % SEASON),
                            encoding="utf-8"))
    hit = attach_hub(rows, hub_keys(hub))

    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    snap = {"source": "themonsterblock.com", "url": URL,
            "source_label": "The Monster Block daily results (community site)",
            "role": ("external RESULTS reference -- may raise a question about "
                     "a result, may never by itself correct one"),
            "access": ("one page per run, no crawling; no robots.txt exists on "
                       "the host. Hobbyist site run by a VolleyTalk member."),
            "publisher_date_heading": date,
            "retrieved_utc": retrieved,
            "fetched": fetched, "n_rows": len(rows),
            "both_sides_resolved": hit,
            "content_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "rows": rows}
    if unchanged(OUT, snap["content_sha256"]):
        print("monsterblock: %d matches for %s; both sides joined on %d "
              "(unchanged since the last snapshot -- nothing appended)"
              % (len(rows), date or "?", hit))
    else:
        with io.open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
        print("monsterblock: %d matches for %s; both sides joined on %d"
              % (len(rows), date or "?", hit))
        print("  ->", OUT)
    # The cross-check below runs on EVERY invocation either way -- it is the
    # point of the run, and it costs nothing.

    import season_counts as SC
    best = {}
    for line in io.open(os.path.join(REPO, "data/raw/%d/games.jsonl" % SEASON),
                        encoding="utf-8"):
        try:
            g = json.loads(line)
        except ValueError:
            continue
        gid = str(g.get("game_id")); prev = best.get(gid)
        if prev is None or g.get("game_state") == "F" or prev.get("game_state") != "F":
            best[gid] = g
    cls = SC.classify(list(best.values()), SEASON)
    corr = SC.corrections(SEASON)
    nm_of = {t["team_id"]: t.get("name_short") for t in hub["teams"]}
    ours = {}
    for gid, g in best.items():
        g2 = SC.apply_correction(g, corr)
        w = SC.winner_index(g2)
        ts = g2.get("teams") or []
        if len(ts) != 2:
            continue
        pair = sorted(n for n in (nm_of.get(t.get("team_id")) for t in ts) if n)
        if len(pair) != 2:
            continue
        ours[tuple(pair)] = (gid, cls.get(gid),
                             nm_of.get(ts[w]["team_id"]) if w is not None else None)

    # POWER ranks, so a disagreement can be weighted by who it involves
    ranks = {}
    try:
        import re as _re
        _page = io.open(os.path.join(REPO, "Cody", "START-HERE.html"),
                        encoding="utf-8").read()
        _T = json.loads(_re.search(r"const TEAMS\s*=\s*(\{.*?\});\n",
                                   _page, _re.S).group(1))
        ranks = {nm: t.get("rank") for nm, t in _T.items() if t.get("rank")}
    except Exception:                                     # noqa: BLE001
        pass

    agree = dis = miss = 0
    notes = []
    for r in rows:
        a, h = r.get("away_hub"), r.get("home_hub")
        if not (a and h) or (r.get("status") or "").upper() != "FINAL":
            continue
        mbw = a if r["winner"] == "away" else h
        key = tuple(sorted((a, h)))
        if key not in ours:
            miss += 1
            notes.append("  NOT IN OUR LOG  %s vs %s -- they have %s winning"
                         % (a, h, mbw))
            continue
        gid, c, ourw = ours[key]
        if c != "ok":
            notes.append("  we HOLD as %-18s %s vs %s -- they have %s winning"
                         % (c, a, h, mbw))
            continue
        if ourw != mbw:
            dis += 1
            best_rank = min([r for r in (ranks.get(a), ranks.get(h)) if r] or [999])
            notes.append("  %s DISAGREE  %s (#%s) vs %s (#%s) -- ours %s, "
                         "theirs %s (gid %s). Go to BOTH schools before "
                         "believing either."
                         % ("⚠⚠ TOP-50" if best_rank <= 50 else "⚠",
                            a, ranks.get(a) or "-", h, ranks.get(h) or "-",
                            ourw, mbw, gid))
        else:
            agree += 1
    print("\ncross-check against our counted results: "
          "agree %d · disagree %d · not in our log %d" % (agree, dis, miss))
    # loudest first: a top-50 disagreement is the one that matters
    for n in sorted(notes, key=lambda x: (0 if "TOP-50" in x else 1, x)):
        print(n)
    if dis:
        print("\n⚠ A DISAGREEMENT IS A PLACE TO LOOK, NOT A CORRECTION. This "
              "source is one witness; the ledger still wants two schools.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
