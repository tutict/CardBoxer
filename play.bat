@echo off
setlocal
call "%~dp0CardBoxer\play.bat" %*
exit /b %errorlevel%
