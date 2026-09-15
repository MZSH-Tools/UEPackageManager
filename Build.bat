@echo off
chcp 65001 >nul
title Build UEPackageManager
cd /d "%~dp0"

set "CONDA_BAT=%USERPROFILE%\miniconda3\condabin\conda.bat"
if not exist "%CONDA_BAT%" goto failed
call "%CONDA_BAT%" activate UEPackageManager
if errorlevel 1 goto failed

python -m PyInstaller UEPackageManager.spec --noconfirm
if errorlevel 1 goto failed
exit /b 0

:failed
echo UEPackageManager build failed.
pause
exit /b 1
