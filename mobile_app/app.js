/**
 * VR Screen Viewer - Mobile Web App
 * High-performance WebSocket client for VR video streaming
 */

class VRStreamViewer {
  constructor() {
    // DOM Elements
    this.screens = {
      connection: document.getElementById("connection-screen"),
      settings: document.getElementById("settings-screen"),
      viewer: document.getElementById("viewer-screen"),
    };

    this.elements = {
      serverIp: document.getElementById("server-ip"),
      serverPort: document.getElementById("server-port"),
      connectBtn: document.getElementById("connect-btn"),
      connectionStatus: document.getElementById("connection-status"),
      recentList: document.getElementById("recent-list"),
      canvas: document.getElementById("vr-canvas"),

      // Stats
      statFps: document.getElementById("stat-fps"),
      statLatency: document.getElementById("stat-latency"),
      statSize: document.getElementById("stat-size"),
      statFrames: document.getElementById("stat-frames"),
      statsOverlay: document.getElementById("stats-overlay"),

      // Controls
      disconnectBtn: document.getElementById("disconnect-btn"),
      settingsBtn: document.getElementById("settings-btn"),
      fullscreenViewerBtn: document.getElementById("fullscreen-viewer-btn"),
      reconnectBtn: document.getElementById("reconnect-btn"),
      connectionLost: document.getElementById("connection-lost"),

      // Settings
      vrMode: document.getElementById("vr-mode"),
      qualityPreset: document.getElementById("quality-preset"),
      bufferFrames: document.getElementById("buffer-frames"),
      bufferValue: document.getElementById("buffer-value"),
      showStats: document.getElementById("show-stats"),
      hardwareDecode: document.getElementById("hardware-decode"),
      fullscreenBtn: document.getElementById("fullscreen-btn"),
      orientationBtn: document.getElementById("orientation-btn"),
      backToConnection: document.getElementById("back-to-connection"),
    };

    // Canvas context
    this.ctx = this.elements.canvas.getContext("2d", {
      alpha: false,
      desynchronized: true, // Reduce latency
    });

    // WebSocket
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;

    // Performance tracking
    this.stats = {
      frameCount: 0,
      totalFrames: 0,
      lastFrameTime: 0,
      fps: 0,
      latency: 0,
      lastSize: 0,
      fpsUpdateTime: Date.now(),
    };

    // Settings
    this.settings = {
      vrMode: "sbs",
      qualityPreset: "auto",
      bufferFrames: 1,
      showStats: true,
      hardwareDecode: true,
    };

    // Frame buffer for smoother playback
    this.frameBuffer = [];
    this.isProcessingFrame = false;

    // Image for decoding
    this.frameImage = new Image();
    this.frameImage.onload = () => this.drawFrame();

    // Initialize
    this.init();
  }

  init() {
    this.loadSettings();
    this.loadRecentConnections();
    this.setupEventListeners();
    this.resizeCanvas();

    // Auto-detect server IP from URL if served by PC app
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has("ip")) {
      this.elements.serverIp.value = urlParams.get("ip");
    } else if (
      window.location.hostname &&
      window.location.hostname !== "localhost"
    ) {
      this.elements.serverIp.value = window.location.hostname;
    }

