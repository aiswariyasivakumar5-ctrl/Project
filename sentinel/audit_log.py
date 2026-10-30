"""Append-only, hash-chained JSONL audit storage with restricted permissions."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _secure_chmod(path: Path) -> bool:
    """Ensure path has 0o600 permissions on POSIX systems. Return True if tightened."""
    if os.name == "nt" or not path.exists():
        return False
    try:
        current = path.stat().st_mode & 0o777
        if current != 0o600:
            os.chmod(path, 0o600)
            return True
    except OSError:
        pass
    return False


class AuditLog:
    def __init__(self, path: str | Path, *, max_bytes: int = 10_485_760):
        if max_bytes < 1024:
            raise ValueError("audit rotation size must be at least 1024 bytes")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.logger = logging.getLogger("sentinel.audit_log")
        self._lock = threading.Lock()
        if self.path.exists() and _secure_chmod(self.path):
            self.logger.warning(
                json.dumps({"event": "tightened_audit_permissions", "path": str(self.path)})
            )
        rotated = self.path.with_name(self.path.name + ".1")
        if rotated.exists() and _secure_chmod(rotated):
            self.logger.warning(
                json.dumps({"event": "tightened_audit_permissions", "path": str(rotated)})
            )
        self._previous_hash = self._load_previous_hash()

    def _load_previous_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return GENESIS
        valid, digest = verify_audit_log(self.path)
        if not valid:
            raise ValueError("existing audit log has an invalid hash chain")
        return digest

    def append(self, record: dict[str, Any]) -> None:
        with self._lock:
            chained = dict(record)
            chained["previous_hash"] = self._previous_hash
            encoded = json.dumps(chained, sort_keys=True, separators=(",", ":"), allow_nan=False)
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            output = dict(chained, record_hash=digest)
            line = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
            if len(line.encode("utf-8")) > self.max_bytes:
                raise ValueError("audit record exceeds configured rotation size")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if (
                self.path.exists()
                and self.path.stat().st_size + len(line.encode()) > self.max_bytes
            ):
                rotated = self.path.with_name(self.path.name + ".1")
                if rotated.exists():
                    rotated.unlink()
                os.replace(self.path, rotated)
                _secure_chmod(rotated)
                self._previous_hash = GENESIS
                output["previous_hash"] = GENESIS
                unsigned = {k: v for k, v in output.items() if k != "record_hash"}
                encoded = json.dumps(
                    unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
                )
                digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                output["record_hash"] = digest
                line = (
                    json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    + "\n"
                )

            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            fd = os.open(self.path, flags, 0o600)
            if os.name != "nt":
                try:
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass
            with open(fd, "a", encoding="utf-8", newline="\n", closefd=True) as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            self._previous_hash = digest


def verify_audit_log(path: str | Path) -> tuple[bool, str]:
    previous = GENESIS
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                item = json.loads(line)
                if not isinstance(item, dict):
                    return False, f"line {line_number}: record is not an object"
                claimed = item.pop("record_hash", None)
                if item.get("previous_hash") != previous or not isinstance(claimed, str):
                    return False, f"line {line_number}: broken hash link"
                actual = hashlib.sha256(
                    json.dumps(
                        item, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode()
                ).hexdigest()
                if not hmac.compare_digest(claimed, actual):
                    return False, f"line {line_number}: hash mismatch"
                previous = claimed
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, f"cannot verify audit log: {exc}"
    return True, previous
