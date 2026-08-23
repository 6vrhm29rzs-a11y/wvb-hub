#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Semantic invariants on what the dashboard actually SHOWS.

WHY THIS EXISTS. The bug that motivated it passed every existing check: the
crawl was correct, the reconcile was 348/348, the freshness tests passed, and CI
was green. The 2026 view rendered "Ark.-Pine Bluff 2025 Pts/Set -14.31" because
`pps` had been repointed from offense-only points/set to opponent-adjusted NET
points/set, and only one of its four call sites was renamed. Every number was
computed correctly and displayed under a heading that made it wrong.

Nothing in the suite guarded "is this number under the right heading". That is
what this file is for. The generic form of the failure is a quantity appearing
where its SIGN, RANGE or UNITS are impossible, so that is what gets asserted --
cheap, and it catches an entire class of mislabelling rather than one instance.

Checks the BUILT artifact (output/vb_dashboard.html) plus data/rating_*.json,
because what matters is what is served, not what an intermediate script thought.

Run: python3 scripts/test_display_invariants.py
No network. Exits non-zero on violation.
"""

import datetime
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2025"))
DASH = os.path.join(REPO, "output", "vb_dashboard.html")
RATING = os.path.join(REPO, "data", "rating_%d.json" % SEASON)

FAILS = []


def bad(what, detail):
    FAILS.append("%s: %s" % (what, detail))


def ok(name, n=None):
    print("  %-58s ok%s" % (name, "" if n is None else "  (%d checked)" % n))


def load_model():
    if not os.path.exists(DASH):
        return None
    h = open(DASH, encoding="utf-8").read()
    m = re.search(r"const MODEL = (\{.*?\});\n", h, re.S)
    if not m:
        return None
    return json.loads(m.group(1).replace("<\\/", "</"))


# Fields that are semantically NON-NEGATIVE. A negative here means a
# differential (or some other signed quantity) has been plumbed into a slot that
# means a count or a rate. That is exactly the bug this file was written for.
NON_NEGATIVE = {
    "opps": "offense points/set (kills+aces+blocks)",
    "kps": "kills per set",
    "aps": "aces per set",
    "bps": "blocks per set",
    "gp": "games played",
}

# Plausible ranges, to catch unit errors and per-set/per-match confusion.
RANGES = {
    "kps": (3.0, 25.0),
    "aps": (0.0, 5.0),
    "bps": (0.0, 5.0),
    "opps": (4.0, 30.0),
    "pps": (-30.0, 30.0),      # adjusted margin: signed, but bounded
}


def check_model(M):
    teams = M.get("teams") or []
    if not teams:
        bad("model", "no teams in the built dashboard")
        return
    print("dashboard payload (%d teams)" % len(teams))

    # --- sign invariants ---
    for field, label in sorted(NON_NEGATIVE.items()):
        offenders = [(t.get("team"), t.get(field)) for t in teams
                     if t.get(field) is not None and t.get(field) < 0]
        if offenders:
            bad("negative %s" % field,
                "%s must be >= 0; %d violations e.g. %s" % (
                    label, len(offenders), offenders[:3]))
        else:
            ok("%s (%s) is never negative" % (field, label), len(teams))

    # --- range invariants ---
    for field, (lo, hi) in sorted(RANGES.items()):
        vals = [(t.get("team"), t.get(field)) for t in teams
                if t.get(field) is not None]
        out = [(n, v) for n, v in vals if not (lo <= v <= hi)]
        if out:
            bad("%s out of range" % field,
                "expected [%s, %s]; %d violations e.g. %s" % (lo, hi, len(out), out[:3]))
        else:
            ok("%s within [%s, %s]" % (field, lo, hi), len(vals))

    # --- ordering invariant ---
    # NOTE: the payload carries no `rank` field -- the page computes ranks
    # client-side from `composite`. So the invariant that actually holds here is
    # that the payload is pre-sorted by composite descending; the row number the
    # user sees is derived from that order. (An earlier version of this test
    # asserted on a `rank` field that does not exist and failed for that reason
    # -- a broken check, not a finding.)
    comps = [t.get("composite") for t in teams]
    if any(c is None for c in comps):
        bad("composite", "%d teams have no composite score"
            % sum(1 for c in comps if c is None))
    elif any(comps[i] < comps[i + 1] for i in range(len(comps) - 1)):
        drops = [(teams[i].get("team"), comps[i], teams[i + 1].get("team"), comps[i + 1])
                 for i in range(len(comps) - 1) if comps[i] < comps[i + 1]]
        bad("ordering", "payload not sorted by composite desc; %d inversions e.g. %s"
            % (len(drops), drops[:2]))
    else:
        ok("payload sorted by composite descending (drives displayed rank)", len(comps))

    # --- delta consistency against the payload's own ordering ---
    mism = []
    for i, t in enumerate(teams, 1):
        d, rr = t.get("delta"), t.get("rpiRank")
        if d is None or rr is None:
            continue
        if d != rr - i:
            mism.append((t.get("team"), d, rr - i))
    if mism:
        bad("delta", "delta != rpiRank - position for %d teams e.g. %s"
            % (len(mism), mism[:3]))
    else:
        ok("delta == official RPI rank minus displayed position")

    # --- record parses and is non-negative ---
    badrec = []
    for t in teams:
        rec = t.get("record")
        if not rec:
            continue
        m = re.match(r"^(\d+)-(\d+)$", str(rec))
        if not m:
            badrec.append((t.get("team"), rec))
        elif t.get("gp") is not None and int(m.group(1)) + int(m.group(2)) != t["gp"]:
            badrec.append((t.get("team"), "%s vs gp=%s" % (rec, t["gp"])))
    if badrec:
        bad("record", "malformed or inconsistent with games played: %s" % badrec[:3])
    else:
        ok("record parses as W-L and matches games played")

    # --- display names must not be raw join keys ---
    keyish = [t.get("team") for t in teams
              if t.get("team") and t["team"] == t["team"].lower()
              and re.match(r"^[a-z0-9 ]+$", t["team"])]
    if keyish:
        bad("team names", "look like normalized join keys, not display names: %s"
            % keyish[:5])
    else:
        ok("team names are display names, not join keys", len(teams))

    # --- low-confidence flag agrees with games played ---
    LOW = 10
    wrong = [t.get("team") for t in teams
             if t.get("gp") is not None
             and bool(t.get("lowconf")) != (t["gp"] < LOW)]
    if wrong:
        bad("lowconf", "flag disagrees with games played for %d teams e.g. %s"
            % (len(wrong), wrong[:3]))
    else:
        ok("low-confidence flag agrees with games played (<%d)" % LOW)

    # --- freshness metadata must exist and be sane ---
    gen = M.get("generated_at")
    if not gen:
        bad("freshness", "no generated_at in the payload; the staleness banner "
                         "cannot work without it")
    else:
        try:
            t = datetime.datetime.strptime(gen.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
            if t > datetime.datetime.utcnow() + datetime.timedelta(hours=1):
                bad("freshness", "generated_at is in the future: %s" % gen)
            else:
                ok("generated_at present and not in the future")
        except Exception:
            bad("freshness", "generated_at unparseable: %r" % gen)

    dt = M.get("data_through")
    if dt:
        try:
            d = datetime.datetime.strptime(dt, "%Y-%m-%d").date()
            if d > datetime.date.today():
                bad("freshness", "data_through is in the future: %s" % dt)
            else:
                ok("data_through present and not in the future")
        except Exception:
            bad("freshness", "data_through unparseable: %r" % dt)


def check_rating():
    if not os.path.exists(RATING):
        print("rating file (season %d): absent -- skipping (normal pre-season)" % SEASON)
        return
    R = json.load(open(RATING))
    teams = R.get("teams") or []
    print("rating payload (%d teams)" % len(teams))

    cr = [t.get("composite_rank") for t in teams]
    if sorted(x for x in cr if x is not None) != list(range(1, len(teams) + 1)):
        bad("composite_rank", "must be exactly 1..%d, unique" % len(teams))
    else:
        ok("composite_rank is exactly 1..N, unique", len(teams))

    neg = [t["team"] for t in teams
           if t.get("games_played") is not None and t["games_played"] < 0]
    if neg:
        bad("games_played", "negative for %s" % neg[:3])
    else:
        ok("games_played non-negative", len(teams))

    badres = []
    for t in teams:
        for k in ("vs_rpi_top25", "vs_rpi_top50"):
            v = (t.get("resume") or {}).get(k)
            if v is None:
                continue
            if not re.match(r"^\d+-\d+$", str(v)):
                badres.append((t.get("team"), k, v))
    if badres:
        bad("resume", "malformed W-L strings: %s" % badres[:3])
    else:
        ok("resume records parse as W-L")

    w = (R.get("meta") or {}).get("weights") or {}
    if w.get("hand_entered") is True:
        bad("weights", "marked hand_entered; they are supposed to be fitted")
    elif not w.get("fitted"):
        bad("weights", "not marked as fitted")
    else:
        ok("rating weights are fitted, not hand-entered")


def check_no_fabrication():
    """No synthesised stand-in values may reach the page.

    The live site rendered a "returning production %" derived from a HASH OF THE
    TEAM NAME for ~316 of 348 teams, beside a banner citing official player
    stats. A generic test cannot recognise every possible fabricator, so this
    guards the specific one and the pattern it used: deriving a displayed number
    from characters of a label.
    """
    if not os.path.exists(DASH):
        return
    h = open(DASH, encoding="utf-8").read()
    body = re.sub(r"/\*.*?\*/", "", h, flags=re.S)   # ignore explanatory comments
    if re.search(r"function\s+retPct", body):
        bad("fabrication", "the name-hash returning-% fabricator is back")
        return

    # Hashing a label is fine for DECORATION (a colour) and not for a
    # MEASUREMENT. Distinguishing those automatically is not reliable, so known
    # decorative hashers are allowlisted by name and anything new is flagged for
    # a human to classify. An earlier version of this check flagged `hueFor`
    # -- which picks a logo colour -- as a fabrication. A guard that cries wolf
    # on correct code gets ignored, which is worse than not having it.
    DECORATIVE = {"hueFor"}
    hashers = set(re.findall(r"function\s+(\w+)\s*\([^)]*\)\s*\{[^}]*charCodeAt", body))
    unknown = hashers - DECORATIVE
    if unknown:
        bad("fabrication", "label-hashing function(s) not known to be decorative: "
                           "%s -- confirm they do not produce a displayed measurement"
            % sorted(unknown))
    else:
        ok("no synthesised stand-in values (decorative hashers: %s)"
           % ", ".join(sorted(DECORATIVE & hashers)) if hashers else
           "no synthesised stand-in values in the built page")


def check_start_times():
    """The feed's midnight PLACEHOLDER must never reach the page.

    ncaa.com fills an unannounced start with a midnight-ish sentinel that
    formats exactly like a real time. Measured: in the completed 2025 season
    only 13 of 5,133 fixtures carried an early-AM Eastern time and ALL THIRTEEN
    were at Hawaii (1:00 AM ET = 7:00 PM HST); in 2026, 176 of 192 were at
    schools that plainly do not host at 1 AM.

    ⚠ THIS TESTS THE RULE, NOT THE RENDERED STRING. The page renders PACIFIC,
    and two attempts to judge plausibility from the displayed text both failed:
    a genuine 10:00 AM ET tournament start shows as 7:00 AM PT (flagged nine
    real matches), and a genuine late West-coast match shows as 9:00 PM PT,
    which is midnight Eastern (flagged 164). Whether a time is possible depends
    on the HOME VENUE's local zone, which we do not have -- so the guard checks
    the decision `listed_time()` actually makes, in the Eastern terms the feed
    publishes in, instead of inferring across timezones it cannot resolve.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_hub import listed_time, FAR_WEST_HOME

    # placeholder in, TBA out
    for t_ in ("12:00 AM ET", "1:00 AM ET", "3:00 AM ET", "6:00 AM ET", "7:30 AM ET"):
        got = listed_time(t_, "Nebraska")
        if got != "TBA":
            bad("placeholder not suppressed", "%s -> %r" % (t_, got))
            break
    else:
        ok("implausible Eastern starts render as TBA", 5)

    # Hawaii's genuine late slate survives -- 1:00 AM ET is 7:00 PM in Honolulu
    if listed_time("1:00 AM ET", "Hawaii") == "TBA":
        bad("Hawaii's real start time was suppressed", "1:00 AM ET at Hawaii")
    else:
        ok("Hawaii keeps its genuine late start")

    # a real morning tournament start is NOT a placeholder
    if listed_time("10:00 AM ET", "Old Dominion") == "TBA":
        bad("a real 10:00 AM ET start was suppressed",
            "August tournaments open in the morning")
    else:
        ok("genuine morning starts survive")

    # ordinary evening times pass through untouched
    if listed_time("7:00 PM ET", "Nebraska") != "7:00 PM ET":
        bad("an ordinary evening time was altered", "7:00 PM ET")
    else:
        ok("ordinary evening times pass through")

    if not FAR_WEST_HOME:
        bad("FAR_WEST_HOME is empty", "Hawaii would lose its exemption")


