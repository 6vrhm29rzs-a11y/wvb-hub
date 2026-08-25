#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Digby: four poses, drawn once, in flat SVG.

WHO HE IS. A friendly volleyball analyst who appears at TRANSITIONS -- an empty
morning, a first ballot, a live point, a finished save. He is not a chat widget
and not a row decoration: if he turned up beside every card he would stop being
a moment and become furniture.

⚠ ORIGINAL, AND DELIBERATELY NOT A BRANDED BALL. The ball in his hands is a
plain sphere with two curved seams -- the generic shape of the sport, not the
NCAA's or Molten's mark, whose panel geometry and colourways are theirs. He is
also not a volleyball-with-a-face, which is the stock mascot every clip-art set
already has.

⚠ HE IS DRAWN FOR A DARK GROUND, AND BOTH GROUNDS HERE ARE DARK. The "chalk
wash" on this site is rgba(245,241,232,.035) over Court Navy -- a tint, not a
light sheet -- so every pose carries a chalk-coloured silhouette stroke and no
large near-black fill. Checked on both before shipping.

SVG rather than PNG: transparent, crisp at 34px on a phone and 120px on a
desktop empty state, a few hundred bytes, and no new binary in a public repo.

Python 3.9 target. Preview: python3 scripts/digby_art.py > /tmp/digby.html
"""

POSES = ("briefing", "clipboard", "watching", "celebrate")

# The palette is the Film Room's, by name, so a colour here cannot drift away
# from the page around it.
SKIN = "#E8C9A8"
POLO = "#1F66D1"
POLO_DK = "#164B9B"
HAIR = "#7A4A2B"
CHALK = "#F5F1E8"
GOLD = "#D99A29"
CORAL = "#E55E4F"
# ⚠ THE OUTLINE HAS TO WORK ON BOTH GROUNDS. It was chalk at 55% alpha,
# which is fine on navy and INVISIBLE on a light sheet -- the ball, the
# clipboard and the board all disappeared, checked in the preview before
# shipping. Quiet Slate contrasts against navy AND chalk, so one value
# serves both instead of the art needing to know where it is.
LINE = "#8390A1"


def _head(tilt=0):
    """Head, hair and face. One definition -- four poses cannot drift apart."""
    return (
        '<g transform="rotate(%d 32 22)">'
        '<path d="M22 20a10 10 0 0 1 20 0v3a10 10 0 0 1-20 0z" fill="%s"/>'
        '<path d="M21.5 19c0-6 4.6-9.5 10.5-9.5S42.5 13 42.5 19c0 1-.4 1.8-.4 1.8'
        's-1.2-3.4-4.1-4.6c-2.6-1-4.6-.2-7.4.5-2.6.7-4.6.2-6.2 1.7-1.3 1.2-1.9 3-1.9 3'
        'S21.5 20 21.5 19z" fill="%s"/>'
        '<circle cx="28" cy="22" r="1.5" fill="#2A2118"/>'
        '<circle cx="36" cy="22" r="1.5" fill="#2A2118"/>'
        '<path d="M29 27q3 2.2 6 0" stroke="#2A2118" stroke-width="1.6" '
        'fill="none" stroke-linecap="round"/>'
        '</g>' % (tilt, SKIN, HAIR)
    )


def _torso():
    """Polo with a collar and a whistle cord -- an analyst, not a player."""
    return (
        '<path d="M22 34h20a6 6 0 0 1 6 6v14H16V40a6 6 0 0 1 6-6z" fill="%s"/>'
        '<path d="M28 34h8l-4 6z" fill="%s"/>'
        '<path d="M28.5 34.5 32 40l3.5-5.5" stroke="%s" stroke-width="1.2" '
        'fill="none"/>' % (POLO, POLO_DK, LINE)
    )


def _ball(cx, cy, r):
    """A plain ball: a sphere and two curved seams. No panels, no branding."""
    return (
        '<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="%s" stroke-width="1.2"/>'
        '<path d="M%s %sq%s %s %s 0" stroke="#9AA6B6" stroke-width="1" fill="none"/>'
        '<path d="M%s %sq%s %s 0 %s" stroke="#9AA6B6" stroke-width="1" fill="none"/>'
        % (cx, cy, r, CHALK, LINE,
           cx - r, cy, r, -r * 1.1, r * 2,
           cx, cy - r, r * 1.1, r, r * 2)
    )


def _arm(d, w=5):
    return ('<path d="%s" stroke="%s" stroke-width="%s" fill="none" '
            'stroke-linecap="round"/>' % (d, SKIN, w))


_BODIES = {
    # presenting: one arm open to the board, the other at his side
    "briefing": (
        '<rect x="46" y="20" width="17" height="14" rx="2" fill="none" '
        'stroke="%s" stroke-width="1.4"/>'
        '<path d="M49 25h11M49 28.5h8" stroke="%s" stroke-width="1.4" '
        'stroke-linecap="round"/>' % (LINE, GOLD)
        + _torso()
        + _arm("M44 42q7 -2 8 -8")
        + _arm("M20 42q-3 5 -2 9")
    ),
    # clipboard: held across the chest, pen in the other hand
    "clipboard": (
        _torso()
        + '<g transform="rotate(-8 40 44)">'
          '<rect x="34" y="36" width="16" height="19" rx="2" fill="%s" '
          'stroke="%s" stroke-width="1"/>'
          '<rect x="39" y="34" width="6" height="3.4" rx="1.2" fill="%s"/>'
          '<path d="M37.5 43h9M37.5 47h6.5" stroke="#8390A1" stroke-width="1.3" '
          'stroke-linecap="round"/></g>' % (CHALK, LINE, GOLD)
        + _arm("M22 41q-2 6 4 8")
    ),
    # watching: a hand shading the eyes, a ball high in the air
    "watching": (
        _ball(52, 13, 6)
        + _torso()
        + _arm("M42 40q6 -4 4 -12")
        + '<path d="M40 26q5 -1 7 -3" stroke="%s" stroke-width="5" '
          'fill="none" stroke-linecap="round"/>' % SKIN
        + _arm("M20 42q-3 5 -1 9")
    ),
    # celebrate: both arms up, ball tucked
    "celebrate": (
        _torso()
        + _arm("M43 38q8 -4 7 -13")
        + _arm("M21 38q-8 -4 -7 -13")
        + _ball(50, 22, 5)
        + '<path d="M14 20l1.5 4M18 17l1 3" stroke="%s" stroke-width="1.6" '
          'stroke-linecap="round"/>' % GOLD
    ),
}

_ALT = {
    "briefing": "Digby, the hub's analyst, presenting the day's board",
    "clipboard": "Digby, the hub's analyst, holding a ballot clipboard",
    "watching": "Digby, the hub's analyst, watching a live point",
    "celebrate": "Digby, the hub's analyst, celebrating a finished ballot",
}


def digby_svg(pose="briefing", size=96, cls="digby-art"):
    """One pose as inline SVG. Unknown pose -> briefing, never an empty box."""
    if pose not in _BODIES:
        pose = "briefing"
    tilt = {"watching": -8, "celebrate": 0, "clipboard": 4, "briefing": 0}[pose]
    return (
        '<svg class="%s" viewBox="0 0 64 64" width="%s" height="%s" '
        'role="img" aria-label="%s" focusable="false">'
        '%s%s</svg>'
        % (cls, size, size, _ALT[pose], _BODIES[pose], _head(tilt))
    )


def alt_text(pose):
    return _ALT.get(pose, _ALT["briefing"])


def preview():
    out = ['<body style="background:#07172B;padding:30px;font:14px sans-serif;'
           'color:#F5F1E8">']
    for ground, label in (("#07172B", "Court Navy"),
                          ("rgba(245,241,232,.035)", "chalk wash"),
                          ("#F5F1E8", "a genuinely light sheet")):
        out.append('<div style="background:%s;padding:18px;margin-bottom:14px">'
                   '<div style="opacity:.7;margin-bottom:8px">%s</div>' % (ground, label))
        for p in POSES:
            out.append('<span style="display:inline-block;text-align:center;'
                       'margin-right:22px">%s<div style="font:11px monospace;'
                       'opacity:.7">%s</div></span>'
                       % (digby_svg(p, 110), p))
        out.append('</div>')
    out.append('</body>')
    return "\n".join(out)


if __name__ == "__main__":
    print(preview())
