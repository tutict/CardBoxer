@echo off
setlocal
call "%~dp0launch.bat" -Mode tactical %*
exit /b %errorlevel%
