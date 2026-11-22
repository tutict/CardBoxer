param(
    [ValidateSet('tactical', 'taikou', 'realtime')]
    [string]$Mode = 'tactical',
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path ([IO.Path]::GetTempPath()) 'CardBoxerLogs'
$logFile = Join-Path $logDirectory ($Mode + '-' + [Guid]::NewGuid().ToString('N') + '.log')

function Read-EngineLog([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    $errors = @($lines | Where-Object {
        $_ -match '^\s*(SCRIPT ERROR:|ERROR:)' -and
        $_ -notmatch 'root certificate store|resources still in use'
    })
    if ($errors.Count -gt 0) {
        throw ('Godot reported an error: ' + $errors[0] + '. Log: ' + $Path)
    }
    return $lines
}

function Test-NativeReady([string[]]$Lines) {
    return (($Lines -match '^F3D_READY\b').Count -gt 0 -and
        ($Lines -match '^F3D_FOE_READY\b').Count -gt 0)
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $projectDirectory 'project.godot'))) {
        throw 'project.godot is missing from the game directory.'
    }
    $enginePath = $null
    if ($env:CARD_BOXER_GODOT) {
        if (-not (Test-Path -LiteralPath $env:CARD_BOXER_GODOT -PathType Leaf)) {
            throw 'CARD_BOXER_GODOT must point to a Godot 4.5 or later executable.'
        }
        $enginePath = (Resolve-Path -LiteralPath $env:CARD_BOXER_GODOT).Path
    } else {
        $candidates = @(
            (Join-Path $projectDirectory 'godot.exe'),
            (Join-Path (Split-Path -Parent $projectDirectory) 'godot.exe'),
            (Join-Path $env:USERPROFILE 'Documents\godot\Godot_v4.5-stable_win64.exe'),
            (Join-Path $env:USERPROFILE 'Downloads\Godot_v4.6.3-stable_win64\Godot_v4.6.3-stable_win64.exe')
        )
        $candidates += @(Get-Command godot.exe, godot4.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        foreach ($candidate in $candidates) {
            if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                $enginePath = $candidate
                break
            }
        }
    }
    if (-not $enginePath) {
        throw 'Godot 4.5 or later was not found. Put godot.exe beside project.godot, add it to PATH, or set CARD_BOXER_GODOT to its full path.'
    }
    $consolePath = $enginePath -replace '(?i)(?<!_console)\.exe$', '_console.exe'
    if (-not (Test-Path -LiteralPath $consolePath)) { $consolePath = $enginePath }
    $engineVersion = (& $consolePath --version | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or $engineVersion -notmatch '^4\.(\d+)\.' -or [int]$Matches[1] -lt 5) {
        throw 'This game requires Godot 4.5 or later in the Godot 4 series.'
    }

    foreach ($variable in @('CARD_BOXER_TACTICAL_BOT', 'CARD_BOXER_TAIKOU_BOT', 'CARD_BOXER_BOT', 'CARD_BOXER_CAPTURE', 'CARD_BOXER_CAPTURE_HIT', 'CARD_BOXER_CAPTURE_AT', 'CARD_BOXER_RAGE_START')) {
        [Environment]::SetEnvironmentVariable($variable, $null, 'Process')
    }
    $env:CARD_BOXER_BATTLE_MODE = $Mode
    $env:CARD_BOXER_3D = '1'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

    $needsImport = -not (Test-Path -LiteralPath (Join-Path $projectDirectory '.godot\global_script_class_cache.cfg'))
    foreach ($importFile in @(Get-ChildItem -LiteralPath $projectDirectory -Filter '*.import' -File -Recurse)) {
        $importContent = [IO.File]::ReadAllText($importFile.FullName)
        if ($importContent -match '(?m)^path="res://([^"]+)"' -and -not (Test-Path -LiteralPath (Join-Path $projectDirectory $Matches[1]))) {
            $needsImport = $true
            break
        }
    }
    if ($needsImport) {
        Write-Host 'Importing game assets for the first launch...'
        $importLog = Join-Path $logDirectory ('import-' + [Guid]::NewGuid().ToString('N') + '.log')
        & $consolePath --headless --editor --import --path $projectDirectory --quit --log-file $importLog
        if ($LASTEXITCODE -ne 0) { throw ('Asset import failed. Log: ' + $importLog) }
        $null = Read-EngineLog $importLog
    }

    if ($Check) {
        & $consolePath --headless --path $projectDirectory --quit-after 3 --log-file $logFile
        if ($LASTEXITCODE -ne 0) { throw "The 3D game failed to start. Log: $logFile" }
        $lines = @(Read-EngineLog $logFile)
        if (-not (Test-NativeReady $lines)) {
            throw "Both native 3D models must finish loading. Log: $logFile"
        }
    } else {
        $arguments = @('--maximized', '--path', ('"' + $projectDirectory + '"'), '--log-file', ('"' + $logFile + '"'))
        $gameProcess = Start-Process -FilePath $enginePath -ArgumentList $arguments -WorkingDirectory $projectDirectory -WindowStyle Normal -PassThru
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        $ready = $false
        while ([DateTime]::UtcNow -lt $deadline) {
            $lines = @(Read-EngineLog $logFile)
            if (Test-NativeReady $lines) {
                $ready = $true
                break
            }
            if ($gameProcess.WaitForExit(250)) {
                throw "The 3D game closed during startup. Log: $logFile"
            }
        }
        if (-not $ready) {
            throw "The 3D models did not finish loading within 30 seconds. Log: $logFile"
        }
    }
    exit 0
} catch {
    Write-Host ('CardBoxer could not start: ' + $_.Exception.Message) -ForegroundColor Red
    if (-not $Check) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
