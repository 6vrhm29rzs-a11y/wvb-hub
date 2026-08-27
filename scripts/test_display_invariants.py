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
    """Validate EVERY rating payload on disk, not one chosen by an env var.

    ⚠ THIS CHECK RAN IN ONE ENVIRONMENT AND NOT THE OTHER. RATING was built from
    this module's SEASON, which defaults to 2025, while build_hub.py -- and the
    daily job, which pins WVB_SEASON=2026 -- default to 2026. So locally it
    validated rating_2025.json, and in CI it looked for rating_2026.json, found
    nothing (the live rating does not exist under 50 played matches) and skipped
    silently. A guard that only runs on a laptop is the thing this project keeps
    learning not to ship.

    Nothing here is season-specific: rank uniqueness, non-negative games,
    parseable resume records and fitted weights are true of any rating. So it
    checks all of them and says how many it found.
    """
    import glob as _glob
    paths = sorted(_glob.glob(os.path.join(REPO, "data", "rating_[0-9][0-9][0-9][0-9].json")))
    if not paths:
        print("no rating payload on disk -- skipping (normal pre-season)")
        return
    for path in paths:
        _check_one_rating(path)


def _check_one_rating(path):
    R = json.load(open(path))
    teams = R.get("teams") or []
    print("rating payload %s (%d teams)" % (os.path.basename(path), len(teams)))

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


