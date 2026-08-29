# -*- coding: utf-8 -*-
"""Guards for the Team Dossier -- the reorganised team page.

The dossier is a POST-RENDER DOM reorganisation: `teamDossier()` takes the
sections the existing renderer already produced and files them into six tabbed
panels, then assembles an Overview that did not exist before. That design was
chosen so no rendering branch could be silently dropped -- but it means the
failure mode is a section landing in NO panel and vanishing from the page.
Nothing about that is visible: the page still renders, just without the part.

So the guards here assert the two things the reorganisation can break --
every group is reachable and nothing is orphaned -- plus the promises the
Overview makes about what it shows and how it shows it.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "scripts", "build_hub.py")
PAGE = os.path.join(ROOT, "Cody", "START-HERE.html")

FAIL = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAIL.append(name)


def main():
    src = io.open(SRC, encoding="utf-8").read()

    print("dossier structure")

    # --- 1. every group in TD_GROUPS has a mapping, and vice versa ---------
    m = re.search(r"const TD_GROUPS = (\[.*?\]);", src, re.S)
    check("TD_GROUPS is declared", m is not None)
    groups = re.findall(r"\['([a-z]+)'", m.group(1)) if m else []
    check("six groups", len(groups) == 6, groups)

    # TD_MAP is an ARRAY of [regex, group] pairs, not an object -- an earlier
    # version of this guard matched it as `{...}`, found no targets, and
    # therefore passed on an empty set. A test that cannot fail is not a test.
    m2 = re.search(r"const TD_MAP = \[(.*?)\n\];", src, re.S)
    check("TD_MAP is declared", m2 is not None)
    mapped = set(re.findall(r",\s*'([a-z]+)'\]", m2.group(1))) if m2 else set()
    check("TD_MAP targets were actually parsed", len(mapped) >= 4, sorted(mapped))
    unknown = mapped - set(groups)
    check("every TD_MAP target is a real group", not unknown, sorted(unknown))
    # every group except the assembled Overview must be reachable by some rule
    # or by the fallback, or its tab can never appear
    unreachable = set(groups) - mapped - {"overview", "numbers"}
    check("every group is reachable from a rule", not unreachable,
          sorted(unreachable))

    # --- 2. the fallback group must exist ---------------------------------
    # tdGroupOf() falls through to a default; a default naming a group that is
    # not in TD_GROUPS means panels[...] is undefined and .appendChild throws,
    # which blanks the whole team view.
    for fb in re.findall(r"\?\s*tdGroupOf\(el\)\s*:\s*'([a-z]+)'", src):
        check("fallback group '%s' exists" % fb, fb in groups)

    # --- 3. TD_GROUPS/TD_MAP must be declared BEFORE first use ------------
    # ⚠ THIS PROJECT HAS HIT THE TEMPORAL DEAD ZONE SEVEN TIMES. A top-level
    # `const` read before its declaration does not read as undefined -- it
    # THROWS, and a throw inside boot renders a blank view with no error the
    # reader can see. A `typeof` guard does not help either.
    for const in ("TD_GROUPS", "TD_MAP", "POSFULL"):
        decl = src.find("const %s" % const)
        if decl < 0:
            check("%s declared" % const, False)
            continue
        # first use inside a function body that boot can reach
        uses = [x.start() for x in re.finditer(r"\b%s\b" % const, src)]
        first = min(uses)
        check("%s declared at or before first mention" % const, first >= decl,
              "first use %d, decl %d" % (first, decl))

    # --- 3b. the idempotence check must test the WORK, not just a stamp ----
    # ⚠ `box.dataset.dossier` lives on the #teamcard element, which survives a
    # re-render; the panels and nav live in its innerHTML, which does not. A
    # guard that trusted the stamp alone returned early on team -> player ->
    # Back and handed the reader the flat pre-dossier page with no tabs. It
    # errored nowhere. The condition must also confirm the nav is still there.
    guard = re.search(r"function teamDossier\([^)]*\)\s*\{(.*?)\n\s*/\* every section",
                      src, re.S)
    check("teamDossier has an entry guard", guard is not None)
    if guard:
        g = guard.group(1)
        check("idempotence checks for the nav, not only the stamp",
              "querySelector('.tdnav')" in g,
              "a dataset stamp alone survives a re-render that wipes the work")

    # --- 3c. the open team page is told when live data lands ---------------
    # ⚠ THIRD MEMBER OF THE POLL-STALENESS FAMILY (scoreboard, ledger, now
    # this). The Next-match card reads matchState(m, LIVE_BY_ID[...]) and
    # renders on route entry -- on a fresh load that is BEFORE the first poll
    # returns, so Michigan's page said "Next match - 3:00 PM PT - 99% to win"
    # while Michigan was mid-2nd-set, and nothing re-rendered it. deskLive()
    # must re-render the OPEN team route (and only that one), and the entry
    # is safe because teamDossier checks for its own nav, not just its stamp.
    live_fn = src[src.find("async function deskLive"):]
    live_fn = live_fn[:live_fn.find("\nasync function ", 10)
                      if live_fn.find("\nasync function ", 10) > 0 else 6000]
    check("the poll re-renders the open team page",
          "#\\/teams\\/" in live_fn and "showTeam(" in live_fn,
          "a live team's own page must not show the pre-match card")
    check("...and only the one actually open",
          "location.hash" in live_fn)
    # --- 3d. a live or finished match shows no pre-match pick --------------
    # ⚠ "99% TO WIN" SAT BESIDE A LIVE MATCH. The simulator's number is a
    # statement about a match that has not started; on a live card it reads as
    # a live win probability, which this site never shows.
    # (this module has no fn() helper -- that lives in a sibling suite; the
    #  bounded-body regex is the same technique inline)
    _nmm = re.search(r"function tdNextMatch\(.*?\n\}", src, re.S)
    nm = _nmm.group(0) if _nmm else ""
    check("the pick renders only on an upcoming match",
          "st === 'upcoming' && f.pick" in nm,
          "a pre-match pick on a live card reads as a live probability")
    check("...and a live card carries the tally, not the start time",
          "st === 'live'" in nm and "matchScore(" in nm)

    print("overview promises")

    # --- 4. Overview carries the three things the brief asked for ---------
    ov = re.search(r"ov\.insertAdjacentHTML\('beforeend',(.*?)\);", src, re.S)
    # round 17: the dashboard wraps the next-match card and the new blocks
    check("Overview assembled from the dashboard + players", ov is not None and
          "tdDashboard" in ov.group(1) and "tdPlayers" in ov.group(1))
    check("Scout's Read appended to Overview",
          re.search(r"if \(scout\) ov\.appendChild\(scout\)", src) is not None)

    # --- 5. faces are a real photo or initials -- never a drawn likeness ---
    # The brief was explicit: official headshots only where verified, never AI
    # portraits and never an empty visual placeholder. `avatar()` draws a
    # figure from a name; it must not be reachable from the dossier face.
    face = re.search(r"function tdFace\(([^)]*)\)\s*\{(.*?)\n\}", src, re.S)
    check("tdFace exists", face is not None)
    if face:
        body = face.group(2)
        check("tdFace never draws an avatar", "avatar(" not in body)
        check("tdFace falls back to initials", "tdInitials" in body)
        check("tdFace renders an img when a photo is given",
              "<img class=\"tdface\"" in body)
        check("a broken photo degrades to initials, not an empty frame",
              "onerror" in body and "tdinit" in body)

    # --- 6. a headline rate is position-appropriate and never a -0.0 ------
    # A libero rendered "-0.0 kills/set" on Bryant: schedule adjustment can
    # push a non-attacker's kill rate a hair below zero and rounding prints
    # the sign. 120 star rows sat below that threshold.
    # ⚠ ONE DEFINITION, EVERY CALLER. The rule below was first fixed inside
    # the dossier's own renderer -- and hours later Cody's phone showed
    # "-0.0 kills/set" on a LIVE MATCH PREVIEW, because starLine() was a
    # second copy of the same line with the old behaviour. posHeadline() is
    # now the single definition; both renderers must call it and neither may
    # keep a private kps fallback.
    check("posHeadline is the one definition",
          src.count("function posHeadline(") == 1)
    # (body extracted to the closing brace at column 0 -- `[^}]*` stopped at
    #  the FIRST inner brace and failed the correct code, the same extractor
    #  mistake this session has already made twice)
    _sl = re.search(r"function starLine\(.*?\n\}", src, re.S)
    check("...the match preview's starLine calls it",
          _sl is not None and "posHeadline(" in _sl.group(0),
          "a second copy of the rule is how the bug outlived its fix")
    check("...and starLine keeps no kps line of its own",
          re.search(r"function starLine\(.*?\n\}", src, re.S) and
          "kills/set" not in re.search(r"function starLine\(.*?\n\}", src,
                                       re.S).group(0))
    check("headline rate is floored above zero",
          re.search(r"v != null && v >= 0\.05", src) is not None)
    for pos, unit in (("LDS", "digs/set"), ("S", "assists/set"),
                      ("MB", "blocks/set")):
        check("%s leads with %s" % (pos, unit),
              re.search(r"x\.pos === '%s' \? \(?rate\(x\.\w+, '%s'\)"
                        % (pos, unit), src) is not None)

    # --- 3c. the glance strip must not hard-code its column count ---------
    # The dossier removes the "Next" tile (its Overview card is a superset),
    # so the strip is three tiles on most teams and four on a team with no
    # fixture. repeat(4,1fr) left a dead quarter-width column on every page
    # that had one removed.
    check("glance strip does not hard-code a column count",
          re.search(r"\.glance\{display:grid;grid-template-columns:"
                    r"repeat\(auto-fit", src) is not None)

    print("built page")
    if not os.path.exists(PAGE):
        check("page exists", False, PAGE)
    else:
        page = io.open(PAGE, encoding="utf-8").read()
        # ⚠ Tests must read the page Cody actually opens -- a guard that read
        # output/vb_dashboard.html once passed against a frozen artefact.
        check("dossier ships in the page", "teamDossier" in page)

        # ── MATCH BY MATCH, 2026 (Cody, 2026-08-28) ─────────────────────
        # "stats per match and totals (kinda like players in a match is
        # formatted)". The invariants that matter: the table exists; its rows
        # come from teamTotals() over the same BOXES payload the match view
        # reads (one definition -- the table and a clicked box score cannot
        # disagree); the totals row RECOMPUTES hit% and pts/set from summed
        # counts rather than averaging match rates; and the dossier files it
        # under Numbers, or it renders into no panel and silently vanishes.
        # ── THE DASHBOARD (round 17) ────────────────────────────────────
        # node executes the real block builders against fixtures; every
        # rendered rate must name its season and sample, form rows come only
        # from t.played (already duplicate/exhibition/empty clean), and a
        # signal can never read as an injury or status.
        import subprocess as _sp
        from test_scoreboard_density import block as _jsb

        def _jfn(name):
            i = src.find("function %s(" % name)
            return _jsb(src, i) if i >= 0 else None
        _dash_ok = True
        _js = """
