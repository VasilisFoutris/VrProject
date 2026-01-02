#pragma once
/**
 * VR Streamer - Common Definitions
 * Platform macros, types, and utility functions for maximum performance.
 */

// Windows target version
#ifdef _WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00 // Windows 10
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
// Include WinSock2 BEFORE Windows.h to avoid conflicts with Boost.Asio
#include <WinSock2.h>
#include <WS2tcpip.h>
#include <Windows.h>
#endif

// Platform detection
#ifdef _WIN32
#define VRS_PLATFORM_WINDOWS 1
#define VRS_EXPORT __declspec(dllexport)
#define VRS_IMPORT __declspec(dllimport)
#define VRS_FORCEINLINE __forceinline
#define VRS_NOINLINE __declspec(noinline)
#define VRS_ALIGN(x) __declspec(align(x))
#define VRS_LIKELY(x) (x)
#define VRS_UNLIKELY(x) (x)
#define VRS_RESTRICT __restrict
#define VRS_ASSUME(x) __assume(x)
#else
#define VRS_PLATFORM_WINDOWS 0
#define VRS_EXPORT __attribute__((visibility("default")))
#define VRS_IMPORT
#define VRS_FORCEINLINE __attribute__((always_inline)) inline
#define VRS_NOINLINE __attribute__((noinline))
#define VRS_ALIGN(x) __attribute__((aligned(x)))
#define VRS_LIKELY(x) __builtin_expect(!!(x), 1)
#define VRS_UNLIKELY(x) __builtin_expect(!!(x), 0)
#define VRS_RESTRICT __restrict__
#define VRS_ASSUME(x)                \
    do                               \
    {                                \
        if (!(x))                    \
            __builtin_unreachable(); \
    } while (0)
#endif

// SIMD support
#if defined(__AVX2__) || defined(_MSC_VER)
#define VRS_HAS_AVX2 1
#include <immintrin.h>
#else
#define VRS_HAS_AVX2 0
#endif

#if defined(__AVX512F__) || (defined(_MSC_VER) && defined(__AVX512F__))
#define VRS_HAS_AVX512 1
#else
#define VRS_HAS_AVX512 0
#endif

// Standard includes
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <string>
#include <string_view>
#include <memory>
#include <vector>
#include <array>
#include <span>
#include <optional>
#include <variant>
#include <functional>
#include <chrono>
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <stdexcept>
#include <format>
#include <source_location>
#include <bit>

namespace vrs
{

    // Type aliases for clarity
    using i8 = int8_t;
    using i16 = int16_t;
    using i32 = int32_t;
    using i64 = int64_t;
    using u8 = uint8_t;
    using u16 = uint16_t;
    using u32 = uint32_t;
    using u64 = uint64_t;
    using f32 = float;
    using f64 = double;

    using byte = std::byte;
    using ByteSpan = std::span<byte>;
    using ConstByteSpan = std::span<const byte>;

    // Time types
    using Clock = std::chrono::high_resolution_clock;
    using TimePoint = Clock::time_point;
    using Duration = Clock::duration;
    using Nanoseconds = std::chrono::nanoseconds;
    using Microseconds = std::chrono::microseconds;
    using Milliseconds = std::chrono::milliseconds;

    // Cache line size for padding to avoid false sharing
    constexpr size_t CACHE_LINE_SIZE = 64;

    // Page size for memory alignment
    constexpr size_t PAGE_SIZE = 4096;

    // Max frame dimensions
    constexpr u32 MAX_WIDTH = 7680; // 8K
    constexpr u32 MAX_HEIGHT = 4320;
    constexpr u32 MAX_FRAME_SIZE = MAX_WIDTH * MAX_HEIGHT * 4;

    /**
     * Aligned memory allocation for SIMD and GPU operations.
     */
    template <typename T>
    struct AlignedDeleter
    {
        void operator()(T *ptr) const noexcept
        {
#ifdef _WIN32
            _aligned_free(ptr);
#else
            std::free(ptr);
#endif
        }
    };

    template <typename T>
    using AlignedPtr = std::unique_ptr<T[], AlignedDeleter<T>>;

