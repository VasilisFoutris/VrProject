/**
 * VR Streamer - JPEG Encoder Implementation
 * High-performance encoding with TurboJPEG and optional nvJPEG.
 */

#include "encoder/jpeg_encoder.hpp"

// TurboJPEG
#include <turbojpeg.h>

// CUDA and nvJPEG (only when CUDA is enabled)
#ifdef HAS_CUDA
#include <cuda_runtime.h>
#include <nvjpeg.h>
#endif

namespace vrs
{

    // ============================================================================
    // TurboJPEGEncoder Implementation
    // ============================================================================

    TurboJPEGEncoder::TurboJPEGEncoder()
    {
        handle_ = tjInitCompress();
        if (!handle_)
        {
            VRS_LOG_WARN("Failed to initialize TurboJPEG");
        }
        else
        {
            VRS_LOG_INFO("TurboJPEG encoder initialized");
        }
    }

    TurboJPEGEncoder::~TurboJPEGEncoder()
    {
        if (handle_)
        {
            tjDestroy(handle_);
        }
    }

    size_t TurboJPEGEncoder::encode(
        const u8 *input,
        u32 width, u32 height,
        u32 pitch, u32 channels,
        u32 quality,
        std::vector<u8> &output)
    {
        if (!handle_)
            return 0;

        Timer timer;

        // Determine pixel format
        int pixel_format = (channels == 4) ? TJPF_BGRA : TJPF_BGR;

        // Estimate output size
        unsigned long jpeg_size = tjBufSize(width, height, TJSAMP_420);

        // Pre-allocate output buffer
        if (output.capacity() < jpeg_size)
        {
            output.reserve(jpeg_size);
        }

        unsigned char *jpeg_buf = nullptr;
        unsigned long actual_size = 0;

        // Encode with fastest subsampling (4:2:0) and no flags for maximum speed
        int result = tjCompress2(
            handle_,
            input,
            width, pitch, height,
            pixel_format,
            &jpeg_buf,
            &actual_size,
            TJSAMP_420, // 4:2:0 subsampling for smaller size
            quality,
            TJFLAG_FASTDCT // Fast DCT
        );

        if (result != 0 || jpeg_buf == nullptr)
        {
            VRS_LOG_ERROR(std::format("TurboJPEG encode failed: {}", tjGetErrorStr()));
            return 0;
        }

        // Copy to output vector
        output.resize(actual_size);
        std::memcpy(output.data(), jpeg_buf, actual_size);

        // Free TurboJPEG buffer
        tjFree(jpeg_buf);

        last_encode_time_ = timer.elapsed_ms();
        return actual_size;
    }

    // ============================================================================
    // NvJPEGEncoder Implementation (CUDA only)
    // ============================================================================

#ifdef HAS_CUDA

    NvJPEGEncoder::NvJPEGEncoder() = default;

    NvJPEGEncoder::~NvJPEGEncoder()
    {
        shutdown();
    }

    bool NvJPEGEncoder::init()
    {
        if (initialized_)
            return true;

        // Create CUDA stream
        cudaError_t cuda_err = cudaStreamCreateWithFlags(
            reinterpret_cast<cudaStream_t *>(&cuda_stream_),
            cudaStreamNonBlocking);
        if (cuda_err != cudaSuccess)
        {
            VRS_LOG_ERROR("Failed to create CUDA stream for nvJPEG");
            return false;
        }

        // Initialize nvJPEG
        nvjpegStatus_t status = nvjpegCreateSimple(
            reinterpret_cast<nvjpegHandle_t *>(&nvjpeg_handle_));
        if (status != NVJPEG_STATUS_SUCCESS)
        {
            VRS_LOG_ERROR(std::format("nvjpegCreateSimple failed: {}", static_cast<int>(status)));
            cudaStreamDestroy(static_cast<cudaStream_t>(cuda_stream_));
            cuda_stream_ = nullptr;
            return false;
        }

        // Create encoder state
        status = nvjpegEncoderStateCreate(
            static_cast<nvjpegHandle_t>(nvjpeg_handle_),
            reinterpret_cast<nvjpegEncoderState_t *>(&encoder_state_),
            static_cast<cudaStream_t>(cuda_stream_));
        if (status != NVJPEG_STATUS_SUCCESS)
        {
            VRS_LOG_ERROR("Failed to create nvJPEG encoder state");
            shutdown();
            return false;
        }

        // Create encoder params
        status = nvjpegEncoderParamsCreate(
            static_cast<nvjpegHandle_t>(nvjpeg_handle_),
            reinterpret_cast<nvjpegEncoderParams_t *>(&encoder_params_),
            static_cast<cudaStream_t>(cuda_stream_));
        if (status != NVJPEG_STATUS_SUCCESS)
        {
            VRS_LOG_ERROR("Failed to create nvJPEG encoder params");
            shutdown();
            return false;
        }

        // Set default encoding parameters
        nvjpegEncoderParamsSetSamplingFactors(
            static_cast<nvjpegEncoderParams_t>(encoder_params_),
            NVJPEG_CSS_420, // 4:2:0 subsampling
            static_cast<cudaStream_t>(cuda_stream_));

        nvjpegEncoderParamsSetOptimizedHuffman(
            static_cast<nvjpegEncoderParams_t>(encoder_params_),
            0, // Disable for speed
            static_cast<cudaStream_t>(cuda_stream_));

        initialized_ = true;
        VRS_LOG_INFO("nvJPEG encoder initialized");
        return true;
    }

