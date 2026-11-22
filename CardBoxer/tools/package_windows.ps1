param(
    [string]$GodotPath = (Join-Path $env:USERPROFILE 'Documents\godot\Godot_v4.5-stable_win64_console.exe'),
    [string]$TemplatePath = '',
    [string]$OutputDirectory = '',
    [string]$Version = '0.1.0'
)

$ErrorActionPreference = 'Stop'
$taskProject = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path -Parent $taskProject) 'dist\windows'
}
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
$taskPreset = Join-Path $taskProject 'export_presets.cfg'
$taskOriginalPreset = [IO.File]::ReadAllText($taskPreset)
$taskUtf8 = New-Object Text.UTF8Encoding($false)
$taskSavedEnvironment = @{}

function Assert-EngineLog([string]$Path) {
    $taskLines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    $taskErrors = @($taskLines | Where-Object {
        $_ -match '^\s*(SCRIPT ERROR:|ERROR:)' -and
        $_ -notmatch 'root certificate store|resources still in use'
    })
    if ($taskErrors.Count) { throw ('Godot: ' + $taskErrors[0] + '. Log: ' + $Path) }
    return $taskLines
}

try {
    if (-not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) { throw 'Godot executable not found.' }
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Version must have three numeric components.' }
    New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
    if ($TemplatePath) {
        $taskTemplate = (Resolve-Path -LiteralPath $TemplatePath).Path.Replace('\','/')
        if ($taskTemplate.Contains('"')) { throw 'Template path contains an invalid quote.' }
        $taskOverride = [regex]::Replace($taskOriginalPreset, '(?m)^custom_template/release="[^"]*"', {
            param($match)
            return 'custom_template/release="' + $taskTemplate + '"'
        })
        [IO.File]::WriteAllText($taskPreset,$taskOverride,$taskUtf8)
    }
    $taskImportLog = Join-Path $taskOutput 'import.engine.log'
    Write-Host 'Importing and checking release resources...'
    & $GodotPath --headless --editor --import --path $taskProject --quit --log-file $taskImportLog *> (Join-Path $taskOutput 'import.out')
    if ($LASTEXITCODE -ne 0) { throw ('Resource import failed. Log: ' + $taskImportLog) }
    $null = Assert-EngineLog $taskImportLog

    $taskName = 'CardBoxer-v' + $Version + '-windows-x64'
    $taskExecutable = Join-Path $taskOutput ($taskName + '.exe')
    $taskExportLog = Join-Path $taskOutput 'export.engine.log'
    Write-Host 'Exporting the standalone Windows executable...'
    & $GodotPath --headless --path $taskProject --export-release 'Windows Desktop' $taskExecutable --log-file $taskExportLog *> (Join-Path $taskOutput 'export.out')
    if ($LASTEXITCODE -ne 0) { throw ('Export failed. Log: ' + $taskExportLog) }
    $null = Assert-EngineLog $taskExportLog
    if (-not (Test-Path -LiteralPath $taskExecutable -PathType Leaf)) { throw 'Export did not produce an executable.' }

    foreach ($taskVariable in @('CARD_BOXER_BATTLE_MODE','CARD_BOXER_3D','CARD_BOXER_SEED','CARD_BOXER_CAPTURE','CARD_BOXER_TACTICAL_CAPTURE','CARD_BOXER_TACTICAL_BOT','CARD_BOXER_TAIKOU_BOT','CARD_BOXER_BOT')) {
        $taskSavedEnvironment[$taskVariable] = [Environment]::GetEnvironmentVariable($taskVariable,'Process')
        [Environment]::SetEnvironmentVariable($taskVariable,$null,'Process')
    }
    $env:CARD_BOXER_3D = '1'
    $env:CARD_BOXER_SEED = '2026'
    foreach ($taskMode in @('tactical','taikou','realtime')) {
        $env:CARD_BOXER_BATTLE_MODE = $taskMode
        $taskSmokeLog = Join-Path $taskOutput ($taskMode + '.smoke.log')
        $taskSmoke = Start-Process -FilePath $taskExecutable -ArgumentList @('--headless','--quit-after','3','--log-file',('"' + $taskSmokeLog + '"')) -WorkingDirectory $taskOutput -WindowStyle Hidden -Wait -PassThru
        if ($taskSmoke.ExitCode -ne 0) { throw ('Packaged ' + $taskMode + ' startup failed.') }
        $taskLines = @(Assert-EngineLog $taskSmokeLog)
        if (-not ($taskLines -match '^F3D_READY\b') -or -not ($taskLines -match '^F3D_FOE_READY\b')) {
            throw ('Packaged ' + $taskMode + ' did not load both native 3D models.')
        }
        Write-Host ('PASS packaged ' + $taskMode + ' startup')
    }
    $taskReadme = @"
牌拳 CardBoxer v$Version — Windows x64

双击 $taskName.exe 开始游戏，无需安装 Godot。
六选三天赋，八张手牌编排五拍；敌方明三暗二。
1–9/0 选牌；Shift+数字换牌；Backspace 撤回；空格/Enter 开打。
鼠标拖动我方计划槽换序；H 查看上轮，Esc 关闭；P 暂停，R 重开。

图文玩法：https://github.com/tutict/CardBoxer
完整规则：https://github.com/tutict/CardBoxer/blob/main/CardBoxer/README.md
Godot Engine licensing is included in GODOT_LICENSE.txt.
"@
    [IO.File]::WriteAllText((Join-Path $taskOutput 'README.txt'),$taskReadme,$taskUtf8)
    Copy-Item -LiteralPath (Join-Path $taskProject 'GODOT_LICENSE.txt') -Destination (Join-Path $taskOutput 'GODOT_LICENSE.txt')
    $taskZip = Join-Path $taskOutput ($taskName + '.zip')
    Compress-Archive -LiteralPath $taskExecutable,(Join-Path $taskOutput 'README.txt'),(Join-Path $taskOutput 'GODOT_LICENSE.txt') -DestinationPath $taskZip -Force
    $taskHashes = @(Get-FileHash -Algorithm SHA256 -LiteralPath $taskExecutable,$taskZip)
    $taskChecksumLines = @($taskHashes | ForEach-Object { $_.Hash.ToLowerInvariant() + '  ' + (Split-Path $_.Path -Leaf) })
    [IO.File]::WriteAllLines((Join-Path $taskOutput 'SHA256SUMS.txt'),$taskChecksumLines,$taskUtf8)
    Write-Host ('EXE: ' + $taskExecutable)
    Write-Host ('ZIP: ' + $taskZip)
} finally {
    [IO.File]::WriteAllText($taskPreset,$taskOriginalPreset,$taskUtf8)
    foreach ($taskVariable in $taskSavedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($taskVariable,$taskSavedEnvironment[$taskVariable],'Process')
    }
}
