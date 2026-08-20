param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,

    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [string]$RoundName = "R8_2",
    [switch]$Apply,
    [string]$CommitMessage = "",
    [switch]$Push,
    [switch]$CommitOnFailure
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $RepoRoot).Path
$ZipPath = (Resolve-Path $ZipPath).Path

$logDir = Join-Path $RepoRoot ".rlw\logs\update_rounds"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$logPath = Join-Path $logDir ("{0}_{1}.log" -f $RoundName, $stamp)
$extractRoot = Join-Path $env:TEMP ("RLW_{0}_{1}" -f $RoundName, $stamp)

# Prefer UTF-8 end-to-end on Windows PowerShell / Conda / Python boundaries.
try { chcp 65001 | Out-Null } catch {}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$roundFailed = $false
$applySucceeded = $false
$verifySucceeded = $false
$testsSucceeded = $false

. {
try {
    Write-Host "RLW UPDATE ROUND"
    Write-Host "------------------------------------------------------------"
    Write-Host ("round      : {0}" -f $RoundName)
    Write-Host ("timestamp  : {0}" -f (Get-Date -Format "o"))
    Write-Host ("repo       : {0}" -f $RepoRoot)
    Write-Host ("zip        : {0}" -f $ZipPath)
    Write-Host ("log        : {0}" -f $logPath)
    Write-Host ("powershell : {0}" -f $PSVersionTable.PSVersion)
    Write-Host ("conda_env  : {0}" -f $env:CONDA_DEFAULT_ENV)
    Write-Host ""

    Write-Host "COMMAND: git status -sb"
    & git -C $RepoRoot status -sb
    Write-Host "COMMAND: git rev-parse HEAD"
    & git -C $RepoRoot rev-parse HEAD
    Write-Host "COMMAND: python --version"
    & python --version
    Write-Host "COMMAND: ZIP SHA256"
    (Get-FileHash -Algorithm SHA256 $ZipPath).Hash

    if (Test-Path $extractRoot) {
        Remove-Item -Recurse -Force $extractRoot
    }
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    Write-Host ""
    Write-Host "COMMAND: Expand-Archive"
    Expand-Archive -Path $ZipPath -DestinationPath $extractRoot -Force

    $applyScript = Join-Path $extractRoot "apply_update.py"
    $verifyScript = Join-Path $extractRoot "verify_update.py"
    if (-not (Test-Path $applyScript)) { throw "apply_update.py not found in ZIP" }
    if (-not (Test-Path $verifyScript)) { throw "verify_update.py not found in ZIP" }

    Write-Host ""
    Write-Host "COMMAND: apply_update.py --dry-run"
    & python $applyScript $RepoRoot --dry-run
    if ($LASTEXITCODE -ne 0) { throw "dry-run failed with exit code $LASTEXITCODE" }

    if (-not $Apply) {
        Write-Host ""
        Write-Host "RESULT: DRY-RUN ONLY"
        return
    }

    Write-Host ""
    Write-Host "COMMAND: apply_update.py"
    & python $applyScript $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "apply failed with exit code $LASTEXITCODE" }
    $applySucceeded = $true

    Write-Host ""
    Write-Host "COMMAND: verify_update.py"
    & python $verifyScript $RepoRoot
    if ($LASTEXITCODE -eq 0) {
        $verifySucceeded = $true
    } else {
        $roundFailed = $true
        Write-Host ("VERIFY FAILED: exit_code={0}" -f $LASTEXITCODE)
    }

    Write-Host ""
    Write-Host "COMMAND: python -m workbench.cli.main --root <repo> dev test"
    Push-Location $RepoRoot
    try {
        & python -m workbench.cli.main --root $RepoRoot dev test
        if ($LASTEXITCODE -eq 0) {
            $testsSucceeded = $true
        } else {
            $roundFailed = $true
            Write-Host ("TESTS FAILED: exit_code={0}" -f $LASTEXITCODE)
        }
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "COMMAND: git status -sb"
    & git -C $RepoRoot status -sb
    Write-Host "COMMAND: git diff --stat"
    & git -C $RepoRoot diff --stat

    $mayCommit = $applySucceeded -and (($verifySucceeded -and $testsSucceeded) -or $CommitOnFailure)
    if ($CommitMessage -and $mayCommit) {
        Write-Host ""
        Write-Host "COMMAND: git add -A"
        & git -C $RepoRoot add -A
        Write-Host "COMMAND: git diff --cached --stat"
        & git -C $RepoRoot diff --cached --stat
        Write-Host "COMMAND: git commit"
        & git -C $RepoRoot commit -m $CommitMessage
        if ($LASTEXITCODE -ne 0) {
            $roundFailed = $true
            Write-Host ("COMMIT FAILED: exit_code={0}" -f $LASTEXITCODE)
        } elseif ($Push) {
            Write-Host "COMMAND: git push"
            & git -C $RepoRoot push
            if ($LASTEXITCODE -ne 0) {
                $roundFailed = $true
                Write-Host ("PUSH FAILED: exit_code={0}" -f $LASTEXITCODE)
            }
        }
    } elseif ($CommitMessage) {
        Write-Host ""
        Write-Host "COMMIT SKIPPED: verification/test failed; use -CommitOnFailure to publish diagnostic state."
    }

    Write-Host ""
    Write-Host "FINAL"
    Write-Host "COMMAND: git rev-parse HEAD"
    & git -C $RepoRoot rev-parse HEAD
    Write-Host "COMMAND: git status -sb"
    & git -C $RepoRoot status -sb
    Write-Host ("round_status: {0}" -f $(if ($roundFailed) { "FAILED" } else { "PASSED" }))
    Write-Host ("round_log   : {0}" -f $logPath)
}
catch {
    $roundFailed = $true
    Write-Host ""
    Write-Host "ROUND ERROR"
    Write-Host $_.Exception.Message
    Write-Host ("round_log   : {0}" -f $logPath)
}
finally {
    if (Test-Path $extractRoot) {
        Remove-Item -Recurse -Force $extractRoot -ErrorAction SilentlyContinue
    }
}
} *>&1 | Tee-Object -FilePath $logPath

# Normalize the final transcript to UTF-8 with BOM so editors and chat uploads
# detect the encoding consistently.
try {
    $transcriptText = [System.IO.File]::ReadAllText($logPath)
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($logPath, $transcriptText, $utf8Bom)
} catch {
    Write-Host ("LOG NORMALIZATION WARNING: {0}" -f $_.Exception.Message)
}

Write-Host ("ROUND_LOG: {0}" -f $logPath)
if ($roundFailed) { exit 1 }
exit 0
