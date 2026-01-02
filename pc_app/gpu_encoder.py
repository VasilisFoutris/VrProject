"""
VR Screen Streamer - GPU-Accelerated Encoder Module
Uses CUDA for image processing and nvJPEG for hardware JPEG encoding.
Falls back to CPU methods if GPU is not available.
"""

import sys
import os

# Set up CUDA DLL paths for Windows BEFORE importing CuPy
if sys.platform == 'win32':
    # Add CUDA Toolkit bin directories (including x64 subdirectory for nvjpeg)
    cuda_paths = [
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin',
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin\x64',  # nvjpeg DLLs
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin',
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin\x64',
    ]
    for cuda_bin in cuda_paths:
        if os.path.exists(cuda_bin):
            try:
                os.add_dll_directory(cuda_bin)
            except (OSError, AttributeError):
                pass
    
    # Find the nvidia packages in venv or site-packages
    for base_path in sys.path:
        nvidia_base = os.path.join(base_path, 'nvidia')
        if os.path.exists(nvidia_base):
            cuda_nvrtc_bin = os.path.join(nvidia_base, 'cuda_nvrtc', 'bin')
            cuda_runtime_bin = os.path.join(nvidia_base, 'cuda_runtime', 'bin')
            nvjpeg_bin = os.path.join(nvidia_base, 'nvjpeg', 'bin')
            for dll_dir in [cuda_nvrtc_bin, cuda_runtime_bin, nvjpeg_bin]:
                if os.path.exists(dll_dir):
                    try:
                        os.add_dll_directory(dll_dir)
                    except (OSError, AttributeError):
                        pass
            break

import numpy as np
from typing import Tuple, Optional
import time
from config import EncoderConfig

# GPU acceleration availability flags
HAS_CUDA = False
HAS_CUPY = False
HAS_NVJPEG = False
HAS_CV2_CUDA = False

# Try to import CUDA-accelerated libraries
cuda_stream = None
gpu_mat_cache = {}

try:
    import cupy as cp
    # Test that CuPy actually works with a simple operation
    _test = cp.array([1, 2, 3])
    _test_result = _test + 1  # This will fail if CUDA is not properly configured
    del _test, _test_result
    HAS_CUPY = True
    HAS_CUDA = True  # CuPy provides CUDA acceleration
    # Create a CUDA stream for async operations
    cuda_stream = cp.cuda.Stream(non_blocking=True)
    print("CuPy CUDA acceleration enabled")
except ImportError:
    print("CuPy not installed - GPU image processing disabled")
    print("  Install with: pip install cupy-cuda12x (adjust for your CUDA version)")
except Exception as e:
    print(f"CuPy not available: {e}")
    print("  GPU acceleration requires CUDA Toolkit to be installed.")
    print("  Download from: https://developer.nvidia.com/cuda-downloads")

# Try OpenCV CUDA (optional - requires custom OpenCV build with CUDA)
try:
    import cv2
    if cv2.cuda.getCudaEnabledDeviceCount() > 0:
        HAS_CV2_CUDA = True
        HAS_CUDA = True
        print(f"OpenCV CUDA enabled - {cv2.cuda.getCudaEnabledDeviceCount()} GPU(s) detected")
    # Silently skip if no CUDA devices - this is expected with pip opencv-python
except AttributeError:
    pass  # OpenCV from pip doesn't have CUDA support - this is normal
except Exception as e:
    pass

# Try nvJPEG through pynvjpeg for GPU JPEG encoding
try:
    from nvjpeg import NvJpeg
    # Test that nvJPEG actually works
    _test_nvjpeg = NvJpeg()
    del _test_nvjpeg
    HAS_NVJPEG = True
    HAS_CUDA = True
    print("nvJPEG GPU JPEG encoding enabled")
except ImportError as e:
    print(f"nvJPEG not available: {e}")
except Exception as e:
    print(f"nvJPEG init error: {e}")

