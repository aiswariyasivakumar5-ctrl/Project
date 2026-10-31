# Member 4 — gateway integration handoff (2026-09-18)

## Completed engineering

Reviewed the supplied September 17 project snapshot and completed gateway-facing
configuration and audit gaps. Existing provenance, novelty scoring, capability
trust, dual memory and reviewed recovery remain the underlying mechanisms.

- GatewayConfig accepts a validated NoveltyConfig and passes it to the wrapper.
- The gateway CLI exposes all four existing novelty configuration switches.
- Rejected preflight requests include the affected capability, current recorded
  trust, active component configuration and `not-evaluated` memory disposition.
- Evaluated tool calls include the complete retained novelty evidence claim in
  `/v1/audit`, alongside the effective decision, claim ID, capability trust,
  counterfactual score, memory disposition and promoted event count.
- Claim evidence is copied while evaluation holds the engine lock, so later
  retention eviction cannot remove evidence required by that audit record.
- Upstream dispatch failures now produce an `error` audit record. `forwarded=true`
  means dispatch was attempted, not that execution or completion was confirmed.
  Single-use authorization remains consumed on a failed dispatch.
- Live HTTP regression verifies that an isolated export capability is never
  invoked upstream while a benign read succeeds and exposes its audit evidence.

## Configuration

Novelty remains opt-in; all four wrapper components are on when enabled.
Tool execution is deny-by-default: configure each approved tool name explicitly.
Python embedding example:

```python
from sentinel.gateway import GatewayConfig, SentinelGateway
from sentinel.novelty import NoveltyConfig
import os

gateway = SentinelGateway(GatewayConfig(
    'http://127.0.0.1:8790', 'srv', novelty=True,
    novelty_config=NoveltyConfig(capability_trust=False),
    allowed_tools=('safe_read', 'calculate'),
    client_auth_token=os.environ['MCP_SENTINEL_CLIENT_TOKEN'],
    auth_token=os.environ['MCP_SENTINEL_OPERATOR_TOKEN'],
))
```

CLI example (component ablation for development; set both credentials and enroll a baseline first):

```sh
python -m sentinel_research.cli baseline --upstream http://127.0.0.1:8790 --server-id srv --state-file sentinel-state.json
python -m sentinel_research.cli gateway --upstream http://127.0.0.1:8790 --server-id srv --state-file sentinel-state.json --novelty --no-capability-trust --allow-tool safe_read --allow-tool calculate
```

Available pairs: `--intent-provenance` / `--no-intent-provenance`,
`--capability-trust` / `--no-capability-trust`, `--dual-memory` /
`--no-dual-memory`, `--require-promotion-approval` /
`--no-require-promotion-approval`. They configure the opt-in wrapper;
without `--novelty` the base engine is used.

`--no-intent-provenance` disables the counterfactual score contribution. It does
not disable authorization validation. `--require-provenance` independently
requires a trusted-issuer claim before every tool dispatch. Disabling capability
trust restores server-level preflight isolation. The other switches expose the
existing learning policies; they do not implement additional research variants.

The embedding application's trusted session resolver and manifest enrollment
remain necessary for gated promotion; raw caller session IDs are not independent
identities. Operator approval and recovery remain in-process APIs, not client
HTTP controls. See `runtime_controls.md` for the existing procedures.

## Validation and evidence

Before fixes, four new regression cases reproduced missing configuration, CLI
flags, dispatch-error audit and blocked-request novelty evidence. After fixes,
six new tests pass, including malformed configuration rejection and disabled-
capability-trust fallback. The complete suite passes: **170 tests** on local
Linux/Python 3.12. Dependency validation passes. Retained research-artifact
verification passes for 43 files; historical results have no changes in the diff.
Existing tests additionally cover stale/mismatched/replayed claims before
execution, concurrent single-use authorization, failed-dispatch consumption,
attestation failures, promotion restrictions and reviewed capability recovery.

## Review boundary

Engineering changes are complete locally and ready for teammate review. This ZIP
has no upstream Git history, authenticated GitHub access or remote configured.
The local branch `feature/gateway-completion` is based on an imported snapshot;
its commits are packaging evidence, not replacements for upstream history. Apply
the included patch on a branch from the current upstream main, resolve any newer
changes, run checks and open a PR. Teammate approval, GitHub CI, merge and release
freeze are pending. This work does not approve final experiments or assign human
conception/inventorship.

Audit remains bounded and in-memory; its endpoint requires the operator Bearer
credential. The hash chain is not signed or durable. Post-response
blocking cannot undo upstream side effects; metadata and trusted issuer quality
remain assumptions. Dispatch errors are covered here; HTTP parsing errors and
malformed upstream response errors are not converted into complete tool audits.
Research scenario completion and new publication ablations remain separate work.
