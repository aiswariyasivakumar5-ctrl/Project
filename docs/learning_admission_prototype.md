# Experimental learning-admission prototype

Status: opt-in research prototype, included for conference review at the owner's
request on October 23, 2026. Novelty and patentability are unverified; the prior-art
screen found substantial overlap. Existing engine defaults, experiments,
thresholds and historical results are unchanged.

## Run the demo

From the repository root in PowerShell:

```powershell
.\.venv-repro\Scripts\python.exe -m sentinel_research.learning_admission_demo
.\.venv-repro\Scripts\python.exe -m unittest discover -s tests -p test_learning_admission.py -v
```

The CLI prints 40 matched functional cases as JSON, including actual model-update
counts and one local timing measurement per case. It does not write experiment
results or train/validation/test data. Those timings are not a latency benchmark,
and these fixtures are not a population sample for confidence intervals or p-values.

## Architecture and trusted integration boundary

`LearningAdmission` owns a private copy of `SentinelEngine`. A trusted application
registers a permission for baseline learning and a capability contract digest for
each `(server, tool)` scope. Registration changes monotonically advance generations,
including regrant and change-back. Callers cannot select omitted dependencies.

Approval validates/copies an Interaction, verifies it using a trusted application
callback, and binds its complete canonical JSON digest to an explicit update ID,
evidence reference, authority generations and deadline. The verifier receives a
separate copy. Approval issuance rechecks authority after verification.

```text
trusted authority setters -> coordinator registry
event -> verifier -> event-bound approval -> delayed commit request
                                      |
                  check + copy model under coordinator lock
                                      |
                      prepare update on private model copy
                                      |
           final expiry/authority/replay/model-version checks under lock
                                      |
           publish model + consumed update ID + decision by one state swap
```

`commit` learns through the existing `learn_approved(..., update_sequence=False)`
hook; it does not rewind session sequence history. A model version conflict returns
`retry_model_conflict` instead of overwriting another update. Preparation exceptions
return `preparation_failed`, leaving published state unchanged and allowing retry.
Authority/expiry/binding rejections are terminal for that ticket. Expiry uses an
inclusive deadline (`now >= expires`). Clock failures or rollback latch admission
closed. Capacity exhaustion fails closed without forgetting replay identities.

Only the copied snapshot API exposes model state. All authority mutations must use
this coordinator. A revocation serialized before publication prevents admission;
one serialized after publication does not undo learning. This is not unlearning.

## Observed deterministic demo results

Executed 2026-10-16. Eight scenarios per policy: unchanged, revoked, relevant
change, unrelated change, expiry, replay, change-back, and event substitution.
There are six ineligible attempts and two eligible attempts per policy. In the
replay fixture the first successful commit is setup; the measured attempt is the
second. No failed response is used: the distinction is learning authority freshness.

| Policy | Ineligible attempts admitted / 6 | Eligible attempts withheld / 2 |
| --- | ---: | ---: |
| Verification only | 4 | 0 |
| Expiry only | 3 | 0 |
| Capability generation only | 2 | 0 |
| Standard transactional baseline | 0 | 0 |
| Combined prototype | 0 | 0 |

All variants retain event binding, replay identity and staged model publication;
only the declared freshness checks differ. All require current authority at initial
approval. The weaker variants are experimental controls, not deployment modes.

### Critical Honest Finding: No Algorithmic Advantage Over Transactional Baselines

The standard transactional baseline and combined prototype use the exact same
underlying concurrency control patterns (serialized monotonic generation checks,
ticket expiry timestamps, and atomic pointer swap under lock). Consequently:

1. **Exact Parity**: Both policies achieve identical outcomes: **0/6 ineligible
   attempts admitted, 0/2 eligible attempts withheld**.
2. **No Algorithmic Novelty**: The mechanism demonstrates that standard database-style
   transaction serializability prevents stale or revoked updates from being committed
   to an in-memory model. It does **not** constitute a novel machine learning defense,
   an algorithmic contribution, or an advantage over classical transaction processing.
3. **Submission Rule**: In any paper submission, learning admission must be presented
   strictly as an engineering integration pattern (ensuring model-update serializability
   against out-of-order or expired authority), never as an algorithmic innovation or
   security breakthrough over standard transactional systems.
4. **No Statistical Claim**: These deterministic fixtures isolate individual freshness
   checks; they do not represent a statistical sample or population inference.

## Tests and limitations

Verification on 2026-10-16: full suite **261/261 passed** in 85.214 seconds;
focused admission suite **18/18 passed**. `python -m sentinel_research.final_verification`
passed for 43 retained files; `python -m pip check` found no broken requirements.
These local checks do not establish remote CI success or real-world effectiveness.

Focused tests cover one-time admission, copied snapshots, permission regrant,
capability ABA, unrelated changes, exact expiry, event substitution, unknown tickets,
clock rollback, verifier failure/mutation, verification-time revocation, preparation
failure, expiry/revocation during preparation, duplicate concurrent workers,
concurrent model updates, post-commit revocation, capacity, and matched controls.

Limits requiring explicit disclosure:

- Single-process in-memory coordination, not crash-durable or cross-process.
- Trusted Python application boundary, not authentication against malicious local
  code. Ticket IDs are not signed attestations; evidence references are labels.
- Two mandatory scope dependencies only. Shared/upstream permissions and automatic
  capability dependency discovery are not implemented. The operator must supply
  genuinely tool-specific contract digests; a global manifest digest cannot
  establish selective invalidation by itself.
- Uses a private learning engine, not the live gateway's model or existing queued
  promotion subsystem. No new HTTP endpoint, frontend or response-blocking behavior.
- Simple arithmetic verification is only a demo oracle, not general semantic safety.
- Full model copying is potentially costly. No scaling, p95 overhead, adaptation
  quality, real-world traces or publication-scale evidence was collected here.
- Standard engine learning can modify its own attestation enrollment; this prototype
  does not establish a live per-tool attestation architecture.
- Revocation after commit does not remove prior influence. Restart discards the
  experiment, including replay records; never restore only tickets into a new gate.
- Model preparation and callbacks are trusted and assumed not to leak staged mutable
  references. Hard process failure is outside the atomic-publication claim.

## College review handoff

Demonstrate the CLI and deterministic tests alongside the local prior-art comparison
in `artifacts/patent-review/`. Present the equality with the transactional baseline,
not just wins over weaker controls. Before live integration, specify shared
dependencies, capacity/restart semantics, staging cost limits and all update paths.
Before a larger experiment, preregister matched schedules, independent units,
evaluation margins and split rules. Human contribution records and professional
patent/disclosure review remain outstanding.
