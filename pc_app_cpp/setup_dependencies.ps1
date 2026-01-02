# VR Streamer C++ - Dependency Setup Script
# Installs all required dependencies using vcpkg

param(
    [switch]$SkipVcpkg,
    [switch]$SkipCuda,
    [string]$VcpkgRoot
)

$ErrorActionPreference = "Stop"

Write-Host "=========================================="
Write-Host "  VR Streamer C++ Dependency Setup"
Write-Host "=========================================="
Write-Host ""

# Determine vcpkg location
if ($VcpkgRoot) {
    $vcpkgPath = $VcpkgRoot
} elseif ($env:VCPKG_ROOT) {
    $vcpkgPath = $env:VCPKG_ROOT
} else {
    $vcpkgPath = "$env:LOCALAPPDATA\vcpkg"
}

$vcpkgExe = Join-Path $vcpkgPath "vcpkg.exe"

# Install vcpkg if not present
if (-not $SkipVcpkg) {
    if (-not (Test-Path $vcpkgExe)) {
        Write-Host "[INFO] Installing vcpkg..."
        
        $vcpkgGit = "https://github.com/Microsoft/vcpkg.git"
        
        if (Test-Path $vcpkgPath) {
            Remove-Item -Recurse -Force $vcpkgPath
        }
        
        git clone $vcpkgGit $vcpkgPath
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to clone vcpkg!"
            exit 1
        }
        
        Push-Location $vcpkgPath
        .\bootstrap-vcpkg.bat -disableMetrics
        Pop-Location
        
        if (-not (Test-Path $vcpkgExe)) {
            Write-Host "[ERROR] vcpkg bootstrap failed!"
            exit 1
        }
        
        # Set environment variable
        [Environment]::SetEnvironmentVariable("VCPKG_ROOT", $vcpkgPath, "User")
        $env:VCPKG_ROOT = $vcpkgPath
        
        Write-Host "[INFO] vcpkg installed to: $vcpkgPath"
    } else {
        Write-Host "[INFO] vcpkg already installed at: $vcpkgPath"
    }
    
    # Update vcpkg
    Write-Host "[INFO] Updating vcpkg..."
    Push-Location $vcpkgPath
    git pull
    .\bootstrap-vcpkg.bat -disableMetrics
    Pop-Location
}

# Check for Visual Studio
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    Write-Host "[ERROR] Visual Studio not found!"
    Write-Host "Please install Visual Studio 2019 or later with:"
    Write-Host "  - Desktop development with C++"
    Write-Host "  - Windows 10/11 SDK"
    exit 1
}

$vsPath = & $vswhere -latest -property installationPath
Write-Host "[INFO] Found Visual Studio at: $vsPath"

# Install vcpkg packages
if (-not $SkipVcpkg) {
    Write-Host ""
    Write-Host "[INFO] Installing vcpkg packages..."
    Write-Host "       This may take 15-30 minutes on first run..."
    Write-Host ""
    
    $packages = @(
        "boost-asio:x64-windows",
        "boost-beast:x64-windows",
        "boost-system:x64-windows",
        "libjpeg-turbo:x64-windows"
    )
    
    foreach ($pkg in $packages) {
        Write-Host "[INFO] Installing $pkg..."
        & $vcpkgExe install $pkg
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] Failed to install $pkg"
        }
    }
    
    Write-Host "[INFO] vcpkg packages installed!"
}

# Check for CUDA
if (-not $SkipCuda) {
    Write-Host ""
    Write-Host "[INFO] Checking CUDA installation..."
    
    if ($env:CUDA_PATH -and (Test-Path "$env:CUDA_PATH\bin\nvcc.exe")) {
        $nvccVersion = & "$env:CUDA_PATH\bin\nvcc.exe" --version 2>&1 | Select-String "release"
        Write-Host "[INFO] CUDA found: $nvccVersion"
    } else {
        Write-Host "[WARN] CUDA not found!"
        Write-Host "       GPU acceleration will be disabled."
        Write-Host ""
        Write-Host "       To enable GPU features, install CUDA Toolkit from:"
        Write-Host "       https://developer.nvidia.com/cuda-downloads"
    }
}

# Check for CMake
$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmake) {
    Write-Host ""
    Write-Host "[WARN] CMake not found in PATH!"
    Write-Host "       Please install CMake from: https://cmake.org/download/"
    Write-Host "       Or use Visual Studio's bundled CMake."
} else {
    $cmakeVersion = & cmake --version | Select-Object -First 1
    Write-Host "[INFO] $cmakeVersion"
}

# Check for Ninja
$ninja = Get-Command ninja -ErrorAction SilentlyContinue
if (-not $ninja) {
    Write-Host "[INFO] Installing Ninja..."
    & $vcpkgExe install ninja:x64-windows
}

Write-Host ""
Write-Host "=========================================="
Write-Host "  Setup Complete!"
Write-Host "=========================================="
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open a new terminal to refresh environment variables"
Write-Host "  2. Run: .\build.bat"
Write-Host ""
Write-Host "Or build manually:"
Write-Host "  mkdir build"
Write-Host "  cd build"
Write-Host "  cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=$vcpkgPath\scripts\buildsystems\vcpkg.cmake .."
Write-Host "  cmake --build . --config Release"
Write-Host ""
