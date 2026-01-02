#pragma once
/**
 * VR Streamer - Stereo Frame Processor
 * GPU-accelerated VR stereo frame creation using CUDA.
 * Converts single frames to side-by-side VR format.
 */

#include "../core/common.hpp"
#include "../core/config.hpp"

namespace vrs
{

    /**
     * Stereo processing statistics.
     */
    struct StereoStats
    {
        u64 frames_processed = 0;
        f64 avg_process_time_ms = 0;
        f64 last_process_time_ms = 0;
    };

    /**
     * Stereo frame processor interface.
     */
    class IStereoProcessor
    {
    public:
        virtual ~IStereoProcessor() = default;

        /**
         * Process a frame into stereo VR format.
         * @param input Input BGR/BGRA image
         * @param input_width Input width
         * @param input_height Input height
         * @param input_pitch Input row pitch
         * @param input_channels 3 or 4
         * @param output Output buffer (must be pre-allocated)
         * @param output_width Output width (should be same as input for SBS)
         * @param output_height Output height
         * @param eye_separation Eye separation factor (0.0 to 0.1)
         * @return Output pitch, or 0 on failure
         */
        virtual u32 process(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 eye_separation) = 0;

        /**
         * Process with downscaling.
         */
        virtual u32 process_scaled(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 downscale_factor,
            f32 eye_separation) = 0;

        [[nodiscard]] virtual bool available() const = 0;
        [[nodiscard]] virtual std::string_view name() const = 0;
        [[nodiscard]] virtual StereoStats stats() const = 0;
    };

    /**
     * CUDA-accelerated stereo processor.
     * Uses GPU for parallel image processing.
     */
    class CUDAStereoProcessor : public IStereoProcessor
    {
    public:
        CUDAStereoProcessor();
        ~CUDAStereoProcessor() override;

        CUDAStereoProcessor(const CUDAStereoProcessor &) = delete;
        CUDAStereoProcessor &operator=(const CUDAStereoProcessor &) = delete;

        /**
         * Initialize CUDA resources.
         */
        bool init(u32 max_width = 3840, u32 max_height = 2160);

        /**
         * Shutdown and release resources.
         */
        void shutdown();

        u32 process(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 eye_separation) override;

        u32 process_scaled(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 downscale_factor,
            f32 eye_separation) override;

        /**
         * Process directly on GPU memory (zero-copy).
         */
        u32 process_gpu(
            void *input_cuda,
            u32 input_width, u32 input_height,
            u32 input_pitch,
            void *output_cuda,
            u32 output_width, u32 output_height,
            f32 downscale_factor,
            f32 eye_separation);

        [[nodiscard]] bool available() const override { return initialized_; }
        [[nodiscard]] std::string_view name() const override { return "CUDA"; }
        [[nodiscard]] StereoStats stats() const override { return stats_; }

    private:
        bool initialized_ = false;
        void *cuda_stream_ = nullptr;
        void *input_buffer_ = nullptr;
        void *output_buffer_ = nullptr;
        size_t input_buffer_size_ = 0;
        size_t output_buffer_size_ = 0;
        StereoStats stats_;
    };

    /**
     * CPU stereo processor with SIMD optimizations.
     * Uses AVX2/SSE for parallel processing when available.
     */
    class CPUStereoProcessor : public IStereoProcessor
    {
    public:
        CPUStereoProcessor() = default;
        ~CPUStereoProcessor() override = default;

        u32 process(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 eye_separation) override;

        u32 process_scaled(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 downscale_factor,
            f32 eye_separation) override;

        [[nodiscard]] bool available() const override { return true; }
        [[nodiscard]] std::string_view name() const override { return "CPU"; }
        [[nodiscard]] StereoStats stats() const override { return stats_; }

    private:
        // SIMD-optimized resize and copy functions
        void resize_bilinear_simd(
            const u8 *src, u32 src_width, u32 src_height, u32 src_pitch,
            u8 *dst, u32 dst_width, u32 dst_height, u32 dst_pitch,
            u32 channels);

        void resize_nearest_simd(
            const u8 *src, u32 src_width, u32 src_height, u32 src_pitch,
            u8 *dst, u32 dst_width, u32 dst_height, u32 dst_pitch,
            u32 channels);

        StereoStats stats_;
    };

    /**
     * Auto-selecting stereo processor.
     */
    class AutoStereoProcessor : public IStereoProcessor
    {
    public:
        AutoStereoProcessor();
        ~AutoStereoProcessor() override = default;

        u32 process(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 eye_separation) override;

        u32 process_scaled(
            const u8 *input,
            u32 input_width, u32 input_height,
            u32 input_pitch, u32 input_channels,
            u8 *output,
            u32 output_width, u32 output_height,
            f32 downscale_factor,
            f32 eye_separation) override;

        [[nodiscard]] bool available() const override { return best_ != nullptr; }
        [[nodiscard]] std::string_view name() const override;
        [[nodiscard]] StereoStats stats() const override;

    private:
        std::unique_ptr<CUDAStereoProcessor> cuda_;
        std::unique_ptr<CPUStereoProcessor> cpu_;
        IStereoProcessor *best_ = nullptr;
    };

    /**
     * Complete VR frame encoder pipeline.
     * Combines stereo processing and JPEG encoding.
     */
    class VRFrameEncoder
    {
    public:
        explicit VRFrameEncoder(const EncoderConfig &config);
        ~VRFrameEncoder();

        VRFrameEncoder(const VRFrameEncoder &) = delete;
        VRFrameEncoder &operator=(const VRFrameEncoder &) = delete;

        /**
         * Encode a frame for VR streaming.
         * @param input Input image data
         * @param width Image width
         * @param height Image height
         * @param pitch Row pitch
         * @param channels 3 or 4
         * @param output Output compressed data
         * @return Size of compressed output, or 0 on failure
         */
        size_t encode(
            const u8 *input,
            u32 width, u32 height,
            u32 pitch, u32 channels,
            std::vector<u8> &output);

        /**
         * Update configuration.
         */
        void update_config(const EncoderConfig &config);

        /**
         * Get encoding statistics.
         */
        struct Stats
        {
            f64 stereo_time_ms = 0;
            f64 encode_time_ms = 0;
            f64 total_time_ms = 0;
            u64 frames_encoded = 0;
            u64 bytes_encoded = 0;
            f64 compression_ratio = 0;
        };
        [[nodiscard]] Stats stats() const { return stats_; }

        /**
         * Get the current configuration.
         */
        [[nodiscard]] const EncoderConfig &config() const { return config_; }

    private:
        EncoderConfig config_;
        std::unique_ptr<AutoStereoProcessor> stereo_processor_;
        std::unique_ptr<class AutoJPEGEncoder> jpeg_encoder_;

        // Work buffers
        std::vector<u8> stereo_buffer_;

        Stats stats_;
    };

} // namespace vrs