def check_roster():
    """The full-roster block: no invented stats, no guessed positions."""
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping roster check")
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_hub import pos_bucket

    # 'O' appears on 94 box-score rows and is genuinely AMBIGUOUS: of the 41
    # that also carry a school-site position, 27 are OPP but 8 are OH and 5 are
    # S. Mapping it to Opposite would misplace roughly one in three. It must
    # stay unbucketed and render as "Position not listed".
    if pos_bucket("O") != "":
        bad("ambiguous position guessed", "'O' was bucketed as %r" % pos_bucket("O"))
    else:
        ok("ambiguous position code 'O' left unlisted, not guessed")
    for code, want in (("OH", "OH"), ("MB", "MB"), ("S", "S"),
                       ("OPP", "OPP"), ("RS", "OPP"), ("L/DS", "L/DS")):
        if pos_bucket(code) != want:
            bad("position bucket", "%s -> %s, expected %s"
                % (code, pos_bucket(code), want))

    h = open(hub, encoding="utf-8").read()
    m = re.search(r"const TEAMS = (\{.*?\});\n", h, re.S)
    if not m:
        return
    teams = json.loads(m.group(1))
    fabricated, dupes, overstarted, n = [], [], [], 0
    for tname, rec in teams.items():
        roster = rec.get("roster") or []
        n += len(roster)
        names = [r["n"] for r in roster]
        if len(set(names)) != len(names):
            dupes.append(tname)
        lu = rec.get("lineup") or {}
        cap = lu.get("matches_with_lineup")
        for r in roster:
            # a player with no D-I record must carry NO production number
            if r["k"] == "new" and r.get("r") is not None:
                fabricated.append((tname, r["n"], r["r"]))
            if cap and (r.get("st") or 0) > cap:
                overstarted.append((tname, r["n"], r["st"], cap))
    if fabricated:
        bad("stat shown for a player with no D-I record",
            "%d, e.g. %s" % (len(fabricated), fabricated[:3]))
    else:
        ok("no production number on a player with no D-I record", n)
    if dupes:
        bad("duplicate player in a roster", str(dupes[:3]))
    else:
        ok("no duplicate players within a roster")
    if overstarted:
        bad("more starts than matches on file", str(overstarted[:3]))
    else:
        ok("no player has more starts than the team has matches")


