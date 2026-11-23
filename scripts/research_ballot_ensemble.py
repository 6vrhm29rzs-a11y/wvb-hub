#!/usr/bin/env python3
"""Research only: chronological opponent adjustment and fitted ranking stack.

Uses archived games only; never crawls or changes production ratings. Requires
numpy and scipy. Weeks are frozen BEFORE any scored match. 2025 trains the
stack; 2026 outcomes never fit its weights. No inferred health/setting scores.
"""
import collections
import datetime as dt
import html
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.sparse import coo_matrix, vstack, eye
from scipy.sparse.linalg import lsqr
from scipy.special import expit
from scipy.stats import rankdata

import bakeoff_2025 as B

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'opponent_adjusted_2026-11-01'
LAYERS = ['points', 'hitting', 'earned', 'aces', 'blocks']
COUNT_FIELDS = {'kills':'kills', 'attack_errors':'attackErrors',
                'attack_attempts':'attackAttempts', 'assists':'assists',
                'digs':'digs', 'service_errors':'serviceErrors',
                'block_solos':'blockSolos', 'block_assists':'blockAssists'}
METRICS = LAYERS + list(COUNT_FIELDS)
FEATURES = ['rpi', 'points', 'hitting', 'earned', 'aces', 'blocks',
            'results_bt', 'recent_points', 'consistency']


def number(box, name):
    try:
        return float(box[name])
    except (KeyError, TypeError, ValueError):
        return None


def values(match):
    """Missing fields stay missing. Scoreboard rally points != earned points."""
    result = []
    for t in match['teams']:
        b = t['box'] or {}
        n = t['sets']
        k, e, a = [number(b, x) for x in ['kills', 'attackErrors', 'attackAttempts']]
        ace, solo, assist = [number(b, x) for x in ['serviceAces', 'blockSolos', 'blockAssists']]
        bs = solo + assist / 2 if solo is not None and assist is not None else None
        # Cross-check the score against the box and the number of sets.
        bp, ns = number(b, 'points'), number(b, 'gamesPlayed')
        valid = n >= 3 and t['points_for'] > 0 and t['points_against'] > 0
        if match.get('expected_sets') is not None and n != match['expected_sets']:
            valid = False
        if bp is not None and bp != t['points_for']:
            valid = False
        if ns is not None and ns != n:
            valid = False
        rate_n = ns if ns is not None else n
        valid_rate = rate_n >= 3
        result.append({
            'points': t['points_for'] / n if valid else None,
            'hitting': (k-e)/a if k is not None and e is not None and a and a > 0 else None,
            'earned': (k+ace+bs)/rate_n if k is not None and ace is not None and bs is not None and valid_rate else None,
            'aces': ace/rate_n if ace is not None and valid_rate else None,
            'blocks': bs/rate_n if bs is not None and valid_rate else None})
        for metric,field in COUNT_FIELDS.items():
            count = number(b,field)
            result[-1][metric] = count/rate_n if count is not None and valid_rate else None
    return result


def load(year):
    B.SEASON = year
    B.RAW = str(ROOT / 'data' / 'raw' / str(year))
    matches, teams = B.load()
    from gamelog import load_games_jsonl
    import season_counts as SC
    corrections = SC.corrections(year)
    source = {str(g['game_id']):SC.apply_correction(g,corrections)
              for g in load_games_jsonl(str(Path(B.RAW)/'games.jsonl'))}
    swaps = SC.box_team_swaps(year)
    matches = sorted([m for m in matches if m['date']], key=lambda m: (m['date'], str(m['game_id'])))
    for m in matches:
        g = source[str(m['game_id'])]
        ts = g['teams']
        won = [t.get('sets_won') for t in ts]
        m['expected_sets'] = sum(int(v) for v in won) if all(v is not None for v in won) else None
        m['set_scores'] = {}
        for t in ts:
            k = B.norm(t['name_short'])
            own,opp = ('home','visit') if t.get('is_home') else ('visit','home')
            m['set_scores'][k] = [[v.get(own),v.get(opp)] for v in g.get('linescores',[])]
        m['sets_won'] = {B.norm(t['name_short']):t.get('sets_won') for t in ts}
        if str(m['game_id']) in swaps:
            by_id = {str(t['team_id']):B.norm(t['name_short']) for t in ts}
            boxes = {t['key']:t['box'] for t in m['teams']}
            for original,corrected in swaps[str(m['game_id'])].items():
                target=next((t for t in m['teams'] if t['key']==by_id.get(corrected)),None)
                if target is not None:
                    target['box']=boxes.get(by_id.get(original))
        m['values'] = values(m)
    return matches, sorted(teams)


