"""
VR Screen Streamer - Python GUI Launcher for C++ Backend
Uses the PyQt5 GUI from pc_app to control the high-performance C++ backend.
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

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider, QGroupBox, QGridLayout,
    QSpinBox, QCheckBox, QFrame, QListWidget, QListWidgetItem,
    QStatusBar, QMessageBox, QTabWidget, QTextEdit, QSizePolicy, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QProcess
from PyQt5.QtGui import QFont, QPixmap, QBrush, QColor

try:
    import qrcode
    from PIL import Image
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


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
        
        # Find C++ executable
        self.exe_path = self._find_executable()
        
        # Settings
        self.port = 8765
        self.http_port = 8080
        self.quality = 75
        self.fps = 60
        self.scale = 0.85
        self.monitor = 1  # Default to first monitor (1-indexed now)
        self.window_hwnd = None  # For window capture
        self.capture_mode = "monitor"  # "monitor" or "window"
        self.vr_enabled = True
        self.preset = "balanced"
        
        # GPU/Encoder options
        self.use_gpu = True
        self.jpeg_library = "turbojpeg"  # "turbojpeg" or "nvjpeg"
        
        # Window list
        self.windows: List[WindowInfo] = []
        self.monitors: List[dict] = []
        
        # Backend process
        self.backend = None
        self.is_streaming = False
        
        # Setup UI
        self.init_ui()
        
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
        """Setup the streaming tab"""
        layout = QVBoxLayout(parent)
        
        # Capture Source Selection
        source_group = QGroupBox("Capture Source")
        source_layout = QVBoxLayout(source_group)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Sources")
        refresh_btn.clicked.connect(self.refresh_sources)
        source_layout.addWidget(refresh_btn)
        
        # Source list (monitors + windows)
        self.source_list = QListWidget()
        self.source_list.setMinimumHeight(200)
        # Connect multiple signals to catch all selection methods
        self.source_list.itemClicked.connect(self.on_source_selected)
        self.source_list.itemDoubleClicked.connect(self.on_source_selected)
        self.source_list.currentItemChanged.connect(self.on_source_current_changed)
        self.source_list.itemSelectionChanged.connect(self.on_item_selection_changed)
        source_layout.addWidget(self.source_list)
        
        # Currently selected
        self.selected_label = QLabel("Selected: Monitor 1 (default)")
        self.selected_label.setStyleSheet("font-weight: bold;")
        source_layout.addWidget(self.selected_label)
        
        layout.addWidget(source_group)
        
        # Stream Control
        control_group = QGroupBox("Stream Control")
        control_layout = QVBoxLayout(control_group)
        
        # Start/Stop button
        self.stream_btn = QPushButton("▶ Start Streaming")
        self.stream_btn.setFont(QFont("Arial", 14, QFont.Bold))
        self.stream_btn.setMinimumHeight(50)
        self.stream_btn.clicked.connect(self.toggle_streaming)
        self.stream_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        control_layout.addWidget(self.stream_btn)
        
        layout.addWidget(control_group)
        
        # Stats Display
        stats_group = QGroupBox("Statistics")
        stats_layout = QGridLayout(stats_group)
        
        self.stat_labels = {}
        stat_items = [
            ('capture_fps', 'Capture FPS:'),
            ('encode_fps', 'Encode FPS:'),
            ('stream_fps', 'Stream FPS:'),
            ('clients', 'Connected Clients:'),
            ('quality', 'Current Quality:'),
            ('bitrate', 'Bitrate:'),
            ('backend', 'Backend:'),
        ]
        
        for i, (key, label) in enumerate(stat_items):
            lbl = QLabel(label)
            val = QLabel("--")
            val.setFont(QFont("Courier", 10))
            stats_layout.addWidget(lbl, i, 0)
            stats_layout.addWidget(val, i, 1)
            self.stat_labels[key] = val
        
        self.stat_labels['backend'].setText("C++ (TurboJPEG)")
        self.stat_labels['backend'].setStyleSheet("color: #4CAF50; font-weight: bold;")
        
        layout.addWidget(stats_group)
        layout.addStretch()
        
    def setup_settings_tab(self, parent):
        """Setup the settings tab"""
        # Make scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        
        # Quality Preset
        preset_group = QGroupBox("Quality Preset")
        preset_layout = QVBoxLayout(preset_group)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            'ultra_performance', 'low_latency', 'balanced', 'quality', 'maximum_quality'
        ])
        self.preset_combo.setCurrentText(self.preset)
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        
        layout.addWidget(preset_group)
        
        # Video Quality
        quality_group = QGroupBox("Video Quality")
        quality_layout = QGridLayout(quality_group)
        
        # JPEG Quality slider
        quality_layout.addWidget(QLabel("JPEG Quality:"), 0, 0)
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(20, 100)
        self.quality_slider.setValue(self.quality)
        self.quality_slider.valueChanged.connect(self.on_quality_changed)
        quality_layout.addWidget(self.quality_slider, 0, 1)
        self.quality_label = QLabel(str(self.quality))
        quality_layout.addWidget(self.quality_label, 0, 2)
        
        # Target FPS
        quality_layout.addWidget(QLabel("Target FPS:"), 1, 0)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(15, 120)
        self.fps_spin.setValue(self.fps)
        self.fps_spin.valueChanged.connect(lambda v: setattr(self, 'fps', v))
        quality_layout.addWidget(self.fps_spin, 1, 1)
        
        # Downscale factor
        quality_layout.addWidget(QLabel("Downscale:"), 2, 0)
        self.downscale_slider = QSlider(Qt.Horizontal)
        self.downscale_slider.setRange(30, 100)
        self.downscale_slider.setValue(int(self.scale * 100))
        self.downscale_slider.valueChanged.connect(self.on_downscale_changed)
        quality_layout.addWidget(self.downscale_slider, 2, 1)
        self.downscale_label = QLabel(f"{self.scale:.0%}")
        quality_layout.addWidget(self.downscale_label, 2, 2)
        
        layout.addWidget(quality_group)
        
        # VR Settings
        vr_group = QGroupBox("VR Settings")
        vr_layout = QVBoxLayout(vr_group)
        
        self.vr_checkbox = QCheckBox("Enable VR Mode (Side-by-Side)")
        self.vr_checkbox.setChecked(self.vr_enabled)
        self.vr_checkbox.stateChanged.connect(lambda s: setattr(self, 'vr_enabled', s == Qt.Checked))
        vr_layout.addWidget(self.vr_checkbox)
        
        layout.addWidget(vr_group)
        
        # GPU Acceleration Settings
        gpu_group = QGroupBox("GPU Acceleration")
        gpu_layout = QVBoxLayout(gpu_group)
        
        self.gpu_checkbox = QCheckBox("Enable GPU Acceleration")
        self.gpu_checkbox.setChecked(self.use_gpu)
        self.gpu_checkbox.stateChanged.connect(self.on_gpu_toggled)
        gpu_layout.addWidget(self.gpu_checkbox)
        
        # JPEG Library selection
        jpeg_layout = QHBoxLayout()
        jpeg_layout.addWidget(QLabel("JPEG Library:"))
        self.jpeg_combo = QComboBox()
        self.jpeg_combo.addItems(['TurboJPEG (CPU)', 'nvJPEG (GPU/CUDA)'])
        self.jpeg_combo.setCurrentIndex(0 if self.jpeg_library == "turbojpeg" else 1)
        self.jpeg_combo.currentIndexChanged.connect(self.on_jpeg_library_changed)
        jpeg_layout.addWidget(self.jpeg_combo)
        gpu_layout.addLayout(jpeg_layout)
        
        # GPU status note
        gpu_note = QLabel("Note: nvJPEG requires NVIDIA GPU with CUDA support")
        gpu_note.setStyleSheet("color: gray; font-size: 10px;")
        gpu_layout.addWidget(gpu_note)
        
        layout.addWidget(gpu_group)
        
        # Network Settings
        network_group = QGroupBox("Network")
        network_layout = QGridLayout(network_group)
        
        network_layout.addWidget(QLabel("WebSocket Port:"), 0, 0)
        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1024, 65535)
        self.ws_port_spin.setValue(self.port)
        self.ws_port_spin.valueChanged.connect(lambda v: setattr(self, 'port', v))
        network_layout.addWidget(self.ws_port_spin, 0, 1)
        
        layout.addWidget(network_group)
        
        layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        parent_layout = QVBoxLayout(parent)
        parent_layout.addWidget(scroll)
        
    def setup_connection_tab(self, parent):
        """Setup the connection tab"""
        layout = QVBoxLayout(parent)
        
        # Server Info
        server_group = QGroupBox("Server Information")
        server_layout = QGridLayout(server_group)
        
        server_layout.addWidget(QLabel("WebSocket Port:"), 0, 0)
        self.ws_port_label = QLabel(str(self.port))
        self.ws_port_label.setFont(QFont("Courier", 12))
        server_layout.addWidget(self.ws_port_label, 0, 1)
        
        # Connection URL will be shown when streaming
        server_layout.addWidget(QLabel("Status:"), 1, 0)
        self.connection_status = QLabel("Not streaming")
        server_layout.addWidget(self.connection_status, 1, 1)
        
        layout.addWidget(server_group)
        
        # Mobile App URL
        mobile_group = QGroupBox("Mobile App Access")
        mobile_layout = QVBoxLayout(mobile_group)
        
        self.mobile_info = QLabel("Start streaming to see connection info")
        self.mobile_info.setAlignment(Qt.AlignCenter)
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
                
    def on_preset_changed(self, preset: str):
        self.preset = preset
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
        
    def on_downscale_changed(self, value: int):
        self.scale = value / 100.0
        self.downscale_label.setText(f"{self.scale:.0%}")
        
    def on_gpu_toggled(self, state: int):
        self.use_gpu = (state == Qt.Checked)
        # Update backend label
        if self.use_gpu and self.jpeg_library == "nvjpeg":
            self.stat_labels['backend'].setText("C++ (nvJPEG/GPU)")
        else:
            self.stat_labels['backend'].setText("C++ (TurboJPEG)")
            
    def on_jpeg_library_changed(self, index: int):
        self.jpeg_library = "turbojpeg" if index == 0 else "nvjpeg"
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
        self.stream_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        
    def stop_streaming(self):
        if self.backend:
            self.backend.stop()
            self.backend = None
            
        self.is_streaming = False
        self.stream_btn.setText("▶ Start Streaming")
        self.stream_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.connection_status.setText("Not streaming")
        
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
            self.stat_labels['clients'].setText(str(stats['clients']))
        if 'bitrate' in stats:
            self.stat_labels['bitrate'].setText(f"{stats['bitrate']:.2f} Mbps")
            
    def on_backend_error(self, error: str):
        self.log_text.append(f"ERROR: {error}")
        self.statusBar.showMessage(f"Error: {error}")
        
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
        
    def closeEvent(self, event):
        self.stop_streaming()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Set style
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
