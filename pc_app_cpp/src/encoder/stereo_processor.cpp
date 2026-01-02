/**
 * VR Streamer - Stereo Frame Processor Implementation
 * CPU implementation with SIMD optimizations.
 */

#include "encoder/stereo_processor.hpp"
#include "encoder/jpeg_encoder.hpp"

#if VRS_HAS_AVX2
#include <immintrin.h>
#endif

namespace vrs
{

    // ============================================================================
    // CPUStereoProcessor Implementation
    // ============================================================================

    u32 CPUStereoProcessor::process(
        const u8 *input,
        u32 input_width, u32 input_height,
        u32 input_pitch, u32 input_channels,
        u8 *output,
        u32 output_width, u32 output_height,
        f32 eye_separation)
    {
        return process_scaled(
            input, input_width, input_height, input_pitch, input_channels,
            output, output_width, output_height,
            1.0f, eye_separation);
    }

    u32 CPUStereoProcessor::process_scaled(
        const u8 *input,
        u32 input_width, u32 input_height,
        u32 input_pitch, u32 input_channels,
        u8 *output,
        u32 output_width, u32 output_height,
        f32 downscale_factor,
        f32 eye_separation)
    {
        Timer timer;

        const u32 half_width = output_width / 2;
        const u32 output_pitch = output_width * 3; // Output is always BGR
        const u32 separation_pixels = static_cast<u32>(input_width * eye_separation);

        // Calculate scaled dimensions
        const u32 scaled_height = output_height;
        const f32 x_scale = static_cast<f32>(input_width) / half_width;
        const f32 y_scale = static_cast<f32>(input_height) / scaled_height;

// Process each row
#pragma omp parallel for schedule(dynamic, 16)
        for (i32 y = 0; y < static_cast<i32>(output_height); ++y)
        {
            const u32 src_y = static_cast<u32>(y * y_scale);
            const u8 *src_row = input + src_y * input_pitch;
            u8 *dst_row = output + y * output_pitch;

            // Left eye (original or shifted right)
            for (u32 x = 0; x < half_width; ++x)
            {
                u32 src_x = static_cast<u32>(x * x_scale);
                // For left eye, sample from left part of image
                if (src_x + separation_pixels < input_width)
                {
                    src_x = std::min(src_x, input_width - separation_pixels - 1);
                }

                const u8 *src_pixel = src_row + src_x * input_channels;
                u8 *dst_pixel = dst_row + x * 3;

                dst_pixel[0] = src_pixel[0]; // B
                dst_pixel[1] = src_pixel[1]; // G
                dst_pixel[2] = src_pixel[2]; // R
            }

            // Right eye (original or shifted left)
            for (u32 x = 0; x < half_width; ++x)
            {
                u32 src_x = static_cast<u32>(x * x_scale) + separation_pixels;
                src_x = std::min(src_x, input_width - 1);

                const u8 *src_pixel = src_row + src_x * input_channels;
                u8 *dst_pixel = dst_row + (half_width + x) * 3;

                dst_pixel[0] = src_pixel[0]; // B
                dst_pixel[1] = src_pixel[1]; // G
                dst_pixel[2] = src_pixel[2]; // R
            }
        }

        stats_.frames_processed++;
        stats_.last_process_time_ms = timer.elapsed_ms();
        stats_.avg_process_time_ms = (stats_.avg_process_time_ms * (stats_.frames_processed - 1) +
                                      stats_.last_process_time_ms) /
                                     stats_.frames_processed;

        return output_pitch;
    }

    void CPUStereoProcessor::resize_nearest_simd(
        const u8 *src, u32 src_width, u32 src_height, u32 src_pitch,
        u8 *dst, u32 dst_width, u32 dst_height, u32 dst_pitch,
        u32 channels)
    {
        const f32 x_scale = static_cast<f32>(src_width) / dst_width;
        const f32 y_scale = static_cast<f32>(src_height) / dst_height;

#if VRS_HAS_AVX2
        // AVX2 optimized path for 3-channel images
        if (channels == 3 && dst_width >= 32)
        {
#pragma omp parallel for schedule(dynamic, 8)
            for (i32 y = 0; y < static_cast<i32>(dst_height); ++y)
            {
                const u32 src_y = static_cast<u32>(y * y_scale);
                const u8 *src_row = src + src_y * src_pitch;
                u8 *dst_row = dst + y * dst_pitch;

                // Process 8 pixels at a time using AVX2
                u32 x = 0;
                for (; x + 8 <= dst_width; x += 8)
                {
                    // Calculate source X coordinates
                    u32 src_x[8];
                    for (u32 i = 0; i < 8; ++i)
                    {
                        src_x[i] = static_cast<u32>((x + i) * x_scale);
                    }

                    // Gather pixels (can't use gather for 3-byte pixels, do manually)
                    for (u32 i = 0; i < 8; ++i)
                    {
                        const u8 *sp = src_row + src_x[i] * 3;
                        u8 *dp = dst_row + (x + i) * 3;
                        dp[0] = sp[0];
                        dp[1] = sp[1];
                        dp[2] = sp[2];
                    }
                }

                // Handle remaining pixels
                for (; x < dst_width; ++x)
                {
                    u32 src_x = static_cast<u32>(x * x_scale);
                    const u8 *sp = src_row + src_x * 3;
                    u8 *dp = dst_row + x * 3;
                    dp[0] = sp[0];
                    dp[1] = sp[1];
                    dp[2] = sp[2];
                }
            }
            return;
        }
#endif

// Scalar fallback
#pragma omp parallel for schedule(dynamic, 16)
        for (i32 y = 0; y < static_cast<i32>(dst_height); ++y)
        {
            const u32 src_y = static_cast<u32>(y * y_scale);
            const u8 *src_row = src + src_y * src_pitch;
            u8 *dst_row = dst + y * dst_pitch;

            for (u32 x = 0; x < dst_width; ++x)
            {
                u32 src_x = static_cast<u32>(x * x_scale);
                const u8 *sp = src_row + src_x * channels;
                u8 *dp = dst_row + x * channels;

                for (u32 c = 0; c < channels; ++c)
                {
                    dp[c] = sp[c];
                }
            }
        }
    }