def offdef(matches, keys, metric, ridge=3.0):
    """Equal-match ridge: y_ij=mean+attack_i-defense_j. Neutral reference.

    Home/neutral is deliberately omitted: historical venue identity is missing.
    Explicit L2 penalty (not an unpenalized iterative pseudo-count update).
    """
    ix = {k: i for i, k in enumerate(keys)}
    n = len(keys)
    rows, cols, data, ys = [], [], [], []
    for m in matches:
        for side in [0, 1]:
            v = m['values'][side][metric]
            if v is None:
                continue
            r = len(ys)
            i, j = [ix[m['teams'][s]['key']] for s in [side, 1-side]]
            rows.extend([r, r]); cols.extend([i, n+j]); data.extend([1., -1.])
            ys.append(v)
    if not ys:
        raise ValueError('No observations for ' + metric)
    mean = float(np.mean(ys))
    x = coo_matrix((data, (rows, cols)), shape=(len(ys), 2*n)).tocsr()
    design = vstack([x, np.sqrt(ridge)*eye(2*n)], format='csr')
    coef = lsqr(design, np.r_[np.asarray(ys)-mean, np.zeros(2*n)], atol=1e-9, btol=1e-9)[0]
    return {'mean': mean, 'off': coef[:n], 'def': coef[n:], 'count': len(ys)}


def bt(matches, keys):
    ix = {k: i for i, k in enumerate(keys)}
    a = np.array([ix[m['teams'][0]['key']] for m in matches])
    b = np.array([ix[m['teams'][1]['key']] for m in matches])
    y = np.array([float(m['winner_idx'] == 0) for m in matches])
    def objective(c):
        z = c[a]-c[b]
        error = expit(z)-y
        grad = np.bincount(a, weights=error, minlength=len(keys))-np.bincount(b, weights=error, minlength=len(keys))+c
        return float(np.sum(np.logaddexp(0, z)-y*z)+.5*np.dot(c,c)), grad
    return minimize(objective, np.zeros(len(keys)), jac=True, method='L-BFGS-B').x


