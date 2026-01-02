#pragma once
/**
 * VR Streamer - WebSocket Server
 * High-performance async WebSocket server using Boost.Beast/Asio.
 * Optimized for low-latency binary frame streaming.
 */

#include "../core/common.hpp"
#include "../core/config.hpp"
#include "../core/spsc_queue.hpp"

#include <boost/asio.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/websocket.hpp>

#include <unordered_map>
#include <shared_mutex>

namespace vrs
{

    namespace asio = boost::asio;
    namespace beast = boost::beast;
    namespace websocket = beast::websocket;
    using tcp = asio::ip::tcp;

    /**
     * Client connection information.
     */
    struct ClientInfo
    {
        std::string id;
        std::string address;
        u16 port;
        TimePoint connected_at;
        u64 frames_sent = 0;
        u64 bytes_sent = 0;
        f64 latency_ms = 0;
        TimePoint last_ping;

        [[nodiscard]] f64 uptime_seconds() const
        {
            return std::chrono::duration<f64>(Clock::now() - connected_at).count();
        }
    };

    /**
     * Server statistics.
     */
    struct ServerStats
    {
        u64 total_frames_sent = 0;
        u64 total_bytes_sent = 0;
        u32 connected_clients = 0;
        f64 current_fps = 0;
        f64 avg_latency_ms = 0;
        TimePoint start_time;

        [[nodiscard]] f64 uptime_seconds() const
        {
            return std::chrono::duration<f64>(Clock::now() - start_time).count();
        }

        [[nodiscard]] f64 avg_bitrate_mbps() const
        {
            f64 uptime = uptime_seconds();
            if (uptime <= 0)
                return 0;
            return (total_bytes_sent * 8.0) / (uptime * 1000000.0);
        }
    };

    /**
     * WebSocket session for a single client.
     */
    class WebSocketSession : public std::enable_shared_from_this<WebSocketSession>
    {
    public:
        WebSocketSession(tcp::socket socket, class StreamingServer &server);
        ~WebSocketSession();

        WebSocketSession(const WebSocketSession &) = delete;
        WebSocketSession &operator=(const WebSocketSession &) = delete;

        /**
         * Start the session.
         */
        void start();

        /**
         * Send a binary frame.
         */
        void send_frame(std::shared_ptr<std::vector<u8>> data);

        /**
         * Close the connection.
         */
        void close();

        /**
         * Get client info.
         */
        [[nodiscard]] const ClientInfo &info() const { return info_; }

        /**
         * Check if session is open.
         */
        [[nodiscard]] bool is_open() const;

    private:
        void do_accept();
        void on_accept(beast::error_code ec);
        void do_read();
        void on_read(beast::error_code ec, std::size_t bytes);
        void do_write();
        void on_write(beast::error_code ec, std::size_t bytes);
        void send_ping();
        void on_pong(beast::error_code ec);

        websocket::stream<beast::tcp_stream> ws_;
        class StreamingServer &server_;
        ClientInfo info_;

        beast::flat_buffer read_buffer_;

        // Write queue (lock-free SPSC)
        SPSCQueue<std::shared_ptr<std::vector<u8>>, 16> write_queue_;
        std::atomic<bool> writing_{false};
        std::shared_ptr<std::vector<u8>> current_write_;

        std::atomic<bool> closing_{false};
    };

    /**
     * High-performance streaming WebSocket server.
     */
    class StreamingServer
    {
    public:
        explicit StreamingServer(const NetworkConfig &config);
        ~StreamingServer();

        StreamingServer(const StreamingServer &) = delete;
        StreamingServer &operator=(const StreamingServer &) = delete;

        /**
         * Start the server.
         */
        bool start();

        /**
         * Stop the server.
         */
        void stop();

        /**
         * Push a frame to all connected clients.
         */
        void push_frame(const u8 *data, size_t size);

        /**
         * Push a frame using shared pointer (zero-copy for multiple clients).
         */
        void push_frame(std::shared_ptr<std::vector<u8>> data);

        /**
         * Get server statistics.
         */
        [[nodiscard]] ServerStats stats() const;

        /**
         * Get connected client count.
         */
        [[nodiscard]] u32 client_count() const;

        /**
         * Get list of connected clients.
         */
        [[nodiscard]] std::vector<ClientInfo> clients() const;

        /**
         * Get server IP address.
         */
        [[nodiscard]] std::string server_ip() const;

        /**
         * Get connection URL.
         */
        [[nodiscard]] std::string connection_url() const;

        /**
         * Check if server is running.
         */
        [[nodiscard]] bool running() const { return running_.load(); }

        /**
         * Set callbacks.
         */
        using ClientCallback = std::function<void(const ClientInfo &)>;
        using StatsCallback = std::function<void(const ServerStats &)>;

        void set_on_client_connect(ClientCallback cb) { on_connect_ = std::move(cb); }
        void set_on_client_disconnect(ClientCallback cb) { on_disconnect_ = std::move(cb); }
        void set_on_stats_update(StatsCallback cb) { on_stats_ = std::move(cb); }

        // Internal - called by sessions
        void register_session(std::shared_ptr<WebSocketSession> session);
        void unregister_session(const std::string &id);
        void on_client_connected(const ClientInfo &info);
        void on_client_disconnected(const ClientInfo &info);
        void add_bytes_sent(u64 bytes);
        void add_frame_sent();

    private:
        void do_accept();
        void on_accept(beast::error_code ec, tcp::socket socket);
        void run_io_context();
        std::string get_local_ip() const;

        NetworkConfig config_;
        asio::io_context io_context_;
        tcp::acceptor acceptor_;

        std::unordered_map<std::string, std::shared_ptr<WebSocketSession>> sessions_;
        mutable std::shared_mutex sessions_mutex_;

        std::atomic<bool> running_{false};
        std::vector<std::thread> io_threads_;

        ServerStats stats_;
        mutable std::mutex stats_mutex_;
        FPSCounter fps_counter_;

        ClientCallback on_connect_;
        ClientCallback on_disconnect_;
        StatsCallback on_stats_;

        std::string server_ip_;
    };

} // namespace vrs
