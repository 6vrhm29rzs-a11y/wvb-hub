#!/usr/bin/env python3
"""Read-only exploratory audit of archived SUPERMIND forecasts, Python 3.9.

Adds the missing calibration-only comparator. Does not fit team ratings, crawl,
modify the site model, or claim that historical folds are pristine holdouts.
All fitted calibration/stack coefficients use 2025 only. 2026 is diagnostic:
it has already been examined during development of the source models.
"""
import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import expit, logit
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Cody/coordination/research/SUPERMIND-2026-11/ensemble'
OUT = ROOT / 'output/power_research_2026-11-03'


def fit_temperature(p, y):
    """Positive slope preserves ordering and side reversal; never fits an intercept."""
    z = logit(np.clip(p, 1e-4, 1-1e-4))
    def loss(log_slope):
        x = np.exp(log_slope) * z
        return np.mean(np.logaddexp(0, x) - y*x)
    result = minimize_scalar(loss, bounds=(-4, 4), method='bounded',
                             options={'xatol': 1e-12})
    return float(np.exp(result.x))


def losses(p, y):
    p = np.clip(p, 1e-4, 1-1e-4)
    return -(y*np.log(p) + (1-y)*np.log1p(-p))


def fit_stack(x, y):
    """Exploratory three-component logistic stack; not percentage weights."""
    assert np.isfinite(x).all()
    def obj(w):
        z = np.einsum('ij,j->i',x,w)
        return (float(np.sum(np.logaddexp(0,z)-y*z)+.001*np.dot(w,w)/2),
                np.einsum('ij,i->j',x,expit(z)-y)+.001*w)
    fit = minimize(obj,np.zeros(x.shape[1]),jac=True,method='L-BFGS-B',options={'ftol':1e-13,'gtol':1e-8})
    if not fit.success:
        raise ValueError('Stack optimization failed: '+str(fit.message))
    return fit.x


def deployed_comparison(source_rows):
    paths = {y:OUT/('reviewer_deployed_rows_%s.jsonl' % y) for y in (2025,2026)}
    if not all(p.exists() for p in paths.values()):
        return {'status':'Replay not yet available; no comparison with deployed mapping claimed.'}
    rows = {y:[json.loads(line) for line in paths[y].read_text().splitlines()] for y in paths}
    by_id = {y:{r['gid']:r for r in source_rows[y]} for y in paths}
    def design(year):
        return np.array([[logit(r['p_deployed']),logit(by_id[year][r['gid']]['p_F1']),
                          logit(by_id[year][r['gid']]['p_F2'])] for r in rows[year]])
    x25,x26 = design(2025),design(2026)
    y25 = np.array([r['y'] for r in rows[2025]])
    y26 = np.array([r['y'] for r in rows[2026]])
    weeks = np.array([r['week'] for r in rows[2026]])
    base25 = np.array([r['p_deployed'] for r in rows[2025]])
    base26 = np.array([r['p_deployed'] for r in rows[2026]])
    slope = fit_temperature(base25,y25)
    w = fit_stack(x25,y25)
    probs = {'deployed_mapping_replayed':base26,
             'deployed_plus_calibration':expit(slope*x26[:,0]),
             'deployed_plus_elo_hitting_stack':expit(np.einsum('ij,j->i',x26,w)),
             'original_harness_stack':np.array([r['p_F4FROZEN'] for r in rows[2026]])}
    # Same joined rows, with identical labels, is essential for paired comparisons.
    assert len(rows[2026]) == len(source_rows[2026])
    assert all(r['y'] == by_id[2026][r['gid']]['y'] for r in rows[2026])
    return {'status':'EXPLORATORY; latest deployed mapping replayed at earlier weekly team snapshots, not live-issued forecasts.',
            'warning':'2025 deployed mapping already used 2025 outcomes to fit its coefficients; no 2025 validation score is claimed. Neither 2026 results nor calibration select a production model here.',
            'replay_sha256':{str(paths[y].relative_to(ROOT)):hashlib.sha256(paths[y].read_bytes()).hexdigest() for y in paths},
            'slope_fit_2025':slope,'stack_coefficients_fit_2025':w.tolist(),
            'metrics_2026':{k:metrics(p,y26) for k,p in probs.items()},
            'stack_minus_calibration_2026':paired(probs['deployed_plus_elo_hitting_stack'],probs['deployed_plus_calibration'],y26,weeks),
            'calibration_minus_deployed_2026':paired(probs['deployed_plus_calibration'],base26,y26,weeks)}


def metrics(p, y):
    n1 = y.sum()
    auc = float((rankdata(p)[y == 1].sum() - n1*(n1+1)/2) / (n1*(len(y)-n1))) if 0 < n1 < len(y) else None
    return {'n': len(y), 'log_loss': float(losses(p,y).mean()),
            'brier': float(np.mean((p-y)**2)), 'auc': auc,
            'accuracy': float(np.mean((p > .5) == y))}


