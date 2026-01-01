@echo off
echo ========================================
echo VR Screen Streamer
echo ========================================
echo.

REM Check if virtual environment exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found.
    echo Running install.bat first...
    call install.bat
    call venv\Scripts\activate.bat
)

echo.
echo Starting VR Screen Streamer...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo Application exited with error.
    pause
)
