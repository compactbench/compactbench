<#
.SYNOPSIS
  Interactive smoke-test menu for CompactBench maintainers on Windows.

.DESCRIPTION
  Offers a pick-and-run menu for the common local verification tasks — single-
  baseline runs, cross-model head-to-heads, leaderboard rebuilds, case
  inspection. Saves typing long command lines in PowerShell, and handles the
  boring bookkeeping (temp dirs, output paths, cleanup) for you.

  Run via:
    - Double-click smoke.bat at the repo root, OR
    - From PowerShell:  .\scripts\smoke.ps1

  Requires Python 3.11+, `pip install compactbench[providers]`, and at least
  one provider API key set as an environment variable. See the "Environment"
  section the script prints on launch.
#>

[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

function Write-Title($text) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host $text -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}

function Write-Section($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Yellow
    Write-Host ("-" * $text.Length) -ForegroundColor DarkGray
}

function Write-Ok($text)   { Write-Host "  [OK]   $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  [WARN] $text" -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host "  [FAIL] $text" -ForegroundColor Red }

function Read-WithDefault($prompt, $default) {
    $input = Read-Host "$prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($input)) { return $default }
    return $input
}

function Invoke-CB {
    param([Parameter(ValueFromRemainingArguments = $true)]$Args)
    & python -m compactbench @Args
    if ($LASTEXITCODE -ne 0) {
        Write-Err "compactbench exited with code $LASTEXITCODE"
        return $false
    }
    return $true
}

# -----------------------------------------------------------------------------
# Environment check
# -----------------------------------------------------------------------------

function Test-Environment {
    Write-Section "Environment"

    # Python
    try {
        $pyver = (python --version 2>&1).Trim()
        Write-Ok "Python: $pyver"
    }
    catch {
        Write-Err "Python not found on PATH"
        return $false
    }

    # compactbench importable
    $cbCheck = python -c "import compactbench; print(compactbench.__version__ if hasattr(compactbench, '__version__') else 'installed')" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "compactbench not installed. Run:  pip install 'compactbench[providers]'"
        return $false
    }
    Write-Ok "compactbench: $cbCheck"

    # Repo root detection
    if (-not (Test-Path (Join-Path $script:RepoRoot "benchmarks\public"))) {
        Write-Err "benchmarks\public not found under $script:RepoRoot"
        Write-Warn "Run this script from the compactbench repo, or set -RepoRoot."
        return $false
    }
    Write-Ok "Repo root: $script:RepoRoot"
    Set-Location $script:RepoRoot

    # API keys
    $keys = @(
        @{ Name = "Groq";             Var = "COMPACTBENCH_GROQ_API_KEY" }
        @{ Name = "Anthropic";        Var = "COMPACTBENCH_ANTHROPIC_API_KEY" }
        @{ Name = "OpenAI";           Var = "COMPACTBENCH_OPENAI_API_KEY" }
        @{ Name = "Google AI Studio"; Var = "COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY" }
        @{ Name = "Ollama base URL";  Var = "COMPACTBENCH_OLLAMA_BASE_URL" }
    )
    $hasAnyKey = $false
    foreach ($k in $keys) {
        $val = [Environment]::GetEnvironmentVariable($k.Var, "User")
        if ([string]::IsNullOrWhiteSpace($val)) {
            $val = [Environment]::GetEnvironmentVariable($k.Var, "Process")
        }
        if ([string]::IsNullOrWhiteSpace($val)) {
            Write-Warn "$($k.Name): not set  ($($k.Var))"
        }
        else {
            Write-Ok "$($k.Name): set"
            $hasAnyKey = $true
        }
    }

    if (-not $hasAnyKey) {
        Write-Warn "No provider keys set. Only the 'mock' provider will work."
    }
    return $true
}

# -----------------------------------------------------------------------------
# Scratch directory — keeps smoke-run output out of the repo root
# -----------------------------------------------------------------------------

function Get-ScratchDir {
    $dir = Join-Path $script:RepoRoot ".smoke-runs"
    if (-not (Test-Path $dir)) {
        New-Item -Path $dir -ItemType Directory | Out-Null
    }
    return $dir
}

# -----------------------------------------------------------------------------
# Actions
# -----------------------------------------------------------------------------