const esc = s => String(s == null ? '' : s);
const routeFor = (v, r) => '#/' + v + (r ? '/' + r : '');
const slug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g,'-');
const PLAYERS = [
  { team: 'X', name: 'A Hitter', sets: 10, k: 39, ast: 2, digs: 12,
    bs: 1, ba: 4, aces: 3 },
  { team: 'X', name: 'B Setter', sets: 10, k: 4, ast: 112, digs: 20,
    bs: 0, ba: 2, aces: 1 },
  { team: 'X', name: 'C Bench', sets: 2, k: 9, ast: 0, digs: 1,
    bs: 0, ba: 0, aces: 0 }];
const AVAIL = { meta: {}, statuses: [], expired: [],
  signals: [{ team: 'X', player: 'A Hitter', kind: 'cody_observation' }] };
%s
%s
%s
const t = { played: [
  { gid: 'G1', d: '2026-08-28', opp: 'Opp', home: true, nondi: false,
    /* t.played sets arrive MINE-FIRST -- the payload builder flips the
       home side's pairs at source, so renderers must never flip again */
    mine: 3, theirs: 1, sets: [[25,20],[20,25],[25,18],[25,22]] }] };
const out = { form: tdForm(t, 'X'), ldr: tdLeaders(t, 'X'),
              av: tdAvailability(t, 'X') };
