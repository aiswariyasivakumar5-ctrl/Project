# Gateway concurrency review

Scope: `sentinel/gateway.py`, `sentinel/engine.py`, `sentinel/provenance.py`, and the stress/regression checks in `tests/test_concurrency_stress.py`. Review focused on mutable state shared across gateway requests and the locks named in the verification task.

## Shared state and synchronization

| Shared structure | Guard and lock order | Paths that touch it outside the guard / residual note |
| --- | --- | --- |
| `pending_actions`, `_approval_events`, and mutable `PendingAction` fields | `_lock`. Approval/denial and event registration use `_lock`; event is signaled while `_lock` is held. State import/export order is `_lock` then `engine.lock`. | `_sweep_pending_actions` assumes its caller owns `_lock`; current call sites are locked. `PendingAction` objects returned from create/approve APIs can be mutated by embedding callers, outside gateway protection. |
| Engine `profiles`, `sessions`, `identities`, causal graph, sequence model, quarantine, and detector internals | `engine.lock`; gateway analysis uses `_engine_lock()` which acquires `engine.lock`, then `_rate_lock`. State export/import acquire `_lock` then `engine.lock`. | Some engine methods such as `SentinelEngine.issue_provenance` are public and do not acquire `engine.lock` themselves; gateway integrations must call them under the engine lock. Research/embedding callers that invoke them concurrently with evaluation need their own synchronization. |
| Provenance ledger `claims`, `_issued`, `consumed`, `_last_time`, `_invalid`, `_evidence` | Ledger’s own `RLock` serializes `issue` and `validate`; when graph-backed through gateway handling, calls occur under `engine.lock`, giving order `engine.lock` then ledger lock. | The ledger can be called directly without `engine.lock`; graph evidence reads then race with causal graph writes. Direct graph-backed use outside the engine lock is unsupported by the current synchronization contract. |
| `_upstream_sessions` and `_uses_upstream_sessions` | `_session_lock` guards session insert, sweep, lookup, and `last_used` updates. | Found an unlocked read of `_uses_upstream_sessions` when a request omitted its MCP session header. It now takes `_session_lock` before checking whether sessions are required. |
| `_rate_buckets` | `_rate_lock` for lookup, refill, insert, and pruning in `allow_rate`. | State snapshots intentionally do not serialize rate buckets. Concurrent saves can therefore have valid engine/profile snapshots while request-rate state continues changing. |
| Metrics (`requests`, latency counters/buckets, upstream errors, lock-wait total) | `_rate_lock`; updates in `_append_audit`, `_engine_lock`, and error paths use this lock; scrape paths snapshot under the same lock. | `_append_audit` also appends to the bounded `audit` deque outside this lock. `deque.append` is atomic in the supported CPython runtime, but the deque has no explicit gateway-level lock for alternate Python implementations. Audit persistence is separately serialized by `AuditLog`'s lock. |
| `auth_failures` | `_auth_lock` guards per-peer timestamp cleanup, insert, and capacity pruning. | No unguarded mutation found. |
| `client_credentials` | Reload parses a complete new map and swaps it while holding `_auth_lock`; each request takes a reference snapshot under `_auth_lock` and iterates that immutable-by-convention map after releasing the lock. | Before this step, reload assignment and authentication reads had no shared lock. That race was closed, and the stress test covers requests during reload. Do not mutate the published map in place. |
| `tool_metadata`, `capability_digest` | State import/export and `tools/list` publication use `_lock`. | Several request decision paths read the published references without `_lock`. Publication replaces whole objects rather than mutating them in place, so readers retain a consistent object; paired metadata/digest reads can still represent adjacent publications. State snapshots serialize under `_lock`. |
| Bounded gateway `audit` deque | Append is performed by `_append_audit`; most request call sites hold `_lock`, while auth-failure and recovery-probe audit paths append without it. | No iteration/serialization of this deque occurs in the gateway state path. Multi-producer append relies on CPython deque append safety; this is a portability limitation rather than a demonstrated race in the supported runtime. |
| `config`, static auth token, feature flags, capacities | Configuration is validated at construction and treated as immutable during serving. | `learning_enabled`, `trusted_enrollment`, and telemetry override are mutable public attributes without a dedicated lock; operators/integrations should set them before serving or synchronize changes externally. |

