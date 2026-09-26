#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The daily reports: Morning Brief and Night Desk.

  mail_report.py morning|night [--variant A|B] [--day YYYY-MM-DD]

One set of facts, two renderings (Cody/coordination to-builder 009):
  A  plain text, compact and editorial -- what the mailer sends today
  B  the same facts as light HTML matched to the site's current theme

⚠ EVERY RESULT COMES FROM THE BUILT PAGE'S OWN PAYLOAD (TEAMS), not a
parallel computation, so the mail and the page cannot disagree about a score.
⚠ POWER CHANGES ARE RECOMPUTED, NOT STORED (power_asof.py): the prior day and
the Sunday lock are the same model with an earlier cutoff. Rating change
(0-100 POWER points) and rank change (places) are always shown separately.
⚠ NOTHING IS INVENTED. No verified news source or VolleyTalk thread capture is
connected, so those sections say so rather than filling in. Upset/close-call
rules are stated conventions and feed nothing.

Python 3.9 target.
"""
import datetime
import html as _h
import io
import json
import os
import re
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
PAGE = os.path.join(REPO, "Cody", "START-HERE.html")
SITE = "https://codys-macbook-pro.tail069aa6.ts.net/START-HERE.html"
import power_asof as PA  # noqa: E402

PT = PA.PT


# ---------------------------------------------------------------- inputs
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


def _live():
    """In-progress state from live_server, when it is running. Optional."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8799/api/live", timeout=5) as r:
            return json.loads(r.read().decode("utf-8")).get("games") or []
    except Exception:
        return []


def _results(teams, day):
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
            sets = g.get("sets") or []
            if not won:
                sets = [[b, a] for a, b in sets]
            rows.append({"w": w, "l": l, "ws": max(mine, theirs), "ls": min(mine, theirs),
                         "sets": sets,
                         "wr": (teams.get(w) or {}).get("rank"),
                         "lr": (teams.get(l) or {}).get("rank"),
                         "wa": (teams.get(w) or {}).get("avca"),
                         "la": (teams.get(l) or {}).get("avca")})
    return rows


def _gap(r):
    a, b = r.get("lr"), r.get("wr")
    return (b - a) if (a and b) else -10 ** 6


def _upset(r):
    """Which ruler makes this an upset, or None. ⚠ REVIEW 010 FINDING 5: the
    old rule mixed rulers -- an AVCA-poll upset was printed beside POWER ranks
    ("#14 BYU def #22 Baylor"), which reads as nonsense. Each upset now names
    its ruler and shows the PREGAME ranks on that ruler only.
      AVCA   the loser was in the AVCA poll in effect, the winner was not or
             was ranked below it
      POWER  on pregame POWER (as of the day's midnight): the loser was top 25
             and the winner 10+ places below, or the gap was 40+ places
    Conventions, not fitted numbers; they feed nothing."""
    la, wa = r.get("la"), r.get("wa")
    lp, wp = r.get("lp"), r.get("wp")
    if lp and wp and ((lp <= 25 and wp >= lp + 10) or (wp - lp) >= 40):
        return "POWER"
    if la and (wa is None or wa > la):
        return "AVCA"
    return None


def _close_call(r):
    lr, wr = r.get("lp"), r.get("wp")
    return bool(lr and wr and wr < lr and (lr - wr) >= 40 and r["ls"] >= 2)


def _fixtures(teams, day):
    fx, seen = [], set()
    for nm, t in teams.items():
        for f in (t.get("fixtures") or []):
            if f.get("d") != day or str(f.get("gid")) in seen:
                continue
            seen.add(str(f.get("gid")))
            a, h = (f.get("opp"), nm) if f.get("home") else (nm, f.get("opp"))
            fx.append({"gid": str(f.get("gid")), "t": f.get("t") or "TBA",
                       "a": a, "h": h, "neutral": f.get("site") == "neutral",
                       "ar": (teams.get(a) or {}).get("rank"),
                       "hr": (teams.get(h) or {}).get("rank"),
                       "apw": (teams.get(a) or {}).get("power"),
                       "hpw": (teams.get(h) or {}).get("power"),
                       "tv": f.get("tv")})
    return fx


