#pragma once
/**
 * VR Streamer - Configuration
 * All tunable parameters with hot-reloading support.
 */

#include "common.hpp"
#include <fstream>

namespace vrs
{

    /**
     * Capture configuration.
     */
    struct CaptureConfig
    {
        u32 target_fps = 60;         // Target frames per second
        u32 monitor_index = 0;       // Monitor to capture (if no window)
        bool capture_cursor = true;  // Include mouse cursor
        bool use_gpu_capture = true; // Use DXGI Desktop Duplication

        // Performance tuning
        u32 frame_buffer_count = 3;  // Triple buffering
        bool wait_for_vsync = false; // Wait for VSync (reduces tearing but adds latency)
    };

    /**
     * Encoder configuration.
     */
    struct EncoderConfig
    {
        // Quality settings
        u32 jpeg_quality = 65;        // JPEG quality (1-100)
        f32 downscale_factor = 0.65f; // Resolution scale (1.0 = native)
        u32 output_width = 0;         // Custom output width (0 = auto)
        u32 output_height = 0;        // Custom output height (0 = auto)

        // Compression method
        enum class Method : u8
        {
            JPEG,      // Standard JPEG
            NVJPEG,    // NVIDIA nvJPEG (GPU)
            TURBOJPEG, // libjpeg-turbo (SIMD optimized)
            H264,      // NVENC H.264 (lowest bandwidth)
            RAW        // Uncompressed (highest bandwidth)
        } method = Method::TURBOJPEG;

        // VR settings
        bool vr_enabled = true;     // Enable VR stereo output
        f32 eye_separation = 0.03f; // IPD simulation (0-0.1)

        // GPU acceleration
        bool use_gpu = true;    // Enable GPU processing
        i32 gpu_device_id = 0;  // GPU device ID
        bool use_nvenc = true;  // Use NVENC for H.264
        bool use_nvjpeg = true; // Use nvJPEG for JPEG

        // H.264 specific (if using NVENC)
        u32 h264_bitrate = 20000;     // Kbps
        u32 h264_gop_length = 30;     // Keyframe interval
        bool h264_low_latency = true; // Low latency mode
    };

    /**
     * Network configuration.
     */
    struct NetworkConfig
    {
        std::string host = "0.0.0.0"; // Listen address
        u16 port = 8765;              // WebSocket port
        u16 http_port = 8080;         // HTTP server port
        std::string static_ip;        // Static IP (empty = auto-detect)

        u32 max_clients = 4;              // Maximum concurrent clients
        u32 send_buffer_size = 64 * 1024; // Send buffer size
        f32 ping_interval = 1.0f;         // Ping interval in seconds

        // Performance
        bool use_tcp_nodelay = true; // Disable Nagle's algorithm
        bool use_cork = false;       // Cork TCP for better batching
    };

    /**
     * Quality presets.
     */
    enum class QualityPreset : u8
    {
        ULTRA_PERFORMANCE, // Maximum FPS, lowest quality
        LOW_LATENCY,       // Balanced for low latency
        BALANCED,          // Balance quality and performance
        QUALITY,           // Higher quality, lower FPS
        MAXIMUM_QUALITY    // Best quality, may lag
    };

    /**
     * Main configuration container.
     */
    struct Config
    {
        CaptureConfig capture;
        EncoderConfig encoder;
        NetworkConfig network;

        /**
         * Apply a quality preset.
         */
        void apply_preset(QualityPreset preset);

        /**
         * Save configuration to YAML file.
         */
        bool save(const std::string &filepath = "config.yaml") const;

        /**
         * Load configuration from YAML file.
         */
        static Config load(const std::string &filepath = "config.yaml");

        /**
         * Get default configuration.
         */
        static Config default_config();
    };

    // Preset parameters
    inline void Config::apply_preset(QualityPreset preset)
    {
        switch (preset)
        {
        case QualityPreset::ULTRA_PERFORMANCE:
            encoder.jpeg_quality = 40;
            encoder.downscale_factor = 0.35f;
            capture.target_fps = 90;
            encoder.method = EncoderConfig::Method::TURBOJPEG;
            break;

        case QualityPreset::LOW_LATENCY:
            encoder.jpeg_quality = 55;
            encoder.downscale_factor = 0.5f;
            capture.target_fps = 60;
            encoder.method = EncoderConfig::Method::TURBOJPEG;
            break;

        case QualityPreset::BALANCED:
            encoder.jpeg_quality = 70;
            encoder.downscale_factor = 0.65f;
            capture.target_fps = 60;
            encoder.method = EncoderConfig::Method::NVJPEG;
            break;

        case QualityPreset::QUALITY:
            encoder.jpeg_quality = 80;
            encoder.downscale_factor = 0.8f;
            capture.target_fps = 45;
            encoder.method = EncoderConfig::Method::H264;
            break;

        case QualityPreset::MAXIMUM_QUALITY:
            encoder.jpeg_quality = 95;
            encoder.downscale_factor = 1.0f;
            capture.target_fps = 30;
            encoder.method = EncoderConfig::Method::H264;
            encoder.h264_bitrate = 50000;
            break;
        }
    }

    inline Config Config::default_config()
    {
        Config cfg;
        cfg.apply_preset(QualityPreset::LOW_LATENCY);
        return cfg;
    }

} // namespace vrs
