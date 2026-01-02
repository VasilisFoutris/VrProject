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

REM Set up CUDA environment for GPU acceleration
REM Use pip-installed CUDA 12 libraries (compatible with CuPy) first
set "PATH=%CD%\venv\Lib\site-packages\nvidia\cuda_nvrtc\bin;%PATH%"
set "PATH=%CD%\venv\Lib\site-packages\nvidia\cuda_runtime\bin;%PATH%"
set "PATH=%CD%\venv\Lib\site-packages\nvidia\nvjpeg\bin;%PATH%"

REM Add CUDA Toolkit bin to PATH for nvJPEG and other CUDA libraries
if exist "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin" (
    set "PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin;%PATH%"
)
if exist "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin\x64" (
    set "PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin\x64;%PATH%"
)

REM Add TurboJPEG library to PATH for fast JPEG encoding
if exist "C:\libjpeg-turbo64\bin" (
    set "PATH=C:\libjpeg-turbo64\bin;%PATH%"
)

REM Set CUDA_PATH to the system CUDA installation if available
if exist "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0" (
    set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0"
) else if exist "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6" (
    set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6"
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
