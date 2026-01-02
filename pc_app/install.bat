@echo off
echo ========================================
echo VR Screen Streamer - Installation
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or later from python.org
    pause
    exit /b 1
)

echo Python found!
echo.

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo Installing CUDA runtime libraries for GPU acceleration...
pip install nvidia-cuda-nvrtc-cu12 nvidia-cuda-runtime-cu12 >nul 2>&1
echo CUDA libraries installed.

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo To run the application, use: run.bat
echo Or: python main.py
echo.
pause
