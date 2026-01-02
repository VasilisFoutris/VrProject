/**
 * VR Streamer - WebSocket Server Implementation
 * High-performance async WebSocket server.
 */

#include "network/websocket_server.hpp"
#include <boost/asio/strand.hpp>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#else
#include <netdb.h>
#include <arpa/inet.h>
#include <ifaddrs.h>
#endif

namespace vrs
{

    // ============================================================================
    // WebSocketSession Implementation
    // ============================================================================

    WebSocketSession::WebSocketSession(tcp::socket socket, StreamingServer &server)
        : ws_(std::move(socket)), server_(server)
    {

        // Generate client ID
        auto ep = ws_.next_layer().socket().remote_endpoint();
        info_.address = ep.address().to_string();
        info_.port = ep.port();
        info_.id = std::format("{}:{}", info_.address, info_.port);
        info_.connected_at = Clock::now();
    }

    WebSocketSession::~WebSocketSession()
    {
        if (!closing_.exchange(true))
        {
            server_.unregister_session(info_.id);
        }
    }

    void WebSocketSession::start()
    {
        // Set WebSocket options for low latency
        ws_.set_option(websocket::stream_base::timeout::suggested(beast::role_type::server));
        ws_.set_option(websocket::stream_base::decorator([](websocket::response_type &res)
                                                         { res.set(beast::http::field::server, "VRStreamer/1.0"); }));

        // Binary mode for frames
        ws_.binary(true);

        // Disable compression for lower latency
        // websocket::permessage_deflate pmd;
        // pmd.server_enable = false;
        // ws_.set_option(pmd);

        do_accept();
    }

    void WebSocketSession::do_accept()
    {
        ws_.async_accept(
            beast::bind_front_handler(&WebSocketSession::on_accept, shared_from_this()));
    }

    void WebSocketSession::on_accept(beast::error_code ec)
    {
        if (ec)
        {
            VRS_LOG_ERROR(std::format("WebSocket accept failed: {}", ec.message()));
            return;
        }

        // Register with server
        server_.register_session(shared_from_this());
        server_.on_client_connected(info_);

        VRS_LOG_INFO(std::format("Client connected: {}", info_.id));

        // Start reading (for ping/pong and control messages)
        do_read();
    }

    void WebSocketSession::do_read()
    {
        ws_.async_read(
            read_buffer_,
            beast::bind_front_handler(&WebSocketSession::on_read, shared_from_this()));
    }

    void WebSocketSession::on_read(beast::error_code ec, std::size_t bytes)
    {
        if (ec == websocket::error::closed)
        {
            return;
        }

        if (ec)
        {
            VRS_LOG_ERROR(std::format("Read error from {}: {}", info_.id, ec.message()));
            return;
        }

        // Handle message (ping/pong are handled automatically by Beast)
        // Could parse JSON messages here for quality requests, etc.

        // Clear buffer and continue reading
        read_buffer_.consume(bytes);
        do_read();
    }

    void WebSocketSession::send_frame(std::shared_ptr<std::vector<u8>> data)
    {
        if (closing_.load() || !is_open())
        {
            return;
        }

        // Try to queue the frame
        if (!write_queue_.try_push(std::move(data)))
        {
            // Queue full - drop frame
            return;
        }

        // If not currently writing, start writing
        bool expected = false;
        if (writing_.compare_exchange_strong(expected, true))
        {
            do_write();
        }
    }

    void WebSocketSession::do_write()
    {
        if (closing_.load())
        {
            writing_.store(false);
            return;
        }

        // Get next frame from queue
        if (!write_queue_.try_pop(current_write_))
        {
            writing_.store(false);
            return;
        }

        ws_.async_write(
            asio::buffer(*current_write_),
            beast::bind_front_handler(&WebSocketSession::on_write, shared_from_this()));
    }

    void WebSocketSession::on_write(beast::error_code ec, std::size_t bytes)
    {
        if (ec)
        {
            VRS_LOG_ERROR(std::format("Write error to {}: {}", info_.id, ec.message()));
            writing_.store(false);
            close();
            return;
        }

        // Update stats
        info_.frames_sent++;
        info_.bytes_sent += bytes;
        server_.add_bytes_sent(bytes);
        server_.add_frame_sent();

        // Clear current write
        current_write_.reset();

        // Continue writing if more in queue
        do_write();
    }

