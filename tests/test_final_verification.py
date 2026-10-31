import unittest
from pathlib import Path

from sentinel_research.final_verification import verify_research_package


class FinalVerificationTests(unittest.TestCase):
    @unittest.skipUnless(Path("results").is_dir(), "Requires generated research results")
    def test_retained_package_is_consistent(self):
        result=verify_research_package()
        self.assertEqual(result["status"],"PASS",result["errors"])
        self.assertEqual(len(result["models"]),6)


if __name__ == "__main__": unittest.main()
