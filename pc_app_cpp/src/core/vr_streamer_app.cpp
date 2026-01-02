/**
 * VR Streamer - Application Implementation
 * High-performance streaming pipeline.
 */

#include "vr_streamer.hpp"
#include <filesystem>

namespace vrs
{

    VRStreamerApp::VRStreamerApp() = default;

    VRStreamerApp::~VRStreamerApp()
    {
        stop();
    }

    bool VRStreamerApp::init(const Config &config)
    {
        if (initialized_.load())
        {
            return true;
        }

        config_ = config;

        try
        {
            // Initialize capture
            capture_ = std::make_unique<CaptureManager>();
            if (!capture_->init())
            {
                VRS_LOG_ERROR("Failed to initialize capture");
                return false;
            }

            // Set capture source
            if (config.capture.monitor_index > 0)
            {
                capture_->set_monitor(config.capture.monitor_index);
            }

            // Initialize encoder
            encoder_ = std::make_unique<VRFrameEncoder>(config.encoder);

            // Initialize server
            server_ = std::make_unique<StreamingServer>(config.network);

            // Initialize HTTP server for mobile app
            std::filesystem::path web_root = std::filesystem::current_path().parent_path() / "mobile_app";
            if (std::filesystem::exists(web_root))
            {
                http_server_ = std::make_unique<HTTPServer>(config.network.http_port, web_root);
            }

            // Initialize memory pools
            // Estimate max frame size: 4K BGRA = 3840 * 2160 * 4 = ~33MB
            size_t max_frame_size = 3840 * 2160 * 4;
            frame_pool_ = std::make_unique<FrameBufferPool>(max_frame_size, 6);
            compressed_pool_ = std::make_unique<CompressedFramePool>(1024 * 1024, 6);

            // Set server callbacks
            server_->set_on_client_connect([this](const ClientInfo &info)
                                           {
            if (on_client_connect_) {
                on_client_connect_(info);
            } });

            server_->set_on_client_disconnect([this](const ClientInfo &info)
                                              {
            if (on_client_disconnect_) {
                on_client_disconnect_(info);
            } });

            initialized_.store(true);
            VRS_LOG_INFO("VR Streamer initialized");

            return true;
        }
        catch (const std::exception &e)
        {
            VRS_LOG_ERROR(std::format("Initialization failed: {}", e.what()));
            return false;
        }
    }

    bool VRStreamerApp::start()
    {
        if (!initialized_.load())
        {
            VRS_LOG_ERROR("Not initialized");
            return false;
        }

        if (streaming_.load())
        {
            return true;
        }

        stop_requested_.store(false);

        // Start servers
        if (!server_->start())
        {
            VRS_LOG_ERROR("Failed to start WebSocket server");
            return false;
        }

        if (http_server_ && !http_server_->start())
        {
            VRS_LOG_WARN("Failed to start HTTP server");
        }

        // Reset timer
        uptime_timer_.reset();

        // Start pipeline threads
        streaming_.store(true);

        capture_thread_ = std::thread(&VRStreamerApp::capture_loop, this);
        encode_thread_ = std::thread(&VRStreamerApp::encode_loop, this);
        stats_thread_ = std::thread(&VRStreamerApp::stats_loop, this);

        VRS_LOG_INFO("Streaming started");
        return true;
    }

    void VRStreamerApp::stop()
    {
        if (!streaming_.exchange(false))
        {
            return;
        }

        stop_requested_.store(true);

        // Wait for threads
        if (capture_thread_.joinable())
        {
            capture_thread_.join();
        }
        if (encode_thread_.joinable())
        {
            encode_thread_.join();
        }
        if (stats_thread_.joinable())
        {
            stats_thread_.join();
        }

        // Stop servers
        if (server_)
        {
            server_->stop();
        }
        if (http_server_)
        {
            http_server_->stop();
        }

        VRS_LOG_INFO("Streaming stopped");
    }

    void VRStreamerApp::run()
    {
        while (streaming_.load())
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }

    void VRStreamerApp::capture_loop()
    {
        VRS_LOG_INFO("Capture thread started");

        const f64 target_frame_time_ms = 1000.0 / config_.capture.target_fps;
        Timer frame_timer;

        CapturedFrame frame;

        while (!stop_requested_.load())
        {
            frame_timer.reset();

            // Capture frame
            if (!capture_->capture(frame, 16))
            {
                // No new frame, wait a bit
                spin_wait(100);
                continue;
            }

            // Copy to CPU if needed
            if (!capture_->copy_to_cpu(frame))
            {
                capture_->release_frame(frame);
                continue;
            }

            // Get buffer from pool
            auto buffer = frame_pool_->acquire();
            if (!buffer)
            {
                capture_->release_frame(frame);
                continue;
            }

            // Copy frame data
            buffer->width = frame.width;
            buffer->height = frame.height;
            buffer->stride = frame.pitch;
            buffer->timestamp = frame.timestamp;
            buffer->frame_id = frame.frame_id;
            buffer->format = 0; // BGRA

            // Ensure buffer is large enough
            size_t required_size = static_cast<size_t>(frame.pitch) * frame.height;
            buffer->allocate(required_size);
            buffer->size = required_size;

            // Copy pixel data
            std::memcpy(buffer->data.get(), frame.cpu_data, required_size);

            // Release capture frame
            capture_->release_frame(frame);

            // Push to encode queue
            if (!capture_queue_.try_push(std::move(buffer)))
            {
                // Queue full, drop frame
                frame_pool_->release(std::move(buffer));
            }

            // Update stats
            capture_fps_.tick();

            {
                std::lock_guard lock(stats_mutex_);
                stats_.frames_captured++;
                stats_.capture_fps = capture_fps_.fps();
                stats_.capture_time_ms = frame_timer.elapsed_ms();
            }

            // Frame rate limiting
            f64 elapsed = frame_timer.elapsed_ms();
            if (elapsed < target_frame_time_ms)
            {
                f64 sleep_time = target_frame_time_ms - elapsed;
                if (sleep_time > 1.0)
                {
                    std::this_thread::sleep_for(std::chrono::microseconds(
                        static_cast<i64>((sleep_time - 0.5) * 1000)));
                }
            }
        }

        VRS_LOG_INFO("Capture thread stopped");
    }

