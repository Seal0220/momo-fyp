@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo Momo environment installer
echo Project:
echo %CD%
echo.

call :find_python
if errorlevel 1 goto :fail

call :ensure_uv
if errorlevel 1 goto :fail

echo.
echo Using uv:
uv --version
if errorlevel 1 goto :fail

echo.
echo Syncing project environment and dependencies...
uv sync --dev
if errorlevel 1 (
    echo.
    echo uv sync failed.
    goto :fail
)

echo.
echo Ensuring WebSocket support...
uv pip install --python ".venv\Scripts\python.exe" "websockets>=15.0.1"
if errorlevel 1 (
    echo.
    echo Failed to install WebSocket support.
    goto :fail
)

echo.
echo Verifying backend and WebSocket imports...
uv run python -c "import backend.app; import websockets; print('backend and websockets import ok')"
if errorlevel 1 (
    echo.
    echo Backend or WebSocket import verification failed.
    goto :fail
)

echo.
echo Installation complete.
echo You can start the backend with:
echo start.bat
echo.
pause
exit /b 0

:find_python
set "PYTHON_CMD="

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        goto :python_found
    )
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3.12"
        goto :python_found
    )

    py -3.11 -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3.11"
        goto :python_found
    )
)

echo Python 3.11 or 3.12 was not found.
echo Install Python 3.11/3.12, then run install.bat again.
exit /b 1

:python_found
echo Using Python command: %PYTHON_CMD%
%PYTHON_CMD% --version
exit /b 0

:ensure_uv
where uv >nul 2>nul
if not errorlevel 1 (
    uv --version >nul 2>nul
    if not errorlevel 1 (
        echo uv is already installed.
        uv --version
        exit /b 0
    )
    echo Found uv on PATH, but it did not run correctly. Installing uv with pip...
)

if errorlevel 1 echo uv was not found. Installing uv with pip...
%PYTHON_CMD% -m pip install --user uv
if errorlevel 1 (
    echo.
    echo Failed to install uv with pip.
    exit /b 1
)

for /f "delims=" %%I in ('%PYTHON_CMD% -m site --user-base') do set "PYTHON_USER_BASE=%%I"
set "USER_BIN=%PYTHON_USER_BASE%\Scripts"
if exist "%USER_BIN%\uv.exe" (
    set "PATH=%USER_BIN%;%PATH%"
)

where uv >nul 2>nul
if not errorlevel 1 (
    uv --version >nul 2>nul
    if not errorlevel 1 (
        echo uv installed successfully.
        uv --version
        exit /b 0
    )
)

if exist "%USER_BIN%\uv.exe" (
    set "PATH=%USER_BIN%;%PATH%"
    "%USER_BIN%\uv.exe" --version >nul 2>nul
    if errorlevel 1 (
        echo uv.exe exists but could not run:
        echo %USER_BIN%\uv.exe
        exit /b 1
    )
    echo uv installed successfully.
    "%USER_BIN%\uv.exe" --version
    exit /b 0
)

echo uv was installed, but uv.exe is not on PATH.
echo Expected uv.exe at:
echo %USER_BIN%\uv.exe
echo Close this terminal and run install.bat again, or add Python user Scripts to PATH.
exit /b 1

:fail
echo.
echo Installation failed.
pause
exit /b 1
