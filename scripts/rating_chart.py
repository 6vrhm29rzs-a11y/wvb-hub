#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The season's POWER movement as a picture (Cody, 2026-09-11).

"graphed out with the top 50 teams and their power rating score (y axis)
throughout the season (x axis) ... lines moving up or down day to day."

⚠ FIFTY LINES CANNOT EACH HAVE A COLOUR, so they do not get one. Giving 50
series 50 hues is the spaghetti chart: nothing is followable and the palette
is decorative. All 50 are drawn in one recessive ink, and a small highlighted
set carries its school's real colour AND a direct label at the right edge --
so identity is never colour alone, which is also what keeps it readable for
a colour-blind reader and in print.

⚠ THE Y AXIS IS THE NUMBER ON THE SITE. POWER = 50 + 12.5z, z taken across
all 348 that day -- verified to reproduce the board exactly (Nebraska 86.2,
Pittsburgh 81.9, Kentucky 81.8, Louisville 81.6, Texas 75.4). A chart whose
numbers disagree with the page it illustrates is worse than no chart.

⚠ GAPS ARE DRAWN AS GAPS. There is no snapshot for 2026-08-25..27 or
09-09..10. A line straight through a day we never published would invent
movement; the series breaks instead.

⚠ AND THE BASIS CHANGE IS MARKED. The board ran on the preseason projection,
then the blend, and moves to the live fit. Across that boundary a line
reports the RULER moving, not the team -- the same error the movement column
refuses to make.

Python 3.9. Writes a PNG next to the data.
"""
import io
import json
import os
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = int(os.environ.get("WVB_SEASON", "2026"))
SRC = os.path.join(REPO, "data", "rating_history_%d.json" % SEASON)
OUT = os.path.join(REPO, "Cody", "rating_history_%d.png" % SEASON)
OUT_SVG = os.path.join(REPO, "Cody", "rating_history_%d.svg" % SEASON)
TOPN = int(os.environ.get("WVB_CHART_TOP", "50"))
HILITE = int(os.environ.get("WVB_CHART_HILITE", "20"))


def power(scores):
    """The board's own transform, reproduced: 50 + 12.5z, clipped."""
    vals = [v for v in scores.values() if v is not None]
    if len(vals) < 2:
        return {}
    m, s = st.mean(vals), st.pstdev(vals)
    if not s:
        return {}
    return {t: max(0.0, min(100.0, 50.0 + 12.5 * (v - m) / s))
            for t, v in scores.items() if v is not None}


