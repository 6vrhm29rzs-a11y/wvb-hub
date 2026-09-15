#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ONE SCHOOL, ONE MATCH: can a published gamebook PDF be trusted as a source?

    python3 scripts/gamebook_pilot.py            # Kentucky v Houston, 2026-09-13

WHAT THIS IS. A read-only feasibility pilot, approved by Cody 2026-09-14. It
follows a school's OWN link chain to one gamebook, extracts it, and produces a
REPORT. It writes nothing to data/, enters no rating, and runs on no schedule.

⚠ IT IS NOT A COLLECTOR. There is no loop, no date range, no second school.
Widening it is a separate decision.

THE TWO STAGES, AND WHY THEY MUST NOT MERGE (Codex review, 2026-09-13):

  STAGE 1 -- THE DOCUMENT MUST BE COHERENT WITH ITSELF. No other source is
  consulted. Player rows must sum to the printed team totals; hitting % must
  recompute from those summed counts; the set scores must sum to the printed
  tally. A document that fails Stage 1 is rejected WHOLE -- never partially
  used, because a PDF that cannot add up is not a source, it is a picture.

  STAGE 2 -- COMPARE, AND PREFER NEITHER. Only a Stage-1-clean document gets
  here. ⚠ AGREEMENT WITH OUR FEED IS NOT A PASS CONDITION. An earlier draft
  of this pilot required the extraction to "reconcile exactly with our
  totals" -- which is requiring agreement with a feed carrying 85 ledgered
  corrections this season. Codex caught it. A disagreement is PRESERVED with
  both claims and their provenance, changes no counted result, and may only
  become a correction through the existing two-source rule. A single PDF is
  one witness.

⚠ ROTATIONS ARE ANCHORED IN WHAT THE DOCUMENT STATES, not in a signature.
The printed starting six, the named server on every rally and the
both-direction substitutions are facts on the page. The 5-1 / OH-spacing
signature is a POPULATION statistic (82.2% over n=169 against a 21.3% null)
and says nothing about any individual match -- it is reported as
corroboration and never as a per-match pass/fail. A slot the document does
not establish renders UNKNOWN.

