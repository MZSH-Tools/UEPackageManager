@echo off
chcp 65001 >nul
title UE Package Manager
cd /d "%~dp0"

set "CONDA_BAT=%USERPROFILE%\miniconda3\condabin\conda.bat"
if not exist "%CONDA_BAT%" goto failed
call "%CONDA_BAT%" activate UEPackageManager
if errorlevel 1 goto failed

set "PYTHONW=%CONDA_PREFIX%\pythonw.exe"
if not exist "%PYTHONW%" goto failed
start "" "%PYTHONW%" "%~dp0Main.py"
if errorlevel 1 goto failed
exit /b 0

:failed
echo UE Package Manager failed to start.
pause
exit /b 1
