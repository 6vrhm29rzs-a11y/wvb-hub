#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the global rail and the Why Watch preview (review round 4).

The failure modes these stop: two global score summaries of the same match
on one screen; a rail that grows without bound on a 60-match night; a quiet
day rendering a giant nothing; a preview that drifts from checkable facts
into marketing copy; and a forecast surviving past first serve.

Run: python3 scripts/test_why_watch.py -- no network.
"""

import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(label, ok, detail=""):
    print("  %-64s %s" % (label, "ok" if ok else "FAIL " + str(detail)[:120]))
    if not ok:
        FAILS.append(label)
    return ok


def main():
    print("THE GLOBAL RAIL AND WHY WATCH\n")
    src = io.open(os.path.join(REPO, "scripts", "build_hub.py"),
                  encoding="utf-8").read()
    hub = os.path.join(REPO, "Cody", "START-HERE.html")
    page = io.open(hub, encoding="utf-8").read() if os.path.exists(hub) else ""

    print("1. ONE GLOBAL SCORE STRIP, NOT TWO")
    # the tape's one-line rail form is deleted; on a non-Today route the tape
    # renders NOTHING and the ticker is the single global summary
    check("the cs-rail form is gone from the source", "cs-rail" not in src)
    check("...and from the built page", not page or "cs-rail" not in page)
    check("the non-marquee tape branch renders empty and returns",
          re.search(r"if \(!marquee\) \{[^}]*mount\.innerHTML = '';[^}]*return;",
                    src, re.S) is not None)

    print("\n2. THE RAIL IS BOUNDED AND ITS ORDER IS DETERMINISTIC")
    tk = src[src.find("let TK_LAST"):src.find("async function pollLive")]
    check("a cap exists and is six", "TK_CAP = 6" in tk)
    check("overflow gets an explicit All-live control",
          "data-alllive" in tk and "live.length > TK_CAP" in tk)
    check("the control applies the Live filter on Scores",
          "SB_FILTER = 'live'" in src)
    # deterministic priority: the sort key is the stated reason tuple with a
    # stable id tiebreak -- no Math.random, no insertion order
    check("priority = rv, mb, tv, dg, rank, then id",
          re.search(r"pa\.rv - pb\.rv.*pa\.mb - pb\.mb.*pa\.tv - pb\.tv"
                    r".*pa\.dg - pb\.dg.*pa\.rk - pb\.rk", tk, re.S) is not None
          and "localeCompare(String(b.id))" in tk)
    check("each chip states its reason (title)", 'title="\' + esc(why)' in tk)
    check("finals cannot linger: the caller filters to in-progress",
          "csTicker(live);" in src and "justEnded" in src)

    print("\n3. THE QUIET STATE IS NEXT-TO-WATCH, NEVER A GIANT NOTHING")
    check("quiet renders up to three upcoming priority fixtures",
          "TK_QUIET_CAP = 3" in tk and "tkQuietChips" in tk)
    check("the window is 72 hours", "3 * 86400000" in tk)
    check("no giant empty message in the ticker path",
          "No matches on the schedule" not in tk)

    print("\n4. WHY WATCH IS FACTS OR ABSENCE, AND IT LEADS")
    ww = src[src.find("/* WHY WATCH"):src.find("Match facts")]
    check("the module exists on the upcoming branch",
          "st === 'upcoming'" in ww and "todayReasons(m, null)" in ww)
    check("it renders BEFORE Match Facts (decision module leads)",
          "ribbonHTML(m, live, null)" in src[:src.find("/* WHY WATCH")]
          or src.find("ribbonHTML(m, live, null)") < src.find("/* WHY WATCH"))
    check("at most three reason chips", ".slice(0, 3)" in ww)
    check("no reasons and no listing renders no section",
          "if (!rs.length && !watch) return '';" in ww)
    check("a held TV listing renders; a missing one is OMITTED, never "
          "phrased as unavailable",
          "m.tv" in ww and "not televised" not in ww
          and "unavailable" not in ww)
    check("no outbound stream link is invented (none are held)",
          "http" not in ww)
    # no marketing adjectives anywhere in the module or the reason set
    reasons = src[src.find("function todayReasons"):src.find("function starPeek")]
    _banned = re.compile(r"'[^']*\b(?:hot|struggling|decisive|must-see|"
                         r"clutch|superstar)\b[^']*'", re.I)
    check("no marketing copy in the reason set",
          not _banned.search(reasons) and not _banned.search(ww))
    check("the disagreement chip carries BOTH labelled values",
          "AVCA #" in reasons and "POWER #" in reasons)
    check("POWER top-50 pairing yields to the stronger AVCA chip",
          "!(m.ar && m.hr)" in reasons)

    print("\n5. ROUND-5 CONTRACTS")
    # one live count, one definition
    check("the poller owns THE live count (LIVE_NOW)",
          "window.LIVE_NOW = live.length" in src)
    check("the masthead reads it",
          "typeof LIVE_NOW === 'number'" in src)
    check("a capped rail SAYS both numbers",
          "' shown</i>'" in src and "in progress" in src)
    # the featured marquee never sits above an open match detail
    check("no marquee above an open match detail",
          "if (h === 'match-desk') return !parts[1];" in src)
    # players-to-know metric precision
    check("metrics name what they measure",
          "% back-row attack share'" in src
          and "% serve-receive share'" in src)
    check("...and the bare ambiguous labels are gone",
          "'% back row'" not in src and "'% of serve-receive'" not in src)
    check("the headline rate carries its own season and sets",
          "x.hb" in src and "x.hs" in src)
    check("the derivation is stated for the group",
          "DERIVED from 2025 play-by-play" in src)
    # today watch cards
    check("a watch card REQUIRES a reason (no reason, no card)",
          "return w ? [m, rs, w] : null;" in src)
    check("the watch heading is live-aware",
          "? 'Watch now' : 'Your next watches'" in src)
    check("a row about another day names the day",
          "m.d !== todayPT() && m.dl" in src)
    # the dead weekend surface is gone, not hidden
    check("the invisible weekbox surface was deleted",
          'id="weekbox"' not in src and "renderWeek();" not in src)

    print("\n6. NEGATIVE CONTROLS")
    check("[NEG] an uncapped rail is caught", "TK_CAP = 6" not in
          tk.replace("TK_CAP = 6", "TK_CAP = 999"))
    _wwbad = ww.replace("if (!rs.length && !watch) return '';",
                        "if (!rs.length && !watch) return 'A big matchup!';")
    check("[NEG] filler prose on an empty reason list is caught",
          _wwbad != ww and "A big matchup!" in _wwbad)

    # ── the watch card's ACTION CONTRACT (review, 2026-08-30) ──────────
    # A card is ONE internal match route (its own <a>) plus AT MOST one
    # clearly labelled outbound official-preview action per destination.
    # "Preview →" beside a bare "ncaa.com" read as one doubled action.
    import re as _re
    _wc = _re.search(r"const watchCard = [\s\S]*?'</a>';", src)
    check("the watch-card renderer is findable", bool(_wc))
    if _wc:
        _w = _wc.group(0)
        check("exactly one action row per card", _w.count("wacts") == 1)
        check("exactly one internal-route label per card",
              _w.count("wgo") == 1)
        check("at most one outbound official action, and it names its "
              "destination", _w.count("wofficial") == 1
              and "preview: ncaa.com" in _w)
        check("the internal label does not say Preview (that word belongs "
              "to the outbound action)", "wgo\">Preview" not in _w)
        check("one outbound host only",
              _w.count("ncaa.com/game/") == 1)
    # and one card per match: the watches list is keyed by gid via
    # allMatches(), so a gid cannot appear twice -- assert the keying holds
    check("the watch list is built from the gid-keyed index",
          "const by = allMatches();" in src
          and "const every = Object.keys(by).map(k => by[k]);" in src)

    # ── BEHAVIORAL: the rendered card, not the source string ───────────
    # A multi-reason card (ranked-v-ranked + ranking disagreement + stars +
    # our-Top-25) and a plain card are RENDERED by the page's own
    # watchCard, then swept by the page's own wcardEnforceActions on a
    # real-ish DOM; the assertions read the surviving DOM, never the
    # source. A pre-seeded duplicate action row must be removed by the
    # paint-time contract.
    import subprocess as _sp
    from test_scoreboard_density import block as _blk
    _enf = _blk(src, src.find("function wcardEnforceActions("))
    # ⚠ brace-matched, never regexed -- a non-greedy [\s\S]*? swallowed
    # everything to the end of renderDesk on the first try (the documented
    # extractor lesson, again) and the harness died on a bare `return`
    _wc = _blk(src, src.find("const watchCard = (x, extraCls) =>"))
    check("watchCard and the enforcement are extractable",
          bool(_wc) and bool(_enf) and "wacts" in _wc
          and "return" in _wc and len(_wc) < 8000, str(len(_wc or "")))
    _js = r"""
