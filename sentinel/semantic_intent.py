"""Dependency-free normalized intent mismatch scorer with synonym canonicalization
and morphological reduction.
"""

from __future__ import annotations

import math
import re
from typing import Any

TOKEN = re.compile(r"[a-zA-Z0-9_]+")

# Common MCP action roots and their standard synonym sets
SYNONYMS: dict[str, str] = {
    # Read/Query actions
    "fetch": "read",
    "retrieve": "read",
    "get": "read",
    "read": "read",
    "lookup": "read",
    "query": "read",
    "search": "read",
    "display": "read",
    "view": "read",
    "show": "read",
    "examine": "read",
    "inspect": "read",
    "check": "read",
    "find": "read",
    "info": "read",
    "information": "read",
    # Delete/Destructive actions
    "delete": "delete",
    "remove": "delete",
    "erase": "delete",
    "purge": "delete",
    "destroy": "delete",
    "drop": "delete",
    "clear": "delete",
    "cancel": "delete",
    # Calculation actions
    "calculate": "calculate",
    "compute": "calculate",
    "computation": "calculate",
    "math": "calculate",
    "mathematical": "calculate",
    "addition": "calculate",
    "add": "calculate",
    "sum": "calculate",
    "solve": "calculate",
    # Export/Exfiltration actions
    "export": "export",
    "download": "export",
    "dump": "export",
    "backup": "export",
    "extract": "export",
    # Write/Update actions
    "update": "update",
    "modify": "update",
    "edit": "update",
    "alter": "update",
    "change": "update",
    "patch": "update",
    "write": "update",
    "set": "update",
    # Create actions
    "create": "create",
    "insert": "create",
    "new": "create",
    "generate": "create",
    "make": "create",
}

# Inherent action conflicts: calling a destructive tool with a passive read intent
CONFLICTING_ACTIONS: frozenset[tuple[str, str]] = frozenset(
    [
        ("delete", "read"),  # Tool is delete, intent is only read
        ("delete", "calculate"),  # Tool is delete, intent is only calculate
        ("export", "read"),  # Tool is mass export, intent is only read one record
    ]
)


def _stem(word: str) -> str:
    """Lightweight suffix stripping for morphological normalization."""
    word = word.lower()
    for suffix in ("tions", "tion", "ing", "ies", "ied", "ed", "es", "s", "ment", "able"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _canonicalize_token(token: str) -> str:
    token = token.lower()
    if token in SYNONYMS:
        return SYNONYMS[token]
    stemmed = _stem(token)
    if stemmed in SYNONYMS:
        return SYNONYMS[stemmed]
    return stemmed


def _extract_normalized_tokens(text: str) -> set[str]:
    raw = [t.lower() for t in TOKEN.findall(text) if len(t) > 2]
    normalized = set()
    for t in raw:
        canon = _canonicalize_token(t)
        normalized.add(canon)
        # Also keep original stem for domain terms
        normalized.add(_stem(t))
    return normalized


def semantic_intent_mismatch(intent: str, tool_name: str, arguments: dict[str, Any]) -> float:
    """Compute semantic intent mismatch between user intent and target operation.

    Dependency-free, robust against paraphrasing and synonym substitution, while
    rigorously detecting deceptive intent masking and empty authorizations.
    """
    intended = _extract_normalized_tokens(intent)

    # Build operation representation from tool name and argument keys & string values
    tool_tokens = _extract_normalized_tokens(tool_name.replace("_", " "))
    arg_texts = list(arguments.keys())
    for v in arguments.values():
        if isinstance(v, str):
            arg_texts.append(v)
    arg_tokens = _extract_normalized_tokens(" ".join(arg_texts))
    operation = tool_tokens | arg_tokens

    # Empty, blank, or terse uninformative intents provide no authorization
    if not intended:
        # Calling tools without an intent is highly suspicious
        return 0.85
    if len(intended) == 1 and next(iter(intended)) in {"ok", "pleas", "yes", "proceed"}:
        return 0.85

    # Check for direct action conflicts (e.g. tool is delete, intent only specifies read)
    intended_actions = {SYNONYMS[t] for t in intended if t in SYNONYMS}
    tool_actions = {SYNONYMS[t] for t in tool_tokens if t in SYNONYMS}
    for tool_act in tool_actions:
        for int_act in intended_actions:
            if (tool_act, int_act) in CONFLICTING_ACTIONS and tool_act not in intended_actions:
                # Strong conflict: user asked to read/calculate, tool performs destructive action
                return 0.95

    # Check whether the core action of the tool is authorized by the intent
    action_match = bool(tool_actions and (tool_actions & intended_actions))

    # Overlap between intended tokens and operation tokens
    overlap_tokens = intended & operation
    overlap: float = float(len(overlap_tokens))

    if not overlap:
        # Check partial/sub-string matches
        sub_matches = sum(
            1
            for it in intended
            for op in operation
            if (len(it) >= 3 and len(op) >= 3) and (it in op or op in it)
        )
        if sub_matches:
            overlap = 0.5 * min(sub_matches, min(len(intended), len(operation)))

    if not overlap:
        return 1.0

    op_coverage = overlap / max(1, len(operation))
    if action_match:
        # Action is explicitly authorized (e.g., synonym for read, delete, calculate)
        # Scale score: even moderate parameter coverage confirms benign alignment
        score = 0.55 + 0.45 * min(1.0, op_coverage * 2.0)
    else:
        # Action root not explicitly present; rely on general lexical/stem overlap
        score = overlap / math.sqrt(len(intended) * len(operation))

    return float(max(0.0, min(1.0, 1.0 - score)))
