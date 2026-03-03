@echo off
:: ============================================================================
:: setup_lab_env.bat
:: Sets up the Python 3.11 virtual environment for the calibration capture script.
:: Run this once on the lab PC before your first capture session.
:: ============================================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================================
echo   Calibration Capture -- Lab Environment Setup
echo ============================================================
echo.

:: ----------------------------------------------------------------------------
:: 1. Check Python 3.11 is available
:: ----------------------------------------------------------------------------
echo [1/4] Checking for Python 3.11...

py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERROR: Python 3.11 not found.
    echo   The Phantom SDK wheel (pyphantom) requires exactly Python 3.11.
    echo.
    echo   Install Python 3.11 from: https://www.python.org/downloads/release/python-3119/
    echo   Make sure to tick "Add Python to PATH" during installation.
    echo   Then re-run this script.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('py -3.11 --version') do set PY_VERSION=%%v
echo   Found: !PY_VERSION!

:: ----------------------------------------------------------------------------
:: 2. Create virtual environment
:: ----------------------------------------------------------------------------
echo.
echo [2/4] Creating virtual environment (phantom_env)...

if exist phantom_env (
    echo   phantom_env already exists -- skipping creation.
) else (
    py -3.11 -m venv phantom_env
    if errorlevel 1 (
        echo   ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   Created phantom_env.
)

:: ----------------------------------------------------------------------------
:: 3. Install pyphantom from local Phantom SDK wheel
:: ----------------------------------------------------------------------------
echo.
echo [3/4] Installing pyphantom from local Phantom SDK wheel...

set PHANTOM_WHEEL=C:\Users\justi\OneDrive\My Documents\Phantom\PhSDK11\Python\pyphantom-3.11.11.806-py311-none-any.whl

if not exist "%PHANTOM_WHEEL%" (
    echo.
    echo   ERROR: Phantom SDK wheel not found at:
    echo   %PHANTOM_WHEEL%
    echo.
    echo   Ask your supervisor for the PhSDK11 installer, install it,
    echo   and then re-run this script.
    echo.
    pause
    exit /b 1
)

phantom_env\Scripts\pip install "%PHANTOM_WHEEL%" --quiet
if errorlevel 1 (
    echo   ERROR: Failed to install pyphantom.
    pause
    exit /b 1
)
echo   pyphantom installed.

:: ----------------------------------------------------------------------------
:: 4. Install remaining dependencies
:: ----------------------------------------------------------------------------
echo.
echo [4/4] Installing remaining dependencies (requirements.txt)...

phantom_env\Scripts\pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo   ERROR: Failed to install dependencies from requirements.txt.
    pause
    exit /b 1
)
echo   Dependencies installed.

:: ----------------------------------------------------------------------------
:: Done
:: ----------------------------------------------------------------------------
echo.
echo ============================================================
echo   Setup complete.
echo ============================================================
echo.
echo   To activate the environment, run:
echo.
echo     phantom_env\Scripts\activate
echo.
echo   Then test without hardware:
echo.
echo     python capture_calibration.py --dry-run
echo.
echo   And test the Arduino (plug it in first):
echo.
echo     python test_arduino.py --port COM4
echo.
pause
