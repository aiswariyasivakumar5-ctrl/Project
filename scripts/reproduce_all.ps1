<#
.SYNOPSIS
    Complete reproducibility script for MCP Runtime Sentinel on Windows PowerShell.
.DESCRIPTION
    Verifies dataset and evaluation artifact checksums, then regenerates all
    publication tables, figures, novelty matrix report, and matched poisoning statistics.
.PARAMETER VerifyOnly
    Only run SHA-256 and artifact verification checks.
.PARAMETER RegenerateOnly
    Only regenerate tables, figures, and reports from existing raw files.
.PARAMETER Full
    Re-run 20-seed training, baseline comparisons, and ablation matrix.
#>
[CmdletBinding()]
param(
    [switch]$VerifyOnly,
    [switch]$RegenerateOnly,
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$ArgsList = @("$ScriptDir\reproduce_all.py")
if ($VerifyOnly) { $ArgsList += "--verify-only" }
if ($RegenerateOnly) { $ArgsList += "--regenerate-only" }
if ($Full) { $ArgsList += "--full" }

Write-Host "Running MCP Sentinel Reproducibility Pipeline..." -ForegroundColor Cyan
& python @ArgsList
if ($LASTEXITCODE -ne 0) {
    Write-Error "Reproduction pipeline failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