def snapshot(matches, keys):
    ix = {k: i for i, k in enumerate(keys)}
    models = {metric: offdef(matches, keys, metric) for metric in METRICS}
    rpi = B.rpi_from_games([(m['teams'][m['winner_idx']]['key'],
                           m['teams'][1-m['winner_idx']]['key'], str(m['game_id'])) for m in matches], keys)
    raw = np.empty((len(keys), len(FEATURES)))
    raw[:, 0] = [rpi[k]['rpi'] for k in keys]
    for col, metric in enumerate(LAYERS, 1):
        raw[:, col] = models[metric]['off']+models[metric]['def']
    raw[:, 6] = bt(matches, keys)
    recent = collections.defaultdict(list)
    all_perfs = collections.defaultdict(list)
    cutoff = max(m['date'] for m in matches)-dt.timedelta(days=29)
    for m in matches:
        v = [m['values'][s]['points'] for s in [0, 1]]
        if None in v:
            continue
        i, j = [ix[t['key']] for t in m['teams']]
        # Full-window descriptive performances, not claimed pregame surprises.
        perf = v[0]-v[1]+raw[j, 1]
        all_perfs[i].append(perf)
        all_perfs[j].append(v[1]-v[0]+raw[i, 1])
        if m['date'] >= cutoff:
            recent[i].append(perf)
            recent[j].append(v[1]-v[0]+raw[i, 1])
    coverage = collections.Counter(t['key'] for m in matches for t in m['teams'])
    for i in range(len(keys)):
        raw[i, 7] = np.mean(recent[i]) if recent[i] else raw[i, 1]
        # Missing variability is a league prior INSIDE the model only, never a displayed stat.
        raw[i, 8] = -np.std(all_perfs[i], ddof=1) if len(all_perfs[i]) >= 2 else np.nan
    raw[np.isnan(raw[:, 8]), 8] = np.nanmedian(raw[:, 8])
    active = np.array([coverage[k] > 0 for k in keys])
    scale = raw[active].std(axis=0)
    scale[scale < 1e-10] = 1
    z = (raw-raw[active].mean(axis=0))/scale
    unadj = np.full(len(keys), np.nan)
    raw_margins = collections.defaultdict(list)
    for g in matches:
        v = [g['values'][side]['points'] for side in [0,1]]
        if None not in v:
            for side in [0,1]:
                raw_margins[g['teams'][side]['key']].append(v[side]-v[1-side])
    for i,k in enumerate(keys):
        margins = raw_margins[k]
        if margins:
            unadj[i] = np.mean(margins)
    mean_unadj = np.nanmean(unadj[active])
    sd_unadj = np.nanstd(unadj[active])
    unadj[np.isnan(unadj)] = mean_unadj
    z_unadj = z.copy()
    z_unadj[:,1] = (unadj-mean_unadj)/(sd_unadj or 1.)
    return {'keys': keys, 'ix': ix, 'models': models, 'raw': raw, 'z': z, 'z_unadj':z_unadj,
            'rpi': rpi, 'coverage': coverage}


def weekly_rows(matches, keys):
    start = min(m['date'] for m in matches)+dt.timedelta(days=21)
    last = max(m['date'] for m in matches)
    rows = []
    while start <= last:
        past = [m for m in matches if m['date'] < start]
        future = [m for m in matches if start <= m['date'] < start+dt.timedelta(days=7)]
        if future:
            s = snapshot(past, keys)
            for m in future:
                a, b = [s['ix'][t['key']] for t in m['teams']]
                if min(s['coverage'][t['key']] for t in m['teams']) < 3:
                    continue
                rows.append({'date': str(m['date']), 'snapshot_before': str(start),
                             'id': str(m['game_id']), 'x': (s['z'][a]-s['z'][b]).tolist(),
                             'x_unadj':(s['z_unadj'][a]-s['z_unadj'][b]).tolist(),
                             'y': int(m['winner_idx'] == 0)})
        start += dt.timedelta(days=7)
    return rows


def fit(rows, columns, penalty):
    x = np.asarray([r['x'] for r in rows])[:, columns]
    y = np.asarray([r['y'] for r in rows])
    def objective(w):
        a = np.einsum('ij,j->i',x,w)
        return float(np.sum(np.logaddexp(0,a)-y*a)+penalty*np.dot(w,w)/2), np.einsum('ij,i->j',x,expit(a)-y)+penalty*w
    result = minimize(objective, np.ones(len(columns))/len(columns), jac=True,
                      bounds=[(0,None)]*len(columns), method='L-BFGS-B',
                      options={'ftol': 1e-12, 'maxiter': 1000})
    if not result.success:
        raise RuntimeError(result.message)
    w = np.zeros(len(FEATURES)); w[columns] = result.x
    return w


def predictions(rows, w):
    return expit(np.einsum('ij,j->i',np.asarray([r['x'] for r in rows]),w))


def scores(y, p):
    pos, neg = int(sum(y)), int(len(y)-sum(y))
    auc = (float(rankdata(p)[y == 1].sum())-pos*(pos+1)/2)/(pos*neg)
    p = np.clip(p, 1e-10, 1-1e-10)
    return {'n': len(y), 'auc': auc, 'brier': float(np.mean((p-y)**2)),
            'log_loss': float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))}


