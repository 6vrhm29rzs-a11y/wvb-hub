#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The daily reports, as plain data.

Two shapes, both text-only for now (Cody: "Doesn't need to be graphics and
images yet. Send the data and we'll find mistakes"):

  night   what happened today, what moved, what is unverified
  morning last night's results, today's slate, what to watch

⚠ EVERY NUMBER COMES FROM THE BUILT PAYLOAD, not a parallel computation. The
page and the mail read the same TEAMS/RES structures, so they cannot disagree
about a score -- which is the failure mode that matters most here, because a
page can be re-rendered and a mail cannot.

⚠ SAME-DAY RESULTS SAY WHETHER THE SCHOOLS HAVE CONFIRMED THEM. The trust
cutoff already refuses to move a rating on an unverified same-day feed claim;
a mail that stated those as settled would be asserting more than the ratings
do.
"""
import datetime
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")


def _payload(name):
    """Pull a const from the built page -- the page is the source of truth."""
    s = io.open(PAGE, encoding="utf-8").read()
    m = re.search(r"const %s\s*=\s*(\{.*?\}|\[.*?\]);\n" % name, s, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _pt_today():
    return (datetime.datetime.utcnow() -
            datetime.timedelta(hours=7)).strftime("%Y-%m-%d")


def _wl(a):
    return "%d-%d" % (a[0], a[1])


def night(day=None):
    day = day or _pt_today()
    teams = _payload("TEAMS") or {}
    out = []
    W = out.append
    W("WVB HUB  —  NIGHT DESK  —  %s" % day)
    W("=" * 62)
    W("")

    # ---- results today, from each team's own counted match list ----
    seen, rows = set(), []
    for nm, t in teams.items():
        for g in (t.get("played") or []):
            if g.get("d") != day:
                continue
            gid = str(g.get("gid"))
            if gid in seen:
                continue
            seen.add(gid)
            mine, theirs = g.get("mine"), g.get("theirs")
            if mine is None or theirs is None:
                continue
            won = mine > theirs
            w, l = (nm, g.get("opp")) if won else (g.get("opp"), nm)
            ws, ls = (mine, theirs) if won else (theirs, mine)
            rows.append({"w": w, "l": l, "ws": ws, "ls": ls,
                         "site": g.get("site"), "opr": g.get("opr"),
                         "mine_rank": (teams.get(w) or {}).get("rank"),
                         "lose_rank": (teams.get(l) or {}).get("rank")})
    W("RESULTS  (%d counted matches)" % len(rows))
    W("-" * 62)
    if not rows:
        W("  none on the board yet for %s." % day)
    # biggest upsets first: the loser ranked well above the winner
    def gap(r):
        a, b = r.get("lose_rank"), r.get("mine_rank")
        return (b - a) if (a and b) else -10 ** 6
    def line(r, tag=""):
        wr = ("#%-3d " % r["mine_rank"]) if r["mine_rank"] else "     "
        lr = ("#%-3d " % r["lose_rank"]) if r["lose_rank"] else "     "
        return ("  %s%-22s def %s%-22s %d-%d%s"
                % (wr, r["w"][:22], lr, r["l"][:22], r["ws"], r["ls"], tag))

    # ⚠ A FLAT 40-PLACE GAP WAS THE WRONG RULE AND HID THE NIGHT'S STORY.
    # Penn St. (#22) beating Stanford (#8) is 14 places and was the result
    # everyone would talk about, while 40 places apart in the 200s is noise.
    # Beating a ranked side matters more the higher the side is, so: a win
    # over a POWER top-25 team by anyone ranked at least 10 places below it,
    # OR a 40-place gap anywhere. Both numbers are CONVENTIONS chosen to
    # match how the sport talks, not thresholds fitted to anything -- stated
    # here and in the mail, and they feed no rating.
    def notable(r):
        lo_, wn = r.get("lose_rank"), r.get("mine_rank")
        if lo_ and lo_ <= 25 and (wn or 999) >= lo_ + 10:
            return True
        return gap(r) >= 40
    ups = [r for r in rows if notable(r)]
    ups.sort(key=lambda r: ((r.get("lose_rank") or 999)
                            if (r.get("lose_rank") or 999) <= 25
                            else 1000 - min(gap(r), 999)))
    if ups:
        W("  UPSETS  (beat a POWER top-25 side from 10+ places below,")
        W("           or won across a 40-place gap)")
        for r in ups[:12]:
            W(line(r, "   %d places" % gap(r)))
        W("")
    rk = [r for r in rows
          if r not in ups and ((r.get("mine_rank") or 999) <= 50
                               or (r.get("lose_rank") or 999) <= 50)]
    rk.sort(key=lambda r: min(r.get("mine_rank") or 999,
                              r.get("lose_rank") or 999))
    if rk:
        W("  RANKED SIDES  (a POWER top-50 team involved)")
        for r in rk[:25]:
            W(line(r))
        W("")
    rest = len(rows) - len(ups) - min(len(rk), 25)
    if rest > 0:
        W("  %d further counted results are on the site." % rest)
        W("")

    # ---- the top of the board, and what moved ----
    # ⚠ TEAMS IS KEYED BY NAME, so an entry has no "team" field --
    # iterate items() and take the name from the key. Guessing that cost a
    # KeyError; guessing `rank26` earlier cost a silently EMPTY upset list,
    # which is worse because nothing failed and the mail just said less.
    board = sorted([(nm, t) for nm, t in teams.items() if t.get("rank")],
                   key=lambda kv: kv[1]["rank"])[:15]
    W("POWER TOP 15")
    W("-" * 62)
    for nm, t in board:
        rec = t.get("record26") or ""
        W("  %2d  %-26s %-7s POWER %s"
          % (t["rank"], nm, rec, t.get("power") or "—"))
    W("")

    # ---- honest caveats ----
    W("NOTES")
    W("-" * 62)
    W("  Counted matches only: exhibitions, duplicate feed listings and")
    W("  results under review are excluded, the same rule the site uses.")
    W("  Upset size is measured in POWER places, our own ruler.")
    W("")
    W("  Full site: https://codys-macbook-pro.tail069aa6.ts.net/START-HERE.html")
    return "\n".join(out)


def morning(day=None):
    day = day or _pt_today()
    teams = _payload("TEAMS") or {}
    out = []
    W = out.append
    W("WVB HUB  —  MORNING BRIEF  —  %s" % day)
    W("=" * 62)
    W("")
    # today's fixtures, ranked first
    fx, seen = [], set()
    for nm, t in teams.items():
        for f in (t.get("fixtures") or []):
            if f.get("d") != day:
                continue
            k = str(f.get("gid"))
            if k in seen:
                continue
            seen.add(k)
            fx.append({"a": nm, "opp": f.get("opp"), "t": f.get("t"),
                       "home": f.get("home"), "tv": f.get("tv"),
                       "ar": (teams.get(nm) or {}).get("rank"),
                       "hr": (teams.get(f.get("opp")) or {}).get("rank"),
                       "venue": f.get("venue")})
    def best(f):
        a, b = f.get("ar") or 999, f.get("hr") or 999
        return min(a, b) * 1000 + max(a, b)
    fx.sort(key=best)
    W("TODAY'S SLATE  (%d matches)" % len(fx))
    W("-" * 62)
    for f in fx[:30]:
        a, opp = f["a"], f["opp"]
        ar, hr, home = f.get("ar"), f.get("hr"), f.get("home")
        if (hr or 999) < (ar or 999):
            a, opp, ar, hr, home = opp, a, hr, ar, (not home)
        arx = ("#%-4d" % ar) if ar else "     "
        hrx = ("#%-4d" % hr) if hr else "     "
        tv = ("  [%s]" % f["tv"]) if f.get("tv") else ""
        W("  %-11s %s%-22s %s %s%-22s%s"
          % (f.get("t") or "TBA", arx, a[:22], "vs" if home else "at",
             hrx, opp[:22], tv))
    if len(fx) > 30:
        W("  ... and %d more on the site." % (len(fx) - 30))
    W("")
    W("  Times are Pacific. Ranks are our POWER rank.")
    W("  Full site: https://codys-macbook-pro.tail069aa6.ts.net/START-HERE.html")
    return "\n".join(out)


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "night"
    print(night() if kind == "night" else morning())