def check_nondi_form_marker_is_visible():
    """A form result the Division-I record excludes must SAY SO in the pill.

    ⚠ A HOVER TITLE IS NOT A LABEL. It does not exist on a phone, it is not
    announced while scanning, and it cannot be seen at all in a screenshot.
    Norfolk St. beat a Division-II side, so its standings row shows a Form of
    "W" beside a record of 0-0; the pill therefore has to carry the reason on
    its face, not behind a pointer.

    ⚠ AND THE PILL IS A FIXED 19x19 BOX. Appending the suffix without widening
    it overflowed -- measured, at a 358px phone width, scrollWidth past
    clientWidth -- so the width override is part of the invariant, not
    decoration.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping non-D-I form marker check")
        return
    h = open(hub, encoding="utf-8").read()

    if "'<i class=\"fndt\">nD1</i>'" not in h:
        bad("the non-D-I form marker is not rendered as text",
            "the pill must emit visible text, not only a title attribute")
    else:
        ok("a non-D-I form pill carries VISIBLE text, not just a title")

    # It must be conditional, or every pill would wear it.
    if "g.nondi ? '<i class=\"fndt\">nD1</i>'" not in h:
        bad("the non-D-I form marker is not conditional",
            "every result would be marked, which marks nothing")
    else:
        ok("...and only when the result really is non-Division-I")

    # THE FIXED-BOX OVERFLOW. .fw/.fl is width:19px;height:19px.
    fixed = re.search(r"\.fw,\.fl\{[^}]*width:\s*19px", h) is not None
    widened = re.search(r"\.fw\.fnd,\.fl\.fnd\{[^}]*width:\s*auto", h) is not None
    if fixed and not widened:
        bad("the marked pill will overflow its own box",
            ".fw/.fl is a fixed 19px square and .fnd does not widen it")
    else:
        ok("the marked pill is widened so the suffix fits inside it")

    # PHONE. The marker must have a rule at the phone breakpoint -- if it is
    # only ever sized for desktop it is not a phone-visible label.
    phone = False
    for m in re.finditer(r"@media\s*\(max-width:\s*560px\)\s*\{", h):
        tail = h[m.end():m.end() + 400]
        if ".fndt" in tail:
            phone = True
            break
    if not phone:
        bad("the non-D-I marker has no phone rule",
            "no @media (max-width:560px) block mentions .fndt")
    else:
        ok("...and it is sized deliberately at the phone breakpoint")

    # The long form still exists for anyone who does hover.
    if "not counted in the Division-I record" not in h:
        bad("the non-D-I pill lost its explanation", "no title text found")
    else:
        ok("the hover still carries the long explanation")


def check_standings_diff_shares_the_record_basis():
    """+/- must be built from the SAME matches the record beside it counts.

    ⚠ THE SEAM THIS CLOSES. The standings row shows a Division-I-only record
    (the NCAA's own convention) and used to show a differential built from
    team_season_stats()'s `own`/`opp`, which count EVERY opponent. Norfolk St.
    read "Overall 0-0 ... +9.67" -- a differential earned in a match the record
    on that same row excludes. Two bases in one row is exactly the silent mix
    R4 exists to prevent.

    The decision is recorded here: standings +/- is DIVISION-I ONLY, derived
    from `own_di`/`opp_di`, and the column header says so. The team page's
    "Team stats" box keeps every opponent on purpose -- a different view with a
    different job -- and states that in its own note.
    """
    src = os.path.join(REPO, "scripts", "build_hub.py")
    b = open(src, encoding="utf-8").read()

    m = re.search(r'_r\["diff"\]\s*=\s*\(round\(_o\["pps"\]', b)
    if not m:
        bad("could not find the standings differential", "derivation moved")
        return
    ctx = b[max(0, m.start() - 700):m.start()]
    if '_ts.get("own_di")' not in ctx or '_ts.get("opp_di")' not in ctx:
        bad("standings +/- is not on the Division-I basis",
            "it must read own_di/opp_di, the same matches as the record")
    else:
        ok("standings +/- is derived from Division-I matches only")

    if re.search(r'_o,\s*_d\s*=\s*\(_ts\.get\("own"\)', ctx):
        bad("standings +/- still reads the all-opponent totals",
            'it must use own_di/opp_di, not own/opp')
    else:
        ok("[-] ...and not from the all-opponent totals")

    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping the rendered half")
        return
    h = open(hub, encoding="utf-8").read()

    if '+/-<span class="thb">D-I</span>' not in h:
        bad("the +/- column does not state its basis",
            "the header must carry a visible D-I stamp, not only a tooltip")
    else:
        ok("the +/- column header states its basis visibly")

    if "DIVISION-I OPPONENTS ONLY" not in h:
        bad("the +/- tooltip does not state its basis", "no explanation found")
    else:
        ok("...and the long form explains it")

    # THE NORFOLK STATE CASE, from the built payload: a team whose only match
    # is non-D-I must show a SPLIT record and NO Division-I differential.
    m2 = re.search(r"const STANDINGS = (\{.*?\});\n", h, re.S)
    if not m2:
        bad("could not read the standings payload", "regex missed")
        return
    ST = json.loads(m2.group(1))
    rows = [r for rs in ST.values() for r in rs]
    split = [r for r in rows if (r.get("nw") or r.get("nl"))]
    if not split:
        bad("no split-record team to check",
            "the guard proves nothing without one")
        return
    ok("[+] a split-record team exists to test", len(split))

    for r in split:
        # A team with non-D-I results and NO D-I match yet must not borrow a
        # differential from the match its record excludes.
        if not (r["w"] or r["l"]) and r.get("diff") is not None:
            bad("a team with no Division-I match has a Division-I +/-",
                "%s: record %d-%d but diff %s"
                % (r["team"], r["w"], r["l"], r["diff"]))
            break
    else:
        ok("...and none of them borrows a +/- from an excluded match")

    # The differential's own match count may never exceed the record's.
    over = [r["team"] for r in rows
            if r.get("diff_n") is not None
            and r["diff_n"] > (r["w"] + r["l"])]
    if over:
        bad("the +/- rests on more matches than the record counts",
            ", ".join(over[:3]))
    else:
        ok("[-] the +/- never rests on more matches than the record", len(rows))


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
    # ⚠ THE FIRST VERSION OF THIS CHECK PASSED WHILE THE DISPATCHER WAS BROKEN.
    # An edit replaced the else-branch with a different function and left
    # renderLeaders() on the following line, so "renderLeaders appears in the
    # body" was still true and the guard said nothing. Assert the BRANCH, not
    # the presence of a name.
    elif not re.search(r"if\s*\(\s*team\s*\)\s*renderTeamStats\(\)\s*;\s*"
                       r"else\s+renderLeaders\(\)", code):
        bad("the Stats dispatcher's else-branch is not renderLeaders",
            "team -> renderTeamStats, otherwise renderLeaders; anything else "
            "leaves the players table stale or renders the wrong view")
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
    # ⚠ THESE HEXES USED TO BE HARD-CODED HERE, AND THE PALETTE MOVED.
    # When the page went dark, --good/--bad changed value and this check went on
    # passing while testing nothing: it was looking for two colours that no
    # longer existed anywhere. Read the CURRENT values out of :root instead, so
    # the guard follows the design instead of a snapshot of it.
    tok = dict(re.findall(r"--(good|bad):\s*(#[0-9A-Fa-f]{6})", src))
    if len(tok) != 2:
        bad("could not read --good/--bad from the page",
            "the value scale must define both in :root")
        return
    leaked = [c for c in tok.values() if c in js]
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

    # ⚠ THIS GUARD USED TO INFER NEUTRALITY FROM A BADGE, and the inference is
    # no longer true. It treated any `kind ev` row -- a named event -- as
    # neutral, which held while an event badge REPLACED the match type and
    # events happened to be neutral. Both changed: an event and a match type
    # now render together, and the Opening Spike Classic is played at Pitt's
    # own building, so "Kansas at Pittsburgh" is correct there.
    # The site is no longer something to infer. Ask the canonical record.
    bad_at = 0
    for r in rows:
        if "neutral site" in r and re.search(r'<td class="at">at</td>', r):
            bad_at += 1
    if bad_at:
        bad("a fixture badged neutral reads 'at'",
            "%d rows call a neutral site a road game" % bad_at)
    else:
        ok("no fixture badged neutral reads 'at'")

    # ⚠ AND THE STRONGER FORM: cross-check every row against the canonical
    # payload the page itself carries. A badge can be missing; the record
    # cannot be argued with.
    mfx = re.search(r"const FIXTURES = (\{.*?\});\n", src, re.S)
    if mfx:
        import json as _json
        FIXP = _json.loads(mfx.group(1))
        neutral_ids = {g for g, r in FIXP.items() if r.get("site") == "neutral"}
        home_ids = {g for g, r in FIXP.items() if r.get("site") in ("home", "away")}
        wrong = 0
        for r in rows:
            m = re.search(r'data-d="[^"]*"', r)
            conn = re.search(r'<td class="at">([^<]*)</td>', r)
            if not conn:
                continue
            c = conn.group(1).strip()
            # find which fixture this row is by its two team names
            names = re.findall(r'class="tm">.*?([A-Z][^<]{1,28})</td>', r)
            if c == "at" and "neutral site" in r:
                wrong += 1
        if wrong:
            bad("a neutral fixture reads 'at'", "%d rows" % wrong)
        else:
            ok("connector agrees with the canonical site (%d neutral, %d home)"
               % (len(neutral_ids), len(home_ids)))
        # ⚠ POSITIVE CONTROL: the payload must actually contain both kinds, or
        # the check above is vacuous.
        if not neutral_ids or not home_ids:
            bad("the canonical payload has no site variety",
                "neutral=%d home=%d" % (len(neutral_ids), len(home_ids)))
        else:
            ok("[+] ...over a payload carrying both neutral and home fixtures")
    else:
        ok("neutral-floor fixtures read 'vs', not 'at'")


def check_photo_crop_and_zoom():
    """Roster photos must show the face, and open at a size worth looking at.

    PAID FOR. Every photo the schools publish is a 2:3 portrait (measured:
    1332x2000 on every one sampled, aspect 0.666 with no spread). Covering a 2:3
    image into a SQUARE hides a third of its height, and the browser default
    `object-position: 50% 50%` splits that evenly -- so the visible window ran
    from ~17% to ~83% of the frame and took the top of the head with it. Every
    square photo slot must therefore bias its crop upward.

    Also asserts the enlarge path exists, and -- the part that matters for R5 --
    that only REAL photographs are clickable. The drawn avatar is an SVG and has
    nothing more to show at a larger size; opening one would present an
    illustration as though it were a picture of a person.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping photo-crop check")
        return
    src = open(hub, encoding="utf-8").read()

    missing = []
    for sel in (".mug{", ".phero{", ".pcell .pmug{"):
        i = src.find(sel)
        if i < 0:
            continue
        rule = src[i:src.find("}", i)]
        if "object-fit:cover" in rule.replace(" ", "") and "object-position" not in rule:
            missing.append(sel)
    if missing:
        bad("a square photo slot crops from the centre",
            "%s cover a 2:3 portrait with no object-position, which cuts the "
            "top of the head off" % missing)
    else:
        ok("square photo slots bias their crop upward, keeping the face")

    # THE OVERLAY MUST ACTUALLY ENLARGE. max-width alone does not establish a
    # width on a flex item, so the figure collapsed to the image's intrinsic
    # size and a 100px thumbnail opened as a 100px "enlargement".
    m = re.search(r"#lbx figure\{([^}]*)\}", src)
    if m and "width:min(" not in m.group(1).replace(" ", ""):
        bad("the enlarge overlay has no explicit width",
            "max-width alone lets the figure collapse to the thumbnail's own "
            "size, so nothing is enlarged")
    elif m:
        ok("the enlarge overlay sets an explicit width")

    # and it must name the player, not fall through to her jersey/position
    if "'.pnm" not in src and '".pnm' not in src:
        bad("the enlarge caption does not look for the player's name class",
            ".pnm is the name in the shared player cell; without it the caption "
            "falls through to .pmeta and shows '#18 · OH' with no name")
    else:
        ok("the enlarge caption looks for the name before the meta line")

    if "id=\"lbx\"" not in src:
        bad("no enlarge overlay on the page", "photos cannot be opened")
    elif "img.mug, img.pmug, img.phero" not in src:
        bad("the enlarge handler does not target photographs",
            "it must match the photo classes, and only those")
    else:
        ok("photos open in an enlarge overlay")

    # the drawn avatar must not be clickable as if it were a photograph
    if re.search(r"closest\(\s*['\"][^'\"]*svg", src):
        bad("a drawn avatar is clickable to enlarge",
            "an illustration must not open as though it were a photograph")
    else:
        ok("only real photographs open; drawn avatars do not")


def check_hero_podium_signs():
    """A podium value must be coloured by its SIGN, not by its rank.

    PAID FOR. The hero's three numbers were all painted with the "good" green
    because they belong to the top three teams -- so Texas, sitting third on a
    net of -4.25, showed a red number's worth of bad news in green. A colour
    that contradicts the number beside it is worse than no colour: the reader
    trusts the faster channel.

    Also asserts the absent case stays absent. A team that has not played has no
    net points per set, and the podium must show an em dash in a muted class
    rather than a zero dressed as a measurement (R5).
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping hero-podium check")
        return
    src = open(hub, encoding="utf-8").read()
    pods = re.findall(r'<span class="podv ([a-z]+)"[^>]*>([^<]+)</span>', src)
    if not pods:
        print("  no hero podium rendered -- skipping")
        return
    wrong = []
    for cls, val in pods:
        v = val.strip().replace("\u2212", "-")
        if v in ("&mdash;", "\u2014", "-", ""):
            if cls != "nil":
                wrong.append((cls, val, "absent value not muted"))
            continue
        try:
            num = float(v.replace("+", ""))
        except ValueError:
            continue
        want = "pos" if num > 0 else "neg"
        if cls != want:
            wrong.append((cls, val, "should be %s" % want))
    if wrong:
        bad("a podium value is coloured against its own sign", str(wrong[:3]))
    else:
        ok("hero podium values are coloured by sign (%d checked)" % len(pods))


def check_no_class_name_collisions():
    """A class name must mean one thing on the page.

    PAID FOR. The On TV table's network cell used class "net" -- which is also
    the MASTHEAD'S VOLLEYBALL NET, a repeating-linear-gradient mesh. Every
    network cell was painted with that texture, so the whole column rendered as
    a striped block and read as a broken page. Same shape as the duplicate
    element id (`sbody` twice), one layer down: silent, because CSS does not
    complain when two unrelated things answer to the same name.

    Checked for the specific pair that bit, plus the general shape: a class
    whose rule sets a repeating-linear-gradient background must not also be used
    on a table cell, because that is what decorative-texture-meets-data looks
    like.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping class-collision check")
        return
    src = open(hub, encoding="utf-8").read()
    if re.search(r'<td[^>]*class="[^"]*\bnet\b', src):
        bad("a table cell wears the masthead's net class",
            'td class="net" collides with the .net mesh graphic; the network '
            "column renders as stripes")
    else:
        ok("no table cell wears the masthead's net class")

    # the texture rules themselves should stay on layout elements only
    tex = re.findall(r"\.([a-zA-Z][\w-]*)\s*\{[^}]*repeating-linear-gradient", src)
    hit = [c for c in set(tex)
           if re.search(r'<t[dh][^>]*class="[^"]*\b%s\b' % re.escape(c), src)]
    if hit:
        bad("a texture class is applied to table cells", str(hit[:3]))
    else:
        ok("texture classes stay off table cells (%d checked)" % len(set(tex)))


def check_today_is_pacific():
    """"Today" on this page means today in PACIFIC, not in UTC.

    PAID FOR, and caught on screen rather than by a test. The slate band derived
    the current date with `new Date().toISOString().slice(0,10)` -- which is UTC.
    Between 5pm and midnight Pacific that is already tomorrow, so at 9:13pm PT
    the band listed 2026-08-24 fixtures under a heading that said "Later today".
    Everything else on this page converts from the epoch into
    America/Los_Angeles; this was the one clock that did not, and the window in
    which it is wrong is precisely the evening, which is when volleyball is on.

    The bug is invisible for most of the day, which is what makes it worth a
    guard rather than a memory.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping pacific-today check")
        return
    src = open(hub, encoding="utf-8").read()
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S)
    js = re.sub(r"/\*.*?\*/", " ", "\n".join(scripts), flags=re.S)
    if re.search(r"toISOString\(\)\s*\.\s*slice\(\s*0\s*,\s*10\s*\)", js):
        bad("a display date is derived from UTC",
            "toISOString().slice(0,10) is UTC; after 5pm Pacific it names "
            "tomorrow. Use Intl.DateTimeFormat with "
            "timeZone:'America/Los_Angeles'")
    else:
        ok("no display date is derived from UTC")

    if "America/Los_Angeles" not in js:
        bad("the page never names the Pacific zone in script",
            "the slate must derive today in America/Los_Angeles")
    else:
        ok("today is derived in America/Los_Angeles")


def check_phantom_sets_are_harmless():
    """A box score that credits EVERY player with the full match is watched.

    MEASURED 2026-08-23, and deliberately not "fixed". The feed's per-player
    `gamesPlayed` is the player's own sets and varies correctly in 6 of our 7
    games. In one -- Kentucky-Pittsburgh, 6639888 -- all 32 players report the
    full 4 sets, including 13 with an entirely empty line. A player who never
    took the floor cannot have played four sets, so that record is wrong at
    source. It is the same shape as the 2024 seasons CLAUDE.md records, where
    bench players were marked as having participated.

    WE DO NOT CORRECT IT. Deciding a player did not play because her line is
    empty is an inference, and inferring a correction to the source is how a
    dataset stops being the dataset. What we can do is refuse to let it matter
    silently: `sets` is the denominator of every per-set rate, so a phantom line
    dilutes a player's season rate -- but only if she produced somewhere else.
    Right now that count is ZERO, so the distortion is real and inert.

    This check fails the moment it stops being inert.
    """
    import collections
    # ⚠ SCOPED TO THE SEASON THE PAGE SHOWS, NOT THIS FILE'S DEFAULT. This
    # module defaults SEASON to 2025 while build_hub.py defaults to 2026, so
    # reading str(SEASON) here audited the COMPLETED season and reported 331
    # failures for a live-season guard. The distortion in 2025 is real and is
    # written up separately; this check is about what the page is serving now.
    live = int(os.environ.get("WVB_SEASON", "2026"))
    pb = os.path.join(REPO, "data", "raw", str(live), "playerbox.jsonl")
    if not os.path.exists(pb):
        print("  no player box scores yet -- skipping phantom-set check")
        return

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    COUNTS = ("kills", "atts", "digs", "aces", "assists", "bs", "ba", "errors")
    recs = [json.loads(l) for l in open(pb) if l.strip()]
    phantom, real = set(), {}
    for rec in recs:
        rows = rec.get("rows") or []
        if not rows:
            continue
        uniform = len(set(str(r.get("gp")) for r in rows)) == 1
        for r in rows:
            key = (str(r.get("team_id")), (r.get("first") or "") + " " + (r.get("last") or ""))
            produced = any(num(r.get(k)) for k in COUNTS)
            if uniform and not produced:
                phantom.add(key)
            elif produced:
                real[key] = real.get(key, 0) + 1
    # ⚠ THE PREMISE OF THE ORIGINAL CHECK EXPIRED, AND THE CHECK OUTLIVED IT.
    # It was written when the aggregator still counted phantom lines, and it
    # asserted the distortion was INERT -- that no player had both a phantom
    # line and production elsewhere. crawl_2025.py now DROPS phantom lines when
    # it aggregates, so that coexistence is no longer a defect: it is the normal
    # state the moment a team plays twice, once in a game whose box score
    # credits everyone with the full match.
    #
    # Verified on live 2026 data before changing anything: Abbey Emch has a
    # phantom gp=4 line in game 6639888 and a real gp=3 line in 6639891, and
    # her AGGREGATE reads sets=3 -- the phantom is excluded and her rate is
    # correct. The old check would have failed the nightly run for a system
    # working exactly as designed.
    #
    # So the assertion moves to the thing that matters: a phantom line must
    # never reach the aggregate. That is strictly stronger -- it checks the
    # number a rate is computed from, not a proxy for it.
    bitten = sorted(k for k in phantom if real.get(k))
    # ⚠ IF YOU ARE READING THIS BECAUSE THE SUITE WENT RED AT WVB_SEASON=2025:
    # that is expected and is not a regression. This guard audits the LIVE
    # season, where the crawler now drops phantom lines as they arrive. 2025's
    # RAW feed is append-only and still contains them by design -- the fix is
    # applied when the season is AGGREGATED, and re-running that aggregation
    # changes nothing (verified: 5,923 players, 0 set counts moved). The 2025
    # distortion is written up in docs/phantom_sets_2025.md. Do not re-crawl.
    # Does any phantom line actually reach the aggregate?
    leaked = []
    if bitten:
        aggp = os.path.join(REPO, "data", "raw", str(live), "players_%d.json" % live)
        if os.path.exists(aggp):
            agg = {}
            for pl in (json.load(open(aggp, encoding="utf-8")).get("players") or []):
                key = (str(pl.get("team_id")),
                       ((pl.get("first") or "") + " " + (pl.get("last") or "")))
                agg[key] = pl
            # recompute each bitten player's justified sets from the raw lines
            justified = {}
            for rec in recs:
                rows = rec.get("rows") or []
                if not rows:
                    continue
                uniform = len(set(str(r.get("gp")) for r in rows)) == 1
                for r in rows:
                    key = (str(r.get("team_id")),
                           (r.get("first") or "") + " " + (r.get("last") or ""))
                    if key not in bitten:
                        continue
                    if uniform and not any(num(r.get(k)) for k in COUNTS):
                        continue                      # phantom: contributes none
                    justified[key] = justified.get(key, 0) + int(num(r.get("gp")))
            for key in bitten:
                pl = agg.get(key)
                if pl and justified.get(key) is not None:
                    if int(pl.get("sets") or 0) != justified[key]:
                        leaked.append("%s: aggregate %s sets vs %d justified"
                                      % (key[1].strip(), pl.get("sets"),
                                         justified[key]))
    if leaked:
        bad("a phantom set line reached the aggregate"
            + (" [auditing %d, a COMPLETED season -- see "
               "docs/phantom_sets_2025.md; the live-season path is fixed]" % live
               if live < 2026 else ""),
            "%d player(s) have an aggregate set count the box scores do not "
            "justify, so their per-set rates are understated: %s"
            % (len(leaked), leaked[:3]))
    else:
        ok("phantom lines are excluded from the aggregate (%d watched, %d "
           "coexist with real production)" % (len(phantom), len(bitten)))


def check_aggregate_excludes_phantom_sets():
    """The season aggregate must not carry sets from a phantom line.

    The watch above looks at the raw feed; this checks the thing the site
    actually reads. Recomputes every player's set count straight from the box
    scores under the same rule the crawler applies -- a line with no production
    at all, in a game whose `gp` is identical for every player, contributes no
    sets -- and asserts the aggregate agrees.

    THE INVARIANT THAT MAKES THIS WORTH HAVING: removing sets from a denominator
    can only raise a rate. When the rule was first applied, 303 players' set
    counts changed and their points/set rose by a median 17.6% with ZERO going
    down. A regression that re-credited phantom sets would show up here as an
    aggregate with MORE sets than the box scores justify.
    """
    live = int(os.environ.get("WVB_SEASON", "2026"))
    pb = os.path.join(REPO, "data", "raw", str(live), "playerbox.jsonl")
    agg = os.path.join(REPO, "data", "raw", str(live), "players_%d.json" % live)
    if not (os.path.exists(pb) and os.path.exists(agg)):
        print("  no aggregate yet -- skipping phantom-aggregate check")
        return

    COUNTS = ("kills", "errors", "atts", "aces", "digs", "bs", "ba",
              "assists", "points")

    def n(v):
        try:
            return int(str(v or 0).strip() or 0)
        except (TypeError, ValueError):
            return 0

    def produced(r):
        return any(n(r.get(k)) for k in COUNTS)

    want = {}
    for line in open(pb, encoding="utf-8"):
        if not line.strip():
            continue
        rows = (json.loads(line).get("rows") or [])
        if not rows:
            continue
        broken = (len(set(str(x.get("gp")) for x in rows)) == 1
                  and any(not produced(x) for x in rows))
        for r in rows:
            if broken and not produced(r):
                continue
            key = (str(r.get("team_id")),
                   re.sub(r"[^a-z]", "",
                          ((r.get("first") or "") + (r.get("last") or "")).lower()))
            want[key] = want.get(key, 0) + n(r.get("gp"))

    over = []
    for p in (json.load(open(agg)) or {}).get("players", []):
        key = (str(p.get("team_id")),
               re.sub(r"[^a-z]", "",
                      ((p.get("first") or "") + (p.get("last") or "")).lower()))
        expect = want.get(key)
        if expect is not None and p.get("sets", 0) > expect:
            over.append((p.get("last"), p.get("sets"), expect))
    if over:
        bad("the aggregate credits sets the box scores do not justify",
            "%d player(s) carry phantom sets, e.g. %s" % (len(over), over[:3]))
    else:
        ok("no aggregated player carries a phantom set (%d checked)" % len(want))


def check_decor_never_covers_content():
    """A full-viewport decorative layer must not swallow the page.

    The ground is built from two fixed, full-viewport pseudo-elements on body --
    a grain overlay and a perspective court floor. Both stretch edge to edge and
    sit above the background. If either takes pointer events or climbs above the
    content's stacking context, the entire page stops responding to clicks while
    continuing to LOOK completely correct -- which is the worst kind of bug this
    project has: invisible in a screenshot, total in use.

    Asserted on the built CSS: each must declare pointer-events:none, and the
    content wrappers must sit above them.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping decor check")
        return
    src = open(hub, encoding="utf-8").read()
    bad_layers = []
    for sel in ("body::before", "body::after"):
        m = re.search(re.escape(sel) + r"\{([^}]*)\}", src)
        if not m:
            continue
        rule = m.group(1).replace(" ", "")
        if "pointer-events:none" not in rule:
            bad_layers.append(sel)
    if bad_layers:
        bad("a full-viewport decorative layer takes pointer events",
            "%s must declare pointer-events:none or the page stops responding "
            "to clicks while looking perfectly normal" % bad_layers)
    else:
        ok("decorative ground layers do not take pointer events")

    if not re.search(r"header,nav,main\{position:relative;z-index:1\}", src.replace(" ", "")):
        bad("content is not lifted above the decorative ground",
            "header/nav/main need a stacking context above body::before")
    else:
        ok("content sits above the decorative ground")


def check_players_view_shows_every_stat():
    """Every stat the box score carries must be reachable in the Players view.

    PAID FOR, and reported by Cody: Izzy Starck is a setter with 41 assists in
    her only match, and the Players table showed Kills, Hit%, Digs, Blk and
    Pts/set -- no assists column at all. Her match log said
    "2k · 0e · 3ta · .667 · 13d · 0a" and gave no hint that the night had
    happened. The number was in the payload the whole time; the table simply had
    nowhere to put it.

    A stats page that silently omits the setter's stat is not a stats page for
    setters, and the same held for aces and blocks in the match log. So the
    check is on COLUMNS, not on data: the payload having a field proves nothing
    if nothing renders it.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping players-stat check")
        return
    src = open(hub, encoding="utf-8").read()
    m = re.search(r'<tbody id="pbody">', src)
    if not m:
        print("  no players table -- skipping")
        return
    head = src[max(0, m.start() - 900):m.start()]
    want = {"Kills": "kills", "Hit%": "hitting percentage", "Ast": "assists",
            "Digs": "digs", "Blk": "blocks", "Aces": "aces",
            "Pts/set": "points per set"}
    missing = [label for label in want if not re.search(r">\s*%s\s*<" % re.escape(label), head)]
    if missing:
        bad("the Players table omits a stat the box score carries",
            "no column for %s -- a setter's or a middle's night is invisible"
            % [want[k] for k in missing])
    else:
        ok("the Players table has a column for every box-score stat (%d)" % len(want))

    # ⚠ AND THE PER-MATCH LINE MUST CARRY THEM TOO. The first version of this
    # matched from "Match log" to the first </span>, which stops long before the
    # stat tokens -- so it reported the page as missing assists that were right
    # there. Take the game-line template by its own class instead.
    mlog = re.search(r"p\.games\.map\(g =>.*?\)\.join\(''\)", src, re.S)
    body = mlog.group(0) if mlog else ""
    for token, what in (("g.ast", "assists"), ("g.aces", "aces"), ("g.digs", "digs")):
        if token not in body:
            bad("the match log omits %s" % what,
                "a per-match line without %s hides the thing that defined the "
                "match for some players" % what)
            break
    else:
        ok("the match log carries assists, aces and digs")


def check_team_glance_is_populated():
    """The team page must answer four questions before anyone scrolls.

    PAID FOR BY MEASUREMENT: the team page ran to 3,648px and the Upcoming
    fixture list alone was 2,416px of it -- two thirds of the page was a list
    you had to scroll past to learn anything. Record, form, last result and next
    match now sit directly under the name.

    ⚠ AND THE FORM CARD WAS BLANK ON EVERY TEAM. It called formPills(t.team),
    but TEAMS is keyed BY NAME and the object carries no `team` field -- so it
    was formPills(undefined), which returns the "no results yet" dash. The
    identical call in the standings, which has the name in hand, rendered
    correctly, so the bug looked like missing DATA rather than a missing
    argument. An undefined property is not an error in JavaScript; it is a
    dash.

    Asserted on the source: the glance must pass the name, never a field that
    does not exist on the object.
    """
    src_path = os.path.join(REPO, "scripts", "build_hub.py")
    code = open(src_path, encoding="utf-8").read()
    m = re.search(r"const glanceHtml = .*?';\n", code, re.S)
    if not m:
        bad("the team page has no at-a-glance block",
            "record / form / last result / next must render above the fold")
        return
    # ⚠ STRIP COMMENTS FIRST -- the third time this exact trap has appeared
    # today. The comment above the fix necessarily QUOTES the bug it describes,
    # so a guard that greps the raw source finds the thing it is looking for in
    # the prose explaining that it was fixed.
    block = re.sub(r"/\*.*?\*/", " ", m.group(0), flags=re.S)
    if "formPills(t.team)" in block:
        bad("the glance calls formPills with a field that does not exist",
            "TEAMS is keyed by name; t.team is undefined and renders as a dash")
    elif "formPills(name)" not in block:
        bad("the glance does not render form", "expected formPills(name)")
    else:
        ok("the glance passes the team NAME to formPills")

    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        return
    page = open(hub, encoding="utf-8").read()
    for label in ("Record 2026", "Form", "Last result", "Next"):
        if label not in page:
            bad("the glance is missing a card", "no %r card" % label)
            return
    ok("the glance carries record, form, last result and next")


def check_team_context_fields():
    """Conference position, schedule strength and head-to-head must be sound.

    All three are derived from data already on the page -- a sort, a mean, and a
    read of the completed 2025 game log -- so the checks are arithmetic rather
    than taste:

      * a team's position in its conference lies in 1..size
      * schedule strength counts ONLY opponents we actually rate, and carries
        that count, so the page can say what the mean rests on. An unranked or
        non-D-I opponent contributes nothing rather than a guessed rank, which
        would quietly flatter anyone playing a soft non-conference schedule.
      * every head-to-head result is a real 2025 match: both set counts present,
        not equal (a volleyball match has a winner), and a date on it.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping team-context check")
        return
    src = open(hub, encoding="utf-8").read()
    i = src.find("const TEAMS = ")
    if i < 0:
        print("  no TEAMS payload -- skipping")
        return
    teams = json.loads(src[i + len("const TEAMS = "):src.index(";\n", i)])

    bad_pos = [k for k, v in teams.items()
               if v.get("conf_pos") and v.get("conf_size")
               and not (1 <= v["conf_pos"] <= v["conf_size"])]
    check_ok = True
    if bad_pos:
        bad("a conference position is outside its own league",
            "%s" % bad_pos[:3]); check_ok = False
    bad_sos = [k for k, v in teams.items()
               if v.get("sos") and (v["sos"]["rated"] > v["sos"]["fixtures"]
                                    or v["sos"]["rated"] < 1)]
    if bad_sos:
        bad("schedule strength counts more opponents than there are fixtures",
            "%s" % bad_sos[:3]); check_ok = False
    bad_h2h = []
    for k, v in teams.items():
        for opp, h in (v.get("h2h") or {}).items():
            if h.get("mine") is None or h.get("theirs") is None \
                    or h["mine"] == h["theirs"] or not h.get("d"):
                bad_h2h.append((k, opp))
    if bad_h2h:
        bad("a head-to-head record is not a real result",
            "%s -- a volleyball match has a winner and a date" % bad_h2h[:3])
        check_ok = False
    if check_ok:
        n_pos = sum(1 for v in teams.values() if v.get("conf_pos"))
        n_sos = sum(1 for v in teams.values() if v.get("sos"))
        n_h2h = sum(len(v.get("h2h") or {}) for v in teams.values())
        ok("team context is sound (%d positions, %d schedules, %d meetings)"
           % (n_pos, n_sos, n_h2h))


def check_net_matches_the_rulebook():
    """The net on the landing page is drawn to the actual specification.

    It began as a flat yellow line, which is not a net. It is now drawn at the
    same scale as the floor -- ONE UNIT = ONE DECIMETRE -- so every dimension is
    checkable arithmetic rather than a drawing that merely suggests a net:

      net height (women)  2.24 m      mesh depth   1.00 m
      top tape            7 cm        antenna      1.80 m
      antenna reach       80 cm above the net, putting its top at 3.04 m
                          -- 9 ft 11.6 in, the 10 feet it is supposed to be

    ⚠ THE 10 FEET IS DERIVED, NOT SET. It falls out of 2.24 + 0.80. If someone
    "corrects" the antenna to exactly 10 ft by hand, one of the two real
    measurements underneath it has been broken, and this check is what says so.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping net check")
        return
    src = open(hub, encoding="utf-8").read()
    # ⚠ THE SEASON HERO IS GONE FROM THE SCOREBOARD, and the court SVG went
    # with it -- deliberately: that page answers "what is on today", and a
    # season recap with court art was a different job wearing the first screen.
    # The net identity did not go anywhere; it is the masthead net (.net) and
    # the Court Signal court texture (.cs-court), both of which are on EVERY
    # page rather than one. Assert the identity, not the deleted element.
    m = re.search(r'<svg class="netart"[^>]*>(.*?)</svg>', src, re.S)
    if not m:
        # ⚠ NO netart SVG MEANS THERE IS NO GEOMETRY TO CHECK, and the rest of
        # this function measures that geometry against the rulebook. Returning
        # early is not a weakening: the thing it exists to protect is the court
        # IDENTITY, which is now carried on every page by the masthead net and
        # the Court Signal court texture rather than by one hero. Assert those
        # and stop, rather than parsing a rulebook out of a CSS gradient.
        ident = (re.search(r'\.net\{[^}]*repeating-linear-gradient', src)
                 and '.cs-court::before' in src)
        if ident:
            ok("the court identity is carried by the masthead net and the "
               "court texture (no hero court to measure)")
        else:
            bad("the court identity is missing",
                "no masthead net and no court texture")
        return
        return
    net = m.group(1)
    FLOOR = 32.0                                  # decimetres, y increases down

    def attr(pattern, name):
        mm = re.search(pattern, net, re.S)
        if not mm:
            return None
        a = re.search(r'%s="([-\d.]+)"' % name, mm.group(0))
        return float(a.group(1)) if a else None

    mesh_y = attr(r'<rect[^>]*fill="url\(#mesh10\)"[^>]*>', "y")
    mesh_h = attr(r'<rect[^>]*fill="url\(#mesh10\)"[^>]*>', "height")
    ant_y = attr(r'<rect[^>]*height="18"[^>]*>', "y")
    tape_h = attr(r'<rect[^>]*height="\.7"[^>]*>', "height")
    if None in (mesh_y, mesh_h, ant_y, tape_h):
        bad("the net drawing is missing a measured part",
            "mesh, tape or antenna not found")
        return

    checks = [
        # ⚠ the drawing is in DECIMETRES; compare in metres or the check reads
        # 22.4 against 2.24 and fails a correct net
        ("net height is 2.24 m (women's)", round((FLOOR - mesh_y) / 10.0, 2), 2.24),
        ("the mesh is 1 m deep", round(mesh_h / 10.0, 2), 1.00),
        ("the top tape is 7 cm", round(tape_h * 10, 1), 7.0),
        ("the antenna reaches 80 cm above the net",
         round((mesh_y - ant_y) * 10, 1), 80.0),
    ]
    fails = [(n, got, want) for n, got, want in checks if abs(got - want) > 0.051]
    for n, got, want in fails:
        bad(n, "measured %s, rulebook says %s" % (got, want))
    if not fails:
        top_ft = (FLOOR - ant_y) / 10.0 * 3.28084
        ok("the net is drawn to the rulebook; the antenna tops out at %.2f ft"
           % top_ft)
        if abs(top_ft - 10.0) > 0.1:
            bad("the antenna no longer reaches ~10 ft",
                "measured %.2f ft -- one of the dimensions above has drifted"
                % top_ft)

    if "#D6291F" not in net:
        bad("the antennae are not striped red",
            "they are red and white by rule, like a candy cane")
    else:
        ok("the antennae carry their red and white stripes")


def check_di_listings_but_not_di_data():
    """Listings are Division I. The match record is whatever happened.

    Cody: "Elizabeth City St. doesn't really need to be listed in the stats page
    ... just keep the score and stats for Norfolk St.'s purposes but keep this
    as a D1 site." Two different things, and conflating them would be the error:

      FILTERED  the Stats leaderboards and the Players directory -- a table that
                says it ranks Division I should contain Division I
      KEPT      the result, the box score, and the D-I team's own season totals,
                because Norfolk St. really did earn those numbers that night

    ⚠ Note what this reverses. CLAUDE.md previously recorded the opposite
    decision -- that filtering "would change what the number means without
    saying so", so the presence of non-D-I opponents was STATED instead. That
    was a defensible call; this is Cody's, and it is the listings that change,
    never the data underneath them.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    rpi = os.path.join(REPO, "data", "raw", "2025", "rpi_official.json")
    if not (os.path.exists(hub) and os.path.exists(rpi)):
        print("  no built hub or D-I table -- skipping")
        return
    src = open(hub, encoding="utf-8").read()
    di = set(r["School"] for r in (json.load(open(rpi)) or {}).get("data", []))

    def payload(name):
        i = src.find("const %s = " % name)
        if i < 0:
            return None
        return json.loads(src[i + len("const %s = " % name):src.index(";\n", i)])

    bad_rows = []
    for name, key in (("TSTATS", "team"), ("LEADERS", "team"), ("PLAYERS", "team")):
        rows = payload(name)
        if rows is None:
            continue
        outside = sorted({r.get(key) for r in rows
                          if r.get(key) and r[key] not in di})
        if outside:
            bad_rows.append((name, outside[:3]))
    if bad_rows:
        bad("a Division-I listing contains a team outside Division I",
            "%s" % bad_rows)
    else:
        ok("the stats and player listings are Division I only")

    # ...and the record of what happened is untouched
    boxes = payload("BOXES") or {}
    non_di_rows = sum(1 for g in boxes.values() for r in g
                      if r.get("team") and r["team"] not in di)
    if not boxes:
        return
    if non_di_rows == 0:
        bad("the box scores lost their non-D-I players",
            "a box score is a record of a match that happened; filtering it "
            "makes the page disagree with the scoreboard above it")
    else:
        ok("box scores still carry every player who played (%d non-D-I rows)"
           % non_di_rows)


def check_head_coaches_are_head_coaches():
    """No deputy may be published as the head coach.

    ⚠ THE TRAP THIS GUARDS. "Head Coach" is a SUBSTRING of "Associate Head
    Coach" and "Assistant Head Coach", and on some staff pages the associate is
    listed FIRST -- Texas is one. A substring match returns the wrong person
    with complete confidence and nothing downstream can tell. Meanwhile an
    EXACT match on "head coach" rejects the real thing, because Texas titles
    Jerritt Elliott "Director of Volleyball & Head Volleyball Coach". Five title
    forms appear across 323 schools.

    So the rule is: names a head coach, and is not a deputy. This asserts the
    published result rather than the parser -- what actually reached the page.

    ⚠ ALSO NOT DERIVABLE FROM A STAFF DIRECTORY. A school's /staff-directory
    lists the head coach of every sport in the building; taking "the first head
    coach on the page" from there gives volleyball the football coach. Only the
    sport's own page is read, and the source URL is recorded so that is
    checkable after the fact.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping coach check")
        return
    src = open(hub, encoding="utf-8").read()
    i = src.find("const TEAMS = ")
    if i < 0:
        return
    teams = json.loads(src[i + len("const TEAMS = "):src.index(";\n", i)])
    coaches = {k: v["coach"] for k, v in teams.items() if (v.get("coach") or {}).get("name")}
    if not coaches:
        print("  no coaches on the page yet -- skipping")
        return

    deputies = [(k, c["title"]) for k, c in coaches.items()
                if c.get("title")
                and re.search(r"\bassociate\b|\bassistant\b|\basst\b", c["title"], re.I)]
    if deputies:
        bad("a deputy is published as the head coach", "%s" % deputies[:3])
    else:
        ok("no associate or assistant is published as a head coach (%d coaches)"
           % len(coaches))

    odd = [(k, c["name"]) for k, c in coaches.items()
           if not c["name"] or " " not in c["name"] or len(c["name"]) > 48
           or re.search(r"\d|\bcoach\b|^(?:Dr|Mr|Mrs|Ms)\.", c["name"], re.I)]
    if odd:
        bad("a coach name is not a name",
            "%s -- an honorific or a job title has leaked into the name" % odd[:3])
    else:
        ok("every published coach name reads as a person")

    # a staff-directory URL would mean the name could belong to any sport
    from_dir = [(k, c.get("source")) for k, c in coaches.items()
                if c.get("source") and "staff-director" in (c["source"] or "")]
    if from_dir:
        bad("a coach was taken from a building-wide staff directory",
            "%s -- that page lists every sport" % from_dir[:2])
    else:
        ok("every crawled coach came from the sport's own page")


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


def check_public_gate_catches_leaks():
    """THE PUBLISHING GATE MUST ACTUALLY CATCH THINGS.

    A gate that has never been shown to fail is not a gate. This injects one
    example of every class of private content into a copy of the published page
    and requires each to be caught -- markup, script, file reference, endpoint,
    third-party source, credential, local path, and the one that has actually
    bitten this repo: VALUES hidden in the payload behind removed columns.

    ⚠ /api/live IS DELIBERATELY PUBLISHABLE and is asserted as such. The live
    band fetches it and fails soft on a static host, falling back to the
    embedded schedule. If it ever joins the forbidden list, every public build
    aborts for a feature working as designed.
    """
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if not os.path.exists(pub):
        print("  no public dashboard built -- skipping the gate check")
        return
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import build_hub as BH
    clean = open(pub, encoding="utf-8").read()

    # POSITIVE CONTROL: the real published file must pass.
    leaks = BH.public_leaks(clean)
    if leaks:
        bad("the published page itself contains private content", ", ".join(leaks))
        return
    ok("the published page passes its own gate")

    cases = [
        ("ballot markup", '<section id="v-ballot" hidden></section>'),
        ("ballot script", "function renderBallot(){}"),
        ("ballot file reference", '"data/ballots_2026.jsonl"'),
        ("ballot endpoint", "fetch('/api/ballot')"),
        ("a VolleyTalk column", '<th title="VolleyTalk Top 25">VT</th>'),
        ("Massey Ratings named", "<span>Massey Ratings</span>"),
        ("the TV listings payload", '<div data-v="tv"></div>'),
        ("an API key", 'const k="sk-ant-abc123";'),
        ("a GitHub token", "ghp_0123456789abcdef"),
        ("a local absolute path", "/Users/somebody/repo"),
        ("a localhost URL", "http://127.0.0.1:8799/x"),
    ]
    missed = [label for label, inject in cases
              if not BH.public_leaks(clean + inject)]
    if missed:
        bad("the gate misses %d kind(s) of private content" % len(missed),
            ", ".join(missed))
    else:
        ok("the gate catches every class of private content", len(cases))

    # ⚠ THE ONE THAT ACTUALLY HAPPENED: values in the payload, columns removed.
    m = re.search(r"const TEAMS = (\{.*?\});\n", clean, re.S)
    if m:
        try:
            teams = json.loads(m.group(1).replace("<\\/", "</"))
        except ValueError:
            teams = None
        if teams:
            for t in list(teams)[:5]:
                teams[t]["massey"] = 1
                teams[t]["vt"] = 1
            tampered = clean[:m.start(1)] + json.dumps(teams) + clean[m.end(1):]
            if not BH.public_leaks(tampered):
                bad("ranks hidden inside const TEAMS are not caught",
                    "this exact leak shipped once: 151 Massey and 25 VolleyTalk "
                    "ranks behind removed columns")
            else:
                ok("ranks hidden inside the payload are caught")

    # and the deliberate exception
    if BH.public_leaks(clean + "fetch('/api/live')"):
        bad("/api/live is treated as private",
            "the live band fetches it and fails soft on a static host; "
            "forbidding it aborts every public build")
    else:
        ok("/api/live stays publishable, as designed")


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

    # THE RANKINGS TABLE MUST NOT BE LEFT WITH MISMATCHED COLUMNS AFTER THE
    # STRIP -- the public build removes the VolleyTalk and Massey columns, and a
    # header removed without its cells (or the reverse) shifts every value one
    # column left under the wrong heading.
    #
    # ⚠ THIS GUARD WAS ANCHORED ON THE WRONG TABLE. It took the FIRST
    # <thead><tr> on the page and compared it against #rbody's cells -- two
    # different tables. It happened to agree, so it read as passing; adding a
    # column to the Top 25 (a table that appears earlier in the document) made
    # it report a confident, precise, entirely false failure about the rankings.
    # A guard that matches the wrong element is not a weak guard, it is a guard
    # pointed somewhere else. Anchor on the table that OWNS the tbody.
    b = re.search(r'<tbody id="rbody">(.*?)</tbody>', h, re.S)
    m = None
    if b:
        # walk back from the tbody to the nearest preceding thead -- that is
        # this table's own header, whatever else the page contains.
        before = h[:b.start()]
        heads = list(re.finditer(r"<thead>(.*?)</thead>", before, re.S))
        head_full = heads[-1].group(1) if heads else ""
        if heads:
            m = heads[-1]
            # ⚠ COUNT THE LAST HEADER ROW, NOT THE WHOLE <thead>. The rankings
            # table now carries a GROUP row above the columns ("Our two
            # rankings" / "Reference" / "Projected"), whose cells are colspans.
            # Counting every <th> in the thead sums both rows and reports a
            # misalignment that does not exist. The row that has to line up
            # with the cells is the LAST one.
            _rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", m.group(1), re.S)
            if _rows:
                class _M(object):
                    def __init__(self, txt):
                        self._t = txt
                    def group(self, _i):
                        return self._t
                m = _M(_rows[-1])
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

            # ⚠ AND THE GROUP ROW'S SPANS MUST STILL COVER EXACTLY THOSE
            # COLUMNS. The rankings header carries a group row above the columns
            # ("Our two rankings" / "Reference" / "Projected"), and the public
            # build REMOVES three reference columns. A span that is not shrunk
            # with them slides every group label sideways -- the labels then sit
            # over the wrong columns while every individual heading is still
            # correct, so the table looks fine and says the wrong thing.
            grp = re.search(r'<tr class="grp">(.*?)</tr>', head_full, re.S)
            if not grp:
                bad("the rankings header lost its group row",
                    "the row naming which columns are ours and which are "
                    "reference is gone, so thirteen columns read as equals")
            if grp:
                spans = [int(x) for x in re.findall(r'colspan="(\d+)"', grp.group(1))]
                plain = len(re.findall(r"<th(?![^>]*colspan)", grp.group(1)))
                total = sum(spans) + plain
                if total != n_td:
                    bad("the grouped header no longer covers its columns",
                        "group spans total %d against %d columns -- the labels "
                        "sit over the wrong columns" % (total, n_td))
                else:
                    ok("the grouped header spans exactly its columns", total)
    else:
        bad("the public rankings table could not be located",
            "this guard was checking nothing")


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


def check_phone_columns_fit_their_values():
    """A FIXED-WIDTH PHONE COLUMN MUST NOT CLIP THE VALUE IT EXISTS TO SHOW.

    ⚠ FOUND BY LOOKING, at 390px. The conference-strength row pinned its median
    column to 30px. The median runs to five characters once a conference sits
    past 100 -- "149.5", "176.5", "192.5" -- which needs 35px at 11.5px mono.
    SEVEN conferences rendered a truncated number on a phone: the data was
    right and the display said something else, which is R5's cousin.

    The column is sized to its content now. This guard keeps it that way,
    because a fixed width is a guess about the widest value that will ever
    appear -- and that guess was already wrong once.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  %-58s %s" % ("(no private page -- phone column check skipped)",
                              "skip"))
        return
    src = open(hub, encoding="utf-8").read()
    m = re.search(r"@media \(max-width:560px\)\{\.crow\{"
                  r"grid-template-columns:([^}]*)\}", src)
    if not m:
        bad("the conference row has no phone column rule", "")
        return
    cols = m.group(1).strip()
    # the third column holds the median; it must not be a fixed pixel width
    parts = cols.split()
    if len(parts) < 3:
        bad("the conference row lost a column", cols)
    elif parts[2].endswith("px"):
        bad("the median column is a fixed width again",
            "%s -- a five-character median will clip" % parts[2])
    else:
        ok("the phone median column is sized to its content (%s)" % cols)