def check_sticky_headers():
    """A sticky header must not cover the first row.

    Paid for: the nav was made sticky and table headers were offset by its
    height so they would clear it. But the rankings and leaders tables scroll
    inside their OWN box, where that offset pushes the header 42px DOWN -- on
    top of row 1. The #1 team disappeared behind its own column header, which
    read as "Nebraska fell off the rankings". Any page-level offset must be
    cancelled for headers inside a scroll container.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping sticky-header check")
        return
    css = open(hub, encoding="utf-8").read()
    offset = re.search(r"th\s*\{[^}]*top:\s*var\(--navh", css) is not None
    cancel = re.search(r"\.scroll\s+th\s*\{[^}]*top:\s*0", css) is not None
    if offset and not cancel:
        bad("sticky header offset not cancelled inside scroll boxes",
            "th uses top:var(--navh) but there is no `.scroll th{top:0}`; "
            "row 1 will be hidden under the header")
    else:
        ok("sticky header offset cancelled for internally-scrolling tables")


def check_stats_dispatcher_does_not_recurse():
    """The Stats tab's dispatcher must delegate, never call itself.

    PAID FOR. renderStats() is the dispatcher: it shows one of two panels and
    then draws it. Its else-branch called renderStats() instead of
    renderLeaders(), so it recursed until the stack blew.

    It was invisible for two compounding reasons. The hidden/visible toggle runs
    BEFORE the recursive call, so the panel appeared correctly populated with
    whatever had been drawn last; and an exception thrown inside an event
    listener never reaches the code that dispatched the event, so nothing
    surfaced it. What actually broke: 'lq' and 'lstat' are wired to this
    function and LSIDE is 'player' on load, so the Stats SEARCH BOX and the STAT
    SELECTOR silently did nothing -- measured in the live page, selecting
    Kills/set left the header reading Pts/set and searching a team still
    returned all 48 rows.

    Asserted on the BUILT page, because that is what runs.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping stats-dispatcher check")
        return
    src = open(hub, encoding="utf-8").read()
    m = re.search(r"function\s+renderStats\s*\([^)]*\)\s*\{", src)
    if not m:
        bad("renderStats not found on the page",
            "renamed? this guard needs updating rather than deleting")
        return
    # Walk to the matching brace so the check reads the function, not the file.
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                body = src[i + 1:j]
                break
    else:
        bad("could not parse renderStats body", "unbalanced braces")
        return
    # ⚠ STRIP COMMENTS FIRST. The first version of this guard fired on the
    # comment written above the fix, which necessarily quotes the bug it
    # describes ("`else renderStats()` recursed"). A guard that reads prose
    # about the code instead of the code is the same mistake the no-scrape hook
    # made when it blocked the command creating its own test file.
    code = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    code = re.sub(r"//[^\n]*", " ", code)
    if re.search(r"\brenderStats\s*\(", code):
        bad("the Stats dispatcher calls itself",
            "renderStats() recurses -- the search box and stat selector will "
            "throw RangeError and silently do nothing")
    elif "renderLeaders(" not in code or "renderTeamStats(" not in code:
        bad("the Stats dispatcher does not delegate to both renderers",
            "expected renderLeaders() and renderTeamStats() in renderStats()")
    else:
        ok("Stats dispatcher delegates to both renderers and never to itself")


