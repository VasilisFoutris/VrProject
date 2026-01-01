# VR Screen Streamer

A high-performance screen streaming solution for VR headsets. Stream your PC games and applications to your phone-based VR headset over WiFi with low latency.

## 📋 Overview

This project consists of two parts:
1. **PC Application** (Windows) - Captures your screen, encodes it in VR format, and streams it
2. **Mobile Web App** (iOS/Android) - Receives the stream and displays it in VR-ready format

## 🚀 Features

- **Window Selection**: Choose any window or full screen to capture
- **VR Mode**: Automatic side-by-side stereo conversion for VR headsets
- **Low Latency**: Optimized for real-time streaming (< 50ms typical)
- **Tunable Quality**: Multiple presets from ultra-low latency to high quality
- **Adaptive Encoding**: Automatically adjusts quality based on performance
- **Cross-Platform Mobile**: Works on any phone with a modern browser
- **Simple Connection**: Connect via WiFi using IP address

## 📁 Project Structure

```
VrProject/
├── pc_app/                  # Windows PC application
│   ├── main.py              # Entry point
│   ├── gui.py               # PyQt5 GUI
│   ├── capture.py           # Window capture module
│   ├── encoder.py           # Video encoding/compression
│   ├── server.py            # WebSocket streaming server
│   ├── config.py            # Configuration management
│   └── requirements.txt     # Python dependencies
│
├── mobile_app/              # Mobile web application
│   ├── index.html           # Main HTML page
│   ├── style.css            # Styles
│   └── app.js               # JavaScript application
│
└── README.md                # This file
```

## 🔧 Installation & Setup

### PC Application (Windows)

#### Prerequisites
- Windows 10 or later
- Python 3.8 or later
- WiFi connection on the same network as your phone

#### Installation Steps

1. **Open Command Prompt or PowerShell** and navigate to the project:
   ```cmd
   cd /path/to/VrProject/pc_app
   ```

2. **Create a virtual environment** (recommended):
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```cmd
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```cmd
   python main.py
   ```

### Mobile Web App

The mobile web app is served directly by the PC application. No separate installation needed!

1. Start the PC application
2. Click "Start Streaming"
3. On your phone, open the browser and go to the URL shown in the app
   - Example: `http://192.168.1.100:8080`
4. Enter the PC's IP address and click Connect

## 📱 Using the Mobile App

### Connection
1. Make sure your phone is on the same WiFi network as your PC
2. Open the URL shown in the PC app (e.g., `http://192.168.1.100:8080`)
3. Enter the PC's IP address
4. Tap "Connect"

### VR Mode
1. Once connected, put your phone in your VR headset
2. The app will display a side-by-side stereo view
3. Rotate your phone to landscape orientation

### Settings
- **VR Mode**: Toggle between side-by-side and mono view
- **Quality Preset**: Choose from ultra-low latency to high quality
- **Buffer Frames**: Adjust buffering (0 = lowest latency)
- **Show Stats**: Display FPS, latency, and bandwidth info

## ⚙️ PC Application Settings

### Quality Presets

| Preset | JPEG Quality | Downscale | Target FPS | Use Case |
|--------|-------------|-----------|------------|----------|
| Ultra Low Latency | 60% | 75% | 60 | Fast-paced games |
| Low Latency | 75% | 85% | 60 | Most games |
| Balanced | 85% | 100% | 45 | Movies, slow games |
| Quality | 95% | 100% | 30 | Screenshots, text |

### Network Settings
- **WebSocket Port**: Default 8765 (video streaming)
- **HTTP Port**: Default 8080 (mobile app serving)

### VR Settings
- **VR Mode**: Enable/disable stereo side-by-side
- **Eye Separation**: Adjust 3D depth effect (0-10%)

## 🔥 Performance Tips

### For Lowest Latency
1. Use "Ultra Low Latency" preset
2. Set buffer frames to 0 on mobile
3. Use 5GHz WiFi (not 2.4GHz)
4. Keep PC and phone close to router
5. Close other apps using network

### For Best Quality
1. Use "Quality" preset
2. Enable adaptive encoding
3. Use wired Ethernet on PC if possible

### Troubleshooting

**Can't connect from phone**
- Check both devices are on same WiFi network
- Check Windows Firewall allows the app
- Try disabling VPN on both devices

**High latency**
- Switch to a lower quality preset
- Use 5GHz WiFi band
- Reduce distance to WiFi router

**Choppy video**
- Lower the quality preset
- Reduce target FPS
- Enable adaptive encoding

**Black screen**
- Select a window to capture
- Check the window isn't minimized
- Try "Full Screen" capture mode

## 🔒 Network & Security

- The app only works on local network (LAN)
- No data is sent to the internet
- Consider setting a static IP on your PC for consistent connections

### Setting Static IP (Windows)
1. Open Network Settings
2. Change adapter options
3. Right-click WiFi > Properties
4. Select "Internet Protocol Version 4"
5. Use these settings:
   - IP: 192.168.1.100 (or similar)
   - Subnet: 255.255.255.0
   - Gateway: Your router's IP

## 📊 Technical Details

### Streaming Pipeline
1. **Capture** (5-10ms): Window capture using Windows GDI
2. **Encode** (3-8ms): JPEG compression with configurable quality
3. **Send** (1-5ms): WebSocket binary transmission
4. **Receive** (1-2ms): Browser WebSocket reception
5. **Decode** (2-5ms): Browser image decoding
6. **Display** (1-3ms): Canvas rendering

**Total typical latency: 15-35ms** (depending on settings)

### Protocols
- **WebSocket**: Real-time bidirectional communication
- **HTTP**: Serving the mobile web app

### Compression
- **JPEG**: Fast encoding, good quality/size ratio
- **WebP**: Optional, better compression but slower

## 🛠️ Development

### Running Tests

```bash
# Test capture module
python capture.py

# Test encoder module
python encoder.py

# Test server module
python server.py
```

### Building Executable (Optional)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "VR Screen Streamer" main.py
```

## 📄 License

This project is provided as-is for personal use.

## 🤝 Contributing

Feel free to modify and improve this project for your needs!

---

**Enjoy your VR gaming experience! 🎮🥽**