    void NvJPEGEncoder::shutdown()
    {
        if (gpu_buffer_)
        {
            cudaFree(gpu_buffer_);
            gpu_buffer_ = nullptr;
            gpu_buffer_size_ = 0;
        }

        if (encoder_params_)
        {
            nvjpegEncoderParamsDestroy(static_cast<nvjpegEncoderParams_t>(encoder_params_));
            encoder_params_ = nullptr;
        }

        if (encoder_state_)
        {
            nvjpegEncoderStateDestroy(static_cast<nvjpegEncoderState_t>(encoder_state_));
            encoder_state_ = nullptr;
        }

        if (nvjpeg_handle_)
        {
            nvjpegDestroy(static_cast<nvjpegHandle_t>(nvjpeg_handle_));
            nvjpeg_handle_ = nullptr;
        }

        if (cuda_stream_)
        {
            cudaStreamDestroy(static_cast<cudaStream_t>(cuda_stream_));
            cuda_stream_ = nullptr;
        }

        initialized_ = false;
    }

    size_t NvJPEGEncoder::encode(
        const u8 *input,
        u32 width, u32 height,
        u32 pitch, u32 channels,
        u32 quality,
        std::vector<u8> &output)
    {
        if (!initialized_)
        {
            if (!init())
                return 0;
        }

        Timer timer;
        (void)channels; // Unused in nvJPEG path

        // Allocate/resize GPU buffer if needed
        size_t required_size = static_cast<size_t>(pitch) * height;
        if (gpu_buffer_size_ < required_size)
        {
            if (gpu_buffer_)
            {
                cudaFree(gpu_buffer_);
            }
            cudaError_t err = cudaMalloc(&gpu_buffer_, required_size);
            if (err != cudaSuccess)
            {
                VRS_LOG_ERROR("Failed to allocate GPU buffer for nvJPEG");
                return 0;
            }
            gpu_buffer_size_ = required_size;
        }

        // Copy input to GPU
        cudaMemcpyAsync(
            gpu_buffer_, input, required_size,
            cudaMemcpyHostToDevice,
            static_cast<cudaStream_t>(cuda_stream_));

        // Encode from GPU memory
        size_t result = encode_gpu(gpu_buffer_, width, height, pitch, quality, output);

        last_encode_time_ = timer.elapsed_ms();
        return result;
    }