def main():
    if not os.path.exists(SRC):
        print("no history at %s -- run scripts/rating_history.py first" % SRC)
        return 1
    doc = json.load(io.open(SRC, encoding="utf-8"))
    pts = doc.get("points") or []
    if len(pts) < 2:
        print("only %d day(s) of history -- nothing to draw yet" % len(pts))
        return 1

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import datetime

    days = [datetime.date(*map(int, p["day"].split("-"))) for p in pts]
    per_day = [power({t: v.get("score") for t, v in p["teams"].items()})
               for p in pts]

    latest = per_day[-1]
    order = sorted(latest, key=lambda t: -latest[t])[:TOPN]
    top = order[:HILITE]

    # school colours, the site's own -- never invented
    colours = {}
    cpath = os.path.join(REPO, "data", "team_colors_%d.json" % SEASON)
    if os.path.exists(cpath):
        raw = json.load(io.open(cpath, encoding="utf-8"))
        raw = raw.get("teams", raw)
        for k, v in raw.items():
            c = v.get("primary") if isinstance(v, dict) else v
            if isinstance(c, str) and c.startswith("#"):
                colours[k] = c

    fig, ax = plt.subplots(figsize=(16, 11), dpi=170)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    have = [set(d) for d in per_day]

    by_day = dict(zip(days, per_day))
    span = []
    _c = days[0]
    while _c <= days[-1]:
        span.append(_c); _c += datetime.timedelta(days=1)

    def series(team):
        # ⚠ WALK THE CALENDAR, NOT THE SNAPSHOTS. Iterating only the days we
        # hold silently joined Aug 24 to Aug 28 across three unpublished
        # days -- a straight line through dates we never ranked, which is
        # exactly the invented movement the caption promised not to draw.
        xs, ys = [], []
        for d0 in span:
            d = by_day.get(d0)
            if d is not None and team in d:
                xs.append(d0); ys.append(d[team])
            else:
                xs.append(None); ys.append(None)
        out, cx, cy = [], [], []
        for x, y in zip(xs, ys):
            if x is None:
                if cx:
                    out.append((cx, cy)); cx, cy = [], []
            else:
                cx.append(x); cy.append(y)
        if cx:
            out.append((cx, cy))
        return out

    # the field: recessive, one ink, no legend -- context, not identity
    for t in order[HILITE:]:
        for cx, cy in series(t):
            ax.plot(cx, cy, color="#CBC7E0", linewidth=1.0,
                    zorder=1, solid_capstyle="round",
                    marker="o" if len(cx) == 1 else None, markersize=2.2)

    ends = []
    for t in top:
        col = colours.get(t) or "#12294B"
        for cx, cy in series(t):
            ax.plot(cx, cy, color=col, linewidth=2.0, zorder=3,
                    solid_capstyle="round",
                    marker="o" if len(cx) == 1 else None, markersize=4.5)
        if t in per_day[-1]:
            ends.append([per_day[-1][t], t, col])
    # ⚠ LABELS COLLIDE WHEN TEAMS ARE TIED, which near the top they are:
    # Pittsburgh 81.9 printed through Louisville 81.6 and Texas through SMU.
    # Nudge each label off its neighbour and draw a leader back to the true
    # value, so the line still ends where the number says it does.
    ends.sort(key=lambda e: e[0])
    span_y = max(1e-6, max(e[0] for e in ends) - min(e[0] for e in ends))
    minsep = span_y * 0.055
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < minsep:
            ends[i][0] = ends[i - 1][0] + minsep
    for (ly, t, col), truth in zip(ends, [per_day[-1][e[1]] for e in ends]):
        ax.annotate(" %s  %.1f" % (t, truth), (days[-1], ly),
                    va="center", ha="left", fontsize=10.5,
                    color="#16233B", fontweight="600", zorder=4)
        if abs(ly - truth) > 1e-9:
            ax.plot([days[-1], days[-1] + datetime.timedelta(hours=10)],
                    [truth, ly], color=col, linewidth=0.8, alpha=.55, zorder=2)

    title = ("POWER through the %d season  —  top %d teams, "
             "%d highlighted" % (SEASON, TOPN, HILITE))
    sub = ("one point per day we published a ranking · %s to %s · "
           "POWER = 50 + 12.5z across all 348, the same number the board shows"
           % (pts[0]["day"], pts[-1]["day"]))
    gaps = (doc.get("meta") or {}).get("missing_days") or []
    if gaps:
        sub += "\nno snapshot on %s — the lines break rather than " \
               "invent movement" % ", ".join(gaps)
    # ⚠ TITLE AND SUBTITLE ARE PLACED ON THE FIGURE, NOT THE AXES.
    # set_title(pad=) moves the title while an axes-fraction annotation
    # stays put, so the two chased each other across three renders. Worse,
    # two of my pad edits never applied at all (a .replace() with no
    # assert), so I was reading renders of unchanged code and concluding
    # the parameter did not work. Figure coordinates put both where they
    # are told, and the asserts below mean a missed edit fails loudly.
    _hdr = (title, sub)

    ax.set_ylabel("POWER", fontsize=11, color="#3F5068")
    ax.grid(axis="y", color="#DEDBEC", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#CBC7E0")
    ax.tick_params(colors="#5D6B80", labelsize=10)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_xlim(days[0], days[-1] + datetime.timedelta(days=4))

    fig.tight_layout(rect=(0, 0, 1, 0.88))    # reserve the header band
    fig.text(0.012, 0.975, _hdr[0], fontsize=17, color="#16233B",
             fontweight="700", va="top", ha="left")
    fig.text(0.012, 0.935, _hdr[1], fontsize=9.5, color="#5D6B80",
             va="top", ha="left", linespacing=1.7)
    if not os.path.isdir(os.path.dirname(OUT)):
        os.makedirs(os.path.dirname(OUT))
    # ⚠ matplotlib picks the format from the EXTENSION, so ".png.tmp" is not
    # a format it knows. Write a real .png beside it, then rename -- the same
    # atomic-write discipline the page uses, since this file is served too.
    tmp = OUT + ".partial.png"
    fig.savefig(tmp, facecolor=fig.get_facecolor())
    os.replace(tmp, OUT)
    tmps = OUT_SVG + ".partial.svg"
    fig.savefig(tmps, facecolor=fig.get_facecolor(), format="svg")
    os.replace(tmps, OUT_SVG)
    print("wrote %s" % os.path.relpath(OUT, REPO))
    print("wrote %s  (vector -- zooms without blurring)"
          % os.path.relpath(OUT_SVG, REPO))
    print("  %d days, top %d drawn, %d highlighted: %s"
          % (len(pts), TOPN, HILITE, ", ".join(top)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
