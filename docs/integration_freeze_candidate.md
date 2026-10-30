# Integration-freeze candidate

Prepared September 20, 2026 by the integration lead. This document assembles
evidence for team review. It does **not** approve a release, register a protocol,
authorize final experiments or determine authorship/inventorship.

## Candidate identity

- GitHub branch: `main`
- Candidate commit: `ecdf974f585a23170d2c8fc685b60923ea166517`
- Candidate subject: `Merge pull request #4 from snehathesingh-stack/feature/gateway-completion`
- Scope: all work merged through gateway completion, including provenance,
  capability trust, dual memory, runtime controls, validation calibration and the
  live novelty experiment framework.

## Machine-verifiable evidence

- [x] All visible remote feature and fix branches are merged into `origin/main`.
- [x] GitHub tree contains 274 tracked files.
- [x] Full exported-snapshot suite passes: 170 tests.
- [x] No retained historical result file was modified by this documentation update.
- [x] Gateway exercises novelty logic through live mock-server regressions.
- [x] Component switches reach the live gateway and the study runner.
- [x] Deterministic seeded scenario tests pass.
- [x] TRAIN, VALIDATION, TEST and ADAPTIVE phase separation is tested.
- [x] Validation-only score calibration is persisted before TEST.
- [x] The proposed metrics and paired analysis are written in `novelty_protocol.md`.
- [x] The exact candidate hash is recorded here before final experiment execution.

Verification command:

```powershell
python -m pip check
python -m unittest discover -s tests -v
python -m sentinel.final_verification
```

## Human gates that remain open

- [ ] Provenance owner reviews provenance and causal assumptions.
- [ ] Dual-memory owner reviews promotion, rejection and poisoning assumptions.
- [ ] Gateway owner reviews capability isolation, audit semantics and switches.
- [ ] Evaluation owner reviews hypotheses, endpoints, seed-level pairing and Holm family.
- [ ] Team records corrections or explicitly records no requested changes.
- [ ] Team approves the candidate commit or identifies a replacement commit.
- [ ] Team selects a registry and formally preregisters the approved protocol.
- [ ] Integration lead creates the release tag only after the preceding approvals.

## Required review record

Each reviewer should add a dated pull-request review or a signed repository entry
containing:

1. reviewer name and GitHub account;
2. mechanism or protocol section reviewed;
3. candidate commit hash;
4. findings and required corrections;
5. approval or rejection;
6. conflicts of interest or unresolved disagreements.

Silence, collaborator access, a merge, a passing test suite or attendance at a
meeting is not approval. Do not replace the unchecked boxes with inferred consent.

## After approval

The integration lead should merge only reviewed corrections, rerun all three
verification commands, update the candidate hash, obtain approval for that exact
hash, create an immutable release tag, record the preregistration identifier and
only then authorize the publication-scale novelty run. Test outcomes must not be
used to revise thresholds, scenarios, primary outcomes or seed selection.
