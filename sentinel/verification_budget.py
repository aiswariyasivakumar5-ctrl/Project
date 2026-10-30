"""Bounded, label-free verification scheduler for offline research only."""

import copy
import math
import random
from dataclasses import dataclass

POLICIES = ("never", "every", "first", "periodic", "random", "uncertainty")


@dataclass
class Candidate:
    index: int
    event: object
    uncertainty: float


class VerificationBudget:
    def __init__(self, policy, *, seed=0, window=8, allowance=2, delay=0, ttl=16):
        if policy not in POLICIES:
            raise ValueError("unknown policy")
        if any(type(v) is not int for v in (window, allowance, delay, ttl)):
            raise ValueError("integer configuration required")
        if window < 1 or not 0 <= allowance <= window or delay < 0 or ttl < 1:
            raise ValueError("invalid budget configuration")
        self.policy, self.window, self.allowance = policy, window, allowance
        self.delay, self.ttl = delay, ttl
        self.rng = random.Random(seed)
        self.candidates, self.pending = [], []
        self.last_index = -1
        self.queries = 0

    def observe(self, index, event, uncertainty, eligible):
        if type(index) is not int or index != self.last_index + 1:
            raise ValueError("observations must arrive once in consecutive order")
        if not math.isfinite(uncertainty) or not 0 <= uncertainty <= 1:
            raise ValueError("invalid uncertainty")
        self.last_index = index
        if eligible and self.policy != "never":
            self.candidates.append(Candidate(index, copy.deepcopy(event), uncertainty))

    def select(self, verifier):
        """Only observed complete windows may be selected; failures cost a query."""
        if (self.last_index + 1) % self.window:
            return []
        items, self.candidates = self.candidates, []
        if self.policy == "every":
            chosen = items
        elif self.policy == "uncertainty":
            chosen = sorted(items, key=lambda c: (-c.uncertainty, c.index))[: self.allowance]
        elif self.policy == "random":
            chosen = self.rng.sample(items, min(self.allowance, len(items)))
        elif self.policy == "periodic":
            slots = {i * self.window // self.allowance for i in range(self.allowance)}
            chosen = [c for c in items if c.index % self.window in slots]
        else:
            chosen = items[: self.allowance]
        records = []
        for candidate in chosen:
            self.queries += 1
            try:
                answer = verifier(copy.deepcopy(candidate.event), candidate.index)
            except Exception:
                answer = None
            answer = answer if type(answer) is bool else None
            self.pending.append((self.last_index + self.delay, candidate, answer))
            records.append(
                {
                    "source_index": candidate.index,
                    "selected_at": self.last_index,
                    "due_at": self.last_index + self.delay,
                    "feedback": answer,
                }
            )
        return records

    def deliver(self, now, capability_digests, learn):
        """Consume once, expire old evidence, and never grant on unknown feedback."""
        ready = [p for p in self.pending if p[0] <= now]
        self.pending = [p for p in self.pending if p[0] > now]
        records = []
        for _due, candidate, answer in ready:
            event = candidate.event
            scope = (event.server_id, event.tool_name)
            valid_scope = (
                scope in capability_digests and capability_digests[scope] == event.capability_digest
            )
            status = (
                "expired"
                if now - candidate.index > self.ttl
                else "scope_changed"
                if not valid_scope
                else "accepted"
                if answer is True
                else "rejected"
                if answer is False
                else "unavailable"
            )
            if status == "accepted":
                learn(copy.deepcopy(event))
            records.append(
                {
                    "source_index": candidate.index,
                    "delivered_at": now,
                    "status": status,
                    "delay": now - candidate.index,
                }
            )
        return records
