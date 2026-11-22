@echo off
setlocal
cd /d "%~dp0"

rem 3D 表现层是双轨开关（arena.gd: use_3d = CARD_BOXER_3D 非空），默认关。
rem 原来的 play-2d.bat 不带这个变量，所以看到的仍是 2D 代码自绘小人。
rem 本脚本只做两件事：打开 3D、把控制台代码页切成 UTF-8。
rem 后者是为了 [TAIKOU] 回合日志（arena.gd 里含「你 / 青岚」等中文）在
rem 从 cmd 启动时不被 GBK 代码页解成乱码；GUI 版没有控制台，此行无害。
chcp 65001 >nul
set "CARD_BOXER_3D=1"

rem 锁 4.5：工程 project.godot 的 features 是 "4.5" + GL Compatibility。
set "GODOT=C:\Users\tutic\Documents\godot\Godot_v4.5-stable_win64.exe"
if not exist "%GODOT%" set "GODOT=C:\Users\tutic\Downloads\Godot_v4.6.3-stable_win64\Godot_v4.6.3-stable_win64.exe"

if not exist "%GODOT%" (
  echo Godot 4 was not found in the usual places.
  echo Open project.godot in this folder with your Godot editor instead.
  pause
  exit /b 1
)

start "" "%GODOT%" --path "%~dp0"
exit /b 0
