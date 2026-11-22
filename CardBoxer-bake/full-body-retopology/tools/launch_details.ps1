param([string]$Name='model-details',[switch]$BaselineOnly)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
if($Name -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Capture name must stay in the task folder' }
$output=Join-Path $taskRoot ('shots/'+$Name)
if(Test-Path -LiteralPath $output) { throw 'Preserve existing capture; use a new name' }
New-Item -ItemType Directory -Path $output | Out-Null
$logs=Join-Path $taskRoot 'logs'
$engine=Join-Path $logs ($Name+'-engine.log')
$stdout=Join-Path $logs ($Name+'-stdout.log')
$stderr=Join-Path $logs ($Name+'-stderr.log')
$env:MODEL_DETAIL_OUT=$output
$env:MODEL_DETAIL_BASELINE_ONLY=if($BaselineOnly) { '1' } else { '' }
$argsList=@('--path',('"'+(Join-Path $taskRoot 'project')+'"'),'--log-file',('"'+$engine+'"'),
    '--script',('"'+(Join-Path $PSScriptRoot 'render_model_details.gd')+'"'),
    '--rendering-method','gl_compatibility','--resolution','1280x720','--fixed-fps','60','--disable-vsync')
$owned=Start-Process -FilePath 'C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe' `
    -ArgumentList $argsList -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Output ('Owned detail renderer PID '+$owned.Id+' | log '+$engine)
$deadline=[DateTime]::UtcNow.AddMinutes(3)
while(-not $owned.WaitForExit(1000)) {
    if([DateTime]::UtcNow -gt $deadline) { $owned.Kill(); $owned.WaitForExit(); throw 'Owned detail renderer timed out' }
}
$owned.Refresh()
Get-Content -LiteralPath $stdout -Tail 4
Get-Content -LiteralPath $stderr -Tail 10
if(Select-String -LiteralPath $stderr -Pattern 'SCRIPT ERROR:','Parse Error:','Failed to load script') { throw 'Detail capture failed; see logs' }
Write-Output ('Detail renderer exit: '+$owned.ExitCode)
exit $owned.ExitCode
