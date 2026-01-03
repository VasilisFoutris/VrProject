/**
 * VR Screen Viewer - Mobile Web App
 * High-performance WebSocket client for VR video streaming
 */

// ============================================
// Toast Notification System
// ============================================
class ToastManager {
  constructor() {
    this.container = document.getElementById("toast-container");
    this.toasts = [];
  }

  show(message, type = "info", duration = 3000) {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;

    const icons = {
      success: "✅",
      error: "❌",
      warning: "⚠️",
      info: "ℹ️",
    };

    toast.innerHTML = `
      <span class="toast-icon" aria-hidden="true">${
        icons[type] || icons.info
      }</span>
      <span class="toast-message">${message}</span>
      <button class="toast-close" aria-label="Close notification">&times;</button>
    `;

    // Close button handler
    toast.querySelector(".toast-close").addEventListener("click", () => {
      this.dismiss(toast);
    });

    this.container.appendChild(toast);
    this.toasts.push(toast);

    // Haptic feedback on mobile
    if (navigator.vibrate && type !== "info") {
      navigator.vibrate(type === "error" ? [50, 30, 50] : 50);
    }

    // Auto dismiss
    setTimeout(() => this.dismiss(toast), duration);

    return toast;
  }

  dismiss(toast) {
    if (!toast.parentElement) return;
    toast.style.animation = "toastSlideOut 0.3s ease forwards";
    setTimeout(() => {
      toast.remove();
      this.toasts = this.toasts.filter((t) => t !== toast);
    }, 300);
  }

  success(message, duration) {
    return this.show(message, "success", duration);
  }
  error(message, duration) {
    return this.show(message, "error", duration);
  }
  warning(message, duration) {
    return this.show(message, "warning", duration);
  }
  info(message, duration) {
    return this.show(message, "info", duration);
  }
}

// Global toast instance
const Toast = new ToastManager();

// ============================================
// Theme Manager
// ============================================
class ThemeManager {
  constructor() {
    this.currentTheme = this.getInitialTheme();
    this.toggleBtn = document.getElementById("theme-toggle");
    this.themeSelect = document.getElementById("theme-select");
    this.init();
  }

  getInitialTheme() {
    const saved = localStorage.getItem("vr-theme");
    if (saved) return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  init() {
    // Apply initial theme
    this.apply(this.currentTheme);

    // Toggle button handler
    if (this.toggleBtn) {
      this.toggleBtn.addEventListener("click", () => {
        this.toggle();
        // Haptic feedback
        if (navigator.vibrate) navigator.vibrate(30);
      });
    }

    // Settings dropdown handler
    if (this.themeSelect) {
      this.themeSelect.value =
        localStorage.getItem("vr-theme-preference") || "system";
      this.themeSelect.addEventListener("change", (e) => {
        const preference = e.target.value;
        localStorage.setItem("vr-theme-preference", preference);

        if (preference === "system") {
          const systemTheme = window.matchMedia("(prefers-color-scheme: dark)")
            .matches
            ? "dark"
            : "light";
          this.apply(systemTheme);
        } else {
          this.apply(preference);
        }
      });
    }

    // Listen for system theme changes
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", (e) => {
        const preference = localStorage.getItem("vr-theme-preference");
        if (!preference || preference === "system") {
          this.apply(e.matches ? "dark" : "light");
        }
      });
  }

  toggle() {
    this.currentTheme = this.currentTheme === "dark" ? "light" : "dark";
    this.apply(this.currentTheme);
    localStorage.setItem("vr-theme-preference", this.currentTheme);
    if (this.themeSelect) this.themeSelect.value = this.currentTheme;
  }

  apply(theme) {
    this.currentTheme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("vr-theme", theme);

    // Update toggle button icon
    if (this.toggleBtn) {
      const toggle = this.toggleBtn.querySelector(".theme-toggle");
      if (toggle) {
        toggle.querySelector(".icon").textContent =
          theme === "dark" ? "🌙" : "☀️";
        toggle.querySelector(".label").textContent =
          theme === "dark" ? "Dark" : "Light";
      }
    }

    // Update theme-color meta tag
    const themeColors = { dark: "#1a1a2e", light: "#f5f5f5" };
    const metaTheme = document.getElementById("theme-color-meta");
    if (metaTheme) metaTheme.setAttribute("content", themeColors[theme]);
  }
}

