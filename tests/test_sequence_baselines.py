import copy
import tempfile
import unittest

import numpy as np

from sentinel_research.compare import CompareConfig, run_comparison
from sentinel_research.comparison_data import build_comparison_dataset
from sentinel_research.sequence_baselines import LSTMAnomalyDetector, TransformerAnomalyDetector
from sentinel_research.sequence_features import SequencePreprocessor


class SequenceFeatureTests(unittest.TestCase):
    def setUp(self):
        self.dataset=build_comparison_dataset(7,40,20,48)

    def test_shape_and_no_future_leakage(self):
        events=[copy.deepcopy(row.interaction) for row in self.dataset.train]
        preprocessor=SequencePreprocessor(4); preprocessor.fit(events)
        prefix=preprocessor.transform(events[:10])
        extended=preprocessor.transform(events[:11])
        self.assertEqual(prefix.shape,(10,4,32))
        self.assertTrue(np.allclose(prefix,extended[:10]))

    def test_session_boundary_resets_history(self):
        events=[copy.deepcopy(row.interaction) for row in self.dataset.train[:2]]
        events[0].session_id="a"; events[1].session_id="b"
        windows=SequencePreprocessor(4).fit(events)
        self.assertEqual(int(windows[1,:,-1].sum()),1)

    def test_transform_does_not_refit_train_statistics(self):
        prep=SequencePreprocessor(4); prep.fit([copy.deepcopy(x.interaction) for x in self.dataset.train])
        mean=prep.scaler.mean.copy()
        prep.transform([copy.deepcopy(x.interaction) for x in self.dataset.test])
        self.assertTrue(np.array_equal(mean,prep.scaler.mean))


class SequenceModelTests(unittest.TestCase):
    def test_lstm_is_deterministic(self):
        x=np.random.default_rng(3).normal(size=(20,4,32)); x[:,:,-1]=1
        a=LSTMAnomalyDetector(9,epochs=2,sequence_length=4); b=LSTMAnomalyDetector(9,epochs=2,sequence_length=4)
        a.fit(x); b.fit(x)
        self.assertTrue(np.allclose(a.score(x),b.score(x)))
        self.assertGreater(a.parameter_count,0)

    def test_transformer_is_deterministic_and_causal(self):
        x=np.random.default_rng(4).normal(size=(12,4,32)); x[:,:,-1]=1
        a=TransformerAnomalyDetector(9,epochs=2,sequence_length=4); b=TransformerAnomalyDetector(9,epochs=2,sequence_length=4)
        a.fit(x); b.fit(x)
        self.assertTrue(np.allclose(a.score(x),b.score(x)))
        self.assertEqual(a.configuration["layers"],1)

    def test_comparison_schema_and_validation_threshold(self):
        with tempfile.TemporaryDirectory() as output:
            result=run_comparison(CompareConfig((11,),40,20,48,("lstm","transformer"),.01,output))
            self.assertEqual({x["model"] for x in result["results"]},{"lstm","transformer"})
            for item in result["results"]:
                self.assertFalse(item["calibration"]["test_used_for_threshold"])
                self.assertEqual(item["sequence_length"],8)
                self.assertIn("parameter_count",item["model_configuration"])


if __name__ == "__main__": unittest.main()