function Invoke-SingleBaseline {
    Write-Section "Single baseline run"

    $methods = @("naive-summary", "structured-state", "hierarchical-summary", "hybrid-ledger")
    for ($i = 0; $i -lt $methods.Count; $i++) {
        Write-Host ("  [{0}] {1}" -f ($i + 1), $methods[$i])
    }
    $mi = [int](Read-WithDefault "Pick a method (1-$($methods.Count))" "4") - 1
    if ($mi -lt 0 -or $mi -ge $methods.Count) { Write-Warn "invalid"; return }
    $method = $methods[$mi]

    $providers = @(
        @{ Key = "mock";             Model = "mock-model" }
        @{ Key = "groq";             Model = "llama-3.3-70b-versatile" }
        @{ Key = "anthropic";        Model = "claude-3-5-haiku-latest" }
        @{ Key = "openai";           Model = "gpt-4o-mini" }
        @{ Key = "google-ai-studio"; Model = "gemini-2.0-flash-exp" }
        @{ Key = "ollama";           Model = "llama3.2" }
    )
    Write-Host ""
    for ($i = 0; $i -lt $providers.Count; $i++) {
        Write-Host ("  [{0}] {1}  (default model: {2})" -f ($i + 1), $providers[$i].Key, $providers[$i].Model)
    }
    $pi = [int](Read-WithDefault "Pick a provider (1-$($providers.Count))" "2") - 1
    if ($pi -lt 0 -or $pi -ge $providers.Count) { Write-Warn "invalid"; return }
    $provider = $providers[$pi].Key
    $defaultModel = $providers[$pi].Model
    $model = Read-WithDefault "Model" $defaultModel

    $suite = Read-WithDefault "Suite (starter | elite_practice)" "starter"
    $drift = Read-WithDefault "Drift cycles" "1"
    $count = Read-WithDefault "Cases per template" "1"

    $scratch = Get-ScratchDir
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $out = Join-Path $scratch "$method-$provider-$stamp.jsonl"

    Write-Host ""
    Write-Host "Running: $method on $provider/$model against $suite ..." -ForegroundColor Cyan
    $ok = Invoke-CB run `
        --method "built-in:$method" `
        --suite $suite `
        --provider $provider `
        --model $model `
        --drift-cycles $drift `
        --case-count $count `
        --output $out
    if (-not $ok) { return }

    Write-Host ""
    Write-Host "Scoring..." -ForegroundColor Cyan
    Invoke-CB score --results $out | Out-Null
    Write-Host ""
    Write-Ok "Results at: $out"
}

function Invoke-CrossModel {
    Write-Section "Cross-model head-to-head"
    Write-Host "Runs all 4 built-in baselines against a selected provider + model."
    Write-Host "This is the first data shape for the 'State of Compaction' post."
    Write-Host ""

    $providers = @(
        @{ Key = "groq";             Model = "llama-3.3-70b-versatile" }
        @{ Key = "anthropic";        Model = "claude-3-5-haiku-latest" }
        @{ Key = "openai";           Model = "gpt-4o-mini" }
        @{ Key = "google-ai-studio"; Model = "gemini-2.0-flash-exp" }
    )
    for ($i = 0; $i -lt $providers.Count; $i++) {
        Write-Host ("  [{0}] {1}  ({2})" -f ($i + 1), $providers[$i].Key, $providers[$i].Model)
    }
    $pi = [int](Read-WithDefault "Pick a provider (1-$($providers.Count))" "1") - 1
    if ($pi -lt 0 -or $pi -ge $providers.Count) { Write-Warn "invalid"; return }
    $provider = $providers[$pi].Key
    $model = Read-WithDefault "Model" $providers[$pi].Model

    $suite = Read-WithDefault "Suite (starter | elite_practice)" "starter"
    $drift = Read-WithDefault "Drift cycles" "1"
    $count = Read-WithDefault "Cases per template" "1"

    $scratch = Get-ScratchDir
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $methods = @("naive-summary", "structured-state", "hierarchical-summary", "hybrid-ledger")
    $results = @{}

    foreach ($method in $methods) {
        $out = Join-Path $scratch "$method-$provider-$stamp.jsonl"
        Write-Host ""
        Write-Host "[$method] running..." -ForegroundColor Cyan
        $ok = Invoke-CB run `
            --method "built-in:$method" `
            --suite $suite `
            --provider $provider `
            --model $model `
            --drift-cycles $drift `
            --case-count $count `
            --output $out
        if (-not $ok) {
            Write-Err "Aborting cross-model run."
            return
        }
        $results[$method] = $out
    }

    Write-Host ""
    Write-Title "Results — $provider / $model ($suite)"
    foreach ($method in $methods) {
        Write-Section $method
        Invoke-CB score --results $results[$method] | Out-Null
    }

    Write-Host ""
    Write-Ok "Results under: $scratch"
    Write-Host "Copy these into the 'State of Compaction' draft once you've run the matrix."
}

