#pragma once
/**
 * VR Streamer - Lock-Free Single Producer Single Consumer Queue
 * Wait-free ring buffer for minimal latency frame passing between threads.
 * Optimized for cache efficiency and branch prediction.
 */

#include "common.hpp"

namespace vrs
{

    /**
     * Lock-free SPSC queue using a ring buffer.
     * Template parameters:
     *   T - Element type (must be trivially copyable for best performance)
     *   N - Capacity (must be power of 2)
     */
    template <typename T, size_t N>
        requires(is_power_of_2(N) && N >= 2)
    class SPSCQueue
    {
    public:
        static constexpr size_t CAPACITY = N;
        static constexpr size_t MASK = N - 1;

        SPSCQueue() noexcept : head_(0), tail_(0)
        {
            // Pre-touch memory to avoid page faults in hot path
            for (size_t i = 0; i < N; ++i)
            {
                new (&storage_[i]) T{};
            }
        }

        ~SPSCQueue() noexcept
        {
            // Clear any remaining elements
            T temp;
            while (try_pop(temp))
            {
            }
        }

        SPSCQueue(const SPSCQueue &) = delete;
        SPSCQueue &operator=(const SPSCQueue &) = delete;

        /**
         * Try to push an element (producer only).
         * Returns true if successful, false if queue is full.
         */
        [[nodiscard]] VRS_FORCEINLINE bool try_push(const T &item) noexcept
        {
            const size_t tail = tail_.load(std::memory_order_relaxed);
            const size_t next = (tail + 1) & MASK;

            if (next == head_.load(std::memory_order_acquire))
            {
                return false; // Queue is full
            }

            storage_[tail] = item;
            tail_.store(next, std::memory_order_release);
            return true;
        }

        /**
         * Try to push by moving (producer only).
         */
        [[nodiscard]] VRS_FORCEINLINE bool try_push(T &&item) noexcept
        {
            const size_t tail = tail_.load(std::memory_order_relaxed);
            const size_t next = (tail + 1) & MASK;

            if (next == head_.load(std::memory_order_acquire))
            {
                return false;
            }

            storage_[tail] = std::move(item);
            tail_.store(next, std::memory_order_release);
            return true;
        }

        /**
         * Try to pop an element (consumer only).
         * Returns true if successful, false if queue is empty.
         */
        [[nodiscard]] VRS_FORCEINLINE bool try_pop(T &item) noexcept
        {
            const size_t head = head_.load(std::memory_order_relaxed);

            if (head == tail_.load(std::memory_order_acquire))
            {
                return false; // Queue is empty
            }

            item = std::move(storage_[head]);
            head_.store((head + 1) & MASK, std::memory_order_release);
            return true;
        }

        /**
         * Peek at the front element without removing (consumer only).
         */
        [[nodiscard]] VRS_FORCEINLINE const T *peek() const noexcept
        {
            const size_t head = head_.load(std::memory_order_relaxed);

            if (head == tail_.load(std::memory_order_acquire))
            {
                return nullptr;
            }

            return &storage_[head];
        }

        /**
         * Check if queue is empty.
         */
        [[nodiscard]] VRS_FORCEINLINE bool empty() const noexcept
        {
            return head_.load(std::memory_order_acquire) ==
                   tail_.load(std::memory_order_acquire);
        }

        /**
         * Get approximate size (may be outdated by the time you use it).
         */
        [[nodiscard]] size_t size_approx() const noexcept
        {
            const size_t head = head_.load(std::memory_order_relaxed);
            const size_t tail = tail_.load(std::memory_order_relaxed);
            return (tail - head + N) & MASK;
        }

        /**
         * Check if queue is full.
         */
        [[nodiscard]] bool full() const noexcept
        {
            const size_t tail = tail_.load(std::memory_order_relaxed);
            const size_t next = (tail + 1) & MASK;
            return next == head_.load(std::memory_order_acquire);
        }

        /**
         * Clear the queue (consumer only - use when producer is paused).
         */
        void clear() noexcept
        {
            head_.store(tail_.load(std::memory_order_relaxed), std::memory_order_release);
        }

    private:
        // Separate head and tail into different cache lines to avoid false sharing
        alignas(CACHE_LINE_SIZE) std::atomic<size_t> head_;
        alignas(CACHE_LINE_SIZE) std::atomic<size_t> tail_;
        alignas(CACHE_LINE_SIZE) std::array<T, N> storage_;
    };

    /**
     * SPSC queue optimized for frame data (large objects).
     * Uses indices to pre-allocated slots to minimize copying.
     */
    template <typename T, size_t N>
        requires(is_power_of_2(N) && N >= 2)
    class SPSCFrameQueue
    {
    public:
        SPSCFrameQueue() noexcept : head_(0), tail_(0), write_in_progress_(false)
        {
            for (size_t i = 0; i < N; ++i)
            {
                slots_[i].ready.store(false, std::memory_order_relaxed);
            }
        }

        /**
         * Get a slot for writing. Returns nullptr if queue is full.
         * Must call commit_write() after writing.
         */
        [[nodiscard]] T *begin_write() noexcept
        {
            if (write_in_progress_)
                return nullptr;

            const size_t tail = tail_.load(std::memory_order_relaxed);
            const size_t next = (tail + 1) & (N - 1);

            if (next == head_.load(std::memory_order_acquire))
            {
                return nullptr;
            }

            write_in_progress_ = true;
            return &slots_[tail].data;
        }

        /**
         * Commit a write started with begin_write().
         */
        void commit_write() noexcept
        {
            if (!write_in_progress_)
                return;

            const size_t tail = tail_.load(std::memory_order_relaxed);
            slots_[tail].ready.store(true, std::memory_order_release);
            tail_.store((tail + 1) & (N - 1), std::memory_order_release);
            write_in_progress_ = false;
        }

        /**
         * Get the front element for reading. Returns nullptr if empty.
         */
        [[nodiscard]] const T *peek_read() const noexcept
        {
            const size_t head = head_.load(std::memory_order_relaxed);

            if (head == tail_.load(std::memory_order_acquire))
            {
                return nullptr;
            }

            if (!slots_[head].ready.load(std::memory_order_acquire))
            {
                return nullptr;
            }

            return &slots_[head].data;
        }

        /**
         * Complete reading and remove the front element.
         */
        void complete_read() noexcept
        {
            const size_t head = head_.load(std::memory_order_relaxed);
            slots_[head].ready.store(false, std::memory_order_relaxed);
            head_.store((head + 1) & (N - 1), std::memory_order_release);
        }

        [[nodiscard]] bool empty() const noexcept
        {
            return head_.load(std::memory_order_acquire) ==
                   tail_.load(std::memory_order_acquire);
        }

    private:
        struct Slot
        {
            alignas(CACHE_LINE_SIZE) T data;
            std::atomic<bool> ready{false};
        };

        alignas(CACHE_LINE_SIZE) std::atomic<size_t> head_;
        alignas(CACHE_LINE_SIZE) std::atomic<size_t> tail_;
        alignas(CACHE_LINE_SIZE) std::array<Slot, N> slots_;
        bool write_in_progress_{false};
    };

} // namespace vrs
