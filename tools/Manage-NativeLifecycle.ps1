[CmdletBinding()]
param(
    [ValidateSet('Audit', 'Checkpoint', 'VerifyReboot')]
    [string]$Action = 'Audit',

    [string]$Policy,

    [string]$OutputDirectory = (Join-Path $env:TEMP 'homelab-native-lifecycle'),

    [string]$BeforeCheckpoint
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$cli = Join-Path $repoRoot 'homelab_cli.py'
if (-not $Policy) {
    $Policy = Join-Path $repoRoot 'modules\native-lifecycle\windows.example.json'
}

if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw 'HomeLab-SelfHosting CLI was not found.'
}
if (-not (Test-Path -LiteralPath $Policy -PathType Leaf)) {
    throw 'Native lifecycle policy was not found.'
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$audit = Join-Path $OutputDirectory "native-lifecycle-audit-$stamp.json"

function Invoke-HomeLabPython {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & python $cli @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "HomeLab-SelfHosting CLI exited with code $LASTEXITCODE."
    }
}

Invoke-HomeLabPython @(
    'native-lifecycle', 'audit',
    '--policy', $Policy,
    '--output', $audit
)
Invoke-HomeLabPython @(
    'native-lifecycle', 'validate-audit',
    '--audit', $audit
)

switch ($Action) {
    'Audit' {
        [pscustomobject]@{
            Action = $Action
            Audit = $audit
            AutomaticRebootPerformed = $false
        }
    }
    'Checkpoint' {
        $checkpoint = Join-Path $OutputDirectory "native-reboot-checkpoint-$stamp.json"
        Invoke-HomeLabPython @(
            'native-lifecycle', 'checkpoint',
            '--audit', $audit,
            '--output', $checkpoint
        )
        [pscustomobject]@{
            Action = $Action
            Audit = $audit
            Checkpoint = $checkpoint
            AutomaticRebootPerformed = $false
        }
    }
    'VerifyReboot' {
        if (-not $BeforeCheckpoint -or
            -not (Test-Path -LiteralPath $BeforeCheckpoint -PathType Leaf)) {
            throw 'VerifyReboot requires -BeforeCheckpoint from a previous boot.'
        }
        $evidence = Join-Path $OutputDirectory "native-reboot-evidence-$stamp.json"
        Invoke-HomeLabPython @(
            'native-lifecycle', 'validate-reboot',
            '--before', $BeforeCheckpoint,
            '--after', $audit,
            '--output', $evidence
        )
        Invoke-HomeLabPython @(
            'native-lifecycle', 'validate-reboot-evidence',
            '--evidence', $evidence
        )
        $proof = Get-Content -LiteralPath $evidence -Raw | ConvertFrom-Json -Depth 20
        if (-not $proof.passed) {
            throw ('Reboot verification failed: ' + [string]::Join(', ', $proof.blockers))
        }
        [pscustomobject]@{
            Action = $Action
            Audit = $audit
            Evidence = $evidence
            AutomaticRebootPerformed = $false
        }
    }
}
