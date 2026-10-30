# Automated technical review — September 21, 2026

Scope: implementation at `d6d188441d179327efbe4e44a5f84b3e211c46d8` and the existing
protocol. Prepared with AI assistance; no teammate approval is implied.

## Findings affecting the research claims

1. The `without_intent_provenance` variant disables a lexical intent-support score.
   It does not remove the single-use authorization ledger. A favorable result cannot
   establish the isolated benefit of replay protection. The six-variant matrix is
   complete for the implemented protocol, not a full factorial security study.
2. The name `counterfactual_risk` in the implementation describes token-overlap
   scoring. There is no intervention-based counterfactual estimator. The paper
   should call this intent-support scoring.
3. `full` deliberately uses the historical promotion policy without operator approval;
   `approval_required` represents the current wrapper's default. Always show this
   difference in tables. All wrapper components are opt-in at the gateway level.
4. The approval-required fixture injects no approvals. Withholding benign adaptation
   is expected and must be reported alongside blocked poisoning updates.
5. Independent-identity fixtures are trusted in-process inputs. Rotating caller session
   headers is not identity independence; compromised independent identities remain a
   separate threat. No production identity system is implemented.
6. Candidate fingerprints encode argument types and manifest digest, not all argument
   values. Trust in an argument shape alone cannot establish semantic safety.
7. Attestation is a nonce/manifest echo extension. A compromised server capable of
   echoing the expected response may still behave maliciously.
8. Single-use claims are consumed before dispatch, including when dispatch fails.
   They are process-local and depend on retained causal evidence and a trusted issuer.
9. Bounded audit retention may discard old records. Hashing an individual evidence
   record does not establish an externally verifiable append-only hash chain.
10. Historical offline threshold metrics and live gateway interventions are different
    endpoints. Do not merge them into one superiority table without identifying the
    operating rules and datasets.
11. The existing runner only reports exploratory F1 comparisons. The new reporting
    module implements the four planned primary endpoints and Holm family separately.
12. Five paired seeds limit exact-test resolution. Narrow or degenerate bootstrap
    intervals from repeated synthetic templates do not establish generalization.

## Verification boundary

Existing tests cover preflight replay/expiry, failed-dispatch consumption, partial
capability isolation, candidate rejection, operator-review lifecycle, frozen learning
and checkpoint independence. Passing these cases is bounded implementation evidence,
not a security proof. An earlier Windows full-suite run had one socket-abort error in
`test_http_rejects_malformed_length_and_service_payload`; its isolated retry and a
subsequent full run passed. The root cause was not established, so the issue should
not be described as conclusively fixed or proven Windows-only.

Technical owners should review these findings and record their own conclusions.
No additional mechanism, threshold retuning or historical metric replacement was
introduced during this review.

The publication-scale attempt later hit a five-second client response timeout after
seven phase files. A focused baseline/seed-42 legitimate_upgrade reproduction passed
at the same 5,000/1,000/3,000 sizes. The cause remains unresolved. Retain both attempts;
do not describe a successful diagnostic as proof that the full run is reproducible.