def _watch(f):
    """How worth watching, 0-100: the two POWER ratings averaged, discounted by
    how far apart they are, weighted 70/30 toward quality. A convention that
    orders a list, not a forecast."""
    pa, pb = f.get("apw"), f.get("hpw")
    if pa is None or pb is None:
        return None
    return round((pa + pb) / 2.0 * (0.70 + 0.30 * max(0.0, 1.0 - abs(pa - pb) / 12.0)), 1)


def _power_block(base_epoch, base_label, lock_epoch, lock_label, top=15):
    cur, meta = PA.current()
    base, _ = PA.as_of(base_epoch)
    lock, _ = PA.as_of(lock_epoch)
    dd, dw = PA.deltas(cur, base), PA.deltas(cur, lock)
    rows = []
    for t, v in sorted(cur.items(), key=lambda kv: kv[1]["rank"])[:top]:
        rows.append({"rank": v["rank"], "team": t, "power": v["power"],
                     "dp_day": dd[t][0], "dr_day": dd[t][1],
                     "dp_wk": dw[t][0], "dr_wk": dw[t][1]})
    movers = []
    for t, v in cur.items():
        if v["rank"] and v["rank"] <= 50 and dd[t][0] is not None and dd[t][0] != 0:
            movers.append({"team": t, "rank": v["rank"], "dp": dd[t][0], "dr": dd[t][1]})
    movers.sort(key=lambda m: -abs(m["dp"]))
    return {"rows": rows, "movers": movers[:6], "day_label": base_label,
            "week_label": lock_label, "pregame": base,
            "recomputed": meta.get("generated_at_utc")}


def _poll_date():
    p = os.path.join(REPO, "data", "raw", str(SEASON), "polls_avca.jsonl")
    try:
        rows = [json.loads(x) for x in io.open(p, encoding="utf-8") if x.strip()]
        rows = [r for r in rows if r.get("season") == SEASON]
        st = rows[-1].get("stamp") if rows else None
        m = re.search(r"([A-Za-z]{3})[A-Za-z.]*\s+(\d{1,2})", st or "")
        return ("through %s %s" % (m.group(1).title(), m.group(2))) if m else st
    except (IOError, ValueError):
        return None


def _pt(epoch):
    return datetime.datetime.fromtimestamp(epoch, PT)


