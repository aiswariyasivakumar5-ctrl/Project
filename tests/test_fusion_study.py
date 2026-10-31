import unittest

import numpy as np

from sentinel_research.fusion_study import MidrankECDF, candidate_scores


def records(scores):
    return [{"final_risk": score, "linear_risk": score / 2} for score in scores]


class FusionCalibrationTests(unittest.TestCase):
    def test_deterministic_calibration(self):
        values=np.array([.1,.2,.2,.5])
        self.assertTrue(np.array_equal(MidrankECDF().fit(values).transform(values),
                                       MidrankECDF().fit(values).transform(values)))

    def test_ties_receive_identical_midrank(self):
        transformed=MidrankECDF().fit(np.array([.1,.5,.5,.5])).transform(np.array([.5,.5]))
        self.assertEqual(transformed[0], transformed[1])
        self.assertAlmostEqual(transformed[0], .625)

    def test_test_values_do_not_affect_calibration(self):
        calibration=MidrankECDF().fit(np.array([.1,.2,.5]))
        before=calibration.transform(np.array([.2]))
        calibration.transform(np.array([100,-100,.2]))
        after=calibration.transform(np.array([.2]))
        self.assertTrue(np.array_equal(before, after))

    def test_candidate_fusion_retains_causal_linear_score(self):
        validation=records([.2,.5]); test=records([.4,.8])
        result=candidate_scores(validation,test)
        self.assertTrue(np.array_equal(result["additive_causal"][1], np.array([.2,.4])))

    def test_midrank_is_monotonic(self):
        calibration=MidrankECDF().fit(np.array([.1,.2,.2,.5]))
        values=calibration.transform(np.array([.05,.1,.2,.3,.5,.9]))
        self.assertTrue(np.all(np.diff(values) >= 0))


if __name__ == "__main__": unittest.main()
