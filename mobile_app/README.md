# VR Screen Viewer - Mobile Web App

A progressive web app for viewing VR screen streams on your phone.

## 📱 Features

- **Cross-Platform**: Works on iOS and Android
- **No App Install Required**: Just open the URL in your browser
- **VR Ready**: Side-by-side stereo display for VR headsets
- **Low Latency**: Optimized WebSocket streaming
- **Adaptive Quality**: Multiple quality presets
- **Fullscreen & Landscape Lock**: Optimized for VR viewing

## 🚀 Quick Start

1. Start the PC streaming application
2. Note the displayed IP address and ports
3. On your phone, open browser and go to:
   ```
   http://[PC-IP-ADDRESS]:8080
   ```
4. Enter the PC's IP address in the connection screen
5. Tap "Connect"
6. Put phone in VR headset and enjoy!

## 📋 Requirements

- Modern mobile browser (Chrome, Safari, Firefox)
- Same WiFi network as the PC
- Phone with gyroscope for VR headset use

## ⚙️ Settings

### Display
- **VR Mode**: Side-by-side stereo or mono view
- **Fullscreen**: Immersive fullscreen mode
- **Orientation Lock**: Lock to landscape for VR

### Quality
- **Quality Preset**: From ultra-low latency to high quality
- **Buffer Frames**: Trade latency for smoothness

### Performance
- **Show Stats**: Display FPS, latency, and bandwidth
- **Hardware Decode**: Use GPU for faster decoding

## 🎮 Controls

When viewing:
- **Tap screen**: Show/hide controls
- **❌ button**: Disconnect
- **⚙️ button**: Open settings
- **📺 button**: Toggle fullscreen

## 📊 Stats Display

- **FPS**: Frames received per second
- **Latency**: Time between frames (ms)
- **Size**: Frame size in KB
- **Frames**: Total frames received

## 💡 Tips for Best Experience

1. **Use 5GHz WiFi** for lower latency
2. **Set buffer to 0** for lowest latency
3. **Lock orientation** before inserting in headset
4. **Enter fullscreen** for immersive experience
5. **Keep screen awake** (app does this automatically)

## 🔧 Troubleshooting

**Can't connect**
- Verify PC IP address is correct
- Check both devices on same network
- Check PC firewall settings

**Choppy video**
- Switch to lower quality preset
- Reduce buffer frames
- Move closer to WiFi router

**High latency**
- Use "Ultra Low Latency" preset
- Set buffer to 0
- Use 5GHz WiFi band

## 📁 Files

- `index.html` - Main HTML structure
- `style.css` - Styling and responsive design
- `app.js` - JavaScript application logic

## 🛠️ Development

### Local Testing

You can test the mobile app locally:

1. Start a local HTTP server:
   ```bash
   python -m http.server 8080
   ```

2. Open `http://localhost:8080` in browser

3. Use browser developer tools to simulate mobile device

### Browser Compatibility

Tested on:
- Chrome Mobile 80+
- Safari iOS 13+
- Firefox Mobile 75+
- Samsung Internet 12+

## 📄 License

Part of the VR Screen Streamer project.
