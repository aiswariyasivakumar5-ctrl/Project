from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

import numpy as np

TOKEN = re.compile(r"[a-zA-Z0-9_]+")
SENSITIVE = re.compile(r"(token|secret|password|credential|private[_-]?key|ssn)", re.I)


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN.findall(value) if len(token) > 2}


def lexical_intent_mismatch(intent: str, tool_name: str, arguments: dict[str, Any]) -> float:
    """Legacy lexical token overlap matcher; sensitive to paraphrasing."""
    intended = _tokens(intent)
    operation = _tokens(tool_name.replace("_", " ")) | _tokens(" ".join(arguments.keys()))
    if not intended or not operation:
        return 0.5
    overlap = len(intended & operation) / math.sqrt(len(intended) * len(operation))
    return float(max(0.0, min(1.0, 1.0 - overlap)))


def intent_mismatch(intent: str, tool_name: str, arguments: dict[str, Any]) -> float:
    """Dependency-free normalized intent mismatch matcher with synonym canonicalization."""
    from .semantic_intent import semantic_intent_mismatch

    return semantic_intent_mismatch(intent, tool_name, arguments)


def response_shape(value: Any) -> tuple[int, int, int]:
    if isinstance(value, dict):
        nested = sum(isinstance(v, (dict, list)) for v in value.values())
        return len(value), nested, len(json.dumps(value, default=str))
    if isinstance(value, list):
        nested = sum(isinstance(v, (dict, list)) for v in value)
        return len(value), nested, len(json.dumps(value, default=str))
    return 1, 0, len(str(value))


def extract_features(event: Any) -> np.ndarray:
    args_text = json.dumps(event.arguments, sort_keys=True, default=str)
    response_text = json.dumps(event.response, sort_keys=True, default=str)
    shape_size, nested, response_bytes = response_shape(event.response)
    types = Counter(type(v).__name__ for v in event.arguments.values())
    return np.asarray(
        [
            math.log1p(max(event.latency_ms, 0.0)),
            math.log1p(len(event.arguments)),
            math.log1p(len(args_text)),
            math.log1p(response_bytes),
            math.log1p(shape_size),
            math.log1p(nested),
            float(event.success),
            float(event.side_effect),
            float(bool(SENSITIVE.search(args_text))),
            float(bool(SENSITIVE.search(response_text))),
            math.log1p(types["str"]),
            math.log1p(types["int"] + types["float"]),
        ],
        dtype=np.float64,
    )
