"""
VR Screen Streamer - Streaming Server Module
WebSocket server for low-latency video streaming to mobile clients.
"""

import asyncio
import json
import time
import socket
from typing import Set, Dict, Optional, Callable, Any
from dataclasses import dataclass, asdict
import websockets
from websockets.server import WebSocketServerProtocol
import threading
from concurrent.futures import ThreadPoolExecutor
import struct

from config import NetworkConfig, Config


@dataclass
class ClientInfo:
    """Information about a connected client"""
    id: str
    address: str
    connected_at: float
    frames_sent: int = 0
    bytes_sent: int = 0
    last_ping: float = 0
    latency_ms: float = 0


@dataclass
class StreamStats:
    """Streaming statistics"""
    total_frames_sent: int = 0
    total_bytes_sent: int = 0
    connected_clients: int = 0
    current_fps: float = 0.0
    average_latency_ms: float = 0.0
    start_time: float = 0.0
    
    def to_dict(self) -> Dict:
        return asdict(self)


class StreamingServer:
    """WebSocket server for streaming video frames to VR clients"""
    
    def __init__(self, config: NetworkConfig):
        self.config = config
        self.clients: Dict[str, tuple[WebSocketServerProtocol, ClientInfo]] = {}
        self.stats = StreamStats()
        self.stats.start_time = time.time()
        
        # Current frame to broadcast
        self._current_frame: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        self._frame_event = asyncio.Event()
        
        # Server state
        self._running = False
        self._server = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Callbacks
        self._on_client_connect: Optional[Callable[[ClientInfo], None]] = None
        self._on_client_disconnect: Optional[Callable[[ClientInfo], None]] = None
        self._on_stats_update: Optional[Callable[[StreamStats], None]] = None
        
        # Frame rate tracking
        self._frame_count = 0
        self._fps_start_time = time.time()
        
        # Server IP
        self._server_ip = self._get_local_ip()
    
    def _get_local_ip(self) -> str:
        """Get local IP address for LAN connections"""
        if self.config.static_ip:
            return self.config.static_ip
        
        try:
            # Create a dummy connection to get local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def get_server_ip(self) -> str:
        """Get the server's IP address"""
        return self._server_ip
    
    def get_connection_url(self) -> str:
        """Get the WebSocket URL for clients to connect"""
        return f"ws://{self._server_ip}:{self.config.port}"
    
    def set_callbacks(
        self,
        on_connect: Optional[Callable[[ClientInfo], None]] = None,
        on_disconnect: Optional[Callable[[ClientInfo], None]] = None,
        on_stats: Optional[Callable[[StreamStats], None]] = None
    ):
        """Set event callbacks"""
        self._on_client_connect = on_connect
        self._on_client_disconnect = on_disconnect
        self._on_stats_update = on_stats
    
    async def _handle_client(self, websocket: WebSocketServerProtocol):
        """Handle a connected client"""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        client_info = ClientInfo(
            id=client_id,
            address=websocket.remote_address[0],
            connected_at=time.time()
        )
        
        self.clients[client_id] = (websocket, client_info)
        self.stats.connected_clients = len(self.clients)
        
        print(f"[Server] Client connected: {client_id}")
        
        if self._on_client_connect:
            self._on_client_connect(client_info)
        
        try:
            # Send initial configuration to client
            await self._send_config(websocket)
            
            # Handle incoming messages (for ping/pong and commands)
            async for message in websocket:
                await self._handle_message(client_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            print(f"[Server] Client disconnected: {client_id}")
        except Exception as e:
            print(f"[Server] Client error: {e}")
        finally:
            if client_id in self.clients:
                _, info = self.clients.pop(client_id)
                self.stats.connected_clients = len(self.clients)
                if self._on_client_disconnect:
                    self._on_client_disconnect(info)
    
    async def _send_config(self, websocket: WebSocketServerProtocol):
        """Send server configuration to client"""
        config_msg = {
            'type': 'config',
            'server_time': time.time(),
            'server_ip': self._server_ip,
        }
        await websocket.send(json.dumps(config_msg))
    
    async def _handle_message(self, client_id: str, message: str):
        """Handle incoming message from client"""
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')
            
            if msg_type == 'pong':
                # Update latency measurement
                if client_id in self.clients:
                    _, client_info = self.clients[client_id]
                    sent_time = data.get('sent_time', 0)
                    client_info.latency_ms = (time.time() - sent_time) * 1000 / 2
                    client_info.last_ping = time.time()
            
            elif msg_type == 'quality_request':
                # Client requesting quality change (handled by GUI)
                quality = data.get('quality', 75)
                print(f"[Server] Client {client_id} requested quality: {quality}")
            
        except json.JSONDecodeError:
            pass
    
    async def _broadcast_frames(self):
        """Continuously broadcast frames to all connected clients"""
        while self._running:
            # Wait for new frame
            try:
                await asyncio.wait_for(self._frame_event.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            
            self._frame_event.clear()
            
            with self._frame_lock:
                frame_data = self._current_frame
            
            if frame_data is None:
                continue
            
            # Broadcast to all clients
            disconnected = []
            
            for client_id, (websocket, client_info) in list(self.clients.items()):
                try:
                    # Send frame as binary
                    await websocket.send(frame_data)
                    
                    client_info.frames_sent += 1
                    client_info.bytes_sent += len(frame_data)
                    
                    self.stats.total_frames_sent += 1
                    self.stats.total_bytes_sent += len(frame_data)
                    
                except websockets.exceptions.ConnectionClosed:
                    disconnected.append(client_id)
                except Exception as e:
                    print(f"[Server] Send error to {client_id}: {e}")
                    disconnected.append(client_id)
            
            # Clean up disconnected clients
            for client_id in disconnected:
                if client_id in self.clients:
                    _, info = self.clients.pop(client_id)
                    self.stats.connected_clients = len(self.clients)
                    if self._on_client_disconnect:
                        self._on_client_disconnect(info)
            
            # Update FPS
            self._frame_count += 1
            elapsed = time.time() - self._fps_start_time
            if elapsed >= 1.0:
                self.stats.current_fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_start_time = time.time()
                
                if self._on_stats_update:
                    self._on_stats_update(self.stats)
    
    async def _ping_clients(self):
        """Periodically ping clients to measure latency"""
        while self._running:
            await asyncio.sleep(self.config.ping_interval)
            
            ping_msg = json.dumps({
                'type': 'ping',
                'sent_time': time.time()
            })
            
            for client_id, (websocket, _) in list(self.clients.items()):
                try:
                    await websocket.send(ping_msg)
                except:
                    pass
    
    async def _run_server(self):
        """Main server loop"""
        print(f"[Server] Starting on ws://{self.config.host}:{self.config.port}")
        print(f"[Server] Clients can connect to: {self.get_connection_url()}")
        
        async with websockets.serve(
            self._handle_client,
            self.config.host,
            self.config.port,
            max_size=10 * 1024 * 1024,  # 10MB max message
            ping_interval=None,  # We handle our own pings
            ping_timeout=None,
        ) as server:
            self._server = server
            self._running = True
            
            # Run frame broadcaster and ping tasks
            await asyncio.gather(
                self._broadcast_frames(),
                self._ping_clients(),
            )
    
    def push_frame(self, frame_data: bytes):
        """Push a new frame to be broadcast to clients"""
        with self._frame_lock:
            self._current_frame = frame_data
        
        # Signal that new frame is available
        if self._loop:
            self._loop.call_soon_threadsafe(self._frame_event.set)
    
    def start(self):
        """Start the server in a background thread"""
        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run_server())
            except Exception as e:
                print(f"[Server] Error: {e}")
            finally:
                self._loop.close()
        
        self._server_thread = threading.Thread(target=run, daemon=True)
        self._server_thread.start()
    
    def stop(self):
        """Stop the server"""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
    
    def get_stats(self) -> StreamStats:
        """Get current streaming statistics"""
        return self.stats
    
    def get_client_count(self) -> int:
        """Get number of connected clients"""
        return len(self.clients)


# HTTP server for serving the mobile web app
class HTTPServer:
    """Simple HTTP server to serve the mobile web app"""
    
    def __init__(self, port: int, web_root: str):
        self.port = port
        self.web_root = web_root
        self._running = False
    
    async def handle_request(self, reader, writer):
        """Handle HTTP request"""
        import os
        
        try:
            request_line = await reader.readline()
            request = request_line.decode('utf-8').strip()
            
            # Parse request
            parts = request.split(' ')
            if len(parts) >= 2:
                path = parts[1]
            else:
                path = '/'
            
            # Read headers
            while True:
                line = await reader.readline()
                if line == b'\r\n' or line == b'':
                    break
            
            # Determine file to serve
            if path == '/':
                path = '/index.html'
            
            file_path = os.path.join(self.web_root, path.lstrip('/'))
            
            if os.path.exists(file_path) and os.path.isfile(file_path):
                # Determine content type
                if path.endswith('.html'):
                    content_type = 'text/html'
                elif path.endswith('.css'):
                    content_type = 'text/css'
                elif path.endswith('.js'):
                    content_type = 'application/javascript'
                else:
                    content_type = 'application/octet-stream'
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                response = f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\nContent-Length: {len(content)}\r\n\r\n"
                writer.write(response.encode() + content)
            else:
                response = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                writer.write(response.encode())
            
            await writer.drain()
            writer.close()
            
        except Exception as e:
            print(f"[HTTP] Error: {e}")
    
    async def run(self):
        """Run the HTTP server"""
        server = await asyncio.start_server(
            self.handle_request,
            '0.0.0.0',
            self.port
        )
        
        print(f"[HTTP] Serving web app on http://0.0.0.0:{self.port}")
        
        async with server:
            await server.serve_forever()
    
    def start(self):
        """Start HTTP server in background thread"""
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run())
            except Exception as e:
                print(f"[HTTP] Error: {e}")
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()


# Test
if __name__ == "__main__":
    import numpy as np
    
    config = NetworkConfig()
    server = StreamingServer(config)
    
    def on_connect(client):
        print(f"Client connected: {client.address}")
    
    def on_disconnect(client):
        print(f"Client disconnected: {client.address}")
    
    server.set_callbacks(on_connect=on_connect, on_disconnect=on_disconnect)
    server.start()
    
    print(f"Server running at: {server.get_connection_url()}")
    print("Sending test frames...")
    
    # Send test frames
    try:
        for i in range(1000):
            # Generate test frame data
            test_data = b"TEST_FRAME_" + str(i).encode()
            server.push_frame(test_data)
            time.sleep(1/60)  # 60 FPS
            
            if i % 60 == 0:
                stats = server.get_stats()
                print(f"Clients: {stats.connected_clients}, FPS: {stats.current_fps:.1f}")
    except KeyboardInterrupt:
        pass
    
    server.stop()
