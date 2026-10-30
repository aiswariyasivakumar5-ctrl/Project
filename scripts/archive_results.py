"""Archive large experimental results directories and generate MANIFEST.json."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LARGE_DIRS = [
    "results/novelty/publication_scale_v3",
    "results/novelty/publication_scale_v2",
    "results/novelty/publication_scale_complete",
    "results/novelty/publication-scale-20261016",
    "results/novelty/publication-scale-20260921",
    "results/baselines_20seed",
    "results/ablations_20seed",
    "results/adaptation/matched_poisoning_20seed",
]


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_directory_manifest(rel_dir: str) -> dict:
    dir_path = ROOT / rel_dir
    if not dir_path.exists():
        return {"exists": False}

    files = [p for p in sorted(dir_path.glob("**/*")) if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    
    # Compute combined directory hash over sorted relative paths and file hashes
    hasher = hashlib.sha256()
    file_entries = {}
    for p in files:
        rel = str(p.relative_to(dir_path)).replace("\\", "/")
        f_hash = file_sha256(p)
        file_entries[rel] = {"size_bytes": p.stat().st_size, "sha256": f_hash}
        hasher.update(f"{rel}:{f_hash}\n".encode("utf-8"))

    return {
        "exists": True,
        "path": rel_dir,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "composite_sha256": hasher.hexdigest(),
        "files": file_entries,
    }


def build_archive(rel_dir: str, out_dir: Path) -> str:
    dir_path = ROOT / rel_dir
    tar_name = rel_dir.replace("/", "_") + ".tar.gz"
    tar_path = out_dir / tar_name
    print(f"Creating archive {tar_name}...", flush=True)
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(dir_path, arcname=dir_path.name)
    tar_hash = file_sha256(tar_path)
    print(f"Archive created: {tar_name} ({tar_path.stat().st_size / 1024 / 1024:.2f} MB, sha256={tar_hash[:16]}...)")
    return tar_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-tarballs", action="store_true", help="Build compressed tarballs in archives/")
    args = parser.parse_args()

    manifest = {"manifest_version": "1.0", "directories": {}}
    print("Computing SHA-256 digests across results directories...", flush=True)

    archive_dir = ROOT / "archives"
    if args.build_tarballs:
        archive_dir.mkdir(parents=True, exist_ok=True)

    for d in LARGE_DIRS:
        print(f"Hashing {d}...", flush=True)
        info = compute_directory_manifest(d)
        if not info.get("exists"):
            continue
        if args.build_tarballs:
            info["tarball_sha256"] = build_archive(d, archive_dir)
        manifest["directories"][d] = info

    manifest_path = ROOT / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved manifest to {manifest_path} (composite digest tracking {len(manifest['directories'])} directories).")


if __name__ == "__main__":
    main()
