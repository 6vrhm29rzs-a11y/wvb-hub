"""Meaningful controls for the research-only probability calibration audit."""
import unittest
import numpy as np
from scipy.special import expit, logit
from research_power_validation import fit_temperature, losses, paired


class CalibrationControls(unittest.TestCase):
    def test_known_overconfidence_and_side_reversal(self):
        # At stated 90% and 10%, truth is 75% and 25%. Known slope is logit(.75)/logit(.9).
        p = np.r_[np.full(100,.9),np.full(100,.1)]
        y = np.r_[np.ones(75),np.zeros(25),np.ones(25),np.zeros(75)]
        slope = fit_temperature(p,y)
        self.assertAlmostEqual(slope,logit(.75)/logit(.9),places=5)
        calibrated = expit(slope*logit(p))
        self.assertLess(losses(calibrated,y).mean(),losses(p,y).mean())
        self.assertAlmostEqual(slope,fit_temperature(1-p,1-y),places=5)
        self.assertTrue(np.array_equal(np.argsort(p),np.argsort(calibrated)))

    def test_identical_predictors_have_zero_difference(self):
        p = np.array([.1,.3,.7,.9]); y = np.array([0,1,0,1]); weeks = np.array([1,1,2,2])
        result = paired(p,p,y,weeks,draws=100)
        self.assertEqual(result['mean_log_loss_difference'],0)
        self.assertEqual(result['week_95_ci'],[0,0])


if __name__ == '__main__':
    unittest.main()
