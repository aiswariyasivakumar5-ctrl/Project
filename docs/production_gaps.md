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