def compare(rows, base, extra, baseline_rows=None):
    y = np.asarray([r['y'] for r in rows])
    pb, pe = predictions(baseline_rows if baseline_rows is not None else rows, base), predictions(rows, extra)
    dates = sorted(set(r['date'] for r in rows))
    grouped = [np.array([i for i,r in enumerate(rows) if r['date']==day]) for day in dates]
    rng = np.random.default_rng(20261101)
    deltas = []
    for _ in range(600):
        ix = np.concatenate([grouped[i] for i in rng.integers(0,len(dates),len(dates))])
        deltas.append([scores(y[ix],pe[ix])['auc']-scores(y[ix],pb[ix])['auc'],
                       float(np.mean((pe[ix]-y[ix])**2-(pb[ix]-y[ix])**2))])
    return {'baseline': scores(y,pb), 'combined': scores(y,pe),
            'auc_delta_95_ci': np.quantile(np.array(deltas)[:,0],[.025,.975]).tolist(),
            'brier_delta_95_ci': np.quantile(np.array(deltas)[:,1],[.025,.975]).tolist()}


def tune(rows, cols):
    dates = sorted(set(r['date'] for r in rows))
    boundary = dates[int(len(dates)*.75)]
    train = [r for r in rows if r['date'] < boundary]
    valid = [r for r in rows if r['date'] >= boundary]
    candidates = []
    for penalty in [1., 10., 100.]:
        w = fit(train, cols, penalty)
        score = scores(np.asarray([r['y'] for r in valid]),predictions(valid,w))
        candidates.append((score['log_loss'],penalty))
    penalty = min(candidates)[1]
    return fit(rows,cols,penalty), penalty


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    seasons = {}
    for year in [2025,2026]:
        m, keys = load(year)
        print('Loaded',year,len(m),flush=True)
        cache = OUT / ('weekly_%d.json' % year)
        fingerprint = hashlib.sha256(Path(__file__).read_bytes()+json.dumps(m,default=str,sort_keys=True).encode()).hexdigest()
        cached = json.loads(cache.read_text()) if cache.exists() else {}
        if isinstance(cached,dict) and cached.get('fingerprint')==fingerprint:
            rows = cached['rows']
        else:
            rows = weekly_rows(m,keys)
            cache.write_text(json.dumps({'fingerprint':fingerprint,'rows':rows}))
        seasons[year] = (m,keys,rows)
        print('Pregame rows',year,len(rows),flush=True)
    trainrows = seasons[2025][2]
    dates = sorted(set(r['date'] for r in trainrows))
    boundary = dates[int(len(dates)*.65)]
    early = [r for r in trainrows if r['date'] < boundary]
    late = [r for r in trainrows if r['date'] >= boundary]
    basecols, extracols = [0,1], list(range(len(FEATURES)))
    base_early, _ = tune(early,basecols)
    extra_early, _ = tune(early,extracols)
    base, basepen = tune(trainrows,basecols)
    extra, extrapen = tune(trainrows,extracols)
    unadjrows = [{**r,'x':r['x_unadj']} for r in trainrows]
    unadj2026 = [{**r,'x':r['x_unadj']} for r in seasons[2026][2]]
    unadj, _ = tune(unadjrows,basecols)
    tests = {'2025_heldout_from':boundary, '2025_holdout':compare(late,base_early,extra_early),
             '2026_external':compare(seasons[2026][2],base,extra)}
    tests['2026_unadjusted_rpi_points'] = scores(np.asarray([r['y'] for r in unadj2026]),predictions(unadj2026,unadj))
    tests['2026_raw_vs_adjusted'] = compare(seasons[2026][2],unadj,base,unadj2026)
    m,keys,rows = seasons[2026]
    s = snapshot(m,keys)
    strength = np.einsum('ij,j->i',s['z'],extra)
    base_strength = np.einsum('ij,j->i',s['z'],base)
    order = np.argsort(-strength)
    raw_margin = collections.defaultdict(list)
    for g in m:
        vals = [g['values'][i]['points'] for i in [0,1]]
        if None not in vals:
            for side in [0,1]:
                raw_margin[g['teams'][side]['key']].append(vals[side]-vals[1-side])
    rawrank = {k:r+1 for r,k in enumerate(sorted(raw_margin,key=lambda k:-np.mean(raw_margin[k])))}
    adjrank = {keys[i]:r+1 for r,i in enumerate(np.argsort(-s['raw'][:,1]))}
    baserank = {keys[i]:r+1 for r,i in enumerate(np.argsort(-base_strength))}
    gamelog = []
    for g in m:
        for side in [0,1]:
            t,op = g['teams'][side],g['teams'][1-side]
            i,j = s['ix'][t['key']],s['ix'][op['key']]
            vals = {}
            for metric in METRICS:
                model = s['models'][metric]
                v = g['values'][side][metric]
                # Remove opponent defense; positive defense means lower allowed rate.
                vals[metric] = {'raw':v, 'opponent_adjusted':v+float(model['def'][j]) if v is not None else None,
                                'expected':float(model['mean']+model['off'][i]-model['def'][j])}
            own,opp = g['values'][side]['points'],g['values'][1-side]['points']
            margin = own-opp if own is not None and opp is not None else None
            perf = margin+float(s['raw'][j,1]) if margin is not None else None
            gamelog.append({'game_id':str(g['game_id']),'date':str(g['date']),'team':t['name_short'],
                            'key':t['key'],'opponent':op['name_short'],'won':g['winner_idx']==side,
                            'raw_margin':margin,'adjusted_performance':perf,'stats':vals,
                            'match_score':[g['sets_won'].get(t['key']),g['sets_won'].get(op['key'])],
                            'set_scores':g['set_scores'].get(t['key'],[])})
    ranked = []
    for rank,i in enumerate(order,1):
        k=keys[i]; rp=s['rpi'][k]
        logs=[g for g in gamelog if g['key']==k]
        if not logs: continue
        perfs=[g['adjusted_performance'] for g in logs if g['adjusted_performance'] is not None]
        teamname=next(t['name_short'] for g in m for t in g['teams'] if t['key']==k)
        ranked.append({'rank':len(ranked)+1,'team':teamname,'key':k,'wins':rp['wins'],'losses':rp['losses'],
                       'score':float(strength[i]),'baseline_rank':baserank[k],
                       'raw_margin_rank':rawrank.get(k),'adjusted_margin_rank':adjrank[k],
                       'raw_net_pps':float(np.mean(raw_margin[k])) if raw_margin[k] else None,
                       'adjusted_net_pps':float(s['raw'][i,1]),
                       'adjusted_hitting_diff':float(s['raw'][i,2]),
                       'adjusted_aces_diff':float(s['raw'][i,4]),'adjusted_blocks_diff':float(s['raw'][i,5]),
                       'performance_median':float(np.median(perfs)) if perfs else None,
                       'performance_iqr':np.quantile(perfs,[.25,.75]).tolist() if perfs else None,
                       'performance_sd':float(np.std(perfs,ddof=1)) if len(perfs)>1 else None,
                       'components':{f:float(s['z'][i,c]*extra[c]) for c,f in enumerate(FEATURES)}})
    existing=json.loads((ROOT/'data'/'rating_2026.json').read_text())
    oldrank={B.norm(t['team']):t['composite_rank'] for t in existing['teams']}
    for t in ranked:
        t['existing_power_rank']=oldrank.get(t['key'])
    report={'as_of':str(max(g['date'] for g in m)),'tests':tests,
            'weights':dict(zip(FEATURES,extra.tolist())),
            'baseline_weights':dict(zip(FEATURES,base.tolist())),
            'penalties':{'baseline':basepen,'combined':extrapen},
            'coverage':{metric:s['models'][metric]['count'] for metric in METRICS},
            'matches':len(m),'ranking':ranked}
    (OUT/'results.json').write_text(json.dumps(report,indent=2))
    (OUT/'all_team_game_adjustments.json').write_text(json.dumps(gamelog))
    render(report,gamelog)
    print(json.dumps({'tests':tests,'weights':report['weights'],'top30':[{k:t[k] for k in ['rank','team','baseline_rank','raw_net_pps','adjusted_net_pps']} for t in ranked[:30]]},indent=2),flush=True)


