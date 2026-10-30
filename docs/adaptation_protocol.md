# Adaptation and poisoning study — October 3, 2026

Verification: three new scenario/metric tests passed. The full suite ran 190 tests
in 78.498 seconds: 189 passed and the existing malformed HTTP request test errored
with Windows socket abort 10053. Retained-research verification passed for 43 files.
The failing test passed individually in 1.043 seconds without code changes; the
full-suite error remains unresolved and is not counted as a full-suite pass.

This prospective extension investigates whether guarded learning can retain benign
adaptation while limiting adversarial learning. It is an exploratory development
protocol, not a registered study. The first diagnostic uses seed 20001, 100 trusted
enrollment events and 30 events per stream. Existing fixed gateway decisions apply;
there is no threshold search in this diagnostic.

## Implemented diagnostic

Four paired streams share a seeded timeline and a benign first third:
clean drift, poisoning only, mixed drift/poisoning, and mixed drift/poisoning with
multiple compromised identities. Drift adds a compact-format argument to reads.
Attacks occupy every third post-onset slot. Attack and legitimate upgrade payloads
are deliberately observationally equivalent. Labels encode the simulated actor's
hidden objective; they are never supplied to the learner. Therefore these streams
test an identifiability limit: no content detector can recover hidden intent from
identical observed inputs. Distinct authenticated identities do not prove independence.

Four policies reuse existing implementations: frozen learning, immediate eligible
updates (`without_dual_memory`), gated updates (`full`), and approval required with
approval withheld. Immediate eligible updating still applies the gateway's existing
eligibility checks; it is not unconditional learning. Approval withheld supplies
no reviewer fixtures. Each stream restores the same post-enrollment checkpoint.
All stream observations are ADAPTIVE diagnostics, separate from frozen TEST.

Run with:

```powershell
python -m sentinel.adaptation_study --output results/adaptation/new-diagnostic --seeds 20001 --events 30 --training 100
```

New output directories are required. Protocol/source hashes, matched workload hashes,
event decisions, updates and partial failure context are saved. Failures retain
completed event rows and do not generate a complete summary. The runner performs
no automatic retries. Intervention is measured from actual gateway observations.
Forwarding is available in event details; forwarding alone is not proof of harmful
downstream execution or task success.

## Required before substantive research claims

1. Add event-level learning attribution, including each replayed candidate event.
   Updates on malicious call steps are only a diagnostic. They cannot measure
   contamination because a promotion can replay earlier benign and malicious events.
   The current summary deliberately leaves contamination undefined.
2. Add matched benign irregularities and attacks with observable security effects.
   Preserve the observationally equivalent streams as negative controls.
3. Add correct and delayed reviewer fixtures with declared timing and information
   access; measure requests, approvals, revocations and review delay. Ground-truth
   oracle approval must be labeled as an upper-bound simulation.
4. Define recovery as sustained acceptable benign utility after drift, with a
   prespecified window and censoring for runs that never recover. Measure task
   completion separately from call admission.
5. Implement and validate a robust streaming comparator against its published
   specification. Do not call a generic single-memory policy MemStream.
6. Freeze a separate expanded protocol before inspecting larger-run outcomes:
   training size, benign validation calibration if used, seeds, attack fractions,
   independent stream families, primary endpoints, comparisons and multiplicity.
   Use paired independent runs for uncertainty; repeated template rows are not
   independent samples. The historical five-seed protocol is a separate study.

Primary proposed joint objective: reduce the fraction of malicious events actually
admitted to learning while retaining benign drift recovery and manageable review
burden. An approach that suppresses all learning does not satisfy that objective.
Thresholds and operating constraints must be chosen on development/validation data.
Run frozen TEST from a training checkpoint; evaluate adaptation in separately
declared streams. No diagnostic result constitutes proof of novelty or patentability.