    void WebSocketSession::close()
    {
        if (closing_.exchange(true))
        {
            return;
        }

        beast::error_code ec;
        ws_.close(websocket::close_code::normal, ec);

        server_.unregister_session(info_.id);
        server_.on_client_disconnected(info_);

        VRS_LOG_INFO(std::format("Client disconnected: {}", info_.id));
    }

    bool WebSocketSession::is_open() const
    {
        return ws_.is_open();
    }

    void WebSocketSession::send_ping()
    {
        if (closing_.load() || !is_open())
        {
            return;
        }

        info_.last_ping = Clock::now();

        ws_.async_ping({},
                       beast::bind_front_handler(&WebSocketSession::on_pong, shared_from_this()));
    }

    void WebSocketSession::on_pong(beast::error_code ec)
    {
        if (!ec)
        {
            auto now = Clock::now();
            info_.latency_ms = std::chrono::duration<f64, std::milli>(now - info_.last_ping).count() / 2.0;
        }
    }

    // ============================================================================
    // StreamingServer Implementation
    // ============================================================================

    StreamingServer::StreamingServer(const NetworkConfig &config)
        : config_(config), io_context_(static_cast<int>(std::thread::hardware_concurrency())), acceptor_(io_context_)
    {

        stats_.start_time = Clock::now();
        server_ip_ = get_local_ip();
    }

    StreamingServer::~StreamingServer()
    {
        stop();
    }

    bool StreamingServer::start()
    {
        if (running_.load())
        {
            return true;
        }

        try
        {
            // Create endpoint
            tcp::endpoint endpoint(
                asio::ip::make_address(config_.host),
                config_.port);

            // Open and configure acceptor
            acceptor_.open(endpoint.protocol());
            acceptor_.set_option(asio::socket_base::reuse_address(true));

            if (config_.use_tcp_nodelay)
            {
                acceptor_.set_option(tcp::no_delay(true));
            }

            acceptor_.bind(endpoint);
            acceptor_.listen(asio::socket_base::max_listen_connections);

            running_.store(true);

            // Start accepting connections
            do_accept();

            // Run IO context on multiple threads
            size_t num_threads = std::max(1u, std::thread::hardware_concurrency() / 2);
            io_threads_.reserve(num_threads);

            for (size_t i = 0; i < num_threads; ++i)
            {
                io_threads_.emplace_back([this]
                                         { run_io_context(); });
            }

            VRS_LOG_INFO(std::format("WebSocket server started on ws://{}:{}",
                                     server_ip_, config_.port));

            return true;
        }
        catch (const std::exception &e)
        {
            VRS_LOG_ERROR(std::format("Failed to start server: {}", e.what()));
            return false;
        }
    }

    void StreamingServer::stop()
    {
        if (!running_.exchange(false))
        {
            return;
        }

        // Close all sessions
        {
            std::unique_lock lock(sessions_mutex_);
            for (auto &[id, session] : sessions_)
            {
                session->close();
            }
            sessions_.clear();
        }

        // Stop acceptor
        beast::error_code ec;
        acceptor_.close(ec);

        // Stop IO context
        io_context_.stop();

        // Wait for threads
        for (auto &thread : io_threads_)
        {
            if (thread.joinable())
            {
                thread.join();
            }
        }
        io_threads_.clear();

        VRS_LOG_INFO("WebSocket server stopped");
    }

    void StreamingServer::do_accept()
    {
        acceptor_.async_accept(
            asio::make_strand(io_context_),
            beast::bind_front_handler(&StreamingServer::on_accept, this));
    }

    void StreamingServer::on_accept(beast::error_code ec, tcp::socket socket)
    {
        if (ec)
        {
            if (running_.load())
            {
                VRS_LOG_ERROR(std::format("Accept error: {}", ec.message()));
            }
        }
        else
        {
            // Check max clients
            if (client_count() < config_.max_clients)
            {
                // Create session
                auto session = std::make_shared<WebSocketSession>(std::move(socket), *this);
                session->start();
            }
            else
            {
                VRS_LOG_WARN("Max clients reached, rejecting connection");
                socket.close();
            }
        }

        // Continue accepting if running
        if (running_.load())
        {
            do_accept();
        }
    }

    void StreamingServer::run_io_context()
    {
        while (running_.load())
        {
            try
            {
                io_context_.run();
                break;
            }
            catch (const std::exception &e)
            {
                VRS_LOG_ERROR(std::format("IO context error: {}", e.what()));
            }
        }
    }

