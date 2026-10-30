"""Tests for clean release archive generation."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile
import tarfile

from scripts.make_release_archive import build_release_archive


class TestReleaseArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # 1. Create valid project structure
        (self.root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
        (self.root / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
        sentinel_dir = self.root / "sentinel"
        sentinel_dir.mkdir()
        (sentinel_dir / "__init__.py").write_text("# sentinel\n", encoding="utf-8")
        (sentinel_dir / "gateway.py").write_text("# gateway\n", encoding="utf-8")

        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_example.py").write_text("# test\n", encoding="utf-8")

        # 2. Create junk files and directories that must be excluded
        (self.root / ".venv" / "Scripts").mkdir(parents=True)
        (self.root / ".venv" / "Scripts" / "python.exe").write_bytes(b"dummy")
        (self.root / ".venv-repro" / "bin").mkdir(parents=True)
        (self.root / ".venv-repro" / "bin" / "python").write_bytes(b"dummy")

        (sentinel_dir / "__pycache__").mkdir()
        (sentinel_dir / "__pycache__" / "gateway.cpython-312.pyc").write_bytes(b"dummy")
        (self.root / ".mypy_cache" / "3.11").mkdir(parents=True)
        (self.root / ".mypy_cache" / "3.11" / "cache.db").write_bytes(b"dummy")
        (self.root / ".ruff_cache" / "content").mkdir(parents=True)
        (self.root / ".ruff_cache" / "content" / "item").write_bytes(b"dummy")
        (self.root / ".pytest_cache" / "v").mkdir(parents=True)
        (self.root / ".pytest_cache" / "v" / "cache").write_bytes(b"dummy")
        (self.root / ".tmp").mkdir()
        (self.root / ".tmp" / "temp.log").write_bytes(b"dummy")
        (self.root / ".coverage").write_bytes(b"dummy")
        (self.root / "build" / "lib").mkdir(parents=True)
        (self.root / "build" / "lib" / "dummy.py").write_bytes(b"dummy")
        (self.root / "dist" / "dummy.whl").mkdir(parents=True)
        (self.root / "mcp_runtime_sentinel.egg-info").mkdir()
        (self.root / "mcp_runtime_sentinel.egg-info" / "PKG-INFO").write_bytes(b"dummy")
        (self.root / "certs").mkdir()
        (self.root / "certs" / "server.key").write_bytes(b"dummy")
        (self.root / "sentinel.state").write_bytes(b"dummy")
        (self.root / "sentinel.state.json").write_bytes(b"dummy")
        (self.root / "test.audit.jsonl").write_bytes(b"dummy")
        (self.root / "debug.log").write_bytes(b"dummy")
        (self.root / "tests" / "test_example.pyc").write_bytes(b"dummy")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_zip_archive_excludes_junk_and_includes_required(self) -> None:
        out_zip = self.root / "dist" / "release.zip"
        archive_path = build_release_archive(root=self.root, output=out_zip, archive_format="zip")
        self.assertTrue(archive_path.exists())

        with zipfile.ZipFile(archive_path, "r") as zf:
            names = set(zf.namelist())

        # Assert required files are present
        self.assertIn("pyproject.toml", names)
        self.assertIn("LICENSE", names)
        self.assertIn("sentinel/__init__.py", names)
        self.assertIn("sentinel/gateway.py", names)
        self.assertIn("tests/test_example.py", names)

        # Assert none of the excluded paths/files are present
        excluded_markers = [
            ".venv",
            ".venv-repro",
            "__pycache__",
            ".pyc",
            ".pyo",
            ".mypy_cache",
            ".ruff_cache",
            ".pytest_cache",
            ".tmp",
            ".coverage",
            "build",
            "dist",
            ".egg-info",
            "certs",
            ".state",
            ".audit.jsonl",
            ".log",
        ]
        for name in names:
            for marker in excluded_markers:
                self.assertNotIn(
                    f"/{marker}/",
                    f"/{name}/",
                    f"Excluded marker {marker} found in archive entry {name}",
                )
                if marker.startswith("."):
                    self.assertFalse(
                        name.endswith(marker),
                        f"Excluded suffix {marker} found on archive entry {name}",
                    )

    def test_build_tar_archive_excludes_junk(self) -> None:
        out_tar = self.root / "dist" / "release.tar.gz"
        archive_path = build_release_archive(root=self.root, output=out_tar, archive_format="tar.gz")
        self.assertTrue(archive_path.exists())

        with tarfile.open(archive_path, "r:gz") as tf:
            names = set(tf.getnames())

        self.assertIn("pyproject.toml", names)
        self.assertIn("LICENSE", names)
        self.assertIn("sentinel/gateway.py", names)

        for name in names:
            self.assertFalse(name.startswith(".venv"))
            self.assertFalse(name.endswith(".pyc"))
            self.assertFalse(name.endswith(".log"))


if __name__ == "__main__":
    unittest.main()

