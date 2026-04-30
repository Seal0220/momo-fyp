@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Momo backend from:
echo %CD%
echo.

"%PYTHON_EXE%" -m backend.app --reload

if errorlevel 1 (
    echo.
    echo Backend exited with an error.
    pause
)
