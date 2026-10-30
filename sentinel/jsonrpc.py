from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .validation import load_json, validate_json


class JsonRpcError(ValueError):
    def __init__(self, code: int, message: str, request_id: Any = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id

    def response(self, data: Any = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": str(self)}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": self.request_id, "error": error}


@dataclass(frozen=True)
class JsonRpcRequest:
    method: str
    params: dict[str, Any]
    request_id: Any
    notification: bool
    raw: dict[str, Any]


def parse_request(body: bytes) -> JsonRpcRequest:
    try:
        value = load_json(body)
    except ValueError as exc:
        raise JsonRpcError(-32700, "Parse error") from exc
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
        raise JsonRpcError(
            -32600, "Invalid Request", value.get("id") if isinstance(value, dict) else None
        )
    method = value.get("method")
    params = value.get("params", {})
    if not isinstance(method, str) or not method or not isinstance(params, dict):
        raise JsonRpcError(-32600, "Invalid Request", value.get("id"))
    if type(value.get("id")) not in (str, int, float, type(None)):
        raise JsonRpcError(-32600, "Invalid request ID")
    return JsonRpcRequest(method, params, value.get("id"), "id" not in value, value)


def validate_response(value: Any, expected_id: Any) -> dict[str, Any]:
    try:
        validate_json(value)
    except ValueError as exc:
        raise JsonRpcError(-32053, "Malformed upstream JSON-RPC response", expected_id) from exc
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
        raise JsonRpcError(-32053, "Malformed upstream JSON-RPC response", expected_id)
    if (
        "id" not in value
        or type(value["id"]) is not type(expected_id)
        or value["id"] != expected_id
    ):
        raise JsonRpcError(-32054, "Upstream response ID mismatch", expected_id)
    if ("result" in value) == ("error" in value):
        raise JsonRpcError(-32053, "Malformed upstream JSON-RPC response", expected_id)
    if "error" in value and (
        not isinstance(value["error"], dict)
        or type(value["error"].get("code")) is not int
        or not isinstance(value["error"].get("message"), str)
    ):
        raise JsonRpcError(-32053, "Malformed upstream JSON-RPC error", expected_id)
    return value


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