// ============================================
// Connection Health Monitor
// ============================================
class ConnectionHealthMonitor {
  constructor() {
    this.element = document.getElementById("connection-health");
    this.latencyHistory = [];
    this.maxHistory = 20;
    this.thresholds = {
      excellent: 30, // < 30ms
      good: 60, // < 60ms
      fair: 100, // < 100ms
      poor: Infinity, // >= 100ms
    };
  }

  update(latency) {
    this.latencyHistory.push(latency);
    if (this.latencyHistory.length > this.maxHistory) {
      this.latencyHistory.shift();
    }

    const avgLatency =
      this.latencyHistory.reduce((a, b) => a + b, 0) /
      this.latencyHistory.length;
    let health = "poor";

    if (avgLatency < this.thresholds.excellent) health = "excellent";
    else if (avgLatency < this.thresholds.good) health = "good";
    else if (avgLatency < this.thresholds.fair) health = "fair";

    if (this.element) {
      this.element.className = `overlay connection-health ${health}`;
      this.element.querySelector(".health-label").textContent =
        health.charAt(0).toUpperCase() + health.slice(1);
    }

    return health;
  }

  reset() {
    this.latencyHistory = [];
    if (this.element) {
      this.element.className = "overlay connection-health";
      this.element.querySelector(".health-label").textContent = "Connecting...";
    }
  }
}

// ============================================
// Gyroscope Manager (for VR alignment)
// ============================================
class GyroscopeManager {
  constructor() {
    this.element = document.getElementById("gyro-indicator");
    this.icon = this.element?.querySelector(".gyro-icon");
    this.status = this.element?.querySelector(".gyro-status");
    this.hasPermission = false;
    this.isActive = false;
  }

  async requestPermission() {
    // iOS 13+ requires permission
    if (
      typeof DeviceOrientationEvent !== "undefined" &&
      typeof DeviceOrientationEvent.requestPermission === "function"
    ) {
      try {
        const permission = await DeviceOrientationEvent.requestPermission();
        this.hasPermission = permission === "granted";
      } catch (e) {
        console.warn("Gyroscope permission denied:", e);
        this.hasPermission = false;
      }
    } else {
      // Non-iOS or older browsers
      this.hasPermission = true;
    }
    return this.hasPermission;
  }

  start() {
    if (!this.hasPermission) return;

    this.isActive = true;
    if (this.element) {
      this.element.classList.remove("hidden");
      this.element.classList.add("active");
    }

    window.addEventListener(
      "deviceorientation",
      this.handleOrientation.bind(this)
    );
  }

  stop() {
    this.isActive = false;
    if (this.element) {
      this.element.classList.add("hidden");
      this.element.classList.remove("active");
    }
    window.removeEventListener(
      "deviceorientation",
      this.handleOrientation.bind(this)
    );
  }

  handleOrientation(event) {
    if (!this.isActive || !this.icon) return;

    // Rotate icon based on device orientation
    const gamma = event.gamma || 0; // Left-right tilt
    this.icon.style.transform = `rotate(${gamma}deg)`;

    // Update status based on orientation
    const isLevel = Math.abs(gamma) < 5;
    if (this.status) {
      this.status.textContent = isLevel ? "Level ✓" : "Tilt to level";
      this.status.style.color = isLevel ? "var(--success)" : "var(--warning)";
    }
  }
}

// ============================================
// Haptic Feedback Utility
// ============================================
const Haptics = {
  light: () => navigator.vibrate?.(10),
  medium: () => navigator.vibrate?.(30),
  heavy: () => navigator.vibrate?.(50),
  success: () => navigator.vibrate?.([30, 50, 30]),
  error: () => navigator.vibrate?.([50, 30, 50, 30, 50]),
  warning: () => navigator.vibrate?.([30, 30, 30]),
};

