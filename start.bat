@echo off
chcp 65001 >nul
title qq-auto-bot · sandbox
cd /d "%~dp0"
python main.py
pause
