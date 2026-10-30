"""Test that every artifact file path referenced in docs/paper_numbers.md exists."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PaperNumbersMappingTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "results").is_dir(), "Requires generated research results")
    def test_all_referenced_artifacts_exist(self) -> None:
        doc_path = ROOT / "docs" / "paper_numbers.md"
        self.assertTrue(doc_path.exists(), "docs/paper_numbers.md must exist")

        content = doc_path.read_text(encoding="utf-8")
        # Extract all file path mentions matching results/ or scripts/
        path_pattern = re.compile(r"`((?:results|scripts|datasets|tests)/[^`*]+)`")
        matches = path_pattern.findall(content)
        self.assertGreater(len(matches), 15, "Expected at least 15 artifact paths in paper_numbers.md")

        missing = []
        for rel_path in matches:
            # Strip trailing punctuation or glob patterns if any
            clean_path = rel_path.split(" -> ")[0].strip()
            # If it's a template like {model} or {20001..20020}, handle specially
            if "{" in clean_path:
                continue
            full_path = ROOT / clean_path
            if not full_path.exists():
                missing.append(clean_path)

        self.assertEqual(missing, [], f"The following referenced files do not exist: {missing}")


if __name__ == "__main__":
    unittest.main()