    void StreamingServer::push_frame(const u8 *data, size_t size)
    {
        // Create shared buffer
        auto buffer = std::make_shared<std::vector<u8>>(data, data + size);
        push_frame(std::move(buffer));
    }

    void StreamingServer::push_frame(std::shared_ptr<std::vector<u8>> data)
    {
        fps_counter_.tick();

        // Broadcast to all clients
        std::shared_lock lock(sessions_mutex_);
        for (auto &[id, session] : sessions_)
        {
            session->send_frame(data);
        }
    }

    void StreamingServer::register_session(std::shared_ptr<WebSocketSession> session)
    {
        std::unique_lock lock(sessions_mutex_);
        sessions_[session->info().id] = std::move(session);

        std::lock_guard stats_lock(stats_mutex_);
        stats_.connected_clients = static_cast<u32>(sessions_.size());
    }

    void StreamingServer::unregister_session(const std::string &id)
    {
        std::unique_lock lock(sessions_mutex_);
        sessions_.erase(id);

        std::lock_guard stats_lock(stats_mutex_);
        stats_.connected_clients = static_cast<u32>(sessions_.size());
    }

    void StreamingServer::on_client_connected(const ClientInfo &info)
    {
        if (on_connect_)
        {
            on_connect_(info);
        }
    }

    void StreamingServer::on_client_disconnected(const ClientInfo &info)
    {
        if (on_disconnect_)
        {
            on_disconnect_(info);
        }
    }

    void StreamingServer::add_bytes_sent(u64 bytes)
    {
        std::lock_guard lock(stats_mutex_);
        stats_.total_bytes_sent += bytes;
    }

    void StreamingServer::add_frame_sent()
    {
        std::lock_guard lock(stats_mutex_);
        stats_.total_frames_sent++;
        stats_.current_fps = fps_counter_.fps();
    }

    ServerStats StreamingServer::stats() const
    {
        std::lock_guard lock(stats_mutex_);
        return stats_;
    }

    u32 StreamingServer::client_count() const
    {
        std::shared_lock lock(sessions_mutex_);
        return static_cast<u32>(sessions_.size());
    }

    std::vector<ClientInfo> StreamingServer::clients() const
    {
        std::vector<ClientInfo> result;
        std::shared_lock lock(sessions_mutex_);
        result.reserve(sessions_.size());
        for (const auto &[id, session] : sessions_)
        {
            result.push_back(session->info());
        }
        return result;
    }

    std::string StreamingServer::server_ip() const
    {
        return server_ip_;
    }

    std::string StreamingServer::connection_url() const
    {
        return std::format("ws://{}:{}", server_ip_, config_.port);
    }

    std::string StreamingServer::get_local_ip() const
    {
        if (!config_.static_ip.empty())
        {
            return config_.static_ip;
        }

#ifdef _WIN32
        // Windows: Use a dummy UDP socket to find local IP
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        {
            return "127.0.0.1";
        }

        SOCKET sock = socket(AF_INET, SOCK_DGRAM, 0);
        if (sock == INVALID_SOCKET)
        {
            WSACleanup();
            return "127.0.0.1";
        }

        sockaddr_in target;
        target.sin_family = AF_INET;
        target.sin_port = htons(80);
        inet_pton(AF_INET, "8.8.8.8", &target.sin_addr);

        connect(sock, reinterpret_cast<sockaddr *>(&target), sizeof(target));

        sockaddr_in local;
        int len = sizeof(local);
        getsockname(sock, reinterpret_cast<sockaddr *>(&local), &len);

        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &local.sin_addr, ip, INET_ADDRSTRLEN);

        closesocket(sock);
        WSACleanup();

        return std::string(ip);
#else
        // Linux: Similar approach
        int sock = socket(AF_INET, SOCK_DGRAM, 0);
        if (sock < 0)
            return "127.0.0.1";

        sockaddr_in target;
        target.sin_family = AF_INET;
        target.sin_port = htons(80);
        inet_pton(AF_INET, "8.8.8.8", &target.sin_addr);

        connect(sock, reinterpret_cast<sockaddr *>(&target), sizeof(target));

        sockaddr_in local;
        socklen_t len = sizeof(local);
        getsockname(sock, reinterpret_cast<sockaddr *>(&local), &len);

        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &local.sin_addr, ip, INET_ADDRSTRLEN);

        close(sock);

        return std::string(ip);
#endif
    }

} // namespace vrs