const bad = [];
if (!/2026, 10 sets/.test(out.ldr))
  bad.push('a leader rate lacks season+sample');
if (/C Bench/.test(out.ldr))
  bad.push('an under-floor sample entered the leaders');
if (!/assists\/set/.test(out.ldr) || !/B Setter/.test(out.ldr))
  bad.push('category leaders missing the setter');
if (out.form.indexOf('>W</i>') < 0 || !/3(\u2013|–)1/.test(out.form)
    || !/25(\u2013|–)20/.test(out.form))
  bad.push('form row lacks result or set line');
if (/injur|\bout\b(?!put)|unavailable/i.test(out.av))
  bad.push('a signal was promoted toward a status');
if (!/sets no status/.test(out.av))
  bad.push('the signal is not labelled as setting no status');
if (bad.length) { console.log('DASH-FAIL: ' + bad.join(' | '));
  process.exit(1); }
console.log('DASH-OK');
""" % (_jfn("tdForm"), _jfn("tdLeaders"), _jfn("tdAvailability"))
        _r = _sp.run(["node", "-e", _js], capture_output=True, text=True)
        check("DASHBOARD BEHAVIOUR: samples, floor, categories, form, "
              "signal wording", _r.returncode == 0,
              (_r.stdout + _r.stderr).strip()[:160])
        # negative control: strip the sample span and the same invariant fails
        _bad_ldr = _jfn("tdLeaders").replace(
            "' <em class=\"rcbasis\">2026, ' + Math.round(top.sets) +\n      ' sets</em>'", "''")
        if _bad_ldr == _jfn("tdLeaders"):
            _bad_ldr = _jfn("tdLeaders").replace("2026, ", "")
        _js2 = _js.replace(_jfn("tdLeaders"), _bad_ldr)
        _r2 = _sp.run(["node", "-e", _js2], capture_output=True, text=True)
        check("[NEG] a rate without its season+sample is caught",
              _r2.returncode != 0
              and "lacks season+sample" in (_r2.stdout + _r2.stderr))
        check("form reads t.played and nothing else",
              "(t.played || []).slice(0, 5)" in src
              and "LEDGER" not in _jfn("tdForm"))
        check("the dashboard grid is two columns on desktop, one on a phone",
              "grid-template-columns:1fr 1fr" in src
              and ".tddash{grid-template-columns:1fr}" in src)
        # ── PLAYER DOSSIER (round 18): the real showPlayer under node ──
        _sp_src = _jfn("showPlayer")
        _pd_js = """
