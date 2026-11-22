@echo off
setlocal
call "%~dp0launch.bat" -Mode taikou %*
exit /b %errorlevel%
