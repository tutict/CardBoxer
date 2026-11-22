@echo off
setlocal
call "%~dp0launch.bat" -Mode realtime %*
exit /b %errorlevel%
