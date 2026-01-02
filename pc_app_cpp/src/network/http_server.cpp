/**
 * VR Streamer - HTTP Server Implementation
 */

#include "network/http_server.hpp"
#include <fstream>

namespace vrs
{

    const std::unordered_map<std::string, std::string> HTTPServer::mime_types_ = {
        {".html", "text/html"},
        {".htm", "text/html"},
        {".css", "text/css"},
        {".js", "application/javascript"},
        {".json", "application/json"},
        {".png", "image/png"},
        {".jpg", "image/jpeg"},
        {".jpeg", "image/jpeg"},
        {".gif", "image/gif"},
        {".svg", "image/svg+xml"},
        {".ico", "image/x-icon"},
        {".woff", "font/woff"},
        {".woff2", "font/woff2"},
        {".ttf", "font/ttf"},
        {".txt", "text/plain"},
    };

    HTTPServer::HTTPServer(u16 port, const std::filesystem::path &web_root)
        : port_(port), web_root_(web_root), io_context_(1), acceptor_(io_context_)
    {
    }

    HTTPServer::~HTTPServer()
    {
        stop();
    }

    bool HTTPServer::start()
    {
        if (running_.load())
        {
            return true;
        }

        if (!std::filesystem::exists(web_root_))
        {
            VRS_LOG_ERROR(std::format("Web root does not exist: {}", web_root_.string()));
            return false;
        }

        try
        {
            tcp::endpoint endpoint(asio::ip::address_v4::any(), port_);

            acceptor_.open(endpoint.protocol());
            acceptor_.set_option(asio::socket_base::reuse_address(true));
            acceptor_.bind(endpoint);
            acceptor_.listen();

            running_.store(true);

            do_accept();

            io_thread_ = std::thread([this]
                                     {
            while (running_.load()) {
                try {
                    io_context_.run();
                    break;
                } catch (const std::exception& e) {
                    VRS_LOG_ERROR(std::format("HTTP server error: {}", e.what()));
                }
            } });

            VRS_LOG_INFO(std::format("HTTP server started on port {}", port_));
            return true;
        }
        catch (const std::exception &e)
        {
            VRS_LOG_ERROR(std::format("Failed to start HTTP server: {}", e.what()));
            return false;
        }
    }

    void HTTPServer::stop()
    {
        if (!running_.exchange(false))
        {
            return;
        }

        beast::error_code ec;
        acceptor_.close(ec);
        io_context_.stop();

        if (io_thread_.joinable())
        {
            io_thread_.join();
        }

        VRS_LOG_INFO("HTTP server stopped");
    }

    void HTTPServer::do_accept()
    {
        acceptor_.async_accept(
            [this](beast::error_code ec, tcp::socket socket)
            {
                if (!ec)
                {
                    // Handle request in a detached thread to avoid blocking
                    std::thread([this, s = std::move(socket)]() mutable
                                { handle_request(std::move(s)); })
                        .detach();
                }

                if (running_.load())
                {
                    do_accept();
                }
            });
    }

    void HTTPServer::handle_request(tcp::socket socket)
    {
        try
        {
            beast::flat_buffer buffer;
            http::request<http::string_body> req;

            http::read(socket, buffer, req);

            // Get request path
            std::string path = std::string(req.target());
            if (path.empty() || path == "/")
            {
                path = "/index.html";
            }

            // Security: prevent directory traversal
            if (path.find("..") != std::string::npos)
            {
                http::response<http::string_body> res{http::status::forbidden, req.version()};
                res.set(http::field::content_type, "text/plain");
                res.body() = "Forbidden";
                res.prepare_payload();
                http::write(socket, res);
                return;
            }

            // Build file path
            std::filesystem::path file_path = web_root_ / path.substr(1);

            if (!std::filesystem::exists(file_path) || !std::filesystem::is_regular_file(file_path))
            {
                http::response<http::string_body> res{http::status::not_found, req.version()};
                res.set(http::field::content_type, "text/plain");
                res.body() = "Not Found";
                res.prepare_payload();
                http::write(socket, res);
                return;
            }

            // Read file
            std::ifstream file(file_path, std::ios::binary);
            std::string content((std::istreambuf_iterator<char>(file)),
                                std::istreambuf_iterator<char>());

            // Build response
            http::response<http::string_body> res{http::status::ok, req.version()};
            res.set(http::field::server, "VRStreamer/1.0");
            res.set(http::field::content_type, get_mime_type(file_path));
            res.set(http::field::cache_control, "no-cache");
            res.body() = std::move(content);
            res.prepare_payload();

            http::write(socket, res);
        }
        catch (const std::exception &e)
        {
            VRS_LOG_ERROR(std::format("HTTP request error: {}", e.what()));
        }

        beast::error_code ec;
        socket.shutdown(tcp::socket::shutdown_send, ec);
    }

    std::string HTTPServer::get_mime_type(const std::filesystem::path &path) const
    {
        std::string ext = path.extension().string();
        auto it = mime_types_.find(ext);
        if (it != mime_types_.end())
        {
            return it->second;
        }
        return "application/octet-stream";
    }

    std::string HTTPServer::url() const
    {
        return std::format("http://localhost:{}", port_);
    }

} // namespace vrs