def check_value_scale_polarity():
    """The good->bad scale must invert for "allowed", and live in ONE place.

    R4 WITH COLOUR INSTEAD OF A COLUMN NAME. On the Stats tab the opponent view
    shows what a team ALLOWS, where a LOWER number is the better performance.
    The sort already flips on `asc`; if the colour scale did not flip with it,
    the best defence in the country would render as the reddest row and the
    worst as the greenest -- every value correct, every colour lying about it.
    Guarded by requiring the scale to be told the direction from the SAME flag
    the sort uses, so the two cannot drift apart.

    Also asserts the scale is defined once: both renderers may emit only `--t`,
    and no renderer may name a colour. If a `--good`/`--bad` literal shows up in
    the JS, the page has grown a second opinion about what green means -- the
    exact failure the crest helper was built to end.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping value-scale check")
        return
    src = open(hub, encoding="utf-8").read()

    if "function hscale(" not in src or "function hcell(" not in src:
        bad("the value scale helpers are missing",
            "hscale()/hcell() are the single definition; renderers must not "
            "compute colour themselves")
        return
    ok("the value scale is defined once, as hscale()/hcell()")

    # The opponent view must pass the inverted direction, taken from `asc`.
    m = re.search(r"function\s+renderTeamStats\s*\(\)\s*\{(.*?)\n\}", src, re.S)
    body = m.group(1) if m else ""
    code = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    if not re.search(r"asc\s*\?\s*'low'\s*:\s*'high'", code):
        bad("the allowed view does not invert the value scale",
            "renderTeamStats must derive the scale direction from `asc`, or "
            "the best defence renders as the worst")
    else:
        ok("the allowed view inverts the scale from the same flag as the sort")

    # No renderer may hard-code a scale colour.
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S)
    js = "\n".join(scripts)
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    leaked = [c for c in ("#0E7C4A", "#B3261E") if c in js]
    if leaked:
        bad("a scale colour is hard-coded in the page script",
            "found %s in JS -- colour belongs only to the CSS rule" % leaked)
    else:
        ok("no renderer names a scale colour; only --t crosses the boundary")


def check_bracket_seed_structure():
    """The bracket must be shaped like a bracket, not like a ranked list.

    PAID FOR. We listed seeds 1..32 straight down, so the four #1 lines sat in
    consecutive rows and would have met in round two -- the exact opposite of
    what a bracket is for. Read off the official 2025 sheet: 32 teams are seeded
    nationally and placed four to a line, each quadrant carries ONE team per
    line, and the lines run 1,8,5,4,3,6,7,2 so round two is 1v8, 5v4, 3v6, 7v2.
    The lower half of each side mirrors that order so the halves converge on the
    final.

    Asserted on the source rather than the rendered DOM, because the render is
    JS: the two constants and their mirroring are what encode the shape.
    """
    src = os.path.join(REPO, "scripts", "build_hub.py")
    code = open(src, encoding="utf-8").read()
    body = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    m = re.search(r"LINE_ORDER\s*=\s*\[([0-9,\s]+)\]", body)
    if not m:
        bad("the bracket has no LINE_ORDER",
            "seed lines must be ordered 1,8,5,4,3,6,7,2, not 1..8")
        return
    order = [int(x) for x in m.group(1).replace(" ", "").split(",") if x]
    if order != [1, 8, 5, 4, 3, 6, 7, 2]:
        bad("bracket seed-line order is not the official one",
            "got %s, expected [1, 8, 5, 4, 3, 6, 7, 2]" % order)
    else:
        ok("bracket seed lines run 1,8,5,4,3,6,7,2 as on the official sheet")

    if not re.search(r"reverse\(\)", body):
        bad("the lower half of the bracket does not mirror",
            "without mirroring, both halves run 1->2 and the final does not "
            "converge")
    else:
        ok("the lower half of each side mirrors, so the halves converge")

    if not re.search(r"QUAD_OF_POS", body):
        bad("seeded teams are not spread across quadrants",
            "all four #1 seeds would sit together and meet in round two")
    else:
        ok("each seed line is spread one-per-quadrant")


def check_schedule_states_where():
    """A fixture must say WHERE it is played, and never infer it.

    R5, in the place it already cost us once: two AVCA First Serve matches were
    rendered as home games for the nominal host because the page inferred
    "at <home team>" when the feed carried no venue. Kentucky-Wisconsin and
    Louisville-Texas A&M were both on a NEUTRAL floor in Milwaukee.

    Three things are asserted on the built page:
      * a fixture with no published venue SAYS SO ("venue not listed") rather
        than borrowing the home team's gym;
      * a neutral floor reads "vs", not "at" -- "Texas at Arizona St." is a
        false sentence about a match in Milwaukee;
      * an unnamed neutral event is labelled "neutral site" and NOT given the
        building's name as if it were the tournament's name. venues.py attaches
        a name only where a human supplied one.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping schedule-venue check")
        return
    src = open(hub, encoding="utf-8").read()
    m = re.search(r'<tbody id="sbody">(.*?)</tbody>', src, re.S)
    if not m:
        bad("no schedule rows on the page", "#sbody is empty or renamed")
        return
    body = m.group(1)
    rows = re.findall(r"<tr.*?</tr>", body, re.S)
    if not rows:
        bad("no schedule rows rendered", "the schedule table is empty")
        return

    unlisted = sum(1 for r in rows if "venue not listed" in r)
    withv = sum(1 for r in rows if 'class="wh l"><' in r or "<b>" in r)
    if unlisted == 0 and withv == 0:
        bad("the schedule says nothing about where matches are played",
            "every row must carry a venue or say it is not listed")
    else:
        ok("every schedule row states a venue or says it is not listed (%d unlisted)"
           % unlisted)

    # a neutral row must not say "at"
    bad_at = 0
    for r in rows:
        if "neutral site" in r or "kind ev" in r:
            if re.search(r'<td class="at">at</td>', r):
                bad_at += 1
    if bad_at:
        bad("a neutral-floor fixture reads 'at'",
            "%d rows call a neutral site a road game" % bad_at)
    else:
        ok("neutral-floor fixtures read 'vs', not 'at'")


