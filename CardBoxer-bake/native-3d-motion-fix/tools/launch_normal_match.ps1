param(
    [string]$Project = '',
    [string]$OutName = 'natural-v2-normal-match',
    [ValidateRange(10, 600)] [int]$TimeoutSeconds = 180
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if ($Project -eq '') { $Project = Join-Path $taskRoot 'project' }
$Project = (Resolve-Path -LiteralPath $Project).Path
if ($OutName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'OutName must stay inside this task folder' }
$outDir = Join-Path $taskRoot ('shots/' + $OutName)
if (Test-Path -LiteralPath $outDir) { throw 'Preserve the existing capture; choose a new OutName' }
New-Item -ItemType Directory -Path $outDir | Out-Null
$logDir = Join-Path $taskRoot 'logs'
$engineLog = Join-Path $logDir ($OutName + '-engine.log')
$stdoutLog = Join-Path $logDir ($OutName + '-stdout.log')
$stderrLog = Join-Path $logDir ($OutName + '-stderr.log')
$priorEnv = @{}
foreach ($item in Get-ChildItem Env:) {
    if ($item.Name.StartsWith('CARD_BOXER_') -or $item.Name.StartsWith('NATIVE_')) {
        $priorEnv[$item.Name] = $item.Value
        [Environment]::SetEnvironmentVariable($item.Name, '', 'Process')
    }
}
foreach ($key in @('NATIVE_MATCH_OUT', 'NATIVE_MATCH_CONTINUOUS')) {
    if (-not $priorEnv.ContainsKey($key)) { $priorEnv[$key] = $null }
}
[Environment]::SetEnvironmentVariable('NATIVE_MATCH_OUT', $outDir, 'Process')
[Environment]::SetEnvironmentVariable('NATIVE_MATCH_CONTINUOUS', '1', 'Process')
$launchArgs = @('--path', ('"' + $Project + '"'), '--log-file', ('"' + $engineLog + '"'),
    '--script', 'res://tests/native_match_capture.gd', '--rendering-method', 'gl_compatibility',
    '--resolution', '1280x720', '--fixed-fps', '60', '--disable-vsync')
try {
    $owned = Start-Process -FilePath 'C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe' `
        -ArgumentList $launchArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
} finally {
    foreach ($key in $priorEnv.Keys) {
        [Environment]::SetEnvironmentVariable($key, $priorEnv[$key], 'Process')
    }
}
Write-Output ('Owned normal-match PID: ' + $owned.Id + ' | real log: ' + $engineLog)
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while (-not $owned.WaitForExit(1000)) {
    if ([DateTime]::UtcNow -gt $deadline) {
        $owned.Kill()
        $owned.WaitForExit()
        throw ('Owned normal-match helper timed out: ' + $owned.Id)
    }
}
$owned.Refresh()
Get-Content -LiteralPath $stdoutLog -Tail 6
Get-Content -LiteralPath $stderrLog -Tail 10
if (Select-String -LiteralPath $stderrLog -Pattern 'SCRIPT ERROR:', 'Parse Error:', 'Failed to load script') {
    throw 'Normal-match runtime failed; see saved stderr log'
}
Write-Output ('Normal-match exit code: ' + $owned.ExitCode)
exit $owned.ExitCode
