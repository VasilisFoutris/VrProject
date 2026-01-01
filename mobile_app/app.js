/**
 * VR Screen Viewer - Mobile Web App
 * High-performance WebSocket client for VR video streaming
 */

class VRStreamViewer {
    constructor() {
        // DOM Elements
        this.screens = {
            connection: document.getElementById('connection-screen'),
            settings: document.getElementById('settings-screen'),
            viewer: document.getElementById('viewer-screen')
        };
        
        this.elements = {
            serverIp: document.getElementById('server-ip'),
            serverPort: document.getElementById('server-port'),
            connectBtn: document.getElementById('connect-btn'),
            connectionStatus: document.getElementById('connection-status'),
            recentList: document.getElementById('recent-list'),
            canvas: document.getElementById('vr-canvas'),
            
            // Stats
            statFps: document.getElementById('stat-fps'),
            statLatency: document.getElementById('stat-latency'),
            statSize: document.getElementById('stat-size'),
            statFrames: document.getElementById('stat-frames'),
            statsOverlay: document.getElementById('stats-overlay'),
            
            // Controls
            disconnectBtn: document.getElementById('disconnect-btn'),
            settingsBtn: document.getElementById('settings-btn'),
            fullscreenViewerBtn: document.getElementById('fullscreen-viewer-btn'),
            reconnectBtn: document.getElementById('reconnect-btn'),
            connectionLost: document.getElementById('connection-lost'),
            
            // Settings
            vrMode: document.getElementById('vr-mode'),
            qualityPreset: document.getElementById('quality-preset'),
            bufferFrames: document.getElementById('buffer-frames'),
            bufferValue: document.getElementById('buffer-value'),
            showStats: document.getElementById('show-stats'),
            hardwareDecode: document.getElementById('hardware-decode'),
            fullscreenBtn: document.getElementById('fullscreen-btn'),
            orientationBtn: document.getElementById('orientation-btn'),
            backToConnection: document.getElementById('back-to-connection')
        };
        
        // Canvas context
        this.ctx = this.elements.canvas.getContext('2d', {
            alpha: false,
            desynchronized: true  // Reduce latency
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
            fpsUpdateTime: Date.now()
        };
        
        // Settings
        this.settings = {
            vrMode: 'sbs',
            qualityPreset: 'auto',
            bufferFrames: 1,
            showStats: true,
            hardwareDecode: true
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
        if (urlParams.has('ip')) {
            this.elements.serverIp.value = urlParams.get('ip');
        } else if (window.location.hostname && window.location.hostname !== 'localhost') {
            this.elements.serverIp.value = window.location.hostname;
        }
        
        // Resize canvas on window resize
        window.addEventListener('resize', () => this.resizeCanvas());
        window.addEventListener('orientationchange', () => {
            setTimeout(() => this.resizeCanvas(), 100);
        });
    }
    
    setupEventListeners() {
        // Connection
        this.elements.connectBtn.addEventListener('click', () => this.connect());
        this.elements.serverIp.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.connect();
        });
        
        // Viewer controls
        this.elements.disconnectBtn.addEventListener('click', () => this.disconnect());
        this.elements.settingsBtn.addEventListener('click', () => this.showSettings());
        this.elements.fullscreenViewerBtn.addEventListener('click', () => this.toggleFullscreen());
        this.elements.reconnectBtn.addEventListener('click', () => this.reconnect());
        
        // Settings
        this.elements.vrMode.addEventListener('change', (e) => {
            this.settings.vrMode = e.target.value;
            this.saveSettings();
        });
        
        this.elements.qualityPreset.addEventListener('change', (e) => {
            this.settings.qualityPreset = e.target.value;
            this.sendQualityRequest();
            this.saveSettings();
        });
        
        this.elements.bufferFrames.addEventListener('input', (e) => {
            this.settings.bufferFrames = parseInt(e.target.value);
            this.elements.bufferValue.textContent = e.target.value;
            this.saveSettings();
        });
        
        this.elements.showStats.addEventListener('change', (e) => {
            this.settings.showStats = e.target.checked;
            this.elements.statsOverlay.style.display = e.target.checked ? 'block' : 'none';
            this.saveSettings();
        });
        
        this.elements.hardwareDecode.addEventListener('change', (e) => {
            this.settings.hardwareDecode = e.target.checked;
            this.saveSettings();
        });
        
        this.elements.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
        this.elements.orientationBtn.addEventListener('click', () => this.lockOrientation());
        this.elements.backToConnection.addEventListener('click', () => this.showConnectionScreen());
        
        // Touch to show/hide controls
        let touchTimeout;
        this.elements.canvas.addEventListener('touchstart', () => {
            document.getElementById('controls-overlay').style.opacity = '1';
            clearTimeout(touchTimeout);
            touchTimeout = setTimeout(() => {
                document.getElementById('controls-overlay').style.opacity = '0';
            }, 3000);
        });
    }
    
    showScreen(screenName) {
        Object.values(this.screens).forEach(screen => screen.classList.remove('active'));
        this.screens[screenName].classList.add('active');
    }
    
    showConnectionScreen() {
        this.showScreen('connection');
    }
    
    showSettings() {
        this.showScreen('settings');
    }
    
    showViewer() {
        this.showScreen('viewer');
        this.resizeCanvas();
    }
    
    resizeCanvas() {
        const canvas = this.elements.canvas;
        const container = this.screens.viewer;
        
        canvas.width = container.clientWidth || window.innerWidth;
        canvas.height = container.clientHeight || window.innerHeight;
        
        // Optimize for mobile
        this.ctx.imageSmoothingEnabled = true;
        this.ctx.imageSmoothingQuality = 'low';  // Fast rendering
    }
    
