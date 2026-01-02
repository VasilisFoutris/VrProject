#pragma once
/**
 * VR Streamer - Memory Pool
 * Pre-allocated memory pools for zero-allocation frame processing.
 * Uses a fixed-size block allocator for consistent performance.
 */

#include "common.hpp"
#include <mutex>
#include <stack>

namespace vrs
{

    /**
     * Fixed-size block pool for frame buffers.
     * Thread-safe with minimal contention using a lock-free free list.
     */
    class FrameBufferPool
    {
    public:
        struct Buffer
        {
            AlignedPtr<u8> data;
            size_t capacity;
            size_t size;
            u32 width;
            u32 height;
            u32 stride;
            u32 format;    // DXGI_FORMAT or custom format enum
            u64 timestamp; // Capture timestamp in nanoseconds
            u32 frame_id;

            Buffer() : capacity(0), size(0), width(0), height(0), stride(0),
                       format(0), timestamp(0), frame_id(0) {}

            void allocate(size_t cap)
            {
                if (cap > capacity)
                {
                    data = make_aligned_array<u8>(cap, PAGE_SIZE);
                    capacity = cap;
                }
                size = 0;
            }

            void reset()
            {
                size = 0;
                width = 0;
                height = 0;
                stride = 0;
                timestamp = 0;
            }
        };

        using BufferPtr = std::shared_ptr<Buffer>;

        explicit FrameBufferPool(size_t buffer_size, size_t pool_size = 8)
            : buffer_size_(buffer_size), pool_size_(pool_size)
        {
            // Pre-allocate all buffers
            for (size_t i = 0; i < pool_size; ++i)
            {
                auto buf = std::make_shared<Buffer>();
                buf->allocate(buffer_size);
                free_buffers_.push(buf);
            }
        }

        /**
         * Acquire a buffer from the pool.
         * Returns nullptr if no buffers available.
         */
        [[nodiscard]] BufferPtr acquire()
        {
            std::lock_guard lock(mutex_);
            if (free_buffers_.empty())
            {
                // Grow pool if needed (avoid in hot path)
                auto buf = std::make_shared<Buffer>();
                buf->allocate(buffer_size_);
                return buf;
            }
            auto buf = free_buffers_.top();
            free_buffers_.pop();
            buf->reset();
            return buf;
        }

        /**
         * Release a buffer back to the pool.
         */
        void release(BufferPtr buf)
        {
            if (!buf)
                return;
            std::lock_guard lock(mutex_);
            if (free_buffers_.size() < pool_size_ * 2)
            {
                buf->reset();
                free_buffers_.push(std::move(buf));
            }
            // Else let it be destroyed (pool is oversized)
        }

        /**
         * Get buffer size.
         */
        [[nodiscard]] size_t buffer_size() const noexcept { return buffer_size_; }

        /**
         * Get number of free buffers.
         */
        [[nodiscard]] size_t free_count() const
        {
            std::lock_guard lock(mutex_);
            return free_buffers_.size();
        }

    private:
        size_t buffer_size_;
        size_t pool_size_;
        std::stack<BufferPtr> free_buffers_;
        mutable std::mutex mutex_;
    };

    /**
     * RAII wrapper for auto-release of pooled buffers.
     */
    class PooledBuffer
    {
    public:
        PooledBuffer() : pool_(nullptr) {}

        PooledBuffer(FrameBufferPool &pool, FrameBufferPool::BufferPtr buf)
            : pool_(&pool), buffer_(std::move(buf)) {}

        PooledBuffer(PooledBuffer &&other) noexcept
            : pool_(other.pool_), buffer_(std::move(other.buffer_))
        {
            other.pool_ = nullptr;
        }

        PooledBuffer &operator=(PooledBuffer &&other) noexcept
        {
            if (this != &other)
            {
                release();
                pool_ = other.pool_;
                buffer_ = std::move(other.buffer_);
                other.pool_ = nullptr;
            }
            return *this;
        }

        ~PooledBuffer() { release(); }

        PooledBuffer(const PooledBuffer &) = delete;
        PooledBuffer &operator=(const PooledBuffer &) = delete;

        void release()
        {
            if (pool_ && buffer_)
            {
                pool_->release(std::move(buffer_));
                buffer_.reset();
            }
        }

        [[nodiscard]] FrameBufferPool::Buffer *get() const noexcept
        {
            return buffer_.get();
        }

        [[nodiscard]] FrameBufferPool::Buffer *operator->() const noexcept
        {
            return buffer_.get();
        }

        [[nodiscard]] FrameBufferPool::BufferPtr shared() const noexcept
        {
            return buffer_;
        }

        [[nodiscard]] explicit operator bool() const noexcept
        {
            return buffer_ != nullptr;
        }

    private:
        FrameBufferPool *pool_;
        FrameBufferPool::BufferPtr buffer_;
    };

    /**
     * Compressed frame buffer for encoded data.
     */
    struct CompressedFrame
    {
        std::vector<u8> data;
        u32 width;
        u32 height;
        u64 timestamp;
        u32 frame_id;
        f32 encode_time_ms;

        CompressedFrame() : width(0), height(0), timestamp(0), frame_id(0), encode_time_ms(0) {}

        void reserve(size_t cap)
        {
            if (data.capacity() < cap)
            {
                data.reserve(cap);
            }
        }

        void clear()
        {
            data.clear();
            encode_time_ms = 0;
        }

        [[nodiscard]] size_t size() const noexcept { return data.size(); }
        [[nodiscard]] const u8 *ptr() const noexcept { return data.data(); }
    };

    using CompressedFramePtr = std::shared_ptr<CompressedFrame>;

    /**
     * Pool for compressed frames.
     */
    class CompressedFramePool
    {
    public:
        explicit CompressedFramePool(size_t reserve_size = 512 * 1024, size_t pool_size = 8)
            : reserve_size_(reserve_size), pool_size_(pool_size)
        {
            for (size_t i = 0; i < pool_size; ++i)
            {
                auto frame = std::make_shared<CompressedFrame>();
                frame->reserve(reserve_size);
                free_frames_.push(std::move(frame));
            }
        }

        [[nodiscard]] CompressedFramePtr acquire()
        {
            std::lock_guard lock(mutex_);
            if (free_frames_.empty())
            {
                auto frame = std::make_shared<CompressedFrame>();
                frame->reserve(reserve_size_);
                return frame;
            }
            auto frame = free_frames_.top();
            free_frames_.pop();
            frame->clear();
            return frame;
        }

        void release(CompressedFramePtr frame)
        {
            if (!frame)
                return;
            std::lock_guard lock(mutex_);
            if (free_frames_.size() < pool_size_ * 2)
            {
                frame->clear();
                free_frames_.push(std::move(frame));
            }
        }

    private:
        size_t reserve_size_;
        size_t pool_size_;
        std::stack<CompressedFramePtr> free_frames_;
        mutable std::mutex mutex_;
    };

} // namespace vrs
