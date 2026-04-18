@echo off
REM Double-click launcher for the CompactBench smoke-test harness.
REM Runs scripts\smoke.ps1 with ExecutionPolicy Bypass so it works on a fresh
REM Windows install without the user touching Set-ExecutionPolicy.
REM -NoExit keeps the window open after the menu exits so you can read the output.

setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "%SCRIPT_DIR%scripts\smoke.ps1" -RepoRoot "%SCRIPT_DIR:~0,-1%"
