"""Research guards: opponent direction, pregame separation, missingness, symmetry."""
import datetime as dt
import unittest

import numpy as np

import research_ballot_ensemble as R


def fixtures():
    keys = ['a','b','c','d']
    offense = np.array([3.,1.,-1.,-3.])
    defense = np.array([2.,-2.,1.,-1.])
    games = []
    for day in range(35):
        for i in range(4):
            j = (i+1+day%3)%4
            if i == j: continue
            p = [20+offense[i]-defense[j],20+offense[j]-defense[i]]
            games.append({'game_id':str(len(games)), 'date':dt.date(2025,8,1)+dt.timedelta(days=day),
                          'teams':[{'key':keys[i]},{'key':keys[j]}],
                          'winner_idx':int(p[1]>p[0]),
                          'values':[{m:p[s]/(100 if m=='hitting' else 1) for m in R.METRICS} for s in [0,1]]})
    return games,keys,offense,defense


class ResearchGuards(unittest.TestCase):
    def test_opponent_adjustment_recovers_known_parameters(self):
        games,keys,offense,defense=fixtures()
        model=R.offdef(games,keys,'points',ridge=1e-7)
        np.testing.assert_allclose(model['off'],offense,atol=1e-5)
        np.testing.assert_allclose(model['def'],defense,atol=1e-5)
        # Same team: weak opposing defense inflates raw scoring. Adjustment removes it.
        raw_strong=20+offense[0]-defense[2]
        raw_weak=20+offense[0]-defense[1]
        self.assertGreater(raw_weak,raw_strong)
        self.assertAlmostEqual(raw_strong+model['def'][2],raw_weak+model['def'][1],places=5)

    def test_future_outcome_cannot_change_own_features(self):
        games,keys,_,_=fixtures()
        rows=R.weekly_rows(games,keys)
        target=rows[-1]
        start=dt.date.fromisoformat(target['snapshot_before'])
        # Mutate every input on/after this forecast's freeze date, not just label.
        for g in games:
            if g['date']>=start:
                g['winner_idx']=1-g['winner_idx']
                for side in g['values']:
                    for metric in side: side[metric]*=2
        again=R.weekly_rows(games,keys)
        old={r['id']:r for r in rows}
        for r in again:
            if r['snapshot_before']==target['snapshot_before']:
                np.testing.assert_array_equal(r['x'],old[r['id']]['x'])
                np.testing.assert_array_equal(r['x_unadj'],old[r['id']]['x_unadj'])

    def test_missing_counts_are_not_zero(self):
        t={'sets':3,'points_for':75,'points_against':40,'box':{}}
        v=R.values({'teams':[t,t]})
        for metric in ['hitting','earned','aces','blocks']:
            self.assertIsNone(v[0][metric])
        t['box']={'points':'74','gamesPlayed':'3'}
        self.assertIsNone(R.values({'teams':[t,t]})[0]['points'])

    def test_predictions_complement_and_are_finite(self):
        games,keys,_,_=fixtures()
        rows=R.weekly_rows(games,keys)
        w=R.fit(rows,list(range(len(R.FEATURES))),10.)
        reverse=[{**r,'x':(-np.array(r['x'])).tolist()} for r in rows]
        p=R.predictions(rows,w)
        self.assertTrue(np.all(np.isfinite(p)))
        self.assertTrue(np.all(w>=0))
        np.testing.assert_allclose(p+R.predictions(reverse,w),1.)


if __name__=='__main__': unittest.main()