function Invoke-InspectCase {
    Write-Section "Inspect a generated case"

    $templates = @(
        "buried_constraint_starter_v1",
        "decision_override_starter_v1",
        "entity_confusion_starter_v1"
    )
    for ($i = 0; $i -lt $templates.Count; $i++) {
        Write-Host ("  [{0}] {1}" -f ($i + 1), $templates[$i])
    }
    $ti = [int](Read-WithDefault "Pick a template (1-$($templates.Count))" "1") - 1
    if ($ti -lt 0 -or $ti -ge $templates.Count) { Write-Warn "invalid"; return }
    $template = $templates[$ti]

    $seed = Read-WithDefault "Seed" "42"
    $diff = Read-WithDefault "Difficulty (easy | medium | hard | elite)" "medium"

    Write-Host ""
    Invoke-CB generate --template $template --seed $seed --difficulty $diff | Out-Null
}

function Invoke-LeaderboardRebuild {
    Write-Section "Leaderboard rebuild (local dry-run)"
    Write-Host "Runs scripts/rebuild_leaderboard.py over the current submissions/ tree."
    Write-Host "If there are no real submissions yet, the output will be an empty entries list — that's expected."
    Write-Host ""

    & python (Join-Path $script:RepoRoot "scripts\rebuild_leaderboard.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Err "rebuild_leaderboard.py exited with code $LASTEXITCODE"
        return
    }
    $json = Join-Path $script:RepoRoot "docs\data\leaderboard.json"
    if (Test-Path $json) {
        Write-Host ""
        Write-Ok "Wrote: $json"
        Write-Host ""
        Write-Host "---- contents ----" -ForegroundColor DarkGray
        Get-Content $json -Raw | ConvertFrom-Json | ConvertTo-Json -Depth 10
        Write-Host "------------------" -ForegroundColor DarkGray
        Write-Warn "Remember: docs/data/leaderboard.json is tracked. `git checkout -- docs/data/leaderboard.json` if you were just testing."
    }
}

function Clear-ScratchDir {
    $dir = Get-ScratchDir
    Write-Section "Clean scratch dir"
    $files = Get-ChildItem $dir -File -ErrorAction SilentlyContinue
    if (-not $files) {
        Write-Ok "Nothing to clean."
        return
    }
    Write-Host "Will delete $($files.Count) file(s) from $dir"
    $confirm = Read-Host "Proceed? [y/N]"
    if ($confirm -match "^(y|yes)$") {
        $files | Remove-Item -Force
        Write-Ok "Cleaned."
    }
    else {
        Write-Warn "Skipped."
    }
}

# -----------------------------------------------------------------------------
# Main menu loop
# -----------------------------------------------------------------------------

if (-not $RepoRoot) {
    $script:RepoRoot = Split-Path -Parent $PSScriptRoot
}
else {
    $script:RepoRoot = $RepoRoot
}

Write-Title "CompactBench Developer Smoke Tests"
if (-not (Test-Environment)) {
    Write-Host ""
    Write-Err "Fix the environment issues above before running tests."
    Read-Host "Press Enter to exit"
    exit 1
}

while ($true) {
    Write-Host ""
    Write-Section "Menu"
    Write-Host "  [1] Single baseline run           — one method × one provider"
    Write-Host "  [2] Cross-model head-to-head      — all 4 baselines × one provider"
    Write-Host "  [3] Inspect a generated case      — see a single deterministic case"
    Write-Host "  [4] Leaderboard rebuild (local)   — dry-run the rebuild_leaderboard script"
    Write-Host "  [5] Clean scratch dir             — delete cached .jsonl runs"
    Write-Host "  [Q] Quit"
    Write-Host ""
    $choice = Read-Host "Your choice"
    switch ($choice.ToLower()) {
        "1" { Invoke-SingleBaseline }
        "2" { Invoke-CrossModel }
        "3" { Invoke-InspectCase }
        "4" { Invoke-LeaderboardRebuild }
        "5" { Clear-ScratchDir }
        "q" { Write-Host ""; Write-Ok "Bye."; exit 0 }
        default { Write-Warn "Unknown choice: '$choice'" }
    }
}
