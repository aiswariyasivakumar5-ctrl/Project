param(
    [string]$Python = '.\.venv-repro\Scripts\python.exe',
    [string]$Output = 'results/novelty/publication-scale-20260921-rerun'
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Output already exists; choose a new path. No automatic retry or overwrite is performed.' }
& $Python -m sentinel_research.cli novelty-study --seeds 42,123,456,789,1001 --variants baseline,full,without_intent_provenance,without_capability_trust,without_dual_memory,approval_required --training-events 5000 --validation-events 1000 --test-events 3000 --validation-fpr 0.01 --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Study failed; partial outputs are retained. No aggregate analysis will run.' }
& $Python -m sentinel_research.novelty_report --source $Output --output "$Output-analysis"
if ($LASTEXITCODE -ne 0) { throw 'Analysis failed; figures will not be generated.' }
& $Python -m sentinel_research.novelty_figures --source $Output --statistics "$Output-analysis/statistics.json" --output "$Output-figures"
if ($LASTEXITCODE -ne 0) { throw 'Figure generation failed; inspect the retained report.' }
