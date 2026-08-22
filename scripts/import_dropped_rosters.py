#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import rosters Cody drops in Cody/rosters_dropbox/ into the 2026 roster file.

WHY THIS EXISTS. 34 teams have no roster because their site defeats the crawler
-- dead domains, JS-rendered pages, templates the parser cannot read. Four of
them are in our top 50. A person with a browser can get those pages in seconds,
so this is the fastest path to closing the gap, and it does not require guessing
anything.

TWO INPUT FORMATS, both fine, pick whichever is less work:

  1. A SAVED WEB PAGE  -- "Southern California.html"
     In the browser, File > Save Page As, format "Page Source" (not "Complete").
     Parsed by the SAME parser the crawler uses, so it gets the same guards.

  2. A PLAIN TEXT LIST -- "Southern California.txt"
     One player per line. Anything after the name is optional and free-form:
         Kassie O'Brien, So, S
         12  Trinity Ward  Sophomore  DS
         Georgia Watson
     Leading jersey numbers and trailing class/position tokens are picked off if
     present, and ignored if not. Blank lines and lines starting with # skipped.

THE FILENAME IS THE TEAM NAME. Use the name as it appears in the ranking table
("Southern California", "Utah St.", "Kansas St.", "Georgia Tech"). Case and
punctuation are forgiving; an unrecognised name is REPORTED, never guessed into
the nearest match -- a roster filed under the wrong team is worse than a missing
one, because it silently reassigns a whole squad's production.

DURABLE. Parsed results are also written to data/raw/2026/rosters_manual.json,
so a full re-crawl cannot wipe them -- re-run this script and they come back.

Idempotent. Safe to run repeatedly. Run:  python3 scripts/import_dropped_rosters.py
"""

import json
import os
import re
import sys
import time
import glob
import plistlib
from html import unescape as _unescape
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_rosters as cr  # noqa: E402
from reconcile_2025 import norm  # noqa: E402

DROP = os.path.join(REPO, "Cody", "rosters_dropbox")
ROSTERS = os.path.join(REPO, "data", "raw", "2026", "rosters_2026.json")
MANUAL = os.path.join(REPO, "data", "raw", "2026", "rosters_manual.json")

CLASS_WORDS = re.compile(
    r"\b(fr|so|jr|sr|gr|freshman|sophomore|junior|senior|graduate|"
    r"r-?fr|r-?so|r-?jr|r-?sr|redshirt(\s+\w+)?)\b", re.I)
POS_WORDS = re.compile(r"\b(OH|MB|OPP|RS|DS|L|S|LIB|SETTER|OUTSIDE|MIDDLE)\b", re.I)
# A person's name: at least two capitalised words. Same shape rule the crawler
# uses, so a text drop cannot smuggle in something the HTML path would reject.
NAME = re.compile(r"^[A-Z][A-Za-z'`À-ɏ.-]+(?:\s+[A-Z][A-Za-z'`À-ɏ.-]+){1,3}$")


# Positions and class tokens mark where a player's NAME stops on a print-view
# line like "8 Mia Tvrdy MB 6' 1'' Jr. La Vista, Neb." -- without them the name
# swallows the rest of the row.
POS_TOKENS = {"OH", "MB", "OPP", "RS", "DS", "L", "S", "LIB", "MH", "DEF",
              "L/DS", "S/DS", "OH/RS", "OPP/RS", "MB/OH", "S/RS", "DS/L"}
CLASS_TOKEN = re.compile(r"^(r-)?(fr|so|jr|sr|gr)\.?$", re.I)


def webarchive_html(path):
    """The ORIGINAL page source out of a Safari .webarchive.

    textutil flattens a webarchive into styled text and drops the anchors the
    HTML parser needs, so go to the plist directly. Also returns the page's own
    URL, which identifies the team far more reliably than a filename does.
    """
    with open(path, "rb") as fh:
        d = plistlib.load(fh)
    main = d.get("WebMainResource") or {}
    data = main.get("WebResourceData") or b""
    return data.decode("utf-8", "replace"), main.get("WebResourceURL")


def html_to_lines(html):
    """Collapse a roster page to one line per table row."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?i)</(tr|div|p|li|h[1-6])>", "\n", t)
    t = re.sub(r"(?i)</t[dh]>", "\t", t)
    t = _unescape(re.sub(r"<[^>]+>", " ", t))
    out = []
    for line in t.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            out.append(line)
    return out


