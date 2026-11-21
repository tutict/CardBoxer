@echo off
setlocal
cd /d "%~dp0"

rem Godot 4 editor, tried in the order the machine is known to have it.
set "GODOT=C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64.exe"
if not exist "%GODOT%" set "GODOT=C:\Users\tutic\Downloads\Godot_v4.6.3-stable_win64\Godot_v4.6.3-stable_win64.exe"
if not exist "%GODOT%" set "GODOT=C:\Users\tutic\Downloads\Godot_v4.6.1-stable_win64.exe\Godot_v4.6.1-stable_win64.exe"

if not exist "%GODOT%" (
  echo Godot 4 was not found in the usual places.
  echo Open project.godot in this folder with your Godot editor instead.
  pause
  exit /b 1
)

start "" "%GODOT%" --path "%~dp0"
exit /b 0