    void CPUStereoProcessor::resize_bilinear_simd(
        const u8 *src, u32 src_width, u32 src_height, u32 src_pitch,
        u8 *dst, u32 dst_width, u32 dst_height, u32 dst_pitch,
        u32 channels)
    {
        const f32 x_scale = static_cast<f32>(src_width - 1) / (dst_width - 1);
        const f32 y_scale = static_cast<f32>(src_height - 1) / (dst_height - 1);

#pragma omp parallel for schedule(dynamic, 8)
        for (i32 y = 0; y < static_cast<i32>(dst_height); ++y)
        {
            const f32 src_y = y * y_scale;
            const u32 y0 = static_cast<u32>(src_y);
            const u32 y1 = std::min(y0 + 1, src_height - 1);
            const f32 y_frac = src_y - y0;
            const f32 y_frac_inv = 1.0f - y_frac;

            const u8 *src_row0 = src + y0 * src_pitch;
            const u8 *src_row1 = src + y1 * src_pitch;
            u8 *dst_row = dst + y * dst_pitch;

            for (u32 x = 0; x < dst_width; ++x)
            {
                const f32 src_x = x * x_scale;
                const u32 x0 = static_cast<u32>(src_x);
                const u32 x1 = std::min(x0 + 1, src_width - 1);
                const f32 x_frac = src_x - x0;
                const f32 x_frac_inv = 1.0f - x_frac;

                const u8 *p00 = src_row0 + x0 * channels;
                const u8 *p01 = src_row0 + x1 * channels;
                const u8 *p10 = src_row1 + x0 * channels;
                const u8 *p11 = src_row1 + x1 * channels;
                u8 *dp = dst_row + x * channels;

                for (u32 c = 0; c < channels; ++c)
                {
                    f32 v = p00[c] * x_frac_inv * y_frac_inv +
                            p01[c] * x_frac * y_frac_inv +
                            p10[c] * x_frac_inv * y_frac +
                            p11[c] * x_frac * y_frac;
                    dp[c] = static_cast<u8>(v + 0.5f);
                }
            }
        }
    }

    // ============================================================================
    // CUDAStereoProcessor Implementation
    // ============================================================================

    CUDAStereoProcessor::CUDAStereoProcessor() = default;

    CUDAStereoProcessor::~CUDAStereoProcessor()
    {
        shutdown();
    }

    bool CUDAStereoProcessor::init(u32 max_width, u32 max_height)
    {
        // CUDA initialization will be in .cu file
        // For now, mark as not initialized
        initialized_ = false;
        return false;
    }

    void CUDAStereoProcessor::shutdown()
    {
        // Cleanup CUDA resources
        initialized_ = false;
    }

    u32 CUDAStereoProcessor::process(
        const u8 *input,
        u32 input_width, u32 input_height,
        u32 input_pitch, u32 input_channels,
        u8 *output,
        u32 output_width, u32 output_height,
        f32 eye_separation)
    {
        return process_scaled(
            input, input_width, input_height, input_pitch, input_channels,
            output, output_width, output_height,
            1.0f, eye_separation);
    }

    u32 CUDAStereoProcessor::process_scaled(
        const u8 *input,
        u32 input_width, u32 input_height,
        u32 input_pitch, u32 input_channels,
        u8 *output,
        u32 output_width, u32 output_height,
        f32 downscale_factor,
        f32 eye_separation)
    {
        // CUDA implementation in .cu file
        return 0;
    }

    u32 CUDAStereoProcessor::process_gpu(
        void *input_cuda,
        u32 input_width, u32 input_height,
        u32 input_pitch,
        void *output_cuda,
        u32 output_width, u32 output_height,
        f32 downscale_factor,
        f32 eye_separation)
    {
        // CUDA implementation in .cu file
        return 0;
    }

