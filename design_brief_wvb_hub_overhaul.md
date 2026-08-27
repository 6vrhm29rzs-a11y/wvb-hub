# WVB Ratings Lab — "Elite/Futuristic" Visual Overhaul
**For:** Claude Code, working in `6vrhm29rzs-a11y/wvb-hub`
**Edit target:** `output/vb_template.html` is the actual source (confirmed: `scripts/build_vb.py` reads this file directly and string-replaces `__DATA__`/`__MODEL__` into it — it is NOT generated from a separate template string). Edit it in place. Do not touch `scripts/build_hub.py`'s inline template — that's a different page (team pages), out of scope here.

## Direction
Current site is a clean, competent dashboard — sober SaaS/spreadsheet aesthetic (soft off-white, muted orange, thin borders, tiny type). Target a **live sports-intelligence command center**: dark-first, high-contrast, glowing data, motion on load, team-color-driven identity. Think broadcast-graphics package crossed with a trading terminal, not a spreadsheet.

Keep every existing data feature (sorting, search, SOS dial, tooltips, freshness banner, bracket, tracker) — this is a re-skin + hero/graphics layer, not a rebuild of the logic.

---

## 1. Color system — replace the `:root` tokens

Go dark-first as the default (not just a `prefers-color-scheme` fallback) — flip the light theme into the secondary/opt-in state:

```css
:root, :root[data-theme="dark"]{
  --bg:#04050a;
  --surface:#0c0f1a;
  --surface-2:#12162550;   /* used with backdrop-filter for glass panels */
  --surface-3:#1a2036;
  --ink:#eef1fb;
  --ink-2:#8d94b8;
  --ink-3:#565d80;
  --line:#1e2440;
  --line-2:#2a3155;
  --accent:#c6ff2e;        /* volt lime — primary signal color */
  --accent-ink:#0a0f00;
  --accent-soft:#1c2a06;
  --accent-2:#7c5cff;      /* electric violet — secondary/gradient partner */
  --court:#1de9c4;         /* neon teal, replaces muddy teal */
  --court-soft:#082e29;
  --good:#3dffa0; --bad:#ff4d6a; --warn:#ffcf40;
  --sos-lo:#161c33; --sos-hi:#7c5cff;
  --rpi-lo:#22283f; --rpi-hi:#c6ff2e;
  --glow-accent:0 0 24px rgba(198,255,46,.35);
  --glow-violet:0 0 32px rgba(124,92,255,.35);
  --shadow:0 1px 2px rgba(0,0,0,.4),0 20px 48px rgba(0,0,0,.5);
  --radius:14px;
}
:root[data-theme="light"]{ /* keep current light palette as-is, it's fine as the opt-out */ }
```

Team-color identity: `data/team_colors_2026.json` already has scraped per-team brand colors — use them. Currently `logoStyle()` hashes a hue from the team name for the fallback logo chip. Replace that with the real team primary color when available, and use it for: the row's left accent sliver on hover, the team-detail header glow, and matchcard borders in the bracket. This is a free "graphics" win — real brand color per team, not a generated hue.

## 2. Typography

Add to `<head>`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```
```css
--font-display:"Chakra Petch","Arial Narrow",sans-serif;  /* was Arial Narrow */
--font-body:"Manrope",system-ui,sans-serif;                /* was system-ui stack */
```
Chakra Petch's angular, technical letterforms carry the "elite data terminal" feel on headers/numbers; Manrope stays clean for body/table text so density doesn't suffer. Push display sizes up: `.viewhead h2` from 26px → 34px, tile values from 30px → 38px with `font-variant-numeric:tabular-nums`.

## 3. New hero section (the actual "home/landing" ask)

Right now the page opens straight into the Rankings tab with no hero — that's the boring part. Insert a hero block above `<header>`'s tab bar, inside `#view-rankings`, before `.tiles`:

**Structure:**
- Full-bleed band, `min-height: 340px`, background = layered radial gradients (`radial-gradient(circle at 15% 20%, rgba(198,255,46,.12), transparent 45%), radial-gradient(circle at 85% 60%, rgba(124,92,255,.14), transparent 50%)`) over `--bg`, plus a faint fixed volleyball-court line motif: a large, low-opacity (`opacity:.06`) SVG of a court's attack line + net line, positioned bottom-right, `mix-blend-mode: screen`.
- A thin animated horizontal scanline (`2px` tall, `--accent`, `box-shadow: var(--glow-accent)`) that drifts top-to-bottom across the hero over ~6s, looping, `opacity:.4`, `pointer-events:none` — pure ambient motion, no data meaning.
- Left side: eyebrow ("LIVE · WEEK N" with a pulsing 6px dot in `--good`), a giant headline in Chakra Petch (`clamp(32px,5vw,56px)`), and a one-line model description.
- Right side: a **"Top 3" podium strip** — three glass cards (see §5) for the current #1/#2/#3 team by Adj Score, each showing team logo (real logo if available), team name, and the Adj Score as an **animated count-up number** (JS: increment from 0 to final value over 900ms with `requestAnimationFrame`, ease-out cubic, on first paint only). Card border glows in that team's real brand color.

This single section does most of the "futuristic/elite" work — it's the first thing seen and currently the flattest part of the page.

## 4. Stat tiles → "readout" cards