const esc = s => String(s == null ? '' : s);
const pct = v => (v==null) ? '\\u2014' : String(v);
const routeFor = (v, r) => '#/' + v + (r ? '/' + r : '');
const slug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g,'-');
const logo = () => '';
const avatar = () => '<svg class="av"></svg>';
const ratingHTML = () => '';
const dayLabel = d => d;
const mHome = m => m.h;
const matchScore = m => [m.as, m.hs];
const allMatches = () => ({ M1: { gid:'M1', h:'X', as:1, hs:3 } });
const TEAMS = { X: { rank: 12, power_basis: 'preseason', avca: 6,
                     record26: '1-2' } };
const els = { playercard: { innerHTML: '' } };
global.document = { getElementById: id => els[id] };
%s
const base = { name: 'P', team: 'X', pos: 'S', num: 9, 'class': 'Jr',
  photo: null, sets: 10, ast: 118, dps: 2.7, aces: 0, kps: 0.4, hit: 0.1,
  bs: 0, ba: 0, pps: 1, games: [
    { gid:'M1', d:'2026-08-28', opp:'Opp', nondi:false, k:1, e:0, ta:3,
      hit:0.333, digs:8, bs:0, ba:1, ast:36, aces:0, sets:4, pts:1.5 }],
  aa: [], xf: null };
showPlayer(base);
const h = els.playercard.innerHTML;
const bad = [];
if (!/Assists\\/set/.test(h) || /Kills\\/set/.test(h))
  bad.push('setter chips not position-aware');
if (h.indexOf('2026 \\u00b7 10 sets') < 0 && h.indexOf('2026 · 10 sets') < 0)
  bad.push('season sample missing');
if (!/POWER <b>#12<\\/b> <i>preseason<\\/i>/.test(h)
    && h.indexOf('preseason') < 0)
  bad.push('rank basis missing');
if (h.indexOf('data-match="M1"') < 0) bad.push('log row lacks a route');
if (h.indexOf('>W</i>') < 0 && h.indexOf('>L</i>') < 0)
  bad.push('log row lacks the match result');
if (!/36 ast<\\/b>/.test(h) && h.indexOf('36 ast') < 0)
  bad.push('setter log does not lead with assists');
showPlayer(Object.assign({}, base, { sets: 0, games: [] }));
const h2 = els.playercard.innerHTML;
if (h2.indexOf('No counted 2026 match yet') < 0)
  bad.push('no-season state missing');