    size_t NvJPEGEncoder::encode_gpu(
        void *cuda_ptr,
        u32 width, u32 height,
        u32 pitch,
        u32 quality,
        std::vector<u8> &output)
    {
        if (!initialized_)
            return 0;

        // Set quality
        nvjpegEncoderParamsSetQuality(
            static_cast<nvjpegEncoderParams_t>(encoder_params_),
            quality,
            static_cast<cudaStream_t>(cuda_stream_));

        // Setup image descriptor
        nvjpegImage_t nv_image;
        nv_image.channel[0] = static_cast<unsigned char *>(cuda_ptr);
        nv_image.pitch[0] = pitch;

        // Encode
        nvjpegStatus_t status = nvjpegEncodeImage(
            static_cast<nvjpegHandle_t>(nvjpeg_handle_),
            static_cast<nvjpegEncoderState_t>(encoder_state_),
            static_cast<nvjpegEncoderParams_t>(encoder_params_),
            &nv_image,
            NVJPEG_INPUT_BGRI, // BGR interleaved
            width, height,
            static_cast<cudaStream_t>(cuda_stream_));

        if (status != NVJPEG_STATUS_SUCCESS)
        {
            VRS_LOG_ERROR(std::format("nvjpegEncodeImage failed: {}", static_cast<int>(status)));
            return 0;
        }

        // Get encoded size
        size_t encoded_size = 0;
        status = nvjpegEncodeRetrieveBitstream(
            static_cast<nvjpegHandle_t>(nvjpeg_handle_),
            static_cast<nvjpegEncoderState_t>(encoder_state_),
            nullptr,
            &encoded_size,
            static_cast<cudaStream_t>(cuda_stream_));

        if (status != NVJPEG_STATUS_SUCCESS)
        {
            return 0;
        }

        // Retrieve encoded data
        output.resize(encoded_size);
        status = nvjpegEncodeRetrieveBitstream(
            static_cast<nvjpegHandle_t>(nvjpeg_handle_),
            static_cast<nvjpegEncoderState_t>(encoder_state_),
            output.data(),
            &encoded_size,
            static_cast<cudaStream_t>(cuda_stream_));

        // Sync stream
        cudaStreamSynchronize(static_cast<cudaStream_t>(cuda_stream_));

        if (status != NVJPEG_STATUS_SUCCESS)
        {
            return 0;
        }

        return encoded_size;
    }

#else // !HAS_CUDA

    // Stub implementations when CUDA is not available
    NvJPEGEncoder::NvJPEGEncoder() = default;
    NvJPEGEncoder::~NvJPEGEncoder() = default;

    bool NvJPEGEncoder::init()
    {
        VRS_LOG_INFO("nvJPEG not available (CUDA disabled)");
        return false;
    }

    void NvJPEGEncoder::shutdown() {}

    size_t NvJPEGEncoder::encode(
        const u8 *, u32, u32, u32, u32, u32, std::vector<u8> &)
    {
        return 0;
    }

    size_t NvJPEGEncoder::encode_gpu(
        void *, u32, u32, u32, u32, std::vector<u8> &)
    {
        return 0;
    }

#endif // HAS_CUDA

    // ============================================================================
    // OpenCVJPEGEncoder Implementation (Fallback)
    // ============================================================================

    size_t OpenCVJPEGEncoder::encode(
        const u8 *input,
        u32 width, u32 height,
        u32 pitch, u32 channels,
        u32 quality,
        std::vector<u8> &output)
    {
        Timer timer;
        (void)input;
        (void)width;
        (void)height;
        (void)pitch;
        (void)channels;
        (void)quality;
        (void)output;

        // This is a minimal fallback - in production, link with OpenCV
        // The TurboJPEG encoder should be available in all practical cases
        VRS_LOG_WARN("OpenCV fallback encoder used - consider installing TurboJPEG");

        last_encode_time_ = timer.elapsed_ms();
        return 0;
    }

    // ============================================================================
    // AutoJPEGEncoder Implementation
    // ============================================================================

    AutoJPEGEncoder::AutoJPEGEncoder()
    {
#ifdef HAS_CUDA
        // Try nvJPEG first (GPU)
        nvjpeg_ = std::make_unique<NvJPEGEncoder>();
        if (nvjpeg_->init())
        {
            best_encoder_ = nvjpeg_.get();
            VRS_LOG_INFO("Auto-selected nvJPEG encoder (GPU)");
            return;
        }
#endif

        // Try TurboJPEG (SIMD CPU)
        turbojpeg_ = std::make_unique<TurboJPEGEncoder>();
        if (turbojpeg_->available())
        {
            best_encoder_ = turbojpeg_.get();
            VRS_LOG_INFO("Auto-selected TurboJPEG encoder (CPU SIMD)");
            return;
        }

        // Fallback to OpenCV
        opencv_ = std::make_unique<OpenCVJPEGEncoder>();
        best_encoder_ = opencv_.get();
        VRS_LOG_WARN("Fell back to OpenCV encoder");
    }

    size_t AutoJPEGEncoder::encode(
        const u8 *input,
        u32 width, u32 height,
        u32 pitch, u32 channels,
        u32 quality,
        std::vector<u8> &output)
    {
        if (!best_encoder_)
            return 0;
        return best_encoder_->encode(input, width, height, pitch, channels, quality, output);
    }

    std::string_view AutoJPEGEncoder::name() const
    {
        if (best_encoder_)
            return best_encoder_->name();
        return "None";
    }

    f64 AutoJPEGEncoder::last_encode_time_ms() const
    {
        if (best_encoder_)
            return best_encoder_->last_encode_time_ms();
        return 0;
    }

} // namespace vrs
