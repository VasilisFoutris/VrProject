"""
VR Screen Streamer - Main Entry Point
Launch the PC application with GUI.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up CUDA environment for CuPy GPU acceleration (Windows)
if sys.platform == 'win32':
    # Add DLL directories for pip-installed NVIDIA packages
    nvidia_base = os.path.join(os.path.dirname(__file__), 'venv', 'Lib', 'site-packages', 'nvidia')
    cuda_nvrtc_bin = os.path.join(nvidia_base, 'cuda_nvrtc', 'bin')
    cuda_runtime_bin = os.path.join(nvidia_base, 'cuda_runtime', 'bin')
    
    # Add DLL directories so ctypes can find CUDA libraries
    for dll_dir in [cuda_nvrtc_bin, cuda_runtime_bin]:
        if os.path.exists(dll_dir):
            try:
                os.add_dll_directory(dll_dir)
            except (OSError, AttributeError):
                pass

def check_dependencies():
    """Check if all required dependencies are installed"""
    missing = []
    
    try:
        import PyQt5
    except ImportError:
        missing.append('PyQt5')
    
    try:
        import mss
    except ImportError:
        missing.append('mss')
    
    try:
        import cv2
    except ImportError:
        missing.append('opencv-python')
    
    try:
        import numpy
    except ImportError:
        missing.append('numpy')
    
    try:
        import websockets
    except ImportError:
        missing.append('websockets')
    
    try:
        import yaml
    except ImportError:
        missing.append('pyyaml')
    
    if missing:
        print("Missing dependencies. Please install them with:")
        print(f"  pip install {' '.join(missing)}")
        print("\nOr run:")
        print("  pip install -r requirements.txt")
        return False
    
    return True


def main():
    """Main entry point"""
    print("=" * 50)
    print("VR Screen Streamer")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check platform
    if sys.platform != 'win32':
        print("Warning: This application is designed for Windows.")
        print("Some features may not work on other platforms.")
    
    # Import and run GUI
    try:
        from gui import main as gui_main
        gui_main()
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