def paired(p, q, y, weeks, draws=4000):
    """Negative difference favors p. Week clusters retain within-week dependence."""
    diff = losses(p,y)-losses(q,y)
    rng = np.random.default_rng(20261103)
    match = np.array([np.mean(diff[rng.integers(0,len(diff),len(diff))])
                      for _ in range(draws)])
    groups = [diff[weeks == w] for w in np.unique(weeks)]
    counts = np.array([len(g) for g in groups])
    sums = np.array([g.sum() for g in groups])
    draws_idx = rng.integers(0, len(groups), (draws,len(groups)))
    block = sums[draws_idx].sum(axis=1) / counts[draws_idx].sum(axis=1)
    return {'mean_log_loss_difference': float(diff.mean()),
            'match_95_ci': np.quantile(match,[.025,.975]).tolist(),
            'week_95_ci': np.quantile(block,[.025,.975]).tolist(),
            'weeks': len(groups)}


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    rows = {}
    hashes = {}
    for year in (2025,2026):
        path = SOURCE / ('rows_%s.jsonl' % year)
        raw = path.read_bytes()
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
        rows[year] = [json.loads(line) for line in raw.splitlines()]
        assert len({r['gid'] for r in rows[year]}) == len(rows[year])
        assert all(r['season'] == year for r in rows[year])
    y25 = np.array([r['y'] for r in rows[2025]])
    p25 = np.array([r['p_BASE'] for r in rows[2025]])
    slope = fit_temperature(p25,y25)
    result = {
        'generated_utc': datetime.datetime.utcnow().isoformat()+'Z',
        'scope': 'EXPLORATORY calibration audit; source BASE is the iid best-of-five harness, not deployed cand_win.',
        'limitations': [
            'Source 2025 preseason rosters are reconstructed from full-season participation.',
            '2025 leave-week-out calibration is cross-fitting, not chronological forecasting; future weeks train the calibrator.',
            '2026 has been repeatedly examined in model development; this is not an untouched confirmation season.',
            'Source model hyperparameter selection is not nested within the 2025 folds.',
            'Week bootstrap does not remove all dependence from teams appearing across weeks.',
            'AUC here orders match win probabilities, not a direct test of top-25 team ordering.'
        ],
        'source_sha256': hashes,
        'calibration_slope_fit_on_2025': slope,
        'probability_examples': {str(p): float(expit(slope*logit(p))) for p in (.6,.75,.9,.95)},
        'years': {}}
    for year, rr in rows.items():
        y = np.array([r['y'] for r in rr])
        weeks = np.array([r['week'] for r in rr])
        base = np.array([r['p_BASE'] for r in rr])
        ps = {'harness_base':base,
              'frozen_three_model_stack':np.array([r['p_F4FROZEN'] for r in rr]),
              'elo':np.array([r['p_F1'] for r in rr]),
              'hitting_only':np.array([r['p_F2'] for r in rr]),
              'equal_blend':np.array([r['p_F5'] for r in rr])}
        if year == 2025:
            cal = np.empty(len(rr))
            for week in np.unique(weeks):
                train = weeks != week
                s = fit_temperature(base[train],y[train])
                cal[~train] = expit(s*logit(base[~train]))
        else:
            cal = expit(slope*logit(base))
        ps['calibration_only'] = cal
        out = {'first_day':min(r['day'] for r in rr),'last_day':max(r['day'] for r in rr),
               'metrics':{name:metrics(p,y) for name,p in ps.items()},
               'calibration_minus_base':paired(cal,base,y,weeks),
               'stack_minus_calibration':paired(ps['frozen_three_model_stack'],cal,y,weeks)}
        if year == 2026:
            out['calibration_preserves_all_ordering'] = bool(np.array_equal(np.argsort(base),np.argsort(cal)))
            out['favorites_changed_stack_vs_base'] = int(np.sum((base>.5)!=(ps['frozen_three_model_stack']>.5)))
            # Fixed calendar subdivisions are descriptive, never used to choose a model.
            out['by_month'] = {}
            for month in sorted({r['day'][:7] for r in rr}):
                mask = np.array([r['day'].startswith(month) for r in rr])
                out['by_month'][month] = {name:metrics(p[mask],y[mask]) for name,p in ps.items()}
            frozen = [{'gid':r['gid'],'day':r['day'],'week':r['week'],'y':r['y'],
                       'p_base':float(base[i]),'p_calibration':float(cal[i]),
                       'p_stack':float(ps['frozen_three_model_stack'][i])} for i,r in enumerate(rr)]
            (OUT/'calibration_rows_2026.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in frozen))
        result['years'][str(year)] = out
    result['deployed_comparison'] = deployed_comparison(rows)
    (OUT/'calibration_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    run()
