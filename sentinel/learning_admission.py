"""Opt-in, process-local learning admission experiment; not patent novelty.

Owns a private engine. All reads return copies. Never attach a concurrently used
live gateway engine. Authority setters and verifier are trusted application APIs.
No persistence, cryptographic approvals, unlearning, or distributed guarantees.
"""

import copy
import hashlib
import json
import math
import threading
import time
import uuid
from dataclasses import asdict, dataclass

from .engine import SentinelEngine
from .models import Interaction

POLICIES = ("verification_only", "expiry_only", "capability_only", "transactional", "combined")


def event_digest(event):
    """Version-1 canonical JSON; validates and binds all Interaction fields."""
    data = asdict(event)
    Interaction.from_dict(data)
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Authority:
    generation: int
    active: bool
    value: str


@dataclass(frozen=True)
class Approval:
    update_id: str
    digest: str
    scope: tuple
    permission_generation: int
    capability_generation: int
    expires: float
    evidence_ref: str


class LearningAdmission:
    """Standard transactional baseline and combined policy intentionally match.

    Preparing a copied model occurs outside the coordinator lock. Final checks,
    replay ledger and model publication are serialized by one pointer swap under
    that lock. A concurrent model commit causes retry, never a lost update.
    Rejected tickets are terminal; preparation errors/conflicts can be retried.
    Capacity never evicts replay identities; start a new experiment when full.
    """

    def __init__(
        self, *, engine=None, verifier=None, clock=time.monotonic, policy="combined", capacity=1024
    ):
        if policy not in POLICIES or type(capacity) is not int or capacity < 1:
            raise ValueError("invalid policy or capacity")
        self.policy, self.capacity = policy, capacity
        self._clock, self._verifier = clock, verifier
        self._lock = threading.Lock()
        self._last_time = None
        self._clock_failed = False
        self._permissions, self._capabilities, self._tickets = {}, {}, {}
        # engine, model version, consumed update IDs, terminal ticket decisions
        self._state = (
            copy.deepcopy(engine) if engine is not None else SentinelEngine(),
            0,
            frozenset(),
            {},
        )

    def _now(self):
        try:
            now = self._clock()
            if type(now) not in (float, int) or not math.isfinite(now):
                raise ValueError("invalid clock")
            if self._last_time is not None and now < self._last_time:
                raise ValueError("clock rollback")
            self._last_time = now
        except Exception:
            self._clock_failed = True
        if self._clock_failed:
            raise ValueError("clock unavailable; admission disabled")
        return now

    def _set(self, registry, scope, active, value):
        if (
            not isinstance(scope, tuple)
            or len(scope) != 2
            or any(not isinstance(x, str) or not x for x in scope)
            or type(active) is not bool
            or not isinstance(value, str)
            or not value
        ):
            raise ValueError("invalid authority")
        with self._lock:
            if scope not in registry and len(registry) >= self.capacity:
                raise ValueError("authority capacity exhausted")
            previous = registry.get(scope)
            registry[scope] = Authority(
                1 if previous is None else previous.generation + 1, active, value
            )

    def set_permission(self, scope, active):
        """Trusted operator sets permission for baseline-learning at this scope."""
        self._set(self._permissions, scope, active, "baseline-learning")

    def set_capability(self, scope, digest):
        """Every call advances generation, including change-back/re-enrollment."""
        self._set(self._capabilities, scope, True, digest)

    def _authority(self, scope):
        permission, capability = self._permissions.get(scope), self._capabilities.get(scope)
        if permission is None or capability is None or not permission.active:
            raise ValueError("missing or revoked authority")
        return permission, capability

    def approve(self, update_id, event, *, ttl=60.0, evidence_ref):
        if (
            not isinstance(update_id, str)
            or not update_id
            or not isinstance(evidence_ref, str)
            or not evidence_ref
            or type(ttl) not in (int, float)
            or not math.isfinite(ttl)
            or ttl <= 0
        ):
            raise ValueError("invalid approval fields")
        event = copy.deepcopy(event)
        digest = event_digest(event)
        if not event.success or event.side_effect:
            raise ValueError("only successful read-only evidence supported")
        scope = (event.server_id, event.tool_name)
        with self._lock:
            now = self._now()
            permission, capability = self._authority(scope)
            if capability.value != event.capability_digest:
                raise ValueError("capability mismatch")
        try:
            verified = self._verifier(copy.deepcopy(event)) is True if self._verifier else False
        except Exception:
            verified = False
        if not verified:
            raise ValueError("verification failed or unavailable")
        with self._lock:
            current = self._now()
            if self._authority(scope) != (permission, capability):
                raise ValueError("authority changed during verification")
            if current >= now + ttl or not math.isfinite(now + ttl):
                raise ValueError("approval expired during verification")
            if len(self._tickets) >= self.capacity:
                raise ValueError("approval capacity exhausted")
            if any(a.update_id == update_id for a in self._tickets.values()):
                raise ValueError("duplicate update identity")
            ticket = uuid.uuid4().hex
            self._tickets[ticket] = Approval(
                update_id,
                digest,
                scope,
                permission.generation,
                capability.generation,
                now + ttl,
                evidence_ref,
            )
            return ticket

    def _check(self, ticket, digest):
        approval = self._tickets.get(ticket)
        if approval is None:
            return "unknown"
        if ticket in self._state[3] or approval.update_id in self._state[2]:
            return "replay"
        if digest != approval.digest:
            return "binding_mismatch"
        try:
            now = self._now()
        except ValueError:
            return "clock_invalid"
        if self.policy in ("expiry_only", "transactional", "combined") and now >= approval.expires:
            return "expired"
        if self.policy in ("capability_only", "transactional", "combined"):
            capability = self._capabilities.get(approval.scope)
            if capability is None or capability.generation != approval.capability_generation:
                return "capability_changed"
        if self.policy in ("transactional", "combined"):
            permission = self._permissions.get(approval.scope)
            if (
                permission is None
                or not permission.active
                or permission.generation != approval.permission_generation
            ):
                return "permission_changed"
        return None

    def _reject(self, ticket, reason):
        if ticket in self._tickets and ticket not in self._state[3]:
            model, version, consumed, decisions = self._state
            self._state = (model, version, consumed, {**decisions, ticket: reason})
        return reason

    def commit(self, ticket, event):
        event = copy.deepcopy(event)
        try:
            digest = event_digest(event)
        except (ValueError, TypeError):
            return "invalid_event"
        with self._lock:
            reason = self._check(ticket, digest)
            if reason:
                return self._reject(ticket, reason)
            staged = copy.deepcopy(self._state[0])
            version = self._state[1]
        try:
            # Historical learning must not rewind sequence state.
            staged.learn_approved(event, update_sequence=False)
        except Exception:
            return "preparation_failed"
        with self._lock:
            reason = self._check(ticket, digest)
            if reason:
                return self._reject(ticket, reason)
            if self._state[1] != version:
                return "retry_model_conflict"
            approval = self._tickets[ticket]
            new_state = (
                staged,
                version + 1,
                self._state[2] | {approval.update_id},
                {**self._state[3], ticket: "committed"},
            )
            self._state = new_state
            return "committed"

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._state)
