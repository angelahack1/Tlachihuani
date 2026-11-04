@echo off
setlocal
rem Run from a visible Command Prompt. Nothing is committed or uploaded.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\Build-Release.ps1" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Release generation failed. See the error above; no new ZIP was published to dist.
exit /b %RESULT%
