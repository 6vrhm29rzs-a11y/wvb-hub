#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A small icon language, drawn from volleyball equipment and broadcast notation.

TEN ICONS, AND NO MORE. A general-purpose icon library invites decoration: once
a hundred glyphs are available something gets one for the sake of it. These ten
each answer a question the page already asks in words, so an icon here is a
second channel for a label -- never a replacement for it.

⚠ EVERY ICON SHIPS WITH TEXT. icon() renders aria-hidden and is meant to sit
beside a word; icon_labelled() carries the word with it. A shape alone is a
guess for a reader who has not learned this set, and nobody has -- it is five
minutes old.

⚠ NO EMOJI. An emoji is somebody else's artwork, rendered differently on every
platform, and it cannot inherit currentColor or a stroke width.

They inherit currentColor, so a live icon is coral because its container is,
and a source icon is slate because its container is. One definition of the
shape, and the colour is the caller's business.

Python 3.9 target. Preview: python3 scripts/icons.py > /tmp/icons.html
"""

# stroke-based, 24x24, so every glyph shares a weight and an optical size
_P = {
    "live":       '<circle cx="12" cy="12" r="3.2" fill="currentColor"/>'
                  '<path d="M6.2 6.2a8.2 8.2 0 0 0 0 11.6M17.8 6.2a8.2 8.2 0 0 1 0 11.6"/>',
    "final":      '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    # a neutral floor: the net seen end-on, no home side
    "neutral":    '<path d="M12 4.5v15M4 8h16M4 8v8M20 8v8"/>'
                  '<path d="M7 11h10M7 14h10" opacity=".55"/>',
    # a road match: an arrow leaving a building
    # a road match: leaving the home post. The first version stacked a building
    # and a transformed arrow and read as neither.
    "road":       '<path d="M5 4.5v15"/><path d="M8.5 12H19"/>'
                  '<path d="M15 8l4 4-4 4"/>',
    "tv":         '<rect x="3.2" y="6" width="17.6" height="12" rx="1.6"/>'
                  '<path d="M8.5 3.5L12 6l3.5-2.5"/>',
    # pinned for review: a pushpin
    "pin":        '<path d="M9 3.5h6l-1 5 3.2 3.2H6.8L10 8.5z"/>'
                  '<path d="M12 11.7V20.5"/>',
    # source / verified: a shield with a tick
    "source":     '<path d="M12 3.4l7 2.6v5.4c0 4.3-2.9 7.6-7 9.2-4.1-1.6-7-4.9-7-9.2V6z"/>'
                  '<path d="M8.8 12.2l2.3 2.3 4.1-4.4"/>',
    # unavailable rather than zero: an empty slot, deliberately not a "0"
    "unavailable": '<path d="M4.5 12h15" stroke-dasharray="3 3"/>'
                   '<circle cx="12" cy="12" r="8.2" opacity=".5"/>',
    "up":         '<path d="M12 19V6"/><path d="M6.5 11.5L12 6l5.5 5.5"/>',
    "down":       '<path d="M12 5v13"/><path d="M6.5 12.5L12 18l5.5-5.5"/>',
}

LABELS = {
    "live": "live", "final": "final", "neutral": "neutral site",
    "road": "road match", "tv": "on TV", "pin": "pinned for review",
    "source": "source verified", "unavailable": "not available",
    "up": "moved up", "down": "moved down",
}

NAMES = tuple(_P.keys())


def icon(name, size=14, cls=""):
    """A glyph to sit BESIDE a word. aria-hidden: the word is the label."""
    if name not in _P:
        return ""
    return ('<svg class="ic %s" width="%s" height="%s" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="1.9" '
            'stroke-linecap="round" stroke-linejoin="round" '
            'aria-hidden="true" focusable="false">%s</svg>'
            % (cls, size, size, _P[name]))


def icon_labelled(name, text=None, size=14, cls=""):
    """The glyph and its word together -- the safe default everywhere."""
    if name not in _P:
        return text or ""
    return ('<span class="icl">%s<span>%s</span></span>'
            % (icon(name, size, cls), text or LABELS[name]))


def icon_alone(name, size=14, cls=""):
    """A glyph with NO adjacent word -- so it carries its own accessible name.

    Use only where a word genuinely will not fit; the title also gives sighted
    readers a hover explanation, because nobody has learned this set yet.
    """
    if name not in _P:
        return ""
    return ('<svg class="ic %s" width="%s" height="%s" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="1.9" '
            'stroke-linecap="round" stroke-linejoin="round" role="img" '
            'aria-label="%s" focusable="false"><title>%s</title>%s</svg>'
            % (cls, size, size, LABELS[name], LABELS[name], _P[name]))


CSS = (".ic{vertical-align:-.16em;flex:none}\n"
       ".icl{display:inline-flex;align-items:center;gap:5px}\n")


def preview():
    out = ['<body style="background:#07172B;color:#F5F1E8;padding:26px;'
           'font:14px sans-serif"><style>%s</style>' % CSS]
    for ground, label in (("#07172B", "Court Navy"), ("#F5F1E8", "light sheet")):
        out.append('<div style="background:%s;color:%s;padding:16px;'
                   'margin-bottom:12px">' % (ground, "#F5F1E8" if ground == "#07172B" else "#07172B"))
        out.append('<div style="opacity:.7;margin-bottom:10px">%s</div>' % label)
        for n in NAMES:
            out.append('<span style="display:inline-flex;align-items:center;'
                       'gap:6px;margin:0 18px 10px 0">%s</span>'
                       % icon_labelled(n, size=18))
        out.append("</div>")
    out.append("</body>")
    return "\n".join(out)


if __name__ == "__main__":
    print(preview())
