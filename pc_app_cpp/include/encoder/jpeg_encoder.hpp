#pragma once
/**
 * VR Streamer - JPEG Encoder
 * High-performance JPEG encoding using TurboJPEG and nvJPEG.
 * SIMD-optimized CPU fallback with GPU acceleration support.
 */

#include "../core/common.hpp"
#include "../core/memory_pool.hpp"

// Forward declarations for CUDA/nvJPEG
struct nvjpegHandle;
struct nvjpegEncoderState;
struct nvjpegEncoderParams;

namespace vrs
{

    /**
     * JPEG encoder interface.
     */
    class IJPEGEncoder
    {
    public:
        virtual ~IJPEGEncoder() = default;

        /**
         * Encode BGR/BGRA image to JPEG.
         * @param input Input image data (BGR or BGRA format)
         * @param width Image width
         * @param height Image height
         * @param pitch Row pitch in bytes
         * @param channels 3 for BGR, 4 for BGRA
         * @param quality JPEG quality (1-100)
         * @param output Output buffer for encoded data
         * @return Size of encoded data, or 0 on failure
         */
        virtual size_t encode(
            const u8 *input,
            u32 width, u32 height,
            u32 pitch, u32 channels,
            u32 quality,
            std::vector<u8> &output) = 0;

        /**
         * Check if encoder is available.
         */
        [[nodiscard]] virtual bool available() const = 0;

        /**
         * Get encoder name.
         */
        [[nodiscard]] virtual std::string_view name() const = 0;

        /**
         * Get last encode time in milliseconds.
         */
        [[nodiscard]] virtual f64 last_encode_time_ms() const = 0;
    };

    /**
     * TurboJPEG encoder - SIMD-optimized CPU encoding.
     * Uses libjpeg-turbo for fast JPEG compression with AVX2/SSE support.
     */
    class TurboJPEGEncoder : public IJPEGEncoder
    {
    public:
        TurboJPEGEncoder();
        ~TurboJPEGEncoder() override;

        TurboJPEGEncoder(const TurboJPEGEncoder &) = delete;
        TurboJPEGEncoder &operator=(const TurboJPEGEncoder &) = delete;

        size_t encode(
            const u8 *input,
            u32 width, u32 height,
            u32 pitch, u32 channels,
            u32 quality,
            std::vector<u8> &output) override;

        [[nodiscard]] bool available() const override { return handle_ != nullptr; }
        [[nodiscard]] std::string_view name() const override { return "TurboJPEG"; }
        [[nodiscard]] f64 last_encode_time_ms() const override { return last_encode_time_; }

    private:
        void *handle_ = nullptr; // tjhandle
        f64 last_encode_time_ = 0;
    };

    /**
     * nvJPEG encoder - GPU-accelerated JPEG encoding using NVIDIA nvJPEG.
     * Offloads encoding to GPU for minimal CPU usage.
     */
    class NvJPEGEncoder : public IJPEGEncoder
    {
    public:
        NvJPEGEncoder();
        ~NvJPEGEncoder() override;

        NvJPEGEncoder(const NvJPEGEncoder &) = delete;
        NvJPEGEncoder &operator=(const NvJPEGEncoder &) = delete;

        /**
         * Initialize the encoder.
         */
        bool init();

        /**
         * Shutdown and release resources.
         */
        void shutdown();

        size_t encode(
            const u8 *input,
            u32 width, u32 height,
            u32 pitch, u32 channels,
            u32 quality,
            std::vector<u8> &output) override;

        /**
         * Encode directly from GPU texture (zero-copy).
         */
        size_t encode_gpu(
            void *cuda_ptr,
            u32 width, u32 height,
            u32 pitch,
            u32 quality,
            std::vector<u8> &output);

        [[nodiscard]] bool available() const override { return initialized_; }
        [[nodiscard]] std::string_view name() const override { return "nvJPEG"; }
        [[nodiscard]] f64 last_encode_time_ms() const override { return last_encode_time_; }

    private:
        bool initialized_ = false;
        void *nvjpeg_handle_ = nullptr;  // nvjpegHandle_t
        void *encoder_state_ = nullptr;  // nvjpegEncoderState_t
        void *encoder_params_ = nullptr; // nvjpegEncoderParams_t
        void *cuda_stream_ = nullptr;    // cudaStream_t
        void *gpu_buffer_ = nullptr;     // Device memory for input
        size_t gpu_buffer_size_ = 0;
        f64 last_encode_time_ = 0;
    };

    /**
     * OpenCV JPEG encoder - Fallback when TurboJPEG is unavailable.
     */
    class OpenCVJPEGEncoder : public IJPEGEncoder
    {
    public:
        OpenCVJPEGEncoder() = default;
        ~OpenCVJPEGEncoder() override = default;

        size_t encode(
            const u8 *input,
            u32 width, u32 height,
            u32 pitch, u32 channels,
            u32 quality,
            std::vector<u8> &output) override;

        [[nodiscard]] bool available() const override { return true; }
        [[nodiscard]] std::string_view name() const override { return "OpenCV"; }
        [[nodiscard]] f64 last_encode_time_ms() const override { return last_encode_time_; }

    private:
        f64 last_encode_time_ = 0;
    };

    /**
     * Automatic encoder selection - picks the best available encoder.
     */
    class AutoJPEGEncoder : public IJPEGEncoder
    {
    public:
        AutoJPEGEncoder();
        ~AutoJPEGEncoder() override = default;

        size_t encode(
            const u8 *input,
            u32 width, u32 height,
            u32 pitch, u32 channels,
            u32 quality,
            std::vector<u8> &output) override;

        [[nodiscard]] bool available() const override { return best_encoder_ != nullptr; }
        [[nodiscard]] std::string_view name() const override;
        [[nodiscard]] f64 last_encode_time_ms() const override;

        /**
         * Get the selected encoder.
         */
        [[nodiscard]] IJPEGEncoder *selected() const { return best_encoder_; }

    private:
        std::unique_ptr<NvJPEGEncoder> nvjpeg_;
        std::unique_ptr<TurboJPEGEncoder> turbojpeg_;
        std::unique_ptr<OpenCVJPEGEncoder> opencv_;
        IJPEGEncoder *best_encoder_ = nullptr;
    };

} // namespace vrs
