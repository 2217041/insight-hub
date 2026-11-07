@echo off
REM Run dev.ps1 without changing the machine's execution policy.
REM Usage: scripts\dev.cmd [-NoBrowser] [-SkipServices]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" %*