# Reviewer review — Grok

**Useful outside-system discovery; correct the method comparison and proposed statistics.** RallyIQ is a relevant real reference, but the report's precise claims need dated evidence.

## Keep
- Compare an external volleyball-specific model rather than only generic machine-learning approaches.
- Test serve/receive modeling and clarify opponent adjustment.
- Preserve missing-data policies, historical cutoffs, and sample limits.

## Correct or qualify
1. **RallyIQ description:** the currently accessible methodology describes a joint penalized binomial fit for serving and receiving. Its one-pass adjustment refers to adjusted hitting, not the core fitted serve/receive model. The precise home-court constants, ridge equivalent, and validation figures quoted in the report were not located on that page. Request a dated source, rather than assuming the report invented them or that the current page never changed.
2. **Baseline experiment:** do not carry 0.0668 unchanged into a new fitting population. Preserve exact live baseline, separate population and floor changes, and recompute training-only unfloored scale for each relevant population. An interval crossing zero is not equivalence.
3. **Dig opportunity formula:** subtracting opponent attack errors and stuff blocks separately double-counts blocked attacks already recorded as attack errors. The NCAA zero-attack accounting bound is attempts minus kills minus errors; even that is not a pure defensive-success denominator.
4. **Phase claims:** aggregate opponent kill percentage and reception errors do not identify first-ball sideout. Label aggregate features as aggregate unless phase observations validate a proxy.
5. **Coverage:** a small handpicked sample with 95% server tags cannot establish nationwide coverage. Stratify by source platform, conference, venue, and feed quality. Include first-rally server, missing events, penalties, replay/score corrections, and final-score reconciliation.
6. **Avoid duplicate evidence:** one team's serve-point win is the opponent's receive-point loss for the same rally. A model may represent both sides, but cannot treat duplicated records as independent evidence.
7. **Repository limitations:** the ncaavolleyballr issue cited concerns a particular team-match CSV. It does not establish that every event dataset is missing or that future collection is impossible. Absence of 2026 in a catalog is an access/availability finding, not a permanent verdict.
8. **Tool choices:** SQLite and DuckDB serve overlapping but different operational/analytical purposes. Rejecting either wholesale is premature. Model/API prices were not all independently verified.

## Sources checked
- https://collegevolleyball.app/methodology
- https://github.com/JeffreyRStevens/ncaavolleyballr/issues/24
- https://jeffreyrstevens.github.io/ncaavolleyballr/articles/data.html
- https://s3.amazonaws.com/fs.ncaa.org/Docs/stats/Stats_Manuals/Volleyball.pdf

## Access
Summary and full Markdown read. Shared Grok chat could not be opened in the web tool. RallyIQ methodology opened; its performance claims remain self-reported, not independently reproduced here.

**Follow-up priority:** corrected competitor comparison, sound opportunity definitions, and a stratified feasibility plan.

## Scope and status
Reviewed 2026-09-26. Research only. These are Reviewer findings, not approved implementation instructions. Original submissions were preserved. Source checks were selective, not an audit of every citation or every vendor/model price. Project facts below come from the existing research packet and handoffs; the live model was not rerun during this review. Builder should independently verify code-dependent claims.
