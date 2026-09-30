@echo off
setlocal
set "RAGHOME=%~dp0"
"%RAGHOME%.venv\Scripts\python.exe" "%RAGHOME%cli.py" %*
