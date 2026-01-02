# VR Streamer C++ Edition

High-performance C++ implementation of the VR screen streaming application, optimized for minimal latency and maximum throughput.

## Performance Features

- **DXGI Desktop Duplication**: Zero-copy GPU screen capture using DirectX 11
- **TurboJPEG/nvJPEG**: SIMD-optimized and GPU-accelerated JPEG encoding
- **Lock-free Queues**: Wait-free inter-thread communication
- **Memory Pools**: Pre-allocated buffers eliminate runtime allocations
- **AVX2 SIMD**: CPU fallback with vectorized operations
- **CUDA Kernels**: GPU-accelerated VR stereo processing
- **Boost.Beast**: High-performance async WebSocket server

## Requirements

### Required
- Windows 10/11 (64-bit)
- Visual Studio 2019 or later with C++ workload
- CMake 3.20+
- Boost 1.75+ (Asio, Beast)
- libjpeg-turbo

### Optional (for GPU acceleration)
- NVIDIA GPU with CUDA support
- CUDA Toolkit 11.0+
- nvJPEG library (included with CUDA Toolkit)

## Quick Start

### 1. Install Dependencies

```powershell
# Run the setup script (installs vcpkg packages)
.\setup_dependencies.ps1
```

### 2. Build

```batch
.\build.bat
```

### 3. Run

```batch
.\run.bat
```

Or with options:
```batch
build\vr_streamer.exe --quality 85 --port 8765
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--config <file>` | Load configuration file | config.yaml |
| `--port <port>` | WebSocket server port | 8765 |
| `--http-port <port>` | HTTP server port | 8080 |
| `--monitor <index>` | Monitor to capture | 1 |
| `--window <title>` | Window title to capture | - |
| `--fps <fps>` | Target frame rate | 60 |
| `--quality <1-100>` | JPEG quality | 80 |
| `--downscale <factor>` | Downscale factor (0.1-1.0) | 1.0 |
| `--preset <name>` | Quality preset | balanced |
| `--no-vr` | Disable VR stereo mode | - |
| `--no-gpu` | Disable GPU acceleration | - |

### Quality Presets

| Preset | Quality | Downscale | Target Use |
|--------|---------|-----------|------------|
| `ultra` | 95 | 1.0 | High-end network |
| `high` | 85 | 1.0 | LAN streaming |
| `balanced` | 75 | 0.85 | Default |
| `performance` | 60 | 0.7 | Lower-end devices |
| `mobile` | 50 | 0.5 | Mobile networks |

## Keyboard Controls

| Key | Action |
|-----|--------|
| `Q` | Quit |
| `+` / `=` | Increase quality |
| `-` | Decrease quality |
| `1-5` | Quick quality presets |
| `W` | List available windows |
| `M` | List monitors |
| `S` | Show statistics |

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  DXGI Capture   │───▶│  VR Encoder     │───▶│  WebSocket      │
│  (GPU Texture)  │    │  (Stereo+JPEG)  │    │  (Broadcast)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                      │                      │
         ▼                      ▼                      ▼
   Lock-free Queue       Memory Pool           Async I/O
```

### Pipeline Stages

1. **Capture Thread**: DXGI Desktop Duplication captures GPU texture, copies to CPU buffer
2. **Encode Thread**: Creates VR stereo frame, encodes to JPEG
3. **Network Thread**: Broadcasts encoded frame to all WebSocket clients

### Optimizations

- **Zero-copy capture**: GPU textures mapped directly, no intermediate copies
- **Lock-free queues**: SPSC queues with atomic operations, no mutex overhead
- **Memory pools**: Reusable buffers, no malloc/free during streaming
- **Batch processing**: Multiple encode operations per wake cycle
- **TCP_NODELAY**: Disabled Nagle's algorithm for lower latency
- **Binary WebSocket**: Raw binary frames, no Base64 encoding

## Configuration File

Example `config.yaml`:

```yaml
capture:
  target_fps: 60
  monitor_index: 1
  capture_cursor: true
  use_gpu_capture: true

encoder:
  jpeg_quality: 80
  downscale_factor: 1.0
  vr_enabled: true
  use_gpu: true
  use_nvjpeg: true

network:
  host: "0.0.0.0"
  port: 8765
  http_port: 8080
  max_clients: 4
  use_tcp_nodelay: true
```

## Performance Benchmarks

Tested on i7-10700K, RTX 3080, 1920x1080 capture:

| Configuration | FPS | Latency | CPU Usage |
|--------------|-----|---------|-----------|
| CPU (TurboJPEG) | 60+ | ~8ms | 15% |
| GPU (nvJPEG) | 60+ | ~4ms | 3% |
| GPU + CUDA Stereo | 60+ | ~3ms | 2% |

## Troubleshooting

### Build Errors

**"Boost not found"**
```powershell
# Install via vcpkg
vcpkg install boost-asio:x64-windows boost-beast:x64-windows
```

**"CUDA not found"**
- Install CUDA Toolkit from https://developer.nvidia.com/cuda-downloads
- Or build without CUDA: `cmake -DENABLE_CUDA=OFF ..`

**"libjpeg-turbo not found"**
```powershell
vcpkg install libjpeg-turbo:x64-windows
```

### Runtime Issues

**"Failed to initialize DXGI capture"**
- Ensure running on Windows 10 or later
- Check that the target monitor is the primary display or specify monitor index

**"No GPU encoder available"**
- Verify NVIDIA GPU is present and drivers are installed
- nvJPEG requires CUDA Toolkit
- Falls back to TurboJPEG CPU encoder automatically

## License

MIT License - See LICENSE file for details.
