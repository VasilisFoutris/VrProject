"""
VR Screen Streamer - Test Script
Run this to verify all components are working correctly.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all required imports work"""
    print("Testing imports...")
    
    errors = []
    
    try:
        import numpy as np
        print("  ✓ numpy")
    except ImportError as e:
        errors.append(f"numpy: {e}")
        print("  ✗ numpy")
    
    try:
        import cv2
        print("  ✓ opencv-python")
    except ImportError as e:
        errors.append(f"opencv-python: {e}")
        print("  ✗ opencv-python")
    
    try:
        import mss
        print("  ✓ mss")
    except ImportError as e:
        errors.append(f"mss: {e}")
        print("  ✗ mss")
    
    try:
        from PIL import Image
        print("  ✓ Pillow")
    except ImportError as e:
        errors.append(f"Pillow: {e}")
        print("  ✗ Pillow")
    
    try:
        import websockets
        print("  ✓ websockets")
    except ImportError as e:
        errors.append(f"websockets: {e}")
        print("  ✗ websockets")
    
    try:
        from PyQt5.QtWidgets import QApplication
        print("  ✓ PyQt5")
    except ImportError as e:
        errors.append(f"PyQt5: {e}")
        print("  ✗ PyQt5")
    
    try:
        import yaml
        print("  ✓ pyyaml")
    except ImportError as e:
        errors.append(f"pyyaml: {e}")
        print("  ✗ pyyaml")
    
    return errors


def test_capture():
    """Test screen capture functionality"""
    print("\nTesting screen capture...")
    
    try:
        from capture import WindowEnumerator, ScreenCapture
        
        # Test window enumeration
        windows = WindowEnumerator.enumerate_windows()
        print(f"  ✓ Found {len(windows)} capturable windows")
        
        # Test screen capture
        capture = ScreenCapture()
        frame = capture.capture_frame()
        if frame is not None:
            print(f"  ✓ Captured frame: {frame.shape}")
        else:
            print("  ✗ Failed to capture frame")
            return ["Screen capture failed"]
        
        capture.cleanup()
        return []
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return [str(e)]


def test_encoder():
    """Test video encoding"""
    print("\nTesting encoder...")
    
    try:
        import numpy as np
        from config import EncoderConfig
        from encoder import VREncoder
        
        # Create test frame
        test_frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        
        config = EncoderConfig()
        encoder = VREncoder(config)
        
        # Test encoding
        encoded = encoder.encode_frame(test_frame)
        if encoded:
            size_kb = len(encoded) / 1024
            print(f"  ✓ Encoded frame: {size_kb:.1f} KB")
            print(f"  ✓ Encode time: {encoder.get_last_encode_time():.1f} ms")
            return []
        else:
            print("  ✗ Encoding failed")
            return ["Encoding failed"]
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return [str(e)]


def test_server():
    """Test WebSocket server"""
    print("\nTesting server...")
    
    try:
        from config import NetworkConfig
        from server import StreamingServer
        
        config = NetworkConfig()
        server = StreamingServer(config)
        
        print(f"  ✓ Server IP: {server.get_server_ip()}")
        print(f"  ✓ Connection URL: {server.get_connection_url()}")
        
        return []
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return [str(e)]


def test_config():
    """Test configuration system"""
    print("\nTesting configuration...")
    
    try:
        from config import Config, apply_preset
        
        config = Config()
        print(f"  ✓ Default config created")
        
        # Test preset application
        config = apply_preset(config, 'low_latency')
        print(f"  ✓ Preset applied: quality={config.encoder.jpeg_quality}")
        
        return []
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return [str(e)]


def test_mobile_app():
    """Test that mobile app files exist"""
    print("\nTesting mobile app files...")
    
    mobile_path = os.path.join(os.path.dirname(__file__), '..', 'mobile_app')
    
    files = ['index.html', 'style.css', 'app.js']
    errors = []
    
    for file in files:
        path = os.path.join(mobile_path, file)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  ✓ {file} ({size} bytes)")
        else:
            print(f"  ✗ {file} not found")
            errors.append(f"Missing: {file}")
    
    return errors


def main():
    print("=" * 50)
    print("VR Screen Streamer - Test Suite")
    print("=" * 50)
    
    all_errors = []
    
    # Run tests
    all_errors.extend(test_imports())
    
    if not all_errors:  # Only continue if imports work
        all_errors.extend(test_config())
        all_errors.extend(test_capture())
        all_errors.extend(test_encoder())
        all_errors.extend(test_server())
    
    all_errors.extend(test_mobile_app())
    
    # Summary
    print("\n" + "=" * 50)
    if all_errors:
        print(f"FAILED: {len(all_errors)} error(s)")
        print("\nErrors:")
        for error in all_errors:
            print(f"  - {error}")
        print("\nPlease install dependencies: pip install -r requirements.txt")
        return 1
    else:
        print("ALL TESTS PASSED!")
        print("\nYou can now run: python main.py")
        return 0


if __name__ == "__main__":
    sys.exit(main())