def name_from_line(line):
    """Take the leading run of name-shaped tokens, stopping at the first
    position / class / height / numeric token."""
    toks = line.split()
    got = []
    for tok in toks:
        bare = tok.strip(".,|")
        if bare.upper() in POS_TOKENS or CLASS_TOKEN.match(bare):
            break
        if re.search(r"[0-9'\"]", tok):
            break
        if not re.match(r"^[A-Z][A-Za-z'`\u00c0-\u024f.-]*$", bare):
            break
        got.append(bare)
        if len(got) >= 4:
            break
    return " ".join(got) if len(got) >= 2 else None


def domain_map() -> Dict[str, str]:
    """host -> our team name, from the crawler's own resolved-sites file.

    A saved page carries the URL it came from, and that identifies the team far
    more reliably than a filename does ("USC Athletics.webarchive" tells you
    little; usctrojans.com is unambiguous). Filename matching stays as the
    fallback for formats that carry no URL.
    """
    out = {}
    sp = os.path.join(REPO, "data", "raw", "2026", "athletics_sites.json")
    if not os.path.exists(sp):
        return out
    for team, meta in json.load(open(sp)).items():
        url = (meta.get("url") or "").strip()
        if not url:
            continue
        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
        host = re.sub(r"^www\.", "", host)
        if host:
            out[host] = team
    return out


def canon_map() -> Dict[str, str]:
    """our canonical team names, keyed by a squashed form"""
    out = {}
    rosters = json.load(open(ROSTERS))["teams"]
    for name in rosters:
        out[re.sub(r"[^a-z0-9]", "", norm(name).lower())] = name
    return out


