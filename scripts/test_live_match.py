#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for Live Match Center (Phase 1).

The feature shows numbers taken from a match that is still being played, so the
ways it can go wrong are all versions of the same thing: showing something that
is not true yet. These guards are therefore mostly NEGATIVE -- they assert what
must be refused.

⚠ AND THE POSITIVE CONTROLS MATTER JUST AS MUCH. "Refuse everything" would pass
every negative check here and ship a feature that never displays anything, so a
real, coherent box score (today's actual finals) must still validate.

Python 3.9 target. Run: python3 scripts/test_live_match.py
"""

import copy
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_detail as LD                                          # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  %-66s %s" % (label, "ok" if ok else "FAIL %s" % detail))
    if not ok:
        FAILS.append(label)


def box(kills=(30, 40), attacks=(90, 95), errors=(10, 12), digs=(25, 30),
        aces=(3, 5), sets_played=3, players=True):
    """A synthetic but structurally faithful box score."""
    tb = []
    for i in (0, 1):
        st = {"kills": str(kills[i]), "attackErrors": str(errors[i]),
              "attackAttempts": str(attacks[i]), "assists": str(max(0, kills[i] - 2)),
              "digs": str(digs[i]), "serviceAces": str(aces[i]),
              "serviceErrors": "4", "blockSolos": "2", "blockAssists": "6",
              "sets": str(sets_played)}
        ps = []
        if players:
            ps = [{"firstName": "A%d" % i, "lastName": "Player",
                   "kills": str(kills[i] // 2), "serviceAces": "1",
                   "blockSolos": "1", "blockAssists": "2", "digs": "5"}]
        tb.append({"teamId": str(100 + i), "teamStats": st, "playerStats": ps})
    return {"teamBoxscore": tb,
            "teams": [{"teamId": "100", "nameShort": "Alpha"},
                      {"teamId": "101", "nameShort": "Beta"}]}


def main():
    print("LIVE MATCH CENTER GUARDS\n")

    print("1. A coherent official box score validates (positive control)")
    t, lead, why = LD.validate(box())
    check("[+] a well-formed box score is accepted", t is not None, why)
    if t:
        check("[+] both teams come back", len(t) == 2)
        check("[+] hitting % is (K-E)/TA from summed counts",
              abs(t[0]["hitpct"] - round((30 - 10) / 90.0, 3)) < 1e-9,
              str(t[0]["hitpct"]))
        # ⚠ RAW COUNTS, NEVER THE FEED'S `points` COLUMN.
        check("[+] points = kills + aces + solo + half assists",
              t[0]["points"] == 30 + 3 + 2 + 3.0, str(t[0]["points"]))
        check("[+] blocks = solo + half assists", t[0]["blocks"] == 5.0)
        check("[+] player leaders are derived", len(lead) > 0)

    print("\n   ...and so do the two REAL box scores from 2026-08-24")
    real = 0
    for gid in ("6639891", "6639887"):
        p = os.path.join(REPO, "data", "raw", "2026", "boxscore_%s.json" % gid)
        if not os.path.exists(p):
            continue
        tt, _l, w = LD.validate(json.load(open(p, encoding="utf-8")))
        check("[+] real box %s validates" % gid, tt is not None, w)
        real += 1
    if not real:
        print("     (no sample box scores on disk -- synthetic controls only)")

    print("\n2. Nonsense is refused, never rendered")
    cases = [
        ("no payload at all", None),
        ("a string instead of a payload", "nope"),
        ("only one team", {"teamBoxscore": [box()["teamBoxscore"][0]]}),
        ("three teams", {"teamBoxscore": box()["teamBoxscore"] + [{}]}),
        ("no teamBoxscore key", {"teams": []}),
        ("a malformed team entry", {"teamBoxscore": ["x", "y"]}),
    ]
    for label, payload in cases:
        t, _l, why = LD.validate(payload)
        check("[-] %s is refused" % label, t is None, "got %r" % (t,))
        check("    ...with a stated reason", bool(why))

    print("\n3. Partial and impossible counts are refused")
    b = box(); b["teamBoxscore"][0]["teamStats"]["kills"] = ""
    check("[-] a blank count is not a zero", LD.validate(b)[0] is None)
    b = box(); b["teamBoxscore"][0]["teamStats"]["digs"] = "-"
    check("[-] a dash is not a zero", LD.validate(b)[0] is None)
    b = box(); del b["teamBoxscore"][1]["teamStats"]["digs"]
    check("[-] a missing field is not a zero", LD.validate(b)[0] is None)
    b = box(); b["teamBoxscore"][0]["teamStats"]["kills"] = "-5"
    check("[-] a negative count is refused", LD.validate(b)[0] is None)
    b = box(kills=(95, 40), attacks=(90, 95))
    check("[-] more kills than attempts is refused", LD.validate(b)[0] is None)
    b = box(); b["teamBoxscore"][0]["teamStats"]["attackErrors"] = "500"
    check("[-] more errors than attempts is refused", LD.validate(b)[0] is None)
    b = box(kills=(0, 0), attacks=(0, 0), errors=(0, 0), digs=(0, 0), aces=(0, 0))
    t, _l, why = LD.validate(b)
    check("[-] an ALL-ZERO box is refused, not shown as 0-0", t is None, why)
    check("    ...and says the box is still empty", "empty" in why, why)
    b = box(sets_played=9)
    check("[-] an implausible set count is refused", LD.validate(b)[0] is None)
    b = box(sets_played=1)
    check("[-] a box behind the scoreboard is refused",
          LD.validate(b, expect_sets=4)[0] is None)
    check("[+] ...but a box level with it is fine",
          LD.validate(box(sets_played=3), expect_sets=3)[0] is not None)

    print("\n4. Number parsing does not invent zeros")
    for bad in (None, "", "  ", "-", "--", "N/A", "abc", "1.5", {}, [], True):
        check("[-] _int(%r) is None, not 0" % (bad,), LD._int(bad) is None)
    for good, want in (("12", 12), (12, 12), ("0", 0), (7.0, 7), ("  9 ", 9)):
        check("[+] _int(%r) == %d" % (good, want), LD._int(good) == want)

    print("\n5. The cache: one match, few entries, fail soft")
    clock = [1000.0]
    calls = []

    def fake(gid):
        calls.append(gid)
        return {"gid": gid, "n": len(calls)}

    c = LD.DetailCache(fake, ttl=20.0, cap=3, clock=lambda: clock[0])
    c.get("A"); c.get("A"); c.get("A")
    check("[+] repeat reads inside the TTL cost ONE upstream call",
          len(calls) == 1, str(calls))
    clock[0] += 21
    c.get("A")
    check("[+] after the TTL it refetches", len(calls) == 2, str(calls))
    check("[-] it never fetches a match nobody opened",
          set(calls) == {"A"}, str(calls))
    for k in ("B", "C", "D", "E"):
        clock[0] += 1
        c.get(k)
    check("[+] the entry cap holds", len(c._entries) <= 3, str(len(c._entries)))

    # fail soft: upstream dies, last good survives and is MARKED stale
    clock[0] += 1
    good = LD.DetailCache(fake, ttl=10.0, clock=lambda: clock[0])
    good.get("Z")
    boom = {"n": 0}

    def dead(gid):
        boom["n"] += 1
        raise IOError("upstream down")

    good._fetch = dead
    clock[0] += 11
    payload, age, stale, err = good.get("Z")
    check("[+] a failed refresh keeps the last coherent response",
          payload is not None, str(payload))
    check("[+] ...and marks it stale", stale is True)
    check("[+] ...and says why", bool(err), repr(err))
    check("[+] ...and reports its age", age >= 11, str(age))
    clock[0] += LD.STALE_MAX + 5
    payload, _a, _s, err = good.get("Z")
    check("[-] but it gives up once too old to mean anything",
          payload is None, str(payload))

    def none_fetch(gid):
        return None

    c2 = LD.DetailCache(none_fetch, clock=lambda: clock[0])
    payload, _a, _s, err = c2.get("Q")
    check("[-] an empty upstream response yields nothing, not {}",
          payload is None, str(payload))
    check("    ...with a reason", bool(err))

    print("\n6. The endpoint's own rules")
    src = open(os.path.join(REPO, "scripts", "live_server.py"),
               encoding="utf-8").read()
    check("/api/match exists and is separate from /api/live",
          '"/api/match"' in src and '"/api/live"' in src)
    check("it is local-only, like the other write/spend endpoints",
          '/api/match' in src and '_is_local()' in src)
    check("the server still binds to 127.0.0.1",
          '127.0.0.1' in src and 'HOST' not in src.split('PORT')[0][-200:])
    check("a non-numeric id is rejected before any upstream call",
          "gid.isdigit()" in src)
    # ⚠ SAME RULE, REWORDED WHEN THE STATE MODEL LANDED. The live endpoint
    # still refuses to fetch a final's box score; that reaches the page through
    # the verified crawl. Assert the BEHAVIOUR (the early return on an over
    # match) rather than one phrasing of the sentence beside it.
    check("a FINAL hands off to the verified pipeline rather than scraping",
          "if MS.is_over(row):" in src
          and "reaches the" in src and "verified crawl" in src)
    check("an unknown id is not looked up (no fishing)",
          "not on the current scoreboard" in src)
    # ⚠ THE PROPERTY THAT MATTERS MOST, AND IT IS STRUCTURAL: this module has
    # no writer. Nothing it produces can reach the dataset.
    # ⚠ SCAN THE CODE, NOT THE PROSE. The first version matched this module's
    # own docstring -- which says it never writes to data/raw -- and reported
    # the promise as the violation.
    import ast
    ld_src = open(os.path.join(REPO, "scripts", "live_detail.py"),
                  encoding="utf-8").read()
    tree = ast.parse(ld_src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) \
                and ast.get_docstring(node):
            node.body = node.body[1:]
    ld = "\n".join(l.split("#")[0] for l in ast.dump(tree).splitlines())
    for bad in ("open", "json.dump", "data/raw", "commit", "write"):
        check("[-] live_detail.py never calls %s" % bad,
              bad not in ld, "found %r" % bad)

    print("\n6b. LIVE STATS BELONG TO THE OPENED ROUTE")
    # the client code lives in the built page; `src` above is live_server.py
    _hp = os.path.join(REPO, "Cody", "START-HERE.html")
    if not os.path.exists(_hp):
        _hp = os.path.join(REPO, "output", "vb_dashboard.html")
    h = open(_hp, encoding="utf-8").read() if os.path.exists(_hp) else ""
    check("a built page is available for the route checks", bool(h))
    # ⚠ PHASE 1 POLLED EVERY CARD THAT HAD BEEN EXPANDED. Leaving one open and
    # navigating away kept it fetching. The timer now knows the single game id
    # it exists for and stops on a route change, a switch, or final.
    check("live stats live in the routed detail", "function lmcSection" in h)
    check("...and are rendered only for a live match",
          "(st === 'live' ? lmcSection(m.gid) : '')" in h)
    check("exactly one match polls", "LMC_ROUTE_GID" in h)
    check("the timer starts only on a live route",
          "if (st === 'live') { lmcStart(m.gid); } else { lmcStop(); }" in h)
    check("...and stops when the detail closes",
          "function closeMatchDetail() {\n  lmcStop();" in h)
    check("...and stops itself the moment the feed says final",
          "if (d && d.state === 'final') { lmcStop();" in h)
    check("...and stops if the route moved to another match",
          "if (LMC_ROUTE_GID !== gid) { lmcStop(); return; }" in h)
    check("a manual refresh exists", "id=\"lmcrefresh\"" in h
          or "id='lmcrefresh'" in h)
    check("...and refreshes the open match only",
          "if (LMC_ROUTE_GID) lmcFetch(LMC_ROUTE_GID);" in h)
    check("the cadence is no faster than phase 1",
          "const LMC_EVERY_MS = 20000;" in h)
    # ⚠ THE VALIDATION IS NOT DUPLICATED. Rendering a validated field is not
    # re-validating it -- my first version banned "attackAttempts" from the
    # renderer, which would have meant the panel could not DISPLAY the number
    # the server had already cleared. What matters is that the client makes no
    # judgement of its own: it branches on the server's verdict and applies no
    # threshold, no comparison and no fallback number.
    body_fn = h.split("function lmcBody")[1].split("\nfunction ")[0]
    check("the client defers to the server's verdict",
          "d.stats_available" in body_fn)
    # ⚠ AND "NO COMPARISON AT ALL" WAS TOO BLUNT: the renderer says
    # `p.aces > 1 ? 's' : ''` to pluralise a word, which is English, not a
    # threshold. What must be absent is the client DERIVING a stat or deciding
    # availability -- both of which live in live_detail.validate().
    derived = re.search(r"\(\s*\w+\.k(?:ills)?\s*-\s*\w+\.(?:e|attackErrors)",
                        body_fn)
    check("[-] ...and derives no statistic of its own", derived is None,
          "hitting % or similar computed client-side")
    check("[-] ...and never sets the availability verdict",
          "stats_available =" not in body_fn and "stats_available=" not in body_fn)
    check("[-] ...and substitutes no value when one is missing",
          "|| 0" not in body_fn and "|| '0'" not in body_fn)
    check("the freshness line names the last successful refresh",
          "id=\"lmcstamp\"" in h and "stale, retrying" in h)
    check("a final says refreshing has stopped",
          "final \\u2014 refreshing has stopped" in h)
    # ⚠ AND A DENIAL IS NOT A BREACH. The source says the panel carries no
    # momentum or consensus; a bare substring search cannot tell that promise
    # from a violation, so each hit must sit in a negating sentence.
    NEGW = ("nothing", "never", "not ", "no ", "cannot", "n't")
    for word in ("point-by-point", "momentum", "keys to win", "win probability"):
        bad_hits = []
        low = h.lower()
        i = low.find(word)
        while i >= 0:
            a = max(0, low.rfind(".", 0, i) + 1)
            b = low.find(".", i)
            sent = re.sub(r"\s+", " ", h[a:(b if b > 0 else len(h))]).lower()
            if not any(n in sent for n in NEGW):
                bad_hits.append(sent[:90])
            i = low.find(word, i + 1)
        check("[-] %r only ever appears in a denial" % word, not bad_hits,
              repr(bad_hits[:1]))
    check("the score ribbon stays the only score header",
          h.split("function renderMatchDetail")[1]
             .split("\nfunction ")[0].count("ribbonHTML(") == 1)
    check("live stats reach no rating or projection",
          "LIVE_BY_ID" not in h.split("function lmcBody")[1].split("\n}")[0])

    print("\n7. The page states its source and never claims more")
    for label, path in (("private", os.path.join(REPO, "Cody", "START-HERE.html")),
                        ("public", os.path.join(REPO, "output",
                                                "vb_dashboard.html"))):
        if not os.path.exists(path):
            continue
        h = open(path, encoding="utf-8").read()
        check("%s: the inset names the official feed" % label,
              "official NCAA feed" in h)
        check("%s: it says live is not used in ratings" % label,
              "Not used in ratings until final" in h)
        check("%s: a missing box score says so honestly" % label,
              "not available from the official feed" in h)
        check("%s: a static host is told it needs the local server" % label,
              "Live detail needs the local server" in h)
        check("%s: staleness is visible" % label, "stale, retrying" in h)
        # ⚠ NO THIRD RANK BESIDE AVCA AND POWER. Checked as the inset's actual
        # column list rather than by grepping for a phrase -- the first version
        # matched the source comment that DENIES a watch score.
        import re as _re
        # anchored INSIDE lmcBody: an unanchored search found the
        # standings table (Rk/Conf/Overall) and accused the inset of it.
        hdr = _re.search(
            r"function lmcBody.*?<table><thead><tr>(.*?)</tr>", h, _re.S)
        cols = _re.findall(r"<th>(.*?)</th>", hdr.group(1)) if hdr else []
        check("%s: the inset shows counted stats only" % label,
              cols == ["Team", "K", "E", "TA", "Hit%", "Digs", "Blk", "Aces"],
              str(cols))

    # ── ONE LIVE-BOX STATE PER MATCH PAGE (outside review, 2026-08-28) ──
    # Stanford-Wisconsin rendered a populated Live-stats table ABOVE a Box
    # score note reading "the source is not serving statistics for this match
    # yet". Two verdicts from two sources: the bulk scoreboard (cannot see
    # stats, so every live match resolves live_score_only) and the per-match
    # fetch (can, and did). The fix: the per-match verdict OWNS the state
    # note the moment it lands -- lmcRender rewrites #mpendnote from
    # d.state_label/d.state_note, both drawn from the same match_state.py
    # table. These guards pin the mechanism and its wiring.
    # ⚠ THE INVARIANT LIVES IN THE SOURCE, WHICH ALWAYS EXISTS. Round 1 of
    # this guard read the built private page and silently SKIPPED when it was
    # absent -- which is every CI checkout, since Cody/ is gitignored. A guard
    # that quietly stands down in exactly the environment that publishes is
    # not a guard (outside review, round 2). The generator is asserted always;
    # the built page adds a second layer only when present.
    hub2 = os.path.join(REPO, "scripts", "build_hub.py")
    if not os.path.exists(hub2):
        check("build_hub.py exists to be audited", False, hub2)
        page2 = ""
    else:
        page2 = open(hub2, encoding="utf-8").read()
    if page2:
        # ⚠ BRACE-AWARE, NOT NON-GREEDY (review round 3): `.*?\n\}` truncates
        # at the first nested function, the exact trap test_scoreboard_density
        # already paid for -- so its comment-aware matcher is the one used.
        from test_scoreboard_density import block as _js_block

        def _fn(name):
            i = page2.find("function %s(" % name)
            return _js_block(page2, i) if i >= 0 else None
        check("the pending box-score note is addressable (#mpendnote)",
              'id="mpendnote"' in page2)
        lrs = _fn("lmcRender") or ""
        check("lmcRender rewrites the note from the per-match verdict",
              "getElementById('mpendnote')" in lrs
              and "d.state_note" in lrs and "d.state_label" in lrs, 
              "lmcRender does not own the state note")
        # the note text itself must come from the shared table, not a second
        # spelling -- match_state.py is the one place the words live
        import match_state as MS2
        check("score-only wording exists only in the shared state table",
              page2.count("not serving statistics")
              <= len(re.findall(r"not serving statistics",
                                json.dumps(MS2.DETAIL_NOTE))) + 1,
              "%d occurrences in the page" % page2.count("not serving statistics"))
        # ── THE INVARIANT, RUN AS BEHAVIOUR (node executes the page's own
        # functions). Both fixture states, then the same invariant against a
        # deliberately regressed lmcRender -- the control is the invariant
        # FAILING, not a string being absent. ──────────────────────────────
        _lmcbody = _fn("lmcBody")
        _lmcrend = _fn("lmcRender")
        if not (_lmcbody and _lmcrend):
            check("lmcBody/lmcRender extracted for behavioural run", False)
        else:
            import subprocess as _sp

            def _run_invariant(render_src):
                js = """
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
const lmcNum = (v,d) => (v===null||v===undefined) ? '\u2014' : v;
%s
%s
const LMC_DATA = {};
// minimal DOM: the two elements lmcRender touches
const els = {};
const mk = id => els[id] = { id: id, innerHTML: '', textContent: '' };
mk('lmc-G'); mk('mpendnote'); mk('lmcstamp');
global.document = { getElementById: id => els[id] || null };
function state(d) {
  LMC_DATA['G'] = d;
  els['mpendnote'].innerHTML =
    '<b>Live</b><span>Live score only \u2014 the source is not serving ' +
    'statistics for this match yet.</span>';   // what the bulk feed painted
  lmcRender('G');
  return { box: els['lmc-G'].innerHTML, note: els['mpendnote'].innerHTML };
}
const av = state({ ok: true, state: 'live', stats_available: true,
  state_label: 'Live',
  state_note: 'Live score and team totals from the official feed.',
  teams: [{team:'A',kills:10},{team:'B',kills:9}] });
const so = state({ ok: true, state: 'live', stats_available: false,
  state_label: 'Live',
  state_note: 'Live score only \u2014 the source is not serving statistics for this match yet.',
  stats_reason: '' });
const bad = [];
if (!/<table/.test(av.box)) bad.push('stats-available: no table rendered');
if (/not serving statistics/.test(av.note))
  bad.push('stats-available: score-only note survived');
if (/<table/.test(so.box)) bad.push('score-only: a numeric table rendered');
if (!/not serving statistics/.test(so.note))
  bad.push('score-only: the score-only note is missing');
if (bad.length) { console.log('INVARIANT-FAILED: ' + bad.join(' | ')); process.exit(1); }
console.log('INVARIANT-HOLDS'); process.exit(0);
""" % (_lmcbody, render_src)
                r = _sp.run(["node", "-e", js], capture_output=True, text=True)
                return r.returncode == 0, (r.stdout + r.stderr).strip()

            _okrun, _why = _run_invariant(_lmcrend)
            check("BEHAVIOUR: both live-box states hold the invariant",
                  _okrun, _why[:200])
            # the regression: lmcRender that no longer rewrites the note
            _regressed = _lmcrend.replace(
                "document.getElementById('mpendnote')", "null")
            _okbad, _whybad = _run_invariant(_regressed)
            check("[NEG] the regressed lmcRender FAILS the same invariant",
                  not _okbad and "score-only note survived" in _whybad,
                  _whybad[:200])
        # ── NO FORECAST ON A LIVE MATCH, ANY SURFACE (review round 2) ──
        # The detail's "current forecast" branch also caught LIVE, so a
        # mid-match page showed a pre-match number under a Forecast heading.
        # Upcoming shows the current pick; live shows nothing; final shows
        # only the provably pre-serve log. Every fixture-pick call site goes
        # through one gate (fxPickable) or an explicit upcoming test.
        check("detail forecast is gated to the upcoming state",
              "st === 'upcoming' && m.hw !== null" in page2)
        check("fixture picks share one gate (fxPickable)",
              page2.count("fxPickable(") >= 3,   # defn + 2 call sites
              "%d occurrences" % page2.count("fxPickable("))
        check("deskWhy suppresses forecast wording on live cards",
              "function deskWhy(m, isLive)" in page2
              and "!isLive && m.hw != null" in page2)
        check("the forecast phrases the favourite, never the home side",
              "const _fcline" in page2 and "hf ? mHome(m) : mAway(m)" in page2)
        # negative control: ungating the detail branch must be caught
        _b2 = page2.replace("st === 'upcoming' && m.hw !== null",
                            "m.hw !== null")
        check("[NEG] removing the upcoming gate is caught",
              "st === 'upcoming' && m.hw !== null" not in _b2)

        # ── PROBABILITY DISPLAY RULE (review round 3): never rounded
        # certainty. 99.97% printed as "100%" reads as a guarantee. The rule
        # lives in ONE function (deskPct) and every pick call site uses it,
        # so the boundary behaviour is executed, not pattern-matched.
        _dp = _fn("deskPct")
        if not _dp:
            check("deskPct extracted", False)
        else:
            import subprocess as _sp2
            _bjs = _dp + """
const cases = [[0.0003,'<1%'],[0.005,'1%'],[0.5,'50%'],[0.994,'99%'],
               [0.9997,'99+%'],[1.0,'99+%'],[0.0,'<1%']];
const bad2 = cases.filter(c => deskPct(c[0]) !== c[1])
  .map(c => c[0]+' -> '+deskPct(c[0])+' (want '+c[1]+')');
if (bad2.length) { console.log('FAIL: '+bad2.join(' | ')); process.exit(1); }
console.log('OK'); process.exit(0);
"""
            _r2 = _sp2.run(["node", "-e", _bjs], capture_output=True, text=True)
            check("BEHAVIOUR: probability boundaries (99+%, <1%)",
                  _r2.returncode == 0, (_r2.stdout + _r2.stderr).strip()[:160])
            check("no pick site bypasses deskPct",
                  not re.search(r"Math\.round\([^)]*(?:pick|hw)[^)]*\*\s*100\)",
                                page2))

        # the dossier's live card uses the ONE live phrasing
        tds = _fn("tdNextMatch") or ""
        check("team-card live line is liveLine(), not a bespoke tally",
              "liveLine(m || f, live)" in tds)
        check("  ...and no leftover inline tally builder",
              "_sc[0] + '\\u2013' + _sc[1] + ' &middot; '" not in tds)
        # neutral floor never renders as somebody's home
        check("a neutral fixture on the team card says 'v', never 'at'",
              "f.site === 'neutral' ? 'v '" in tds)

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - %s" % f)
        return 1
    print("ALL LIVE MATCH CENTER GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
