# Dataset expansion — October 3, 2026

User-authorized increase in synthetic input volume and GitHub publication.
This is a separate corpus version, not an amendment silently applied to retained
experiments. The five-seed novelty protocol remains unchanged. No model outcomes
were consulted in selecting the new consecutive seeds 20001–20020.

The exporter reuses existing generators with 10,000 TRAIN, 2,000 VALIDATION and
requested 3,000 events per scenario. All legacy and novelty scenario names are
included; shared names use the novelty catalog definition. Source hashes, actual
class counts, unique event IDs and per-shard hashes are retained in the manifest.
No generator, detector, action band or calibration rule changed.

See [dataset card](../datasets/README.md) for reproduction, schema, split semantics,
resource requirements and limitations. Larger fixture volume cannot replace
independent licensed MCP sessions. Exported fixture metadata must not become model
features. Many attack sequences are structurally identical across seeds and are
not independent attack replications. Analysis must account for that dependence.

## Verification record

- Completed export: 1,050,380 records, 480 shards, 20 seeds, 22 TEST scenarios.
  TRAIN 200,000; VALIDATION 40,000; TEST 810,380.
- All 480 saved compressed shard SHA-256 hashes verified against the manifest.

- Three exporter tests passed: deterministic outputs/counts/hashes/schema/split
  separation; refusal to overwrite; invalid configurations create no output.
- Initial full suite: 187 tests, 186 passed, one error in
  `test_http_rejects_malformed_length_and_service_payload`: Windows socket abort
  (`WinError 10053`) while awaiting an HTTP response. Export was running concurrently.
  This does not establish the cause. No timeout or test assertion was changed.
- Retained research verification passed for 43 files; `results/` has no diff.
- Full-suite rerun after export completed: **187 tests passed in 92.714 seconds**.
  The initial socket-abort failure is retained above; the successful rerun does
  not establish its root cause. No implementation or timeout change was made
  between these two runs.

## Remaining research work

Review an adapter and a separate expanded evaluation protocol before evaluating
this corpus; maintain TRAIN-only fitting, VALIDATION-only calibration and frozen
TEST. A full matched-model/ablation run, independent traces and team review remain
outstanding. No new accuracy, confidence interval or statistical significance is
claimed by generating input files.
