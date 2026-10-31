from __future__ import annotations

import hashlib
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AttestationChallenge:
    challenge_id: str
    server_id: str
    nonce: str
    expected_capability_digest: str
    created_at: float = 0.0
    expires_at: float = 0.0
    instruction: str = (
        "Return SHA-256(nonce + ':' + capability_digest) from a side-effect-free endpoint."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AttestationManager:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = 30.0,
        max_pending: int = 1024,
    ):
        if type(ttl_seconds) not in (int, float) or not 0 < ttl_seconds <= 86400:
            raise ValueError("attestation TTL must be finite and positive")
        if type(max_pending) is not int or max_pending < 1:
            raise ValueError("max_pending must be a positive integer")
        self.clock, self.ttl_seconds, self.max_pending = clock, ttl_seconds, max_pending
        self._last_time: float | None = None
        self._lock = threading.RLock()
        self.enrolled: dict[str, str] = {}
        self.pending: dict[str, AttestationChallenge] = {}

    def __getstate__(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if key != "_lock"}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._lock = threading.RLock()

    def _prune(self) -> float:
        now = self.clock()
        if (
            type(now) not in (int, float)
            or not math.isfinite(now)
            or (self._last_time is not None and now < self._last_time)
        ):
            self.pending.clear()
            raise ValueError("invalid or rolled-back attestation clock")
        self._last_time = now
        for key, challenge in list(self.pending.items()):
            if now >= challenge.expires_at:
                del self.pending[key]
        return now

    def discard(self, challenge_id: str) -> None:
        with self._lock:
            self.pending.pop(challenge_id, None)

    def enroll(self, server_id: str, capability_digest: str | None) -> None:
        with self._lock:
            if capability_digest and server_id not in self.enrolled:
                self.enrolled[server_id] = capability_digest

    def issue(self, server_id: str) -> AttestationChallenge | None:
        with self._lock:
            now = self._prune()
            expected = self.enrolled.get(server_id)
            if not expected:
                return None
            if not math.isfinite(now + self.ttl_seconds):
                raise ValueError("invalid attestation expiration")
            while len(self.pending) >= self.max_pending:
                del self.pending[next(iter(self.pending))]
            nonce = secrets.token_hex(16)
            challenge_id = secrets.token_hex(8)
            challenge = AttestationChallenge(
                challenge_id, server_id, nonce, expected, now, now + self.ttl_seconds
            )
            self.pending[challenge_id] = challenge
            return challenge

    def verify(
        self, challenge_id: str, capability_digest: str, echo: str, *, server_id: str
    ) -> bool:
        with self._lock:
            try:
                self._prune()
            except ValueError:
                return False
            if not all(
                isinstance(value, str)
                for value in (challenge_id, capability_digest, echo, server_id)
            ):
                return False
            challenge = self.pending.get(challenge_id)
            if challenge is None or server_id != challenge.server_id:
                return False
            del self.pending[challenge_id]
            if (
                capability_digest != challenge.expected_capability_digest
                or self.enrolled.get(server_id) != challenge.expected_capability_digest
            ):
                return False
            expected_echo = hashlib.sha256(
                f"{challenge.nonce}:{capability_digest}".encode()
            ).hexdigest()
            return (
                len(echo) == 64 and echo.isascii() and secrets.compare_digest(echo, expected_echo)
            )