// ============================================
// Main VR Stream Viewer Class
// ============================================
class VRStreamViewer {
  constructor() {
    // Initialize managers
    this.themeManager = new ThemeManager();
    this.healthMonitor = new ConnectionHealthMonitor();
    this.gyroscope = new GyroscopeManager();

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
      connectionForm: document.getElementById("connection-form"),
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
      themeSelect: document.getElementById("theme-select"),
      qualityPreset: document.getElementById("quality-preset"),
      bufferFrames: document.getElementById("buffer-frames"),
      bufferValue: document.getElementById("buffer-value"),
      showStats: document.getElementById("show-stats"),
      hardwareDecode: document.getElementById("hardware-decode"),
      fullscreenBtn: document.getElementById("fullscreen-btn"),
      orientationBtn: document.getElementById("orientation-btn"),
      backToConnection: document.getElementById("back-to-connection"),
    };

    // Canvas context - use willReadFrequently:false for GPU-accelerated rendering
    this.ctx = this.elements.canvas.getContext("2d", {
      alpha: false,
      desynchronized: true, // Reduce latency - decouples canvas from event loop
      willReadFrequently: false, // Optimize for drawing, not reading
    });

    // Create offscreen canvas for double-buffering (prevents jitter/tearing)
    this.offscreenCanvas = document.createElement("canvas");
    this.offscreenCtx = this.offscreenCanvas.getContext("2d", {
      alpha: false,
      willReadFrequently: false,
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
      theme: "system",
    };

    // Frame buffer for smoother playback
    this.frameBuffer = [];
    this.isProcessingFrame = false;

    // Pending frame for synchronized rendering (prevents jitter)
    this.pendingFrame = null;
    this.frameReady = false;
    this.renderScheduled = false;

    // Reusable Image for decoding (legacy fallback)
    this.frameImage = new Image();
    this.frameImage.onload = () => this.onFrameImageLoaded();

    // Track current blob URL for cleanup
    this.currentFrameUrl = null;

    // Initialize
    this.init();
  }

  init() {
    this.loadSettings();
    this.loadRecentConnections();
    this.setupEventListeners();
    this.resizeCanvas();
    this.setupAccessibility();

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

    // Quick connect from PWA shortcut
    if (urlParams.has("quickconnect")) {
      const recent = this.getRecentConnections();
      if (recent.length > 0) {
        this.elements.serverIp.value = recent[0].ip;
        this.elements.serverPort.value = recent[0].port;
        setTimeout(() => this.connect(), 500);
      }
    }

    // Resize canvas on window resize
    window.addEventListener("resize", () => this.resizeCanvas());
    window.addEventListener("orientationchange", () => {
      setTimeout(() => this.resizeCanvas(), 100);
    });

    // Request gyroscope permission on first interaction
    document.addEventListener(
      "click",
      async () => {
        if (!this.gyroscope.hasPermission) {
          await this.gyroscope.requestPermission();
        }
      },
      { once: true }
    );
  }

  setupAccessibility() {
    // Keyboard navigation for recent connections
    document.addEventListener("keydown", (e) => {
      // Escape key to go back
      if (e.key === "Escape") {
        if (this.screens.settings.classList.contains("active")) {
          this.showConnectionScreen();
        } else if (this.screens.viewer.classList.contains("active")) {
          this.disconnect();
        }
      }
    });
  }

