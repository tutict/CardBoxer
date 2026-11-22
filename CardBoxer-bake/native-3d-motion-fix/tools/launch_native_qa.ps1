param(
    [ValidateSet('rest', 'capture', 'live', 'live-render')] [string]$Mode = 'capture',
    [string]$Project = '', [string]$OutName = '',
    [string]$Clips = 'stance,jab,cross,sweep', [string]$Scenarios = '',
    [ValidateSet('default', 'both')] [string]$Facing = 'default',
    [ValidateRange(1, 60)] [int]$Stride = 1,
    [ValidateRange(10, 3600)] [int]$TimeoutSeconds = 300,
    [switch]$ThreeD
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if ($Project -eq '') { $Project = Join-Path $taskRoot 'project' }
$Project = (Resolve-Path -LiteralPath $Project).Path
if ($OutName -eq '') { $OutName = $Mode }
if ($OutName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'OutName must be a simple name inside this task folder' }
$outBase = if ($Mode -in @('capture', 'live-render')) { 'shots' } else { 'reports' }
$outDir = Join-Path (Join-Path $taskRoot $outBase) $OutName
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$logDir = Join-Path $taskRoot 'logs'
$engineLog = Join-Path $logDir ($OutName + '-engine.log')
$stdoutLog = Join-Path $logDir ($OutName + '-stdout.log')
$stderrLog = Join-Path $logDir ($OutName + '-stderr.log')
$scriptPath = if ($Mode -eq 'rest') { Join-Path $PSScriptRoot 'rig_rest_probe.gd' } elseif ($Mode -eq 'capture') {
    Join-Path $taskRoot 'project/tests/native_motion_capture.gd'
} else { Join-Path $taskRoot 'project/tests/native_live_check.gd' }
$scriptPath = (Resolve-Path -LiteralPath $scriptPath).Path
$taskEnv = @{
    NATIVE_RIG_OUT = (Join-Path $taskRoot 'reports/rig-rest.json'); NATIVE_CAPTURE_OUT = $outDir;
    NATIVE_CAPTURE_CLIPS = $Clips; NATIVE_CAPTURE_FACING = $Facing;
    NATIVE_LIVE_OUT = $outDir; NATIVE_LIVE_SCENARIOS = $Scenarios; NATIVE_LIVE_STRIDE = [string]$Stride;
    NATIVE_LIVE_CAPTURE = $(if ($Mode -eq 'live-render') { '1' } else { '' });
    CARD_BOXER_3D = $(if ($ThreeD) { '1' } else { '' }); CARD_BOXER_BOT = ''; CARD_BOXER_TAIKOU_BOT = '';
    CARD_BOXER_CAPTURE = ''; CARD_BOXER_CAPTURE_HIT = ''; CARD_BOXER_CAPTURE_AT = '';
    CARD_BOXER_3D_YAW = ''; CARD_BOXER_3D_FLIP = ''; CARD_BOXER_3D_STANCE = ''; CARD_BOXER_RAGE_START = ''
}
$priorEnv = @{}
foreach ($key in $taskEnv.Keys) {
    $priorEnv[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, [string]$taskEnv[$key], 'Process')
}
$launchArgs = @('--path', ('"' + $Project + '"'), '--log-file', ('"' + $engineLog + '"'),
    '--script', ('"' + $scriptPath + '"'))
if ($Mode -in @('rest', 'live')) { $launchArgs += '--headless' } else {
    $launchArgs += @('--rendering-method', 'gl_compatibility', '--resolution', '1280x720', '--fixed-fps', '60', '--disable-vsync')
}
try {
    $launched = Start-Process -FilePath 'C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe' `
        -ArgumentList $launchArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
} finally {
    foreach ($key in $priorEnv.Keys) { [Environment]::SetEnvironmentVariable($key, $priorEnv[$key], 'Process') }
}
Write-Output ("Started owned Godot PID " + $launched.Id + " | output " + $outDir)
Write-Output ("Real log: " + $engineLog)
if (-not $launched.WaitForExit($TimeoutSeconds * 1000)) {
    # The Process object identifies only the helper launched above. No global kill.
    $launched.Kill()
    $launched.WaitForExit()
    throw ("Owned helper timed out: PID " + $launched.Id + " | " + $engineLog)
}
$launched.Refresh()
Get-Content -LiteralPath $stdoutLog -Tail 6
if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog -Tail 12 }
$runtimeErrors = Select-String -LiteralPath $stderrLog -Pattern '^SCRIPT ERROR:', 'Failed to load script', 'Parse Error:'
if ($runtimeErrors) { throw ('Godot runtime/parse errors detected; see ' + $stderrLog) }
Write-Output ("Exit code: " + $launched.ExitCode)
exit $launched.ExitCode
