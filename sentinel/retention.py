"""Finite evidence windows and fail-closed identity admission limits."""

from dataclasses import dataclass, fields


class StateCapacityError(ValueError):
    pass


@dataclass(frozen=True)
class RetentionConfig:
    audit_records: int = 10_000
    causal_nodes: int = 10_000
    quarantine_per_server: int = 256
    provenance_claims: int = 10_000
    servers: int = 256
    sessions: int = 4096
    tools_per_server: int = 256
    transitions_per_session: int = 1024
    memory_entries: int = 4096

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{item.name} must be a positive integer")