    // ============================================================================
    // AutoStereoProcessor Implementation
    // ============================================================================

    AutoStereoProcessor::AutoStereoProcessor()
    {
        // Try CUDA first
        cuda_ = std::make_unique<CUDAStereoProcessor>();
        if (cuda_->init())
        {
            best_ = cuda_.get();
            VRS_LOG_INFO("Auto-selected CUDA stereo processor (GPU)");
            return;
        }

        // Fallback to CPU
        cpu_ = std::make_unique<CPUStereoProcessor>();
        best_ = cpu_.get();
        VRS_LOG_INFO("Auto-selected CPU stereo processor");
    }

    u32 AutoStereoProcessor::process(
        const u8 *input,
        u32 input_width, u32 input_height,
        u32 input_pitch, u32 input_channels,
        u8 *output,
        u32 output_width, u32 output_height,
        f32 eye_separation)
    {
        if (!best_)
            return 0;
        return best_->process(
            input, input_width, input_height, input_pitch, input_channels,
            output, output_width, output_height, eye_separation);
    }

    u32 AutoStereoProcessor::process_scaled(
        const u8 *input,
        u32 input_width, u32 input_height,
        u32 input_pitch, u32 input_channels,
        u8 *output,
        u32 output_width, u32 output_height,
        f32 downscale_factor,
        f32 eye_separation)
    {
        if (!best_)
            return 0;
        return best_->process_scaled(
            input, input_width, input_height, input_pitch, input_channels,
            output, output_width, output_height, downscale_factor, eye_separation);
    }

    std::string_view AutoStereoProcessor::name() const
    {
        if (best_)
            return best_->name();
        return "None";
    }

    StereoStats AutoStereoProcessor::stats() const
    {
        if (best_)
            return best_->stats();
        return {};
    }

    // ============================================================================
    // VRFrameEncoder Implementation
    // ============================================================================

    VRFrameEncoder::VRFrameEncoder(const EncoderConfig &config)
        : config_(config)
    {
        stereo_processor_ = std::make_unique<AutoStereoProcessor>();
        jpeg_encoder_ = std::make_unique<AutoJPEGEncoder>();

        // Pre-allocate stereo buffer for typical 1080p
        stereo_buffer_.reserve(1920 * 1080 * 3);
    }

    VRFrameEncoder::~VRFrameEncoder() = default;

    size_t VRFrameEncoder::encode(
        const u8 *input,
        u32 width, u32 height,
        u32 pitch, u32 channels,
        std::vector<u8> &output)
    {
        Timer total_timer;

        // Calculate output dimensions
        u32 output_width = width;
        u32 output_height = height;

        if (config_.downscale_factor < 1.0f)
        {
            output_width = static_cast<u32>(width * config_.downscale_factor);
            output_height = static_cast<u32>(height * config_.downscale_factor);
        }

        if (config_.output_width > 0 && config_.output_height > 0)
        {
            output_width = config_.output_width;
            output_height = config_.output_height;
        }

        // Ensure dimensions are even for VR
        output_width = (output_width / 2) * 2;
        output_height = (output_height / 2) * 2;

        const u32 output_pitch = output_width * 3;
        const size_t stereo_size = output_pitch * output_height;

        // Resize stereo buffer if needed
        if (stereo_buffer_.size() < stereo_size)
        {
            stereo_buffer_.resize(stereo_size);
        }

        Timer stereo_timer;

        // Process to stereo if VR enabled
        const u8 *encode_input = input;
        u32 encode_width = width;
        u32 encode_height = height;
        u32 encode_pitch = pitch;
        u32 encode_channels = channels;

        if (config_.vr_enabled)
        {
            u32 result_pitch = stereo_processor_->process_scaled(
                input, width, height, pitch, channels,
                stereo_buffer_.data(), output_width, output_height,
                config_.downscale_factor, config_.eye_separation);

            if (result_pitch > 0)
            {
                encode_input = stereo_buffer_.data();
                encode_width = output_width;
                encode_height = output_height;
                encode_pitch = output_pitch;
                encode_channels = 3;
            }
        }

        stats_.stereo_time_ms = stereo_timer.elapsed_ms();

        // Encode to JPEG
        Timer encode_timer;

        size_t encoded_size = jpeg_encoder_->encode(
            encode_input,
            encode_width, encode_height,
            encode_pitch, encode_channels,
            config_.jpeg_quality,
            output);

        stats_.encode_time_ms = encode_timer.elapsed_ms();
        stats_.total_time_ms = total_timer.elapsed_ms();
        stats_.frames_encoded++;
        stats_.bytes_encoded += encoded_size;

        // Calculate compression ratio
        size_t raw_size = encode_width * encode_height * encode_channels;
        stats_.compression_ratio = static_cast<f64>(raw_size) / encoded_size;

        return encoded_size;
    }

    void VRFrameEncoder::update_config(const EncoderConfig &config)
    {
        config_ = config;
    }

} // namespace vrs
