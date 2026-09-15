@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "CONDA_BAT=%USERPROFILE%\miniconda3\condabin\conda.bat"
if not exist "%CONDA_BAT%" goto failed
call "%CONDA_BAT%" activate UEPackageManager
if errorlevel 1 goto failed

set "PYTHONIOENCODING=utf-8"
python "%~dp0Main.py" %*
exit /b %ERRORLEVEL%

:failed
echo UE Package Manager CLI failed to start.
exit /b 1