def render(report,logs):
    ext=report['tests']['2026_external']
    raw=report['tests']['2026_unadjusted_rpi_points']
    adjustment=report['tests']['2026_raw_vs_adjusted']
    h=['<!doctype html><meta charset="utf-8"><title>Opponent-adjusted ballot research</title>',
       '<style>body{font:16px system-ui;background:#f7f6f2;color:#172b30;max-width:1350px;margin:30px auto;padding:20px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:right;padding:8px;border-bottom:1px solid #ccc}th:nth-child(2),td:nth-child(2){text-align:left}details{margin:18px 0}summary{cursor:pointer;font-weight:700}small{color:#53646a}</style>',
       '<h1>Opponent-adjusted ballot research · '+report['as_of']+'</h1>',
       '<p>Research ranking: weights learned from 2025, frozen for 2026. Every weekly prediction uses only earlier dates. No production ratings changed. This is a strength model with a results component, not a committee-selection projection.</p>',
       '<p>Per-game adjusted stats below are retrospective: raw offensive rate + opponent defensive rating from the current season. They compare performance against a reference defense. Adjusted net points/set uses both offense and defense. Neither is an independently observed statistic.</p>',
       '<p>Incomplete scores/box fields are omitted, never shown as zero. Equal match weights; explicit ridge penalty 3. Home/altitude/health/setting-quality adjustments are absent because comparable verified historical inputs are unavailable. Dates are UTC in the archived loader. Records inherit the saved canonical game ledger, including known missing results: Kansas–Utah Oct 1 and one Texas A&amp;M win. Their displayed records and ratings are incomplete.</p>',
       '<h2>What changed?</h2><p>Across %d future 2026 matches: RPI + raw margins AUC %.4f; RPI + opponent-adjusted margins %.4f; combined layers %.4f. AUC measures winner discrimination, not accuracy percentage. Lower Brier error is better: %.4f → %.4f → %.4f.</p>'%(ext['baseline']['n'],raw['auc'],ext['baseline']['auc'],ext['combined']['auc'],raw['brier'],ext['baseline']['brier'],ext['combined']['brier']),
       '<p>Day-cluster bootstrap 95%% intervals: opponent-adjustment AUC gain %+.4f to %+.4f; extra-layer AUC gain %+.4f to %+.4f. These intervals describe match-sampling uncertainty, not every source of model uncertainty. All layer coefficients were frozen using 2025; the 2026 data were used to evaluate this research model.</p>'%tuple(adjustment['auc_delta_95_ci']+ext['auc_delta_95_ci']),
       '<details><summary>Full chronological validation</summary><pre>'+html.escape(json.dumps(report['tests'],indent=2))+'</pre></details>',
       '<h2>Fitted weights</h2><p>Coefficients apply to standardized team features, then to team differences for match probability; they are not percentages. Correlated layers can receive zero weight.</p><pre>'+html.escape(json.dumps(report['weights'],indent=2))+'</pre>',
       '<p>Coverage (team-match lines): '+html.escape(str(report['coverage']))+'</p>',
       '<h2>All teams</h2><p>POWER = existing site rank. Adj baseline = this experiment’s two-layer RPI + adjusted-margin model; it uses different calibration from the site. A rank movement is not proof of improved accuracy.</p><table><tr><th>Rank</th><th>Team</th><th>W–L</th><th>POWER</th><th>Adj baseline</th><th>Raw net PPS</th><th>Adj net PPS</th><th>Adj hit diff</th><th>Adj ace diff/set</th><th>Adj block diff/set</th><th>Perf median</th><th>Perf middle 50%</th></tr>']
    fmt=lambda v: '—' if v is None else ('%.3f'%v)
    for t in report['ranking']:
        iqr=t['performance_iqr']
        h.append('<tr><td>%d</td><td>%s</td><td>%d–%d</td><td>%s</td><td>%d</td>'%(t['rank'],html.escape(t['team']),t['wins'],t['losses'],str(t['existing_power_rank']) if t['existing_power_rank'] is not None else '—',t['baseline_rank'])+''.join('<td>'+fmt(t[x])+'</td>' for x in ['raw_net_pps','adjusted_net_pps','adjusted_hitting_diff','adjusted_aces_diff','adjusted_blocks_diff','performance_median'])+'<td>'+(' to '.join(fmt(v) for v in iqr) if iqr else '—')+'</td></tr>')
    h.append('</table><h2>Every team · every game</h2><p>Each metric displays raw → opponent adjusted. Hitting is efficiency; all other metrics are per set. Earned = kills + aces + solo blocks + half block assists. Supplemental counts (digs, assists, errors, etc.) are context, not additional fitted ranking layers; a higher count is not automatically better. Performance = observed net PPS + opponent adjusted net PPS; it is descriptive, with no home correction. Use median and middle 50% to examine consistency, not just the best match. Wide tables scroll horizontally.</p>')
    for t in report['ranking']:
        teamlogs=[g for g in logs if g['key']==t['key']]
        rankmap={r['key']:r['rank'] for r in report['ranking']}
        wins=sorted([g for g in teamlogs if g['won']],key=lambda g:rankmap.get(B.norm(g['opponent']),999))[:3]
        losses=sorted([g for g in teamlogs if not g['won']],key=lambda g:-rankmap.get(B.norm(g['opponent']),999))[:3]
        recent=sorted(teamlogs,key=lambda g:(g['date'],g['game_id']))[-3:]
        def short(g):
            score='–'.join(str(v) if v is not None else '—' for v in g['match_score'])
            return html.escape('%s %s %s %s (current #%s)'%(g['date'],'W' if g['won'] else 'L',g['opponent'],score,rankmap.get(B.norm(g['opponent']),'—')))
        h.append('<details><summary>%d. %s</summary>'%(t['rank'],html.escape(t['team'])))
        for label,items in [('Best wins by current model rank',wins),('Lowest-ranked losses',losses),('Most recent three',recent)]:
            h.append('<p><b>'+label+':</b> '+('; '.join(short(g) for g in items) if items else 'None')+'</p>')
        h.append('<div style="overflow-x:auto"><table><tr><th>Date</th><th>Opponent</th><th>Match / set scores</th><th>Net PPS</th><th>Adj performance</th>'+''.join('<th>'+x+' raw → adj</th>' for x in METRICS)+'</tr>')
        # Fill summary separately to keep formatting easy to inspect.
        for g in logs:
            if g['key']!=t['key']:continue
            score=('W ' if g['won'] else 'L ')+'–'.join(str(v) if v is not None else '—' for v in g['match_score'])
            sets=', '.join('–'.join(str(v) if v is not None else '—' for v in pair) for pair in g['set_scores'])
            h.append('<tr><td>'+g['date']+'</td><td>'+html.escape(g['opponent'])+'</td><td>'+score+'<br><small>'+sets+'</small></td><td>'+fmt(g['raw_margin'])+'</td><td>'+fmt(g['adjusted_performance'])+'</td>'+''.join('<td>'+fmt(g['stats'][x]['raw'])+' → '+fmt(g['stats'][x]['opponent_adjusted'])+'</td>' for x in METRICS)+'</tr>')
        h.append('</table></div></details>')
    (OUT/'report.html').write_text(''.join(h))


if __name__=='__main__':
    main()
