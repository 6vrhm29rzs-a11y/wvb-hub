# Coaches, and why players don't get avatars

## Head coaches — the data is the problem, not the page

**Not derivable from anything we can reach.** Probed 2026-08-23:

| source | result |
|---|---|
| ncaa.com / ncaa-api | no coach field anywhere |
| ncaavolleyballr CSVs (MIT) | `teamseason` is stats only — no coach column |
| school coaches pages | **JavaScript-rendered.** Texas returns 409 KB with zero occurrences of "Head Coach" outside CSS; no JSON-LD, no `__INITIAL_STATE__`, no `__NEXT_DATA__` |
| school roster pages (the JSON-LD route that rescued rosters and photos) | Nebraska: 1 JSON-LD block, **0 `Person` entries** |
| `team_season_info()` in ncaavolleyballr | *does* extract a coach — but only by driving Chrome against stats.ncaa.org, which we do not fetch |

So this is a **sourced-entry** job, like the TV listings and the injury context.
`data/raw/2026/coaches_2026.json` is scaffolded with the **top 50 by our 2026
rank**, one row each, all fields null.

**Rules, same as everywhere else here:**
- Every row needs a `source` URL. A row without one **renders nothing** — never
  a guessed name (R5).
- `photo` is a **URL only**. Never downloaded, never committed. This repo is
  public and the images belong to the schools — identical to how player photos
  already work.
- Absent photo renders **initials**, never a stand-in image.

Fastest fill: hand the 50 names to a research seat with the sourcing rule, the
same way the AQ formats and injury context were done.

## Players DO get avatars — Cody, 2026-08-23

**Overruled, and correctly.** The first version of this doc refused on R5
grounds. R5 says the opposite: *"Hashing a label for **decoration** (a colour)
is fine; for a **measurement** it never is."* An avatar is decoration. The rule
was written here and then misapplied here.

What shipped is better than the bitmoji idea anyway, because it uses real data:

- **Pose = her actual position.** Setter sets (ball above the hands), pin
  swings, middle blocks, libero passes. Straight from the roster.
- **Colour = her school's own logo colour**, read out of the logo SVG rather
  than typed by hand (`scripts/crawl_team_colors.py`, 373 of 384 teams).
- **The libero is drawn in the accent colour**, because the rules require a
  contrasting jersey. That is the one thing the picture actually tells you.
- **A real photograph always wins.** The avatar appears where there is no
  photo, and full roster rows never had one at all.

**Still no faces**, and that part is a design call rather than a rule: a face
hashed out of a name is wrong about a specific real person essentially always,
and it would sit inches from the real photographs already shown for 89.9% of
projected-six slots. A stylised figure is honestly a figure. Nothing in the
drawing carries hair, skin tone or body type.

Guarded in `test_display_invariants.py`: photos take precedence, the art is
shapes only (no embedded image, text or link), and the libero keeps its
contrast.

### Drawing notes, paid for

- **Fill and stroke must not come from the same group.** The first pass set
  both on the parent, so every filled shape also got a 2.6px outline and the
  limbs fattened into the torso. The figures read as chess pieces.
- **Limbs go outside the torso silhouette**, or the pose vanishes at 26px —
  which is the only size that matters in a roster row.
- **The setter needed a ball.** Arms-up with a crossbar between the hands read
  as a trophy. A ball above the hands makes it unmistakable; the hitter got one
  too.
- `.mug` fixes 34px and a class beats a width attribute, so the roster avatar
  came out mug-sized until it was sized in the context that owns it.

## Superseded: the original refusal

### Players don't get generated avatars, and shouldn't

Cartoon likenesses of real, identifiable people — college students, most of
them private individuals — are not something this project should synthesise.
Two reasons, and the first is the project's own rule:

**R5.** "No placeholder, no illustrative stand-in, no default that stands where
a measurement belongs." A generated face sitting in a real player's row is
exactly that: it *looks* like her and is not her. The page already states the
weaker version of this — a player without a photo renders **initials**, never a
stand-in image — and an invented face is a stronger violation than a hashed
number ever was.

**They are real people.** A likeness of a named college athlete is hers. Real
photos are a different act: we store a **URL** to the picture her own school
published, which is a reference, not a fabrication or a republication.

**The coverage argument settles it anyway.** Real photos already reach **89.9%
of projected-six slots** and 290 of 348 teams. The remaining gap is
JS-rendered roster templates — a crawl problem with a known fix, not a reason
to draw faces.

## Digby does get a face

He is fictional, so none of the above applies. Drawn as **inline SVG** in
`build_hub.py` (`DIGBY_SVG`) rather than an image file or a hosted asset:

- the page is one self-contained document, and an external asset is a request
  the CSP blocks and a dependency that can rot;
- it inherits the page's own tokens (`--amber`, `--card`), so it follows the
  theme instead of fighting it;
- it costs ~700 bytes.

He appears on the summary panel, the chat launcher and the chat header. He is
private-build only, along with the rest of the Digby feature.

**A hosted design tool is the wrong shape for this**, not the wrong quality: it
produces an asset living at a URL, and this page cannot fetch one.
