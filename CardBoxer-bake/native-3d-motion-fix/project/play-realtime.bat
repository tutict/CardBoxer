@echo off
setlocal
chcp 65001 >nul
set "CARD_BOXER_BATTLE_MODE=realtime"
call "%~dp0play.bat"
