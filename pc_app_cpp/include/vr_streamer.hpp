#pragma once
/**
 * VR Streamer - Main Application Header
 * Complete VR streaming application interface.
 */

#include "core/common.hpp"
#include "core/config.hpp"
#include "core/memory_pool.hpp"
#include "core/spsc_queue.hpp"
#include "capture/dxgi_capture.hpp"
#include "encoder/stereo_processor.hpp"
#include "encoder/jpeg_encoder.hpp"
#include "network/websocket_server.hpp"
#include "network/http_server.hpp"

namespace vrs
{

    /**
     * Streaming pipeline statistics.
     */
    struct PipelineStats
    {
        // Capture
        f64 capture_fps = 0;
        f64 capture_time_ms = 0;

        // Encoding
        f64 encode_fps = 0;
        f64 stereo_time_ms = 0;
        f64 jpeg_time_ms = 0;
        f64 total_encode_time_ms = 0;

        // Network
        f64 stream_fps = 0;
        u32 connected_clients = 0;
        f64 avg_latency_ms = 0;
        f64 bitrate_mbps = 0;

        // Overall
        u64 frames_captured = 0;
        u64 frames_encoded = 0;
        u64 frames_sent = 0;
        u64 bytes_sent = 0;
        f64 uptime_seconds = 0;

        // Quality
        u32 current_quality = 0;
        f32 downscale_factor = 0;
        bool gpu_encoding = false;
        bool gpu_stereo = false;
    };

    /**
     * VR Streaming Application.
     * High-performance pipeline: Capture -> Encode -> Stream
     */
    class VRStreamerApp
    {
    public:
        VRStreamerApp();
        ~VRStreamerApp();

        VRStreamerApp(const VRStreamerApp &) = delete;
        VRStreamerApp &operator=(const VRStreamerApp &) = delete;

        /**
         * Initialize the application.
         */
        bool init(const Config &config = Config::default_config());

        /**
         * Start streaming.
         */
        bool start();

        /**
         * Stop streaming.
         */
        void stop();

        /**
         * Run the main loop (blocking).
         */
        void run();

        /**
         * Check if streaming is active.
         */
        [[nodiscard]] bool streaming() const { return streaming_.load(); }

        /**
         * Get current statistics.
         */
        [[nodiscard]] PipelineStats stats() const;

        /**
         * Update configuration.
         */
        void update_config(const Config &config);

        /**
         * Get current configuration.
         */
        [[nodiscard]] const Config &config() const { return config_; }

        /**
         * Set capture to a specific monitor.
         */
        bool set_capture_monitor(u32 index);

        /**
         * Set capture to a specific window.
         */
        bool set_capture_window(HWND hwnd);

        /**
         * Set capture to a window by title.
         */
        bool set_capture_window_by_title(std::wstring_view title);

        /**
         * Get list of available windows.
         */
        [[nodiscard]] std::vector<WindowInfo> get_windows() const;

        /**
         * Get list of available monitors.
         */
        [[nodiscard]] std::vector<MonitorInfo> get_monitors() const;

        /**
         * Get server connection URL.
         */
        [[nodiscard]] std::string connection_url() const;

        /**
         * Get server IP.
         */
        [[nodiscard]] std::string server_ip() const;

        /**
         * Set quality preset.
         */
        void set_quality_preset(QualityPreset preset);

        /**
         * Set JPEG quality directly.
         */
        void set_quality(u32 quality);

        /**
         * Set downscale factor.
         */
        void set_downscale(f32 factor);

        // Callbacks
        using StatsCallback = std::function<void(const PipelineStats &)>;
        using ClientCallback = std::function<void(const ClientInfo &)>;
        using ErrorCallback = std::function<void(const std::string &)>;

        void set_on_stats_update(StatsCallback cb) { on_stats_ = std::move(cb); }
        void set_on_client_connect(ClientCallback cb) { on_client_connect_ = std::move(cb); }
        void set_on_client_disconnect(ClientCallback cb) { on_client_disconnect_ = std::move(cb); }
        void set_on_error(ErrorCallback cb) { on_error_ = std::move(cb); }

    private:
        void capture_loop();
        void encode_loop();
        void stats_loop();

        Config config_;

        // Components
        std::unique_ptr<CaptureManager> capture_;
        std::unique_ptr<VRFrameEncoder> encoder_;
        std::unique_ptr<StreamingServer> server_;
        std::unique_ptr<HTTPServer> http_server_;

        // Memory pools
        std::unique_ptr<FrameBufferPool> frame_pool_;
        std::unique_ptr<CompressedFramePool> compressed_pool_;

        // Frame queues (capture -> encode -> stream)
        static constexpr size_t QUEUE_SIZE = 4;
        SPSCQueue<FrameBufferPool::BufferPtr, QUEUE_SIZE> capture_queue_;
        SPSCQueue<CompressedFramePtr, QUEUE_SIZE> encode_queue_;

        // Threads
        std::thread capture_thread_;
        std::thread encode_thread_;
        std::thread stats_thread_;

        // State
        std::atomic<bool> initialized_{false};
        std::atomic<bool> streaming_{false};
        std::atomic<bool> stop_requested_{false};

        // Statistics
        PipelineStats stats_;
        mutable std::mutex stats_mutex_;
        FPSCounter capture_fps_;
        FPSCounter encode_fps_;
        Timer uptime_timer_;

        // Callbacks
        StatsCallback on_stats_;
        ClientCallback on_client_connect_;
        ClientCallback on_client_disconnect_;
        ErrorCallback on_error_;
    };

} // namespace vrs
