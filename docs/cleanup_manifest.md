# Deletion Audit Manifest: Phase 7 Repository Cleanup

This manifest records all redundant, nested duplicate, and non-source artifacts audited and scheduled for deletion in Phase 7. All files were hashed and inventoried prior to removal.

Date: 2026-10-25
Repository: `MCP-Runtime-Sentinel`

---

## 1. High-Level Summary of Targets

| Item Path | Type | Size | Status / Reason for Deletion |
|---|---|---|---|
| `MCP-Runtime-Sentinel-main.zip` | ZIP archive | 5,827,158 bytes | Redundant bundled zip archive from legacy snapshot; bloats git repo. |
| `MCP-Runtime-Sentinel-main/` | Directory tree | 282 files (~12.4 MB) | Accidental nested checkout of repository inside repository root. |
| `MCP-Runtime-Sentinel-research-completion/` | Directory | 0 bytes (empty) | Stale empty directory from research milestone handoff. |
| `.DS_Store` | macOS desktop metadata | 8,196 bytes | Unnecessary OS metadata file tracked in git repository root. |

---

## 2. Cryptographic Checksums (Pre-Deletion)

### 2.1 Bundled Archive
- **Path**: `MCP-Runtime-Sentinel-main.zip`
- **Bytes**: 5,827,158
- **SHA-256**: `84f7211f0d9bc626fa23060eceee6b70f8aa34ae56aa69b16a151a47b6c2ad70`

### 2.2 Root Metadata File
- **Path**: `.DS_Store`
- **Bytes**: 8,196
- **SHA-256**: `a525a10ed13078fe079c23daec357a919fb33d83629f9a23878752054af2a00d`

### 2.3 Nested Directory Sample Checksums
The nested folder `MCP-Runtime-Sentinel-main/` contains 282 duplicate files mirroring an older commit of the repository. Sample digests:
- `MCP-Runtime-Sentinel-main/README.md`: `1c9ff5f2cb7349dd0d6ea861a52003c2ff233d4da34354228965f7c32bf8166c`
- `MCP-Runtime-Sentinel-main/pyproject.toml`: `ce8f3bb114fb00318536f2f9f1ff96eef146ec6c9a38ea674a24e259b3bf6da4`
- `MCP-Runtime-Sentinel-main/sentinel/engine.py`: `82f9bda05e46bfb767dd44bb5b3f2f8ebf1f3a38fa4e32049e49c716cb839b97`

---

## 3. Verification Post-Deletion

Following deletion:
1. Active package code in root `sentinel/` and `tests/` remains intact.
2. Full test suite (`python -m unittest discover -s tests`) must pass with 281+ tests.
3. Reproduction pipeline (`python scripts/reproduce_all.py --verify-only`) must pass with zero missing file errors.
