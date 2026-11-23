#!/usr/bin/env python3
"""Build the dated research report from measured audit results. No model promotion."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/power_research_2026-11-03'

FACTORS = [
    ('Scoring control', 'Core, already measured',
     'Set scores, rally points won / all rally points, points scored and allowed per set, margin.',
     'Estimate team strength against each opponent. Model fifth sets to 15 and ordinary sets to 25 separately; preserve deuce and match structure. A 3–0 with three 25–23 sets differs from three 25–15 sets.',
     'Compare the deployed ridge model with a legal-score set model and an ordinal 3–0 through 0–3 model on identical future matches. Test match weighting against set weighting; do not let a five-set match automatically supply five independent matches.'),
    ('Attack and opponent attack', 'Box-score counts available',
     'Kills / attempts, errors / attempts, hitting percentage, opponent equivalents.',
     'Fit offense and opponent defense together. Use attempts as the denominator for hitting, and keep scoring volume separate. Hitting percentage = kill rate − error rate, so those three columns cannot count as three independent signals.',
     'Test the attack family alone and jointly with point share; remove the whole family from the combined model to measure its added value. Use shrinkage and correlated errors, not three full-strength votes for the same kills.'),
    ('Serving and reception', 'Partial box data; richer contact data missing for 2026',
     'Aces, service errors, opponent aces; service attempts and pass grades where genuinely recorded.',
     'Serving pressure is more than aces. A tough serve that forces a predictable high ball can matter without an ace. Model net expected rally benefit against the receiving team; do not equate every non-ace serve with zero value.',
     'Start with opponent-adjusted available box measures. Promote pass grades, first-ball side-out and out-of-system frequency only with current-season verified denominators. Do not label aces/set as ace percentage.'),
    ('Side-out and transition', '2025 historical data; current coverage not established',
     'Side-out points / reception rallies; first-ball kills / reception opportunities; transition points / transition opportunities.',
     'Separate winning the point while receiving from creating points while serving. Transition conversion can expose teams that keep rallies alive but cannot finish.',
     'A serving team’s break-point rate is the complement of that opponent’s side-out rate for the same rallies: model those as one paired observation. Audit rally reconstruction before fitting; do not substitute last year’s rates for this year’s measurements.'),
    ('Block and floor defense', 'Box counts available; opportunity quality incomplete',
     'Blocks, opponent attacks, digs, opponent hitting and transition conversion.',
     'Digs per set depends on how many playable attacks a team faces. Soft blocks and controlled digs may create value absent from blocks/set. A block and the opponent attack error can be the same point.',
     'Adjust for opponent attack opportunities and avoid double counting blocked attacks as independent pieces of evidence. Contact-level models are a later step, contingent on data.'),
    ('Recent development', 'Dates and scores available',
     'Recent opponent-adjusted performance relative to the team’s longer-term level.',
     'Let sustained change move strength while one strange match mainly increases uncertainty. Separate a true improvement from an easier run of opponents.',
     'Test a dynamic latent-strength model and a small preregistered recency grid against the calibrated static baseline. Test recency with lineup changes jointly; some useful combinations may have weak individual effects.'),
    ('Lineups and availability', 'Participation available; verified status coverage limited',
     'Who played, actual participation, position/role changes, confirmed status and likely replacement.',
     'Estimate the lineup expected to play now. Compare an unavailable player with her replacement, accounting for effects on passing, setting and attack options. Avoid subtracting her value again if recent results already represent her absence.',
     'Require information known before the forecast. Backtest participation-derived features separately from verified availability news. Run healthy/current/uncertain scenarios when probabilities are not known; never infer an injury from a missing box line.'),
    ('Setting and tactical observations', 'Structured scouting needed',
     'Set location, tempo, usable attack options, out-of-system decisions, video notes and dated eyewitness observations.',
     'Assists measure a recorded outcome, not whether a set was hittable or made an attack predictable. Your Gaerte-outside / Watson-opposite observation is a role-change hypothesis, not an automatic numerical bonus.',
     'Record observer, match, timestamp, role, observation and confidence. Check agreement between observers and whether the observation predicts later results beyond existing stats. Unverified board discussion remains a lead to investigate.'),
    ('Home, travel and altitude', 'Home/neutral partially resolved; exact travel/elevation incomplete',
     'Verified venue, home/away/neutral, rest, recent workload, venue elevation and visitor elevation change.',
     'Estimate neutral-court ability separately from the conditions of one match. BYU or Colorado home/road differences also reflect who they played; altitude is not established by the raw split.',
     'Fit venue effects after opponent adjustment, pooling teams with thin samples. Use real venue coordinates/elevation, not a state centroid as precise travel distance. Test home × elevation and rest × workload together. Unknown venue stays unknown.'),
    ('Matchup style and rotations', 'Aggregate styles possible; live rotation data incomplete',
     'Serve pressure versus reception; attacker distribution versus block; setter front/back row; rotation-specific side-out.',
     'A team can be stronger overall yet face an awkward opponent. Use matchup interactions in the forecast while preserving a standardized neutral-opponent strength ranking.',
     'Fit a small regularized interaction set, compare it with the same main effects, and validate on unseen opponents. Sparse rotations need partial pooling; do not turn one bad rotation into a permanent team-wide penalty.'),
    ('Consistency, floor and ceiling', 'Descriptive distributions available',
     'Median, interquartile range and tails of opponent-adjusted match residuals; actual margin and hitting distributions alongside them.',
     'Separate uncertainty about strength from genuine match-to-match volatility. A stable average team is not automatically stronger than an excellent volatile team.',
     'Test whether estimated volatility improves upset and score-distribution forecasts. Raw standard deviation alone did not earn a weight in the earlier ballot experiment; that does not settle richer volatility models.'),
    ('Prior seasons, personnel and conference', 'Available with historical limitations',
     'Prior team ability, returning and transfer production, participation, season-correct conference membership.',
     'Use preseason information as a shrinking starting estimate. Unknown newcomers increase uncertainty; they do not deserve invented production or a generic zero-ability rating. Learn conference pooling from the schedule graph, not conference reputation.',
     'Use real archived preseason rosters or a clearly separate prior-team-only baseline. Do not choose 2025 roster membership by who eventually appeared in 2025. Check influence and calibration as current-season evidence accumulates.'),
    ('Polls and résumé', 'Keep separate outputs',
     'AVCA, VolleyTalk, record, best wins, losses, RPI and selection evidence.',
     'These answer valuable but different questions. A ballot can reflect earned results and judgment; power estimates should answer how teams would perform under stated conditions.',
     'Keep polls as dated comparison benchmarks. If a past résumé feature is tested for prediction, disclose it and its incremental benefit. Do not let a poll become both the target and the claimed independent validation of power.'),
]

SOURCES = [
    ('Powers, Stancil & Consiglio (2024): NCAA women’s volleyball Points Gained',
     'https://arxiv.org/html/2402.01083v1',
     'Directly relevant college-women research uses contact-by-contact point value and opponent adjustment. It motivates a richer skills layer, but requires charted contacts we have not established for 2026. Its authors also identify attribution and outcome-dependent schedule-adjustment limitations; this is not proof of an improved team forecast for our data.'),
    ('Millán-Sánchez et al. (2020): setting, first-tempo availability and side-out',
     'https://pmc.ncbi.nlm.nih.gov/articles/PMC7504473/',
     'The study examines setter movement, reception, first-tempo availability and rotations, including 663 women’s side-outs. It supports measuring setting in context. Its small elite-European sample does not justify a numerical NCAA setter-quality weight.'),
    ('Egidi & Ntzoufras (2020): a volleyball-specific hierarchical score model',
     'https://leoegidi.github.io/paper/Egidi_Ntzoufras_2020_final_published.pdf',
     'Models set winners, losing-team points and extra deuce points with team and home effects. Useful structure for legal score distributions. Dynamic ability did not improve fit in their Italian men’s sample, so dynamics is a hypothesis to test here, not an assumed upgrade.'),
    ('Gabrio (2019/2021): hierarchical attack and defense models',
     'https://arxiv.org/html/1911.08791v1',
     'Explores attack/defense structure and richer covariates using Italian women’s volleyball. For our pre-match use, any skill input must come from previous matches; actual statistics from the match being predicted cannot enter the forecast.'),
    ('Tenni, Zanco & Szczecinski (2024): evaluation of FIVB ranking',
     'https://arxiv.org/html/2408.01603v1',
     'Evaluates an ordinal match-score rating, finding benefits from a home effect and problems with competition-importance weighting in its data. This argues for testing weights against predictive performance rather than assuming a prestigious match deserves more power-rating influence.'),
    ('FIVB: official description of the ranking approach',
     'https://www.fivb.com/fivb-launches-advanced-world-ranking-system/',
     'An official example of updating a rating relative to expected match outcomes. Its international-ranking purpose and competition weights should not be copied untested into NCAA strength estimation.'),
    ('Guo et al. (2017): probability calibration',
     'https://proceedings.mlr.press/v70/guo17a.html',
     'Shows the usefulness of a simple confidence-calibration comparator in other prediction settings. Our volleyball result is computed from our own archived forecasts; their paper is not evidence that our ranking itself improves.'),
    ('Naimi & Balzer (2018): combining predictions with stacking',
     'https://pmc.ncbi.nlm.nih.gov/articles/PMC6089257/',
     'Explains fitting a combination using out-of-fold predictions. For this project, time-ordered folds replace random folds so a future match cannot teach a past forecast.'),
    ('Cawley & Talbot (2010): overfitting model selection',
     'https://jmlr.org/papers/v11/cawley10a.html',
     'Repeatedly selecting models on the same finite validation data can overfit the evaluation itself. This is why many 2026 experiments do not become independent confirmations merely because their individual weights were trained on 2025.'),
]


def main():
    r = json.loads((OUT/'calibration_audit.json').read_text())
    rev = json.loads((OUT/'reviewer_deployed_audit.json').read_text())
    cur = json.loads((ROOT/'Cody/data/power_candidate/v2so_preview.json').read_text())
    m = r['years']['2026']['metrics']
    deployed = r['deployed_comparison']['metrics_2026']
    comparisons = [
        ('Original test baseline',m['harness_base']),
        ('Site formula, replayed on the same weeks',deployed['deployed_mapping_replayed']),
        ('Original baseline + confidence correction',m['calibration_only']),
        ('Original baseline + Elo + hitting',m['frozen_three_model_stack']),
        ('Site formula + confidence correction',deployed['deployed_plus_calibration']),
        ('Site formula + Elo + hitting, weights fitted together',deployed['deployed_plus_elo_hitting_stack'])]
    rows = ''.join('<tr><th scope="row">%s</th><td>%.5f</td><td>%.5f</td><td>%.2f%%</td></tr>' %
                   (html.escape(label),x['log_loss'],x['brier'],100*x['accuracy']) for label,x in comparisons)
    features = ''.join('<details><summary>%s <span>%s</span></summary><p><b>Look at:</b> %s</p><p>%s</p><p><b>How to test it:</b> %s</p></details>' % tuple(html.escape(t) for t in f) for f in FACTORS)
    refs = ''.join('<li><a href="%s">%s</a><p>%s</p></li>' % (html.escape(url,quote=True),html.escape(title),html.escape(note)) for title,url,note in SOURCES)
    diff = r['years']['2026']['stack_minus_calibration']
    bs = r['years']['2026']['calibration_minus_base']
    positive = -bs['mean_log_loss_difference']
    new = r['deployed_comparison']['stack_minus_calibration_2026']
    ratio = positive/m['harness_base']['log_loss']*100
    prior = rev['seasons']['2025']['prior_observation_by_week'][0]
    verdict = ('The original three-model combination adds %.5f log loss versus confidence correction alone (95%% week-block interval %+.5f to %+.5f). '
               'The interval includes zero: these extra model inputs have not established an incremental improvement.' %
               (diff['mean_log_loss_difference'],diff['week_95_ci'][0],diff['week_95_ci'][1]))
    diagram = '''<div class="flow"><div>Actual match data<small>Scores · attacks · serves · players</small></div><b>→</b><div>Opponent & context adjustment<small>What happened, against whom, with which lineup?</small></div><b>→</b><div>Joint skill estimates<small>Shared information counted once</small></div><b>→</b><div>Strength + matchup forecast<small>Neutral ranking · win chance · uncertainty</small></div></div>'''
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Building a better volleyball power model · November 3, 2026</title>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#152b42;background:#f5f7fa;font-size:17px;line-height:1.65}*{box-sizing:border-box}body{margin:0}main{max-width:1080px;margin:auto;padding:40px 24px 80px}h1{font-size:clamp(2rem,5vw,3.6rem);line-height:1.08;letter-spacing:-.045em;max-width:850px}h2{font-size:1.65rem;line-height:1.25;margin:42px 0 16px}p{max-width:900px}a{color:#075aaa}small,.muted{color:#53687d}.eyebrow{color:#1f608c;font-weight:700;letter-spacing:.09em;font-size:.75rem;text-transform:uppercase}.lead{font-size:1.2rem}section,.card{background:white;border:1px solid #dce4ec;border-radius:16px;padding:24px;margin:20px 0}.callout{background:#e7f2fa;border-left:5px solid #1f77b5;padding:18px 22px;border-radius:6px}.note{background:#fff5df;border-left-color:#c28a20}.flow{display:flex;align-items:center;gap:10px;margin:24px 0}.flow div{flex:1;background:#173e61;color:white;border-radius:12px;padding:18px;font-weight:650;line-height:1.35}.flow small{display:block;color:#d9e7f3;font-weight:400;font-size:.8rem;margin-top:9px}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.92rem}th,td{padding:13px 10px;border-bottom:1px solid #e1e7ec;text-align:right;white-space:nowrap}th:first-child{text-align:left;white-space:normal;min-width:190px}thead{background:#edf3f8}tbody th{font-weight:500}details{border-top:1px solid #dce4ec;padding:16px 0}summary{font-weight:700;cursor:pointer;line-height:1.5}summary span{display:block;font-size:.82rem;font-weight:450;color:#53728d;margin-left:19px}details p{padding-left:19px}li{padding:6px 0}li p{font-size:.94rem;margin:4px 0 15px}.pill{display:inline-block;background:#eaf3e9;color:#305c37;border-radius:20px;padding:5px 13px;font-size:.8rem}.columns{display:grid;grid-template-columns:1fr 1fr;gap:16px}.columns .card{margin:0}.big{font-size:2.3rem;font-weight:750;color:#195b88;line-height:1.1}.metric-label{font-size:.85rem;color:#53687d}.barrow{margin:16px 0}.track{height:16px;background:#e7edf2;border-radius:20px;overflow:hidden;margin-top:7px}.fill{height:100%;background:#337dae;border-radius:20px}footer{font-size:.85rem;color:#53687d;margin-top:35px}@media(max-width:650px){main{padding:24px 16px}.flow{flex-direction:column;align-items:stretch}.flow>b{text-align:center;transform:rotate(90deg)}.columns{grid-template-columns:1fr}section{padding:18px}th,td{padding:10px 7px;font-size:.8rem}}@media print{details>*{display:block}main{max-width:none}section{break-inside:avoid}.flow{display:block}}
</style><main>
<div class="eyebrow">Research review · November 3, 2026 · Archived data through November 3</div>
<h1>More volleyball knowledge.<br>Weights that earn their place.</h1>
<p class="lead">A comprehensive strength model should combine distinct information about how a team wins points, who is playing, and the conditions of the matchup. The weights need to improve future predictions together, after overlapping statistics and uncertainty are accounted for.</p>
<span class="pill">Research and independent review complete</span>
<p class="muted">This pass added evaluation tools and this report. It did not replace the local site’s power rankings, ballot, injury judgments or bracket model.</p>
DIAGRAM
<h2>The central finding</h2>
<div class="callout"><b>The saved ensemble improvement is largely a confidence-calibration result.</b><p>VERDICT</p></div>
<div class="columns"><div class="card"><div class="big">N_MATCHES</div><div class="metric-label">same 2026 matches in the comparison</div><p>Team estimates were rebuilt using earlier weeks. This is a historical replay, not a claim that all predictions were issued live before those matches.</p></div><div class="card"><div class="big">REL_GAIN%</div><div class="metric-label">lower log loss from correcting the original baseline’s confidence</div><p>This does not mean REL_GAIN percentage points more winners picked. That positive scalar adjustment leaves every original favorite and the probability ordering unchanged.</p></div></div>
<section><h2 style="margin-top:0">What the comparison actually says</h2><p><b>Lower log loss and Brier score are better.</b> They measure the quality of win probabilities, including how severely a model is wrong when it is very confident. Winner accuracy is shown separately.</p><div class="table"><table><thead><tr><th>Model</th><th>Log loss ↓</th><th>Brier ↓</th><th>Winners picked</th></tr></thead><tbody>ROWS</tbody></table></div>
<p>The original experiment compared against an independent-set, best-of-five calculation. The site uses a different, season- and sample-aware probability mapping. An independent replay reproduced the original baseline to numerical precision and applied the actual site mapping on the same weekly snapshots.</p>
<p>The original stack does improve on the replayed site formula: its week-block interval for log-loss change is −0.00884 to −0.00140. But the simpler confidence correction to the original baseline performs slightly better still. Refitting the combination around the site formula also fails to establish a useful extra-information benefit: the extra Elo/hitting inputs increase log loss by DEPLOYED_DIFF versus calibrating that formula alone.</p>
<p class="muted">The added calibration and combination coefficients were fitted on 2025, not selected from these 2026 outcomes. Weekly team-strength estimates use earlier matches from the season being forecast. Nonetheless, 2026 has already influenced earlier model-development decisions; these are exploratory comparisons, not a fresh independent confirmation. The 2025 site mapping used 2025 outcomes for its own fit, so its replay is not reported as validation.</p>
</section>
<h2>What belongs in the combined system</h2>
<p>Use a small number of <b>skill families</b> with several useful measurements inside each. Fit the families jointly, with shrinkage that reduces unstable coefficients. Evaluate plausible interactions as bundles: a serving metric may matter most when paired with the opponent’s reception, even if its standalone average effect is weak.</p>
<section>FEATURES</section>
<h2>How the weights should be learned</h2>
<section><ol>
<li><b>Define the question first.</b> Power: expected performance on a neutral floor with the current expected lineup. Match forecast: add this opponent, venue and available players. Résumé: maintain a separate earned-results view.</li>
<li><b>Build every training example as it existed before the match.</b> Previous results, box scores, roster, lineup reports, conference and venue records must carry an effective date and a known-at timestamp. A retrospective correction is useful for research, but it does not prove what a live forecast knew.</li>
<li><b>Adjust the relevant skill against the relevant opponent skill.</b> Attack against defensive resistance; serving against reception. Avoid a universal multiplier based on an opponent’s final rank. Refit the schedule graph at each historical cutoff.</li>
<li><b>Handle dependence explicitly.</b> Kills, hitting, earned points and rally share overlap. Use a joint likelihood with residual covariance, or regularized group-level predictions. Compare both against the simpler baseline. Do not treat multiple statistics from one set as independent matches.</li>
<li><b>Fit and tune only inside earlier time windows.</b> Use rolling outer weeks or seasons for evaluation, with model selection and calibration in inner earlier windows. Stack predictions that were themselves made without their target match. Fit transformations and missing-data handling within each training window.</li>
<li><b>Use two tests of value.</b> Add a family to the baseline, then remove it from the full combination. Test meaningful interactions together. A zero coefficient in one specification means no demonstrated extra value in that specification, not that the skill is irrelevant.</li>
<li><b>Measure the whole forecast.</b> Match log loss and Brier score; calibration; six match-score outcomes; margin error; interval coverage. Report performance for pre-match top-25 contests, close matches, neutral venues, season phases and conference-crossing matches without tuning to those slices afterward.</li>
<li><b>Freeze finalists for future matches.</b> Timestamp predictions and inputs before first serve; score every eligible match, including failures and missing-data cases. Keep the exact deployed model as one comparator. A frozen future period must remain unused until scoring; merely calling reused 2026 data “confirmation” is insufficient.</li>
</ol><p>Weights do not need to sum to 100%. A regression coefficient is conditional on the scale and other inputs. Prefer reporting how a measured feature changes a forecast, with uncertainty, over a misleading “30% hitting / 20% serving” pie chart.</p></section>
<h2>Problems to fix before claiming a stronger ranking</h2>
<div class="callout note"><b>Historical information timing is the main trust issue.</b><p>The 2025 prior uses 2024 production, but chooses returning-player membership from full-season 2025 participation. At the first scored week, PRIOR_UNSEEN of PRIOR_TOTAL included players had not yet appeared. Some could have been known from actual preseason rosters, but this reconstruction does not establish that. Use an archived roster, a separately labelled hindsight analysis, or a prior-team-only fallback.</p></div>
<section><ul>
<li><b>Season-specific structure:</b> the candidate conference map comes from 2026 even in 2025 replay. Audit true conference moves and aliases separately before scoring that component.</li>
<li><b>Repeated model selection:</b> numerous saved experiments have checked 2026 and used it as an adoption gate. Confidence intervals within one experiment do not include all that selection uncertainty.</li>
<li><b>Meta-model leakage:</b> leave-one-week-out stacking is not forward-only. Later weeks’ base forecasts can already depend on outcomes in the held-out earlier week. Parameter selection must also be nested.</li>
<li><b>Incomplete provenance:</b> input hashes must include player priors, rosters, venue and conference files, corrections and code. Four game/box hashes alone are insufficient.</li>
<li><b>Source labels:</b> the live probability artifact still names an older calibration receipt while coefficients are supplied by a newer one. Display and test the exact version and coefficient source.</li>
<li><b>Data quality before extra precision:</b> preserve final-beats-nonfinal deduplication, legal completed sets, verified team attribution and missing values. Box-score completeness and correct home/neutral status affect what the model is actually learning.</li>
</ul><p>These do not establish that all current rankings are wrong. They limit how confidently we can say one model has demonstrated an improvement over another.</p></section>
<h2>The build order I recommend</h2>
<section><ol>
<li><b>First: repair the evaluation contract.</b> Exact production comparator, time-correct historical inputs, one frozen data manifest, and a clean forward evaluation. Keep calibration-only in every comparison.</li>
<li><b>Next: one combined box-score candidate.</b> Scoring control plus jointly estimated attack/defense and serve/receive families, with opponent adjustment and correlated-stat safeguards. Compare the whole bundle and family removals; do not add unproven fixed weights.</li>
<li><b>Then: current team state.</b> Fit recency and participation changes together. Add dated, verified availability scenarios and rest/workload with genuine venue context. Check that a prior or an absence is not counted twice.</li>
<li><b>Finally: the richer volleyball layer.</b> Acquire authorized current contact/rotation data or structured charting. Test side-out, transition, passing quality, setter options and matchup interactions. This is the most direct route to capturing what the box score misses.</li>
</ol></section>
<h2>What you should see on the local site</h2>
<p><b>Keep actual statistics visible:</b> scoring/allowed points per set, actual hitting percentages, win rate, recent set scores and margins, plus best wins and losses. Alongside them show neutral-court strength with an uncertainty band, the recent trend, the current-lineup scenario, and a short explanation of what moved the estimate. A matchup panel can show win and 3–0/3–1/3–2 probabilities. Unmeasured setting quality stays a dated scouting note, not a fabricated statistic.</p>
<p>For your BYU concern, show opponent-adjusted dominance and neutral/road evidence next to the lack of elite wins; let uncertainty reflect the untested schedule. For Kentucky, mark the role-change date and evaluate later matches against expectations without assigning a “smart adjustment” bonus. For Oregon, show the actual distribution of margins and scores alongside opponent-adjusted consistency, so repeated narrow wins remain visible.</p>
<h2>Research sources and what they support</h2><section><ol>REFS</ol></section>
<h2>Work completed in this pass</h2>
<section><p>Added a reproducible calibration-only audit and exploratory comparison using the exact deployed mapping; saved per-match forecasts, input hashes, paired match/week intervals and an independent review. Two numerical controls passed: recovery of a known calibration error with side-reversal symmetry, and a zero-difference comparison of identical predictions. The independent reviewer solved the calibration equation separately and reproduced the baseline forecasts.</p>
<p><b>Live-model changes: none.</b> No new ratings were promoted, no production data was crawled, no bracket repair was bundled into this task, and no git commit or push was performed. The richer factors above are a researched implementation plan; their combined accuracy has not yet been established.</p>
<p><a href="power-research-evidence-2026-11-03.json">Download numerical evidence</a> · <a href="ballot-review-2026-11-01.html#view=overview">Return to the ballot dashboard</a></p></section>
<footer>Local research report · source candidate CANDIDATE · 2026 comparison: FIRST_DAY through LAST_DAY · see saved audit manifests for exact input hashes. No point estimates are invented to fill missing evidence.</footer></main></html>'''
    replace = {'DIAGRAM':diagram,'VERDICT':html.escape(verdict),'N_MATCHES':format(m['harness_base']['n'],','),
               'REL_GAIN':'%.2f' % ratio,'ROWS':rows,'FEATURES':features,'REFS':refs,
               'DEPLOYED_DIFF':'%.5f' % new['mean_log_loss_difference'],
               'PRIOR_UNSEEN':str(prior['prior_players_not_yet_observed']),'PRIOR_TOTAL':format(prior['prior_players'],','),
               'CANDIDATE':html.escape(cur['version']), 'FIRST_DAY':r['years']['2026']['first_day'],
               'LAST_DAY':r['years']['2026']['last_day']}
    for k,v in replace.items():
        page=page.replace(k,v)
    (OUT/'report.html').write_text(page)
    (ROOT/'Cody/power-research-2026-11-03.html').write_text(page)
    (ROOT/'Cody/power-research-evidence-2026-11-03.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
    registry = {'status':'RESEARCH_PLAN_NOT_DEPLOYED','date':'2026-11-03',
                'families':[dict(zip(['name','data_status','measurements','mechanism','validation'],f)) for f in FACTORS],
                'sources':[{'title':t,'url':u,'supports':n} for t,u,n in SOURCES]}
    (OUT/'factor_research.json').write_text(json.dumps(registry,indent=2)+'\n')
    print('Wrote local report, numerical evidence, and factor research registry.')


if __name__ == '__main__':
    main()
