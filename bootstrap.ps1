# Thin launcher only. Does not install software, elevate or alter Docker.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArguments)
$ErrorActionPreference = 'Stop'
foreach ($candidate in @('python', 'python3', 'py')) {
    $executable = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike '*\Microsoft\WindowsApps\*' } | Select-Object -First 1
    if (-not $executable) { continue }
    $prefix = if ($candidate -eq 'py') { @('-3') } else { @() }
    $probe = & $executable.Source @prefix -c "import sys; print('homelab-python-ok' if sys.version_info >= (3,12) else 'unsupported')" 2>$null
    if ($LASTEXITCODE -ne 0 -or $probe -ne 'homelab-python-ok') { continue }
    & $executable.Source @prefix (Join-Path $PSScriptRoot 'homelab_cli.py') @CliArguments
    exit $LASTEXITCODE
}
Write-Error 'Python 3.12 or newer was not found. Install Python manually, then rerun this launcher.'
exit 2
