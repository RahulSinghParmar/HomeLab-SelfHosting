#Requires -Version 7.0
<#
Read-only Windows reference discovery. Writes a metadata-only PRIVATE report
outside this checkout. Never exports environment values or full task arguments.
Requires a reachable Docker engine; no application commands are executed.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$StackRoot
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'This reference collector supports Windows only.' }
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
if (-not [IO.Path]::IsPathFullyQualified($OutputPath)) { throw 'OutputPath must be absolute.' }
$reportPath = [IO.Path]::GetFullPath($OutputPath)
if ([IO.Path]::GetExtension($reportPath) -ne '.json') { throw 'OutputPath must be a JSON file.' }
if ($reportPath -eq $repositoryRoot -or $reportPath.StartsWith($repositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Private reports must be outside the repository.'
}
if (Test-Path -LiteralPath $reportPath) { throw 'Refusing to overwrite an existing report.' }
$ancestorPath = Split-Path -Parent $reportPath
while ($ancestorPath) {
    if (Test-Path -LiteralPath $ancestorPath) {
        $ancestor = Get-Item -LiteralPath $ancestorPath -Force
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Output ancestors must not be links or junctions.' }
    }
    $ancestorPath = Split-Path -Parent $ancestorPath
}
$resolvedStackRoot = (Resolve-Path -LiteralPath $StackRoot).Path.TrimEnd('\')
function Read-DockerJson([string[]]$Arguments) {
    $result = & docker @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Read-only Docker metadata command failed.' }
    return ($result | ConvertFrom-Json)
}
function Get-Keys($Value) {
    if ($null -eq $Value) { return @() }
    return @($Value.PSObject.Properties.Name | Sort-Object)
}
$ids = @(& docker ps -aq)
if ($LASTEXITCODE -ne 0 -or $ids.Count -eq 0) { throw 'No Docker inventory available.' }
$inspected = @(Read-DockerJson (@('inspect') + $ids))
$containers = @($inspected | ForEach-Object {
    $item = $_
    [pscustomobject][ordered]@{
        name = $item.Name.TrimStart('/')
        id = $item.Id
        imageReference = $item.Config.Image
        imageId = $item.Image
        state = $item.State.Status
        startedAt = $item.State.StartedAt
        restartCount = $item.RestartCount
        exitCode = $item.State.ExitCode
        health = $item.State.Health.Status
        project = $item.Config.Labels.'com.docker.compose.project'
        service = $item.Config.Labels.'com.docker.compose.service'
        workingDirectory = $item.Config.Labels.'com.docker.compose.project.working_dir'
        configFiles = $item.Config.Labels.'com.docker.compose.project.config_files'
        environmentNames = @($item.Config.Env | ForEach-Object { ($_ -split '=', 2)[0] } | Sort-Object)
        mounts = @($item.Mounts | Select-Object Type,Name,Source,Destination,RW)
        portBindings = $item.HostConfig.PortBindings
        networks = @(Get-Keys $item.NetworkSettings.Networks)
        restartPolicy = $item.HostConfig.RestartPolicy.Name
        memoryBytes = $item.HostConfig.Memory
        nanoCpus = $item.HostConfig.NanoCpus
        privileged = $item.HostConfig.Privileged
        readOnlyRootfs = $item.HostConfig.ReadonlyRootfs
        user = $item.Config.User
        deviceRequests = @($item.HostConfig.DeviceRequests | Select-Object Driver,Count,Capabilities)
    }
})
$imageIds = @($inspected.Image | Sort-Object -Unique)
$images = @(Read-DockerJson (@('image', 'inspect') + $imageIds) | ForEach-Object {
    [ordered]@{ id = $_.Id; tags = @($_.RepoTags); digests = @($_.RepoDigests); architecture = $_.Architecture; os = $_.Os }
})
$composeGroups = @($containers | Where-Object { $_.configFiles } | Group-Object { $_.configFiles })
$compose = @($composeGroups | ForEach-Object {
    $group = $_
    $paths = @($group.Name -split ',' | ForEach-Object {
        if ($_ -like '/data/coolify/*') { Join-Path $resolvedStackRoot ('coolify\' + $_.Substring('/data/coolify/'.Length).Replace('/', '\')) }
        else { $_ }
    })
    $arguments = @('compose')
    foreach ($path in $paths) { $arguments += @('-f', $path) }
    $arguments += @('config', '--format', 'json')
    $evidence = @($paths | ForEach-Object {
        [ordered]@{ path = $_; exists = (Test-Path -LiteralPath $_); sha256 = $(if (Test-Path -LiteralPath $_ -PathType Leaf) { (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash } else { $null }) }
    })
    try {
        $configuration = Read-DockerJson $arguments
        $services = @($configuration.services.PSObject.Properties | ForEach-Object {
            $definition = $_.Value
            [ordered]@{
                service = $_.Name
                image = $definition.image
                buildContext = $definition.build.context
                dockerfile = $definition.build.dockerfile
                environmentNames = @(Get-Keys $definition.environment)
                dependencies = @(Get-Keys $definition.depends_on)
                mounts = @($definition.volumes | Select-Object type,source,target,read_only)
                ports = @($definition.ports | Select-Object target,published,host_ip,protocol)
                profiles = @($definition.profiles)
                secretNames = @($definition.secrets | ForEach-Object { $_.source })
                healthcheckConfigured = ($null -ne $definition.healthcheck)
            }
        })
        [ordered]@{ project = $configuration.name; sources = $evidence; status = 'resolved'; services = $services }
    } catch {
        [ordered]@{ project = $group.Group[0].project; sources = $evidence; status = 'unresolved-read-only'; services = @() }
    }
})
$native = @()
$tasks = @()
try {
    $native = @(Get-CimInstance Win32_Service | Where-Object { $_.Name -match 'cloudflared|tailscale|beszel|jellyfin|docker|wsl' } | ForEach-Object {
        $service = $_
        $executable = if ($service.PathName -match '^"([^"]+)"') { $Matches[1] } elseif ($service.PathName -match '^(.+?\.exe)') { $Matches[1] } else { $null }
        [ordered]@{ name = $service.Name; state = $service.State; startMode = $service.StartMode; executable = $executable }
    })
    $tasks = @(Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' -and $_.TaskName -match 'affine|paperless|arrstack|coolify|firefly|glance|kuma|jellyfin|beszel|docker' } | ForEach-Object {
        $task = $_
        $info = Get-ScheduledTaskInfo -InputObject $task
        $actions = @($task.Actions | ForEach-Object {
            $scripts = @([regex]::Matches([string]$_.Arguments, '(?i)([A-Z]:\\[^"\r\n]*?\.(?:ps1|py))') | ForEach-Object { $_.Groups[1].Value })
            [ordered]@{ executable = $_.Execute; scriptPaths = $scripts }
        })
        [ordered]@{ name = $task.TaskName; state = [string]$task.State; lastRun = $(if ($null -ne $info.LastRunTime) { $info.LastRunTime.ToString('o') }); nextRun = $(if ($null -ne $info.NextRunTime) { $info.NextRunTime.ToString('o') }); lastResult = $info.LastTaskResult; actions = $actions }
    })
} catch { throw "Native metadata discovery failed ($($_.Exception.GetType().Name), line $($_.InvocationInfo.ScriptLineNumber)); no partial report was written." }
$report = [ordered]@{
    format = 1; collectedAtUtc = [DateTime]::UtcNow.ToString('o')
    privacy = 'PRIVATE: paths and identities; no environment values or full task arguments'
    dockerContext = (& docker context show)
    engineVersion = (& docker version --format '{{.Server.Version}}')
    composeVersion = (& docker compose version --short)
    containers = $containers; images = $images; compose = $compose; nativeServices = $native; tasks = $tasks
}
$reportParent = Split-Path -Parent $reportPath
if (-not (Test-Path -LiteralPath $reportParent)) { New-Item -ItemType Directory -Path $reportParent | Out-Null }
$report | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Output "Private metadata report written. Containers: $($containers.Count); Compose groups: $($compose.Count); tasks: $($tasks.Count)."
