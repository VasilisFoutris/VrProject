#pragma once
/**
 * VR Streamer - DXGI Desktop Duplication Capture
 * Zero-copy GPU screen capture using Direct3D 11.
 * Achieves lowest possible capture latency with GPU textures.
 */

#include "../core/common.hpp"
#include "../core/memory_pool.hpp"

#include <d3d11.h>
#include <dxgi1_6.h>
#include <vector>

namespace vrs
{

    /**
     * Captured frame data structure.
     */
    struct CapturedFrame
    {
        ComPtr<ID3D11Texture2D> gpu_texture;     // GPU texture (zero-copy)
        ComPtr<ID3D11Texture2D> staging_texture; // CPU-accessible staging texture
        u8 *cpu_data = nullptr;                  // CPU memory pointer (after Map)
        u32 width = 0;
        u32 height = 0;
        u32 pitch = 0;     // Row pitch in bytes
        u64 timestamp = 0; // Capture timestamp (ns)
        u32 frame_id = 0;
        bool cursor_visible = false;
        i32 cursor_x = 0;
        i32 cursor_y = 0;

        [[nodiscard]] bool valid() const noexcept
        {
            return gpu_texture != nullptr || cpu_data != nullptr;
        }

        [[nodiscard]] size_t size() const noexcept
        {
            return static_cast<size_t>(pitch) * height;
        }
    };

    /**
     * Monitor information.
     */
    struct MonitorInfo
    {
        u32 index;
        std::wstring name;
        i32 left, top, right, bottom;
        u32 width() const { return right - left; }
        u32 height() const { return bottom - top; }
        bool is_primary;
        HMONITOR handle;
    };

    /**
     * Window information for window capture.
     */
    struct WindowInfo
    {
        HWND hwnd;
        std::wstring title;
        std::wstring class_name;
        i32 left, top, right, bottom;
        u32 width() const { return right - left; }
        u32 height() const { return bottom - top; }
        bool is_visible;
        DWORD process_id;
    };

    /**
     * High-performance DXGI Desktop Duplication capture.
     * Features:
     * - Zero-copy GPU texture capture
     * - Cursor compositing
     * - Dirty region tracking
     * - Multi-monitor support
     */
    class DXGICapture
    {
    public:
        DXGICapture();
        ~DXGICapture();

        DXGICapture(const DXGICapture &) = delete;
        DXGICapture &operator=(const DXGICapture &) = delete;

        /**
         * Initialize capture for a specific monitor.
         */
        bool init(u32 monitor_index = 0);

        /**
         * Initialize capture for a specific window.
         * Falls back to monitor capture with clipping.
         */
        bool init_window(HWND hwnd);

        /**
         * Shutdown and release all resources.
         */
        void shutdown();

        /**
         * Capture the next frame.
         * @param timeout_ms Maximum time to wait for a new frame
         * @param frame Output frame data
         * @return true if a new frame was captured
         */
        bool capture_frame(CapturedFrame &frame, u32 timeout_ms = 16);

        /**
         * Copy GPU texture to CPU memory.
         * Call this to access pixel data on CPU.
         */
        bool copy_to_cpu(CapturedFrame &frame);

        /**
         * Release frame resources (must call after processing).
         */
        void release_frame(CapturedFrame &frame);

        /**
         * Get list of available monitors.
         */
        static std::vector<MonitorInfo> enumerate_monitors();

        /**
         * Get list of capturable windows.
         */
        static std::vector<WindowInfo> enumerate_windows();

        /**
         * Get D3D11 device (for GPU processing).
         */
        [[nodiscard]] ID3D11Device *device() const noexcept { return device_.get(); }

        /**
         * Get D3D11 device context.
         */
        [[nodiscard]] ID3D11DeviceContext *context() const noexcept { return context_.get(); }

        /**
         * Get capture dimensions.
         */
        [[nodiscard]] u32 width() const noexcept { return width_; }
        [[nodiscard]] u32 height() const noexcept { return height_; }

        /**
         * Check if capture is initialized.
         */
        [[nodiscard]] bool initialized() const noexcept { return initialized_; }

        /**
         * Get current FPS.
         */
        [[nodiscard]] f64 fps() const noexcept { return fps_; }

        /**
         * Get capture statistics.
         */
        struct Stats
        {
            u64 frames_captured = 0;
            u64 frames_dropped = 0;
            f64 avg_capture_time_ms = 0;
            f64 avg_copy_time_ms = 0;
        };
        [[nodiscard]] Stats stats() const noexcept { return stats_; }

    private:
        bool create_device();
        bool create_duplication(u32 monitor_index);
        bool create_staging_texture();
        bool reinit_duplication();

        // D3D11 objects
        ComPtr<ID3D11Device> device_;
        ComPtr<ID3D11DeviceContext> context_;
        ComPtr<IDXGIOutputDuplication> duplication_;
        ComPtr<ID3D11Texture2D> staging_texture_;

        // Adapter and output
        ComPtr<IDXGIAdapter1> adapter_;
        ComPtr<IDXGIOutput1> output_;
        u32 monitor_index_ = 0;

        // Window capture (optional)
        HWND target_window_ = nullptr;
        RECT window_rect_{};
        RECT monitor_rect_{};            // Monitor desktop coordinates
        std::vector<u8> clipped_buffer_; // Buffer for clipped window data
        u32 clipped_width_ = 0;
        u32 clipped_height_ = 0;

        // Private helper methods
        bool update_window_rect();
        bool clip_to_window(CapturedFrame &frame);

        // State
        bool initialized_ = false;
        u32 width_ = 0;
        u32 height_ = 0;
        u32 frame_id_ = 0;

        // Statistics
        Stats stats_;
        FPSCounter fps_counter_;
        f64 fps_ = 0;
        f64 capture_time_accum_ = 0;
        f64 copy_time_accum_ = 0;
        u32 time_sample_count_ = 0;
    };

    /**
     * Capture manager with automatic recovery and window tracking.
     */
    class CaptureManager
    {
    public:
        CaptureManager();
        ~CaptureManager();

        /**
         * Initialize capture system.
         */
        bool init();

        /**
         * Set capture source to a monitor.
         */
        bool set_monitor(u32 monitor_index);

        /**
         * Set capture source to a window.
         */
        bool set_window(HWND hwnd);

        /**
         * Set capture source to a window by title (partial match).
         */
        bool set_window_by_title(std::wstring_view title);

        /**
         * Capture the next frame with automatic recovery.
         */
        bool capture(CapturedFrame &frame, u32 timeout_ms = 16);

        /**
         * Copy frame to CPU memory.
         */
        bool copy_to_cpu(CapturedFrame &frame);

        /**
         * Release frame resources.
         */
        void release_frame(CapturedFrame &frame);

        /**
         * Get the underlying capture object.
         */
        [[nodiscard]] DXGICapture &capture() noexcept { return capture_; }

        /**
         * Refresh the list of available windows.
         */
        std::vector<WindowInfo> refresh_windows();

        /**
         * Get selected window info.
         */
        [[nodiscard]] const WindowInfo *selected_window() const noexcept
        {
            return selected_window_.hwnd ? &selected_window_ : nullptr;
        }

    private:
        DXGICapture capture_;
        WindowInfo selected_window_{};
        bool use_window_capture_ = false;
        u32 recovery_attempts_ = 0;
        static constexpr u32 MAX_RECOVERY_ATTEMPTS = 3;
    };

} // namespace vrs
