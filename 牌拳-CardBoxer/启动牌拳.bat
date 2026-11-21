@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "CARD_BOXER_BATTLE_MODE=%~1"
if "%CARD_BOXER_BATTLE_MODE%"=="" set "CARD_BOXER_BATTLE_MODE=tactical"
set "CARD_BOXER_3D="
if "%~2"=="1" set "CARD_BOXER_3D=1"
set "CARD_BOXER_TACTICAL_BOT="
set "CARD_BOXER_TAIKOU_BOT="
set "CARD_BOXER_BOT="
set "CARD_BOXER_CAPTURE="
set "GAME_GODOT=%USERPROFILE%\Documents\godot\Godot_v4.5-stable_win64.exe"
if not exist "%GAME_GODOT%" set "GAME_GODOT=%USERPROFILE%\Downloads\Godot_v4.6.3-stable_win64\Godot_v4.6.3-stable_win64.exe"
if not exist "%GAME_GODOT%" (
  echo Godot 4 was not found. Open project.godot with Godot 4.5 or later.
  pause
  exit /b 1
)
set "GAME_LOG_DIR=%TEMP%\CardBoxerLogs"
if not exist "%GAME_LOG_DIR%" mkdir "%GAME_LOG_DIR%"
set "GAME_LOG_FILE=%GAME_LOG_DIR%\tactical-%RANDOM%-%RANDOM%.log"
start "" "%GAME_GODOT%" --maximized --path "%~dp0" --log-file "%GAME_LOG_FILE%"
