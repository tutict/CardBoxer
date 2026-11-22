param(
    [ValidateSet('motion','preview','match','performance','live','brightness')] [string]$Kind='motion',
    [string]$Name='retopo-motion',
    [ValidateRange(20,600)] [int]$TimeoutSeconds=300,
    [string]$Scenarios=''
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
if($Name -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Capture name must stay inside this task folder' }
$output=Join-Path $taskRoot ('shots/'+$Name)
if(Test-Path -LiteralPath $output) { throw 'Preserve existing evidence; choose another capture name' }
New-Item -ItemType Directory -Path $output | Out-Null
$engine=Join-Path $taskRoot ('logs/'+$Name+'-engine.log')
$stdout=Join-Path $taskRoot ('logs/'+$Name+'-stdout.log')
$stderr=Join-Path $taskRoot ('logs/'+$Name+'-stderr.log')
$scripts=@{
    motion=(Join-Path $PSScriptRoot 'render_motion_review.gd')
    brightness=(Join-Path $PSScriptRoot 'render_brightness.gd')
    preview=(Join-Path $taskRoot '..\native-3d-motion-fix\tools\natural_preview_capture_v2.gd')
    match='res://tests/native_match_capture.gd'
    performance='res://tests/natural_runtime_benchmark.gd'
    live='res://tests/native_live_check.gd'
}
$prior=@{}
foreach($entry in Get-ChildItem Env:) {
    if($entry.Name -match '^(CARD_BOXER_|NATIVE_|NATURAL_|MODEL_DETAIL_|RETOPO_)') {
        $prior[$entry.Name]=$entry.Value
        [Environment]::SetEnvironmentVariable($entry.Name,$null,'Process')
    }
}
$settings=@{CARD_BOXER_3D='1'; RETOPO_CAPTURE_OUT=$output; NATURAL_PREVIEW_OUT=$output;
    NATIVE_MATCH_OUT=$output; NATIVE_MATCH_CONTINUOUS='1'; NATURAL_BENCH_CAP='60';
    NATIVE_LIVE_OUT=$output; NATIVE_LIVE_CAPTURE='1'; NATIVE_LIVE_STRIDE='6'; NATIVE_LIVE_SCENARIOS=$Scenarios}
foreach($key in $settings.Keys) {
    if(-not $prior.ContainsKey($key)) { $prior[$key]=$null }
    [Environment]::SetEnvironmentVariable($key,[string]$settings[$key],'Process')
}
$argsList=@('--path',('"'+(Join-Path $taskRoot 'project')+'"'),'--log-file',('"'+$engine+'"'),
    '--script',('"'+$scripts[$Kind]+'"'),'--rendering-method','gl_compatibility',
    '--resolution','1280x720','--disable-vsync')
if($Kind -ne 'performance') { $argsList+=@('--fixed-fps','60') }
try {
    $owned=Start-Process -FilePath 'C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe' `
        -ArgumentList $argsList -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
} finally {
    foreach($key in $prior.Keys) { [Environment]::SetEnvironmentVariable($key,$prior[$key],'Process') }
}
Write-Output ('Owned '+$Kind+' renderer PID '+$owned.Id+' | log '+$engine)
$deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while(-not $owned.WaitForExit(1000)) {
    if([DateTime]::UtcNow -gt $deadline) { $owned.Kill(); $owned.WaitForExit(); throw 'Owned renderer timed out' }
}
$owned.Refresh()
Get-Content -LiteralPath $stdout -Tail 6
Get-Content -LiteralPath $stderr -Tail 6
if(Select-String -LiteralPath $stderr -Pattern 'SCRIPT ERROR:','Parse Error:','Failed to load script') { throw 'Capture failed; see real logs' }
if(Select-String -LiteralPath $stdout -Pattern '^FAIL:') { throw 'Capture acceptance failed; see real logs' }
Write-Output ('Owned renderer exit: '+$owned.ExitCode)
exit $owned.ExitCode