    template <typename T>
    [[nodiscard]] VRS_FORCEINLINE AlignedPtr<T> make_aligned_array(size_t count, size_t alignment = CACHE_LINE_SIZE)
    {
#ifdef _WIN32
        auto *ptr = static_cast<T *>(_aligned_malloc(count * sizeof(T), alignment));
#else
        T *ptr = nullptr;
        if (posix_memalign(reinterpret_cast<void **>(&ptr), alignment, count * sizeof(T)) != 0)
        {
            ptr = nullptr;
        }
#endif
        if (!ptr)
            throw std::bad_alloc();
        return AlignedPtr<T>(ptr);
    }

    /**
     * High-resolution timer for profiling.
     */
    class Timer
    {
    public:
        Timer() noexcept : start_(Clock::now()) {}

        void reset() noexcept { start_ = Clock::now(); }

        [[nodiscard]] VRS_FORCEINLINE f64 elapsed_ns() const noexcept
        {
            return std::chrono::duration<f64, std::nano>(Clock::now() - start_).count();
        }

        [[nodiscard]] VRS_FORCEINLINE f64 elapsed_us() const noexcept
        {
            return std::chrono::duration<f64, std::micro>(Clock::now() - start_).count();
        }

        [[nodiscard]] VRS_FORCEINLINE f64 elapsed_ms() const noexcept
        {
            return std::chrono::duration<f64, std::milli>(Clock::now() - start_).count();
        }

        [[nodiscard]] VRS_FORCEINLINE f64 elapsed_s() const noexcept
        {
            return std::chrono::duration<f64>(Clock::now() - start_).count();
        }

    private:
        TimePoint start_;
    };

    /**
     * Scoped timer for automatic timing measurement.
     */
    class ScopedTimer
    {
    public:
        explicit ScopedTimer(f64 &out_ms) noexcept : out_ms_(out_ms) {}
        ~ScopedTimer() noexcept { out_ms_ = timer_.elapsed_ms(); }

        ScopedTimer(const ScopedTimer &) = delete;
        ScopedTimer &operator=(const ScopedTimer &) = delete;

    private:
        Timer timer_;
        f64 &out_ms_;
    };

    /**
     * FPS counter with smoothing.
     */
    class FPSCounter
    {
    public:
        FPSCounter() noexcept : last_time_(Clock::now()), frame_count_(0), fps_(0.0) {}

        void tick() noexcept
        {
            ++frame_count_;
            auto now = Clock::now();
            auto elapsed = std::chrono::duration<f64>(now - last_time_).count();

            if (elapsed >= 1.0)
            {
                fps_ = frame_count_ / elapsed;
                frame_count_ = 0;
                last_time_ = now;
            }
        }

        [[nodiscard]] f64 fps() const noexcept { return fps_; }

    private:
        TimePoint last_time_;
        u64 frame_count_;
        f64 fps_;
    };

    /**
     * Spin-wait with exponential backoff.
     */
    VRS_FORCEINLINE void spin_wait(u32 iterations = 100) noexcept
    {
        for (u32 i = 0; i < iterations; ++i)
        {
#if defined(_MSC_VER) && (defined(_M_IX86) || defined(_M_X64))
            _mm_pause();
#elif defined(__x86_64__) || defined(__i386__)
            __builtin_ia32_pause();
#elif defined(__aarch64__)
            __asm__ volatile("yield" ::: "memory");
#else
            std::this_thread::yield();
#endif
        }
    }

    /**
     * Round up to power of 2.
     */
    [[nodiscard]] constexpr VRS_FORCEINLINE u64 next_power_of_2(u64 v) noexcept
    {
        return std::bit_ceil(v);
    }

    /**
     * Check if value is power of 2.
     */
    [[nodiscard]] constexpr VRS_FORCEINLINE bool is_power_of_2(u64 v) noexcept
    {
        return std::has_single_bit(v);
    }

    /**
     * Result type for operations that can fail.
     */
    template <typename T, typename E = std::string>
    using Result = std::variant<T, E>;

    template <typename T, typename E>
    [[nodiscard]] VRS_FORCEINLINE bool is_ok(const Result<T, E> &result) noexcept
    {
        return std::holds_alternative<T>(result);
    }

    template <typename T, typename E>
    [[nodiscard]] VRS_FORCEINLINE const T &get_ok(const Result<T, E> &result)
    {
        return std::get<T>(result);
    }