`.tile` currently: white card, 3px flat accent bar, plain number. Upgrade:
- Background: `var(--surface)` at 60% opacity + `backdrop-filter: blur(16px)` (glass panel over the hero gradient bleeding through).
- Border: `1px solid var(--line)`, plus `box-shadow: var(--shadow), inset 0 1px 0 rgba(255,255,255,.04)`.
- Replace the flat left accent bar with a **corner glow**: `::before` becomes a blurred radial glow in the top-left corner (`width/height:80px`, `background:var(--accent)`, `filter:blur(30px)`, `opacity:.35`) instead of a hard stripe.
- Numbers animate count-up on tab entry (reuse the hero's count-up helper).
- Add a 4th visual element per tile: a tiny inline sparkline-style bar (5–8 bars, CSS-only, using the team's actual K/A/B split for that stat) instead of plain descriptive text where relevant — turns "Best Offense: Team X — 14.2 pts/set" into a mini stacked bar of kills/aces/blocks contribution, still built from real fields already in `MODEL`.

## 5. Reusable "glass card" component

Define once, use across hero podium, tiles, matchcards, team header:
```css
.glass{
  background:color-mix(in srgb, var(--surface) 55%, transparent);
  backdrop-filter:blur(18px) saturate(140%);
  border:1px solid var(--line-2);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  transition:border-color .2s, box-shadow .2s, transform .2s;
}
.glass:hover{border-color:var(--accent); box-shadow:var(--shadow), var(--glow-accent); transform:translateY(-2px);}
```

## 6. Rankings table — de-spreadsheet it

- Row hover: currently flat `background:var(--surface-2)`. Change to a left-edge glow bar that slides in (`::before` 3px, `background:var(--accent)`, `box-shadow:var(--glow-accent)`, `transform:scaleY(0)→scaleY(1)` on hover, transition .15s) rather than a background swap — reads as "selected signal" not "table stripe."
- Rank number for top 3 (`.seedrow` with `t.rank<=3`): render in `--accent` at 1.3× size with `text-shadow:var(--glow-accent)`.
- Add a **rank-change chevron** next to rank (needs a `prevRank` field if the pipeline can snapshot the prior build's ranks — flag this as a data need, don't fake it): ▲/▼ in `--good`/`--bad` with a brief CSS flash-in animation when a row first renders after a rank change. If there's no historical snapshot yet, skip the chevron rather than inventing motion with no signal — note this as a follow-up data task (store yesterday's rank alongside today's in the build).
- `.sos` and `.bar` gradients: already good sequential-color logic, just repoint `--sos-lo/hi` and `--rpi-lo/hi` to the new violet/lime pair above — no structural change needed.

## 7. Bracket — regional identity + real color

- `.matchcard`: switch to `.glass`, and set its border-top to a 3px bar in the **winning team's real brand color** (from `team_colors_2026.json`) instead of the flat surface border — a bracket should look like it's made of team colors, not generic UI chrome.
- `.champbox`: replace the current flat accent gradient with a layered look: base `linear-gradient(160deg, var(--accent-2), #000)` plus a radial glow behind the trophy position (`::after`, blurred, `background:var(--accent)`, `filter:blur(40px)`, `opacity:.5`, positioned behind the logo). Add a subtle confetti/particle motif as a repeating low-opacity SVG dot pattern, not literal falling confetti (keep it static/ambient, not busy).
- `.region h4` headers: add the same corner-glow micro-treatment as tiles, tinted per-region if the four regions ever get distinct colors (optional, low priority).

## 8. Motion spec (all respect `prefers-reduced-motion:reduce` — the page already has that media query, extend it to cover every new animation below)

| Element | Motion | Duration/easing |
|---|---|---|
| Hero numbers, tile numbers | count-up from 0 | 900ms ease-out-cubic, once per load |
| Hero scanline | vertical drift loop | 6s linear, infinite |
| Row hover glow bar | scaleY 0→1 | 150ms ease |
| Glass card hover | translateY(-2px) + glow-in | 200ms ease |
| Tab switch (`.view.active`) | already fades+slides 6px | keep as-is |
| Live pulse dot (hero eyebrow) | opacity pulse | 1.6s ease-in-out infinite |

## 9. Assets already in the repo to put to use (no new asset production needed)
- `data/team_colors_2026.json` — real per-team brand colors: use everywhere logo-chip hue is currently hashed.
- `MODEL.logos` (built from `data/vb_logos_seo.json` + crawled logo files) — real team logos already render via `LG()`; make sure the new glass cards and hero podium use `LG(team,'xl')`, not re-derive anything.
- `assets/digby_*.png` — Digby (the coach mascot/avatar) exists but isn't in this public template; if the write-up copy in the hero wants a face, ask before introducing Digby publicly — `docs/digby.md` states **"appear on the public site" is explicitly something Digby will not do**. Do not surface Digby art here without separately confirming that's now wanted.

## 10. Explicitly out of scope / do not invent
- No fake historical trend lines — every chart/sparkline must trace an existing field in `MODEL`/`DATA` (pts/set, K/A/B split, SOS, RPI). If a desired graphic (e.g. week-over-week rank trend) needs data the pipeline doesn't snapshot yet, add a TODO in code rather than fabricating numbers.
- No new color use beyond the two-accent system above (lime + violet) plus the existing semantic good/bad/warn — don't let "more graphics" become a rainbow.
