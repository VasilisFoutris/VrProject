"""
VR Screen Streamer - Video Encoder Module
Handles video compression with tunable quality and VR stereo split.
"""

import cv2
import numpy as np
from typing import Tuple, Optional
import time
from config import EncoderConfig, Config


class VREncoder:
    """Encodes frames for VR streaming with stereo split and compression"""
    
    def __init__(self, config: EncoderConfig):
        self.config = config
        self.encode_count: int = 0
        self.encode_time_total: float = 0.0
        self.last_encode_time: float = 0.0
        
        # JPEG encoding parameters
        self.jpeg_params = [
            cv2.IMWRITE_JPEG_QUALITY, config.jpeg_quality,
            cv2.IMWRITE_JPEG_OPTIMIZE, 1,
        ]
        
        # WebP encoding parameters
        self.webp_params = [
            cv2.IMWRITE_WEBP_QUALITY, config.jpeg_quality,
        ]
    
    def update_config(self, config: EncoderConfig):
        """Update encoder configuration"""
        self.config = config
        self.jpeg_params = [
            cv2.IMWRITE_JPEG_QUALITY, config.jpeg_quality,
            cv2.IMWRITE_JPEG_OPTIMIZE, 1,
        ]
        self.webp_params = [
            cv2.IMWRITE_WEBP_QUALITY, config.jpeg_quality,
        ]
    
    def create_stereo_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Create a side-by-side stereo frame for VR.
        Applies slight horizontal offset for each eye to create depth.
        """
        height, width = frame.shape[:2]
        
        # Calculate eye separation in pixels
        separation = int(width * self.config.eye_separation)
        
        # Create left and right eye views with horizontal offset
        # Left eye gets content shifted slightly right
        # Right eye gets content shifted slightly left
        
        left_eye = np.zeros_like(frame)
        right_eye = np.zeros_like(frame)
        
        if separation > 0:
            # Left eye: shift image right (view from left)
            left_eye[:, separation:] = frame[:, :width - separation]
            left_eye[:, :separation] = frame[:, :separation]  # Fill edge
            
            # Right eye: shift image left (view from right)
            right_eye[:, :width - separation] = frame[:, separation:]
            right_eye[:, width - separation:] = frame[:, width - separation:]  # Fill edge
        else:
            # No separation, just duplicate
            left_eye = frame.copy()
            right_eye = frame.copy()
        
        # Scale each eye to half width
        half_width = width // 2
        left_scaled = cv2.resize(left_eye, (half_width, height), interpolation=cv2.INTER_LINEAR)
        right_scaled = cv2.resize(right_eye, (half_width, height), interpolation=cv2.INTER_LINEAR)
        
        # Combine side by side
        stereo = np.hstack([left_scaled, right_scaled])
        
        return stereo
    
    def resize_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame according to configuration"""
        height, width = frame.shape[:2]
        
        # Apply downscale factor
        if self.config.downscale_factor < 1.0:
            new_width = int(width * self.config.downscale_factor)
            new_height = int(height * self.config.downscale_factor)
            frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        
        # Apply custom output resolution if specified
        if self.config.output_width > 0 and self.config.output_height > 0:
            frame = cv2.resize(
                frame, 
                (self.config.output_width, self.config.output_height),
                interpolation=cv2.INTER_LINEAR
            )
        
        return frame
    
    def compress_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """Compress frame to bytes using configured method"""
        try:
            if self.config.compression_method == 'jpeg':
                _, encoded = cv2.imencode('.jpg', frame, self.jpeg_params)
                return encoded.tobytes()
            
            elif self.config.compression_method == 'webp':
                _, encoded = cv2.imencode('.webp', frame, self.webp_params)
                return encoded.tobytes()
            
            elif self.config.compression_method == 'raw':
                return frame.tobytes()
            
            else:
                # Default to JPEG
                _, encoded = cv2.imencode('.jpg', frame, self.jpeg_params)
                return encoded.tobytes()
                
        except Exception as e:
            print(f"Compression error: {e}")
            return None
    
    def encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """
        Full encoding pipeline: resize, stereo split, compress.
        Returns compressed bytes ready for streaming.
        """
        start_time = time.perf_counter()
        
        try:
            # Step 1: Resize if needed
            frame = self.resize_frame(frame)
            
            # Step 2: Create VR stereo frame if enabled
            if self.config.vr_enabled:
                frame = self.create_stereo_frame(frame)
            
            # Step 3: Compress
            compressed = self.compress_frame(frame)
            
            # Update stats
            self.last_encode_time = (time.perf_counter() - start_time) * 1000  # ms
            self.encode_time_total += self.last_encode_time
            self.encode_count += 1
            
            return compressed
            
        except Exception as e:
            print(f"Encoding error: {e}")
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


class AdaptiveEncoder(VREncoder):
    """
    Adaptive encoder that adjusts quality based on performance.
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
        if avg_encode_time > self.target_frame_time * 0.5:
            # Reduce quality
            new_quality = max(30, self.config.jpeg_quality - 5)
            if new_quality != self.config.jpeg_quality:
                self.config.jpeg_quality = new_quality
                self._update_params()
                self.quality_history.append(('decrease', new_quality, avg_encode_time))
        
        # If we have headroom, increase quality
        elif avg_encode_time < self.target_frame_time * 0.3:
            new_quality = min(95, self.config.jpeg_quality + 2)
            if new_quality != self.config.jpeg_quality:
                self.config.jpeg_quality = new_quality
                self._update_params()
                self.quality_history.append(('increase', new_quality, avg_encode_time))
        
        # Reset stats periodically for fresh measurements
        if self.encode_count > 60:
            self.reset_stats()
    
    def _update_params(self):
        """Update compression parameters after quality change"""
        self.jpeg_params = [
            cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality,
            cv2.IMWRITE_JPEG_OPTIMIZE, 1,
        ]
        self.webp_params = [
            cv2.IMWRITE_WEBP_QUALITY, self.config.jpeg_quality,
        ]
    
    def encode_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """Encode frame with adaptive quality"""
        result = super().encode_frame(frame)
        
        # Periodically adapt quality
        if self.encode_count % 30 == 0:
            self.adapt_quality()
        
        return result


# Test function
if __name__ == "__main__":
    print("Testing VR Encoder...")
    
    # Create test frame
    test_frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    config = EncoderConfig()
    encoder = VREncoder(config)
    
    print(f"Original frame size: {test_frame.shape}")
    
    # Test stereo creation
    stereo = encoder.create_stereo_frame(test_frame)
    print(f"Stereo frame size: {stereo.shape}")
    
    # Test full encoding
    for quality in [50, 75, 90]:
        config.jpeg_quality = quality
        encoder.update_config(config)
        
        compressed = encoder.encode_frame(test_frame)
        if compressed:
            size_kb = len(compressed) / 1024
            print(f"Quality {quality}: {size_kb:.1f} KB, encode time: {encoder.get_last_encode_time():.1f} ms")
    
    # Test adaptive encoder
    print("\nTesting Adaptive Encoder...")
    adaptive = AdaptiveEncoder(config, target_fps=60)
    
    for i in range(100):
        compressed = adaptive.encode_frame(test_frame)
    
    print(f"Final quality: {adaptive.config.jpeg_quality}")
    print(f"Average encode time: {adaptive.get_average_encode_time():.1f} ms")
