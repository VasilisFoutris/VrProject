"""
VR Screen Streamer - PC GUI
Simple PyQt5 interface for window selection, settings, and streaming control.
"""

import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider, QGroupBox, QGridLayout,
    QSpinBox, QCheckBox, QFrame, QListWidget, QListWidgetItem,
    QStatusBar, QMessageBox, QTabWidget, QTextEdit, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QPixmap, QImage, QPalette, QColor

import numpy as np
import cv2
import time
import threading

from config import Config, EncoderConfig, NetworkConfig, QUALITY_PRESETS, apply_preset
from capture import CaptureManager, WindowEnumerator, WindowInfo
from encoder import VREncoder, AdaptiveEncoder
from server import StreamingServer, HTTPServer, ClientInfo, StreamStats


class StreamingThread(QThread):
    """Background thread for capture and streaming"""
    
    stats_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, capture_manager: CaptureManager, encoder: VREncoder, 
                 server: StreamingServer, config: Config):
        super().__init__()
        self.capture_manager = capture_manager
        self.encoder = encoder
        self.server = server
        self.config = config
        self._running = False
    
    def run(self):
        """Main streaming loop"""
        self._running = True
        target_fps = self.config.capture.target_fps
        frame_time = 1.0 / target_fps
        
        frame_count = 0
        start_time = time.time()
        
        while self._running:
            loop_start = time.perf_counter()
            
            try:
                # Capture frame
                frame = self.capture_manager.get_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue
                
                # Encode frame
                encoded = self.encoder.encode_frame(frame)
                if encoded is None:
                    continue
                
                # Push to server for broadcasting
                self.server.push_frame(encoded)
                
                frame_count += 1
                
                # Update stats every second
                elapsed = time.time() - start_time
                if elapsed >= 1.0:
                    stats = {
                        'capture_fps': self.capture_manager.get_fps(),
                        'stream_fps': self.server.get_stats().current_fps,
                        'encode_time': self.encoder.get_last_encode_time(),
                        'clients': self.server.get_client_count(),
                        'quality': self.encoder.config.jpeg_quality,
                        'bytes_sent': self.server.get_stats().total_bytes_sent,
                    }
                    self.stats_updated.emit(stats)
                    frame_count = 0
                    start_time = time.time()
                
            except Exception as e:
                self.error_occurred.emit(str(e))
                time.sleep(0.1)
            
            # Maintain target frame rate
            elapsed = time.perf_counter() - loop_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def stop(self):
        """Stop the streaming thread"""
        self._running = False
        self.wait(2000)


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize components
        self.config = Config.load()
        self.capture_manager = CaptureManager()
        self.encoder = AdaptiveEncoder(self.config.encoder, self.config.capture.target_fps)
        self.server = StreamingServer(self.config.network)
        self.http_server = None
        
        self.streaming_thread = None
        self.is_streaming = False
        
        # Setup UI
        self.init_ui()
        
        # Setup timers
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_windows)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
        
        # Initial window list refresh
        self.refresh_windows()
        
        # Setup server callbacks
        self.server.set_callbacks(
            on_connect=self.on_client_connect,
            on_disconnect=self.on_client_disconnect,
            on_stats=self.on_stats_update
        )
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("VR Screen Streamer")
        self.setMinimumSize(600, 700)
        
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
        
        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
    
    def setup_stream_tab(self, parent):
        """Setup the streaming tab"""
        layout = QVBoxLayout(parent)
        
        # Window Selection
        window_group = QGroupBox("Window Selection")
        window_layout = QVBoxLayout(window_group)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Windows")
        refresh_btn.clicked.connect(self.refresh_windows)
        window_layout.addWidget(refresh_btn)
        
        # Window list
        self.window_list = QListWidget()
        self.window_list.setMinimumHeight(150)
        self.window_list.itemClicked.connect(self.on_window_selected)
        window_layout.addWidget(self.window_list)
        
        # Full screen option
        fullscreen_btn = QPushButton("📺 Capture Full Screen")
        fullscreen_btn.clicked.connect(self.select_fullscreen)
        window_layout.addWidget(fullscreen_btn)
        
        layout.addWidget(window_group)
        
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
            ('stream_fps', 'Stream FPS:'),
            ('encode_time', 'Encode Time:'),
            ('clients', 'Connected Clients:'),
            ('quality', 'Current Quality:'),
            ('bandwidth', 'Bandwidth:'),
        ]
        
        for i, (key, label) in enumerate(stat_items):
            lbl = QLabel(label)
            val = QLabel("--")
            val.setFont(QFont("Courier", 10))
            stats_layout.addWidget(lbl, i, 0)
            stats_layout.addWidget(val, i, 1)
            self.stat_labels[key] = val
        
        layout.addWidget(stats_group)
        
        layout.addStretch()
    
    def setup_settings_tab(self, parent):
        """Setup the settings tab"""
        layout = QVBoxLayout(parent)
        
        # Quality Preset
        preset_group = QGroupBox("Quality Preset")
        preset_layout = QVBoxLayout(preset_group)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(['ultra_low_latency', 'low_latency', 'balanced', 'quality'])
        self.preset_combo.setCurrentText(self.config.encoder.preset)
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        
        layout.addWidget(preset_group)
        
        # Video Quality
        quality_group = QGroupBox("Video Quality")
        quality_layout = QGridLayout(quality_group)
        
        # JPEG Quality slider
        quality_layout.addWidget(QLabel("JPEG Quality:"), 0, 0)
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(30, 100)
        self.quality_slider.setValue(self.config.encoder.jpeg_quality)
        self.quality_slider.valueChanged.connect(self.on_quality_changed)
        quality_layout.addWidget(self.quality_slider, 0, 1)
        self.quality_label = QLabel(str(self.config.encoder.jpeg_quality))
        quality_layout.addWidget(self.quality_label, 0, 2)
        
        # Target FPS
        quality_layout.addWidget(QLabel("Target FPS:"), 1, 0)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(15, 120)
        self.fps_spin.setValue(self.config.capture.target_fps)
        self.fps_spin.valueChanged.connect(self.on_fps_changed)
        quality_layout.addWidget(self.fps_spin, 1, 1)
        
        # Downscale factor
        quality_layout.addWidget(QLabel("Downscale:"), 2, 0)
        self.downscale_slider = QSlider(Qt.Horizontal)
        self.downscale_slider.setRange(50, 100)
        self.downscale_slider.setValue(int(self.config.encoder.downscale_factor * 100))
        self.downscale_slider.valueChanged.connect(self.on_downscale_changed)
        quality_layout.addWidget(self.downscale_slider, 2, 1)
        self.downscale_label = QLabel(f"{self.config.encoder.downscale_factor:.0%}")
        quality_layout.addWidget(self.downscale_label, 2, 2)
        
        layout.addWidget(quality_group)
        
        # VR Settings
        vr_group = QGroupBox("VR Settings")
        vr_layout = QGridLayout(vr_group)
        
        # VR mode toggle
        self.vr_checkbox = QCheckBox("Enable VR Mode (Side-by-Side)")
        self.vr_checkbox.setChecked(self.config.encoder.vr_enabled)
        self.vr_checkbox.stateChanged.connect(self.on_vr_toggled)
        vr_layout.addWidget(self.vr_checkbox, 0, 0, 1, 2)
        
        # Eye separation
        vr_layout.addWidget(QLabel("Eye Separation:"), 1, 0)
        self.separation_slider = QSlider(Qt.Horizontal)
        self.separation_slider.setRange(0, 10)
        self.separation_slider.setValue(int(self.config.encoder.eye_separation * 100))
        self.separation_slider.valueChanged.connect(self.on_separation_changed)
        vr_layout.addWidget(self.separation_slider, 1, 1)
        self.separation_label = QLabel(f"{self.config.encoder.eye_separation:.0%}")
        vr_layout.addWidget(self.separation_label, 1, 2)
        
        layout.addWidget(vr_group)
        
        # Adaptive encoding
        adaptive_group = QGroupBox("Adaptive Encoding")
        adaptive_layout = QVBoxLayout(adaptive_group)
        
        self.adaptive_checkbox = QCheckBox("Enable Adaptive Quality")
        self.adaptive_checkbox.setChecked(True)
        self.adaptive_checkbox.stateChanged.connect(self.on_adaptive_toggled)
        adaptive_layout.addWidget(self.adaptive_checkbox)
        
        layout.addWidget(adaptive_group)
        
        # Save button
        save_btn = QPushButton("💾 Save Settings")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
    
    def setup_connection_tab(self, parent):
        """Setup the connection tab"""
        layout = QVBoxLayout(parent)
        
        # Server Info
        server_group = QGroupBox("Server Information")
        server_layout = QGridLayout(server_group)
        
        server_layout.addWidget(QLabel("Server IP:"), 0, 0)
        self.ip_label = QLabel(self.server.get_server_ip())
        self.ip_label.setFont(QFont("Courier", 12, QFont.Bold))
        self.ip_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        server_layout.addWidget(self.ip_label, 0, 1)
        
        server_layout.addWidget(QLabel("WebSocket Port:"), 1, 0)
        self.ws_port_label = QLabel(str(self.config.network.port))
        self.ws_port_label.setFont(QFont("Courier", 12))
        server_layout.addWidget(self.ws_port_label, 1, 1)
        
        server_layout.addWidget(QLabel("HTTP Port:"), 2, 0)
        self.http_port_label = QLabel(str(self.config.network.http_port))
        self.http_port_label.setFont(QFont("Courier", 12))
        server_layout.addWidget(self.http_port_label, 2, 1)
        
        server_layout.addWidget(QLabel("Connection URL:"), 3, 0)
        self.url_label = QLabel(self.server.get_connection_url())
        self.url_label.setFont(QFont("Courier", 10))
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        server_layout.addWidget(self.url_label, 3, 1)
        
        layout.addWidget(server_group)
        
        # Mobile App URL
        mobile_group = QGroupBox("Mobile App Access")
        mobile_layout = QVBoxLayout(mobile_group)
        
        mobile_info = QLabel(
            f"Open this URL on your phone's browser:\n\n"
            f"http://{self.server.get_server_ip()}:{self.config.network.http_port}"
        )
        mobile_info.setFont(QFont("Courier", 11))
        mobile_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mobile_info.setAlignment(Qt.AlignCenter)
        mobile_layout.addWidget(mobile_info)
        
        layout.addWidget(mobile_group)
        
        # Network Settings
        network_group = QGroupBox("Network Settings")
        network_layout = QGridLayout(network_group)
        
        network_layout.addWidget(QLabel("WebSocket Port:"), 0, 0)
        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1024, 65535)
        self.ws_port_spin.setValue(self.config.network.port)
        network_layout.addWidget(self.ws_port_spin, 0, 1)
        
        network_layout.addWidget(QLabel("HTTP Port:"), 1, 0)
        self.http_port_spin = QSpinBox()
        self.http_port_spin.setRange(1024, 65535)
        self.http_port_spin.setValue(self.config.network.http_port)
        network_layout.addWidget(self.http_port_spin, 1, 1)
        
        apply_network_btn = QPushButton("Apply Network Settings")
        apply_network_btn.clicked.connect(self.apply_network_settings)
        network_layout.addWidget(apply_network_btn, 2, 0, 1, 2)
        
        layout.addWidget(network_group)
        
        # Connected Clients
        clients_group = QGroupBox("Connected Clients")
        clients_layout = QVBoxLayout(clients_group)
        
        self.clients_list = QListWidget()
        self.clients_list.setMinimumHeight(100)
        clients_layout.addWidget(self.clients_list)
        
        layout.addWidget(clients_group)
        
        layout.addStretch()
    
    def refresh_windows(self):
        """Refresh the list of available windows"""
        self.window_list.clear()
        
        windows = WindowEnumerator.enumerate_windows()
        
        for window in windows:
            item = QListWidgetItem(f"🪟 {window.title} ({window.width}x{window.height})")
            item.setData(Qt.UserRole, window)
            self.window_list.addItem(item)
    
    def on_window_selected(self, item: QListWidgetItem):
        """Handle window selection"""
        window = item.data(Qt.UserRole)
        if window:
            self.capture_manager.select_window(window)
            self.statusBar.showMessage(f"Selected: {window.title}")
    
    def select_fullscreen(self):
        """Select full screen capture mode"""
        self.capture_manager.select_full_screen()
        self.window_list.clearSelection()
        self.statusBar.showMessage("Selected: Full Screen")
    
    def toggle_streaming(self):
        """Start or stop streaming"""
        if self.is_streaming:
            self.stop_streaming()
        else:
            self.start_streaming()
    
    def start_streaming(self):
        """Start the streaming process"""
        # Start the WebSocket server
        self.server.start()
        
        # Start HTTP server for mobile app
        mobile_app_path = os.path.join(os.path.dirname(__file__), '..', 'mobile_app')
        if os.path.exists(mobile_app_path):
            self.http_server = HTTPServer(self.config.network.http_port, mobile_app_path)
            self.http_server.start()
        
        # Start streaming thread
        self.streaming_thread = StreamingThread(
            self.capture_manager, self.encoder, self.server, self.config
        )
        self.streaming_thread.stats_updated.connect(self.update_stats)
        self.streaming_thread.error_occurred.connect(self.on_stream_error)
        self.streaming_thread.start()
        
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
        self.statusBar.showMessage("Streaming started")
    
    def stop_streaming(self):
        """Stop the streaming process"""
        if self.streaming_thread:
            self.streaming_thread.stop()
            self.streaming_thread = None
        
        self.server.stop()
        
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
        self.statusBar.showMessage("Streaming stopped")
    
    def update_stats(self, stats: dict):
        """Update statistics display"""
        self.stat_labels['capture_fps'].setText(f"{stats.get('capture_fps', 0):.1f}")
        self.stat_labels['stream_fps'].setText(f"{stats.get('stream_fps', 0):.1f}")
        self.stat_labels['encode_time'].setText(f"{stats.get('encode_time', 0):.1f} ms")
        self.stat_labels['clients'].setText(str(stats.get('clients', 0)))
        self.stat_labels['quality'].setText(str(stats.get('quality', 0)))
        
        bytes_sent = stats.get('bytes_sent', 0)
        if bytes_sent > 1024 * 1024:
            bandwidth = f"{bytes_sent / (1024 * 1024):.1f} MB"
        else:
            bandwidth = f"{bytes_sent / 1024:.1f} KB"
        self.stat_labels['bandwidth'].setText(bandwidth)
    
    def on_stream_error(self, error: str):
        """Handle streaming errors"""
        self.statusBar.showMessage(f"Error: {error}")
    
    def on_client_connect(self, client: ClientInfo):
        """Handle client connection"""
        self.clients_list.addItem(f"📱 {client.address}")
    
    def on_client_disconnect(self, client: ClientInfo):
        """Handle client disconnection"""
        for i in range(self.clients_list.count()):
            item = self.clients_list.item(i)
            if client.address in item.text():
                self.clients_list.takeItem(i)
                break
    
    def on_stats_update(self, stats: StreamStats):
        """Handle stats update from server"""
        pass  # Already handled by streaming thread
    
    def on_preset_changed(self, preset: str):
        """Handle quality preset change"""
        self.config = apply_preset(self.config, preset)
        self.update_ui_from_config()
        self.apply_encoder_settings()
    
    def on_quality_changed(self, value: int):
        """Handle quality slider change"""
        self.quality_label.setText(str(value))
        self.config.encoder.jpeg_quality = value
        self.apply_encoder_settings()
    
    def on_fps_changed(self, value: int):
        """Handle FPS change"""
        self.config.capture.target_fps = value
    
    def on_downscale_changed(self, value: int):
        """Handle downscale change"""
        factor = value / 100.0
        self.downscale_label.setText(f"{factor:.0%}")
        self.config.encoder.downscale_factor = factor
        self.apply_encoder_settings()
    
    def on_vr_toggled(self, state: int):
        """Handle VR mode toggle"""
        self.config.encoder.vr_enabled = state == Qt.Checked
        self.apply_encoder_settings()
    
    def on_separation_changed(self, value: int):
        """Handle eye separation change"""
        separation = value / 100.0
        self.separation_label.setText(f"{separation:.0%}")
        self.config.encoder.eye_separation = separation
        self.apply_encoder_settings()
    
    def on_adaptive_toggled(self, state: int):
        """Handle adaptive encoding toggle"""
        if isinstance(self.encoder, AdaptiveEncoder):
            self.encoder.adaptation_enabled = state == Qt.Checked
    
    def update_ui_from_config(self):
        """Update UI elements from current config"""
        self.quality_slider.setValue(self.config.encoder.jpeg_quality)
        self.quality_label.setText(str(self.config.encoder.jpeg_quality))
        self.fps_spin.setValue(self.config.capture.target_fps)
        self.downscale_slider.setValue(int(self.config.encoder.downscale_factor * 100))
        self.downscale_label.setText(f"{self.config.encoder.downscale_factor:.0%}")
    
    def apply_encoder_settings(self):
        """Apply current settings to encoder"""
        self.encoder.update_config(self.config.encoder)
    
    def apply_network_settings(self):
        """Apply network settings"""
        self.config.network.port = self.ws_port_spin.value()
        self.config.network.http_port = self.http_port_spin.value()
        
        self.ws_port_label.setText(str(self.config.network.port))
        self.http_port_label.setText(str(self.config.network.http_port))
        
        QMessageBox.information(
            self, "Settings Applied",
            "Network settings will take effect when you restart streaming."
        )
    
    def save_settings(self):
        """Save current settings to file"""
        self.config.save()
        self.statusBar.showMessage("Settings saved")
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.is_streaming:
            self.stop_streaming()
        self.capture_manager.cleanup()
        self.config.save()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
