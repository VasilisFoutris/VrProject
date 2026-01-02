@echo off
REM VR Streamer C++ Run Script

setlocal EnableDelayedExpansion

set "EXE=build\vr_streamer.exe"

if not exist "%EXE%" (
    echo [ERROR] Executable not found: %EXE%
    echo Please run build.bat first.
    exit /b 1
)

echo.
echo ==========================================
echo   VR Streamer C++
echo ==========================================
echo.
echo Controls:
echo   Q      - Quit
echo   +/-    - Adjust quality
echo   1-5    - Quick quality presets
echo   W      - List windows
echo   M      - List monitors
echo   S      - Show stats
echo.
echo ==========================================
echo.

%EXE% %*

exit /b %ERRORLEVEL%