## Lock ordering

The enforced nested-lock hierarchy is **gateway `_lock` → `engine.lock` →
provenance ledger lock → `_rate_lock`**. Paths may take a suffix of this order;
they must release before acquiring an earlier lock. `_auth_lock`,
`_session_lock`, and `AuditLog._lock` are independent leaf locks and must not be
nested with one another or with the hierarchy above. The recovery-probe test
uses a per-thread lock-order recorder with ranks for `_lock` and `engine.lock`;
it fails immediately if any code acquires the gateway lock while the engine
lock is held.

- State export/import: `_lock` → `engine.lock`.
- Approval resolution/state persistence: `_lock` → reentrant `_lock` in `export_state` → `engine.lock`.
- Gateway engine evaluation: `engine.lock` → `_rate_lock` briefly to account for lock wait.
- Audit append under a request: caller may hold `_lock`; `_append_audit` then takes `_rate_lock`.
- Session binding work uses `_session_lock` without nesting `_lock` or `engine.lock` in current gateway paths.
- Authentication map snapshot and failure accounting use `_auth_lock`; map parsing occurs before the lock.
- Provenance validation during gateway evaluation: `engine.lock` → provenance ledger lock.

The following caller-visible access paths do not acquire the guarding lock and
therefore require external synchronization or immutable-by-convention use:

| Access path | Unlocked access | Requirement / effect |
| --- | --- | --- |
| Direct calls to `SentinelEngine.issue_provenance` | Reads audit log, causal graph, then issues against the ledger without taking `engine.lock`. | Embedders must hold `engine.lock` when concurrent evaluation can mutate those structures. |
| Direct graph-backed `ProvenanceLedger` use | Ledger lock protects ledger maps, but graph evidence reads occur without the engine lock. | Use through the engine/gateway lock contract; direct callers synchronize graph access. |
| Mutation of returned `PendingAction` objects or `client_credentials` mapping | Public Python references can be mutated by callers outside gateway locks. | Treat returned/published values as immutable; mutate credentials only through the reload API. |
| Runtime changes to `learning_enabled`, `trusted_enrollment`, and telemetry override | These are public mutable attributes with no dedicated lock. | Set before serving or synchronize changes externally. |
| `tool_metadata` and `capability_digest` request reads | Readers can observe adjacent whole-object publications without `_lock`. | Objects are replaced, not mutated in place; a paired read can span publications. |
| `audit` deque appends on auth-failure/recovery paths | Those appends do not take `_lock`; code relies on CPython deque append behavior. | Portability to Python runtimes without equivalent append atomicity is not established. |

The review found a lock inversion in `probe_recovery`: it held `engine.lock` while acquiring `_lock`, while state persistence holds `_lock` while waiting for `engine.lock`. A recovery probe concurrent with a save could deadlock. The audit append now runs after the engine lock is released. A lock-order regression test asserts that the gateway lock is not acquired while the engine lock is held.

## Stress evidence

`tests/test_concurrency_stress.py` is marked with `pytest.mark.stress` and is run explicitly with `pytest -m stress`. Each of the four requested stress scenarios ran 51 rounds: 17 rounds each with 2, 4, and 8 worker threads.

- Concurrent pending-action creation, approval, denial, and expiration: passed.
- Concurrent profile/rate-bucket mutations and repeated state saves, followed by load and snapshot equality checks: passed.
- Concurrent single-use consumption of the same provenance token: exactly one consumer succeeded in every round.
- Credential reload while authenticated requests were in flight: completed without unexpected HTTP status or thread errors.
- Additional lock-order regression: passed.

Full command and exact result are recorded in `docs/verification_log.md`.
