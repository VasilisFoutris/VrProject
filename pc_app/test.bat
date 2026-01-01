@echo off
echo ========================================
echo VR Screen Streamer - Test Suite
echo ========================================
echo.

REM Check if virtual environment exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found.
    echo Please run install.bat first.
    pause
    exit /b 1
)

python test.py
pause