  setupEventListeners() {
    // Connection form submission (prevents default and handles connect)
    if (this.elements.connectionForm) {
      this.elements.connectionForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.connect();
      });
    }

    // Connection button with haptic feedback
    this.elements.connectBtn.addEventListener("click", (e) => {
      // Only handle if not a form submit
      if (!this.elements.connectionForm) {
        Haptics.medium();
        this.connect();
      }
    });

    this.elements.serverIp.addEventListener("keypress", (e) => {
      if (e.key === "Enter" && !this.elements.connectionForm) {
        this.connect();
      }
    });

    // Viewer controls with haptic feedback
    this.elements.disconnectBtn.addEventListener("click", () => {
      Haptics.medium();
      this.disconnect();
    });
    this.elements.settingsBtn.addEventListener("click", () => {
      Haptics.light();
      this.showSettings();
    });
    this.elements.fullscreenViewerBtn.addEventListener("click", () => {
      Haptics.light();
      this.toggleFullscreen();
    });
    this.elements.reconnectBtn.addEventListener("click", () => {
      Haptics.medium();
      this.reconnect();
    });

    // Settings with haptic feedback
    this.elements.vrMode.addEventListener("change", (e) => {
      Haptics.light();
      this.settings.vrMode = e.target.value;
      this.saveSettings();
      Toast.success("VR mode updated");
    });

    this.elements.qualityPreset.addEventListener("change", (e) => {
      Haptics.light();
      this.settings.qualityPreset = e.target.value;
      this.sendQualityRequest();
      this.saveSettings();
      Toast.success("Quality preset updated");
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

    // Sync offscreen canvas size for double-buffering
    this.offscreenCanvas.width = canvas.width;
    this.offscreenCanvas.height = canvas.height;

    // Optimize for mobile - low quality for speed, reduce jitter
    this.ctx.imageSmoothingEnabled = true;
    this.ctx.imageSmoothingQuality = "low"; // Fast rendering
    this.offscreenCtx.imageSmoothingEnabled = true;
    this.offscreenCtx.imageSmoothingQuality = "low";
  }

  connect() {
    const ip = this.elements.serverIp.value.trim();
    const port = this.elements.serverPort.value.trim();

    if (!ip) {
      this.showStatus("Please enter the PC IP address", "error");
      Toast.warning("Please enter a valid IP address");
      Haptics.warning();
      return;
    }

    const url = `ws://${ip}:${port}`;
    this.showStatus("Connecting...", "connecting");
    this.elements.connectBtn.disabled = true;
    this.elements.connectBtn.classList.add("btn-loading");
    this.healthMonitor.reset();

    try {
      this.ws = new WebSocket(url);
      this.ws.binaryType = "blob"; // Receive as blob for faster handling

      this.ws.onopen = () => {
        console.log("WebSocket connected");
        this.showStatus("Connected!", "success");
        this.saveRecentConnection(ip, port);
        this.reconnectAttempts = 0;

        Toast.success(`Connected to ${ip}`);
        Haptics.success();
        this.elements.connectBtn.classList.remove("btn-loading");

        setTimeout(() => {
          this.showViewer();
          this.requestWakeLock();
          // Start gyroscope for VR alignment
          if (this.gyroscope.hasPermission) {
            this.gyroscope.start();
          }
        }, 500);
      };

      this.ws.onmessage = (event) => this.handleMessage(event);

      this.ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        this.showStatus("Connection failed", "error");
        this.elements.connectBtn.disabled = false;
        this.elements.connectBtn.classList.remove("btn-loading");
        Toast.error("Connection failed - check IP address");
        Haptics.error();
      };

      this.ws.onclose = () => {
        console.log("WebSocket closed");
        if (this.screens.viewer.classList.contains("active")) {
          this.handleDisconnect();
        }
        this.elements.connectBtn.disabled = false;
        this.elements.connectBtn.classList.remove("btn-loading");
      };
    } catch (error) {
      console.error("Connection error:", error);
      this.showStatus("Invalid address", "error");
      this.elements.connectBtn.disabled = false;
      this.elements.connectBtn.classList.remove("btn-loading");
      Toast.error("Invalid address format");
      Haptics.error();
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.gyroscope.stop();
    this.showConnectionScreen();
    this.releaseWakeLock();
    Toast.info("Disconnected");
  }

  handleDisconnect() {
    this.elements.connectionLost.classList.remove("hidden");
    Toast.warning("Connection lost - attempting to reconnect...");
    Haptics.warning();
    this.gyroscope.stop();

    // Auto-reconnect
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      setTimeout(() => this.reconnect(), this.reconnectDelay);
    } else {
      Toast.error("Failed to reconnect after multiple attempts");
    }
  }

  reconnect() {
    this.reconnectAttempts++;
    this.elements.connectionLost.classList.add("hidden");
    Toast.info(
      `Reconnecting... (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    );
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
    // Use createImageBitmap for GPU-accelerated decoding (prevents jitter)
    // This decodes the JPEG using hardware acceleration where available
    if (typeof createImageBitmap === "function") {
      createImageBitmap(blob, {
        premultiplyAlpha: "none",
        colorSpaceConversion: "none", // Skip color conversion for speed
      })
        .then((bitmap) => {
          // Store the decoded bitmap for synchronized rendering
          if (this.pendingFrame && this.pendingFrame.close) {
            this.pendingFrame.close(); // Release previous bitmap
          }
          this.pendingFrame = bitmap;
          this.frameReady = true;

          // Schedule render on next animation frame for smooth timing
          if (!this.renderScheduled) {
            this.renderScheduled = true;
            requestAnimationFrame(() => this.renderFrame());
          }
        })
        .catch((e) => {
          // Fallback to Image element if createImageBitmap fails
          console.warn("ImageBitmap failed, using fallback:", e);
          this.displayFrameFallback(blob);
        });
    } else {
      // Fallback for older browsers without createImageBitmap
      this.displayFrameFallback(blob);
    }
  }

  displayFrameFallback(blob) {
    // Legacy fallback using Image element
    const url = URL.createObjectURL(blob);

    // Clean up previous URL
    if (this.currentFrameUrl) {
      URL.revokeObjectURL(this.currentFrameUrl);
    }
    this.currentFrameUrl = url;

    // Load and display
    this.frameImage.src = url;
  }

  onFrameImageLoaded() {
    // Called when legacy Image element has loaded
    // Draw directly without double-buffering for fallback
    this.drawFrameLegacy();
  }

  renderFrame() {
    this.renderScheduled = false;

    if (!this.frameReady || !this.pendingFrame) {
      // No frame ready, continue processing buffer
      if (this.settings.bufferFrames > 0 && this.frameBuffer.length > 0) {
        this.processNextFrame();
      }
      return;
    }

    this.frameReady = false;
    const bitmap = this.pendingFrame;

    const canvas = this.elements.canvas;
    const offCanvas = this.offscreenCanvas;
    const offCtx = this.offscreenCtx;

    // Draw to offscreen canvas first (double-buffering prevents flicker)
    offCtx.fillStyle = "#000";
    offCtx.fillRect(0, 0, offCanvas.width, offCanvas.height);

    // Calculate scaling to fit canvas while maintaining aspect ratio
    const scale = Math.min(
      offCanvas.width / bitmap.width,
      offCanvas.height / bitmap.height
    );

    const drawWidth = bitmap.width * scale;
    const drawHeight = bitmap.height * scale;
    const drawX = (offCanvas.width - drawWidth) / 2;
    const drawY = (offCanvas.height - drawHeight) / 2;

    // Draw to offscreen canvas
    offCtx.drawImage(bitmap, drawX, drawY, drawWidth, drawHeight);

    // Atomic copy to visible canvas (prevents tearing/jitter)
    this.ctx.drawImage(offCanvas, 0, 0);

    // Continue processing buffer
    if (this.settings.bufferFrames > 0) {
      requestAnimationFrame(() => this.processNextFrame());
    } else {
      this.isProcessingFrame = false;
    }
  }

  drawFrameLegacy() {
    // Legacy draw method for browsers without createImageBitmap
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

    // Update connection health indicator
    this.healthMonitor.update(this.stats.latency);
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
      recent.unshift({ ip, port, lastUsed: Date.now() });

      // Keep only last 5
      recent = recent.slice(0, 5);

      localStorage.setItem("vr_recent_connections", JSON.stringify(recent));
      this.loadRecentConnections();
    } catch (e) {
      console.error("Error saving recent connection:", e);
    }
  }

  getRecentConnections() {
    try {
      return JSON.parse(localStorage.getItem("vr_recent_connections") || "[]");
    } catch (e) {
      return [];
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
