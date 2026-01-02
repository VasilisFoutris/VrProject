@echo off
REM VR Streamer C++ - GUI Launcher
REM Uses the Python GUI to control the C++ backend

cd /d "%~dp0"

REM Check if executable exists
if not exist "build\Release\vr_streamer.exe" (
    echo [ERROR] C++ backend not found!
    echo Please run build.bat first.
    pause
    exit /b 1
)

REM Use venv Python if available
set "PYTHON=../.venv/Scripts/python.exe"
if not exist "%PYTHON%" (
    set "PYTHON=python"
)

REM Run the Python GUI
"%PYTHON%" gui.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start GUI.
    echo Make sure PyQt5 is installed: pip install PyQt5 qrcode pillow
    pause
)
