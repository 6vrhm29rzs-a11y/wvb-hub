# Arena Daylight — the visual system

2026-08-30. One deliberate system, applied everywhere; not a patch pass.
Direction set by Cody's review: the navy-on-navy build was hard to read,
type too small and condensed, borders louder than content, and the giant
header made every route feel cramped.

## Palette (all contrast ratios computed against the surface they sit on)

| Token | Hex | Role | Contrast |
|---|---|---|---|
| `--page` | `#F4F6F9` | primary canvas — cool arena near-white, not cream | — |
| `--card` | `#FFFFFF` | cards, tables, panels | — |
| `--alt` | `#EDF1F6` | stripes, wells, quiet fills | — |
| `--ink` | `#16233B` | reading ink — deep navy AS TYPE | 13.0:1 on page |
| `--ink2` | `#3F5068` | secondary copy | 7.2:1 |
| `--ink3` | `#64748B` | muted slate: labels, dividers' text | 4.8:1 |
| `--line` / `--line2` | `#DDE4EE` / `#C9D4E2` | hairline dividers — borders recede, content leads | — |
| `--navy` | `#12294B` | THE scoreboard surface: rally tape, featured board, table header bands only | chalk 12.6:1 |
| `--chalk` | `#F5F7FA` | ink on navy surfaces | — |
| `--rally` | `#1D5FC2` | serve blue: links, controls, focus, neutral data emphasis | 4.9:1 on card |
| `--gold` | `#8A6508` | court-gold as TYPE (rank, selection) | 5.4:1 on card |
| `--gold-fill` | `#E3B341` | court-gold as FILL/edge (never body text) | — |
| `--live` | `#C81E2E` | live/urgent only | 5.9:1 on card |
| `--good` / `--bad` | `#1D7D4F` / `#B42332` | win/loss semantics | 4.9 / 6.6:1 |

Never: rainbow chips, gradients-as-decoration, glass, motion for its own
sake. Team colours stay as the 4px identity edge (checkable information).

## Typography roles

- **Body**: Source Sans 3 / system sans, 15px/1.55. Normal reading copy
  never below 14px. Long methodology copy is cut or collapsed, not shrunk.
- **Utility labels**: mono, 11px floor (raised from 9px), used for
  eyebrows, retrieval stamps, chips.
- **Display (Barlow Condensed)**: team names, scoreboard numerals, the
  masthead, section eyebrows. Nowhere else — condensed type is fast at
  three words and slow at three sentences.

## Layout principles

1. **The chrome is small; the page is the product.** Compact one-row
   masthead + slim live rail on every route. The rally tape (the marquee
   scoreboard) belongs to TODAY'S PAGE CONTENT, not to global chrome.
2. **Scoreboards are navy islands on daylight.** The few high-information
   surfaces (tape, featured board, linescore header bands) keep the deep
   navy — they read as scoreboards *because* the canvas is light.
3. **Borders recede.** One hairline where a division is needed; no nested
   double-boxing. Elevation via surface (card on page), not outlines.
4. **Same card/table/label system on every route** — Rankings, dossiers,
   match detail share spacing (8/12/16/24), header bands, and label style.
5. **Mobile is a real 390px layout**: one column, no sideways scroll,
   ≥40px touch targets, nav and live rail usable without zoom.

## The signature: the attack line

One volleyball-specific mark, used sparingly: a 3px **court-gold attack
line** under the active nav item and section headings — the 3-metre line
drawn on a light court — plus the set-column linescore grid, which is the
scoreboard language the site already earned. Nothing futuristic.
