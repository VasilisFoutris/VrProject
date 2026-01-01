"""
VR Screen Streamer - Configuration Module
All tunable parameters for capture, compression, and streaming.
"""

import yaml
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class CaptureConfig:
    """Screen capture settings"""
    target_fps: int = 60  # Target frames per second
    capture_cursor: bool = True  # Include mouse cursor
    monitor_index: int = 0  # Monitor to capture (if no window selected)


@dataclass
class EncoderConfig:
    """Video encoding/compression settings"""
    # Quality presets: 'ultra_low_latency', 'low_latency', 'balanced', 'quality'
    preset: str = 'low_latency'
    
    # Output resolution (0 = native)
    output_width: int = 0
    output_height: int = 0
    
    # JPEG quality for fallback (1-100)
    jpeg_quality: int = 65
    
    # Target bitrate in Kbps (0 = auto)
    target_bitrate: int = 0
    
    # Compression method: 'jpeg', 'webp', 'raw'
    compression_method: str = 'jpeg'
    
    # VR mode: split screen for left/right eye
    vr_enabled: bool = True
    
    # Eye separation percentage (how much the image is offset for each eye)
    eye_separation: float = 0.03
    
    # Downscale factor (1.0 = no downscale, 0.5 = half resolution)
    # Lower = faster encoding. For VR, 0.65-0.75 is usually enough
    downscale_factor: float = 0.65


@dataclass
class NetworkConfig:
    """Network and streaming settings"""
    # Server settings
    host: str = '0.0.0.0'  # Listen on all interfaces
    port: int = 8765  # WebSocket port
    http_port: int = 8080  # HTTP server port for mobile app
    
    # Static IP (empty = auto-detect)
    static_ip: str = ''
    
    # Maximum clients
    max_clients: int = 2
    
    # Buffer settings
    send_buffer_size: int = 65536
    
    # Ping interval for connection monitoring
    ping_interval: float = 1.0


@dataclass
class Config:
    """Main configuration container"""
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    encoder: EncoderConfig = field(default_factory=EncoderConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    
    def save(self, filepath: str = 'config.yaml'):
        """Save configuration to YAML file"""
        with open(filepath, 'w') as f:
            yaml.dump(asdict(self), f, default_flow_style=False)
    
    @classmethod
    def load(cls, filepath: str = 'config.yaml') -> 'Config':
        """Load configuration from YAML file"""
        if not os.path.exists(filepath):
            return cls()
        
        with open(filepath, 'r') as f:
            data = yaml.safe_load(f)
        
        if data is None:
            return cls()
        
        config = cls()
        
        if 'capture' in data:
            config.capture = CaptureConfig(**data['capture'])
        if 'encoder' in data:
            config.encoder = EncoderConfig(**data['encoder'])
        if 'network' in data:
            config.network = NetworkConfig(**data['network'])
        
        return config


# Quality presets for quick configuration
# Downscale helps a lot with encoding speed - 0.5 = 4x less pixels to encode
QUALITY_PRESETS = {
    'ultra_performance': {  # For very slow PCs - maximum FPS
        'jpeg_quality': 40,
        'downscale_factor': 0.35,  # 35% = ~1/9 of pixels, 9x faster encode
        'target_fps': 60,
    },
    'ultra_low_latency': {
        'jpeg_quality': 50,
        'downscale_factor': 0.5,  # 50% = 1/4 of pixels, 4x faster encode
        'target_fps': 60,
    },
    'low_latency': {
        'jpeg_quality': 65,
        'downscale_factor': 0.65,
        'target_fps': 60,
    },
    'balanced': {
        'jpeg_quality': 75,
        'downscale_factor': 0.75,
        'target_fps': 45,
    },
    'quality': {
        'jpeg_quality': 85,
        'downscale_factor': 0.85,
        'target_fps': 30,
    },
}


def apply_preset(config: Config, preset_name: str) -> Config:
    """Apply a quality preset to the configuration"""
    if preset_name not in QUALITY_PRESETS:
        return config
    
    preset = QUALITY_PRESETS[preset_name]
    config.encoder.preset = preset_name
    config.encoder.jpeg_quality = preset['jpeg_quality']
    config.encoder.downscale_factor = preset['downscale_factor']
    config.capture.target_fps = preset['target_fps']
    
    return config
