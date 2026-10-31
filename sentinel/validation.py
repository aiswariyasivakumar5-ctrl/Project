"""Finite, bounded JSON and unambiguous HTTP request framing."""

from __future__ import annotations

import json
import math
from http.server import BaseHTTPRequestHandler
from typing import Any, NoReturn

from .http_limits import budget, remaining


class PayloadTooLargeError(ValueError):
    """Raised when request payload exceeds configured size limits."""


def validate_json(value: Any, *, max_depth: int = 64, max_items: int = 100_000) -> None:
    pending, visited = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > max_depth or visited > max_items:
            raise ValueError("JSON structure exceeds limits")
        if type(item) is str:
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("invalid Unicode string") from exc
            continue
        if item is None or type(item) in (bool, int):
            continue
        if type(item) is float and math.isfinite(item):
            continue
        if type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is dict and all(type(key) is str for key in item):
            pending.extend((child, depth + 1) for child in item.values())
            pending.extend((key, depth + 1) for key in item)
        else:
            raise ValueError("finite JSON values required")


def load_json(body: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value: str) -> NoReturn:
        raise ValueError("nonfinite JSON constant")

    try:
        value = json.loads(body, object_pairs_hook=pairs, parse_constant=constant)
        validate_json(value)
        return value
    except (RecursionError, UnicodeDecodeError) as exc:
        raise ValueError("invalid JSON encoding or nesting") from exc


def read_body(handler: BaseHTTPRequestHandler, maximum: int, timeout: float) -> bytes:
    lengths = handler.headers.get_all("Content-Length", [])
    if handler.headers.get_all("Transfer-Encoding", []) or len(lengths) != 1:
        raise ValueError("one Content-Length and no Transfer-Encoding required")
    raw = lengths[0].strip()
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10:
        raise ValueError("invalid Content-Length")
    length = int(raw)
    if length > maximum:
        raise PayloadTooLargeError("request size exceeds limits")
    if length <= 0:
        raise ValueError("request size exceeds limits")
    chunks: list[bytes] = []
    left = length
    with budget(timeout):
        while left:
            handler.connection.settimeout(remaining(timeout))
            chunk = handler.rfile.read1(min(left, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        remaining(timeout)
    body = b"".join(chunks)
    if len(body) != length:
        raise ValueError("truncated request body")
    return body
