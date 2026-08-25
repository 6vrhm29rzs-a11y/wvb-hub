#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A trend line, or an honest statement that there is not one yet.

⚠ THE POINT OF THIS MODULE IS THE STATE WHERE IT DRAWS NOTHING. A chart with
one point, or with two points taken off different rulers, is not a smaller
chart -- it is a wrong one, and a line is the most persuasive thing a page can
draw. So the unavailable state is the default and a line has to earn its way
out of it.

TWO CONDITIONS, BOTH REQUIRED:
  1. at least MIN_POINTS dated observations for that team;
  2. all of them on the SAME BASIS.
Condition 2 is the one that is easy to miss. data/rankings_history_*.jsonl
records `source` per week -- "preseason" is a projection that reads no result,
"live"/"digby" respond to results -- and subtracting one from the other is
arithmetic on two different rulers. The archive already refuses to compute
MOVEMENT across a basis change for exactly this reason; a trend line is the
same claim drawn as a picture.

MEASURED 2026-08-25: the 2026 archive holds two weeks, W34 preseason and W35
digby. Zero teams have two observations on one basis, so every team currently
renders the unavailable state -- which is the correct answer, not a gap.

Python 3.9 target.
"""

import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_POINTS = 3          # two points is a line through anything


def load_history(season):
    path = os.path.join(REPO, "data", "rankings_history_%d.jsonl" % season)
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    rows.sort(key=lambda r: r.get("week") or "")
    return rows


def series(rows, team):
    """[(week, rank, source)] for one team, oldest first."""
    out = []
    for r in rows:
        for t in (r.get("teams") or []):
            if t.get("team") == team and t.get("rank"):
                out.append((r.get("week"), int(t["rank"]), r.get("source")))
                break
    return out


def usable(points):
    """(points_on_one_basis, why_not). Never returns a mixed-basis series."""
    if not points:
        return [], "no verified snapshot has been archived yet"
    bases = {}
    for w, rank, src in points:
        bases.setdefault(src or "?", []).append((w, rank, src))
    best = max(bases.values(), key=len)
    if len(best) < MIN_POINTS:
        if len(bases) > 1:
            return [], ("the archived weeks are on different rulers (%s), and a "
                        "line across them would compare two different rankings"
                        % " and ".join(sorted(bases)))
        return [], ("%d of %d verified snapshots so far"
                    % (len(best), MIN_POINTS))
    return best, ""


def spark(points, w=180, h=44):
    """A rank sparkline. Rank 1 is the TOP, because a rank is not a quantity."""
    if len(points) < 2:
        return ""
    ranks = [p[1] for p in points]
    lo, hi = min(ranks), max(ranks)
    span = float(hi - lo) or 1.0
    n = len(points) - 1
    pts = []
    for i, (_wk, rank, _s) in enumerate(points):
        x = 4 + (w - 8) * (i / float(n))
        y = 6 + (h - 12) * ((rank - lo) / span)      # lower rank number, higher
        pts.append((x, y))
    d = " ".join(("M" if i == 0 else "L") + "%.1f %.1f" % p
                 for i, p in enumerate(pts))
    dots = "".join('<circle cx="%.1f" cy="%.1f" r="2.2" fill="currentColor"/>' % p
                   for p in pts)
    first, last = points[0], points[-1]
    label = ("rank %d in %s, %d in %s"
             % (first[1], first[0], last[1], last[0]))
    return ('<svg class="spark" viewBox="0 0 %s %s" width="%s" height="%s" '
            'role="img" aria-label="%s" focusable="false">'
            '<path d="%s" fill="none" stroke="currentColor" stroke-width="1.8" '
            'stroke-linecap="round" stroke-linejoin="round"/>%s</svg>'
            % (w, h, w, h, label, d, dots))


def trend_html(season, team, label="POWER"):
    """The component. Either a real line, or a sentence saying why not."""
    pts = series(load_history(season), team)
    ok, why = usable(pts)
    head = ('<div class="trhd"><i>%s history</i></div>' % label)
    if not ok:
        return ('<div class="trend none">%s<p>Trend begins after more verified '
                'snapshots &mdash; %s.</p></div>' % (head, why))
    src = ok[0][2] or "archive"
    return ('<div class="trend">%s%s<p class="trsrc">%d weekly snapshots, all on '
            'the <b>%s</b> basis. Archived Mondays; never recomputed.</p></div>'
            % (head, spark(ok), len(ok), src))


def history_note(season):
    """One sentence for the Rankings tab: what the archive can and cannot draw.

    ⚠ SAID ONCE, IN THE RIGHT PLACE. The same fact used to render as a
    component on all 348 team pages. It is a fact about the ARCHIVE, not about
    any one team, so it belongs where the archive is the subject.
    """
    rows = load_history(season)
    if not rows:
        return ("No weekly ranking snapshot has been archived yet. "
                "History begins with the first Monday capture.")
    names = set()
    for r in rows:
        for t in (r.get("teams") or []):
            names.add(t.get("team"))
    ready = 0
    for n in names:
        pts, _why = usable(series(rows, n))
        if pts:
            ready += 1
    bases = sorted({(r.get("source") or "?") for r in rows})
    if ready:
        return ("%d of %d teams now have %d or more weekly snapshots on one "
                "basis, so their POWER history is drawn on the team page."
                % (ready, len(names), MIN_POINTS))
    return ("%d weekly snapshot%s archived so far (%s). A POWER history line "
            "needs %d on the SAME basis, so none is drawn yet -- a line across "
            "a preseason projection and an in-season rating would compare two "
            "different rankings."
            % (len(rows), "" if len(rows) == 1 else "s",
               " and ".join(bases), MIN_POINTS))


CSS = (".trend{margin:12px 0 4px}\n"
       ".trhd i{font:600 9.5px/1 var(--disp);letter-spacing:.15em;"
       "text-transform:uppercase;color:var(--slate);font-style:normal}\n"
       ".trend .spark{color:var(--navy);display:block;margin:7px 0 3px}\n"
       ".trend p{margin:4px 0 0;font-size:11.5px;color:var(--ink3);"
       "line-height:1.55}\n"
       ".trend.none p{color:var(--slate)}\n"
       ".histnote{margin:10px 0 2px;font-size:12px;color:var(--slate);"
       "line-height:1.6;max-width:78ch}\n")


if __name__ == "__main__":
    import sys
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    rows = load_history(season)
    print("archived weeks: %d" % len(rows))
    for r in rows:
        print("  %s  source=%s  teams=%d"
              % (r.get("week"), r.get("source"), len(r.get("teams") or []))) 
    names = set()
    for r in rows:
        for t in (r.get("teams") or []):
            names.add(t.get("team"))
    drawable = 0
    for n in sorted(names):
        ok, _why = usable(series(rows, n))
        if ok:
            drawable += 1
    print("teams with a drawable same-basis trend: %d of %d" % (drawable, len(names)))
    if names:
        n = sorted(names)[0]
        print("\nexample (%s):\n%s" % (n, trend_html(season, n)))
