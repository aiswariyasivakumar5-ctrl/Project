import json
import tempfile
import unittest
from pathlib import Path

from sentinel.novelty_experiment import NoveltyStudyConfig, run_novelty_study


class NoveltyResumptionTests(unittest.TestCase):
    def test_in_process_and_resumption(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Run 1: Run seed 42 with only 2 scenarios and small workload
            cfg1 = NoveltyStudyConfig(
                seeds=(42,),
                variants=("baseline",),
                scenarios=("capability_laundering", "schema_stable_response"),
                training_events=10,
                validation_events=5,
                test_events=6,
                output=str(temp_path),
                in_process=True,
                resumable=True,
            )
            res1 = run_novelty_study(cfg1)
            self.assertEqual(len(res1["aggregate"]), 2)
            exec1 = json.loads((temp_path / "execution.json").read_text(encoding="utf-8"))
            self.assertEqual(exec1["status"], "completed")
            self.assertEqual(exec1["completed_phase_records"], 2)

            # Check that phase JSONs exist
            phase_files = list(temp_path.glob("baseline/*/seed-42-*.json"))
            self.assertEqual(len(phase_files), 2)

            # Run 2: Resume into same folder with an additional scenario
            cfg2 = NoveltyStudyConfig(
                seeds=(42,),
                variants=("baseline",),
                scenarios=("capability_laundering", "schema_stable_response", "coordinated_servers"),
                training_events=10,
                validation_events=5,
                test_events=6,
                output=str(temp_path),
                in_process=True,
                resumable=True,
            )
            res2 = run_novelty_study(cfg2)
            self.assertEqual(len(res2["aggregate"]), 3)
            exec2 = json.loads((temp_path / "execution.json").read_text(encoding="utf-8"))
            self.assertEqual(exec2["status"], "completed")
            self.assertEqual(exec2["completed_phase_records"], 3)


if __name__ == "__main__":
    unittest.main()
