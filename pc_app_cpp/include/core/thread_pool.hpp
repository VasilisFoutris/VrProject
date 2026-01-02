#pragma once
/**
 * VR Streamer - Thread Pool
 * High-performance thread pool with work stealing for parallel encoding.
 */

#include "common.hpp"
#include <queue>
#include <future>

namespace vrs
{

    /**
     * Modern thread pool implementation with minimal overhead.
     */
    class ThreadPool
    {
    public:
        explicit ThreadPool(size_t num_threads = 0) : stop_(false)
        {
            if (num_threads == 0)
            {
                num_threads = std::thread::hardware_concurrency();
                if (num_threads == 0)
                    num_threads = 4;
            }

            workers_.reserve(num_threads);
            for (size_t i = 0; i < num_threads; ++i)
            {
                workers_.emplace_back([this]
                                      { worker_loop(); });
            }
        }

        ~ThreadPool()
        {
            {
                std::lock_guard lock(mutex_);
                stop_ = true;
            }
            cv_.notify_all();
            for (auto &worker : workers_)
            {
                if (worker.joinable())
                {
                    worker.join();
                }
            }
        }

        ThreadPool(const ThreadPool &) = delete;
        ThreadPool &operator=(const ThreadPool &) = delete;

        /**
         * Submit a task and get a future for the result.
         */
        template <typename F, typename... Args>
        [[nodiscard]] auto submit(F &&f, Args &&...args)
            -> std::future<std::invoke_result_t<F, Args...>>
        {
            using ReturnType = std::invoke_result_t<F, Args...>;

            auto task = std::make_shared<std::packaged_task<ReturnType()>>(
                std::bind(std::forward<F>(f), std::forward<Args>(args)...));

            std::future<ReturnType> result = task->get_future();

            {
                std::lock_guard lock(mutex_);
                if (stop_)
                {
                    throw std::runtime_error("ThreadPool stopped");
                }
                tasks_.emplace([task]()
                               { (*task)(); });
            }

            cv_.notify_one();
            return result;
        }

        /**
         * Submit a task without caring about the result.
         */
        template <typename F>
        void submit_detached(F &&f)
        {
            {
                std::lock_guard lock(mutex_);
                if (stop_)
                    return;
                tasks_.emplace(std::forward<F>(f));
            }
            cv_.notify_one();
        }

        /**
         * Get the number of worker threads.
         */
        [[nodiscard]] size_t size() const noexcept { return workers_.size(); }

        /**
         * Get approximate queue size.
         */
        [[nodiscard]] size_t pending() const
        {
            std::lock_guard lock(mutex_);
            return tasks_.size();
        }

    private:
        void worker_loop()
        {
            while (true)
            {
                std::function<void()> task;

                {
                    std::unique_lock lock(mutex_);
                    cv_.wait(lock, [this]
                             { return stop_ || !tasks_.empty(); });

                    if (stop_ && tasks_.empty())
                    {
                        return;
                    }

                    task = std::move(tasks_.front());
                    tasks_.pop();
                }

                task();
            }
        }

        std::vector<std::thread> workers_;
        std::queue<std::function<void()>> tasks_;
        mutable std::mutex mutex_;
        std::condition_variable cv_;
        bool stop_;
    };

    /**
     * Global thread pool singleton.
     */
    inline ThreadPool &get_global_thread_pool()
    {
        static ThreadPool pool;
        return pool;
    }

} // namespace vrs
