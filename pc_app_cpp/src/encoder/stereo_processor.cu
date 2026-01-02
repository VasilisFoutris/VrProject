/**
 * VR Streamer - CUDA Stereo Processor Kernels
 * GPU-accelerated stereo frame creation for VR.
 */

#include <cuda_runtime.h>
#include <device_launch_parameters.h>
#include <cstdint>

namespace vrs
{

    using u8 = uint8_t;
    using u32 = uint32_t;
    using i32 = int32_t;
    using f32 = float;

    // ============================================================================
    // CUDA Kernels
    // ============================================================================

    /**
     * Stereo frame creation kernel.
     * Creates side-by-side VR frame with eye separation.
     */
    __global__ void stereo_kernel(
        const u8 *__restrict__ input,
        u8 *__restrict__ output,
        u32 input_width, u32 input_height, u32 input_pitch,
        u32 output_width, u32 output_height,
        u32 input_channels,
        f32 x_scale, f32 y_scale,
        u32 separation_pixels)
    {
        const u32 x = blockIdx.x * blockDim.x + threadIdx.x;
        const u32 y = blockIdx.y * blockDim.y + threadIdx.y;

        if (x >= output_width || y >= output_height)
            return;

        const u32 half_width = output_width / 2;
        const u32 output_pitch = output_width * 3;

        // Determine which eye and calculate source position
        u32 src_x;
        if (x < half_width)
        {
            // Left eye - sample from left part
            src_x = static_cast<u32>(x * x_scale);
            if (src_x + separation_pixels < input_width)
            {
                src_x = min(src_x, input_width - separation_pixels - 1);
            }
        }
        else
        {
            // Right eye - sample with separation offset
            src_x = static_cast<u32>((x - half_width) * x_scale) + separation_pixels;
            src_x = min(src_x, input_width - 1);
        }

        const u32 src_y = static_cast<u32>(y * y_scale);

        // Read source pixel
        const u8 *src_pixel = input + src_y * input_pitch + src_x * input_channels;
        u8 *dst_pixel = output + y * output_pitch + x * 3;

        // Copy BGR (ignore alpha if present)
        dst_pixel[0] = src_pixel[0];
        dst_pixel[1] = src_pixel[1];
        dst_pixel[2] = src_pixel[2];
    }

    /**
     * Bilinear interpolation stereo kernel for higher quality.
     */
    __global__ void stereo_bilinear_kernel(
        const u8 *__restrict__ input,
        u8 *__restrict__ output,
        u32 input_width, u32 input_height, u32 input_pitch,
        u32 output_width, u32 output_height,
        u32 input_channels,
        f32 x_scale, f32 y_scale,
        u32 separation_pixels)
    {
        const u32 x = blockIdx.x * blockDim.x + threadIdx.x;
        const u32 y = blockIdx.y * blockDim.y + threadIdx.y;

        if (x >= output_width || y >= output_height)
            return;

        const u32 half_width = output_width / 2;
        const u32 output_pitch = output_width * 3;

        // Calculate source position with sub-pixel precision
        f32 src_x_f;
        if (x < half_width)
        {
            src_x_f = x * x_scale;
        }
        else
        {
            src_x_f = (x - half_width) * x_scale + separation_pixels;
        }

        const f32 src_y_f = y * y_scale;

        // Clamp to valid range
        src_x_f = fminf(fmaxf(src_x_f, 0.0f), input_width - 1.001f);
        const f32 src_y_clamped = fminf(fmaxf(src_y_f, 0.0f), input_height - 1.001f);

        // Bilinear interpolation coordinates
        const u32 x0 = static_cast<u32>(src_x_f);
        const u32 y0 = static_cast<u32>(src_y_clamped);
        const u32 x1 = min(x0 + 1, input_width - 1);
        const u32 y1 = min(y0 + 1, input_height - 1);

        const f32 x_frac = src_x_f - x0;
        const f32 y_frac = src_y_clamped - y0;
        const f32 x_frac_inv = 1.0f - x_frac;
        const f32 y_frac_inv = 1.0f - y_frac;

        // Sample 4 pixels
        const u8 *p00 = input + y0 * input_pitch + x0 * input_channels;
        const u8 *p01 = input + y0 * input_pitch + x1 * input_channels;
        const u8 *p10 = input + y1 * input_pitch + x0 * input_channels;
        const u8 *p11 = input + y1 * input_pitch + x1 * input_channels;

        u8 *dst_pixel = output + y * output_pitch + x * 3;

// Interpolate each channel
#pragma unroll
        for (int c = 0; c < 3; ++c)
        {
            f32 v = p00[c] * x_frac_inv * y_frac_inv +
                    p01[c] * x_frac * y_frac_inv +
                    p10[c] * x_frac_inv * y_frac +
                    p11[c] * x_frac * y_frac;
            dst_pixel[c] = static_cast<u8>(fminf(fmaxf(v + 0.5f, 0.0f), 255.0f));
        }
    }

    /**
     * BGRA to BGR conversion kernel.
     */
    __global__ void bgra_to_bgr_kernel(
        const u8 *__restrict__ input,
        u8 *__restrict__ output,
        u32 width, u32 height,
        u32 input_pitch, u32 output_pitch)
    {
        const u32 x = blockIdx.x * blockDim.x + threadIdx.x;
        const u32 y = blockIdx.y * blockDim.y + threadIdx.y;

        if (x >= width || y >= height)
            return;

        const u8 *src = input + y * input_pitch + x * 4;
        u8 *dst = output + y * output_pitch + x * 3;

        dst[0] = src[0];
        dst[1] = src[1];
        dst[2] = src[2];
    }

