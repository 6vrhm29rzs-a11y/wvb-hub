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
    """No fixture may display an impossible start time.

    ncaa.com fills an unannounced start with a midnight-ish sentinel that
    formats exactly like a real time (12:00-3:00 AM ET). Measured: in the
    completed 2025 season all 13 early-AM fixtures were at Hawaii, where
    1:00 AM ET is a 7:00 PM local start; in the 2026 schedule 176 of 192 were
    at schools like Nebraska and Alabama, which do not host at 1 AM. Printing
    those is R5 -- a synthesised value under a real-looking label.
    """
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(hub):
        print("  no built hub -- skipping start-time check")
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_hub import listed_time, FAR_WEST_HOME

    h = open(hub, encoding="utf-8").read()
    early = re.compile(r"^(12|[1-5]):\d\d\s*AM", re.I)

    m = re.search(r"const TEAMS = (\{.*?\});\n", h, re.S)
    n_checked = 0
    offenders = []
    if m:
        teams = json.loads(m.group(1))
        for tname, rec in teams.items():
            for f in rec.get("fixtures") or []:
                t = (f.get("t") or "").strip()
                n_checked += 1
                if not early.match(t):
                    continue
                # only legitimate when THIS team hosts and is far-western
                home_team = tname if f.get("home") else f.get("opp")
                if home_team not in FAR_WEST_HOME:
                    offenders.append((tname, f.get("d"), t))
    if offenders:
        bad("impossible start time displayed",
            "%d fixtures, e.g. %s" % (len(offenders), offenders[:3]))
    else:
        ok("no fixture shows an impossible early-AM start", n_checked)

    m2 = re.search(r"const SCHED = (\[.*?\]);\n", h, re.S)
    if m2:
        sched = json.loads(m2.group(1))
        off2 = [r for r in sched
                if early.match((r.get("t") or "")) and r.get("h") not in FAR_WEST_HOME]
        if off2:
            bad("impossible start time in schedule tab",
                "%d rows, e.g. %s" % (len(off2), off2[:2]))
        else:
            ok("schedule tab shows no impossible start", len(sched))

    # ---- NEGATIVE CONTROL: the checker must reject a known-bad value, and
    # must NOT reject a genuine Hawaii night match.
    if listed_time("1:00 AM ET", "Nebraska") != "TBA":
        bad("negative control", "sentinel at Nebraska was not suppressed")
    elif listed_time("1:00 AM ET", "Hawaii") != "1:00 AM ET":
        bad("negative control", "genuine Hawaii start time was suppressed")
    elif listed_time("7:00 PM ET", "Nebraska") != "7:00 PM ET":
        bad("negative control", "a normal evening time was altered")
    else:
        ok("negative control: sentinel suppressed, Hawaii + evening kept")


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
    print()
    check_transfer_reconciliation()
    print()
    check_public_build_is_clean()
    print()
    check_photos_are_urls_only()
    print()
    check_no_unreplaced_placeholders()
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
