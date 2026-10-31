"""Explicit operator policy for legacy gateway integration fixtures."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
import pytest

from sentinel.gateway import GatewayConfig


@pytest.fixture(scope="session", autouse=True)
def install_fixture_policies(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Give older integration fixtures explicit permissive local test policies.

    Production configuration is never synthesized this way. The dedicated
    policy tests use their own files and exercise the fail-closed defaults.
    """
    directory = tmp_path_factory.mktemp("operator-policies")
    original = GatewayConfig.__post_init__
    lock = threading.Lock()
    next_id = 0

    def configure(config: GatewayConfig) -> None:
        nonlocal next_id
        if config.policy_file is None and config.allowed_tools and isinstance(config.allowed_tools, tuple) and all(
            isinstance(tool, str) and tool for tool in config.allowed_tools
        ):
            with lock:
                next_id += 1
                path = directory / f"policy-{next_id}.json"
            rules = {
                tool: {
                    # These are synthetic integration fixtures. Their explicit
                    # allowlist is the fixture's operator decision; policy
                    # behavior is exercised separately with dedicated policies.
                    "risk_class": "read",
                    "input_schema": {"type": "object", "additionalProperties": True},
                }
                for tool in config.allowed_tools
            }
            path.write_text(json.dumps({"tools": rules}), encoding="utf-8")
            config.policy_file = str(path)
            config.enable_learning = True
        original(config)

    GatewayConfig.__post_init__ = configure
    try:
        yield
    finally:
        GatewayConfig.__post_init__ = original