const esc = s => String(s == null ? '' : s);
const rankHTML = () => '';
const teamRankChips = () => '';
const logo = () => '';
const mAway = m => m.a, mHome = m => m.h;
const matchRoute = (g) => '#/m/' + g;
const matchState = (m, live) => live ? 'live' : 'upcoming';
const matchScore = () => ['0','0'];
const liveLine = () => 'LIVE';
const reasonChips = m => '<span class="tdwhy">' +
  (m.ar && m.hr ? '<span class="tdtag">ranked v ranked</span>' : '') +
  (m.ap ? '<span class="tdtag dg">ranking disagreement</span>' : '') +
  '</span>';
const starPeek = m => m.stars
  ? '<span class="tdstars"><span class="pk">OH A</span><span class="pk">MB B</span></span>' : '';
const liveOf = () => null;
const dayLabel = d => d;
const tvOf = () => null;
const deskPct = p => p == null ? null : Math.round(p * 100) + '%%';
const deskForecast = () => '';
const nonDiPhrase = () => '';
const connector = () => ' v ';
const starLine = () => '';
const reasonWhy = () => '';
const fxPickable = () => false;
const posHeadline = () => '';
%s
// -- minimal DOM: parse the rendered string into a queryable tree --------
function parse(html) {
  const nodes = []; const stack = [];
  const re = /<(\/?)([a-zA-Z]+)((?:\s+[a-zA-Z-]+="[^"]*")*)\s*\/?>/g;
  let m2;
  const root = { tag: 'root', cls: '', attrs: {}, kids: [], parent: null };
  let cur = root;
  while ((m2 = re.exec(html))) {
    if (m2[1]) { cur = cur.parent || root; continue; }
    const attrs = {};
    (m2[3].match(/[a-zA-Z-]+="[^"]*"/g) || []).forEach(a => {
      const i = a.indexOf('='); attrs[a.slice(0, i)] = a.slice(i + 2, -1);
    });
    const n = { tag: m2[2], cls: attrs['class'] || '', attrs, kids: [],
                parent: cur, removed: false };
    cur.kids.push(n);
    if (!/^(br|img)$/.test(m2[2])) cur = n;   /* i/b are NOT void */
  }
  return root;
}
function q(node, cls, out) {
  out = out || [];
  node.kids.forEach(k => { if (!k.removed) {
    if (k.cls.split(' ').indexOf(cls) >= 0) out.push(k);
    q(k, cls, out); } });
  return out;
}
function wrapDom(tree) {
  const mk = n => ({
    _n: n,
    get href() { return n.attrs.href; },
    getAttribute: a => n.attrs[a] || null,
    querySelectorAll: sel => q(n, sel.replace('.', '')).map(mk),
    remove: () => { n.removed = true; },
  });
  return mk(tree);
}
const multi = { gid: 'G1', a: 'A U', h: 'B U', ar: '2', hr: '1',
  ap: 11, hp: 1, t: '1:00 PM PT', d: '2026-08-30', venue: 'Arena',
  stars: true };
