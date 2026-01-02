#pragma once
/**
 * VR Streamer - HTTP Server
 * Simple HTTP server for serving the mobile web app.
 */

#include "../core/common.hpp"
#include "../core/config.hpp"

#include <boost/asio.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/http.hpp>

#include <filesystem>
#include <unordered_map>

namespace vrs
{

    namespace asio = boost::asio;
    namespace beast = boost::beast;
    namespace http = beast::http;
    using tcp = asio::ip::tcp;

    /**
     * HTTP server for serving static files.
     */
    class HTTPServer
    {
    public:
        HTTPServer(u16 port, const std::filesystem::path &web_root);
        ~HTTPServer();

        HTTPServer(const HTTPServer &) = delete;
        HTTPServer &operator=(const HTTPServer &) = delete;

        /**
         * Start the server.
         */
        bool start();

        /**
         * Stop the server.
         */
        void stop();

        /**
         * Check if server is running.
         */
        [[nodiscard]] bool running() const { return running_.load(); }

        /**
         * Get server URL.
         */
        [[nodiscard]] std::string url() const;

    private:
        void do_accept();
        void handle_request(tcp::socket socket);
        std::string get_mime_type(const std::filesystem::path &path) const;

        u16 port_;
        std::filesystem::path web_root_;

        asio::io_context io_context_;
        tcp::acceptor acceptor_;

        std::atomic<bool> running_{false};
        std::thread io_thread_;

        static const std::unordered_map<std::string, std::string> mime_types_;
    };

} // namespace vrs
