"""Build a clean source release archive for MCP Runtime Sentinel.

Excludes virtual environments, caches, temporary files, build artifacts,
runtime state files, and logs.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tarfile
from typing import Sequence
import zipfile

EXCLUDED_DIR_NAMES = {
    ".venv",
    ".venv-repro",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".tmp",
    "build",
    "dist",
    "certs",
    ".git",
}

EXCLUDED_FILE_EXACT = {
    ".coverage",
}

EXCLUDED_FILE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".state",
    ".state.json",
    ".audit.jsonl",
    ".log",
)


def is_excluded_dir(name: str) -> bool:
    if name in EXCLUDED_DIR_NAMES:
        return True
    if name.endswith(".egg-info"):
        return True
    return False


def is_excluded_file(name: str) -> bool:
    if name in EXCLUDED_FILE_EXACT:
        return True
    if name.endswith(EXCLUDED_FILE_SUFFIXES):
        return True
    return False


def collect_files_from_git(root: Path) -> list[Path] | None:
    if not (root / ".git").is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            path = root / line
            # Even if tracked, exclude any junk patterns
            parts = Path(line).parts
            if any(is_excluded_dir(p) for p in parts[:-1]):
                continue
            if is_excluded_file(parts[-1]):
                continue
            if path.is_file():
                files.append(path)
        return files
    except (subprocess.SubprocessError, OSError):
        return None


def collect_files_from_walk(root: Path, output_file: Path | None = None) -> list[Path]:
    collected: list[Path] = []
    output_resolved = output_file.resolve() if output_file else None

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if not is_excluded_dir(d)]

        current_dir = Path(dirpath)
        for f in filenames:
            if is_excluded_file(f):
                continue
            file_path = current_dir / f
            if output_resolved and file_path.resolve() == output_resolved:
                continue
            collected.append(file_path)

    return sorted(collected)


def build_release_archive(
    root: str | Path = ".",
    output: str | Path | None = None,
    archive_format: str = "zip",
) -> Path:
    root_path = Path(root).resolve()

    if output is None:
        dist_dir = root_path / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        ext = ".tar.gz" if archive_format in ("tar.gz", "tgz") else ".zip"
        output_path = dist_dir / f"mcp-runtime-sentinel-0.2.0{ext}"
    else:
        output_path = Path(output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.name.endswith((".tar.gz", ".tgz")):
            archive_format = "tar.gz"
        elif output_path.name.endswith(".zip"):
            archive_format = "zip"

    # 1. Try git ls-files if .git exists, otherwise fall back to directory walk
    files = collect_files_from_git(root_path)
    if files is None:
        files = collect_files_from_walk(root_path, output_file=output_path)

    # 2. Build archive
    if archive_format in ("tar.gz", "tgz"):
        with tarfile.open(output_path, "w:gz") as tar:
            for file_path in files:
                arcname = file_path.relative_to(root_path).as_posix()
                tar.add(file_path, arcname=arcname)
    else:
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in files:
                arcname = file_path.relative_to(root_path).as_posix()
                zf.write(file_path, arcname=arcname)

    return output_path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create a clean MCP Runtime Sentinel release archive.")
    parser.add_argument("--root", default=".", help="Root directory of the repository")
    parser.add_argument("--output", default=None, help="Output archive path")
    parser.add_argument(
        "--format",
        choices=["zip", "tar.gz"],
        default="zip",
        help="Archive format (default: zip)",
    )
    args = parser.parse_args(argv)

    archive = build_release_archive(
        root=args.root,
        output=args.output,
        archive_format=args.format,
    )
    size_bytes = archive.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"Created release archive: {archive}")
    print(f"Size: {size_mb:.2f} MB ({size_bytes:,} bytes)")


if __name__ == "__main__":
    main()

