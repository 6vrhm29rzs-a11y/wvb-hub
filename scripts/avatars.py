#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Video-game style player avatars, drawn from what we actually know.

    python3 scripts/avatars.py > preview.html      # contact sheet

WHAT DRIVES THE PICTURE. Her POSITION and her TEAM'S COLOURS -- both real, both
already on the page. The pose is what that position does on a court: a setter
sets, a middle blocks, a pin swings, a libero passes. Nothing about the figure
claims anything about the person -- no face, no hair, no skin tone, no body
type. It is a kit and an action, the way a sports game draws a player you have
not unlocked yet.

WHY NOT A GENERATED FACE. Not squeamishness -- it would be WORSE. A face hashed
out of a name is wrong about a specific real person essentially always, and it
would sit inches from the real photographs already shown for 89.9% of
projected-six slots. A stylised figure is honestly a figure; a generated face is
a claim.

THE LIBERO IS A REAL RULE, NOT A STYLE CHOICE. The libero must wear a jersey
contrasting with her team's, so she is drawn in the school's accent colour. That
is the one place the picture tells you something you could verify.

DRAWING NOTES, paid for by a first attempt that read as chess pieces:
  * Fill and stroke never come from the same group. The first version set both
    on the parent, so every filled shape also got a 2.6px outline and the limbs
    fattened into the torso until the silhouette was a blob.
  * Limbs are drawn OUTSIDE the torso silhouette, not overlapping it, or the
    pose disappears at 40px -- which is the only size that matters.
  * Each pose has one unmistakable feature: the setter's triangle, the
    blocker's two vertical bars, the hitter's cocked arm, the libero's platform.