# Also check for TurboJPEG as fast CPU fallback
HAS_TURBOJPEG = False
turbojpeg_encoder = None
try:
    from turbojpeg import TurboJPEG, TJPF_BGR
    # Try common installation paths for libjpeg-turbo on Windows
    turbojpeg_paths = [
        None,  # Let it auto-detect
        r'C:\libjpeg-turbo64\bin\turbojpeg.dll',
        r'C:\libjpeg-turbo-gcc64\bin\libturbojpeg.dll',
    ]
    for lib_path in turbojpeg_paths:
        try:
            turbojpeg_encoder = TurboJPEG(lib_path) if lib_path else TurboJPEG()
            HAS_TURBOJPEG = True
            print("TurboJPEG encoder enabled" + (f" ({lib_path})" if lib_path else ""))
            break
        except:
            continue
except Exception as e:
    pass

# Import standard libraries
import cv2


class GPUEncoder:
    """
    GPU-accelerated encoder for VR streaming.
    Uses CUDA for image resizing/stereo and nvJPEG for JPEG encoding.
    Automatically falls back to CPU if GPU is not available.
    """
    
    def __init__(self, config: EncoderConfig):
        self.config = config
        self.encode_count: int = 0
        self.encode_time_total: float = 0.0
        self.last_encode_time: float = 0.0
        
        # GPU state
        self.use_gpu = config.use_gpu and HAS_CUDA
        self.use_nvjpeg = config.use_nvjpeg and HAS_NVJPEG
        self.use_cupy = HAS_CUPY
        self.use_cv2_cuda = HAS_CV2_CUDA
        
        # Initialize nvJPEG encoder if available
        self.nvjpeg_encoder = None
        if self.use_nvjpeg:
            try:
                self.nvjpeg_encoder = NvJpeg()
                print(f"[GPU Encoder] nvJPEG initialized")
            except Exception as e:
                print(f"[GPU Encoder] nvJPEG init failed: {e}")
                self.use_nvjpeg = False
        
        # Initialize OpenCV CUDA if available
        self.cuda_stream = None
        if self.use_cv2_cuda:
            try:
                cv2.cuda.setDevice(config.gpu_device_id)
                self.cuda_stream = cv2.cuda.Stream()
                print(f"[GPU Encoder] OpenCV CUDA initialized on device {config.gpu_device_id}")
            except Exception as e:
                print(f"[GPU Encoder] OpenCV CUDA init failed: {e}")
                self.use_cv2_cuda = False
        
        # GPU memory cache for reusing allocations
        self._gpu_frame = None
        self._gpu_resized = None
        self._gpu_stereo = None
        
        # JPEG encoding parameters (CPU fallback)
        self.jpeg_params = [
            cv2.IMWRITE_JPEG_QUALITY, config.jpeg_quality,
            cv2.IMWRITE_JPEG_OPTIMIZE, 0,  # Disable optimization for speed
        ]
        
        # Report acceleration status
        self._report_status()
    
    def _report_status(self):
        """Report GPU acceleration status"""
        if self.use_gpu:
            accel = []
            if self.use_cv2_cuda:
                accel.append("OpenCV-CUDA (resize)")
            if self.use_cupy:
                accel.append("CuPy (stereo)")
            if self.use_nvjpeg:
                accel.append("nvJPEG (encode)")
            elif HAS_TURBOJPEG:
                accel.append("TurboJPEG (encode)")
            print(f"[GPU Encoder] Active accelerators: {', '.join(accel)}")
        else:
            print("[GPU Encoder] Running in CPU mode")
    
    def update_config(self, config: EncoderConfig):
        """Update encoder configuration"""
        self.config = config
        self.jpeg_params = [
            cv2.IMWRITE_JPEG_QUALITY, config.jpeg_quality,
            cv2.IMWRITE_JPEG_OPTIMIZE, 0,
        ]
    
    def _upload_to_gpu(self, frame: np.ndarray) -> 'cv2.cuda.GpuMat':
        """Upload frame to GPU memory"""
        if self._gpu_frame is None:
            self._gpu_frame = cv2.cuda.GpuMat()
        self._gpu_frame.upload(frame, self.cuda_stream)
        return self._gpu_frame
    
    def resize_frame_gpu(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame using GPU (OpenCV CUDA)"""
        height, width = frame.shape[:2]
        
        # Calculate new dimensions
        if self.config.downscale_factor < 1.0:
            new_width = int(width * self.config.downscale_factor)
            new_height = int(height * self.config.downscale_factor)
        elif self.config.output_width > 0 and self.config.output_height > 0:
            new_width = self.config.output_width
            new_height = self.config.output_height
        else:
            return frame  # No resize needed
        
        try:
            # Upload to GPU
            gpu_frame = self._upload_to_gpu(frame)
            
            # Resize on GPU (INTER_NEAREST is fastest)
            if self._gpu_resized is None:
                self._gpu_resized = cv2.cuda.GpuMat()
            
            cv2.cuda.resize(gpu_frame, (new_width, new_height), 
                          self._gpu_resized, 
                          interpolation=cv2.INTER_NEAREST,
                          stream=self.cuda_stream)
            
            # Download result
            self.cuda_stream.waitForCompletion()
            return self._gpu_resized.download()
            
        except Exception as e:
            print(f"[GPU Encoder] GPU resize failed: {e}, falling back to CPU")
            return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
    
    def resize_frame_cpu(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame using CPU"""
        height, width = frame.shape[:2]
        
        if self.config.downscale_factor < 1.0:
            new_width = int(width * self.config.downscale_factor)
            new_height = int(height * self.config.downscale_factor)
            frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
        
        if self.config.output_width > 0 and self.config.output_height > 0:
            frame = cv2.resize(
                frame, 
                (self.config.output_width, self.config.output_height),
                interpolation=cv2.INTER_NEAREST
            )
        
        return frame
    
    def resize_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame using best available method"""
        if self.use_cv2_cuda:
            return self.resize_frame_gpu(frame)
        return self.resize_frame_cpu(frame)
    
    def create_stereo_frame_cupy(self, frame: np.ndarray) -> np.ndarray:
        """Create stereo frame using CuPy (GPU)"""
        height, width = frame.shape[:2]
        half_width = width // 2
        separation = int(width * self.config.eye_separation)
        
        try:
            with cuda_stream:
                # Upload to GPU
                gpu_frame = cp.asarray(frame)
                
                if separation == 0:
                    # No separation - simple case
                    # We need to resize to half width, which CuPy doesn't do directly
                    # Download and use CPU resize, then upload result
                    resized = cv2.resize(frame, (half_width, height), interpolation=cv2.INTER_NEAREST)
                    gpu_resized = cp.asarray(resized)
                    
                    # Create stereo output
                    stereo = cp.empty((height, width, 3), dtype=cp.uint8)
                    stereo[:, :half_width] = gpu_resized
                    stereo[:, half_width:] = gpu_resized
                else:
                    # With separation - crop first on GPU, then resize on CPU
                    left_cropped = cp.asnumpy(gpu_frame[:, :width - separation])
                    right_cropped = cp.asnumpy(gpu_frame[:, separation:])
                    
                    left_scaled = cv2.resize(left_cropped, (half_width, height), interpolation=cv2.INTER_NEAREST)
                    right_scaled = cv2.resize(right_cropped, (half_width, height), interpolation=cv2.INTER_NEAREST)
                    
                    stereo = cp.empty((height, width, 3), dtype=cp.uint8)
                    stereo[:, :half_width] = cp.asarray(left_scaled)
                    stereo[:, half_width:] = cp.asarray(right_scaled)
                
                # Download result
                cuda_stream.synchronize()
                return cp.asnumpy(stereo)
                
        except Exception as e:
            print(f"[GPU Encoder] CuPy stereo failed: {e}, falling back to CPU")
            return self.create_stereo_frame_cpu(frame)
    
    def create_stereo_frame_cpu(self, frame: np.ndarray) -> np.ndarray:
        """Create a side-by-side stereo frame for VR (CPU)"""
        height, width = frame.shape[:2]
        half_width = width // 2
        separation = int(width * self.config.eye_separation)
        
        if separation == 0:
            # No separation - fastest path
            resized = cv2.resize(frame, (half_width, height), interpolation=cv2.INTER_NEAREST)
            stereo = np.empty((height, width, 3), dtype=np.uint8)
            stereo[:, :half_width] = resized
            stereo[:, half_width:] = resized
            return stereo
        
        # With separation
        left_end = width - separation
        left_scaled = cv2.resize(frame[:, :left_end], (half_width, height), interpolation=cv2.INTER_NEAREST)
        right_scaled = cv2.resize(frame[:, separation:], (half_width, height), interpolation=cv2.INTER_NEAREST)
        
        stereo = np.empty((height, width, 3), dtype=np.uint8)
        stereo[:, :half_width] = left_scaled
        stereo[:, half_width:] = right_scaled
        return stereo
    
    def create_stereo_frame(self, frame: np.ndarray) -> np.ndarray:
        """Create stereo frame using best available method"""
        if self.use_cupy:
            return self.create_stereo_frame_cupy(frame)
        return self.create_stereo_frame_cpu(frame)
    
    def compress_frame_nvjpeg(self, frame: np.ndarray) -> Optional[bytes]:
        """Compress frame using nvJPEG (GPU hardware encoding)"""
        try:
            # pynvjpeg expects BGR format directly (same as OpenCV)
            # No color conversion needed!
            
            # Encode using nvJPEG - the encode method handles BGR input
            encoded = self.nvjpeg_encoder.encode(frame, self.config.jpeg_quality)
            return bytes(encoded)
            
        except Exception as e:
            print(f"[GPU Encoder] nvJPEG encode failed: {e}")
            return None
    
    def compress_frame_cpu(self, frame: np.ndarray) -> Optional[bytes]:
        """Compress frame using CPU (TurboJPEG or OpenCV)"""
        try:
            if self.config.compression_method == 'jpeg':
                # Try TurboJPEG first (3-5x faster than OpenCV)
                if HAS_TURBOJPEG and turbojpeg_encoder is not None:
                    try:
                        return turbojpeg_encoder.encode(frame, quality=self.config.jpeg_quality)
                    except Exception:
                        pass
                
                # Fallback to OpenCV
                _, encoded = cv2.imencode('.jpg', frame, self.jpeg_params)
                return encoded.tobytes()
            
            elif self.config.compression_method == 'webp':
                _, encoded = cv2.imencode('.webp', frame, [cv2.IMWRITE_WEBP_QUALITY, self.config.jpeg_quality])
                return encoded.tobytes()
            
            elif self.config.compression_method == 'raw':
                return frame.tobytes()
            
            else:
                # Default to JPEG
                if HAS_TURBOJPEG and turbojpeg_encoder is not None:
                    return turbojpeg_encoder.encode(frame, quality=self.config.jpeg_quality)
                _, encoded = cv2.imencode('.jpg', frame, self.jpeg_params)
                return encoded.tobytes()
                
        except Exception as e:
            print(f"[GPU Encoder] CPU compression error: {e}")
            return None
    
    def compress_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """Compress frame using best available method"""
        # Try nvJPEG first if available and enabled
        if self.use_nvjpeg and self.nvjpeg_encoder is not None:
            result = self.compress_frame_nvjpeg(frame)
            if result is not None:
                return result
        
        # Fallback to CPU
        return self.compress_frame_cpu(frame)
    
    def encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """
        Full encoding pipeline: resize, stereo split, compress.
        Uses GPU acceleration where available.
        """
        start_time = time.perf_counter()
        
        try:
            # Step 1: Resize if needed (GPU or CPU)
            frame = self.resize_frame(frame)
            
            # Step 2: Create VR stereo frame if enabled (GPU or CPU)
            if self.config.vr_enabled:
                frame = self.create_stereo_frame(frame)
            
            # Step 3: Compress (GPU nvJPEG or CPU TurboJPEG/OpenCV)
            compressed = self.compress_frame(frame)
            
            # Update stats
            self.last_encode_time = (time.perf_counter() - start_time) * 1000  # ms
            self.encode_time_total += self.last_encode_time
            self.encode_count += 1
            
            return compressed
            
        except Exception as e:
            print(f"[GPU Encoder] Encoding error: {e}")
            return None
    
    def get_average_encode_time(self) -> float:
        """Get average encoding time in milliseconds"""
        if self.encode_count == 0:
            return 0.0
        return self.encode_time_total / self.encode_count
    
    def get_last_encode_time(self) -> float:
        """Get last encoding time in milliseconds"""
        return self.last_encode_time
    
    def reset_stats(self):
        """Reset encoding statistics"""
        self.encode_count = 0
        self.encode_time_total = 0.0
        self.last_encode_time = 0.0
    
    def get_acceleration_status(self) -> dict:
        """Get current acceleration status"""
        return {
            'gpu_enabled': self.use_gpu,
            'cv2_cuda': self.use_cv2_cuda,
            'cupy': self.use_cupy,
            'nvjpeg': self.use_nvjpeg,
            'turbojpeg': HAS_TURBOJPEG,
        }


class AdaptiveGPUEncoder(GPUEncoder):
    """
    Adaptive GPU encoder that adjusts quality based on performance.
    Maintains target frame rate by adjusting compression.
    """
    
    def __init__(self, config: EncoderConfig, target_fps: int = 60):
        super().__init__(config)
        self.target_fps = target_fps
        self.target_frame_time = 1000.0 / target_fps  # ms
        self.quality_history: list = []
        self.adaptation_enabled: bool = True
    
    def adapt_quality(self):
        """Adjust quality based on recent performance"""
        if not self.adaptation_enabled or self.encode_count < 30:
            return
        
        avg_encode_time = self.get_average_encode_time()
        
        # If encoding takes too long, reduce quality
        if avg_encode_time > self.target_frame_time * 0.8:
            new_quality = max(40, self.config.jpeg_quality - 3)
            if new_quality != self.config.jpeg_quality:
                self.config.jpeg_quality = new_quality
                self.jpeg_params = [cv2.IMWRITE_JPEG_QUALITY, new_quality, cv2.IMWRITE_JPEG_OPTIMIZE, 0]
                self.quality_history.append(('decrease', new_quality, avg_encode_time))
        
        # If we have lots of headroom, increase quality
        elif avg_encode_time < self.target_frame_time * 0.5:
            new_quality = min(95, self.config.jpeg_quality + 2)
            if new_quality != self.config.jpeg_quality:
                self.config.jpeg_quality = new_quality
                self.jpeg_params = [cv2.IMWRITE_JPEG_QUALITY, new_quality, cv2.IMWRITE_JPEG_OPTIMIZE, 0]
                self.quality_history.append(('increase', new_quality, avg_encode_time))
        
        # Reset stats periodically
        if self.encode_count > 60:
            self.reset_stats()
    
    def encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """Encode frame with adaptive quality"""
        result = super().encode_frame(frame)
        
        # Periodically adapt quality
        if self.encode_count % 30 == 0:
            self.adapt_quality()
        
        return result


def get_best_encoder(config: EncoderConfig):
    """
    Factory function to get the best encoder based on available hardware.
    Returns GPUEncoder if CUDA is available, otherwise falls back to VREncoder.
    """
    if config.use_gpu and HAS_CUDA:
        print("[Encoder Factory] Using GPU-accelerated encoder")
        return GPUEncoder(config)
    else:
        print("[Encoder Factory] Using CPU encoder (GPU not available or disabled)")
        # Import the original encoder as fallback
        from encoder import VREncoder
        return VREncoder(config)


# Test function
if __name__ == "__main__":
    print("=" * 60)
    print("GPU Encoder Test")
    print("=" * 60)
    
    print(f"\nCUDA available: {HAS_CUDA}")
    print(f"CuPy available: {HAS_CUPY}")
    print(f"nvJPEG available: {HAS_NVJPEG}")
    print(f"OpenCV CUDA available: {HAS_CV2_CUDA}")
    print(f"TurboJPEG available: {HAS_TURBOJPEG}")
    
    # Create test frame
    test_frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    config = EncoderConfig()
    config.use_gpu = True
    config.jpeg_quality = 75
    
    encoder = GPUEncoder(config)
    
    print(f"\nOriginal frame size: {test_frame.shape}")
    print(f"Acceleration status: {encoder.get_acceleration_status()}")
    
    # Warmup
    for _ in range(5):
        encoder.encode_frame(test_frame)
    encoder.reset_stats()
    
    # Benchmark
    print("\nBenchmarking...")
    for i in range(100):
        compressed = encoder.encode_frame(test_frame)
    
    if compressed:
        print(f"\nResults:")
        print(f"  Encoded size: {len(compressed) / 1024:.1f} KB")
        print(f"  Average encode time: {encoder.get_average_encode_time():.2f} ms")
        print(f"  Theoretical max FPS: {1000 / encoder.get_average_encode_time():.1f}")