def parse_text(body: str) -> List[Dict[str, Optional[str]]]:
    players = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # strip a leading jersey number
        num = None
        m = re.match(r"^#?\s*(\d{1,2})\b[\s.,:-]*(.+)$", line)
        if m:
            num, line = m.group(1), m.group(2).strip()
        # class / position tokens, wherever they sit
        cls = CLASS_WORDS.search(line)
        pos = POS_WORDS.search(line)
        # Print-view rows are single-spaced ("Mia Tvrdy MB 6' 1'' Jr. ..."), so
        # splitting on separators returns the whole row. Take the leading run of
        # name-shaped tokens instead, then fall back to the separator split for
        # comma/tab/pipe formatted pastes.
        name = name_from_line(line)
        if not name:
            name = re.split(r"\s*[,|\t]\s*|\s{2,}", line)[0].strip()
            name = re.sub(r"\s+", " ", CLASS_WORDS.sub("", name)).strip(" ,-|")
        if not name or not NAME.match(name):
            continue
        players.append({
            "first": name.split(" ")[0],
            "last": " ".join(name.split(" ")[1:]) or None,
            "name_raw": name,
            "class_raw": cls.group(0) if cls else None,
            "pos_raw": pos.group(0).upper() if pos else None,
            "num_raw": num,
            "how": "manual-text",
        })
    # DROP HEADER AND BOILERPLATE ROWS. A print view yields "Full Name",
    # "High School" and the site's own title alongside the real rows, and all of
    # them are two capitalised words -- name-shaped. Real rows in a structured
    # table always carry a jersey number, position or class; header rows carry
    # none. So: if ANY row in this file is structured, require it of every row.
    # If NO row is (a freeform list of bare names), keep them all.
    structured = any(p["num_raw"] or p["pos_raw"] or p["class_raw"] for p in players)
    if structured:
        players = [p for p in players
                   if p["num_raw"] or p["pos_raw"] or p["class_raw"]]

    # de-duplicate the same way the crawler does
    seen, out = set(), []
    for p in players:
        k = re.sub(r"[^a-z]", "", p["name_raw"].lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def main():
    if not os.path.isdir(DROP):
        os.makedirs(DROP)
    files = sorted(glob.glob(os.path.join(DROP, "*.html")) +
                   glob.glob(os.path.join(DROP, "*.htm")) +
                   glob.glob(os.path.join(DROP, "*.txt")) +
                   glob.glob(os.path.join(DROP, "*.webarchive")))
    files = [f for f in files if not os.path.basename(f).upper().startswith("README")]
    if not files:
        print("nothing in %s" % DROP)
        print("drop a saved roster page or a text list named after the team, then re-run.")
        return 0

    canon = canon_map()
    domains = domain_map()
    rosters = json.load(open(ROSTERS))
    manual = {}
    if os.path.exists(MANUAL):
        manual = json.load(open(MANUAL)).get("teams", {})

    added, skipped, unknown = 0, 0, []
    for path in files:
        base = os.path.basename(path)
        stem, ext = os.path.splitext(base)
        ext = ext.lower()
        src_url = None

        if ext == ".webarchive":
            try:
                body, src_url = webarchive_html(path)
            except Exception as exc:
                print("  %-40s unreadable webarchive: %s" % (base[:40], exc))
                skipped += 1
                continue
            # Print views carry no player links, so read the table as text;
            # a full page still parses better through the HTML parser.
            players = cr.parse_roster(body)
            how = "manual-webarchive-html"
            if len(players) < 8:
                alt = parse_text("\n".join(html_to_lines(body)))
                if len(alt) > len(players):
                    players, how = alt, "manual-webarchive-text"
        elif ext in (".html", ".htm"):
            body = open(path, encoding="utf-8", errors="replace").read()
            players = cr.parse_roster(body)
            how = "manual-html"
            if len(players) < 8:
                alt = parse_text("\n".join(html_to_lines(body)))
                if len(alt) > len(players):
                    players, how = alt, "manual-html-text"
        elif ext == ".txt":
            players = parse_text(open(path, encoding="utf-8", errors="replace").read())
            how = "manual-text"
        else:
            print("  %-40s unsupported format %s -- see README" % (base[:40], ext))
            skipped += 1
            continue

        # Identify the team by the page's own URL first, filename second.
        team = None
        if src_url:
            host = re.sub(r"^www\.", "",
                          re.sub(r"^https?://", "", src_url).split("/")[0].lower())
            team = domains.get(host)
        if not team:
            team = canon.get(re.sub(r"[^a-z0-9]", "", norm(stem).lower()))
        if not team:
            unknown.append("%s%s" % (base, ("  [url %s]" % src_url) if src_url else ""))
            continue

        if not players:
            print("  %-26s %-14s 0 players parsed -- SKIPPED" % (team, base))
            skipped += 1
            continue
        if len(players) > 30:
            # A real D-I roster is ~14-24. Well past that means the file caught
            # staff or a whole page of links; refuse rather than pollute.
            print("  %-26s %-14s %d players -- REFUSED, implausible (staff or wrong page?)"
                  % (team, base, len(players)))
            skipped += 1
            continue

        rec = {
            "status": "ok",
            "url": "manual drop: %s" % base,
            "platform": how,
            "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            # The roster itself is the school's own published list, so OFFICIAL;
            # the CAPTURE was by hand, which the label keeps visible.
            "source_tier": "OFFICIAL (manual capture)",
            "team_id": (rosters["teams"].get(team) or {}).get("team_id"),
            "players": players,
        }
        prev = len((rosters["teams"].get(team) or {}).get("players") or [])
        # DO NOT LET A PARTIAL DROP DESTROY A GOOD ROSTER. A truncated paste --
        # six lines copied out of a table of seventeen -- would otherwise
        # silently replace a complete crawl, and the eleven missing players
        # would read as DEPARTED. Same rule as the daily pipeline's "the game
        # log must not shrink" gate: a big drop is a defect signal, not an
        # update. Pass --force when the shrink is real (a squad that actually
        # got smaller).
        if prev and len(players) < 0.7 * prev and "--force" not in sys.argv:
            print("  %-26s %-14s %d players but %d already on file -- REFUSED "
                  "(would lose %d; re-run with --force if this is real)"
                  % (team, base, len(players), prev, prev - len(players)))
            skipped += 1
            continue
        rosters["teams"][team] = rec
        manual[team] = rec
        flag = ""
        if len(players) < 12:
            flag = "  <-- only %d, check the file caught the whole roster" % len(players)
        print("  %-26s %-14s %2d players (was %d)%s" % (team, base, len(players), prev, flag))
        added += 1

    json.dump({"meta": {"season": 2026,
                        "note": "rosters captured by hand and dropped in Cody/rosters_dropbox/; "
                                "kept here so a full re-crawl cannot lose them",
                        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
               "teams": manual}, open(MANUAL, "w"), indent=1)

    rosters["meta"]["manual_imports"] = len(manual)
    json.dump(rosters, open(ROSTERS, "w"), indent=1)

    print("\nimported %d, skipped %d" % (added, skipped))
    if unknown:
        print("\nFILENAME NOT RECOGNISED as a team -- rename and re-run "
              "(not guessed on purpose):")
        for u in unknown:
            print("   %s" % u)
    left = sorted(t for t, v in rosters["teams"].items() if not v.get("players"))
    print("\nstill without a roster: %d teams" % len(left))
    if added:
        print("\nnext: python3 scripts/join_players.py "
              "&& WVB_SEASON=2026 python3 scripts/build_vb.py "
              "&& python3 scripts/build_rankings_board.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