Python 3.9 target. This module is the single definition of the art; the page
gets the same shapes emitted as a JS function.
"""

import json
import os
import sys
from typing import Any, Dict, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEUTRAL = "#9A8F7D"          # a team with no readable logo colour
ON_NEUTRAL = "#FFFFFF"

# 40x40 canvas. `B` = body group (fill only). `L` = limbs (stroke only).
# Torso is deliberately narrow so arms read as separate shapes.
_HEAD = '<circle cx="%s" cy="%s" r="3.9"/>'
_TORSO = ('<path d="M%(x)s %(y)sc2.9 0 4.4 1.8 4.4 4.4v6.2h-8.8v-6.2'
          'c0-2.6 1.5-4.4 4.4-4.4z"/>')

POSES = {
    # SETTER -- hands together above the forehead, elbows wide. The triangle is
    # the read.
    "S": {
        "body": (_HEAD % (20, 13) + (_TORSO % {"x": 20, "y": 17.6})),
        "limbs": '<path d="M16.6 19.6 14.6 12.8M23.4 19.6l2-6.8"/>',
        "hands": [(14.2, 11.8), (25.8, 11.8)],
        "ball": (20, 7.6, 3.2),
    },
    # MIDDLE BLOCKER -- two straight vertical arms clear of the torso, hands
    # above the head. Reads as a wall.
    "MB": {
        "body": (_HEAD % (20, 15) + (_TORSO % {"x": 20, "y": 19.6})),
        "limbs": '<path d="M14.4 22.4 13.6 9.6M25.6 22.4l.8-12.8"/>',
        "hands": [(13.4, 8.4), (26.6, 8.4)],
    },
    # OUTSIDE / OPPOSITE -- the swing. One arm cocked high behind, one tracking
    # low across. Asymmetry is the whole point.
    "OH": {
        "body": (_HEAD % (21.5, 14) + (_TORSO % {"x": 21.5, "y": 18.6})),
        "limbs": ('<path d="M25 20.4 30 13.4"/>'
                  '<path d="M18 21.4 10.8 25.4"/>'),
        "hands": [(30.6, 12.4), (9.8, 26)],
        "ball": (32.4, 7.4, 2.9),
    },
    # LIBERO / DS -- the platform: two arms joined, angled low. Drawn dropped
    # and forward so the stance reads as a dig.
    "L/DS": {
        "body": (_HEAD % (23, 15.5) + (_TORSO % {"x": 23, "y": 20})),
        "limbs": ('<path d="M19.8 22.8 10.4 28.4M25.6 23.4 10.4 28.4"/>'),
        "hands": [(9.4, 29)],
    },
}
POSES["OPP"] = POSES["OH"]
POSES["RS"] = POSES["OH"]
POSES["DS"] = POSES["L/DS"]
POSES["L"] = POSES["L/DS"]

# No position on file: a plain standing figure. Present and unlabelled, not
# pretending to be a position we do not know.
UNKNOWN = {
    "body": (_HEAD % (20, 14) + (_TORSO % {"x": 20, "y": 18.6})),
    "limbs": '<path d="M16.4 21.6 13.4 27.4M23.6 21.6l3 5.8"/>',
    "hands": [],
}

LIBERO_POSITIONS = ("L/DS", "L", "DS")


def avatar_svg(pos, colors=None, size=40):
    # type: (Optional[str], Optional[Dict[str, Any]], int) -> str
    """One player avatar as a standalone SVG string."""
    c = colors or {}
    primary = c.get("primary") or NEUTRAL
    ink = c.get("on_primary") or ON_NEUTRAL
    if pos in LIBERO_POSITIONS:
        # Contrasting jersey -- the school's own accent where it has one.
        primary = c.get("accent") or primary
        ink = c.get("on_accent") or ink

    p = POSES.get(pos) or POSES.get((pos or "").upper()) or UNKNOWN
    hands = "".join('<circle cx="%s" cy="%s" r="1.9"/>' % h for h in p["hands"])
    ball = ""
    if p.get("ball"):
        bx, by, br = p["ball"]
        ball = ('<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="%s" '
                'stroke-width="1.6"/>' % (bx, by, br, primary, ink))
    return (
        '<svg viewBox="0 0 40 40" width="%d" height="%d" class="pav" '
        'aria-hidden="true" focusable="false">'
        '<circle cx="20" cy="20" r="20" fill="%s"/>'
        # Fill-only group: heads, torsos and hands.
        '<g fill="%s">%s%s</g>'
        # Stroke-only group: limbs. Kept apart so nothing gets both.
        '<g fill="none" stroke="%s" stroke-width="2.5" stroke-linecap="round">%s</g>'
        '%s</svg>' % (size, size, primary, ink, p["body"], hands, ink,
                      p["limbs"], ball))


def preview():
    """A contact sheet, so the art is judged rather than imagined -- including
    at 22px, which is the size it actually renders in a roster row."""
    colors = {}
    path = os.path.join(REPO, "data", "team_colors_2026.json")
    if os.path.exists(path):
        colors = (json.load(open(path, encoding="utf-8")) or {}).get("teams") or {}
    picks = [t for t in ("Nebraska", "Texas", "Kentucky", "Wisconsin",
                         "Louisville", "Stanford", "Pittsburgh", "Creighton")
             if t in colors] or [None]
    order = ("S", "OH", "OPP", "MB", "L/DS", None)
    rows = []
    for t in picks:
        sw = colors.get(t) or {}
        cells = "".join('<td>%s<span>%s</span></td>'
                        % (avatar_svg(pos, sw, 54), pos or "none")
                        for pos in order)
        small = "".join(avatar_svg(pos, sw, 22) for pos in order)
        rows.append('<tr><th>%s<br><code>%s%s</code></th>%s<td class="sm">%s'
                    '<span>at 22px</span></td></tr>'
                    % (t or "no colours yet", sw.get("primary", "&mdash;"),
                       (" / " + sw["accent"]) if sw.get("accent") else "",
                       cells, small))
    return ("<!doctype html><meta charset=utf-8><title>avatar sheet</title>"
            "<style>body{font:14px system-ui;background:#FBF7EF;color:#141210;padding:24px}"
            "table{border-collapse:collapse}"
            "th{text-align:left;padding:10px 16px 10px 0;font-weight:600;white-space:nowrap}"
            "code{font:11px ui-monospace;color:#5A5347}"
            "td{padding:9px;text-align:center}"
            "td span{display:block;font:11px ui-monospace;color:#5A5347;margin-top:5px}"
            "td.sm{padding-left:22px;border-left:1px solid #E7DECD}"
            "</style><h1>Player avatars &mdash; position &times; team colour</h1>"
            "<p style='color:#5A5347;max-width:60em'>Pose is the player's real position; "
            "colour is her school's own logo colour. The libero is drawn in the accent "
            "because the rules require a contrasting jersey. No face, no hair, no skin "
            "tone &mdash; nothing here claims anything about the person.</p>"
            "<table>%s</table>" % "".join(rows))


if __name__ == "__main__":
    sys.stdout.write(preview())