    connect() {
        const ip = this.elements.serverIp.value.trim();
        const port = this.elements.serverPort.value.trim();
        
        if (!ip) {
            this.showStatus('Please enter the PC IP address', 'error');
            return;
        }
        
        const url = `ws://${ip}:${port}`;
        this.showStatus('Connecting...', 'connecting');
        this.elements.connectBtn.disabled = true;
        
        try {
            this.ws = new WebSocket(url);
            this.ws.binaryType = 'blob';  // Receive as blob for faster handling
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.showStatus('Connected!', 'success');
                this.saveRecentConnection(ip, port);
                this.reconnectAttempts = 0;
                
                setTimeout(() => {
                    this.showViewer();
                    this.requestWakeLock();
                }, 500);
            };
            
            this.ws.onmessage = (event) => this.handleMessage(event);
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.showStatus('Connection failed', 'error');
                this.elements.connectBtn.disabled = false;
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket closed');
                if (this.screens.viewer.classList.contains('active')) {
                    this.handleDisconnect();
                }
                this.elements.connectBtn.disabled = false;
            };
            
        } catch (error) {
            console.error('Connection error:', error);
            this.showStatus('Invalid address', 'error');
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
        this.elements.connectionLost.classList.remove('hidden');
        
        // Auto-reconnect
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            setTimeout(() => this.reconnect(), this.reconnectDelay);
        }
    }
    
    reconnect() {
        this.reconnectAttempts++;
        this.elements.connectionLost.classList.add('hidden');
        this.connect();
    }
    
    handleMessage(event) {
        const receiveTime = performance.now();
        
        // Check if it's a text message (config/ping) or binary (frame)
        if (typeof event.data === 'string') {
            try {
                const msg = JSON.parse(event.data);
                this.handleControlMessage(msg);
            } catch (e) {
                console.error('Invalid JSON message:', e);
            }
            return;
        }
        
        // Binary frame data
        this.processFrame(event.data, receiveTime);
    }
    
    handleControlMessage(msg) {
        switch (msg.type) {
            case 'config':
                console.log('Received server config:', msg);
                break;
                
            case 'ping':
                // Respond with pong
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: 'pong',
                        sent_time: msg.sent_time
                    }));
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
        ctx.fillStyle = '#000';
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
        this.elements.statSize.textContent = (this.stats.lastSize / 1024).toFixed(1);
        this.elements.statFrames.textContent = this.stats.totalFrames;
    }
    
    showStatus(message, type = '') {
        const status = this.elements.connectionStatus;
        status.textContent = message;
        status.className = 'status ' + type;
    }
    
    sendQualityRequest() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'quality_request',
                preset: this.settings.qualityPreset
            }));
        }
    }
    
    // Recent connections management
    loadRecentConnections() {
        try {
            const recent = JSON.parse(localStorage.getItem('vr_recent_connections') || '[]');
            this.elements.recentList.innerHTML = '';
            
            recent.forEach(conn => {
                const item = document.createElement('div');
                item.className = 'recent-item';
                item.textContent = `${conn.ip}:${conn.port}`;
                item.addEventListener('click', () => {
                    this.elements.serverIp.value = conn.ip;
                    this.elements.serverPort.value = conn.port;
                });
                this.elements.recentList.appendChild(item);
            });
        } catch (e) {
            console.error('Error loading recent connections:', e);
        }
    }
    
    saveRecentConnection(ip, port) {
        try {
            let recent = JSON.parse(localStorage.getItem('vr_recent_connections') || '[]');
            
            // Remove existing entry for this IP
            recent = recent.filter(conn => conn.ip !== ip);
            
            // Add to front
            recent.unshift({ ip, port });
            
            // Keep only last 5
            recent = recent.slice(0, 5);
            
            localStorage.setItem('vr_recent_connections', JSON.stringify(recent));
            this.loadRecentConnections();
        } catch (e) {
            console.error('Error saving recent connection:', e);
        }
    }
    
    // Settings persistence
    loadSettings() {
        try {
            const saved = JSON.parse(localStorage.getItem('vr_settings') || '{}');
            Object.assign(this.settings, saved);
            
            // Apply to UI
            this.elements.vrMode.value = this.settings.vrMode;
            this.elements.qualityPreset.value = this.settings.qualityPreset;
            this.elements.bufferFrames.value = this.settings.bufferFrames;
            this.elements.bufferValue.textContent = this.settings.bufferFrames;
            this.elements.showStats.checked = this.settings.showStats;
            this.elements.hardwareDecode.checked = this.settings.hardwareDecode;
            
            this.elements.statsOverlay.style.display = this.settings.showStats ? 'block' : 'none';
        } catch (e) {
            console.error('Error loading settings:', e);
        }
    }
    
    saveSettings() {
        try {
            localStorage.setItem('vr_settings', JSON.stringify(this.settings));
        } catch (e) {
            console.error('Error saving settings:', e);
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
            screen.orientation.lock('landscape').catch(e => {
                console.log('Orientation lock not supported:', e);
            });
        }
    }
    
    // Wake lock to keep screen on
    async requestWakeLock() {
        if ('wakeLock' in navigator) {
            try {
                this.wakeLock = await navigator.wakeLock.request('screen');
                console.log('Wake Lock acquired');
            } catch (e) {
                console.log('Wake Lock error:', e);
            }
        }
    }
    
    releaseWakeLock() {
        if (this.wakeLock) {
            this.wakeLock.release();
            this.wakeLock = null;
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.vrViewer = new VRStreamViewer();
});

// Handle visibility change to manage wake lock
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && window.vrViewer) {
        window.vrViewer.requestWakeLock();
    }
});
