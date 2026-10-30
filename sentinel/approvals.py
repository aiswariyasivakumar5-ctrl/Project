"""Trusted in-process review evidence; never populated from client headers."""

import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewApproval:
    reviewer: str
    evidence_ref: str
    expires_at: float


class ReviewApprovals:
    def __init__(self, max_entries=4096, clock=time.monotonic):
        self.max_entries, self.clock = max_entries, clock
        self.entries = {}
        self.last_time = None

    def _now(self):
        now = self.clock()
        if (
            type(now) not in (int, float)
            or not math.isfinite(now)
            or (self.last_time is not None and now < self.last_time)
        ):
            self.entries.clear()
            raise ValueError("invalid review approval clock")
        self.last_time = now
        self.entries = {key: value for key, value in self.entries.items() if now < value.expires_at}
        return now

    def grant(self, key, *, reviewer, evidence_ref, ttl=300):
        if not all(
            isinstance(value, str) and 0 < len(value.strip()) <= 512
            for value in (reviewer, evidence_ref)
        ):
            raise ValueError("reviewer and evidence reference required")
        if type(ttl) not in (int, float) or not 0 < ttl <= 86400:
            raise ValueError("approval TTL must be positive and at most one day")
        now = self._now()
        if key not in self.entries and len(self.entries) >= self.max_entries:
            raise ValueError("review approval capacity exhausted")
        self.entries[key] = ReviewApproval(reviewer, evidence_ref, now + ttl)

    def get(self, key):
        try:
            self._now()
        except ValueError:
            return None
        return self.entries.get(key)

    def consume(self, key):
        return self.entries.pop(key, None)