def _sunday_complete(lock_epoch):
    """(n_logged, n_final) for the Sunday before a Monday-00:00 lock, from the
    logged dataset. Positive only when every logged fixture is final; it
    cannot prove no game is missing from the log, and says so."""
    import season_counts as SC
    sun = (_pt(lock_epoch) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    doc = json.load(io.open(os.path.join(REPO, "data", "data_%d.json" % SEASON), encoding="utf-8"))
    g = [x for x in doc.get("games") or [] if x.get("start_time_epoch") and
         datetime.datetime.fromtimestamp(x["start_time_epoch"], PT).strftime("%Y-%m-%d") == sun]
    cls = SC.classify(g, SEASON) if g else {}
    g = [x for x in g if cls.get(str(x.get("game_id"))) not in ("duplicate", "exhibition")]
    return len(g), sum(1 for x in g if x.get("state") == "F")


def _pregame(res, table):
    for r in res:
        r["wp"] = (table.get(r["w"]) or {}).get("rank")
        r["lp"] = (table.get(r["l"]) or {}).get("rank")


def collect(kind, day=None, status_note=""):
    now = datetime.datetime.now(PT)
    day = day or now.strftime("%Y-%m-%d")
    d = datetime.date(*[int(x) for x in day.split("-")])
    teams = _payload("TEAMS") or {}
    lock = PA.week_lock_epoch(now)
    lock_label = "Sunday-night lock (%s)" % (_pt(lock) - datetime.timedelta(days=1)).strftime("%a %b %-d")
    n_sun, f_sun = _sunday_complete(lock)
    if n_sun and n_sun == f_sun:
        lock_label += ", all %d logged Sunday matches final" % n_sun
    else:
        lock_label += ", PROVISIONAL: %d of %d logged Sunday matches final" % (f_sun, n_sun)
    out = {"kind": kind, "day": day, "made": now.strftime("%a %b %-d, %-I:%M %p PT"),
           "site": SITE, "status_note": status_note,
           "page_built": datetime.datetime.fromtimestamp(os.path.getmtime(PAGE), PT).strftime("%a %-I:%M %p PT"),
           "avca_poll": _poll_date()}
    if kind == "night":
        res = _results(teams, day)
        out["results"] = res
        pend = [f for f in _fixtures(teams, day)]
        live = dict((str(g.get("id")), g) for g in _live())
        for f in pend:
            g = live.get(f["gid"])
            f["state"] = (g.get("period") if g and g.get("state") == "live" else
                          ("FINAL, not logged yet" if g and g.get("state") == "final" else "not started"))
        out["pending"] = pend
        out["power"] = _power_block(PA.pt_midnight(d), "vs start of today (today's results)",
                                    lock, lock_label)
        tmr = _fixtures(teams, (d + datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
        for f in tmr:
            f["ems"] = _watch(f)
        out["tomorrow"] = sorted([f for f in tmr if f["ems"] is not None],
                                 key=lambda f: -f["ems"])[:3]
    else:
        y = d - datetime.timedelta(days=1)
        res = _results(teams, y.strftime("%Y-%m-%d"))
        out["yesterday"] = y.strftime("%a %b %-d")
        out["results"] = res
        out["power"] = _power_block(PA.pt_midnight(y), "vs start of yesterday (yesterday's results)",
                                    lock, lock_label)
        fx = _fixtures(teams, day)
        for f in fx:
            f["ems"] = _watch(f)
        out["slate"] = sorted(fx, key=lambda f: (min(f["ar"] or 999, f["hr"] or 999),
                                                 max(f["ar"] or 999, f["hr"] or 999)))
        out["watch"] = sorted([f for f in fx if f["ems"] is not None],
                              key=lambda f: -f["ems"])[:5]
    res = out["results"]
    _pregame(res, out["power"]["pregame"])
    for r in res:
        r["ruler"] = _upset(r)
    ups = sorted([r for r in res if r["ruler"]],
                 key=lambda r: ((r.get("lp") or 999) if r["ruler"] == "POWER" else (r.get("la") or 99)))
    # ⚠ COMPACT (review 010): a brief leads with a few highlights, not 24 rows
    out["upsets"] = ups[:5]
    top = sorted([r for r in res if not r["ruler"]
                  and min(r.get("wp") or 999, r.get("lp") or 999) <= 25],
                 key=lambda r: min(r.get("wp") or 999, r.get("lp") or 999))
    out["ranked"] = top[:6]
    cc = [r for r in res if _close_call(r) and not r["ruler"]]
    out["close"] = cc[:3]
    shown = len(out["upsets"]) + len(out["ranked"]) + len(out["close"])
    out["more"] = max(0, len(res) - shown)
    return out


# ---------------------------------------------------------------- A: text
def _sgn(v, unit=""):
    if v is None:
        return "—"
    if v == 0:
        return "0"
    return ("%+.1f%s" % (v, unit)) if isinstance(v, float) else ("%+d%s" % (v, unit))


def _rk(n):
    return ("#%d" % n) if n else "NR"


def _res_line(r):
    """Ranks shown are PREGAME POWER (as of that day's midnight), labelled."""
    sets = " ".join("%d-%d" % (a, b) for a, b in r["sets"]) if r.get("sets") else ""
    return "%-4s %-20s def %-4s %-20s %d-%d  %s" % (
        _rk(r.get("wp")), r["w"][:20], _rk(r.get("lp")), r["l"][:20], r["ws"], r["ls"], sets)


def _upset_line(r, poll):
    if r["ruler"] == "AVCA":
        why = "AVCA upset: %s beat AVCA #%d %s (poll %s)" % (
            ("AVCA #%d %s" % (r["wa"], r["w"])) if r.get("wa") else ("unranked " + r["w"]),
            r["la"], r["l"], poll or "in effect")
    else:
        why = "POWER upset: pregame #%d %s beat pregame #%d %s (%d places)" % (
            r["wp"], r["w"], r["lp"], r["l"], r["wp"] - r["lp"])
    sets = " ".join("%d-%d" % (a, b) for a, b in r["sets"]) if r.get("sets") else ""
    return "%s, %d-%d  %s" % (why, r["ws"], r["ls"], sets)


def _dtxt(dp, dr):
    """Rating points and places, each labelled (review 010)."""
    if dp is None:
        return "—"
    pts = "0.0 pts" if dp == 0 else ("%+.1f pts" % dp)
    pl = "=" if not dr else ("%s%d" % ("▲" if dr > 0 else "▼", abs(dr)))
    return "%s %s" % (pts, pl)


def render_a(c):
    L = []
    W = L.append
    title = "NIGHT DESK" if c["kind"] == "night" else "MORNING BRIEF"
    W("WVB HUB DESK · %s · %s" % (title, c["day"]))
    W("Made %s from the page built %s." % (c["made"], c["page_built"]))
    if c.get("status_note"):
        W("Data status: %s" % c["status_note"])
    W("Ranks beside results are PREGAME POWER ranks.")
    W("")
    if c["kind"] == "morning":
        W("YESTERDAY (%s): %d counted results" % (c["yesterday"], len(c["results"])))
    else:
        W("TODAY: %d counted results" % len(c["results"]))
    W("-" * 58)
    if c["upsets"]:
        W("Upsets")
        for r in c["upsets"]:
            W("  " + _upset_line(r, c.get("avca_poll")))
    if c["ranked"]:
        W("Top-25 sides (pregame POWER)")
        for r in c["ranked"]:
            W("  " + _res_line(r))
    if c["close"]:
        W("Close calls (favourite ranked 40+ places higher, dropped 2 sets)")
        for r in c["close"]:
            W("  " + _res_line(r))
    if not c["results"]:
        W("  No counted results.")
    elif c.get("more"):
        W("  %d more results on the site." % c["more"])
    W("")
    p = c["power"]
    W("POWER TOP 15  (rating 0-100; change = rating pts, then places ▲/▼)")
    W("-" * 58)
    W("  %-3s %-20s %5s  %-13s  %-13s" % ("#", "Team", "POWER", "day", "week"))
    for r in p["rows"]:
        W("  %-3d %-20s %5.1f  %-13s  %-13s" % (
            r["rank"], r["team"][:20], r["power"],
            _dtxt(r["dp_day"], r["dr_day"]), _dtxt(r["dp_wk"], r["dr_wk"])))
    W("  day = %s." % p["day_label"])
    W("  week = vs the %s." % p["week_label"])
    W("  Both baselines are the same model recomputed with an earlier cutoff,")
    W("  using results known now: a late final or correction can change them.")
    if p["movers"]:
        W("  Biggest moves (top 50): " + "; ".join(
            "%s %s" % (m["team"], _dtxt(m["dp"], m["dr"])) for m in p["movers"]))
    W("")
    if c["kind"] == "night":
        W("STILL LIVE / NOT LOGGED AT SEND TIME: %d" % len(c["pending"]))
        W("-" * 58)
        for f in sorted(c["pending"], key=lambda f: min(f["ar"] or 999, f["hr"] or 999))[:15]:
            W("  %-4s %-20s at %-4s %-20s %s" % (_rk(f["ar"]), f["a"][:20], _rk(f["hr"]), f["h"][:20], f["state"]))
        if not c["pending"]:
            W("  None. Every match on today's slate is final and logged.")
        W("")
        if c["tomorrow"]:
            W("TOMORROW, WORTH WATCHING")
            for f in c["tomorrow"]:
                W("  %-11s %s %s %s %s %s" % (f["t"], _rk(f["ar"]), f["a"], "vs" if f["neutral"] else "at", _rk(f["hr"]), f["h"]))
            W("")
    else:
        W("TODAY'S SLATE: %d matches (ranked first)" % len(c["slate"]))
        W("-" * 58)
        for f in c["slate"][:15]:
            W("  %-11s %-4s %-20s %s %-4s %-20s" % (f["t"], _rk(f["ar"]), f["a"][:20],
                                                   "vs" if f["neutral"] else "at", _rk(f["hr"]), f["h"][:20]))
        if len(c["slate"]) > 15:
            W("  ... %d more on the site." % (len(c["slate"]) - 15))
        W("")
        W("NEWS & GAME THREADS: no verified news source or VolleyTalk thread")
        W("capture is connected yet, so nothing is listed.")
        W("")
    W("Upsets name their ruler. AVCA: the loser was in the poll in effect and")
    W("the winner was not, or ranked below it. POWER: on pregame POWER, a top-25")
    W("side beaten from 10+ places below, or a 40+ place gap. Conventions only.")
    W("Site: %s" % c["site"])
    return "\n".join(L)


# ---------------------------------------------------------------- B: HTML
INK, INK2, MUTE, LINE, PAGE_BG, CARD = "#16233B", "#3F5068", "#5D6B80", "#DCD6EC", "#EFECF7", "#FFFFFF"
POW, AVCA, WIN, LOSS, GOLD = "#4238C4", "#1D5FC2", "#1F7A4D", "#B23B3B", "#8A6508"


def _e(s):
    return _h.escape(str(s))


def _chip(n):
    if not n:
        return ('<span style="display:inline-block;min-width:30px;text-align:center;'
                'font:600 10px/16px Menlo,monospace;color:%s;border:1px solid %s;'
                'border-radius:4px">NR</span>' % (MUTE, LINE))
    return ('<span style="display:inline-block;min-width:30px;text-align:center;'
            'font:700 11px/18px Menlo,monospace;color:#fff;border-radius:4px;'
            'background:linear-gradient(120deg,#3B2F9E,#6A4FD8);background-color:%s">#%d</span>'
            % (POW, n))


def _delta_html(dp, dr):
    if dp is None:
        return '<span style="color:%s">—</span>' % MUTE
    col = WIN if dp > 0 else (LOSS if dp < 0 else MUTE)
    pts = "0.0 pts" if dp == 0 else ("%+.1f pts" % dp)
    pl = "=" if not dr else ("%s%d" % ("▲" if dr > 0 else "▼", abs(dr)))
    return ('<span style="color:%s;font-family:Menlo,monospace">%s</span>'
            ' <span style="color:%s;font-size:11px">%s</span>' % (col, pts, MUTE, pl))


def _h2(t, sub=""):
    return ('<h2 style="margin:26px 0 8px;font:700 15px/1.2 -apple-system,Helvetica,Arial,sans-serif;'
            'letter-spacing:.08em;text-transform:uppercase;color:%s;border-bottom:2px solid %s;'
            'padding-bottom:6px">%s%s</h2>' % (INK, POW, _e(t),
                                               ('<span style="font-weight:400;letter-spacing:0;'
                                                'text-transform:none;color:%s;font-size:12px"> · %s</span>' % (MUTE, _e(sub))) if sub else ""))


def _res_rows(rows, tag=None):
    out = []
    for r in rows:
        sets = " ".join("%d-%d" % (a, b) for a, b in r["sets"]) if r.get("sets") else ""
        out.append(
            '<tr><td style="padding:8px 0;border-bottom:1px solid %s">%s <b>%s</b>'
            ' <span style="color:%s">def.</span> %s %s'
            '<div style="color:%s;font:12px Menlo,monospace;margin-top:2px">%d-%d &nbsp; %s%s</div></td></tr>'
            % (LINE, _chip(r.get("wp")), _e(r["w"]), MUTE, _chip(r.get("lp")), _e(r["l"]),
               MUTE, r["ws"], r["ls"], _e(sets),
               (' &nbsp;<span style="color:%s;font-weight:700">%s</span>' % (LOSS, tag)) if tag else ""))
    return '<table role="presentation" width="100%%" style="border-collapse:collapse">%s</table>' % "".join(out)


def render_b(c):
    title = "Night Desk" if c["kind"] == "night" else "Morning Brief"
    B = []
    A = B.append
    A('<div style="background:%s;padding:16px 0;font-family:-apple-system,Helvetica,Arial,sans-serif;color:%s">'
      % (PAGE_BG, INK))
    A('<div style="max-width:620px;margin:0 auto;background:%s;border-radius:12px;overflow:hidden">' % CARD)
    A('<div style="background:linear-gradient(120deg,#1E2F5C,#3B2F7E 60%%,#6A3B8C);background-color:#1E2F5C;'
      'color:#fff;padding:18px 20px">'
      '<div style="font:700 11px/1 -apple-system,Helvetica,sans-serif;letter-spacing:.14em;color:#D6D2EE">WVB HUB DESK</div>'
      '<div style="font:800 28px/1.1 -apple-system,Helvetica,sans-serif;margin-top:6px">%s</div>'
      '<div style="font-size:13px;color:#D6D2EE;margin-top:4px">%s · made %s</div>%s</div>'
      % (_e(title), _e(c["day"]), _e(c["made"]),
         ('<div style="font-size:12px;color:#F2C766;margin-top:4px">Data status: %s</div>' % _e(c["status_note"])) if c.get("status_note") else ""))
    A('<div style="padding:4px 20px 22px">')
    head = ("Yesterday · %s" % c["yesterday"]) if c["kind"] == "morning" else "Today's results"
    A(_h2(head, "%d counted" % len(c["results"])))
    if c["upsets"]:
        A('<div style="font-weight:700;color:%s;font-size:13px;margin-top:6px">Upsets</div>' % LOSS)
        for r in c["upsets"]:
            A('<p style="margin:6px 0;font-size:14px;line-height:1.45">%s</p>' % _e(_upset_line(r, c.get("avca_poll"))))
    if c["ranked"]:
        A('<div style="font-weight:700;color:%s;font-size:13px;margin-top:12px">Top-25 sides</div>' % INK2)
        A(_res_rows(c["ranked"]))
    if c["close"]:
        A('<div style="font-weight:700;color:%s;font-size:13px;margin-top:12px">Close calls</div>' % GOLD)
        A(_res_rows(c["close"]))
    if not c["results"]:
        A('<p style="color:%s">No counted results.</p>' % MUTE)
    elif c.get("more"):
        A('<p style="color:%s;font-size:12px">%d more results on the site.</p>' % (MUTE, c["more"]))
    p = c["power"]
    A(_h2("POWER top 15", "rating 0-100 · change in points, then places"))
    A('<table role="presentation" width="100%%" style="border-collapse:collapse;font-size:14px">'
      '<tr style="color:%s;font-size:11px;text-transform:uppercase;letter-spacing:.06em">'
      '<td style="padding:4px 0">Team</td><td align="right">POWER</td><td align="right">vs day</td><td align="right">vs week</td></tr>' % MUTE)
    for r in p["rows"]:
        A('<tr><td style="padding:7px 0;border-top:1px solid %s">%s <b>%s</b></td>'
          '<td align="right" style="border-top:1px solid %s;font:700 14px Menlo,monospace">%.1f</td>'
          '<td align="right" style="border-top:1px solid %s">%s</td>'
          '<td align="right" style="border-top:1px solid %s">%s</td></tr>'
          % (LINE, _chip(r["rank"]), _e(r["team"]), LINE, r["power"], LINE,
             _delta_html(r["dp_day"], r["dr_day"]), LINE, _delta_html(r["dp_wk"], r["dr_wk"])))
    A('</table><p style="color:%s;font-size:12px;margin:6px 0 0">Day = %s. Week = vs the %s. '
      'Both baselines are the same model recomputed with an earlier cutoff, using results known now; '
      'a late final or correction can change them.</p>'
      % (MUTE, _e(p["day_label"]), _e(p["week_label"])))
    if p["movers"]:
        A('<p style="font-size:13px;margin:8px 0 0"><b>Biggest moves (top 50):</b> %s</p>' % " · ".join(
            "%s %s" % (_e(m["team"]), _delta_html(m["dp"], m["dr"])) for m in p["movers"]))
    if c["kind"] == "night":
        A(_h2("Still live / not logged", "at send time"))
        if c["pending"]:
            A('<table role="presentation" width="100%" style="border-collapse:collapse;font-size:14px">')
            for f in sorted(c["pending"], key=lambda f: min(f["ar"] or 999, f["hr"] or 999))[:15]:
                A('<tr><td style="padding:6px 0;border-bottom:1px solid %s">%s %s <span style="color:%s">at</span> %s %s</td>'
                  '<td align="right" style="border-bottom:1px solid %s;color:%s;font-size:12px">%s</td></tr>'
                  % (LINE, _chip(f["ar"]), _e(f["a"]), MUTE, _chip(f["hr"]), _e(f["h"]), LINE, GOLD, _e(f["state"])))
            A('</table>')
        else:
            A('<p style="font-size:14px">None. Every match on today\'s slate is final and logged.</p>')
        if c["tomorrow"]:
            A(_h2("Tomorrow, worth watching"))
            for f in c["tomorrow"]:
                A('<p style="margin:6px 0;font-size:14px"><span style="color:%s;font-family:Menlo,monospace">%s</span> '
                  '%s %s %s %s %s</p>' % (MUTE, _e(f["t"]), _chip(f["ar"]), _e(f["a"]),
                                         "vs" if f["neutral"] else "at", _chip(f["hr"]), _e(f["h"])))
    else:
        A(_h2("Today's slate", "%d matches, ranked first" % len(c["slate"])))
        A('<table role="presentation" width="100%" style="border-collapse:collapse;font-size:14px">')
        for f in c["slate"][:12]:
            A('<tr><td style="padding:6px 0;border-bottom:1px solid %s;color:%s;font:12px Menlo,monospace;white-space:nowrap">%s</td>'
              '<td style="padding:6px 0 6px 8px;border-bottom:1px solid %s">%s %s <span style="color:%s">%s</span> %s %s</td></tr>'
              % (LINE, MUTE, _e(f["t"]), LINE, _chip(f["ar"]), _e(f["a"]), MUTE,
                 "vs" if f["neutral"] else "at", _chip(f["hr"]), _e(f["h"])))
        A('</table>')
        if len(c["slate"]) > 12:
            A('<p style="color:%s;font-size:12px">%d more on the site.</p>' % (MUTE, len(c["slate"]) - 12))
        A(_h2("News & game threads"))
        A('<p style="font-size:14px;color:%s">No verified news source or VolleyTalk thread capture is connected yet, so nothing is listed.</p>' % INK2)
    A('<p style="color:%s;font-size:11.5px;line-height:1.5;margin-top:22px">Ranks beside results are pregame POWER. '
      'Upsets name their ruler: AVCA (poll in effect) or POWER (pregame; top-25 side beaten from 10+ below, or a 40+ gap). '
      'Conventions only.</p>' % MUTE)
    A('<p style="margin:14px 0 0"><a href="%s" style="color:%s;font-weight:700">Open the hub</a></p>' % (_e(c["site"]), POW))
    A('</div></div></div>')
    return "".join(B)


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "night"
    variant = "A"
    if "--variant" in sys.argv:
        variant = sys.argv[sys.argv.index("--variant") + 1].upper()
    day = None
    if "--day" in sys.argv:
        day = sys.argv[sys.argv.index("--day") + 1]
    note = ""
    if "--status" in sys.argv:
        note = sys.argv[sys.argv.index("--status") + 1]
    c = collect(kind, day, note)
    print(render_b(c) if variant == "B" else render_a(c))
