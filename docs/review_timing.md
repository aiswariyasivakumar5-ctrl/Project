# Operator approval timing diagnostic — October 4, 2026

The adaptation runner supports `--review-study`: correct review at drift onset,
review delayed by five event steps, and review withheld. All use the existing
approval-required engine. The trusted simulation grants one shape/intent/manifest
approval only for clean drift; all poisoning and mixed streams receive no approval.
This is an oracle reviewer with access to scenario identity, not an evaluated human
or automatic reviewer. No labels are passed to the detector. Grants use the real
`approve_promotion` API with a one-hour expiry and do not override eligibility or
fresh-attestation requirements. No repeated regranting occurs after invalidation.

The schedule was implemented before observing the run, using seed 20001, 100
enrollment events, 30 stream events, drift onset index 10 and the existing scoped
read permissions. Each policy/stream restores the enrollment checkpoint. Source
hashes, schedule, event-level grants and learning attribution are retained.

```powershell
python -m sentinel.adaptation_study --output results/adaptation/new-review-study --events 30 --training 100 --authorize-reads --review-study
```

## Measures

- Grant count and grants per 100 calls describe simulated review actions, not
  review requests, human effort, review duration or the number of distinct people.
- Admission recovery is the first completion of five consecutive benign calls
  without intervention after onset. Delay is measured in event steps from onset.
  No such window means right-censored within the observed horizon, represented null.
- First post-onset benign learning uses the source index and label of every replayed
  event. It is separately censored. Admission alone does not imply adaptation.
  For poisoning-only streams this is ordinary benign learning, not drift recovery.
- Contamination retains the attributed adaptive-update definition. No wall-clock
  human recovery time, task completion or statistical significance is inferred.

## Retained findings

Verification: all 209 tests passed in 77.640 seconds, including recovery-window,
interruption and replay-source attribution regression tests.

`results/adaptation/review-timing-20261004` completed all 12 cells. In clean drift,
all three policies had 10 learning updates, all from before onset. None learned a
post-onset benign event. Admission recovery delay was five steps for all three;
benign intervention rate was 10%. Correct and delayed review each issued one grant;
withheld issued none. No malicious updates were observed across the matrix, while
malicious intervention was zero in attack-bearing streams.

The first changed call at index 10 required confirmation; later allowed calls still
had risk around or above the existing 0.42 learning gate and memory disposition
`rejected`. The rejection prevents this workload from exercising successful
approval-driven promotion. Approval alone is insufficient to cause learning, and
these data establish no advantage for earlier review. Keep this adverse result.

Next: add a separately specified positive-control workload that exercises eligible
promotion, plus reviewers with imperfect information and recovery after an actual
incident. Do not lower thresholds or choose favorable seeds based on this outcome.
