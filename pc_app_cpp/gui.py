"""
VR Screen Streamer - Python GUI Launcher for C++ Backend
Uses the PyQt5 GUI from pc_app to control the high-performance C++ backend.
Features: Dark/Light themes, System Tray, Keyboard Shortcuts, Notifications
"""

import sys
import os
import subprocess
import threading
import time
import re
import ctypes
from ctypes import wintypes
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider, QGroupBox, QGridLayout,
    QSpinBox, QCheckBox, QFrame, QListWidget, QListWidgetItem,
    QStatusBar, QMessageBox, QTabWidget, QTextEdit, QSizePolicy, QScrollArea,
    QSystemTrayIcon, QMenu, QAction, QShortcut, QToolTip, QStyle, QStyleFactory
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QProcess, QSettings
from PyQt5.QtGui import (
    QFont, QPixmap, QBrush, QColor, QIcon, QPalette, QKeySequence,
    QFontDatabase
)

try:
    import qrcode
    from PIL import Image
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


# ============================================================================
# Theme System
# ============================================================================

class ThemeMode(Enum):
    SYSTEM = "system"
    DARK = "dark"
    LIGHT = "light"


class ThemeManager:
    """Manages dark/light theme switching with OS detection"""
    
    # Dark theme colors (matching mobile app)
    DARK_COLORS = {
        'background': '#1a1a2e',
        'background_secondary': '#0f0f1a',
        'surface': '#16213e',
        'surface_hover': '#1e2a4a',
        'text_primary': '#ffffff',
        'text_secondary': '#b0b0b0',
        'primary': '#4CAF50',
        'primary_dark': '#388E3C',
        'secondary': '#2196F3',
        'error': '#f44336',
        'warning': '#ff9800',
        'success': '#4CAF50',
        'border': 'rgba(255, 255, 255, 0.1)',
    }
    
    # Light theme colors - MODERN DESIGN with subtle gradients and clean look
    LIGHT_COLORS = {
        'background': '#f8fafc',           # Very subtle blue-gray
        'background_secondary': '#f1f5f9', # Slightly darker
        'surface': '#ffffff',              # Pure white cards
        'surface_hover': '#f8fafc',        # Subtle hover
        'text_primary': '#0f172a',         # Dark slate
        'text_secondary': '#64748b',       # Slate gray
        'primary': '#10b981',              # Modern emerald green
        'primary_dark': '#059669',         # Darker emerald
        'secondary': '#3b82f6',            # Modern blue
        'error': '#ef4444',                # Modern red
        'warning': '#f59e0b',              # Amber
        'success': '#10b981',              # Emerald
        'border': '#e2e8f0',               # Soft border - no transparency
    }
    
    @staticmethod
    def is_system_dark_mode() -> bool:
        """Detect if Windows is using dark mode"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0  # 0 = dark, 1 = light
        except:
            return True  # Default to dark
    
    @classmethod
    def get_stylesheet(cls, mode: ThemeMode) -> str:
        """Generate complete stylesheet for the given theme"""
        if mode == ThemeMode.SYSTEM:
            colors = cls.DARK_COLORS if cls.is_system_dark_mode() else cls.LIGHT_COLORS
        elif mode == ThemeMode.DARK:
            colors = cls.DARK_COLORS
        else:
            colors = cls.LIGHT_COLORS
        
        is_light = mode == ThemeMode.LIGHT or (mode == ThemeMode.SYSTEM and not cls.is_system_dark_mode())
        
        # Text colors based on theme
        text_bright = '#0f172a' if is_light else '#ffffff'
        text_medium = '#475569' if is_light else '#cbd5e1'
        text_muted = '#64748b' if is_light else '#94a3b8'
        
        # Arrow color for spinbox/combobox
        arrow_color = '#475569' if is_light else '#ffffff'
        
        # Card shadow for light mode (more modern look)
        card_border = f"1px solid {colors['border']}" if is_light else f"1px solid {colors['border']}"
        
        return f"""
            /* Main Window - Clean background */
            QMainWindow, QWidget {{
                background-color: {colors['background']};
                color: {text_bright};
                font-size: 13px;
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }}
            
            /* Labels */
            QLabel {{
                color: {text_bright};
                font-size: 13px;
                padding: 2px;
            }}
            
            QLabel[subtitle="true"] {{
                color: {text_muted};
                font-size: 12px;
            }}
            
            /* Group Boxes - Modern card style with more padding */
            QGroupBox {{
                background-color: {colors['surface']};
                border: {card_border};
                border-radius: 12px;
                margin-top: 20px;
                padding: 20px;
                padding-top: 32px;
                font-weight: 600;
                font-size: 13px;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 16px;
                padding: 6px 14px;
                color: {colors['primary']};
                font-size: 14px;
                font-weight: 600;
            }}
            
            /* Buttons - Modern with subtle hover */
            QPushButton {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 500;
                min-height: 24px;
            }}
            
            QPushButton:hover {{
                background-color: {colors['background_secondary']};
                border-color: {colors['primary']};
            }}
            
            QPushButton:pressed {{
                background-color: {colors['background']};
            }}
            
            QPushButton:disabled {{
                color: {text_muted};
                background-color: {colors['background_secondary']};
                border-color: {colors['border']};
            }}
            
            QPushButton[primary="true"] {{
                background-color: {colors['primary']};
                color: white;
                border: none;
                font-weight: 600;
            }}
            
            QPushButton[primary="true"]:hover {{
                background-color: {colors['primary_dark']};
            }}
            
            QPushButton[danger="true"] {{
                background-color: {colors['error']};
                color: white;
                border: none;
            }}
            
            /* Input Fields - Clean and spacious */
            QLineEdit {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 8px;
                padding: 10px 14px;
                min-height: 22px;
                selection-background-color: {colors['primary']};
            }}
            
            QLineEdit:focus {{
                border: 2px solid {colors['primary']};
                padding: 9px 13px;
            }}
            
            QSpinBox {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 8px;
                padding: 8px 12px;
                padding-right: 36px;
                min-height: 26px;
                min-width: 90px;
            }}
            
            QSpinBox:focus {{
                border: 2px solid {colors['primary']};
            }}
            
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 28px;
                height: 15px;
                border-left: {card_border};
                border-top-right-radius: 8px;
                background-color: {colors['background']};
            }}
            
            QSpinBox::up-button:hover {{
                background-color: {colors['primary']};
            }}
            
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 28px;
                height: 15px;
                border-left: {card_border};
                border-top: {card_border};
                border-bottom-right-radius: 8px;
                background-color: {colors['background']};
            }}
            
            QSpinBox::down-button:hover {{
                background-color: {colors['primary']};
            }}
            
            QSpinBox::up-arrow {{
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-bottom: 7px solid {arrow_color};
                width: 0;
                height: 0;
            }}
            
            QSpinBox::up-button:hover QSpinBox::up-arrow,
            QSpinBox::up-arrow:hover {{
                border-bottom-color: white;
            }}
            
            QSpinBox::down-arrow {{
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 7px solid {arrow_color};
                width: 0;
                height: 0;
            }}
            
            QSpinBox::down-button:hover QSpinBox::down-arrow,
            QSpinBox::down-arrow:hover {{
                border-top-color: white;
            }}
            
            QComboBox {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 8px;
                padding: 10px 14px;
                padding-right: 36px;
                min-height: 22px;
            }}
            
            QComboBox:focus {{
                border: 2px solid {colors['primary']};
            }}
            
            QComboBox::drop-down {{
                border: none;
                width: 30px;
                padding-right: 10px;
            }}
            
            QComboBox::down-arrow {{
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 7px solid {arrow_color};
                width: 0;
                height: 0;
            }}
            
            QComboBox QAbstractItemView {{
                background-color: {colors['surface']};
                color: {text_bright};
                selection-background-color: {colors['primary']};
                selection-color: white;
                border: {card_border};
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }}
            
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                border-radius: 4px;
            }}
            
            QComboBox QAbstractItemView::item:hover {{
                background-color: {colors['background_secondary']};
            }}
            
            /* Sliders - Modern rounded */
            QSlider::groove:horizontal {{
                background: {colors['background_secondary']};
                height: 8px;
                border-radius: 4px;
            }}
            
            QSlider::handle:horizontal {{
                background: {colors['primary']};
                width: 20px;
                height: 20px;
                margin: -6px 0;
                border-radius: 10px;
                border: 3px solid {colors['surface']};
            }}
            
            QSlider::handle:horizontal:hover {{
                background: {colors['primary_dark']};
            }}
            
            QSlider::sub-page:horizontal {{
                background: {colors['primary']};
                border-radius: 4px;
            }}
            
            /* Checkboxes - Modern with clear state */
            QCheckBox {{
                color: {text_bright};
                spacing: 12px;
                font-size: 13px;
                padding: 4px;
            }}
            
            QCheckBox::indicator {{
                width: 24px;
                height: 24px;
                border-radius: 6px;
                border: 2px solid {colors['border']};
                background-color: {colors['surface']};
            }}
            
            QCheckBox::indicator:hover {{
                border-color: {colors['primary']};
            }}
            
            QCheckBox::indicator:checked {{
                background-color: {colors['primary']};
                border-color: {colors['primary']};
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjMiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBvbHlsaW5lIHBvaW50cz0iMjAgNiA5IDE3IDQgMTIiPjwvcG9seWxpbmU+PC9zdmc+);
            }}
            
            /* Tab Widget - Clean modern tabs */
            QTabWidget::pane {{
                border: {card_border};
                border-radius: 12px;
                background-color: {colors['surface']};
                margin-top: -1px;
            }}
            
            QTabBar::tab {{
                background-color: transparent;
                color: {text_muted};
                padding: 14px 36px;
                margin-right: 4px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-size: 14px;
                font-weight: 500;
                min-width: 100px;
            }}
            
            QTabBar::tab:selected {{
                background-color: {colors['surface']};
                color: {colors['primary']};
                font-weight: 600;
                border: {card_border};
                border-bottom: 2px solid {colors['surface']};
            }}
            
            QTabBar::tab:hover:!selected {{
                background-color: {colors['background_secondary']};
                color: {text_bright};
            }}
            
            /* List Widget - Modern with spacing */
            QListWidget {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 10px;
                outline: none;
                font-size: 13px;
                padding: 8px;
            }}
            
            QListWidget::item {{
                padding: 14px 16px;
                margin: 2px 4px;
                border-radius: 8px;
                color: {text_bright};
            }}
            
            QListWidget::item:selected {{
                background-color: {colors['primary']};
                color: white;
            }}
            
            QListWidget::item:hover:!selected {{
                background-color: {colors['background_secondary']};
            }}
            
            /* Text Edit (Log) */
            QTextEdit {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 10px;
                font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 12px;
                selection-background-color: {colors['primary']};
            }}
            
            /* Scroll Area */
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            
            QScrollBar:vertical {{
                background: transparent;
                width: 14px;
                margin: 4px 2px;
                border-radius: 7px;
            }}
            
            QScrollBar::handle:vertical {{
                background: {colors['border']};
                min-height: 40px;
                border-radius: 5px;
                margin: 0 3px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background: {text_muted};
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            
            /* Status Bar */
            QStatusBar {{
                background-color: {colors['surface']};
                color: {text_muted};
                border-top: {card_border};
                padding: 6px 12px;
                font-size: 12px;
            }}
            
            /* Menu - Modern dropdown */
            QMenu {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 10px;
                padding: 8px;
            }}
            
            QMenu::item {{
                padding: 10px 28px;
                border-radius: 6px;
                margin: 2px 4px;
            }}
            
            QMenu::item:selected {{
                background-color: {colors['primary']};
                color: white;
            }}
            
            /* Tooltips */
            QToolTip {{
                background-color: {colors['surface']};
                color: {text_bright};
                border: {card_border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            
            QMenu::separator {{
                height: 1px;
                background: {colors['border']};
                margin: 4px 8px;
            }}
            
            /* Tooltips */
            QToolTip {{
                background-color: {colors['surface']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 6px 10px;
            }}
        """
    
    @classmethod
    def get_colors(cls, mode: ThemeMode) -> dict:
        """Get color dictionary for the current theme"""
        if mode == ThemeMode.SYSTEM:
            return cls.DARK_COLORS if cls.is_system_dark_mode() else cls.LIGHT_COLORS
        elif mode == ThemeMode.DARK:
            return cls.DARK_COLORS
        else:
            return cls.LIGHT_COLORS


# ============================================================================
# Windows API for Window Enumeration
# ============================================================================

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
    
    @staticmethod
    def get_monitors() -> List[dict]:
        """Get list of monitors with names (individual monitors only, no 'All')"""
        monitors = []
        
        try:
            import mss
            with mss.mss() as sct:
                # Skip index 0 (combined monitor) - start from index 1
                for i, mon in enumerate(sct.monitors):
                    if i == 0:
                        continue  # Skip "All Monitors" combined view
                    monitors.append({
                        'index': i,  # Use 1-based indexing for individual monitors
                        'name': f"Monitor {i} ({mon['width']}x{mon['height']})",
                        'left': mon['left'],
                        'top': mon['top'],
                        'width': mon['width'],
                        'height': mon['height']
                    })
        except ImportError:
            # Fallback to user32 - only primary
            monitors.append({
                'index': 1,
                'name': f"Primary Monitor ({user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)})",
                'left': 0,
                'top': 0,
                'width': user32.GetSystemMetrics(0),
                'height': user32.GetSystemMetrics(1)
            })
        
        return monitors


# ============================================================================
# C++ Backend Process
# ============================================================================

class CppBackendProcess(QThread):
    """Manages the C++ backend process"""
    
    output_received = pyqtSignal(str)
    stats_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    process_started = pyqtSignal()
    process_stopped = pyqtSignal()
    
    def __init__(self, exe_path: str):
        super().__init__()
        self.exe_path = exe_path
        self.process = None
        self._running = False
        self.args = []
        
    def set_args(self, args: list):
        self.args = args
        
    def run(self):
        if not os.path.exists(self.exe_path):
            self.error_occurred.emit(f"Executable not found: {self.exe_path}")
            return
            
        self._running = True
        
        try:
            cmd = [self.exe_path] + self.args
            
            # Start process with proper encoding to avoid charmap errors
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            # Use unbuffered mode (bufsize=0) for immediate output
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,  # Unbuffered for immediate reads
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self.process_started.emit()
            
            # Read output line by line for reliable parsing
            # Use readline() which is more reliable for line-based output
            while self._running and self.process.poll() is None:
                try:
                    # Use readline for proper line buffering
                    line_bytes = self.process.stdout.readline()
                    if line_bytes:
                        # Handle carriage returns
                        line_bytes = line_bytes.replace(b'\r', b'').replace(b'\n', b'')
                        if line_bytes:
                            try:
                                line = line_bytes.decode('utf-8', errors='replace').strip()
                            except:
                                line = line_bytes.decode('latin-1', errors='replace').strip()
                            
                            if line:
                                self.output_received.emit(line)
                                self._parse_stats(line)
                    else:
                        time.sleep(0.01)  # Small sleep when no data
                except Exception as e:
                    self.error_occurred.emit(f"Read error: {e}")
                    break
                    
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.process_stopped.emit()
            
    def _parse_stats(self, line: str):
        """Parse stats from C++ output"""
        # C++ output format: "Capture: X fps | Encode: X fps | Stream: X fps | Clients: X | Bitrate: X Mbps | Quality: X"
        stats = {}
        
        # Parse capture FPS
        if match := re.search(r'Capture:\s*([\d.]+)', line):
            stats['capture_fps'] = float(match.group(1))
        
        # Parse encode FPS  
        if match := re.search(r'Encode:\s*([\d.]+)', line):
            stats['encode_fps'] = float(match.group(1))
            
        # Parse stream FPS
        if match := re.search(r'Stream:\s*([\d.]+)', line):
            stats['stream_fps'] = float(match.group(1))
            
        # Parse clients
        if match := re.search(r'Clients:\s*(\d+)', line):
            stats['clients'] = int(match.group(1))
            
        # Parse bitrate
        if match := re.search(r'Bitrate:\s*([\d.]+)', line):
            stats['bitrate'] = float(match.group(1))
            
        # Parse quality
        if match := re.search(r'Quality:\s*(\d+)', line):
            stats['quality'] = int(match.group(1))
            
        if stats:
            self.stats_updated.emit(stats)
    
    def stop(self):
        self._running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.wait(2000)


# ============================================================================
# Main Window
# ============================================================================

class MainWindow(QMainWindow):
    """Main application window for C++ backend GUI"""
    
    def __init__(self):
        super().__init__()
        
        # Settings storage
        self.settings = QSettings("VRStreamer", "VRScreenStreamer")
        
        # Theme
        self.theme_mode = ThemeMode(self.settings.value("theme_mode", ThemeMode.SYSTEM.value))
        
        # Find C++ executable
        self.exe_path = self._find_executable()
        
        # Settings
        self.port = int(self.settings.value("port", 8765))
        self.http_port = int(self.settings.value("http_port", 8080))
        self.quality = int(self.settings.value("quality", 75))
        self.fps = int(self.settings.value("fps", 60))
        self.scale = float(self.settings.value("scale", 0.85))
        self.monitor = 1  # Default to first monitor (1-indexed now)
        self.window_hwnd = None  # For window capture
        self.capture_mode = "monitor"  # "monitor" or "window"
        self.vr_enabled = self.settings.value("vr_enabled", True, type=bool)
        self.preset = self.settings.value("preset", "balanced")
        
        # GPU/Encoder options
        self.use_gpu = self.settings.value("use_gpu", True, type=bool)
        self.jpeg_library = self.settings.value("jpeg_library", "turbojpeg")
        
        # Window list
        self.windows: List[WindowInfo] = []
        self.monitors: List[dict] = []
        
        # Backend process
        self.backend = None
        self.is_streaming = False
        
        # Notifications
        self.notifications_enabled = True
        
        # Setup UI
        self.init_ui()
        
        # Setup system tray
        self.setup_system_tray()
        
        # Setup keyboard shortcuts
        self.setup_shortcuts()
        
        # Apply theme
        self.apply_theme(self.theme_mode)
        
        # Setup refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_sources)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
        
        # Initial refresh
        self.refresh_sources()
        
    def _find_executable(self) -> str:
        """Find the C++ executable"""
        base_dir = os.path.dirname(__file__)
        
        # Check common locations
        paths = [
            os.path.join(base_dir, 'build', 'Release', 'vr_streamer.exe'),
            os.path.join(base_dir, 'build', 'Debug', 'vr_streamer.exe'),
            os.path.join(base_dir, 'build', 'vr_streamer.exe'),
            os.path.join(base_dir, 'vr_streamer.exe'),
        ]
        
        for path in paths:
            if os.path.exists(path):
                return os.path.abspath(path)
                
        return os.path.join(base_dir, 'build', 'Release', 'vr_streamer.exe')
    
    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create a simple icon (green circle when streaming, gray when not)
        self.update_tray_icon()
        
        # Create tray menu
        tray_menu = QMenu()
        
        # Show/Hide action
        self.show_action = QAction("Show Window", self)
        self.show_action.triggered.connect(self.show_window)
        tray_menu.addAction(self.show_action)
        
        tray_menu.addSeparator()
        
        # Stream control
        self.tray_stream_action = QAction("▶ Start Streaming", self)
        self.tray_stream_action.triggered.connect(self.toggle_streaming)
        tray_menu.addAction(self.tray_stream_action)
        
        tray_menu.addSeparator()
        
        # Theme submenu
        theme_menu = QMenu("🎨 Theme", self)
        
        self.theme_system_action = QAction("System", self)
        self.theme_system_action.setCheckable(True)
        self.theme_system_action.triggered.connect(lambda: self.set_theme(ThemeMode.SYSTEM))
        theme_menu.addAction(self.theme_system_action)
        
        self.theme_dark_action = QAction("Dark", self)
        self.theme_dark_action.setCheckable(True)
        self.theme_dark_action.triggered.connect(lambda: self.set_theme(ThemeMode.DARK))
        theme_menu.addAction(self.theme_dark_action)
        
        self.theme_light_action = QAction("Light", self)
        self.theme_light_action.setCheckable(True)
        self.theme_light_action.triggered.connect(lambda: self.set_theme(ThemeMode.LIGHT))
        theme_menu.addAction(self.theme_light_action)
        
        tray_menu.addMenu(theme_menu)
        self.update_theme_menu()
        
        tray_menu.addSeparator()
        
        # Quit action
        quit_action = QAction("❌ Quit", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()
        
        # Set tooltip
        self.tray_icon.setToolTip("VR Screen Streamer - Not streaming")
    
    def update_tray_icon(self):
        """Update tray icon based on streaming state"""
        # Create a colored icon
        pixmap = QPixmap(32, 32)
        if self.is_streaming:
            pixmap.fill(QColor("#4CAF50"))  # Green when streaming
        else:
            pixmap.fill(QColor("#666666"))  # Gray when not
        
        self.tray_icon.setIcon(QIcon(pixmap))
    
    def update_theme_menu(self):
        """Update theme menu checkboxes"""
        self.theme_system_action.setChecked(self.theme_mode == ThemeMode.SYSTEM)
        self.theme_dark_action.setChecked(self.theme_mode == ThemeMode.DARK)
        self.theme_light_action.setChecked(self.theme_mode == ThemeMode.LIGHT)
    
    def tray_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()
    
    def show_window(self):
        """Show and activate the main window"""
        self.showNormal()
        self.activateWindow()
        self.raise_()
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Start/Stop streaming: Ctrl+Enter
        self.shortcut_stream = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_stream.activated.connect(self.toggle_streaming)
        
        # Refresh sources: F5
        self.shortcut_refresh = QShortcut(QKeySequence("F5"), self)
        self.shortcut_refresh.activated.connect(self.refresh_sources)
        
        # Toggle theme: Ctrl+T
        self.shortcut_theme = QShortcut(QKeySequence("Ctrl+T"), self)
        self.shortcut_theme.activated.connect(self.cycle_theme)
        
        # Minimize to tray: Ctrl+M
        self.shortcut_minimize = QShortcut(QKeySequence("Ctrl+M"), self)
        self.shortcut_minimize.activated.connect(self.hide)
        
        # Quit: Ctrl+Q
        self.shortcut_quit = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.shortcut_quit.activated.connect(self.quit_app)
    
    def cycle_theme(self):
        """Cycle through themes"""
        if self.theme_mode == ThemeMode.SYSTEM:
            self.set_theme(ThemeMode.DARK)
        elif self.theme_mode == ThemeMode.DARK:
            self.set_theme(ThemeMode.LIGHT)
        else:
            self.set_theme(ThemeMode.SYSTEM)
    
    def set_theme(self, mode: ThemeMode):
        """Set the theme mode"""
        self.theme_mode = mode
        self.settings.setValue("theme_mode", mode.value)
        self.apply_theme(mode)
        self.update_theme_menu()
        
        # Update theme combo in settings if it exists
        if hasattr(self, 'theme_combo'):
            self.theme_combo.blockSignals(True)
            index = {ThemeMode.SYSTEM: 0, ThemeMode.DARK: 1, ThemeMode.LIGHT: 2}[mode]
            self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(False)
    
    def apply_theme(self, mode: ThemeMode):
        """Apply the selected theme"""
        stylesheet = ThemeManager.get_stylesheet(mode)
        self.setStyleSheet(stylesheet)
        
        # Update status bar message
        theme_names = {ThemeMode.SYSTEM: "System", ThemeMode.DARK: "Dark", ThemeMode.LIGHT: "Light"}
        self.statusBar.showMessage(f"Theme: {theme_names[mode]}", 2000)
    
    def show_notification(self, title: str, message: str, icon=QSystemTrayIcon.Information):
        """Show a system tray notification"""
        if self.notifications_enabled and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, icon, 3000)
    
    def quit_app(self):
        """Properly quit the application"""
        self.stop_streaming()
        self.tray_icon.hide()
        QApplication.quit()
    
    def closeEvent(self, event):
        """Handle window close - minimize to tray instead"""
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "VR Screen Streamer",
                "Application minimized to tray. Right-click for options.",
                QSystemTrayIcon.Information,
                2000
            )
            event.ignore()
        else:
            self.stop_streaming()
            event.accept()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("VR Screen Streamer (C++ High-Performance)")
        self.setMinimumSize(600, 750)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("VR Screen Streamer")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("High-Performance C++ Edition")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(subtitle)
        
        # Create tabs
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Tab 1: Capture & Stream
        stream_tab = QWidget()
        tabs.addTab(stream_tab, "Stream")
        self.setup_stream_tab(stream_tab)
        
        # Tab 2: Settings
        settings_tab = QWidget()
        tabs.addTab(settings_tab, "Settings")
        self.setup_settings_tab(settings_tab)
        
        # Tab 3: Connection
        connection_tab = QWidget()
        tabs.addTab(connection_tab, "Connection")
        self.setup_connection_tab(connection_tab)
        
        # Tab 4: Output Log
        log_tab = QWidget()
        tabs.addTab(log_tab, "Log")
        self.setup_log_tab(log_tab)
        
        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Check executable
        if os.path.exists(self.exe_path):
            self.statusBar.showMessage(f"Ready - Backend: {os.path.basename(self.exe_path)}")
        else:
            self.statusBar.showMessage("⚠️ C++ backend not found! Run build.bat first.")
            self.statusBar.setStyleSheet("color: red;")
            
    def setup_stream_tab(self, parent):
        """Setup the streaming tab - sources bigger, statistics at bottom"""
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)
        
        # Capture Source Selection - takes most space (stretch=3)
        source_group = QGroupBox("📺 Capture Source")
        source_layout = QVBoxLayout(source_group)
        source_layout.setContentsMargins(12, 20, 12, 12)
        
        # Header row with refresh button
        header_row = QHBoxLayout()
        self.selected_label = QLabel("Selected: Monitor 1 (default)")
        self.selected_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        header_row.addWidget(self.selected_label)
        header_row.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_sources)
        refresh_btn.setToolTip("Refresh the list of available capture sources")
        header_row.addWidget(refresh_btn)
        source_layout.addLayout(header_row)
        
        # Source list (monitors + windows) - grows to fill space
        self.source_list = QListWidget()
        self.source_list.setMinimumHeight(250)
        # Connect multiple signals to catch all selection methods
        self.source_list.itemClicked.connect(self.on_source_selected)
        self.source_list.itemDoubleClicked.connect(self.on_source_selected)
        self.source_list.currentItemChanged.connect(self.on_source_current_changed)
        self.source_list.itemSelectionChanged.connect(self.on_item_selection_changed)
        source_layout.addWidget(self.source_list, 1)  # Stretch factor
        
        layout.addWidget(source_group, 3)  # Stretch factor 3 - takes most space
        
        # Stream Control - compact, fixed height
        control_group = QGroupBox("🎬 Stream Control")
        control_layout = QVBoxLayout(control_group)
        control_layout.setContentsMargins(12, 20, 12, 12)
        
        # Start/Stop button
        self.stream_btn = QPushButton("▶ Start Streaming")
        self.stream_btn.setFont(QFont("Arial", 14, QFont.Bold))
        self.stream_btn.setMinimumHeight(50)
        self.stream_btn.clicked.connect(self.toggle_streaming)
        self.stream_btn.setProperty("primary", True)
        self.stream_btn.setToolTip("Start or stop the VR stream (Ctrl+Enter)")
        control_layout.addWidget(self.stream_btn)
        
        layout.addWidget(control_group, 0)  # No stretch - fixed size
        
        # Stats Display - at bottom, compact horizontal layout
        stats_group = QGroupBox("📊 Statistics")
        stats_layout = QHBoxLayout(stats_group)
        stats_layout.setContentsMargins(12, 20, 12, 12)
        stats_layout.setSpacing(20)
        
        self.stat_labels = {}
        stat_items = [
            ('capture_fps', '🎥 Capture'),
            ('encode_fps', '⚙ Encode'),
            ('stream_fps', '📡 Stream'),
            ('clients', '👥 Clients'),
            ('quality', '✨ Quality'),
            ('bitrate', '📊 Bitrate'),
        ]
        
        for key, label in stat_items:
            stat_frame = QVBoxLayout()
            stat_frame.setSpacing(2)
            
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 11px; color: #888;")
            stat_frame.addWidget(lbl)
            
            val = QLabel("--")
            val.setAlignment(Qt.AlignCenter)
            val.setFont(QFont("Courier", 12, QFont.Bold))
            stat_frame.addWidget(val)
            
            stats_layout.addLayout(stat_frame)
            self.stat_labels[key] = val
        
        # Backend info at the end
        stats_layout.addStretch()
        backend_frame = QVBoxLayout()
        backend_label = QLabel("🔧 Backend")
        backend_label.setAlignment(Qt.AlignCenter)
        backend_label.setStyleSheet("font-size: 11px; color: #888;")
        backend_frame.addWidget(backend_label)
        
        backend_val = QLabel("C++ (TurboJPEG)")
        backend_val.setAlignment(Qt.AlignCenter)
        backend_val.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 12px;")
        backend_frame.addWidget(backend_val)
        stats_layout.addLayout(backend_frame)
        self.stat_labels['backend'] = backend_val
        
        layout.addWidget(stats_group, 0)  # No stretch - fixed at bottom
        
    def setup_settings_tab(self, parent):
        """Setup the settings tab with tooltips and theme options"""
        # Make scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        
        # Appearance Settings (Theme)
        appearance_group = QGroupBox("🎨 Appearance")
        appearance_layout = QGridLayout(appearance_group)
        appearance_layout.setContentsMargins(16, 24, 16, 16)
        appearance_layout.setHorizontalSpacing(16)
        
        theme_label = QLabel("Theme:")
        theme_label.setToolTip("Choose the application color theme")
        appearance_layout.addWidget(theme_label, 0, 0)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(['System', 'Dark', 'Light'])
        self.theme_combo.setCurrentIndex({ThemeMode.SYSTEM: 0, ThemeMode.DARK: 1, ThemeMode.LIGHT: 2}[self.theme_mode])
        self.theme_combo.currentIndexChanged.connect(self.on_theme_combo_changed)
        self.theme_combo.setToolTip("System: Follow Windows theme\nDark: Always use dark mode\nLight: Always use light mode")
        appearance_layout.addWidget(self.theme_combo, 0, 1)
        
        # Notifications toggle
        notif_label = QLabel("Notifications:")
        notif_label.setToolTip("Show system notifications for events")
        appearance_layout.addWidget(notif_label, 1, 0)
        
        self.notifications_checkbox = QCheckBox("Enable notifications")
        self.notifications_checkbox.setChecked(self.notifications_enabled)
        self.notifications_checkbox.stateChanged.connect(lambda s: setattr(self, 'notifications_enabled', s == Qt.Checked))
        self.notifications_checkbox.setToolTip("Show notifications when streaming starts/stops or clients connect")
        appearance_layout.addWidget(self.notifications_checkbox, 1, 1)
        
        layout.addWidget(appearance_group)
        
        # Quality Preset
        preset_group = QGroupBox("📊 Quality Preset")
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.setContentsMargins(16, 24, 16, 16)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            'ultra_performance', 'low_latency', 'balanced', 'quality', 'maximum_quality'
        ])
        self.preset_combo.setCurrentText(self.preset)
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        self.preset_combo.setToolTip(
            "Quick presets to balance quality and performance:\n"
            "• Ultra Performance: Lowest latency, lower quality\n"
            "• Low Latency: Fast streaming, good quality\n"
            "• Balanced: Recommended for most users\n"
            "• Quality: Higher quality, more bandwidth\n"
            "• Maximum Quality: Best quality, highest bandwidth"
        )
        preset_layout.addWidget(self.preset_combo)
        
        layout.addWidget(preset_group)
        
        # Video Quality
        quality_group = QGroupBox("🎬 Video Quality")
        quality_layout = QGridLayout(quality_group)
        quality_layout.setContentsMargins(16, 24, 16, 16)
        quality_layout.setHorizontalSpacing(16)
        
        # JPEG Quality slider
        jpeg_label = QLabel("JPEG Quality:")
        jpeg_label.setToolTip("Higher values = better quality but larger file size (20-100)")
        quality_layout.addWidget(jpeg_label, 0, 0)
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(20, 100)
        self.quality_slider.setValue(self.quality)
        self.quality_slider.valueChanged.connect(self.on_quality_changed)
        self.quality_slider.setToolTip("JPEG compression quality (20=lowest, 100=highest)")
        quality_layout.addWidget(self.quality_slider, 0, 1)
        self.quality_label = QLabel(str(self.quality))
        quality_layout.addWidget(self.quality_label, 0, 2)
        
        # Target FPS
        fps_label = QLabel("Target FPS:")
        fps_label.setToolTip("Maximum frames per second to stream (15-120)")
        quality_layout.addWidget(fps_label, 1, 0)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(15, 120)
        self.fps_spin.setValue(self.fps)
        self.fps_spin.valueChanged.connect(lambda v: setattr(self, 'fps', v))
        self.fps_spin.setToolTip("Higher FPS = smoother video but more CPU/bandwidth")
        quality_layout.addWidget(self.fps_spin, 1, 1)
        
        # Downscale factor
        scale_label = QLabel("Downscale:")
        scale_label.setToolTip("Reduce resolution to improve performance")
        quality_layout.addWidget(scale_label, 2, 0)
        self.downscale_slider = QSlider(Qt.Horizontal)
        self.downscale_slider.setRange(30, 100)
        self.downscale_slider.setValue(int(self.scale * 100))
        self.downscale_slider.valueChanged.connect(self.on_downscale_changed)
        self.downscale_slider.setToolTip("100% = Full resolution, 50% = Half resolution")
        quality_layout.addWidget(self.downscale_slider, 2, 1)
        self.downscale_label = QLabel(f"{self.scale:.0%}")
        quality_layout.addWidget(self.downscale_label, 2, 2)
        
        layout.addWidget(quality_group)
        
        # VR Settings
        vr_group = QGroupBox("🥽 VR Settings")
        vr_layout = QVBoxLayout(vr_group)
        vr_layout.setContentsMargins(16, 24, 16, 16)
        
        self.vr_checkbox = QCheckBox("Enable VR Mode (Side-by-Side)")
        self.vr_checkbox.setChecked(self.vr_enabled)
        self.vr_checkbox.stateChanged.connect(lambda s: setattr(self, 'vr_enabled', s == Qt.Checked))
        self.vr_checkbox.setToolTip("Duplicate the image side-by-side for VR headset viewing")
        vr_layout.addWidget(self.vr_checkbox)
        
        layout.addWidget(vr_group)
        
        # GPU Acceleration Settings
        gpu_group = QGroupBox("🚀 GPU Acceleration")
        gpu_layout = QVBoxLayout(gpu_group)
        gpu_layout.setContentsMargins(16, 24, 16, 16)
        
        self.gpu_checkbox = QCheckBox("Enable GPU Acceleration")
        self.gpu_checkbox.setChecked(self.use_gpu)
        self.gpu_checkbox.stateChanged.connect(self.on_gpu_toggled)
        self.gpu_checkbox.setToolTip("Use GPU for faster encoding when available")
        gpu_layout.addWidget(self.gpu_checkbox)
        
        # JPEG Library selection
        jpeg_layout = QHBoxLayout()
        jpeg_lib_label = QLabel("JPEG Library:")
        jpeg_lib_label.setToolTip("Select the JPEG encoding library")
        jpeg_layout.addWidget(jpeg_lib_label)
        self.jpeg_combo = QComboBox()
        self.jpeg_combo.addItems(['TurboJPEG (CPU)', 'nvJPEG (GPU/CUDA)'])
        self.jpeg_combo.setCurrentIndex(0 if self.jpeg_library == "turbojpeg" else 1)
        self.jpeg_combo.currentIndexChanged.connect(self.on_jpeg_library_changed)
        self.jpeg_combo.setToolTip(
            "TurboJPEG: Fast CPU-based encoding, works on all systems\n"
            "nvJPEG: GPU-accelerated encoding, requires NVIDIA GPU with CUDA"
        )
        jpeg_layout.addWidget(self.jpeg_combo)
        gpu_layout.addLayout(jpeg_layout)
        
        # GPU status note
        gpu_note = QLabel("💡 nvJPEG requires NVIDIA GPU with CUDA support")
        gpu_note.setProperty("subtitle", True)
        gpu_layout.addWidget(gpu_note)
        
        layout.addWidget(gpu_group)
        
        # Network Settings
        network_group = QGroupBox("🌐 Network")
        network_layout = QGridLayout(network_group)
        network_layout.setContentsMargins(16, 24, 16, 16)
        network_layout.setHorizontalSpacing(16)
        
        ws_port_label = QLabel("WebSocket Port:")
        ws_port_label.setToolTip("Port for the streaming WebSocket server")
        network_layout.addWidget(ws_port_label, 0, 0)
        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1024, 65535)
        self.ws_port_spin.setValue(self.port)
        self.ws_port_spin.valueChanged.connect(lambda v: setattr(self, 'port', v))
        self.ws_port_spin.setToolTip("Default: 8765. Change if there's a port conflict.")
        network_layout.addWidget(self.ws_port_spin, 0, 1)
        
        layout.addWidget(network_group)
        
        # Keyboard Shortcuts Info
        shortcuts_group = QGroupBox("⌨️ Keyboard Shortcuts")
        shortcuts_layout = QVBoxLayout(shortcuts_group)
        shortcuts_layout.setContentsMargins(16, 24, 16, 16)
        
        shortcuts_info = QLabel(
            "<b>Ctrl+Enter</b> - Start/Stop streaming<br>"
            "<b>F5</b> - Refresh sources<br>"
            "<b>Ctrl+T</b> - Cycle theme<br>"
            "<b>Ctrl+M</b> - Minimize to tray<br>"
            "<b>Ctrl+Q</b> - Quit application"
        )
        shortcuts_info.setWordWrap(True)
        shortcuts_layout.addWidget(shortcuts_info)
        
        layout.addWidget(shortcuts_group)
        
        layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        parent_layout = QVBoxLayout(parent)
        parent_layout.addWidget(scroll)
        
    def setup_connection_tab(self, parent):
        """Setup the connection tab"""
        layout = QVBoxLayout(parent)
        layout.setSpacing(16)
        
        # Server Info
        server_group = QGroupBox("🖥️ Server Information")
        server_layout = QGridLayout(server_group)
        server_layout.setContentsMargins(20, 28, 20, 20)
        server_layout.setHorizontalSpacing(20)
        server_layout.setVerticalSpacing(12)
        
        server_layout.addWidget(QLabel("WebSocket Port:"), 0, 0)
        self.ws_port_label = QLabel(str(self.port))
        self.ws_port_label.setFont(QFont("Cascadia Code", 12))
        self.ws_port_label.setStyleSheet("font-weight: 600;")
        server_layout.addWidget(self.ws_port_label, 0, 1)
        
        # Connection URL will be shown when streaming
        server_layout.addWidget(QLabel("Status:"), 1, 0)
        self.connection_status = QLabel("Not streaming")
        self.connection_status.setStyleSheet("font-weight: 500;")
        server_layout.addWidget(self.connection_status, 1, 1)
        
        layout.addWidget(server_group)
        
        # Mobile App URL
        mobile_group = QGroupBox("📱 Mobile App Access")
        mobile_layout = QVBoxLayout(mobile_group)
        mobile_layout.setContentsMargins(20, 28, 20, 20)
        mobile_layout.setSpacing(16)
        
        self.mobile_info = QLabel("Start streaming to see connection info")
        self.mobile_info.setAlignment(Qt.AlignCenter)
        self.mobile_info.setStyleSheet("font-size: 14px; padding: 16px;")
        mobile_layout.addWidget(self.mobile_info)
        
        if HAS_QRCODE:
            self.qr_label = QLabel()
            self.qr_label.setAlignment(Qt.AlignCenter)
            self.qr_label.setMinimumSize(200, 200)
            mobile_layout.addWidget(self.qr_label)
        
        layout.addWidget(mobile_group)
        layout.addStretch()
        
    def setup_log_tab(self, parent):
        """Setup the log output tab"""
        layout = QVBoxLayout(parent)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.log_text)
        
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.log_text.clear)
        layout.addWidget(clear_btn)
    
    def refresh_sources(self):
        """Refresh the list of capture sources (monitors and windows)"""
        # Remember current selection
        current_hwnd = self.window_hwnd
        current_mode = self.capture_mode
        current_monitor = self.monitor
        
        # Block signals temporarily to avoid spurious callbacks during refresh
        self.source_list.blockSignals(True)
        self.source_list.clear()
        
        # Get monitors (individual only, no "All Monitors")
        self.monitors = WindowEnumerator.get_monitors()
        
        # Add monitors header
        header_item = QListWidgetItem("━━━ Monitors ━━━")
        header_item.setFlags(Qt.NoItemFlags)  # Not selectable
        header_item.setForeground(QBrush(QColor(128, 128, 128)))
        self.source_list.addItem(header_item)
        
        # Track if we restored selection
        selection_restored = False
        first_monitor_item = None
        
        # Add monitors
        for mon in self.monitors:
            item = QListWidgetItem(f"📺 {mon['name']}")
            item.setData(Qt.UserRole, ('monitor', mon['index']))
            self.source_list.addItem(item)
            
            # Track first monitor for default selection
            if first_monitor_item is None:
                first_monitor_item = item
            
            # Re-select if this was the previously selected monitor
            if current_mode == 'monitor' and current_monitor == mon['index']:
                item.setSelected(True)
                self.source_list.setCurrentItem(item)
                selection_restored = True
        
        # Get windows
        self.windows = WindowEnumerator.enumerate_windows()
        
        # Add windows header
        header_item = QListWidgetItem("━━━ Windows ━━━")
        header_item.setFlags(Qt.NoItemFlags)  # Not selectable
        header_item.setForeground(QBrush(QColor(128, 128, 128)))
        self.source_list.addItem(header_item)
        
        # Add windows
        for win in self.windows:
            # Truncate long titles
            title = win.title if len(win.title) <= 50 else win.title[:47] + "..."
            item = QListWidgetItem(f"🪟 {title} ({win.width}x{win.height})")
            item.setData(Qt.UserRole, ('window', win.hwnd))
            item.setToolTip(win.title)  # Full title on hover
            self.source_list.addItem(item)
            # Re-select if this was the previously selected window
            if current_mode == 'window' and current_hwnd == win.hwnd:
                item.setSelected(True)
                self.source_list.setCurrentItem(item)
                selection_restored = True
        
        # If no selection was restored and we have monitors, select the first one
        if not selection_restored and first_monitor_item is not None:
            first_monitor_item.setSelected(True)
            self.source_list.setCurrentItem(first_monitor_item)
            # Also update the internal state
            data = first_monitor_item.data(Qt.UserRole)
            if data:
                self.capture_mode = 'monitor'
                self.monitor = data[1]
                self.window_hwnd = None
                mon = next((m for m in self.monitors if m['index'] == self.monitor), None)
                if mon:
                    self.selected_label.setText(f"Selected: {mon['name']}")
        
        # Re-enable signals
        self.source_list.blockSignals(False)
    
    def on_source_selected(self, item: QListWidgetItem):
        """Handle source selection"""
        data = item.data(Qt.UserRole)
        if data is None:
            return  # Header item
        
        source_type, source_id = data
        
        if source_type == 'monitor':
            self.capture_mode = 'monitor'
            self.monitor = source_id
            self.window_hwnd = None
            # Find monitor name
            mon = next((m for m in self.monitors if m['index'] == source_id), None)
            name = mon['name'] if mon else f"Monitor {source_id}"
            self.selected_label.setText(f"Selected: {name}")
        else:
            self.capture_mode = 'window'
            self.window_hwnd = source_id
            # Find window info
            win = next((w for w in self.windows if w.hwnd == source_id), None)
            if win:
                title = win.title if len(win.title) <= 40 else win.title[:37] + "..."
                self.selected_label.setText(f"Selected: {title}")
            else:
                self.selected_label.setText(f"Selected: Window {source_id}")
    
    def on_source_current_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle selection change via keyboard or other means"""
        if current is not None:
            self.on_source_selected(current)
    
    def on_item_selection_changed(self):
        """Handle when the selection changes"""
        selected_items = self.source_list.selectedItems()
        if selected_items:
            self.on_source_selected(selected_items[0])
    
    def on_theme_combo_changed(self, index: int):
        """Handle theme combo box change"""
        modes = [ThemeMode.SYSTEM, ThemeMode.DARK, ThemeMode.LIGHT]
        self.set_theme(modes[index])
                
    def on_preset_changed(self, preset: str):
        self.preset = preset
        self.settings.setValue("preset", preset)
        presets = {
            'ultra_performance': (40, 0.5),
            'low_latency': (55, 0.65),
            'balanced': (75, 0.85),
            'quality': (85, 1.0),
            'maximum_quality': (95, 1.0),
        }
        if preset in presets:
            q, s = presets[preset]
            self.quality = q
            self.scale = s
            self.quality_slider.setValue(q)
            self.downscale_slider.setValue(int(s * 100))
            
    def on_quality_changed(self, value: int):
        self.quality = value
        self.quality_label.setText(str(value))
        self.settings.setValue("quality", value)
        
    def on_downscale_changed(self, value: int):
        self.scale = value / 100.0
        self.downscale_label.setText(f"{self.scale:.0%}")
        self.settings.setValue("scale", self.scale)
        
    def on_gpu_toggled(self, state: int):
        self.use_gpu = (state == Qt.Checked)
        self.settings.setValue("use_gpu", self.use_gpu)
        # Update backend label
        if self.use_gpu and self.jpeg_library == "nvjpeg":
            self.stat_labels['backend'].setText("C++ (nvJPEG/GPU)")
        else:
            self.stat_labels['backend'].setText("C++ (TurboJPEG)")
            
    def on_jpeg_library_changed(self, index: int):
        self.jpeg_library = "turbojpeg" if index == 0 else "nvjpeg"
        self.settings.setValue("jpeg_library", self.jpeg_library)
        # Update backend label
        if self.use_gpu and self.jpeg_library == "nvjpeg":
            self.stat_labels['backend'].setText("C++ (nvJPEG/GPU)")
        else:
            self.stat_labels['backend'].setText("C++ (TurboJPEG)")
        
    def toggle_streaming(self):
        if self.is_streaming:
            self.stop_streaming()
        else:
            self.start_streaming()
            
    def start_streaming(self):
        if not os.path.exists(self.exe_path):
            QMessageBox.critical(self, "Error", f"C++ backend not found!\n{self.exe_path}\n\nRun build.bat first.")
            return
        
        # Double-check current selection from list widget (safety check)
        current_item = self.source_list.currentItem()
        if current_item is not None:
            data = current_item.data(Qt.UserRole)
            if data is not None:
                source_type, source_id = data
                if source_type == 'window':
                    self.capture_mode = 'window'
                    self.window_hwnd = source_id
                else:
                    self.capture_mode = 'monitor'
                    self.monitor = source_id
                    self.window_hwnd = None
            
        # Build args
        args = [
            '-p', str(self.port),
            '-q', str(self.quality),
            '-f', str(self.fps),
            '-s', str(self.scale),
            '--preset', self.preset,
        ]
        
        # Add capture source
        if self.capture_mode == 'window' and self.window_hwnd:
            # Window capture via handle
            args.extend(['--hwnd', str(self.window_hwnd)])
            capture_desc = f"window HWND={self.window_hwnd}"
        else:
            # Monitor capture - subtract 1 since mss uses 1-indexed but C++ uses 0-indexed
            args.extend(['-m', str(self.monitor - 1)])
            capture_desc = f"monitor {self.monitor}"
        
        # Log to UI
        self.log_text.append(f"Starting stream with capture: {capture_desc}")
        self.log_text.append(f"Command args: {' '.join(args)}")
        
        if not self.vr_enabled:
            args.append('--no-vr')
            
        if not self.use_gpu:
            args.append('--no-gpu')
            
        # Create backend process
        self.backend = CppBackendProcess(self.exe_path)
        self.backend.set_args(args)
        self.backend.output_received.connect(self.on_backend_output)
        self.backend.stats_updated.connect(self.on_stats_update)
        self.backend.error_occurred.connect(self.on_backend_error)
        self.backend.process_started.connect(self.on_backend_started)
        self.backend.process_stopped.connect(self.on_backend_stopped)
        self.backend.start()
        
        self.is_streaming = True
        self.stream_btn.setText("⏹ Stop Streaming")
        self.stream_btn.setProperty("danger", True)
        self.stream_btn.style().unpolish(self.stream_btn)
        self.stream_btn.style().polish(self.stream_btn)
        
        # Update tray
        self.update_tray_icon()
        self.tray_stream_action.setText("⏹ Stop Streaming")
        self.tray_icon.setToolTip(f"VR Screen Streamer - Streaming on port {self.port}")
        
    def stop_streaming(self):
        if self.backend:
            self.backend.stop()
            self.backend = None
            
        self.is_streaming = False
        self.stream_btn.setText("▶ Start Streaming")
        self.stream_btn.setProperty("danger", False)
        self.stream_btn.setProperty("primary", True)
        self.stream_btn.style().unpolish(self.stream_btn)
        self.stream_btn.style().polish(self.stream_btn)
        
        self.connection_status.setText("Not streaming")
        
        # Update tray
        self.update_tray_icon()
        self.tray_stream_action.setText("▶ Start Streaming")
        self.tray_icon.setToolTip("VR Screen Streamer - Not streaming")
        
        self.show_notification("Streaming Stopped", "VR Screen Streamer has stopped streaming.")
        
    def on_backend_output(self, line: str):
        self.log_text.append(line)
        # Auto-scroll
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def on_stats_update(self, stats: dict):
        if 'capture_fps' in stats:
            self.stat_labels['capture_fps'].setText(f"{stats['capture_fps']:.1f}")
        if 'encode_fps' in stats:
            self.stat_labels['encode_fps'].setText(f"{stats['encode_fps']:.1f}")
        if 'stream_fps' in stats:
            self.stat_labels['stream_fps'].setText(f"{stats['stream_fps']:.1f}")
        if 'quality' in stats:
            self.stat_labels['quality'].setText(str(stats['quality']))
        if 'clients' in stats:
            clients = stats['clients']
            self.stat_labels['clients'].setText(str(clients))
            # Update tray tooltip with client count
            self.tray_icon.setToolTip(f"VR Screen Streamer - {clients} client(s) connected")
        if 'bitrate' in stats:
            self.stat_labels['bitrate'].setText(f"{stats['bitrate']:.2f} Mbps")
            
    def on_backend_error(self, error: str):
        self.log_text.append(f"ERROR: {error}")
        self.statusBar.showMessage(f"Error: {error}")
        self.show_notification("Error", error, QSystemTrayIcon.Critical)
        
    def on_backend_started(self):
        import socket
        hostname = socket.gethostname()
        try:
            ip = socket.gethostbyname(hostname)
        except:
            ip = "127.0.0.1"
            
        self.connection_status.setText(f"Streaming on ws://{ip}:{self.port}")
        self.mobile_info.setText(f"Open http://{ip}:{self.http_port} on your phone")
        self.statusBar.showMessage(f"Streaming on port {self.port}")
        
        # Show notification
        self.show_notification(
            "Streaming Started", 
            f"VR Screen Streamer is now streaming on port {self.port}\nOpen http://{ip}:{self.http_port} on your phone"
        )
        
        # Generate QR code
        if HAS_QRCODE:
            url = f"http://{ip}:{self.http_port}"
            qr = qrcode.make(url)
            qr = qr.convert('RGB')
            qr = qr.resize((200, 200))
            
            # Convert to QPixmap
            from io import BytesIO
            buffer = BytesIO()
            qr.save(buffer, format='PNG')
            buffer.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            self.qr_label.setPixmap(pixmap)
            
    def on_backend_stopped(self):
        self.statusBar.showMessage("Streaming stopped")


def main():
    app = QApplication(sys.argv)
    
    # Set application metadata
    app.setApplicationName("VR Screen Streamer")
    app.setOrganizationName("VRStreamer")
    app.setApplicationVersion("2.0.0")
    
    # Set style to Fusion for consistent look across platforms
    app.setStyle('Fusion')
    
    # Enable high DPI scaling
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