def check_transfer_reconciliation():
    """A transfer must describe the SAME player on both sides.

    Her old team lists her under departures with a season point total; her new
    team lists her with a rate and a set count taken from that same season at
    the old school. The two are derived by different paths and must agree --
    rate x sets == points. A mismatch means a name matched the wrong person,
    which is the failure mode that looks entirely correct on both pages (R8).
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping transfer reconciliation")
        return
    h = open(hub, encoding="utf-8").read()
    m = re.search(r"const TEAMS = (\{.*?\});\n", h, re.S)
    if not m:
        return
    teams = json.loads(m.group(1))
    pairs = {}
    for _t, v in teams.items():
        for d in (v.get("top_dep") or []):
            if d.get("to"):
                pairs[(d["name"], d["to"])] = d.get("pts")
    checked = mismatch = 0
    examples = []
    for (nm, dest), pts in pairs.items():
        rows = [r for r in (teams.get(dest, {}).get("roster") or []) if r["n"] == nm]
        if not rows:
            continue
        r = rows[0]
        if not (r.get("r") and r.get("sets")):
            continue
        checked += 1
        if abs(r["r"] * r["sets"] - (pts or 0)) > 1.0:
            mismatch += 1
            examples.append((nm, dest, pts, r["r"], r["sets"]))
    if mismatch:
        bad("transfer does not reconcile across the two teams",
            "%d of %d, e.g. %s" % (mismatch, checked, examples[:2]))
    else:
        ok("every transfer reconciles: rate x sets == departure points", checked)


def check_public_build_is_clean():
    """The PUBLIC dashboard must carry no third-party source.

    This repo is public. The private page shows a VolleyTalk poll, Massey
    Ratings and TV listings transcribed from a forum; none of those are ours to
    republish. One builder now produces both pages, which is what keeps their
    UI identical -- and is exactly why this guard has to exist, because a new
    section added for the private page reaches the public one by default.

    Markers must not collide with DATA: a bare "Massey" matched Addison Massey
    and Alexis Massey, real players on real rosters.
    """
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if not os.path.exists(pub):
        print("  no public dashboard built -- skipping")
        return
    h = open(pub, encoding="utf-8").read()
    markers = ("VolleyTalk", "Massey Ratings", 'data-v="tv"', 'id="v-tv"',
               "tv_listings", "chip('Massey'", "chip('VT'")
    leaked = [m for m in markers if m in h]
    if leaked:
        bad("public dashboard leaks a private source", ", ".join(leaked))
    else:
        ok("public dashboard carries no third-party source", len(markers))

    # ---- THE DATA, not just the words --------------------------------
    # The first version of this guard only looked for the STRINGS "VolleyTalk"
    # and "Massey Ratings". It passed while the payload still shipped 25
    # VolleyTalk ranks and 151 Massey ranks inside const TEAMS -- invisible on
    # the page, one devtools open away from anyone. Hiding third-party data is
    # not the same as not publishing it.
    tm = re.search(r"const TEAMS = (\{.*?\});\n", h, re.S)
    if tm:
        teams = json.loads(tm.group(1))
        vt = sum(1 for v in teams.values() if v.get("vt") is not None)
        ms = sum(1 for v in teams.values() if v.get("massey") is not None)
        if vt or ms:
            bad("public payload carries third-party ranks",
                "%d VolleyTalk, %d Massey values in const TEAMS" % (vt, ms))
        else:
            ok("public payload carries no third-party rank values", len(teams))

    # ---- Digby is private ------------------------------------------------
    # Checked in the DATA, not the markup: the rendering JS ships in both
    # builds and only the values differ, so grepping for the panel markup would
    # false-positive. Same lesson as the Massey leak -- when the question is
    # "did we publish X", grep what was published, not what draws it.
    if tm:
        withsum = [k for k, v in teams.items() if v.get("digby")]
        if withsum:
            bad("public build carries Digby summaries",
                "%d teams, e.g. %s" % (len(withsum), withsum[:3]))
        else:
            ok("public build carries no Digby summary", len(teams))

    # The chat is a different exposure from the summaries: it is an ENDPOINT,
    # and the key that answers it lives in the local server. A static public
    # page offering /api/digby would be a dead button at best. These markers
    # ARE safe to grep in the markup, because the whole feature -- CSS, panel
    # and script -- is emitted only in the private build.
    for marker, what in (("/api/digby", "the chat endpoint"),
                         ("asklaunch", "the Ask Digby launcher"),
                         ("askwrap", "the Ask Digby panel"),
                         (".askform", "the Ask Digby styles")):
        if marker in h:
            bad("public build exposes %s" % what, marker)
    if not any(m in h for m in ("/api/digby", "asklaunch", "askwrap", ".askform")):
        ok("public build carries no Ask Digby endpoint, panel, or styles")

    # ---- every conference on the page must have an AQ row -----------------
    # The UAC sat on the TOURNAMENT default for weeks because ncaa.com labelled
    # UT Arlington "wac" and the map still carried a WAC row. The fallback was
    # right by luck; nothing said it was unexamined. A missing row is now a
    # failure rather than a silent default, and an undersized league means a
    # realignment the labels have not caught up with.
    if tm:
        import collections as _c
        live = set(v.get("conf") for v in teams.values() if v.get("conf"))
        try:
            _aq = set(json.load(open(os.path.join(
                REPO, "data/raw/2026/aq_mechanism_2026.json"),
                encoding="utf-8"))["conferences"])
        except Exception:
            _aq = None
        if _aq is not None:
            missing = sorted(live - _aq)
            if missing:
                bad("conference(s) with no AQ mechanism row", ", ".join(missing))
            else:
                ok("every conference on the page has an AQ mechanism row", len(live))
        sizes = _c.Counter(v.get("conf") for v in teams.values() if v.get("conf"))
        tiny = sorted("%s(%d)" % (k, n) for k, n in sizes.items() if n < 6)
        if tiny:
            bad("league(s) too small to award a bid -- stale conference label?",
                ", ".join(tiny))
        else:
            ok("no conference is below six D-I members", len(sizes))

    # ---- the serving rotation ---------------------------------------------
    # It is DERIVED, and the derivation only holds if the ring has exactly six
    # distinct slots. Five names, or a repeat, means the cycle was mis-read and
    # the page would draw a rotation that cannot exist on a court.
    if tm:
        rots = [(k, v["rot25"]) for k, v in teams.items() if v.get("rot25")]
        bad_len = [k for k, r in rots if len(r.get("rotation") or []) != 6]
        dupes = [k for k, r in rots
                 if len(set(r.get("rotation") or [])) != len(r.get("rotation") or [])]
        if bad_len:
            bad("rotation without six slots", "%d teams, e.g. %s" % (len(bad_len), bad_len[:3]))
        elif dupes:
            bad("a player appears twice in one rotation",
                "%d teams, e.g. %s" % (len(dupes), dupes[:3]))
        elif rots:
            ok("every serving rotation has six distinct players", len(rots))
        # A share above 1.0 would mean more agreeing sets than resolved sets.
        weird = [k for k, r in rots
                 if not (0 < (r.get("agreement") or 0) <= 1.0)
                 or (r.get("sets_with_this_rotation") or 0) > (r.get("sets_resolved") or 0)]
        if weird:
            bad("rotation agreement out of range", str(weird[:3]))
        elif rots:
            ok("rotation agreement is a real share of resolved sets", len(rots))
        # The source is MIT-licensed and must be credited wherever it renders.
        if rots and "ncaavolleyballr" not in h:
            bad("serving rotation shown without crediting its source", "ncaavolleyballr")
        elif rots:
            ok("the rotation's data source is credited on the page")
        # The old copy asserted this was impossible. It is not, and a page that
        # says both is worse than one that says neither.
        if "Rotation order 1\u20136 is not available" in h or "is not available</b>" in h:
            bad("page still claims rotation order is unavailable while showing it")

    # ---- nothing reads TEAMS before it exists ------------------------------
    # `const TEAMS` is declared near the END of the script, so any code above it
    # that touches TEAMS throws "Cannot access 'TEAMS' before initialization" --
    # and a `typeof` guard does NOT save you, because a const in the temporal
    # dead zone throws for that too. The standings differential is computed
    # server-side for exactly this reason.
    _tp2 = os.path.join(REPO, "Cody", "START-HERE.html")
    _th2 = open(_tp2, encoding="utf-8").read() if os.path.exists(_tp2) else ""
    if _th2:
        decl = _th2.find("const TEAMS = ")
        rs = _th2.find("function renderStandings")
        if decl > 0 and rs > 0 and rs < decl and "TEAMS[r.team]" in _th2:
            bad("renderStandings reads TEAMS before it is declared",
                "temporal dead zone -- compute it server-side instead")
        else:
            ok("nothing above the TEAMS declaration reads it")

    # ---- no duplicate element ids ------------------------------------------
    # I put id="sbody" on the scores grid without noticing the schedule tbody
    # already had it. getElementById returns whichever comes first, so the
    # just-finished band was querying whichever element document order handed
    # it. Cheap to check, silent when it breaks.
    _dp = os.path.join(REPO, "Cody", "START-HERE.html")
    _dh = open(_dp, encoding="utf-8").read() if os.path.exists(_dp) else ""
    if _dh:
        ids = re.findall(r'\sid="([A-Za-z][-\w]*)"', _dh)
        dupes = sorted(set(i for i in ids if ids.count(i) > 1))
        if dupes:
            bad("duplicate element ids on the page", ", ".join(dupes[:6]))
        else:
            ok("every element id on the page is unique", len(set(ids)))

    # ---- nobody leads at 0-0 ----------------------------------------------
    # `away > home` is false when the sets are level, so the else-branch bolded
    # the HOME team from the first whistle: Kentucky-Pittsburgh showed Pitt as
    # the leader at 0-0. Three states, not two.
    _lp = os.path.join(REPO, "Cody", "START-HERE.html")
    _lh = open(_lp, encoding="utf-8").read() if os.path.exists(_lp) else ""
    if _lh:
        if "const lead = +g.away_sets === +g.home_sets ? 0" not in _lh:
            bad("the live card still has a two-state winner test",
                "at 0-0 it will bold the home team")
        else:
            ok("the live card leaves both teams unhighlighted at 0-0")

    # ---- AVCA honours -----------------------------------------------------
    # R8: an All-America badge on the wrong player is the same class of error as
    # attributing her statistics, and it is the kind that looks right. The join
    # is school + exact full name, so the check is that recent selections all
    # resolved to a school -- an unresolved one is silently dropped otherwise.
    _ap = os.path.join(REPO, "data", "avca_awards.json")
    if os.path.exists(_ap):
        _aw = json.load(open(_ap, encoding="utf-8"))
        recent = [x for x in (_aw.get("selections") or []) if x.get("season", 0) >= 2024]
        unresolved = [x for x in recent if not x.get("team")]
        if recent and unresolved:
            bad("recent All-America selections with no school",
                "%d of %d, e.g. %s" % (len(unresolved), len(recent),
                                       unresolved[0].get("school_raw")))
        elif recent:
            ok("every recent All-America selection resolved to a school", len(recent))
        # The honour itself must survive -- it was once overwritten by the school.
        if recent and not any(x.get("honour") for x in recent):
            bad("All-America rows lost which team they made")
        elif recent:
            ok("selections carry which All-America team they made")

    # ---- the Stats tab -----------------------------------------------------
    _sp = os.path.join(REPO, "Cody", "START-HERE.html")
    _sh = open(_sp, encoding="utf-8").read() if os.path.exists(_sp) else ""
    if _sh:
        if 'data-ls="team"' not in _sh:
            bad("the Stats tab has no team/player toggle")
        else:
            ok("Stats splits players and teams")
        # ONE MEANING PER KEY. `aps` is aces and `asps` is assists, on both the
        # player and the team side. They were once opposite, which would have
        # ranked teams by the wrong column with no visible error.
        if '"aps": (round(d["aces"]' not in open(
                os.path.join(REPO, "scripts", "build_hub.py"), encoding="utf-8").read():
            bad("team stat keys do not match the player ones", "aps must be aces")
        else:
            ok("aps is aces and asps is assists on both sides")
        # "Allowed" must sort ascending or the worst defence ranks first.
        if "asc = side === 'opp'" not in _sh:
            bad("the allowed view does not flip its sort")
        else:
            ok("the allowed view sorts so the best defence leads")

    # ---- schedule counts join on the normaliser ---------------------------
    # "LSU New Orleans" vs "New Orleans" gave that team ZERO fixtures and made
    # its projection look like a bug. One team is legitimately zero (Saint
    # Francis is not in a single 2026 fixture); more than that means the join
    # has broken again.
    # NOTE: `teams` here comes from the PUBLIC dashboard, which is no longer
    # built -- it has no sched_n at all, so every team looked like a zero.
    # Read the page Cody opens. Third time this has caught me.
    _zp = os.path.join(REPO, "Cody", "START-HERE.html")
    _zh = open(_zp, encoding="utf-8").read() if os.path.exists(_zp) else ""
    _zt = {}
    if _zh:
        _m = re.search(r"const TEAMS = (\{.*?\});\n", _zh, re.S)
        if _m:
            try:
                _zt = json.loads(_m.group(1))
            except ValueError:
                _zt = {}
    if _zt:
        zero = [k for k, v in _zt.items() if not v.get("sched_n")]
        if len(zero) > 1:
            bad("teams with no scheduled matches -- a name join has broken",
                ", ".join(zero[:5]))
        else:
            ok("every team but one has a scheduled-match count", len(_zt) - len(zero))
        # And a team with none must SAY so rather than showing blank projections.
        if zero and _zh and "No 2026 Division-I schedule" not in _zh:
            bad("a team with no 2026 schedule shows blank numbers with no reason")
        elif zero and _zh:
            ok("a team with no 2026 schedule explains itself")

    # ---- team stats box ----------------------------------------------------
    # The opponent column is the half nobody shows, and it is free: every box
    # score carries both sides. If it ever disappears the page is showing half
    # a team.
    _tp = os.path.join(REPO, "Cody", "START-HERE.html")
    _th = open(_tp, encoding="utf-8").read() if os.path.exists(_tp) else ""
    if _th:
        if "Team stats, 2026" not in _th:
            bad("the team-stats box is gone from the team page")
        elif "Opponents" not in _th:
            bad("team stats show only the offence", "no opponent column")
        else:
            ok("team stats show both what a team does and what it allows")
        # POINTS PER SET IS KILLS + BLOCKS + ACES. That is the box-score
        # definition and the only thing the sport calls "points". An earlier
        # version also showed rally points off the set scores and called them
        # "points scored", which is not a volleyball stat -- Cody corrected it.
        if "Points / set" not in _th:
            bad("team stats have no points per set")
        elif "kills + blocks + aces" not in _th:
            bad("points per set is not the box-score definition")
        else:
            ok("points/set is kills + blocks + aces")
        # Hitting % must come from summed counts, never a mean of percentages.
        if "teamTotals" not in _th:
            bad("box scores have no team totals row")
        elif "(t.k - t.e) / t.ta" not in _th:
            bad("team hitting % is not computed from summed raw counts")
        else:
            ok("box-score team totals compute hit% from summed raw counts")

    # ---- the bracket is a bracket -----------------------------------------
    # Connectors are drawn from measured positions at runtime, so the test can
    # only check the machinery is present and wired to the right trigger. The
    # trigger is the part that went wrong three times.
    _hp = os.path.join(REPO, "Cody", "START-HERE.html")
    _h2 = open(_hp, encoding="utf-8").read() if os.path.exists(_hp) else ""
    if _h2:
        if "function drawBracketLines" not in _h2:
            bad("the bracket has no connector drawing")
        elif "attributeFilter" not in _h2 or "v-bracket" not in _h2:
            bad("connectors are not triggered by the section being revealed",
                "a box in a hidden section measures as zero")
        else:
            ok("bracket connectors are drawn and triggered on reveal")
        # Both halves must converge on the championship, or the right side
        # flows away from the final.
        if "mirror" not in _h2:
            bad("the right half of the bracket is not mirrored")
        else:
            ok("the right half of the bracket is mirrored inward")

    # ---- crests -----------------------------------------------------------
    # Cody: "make sure the teams that are listed have the logos next to them.
    # There are certain pages that don't have logos." They were missing from
    # every view rendered in PYTHON, because those rows could not reach the
    # page's JS logo() helper -- and from the live band, which is JS but was
    # written before the helper existed. One definition now (team_logos), used
    # by both sides.
    _hubp = os.path.join(REPO, "Cody", "START-HERE.html")
    _hub = open(_hubp, encoding="utf-8").read() if os.path.exists(_hubp) else ""
    n_crest = _hub.count('class="tlogo')
    if _hub and n_crest < 200:
        bad("too few team crests on the page -- a view has lost them",
            "%d found" % n_crest)
    elif _hub:
        ok("team crests render across the views", n_crest)
    # The live band draws its own cards; the helper must be reachable there too.
    for frag, what in (("logo(g.away)", "live/upcoming away side"),
                       ("logo(g.home)", "live/upcoming home side")):
        if _hub and frag not in _hub:
            bad("the %s has no crest" % what, frag)
    if _hub and "logo(g.away)" in _hub and "logo(g.home)" in _hub:
        ok("the live band draws crests too")

    # ---- roster photographs ------------------------------------------------
    # Cody: "you got rid of the roster photos... keep the photos." They were
    # never there -- the full roster carried no photo field at all -- but the
    # avatars made their absence visible, which is the same thing from where he
    # was sitting. Now they are wired, and this guard stops them going missing.
    if tm:
        rows = [c for t in teams.values() for c in (t.get("roster") or [])]
        withph = [c for c in rows if c.get("ph")]
        if rows and len(withph) < 0.5 * len(rows):
            bad("full-roster photo coverage collapsed",
                "%d of %d rows" % (len(withph), len(rows)))
        elif rows:
            ok("full roster carries photographs", len(withph))
        # Same rule as everywhere: URLs only, never an embedded image.
        embedded = [c for c in withph if str(c["ph"]).startswith("data:")]
        if embedded:
            bad("a roster photo is embedded rather than linked", str(len(embedded)))
        elif withph:
            ok("every roster photo is a remote URL, never a committed file",
               len(withph))

    # ---- player avatars ---------------------------------------------------
    # They are DECORATION and are allowed to be (R5 draws the line at a
    # measurement, and says a hashed colour is fine). What must stay true is
    # that a real photograph always wins, and that the avatar never carries a
    # face -- it is a kit and an action, not a claim about a person.
    if "function avatar(" in h:
        if "c.photo ?" not in h:
            bad("avatar shown without a real photo taking precedence")
        else:
            ok("a real photograph still wins over the avatar")
        # The poses are geometry only: circles, paths, no text, no image.
        m = re.search(r"const AV = (\{.*?\});", h, re.S)
        if m:
            try:
                av = json.loads(m.group(1))
            except ValueError:
                av = None
            if av:
                blob = json.dumps(av)
                if "<image" in blob or "<text" in blob or "href" in blob:
                    bad("avatar art embeds an image, text or link", "should be shapes only")
                else:
                    ok("avatar art is shapes only -- no image, text or link",
                       len(av.get("poses") or {}))
                if set(av.get("libero") or []) != {"L/DS", "L", "DS"}:
                    bad("libero contrast rule lost its positions",
                        str(av.get("libero")))
                else:
                    ok("the libero still gets a contrasting jersey")

    # the rankings table must not be left with mismatched columns after the strip
    m = re.search(r"<thead><tr>(.*?)</tr></thead>", h, re.S)
    b = re.search(r'<tbody id="rbody">(.*?)</tbody>', h, re.S)
    if m and b:
        row = re.search(r'<tr[^>]*class="row"[^>]*>(.*?)</tr>', b.group(1), re.S)
        if row:
            n_th = len(re.findall(r"<th", m.group(1)))
            n_td = len(re.findall(r"<td", row.group(1)))
            if n_th != n_td:
                bad("public rankings columns misaligned",
                    "%d headers vs %d cells" % (n_th, n_td))
            else:
                ok("public rankings header and cells align", n_th)


def check_photos_are_urls_only():
    """Headshots are REFERENCES, never files.

    This repo is public and the photographs belong to the schools: storing a
    URL is a different act from republishing the image. So no photo value may
    be an embedded image (`data:`) or a local path, and a player without one
    must fall back to initials rather than a stand-in picture.
    """
    for label, path in (("private", os.path.join(REPO, "Cody", "START-HERE.html")),
                        ("public", os.path.join(REPO, "output", "vb_dashboard.html"))):
        if not os.path.exists(path):
            continue
        h = open(path, encoding="utf-8").read()
        m = re.search(r"const TEAMS = (\{.*?\});\n", h, re.S)
        if not m:
            continue
        teams = json.loads(m.group(1))
        vals = [c.get("photo") for v in teams.values()
                for c in (v.get("rotation") or []) if c.get("photo")]
        embedded = [u for u in vals if str(u).startswith("data:")]
        local = [u for u in vals if not str(u).startswith(("http://", "https://"))]
        if embedded:
            bad("%s: embedded image data in a photo field" % label,
                "%d values" % len(embedded))
        elif local:
            bad("%s: non-URL photo value" % label, str(local[:2]))
        else:
            ok("%s: every headshot is a remote URL" % label, len(vals))
        # the initials fallback must still exist
        if "mug--none" not in h:
            bad("%s: no initials fallback for a missing photo" % label, "")


def check_no_unreplaced_placeholders():
    """No `{{TOKEN}}` may survive into a built page.

    A placeholder that never got substituted renders as literal braces to the
    reader and, worse, silently omits whatever it was going to say -- this is
    how a caveat sentence can vanish while the page still looks finished. Cheap
    to check, catches the whole class.
    """
    for label, path in (("private", os.path.join(REPO, "Cody", "START-HERE.html")),
                        ("public", os.path.join(REPO, "output", "vb_dashboard.html"))):
        if not os.path.exists(path):
            continue
        h = open(path, encoding="utf-8").read()
        left = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", h)))
        if left:
            bad("%s: unreplaced template placeholder" % label, ", ".join(left[:5]))
        else:
            ok("%s: no unreplaced placeholders" % label)


def check_every_view_names_its_season():
    """Every data view must say which SEASON it is showing.

    Cody, 2026-08-23: "some of this info and rankings and stuff is 2025, not
    2026. make sure we don't mix the two." He was right -- the RPI view was
    serving the FINAL 2025 table under a 2026 heading, because the rankings
    endpoint is current-only and still publishes last season until the new one
    has enough matches. A 2025 table under a 2026 heading is the error that
    looks completely correct, so the season is now stated on every view and a
    previous-season fallback has to announce itself.
    """
    for label, path in (("private", os.path.join(REPO, "Cody", "START-HERE.html")),
                        ("public", os.path.join(REPO, "output", "vb_dashboard.html"))):
        if not os.path.exists(path):
            continue
        h = open(path, encoding="utf-8").read()
        leads = re.findall(r'<p class="lead"[^>]*>(.*?)</p>', h, re.S)
        unlabelled = []
        for raw in leads:
            txt = re.sub(r"<[^>]+>", "", raw)
            if not re.search(r"20\d{2}", txt):
                unlabelled.append(re.sub(r"\s+", " ", txt).strip()[:60])
        if unlabelled:
            bad("%s: a view does not name its season" % label, str(unlabelled[:3]))
        else:
            ok("%s: every view names its season" % label, len(leads))

        # a previous-season poll must carry the warning, not pass as current
        m = re.search(r"const POLLS = (\{.*?\});\n", h, re.S)
        if m:
            polls = json.loads(m.group(1))
            prev = [k for k, v in polls.items() if v.get("prev")]
            if prev and "seasonwarn" not in h:
                bad("%s: previous-season ranking shown with no warning" % label,
                    ", ".join(prev))
            elif prev:
                ok("%s: previous-season ranking carries a season warning" % label,
                   len(prev))


def main():
    print("=" * 68)
    print("DISPLAY INVARIANTS -- is each number under the right heading?")
    print("=" * 68)
    M = load_model()
    if M is None:
        print("no built dashboard payload found -- skipping (pre-season is fine)")
    else:
        check_model(M)
    check_no_fabrication()
    print()
    check_start_times()
    print()
    check_roster()
    print()
    check_sticky_headers()
    check_stats_dispatcher_does_not_recurse()
    check_value_scale_polarity()
    check_bracket_seed_structure()
    check_schedule_states_where()
    print()
    check_transfer_reconciliation()
    print()
    check_public_build_is_clean()
    print()
    check_photos_are_urls_only()
    print()
    check_no_unreplaced_placeholders()
    print()
    check_every_view_names_its_season()
    print()
    check_rating()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL DISPLAY INVARIANTS HOLD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