    // Resize canvas on window resize
    window.addEventListener("resize", () => this.resizeCanvas());
    window.addEventListener("orientationchange", () => {
      setTimeout(() => this.resizeCanvas(), 100);
    });
  }

  setupEventListeners() {
    // Connection
    this.elements.connectBtn.addEventListener("click", () => this.connect());
    this.elements.serverIp.addEventListener("keypress", (e) => {
      if (e.key === "Enter") this.connect();
    });

    // Viewer controls
    this.elements.disconnectBtn.addEventListener("click", () =>
      this.disconnect()
    );
    this.elements.settingsBtn.addEventListener("click", () =>
      this.showSettings()
    );
    this.elements.fullscreenViewerBtn.addEventListener("click", () =>
      this.toggleFullscreen()
    );
    this.elements.reconnectBtn.addEventListener("click", () =>
      this.reconnect()
    );

    // Settings
    this.elements.vrMode.addEventListener("change", (e) => {
      this.settings.vrMode = e.target.value;
      this.saveSettings();
    });

    this.elements.qualityPreset.addEventListener("change", (e) => {
      this.settings.qualityPreset = e.target.value;
      this.sendQualityRequest();
      this.saveSettings();
    });

    this.elements.bufferFrames.addEventListener("input", (e) => {
      this.settings.bufferFrames = parseInt(e.target.value);
      this.elements.bufferValue.textContent = e.target.value;
      this.saveSettings();
    });

    this.elements.showStats.addEventListener("change", (e) => {
      this.settings.showStats = e.target.checked;
      this.elements.statsOverlay.style.display = e.target.checked
        ? "block"
        : "none";
      this.saveSettings();
    });

    this.elements.hardwareDecode.addEventListener("change", (e) => {
      this.settings.hardwareDecode = e.target.checked;
      this.saveSettings();
    });

    this.elements.fullscreenBtn.addEventListener("click", () =>
      this.toggleFullscreen()
    );
    this.elements.orientationBtn.addEventListener("click", () =>
      this.lockOrientation()
    );
    this.elements.backToConnection.addEventListener("click", () =>
      this.showConnectionScreen()
    );

    // Touch to show/hide controls
    let touchTimeout;
    this.elements.canvas.addEventListener("touchstart", () => {
      document.getElementById("controls-overlay").style.opacity = "1";
      clearTimeout(touchTimeout);
      touchTimeout = setTimeout(() => {
        document.getElementById("controls-overlay").style.opacity = "0";
      }, 3000);
    });
  }

  showScreen(screenName) {
    Object.values(this.screens).forEach((screen) =>
      screen.classList.remove("active")
    );
    this.screens[screenName].classList.add("active");
  }

  showConnectionScreen() {
    this.showScreen("connection");
  }

  showSettings() {
    this.showScreen("settings");
  }

  showViewer() {
    this.showScreen("viewer");
    this.resizeCanvas();
  }

  resizeCanvas() {
    const canvas = this.elements.canvas;
    const container = this.screens.viewer;

    canvas.width = container.clientWidth || window.innerWidth;
    canvas.height = container.clientHeight || window.innerHeight;

    // Optimize for mobile
    this.ctx.imageSmoothingEnabled = true;
    this.ctx.imageSmoothingQuality = "low"; // Fast rendering
  }

  connect() {
    const ip = this.elements.serverIp.value.trim();
    const port = this.elements.serverPort.value.trim();

    if (!ip) {
      this.showStatus("Please enter the PC IP address", "error");
      return;
    }

    const url = `ws://${ip}:${port}`;
    this.showStatus("Connecting...", "connecting");
    this.elements.connectBtn.disabled = true;

    try {
      this.ws = new WebSocket(url);
      this.ws.binaryType = "blob"; // Receive as blob for faster handling

      this.ws.onopen = () => {
        console.log("WebSocket connected");
        this.showStatus("Connected!", "success");
        this.saveRecentConnection(ip, port);
        this.reconnectAttempts = 0;

        setTimeout(() => {
          this.showViewer();
          this.requestWakeLock();
        }, 500);
      };

      this.ws.onmessage = (event) => this.handleMessage(event);

      this.ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        this.showStatus("Connection failed", "error");
        this.elements.connectBtn.disabled = false;
      };

      this.ws.onclose = () => {
        console.log("WebSocket closed");
        if (this.screens.viewer.classList.contains("active")) {
          this.handleDisconnect();
        }
        this.elements.connectBtn.disabled = false;
      };
    } catch (error) {
      console.error("Connection error:", error);
      this.showStatus("Invalid address", "error");
      this.elements.connectBtn.disabled = false;
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.showConnectionScreen();
    this.releaseWakeLock();
  }

  handleDisconnect() {
    this.elements.connectionLost.classList.remove("hidden");

    // Auto-reconnect
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      setTimeout(() => this.reconnect(), this.reconnectDelay);
    }
  }

  reconnect() {
    this.reconnectAttempts++;
    this.elements.connectionLost.classList.add("hidden");
    this.connect();
  }

  handleMessage(event) {
    const receiveTime = performance.now();

    // Check if it's a text message (config/ping) or binary (frame)
    if (typeof event.data === "string") {
      try {
        const msg = JSON.parse(event.data);
        this.handleControlMessage(msg);
      } catch (e) {
        console.error("Invalid JSON message:", e);
      }
      return;
    }

    // Binary frame data
    this.processFrame(event.data, receiveTime);
  }

  handleControlMessage(msg) {
    switch (msg.type) {
      case "config":
        console.log("Received server config:", msg);
        break;

      case "ping":
        // Respond with pong
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(
            JSON.stringify({
              type: "pong",
              sent_time: msg.sent_time,
            })
          );
        }
        break;
    }
  }

  processFrame(blob, receiveTime) {
    // Update stats
    this.stats.frameCount++;
    this.stats.totalFrames++;
    this.stats.lastSize = blob.size;

    // Calculate latency (rough estimate based on frame timing)
    const now = performance.now();
    if (this.stats.lastFrameTime > 0) {
      this.stats.latency = now - this.stats.lastFrameTime;
    }
    this.stats.lastFrameTime = now;

    // Update FPS every second
    if (now - this.stats.fpsUpdateTime >= 1000) {
      this.stats.fps = this.stats.frameCount;
      this.stats.frameCount = 0;
      this.stats.fpsUpdateTime = now;
      this.updateStatsDisplay();
    }

    // Buffer management
    if (this.settings.bufferFrames === 0) {
      // No buffering - display immediately
      this.displayFrame(blob);
    } else {
      // Add to buffer
      this.frameBuffer.push(blob);

      // Trim buffer if too large
      while (this.frameBuffer.length > this.settings.bufferFrames) {
        this.frameBuffer.shift();
      }

      // Process buffer
      if (!this.isProcessingFrame && this.frameBuffer.length > 0) {
        this.processNextFrame();
      }
    }
  }

  processNextFrame() {
    if (this.frameBuffer.length === 0) {
      this.isProcessingFrame = false;
      return;
    }

    this.isProcessingFrame = true;
    const blob = this.frameBuffer.shift();
    this.displayFrame(blob);
  }

  displayFrame(blob) {
    // Create object URL for the blob
    const url = URL.createObjectURL(blob);

    // Clean up previous URL
    if (this.currentFrameUrl) {
      URL.revokeObjectURL(this.currentFrameUrl);
    }
    this.currentFrameUrl = url;

    // Load and display
    this.frameImage.src = url;
  }

  drawFrame() {
    const canvas = this.elements.canvas;
    const ctx = this.ctx;
    const img = this.frameImage;

    // Clear canvas
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Calculate scaling to fit canvas while maintaining aspect ratio
    const scale = Math.min(
      canvas.width / img.width,
      canvas.height / img.height
    );

    const drawWidth = img.width * scale;
    const drawHeight = img.height * scale;
    const drawX = (canvas.width - drawWidth) / 2;
    const drawY = (canvas.height - drawHeight) / 2;

    // Draw the frame
    ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight);

    // Continue processing buffer
    if (this.settings.bufferFrames > 0) {
      requestAnimationFrame(() => this.processNextFrame());
    }
  }

  updateStatsDisplay() {
    if (!this.settings.showStats) return;

    this.elements.statFps.textContent = this.stats.fps.toFixed(0);
    this.elements.statLatency.textContent = this.stats.latency.toFixed(0);
    this.elements.statSize.textContent = (this.stats.lastSize / 1024).toFixed(
      1
    );
    this.elements.statFrames.textContent = this.stats.totalFrames;
  }

  showStatus(message, type = "") {
    const status = this.elements.connectionStatus;
    status.textContent = message;
    status.className = "status " + type;
  }

  sendQualityRequest() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          type: "quality_request",
          preset: this.settings.qualityPreset,
        })
      );
    }
  }

  // Recent connections management
  loadRecentConnections() {
    try {
      const recent = JSON.parse(
        localStorage.getItem("vr_recent_connections") || "[]"
      );
      this.elements.recentList.innerHTML = "";

      recent.forEach((conn) => {
        const item = document.createElement("div");
        item.className = "recent-item";
        item.textContent = `${conn.ip}:${conn.port}`;
        item.addEventListener("click", () => {
          this.elements.serverIp.value = conn.ip;
          this.elements.serverPort.value = conn.port;
        });
        this.elements.recentList.appendChild(item);
      });
    } catch (e) {
      console.error("Error loading recent connections:", e);
    }
  }

  saveRecentConnection(ip, port) {
    try {
      let recent = JSON.parse(
        localStorage.getItem("vr_recent_connections") || "[]"
      );

      // Remove existing entry for this IP
      recent = recent.filter((conn) => conn.ip !== ip);

      // Add to front
      recent.unshift({ ip, port });

      // Keep only last 5
      recent = recent.slice(0, 5);

      localStorage.setItem("vr_recent_connections", JSON.stringify(recent));
      this.loadRecentConnections();
    } catch (e) {
      console.error("Error saving recent connection:", e);
    }
  }

  // Settings persistence
  loadSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem("vr_settings") || "{}");
      Object.assign(this.settings, saved);

      // Apply to UI
      this.elements.vrMode.value = this.settings.vrMode;
      this.elements.qualityPreset.value = this.settings.qualityPreset;
      this.elements.bufferFrames.value = this.settings.bufferFrames;
      this.elements.bufferValue.textContent = this.settings.bufferFrames;
      this.elements.showStats.checked = this.settings.showStats;
      this.elements.hardwareDecode.checked = this.settings.hardwareDecode;

      this.elements.statsOverlay.style.display = this.settings.showStats
        ? "block"
        : "none";
    } catch (e) {
      console.error("Error loading settings:", e);
    }
  }

  saveSettings() {
    try {
      localStorage.setItem("vr_settings", JSON.stringify(this.settings));
    } catch (e) {
      console.error("Error saving settings:", e);
    }
  }

  // Fullscreen and orientation
  toggleFullscreen() {
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      const elem = document.documentElement;
      if (elem.requestFullscreen) {
        elem.requestFullscreen();
      } else if (elem.webkitRequestFullscreen) {
        elem.webkitRequestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
  }

  lockOrientation() {
    if (screen.orientation && screen.orientation.lock) {
      screen.orientation.lock("landscape").catch((e) => {
        console.log("Orientation lock not supported:", e);
      });
    }
  }

  // Enhanced Wake Lock to keep screen on - multiple fallback methods
  async requestWakeLock() {
    console.log("Requesting wake lock...");

    // Always start all methods for maximum reliability
    this.startNoSleepVideo();
    this.startKeepAwakeInterval();

    // Method 1: Screen Wake Lock API (modern browsers)
    if ("wakeLock" in navigator) {
      try {
        // Release existing lock first
        if (this.wakeLock) {
          await this.wakeLock.release();
        }

        this.wakeLock = await navigator.wakeLock.request("screen");
        console.log("Wake Lock acquired via API");

        // Re-acquire wake lock when it's released (e.g., after tab switch)
        this.wakeLock.addEventListener("release", () => {
          console.log("Wake Lock released, re-acquiring...");
          if (this.screens.viewer.classList.contains("active")) {
            setTimeout(() => this.requestWakeLock(), 100);
          }
        });
      } catch (e) {
        console.log("Wake Lock API error:", e);
      }
    }
  }

  startNoSleepVideo() {
    // Create a tiny video element that plays in loop to prevent sleep
    if (this.noSleepVideo) {
      // Ensure it's playing
      this.noSleepVideo.play().catch(() => {});
      return;
    }

    try {
      this.noSleepVideo = document.createElement("video");
      this.noSleepVideo.setAttribute("playsinline", "");
      this.noSleepVideo.setAttribute("muted", "");
      this.noSleepVideo.muted = true;
      this.noSleepVideo.setAttribute("loop", "");
      this.noSleepVideo.setAttribute("title", "wake lock");
      this.noSleepVideo.style.cssText =
        "position:fixed;left:-100px;top:-100px;width:1px;height:1px;opacity:0.01;pointer-events:none;";

      // Create a proper video blob that works on all browsers
      // This is a minimal MP4 video that loops
      const base64Video =
        "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";

      // Convert base64 to blob
      const byteCharacters = atob(base64Video);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: "video/mp4" });

      this.noSleepVideo.src = URL.createObjectURL(blob);
      document.body.appendChild(this.noSleepVideo);

      // Play and keep trying
      const playVideo = () => {
        this.noSleepVideo
          .play()
          .then(() => {
            console.log("NoSleep video playing");
          })
          .catch((e) => {
            console.log("NoSleep play failed, retrying...", e);
            setTimeout(playVideo, 1000);
          });
      };
      playVideo();
    } catch (e) {
      console.log("NoSleep video error:", e);
    }
  }

  stopNoSleepVideo() {
    if (this.noSleepVideo) {
      this.noSleepVideo.pause();
      this.noSleepVideo.remove();
      this.noSleepVideo = null;
    }
  }

  startKeepAwakeInterval() {
    // Fallback: periodically trigger activity to keep screen on
    if (this.keepAwakeInterval) return;

    this.keepAwakeInterval = setInterval(() => {
      if (this.screens.viewer.classList.contains("active")) {
        // Multiple techniques to signal activity

        // 1. DOM manipulation
        document.body.style.opacity = "0.9999";
        requestAnimationFrame(() => {
          document.body.style.opacity = "1";
        });

        // 2. Trigger a tiny scroll (works on some browsers)
        window.scrollTo(0, window.scrollY === 0 ? 1 : 0);

        // 3. Touch the title
        const originalTitle = document.title;
        document.title = originalTitle + " ";
        setTimeout(() => {
          document.title = originalTitle;
        }, 100);

        // 4. Re-request wake lock periodically
        this.requestWakeLock();
      }
    }, 10000); // Every 10 seconds
    console.log("Keep-awake interval started");
  }

  stopKeepAwakeInterval() {
    if (this.keepAwakeInterval) {
      clearInterval(this.keepAwakeInterval);
      this.keepAwakeInterval = null;
    }
  }

  releaseWakeLock() {
    if (this.wakeLock) {
      this.wakeLock.release();
      this.wakeLock = null;
    }
    this.stopNoSleepVideo();
    this.stopKeepAwakeInterval();
  }
}

// Initialize app when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.vrViewer = new VRStreamViewer();
});

// Handle visibility change to manage wake lock
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && window.vrViewer) {
    window.vrViewer.requestWakeLock();
  }
});

// Request wake lock on any user interaction (helps on iOS)
["touchstart", "touchend", "click", "mousedown"].forEach((eventType) => {
  document.addEventListener(
    eventType,
    () => {
      if (
        window.vrViewer &&
        window.vrViewer.screens.viewer.classList.contains("active")
      ) {
        window.vrViewer.requestWakeLock();
      }
    },
    { passive: true }
  );
});

// Prevent screen dimming by simulating user activity
setInterval(() => {
  if (
    window.vrViewer &&
    window.vrViewer.screens.viewer.classList.contains("active")
  ) {
    // Dispatch a fake user interaction event
    document.dispatchEvent(new Event("mousemove"));
  }
}, 30000);