if (/0\\.00/.test(h2)) bad.push('zeros invented for an unplayed player');
if (bad.length) { console.log('PD-FAIL: ' + bad.join(' | '));
  process.exit(1); }
console.log('PD-OK');
""" % _sp_src
        _rp = _sp.run(["node", "-e", _pd_js], capture_output=True, text=True)
        check("PLAYER DOSSIER BEHAVIOUR: position chips, samples, rank "
              "basis, routed log, no-season state",
              _rp.returncode == 0, (_rp.stdout + _rp.stderr).strip()[:160])
        # negative controls: strip the sample suffix / the rank basis
        _bad1 = _sp_src.replace("' sets</i></span></div>'", "'</i></span></div>'")
        _r_b1 = _sp.run(["node", "-e", _pd_js.replace(_sp_src, _bad1)],
                        capture_output=True, text=True)
        check("[NEG] a season without its sample is caught",
              _r_b1.returncode != 0)
        _bad2 = _sp_src.replace("power_basis === 'live'", "false && ''")
        check("[NEG] the rank-basis expression exists to strip",
              _bad2 != _sp_src)
        check("the log reads p.games and nothing else",
              "(p.games || []).slice(0, 5)" in _sp_src
              and "LEDGER" not in _sp_src)
        check("the player availability block is AVAIL-fenced with its hook",
              "AVAILP-HOOK-BEGIN" in src and "function pdAvailability" in
              src.split("AVAIL-JS-BEGIN")[1].split("AVAIL-JS-END")[0])
        check("match-by-match table ships", 'Match by match, 2026' in page)
        _mbm = page[page.find('MATCH BY MATCH, THE TEAM AS A BOX-SCORE LINE'):]
        _mbm = _mbm[:_mbm.find('const rt = t.rot25')] if _mbm else ''
        check("  ...its rows come from teamTotals()", 'teamTotals(mine)' in _mbm)
        check("  ...totals recompute hit%% from summed counts",
              '(agg.k - agg.e) / agg.ta' in _mbm)
        check("  ...pts/set recomputed, never averaged",
              'aPts / agg.sets' in _mbm)
        check("  ...a missing box renders as absence, not a synthesized line",
              'no box score on file' in _mbm)
        check("  ...rows route to the match (data-match)", 'data-match=' in _mbm)
        # TD_MAP behavior: apply the page's own mapping rules to the heading
        _map = re.search(r"const TD_MAP = \[(.*?)\];", page, re.S)
        _files_to = None
        if _map:
            for pat, grp in re.findall(r"\[/(.+?)/i, '([a-z]+)'\]", _map.group(1)):
                if re.search(pat, 'Match by match, 2026', re.I):
                    _files_to = grp
                    break
        check("  ...TD_MAP files it into Numbers", _files_to == 'numbers',
              repr(_files_to))
        # negative control: an unmapped heading must NOT resolve to numbers
        _neg = None
        if _map:
            for pat, grp in re.findall(r"\[/(.+?)/i, '([a-z]+)'\]", _map.group(1)):
                if re.search(pat, 'Completely Unmapped Heading Xyz', re.I):
                    _neg = grp
                    break
        check("  [NEG] an unmapped heading files nowhere", _neg is None, repr(_neg))
        check("nav is a tablist", 'class="tdnav"' in page or
              "'tdnav'" in page)
        # mobile: the player grid must collapse to one column
        check("player grid collapses on a phone",
              re.search(r"@media \(max-width:\s*560px\)[^@]*?"
                        r"\.tdpgrid\{grid-template-columns:1fr\}", page,
                        re.S) is not None)

    # --- 7. negative-zero control on the real payload ---------------------
    # Positive control: the values that WOULD have printed a negative zero are
    # still in the data, so the guard above is doing work rather than passing
    # because the case disappeared.
    import json
    mm = re.search(r"const TEAMS = (\{)", page) if os.path.exists(PAGE) else None
    if mm:
        i = mm.start(1)
        d = 0
        j = i
        instr = False
        esc = False
        while j < len(page):
            c = page[j]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            elif c == '"':
                instr = True
            elif c == "{":
                d += 1
            elif c == "}":
                d -= 1
                if d == 0:
                    break
            j += 1
        teams = json.loads(page[i:j + 1])
        near = 0
        for v in teams.values():
            for st in (v.get("stars") or []):
                for f in ("kps", "dps", "bps", "asps"):
                    x = st.get(f)
                    if x is not None and -0.05 < x < 0.05:
                        near += 1
        check("rates that would round to zero still exist in the payload",
              near > 0, "%d found" % near)
        # ⚠ THE FACE RULE IS ENFORCED ON THE DATA, NOT THE FUNCTION. tdFace
        # renders whatever url it is handed; what makes the rule true is that
        # no placeholder ever reaches it. A `data:` URI is the 1x1 transparent
        # pixel some roster templates ship in place of a headshot -- an empty
        # visual placeholder is exactly what the brief forbade.
        # the face is looked up on the ROSTER row (`r.ph`), not on the star
        bad = []
        withph = 0
        for tn, v in teams.items():
            for r in (v.get("roster") or []):
                ph = r.get("ph")
                if not ph:
                    continue
                withph += 1
                # A face is legitimately one of two things: a remote headshot
                # URL from the school's own site, or a file Cody dropped in
                # Cody/players/ himself (private build only, gitignored). What
                # it may never be is a `data:` URI -- the 1x1 transparent pixel
                # some roster templates ship where a headshot should be, which
                # renders as an empty frame.
                if not (str(ph).startswith("http")
                        or str(ph).startswith("players/")):
                    bad.append((tn, r.get("n"), str(ph)[:32]))
        check("no face is a data: URI or other placeholder", not bad, bad[:3])
        check("real headshots are actually present", withph > 200,
              "%d roster rows carry a photo" % withph)
        # and the stars a dossier shows must be findable on that roster, or
        # every face silently falls back to initials
        # ⚠ THRESHOLD-FREE NOW, THIRD REWRITE OF THIS CHECK. `len(miss) < 20`
        # broke on growth; a 5% ratio then broke the first Saturday at 5.7%,
        # because the residual is players the roster crawl genuinely lacks --
        # a COVERAGE fact that grows with the season, not a display bug (an
        # unrostered star renders initials, which is honest). The actual
        # defect class is a SPELLING/CASING miss: the star and a roster row
        # normalise to the same key yet differ as strings, so the face lookup
        # fails on a player the page demonstrably knows. build_hub now
        # respells stars from the payload roster (_star_names_aligned), so
        # the correct count of that class is ZERO -- no bound to drift.
        def _nk(x):
            import unicodedata as _u
            x = _u.normalize("NFKD", x or "")
            x = x.encode("ascii", "ignore").decode("ascii")
            return re.sub(r"[^a-z]", "", x.lower())
        spell, unrostered, tot = [], 0, 0
        for tn, v in teams.items():
            rows = [r.get("n") for r in (v.get("roster") or []) if r.get("n")]
            names, byk = set(rows), dict((_nk(r), r) for r in rows)
            for st in (v.get("stars") or [])[:3]:
                if not st.get("n"):
                    continue
                tot += 1
                if st["n"] in names:
                    continue
                if _nk(st["n"]) in byk:
                    spell.append((tn, st["n"], byk[_nk(st["n"])]))
                else:
                    unrostered += 1
        check("no dossier star misses its roster row on spelling alone",
              not spell, spell[:4])
        # coverage is REPORTED, not bounded -- the initials fallback is the
        # designed behaviour for a player the roster crawl does not carry
        print("  (stars without a roster row at all: %d of %d -- render "
              "initials by design)" % (unrostered, tot))

    # --- 8. the private art must never reach the published page -----------
    # Cody/players/ holds drawn likenesses of named athletes that he placed
    # there himself. They are fine on his own machine and are not ours to
    # republish; Cody/ is gitignored, but the guard that matters is that the
    # PUBLIC build cannot emit the path at all.
    art = re.search(r"_artdir[^\n]*\n(?:[^\n]*\n){0,3}?[^\n]*os\.path\.isdir"
                    r"\(_artdir\)([^\n]*)", src)
    check("private player art is excluded from the public build",
          art is not None and "not PUBLIC" in art.group(1),
          art.group(1) if art else "guard not found")

    pub = os.path.join(ROOT, "output", "vb_dashboard.html")
    if os.path.exists(pub):
        p_ = io.open(pub, encoding="utf-8").read()
        check("no private art path in the published page",
              '"players/' not in p_ and "'players/" not in p_)

    print("")
    if FAIL:
        print("FAILED: %s" % ", ".join(FAIL))
        return 1
    print("dossier guards pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
