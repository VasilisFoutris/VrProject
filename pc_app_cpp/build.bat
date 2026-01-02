@echo off
REM VR Streamer C++ Build Script
REM Builds the high-performance C++ version

setlocal EnableDelayedExpansion

echo ==========================================
echo   VR Streamer C++ Build Script
echo ==========================================
echo.

REM Check for Visual Studio
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo [ERROR] Visual Studio not found!
    echo Please install Visual Studio 2019 or later with C++ workload.
    exit /b 1
)

REM Find VS installation
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -property installationPath`) do (
    set "VS_PATH=%%i"
)

if not defined VS_PATH (
    echo [ERROR] Visual Studio installation not found!
    exit /b 1
)

echo [INFO] Found Visual Studio at: %VS_PATH%

REM Setup VS environment
call "%VS_PATH%\VC\Auxiliary\Build\vcvars64.bat" > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to setup Visual Studio environment!
    exit /b 1
)

REM Check for CMake
where cmake > nul 2>&1
if errorlevel 1 (
    echo [ERROR] CMake not found in PATH!
    echo Please install CMake from https://cmake.org/download/
    exit /b 1
)

REM Check for CUDA (optional)
set "CUDA_FOUND=0"
if defined CUDA_PATH (
    if exist "%CUDA_PATH%\bin\nvcc.exe" (
        set "CUDA_FOUND=1"
        echo [INFO] CUDA found at: %CUDA_PATH%
    )
)

REM Check for vcpkg
set "VCPKG_ROOT_LOCAL=%LOCALAPPDATA%\vcpkg"
set "VCPKG_ROOT_CUSTOM=%VCPKG_ROOT%"

if exist "%VCPKG_ROOT_CUSTOM%\vcpkg.exe" (
    set "VCPKG_CMAKE=%VCPKG_ROOT_CUSTOM%\scripts\buildsystems\vcpkg.cmake"
    echo [INFO] Using vcpkg from: %VCPKG_ROOT_CUSTOM%
) else if exist "%VCPKG_ROOT_LOCAL%\vcpkg.exe" (
    set "VCPKG_CMAKE=%VCPKG_ROOT_LOCAL%\scripts\buildsystems\vcpkg.cmake"
    echo [INFO] Using vcpkg from: %VCPKG_ROOT_LOCAL%
) else (
    echo [WARN] vcpkg not found. Dependencies will need manual configuration.
    set "VCPKG_CMAKE="
)

REM Create build directory
set "BUILD_DIR=build"
if not exist %BUILD_DIR% (
    mkdir %BUILD_DIR%
)

cd %BUILD_DIR%

REM Configure CMake
echo.
echo [INFO] Configuring CMake...
echo.

set "CMAKE_ARGS=-G Ninja"
set "CMAKE_ARGS=%CMAKE_ARGS% -DCMAKE_BUILD_TYPE=Release"

if defined VCPKG_CMAKE (
    set "CMAKE_ARGS=%CMAKE_ARGS% -DCMAKE_TOOLCHAIN_FILE=%VCPKG_CMAKE%"
)

if "%CUDA_FOUND%"=="1" (
    set "CMAKE_ARGS=%CMAKE_ARGS% -DENABLE_CUDA=ON"
) else (
    set "CMAKE_ARGS=%CMAKE_ARGS% -DENABLE_CUDA=OFF"
)

cmake %CMAKE_ARGS% ..
if errorlevel 1 (
    echo [ERROR] CMake configuration failed!
    cd ..
    exit /b 1
)

REM Build
echo.
echo [INFO] Building...
echo.

cmake --build . --config Release --parallel
if errorlevel 1 (
    echo [ERROR] Build failed!
    cd ..
    exit /b 1
)

cd ..

echo.
echo ==========================================
echo   Build Complete!
echo ==========================================
echo.
echo Executable: build\vr_streamer.exe
echo.
echo Run with: build\vr_streamer.exe --help
echo.

exit /b 0