Python 3.9 target.
"""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

# ⚠ EVERY SCHOOL PUBLISHES DIFFERENTLY, AND THAT IS THE COVERAGE QUESTION.
# Kentucky links its gamebooks straight off the schedule page; Louisville
# hides them one level down on each SIDEARM box-score page, served from a
# CDN; Nebraska links a `/documents/<uuid>.pdf` that is not a PDF at all.
# The discovery route is per school and written down, never guessed.
SCHOOLS = {
    "kentucky": {"school": "Kentucky", "via": "schedule", "pick": "-uh.pdf",
                 "page": "https://ukathletics.com/sports/wvball/schedule/",
                 "gid": "6627186", "opponent": "Houston",
                 "date": "2026-09-13"},
    "louisville": {"school": "Louisville", "via": "boxpage", "pick": ".pdf",
                   "page": "https://gocards.com/boxscore.aspx?id=26415",
                   "gid": None, "opponent": "UNI", "date": "2026-09-13"},
    "nebraska": {"school": "Nebraska", "via": "boxpage", "pick": "documents",
                 "page": "https://huskers.com/boxscore/25159",
                 "gid": None, "opponent": "Georgia Tech",
                 "date": "2026-09-12"},
}
CFG = SCHOOLS[(sys.argv[1] if len(sys.argv) > 1 else "kentucky").lower()]
SCHOOL = CFG["school"]
SCHEDULE = CFG["page"]
WANT = {"gid": CFG["gid"], "opponent": CFG["opponent"], "date": CFG["date"]}
ARCHIVE = os.path.join(REPO, "Cody", "data", "source_archive")

# a player row's trailing 22 columns, fixed by the gamebook's own header:
#   S K E TA Pct | Ast Err TA Pct | SA SE TA Pct | 0 RE Pct | Dig BS BA BE BHE Pts
NCOLS = 22
COLS = ["S", "K", "E", "TA", "HPct", "Ast", "AErr", "ATA", "APct",
        "SA", "SE", "STA", "SPct", "RZ", "RE", "RPct",
        "Dig", "BS", "BA", "BE", "BHE", "Pts"]


def num(tok):
    """A gamebook cell. `.` means zero -- it is the document's own convention
    for 'none', not missing data."""
    if tok in (".", "", "-"):
        return 0.0
    try:
        return float(tok)
    except ValueError:
        return None


def discover(sched_html):
    """Every gamebook the SCHOOL links from its own page.

    ⚠ NEVER GUESS A URL. The filenames carry opaque hashes
    (`f3e04e3b-ma09-uh.pdf`, `20260913013345-224216.pdf`); they cannot be
    constructed and must not be.
    ⚠ AND NOT ALWAYS FROM href. Kentucky's schedule page carries them inside
    its embedded data, so an href-only scan found ZERO on a page linking
    thirteen. Scan the document wherever they sit -- still the school's own
    page, still never a constructed URL.
    """
    out = []
    for m in re.finditer(r"https?://[^\"'\s\\]+\.pdf", sched_html):
        u = m.group(0)
        if CFG["via"] == "schedule":
            # the match tag follows the opaque hash with a HYPHEN, not a
            # slash: `.../f3e04e3b-ma09-uh.pdf`.
            if re.search(r"[-/](?:ma|gm)\d+-", u):
                out.append(u)
        else:
            out.append(u)
    return sorted(set(out))


def extract(pdf_path):
    txt = subprocess.check_output(["pdftotext", "-layout", pdf_path, "-"],
                                  stderr=subprocess.DEVNULL)
    return txt.decode("utf-8", "replace")


def parse_teams(text):
    """{team: {'players': [...], 'totals': {...}}} from the box-score page."""
    # ⚠ A GAMEBOOK HOLDS SEVERAL TABLES, NOT ONE. After the full match box
    # come PER-SET boxes and two condensed layouts, each with its own `##`
    # header and a DIFFERENT column count -- so a fixed "last 22 tokens" rule
    # silently mis-parses them and the sums came out at 2-2.4x the printed
    # totals. Accept only the full-match layout, identified by its own column
    # signature, and only the FIRST such block per team.
    FULL = ("Ast", "Err", "BHE", "Dig")
    teams = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^\s*##\s+(.+?)\s{2,}", line)
        if m:
            if not all(k in line for k in FULL):
                cur = None                  # a per-set or condensed table
                continue
            name = m.group(1).strip()
            if name in teams and teams[name]["totals"] is not None:
                cur = None                  # already have this team's box
                continue
            cur = name
            # ⚠ THE HEADER REPEATS ON CONTINUATION PAGES. Assigning a fresh
            # dict here WIPED every row already collected for that team, so
            # the parser reported "no player rows" about a document holding
            # twenty-three of them. Accumulate; never reset on a re-header.
            teams.setdefault(cur, {"players": [], "totals": None})
            continue
        if cur is None:
            continue
        toks = line.split()
        if len(toks) < NCOLS + 1:
            continue
        tail = toks[-NCOLS:]
        vals = [num(t) for t in tail]
        if any(v is None for v in vals):
            continue
        head = " ".join(toks[:len(toks) - NCOLS])
        row = dict(zip(COLS, vals))
        if head.strip().lower().startswith("totals"):
            # first totals row wins: a repeat on a later page is the same
            # printed figure, not a second match
            if teams[cur]["totals"] is None:
                teams[cur]["totals"] = row
            cur = None                      # totals close the team block
        elif re.match(r"^\s*\d+\s+\S", head) and "," in head:
            # ⚠ STRIP THE SET-PARTICIPATION MARKERS. A libero's row carries
            # `L L L` between her name and her stats, so a naive read gave
            # "Tuozzo, Molly L L L" -- which then matched no server in the
            # play-by-play, and BOTH liberos fell out of the rotation as
            # "unresolved". The one position most likely to serve.
            nm = re.sub(r"^\s*\d+\s+", "", head).strip()
            nm = re.sub(r"(?:\s+(?:L|\d))+$", "", nm).strip()
            row["name"] = nm
            row["jersey"] = head.split()[0]
            teams[cur]["players"].append(row)
    return teams


# ⚠ THE FORMAT IS NOT UNIVERSAL, AND THAT IS THE COVERAGE ANSWER.
# Kentucky publishes the NCAA LiveStats GAMEBOOK: `##` team headers, 22
# columns, and a full play-by-play naming the server on every rally.
# Louisville publishes a SIDEARM BOX PDF: a different header, 17 columns, and
# NO play-by-play at all. They are both "the box score as a PDF" and only one
# of them carries the thing this pilot was chasing.
SIDEARM_COLS = ["SP", "K", "E", "TA", "PCT", "Ast", "AErr", "SA", "SE",
                "BS", "BA", "BE", "Dig", "BHE", "RE", "Pts"]


def detect_format(text):
    if re.search(r"^\s*##\s+\S", text, re.M) and "Play-by-Play" in text:
        return "livestats_gamebook"
    if re.search(r"^#\s+Player\s+SP\s", text, re.M) or \
            re.search(r"\bSP\s+K\s+E\s+TA\s+PCT\b", text):
        return "sidearm_box"
    return "unknown"


def parse_sidearm(text):
    """{team: {'players': [...], 'totals': {...}}} from a SIDEARM box PDF."""
    teams, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Z][A-Za-z&.'\- ]+?)\s*\(\d+-\d+[^)]*\)\s*$",
                     line)
        if m:
            cur = m.group(1).strip()
            teams.setdefault(cur, {"players": [], "totals": None})
            continue
        if cur is None:
            continue
        toks = line.split()
        n = len(SIDEARM_COLS)
        if len(toks) < n + 1:
            continue
        tail = toks[-n:]
        vals = [num(t) for t in tail]
        if any(v is None for v in vals):
            continue
        head = " ".join(toks[:len(toks) - n])
        row = dict(zip(SIDEARM_COLS, vals))
        if head.strip().lower().startswith("totals"):
            if teams[cur]["totals"] is None:
                teams[cur]["totals"] = row
            cur = None
        elif "," in head and not head.strip().upper().startswith("TM"):
            row["name"] = re.sub(r"^\s*\S+\s+", "", head).strip()
            row["jersey"] = head.split()[0]
            teams[cur]["players"].append(row)
    return teams


def parse_sets(text):
    """[(away_pts, home_pts)] from the SET SCORES block, with the team names."""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if "SET SCORES" in l.upper():
            rows = []
            for j in range(i, min(i + 12, len(lines))):
                # ⚠ TAKE ONLY THE LEADING RUN OF SET SCORES. The layout puts
                # the "Attack By Set" table alongside, so a greedy read
                # swallowed `.167  12-24  50%` into the set line. Stop at the
                # first token that is not a bare integer, and cap at five.
                # the name is the text BEFORE "(n)" and must not swallow the
                # neighbouring table: allow letters, spaces and the usual
                # punctuation in school names, nothing numeric
                # ⚠ SEARCH, DO NOT ANCHOR. The "Attack By Set" table shares
                # these lines and sits to the LEFT of the second team, so
                # `Kentucky (3) 25 25 25` is preceded by `.167 12-24 50%`.
                # Anchoring at the start matched Houston and missed Kentucky,
                # which read as "the block will not parse".
                m = re.search(r"([A-Za-z][A-Za-z&.'\- ]*?)\s+\((\d+)\)"
                              r"\s+(\d+(?:\s+\d+)*)", lines[j])
                if m:
                    pts = [int(x) for x in m.group(3).split()][:5]
                    rows.append((m.group(1).strip(), int(m.group(2)), pts))
            if len(rows) == 2:
                # ⚠ THE DOCUMENT SAYS HOW MANY SET COLUMNS THERE ARE: the two
                # printed sets-won figures sum to the sets played. The
                # "Attack By Set" table sits alongside on the same lines, so
                # reading "every integer" pulled its numbers in and invented a
                # fourth set in a three-set match. Truncate to what the
                # tally says, and refuse if either row is short of it.
                n = rows[0][1] + rows[1][1]
                if min(len(rows[0][2]), len(rows[1][2])) < n:
                    return []
                return [(a, b, c[:n]) for a, b, c in rows]
    return []


def parse_pbp(text):
    """Per set: the starting six, the serve order, and substitutions."""
    sets = []
    cur = None
    for line in text.splitlines():
        m = re.search(r"Play-by-Play Summary \((\w+) set\)", line, re.I)
        if m:
            cur = {"set": m.group(1), "starters": {}, "servers": [],
                   "subs": [], "libero": {}}
            sets.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^\s*([A-Z][A-Za-z&\.\' ]{1,20}):\s+(\d+\s+.+)$", line)
        if m and ";" in m.group(2):
            side = m.group(1).strip()
            names, lib = [], None
            for part in m.group(2).split(";"):
                part = part.strip().rstrip(".")
                if part.lower().startswith("libero"):
                    lib = re.sub(r"^libero\s+", "", part, flags=re.I)
                elif part:
                    names.append(part)
            cur["starters"][side] = names
            if lib:
                cur["libero"][side] = lib
            continue
        m = re.search(r"\[(\d+\s+[^\]]+)\]", line)
        if m:
            cur["servers"].append(m.group(1).strip())
        m = re.search(r"Substitution:\s+(.+?)\s+for\s+(.+?)\.", line)
        if m:
            cur["subs"].append((m.group(1).strip(), m.group(2).strip()))
    return sets


def main():
    print("GAMEBOOK PILOT -- %s, one match, READ ONLY\n" % SCHOOL)
    import verify_results_daily as V

    print("1. DISCOVERY -- from the school's own schedule page")
    st, body, _ = V._fetch(SCHEDULE)
    print("   %s  HTTP %s  %d bytes" % (SCHEDULE, st, len(body or "")))
    if st != 200 or not body:
        return 1
    books = discover(body)
    print("   %d gamebooks linked by the school" % len(books))
    url = next((u for u in books if CFG["pick"] in u), None)
    print("   selected: %s" % url)
    if not url:
        return 1

    print("\n2. RETRIEVAL -- provenance recorded, nothing guessed")
    st, raw, _ = V._fetch(url, binary=True) if "binary" in \
        V._fetch.__code__.co_varnames else (None, None, None)
    if raw is None:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent":
                                                   "wvb-hub pilot (personal)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            hdrs = dict(r.headers)
            st = r.status
    else:
        hdrs = {}
    # ⚠ A .pdf URL THAT RETURNS 200 IS NOT A PDF. Nebraska's box page links
    # `/documents/<uuid>.pdf`, which answers 200 with 558 KB of the site's
    # own HTML shell -- pdftotext chews on it and yields nothing, which
    # reads as a parse bug rather than as the school not publishing one.
    # Check the magic bytes and name it a COVERAGE GAP.
    if not raw[:5].startswith(b"%PDF"):
        print("   \u26a0 NOT A PDF -- returns %s (first bytes %r)."
              % ("HTML" if b"<" in raw[:300] else "unknown", raw[:8]))
        print("   COVERAGE GAP: this school does not publish an extractable "
              "gamebook by this route. Not a parse failure.")
        return 2
    sha = hashlib.sha256(raw).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    if not os.path.isdir(ARCHIVE):
        os.makedirs(ARCHIVE)
    dest = os.path.join(ARCHIVE, "%s_%s_%s.pdf"
                        % (SCHOOL.lower(), WANT["date"], sha[:8]))
    open(dest, "wb").write(raw)
    print("   HTTP %s  %d bytes  sha256 %s" % (st, len(raw), sha))
    print("   retrieved %s" % now)
    for k in ("Last-Modified", "ETag", "Content-Type"):
        if hdrs.get(k):
            print("   %-14s %s" % (k + ":", hdrs[k]))
    print("   archived  %s" % os.path.relpath(dest, REPO))

    text = extract(dest)
    fmt = detect_format(text)
    if fmt == "sidearm_box":
        teams = parse_sidearm(text)
        pbp = []
    else:
        teams = parse_teams(text)
        pbp = parse_pbp(text)
    sets = parse_sets(text)
    print("   format: %s" % fmt)
    print("   extracted %d lines, %d teams, %d sets, %d pbp blocks"
          % (len(text.splitlines()), len(teams), len(sets), len(pbp)))
    if fmt == "sidearm_box":
        print("   \u26a0 this format carries NO play-by-play -- no named "
              "servers, no substitutions, no rotation. The box totals are "
              "here; the thing this pilot was chasing is not.")

    print("\n3. STAGE 1 -- IS THE DOCUMENT COHERENT WITH ITSELF?")
    print("   (no other source consulted; a failure rejects it WHOLE)")
    stage1 = True
    for tm, d in teams.items():
        t = d["totals"]
        if not t or not d["players"]:
            print("   %-12s FAIL -- no totals or no player rows" % tm)
            stage1 = False
            continue
        cols = [c for c in ("K", "E", "TA", "Ast", "SA", "SE", "Dig",
                            "BS", "BA") if c in t]
        for col in cols:
            s = round(sum(p[col] for p in d["players"]), 2)
            if abs(s - t[col]) > 0.01:
                print("   %-12s FAIL %-4s players sum %.1f vs printed %.1f"
                      % (tm, col, s, t[col]))
                stage1 = False
        # the two formats name the printed percentage differently
        printed = t.get("HPct", t.get("PCT"))
        hit = (t["K"] - t["E"]) / t["TA"] if t["TA"] else None
        if hit is not None and printed is not None \
                and abs(hit - printed) > 0.0015:
            print("   %-12s FAIL hit%% recomputes %.3f vs printed %.3f"
                  % (tm, hit, t["HPct"]))
            stage1 = False
        print("   %-12s %2d players  K %.0f E %.0f TA %.0f  hit %.3f "
              "(recomputed %.3f)  sets %.0f*"
              % (tm, len(d["players"]), t["K"], t["E"], t["TA"],
                 printed if printed is not None else float("nan"),
                 hit if hit is not None else float("nan"),
                 t.get("S", 0) or 0))
    if len(sets) == 2:
        (an, aw, ascores), (hn, hw, hscores) = sets
        won_a = sum(1 for x, y in zip(ascores, hscores) if x > y)
        won_h = sum(1 for x, y in zip(ascores, hscores) if y > x)
        ok = (won_a, won_h) == (aw, hw)
        print("   set line  %s %s | %s %s  -> %d-%d, printed %d-%d  %s"
              % (an, ascores, hn, hscores, won_a, won_h, aw, hw,
                 "ok" if ok else "FAIL"))
        stage1 = stage1 and ok
    else:
        print("   set scores FAIL -- block not parsed")
        stage1 = False
    print("   STAGE 1: %s" % ("CLEAN" if stage1 else "REJECTED"))
    if not stage1:
        print("\n   Document rejected whole. No comparison is run.")
        return 1

    print("\n4. STAGE 2 -- COMPARE WITH WHAT WE HOLD, PREFER NEITHER")
    import season_counts as SC
    games = [json.loads(l) for l in open(os.path.join(
        REPO, "data", "raw", "2026", "games.jsonl"), encoding="utf-8")
        if l.strip()]
    corr = SC.corrections(2026)
    ours = None
    for g in SC.resolve(games):
        if WANT["gid"] and str(g.get("game_id")) == WANT["gid"]:
            ours = SC.apply_correction(g, corr)
    if not WANT["gid"]:
        print("   no gid pinned for this school in the pilot config -- the "
              "result comparison is skipped; Stage 1 stands on its own")
    elif not ours:
        print("   we hold no record for gid %s -- nothing to compare"
              % WANT["gid"])
    else:
        ts = ours.get("teams") or []
        wi = SC.winner_index(ours)
        print("   ours : %s def. %s %s-%s"
              % (ts[wi].get("name_short"), ts[1 - wi].get("name_short"),
                 ts[wi].get("sets_won"), ts[1 - wi].get("sets_won")))
        print("   pdf  : %s %d-%d %s"
              % (sets[1][0], sets[1][1], sets[0][1], sets[0][0]))
        agree = int(sets[1][1]) == int(ts[wi].get("sets_won") or -1) or \
            int(sets[0][1]) == int(ts[wi].get("sets_won") or -1)
        print("   result agreement: %s" % ("AGREE" if agree else
                                           "DISAGREE -- both claims preserved"))
        # per-set line
        bp = [(int(l["visit"]), int(l["home"]))
              for l in (ours.get("linescores") or [])
              if l.get("home") is not None]
        print("   our set line : %s" % bp)
        print("   pdf set line : %s" % list(zip(sets[0][2], sets[1][2])))

        # ⚠ FIELD BY FIELD, AND THE THREE STATES ARE KEPT APART: agrees /
        # disagrees / only-one-source-has-it. The third is not a defect on
        # either side and must not be reported as one.
        print("\n   field-by-field, per team:")
        # ⚠ READ playerbox.jsonl, NOT boxscores.jsonl. I compared against
        # boxscores.jsonl first and reported "our box is partial -- ten
        # fields only the PDF has". That was WRONG: boxscores.jsonl carries a
        # sparse team_stats block with no player rows, while the real per-
        # player data lives in playerbox.jsonl and is complete. The claim was
        # a fact about which file I opened, not about our data. Corrected in
        # CL-0008.
        rows = []
        for l in open(os.path.join(REPO, "data", "raw", "2026",
                                   "playerbox.jsonl"), encoding="utf-8"):
            if '"%s"' % WANT["gid"] in l:
                d = json.loads(l)
                if str(d.get("game_id")) == WANT["gid"]:
                    rows = d.get("rows") or []
        by_id = {}
        for t in ts:
            by_id[str(t.get("team_id"))] = t.get("name_short")
        agg = {}
        for r in rows:
            tm = by_id.get(str(r.get("team_id")))
            if not tm:
                continue
            a = agg.setdefault(tm, dict.fromkeys(
                ("kills", "errors", "atts", "assists", "aces", "digs",
                 "bs", "ba", "recv_atts", "recv_errors"), 0))
            for k in a:
                try:
                    a[k] += int(r.get(k) or 0)
                except (TypeError, ValueError):
                    pass
        box = {"teams": [{"name_short": k, "team_stats": v,
                          "players": [1]} for k, v in agg.items()]}
        MAP = [("kills", "K"), ("errors", "E"), ("atts", "TA"),
               ("assists", "Ast"), ("aces", "SA"), ("digs", "Dig"),
               ("bs", "BS"), ("ba", "BA"), ("recv_errors", "RE")]
        agree = differ = only_pdf = only_ours = 0
        for t in (box or {}).get("teams") or []:
            tm = t.get("name_short")
            pdft = (teams.get(tm) or {}).get("totals")
            if not pdft:
                continue
            st_ = t.get("team_stats") or {}
            bits = []
            for ours_k, pdf_k in MAP:
                ov = st_.get(ours_k)
                pv = pdft.get(pdf_k)
                if ov is None and pv is not None:
                    only_pdf += 1
                    bits.append("%s pdf=%.0f ours=-" % (pdf_k, pv))
                elif ov is not None and pv is None:
                    only_ours += 1
                elif ov is not None and pv is not None:
                    if abs(float(ov) - pv) < 0.01:
                        agree += 1
                    else:
                        differ += 1
                        bits.append("%s DISAGREE pdf=%.0f ours=%s"
                                    % (pdf_k, pv, ov))
            print("   %-10s %s" % (tm, "; ".join(bits) or "all fields agree"))
        print("   -> %d agree, %d disagree, %d only the PDF has, "
              "%d only we have" % (agree, differ, only_pdf, only_ours))
        if differ:
            print("   ⚠ a disagreement is PRESERVED, not resolved: both "
                  "claims stand, nothing is overwritten, and a correction "
                  "still needs the two-source rule.")
        print("   our player rows: %d | pdf player rows: %d"
              % (len(rows), sum(len(d["players"]) for d in teams.values())))
        # receptions are the one place the two genuinely differ; show both
        for t in (box or {}).get("teams") or []:
            tm = t["name_short"]
            pdft = (teams.get(tm) or {}).get("totals") or {}
            if "RZ" in pdft:
                print("   %-10s receptions  pdf %.0f good / %.0f err   "
                      "ours %s att / %s err"
                      % (tm, pdft["RZ"], pdft["RE"],
                         t["team_stats"].get("recv_atts"),
                         t["team_stats"].get("recv_errors")))

    print("\n5. WHAT THE DOCUMENT CARRIES THAT OUR FEED DOES NOT")
    tot_srv = sum(len(s["servers"]) for s in pbp)
    tot_sub = sum(len(s["subs"]) for s in pbp)
    print("   named servers on rallies : %d" % tot_srv)
    print("   substitutions, BOTH names: %d" % tot_sub)
    for s in pbp[:1]:
        for side, names in s["starters"].items():
            print("   set %s starters %-5s: %s"
                  % (s["set"], side, "; ".join(names)))
            if s["libero"].get(side):
                print("   %18s libero: %s" % ("", s["libero"][side]))
    for tm, d in teams.items():
        t = d["totals"]
        # ⚠ ONLY THE LIVESTATS GAMEBOOK CARRIES SERVE-RECEIVE. SIDEARM's box
        # prints reception ERRORS and nothing to divide them by, so a receive
        # percentage cannot be formed -- and inventing a denominator would be
        # exactly the synthesised value R5 forbids.
        if "RZ" in t and "RPct" in t:
            print("   %-12s serve-receive: %.0f received, %.0f errors, %.3f"
                  % (tm, t["RZ"], t["RE"], t["RPct"]))
        elif "RE" in t:
            print("   %-12s reception errors: %.0f (no receive attempts "
                  "printed -- no percentage is derivable)" % (tm, t["RE"]))
    print("   \u26a0 sideout % is printed per set in the ATTACK BY SET "
          "block (read separately; not parsed by this pilot)")

    print("\n6. ROTATION -- anchored in what the document STATES")
    if not pbp:
        print("   NONE DERIVABLE. This format prints no play-by-play, so no")
        print("   server is named and no rotation may be inferred. That is a")
        print("   fact about the document, not a gap to be filled.")
        print("\nPILOT COMPLETE (format: %s)." % fmt)
        return 0
    # ⚠ THE RALLIES OF BOTH TEAMS INTERLEAVE IN ONE COLUMN. Reading the
    # server list as "a team's serve order" without attributing each name is
    # simply wrong. Bind each server to the team whose OWN box lists her --
    # surname plus jersey, the R8 anchor -- and report only what that
    # establishes.
    roster = {}
    for tm, d in teams.items():
        for pl in d["players"]:
            roster[(pl["jersey"], pl["name"])] = tm
    for s in pbp[:1]:
        by_team = {}
        for srv in s["servers"]:
            mm = re.match(r"^(\d+)\s+(.+)$", srv)
            if not mm:
                continue
            tm = roster.get((mm.group(1), mm.group(2).strip()))
            if tm:
                by_team.setdefault(tm, []).append(srv)
        unattr = len(s["servers"]) - sum(len(v) for v in by_team.values())
        print("   set %s: %d rallies, %d attributed to a team, %d unresolved"
              % (s["set"], len(s["servers"]),
                 sum(len(v) for v in by_team.values()), unattr))
        for tm, lst in sorted(by_team.items()):
            # ⚠ CONSECUTIVE SERVES BY ONE PLAYER ARE ONE ROTATION SLOT, not
            # two. She keeps serving while her team scores, so the raw list
            # has runs. Collapsing them first is the difference between a
            # cycle and "she repeated immediately, stop" -- which is what my
            # first version reported for a setter who served an ace.
            runs = [x for i, x in enumerate(lst) if i == 0 or x != lst[i - 1]]
            order, seen = [], set()
            for x in runs:
                if x in seen:
                    break
                seen.add(x)
                order.append(x)
            print("   %-10s serve order, %d distinct before the cycle "
                  "repeats: %s"
                  % (tm, len(order),
                     " \u2192 ".join(x.split(None, 1)[1] for x in order)))
            if len(order) < 6:
                print("   %-10s ⚠ fewer than six -- the serving six is NOT "
                      "the six on court; unestablished slots stay UNKNOWN"
                      % "")
    print("   ⚠ the SERVING six is not the six on court -- a libero replaces")
    print("     a middle as she rotates back. Unestablished slots stay UNKNOWN.")

    print("\nPILOT COMPLETE. Nothing written to data/, no rating touched,")
    print("no schedule created. One document, one match, one report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
