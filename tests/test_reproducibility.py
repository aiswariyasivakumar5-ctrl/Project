"""Tests for the reproducibility package and verification pipeline."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.reproduce_all import (
    EXIT_CHECKSUM_MISMATCH,
    EXIT_RESULTS_MISSING,
    EXIT_SUCCESS,
    run_pipeline,
    verify_dataset_manifest,
    verify_20seed_artifacts,
    regenerate_all_outputs,
)
from sentinel.final_verification import verify_research_package


class TestReproducibilityPackage(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parent.parent

    def test_dataset_manifest_checksums(self) -> None:
        result = verify_dataset_manifest(self.root / "datasets/synthetic-expanded-v1")
        self.assertEqual(result["status"], "PASS", f"Manifest errors: {result.get('errors')}")
        self.assertEqual(result["checked_shards"], 480)
        self.assertEqual(len(result["errors"]), 0)

    @unittest.skipUnless((Path(__file__).resolve().parent.parent / "results").is_dir(), "Requires generated research results")
    def test_legacy_research_package(self) -> None:
        result = verify_research_package(str(self.root))
        self.assertEqual(result["status"], "PASS", f"Legacy package errors: {result.get('errors')}")
        self.assertGreaterEqual(result["checked_file_count"], 40)

    @unittest.skipUnless((Path(__file__).resolve().parent.parent / "results").is_dir(), "Requires generated research results")
    def test_20seed_artifacts_integrity(self) -> None:
        result = verify_20seed_artifacts(str(self.root))
        self.assertEqual(result["status"], "PASS", f"20-seed artifact errors: {result.get('errors')}")
        self.assertGreaterEqual(result["checked_files"], 500)

    def test_reproduce_pipeline_results_absent(self) -> None:
        # In a workspace without results/, verify_only should verify shards and exit with code 2
        if not (self.root / "results").is_dir():
            exit_code = run_pipeline(root=self.root, verify_only=True)
            self.assertEqual(exit_code, EXIT_RESULTS_MISSING)

    def test_reproduce_pipeline_tampered_dataset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            dataset_dir = temp_root / "datasets" / "synthetic-expanded-v1"
            dataset_dir.mkdir(parents=True)
            manifest = {
                "shards": [{"path": "shard1.jsonl.gz", "gzip_sha256": "expected_hash_000"}],
                "seeds": [20001],
            }
            (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            # Create tampered file with non-matching hash
            (dataset_dir / "shard1.jsonl.gz").write_bytes(b"tampered content")

            exit_code = run_pipeline(root=temp_root, verify_only=True)
            self.assertEqual(exit_code, EXIT_CHECKSUM_MISMATCH)

    def test_reproduce_pipeline_tampered_results_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            # Create valid manifest with empty shards so shard verification passes
            dataset_dir = temp_root / "datasets" / "synthetic-expanded-v1"
            dataset_dir.mkdir(parents=True)
            (dataset_dir / "manifest.json").write_text(json.dumps({"shards": []}), encoding="utf-8")

            # Create mock results/ with broken baseline aggregate
            res_dir = temp_root / "results" / "baselines_20seed" / "aggregate"
            res_dir.mkdir(parents=True)
            (res_dir / "metrics.json").write_text("{\"invalid\": true}", encoding="utf-8")

            exit_code = run_pipeline(root=temp_root, verify_only=True)
            self.assertEqual(exit_code, EXIT_CHECKSUM_MISMATCH)

    def test_paper_numbers_documentation_exists(self) -> None:
        doc = self.root / "docs/paper_numbers.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("0.8000", text)
        self.assertIn("0.8815", text)
        self.assertIn("0.0000", text)
        self.assertIn("0.8250", text)
        self.assertIn("0.7904", text)
        self.assertIn("0.8381", text)

    def test_reproducibility_guide_exists(self) -> None:
        guide = self.root / "docs/reproducibility.md"
        self.assertTrue(guide.exists())
        text = guide.read_text(encoding="utf-8")
        self.assertIn("Quickstart", text)
        self.assertIn("numpy==2.5.2", text)


if __name__ == "__main__":
    unittest.main()
