"""
VR Screen Streamer - Window Capture Module
Handles window enumeration, selection, and screen capture on Windows.
"""

import ctypes
from ctypes import wintypes
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from PIL import Image
import mss
import mss.tools

# Windows API constants
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

# Load Windows DLLs
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi


@dataclass
class WindowInfo:
    """Information about a capturable window"""
    hwnd: int
    title: str
    class_name: str
    rect: Tuple[int, int, int, int]  # left, top, right, bottom
    is_visible: bool
    process_name: str = ""
    
    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]
    
    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]
    
    def __str__(self) -> str:
        return f"{self.title} ({self.width}x{self.height})"


class WindowEnumerator:
    """Enumerates and manages capturable windows"""
    
    @staticmethod
    def get_window_text(hwnd: int) -> str:
        """Get window title text"""
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buffer = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buffer, length)
        return buffer.value
    
    @staticmethod
    def get_class_name(hwnd: int) -> str:
        """Get window class name"""
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value
    
    @staticmethod
    def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """Get window rectangle using DWM for accurate bounds"""
        rect = wintypes.RECT()
        
        # Try DWM extended frame bounds first (more accurate)
        result = dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect)
        )
        
        if result != 0:
            # Fallback to regular GetWindowRect
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
        
        return (rect.left, rect.top, rect.right, rect.bottom)
    
    @staticmethod
    def is_window_visible(hwnd: int) -> bool:
        """Check if window is truly visible"""
        if not user32.IsWindowVisible(hwnd):
            return False
        
        # Check if window is cloaked (hidden by Windows)
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked)
        )
        
        return cloaked.value == 0
    
    @staticmethod
    def is_capturable_window(hwnd: int) -> bool:
        """Check if window should be shown in capture list"""
        # Must be visible
        if not WindowEnumerator.is_window_visible(hwnd):
            return False
        
        # Must have a title
        title = WindowEnumerator.get_window_text(hwnd)
        if not title or len(title.strip()) == 0:
            return False
        
        # Check window styles
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        # Skip tool windows without app window style
        if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
            return False
        
        # Get window rect and check size
        rect = WindowEnumerator.get_window_rect(hwnd)
        if rect is None:
            return False
        
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        # Skip tiny windows
        if width < 100 or height < 100:
            return False
        
        # Skip certain system windows
        class_name = WindowEnumerator.get_class_name(hwnd)
        skip_classes = [
            'Progman', 'WorkerW', 'Shell_TrayWnd',
            'Windows.UI.Core.CoreWindow', 'ApplicationFrameWindow'
        ]
        if class_name in skip_classes:
            return False
        
        return True
    
    @classmethod
    def enumerate_windows(cls) -> List[WindowInfo]:
        """Get list of all capturable windows"""
        windows = []
        
        def enum_callback(hwnd, lparam):
            if cls.is_capturable_window(hwnd):
                rect = cls.get_window_rect(hwnd)
                if rect:
                    windows.append(WindowInfo(
                        hwnd=hwnd,
                        title=cls.get_window_text(hwnd),
                        class_name=cls.get_class_name(hwnd),
                        rect=rect,
                        is_visible=True
                    ))
            return True
        
        # Create callback type
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        callback = WNDENUMPROC(enum_callback)
        
        user32.EnumWindows(callback, 0)
        
        # Sort by title
        windows.sort(key=lambda w: w.title.lower())
        
        return windows