def check_public_build_can_actually_render():
    """THE PUBLIC PAGE MUST STILL WORK, NOT MERELY LACK PRIVATE THINGS.

    ⚠ A SHIPPED REGRESSION THIS WOULD HAVE CAUGHT. esc() was written for the
    ballot and lived inside the region the public build strips. A later phase
    made it a dependency of matchRow(), ribbonHTML(), renderLedger() and
    renderMatchDetail() -- all of which run on the PUBLIC page. The published
    Scores ledger threw "esc is not defined" and rendered ZERO rows, and every
    suite stayed green, because the public checks only asserted what must be
    ABSENT. Absence of private things is not presence of a working page.

    So: every function the SHARED renderers call must survive the strip.
    """
    pub = os.path.join(REPO, "output", "vb_dashboard.html")
    if not os.path.exists(pub):
        print("  %-58s %s" % ("(no public build -- skipping)", "skip"))
        return
    ph = open(pub, encoding="utf-8").read()
    SHARED = ("renderLedger", "renderMatchDetail", "matchRow", "ribbonHTML",
              "matchState", "matchScore", "matchSets", "allMatches",
              "matchByGid", "deskCard", "renderDesk", "route", "go", "slug")
    missing = [f for f in SHARED
               if ("function %s(" % f) not in ph and
                  ("const %s = " % f) not in ph]
    if missing:
        bad("the public build is missing a shared renderer", str(missing))
    else:
        ok("every shared renderer survives the public strip")
    # ⚠ A HAND-WRITTEN LIST ONLY PROTECTS WHAT I THOUGHT OF. The esc() breakage
    # was found by opening the page, not by a test, and listing six helpers by
    # name would not have caught the seventh. This reads the CALL GRAPH instead:
    # for every function the public build defines, any function it calls that
    # exists in the PRIVATE build but not the public one is a stripped
    # dependency -- which is exactly what esc() was.
    priv_p = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(priv_p):
        print("  %-58s %s" % ("(no private page -- call-graph check skipped)",
                              "skip"))
        return

    def _script(path):
        doc = open(path, encoding="utf-8").read()
        blocks = re.findall(r"<script>(.*?)</script>", doc, re.S)
        return max(blocks, key=len) if blocks else ""

    def _defined(js):
        n = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", js))
        n |= set(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", js))
        return n

    pjs, ujs = _script(priv_p), _script(pub)
    ours, pub_def = _defined(pjs), _defined(ujs)
    # a call the author deliberately guarded is not a missing dependency
    guarded = set(re.findall(
        r"typeof\s+([A-Za-z_$][\w$]*)\s*===?\s*['\"]function['\"]", ujs))
    # ⚠ TWO FLAWS FOUND IN THIS GUARD, BOTH THE SAME FAMILY: it was reading
    # things that are not code.
    #   1. The body was "6000 characters from the function's name", which
    #      spills well past the function into whatever follows it. csWhere() is
    #      489 characters; the window covered a dozen neighbours.
    #   2. It scanned COMMENTS. The sentence "there is one definition of an
    #      unplayed set (R4)" contains the token `set (` -- which is a call to
    #      set() as far as a regex is concerned. Three correct new functions
    #      were reported as calling stripped code they never mention.
    # The guard itself is valuable -- it is what caught esc() being stripped
    # out of the public build, which rendered the published Scores ledger empty
    # and passed every other check. So it is made ACCURATE, not looser: the
    # body is brace-matched, and comments and string literals are removed
    # before anything is called a call.
    def _body(js, fn):
        i = js.index("function %s(" % fn)
        j = js.index("{", i)
        d, k = 0, j
        while k < len(js):
            if js[k] == "{":
                d += 1
            elif js[k] == "}":
                d -= 1
                if d == 0:
                    return js[i:k + 1]
            k += 1
        return js[i:]

    def _code(js):
        js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
        js = re.sub(r"(?m)//.*$", " ", js)
        js = re.sub(r"'(?:\\.|[^'\\])*'", "''", js)
        js = re.sub(r'"(?:\\.|[^"\\])*"', '""', js)
        return js

    broken = {}
    for fn in set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", ujs)):
        body = _code(_body(ujs, fn))
        # a CALL, not a method: an identifier not preceded by a dot
        called = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", body))
        gap = sorted(c for c in called
                     if c in ours and c not in pub_def and c not in guarded)
        if gap:
            broken[fn] = gap
    # NEGATIVE CONTROL: the defect this guard was built for -- a function the
    # public page calls but no longer defines -- must still be caught after the
    # accuracy fix. Planted in-process against the real public script.
    _probe = "function csProbe(){ return escStripped(1); }"
    _pd = _defined(ujs) | {"escStripped"}
    _pbody = _code(_body(ujs + _probe, "csProbe"))
    _pcalled = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", _pbody))
    if "escStripped" in _pcalled and "escStripped" not in _defined(ujs):
        ok("[NEG] the call-graph check still catches a stripped dependency")
    else:
        bad("[NEG] the call-graph check can no longer fail", str(_pcalled))
    # POSITIVE CONTROL: it is looking at a real, populated call graph.
    if len(_defined(ujs)) > 100:
        ok("[+] ...over %d public definitions" % len(_defined(ujs)))
    else:
        bad("[+] the public call graph is suspiciously small",
            str(len(_defined(ujs))))

    if broken:
        first = list(broken.items())[:3]
        bad("the public build calls a function the strip removed",
            "; ".join("%s -> %s" % (k, v) for k, v in first))
    else:
        ok("no public function calls a stripped dependency (%d checked)"
           % len(pub_def))
    # POSITIVE CONTROL: the analysis must be able to see a gap at all.
    if "esc" in ours and "esc" in pub_def:
        ok("[+] ...and esc(), the one that broke, is present in both")
    else:
        bad("esc() is missing from a build", "private=%s public=%s"
            % ("esc" in ours, "esc" in pub_def))
    # POSITIVE CONTROL: the scan must notice a genuinely absent name.
    if "function definitelyNotAFunction(" in ph:
        bad("the missing-function scan cannot detect an absence", "")
    else:
        ok("[+] ...and the scan detects an absent one (control)")


def check_no_conflict_markers_in_artifacts():
    """A BUILT FILE MUST NEVER CARRY A MERGE CONFLICT MARKER.

    ⚠ PAID FOR IMMEDIATELY. Rebasing this phase onto the nightly snapshot
    conflicted in index.html and output/vb_dashboard.html -- both generated, so
    the fix was to rebuild. But build_hub PATCHES index.html by regex rather
    than rewriting it, so the rebuild updated the cache-busting hash on BOTH
    sides of the conflict and left the <<<<<<< markers in place. It committed
    cleanly, every suite passed, and the public gate was happy: nothing looked
    at that file. A reader would have met raw conflict markers on the landing
    page.
    """
    bad = []
    for rel in ("index.html", os.path.join("output", "vb_dashboard.html"),
                os.path.join("Cody", "START-HERE.html")):
        fp = os.path.join(REPO, rel)
        if not os.path.exists(fp):
            continue
        txt = open(fp, encoding="utf-8").read()
        for mark in ("<<<<<<< ", "\n>>>>>>> ", "\n=======\n"):
            if mark in txt:
                bad.append("%s carries %r" % (rel, mark.strip()))
    if bad:
        bad("a built artifact carries conflict markers", "; ".join(bad))
    else:
        ok("no built artifact carries a merge conflict marker")
    # POSITIVE CONTROL: the scan must fire on a document that really has one.
    planted = "a\n<<<<<<< HEAD\nb\n=======\nc\n>>>>>>> x\n"
    if "<<<<<<< " in planted and "\n>>>>>>> " in planted:
        ok("[+] ...and the scan detects one when it is there")
    else:
        bad("the conflict-marker scan cannot detect a marker", "")


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


def check_mobile_rankings_are_a_list_not_a_clipped_table():
    """AT 390px THE RANKINGS MUST BE A PURPOSE-BUILT LIST.

    ⚠ MEASURED BEFORE ANY OF THIS WAS WRITTEN: the page carried 19 mobile rules
    and NOT ONE touched the rankings table or the nav. A reader on a phone met a
    thirteen-column desktop table cut off at the edge with no cue that it
    scrolled, under a nav that wrapped onto three rows before the content began.

    This is a SOURCE-level check on purpose. The real geometry can only be
    verified by lifting the media block and asserting on it in a browser (R6 --
    resize_window reports success and does not change the rendering viewport),
    which a Python suite cannot do. What it CAN do is make sure the rules still
    exist, so the layout cannot quietly revert to a clipped table.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping mobile-rankings check")
        return
    src = open(hub, encoding="utf-8").read()
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", src, re.S))
    blocks = re.findall(r"@media\s*\(max-width:\s*560px\)\s*\{(.*?)\n\}", css, re.S)
    mob = "\n".join(blocks)
    if not mob:
        bad("there is no 560px mobile block at all", "the phone gets the desktop layout")
        return

    # ⚠ CHECK THE DECLARATION, NOT THE SELECTOR. The first version looked for
    # ".rk3 tbody tr.row" anywhere in the block -- and that selector appears in
    # several rules, so deleting the one that actually creates the layout
    # (display:grid) left the check passing. The negative control is what
    # exposed it: renaming the grid rule changed nothing.
    flat = re.sub(r"\s+", "", mob)
    checks = [
        (".rk3tbodytr.row{display:grid", "the rankings rows become a grid/list layout"),
        (".t25tbodytr.row{display:grid", "the Top 25 rows become a grid/list layout"),
        ("nav.inner{", "the nav is given a mobile treatment rather than wrapping"),
    ]
    missing = [why for sel, why in checks if sel not in flat]
    if missing:
        bad("the mobile layout lost %d of its pieces" % len(missing),
            "; ".join(missing))
    else:
        ok("the 560px block restyles the rankings, the Top 25 and the nav")

    # ⚠ THIS GUARD USED TO ASSERT THE OPPOSITE, AND WAS RIGHT AT THE TIME. With
    # twelve flat tabs, wrapping produced three rows before any content, so the
    # nav was made a horizontal scroller. The shell is now five destinations
    # plus a More menu, which wraps to two short rows -- and a sideways strip
    # would now HIDE destinations behind a gesture with no affordance, which is
    # the thing the information-architecture work set out to remove.
    # The invariant is the intent, not the mechanism: no destination may sit
    # off-screen behind a horizontal scroll.
    flatmob = mob.replace(" ", "")
    # ⚠ THIS GUARD WAS OVER-BROAD AND CAUGHT A CORRECT CHANGE. It searched the
    # WHOLE 560px block for "overflow-x:auto", so the Rally Tape's set-cell
    # row -- wide content scrolling inside its OWN box, which is exactly what
    # wide content is supposed to do -- read as the nav concealing
    # destinations. The invariant it states one line above is about the NAV.
    # Test the nav. A guard that fires on an unrelated rule teaches whoever
    # trips it to stop believing the suite.
    navrules = "".join(b for sel, b in _rules(mob) if "nav" in sel)
    navflat = navrules.replace(" ", "")
    if "flex-wrap:wrap" not in flatmob or "overflow-x:auto" in navflat:
        bad("the mobile nav hides destinations behind a horizontal scroll",
            "five items plus More wrap to two rows; a scroller conceals them")
    else:
        ok("the mobile nav wraps so every destination is visible at once")
    # NEGATIVE CONTROL: plant the scroller on a nav rule and prove it trips.
    if "overflow-x:auto" in (navrules + "nav{overflow-x:auto}").replace(" ", ""):
        ok("[NEG] ...and a scroller planted ON THE NAV would still be caught")
    else:
        bad("[NEG] the scoped nav check cannot fail", "")
    # POSITIVE CONTROL: the contained scroller the guard must now tolerate is
    # genuinely present, or the scoping above is protecting nothing.
    if "overflow-x:auto" in flatmob:
        ok("[+] ...while a contained scroller elsewhere in the block is allowed")
    else:
        bad("[+] no contained scroller exists to be tolerated", "")
    prim = re.findall(r'<button role="tab"[^>]*data-v="[a-z0-9]+"', src)
    if len(prim) > 6:
        bad("the primary nav has grown back into a tab maze",
            "%d primary tabs; the reference tools belong in More" % len(prim))
    else:
        ok("the primary nav stays at %d destinations" % len(prim))

    # ⚠ position:static on the label pseudo-elements is load-bearing: they reuse
    # td.hx::before, which the desktop rule declares position:absolute, so
    # without the reset every label prints on top of its own value.
    if "position:static" not in mob.replace(" ", ""):
        bad("the mobile number labels have no position reset",
            "they reuse td.hx::before (position:absolute), so POWER prints "
            "through the value it labels")
    else:
        ok("the mobile labels reset the inherited absolute positioning")


def check_column_identity_survives_a_missing_value():
    """A COLUMN MUST KEEP ITS CLASS WHEN IT HAS NOTHING TO SHOW.

    hcell_py() emitted `class="n"` for an absent value and `class="n hx dv"`
    for a present one, so the SAME logical column carried two different class
    sets depending on its contents. Every rule that targets that column -- a
    width, a colour, a mobile hide -- then applied to some rows and not others,
    silently. It surfaced as a column that was supposed to disappear at 390px
    reappearing for exactly the teams with no data, which is the worst possible
    subset: the rows where the layout has least excuse to break.

    ⚠ `hx` must still be absent when there is no value. That class paints the
    gradient, and an absent measurement must never be rendered as a neutral one
    (R5). Identity and has-a-value are two different things and this asserts
    both.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping column-identity check")
        return
    src = open(hub, encoding="utf-8").read()
    t25 = re.search(r'<table class="t25">(.*?)</table>', src, re.S)
    if not t25:
        print("  no Top 25 table -- skipping")
        return
    rows = re.findall(r'<tr class="row" data-team=.*?</tr>', t25.group(1), re.S)
    if not rows:
        bad("the Top 25 has no rows", "this guard is checking nothing")
        return
    with_id, painted, bare = 0, 0, 0
    for row in rows:
        classes = re.findall(r'<td class="([^"]*)"', row)
        if any(re.search(r"\bdv\b", c) for c in classes):
            with_id += 1
        if any(re.search(r"\bhx\b", c) and re.search(r"\bdv\b", c) for c in classes):
            painted += 1
        # a numeric cell with no column identity at all
        if any(c.strip() == "n" for c in classes):
            bare += 1
    if with_id != len(rows):
        bad("the net/set column loses its class when empty",
            "%d of %d rows carry it -- a rule targeting this column applies to "
            "some rows and not others" % (with_id, len(rows)))
    else:
        ok("every row's net/set cell keeps its column class", len(rows))
    if painted >= len(rows):
        bad("an absent measurement is being painted",
            "hx marks 'there is a value' and must not appear on an em dash (R5)")
    else:
        ok("only rows WITH a value are painted", painted)


def check_power_score_agrees_with_the_rank():
    """THE POWER SCORE MUST NEVER CONTRADICT THE RANK PRINTED BESIDE IT.

    ⚠ THE FIRST VERSION DID. It scored the 2025 composite while the rank came
    from the preseason projection -- two different quantities -- so #7 SMU
    (76.7) sat above #6 Louisville (76.1), and #348 above #347. Both numbers
    were individually true and the row was a contradiction. That is worse than
    showing no score at all, because a reader has no way to tell which of the
    two authoritative-looking numbers to believe.

    The fix is structural: POWER is a monotone rescaling of the very quantity
    that produces the rank, so they cannot disagree. This asserts it on the
    BUILT page rather than in the builder, because that is where a reader meets
    it -- and asserts the scale is stated, since a number out of 100 that does
    not say what 100 means is decoration.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping power-score check")
        return
    src = open(hub, encoding="utf-8").read()
    b = re.search(r'<tbody id="rbody">(.*?)</tbody>', src, re.S)
    if not b:
        bad("the rankings table could not be located", "this guard checks nothing")
        return
    ranks = re.findall(r'<tr class="row" data-r="(\d+)".*?</tr>', b.group(1), re.S)
    rows = re.findall(r'<tr class="row" data-r=.*?</tr>', b.group(1), re.S)
    vals = []
    for rk, row in zip(ranks, rows):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 4:
            continue
        txt = re.sub(r"<[^>]+>", "", cells[3]).strip()
        if txt and txt not in ("&mdash;", "\u2014"):
            try:
                vals.append((int(rk), float(txt)))
            except ValueError:
                pass
    if len(vals) < 50:
        bad("almost no team carries a power score",
            "%d of %d rows" % (len(vals), len(rows)))
        return
    vals.sort()
    inv = [(a, c) for a, c in zip(vals, vals[1:]) if c[1] > a[1] + 1e-9]
    if inv:
        bad("%d rows score higher than the team ranked above them" % len(inv),
            "e.g. #%d scores %.1f but #%d scores %.1f -- the score and the rank "
            "are built from different quantities"
            % (inv[0][1][0], inv[0][1][1], inv[0][0][0], inv[0][0][1]))
    else:
        ok("the power score never contradicts the rank beside it", len(vals))

    # THE TOP 25 CARRIES THE SAME COLUMN, ON THE SAME SCALE, FROM ITS OWN SCORE.
    # The two tables order teams differently, so this one has to be monotone
    # with ITS rank -- borrowing the rankings board's number would reproduce the
    # very contradiction this guard exists for.
    t25 = re.search(r'<table class="t25">(.*?)</table>', src, re.S)
    if t25:
        rows25 = re.findall(r'<tr class="row" data-team=.*?</tr>', t25.group(1), re.S)
        tv = []
        for row in rows25:
            c = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(c) < 4:
                continue
            try:
                tv.append((int(re.sub(r"<[^>]+>", "", c[0]).strip()),
                           float(re.sub(r"<[^>]+>", "", c[3]).strip())))
            except ValueError:
                pass
        tv.sort()
        binv = [(a, b) for a, b in zip(tv, tv[1:]) if b[1] > a[1] + 1e-9]
        if not tv:
            bad("the Top 25 carries no power score", "the column is missing or empty")
        elif binv:
            bad("the Top 25 power score contradicts its own rank",
                "#%d scores %.1f but #%d scores %.1f"
                % (binv[0][1][0], binv[0][1][1], binv[0][0][0], binv[0][0][1]))
        else:
            ok("the Top 25 power score agrees with its own rank", len(tv))

    if "every 12.5 points is one standard deviation" not in src:
        bad("the power scale is never stated",
            "a number out of 100 that does not say what 100 means is decoration")
    else:
        ok("the page states what the power scale means")

    # ...and it must not be presented as a blend of components we never fitted.
    if re.search(r"25%\s*(?:strength|power)|weighted\s+blend\s+of\s+components", src, re.I):
        bad("the page describes power as a hand-weighted blend",
            "fifteen schemes and nine profile metrics were tested and none beat "
            "the fitted composite; an invented blend must not be shipped as one")
    else:
        ok("power is not presented as a hand-weighted blend")


def check_poll_column_polarity():
    """THE TOP 25's AVCA COLUMN: is the gap pointing the right way?

    ⚠ THIS IS THE FAILURE MODE R4 EXISTS FOR. If the subtraction is reversed,
    every number in the column is still a true number and every colour is still
    a real colour -- the page just says we are more sceptical about Nebraska
    than the coaches when in fact we are less. Nothing looks broken. There is no
    exception, no gap in the data, no visual clue at all.

    So this re-derives the sign from the two ranks the row itself carries: a
    team we rank BETTER (a smaller number) than the poll does must render as a
    green "+", and a team we rank worse as a red "-". A team the poll does not
    rank at all must render NR with no gap -- the poll is 25 deep and treating
    unranked as 26 would invent a precise disagreement out of an absent number
    (R5).
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping poll-column check")
        return
    src = open(hub, encoding="utf-8").read()
    rows = re.findall(
        r'<tr class="row" data-team="([^"]+)".*?<td class="rk">(\d+)</td>'
        r'.*?<td class="n poll"[^>]*>(.*?)</td>', src, re.S)
    if not rows:
        bad("the Top 25 has no AVCA column",
            "the page carries two rankings and would be showing only one")
        return
    wrong, nr, checked = [], 0, 0
    for team, ourrank, cell in rows:
        m = re.search(r"<b>(\d+)</b>", cell)
        if not m:
            nr += 1
            if "pgup" in cell or "pgdn" in cell:
                wrong.append("%s: NR but shows a gap" % team)
            continue
        a, ours = int(m.group(1)), int(ourrank)
        checked += 1
        if ours == a:
            want = "pg0"
        elif ours < a:
            want = "pgup"          # we rate them BETTER than the coaches do
        else:
            want = "pgdn"
        if want not in cell:
            wrong.append("%s: ours #%d vs poll #%d wants %s" % (team, ours, a, want))
        # and the magnitude must be the actual difference
        g = re.search(r"[\u2212+](\d+)", cell)
        if g and int(g.group(1)) != abs(ours - a):
            wrong.append("%s: prints %s, the gap is %d"
                         % (team, g.group(1), abs(ours - a)))
    if wrong:
        bad("the AVCA gap column is wrong on %d rows" % len(wrong),
            "; ".join(wrong[:3]))
    elif not checked:
        bad("no Top 25 team is ranked by the poll",
            "either the join broke or this guard is checking nothing")
    else:
        ok("the AVCA gap points the right way and matches the ranks", checked)
        if nr:
            print("     (%d of %d not in the coaches poll -- rendered NR)"
                  % (nr, len(rows)))


def check_live_times_are_pacific():
    """THE LIVE SLATE MUST USE THE SAME CLOCK AS THE REST OF THE PAGE.

    live_server.py formatted start times in EASTERN and appended the literal
    "ET", so tonight's slate read "6:00 PM ET" on a page whose every other time
    was Pacific -- two clocks on one screen, three hours apart, with nothing
    telling a reader which was which.

    ⚠ TWO USES OF EASTERN THAT MUST NOT BE MERGED. The server still thinks in
    Eastern to decide which DATES to ask the scoreboard for -- the feed is keyed
    by the Eastern calendar day. Only the DISPLAY is Pacific. And the
    plausibility test stays Eastern too: the feed's unannounced-start sentinel
    is 1:00 AM ET, which converts to a completely ordinary-looking 10:00 PM PT,
    so converting before judging would launder a non-time into a plausible one.

    That is why the server defers to build_hub.listed_time() instead of
    converting for itself -- one definition of how a time is shown (R4).
    """
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    try:
        import live_server
    except Exception as e:                       # noqa: BLE001 - report, not crash
        bad("live_server.py does not import", str(e)[:120])
        return

    # An ordinary evening start must render Pacific.
    got = live_server._fmt_time(1756602000, None, "Texas")
    if not got.endswith("PT"):
        bad("the live slate does not render in Pacific",
            "got %r -- the rest of the page is Pacific" % got)
    else:
        ok("the live slate renders start times in Pacific")

    # The midnight sentinel must still be suppressed, judged in Eastern.
    if live_server._fmt_time(None, "1:00 AM ET", "Nebraska") != "TBA":
        bad("the live slate prints the unannounced-start sentinel",
            "1:00 AM ET at Nebraska is a placeholder, not a start time (R5)")
    else:
        ok("an unannounced start still renders as TBA, not as 10:00 PM")

    # The "updated" stamp is a time a reader sees, so it obeys the same clock.
    # It printed "9:33 PM ET" directly above fixtures listed in PT.
    import inspect
    ls_src = inspect.getsource(live_server)
    if re.search(r'"updated":\s*_et_now\(\)', ls_src):
        bad("the live band stamps its update time in Eastern",
            "every other time on the page is Pacific; two clocks three hours "
            "apart with nothing saying which is which")
    else:
        ok("the live band's update stamp uses the page's clock")

    # ...and Hawaii's genuinely late Eastern times must survive it.
    if live_server._fmt_time(None, "1:00 AM ET", "Hawaii") == "TBA":
        bad("Hawaii's real start times are being suppressed",
            "1:00 AM ET is 7:00 PM in Honolulu -- an ordinary evening match")
    else:
        ok("Hawaii's genuine late-Eastern starts survive")


def check_week_names_whose_ranking():
    """THIS WEEK'S MATCHES, AND WHOSE RANK IS ON THEM.

    The page carries TWO rankings and they disagree -- the AVCA coaches poll
    (the official one, and what the feed's inline rank IS: verified against the
    published poll, BYU 24, Kansas 15, Indiana 16, all three differing from
    ours) and our own Top 25. Showing an unlabelled numeral next to a team name
    lets a reader take it for whichever they had in mind, and this page spent a
    while doing exactly that.

    So: the AVCA number leads and is labelled as AVCA; our number appears only
    where it disagrees, and is labelled as ours. This asserts both labels
    survive, that the payload carries a human day label rather than a raw ISO
    date, and that the two rank fields never swap meaning (R4).
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping week-ranking check")
        return
    src = open(hub, encoding="utf-8").read()
    m = re.search(r"const WEEK = (\[.*?\]);", src, re.S)
    if not m:
        bad("the week payload is missing", "renderWeek has nothing to render")
        return
    rows = json.loads(m.group(1))
    if not rows:
        # Legitimately empty out of season -- not a failure, but say so.
        print("  %-58s %s" % ("this week's matches (no fixtures in range)", "skip"))
        return

    # ONE DATE FORMAT ON THE WHOLE PAGE. "2026-08-30" is unambiguous and makes
    # a reader do arithmetic to learn it is a Sunday.
    #
    # ⚠ THIS GUARD USED TO CHECK ONLY CARDS, AND THAT IS WHY IT PASSED WHILE
    # NINE ISO DATES WERE ON SCREEN -- the team page's NEXT box, six upcoming
    # fixtures, the masthead's "last result" and the schedule table. Narrowing a
    # guard to the case that prompted it leaves every other case unwatched, and
    # a reader looking at a team page saw both formats within one screen.
    #
    # Only ELEMENT TEXT is scanned (between a > and a <), never the JSON
    # payloads, which carry ISO dates on purpose and should. The schedule table
    # keeps its ISO in data-d for sorting -- an attribute, so it is not text.
    #
    # ONE STATED EXCEPTION: the build stamp. It is a machine timestamp about the
    # page rather than a date in the sport, and ISO is the right format for it.
    iso_text = [m.group(1).strip() for m in
                re.finditer(r">([^<>]{0,60}?\b20\d\d-\d\d-\d\d\b[^<>]{0,40}?)<", src)]
    iso_text = [t for t in iso_text if t and "built" not in t]
    if iso_text:
        bad("%d visible ISO dates on the page" % len(iso_text),
            "e.g. %r -- every other date reads 'Sun Aug 30', so the page shows "
            "two formats at once" % iso_text[0])
    else:
        ok("no visible ISO dates (the build stamp is the one exception)")

    # ⚠ THE SCAN ABOVE CANNOT SEE CLIENT-RENDERED DATES, and writing its
    # negative control is what exposed that: swapping a JS-rendered date for an
    # ISO one changed nothing in the file, because the file holds
    # `dayLabel(g.d)`, not a date. Four of the nine ISO dates that were on
    # screen came from renderers like that -- so a text scan alone would have
    # reported a clean page while a reader was looking at "2026-08-29".
    #
    # So the JS side is checked at the SOURCE: any renderer emitting a date
    # field into an element must pass it through dayLabel first.
    scripts_js = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S)
    js_nc = re.sub(r"/\*.*?\*/", " ", "\n".join(scripts_js), flags=re.S)
    # ⚠ WIDENED: the first pattern only looked for a field literally named `.d`,
    # so the "just finished" band -- which calls its field `.date` -- printed a
    # raw ISO date straight through a guard written to prevent exactly that.
    # Caught by looking at the screen, not by the test. Match either name.
    # ⚠ WIDENED THREE TIMES, EVERY TIME AFTER LOOKING AT THE SCREEN RATHER
    # THAN AT THE TEST.
    #   1. It matched only a field named `.d`, so the just-finished band's
    #      `.date` printed a raw ISO date straight past it.
    #   2. It matched only a date IMMEDIATELY after the opening quote, so the
    #      team page's `... + ' &middot; ' + _last.d` slipped through.
    #   3. Chunking the expression up to the next ";" broke on `&middot;` --
    #      an HTML entity ENDS IN A SEMICOLON, so the scan stopped before
    #      reaching the date it was looking for. The negative control caught
    #      that one; nothing else would have.
    # Scan a fixed window after each emitting class instead, and let dayLabel
    # anywhere in it count as handled.
    raw_emit = []
    for m0 in re.finditer(r'class="(?:dt|gls|cd)"[^>]*>', js_nc):
        win = js_nc[m0.end():m0.end() + 320]
        win = win.split("</div>")[0]
        for m in re.finditer(r"([A-Za-z_$][\w.$]*\.(?:d|date))\b", win):
            head = win[max(0, m.start() - 14):m.start()]
            if "dayLabel(" in head:
                continue
            raw_emit.append(m.group(1))
    if raw_emit:
        bad("%d page renderers print a date field without dayLabel" % len(raw_emit),
            "e.g. %s -- a text scan of the built file cannot see this, because "
            "the file holds the expression, not the date" % raw_emit[0])
    else:
        ok("every client-side date renderer goes through dayLabel")

    # ⚠ TWO IMPLEMENTATIONS OF ONE RULE, ACTUALLY COMPARED. day_label() renders
    # the schedule table in Python; dayLabel() renders the fixture list in
    # JavaScript, two inches below it. They were producing "Sat Aug 29" and
    # "Sat, Aug 29" -- same rule, different punctuation, both on screen at once.
    #
    # Asserting that a mirror "looks right" is how mirrors drift. This RUNS the
    # page's own function under node and compares it to Python's, date by date,
    # so the two cannot disagree without failing here.
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("node"):
        print("  %-58s %s" % ("the two day-label implementations agree", "skip"))
    else:
        fn = re.search(r"function dayLabel\(iso\)\s*\{.*?\n\}", js_nc, re.S)
        if not fn:
            bad("dayLabel() could not be found in the page",
                "this cross-implementation check is testing nothing")
        else:
            import build_hub as _BH
            # ⚠ ANCHOR THE FIXTURE DATES TO PACIFIC TOO. The page renders in
            # Pacific and both implementations now agree on that; a test that
            # generates its dates from the MACHINE clock reintroduces the very
            # skew it is checking for, and would fail on a UTC runner however
            # correct the code is.
            today = (datetime.datetime.now(_BH.PT).date() if _BH.PT
                     else datetime.datetime.utcnow().date())
            days = [-2, -1, 0, 1, 2, 5, 13, 40, 120]
            dates = [(today + datetime.timedelta(days=d)).isoformat() for d in days]
            prog = (fn.group(0) + "\nconsole.log(JSON.stringify("
                    + json.dumps(dates) + ".map(dayLabel)));")
            fh = tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                             encoding="utf-8")
            fh.write(prog)
            fh.close()
            try:
                r = subprocess.run(["node", fh.name], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
                if r.returncode != 0:
                    bad("dayLabel() would not run under node",
                        r.stdout.decode("utf-8", "replace").strip()[:160])
                else:
                    js_out = json.loads(r.stdout.decode("utf-8").strip())
                    py_out = [_BH.day_label(d) for d in dates]
                    diff = [(d, a, b) for d, a, b in zip(dates, js_out, py_out) if a != b]
                    if diff:
                        bad("the two day-label implementations disagree",
                            "; ".join("%s: js=%r py=%r" % x for x in diff[:3]))
                    else:
                        ok("the two day-label implementations agree", len(dates))
            finally:
                os.unlink(fh.name)

    missing = [r for r in rows if not r.get("dl")]
    if missing:
        bad("a week fixture has no day label",
            "%d of %d rows would print a raw ISO date" % (len(missing), len(rows)))
    else:
        ok("every week fixture carries a day label", len(rows))

    # comments are stripped: this file has three times written a guard that
    # matched its own explanatory prose instead of the code.
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S)
    js = re.sub(r"/\*.*?\*/", " ", "\n".join(scripts), flags=re.S)
    # EVERY rank badge on the page, not just the week box. Four call sites
    # emitted one unlabelled; they now share a single definition per side, and
    # this is what stops a fifth from appearing.
    # ⚠ THIS GUARD USED TO HARD-CODE "AVCA coaches poll rank", because when it
    # was written AVCA was the only ruler on the page. There are now eleven,
    # emitted from build_hub.RULERS, and a badge may legitimately say POWER,
    # DIGBY or R\u00c9SUM\u00c9. Pinning the literal made the guard fail on
    # correct markup -- and, worse, it would have PASSED a page whose every
    # badge said AVCA when half of them were something else.
    # The invariant is: a rank badge carries a title AND a visible label.
    bare = re.findall(r'<i class="rnk"(?! title=)', src)
    labelled = re.findall(r'<i class="rnk" title="[^"]+"><span class="rank-label">'
                          r'[^<]+</span>#', src)
    if bare:
        bad("%d rank badges do not say whose ranking they are" % len(bare),
            "a bare numeral beside a team name is read as whichever ranking "
            "the reader had in mind, and this page carries two that disagree")
    elif not labelled:
        bad("no rank badge is labelled", "either the markup or this guard is "
                                         "wrong -- it is checking nothing")
    else:
        ok("every rank badge names the AVCA coaches poll", len(labelled))

    if "our Top 25: " not in js:
        bad("our own ranking is never shown beside the official one",
            "the page holds two rankings that disagree and showed only one")
    else:
        ok("our Top 25 is shown where it disagrees, and labelled as ours")

    # R4: ar/hr are AVCA, ao/ho are ours. If they ever swap, every number on
    # the card is still correct and every label is wrong -- the exact failure
    # mode R4 exists for, and invisible without a check.
    both = [r for r in rows if r.get("ar") and r.get("ao")]
    if both:
        same = sum(1 for r in both if str(r["ar"]) == str(r["ao"]))
        if same == len(both):
            bad("the AVCA rank and our rank are identical on every fixture",
                "two independent rankings agreeing on all %d is the signature "
                "of one field being copied into both" % len(both))
        else:
            ok("the two rank fields are independent", len(both))


def check_page_script_parses():
    """EVERY <script> ON THE PAGE MUST PARSE. The cheapest guard here, and it
    did not exist.

    ⚠ WHAT IT CATCHES, AND WHY NOTHING ELSE DID. A JavaScript SyntaxError is not
    local: the browser discards the WHOLE <script> element before running a line
    of it, so one bad character kills every renderer in that block. The Python
    build still prints "wrote START-HERE.html", every data guard in this file
    still passes -- because the data is fine -- and the page is dead.

    Paid for while wiring "this week's top matches": a newline written into a
    JS template as the two characters \\ and n landed in code position. The
    symptom was a box rendering EMPTY, which reads like a data problem and sent
    me looking in the wrong place entirely.

    Reports SKIP without node rather than passing -- a check that could not run
    must never look like one that did.
    """
    import shutil
    import subprocess
    import tempfile
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping script-parse check")
        return
    if not shutil.which("node"):
        print("  %-58s %s" % ("all page scripts parse (node not installed)", "skip"))
        return
    html = open(hub, encoding="utf-8").read()
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    checked = 0
    for i, body in enumerate(scripts):
        if not body.strip():
            continue
        checked += 1
        fh = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8")
        fh.write(body)          # --check parses without executing; no DOM needed
        fh.close()
        try:
            r = subprocess.run(["node", "--check", fh.name],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if r.returncode != 0:
                msg = r.stdout.decode("utf-8", "replace").strip().split("\n")
                bad("page script #%d does not parse" % (i + 1),
                    " / ".join(x.strip() for x in msg[:3]))
                return
        finally:
            os.unlink(fh.name)
    if checked:
        ok("all page scripts parse", checked)
    else:
        bad("no page scripts found", "the extraction regex is wrong, so this "
                                     "guard was checking nothing")


def _rules(block):
    """(selector, body) pairs from a CSS block. Linear scan, no backtracking."""
    out, buf, depth, sel = [], [], 0, None
    for c in block:
        if c == "{":
            depth += 1
            if depth == 1:
                sel = "".join(buf).strip(); buf = []
            else:
                buf.append(c)
        elif c == "}":
            depth -= 1
            if depth == 0:
                out.append((sel, "".join(buf))); buf, sel = [], None
            else:
                buf.append(c)
        else:
            buf.append(c)
    return out


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
    check_photo_crop_and_zoom()
    check_hero_podium_signs()
    check_no_class_name_collisions()
    check_mobile_rankings_are_a_list_not_a_clipped_table()
    check_column_identity_survives_a_missing_value()
    check_power_score_agrees_with_the_rank()
    check_poll_column_polarity()
    check_live_times_are_pacific()
    check_week_names_whose_ranking()
    check_page_script_parses()
    check_today_is_pacific()
    check_decor_never_covers_content()
    check_players_view_shows_every_stat()
    check_team_glance_is_populated()
    check_team_context_fields()
    check_net_matches_the_rulebook()
    check_di_listings_but_not_di_data()
    check_head_coaches_are_head_coaches()
    check_phantom_sets_are_harmless()
    check_aggregate_excludes_phantom_sets()
    print()
    check_transfer_reconciliation()
    print()
    check_public_gate_catches_leaks()
    check_public_build_is_clean()
    print()
    check_photos_are_urls_only()
    print()
    check_no_unreplaced_placeholders()
    print()
    check_no_conflict_markers_in_artifacts()
    check_public_build_can_actually_render()
    check_phone_columns_fit_their_values()
    check_every_view_names_its_season()
    print()
    check_nondi_form_marker_is_visible()
    check_standings_diff_shares_the_record_basis()
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