    // ============================================================================
    // Host Functions
    // ============================================================================

    extern "C"
    {

        /**
         * Process stereo frame on GPU.
         */
        bool cuda_process_stereo(
            const u8 *input_gpu,
            u8 *output_gpu,
            u32 input_width, u32 input_height, u32 input_pitch,
            u32 output_width, u32 output_height,
            u32 input_channels,
            f32 downscale_factor,
            f32 eye_separation,
            void *stream)
        {
            cudaStream_t cuda_stream = static_cast<cudaStream_t>(stream);

            const u32 half_width = output_width / 2;
            const f32 x_scale = static_cast<f32>(input_width) / half_width;
            const f32 y_scale = static_cast<f32>(input_height) / output_height;
            const u32 separation_pixels = static_cast<u32>(input_width * eye_separation);

            // Configure kernel launch
            dim3 block(16, 16);
            dim3 grid(
                (output_width + block.x - 1) / block.x,
                (output_height + block.y - 1) / block.y);

            // Launch kernel
            stereo_kernel<<<grid, block, 0, cuda_stream>>>(
                input_gpu, output_gpu,
                input_width, input_height, input_pitch,
                output_width, output_height,
                input_channels,
                x_scale, y_scale,
                separation_pixels);

            return cudaGetLastError() == cudaSuccess;
        }

        /**
         * Process stereo frame with bilinear interpolation.
         */
        bool cuda_process_stereo_bilinear(
            const u8 *input_gpu,
            u8 *output_gpu,
            u32 input_width, u32 input_height, u32 input_pitch,
            u32 output_width, u32 output_height,
            u32 input_channels,
            f32 downscale_factor,
            f32 eye_separation,
            void *stream)
        {
            cudaStream_t cuda_stream = static_cast<cudaStream_t>(stream);

            const u32 half_width = output_width / 2;
            const f32 x_scale = static_cast<f32>(input_width) / half_width;
            const f32 y_scale = static_cast<f32>(input_height) / output_height;
            const u32 separation_pixels = static_cast<u32>(input_width * eye_separation);

            dim3 block(16, 16);
            dim3 grid(
                (output_width + block.x - 1) / block.x,
                (output_height + block.y - 1) / block.y);

            stereo_bilinear_kernel<<<grid, block, 0, cuda_stream>>>(
                input_gpu, output_gpu,
                input_width, input_height, input_pitch,
                output_width, output_height,
                input_channels,
                x_scale, y_scale,
                separation_pixels);

            return cudaGetLastError() == cudaSuccess;
        }

        /**
         * Convert BGRA to BGR on GPU.
         */
        bool cuda_bgra_to_bgr(
            const u8 *input_gpu,
            u8 *output_gpu,
            u32 width, u32 height,
            u32 input_pitch, u32 output_pitch,
            void *stream)
        {
            cudaStream_t cuda_stream = static_cast<cudaStream_t>(stream);

            dim3 block(32, 8);
            dim3 grid(
                (width + block.x - 1) / block.x,
                (height + block.y - 1) / block.y);

            bgra_to_bgr_kernel<<<grid, block, 0, cuda_stream>>>(
                input_gpu, output_gpu,
                width, height,
                input_pitch, output_pitch);

            return cudaGetLastError() == cudaSuccess;
        }

        /**
         * Allocate GPU memory.
         */
        void *cuda_alloc(size_t size)
        {
            void *ptr = nullptr;
            cudaError_t err = cudaMalloc(&ptr, size);
            return (err == cudaSuccess) ? ptr : nullptr;
        }

        /**
         * Free GPU memory.
         */
        void cuda_free(void *ptr)
        {
            if (ptr)
                cudaFree(ptr);
        }

        /**
         * Copy data to GPU.
         */
        bool cuda_upload(void *dst, const void *src, size_t size, void *stream)
        {
            cudaError_t err = cudaMemcpyAsync(
                dst, src, size,
                cudaMemcpyHostToDevice,
                static_cast<cudaStream_t>(stream));
            return err == cudaSuccess;
        }

        /**
         * Copy data from GPU.
         */
        bool cuda_download(void *dst, const void *src, size_t size, void *stream)
        {
            cudaError_t err = cudaMemcpyAsync(
                dst, src, size,
                cudaMemcpyDeviceToHost,
                static_cast<cudaStream_t>(stream));
            return err == cudaSuccess;
        }

        /**
         * Synchronize stream.
         */
        bool cuda_sync(void *stream)
        {
            cudaError_t err = cudaStreamSynchronize(static_cast<cudaStream_t>(stream));
            return err == cudaSuccess;
        }

        /**
         * Create CUDA stream.
         */
        void *cuda_create_stream()
        {
            cudaStream_t stream;
            cudaError_t err = cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking);
            return (err == cudaSuccess) ? stream : nullptr;
        }

        /**
         * Destroy CUDA stream.
         */
        void cuda_destroy_stream(void *stream)
        {
            if (stream)
            {
                cudaStreamDestroy(static_cast<cudaStream_t>(stream));
            }
        }

    } // extern "C"

} // namespace vrs