    void VRStreamerApp::encode_loop()
    {
        VRS_LOG_INFO("Encode thread started");

        std::vector<u8> encoded_buffer;
        encoded_buffer.reserve(1024 * 1024); // 1MB initial

        while (!stop_requested_.load())
        {
            // Get frame from capture queue
            FrameBufferPool::BufferPtr buffer;
            if (!capture_queue_.try_pop(buffer))
            {
                spin_wait(50);
                continue;
            }

            if (!buffer)
            {
                continue;
            }

            Timer encode_timer;

            // Encode frame
            size_t encoded_size = encoder_->encode(
                buffer->data.get(),
                buffer->width,
                buffer->height,
                buffer->stride,
                4, // BGRA
                encoded_buffer);

            // Return buffer to pool
            frame_pool_->release(std::move(buffer));

            if (encoded_size == 0)
            {
                continue;
            }

            // Create shared buffer for streaming
            auto shared_data = std::make_shared<std::vector<u8>>(
                encoded_buffer.begin(),
                encoded_buffer.begin() + encoded_size);

            // Push to server (broadcasts to all clients)
            server_->push_frame(std::move(shared_data));

            // Update stats
            encode_fps_.tick();
            auto encoder_stats = encoder_->stats();

            {
                std::lock_guard lock(stats_mutex_);
                stats_.frames_encoded++;
                stats_.encode_fps = encode_fps_.fps();
                stats_.stereo_time_ms = encoder_stats.stereo_time_ms;
                stats_.jpeg_time_ms = encoder_stats.encode_time_ms;
                stats_.total_encode_time_ms = encode_timer.elapsed_ms();
            }
        }

        VRS_LOG_INFO("Encode thread stopped");
    }

    void VRStreamerApp::stats_loop()
    {
        VRS_LOG_INFO("Stats thread started");

        while (!stop_requested_.load())
        {
            std::this_thread::sleep_for(std::chrono::seconds(1));

            if (!server_)
                continue;

            auto server_stats = server_->stats();

            {
                std::lock_guard lock(stats_mutex_);
                stats_.stream_fps = server_stats.current_fps;
                stats_.connected_clients = server_stats.connected_clients;
                stats_.bytes_sent = server_stats.total_bytes_sent;
                stats_.frames_sent = server_stats.total_frames_sent;
                stats_.bitrate_mbps = server_stats.avg_bitrate_mbps();
                stats_.avg_latency_ms = server_stats.avg_latency_ms;
                stats_.uptime_seconds = uptime_timer_.elapsed_s();
                stats_.current_quality = config_.encoder.jpeg_quality;
                stats_.downscale_factor = config_.encoder.downscale_factor;
            }

            if (on_stats_)
            {
                on_stats_(stats());
            }
        }

        VRS_LOG_INFO("Stats thread stopped");
    }

    PipelineStats VRStreamerApp::stats() const
    {
        std::lock_guard lock(stats_mutex_);
        return stats_;
    }

    void VRStreamerApp::update_config(const Config &config)
    {
        config_ = config;

        if (encoder_)
        {
            encoder_->update_config(config.encoder);
        }
    }

    bool VRStreamerApp::set_capture_monitor(u32 index)
    {
        if (capture_)
        {
            return capture_->set_monitor(index);
        }
        return false;
    }

    bool VRStreamerApp::set_capture_window(HWND hwnd)
    {
        if (capture_)
        {
            return capture_->set_window(hwnd);
        }
        return false;
    }

    bool VRStreamerApp::set_capture_window_by_title(std::wstring_view title)
    {
        if (capture_)
        {
            return capture_->set_window_by_title(title);
        }
        return false;
    }

    std::vector<WindowInfo> VRStreamerApp::get_windows() const
    {
        return DXGICapture::enumerate_windows();
    }

    std::vector<MonitorInfo> VRStreamerApp::get_monitors() const
    {
        return DXGICapture::enumerate_monitors();
    }

    std::string VRStreamerApp::connection_url() const
    {
        if (server_)
        {
            return server_->connection_url();
        }
        return "";
    }

    std::string VRStreamerApp::server_ip() const
    {
        if (server_)
        {
            return server_->server_ip();
        }
        return "127.0.0.1";
    }

    void VRStreamerApp::set_quality_preset(QualityPreset preset)
    {
        config_.apply_preset(preset);

        if (encoder_)
        {
            encoder_->update_config(config_.encoder);
        }
    }

    void VRStreamerApp::set_quality(u32 quality)
    {
        config_.encoder.jpeg_quality = std::clamp(quality, 1u, 100u);

        if (encoder_)
        {
            encoder_->update_config(config_.encoder);
        }
    }

    void VRStreamerApp::set_downscale(f32 factor)
    {
        config_.encoder.downscale_factor = std::clamp(factor, 0.1f, 1.0f);

        if (encoder_)
        {
            encoder_->update_config(config_.encoder);
        }
    }

} // namespace vrs