class ScreenCapture:
    """High-performance screen capture - thread-safe"""
    
    def __init__(self):
        # Don't create mss here - it's not thread-safe
        # Will be created lazily in the thread that uses it
        self._sct = None
        self._sct_thread_id = None
        self.target_hwnd: Optional[int] = None
        self.last_frame: Optional[np.ndarray] = None
        self.last_capture_time: float = 0
        self.capture_count: int = 0
        self.fps_counter_start: float = time.time()
        self.current_fps: float = 0.0
    
    @property
    def sct(self):
        """Get mss instance for current thread (thread-safe)"""
        import threading
        current_thread = threading.current_thread().ident
        
        # Create new mss instance if needed (different thread or not created)
        if self._sct is None or self._sct_thread_id != current_thread:
            if self._sct is not None:
                try:
                    self._sct.close()
                except:
                    pass
            self._sct = mss.mss()
            self._sct_thread_id = current_thread
        
        return self._sct
    
    def set_target_window(self, hwnd: Optional[int]):
        """Set the window to capture"""
        self.target_hwnd = hwnd
    
    def get_capture_region(self) -> Optional[Dict]:
        """Get the region to capture based on target window"""
        if self.target_hwnd is None:
            # Capture primary monitor
            return self.sct.monitors[1]
        
        # Get window rect
        rect = WindowEnumerator.get_window_rect(self.target_hwnd)
        if rect is None:
            return None
        
        left, top, right, bottom = rect
        
        return {
            'left': left,
            'top': top,
            'width': right - left,
            'height': bottom - top
        }
    
    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame - optimized for performance"""
        region = self.get_capture_region()
        if region is None:
            return None
        
        try:
            # Capture using mss (very fast)
            screenshot = self.sct.grab(region)
            
            # Convert to numpy array (BGRA format) - use np.asarray for zero-copy when possible
            frame = np.asarray(screenshot, dtype=np.uint8)
            
            # Convert BGRA to BGR by slicing (creates a view, not a copy when contiguous)
            # Use reshape trick for faster slicing
            if frame.shape[2] == 4:
                frame = frame[:, :, :3].copy()  # Need copy for contiguous memory
            
            # Update stats
            self.capture_count += 1
            self.last_capture_time = time.time()
            self.last_frame = frame
            
            # Calculate FPS every second
            elapsed = time.time() - self.fps_counter_start
            if elapsed >= 1.0:
                self.current_fps = self.capture_count / elapsed
                self.capture_count = 0
                self.fps_counter_start = time.time()
            
            return frame
            
        except Exception as e:
            print(f"Capture error: {e}")
            return None
    
    def get_fps(self) -> float:
        """Get current capture FPS"""
        return self.current_fps
    
    def cleanup(self):
        """Clean up resources"""
        if self._sct:
            try:
                self._sct.close()
            except:
                pass
            self._sct = None
            self._sct_thread_id = None


class CaptureManager:
    """Manages window selection and capture operations"""
    
    def __init__(self):
        self.capture = ScreenCapture()
        self.selected_window: Optional[WindowInfo] = None
    
    def refresh_windows(self) -> List[WindowInfo]:
        """Refresh the list of available windows"""
        return WindowEnumerator.enumerate_windows()
    
    def select_window(self, window: WindowInfo):
        """Select a window for capture"""
        self.selected_window = window
        self.capture.set_target_window(window.hwnd)
    
    def select_full_screen(self):
        """Select full screen capture mode"""
        self.selected_window = None
        self.capture.set_target_window(None)
    
    def get_frame(self) -> Optional[np.ndarray]:
        """Get the next frame from the selected source"""
        return self.capture.capture_frame()
    
    def get_fps(self) -> float:
        """Get current capture FPS"""
        return self.capture.get_fps()
    
    def cleanup(self):
        """Clean up resources"""
        self.capture.cleanup()


# Test function
if __name__ == "__main__":
    print("Enumerating windows...")
    windows = WindowEnumerator.enumerate_windows()
    
    print(f"\nFound {len(windows)} capturable windows:")
    for i, window in enumerate(windows):
        print(f"  {i+1}. {window}")
    
    if windows:
        print("\nTesting capture on first window...")
        manager = CaptureManager()
        manager.select_window(windows[0])
        
        for i in range(10):
            frame = manager.get_frame()
            if frame is not None:
                print(f"  Frame {i+1}: {frame.shape}")
            time.sleep(0.1)
        
        print(f"  FPS: {manager.get_fps():.1f}")
        manager.cleanup()
