#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read the schools' own words about the players the box scores flagged.

Cody, 2026-09-13: "create a new system that can infer that based on data,
volleytalk posts, etc. versus me adding info and telling you. i can't be the
catch for everything."

The box-score leg is participation_radar.py: it says WHO has stopped
appearing. This is the text leg: it goes to the school's own published
recaps and previews and looks for the school SAYING something about her.

WHAT IT PRODUCES: candidate SIGNALS, each carrying the sentence verbatim,
the URL it came from and when it was read. Nothing else.

⚠ IT CAN NEVER SET AN AVAILABILITY STATUS. In this codebase a status may
only be created by a human filing an attributable source into
availability_evidence.json with its exact wording, a review-by date and a
claim from a CLOSED set. A machine that both finds and believes its own
evidence has no second witness -- the same reason the duplicate detector and
the fixture-time check write candidates only.

⚠ EVIDENCE BINDS TO ITS OWN SENTENCE (R8, and the USC-Arizona St. incident
of 2026-08-29, where a "Scrimmage / Exhibition" descriptor was read from a
NEIGHBOURING card inside a 3,000-character window and a counting match was
ledgered as an exhibition). A phrase found 400 characters from a surname
proves nothing about that player. The surname and the phrase must occur in
the SAME sentence, and the surname must match a roster surname as a whole
token.

⚠ IT READS ONLY WHAT THE SCHOOL PUBLISHES ABOUT ITS OWN TEAM. VolleyTalk is
not read here: proboards now serves a proof-of-work bot challenge to
non-browser clients, and scripting around that is bot-detection bypass.

