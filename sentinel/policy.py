"""Optional JSON-only pre-execution tool policy."""

from __future__ import annotations

import json
import re
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .validation import validate_json


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    risk_class: str
    schema: Draft202012Validator
    approval_required: bool
    denied_by_default: bool
    max_argument_bytes: int
    max_argument_depth: int
    patterns: list[re.Pattern[str]]
    paths: set[str]
    rate_limit: float
    rate_burst: int


def _default_closed_objects(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_default_closed_objects(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _default_closed_objects(value) for key, value in schema.items()}
    if result.get("type") == "object":
        result.setdefault("additionalProperties", False)
    return result

class PreExecutionPolicy:
    def __init__(self, path: str | Path):
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read policy file: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != {"tools"} or not isinstance(raw["tools"], dict):
            raise ValueError('policy must be a JSON object with a "tools" object')
        self.rules: dict[str, ToolPolicy] = {}
        for tool, rule in raw["tools"].items():
            if not isinstance(tool, str) or not tool or not isinstance(rule, dict):
                raise ValueError("policy tool rules must map names to objects")
            if set(rule) - {
                "max_argument_bytes",
                "forbidden_patterns",
                "forbidden_paths",
                "rate_limit",
                "rate_burst",
                "approval_required",
                "risk_class",
                "input_schema",
                "max_argument_depth",
            }:
                raise ValueError(f"unknown policy field for {tool}")
            maximum = rule.get("max_argument_bytes", 1_048_576)
            if type(maximum) is not int or not 1 <= maximum <= 1_048_576:
                raise ValueError(f"invalid max_argument_bytes for {tool}")
            patterns = rule.get("forbidden_patterns", [])
            paths = rule.get("forbidden_paths", [])
            if not isinstance(patterns, list) or any(not isinstance(p, str) for p in patterns):
                raise ValueError(f"invalid forbidden_patterns for {tool}")
            if not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
                raise ValueError(f"invalid forbidden_paths for {tool}")
            try:
                compiled = [re.compile(pattern) for pattern in patterns]
            except re.error as exc:
                raise ValueError(f"invalid forbidden pattern for {tool}: {exc}") from exc
            rate, burst = rule.get("rate_limit", 0.0), rule.get("rate_burst", 0)
            if type(rate) not in (int, float) or rate < 0 or type(burst) is not int or burst < 0:
                raise ValueError(f"invalid tool rate limit for {tool}")
            if rate and burst < 1:
                raise ValueError(f"rate_burst is required for {tool}")
            risk_class = rule.get("risk_class")
            if not isinstance(risk_class, str) or risk_class not in {
                "read",
                "write",
                "destructive",
            }:
                raise ValueError(f"invalid or missing risk_class for {tool}")
            schema = rule.get("input_schema")
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise ValueError(f"input_schema for {tool} must be an object schema")
            schema = _default_closed_objects(deepcopy(schema))
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:
                raise ValueError(f"invalid input_schema for {tool}: {exc}") from exc
            max_depth = rule.get("max_argument_depth", 32)
            if type(max_depth) is not int or not 1 <= max_depth <= 64:
                raise ValueError(f"invalid max_argument_depth for {tool}")
            default_approval = risk_class == "write"
            approval = rule.get("approval_required", default_approval)
            if type(approval) is not bool:
                raise ValueError(f"approval_required must be boolean for {tool}")
            denied_by_default = risk_class == "destructive" and not approval
            self.rules[tool] = ToolPolicy(
                risk_class=risk_class,
                schema=Draft202012Validator(schema),
                approval_required=approval,
                denied_by_default=denied_by_default,
                max_argument_bytes=maximum,
                max_argument_depth=max_depth,
                patterns=compiled,
                paths=set(paths),
                rate_limit=float(rate),
                rate_burst=burst,
            )
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}

    def _consume_rate(self, tool: str, client_id: str, rule: ToolPolicy) -> bool:
        if not rule.rate_limit:
            return True
        now = time.monotonic()
        key = f"{client_id}:{tool}"
        with self._lock:
            tokens, updated = self._buckets.get(key, (float(rule.rate_burst), now))
            tokens = min(float(rule.rate_burst), tokens + (now - updated) * rule.rate_limit)
            if tokens < 1:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1, now)
            return True

    def evaluate(
        self, tool: str, arguments: dict[str, Any], client_id: str
    ) -> tuple[list[str], bool]:
        rule = self.rules.get(tool)
        if rule is None:
            return ["tool is not classified by operator policy"], False
        serialized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        reasons: list[str] = []
        if rule.denied_by_default:
            reasons.append("destructive tool denied by default")
        if len(serialized.encode("utf-8")) > rule.max_argument_bytes:
            reasons.append("policy argument size limit")
        try:
            validate_json(arguments, max_depth=rule.max_argument_depth)
        except ValueError:
            reasons.append("policy argument depth limit")
        if any(error for error in rule.schema.iter_errors(arguments)):
            reasons.append("policy argument schema validation failed")
        if any(pattern.search(serialized) for pattern in rule.patterns):
            reasons.append("policy forbidden argument pattern")
        paths: set[str] = set()

        def visit(value: Any, prefix: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    current = f"{prefix}.{key}" if prefix else str(key)
                    paths.add(current)
                    visit(child, current)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{prefix}[{index}]")

        visit(arguments)
        if paths & rule.paths:
            reasons.append("policy forbidden argument path")
        if not self._consume_rate(tool, client_id, rule):
            reasons.append("policy per-tool rate limit")
        return reasons, rule.approval_required

    def risk_class(self, tool: str) -> str | None:
        rule = self.rules.get(tool)
        return rule.risk_class if rule else None

    def classified_tools(self) -> set[str]:
        return set(self.rules)
