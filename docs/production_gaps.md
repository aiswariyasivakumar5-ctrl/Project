# Production gaps and operating limits

This list describes limits that remain even after gateway hardening. Runtime
enforcement does not establish that the detector catches every harmful MCP
interaction.

## Transport and deployment

- Upstream stdio transport is not implemented. The gateway accepts HTTP(S)
  upstream URLs only.
- The gateway is a single-process service. Learned profiles, session mappings,
  rate buckets, and pending actions are process-local or stored in one local
  state file; there is no distributed coordination or horizontal scaling.
- There is no high-availability failover or replicated state protocol.
- The persistent audit sink rotates one active JSONL file and one `.1` file.
  Hash links detect edits within each retained segment; older rotated segments
  are discarded when the next rotation occurs.
- The optional request rate limits are disabled by default and are local to one
  process. Configure them explicitly for a deployment.
- Readiness checks the enrolled baseline and whether the upstream TCP/TLS
  endpoint accepts a connection. It does not prove that every MCP method works.
- Pending-action state is written atomically with the learned gateway state.
  The saved upstream response can contain sensitive data; restrict state-file
  permissions and backups accordingly. HMAC integrity is available through
  `MCP_SENTINEL_STATE_KEY`, but it does not encrypt the file.
- TLS certificates, private keys, credentials files, audit logs, and state
  backups remain the operator's responsibility to provision and protect.
- Reverse-proxy deployments must set explicit allowed Host/Origin values.
  `--trust-proxy-headers` trusts the proxy's forwarded scheme header and is safe
  only when direct untrusted access to the gateway is blocked.

## Detection and validation

- Detection quality has not been validated on representative real production
  traffic. The available results use synthetic workloads.
- The evaluated detector has zero recall on `abnormal_sequence`,
  `capability_drift`, `gradual_poisoning`, and `low_and_slow` attack families in
  the retained synthetic evaluation. Treat this as a known limitation, not as a
  claim that the gateway prevents those attacks.
- MCP `ping`, resources, and prompts methods are available only with explicit
  `--allow-method` flags. Their responses are size limited and audited, but are
  currently unscored by the tool-interaction detector.
- Withholding a suspicious tool response happens after upstream execution.
  The gateway does not provide operating-system, container, filesystem, or
  network isolation for upstream tools.
- Intent is client-supplied context. It can be inaccurate or malicious and is
  not an authenticated authorization grant.
- Independent-session and quorum mechanisms cannot prevent an attacker from
  creating multiple identities (Sybil behavior) when identity enrollment is
  not independently controlled.
- The gateway's nonce/digest echo is behavioral evidence, not cryptographic
  server identity or hardware-backed attestation.

## Phase 1 enforcement limits

- Detector analysis for every tool happens after upstream execution. `read`
  responses may be withheld after the call, but this does not undo or prevent
  any upstream side effect. The detector is advisory only for `write` and
  `destructive` risk classes.
- A policy `write` call can execute after an operator approves it. A
  `destructive` call remains denied unless the operator policy explicitly
  requires approval; after approval, its upstream action executes.
- Explicit `--enable-learning` permits online changes to the in-memory model.
  Every observed model update is audited and marks the persisted baseline
  unapproved; the process may continue using the changed model until restarted.
  Operators must review and approve the new baseline before the next start.
- Per-tool schemas are operator supplied. Schema validation bounds and rejects
  malformed/unknown arguments; it does not make an allowed upstream operation
  safe or constrain what the upstream server does with valid arguments.

## Phase 0 package boundary status

The Python distributions are separated: the runtime wheel contains the 20-module runtime package and the research distribution contains research workflows and dashboard assets. The built runtime wheel passed `scripts/check_runtime_wheel.py`; no `sentinel_research` files or imports were found in it. Package separation and archive hygiene are complete locally.

The Phase 0 full-suite rerun is **NOT VERIFIED HERE**: loopback-dependent tests were blocked by Windows socket permission errors (`WinError 10013`). Docker build is **NOT VERIFIED HERE** because access to the Docker Buildx lock was denied. Run `python -m pytest -q` on a host that permits loopback sockets and `docker build -t mcp-runtime-sentinel:phase0 .` on a Docker-enabled host before treating those gates as passed.

## Phase 1 local verification update (2026-10-30)

The requested full suite was run in WSL/Linux after Phase 1 changes: `399 passed, 8 skipped, 110 subtests passed` (exit 0), compared with the 391/8 preflight baseline. Runtime statement/branch coverage was 87%, above the 85% gate. Ruff, strict mypy over the full runtime package, and pip-audit passed. The older Windows socket-blocked result above remains the Phase 0 Windows attempt; it is superseded for Linux test status by this WSL run.

Local Docker was not run. Docker smoke is reported as verified in CI by the operator; this local verification does not independently confirm that CI run. The targeted local policy mutmut run was interrupted before completion. The workflow contains the Linux security mutation job; updated mutation results remain pending a hosted workflow run. Do not treat mutation coverage as verified until that job completes.