Run: python3 scripts/availability_scan.py [--limit N]
"""

import datetime
import io
import json
import os
import re
import sys
from html import unescape as _unescape

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SEASON = int(os.environ.get("WVB_SEASON", "2026"))
OUT = os.path.join(REPO, "data", "availability_scan_%d.json" % SEASON)
IDS = os.path.join(REPO, "data", "raw", str(SEASON), "wmt_sport_ids.json")

# ⚠ PHRASES THAT DESCRIBE PARTICIPATION, NOT CONDITION. The scan looks for a
# school saying a player did not or will not play. It does NOT look for
# diagnoses: "torn", "surgery", "concussion" and the like are deliberately
# absent, because a machine that harvests medical words about named athletes
# is doing something this project will not do. A human reading the linked
# article decides what it means.
PHRASES = [
    "did not play", "did not dress", "was unavailable", "is unavailable",
    "will not play", "will miss", "has missed", "out of the lineup",
    "out of the rotation", "did not travel", "has not played",
    "returned to the lineup", "returned to action", "back in the lineup",
    "made her return", "in street clothes", "held out",
]
RETURN_PHRASES = {"returned to the lineup", "returned to action",
                  "back in the lineup", "made her return"}


def sentences(text):
    text = re.sub(r"\s+", " ", text or "")
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def main():
    import verify_results_daily as V

    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    radar_p = os.path.join(REPO, "data",
                           "participation_radar_%d.json" % SEASON)
    radar = json.load(io.open(radar_p, encoding="utf-8")) if \
        os.path.exists(radar_p) else {"players": []}
    # who to look for, per team: the flagged players only. Scanning every
    # roster would be a lot of requests to say nothing.
    want = {}
    for r in (radar.get("players") or []):
        want.setdefault(r["team"], []).append(r)
    teams = sorted(want)
    if limit:
        teams = teams[:limit]

    sites = V._sites()
    try:
        ids = json.load(io.open(IDS, encoding="utf-8"))
    except (OSError, ValueError):
        ids = {}

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    signals, reached, unreadable = [], 0, []
    # ⚠ COUNT WHAT WAS READ, NOT ONLY WHAT WAS FOUND. "0 signals" from a scan
    # that opened nothing and "0 signals" from a scan that read 27,000 words
    # are the same line of output and completely different facts. A
    # measurement that returns nothing has to be positive-controlled before
    # it is believed -- this file carries its own control.
    articles_read = 0
    chars_scanned = 0
    for team in teams:
        base = sites.get(team)
        sid = ids.get(team)
        if not base or not sid:
            unreadable.append(team)
            continue
        url = (base + "/website-api/schedule-events?filter%5Bschedule."
               "sport_id%5D=" + str(sid) + "&filter%5Bpast%5D=true"
               "&per_page=6&sort=-datetime"
               "&include=postEventArticle,preEventArticle")
        with V._host_lock(base):
            st, body, _fu = V._fetch(url)
        if st != 200 or not body:
            unreadable.append(team)
            continue
        try:
            doc = json.loads(body)
        except ValueError:
            unreadable.append(team)
            continue
        reached += 1
        # ⚠ THE API CARRIES A HEADLINE AND A LINK, NOT THE STORY. The article
        # include returns title/slug/permalink only, and "did not play" is
        # never in a headline -- the first version of this scan searched
        # titles, found nothing, and would have read as "no news" when it had
        # simply not opened anything. The body is server-rendered on the
        # school's own page, so the permalink is fetched and its paragraphs
        # are read.
        arts = []
        seen_urls = set()
        for ev in (doc.get("data") or []):
            for k in ("post_event_article", "pre_event_article"):
                a = ev.get(k) or {}
                u = a.get("permalink") or a.get("url")
                if not u:
                    continue
                if not u.startswith("http"):
                    u = base.rstrip("/") + "/" + u.lstrip("/")
                if u in seen_urls or len(seen_urls) >= 4:
                    continue
                seen_urls.add(u)
                with V._host_lock(base):
                    ast, ahtml, _au = V._fetch(u)
                if ast != 200 or not ahtml:
                    continue
                paras = []
                for m in re.finditer(r"<p[^>]*>(.*?)</p>", ahtml, re.S):
                    t2 = re.sub(r"\s+", " ",
                                re.sub(r"<[^>]+>", " ", m.group(1))).strip()
                    # the site chrome renders as <p> too; a paragraph that is
                    # navigation is not the story
                    if len(t2) < 60 or "Opens in a new window" in t2 \
                            or "Tickets for" in t2:
                        continue
                    paras.append(_unescape(t2))
                if paras:
                    articles_read += 1
                    chars_scanned += sum(len(x) for x in paras)
                    arts.append({
                        "kind": k, "text": " ".join(paras), "url": u,
                        "title": a.get("title"),
                        "published": ev.get("datetime"),
                    })
        for pl in want[team]:
            surname = (pl["player"].split()[-1] if pl.get("player") else "")
            if len(surname) < 3:
                continue
            pat = re.compile(r"\b%s\b" % re.escape(surname), re.I)
            for a in arts:
                for sent in sentences(a["text"]):
                    if not pat.search(sent):
                        continue
                    hit = [p for p in PHRASES if p in sent.lower()]
                    if not hit:
                        continue
                    signals.append({
                        "team": team, "player": pl["player"],
                        "matched_surname": surname,
                        "phrase": hit[0],
                        "direction": ("return" if hit[0] in RETURN_PHRASES
                                      else "absence"),
                        "quote": sent[:400],
                        "source_url": a["url"],
                        "source_title": a.get("title"),
                        "source_kind": "school article (" + a["kind"] + ")",
                        "published": a.get("published"),
                        "retrieved_utc": now,
                        "status": "UNREVIEWED CANDIDATE -- a school's own "
                                  "words, quoted. Not an availability "
                                  "status; a human files one or does not.",
                    })
    doc = {
        "season": SEASON, "generated_utc": now,
        "teams_with_a_flagged_player": len(want),
        "teams_reached": reached,
        "teams_unreadable": len(unreadable),
        "phrases": PHRASES,
        "binding_rule": "the surname and the phrase must appear in the SAME "
                        "sentence, and the surname must match as a whole "
                        "token (R8; the USC-Arizona St. incident)",
        "what_this_is_not": "Not an availability status and not a diagnosis. "
                            "No medical vocabulary is searched for at all.",
        "articles_read": articles_read,
        "chars_scanned": chars_scanned,
        "reading_note": "school recaps describe what happened and rarely "
                        "state that a player was unavailable; a run that "
                        "reads thousands of words and returns no signal is "
                        "the expected result from this source, which is why "
                        "the counters above are recorded.",
        "n": len(signals), "signals": signals,
    }
    json.dump(doc, io.open(OUT, "w", encoding="utf-8"), indent=1)
    print("teams with a flagged player: %d; reached %d; unreadable %d"
          % (len(want), reached, len(unreadable)))
    print("articles read: %d (%d characters of story text)"
          % (articles_read, chars_scanned))
    print("candidate signals: %d" % len(signals))
    print("wrote %s" % OUT)
    for s in signals[:12]:
        print("  %-18s %-22s %-18s %s"
              % (s["team"][:18], s["player"][:22], s["phrase"],
                 s["quote"][:70]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