    template <typename T, typename E>
    [[nodiscard]] VRS_FORCEINLINE T &get_ok(Result<T, E> &result)
    {
        return std::get<T>(result);
    }

    template <typename T, typename E>
    [[nodiscard]] VRS_FORCEINLINE const E &get_err(const Result<T, E> &result)
    {
        return std::get<E>(result);
    }

    /**
     * RAII helper for COM pointers.
     */
    template <typename T>
    class ComPtr
    {
    public:
        ComPtr() noexcept : ptr_(nullptr) {}
        ComPtr(std::nullptr_t) noexcept : ptr_(nullptr) {}
        explicit ComPtr(T *p) noexcept : ptr_(p) {}

        ComPtr(const ComPtr &other) noexcept : ptr_(other.ptr_)
        {
            if (ptr_)
                ptr_->AddRef();
        }

        ComPtr(ComPtr &&other) noexcept : ptr_(other.ptr_)
        {
            other.ptr_ = nullptr;
        }

        ~ComPtr() noexcept
        {
            if (ptr_)
                ptr_->Release();
        }

        ComPtr &operator=(const ComPtr &other) noexcept
        {
            if (this != &other)
            {
                if (ptr_)
                    ptr_->Release();
                ptr_ = other.ptr_;
                if (ptr_)
                    ptr_->AddRef();
            }
            return *this;
        }

        ComPtr &operator=(ComPtr &&other) noexcept
        {
            if (this != &other)
            {
                if (ptr_)
                    ptr_->Release();
                ptr_ = other.ptr_;
                other.ptr_ = nullptr;
            }
            return *this;
        }

        ComPtr &operator=(std::nullptr_t) noexcept
        {
            if (ptr_)
                ptr_->Release();
            ptr_ = nullptr;
            return *this;
        }

        T *operator->() const noexcept { return ptr_; }
        T &operator*() const noexcept { return *ptr_; }
        T *get() const noexcept { return ptr_; }
        T **address_of() noexcept { return &ptr_; }
        T *const *address_of() const noexcept { return &ptr_; }

        void reset(T *p = nullptr) noexcept
        {
            if (ptr_)
                ptr_->Release();
            ptr_ = p;
        }

        T *release() noexcept
        {
            T *p = ptr_;
            ptr_ = nullptr;
            return p;
        }

        [[nodiscard]] explicit operator bool() const noexcept { return ptr_ != nullptr; }
        [[nodiscard]] bool operator!() const noexcept { return ptr_ == nullptr; }

        // Comparison operators
        [[nodiscard]] friend bool operator==(const ComPtr &lhs, std::nullptr_t) noexcept { return lhs.ptr_ == nullptr; }
        [[nodiscard]] friend bool operator==(std::nullptr_t, const ComPtr &rhs) noexcept { return rhs.ptr_ == nullptr; }
        [[nodiscard]] friend bool operator!=(const ComPtr &lhs, std::nullptr_t) noexcept { return lhs.ptr_ != nullptr; }
        [[nodiscard]] friend bool operator!=(std::nullptr_t, const ComPtr &rhs) noexcept { return rhs.ptr_ != nullptr; }
        [[nodiscard]] friend bool operator==(const ComPtr &lhs, const ComPtr &rhs) noexcept { return lhs.ptr_ == rhs.ptr_; }
        [[nodiscard]] friend bool operator!=(const ComPtr &lhs, const ComPtr &rhs) noexcept { return lhs.ptr_ != rhs.ptr_; }

    private:
        T *ptr_;
    };

// Logging macros (compile-time disabled in release for zero overhead)
#ifdef NDEBUG
#define VRS_LOG_DEBUG(...)
#else
#define VRS_LOG_DEBUG(...) ::vrs::log_debug(__VA_ARGS__)
#endif

#define VRS_LOG_INFO(...) ::vrs::log_info(__VA_ARGS__)
#define VRS_LOG_WARN(...) ::vrs::log_warn(__VA_ARGS__)
#define VRS_LOG_ERROR(...) ::vrs::log_error(__VA_ARGS__)

    void log_debug(std::string_view msg);
    void log_info(std::string_view msg);
    void log_warn(std::string_view msg);
    void log_error(std::string_view msg);

} // namespace vrs