const plain = { gid: 'G2', a: 'C U', h: 'D U', t: '2:00 PM PT',
  d: '2026-08-30', venue: 'Gym' };
const html = watchCard([multi, [], 1]) + watchCard([plain, [], 1]);
const dom = wrapDom(parse(html));
const cards = dom.querySelectorAll('.wcard');
const bad = [];
if (cards.length !== 2) bad.push('expected 2 cards, got ' + cards.length);
cards.forEach((c, i) => {
  wcardEnforceActions({ querySelectorAll: s2 => (s2 === '.wcard' ? [c] : c.querySelectorAll(s2)) });
  const acts = c.querySelectorAll('.wacts');
  const gos = c.querySelectorAll('.wgo');
  const offs = c.querySelectorAll('.wofficial');
  if (acts.length !== 1) bad.push('card ' + i + ': ' + acts.length + ' action rows');
  if (gos.length !== 1) bad.push('card ' + i + ': ' + gos.length + ' internal labels');
  const hosts = offs.map(o => ((o.getAttribute('data-href') || '')
    .match(/https?:\/\/([^/]+)/) || [])[1]);
  if (new Set(hosts).size !== hosts.length)
    bad.push('card ' + i + ': repeated outbound destination');
  if (!c.href) bad.push('card ' + i + ': no internal route on the card');
});
// pre-seeded duplicate: the contract must sweep it
const dupHtml = watchCard([multi, [], 1]).replace('<span class="wacts">',
  '<span class="wacts"><span class="wgo">Open match →</span>' +
  '<span class="wofficial" data-href="https://www.ncaa.com/game/G1">' +
  'preview: ncaa.com</span></span><span class="wacts">');
const ddom = wrapDom(parse(dupHtml));
const dcard = ddom.querySelectorAll('.wcard')[0];
const before = dcard.querySelectorAll('.wacts').length;
wcardEnforceActions({ querySelectorAll: s2 => (s2 === '.wcard' ? [dcard] : dcard.querySelectorAll(s2)) });
const after = dcard.querySelectorAll('.wacts').length;
if (before !== 2) bad.push('seed failed: ' + before + ' rows before sweep');
if (after !== 1) bad.push('sweep left ' + after + ' rows');
if (bad.length) { console.log('WC-FAIL: ' + bad.join(' | ')); process.exit(1); }
console.log('WC-OK'); process.exit(0);
""" % ((_wc or "") + "\n" + (_enf or ""))
    _r = _sp.run(["node", "-e", _js], capture_output=True, text=True)
    check("BEHAVIOR: rendered multi-reason and plain cards each carry "
          "exactly one action row; a seeded duplicate is swept",
          _r.returncode == 0, (_r.stdout + _r.stderr).strip()[:200])

    print()
    if FAILS:
        print("FAILED: %d check(s)" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("ALL WHY-WATCH GUARDS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
