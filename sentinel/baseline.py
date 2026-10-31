"""Operator-controlled baseline approval, export, and rollback operations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .audit_log import AuditLog
from .gateway import GatewayConfig, SentinelGateway
from .validation import load_json


def _digest(state: dict[str, Any]) -> str:
    baseline_content = {
        key: state[key]
        for key in ("engine", "novelty", "tool_metadata", "capability_digest")
    }
    canonical = json.dumps(
        baseline_content, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _gateway_for_state(path: Path) -> SentinelGateway:
    with path.open("rb") as stream:
        raw = load_json(stream.read(32 * 1024 * 1024 + 1))
    if not isinstance(raw, dict) or not isinstance(raw.get("server_id"), str):
        raise ValueError("baseline state has no valid server_id")
    gateway = SentinelGateway(
        GatewayConfig(
            "http://127.0.0.1",
            raw["server_id"],
            novelty=raw.get("novelty") is not None,
        )
    )
    gateway.load_state(path)
    return gateway


def _backup(gateway: SentinelGateway, state_path: Path, digest: str) -> Path:
    history = state_path.with_name(state_path.name + ".versions")
    history.mkdir(parents=True, exist_ok=True)
    version_path = history / f"{digest}.json"
    if not version_path.exists():
        gateway.save_state(version_path)
    return version_path


def _audit(
    audit_log: str | Path,
    *,
    action: str,
    actor: str,
    version: int,
    digest_before: str,
    digest_after: str,
    diff_summary: str,
) -> None:
    AuditLog(audit_log).append(
        {
            "event": "baseline_change",
            "action": action,
            "actor": actor,
            "timestamp": time.time(),
            "version": version,
            "digest_before": digest_before,
            "digest_after": digest_after,
            "diff_summary": diff_summary,
        }
    )


def manage_baseline(
    action: str,
    state_file: str | Path,
    *,
    actor: str | None,
    audit_log: str | Path | None,
    output: str | Path | None = None,
    version_file: str | Path | None = None,
) -> None:
    if action not in {"export", "approve", "rollback"}:
        raise ValueError("unsupported baseline action")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 128:
        raise ValueError("baseline operations require a nonempty --actor of at most 128 characters")
    if audit_log is None:
        raise ValueError("baseline operations require --audit-log")
    path = Path(state_file)
    gateway = _gateway_for_state(path)
    state = gateway.export_state()
    digest_before = _digest(state)

    if action == "export":
        if output is None:
            raise ValueError("baseline export requires --output")
        if gateway.baseline_metadata["status"] != "approved":
            raise ValueError("only an approved baseline can be exported")
        output_path = Path(output)
        if output_path.exists():
            raise FileExistsError(f"refusing to overwrite baseline export: {output_path}")
        gateway.save_state(output_path)
        _audit(
            audit_log,
            action=action,
            actor=actor,
            version=gateway.baseline_metadata["version"],
            digest_before=digest_before,
            digest_after=digest_before,
            diff_summary=f"exported approved baseline to {output_path.name}",
        )
        return

    if action == "approve":
        if gateway.baseline_metadata["status"] == "approved":
            raise ValueError("baseline is already approved")
        old_bytes = path.read_bytes()
        _backup(gateway, path, digest_before)
        now = time.time()
        gateway.baseline_metadata.update(
            {
                "status": "approved",
                "approved_by": actor,
                "approved_at": now,
                "changed_by": actor,
                "changed_at": now,
                "diff_summary": f"operator approved baseline {digest_before[:12]}",
            }
        )
        gateway.save_state(path)
        try:
            _audit(
                audit_log,
                action=action,
                actor=actor,
                version=gateway.baseline_metadata["version"],
                digest_before=digest_before,
                digest_after=digest_before,
                diff_summary=gateway.baseline_metadata["diff_summary"],
            )
        except Exception:
            _atomic_restore(path, old_bytes)
            raise
        return

    if version_file is None:
        raise ValueError("baseline rollback requires --version-file")
    target_path = Path(version_file)
    target = _gateway_for_state(target_path)
    if target.config.server_id != gateway.config.server_id:
        raise ValueError("rollback baseline belongs to a different server")
    if target.baseline_metadata["status"] != "approved":
        raise ValueError("rollback target must be an approved baseline export")
    old_bytes = path.read_bytes()
    _backup(gateway, path, digest_before)
    target_state = target.export_state()
    digest_after = _digest(target_state)
    now = time.time()
    target.baseline_metadata.update(
        {
            "version": gateway.baseline_metadata["version"] + 1,
            "status": "approved",
            "approved_by": actor,
            "approved_at": now,
            "changed_by": actor,
            "changed_at": now,
            "diff_summary": f"rollback from {digest_before[:12]} to {digest_after[:12]}",
        }
    )
    target.save_state(path)
    try:
        _audit(
            audit_log,
            action=action,
            actor=actor,
            version=target.baseline_metadata["version"],
            digest_before=digest_before,
            digest_after=digest_after,
            diff_summary=target.baseline_metadata["diff_summary"],
        )
    except Exception:
        _atomic_restore(path, old_bytes)
        raise


def _atomic_restore(path: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
