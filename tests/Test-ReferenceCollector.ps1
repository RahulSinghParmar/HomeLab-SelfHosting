#Requires -Version 7.0
# Pure mocked metadata tests. Never contacts Docker or Windows service APIs.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Run the reference-collector fixtures on Windows.' }
$collectorPath = Join-Path $PSScriptRoot '../tools/Collect-ReferenceInventory.ps1'
$testParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$testRoot = Join-Path $testParent ('homelab-phase1-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$script:dockerCalls = 0
function Assert-True($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function docker {
    $script:dockerCalls++
    $global:LASTEXITCODE = 0
    $commandArgs = @($args)
    switch ($commandArgs[0]) {
        'ps' { 'fixture-a'; 'fixture-b' }
        'inspect' {
            @('a','b') | ForEach-Object {
                [ordered]@{
                    Name = "/fixture-$_"; Id = "fixture-$_"; Image = "sha256:fixture-$_"
                    Config = @{ Image = 'example/image:1'; Env = @('EXAMPLE_TOKEN=DO_NOT_EXPORT_THIS_VALUE'); User = '1000'; Labels = @{
                        'com.docker.compose.project' = "fixture-$_"
                        'com.docker.compose.service' = 'app'
                        'com.docker.compose.project.config_files' = (Join-Path $testRoot "$_-compose.yaml")
                    } }
                    State = @{ Status = 'running'; ExitCode = 0 }; Mounts = @()
                    HostConfig = @{ RestartPolicy = @{Name='unless-stopped'}; Memory=100; NanoCpus=0 }
                    NetworkSettings = @{Networks=@{fixture=@{}}}
                }
            } | ConvertTo-Json -Depth 10
        }
        'image' { @(@{Id='sha256:fixture';RepoTags=@('example/image:1');RepoDigests=@();Architecture='amd64';Os='linux'}) | ConvertTo-Json -Depth 5 }
        'compose' {
            if ($commandArgs[1] -eq 'version') { '5.5.1'; break }
            @{name='fixture';services=@{app=@{image='example/image:1';environment=@{EXAMPLE_TOKEN='DO_NOT_EXPORT_THIS_VALUE'};depends_on=@{};volumes=@();ports=@()}}} | ConvertTo-Json -Depth 8
        }
        'context' { 'fixture-local' }
        'version' { '29.8.1' }
        default { throw 'Unexpected Docker operation: read-only test failed.' }
    }
}
function Get-CimInstance { @([pscustomobject]@{Name='Cloudflared';State='Running';StartMode='Auto';PathName='"C:\Example\cloudflared.exe" --token DO_NOT_EXPORT_THIS_VALUE'}) }
function Get-ScheduledTask {
    @([pscustomobject]@{TaskName='AFFiNE Backup Daily';TaskPath='\';State='Ready';Actions=@([pscustomobject]@{Execute='pwsh.exe';Arguments='-File "C:\Example\backup.ps1" -Token DO_NOT_EXPORT_THIS_VALUE'})},
      [pscustomobject]@{TaskName='Glance fixture';TaskPath='\';State='Running';Actions=@([pscustomobject]@{Execute='python.exe';Arguments=$null})})
}
function Get-ScheduledTaskInfo { param($InputObject) [pscustomobject]@{LastRunTime=$null;NextRunTime=$null;LastTaskResult=267011} }
try {
    $output = Join-Path $testRoot 'inventory.json'
    & $collectorPath -OutputPath $output -StackRoot $testRoot
    $text = Get-Content -Raw -LiteralPath $output
    $report = $text | ConvertFrom-Json
    Assert-True ($report.containers.Count -eq 2) 'Container coverage failed.'
    Assert-True ($report.compose.Count -eq 2) 'Distinct Compose source groups collapsed.'
    Assert-True (@($report.compose | Where-Object status -eq 'resolved').Count -eq 2) 'Compose resolution failed.'
    Assert-True ($report.tasks.Count -eq 2) 'Null task arguments/timestamps not handled.'
    Assert-True ($text -notmatch 'DO_NOT_EXPORT_THIS_VALUE') 'A private value escaped metadata reduction.'
    Assert-True ($text -match 'EXAMPLE_TOKEN') 'Secret variable names should remain discoverable.'
    Assert-True ($report.nativeServices[0].executable -eq 'C:\Example\cloudflared.exe') 'Full service command line must not be retained.'
    $before = $script:dockerCalls
    foreach ($invalidOutput in @($output, (Join-Path (Split-Path $PSScriptRoot -Parent) 'private-test.json'), 'relative.json', (Join-Path $testRoot 'bad.txt'))) {
        $refused = $false
        try { & $collectorPath -OutputPath $invalidOutput -StackRoot $testRoot } catch { $refused = $true }
        Assert-True $refused 'Unsafe/existing output was not refused.'
    }
    Assert-True ($before -eq $script:dockerCalls) 'Refusal must happen before inventory calls.'
    Write-Output 'PASS: reference collector grouping, privacy, null metadata and output guards.'
} finally {
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    if ($resolvedTestRoot.StartsWith($testParent + '\', [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolvedTestRoot -Leaf) -like 'homelab-phase1-test-*') {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    } else { throw 'Test cleanup path validation failed.' }
}
